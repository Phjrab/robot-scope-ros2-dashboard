from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = ROOT / "robot_dashboard" / "app.py"


class FrontendCacheContractTests(unittest.TestCase):
    def test_index_and_executable_assets_are_not_reused_after_restart(self) -> None:
        source = APP_SOURCE.read_text(encoding="utf-8")

        self.assertIn("class DashboardStaticFiles(StaticFiles):", source)
        self.assertIn('path.endswith((".js", ".css"))', source)
        self.assertGreaterEqual(
            source.count('headers["Cache-Control"] = "no-store"'),
            1,
        )
        self.assertIn('headers={"Cache-Control": "no-store"}', source)
        self.assertIn(
            'app.mount("/static", DashboardStaticFiles(directory=STATIC_DIR)',
            source,
        )


if __name__ == "__main__":
    unittest.main()
