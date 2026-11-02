"""Robot-free regression exposing first-start preparation dependencies.

These tests document current behavior; they do not authorize a pose or motion.
"""
import copy
import unittest

import numpy as np

from robot_dashboard.application.anchor_proposal import proposal_from_job
from robot_dashboard.application.global_observation import GlobalObservationCoordinator
from robot_dashboard.application.navigation_preparation_inputs import preparation_inputs
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy
from robot_dashboard.relocalization.external_global_observation import ExternalGlobalObservationRunner
from robot_dashboard.relocalization.global_observation_jobs import (
    GlobalObservationConflict, GlobalObservationUnavailable, GlobalObservationValidationError,
)
from robot_dashboard.relocalization.seeded_initialization import validate_seed

import test_anchor_proposal as anchor_fixture
import test_navigation_preparation_inputs as preparation_fixture
import test_operational_navigation_bundle as bundle_fixture
import test_operational_3d_localization as operational_fixture


class FirstStartDependencyTests(unittest.TestCase):
    def test_fresh_observation_pair_does_not_unblock_first_navigation_start(self):
        case = bundle_fixture.OperationalNavigationBundleTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        selected = case.manager.select_pair(case.pair_fixture())
        _, session, agent, _, _ = preparation_fixture.fixture()
        view = preparation_inputs(case.manager, session, agent)
        self.assertTrue(view['pair']['valid'])
        self.assertEqual(view['pair']['generation'], selected['pair']['generation'])
        self.assertTrue(view['evidence']['valid'])
        self.assertEqual(view['reference_pose']['frame'], 'camera_init')
        self.assertTrue(all(item['value'] is None and not item['available']
                            for item in view['candidates'].values()))
        self.assertEqual(view['map_estimate_reason'], 'NAVIGATION_JOB_NOT_RUNNING')
        self.assertIsNone(selected['selected']['seed_geometry'])
        self.assertIsNone(case.manager.preparation_execution())
        with self.assertRaisesRegex(ValueError, 'INITIAL_HEIGHT_TILT_REQUIRED'):
            case.manager.preflight(case.navigation['id'], case.navigation['revision'])

    def test_xy_yaw_alone_is_not_a_valid_existing_local_search_seed(self):
        incomplete = {'revision': 1, 'pose': {'x': 2., 'y': 3., 'yaw': 15.},
                      'pose_reference': 'FASTLIO_IMU', 'units': 'metres_degrees',
                      'map_frame': 'camera_init', 'height_source': 'manual',
                      'bounds': {'xy_m': 1., 'yaw_deg': 30., 'z_m': .5, 'tilt_deg': 10.},
                      'source_contract': {}}
        with self.assertRaisesRegex(GlobalObservationValidationError, 'INVALID_LOCAL_SEED'):
            validate_seed(incomplete)
        for axis in ('z', 'roll', 'pitch'):
            with self.subTest(missing=axis):
                seed = copy.deepcopy(incomplete)
                seed['pose'] = {'x': 2., 'y': 3., 'z': .5, 'roll': 0., 'pitch': 0., 'yaw': 15.}
                del seed['pose'][axis]
                with self.assertRaisesRegex(GlobalObservationValidationError, 'INVALID_LOCAL_SEED'):
                    validate_seed(seed)

    def test_global_hypothesis_is_imu_historical_and_not_verified_body_or_applied(self):
        case = anchor_fixture.AnchorProposalTests()
        case.setUp()
        job = case.job()
        proposal = proposal_from_job(job, case.catalog, case.agent)
        self.assertEqual(proposal['pose_reference'], 'FASTLIO_IMU')
        self.assertTrue(proposal['approximate_only'])
        self.assertTrue(proposal['requires_reanchor'])
        self.assertFalse(proposal['body_extrinsic_verified'])
        self.assertEqual(proposal['operational_application'], 'NOT_RUN')
        self.assertIsNone(proposal['absolute_accuracy_m'])
        # A non-identity body extrinsic changes height and orientation; IMU is not base_link.
        imu_from_body = from_translation_rpy([.25, -.1, -.2], [.05, -.04, .02])
        map_imu = case.map0
        map_body = map_imu @ imu_from_body
        self.assertGreater(np.linalg.norm(map_body[:3, 3] - map_imu[:3, 3]), .1)
        self.assertFalse(np.allclose(map_body[:3, :3], map_imu[:3, :3]))

    def test_global_hypothesis_needs_backend_and_rejects_ambiguous_selection(self):
        case = anchor_fixture.AnchorProposalTests()
        case.setUp()
        owner = GlobalObservationCoordinator(case.catalog, case.agent, ExternalGlobalObservationRunner())
        self.addCleanup(owner.close)
        self.assertFalse(owner.provider_status()['available'])
        with self.assertRaisesRegex(GlobalObservationUnavailable, 'TRUSTED_LOCAL_RUNNER_UNAVAILABLE'):
            owner.start('first-map-proposal', anchor_fixture.MAP_ID, anchor_fixture.REVISION,
                        input_kind='fastlio_imu')
        job = case.job()
        job['result']['observation']['selected_candidate'] = None
        with self.assertRaises((GlobalObservationConflict, ValueError)):
            proposal_from_job(job, case.catalog, case.agent)

    def test_global_overlap_eligibility_is_not_operational_initialization_quality(self):
        anchor = anchor_fixture.AnchorProposalTests()
        anchor.setUp()
        job = anchor.job()
        job['result']['observation']['candidates'][0]['overlap'] = .70
        proposal = proposal_from_job(job, anchor.catalog, anchor.agent)
        self.assertAlmostEqual(proposal['overlap'], .70)
        self.assertTrue(proposal['approximate_only'])
        self.assertEqual(proposal['operational_application'], 'NOT_RUN')
        operational = operational_fixture.Operational3DLocalizationTests()
        operational.setUp()
        self.addCleanup(operational.doCleanups)
        engine = operational.make_engine()
        operational.stationary_reseed(engine, np.eye(4))
        operational.inject_initial_result(engine, np.eye(4), overlap=.70)
        self.assertEqual(engine.reason, 'INITIAL_REFINEMENT_LOW_OVERLAP')
        self.assertFalse(engine.status()['ready'])
        self.assertEqual(engine.initial_candidates, [])

    def test_planar_identity_alone_does_not_determine_vertical_origin(self):
        # A planar xy mapping is unchanged by an arbitrary independent z shift.
        xy = np.array([[0., 0.], [2., -1.], [-.2, 4.]])
        points = np.column_stack((xy, np.zeros(len(xy)), np.ones(len(xy))))
        transforms = [from_translation_rpy([0, 0, z], [0, 0, 0]) for z in (0., 1.5)]
        for transform in transforms:
            np.testing.assert_allclose((transform @ points.T).T[:, :2], xy)
        imu_pose = from_translation_rpy([2., 3., .8], [.1, -.2, .3])
        self.assertAlmostEqual((transforms[1] @ imu_pose)[2, 3] - (transforms[0] @ imu_pose)[2, 3], 1.5)


if __name__ == '__main__':
    unittest.main()
