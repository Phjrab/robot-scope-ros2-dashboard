import importlib.util
import sys
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch


if importlib.util.find_spec("rclpy") is None:
    class Dummy:
        pass

    rclpy = types.ModuleType("rclpy")
    rclpy.ok = lambda: False
    rclpy.init = lambda **kwargs: None
    rclpy.shutdown = lambda: None
    stubs = {
        "rclpy": rclpy,
        "rclpy.callback_groups": types.ModuleType("rclpy.callback_groups"),
        "rclpy.executors": types.ModuleType("rclpy.executors"),
        "rclpy.node": types.ModuleType("rclpy.node"),
        "rclpy.qos": types.ModuleType("rclpy.qos"),
        "rosidl_runtime_py": types.ModuleType("rosidl_runtime_py"),
        "rosidl_runtime_py.utilities": types.ModuleType("rosidl_runtime_py.utilities"),
        "std_msgs": types.ModuleType("std_msgs"),
        "std_msgs.msg": types.ModuleType("std_msgs.msg"),
    }
    stubs["rclpy.callback_groups"].MutuallyExclusiveCallbackGroup = Dummy
    stubs["rclpy.executors"].MultiThreadedExecutor = Dummy
    stubs["rclpy.node"].Node = Dummy
    for name in ("DurabilityPolicy", "HistoryPolicy", "QoSProfile", "ReliabilityPolicy"):
        setattr(stubs["rclpy.qos"], name, Dummy)
    stubs["rosidl_runtime_py.utilities"].get_message = lambda value: Dummy
    stubs["std_msgs.msg"].String = Dummy
    sys.modules.update(stubs)

from robot_dashboard.control import ControlDisabled, ControlManager
from robot_dashboard.ros_agent import RosAgent


ROOT = Path(__file__).resolve().parents[1]


