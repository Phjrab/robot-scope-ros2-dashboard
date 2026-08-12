import ast
import unittest
from pathlib import Path


SOURCE_PATH = Path(__file__).parents[1] / "robot_dashboard" / "app.py"


class DatasetAppContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.functions = {
            node.name: node
            for node in cls.tree.body
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
        start = self.functions["dataset_capture_start"]
        stop = self.functions["dataset_capture_stop"]
        for function in (start, stop):
            self.assertTrue(self.calls_name(function, "require_same_origin"))
            self.assertTrue(
                any(
                    isinstance(node, ast.AsyncWith)
                    and any(
                        isinstance(item.context_expr, ast.Name)
                        and item.context_expr.id == "PIPELINE_COORDINATION_LOCK"
                        for item in node.items
                    )
                    for node in ast.walk(function)
                )
            )
        self.assertTrue(self.calls_name(start, "require_service_lifecycle_idle"))

        classes = {
            node.name: node for node in self.tree.body if isinstance(node, ast.ClassDef)
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
        blockers = self.functions["service_lifecycle_blockers"]
        constants = {
            node.value
            for node in ast.walk(blockers)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertIn("dataset_capture_active", constants)
        self.assertIn("dataset_capture_state_unknown", constants)

        lifespan = self.functions["lifespan"]
        segment = ast.get_source_segment(self.source, lifespan)
        self.assertIn("DATASET_CAPTURE.close", segment)
        self.assertLess(
            segment.index("navigation_deactivate"),
            segment.index("DATASET_CAPTURE.close"),
        )
        self.assertLess(
            segment.index("AGENT.shutdown_control()"),
            segment.index("DATASET_CAPTURE.close"),
        )
        self.assertLess(segment.index("DATASET_CAPTURE.close"), segment.index("AGENT.stop()"))

    def test_main_wires_fixed_camera_callbacks_and_dataset_path(self):
        main = self.functions["main"]
        segment = ast.get_source_segment(self.source, main)
        self.assertIn("DatasetCaptureManager", segment)
        self.assertIn("camera_open=AGENT.camera_stream_open", segment)
        self.assertIn("camera_close=AGENT.camera_stream_close", segment)
        self.assertIn("camera_snapshots=AGENT.camera_snapshots", segment)
        self.assertIn("Path(args.dataset_output_dir)", segment)
        self.assertIn('"--dataset-output-dir"', self.source)

    def test_gallery_routes_are_fixed_and_images_are_not_cacheable(self):
        expected = {
            "/api/v1/datasets/capture",
            "/api/v1/datasets/capture/start",
            "/api/v1/datasets/capture/stop",
            "/api/v1/datasets",
            "/api/v1/datasets/{session_id}",
            "/api/v1/datasets/{session_id}/samples/{sample_index}/{source_id}.jpg",
        }
        routes = set()
        for node in self.tree.body:
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
        image = self.functions["dataset_image"]
        constants = {
            node.value
            for node in ast.walk(image)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertIn("image/jpeg", constants)
        self.assertIn("private, no-store", constants)
        self.assertIn("nosniff", constants)


if __name__ == "__main__":
    unittest.main()
