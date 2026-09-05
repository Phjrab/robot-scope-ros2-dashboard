import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_c4c_signed_motion_observation.py"
SPEC = importlib.util.spec_from_file_location("c4c_signed_observation", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class C4CSignedMotionObservationTests(unittest.TestCase):
    release = "a" * 40

    def snapshot(self, *, sequence=20, stamp_ns=2_000_000_001, x=1.0, **bridge_changes):
        request_evidence = {
            "schema": "robot-scope.sport-request-evidence.v1",
            "scope": "bridge_process",
            "published_count": 0,
            "stop_count": 0,
            "move_count": 0,
            "zero_move_count": 0,
            "nonzero_move_count": 0,
            "malformed_move_count": 0,
            "action_count": 0,
            "other_count": 0,
            "last_api_id": None,
            "last_publish_age_ms": None,
            "motion_run_id": 0,
            "motion_run_active": False,
            "motion_run_nonzero_move_count": 0,
        }
        observation = {
            "schema": "robot-scope.motion-observation",
            "schema_version": 1,
            "source_id": module.SOURCE_ID,
            "producer_generation": "e" * 32,
            "release_commit": self.release,
            "source_sequence": sequence,
            "source_stamp_ns": stamp_ns,
            "coordinate_space": "unitree_go.sport_mode_state.local",
            "frame_id": None,
            "origin": "vendor_local_origin_unverified",
            "orientation_xyzw": None,
            "quality": "READY",
            "invalid_reason": "",
            "origin_reset_detected": False,
            "callback_receive_age_ms": 10,
            "receiver_status_age_ms": 20,
            "position_xyz": [x, 2.0, 0.0],
        }
        bridge = {
            "bridge_role": "motion_observer",
            "authenticated": True,
            "observation_connected": True,
            "ready": False,
            "connected": False,
            "available": False,
            "release_commit": self.release,
            "expected_bare_sport_publishers": 10,
            "own_sport_publishers": 0,
            "foreign_named_sport_publishers": 0,
            "bare_unitree_sport_publishers": 10,
            "total_sport_publishers": 10,
            "lowstate_publishers": 1,
            "accepted_command": {
                "deadman": False,
                "linear_x": 0.0,
                "linear_y": 0.0,
                "angular_z": 0.0,
            },
            "request_evidence": request_evidence,
            "motion_observation": observation,
        }
        bridge.update(bridge_changes)
        return {
            "control": {
                "available": False,
                "lease": {"active": False, "token": None},
                "command": {
                    "deadman": False,
                    "linear_x": 0.0,
                    "linear_y": 0.0,
                    "angular_z": 0.0,
                },
                "bridge": bridge,
            }
        }

    def test_validates_isolated_signed_observation(self):
        sample = module.validate_snapshot(
            self.snapshot(), expected_release=self.release
        )
        self.assertEqual(sample.sequence, 20)
        self.assertEqual(sample.position, (1.0, 2.0, 0.0))

    def test_rejects_control_readiness_commands_and_request_evidence(self):
        cases = (
            {"ready": True},
            {"own_sport_publishers": 1},
            {
                "accepted_command": {
                    "deadman": True,
                    "linear_x": 0.03,
                    "linear_y": 0.0,
                    "angular_z": 0.0,
                }
            },
        )
        for changes in cases:
            with (
                self.subTest(changes=changes),
                self.assertRaises(module.SignedObservationError),
            ):
                module.validate_snapshot(
                    self.snapshot(**changes), expected_release=self.release
                )
        payload = self.snapshot()
        payload["control"]["bridge"]["request_evidence"].update(
            published_count=1, stop_count=1, last_api_id=1003
        )
        with self.assertRaises(module.SignedObservationError):
            module.validate_snapshot(payload, expected_release=self.release)

    def test_run_rejects_generation_regression_and_mode_displacement(self):
        run = module.ObservationRun(expected_release=self.release, mode="stationary")
        run.add(self.snapshot())
        run.add(self.snapshot(sequence=21, stamp_ns=2_010_000_001, x=1.001))
        result = run.result(duration_s=1.0)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["motion_command_created"])

        with self.assertRaises(module.SignedObservationError):
            run.add(self.snapshot(sequence=22, stamp_ns=2_020_000_001, x=1.006))

        regressed = module.ObservationRun(expected_release=self.release, mode="dynamic")
        regressed.add(self.snapshot())
        with self.assertRaises(module.SignedObservationError):
            regressed.add(self.snapshot(sequence=19, stamp_ns=1_900_000_001))

    def test_dynamic_run_requires_five_millimetres_of_significant_displacement(self):
        no_motion = module.ObservationRun(
            expected_release=self.release,
            mode="dynamic",
        )
        no_motion.add(self.snapshot())
        no_motion.add(
            self.snapshot(sequence=21, stamp_ns=2_010_000_001, x=1.0002)
        )
        with self.assertRaisesRegex(
            module.SignedObservationError,
            "did not reach significant displacement",
        ):
            no_motion.result(duration_s=20.0)

        significant = module.ObservationRun(
            expected_release=self.release,
            mode="dynamic",
        )
        significant.add(self.snapshot())
        significant.add(
            self.snapshot(sequence=21, stamp_ns=2_010_000_001, x=1.006)
        )
        self.assertEqual(significant.result(duration_s=20.0)["status"], "PASS")

    def test_default_invocation_is_hardware_free_dry_run(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "NOT_RUN")
        self.assertFalse(payload["creates_ros_endpoints"])
        self.assertFalse(payload["creates_motion_commands"])

    def test_checker_contains_no_ros_or_motion_endpoint(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "rclpy",
            "create_publisher",
            "create_subscription",
            "/api/sport/request",
            "ControlManager",
            "deadman=True",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
