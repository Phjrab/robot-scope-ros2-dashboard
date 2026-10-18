"""Subscription evidence stays separate from native per-message identity."""

import ast
import copy
import math
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from robot_dashboard.ros.observation_identity import (
    ObservationIdentity,
    make_subscription_evidence,
    subscription_evidence_key,
    subscription_graph_snapshot,
    subscription_qos_snapshot,
    wrap_observation_callback,
)
from robot_dashboard.ros.pointcloud import PointCloudHub
from robot_dashboard.ros.observation_subscriptions import ObservationSubscriptionMixin
from robot_dashboard.ros.telemetry import TelemetryHub


CLOUD_TOPIC = "/velodyne_points"
CLOUD_TYPE = "sensor_msgs/msg/PointCloud2"
POSE_TOPIC = "/utlidar/robot_odom"
POSE_TYPE = "nav_msgs/msg/Odometry"
QOS = {"reliability": "BEST_EFFORT", "durability": "VOLATILE", "history": "KEEP_LAST", "depth": 1}
MODULE_IMPORT = "robot_dashboard.ros.observation_identity.import_module"
POINTS = np.random.default_rng(4).uniform(-1, 1, (80, 3)).astype(np.float32)
PARSED_POSE = {"frame_id": "odom", "child_frame_id": "base_link", "position": {"x": 0, "y": 0, "z": 0},
               "orientation": {"x": 0, "y": 0, "z": 0, "w": 1}}


def endpoint(type_name=CLOUD_TYPE, *, gid=2, bare=False):
    return {"node_name": "_CREATED_BY_BARE_DDS_APP_" if bare else "fixture",
            "node_namespace": "_CREATED_BY_BARE_DDS_APP_" if bare else "/",
            "topic_type": type_name, "endpoint_gid": bytes([gid]) * 24, "qos": QOS.copy()}


def evidence(topic=CLOUD_TOPIC, type_name=CLOUD_TYPE, *, session="1", gid=2, at=10.0):
    graph = subscription_graph_snapshot(topic, type_name, 1, [endpoint(type_name, gid=gid)], at)
    return make_subscription_evidence(session * 32, topic, type_name, QOS, graph)


def message(frame="odom"):
    return SimpleNamespace(header=SimpleNamespace(frame_id=frame), child_frame_id="base_link")


def hubs():
    lock = threading.RLock()
    return (lock, TelemetryHub(lock, joint_stale_after_s=1, pose_stale_after_s=1, pose_position_limit_m=1000),
            PointCloudHub(lock, max_points=1000, radius_limit_m=10, frame_interval_s=.1))


def update_pose(hub, context, *, now=10.0, stamp=1):
    with patch("robot_dashboard.ros.telemetry.extract_odometry_pose", return_value=copy.deepcopy(PARSED_POSE)):
        hub.update_pose(POSE_TOPIC, POSE_TYPE, message(), now, selected_topic=lambda: POSE_TOPIC,
                        stamp_ns=lambda _: stamp, publisher_count=1, observation_context=context)


def update_cloud(hub, context, *, now=10.0, stamp=1):
    with patch("robot_dashboard.ros.pointcloud.extract_xyz", return_value=(POINTS, len(POINTS))):
        return hub.process(CLOUD_TOPIC, message(), now, selected_topic=lambda: CLOUD_TOPIC,
                           stamp_ns=lambda _: stamp, robot_pose_in_frame=lambda _: None,
                           publisher_count=1, observation_context=context)


def agent_type():
    """Execute the production adapter methods without importing/starting ROS."""
    source = Path(__file__).resolve().parents[1] / "robot_dashboard" / "ros_agent.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    selected = {"_refresh_graph", "_create_subscription",
                "_summary_callback", "_update_pose", "_pointcloud_callback", "observation_pose_near"}
    original = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "RosAgent")
    methods = [node for node in original.body if isinstance(node, ast.FunctionDef) and node.name in selected]
    isolated = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
                               ast.ClassDef(name="AgentAdapter", bases=original.bases,
                                            keywords=[], body=methods, decorator_list=[])],
                          type_ignores=[])
    namespace = {"time": time, "get_message": lambda _: object,
                 "ObservationSubscriptionMixin": ObservationSubscriptionMixin}
    exec(compile(ast.fix_missing_locations(isolated), str(source), "exec"), namespace)
    return namespace["AgentAdapter"]


