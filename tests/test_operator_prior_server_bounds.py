"""A current pose draft can use the server's fixed acceptance policy."""
import copy
import time
import unittest

from pydantic import ValidationError

import test_navigation_operator_prior as proposal_fixture
import test_navigation_operator_prior_handoff as handoff_fixture
import test_planar_prior_duplicates as duplicate_fixture
from robot_dashboard.api.routers.operational_navigation import OperatorPrior
from robot_dashboard.application.navigation_initialization_proposal import ProposalConflict
from robot_dashboard.application.planar_prior_selection import PriorRejected, validate_prior
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy
from robot_dashboard.relocalization.handoff_policy import MAX_XY_M, MAX_YAW_RAD, validate_handoff, validate_candidate


class ServerPriorBoundsTests(unittest.TestCase):
    def proposal(self):
        fixture = proposal_fixture.ConditionalProposalTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        return fixture

    def handoff(self, *, prior_x_offset=0.):
        fixture = handoff_fixture.ConditionalHandoffTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        prior = copy.deepcopy(fixture.prior); prior.pop('bounds')
        prior['pose']['x'] += prior_x_offset
        started = fixture.coordinator.start('server-fixed-policy', fixture.h.generation,
            fixture.h.session_id, operator_prior=prior)
        deadline = time.monotonic() + 3.
        while fixture.owner.job(started['proposal_id'])['worker_active'] and time.monotonic() < deadline:
            time.sleep(.005)
        fixture.identifier = started['proposal_id']
        return fixture

    def test_omitted_bounds_preserve_the_draft_without_inventing_user_values(self):
        fixture = self.proposal(); prior = fixture.prior(); prior.pop('bounds')
        self.assertEqual(validate_prior(prior), prior)
        body = OperatorPrior.model_validate(prior).model_dump(exclude_none=True)
        self.assertEqual(body, prior)
        null_prior = {**prior, 'bounds': None}
        self.assertEqual(validate_prior(null_prior), prior)
        for key in ('bounds_source', 'effective_bounds'):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                OperatorPrior.model_validate({**prior, key: 'server_policy'})

    def test_server_fixed_policy_is_bound_to_the_proposal_and_request_id(self):
        fixture = self.proposal(); prior = fixture.prior(); prior.pop('bounds')
        started = fixture.start(prior); fixture.case.complete(started)
        result = fixture.case.coordinator.get(started['proposal_id'])
        self.assertEqual(result['state'], 'ready', result)
        proof = result['operator_prior_resolution']
        self.assertEqual(proof['operator_prior'], prior)
        self.assertEqual(proof['bounds_source'], 'server_policy')
        self.assertEqual(proof['effective_bounds'], {'xy_m': MAX_XY_M, 'yaw_rad': MAX_YAW_RAD})
        self.assertTrue(proof['original_ambiguity_unresolved'])
        tampered = copy.deepcopy(proof); tampered['effective_bounds']['xy_m'] = .3
        with self.assertRaisesRegex(ProposalConflict, 'OPERATOR_PRIOR_PROOF_CHANGED'):
            fixture.case.coordinator.validate_conditional_confirmation(started['proposal_id'], tampered)
        changed = {**prior, 'bounds': {'xy_m': MAX_XY_M, 'yaw_rad': MAX_YAW_RAD}}
        with self.assertRaisesRegex(ProposalConflict, 'REQUEST_ID_CONTEXT_CHANGED'):
            fixture.case.coordinator.start('test-prior', fixture.case.generation,
                fixture.case.session_id, operator_prior=changed)

    def test_explicit_bounds_keep_the_original_contract(self):
        fixture = self.proposal(); prior = fixture.prior()
        started = fixture.start(prior); fixture.case.complete(started)
        proof = fixture.case.coordinator.get(started['proposal_id'])['operator_prior_resolution']
        self.assertEqual(proof['operator_prior'], prior)
        self.assertEqual(proof['bounds_source'], 'operator_prior')
        self.assertEqual(proof['effective_bounds'], prior['bounds'])

    def test_all_members_still_have_to_fit_the_fixed_server_policy(self):
        fixture = duplicate_fixture.RetainedDuplicateTests(); fixture.setUp()
        fixture.f.prior.pop('bounds')
        for a, b in (([.24, 0., 0.], [.26, 0., 0.]),):
            first = from_translation_rpy(a, [0., 0., 0.])
            second = from_translation_rpy(b, [0., 0., 0.])
            with self.assertRaisesRegex(PriorRejected, 'PRIOR_DUPLICATE_BOUNDARY'):
                fixture.select(fixture.observation([first, second], [None, 0]))
        outside = from_translation_rpy([.26, 0., 0.], [0., 0., 0.])
        with self.assertRaisesRegex(PriorRejected, 'PRIOR_NO_MATCH'):
            fixture.select(fixture.observation([outside], [None]))
        first = from_translation_rpy([0., 0., 0.], [0., 0., .19])
        second = from_translation_rpy([0., 0., 0.], [0., 0., .21])
        with self.assertRaisesRegex(PriorRejected, 'PRIOR_DUPLICATE_BOUNDARY'):
            fixture.select(fixture.observation([first, second], [None, 0]))

    def test_confirmation_stop_and_handoff_validate_the_server_policy_source(self):
        fixture = self.handoff()
        result = fixture.confirm(True)
        fixture.h.finish_stop(result['handoff_id'])
        fixture.h.manager.preflight(fixture.h.map_id, fixture.h.revision)
        geometry = fixture.h.manager.selected['seed_geometry']
        validate_handoff(geometry, fixture.h.manager.selected)
        for key, value in (('bounds_source', 'operator_prior'),
                           ('effective_bounds', {'xy_m': .3, 'yaw_rad': MAX_YAW_RAD})):
            tampered = copy.deepcopy(geometry)
            tampered['handoff']['operator_prior_resolution'][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'INITIAL_GEOMETRY_PROVENANCE_REQUIRED'):
                validate_handoff(tampered, fixture.h.manager.selected)
        for removed in (('bounds_source',), ('effective_bounds',), ('bounds_source', 'effective_bounds')):
            tampered = copy.deepcopy(geometry)
            for key in removed:
                tampered['handoff']['operator_prior_resolution'].pop(key)
            with self.subTest(removed=removed), self.assertRaisesRegex(ValueError, 'INITIAL_GEOMETRY_PROVENANCE_REQUIRED'):
                validate_handoff(tampered, fixture.h.manager.selected)

    def test_legacy_explicit_bounds_proof_remains_valid_without_policy_fields(self):
        fixture = handoff_fixture.ConditionalHandoffTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        result = fixture.confirm(True); fixture.h.finish_stop(result['handoff_id'])
        fixture.h.manager.preflight(fixture.h.map_id, fixture.h.revision)
        geometry = copy.deepcopy(fixture.h.manager.selected['seed_geometry'])
        resolution = geometry['handoff']['operator_prior_resolution']
        resolution.pop('bounds_source'); resolution.pop('effective_bounds')
        validate_handoff(geometry, fixture.h.manager.selected)

    def test_initial_pose_must_fit_fixed_policy_as_well_as_candidate_reference(self):
        fixture = self.handoff(prior_x_offset=-.2)
        result = fixture.confirm(True); fixture.h.finish_stop(result['handoff_id'])
        fixture.h.manager.preflight(fixture.h.map_id, fixture.h.revision)
        geometry = fixture.h.manager.selected['seed_geometry']; reference = geometry['handoff']['reference']
        with self.assertRaisesRegex(ValueError, 'INITIAL_POSE_PRIOR_MISMATCH'):
            validate_candidate(geometry, reference['x'] + .1, reference['y'], reference['yaw'], fixture.h.manager.selected)

    def test_current_pose_outside_fixed_policy_never_confirms(self):
        fixture = self.handoff()
        fixture.t.case.runtime.agent.pose['position']['x'] += .3
        with self.assertRaisesRegex(ValueError, 'PRIOR_HANDOFF_MISMATCH'):
            fixture.confirm(True)
        self.assertIsNone(fixture.h.manager.selected['seed_geometry'])

    def test_server_bounds_do_not_extend_prior_expiry(self):
        fixture = self.proposal(); prior = fixture.prior(); prior.pop('bounds')
        started = fixture.start(prior); fixture.case.complete(started)
        fixture.case.coordinator._records[started['proposal_id']]['prior_anchor']['expires_monotonic_s'] = time.monotonic() - 1.
        result = fixture.case.coordinator.get(started['proposal_id'])
        self.assertEqual(result['reason'], 'OPERATOR_PRIOR_EXPIRED')
        self.assertIsNone(result['navigation_geometry_candidate'])


if __name__ == '__main__':
    unittest.main()
