from __future__ import annotations

import copy
import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_go2_locomotion_micro_probe.py"
SPEC = importlib.util.spec_from_file_location("go2_locomotion_micro_probe", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)
RELEASE = "a" * 40
DEFAULT_ARM_RESPONSE = object()


def snapshots() -> dict:
    request = {
        "schema": "robot-scope.sport-request-evidence.v1",
        "published_count": 10,
        "stop_count": 10,
        "move_count": 0,
        "zero_move_count": 0,
        "nonzero_move_count": 0,
        "malformed_move_count": 0,
        "action_count": 0,
        "other_count": 0,
        "last_api_id": probe.API_STOP_MOVE,
        "last_publish_age_ms": 1,
        "max_abs_linear_x": 0.0,
        "max_abs_linear_y": 0.0,
        "max_abs_angular_z": 0.0,
        "motion_run_id": 4,
        "motion_run_active": False,
        "motion_run_nonzero_move_count": 0,
        "motion_run_max_abs_linear_x": 0.0,
        "motion_run_max_abs_linear_y": 0.0,
        "motion_run_max_abs_angular_z": 0.0,
    }
    zero = {
        "deadman": False,
        "linear_x": 0.0,
        "linear_y": 0.0,
        "angular_z": 0.0,
    }
    bridge = {
        "motion_observation_generation_verified": True,
        "release_commit": RELEASE,
        "ready": True,
        "authenticated": True,
        "connected": True,
        "available": True,
        "status_age_s": 0.01,
        "lowstate_age_ms": 1.0,
        "lowstate_publishers": 1,
        "sport_subscribers": 1,
        "own_sport_publishers": 1,
        "foreign_named_sport_publishers": 0,
        "bare_unitree_sport_publishers": 10,
        "expected_bare_sport_publishers": 10,
        "total_sport_publishers": 11,
        "telemetry": {
            "battery": {"battery_soc": 46},
            "joints": {"seq": 100},
        },
        "accepted_command": dict(zero),
        "command_ack": {
            "source_matches_dashboard": True,
            "seq": 2,
            "type": "stop",
            "age_ms": 1,
        },
        "request_evidence": request,
        "sport_mode_state": {
            "topic": "/sportmodestate",
            "fresh": True,
            "mode": 0,
            "gait_type": 0,
            "velocity": [0.0, 0.0, 0.0],
            "error_code": 100,
            "age_ms": 1,
        },
        "motion_observation": {
            "schema": probe.MOTION_OBSERVATION_SCHEMA,
            "schema_version": 1,
            "source_id": probe.MOTION_OBSERVATION_SOURCE,
            "producer_generation": "e" * 32,
            "release_commit": RELEASE,
            "source_sequence": 10,
            "source_stamp_ns": 1_000_000_000,
            "source_clock_domain": "unitree_go.timespec.unverified",
            "source_age_ms": None,
            "sample_progression": "source_stamp_strict_increase",
            "callback_receive_age_ms": 1,
            "last_callback_gap_ms": 10,
            "max_callback_gap_ms": 12,
            "callback_clock_domain": "bridge_process.monotonic",
            "stale_after_ms": 500,
            "coordinate_space": "unitree_go.sport_mode_state.local",
            "frame_id": None,
            "origin": "vendor_local_origin_unverified",
            "position_xyz": [0.0, 0.0, 0.0],
            "orientation_xyzw": None,
            "quality": "READY",
            "invalid_reason": "",
            "origin_reset_detected": False,
            "accepted_sample_count": 10,
            "duplicate_sample_count": 0,
            "rejected_sample_count": 0,
            "receiver_status_age_ms": 10.0,
            "receiver_clock_domain": "dashboard_process.monotonic",
        },
    }
    return {
        "health": {
            "runtime_profile": {"id": "go2"},
            "target_matches_startup": True,
        },
        "pose": {
            "state": "ok",
            "topic": "/Odometry",
            "seq": 10,
            "age_s": 0.01,
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        },
        "control": {
            "control": {
                "enabled": True,
                "configured": True,
                "available": True,
                "estop_latched": False,
                "lease": {"active": False},
                "action_guard": {"active": False},
                "command": {"source": None, **zero},
                "limits": {"max_linear_x": 0.30},
                "bridge": bridge,
            }
        },
        "navigation": {
            "pipeline": {"state": "idle"},
            "session_mode": "idle",
            "goal": {"state": "idle"},
            "localization_session": {"active": False},
            "bindings": {"navigation_profile": probe.EXPECTED_PROFILE},
        },
        "competition": {"operation_mode": "MANUAL"},
        "missions": {"active_mission_id": None},
        "mapping": {
            "pipeline": {"state": "idle"},
            "operation": {"state": "idle"},
        },
    }


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.now += max(0.0, duration)


class LateClock(FakeClock):
    def __init__(self) -> None:
        super().__init__()
        self.late_injected = False

    def sleep(self, duration: float) -> None:
        late_by = 0.0
        if duration > 0.0 and not self.late_injected:
            late_by = (2 * probe.FRAME_LATE_TOLERANCE_S) + 0.001
            self.late_injected = True
        self.now += max(0.0, duration) + late_by


