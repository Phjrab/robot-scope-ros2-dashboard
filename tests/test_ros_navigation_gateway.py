import math
import threading
import time
import unittest
from pathlib import Path

from robot_dashboard.control import CommandValidationError
from robot_dashboard.ros.navigation_gateway import (
    NAVIGATION_ACTION,
    NAVIGATION_CLEAR_SERVICES,
    NAVIGATION_CMD_VEL_TOPIC,
    NAVIGATION_CONTROLLER_ODOM_TOPIC,
    NAVIGATION_FAST_LIO_ODOM_TOPIC,
    NAVIGATION_INITIAL_POSE_TOPIC,
    NAVIGATION_LOCALIZATION_POSE_TOPIC,
    NAVIGATION_RUNTIME_HEALTH_TOPIC,
    NavigationRosGateway,
    public_navigation_reason,
)


ROOT = Path(__file__).resolve().parents[1]


class StubManager:
    def __init__(self, events=None):
        self.events = events if events is not None else []
        self.submissions = []
        self._snapshot = {
            "configured": True,
            "closed": False,
            "ready": True,
            "estop": {"latched": False},
            "action_guard": {"active": False},
            "lease": {"active": False, "input_source": None},
            "limits": {"vx_mps": 0.30, "vy_mps": 0.20, "wz_rps": 0.50},
        }

    def snapshot(self):
        return {
            **self._snapshot,
            "estop": dict(self._snapshot["estop"]),
            "action_guard": dict(self._snapshot["action_guard"]),
            "lease": dict(self._snapshot["lease"]),
            "limits": dict(self._snapshot["limits"]),
        }

    def acquire_navigation_lease(self):
        self._snapshot["lease"] = {
            "active": True,
            "input_source": "navigation",
        }
        return {"token": "navigation-test-token-long-enough"}

    def bind_lease(self, token, binding):
        del token, binding
        return self.snapshot()

    def release_lease(self, token, binding=None):
        del token, binding
        self.events.append("release")
        self._snapshot["lease"] = {"active": False, "input_source": None}
        return self.snapshot()

    def heartbeat(self, token, binding, sequence):
        del token, binding, sequence
        self.events.append("heartbeat")
        return self.snapshot()

    def submit_drive(self, *args, **kwargs):
        self.submissions.append((args, kwargs))
        return self.snapshot()


class StubControlPort:
    def __init__(self, events=None):
        self.events = events if events is not None else []
        self.manager = StubManager(self.events)
        self.operation_lock = threading.RLock()
        self.published = []

    def flush_outputs(self):
        self.events.append("flush")

    def publish_outputs(self, outputs):
        self.events.append("publish")
        self.published.extend(outputs)

    def ensure_target(self):
        return None

    def go2_target(self):
        return True


class CountNode:
    def __init__(self, count=1):
        self.count = count

    def count_publishers(self, topic):
        del topic
        return self.count


def gateway(*, port=None, node=None, ticks=None):
    control_port = port if port is not None else StubControlPort()
    count_node = node if node is not None else CountNode()
    tick_events = ticks if ticks is not None else []
    return NavigationRosGateway(
        control_port,
        node_getter=lambda: count_node,
        tick=lambda topic, observed: tick_events.append((topic, observed)),
        graph_getter=lambda: {},
    )


