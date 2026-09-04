import math
import json
import threading
import time
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

from robot_dashboard.control import CommandValidationError
from robot_dashboard.localization_health import classify_localization_health
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
            "limits": {
                "vx_mps": 0.30,
                "vy_mps": 0.20,
                "wz_rps": 0.50,
                "default_speed_scale": 0.35,
            },
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


def gateway(*, port=None, node=None, ticks=None, navigation_profile=""):
    control_port = port if port is not None else StubControlPort()
    count_node = node if node is not None else CountNode()
    tick_events = ticks if ticks is not None else []
    return NavigationRosGateway(
        control_port,
        node_getter=lambda: count_node,
        tick=lambda topic, observed: tick_events.append((topic, observed)),
        graph_getter=lambda: {},
        navigation_profile=navigation_profile,
    )


class NavigationRosGatewayTests(unittest.TestCase):
    @staticmethod
    def _prepare_active_goal(navigation, *, started_at=100.0):
        navigation._navigation_goal_generation = 1
        navigation._navigation["active"] = True
        navigation._navigation["localization"] = {
            "state": "localized",
            "pose": {"x": 0.0, "y": 0.0, "yaw": 0.0},
        }
        navigation._navigation["goal"] = {
            "state": "active",
            "goal_id": "g" * 32,
            "pose": {"x": 0.25, "y": 0.0, "yaw": 0.0},
            "distance_remaining": None,
            "initial_distance": None,
            "navigation_time": None,
            "recoveries": 0,
            "error": None,
        }
        navigation._navigation_goal_progress = (
            navigation._new_navigation_goal_progress(started_at)
        )

    @staticmethod
    def _publish_goal_feedback(navigation, distance, *, observed_at):
        message = SimpleNamespace(
            feedback=SimpleNamespace(
                distance_remaining=distance,
                navigation_time=None,
                number_of_recoveries=0,
            )
        )
        with mock.patch(
            "robot_dashboard.ros.navigation_gateway.time.monotonic",
            return_value=observed_at,
        ):
            navigation._navigation_feedback_callback(
                1,
                "g" * 32,
                message,
            )

    @staticmethod
    def _healthy_runtime_health():
        return {
            "ready": True,
            "cloud_fresh": True,
            "odom_fresh": True,
            "localized": True,
            "cloud_frequency_hz": 10.0,
            "cloud_jitter_s": 0.01,
            "cloud_age_s": 0.1,
            "age_s": 0.1,
            "odometry_frequency_hz": 100.0,
            "odometry_frequency_hz_raw": 100.0,
            "odometry_max_gap_s": 0.01,
            "odometry_jitter_s": 0.005,
            "odometry_age_s": 0.02,
            "odom_to_base_age_s": 0.02,
            "map_to_odom_age_s": 0.02,
            "accepted_points": 500,
            "fresh_sequence_count": 3,
            "last_jump_age_s": None,
            "frame_error": "",
            "source_error": "",
            "lidar_extrinsic": {
                "parent": "base_link",
                "child": "hesai_lidar",
            },
        }

    @classmethod
    def _goal_health(cls, navigation, *, now):
        metrics = navigation._localization_metrics(
            cls._healthy_runtime_health(),
            now,
        )
        return classify_localization_health(
            metrics,
            active=True,
            localized=True,
            thresholds=navigation._health_thresholds,
            rate_policy=navigation._rate_policy,
        )

    def test_runtime_health_tracks_only_advancing_fresh_sequences_and_bounds_metrics(self):
        navigation = gateway()

        def publish(sequence, *, fresh=True):
            payload = {
                "schema": "robot-scope.navigation-runtime-health.v1",
                "ready": fresh,
                "cloud_fresh": fresh,
                "odom_fresh": fresh,
                "localized": fresh,
                "cloud_topic": "/velodyne_points",
                "scan_topic": "/scan",
                "odometry_topic": "/Odometry",
                "cloud_frame": "hesai_lidar",
                "publisher_counts": {"/velodyne_points": 1, "/Odometry": 1},
                "input_points": 1000,
                "accepted_points": 500,
                "cloud_sequence": sequence,
                "odometry_sequence": sequence,
                "cloud_frequency_hz": 10.0,
                "cloud_jitter_s": 0.01,
                "cloud_age_s": 0.02,
                "odometry_frequency_hz": 100.0,
                "odometry_jitter_s": 0.005,
                "odometry_age_s": 0.01,
                "odom_to_base_age_s": 0.01,
                "map_to_odom_age_s": 0.01,
                "translation_jump_count": 0,
                "heading_jump_count": 0,
                "last_jump_age_s": None,
                "frames": {"cloud": "hesai_lidar"},
                "lidar_extrinsic": {"parent": "base_link", "child": "hesai_lidar", "x": 0.25, "y": 0, "z": 0, "yaw": 0},
                "clock_domains": {"pointcloud": "host_ros_normalized"},
            }
            navigation._navigation_runtime_health_callback(
                SimpleNamespace(data=json.dumps(payload))
            )

        publish(1)
        publish(1)
        self.assertEqual(navigation._navigation_runtime_health["fresh_sequence_count"], 1)
        publish(2)
        publish(3)
        publish(4)
        health = navigation._navigation_runtime_health
        self.assertEqual(health["fresh_sequence_count"], 3)
        self.assertEqual(health["cloud_frequency_hz"], 10.0)
        self.assertEqual(health["accepted_points"], 500)
        navigation._navigation_runtime_health_received = (
            time.monotonic() - navigation._health_thresholds.runtime_health_stale_s - 0.1
        )
        publish(5)
        self.assertEqual(navigation._navigation_runtime_health["fresh_sequence_count"], 1)
        publish(6, fresh=False)
        self.assertEqual(navigation._navigation_runtime_health["fresh_sequence_count"], 0)

    def test_competition_runtime_owns_stable_raw_rate_evidence(self):
        navigation = gateway(
            navigation_profile="go2-xt16-wireless-competition-fastlio"
        )
        navigation._localization_only["active"] = True
        navigation._navigation["localization"] = {
            "state": "localized",
            "pose": {"x": 0.0, "y": 0.0, "yaw": 0.0},
        }

        def payload(sequence, raw_rate=9.984123456):
            return {
                "schema": "robot-scope.navigation-runtime-health.v1",
                "ready": True,
                "cloud_fresh": True,
                "odom_fresh": True,
                "localized": True,
                "cloud_topic": "/velodyne_points",
                "scan_topic": "/scan",
                "odometry_topic": "/Odometry",
                "controller_odometry_topic": (
                    "/robot_scope/nav/controller_odom_fastlio"
                ),
                "controller_odometry_mode": "competition_fastlio",
                "controller_odometry": {
                    "ready": True,
                    "state": "ready",
                    "age_s": 0.01,
                    "source_to_host_offset_s": 0.01,
                    "error": "",
                },
                "cloud_frame": "hesai_lidar",
                "publisher_counts": {"/velodyne_points": 1, "/Odometry": 1},
                "input_points": 1000,
                "accepted_points": 500,
                "cloud_sequence": sequence,
                "odometry_sequence": sequence,
                "cloud_frequency_hz": 10.0,
                "cloud_jitter_s": 0.01,
                "cloud_age_s": 0.02,
                "odometry_frequency_hz": round(raw_rate, 3),
                "odometry_frequency_hz_raw": raw_rate,
                "odometry_mean_period_s": 1.0 / raw_rate,
                "odometry_median_period_s": 0.1001,
                "odometry_p95_period_s": 0.101,
                "odometry_max_gap_s": 0.102,
                "odometry_window_duration_s": 3.1,
                "odometry_sample_count": 32,
                "odometry_interval_count": 31,
                "odometry_jitter_s": 0.005,
                "odometry_age_s": 0.01,
                "odom_to_base_age_s": 0.01,
                "map_to_odom_age_s": 0.01,
                "translation_jump_count": 0,
                "heading_jump_count": 0,
                "last_jump_age_s": None,
                "process_generation": 4242,
                "frames": {"cloud": "hesai_lidar"},
                "lidar_extrinsic": {
                    "parent": "base_link",
                    "child": "hesai_lidar",
                    "x": 0.25,
                    "y": 0,
                    "z": 0,
                    "yaw": 0,
                },
                "clock_domains": {"pointcloud": "host_ros_normalized"},
            }

        for sequence in range(1, 104):
            observed = 100.0 + (sequence - 1) * 0.1
            with mock.patch(
                "robot_dashboard.ros.navigation_gateway.time.monotonic",
                return_value=observed,
            ):
                navigation._navigation_runtime_health_callback(
                    SimpleNamespace(data=json.dumps(payload(sequence)))
                )
        with mock.patch(
            "robot_dashboard.ros.navigation_gateway.time.monotonic",
            return_value=110.3,
        ):
            navigation._navigation_runtime_health_callback(
                SimpleNamespace(data=json.dumps(payload(104)))
            )
            snapshot = navigation.runtime_snapshot()

        health = snapshot["localization_health"]
        self.assertEqual(health["state"], "READY", health)
        self.assertEqual(health["stable_ready_duration_s"], 10.1)
        self.assertTrue(health["rate_gate"]["enabled"])
        self.assertEqual(
            health["metrics"]["odometry_frequency_hz_raw"], 9.984123
        )
        self.assertEqual(
            health["metrics"]["odometry_frequency_hz_display"], 9.984
        )

        nonfinite = payload(105)
        nonfinite["odometry_frequency_hz_raw"] = float("nan")
        with mock.patch(
            "robot_dashboard.ros.navigation_gateway.time.monotonic",
            return_value=110.4,
        ):
            navigation._navigation_runtime_health_callback(
                SimpleNamespace(data=json.dumps(nonfinite))
            )
            rejected = navigation.runtime_snapshot()["localization_health"]
        self.assertEqual(rejected["state"], "UNAVAILABLE")
        self.assertTrue(rejected["hard_fault"])

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

    def test_active_navigation_applies_default_speed_scale_once(self):
        port = StubControlPort()
        navigation = gateway(port=port)
        now = time.monotonic()
        navigation._navigation_token = "navigation-test-token-long-enough"
        navigation._navigation_binding = "navigation-binding"
        navigation.state.update(
            active=True,
            state="armed",
            goal={"state": "active", "goal_id": "g" * 32},
        )
        port.manager._snapshot["lease"] = {
            "active": True,
            "input_source": "navigation",
        }
        navigation._navigation_runtime_health_received = now
        navigation._navigation_runtime_health.update(
            ready=True,
            cloud_fresh=True,
            odom_fresh=True,
            localized=True,
        )
        navigation._navigation_validated_receipts.update(
            {
                "/scan": now,
                NAVIGATION_FAST_LIO_ODOM_TOPIC: now,
                NAVIGATION_CONTROLLER_ODOM_TOPIC: now,
                NAVIGATION_LOCALIZATION_POSE_TOPIC: now,
            }
        )

        navigation.submit_velocity(0.20, 0.0, 0.0)

        self.assertEqual(len(port.manager.submissions), 1)
        _args, kwargs = port.manager.submissions[0]
        self.assertAlmostEqual(kwargs["vx"], 0.20 / 0.30)
        self.assertEqual(kwargs["speed_scale"], 0.35)
        self.assertTrue(kwargs["deadman"])
        self.assertAlmostEqual(navigation.state["last_cmd"]["vx"], 0.07)

    def test_cumulative_progress_accepts_c4_scaled_motion_at_ten_hz(self):
        navigation = gateway()
        self._prepare_active_goal(navigation)

        for sample in range(41):
            self._publish_goal_feedback(
                navigation,
                1.0 - sample * 0.0035,
                observed_at=100.0 + sample * 0.1,
            )

        progress = navigation._navigation_goal_progress
        self.assertGreaterEqual(progress["progress_rate_mps"], 0.034)
        self.assertGreater(progress["last_progress_at"], 103.7)
        self.assertEqual(navigation._navigation["goal"]["distance_remaining"], 0.86)
        health = self._goal_health(navigation, now=104.0)
        self.assertEqual(health["state"], "READY", health)

    def test_no_progress_fails_at_the_existing_three_second_boundary(self):
        navigation = gateway()
        self._prepare_active_goal(navigation)
        self._publish_goal_feedback(navigation, 1.0, observed_at=100.0)

        before = self._goal_health(navigation, now=102.999)
        at_boundary = self._goal_health(navigation, now=103.0)

        self.assertEqual(before["state"], "READY", before)
        self.assertEqual(at_boundary["state"], "DEGRADED", at_boundary)
        self.assertEqual(at_boundary["reason_code"], "GOAL_PROGRESS_TOO_LOW")

    def test_stationary_noise_reverse_and_below_minimum_progress_still_fail(self):
        cases = {
            "no_progress": lambda sample: 1.0,
            "stationary_noise": lambda sample: 1.0 + (0.002 if sample % 2 else -0.002),
            "reverse": lambda sample: 1.0 + sample * 0.0035,
            "below_minimum_rate": lambda sample: 1.0 - sample * 0.0005,
        }
        for name, distance_at in cases.items():
            with self.subTest(name=name):
                navigation = gateway()
                self._prepare_active_goal(navigation)
                for sample in range(32):
                    self._publish_goal_feedback(
                        navigation,
                        distance_at(sample),
                        observed_at=100.0 + sample * 0.1,
                    )

                metrics = navigation._localization_metrics({}, 103.1)
                self.assertGreaterEqual(
                    metrics["controller_stall_duration_s"],
                    navigation._health_thresholds.controller_stall_s,
                )
                self.assertLess(
                    metrics["goal_progress_rate_mps"],
                    navigation._health_thresholds.goal_progress_min_mps,
                )
                health = self._goal_health(navigation, now=103.1)
                self.assertEqual(health["state"], "DEGRADED", health)
                self.assertEqual(health["reason_code"], "GOAL_PROGRESS_TOO_LOW")

    def test_first_active_goal_health_failure_survives_cancel_and_stop(self):
        navigation = gateway()
        self._prepare_active_goal(navigation)
        self._publish_goal_feedback(navigation, 1.0, observed_at=100.0)
        runtime = self._healthy_runtime_health()
        with navigation._navigation_lock:
            navigation._update_localization_readiness_locked(103.0, runtime)
            first = json.loads(
                json.dumps(navigation._navigation_goal_first_nonready)
            )

            later = dict(runtime)
            later["frame_error"] = "later frame fault"
            navigation._update_localization_readiness_locked(103.1, later)
            self.assertEqual(navigation._navigation_goal_first_nonready, first)

        self.assertEqual(first["reason_code"], "GOAL_PROGRESS_TOO_LOW")
        self.assertEqual(first["metrics"]["controller_stall_duration_s"], 3.0)
        self.assertEqual(first["observed_at_monotonic_s"], 103.0)
        self.assertLess(len(json.dumps(first)), 5_000)

        with mock.patch(
            "robot_dashboard.ros.navigation_gateway.time.monotonic",
            return_value=104.0,
        ):
            canceled = navigation.cancel_goal(goal_id="g" * 32)
            stopped = navigation.deactivate("navigation_stop")

        for snapshot in (canceled, stopped):
            public = snapshot["goal"]["first_nonready_health"]
            self.assertEqual(public["reason_code"], "GOAL_PROGRESS_TOO_LOW")
            self.assertEqual(public["captured_age_s"], 1.0)
            self.assertNotIn("observed_at_monotonic_s", public)

    def test_new_goal_initialization_resets_first_nonready_health(self):
        class GoalMessage:
            def __init__(self):
                self.pose = SimpleNamespace(header=None, pose=None)

        class ActionType:
            Goal = GoalMessage

        class PendingFuture:
            def add_done_callback(self, callback):
                self.callback = callback

        class ReadyActionClient:
            @staticmethod
            def server_is_ready():
                return True

            @staticmethod
            def send_goal_async(message, *, feedback_callback):
                del message, feedback_callback
                return PendingFuture()

        navigation = gateway()
        self._prepare_active_goal(navigation)
        navigation._navigation["map"] = {
            "id": "map",
            "revision": "a" * 64,
        }
        navigation._navigation["goal"]["state"] = "idle"
        navigation._navigation_goal_first_nonready = {
            "state": "DEGRADED",
            "reason_code": "OLD_GOAL_FAILURE",
        }
        navigation._navigation_action_type = ActionType
        navigation._navigation_action_client = ReadyActionClient()
        navigation._navigation_sensor_interlock_reason = (
            lambda *_args, **_kwargs: None
        )
        navigation._new_stamped_pose = lambda *_args: SimpleNamespace(
            header=SimpleNamespace(),
            pose=SimpleNamespace(pose=SimpleNamespace()),
        )

        snapshot = navigation.send_goal(
            map_id="map",
            map_revision="a" * 64,
            x=0.25,
            y=0.0,
            yaw=0.0,
        )

        self.assertIsNone(navigation._navigation_goal_first_nonready)
        self.assertIsNone(snapshot["goal"]["first_nonready_health"])

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
