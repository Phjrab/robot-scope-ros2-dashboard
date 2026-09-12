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
            'MANUAL_GUIDANCE': '71fbe88719ac5c23f6a7c08f82ae29721a095a407c451b03301efa0a6ea1acd5',
            'AUTO_NAV2': 'bbd46f10bceafa20608135218cd3f8ce5a5e6f2cf8549bdf8316e1d46cc87107',
        }.items():
            result = recommend_routes(order=order, graph=graph, annotations=annotations(), start_node_id='START_NODE', operation_mode=mode, perception=perception)
            self.assertEqual(hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest(), expected)
