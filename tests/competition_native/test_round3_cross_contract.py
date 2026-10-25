"""Actual pinned C4 projection and C1 coordinator with C2 public hooks.

Navigation/detector/clock/physical observations are synthetic, no live motion.
C1 session/ingress files are not edited; the test harness exercises the proposed
small public-API call sites against the real r2 coordinator and SessionGate.
"""
import asyncio
import copy
from dataclasses import replace
import importlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from robot_dashboard.mission_routes.competition_native import RuntimePorts, configure_action
from robot_dashboard.mission_routes.competition_native.authority import Command
from robot_dashboard.mission_routes.competition_native.contracts import ConstraintRequest
from robot_dashboard.mission_routes.competition_native.coordinator import CoordinatorNavigationPort, LegBinding
from robot_dashboard.mission_routes.competition_native.fragments import project_signal
from robot_dashboard.mission_routes.competition_native.observations import ObservationRejected, Extras
from .dependency_overlay import C1_SHA, C4_SHA, pinned_dependencies
from .helpers import POSE
from .test_coordinator import Navigation, SavedMaps
from .test_runtime_contract import runtime_rig


class C4CrossTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.overlay = pinned_dependencies()
        cls.deps = cls.overlay.__enter__()
        cls.addClassCleanup(cls.overlay.__exit__, None, None, None)
        print(f"C2 cross dependency C4={C4_SHA}; C1={C1_SHA}")

    def setUp(self):
        from .test_runtime_contract import SignalFragmentTests
        self.f = SignalFragmentTests()
        self.f.setUp()
        self.observation = SimpleNamespace(signal=self.f.fragment, context=self.f.context)

    def project(self, *, now=10.15, observation=None, **kwargs):
        return project_signal(self.f.r.packet(), observation=observation or self.observation,
            projection=self.deps.projection, binding=self.f.binding, now_s=now,
            receiver_clock_id="local", **kwargs)

    def test_actual_projection_age_017_boundary_025_and_expired(self):
        p = self.project(first_received_s=10., source_age_at_first_receipt_s=.02, processed_s=10.08)
        frame = self.f.normalizer.receive(p, 10.15)
        stamp = frame.components["signal"]
        self.assertAlmostEqual(stamp.stamp.source_age_s + frame.now - stamp.receipt_s, .17)
        self.assertTrue(frame.fresh("signal"))
        # Exactly .25 source age is accepted by BOTH actual C4 and C2.
        p = self.project(now=10.23)
        self.assertTrue(self.f.normalizer.receive(p, 10.23).fresh("signal"))
        self.assertFalse(self.f.normalizer.current(10.230001).fresh("signal"))
        with self.assertRaisesRegex(ValueError, "EXPIRED"):
            self.project(now=10.230001)

    def test_polling_and_completion_cannot_replace_first_receipt(self):
        for override in ({"first_received_s": 10.08}, {"processed_s": 10.15},
                         {"source_age_at_first_receipt_s": 0.0}):
            with self.subTest(override=override), self.assertRaisesRegex(ValueError, "MISMATCH"):
                self.project(**override)
        with self.assertRaisesRegex(ValueError, "FIRST_RECEIPT_MISMATCH"):
            self.deps.projection(self.observation, now_s=10.15, received_s=10.08)
        p = self.project()
        self.f.normalizer.receive(p, 10.15)
        repeated = self.project(now=10.2)
        self.assertEqual(self.f.normalizer.receive(repeated, 10.2).components["signal"].receipt_s, 10.)
        # A caller laundering the same source identity fails even if all of the
        # changed time fields agree with one another.
        c = {**self.f.context, "first_received_s": 10.1, "processed_s": 10.18}
        forged = self.project(now=10.2, observation=SimpleNamespace(signal=self.f.fragment, context=c))
        with self.assertRaisesRegex(ObservationRejected, "DUPLICATE_COMPONENT_CHANGED"):
            self.f.normalizer.receive(forged, 10.2)

    def test_explicit_first_age_and_mixed_legacy_conflicts(self):
        for key, value in (("source_age_s", .08), ("receiver_age_s", 0.),
                           ("identity_verified", False), ("clock_verified", False),
                           ("association_verified", False), ("producer_epoch", "retired"),
                           ("config_hash", "d" * 64), ("sequence", True)):
            with self.subTest(key=key), self.assertRaises((ValueError, TypeError)):
                self.project(observation=SimpleNamespace(signal=self.f.fragment,
                    context={**self.f.context, key: value}))
        explicit = {k: v for k, v in self.f.context.items() if k not in {"source_age_s", "receiver_age_s"}}
        self.assertEqual(self.project(observation=SimpleNamespace(signal=self.f.fragment,
                         context=explicit)).components["signal"].source_age_s, .02)
        for name in ("first_received_s", "source_age_at_first_receipt_s", "processed_s"):
            incomplete = {k: v for k, v in self.f.context.items() if k != name}
            with self.subTest(name=name), self.assertRaises((ValueError, KeyError)):
                self.project(observation=SimpleNamespace(signal=self.f.fragment, context=incomplete))

    def test_reconnect_old_signal_has_no_new_receipt_or_green(self):
        p = self.project()
        self.f.normalizer.receive(p, 10.15)
        from robot_dashboard.mission_routes.competition_native.observations import Normalizer
        old = self.f.normalizer
        restarted = Normalizer(old.scope, old.policy, old.bindings, synthetic=True, receiver_clock_id="local")
        with self.assertRaisesRegex(ObservationRejected, "SESSION_RETIRED"):
            restarted.receive(p, 10.16)
        with self.assertRaisesRegex(ValueError, "EXPIRED"):
            self.project(now=11.)

    def test_identical_jpeg_new_verified_identity_and_repeated_stamp(self):
        import cv2
        import numpy as np
        from experiments.competition_vm.traffic_signals.detector import Detection
        c4 = self.deps.c4_package
        pipeline_type = importlib.import_module(c4 + ".pipeline").TrafficPipeline
        frames = importlib.import_module(c4 + ".frames")
        # Hand-authored configuration and synthetic pixels; detector is a stub.
        association = {"signal_id": "signal-1", "crossing_id": "crossing-1",
            "binding_id": self.f.binding.binding_id, "native_image_size": [64, 64],
            "verified": True, "expected_roi_native": [0, 0, 64, 64]}
        config = SimpleNamespace(sha256=self.f.binding.config_hash, document={
            "model": {"sha256": "f" * 64}, "class_map": {"0": "traffic_light"},
            "min_confidence": .25, "association": association})
        detector = SimpleNamespace(sha256="f" * 64, names={"0": "traffic_light"},
            coordinate_space="native_xyxy", infer=lambda _: [Detection((0, 0, 64, 64), .9, 0, "stub")])
        pixels = np.full((64, 64, 3), 15, np.uint8)
        cv2.circle(pixels, (32, 32), 12, (0, 230, 0), -1)
        ok, encoded = cv2.imencode(".jpg", pixels)
        self.assertTrue(ok)
        jpeg = encoded.tobytes()
        clock = [9.58]
        pipeline = pipeline_type(config, detector, clock=lambda: clock[0])
        for index in range(6):
            first = round(9.5 + index * .1, 2)
            clock[0] = first + .08
            image = frames.from_owner_jpeg(jpeg, source_id="camera", producer_epoch="camera-boot",
                sequence=index, source_stamp_ns=str(1_000_000_000 + index * 100_000_000),
                source_clock="synchronized_ros", source_age_s=.02, received_s=first,
                clock_verified=True, identity_verified=True, provenance="SYNTHETIC_C2_CROSS_TEST",
                binding_id=self.f.binding.binding_id)
            observed = pipeline.process(image, now_s=first)
            p = self.project(now=clock[0], observation=observed)
            self.f.normalizer.receive(p, clock[0])
        self.assertEqual(observed.signal["stable_state"], "GREEN")
        self.assertTrue(observed.context["diagnostics"]["same_content_as_previous"])
        self.assertEqual(p.components["signal"].first_received_s, 10.)
        self.assertEqual(p.components["signal"].source_age_s, .02)
        # C2 additionally rejects an incremented sequence with the old stamp.
        bad = SimpleNamespace(signal=observed.signal, context={**observed.context, "sequence": 6})
        with self.assertRaisesRegex(ObservationRejected, "REPLAY"):
            self.f.normalizer.receive(self.project(now=10.1, observation=bad), 10.1)
        # The actual C4 pipeline also closes repeated source identity.
        clock[0] = 10.1
        repeated = pipeline.process(image, now_s=10.1)
        self.assertIn("REPEATED_OR_REVERSED_FRAME", repeated.signal["quality_flags"])


