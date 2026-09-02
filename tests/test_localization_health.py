import json
import unittest
from pathlib import Path

from robot_dashboard.localization_health import (
    COMPETITION_FASTLIO_PROFILE,
    LOCALIZATION_HEALTH_STATES,
    LocalizationHealthThresholds,
    LocalizationReadinessStabilizer,
    OdometryRateReadinessPolicy,
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
        "odometry_frequency_hz_raw": 100.0,
        "odometry_max_gap_s": 0.01,
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
        self.assertAlmostEqual(snapshot["frequency_hz_raw"], 10.0)
        self.assertAlmostEqual(snapshot["mean_period_s"], 0.1)
        self.assertAlmostEqual(snapshot["median_period_s"], 0.1)
        self.assertAlmostEqual(snapshot["p95_period_s"], 0.1)
        self.assertAlmostEqual(snapshot["max_gap_s"], 0.1)
        self.assertEqual(snapshot["sample_count"], 3)
        self.assertEqual(snapshot["interval_count"], 2)

    def test_invalid_window_and_non_monotonic_arrival_fail_closed(self):
        with self.assertRaises(NavigationRuntimeError):
            BoundedRateWindow(2)
        window = BoundedRateWindow(3)
        window.observe(2.0)
        window.observe(1.0)
        self.assertEqual(window.snapshot(2.1)["samples"], 1)

    def test_raw_rate_is_distinct_from_display_and_nearest_rank_p95(self):
        window = BoundedRateWindow(5)
        for observed_at in (0.0, 0.10016, 0.20017, 0.30020, 0.40007):
            window.observe(observed_at)
        snapshot = window.snapshot(0.41)
        self.assertNotEqual(
            snapshot["frequency_hz_raw"], snapshot["frequency_hz"]
        )
        self.assertEqual(snapshot["frequency_hz"], 9.998)
        self.assertAlmostEqual(snapshot["mean_period_s"], 0.1000175)
        self.assertAlmostEqual(snapshot["median_period_s"], 0.10002)
        self.assertAlmostEqual(snapshot["p95_period_s"], 0.10016)
        self.assertAlmostEqual(snapshot["max_gap_s"], 0.10016)

    def test_gap_and_window_remain_bounded(self):
        window = BoundedRateWindow(4)
        for observed_at in (1.0, 1.1, 1.2, 1.46, 1.56):
            window.observe(observed_at)
        snapshot = window.snapshot(1.57)
        self.assertEqual(snapshot["sample_count"], 4)
        self.assertEqual(snapshot["interval_count"], 3)
        self.assertAlmostEqual(snapshot["max_gap_s"], 0.26)
        self.assertAlmostEqual(snapshot["window_duration_s"], 0.46)


class LocalizationReadinessStabilizerTests(unittest.TestCase):
    def setUp(self):
        self.thresholds = LocalizationHealthThresholds()
        self.policy = OdometryRateReadinessPolicy.for_navigation_profile(
            COMPETITION_FASTLIO_PROFILE,
            legacy_min_hz=self.thresholds.odometry_min_hz,
        )
        self.stabilizer = LocalizationReadinessStabilizer(self.policy)
        self.generation = (COMPETITION_FASTLIO_PROFILE, 1, 123)

    def observation(self, rate, *, now, **updates):
        metrics = healthy_metrics(
            odometry_frequency_hz=round(rate, 3),
            odometry_frequency_hz_raw=rate,
            **updates,
        )
        instantaneous = classify_localization_health(
            metrics,
            active=True,
            localized=True,
            thresholds=self.thresholds,
            rate_policy=self.policy,
        )
        return self.stabilizer.update(
            instantaneous,
            metrics,
            now=now,
            generation=self.generation,
        )

    def test_profile_policy_is_fixed_and_legacy_profiles_are_unchanged(self):
        self.assertTrue(self.policy.enabled)
        self.assertEqual(self.policy.nominal_hz, 10.0)
        self.assertEqual(self.policy.ready_enter_hz, 9.5)
        self.assertEqual(self.policy.ready_exit_hz, 9.0)
        self.assertEqual(self.policy.ready_enter_dwell_s, 10.0)
        self.assertEqual(self.policy.ready_exit_dwell_s, 2.0)
        self.assertEqual(self.policy.max_gap_s, 0.25)
        legacy = OdometryRateReadinessPolicy.for_navigation_profile(
            "go2-xt16-wireless",
            legacy_min_hz=10.0,
        )
        self.assertFalse(legacy.enabled)
        self.assertEqual(legacy.ready_enter_hz, 10.0)
        self.assertEqual(legacy.ready_enter_dwell_s, 0.0)
        metrics = healthy_metrics(
            odometry_frequency_hz=10.0,
            odometry_frequency_hz_raw=9.499999,
        )
        legacy_result = classify_localization_health(
            metrics,
            active=True,
            localized=True,
            thresholds=self.thresholds,
            rate_policy=legacy,
        )
        competition_result = classify_localization_health(
            metrics,
            active=True,
            localized=True,
            thresholds=self.thresholds,
            rate_policy=self.policy,
        )
        self.assertEqual(legacy_result["state"], "READY")
        self.assertEqual(competition_result["state"], "DEGRADED")

    def test_ready_requires_ten_second_enter_dwell(self):
        first = self.observation(9.984, now=100.0)
        self.assertEqual(first["state"], "UNAVAILABLE")
        self.assertTrue(first["hard_fault"])
        self.assertEqual(self.observation(9.984, now=100.1)["state"], "DEGRADED")
        at_9_9 = self.observation(9.999, now=110.0)
        self.assertEqual(at_9_9["state"], "DEGRADED")
        self.assertAlmostEqual(at_9_9["enter_candidate_duration_s"], 9.9)
        ready = self.observation(9.997, now=110.1)
        self.assertEqual(ready["state"], "READY")
        self.assertEqual(ready["stable_ready_duration_s"], 10.0)

    def test_hysteresis_exit_and_reentry_dwell(self):
        self.assertEqual(self.observation(9.6, now=0.0)["state"], "UNAVAILABLE")
        self.observation(9.6, now=0.1)
        self.assertEqual(self.observation(9.6, now=10.1)["state"], "READY")
        band = self.observation(9.49, now=10.6)
        self.assertEqual(band["state"], "READY")
        self.assertEqual(band["rate_band"], "HYSTERESIS")
        pending = self.observation(8.9, now=11.1)
        self.assertEqual(pending["state"], "READY")
        self.assertEqual(pending["exit_candidate_duration_s"], 0.0)
        self.assertEqual(self.observation(8.9, now=12.1)["state"], "READY")
        exited = self.observation(8.9, now=13.1)
        self.assertEqual(exited["state"], "DEGRADED")
        self.assertEqual(exited["reason_code"], "ODOMETRY_RATE_BELOW_EXIT")
        self.assertEqual(self.observation(9.6, now=14.1)["state"], "DEGRADED")
        self.assertEqual(self.observation(9.6, now=24.1)["state"], "READY")

    def test_gap_hard_fault_and_generation_change_reset_ready(self):
        self.observation(9.6, now=0.0)
        self.observation(9.6, now=10.0)
        gap = self.observation(9.6, now=10.1, odometry_max_gap_s=0.26)
        self.assertEqual(gap["state"], "DEGRADED")
        self.assertTrue(gap["hard_fault"])
        self.assertEqual(gap["reason_code"], "ODOMETRY_MAX_GAP_EXCEEDED")
        self.generation = (COMPETITION_FASTLIO_PROFILE, 1, 124)
        reset = self.observation(9.6, now=11.0)
        self.assertEqual(reset["state"], "UNAVAILABLE")
        self.assertTrue(reset["hard_fault"])
        self.assertEqual(reset["rate_band"], "HARD_FAULT")
        self.assertEqual(reset["last_transition_reason"], "GENERATION_CHANGED")
        warming = self.observation(9.6, now=11.1)
        self.assertEqual(warming["state"], "DEGRADED")
        self.assertFalse(warming["hard_fault"])
        self.assertEqual(reset["enter_candidate_duration_s"], 0.0)
        self.assertEqual(warming["last_transition_reason"], "READY_ENTER_DWELL_PENDING")

    def test_stale_and_non_rate_faults_are_immediate(self):
        self.observation(9.6, now=0.0)
        self.observation(9.6, now=10.0)
        stale = self.observation(9.6, now=10.1, odometry_age_s=0.51)
        self.assertEqual(stale["state"], "STALE")
        self.assertTrue(stale["hard_fault"])
        self.assertEqual(stale["stable_ready_duration_s"], 0.0)
        jitter = self.observation(9.6, now=11.0, odometry_jitter_s=0.101)
        self.assertEqual(jitter["state"], "DEGRADED")
        self.assertTrue(jitter["hard_fault"])


if __name__ == "__main__":
    unittest.main()
