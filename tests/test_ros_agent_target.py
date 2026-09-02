import importlib.util
import os
import struct
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


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

from robot_dashboard.capabilities import capabilities_for_robot_type
from robot_dashboard.control import ControlDisabled, ControlManager
from robot_dashboard.discovery import UnknownRobotType
from robot_dashboard.ros_agent import RateMeter, RosAgent, pointcloud_source_metadata
from robot_dashboard.ros.graph import RosGraphMonitor
from robot_dashboard.ros.runtime import RosRuntime


ROOT = Path(__file__).resolve().parents[1]


class JointSourceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.agent = object.__new__(RosAgent)
        self.agent._ros_runtime = RosRuntime()
        self.agent._lock = self.agent._ros_runtime.lock
        self.agent._graph_monitor = RosGraphMonitor(self.agent._lock)
        self.agent._graph = {
            "/lowstate": {
                "type": "unitree_go/msg/LowState",
                "publishers": 0,
            },
        }
        self.agent._metrics = {}

    def test_zero_publisher_lowstate_requires_recent_received_samples(self):
        self.assertEqual(self.agent._preferred_joint_source_locked(), "")

        meter = RateMeter()
        meter.tick(time.monotonic())
        self.agent._metrics["/lowstate"] = meter
        self.assertEqual(self.agent._preferred_joint_source_locked(), "/lowstate")

        meter.times.clear()
        meter.tick(time.monotonic() - 4.0)
        self.assertEqual(self.agent._preferred_joint_source_locked(), "")

    def test_publisher_backed_joint_state_still_wins_over_observed_lowstate(self):
        meter = RateMeter()
        meter.tick(time.monotonic())
        self.agent._metrics["/lowstate"] = meter
        self.agent._graph["/joint_states"] = {
            "type": "sensor_msgs/msg/JointState",
            "publishers": 1,
        }
        self.assertEqual(self.agent._preferred_joint_source_locked(), "/joint_states")