class RobotTargetSafetyTests(unittest.TestCase):
    def setUp(self):
        self.agent = RosAgent(
            robot_ip="192.168.123.161",
            profile_path=str(ROOT / "config" / "go2.json"),
        )
        profile = {"name": "Unitree Go2", "control": {"enabled": True}}
        environ = {
            "ROBOT_SCOPE_CONTROL_ENABLED": "true",
            "ROBOT_SCOPE_CONTROL_PIN_SHA256": ControlManager.pin_sha256("4826"),
        }
        self.manager = ControlManager(
            profile,
            environ=environ,
            token_factory=lambda: "test-target-lease-token-long-enough",
        )
        self.manager.set_readiness(bridge_ready=True, lowstate_ready=True)
        self.agent._control_manager = self.manager

    def test_target_change_revokes_lease_and_non_go2_blocks_all_enabling_mutators(self):
        lease = self.agent.control_acquire("4826", "keyboard")["token"]
        self.agent.control_bind(lease, "target-test-websocket")

        selected = self.agent.set_robot_target(
            "10.100.0.42",
            "turtlebot",
            "turtlebot3.local",
        )
        self.assertTrue(selected["changed"])
        self.assertEqual(selected["robot_type"], "turtlebot")
        self.assertFalse(self.manager.snapshot()["lease"]["active"])
        self.assertTrue(self.manager.snapshot()["estop"]["latched"])

        snapshot = self.agent.control_snapshot()
        self.assertFalse(snapshot["target_supported"])
        self.assertFalse(snapshot["target_matches_startup"])
        self.assertTrue(snapshot["restart_required"])
        self.assertTrue(snapshot["control_restart_required"])
        self.assertEqual(snapshot["control_target_reason"], "runtime_target_changed_restart_required")
        self.assertFalse(snapshot["enabled"])
        self.assertEqual(snapshot["actions"], [])
        calls = (
            lambda: self.agent.control_acquire("4826", "keyboard"),
            lambda: self.agent.control_bind("invalid", "binding"),
            lambda: self.agent.control_heartbeat("invalid", "binding", 1),
            lambda: self.agent.control_drive("invalid", "binding", 1, vx=0, vy=0, wz=0),
            lambda: self.agent.control_action("invalid", "binding", 1, "hello", confirm=True),
            lambda: self.agent.control_clear_estop("4826", confirm=True),
        )
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaises(ControlDisabled):
                    call()

        # Returning the UI selection to the startup values cannot retarget or
        # re-authorize the already constructed DDS transport.
        returned = self.agent.set_robot_target("192.168.123.161", "go2", "")
        self.assertTrue(returned["changed"])
        self.assertTrue(returned["target_matches_startup"])
        self.assertTrue(returned["restart_required"])
        self.assertTrue(returned["control_restart_required"])
        self.assertEqual(returned["control_target_reason"], "runtime_target_changed_restart_required")
        self.assertFalse(returned["control_target_supported"])
        returned_control = self.agent.control_snapshot()
        self.assertTrue(returned_control["target_matches_startup"])
        self.assertTrue(returned_control["restart_required"])
        self.assertFalse(returned_control["target_supported"])
        with self.assertRaises(ControlDisabled):
            self.agent.control_acquire("4826", "keyboard")

    def test_same_target_metadata_refresh_does_not_revoke_lease(self):
        lease = self.agent.control_acquire("4826", "keyboard")["token"]
        self.agent.control_bind(lease, "target-test-websocket")
        selected = self.agent.set_robot_target(
            "192.168.123.161",
            "go2",
            "unitree-go2.local",
        )
        self.assertFalse(selected["changed"])
        self.assertTrue(selected["target_matches_startup"])
        self.assertFalse(selected["restart_required"])
        self.assertFalse(selected["control_restart_required"])
        self.assertEqual(selected["control_target_reason"], "startup_go2_target_match")
        self.assertTrue(selected["control_target_supported"])
        self.assertTrue(self.manager.snapshot()["lease"]["active"])
        self.assertFalse(self.manager.snapshot()["estop"]["latched"])

    def test_go2_ip_change_is_not_treated_as_control_bridge_retargeting(self):
        selected = self.agent.set_robot_target("192.168.123.162", "go2", "other-go2.local")
        self.assertTrue(selected["changed"])
        self.assertFalse(selected["target_matches_startup"])
        self.assertTrue(selected["restart_required"])
        self.assertFalse(selected["control_target_supported"])
        snapshot = self.agent.control_snapshot()
        self.assertFalse(snapshot["target_supported"])
        self.assertFalse(snapshot["target_matches_startup"])
        self.assertTrue(snapshot["restart_required"])
        with self.assertRaises(ControlDisabled):
            self.agent.control_acquire("4826", "keyboard")

    def test_generic_startup_can_never_enable_go2_control_by_runtime_selection(self):
        generic = RosAgent(
            robot_ip="10.100.0.89",
            profile_path=str(ROOT / "config" / "generic.json"),
        )
        generic._control_manager = self.manager
        selected = generic.set_robot_target("10.100.0.89", "go2", "go2-controller.local")
        self.assertTrue(selected["changed"])
        self.assertTrue(selected["restart_required"])
        self.assertFalse(selected["control_target_supported"])
        snapshot = generic.control_snapshot()
        self.assertFalse(snapshot["target_supported"])
        with self.assertRaises(ControlDisabled):
            generic.control_acquire("4826", "keyboard")

    def test_generic_observation_can_switch_turtlebot_and_so101_without_restart(self):
        generic = RosAgent(
            robot_ip="10.100.0.89",
            profile_path=str(ROOT / "config" / "generic.json"),
        )
        generic._control_manager = self.manager
        turtlebot = generic.set_robot_target(
            "10.100.0.42",
            "turtlebot",
            "turtlebot3.local",
        )
        self.assertTrue(turtlebot["changed"])
        self.assertFalse(turtlebot["restart_required"])
        self.assertFalse(turtlebot["control_restart_required"])
        self.assertFalse(turtlebot["control_target_supported"])
        self.assertFalse(self.manager.snapshot()["estop"]["latched"])

        so101 = generic.set_robot_target("10.100.0.43", "so-101", "so101-controller.local")
        self.assertTrue(so101["changed"])
        self.assertFalse(so101["restart_required"])
        self.assertFalse(so101["control_restart_required"])
        self.assertFalse(self.manager.snapshot()["estop"]["latched"])

    def test_generic_go2_selection_requires_restart_but_non_go2_selection_clears_overlay(self):
        generic = RosAgent(
            robot_ip="10.100.0.89",
            profile_path=str(ROOT / "config" / "generic.json"),
        )
        generic._control_manager = self.manager
        go2 = generic.set_robot_target("10.100.0.42", "go2", "go2-controller.local")
        self.assertTrue(go2["restart_required"])
        self.assertFalse(go2["control_target_supported"])
        turtlebot = generic.set_robot_target("10.100.0.43", "turtlebot", "turtlebot3.local")
        self.assertFalse(turtlebot["restart_required"])
        self.assertFalse(turtlebot["control_target_supported"])

    def test_explicit_non_go2_startup_profile_supports_live_observation_switch(self):
        turtlebot_agent = RosAgent(
            robot_ip="10.100.0.42",
            profile_path=str(ROOT / "config" / "turtlebot.json"),
        )
        turtlebot_agent._control_manager = self.manager
        self.assertEqual(turtlebot_agent.robot_target_snapshot()["robot_type"], "turtlebot")
        selected = turtlebot_agent.set_robot_target(
            "10.100.0.43",
            "so-101",
            "so101-controller.local",
        )
        self.assertFalse(selected["restart_required"])
        turtlebot_agent._network_cache = (float("inf"), False, None)
        health = turtlebot_agent.health_snapshot()
        self.assertEqual(health["runtime_profile"]["id"], "turtlebot")
        self.assertEqual(health["selected_profile"]["id"], "so-101")

    def test_health_keeps_actual_startup_profile_separate_from_selection(self):
        self.agent.set_robot_target("10.100.0.42", "turtlebot", "turtlebot3.local")
        self.agent._network_cache = (float("inf"), False, None)
        health = self.agent.health_snapshot()
        self.assertEqual(health["profile"], "Unitree Go2")
        self.assertEqual(health["runtime_profile"]["id"], "go2")
        self.assertEqual(health["selected_profile"]["id"], "turtlebot")

    def test_old_ping_result_cannot_poison_new_target_cache(self):
        started = threading.Event()
        release = threading.Event()
        result = []

        def delayed_ping(*args, **kwargs):
            started.set()
            release.wait(timeout=2.0)
            return types.SimpleNamespace(returncode=0)

        with patch("robot_dashboard.ros_agent.subprocess.run", side_effect=delayed_ping):
            worker = threading.Thread(target=lambda: result.append(self.agent._network_status()))
            worker.start()
            self.assertTrue(started.wait(timeout=1.0))
            self.agent.set_robot_target("10.100.0.42", "turtlebot", "turtlebot3.local")
            release.set()
            worker.join(timeout=2.0)

        self.assertEqual(result, [(False, None)])
        self.assertEqual(self.agent._network_cache, (0.0, False, None))


if __name__ == "__main__":
    unittest.main()
