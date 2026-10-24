import unittest
from dataclasses import replace

from robot_dashboard.mission_routes.competition_native import Activation, TimingPolicy
from robot_dashboard.mission_routes.competition_native.observations import Extras
from .helpers import POSE, Rig


class ActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_disabled_and_snapshot_has_no_side_effects(self):
        r = Rig(activation=Activation())
        self.assertFalse(r.adapter.snapshot()["capabilities"]["enabled"])
        with self.assertRaisesRegex(ValueError, "UNCONNECTED"):
            await r.start()
        self.assertEqual(r.ports.calls, [])

    async def test_native_requires_explicit_cadence(self):
        r = Rig(policy=TimingPolicy())
        with self.assertRaisesRegex(ValueError, "TIMING"):
            await r.start()
        self.assertEqual(r.ports.calls, [])

    async def test_capability_report_is_per_action(self):
        r = Rig("NAVIGATE_ADAPTIVE", activation=Activation(True, True, "fake", "test",
            frozenset(REQUIRED_NAV)))
        self.assertTrue(r.adapter.snapshot()["capabilities"]["enabled"])
        r2 = Rig(activation=replace(r.adapter.activation, capabilities=frozenset(REQUIRED_NAV)))
        self.assertIn("feet_evidence", r2.adapter.snapshot()["capabilities"]["missing"])

    async def test_normal_traffic_order_and_departure_evidence(self):
        r = Rig()
        await r.hold()
        await r.dwell()
        self.assertEqual(r.adapter.state.phase, "EXIT_PENDING")
        self.assertFalse(r.adapter.state.departed)
        self.assertEqual(r.ports.calls, [("goal", "approach", 1), ("HOLD", 1),
                                       ("HOLD", 2), ("goal", "exit", 2)])
        await r.tick(2.03)
        self.assertEqual(r.ports.calls[-1], ("RELEASE", 2))
        self.assertFalse(r.adapter.state.departed)
        await r.tick(2.04, extras=Extras(departure_observed=True), body_motion_status="MOVING")
        self.assertTrue(r.adapter.state.departed)
        await r.tick(2.05, stable_state="RED", raw_state="RED", body_motion_status="MOVING")
        self.assertEqual(r.adapter.state.phase, "DEPARTING")
        await r.tick(2.06, goal_state="SUCCEEDED", stable_state="RED", raw_state="RED")
        self.assertEqual(r.adapter.state.phase, "SUCCEEDED")
        self.assertEqual(r.ports.calls[-1], ("HOLD", 2))

    async def test_two_second_boundary_is_not_rounded_up(self):
        r = Rig()
        await r.hold()
        await r.dwell(duration=1.75)
        await r.tick(2.019999, goal_state="SUCCEEDED")
        self.assertEqual(r.adapter.state.phase, "HOLD_SIGNAL")
        await r.tick(2.02, goal_state="SUCCEEDED")
        self.assertEqual(r.adapter.state.phase, "EXIT_PENDING")

    async def test_one_foot_never_accumulates(self):
        r = Rig()
        await r.hold()
        await r.dwell(duration=3.0, front_right_status="OUTSIDE")
        self.assertIsNone(r.adapter.state.dwell_start)
        self.assertEqual(len([x for x in r.ports.calls if x[0] == "goal"]), 1)

    async def test_gap_above_half_second_restarts_dwell(self):
        r = Rig()
        await r.hold()
        await r.tick(0.02, goal_state="SUCCEEDED")
        await r.tick(0.52, goal_state="SUCCEEDED")
        self.assertEqual(r.adapter.state.dwell_start, 0.02)
        await r.tick(1.020001, goal_state="SUCCEEDED")
        self.assertEqual(r.adapter.state.dwell_start, 1.020001)

    async def test_polling_cached_sample_cannot_accumulate_dwell(self):
        r = Rig()
        await r.hold()
        await r.tick(0.02, goal_state="SUCCEEDED")
        r.clock.now = 0.5
        await r.adapter.observe()
        self.assertEqual(r.adapter.state.last_valid_s, 0.02)
        await r.tick(0.6, goal_state="SUCCEEDED")
        self.assertEqual(r.adapter.state.dwell_start, 0.6)

    async def test_wrong_or_stale_signal_does_not_depart(self):
        for change in ({"signal_id": "other"}, {"crossing_id": "other"},
                       {"stable_state": "RED"}, {"quality_flags": ["blur"]}, {"pose": None}):
            with self.subTest(change=change):
                r = Rig()
                await r.hold()
                await r.dwell(**change)
                self.assertEqual(r.adapter.state.phase, "HOLD_SIGNAL")
                self.assertNotIn(("RELEASE", 1), r.ports.calls)
        r = Rig()
        await r.hold()
        for i in range(10):
            r.clock.now = i * 0.25 + 0.02
            p = r.packet(goal_state="SUCCEEDED")
            stamps = dict(p.components)
            stamps["signal"] = replace(stamps["signal"], source_age_s=0.6)
            await r.adapter.observe(replace(p, components=stamps))
        self.assertEqual(r.adapter.state.phase, "HOLD_SIGNAL")

    async def test_cancel_delay_does_not_hold_approach_prematurely(self):
        r = Rig()
        await r.start()
        await r.tick(0)
        self.assertEqual(r.adapter.state.phase, "WAIT_CANCEL")
        self.assertEqual(r.ports.calls, [("goal", "approach", 1), ("cancel", 1)])
        await r.tick(0.1, goal_state="CANCELED", cancel_ack=False)
        self.assertNotIn(("HOLD", 1), r.ports.calls)
        await r.tick(0.2, goal_state="CANCELED", cancel_ack=True)
        self.assertEqual(r.ports.calls[-1], ("HOLD", 1))
        self.assertEqual(r.ports.calls.count(("cancel", 1)), 1)

    async def test_lost_or_wrong_hold_ack_never_releases(self):
        for wrong in (False, True):
            r = Rig()
            await r.start()
            r.ports.drop_ack, r.ports.wrong_ack = not wrong, wrong
            for i in range(14):
                await r.tick(i * 0.25, goal_state="SUCCEEDED")
            self.assertEqual(r.adapter.state.phase, "HOLD_ACK")
            self.assertEqual(len([x for x in r.ports.calls if x[0] == "goal"]), 1)

    async def test_red_before_departure_holds_and_cancels_exact_exit_once(self):
        for after_release in (False, True):
            r = Rig()
            await r.hold()
            await r.dwell()
            if after_release:
                await r.tick(2.03)
            await r.tick(2.04, stable_state="RED", raw_state="RED")
            self.assertEqual(r.adapter.state.phase, "FAILED")
            self.assertFalse(r.adapter.state.departed)
            self.assertEqual(r.ports.calls[-1], ("cancel", 2))
            self.assertEqual(r.ports.calls.count(("cancel", 2)), 1)

    async def test_moving_without_departure_proof_does_not_latch(self):
        r = Rig()
        await r.hold()
        await r.dwell()
        await r.tick(2.03, body_motion_status="MOVING")
        self.assertFalse(r.adapter.state.departed)
        await r.tick(2.04, stable_state="RED", raw_state="RED", body_motion_status="MOVING")
        self.assertEqual(r.adapter.state.phase, "FAILED")

    async def test_contradictory_departure_fails_closed(self):
        r = Rig()
        await r.hold()
        await r.dwell()
        await r.tick(2.03, extras=Extras(departure_observed=True))
        self.assertEqual(r.adapter.state.reason, "CONTRADICTORY_DEPARTURE_EVIDENCE")

    async def test_estop_and_collision_override_post_departure(self):
        for extras in (Extras(estop=True), Extras(collision=True)):
            r = Rig()
            await r.hold()
            await r.dwell()
            await r.tick(2.03)
            await r.tick(2.04, extras=Extras(departure_observed=True), body_motion_status="MOVING")
            self.assertTrue(r.adapter.state.departed)
            await r.tick(2.05, extras=extras)
            self.assertEqual(r.adapter.state.phase, "FAILED")
            self.assertEqual(r.ports.calls[-1], ("cancel", 2))

    async def test_adaptive_causes_are_distinct_and_no_recovery_calls(self):
        changes = [({"obstacle_state": "WAIT_OBSTACLE"}, "WAIT_OBSTACLE"),
                   ({"obstacle_state": "REPLANNING"}, "REPLANNING"),
                   ({"obstacle_state": "SENSOR_UNAVAILABLE"}, "NAVIGATION_SENSOR_STALE"),
                   ({"goal_state": "FAILED"}, "NAVIGATION_PROGRESS_FAILED"),
                   ({"goal_state": "CANCELED", "cancel_ack": True}, "NAVIGATION_CANCELED")]
        for change, reason in changes:
            r = Rig("NAVIGATE_ADAPTIVE")
            await r.start()
            await r.tick(0, **change)
            self.assertEqual(r.adapter.state.reason, reason)
            self.assertTrue(all(x[0] in {"goal", "HOLD", "cancel"} for x in r.ports.calls))

    async def test_blocked_navigation_releases_only_with_fresh_path(self):
        r = Rig("NAVIGATE_ADAPTIVE")
        await r.start()
        await r.tick(0, obstacle_state="WAIT_OBSTACLE")
        await r.tick(0.1)
        self.assertEqual(r.ports.calls[-1], ("RELEASE", 1))
        await r.tick(0.2, goal_state="SUCCEEDED")
        self.assertEqual(r.adapter.state.phase, "SUCCEEDED")

    async def test_signal_wait_has_own_timeout(self):
        r = Rig()
        await r.hold()
        await r.tick(20.0, goal_state="SUCCEEDED", stable_state="RED")
        self.assertEqual(r.adapter.state.reason, "SIGNAL_WAIT_TIMEOUT")

    async def test_terrain_time_and_ack_do_not_prove_completion(self):
        r = Rig("TRAVERSE_TERRAIN")
        await r.start()
        await r.tick(0, goal_state="SUCCEEDED")
        self.assertEqual(r.ports.calls[-1], ("terrain", 1))
        await r.tick(5, terrain_complete=True)
        self.assertEqual(r.adapter.state.phase, "TERRAIN")
        await r.tick(6, terrain_complete=True, extras=Extras(terrain_verified=True, validation_reference="test-terrain"))
        self.assertEqual(r.adapter.state.phase, "SUCCEEDED")

    async def test_full_out_and_course_coverage_are_independent(self):
        r = Rig("FINISH_CROSSING")
        await r.start()
        await r.tick(0, goal_state="SUCCEEDED")
        await r.tick(2, full_body_crossed=False)
        self.assertEqual(r.adapter.state.phase, "FINISH")
        await r.tick(3, full_body_crossed=True, extras=Extras(attempted_steps=("one",), traversed_segments=()))
        self.assertEqual(r.adapter.state.phase, "SUCCEEDED")
        self.assertTrue(r.adapter.state.full_body_crossed)
        self.assertEqual(r.adapter.state.attempted_steps, ("one",))
        self.assertEqual(r.adapter.state.traversed_segments, ())

    async def test_park_break_resets_five_seconds_and_rise_needs_evidence(self):
        r = Rig("PARK_SIT_HOLD")
        await r.hold()
        self.assertEqual(r.ports.calls[-1], ("SIT", 1))
        good = dict(full_body_inside=True, posture="SIT",
                    extras=Extras(posture_verified=True, validation_reference="test-posture"))
        await r.dwell(duration=4.75, **good)
        self.assertEqual(r.adapter.state.phase, "PARK_HOLD")
        await r.tick(5.0, **{**good, "full_body_inside": False})
        self.assertIsNone(r.adapter.state.dwell_start)
        await r.dwell(start=5.1, duration=5.0, **good)
        self.assertEqual(r.adapter.state.phase, "SUCCEEDED")
        await r.adapter.prepare_movement("stand-request-0001")
        self.assertEqual(r.ports.calls[-1], ("STAND", 1))
        await r.tick(10.2, posture="STAND")
        self.assertEqual(r.adapter.state.phase, "RISE_WAIT")
        await r.tick(10.3, posture="STAND", extras=good["extras"])
        self.assertEqual(r.adapter.state.phase, "READY_TO_MOVE")
        self.assertFalse(any(x[0] == "RELEASE" for x in r.ports.calls))

    async def test_sdk_sit_ack_does_not_count(self):
        r = Rig("PARK_SIT_HOLD")
        await r.hold()
        await r.dwell(duration=6.0, posture="SIT", full_body_inside=True)
        self.assertEqual(r.adapter.state.phase, "PARK_HOLD")
        self.assertIsNone(r.adapter.state.dwell_start)

    async def test_duplicate_start_stop_and_restart_never_reissue_goal(self):
        r = Rig()
        await r.start()
        await r.start()
        self.assertEqual(len(r.ports.calls), 1)
        await r.adapter.stop("stop-request-00001", restart=True)
        calls = list(r.ports.calls)
        await r.adapter.stop("stop-request-00001", restart=True)
        await r.tick(1.0)
        self.assertEqual(r.ports.calls, calls)
        self.assertEqual(r.adapter.state.phase, "INTERRUPTED")
        with self.assertRaisesRegex(ValueError, "RETIRED"):
            await r.adapter.start("new-start-request-1", approach_pose=POSE)
        with self.assertRaisesRegex(ValueError, "PAYLOAD"):
            await r.adapter.stop("start-request-0001")

    async def test_ambiguous_goal_and_cleanup_failures_are_not_retried(self):
        r = Rig()
        r.ports.fail_goal = r.ports.fail_hold = r.ports.fail_cancel = True
        with self.assertRaises(RuntimeError):
            await r.start()
        self.assertIn("CLEANUP_UNCONFIRMED", r.adapter.state.reason)
        self.assertEqual([x[0] for x in r.ports.calls], ["goal", "HOLD", "cancel"])
        await r.start()
        self.assertEqual(len(r.ports.calls), 3)

    async def test_missing_safety_observation_stops_and_no_goal_replay(self):
        r = Rig("NAVIGATE_ADAPTIVE")
        await r.start()
        await r.tick(0)
        r.clock.now = 0.500001
        await r.adapter.observe()
        self.assertEqual(r.adapter.state.reason, "SAFETY_OBSERVATION_STALE")
        self.assertEqual(r.ports.calls[-2:], [("HOLD", 1), ("cancel", 1)])


