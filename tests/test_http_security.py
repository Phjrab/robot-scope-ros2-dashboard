import ast
import unittest
from pathlib import Path

from robot_dashboard.http_security import is_same_origin


class HttpSecurityTests(unittest.TestCase):
    def test_matching_origin_is_allowed(self):
        self.assertTrue(is_same_origin("http://10.100.0.89:8088", "10.100.0.89:8088"))
        self.assertTrue(is_same_origin("HTTPS://ROBOT.LOCAL:8088", "robot.local:8088"))

    def test_missing_or_cross_origin_is_rejected(self):
        for origin, host in (
            ("", "10.100.0.89:8088"),
            ("http://10.100.0.89:8088", ""),
            ("http://evil.example", "10.100.0.89:8088"),
            ("http://10.100.0.89:9090", "10.100.0.89:8088"),
            ("http://[invalid", "10.100.0.89:8088"),
        ):
            with self.subTest(origin=origin, host=host):
                self.assertFalse(is_same_origin(origin, host))

    def test_every_mapping_mutation_route_calls_same_origin_guard(self):
        source_path = Path(__file__).parents[1] / "robot_dashboard" / "app.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for name in ("mapping_start", "mapping_stop", "mapping_save"):
            function = functions[name]
            guarded = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "require_same_origin"
                and len(node.args) == 1
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "request"
                for node in ast.walk(function)
            )
            self.assertTrue(guarded, f"{name} must require a same-origin Request")

    def test_mapping_save_keeps_body_and_http_request_separate(self):
        source_path = Path(__file__).parents[1] / "robot_dashboard" / "app.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "mapping_save"
        )
        self.assertEqual([argument.arg for argument in function.args.args], ["body", "request"])


if __name__ == "__main__":
    unittest.main()