class C1RuntimeCrossTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.overlay = pinned_dependencies()
        cls.deps = cls.overlay.__enter__()
        cls.addClassCleanup(cls.overlay.__exit__, None, None, None)

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.r, draft = runtime_rig()
        self.lock = asyncio.Lock()
        self.nav = Navigation(self.lock)
        self.path = Path(self.directory.name) / "mission.json"
        self.owner = self.deps.coordinator.MissionCoordinator(self.nav, SavedMaps(), self.path,
            coordination_lock=self.lock, poll_interval_s=.01, cancel_timeout_s=.1)
        self.admission, self.token = object(), object()
        self.owner._managed_admission = self.admission
        visits = ("1" * 32, "2" * 32)
        result = await self.owner.create(label="Round3 actual C1 owner", map_id="a" * 24,
            map_revision="b" * 64, annotation_revision="c" * 64, context_revision="d" * 64,
            waypoints=[{"visit_id": v, "mission_local_pose": POSE, "label": "Leg"} for v in visits])
        scope = replace(draft.scope, mission_run_id=result["mission"]["id"])
        self.gate = self.deps.gate(scope, self.r.clock)
        self.port = CoordinatorNavigationPort(self.owner, self.nav, mission_id=scope.mission_run_id,
            admission=self.admission, native_owner=self.token,
            legs={(scope.step_id, leg): LegBinding(v, tuple(POSE.values()))
                  for leg, v in zip(("approach", "exit"), visits)})
        self.runtime = configure_action(replace(draft.config, scope=scope),
            RuntimePorts(self.port, self.gate), clock=self.r.clock)
        self.r.adapter = self.runtime.adapter  # packet fixture only; integration hooks use public API
        self.plan_started, self.plan_continue = asyncio.Event(), asyncio.Event()
        self.wait_for_plan = False
        self.phases_at_plan = []
        async def preflight(mission):
            if mission["current_index"] == 1:
                self.phases_at_plan.append(self.runtime.snapshot()["state"]["phase"])
                if self.wait_for_plan:
                    self.plan_started.set()
                    await self.plan_continue.wait()
            # Proposed C1 call site at the END of existing awaited planning.
            self.runtime.require_dispatch_authorized(starting=mission["current_index"] == 0)
        self.owner._dispatch_preflight = preflight
        await self.owner.bind_native_owner(scope.mission_run_id, admission=self.admission,
            token=self.token, visits=visits, guard=self.runtime.continuation_proven)

    async def asyncTearDown(self):
        self.plan_continue.set()
        self.nav.cancel_ack = True
        await self.owner.close()

    async def observe(self, now, **kwargs):
        self.r.clock.now = now
        kwargs.setdefault("goal_state", self.port.goal_observation(self.runtime.scope)["goal_state"])
        kwargs.setdefault("cancel_ack", self.nav.goal["state"] == "canceled")
        return await self.runtime.receive(self.r.packet(**kwargs))

    async def hold(self, canceled=False):
        await self.runtime.start("cross-start-request", approach_pose=POSE)
        if canceled:
            await self.observe(0.)
            self.assertEqual(self.runtime.snapshot()["state"]["phase"], "WAIT_CANCEL")
            self.assertEqual(self.nav.goal["state"], "canceled")
        else:
            self.nav.goal["state"] = "succeeded"
            for _ in range(100):
                if self.owner.snapshot(self.runtime.scope.mission_run_id)["mission"]["phase"] == "native_barrier":
                    break
                await asyncio.sleep(.005)
            self.assertEqual(self.owner.snapshot(self.runtime.scope.mission_run_id)["mission"]["phase"], "native_barrier")
        await self.observe(.01)
        await self.observe(.02)
        self.assertEqual(self.runtime.snapshot()["state"]["phase"], "HOLD_SIGNAL")

    async def dwell(self, *, final=True):
        for i in range(11 if final else 10):
            await self.observe(round(.03 + i * .2, 2))

    async def test_success_exactly_one_exit_and_ack_is_not_departure(self):
        await self.hold()
        await self.dwell()
        self.assertEqual(len(self.nav.sent), 2)
        self.assertEqual(self.phases_at_plan, ["EXIT_PREPARE"])
        self.assertFalse(self.runtime.snapshot()["state"]["departed"])
        await self.observe(2.04)
        self.assertFalse(self.runtime.snapshot()["state"]["departed"])
        await self.observe(2.05, body_motion_status="MOVING", extras=Extras(departure_observed=True))
        await self.observe(2.06, raw_state="RED", stable_state="RED", body_motion_status="MOVING")
        self.assertTrue(self.runtime.snapshot()["state"]["departed"])
        self.assertEqual(self.nav.canceled, [])
        self.nav.goal["state"] = "succeeded"
        await self.observe(2.07, raw_state="RED", stable_state="RED")
        self.assertTrue(self.runtime.continuation_proven(completed=True))
        await self.owner.finish_native(self.runtime.scope.mission_run_id, admission=self.admission,
            token=self.token, actual_goal_id=self.runtime.snapshot()["actual_goal_id"])
        self.assertEqual(self.owner.snapshot(self.runtime.scope.mission_run_id)["mission"]["state"], "completed")
        await self.runtime.tick()
        self.assertEqual(len(self.nav.sent), 2)

    async def test_cancel_ack_continues_once_without_external_pause(self):
        await self.hold(canceled=True)
        await self.dwell()
        self.assertEqual(len(self.nav.sent), 2)
        self.assertEqual(len(self.nav.canceled), 1)
        self.assertFalse(self.owner._native_owners[self.runtime.scope.mission_run_id].get("external_stop", False))

    async def test_delayed_hold_install_and_physical_stop_are_distinct(self):
        self.gate.closed = True  # an uninstalled HOLD produces no ACK
        await self.runtime.start("cross-start-request", approach_pose=POSE)
        await self.observe(0.)
        await self.observe(.01)
        await self.observe(.02)
        self.assertEqual(self.runtime.snapshot()["state"]["phase"], "HOLD_ACK")
        self.assertIsNone(self.runtime.snapshot()["state"]["dwell_start"])
        self.assertEqual(len(self.nav.sent), 1)

    async def test_exit_waits_for_hold_install_then_preflight_sees_prepare(self):
        await self.hold(canceled=True)
        await self.dwell(final=False)
        original = self.gate.apply
        pending = []
        async def delay(request):
            if request.scope.goal_generation == 2:
                pending.append(request)
                return None
            return await original(request)
        self.gate.apply = delay
        await self.observe(2.03)
        self.assertEqual(self.runtime.snapshot()["state"]["phase"], "EXIT_PREPARE")
        self.assertFalse(self.runtime.continuation_proven())
        self.assertEqual(len(self.nav.sent), 1)
        self.r.clock.now = 2.04
        await original(pending[0])
        await self.runtime.tick()
        self.assertEqual(len(self.nav.sent), 2)
        self.assertEqual(self.phases_at_plan, ["EXIT_PREPARE"])

    async def test_red_while_exit_hold_ack_pending_invalidates_before_dispatch(self):
        await self.hold(canceled=True)
        await self.dwell(final=False)
        original = self.gate.apply
        async def delay(request):
            if request.scope.goal_generation == 2:
                return None
            return await original(request)
        self.gate.apply = delay
        await self.observe(2.03)
        self.r.clock.now = 2.04
        # Independent safety/signal facts for the newly reserved scope; no exit
        # goal has been issued and no navigation ACTIVE ACK is invented.
        p = self.r.packet(raw_state="RED", stable_state="RED", goal_state="CANCELED")
        p = replace(p, components={k: v for k, v in p.components.items() if k != "navigation"})
        await self.runtime.receive(p)
        self.assertEqual(self.runtime.snapshot()["state"]["phase"], "FAILED")
        self.assertIn("EXIT_PROOF_INVALIDATED", self.runtime.snapshot()["state"]["reason"])
        self.assertEqual(len(self.nav.sent), 1)

    async def pending_exit(self):
        await self.hold(canceled=True)
        await self.dwell(final=False)
        self.wait_for_plan = True
        task = asyncio.create_task(self.observe(2.03))
        await asyncio.wait_for(self.plan_started.wait(), 1)
        self.assertEqual(len(self.nav.sent), 1)
        return task

    async def test_stop_during_preexit_planning_prevents_goal(self):
        task = await self.pending_exit()
        # C1 retains its immediate gate + coordinator fence before durable IO.
        self.gate.retire()
        self.owner.fence_native_stop(self.runtime.scope.mission_run_id, token=self.token)
        stop = asyncio.create_task(self.runtime.stop("cross-stop-request"))
        await asyncio.sleep(0)
        self.plan_continue.set()
        await asyncio.gather(task, stop, return_exceptions=True)
        self.assertEqual(len(self.nav.sent), 1)
        self.assertFalse(self.runtime.continuation_proven())
        self.assertTrue(self.runtime.snapshot()["stop_requested"])

    async def test_operator_pause_during_planning_prevents_goal(self):
        task = await self.pending_exit()
        pause = asyncio.create_task(self.owner.pause(self.runtime.scope.mission_run_id))
        await asyncio.sleep(0)
        self.plan_continue.set()
        await asyncio.gather(task, pause, return_exceptions=True)
        self.assertEqual(len(self.nav.sent), 1)
        self.assertTrue(self.owner._native_owners[self.runtime.scope.mission_run_id]["external_stop"])

    async def test_old_release_during_planning_invalidates_guard(self):
        task = await self.pending_exit()
        previous = replace(self.runtime.scope, goal_id=self.r.scope.goal_id, goal_generation=1)
        await self.gate.apply(ConstraintRequest(previous, "late-old-release", "RELEASE", "late", sequence=1))
        self.assertTrue(self.gate.closed)
        self.assertFalse(self.runtime.continuation_proven())
        self.plan_continue.set()
        result = await asyncio.gather(task, return_exceptions=True)
        self.assertIsInstance(result[0], Exception)
        self.assertEqual(len(self.nav.sent), 1)

    async def test_expired_proof_during_planning_prevents_goal(self):
        task = await self.pending_exit()
        self.r.clock.now = 2.280001  # last physical/green sample was 2.03
        self.assertFalse(self.runtime.continuation_proven())
        self.plan_continue.set()
        result = await asyncio.gather(task, return_exceptions=True)
        self.assertIsInstance(result[0], Exception)
        self.assertEqual(len(self.nav.sent), 1)

    async def test_installed_hold_without_physical_stop_never_starts_dwell(self):
        await self.hold(canceled=True)
        for i in range(12):
            await self.observe(round(.03 + i * .2, 2), body_motion_status="MOVING")
        self.assertEqual(self.runtime.snapshot()["state"]["phase"], "HOLD_SIGNAL")
        self.assertIsNone(self.runtime.snapshot()["state"]["dwell_start"])
        self.assertEqual(len(self.nav.sent), 1)

    async def before_departure_fault(self, color):
        await self.hold(canceled=True)
        await self.dwell()
        await self.observe(2.04)
        self.r.clock.now = 2.05
        p = self.r.packet(raw_state=color if color != "stale" else "GREEN",
                          stable_state=color if color != "stale" else "GREEN")
        if color == "stale":
            p = replace(p, components={**p.components, "signal":
                        replace(p.components["signal"], source_age_s=.250001)})
        await self.runtime.receive(p)
        self.assertEqual(self.runtime.snapshot()["state"]["phase"], "FAILED")
        self.assertFalse(self.runtime.snapshot()["state"]["departed"])
        self.assertEqual(self.nav.goal["state"], "canceled")
        self.assertFalse(self.runtime.command_context().inputs_fresh)

    async def test_red_before_departure_stops(self):
        await self.before_departure_fault("RED")

    async def test_unknown_before_departure_stops(self):
        await self.before_departure_fault("UNKNOWN")

    async def test_stale_before_departure_stops(self):
        await self.before_departure_fault("stale")

    async def after_departure_fault(self, kind):
        await self.hold(canceled=True)
        await self.dwell()
        await self.observe(2.04)
        await self.observe(2.05, body_motion_status="MOVING", extras=Extras(departure_observed=True))
        self.assertTrue(self.runtime.snapshot()["state"]["departed"])
        if kind == "expiry":
            self.r.clock.now = 2.300001
            await self.runtime.tick()
        else:
            await self.observe(2.06, extras=Extras(**{kind: True}))
        self.assertEqual(self.runtime.snapshot()["state"]["phase"], "FAILED")
        self.assertEqual(self.nav.goal["state"], "canceled")
        context = self.runtime.command_context()
        self.assertEqual(self.gate.boundary.evaluate(
            Command(context.scope, 100, self.r.clock.now, (.2, 0., 0.)), now=self.r.clock.now,
            goal_scope=context.scope, goal_receipt_s=context.goal_receipt_s,
            inputs_fresh=context.inputs_fresh, estop=context.estop, collision=context.collision)[0], (0., 0., 0.))

    async def test_collision_after_departure_still_stops(self):
        await self.after_departure_fault("collision")

    async def test_estop_after_departure_still_stops(self):
        await self.after_departure_fault("estop")

    async def test_input_expiry_after_departure_still_stops(self):
        await self.after_departure_fault("expiry")

    async def test_source_progress_cannot_be_faked_by_receipt_progress(self):
        await self.hold(canceled=True)
        for i in range(11):
            self.r.clock.now = round(.03 + i * .2, 2)
            packet = self.r.packet(goal_state="CANCELED", cancel_ack=True)
            parts = dict(packet.components)
            for name in ("feet", "motion"):
                parts[name] = replace(parts[name], source_stamp_ns=str(30_000_000 + i))
            await self.runtime.receive(replace(packet, components=parts))
        self.assertEqual(self.runtime.snapshot()["state"]["phase"], "HOLD_SIGNAL")
        self.assertEqual(len(self.nav.sent), 1)

    async def test_1200_ticks_use_no_new_action_requests_or_observation_time(self):
        await self.hold(canceled=True)
        await self.observe(.03, raw_state="RED", stable_state="RED")
        before = copy.deepcopy(self.runtime.snapshot())
        for _ in range(1200):
            await self.runtime.tick()
        after = self.runtime.snapshot()
        self.assertEqual(after["request_counts"], before["request_counts"])
        self.assertEqual(after["state"]["last_valid_s"], before["state"]["last_valid_s"])
        self.assertEqual(len(self.gate.requests), 1)

    async def test_restart_retains_no_executable_native_owner_or_command(self):
        await self.hold(canceled=True)
        await self.dwell()
        await self.observe(2.04)
        command = Command(self.runtime.scope, 1, 2.04, (.2, 0., 0.))
        context = self.runtime.command_context()
        self.assertEqual(self.gate.boundary.evaluate(command, now=2.04,
            goal_scope=context.scope, goal_receipt_s=context.goal_receipt_s,
            inputs_fresh=context.inputs_fresh)[1], "TRACKING")
        self.gate.retire()
        await self.runtime.cleanup("cross-cleanup-request")
        self.assertEqual(self.gate.boundary.evaluate(replace(command, sequence=2), now=2.04)[0], (0., 0., 0.))
        self.assertEqual((await self.runtime.tick())["state"]["phase"], "INTERRUPTED")
        await self.owner.close()
        restored = self.deps.coordinator.MissionCoordinator(self.nav, SavedMaps(), self.path,
            coordination_lock=self.lock)
        restored._managed_admission = self.admission
        try:
            with self.assertRaisesRegex(Exception, "NATIVE_OWNER_REQUIRED"):
                await restored.start(self.runtime.scope.mission_run_id, admission=self.admission,
                                     native_owner=self.token)
        finally:
            await restored.close()
