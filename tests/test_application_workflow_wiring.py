"""Exercise shared app wiring without importing or starting a ROS agent."""

import argparse
import ast
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from robot_dashboard.application.runtime import ApplicationRuntime, configure_competition
from robot_dashboard.competition import CompetitionConflict
from robot_dashboard.mapping_jobs import SUPPORTED_MAPPING_PROFILES, WIRED_MAPPING_PROFILE


APP = Path(__file__).resolve().parents[1] / "robot_dashboard" / "app.py"


class SharedWorkflowWiringTests(unittest.TestCase):
    def setUp(self):
        self.tree = ast.parse(APP.read_text(encoding="utf-8"))
        self.main = next(node for node in self.tree.body
                         if isinstance(node, ast.FunctionDef) and node.name == "main")

    def test_native_preview_requires_explicit_cli_flag(self):
        function = next(node for node in self.tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == "parse_args")
        namespace = {
            "argparse": argparse, "Path": Path, "__file__": str(APP),
            "SUPPORTED_MAPPING_PROFILES": SUPPORTED_MAPPING_PROFILES,
            "WIRED_MAPPING_PROFILE": WIRED_MAPPING_PROFILE,
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(APP), "exec"), namespace)
        for flags, expected in (([], False), (["--mission-native-preview"], True)):
            with self.subTest(flags=flags), patch("sys.argv", ["robot-scope", *flags]):
                self.assertIs(namespace["parse_args"]().mission_native_preview, expected)

    def test_mission_hook_uses_final_slam_and_exact_runtime_without_policy_proof(self):
        calls = {name: [node for node in ast.walk(self.main)
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == name]
                 for name in ("configure_slam", "configure_mission_routes")}
        self.assertEqual(len(calls["configure_slam"]), 1)
        self.assertEqual(len(calls["configure_mission_routes"]), 1)
        slam_call, mission_call = calls["configure_slam"][0], calls["configure_mission_routes"][0]
        self.assertLess(slam_call.lineno, mission_call.lineno)
        for owner in ("saved_maps", "spatial_routes", "navigation", "mission"):
            assignments = [node.lineno for node in ast.walk(self.main)
                           if isinstance(node, ast.Assign) and any(
                               isinstance(target, ast.Attribute) and target.attr == owner
                               and isinstance(target.value, ast.Name) and target.value.id == "RUNTIME"
                               for target in node.targets)]
            self.assertTrue(assignments, owner)
            self.assertLess(max(assignments), slam_call.lineno, owner)
        runtime = ApplicationRuntime()
        record = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            state_root = Path(temporary).resolve() / "navigation"
            for enabled in (False, True):
                record.reset_mock()
                namespace = {"RUNTIME": runtime, "Path": Path, "configure_mission_routes": record,
                             "args": SimpleNamespace(navigation_runtime_dir=str(state_root),
                                                     mission_native_preview=enabled)}
                exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.Expr(mission_call)], type_ignores=[])),
                             str(APP), "exec"), namespace)
                record.assert_called_once_with(runtime, state_root / "mission-routes",
                                               native_planner_window=enabled)

    def test_legacy_and_additive_routers_each_registered_once(self):
        registered = [node.args[0].id for node in ast.walk(self.tree)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                      and node.func.attr == "include_router" and node.args
                      and isinstance(node.args[0], ast.Name)]
        for name in ("missions_router", "mission_routes_router", "slam_router"):
            self.assertEqual(registered.count(name), 1, name)

    def test_competition_keeps_live_blockers_and_control_authority(self):
        values = {key: False for key in ("control_armed", "navigation_active", "mission_active",
                                        "dataset_capture_active", "mapping_active")}
        control = {"lease": {"active": False}, "estop_latched": False}
        runtime = ApplicationRuntime(
            agent=SimpleNamespace(control_snapshot=lambda: control),
            mapping=SimpleNamespace(activity=lambda: (values["mapping_active"], None)),
            navigation=SimpleNamespace(is_active=lambda: values["navigation_active"]),
            mission=SimpleNamespace(blocks_navigation_goal=lambda: values["mission_active"]),
            dataset_capture=SimpleNamespace(is_active=lambda: values["dataset_capture_active"]),
        )
        other_runtime = ApplicationRuntime()
        with tempfile.TemporaryDirectory() as temporary:
            configure_competition(runtime, Path(temporary).resolve() / "competition")
            self.assertIsNone(other_runtime.competition)
            manager = runtime.competition
            manager.lock("LOCK")
            for key in values:
                with self.subTest(key=key):
                    values[key] = True
                    control["lease"]["active"] = values["control_armed"]
                    with self.assertRaisesRegex(CompetitionConflict, key):
                        manager.unlock("UNLOCK", stationary_confirmed=True)
                    self.assertTrue(manager.snapshot()["locked"])
                    values[key] = False
                    control["lease"]["active"] = False
            self.assertFalse(manager.unlock("UNLOCK", stationary_confirmed=True)["locked"])
            control["estop_latched"] = True
            self.assertEqual(manager.snapshot()["operation_mode"], "SAFE_STOP")
            self.assertEqual(manager.snapshot()["motion_authority"], "NONE")


if __name__ == "__main__":
    unittest.main()
