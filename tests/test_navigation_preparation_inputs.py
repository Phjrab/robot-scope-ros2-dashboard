"""Read-only preparation provenance and generation gates without ROS or hardware."""
import copy
import json
import math
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from fastapi import FastAPI

from robot_dashboard.application.navigation_preparation_inputs import preparation_inputs, observation_start_blockers
from robot_dashboard.api.routers.operational_navigation import router
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.application.operational_navigation import OperationalNavigation
from robot_dashboard.ros.observation_identity import ObservationIdentity
from test_observation_subscription_evidence import evidence, CLOUD_TYPE, POSE_TYPE
import test_operational_navigation_bundle as bundle_test


def fixture():
    now = time.monotonic()
    cloud_topic, pose_topic = '/cloud_registered', '/Odometry'
    def obs(topic, typ):
        return ObservationIdentity().observe(topic=topic, frame='camera_init', stamp_ns=12345,
            received=now, publisher_count=1, observation_context=evidence(topic, typ, at=now))
    cloud = dict(topic=cloud_topic, frame_id='camera_init', pipeline_stage='registered', units='m', seq=1,
                 sent_points=80, points_bytes=np.ones((80, 3), dtype='<f4').tobytes(), observation=obs(cloud_topic, CLOUD_TYPE))
    pose = dict(topic=pose_topic, frame_id='camera_init', child_frame_id='body', state='ok', seq=1,
                position=dict(x=1., y=2., z=3.), orientation=dict(x=0., y=0., z=0., w=1.),
                observation=obs(pose_topic, POSE_TYPE))
    pair = dict(generation='a'*32, valid=True, calibration_sha256='b'*64,
                localization_3d=dict(map_id='c'*24, revision='d'*64, frame='camera_init', sha256='e'*64),
                navigation_2d=dict(map_id='f'*24, revision='1'*64, frame='map'))
    transform = np.eye(4); transform[2, 3] = .4
    state = dict(pair=pair, selected={'calibration': {'T_imu_base': transform.tolist()}})
    session = dict(state='READY', active=True, session_id='2'*32, started_monotonic_s=now-.1)
    class Agent:
        def __init__(self): self.cloud, self.pose, self.health = cloud, pose, {}
        def pointcloud_binary_snapshot(self): return copy.deepcopy(self.cloud)
        def pose_snapshot(self): return copy.deepcopy(self.pose)
        def observation_pose_near(self, observation, *, provenance_mode):
            return copy.deepcopy(self.pose)
        def _navigation_runtime_health_snapshot(self, _): return copy.deepcopy(self.health)
    agent = Agent()
    execution = dict(job_id='7'*32, source='STORED_PCD_FASTLIO', bundle_generation=pair['generation'],
                     map_id=pair['navigation_2d']['map_id'], map_revision=pair['navigation_2d']['revision'],
                     localization_map_id=pair['localization_3d']['map_id'],
                     localization_map_revision=pair['localization_3d']['revision'],
                     snapshot_monotonic_ns=time.monotonic_ns()-1_000_000_000)
    manager = SimpleNamespace(status=lambda: copy.deepcopy(state), preparation_execution=lambda: copy.deepcopy(execution))
    service = SimpleNamespace(snapshot=lambda: copy.deepcopy(session))
    return manager, service, agent, state, session


def active_health(pair):
    generation = f'123:{time.monotonic_ns() - 500_000_000}'
    pins = dict(bundle_generation=pair['generation'], map_id=pair['navigation_2d']['map_id'],
                map_revision=pair['navigation_2d']['revision'], localization_map_id=pair['localization_3d']['map_id'],
                localization_map_revision=pair['localization_3d']['revision'], runtime_instance_generation=generation,
                localization_generation=2)
    marker = dict(**pins, source='STORED_PCD_FASTLIO', pose=dict(z=.42, roll=.03, pitch=-.04),
                  stamp_ns='12345', correction_sequence=3, stale=False, age_s=.05)
    source = dict(**pins, source='STORED_PCD_FASTLIO', ready=True, reference_sha256=pair['localization_3d']['sha256'],
                  correction_sequence=3, estimated_pose=marker)
    return dict(fresh=True, age_s=.05, process_generation=123, runtime_instance_generation=generation, operational_3d=source)


