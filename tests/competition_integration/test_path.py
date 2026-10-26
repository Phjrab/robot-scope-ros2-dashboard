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


from competition_integration.harness import SoftwareHarness


class IntegrationPathTests(SoftwareHarness, unittest.IsolatedAsyncioTestCase):
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
        old_release = next(iter(self.session.gate.requests.values()))
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

    async def test_operator_pause_cannot_be_consumed_as_native_cancel_continuation(self):
        await self.terminal(canceled=True)
        await self.coordinator.pause(self.session.adapter.scope.mission_run_id)
        self.assertEqual(self.command()[0], (0., 0., 0.))
        with self.assertRaisesRegex(MissionConflict, 'NATIVE_CONTINUATION_NOT_PROVEN'):
            for _ in range(24):
                await self.tick()
        self.assertEqual(self.session.adapter.state.phase, 'FAILED')
        self.assertEqual(len(self.nav.sent), 1)
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_late_plan_rechecks_age_before_exit_goal(self):
        await self.terminal()
        async def delayed(mission):
            if mission['current_index'] == 1:
                self.clock.now += .251
        self.coordinator._dispatch_preflight = delayed
        with self.assertRaisesRegex(MissionConflict, 'NATIVE_DISPATCH_PROOF_EXPIRED'):
            for _ in range(24):
                await self.tick()
        self.assertEqual(len(self.nav.sent), 1)
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_terminal_poll_does_not_repeat_coordinator_completion(self):
        await self.exit_ready()
        await self.tick()
        await self.tick(body_motion_status='MOVING', extras=Extras(departure_observed=True))
        self.nav.goal['state'] = 'succeeded'
        await self.tick()
        for n in range(10):
            await self.session.observe(f'terminal-poll-{n:08}')
        self.assertEqual(len(self.nav.sent), 2)
        self.assertFalse(self.coordinator.blocks_navigation_goal())

    async def test_old_release_during_delayed_plan_invalidates_final_guard(self):
        from robot_dashboard.mission_routes.competition_native.contracts import ConstraintRequest
        await self.terminal()
        old_scope = self.session.adapter.scope
        async def delayed(mission):
            if mission['current_index'] == 1:
                await self.session.gate.apply(ConstraintRequest(old_scope,
                    'old-release-race-0001', 'RELEASE', 'retired', sequence=99))
        self.coordinator._dispatch_preflight = delayed
        with self.assertRaisesRegex(MissionConflict, 'NATIVE_DISPATCH_PROOF_EXPIRED'):
            for _ in range(24):
                await self.tick()
        self.assertEqual(len(self.nav.sent), 1)
        self.assertEqual(self.command()[0], (0., 0., 0.))
