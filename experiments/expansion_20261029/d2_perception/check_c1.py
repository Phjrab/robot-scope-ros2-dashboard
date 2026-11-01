"""Read-only compatibility check; C1 owns all wire validation."""
import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from robot_dashboard.obstacle_fusion_core import Tracker, process_lidar
from .scenarios import metadata, scene

PIN='2402c02c6f91ba54064894b21735e01b98610acd'


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--repo',default='.')
    args=parser.parse_args()
    # Explicit pinned file only; never merge/copy into submission or follow HEAD.
    content=subprocess.check_output(['git','-C',args.repo,'show',PIN+':robot_dashboard/expansion_contracts/messages.py'])
    with tempfile.TemporaryDirectory(prefix='d2-c1-readonly-') as tmp:
        path=Path(tmp)/'messages.py'; path.write_bytes(content)
        spec=importlib.util.spec_from_file_location('d2_pinned_c1',path)
        module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)
        points,ground,_=scene(2); output=Tracker().step(process_lidar(points,metadata(),ground=ground))
        module.ObstacleFrame.from_dict(output['obstacle_frame'])
        print(json.dumps({'dependency_sha':PIN,'validator':'ObstacleFrame.from_dict','status':'PASS','evidence_kind':'SYNTHETIC'}))

if __name__=='__main__': main()
