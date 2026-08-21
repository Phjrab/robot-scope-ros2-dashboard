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
            ("ftp://robot.local:8088", "robot.local:8088"),
            ("//robot.local:8088", "robot.local:8088"),
            ("http://robot.local:8088/", "robot.local:8088"),
            ("http://robot.local:8088?query", "robot.local:8088"),
            ("http://robot.local:8088#fragment", "robot.local:8088"),
            ("http://user@robot.local:8088", "user@robot.local:8088"),
            ("http://robot.local:notaport", "robot.local:notaport"),
            ("http://robot.local:99999", "robot.local:99999"),
            ("http://robot.local:8088", "robot.local:8088/path"),
            ("http://robot.local:8088\n", "robot.local:8088"),
            ("http://robot.local:8088", "robot.local:8088\t"),
            ("http://" + "a" * 510, "a" * 510),
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

    def test_source_selection_mutation_requires_same_origin(self):
        source_path = (
            Path(__file__).parents[1]
            / "robot_dashboard"
            / "api"
            / "routers"
            / "telemetry.py"
        )
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "select_sources"
        )
        self.assertEqual(
            [argument.arg for argument in function.args.args],
            ["selection", "request"],
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "require_same_origin"
                and len(node.args) == 1
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "request"
                for node in ast.walk(function)
            )
        )

    def test_robot_target_disconnect_requires_same_origin(self):
        source_path = (
            Path(__file__).parents[1]
            / "robot_dashboard"
            / "api"
            / "routers"
            / "discovery.py"
        )
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "disconnect_robot"
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "require_same_origin"
                for node in ast.walk(function)
            )
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Attribute)
                and node.attr == "disconnect_robot_target"
                for node in ast.walk(function)
            )
        )

    def test_streaming_mutations_and_websockets_are_same_origin(self):
        router_root = Path(__file__).parents[1] / "robot_dashboard" / "api" / "routers"
        functions = {}
        for filename in ("telemetry.py", "cameras.py"):
            tree = ast.parse((router_root / filename).read_text(encoding="utf-8"))
            functions.update(
                {
                    node.name: node
                    for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
            )
        settings = functions["set_pointcloud_settings"]
        self.assertEqual(
            [argument.arg for argument in settings.args.args],
            ["body", "request"],
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "require_same_origin"
                for node in ast.walk(settings)
            )
        )
        for name in (
            "pointcloud_stream",
            "joint_stream",
            "pose_stream",
            "_camera_stream_source",
        ):
            function = functions[name]
            self.assertTrue(
                any(
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "websocket_same_origin"
                    for node in ast.walk(function)
                ),
                f"{name} must reject cross-origin WebSockets",
            )


if __name__ == "__main__":
    unittest.main()