def agent():
    value = agent_type()()
    value._lock, value._telemetry_hub, value._pointcloud_hub = hubs()
    value._graph = {CLOUD_TOPIC: {"type": CLOUD_TYPE, "publishers": 1},
                    POSE_TOPIC: {"type": POSE_TYPE, "publishers": 1}}
    value._sources = {"pointcloud": CLOUD_TOPIC, "odometry": POSE_TOPIC}
    value._subscriptions, value._metrics = {}, {}
    value._observation_callbacks, value._observation_subscription_contexts = {}, {}
    value._observation_graph_snapshots = {
        CLOUD_TOPIC: evidence()["graph"], POSE_TOPIC: evidence(POSE_TOPIC, POSE_TYPE)["graph"],
    }
    value._qos_for = lambda *_: QOS.copy()
    value._tick, value._store_summary = Mock(), Mock()
    value._stamp_ns = lambda _: 1
    value._robot_pose_in_cloud_frame = lambda _: None
    value._reset_cloud_locked = lambda topic: value._pointcloud_hub.reset(topic)
    value._reset_pose_locked = lambda topic: value._telemetry_hub.reset_pose(topic, POSE_TYPE)
    value._node = SimpleNamespace(create_subscription=Mock(return_value=SimpleNamespace(qos_profile=QOS.copy())),
                                  destroy_subscription=Mock())
    return value


