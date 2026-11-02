"""Synthetic, robot-free tests for proposal handoff and stop receipt."""
import asyncio
import copy
import math
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from robot_dashboard.application.fastlio_observation import FastlioObservationSession
from robot_dashboard.observation_service import ObservationServiceError
from robot_dashboard.relocalization.handoff_policy import validate_candidate, validate_handoff
from robot_dashboard.relocalization.operational import load_bundle
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy
from robot_dashboard.application.navigation_preparation_inputs import preparation_inputs
from robot_dashboard.application.runtime_health_sample import capture_runtime_health
from robot_dashboard.api.routers.operational_navigation import router
from robot_dashboard.application.runtime import ApplicationRuntime
from fastapi import FastAPI
from test_navigation_presets import LocalASGIClient
import numpy as np
import test_operational_navigation_bundle as bundle_fixture
import test_navigation_initialization_proposal as proposal_fixture
from robot_dashboard.application.global_observation import GlobalObservationCoordinator
from robot_dashboard.application.navigation_initialization_proposal import NavigationInitializationProposals


class ProposalHandoffTests(unittest.TestCase):
    def setUp(self):
        self.case = bundle_fixture.OperationalNavigationBundleTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.manager = self.case.manager
        self.addCleanup(self.manager.close_handoff_monitor)
        state = self.manager.select_pair(self.case.pair_fixture())
        self.generation = state['selected']['generation']
        self.session_id = 'a' * 32
        self.session = FastlioObservationSession(SimpleNamespace(pipeline_coordination_lock=asyncio.Lock()), enabled=True)
        self.session._status = {'state': 'READY', 'active': True, 'busy': True,
            'session_id': self.session_id, 'started_monotonic_s': time.monotonic()-1}
        self.session._updated_at = time.monotonic()
        self.proposal = {'state': 'ready', 'pair': {k: copy.deepcopy(state['pair'][k]) for k in ('generation', 'localization_3d', 'navigation_2d', 'calibration_sha256')},
            'observation_session_id': self.session_id,
            'provenance': {'bundle_generation': self.generation, 'observation_session_id': self.session_id,
                'calibration_sha256': state['pair']['calibration_sha256'], 'pose_age_s': .1,
                'capture_stamp_ns': '1234', 'source_contract': {'frame': 'synthetic'}},
            'quality': {'ambiguity_unresolved': False},
            'body_candidate': {'pose_reference': 'base_link', 'units': 'metres_radians', 'pose': dict(x=1., y=2., z=3., roll=.1, pitch=.2, yaw=3.1)}}
        self.global_owner = SimpleNamespace(job=lambda _: {'worker_active': False})
        self.watch_identity = (('cloud', 'observer', 'epoch1'), ('pose', 'observer', 'epoch1'))
        self.watch_stamps = (100, 100)
        def watch_context(_, __):
            return {'identity': self.watch_identity, 'stamps': self.watch_stamps,
                    'session': {'session_id': self.session_id,
                                'started_monotonic_s': self.session._status['started_monotonic_s']}}
        def watch_sample():
            snapshot = self.session.snapshot()
            return {'identity': self.watch_identity, 'stamps': self.watch_stamps,
                'session': {'session_id': snapshot.get('session_id'),
                            'started_monotonic_s': snapshot.get('started_monotonic_s')},
                'state': snapshot['state'], 'active': snapshot['active'], 'sample_end_ns': time.monotonic_ns()}
        self.owner = SimpleNamespace(get=lambda _: copy.deepcopy(self.proposal),
            handoff_watch_context=watch_context, handoff_watch_sample=watch_sample,
            runtime=SimpleNamespace(global_observation=self.global_owner))
        self.map_id, self.revision = self.case.navigation['id'], self.case.navigation['revision']

    def confirm(self, request='request'):
        return self.manager.confirm_proposal(self.owner, self.session, 'b'*24, request, self.generation, self.session_id)

    def finish_stop(self, identifier):
        self.session._handoff_record('dispatch', session_id=self.session_id)
        self.session._handoff_record('accepted', session_id=self.session_id)
        status = dict(state='STOPPED', active=False, busy=False, session_id=None, job_pending=False)
        self.session._handoff_record('status', status=status)
        self.session._status = status
        self.session._updated_at = time.monotonic()
        self.wait_watch(identifier, 'STOP_BOUNDARY')

    def wait_watch(self, identifier, state):
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            if self.manager._handoffs[identifier]['watch_state'] == state:
                return
            time.sleep(.01)
        self.fail('watch did not reach ' + state)

    def test_confirm_stop_snapshot_one_shot_and_initial_pose(self):
        result = self.confirm()
        identifier = result['handoff_id']
        self.assertEqual(result['state'], 'CONFIRMED_OBSERVATION_ACTIVE')
        self.assertEqual(result['source'], 'proposal_confirmed')
        self.assertEqual(self.confirm()['handoff_id'], identifier)
        with self.assertRaisesRegex(ValueError, 'REQUEST_ID_CONTEXT_CONFLICT'):
            self.manager.confirm_proposal(self.owner, self.session, 'c'*24, 'request', self.generation, self.session_id)
        with self.assertRaisesRegex(ValueError, 'HANDOFF_OBSERVATION_STOP_REQUIRED'):
            self.manager.preflight(self.map_id, self.revision)
        self.finish_stop(identifier)
        self.assertEqual(self.manager.handoff_status(identifier)['state'], 'OBSERVATION_STOPPED')
        self.manager.preflight(self.map_id, self.revision)
        directory = self.case.job_directory()
        self.manager.snapshot_for_job(self.map_id, self.revision, directory)
        with patch.object(self.case.jobs, 'snapshot', return_value={'pipeline': {'state':'running', 'job_id':directory.name},
                          'map': {'id':self.map_id, 'revision':self.revision}}):
            self.assertEqual(self.manager.handoff_status(identifier)['state'], 'SNAPSHOTTED')
        reference = result['initial_pose_reference']
        self.manager.check_initial_pose(self.map_id, self.revision, reference)
        with self.assertRaisesRegex(ValueError, 'INITIAL_POSE_CANDIDATE_MISMATCH'):
            self.manager.check_initial_pose(self.map_id, self.revision, {**reference, 'x': reference['x']+.3})
        with self.assertRaisesRegex(ValueError, 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED'):
            self.manager.preflight(self.map_id, self.revision)

    def test_unknown_stop_wrong_generation_and_expiry_block(self):
        result = self.confirm()
        identifier = result['handoff_id']
        self.session._handoff_record('dispatch', session_id=self.session_id)
        self.session._handoff_record('error')
        self.assertEqual(self.manager.handoff_status(identifier)['state'], 'OUTCOME_UNKNOWN')
        with self.assertRaisesRegex(ValueError, 'HANDOFF_STOP_OUTCOME_UNKNOWN'):
            self.manager.preflight(self.map_id, self.revision)
        record = self.manager._handoffs[identifier]
        record['geometry']['handoff']['expires_monotonic_s'] = time.monotonic()-1
        self.assertEqual(self.manager.handoff_status(identifier)['state'], 'OUTCOME_UNKNOWN')

    def test_wrap_ttl_and_calibration_change(self):
        result = self.confirm()
        self.finish_stop(result['handoff_id'])
        self.manager.preflight(self.map_id, self.revision)
        geo = self.manager.selected['seed_geometry']
        ref = geo['handoff']['reference']
        validate_candidate(geo, ref['x'], ref['y'], ref['yaw']-2*math.pi, self.manager.selected)
        with self.assertRaisesRegex(ValueError, 'INITIAL_POSE_CANDIDATE_MISMATCH'):
            validate_candidate(geo, ref['x'], ref['y'], ref['yaw']+.21, self.manager.selected)
        self.case.calibration['evidence'] = 'changed'
        self.case.write_calibration()
        with self.assertRaisesRegex(ValueError, 'CALIBRATION_CHANGED'):
            self.manager.preflight(self.map_id, self.revision)

    def test_receipt_nonce_and_start_are_bound_and_fail_closed(self):
        result = self.confirm()
        identifier = result['handoff_id']
        self.session._handoff_record('dispatch', session_id=self.session_id)
        self.session._handoff_record('accepted', session_id=self.session_id)
        self.assertEqual(self.manager.handoff_status(identifier)['state'], 'STOP_PENDING')
        with self.session._lock:
            self.session._handoff_receipts[identifier]['nonce'] = 'f'*32
        self.assertEqual(self.manager.handoff_status(identifier)['state'], 'OUTCOME_UNKNOWN')
        with self.assertRaisesRegex(ValueError, 'HANDOFF_STOP_OUTCOME_UNKNOWN'):
            self.manager.preflight(self.map_id, self.revision)

    def test_inactive_wrong_started_generation_is_unknown(self):
        result = self.confirm()
        identifier = result['handoff_id']
        self.session._handoff_record('dispatch', session_id=self.session_id)
        self.session._handoff_record('accepted', session_id=self.session_id)
        self.session._handoff_record('status', status={'state':'STOPPED', 'active':False,
            'session_id':self.session_id, 'started_monotonic_s':self.session._status['started_monotonic_s']+1})
        self.assertEqual(self.session.handoff_receipt(identifier)['state'], 'OUTCOME_UNKNOWN')

    def test_corrupt_confirmed_receipt_session_and_start_cannot_authorize(self):
        result = self.confirm()
        self.finish_stop(result['handoff_id'])
        with self.session._lock:
            self.session._handoff_receipts[result['handoff_id']]['session_id'] = 'd'*32
        with self.assertRaisesRegex(ValueError, 'HANDOFF_STOP_OUTCOME_UNKNOWN'):
            self.manager.preflight(self.map_id, self.revision)

    def test_duplicate_stop_does_not_dispatch_again(self):
        self.confirm()
        class Service:
            def __init__(inner): inner.current = copy.deepcopy(self.session._status); inner.calls = []
            def status(inner): return copy.deepcopy(inner.current)
            def dispatch(inner, command): inner.calls.append(command); inner.current['state'] = 'STOPPING'
        service = Service()
        self.session.service = service
        async def inline(function, *args, **kwargs): return function(*args, **kwargs)
        async def run():
            with patch('robot_dashboard.application.fastlio_observation.asyncio.to_thread', inline):
                await self.session.stop(self.session_id)
                from robot_dashboard.application.fastlio_observation import ObservationSessionConflict
                with self.assertRaises(ObservationSessionConflict):
                    await self.session.stop(self.session_id)
        asyncio.run(run())
        self.assertEqual(service.calls, ['stop'])

    def test_receipt_never_confirms_without_accepted_dispatch_and_correct_generation(self):
        result = self.confirm()
        identifier = result['handoff_id']
        self.session._handoff_record('status', status={'state':'STOPPED','active':False,'session_id':None})
        self.assertEqual(self.session.handoff_receipt(identifier)['state'], 'OUTCOME_UNKNOWN')

    def test_actual_stop_dispatch_and_delayed_inactive_receipt(self):
        result = self.confirm()
        identifier = result['handoff_id']
        class Service:
            def __init__(self, active): self.current = active; self.calls = []
            def status(self): return copy.deepcopy(self.current)
            def dispatch(self, command):
                self.calls.append(command)
                self.current['state'] = 'STOPPING'
        service = Service(copy.deepcopy(self.session._status))
        self.session.service = service
        async def inline(function, *args, **kwargs): return function(*args, **kwargs)
        async def run():
            with patch('robot_dashboard.application.fastlio_observation.asyncio.to_thread', inline):
                await self.session.stop(self.session_id)
                self.assertEqual(self.session.handoff_receipt(identifier)['state'], 'DISPATCH_ACCEPTED')
                service.current = dict(state='STOPPED', active=False, busy=False, session_id=None, job_pending=False)
                await self.session.refresh()
        asyncio.run(run())
        self.wait_watch(identifier, 'STOP_BOUNDARY')
        self.assertEqual(service.calls, ['stop'])
        self.assertEqual(self.session.handoff_receipt(identifier)['state'], 'INACTIVE_CONFIRMED')
        self.assertEqual(self.manager.handoff_status(identifier)['state'], 'OBSERVATION_STOPPED')

    def test_dispatch_timeout_never_becomes_success_on_later_inactive(self):
        result = self.confirm()
        identifier = result['handoff_id']
        class Service:
            def status(inner): return copy.deepcopy(self.session._status)
            def dispatch(inner, command): raise ObservationServiceError('timeout')
        self.session.service = Service()
        async def inline(function, *args, **kwargs): return function(*args, **kwargs)
        async def run():
            with patch('robot_dashboard.application.fastlio_observation.asyncio.to_thread', inline):
                with self.assertRaises(ObservationServiceError):
                    await self.session.stop(self.session_id)
        asyncio.run(run())
        self.session._handoff_record('status', status={'state':'STOPPED', 'active':False, 'session_id':None})
        self.assertEqual(self.session.handoff_receipt(identifier)['state'], 'OUTCOME_UNKNOWN')

    def test_receipt_journal_failure_does_not_block_stop(self):
        result = self.confirm()
        current = copy.deepcopy(self.session._status)
        class Service:
            def status(self): return copy.deepcopy(current)
            def dispatch(self, command): self.called = command
        service = Service()
        self.session.service = service
        async def inline(function, *args, **kwargs): return function(*args, **kwargs)
        async def run():
            with patch('robot_dashboard.application.fastlio_observation.asyncio.to_thread', inline), \
                 patch.object(self.session, '_handoff_record', side_effect=RuntimeError('journal')):
                await self.session.stop(self.session_id)
        asyncio.run(run())
        self.assertEqual(service.called, 'stop')
        self.assertEqual(self.session.handoff_receipt(result['handoff_id'])['state'], 'OUTCOME_UNKNOWN')

    def test_real_global_proposal_and_real_catalogue_confirm_without_client_geometry(self):
        case = proposal_fixture.ProposalTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.runtime.operational_navigation = self.manager
        case.runtime.fastlio_observation = self.session
        case.session_id = self.session_id
        # Keep the real source samples inside this observation session.
        self.session._status['started_monotonic_s'] = case.session_state['started_monotonic_s']
        owner = GlobalObservationCoordinator(self.case.catalog, case.runtime.agent, case.runner)
        self.addCleanup(owner.close)
        case.runtime.global_observation = owner
        coordinator = NavigationInitializationProposals(case.runtime)
        started = coordinator.start('real-handoff', self.generation, self.session_id)
        deadline = time.monotonic()+3
        while owner.job(started['proposal_id'])['worker_active'] and time.monotonic() < deadline:
            time.sleep(.005)
        preview = coordinator.get(started['proposal_id'])['navigation_geometry_candidate']
        self.assertIsNotNone(preview)
        self.assertIsNone(self.manager.selected['seed_geometry'])
        result = self.manager.confirm_proposal(coordinator, self.session, started['proposal_id'],
            'real-confirm', self.generation, self.session_id)
        self.assertEqual(result['state'], 'CONFIRMED_OBSERVATION_ACTIVE')
        self.assertEqual(result['source'], 'proposal_confirmed')
        self.assertEqual(result['operational_application'], 'NOT_RUN')
        self.assertEqual(preview['pose'], result['geometry'])
        old_topic = case.runtime.agent.pose['topic']
        case.runtime.agent.pose['topic'] = '/synthetic-other-source'
        self.wait_watch(result['handoff_id'], 'INVALID')
        case.runtime.agent.pose['topic'] = old_topic
        self.assertEqual(self.manager.handoff_status(result['handoff_id'])['reason'], 'SOURCE_OR_CONTEXT_CHANGED')

    def test_watcher_permanently_invalidates_observed_source_epoch_and_session_changes(self):
        for mutation in ('source', 'epoch', 'stamp', 'session'):
            with self.subTest(mutation=mutation):
                if mutation != 'source':
                    self.manager.seed_geometry({'generation':self.generation, 'z':.1, 'roll':0., 'pitch':0.})
                result = self.confirm(request='watch-'+mutation)
                original_identity, original_stamps = self.watch_identity, self.watch_stamps
                if mutation == 'source': self.watch_identity = (('different', 'observer', 'epoch1'), original_identity[1])
                if mutation == 'epoch': self.watch_identity = (('cloud', 'observer', 'epoch2'), original_identity[1])
                if mutation == 'stamp': self.watch_stamps = (99, 100)
                if mutation == 'session': self.session._status['session_id'] = 'e'*32
                self.wait_watch(result['handoff_id'], 'INVALID')
                self.watch_identity, self.watch_stamps = original_identity, original_stamps
                self.session._status['session_id'] = self.session_id
                self.assertEqual(self.manager.handoff_status(result['handoff_id'])['state'], 'INVALID')
                self.assertEqual(self.manager.status()['initialization_handoff']['reason'], 'SOURCE_OR_CONTEXT_CHANGED')
                with self.assertRaisesRegex(ValueError, 'SOURCE_OR_CONTEXT_CHANGED'):
                    self.manager.preflight(self.map_id, self.revision)

    def test_watcher_loss_fails_closed_and_threads_end(self):
        result = self.confirm()
        self.owner.handoff_watch_sample = lambda: (_ for _ in ()).throw(RuntimeError('lost'))
        self.wait_watch(result['handoff_id'], 'INVALID')
        self.assertEqual(self.manager.handoff_status(result['handoff_id'])['reason'], 'HANDOFF_MONITOR_UNAVAILABLE')
        deadline = time.monotonic()+2
        while self.manager._handoff_watch_thread is not None and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertIsNone(self.manager._handoff_watch_thread)

    def test_sample_completed_before_dispatch_invalidates_even_if_processed_later(self):
        sampled, release = threading.Event(), threading.Event()
        original = self.owner.handoff_watch_sample
        def delayed_changed_sample():
            result = original()
            result['identity'] = (('cloud', 'observer', 'changed-epoch'), result['identity'][1])
            result['sample_end_ns'] = time.monotonic_ns()
            sampled.set()
            if not release.wait(2): raise RuntimeError('test release missing')
            return result
        self.owner.handoff_watch_sample = delayed_changed_sample
        result = self.confirm()
        try:
            self.assertTrue(sampled.wait(2))
            self.session._handoff_record('dispatch', session_id=self.session_id)
        finally:
            release.set()
        self.wait_watch(result['handoff_id'], 'INVALID')
        self.assertEqual(self.manager.handoff_status(result['handoff_id'])['reason'], 'SOURCE_OR_CONTEXT_CHANGED')

    def test_monitor_failure_never_blocks_normal_stop(self):
        result = self.confirm()
        self.owner.handoff_watch_sample = lambda: (_ for _ in ()).throw(RuntimeError('lost'))
        self.wait_watch(result['handoff_id'], 'INVALID')
        class Service:
            def __init__(inner): inner.calls = []
            def status(inner): return copy.deepcopy(self.session._status)
            def dispatch(inner, command): inner.calls.append(command)
        service = Service(); self.session.service = service
        async def inline(function, *args, **kwargs): return function(*args, **kwargs)
        async def run():
            with patch('robot_dashboard.application.fastlio_observation.asyncio.to_thread', inline):
                await self.session.stop(self.session_id)
        asyncio.run(run())
        self.assertEqual(service.calls, ['stop'])
        self.assertEqual(self.manager.handoff_status(result['handoff_id'])['state'], 'INVALID')

    def test_monitor_stall_and_selection_change_end_fail_closed(self):
        result = self.confirm()
        with self.manager.lock:
            record = self.manager._handoffs[result['handoff_id']]
            record['watch_last'] = time.monotonic()-3
            with self.assertRaisesRegex(ValueError, 'HANDOFF_MONITOR_UNAVAILABLE'):
                self.manager._handoff_gate(record)
        self.assertEqual(record['watch_state'], 'INVALID')
        second = self.confirm(request='next-confirm')
        self.manager.select({})
        self.wait_watch(second['handoff_id'], 'INVALID')
        self.assertEqual(self.manager._handoffs[second['handoff_id']]['invalid'], 'MAP_PAIR_CHANGED')

    def test_monitor_expiry_and_close_stop_the_watcher(self):
        result = self.confirm()
        with self.manager.lock:
            self.manager._handoffs[result['handoff_id']]['geometry']['handoff']['expires_monotonic_s'] = time.monotonic()-1
        self.wait_watch(result['handoff_id'], 'INVALID')
        self.assertEqual(self.manager.handoff_status(result['handoff_id'])['state'], 'EXPIRED')
        self.manager.seed_geometry({'generation':self.generation, 'z':.1, 'roll':0., 'pitch':0.})
        second = self.confirm(request='close-test')
        self.manager.close_handoff_monitor()
        self.assertEqual(self.manager._handoffs[second['handoff_id']]['invalid'], 'HANDOFF_MONITOR_UNAVAILABLE')
        deadline = time.monotonic()+2
        while self.manager._handoff_watch_thread is not None and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertIsNone(self.manager._handoff_watch_thread)

    def test_normal_stop_tolerates_source_unavailable_after_dispatch_boundary(self):
        result = self.confirm()
        class Service:
            def __init__(inner): inner.current = copy.deepcopy(self.session._status); inner.calls = []
            def status(inner): return copy.deepcopy(inner.current)
            def dispatch(inner, command):
                inner.calls.append(command)
                self.owner.handoff_watch_sample = lambda: (_ for _ in ()).throw(RuntimeError('source stopped'))
                inner.current['state'] = 'STOPPING'
        service = Service(); self.session.service = service
        async def inline(function, *args, **kwargs): return function(*args, **kwargs)
        async def run():
            with patch('robot_dashboard.application.fastlio_observation.asyncio.to_thread', inline):
                await self.session.stop(self.session_id)
                service.current = dict(state='STOPPED', active=False, busy=False, session_id=None, job_pending=False)
                await self.session.refresh()
        asyncio.run(run())
        self.wait_watch(result['handoff_id'], 'STOP_BOUNDARY')
        self.assertEqual(self.manager.handoff_status(result['handoff_id'])['state'], 'OBSERVATION_STOPPED')
        self.assertEqual(service.calls, ['stop'])

    def test_missing_watch_provider_refuses_confirmation(self):
        del self.owner.handoff_watch_context
        with self.assertRaisesRegex(ValueError, 'HANDOFF_MONITOR_UNAVAILABLE'):
            self.confirm()
        self.assertIsNone(self.manager.selected['seed_geometry'])

    def test_slow_confirmation_keeps_monitor_sampling_and_selection_fence(self):
        original = self.manager._revalidate_pair
        entered, release = threading.Event(), threading.Event()
        samples = []
        old_sample = self.owner.handoff_watch_sample
        def sample():
            samples.append(time.monotonic())
            return old_sample()
        self.owner.handoff_watch_sample = sample
        def delayed(bundle, **kwargs):
            if (bundle.get('seed_geometry') or {}).get('source') == 'proposal_confirmed':
                entered.set()
                if not release.wait(4): raise RuntimeError('test timed out')
            return original(bundle, **kwargs)
        output = []
        with patch.object(self.manager, '_revalidate_pair', side_effect=delayed):
            worker = threading.Thread(target=lambda: output.append(self.confirm()))
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                time.sleep(2.2)
                self.assertGreater(len(samples), 10)
            finally:
                release.set(); worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual((output[0]['state'], output[0]['reason']), ('CONFIRMED_OBSERVATION_ACTIVE', None))
        self.assertEqual(self.manager.handoff_status(output[0]['handoff_id'])['state'], 'CONFIRMED_OBSERVATION_ACTIVE')

    def test_source_change_and_selection_race_during_slow_validation_fail_closed(self):
        for variant in ('source', 'same_generation_calibration', 'selection'):
            with self.subTest(variant=variant):
                if variant != 'source':
                    self.manager.seed_geometry({'generation':self.generation, 'z':.1, 'roll':0., 'pitch':0.})
                original = self.manager._revalidate_pair
                entered, release = threading.Event(), threading.Event()
                def delayed(bundle, **kwargs):
                    if (bundle.get('seed_geometry') or {}).get('source') == 'proposal_confirmed':
                        entered.set()
                        if not release.wait(3): raise RuntimeError('test timed out')
                    return original(bundle, **kwargs)
                output = []
                with patch.object(self.manager, '_revalidate_pair', side_effect=delayed):
                    worker = threading.Thread(target=lambda: output.append(self.confirm(request='race-'+variant)))
                    worker.start()
                    try:
                        self.assertTrue(entered.wait(2))
                        if variant == 'source':
                            identifier = next(reversed(self.manager._handoffs))
                            self.watch_identity = (('cloud', 'observer', 'changed'), self.watch_identity[1])
                            self.wait_watch(identifier, 'INVALID')
                            self.watch_identity = (('cloud', 'observer', 'epoch1'), self.watch_identity[1])
                        elif variant == 'same_generation_calibration':
                            with self.manager.lock:
                                self.manager.selected['calibration']['evidence'] = 'changed-during-validation'
                        else:
                            self.manager.select({})
                    finally:
                        release.set(); worker.join(3)
                self.assertFalse(worker.is_alive())
                self.assertEqual(output[0]['state'], 'INVALID')

    def test_slow_status_lock_does_not_starve_healthy_watcher(self):
        result = self.confirm()
        entered, release = threading.Event(), threading.Event()
        samples = []
        original_sample = self.owner.handoff_watch_sample
        original_validate = self.manager._revalidate_pair
        def sampled():
            samples.append(time.monotonic())
            return original_sample()
        self.owner.handoff_watch_sample = sampled
        def delayed(bundle, **kwargs):
            entered.set()
            if not release.wait(4): raise RuntimeError('test timed out')
            return original_validate(bundle, **kwargs)
        output = []
        with patch.object(self.manager, '_revalidate_pair', side_effect=delayed):
            worker = threading.Thread(target=lambda: output.append(self.manager.status()))
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                time.sleep(2.2)
                self.assertGreater(len(samples), 10)
            finally:
                release.set(); worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(output[0]['initialization_handoff']['state'], 'CONFIRMED_OBSERVATION_ACTIVE')
        self.assertEqual(self.manager.handoff_status(result['handoff_id'])['state'], 'CONFIRMED_OBSERVATION_ACTIVE')

    def test_watcher_runs_while_other_status_holds_manager_lock(self):
        result = self.confirm()
        entered, release = threading.Event(), threading.Event()
        original = self.manager._revalidate_pair
        def delayed(bundle, **kwargs):
            entered.set()
            if not release.wait(4): raise RuntimeError('test timed out')
            return original(bundle, **kwargs)
        with patch.object(self.manager, '_revalidate_pair', side_effect=delayed):
            worker = threading.Thread(target=self.manager.status)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                self.watch_identity = (('cloud', 'observer', 'changed'), self.watch_identity[1])
                self.wait_watch(result['handoff_id'], 'INVALID')
            finally:
                self.watch_identity = (('cloud', 'observer', 'epoch1'), self.watch_identity[1])
                release.set(); worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.manager.handoff_status(result['handoff_id'])['reason'], 'SOURCE_OR_CONTEXT_CHANGED')

    def test_recovery_comes_from_current_server_selection_and_job(self):
        self.assertIsNone(self.manager.status()['initialization_handoff'])
        result = self.confirm()
        restored = preparation_inputs(self.manager, self.session, None)['operational_state']['initialization_handoff']
        self.assertEqual(restored['handoff_id'], result['handoff_id'])
        self.assertIsNone(restored['job_id'])
        self.jobs = self.case.jobs
        self.jobs.state = 'running'
        self.assertEqual(self.manager.status()['initialization_handoff']['state'], 'OUTCOME_UNKNOWN')
        self.jobs.state = 'idle'
        self.manager.select({})
        self.assertIsNone(self.manager.status()['initialization_handoff'])

    def test_recovery_requires_current_job_map_and_phase_after_snapshot(self):
        result = self.confirm()
        self.finish_stop(result['handoff_id'])
        directory = self.case.job_directory()
        self.manager.snapshot_for_job(self.map_id, self.revision, directory)
        def view(state, job_id, map_id, revision):
            snapshot = {'pipeline': {'state':state, 'job_id':job_id},
                        'map': {'id':map_id, 'revision':revision}}
            with patch.object(self.case.jobs, 'snapshot', return_value=snapshot):
                return self.manager.status()['initialization_handoff']
        self.assertEqual(view('running', directory.name, self.map_id, self.revision)['state'], 'SNAPSHOTTED')
        for phase in ('starting', 'stopping', 'idle', 'failed'):
            self.assertNotEqual(view(phase, directory.name, self.map_id, self.revision)['state'], 'SNAPSHOTTED')
            self.assertIsNone(view(phase, 'different', self.map_id, self.revision))
            self.assertIsNone(view(phase, directory.name, 'f'*24, self.revision))
            missing = view(phase, None, None, None)
            self.assertEqual(missing['state'], 'OUTCOME_UNKNOWN')
            self.assertIsNone(missing['geometry'])

    def test_runtime_match_is_not_disarmed_only_by_expired_bootstrap_ttl(self):
        result = self.confirm()
        self.finish_stop(result['handoff_id'])
        directory = self.case.job_directory()
        self.manager.snapshot_for_job(self.map_id, self.revision, directory)
        engine = load_bundle(directory / 'nav2_params.yaml')
        self.addCleanup(engine.close)
        engine.current_odom = np.eye(4)
        engine.stopped_since = time.monotonic() - 3
        engine.last_pose_receipt = time.monotonic()
        ref = result['initial_pose_reference']
        engine.reseed(from_translation_rpy([ref['x'], ref['y'], 0.], [0., 0., ref['yaw']]), stamp_ns=123)
        self.assertEqual(engine.accepted_initial_pose['geometry_source'], 'proposal_confirmed')
        engine.start_matching(123)
        receipt = {'accepted':True, 'request_id':'c'*32, 'localization_generation':engine.generation, 'reason':'WAITING_MAP_CORRECTION'}
        engine.match_receipt = receipt
        instance = '123:' + str(self.manager._snapshot_binding_monotonic_ns + 1)
        engine.initial_pose_receipt = {'accepted':True, 'stamp_ns':'123', 'reason':'WAITING_EXPLICIT_MAP_MATCH',
                                       'localization_generation':engine.generation}
        source = engine.status()
        source['runtime_instance_generation'] = instance
        source['accepted_initial_pose']['runtime_instance_generation'] = instance
        health = {'fresh':True, 'age_s':.01, 'runtime_instance_generation':instance, 'process_generation':123, 'operational_3d':source}
        sample = capture_runtime_health(SimpleNamespace(_navigation_runtime_health_snapshot=lambda _: health))
        with self.assertRaisesRegex(ValueError, 'HANDOFF_MATCH_CURRENT_UNCONFIRMED'):
            self.manager.record_match_armed(self.generation, self.map_id, self.revision, receipt, health, expected_stamp='123')
        self.manager.record_match_armed(self.generation, self.map_id, self.revision, receipt, sample, expected_stamp='123')
        patcher = patch.object(self.case.jobs, 'snapshot', return_value={'pipeline': {'state':'running', 'job_id':directory.name},
            'map': {'id':self.map_id, 'revision':self.revision}})
        patcher.start(); self.addCleanup(patcher.stop)
        self.assertEqual(self.manager.handoff_status(result['handoff_id'], health=sample)['state'], 'MATCH_ARMED')
        agent = SimpleNamespace(_navigation_runtime_health_snapshot=lambda _: copy.deepcopy(health))
        # Recover the accepted runtime receipt after a lost match response.
        self.manager._handoffs[result['handoff_id']]['match_binding'] = None
        view = preparation_inputs(self.manager, self.session, agent)
        self.assertEqual(view['operational_state']['initialization_handoff']['state'], 'MATCH_ARMED')
        self.assertEqual(view['operational_state']['initialization_handoff']['match_history']['match_request_id'], 'c'*32)
        self.assertTrue(engine.match_armed)
        # Both public reads must account for a manager/executor delay after capture.
        original_status = self.manager.handoff_status
        delayed = {'armed':True}
        def slow_after_capture(*args, **kwargs):
            if kwargs.get('health') is not None and delayed['armed']:
                delayed['armed'] = False
                time.sleep(.8)
            return original_status(*args, **kwargs)
        app = FastAPI(); app.state.runtime = ApplicationRuntime(operational_navigation=self.manager,
            fastlio_observation=self.session, agent=agent); app.include_router(router)
        async def inline_thread(function, *args, **kwargs): return function(*args, **kwargs)
        with patch.object(self.manager, 'handoff_status', side_effect=slow_after_capture), \
             patch('robot_dashboard.api.routers.operational_navigation.asyncio.to_thread', inline_thread):
            direct = LocalASGIClient(app).get('/api/v1/navigation/operational-3d/initialization-handoffs/'+result['handoff_id'])
        self.assertEqual((direct.json()['state'], direct.json()['reason']), ('OUTCOME_UNKNOWN', 'HANDOFF_MATCH_CURRENT_UNCONFIRMED'))
        delayed['armed'] = True
        with patch.object(self.manager, 'handoff_status', side_effect=slow_after_capture):
            delayed_view = preparation_inputs(self.manager, self.session, agent)
        h = delayed_view['operational_state']['initialization_handoff']
        self.assertEqual((h['state'], h['reason']), ('OUTCOME_UNKNOWN', 'HANDOFF_MATCH_CURRENT_UNCONFIRMED'))
        self.assertFalse(delayed_view['operational_state']['runtime_fresh'])
        sample = capture_runtime_health(SimpleNamespace(_navigation_runtime_health_snapshot=lambda _: health))
        time.sleep(.8)
        self.assertEqual(self.manager.handoff_status(result['handoff_id'], health=sample)['reason'], 'HANDOFF_MATCH_CURRENT_UNCONFIRMED')
        with self.assertRaisesRegex(ValueError, 'HANDOFF_MATCH_CURRENT_UNCONFIRMED'):
            self.manager.record_match_armed(self.generation, self.map_id, self.revision, receipt, sample, expected_stamp='123')
        prior_age = {**health, 'age_s': .8}
        prior_sample = capture_runtime_health(SimpleNamespace(_navigation_runtime_health_snapshot=lambda _: prior_age))
        self.assertEqual(self.manager.handoff_status(result['handoff_id'], health=prior_sample)['reason'], 'HANDOFF_MATCH_CURRENT_UNCONFIRMED')
        self.assertEqual(self.manager.handoff_status(result['handoff_id'])['state'], 'OUTCOME_UNKNOWN')
        different = copy.deepcopy(health)
        different['operational_3d']['localization_generation'] += 1
        changed_sample = capture_runtime_health(SimpleNamespace(_navigation_runtime_health_snapshot=lambda _: different))
        self.assertEqual(self.manager.handoff_status(result['handoff_id'], health=changed_sample)['reason'], 'HANDOFF_RUNTIME_CHANGED')
        agent._navigation_runtime_health_snapshot = lambda _: copy.deepcopy(different)
        view = preparation_inputs(self.manager, self.session, agent)
        self.assertEqual(view['operational_state']['initialization_handoff']['reason'], 'HANDOFF_RUNTIME_CHANGED')
        stale = {**health, 'fresh':False}
        stale_sample = capture_runtime_health(SimpleNamespace(_navigation_runtime_health_snapshot=lambda _: stale))
        self.assertEqual(self.manager.handoff_status(result['handoff_id'], health=stale_sample)['reason'], 'HANDOFF_MATCH_CURRENT_UNCONFIRMED')
        agent._navigation_runtime_health_snapshot = lambda _: copy.deepcopy(stale)
        view = preparation_inputs(self.manager, self.session, agent)
        self.assertEqual(view['operational_state']['initialization_handoff']['reason'], 'HANDOFF_MATCH_CURRENT_UNCONFIRMED')
        with patch('robot_dashboard.relocalization.handoff_policy.time.monotonic', return_value=time.monotonic()+121.):
            self.assertTrue(engine.match_armed)
            refreshed = capture_runtime_health(SimpleNamespace(_navigation_runtime_health_snapshot=lambda _: health))
            self.assertEqual(self.manager.handoff_status(result['handoff_id'], health=refreshed)['state'], 'MATCH_ARMED')
            engine.status()
            self.assertTrue(engine.match_armed)
            with self.assertRaisesRegex(ValueError, 'HANDOFF_EXPIRED'):
                engine.start_matching(123)

    def test_asgi_confirmation_is_explicit_strict_and_restorable(self):
        runtime = ApplicationRuntime(operational_navigation=self.manager, fastlio_observation=self.session,
            competition=SimpleNamespace(require_unlocked=lambda _: None, require_manual_mode=lambda: None))
        runtime._navigation_initialization_proposals = self.owner
        app = FastAPI(); app.state.runtime = runtime; app.include_router(router)
        client = LocalASGIClient(app)
        path = '/api/v1/navigation/operational-3d/initialization-proposals/' + 'b'*24 + '/confirm-geometry'
        body = {'request_id':'api-confirm', 'bundle_generation':self.generation,
            'observation_session_id':self.session_id, 'confirmed':True, 'stationary_supervision_acknowledged':True}
        async def inline_thread(function, *args, **kwargs): return function(*args, **kwargs)
        with patch('robot_dashboard.api.routers.operational_navigation.asyncio.to_thread', inline_thread):
            self.assertEqual(client.post(path, body, headers={'origin':'http://evil.invalid'}).status_code, 403)
            self.assertEqual(client.post(path, {**body, 'z':0.}).status_code, 422)
            self.assertEqual(client.post(path, {**body, 'confirmed':False}).status_code, 409)
            response = client.post(path, body)
            self.assertEqual(response.status_code, 200, response.text)
            identifier = response.json()['handoff_id']
            self.assertEqual(client.get('/api/v1/navigation/operational-3d/initialization-handoffs/'+identifier).json()['handoff_id'], identifier)
            self.assertEqual(client.post(path, body).json()['handoff_id'], identifier)

if __name__ == '__main__': unittest.main()
