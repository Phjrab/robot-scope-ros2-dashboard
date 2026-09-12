"""Golden whole-result digests captured from 78224f4 before provider extraction."""
import hashlib
import json
import unittest
from route_planner_fixtures import Geometry, annotations, graph_payload, order_payload, ready_perception
from robot_dashboard.route_planner.graph import normalize_graph
from robot_dashboard.route_planner.optimizer import recommend_routes
from robot_dashboard.route_planner.orders import normalize_order
from robot_dashboard.route_planner.perception import normalize_perception_snapshot


class SavedProviderGoldenTests(unittest.TestCase):
    def test_both_existing_modes_match_baseline_complete_route_results(self):
        order = normalize_order(order_payload(), identifier_factory=lambda: 'f' * 32)
        graph = normalize_graph(graph_payload(), annotations=annotations(), geometry=Geometry())
        perception = normalize_perception_snapshot(ready_perception(), now_ns=1_000_000_000)
        for mode, expected in {
            'MANUAL_GUIDANCE': 'df544dffec64a74bdccd866eef79367f256341f8cb147e8c67c480f0ce226614',
            'AUTO_NAV2': 'cb5a0b39abf3321a8c7ab901736fd0e86742c24ebad485aef805181b150370ea',
        }.items():
            result = recommend_routes(order=order, graph=graph, annotations=annotations(), start_node_id='START_NODE', operation_mode=mode, perception=perception)
            self.assertEqual(hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest(), expected)
