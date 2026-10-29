from types import SimpleNamespace as NS
import unittest

from robot_dashboard.ros.policy_parameters import complete_parameters, declaration_names
from robot_dashboard.ros.policy_readback import PARAMETERS
from test_policy_readback_diagnostics import Harness


class DeclarationTests(unittest.TestCase):
    def test_inactive_plugins_are_explicitly_not_applicable(self):
        values, status, missing = complete_parameters('/local_costmap/local_costmap',
            ('plugins', 'filters', 'static_layer.plugin', 'keepout_filter.enabled', 'robot_radius'),
            {'plugins': ['obstacle_layer', 'inflation_layer'], 'filters': [], 'robot_radius': .22})
        self.assertEqual(missing, [])
        self.assertIsNone(values['static_layer.plugin'])
        self.assertEqual(status['static_layer.plugin'], 'NOT_APPLICABLE')
        self.assertEqual(status['keepout_filter.enabled'], 'NOT_APPLICABLE')

    def test_active_missing_unknown_applicability_and_required_not_set_fail(self):
        for observed in ({'plugins': ['static_layer'], 'filters': []}, {},
                         {'plugins': [], 'filters': [], 'robot_radius': None}):
            _, _, missing = complete_parameters('/local_costmap/local_costmap',
                ('static_layer.plugin', 'robot_radius'), observed)
            self.assertIn('robot_radius', missing)
            if observed.get('plugins') != []:
                self.assertIn('static_layer.plugin', missing)
        _, status, missing = complete_parameters('/controller_server',
            ('progress_checker.required_movement_angle',),
            {'progress_checker.plugin': 'nav2_controller::SimpleProgressChecker'})
        self.assertFalse(missing)
        self.assertEqual(status['progress_checker.required_movement_angle'], 'NOT_APPLICABLE')

    def test_declaration_response_is_bounded(self):
        for names in (['x'] * 2, ['x' * 513], ['p' + str(i) for i in range(4097)]):
            with self.assertRaises(ValueError):
                declaration_names(NS(result=NS(names=names)))

    def test_list_before_get_filters_undeclared_and_reuses_incarnation_cache(self):
        h = Harness()
        observer = h.observer
        observer._declarations = None
        observer._list_type = NS(Request=NS)
        calls = []
        class Future:
            def __init__(self, name): self.name = name
            def done(self): return True
            def result(self): return NS(result=NS(names=list(PARAMETERS[self.name])[:-1]))
        class Client:
            def __init__(self, name): self.name = name
            def service_is_ready(self): return True
            def call_async(self, request):
                calls.append((self.name, request))
                return Future(self.name)
        observer._list_clients = {name: Client(name) for name in PARAMETERS}
        observer.tick()
        self.assertEqual(len(calls), 5)
        self.assertEqual(h.requests, [])
        h.now += .25
        observer.tick()
        self.assertEqual(len(h.requests), 10)
        for name, names in observer._request_names.items():
            self.assertEqual(names, list(PARAMETERS[name])[:-1])
        # No declaration refresh for the same event epoch / authority set.
        self.assertTrue(observer._ensure_declarations(observer._authorities(), h.now))
        self.assertEqual(len(calls), 5)

    def test_partial_costmap_retains_controller_evidence_but_policy_invalid(self):
        h = Harness()
        h.observer.tick()
        for f in h.futures:
            f.complete = True
        h.futures[6].result = lambda: NS(values=[])
        h.now += .25
        h.observer.tick()
        value = h.observer.snapshot()
        self.assertEqual(value['status'], 'invalid')
        self.assertEqual(value['node_status']['/controller_server'], 'current')
        self.assertEqual(value['node_status']['/global_costmap/global_costmap'], 'invalid')
        self.assertIn('FollowPath.plugin', value['parameters']['/controller_server'])
        self.assertEqual(value['reason'], 'POLICY_PARTIAL_READBACK')
