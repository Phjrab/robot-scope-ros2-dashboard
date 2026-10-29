"""Pinned actual core/validator/C4 Python ports, not HTTP or ROS execution."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

PINS = {'c1': '54629c793ad4ae0ea88127f00ed1b7f8805fc4e2',
        'c4': 'b9d700d754f0d3d43b9afdcffcb86e9deb7b1020'}
PATHS = {'c1': ['robot_dashboard/expansion_contracts', 'robot_dashboard/expansion_services'],
         'c4': ['robot_dashboard/obstacle_runtime_adapter']}


def export(root):
    for role, sha in PINS.items():
        for path in subprocess.check_output(['git','ls-tree','-r','--name-only',sha,'--',*PATHS[role]],text=True).splitlines():
            destination=root/role/path; destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(subprocess.check_output(['git','show',sha+':'+path]))


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,required=True); ap.add_argument('--example-output',type=Path); args=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='d2-round2-exact-') as tmp:
        root=Path(tmp); export(root); os.environ['D2_DEPENDENCY_ROOT']=str(root)
        import sys
        sys.path.insert(0, str(Path("tests").resolve()))
        from expansion_d2 import test_round2_ports
        suite=unittest.defaultTestLoader.loadTestsFromModule(test_round2_ports)
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        report={'pins':PINS,'actual_core':True,'actual_c1_validator':True,'actual_c1_service_python':True,
                'actual_c4_python_ports':True,'HTTP':'NOT_RUN','ROS':'NOT_RUN',
                'REAL_YOLO_EVALUATION':'INPUT_REQUIRED','tests':result.testsRun,
                'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),
                'payloads':test_round2_ports.MEASUREMENTS}
        if args.example_output:
            example=test_round2_ports.C1ObstacleProjection(test_round2_ports.ObstacleFrame)(
                test_round2_ports.port().process(test_round2_ports.sample(1)[0])).to_dict()
            args.example_output.write_text(json.dumps(example,indent=2,sort_keys=True)+'\n')
            import hashlib
            report['example_sha256']=hashlib.sha256(test_round2_ports.canonical(example)).hexdigest()
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
        if not result.wasSuccessful(): raise SystemExit(1)

if __name__=='__main__': main()
