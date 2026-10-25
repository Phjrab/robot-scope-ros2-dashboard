"""Synthetic contract regressions, NOT a D0/C4 package integration or robot test."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from robot_dashboard.mission_routes.competition_native import RuntimeConfig, RuntimePorts, TimingPolicy, configure_action
from robot_dashboard.mission_routes.competition_native.authority import ConsumerReceipt, FinalConsumerConstraintPort
from robot_dashboard.mission_routes.competition_native.contracts import ActionEvent, ConstraintAck, ConstraintRequest, EventBinding, ExitAuthorization
from robot_dashboard.mission_routes.competition_native.coordinator import CoordinatorNavigationPort, LegBinding
from robot_dashboard.mission_routes.competition_native.fragments import SignalBinding, join_signal
from robot_dashboard.mission_routes.competition_native.observations import ClockBinding, Extras, Normalizer, ObservationRejected
from .helpers import POSE, Rig


def runtime_rig():
    r = Rig(policy=TimingPolicy(.25, .25, .5, .25))
    a = r.adapter
    config = RuntimeConfig(a.action.model_dump(), a.scope, a.policy, r.bindings,
                           EventBinding("owner-loop", "boot-1"), "local-monotonic", a.activation)
    runtime = configure_action(config, RuntimePorts(r.ports, r.ports, r.ports, r.ports), clock=r.clock)
    r.adapter = runtime.adapter
    return r, runtime


def event(r, kind, *, sequence=1, status="ACKNOWLEDGED", cancel_ack=False):
    a = r.adapter
    if kind == "APPROACH_TERMINAL":
        request = a._cancel_request_id if status == "CANCELED" else a._goal_request_id
    elif kind == "EXIT_ACK":
        request = a._goal_request_id
    else:
        request = a._constraint.request_id
    return ActionEvent(kind, a.scope, a._goal.actual_goal_id if a._goal else "", request,
                       "owner-loop", "boot-1", sequence, r.clock.now, 0.,
                       "local-monotonic", a.receiver_session_id, status, cancel_ack)


class RuntimeContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_factory_snapshot_and_live_start_do_not_create_execution(self):
        r, runtime = runtime_rig()
        self.assertFalse(runtime.snapshot()["live_ready"])
        self.assertEqual(r.ports.calls, [])
        config = replace(runtime.config, activation=replace(runtime.config.activation, synthetic=False))
        live = configure_action(config, RuntimePorts(r.ports, r.ports), clock=r.clock)
        with self.assertRaisesRegex(ValueError, "UNCONNECTED"):
            await live.start("live-start-request", approach_pose=POSE)
        self.assertEqual(r.ports.calls, [])

    async def test_delayed_cancel_duplicate_ack_and_no_physical_dwell(self):
        r, runtime = runtime_rig()
        await r.start()
        await r.tick(0.)  # feet cancel approach, no HOLD until terminal ACK
        self.assertEqual(r.adapter.state.phase, "WAIT_CANCEL")
        r.clock.now = .01
        pending = event(r, "APPROACH_TERMINAL", status="CANCELED")
        self.assertEqual((await runtime.event_ack(pending))["reason"], "CANCEL_ACK_PENDING")
        self.assertEqual((await runtime.event_ack(pending))["reason"], "DUPLICATE_ACK")
        self.assertNotIn(("HOLD", 1), r.ports.calls)
        r.clock.now = .02
        accepted = event(r, "APPROACH_TERMINAL", sequence=2, status="CANCELED", cancel_ack=True)
        self.assertTrue((await runtime.event_ack(accepted))["accepted"])
        self.assertEqual((await runtime.event_ack(accepted))["reason"], "DUPLICATE_ACK")
        self.assertEqual((await runtime.event_ack(pending))["reason"], "DUPLICATE_ACK")
        for t in (.03, .04, .24, .44):
            await r.tick(t, goal_state="CANCELED", cancel_ack=True, front_left_status="OUTSIDE",
                         body_motion_status="MOVING")
        self.assertEqual(r.adapter.state.phase, "HOLD_SIGNAL")
        self.assertIsNone(r.adapter.state.dwell_start)
        self.assertEqual(r.ports.calls.count(("HOLD", 1)), 1)

    async def test_foreign_ack_fails_closed(self):
        r, runtime = runtime_rig()
        await r.start()
        r.clock.now = .01
        foreign = replace(event(r, "APPROACH_TERMINAL", status="SUCCEEDED"), actual_goal_id="foreign")
        result = await runtime.event_ack(foreign)
        self.assertFalse(result["accepted"])
        self.assertEqual(r.adapter.state.phase, "FAILED")
        self.assertEqual(r.ports.calls[-2:], [("HOLD", 1), ("cancel", 1)])

    async def test_new_generation_hold_ack_can_arrive_on_later_tick(self):
        r, _ = runtime_rig()
        await r.hold()
        original = r.ports.apply
        async def delayed(request):
            if request.scope.goal_generation == 2:
                r.ports.drop_ack = True
            return await original(request)
        r.ports.apply = delayed
        await r.dwell()
        self.assertEqual(r.adapter.state.phase, "EXIT_PREPARE")
        self.assertNotIn(("goal", "exit", 2), r.ports.calls)
        r.clock.now = 2.03
        self.assertTrue((await r.adapter.event_ack(event(r, "HOLD_ACK")))["accepted"])
        r.ports.drop_ack = False  # consumer now reports the installed ACK too
        await r.adapter.tick()
        self.assertEqual(r.adapter.state.phase, "EXIT_PENDING")
        self.assertEqual(r.ports.calls.count(("goal", "exit", 2)), 1)

    async def test_exit_ack_and_release_ack_precede_acquired_moving(self):
        r, runtime = runtime_rig()
        original = r.ports.dispatch
        async def pending(*args, **kwargs):
            result = await original(*args, **kwargs)
            return replace(result, acknowledged=kwargs["leg"] != "exit")
        r.ports.dispatch = pending
        await r.hold()
        await r.dwell()
        await r.tick(2.03)
        self.assertEqual(r.adapter.state.reason, "EXIT_ACK_REQUIRED")
        r.clock.now = 2.04
        self.assertTrue((await runtime.event_ack(event(r, "EXIT_ACK", status="ACTIVE")))["accepted"])
        await r.tick(2.05)  # final consumer RELEASE acknowledged
        r.clock.now = 2.06
        p = r.packet(extras=Extras(departure_observed=True), body_motion_status="MOVING")
        parts = {**p.components}
        for key in ("motion", "departure"):
            parts[key] = replace(parts[key], source_age_s=.04)  # acquired at 2.02, before exit ACK
        await runtime.receive(replace(p, components=parts))
        self.assertEqual(r.adapter.state.reason, "DEPARTURE_OBSERVATION_PRECEDES_EXIT_ACK")
        self.assertFalse(r.adapter.state.departed)

    async def test_foreign_goal_moving_is_rejected(self):
        r, runtime = runtime_rig()
        await r.hold()
        await r.dwell()
        await r.tick(2.03)
        r.clock.now = 2.04
        p = r.packet(extras=Extras(departure_observed=True), body_motion_status="MOVING")
        parts = {**p.components, "motion": replace(p.components["motion"], scope=r.scope)}
        await runtime.receive(replace(p, components=parts))
        self.assertFalse(r.adapter.state.departed)
        self.assertEqual(r.adapter.state.phase, "FAILED")

    async def test_dwell_uses_acquisition_interval_and_half_second_gap(self):
        r, _ = runtime_rig()
        await r.hold()
        for t in (.02, .22, .42, 2.02):
            await r.tick(t, goal_state="SUCCEEDED")
        self.assertEqual(r.adapter.state.dwell_start, 2.02)
        self.assertEqual(r.adapter.state.phase, "HOLD_SIGNAL")
        self.assertNotIn(("goal", "exit", 2), r.ports.calls)
        r.clock.now = 2.1
        await r.adapter.tick()  # polling doesn't advance supported end
        self.assertEqual(r.adapter.state.last_valid_s, 2.02)

    async def test_stop_observations_acquired_before_hold_ack_do_not_count(self):
        r, runtime = runtime_rig()
        await r.hold()
        r.clock.now = .1
        p = r.packet(goal_state="SUCCEEDED")
        parts = dict(p.components)
        for key in ("feet", "motion"):
            parts[key] = replace(parts[key], source_age_s=.15)
        await runtime.receive(replace(p, components=parts))
        self.assertIsNone(r.adapter.state.dwell_start)
        self.assertEqual(r.adapter.state.reason, "STOP_OBSERVATION_PRECEDES_HOLD_ACK")

    async def test_red_unknown_or_stale_before_departure_always_reholds(self):
        for color in ("RED", "UNKNOWN", "stale"):
            with self.subTest(color=color):
                r, runtime = runtime_rig()
                await r.hold()
                await r.dwell()
                await r.tick(2.03)
                r.clock.now = 2.04
                p = r.packet(raw_state="GREEN" if color == "stale" else color,
                             stable_state="GREEN" if color == "stale" else color)
                if color == "stale":
                    p = replace(p, components={**p.components, "signal":
                        replace(p.components["signal"], source_age_s=.250001)})
                await runtime.receive(p)
                self.assertFalse(r.adapter.state.departed)
                self.assertEqual(r.adapter.state.reason, "SIGNAL_LOST_BEFORE_DEPARTURE")
                self.assertEqual(r.ports.calls[-2:], [("HOLD", 2), ("cancel", 2)])

    async def test_cleanup_uncertain_retires_and_never_restarts(self):
        r, runtime = runtime_rig()
        await r.start()
        r.ports.fail_cancel = True
        snap = await runtime.cleanup("shutdown-request-01")
        self.assertEqual(snap["state"]["phase"], "INTERRUPTED")
        self.assertIn("CLEANUP_UNCONFIRMED", snap["state"]["reason"])
        await runtime.tick()
        with self.assertRaisesRegex(ValueError, "RETIRED"):
            await runtime.start("restart-request-01", approach_pose=POSE)
        self.assertEqual(r.ports.calls.count(("goal", "approach", 1)), 1)

    async def test_cleanup_without_consumer_ack_is_explicitly_unconfirmed(self):
        r, runtime = runtime_rig()
        await r.start()
        r.ports.drop_ack = True
        result = await runtime.cleanup("shutdown-request-01")
        self.assertEqual(result["state"]["phase"], "INTERRUPTED")
        self.assertIn("CLEANUP_UNCONFIRMED:HOLD_ACK_UNCONFIRMED", result["state"]["reason"])
        self.assertEqual(r.ports.calls[-1], ("cancel", 1))

    async def test_reviewable_synthetic_trace(self):
        trace = json.loads((Path(__file__).parent / "fixtures/runtime_contract.json").read_text())
        r, runtime = runtime_rig()
        await runtime.start("trace-start-request", approach_pose=POSE)
        for row in trace["inputs"]:
            values = dict(row.get("observation", {}))
            if "departure_observed" in values:
                values["extras"] = Extras(departure_observed=values.pop("departure_observed"))
            await r.tick(row["time_s"], **values)
            self.assertEqual(r.adapter.state.phase, row["phase"], row)
            self.assertEqual(r.adapter.state.departed, row.get("departed", False), row)
        self.assertEqual([list(c) for c in r.ports.calls], trace["expected_calls"])


class ConsumerPortTests(unittest.IsolatedAsyncioTestCase):
    async def test_enqueue_is_not_ack_and_late_release_cannot_supersede_hold(self):
        sent = []
        async def install(request):
            sent.append(request)
            return None
        port = FinalConsumerConstraintPort(consumer_id="final-command-consumer", install=install)
        scope = Rig().scope
        hold = ConstraintRequest(scope, "hold-request-0001", "HOLD", "test", sequence=1)
        self.assertIsNone(await port.apply(hold))
        self.assertIsNone(port.ack(hold))
        port.acknowledge(ConsumerReceipt(port.consumer_id, hold, True))
        self.assertTrue(port.ack(hold).matches(hold))
        await port.apply(hold)
        self.assertEqual(len(sent), 1)
        release = replace(hold, request_id="release-request-01", mode="RELEASE", sequence=2)
        await port.apply(release)
        next_hold = replace(hold, request_id="hold-request-0002", sequence=3,
                            scope=replace(scope, goal_id="e" * 32, goal_generation=2))
        await port.apply(next_hold)
        with self.assertRaisesRegex(ValueError, "ACK_MISMATCH"):
            port.acknowledge(ConsumerReceipt(port.consumer_id, release, True))
        self.assertIsNone(port.ack(release))
        with self.assertRaisesRegex(ValueError, "RETIRED"):
            await port.apply(replace(release, request_id="late-release-0001", sequence=4))


class SignalFragmentTests(unittest.TestCase):
    def setUp(self):
        self.r = Rig()
        self.binding = SignalBinding("camera", "camera-boot", "synchronized_ros", "e" * 64,
                                     "camera-signal-binding", "f" * 64, "signal-1", "crossing-1", "local")
        self.context = dict(schema_version="traffic-observation-sidecar.v0.1", source_id="camera",
            producer_epoch="camera-boot", source_clock="synchronized_ros", sequence=1, source_stamp_ns="1000",
            clock_verified=True, identity_verified=True, association_verified=True, config_hash="e" * 64,
            first_received_s=10., processed_s=10.08, source_age_at_first_receipt_s=.02,
            binding_id="camera-signal-binding", receipt_ttl_s=.25, source_age_s=.1, receiver_age_s=.08,
            complete_mission_evidence=False, departure_authorized=False)
        self.fragment = dict(signal_id="signal-1", crossing_id="crossing-1", model_sha256="f" * 64,
            raw_state="GREEN", stable_state="GREEN", quality_flags=[], confidence=.9,
            roi_xyxy_native=[1, 2, 3, 4], native_image_size=[640, 480])
        bindings = {**self.r.bindings, "signal": ClockBinding("camera", "camera-boot", "synchronized_ros", True)}
        self.normalizer = Normalizer(self.r.scope, TimingPolicy.synthetic(), bindings, synthetic=True,
                                    receiver_session_id=self.r.adapter.receiver_session_id, receiver_clock_id="local")

    def join(self, packet=None, **kwargs):
        args = dict(fragment=self.fragment, context=self.context, binding=self.binding,
                    first_received_s=10., processed_s=10.08, now_s=10.15, receiver_clock_id="local")
        args.update(kwargs)
        return join_signal(packet or self.r.packet(), **args)

    def test_processing_age_once_first_arrival_preserved_polling_never_renews(self):
        p = self.join()
        frame = self.normalizer.receive(p, 10.15)
        self.assertAlmostEqual(frame.components["signal"].stamp.source_age_s, .02)
        self.assertEqual(frame.components["signal"].receipt_s, 10.)
        self.assertTrue(frame.fresh("signal"))  # age .17, not .1 + .15
        q = self.join(now_s=10.2)
        self.normalizer.receive(q, 10.2)
        self.assertFalse(self.normalizer.current(10.240001).fresh("signal"))
        self.assertEqual(self.normalizer.current(10.240001).components["signal"].receipt_s, 10.)

    def test_path_age_at_first_arrival_also_accrues_residence(self):
        n = Normalizer(self.r.scope, TimingPolicy(.25, .25, .5, .25), self.r.bindings,
                       synthetic=True, receiver_session_id=self.r.adapter.receiver_session_id)
        self.assertTrue(n.receive(self.r.packet(observation_age_s=.24), 1.).fresh("path"))
        self.assertFalse(n.current(1.02).fresh("path"))

    def test_color_never_creates_feet_stop_or_path(self):
        donor = self.r.packet(front_left_status="OUTSIDE", body_motion_status="MOVING", path_clear=False)
        p = self.join(donor)
        for key in ("front_left_status", "body_motion_status", "path_clear"):
            self.assertEqual(p.evidence[key], donor.evidence[key])
        self.assertEqual(p.extras, donor.extras)

    def test_foreign_clock_association_and_rebased_arrival_rejected(self):
        for change in ({"receiver_clock_id": "another-host"}, {"first_received_s": 10.07},
                       {"fragment": {**self.fragment, "crossing_id": "foreign"}},
                       {"context": {**self.context, "source_clock": "fixture"}},
                       {"now_s": 10.3}):
            with self.subTest(change=change), self.assertRaises(ObservationRejected):
                self.join(**change)


class NativeContinuationContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_distinct_success_and_canceled_hooks_recheck_inside_owner_lock(self):
        for terminal in ("SUCCEEDED", "CANCELED"):
            with self.subTest(terminal=terminal):
                scope = Rig().scope
                lock, operation_lock, admission = asyncio.Lock(), asyncio.Lock(), object()
                visits = ("1" * 32, "2" * 32)
                mission = dict(id=scope.mission_run_id, context_revision="pinned-context",
                    state="ready", phase="ready", ownership_active=False, current_index=0,
                    current_waypoint={"visit_id": visits[0]},
                    waypoints=[{"visit_id": x} for x in visits])
                goal = {}
                observed = []
                async def start(mission_id, *, admission):
                    goal.update(goal_id="actual-approach", state="active")
                    mission.update(state="running", ownership_active=True,
                                   current_waypoint={"visit_id": visits[0], "goal_id": "actual-approach"})
                    return {"mission": mission}
                def barrier():
                    goal["state"] = terminal.lower()
                    mission.update(state="paused", phase="native_action_barrier", native_barrier={
                        "scope": vars(scope), "actual_goal_id": "actual-approach",
                        "terminal_status": terminal, "token": "native-only-token"})
                async def pause(mission_id):
                    barrier()
                coordinator = SimpleNamespace(_coordination_lock=lock, _operation_lock=operation_lock,
                    _managed_admission=admission, snapshot=lambda _: {"mission": mission}, start=start, pause=pause)
                navigation = SimpleNamespace(coordination_lock=lock, view=lambda: {"goal": dict(goal)})
                async def hook(*, request, admission):
                    async with operation_lock:
                        self.assertIs(admission, coordinator._managed_admission)
                        self.assertEqual(request.native_barrier_token, mission["native_barrier"]["token"])
                        self.assertEqual(request.terminal_status, terminal)
                        self.assertEqual(request.actual_approach_goal_id, "actual-approach")
                        self.assertEqual(request.cancel_request_id, "cancel-request-001" if terminal == "CANCELED" else None)
                        self.assertTrue(request.authorization.hold_ack.matches(request.authorization.hold_request))
                        observed.append(request)
                        goal.update(goal_id="actual-exit", state="active")
                        mission.update(state="running", current_index=1,
                                       current_waypoint={"visit_id": visits[1], "goal_id": "actual-exit"})
                        return {"mission": mission}
                async def wrong_hook(**kwargs):
                    self.fail("wrong terminal path used")
                port = CoordinatorNavigationPort(coordinator, navigation, mission_id=scope.mission_run_id,
                    admission=admission, legs={(scope.step_id, leg): LegBinding(visit, tuple(POSE.values()))
                                              for leg, visit in zip(("approach", "exit"), visits)},
                    canceled_approach_continuation=hook if terminal == "CANCELED" else wrong_hook,
                    successful_approach_continuation=hook if terminal == "SUCCEEDED" else wrong_hook)
                await port.dispatch(scope, leg="approach", pose=POSE, request_id="approach-request01")
                if terminal == "CANCELED":
                    await port.cancel(scope, request_id="cancel-request-001")
                else:
                    barrier()
                new = replace(scope, goal_id="e" * 32, goal_generation=2)
                hold = ConstraintRequest(new, "exit-hold-request", "HOLD", "barrier", sequence=2)
                port.prepare_exit(ExitAuthorization(scope, new, hold, ConstraintAck(new, hold.request_id, "HOLD", True)))
                await operation_lock.acquire()
                task = asyncio.create_task(port.dispatch(new, leg="exit", pose=POSE, request_id="exit-request-0001"))
                await asyncio.sleep(0)
                self.assertEqual(observed, [])
                operation_lock.release()
                receipt = await asyncio.wait_for(task, 1)
                self.assertEqual(receipt.actual_goal_id, "actual-exit")
                self.assertEqual(len(observed), 1)
                self.assertEqual(await port.dispatch(new, leg="exit", pose=POSE, request_id="exit-request-0001"), receipt)
                with self.assertRaisesRegex(ValueError, "LATE_CANCEL"):
                    await port.cancel(scope, request_id="old-cancel-request")
