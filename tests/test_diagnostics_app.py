from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "robot_dashboard" / "app.py"
SYSTEM = ROOT / "robot_dashboard" / "api" / "routers" / "system.py"


class DiagnosticsAppContractTests(unittest.TestCase):
    def test_export_is_same_origin_attachment_and_never_takes_robot_work_lock(self) -> None:
        source = SYSTEM.read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "export_diagnostics"
        )
        rendered = ast.unparse(function)
        self.assertIn("require_same_origin(request)", rendered)
        self.assertIn("asyncio.to_thread(_diagnostics(runtime).build)", rendered)
        self.assertNotIn("pipeline_coordination_lock", rendered)
        self.assertNotIn("require_idle", rendered)
        self.assertIn("media_type='application/zip'", rendered)
        self.assertIn("'Cache-Control': 'private, no-store'", rendered)
        self.assertIn("'Content-Disposition'", rendered)

    def test_cross_origin_and_missing_service_fail_closed(self) -> None:
        source = SYSTEM.read_text(encoding="utf-8")
        self.assertIn('"diagnostics export is not configured"', source)
        self.assertIn("runtime.diagnostics", source)
        self.assertIn("except DiagnosticsUnavailable as exc", source)
        self.assertIn("status_code=503", source)
        self.assertNotIn("bridge_key", source)
        self.assertNotIn("Authorization", source)

    def test_runtime_wires_single_timeline_and_bundle_and_middleware_is_best_effort(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertEqual(source.count("OperatorEventTimeline("), 1)
        self.assertEqual(source.count("DiagnosticsBundleService("), 1)
        self.assertIn("RUNTIME.operator_events = OperatorEventTimeline", source)
        self.assertIn("RUNTIME.diagnostics = DiagnosticsBundleService", source)
        tree = ast.parse(source)
        middleware = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "api_response_security"
        )
        rendered = ast.unparse(middleware)
        self.assertEqual(rendered.count("record_http_event"), 2)
        self.assertIn(
            "tracked_operator_event = classify_http_event(request.method, request.url.path)",
            rendered,
        )
        self.assertEqual(rendered.count("if tracked_operator_event is not None"), 2)
        self.assertIn("LOGGER.exception('operator event recording failed')", rendered)
        self.assertIn("response = await call_next(request)", rendered)


if __name__ == "__main__":
    unittest.main()
