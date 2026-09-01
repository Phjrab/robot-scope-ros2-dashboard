import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CockpitAcceptanceDocumentationTests(unittest.TestCase):
    def test_operator_guide_covers_every_required_competition_procedure(self):
        guide = (ROOT / "docs" / "COCKPIT_OPERATOR_GUIDE.md").read_text(encoding="utf-8")
        required = {
            "Cockpit 진입",
            "별도 전체 창과 브라우저 Fullscreen",
            "Layout Edit와 Operate",
            "Panel 열기와 Focus",
            "Xbox 연결",
            "ARM과 Deadman",
            "STOP의 의미",
            "Camera와 LiDAR stale 판별",
            "Manual Takeover",
            "Mission Pause와 Abort",
            "대회 시작 전 체크리스트",
            "대회 종료 후 로그와 Dataset 보존",
        }
        for heading in required:
            self.assertIn(heading, guide)
        self.assertIn("물리 정지", guide)
        self.assertIn("자동 ARM", guide)
        self.assertIn("CWP 전체 창", guide)
        self.assertIn("팝업", guide)
        self.assertIn("브라우저 전체 화면", guide)

    def test_acceptance_report_separates_software_hardware_and_unmeasured_results(self):
        report = (ROOT / "docs" / "COCKPIT_ACCEPTANCE.md").read_text(encoding="utf-8")
        for status in ("PASS", "FAIL", "BLOCKED", "NOT_RUN"):
            self.assertIn(f"`{status}`", report)
        for environment in (
            "1920×1080 Chromium",
            "2560×1440 Chromium",
            "저사양 관리 노트북",
            "Jetson local browser",
            "원격 PC browser",
        ):
            self.assertIn(environment, report)
        for metric in (
            "renderer FPS p50/p95",
            "PointCloud decode",
            "Camera decode/render",
            "control frame interval/jitter",
            "WebSocket reconnect",
            "main-thread long task",
            "browser memory",
            "Jetson CPU/memory",
            "network throughput",
            "60분",
            "3시간",
        ):
            self.assertIn(metric, report)
        self.assertIn("Software-only acceptance", report)
        self.assertIn("Hardware acceptance", report)
        self.assertIn("P0", report)
        self.assertIn("실제 Nav2 no-goal start/stop", report)
        self.assertIn("legacy direct-Go2 launcher", report)

    def test_cockpit_node_and_browser_suites_have_dedicated_commands(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        scripts = package["scripts"]
        self.assertEqual(scripts["test:cockpit"], "node --test tests/test_cockpit_*.mjs")
        self.assertEqual(scripts["test:cockpit:e2e"], "playwright test --grep Cockpit")
        syntax = (ROOT / "scripts" / "check_frontend_syntax.mjs").read_text(encoding="utf-8")
        self.assertIn("collectJavaScript(staticRoot)", syntax)


if __name__ == "__main__":
    unittest.main()
