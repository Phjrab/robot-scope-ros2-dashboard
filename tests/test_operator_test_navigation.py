"""Robot-free contracts for the real mission owner and operator permission.

These tests submit goals only to an in-memory NavigationPort. Their results
are software evidence, never evidence of physical stopping or departure.
"""
from __future__ import annotations

import asyncio
import copy
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from robot_dashboard.application.mission_coordinator import MissionConflict, MissionCoordinator
from robot_dashboard.application.operator_test import OperatorTestGate
from robot_dashboard.application.navigation_coordinator import NavigationCoordinator
from robot_dashboard.navigation_jobs import NavigationPoseError


MAP_ID = 'a' * 24
MAP_REVISION = 'b' * 64
ANNOTATION_REVISION = 'c' * 64
FIRST = 'd' * 24
SECOND = 'e' * 24


class Clock:
    def __init__(self):
        self.now = 100.

    def __call__(self):
        return self.now


def live_health():
    return {'fresh': True, 'ready': True, 'runtime_instance_generation': 'runtime-1',
            'operational_3d': {'source': 'STORED_PCD_FASTLIO', 'ready': True,
                'bundle_generation': 'bundle-1', 'localization_generation': 1,
                'linear_speed_mps': 0., 'angular_speed_rps': 0., 'stopped_seconds': 0.}}


class OperatorTestGateTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.health = Clock(), live_health()
        self.gate = OperatorTestGate(lambda: copy.deepcopy(self.health), self.clock)

    def test_arrival_and_measured_stop_both_need_two_seconds(self):
        self.health['operational_3d']['stopped_seconds'] = 20.
        self.assertFalse(self.gate.stopped(), 'being stationary before arrival is insufficient')
        self.gate.arrived()
        self.clock.now += 1.99
        self.assertFalse(self.gate.stopped())
        with self.assertRaisesRegex(ValueError, 'STOP_DWELL'):
            self.gate.release(request_id='request-00000001', run_id='run', step_id='step', token='token')
        self.clock.now += .02
        self.health['operational_3d']['stopped_seconds'] = .1
        self.assertFalse(self.gate.stopped(), 'Nav2 success alone cannot establish physical stop')
        self.health['operational_3d']['stopped_seconds'] = 2.01
        self.assertTrue(self.gate.stopped())

    def test_release_is_separate_from_sensor_green_and_expires_before_dispatch(self):
        self.gate.arrived()
        self.clock.now += 2.1
        self.health['operational_3d']['stopped_seconds'] = 2.1
        event = self.gate.release(request_id='request-00000001', run_id='run', step_id='step', token='token')
        self.assertEqual(event['source'], 'OPERATOR_TEST')
        self.assertEqual(event['completion_profile'], 'NAV_STOP_POINT_TEST')
        self.assertEqual(event['departure'], 'NOT_DISPATCHED')
        self.assertNotIn('GREEN', self.health.values())
        self.gate.require_dispatch(1)
        self.clock.now += 2.01
        with self.assertRaisesRegex(ValueError, 'CURRENT_OPERATOR_TEST_RELEASE_REQUIRED'):
            self.gate.require_dispatch(1)

    def test_dispatch_consumes_one_release_and_new_stop_has_new_generation(self):
        self.gate.arrived()
        self.clock.now += 2.1
        self.health['operational_3d']['stopped_seconds'] = 2.1
        self.gate.release(request_id='request-00000001', run_id='run', step_id='first', token='token')
        self.gate.dispatched()
        self.assertEqual(self.gate.last_event['departure'], 'GOAL_DISPATCHED')
        with self.assertRaises(ValueError):
            self.gate.require_dispatch(1)
        self.gate.arrived()
        self.assertEqual(self.gate.stop_generation, 2)
        self.assertFalse(self.gate.stopped())
        with self.assertRaises(ValueError):
            self.gate.require_dispatch(2)

    def test_runtime_map_or_localization_generation_change_invalidates_permission(self):
        for change in ('runtime', 'bundle', 'localization'):
            with self.subTest(change=change):
                health = live_health()
                gate = OperatorTestGate(lambda: copy.deepcopy(health), self.clock)
                gate.arrived()
                self.clock.now += 2.1
                health['operational_3d']['stopped_seconds'] = 2.1
                if change == 'runtime':
                    health['runtime_instance_generation'] = 'runtime-2'
                elif change == 'bundle':
                    health['operational_3d']['bundle_generation'] = 'bundle-2'
                else:
                    health['operational_3d']['localization_generation'] = 2
                rejected = gate.snapshot()
                self.assertFalse(rejected['ready'])
                self.assertIn('GENERATION_CHANGED', rejected['reason'])
                with self.assertRaisesRegex(ValueError, 'REAUTHORIZATION_REQUIRED'):
                    gate.release(request_id='request-00000001', run_id='run', step_id='step', token='token')

    def test_stale_missing_or_nonfinite_real_stop_evidence_fails_closed(self):
        for key, value in (('linear_speed_mps', None), ('angular_speed_rps', float('nan')),
                           ('stopped_seconds', True), ('stopped_seconds', -1.)):
            with self.subTest(key=key, value=value):
                health = live_health()
                health['operational_3d'][key] = value
                with self.assertRaisesRegex(ValueError, 'MEASURED_STOP_EVIDENCE_REQUIRED'):
                    OperatorTestGate(lambda: health, self.clock)
        self.health['fresh'] = False
        rejected = self.gate.snapshot()
        self.assertFalse(rejected['ready'])
        self.assertEqual(rejected['reason'], 'LIVE_3D_LOCALIZATION_REQUIRED')
        with self.assertRaisesRegex(ValueError, 'REAUTHORIZATION_REQUIRED'):
            self.gate.require_source()

    def test_observed_source_loss_latches_current_stop_permission_invalid(self):
        self.gate.arrived()
        self.clock.now += 2.1
        self.health['operational_3d']['stopped_seconds'] = 2.1
        self.gate.release(request_id='request-00000001', run_id='run', step_id='step', token='token')
        self.health['fresh'] = False
        self.assertFalse(self.gate.snapshot()['ready'])
        self.health['fresh'] = True
        self.assertFalse(self.gate.snapshot()['ready'], 'recovered telemetry cannot revive the old stop permission')
        with self.assertRaises(ValueError):
            self.gate.require_dispatch(1)