class SubscriptionGraphTests(unittest.TestCase):
    def test_actual_native_endpoint_and_qos_allow_bare_dds_namespace_without_native_identity(self):
        qos = SimpleNamespace(**{key: SimpleNamespace(name=val) for key, val in QOS.items() if key != "depth"},
                              depth=1, liveliness=SimpleNamespace(name="AUTOMATIC"),
                              deadline=SimpleNamespace(nanoseconds=0), lifespan=SimpleNamespace(nanoseconds=0),
                              liveliness_lease_duration=SimpleNamespace(nanoseconds=0),
                              avoid_ros_namespace_conventions=False)
        native_endpoint = SimpleNamespace(node_name="_CREATED_BY_BARE_DDS_APP_",
                                          node_namespace="_CREATED_BY_BARE_DDS_APP_", topic_type=POSE_TYPE,
                                          endpoint_gid=[3] * 24, qos_profile=qos)
        graph = subscription_graph_snapshot(POSE_TOPIC, POSE_TYPE, 1, [native_endpoint], 10.0)
        self.assertEqual(graph["state"], "ok")
        self.assertEqual(graph["endpoints"][0]["endpoint_gid"], "03" * 24)
        self.assertEqual(graph["endpoints"][0]["qos"], {
            **QOS, "liveliness": "AUTOMATIC", "deadline_ns": 0, "lifespan_ns": 0,
            "liveliness_lease_duration_ns": 0, "avoid_ros_namespace_conventions": False,
        })
        context = make_subscription_evidence("1" * 32, POSE_TOPIC, POSE_TYPE, qos, graph)
        observed = ObservationIdentity().observe(topic=POSE_TOPIC, frame="odom", stamp_ns=1, received=10,
                                                message_info={"source_timestamp": 1, "received_timestamp": 0},
                                                publisher_count=1, observation_context=context)
        self.assertIsNotNone(subscription_evidence_key(observed, 10))
        self.assertEqual(observed["identity_status"], "UNAVAILABLE")
        self.assertIsNone(observed["publisher_gid"])
        self.assertFalse(context["per_message_publisher_verified"])
        self.assertEqual(context["identity_basis"], "LOCAL_SUBSCRIPTION_AND_ROS_GRAPH_ONLY")

    def test_fingerprint_ignores_graph_receipt_time_and_tracks_actual_endpoint_contract(self):
        first = subscription_graph_snapshot(CLOUD_TOPIC, CLOUD_TYPE, 1, [endpoint()], 10)
        later = subscription_graph_snapshot(CLOUD_TOPIC, CLOUD_TYPE, 1, [endpoint()], 12)
        self.assertEqual(first["fingerprint"], later["fingerprint"])
        for field, replacement in (("node_name", "other"), ("node_namespace", "/other"),
                                   ("endpoint_gid", bytes([3]) * 24), ("qos", {**QOS, "depth": 2})):
            changed = {**endpoint(), field: replacement}
            with self.subTest(field=field):
                graph = subscription_graph_snapshot(CLOUD_TOPIC, CLOUD_TYPE, 1, [changed], 10)
                self.assertNotEqual(graph["fingerprint"], first["fingerprint"])
        other_type = "custom_msgs/msg/Cloud"
        changed = subscription_graph_snapshot(CLOUD_TOPIC, other_type, 1, [endpoint(other_type)], 10)
        self.assertNotEqual(changed["fingerprint"], first["fingerprint"])
        changed = subscription_graph_snapshot("/another", CLOUD_TYPE, 1, [endpoint()], 10)
        self.assertNotEqual(changed["fingerprint"], first["fingerprint"])

    def test_ambiguous_graph_missing_gid_or_qos_never_supplies_evidence_key(self):
        cases = [(count, [endpoint()]) for count in (None, 0, 2, True, 1.0, "1")]
        cases += [(1, []), (1, [endpoint(), endpoint(gid=3)])]
        cases += [(1, [{**endpoint(), field: bad}]) for field, bad in (
            ("endpoint_gid", None), ("endpoint_gid", bytes(24)), ("endpoint_gid", [True] * 24),
            ("qos", {}), ("qos", {**QOS, "depth": True}), ("qos", {**QOS, "reliability": "UNKNOWN"}),
            ("node_name", ""), ("node_namespace", ""), ("topic_type", POSE_TYPE),
        )]
        for count, endpoints in cases:
            with self.subTest(count=count, endpoints=endpoints):
                graph = subscription_graph_snapshot(CLOUD_TOPIC, CLOUD_TYPE, count, endpoints, 10)
                context = make_subscription_evidence("1" * 32, CLOUD_TOPIC, CLOUD_TYPE, QOS, graph)
                self.assertEqual(graph["state"], "unavailable")
                self.assertIsNone(graph["fingerprint"])
                self.assertIsNone(subscription_evidence_key({"subscription_evidence": context}, 10))
        self.assertEqual(subscription_qos_snapshot(None), {})
        self.assertEqual(subscription_qos_snapshot({"depth": True}), {})

    def test_key_revalidates_fingerprint_schema_session_and_graph_freshness(self):
        observed = {"subscription_evidence": evidence()}
        original = subscription_evidence_key(observed, 10)
        self.assertIsNotNone(original)
        self.assertEqual(subscription_evidence_key(observed, 13), original)
        for now in (9.99, 13.001, math.inf, math.nan):
            with self.subTest(now=now):
                self.assertIsNone(subscription_evidence_key(observed, now))
        changes = [lambda o: o.update(invalidated=True),
                   lambda o: o.update(reset_reason="SOURCE_STAMP_STALLED"),
                   lambda o: o["subscription_evidence"].update(session_id="bad"),
                   lambda o: o["subscription_evidence"].update(schema="other"),
                   lambda o: o["subscription_evidence"].update(identity_basis="NATIVE"),
                   lambda o: o["subscription_evidence"].update(per_message_publisher_verified=True),
                   lambda o: o["subscription_evidence"].update(subscription_qos={}),
                   lambda o: o["subscription_evidence"]["graph"].update(endpoint_count=True),
                   lambda o: o["subscription_evidence"]["graph"].update(reported_publisher_count=True),
                   lambda o: o["subscription_evidence"]["graph"].update(state="unavailable", reason="GRAPH_REFRESH_FAILED"),
                   lambda o: o["subscription_evidence"]["graph"]["endpoints"][0].update(node_name="replacement"),
                   lambda o: o["subscription_evidence"]["graph"].update(fingerprint="0" * 64)]
        for change in changes:
            changed = copy.deepcopy(observed)
            change(changed)
            with self.subTest(change=change):
                self.assertIsNone(subscription_evidence_key(changed, 10))


