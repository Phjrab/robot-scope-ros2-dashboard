"""Whole-result regression baseline updated for confirmed parallel cooking policy."""
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
            'MANUAL_GUIDANCE': '600bf21b4c49967fc0d1391afd45b21bf0b6c59ca38cec77f557ca75062dde6a',
            'AUTO_NAV2': 'c8337ee2e535847072ed70b20c39e158852d7d3e3b5884b77ebce8a863641617',
        }.items():
            result = recommend_routes(order=order, graph=graph, annotations=annotations(), start_node_id='START_NODE', operation_mode=mode, perception=perception)
            self.assertEqual(hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest(), expected)
