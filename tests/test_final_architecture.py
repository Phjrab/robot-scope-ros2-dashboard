import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"
APP = ROOT / "robot_dashboard" / "app.py"
AGENT = ROOT / "robot_dashboard" / "ros_agent.py"
FRONTEND = ROOT / "robot_dashboard" / "static" / "app.js"
PRODUCT_ROOTS = (
    ROOT / "config",
    ROOT / "scripts",
    ROOT / "robot_dashboard",
)


class FinalArchitectureAuditTests(unittest.TestCase):
    def test_current_architecture_is_the_documented_product_authority(self):
        source = ARCHITECTURE.read_text(encoding="utf-8")
        for required in (
            "ROS2 Autonomous Mobile Robot Mapping, Navigation and Control Dashboard",
            "## Before and after",
            "## Module layout and ownership",
            "## Preserved safety contracts",
            "## SO-101 extraction and assets",
            "## Cleanup and duplicate-authority audit",
            "## Remaining debt and future milestones",
        ):
            self.assertIn(required, source)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/ARCHITECTURE.md", readme)
        self.assertIn(
            "ROS2 Autonomous Mobile Robot Mapping, Navigation and Control Dashboard",
            readme,
        )
        self.assertIn(
            'description="ROS2 Autonomous Mobile Robot Mapping, Navigation and Control Dashboard"',
            APP.read_text(encoding="utf-8"),
        )
        for required_document in (
            "INSTALL.md",
            "DEPENDENCIES.md",
            "TOPOLOGY.md",
            "TROUBLESHOOTING.md",
        ):
            self.assertTrue((ROOT / "docs" / required_document).is_file())
        self.assertTrue((ROOT / "THIRD_PARTY_NOTICES.md").is_file())

        for linked_record in (
            "ARCHITECTURE_BASELINE.md",
            "ARCHITECTURE_PHASE8.md",
            "ARCHITECTURE_PHASE9.md",
            "SO101_EXTRACTION.md",
        ):
            self.assertIn(linked_record, source)

    def test_phase_zero_hotspots_remain_materially_reduced(self):
        baseline = {
            APP: 3_208,
            AGENT: 4_723,
            FRONTEND: 8_404,
        }
        ceilings = {
            APP: 1_600,
            AGENT: 2_600,
            FRONTEND: 7_500,
        }
        for path, baseline_lines in baseline.items():
            with self.subTest(path=path.name):
                current_lines = len(path.read_text(encoding="utf-8").splitlines())
                self.assertLess(current_lines, baseline_lines)
                self.assertLess(current_lines, ceilings[path])

    def test_runtime_product_tree_has_no_so101_or_lerobot_residue(self):
        residue = re.compile(r"so[-_ ]?101|lerobot", re.IGNORECASE)
        found = []
        for root in PRODUCT_ROOTS:
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    source = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if residue.search(path.as_posix()) or residue.search(source):
                    found.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(found, [])

    def test_runtime_ownership_and_component_boundaries_are_explicit(self):
        app_source = APP.read_text(encoding="utf-8")
        agent_source = AGENT.read_text(encoding="utf-8")
        runtime_source = (
            ROOT / "robot_dashboard" / "application" / "runtime.py"
        ).read_text(encoding="utf-8")

        self.assertEqual(app_source.count("RUNTIME = ApplicationRuntime()"), 1)
        for legacy_global in (
            "AGENT =",
            "MAPPING_JOBS =",
            "NAVIGATION_JOBS =",
            "MAPPING_TASK =",
            "NAVIGATION_START_TASK =",
        ):
            self.assertNotIn(legacy_global, app_source)
        for owner in (
            "mapping: MappingCoordinator | None",
            "navigation: NavigationCoordinator | None",
            "lifecycle: LifecycleCoordinator | None",
        ):
            self.assertIn(owner, runtime_source)
        self.assertEqual(agent_source.count("ControlTransport("), 1)
        self.assertEqual(agent_source.count("NavigationRosGateway("), 1)

    def test_assets_and_notices_match_the_mobile_product_boundary(self):
        catalog_path = (
            ROOT
            / "robot_dashboard"
            / "static"
            / "assets"
            / "robot-model-catalog.json"
        )
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        self.assertEqual(set(catalog["models"]), {"go2", "turtlebot"})
        self.assertFalse((catalog_path.parent / "so101").exists())

        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("Unitree Go2 model", notices)
        self.assertIn("ROBOTIS TurtleBot3 Burger model", notices)
        self.assertNotRegex(notices, re.compile(r"so[-_ ]?101|lerobot", re.I))


if __name__ == "__main__":
    unittest.main()
