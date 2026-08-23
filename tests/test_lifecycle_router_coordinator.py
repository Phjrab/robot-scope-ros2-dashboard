import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTER_PATH = ROOT / "robot_dashboard" / "api" / "routers" / "system.py"
SOURCE = ROUTER_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def function(name):
    return next(
        node
        for node in TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def called_names(node):
    result = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            result.add(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            result.add(child.func.attr)
    return result


def attribute_names(node):
    return {
        child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute)
    }


class LifecycleRouterCoordinatorTests(unittest.TestCase):
    def test_router_resolves_one_coordinator_without_raw_manager_fields(self):
        self.assertIn("LifecycleCoordinator", SOURCE)
        self.assertNotIn("ControlBridgeLifecycleManager", SOURCE)
        self.assertNotIn("ServiceLifecycleManager", SOURCE)
        for helper_name in ("_service", "_bridge"):
            attributes = attribute_names(function(helper_name))
            self.assertIn("lifecycle", attributes)
            self.assertNotIn("service_lifecycle", attributes)
            self.assertNotIn("control_bridge_lifecycle", attributes)

    def test_status_routes_use_thin_coordinator_snapshots(self):
        expected = {
            "service_lifecycle_status": "service_snapshot",
            "control_bridge_lifecycle_status": "control_bridge_snapshot",
        }
        for route_name, method_name in expected.items():
            route = function(route_name)
            self.assertIn(method_name, attribute_names(route))
            self.assertNotIn("require_same_origin", called_names(route))

    def test_mutations_keep_origin_lock_and_coordinator_operation(self):
        expected = {
            "service_lifecycle_restart": "schedule_service_restart",
            "service_lifecycle_stop": "schedule_service_stop",
            "control_bridge_lifecycle_start": (
                "schedule_control_bridge_start"
            ),
            "control_bridge_lifecycle_stop": "schedule_control_bridge_stop",
        }
        for route_name, method_name in expected.items():
            route = function(route_name)
            self.assertIn("require_same_origin", called_names(route))
            self.assertIn(method_name, attribute_names(route))
            self.assertTrue(
                any(
                    isinstance(child, ast.AsyncWith)
                    and any(
                        isinstance(item.context_expr, ast.Attribute)
                        and item.context_expr.attr == "pipeline_coordination_lock"
                        for item in child.items
                    )
                    for child in ast.walk(route)
                ),
                route_name,
            )

    def test_paths_and_accepted_status_codes_are_unchanged(self):
        actual = {}
        for node in TREE.body:
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                ):
                    keywords = {
                        item.arg: item.value for item in decorator.keywords
                    }
                    status = keywords.get("status_code")
                    actual[node.name] = (
                        decorator.func.attr,
                        decorator.args[0].value,
                        status.value if isinstance(status, ast.Constant) else None,
                    )
        self.assertEqual(
            actual,
            {
                "service_lifecycle_status": (
                    "get",
                    "/api/v1/system/service",
                    None,
                ),
                "service_lifecycle_restart": (
                    "post",
                    "/api/v1/system/service/restart",
                    202,
                ),
                "service_lifecycle_stop": (
                    "post",
                    "/api/v1/system/service/stop",
                    202,
                ),
                "control_bridge_lifecycle_status": (
                    "get",
                    "/api/v1/control/bridge-service",
                    None,
                ),
                "control_bridge_lifecycle_start": (
                    "post",
                    "/api/v1/control/bridge-service/start",
                    202,
                ),
                "control_bridge_lifecycle_stop": (
                    "post",
                    "/api/v1/control/bridge-service/stop",
                    202,
                ),
                "export_diagnostics": (
                    "post",
                    "/api/v1/system/diagnostics/export",
                    None,
                ),
            },
        )


if __name__ == "__main__":
    unittest.main()
