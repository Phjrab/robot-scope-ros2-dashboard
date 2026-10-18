"""Synthetic opt-in observation hypotheses; no ROS, hardware or motion."""
import copy
import time
import unittest
from unittest.mock import patch

import numpy as np
from pydantic import ValidationError

from robot_dashboard.api.routers.observation_alignment import ObservationRequest
from robot_dashboard.relocalization.observation_alignment import (
    ObservationAligner, ObservationAlignmentError, project_query, register_se3,
)
from robot_dashboard.ros.observation_identity import (
    make_subscription_evidence, subscription_graph_snapshot,
)
from test_observation_alignment import Agent, Catalog, inputs, request_body


QOS = {"reliability": "BEST_EFFORT", "durability": "VOLATILE", "history": "KEEP_LAST", "depth": 1}


def evidence(topic, type_name, *, session="1", endpoint="2", at=None):
    endpoint_info = dict(node_name="fixture", node_namespace="/", topic_type=type_name,
                         endpoint_gid=endpoint * 48, qos=QOS.copy())
    graph = subscription_graph_snapshot(topic, type_name, 1, [endpoint_info],
                                        time.monotonic() if at is None else at)
    return make_subscription_evidence(session * 32, topic, type_name, QOS.copy(), graph)


def subscription_inputs(points=None):
    cloud, pose = inputs(points)
    for value, type_name, session in (
        (cloud, "sensor_msgs/msg/PointCloud2", "1"),
        (pose, "nav_msgs/msg/Odometry", "2"),
    ):
        value["observation"].update(identity_status="UNAVAILABLE", publisher_gid=None,
                                    subscription_evidence=evidence(value["topic"], type_name, session=session,
                                        at=value["observation"]["received_monotonic_s"]))
    return cloud, pose


class SubscriptionAgent(Agent):
    def observation_pose_near(self, observation, *, provenance_mode="native_publisher"):
        if provenance_mode != "subscription_observation":
            raise AssertionError("fallback must explicitly request its pairing mode")
        return copy.deepcopy(self.pose)


