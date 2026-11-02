"""Failure probes for gaps not covered by the imported candidate. Offline only."""
import unittest
import asyncio
from test_observation_bridge_transport import SignedLoop
from test_observation_bridge_session import active_session
from robot_dashboard.observation_service import ObservationServiceError


class TransportGapTests(unittest.TestCase):
    def test_retained_bridge_hold_blocks_arm_even_without_local_owner(self):
        from robot_dashboard.control import ControlNotReady
        for lose_local_owner in (False, True):
            with self.subTest(lose_local_owner=lose_local_owner):
                loop = SignedLoop()
                loop.transport.begin_observation_inhibit()
                if lose_local_owner:
                    loop.transport._observation_inhibit = None
                    loop.status()
                with self.assertRaises(ControlNotReady):
                    loop.transport.manager.acquire_lease('keyboard')

    def test_unknown_inactive_is_not_an_admission_proof(self):
        from robot_dashboard.application.observation_bridge import bridge_admission_error
        self.assertEqual(bridge_admission_error(None, {'active_state': 'inactive', 'available': False}),
                         'CONTROL_BRIDGE_STATE_UNKNOWN')

    def test_new_status_cannot_hide_an_unsampled_receipt_gap(self):
        loop = SignedLoop()
        token = loop.transport.begin_observation_inhibit()
        loop.transport.status_received -= 2.
        # No intermediate snapshot/tick: the fresh callback itself must latch the gap.
        loop.status()
        self.assertEqual(loop.transport.observation_inhibit_status(token)['state'], 'INVALID')
        loop.status()
        self.assertEqual(loop.transport.observation_inhibit_status(token)['state'], 'INVALID')


class StartOutcomeTests(unittest.IsolatedAsyncioTestCase):
    async def test_monitor_refresh_serializes_with_admission_without_lock_inversion(self):
        runtime, owner, service, loop, _ = active_session()
        async with runtime.pipeline_coordination_lock:
            pending = asyncio.create_task(owner.refresh())
            await asyncio.sleep(.01)
            self.assertFalse(pending.done())
        result = await asyncio.wait_for(pending, 1.)
        self.assertEqual(result['state'], 'STOPPED')

    async def test_uncertain_start_stopped_readback_cannot_release_hold(self):
        runtime, owner, service, loop, _ = active_session()
        def uncertain(action):
            service.calls.append(action)
            raise ObservationServiceError('synthetic start response lost')
        service.dispatch = uncertain
        with self.assertRaises(ObservationServiceError):
            await owner.start()
        self.assertIsNotNone(loop.core._observation_inhibit)
        self.assertTrue(owner.busy())
        self.assertFalse(owner.snapshot()['can_start'])
        # A late service activation does not cure uncertain admission.
        service.state = 'active'
        await owner.refresh()
        self.assertNotEqual(owner.snapshot()['state'], 'READY')
        self.assertIsNotNone(loop.core._observation_inhibit)

    async def test_accepted_async_start_waits_for_activation_before_release(self):
        runtime, owner, service, loop, _ = active_session()
        service.dispatch = lambda action: service.calls.append(action)
        await owner.start()
        self.assertIsNotNone(loop.core._observation_inhibit)
        self.assertTrue(owner.busy())
        service.state = 'active'
        await owner.refresh()
        self.assertEqual(owner.snapshot()['state'], 'READY')
        self.assertEqual(owner.snapshot()['bridge_guard']['state'], 'HELD')

    async def test_observation_invocation_replacement_is_latched(self):
        runtime, owner, service, loop, _ = active_session()
        await owner.start()
        service.invocation = 'f' * 32
        await owner.refresh()
        self.assertNotEqual(owner.snapshot()['state'], 'READY')
        service.invocation = 'a' * 32
        await owner.refresh()
        self.assertNotEqual(owner.snapshot()['state'], 'READY')


class ReleaseReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_release_ack_before_next_refresh_keeps_valid_handoff(self):
        runtime, owner, service, loop, _ = active_session()
        state = await owner.start()
        owner.reserve_handoff_receipt('handoff', state['session_id'], state['started_monotonic_s'])
        loop.ack = False
        await owner.stop(state['session_id'])
        loop.status()
        owner.snapshot()  # UI GET can arrive between signed ACK and monitor refresh.
        await owner.refresh()
        self.assertIsNone(owner._safety_error)
        self.assertEqual(owner.handoff_receipt('handoff')['state'], 'INACTIVE_CONFIRMED')

    def test_missing_local_hold_is_not_an_exact_release_receipt(self):
        loop = SignedLoop()
        token = loop.transport.begin_observation_inhibit()
        loop.transport._observation_inhibit = None  # lost local ownership bookkeeping
        self.assertNotEqual(loop.transport.observation_inhibit_status(token)['state'], 'RELEASED')


    async def test_service_read_failure_never_revives_ready_or_enables_unknown_stop(self):
        runtime, owner, service, loop, _ = active_session()
        await owner.start()
        service.failure = True
        await owner.refresh()
        self.assertEqual(owner.snapshot()['state'], 'UNKNOWN')
        self.assertFalse(owner.snapshot()['can_stop'])
        service.failure = False
        await owner.refresh()
        self.assertEqual(owner.snapshot()['state'], 'INVALIDATED')
        self.assertTrue(owner.snapshot()['can_stop'])


if __name__ == '__main__': unittest.main()