class RobotTargetSafetyTests(unittest.TestCase):
    def setUp(self):
        self.agent = RosAgent(
            robot_ip="192.168.123.161",
            profile_path=str(ROOT / "config" / "go2.json"),
        )
        profile = {"name": "Unitree Go2", "control": {"enabled": True}}
        environ = {
            "ROBOT_SCOPE_CONTROL_ENABLED": "true",
        }
        self.manager = ControlManager(
            profile,
            environ=environ,
            token_factory=lambda: "test-target-lease-token-long-enough",
        )
        self.manager.set_readiness(bridge_ready=True, lowstate_ready=True)
        self.agent._control_manager = self.manager

    def test_disconnect_is_idempotent_revokes_motion_and_clears_target_health(self):
        lease = self.agent.control_acquire("keyboard")["token"]
        self.agent.control_bind(lease, "target-disconnect-websocket")

        disconnected = self.agent.disconnect_robot_target()
        self.assertTrue(disconnected["changed"])
        self.assertFalse(disconnected["connected"])
        self.assertEqual(disconnected["ip"], "")
        self.assertEqual(disconnected["hostname"], "")
        self.assertTrue(disconnected["restart_required"])
        self.assertEqual(disconnected["control_target_reason"], "robot_target_disconnected")
        self.assertFalse(disconnected["control_target_supported"])
        self.assertFalse(self.manager.snapshot()["lease"]["active"])
        self.assertTrue(self.manager.snapshot()["estop"]["latched"])

        health = self.agent.health_snapshot()
        self.assertFalse(health["robot_target_connected"])
        self.assertFalse(health["robot_online"])
        self.assertEqual(health["robot_ip"], "")

        duplicate = self.agent.disconnect_robot_target()
        self.assertFalse(duplicate["changed"])

        reselected = self.agent.set_robot_target("192.168.123.161", "go2", "")
        self.assertTrue(reselected["connected"])
        self.assertTrue(reselected["changed"])
        self.assertTrue(reselected["restart_required"])
        self.assertFalse(reselected["control_target_supported"])

    def test_wireless_profile_exposes_onboard_gateway_without_weakening_control_target(self):
        agent = RosAgent(
            robot_ip="192.168.50.30",
            profile_path=str(ROOT / "config" / "go2.json"),
            navigation_profile="go2-xt16-wireless-competition-fastlio",
        )
        target = agent.robot_target_snapshot()
        health = agent.health_snapshot()
        self.assertEqual(target["connection_topology"], "onboard_gateway")
        self.assertEqual(health["connection_topology"], "onboard_gateway")
        self.assertEqual(target["ip"], "192.168.50.30")
        self.assertTrue(target["control_target_supported"])

    def test_target_change_revokes_lease_and_non_go2_blocks_all_enabling_mutators(self):
        lease = self.agent.control_acquire("keyboard")["token"]
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
            lambda: self.agent.control_acquire("keyboard"),
            lambda: self.agent.control_bind("invalid", "binding"),
            lambda: self.agent.control_heartbeat("invalid", "binding", 1),
            lambda: self.agent.control_drive("invalid", "binding", 1, vx=0, vy=0, wz=0),
            lambda: self.agent.control_action("invalid", "binding", 1, "hello", confirm=True),
            lambda: self.agent.control_clear_estop(confirm=True),
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
            self.agent.control_acquire("keyboard")

    def test_same_target_metadata_refresh_does_not_revoke_lease(self):
        lease = self.agent.control_acquire("keyboard")["token"]
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
            self.agent.control_acquire("keyboard")

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
            generic.control_acquire("keyboard")

    def test_generic_observation_can_switch_turtlebot_without_restart(self):
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

        with self.assertRaises(UnknownRobotType):
            generic.set_robot_target("10.100.0.43", "so-101", "arm-controller.local")

    def test_generic_go2_selection_requires_restart_but_non_go2_selection_clears_overlay(self):
        generic = RosAgent(
            robot_ip="10.100.0.89",
            profile_path=str(ROOT / "config" / "generic.json"),
        )
        generic._control_manager = self.manager
        go2 = generic.set_robot_target("10.100.0.42", "go2", "go2-controller.local")
        self.assertTrue(go2["restart_required"])
        self.assertFalse(go2["control_target_supported"])
        self.assertEqual(
            go2["runtime_capabilities"],
            capabilities_for_robot_type("generic"),
        )
        self.assertEqual(
            go2["profile"]["capabilities"],
            capabilities_for_robot_type("go2"),
        )
        turtlebot = generic.set_robot_target("10.100.0.43", "turtlebot", "turtlebot3.local")
        self.assertFalse(turtlebot["restart_required"])
        self.assertFalse(turtlebot["control_target_supported"])

    def test_explicit_non_go2_startup_profile_rejects_unsupported_live_target(self):
        turtlebot_agent = RosAgent(
            robot_ip="10.100.0.42",
            profile_path=str(ROOT / "config" / "turtlebot.json"),
        )
        turtlebot_agent._control_manager = self.manager
        self.assertEqual(turtlebot_agent.robot_target_snapshot()["robot_type"], "turtlebot")
        with self.assertRaises(UnknownRobotType):
            turtlebot_agent.set_robot_target("10.100.0.43", "so-101", "arm-controller.local")
        turtlebot_agent._network_cache = (float("inf"), False, None)
        health = turtlebot_agent.health_snapshot()
        self.assertEqual(health["runtime_profile"]["id"], "turtlebot")
        self.assertEqual(health["selected_profile"]["id"], "turtlebot")
        self.assertEqual(
            health["runtime_profile"]["capabilities"],
            capabilities_for_robot_type("turtlebot"),
        )
        self.assertEqual(
            health["selected_profile"]["capabilities"],
            capabilities_for_robot_type("turtlebot"),
        )

    def test_health_keeps_actual_startup_profile_separate_from_selection(self):
        self.agent.set_robot_target("10.100.0.42", "turtlebot", "turtlebot3.local")
        self.agent._network_cache = (float("inf"), False, None)
        health = self.agent.health_snapshot()
        self.assertEqual(health["profile"], "Unitree Go2")
        self.assertEqual(health["runtime_profile"]["id"], "go2")
        self.assertEqual(health["selected_profile"]["id"], "turtlebot")
        self.assertTrue(health["runtime_profile"]["capabilities"]["navigation"])
        self.assertFalse(health["selected_profile"]["capabilities"]["navigation"])
        target = self.agent.robot_target_snapshot()
        self.assertEqual(
            target["runtime_capabilities"],
            capabilities_for_robot_type("go2"),
        )
        self.assertEqual(
            target["profile"]["capabilities"],
            capabilities_for_robot_type("turtlebot"),
        )

    def test_health_keeps_ping_link_separate_from_missing_go2_dds_interface(self):
        self.agent._network_cache = (time.monotonic(), True, 1.2)
        with patch.dict(os.environ, {}, clear=True):
            health = self.agent.health_snapshot()
        self.assertTrue(health["robot_online"])
        self.assertFalse(health["ros_interface_ready"])
        self.assertTrue(health["ros_offline_viewer"])
        self.assertTrue(health["ros_transport"]["dedicated_interface_required"])

    def test_state_uses_only_fresh_signed_bridge_battery_when_direct_ros_is_absent(self):
        now = time.monotonic()
        self.agent._network_cache = (now, True, 1.0)
        with self.agent._control_transport.transport_lock:
            self.agent._control_transport.status_received = now
            self.agent._control_transport.status = {
                "authenticated": True,
                "lowstate_age_ms": 20.0,
                "telemetry": {
                    "battery": {
                        "battery_soc": 64,
                        "battery_current_ma": -700,
                        "power_v": 28.4,
                    }
                },
            }

        battery = [
            sensor
            for sensor in self.agent.state_snapshot()["sensors"]
            if sensor.get("values", {}).get("battery_soc") is not None
        ]
        self.assertEqual(len(battery), 1)
        self.assertEqual(
            battery[0]["topic"],
            "bridge://go2/lowstate/battery",
        )
        self.assertEqual(battery[0]["values"]["battery_soc"], 64)

        with self.agent._lock:
            self.agent._summaries["/lowstate"] = {
                "topic": "/lowstate",
                "type": "unitree_go/msg/LowState",
                "category": "robot_state",
                "values": {"battery_soc": 63},
            }
        battery = [
            sensor
            for sensor in self.agent.state_snapshot()["sensors"]
            if sensor.get("values", {}).get("battery_soc") is not None
        ]
        self.assertEqual(len(battery), 1)
        self.assertEqual(battery[0]["topic"], "/lowstate")

    def test_state_and_joint_stream_use_fresh_signed_bridge_joints_without_direct_dds(self):
        now = time.monotonic()
        positions = [0.0, 0.5, -1.2] * 4
        with self.agent._control_transport.transport_lock:
            self.agent._control_transport.status_received = now
            self.agent._control_transport.status = {
                "authenticated": True,
                "lowstate_age_ms": 20.0,
                "telemetry": {
                    "joints": {
                        "position_rad": positions,
                        "imu_rpy_rad": [0.01, -0.02, 0.03],
                        "seq": 77,
                    }
                },
            }

        state_joints = self.agent.state_snapshot()["robot_joints"]
        with self.agent._control_transport.transport_lock:
            self.agent._control_transport.status_received = time.monotonic()
        stream_joints = self.agent.joint_snapshot()
        for label, snapshot in (
            ("state", state_joints),
            ("stream", stream_joints),
        ):
            self.assertEqual(snapshot["state"], "ok", (label, snapshot))
            self.assertEqual(snapshot["seq"], 77)
            self.assertEqual(snapshot["position_rad"], positions)
            self.assertEqual(
                snapshot["topic"],
                "bridge://go2/lowstate/joints",
            )

    def test_direct_camera_is_exposed_without_mutating_ros_source_selection(self):
        sources = self.agent.sources_snapshot()
        self.assertEqual(
            sources["selected"]["camera"], "go2-camera://230.1.1.1:1720"
        )
        self.assertTrue(sources["locked"]["camera"])
        self.assertEqual(
            sources["options"]["camera"][0]["type"],
            "video/H264 (direct RTP multicast)",
        )
        waiting = self.agent.camera_snapshot()
        self.assertEqual(waiting["source"], "go2_multicast")
        self.assertEqual(waiting["topic"], "go2-camera://230.1.1.1:1720")
        self.assertEqual(waiting["state"], "waiting")

        self.agent._direct_camera._publish_jpeg(b"\xff\xd8frame\xff\xd9")
        camera = self.agent.camera_snapshot()
        self.assertEqual(camera["format"], "jpeg")
        self.assertEqual(camera["source"], "go2_multicast")
        self.assertEqual(camera["transport"], "udp_multicast_rtp_h264")
        self.assertEqual(camera["state"], "ok")
        self.agent._network_cache = (time.monotonic(), False, None)
        state = self.agent.state_snapshot()
        self.assertEqual(state["sources"]["camera"], "go2-camera://230.1.1.1:1720")
        self.assertEqual(
            self.agent.sources_snapshot()["selected"]["camera"],
            "go2-camera://230.1.1.1:1720",
        )

        with self.assertRaisesRegex(ValueError, "direct camera is active"):
            self.agent.set_sources({"camera": "/frontvideostream"})
        accepted = self.agent.set_sources(
            {"camera": "go2-camera://230.1.1.1:1720"}
        )
        self.assertTrue(accepted["locked"]["camera"])

    def test_direct_camera_errors_are_redacted_in_health_and_frame_metadata(self):
        private_path = "/private/robot-scope/camera-pipeline.log"
        private_secret = "camera-password-do-not-expose"
        with self.agent._direct_camera._lock:
            self.agent._direct_camera._last_error = (
                f"failed at {private_path} password={private_secret}"
            )
        private_status = self.agent._direct_camera.status()
        private_status["bridge_epoch"] = "camera-internal-generation"
        self.agent._network_cache = (time.monotonic(), False, None)

        with patch.object(
            self.agent._direct_camera,
            "status",
            return_value=private_status,
        ):
            projections = (
                self.agent.health_snapshot()["direct_camera"],
                self.agent.camera_snapshot()["direct_camera"],
            )
        for projection in projections:
            rendered = str(projection.get("last_error", ""))
            self.assertTrue(rendered)
            self.assertNotIn(private_path, rendered)
            self.assertNotIn(private_secret, rendered)
            self.assertNotIn("bridge_epoch", projection)

    def test_direct_camera_accepts_exact_trusted_go2_host_interface(self):
        with patch.dict(
            os.environ,
            {
                "ROBOT_SCOPE_GO2_INTERFACE": "enp4s0",
                "ROBOT_SCOPE_CAMERA_INTERFACE": "enp4s0",
            },
            clear=False,
        ):
            agent = RosAgent(
                robot_ip="192.168.123.161",
                profile_path=str(ROOT / "config" / "go2.json"),
            )
        self.assertEqual(agent._direct_camera.interface, "enp4s0")
        self.assertIn("enp4s0", agent._direct_camera.allowed_interfaces)
        self.assertTrue(agent._direct_camera.configured)

    def test_direct_camera_exclusively_ignores_legacy_ros_camera_callbacks(self):
        self.agent._direct_camera._publish_jpeg(b"\xff\xd8direct\xff\xd9")
        before = self.agent.camera_snapshot()
        ros_message = types.SimpleNamespace(format="jpeg", data=b"legacy")

        self.agent._camera_callback(
            "/frontvideostream",
            "sensor_msgs/msg/CompressedImage",
            ros_message,
        )
        self.agent._decoded_camera_callback(b"\xff\xd8legacy\xff\xd9")

        after = self.agent.camera_snapshot()
        self.assertEqual(after["seq"], before["seq"])
        self.assertEqual(after["data"], before["data"])
        self.assertEqual(after["source"], "go2_multicast")
        self.assertEqual(self.agent._metrics["/frontvideostream"].samples, 1)

    def test_direct_camera_runs_only_between_first_open_and_last_close(self):
        self.agent._direct_camera.start = Mock(return_value=True)
        self.agent._direct_camera.stop = Mock()
        self.agent._camera_accepting_demand = True
        with self.agent._lock:
            self.agent._camera["data"] = b"stale-jpeg"
            self.agent._camera["format"] = "jpeg"

        first = self.agent.camera_stream_open()
        self.assertEqual(first["consumers"], 1)
        self.assertEqual(self.agent.camera_snapshot()["data"], b"")
        second = self.agent.camera_stream_open()
        self.assertEqual(second["consumers"], 2)
        self.agent._direct_camera.start.assert_called_once_with()

        self.assertEqual(
            self.agent.camera_stream_close("go2_front", first["token"])["consumers"],
            1,
        )
        self.agent._direct_camera.stop.assert_not_called()
        self.assertEqual(
            self.agent.camera_stream_close("go2_front", second["token"])["consumers"],
            0,
        )
        self.agent._direct_camera.stop.assert_called_once_with()

        # Duplicate disconnects are idempotent, and shutdown rejects new work.
        duplicate = self.agent.camera_stream_close("go2_front", second["token"])
        self.assertEqual(duplicate["consumers"], 0)
        self.assertFalse(duplicate["released"])
        self.agent._direct_camera.stop.assert_called_once_with()
        self.agent._camera_accepting_demand = False
        self.assertFalse(self.agent.camera_stream_open()["accepted"])

    def test_camera_catalog_and_frames_are_isolated_per_fixed_source(self):
        catalog = self.agent.cameras_snapshot()
        self.assertEqual(catalog["max_active"], 2)
        self.assertEqual(
            [source["source_id"] for source in catalog["sources"]],
            ["go2_front", "realsense_color"],
        )
        self.assertTrue(catalog["sources"][0]["configured"])
        self.assertTrue(catalog["sources"][1]["configured"])
        self.assertEqual(
            catalog["sources"][0]["topic"], "go2-camera://230.1.1.1:1720"
        )
        self.assertEqual(
            catalog["sources"][1]["topic"],
            "http://192.168.123.18:8090/stream",
        )
        self.assertEqual(catalog["sources"][0]["width"], 1280)
        self.assertEqual(catalog["sources"][0]["height"], 720)

        self.agent._direct_camera._publish_jpeg(b"\xff\xd8go2\xff\xd9")
        self.agent._remote_camera._publish_jpeg(b"\xff\xd8rs\xff\xd9")
        go2 = self.agent.camera_snapshot("go2_front")
        realsense = self.agent.camera_snapshot("realsense_color")
        self.assertEqual(go2["data"], b"\xff\xd8go2\xff\xd9")
        self.assertEqual(realsense["data"], b"\xff\xd8rs\xff\xd9")
        self.assertEqual(go2["source_id"], "go2_front")
        self.assertEqual(realsense["source_id"], "realsense_color")
        self.assertNotEqual(go2["stream_id"], realsense["stream_id"])

        paired = self.agent.camera_snapshots(("go2_front", "realsense_color"))
        self.assertEqual(set(paired), {"go2_front", "realsense_color"})
        self.assertEqual(paired["go2_front"]["data"], b"\xff\xd8go2\xff\xd9")
        self.assertEqual(
            paired["realsense_color"]["data"], b"\xff\xd8rs\xff\xd9"
        )
        with self.assertRaises(ValueError):
            self.agent.camera_snapshots(("go2_front", "go2_front"))
        with self.assertRaises(ValueError):
            self.agent.camera_snapshots(("http://attacker.invalid/camera",))

    def test_realsense_relay_host_override_does_not_change_go2_target(self):
        with patch.dict(
            os.environ,
            {"ROBOT_SCOPE_REALSENSE_RELAY_HOST": "192.168.50.103"},
        ):
            agent = RosAgent(
                robot_ip="192.168.123.161",
                profile_path=str(ROOT / "config" / "go2.json"),
            )
        self.assertEqual(agent.robot_target_snapshot()["ip"], "192.168.123.161")
        self.assertEqual(
            agent._remote_camera.url,
            "http://192.168.50.103:8090/stream",
        )
        self.assertEqual(agent._remote_camera.relay_host, "192.168.50.103")
        self.assertTrue(agent._remote_camera.configured)

    def test_realsense_relay_port_override_is_exact_and_invalid_values_fail_closed(self):
        with patch.dict(
            os.environ,
            {
                "ROBOT_SCOPE_REALSENSE_RELAY_HOST": "192.168.50.30",
                "ROBOT_SCOPE_REALSENSE_PORT": "18090",
            },
        ):
            configured = RosAgent(
                robot_ip="192.168.123.161",
                profile_path=str(ROOT / "config" / "go2.json"),
            )
        self.assertEqual(
            configured._remote_camera.url,
            "http://192.168.50.30:18090/stream",
        )
        self.assertTrue(configured._remote_camera.configured)

        with patch.dict(
            os.environ,
            {
                "ROBOT_SCOPE_REALSENSE_RELAY_HOST": "192.168.50.30",
                "ROBOT_SCOPE_REALSENSE_PORT": "",
            },
        ):
            rejected = RosAgent(
                robot_ip="192.168.123.161",
                profile_path=str(ROOT / "config" / "go2.json"),
            )
        self.assertFalse(rejected._remote_camera.configured)
        self.assertIn(
            "allowlisted explicit port",
            rejected._remote_camera.status()["last_error"],
        )

        with patch.dict(
            os.environ,
            {"ROBOT_SCOPE_REALSENSE_RELAY_HOST": ""},
        ):
            blank_host = RosAgent(
                robot_ip="192.168.123.161",
                profile_path=str(ROOT / "config" / "go2.json"),
            )
        self.assertFalse(blank_host._remote_camera.configured)

    def test_camera_tokens_are_source_bound_exactly_once_and_capped(self):
        self.agent._direct_camera.start = Mock(return_value=True)
        self.agent._direct_camera.stop = Mock()
        self.agent._remote_camera.start = Mock(return_value=True)
        self.agent._remote_camera.stop = Mock()
        self.agent._camera_accepting_demand = True
        opens = [self.agent.camera_stream_open("go2_front") for _ in range(4)]
        limited = self.agent.camera_stream_open("go2_front")
        remote = self.agent.camera_stream_open("realsense_color")
        self.assertTrue(all(opened["accepted"] for opened in opens))
        self.assertFalse(limited["accepted"])
        self.assertEqual(limited["reason"], "camera_source_viewer_limit_reached")
        self.assertTrue(remote["accepted"])

        token = opens[0]["token"]
        wrong_source = self.agent.camera_stream_close("realsense_color", token)
        self.assertFalse(wrong_source["released"])
        released = self.agent.camera_stream_close("go2_front", token)
        self.assertTrue(released["released"])
        duplicate = self.agent.camera_stream_close("go2_front", token)
        self.assertFalse(duplicate["released"])

    def test_pointcloud_source_identity_uses_only_fixed_vendor_topic_rules(self):
        cases = {
            "/utlidar/cloud": ("go2_builtin_lidar", "raw"),
            "/utlidar/cloud_deskewed": ("go2_builtin_lidar", "deskewed"),
            "/utlidar/cloud_base": ("go2_builtin_lidar", "base_frame"),
            "/utlidar/grid_map": ("go2_builtin_lidar", "local_map"),
            "/utlidar/height_map": ("go2_builtin_lidar", "height_map"),
            "/utlidar/range_map": ("go2_builtin_lidar", "range_map"),
            "/utlidar/voxel_map": ("go2_builtin_lidar", "voxel_map"),
            "/uslam/cloud_map": ("go2_builtin_lidar", "map"),
            "/lidar_points": ("hesai_xt16", "raw"),
            "/velodyne_points": ("hesai_xt16", "converted"),
            "/cloud_registered": ("hesai_xt16", "registered"),
            "/Laser_map": ("hesai_xt16", "map"),
            "/utlidar/vendor_extension": ("generic_pointcloud", "unknown"),
            "/uslam/vendor_extension": ("generic_pointcloud", "unknown"),
            "/utlidar_fake/cloud": ("generic_pointcloud", "unknown"),
            "/laser_map": ("generic_pointcloud", "unknown"),
            "/camera/depth/points": ("generic_pointcloud", "unknown"),
        }
        for topic, expected in cases.items():
            with self.subTest(topic=topic):
                metadata = pointcloud_source_metadata(topic)
                self.assertEqual(
                    (metadata["sensor_id"], metadata["pipeline_stage"]),
                    expected,
                )
                self.assertIn(topic, metadata["display_label"])
                self.assertTrue(metadata["sensor_label"])
                self.assertTrue(metadata["pipeline_stage_label"])

    def test_pointcloud_source_options_expose_publisher_and_sample_state(self):
        point_type = "sensor_msgs/msg/PointCloud2"
        with self.agent._lock:
            self.agent._graph = {
                "/cloud_registered": {
                    "name": "/cloud_registered",
                    "type": point_type,
                    "category": "pointcloud",
                    "publishers": 2,
                },
                "/utlidar/cloud": {
                    "name": "/utlidar/cloud",
                    "type": point_type,
                    "category": "pointcloud",
                    "publishers": 1,
                },
                "/custom_cloud": {
                    "name": "/custom_cloud",
                    "type": point_type,
                    "category": "pointcloud",
                    "publishers": 1,
                },
                "/offline_cloud": {
                    "name": "/offline_cloud",
                    "type": point_type,
                    "category": "pointcloud",
                    "publishers": 0,
                },
            }
            self.agent._sources["pointcloud"] = "/cloud_registered"
            live_meter = RateMeter()
            live_meter.tick(time.monotonic() - 0.05)
            live_meter.tick(time.monotonic())
            stale_meter = RateMeter()
            stale_meter.tick(time.monotonic() - 8.0)
            self.agent._metrics = {
                "/cloud_registered": live_meter,
                "/custom_cloud": stale_meter,
            }

        sources = self.agent.sources_snapshot()
        options = {
            descriptor["topic"]: descriptor
            for descriptor in sources["options"]["pointcloud"]
        }
        self.assertEqual(
            set(options),
            {"/cloud_registered", "/utlidar/cloud", "/custom_cloud"},
        )

        selected = sources["selected_descriptors"]["pointcloud"]
        self.assertEqual(sources["selected"]["pointcloud"], "/cloud_registered")
        self.assertEqual(selected, options["/cloud_registered"])
        self.assertEqual(selected["type"], point_type)
        self.assertEqual(selected["sensor_id"], "hesai_xt16")
        self.assertEqual(selected["pipeline_stage"], "registered")
        self.assertEqual(selected["publishers"], 2)
        self.assertEqual(selected["samples"], 2)
        self.assertTrue(selected["available"])
        self.assertTrue(selected["live"])
        self.assertEqual(selected["state"], "ok")
        self.assertEqual(selected["sample_state"], "ok")
        self.assertIsNotNone(selected["hz"])

        onboard = options["/utlidar/cloud"]
        self.assertEqual(onboard["sensor_id"], "go2_builtin_lidar")
        self.assertTrue(onboard["available"])
        self.assertFalse(onboard["live"])
        self.assertEqual(onboard["state"], "waiting")

        generic = options["/custom_cloud"]
        self.assertEqual(generic["sensor_id"], "generic_pointcloud")
        self.assertEqual(generic["publishers"], 1)
        self.assertEqual(generic["samples"], 1)
        self.assertTrue(generic["available"])
        self.assertFalse(generic["live"])
        self.assertEqual(generic["state"], "stale")

        # Publisher-free graph entries remain unavailable for selection, but an
        # already selected descriptor still reports the real offline state.
        with self.agent._lock:
            self.agent._sources["pointcloud"] = "/offline_cloud"
        offline_sources = self.agent.sources_snapshot()
        offline = offline_sources["selected_descriptors"]["pointcloud"]
        self.assertNotIn(
            "/offline_cloud",
            {item["topic"] for item in offline_sources["options"]["pointcloud"]},
        )
        self.assertEqual(offline["type"], point_type)
        self.assertFalse(offline["available"])
        self.assertFalse(offline["live"])
        self.assertEqual(offline["publishers"], 0)
        self.assertEqual(offline["samples"], 0)
        self.assertEqual(offline["state"], "waiting")

        topics = {item["name"]: item for item in self.agent.topics_snapshot()}
        self.assertEqual(topics["/cloud_registered"]["sensor_id"], "hesai_xt16")
        self.assertEqual(topics["/cloud_registered"]["pipeline_stage"], "registered")
        self.assertEqual(topics["/custom_cloud"]["sensor_id"], "generic_pointcloud")
        self.assertEqual(topics["/custom_cloud"]["pipeline_stage"], "unknown")

    def test_pointcloud_stream_epoch_and_bandwidth_budget_are_bounded(self):
        with self.agent._lock:
            self.agent._cloud.update(
                {
                    "seq": 9,
                    "topic": "/velodyne_points",
                    "points_bytes": struct.pack("<3f", 1.0, 2.0, 3.0),
                    "sent_points": 1,
                }
            )
        binary = self.agent.pointcloud_binary_snapshot()
        legacy = self.agent.pointcloud_snapshot()
        self.assertTrue(binary["stream_id"])
        self.assertEqual(binary["stream_id"], legacy["stream_id"])
        self.assertEqual(legacy["points"], [1.0, 2.0, 3.0])
        self.assertEqual(binary["sensor_id"], "hesai_xt16")
        self.assertEqual(binary["pipeline_stage"], "converted")
        self.assertEqual(legacy["sensor_id"], "hesai_xt16")
        state = self.agent.state_snapshot()
        self.assertEqual(state["cloud"]["sensor_id"], "hesai_xt16")
        self.assertAlmostEqual(self.agent._pointcloud_frame_interval(30_000), 0.18)
        self.assertAlmostEqual(self.agent._pointcloud_frame_interval(100_000), 0.3)
        self.assertAlmostEqual(self.agent._pointcloud_frame_interval(None), 3.0)

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
