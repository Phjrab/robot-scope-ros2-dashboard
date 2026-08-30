import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "robot_dashboard/api/routers/model_registry.py"
APP = ROOT / "robot_dashboard/app.py"
TOOL = ROOT / "scripts/model_registry_tool.py"


class ModelRegistryAppContractTests(unittest.TestCase):
    def test_dashboard_registry_surface_is_read_only(self):
        tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
        routes = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                ):
                    routes.append((decorator.func.attr, decorator.args[0].value))
        self.assertEqual(
            routes,
            [
                ("get", "/api/v1/models"),
                ("get", "/api/v1/models/active"),
            ],
        )

    def test_app_owns_registry_and_dataset_context_without_remote_activation(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("RUNTIME.model_registry = ModelRegistry", source)
        self.assertIn("session_context_snapshot=dataset_session_context_snapshot", source)
        self.assertIn("ROBOT_SCOPE_NETWORK_TOPOLOGY_REVISION", source)
        self.assertIn("ROBOT_SCOPE_GIT_COMMIT", source)
        self.assertNotIn('app.post("/api/v1/models', source)

    def test_target_tool_has_explicit_local_transitions_and_no_network_or_motion(self):
        source = TOOL.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        ]
        self.assertFalse(any(name in {"socket", "http", "requests", "rclpy"} for name in imports))
        self.assertNotIn("subprocess", source)
        self.assertNotIn("cmd_vel", source)
        self.assertIn("ROBOT_SCOPE_MODEL_REGISTRY_DIR", source)
        self.assertNotIn("ROBOT_SCOPE_MODEL_REGISTRY_ROOT", source)
        for command in ("stage", "validate-engine", "activate", "rollback", "list", "active"):
            self.assertIn(f'"{command}"', source)
        self.assertIn("--confirm", source)
        self.assertIn("--confirm-active-model", source)


if __name__ == "__main__":
    unittest.main()
