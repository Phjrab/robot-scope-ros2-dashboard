import ast
import unittest
from pathlib import Path

from robot_dashboard.application.runtime import ApplicationRuntime


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "robot_dashboard" / "api" / "routers" / "route_planner.py"
APP = ROOT / "robot_dashboard" / "app.py"
MODELS = ROOT / "robot_dashboard" / "api" / "models.py"


def routes():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    result = set()
    for function in (node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))):
        for decorator in function.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.args and isinstance(decorator.args[0], ast.Constant):
                result.add((decorator.func.attr, decorator.args[0].value))
    return result


class RoutePlannerApiContractTests(unittest.TestCase):
    def test_exact_bounded_routes_are_registered(self):
        self.assertEqual(routes(), {
            ("get", "/api/v1/route-planner"),
            ("get", "/api/v1/route-planner/catalog"),
            ("post", "/api/v1/route-planner/orders"),
            ("patch", "/api/v1/route-planner/orders/{order_id}"),
            ("get", "/api/v1/route-planner/orders/{order_id}"),
            ("get", "/api/v1/route-planner/graph"),
            ("put", "/api/v1/route-planner/graph"),
            ("post", "/api/v1/route-planner/recommendations"),
            ("get", "/api/v1/route-planner/recommendations/{route_id}"),
            ("post", "/api/v1/route-planner/recommendations/{route_id}/select"),
            ("post", "/api/v1/route-planner/guidance/start"),
            ("post", "/api/v1/route-planner/guidance/stop"),
            ("post", "/api/v1/route-planner/guidance/pickup"),
            ("post", "/api/v1/route-planner/guidance/dropoff"),
            ("post", "/api/v1/route-planner/routes/{route_id}/preview"),
            ("post", "/api/v1/route-planner/routes/{route_id}/export-mission"),
        })

    def test_mutations_share_same_origin_and_competition_lock_gate(self):
        source = ROUTER.read_text(encoding="utf-8")
        self.assertIn("require_same_origin(request)", source)
        self.assertIn("require_competition_unlocked(runtime, action)", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("/cmd_vel", source)
        self.assertNotIn("send_annotation_goal", source)
        self.assertNotIn(".start(", source)

    def test_order_schema_forbids_derived_unknown_and_raw_execution_fields(self):
        tree = ast.parse(MODELS.read_text(encoding="utf-8"))
        classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        order = classes["RouteOrderCreateRequest"]
        fields = {node.target.id for node in order.body if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)}
        self.assertEqual(fields, {"label", "destination_id", "lines", "order_started_at", "locked"})
        self.assertTrue(all(field not in fields for field in {"difficulty", "filesystem_path", "ros_topic", "x", "y", "yaw"}))
        strict = classes["StrictRequest"]
        strict_source = ast.get_source_segment(MODELS.read_text(encoding="utf-8"), strict)
        self.assertIn('extra="forbid"', strict_source)

    def test_runtime_and_app_own_exactly_one_route_planner_coordinator(self):
        self.assertIsNone(ApplicationRuntime().route_planner)
        source = APP.read_text(encoding="utf-8")
        self.assertEqual(source.count("RUNTIME.route_planner = RoutePlannerCoordinator("), 1)
        self.assertIn("app.include_router(route_planner_router)", source)
        self.assertIn("await runtime.route_planner.close()", source)


if __name__ == "__main__":
    unittest.main()
