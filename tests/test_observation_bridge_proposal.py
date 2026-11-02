import copy
import time
import unittest
from types import SimpleNamespace

import test_navigation_initialization_proposal as proposal_fixture
from test_observation_bridge_transport import SignedLoop
from robot_dashboard.application.fastlio_observation import FastlioObservationSession


class ActiveBridgeProposalTests(unittest.TestCase):
    def setUp(self):
        self.case=proposal_fixture.ProposalTests();self.case.setUp();self.addCleanup(self.case.doCleanups)
        c=self.case;self.loop=SignedLoop()
        c.runtime.agent._control_transport=self.loop.transport
        token=self.loop.transport.begin_observation_inhibit()
        self.owner=FastlioObservationSession(c.runtime,enabled=True,service=SimpleNamespace())
        self.owner._status=dict(copy.deepcopy(c.session_state),busy=True)
        self.owner._bridge_context=dict(token=token,invocation_id='c'*32)
        c.runtime.fastlio_observation=self.owner
        c.runtime._navigation_initialization_proposals=c.coordinator
        c.runtime.lifecycle.control_bridge_lifecycle._read_systemd=lambda:dict(
            available=True,active_state='active',sub_state='running',invocation_id='c'*32)

    def test_active_bridge_proposal_ready_preserves_geometry_and_source_fences(self):
        c=self.case
        started=c.coordinator.start('active-bridge-proposal',c.generation,c.session_id)
        c.complete(started)
        result=c.coordinator.get(started['proposal_id'])
        self.assertEqual(result['state'],'ready',result)
        self.assertEqual(result['navigation_geometry_candidate']['frame'],'map')
        self.assertEqual(result['operational_application'],'NOT_RUN')
        self.assertNotIn('seed_geometry',c.state['selected'])
        c.runtime.agent.pose['observation']['publisher_epoch']='9'*32
        result=c.coordinator.get(started['proposal_id'])
        self.assertEqual(result['state'],'stale')
        self.assertIsNone(result['navigation_geometry_candidate'])

    def test_ready_candidate_never_revives_after_control_loss(self):
        c=self.case;started=c.coordinator.start('active-loss',c.generation,c.session_id)
        c.complete(started)
        self.assertEqual(c.coordinator.get(started['proposal_id'])['state'],'ready')
        self.loop.transport.set_unready('synthetic loss');self.loop.status()
        for _ in range(2):
            result=c.coordinator.get(started['proposal_id'])
            self.assertEqual(result['state'],'stale')
            self.assertIsNone(result['body_candidate'])
            self.assertIsNone(result['navigation_geometry_candidate'])
            self.loop.status()

    def test_running_job_is_invalidated_without_a_get_request(self):
        c=self.case;c.runner.release.clear()
        started=c.coordinator.start('active-running-loss',c.generation,c.session_id)
        self.assertTrue(c.runner.entered.wait(1.))
        self.loop.core.force_stop('synthetic emergency stop');self.loop.status()
        record=c.coordinator._records[started['proposal_id']]
        deadline=time.monotonic()+1.
        while not record.get('invalidated_reason') and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue(record.get('invalidated_reason'))
        self.assertTrue(record['cleanup']['cancellation_requested'])
        c.runner.release.set();c.complete(started)
        self.assertEqual(c.coordinator.get(started['proposal_id'])['state'],'stale')


if __name__ == '__main__':unittest.main()
