"""Source-specific timeout tests; no ROS or robot connection is used."""

import json
import unittest
from pathlib import Path

from robot_dashboard.control import CommandValidationError, ControlManager, LeaseInvalid
from robot_dashboard.go2_bridge import Go2BridgeCore


class NavigationTimeoutConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.profile = json.loads(
            (Path(__file__).resolve().parents[1] / "config/go2.json").read_text()
        )

    def armed(self, source="navigation"):
        manager = ControlManager(
            self.profile,
            environ={"ROBOT_SCOPE_CONTROL_ENABLED": "true"},
            clock=lambda: self.now,
            token_factory=lambda: "offline-timeout-test-token",
        )
        manager.set_readiness(bridge_ready=True, lowstate_ready=True)
        lease = (
            manager.acquire_navigation_lease() if source == "navigation"
            else manager.acquire_lease(source)
        )
        token = lease["token"]
        manager.bind_lease(token, "offline")
        return manager, token

    @staticmethod
    def drive(manager, token, seq=0, age=0.0):
        return manager.submit_drive(
            token, "offline", seq, vx=0.1, vy=0.0, wz=0.0,
            deadman=True, client_age_s=age,
        )

    def test_go2_navigation_accepts_201ms_gap(self):
        manager, token = self.armed()
        self.drive(manager, token)
        self.now = 0.201
        self.drive(manager, token, seq=1)
        self.assertEqual(manager.tick()[-1]["type"], "drive")
        self.assertTrue(manager.snapshot()["lease"]["active"])

    def test_navigation_expires_at_300ms_and_late_command_cannot_resume(self):
        manager, token = self.armed()
        self.drive(manager, token)
        self.now = 0.299999
        self.assertEqual(manager.tick()[-1]["type"], "drive")
        self.now = 0.3
        output = manager.tick()[-1]
        self.assertEqual(output["reason"], "command_timeout")
        self.assertEqual(output["velocity"], {"vx": 0.0, "vy": 0.0, "wz": 0.0})
        with self.assertRaisesRegex(LeaseInvalid, "command_timeout"):
            self.drive(manager, token, seq=1)

    def test_manual_sources_still_expire_at_200ms(self):
        for source in ("keyboard", "gamepad"):
            with self.subTest(source=source):
                self.now = 0.0
                manager, token = self.armed(source)
                self.drive(manager, token)
                self.now = 0.2
                self.assertEqual(manager.tick()[-1]["reason"], "command_timeout")
                self.assertFalse(manager.snapshot()["lease"]["active"])

    def test_client_age_validation_uses_the_lease_source(self):
        manager, token = self.armed()
        self.drive(manager, token, age=0.25)
        self.assertEqual(manager.tick()[-1]["type"], "drive")
        manager, token = self.armed("keyboard")
        with self.assertRaises(CommandValidationError):
            self.drive(manager, token, age=0.25)

    def test_navigation_defaults_to_300ms_and_caps_at_300ms(self):
        del self.profile["control"]["navigation_command_timeout_s"]
        manager, token = self.armed()
        self.drive(manager, token)
        self.now = 0.299999
        self.assertEqual(manager.tick()[-1]["type"], "drive")
        self.now = 0.3
        self.assertEqual(manager.tick()[-1]["reason"], "command_timeout")
        self.now = 0.0
        self.profile["control"]["navigation_command_timeout_s"] = 10.0
        manager, token = self.armed()
        self.drive(manager, token)
        self.now = 0.3
        self.assertEqual(manager.tick()[-1]["reason"], "command_timeout")

    def test_missing_navigation_setting_does_not_inherit_manual_timeout(self):
        del self.profile["control"]["navigation_command_timeout_s"]
        self.profile["control"]["command_timeout_s"] = 0.1
        manager, token = self.armed()
        self.drive(manager, token)
        self.now = 0.299999
        self.assertEqual(manager.tick()[-1]["type"], "drive")
        self.now = 0.3
        self.assertEqual(manager.tick()[-1]["reason"], "command_timeout")

    def test_bridge_keeps_independent_200ms_cap(self):
        self.assertEqual(self.profile["control"]["bridge_command_timeout_s"], 0.2)
        bridge = Go2BridgeCore(command_timeout_s=0.3)
        self.assertEqual(bridge.command_timeout_s, 0.2)


if __name__ == "__main__":
    unittest.main()
