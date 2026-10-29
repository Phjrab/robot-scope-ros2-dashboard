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
        result = subprocess.run([node, "tests/expansion_c3/test_consumer.mjs"], cwd=root,
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
