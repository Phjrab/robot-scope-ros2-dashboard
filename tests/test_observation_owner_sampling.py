"""Real-executor regressions; synthetic owners, no device or ROS calls."""
import asyncio
import json
import threading
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from robot_dashboard.api.routers.operational_navigation import router

from test_observation_bridge_session import active_session


class ObservationOwnerSamplingTests(unittest.IsolatedAsyncioTestCase):
    async def test_event_loop_read_lock_does_not_invalidate_start_or_refresh(self):
        runtime, owner, service, link, _ = active_session()
        # An event-loop reader holds the reentrant state lock, without changing
        # ownership. Moving the ownership copy to another thread turns this
        # read into a false unknown and used to reject/latch the session.
        with runtime.navigation._state_lock:
            state = await owner.start()
            self.assertEqual(state['state'], 'READY', state)
            current = await owner.refresh()
        self.assertEqual(current['state'], 'READY', current)
        self.assertEqual(current['bridge_guard']['state'], 'HELD')
        self.assertFalse(current['map_registration_applied'])
        stopped = await owner.stop(state['session_id'])
        self.assertEqual(stopped['state'], 'STOPPED')
        self.assertEqual(service.calls, ['start', 'stop'])
        self.assertTrue(all(p['type'] == 'observation_inhibit' for p in link.sent))

    async def test_real_foreign_lock_contention_still_latches_and_allows_cleanup(self):
        runtime, owner, service, _, _ = active_session()
        state = await owner.start()
        owner.reserve_handoff_receipt('h', state['session_id'], state['started_monotonic_s'])
        entered, release = threading.Event(), threading.Event()

        def hold():
            with runtime.navigation._state_lock:
                entered.set()
                if not release.wait(5):
                    raise AssertionError('test lock release timed out')

        worker = threading.Thread(target=hold)
        worker.start()
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            current = await owner.refresh()
            self.assertEqual(current['state'], 'INVALIDATED')
            self.assertTrue(current['can_stop'])
        finally:
            release.set()
            await asyncio.to_thread(worker.join, 2)
        self.assertEqual((await owner.refresh())['state'], 'INVALIDATED')
        self.assertEqual(current['owner_failure']['unknown_components'], ['navigation'])
        self.assertEqual(current['owner_failure']['unknown_reasons'], {'navigation': 'OWNER_LOCK_BUSY'})
        failure = owner.snapshot()['owner_failure']
        failure['unknown_components'].clear()
        failure['unknown_reasons'].clear()
        self.assertEqual(owner.snapshot()['owner_failure'], current['owner_failure'])
        with self.assertRaises(ValueError):
            owner.reserve_handoff_receipt('new', state['session_id'], state['started_monotonic_s'])
        self.assertEqual((await owner.stop(state['session_id']))['state'], 'STOPPED')
        self.assertEqual(owner.handoff_receipt('h')['state'], 'OUTCOME_UNKNOWN')
        self.assertEqual(service.calls, ['start', 'stop'])

    async def test_observed_busy_and_unreadable_owners_keep_first_failure(self):
        for mode in ('busy', 'unreadable'):
            with self.subTest(mode=mode):
                runtime, owner, service, _, _ = active_session()
                state = await owner.start()
                lock = runtime.navigation._state_lock
                if mode == 'busy':
                    runtime.navigation._start['pending'] = True
                else:
                    runtime.navigation._state_lock = None
                current = await owner.refresh()
                self.assertEqual(current['state'], 'INVALIDATED')
                diagnostic = current['owner_failure']
                self.assertEqual(diagnostic['busy_components'], ['navigation'] if mode == 'busy' else [])
                if mode == 'unreadable':
                    self.assertEqual(diagnostic['unknown_reasons'], {'navigation': 'OWNER_READ_UNAVAILABLE'})
                runtime.navigation._start['pending'] = False
                runtime.navigation._state_lock = lock
                current = await owner.refresh()
                self.assertEqual(current['state'], 'INVALIDATED')
                self.assertEqual(current['owner_failure'], diagnostic)
                await owner.stop(state['session_id'])
                restarted = await owner.start()
                self.assertEqual(restarted['state'], 'READY')
                self.assertIsNone(restarted['owner_failure'])
                await owner.stop(restarted['session_id'])

    async def test_preparation_advisory_reads_owners_on_event_loop(self):
        runtime, owner, _, _, _ = active_session()
        await owner.refresh()
        runtime.operational_navigation = object()
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router)
        messages = []

        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}

        async def send(message):
            messages.append(message)

        path = '/api/v1/navigation/operational-3d/preparation-inputs'
        scope = dict(type='http', asgi={'version': '3.0'}, http_version='1.1', method='GET',
                     scheme='http', path=path, raw_path=path.encode(), query_string=b'',
                     root_path='', headers=[(b'host', b'test')], server=('test', 80), client=('test', 1))
        # This regression isolates admission display; map/evidence collection
        # has its own integration suite. The ASGI route and executor are real.
        with runtime.navigation._state_lock, patch(
                'robot_dashboard.application.navigation_preparation_inputs.preparation_inputs', return_value={}):
            await app(scope, receive, send)
        self.assertEqual(messages[0]['status'], 200)
        result = json.loads(b''.join(m.get('body', b'') for m in messages[1:]))
        self.assertEqual(result['start_blockers']['items'], [])


if __name__ == '__main__':
    unittest.main()