class FakeStream:
    def __init__(self, adapter: "FakeAdapter", *, release_error: bool = False) -> None:
        self.adapter = adapter
        self.release_error = release_error
        self.payloads: list[dict] = []
        self.bound = False
        self.closed = False

    def bind(self, lease_id: str, *, client_time_ms: float) -> None:
        del client_time_ms
        if lease_id != self.adapter.lease_id:
            raise AssertionError("wrong lease")
        self.bound = True

    def send_twist(self, payload: dict) -> None:
        if not self.bound:
            raise AssertionError("unbound stream")
        value = dict(payload)
        self.payloads.append(value)
        if value["deadman"] is False and self.adapter.zero_error:
            raise RuntimeError("simulated explicit zero failure")
        control = self.adapter.state["control"]["control"]
        bridge = control["bridge"]
        request = bridge["request_evidence"]
        bridge["telemetry"]["joints"]["seq"] += 1
        deadman = value["deadman"]
        target_x = value["linear_x"] * control["limits"]["max_linear_x"]
        accepted_x = target_x * self.adapter.output_scale if deadman else 0.0
        command = {
            "deadman": deadman,
            "linear_x": accepted_x,
            "linear_y": 0.0,
            "angular_z": 0.0,
        }
        control["command"] = {
            "source": "keyboard",
            **command,
            "linear_x": target_x if deadman else 0.0,
        }
        bridge["accepted_command"] = dict(command)
        if self.adapter.ack_fault != "nonadvancing":
            self.adapter.bridge_ack_seq += 1
        bridge["command_ack"] = {
            "source_matches_dashboard": self.adapter.ack_fault != "source_mismatch",
            "seq": self.adapter.bridge_ack_seq,
            "type": (
                "stop"
                if deadman and self.adapter.ack_fault == "type_mismatch"
                else "drive"
                if deadman
                else "stop"
            ),
            "age_ms": 751 if self.adapter.ack_fault == "stale" else 0,
        }
        request["published_count"] += 1
        if deadman and accepted_x > 0.0:
            if not request["motion_run_active"]:
                request["motion_run_id"] += 1
            request["move_count"] += 1
            request["nonzero_move_count"] += 1
            request["motion_run_active"] = True
            request["motion_run_nonzero_move_count"] += 1
            request["motion_run_max_abs_linear_x"] = max(
                request["motion_run_max_abs_linear_x"], accepted_x
            )
            request["max_abs_linear_x"] = max(
                request["max_abs_linear_x"], accepted_x
            )
            request["last_api_id"] = probe.API_MOVE
        else:
            request["stop_count"] += 1
            request["motion_run_active"] = False
            request["last_api_id"] = probe.API_STOP_MOVE

    def release(self, lease_id: str, *, client_time_ms: float) -> bool:
        del client_time_ms
        if self.release_error:
            raise RuntimeError("simulated release race")
        if lease_id != self.adapter.lease_id:
            return False
        self.adapter.apply_stop()
        return True

    def close(self) -> None:
        self.closed = True


class FakeAdapter:
    def __init__(
        self,
        *,
        release_error: bool = False,
        zero_error: bool = False,
        disarm_error: bool = False,
        software_stop_error: bool = False,
        arm_response: object = DEFAULT_ARM_RESPONSE,
        ack_fault: str | None = None,
        output_scale: float = 1.0,
        cleanup_fault: str | None = None,
        advance_lowstate: bool = True,
    ) -> None:
        self.state = snapshots()
        self.lease_id = "fixed-lease-token-0001"
        self.arm_response = (
            self.lease_id if arm_response is DEFAULT_ARM_RESPONSE else arm_response
        )
        self.zero_error = zero_error
        self.disarm_error = disarm_error
        self.software_stop_error = software_stop_error
        self.ack_fault = ack_fault
        self.output_scale = output_scale
        self.cleanup_fault = cleanup_fault
        self.advance_lowstate = advance_lowstate
        self.bridge_ack_seq = self.state["control"]["control"]["bridge"][
            "command_ack"
        ]["seq"]
        self.stream = FakeStream(self, release_error=release_error)
        self.arm_count = 0
        self.disarm_count = 0
        self.stop_count = 0

    def snapshots(self) -> dict:
        if self.advance_lowstate:
            self.state["control"]["control"]["bridge"]["telemetry"]["joints"][
                "seq"
            ] += 1
            observation = self.state["control"]["control"]["bridge"][
                "motion_observation"
            ]
            observation["source_sequence"] += 1
            observation["accepted_sample_count"] += 1
            observation["source_stamp_ns"] += 10_000_000
        return copy.deepcopy(self.state)

    def arm(self) -> object:
        self.arm_count += 1
        self.state["control"]["control"]["lease"] = {
            "active": True,
            "source": "keyboard",
        }
        return self.arm_response

    def open_stream(self) -> FakeStream:
        return self.stream

    def disarm(self, lease_id: str) -> None:
        if lease_id != self.lease_id:
            raise AssertionError("wrong lease")
        self.disarm_count += 1
        if self.disarm_error:
            raise RuntimeError("simulated HTTP disarm failure")
        self.apply_stop()

    def software_stop(self) -> None:
        self.stop_count += 1
        if self.software_stop_error:
            raise RuntimeError("simulated software STOP failure")
        self.apply_stop()

    def apply_stop(self) -> None:
        control = self.state["control"]["control"]
        bridge = control["bridge"]
        request = bridge["request_evidence"]
        zero = {
            "deadman": False,
            "linear_x": 0.0,
            "linear_y": 0.0,
            "angular_z": 0.0,
        }
        control["lease"] = {"active": False, "source": None}
        control["command"] = {"source": "keyboard", **zero}
        bridge["accepted_command"] = dict(zero)
        self.bridge_ack_seq += 1
        bridge["command_ack"] = {
            "source_matches_dashboard": True,
            "seq": self.bridge_ack_seq,
            "type": "stop",
            "age_ms": 0,
        }
        request["published_count"] += 1
        request["stop_count"] += 1
        request["motion_run_active"] = False
        request["last_api_id"] = probe.API_STOP_MOVE
        if self.cleanup_fault == "readiness":
            bridge.update(
                ready=False,
                authenticated=False,
                connected=False,
                available=False,
            )
        elif self.cleanup_fault == "status":
            bridge["status_age_s"] = 0.751
        elif self.cleanup_fault == "lowstate":
            bridge["lowstate_age_ms"] = 500.1
        elif self.cleanup_fault == "cardinality":
            bridge["foreign_named_sport_publishers"] = 1
        elif self.cleanup_fault == "connected":
            bridge["connected"] = False
        elif self.cleanup_fault == "available":
            bridge["available"] = False
        elif self.cleanup_fault == "navigation":
            self.state["navigation"]["pipeline"]["state"] = "running"


