"""Synthetic conditional proposal integration, no hardware or systemd."""
import copy
import math
import time
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from test_navigation_presets import LocalASGIClient
from robot_dashboard.api.routers.operational_navigation import router
import numpy as np

from robot_dashboard.api.routers.operational_navigation import InitializationProposalRequest
from robot_dashboard.application.navigation_initialization_proposal import ProposalConflict
from robot_dashboard.application.planar_prior_selection import retained_candidate_digest
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy
from robot_dashboard.relocalization.v031_observation_compat import REVIEWED_HASHES
import test_navigation_initialization_proposal as proposal_fixture


class ConditionalProposalTests(unittest.TestCase):
    def setUp(self):
        self.case=proposal_fixture.ProposalTests(); self.case.setUp(); self.addCleanup(self.case.doCleanups)
        self.pin_sha='a'*64
        self.ambiguous=True
        self.case.runner._configuration=lambda:(None,None,{'files':dict(REVIEWED_HASHES)},self.pin_sha)
        original=self.case.runner.run_arrays
        def run(**kwargs):
            result=original(**kwargs)
            base=result['candidates'][0]
            result.update(gate_reasons=['AMBIGUOUS_ALTERNATIVES'] if self.ambiguous else [],
                          selected_candidate=None if self.ambiguous else 0,
                          ambiguity_override={'enabled':True,'applied':False})
            result['candidates']=[]
            for i in range(6):
                m=self.case.runner.pose.copy();m[0,3] += 0 if i==0 else 3+i
                result['candidates'].append({**copy.deepcopy(base),'attempt':i,'map_from_scan':m.tolist(),
                    'gate_reasons':['AMBIGUOUS_ALTERNATIVES'] if self.ambiguous else [],'capped_full_rmse_m':.1,
                    'duplicate_of':None})
            result['candidate_retention']=retained_candidate_digest(result)
            result['execution']={'source_pin_sha256':self.pin_sha,'worker_reaped':True}
            return result
        self.case.runner.run_arrays=run
    def prior(self):
        c=self.case
        nav=np.array(c.state['selected']['calibration']['T_nav_map_from_localization_map'])
        imu=np.array(c.state['selected']['calibration']['T_imu_base'])
        pose=nav@c.runner.pose@imu
        pair=c.state['pair']
        return {'frame':'map','pose_reference':'base_link','units':'metres_radians',
                'pose':{'x':float(pose[0,3]),'y':float(pose[1,3]),'yaw':math.atan2(pose[1,0],pose[0,0])},
                'bounds':{'xy_m':.5,'yaw_rad':.3},'source':'OPERATOR_CURRENT_MAP_DRAFT',
                'stationary_current_pose_confirmed':True,'navigation_map_id':pair['navigation_2d']['map_id'],
                'navigation_map_revision':pair['navigation_2d']['revision'],'calibration_sha256':pair['calibration_sha256']}
    def start(self, prior=None):
        c=self.case; return c.coordinator.start('test-prior',c.generation,c.session_id,operator_prior=prior or self.prior())
    def test_ready_is_explicitly_conditional_and_no_seed_changed(self):
        prior=self.prior(); before=copy.deepcopy(self.case.state)
        started=self.start(prior); self.case.complete(started)
        result=self.case.coordinator.get(started['proposal_id'])
        self.assertEqual(result['state'],'ready',result)
        self.assertEqual(result['classification'],'CONDITIONAL_ON_OPERATOR_PRIOR')
        self.assertTrue(result['quality']['ambiguity_unresolved'])
        proof=result['operator_prior_resolution']
        self.assertEqual(proof['operator_prior'],prior)
        self.assertEqual(proof['matching_candidate_count'],1)
        self.assertFalse(proof['global_uniqueness_verified'])
        self.assertEqual(self.case.state,before)
        self.assertEqual(self.case.coordinator.validate_conditional_confirmation(started['proposal_id'],proof)['state'],'ready')
    def test_unambiguous_global_still_enforces_prior_and_conditional_proof(self):
        self.ambiguous=False
        started=self.start();self.case.complete(started)
        result=self.case.coordinator.get(started['proposal_id'])
        self.assertEqual(result['state'],'ready',result)
        self.assertEqual(result['classification'],'CONDITIONAL_ON_OPERATOR_PRIOR')
        self.assertIs(result['quality']['ambiguity_unresolved'],False)
        self.assertIs(result['operator_prior_resolution']['original_ambiguity_unresolved'],False)
        fixture=ConditionalProposalTests();fixture.setUp()
        try:
            fixture.ambiguous=False
            far=fixture.prior();far['pose'].update(x=900.,y=900.)
            started=fixture.start(far);fixture.case.complete(started)
            rejected=fixture.case.coordinator.get(started['proposal_id'])
            self.assertEqual((rejected['state'],rejected['reason']),('rejected','PRIOR_NO_MATCH'))
            self.assertIsNone(rejected['navigation_geometry_candidate'])
            self.assertIsNone(rejected['body_candidate'])
            self.assertEqual(rejected['operational_application'],'NOT_RUN')
            diagnostic=rejected['prior_rejection_diagnostics']
            self.assertEqual(diagnostic['prior_pose'],far['pose'])
            self.assertEqual(diagnostic['matching_hypothesis_count'],0)
            self.assertGreater(diagnostic['candidates'][0]['xy_distance_m'],100.)
            fixture.case.coordinator._records[started['proposal_id']]['prior_anchor']['expires_monotonic_s']=time.monotonic()-1
            expired=fixture.case.coordinator.get(started['proposal_id'])
            self.assertEqual(expired['reason'],'OPERATOR_PRIOR_EXPIRED')
            self.assertNotIn('prior_rejection_diagnostics',expired)
        finally: fixture.doCleanups()

    def test_request_id_prior_change_fails(self):
        started=self.start(); self.case.complete(started)
        changed=self.prior();changed['pose']['x']+=.1
        with self.assertRaisesRegex(ProposalConflict,'REQUEST_ID_CONTEXT_CHANGED'):
            self.case.coordinator.start('test-prior',self.case.generation,self.case.session_id,operator_prior=changed)
    def test_source_or_prior_expiry_never_returns_preview(self):
        started=self.start();self.case.complete(started)
        record=self.case.coordinator._records[started['proposal_id']]
        record['prior_anchor']['expires_monotonic_s']=time.monotonic()-1
        result=self.case.coordinator.get(started['proposal_id'])
        self.assertEqual((result['state'],result['reason']),('stale','OPERATOR_PRIOR_EXPIRED'))
        self.assertIsNone(result['navigation_geometry_candidate'])
    def test_changed_source_session_map_or_calibration_discards_preview(self):
        # Each scenario gets a separate coordinator and real global fixture.
        for field in ('source','session','map','calibration'):
            with self.subTest(field=field):
                fixture=ConditionalProposalTests();fixture.setUp()
                try:
                    started=fixture.start();fixture.case.complete(started)
                    if field=='source': fixture.case.runtime.agent.pose['observation']['publisher_epoch']='9'*32
                    if field=='session': fixture.case.session_state['session_id']='9'*32
                    if field=='map': fixture.case.state['pair']['valid']=False
                    if field=='calibration': fixture.case.state['selected']['calibration']['T_imu_base'][2][3]+=.1
                    result=fixture.case.coordinator.get(started['proposal_id'])
                    self.assertEqual(result['state'],'stale')
                    self.assertIsNone(result['navigation_geometry_candidate'])
                finally: fixture.doCleanups()

    def test_bad_map_prior_never_starts_job(self):
        prior=self.prior();prior['navigation_map_id']='9'*24
        with self.assertRaisesRegex(ProposalConflict,'MAP_PAIR_CHANGED'):self.start(prior)
        self.assertEqual(self.case.runner.calls,0)
    def test_asgi_prior_request_and_changed_request_id_conflict(self):
        c=self.case;app=FastAPI();app.include_router(router)
        app.state.runtime=c.runtime;c.runtime._navigation_initialization_proposals=c.coordinator
        client=LocalASGIClient(app)
        path='/api/v1/navigation/operational-3d/initialization-proposals'
        body={'request_id':'api-prior','bundle_generation':c.generation,
              'observation_session_id':c.session_id,'operator_prior':self.prior()}
        async def inline(function,*args,**kwargs): return function(*args,**kwargs)
        with patch('robot_dashboard.api.routers.operational_navigation.asyncio.to_thread',inline):
            started=client.post(path,body);self.assertEqual(started.status_code,202,started.text)
            c.complete(started.json())
            response=client.get(path+'/'+started.json()['proposal_id'])
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['classification'],'CONDITIONAL_ON_OPERATOR_PRIOR')
            self.assertTrue(response.json()['quality']['ambiguity_unresolved'])
            changed=copy.deepcopy(body);changed['operator_prior']['pose']['x']+=.1
            self.assertEqual(client.post(path,changed).status_code,409)

    def test_request_dto_strict_prior(self):
        body={'request_id':'prior-test','bundle_generation':self.case.generation,
              'observation_session_id':self.case.session_id,'operator_prior':self.prior()}
        self.assertEqual(InitializationProposalRequest.model_validate(body).operator_prior.frame,'map')
        for change in ('extra','nan','bool','units','bounds','confirmation_int','confirmation_false'):
            trial=copy.deepcopy(body)
            if change=='extra': trial['operator_prior']['extra']=1
            if change=='nan': trial['operator_prior']['pose']['x']=float('nan')
            if change=='bool': trial['operator_prior']['pose']['x']=True
            if change=='units': trial['operator_prior']['units']='degrees'
            if change=='bounds': trial['operator_prior']['bounds']['xy_m']=.01
            if change=='confirmation_int': trial['operator_prior']['stationary_current_pose_confirmed']=1
            if change=='confirmation_false': trial['operator_prior']['stationary_current_pose_confirmed']=False
            with self.subTest(change=change), self.assertRaises(ValueError): InitializationProposalRequest.model_validate(trial)

if __name__=='__main__': unittest.main()
