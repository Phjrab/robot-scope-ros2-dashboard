"""Retained duplicate references are verified against the pinned SE(3) rule."""
import copy
import math
import unittest
import numpy as np

import test_planar_prior_selection as fixture
from robot_dashboard.application.planar_prior_selection import PriorRejected, retained_candidate_digest, select_candidates
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy


class RetainedDuplicateTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.ConditionalPrototypeTests(); self.f.setUp()
        self.identity = np.eye(4)

    def observation(self, matrices, refs):
        obs = self.f.observation(matrices)
        for i, candidate in enumerate(obs['candidates']):
            candidate['duplicate_of'] = refs[i] if i < len(refs) else None
        return self.seal(obs)

    def seal(self, obs):
        obs['candidate_retention'] = retained_candidate_digest(obs)
        return obs

    def select(self, obs, *, nav=None, odom=None, base=None):
        return select_candidates(obs, self.f.ctx, self.f.prior,
            nav_from_localization=self.identity if nav is None else nav,
            odom_from_imu_at_prior=self.identity if odom is None else odom,
            imu_from_base=self.identity if base is None else base, allow_ambiguous=False)

    def test_duplicate_member_group_is_one_without_mutating_evidence(self):
        near = from_translation_rpy([.1,0.,0.],[0.,0.,0.])
        duplicate = from_translation_rpy([.12,0.,0.],[0.,0.,.01])
        distant = from_translation_rpy([3.,0.,0.],[0.,0.,0.])
        obs = self.observation([near, duplicate, distant], [None, 0, None])
        before = copy.deepcopy(obs)
        result = self.select(obs)
        self.assertEqual(result['candidate_index'], 0)
        self.assertEqual(result['eligible_candidate_count'], 3)
        self.assertEqual(result['matching_candidate_count'], 2)
        self.assertEqual(result['matching_hypothesis_count'], 1)
        self.assertEqual(result['matching_member_indices'], [0,1])
        self.assertEqual(obs, before)

    def test_within_threshold_height_and_tilt_differences_are_reported(self):
        tilted=from_translation_rpy([0.,0.,.05],[.02,.01,0.])
        result=self.select(self.observation([self.identity,tilted],[None,0]))
        self.assertEqual(result['matching_member_indices'],[0,1])
        members=result['matching_member_geometry']
        self.assertEqual(members[1]['candidate_index'],1)
        self.assertAlmostEqual(members[1]['z_delta_m'],.05)
        self.assertAlmostEqual(members[1]['roll_delta_rad'],.02)
        self.assertAlmostEqual(members[1]['pitch_delta_rad'],.01)

    def test_crossing_prior_boundary_rejects_the_group(self):
        a=from_translation_rpy([.49,0.,0.],[0.,0.,0.]); b=from_translation_rpy([.51,0.,0.],[0.,0.,0.])
        for first,second in ((a,b),(b,a)):
            with self.subTest(first=first[0,3]), self.assertRaisesRegex(PriorRejected, 'PRIOR_DUPLICATE_BOUNDARY'):
                self.select(self.observation([first,second], [None,0]))

    def test_crossing_yaw_boundary_rejects_the_group(self):
        self.f.prior['bounds']['yaw_rad']=.1
        a=from_translation_rpy([0.,0.,0.],[0.,0.,.09]); b=from_translation_rpy([0.,0.,0.],[0.,0.,.11])
        with self.assertRaisesRegex(PriorRejected, 'PRIOR_DUPLICATE_BOUNDARY'):
            self.select(self.observation([a,b], [None,0]))

    def test_pinned_se3_limits_and_no_match(self):
        at_translation_limit=from_translation_rpy([.1,0.,0.],[0.,0.,0.])
        self.assertEqual(self.select(self.observation([self.identity,at_translation_limit],[None,0]))['candidate_index'],0)
        outside_rotation_limit=from_translation_rpy([0.,0.,0.],[.051,0.,0.])
        with self.assertRaisesRegex(PriorRejected,'PRIOR_MULTIPLE_MATCHES'):
            self.select(self.observation([self.identity,outside_rotation_limit],[None,None]))
        far=from_translation_rpy([3.,0.,0.],[0.,0.,0.]);near_far=from_translation_rpy([3.01,0.,0.],[0.,0.,0.])
        with self.assertRaisesRegex(PriorRejected,'PRIOR_NO_MATCH'):
            self.select(self.observation([far,near_far],[None,0]))

    def test_same_xy_yaw_but_different_height_or_tilt_are_distinct(self):
        for alt in (from_translation_rpy([0.,0.,.2],[0.,0.,0.]), from_translation_rpy([0.,0.,0.],[.1,0.,0.])):
            with self.subTest(alt=alt), self.assertRaisesRegex(PriorRejected,'PRIOR_MULTIPLE_MATCHES'):
                self.select(self.observation([self.identity,alt], [None,None]))

    def test_malformed_or_false_markers_are_rejected(self):
        a=from_translation_rpy([0.,0.,0.],[0.,0.,0.]);b=from_translation_rpy([.01,0.,0.],[0.,0.,0.]);far=from_translation_rpy([2.,0.,0.],[0.,0.,0.])
        for marker in ('missing', True, '0', -1, 1, 2, 99, None):
            obs=self.observation([a,b,far],[None,0,None])
            if marker == 'missing': del obs['candidates'][1]['duplicate_of']
            else: obs['candidates'][1]['duplicate_of']=marker
            with self.subTest(marker=marker), self.assertRaisesRegex(PriorRejected,'CANDIDATE_DUPLICATE_INVALID'):
                self.select(self.seal(obs))
        obs=self.observation([a,b,far],[None,0,0])
        with self.assertRaisesRegex(PriorRejected,'CANDIDATE_DUPLICATE_INVALID'): self.select(obs)

    def test_reference_must_be_first_qualifying_representative_and_not_chain(self):
        a=from_translation_rpy([0.,0.,0.],[0.,0.,0.]);b=from_translation_rpy([.15,0.,0.],[0.,0.,0.]);c=from_translation_rpy([.08,0.,0.],[0.,0.,0.])
        self.f.prior['bounds']['xy_m']=.1
        self.assertEqual(self.select(self.observation([a,b,c],[None,None,0]))['candidate_index'],0)
        with self.assertRaisesRegex(PriorRejected,'CANDIDATE_DUPLICATE_INVALID'):
            self.select(self.observation([a,b,c],[None,None,1]))
        c=from_translation_rpy([.02,0.,0.],[0.,0.,0.])
        with self.assertRaisesRegex(PriorRejected,'CANDIDATE_DUPLICATE_INVALID'):
            self.select(self.observation([a,c,c],[None,0,1]))

    def test_rejected_candidate_cannot_be_referenced(self):
        obs=self.observation([self.identity,self.identity],[None,0])
        obs['candidates'][0]['gate_reasons']=['FAILED_RANSAC']
        with self.assertRaisesRegex(PriorRejected,'CANDIDATE_DUPLICATE_INVALID'):
            self.select(self.seal(obs))

    def test_nonidentity_and_time_propagation_are_applied_to_all_members(self):
        nav=from_translation_rpy([3.,2.,1.],[.1,.2,.3]);cap=from_translation_rpy([1.,2.,.3],[.1,0.,.2])
        odom=from_translation_rpy([1.2,2.1,.4],[.1,.1,.4]);base=from_translation_rpy([.4,0.,.2],[0.,.1,.2])
        fit=from_translation_rpy([2.,-.5,1.],[.2,-.3,.5]); duplicate=fit.copy();duplicate[0,3]+=.01
        self.f.ctx['anchor_capture']['T_odom_imu']=cap.tolist()
        expected=nav@fit@np.linalg.inv(cap)@odom@base
        self.f.prior['pose']={'x':float(expected[0,3]),'y':float(expected[1,3]),'yaw':math.atan2(expected[1,0],expected[0,0])}
        self.assertEqual(self.select(self.observation([fit,duplicate],[None,0]),nav=nav,odom=odom,base=base)['candidate_index'],0)
        with self.assertRaisesRegex(PriorRejected,'PRIOR_NO_MATCH'):
            self.select(self.observation([fit,duplicate],[None,0]))

if __name__=='__main__': unittest.main()
