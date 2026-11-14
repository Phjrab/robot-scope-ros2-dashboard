"""Independent synthetic end-to-end handoff/observation-stop contract checks.

Uses real FastlioObservationSession and OperationalNavigation with a fake
service; no robot, ROS, systemd, or external actions are contacted.
"""
import asyncio
import copy
import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from robot_dashboard.application.fastlio_observation import FastlioObservationSession, ObservationSessionConflict
from robot_dashboard.observation_service import ObservationServiceError
from robot_dashboard.application.navigation_preparation_inputs import preparation_inputs
import test_operational_navigation_bundle as bundle_fixture
import test_operational_3d_localization as localization_fixture
import test_navigation_initialization_proposal as proposal_fixture
from test_navigation_preparation_inputs import fixture as source_fixture
import numpy as np
from robot_dashboard.application.global_observation import GlobalObservationCoordinator
from robot_dashboard.application.navigation_initialization_proposal import NavigationInitializationProposals
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy
from robot_dashboard.relocalization.operational import OperationalLocalizer
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.application.runtime_health_sample import capture_runtime_health
from robot_dashboard.api.routers.operational_navigation import router as operational_router
from fastapi import FastAPI


class ControlledService:
    def __init__(self):
        self.session_id = 'a' * 32
        self.started = time.monotonic() - 2
        self.current = self.ready()
        self.calls = []
        self.after_dispatch = None
        self.dispatch_error = None
        self.entered = None
        self.release = None

    def ready(self):
        return {'state':'READY','active':True,'busy':True,'job_pending':False,
                'session_id':self.session_id,'started_monotonic_s':self.started,'reason':''}

    def status(self):
        return copy.deepcopy(self.current)

    def dispatch(self, action):
        self.calls.append(action)
        if self.entered:
            self.entered.set()
            if not self.release.wait(3):
                raise RuntimeError('synthetic dispatch wait expired')
        if self.dispatch_error:
            raise self.dispatch_error
        self.current = copy.deepcopy(self.after_dispatch or {
            **self.ready(), 'state':'STOPPING','active':True,'busy':True,'job_pending':True})

    def stopped(self, session_id=None, started=0.0):
        self.current = {'state':'STOPPED','active':False,'busy':False,'job_pending':False,
                        'session_id':session_id,'started_monotonic_s':started,'reason':''}


class StopContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = bundle_fixture.OperationalNavigationBundleTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.manager = self.fixture.manager
        self.addCleanup(self.manager.close_handoff_monitor)
        selection = self.manager.select_pair(self.fixture.pair_fixture())
        selected = selection['selected']
        pair = selection['pair']
        self.generation = selected['generation']
        _, _, source_agent, _, source_session = source_fixture()
        self.service = ControlledService()
        self.service.started = source_session['started_monotonic_s']
        self.service.current = {**self.service.ready(), 'observation_only':True,
                                'map_registration_applied':False}
        self.runtime = SimpleNamespace(pipeline_coordination_lock=asyncio.Lock())
        self.observation = FastlioObservationSession(self.runtime, enabled=True, service=self.service)
        await self.observation.refresh()
        self.global_owner = SimpleNamespace(job=lambda _: {'worker_active':False})
        runtime = SimpleNamespace(global_observation=self.global_owner, agent=source_agent,
                                  fastlio_observation=self.observation)
        source_monitor = NavigationInitializationProposals(runtime)
        source_contract, _, _ = source_monitor._source(self.observation.snapshot())
        self.proposal = {'state':'ready',
            'pair': {key: copy.deepcopy(pair[key]) for key in ('generation','localization_3d','navigation_2d','calibration_sha256')},
            'observation_session_id':self.service.session_id,
            'provenance':{'bundle_generation':self.generation, 'observation_session_id':self.service.session_id,
                          'calibration_sha256':pair['calibration_sha256'], 'pose_age_s':.1,
                          'capture_stamp_ns':'12345', 'source_contract':source_contract},
            'quality':{'ambiguity_unresolved':False},
            'body_candidate':{'pose_reference':'base_link','units':'metres_radians',
                              'pose':dict(x=1.,y=2.,z=.5,roll=.1,pitch=-.1,yaw=.2)}}
        def watch_context(_, session_id):
            session = self.observation.snapshot()
            if session['session_id'] != session_id:
                raise ValueError('OBSERVATION_SESSION_CHANGED')
            contract, identity, stamps = source_monitor._source(session)
            if contract != source_contract:
                raise ValueError('SOURCE_OR_CONTEXT_CHANGED')
            return {'identity':identity, 'stamps':stamps,
                    'session':{'session_id':session_id, 'started_monotonic_s':session['started_monotonic_s']}}
        self.proposal_owner = SimpleNamespace(get=lambda _:copy.deepcopy(self.proposal), runtime=runtime,
            handoff_watch_context=watch_context, handoff_watch_sample=source_monitor.handoff_watch_sample)
        self.map_id = self.fixture.navigation['id']
        self.map_revision = self.fixture.navigation['revision']

    def confirm(self, request_id='independent-confirm'):
        return self.manager.confirm_proposal(self.proposal_owner,self.observation,'b'*24,request_id,
                                             self.generation,self.service.session_id)

    async def wait_stop_boundary(self, hid):
        deadline = time.monotonic() + 2.
        while time.monotonic() < deadline:
            status = self.manager.handoff_status(hid)
            if status['reason'] != 'HANDOFF_MONITOR_PENDING':
                return status
            await asyncio.sleep(.01)
        self.fail('monitor did not settle its stop boundary')

    def synthetic_match_health(self, *, stamp='1234', generation=2, accepted_initial_pose=None):
        """Represent the gateway's bound runtime health, including both receipts."""
        bundle = self.manager.selected
        instance = f'123:{time.monotonic_ns()}'
        initial = dict(accepted_initial_pose or {})
        initial.update(accepted=True, stamp_ns=stamp, geometry_source='proposal_confirmed',
                       runtime_instance_generation=instance, localization_generation=generation,
                       bundle_generation=self.generation, map_id=self.map_id, map_revision=self.map_revision)
        receipt = {'accepted':True, 'request_id':'synthetic-match', 'reason':'ACCEPTED',
                   'localization_generation':generation}
        source = {'source':'STORED_PCD_FASTLIO', 'bundle_generation':self.generation,
                  'runtime_instance_generation':instance, 'localization_generation':generation,
                  'map_id':self.map_id, 'map_revision':self.map_revision,
                  'localization_map_id':bundle['localization_3d']['map_id'],
                  'localization_map_revision':bundle['localization_3d']['revision'],
                  'reference_sha256':bundle['localization_3d']['sha256'],
                  'accepted_initial_pose':initial,
                  'initial_pose_receipt':{'accepted':True, 'stamp_ns':stamp, 'reason':'ACCEPTED',
                                          'localization_generation':generation},
                  'match_armed':True, 'match_receipt':receipt}
        return {'fresh':True, 'age_s':.01, 'process_generation':123,
                'runtime_instance_generation':instance, 'operational_3d':source}

    def capture_synthetic_health(self, health):
        return capture_runtime_health(SimpleNamespace(
            _navigation_runtime_health_snapshot=lambda _: copy.deepcopy(health)))

    async def asgi_get(self, app, path):
        messages = []
        async def receive():
            return {'type':'http.request', 'body':b'', 'more_body':False}
        async def send(message):
            messages.append(message)
        scope = {'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'GET',
                 'scheme':'http','path':path,'raw_path':path.encode(),'query_string':b'','root_path':'',
                 'headers':[(b'host',b'testserver')], 'client':('127.0.0.1',1), 'server':('testserver',80)}
        await app(scope, receive, send)
        code = next(m['status'] for m in messages if m['type'] == 'http.response.start')
        data = b''.join(m.get('body',b'') for m in messages if m['type'] == 'http.response.body')
        return code, json.loads(data)

    async def real_proposal_handoff(self):
        """Use the genuine source identity and proposal pipeline with synthetic inputs."""
        case = proposal_fixture.ProposalTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.runtime.operational_navigation = self.manager
        case.runtime.fastlio_observation = self.observation
        case.session_id = self.service.session_id
        self.service.started = case.session_state['started_monotonic_s']
        self.service.current = {**self.service.ready(), 'observation_only':True,
                                'map_registration_applied':False}
        await self.observation.refresh()
        owner = GlobalObservationCoordinator(self.fixture.catalog, case.runtime.agent, case.runner)
        self.addCleanup(owner.close)
        case.runtime.global_observation = owner
        coordinator = NavigationInitializationProposals(case.runtime)
        started = coordinator.start('independent-real-source', self.generation, self.service.session_id)
        deadline = time.monotonic() + 3.
        while owner.job(started['proposal_id'])['worker_active'] and time.monotonic() < deadline:
            await asyncio.sleep(.005)
        self.assertFalse(owner.job(started['proposal_id'])['worker_active'])
        result = self.manager.confirm_proposal(coordinator, self.observation, started['proposal_id'],
            'independent-real-source-confirm', self.generation, self.service.session_id)
        return case, coordinator, result['handoff_id']

    async def test_dispatch_acceptance_requires_later_exact_inactive_receipt(self):
        confirmed=self.confirm();hid=confirmed['handoff_id']
        self.assertEqual(self.observation.handoff_receipt(hid)['state'],'NOT_REQUESTED')
        result=await asyncio.wait_for(self.observation.stop(self.service.session_id),2)
        self.assertEqual(result['state'],'STOPPING')
        pending=self.observation.handoff_receipt(hid)
        self.assertEqual(pending['state'],'DISPATCH_ACCEPTED')
        self.assertEqual(pending['session_id'],self.service.session_id)
        self.assertEqual(pending['started'],self.service.started)
        self.assertRegex(pending['nonce'],r'^[0-9a-f]{32}$')
        self.assertEqual(self.manager.handoff_status(hid)['state'],'STOP_PENDING')
        with self.assertRaisesRegex(ValueError,'HANDOFF_OBSERVATION_STOP_REQUIRED'):
            self.manager.preflight(self.map_id,self.map_revision)
        # A lost confirm response is recovered by its original idempotency key.
        self.assertEqual(self.confirm()['handoff_id'],hid)
        self.service.stopped()
        await self.observation.refresh()
        receipt=self.observation.handoff_receipt(hid)
        self.assertEqual(receipt['state'],'INACTIVE_CONFIRMED')
        self.assertEqual(receipt['nonce'],pending['nonce'])
        self.assertEqual((await self.wait_stop_boundary(hid))['state'],'OBSERVATION_STOPPED')
        self.assertEqual(self.service.calls,['stop'])

    async def test_second_stop_while_first_is_stopping_never_dispatches_twice(self):
        hid=self.confirm()['handoff_id']
        await self.observation.stop(self.service.session_id)
        with self.assertRaises(ObservationSessionConflict):
            await self.observation.stop(self.service.session_id)
        self.assertEqual(self.service.calls,['stop'])
        self.assertNotEqual(self.observation.handoff_receipt(hid)['state'],'INACTIVE_CONFIRMED')

    async def test_stale_stopped_observation_blocks_without_poisoning_handoff(self):
        hid = self.confirm()['handoff_id']
        await self.observation.stop(self.service.session_id)
        self.service.stopped()
        await self.observation.refresh()
        await self.wait_stop_boundary(hid)
        receipt = self.observation.handoff_receipt(hid)
        # Slow map reads can hold the shared admission lock past the six-second
        # monitor freshness bound. Expiry must still block all command gates.
        self.observation._updated_at = time.monotonic() - 6.1
        self.assertEqual(self.observation.snapshot()['state'], 'UNKNOWN')
        with patch.object(self.service, 'status', side_effect=ObservationServiceError('unavailable')):
            for check in (
                lambda: self.manager.preflight(self.map_id, self.map_revision),
                lambda: self.manager.snapshot_for_job(self.map_id, self.map_revision,
                                                     self.fixture.job_directory('stale-stop-job')),
            ):
                with self.assertRaisesRegex(ValueError, 'HANDOFF_OBSERVATION_STATUS_UNCONFIRMED'):
                    check()
        status = self.manager.status()['initialization_handoff']
        self.assertEqual((status['state'], status['reason']),
                         ('OUTCOME_UNKNOWN', 'HANDOFF_OBSERVATION_STATUS_UNCONFIRMED'))
        self.assertIsNone(status['geometry'])
        self.assertEqual(self.observation.handoff_receipt(hid), receipt)
        await self.observation.refresh()
        self.assertEqual(self.manager.handoff_status(hid)['state'], 'OBSERVATION_STOPPED')
        self.manager.preflight(self.map_id, self.map_revision)
        self.assertEqual(self.service.calls, ['stop'])

    async def test_admission_refreshes_stopped_service_without_renewing_monitor_cache(self):
        hid = self.confirm()['handoff_id']
        await self.observation.stop(self.service.session_id)
        self.service.stopped()
        await self.observation.refresh()
        await self.wait_stop_boundary(hid)
        expires = self.manager.selected['seed_geometry']['handoff']['expires_monotonic_s']
        self.observation._updated_at = time.monotonic() - 6.1
        cached_at = self.observation._updated_at
        # Exactly the admission mutex that prevents the normal monitor refresh.
        async with self.runtime.pipeline_coordination_lock:
            with patch.object(self.service, 'status', wraps=self.service.status) as read:
                self.manager.preflight(self.map_id, self.map_revision)
                self.manager.snapshot_for_job(self.map_id, self.map_revision,
                                             self.fixture.job_directory('fresh-stop-job'))
                self.assertGreaterEqual(read.call_count, 2)
        self.assertEqual(self.observation._updated_at, cached_at)
        self.assertEqual(self.observation.snapshot()['state'], 'UNKNOWN')
        self.assertEqual(self.manager.selected['seed_geometry']['handoff']['expires_monotonic_s'], expires)
        self.assertEqual(self.service.calls, ['stop'])

    async def test_fresh_stop_read_never_overrides_pending_transition_or_busy_service(self):
        hid = self.confirm()['handoff_id']
        await self.observation.stop(self.service.session_id)
        self.service.stopped()
        await self.observation.refresh()
        await self.wait_stop_boundary(hid)
        self.observation._updated_at = time.monotonic() - 6.1
        self.service.current.update(job_pending=True, busy=True)
        with self.assertRaisesRegex(ValueError, 'HANDOFF_OBSERVATION_STATUS_UNCONFIRMED'):
            self.manager.preflight(self.map_id, self.map_revision)
        self.service.stopped()
        original_status = self.service.status
        with patch.object(self.service, 'status', side_effect=lambda: (
                setattr(self.observation, '_pending', 'start') or original_status())):
            with self.assertRaises(ValueError):
                self.manager.preflight(self.map_id, self.map_revision)
        self.assertEqual(self.service.calls, ['stop'])

    async def test_different_session_after_stale_read_still_permanently_invalidates(self):
        hid = self.confirm()['handoff_id']
        await self.observation.stop(self.service.session_id)
        self.service.stopped()
        await self.observation.refresh()
        await self.wait_stop_boundary(hid)
        self.observation._updated_at = time.monotonic() - 6.1
        self.assertEqual(self.manager.handoff_status(hid)['state'], 'OUTCOME_UNKNOWN')
        self.service.stopped(session_id='f' * 32, started=self.service.started + 1)
        await self.observation.refresh()
        # Even a stale read retains positive evidence of the changed identity.
        self.observation._updated_at = time.monotonic() - 6.1
        self.assertEqual(self.manager.handoff_status(hid)['reason'], 'OBSERVATION_SESSION_CHANGED')
        self.service.stopped()
        await self.observation.refresh()
        self.assertEqual(self.manager.handoff_status(hid)['reason'], 'OBSERVATION_SESSION_CHANGED')

    async def test_another_session_after_dispatch_never_confirms_old_receipt(self):
        hid=self.confirm()['handoff_id']
        self.service.after_dispatch={**self.service.ready(),'session_id':'c'*32,'started_monotonic_s':self.service.started+1}
        await self.observation.stop(self.service.session_id)
        self.assertEqual(self.service.calls,['stop'])
        self.assertEqual(self.observation.handoff_receipt(hid)['state'],'OUTCOME_UNKNOWN')
        self.service.stopped()
        await self.observation.refresh()
        self.assertNotEqual(self.observation.handoff_receipt(hid)['state'],'INACTIVE_CONFIRMED')
        with self.assertRaisesRegex(ValueError,'HANDOFF_STOP_OUTCOME_UNKNOWN'):
            self.manager.preflight(self.map_id,self.map_revision)

    async def test_inactive_readback_with_same_id_but_other_start_is_not_receipt(self):
        hid=self.confirm()['handoff_id']
        await self.observation.stop(self.service.session_id)
        self.service.stopped(session_id=self.service.session_id,started=self.service.started+3)
        await self.observation.refresh()
        self.assertNotEqual(self.observation.handoff_receipt(hid)['state'],'INACTIVE_CONFIRMED')
        with self.assertRaises(ValueError):
            self.manager.preflight(self.map_id,self.map_revision)

    async def test_stop_dispatch_timeout_never_becomes_success_on_later_inactive(self):
        hid=self.confirm()['handoff_id']
        self.service.dispatch_error=ObservationServiceError('synthetic uncertain stop')
        with self.assertRaises(ObservationServiceError):
            await self.observation.stop(self.service.session_id)
        self.service.stopped()
        await self.observation.refresh()
        self.assertEqual(self.service.calls,['stop'])
        self.assertEqual(self.observation.handoff_receipt(hid)['state'],'OUTCOME_UNKNOWN')
        with self.assertRaisesRegex(ValueError,'HANDOFF_STOP_OUTCOME_UNKNOWN'):
            self.manager.preflight(self.map_id,self.map_revision)

    async def test_corrupted_confirmed_receipt_cannot_authorize_different_session(self):
        hid=self.confirm()['handoff_id']
        await self.observation.stop(self.service.session_id)
        self.service.stopped()
        await self.observation.refresh()
        self.assertEqual(self.observation.handoff_receipt(hid)['state'],'INACTIVE_CONFIRMED')
        self.assertEqual((await self.wait_stop_boundary(hid))['state'], 'OBSERVATION_STOPPED')
        with self.observation._lock:
            self.observation._handoff_receipts[hid]['session_id']='d'*32
        with self.assertRaises(ValueError):
            self.manager.preflight(self.map_id,self.map_revision)

    async def test_journal_error_after_dispatch_keeps_normal_stop_available(self):
        hid=self.confirm()['handoff_id']
        record=self.observation._handoff_record
        def fail_accepted(event,**kwargs):
            if event=='accepted':raise RuntimeError('synthetic journal failure')
            return record(event,**kwargs)
        with patch.object(self.observation,'_handoff_record',side_effect=fail_accepted):
            result=await asyncio.wait_for(self.observation.stop(self.service.session_id),2)
        self.assertEqual(result['state'],'STOPPING')
        self.assertEqual(self.service.calls,['stop'])
        self.assertEqual(self.observation.handoff_receipt(hid)['state'],'OUTCOME_UNKNOWN')
        with self.assertRaisesRegex(ValueError,'HANDOFF_STOP_OUTCOME_UNKNOWN'):
            self.manager.preflight(self.map_id,self.map_revision)

    async def test_confirm_response_loss_recovers_without_second_reservation(self):
        first = self.confirm(request_id='lost-response')
        recovered = preparation_inputs(self.manager, self.observation, None)
        handoff = recovered['operational_state']['initialization_handoff']
        self.assertEqual(handoff['handoff_id'], first['handoff_id'])
        self.assertIsNone(handoff['job_id'])
        self.assertEqual(len(self.observation._handoff_receipts), 1)
        self.assertEqual(self.confirm(request_id='lost-response')['handoff_id'], first['handoff_id'])
        self.assertEqual(self.service.calls, [])

    async def test_restoration_rejects_current_job_or_map_mismatch(self):
        first = self.confirm()
        await self.observation.stop(self.service.session_id)
        self.service.stopped()
        await self.observation.refresh()
        await self.wait_stop_boundary(first['handoff_id'])
        directory = self.fixture.job_directory('synthetic-job')
        self.manager.snapshot_for_job(self.map_id, self.map_revision, directory)
        self.assertEqual(self.manager._handoffs[first['handoff_id']]['job_id'], directory.name)
        pipeline = {'state':'running', 'job_id':'different-job'}
        map_state = {'id':self.map_id, 'revision':self.map_revision}
        with patch.object(self.fixture.jobs, 'snapshot', side_effect=lambda: {'pipeline':dict(pipeline), 'map':dict(map_state)}):
            result = preparation_inputs(self.manager, self.observation, None)
            self.assertIsNone(result['operational_state']['initialization_handoff'])
            pipeline['job_id'] = directory.name
            result = preparation_inputs(self.manager, self.observation, None)
            handoff = result['operational_state']['initialization_handoff']
            self.assertEqual(handoff['handoff_id'], first['handoff_id'])
            self.assertEqual(handoff['job_id'], directory.name)
            map_state['id'] = 'f' * 24
            result = preparation_inputs(self.manager, self.observation, None)
            self.assertIsNone(result['operational_state']['initialization_handoff'])

    async def test_bound_nonce_change_stays_unknown_even_if_old_nonce_returns(self):
        hid = self.confirm()['handoff_id']
        await self.observation.stop(self.service.session_id)
        original = self.observation.handoff_receipt(hid)['nonce']
        self.assertEqual(self.manager.handoff_status(hid)['state'], 'STOP_PENDING')
        with self.observation._lock:
            self.observation._handoff_receipts[hid]['nonce'] = 'e' * 32
        self.service.stopped()
        await self.observation.refresh()
        with self.assertRaisesRegex(ValueError, 'HANDOFF_STOP_OUTCOME_UNKNOWN'):
            self.manager.preflight(self.map_id, self.map_revision)
        with self.observation._lock:
            self.observation._handoff_receipts[hid]['nonce'] = original
        with self.assertRaisesRegex(ValueError, 'HANDOFF_STOP_OUTCOME_UNKNOWN'):
            self.manager.preflight(self.map_id, self.map_revision)

    async def test_job_phases_and_missing_or_mismatched_binding_are_not_ready(self):
        hid = self.confirm()['handoff_id']
        await self.observation.stop(self.service.session_id)
        self.service.stopped()
        await self.observation.refresh()
        await self.wait_stop_boundary(hid)
        directory = self.fixture.job_directory('phase-job')
        self.manager.snapshot_for_job(self.map_id, self.map_revision, directory)
        pipeline = {'state':'running', 'job_id':directory.name}
        map_state = {'id':self.map_id, 'revision':self.map_revision}
        def read():
            return preparation_inputs(self.manager, self.observation, None)['operational_state']['initialization_handoff']
        with patch.object(self.fixture.jobs, 'snapshot', side_effect=lambda: {'pipeline':dict(pipeline), 'map':dict(map_state)}):
            self.assertEqual(read()['state'], 'SNAPSHOTTED')
            for phase, reason in (('starting','HANDOFF_JOB_STARTING'), ('stopping','HANDOFF_JOB_STOPPING'),
                                  ('idle','HANDOFF_JOB_NOT_RUNNING'), ('stopped','HANDOFF_JOB_NOT_RUNNING'),
                                  ('failed','HANDOFF_JOB_NOT_RUNNING')):
                pipeline['state'] = phase
                value = read()
                self.assertEqual(value['reason'], reason)
                self.assertEqual(value['state'], 'OUTCOME_UNKNOWN' if phase in ('starting','stopping') else 'INVALID')
                self.assertIsNone(value['geometry'])
                for key, wrong in (('id','f'*24), ('revision','f'*64)):
                    original = map_state[key]
                    map_state[key] = wrong
                    self.assertIsNone(read())
                    self.assertEqual(self.manager.handoff_status(hid)['reason'], 'HANDOFF_RUNTIME_CHANGED')
                    map_state[key] = original
                pipeline['job_id'] = 'different-job'
                self.assertIsNone(read())
                pipeline['job_id'] = directory.name
            pipeline['state'] = 'running'
            # Reading temporary phases must not damage the valid handoff.
            self.assertEqual(read()['state'], 'SNAPSHOTTED')
            self.manager.check_initial_pose(self.map_id, self.map_revision, {'x':1., 'y':2., 'yaw':.2})
            self.manager.check_match(self.generation, self.map_id, self.map_revision)
            for target, key in ((pipeline,'job_id'), (map_state,'id'), (map_state,'revision')):
                original = target.pop(key)
                value = read()
                self.assertEqual(value['state'], 'OUTCOME_UNKNOWN')
                self.assertEqual(value['reason'], 'HANDOFF_JOB_CONTEXT_UNCONFIRMED')
                self.assertIsNone(value['geometry'])
                target[key] = original

    async def test_unbound_transition_reads_do_not_poison_later_start(self):
        hid = self.confirm()['handoff_id']
        pipeline = {'state':'starting', 'job_id':None}
        def read():
            return preparation_inputs(self.manager, self.observation, None)['operational_state']['initialization_handoff']
        with patch.object(self.fixture.jobs, 'snapshot', side_effect=lambda: {'pipeline':dict(pipeline), 'map':{}}):
            for phase in ('starting', 'running', 'stopping', 'unknown'):
                pipeline['state'] = phase
                value = read()
                self.assertEqual(value['state'], 'OUTCOME_UNKNOWN')
                self.assertEqual(value['reason'], 'HANDOFF_JOB_CONTEXT_UNCONFIRMED')
                self.assertIsNone(value['geometry'])
            for phase in ('idle', 'stopped', 'failed'):
                pipeline['state'] = phase
                self.assertEqual(read()['handoff_id'], hid)
                self.assertEqual(read()['state'], 'CONFIRMED_OBSERVATION_ACTIVE')
        await self.observation.stop(self.service.session_id)
        self.service.stopped()
        await self.observation.refresh()
        await self.wait_stop_boundary(hid)
        directory = self.fixture.job_directory('transition-job')
        self.manager.snapshot_for_job(self.map_id, self.map_revision, directory)
        snapshot = {'pipeline':{'state':'running', 'job_id':directory.name},
                    'map':{'id':self.map_id, 'revision':self.map_revision}}
        with patch.object(self.fixture.jobs, 'snapshot', return_value=snapshot):
            self.assertEqual(read()['state'], 'SNAPSHOTTED')
            self.manager.check_initial_pose(self.map_id, self.map_revision, {'x':1., 'y':2., 'yaw':.2})
            self.manager.check_match(self.generation, self.map_id, self.map_revision)

    async def test_observed_source_change_then_restoration_stays_invalid(self):
        case, _, hid = await self.real_proposal_handoff()
        agent = case.runtime.agent
        original_topic = agent.pose['topic']
        changed_read = threading.Event()
        original_snapshot = agent.pose_snapshot
        def observed_snapshot():
            value = original_snapshot()
            if value['topic'] != original_topic:
                changed_read.set()
            return value
        agent.pose_snapshot = observed_snapshot
        agent.pose['topic'] = '/utlidar/robot_odom'
        # No handoff/proposal GET drives detection: wait for a real observer read.
        self.assertTrue(await asyncio.to_thread(changed_read.wait, 3), 'source monitor did not sample changed topic')
        agent.pose['topic'] = original_topic
        await self.observation.stop(self.service.session_id)
        self.service.stopped()
        await self.observation.refresh()
        self.assertEqual(self.observation.handoff_receipt(hid)['state'], 'INACTIVE_CONFIRMED')
        self.assertEqual((await self.wait_stop_boundary(hid))['reason'], 'SOURCE_OR_CONTEXT_CHANGED')
        with self.assertRaisesRegex(ValueError, 'SOURCE_OR_CONTEXT_CHANGED'):
            self.manager.preflight(self.map_id, self.map_revision)
        self.assertEqual(self.service.calls, ['stop'])

    async def test_pre_dispatch_source_sample_is_not_erased_by_racing_stop(self):
        case, coordinator, hid = await self.real_proposal_handoff()
        agent = case.runtime.agent
        previous = agent.pose['topic']
        sampled, release = threading.Event(), threading.Event()
        original_sample = coordinator.handoff_watch_sample
        sample_times = []
        def paused_sample():
            value = original_sample()
            if agent.pose['topic'] != previous:
                sample_times.append(value['sample_end_ns'])
                sampled.set()
                if not release.wait(3):
                    raise RuntimeError('synthetic sample wait expired')
            return value
        coordinator.handoff_watch_sample = paused_sample
        agent.pose['topic'] = '/utlidar/robot_odom'
        try:
            self.assertTrue(await asyncio.to_thread(sampled.wait, 3))
            agent.pose['topic'] = previous
            await asyncio.wait_for(self.observation.stop(self.service.session_id), 2)
            receipt = self.observation.handoff_receipt(hid)
            self.assertEqual(receipt['state'], 'DISPATCH_ACCEPTED')
            self.assertLessEqual(sample_times[0], receipt['dispatch_monotonic_ns'])
        finally:
            release.set()
        self.service.stopped()
        await self.observation.refresh()
        self.assertEqual((await self.wait_stop_boundary(hid))['reason'], 'SOURCE_OR_CONTEXT_CHANGED')
        with self.assertRaisesRegex(ValueError, 'SOURCE_OR_CONTEXT_CHANGED'):
            self.manager.preflight(self.map_id, self.map_revision)
        self.assertEqual(self.service.calls, ['stop'])

    async def test_monitor_failure_blocks_handoff_but_never_normal_stop(self):
        case, _, hid = await self.real_proposal_handoff()
        sampled = threading.Event()
        def broken_snapshot():
            sampled.set()
            raise RuntimeError('synthetic source read failure')
        case.runtime.agent.pose_snapshot = broken_snapshot
        self.assertTrue(await asyncio.to_thread(sampled.wait, 3))
        deadline = time.monotonic() + 2.
        while time.monotonic() < deadline:
            status = self.manager.handoff_status(hid)
            if status['reason'] == 'HANDOFF_MONITOR_UNAVAILABLE':
                break
            await asyncio.sleep(.01)
        self.assertEqual(status['reason'], 'HANDOFF_MONITOR_UNAVAILABLE')
        await asyncio.wait_for(self.observation.stop(self.service.session_id), 2)
        self.service.stopped()
        await self.observation.refresh()
        self.assertEqual(self.service.calls, ['stop'])
        with self.assertRaisesRegex(ValueError, 'HANDOFF_MONITOR_UNAVAILABLE'):
            self.manager.preflight(self.map_id, self.map_revision)

    async def test_expected_source_disappearance_during_normal_stop_and_monitor_cleanup(self):
        case, _, hid = await self.real_proposal_handoff()
        agent = case.runtime.agent
        original_snapshot = agent.pose_snapshot
        calls = []
        def observed_snapshot():
            calls.append(time.monotonic())
            if self.service.current['state'] in ('STOPPING', 'STOPPED'):
                return None  # Expected input disappearance as the observation ends.
            return original_snapshot()
        agent.pose_snapshot = observed_snapshot
        await self.observation.stop(self.service.session_id)
        await asyncio.sleep(.3)
        self.service.stopped()
        await self.observation.refresh()
        self.assertEqual(self.observation.handoff_receipt(hid)['state'], 'INACTIVE_CONFIRMED')
        await self.wait_stop_boundary(hid)
        self.manager.preflight(self.map_id, self.map_revision)
        await asyncio.sleep(.4)
        count = len(calls)
        await asyncio.sleep(.5)
        self.assertEqual(len(calls), count, 'source monitor continued after normal stop')
        self.assertEqual(self.service.calls, ['stop'])

    async def test_match_restoration_requires_fresh_current_runtime_and_localization(self):
        hid = self.confirm()['handoff_id']
        await self.observation.stop(self.service.session_id)
        self.service.stopped()
        await self.observation.refresh()
        await self.wait_stop_boundary(hid)
        directory = self.fixture.job_directory('c' * 32)
        self.manager.snapshot_for_job(self.map_id, self.map_revision, directory)
        job_snapshot = {'pipeline':{'state':'running', 'job_id':directory.name},
                        'map':{'id':self.map_id, 'revision':self.map_revision}}
        health = self.synthetic_match_health()
        source = health['operational_3d']
        instance = health['runtime_instance_generation']
        agent = SimpleNamespace(_navigation_runtime_health_snapshot=lambda _: copy.deepcopy(health))
        def read():
            return preparation_inputs(self.manager, self.observation, agent)['operational_state']['initialization_handoff']
        with patch.object(self.fixture.jobs, 'snapshot', return_value=job_snapshot):
            restored = read()
            self.assertEqual(restored['state'], 'MATCH_ARMED')
            self.assertEqual(restored['match_history'], {'runtime_instance_generation':instance,
                'localization_generation':2, 'initial_pose_stamp_ns':'1234', 'match_request_id':'synthetic-match'})
            missing = self.manager.handoff_status(hid, health=None)
            self.assertEqual((missing['state'], missing['reason']),
                             ('OUTCOME_UNKNOWN', 'HANDOFF_MATCH_CURRENT_UNCONFIRMED'))
            self.assertIsNone(missing['geometry'])
            self.assertEqual(missing['match_history'], restored['match_history'])
            raw = self.manager.handoff_status(hid, health=health)
            self.assertEqual((raw['state'], raw['reason']),
                             ('OUTCOME_UNKNOWN', 'HANDOFF_MATCH_CURRENT_UNCONFIRMED'))
            source['initial_pose_receipt']['stamp_ns'] = '9999'
            self.assertNotEqual(read()['state'], 'MATCH_ARMED')
            source['initial_pose_receipt']['stamp_ns'] = '1234'
            self.assertEqual(read()['state'], 'MATCH_ARMED')
            self.manager._handoffs[hid]['geometry']['handoff']['expires_monotonic_s'] = time.monotonic() - 1
            self.manager.selected['seed_geometry']['handoff']['expires_monotonic_s'] = time.monotonic() - 1
            self.assertEqual(read()['state'], 'MATCH_ARMED')
            # Same job/map is insufficient if a new runtime has not accepted match.
            new_instance = f'124:{time.monotonic_ns()}'
            health.update(process_generation=124, runtime_instance_generation=new_instance)
            source.update(runtime_instance_generation=new_instance, match_armed=False)
            mismatch = read()
            self.assertEqual((mismatch['state'], mismatch['reason']), ('INVALID', 'HANDOFF_RUNTIME_CHANGED'))
            self.assertIsNone(mismatch['geometry'])
            self.assertEqual(mismatch['match_history'], restored['match_history'])
            # Even matching identifiers cannot turn stale health into current acceptance.
            health.update(process_generation=123, runtime_instance_generation=instance, fresh=False, age_s=2.)
            source.update(runtime_instance_generation=instance, match_armed=True)
            stale = read()
            self.assertEqual((stale['state'], stale['reason']), ('OUTCOME_UNKNOWN', 'HANDOFF_MATCH_CURRENT_UNCONFIRMED'))
            self.assertIsNone(stale['initial_pose_reference'])
            health.update(fresh=True, age_s=2.)
            stale = read()
            self.assertEqual((stale['state'], stale['reason']),
                             ('OUTCOME_UNKNOWN', 'HANDOFF_MATCH_CURRENT_UNCONFIRMED'))
            health.update(fresh=True, age_s=.01)
            source['localization_generation'] = 3
            mismatch = read()
            self.assertEqual((mismatch['state'], mismatch['reason']), ('INVALID', 'HANDOFF_RUNTIME_CHANGED'))
        self.assertEqual(self.service.calls, ['stop'])

    async def test_delayed_health_is_not_presented_as_current_by_get_routes(self):
        hid = self.confirm()['handoff_id']
        await self.observation.stop(self.service.session_id)
        self.service.stopped()
        await self.observation.refresh()
        await self.wait_stop_boundary(hid)
        directory = self.fixture.job_directory('d'*32)
        self.manager.snapshot_for_job(self.map_id, self.map_revision, directory)
        job_snapshot = {'pipeline':{'state':'running', 'job_id':directory.name},
                        'map':{'id':self.map_id, 'revision':self.map_revision}}
        health = self.synthetic_match_health()
        receipt = health['operational_3d']['match_receipt']
        self.manager.record_match_armed(self.generation, self.map_id, self.map_revision, receipt,
                                        self.capture_synthetic_health(health))
        capture = []
        mode = {'value':'none'}
        armed, locked, release = threading.Event(), threading.Event(), threading.Event()
        def lock_holder():
            if not armed.wait(3):
                return
            with self.manager.lock:
                locked.set()
                release.wait(4)
        def health_snapshot(_):
            capture.append(time.monotonic())
            if mode['value'] == 'direct':
                armed.set()
                if not locked.wait(3):
                    raise RuntimeError('lock fixture did not acquire')
            return copy.deepcopy(health)
        agent = SimpleNamespace(_navigation_runtime_health_snapshot=health_snapshot)
        app = FastAPI()
        app.include_router(operational_router)
        app.state.runtime = ApplicationRuntime(operational_navigation=self.manager,
                                                fastlio_observation=self.observation, agent=agent)
        original_record = self.manager.record_match_armed
        def record_then_lock(*args, **kwargs):
            result = original_record(*args, **kwargs)
            if mode['value'] == 'preparation':
                armed.set()
                if not locked.wait(3):
                    raise RuntimeError('lock fixture did not acquire')
            return result
        observations = {}
        with patch.object(self.fixture.jobs, 'snapshot', return_value=job_snapshot), \
             patch.object(self.manager, 'record_match_armed', side_effect=record_then_lock):
            for variant, path in (('direct', f'/api/v1/navigation/operational-3d/initialization-handoffs/{hid}'),
                                  ('preparation', '/api/v1/navigation/operational-3d/preparation-inputs')):
                mode['value'] = variant
                armed.clear(); locked.clear(); release.clear(); capture.clear()
                holder = threading.Thread(target=lock_holder, daemon=True)
                holder.start()
                task = asyncio.create_task(self.asgi_get(app, path))
                try:
                    self.assertTrue(await asyncio.to_thread(locked.wait, 3), variant)
                    await asyncio.sleep(.95)
                finally:
                    released_at = time.monotonic()
                    release.set()
                code, value = await asyncio.wait_for(task, 4)
                holder.join(timeout=1)
                self.assertEqual(code, 200)
                handoff = value if variant == 'direct' else value['operational_state']['initialization_handoff']
                observations[variant] = (handoff['state'], handoff['reason'], round(released_at - capture[-1], 3))
        for variant, (state, reason, delay) in observations.items():
            self.assertGreater(delay, .75, observations)
            self.assertEqual((state, reason), ('OUTCOME_UNKNOWN', 'HANDOFF_MATCH_CURRENT_UNCONFIRMED'), observations)

    async def test_slow_confirm_validation_does_not_invalidate_healthy_monitor(self):
        original = self.manager._revalidate_pair
        delayed = threading.Event()
        agent = self.proposal_owner.runtime.agent
        updates = []
        monitored = []
        original_sample = self.proposal_owner.handoff_watch_sample
        def observed_sample():
            result = original_sample()
            if delayed.is_set():
                monitored.append(time.monotonic())
            return result
        self.proposal_owner.handoff_watch_sample = observed_sample
        async def feed_fresh_source():
            while True:
                now = time.monotonic()
                for sample in (agent.cloud, agent.pose):
                    sample['observation']['received_monotonic_s'] = now
                    sample['observation']['subscription_evidence']['graph']['observed_monotonic_s'] = now
                updates.append(now)
                await asyncio.sleep(.05)
        def slow_final_validation(bundle, **kwargs):
            if (bundle.get('seed_geometry') or {}).get('source') == 'proposal_confirmed':
                delayed.set()
                time.sleep(2.2)  # Simulate the same real slow asset-read boundary.
            return original(bundle, **kwargs)
        feeder = asyncio.create_task(feed_fresh_source())
        try:
            with patch.object(self.manager, '_revalidate_pair', side_effect=slow_final_validation):
                result = await asyncio.wait_for(asyncio.to_thread(self.confirm), 5)
            self.assertGreater(len(updates), 20, 'fresh inputs were not fed during asset delay')
            self.assertGreaterEqual(len(monitored), 5, 'source watcher did not run during asset delay')
            current = self.proposal_owner.handoff_watch_context('b'*24, self.service.session_id)
            self.assertEqual(current['session']['session_id'], self.service.session_id)
            self.assertEqual(self.observation.snapshot()['state'], 'READY')
        finally:
            feeder.cancel()
            await asyncio.gather(feeder, return_exceptions=True)
        self.assertTrue(delayed.is_set(), 'final validation delay was not exercised')
        self.assertEqual((result['state'], result['reason']), ('CONFIRMED_OBSERVATION_ACTIVE', None), result)
        status = self.manager.handoff_status(result['handoff_id'])
        self.assertEqual((status['state'], status['reason']), ('CONFIRMED_OBSERVATION_ACTIVE', None), status)

    async def test_inflight_dispatch_does_not_deadlock_receipt_or_normal_stop(self):
        hid=self.confirm()['handoff_id']
        self.service.entered=threading.Event();self.service.release=threading.Event()
        task=asyncio.create_task(self.observation.stop(self.service.session_id))
        try:
            entered=await asyncio.to_thread(self.service.entered.wait,2)
            self.assertTrue(entered,'dispatch did not start')
            self.assertEqual(self.observation.handoff_receipt(hid)['state'],'DISPATCH_PENDING')
            self.assertEqual(self.manager.handoff_status(hid)['state'],'STOP_PENDING')
        finally:
            self.service.release.set()
            await asyncio.wait_for(task,3)
        self.assertEqual(self.service.calls,['stop'])
        self.assertEqual(self.observation.handoff_receipt(hid)['state'],'DISPATCH_ACCEPTED')

    async def test_expired_after_match_keeps_quality_checks_and_requires_fresh_reinit(self):
        hid = self.confirm()['handoff_id']
        await self.observation.stop(self.service.session_id)
        self.service.stopped()
        await self.observation.refresh()
        await self.wait_stop_boundary(hid)
        directory = self.fixture.job_directory('ttl-quality-job')
        self.manager.snapshot_for_job(self.map_id, self.map_revision, directory)
        job_snapshot = {'pipeline':{'state':'running', 'job_id':directory.name},
                        'map':{'id':self.map_id, 'revision':self.map_revision}}
        job_patch = patch.object(self.fixture.jobs, 'snapshot', return_value=job_snapshot)
        job_patch.start()
        self.addCleanup(job_patch.stop)
        bundle = json.loads((directory / 'operational-3d.json').read_text())
        fixture = localization_fixture.Operational3DLocalizationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        engine = OperationalLocalizer(bundle, directory / 'localization-reference.pcd', clock=fixture.clock)
        self.addCleanup(engine.close)
        fixture.clock.value = time.monotonic()
        engine.observe_odometry(fixture.stamp, np.eye(4), fixture.clock())
        for _ in range(23):
            fixture.observe(engine, np.eye(4))
        pose = from_translation_rpy([1., 2., .5], [.1, -.1, .2])
        engine.reseed(pose, stamp_ns='1234')
        engine.start_matching('1234')
        health = self.synthetic_match_health(generation=engine.generation,
                                             accepted_initial_pose=engine.accepted_initial_pose)
        receipt = health['operational_3d']['match_receipt']
        self.manager.record_match_armed(self.generation, self.map_id, self.map_revision,
                                        receipt, self.capture_synthetic_health(health), expected_stamp='1234')
        self.assertEqual(self.manager.handoff_status(hid, health=self.capture_synthetic_health(health))['state'], 'MATCH_ARMED')
        # Independently advance the handoff deadline after explicit acceptance;
        # the estimator's clock and normal freshness gates remain intact.
        engine.bundle['seed_geometry']['handoff']['expires_monotonic_s'] = time.monotonic() - 1
        self.manager._handoffs[hid]['geometry']['handoff']['expires_monotonic_s'] = time.monotonic() - 1
        self.assertEqual(self.manager.handoff_status(hid, health=self.capture_synthetic_health(health))['state'], 'MATCH_ARMED')
        self.assertTrue(engine.match_armed)
        self.assertFalse(engine.status()['ready'])
        # Use the real asynchronous submit/poll path, while controlling solver
        # quality independently of the synthetic reference-map geometry.
        low_quality = {'status':'CANDIDATE', 'metrics':{'rmse_m':.03, 'overlap_ratio':.70}}
        with patch('robot_dashboard.relocalization.operational.solve_prepared',
                   return_value=(low_quality, engine.seed.copy())):
            self.assertTrue(engine.submit(fixture.points, fixture.stamp, np.eye(4), fixture.clock()))
            engine.future.result(timeout=5)
            engine.poll()
        self.assertFalse(engine.status()['ready'])
        self.assertEqual(engine.reason, 'INITIAL_REFINEMENT_LOW_OVERLAP')
        for index in range(3):
            fixture.observe(engine, np.eye(4))
            fixture.inject_initial_result(engine, engine.seed.copy(), overlap=.95)
            self.assertEqual(engine.status()['ready'], index == 2)
        self.assertIsNotNone(engine.nav_odom())
        with self.assertRaisesRegex(ValueError, 'HANDOFF_EXPIRED'):
            engine.start_matching('1234')
        with self.assertRaisesRegex(ValueError, 'HANDOFF_EXPIRED'):
            engine.reseed(pose, stamp_ns='1235')


if __name__=='__main__':unittest.main()