class Maps:
    def annotations(self, map_id):
        return {'map_id': map_id, 'map_revision': MAP_REVISION,
                'annotation_revision': ANNOTATION_REVISION,
                'points': [{'id': FIRST, 'type': 'HOME', 'name': 'First'},
                           {'id': SECOND, 'type': 'POI', 'name': 'Second'}]}


class Navigation:
    def __init__(self):
        self.sent, self.canceled = [], []
        self.goal = {'state': 'idle', 'goal_id': None}
        self.ready = True

    def view(self):
        return {'pipeline': {'state': 'running'}, 'map': {'id': MAP_ID, 'revision': MAP_REVISION},
                'localization': {'state': 'localized'}, 'safety': {'can_send_goal': self.ready},
                'goal': dict(self.goal)}

    async def send_annotation_goal(self, **kwargs):
        if self.goal['state'] in {'pending', 'active', 'canceling'}:
            raise AssertionError('second concurrent navigation goal')
        self.sent.append(kwargs)
        self.goal = {'state': 'active', 'goal_id': f'{len(self.sent):032x}'}
        return {'navigation': self.view()}

    async def cancel_goal(self, *, goal_id):
        self.canceled.append(goal_id)
        self.goal = {'state': 'canceled', 'goal_id': goal_id}
        return {'navigation': self.view()}


async def until(predicate, *, timeout=2.):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(.01)
    raise AssertionError('mission owner did not reach expected state')


class OperatorTestMissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / 'missions'
        self.navigation, self.clock, self.health = Navigation(), Clock(), live_health()
        self.owner = MissionCoordinator(self.navigation, Maps(), self.root,
                                        poll_interval_s=.05, monotonic=self.clock)
        self.owner._operational_health = lambda: copy.deepcopy(self.health)
        result = await self.owner.create(label='Operator stop points', map_id=MAP_ID,
            map_revision=MAP_REVISION, annotation_revision=ANNOTATION_REVISION,
            waypoints=[{'annotation_id': item, 'hold_seconds': 0.,
                        'requires_operator_confirmation': False, 'label': item[:4]}
                       for item in (FIRST, SECOND)])
        self.id = result['mission']['id']

    async def asyncTearDown(self):
        await self.owner.close()
        self.tmp.cleanup()

    def mission(self):
        return self.owner.snapshot(self.id)['mission']

    async def test_real_navigation_clearance_rejection_is_abortable_without_action_submission(self):
        calls = []

        def reject_pose(**kwargs):
            raise NavigationPoseError('pose must be inside known-free map space with robot-radius clearance')

        def action(**kwargs):
            calls.append(kwargs)
            raise AssertionError('unsafe pose reached the ROS action consumer')

        coordinator = NavigationCoordinator(
            SimpleNamespace(navigation_runtime_snapshot=lambda: {'safety': {'can_send_goal': True}},
                navigation_send_guarded_goal=action),
            SimpleNamespace(validate_active_pose=reject_pose),
            SimpleNamespace(activity=lambda: (False, []), pipeline_state=lambda: 'running'),
            SimpleNamespace(resolve_annotation_goal=lambda *args: SimpleNamespace(x=-.5, y=.29, yaw=0.)),
            coordination_lock=asyncio.Lock(), require_lifecycle_idle=lambda: None)
        self.navigation.send_annotation_goal = coordinator.send_annotation_goal
        await self.owner.enable_operator_test(self.id)
        with self.assertRaisesRegex(MissionConflict, 'robot-radius clearance'):
            await self.owner.start(self.id)
        self.assertEqual(self.mission()['phase'], 'dispatch_rejected')
        self.assertIsNone(self.mission()['current_waypoint']['goal_id'])
        self.assertEqual(calls, [])
        await self.owner.abort(self.id)
        self.assertEqual(self.mission()['outcome'], 'aborted')
        self.assertFalse(self.mission()['ownership_active'])
        self.assertEqual(self.navigation.canceled, [])

    async def enabled_start(self):
        await self.owner.enable_operator_test(self.id)
        await self.owner.start(self.id)
        self.assertEqual(len(self.navigation.sent), 1)

    async def arrive(self):
        self.navigation.goal['state'] = 'succeeded'
        await until(lambda: self.mission()['phase'] == 'holding')

    async def wait_green(self):
        await self.arrive()
        self.clock.now += 2.1
        self.health['operational_3d']['stopped_seconds'] = 2.1
        await until(lambda: self.mission()['phase'] == 'after_arrival_confirmation')

    def release_args(self, request='request-00000001'):
        mission = self.mission()
        return {'request_id': request, 'confirmation_token': mission['confirmation_token'],
                'stop_generation': mission['operator_test']['stop_generation']}

    async def test_early_click_is_rejected_and_not_reserved(self):
        await self.enabled_start()
        with self.assertRaises(MissionConflict):
            await self.owner.operator_test_green(self.id, request_id='request-00000001',
                confirmation_token='old', stop_generation=0)
        await self.arrive()
        self.clock.now += 2.1
        self.health['operational_3d']['stopped_seconds'] = .1
        await asyncio.sleep(.11)
        self.assertEqual(self.mission()['phase'], 'holding')
        self.assertEqual(len(self.navigation.sent), 1)
        self.health['operational_3d']['stopped_seconds'] = 2.1
        await until(lambda: self.mission()['phase'] == 'after_arrival_confirmation')
        self.assertEqual(len(self.navigation.sent), 1, 'early click must never authorize departure later')

    async def test_one_green_dispatches_one_existing_nav_goal_and_duplicate_is_idempotent(self):
        await self.enabled_start()
        await self.wait_green()
        args = self.release_args()
        result = await self.owner.operator_test_green(self.id, **args)
        duplicate = await self.owner.operator_test_green(self.id, **args)
        self.assertEqual([item['annotation_id'] for item in self.navigation.sent], [FIRST, SECOND])
        self.assertFalse(result['duplicate'])
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(result['event']['source'], 'OPERATOR_TEST')
        self.assertEqual(result['event']['departure'], 'GOAL_DISPATCHED')
        self.assertEqual(result['event']['completion_profile'], 'NAV_STOP_POINT_TEST')
        self.assertNotIn('GREEN', self.health.values())

    async def test_old_step_token_cannot_release_next_stop(self):
        await self.enabled_start()
        await self.wait_green()
        args = self.release_args()
        await self.owner.operator_test_green(self.id, **args)
        await self.wait_green()
        with self.assertRaises(MissionConflict):
            await self.owner.operator_test_green(self.id, **{**args, 'request_id': 'request-00000002'})
        self.assertEqual(len(self.navigation.sent), 2)
        self.assertEqual(self.mission()['current_index'], 1)

    async def test_source_loss_generation_or_blocked_navigation_reject_release(self):
        await self.enabled_start()
        await self.wait_green()
        args = self.release_args()
        self.health['fresh'] = False
        with self.assertRaises(MissionConflict):
            await self.owner.operator_test_green(self.id, **args)
        self.health['fresh'] = True
        self.health['operational_3d']['localization_generation'] = 2
        with self.assertRaises(MissionConflict):
            await self.owner.operator_test_green(self.id, **args)
        self.health['operational_3d']['localization_generation'] = 1
        self.navigation.ready = False
        with self.assertRaises(MissionConflict):
            await self.owner.operator_test_green(self.id, **args)
        self.assertEqual(len(self.navigation.sent), 1)

    async def test_running_mission_cancels_owned_goal_on_healthy_new_source_generation(self):
        await self.enabled_start()
        owned_goal = self.navigation.goal['goal_id']
        # Navigation stays localized and can_send_goal stays true: only the
        # bound source generation changed, so the owner must compare its pin.
        self.health['operational_3d']['localization_generation'] = 2
        await until(lambda: self.mission()['state'] == 'failed')
        self.assertEqual(self.navigation.canceled, [owned_goal])
        self.assertEqual(len(self.navigation.sent), 1)
        self.assertFalse(self.mission()['ownership_active'])

    async def test_wait_source_drop_then_recovery_cannot_reuse_old_button_token(self):
        await self.enabled_start()
        await self.wait_green()
        args = self.release_args()
        self.health['fresh'] = False
        self.assertFalse(self.mission()['operator_test']['ready'])
        self.health['fresh'] = True
        self.assertFalse(self.mission()['operator_test']['ready'])
        with self.assertRaises(MissionConflict):
            await self.owner.operator_test_green(self.id, **args)
        self.assertEqual(len(self.navigation.sent), 1)

    async def test_generic_resume_skip_retry_cannot_bypass_operator_test(self):
        await self.enabled_start()
        await self.wait_green()
        for name in ('resume', 'skip', 'retry'):
            with self.subTest(name=name), self.assertRaises(MissionConflict):
                await getattr(self.owner, name)(self.id)
        self.assertEqual(len(self.navigation.sent), 1)

    async def test_disabled_test_mode_rejects_green(self):
        with self.assertRaises(MissionConflict):
            await self.owner.operator_test_green(self.id, request_id='request-00000001',
                confirmation_token='token', stop_generation=0)
        self.assertFalse(self.navigation.sent)

    async def test_cancel_during_final_preflight_prevents_next_dispatch(self):
        await self.enabled_start()
        await self.wait_green()
        entered, unblock = asyncio.Event(), asyncio.Event()
        mission = self.owner._mission(self.id)
        mission['context_revision'] = 'f' * 64

        async def preflight(_):
            entered.set()
            await unblock.wait()

        self.owner._dispatch_preflight = preflight
        release = asyncio.create_task(self.owner.operator_test_green(self.id, **self.release_args()))
        await asyncio.wait_for(entered.wait(), 1.)
        abort = asyncio.create_task(self.owner.abort(self.id))
        await asyncio.sleep(0)
        unblock.set()
        await asyncio.gather(release, abort)
        self.assertEqual(len(self.navigation.sent), 1)
        self.assertEqual(self.mission()['outcome'], 'aborted')
        self.assertFalse(self.mission()['ownership_active'])

    async def test_localization_loss_during_final_preflight_prevents_next_dispatch(self):
        await self.enabled_start()
        await self.wait_green()
        mission = self.owner._mission(self.id)
        mission['context_revision'] = 'f' * 64

        async def preflight(_):
            self.health['operational_3d']['ready'] = False
            await asyncio.sleep(0)

        self.owner._dispatch_preflight = preflight
        with self.assertRaises(MissionConflict):
            await self.owner.operator_test_green(self.id, **self.release_args())
        self.assertEqual(len(self.navigation.sent), 1)

    def delay_navigation_consumer(self):
        """Model awaited annotation/pose validation inside NavigationCoordinator."""
        original = self.navigation.send_annotation_goal
        entered, unblock = asyncio.Event(), asyncio.Event()

        async def delayed(**kwargs):
            entered.set()
            await unblock.wait()
            self.assertTrue(callable(kwargs.get('dispatch_guard')),
                            'the same owner proof must reach the final NavigationPort consumer')
            kwargs['dispatch_guard']()
            return await original(**kwargs)

        self.navigation.send_annotation_goal = delayed
        return entered, unblock

    async def test_source_loss_during_navigation_consumer_await_prevents_actual_send(self):
        await self.enabled_start()
        await self.wait_green()
        entered, unblock = self.delay_navigation_consumer()
        release = asyncio.create_task(self.owner.operator_test_green(self.id, **self.release_args()))
        await asyncio.wait_for(entered.wait(), 1.)
        self.health['operational_3d']['ready'] = False
        unblock.set()
        with self.assertRaises(MissionConflict):
            await release
        self.assertEqual(len(self.navigation.sent), 1)

    async def test_permission_expiry_during_navigation_consumer_await_prevents_actual_send(self):
        await self.enabled_start()
        await self.wait_green()
        entered, unblock = self.delay_navigation_consumer()
        release = asyncio.create_task(self.owner.operator_test_green(self.id, **self.release_args()))
        await asyncio.wait_for(entered.wait(), 1.)
        self.clock.now += 2.01
        unblock.set()
        with self.assertRaises(MissionConflict):
            await release
        self.assertEqual(len(self.navigation.sent), 1)

    async def test_abort_during_navigation_consumer_await_prevents_actual_send(self):
        await self.enabled_start()
        await self.wait_green()
        entered, unblock = self.delay_navigation_consumer()
        release = asyncio.create_task(self.owner.operator_test_green(self.id, **self.release_args()))
        await asyncio.wait_for(entered.wait(), 1.)
        abort = asyncio.create_task(self.owner.abort(self.id))
        await asyncio.sleep(0)
        unblock.set()
        results = await asyncio.gather(release, abort, return_exceptions=True)
        self.assertIsInstance(results[0], MissionConflict)
        self.assertEqual(len(self.navigation.sent), 1)
        # A final consumer that rejected before sending should give the owner
        # enough information to finish its queued cancellation transaction.
        self.assertIsInstance(results[1], dict)
        self.assertEqual(self.mission()['outcome'], 'aborted')
        self.assertFalse(self.mission()['ownership_active'])

    async def test_restart_preserves_readable_history_and_never_restores_permission(self):
        await self.enabled_start()
        await self.wait_green()
        args = self.release_args()
        await self.owner.operator_test_green(self.id, **args)
        await self.owner.close()
        restored = MissionCoordinator(self.navigation, Maps(), self.root, monotonic=self.clock)
        try:
            self.assertTrue(restored.snapshot()['available'], 'operator audit events must remain readable after restart')
            history = restored.snapshot(self.id)['mission']
            self.assertEqual(history['outcome'], 'interrupted')
            self.assertFalse(history['ownership_active'])
            events = [entry['operator_test_event'] for entry in history['logs'] if 'operator_test_event' in entry]
            self.assertTrue(events, 'operator release and dispatch receipts must survive restart')
            self.assertTrue(all(event['source'] == 'OPERATOR_TEST' for event in events))
            self.assertTrue(all(event['completion_profile'] == 'NAV_STOP_POINT_TEST' for event in events))
            with self.assertRaises(MissionConflict):
                await restored.operator_test_green(self.id, **args)
            self.assertEqual(len(self.navigation.sent), 2)
        finally:
            await restored.close()

    async def test_restart_of_enabled_ready_mission_requires_new_live_binding(self):
        await self.owner.enable_operator_test(self.id)
        restored = MissionCoordinator(self.navigation, Maps(), self.root, monotonic=self.clock)
        try:
            self.assertTrue(restored.snapshot()['available'])
            self.assertEqual(restored.snapshot(self.id)['mission']['state'], 'ready')
            with self.assertRaises(MissionConflict):
                await restored.start(self.id)
            self.assertFalse(self.navigation.sent)
        finally:
            await restored.close()

    async def test_second_stop_requires_its_own_button_and_final_release_adds_no_goal(self):
        await self.enabled_start()
        await self.wait_green()
        await self.owner.operator_test_green(self.id, **self.release_args())
        await self.wait_green()
        self.assertEqual(len(self.navigation.sent), 2)
        self.assertEqual(self.mission()['state'], 'paused')
        result = await self.owner.operator_test_green(self.id, **self.release_args('request-00000002'))
        self.assertEqual(result['mission']['state'], 'completed')
        self.assertEqual(result['mission']['completed_count'], 2)
        self.assertFalse(result['mission']['ownership_active'])
        self.assertEqual(len(self.navigation.sent), 2)


if __name__ == '__main__':
    unittest.main()
