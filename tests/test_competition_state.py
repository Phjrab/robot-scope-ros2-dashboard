import json
import os
import tempfile
import unittest
from pathlib import Path

from robot_dashboard.api.routers.competition import router
from robot_dashboard.competition import (
    CompetitionConflict,
    CompetitionConfirmationRequired,
    CompetitionStateManager,
    CompetitionUnavailable,
)


class CompetitionStateTests(unittest.TestCase):
    def manager(self, root: Path, blockers=None, control=None):
        return CompetitionStateManager(
            root,
            blockers_provider=lambda: blockers or {},
            control_provider=lambda: control or {
                "estop_latched": False,
                "lease": {"active": False},
            },
        )

    def test_lock_mode_and_restart_state_are_persistent_and_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "competition"
            manager = self.manager(root)
            self.assertEqual(manager.snapshot()["operation_mode"], "MANUAL")
            self.assertEqual(manager.snapshot()["motion_authority"], "NONE")
            shadow = manager.set_mode("SHADOW", "SHADOW")
            self.assertEqual(shadow["requested_mode"], "SHADOW")
            locked = manager.lock("LOCK")
            self.assertTrue(locked["locked"])
            restored = self.manager(root).snapshot()
            self.assertTrue(restored["locked"])
            self.assertEqual(restored["requested_mode"], "SHADOW")
            self.assertEqual(stat_mode(root / "state.json"), 0o600)
            self.assertEqual(stat_mode(root), 0o700)

    def test_assisted_auto_and_derived_safe_stop_never_gain_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "competition"
            manager = self.manager(root)
            for mode in ("ASSISTED", "AUTO", "SAFE_STOP"):
                with self.assertRaises(CompetitionConflict):
                    manager.set_mode(mode, mode)
            stopped = self.manager(
                Path(temporary).resolve() / "stopped",
                control={"estop_latched": True, "lease": {"active": False}},
            ).snapshot()
            self.assertEqual(stopped["operation_mode"], "SAFE_STOP")
            self.assertEqual(stopped["motion_authority"], "NONE")

    def test_unlock_requires_exact_action_stationary_disarmed_and_idle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "competition"
            blockers = {"control_armed": True, "dataset_capture_active": True}
            manager = self.manager(root, blockers=blockers)
            manager.lock("LOCK")
            with self.assertRaises(CompetitionConfirmationRequired):
                manager.unlock("UNLOCK", stationary_confirmed=False)
            with self.assertRaises(CompetitionConflict) as raised:
                manager.unlock("UNLOCK", stationary_confirmed=True)
            self.assertIn("control_armed", str(raised.exception))
            blockers.clear()
            self.assertFalse(manager.unlock("UNLOCK", stationary_confirmed=True)["locked"])

    def test_corrupt_or_permissive_state_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "competition"
            manager = self.manager(root)
            manager.path.write_text("{}", encoding="utf-8")
            with self.assertRaises(CompetitionUnavailable):
                self.manager(root)
            manager.path.write_text(json.dumps(manager._state), encoding="utf-8")
            os.chmod(manager.path, 0o644)
            with self.assertRaises(CompetitionUnavailable):
                self.manager(root)


class CompetitionRouterTests(unittest.TestCase):
    def test_router_exposes_one_read_and_three_explicit_mutations(self):
        routes = {
            (method, route.path)
            for route in router.routes
            for method in (route.methods or set())
        }
        self.assertEqual(routes, {
            ("GET", "/api/v1/competition"),
            ("POST", "/api/v1/competition/lock"),
            ("POST", "/api/v1/competition/unlock"),
            ("POST", "/api/v1/competition/mode"),
        })


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


if __name__ == "__main__":
    unittest.main()
