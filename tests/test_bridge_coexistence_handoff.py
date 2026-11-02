"""Signed bridge + observation + real proposal/handoff owners; synthetic inputs only."""
import asyncio
import time
import unittest
from test_observation_bridge_session import active_session
import test_navigation_initialization_proposal as proposal_fixture
import test_operational_navigation_bundle as bundle_fixture
from robot_dashboard.application.global_observation import GlobalObservationCoordinator
from robot_dashboard.application.navigation_initialization_proposal import NavigationInitializationProposals


class BridgeHandoffTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bundle = bundle_fixture.OperationalNavigationBundleTests()
        self.bundle.setUp()
        self.addCleanup(self.bundle.doCleanups)
        self.manager = self.bundle.manager
        self.addCleanup(self.manager.close_handoff_monitor)
        selection = self.manager.select_pair(self.bundle.pair_fixture())
        self.generation = selection['selected']['generation']
        self.runtime, self.observation, self.service, self.link, _ = active_session()
        self.state = await self.observation.start()
        self.case = proposal_fixture.ProposalTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        old_agent = self.runtime.agent
        self.runtime.agent = self.case.runtime.agent
        self.runtime.agent._control_transport = self.link.transport
        self.runtime.agent._pointcloud_hub = old_agent._pointcloud_hub
        self.runtime.operational_navigation = self.manager
        self.global_owner = GlobalObservationCoordinator(self.bundle.catalog, self.runtime.agent, self.case.runner)
        self.addCleanup(self.global_owner.close)
        self.runtime.global_observation = self.global_owner
        self.proposals = NavigationInitializationProposals(self.runtime)
        self.runtime._navigation_initialization_proposals = self.proposals
        self.job = self.proposals.start('bridge-handoff-proposal', self.generation, self.state['session_id'])
        deadline = time.monotonic() + 3
        while self.global_owner.job(self.job['proposal_id'])['worker_active'] and time.monotonic() < deadline:
            await asyncio.sleep(.005)
        self.assertFalse(self.global_owner.job(self.job['proposal_id'])['worker_active'])

    def confirm(self):
        return self.manager.confirm_proposal(self.proposals, self.observation,
            self.job['proposal_id'], 'bridge-handoff-confirm', self.generation, self.state['session_id'])

    async def test_explicit_confirmation_and_exact_stop_preserve_geometry_provenance(self):
        self.assertIsNone(self.manager.selected.get('seed_geometry'))
        proposal = self.proposals.get(self.job['proposal_id'])
        self.assertEqual(proposal['state'], 'ready')
        confirmed = self.confirm()
        self.assertEqual(confirmed['state'], 'CONFIRMED_OBSERVATION_ACTIVE')
        self.assertEqual(confirmed['source'], 'proposal_confirmed')
        self.assertEqual(confirmed['geometry'], {k: proposal['navigation_geometry_candidate']['pose'][k]
                                              for k in ('z', 'roll', 'pitch')})
        self.assertEqual(self.service.calls, ['start'])
        self.assertIsNotNone(self.link.core._observation_inhibit)
        stopped = await self.observation.stop(self.state['session_id'])
        self.assertEqual(stopped['state'], 'STOPPED')
        self.assertEqual(self.observation.handoff_receipt(confirmed['handoff_id'])['state'], 'INACTIVE_CONFIRMED')
        self.assertIsNone(self.link.core._observation_inhibit)
        self.assertEqual(self.service.calls, ['start', 'stop'])
        self.assertEqual(self.manager.selected['seed_geometry']['source'], 'proposal_confirmed')
        self.assertEqual(confirmed['operational_application'], 'NOT_RUN')

    async def test_lost_guard_blocks_confirm_even_after_link_returns(self):
        self.link.transport.set_unready('synthetic guard loss')
        self.link.status()
        with self.assertRaises(ValueError):
            self.confirm()
        self.assertIsNone(self.manager.selected.get('seed_geometry'))
        self.assertEqual(self.service.calls, ['start'])
        self.assertEqual(self.proposals.get(self.job['proposal_id'])['state'], 'stale')
        await self.observation.stop(self.state['session_id'])


if __name__ == '__main__': unittest.main()