class SubscriptionHubTests(unittest.TestCase):
    def test_real_wrappers_have_distinct_sessions_and_keep_native_metadata_absent(self):
        _, pose_hub, _ = hubs()
        captured = []

        def callback(topic, type_name, value, **kwargs):
            captured.append(kwargs)
            pose_hub.update_pose(topic, type_name, value, 10, selected_topic=lambda: POSE_TOPIC,
                                 stamp_ns=lambda _: 1, publisher_count=1, **kwargs)

        values = {"subscription_qos": QOS, "graph": evidence(POSE_TOPIC, POSE_TYPE)["graph"]}
        with patch(MODULE_IMPORT, side_effect=ImportError("Humble")), \
                patch.object(time, "monotonic", return_value=10), \
                patch("robot_dashboard.ros.telemetry.extract_odometry_pose", return_value=PARSED_POSE):
            first = wrap_observation_callback(callback, POSE_TOPIC, POSE_TYPE, lambda: True,
                                              observation_context=lambda: values)
            second = wrap_observation_callback(callback, POSE_TOPIC, POSE_TYPE, lambda: True,
                                               observation_context=lambda: values)
            first(message())
            first_observation = pose_hub.pose["observation"]
            second(message())
        second_observation = pose_hub.pose["observation"]
        self.assertNotEqual(first.subscription_session_id, second.subscription_session_id)
        self.assertEqual(first_observation["subscription_evidence"]["session_id"], first.subscription_session_id)
        self.assertEqual(second_observation["subscription_evidence"]["session_id"], second.subscription_session_id)
        self.assertNotEqual(first_observation["publisher_epoch"], second_observation["publisher_epoch"])
        self.assertIsNone(captured[0]["message_info"])
        self.assertTrue(callable(captured[0]["observation_context"]))
        self.assertEqual(second_observation["identity_status"], "UNAVAILABLE")
        self.assertIsNone(second_observation["publisher_gid"])

    def test_pose_history_pairs_nearest_receipt_only_in_current_subscription_epoch(self):
        _, pose_hub, _ = hubs()
        context = evidence(POSE_TOPIC, POSE_TYPE)
        for i, now in enumerate((10, 10.1, 10.2), 1):
            update_pose(pose_hub, context, now=now, stamp=i * 1000)
        self.assertEqual(len(pose_hub.pose_history), 3)
        cloud = ObservationIdentity().observe(topic=CLOUD_TOPIC, frame="odom", stamp_ns=8, received=10.09,
                                             publisher_count=1, observation_context=evidence())
        paired = pose_hub.observation_pose_near(cloud, 10.25, provenance_mode="subscription_observation")
        self.assertEqual(paired["stamp_ns"], 2000)
        self.assertEqual(paired["observation"]["received_monotonic_s"], 10.1)
        self.assertEqual(paired["observation"]["identity_status"], "UNAVAILABLE")
        self.assertIsNone(pose_hub.observation_pose_near(cloud, 13.1, provenance_mode="subscription_observation"))
        self.assertIsNone(pose_hub.observation_pose_near(cloud, 10.25, provenance_mode="unknown"))
        update_pose(pose_hub, evidence(POSE_TOPIC, POSE_TYPE, session="2"), now=10.3, stamp=4)
        self.assertEqual(len(pose_hub.pose_history), 1)
        paired = pose_hub.observation_pose_near(cloud, 10.35, provenance_mode="subscription_observation")
        self.assertEqual(paired["stamp_ns"], 4)

    def test_session_endpoint_failure_and_graph_staleness_rotate_epoch_and_clear_history(self):
        for change in ("session", "endpoint", "failure", "stale"):
            with self.subTest(change=change):
                _, pose_hub, _ = hubs()
                context = evidence(POSE_TOPIC, POSE_TYPE, at=7.2 if change == "stale" else 10)
                update_pose(pose_hub, context, now=10, stamp=1)
                update_pose(pose_hub, context, now=10.1, stamp=2)
                old_epoch = pose_hub.pose["observation"]["publisher_epoch"]
                self.assertEqual(len(pose_hub.pose_history), 2)
                replacement = copy.deepcopy(context)
                if change == "session":
                    replacement["session_id"] = "2" * 32
                elif change == "endpoint":
                    replacement = evidence(POSE_TOPIC, POSE_TYPE, gid=3)
                elif change == "failure":
                    replacement["graph"].update(state="unavailable", fingerprint=None, reason="GRAPH_REFRESH_FAILED")
                update_pose(pose_hub, replacement, now=10.3, stamp=3)
                observed = pose_hub.pose["observation"]
                self.assertNotEqual(old_epoch, observed["publisher_epoch"])
                self.assertEqual(observed["reset_reason"], "SOURCE_CHANGED")
                self.assertEqual(len(pose_hub.pose_history), 1)
                self.assertEqual(observed["identity_status"], "UNAVAILABLE")
                if change in {"failure", "stale"}:
                    self.assertIsNone(subscription_evidence_key(observed, 10.3))

    def test_changed_cloud_with_empty_replacement_cannot_leave_previous_points(self):
        _, _, cloud_hub = hubs()
        self.assertTrue(update_cloud(cloud_hub, evidence()))
        old_epoch = cloud_hub.cloud["observation"]["publisher_epoch"]
        with patch("robot_dashboard.ros.pointcloud.extract_xyz", return_value=(np.empty((0, 3)), 0)):
            self.assertFalse(cloud_hub.process(CLOUD_TOPIC, message(), 10.2, selected_topic=lambda: CLOUD_TOPIC,
                                              stamp_ns=lambda _: 2, robot_pose_in_frame=lambda _: None,
                                              publisher_count=1, observation_context=evidence(gid=3)))
        self.assertNotEqual(old_epoch, cloud_hub.cloud["observation"]["publisher_epoch"])
        self.assertTrue(cloud_hub.cloud["observation"]["invalidated"])
        self.assertEqual(cloud_hub.cloud["points_bytes"], b"")

    def test_expired_context_drops_both_hubs_before_extraction(self):
        _, pose_hub, cloud_hub = hubs()
        with patch("robot_dashboard.ros.telemetry.extract_odometry_pose") as pose_extract, \
                patch("robot_dashboard.ros.pointcloud.extract_xyz") as cloud_extract:
            pose_hub.update_pose(POSE_TOPIC, POSE_TYPE, message(), 10, selected_topic=lambda: POSE_TOPIC,
                                 stamp_ns=lambda _: 1, publisher_count=1, observation_context=lambda: None)
            self.assertFalse(cloud_hub.process(CLOUD_TOPIC, message(), 10, selected_topic=lambda: CLOUD_TOPIC,
                                              stamp_ns=lambda _: 1, robot_pose_in_frame=lambda _: None,
                                              publisher_count=1, observation_context=lambda: None))
        pose_extract.assert_not_called()
        cloud_extract.assert_not_called()
        self.assertEqual(len(pose_hub.pose_history), 0)
        self.assertEqual(cloud_hub.cloud["seq"], 0)

    def test_newer_graph_than_callback_receipt_drops_one_sample_without_epoch_reset(self):
        _, pose_hub, cloud_hub = hubs()
        update_pose(pose_hub, evidence(POSE_TOPIC, POSE_TYPE), stamp=1)
        update_cloud(cloud_hub, evidence(), stamp=1)
        pose_epoch = pose_hub.pose_identity.epoch
        cloud_epoch = cloud_hub.observation_identity.epoch
        with patch("robot_dashboard.ros.telemetry.extract_odometry_pose") as pose_extract, \
                patch("robot_dashboard.ros.pointcloud.extract_xyz") as cloud_extract:
            pose_hub.update_pose(POSE_TOPIC, POSE_TYPE, message(), 10.01, selected_topic=lambda: POSE_TOPIC,
                                 stamp_ns=lambda _: 2, publisher_count=1,
                                 observation_context=lambda: evidence(POSE_TOPIC, POSE_TYPE, at=10.02))
            self.assertFalse(cloud_hub.process(CLOUD_TOPIC, message(), 10.01, selected_topic=lambda: CLOUD_TOPIC,
                                              stamp_ns=lambda _: 2, robot_pose_in_frame=lambda _: None,
                                              publisher_count=1, observation_context=lambda: evidence(at=10.02)))
        pose_extract.assert_not_called()
        cloud_extract.assert_not_called()
        self.assertEqual(pose_hub.pose_identity.epoch, pose_epoch)
        self.assertEqual(cloud_hub.observation_identity.epoch, cloud_epoch)
        self.assertEqual(len(pose_hub.pose_history), 1)
        self.assertEqual(pose_hub.pose["stamp_ns"], 1)
        self.assertEqual(cloud_hub.cloud["stamp_ns"], 1)
        update_pose(pose_hub, evidence(POSE_TOPIC, POSE_TYPE, at=10.02), now=10.2, stamp=3)
        self.assertTrue(update_cloud(cloud_hub, evidence(at=10.02), now=10.2, stamp=3))
        self.assertEqual(pose_hub.pose_identity.epoch, pose_epoch)
        self.assertEqual(cloud_hub.observation_identity.epoch, cloud_epoch)
        self.assertEqual(len(pose_hub.pose_history), 2)
        self.assertEqual(pose_hub.pose["observation"]["received_monotonic_s"], 10.2)
        self.assertEqual(cloud_hub.cloud["observation"]["received_monotonic_s"], 10.2)

    def test_missing_graph_does_not_stop_native_display_updates_or_create_fallback_evidence(self):
        _, pose_hub, cloud_hub = hubs()
        for now in (10, 10.2):
            pose_context = evidence(POSE_TOPIC, POSE_TYPE, at=now + .001)
            cloud_context = evidence(at=now + .001)
            for context in (pose_context, cloud_context):
                context["graph"].update(state="unavailable", fingerprint=None, reason="GRAPH_REFRESH_FAILED")
            update_pose(pose_hub, lambda: pose_context, now=now, stamp=1 if now == 10 else 2)
            self.assertTrue(update_cloud(cloud_hub, lambda: cloud_context, now=now, stamp=1 if now == 10 else 2))
        self.assertEqual(pose_hub.pose["stamp_ns"], 2)
        self.assertEqual(cloud_hub.cloud["stamp_ns"], 2)
        for observed in (pose_hub.pose["observation"], cloud_hub.cloud["observation"]):
            self.assertEqual(observed["identity_status"], "UNAVAILABLE")
            self.assertIsNone(observed["publisher_gid"])
            self.assertIsNone(subscription_evidence_key(observed, 10.2))

    def test_graph_or_subscription_reset_during_extraction_fences_old_commits(self):
        _, pose_hub, cloud_hub = hubs()

        def reset_pose(*args, **kwargs):
            with pose_hub._lock:
                pose_hub.reset_pose(POSE_TOPIC, POSE_TYPE)
            return PARSED_POSE

        def reset_cloud(*args, **kwargs):
            with cloud_hub._lock:
                cloud_hub.reset(CLOUD_TOPIC)
            return POINTS, len(POINTS)

        with patch("robot_dashboard.ros.telemetry.extract_odometry_pose", side_effect=reset_pose), \
                patch("robot_dashboard.ros.pointcloud.extract_xyz", side_effect=reset_cloud):
            pose_hub.update_pose(POSE_TOPIC, POSE_TYPE, message(), 10, selected_topic=lambda: POSE_TOPIC,
                                 stamp_ns=lambda _: 1, publisher_count=1,
                                 observation_context=evidence(POSE_TOPIC, POSE_TYPE))
            self.assertFalse(cloud_hub.process(CLOUD_TOPIC, message(), 10, selected_topic=lambda: CLOUD_TOPIC,
                                              stamp_ns=lambda _: 1, robot_pose_in_frame=lambda _: None,
                                              publisher_count=1, observation_context=evidence()))
        self.assertEqual(len(pose_hub.pose_history), 0)
        self.assertIsNone(pose_hub.pose["pose"])
        self.assertEqual(cloud_hub.cloud["points_bytes"], b"")


