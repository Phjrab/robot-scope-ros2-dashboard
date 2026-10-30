"""C4 hosted wrapper around the exact D3 image builder; owners stay read-only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from experiments.expansion_20261029.c4_runtime.ros_bridge.dependencies import load,PINS,REPO


def run(output):
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':
        raise RuntimeError('GITHUB_HOSTED_TEMPORARY_RUNNER_REQUIRED')
    paths=load(); output.mkdir(parents=True,exist_ok=True)
    receipt=dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
                 dependencies=PINS,status='NOT_RUN',native_started=False,device='DEVICE_NOT_RUN')
    name='c4-review-'+uuid.uuid4().hex[:12]; created=False
    def command(argv,**kwargs):
        return subprocess.run(argv,check=True,**kwargs)
    try:
        lock=output/'d3-image-lock.json'
        command([sys.executable,str(paths['d3']/'experiments/competition_nav2/container/manage.py'),'build','--lock',str(lock)])
        base=json.loads(lock.read_text())
        versions=dict(line.split('\t') for line in base['packages_tsv'].splitlines())
        nav={k:v for k,v in versions.items() if k.startswith('ros-humble-nav2-') or k=='ros-humble-navigation2'}
        if not nav or any(not v.startswith('1.1.20-') for v in nav.values()):
            raise RuntimeError('NAV2_1_1_20_REQUIRED:'+str(nav))
        receipt['nav2_packages']=nav
        receipt['d3_base_image']=base['image_id']
        iid=output/'c4-image-id.txt'
        directory=Path(__file__).parent
        command(['docker','build','--build-arg','BASE_IMAGE='+base['image_id'],'--iidfile',str(iid),
                 '-f',str(directory/'Dockerfile'),str(directory)])
        image=iid.read_text().strip(); receipt['image_id']=image
        deps=Path(os.environ['C4_ROS_DEP_ROOT']).resolve()
        argv=['docker','create','--name',name,'--network','none','--cap-drop','ALL','--security-opt','no-new-privileges',
            '--read-only','--pids-limit','256','--memory','4g','--cpus','4',
            '--user',f'{os.getuid()}:{os.getgid()}','--tmpfs','/tmp:rw,nosuid,nodev,size=512m,mode=1777',
            '--mount',f'type=bind,src={REPO},dst=/repo,readonly',
            '--mount',f'type=bind,src={deps},dst=/deps,readonly',
            '--mount',f'type=bind,src={output.resolve()},dst=/results',
            '-w','/repo','-e','C4_ROS_DEP_ROOT=/deps','-e','C4_NETWORK_NONE=1','-e','ROS_LOCALHOST_ONLY=1',
            '-e','ROS_DOMAIN_ID=194','-e','RMW_IMPLEMENTATION=rmw_fastrtps_cpp','-e','PYTHONDONTWRITEBYTECODE=1',
            '-e','PYTHONPATH=/repo:/repo/tests',image,'/opt/c4/bin/python','-m',
            'experiments.expansion_20261029.c4_runtime.ros_bridge.native_probe','/results/probe']
        receipt['command']=argv
        command(argv); created=True
        inspection=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
        receipt['network_mode']=inspection['HostConfig']['NetworkMode']
        receipt['mounts']=[dict(destination=m['Destination'],rw=m['RW']) for m in inspection['Mounts']]
        if (receipt['network_mode']!='none' or inspection['HostConfig']['Privileged']
                or inspection['HostConfig'].get('Devices') or any(m['rw'] for m in receipt['mounts'] if m['destination']!='/results')):
            raise RuntimeError('CONTAINER_ISOLATION_REJECTED')
        receipt['native_started']=True
        proc=subprocess.run(['docker','start','-a',name],check=False,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        (output/'native-output.log').write_text(proc.stdout)
        print(proc.stdout,flush=True)
        state=json.loads(subprocess.check_output(['docker','inspect',name]))[0]['State']
        receipt['exit_code']=state['ExitCode']; receipt['client_exit']=proc.returncode
        if state['ExitCode'] or proc.returncode: raise RuntimeError('NATIVE_PROBE_FAILED')
        # C3 consumes the exact saved real TCP response. This is a recorded-byte
        # compatibility check, not browser rendering or a new observation receipt.
        snapshot=output/'probe/http-snapshot.json'
        check=subprocess.run(['node',str(directory/'consumer_check.mjs'),
            str(paths['c3']/'robot_dashboard/static/features/obstacle_scene'),str(snapshot)],capture_output=True,text=True)
        (output/'c3-consumer.log').write_text(check.stdout+check.stderr)
        receipt['C3_exit']=check.returncode
        if check.returncode: raise RuntimeError('ACTUAL_C3_REJECTED')
        receipt['http_sha256']=hashlib.sha256(snapshot.read_bytes()).hexdigest()
        receipt['status']='PASS_WITH_EXPLICIT_UNPROVEN_BOUNDARIES'
    except Exception as exc:
        receipt['status']='FAIL'; receipt['error']=type(exc).__name__+':'+str(exc)
        raise
    finally:
        if created:
            subprocess.run(['docker','rm','-f',name],check=True)
            receipt['container_removed']=True
        # Verify peer blobs again after execution.
        load()
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