REQUIRED_NAV = {"navigation_adapter", "pose_to_body", "collision_observations", "command_arbiter"}


class RaceAndFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_applies_hold_while_dispatch_is_pending(self):
        import asyncio
        r = Rig("NAVIGATE_ADAPTIVE")
        entered, release = asyncio.Event(), asyncio.Event()
        original = r.ports.dispatch
        async def delayed(*args, **kwargs):
            entered.set()
            await release.wait()
            return await original(*args, **kwargs)
        r.ports.dispatch = delayed
        start = asyncio.create_task(r.start())
        await entered.wait()
        stop = asyncio.create_task(r.adapter.stop("stop-pending-00001"))
        await asyncio.sleep(0)
        self.assertIn(("HOLD", 1), r.ports.calls)
        release.set()
        with self.assertRaisesRegex(ValueError, "STOP_REQUESTED"):
            await start
        await stop
        self.assertEqual(r.adapter.state.phase, "INTERRUPTED")
        self.assertEqual(r.ports.calls.count(("cancel", 1)), 1)
        self.assertFalse(any(x[0] == "RELEASE" for x in r.ports.calls))

    async def test_release_ack_failure_reholds_and_cancels(self):
        r = Rig()
        await r.hold()
        await r.dwell()
        r.ports.wrong_ack = True
        with self.assertRaisesRegex(ValueError, "RELEASE_ACK"):
            await r.tick(2.03)
        self.assertEqual(r.ports.calls[-2:], [("HOLD", 2), ("cancel", 2)])

    async def test_receiver_clock_rollback_interrupts_without_reusing_green(self):
        r = Rig()
        await r.hold()
        await r.tick(1, goal_state="SUCCEEDED")
        with self.assertRaisesRegex(ValueError, "ROLLBACK"):
            await r.tick(0.5, goal_state="SUCCEEDED")
        self.assertEqual(r.adapter.state.phase, "FAILED")
        self.assertIsNone(r.adapter.state.dwell_start)

    async def test_retired_generation_cannot_satisfy_exit(self):
        r = Rig()
        await r.hold()
        old = r.packet(goal_state="SUCCEEDED")
        await r.dwell()
        await r.adapter.observe(old)
        self.assertEqual(r.adapter.state.phase, "FAILED")
        self.assertNotIn(("RELEASE", 2), r.ports.calls)

    async def test_missing_terrain_and_out_evidence_timeout_without_success(self):
        for kind in ("TRAVERSE_TERRAIN", "FINISH_CROSSING"):
            r = Rig(kind)
            await r.start()
            await r.tick(0, goal_state="SUCCEEDED")
            await r.tick(20)
            self.assertEqual(r.adapter.state.phase, "FAILED")
            self.assertEqual(r.adapter.state.reason, "ACTION_TIMEOUT")

    async def test_duplicate_envelope_resets_dwell_without_releasing(self):
        r = Rig()
        await r.hold()
        r.clock.now = 0.02
        packet = r.packet(goal_state="SUCCEEDED")
        await r.adapter.observe(packet)
        r.clock.now = 0.03
        await r.adapter.observe(packet)
        self.assertIsNone(r.adapter.state.dwell_start)
        self.assertEqual(r.adapter.state.phase, "HOLD_SIGNAL")
        self.assertFalse(any(x[0] == "RELEASE" for x in r.ports.calls))

    async def test_missing_terrain_port_does_not_block_navigation_inspection(self):
        r = Rig("TRAVERSE_TERRAIN")
        r.adapter.terrain = None
        with self.assertRaisesRegex(ValueError, "TERRAIN_PORT"):
            await r.start()
        self.assertEqual(r.ports.calls, [])
        n = Rig("NAVIGATE_ADAPTIVE")
        n.adapter.terrain = n.adapter.posture = None
        await n.start()
        self.assertEqual(n.ports.calls, [("goal", "approach", 1)])
