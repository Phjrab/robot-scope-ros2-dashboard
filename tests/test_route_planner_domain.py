import copy
import unittest

from robot_dashboard.route_planner.catalog import competition_catalog
from robot_dashboard.route_planner.graph import RouteGraphError, normalize_graph
from robot_dashboard.route_planner.guidance import project_guidance
from robot_dashboard.route_planner.optimizer import RoutePlanningError, recommend_routes
from robot_dashboard.route_planner.orders import OrderValidationError, normalize_order
from robot_dashboard.route_planner.perception import (
    MockRoutePerceptionProvider,
    PerceptionContractError,
    normalize_perception_snapshot,
    requirement_states,
)
from route_planner_fixtures import (
    ANNOTATION_REVISION,
    Geometry,
    annotations,
    graph_payload,
    order_payload,
    ready_perception,
)


class OrderSheetTests(unittest.TestCase):
    def test_catalog_is_fixed_and_uses_underpass_as_the_single_semantic(self):
        catalog = competition_catalog()
        self.assertEqual(catalog["capacity"], 5)
        self.assertEqual(catalog["production"], {"seconds_per_item": 20, "policy": "ORDER_SEQUENCE_20S"})
        self.assertEqual(catalog["underpass_semantic"], "UNDERPASS")
        self.assertEqual(catalog["zones"][3]["restaurant_id"], None)

    def test_low_order_derives_quantity_difficulty_and_ready_times(self):
        value = normalize_order(order_payload(), identifier_factory=lambda: "f" * 32)
        self.assertEqual(value["difficulty"], "LOW")
        self.assertEqual(value["total_quantity"], 3)
        self.assertEqual([line["ready_at_s"] for line in value["lines"]], [40, 60])
        self.assertEqual(len(value["revision"]), 64)

    def test_medium_and_high_are_derived(self):
        medium = order_payload(); medium["lines"][1]["quantity"] = 2
        self.assertEqual(normalize_order(medium)["difficulty"], "MEDIUM")
        high = order_payload(); high["lines"] = [
            {"sequence": 1, "restaurant_id": "HANSOT", "menu_id": "CHICKEN_MAYO", "quantity": 2},
            {"sequence": 2, "restaurant_id": "EDIYA", "menu_id": "AMERICANO", "quantity": 2},
            {"sequence": 3, "restaurant_id": "DOMINO", "menu_id": "CHEESE_PIZZA", "quantity": 1},
        ]; high["destination_id"] = "GTX_SITE"
        self.assertEqual(normalize_order(high)["difficulty"], "HIGH")

    def test_rejects_derived_field_forgery_and_bad_rules(self):
        for mutate in (
            lambda value: value.update(difficulty="LOW"),
            lambda value: value.update(destination_id="UNKNOWN"),
            lambda value: value["lines"].__setitem__(1, {"sequence": 2, "restaurant_id": "HANSOT", "menu_id": "CHICKEN_MAYO", "quantity": 1}),
            lambda value: value["lines"].__setitem__(0, {"sequence": 1, "restaurant_id": "HANSOT", "menu_id": "AMERICANO", "quantity": 2}),
            lambda value: value["lines"].__setitem__(1, {"sequence": 3, "restaurant_id": "EDIYA", "menu_id": "AMERICANO", "quantity": 1}),
            lambda value: value["lines"][0].update(quantity=5),
        ):
            payload = copy.deepcopy(order_payload()); mutate(payload)
            with self.subTest(payload=payload), self.assertRaises(OrderValidationError):
                normalize_order(payload)

    def test_destination_zone_restaurant_is_rejected(self):
        payload = order_payload(); payload["destination_id"] = "WHIMOON"
        with self.assertRaisesRegex(OrderValidationError, "destination-zone"):
            normalize_order(payload)


class RouteGraphTests(unittest.TestCase):
    def test_graph_is_exactly_pinned_and_revision_is_deterministic(self):
        first = normalize_graph(graph_payload(), annotations=annotations(), geometry=Geometry())
        second = normalize_graph(graph_payload(), annotations=annotations(), geometry=Geometry())
        self.assertEqual(first["graph_revision"], second["graph_revision"])
        self.assertEqual(first["annotation_revision"], ANNOTATION_REVISION)
        self.assertEqual({edge["type"] for edge in first["edges"]} & {"OVERPASS"}, set())

    def test_missing_annotation_duplicate_and_out_of_map_are_rejected(self):
        bad = graph_payload(); bad["nodes"][0]["annotation_id"] = "9" * 24
        with self.assertRaises(RouteGraphError): normalize_graph(bad, annotations=annotations(), geometry=Geometry())
        bad = graph_payload(); bad["nodes"][1]["id"] = bad["nodes"][0]["id"]
        with self.assertRaises(RouteGraphError): normalize_graph(bad, annotations=annotations(), geometry=Geometry())
        bad = graph_payload(); bad["edges"][0]["polyline"][0]["x"] = 99.0
        with self.assertRaises(RouteGraphError): normalize_graph(bad, annotations=annotations(), geometry=Geometry())

    def test_unknown_fields_and_overpass_edge_type_are_rejected(self):
        bad = graph_payload(); bad["filesystem_path"] = "/tmp/map"
        with self.assertRaises(RouteGraphError): normalize_graph(bad, annotations=annotations(), geometry=Geometry())
        bad = graph_payload(); bad["edges"][0]["type"] = "OVERPASS"
        with self.assertRaises(RouteGraphError): normalize_graph(bad, annotations=annotations(), geometry=Geometry())


class OptimizerAndGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.order = normalize_order(order_payload(), identifier_factory=lambda: "f" * 32)
        self.graph = normalize_graph(graph_payload(), annotations=annotations(), geometry=Geometry())
        snapshot = normalize_perception_snapshot(ready_perception(), now_ns=1_000_000_000)
        self.perception = snapshot

    def test_recommendations_are_bounded_deterministic_and_have_score_breakdown(self):
        first = recommend_routes(order=self.order, graph=self.graph, annotations=annotations(), start_node_id="START_NODE", operation_mode="AUTO_NAV2", perception=self.perception)
        second = recommend_routes(order=self.order, graph=self.graph, annotations=annotations(), start_node_id="START_NODE", operation_mode="AUTO_NAV2", perception=self.perception)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 3)
        self.assertEqual({profile for route in first for profile in route["profiles"]}, {"BALANCED", "FASTEST", "SAFEST"})
        self.assertTrue(all({"distance_m", "travel_time_s", "food_wait_s", "signal_wait_s", "risk_score", "eta_s"} <= set(route["metrics"]) for route in first))

    def test_safest_avoids_high_risk_direct_edge(self):
        routes = recommend_routes(order=self.order, graph=self.graph, annotations=annotations(), start_node_id="START_NODE", operation_mode="AUTO_NAV2", perception=self.perception)
        safest = next(route for route in routes if "SAFEST" in route["profiles"])
        self.assertIn("SAFE_HOLD", safest["node_ids"])

    def test_unknown_perception_blocks_auto_special_edge_but_never_manual_guidance(self):
        stale = MockRoutePerceptionProvider(now_ns=lambda: 5_000_000_000).snapshot()
        routes = recommend_routes(order=self.order, graph=self.graph, annotations=annotations(), start_node_id="START_NODE", operation_mode="AUTO_NAV2", perception=stale)
        self.assertTrue(any(not route["executable"] for route in routes if any(segment["requirements"] for segment in route["segments"])))
        manual = recommend_routes(order=self.order, graph=self.graph, annotations=annotations(), start_node_id="START_NODE", operation_mode="MANUAL_GUIDANCE", perception=stale)
        self.assertTrue(all(route["executable"] is False for route in manual))

    def test_missing_start_and_disconnected_graph_fail_with_bounded_reasons(self):
        with self.assertRaises(RoutePlanningError) as raised:
            recommend_routes(order=self.order, graph=self.graph, annotations=annotations(), start_node_id="MISSING", operation_mode="AUTO_NAV2", perception=self.perception)
        self.assertEqual(raised.exception.reason, "NO_START_NODE")
        disconnected = copy.deepcopy(self.graph)
        disconnected["edges"] = [edge for edge in disconnected["edges"] if "COEX" not in edge["id"]]
        with self.assertRaises(RoutePlanningError) as raised:
            recommend_routes(order=self.order, graph=disconnected, annotations=annotations(), start_node_id="START_NODE", operation_mode="AUTO_NAV2", perception=self.perception)
        self.assertEqual(raised.exception.reason, "GRAPH_DISCONNECTED")

    def test_guidance_projects_progress_off_route_and_missing_pose_without_control(self):
        route = recommend_routes(order=self.order, graph=self.graph, annotations=annotations(), start_node_id="START_NODE", operation_mode="MANUAL_GUIDANCE", perception=self.perception)[0]
        near = project_guidance(route, {"x": 0.2, "y": 0.0}, self.perception)
        self.assertTrue(near["active"])
        self.assertGreater(near["remaining_distance_m"], 0)
        self.assertFalse(near["control_authority"])
        off = project_guidance(route, {"x": 0.2, "y": -3.0}, self.perception)
        self.assertTrue(off["off_route"])
        self.assertTrue(off["replan_available"])
        paused = project_guidance(route, None, self.perception)
        self.assertTrue(paused["paused"])

    def test_perception_freshness_projects_requirements_only(self):
        states = requirement_states(self.perception)
        self.assertEqual(states["TRAFFIC_GREEN"], "READY")
        self.assertEqual(states["PEDESTRIAN_CLEAR"], "READY")
        self.assertEqual(states["SPECIAL_GAIT"], "OPERATOR")

    def test_perception_entries_are_strict_typed_and_finite(self):
        value = ready_perception()
        value["traffic"][0]["raw_command"] = "go"
        with self.assertRaises(PerceptionContractError):
            normalize_perception_snapshot(value, now_ns=1_000_000_000)
        value = ready_perception()
        value["crosswalks"][0]["lateral_offset_m"] = float("nan")
        with self.assertRaises(PerceptionContractError):
            normalize_perception_snapshot(value, now_ns=1_000_000_000)


if __name__ == "__main__":
    unittest.main()
