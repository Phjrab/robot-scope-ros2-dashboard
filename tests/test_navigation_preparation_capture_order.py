"""Independent capture-order tests using synthetic, explicitly published samples.

No ROS, hardware, external service, raw field data, or elapsed-time reset is used.
The production capture/quality limits remain in force. The controlled clock only
advances; creating a new sample is a separate explicit provider operation.
"""
import copy
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from robot_dashboard.application import navigation_preparation_inputs as preparation
from test_navigation_preparation_inputs import active_health, fixture


class Clock:
    def __init__(self, start):
        self.value = start

    def monotonic(self):
        return self.value

    def monotonic_ns(self):
        return int(self.value * 1_000_000_000)

    def advance(self, seconds):
        assert seconds >= 0
        self.value += seconds


class CaptureOrderTests(unittest.TestCase):
    def setUp(self):
        self.manager, self.session, self.agent, self.state, self.session_state = fixture()
        self.clock = Clock(self.agent.cloud['observation']['received_monotonic_s'])
        self.original_cloud = copy.deepcopy(self.agent.cloud)
        self.original_pose = copy.deepcopy(self.agent.pose)
        self.manager.preparation_snapshot = lambda: copy.deepcopy(self.state)
        self.manager.status = lambda: copy.deepcopy(self.state)
        self.patch_time = patch.object(preparation, 'time', self.clock)
        self.patch_time.start()
        self.addCleanup(self.patch_time.stop)

    def publish(self, stamp='12346', *, receipt=None, position_x=9.):
        """Publish genuinely new objects; never retime the old sample."""
        when = self.clock.monotonic() if receipt is None else receipt
        for attr, original in (('cloud', self.original_cloud), ('pose', self.original_pose)):
            sample = copy.deepcopy(original)
            sample['seq'] += 1
            sample['observation']['source_stamp_ns'] = str(stamp)
            sample['observation']['received_monotonic_s'] = when
            sample['observation']['subscription_evidence']['graph']['observed_monotonic_s'] = when
            if attr == 'pose':
                sample['position']['x'] = position_x
            setattr(self.agent, attr, sample)

    def collect(self):
        result = preparation.preparation_inputs(self.manager, self.session, self.agent)
        # The real old objects must retain their original provenance.
        self.assertEqual(self.original_cloud['observation']['source_stamp_ns'], '12345')
        self.assertEqual(self.original_pose['observation']['source_stamp_ns'], '12345')
        self.assertEqual(self.original_cloud['observation']['received_monotonic_s'],
                         self.original_pose['observation']['received_monotonic_s'])
        return result

    def assert_rejected(self, result):
        self.assertFalse(result['evidence']['valid'])
        self.assertIsNone(result['reference_pose'])
        self.assertIsNone(result['evidence']['cloud'])
        self.assertIsNone(result['evidence']['pose'])
        self.assertTrue(all(not item['available'] for item in result['candidates'].values()))

    def assert_new_pair(self, result):
        self.assertTrue(result['evidence']['valid'], result['evidence'])
        for name in ('cloud', 'pose'):
            self.assertEqual(result['evidence'][name]['source_stamp_ns'], '12346')
        self.assertEqual(result['reference_pose']['source_stamp_ns'], '12346')
        self.assertAlmostEqual(result['reference_pose']['position']['x'], 9.)
        self.assertNotIn('points_bytes', json.dumps(result))

    def test_new_exact_pair_after_slow_map_validation_is_used(self):
        def slow_status():
            self.clock.advance(1.12)
            self.publish()
            return copy.deepcopy(self.state)
        self.manager.status = slow_status
        self.assert_new_pair(self.collect())
        self.assertGreater(self.clock.monotonic() -
                           self.original_cloud['observation']['received_monotonic_s'], 1.)

    def test_new_exact_pair_after_slow_health_is_used(self):
        def slow_health(_):
            self.clock.advance(1.12)
            self.publish()
            return {}
        self.agent._navigation_runtime_health_snapshot = slow_health
        self.assert_new_pair(self.collect())
        self.assertGreater(self.clock.monotonic() -
                           self.original_cloud['observation']['received_monotonic_s'], 1.)

    def test_old_pair_is_not_retimed_when_no_new_sample_is_available(self):
        def slow_status():
            self.clock.advance(1.12)
            return copy.deepcopy(self.state)
        self.manager.status = slow_status
        result = self.collect()
        self.assert_rejected(result)
        self.assertEqual(result['evidence']['reason'], 'OBSERVATION_STALE_OR_SOURCE_INVALID')
        self.assertEqual(self.agent.cloud, self.original_cloud)
        self.assertEqual(self.agent.pose, self.original_pose)

    def test_fresh_pair_expires_after_late_health_work_without_another_sample(self):
        def status_with_new_data():
            self.clock.advance(.2)
            self.publish()
            return copy.deepcopy(self.state)
        def slow_health(_):
            self.clock.advance(1.12)
            return {}
        self.manager.status = status_with_new_data
        self.agent._navigation_runtime_health_snapshot = slow_health
        self.assert_rejected(self.collect())
        self.assertGreater(self.clock.monotonic() - self.agent.cloud['observation']['received_monotonic_s'], 1.)

    def test_intermediate_failure_preserves_the_sample_that_expired_during_health(self):
        def slow_health(_):
            self.clock.advance(1.12)
            return {}
        self.agent._navigation_runtime_health_snapshot = slow_health
        result = self.collect()
        self.assert_rejected(result)
        diagnostics = result['evidence']['diagnostics']
        self.assertEqual(diagnostics['failure_stage'], 'context_fence')
        sample = diagnostics['failure_sample']
        self.assertIsNotNone(sample)
        for name in ('pose', 'cloud'):
            self.assertEqual(sample[name]['source_stamp_ns'], '12345')
            self.assertAlmostEqual(sample[name]['receipt_age_s'], 1.12)
            self.assertAlmostEqual(diagnostics['checks'][0][name]['receipt_age_s'], 0.)

    def test_intermediate_pose_read_failure_preserves_only_the_captured_cloud(self):
        original_pose_snapshot = self.agent.pose_snapshot
        calls = 0
        def pose_snapshot():
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError('synthetic pose snapshot unavailable')
            return original_pose_snapshot()
        self.agent.pose_snapshot = pose_snapshot
        result = self.collect()
        self.assert_rejected(result)
        diagnostics = result['evidence']['diagnostics']
        self.assertEqual(diagnostics['failure_stage'], 'context_fence')
        sample = diagnostics['failure_sample']
        self.assertIsNotNone(sample)
        self.assertEqual(sample['cloud']['source_stamp_ns'], '12345')
        self.assertTrue(all(value is None for value in sample['pose'].values()))

    def test_slow_handoff_status_is_inside_the_final_freshness_boundary(self):
        self.state['initialization_handoff'] = {'state': 'SNAPSHOTTED'}
        self.state['selected']['seed_geometry'] = {
            'source': 'proposal_confirmed', 'handoff': {'handoff_id': 'a' * 32}}
        self.agent.health = active_health(self.state['pair'])
        calls = []
        def slow_handoff(*_args, **_kwargs):
            calls.append(True)
            self.clock.advance(1.12)
            return {'state': 'SNAPSHOTTED'}
        self.manager.handoff_status = slow_handoff
        result = self.collect()
        self.assertTrue(calls, 'the slow handoff path must actually execute')
        self.assertGreater(self.clock.monotonic() - self.agent.cloud['observation']['received_monotonic_s'], 1.)
        self.assert_rejected(result)

    def test_selected_map_and_session_changes_during_validation_are_rejected(self):
        for index, field in enumerate(('generation', 'map_revision', 'calibration_sha', 'calibration_content',
                                       'session_id', 'session_started', 'session_state')):
            with self.subTest(field=field):
                if index:
                    self.setUp()
                def changed_status():
                    self.clock.advance(.1)
                    changed = copy.deepcopy(self.state)
                    if field == 'generation': changed['pair']['generation'] = '9' * 32
                    if field == 'map_revision': changed['pair']['localization_3d']['revision'] = '8' * 64
                    if field == 'calibration_sha': changed['pair']['calibration_sha256'] = '7' * 64
                    if field == 'calibration_content': changed['selected']['calibration']['T_imu_base'][2][3] = .8
                    if field == 'session_id': self.session_state['session_id'] = '6' * 32
                    if field == 'session_started': self.session_state['started_monotonic_s'] += .01
                    if field == 'session_state': self.session_state['state'] = 'STOPPED'; self.session_state['active'] = False
                    self.publish()
                    return changed
                self.manager.status = changed_status
                self.assert_rejected(self.collect())
                self.doCleanups()

    def test_changed_source_identity_or_graph_is_not_adopted_as_same_context(self):
        for index, field in enumerate(('topic', 'observer_id', 'publisher_epoch', 'subscription_session', 'graph_fingerprint')):
            with self.subTest(field=field):
                if index:
                    self.setUp()
                def changed_status():
                    self.clock.advance(.1)
                    self.publish()
                    cloud = self.agent.cloud
                    obs = cloud['observation']
                    if field == 'topic': cloud['topic'] = '/other_cloud'
                    if field == 'observer_id': obs['observer_id'] = '9' * 32
                    if field == 'publisher_epoch': obs['publisher_epoch'] = '9' * 32
                    if field == 'subscription_session': obs['subscription_evidence']['session_id'] = '9' * 32
                    if field == 'graph_fingerprint': obs['subscription_evidence']['graph']['fingerprint'] = '9' * 64
                    return copy.deepcopy(self.state)
                self.manager.status = changed_status
                self.assert_rejected(self.collect())
                self.doCleanups()

    def test_observed_epoch_change_is_not_revived_after_provider_restores(self):
        triggered = False
        seen_transition = []
        original_cloud_snapshot = self.agent.pointcloud_binary_snapshot
        def after_validation():
            nonlocal triggered
            self.clock.advance(.1)
            self.publish()
            triggered = True
            return copy.deepcopy(self.state)
        def cloud_snapshot():
            nonlocal triggered
            sample = original_cloud_snapshot()
            if triggered:
                triggered = False
                sample['observation']['publisher_epoch'] = '9' * 32
                seen_transition.append(True)
            return sample
        self.manager.status = after_validation
        self.agent.pointcloud_binary_snapshot = cloud_snapshot
        result = self.collect()
        self.assertTrue(seen_transition, 'a mismatched epoch must actually be observed')
        self.assertEqual(self.agent.cloud['observation']['publisher_epoch'],
                         self.original_cloud['observation']['publisher_epoch'])
        self.assert_rejected(result)

    def test_observed_session_change_is_not_revived_after_snapshot_restores(self):
        triggered = False
        seen_transition = []
        def after_validation():
            nonlocal triggered
            self.clock.advance(.1)
            self.publish()
            triggered = True
            return copy.deepcopy(self.state)
        def snapshot():
            nonlocal triggered
            value = copy.deepcopy(self.session_state)
            if triggered:
                triggered = False
                value['session_id'] = '9' * 32
                seen_transition.append(True)
            return value
        self.manager.status = after_validation
        self.session.snapshot = snapshot
        result = self.collect()
        self.assertTrue(seen_transition, 'a mismatched session must actually be observed')
        self.assertEqual(self.session_state['session_id'], '2' * 32)
        self.assert_rejected(result)

    def test_job_change_at_health_fence_discards_the_reference(self):
        first = self.manager.preparation_execution()
        count = 0
        def changing_job():
            nonlocal count
            count += 1
            return copy.deepcopy(first if count == 1 else {**first, 'job_id': '8' * 32})
        self.manager.preparation_execution = changing_job
        result = self.collect()
        self.assertGreaterEqual(count, 2, 'the job change must actually be observed')
        self.assert_rejected(result)
        self.assertIsNone(result['operational_state'])
        self.assertEqual(result['operational_state_error'], 'CONTEXT_CHANGED')

    def test_calibration_or_selection_fence_delay_does_not_extend_sample_age(self):
        calls = 0
        def final_selection():
            nonlocal calls
            calls += 1
            if calls == 2:
                self.clock.advance(1.12)
            return copy.deepcopy(self.state)
        self.manager.preparation_snapshot = final_selection
        result = self.collect()
        self.assertGreaterEqual(calls, 2, 'the delayed fence must actually execute')
        self.assertGreater(self.clock.monotonic() - self.agent.cloud['observation']['received_monotonic_s'], 1.)
        self.assert_rejected(result)

    def test_exact_stamp_does_not_bypass_the_150ms_receipt_pair_limit(self):
        def delayed_pair():
            self.clock.advance(.25)
            self.publish()
            # Same ROS stamp, individually fresh and post-start, but receipts
            # differ by more than the existing 150 ms exact-pair window.
            self.agent.pose['observation']['received_monotonic_s'] -= .151
            return copy.deepcopy(self.state)
        self.manager.status = delayed_pair
        result = self.collect()
        self.assertEqual(self.agent.cloud['observation']['source_stamp_ns'],
                         self.agent.pose['observation']['source_stamp_ns'])
        self.assertGreater(self.agent.cloud['observation']['received_monotonic_s'] -
                           self.agent.pose['observation']['received_monotonic_s'], .15)
        self.assert_rejected(result)

    def diagnostics(self, result):
        diagnostic = result['evidence']['diagnostics']
        self.assertEqual(diagnostic['schema'], 'robot-scope.preparation-diagnostics.v1')
        self.assertLessEqual(len(diagnostic['checks']), 5)
        self.assertNotIn('points_bytes', json.dumps(diagnostic))
        self.assertNotIn('position', json.dumps(diagnostic))
        self.assertNotIn('orientation', json.dumps(diagnostic))
        self.assertIn('failure_sample', diagnostic)
        for check in diagnostic['checks']:
            for item in ('pose', 'cloud'):
                for field in ('state', 'units', 'sent_points', 'subscription_session_id',
                              'graph_fingerprint', 'receipt_after_session_start'):
                    self.assertIn(field, check[item])
        for phase in ('initial_snapshot', 'initial_capture', 'pair_validation',
                      'health_and_handoff', 'final_capture', 'calibration_fence',
                      'response_fence', 'total'):
            self.assertIn(phase, diagnostic['phase_ms'])
            value = diagnostic['phase_ms'][phase]
            self.assertTrue(value is None or (type(value) in (int, float) and value >= 0), phase)
        return diagnostic

    def test_diagnostics_bind_initial_and_final_stamps_and_real_phase_time(self):
        def slow_status():
            self.clock.advance(1.12)
            self.publish()
            return copy.deepcopy(self.state)
        self.manager.status = slow_status
        result = self.collect()
        self.assert_new_pair(result)
        d = self.diagnostics(result)
        self.assertIsNone(d['failure_stage'])
        self.assertIsNone(d['failure_code'])
        by_stage = {item['stage']: item for item in d['checks']}
        self.assertEqual(by_stage['initial_latest']['sample'], 'initial')
        self.assertEqual(by_stage['initial_latest']['cloud']['source_stamp_ns'], '12345')
        self.assertAlmostEqual(by_stage['initial_latest']['cloud']['receipt_age_s'], 0., delta=.001)
        self.assertEqual(by_stage['final_latest']['sample'], 'final')
        self.assertEqual(by_stage['final_latest']['cloud']['source_stamp_ns'], '12346')
        self.assertAlmostEqual(by_stage['final_latest']['cloud']['receipt_age_s'], 0., delta=.001)
        self.assertGreaterEqual(d['phase_ms']['pair_validation'], 1120.)
        self.assertGreaterEqual(d['phase_ms']['total'], 1120.)

    def test_missing_receipt_metadata_is_null_and_reports_actual_rejection(self):
        self.agent.pose['observation']['received_monotonic_s'] = None
        result = self.collect()
        self.assert_rejected(result)
        d = self.diagnostics(result)
        self.assertEqual(d['failure_stage'], 'initial_latest')
        self.assertEqual(d['failure_code'], 'OBSERVATION_STALE_OR_SOURCE_INVALID')
        check = next(c for c in d['checks'] if c['stage'] == 'initial_latest')
        self.assertFalse(check['ready'])
        self.assertIn('POSE_RECEIPT', check['failures'])
        self.assertIsNone(check['pose']['receipt_age_s'])
        self.assertEqual(d['failure_sample'], {'stage': 'initial_latest',
                         'pose': check['pose'], 'cloud': check['cloud']})
        self.assertIsNone(d['phase_ms']['final_capture'])

    def test_graph_age_uses_the_failed_check_time_and_does_not_fake_freshness(self):
        self.agent.cloud['observation']['subscription_evidence']['graph']['observed_monotonic_s'] -= 3.25
        result = self.collect()
        self.assert_rejected(result)
        d = self.diagnostics(result)
        check = next(c for c in d['checks'] if c['stage'] == 'initial_latest')
        self.assertFalse(check['ready'])
        self.assertIn('CLOUD_GRAPH', check['failures'])
        self.assertAlmostEqual(check['cloud']['graph_age_s'], 3.25, delta=.001)
        self.assertAlmostEqual(check['cloud']['receipt_age_s'], 0., delta=.001)

    def test_future_receipt_keeps_negative_age_and_fails(self):
        self.agent.pose['observation']['received_monotonic_s'] += .25
        result = self.collect()
        self.assert_rejected(result)
        check = next(c for c in self.diagnostics(result)['checks'] if c['stage'] == 'initial_latest')
        self.assertFalse(check['ready'])
        self.assertIn('POSE_RECEIPT', check['failures'])
        self.assertAlmostEqual(check['pose']['receipt_age_s'], -.25, delta=.001)

    def test_first_diagnostic_failure_survives_a_later_context_change(self):
        self.agent.pose['topic'] = '/wrong_source'
        def changed_status():
            changed = copy.deepcopy(self.state)
            changed['pair']['generation'] = '9' * 32
            return changed
        self.manager.status = changed_status
        result = self.collect()
        self.assert_rejected(result)
        self.assertEqual(result['evidence']['reason'], 'CONTEXT_CHANGED')
        d = self.diagnostics(result)
        self.assertEqual(d['failure_stage'], 'initial_latest')
        self.assertEqual(d['failure_code'], 'OBSERVATION_STALE_OR_SOURCE_INVALID')
        check = next(c for c in d['checks'] if c['stage'] == 'initial_latest')
        self.assertIn('POSE_TOPIC', check['failures'])
        self.assertEqual(check['pose']['topic'], '/wrong_source')

    def test_no_observation_leaves_unexecuted_sensor_phases_null(self):
        self.session_state.update(active=False, state='STOPPED')
        result = self.collect()
        self.assert_rejected(result)
        d = self.diagnostics(result)
        self.assertEqual(d['failure_stage'], 'session')
        self.assertEqual(d['failure_code'], 'OBSERVATION_INACTIVE')
        self.assertEqual(d['checks'], [])
        self.assertIsNone(d['phase_ms']['initial_capture'])
        self.assertIsNone(d['phase_ms']['final_capture'])

    def test_backward_stamp_or_unpaired_pose_is_not_accepted(self):
        for index, case in enumerate(('backward', 'unpaired')):
            with self.subTest(case=case):
                if index:
                    self.setUp()
                def changed_status():
                    self.clock.advance(.1)
                    self.publish(stamp='12344' if case == 'backward' else '12346')
                    if case == 'unpaired':
                        self.agent.pose['observation']['source_stamp_ns'] = '12347'
                        self.agent.observation_pose_near = lambda *_args, **_kwargs: None
                    return copy.deepcopy(self.state)
                self.manager.status = changed_status
                self.assert_rejected(self.collect())
                self.doCleanups()


if __name__ == '__main__':
    unittest.main()