class Go2LocomotionMicroProbeTests(unittest.TestCase):
    def test_bounded_report_always_retains_final_cleanup_evidence(self):
        samples = [
            {"phase": "runtime", "index": index}
            for index in range(probe.MAX_SAMPLES + 8)
        ]
        samples.append({"phase": "cleanup", "final_exact_zero": True})

        retained = probe._bounded_report_samples(samples)

        self.assertEqual(len(retained), probe.MAX_SAMPLES)
        self.assertEqual(retained[-1], samples[-1])
        self.assertEqual(retained[0], samples[0])

    def test_default_is_hardware_free_and_every_probe_is_bounded(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        path = Path(summary["result_file"])
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "DRY_RUN")
            self.assertFalse(payload["network_access"])
            self.assertEqual(payload["mutation_count"], 0)
            self.assertEqual(
                [item["probe_id"] for item in payload["probes"]],
                ["MP-030", "MP-050", "MP-080", "MP-100"],
            )
            self.assertLessEqual(
                max(item["predicted_max_travel_m"] for item in payload["probes"]),
                0.10,
            )
            self.assertFalse(payload["safety"]["automatic_retry"])
            self.assertFalse(payload["safety"]["automatic_escalation"])
        finally:
            path.unlink(missing_ok=True)

    def test_live_probe_requires_all_confirmations_and_one_fixed_choice(self):
        parser = probe.build_parser()
        args = parser.parse_args(["--execute-mp-030"])
        with self.assertRaises(SystemExit):
            probe.selected_probe(args, parser)
        with self.assertRaises(SystemExit):
            parser.parse_args(["--execute-mp-030", "--execute-mp-050"])

        flags = ["--" + value.replace("_", "-") for value in probe.CONFIRMATION_FLAGS]
        args = parser.parse_args([
            "--execute-mp-030", *flags,
            "--observation-source", probe.MOTION_OBSERVATION_SOURCE,
        ])
        self.assertIs(probe.selected_probe(args, parser), probe.PROBES["MP-030"])
        self.assertTrue(probe.MOTION_USE_APPROVED)
        self.assertEqual(probe.APPROVED_PROBE_IDS, frozenset({"MP-030"}))

        for option in ("--execute-mp-050", "--execute-mp-080", "--execute-mp-100"):
            with self.subTest(option=option):
                args = parser.parse_args([
                    option,
                    *flags,
                    "--observation-source",
                    probe.MOTION_OBSERVATION_SOURCE,
                ])
                with self.assertRaises(SystemExit):
                    probe.selected_probe(args, parser)

    def test_preflight_accepts_only_idle_authoritative_bridge_state(self):
        result = probe.validate_preflight(snapshots(), expected_release=RELEASE)
        self.assertEqual(result["motion_run_id"], 4)
        self.assertEqual(result["mode"], 0)
        self.assertEqual(result["gait_type"], 0)
        self.assertEqual(result["error_code"], 100)

    def test_legacy_waiting_pose_remains_blocked_but_is_not_silently_redefined(self):
        waiting = probe._pose_sample(
            {"state": "waiting", "topic": "", "seq": 0, "age_s": None}
        )
        with self.assertRaisesRegex(probe.ProbeError, "fresh odometry pose"):
            probe._validate_pose_travel(
                waiting,
                baseline_pose=waiting,
                maximum_m=probe.MAX_PRECOMMAND_DRIFT_M,
            )
        value = snapshots()
        value["pose"] = {"state": "waiting", "topic": "", "seq": 0, "age_s": None}
        result = probe.validate_preflight(value, expected_release=RELEASE)
        self.assertEqual(result["legacy_pose"]["state"], "waiting")
        self.assertEqual(
            result["motion_observation"]["source_id"],
            probe.MOTION_OBSERVATION_SOURCE,
        )

    def test_preflight_accepts_old_idle_ack_but_runtime_requires_fresh_drive_ack(self):
        value = snapshots()
        value["control"]["control"]["bridge"]["command_ack"]["age_ms"] = (
            2_147_483_647
        )
        result = probe.validate_preflight(value, expected_release=RELEASE)
        self.assertEqual(result["ack_seq"], 2)

    def test_preflight_rejects_every_critical_boundary_change(self):
        mutations = (
            lambda value: value["control"]["control"]["lease"].update(active=True),
            lambda value: value["control"]["control"]["command"].update(
                deadman=True, linear_x=0.01
            ),
            lambda value: value["control"]["control"]["bridge"].pop(
                "accepted_command"
            ),
            lambda value: value["control"]["control"]["bridge"].update(
                lowstate_age_ms=500.1
            ),
            lambda value: value["control"]["control"]["bridge"].update(
                foreign_named_sport_publishers=1
            ),
            lambda value: value["control"]["control"]["bridge"].update(
                release_commit="b" * 40
            ),
            lambda value: value["navigation"]["pipeline"].update(state="running"),
            lambda value: value["mapping"]["pipeline"].update(state="running"),
            lambda value: value["competition"].update(operation_mode="AUTO"),
        )
        for mutate in mutations:
            value = snapshots()
            mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(probe.ProbeError):
                probe.validate_preflight(value, expected_release=RELEASE)

    def test_motion_observation_faults_block_before_lease_or_drive(self):
        def motion(value):
            return value["control"]["control"]["bridge"]["motion_observation"]

        mutations = (
            lambda value: motion(value).update(source_id="other"),
            lambda value: motion(value).update(frame_id="odom"),
            lambda value: motion(value).update(
                quality="STALE",
                invalid_reason="callback_receive_stale",
                callback_receive_age_ms=501,
            ),
            lambda value: motion(value).update(source_stamp_ns=-1_000_000_000),
            lambda value: motion(value).update(source_sequence=9),
            lambda value: (
                motion(value).update(producer_generation="n" * 32),
                value["control"]["control"]["bridge"].update(
                    motion_observation_generation_verified=False
                ),
            ),
            lambda value: value["control"]["control"]["bridge"].pop(
                "motion_observation_generation_verified"
            ),
            lambda value: motion(value).update(
                quality="INVALID", invalid_reason="source_stamp_duplicate"
            ),
            lambda value: motion(value).update(receiver_status_age_ms=751),
            lambda value: motion(value).update(position_xyz=[float("nan"), 0.0, 0.0]),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                adapter = FakeAdapter()
                mutate(adapter.state)
                with self.assertRaises(probe.ProbeError):
                    probe.ProbeSupervisor(
                        adapter,
                        release_provider=lambda: RELEASE,
                    ).run(probe.PROBES["MP-030"])
                self.assertEqual(adapter.arm_count, 0)
                self.assertEqual(adapter.stream.payloads, [])
                self.assertEqual(adapter.disarm_count, 0)

    def test_planar_travel_includes_lateral_and_preserves_max_after_return(self):
        value = snapshots()
        baseline = probe.validate_preflight(value, expected_release=RELEASE)
        value["control"]["control"]["lease"] = {
            "active": True,
            "source": "keyboard",
        }
        observation = value["control"]["control"]["bridge"]["motion_observation"]
        observation["source_sequence"] += 1
        observation["accepted_sample_count"] += 1
        observation["source_stamp_ns"] += 10_000_000
        observation["position_xyz"][1] = 0.08
        first = probe.safe_sample(value, elapsed_s=0.1)
        cursor = probe.validate_runtime_sample(
            first,
            spec=probe.PROBES["MP-100"],
            baseline=baseline,
            require_motion_evidence=False,
            previous=probe._baseline_cursor(baseline),
            require_ack_advance=False,
        )
        self.assertEqual(first["observed_travel_m"], 0.08)
        self.assertEqual(cursor.max_observed_travel_m, 0.08)

        observation["source_sequence"] += 1
        observation["accepted_sample_count"] += 1
        observation["source_stamp_ns"] += 10_000_000
        observation["position_xyz"][1] = 0.0
        returned = probe.safe_sample(value, elapsed_s=0.2)
        cursor = probe.validate_runtime_sample(
            returned,
            spec=probe.PROBES["MP-100"],
            baseline=baseline,
            require_motion_evidence=False,
            previous=cursor,
            require_ack_advance=False,
        )
        self.assertEqual(returned["observed_travel_m"], 0.0)
        self.assertEqual(returned["max_observed_travel_m"], 0.08)
        self.assertEqual(cursor.max_observed_travel_m, 0.08)

    def test_motion_travel_boundaries_remain_five_mm_and_ten_cm(self):
        baseline = {
            "source_id": probe.MOTION_OBSERVATION_SOURCE,
            "producer_generation": "e" * 32,
            "release_commit": RELEASE,
            "coordinate_space": "unitree_go.sport_mode_state.local",
            "origin": "vendor_local_origin_unverified",
            "source_sequence": 1,
            "source_stamp_ns": 1,
            "position_xyz": [0.0, 0.0, 0.0],
        }
        for bound in (probe.MAX_PRECOMMAND_DRIFT_M, probe.MAX_OBSERVED_TRAVEL_M):
            at_bound = {
                **baseline,
                "source_sequence": 2,
                "source_stamp_ns": 2,
                "position_xyz": [bound, 0.0, 0.0],
            }
            self.assertEqual(
                probe._validate_observed_travel(
                    at_bound,
                    baseline_observation=baseline,
                    maximum_m=bound,
                ),
                bound,
            )
            above = {**at_bound, "position_xyz": [bound + 0.000001, 0.0, 0.0]}
            with self.assertRaisesRegex(probe.ProbeError, "observed travel exceeded"):
                probe._validate_observed_travel(
                    above,
                    baseline_observation=baseline,
                    maximum_m=bound,
                )

    def test_active_preexisting_motion_run_blocks_arm(self):
        adapter = FakeAdapter()
        evidence = adapter.state["control"]["control"]["bridge"][
            "request_evidence"
        ]
        evidence.update(
            motion_run_active=True,
            last_api_id=probe.API_MOVE,
            motion_run_nonzero_move_count=1,
            motion_run_max_abs_linear_x=0.03,
        )
        with self.assertRaisesRegex(probe.ProbeError, "motion run is not idle"):
            probe.ProbeSupervisor(
                adapter,
                release_provider=lambda: RELEASE,
            ).run(probe.PROBES["MP-030"])
        self.assertEqual(adapter.arm_count, 0)
        self.assertEqual(adapter.stream.payloads, [])

    def test_supervisor_uses_one_probe_and_cleans_up_exactly_zero(self):
        adapter = FakeAdapter()
        clock = FakeClock()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["status_scope"], "SIGNED_COMMAND_PATH_ONLY")
        self.assertEqual(result["locomotion_acceptance"], "NOT_EVALUATED")
        self.assertEqual(result["physical_motion"], "OPERATOR_CONFIRMATION_REQUIRED")
        self.assertEqual(adapter.arm_count, 1)
        self.assertEqual(adapter.disarm_count, 0)
        drives = [item for item in adapter.stream.payloads if item["deadman"]]
        self.assertEqual(len(drives), 14)
        self.assertTrue(all(item["speed_scale"] == 1.0 for item in drives))
        self.assertTrue(
            all(item["linear_x"] == 0.03 / 0.30 for item in drives)
        )
        self.assertFalse(adapter.stream.payloads[-1]["deadman"])
        self.assertEqual(adapter.stream.payloads[-1]["linear_x"], 0.0)
        self.assertTrue(adapter.stream.closed)
        self.assertEqual(result["predicted_max_travel_m"], 0.0285)
        final = result["samples"][-1]
        self.assertEqual(final["sport_mode_state"]["mode"], 0)
        self.assertEqual(final["sport_mode_state"]["gait_type"], 0)
        self.assertEqual(final["request"]["move_count"], 14)
        self.assertEqual(final["request"]["nonzero_move_count"], 14)
        self.assertGreater(final["request"]["stop_count"], 10)

    def test_post_arm_race_is_rechecked_before_any_nonzero_frame(self):
        class PostArmRaceAdapter(FakeAdapter):
            def arm(self) -> object:
                lease = super().arm()
                self.state["navigation"]["pipeline"]["state"] = "running"
                return lease

        adapter = PostArmRaceAdapter()
        clock = FakeClock()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("Navigation or localization is active", result["error"])
        self.assertEqual(
            [item for item in adapter.stream.payloads if item["deadman"]], []
        )
        self.assertFalse(result["cleanup"]["final_exact_zero_confirmed"])
        self.assertTrue(result["cleanup"]["software_stop_attempted"])

    def test_post_arm_pose_drift_above_five_mm_blocks_without_drive(self):
        class PostArmDriftAdapter(FakeAdapter):
            def arm(self) -> object:
                lease = super().arm()
                self.state["control"]["control"]["bridge"]["motion_observation"][
                    "position_xyz"
                ][0] = 0.0051
                return lease

        adapter = PostArmDriftAdapter()
        clock = FakeClock()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("observed travel exceeded", result["error"])
        self.assertEqual(
            [item for item in adapter.stream.payloads if item["deadman"]], []
        )
        self.assertTrue(result["cleanup"]["final_exact_zero_confirmed"])

    def test_post_arm_requires_advancing_lowstate_before_first_drive(self):
        adapter = FakeAdapter(advance_lowstate=False)
        clock = FakeClock()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("joint sequence did not advance", result["error"])
        self.assertEqual(
            [item for item in adapter.stream.payloads if item["deadman"]], []
        )
        self.assertTrue(result["cleanup"]["final_exact_zero_confirmed"])

    def test_every_followup_frame_requires_current_consistent_bridge_evidence(self):
        def inactive(request, _sample):
            request["motion_run_active"] = False
            request["last_api_id"] = probe.API_STOP_MOVE

        def interleaved_stop(request, _sample):
            request["published_count"] += 1
            request["stop_count"] += 1

        def regressed_counter(request, _sample):
            request["move_count"] = 0

        def regressed_lowstate(_request, sample):
            sample["control"]["control"]["bridge"]["telemetry"]["joints"][
                "seq"
            ] = 0

        cases = (
            (inactive, "drive acceptance is unconfirmed"),
            (interleaved_stop, "drive acceptance is unconfirmed"),
            (regressed_counter, "request counters regressed"),
            (regressed_lowstate, "joint sequence regressed"),
        )

        for mutation, expected in cases:
            with self.subTest(mutation=mutation.__name__):
                class RuntimeFaultAdapter(FakeAdapter):
                    active_reads = 0

                    def snapshots(self) -> dict:
                        result = super().snapshots()
                        lease_active = self.state["control"]["control"]["lease"][
                            "active"
                        ]
                        has_drive = any(
                            item["deadman"] for item in self.stream.payloads
                        )
                        if lease_active and has_drive:
                            self.active_reads += 1
                            if self.active_reads == 2:
                                request = result["control"]["control"]["bridge"][
                                    "request_evidence"
                                ]
                                mutation(request, result)
                        return result

                adapter = RuntimeFaultAdapter()
                clock = FakeClock()
                result = probe.ProbeSupervisor(
                    adapter,
                    release_provider=lambda: RELEASE,
                    monotonic=clock.monotonic,
                    wall_ms=lambda: clock.now * 1000.0,
                    sleep=clock.sleep,
                ).run(probe.PROBES["MP-030"])
                self.assertEqual(result["status"], "FAIL")
                self.assertIn(expected, result["error"])
                self.assertEqual(
                    len(
                        [
                            item
                            for item in adapter.stream.payloads
                            if item["deadman"]
                        ]
                    ),
                    1,
                )
                self.assertTrue(result["cleanup"]["final_exact_zero_confirmed"])

    def test_mode_and_gait_transitions_are_recorded_without_inference(self):
        class TransitionAdapter(FakeAdapter):
            active_reads = 0

            def snapshots(self) -> dict:
                result = super().snapshots()
                lease_active = self.state["control"]["control"]["lease"]["active"]
                has_drive = any(item["deadman"] for item in self.stream.payloads)
                if lease_active and has_drive:
                    self.active_reads += 1
                    if self.active_reads == 2:
                        result["control"]["control"]["bridge"][
                            "sport_mode_state"
                        ].update(
                            mode=3,
                            gait_type=1,
                            velocity=[0.02, 0.0, 0.0],
                        )
                return result

        adapter = TransitionAdapter()
        clock = FakeClock()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "PASS", result)
        transitions = [
            sample["sport_mode_state"]
            for sample in result["samples"]
            if sample.get("sport_mode_state", {}).get("mode") == 3
        ]
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0]["gait_type"], 1)
        self.assertEqual(transitions[0]["error_code"], 100)

    def test_error_evidence_change_aborts_before_another_drive_frame(self):
        class ErrorTransitionAdapter(FakeAdapter):
            active_reads = 0

            def snapshots(self) -> dict:
                result = super().snapshots()
                lease_active = self.state["control"]["control"]["lease"]["active"]
                has_drive = any(item["deadman"] for item in self.stream.payloads)
                if lease_active and has_drive:
                    self.active_reads += 1
                    if self.active_reads == 2:
                        result["control"]["control"]["bridge"][
                            "sport_mode_state"
                        ]["error_code"] = 101
                return result

        adapter = ErrorTransitionAdapter()
        clock = FakeClock()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("error evidence changed", result["error"])
        self.assertEqual(
            len([item for item in adapter.stream.payloads if item["deadman"]]),
            1,
        )
        self.assertTrue(result["cleanup"]["final_exact_zero_confirmed"])

    def test_first_signed_acceptance_waits_bounded_without_more_drive_frames(self):
        class DelayedStatusAdapter(FakeAdapter):
            def __init__(self, delayed_reads: int) -> None:
                super().__init__()
                self.delayed_reads = delayed_reads
                self.pending_reads = 0
                self.max_drive_frames_before_acceptance = 0
                self.stale_bridge = copy.deepcopy(
                    self.state["control"]["control"]["bridge"]
                )

            def snapshots(self) -> dict:
                result = super().snapshots()
                lease_active = self.state["control"]["control"]["lease"]["active"]
                drive_count = len(
                    [item for item in self.stream.payloads if item["deadman"]]
                )
                if lease_active and drive_count and self.pending_reads < self.delayed_reads:
                    self.pending_reads += 1
                    self.max_drive_frames_before_acceptance = max(
                        self.max_drive_frames_before_acceptance, drive_count
                    )
                    current_bridge = result["control"]["control"]["bridge"]
                    stale_bridge = copy.deepcopy(self.stale_bridge)
                    stale_bridge["telemetry"] = copy.deepcopy(
                        current_bridge["telemetry"]
                    )
                    stale_bridge["motion_observation"] = copy.deepcopy(
                        current_bridge["motion_observation"]
                    )
                    result["control"]["control"]["bridge"] = stale_bridge
                return result

        clock = FakeClock()
        adapter = DelayedStatusAdapter(delayed_reads=4)
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(adapter.max_drive_frames_before_acceptance, 1)
        drive_count = len(
            [item for item in adapter.stream.payloads if item["deadman"]]
        )
        self.assertGreater(drive_count, 1)
        self.assertLessEqual(drive_count, 14)

        clock = FakeClock()
        adapter = DelayedStatusAdapter(delayed_reads=100)
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("first signed Bridge drive acceptance timed out", result["error"])
        self.assertEqual(
            len([item for item in adapter.stream.payloads if item["deadman"]]),
            1,
        )
        self.assertTrue(result["cleanup"]["final_exact_zero_confirmed"])

    def test_late_successful_first_snapshot_cannot_bypass_acceptance_deadline(self):
        clock = FakeClock()

        class SlowAcceptedAdapter(FakeAdapter):
            delayed = False

            def snapshots(self) -> dict:
                result = super().snapshots()
                lease_active = self.state["control"]["control"]["lease"]["active"]
                has_drive = any(item["deadman"] for item in self.stream.payloads)
                if lease_active and has_drive and not self.delayed:
                    clock.now += probe.FIRST_ACCEPTANCE_TIMEOUT_S + 0.001
                    self.delayed = True
                return result

        adapter = SlowAcceptedAdapter()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("first signed Bridge drive acceptance timed out", result["error"])
        self.assertEqual(
            len([item for item in adapter.stream.payloads if item["deadman"]]),
            1,
        )
        self.assertTrue(adapter.stream.closed)
        self.assertTrue(result["cleanup"]["final_exact_zero_confirmed"])

    def test_operator_cancel_after_first_frame_is_fail_closed(self):
        class CancelAdapter(FakeAdapter):
            canceled = False

            def snapshots(self) -> dict:
                lease_active = self.state["control"]["control"]["lease"]["active"]
                has_drive = any(item["deadman"] for item in self.stream.payloads)
                if lease_active and has_drive and not self.canceled:
                    self.canceled = True
                    raise KeyboardInterrupt
                return super().snapshots()

        adapter = CancelAdapter()
        clock = FakeClock()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["error"], "KeyboardInterrupt")
        self.assertEqual(
            len([item for item in adapter.stream.payloads if item["deadman"]]),
            1,
        )
        self.assertFalse(adapter.stream.payloads[-1]["deadman"])
        self.assertTrue(adapter.stream.closed)
        self.assertTrue(result["cleanup"]["websocket_release_acknowledged"])
        self.assertTrue(result["cleanup"]["final_exact_zero_confirmed"])

    def test_observed_travel_bound_aborts_after_the_first_frame(self):
        adapter = FakeAdapter()
        original_send = adapter.stream.send_twist

        def send_and_move(payload: dict) -> None:
            original_send(payload)
            if payload["deadman"]:
                adapter.state["control"]["control"]["bridge"][
                    "motion_observation"
                ]["position_xyz"][0] = 0.101

        adapter.stream.send_twist = send_and_move  # type: ignore[method-assign]
        clock = FakeClock()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("observed travel exceeded", result["error"])
        self.assertEqual(
            len([item for item in adapter.stream.payloads if item["deadman"]]),
            1,
        )
        self.assertTrue(result["cleanup"]["final_exact_zero_confirmed"])

    def test_release_race_is_fail_closed_with_http_disarm_fallback(self):
        adapter = FakeAdapter(release_error=True)
        clock = FakeClock()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("release failed", result["error"])
        self.assertTrue(result["cleanup"]["http_disarm_fallback"])
        self.assertEqual(adapter.disarm_count, 1)
        self.assertEqual(adapter.stop_count, 0)
        self.assertFalse(adapter.state["control"]["control"]["lease"]["active"])
        self.assertFalse(adapter.stream.payloads[-1]["deadman"])

    def test_ack_faults_abort_once_and_still_confirm_exact_zero(self):
        cases = {
            "source_mismatch": "signed Bridge drive acceptance is unconfirmed",
            "type_mismatch": "signed Bridge drive acceptance is unconfirmed",
            "stale": "signed Bridge drive acceptance is unconfirmed",
            "nonadvancing": "signed Bridge drive acceptance is unconfirmed",
        }
        for ack_fault, expected_error in cases.items():
            with self.subTest(ack_fault=ack_fault):
                adapter = FakeAdapter(ack_fault=ack_fault)
                clock = FakeClock()
                result = probe.ProbeSupervisor(
                    adapter,
                    release_provider=lambda: RELEASE,
                    monotonic=clock.monotonic,
                    wall_ms=lambda: clock.now * 1000.0,
                    sleep=clock.sleep,
                ).run(probe.PROBES["MP-030"])
                self.assertEqual(result["status"], "FAIL")
                self.assertIn(expected_error, result["error"])
                self.assertTrue(result["cleanup"]["final_exact_zero_confirmed"])
                self.assertEqual(adapter.arm_count, 1)
                self.assertEqual(adapter.disarm_count, 0)
                self.assertEqual(
                    len([item for item in adapter.stream.payloads if item["deadman"]]),
                    1,
                )
                self.assertTrue(adapter.stream.closed)

    def test_bridge_output_overshoot_aborts_without_a_second_probe(self):
        adapter = FakeAdapter(output_scale=2.0)
        clock = FakeClock()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("exceeded the fixed probe envelope", result["error"])
        self.assertEqual(adapter.arm_count, 1)
        self.assertEqual(
            len([item for item in adapter.stream.payloads if item["deadman"]]),
            1,
        )
        self.assertTrue(result["cleanup"]["final_exact_zero_confirmed"])
        final = result["samples"][-1]
        self.assertEqual(final["request"]["motion_run_max_abs_linear_x"], 0.06)

    def test_late_scheduler_never_catches_up_or_retries(self):
        adapter = FakeAdapter()
        clock = LateClock()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("missed the command deadline", result["error"])
        self.assertTrue(clock.late_injected)
        self.assertEqual(adapter.arm_count, 1)
        self.assertEqual(
            len([item for item in adapter.stream.payloads if item["deadman"]]),
            1,
        )
        self.assertTrue(result["cleanup"]["final_exact_zero_confirmed"])

    def test_invalid_or_missing_arm_lease_uses_software_stop_without_stream(self):
        for arm_response in (None, "", "too-short"):
            with self.subTest(arm_response=arm_response):
                adapter = FakeAdapter(arm_response=arm_response)
                clock = FakeClock()
                result = probe.ProbeSupervisor(
                    adapter,
                    release_provider=lambda: RELEASE,
                    monotonic=clock.monotonic,
                    wall_ms=lambda: clock.now * 1000.0,
                    sleep=clock.sleep,
                ).run(probe.PROBES["MP-030"])
                self.assertEqual(result["status"], "FAIL")
                self.assertIn("invalid lease", result["error"])
                self.assertEqual(adapter.arm_count, 1)
                self.assertEqual(adapter.stream.payloads, [])
                self.assertEqual(adapter.stop_count, 1)
                self.assertTrue(result["cleanup"]["software_stop_attempted"])
                self.assertTrue(result["cleanup"]["software_stop_fallback"])
                self.assertTrue(result["cleanup"]["final_exact_zero_confirmed"])
                self.assertFalse(
                    adapter.state["control"]["control"]["lease"]["active"]
                )

    def test_explicit_zero_failure_is_retained_after_release_cleanup(self):
        adapter = FakeAdapter(zero_error=True)
        clock = FakeClock()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("explicit zero failed", result["error"])
        self.assertTrue(result["cleanup"]["websocket_release_acknowledged"])
        self.assertFalse(result["cleanup"]["http_disarm_fallback"])
        self.assertTrue(result["cleanup"]["final_exact_zero_confirmed"])
        self.assertTrue(adapter.stream.closed)

    def test_disarm_failure_escalates_once_to_software_stop(self):
        adapter = FakeAdapter(release_error=True, disarm_error=True)
        clock = FakeClock()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(adapter.disarm_count, 1)
        self.assertEqual(adapter.stop_count, 1)
        self.assertFalse(result["cleanup"]["http_disarm_fallback"])
        self.assertTrue(result["cleanup"]["software_stop_attempted"])
        self.assertTrue(result["cleanup"]["software_stop_fallback"])
        self.assertTrue(result["cleanup"]["final_exact_zero_confirmed"])
        self.assertTrue(
            any("HTTP disarm failed" in item for item in result["cleanup"]["errors"])
        )

    def test_software_stop_failure_is_bounded_and_never_retried(self):
        adapter = FakeAdapter(arm_response=None, software_stop_error=True)
        clock = FakeClock()
        result = probe.ProbeSupervisor(
            adapter,
            release_provider=lambda: RELEASE,
            monotonic=clock.monotonic,
            wall_ms=lambda: clock.now * 1000.0,
            sleep=clock.sleep,
        ).run(probe.PROBES["MP-030"])
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(adapter.stop_count, 1)
        self.assertTrue(result["cleanup"]["software_stop_attempted"])
        self.assertFalse(result["cleanup"]["software_stop_fallback"])
        self.assertFalse(result["cleanup"]["final_exact_zero_confirmed"])
        self.assertTrue(
            any(
                "software STOP failed" in item
                for item in result["cleanup"]["errors"]
            )
        )
        self.assertTrue(adapter.state["control"]["control"]["lease"]["active"])

    def test_cleanup_readiness_or_status_loss_fails_closed(self):
        for cleanup_fault, expected_error in (
            ("readiness", "not ready"),
            ("status", "stale"),
            ("lowstate", "LowState is stale"),
            ("cardinality", "changed"),
            ("connected", "not ready"),
            ("available", "not ready"),
            ("navigation", "Navigation or localization is active"),
        ):
            with self.subTest(cleanup_fault=cleanup_fault):
                adapter = FakeAdapter(cleanup_fault=cleanup_fault)
                clock = FakeClock()
                result = probe.ProbeSupervisor(
                    adapter,
                    release_provider=lambda: RELEASE,
                    monotonic=clock.monotonic,
                    wall_ms=lambda: clock.now * 1000.0,
                    sleep=clock.sleep,
                ).run(probe.PROBES["MP-030"])
                self.assertEqual(result["status"], "FAIL")
                self.assertIn(expected_error, result["error"])
                self.assertTrue(result["cleanup"]["software_stop_attempted"])
                self.assertTrue(result["cleanup"]["software_stop_fallback"])
                self.assertFalse(result["cleanup"]["final_exact_zero_confirmed"])
                self.assertEqual(adapter.stop_count, 1)
                self.assertEqual(adapter.arm_count, 1)

    def test_private_evidence_is_exclusive_and_mode_0600(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "private"
            path = probe._write_private_json({"safe": True}, root=root)
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"safe": True})

    def test_private_evidence_retries_short_writes(self):
        retained = bytearray()

        def short_write(_descriptor, value):
            chunk = bytes(value[:2])
            retained.extend(chunk)
            return len(chunk)

        with mock.patch.object(probe.os, "write", side_effect=short_write):
            probe._write_all(99, b"bounded-evidence")
        self.assertEqual(bytes(retained), b"bounded-evidence")

    def test_release_identity_requires_active_exact_matching_full_sha(self):
        def result(stdout: str, returncode: int = 0):
            def runner(*args, **kwargs):
                return subprocess.CompletedProcess(
                    args=args, returncode=returncode, stdout=stdout, stderr=""
                )

            return runner

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            release = base / RELEASE
            other_release = base / ("b" * 40)
            named_release = base / "not-a-commit"
            for path in (release, other_release, named_release):
                path.mkdir()

            self.assertEqual(
                probe.deployed_release_identity(
                    runner=result("123\n"),
                    root=release,
                    process_cwd=lambda _pid: release,
                ),
                RELEASE,
            )
            for runner, root, process_cwd in (
                (result("0\n"), release, lambda _pid: release),
                (result("not-a-pid\n"), release, lambda _pid: release),
                (result("123\n"), release, lambda _pid: other_release),
                (result("123\n"), named_release, lambda _pid: named_release),
                (result("123\n", returncode=1), release, lambda _pid: release),
            ):
                with self.subTest(root=root, runner=runner), self.assertRaises(
                    probe.ProbeError
                ):
                    probe.deployed_release_identity(
                        runner=runner,
                        root=root,
                        process_cwd=process_cwd,
                    )

            def timeout_runner(*_args, **_kwargs):
                raise subprocess.TimeoutExpired(cmd="systemctl", timeout=3.0)

            with self.assertRaises(probe.ProbeError):
                probe.deployed_release_identity(
                    runner=timeout_runner,
                    root=release,
                    process_cwd=lambda _pid: release,
                )

    def test_source_has_no_direct_ros_sdk_or_free_motion_controls(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("/api/sport/request", source)
        self.assertNotIn("create_publisher", source)
        self.assertNotIn("create_subscription", source)
        self.assertNotIn("unitree_sdk2py", source)
        self.assertNotIn("rclpy", source)
        self.assertNotIn("--velocity", source)
        self.assertNotIn("--duration", source)
        self.assertNotIn("--host", source)
        self.assertNotIn("--url", source)
        self.assertLess(
            source.index("output = _write_private_json(payload)"),
            source.rindex("_append_event(payload)"),
        )


if __name__ == "__main__":
    unittest.main()
