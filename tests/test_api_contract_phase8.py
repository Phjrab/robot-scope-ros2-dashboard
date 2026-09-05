import ast
import unittest
from pathlib import Path
from typing import Any, Dict

from robot_dashboard.go2_bridge import (
    MOTION_OBSERVATION_PUBLIC_FIELDS,
    SPORT_MODE_STATE_PUBLIC_FIELDS,
)
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
                    in {"get", "post", "patch", "delete", "websocket"}
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

        self.assertEqual(len(http), 83)
        self.assertEqual(sum(path.startswith("/api/v1/") for _, path in http), 82)
        self.assertEqual(
            {method: sum(candidate == method for candidate, _ in http) for method in {"GET", "POST", "PATCH", "DELETE"}},
            {"GET": 37, "POST": 41, "PATCH": 3, "DELETE": 2},
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
            if entry[0] in {"POST", "PATCH", "DELETE"}
        ]
        self.assertEqual(len(mutations), 46)
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
            "MOTION_OBSERVATION_PUBLIC_FIELDS": MOTION_OBSERVATION_PUBLIC_FIELDS,
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
                    "release_commit": "a" * 40,
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
                    "motion_observation": {
                        "schema": "robot-scope.motion-observation",
                        "schema_version": 1,
                        "source_id": "unitree_go.sport_mode_state.position",
                        "producer_generation": "e" * 32,
                        "release_commit": "a" * 40,
                        "source_sequence": 20,
                        "source_stamp_ns": 2_000_000_001,
                        "source_clock_domain": "unitree_go.timespec.unverified",
                        "source_age_ms": None,
                        "sample_progression": "source_stamp_strict_increase",
                        "callback_receive_age_ms": 25,
                        "last_callback_gap_ms": 4,
                        "max_callback_gap_ms": 8,
                        "callback_clock_domain": "bridge_process.monotonic",
                        "receiver_status_age_ms": 100.0,
                        "receiver_clock_domain": "dashboard_process.monotonic",
                        "stale_after_ms": 500,
                        "coordinate_space": "unitree_go.sport_mode_state.local",
                        "frame_id": None,
                        "origin": "vendor_local_origin_unverified",
                        "position_xyz": [1.0, 2.0, 0.0],
                        "orientation_xyzw": None,
                        "quality": "READY",
                        "invalid_reason": "",
                        "origin_reset_detected": False,
                        "accepted_sample_count": 20,
                        "duplicate_sample_count": 1,
                        "rejected_sample_count": 0,
                        "private": "not-public",
                    },
                    "accepted_command": {
                        "deadman": True,
                        "linear_x": 0.03,
                        "linear_y": 0.0,
                        "angular_z": 0.0,
                        "private": "not-public",
                    },
                    "command_ack": {
                        "source_id": "private-dashboard-source",
                        "seq": 42,
                        "type": "drive",
                        "age_ms": 15,
                        "source_matches_dashboard": True,
                        "bridge_epoch": "private-generation",
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
                "command": {
                    "source": "keyboard",
                    "deadman": True,
                    "linear_x": 0.03,
                    "linear_y": 0.0,
                    "angular_z": 0.0,
                    "private": "not-public",
                },
            }
        )
        bridge = projected["bridge"]
        self.assertTrue(bridge["authenticated"])
        self.assertEqual(bridge["status_age_s"], 0.1)
        self.assertEqual(bridge["total_sport_publishers"], 10)
        self.assertEqual(bridge["transport"], "udp")
        self.assertEqual(bridge["release_commit"], "a" * 40)
        self.assertEqual(bridge["request_evidence"]["published_count"], 2)
        self.assertNotIn("private", bridge["request_evidence"])
        self.assertEqual(
            set(bridge["motion_observation"]),
            set(MOTION_OBSERVATION_PUBLIC_FIELDS),
        )
        self.assertNotIn("private", bridge["motion_observation"])
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
        self.assertEqual(
            bridge["accepted_command"],
            {
                "deadman": True,
                "linear_x": 0.03,
                "linear_y": 0.0,
                "angular_z": 0.0,
            },
        )
        self.assertEqual(
            bridge["command_ack"],
            {
                "seq": 42,
                "type": "drive",
                "age_ms": 15,
                "source_matches_dashboard": True,
            },
        )
        self.assertNotIn("source_id", bridge["command_ack"])
        self.assertNotIn("bridge_epoch", bridge["command_ack"])
        self.assertEqual(
            projected["command"],
            {
                "source": "keyboard",
                "deadman": True,
                "linear_x": 0.03,
                "linear_y": 0.0,
                "angular_z": 0.0,
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

        without_command = namespace["control_view"](
            {
                "bridge": {},
                "limits": {},
                "readiness": {},
                "estop": {},
                "lease": {},
                "action_guard": {},
            }
        )
        self.assertEqual(without_command["command"], {})


if __name__ == "__main__":
    unittest.main()
