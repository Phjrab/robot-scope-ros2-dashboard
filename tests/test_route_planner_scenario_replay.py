from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from robot_dashboard.route_planner.clock import VirtualClockError, VirtualMonotonicClock
from robot_dashboard.route_planner.perception import (
    MAX_UINT64,
    PerceptionContractError,
    normalize_perception_snapshot,
)
from robot_dashboard.route_planner.replay import (
    ALLOWED_EVENT_KINDS,
    FORBIDDEN_CONTROL_EVENT_KINDS,
    SCENARIO_ROOT,
    ScenarioReplayError,
    load_scenario,
    normalize_scenario,
    replay_scenario_file,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "docs" / "contracts" / "route_planner"
SCENARIOS = sorted(SCENARIO_ROOT.glob("*.json"))


class PerceptionSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.success = json.loads(
            (CONTRACT_ROOT / "examples" / "perception-success.json").read_text(
                encoding="utf-8"
            )
        )

    def test_schema_is_draft_2020_12_exact_and_bounded(self) -> None:
        schema = json.loads(
            (CONTRACT_ROOT / "perception-envelope-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["frame_id"]["enum"], ["base_link"])
        self.assertEqual(schema["properties"]["sequence"]["maximum"], MAX_UINT64)
        self.assertEqual(schema["properties"]["observed_at_ns"]["maximum"], MAX_UINT64)
        for field in ("traffic", "crosswalks", "people", "aruco"):
            self.assertEqual(schema["properties"][field]["maxItems"], 32)

    def test_success_and_failed_examples_match_runtime_contract(self) -> None:
        success = normalize_perception_snapshot(
            self.success, now_ns=self.success["observed_at_ns"]
        )
        self.assertTrue(success["fresh"])
        failed_raw = json.loads(
            (CONTRACT_ROOT / "examples" / "perception-failed.json").read_text(
                encoding="utf-8"
            )
        )
        failed = normalize_perception_snapshot(
            failed_raw, now_ns=failed_raw["observed_at_ns"]
        )
        self.assertFalse(failed["fresh"])
        self.assertEqual(failed["state"], "FAILED")

    def test_unknown_fields_bad_frame_uint64_and_non_finite_are_rejected(self) -> None:
        invalid = json.loads(
            (
                CONTRACT_ROOT / "examples" / "perception-invalid-unknown-field.json"
            ).read_text(encoding="utf-8")
        )
        cases = [invalid]
        for field, value in (
            ("frame_id", "map"),
            ("sequence", MAX_UINT64 + 1),
            ("observed_at_ns", MAX_UINT64 + 1),
            ("confidence", float("nan")),
        ):
            candidate = copy.deepcopy(self.success)
            candidate[field] = value
            cases.append(candidate)
        too_many = copy.deepcopy(self.success)
        too_many["traffic"] = too_many["traffic"] * 33
        cases.append(too_many)
        for candidate in cases:
            with (
                self.subTest(candidate=candidate),
                self.assertRaises(PerceptionContractError),
            ):
                normalize_perception_snapshot(
                    candidate, now_ns=self.success["observed_at_ns"]
                )

    def test_future_timestamp_is_rejected_and_one_second_is_still_fresh(self) -> None:
        with self.assertRaisesRegex(PerceptionContractError, "future"):
            normalize_perception_snapshot(
                self.success, now_ns=self.success["observed_at_ns"] - 1
            )
        boundary = normalize_perception_snapshot(
            self.success, now_ns=self.success["observed_at_ns"] + 1_000_000_000
        )
        stale = normalize_perception_snapshot(
            self.success, now_ns=self.success["observed_at_ns"] + 1_000_000_001
        )
        self.assertTrue(boundary["fresh"])
        self.assertFalse(stale["fresh"])


class VirtualClockTests(unittest.TestCase):
    def test_clock_is_deterministic_monotonic_and_uint64_bounded(self) -> None:
        clock = VirtualMonotonicClock(100)
        self.assertEqual(clock.now_ns(), 100)
        self.assertEqual(clock.advance_ms(2), 2_000_100)
        self.assertEqual(clock.set_ns(3_000_000), 3_000_000)
        with self.assertRaises(VirtualClockError):
            clock.advance_ms(-1)
        with self.assertRaises(VirtualClockError):
            clock.set_ns(2_999_999)
        with self.assertRaises(VirtualClockError):
            VirtualMonotonicClock(MAX_UINT64).advance_ms(1)


class ScenarioReplayTests(unittest.TestCase):
    def test_required_event_allowlist_excludes_every_control_event(self) -> None:
        self.assertEqual(
            ALLOWED_EVENT_KINDS,
            {
                "POSE",
                "PERCEPTION",
                "ORDER_STATUS",
                "PICKUP_CONFIRM",
                "DROPOFF_CONFIRM",
                "TIME_ADVANCE",
                "SERVER_RESTART",
                "MAP_REVISION_CHANGE",
                "GRAPH_REVISION_CHANGE",
            },
        )
        self.assertFalse(ALLOWED_EVENT_KINDS & FORBIDDEN_CONTROL_EVENT_KINDS)

    def test_event_order_and_forbidden_control_events_are_rejected(self) -> None:
        scenario = load_scenario(SCENARIO_ROOT / "traffic-red-to-green.json")
        scenario["events"][1]["at_ms"] = 700
        scenario["events"][2]["at_ms"] = 600
        with self.assertRaisesRegex(ScenarioReplayError, "ordered"):
            normalize_scenario(scenario)
        scenario = load_scenario(SCENARIO_ROOT / "order-low-valid.json")
        scenario["events"] = [{"at_ms": 0, "kind": "MISSION_START", "payload": {}}]
        with self.assertRaisesRegex(ScenarioReplayError, "forbidden"):
            normalize_scenario(scenario)

    def test_loader_is_confined_to_the_scenario_fixture_root(self) -> None:
        with self.assertRaisesRegex(ScenarioReplayError, "allowed root"):
            load_scenario(CONTRACT_ROOT / "perception-envelope-v1.schema.json")

    def test_at_least_twenty_golden_scenarios_are_deterministic(self) -> None:
        self.assertGreaterEqual(len(SCENARIOS), 20)
        identifiers: set[str] = set()
        for path in SCENARIOS:
            with self.subTest(path=path.name):
                first = replay_scenario_file(path)
                second = replay_scenario_file(path)
                self.assertEqual(first, second)
                self.assertTrue(first["expected_vs_actual"]["match"])
                self.assertEqual(first["side_effect_count"], 0)
                self.assertTrue(
                    all(value == 0 for value in first["side_effect_counters"].values())
                )
                self.assertNotIn(first["scenario_id"], identifiers)
                identifiers.add(first["scenario_id"])

    def test_sequence_rollback_is_invalid_and_restart_does_not_resume(self) -> None:
        rollback = replay_scenario_file(
            SCENARIO_ROOT / "traffic-sequence-rollback.json"
        )
        self.assertEqual(
            rollback["expected_vs_actual"]["actual"]["stale_or_invalid"],
            "INVALID_PERCEPTION",
        )
        restart = replay_scenario_file(SCENARIO_ROOT / "composite-server-restart.json")
        self.assertEqual(restart["route_state"], "RESTART_REQUIRED")
        self.assertIsNone(restart["recommendation_id"])
        self.assertEqual(restart["guidance_state"], "GUIDANCE_PAUSED")

    def test_replay_module_has_no_runtime_or_control_adapter_import(self) -> None:
        source = (ROOT / "robot_dashboard" / "route_planner" / "replay.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        for forbidden in (
            "rclpy",
            "fastapi",
            "socket",
            "subprocess",
            "robot_dashboard.runtime",
        ):
            self.assertNotIn(forbidden, imports)
        for forbidden_name in (
            "ControlManager",
            "NavigationCoordinator",
            "NavigationRosGateway",
            "MissionCoordinator",
        ):
            self.assertNotIn(forbidden_name, source)

    def test_cli_emits_matching_json_and_zero_side_effects(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "replay_route_planner_scenario.py"),
                "--scenario",
                str(SCENARIO_ROOT / "order-low-valid.json"),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertTrue(output["expected_vs_actual"]["match"])
        self.assertEqual(output["side_effect_count"], 0)
        rejected = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "replay_route_planner_scenario.py"),
                "--scenario",
                str(CONTRACT_ROOT / "perception-envelope-v1.schema.json"),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(rejected.returncode, 2)
        failure = json.loads(rejected.stderr)
        self.assertEqual(failure["side_effect_count"], 0)
        self.assertTrue(
            all(value == 0 for value in failure["side_effect_counters"].values())
        )


if __name__ == "__main__":
    unittest.main()
