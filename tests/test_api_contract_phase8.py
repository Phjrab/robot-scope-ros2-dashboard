import ast
import unittest
from pathlib import Path
from typing import Any, Dict

from robot_dashboard.go2_bridge import SPORT_MODE_STATE_PUBLIC_FIELDS
from robot_dashboard.public_diagnostics import public_diagnostic


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "robot_dashboard" / "app.py"
ROUTERS = ROOT / "robot_dashboard" / "api" / "routers"
MODELS = ROOT / "robot_dashboard" / "api" / "models.py"


def route_inventory():
    inventory = []
    paths = [APP, *sorted(ROUTERS.glob("*.py"))]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            for decorator in function.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr
                    in {"get", "post", "put", "patch", "delete", "websocket"}
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                ):
                    inventory.append(
                        (
                            decorator.func.attr.upper(),
                            decorator.args[0].value,
                            path,
                            function,
                        )
                    )
    return inventory


def calls_name(function: ast.AST, name: str) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
        for node in ast.walk(function)
    )


class Phase8ApiContractTests(unittest.TestCase):
    def test_http_and_websocket_inventory_is_exact_and_bounded(self):
        inventory = route_inventory()
        http = [(method, path) for method, path, _, _ in inventory if method != "WEBSOCKET"]
        websocket = [(method, path) for method, path, _, _ in inventory if method == "WEBSOCKET"]

        self.assertEqual(len(http), 99)
        self.assertEqual(sum(path.startswith("/api/v1/") for _, path in http), 98)
        self.assertEqual(
            {
                method: sum(candidate == method for candidate, _ in http)
                for method in {"GET", "POST", "PUT", "PATCH", "DELETE"}
            },
            {"GET": 42, "POST": 50, "PUT": 1, "PATCH": 4, "DELETE": 2},
        )
        self.assertTrue(
            {
                ("GET", "/api/v1/perception/health"),
                ("GET", "/api/v1/perception/latest"),
                ("GET", "/api/v1/perception/history"),
                ("POST", "/api/v1/datasets/{session_id}/export"),
                ("GET", "/api/v1/datasets/exports/{export_id}"),
                ("GET", "/api/v1/models"),
                ("GET", "/api/v1/models/active"),
                ("GET", "/api/v1/competition"),
                ("POST", "/api/v1/competition/lock"),
                ("POST", "/api/v1/competition/unlock"),
                ("POST", "/api/v1/competition/mode"),
                ("GET", "/api/v1/route-planner"),
                ("PUT", "/api/v1/route-planner/graph"),
                ("POST", "/api/v1/route-planner/recommendations"),
                ("POST", "/api/v1/route-planner/guidance/pickup"),
                ("POST", "/api/v1/route-planner/guidance/dropoff"),
            }.issubset(set(http))
        )
        self.assertEqual(
            {path for _, path in websocket},
            {
                "/api/v1/ws/control",
                "/api/v1/ws/pointcloud",
                "/api/v1/ws/camera",
                "/api/v1/ws/cameras/{source_id}",
                "/api/v1/ws/joints",
                "/api/v1/ws/pose",
            },
        )

    def test_every_http_mutation_calls_the_shared_origin_guard(self):
        mutations = [
            entry
            for entry in route_inventory()
            if entry[0] in {"POST", "PUT", "PATCH", "DELETE"}
        ]
        self.assertEqual(len(mutations), 57)
        for method, path, _, function in mutations:
            with self.subTest(method=method, path=path):
                self.assertTrue(calls_name(function, "require_same_origin"))

    def test_every_websocket_reaches_origin_guard_before_accept(self):
        inventory = {
            path: function
            for method, path, _, function in route_inventory()
            if method == "WEBSOCKET"
        }
        for path in (
            "/api/v1/ws/control",
            "/api/v1/ws/pointcloud",
            "/api/v1/ws/joints",
            "/api/v1/ws/pose",
        ):
            function = inventory[path]
            guard_line = min(
                node.lineno
                for node in ast.walk(function)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "websocket_same_origin"
            )
            accept_line = min(
                node.lineno
                for node in ast.walk(function)
                if isinstance(node, ast.Attribute) and node.attr == "accept"
            )
            self.assertLess(guard_line, accept_line, path)

        camera_tree = ast.parse((ROUTERS / "cameras.py").read_text(encoding="utf-8"))
        camera_helper = next(
            node
            for node in camera_tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_camera_stream_source"
        )
        self.assertTrue(calls_name(camera_helper, "websocket_same_origin"))
        for path in ("/api/v1/ws/camera", "/api/v1/ws/cameras/{source_id}"):
            self.assertTrue(calls_name(inventory[path], "_camera_stream_source"))

    def test_app_uses_one_origin_authority_and_adds_no_store_headers(self):
        tree = ast.parse(APP.read_text(encoding="utf-8"))
        definitions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn("require_same_origin", definitions)
        self.assertNotIn("websocket_same_origin", definitions)
        dependency_import = next(
            node
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "api.dependencies"
        )
        self.assertEqual(
            {alias.name for alias in dependency_import.names},
            {"require_same_origin", "websocket_same_origin"},
        )
        middleware = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "api_response_security"
        )
        strings = {
            node.value
            for node in ast.walk(middleware)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertTrue(
            {
                "/api/v1/",
                "Cache-Control",
                "no-store",
                "X-Content-Type-Options",
                "nosniff",
                "Referrer-Policy",
                "no-referrer",
            }.issubset(strings)
        )

    def test_safety_confirmations_and_source_names_are_strictly_bounded(self):
        tree = ast.parse(MODELS.read_text(encoding="utf-8"))
        classes = {
            node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
        }
        clear = classes["ControlClearEstopRequest"]
        assignment = next(
            node
            for node in clear.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "confirmed"
        )
        self.assertIsInstance(assignment.value, ast.Call)
        self.assertEqual(
            {
                keyword.arg: ast.literal_eval(keyword.value)
                for keyword in assignment.value.keywords
            },
            {"strict": True},
        )
        source = classes["SourceSelection"]
        fields = {
            node.target.id: node
            for node in source.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        self.assertEqual(
            set(fields), {"camera", "pointcloud", "odometry", "occupancy_grid"}
        )
        for field in fields.values():
            keywords = {
                keyword.arg: ast.literal_eval(keyword.value)
                for keyword in field.value.keywords
            }
            self.assertEqual(keywords, {"default": None, "max_length": 255})

    def test_control_projection_allowlists_bridge_fields(self):
        tree = ast.parse(APP.read_text(encoding="utf-8"))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "control_view"
        )
        namespace = {
            "Any": Any,
            "Dict": Dict,
            "SPORT_MODE_STATE_PUBLIC_FIELDS": SPORT_MODE_STATE_PUBLIC_FIELDS,
            "public_diagnostic": public_diagnostic,
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(APP), "exec"), namespace)
        projected = namespace["control_view"](
            {
                "bridge": {
                    "state": "ready",
                    "authenticated": True,
                    "ready": True,
                    "message": "ready",
                    "status_age_s": 0.1,
                    "sport_publishers": 10,
                    "own_sport_publishers": 1,
                    "foreign_named_sport_publishers": 0,
                    "bare_unitree_sport_publishers": 9,
                    "expected_bare_sport_publishers": 9,
                    "transport": "udp",
                    "request_evidence": {
                        "schema": "robot-scope.sport-request-evidence.v1",
                        "scope": "bridge_process",
                        "published_count": 2,
                        "stop_count": 1,
                        "move_count": 1,
                        "zero_move_count": 1,
                        "nonzero_move_count": 0,
                        "malformed_move_count": 0,
                        "action_count": 0,
                        "other_count": 0,
                        "last_api_id": 1008,
                        "last_publish_age_ms": 20,
                        "max_abs_linear_x": 0.0,
                        "max_abs_linear_y": 0.0,
                        "max_abs_angular_z": 0.0,
                        "motion_run_id": 0,
                        "motion_run_active": False,
                        "motion_run_nonzero_move_count": 0,
                        "motion_run_max_abs_linear_x": 0.0,
                        "motion_run_max_abs_linear_y": 0.0,
                        "motion_run_max_abs_angular_z": 0.0,
                        "private": "not-public",
                    },
                    "sport_mode_state": {
                        "topic": "/sportmodestate",
                        "mode": 5,
                        "gait_type": 3,
                        "velocity": [0.105, 0.0, 0.0],
                        "error_code": 123456,
                        "age_ms": 25,
                        "stale_after_ms": 500,
                        "fresh": True,
                        "private": "not-public",
                    },
                    "bridge_epoch": "private-generation",
                    "bridge_pid": 1234,
                    "issued_at_ms": 999,
                    "mac": "private-signature",
                    "unexpected_secret": "not-public",
                },
                "limits": {},
                "readiness": {},
                "estop": {},
                "lease": {},
                "action_guard": {},
            }
        )
        bridge = projected["bridge"]
        self.assertTrue(bridge["authenticated"])
        self.assertEqual(bridge["status_age_s"], 0.1)
        self.assertEqual(bridge["total_sport_publishers"], 10)
        self.assertEqual(bridge["transport"], "udp")
        self.assertEqual(bridge["request_evidence"]["published_count"], 2)
        self.assertNotIn("private", bridge["request_evidence"])
        self.assertEqual(
            bridge["sport_mode_state"],
            {
                "topic": "/sportmodestate",
                "mode": 5,
                "gait_type": 3,
                "velocity": [0.105, 0.0, 0.0],
                "error_code": 123456,
                "age_ms": 25,
                "stale_after_ms": 500,
                "fresh": True,
            },
        )
        for private in (
            "bridge_epoch",
            "bridge_pid",
            "issued_at_ms",
            "mac",
            "sport_publishers",
            "unexpected_secret",
        ):
            self.assertNotIn(private, bridge)


if __name__ == "__main__":
    unittest.main()
