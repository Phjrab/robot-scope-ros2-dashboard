"""Synthetic exact-stop proof probes. No robot or network access."""
import unittest
from test_observation_bridge_session import active_session
from robot_dashboard.observation_service import ObservationServiceError

class ExactStopProofTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_stop_dispatch_with_inactive_readback_retains_inhibit(self):
        _, owner, service, loop, _ = active_session()
        state = await owner.start()
        self.assertIsNotNone(loop.core._observation_inhibit)
        def response_lost(action):
            service.calls.append(action)
            service.state = 'inactive'
            raise ObservationServiceError('synthetic stop response lost')
        service.dispatch = response_lost
        with self.assertRaises(ObservationServiceError):
            await owner.stop(state['session_id'])
        self.assertFalse(owner._bridge_stop_accepted)
        self.assertIsNotNone(loop.core._observation_inhibit)
        self.assertTrue(owner.busy())
        self.assertEqual(owner.snapshot()['reason'], 'OBSERVATION_STOP_ACCEPTANCE_UNCONFIRMED')

    async def test_unsolicited_observation_exit_retains_inhibit_without_exact_stop(self):
        _, owner, service, loop, _ = active_session()
        await owner.start()
        service.state = 'inactive'
        await owner.refresh()
        self.assertFalse(owner._bridge_stop_accepted)
        self.assertIsNotNone(loop.core._observation_inhibit)
        self.assertTrue(owner.busy())
        self.assertEqual(owner.snapshot()['reason'], 'OBSERVATION_STOP_ACCEPTANCE_UNCONFIRMED')

if __name__ == '__main__': unittest.main(verbosity=2)
