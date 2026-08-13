import importlib.util
import importlib.machinery
import os
import sys
import types
import unittest
import time
from pathlib import Path
from unittest.mock import patch


if importlib.util.find_spec("rclpy") is None:
    class Dummy:
        pass

    rclpy = types.ModuleType("rclpy")
    rclpy.__spec__ = importlib.machinery.ModuleSpec("rclpy", loader=None)
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

from robot_dashboard.control import (
    CommandValidationError,
    ControlManager,
    ControlNotReady,
    LeaseBusy,
)
from robot_dashboard.control_protocol import ControlProtocolError
from robot_dashboard.ros_agent import (
    NAVIGATION_CLEAR_SERVICES,
    NAVIGATION_CONTROLLER_ODOM_TOPIC,
    NAVIGATION_FAST_LIO_ODOM_TOPIC,
    NAVIGATION_RUNTIME_HEALTH_TOPIC,
    NAVIGATION_ODOM_STAMP_MAX_AGE_S,
    NAVIGATION_ODOM_STAMP_MAX_FUTURE_S,
    RosAgent,
    _public_navigation_reason,
)


ROOT = Path(__file__).resolve().parents[1]


class ReadyClient:
    def server_is_ready(self):
        return False

    def service_is_ready(self):
        return False


class CountNode:
    def __init__(self, count=0):
        self.count = count

    def count_publishers(self, topic):
        return self.count


class FixedClockNode(CountNode):
    def __init__(self, now_ns, count=1):
        super().__init__(count)
        self.now_ns = now_ns

    def get_clock(self):
        now_ns = self.now_ns
        return types.SimpleNamespace(
            now=lambda: types.SimpleNamespace(nanoseconds=now_ns)
        )


