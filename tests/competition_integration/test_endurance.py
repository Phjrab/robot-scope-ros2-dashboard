"""120 seconds of software inputs, not a physical real-time performance claim."""
import unittest
from unittest.mock import patch
from dataclasses import replace

from competition_integration.harness import SoftwareHarness
from robot_dashboard.application.mission_coordinator import MissionConflict
from robot_dashboard.mission_routes.competition_native.observations import Extras


class EnduranceTests(SoftwareHarness, unittest.IsolatedAsyncioTestCase):
    async def test_1200_ticks_1000_duplicate_reconnect_reads_and_one_exit(self):
        await self.terminal()
        with patch.object(self.service.store, 'save', wraps=self.service.store.save) as saves:
            for n in range(1200):
                await self.tick(color='RED')
                # A transport reconnect does not recreate the owner. GET/read is inert.
                self.session.runtime.snapshot()
                await self.session.observe(f'reconnect-duplicate-{n:04}', self.last_packet, sample=self.last_sample)
                # Each reconnect may assign a new key; the packet remains the same.
            self.assertEqual(saves.call_count, 0)
        self.assertEqual(len(self.nav.sent), 1)
        self.assertLessEqual(len(self.session.observation_requests), 64)
        self.assertLessEqual(len(self.session.adapter.normalizer.highwater), 12)
        self.assertLess(len(self.service.data['requests']), 16)
        for _ in range(8):
            await self.tick()
            if self.session.adapter.state.phase == 'EXIT_PENDING':
                break
        self.assertEqual(len(self.nav.sent), 2)
        await self.tick()
        await self.tick(body_motion_status='MOVING', extras=Extras(departure_observed=True))
        self.clock.now += .251
        self.assertEqual(self.command()[0], (0., 0., 0.))
        await self.session.observe('endurance-stale-poll')
        self.assertEqual(self.session.adapter.state.phase, 'FAILED')
        self.assertEqual(len(self.nav.sent), 2)

    async def test_replay_after_transport_cache_eviction_cannot_issue_effect(self):
        await self.tick(front_left_status='OUTSIDE', front_right_status='OUTSIDE')
        old = self.last_packet
        for _ in range(70):
            await self.tick(front_left_status='OUTSIDE', front_right_status='OUTSIDE')
        await self.session.observe('evicted-transport-00001', old)
        self.assertEqual(self.session.adapter.state.phase, 'FAILED')
        self.assertEqual(len(self.nav.sent), 1)
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_full_intent_ledger_blocks_goal_but_never_blocks_stop(self):
        await self.terminal()
        for n in range(256 - len(self.service.data['requests'])):
            self.service.data['requests'][f'archived-intent-{n:04}'] = {'digest': 'a'*64, 'result': {}}
        self.service._save()
        for _ in range(40):
            await self.tick(color='RED')  # input path still available
        with self.assertRaisesRegex(MissionConflict, 'REQUEST_LEDGER_FULL'):
            for _ in range(8):
                await self.tick()
        self.assertEqual(len(self.nav.sent), 1)
        await self.session.stop('full-ledger-stop-0001')
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_write_failure_precedes_release_or_exit_and_closes_gate(self):
        await self.terminal()
        for _ in range(24):
            await self.tick(color='RED')
        with patch.object(self.service.store, 'save', side_effect=OSError('injected disk failure')):
            with self.assertRaisesRegex(Exception, 'AUDIT_STORAGE_UNAVAILABLE'):
                for _ in range(8):
                    await self.tick()
        self.assertEqual(len(self.nav.sent), 1)
        self.assertEqual(self.command()[0], (0., 0., 0.))

    async def test_effect_intent_is_on_disk_before_port_and_stop_does_not_wait_for_ledger(self):
        seen = []
        install = self.session.gate._install
        async def checked_install(request):
            on_disk = self.service.store.load()['requests'][request.request_id]
            self.assertIsNone(on_disk['result'])
            seen.append(request.mode)
            return await install(request)
        with patch.object(self.session.gate, '_install', side_effect=checked_install):
            await self.terminal()
        self.assertIn('HOLD', seen)
        # No user mutation may hold the STOP fence behind persistence.
        await self.service._lock.acquire()
        import asyncio
        stopping = asyncio.create_task(self.session.stop('durable-queued-stop-01'))
        await asyncio.sleep(0)
        self.assertTrue(self.session.gate.closed)
        self.assertIn(self.session.adapter.scope.mission_run_id, self.coordinator._stop_requests)
        self.assertEqual(self.command()[0], (0., 0., 0.))
        self.service._lock.release()
        await stopping
        self.assertEqual(len(self.nav.sent), 1)