class SubscriptionAgentTests(unittest.TestCase):
    def test_creation_uses_actual_qos_and_recreation_fences_old_wrapper(self):
        value = agent()
        value._node.create_subscription.return_value.qos_profile = {**QOS, "reliability": "RELIABLE", "depth": 5}
        with patch(MODULE_IMPORT, side_effect=ImportError("Humble")), \
                patch.object(time, "monotonic", return_value=10), \
                patch("robot_dashboard.ros.pointcloud.extract_xyz", return_value=(POINTS, len(POINTS))):
            self.assertTrue(value._create_subscription("special:pointcloud", CLOUD_TOPIC, value._pointcloud_callback))
            old_callback = value._node.create_subscription.call_args.args[2]
            old_callback(message())
            first = value._pointcloud_hub.cloud["observation"]
            self.assertEqual(first["subscription_evidence"]["subscription_qos"]["depth"], 5)
            self.assertEqual(first["identity_status"], "UNAVAILABLE")
            value._destroy_subscription("special:pointcloud")
            self.assertTrue(value._create_subscription("special:pointcloud", CLOUD_TOPIC, value._pointcloud_callback))
            new_callback = value._node.create_subscription.call_args.args[2]
            before = value._pointcloud_hub.cloud["seq"]
            old_callback(message())
            self.assertEqual(value._pointcloud_hub.cloud["seq"], before)
            new_callback(message())
        current = value._pointcloud_hub.cloud["observation"]
        self.assertNotEqual(old_callback.subscription_session_id, new_callback.subscription_session_id)
        self.assertNotEqual(first["publisher_epoch"], current["publisher_epoch"])
        self.assertEqual(current["subscription_evidence"]["session_id"], new_callback.subscription_session_id)
        self.assertIsNone(current["publisher_gid"])

    def test_pending_or_destroyed_creation_cannot_attach_context_or_store_native_handle(self):
        value = agent()
        update_cloud(value._pointcloud_hub, evidence())
        handle = SimpleNamespace(qos_profile=QOS.copy())

        def creating(_type, _topic, callback, _qos):
            self.assertEqual(value._pointcloud_hub.cloud["points_bytes"], b"")
            token = value._observation_callbacks["special:pointcloud"]
            self.assertIsNone(value._observation_context_snapshot("special:pointcloud", token))
            callback(message())
            self.assertEqual(value._pointcloud_hub.cloud["points_bytes"], b"")
            value._destroy_subscription("special:pointcloud")
            return handle

        value._node.create_subscription.side_effect = creating
        with patch(MODULE_IMPORT, side_effect=ImportError("Humble")):
            self.assertFalse(value._create_subscription("special:pointcloud", CLOUD_TOPIC, value._pointcloud_callback))
        self.assertNotIn("special:pointcloud", value._subscriptions)
        self.assertNotIn("special:pointcloud", value._observation_callbacks)
        self.assertNotIn("special:pointcloud", value._observation_subscription_contexts)
        value._node.destroy_subscription.assert_called_once_with(handle)

    def test_failed_creation_invalidates_previous_cache_and_removes_pending_context(self):
        value = agent()
        update_cloud(value._pointcloud_hub, evidence())
        value._node.create_subscription.side_effect = RuntimeError("native create failed")
        with patch(MODULE_IMPORT, side_effect=ImportError("Humble")):
            self.assertFalse(value._create_subscription("special:pointcloud", CLOUD_TOPIC, value._pointcloud_callback))
        self.assertEqual(value._pointcloud_hub.cloud["points_bytes"], b"")
        self.assertEqual(value._observation_callbacks, {})
        self.assertEqual(value._observation_subscription_contexts, {})
        self.assertIn("native create failed", value._last_error)

    def test_destroy_after_wrapper_dispatch_cannot_resolve_new_sessions_context(self):
        value = agent()
        actual_process = value._pointcloud_hub.process
        queued = Mock(return_value=False)
        with patch(MODULE_IMPORT, side_effect=ImportError("Humble")), \
                patch.object(time, "monotonic", return_value=10):
            self.assertTrue(value._create_subscription("special:pointcloud", CLOUD_TOPIC, value._pointcloud_callback))
            old_callback = value._node.create_subscription.call_args.args[2]
            value._pointcloud_hub.process = queued
            old_callback(message())
            self.assertEqual(queued.call_count, 1)
            value._pointcloud_hub.process = actual_process
            value._destroy_subscription("special:pointcloud")
            self.assertTrue(value._create_subscription("special:pointcloud", CLOUD_TOPIC, value._pointcloud_callback))
            current_epoch = value._pointcloud_hub.observation_identity.epoch
            self.assertFalse(actual_process(*queued.call_args.args, **queued.call_args.kwargs))
        self.assertEqual(value._pointcloud_hub.observation_identity.epoch, current_epoch)
        self.assertEqual(value._pointcloud_hub.cloud["points_bytes"], b"")

    def test_graph_refresh_and_failure_reset_cached_observations_before_next_message(self):
        value = agent()
        update_pose(value._telemetry_hub, evidence(POSE_TOPIC, POSE_TYPE))
        update_cloud(value._pointcloud_hub, evidence())
        pose_epoch = value._telemetry_hub.pose_identity.epoch
        cloud_epoch = value._pointcloud_hub.observation_identity.epoch
        snapshots = copy.deepcopy(value._observation_graph_snapshots)
        snapshots[CLOUD_TOPIC] = evidence(gid=4)["graph"]
        with value._lock:
            value._replace_observation_graph_locked(snapshots)
        self.assertNotEqual(value._pointcloud_hub.observation_identity.epoch, cloud_epoch)
        self.assertEqual(value._pointcloud_hub.cloud["points_bytes"], b"")
        self.assertEqual(value._telemetry_hub.pose_identity.epoch, pose_epoch)
        unchanged = copy.deepcopy(value._observation_graph_snapshots)
        unchanged[POSE_TOPIC]["observed_monotonic_s"] = 10.2
        with value._lock:
            value._replace_observation_graph_locked(unchanged)
        self.assertEqual(value._telemetry_hub.pose_identity.epoch, pose_epoch)
        self.assertEqual(len(value._telemetry_hub.pose_history), 1)
        value._graph_monitor = SimpleNamespace(discover=Mock(side_effect=RuntimeError("graph failed")))
        value._refresh_graph()
        self.assertNotEqual(value._telemetry_hub.pose_identity.epoch, pose_epoch)
        self.assertEqual(len(value._telemetry_hub.pose_history), 0)
        self.assertIsNone(value._telemetry_hub.pose["pose"])
        for graph in value._observation_graph_snapshots.values():
            self.assertEqual(graph["state"], "unavailable")
            self.assertEqual(graph["reason"], "GRAPH_REFRESH_FAILED")

    def test_endpoint_query_failure_is_unavailable_while_other_native_endpoint_is_recorded(self):
        value = agent()
        odom = endpoint(POSE_TYPE, bare=True)
        native_odom = SimpleNamespace(**{key: val for key, val in odom.items() if key != "qos"},
                                     qos_profile=QOS.copy())
        value._node.get_publishers_info_by_topic = Mock(side_effect=[RuntimeError("not available"), [native_odom]])
        with patch.object(time, "monotonic", return_value=10):
            value._refresh_observation_graph(value._node, value._graph)
        self.assertEqual(value._observation_graph_snapshots[CLOUD_TOPIC]["reason"], "GRAPH_ENDPOINT_QUERY_FAILED")
        self.assertEqual(value._observation_graph_snapshots[POSE_TOPIC]["state"], "ok")
        self.assertEqual(value._observation_graph_snapshots[POSE_TOPIC]["endpoints"][0]["node_namespace"],
                         "_CREATED_BY_BARE_DDS_APP_")

    def test_pose_context_and_pairing_mode_are_forwarded_by_production_agent_methods(self):
        value = agent()
        with patch(MODULE_IMPORT, side_effect=ImportError("Humble")), \
                patch.object(time, "monotonic", return_value=10), \
                patch("robot_dashboard.ros.telemetry.extract_odometry_pose", return_value=PARSED_POSE):
            self.assertTrue(value._create_subscription("observe:odom", POSE_TOPIC, value._summary_callback))
            callback = value._node.create_subscription.call_args.args[2]
            callback(message())
        observed = value._telemetry_hub.pose["observation"]
        self.assertEqual(observed["subscription_evidence"]["topic"], POSE_TOPIC)
        self.assertEqual(observed["identity_status"], "UNAVAILABLE")
        value._telemetry_hub.observation_pose_near = Mock(return_value={"paired": True})
        value.observation_pose_near(observed, provenance_mode="subscription_observation")
        self.assertEqual(value._telemetry_hub.observation_pose_near.call_args.kwargs,
                         {"provenance_mode": "subscription_observation"})


if __name__ == "__main__":
    unittest.main()
