"""SOFTWARE_TEST: real observer/factory/context; only ROS observations are fixtures."""
import asyncio
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

from robot_dashboard.navigation_policy import POLICY_SCHEMA, POLICY_OBSERVER_REASONS, REQUIRED_NODES, RuntimePolicyProvider
from robot_dashboard.ros.policy_readback import RosPolicyReadback, PARAMETERS, parameter_value
from robot_dashboard.mission_routes.context import NavigationContext
from robot_dashboard.mission_routes.wiring import configure_mission_routes
from robot_dashboard.application.mission_coordinator import MissionCoordinator
from test_mission_route_integration import SyntheticNavigation
from test_spatial_routes import MapProvider


def observed():
    params = {node: {} for node in REQUIRED_NODES}
    params['/planner_server'] = {'GridBased.allow_unknown': False, 'GridBased.plugin': 'nav2_navfn_planner/NavfnPlanner'}
    for name in ('/global_costmap/global_costmap', '/local_costmap/local_costmap'):
        params[name] = {'robot_radius': .22, 'footprint_padding': .01, 'footprint': '[]', 'track_unknown_space': True}
    return {'runtime_health': {'process_generation': 123, 'runtime_instance_generation': '123:1000'},
        'policy_readback': {'schema': POLICY_SCHEMA, 'parameters': params, 'age_s': .1, 'status': 'current',
            'lifecycle': {node: 3 for node in REQUIRED_NODES}, 'authorities': {node: 'a'*48 for node in REQUIRED_NODES}, 'sequence': 1}}


