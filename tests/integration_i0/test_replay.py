import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.integration_i0.prepare_replays import prepare
from robot_dashboard.run_review.summary import summary, markdown


class InstalledReplayTests(unittest.TestCase):
    def test_installed_c1_parser_cli_and_allowlisted_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "inputs"
            prepare(root)
            output = Path(directory) / "export"
            result = subprocess.run([sys.executable, "-m", "robot_dashboard.run_review",
                "--root", str(root), "--manifest", "manifest-0.json", "--compare-manifest",
                "manifest-1.json", "--installed-contracts", "--output", str(output)],
                capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = json.loads((root / "review-0.json").read_text())
            public = json.loads((output / "summary.json").read_text())
            self.assertEqual(public, summary(run))
            self.assertEqual((output / "summary.md").read_text(), markdown(public))
            self.assertEqual(public["near_result"]["stamp_ns"], "1793244679103000000")
            self.assertNotIn("source_id", public)
            scene = json.loads((root / "review-3.json").read_text())
            self.assertEqual(scene["mode"], "REPLAY")
            self.assertEqual(len(scene["frames"]), 4)
