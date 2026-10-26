# ruff: noqa: E402
"""Keep the narrow candidate from changing the conditions it aims to satisfy."""

import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configure import candidate, validate_config
from d0_adapter import load_fixture, input_path
from native_runner import loaded_plugin_paths, plugin_library_names
from run_narrow import ORDER


class NarrowTests(unittest.TestCase):
    def test_library_proof_separates_overlay_and_preserved_stock(self):
        maps = "\n".join(
            "100-200 r-xp 0 0 1 " + path
            for path in (
                "/opt/c3-overlay/lib/libmppi_controller.so",
                "/opt/ros/humble/lib/libmppi_controller.so",
                "/tmp/opt/c3-overlay/lib/libmppi_controller.so",
                "/opt/c3-overlay/lib/libunrelated.so",
            )
        )
        names = {"libmppi_controller.so"}
        self.assertEqual(
            loaded_plugin_paths(maps, names, "omni_checked_overlay"),
            {"/opt/c3-overlay/lib/libmppi_controller.so"},
        )
        self.assertEqual(
            loaded_plugin_paths(maps, names, "omni_coverage"),
            {"/opt/ros/humble/lib/libmppi_controller.so"},
        )

    def test_candidate_changes_only_native_planner(self):
        fixture = load_fixture(input_path("feasible1"))
        baseline = candidate("rpp", fixture=fixture)
        selected = candidate("rpp", "se2_rpp", fixture)
        self.assertEqual(
            validate_config(selected, "rpp", fixture["effective_footprint"]), []
        )
        selected = copy.deepcopy(selected)
        selected["planner_server"] = baseline["planner_server"]
        self.assertEqual(selected, baseline)

    def test_candidate_cannot_silently_change_model_or_builtin_contract(self):
        with self.assertRaises(ValueError):
            candidate("mppi", "se2_rpp", load_fixture(input_path("feasible1")))
        with self.assertRaises(ValueError):
            candidate("rpp", "se2_rpp")
        with self.assertRaises(ValueError):
            candidate("rpp", "unknown_revision")

    def test_humble_slash_export_resolves_actual_library(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "smac.xml").write_text(
                '<library path="nav2_smac_planner"><class '
                'name="nav2_smac_planner/SmacPlannerHybrid" '
                'type="nav2_smac_planner::SmacPlannerHybrid"/></library>'
            )
            self.assertEqual(
                plugin_library_names(directory, "nav2_smac_planner/SmacPlannerHybrid"),
                {"libnav2_smac_planner.so"},
            )

    def test_bounded_run_order_has_only_requested_cases(self):
        self.assertEqual(ORDER[0], ("rpp", "d0_feasible1", 0))
        self.assertEqual(len(ORDER), 6)
        self.assertEqual(
            ORDER[-2:], [("rpp", "d0_feasible1", 1), ("rpp", "d0_feasible2", 0)]
        )
        self.assertEqual(
            {s for _, s, _ in ORDER},
            {
                "d0_feasible1",
                "d0_feasible2",
                "d0_empty",
                "d0_blocked",
                "d0_sensor_dropout",
            },
        )
