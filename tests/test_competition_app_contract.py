import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CompetitionAppContractTests(unittest.TestCase):
    def test_configuration_mutations_are_gated_but_cleanup_remains_available(self):
        app = (ROOT / "robot_dashboard" / "app.py").read_text(encoding="utf-8")
        system = (ROOT / "robot_dashboard" / "api" / "routers" / "system.py").read_text(encoding="utf-8")
        discovery = (ROOT / "robot_dashboard" / "api" / "routers" / "discovery.py").read_text(encoding="utf-8")
        telemetry = (ROOT / "robot_dashboard" / "api" / "routers" / "telemetry.py").read_text(encoding="utf-8")
        missions = (ROOT / "robot_dashboard" / "api" / "routers" / "missions.py").read_text(encoding="utf-8")
        for phrase in (
            "navigation parameter changes", "map revision creation", "map revision conversion",
            "edited map revision creation", "map annotation revision changes", "saved map rename",
            "saved map deletion",
        ):
            self.assertIn(f'require_competition_unlocked(RUNTIME, "{phrase}")', app)
        for phrase in ("dashboard service restart", "dashboard service stop", "control bridge service start"):
            self.assertIn(f'require_competition_unlocked(runtime, "{phrase}")', system)
        self.assertNotIn('require_competition_unlocked(runtime, "control bridge service stop")', system)
        self.assertIn("robot network target changes", discovery)
        self.assertIn("robot network target disconnect", discovery)
        self.assertIn("sensor source selection", telemetry)
        self.assertIn("PointCloud diagnostic settings", telemetry)
        self.assertIn("mission revision creation", missions)

    def test_local_model_activation_obeys_the_same_persistent_lock(self):
        tool = (ROOT / "scripts" / "model_registry_tool.py").read_text(encoding="utf-8")
        self.assertIn('args.command in {"activate", "rollback"}', tool)
        self.assertIn("ROBOT_SCOPE_COMPETITION_STATE_DIR", tool)
        self.assertIn("competition state must exist before model activation", tool)
        self.assertIn("require_unlocked", tool)

    def test_runner_wires_a_private_persistent_state_root(self):
        for relative in ("scripts/run_go2_humble.sh", "scripts/run_generic.sh"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("ROBOT_SCOPE_COMPETITION_STATE_DIR", source)
            self.assertIn('--competition-state-dir "$COMPETITION_STATE_DIR"', source)


if __name__ == "__main__":
    unittest.main()
