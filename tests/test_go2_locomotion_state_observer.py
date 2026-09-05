from __future__ import annotations

import importlib.util
import io
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from array import array
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "observe_go2_locomotion_state.py"
SPEC = importlib.util.spec_from_file_location("go2_locomotion_observer", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
observer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = observer
SPEC.loader.exec_module(observer)


def message(
    mode=0,
    gait_type=0,
    error_code=100,
    velocity=(0.0, 0.0, 0.0),
    position=(0.0, 0.0, 0.0),
):
    return SimpleNamespace(
        mode=mode,
        gait_type=gait_type,
        error_code=error_code,
        velocity=velocity,
        position=position,
    )


class Go2LocomotionObserverTests(unittest.TestCase):
    def test_default_is_hardware_free_dry_run_with_fixed_plan(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["dry_run"])
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["mode"], "S0")
        self.assertEqual(payload["topic"], "/sportmodestate")
        self.assertEqual(payload["duration_s"], 10.0)
        self.assertFalse(payload["creates_publishers"])
        self.assertFalse(payload["creates_control_requests"])
        self.assertFalse(payload["writes_evidence"])

    def test_cli_rejects_free_topic_duration_output_and_host(self):
        parser = observer.build_parser()
        for arguments in (
            ["--topic", "/arbitrary"],
            ["--mode", "OTHER"],
            ["--duration", "1"],
            ["--output", "/tmp/result.json"],
            ["--host", "example.invalid"],
        ):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                parser.parse_args(arguments)

    def test_three_modes_have_fixed_bounded_durations(self):
        self.assertEqual(
            observer.MODE_DURATIONS_S,
            {"S0": 10.0, "S1": 10.0, "STOCK-1": 20.0},
        )
        self.assertEqual(
            observer.ALLOWLISTED_TOPICS,
            ("/sportmodestate", "/lf/sportmodestate"),
        )
        with self.assertRaises(observer.ObservationError):
            observer.observation_plan("S0", "/arbitrary")
        with self.assertRaises(observer.ObservationError):
            observer.observation_plan("OTHER", "/sportmodestate")
        self.assertEqual(
            observer.observation_plan("S1", "/sportmodestate")["duration_s"],
            10.0,
        )

    def test_ready_marker_requires_fixed_topic_and_bounded_publisher_count(self):
        marker = observer.readiness_marker("STOCK-1", "/sportmodestate", 1)
        self.assertEqual(marker["status"], "OBSERVER_READY")
        self.assertTrue(marker["valid_first_sample"])
        self.assertTrue(marker["read_only"])
        self.assertFalse(marker["creates_publishers"])
        self.assertFalse(marker["creates_control_requests"])
        for count in (0, observer.MAX_PUBLISHER_COUNT + 1, True):
            with self.subTest(count=count), self.assertRaises(
                observer.ObservationError
            ):
                observer.readiness_marker("STOCK-1", "/sportmodestate", count)

    def test_accumulator_reports_transition_and_velocity_noise(self):
        accumulator = observer.ObservationAccumulator()
        self.assertTrue(
            accumulator.add(
                message(
                    velocity=(0.01, -0.02, 0.03),
                    position=(1.0, 2.0, 3.0),
                ),
                0.0,
            )
        )
        self.assertTrue(
            accumulator.add(
                message(
                    mode=3,
                    gait_type=1,
                    velocity=(0.03, 0.0, -0.01),
                    position=(1.02, 1.99, 3.0),
                ),
                0.1,
            )
        )
        evidence = accumulator.evidence()
        self.assertEqual(evidence["sample_count"], 2)
        self.assertEqual(evidence["transition_count"], 1)
        self.assertEqual(
            evidence["transitions"][0]["from"], {"mode": 0, "gait_type": 0}
        )
        self.assertEqual(
            evidence["transitions"][0]["to"], {"mode": 3, "gait_type": 1}
        )
        self.assertEqual(
            evidence["first_mode_or_gait_transition"], evidence["transitions"][0]
        )
        self.assertEqual(evidence["first_mode_transition_elapsed_s"], 0.1)
        self.assertEqual(evidence["first_gait_transition_elapsed_s"], 0.1)
        self.assertEqual(
            evidence["first_body_velocity_over_noise"],
            {
                "elapsed_s": 0.0,
                "speed_mps": 0.037417,
                "velocity_mps": [0.01, -0.02, 0.03],
            },
        )
        self.assertEqual(evidence["max_intersample_gap_s"], 0.1)
        self.assertEqual(
            evidence["velocity_noise"]["axis_max_abs_mps"], [0.03, 0.02, 0.03]
        )
        self.assertGreater(evidence["velocity_noise"]["max_vector_speed_mps"], 0)
        self.assertEqual(evidence["position_noise"]["axis_span_m"], [0.02, 0.01, 0.0])
        self.assertEqual(
            evidence["position_noise"]["first_to_last_delta_m"],
            [0.02, -0.01, 0.0],
        )

    def test_raw_sample_and_transition_evidence_are_bounded(self):
        accumulator = observer.ObservationAccumulator()
        count = observer.MAX_RETAINED_SAMPLES + observer.MAX_RETAINED_TRANSITIONS + 5
        for index in range(count):
            accumulator.add(message(mode=index % 2, gait_type=index % 2), index * 0.01)
        evidence = accumulator.evidence()
        self.assertEqual(evidence["sample_count"], count)
        self.assertEqual(
            evidence["retained_sample_count"], observer.MAX_RETAINED_SAMPLES
        )
        self.assertEqual(
            evidence["retained_transition_count"],
            observer.MAX_RETAINED_TRANSITIONS,
        )
        self.assertGreater(evidence["transition_count"], len(evidence["transitions"]))

    def test_invalid_sample_is_counted_but_not_retained(self):
        accumulator = observer.ObservationAccumulator()
        self.assertFalse(
            accumulator.add(message(velocity=(float("nan"), 0.0, 0.0)), 0.0)
        )
        self.assertFalse(accumulator.add(message(mode=256), 0.1))
        self.assertFalse(accumulator.add(message(mode=1.5), 0.2))
        self.assertFalse(
            accumulator.add(message(position=(float("nan"), 0.0, 0.0)), 0.3)
        )
        evidence = accumulator.evidence()
        self.assertEqual(evidence["sample_count"], 0)
        self.assertEqual(evidence["rejected_count"], 4)
        self.assertIsNone(evidence["first_sample"])

    def test_ros_fixed_numeric_arrays_are_accepted_without_sequence_contract(self):
        sample = observer.validate_sample(
            message(
                velocity=array("f", [0.01, -0.02, 0.03]),
                position=array("d", [1.0, 2.0, 3.0]),
            ),
            0.0,
        )
        self.assertAlmostEqual(sample.velocity[0], 0.01, places=6)
        self.assertEqual(sample.position, (1.0, 2.0, 3.0))
        with self.assertRaises(observer.ObservationError):
            observer.validate_sample(message(velocity="000"), 0.0)

    def test_non_monotonic_elapsed_time_is_rejected(self):
        accumulator = observer.ObservationAccumulator()
        self.assertTrue(accumulator.add(message(), 0.2))
        self.assertFalse(accumulator.add(message(), 0.1))
        self.assertEqual(accumulator.sample_count, 1)
        self.assertEqual(accumulator.rejected_count, 1)

    def test_velocity_threshold_and_first_transitions_are_kept_online(self):
        accumulator = observer.ObservationAccumulator()
        accumulator.add(message(velocity=(0.006, 0.0, 0.0)), 0.0)
        accumulator.add(message(mode=1, velocity=(0.008, 0.008, 0.0)), 0.1)
        accumulator.add(message(mode=1, gait_type=2, velocity=(0.2, 0.0, 0.0)), 0.2)
        accumulator.add(message(mode=3, gait_type=3), 0.3)
        evidence = accumulator.evidence()
        self.assertEqual(evidence["first_mode_transition_elapsed_s"], 0.1)
        self.assertEqual(evidence["first_gait_transition_elapsed_s"], 0.2)
        self.assertEqual(
            evidence["first_mode_or_gait_transition"]["elapsed_s"], 0.1
        )
        self.assertEqual(
            evidence["first_body_velocity_over_noise"]["elapsed_s"], 0.1
        )
        self.assertEqual(
            evidence["body_velocity_over_noise_threshold_mps"], 0.01
        )

    @staticmethod
    def passing_evidence():
        return {
            "sample_count": 100,
            "rejected_count": 0,
            "observed_rate_hz": 10.0,
            "first_sample": {"elapsed_s": 0.0},
            "max_intersample_gap_s": 0.1,
            "final_sample_age_s": 0.05,
        }

    def test_evidence_assessment_passes_complete_stable_observation(self):
        result = observer.assess_evidence(
            mode="S1",
            actual_duration_s=10.0,
            evidence=self.passing_evidence(),
            publisher_counts=[1, 1, 1],
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["failure_reasons"], [])
        self.assertEqual(result["publisher_counts_seen"], [1, 1, 1])

    def test_evidence_assessment_reports_every_quality_gate(self):
        evidence = {
            "sample_count": observer.MIN_SAMPLE_COUNT - 1,
            "rejected_count": 2,
            "observed_rate_hz": observer.MIN_OBSERVED_RATE_HZ - 0.1,
            "first_sample": {
                "elapsed_s": observer.MAX_INITIAL_SAMPLE_AGE_S + 0.1
            },
            "max_intersample_gap_s": observer.MAX_INTERSAMPLE_GAP_S + 0.1,
            "final_sample_age_s": observer.MAX_FINAL_SAMPLE_AGE_S + 0.1,
        }
        result = observer.assess_evidence(
            mode="S0",
            actual_duration_s=(
                observer.MODE_DURATIONS_S["S0"]
                - observer.DURATION_COMPLETION_TOLERANCE_S
                - 0.01
            ),
            evidence=evidence,
            publisher_counts=[0, observer.MAX_PUBLISHER_COUNT + 1],
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(
            set(result["failure_reasons"]),
            {
                "OBSERVATION_DURATION_INCOMPLETE",
                "SAMPLE_COUNT_TOO_LOW",
                "SAMPLE_RATE_TOO_LOW",
                "INVALID_SAMPLE_REJECTED",
                "INTERSAMPLE_GAP_TOO_LARGE",
                "INITIAL_SAMPLE_LATE",
                "FINAL_SAMPLE_STALE",
                "PUBLISHER_COUNT_ZERO",
                "PUBLISHER_COUNT_TOO_HIGH",
                "PUBLISHER_COUNT_CHANGED",
            },
        )

    def test_evidence_assessment_fails_missing_timing_or_publishers(self):
        evidence = self.passing_evidence()
        evidence["first_sample"] = None
        evidence["max_intersample_gap_s"] = None
        evidence["final_sample_age_s"] = None
        result = observer.assess_evidence(
            mode="STOCK-1",
            actual_duration_s=20.0,
            evidence=evidence,
            publisher_counts=[],
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("INTERSAMPLE_GAP_TOO_LARGE", result["failure_reasons"])
        self.assertIn("INITIAL_SAMPLE_LATE", result["failure_reasons"])
        self.assertIn("FINAL_SAMPLE_STALE", result["failure_reasons"])
        self.assertIn("PUBLISHER_COUNT_ZERO", result["failure_reasons"])

    def test_live_main_returns_nonzero_for_invalid_written_evidence(self):
        failed_payload = {
            "mode": "S1",
            "status": "FAIL",
            "failure_reasons": ["SAMPLE_RATE_TOO_LOW"],
            "evidence": {"sample_count": 1},
        }
        with mock.patch.object(
            observer,
            "observe",
            return_value=(failed_payload, Path("/fixed/private/evidence.json")),
        ), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(observer.main(["--mode", "S1", "--observe"]), 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "FAIL")

    def test_live_main_returns_zero_only_for_passing_evidence(self):
        passed_payload = {
            "mode": "S0",
            "status": "PASS",
            "failure_reasons": [],
            "evidence": {"sample_count": 100},
        }
        with mock.patch.object(
            observer,
            "observe",
            return_value=(passed_payload, Path("/fixed/private/evidence.json")),
        ), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(observer.main(["--observe"]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "PASS")

    def test_private_json_is_exclusive_and_mode_0600(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            observer._write_private_json(path, {"safe": True})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"safe": True})
            with self.assertRaises(FileExistsError):
                observer._write_private_json(path, {"replace": False})

    def test_source_has_subscription_only_and_lazy_ros_imports(self):
        source = SCRIPT.read_text(encoding="utf-8")
        prefix = source.split("def observe(", 1)[0]
        self.assertNotIn("import rclpy", prefix)
        self.assertNotIn("unitree_go", prefix)
        self.assertIn("create_subscription", source)
        self.assertIn("get_publishers_info_by_topic", source)
        self.assertIn("enable_rosout=False", source)
        self.assertIn("start_parameter_services=False", source)
        self.assertIn('"status": "OBSERVER_READY"', source)
        self.assertIn("warmup_message", source)
        self.assertNotIn("create_publisher", source)
        self.assertNotIn("create_client", source)
        self.assertNotIn("/api/sport/request", source)
        self.assertNotIn("/api/v1/control", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("import httpx", source)


if __name__ == "__main__":
    unittest.main()
