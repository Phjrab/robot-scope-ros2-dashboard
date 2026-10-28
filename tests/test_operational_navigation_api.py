"""Actual ASGI transport contracts; no ROS, socket, service, or robot use."""
from __future__ import annotations

import asyncio
import copy
import json
import threading
from types import SimpleNamespace
import unittest

from fastapi import FastAPI

from robot_dashboard.api.routers.missions import router as missions_router
from robot_dashboard.api.routers.operational_navigation import router as operational_router
from robot_dashboard.application.mission_coordinator import MissionConflict
from robot_dashboard.application.navigation_coordinator import NavigationCoordinator
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.competition import CompetitionConflict
from robot_dashboard.navigation_dispatch import OperatorDispatchRejected
from robot_dashboard.ros.navigation_gateway import NavigationRosGateway


URL = '/api/v1/navigation/operational-3d'
MISSION_ID = 'a' * 32
GREEN = f'/api/v1/missions/{MISSION_ID}/operator-test-green'
ENABLE = f'/api/v1/missions/{MISSION_ID}/operator-test-enable'


def selection():
    return {'map_id': 'a' * 24, 'map_revision': 'b' * 64,
            'navigation_map_id': 'c' * 24, 'navigation_map_revision': 'd' * 64,
            'seed_pose': {'x': 1., 'y': 2., 'z': .3, 'roll': 0., 'pitch': 0., 'yaw': .1}}


def green():
    return {'request_id': 'operator-request-0001', 'confirmation_token': 'e' * 32,
            'stop_generation': 1}


class SelectionManager:
    def __init__(self):
        self.calls = []
        self.failure = None

    def status(self):
        return {'selected': None, 'calibration_available': True, 'activation': 'LEGACY_2D'}

    def select(self, body):
        if self.failure:
            raise self.failure
        self.calls.append(copy.deepcopy(body))
        return {'selected': body or None, 'activation': 'NEXT_NAVIGATION_START' if body else 'LEGACY_2D'}


class Missions:
    def __init__(self):
        self.active = False
        self.calls = []
        self.failure = None

    def blocks_navigation_goal(self):
        return self.active

    async def enable_operator_test(self, mission_id):
        if self.failure:
            raise self.failure
        self.calls.append(('enable', mission_id))
        return {'mission': {'id': mission_id}}

    async def operator_test_green(self, mission_id, **body):
        if self.failure:
            raise self.failure
        self.calls.append(('green', mission_id, body))
        return {'event': {'source': 'OPERATOR_TEST', 'kind': 'GREEN_RELEASE_REQUEST'}}


class Competition:
    def __init__(self):
        self.locked = False
        self.manual = True

    def require_unlocked(self, action):
        if self.locked:
            raise CompetitionConflict('competition locked: ' + action)

    def require_manual_mode(self):
        if not self.manual:
            raise CompetitionConflict('manual mode required')


class OperationalNavigationApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager, self.mission, self.competition = SelectionManager(), Missions(), Competition()
        self.nav_state = {'mode': 'inactive', 'localization_session': {'active': False}}
        self.nav = SimpleNamespace(start_task=None, view=lambda: copy.deepcopy(self.nav_state))
        self.mapping_busy = False
        self.runtime = ApplicationRuntime()
        self.runtime.operational_navigation = self.manager
        self.runtime.navigation = self.nav
        self.runtime.mission = self.mission
        self.runtime.competition = self.competition
        self.runtime.mapping = SimpleNamespace(activity=lambda: (self.mapping_busy, 'test transition'))
        self.runtime.agent = SimpleNamespace(_navigation_runtime_health_snapshot=lambda _: {
            'operational_3d': {'source': 'STORED_PCD_FASTLIO', 'ready': True}, 'fresh': True})
        self.app = FastAPI()
        self.app.state.runtime = self.runtime
        self.app.include_router(operational_router)
        self.app.include_router(missions_router)

    async def request(self, method, path, *, body=None, origin='http://testserver'):
        data = b'' if body is None else json.dumps(body, allow_nan=True).encode()
        headers = {'host': 'testserver', 'content-type': 'application/json', 'content-length': str(len(data))}
        if origin is not None:
            headers['origin'] = origin
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {'type': 'http.request', 'body': data, 'more_body': False}
            return {'type': 'http.disconnect'}

        status, chunks = None, bytearray()

        async def respond(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            elif message['type'] == 'http.response.body':
                chunks.extend(message.get('body', b''))

        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                 'scheme': 'http', 'method': method, 'path': path, 'raw_path': path.encode(),
                 'query_string': b'', 'root_path': '', 'server': ('testserver', 80),
                 'client': ('tests', 1), 'headers': [(k.encode(), v.encode()) for k, v in headers.items()]}
        await self.app(scope, receive, respond)
        return status, json.loads(chunks) if chunks else None

    async def test_get_status_cannot_select_or_clear_source(self):
        self.mission.active = True
        status, result = await self.request('GET', URL, origin=None)
        self.assertEqual(status, 200)
        self.assertEqual(result['runtime']['source'], 'STORED_PCD_FASTLIO')
        self.assertTrue(result['runtime_fresh'])
        self.assertEqual(self.manager.calls, [])
        self.assertEqual(self.mission.calls, [])

    async def test_same_origin_selection_and_delete_use_existing_manager(self):
        body = selection()
        status, _ = await self.request('POST', URL, body=body)
        self.assertEqual(status, 200)
        self.assertEqual(self.manager.calls, [body])
        status, result = await self.request('DELETE', URL)
        self.assertEqual(status, 200)
        self.assertEqual(self.manager.calls, [body, {}])
        self.assertIsNone(result['selected'])

    async def test_all_source_and_operator_mutations_require_same_origin(self):
        for origin in (None, 'http://attacker.invalid', 'http://testserver.attacker.invalid', 'null'):
            for method, path, body in (('POST', URL, selection()), ('DELETE', URL, None),
                                       ('POST', ENABLE, {}), ('POST', GREEN, green())):
                with self.subTest(origin=origin, path=path, method=method):
                    status, _ = await self.request(method, path, body=body, origin=origin)
                    self.assertEqual(status, 403)
        self.assertFalse(self.manager.calls)
        self.assertFalse(self.mission.calls)

    async def test_pending_start_active_mission_and_mapping_transition_block_selection_and_clear(self):
        pending = asyncio.get_running_loop().create_future()
        for condition in ('start', 'mission', 'mapping', 'navigation', 'localization'):
            self.nav.start_task = pending if condition == 'start' else None
            self.mission.active = condition == 'mission'
            self.mapping_busy = condition == 'mapping'
            self.nav_state['mode'] = 'navigation' if condition == 'navigation' else 'inactive'
            self.nav_state['localization_session']['active'] = condition == 'localization'
            for method, body in (('POST', selection()), ('DELETE', None)):
                with self.subTest(condition=condition, method=method):
                    status, _ = await self.request(method, URL, body=body)
                    self.assertEqual(status, 409)
        pending.cancel()
        self.assertFalse(self.manager.calls)

    async def test_competition_lock_blocks_source_and_operator_mutations(self):
        self.competition.locked = True
        for method, path, body in (('POST', URL, selection()), ('DELETE', URL, None),
                                   ('POST', ENABLE, {}), ('POST', GREEN, green())):
            with self.subTest(method=method, path=path):
                status, _ = await self.request(method, path, body=body)
                self.assertEqual(status, 423)
        self.assertFalse(self.manager.calls)
        self.assertFalse(self.mission.calls)

    async def test_source_selection_requires_manual_mode(self):
        self.competition.manual = False
        status, _ = await self.request('POST', URL, body=selection())
        self.assertEqual(status, 409)
        self.assertFalse(self.manager.calls)

    async def test_selection_rejects_unsupported_fields_bad_pins_and_unbounded_seed(self):
        invalid = [dict(selection(), source='GREEN'), dict(selection(), map_id='a' * 25),
                   dict(selection(), navigation_map_revision='stale')]
        for key, value in (('x', 1000.01), ('y', -1000.01), ('z', 1001.), ('roll', 4.),
                           ('pitch', 2.), ('yaw', -4.)):
            body = selection()
            body['seed_pose'][key] = value
            invalid.append(body)
        body = selection()
        body['seed_pose']['receipt'] = 'sensor-proof'
        invalid.append(body)
        for body in invalid:
            with self.subTest(body=body):
                status, _ = await self.request('POST', URL, body=body)
                self.assertEqual(status, 422)
        self.assertFalse(self.manager.calls)

    async def test_selection_requires_real_json_numbers_for_seed(self):
        for value in (True, '1.2'):
            with self.subTest(value=value):
                body = selection()
                body['seed_pose']['x'] = value
                status, _ = await self.request('POST', URL, body=body)
                self.assertEqual(status, 422)
        self.assertFalse(self.manager.calls)

    async def test_operator_test_transports_only_current_stop_request(self):
        status, _ = await self.request('POST', ENABLE, body={})
        self.assertEqual(status, 200)
        status, result = await self.request('POST', GREEN, body=green())
        self.assertEqual(status, 200)
        self.assertEqual(self.mission.calls, [('enable', MISSION_ID), ('green', MISSION_ID, green())])
        self.assertEqual(result['event']['source'], 'OPERATOR_TEST')

    async def test_operator_test_cannot_supply_sensor_receipts_sources_or_client_clock(self):
        for key, value in (('source', 'YOLO'), ('kind', 'GREEN'), ('sensor_receipt', {'GREEN': True}),
                           ('server_issued_at', 123.), ('expires_at', 999999.), ('synthetic', True),
                           ('front_feet_in_zone', True), ('localization_generation', 1)):
            with self.subTest(key=key):
                status, _ = await self.request('POST', GREEN, body={**green(), key: value})
                self.assertEqual(status, 422)
        for body in ({'source': 'OPERATOR_TEST'}, {'synthetic': True}, {'GREEN': True}):
            status, _ = await self.request('POST', ENABLE, body=body)
            self.assertEqual(status, 422)
        self.assertFalse(self.mission.calls)

    async def test_operator_test_stop_generation_and_request_tokens_are_strict(self):
        invalid = []
        missing = green()
        del missing['stop_generation']
        invalid.append(missing)
        invalid.extend({**green(), 'stop_generation': value} for value in (0, -1, True, '1', 1.1))
        invalid.extend({**green(), 'request_id': value} for value in ('short', 'a' * 81, 'bad request ' * 2))
        invalid.extend({**green(), 'confirmation_token': value} for value in ('old', 'e' * 33, 'G' * 32))
        for body in invalid:
            with self.subTest(body=body):
                status, _ = await self.request('POST', GREEN, body=body)
                self.assertEqual(status, 422)
        self.assertFalse(self.mission.calls)

    async def test_backend_conflicts_propagate_without_mutation(self):
        self.manager.failure = ValueError('REFERENCE_REVISION_CHANGED')
        status, result = await self.request('POST', URL, body=selection())
        self.assertEqual(status, 409)
        self.assertEqual(result['detail'], 'REFERENCE_REVISION_CHANGED')
        self.mission.failure = MissionConflict('CURRENT_WAIT_TEST_GREEN_REQUIRED')
        status, result = await self.request('POST', GREEN, body=green())
        self.assertEqual(status, 409)
        self.assertEqual(result['detail'], 'CURRENT_WAIT_TEST_GREEN_REQUIRED')
        self.assertFalse(self.manager.calls)
        self.assertFalse(self.mission.calls)


class GuardedNavigationPortTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_navigation_coordinator_forwards_final_guard_to_guarded_agent_only(self):
        called, checks = [], []

        def guarded(**kwargs):
            checks.append('guarded_consumer')
            kwargs['dispatch_guard']()
            called.append(kwargs)

        def unguarded(**kwargs):
            checks.append('legacy_consumer')
            called.append(kwargs)

        agent = SimpleNamespace(navigation_send_guarded_goal=guarded, navigation_send_goal=unguarded)
        jobs = SimpleNamespace(on_terminal=None, validate_active_pose=lambda **kwargs: {
            key: kwargs[key] for key in ('x', 'y', 'yaw')})
        mapping = SimpleNamespace(activity=lambda: (False, ''), pipeline_state=lambda: 'running')
        nav = NavigationCoordinator(agent, jobs, mapping, object(), coordination_lock=asyncio.Lock(),
                                    require_lifecycle_idle=lambda: None)
        nav.require_runtime_capability = lambda capability: None
        def guard():
            checks.append('final_guard')
        await nav._send_goal_locked(map_id='a' * 24, map_revision='b' * 64,
                                    x=1., y=2., yaw=.3, dispatch_guard=guard)
        self.assertEqual(checks, ['guarded_consumer', 'final_guard'])
        self.assertIs(called[0]['dispatch_guard'], guard)
        checks.clear()
        await nav._send_goal_locked(map_id='a' * 24, map_revision='b' * 64, x=1., y=2., yaw=.3)
        self.assertEqual(checks, ['legacy_consumer'])
        self.assertNotIn('dispatch_guard', called[1])