class PolicyProjectionTests(unittest.TestCase):
    def setUp(self):
        self.raw = observed()
        self.provider = RuntimePolicyProvider(lambda: deepcopy(self.raw))
        self.context = NavigationContext(SyntheticNavigation(), policy_provider=self.provider, runtime_provider=lambda: self.raw)

    def test_real_readback_cannot_impersonate_enforcement(self):
        result = self.context.snapshot()
        self.assertAlmostEqual(result['robot_radius_m'], .23)
        self.assertFalse(result['runtime_policy_enforced'])
        self.assertIn('POLICY_MASK_INGESTION_UNVERIFIED', result['blocking_reasons'])
        self.assertEqual(set(result['policy_scopes'].values()), {False})

    def test_heartbeat_and_expiry_do_not_change_semantic_pin(self):
        original = self.context.snapshot()['navigation_context_revision']
        self.raw['policy_readback'].update(age_s=.2, sequence=55, checked_at='later')
        self.assertEqual(original, self.context.snapshot()['navigation_context_revision'])
        self.raw['policy_readback']['age_s'] = .751
        expired = self.context.snapshot()
        self.assertEqual(original, expired['navigation_context_revision'])
        self.assertIn('POLICY_EVIDENCE_EXPIRED', expired['blocking_reasons'])

    def test_parameter_footprint_authority_and_same_pid_restart_change_pin(self):
        for mutate in (
            lambda r: r['policy_readback']['parameters']['/planner_server'].update({'GridBased.allow_unknown': True}),
            lambda r: r['policy_readback']['parameters']['/local_costmap/local_costmap'].update(robot_radius=.3),
            lambda r: r['policy_readback']['authorities'].update({'/planner_server':'b'*48}),
            lambda r: r['runtime_health'].update(runtime_instance_generation='123:2000'),
        ):
            self.raw = observed()
            before = self.context.snapshot()['navigation_context_revision']
            mutate(self.raw)
            self.assertNotEqual(before, self.context.snapshot()['navigation_context_revision'])

    def test_missing_partial_invalid_nonfinite_and_provider_exception_fail_closed(self):
        for mutate in (
            lambda r: r.pop('policy_readback'),
            lambda r: r['policy_readback']['parameters'].pop('/controller_server'),
            lambda r: r['policy_readback'].update(age_s=float('nan')),
            lambda r: r['policy_readback']['parameters']['/global_costmap/global_costmap'].update(robot_radius=float('nan')),
            lambda r: r['policy_readback']['authorities'].update({'/planner_server': ''}),
            lambda r: r['policy_readback']['lifecycle'].update({'/controller_server': 2}),
        ):
            self.raw = observed()
            mutate(self.raw)
            self.assertFalse(self.context.snapshot()['runtime_policy_enforced'])
        self.context.policy_provider = lambda: 1 / 0
        self.assertIn('POLICY_PROVIDER_UNAVAILABLE', self.context.snapshot()['blocking_reasons'])

    def test_incomplete_readback_preserves_only_bounded_observer_diagnostics(self):
        for parameters in ({}, {'/planner_server': {}}):
            for reason in POLICY_OBSERVER_REASONS:
                with self.subTest(parameters=list(parameters), reason=reason):
                    self.raw['policy_readback'].update(parameters=parameters,
                        status='invalid', reason=reason, age_s=.25, sequence=7)
                    result = self.context.snapshot()
                    self.assertFalse(result['runtime_policy_enforced'])
                    self.assertIsNone(result['planner_config_digest'])
                    self.assertIsNone(result['footprint_revision'])
                    self.assertIsNone(result['robot_radius_m'])
                    self.assertIn('POLICY_READBACK_UNAVAILABLE', result['blocking_reasons'])
                    self.assertIn(reason, result['blocking_reasons'])
                    self.assertEqual(result['policy_evidence'], dict(status='unavailable',
                        observer_status='invalid', reason=reason, age_s=.25, sequence=7))
        # An incomplete observer cannot upgrade provider evidence by claiming current.
        self.raw['policy_readback']['status'] = 'current'
        self.assertEqual(self.context.snapshot()['policy_evidence']['status'], 'unavailable')

    def test_diagnostic_changes_do_not_change_semantic_revision(self):
        for parameters in ({}, observed()['policy_readback']['parameters']):
            self.raw['policy_readback'].update(parameters=parameters,
                status='invalid', reason='POLICY_READBACK_TIMEOUT')
            before = self.context.snapshot()['navigation_context_revision']
            self.raw['policy_readback'].update(status='stale', reason='PARAMETERS_CHANGED',
                age_s=1.5, sequence=99)
            after = self.context.snapshot()
            self.assertEqual(before, after['navigation_context_revision'])
            self.assertFalse(after['runtime_policy_enforced'])
            self.assertIn('PARAMETERS_CHANGED', after['blocking_reasons'])

    def test_malformed_diagnostics_never_export_raw_text_or_nonfinite_values(self):
        for parameters in ({}, observed()['policy_readback']['parameters']):
            for age, sequence, status, reason in (
                (float('nan'), True, ['invalid'], {'secret': '/private/path'}),
                (float('inf'), -1, '/private/path', '/private/path' * 1000),
                (-.1, 1.5, None, ['unexpected']),
                (True, 2**64, {}, 123),
                (2**4096, '1', 123, ''),
            ):
                self.raw['policy_readback'].update(parameters=parameters, age_s=age,
                    sequence=sequence, status=status, reason=reason)
                evidence = self.context.snapshot()['policy_evidence']
                self.assertEqual(evidence, dict(status='unavailable' if not parameters else 'invalid',
                    observer_status='unavailable', reason='POLICY_READBACK_FAILED',
                    age_s=None, sequence=None))

    def test_unrecognized_schema_and_provider_failure_remain_generic(self):
        self.raw['policy_readback'].update(schema='unknown', reason='POLICY_READBACK_TIMEOUT')
        self.assertEqual(self.provider()['evidence'], {'status': 'unavailable'})
        self.assertEqual(RuntimePolicyProvider(lambda: 1 / 0)()['evidence'], {'status': 'unavailable'})

    def test_explicit_legacy_provider_heartbeat_ignored(self):
        p = dict(runtime_policy_enforced=True, planner_config_digest='a'*64, footprint_revision='b'*64, robot_radius_m=.25)
        self.context.policy_provider = lambda: p
        before = self.context.snapshot()['navigation_context_revision']
        p.update(heartbeat=99, observed_at='now')
        self.assertEqual(before, self.context.snapshot()['navigation_context_revision'])
        p['runtime_policy_enforced'] = False
        self.assertNotEqual(before, self.context.snapshot()['navigation_context_revision'])


