"""Conditional handoff must retain both exact source and operator bounds."""
import copy
import math
import time
import unittest
from unittest.mock import patch
import numpy as np
from pydantic import ValidationError

import test_navigation_operator_prior as conditional_fixture
import test_navigation_proposal_handoff as handoff_fixture
from robot_dashboard.application.global_observation import GlobalObservationCoordinator
from robot_dashboard.application.navigation_initialization_proposal import NavigationInitializationProposals
from robot_dashboard.relocalization.handoff_policy import CONDITIONAL_POLICY_ID, validate_handoff, validate_candidate
from robot_dashboard.application.planar_prior_selection import retained_candidate_digest
from robot_dashboard.application.anchor_proposal import current_imu
from robot_dashboard.api.routers.operational_navigation import HandoffConfirmation


class ConditionalHandoffTests(unittest.TestCase):
    def setUp(self):
        self.h=handoff_fixture.ProposalHandoffTests();self.h.setUp();self.addCleanup(self.h.doCleanups)
        self.t=conditional_fixture.ConditionalProposalTests();self.t.setUp();self.addCleanup(self.t.doCleanups)
        c=self.t.case; h=self.h
        c.runtime.operational_navigation=h.manager
        c.runtime.fastlio_observation=h.session
        h.session._status['started_monotonic_s']=c.session_state['started_monotonic_s']
        owner=GlobalObservationCoordinator(h.case.catalog,c.runtime.agent,c.runner)
        self.addCleanup(owner.close);c.runtime.global_observation=owner
        self.owner=owner;self.coordinator=NavigationInitializationProposals(c.runtime)
        state=h.manager.status();pair=state['pair']; cal=state['selected']['calibration']
        matrix=np.array(cal['T_nav_map_from_localization_map'])@c.runner.pose@np.array(cal['T_imu_base'])
        self.prior={'frame':'map','pose_reference':'base_link','units':'metres_radians',
          'pose':{'x':float(matrix[0,3]),'y':float(matrix[1,3]),'yaw':math.atan2(matrix[1,0],matrix[0,0])},
          'bounds':{'xy_m':.1,'yaw_rad':.1},'source':'OPERATOR_CURRENT_MAP_DRAFT',
          'stationary_current_pose_confirmed':True,'navigation_map_id':pair['navigation_2d']['map_id'],
          'navigation_map_revision':pair['navigation_2d']['revision'],'calibration_sha256':pair['calibration_sha256']}
        started=self.coordinator.start('conditional-handoff',h.generation,h.session_id,operator_prior=self.prior)
        deadline=time.monotonic()+3
        while owner.job(started['proposal_id'])['worker_active'] and time.monotonic()<deadline:time.sleep(.005)
        self.identifier=started['proposal_id']
    def confirm(self, ack):
        return self.h.manager.confirm_proposal(self.coordinator,self.h.session,self.identifier,'conditional-confirm',
            self.h.generation,self.h.session_id,conditional_prior_acknowledged=ack)
    def test_ack_receipt_dual_bounds_and_tamper(self):
        result=self.coordinator.get(self.identifier);self.assertEqual(result['state'],'ready',result)
        with self.assertRaisesRegex(ValueError,'CONDITIONAL_PRIOR_CONFIRMATION_REQUIRED'):self.confirm(False)
        self.assertIsNone(self.h.manager.selected['seed_geometry'])
        result=self.confirm(True);self.assertEqual(result['state'],'CONFIRMED_OBSERVATION_ACTIVE')
        self.assertEqual(result['policy']['id'],CONDITIONAL_POLICY_ID)
        geometry=self.h.manager.selected['seed_geometry'];proof=geometry['handoff']
        self.assertLessEqual(proof['expires_monotonic_s'],proof['operator_prior_resolution']['expires_monotonic_s'])
        self.h.finish_stop(result['handoff_id'])
        self.h.manager.preflight(self.h.map_id,self.h.revision)
        geometry=self.h.manager.selected['seed_geometry'];proof=geometry['handoff']
        validate_handoff(geometry,self.h.manager.selected)
        ref=proof['reference'];validate_candidate(geometry,ref['x'],ref['y'],ref['yaw'],self.h.manager.selected)
        p=self.prior['pose']
        # 15cm stays within the candidate's 25cm gate but exceeds this prior's 10cm bound.
        with self.assertRaisesRegex(ValueError,'INITIAL_POSE_PRIOR_MISMATCH'):
            validate_candidate(geometry,p['x']+.15,p['y'],p['yaw'],self.h.manager.selected)
        tampered=copy.deepcopy(geometry);tampered['handoff']['operator_prior_resolution']['matching_candidate_count']=2
        with self.assertRaisesRegex(ValueError,'INITIAL_GEOMETRY_PROVENANCE_REQUIRED'):validate_handoff(tampered,self.h.manager.selected)
    def test_prior_changed_after_proposal_never_creates_handoff(self):
        result=self.coordinator.get(self.identifier);self.assertEqual(result['state'],'ready',result)
        record=self.coordinator._records[self.identifier];record['operator_prior']['pose']['x']+=2.
        with self.assertRaises(ValueError):self.confirm(True)
        self.assertIsNone(self.h.manager.selected['seed_geometry'])

    def test_current_pose_outside_prior_cannot_confirm_even_inside_handoff_limit(self):
        self.assertEqual(self.coordinator.get(self.identifier)['state'], 'ready')
        self.t.case.runtime.agent.pose['position']['x'] += .2
        updated = self.coordinator.get(self.identifier)
        self.assertEqual(updated['state'], 'ready', updated)
        self.assertFalse(updated['current_vs_prior']['within_prior_bounds'])
        self.assertTrue(updated['current_vs_prior']['within_existing_handoff_reference'])
        self.assertEqual(updated['operator_prior_resolution'], self.coordinator.get(self.identifier)['operator_prior_resolution'])
        with self.assertRaisesRegex(ValueError, 'PRIOR_HANDOFF_MISMATCH'):
            self.confirm(True)
        self.assertIsNone(self.h.manager.selected['seed_geometry'])

    def test_current_yaw_outside_prior_cannot_confirm(self):
        agent = self.t.case.runtime.agent
        agent.pose['orientation'].update(z=math.sin(.15/2), w=math.cos(.15/2))
        updated = self.coordinator.get(self.identifier)
        self.assertEqual(updated['state'], 'ready', updated)
        self.assertFalse(updated['current_vs_prior']['within_prior_bounds'])
        self.assertTrue(updated['current_vs_prior']['within_existing_handoff_reference'])
        with self.assertRaisesRegex(ValueError, 'PRIOR_HANDOFF_MISMATCH'):
            self.confirm(True)
        self.assertIsNone(self.h.manager.selected['seed_geometry'])

    def test_verified_duplicates_survive_server_owned_confirmation(self):
        with self.owner._lock:
            observation=self.owner._jobs[self.identifier]['result']['observation']
            representative=observation['candidates'][0]
            for candidate in observation['candidates'][1:]:
                candidate['map_from_scan']=copy.deepcopy(representative['map_from_scan'])
                candidate['duplicate_of']=0
            observation['candidate_retention']=retained_candidate_digest(observation)
        proposal=self.coordinator.get(self.identifier)
        self.assertEqual(proposal['state'],'ready',proposal)
        proof=proposal['operator_prior_resolution']
        self.assertEqual((proof['matching_candidate_count'],proof['matching_retained_candidate_count'],
                          proof['matching_hypothesis_count'],proof['verified_duplicate_count']), (6,6,1,5))
        self.assertEqual(proof['matching_member_indices'],list(range(6)))
        self.assertEqual(len(proof['original_observation_sha256']),64)
        result=self.confirm(True)
        self.assertEqual(result['state'],'CONFIRMED_OBSERVATION_ACTIVE')
        self.assertEqual(self.h.manager.selected['seed_geometry']['handoff']['operator_prior_resolution'],proof)
        self.h.finish_stop(result['handoff_id'])
        self.h.manager.preflight(self.h.map_id,self.h.revision)
        geometry=self.h.manager.selected['seed_geometry']
        validate_handoff(geometry,self.h.manager.selected)
        for mutation in ('policy','count','member_index','geometry_delta','member_missing','member_outside'):
            altered=copy.deepcopy(geometry)
            handoff=altered['handoff']; resolution=handoff['operator_prior_resolution']
            if mutation=='policy': resolution['grouping_policy']='UNKNOWN'
            if mutation=='count': resolution['matching_candidate_count']-=1
            if mutation=='member_index': resolution['matching_member_indices'][1]=17
            if mutation=='geometry_delta': resolution['matching_member_geometry'][1]['z_delta_m']+=1.
            if mutation=='member_missing': handoff['operator_prior_current_members']['member_checks'].pop()
            if mutation=='member_outside': handoff['operator_prior_current_members']['member_checks'][1]['xy_distance_m']=1.
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError,'INITIAL_GEOMETRY_PROVENANCE_REQUIRED'):
                validate_handoff(altered,self.h.manager.selected)

    def test_nonrepresentative_current_prior_mismatch_blocks_confirmation(self):
        with self.owner._lock:
            observation=self.owner._jobs[self.identifier]['result']['observation']
            representative=observation['candidates'][0]
            for candidate in observation['candidates'][1:]:
                candidate['map_from_scan']=copy.deepcopy(representative['map_from_scan'])
                candidate['duplicate_of']=0
            observation['candidates'][1]['map_from_scan'][0][3] += .09
            observation['candidate_retention']=retained_candidate_digest(observation)
        before=self.coordinator.get(self.identifier)
        self.assertEqual(before['state'],'ready',before)
        self.t.case.runtime.agent.pose['position']['x'] += .05
        current=self.coordinator.get(self.identifier)
        self.assertTrue(current['current_vs_prior']['within_prior_bounds'])
        self.assertFalse(current['current_vs_prior']['all_members_within_prior_bounds'])
        self.assertFalse(current['current_vs_prior']['member_checks'][1]['within_prior_bounds'])
        context=self.owner.job(self.identifier)['captured_context']
        _,_,odom_now,_=current_imu(self.t.case.runtime.agent,context)
        cal=self.h.manager.selected['calibration']
        member=(np.array(cal['T_nav_map_from_localization_map']) @ np.array(observation['candidates'][1]['map_from_scan'])
                @ np.linalg.inv(np.array(context['anchor_capture']['T_odom_imu'])) @ odom_now @ np.array(cal['T_imu_base']))
        self.assertGreater(math.hypot(member[0,3]-self.prior['pose']['x'],member[1,3]-self.prior['pose']['y']),.1)
        with self.assertRaisesRegex(ValueError,'PRIOR_HANDOFF_MISMATCH'):
            self.confirm(True)
        self.assertIsNone(self.h.manager.selected['seed_geometry'])

    def test_newer_pose_at_watch_boundary_requires_fresh_recomputation(self):
        original=self.coordinator.handoff_watch_context
        def changed(*args):
            context=original(*args)
            context['stamps']=(context['stamps'][0],context['stamps'][1]+1)
            return context
        with patch.object(self.coordinator,'handoff_watch_context',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'OBSERVATION_INPUTS_UNAVAILABLE'):
                self.confirm(True)
        self.assertIsNone(self.h.manager.selected['seed_geometry'])

    def test_normal_publisher_progression_recomputes_handoff_sample(self):
        original=self.coordinator.handoff_watch_context
        def advance(*args):
            context=original(*args)
            agent=self.t.case.runtime.agent
            for message in (agent.cloud,agent.pose):
                observation=message['observation']
                observation['source_stamp_ns']=str(int(observation['source_stamp_ns'])+1)
                observation['received_monotonic_s']=time.monotonic()
            agent.pose['position']['x'] += .02
            return context
        with patch.object(self.coordinator,'handoff_watch_context',side_effect=advance):
            result=self.confirm(True)
        self.assertEqual(result['state'],'CONFIRMED_OBSERVATION_ACTIVE')
        current=self.h.manager.selected['seed_geometry']['handoff']['operator_prior_current_members']
        self.assertEqual(current['pose_stamp_ns'],'12346')
        reference=self.h.manager.selected['seed_geometry']['handoff']['reference']
        self.assertGreater(math.hypot(reference['x']-self.prior['pose']['x'],reference['y']-self.prior['pose']['y']),.01)

    def test_publisher_progression_rechecks_all_members_before_handoff(self):
        with self.owner._lock:
            observation=self.owner._jobs[self.identifier]['result']['observation']
            representative=observation['candidates'][0]
            for candidate in observation['candidates'][1:]:
                candidate['map_from_scan']=copy.deepcopy(representative['map_from_scan'])
                candidate['duplicate_of']=0
            observation['candidates'][1]['map_from_scan'][0][3]+=.09
            observation['candidate_retention']=retained_candidate_digest(observation)
        self.assertTrue(self.coordinator.get(self.identifier)['current_vs_prior']['all_members_within_prior_bounds'])
        original=self.coordinator.handoff_watch_context
        def advance(*args):
            context=original(*args);agent=self.t.case.runtime.agent
            for message in (agent.cloud,agent.pose):
                observation=message['observation']
                observation['source_stamp_ns']=str(int(observation['source_stamp_ns'])+1)
                observation['received_monotonic_s']=time.monotonic()
            agent.pose['position']['x'] += .05
            return context
        with patch.object(self.coordinator,'handoff_watch_context',side_effect=advance):
            with self.assertRaisesRegex(ValueError,'PRIOR_HANDOFF_MISMATCH'):
                self.confirm(True)
        self.assertIsNone(self.h.manager.selected['seed_geometry'])

    def test_slow_watch_boundary_cannot_reuse_stale_member_sample(self):
        original=self.coordinator.handoff_watch_context
        def delayed(*args):
            context=original(*args)
            time.sleep(1.02)
            return context
        with patch.object(self.coordinator,'handoff_watch_context',side_effect=delayed):
            with self.assertRaisesRegex(ValueError,'OBSERVATION_INPUTS_UNAVAILABLE'):
                self.confirm(True)
        self.assertIsNone(self.h.manager.selected['seed_geometry'])

    def test_original_observation_changed_after_preview_cannot_confirm(self):
        self.assertEqual(self.coordinator.get(self.identifier)['state'],'ready')
        with self.owner._lock:
            observation=self.owner._jobs[self.identifier]['result']['observation']
            observation['candidates'][0]['map_from_scan'][0][3] += .01
        with self.assertRaisesRegex(ValueError,'CANDIDATE_RETENTION_UNCONFIRMED'):
            self.confirm(True)
        self.assertIsNone(self.h.manager.selected['seed_geometry'])

    def test_client_cannot_supply_proof_or_mutate_owner_through_responses(self):
        proposal=self.coordinator.get(self.identifier)
        original=copy.deepcopy(proposal['operator_prior_resolution'])
        proposal['operator_prior_resolution']['matching_member_geometry'][0]['z_m']+=.03
        self.assertEqual(self.coordinator.get(self.identifier)['operator_prior_resolution'],original)
        with self.assertRaises(ValidationError):
            HandoffConfirmation.model_validate({'request_id':'injected-proof', 'bundle_generation':self.h.generation,
                'observation_session_id':self.h.session_id,'confirmed':True,'stationary_supervision_acknowledged':True,
                'conditional_prior_acknowledged':True,'operator_prior_resolution':proposal['operator_prior_resolution']})
        result=self.confirm(True)
        public=self.h.manager.status()
        public['selected']['seed_geometry']['handoff']['operator_prior_resolution']['matching_member_geometry'][0]['z_m']+=.03
        self.assertEqual(self.h.manager.selected['seed_geometry']['handoff']['operator_prior_resolution'],original)
        self.assertEqual(self.h.manager.handoff_status(result['handoff_id'])['state'],'CONFIRMED_OBSERVATION_ACTIVE')

if __name__=='__main__':unittest.main()
