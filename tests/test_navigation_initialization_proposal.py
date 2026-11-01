"""End-to-end synthetic coordinator/ASGI contract; no ROS or robot commands."""
import asyncio
import copy
import hashlib
import math
import time
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from fastapi import FastAPI

from robot_dashboard.api.routers.operational_navigation import router
from robot_dashboard.application.global_observation import GlobalObservationCoordinator
from robot_dashboard.application.navigation_initialization_proposal import (
    NavigationInitializationProposals, ProposalConflict, ProposalUnavailable,
)
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy
from test_anchor_proposal import result_for
from test_navigation_preparation_inputs import fixture
from test_navigation_presets import LocalASGIClient
import test_operational_navigation_bundle as bundle_fixture


class Catalog:
    def __init__(self, pair):
        self.pair = pair
    def metadata(self, identifier):
        assert identifier == self.pair['localization_3d']['map_id']
        return dict(kind='pointcloud3d', format='pcd-binary', revision=self.pair['localization_3d']['revision'],
                    frame_id=self.pair['localization_3d']['frame'])
    def raw_global_reference(self, identifier, revision, **kwargs):
        data = np.arange(240, dtype='<f8').reshape(80, 3).tobytes()
        return dict(xyz_bytes=data, sha256=hashlib.sha256(data).hexdigest(),
                    source_sha256=self.pair['localization_3d']['sha256'], encoding='float64_le_xyz',
                    point_count=80, frame_id=self.pair['localization_3d']['frame'], units='m')


class Runner:
    def __init__(self):
        self.pose = from_translation_rpy([4., -1., 2.], [.2, -.1, .4])
        self.override = False
        self.allow_ambiguous = True  # Existing deployed option can remain enabled.
        self.calls = 0
        self.entered, self.release = threading.Event(), threading.Event()
        self.release.set()
    def status(self):
        return {'available': True, 'backend_id': 'synthetic', 'allow_ambiguous': self.allow_ambiguous}
    def run_arrays(self, *, scan_bytes, map_bytes, context, cancel_event):
        self.calls += 1
        self.entered.set()
        self.release.wait(5.)
        result = result_for(context, self.pose)
        if self.override:
            result['ambiguity_override'] = {'enabled': True, 'applied': True}
        return result


