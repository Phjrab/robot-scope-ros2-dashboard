"""Real D0/C4 pipeline, C2 state/ports, service ledger and MissionCoordinator.

Only RGB detector, clocks, map/navigation/planner/actuator boundaries are fake.
These tests are software evidence and never claim sensor/physical qualification.
"""
import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from competition_traffic import optional_deps  # noqa: F401
from competition_traffic.helpers import config, frame, lamp, Detector
from competition_native.helpers import Rig, POSE, ALL_CAPS
from competition_native.test_coordinator import Navigation, SavedMaps
from robot_dashboard.application.mission_coordinator import MissionCoordinator, MissionConflict
from robot_dashboard.competition_traffic.pipeline import TrafficPipeline
from robot_dashboard.competition_traffic.worker import TrafficWorker
from robot_dashboard.mission_routes.service import MissionRoutes
from robot_dashboard.mission_routes.competition_native.contracts import Activation, TimingPolicy
from robot_dashboard.mission_routes.competition_native.coordinator import LegBinding
from robot_dashboard.mission_routes.competition_native.authority import Command
from robot_dashboard.mission_routes.competition_native.observations import Extras


class IntegrationPathTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.lock = asyncio.Lock()
        self.nav = Navigation(self.lock)
        self.coordinator = MissionCoordinator(self.nav, SavedMaps(), self.root/'missions',
            coordination_lock=self.lock, poll_interval_s=.05, cancel_timeout_s=.1)
        self.service = MissionRoutes(self.root/'plans', SavedMaps(), None, self.coordinator,
                                     SimpleNamespace(snapshot=lambda: {}), None)
        # Explicit isolated planner boundary; no native availability is asserted.
        self.preflights = []
        async def preflight(mission):
            self.preflights.append(mission['current_index'])
        self.coordinator._dispatch_preflight = preflight
        self.visits = ('1'*32, '2'*32)
        result = await self.coordinator.create(label='Synthetic native traffic',
            map_id='a'*24, map_revision='b'*64, annotation_revision='c'*64,
            context_revision='d'*64, waypoints=[{'visit_id': v, 'label': 'Leg',
                'mission_local_pose': POSE} for v in self.visits])
        self.rig = Rig()
        self.clock = self.rig.clock
        scope = replace(self.rig.scope, mission_run_id=result['mission']['id'])
        action = self.rig.adapter.action.model_dump()
        action.update(signal_id='signal_01', crossing_id='crossing_01')
        bindings = dict(self.rig.bindings)
        bindings['signal'] = replace(bindings['signal'], producer_id='camera-1')
        self.cfg = config()
        self.worker = TrafficWorker(TrafficPipeline(self.cfg, Detector(), clock=self.clock), clock=self.clock)
        self.worker.start()
        self.session = await self.service.create_software_native_session(scope=scope, action=action,
            legs={(scope.step_id, leg): LegBinding(v, tuple(POSE.values()))
                  for leg, v in zip(('approach', 'exit'), self.visits)},
            policy=TimingPolicy(.25, .25, .25, .25), bindings=bindings,
            activation=Activation(True, True, 'isolated-test-ports', 'synthetic-only', ALL_CAPS),
            clock=self.clock, traffic_config_hash=self.cfg.sha256, worker=self.worker)
        self.rig.adapter = self.session.adapter
        self.number = 0
        self.command_seq = 0
        await self.session.start('native-start-00000001', approach_pose=POSE)

    async def asyncTearDown(self):
        self.nav.cancel_ack = True
        await self.service.close()
        await self.coordinator.close()
        self.temp.cleanup()

    async def tick(self, *, color='GREEN', advance=.1, source_advance_ns=None, **fields):
        self.clock.now = round(self.clock.now + advance, 6)
        self.number += 1
        rgb = lamp((0, 230, 0) if color == 'GREEN' else (0, 0, 230) if color == 'RED' else (0, 0, 0))
        f = frame(self.number, image=rgb, received_s=self.clock.now,
                  source_stamp_ns=str(round(self.clock.now*1e9)))
        self.worker.offer(f)
        await self.worker.queue.join()
        packet = self.rig.packet(**fields)
        observed = self.session.port.goal_observation(self.session.adapter.scope)
        packet = replace(packet, evidence={**packet.evidence, **observed})
        if source_advance_ns is not None:
            stamps = dict(packet.components)
            for name in ('feet', 'motion'):
                previous = self.session.adapter.normalizer.received[name].stamp
                stamps[name] = replace(stamps[name], source_stamp_ns=str(int(previous.source_stamp_ns) + source_advance_ns))
            packet = replace(packet, components=stamps)
        self.last_packet = packet
        self.last_sample = self.worker.latest
        return await self.session.observe(f'native-event-{self.number:08}', packet, sample=self.last_sample)

    def command(self):
        self.command_seq += 1
        return self.session.command(Command(self.session.adapter.scope, self.command_seq,
                                            self.clock.now, (.2, 0., 0.)))

    async def terminal(self, *, canceled=False):
        if canceled:
            await self.tick()  # two feet INSIDE requests actual coordinator pause/cancel
            self.assertEqual(self.session.adapter.state.phase, 'WAIT_CANCEL')
            self.assertEqual(self.nav.goal['state'], 'canceled')
        else:
            self.nav.goal['state'] = 'succeeded'
            for _ in range(30):
                if self.coordinator.snapshot(self.session.adapter.scope.mission_run_id)['mission']['phase'] == 'native_barrier':
                    break
                await asyncio.sleep(.01)
        await self.tick()
        self.assertEqual(self.session.adapter.state.phase, 'HOLD_ACK')
        await self.tick()
        self.assertEqual(self.session.adapter.state.phase, 'HOLD_SIGNAL')

    async def exit_ready(self, *, canceled=False):
        await self.terminal(canceled=canceled)
        for _ in range(23):
            await self.tick()
            if self.session.adapter.state.phase == 'EXIT_PENDING':
                break
        self.assertEqual(self.session.adapter.state.phase, 'EXIT_PENDING')
        self.assertEqual(len(self.nav.sent), 2)
        self.assertEqual(self.preflights, [0, 1])

    async def test_approach_signal_does_not_hold_tracking(self):
        await self.tick(color='RED', front_left_status='OUTSIDE', front_right_status='OUTSIDE')
        self.assertEqual(self.session.adapter.state.phase, 'APPROACH')
        self.assertEqual(self.command()[0], (.2, 0., 0.))
        self.assertIsNone(self.session.adapter._constraint)

    async def test_terminal_hold_ack_is_not_physical_stop_or_two_second_dwell(self):
        await self.terminal()
        for _ in range(25):
            await self.tick(body_motion_status='MOVING')
        self.assertEqual(len(self.nav.sent), 1)
        self.assertIsNone(self.session.adapter.state.dwell_start)
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_success_barrier_cannot_be_operator_confirmed_or_skipped(self):
        await self.terminal()
        mid = self.session.adapter.scope.mission_run_id
        mission = self.coordinator.snapshot(mid)['mission']
        self.assertEqual(mission['phase'], 'native_barrier')
        self.assertIsNone(mission['confirmation_token'])
        for action in ('resume', 'skip'):
            with self.assertRaisesRegex(MissionConflict, 'NATIVE_OWNER'):
                await getattr(self.coordinator, action)(mid, admission=self.service._admission)
        self.assertEqual(len(self.nav.sent), 1)

    async def test_success_exit_ack_is_not_departure_and_red_stops_before_departure(self):
        await self.exit_ready()
        self.assertFalse(self.session.adapter.state.departed)
        await self.tick(color='RED')
        self.assertEqual(self.session.adapter.state.phase, 'FAILED')
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_canceled_approach_atomic_exit_and_postdeparture_red(self):
        await self.exit_ready(canceled=True)
        await self.tick()  # fresh exit goal ACK permits RELEASE, not departure
        self.assertFalse(self.session.adapter.state.departed)
        self.assertEqual(self.command()[0], (.2, 0., 0.))
        await self.tick(body_motion_status='MOVING', extras=Extras(departure_observed=True))
        self.assertTrue(self.session.adapter.state.departed)
        await self.tick(color='RED', body_motion_status='MOVING', extras=Extras(departure_observed=True))
        self.assertEqual(self.session.adapter.state.phase, 'DEPARTING')
        self.assertEqual(self.command()[0], (.2, 0., 0.))
        self.assertTrue(self.coordinator.blocks_navigation_goal())

    async def test_duplicate_callback_and_polling_do_not_extend_first_receipt(self):
        await self.terminal()
        await self.tick()
        before = self.session.adapter.normalizer.received['signal'].receipt_s
        result = await self.session.observe(f'native-event-{self.number:08}', self.last_packet, sample=self.last_sample)
        self.assertEqual(result['state']['phase'], 'HOLD_SIGNAL')
        self.clock.now += .3
        await self.session.observe('native-poll-00000001')
        self.assertEqual(self.session.adapter.normalizer.received['signal'].receipt_s, before)
        self.assertEqual(len(self.nav.sent), 1)

    async def test_unknown_and_stale_signal_stop_before_departure(self):
        await self.exit_ready()
        await self.tick(color='UNKNOWN')
        self.assertEqual(self.session.adapter.state.phase, 'FAILED')
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_estop_collision_old_epoch_foreign_goal_and_stale_release_are_closed(self):
        await self.tick(front_left_status='OUTSIDE', front_right_status='OUTSIDE')
        old_release = self.session.gate.requests['approach-tracking']
        await self.tick(extras=Extras(collision=True))
        self.assertEqual(self.session.adapter.state.reason, 'COLLISION')
        self.assertIsNone(await self.session.gate.apply(old_release))
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_foreign_goal_is_rejected_at_single_command_boundary(self):
        await self.tick(front_left_status='OUTSIDE', front_right_status='OUTSIDE')
        self.nav.goal['goal_id'] = 'foreign-navigation-goal'
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_reconnect_restart_and_uncertain_cancel_never_restore_nonzero(self):
        await self.tick(front_left_status='OUTSIDE', front_right_status='OUTSIDE')
        self.nav.cancel_ack = False
        await self.session.stop('native-restart-000001', restart=True)
        self.assertEqual(self.command()[0], (0., 0., 0.))
        self.assertIn('UNCONFIRMED', self.session.adapter.state.reason)
        self.assertTrue(self.coordinator.blocks_navigation_goal())
        self.nav.cancel_ack = True
        self.nav.goal['state'] = 'canceled'
        restarted = MissionCoordinator(self.nav, SavedMaps(), self.root/'missions', coordination_lock=self.lock)
        restarted._managed_admission = self.service._admission
        with self.assertRaisesRegex(MissionConflict, 'NATIVE_OWNER'):
            await restarted.start(self.session.adapter.scope.mission_run_id, admission=self.service._admission)
        await restarted.close()

    async def test_old_camera_epoch_cannot_be_joined(self):
        await self.tick(front_left_status='OUTSIDE', front_right_status='OUTSIDE')
        bad = replace(self.last_sample, frame=replace(self.last_sample.frame, producer_epoch='retired-epoch'))
        with self.assertRaisesRegex(ValueError, 'SIGNAL_BINDING'):
            await self.session.observe('native-old-epoch-0001', self.rig.packet(), sample=bad)
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_new_sequences_without_two_seconds_of_source_time_never_depart(self):
        await self.terminal()
        for _ in range(25):
            await self.tick(source_advance_ns=1)
        self.assertEqual(len(self.nav.sent), 1)
        self.assertEqual(self.session.adapter.state.phase, 'HOLD_SIGNAL')

    async def test_missing_hold_ack_never_counts_physical_stop(self):
        with patch.object(self.session.gate, 'ack', return_value=None):
            self.nav.goal['state'] = 'succeeded'
            await self.tick()
            for _ in range(25):
                await self.tick()
        self.assertEqual(self.session.adapter.state.phase, 'HOLD_ACK')
        self.assertEqual(len(self.nav.sent), 1)

    async def test_source_receipt_age_is_not_refreshed_by_late_join(self):
        await self.tick(front_left_status='OUTSIDE', front_right_status='OUTSIDE')
        self.clock.now += .26
        with self.assertRaisesRegex(ValueError, 'EXPIRED'):
            await self.session.observe('native-late-join-001', self.rig.packet(), sample=self.last_sample)
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_stale_signal_at_command_time_cannot_wait_for_next_poll(self):
        await self.exit_ready()
        await self.tick()
        self.clock.now += .251
        self.assertEqual(self.command()[0], (0., 0., 0.))
        await self.session.observe('native-stale-poll-001')
        self.assertEqual(self.session.adapter.state.phase, 'FAILED')

    async def test_estop_after_departure_overrides_release(self):
        await self.exit_ready()
        await self.tick()
        await self.tick(body_motion_status='MOVING', extras=Extras(departure_observed=True))
        await self.tick(extras=Extras(estop=True))
        self.assertEqual(self.session.adapter.state.reason, 'ESTOP')
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_completion_releases_coordinator_owner_only_after_departure(self):
        await self.exit_ready()
        await self.tick()
        await self.tick(body_motion_status='MOVING', extras=Extras(departure_observed=True))
        self.nav.goal['state'] = 'succeeded'
        await self.tick()
        self.assertEqual(self.session.adapter.state.phase, 'SUCCEEDED')
        self.assertFalse(self.coordinator.blocks_navigation_goal())
        self.assertEqual(self.command()[0], (0., 0., 0.))
        self.assertEqual(len(self.nav.sent), 2)

    async def test_durable_payload_conflict_cannot_replay_callback(self):
        await self.tick(front_left_status='OUTSIDE', front_right_status='OUTSIDE')
        with self.assertRaisesRegex(MissionConflict, 'PAYLOAD_CONFLICT'):
            await self.session.observe(f'native-event-{self.number:08}', self.rig.packet(), sample=self.last_sample)
        self.assertEqual(len(self.nav.sent), 1)
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_stop_while_exit_preflight_awaits_never_sends_second_goal(self):
        await self.terminal()
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(mission):
            if mission['current_index'] == 1:
                entered.set()
                await release.wait()
        self.coordinator._dispatch_preflight = delayed
        async def dwell():
            for _ in range(24):
                await self.tick()
        pending = asyncio.create_task(dwell())
        await asyncio.wait_for(entered.wait(), 2)
        stopping = asyncio.create_task(self.session.stop('native-racing-stop-01'))
        await asyncio.sleep(0)
        self.assertEqual(self.command()[0], (0., 0., 0.))
        release.set()
        await asyncio.gather(pending, stopping, return_exceptions=True)
        self.assertEqual(len(self.nav.sent), 1)
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_d0_reference_and_c2_share_terminal_ack_and_stop_separation(self):
        from experiments.competition_vm.traffic_signals.lifecycle import TrafficLifecycle, ActionEvent
        from experiments.competition_vm.traffic_signals.core import StopInput
        ref = TrafficLifecycle('vm-run', 'signal-step', 'crossing-1', 'visit-1',
                               'signal_01', 0, 'stop_zone_01', 'approach', 1)
        event = ActionEvent('APPROACH_TERMINAL', 'vm-run', 'signal-step', 'approach',
                            1, 'actions-1', 1, 0., status='SUCCEEDED')
        self.assertTrue(ref.accept_event(event, now=0.))
        observation = StopInput(.1, 1, stable_state='GREEN', left_inside=True,
                                right_inside=True, body_stopped=True)
        result = ref.observe(observation, now=.1, pose_age_s=0.)
        self.assertEqual(result['reason'], 'WAIT_MATCHING_HOLD_ACK')
        self.assertEqual(result['motion_constraint']['mode'], 'HOLD')
        await self.terminal()
        self.assertEqual(self.command()[0], (0., 0., 0.))
        self.assertEqual(len(self.nav.sent), 1)