class PreparationTests(unittest.TestCase):
    def test_exact_pair_calibrated_reference_is_never_map_candidate(self):
        manager, service, agent, _, _ = fixture()
        result = preparation_inputs(manager, service, agent)
        self.assertTrue(result['evidence']['valid'])
        self.assertEqual(result['reference_pose']['frame'], 'camera_init')
        self.assertAlmostEqual(result['reference_pose']['position']['z'], 3.4)
        self.assertEqual(result['evidence']['pose']['source_stamp_ns'], result['evidence']['cloud']['source_stamp_ns'])
        self.assertNotIn('points_bytes', json.dumps(result))
        self.assertEqual(result['candidates']['z']['reason'], 'MAP_ABSOLUTE_Z_UNVERIFIED')
        self.assertEqual(result['candidates']['pitch']['reason'], 'MAP_GRAVITY_ALIGNMENT_UNVERIFIED')
        self.assertTrue(all(not v['available'] and v['value'] is None for v in result['candidates'].values()))

    def test_bad_observation_never_yields_reference(self):
        for mutation in ('stamp', 'stale', 'source', 'quaternion', 'session', 'calibration'):
            with self.subTest(mutation=mutation):
                manager, service, agent, state, session = fixture()
                if mutation == 'stamp': agent.pose['observation']['source_stamp_ns'] = '12346'
                if mutation == 'stale': agent.cloud['observation']['received_monotonic_s'] -= 2
                if mutation == 'source': agent.pose['topic'] = '/utlidar/robot_odom'
                if mutation == 'quaternion': agent.pose['orientation']['w'] = .2
                if mutation == 'session': session['state'] = 'STOPPED'; session['active'] = False
                if mutation == 'calibration': state['pair']['valid'] = False
                result = preparation_inputs(manager, service, agent)
                self.assertFalse(result['evidence']['valid'])
                self.assertIsNone(result['reference_pose'])
                self.assertTrue(all(not v['available'] for v in result['candidates'].values()))

    def test_map_estimate_requires_fresh_matching_quality_and_all_generations(self):
        manager, service, agent, state, _ = fixture()
        agent.health = active_health(state['pair'])
        result = preparation_inputs(manager, service, agent)
        self.assertEqual(result['candidates']['z']['value'], .42)
        self.assertTrue(all(v['available'] for v in result['candidates'].values()))
        self.assertEqual(result['candidates']['z']['provenance']['source_stamp_ns'], '12345')
        for mutation in ('revision', 'generation', 'runtime', 'stale', 'correction', 'health_age', 'reference', 'nonfinite'):
            with self.subTest(mutation=mutation):
                agent.health = active_health(state['pair'])
                h, s = agent.health, agent.health['operational_3d']
                if mutation == 'revision': s['estimated_pose']['map_revision'] = 'x'*64
                if mutation == 'generation': s['bundle_generation'] = '4'*32
                if mutation == 'runtime': h['runtime_instance_generation'] = '5'*32
                if mutation == 'stale': s['estimated_pose']['stale'] = True
                if mutation == 'correction': s['correction_sequence'] = 0
                if mutation == 'health_age': h['age_s'] = .6
                if mutation == 'reference': s['reference_sha256'] = '6'*64
                if mutation == 'nonfinite': s['estimated_pose']['pose']['z'] = math.nan
                result = preparation_inputs(manager, service, agent)
                self.assertTrue(all(not v['available'] for v in result['candidates'].values()))

    def test_stopped_or_restarted_job_cannot_reuse_fresh_old_health(self):
        manager, service, agent, state, _ = fixture()
        agent.health = active_health(state['pair'])
        self.assertTrue(preparation_inputs(manager, service, agent)['candidates']['z']['available'])
        previous = manager.preparation_execution()
        manager.preparation_execution = lambda: None
        stopped = preparation_inputs(manager, service, agent)
        self.assertFalse(stopped['candidates']['z']['available'])
        self.assertEqual(stopped['map_estimate_reason'], 'NAVIGATION_JOB_NOT_RUNNING')
        restarted = {**previous, 'job_id': '8'*32, 'snapshot_monotonic_ns': time.monotonic_ns()}
        manager.preparation_execution = lambda: restarted
        self.assertFalse(preparation_inputs(manager, service, agent)['candidates']['z']['available'])
        calls = [0]
        def transition():
            calls[0] += 1
            return previous if calls[0] == 1 else restarted
        manager.preparation_execution = transition
        self.assertFalse(preparation_inputs(manager, service, agent)['candidates']['z']['available'])

    def test_start_blockers_expose_bridge_and_busy_or_unknown_owners(self):
        bridge = SimpleNamespace(_read_systemd=lambda: {'available': True, 'active_state': 'active'})
        owner = SimpleNamespace(snapshot=lambda: {'can_start': True})
        runtime = SimpleNamespace(fastlio_observation=owner,
                                  lifecycle=SimpleNamespace(control_bridge_lifecycle=bridge))
        owners = {'busy_components': ['navigation', 'legacy_alignment'],
                  'unknown_components': ['dataset']}
        with patch('robot_dashboard.application.ownership_readback.ownership_readback', return_value=owners):
            result = observation_start_blockers(runtime)
        self.assertEqual(result['items'], ['OWNER_BUSY:navigation', 'OWNER_UNKNOWN:dataset',
                                           'CONTROL_BRIDGE_NOT_INACTIVE'])
        self.assertTrue(result['advisory'])
        bridge._read_systemd = lambda: {'available': False, 'active_state': 'unknown'}
        with patch('robot_dashboard.application.ownership_readback.ownership_readback', return_value=owners):
            self.assertIn('CONTROL_BRIDGE_STATE_UNKNOWN', observation_start_blockers(runtime)['items'])

    def test_single_final_asset_validation_detects_changes_after_tentative_snapshot(self):
        case = bundle_test.OperationalNavigationBundleTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.manager.select_pair(case.pair_fixture())
        snapshot = case.manager.preparation_snapshot
        def change_calibration():
            tentative = snapshot()
            case.calibration['evidence'] = 'changed after tentative capture'
            case.write_calibration()
            return tentative
        with patch.object(case.manager, 'preparation_snapshot', side_effect=change_calibration), \
             patch.object(case.manager, '_revalidate_pair', wraps=case.manager._revalidate_pair) as check:
            result = preparation_inputs(case.manager, None, None)
        self.assertEqual(check.call_count, 1)
        self.assertFalse(result['pair']['valid'])
        self.assertEqual(result['evidence']['reason'], 'MAP_PAIR_INVALID')
        self.assertTrue(all(not item['available'] for item in result['candidates'].values()))

    def test_slow_final_validation_expires_independent_freshness_limits(self):
        for delay, reference_valid in ((.60, True), (1.05, False)):
            with self.subTest(delay=delay):
                manager, service, agent, state, _ = fixture()
                manager.preparation_snapshot = lambda: copy.deepcopy(state)
                agent.health = active_health(state['pair'])
                health_at = time.monotonic()
                def health(_):
                    result = copy.deepcopy(agent.health)
                    result['age_s'] += time.monotonic() - health_at
                    return result
                agent._navigation_runtime_health_snapshot = health
                def slow_status():
                    time.sleep(delay)
                    return copy.deepcopy(state)
                manager.status = slow_status
                start = time.perf_counter()
                result = preparation_inputs(manager, service, agent)
                elapsed = time.perf_counter() - start
                self.assertGreaterEqual(elapsed, delay)
                self.assertEqual(result['evidence']['valid'], reference_valid)
                self.assertEqual(result['reference_pose'] is not None, reference_valid)
                self.assertFalse(result['candidates']['z']['available'])
                if not reference_valid:
                    self.assertEqual(result['evidence']['reason'], 'OBSERVATION_STALE_OR_SOURCE_INVALID')

    def test_observation_is_rechecked_after_slow_health_read(self):
        manager, service, agent, state, _ = fixture()
        manager.preparation_snapshot = lambda: copy.deepcopy(state)
        def slow_health(_):
            time.sleep(1.05)
            return {}
        agent._navigation_runtime_health_snapshot = slow_health
        result = preparation_inputs(manager, service, agent)
        self.assertFalse(result['evidence']['valid'])
        self.assertIsNone(result['reference_pose'])
        self.assertEqual(result['evidence']['reason'], 'OBSERVATION_STALE_OR_SOURCE_INVALID')

    def test_selected_context_change_during_final_validation_is_rejected(self):
        manager, service, agent, state, _ = fixture()
        manager.preparation_snapshot = lambda: copy.deepcopy(state)
        def change_selection():
            result = copy.deepcopy(state)
            result['pair']['generation'] = '9'*32
            return result
        manager.status = change_selection
        result = preparation_inputs(manager, service, agent)
        self.assertEqual(result['evidence']['reason'], 'CONTEXT_CHANGED')
        self.assertIsNone(result['reference_pose'])

    def test_manager_exposes_only_current_running_bound_job(self):
        pipeline = {'state': 'running', 'job_id': 'a'*32}
        manager = OperationalNavigation(None, '/tmp', SimpleNamespace(snapshot=lambda: {'pipeline': dict(pipeline)}))
        manager.snapshot_binding = {'job_id': 'a'*32, 'source': 'STORED_PCD_FASTLIO'}
        manager._snapshot_binding_monotonic_ns = 100
        self.assertEqual(manager.preparation_execution()['job_id'], 'a'*32)
        for change in ({'state': 'stopped', 'job_id': 'a'*32}, {'state': 'running', 'job_id': 'b'*32}):
            pipeline.update(change)
            self.assertIsNone(manager.preparation_execution())

    def test_context_change_discards_observation(self):
        manager, service, agent, state, session = fixture()
        reads = [0]
        def changing():
            reads[0] += 1
            if reads[0] == 2: session['session_id'] = '9'*32
            return copy.deepcopy(session)
        service.snapshot = changing
        result = preparation_inputs(manager, service, agent)
        self.assertEqual(result['evidence']['reason'], 'CONTEXT_CHANGED')
        self.assertIsNone(result['reference_pose'])


class PreparationTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_is_read_only_and_returns_contract(self):
        runtime = ApplicationRuntime()
        manager = SimpleNamespace(status=lambda: {'pair': None})
        runtime.operational_navigation = manager
        runtime.fastlio_observation = None
        runtime.agent = None
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router)
        async def inline_thread(func, *args):
            return func(*args)
        # This sandbox's Python executor shutdown hangs even for a trivial to_thread.
        messages = []
        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        async def send(message):
            messages.append(message)
        path = '/api/v1/navigation/operational-3d/preparation-inputs'
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                 'method': 'GET', 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
                 'query_string': b'', 'root_path': '', 'headers': [(b'host', b'test')],
                 'server': ('test', 80), 'client': ('test', 1)}
        with patch('robot_dashboard.api.routers.operational_navigation.asyncio.to_thread', inline_thread):
            await app(scope, receive, send)
        self.assertEqual(messages[0]['status'], 200)
        self.assertIn((b'cache-control', b'no-store'), messages[0]['headers'])
        result = json.loads(b''.join(message.get('body', b'') for message in messages[1:]))
        self.assertEqual(result['schema'], 'robot-scope.navigation-preparation-inputs.v1')
        self.assertEqual(result['candidates']['z']['reason'], 'MAP_PAIR_REQUIRED')
        self.assertEqual(result['start_blockers']['items'], ['OBSERVATION_STATUS_UNAVAILABLE'])
