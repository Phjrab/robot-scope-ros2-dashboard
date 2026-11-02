"""Single preparation refresh integration against synthetic saved-map assets.

These checks exercise the ASGI response, real catalogue validation, and fake
observation/session transitions together. They do not contact ROS or a robot.
"""
import json
import os
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI

from robot_dashboard.api.routers.operational_navigation import router
from robot_dashboard.application.runtime import ApplicationRuntime
from test_navigation_preparation_inputs import fixture as observation_fixture
import test_operational_navigation_bundle as bundle_test


class SingleRefreshContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bundle = bundle_test.OperationalNavigationBundleTests()
        self.bundle.setUp()
        self.addCleanup(self.bundle.doCleanups)
        self.bundle.manager.select_pair(self.bundle.pair_fixture())
        _, self.observation, self.agent, _, self.session = observation_fixture()
        self.runtime = ApplicationRuntime()
        self.runtime.operational_navigation = self.bundle.manager
        self.runtime.fastlio_observation = self.observation
        self.runtime.agent = self.agent
        self.app = FastAPI()
        self.app.state.runtime = self.runtime
        self.app.include_router(router)

    async def get(self, path='/api/v1/navigation/operational-3d/preparation-inputs'):
        messages = []
        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        async def send(message):
            messages.append(message)
        async def inline_thread(func, *args):
            return func(*args)
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                 'method': 'GET', 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
                 'query_string': b'', 'root_path': '', 'headers': [(b'host', b'test')],
                 'server': ('test', 80), 'client': ('test', 1)}
        with patch('robot_dashboard.api.routers.operational_navigation.asyncio.to_thread', inline_thread):
            await self.app(scope, receive, send)
        self.assertEqual(messages[0]['status'], 200)
        result = json.loads(b''.join(m.get('body', b'') for m in messages[1:]))
        return result, messages[0]['headers']

    async def test_one_validation_per_combined_read_and_independent_status(self):
        manager = self.bundle.manager
        with patch.object(manager, '_revalidate_pair', wraps=manager._revalidate_pair) as validate:
            combined, headers = await self.get()
            self.assertEqual(validate.call_count, 1)
            self.assertIn((b'cache-control', b'no-store'), headers)
            state = combined['operational_state']
            self.assertIsNone(combined['operational_state_error'])
            self.assertEqual(combined['pair']['generation'], state['selected']['generation'])
            self.assertEqual(combined['pair']['generation'], state['pair']['generation'])
            self.assertTrue(combined['pair']['valid'])
            self.assertTrue(state['pair']['valid'])
            self.assertIsNone(state['selected']['seed_geometry'])
            self.assertFalse(state['pair']['can_start'])
            self.assertTrue(combined['evidence']['valid'])
            self.assertIsNotNone(combined['reference_pose'])
            self.assertTrue(all(not candidate['available'] for candidate in combined['candidates'].values()))
            legacy, _ = await self.get('/api/v1/navigation/operational-3d')
            self.assertEqual(validate.call_count, 2, 'independent GET must revalidate rather than reuse proof')
            self.assertEqual(legacy['selected']['generation'], state['selected']['generation'])
            self.assertTrue(legacy['pair']['valid'])

    async def test_calibration_changed_between_reads_cannot_reuse_prior_proof(self):
        manager = self.bundle.manager
        with patch.object(manager, '_revalidate_pair', wraps=manager._revalidate_pair) as validate:
            first, _ = await self.get()
            self.assertTrue(first['pair']['valid'])
            self.assertTrue(first['evidence']['valid'])
            self.bundle.calibration['evidence'] = 'changed after first request'
            self.bundle.write_calibration()
            second, _ = await self.get()
            self.assertEqual(validate.call_count, 2)
        self.assertFalse(second['pair']['valid'])
        self.assertEqual(second['evidence']['reason'], 'MAP_PAIR_INVALID')
        self.assertIsNone(second['reference_pose'])
        self.assertTrue(all(not value['available'] and value['value'] is None
                            for value in second['candidates'].values()))
        state = second['operational_state']
        self.assertTrue(state is None or state['pair']['valid'] is False)

    async def test_reference_file_tamper_with_original_mtime_is_revalidated(self):
        manager = self.bundle.manager
        with patch.object(manager, '_revalidate_pair', wraps=manager._revalidate_pair) as validate:
            first, _ = await self.get()
            self.assertTrue(first['pair']['valid'])
            path = self.bundle.pcd
            before = path.stat()
            data = bytearray(path.read_bytes())
            data[-1] ^= 1
            path.write_bytes(data)
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            second, _ = await self.get()
            self.assertEqual(validate.call_count, 2)
        self.assertFalse(second['pair']['valid'])
        self.assertIsNone(second['reference_pose'])
        self.assertTrue(all(not item['available'] for item in second['candidates'].values()))
        state = second['operational_state']
        self.assertTrue(state is None or state['pair']['valid'] is False)

    async def test_slow_validation_expires_reference_in_combined_response(self):
        manager = self.bundle.manager
        old = manager._revalidate_pair
        def slow(*args, **kwargs):
            time.sleep(1.05)
            return old(*args, **kwargs)
        with patch.object(manager, '_revalidate_pair', side_effect=slow) as validate:
            result, _ = await self.get()
        self.assertEqual(validate.call_count, 1)
        self.assertFalse(result['evidence']['valid'])
        self.assertEqual(result['evidence']['reason'], 'OBSERVATION_STALE_OR_SOURCE_INVALID')
        self.assertIsNone(result['reference_pose'])
        self.assertFalse(result['candidates']['z']['available'])

    async def test_source_transition_drops_combined_state(self):
        manager = self.bundle.manager
        old = self.agent.pointcloud_binary_snapshot
        reads = 0
        def transition():
            nonlocal reads
            reads += 1
            if reads == 2:
                self.agent.cloud['topic'] = '/changed-source'
            return old()
        with patch.object(self.agent, 'pointcloud_binary_snapshot', side_effect=transition), \
             patch.object(manager, '_revalidate_pair', wraps=manager._revalidate_pair) as validate:
            result, _ = await self.get()
        self.assertEqual(validate.call_count, 1)
        self.assertFalse(result['evidence']['valid'])
        self.assertIsNone(result['reference_pose'])
        self.assertFalse(bool(result['operational_state']), 'source transition must discard combined state')
        self.assertEqual(result['operational_state_error'], 'CONTEXT_CHANGED')

    async def test_selection_cleared_during_health_lookup_drops_combined_state(self):
        manager = self.bundle.manager
        old_health = self.agent._navigation_runtime_health_snapshot
        def clear_selection(now):
            health = old_health(now)
            manager.selected = None
            manager._selected_records = None
            return health
        with patch.object(self.agent, '_navigation_runtime_health_snapshot', side_effect=clear_selection), \
             patch.object(manager, '_revalidate_pair', wraps=manager._revalidate_pair) as validate:
            result, _ = await self.get()
        self.assertEqual(validate.call_count, 1)
        self.assertFalse(result['evidence']['valid'])
        self.assertIsNone(result['reference_pose'])
        self.assertIsNone(result['operational_state'])
        self.assertEqual(result['operational_state_error'], 'CONTEXT_CHANGED')
        self.assertTrue(all(not value['available'] for value in result['candidates'].values()))

    async def test_session_transition_discards_combined_state_then_recovers(self):
        manager = self.bundle.manager
        original_status = manager.status
        def transition():
            result = original_status()
            self.session['session_id'] = '9' * 32
            return result
        with patch.object(manager, 'status', side_effect=transition), \
             patch.object(manager, '_revalidate_pair', wraps=manager._revalidate_pair) as validate:
            result, _ = await self.get()
            self.assertEqual(validate.call_count, 1)
        self.assertEqual(result['evidence']['reason'], 'CONTEXT_CHANGED')
        self.assertIsNone(result['reference_pose'])
        self.assertIsNone(result['operational_state'])
        self.assertEqual(result['operational_state_error'], 'CONTEXT_CHANGED')
        recovered, _ = await self.get()
        self.assertIsNone(recovered['operational_state_error'])
        self.assertTrue(recovered['pair']['valid'])


if __name__ == '__main__':
    unittest.main()