class NavigationRosGatewayTests(unittest.TestCase):
    def test_instances_own_independent_navigation_state(self):
        first = gateway()
        second = gateway()

        self.assertIsNot(first.lock, second.lock)
        self.assertIsNot(first.state, second.state)
        self.assertIsNot(first.validated_receipts, second.validated_receipts)
        first.state["active"] = True
        first.validated_receipts["/scan"] = 12.0

        self.assertFalse(second.state["active"])
        self.assertEqual(second.validated_receipts["/scan"], 0.0)

    def test_pose_and_public_reason_bounds_are_preserved(self):
        x, y, yaw = NavigationRosGateway.pose_values(1.0, -2.0, 4.0)
        self.assertEqual((x, y), (1.0, -2.0))
        self.assertGreaterEqual(yaw, -math.pi)
        self.assertLessEqual(yaw, math.pi)
        for values in ((float("nan"), 0, 0), (0, 10001, 0), (True, 0, 0)):
            with self.subTest(values=values):
                with self.assertRaises(CommandValidationError):
                    NavigationRosGateway.pose_values(*values)

        reason = public_navigation_reason(
            "heartbeat failed\n bridge_token=super-secret-value " + "x" * 300
        )
        self.assertLessEqual(len(reason), 160)
        self.assertNotIn("super-secret-value", reason)
        self.assertNotIn("\n", reason)
        self.assertIn("bridge_token=[redacted]", reason)

    def test_fixed_navigation_ros_bindings_are_not_caller_selected(self):
        self.assertEqual(NAVIGATION_CMD_VEL_TOPIC, "/robot_scope/nav/cmd_vel_raw")
        self.assertEqual(NAVIGATION_INITIAL_POSE_TOPIC, "/initialpose")
        self.assertEqual(NAVIGATION_LOCALIZATION_POSE_TOPIC, "/amcl_pose")
        self.assertEqual(
            NAVIGATION_RUNTIME_HEALTH_TOPIC,
            "/robot_scope/nav/runtime_health",
        )
        self.assertEqual(NAVIGATION_FAST_LIO_ODOM_TOPIC, "/Odometry")
        self.assertEqual(NAVIGATION_CONTROLLER_ODOM_TOPIC, "/utlidar/robot_odom")
        self.assertEqual(NAVIGATION_ACTION, "/navigate_to_pose")
        self.assertEqual(
            NAVIGATION_CLEAR_SERVICES,
            (
                "/global_costmap/clear_entirely_global_costmap",
                "/local_costmap/clear_entirely_local_costmap",
            ),
        )

    def test_unarmed_gateway_cannot_submit_nonzero_velocity(self):
        port = StubControlPort()
        navigation = gateway(port=port)

        navigation.submit_velocity(0.2, 0.0, 0.0)

        self.assertEqual(port.manager.submissions, [])
        self.assertEqual(port.published, [])
        self.assertEqual(port.events, [])

    def test_ui_metric_ticks_cannot_open_validated_freshness_gate(self):
        ticks = []
        navigation = gateway(ticks=ticks)
        now = time.monotonic()
        navigation._navigation_runtime_health_received = now
        navigation._navigation_runtime_health = {
            "ready": True,
            "cloud_fresh": True,
            "odom_fresh": True,
            "localized": True,
            "error": None,
        }

        # An observability producer can record every UI metric and still has no
        # authority to mutate the navigation-owned validated receipts.
        for topic in navigation.validated_receipts:
            ticks.append((topic, now))

        self.assertEqual(
            navigation._navigation_sensor_interlock_reason(
                now,
                require_localized=True,
            ),
            "navigation input /scan is stale",
        )
        self.assertTrue(
            all(received == 0.0 for received in navigation.validated_receipts.values())
        )

    def test_deactivation_flushes_stop_before_async_goal_cancel(self):
        events = []
        port = StubControlPort(events)
        navigation = gateway(port=port)

        class GoalHandle:
            def cancel_goal_async(self):
                events.append("cancel")

        navigation._navigation_token = "navigation-test-token-long-enough"
        navigation._navigation_binding = "navigation-binding"
        navigation._navigation_goal_handle = GoalHandle()
        navigation.state.update(
            active=True,
            state="armed",
            goal={"state": "active", "goal_id": "g" * 32},
        )
        port.manager._snapshot["lease"] = {
            "active": True,
            "input_source": "navigation",
        }

        navigation.deactivate("operator_stop")

        self.assertLess(events.index("release"), events.index("flush"))
        self.assertLess(events.index("flush"), events.index("cancel"))
        self.assertFalse(navigation.state["active"])
        self.assertFalse(port.manager.snapshot()["lease"]["active"])

    def test_gateway_has_no_application_or_process_manager_dependency(self):
        source = (
            ROOT / "robot_dashboard" / "ros" / "navigation_gateway.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "fastapi",
            "from ..app",
            "navigation_jobs",
            "mapping_jobs",
            "saved_maps",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
