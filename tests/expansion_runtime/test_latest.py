"""Avoid mixing old and current exact-SHA imports in one Python interpreter."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

ENABLED = bool(os.environ.get('C4_LATEST_DEP_ROOT'))
if os.environ.get('C4_LATEST_REQUIRED') == '1' and not ENABLED:
    raise RuntimeError('C4_LATEST_DEP_ROOT required; current owner dependencies cannot be mocked')


class LatestDependencyProcess(unittest.TestCase):
    @unittest.skipUnless(ENABLED, 'NOT_RUN: current exact SHA read-only owner exports required')
    def test_current_actual_dependencies(self):
        root = Path(__file__).resolve().parents[2]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        env['PYTHONPATH'] = str(root/'tests')+os.pathsep+str(root)+os.pathsep+env.get('PYTHONPATH', '')
        result = subprocess.run([sys.executable, '-m', 'unittest', 'expansion_runtime.latest_cases', '-v'],
                                cwd=root, env=env, text=True, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
