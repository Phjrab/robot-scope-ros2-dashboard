import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "robot_dashboard" / "app.py"
APP_SOURCE = APP_PATH.read_text(encoding="utf-8")
APP_TREE = ast.parse(APP_SOURCE)
SYSTEM_PATH = ROOT / "robot_dashboard" / "api" / "routers" / "system.py"
SYSTEM_SOURCE = SYSTEM_PATH.read_text(encoding="utf-8")
SYSTEM_TREE = ast.parse(SYSTEM_SOURCE)
LIFECYCLE_PATH = (
    ROOT / "robot_dashboard" / "application" / "lifecycle_coordinator.py"
)
LIFECYCLE_SOURCE = LIFECYCLE_PATH.read_text(encoding="utf-8")
LIFECYCLE_TREE = ast.parse(LIFECYCLE_SOURCE)
NAVIGATION_TREE = ast.parse(
    (
        ROOT
        / "robot_dashboard"
        / "application"
        / "navigation_coordinator.py"
    ).read_text(encoding="utf-8")
)
MODELS_TREE = ast.parse(
    (ROOT / "robot_dashboard" / "api" / "models.py").read_text(encoding="utf-8")
)


def function_node(name):
    for tree in (APP_TREE, SYSTEM_TREE):
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
    raise AssertionError(f"function {name} was not found")


def tree_function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {name} was not found")


def class_function(tree, class_name, name):
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    for node in owner.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {class_name}.{name} was not found")


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


class ControlBridgeLifecycleAppContractTests(unittest.TestCase):
    def test_mutations_are_same_origin_strict_and_use_only_coordinator_methods(self):
        expected = {
            "control_bridge_lifecycle_start": "schedule_control_bridge_start",
            "control_bridge_lifecycle_stop": "schedule_control_bridge_stop",
        }
        for name, method in expected.items():
            calls = called_names(function_node(name))
            attributes = attribute_names(function_node(name))
            self.assertIn("require_same_origin", calls)
            self.assertIn("_bridge", calls)
            self.assertIn(method, attributes)
            self.assertNotIn("system", calls)
            self.assertNotIn("run", calls)
            self.assertNotIn("Popen", calls)

    def test_confirmation_body_is_strict_and_has_no_service_or_force_field(self):
        model = next(
            node
            for node in MODELS_TREE.body
            if isinstance(node, ast.ClassDef)
            and node.name == "ControlBridgeLifecycleRequest"
        )
        assignments = {
            item.target.id: item
            for item in model.body
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
        }
        self.assertEqual(set(assignments), {"confirmed"})
        value = assignments["confirmed"].value
        self.assertIsInstance(value, ast.Call)
        keywords = {item.arg: item.value for item in value.keywords}
        self.assertIs(keywords["strict"].value, True)
        self.assertNotIn("force", APP_SOURCE)

    def test_new_robot_work_interlock_includes_bridge_lifecycle(self):
        helper = function_node("require_service_lifecycle_idle")
        calls = called_names(helper)
        self.assertIn("lifecycle_coordinator", calls)
        self.assertIn("require_idle", attribute_names(helper))

        self.assertIn(
            "require_service_lifecycle_idle",
            called_names(function_node("control_arm")),
        )
        for guarded in ("start", "_send_goal_locked"):
            self.assertIn(
                "_require_lifecycle_idle",
                called_names(
                    class_function(
                        NAVIGATION_TREE,
                        "NavigationCoordinator",
                        guarded,
                    )
                ),
            )
        self.assertIn(
            "_send_goal_locked",
            called_names(
                class_function(
                    NAVIGATION_TREE,
                    "NavigationCoordinator",
                    "send_goal",
                )
            ),
        )
        for cleanup in ("control_disarm", "control_stop", "navigation_stop"):
            self.assertNotIn(
                "require_service_lifecycle_idle",
                called_names(function_node(cleanup)),
            )

    def test_dashboard_lifecycle_preflight_blocks_bridge_transition_fail_closed(self):
        wrapper = function_node("service_lifecycle_blockers")
        self.assertIn("service_blockers", attribute_names(wrapper))
        node = tree_function(LIFECYCLE_TREE, "service_blockers")
        attributes = attribute_names(node)
        strings = {
            child.value
            for child in ast.walk(node)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        }
        self.assertIn("_control_bridge_lifecycle", attributes)
        self.assertIn("is_busy", attributes)
        self.assertIn("control_bridge_service_transition", strings)
        self.assertIn(
            "control_bridge_service_lifecycle_status_unavailable", strings
        )

    def test_read_only_status_route_does_not_require_origin_or_accept_input(self):
        status = function_node("control_bridge_lifecycle_status")
        calls = called_names(status)
        self.assertIn("control_bridge_snapshot", attribute_names(status))
        self.assertNotIn("require_same_origin", calls)
        self.assertEqual([argument.arg for argument in status.args.args], ["request"])


if __name__ == "__main__":
    unittest.main()
