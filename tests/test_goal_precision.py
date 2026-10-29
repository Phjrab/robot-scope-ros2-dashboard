import math
import unittest
from types import SimpleNamespace as NS

from robot_dashboard.goal_precision import GoalPrecision, pose_error, read_pose


def message(t, x=0.0, y=0.0, yaw=0.0, frame="map"):
    ns = round(t * 1e9)
    return NS(
        header=NS(frame_id=frame, stamp=NS(sec=ns // 10**9, nanosec=ns % 10**9)),
        child_frame_id="base_link",
        pose=NS(
            pose=NS(
                position=NS(x=x, y=y, z=0.0),
                orientation=NS(x=0.0, y=0.0, z=math.sin(yaw / 2), w=math.cos(yaw / 2)),
            )
        ),
    )


class GoalPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.r = GoalPrecision()
        self.r.start("goal1", {"x": 1.0, "y": 0.0, "yaw": 0.0}, {"job_id": "job1"})

    def sample(
        self, t, x=0.95, correction=0.0, yaw=0.0, generation="gen1", odom_stamp=None
    ):
        self.r.observe_map(
            message(t, x=x + correction, yaw=yaw), round(t * 1e9), t, generation
        )
        self.r.observe_odom(
            message(
                t if odom_stamp is None else odom_stamp, x=x, yaw=yaw, frame="odom"
            ),
            round(t * 1e9),
            t,
        )

    def stop(self, t=10.0, state="succeeded"):
        self.r.finish(state, round(t * 1e9), t, {"status": "unavailable"})
        for i in range(1, 26):
            self.sample(t + i * 0.1)

    def test_wrap_around_and_field_record_error(self):
        self.assertAlmostEqual(
            pose_error(
                {"x": 0.0, "y": 0.0, "yaw": -math.pi + 0.01},
                {"x": 0.0, "y": 0.0, "yaw": math.pi - 0.01},
            )["yaw_rad"],
            0.02,
        )
        error = pose_error(
            {"x": 0.1822845587, "y": 0.0050038571, "yaw": 0.6011655685},
            {"x": 0.4333220035, "y": -0.1750390756, "yaw": 1.0734900347},
        )
        self.assertAlmostEqual(error["xy_m"], 0.3089259722)
        self.assertAlmostEqual(error["yaw_rad"], -0.4723244662)

    def test_success_zero_without_body_measurement_is_not_stop_or_precision(self):
        self.sample(10.0, x=0.69, yaw=0.472)
        self.r.finish("succeeded", 10_000_000_000, 10.0, {})
        self.r.zero = {"issued_ros_ns": "10000000000", "bridge_ack": "UNOBSERVED"}
        v = self.r.snapshot(10.1)
        self.assertEqual(v["result"]["state"], "succeeded")
        self.assertFalse(v["stop"]["confirmed_now"])
        self.assertIsNone(v["precision"]["satisfied_now"])
        self.assertAlmostEqual(v["current"]["error"]["xy_m"], 0.31)
        self.assertIsNone(v["result"]["nav2_success_stamp_ns"])

    def test_valid_fresh_stop_preserves_near_result_and_stale_is_not_current_pass(self):
        self.sample(10.0)
        self.stop()
        v = self.r.snapshot(12.5)
        self.assertTrue(v["stop"]["confirmed_now"])
        self.assertTrue(v["precision"]["satisfied_now"])
        self.assertEqual(v["near_result"]["stamp_ns"], "10000000000")
        self.assertEqual(v["near_result"]["offset_from_result_receipt_s"], 0.0)
        self.assertGreaterEqual(v["stop"]["window"]["observed_stopped_seconds"], 2)
        stale = self.r.snapshot(13.1)
        self.assertFalse(stale["stop"]["confirmed_now"])
        self.assertIsNone(stale["precision"]["satisfied_now"])
        self.assertIsNotNone(stale["after_stop"])

    def test_mismatched_frame_stale_future_and_missing_pose_cannot_pass(self):
        self.sample(10.0)
        self.stop()
        for m, now in [
            (message(12.6, frame="odom"), 12.6),
            (message(10.0), 12.6),
            (message(13.0), 12.6),
            (NS(), 12.6),
        ]:
            with self.subTest(m=m):
                self.r.observe_map(m, round(now * 1e9), now, "gen1")
                self.assertFalse(self.r.snapshot(now)["stop"]["confirmed_now"])
                self.assertIsNone(self.r.snapshot(now)["precision"]["satisfied_now"])
        with self.assertRaises(ValueError):
            read_pose(message(12.0, yaw=float("nan")), "map", 12_000_000_000, 12.0)

    def test_corrected_map_pose_is_not_body_motion_and_unsynchronized_is_unavailable(
        self,
    ):
        self.sample(10.0)
        self.r.finish("succeeded", 10_000_000_000, 10.0, {})
        for i in range(1, 26):
            self.sample(10 + i * 0.1, correction=0.2)
        v = self.r.snapshot(12.5)
        self.assertFalse(v["precision"]["satisfied_now"])
        self.assertAlmostEqual(v["motion_vs_correction"]["map_odom_translation_m"], 0.2)
        self.assertAlmostEqual(
            v["motion_vs_correction"]["body_odom_translation_m"], 0.0
        )
        self.r.start("goal2", {"x": 1.0, "y": 0.0, "yaw": 0.0}, {})
        self.sample(20.0, odom_stamp=19.99)
        self.r.finish("succeeded", 20_000_000_000, 20.0, {})
        for i in range(1, 26):
            self.sample(20 + i * 0.1, odom_stamp=20 + i * 0.1 - 0.01)
        self.assertIsNone(self.r.snapshot(22.5)["motion_vs_correction"])
        self.assertIsNone(self.r.snapshot(22.5)["after_stop"])

    def test_cancel_abort_and_new_goal_never_inherit_precision_success(self):
        for state in ("canceled", "failed"):
            self.setUp()
            self.sample(10.0)
            self.stop(state=state)
            self.assertFalse(self.r.snapshot(12.5)["precision"]["satisfied_now"])
        self.r.start("new", {"x": 2.0, "y": 0.0, "yaw": 0.0}, {})
        v = self.r.snapshot(13.0)
        self.assertIsNone(v["near_result"])
        self.assertIsNone(v["after_stop"])
        self.assertIsNone(v["result"])

    def test_motion_resets_stop_and_duplicate_stamps_do_not_extend_evidence(self):
        self.sample(10.0)
        self.stop()
        before = self.r.snapshot(12.5)["stop"]["window"]["samples"]
        self.sample(12.5)
        self.assertEqual(self.r.snapshot(12.5)["stop"]["window"]["samples"], before)
        self.sample(12.6, x=0.98)
        self.assertFalse(self.r.snapshot(12.6)["stop"]["confirmed_now"])

    def test_transmitted_goal_and_plan_endpoint_are_separate_and_plan_uuid_unknown(
        self,
    ):
        msg = message(10.0, x=1.0)
        self.r.sent(msg, 10_000_000_000, 10.0)
        p = message(10.1, x=1.2)
        p.pose = p.pose.pose
        self.r.observe_plan(NS(header=p.header, poses=[p]), 10_100_000_000, 10.1)
        v = self.r.snapshot(10.1)
        self.assertEqual(v["transmitted"]["request_error"]["xy_m"], 0.0)
        self.assertAlmostEqual(v["plan_endpoint"]["request_error"]["xy_m"], 0.2)
        self.assertEqual(
            v["plan_endpoint"]["association"], "OBSERVED_DURING_GOAL_NO_ACTION_UUID"
        )

    def test_ring_and_snapshot_copy_are_bounded(self):
        for i in range(200):
            self.sample(10 + i * 0.1)
        self.assertLessEqual(len(self.r.samples), 64)
        self.assertLessEqual(len(self.r.odometry), 64)
        v = self.r.snapshot(29.9)
        v["requested"]["pose"]["x"] = 999
        self.assertEqual(self.r.goal["x"], 1.0)

    def test_source_generation_change_cannot_be_counted_as_same_stop(self):
        self.sample(10.0)
        self.r.finish("succeeded", 10_000_000_000, 10.0, {})
        for i in range(1, 26):
            self.sample(10 + i * 0.1, generation="new-source")
        v = self.r.snapshot(12.5)
        self.assertTrue(v["source_changed_after_dispatch"])
        self.assertFalse(v["stop"]["confirmed_now"])
        self.assertIsNone(v["motion_vs_correction"])

    def test_delayed_previous_goal_result_cannot_replace_new_record(self):
        from test_ros_navigation_gateway import gateway

        g = gateway()
        g._navigation_goal_generation = 2
        g._navigation["goal"] = {"goal_id": "new", "state": "active"}
        g._goal_precision.start("new", {"x": 1.0, "y": 0.0, "yaw": 0.0}, {})
        g._navigation_result_callback(1, "old", NS(result=lambda: NS(status=4)))
        self.assertIsNone(g._goal_precision.result)
        self.assertEqual(g._navigation["goal"]["state"], "active")


class GatewayPrecisionTests(unittest.TestCase):
    def test_callbacks_record_offset_stop_and_zero_without_changing_control(self):
        from unittest.mock import patch
        from test_ros_navigation_gateway import gateway

        clock = [10.0]
        node = NS(
            count_publishers=lambda topic: 1,
            get_clock=lambda: NS(now=lambda: NS(nanoseconds=round(clock[0] * 1e9))),
        )
        g = gateway(node=node)
        g._navigation["active"] = True
        g._controller_odom_mode = "fastlio_body"
        g._navigation_goal_generation = 1
        g._navigation["goal"] = {"goal_id": "g", "state": "active"}
        g._goal_precision.start("g", {"x": 1.0, "y": 0.0, "yaw": 0.0}, {})
        with patch(
            "robot_dashboard.ros.navigation_gateway.time.monotonic",
            side_effect=lambda: clock[0],
        ):
            for i in range(30):
                clock[0] = 10 + i * 0.1
                m = message(clock[0], x=0.69, yaw=-0.47)
                g._navigation_localization_callback(m)
                o = message(clock[0], x=0.69, yaw=-0.47, frame="odom")
                o.twist = NS(twist=NS(linear=NS(x=0.0, y=0.0), angular=NS(z=0.0)))
                g._navigation_health_callback(g._controller_odom_topic, o)
                if i == 2:
                    g._navigation_result_callback(
                        1, "g", NS(result=lambda: NS(status=4))
                    )
            v = g.runtime_snapshot()["goal"]["precision_evidence"]
        self.assertEqual(v["result"]["state"], "succeeded")
        self.assertEqual(g._navigation["goal"]["distance_remaining"], 0.0)
        self.assertAlmostEqual(v["after_stop"]["error"]["xy_m"], 0.31)
        self.assertAlmostEqual(v["near_result"]["error"]["yaw_rad"], -0.47)
        self.assertTrue(v["stop"]["confirmed_now"])
        self.assertFalse(v["precision"]["satisfied_now"])
        self.assertIsNotNone(v["motion_vs_correction"])
        self.assertIsNotNone(v["zero_command_issued"])
        self.assertTrue(g._goal_precision.logged_stop)

    def test_observer_failure_cannot_prevent_result_or_existing_stop(self):
        from unittest.mock import patch
        from test_ros_navigation_gateway import gateway, StubControlPort

        port = StubControlPort()
        g = gateway(port=port)
        g._navigation_goal_generation = 1
        g._navigation["goal"] = {"goal_id": "g", "state": "active"}
        g._goal_precision.start("g", {"x": 1.0, "y": 0.0, "yaw": 0.0}, {})
        with patch.object(
            g._goal_precision, "finish", side_effect=RuntimeError("observer failed")
        ):
            g._navigation_result_callback(1, "g", NS(result=lambda: NS(status=4)))
        self.assertEqual(g._navigation["goal"]["state"], "succeeded")
        self.assertIn("flush", port.events)
        self.assertIsNone(g.runtime_snapshot()["goal"]["precision_evidence"])
