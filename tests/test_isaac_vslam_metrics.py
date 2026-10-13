"""Synthetic analysis tests; these provide no CUDA/ROS/camera execution evidence."""
import contextlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.isaac_vslam.metrics.analyze import analyze, distribution, pose_metrics, read_jsonl, stereo_metrics
from experiments.isaac_vslam.metrics.collect import finite_json, parse_args, status_schema_matches


def run_start(**extra):
    return {"event": "run_start", "receipt_monotonic_ns": 0, "run_id": "synthetic-test",
            "evidence_type": "synthetic", "streams": {"left": {}, "right": {}, "odom": {}, "status": {}}, **extra}


def sample(stream, receipt_s, stamp_s=None, **extra):
    result = {"event": "sample", "stream": stream, "receipt_monotonic_ns": int(receipt_s * 1e9), **extra}
    if stamp_s is not None:
        result["stamp_ns"] = int(stamp_s * 1e9)
    return result


def end(at=1., reason="duration_complete"):
    return {"event": "run_end", "receipt_monotonic_ns": int(at * 1e9), "reason": reason}


class IsaacVslamMetricsTests(unittest.TestCase):
    def test_percentiles_are_linear_and_sample_count_explicit(self):
        result = distribution([0, 1, 2, 3, 4])
        self.assertEqual(result["samples"], 5)
        self.assertEqual(result["p50"], 2)
        self.assertAlmostEqual(result["p95"], 3.8)
        self.assertIsNone(distribution([])["p95"])

    def test_missing_stream_never_means_tracking_lost(self):
        result = analyze([run_start(), end()], warmup_seconds=0)
        self.assertEqual(result["streams"]["odom"]["state"], "NOT_OBSERVED")
        self.assertNotIn("tracking", result["streams"]["odom"])
        self.assertEqual(result["streams"]["status"]["tracking"]["state"], "NOT_OBSERVED")
        self.assertEqual(result["accuracy"]["state"], "N/A")

    def test_receipt_and_header_fps_separate(self):
        events = [run_start()] + [sample("left", .1 + i * .1, 10 + i / 30) for i in range(4)] + [end(.4)]
        stream = analyze(events, warmup_seconds=0)["streams"]["left"]
        self.assertAlmostEqual(stream["receipt_monotonic"]["fps_over_observed_span"], 10)
        self.assertAlmostEqual(stream["header_stamp"]["fps_over_observed_span"], 30)
        self.assertEqual(stream["data_age_ms"]["state"], "N/A")

    def test_gaps_duplicates_out_of_order_not_hidden(self):
        events = [run_start()] + [sample("left", (i + 1) / 10, stamp) for i, stamp in enumerate([1, 1, .9, 1.5])] + [end(.4)]
        stats = analyze(events, warmup_seconds=0)["streams"]["left"]["header_stamp"]
        self.assertEqual(stats["duplicate_timestamps"], 1)
        self.assertEqual(stats["out_of_order"], 1)
        self.assertEqual(stats["gaps_above_threshold"], 1)
        self.assertIsNone(stats["fps_over_observed_span"])

    def test_stereo_timestamps_paired_one_to_one_and_not_reused(self):
        left = [sample("left", 0, 1), sample("left", 0, 1.001), sample("left", 0, 2)]
        right = [sample("right", 0, 1.00005), sample("right", 0, 3)]
        stats = stereo_metrics(left, right, 15)
        self.assertEqual(stats["matched_pairs"], 1)
        self.assertEqual(stats["unmatched_left"], 2)
        self.assertAlmostEqual(stats["absolute_difference_ms"]["p50"], .05)

    def test_warmup_excluded_and_window_explicit(self):
        events = [run_start(), sample("left", 1, 100), sample("left", 11, 110), end(12)]
        result = analyze(events, warmup_seconds=10)
        self.assertEqual(result["streams"]["left"]["samples"], 1)
        self.assertEqual(result["measurement"]["duration_seconds"], 2)

    def test_silence_not_explicit_stopped_status(self):
        events = [run_start(), sample("status", .1, 10, tracking_state="TRACKING"), end(2)]
        result = analyze(events, warmup_seconds=0)["streams"]["status"]
        self.assertEqual(result["state"], "NO_RECENT_INPUT")
        self.assertEqual(result["tracking"]["explicit_stopped_samples"], 0)
        self.assertEqual(result["tracking"]["lost_entries"], 0)

    def test_status_loss_recovery_and_unrecovered_interval(self):
        states = ["TRACKING", "LOST", "LOST", "TRACKING", "LOST", "STOPPED"]
        events = [run_start()] + [sample("status", i + 1, tracking_state=state) for i, state in enumerate(states)] + [end(7)]
        result = analyze(events, warmup_seconds=0)["streams"]["status"]["tracking"]
        self.assertEqual(result["lost_entries"], 2)
        self.assertEqual(result["recovery_seconds"]["samples"], 1)
        self.assertEqual(result["recovery_seconds"]["p50"], 2)
        self.assertEqual(result["unrecovered_loss_seconds_at_end"], 2)
        self.assertEqual(result["explicit_stopped_samples"], 1)

    def test_age_requires_evidence_and_same_clock_contract(self):
        events = [run_start(clock_contract={"header_and_receipt_same_ros_clock": True}),
                  sample("left", 1, 100, receipt_ros_ns=100_010_000_000), end(1)]
        self.assertEqual(analyze(events, 0)["streams"]["left"]["data_age_ms"]["state"], "N/A")
        events[0]["clock_contract"]["evidence"] = "synthetic same-domain clocks"
        age = analyze(events, 0)["streams"]["left"]["data_age_ms"]
        self.assertEqual(age["state"], "MEASURED")
        self.assertAlmostEqual(age["distribution"]["p50"], 10)

    def test_backward_clock_jump_invalidates_age(self):
        events = [run_start(clock_contract={"header_and_receipt_same_ros_clock": True, "evidence": "synthetic"}),
                  sample("left", 1, 100, receipt_ros_ns=100_010_000_000),
                  sample("left", 2, 99, receipt_ros_ns=99_010_000_000), end(2)]
        age = analyze(events, 0)["streams"]["left"]["data_age_ms"]
        self.assertEqual(age["state"], "N/A")
        self.assertIn("Backward", age["reason"])

    def test_live_forward_ros_clock_jump_invalidates_age(self):
        events = [run_start(clock_contract={"mode": "live", "header_and_receipt_same_ros_clock": True, "evidence": "synthetic"}),
                  sample("left", 1, 100, receipt_ros_ns=100_010_000_000),
                  sample("left", 2, 110, receipt_ros_ns=110_010_000_000), end(2)]
        self.assertEqual(analyze(events, 0)["streams"]["left"]["data_age_ms"]["state"], "N/A")

    def test_negative_age_and_stalled_ros_clock_invalidated(self):
        header = run_start(clock_contract={"header_and_receipt_same_ros_clock": True, "evidence": "synthetic"})
        events = [header, sample("left", 1, 100, receipt_ros_ns=99_000_000_000), end(1)]
        self.assertEqual(analyze(events, 0)["streams"]["left"]["data_age_ms"]["state"], "N/A")
        events = [header, sample("left", 1, 100, receipt_ros_ns=100_000_000_000),
                  sample("left", 2, 100, receipt_ros_ns=100_000_000_000), end(2)]
        self.assertIn("did not advance", analyze(events, 0)["streams"]["left"]["data_age_ms"]["reason"])

    def test_pose_quaternion_sign_is_same_rotation(self):
        events = [sample("odom", 0, pose={"position": [0, 0, 0], "quaternion_xyzw": [0, 0, 0, 1]}),
                  sample("odom", 1, pose={"position": [.03, .04, 0], "quaternion_xyzw": [0, 0, 0, -1]})]
        result = pose_metrics(events)
        self.assertEqual(result["rotation_from_first_deg"]["max"], 0)
        self.assertAlmostEqual(result["endpoint_displacement_m"], .05)

    def test_pose_angle_and_frame_change(self):
        events = [sample("odom", 0, frame_id="odom_a", pose={"position": [0, 0, 0], "quaternion_xyzw": [0, 0, 0, 1]}),
                  sample("odom", 1, frame_id="odom_a", pose={"position": [1, 0, 0], "quaternion_xyzw": [0, 0, math.sqrt(.5), math.sqrt(.5)]})]
        self.assertAlmostEqual(pose_metrics(events)["rotation_from_first_deg"]["max"], 90)
        events[-1]["frame_id"] = "odom_b"
        self.assertEqual(pose_metrics(events)["state"], "N/A")

    def test_algorithm_callback_duration_distinct_from_receipt_age(self):
        events = [run_start(status_schema_source="synthetic"), sample("status", 1, 100,
                  algorithm_timing_seconds={"node_callback_execution_time": .003, "track_execution_time": .002}), end(1)]
        result = analyze(events, 0)
        self.assertEqual(result["algorithm_processing_time_ms"]["fields"]["node_callback_execution_time_ms"]["p50"], 3)
        self.assertEqual(result["streams"]["status"]["data_age_ms"]["state"], "N/A")

    def test_partial_run_preserved_as_incomplete(self):
        result = analyze([run_start(), sample("left", 1, 1)], 0)
        self.assertEqual(result["collector"]["state"], "INCOMPLETE")

    def test_no_measurement_window_explicit(self):
        result = analyze([run_start(), end(1)], 10)
        self.assertEqual(result["measurement"]["state"], "NO_MEASUREMENT_WINDOW")
        self.assertEqual(result["measurement"]["duration_seconds"], 0)

    def test_nonfinite_json_rejected_and_sensor_values_sanitized(self):
        self.assertEqual(finite_json({"values": [float("nan"), float("inf"), 1]}), {"values": [None, None, 1]})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jsonl"
            path.write_text('{"event":"sample","value":NaN}\n')
            with self.assertRaisesRegex(ValueError, "line 1"):
                read_jsonl(path)
        json.dumps(analyze([run_start(), end()], 0), allow_nan=False)

    def test_nonfinite_options_rejected(self):
        with self.assertRaises(ValueError):
            analyze([run_start(), end()], warmup_seconds=float("nan"))

    def test_collector_requires_explicit_domain_localhost_and_finite_duration(self):
        argv = ["--output", "not-written.jsonl", "--run-id", "x", "--domain", "71", "--duration", "5", "--evidence-type", "synthetic"]
        with patch.dict(os.environ, {"ROS_DOMAIN_ID": "71", "ROS_LOCALHOST_ONLY": "1"}):
            self.assertEqual(parse_args(argv).domain, 71)
        with patch.dict(os.environ, {"ROS_DOMAIN_ID": "0", "ROS_LOCALHOST_ONLY": "1"}), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_args(argv)
        with patch.dict(os.environ, {"ROS_DOMAIN_ID": "71", "ROS_LOCALHOST_ONLY": "0"}), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_args(argv)

    def test_status_semantics_require_exact_release32_schema(self):
        fields = {"header": "std_msgs/Header", "vo_state": "uint8",
                  "node_callback_execution_time": "double", "track_execution_time": "double",
                  "track_execution_time_mean": "double", "track_execution_time_max": "double"}
        self.assertTrue(status_schema_matches(fields))
        self.assertFalse(status_schema_matches({**fields, "new_unknown_field": "string"}))
        self.assertFalse(status_schema_matches({**fields, "vo_state": "string"}))


if __name__ == "__main__":
    unittest.main()
