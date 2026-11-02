"""Independent synthetic contract checks; no robot, ROS, or real sensor input."""
from __future__ import annotations

import copy
import time
import unittest
from unittest.mock import patch

import test_navigation_initialization_proposal as proposal_fixture
import test_operational_navigation_bundle as bundle_fixture
from robot_dashboard.application.global_observation import GlobalObservationCoordinator
from robot_dashboard.application.navigation_initialization_proposal import (
    NavigationInitializationProposals,
    ProposalNotFound,
)


class InitializationProposalBoundaryTests(unittest.TestCase):
    def setUp(self):
        # Reuse the sensor/session and ownership fixture but exercise the real
        # OperationalNavigation and SavedMapCatalog with synthetic files.
        self.base = proposal_fixture.ProposalTests(
            'test_real_catalog_pair_global_coordinator_and_nonidentity_calibration'
        )
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.bundle = bundle_fixture.OperationalNavigationBundleTests(
            'test_pair_geometry_explicit_and_one_execution_only_with_reconfirm_and_legacy_restore'
        )
        self.bundle.setUp()
        self.addCleanup(self.bundle.doCleanups)
        self.state = self.bundle.manager.select_pair(self.bundle.pair_fixture())
        self.base.runtime.operational_navigation = self.bundle.manager
        self.owner = GlobalObservationCoordinator(
            self.bundle.catalog, self.base.runtime.agent, self.base.runner
        )
        self.addCleanup(self.owner.close)
        self.addCleanup(self.base.runner.release.set)
        self.base.runtime.global_observation = self.owner
        self.proposals = NavigationInitializationProposals(self.base.runtime)
        self.generation = self.state['pair']['generation']
        self.session_id = self.base.session_id

    def wait_until(self, predicate, message, timeout=1.5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.01)
        self.fail(message)

    def completed_proposal(self, request_id):
        started = self.proposals.start(request_id, self.generation, self.session_id)
        job_id = started['proposal_id']
        self.wait_until(lambda: not self.owner.job(job_id)['worker_active'], 'job did not settle')
        self.assertEqual(self.owner.job(job_id)['state'], 'succeeded')
        return job_id

    def test_source_change_then_restore_does_not_revive_a_candidate(self):
        job_id = self.completed_proposal('independent-source-fence')
        self.assertEqual(self.proposals.get(job_id)['state'], 'ready')
        self.base.runtime.agent.pose['topic'] = '/utlidar/robot_odom'
        invalid = self.proposals.get(job_id)
        self.assertEqual(invalid['state'], 'stale')
        self.assertIsNone(invalid['body_candidate'])
        self.base.runtime.agent.pose['topic'] = '/Odometry'
        restored = self.proposals.get(job_id)
        self.assertEqual(restored['state'], 'stale')
        self.assertIsNone(restored['body_candidate'])

    def test_calibration_change_before_return_rejects_the_candidate(self):
        job_id = self.completed_proposal('independent-calibration-fence')
        original = self.owner.anchor_proposal

        def change_after_asset_validation(identifier):
            value = original(identifier)
            self.bundle.calibration['evidence'] = 'changed during synthetic request'
            self.bundle.write_calibration()
            return value

        with patch.object(self.owner, 'anchor_proposal', side_effect=change_after_asset_validation):
            result = self.proposals.get(job_id)
        self.assertFalse(self.bundle.manager.status()['pair']['valid'])
        self.assertNotEqual(result['state'], 'ready')
        self.assertIsNone(result['body_candidate'])

    def test_external_request_id_collision_cannot_adopt_existing_job(self):
        pin = self.state['pair']['localization_3d']
        external = self.owner.start('independent-collision', pin['map_id'], pin['revision'],
                                    input_kind='fastlio_imu', provenance_mode='subscription_observation',
                                    search_mode='global')
        external_id = external['job_id']
        self.wait_until(lambda: not self.owner.job(external_id)['worker_active'], 'external job did not finish')
        self.assertEqual(self.owner.job(external_id)['state'], 'succeeded')
        result = self.proposals.start('independent-collision', self.generation, self.session_id)
        self.assertNotEqual(result['proposal_id'], external_id)
        self.assertFalse(self.owner.job(external_id)['cancellation_requested'])

    def test_stopped_session_cancels_and_settles_only_its_job_without_polling(self):
        self.base.runner.release.clear()
        started = self.proposals.start('independent-stop', self.generation, self.session_id)
        own_id = started['proposal_id']
        self.assertTrue(self.base.runner.entered.wait(1.0))
        # Simulate the session's public snapshot transitioning to stopped. The
        # browser does not poll the proposal after the transition.
        self.base.session_state.update(state='STOPPED', active=False, session_id=None)
        self.wait_until(lambda: self.owner.job(own_id)['cancellation_requested'],
                        'own in-flight job was not cancelled after session stop')
        # The synthetic runner waits on this event instead of honouring the
        # cancellation event, so release it and verify the public worker state.
        self.base.runner.release.set()
        self.wait_until(lambda: not self.owner.job(own_id)['worker_active'],
                        'own worker did not settle after cancellation')
        self.assertNotEqual(self.owner.job(own_id)['state'], 'succeeded')

        # A later global job belongs to another feature. The old session's
        # cleanup must never follow the active slot and cancel that new owner.
        self.base.runner.entered.clear()
        self.base.runner.release.clear()
        pin = self.state['pair']['localization_3d']
        external = self.owner.start('external-after-cleanup', pin['map_id'], pin['revision'],
                                    input_kind='fastlio_imu', provenance_mode='subscription_observation',
                                    search_mode='global')
        external_id = external['job_id']
        self.assertTrue(self.base.runner.entered.wait(1.0))
        self.base.runner.release.wait(.25)
        external_status = self.owner.job(external_id)
        self.assertTrue(external_status['worker_active'])
        self.assertFalse(external_status['cancellation_requested'])

    def test_adapter_cannot_cancel_an_unowned_global_job(self):
        self.base.runner.release.clear()
        pin = self.state['pair']['localization_3d']
        external = self.owner.start('external-inflight', pin['map_id'], pin['revision'],
                                    input_kind='fastlio_imu', provenance_mode='subscription_observation',
                                    search_mode='global')
        external_id = external['job_id']
        self.assertTrue(self.base.runner.entered.wait(1.0))
        self.base.session_state.update(state='STOPPED', active=False, session_id=None)
        with self.assertRaises(ProposalNotFound):
            self.proposals.get(external_id)
        job = self.owner.job(external_id)
        self.assertTrue(job['worker_active'])
        self.assertFalse(job['cancellation_requested'])

    def test_exact_stamp_pose_received_before_session_start_is_rejected(self):
        job_id = self.completed_proposal('independent-pose-boundary')
        original_job = self.owner.job
        start = self.base.session_state['started_monotonic_s']

        def with_prior_session_pose(identifier):
            job = original_job(identifier)
            context = job.get('captured_context')
            if identifier == job_id and context:
                # Model an exact-stamp pose received 1ms before the new session;
                # the paired cloud remains after start and within the 150ms
                # receipt window. This is synthetic provenance, never field data.
                pose_receipt = start - .001
                cloud_receipt = context['scan']['received_monotonic_s']
                self.assertGreaterEqual(cloud_receipt, start)
                self.assertLessEqual(abs(cloud_receipt - pose_receipt), .15)
                context['anchor_capture']['provenance']['pose_received_monotonic_s'] = pose_receipt
                if job.get('result'):
                    job['result']['captured_context'] = copy.deepcopy(context)
            return job

        with patch.object(self.owner, 'job', side_effect=with_prior_session_pose):
            result = self.proposals.get(job_id)
        self.assertNotEqual(result['state'], 'ready')
        self.assertIsNone(result['body_candidate'])


if __name__ == '__main__':
    unittest.main()