class ReadbackTransportTests(unittest.TestCase):
    def setUp(self):
        self.clock = [10.0]
        self.gids = {node: 'a'*48 for node in REQUIRED_NODES}
        self.ready, self.done = True, True
        self.futures, self.requests = [], []
        owner = self
        class Future:
            def __init__(self, value): self.value, self.cancelled = value, False
            def done(self): return owner.done or self.cancelled
            def result(self): return self.value
            def cancel(self): self.cancelled = True
        class Client:
            def __init__(self, value): self.value = value
            def service_is_ready(self): return owner.ready
            def call_async(self, request):
                owner.requests.append(request)
                f = Future(self.value); owner.futures.append(f); return f
        self.observer = RosPolicyReadback(NS(), clock=lambda: self.clock[0])
        self.observer._authorities = lambda: dict(self.gids)
        self.observer._param_type = NS(Request=NS)
        self.observer._state_type = NS(Request=NS)
        self.observer._clients = {node: (Client(NS(values=[NS(type=0) for _ in PARAMETERS[node]])), Client(NS(current_state=NS(id=3)))) for node in REQUIRED_NODES}

    def test_bounded_async_fixed_readback_and_expiry(self):
        self.observer.tick()
        self.assertEqual(len(self.requests), 10)
        self.assertEqual(self.observer.snapshot()['status'], 'unavailable')
        self.clock[0] += .25
        self.observer.tick()
        r = self.observer.snapshot()
        self.assertEqual(r['status'], 'current')
        self.assertEqual(set(r['parameters']), REQUIRED_NODES)
        self.clock[0] += .51
        self.assertEqual(self.observer.snapshot()['status'], 'stale')
        self.assertEqual(len(self.requests), 10)  # GET never schedules ROS

    def test_source_change_event_timeout_and_partial_reply_invalidate(self):
        for reason in ('source','event','timeout','partial'):
            self.setUp()
            self.observer.tick()
            if reason == 'source': self.gids['/planner_server'] = 'b'*48
            if reason == 'event': self.observer._on_event(NS(node='/planner_server'))
            if reason == 'timeout': self.clock[0] += .501; self.done = False
            if reason == 'partial': self.futures[0].value.values = []
            self.observer.tick()
            self.assertEqual(self.observer.snapshot()['status'], 'unavailable')
            self.assertEqual(self.observer.snapshot()['reason'], {
                'source': 'POLICY_SOURCE_CHANGED_DURING_READBACK',
                'event': 'POLICY_SOURCE_CHANGED_DURING_READBACK', 'timeout': 'POLICY_READBACK_TIMEOUT',
                'partial': 'POLICY_PARTIAL_READBACK'}[reason])
            self.assertIsNone(self.observer._batch)
            if reason == 'timeout': self.assertTrue(all(f.cancelled for f in self.futures))

    def test_decode_preserves_false_not_set_and_rejects_oversize(self):
        self.assertIs(parameter_value(NS(type=1,bool_value=False)), False)
        self.assertIsNone(parameter_value(NS(type=0)))
        for value in (NS(type=4,string_value='x'*513), NS(type=8,double_array_value=[float('nan')]), NS(type=9,string_array_value=['x']*65)):
            with self.assertRaises(ValueError): parameter_value(value)

    def test_humble_endpoint_gid_graph_shape_and_duplicates(self):
        infos = [NS(node_namespace=name.rsplit('/',1)[0] or '/', node_name=name.rsplit('/',1)[1], endpoint_gid=bytes([1])*24) for name in REQUIRED_NODES]
        observer = RosPolicyReadback(NS(get_publishers_info_by_topic=lambda topic: infos))
        self.assertEqual(set(observer._authorities()), REQUIRED_NODES)
        infos.append(infos[0])
        with self.assertRaisesRegex(ValueError, 'NOT_UNIQUE'): observer._authorities()

    def test_authority_restart_invalidates_cache_before_next_reply(self):
        self.observer.tick(); self.observer.tick()
        self.assertEqual(self.observer.snapshot()['status'],'current')
        self.gids['/planner_server'] = 'b'*48
        self.observer.tick()
        current = self.observer.snapshot()
        self.assertEqual(current['status'],'invalid')
        self.assertEqual(current['authorities']['/planner_server'],'b'*48)


class ProductionFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_configure_uses_live_observer_cache_without_fixture_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            nav, maps, raw = SyntheticNavigation(), MapProvider(), observed()
            mission = MissionCoordinator(nav, maps, root/'legacy')
            runtime = NS(mission=mission, navigation=nav, saved_maps=maps, spatial_routes=NS(), slam=None,
                agent=NS(navigation_runtime_snapshot=lambda: deepcopy(raw)), pipeline_coordination_lock=asyncio.Lock())
            configure_mission_routes(runtime, root/'plans')
            self.assertIsInstance(runtime.mission_routes.context.policy_provider, RuntimePolicyProvider)
            self.assertFalse(runtime.mission_routes.planner.enabled)
            report = runtime.mission_routes.context.snapshot()
            self.assertIsNotNone(report['planner_config_digest'])
            self.assertIn('POLICY_MASK_INGESTION_UNVERIFIED', report['blocking_reasons'])
            raw['policy_readback'].update(parameters={}, status='unavailable',
                reason='POLICY_SERVICES_UNAVAILABLE', age_s=None, sequence=0)
            report = runtime.mission_routes.context.snapshot()
            self.assertFalse(report['runtime_policy_enforced'])
            self.assertIn('POLICY_SERVICES_UNAVAILABLE', report['blocking_reasons'])
            self.assertEqual(report['policy_evidence']['reason'], 'POLICY_SERVICES_UNAVAILABLE')
            self.assertEqual(report['policy_evidence']['status'], 'unavailable')
            self.assertEqual(nav.sent, [])
            await mission.close()
