"""Pure offline prototype tests; no production integration or sensor access."""
import copy
import math
import unittest

import numpy as np
from robot_dashboard.application.planar_prior_selection import PriorRejected, select_candidates, validate_prior, retained_candidate_digest
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy
from robot_dashboard.relocalization.global_observation_worker import _retained_candidate_metadata
from test_anchor_proposal import result_for
from robot_dashboard.relocalization.v031_observation_compat import apply_ambiguity_override


class ConditionalPrototypeTests(unittest.TestCase):
    def setUp(self):
        self.ctx = {'map_frame':'camera_init','source_frame':'body','source_stamp_ns':'123',
                    'observer_epoch':'e'*32,'map':{'sha256':'a'*64,'point_count':120},
                    'scan':{'point_count':80},'anchor_capture':{'T_odom_imu':np.eye(4).tolist()}}
        self.prior = {'frame':'map','pose_reference':'base_link','units':'metres_radians',
                      'pose':{'x':0.,'y':0.,'yaw':0.},'bounds':{'xy_m':.5,'yaw_rad':.3},
                      'source':'OPERATOR_CURRENT_MAP_DRAFT','stationary_current_pose_confirmed':True,
                      'navigation_map_id':'c'*24, 'navigation_map_revision':'d'*64, 'calibration_sha256':'e'*64}
        self.ident = np.eye(4)
    def observation(self, matrices):
        obj=result_for(self.ctx, matrices[0])
        prototype=obj['candidates'][0]
        obj.update(gate_reasons=['AMBIGUOUS_ALTERNATIVES'], selected_candidate=None,
                   ambiguity_override={'enabled':False,'applied':False})
        obj['candidates']=[{**copy.deepcopy(prototype), 'map_from_scan':m.tolist(),
                            'gate_reasons':['AMBIGUOUS_ALTERNATIVES'], 'capped_full_rmse_m':.1,
                            'attempt':i, 'duplicate_of':None}
                           for i,m in enumerate(matrices)]
        for i in range(len(matrices),6):
            obj['candidates'].append({'attempt':i,'map_from_scan':None,'gate_reasons':['FAILED_RANSAC'], 'duplicate_of':None})
        obj['candidate_retention']=retained_candidate_digest(obj)
        return obj
    def call(self, matrices, **opts):
        return select_candidates(self.observation(matrices),self.ctx,self.prior,
            nav_from_localization=opts.get('nav',self.ident), odom_from_imu_at_prior=opts.get('odom',self.ident),
            imu_from_base=opts.get('base',self.ident), allow_ambiguous=False)
    def test_one_zero_multiple_and_different_height_tilt(self):
        near=from_translation_rpy([.1,.1,.7],[.2,-.1,0.])
        far=from_translation_rpy([2.,0.,0.],[0.,0.,0.])
        self.assertEqual(self.call([near,far])['candidate_index'],0)
        with self.assertRaisesRegex(PriorRejected,'PRIOR_NO_MATCH'): self.call([far])
        duplicate=self.observation([near,near]);duplicate['candidates'][1]['duplicate_of']=0
        duplicate['candidate_retention']=retained_candidate_digest(duplicate)
        self.assertEqual(select_candidates(duplicate,self.ctx,self.prior,nav_from_localization=self.ident,
            odom_from_imu_at_prior=self.ident,imu_from_base=self.ident,allow_ambiguous=False)['candidate_index'],0)
        alternative=from_translation_rpy([.1,.1,2.],[.4,.2,0.])
        with self.assertRaisesRegex(PriorRejected,'PRIOR_MULTIPLE_MATCHES'): self.call([near,alternative])
    def test_inclusive_bounds_and_wrap_and_handoff_diagnostic(self):
        self.prior['pose']['yaw']=math.pi-.1
        self.prior['bounds']={'xy_m':1.,'yaw_rad':.25}
        near=from_translation_rpy([1.,0.,0.],[0.,0.,-math.pi+.1])
        result=self.call([near])
        self.assertAlmostEqual(result['candidate_vs_prior']['xy_distance_m'],1.)
        self.assertAlmostEqual(result['candidate_vs_prior']['absolute_wrapped_yaw_rad'],.2)
        self.assertFalse(result['candidate_vs_prior']['within_existing_handoff_reference'])
    def test_nonidentity_transform_order(self):
        nav=from_translation_rpy([3.,2.,1.],[.1,.2,.3]); cap=from_translation_rpy([1.,2.,.3],[.1,0.,.2]);
        odom=from_translation_rpy([1.2,2.1,.4],[.1,.1,.4]); body=from_translation_rpy([.4,0.,.2],[0.,.1,.2]);
        fit=from_translation_rpy([2.,-.5,1.],[.2,-.3,.5]); self.ctx['anchor_capture']['T_odom_imu']=cap.tolist()
        expected=nav@fit@np.linalg.inv(cap)@odom@body
        self.prior['pose']={'x':float(expected[0,3]),'y':float(expected[1,3]),'yaw':math.atan2(expected[1,0],expected[0,0])}
        self.assertEqual(self.call([fit],nav=nav,odom=odom,base=body)['candidate_index'],0)
        with self.assertRaisesRegex(PriorRejected,'PRIOR_NO_MATCH'): self.call([fit])
    def test_invalid_prior_extra_units_nan_or_unconfirmed(self):
        for change in ('extra','unit','nan','zero','bool','unconfirmed'):
            p=copy.deepcopy(self.prior)
            if change=='extra': p['unexpected']=1
            if change=='unit': p['units']='degrees'
            if change=='nan': p['pose']['x']=float('nan')
            if change=='zero': p['bounds']['xy_m']=0.
            if change=='bool': p['pose']['x']=True
            if change=='unconfirmed': p['stationary_current_pose_confirmed']=False
            with self.subTest(change=change), self.assertRaises(PriorRejected): validate_prior(p)

    def test_rejection_diagnostics_use_exact_prior_time_body_transform_and_wrapped_yaw(self):
        nav=from_translation_rpy([3.,2.,1.],[.1,.2,.3])
        cap=from_translation_rpy([1.,2.,.3],[.1,0.,.2])
        odom=from_translation_rpy([1.2,2.1,.4],[.1,.1,.4])
        body=from_translation_rpy([.4,0.,.2],[0.,.1,.2])
        fit=from_translation_rpy([2.,-.5,1.],[.2,-.3,.5])
        self.ctx['anchor_capture']['T_odom_imu']=cap.tolist()
        expected=nav@fit@np.linalg.inv(cap)@odom@body
        yaw=math.atan2(expected[1,0],expected[0,0])
        self.prior['pose']={'x':float(expected[0,3])+1.,'y':float(expected[1,3]),'yaw':yaw}
        with self.assertRaisesRegex(PriorRejected,'PRIOR_NO_MATCH') as caught:
            self.call([fit],nav=nav,odom=odom,base=body)
        d=caught.exception.diagnostics; c=d['candidates'][0]
        self.assertEqual(d['qualification'],'HISTORICAL_PRIOR_COMPARISON_ONLY')
        self.assertEqual(d['matching_hypothesis_count'],0)
        self.assertEqual(d['eligible_candidate_count'],1)
        self.assertAlmostEqual(c['pose']['x'],expected[0,3])
        self.assertAlmostEqual(c['xy_distance_m'],1.)
        self.assertAlmostEqual(c['absolute_wrapped_yaw_rad'],0.)
        self.assertFalse(c['within_xy_bound']); self.assertTrue(c['within_yaw_bound'])
        self.assertNotIn('z',c['pose'])
        self.prior['pose']['yaw']=math.pi-.1
        wrapped=from_translation_rpy([2.,0.,0.],[0.,0.,-math.pi+.1])
        self.ctx['anchor_capture']['T_odom_imu']=self.ident.tolist()
        self.prior['pose'].update(x=0.,y=0.)
        with self.assertRaisesRegex(PriorRejected,'PRIOR_NO_MATCH') as caught:
            self.call([wrapped])
        self.assertAlmostEqual(caught.exception.diagnostics['candidates'][0]['absolute_wrapped_yaw_rad'],.2)

    def test_unvalidated_candidate_set_never_has_rejection_comparisons(self):
        obs=self.observation([self.ident]);obs['candidate_retention']['sha256']='0'*64
        with self.assertRaises(PriorRejected) as caught:
            select_candidates(obs,self.ctx,self.prior,nav_from_localization=self.ident,
                odom_from_imu_at_prior=self.ident,imu_from_base=self.ident,allow_ambiguous=False)
        self.assertIsNone(caught.exception.diagnostics)
    def test_observation_only_override_does_not_choose_the_prior_match(self):
        near=from_translation_rpy([.1,0.,.5],[0.,0.,0.])
        far=from_translation_rpy([2.,0.,.5],[0.,0.,0.])
        obs=self.observation([near,far])
        obs['candidates'][0]['rmse_m']=.2
        obs['candidates'][1]['rmse_m']=.01
        apply_ambiguity_override(obs,allow_ambiguous=True)
        obs['candidate_retention']=retained_candidate_digest(obs)
        self.assertEqual(obs['selected_candidate'],1)
        original=copy.deepcopy(obs)
        result=select_candidates(obs,self.ctx,self.prior,nav_from_localization=self.ident,
            odom_from_imu_at_prior=self.ident,imu_from_base=self.ident,allow_ambiguous=True)
        self.assertEqual(result['candidate_index'],0)
        self.assertTrue(result['original_ambiguity_preserved'])
        self.assertFalse(result['global_uniqueness_verified'])
        self.assertEqual(obs,original)

    def test_worker_and_consumer_agree_on_complete_retained_digest(self):
        obs=self.observation([self.ident])
        self.assertEqual(_retained_candidate_metadata(obs),obs['candidate_retention'])
        obs['candidates'].pop()
        self.assertIsNone(_retained_candidate_metadata(obs))

    def test_missing_or_tampered_retention_never_becomes_unique(self):
        for mutation in ('missing', 'digest', 'attempt'):
            obs=self.observation([self.ident])
            if mutation == 'missing': obs.pop('candidate_retention')
            if mutation == 'digest': obs['candidate_retention']['sha256']='0'*64
            if mutation == 'attempt': obs['candidates'].pop()
            with self.subTest(mutation=mutation), self.assertRaisesRegex(PriorRejected,'CANDIDATE_RETENTION_UNCONFIRMED'):
                select_candidates(obs,self.ctx,self.prior,nav_from_localization=self.ident,
                    odom_from_imu_at_prior=self.ident,imu_from_base=self.ident,allow_ambiguous=False)

    def test_unknown_or_malformed_quality_gate_fails_closed(self):
        for gate in ('UNKNOWN_NOT_A_REVIEWED_GATE', 7, ''):
            obs=self.observation([self.ident]);obs['candidates'][1]['gate_reasons']=[gate]
            obs['candidate_retention']=retained_candidate_digest(obs)
            with self.subTest(gate=gate), self.assertRaisesRegex(PriorRejected,'CANDIDATE_QUALITY_UNAVAILABLE'):
                select_candidates(obs,self.ctx,self.prior,nav_from_localization=self.ident,
                    odom_from_imu_at_prior=self.ident,imu_from_base=self.ident,allow_ambiguous=False)

    def test_quality_failure_must_not_be_omitted(self):
        obs=self.observation([self.ident,self.ident]);obs['candidates'][1]['duplicate_of']=0;obs['candidates'][1]['inlier_count']=0;obs['candidate_retention']=retained_candidate_digest(obs)
        with self.assertRaisesRegex(PriorRejected,'CANDIDATE_QUALITY_UNAVAILABLE'):
            select_candidates(obs,self.ctx,self.prior,nav_from_localization=self.ident,
                 odom_from_imu_at_prior=self.ident,imu_from_base=self.ident,allow_ambiguous=False)

if __name__=='__main__': unittest.main()
