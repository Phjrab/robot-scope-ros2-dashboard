import os
from pathlib import Path
import subprocess
import sys
import unittest

ENABLED = bool(os.environ.get('C4_ROS_DEP_ROOT'))
if os.environ.get('C4_ROS_REQUIRED') == '1' and not ENABLED:
    raise RuntimeError('C4_ROS_DEP_ROOT required; actual owners cannot be replaced by mocks')


class AsyncDependencyProcess(unittest.TestCase):
    @unittest.skipUnless(ENABLED, 'NOT_RUN: ROS bridge exact SHA core dependencies required')
    def test_actual_async_composition(self):
        root = Path(__file__).resolve().parents[2]
        env = dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        env['PYTHONPATH'] = str(root/'tests')+os.pathsep+str(root)+os.pathsep+env.get('PYTHONPATH','')
        result = subprocess.run([sys.executable,'-m','unittest','expansion_runtime.async_cases','-v'],
                                cwd=root,env=env,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