class GuardedRosGatewayTests(unittest.TestCase):
    def gateway(self):
        """Use the real final ROS adapter with a recording action client."""
        sent, stops = [], []
        gateway = NavigationRosGateway(SimpleNamespace(operation_lock=threading.RLock()),
            node_getter=lambda: None, tick=lambda *_: None, graph_getter=lambda: {})
        gateway._navigation['active'] = True
        gateway._navigation['map'] = {'id': 'a' * 24, 'revision': 'b' * 64}
        gateway._navigation['localization'] = {'state': 'localized'}
        gateway._navigation['goal'] = {'state': 'idle', 'goal_id': None}
        gateway._navigation_sensor_interlock_reason = lambda *_args, **_kwargs: None
        gateway._navigation_issue_stop = lambda reason: stops.append(reason)
        gateway._new_stamped_pose = lambda *_: SimpleNamespace(
            header=SimpleNamespace(), pose=SimpleNamespace(pose=SimpleNamespace()))
        gateway._navigation_action_type = SimpleNamespace(Goal=lambda: SimpleNamespace(
            pose=SimpleNamespace(header=None, pose=None)))

        def send_goal_async(message, *, feedback_callback):
            sent.append(message)
            return SimpleNamespace(add_done_callback=lambda _: None)

        gateway._navigation_action_client = SimpleNamespace(server_is_ready=lambda: True,
                                                           send_goal_async=send_goal_async)
        gateway.runtime_snapshot = lambda: copy.deepcopy(gateway._navigation)
        return gateway, sent, stops

    def test_first_guard_rejection_preserves_known_not_sent_receipt(self):
        gateway, sent, stops = self.gateway()
        rejected = OperatorDispatchRejected('stop requested')

        def guard():
            raise rejected

        with self.assertRaises(OperatorDispatchRejected) as caught:
            gateway.send_goal(map_id='a' * 24, map_revision='b' * 64,
                              x=1., y=2., yaw=.3, dispatch_guard=guard)
        self.assertIs(caught.exception, rejected)
        self.assertFalse(sent)
        self.assertFalse(stops)
        self.assertEqual(gateway._navigation['goal']['state'], 'idle')

    def test_second_guard_rejection_stays_known_not_sent_and_uses_existing_stop(self):
        gateway, sent, stops = self.gateway()
        rejected = OperatorDispatchRejected('permission expired')
        checks = []

        def guard():
            checks.append('guard')
            if len(checks) == 2:
                raise rejected

        with self.assertRaises(OperatorDispatchRejected) as caught:
            gateway.send_goal(map_id='a' * 24, map_revision='b' * 64,
                              x=1., y=2., yaw=.3, dispatch_guard=guard)
        self.assertIs(caught.exception, rejected)
        self.assertEqual(checks, ['guard', 'guard'])
        self.assertFalse(sent)
        self.assertEqual(len(stops), 1)
        self.assertEqual(gateway._navigation['goal']['state'], 'failed')

    def test_two_successful_final_checks_submit_one_goal(self):
        gateway, sent, stops = self.gateway()
        checks = []
        gateway.send_goal(map_id='a' * 24, map_revision='b' * 64,
                          x=1., y=2., yaw=.3, dispatch_guard=lambda: checks.append('guard'))
        self.assertEqual(checks, ['guard', 'guard'])
        self.assertEqual(len(sent), 1)
        self.assertFalse(stops)


if __name__ == '__main__':
    unittest.main()