class NavigationControlTests(unittest.TestCase):
    def manager(self):
        manager = ControlManager(
            {"name": "Unitree Go2", "control": {"enabled": True}},
            environ={"ROBOT_SCOPE_CONTROL_ENABLED": "1"},
            token_factory=lambda: "navigation-test-token-long-enough",
        )
        manager.set_readiness(bridge_ready=True, lowstate_ready=True)
        return manager

    @staticmethod
    def seed_prelocalization_ready(agent):
        now = time.monotonic()
        agent._navigation_runtime_health_received = now
        agent._navigation_runtime_health = {
            "ready": False,
            "cloud_fresh": True,
            "odom_fresh": True,
            "localized": False,
            "error": None,
        }
        agent._tick("/scan", now)
        agent._tick(NAVIGATION_FAST_LIO_ODOM_TOPIC, now)
        return now

    def test_internal_navigation_lease_does_not_widen_browser_sources(self):
        manager = self.manager()
        with self.assertRaises(CommandValidationError):
            manager.acquire_lease("navigation")
        acquired = manager.acquire_navigation_lease()
        self.assertEqual(acquired["lease"]["input_source"], "navigation")
        self.assertNotIn("navigation", manager.snapshot()["input_sources"])
        with self.assertRaises(LeaseBusy):
            manager.acquire_lease("keyboard")

    def test_bridge_status_requires_owned_publisher_and_trusted_bare_baseline(self):
        payload = {
            "type": "bridge_status",
            "ready": True,
            "sport_subscribers": 1,
            "sport_publishers": 10,
            "own_sport_publishers": 1,
            "foreign_named_sport_publishers": 0,
            "bare_unitree_sport_publishers": 9,
            "expected_bare_sport_publishers": 9,
            "lowstate_publishers": 1,
            "bridge_epoch": "e" * 32,
            "lowstate_age_ms": 10.0,
        }
        self.assertEqual(
            RosAgent._control_status_readiness(
                payload,
                lowstate_timeout_s=0.5,
                expected_bare_sport_publishers=9,
            )[:2],
            (True, True),
        )
        for field, value in (
            ("own_sport_publishers", 0),
            ("own_sport_publishers", 2),
            ("foreign_named_sport_publishers", 1),
            ("bare_unitree_sport_publishers", 8),
        ):
            candidate = dict(payload)
            candidate[field] = value
            candidate["sport_publishers"] = (
                candidate["own_sport_publishers"]
                + candidate["foreign_named_sport_publishers"]
                + candidate["bare_unitree_sport_publishers"]
            )
            self.assertFalse(
                RosAgent._control_status_readiness(
                    candidate,
                    lowstate_timeout_s=0.5,
                    expected_bare_sport_publishers=9,
                )[0]
            )

        for field in (
            "sport_publishers",
            "own_sport_publishers",
            "foreign_named_sport_publishers",
            "bare_unitree_sport_publishers",
            "expected_bare_sport_publishers",
        ):
            for invalid in (None, True, -1, 65):
                candidate = dict(payload)
                if invalid is None:
                    candidate.pop(field)
                else:
                    candidate[field] = invalid
                with self.assertRaises(ControlProtocolError):
                    RosAgent._control_status_readiness(
                        candidate,
                        lowstate_timeout_s=0.5,
                        expected_bare_sport_publishers=9,
                    )

        inconsistent = dict(payload, sport_publishers=9)
        with self.assertRaisesRegex(ControlProtocolError, "inconsistent"):
            RosAgent._control_status_readiness(
                inconsistent,
                lowstate_timeout_s=0.5,
                expected_bare_sport_publishers=9,
            )

        with self.assertRaisesRegex(ControlProtocolError, "does not match profile"):
            RosAgent._control_status_readiness(
                payload,
                lowstate_timeout_s=0.5,
                expected_bare_sport_publishers=8,
            )

    def test_navigation_reserves_same_lease_as_manual_control(self):
        with patch.dict(
            os.environ,
            {"ROBOT_SCOPE_CONTROL_ENABLED": "1"},
            clear=True,
        ):
            agent = RosAgent(
                robot_ip="192.168.123.161",
                profile_path=str(ROOT / "config" / "go2.json"),
            )
        manager = self.manager()
        agent._control_manager = manager
        agent._node = CountNode(1)
        agent._navigation_cmd_subscription = object()
        agent._navigation_health_subscriptions = {
            "/scan": object(),
            NAVIGATION_FAST_LIO_ODOM_TOPIC: object(),
            NAVIGATION_CONTROLLER_ODOM_TOPIC: object(),
            "/amcl_pose": object(),
            NAVIGATION_RUNTIME_HEALTH_TOPIC: object(),
        }
        agent._navigation_initial_pose_publisher = object()
        agent._navigation_pose_type = object()
        agent._navigation_action_type = object()
        agent._navigation_action_client = ReadyClient()
        agent._navigation_clear_service_type = object()
        agent._navigation_clear_clients = {
            service: ReadyClient() for service in NAVIGATION_CLEAR_SERVICES
        }
        ready_after = self.seed_prelocalization_ready(agent)

        result = agent.navigation_activate(
            map_id="opaque-map-id",
            map_revision="a" * 64,
            map_name="classroom",
            ready_after=ready_after,
        )
        self.assertTrue(result["active"])
        self.assertEqual(manager.snapshot()["lease"]["input_source"], "navigation")
        with self.assertRaises(LeaseBusy):
            agent.control_acquire("keyboard")

        stopped = agent.navigation_deactivate(reason="operator_stop")
        self.assertFalse(stopped["active"])
        self.assertFalse(manager.snapshot()["lease"]["active"])

    def test_pose_validation_is_finite_bounded_and_normalizes_yaw(self):
        x, y, yaw = RosAgent._navigation_pose_values(1.0, -2.0, 4.0)
        self.assertEqual((x, y), (1.0, -2.0))
        self.assertGreaterEqual(yaw, -3.141593)
        self.assertLessEqual(yaw, 3.141593)
        for values in ((float("nan"), 0, 0), (0, 10001, 0), (True, 0, 0)):
            with self.assertRaises(CommandValidationError):
                RosAgent._navigation_pose_values(*values)

    def test_active_goal_sensor_loss_revokes_navigation_before_drive(self):
        with patch.dict(os.environ, {"ROBOT_SCOPE_CONTROL_ENABLED": "1"}, clear=True):
            agent = RosAgent(
                robot_ip="192.168.123.161",
                profile_path=str(ROOT / "config" / "go2.json"),
            )
        manager = self.manager()
        agent._control_manager = manager
        agent._node = CountNode(1)
        agent._navigation_cmd_subscription = object()
        agent._navigation_health_subscriptions = {
            "/scan": object(),
            NAVIGATION_FAST_LIO_ODOM_TOPIC: object(),
            NAVIGATION_CONTROLLER_ODOM_TOPIC: object(),
            "/amcl_pose": object(),
            NAVIGATION_RUNTIME_HEALTH_TOPIC: object(),
        }
        agent._navigation_initial_pose_publisher = object()
        agent._navigation_pose_type = object()
        agent._navigation_action_type = object()
        agent._navigation_action_client = ReadyClient()
        agent._navigation_clear_service_type = object()
        agent._navigation_clear_clients = {
            service: ReadyClient() for service in NAVIGATION_CLEAR_SERVICES
        }
        ready_after = self.seed_prelocalization_ready(agent)
        agent.navigation_activate(
            map_id="map", map_revision="b" * 64, ready_after=ready_after
        )
        now = time.monotonic()
        agent._navigation_runtime_health_received = now
        agent._navigation_runtime_health = {
            "ready": True,
            "cloud_fresh": True,
            "odom_fresh": True,
            "localized": True,
            "error": None,
        }
        for topic in (
            NAVIGATION_FAST_LIO_ODOM_TOPIC,
            NAVIGATION_CONTROLLER_ODOM_TOPIC,
            "/amcl_pose",
        ):
            agent._tick(topic, now)
        # The scan is already outside the hard active-goal freshness window.
        agent._tick("/scan", now - 1.0)
        with agent._navigation_lock:
            agent._navigation["goal"] = {
                "state": "active",
                "goal_id": "goal-identifier-1234",
            }
        published = []
        agent._publish_control_outputs = lambda outputs, **_: published.extend(outputs)

        agent._control_tick()

        self.assertFalse(agent._navigation["active"])
        self.assertFalse(manager.snapshot()["lease"]["active"])
        self.assertTrue(any(item.get("type") == "stop" for item in published))

    def test_stale_prelocalization_never_acquires_navigation_lease(self):
        with patch.dict(os.environ, {"ROBOT_SCOPE_CONTROL_ENABLED": "1"}, clear=True):
            agent = RosAgent(
                robot_ip="192.168.123.161",
                profile_path=str(ROOT / "config" / "go2.json"),
            )
        manager = self.manager()
        agent._control_manager = manager
        agent._node = CountNode(1)
        agent._navigation_cmd_subscription = object()
        agent._navigation_health_subscriptions = {
            "/scan": object(),
            NAVIGATION_FAST_LIO_ODOM_TOPIC: object(),
            NAVIGATION_CONTROLLER_ODOM_TOPIC: object(),
            "/amcl_pose": object(),
            NAVIGATION_RUNTIME_HEALTH_TOPIC: object(),
        }
        agent._navigation_initial_pose_publisher = object()
        agent._navigation_pose_type = object()
        agent._navigation_action_type = object()
        agent._navigation_action_client = ReadyClient()
        agent._navigation_clear_service_type = object()
        agent._navigation_clear_clients = {
            service: ReadyClient() for service in NAVIGATION_CLEAR_SERVICES
        }

        with self.assertRaises(ControlNotReady):
            agent.navigation_activate(
                map_id="map",
                map_revision="c" * 64,
                ready_after=time.monotonic(),
            )

        self.assertFalse(manager.snapshot()["lease"]["active"])
        self.assertEqual(manager.drain_outputs(), [])

    def test_unarmed_runtime_cannot_submit_nonzero_velocity(self):
        agent = object.__new__(RosAgent)
        agent._control_operation_lock = __import__("threading").RLock()
        agent._navigation_lock = __import__("threading").RLock()
        agent._navigation = {
            "active": False,
            "goal": {"state": "active"},
        }
        agent._navigation_token = ""
        agent._navigation_binding = ""
        submissions = []
        agent._control_manager = types.SimpleNamespace(
            submit_drive=lambda *args, **kwargs: submissions.append((args, kwargs))
        )

        agent._navigation_submit_velocity(0.2, 0.0, 0.0)

        self.assertEqual(submissions, [])

    def test_idle_navigation_lease_is_revoked_when_prelocalization_stales(self):
        with patch.dict(os.environ, {"ROBOT_SCOPE_CONTROL_ENABLED": "1"}, clear=True):
            agent = RosAgent(
                robot_ip="192.168.123.161",
                profile_path=str(ROOT / "config" / "go2.json"),
            )
        manager = self.manager()
        agent._control_manager = manager
        agent._node = CountNode(1)
        agent._navigation_cmd_subscription = object()
        agent._navigation_health_subscriptions = {
            "/scan": object(),
            NAVIGATION_FAST_LIO_ODOM_TOPIC: object(),
            NAVIGATION_CONTROLLER_ODOM_TOPIC: object(),
            "/amcl_pose": object(),
            NAVIGATION_RUNTIME_HEALTH_TOPIC: object(),
        }
        agent._navigation_initial_pose_publisher = object()
        agent._navigation_pose_type = object()
        agent._navigation_action_type = object()
        agent._navigation_action_client = ReadyClient()
        agent._navigation_clear_service_type = object()
        agent._navigation_clear_clients = {
            service: ReadyClient() for service in NAVIGATION_CLEAR_SERVICES
        }
        ready_after = self.seed_prelocalization_ready(agent)
        agent.navigation_activate(
            map_id="map", map_revision="d" * 64, ready_after=ready_after
        )
        with agent._navigation_lock:
            agent._navigation_runtime_health_received = time.monotonic() - 2.0

        agent._control_tick()

        self.assertFalse(agent._navigation["active"])
        self.assertFalse(manager.snapshot()["lease"]["active"])
        self.assertEqual(
            agent._navigation["deactivation_reason"],
            "navigation runtime health is stale",
        )

    def test_public_deactivation_reason_is_bounded_and_redacts_secrets(self):
        reason = _public_navigation_reason(
            "heartbeat failed\n bridge_token=super-secret-value " + "x" * 300
        )
        self.assertLessEqual(len(reason), 160)
        self.assertNotIn("super-secret-value", reason)
        self.assertNotIn("\n", reason)
        self.assertIn("bridge_token=[redacted]", reason)

    def test_feedback_does_not_open_gate_before_goal_acceptance(self):
        agent = object.__new__(RosAgent)
        agent._navigation_lock = __import__("threading").RLock()
        agent._navigation_goal_generation = 7
        agent._navigation_goal_handle = None
        agent._navigation = {
            "seq": 0,
            "goal": {"state": "pending", "goal_id": "goal-identifier-1234"},
        }
        feedback = types.SimpleNamespace(
            feedback=types.SimpleNamespace(
                distance_remaining=1.0,
                navigation_time=None,
                number_of_recoveries=0,
            )
        )

        agent._navigation_feedback_callback(7, "goal-identifier-1234", feedback)

        self.assertEqual(agent._navigation["goal"]["state"], "pending")

    @staticmethod
    def odometry_message(stamp_ns):
        return types.SimpleNamespace(
            header=types.SimpleNamespace(
                stamp=types.SimpleNamespace(
                    sec=stamp_ns // 1_000_000_000,
                    nanosec=stamp_ns % 1_000_000_000,
                ),
                frame_id="odom",
            ),
            child_frame_id="base_link",
            pose=types.SimpleNamespace(
                pose=types.SimpleNamespace(
                    position=types.SimpleNamespace(x=0.0, y=0.0, z=0.0),
                    orientation=types.SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
                )
            ),
            twist=types.SimpleNamespace(
                twist=types.SimpleNamespace(
                    linear=types.SimpleNamespace(x=0.0, y=0.0),
                    angular=types.SimpleNamespace(z=0.0),
                )
            ),
        )

    def stamp_test_agent(self, now_ns, *, active=True):
        agent = object.__new__(RosAgent)
        agent._node = FixedClockNode(now_ns)
        agent._navigation_lock = __import__("threading").RLock()
        agent._navigation_odom_stamp_ns = {
            NAVIGATION_FAST_LIO_ODOM_TOPIC: 0,
            NAVIGATION_CONTROLLER_ODOM_TOPIC: 0,
        }
        agent._navigation = {"active": active}
        agent._tick_events = []
        agent._deactivation_events = []
        agent._tick = lambda topic, observed: agent._tick_events.append((topic, observed))
        agent.navigation_deactivate = (
            lambda reason: agent._deactivation_events.append(reason)
        )
        return agent

    def test_controller_odometry_requires_current_nondecreasing_header_stamp(self):
        now_ns = 10_000_000_000
        agent = self.stamp_test_agent(now_ns)
        first_stamp = now_ns - 100_000_000
        agent._navigation_health_callback(
            NAVIGATION_CONTROLLER_ODOM_TOPIC,
            self.odometry_message(first_stamp),
        )
        self.assertEqual(len(agent._tick_events), 1)
        self.assertEqual(agent._deactivation_events, [])

        # A reordered message cannot refresh the receipt-age gate and actively
        # closes navigation instead of waiting for the watchdog timeout.
        agent._navigation_health_callback(
            NAVIGATION_CONTROLLER_ODOM_TOPIC,
            self.odometry_message(first_stamp - 1),
        )
        self.assertEqual(len(agent._tick_events), 1)
        self.assertIn("moved backwards", agent._deactivation_events[-1])

    def test_odometry_stamp_rejects_zero_stale_and_future_samples(self):
        now_ns = 20_000_000_000
        invalid_stamps = (
            0,
            now_ns - int((NAVIGATION_ODOM_STAMP_MAX_AGE_S + 0.01) * 1_000_000_000),
            now_ns + int((NAVIGATION_ODOM_STAMP_MAX_FUTURE_S + 0.01) * 1_000_000_000),
        )
        for stamp_ns in invalid_stamps:
            with self.subTest(stamp_ns=stamp_ns):
                agent = self.stamp_test_agent(now_ns)
                agent._navigation_health_callback(
                    NAVIGATION_CONTROLLER_ODOM_TOPIC,
                    self.odometry_message(stamp_ns),
                )
                self.assertEqual(agent._tick_events, [])
                self.assertEqual(len(agent._deactivation_events), 1)


if __name__ == "__main__":
    unittest.main()
