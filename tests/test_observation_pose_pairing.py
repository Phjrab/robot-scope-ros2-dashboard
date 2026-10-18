"""Exact nearest valid pose pairing with bounded request-local diagnostics."""

import copy
import math
import threading
import unittest
from unittest.mock import patch

from robot_dashboard.relocalization.observation_timing import ObservationTiming
from robot_dashboard.ros.observation_identity import ObservationIdentity, subscription_evidence_key
from test_observation_subscription_evidence import (
    CLOUD_TOPIC, POSE_TOPIC, POSE_TYPE, evidence, hubs, update_pose,
)


EVIDENCE_KEY = "robot_dashboard.ros.telemetry.subscription_evidence_key"


def inputs(times=(10, 10.125, 10.25), *, received=10.125):
    _, hub, _ = hubs()
    for stamp, at in enumerate(times, 1):
        update_pose(hub, evidence(POSE_TOPIC, POSE_TYPE), now=at, stamp=stamp)
    cloud = ObservationIdentity().observe(topic=CLOUD_TOPIC, frame="odom", stamp_ns=1, received=received,
                                         publisher_count=1, observation_context=evidence())
    return hub, cloud


def original_nearest(hub, observation, now):
    epoch = hub.pose["observation"]["publisher_epoch"]
    key = subscription_evidence_key(hub.pose["observation"], now)
    candidates = [p for p in hub.pose_history if p["observation"]["publisher_epoch"] == epoch
                  and p["observation"]["observer_id"] == observation["observer_id"]
                  and subscription_evidence_key(p["observation"], now) == key]
    return min(candidates, key=lambda p: abs(p["updated"] - observation["received_monotonic_s"])) if candidates else None


class NearestValidPoseTests(unittest.TestCase):
    def assert_lock_released(self, hub):
        acquired = []

        def from_another_thread():
            available = hub._lock.acquire(blocking=False)
            acquired.append(available)
            if available:
                hub._lock.release()

        worker = threading.Thread(target=from_another_thread)
        worker.start()
        worker.join(timeout=1)
        self.assertEqual(acquired, [True])

    def test_nearest_valid_candidate_stops_after_one_history_evidence_check(self):
        hub, cloud = inputs(tuple(10 + index / 256 for index in range(160)), received=10.25)
        expected = original_nearest(hub, cloud, 10.75)
        trace = ObservationTiming()
        with trace.bind(), patch(EVIDENCE_KEY, wraps=subscription_evidence_key) as checked:
            result = hub.observation_pose_near(cloud, 10.75, provenance_mode="subscription_observation")
        self.assertEqual(result["stamp_ns"], expected["stamp_ns"])
        self.assertEqual(checked.call_count, 3)  # Current pose, cloud, nearest candidate.
        self.assertEqual(trace.values["pose_history_count"], 160)
        self.assertEqual(trace.values["pose_evidence_checks"], 3)
        self.assertEqual(set(trace.stages), {"pose_lock_wait", "pose_lock_hold"})
        for stage in trace.stages.values():
            self.assertEqual(stage["calls"], 1)
            self.assertGreaterEqual(stage["wall_ms"], 0)
            self.assertGreaterEqual(stage["thread_cpu_ms"], 0)

    def test_invalid_nearest_is_skipped_and_equal_distance_uses_history_order(self):
        for invalid in ("invalidated", "stale", "different_session", "different_endpoint"):
            with self.subTest(invalid=invalid):
                hub, cloud = inputs((10, 10.125, 10.25), received=10.125)
                nearest = hub.pose_history[1]["observation"]
                if invalid == "invalidated":
                    nearest["invalidated"] = True
                elif invalid == "stale":
                    nearest["subscription_evidence"]["graph"]["observed_monotonic_s"] = 1
                elif invalid == "different_session":
                    nearest["subscription_evidence"]["session_id"] = "4" * 32
                else:
                    nearest["subscription_evidence"] = evidence(POSE_TOPIC, POSE_TYPE, gid=4)
                expected = original_nearest(hub, cloud, 10.5)
                with patch(EVIDENCE_KEY, wraps=subscription_evidence_key) as checked:
                    result = hub.observation_pose_near(cloud, 10.5, provenance_mode="subscription_observation")
                self.assertEqual(result["stamp_ns"], 1)
                self.assertEqual(result["stamp_ns"], expected["stamp_ns"])
                self.assertEqual(checked.call_count, 4)

    def test_no_valid_candidate_or_invalid_current_or_cloud_still_returns_none(self):
        for invalid in ("history", "current", "cloud", "mode"):
            with self.subTest(invalid=invalid):
                hub, cloud = inputs()
                mode = "subscription_observation"
                if invalid == "history":
                    hub.pose = copy.deepcopy(hub.pose)
                    for item in hub.pose_history:
                        item["observation"]["invalidated"] = True
                elif invalid == "current":
                    hub.pose["observation"]["invalidated"] = True
                elif invalid == "cloud":
                    cloud["invalidated"] = True
                else:
                    mode = "unknown"
                trace = ObservationTiming()
                with trace.bind():
                    self.assertIsNone(hub.observation_pose_near(cloud, 10.5, provenance_mode=mode))
                self.assertLessEqual(trace.values["pose_evidence_checks"], 5)
                self.assertEqual(set(trace.stages), {"pose_lock_wait", "pose_lock_hold"})
                # Every return path releases the shared lock, including rejection.
                self.assert_lock_released(hub)

    def test_native_mode_nearest_and_tie_behavior_do_not_validate_subscription_evidence(self):
        hub, cloud = inputs((10, 10.25), received=10.125)
        trace = ObservationTiming()
        with trace.bind(), patch(EVIDENCE_KEY, side_effect=AssertionError("native mode must stay unchanged")):
            result = hub.observation_pose_near(cloud, 10.5)
        self.assertEqual(result["stamp_ns"], 1)
        self.assertEqual(trace.values["pose_evidence_checks"], 0)

    def test_nonfinite_distance_preserves_original_filter_then_min_behavior(self):
        for at, received in ((math.nan, 10.125), (10.125, math.nan), (10.125, math.inf)):
            with self.subTest(at=at, received=received):
                hub, cloud = inputs(received=received)
                hub.pose_history[0]["updated"] = at
                expected = original_nearest(hub, cloud, 10.5)
                with patch.object(hub, "_pose_payload", side_effect=lambda item, _: {"stamp_ns": item["stamp_ns"]}):
                    result = hub.observation_pose_near(cloud, 10.5, provenance_mode="subscription_observation")
                self.assertEqual(result["stamp_ns"], expected["stamp_ns"])

    def test_exception_releases_lock_and_records_evidence_checks(self):
        hub, cloud = inputs()
        trace = ObservationTiming()
        with trace.bind(), patch(EVIDENCE_KEY, side_effect=RuntimeError("key failed")):
            with self.assertRaisesRegex(RuntimeError, "key failed"):
                hub.observation_pose_near(cloud, 10.5, provenance_mode="subscription_observation")
        self.assertEqual(trace.values["pose_evidence_checks"], 1)
        self.assertEqual(trace.failed_stage, "pose_lock_hold")
        self.assert_lock_released(hub)


if __name__ == "__main__":
    unittest.main()
