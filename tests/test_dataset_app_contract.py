import ast
import unittest
from pathlib import Path


SOURCE_PATH = Path(__file__).parents[1] / "robot_dashboard" / "app.py"
ROUTER_PATH = (
    Path(__file__).parents[1]
    / "robot_dashboard"
    / "api"
    / "routers"
    / "dataset.py"
)
MODELS_PATH = Path(__file__).parents[1] / "robot_dashboard" / "api" / "models.py"
LIFECYCLE_PATH = (
    Path(__file__).parents[1]
    / "robot_dashboard"
    / "application"
    / "lifecycle_coordinator.py"
)


class DatasetAppContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.router_source = ROUTER_PATH.read_text(encoding="utf-8")
        cls.router_tree = ast.parse(cls.router_source)
        cls.models_tree = ast.parse(MODELS_PATH.read_text(encoding="utf-8"))
        cls.lifecycle_source = LIFECYCLE_PATH.read_text(encoding="utf-8")
        cls.lifecycle_tree = ast.parse(cls.lifecycle_source)
        cls.functions = {
            node.name: node
            for node in cls.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        cls.router_functions = {
            node.name: node
            for node in ast.walk(cls.router_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        cls.lifecycle_functions = {
            node.name: node
            for node in ast.walk(cls.lifecycle_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def calls_name(self, function, name):
        return any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
            for node in ast.walk(function)
        )

    def test_start_and_stop_are_same_origin_and_serialized(self):
        start = self.router_functions["dataset_capture_start"]
        stop = self.router_functions["dataset_capture_stop"]
        for function in (start, stop):
            self.assertTrue(self.calls_name(function, "require_same_origin"))
            self.assertTrue(
                any(
                    isinstance(node, ast.AsyncWith)
                    and any(
                        isinstance(item.context_expr, ast.Attribute)
                        and item.context_expr.attr == "pipeline_coordination_lock"
                        for item in node.items
                    )
                    for node in ast.walk(function)
                )
            )
        self.assertTrue(self.calls_name(start, "require_service_lifecycle_idle"))

        classes = {
            node.name: node
            for node in self.models_tree.body
            if isinstance(node, ast.ClassDef)
        }
        for name in ("DatasetCaptureStartRequest", "DatasetCaptureStopRequest"):
            self.assertEqual(
                [base.id for base in classes[name].bases if isinstance(base, ast.Name)],
                ["StrictRequest"],
            )
        start_fields = {
            node.target.id
            for node in classes["DatasetCaptureStartRequest"].body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        stop_fields = {
            node.target.id
            for node in classes["DatasetCaptureStopRequest"].body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        self.assertEqual(start_fields, {"sources", "capture_hz", "label"})
        self.assertEqual(stop_fields, {"session_id"})

    def test_capture_is_a_fail_closed_lifecycle_blocker_and_shutdown_precedes_agent(self):
        wrapper = self.functions["service_lifecycle_blockers"]
        self.assertTrue(self.calls_name(wrapper, "lifecycle_coordinator"))
        blockers = self.lifecycle_functions["service_blockers"]
        constants = {
            node.value
            for node in ast.walk(blockers)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertIn("dataset_capture_active", constants)
        self.assertIn("dataset_capture_state_unknown", constants)

        lifespan = self.functions["lifespan"]
        segment = ast.get_source_segment(self.source, lifespan)
        self.assertIn("runtime.lifecycle.close", segment)
        self.assertLess(
            segment.index("runtime.lifecycle.close"),
            segment.index("runtime.navigation.close"),
        )
        self.assertLess(
            segment.index("runtime.navigation.close"),
            segment.index("runtime.agent.shutdown_control()"),
        )
        self.assertLess(
            segment.index("runtime.agent.shutdown_control()"),
            segment.index("runtime.dataset_capture.close"),
        )
        self.assertLess(
            segment.index("runtime.dataset_capture.close"),
            segment.index("runtime.mapping.close"),
        )
        self.assertLess(
            segment.index("runtime.mapping.close"),
            segment.index("runtime.agent.stop()"),
        )

    def test_main_wires_fixed_camera_callbacks_and_dataset_path(self):
        main = self.functions["main"]
        segment = ast.get_source_segment(self.source, main)
        self.assertIn("DatasetCaptureManager", segment)
        self.assertIn("camera_open=RUNTIME.agent.camera_stream_open", segment)
        self.assertIn("camera_close=RUNTIME.agent.camera_stream_close", segment)
        self.assertIn("camera_snapshots=RUNTIME.agent.camera_snapshots", segment)
        self.assertIn("Path(args.dataset_output_dir)", segment)
        self.assertIn('"--dataset-output-dir"', self.source)

    def test_gallery_routes_are_fixed_and_images_are_not_cacheable(self):
        expected = {
            "/api/v1/datasets/capture",
            "/api/v1/datasets/capture/start",
            "/api/v1/datasets/capture/stop",
            "/api/v1/datasets",
            "/api/v1/datasets/{session_id}/export",
            "/api/v1/datasets/exports/{export_id}",
            "/api/v1/datasets/{session_id}",
            "/api/v1/datasets/{session_id}/samples/{sample_index}/{source_id}.jpg",
        }
        routes = set()
        for node in ast.walk(self.router_tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr in {"get", "post"}
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                ):
                    routes.add(decorator.args[0].value)
        self.assertTrue(expected.issubset(routes))
        image = self.router_functions["dataset_image"]
        constants = {
            node.value
            for node in ast.walk(image)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertIn("image/jpeg", constants)
        self.assertIn("private, no-store", constants)
        self.assertIn("nosniff", constants)

    def test_export_is_same_origin_serialized_and_lifecycle_blocked(self):
        export = self.router_functions["dataset_export"]
        self.assertTrue(self.calls_name(export, "require_same_origin"))
        self.assertTrue(self.calls_name(export, "require_service_lifecycle_idle"))
        self.assertTrue(
            any(
                isinstance(node, ast.AsyncWith)
                and any(
                    isinstance(item.context_expr, ast.Attribute)
                    and item.context_expr.attr == "pipeline_coordination_lock"
                    for item in node.items
                )
                for node in ast.walk(export)
            )
        )
        download = self.router_functions["dataset_export_download"]
        constants = {
            node.value
            for node in ast.walk(download)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertIn("application/zip", constants)
        self.assertIn("private, no-store", constants)


if __name__ == "__main__":
    unittest.main()
