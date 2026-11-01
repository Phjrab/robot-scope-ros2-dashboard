"""Run the real JS consumer suite from the mandatory Python discovery pass."""
from pathlib import Path
import shutil
import subprocess
import unittest


class SceneConsumerTests(unittest.TestCase):
    def test_consumer_suite(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js unavailable")
        root = Path(__file__).resolve().parents[2]
        for suite in ("test_consumer.mjs", "test_canonical.mjs", "test_assets.mjs"):
            with self.subTest(suite=suite):
                result = subprocess.run([node, f"tests/expansion_c3/{suite}"], cwd=root,
                                        capture_output=True, text=True, timeout=30, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
