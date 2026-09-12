"""Offline timing replay with the real gateway and control manager.

ROS inputs and time are synthetic; control outputs stay in an in-memory list.
No ROS runtime, socket, robot service or physical movement is involved.
"""

import json
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from robot_dashboard.control import ControlManager
from robot_dashboard.ros.navigation_gateway import NavigationRosGateway


class ReplayClock:
    def __init__(self):
        self.now = 10.0

    def __call__(self):
        return self.now


class ReplayLock:
    """Model one lock acquisition delay without threads or wall-clock sleeps."""

    def __init__(self, clock):
        self.clock = clock
        self.delay = 0.0
        self.lock = threading.RLock()

    def __enter__(self):
        self.lock.acquire()
        self.clock.now += self.delay
        self.delay = 0.0
        return self

    def __exit__(self, *args):
        self.lock.release()


class NavigationCommandTimingTests(unittest.TestCase):
    timeout_s = 0.30
    expected_speed = 0.035

    def make_profile(self):
        return {"control": {"enabled": True}}

    def setUp(self):
        self.clock = ReplayClock()
        patcher = mock.patch(
            "robot_dashboard.ros.navigation_gateway.time.monotonic", self.clock,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.manager = ControlManager(
            self.make_profile(),
            environ={"ROBOT_SCOPE_CONTROL_ENABLED": "true"},
            clock=self.clock,
            token_factory=lambda: "offline-navigation-token",
        )
        self.manager.set_readiness(bridge_ready=True, lowstate_ready=True)
        self.assertEqual(
            self.manager.snapshot()["limits"]["navigation_command_timeout_s"],
            self.timeout_s,
        )
        token = self.manager.acquire_navigation_lease()["token"]
        self.manager.bind_lease(token, "offline-binding")
        self.outputs = []
        self.cancel_output_counts = []
        self.scan_check_delay = 0.0
        self.operation_lock = ReplayLock(self.clock)
        port = SimpleNamespace(
            manager=self.manager,
            operation_lock=self.operation_lock,
            flush_outputs=lambda: self.outputs.extend(self.manager.drain_outputs()),
            publish_outputs=self.outputs.extend,
            ensure_target=lambda: None,
            go2_target=lambda: True,
        )
        node = SimpleNamespace(count_publishers=self.count_publishers)
        self.navigation = NavigationRosGateway(
            port, node_getter=lambda: node,
            tick=lambda *args: None, graph_getter=lambda: {},
        )
        self.navigation._navigation_token = token
        self.navigation._navigation_binding = "offline-binding"
        self.navigation._navigation_last_heartbeat = self.clock()
        self.navigation.state.update(
            active=True,
            state="armed",
            localization={"state": "localized"},
            goal={"state": "active", "goal_id": "a" * 32},
        )
        self.navigation._navigation_goal_handle = SimpleNamespace(
            cancel_goal_async=lambda: self.cancel_output_counts.append(len(self.outputs)),
        )
        self.message = SimpleNamespace(
            linear=SimpleNamespace(x=0.10, y=0.0),
            angular=SimpleNamespace(z=0.0),
        )
        self.refresh_inputs()

    def count_publishers(self, topic):
        if topic == "/scan":
            self.clock.now += self.scan_check_delay
            self.scan_check_delay = 0.0
        return 1

    def refresh_inputs(self):
        self.manager.set_readiness(bridge_ready=True, lowstate_ready=True)
        self.navigation._navigation_runtime_health_received = self.clock()
        self.navigation._navigation_runtime_health.update(
            ready=True, cloud_fresh=True, odom_fresh=True, localized=True,
        )
        for topic in self.navigation._navigation_validated_receipts:
            self.navigation._navigation_validated_receipts[topic] = self.clock()

    def command(self):
        self.navigation._navigation_cmd_vel_callback(self.message)

    def tick(self):
        self.outputs.extend(self.manager.tick())

    def test_ten_hz_commands_with_20_hz_ticks_remain_armed_for_five_seconds(self):
        # Match the transport's 50 ms timer and Nav2's 100 ms command period.
        for step in range(101):
            self.clock.now = 10.0 + step * 0.05
            self.refresh_inputs()
            if step % 2 == 0:
                self.command()
            self.assertIsNone(self.navigation.keepalive_locked(self.clock()))
            self.tick()
            self.assertTrue(self.manager.snapshot()["lease"]["active"])
        drives = [entry for entry in self.outputs if entry["type"] == "drive"]
        self.assertEqual(len(drives), 101)
        self.assertAlmostEqual(drives[-1]["velocity"]["vx"], self.expected_speed)
        self.assertTrue(all(0.0 <= item["velocity"]["vx"] <= self.expected_speed for item in drives))
        self.assertEqual(self.navigation.state["goal"]["state"], "active")
        self.assertEqual(self.cancel_output_counts, [])

    def test_command_arriving_just_under_timeout_is_accepted(self):
        self.command()
        self.tick()
        self.clock.now += self.timeout_s - 0.000001
        self.refresh_inputs()
        self.command()
        self.tick()
        self.assertTrue(self.manager.snapshot()["lease"]["active"])
        self.assertEqual(self.outputs[-1]["type"], "drive")
        self.assertEqual(self.cancel_output_counts, [])

    def exercise_expiry(
        self, *, arrival_gap, lock_delay=0.0, scan_delay=0.0, expire_with_tick=False,
    ):
        self.command()
        self.tick()
        cutoff = len(self.outputs)
        self.clock.now += arrival_gap
        self.refresh_inputs()
        if expire_with_tick:
            self.tick()
            self.assertFalse(self.manager.snapshot()["lease"]["active"])
        self.operation_lock.delay = lock_delay
        self.scan_check_delay = scan_delay
        with self.assertLogs("robot_dashboard.ros.navigation_gateway", level="WARNING") as logs:
            self.command()
        self.assertFalse(self.manager.snapshot()["lease"]["active"])
        self.assertFalse(self.navigation.state["active"])
        self.assertEqual(self.navigation.state["goal"]["state"], "canceled")
        self.assertIn("command_timeout", self.navigation.state["goal"]["error"])
        self.assertTrue(self.outputs[cutoff:])
        self.assertTrue(all(item["type"] == "stop" for item in self.outputs[cutoff:]))
        self.assertEqual(self.cancel_output_counts, [len(self.outputs)])
        self.assertGreater(self.cancel_output_counts[0], cutoff)
        # A fresh later callback must not resume the canceled generation.
        self.clock.now += 0.1
        self.refresh_inputs()
        self.command()
        self.tick()
        self.assertFalse(self.manager.snapshot()["lease"]["active"])
        self.assertTrue(all(item["type"] == "stop" for item in self.outputs[cutoff:]))
        return " ".join(logs.output)

    def test_input_gap_over_timeout_by_one_ms_cancels_before_new_drive(self):
        text = self.exercise_expiry(arrival_gap=self.timeout_s + 0.001)
        self.assertIn("lock_wait_s=0.000000 processing_s=0.000000", text)
        self.assertIn(f"previous_submit_age_s={self.timeout_s + 0.001:.6f}", text)

    def test_operation_lock_delay_is_separate_from_processing_delay(self):
        delay = self.timeout_s - 0.05
        text = self.exercise_expiry(arrival_gap=0.1, lock_delay=delay)
        self.assertIn(f"lock_wait_s={delay:.6f} processing_s=0.000000", text)
        self.assertIn(f"previous_submit_age_s={self.timeout_s + 0.05:.6f}", text)

    def test_watchdog_tick_before_late_callback_preserves_timeout_cause(self):
        text = self.exercise_expiry(
            arrival_gap=self.timeout_s + 0.001, expire_with_tick=True,
        )
        self.assertIn("kind=LeaseInvalid", text)
        self.assertIn(f"previous_submit_age_s={self.timeout_s + 0.001:.6f}", text)

    def test_synchronous_sensor_check_delay_is_recorded_as_processing(self):
        delay = self.timeout_s - 0.05
        text = self.exercise_expiry(arrival_gap=0.1, scan_delay=delay)
        self.assertIn(f"lock_wait_s=0.000000 processing_s={delay:.6f}", text)
        self.assertIn(f"previous_submit_age_s={self.timeout_s + 0.05:.6f}", text)


class Go2NavigationCommandTimingTests(NavigationCommandTimingTests):
    """Run the same gateway/manager checks against the user's Go2 profile."""

    timeout_s = 0.30
    expected_speed = 0.10

    def make_profile(self):
        return json.loads(
            (Path(__file__).resolve().parents[1] / "config/go2.json").read_text()
        )

    def test_nav2_one_mps_both_directions_preserves_caps_slew_and_timeout(self):
        for direction in (1.0, -1.0):
            self.message.linear.x = direction * 9.0
            initial = self.clock.now
            for step in range(81):
                self.clock.now = initial + step * 0.05
                self.refresh_inputs()
                if step % 2 == 0:
                    self.command()
                self.assertIsNone(self.navigation.keepalive_locked(self.clock()))
                self.tick()
            self.assertAlmostEqual(self.outputs[-1]["velocity"]["vx"], direction)
        drives = [item for item in self.outputs if item["type"] == "drive"]
        self.assertTrue(all(abs(item["velocity"]["vx"]) <= 1.0 for item in drives))
        for previous, current in zip(drives, drives[1:]):
            self.assertLessEqual(abs(current["velocity"]["vx"] - previous["velocity"]["vx"]), 0.040001)
        self.clock.now += 0.301
        self.refresh_inputs()
        self.tick()
        self.assertFalse(self.manager.snapshot()["lease"]["active"])
        self.assertEqual(self.manager.snapshot()["command"]["linear_x"], 0.0)

    def test_navigation_scaling_is_independent_of_manual_default(self):
        limits = self.manager.snapshot()["limits"]
        self.assertEqual(limits["default_speed_scale"], 0.35)
        self.assertEqual(limits["navigation_speed_scale"], 1.0)
        self.assertEqual(limits["vy_mps"], 0.2)
        self.assertEqual(limits["wz_rps"], 0.5)

    def test_one_missed_ten_hz_input_is_tolerated_and_second_miss_stops(self):
        self.command()
        self.tick()
        self.clock.now += 0.201
        self.refresh_inputs()
        self.command()
        self.tick()
        self.assertEqual(self.navigation.state["goal"]["state"], "active")
        self.assertTrue(self.manager.snapshot()["lease"]["active"])
        # Resume the ordinary 100 ms cadence without reacquiring the lease.
        self.clock.now += 0.1
        self.refresh_inputs()
        self.command()
        self.tick()
        self.assertEqual(self.outputs[-1]["type"], "drive")
        text = self.exercise_expiry(arrival_gap=0.301)
        self.assertIn("previous_submit_age_s=0.301000", text)


if __name__ == "__main__":
    unittest.main()
