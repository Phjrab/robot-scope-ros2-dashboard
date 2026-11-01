"""Conditional handoff must retain both exact source and operator bounds."""
import copy
import math
import time
import unittest
import numpy as np

import test_navigation_operator_prior as conditional_fixture
import test_navigation_proposal_handoff as handoff_fixture
from robot_dashboard.application.global_observation import GlobalObservationCoordinator
from robot_dashboard.application.navigation_initialization_proposal import NavigationInitializationProposals
from robot_dashboard.relocalization.handoff_policy import CONDITIONAL_POLICY_ID, validate_handoff, validate_candidate


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

if __name__=='__main__':unittest.main()
