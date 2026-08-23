import json
import unittest
from pathlib import Path

from robot_dashboard.localization_health import (
    LOCALIZATION_HEALTH_STATES,
    LocalizationHealthThresholds,
    build_calibration_assistant,
    classify_localization_health,
)
from robot_dashboard.navigation_runtime import BoundedRateWindow, NavigationRuntimeError


def healthy_metrics(**updates):
    values = {
        "cloud_frequency_hz": 10.0,
        "cloud_jitter_s": 0.01,
        "cloud_age_s": 0.1,
        "runtime_health_age_s": 0.1,
        "odometry_frequency_hz": 100.0,
        "odometry_jitter_s": 0.005,
        "odometry_age_s": 0.02,
        "odom_to_base_age_s": 0.02,
        "map_to_odom_age_s": 0.02,
        "accepted_points": 500,
        "fresh_sequence_count": 3,
        "last_jump_age_s": None,
        "controller_stall_duration_s": 0.0,
        "frame_error": "",
        "calibration_suspected": False,
    }
    values.update(updates)
    return values


class LocalizationHealthTests(unittest.TestCase):
    def setUp(self):
        self.thresholds = LocalizationHealthThresholds()

    def classify(self, metrics=None, *, active=True, localized=True):
        return classify_localization_health(
            healthy_metrics(**(metrics or {})),
            active=active,
            localized=localized,
            thresholds=self.thresholds,
        )

    def test_all_seven_states_are_explicit_and_no_confidence_score_exists(self):
        cases = {
            "READY": self.classify(),
            "DEGRADED": self.classify({"cloud_frequency_hz": 1.0}),
            "STALE": self.classify({"cloud_age_s": 2.0}),
            "DISCONTINUITY": self.classify(
                {"last_jump_age_s": 0.1, "last_jump_reason": "odometry heading jumped"}
            ),
            "FRAME_MISMATCH": self.classify({"frame_error": "camera_init->wrong"}),
            "CALIBRATION_SUSPECTED": self.classify(
                {"calibration_suspected": True, "calibration_reason": "EXTRINSIC_MISMATCH"}
            ),
            "UNAVAILABLE": self.classify(active=False),
        }
        self.assertEqual(set(cases), LOCALIZATION_HEALTH_STATES)
        for expected, snapshot in cases.items():
            self.assertEqual(snapshot["state"], expected)
            self.assertTrue(snapshot["reason_code"])
            self.assertTrue(snapshot["threshold_basis"])
            self.assertNotIn("confidence", snapshot)

    def test_ready_requires_a_fresh_advancing_sequence(self):
        warmup = self.classify({"fresh_sequence_count": 2})
        self.assertEqual(warmup["state"], "DEGRADED")
        self.assertEqual(warmup["reason_code"], "FRESH_SEQUENCE_WARMUP")
        self.assertEqual(self.classify()["state"], "READY")

    def test_cached_runtime_health_cannot_remain_ready_after_its_freshness_window(self):
        stale = self.classify({"runtime_health_age_s": 0.76})
        self.assertEqual(stale["state"], "STALE")
        self.assertEqual(stale["reason_code"], "FRESHNESS_THRESHOLD_EXCEEDED")
        self.assertIn("runtime_health_age_s>0.75", stale["threshold_basis"])

    def test_profile_thresholds_are_bounded_and_public(self):
        thresholds = LocalizationHealthThresholds.from_profile(
            {
                "navigation_health": {
                    "cloud_min_hz": 7,
                    "cloud_stale_s": 999,
                    "fresh_sequence_min": 0,
                    "controller_stall_s": "bad",
                }
            }
        )
        self.assertEqual(thresholds.cloud_min_hz, 7.0)
        self.assertEqual(thresholds.cloud_stale_s, 10.0)
        self.assertEqual(thresholds.fresh_sequence_min, 1)
        self.assertEqual(thresholds.controller_stall_s, 3.0)
        self.assertEqual(thresholds.public()["cloud_min_hz"], 7.0)

    def test_initial_pose_is_degraded_not_false_ready(self):
        snapshot = self.classify(localized=False)
        self.assertEqual(snapshot["state"], "DEGRADED")
        self.assertEqual(snapshot["reason_code"], "INITIAL_POSE_REQUIRED")

    def test_go2_profile_declares_every_threshold_and_assistant_is_read_only(self):
        root = Path(__file__).resolve().parents[1]
        profile = json.loads((root / "config" / "go2.json").read_text(encoding="utf-8"))
        configured = profile["navigation_health"]
        self.assertEqual(set(configured), set(self.thresholds.public()))
        health_source = (root / "robot_dashboard" / "localization_health.py").read_text(encoding="utf-8")
        assistant_start = health_source.index("def build_calibration_assistant(")
        assistant_end = health_source.index("\n\n__all__", assistant_start)
        assistant = health_source[assistant_start:assistant_end]
        self.assertIn('"read_only": True', assistant)
        self.assertIn('"writes_configuration": False', assistant)
        for forbidden in ("write_text", "open(", "os.replace", "subprocess", "set_parameters"):
            self.assertNotIn(forbidden, assistant)

        snapshot = build_calibration_assistant(
            {
                "frames": {"cloud": "hesai_lidar", "odometry_parent": "camera_init", "odometry_child": "body"},
                "lidar_extrinsic": {"parent": "base_link", "child": "hesai_lidar", "x": 0.25, "y": 0, "z": 0, "yaw": 0},
                "clock_domains": {"pointcloud": "host_ros_normalized"},
                "publisher_counts": {"/velodyne_points": 1},
            },
            static_tf_publishers=1,
            topic_publishers={"/Odometry": 1, "/robot_scope/nav/runtime_health": 1},
            metrics={"host_clock_offsets_s": {"fast_lio": 0.01, "controller": 100.0}},
            expected_model=profile["robot_pose_in_cloud_frames"]["hesai_lidar"],
        )
        self.assertTrue(snapshot["read_only"])
        self.assertFalse(snapshot["writes_configuration"])
        self.assertEqual(len(snapshot["items"]), 6)
        self.assertEqual(snapshot["source_publishers"]["fast_lio_odometry"], 1)


class BoundedRateWindowTests(unittest.TestCase):
    def test_frequency_jitter_age_and_bound_are_deterministic(self):
        window = BoundedRateWindow(3)
        for observed_at in (1.0, 1.1, 1.2, 1.3):
            window.observe(observed_at)
        snapshot = window.snapshot(1.35)
        self.assertEqual(snapshot["samples"], 3)
        self.assertAlmostEqual(snapshot["frequency_hz"], 10.0)
        self.assertAlmostEqual(snapshot["jitter_s"], 0.0)
        self.assertAlmostEqual(snapshot["age_s"], 0.05)

    def test_invalid_window_and_non_monotonic_arrival_fail_closed(self):
        with self.assertRaises(NavigationRuntimeError):
            BoundedRateWindow(2)
        window = BoundedRateWindow(3)
        window.observe(2.0)
        window.observe(1.0)
        self.assertEqual(window.snapshot(2.1)["samples"], 1)


if __name__ == "__main__":
    unittest.main()