class SubscriptionAlignmentTests(unittest.TestCase):
    def test_request_defaults_to_strict_and_rejects_unknown_mode(self):
        self.assertEqual(ObservationRequest(**request_body()).provenance_mode, "native_publisher")
        with self.assertRaises(ValidationError):
            ObservationRequest(**dict(request_body(), provenance_mode="trust_graph_as_native"))

    def test_native_gate_unchanged_and_fallback_requires_explicit_mode(self):
        cloud, pose = subscription_inputs()
        with self.assertRaisesRegex(ObservationAlignmentError, "SOURCE_IDENTITY_UNAVAILABLE"):
            project_query(cloud, pose, time.monotonic())
        _, _, provenance = project_query(cloud, pose, time.monotonic(), provenance_mode="subscription_observation")
        self.assertFalse(provenance["per_message_publisher_verified"])
        self.assertFalse(provenance["body_extrinsic_verified"])
        self.assertFalse(provenance["map_origin_verified"])
        self.assertEqual(provenance["clock_relation"], "UNVERIFIED")
        self.assertIsNone(cloud["observation"]["publisher_gid"])

    def test_candidate_is_explicitly_unverified_and_not_operational(self):
        cloud, pose = subscription_inputs()
        reference = np.frombuffer(cloud["points_bytes"], dtype="<f4").reshape(-1, 3)
        result = ObservationAligner().estimate(Catalog(reference), SubscriptionAgent(cloud, pose),
                    dict(request_body(), provenance_mode="subscription_observation"))
        self.assertEqual(result["status"], "CANDIDATE_SOURCE_UNVERIFIED")
        self.assertEqual(result["reason"], "CANDIDATE_SOURCE_UNVERIFIED")
        self.assertEqual(result["provenance_mode"], "subscription_observation")
        self.assertFalse(result["per_message_publisher_verified"])
        self.assertFalse(result["body_pose_verified"])
        self.assertFalse(result["body_extrinsic_verified"])
        self.assertIsNone(result["absolute_accuracy_m"])
        self.assertEqual(result["operational_application"], "NOT_RUN")
        self.assertEqual(result["correspondence_gate_m"], .75)
        self.assertLess(result["total_runtime_ms"], 600)
        self.assertLess(result["metrics"]["rmse_m"], .0001)

    def test_missing_stale_ambiguous_or_stalled_evidence_never_reaches_solver(self):
        def graph(value):
            return value["observation"]["subscription_evidence"]["graph"]
        changes = [
            lambda c, p: c["observation"].pop("subscription_evidence"),
            lambda c, p: graph(c).update(observed_monotonic_s=time.monotonic() - 3.1),
            lambda c, p: graph(c).update(observed_monotonic_s=time.monotonic() + 1),
            lambda c, p: graph(c).update(endpoint_count=2),
            lambda c, p: graph(c).update(state="unavailable"),
            lambda c, p: c["observation"].update(reset_reason="SOURCE_STAMP_STALLED"),
            lambda c, p: c["observation"].update(invalidated=True),
            lambda c, p: c["observation"].update(publisher_count=True),
            lambda c, p: c["observation"]["subscription_evidence"].update(topic="/another_topic"),
            lambda c, p: c["observation"]["subscription_evidence"].update(session_id=""),
        ]
        for change in changes:
            cloud, pose = subscription_inputs()
            change(cloud, pose)
            with self.subTest(change=change), self.assertRaisesRegex(ObservationAlignmentError, "EVIDENCE"):
                project_query(cloud, pose, time.monotonic(), provenance_mode="subscription_observation")

    def test_pair_freshness_units_and_frame_constraints_are_not_relaxed(self):
        for change, reason in [
            (lambda c, p: p["observation"].update(received_monotonic_s=c["observation"]["received_monotonic_s"] + .151), "MISMATCH"),
            (lambda c, p: p.update(child_frame_id="camera"), "INVALID_INPUT"),
            (lambda c, p: c.update(units="mm"), "INVALID_INPUT"),
            (lambda c, p: c.update(frame_id="unknown"), "FRAME_RELATION_UNAVAILABLE"),
        ]:
            cloud, pose = subscription_inputs()
            change(cloud, pose)
            with self.subTest(reason=reason), self.assertRaisesRegex(ObservationAlignmentError, reason):
                project_query(cloud, pose, time.monotonic(), provenance_mode="subscription_observation")
        cloud, pose = subscription_inputs()
        for value in (cloud, pose):
            value["observation"]["received_monotonic_s"] -= 1.1
        with self.assertRaisesRegex(ObservationAlignmentError, "STALE_INPUT"):
            project_query(cloud, pose, time.monotonic(), provenance_mode="subscription_observation")

    def test_endpoint_or_session_replacement_even_with_same_epoch_rejects_completion(self):
        for replacement in ("endpoint", "session"):
            cloud, pose = subscription_inputs()
            reference = np.frombuffer(cloud["points_bytes"], dtype="<f4").reshape(-1, 3)
            agent = SubscriptionAgent(cloud, pose)

            def changed(*args, **kwargs):
                result = register_se3(*args, **kwargs)
                agent.cloud["observation"]["subscription_evidence"] = evidence(
                    cloud["topic"], "sensor_msgs/msg/PointCloud2",
                    session="3" if replacement == "session" else "1",
                    endpoint="4" if replacement == "endpoint" else "2")
                return result

            with self.subTest(replacement=replacement), patch(
                "robot_dashboard.relocalization.observation_alignment.register_se3", side_effect=changed
            ), self.assertRaisesRegex(ObservationAlignmentError, "SUBSCRIPTION_EVIDENCE_CHANGED"):
                ObservationAligner().estimate(Catalog(reference), agent,
                    dict(request_body(), provenance_mode="subscription_observation"))

    def test_planar_fit_is_rejected_in_unverified_source_mode_too(self):
        plane = np.array([[x, y, 0] for x in np.linspace(-1, 1, 12) for y in np.linspace(-1, 1, 12)])
        reference = np.vstack((plane, np.random.default_rng(2).uniform(5, 8, (180, 3))))
        cloud, pose = subscription_inputs(plane)
        result = ObservationAligner().estimate(Catalog(reference), SubscriptionAgent(cloud, pose),
                    dict(request_body(), provenance_mode="subscription_observation"))
        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["reason"], "DEGENERATE_MATCHED_GEOMETRY")


if __name__ == "__main__":
    unittest.main()