class ProposalTests(unittest.TestCase):
    def setUp(self):
        manager, session, agent, self.state, self.session_state = fixture()
        self.state['selected']['calibration']['T_nav_map_from_localization_map'] = from_translation_rpy(
            [2., -.5, .7], [.12, -.08, .3]).tolist()
        self.session_state.update(observation_only=True, map_registration_applied=False)
        manager.lock = threading.RLock()
        manager.preparation_snapshot = lambda: copy.deepcopy(self.state)
        manager.verify_preparation_calibration = lambda *_: True
        self.runtime = ApplicationRuntime(operational_navigation=manager, fastlio_observation=session,
                                          agent=agent, competition=SimpleNamespace(
                                              require_unlocked=lambda _: None, require_manual_mode=lambda: None),
                                          lifecycle=SimpleNamespace(control_bridge_lifecycle=SimpleNamespace(
                                              _read_systemd=lambda: {'available': True, 'active_state': 'inactive'})))
        self.runner = Runner()
        self.global_owner = GlobalObservationCoordinator(Catalog(self.state['pair']), agent, self.runner)
        self.runtime.global_observation = self.global_owner
        self.addCleanup(self.global_owner.close)
        self.addCleanup(self.runner.release.set)
        self.owners = {'busy_components': ['fastlio_observation'], 'unknown_components': []}
        patcher = patch('robot_dashboard.application.navigation_initialization_proposal.ownership_readback',
                        side_effect=lambda _: copy.deepcopy(self.owners))
        patcher.start(); self.addCleanup(patcher.stop)
        self.coordinator = NavigationInitializationProposals(self.runtime)
        self.generation = self.state['pair']['generation']
        self.session_id = self.session_state['session_id']

    def complete(self, started):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            job = self.global_owner.job(started['proposal_id'])
            if not job['worker_active']:
                return job
            time.sleep(.005)
        self.fail('global job did not finish')

    def test_actual_global_coordinator_produces_calibrated_information_only_candidate(self):
        before = copy.deepcopy(self.state)
        started = self.coordinator.start('bootstrap-1', self.generation, self.session_id)
        self.assertEqual(started['operational_application'], 'NOT_RUN')
        self.assertIsNone(started['imu_hypothesis'])
        self.assertIsNone(started['navigation_geometry_candidate'])
        job = self.complete(started)
        self.assertEqual(job['state'], 'succeeded', job)
        result = self.coordinator.get(started['proposal_id'])
        self.assertEqual(result['state'], 'ready', result)
        self.assertEqual(result['imu_hypothesis']['pose_reference'], 'FASTLIO_IMU')
        self.assertEqual(result['imu_hypothesis']['units'], 'metres_degrees')
        self.assertEqual(result['body_candidate']['units'], 'metres_radians')
        self.assertEqual(result['body_candidate']['frame'], self.state['pair']['localization_3d']['frame'])
        expected = self.runner.pose @ np.array(self.state['selected']['calibration']['T_imu_base'])
        self.assertAlmostEqual(result['body_candidate']['pose']['z'], expected[2, 3])
        navigation = np.array(self.state['selected']['calibration']['T_nav_map_from_localization_map']) @ expected
        preview = result['navigation_geometry_candidate']
        self.assertEqual({k: preview[k] for k in ('frame', 'pose_reference', 'units')},
                         {'frame': 'map', 'pose_reference': 'base_link', 'units': 'metres_radians'})
        self.assertEqual(set(preview['pose']), {'z', 'roll', 'pitch'})
        self.assertAlmostEqual(preview['pose']['z'], navigation[2, 3])
        self.assertAlmostEqual(preview['pose']['roll'], math.atan2(navigation[2, 1], navigation[2, 2]))
        self.assertAlmostEqual(preview['pose']['pitch'], math.asin(-navigation[2, 0]))
        self.assertNotAlmostEqual(preview['pose']['z'], result['body_candidate']['pose']['z'])
        self.assertEqual(result['quality']['hypothesis_overlap_min'], .6)
        self.assertEqual(result['quality']['operational_initial_overlap_min'], .85)
        self.assertFalse(result['quality']['residual_selection_gate_enabled'])
        self.assertFalse(result['provenance']['source_clock_verified'])
        self.assertFalse(result['provenance']['per_message_publisher_verified'])
        self.assertGreaterEqual(result['provenance']['capture_age_s'], result['provenance']['pose_age_s'])
        self.assertEqual(result['operational_application'], 'NOT_RUN')
        self.assertIsNone(result['absolute_accuracy_m'])
        self.assertEqual(result['provenance']['capture_stamp_ns'], result['provenance']['proposal_stamp_ns'])
        self.assertEqual(before, self.state)  # No seed, source, service, TF, Nav2, goal or pose call exists on fixture.
        self.assertEqual(self.runner.calls, 1)
        duplicate = self.coordinator.start('bootstrap-1', self.generation, self.session_id)
        self.assertEqual(duplicate['proposal_id'], started['proposal_id'])
        self.assertEqual(self.runner.calls, 1)

    def test_real_catalog_pair_global_coordinator_and_nonidentity_calibration(self):
        case = bundle_fixture.OperationalNavigationBundleTests()
        case.setUp(); self.addCleanup(case.doCleanups)
        state = case.manager.select_pair(case.pair_fixture())
        self.runtime.operational_navigation = case.manager
        owner = GlobalObservationCoordinator(case.catalog, self.runtime.agent, self.runner)
        self.addCleanup(owner.close)
        self.runtime.global_observation = owner
        coordinator = NavigationInitializationProposals(self.runtime)
        started = coordinator.start('real-catalog-1', state['pair']['generation'], self.session_id)
        deadline = time.monotonic() + 2.
        while owner.job(started['proposal_id'])['worker_active'] and time.monotonic() < deadline:
            time.sleep(.005)
        with patch.object(case.manager, '_revalidate_pair', wraps=case.manager._revalidate_pair) as full, \
             patch.object(case.manager, '_calibration', wraps=case.manager._calibration) as calibration:
            result = coordinator.get(started['proposal_id'])
        self.assertEqual(full.call_count, 1)  # No second full PCD rehash for the final fence.
        self.assertEqual(calibration.call_count, 2)  # Full proof, then final small calibration proof.
        self.assertEqual(result['state'], 'ready', result)
        self.assertEqual(result['pair']['localization_3d']['sha256'], case.sha)
        self.assertEqual(result['body_candidate']['frame'], state['pair']['localization_3d']['frame'])
        self.assertEqual(result['operational_application'], 'NOT_RUN')
        self.assertIsNone(case.manager.selected['seed_geometry'])

    def test_actual_override_result_is_rejected_even_with_enabled_provider(self):
        self.runner.override = True
        started = self.coordinator.start('bootstrap-ambiguous', self.generation, self.session_id)
        self.complete(started)
        result = self.coordinator.get(started['proposal_id'])
        self.assertEqual((result['state'], result['reason']), ('rejected', 'GLOBAL_AMBIGUOUS'))
        self.assertIsNone(result['body_candidate'])
        self.assertIsNone(result['navigation_geometry_candidate'])

    def test_changed_session_pair_source_and_ownership_never_return_previous_candidate(self):
        for field in ('session', 'pair', 'source', 'busy', 'bridge'):
            with self.subTest(field=field):
                started = self.coordinator.start('bootstrap-fence-' + field, self.generation, self.session_id)
                self.complete(started)
                self.assertEqual(self.coordinator.get(started['proposal_id'])['state'], 'ready')
                original_state, original_session = copy.deepcopy(self.state), copy.deepcopy(self.session_state)
                original_pose = copy.deepcopy(self.runtime.agent.pose)
                try:
                    if field == 'session': self.session_state['session_id'] = '9'*32
                    if field == 'pair': self.state['pair']['valid'] = False
                    if field == 'source': self.runtime.agent.pose['observation']['publisher_epoch'] = '9'*32
                    if field == 'busy': self.owners['busy_components'].append('navigation')
                    if field == 'bridge': self.runtime.lifecycle.control_bridge_lifecycle._read_systemd = lambda: {'available': True, 'active_state': 'active'}
                    result = self.coordinator.get(started['proposal_id'])
                    self.assertEqual(result['state'], 'stale')
                    self.assertIsNone(result['body_candidate'])
                    self.assertIsNone(result['navigation_geometry_candidate'])
                finally:
                    self.state.clear(); self.state.update(original_state)
                    self.session_state.clear(); self.session_state.update(original_session)
                    self.runtime.agent.pose = original_pose
                    self.owners['busy_components'] = ['fastlio_observation']
                    self.runtime.lifecycle.control_bridge_lifecycle._read_systemd = lambda: {'available': True, 'active_state': 'inactive'}
                if field in ('session', 'pair', 'source'):
                    self.assertEqual(self.coordinator.get(started['proposal_id'])['state'], 'stale')
                else:
                    self.assertEqual(self.coordinator.get(started['proposal_id'])['state'], 'ready')

    def test_admission_rejects_unavailable_backend_and_wrong_or_busy_context(self):
        for field in ('session', 'pair', 'busy', 'unknown', 'bridge', 'backend'):
            with self.subTest(field=field):
                state, session = copy.deepcopy(self.state), copy.deepcopy(self.session_state)
                owners = copy.deepcopy(self.owners)
                runner_status = self.runner.status
                try:
                    if field == 'session': self.session_state['active'] = False
                    if field == 'pair': self.state['pair']['valid'] = False
                    if field == 'busy': self.owners['busy_components'].append('navigation')
                    if field == 'unknown': self.owners['unknown_components'].append('control')
                    if field == 'bridge': self.runtime.lifecycle.control_bridge_lifecycle._read_systemd = lambda: {'available': False}
                    if field == 'backend': self.runner.status = lambda: {'available': False}
                    with self.assertRaises((ProposalConflict, ProposalUnavailable)):
                        self.coordinator.start('denied-' + field, self.generation, self.session_id)
                    self.assertIsNone(self.global_owner.snapshot()['active'])
                    self.assertEqual(self.runner.calls, 0)
                finally:
                    self.state.clear(); self.state.update(state)
                    self.session_state.clear(); self.session_state.update(session)
                    self.owners = owners
                    self.runner.status = runner_status
                    self.runtime.lifecycle.control_bridge_lifecycle._read_systemd = lambda: {'available': True, 'active_state': 'inactive'}

    def test_only_this_proposal_job_may_own_global_worker_during_poll(self):
        self.runner.release.clear()
        started = self.coordinator.start('bootstrap-running', self.generation, self.session_id)
        self.assertTrue(self.runner.entered.wait(1.))
        self.owners['busy_components'].append('global_observation')
        self.owners['components'] = {'global_observation': {'active_id': started['proposal_id']}}
        self.assertEqual(self.coordinator.get(started['proposal_id'])['state'], 'running')
        self.owners['components']['global_observation']['active_id'] = '9'*24
        result = self.coordinator.get(started['proposal_id'])
        self.assertEqual((result['state'], result['reason']), ('stale', 'OWNERSHIP_BUSY_OR_UNKNOWN'))
        self.assertIsNone(result['body_candidate'])
        self.assertIsNone(result['navigation_geometry_candidate'])
        self.runner.release.set()
        self.complete(started)

    def test_exact_stamp_paired_pose_from_another_epoch_is_rejected(self):
        def wrong_epoch(_, *, provenance_mode):
            pose = copy.deepcopy(self.runtime.agent.pose)
            pose['observation']['publisher_epoch'] = '9'*32
            return pose
        self.runtime.agent.observation_pose_near = wrong_epoch
        with self.assertRaisesRegex(ProposalConflict, 'SOURCE_OR_CONTEXT_CHANGED'):
            self.coordinator.start('wrong-pose-epoch', self.generation, self.session_id)
        self.assertEqual(self.runner.calls, 0)

    def test_inflight_source_change_invalidates_result_and_does_not_send_commands(self):
        self.runner.release.clear()
        started = self.coordinator.start('bootstrap-source-transition', self.generation, self.session_id)
        self.assertTrue(self.runner.entered.wait(1.))
        self.runtime.agent.pose['observation']['publisher_epoch'] = '9'*32
        result = self.coordinator.get(started['proposal_id'])
        self.assertEqual(result['state'], 'stale')
        self.assertIsNone(result['body_candidate'])
        self.runner.release.set()
        job = self.complete(started)
        self.assertNotEqual(job['state'], 'succeeded')
        self.assertEqual(self.state['selected'], {'calibration': self.state['selected']['calibration']})

    def test_request_id_is_bound_to_exact_session_and_generation(self):
        started = self.coordinator.start('bootstrap-dedupe', self.generation, self.session_id)
        self.complete(started)
        with self.assertRaisesRegex(ProposalConflict, 'REQUEST_ID_CONTEXT_CHANGED'):
            self.coordinator.start('bootstrap-dedupe', '9'*32, self.session_id)
        self.assertEqual(self.runner.calls, 1)

    def test_changed_topic_does_not_resurrect_after_restoring_original(self):
        started = self.coordinator.start('changed-topic', self.generation, self.session_id)
        self.complete(started)
        self.assertEqual(self.coordinator.get(started['proposal_id'])['state'], 'ready')
        old = self.runtime.agent.pose['topic']
        self.runtime.agent.pose['topic'] = '/utlidar/robot_odom'
        rejected = self.coordinator.get(started['proposal_id'])
        self.assertEqual((rejected['state'], rejected['reason']), ('stale', 'SOURCE_OR_CONTEXT_CHANGED'))
        self.runtime.agent.pose['topic'] = old
        self.assertEqual(self.coordinator.get(started['proposal_id'])['state'], 'stale')

    def test_calibration_changed_after_proposal_read_is_detected_before_return(self):
        case = bundle_fixture.OperationalNavigationBundleTests()
        case.setUp(); self.addCleanup(case.doCleanups)
        state = case.manager.select_pair(case.pair_fixture())
        self.runtime.operational_navigation = case.manager
        owner = GlobalObservationCoordinator(case.catalog, self.runtime.agent, self.runner)
        self.addCleanup(owner.close)
        self.runtime.global_observation = owner
        coordinator = NavigationInitializationProposals(self.runtime)
        started = coordinator.start('calibration-race', state['pair']['generation'], self.session_id)
        deadline = time.monotonic() + 2.
        while owner.job(started['proposal_id'])['worker_active'] and time.monotonic() < deadline:
            time.sleep(.005)
        original = owner.anchor_proposal
        def change_after_anchor(identifier):
            result = original(identifier)
            case.calibration['evidence'] = 'changed after anchor result'
            case.write_calibration()
            return result
        with patch.object(owner, 'anchor_proposal', side_effect=change_after_anchor):
            result = coordinator.get(started['proposal_id'])
        self.assertEqual((result['state'], result['reason']), ('stale', 'CALIBRATION_CHANGED'))
        self.assertIsNone(result['body_candidate'])
        self.assertIsNone(result['navigation_geometry_candidate'])

    def test_navigation_map_transform_changed_after_anchor_discards_preview(self):
        started = self.coordinator.start('navigation-transform-race', self.generation, self.session_id)
        self.complete(started)
        original = self.global_owner.anchor_proposal
        def change_after_anchor(identifier):
            result = original(identifier)
            self.state['selected']['calibration']['T_nav_map_from_localization_map'][2][3] += .5
            return result
        with patch.object(self.global_owner, 'anchor_proposal', side_effect=change_after_anchor):
            result = self.coordinator.get(started['proposal_id'])
        self.assertEqual(result['state'], 'stale')
        self.assertIsNone(result['body_candidate'])
        self.assertIsNone(result['navigation_geometry_candidate'])

    def test_preview_conversion_delay_cannot_omit_original_pose_age(self):
        from robot_dashboard.application import navigation_initialization_proposal as proposals
        started = self.coordinator.start('preview-delay', self.generation, self.session_id)
        self.complete(started)
        original = proposals._navigation_map_body_pose
        def delayed(calibration, body):
            time.sleep(1.2)
            return original(calibration, body)
        with patch.object(proposals, '_navigation_map_body_pose', side_effect=delayed):
            result = self.coordinator.get(started['proposal_id'])
        self.assertEqual(result['state'], 'stale')
        self.assertIsNone(result['navigation_geometry_candidate'])
        self.assertIsNone(result['body_candidate'])

    def test_map_transform_changed_during_preview_conversion_discards_candidate(self):
        from robot_dashboard.application import navigation_initialization_proposal as proposals
        started = self.coordinator.start('preview-transform-change', self.generation, self.session_id)
        self.complete(started)
        original = proposals._navigation_map_body_pose
        def changed(calibration, body):
            pose = original(calibration, body)
            self.state['selected']['calibration']['T_nav_map_from_localization_map'][2][3] += .5
            return pose
        with patch.object(proposals, '_navigation_map_body_pose', side_effect=changed):
            result = self.coordinator.get(started['proposal_id'])
        self.assertEqual(result['state'], 'stale')
        self.assertIsNone(result['navigation_geometry_candidate'])
        self.assertIsNone(result['body_candidate'])

    def test_session_stop_cancels_owned_job_without_any_http_poll_and_tracks_cleanup(self):
        self.runner.release.clear()
        started = self.coordinator.start('abandoned-job', self.generation, self.session_id)
        self.assertTrue(self.runner.entered.wait(1.))
        self.session_state.update(state='STOPPED', active=False)
        deadline = time.monotonic() + 2.
        while time.monotonic() < deadline:
            job = self.global_owner.job(started['proposal_id'])
            if job['cancellation_requested']:
                break
            time.sleep(.02)
        self.assertTrue(job['cancellation_requested'], job)
        self.assertEqual(job['state'], 'cancelled')
        result = self.coordinator.get(started['proposal_id'])
        self.assertEqual(result['state'], 'stale')
        self.assertIn(result['cleanup']['state'], ('CANCELLING', 'CANCEL_PENDING', 'SETTLED'))
        self.runner.release.set()
        deadline = time.monotonic() + 2.
        while time.monotonic() < deadline:
            result = self.coordinator.get(started['proposal_id'])
            if result['cleanup']['state'] == 'SETTLED':
                break
            time.sleep(.02)
        self.assertEqual(result['cleanup']['state'], 'SETTLED')
        self.assertFalse(result['cleanup']['worker_active'])

    def test_unsettled_cancellation_reports_pending_then_actual_settlement(self):
        self.runner.release.clear()
        started = self.coordinator.start('slow-cleanup', self.generation, self.session_id)
        self.assertTrue(self.runner.entered.wait(1.))
        self.session_state.update(state='STOPPED', active=False)
        deadline = time.monotonic() + 4.5
        while time.monotonic() < deadline:
            result = self.coordinator.get(started['proposal_id'])
            if result['cleanup']['state'] == 'CANCEL_PENDING':
                break
            time.sleep(.05)
        self.assertEqual(result['cleanup']['state'], 'CANCEL_PENDING')
        self.assertTrue(result['cleanup']['worker_active'])
        self.assertTrue(result['cleanup']['cancellation_requested'])
        self.runner.release.set()
        deadline = time.monotonic() + 2.
        while time.monotonic() < deadline:
            result = self.coordinator.get(started['proposal_id'])
            if result['cleanup']['state'] == 'SETTLED':
                break
            time.sleep(.02)
        self.assertEqual(result['cleanup']['state'], 'SETTLED')
        self.assertFalse(result['cleanup']['worker_active'])

    def test_client_request_id_cannot_adopt_or_cancel_another_global_job(self):
        loc = self.state['pair']['localization_3d']
        old = self.global_owner.start('shared-client-id', loc['map_id'], loc['revision'],
                                      input_kind='fastlio_imu', provenance_mode='subscription_observation')
        self.complete({'proposal_id': old['job_id']})
        self.runner.release.clear()
        self.runner.entered.clear()
        new = self.coordinator.start('shared-client-id', self.generation, self.session_id)
        self.assertNotEqual(new['proposal_id'], old['job_id'])
        self.assertTrue(self.runner.entered.wait(1.))
        self.session_state.update(state='STOPPED', active=False)
        deadline = time.monotonic() + 2.
        while time.monotonic() < deadline:
            new_job = self.global_owner.job(new['proposal_id'])
            if new_job['cancellation_requested']:
                break
            time.sleep(.02)
        self.assertTrue(new_job['cancellation_requested'])
        old_job = self.global_owner.job(old['job_id'])
        self.assertEqual(old_job['state'], 'succeeded')
        self.assertFalse(old_job['cancellation_requested'])
        self.runner.release.set()

    def test_captured_pose_receipt_must_be_within_current_observation_session(self):
        started = self.coordinator.start('old-pose-receipt', self.generation, self.session_id)
        self.complete(started)
        with self.global_owner._lock:
            job = self.global_owner._jobs[started['proposal_id']]
            job['captured_context']['anchor_capture']['provenance']['pose_received_monotonic_s'] = self.session_state['started_monotonic_s'] - 1.
        result = self.coordinator.get(started['proposal_id'])
        self.assertEqual((result['state'], result['reason']), ('stale', 'SOURCE_OR_CONTEXT_CHANGED'))
        self.assertIsNone(result['body_candidate'])

    def test_asgi_post_and_get_are_explicit_origin_guarded_and_no_store(self):
        app = FastAPI(); app.state.runtime = self.runtime; app.include_router(router)
        self.runtime._navigation_initialization_proposals = self.coordinator
        client = LocalASGIClient(app)
        url = '/api/v1/navigation/operational-3d/initialization-proposals'
        body = {'request_id': 'bootstrap-api', 'bundle_generation': self.generation,
                'observation_session_id': self.session_id}
        async def inline_thread(func, *args): return func(*args)
        with patch('robot_dashboard.api.routers.operational_navigation.asyncio.to_thread', inline_thread):
            self.assertEqual(client.post(url, body, headers={'origin': 'http://evil.invalid'}).status_code, 403)
            self.assertEqual(client.post(url, {**body, 'z': 0.}).status_code, 422)
            response = client.post(url, body)
            self.assertEqual(response.status_code, 202, response.text)
            self.complete(response.json())
            response = client.get(url + '/' + response.json()['proposal_id'])
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['state'], 'ready', response.text)
            self.assertEqual(response.json()['navigation_geometry_candidate']['frame'], 'map')
            path = url + '/' + response.json()['proposal_id']
            async def inspect_headers():
                messages = []
                async def receive(): return {'type': 'http.request', 'body': b'', 'more_body': False}
                async def send(message): messages.append(message)
                scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                         'method': 'GET', 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
                         'query_string': b'', 'root_path': '', 'headers': [(b'host', b'testserver')],
                         'server': ('testserver', 80), 'client': ('test', 1)}
                await app(scope, receive, send)
                return messages[0]['headers']
            self.assertIn((b'cache-control', b'no-store'), asyncio.run(inspect_headers()))


if __name__ == '__main__':
    unittest.main()
