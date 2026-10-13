#!/usr/bin/env python3
"""Owned Docker sessions: no host ROS, host network, whole-home mounts or reuse."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

LABEL = 'org.robot-scope.isaac-vslam.owner'
ROOT = Path('/home/unitree/experiments/isaac-vslam-lab')


def call(args):
    return subprocess.check_output(args, text=True).strip()


def inspect(cid):
    return json.loads(call(['docker', 'inspect', cid]))[0]


def owned(state):
    obj = inspect(state['container_id'])
    if (obj['Id'] != state['container_id'] or
            obj['Config'].get('Labels', {}).get(LABEL) != state['owner'] or
            obj['Created'] != state['created']):
        raise RuntimeError('Container identity/ownership mismatch; refusing operation')
    return obj


def disk_gate(root):
    d = shutil.disk_usage(root)
    if d.free < max(10 * 1024**3, d.total // 10):
        raise RuntimeError('Free space below max(10 GiB, 10% filesystem)')


def start(a):
    raw_root = Path(a.root)
    root = raw_root.resolve(strict=True)
    if root != ROOT or raw_root.is_symlink():
        raise RuntimeError('Only the dedicated runtime root is supported')
    for name in ('runs', 'code', 'sources', 'data'):
        child = root / name
        if child.is_symlink() or child.resolve(strict=True) != child or not child.is_dir():
            raise RuntimeError('Runtime subdirectories must be real dedicated directories')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', a.run):
        raise ValueError('Invalid run ID')
    if not re.fullmatch(r'(?:nvcr\.io/nvidia/isaac/ros@)?sha256:[0-9a-f]{64}', a.image):
        raise ValueError('Image must be an immutable NVIDIA registry digest or local image ID')
    if not 1 <= a.domain <= 101:
        raise ValueError('Explicit non-default lab domain (1..101) required')
    if not a.resource_window_confirmed:
        raise ValueError('Inspect current load/builds/acceptance first; resource window required')
    # Visible host participants only. Docker network namespace provides further isolation.
    for p in Path('/proc').glob('[0-9]*/environ'):
        try:
            if f'ROS_DOMAIN_ID={a.domain}'.encode() in p.read_bytes().split(b'\0'):
                raise RuntimeError('Candidate ROS domain observed on host; choose another')
        except PermissionError:
            pass
        except FileNotFoundError:
            pass
    disk_gate(root)
    archive = root / 'recordings'
    archive.mkdir(mode=0o700, exist_ok=True)
    if archive.is_symlink() or archive.resolve(strict=True) != archive:
        raise RuntimeError('Recording archive must be a real dedicated directory')
    run = root / 'runs' / a.run
    run.mkdir(mode=0o700, parents=False, exist_ok=False)
    owner = str(uuid.uuid4())
    camera_devices = []
    if getattr(a, 'camera_usb', None):
        if not a.camera_window_confirmed:
            raise ValueError('Fresh exclusive camera handoff is required')
        device = Path(a.camera_usb)
        if not re.fullmatch(r'/dev/bus/usb/[0-9]{3}/[0-9]{3}', str(device)) or not device.is_char_device():
            raise ValueError('Only one exact observed USB device is supported')
        import stat
        number = device.stat().st_rdev
        match = False
        for sysdev in Path('/sys/bus/usb/devices').glob('*'):
            try:
                major, minor = map(int, (sysdev / 'dev').read_text().strip().split(':'))
                if (major, minor) == (os.major(number), os.minor(number)):
                    match = ((sysdev / 'idVendor').read_text().strip() == '8086' and
                             (sysdev / 'idProduct').read_text().strip() == '0b3a')
            except (OSError, ValueError):
                pass
        if not match:
            raise ValueError('USB node is not the observed Intel D435i (8086:0b3a)')
        camera_devices = [str(device)]
    cmd = ['docker', 'create', '--name', 'vslam-lab-' + a.run, '--label', LABEL + '=' + owner,
           '--label', 'org.robot-scope.isaac-vslam.run=' + a.run,
           '--runtime', 'nvidia', '--network', 'bridge' if a.setup_network else 'none',
           '--cpus', str(a.cpus), '--memory', '6g', '--memory-swap', '6g', '--pids-limit', '512',
           '--shm-size', '512m', '--security-opt', 'no-new-privileges',
           '--env', f'ROS_DOMAIN_ID={a.domain}', '--env', 'ROS_LOCALHOST_ONLY=1',
           '--env', f'VSLAM_LAB_RUN_ID={a.run}',
           '--env', 'RMW_IMPLEMENTATION=rmw_fastrtps_cpp',
           '--env', 'ROS_LOG_DIR=/lab/run/ros_logs', '--env', 'ROS_HOME=/lab/run/ros_home',
           '--env', 'NVIDIA_VISIBLE_DEVICES=all', '--env', 'NVIDIA_DRIVER_CAPABILITIES=all',
           '--env', 'OMP_NUM_THREADS=2', '--env', 'MAKEFLAGS=-j2',
           '--mount', f'type=bind,src={root / "code"},dst=/lab/code,readonly',
           '--mount', f'type=bind,src={root / "sources"},dst=/lab/sources,readonly',
           '--mount', f'type=bind,src={root / "data"},dst=/lab/data,readonly',
           '--mount', f'type=bind,src={run},dst=/lab/run',
           '--mount', f'type=bind,src={archive},dst=/lab/recordings',
           '--workdir', '/lab/run', '--entrypoint', '/bin/bash', a.image,
           '-c', 'exec sleep infinity']
    # Exact camera USB only after a fresh handoff, never /dev or whole USB bus.
    for device in camera_devices:
        cmd[2:2] = ['--device', device + ':' + device + ':rw']
    cid = call(cmd)
    obj = inspect(cid)
    state = {'schema': 1, 'run_id': a.run, 'owner': owner, 'container_id': obj['Id'],
             'created': obj['Created'], 'image_requested': a.image, 'image_id': obj['Image'],
             'domain': a.domain, 'network': obj['HostConfig']['NetworkMode'],
             'cpus': a.cpus, 'memory_bytes': obj['HostConfig']['Memory'],
             'camera_devices': camera_devices, 'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'docker_create_argv': cmd}
    (run / 'ownership.json').write_text(json.dumps(state, indent=2) + '\n')
    subprocess.run(['docker', 'start', cid], check=True)
    print(run / 'ownership.json')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    s = sub.add_parser('start')
    s.add_argument('--root', default=str(ROOT))
    s.add_argument('--run', required=True)
    s.add_argument('--image', required=True)
    s.add_argument('--domain', type=int, required=True)
    s.add_argument('--cpus', type=float, default=2)
    s.add_argument('--resource-window-confirmed', action='store_true')
    s.add_argument('--setup-network', action='store_true', help='Bridge NAT for container apt only')
    s.add_argument('--camera-usb', help='One observed Intel D435i /dev/bus/usb/BBB/DDD node')
    s.add_argument('--camera-window-confirmed', action='store_true')
    for action in ('exec', 'cleanup', 'inspect'):
        q = sub.add_parser(action)
        q.add_argument('--state', required=True)
        if action == 'exec':
            q.add_argument('command', nargs=argparse.REMAINDER)
    a = p.parse_args()
    if a.action == 'start':
        if not 0 < a.cpus <= 2:
            p.error('Initial CPU limit is at most 2 cores')
        start(a)
        return
    state = json.loads(Path(a.state).read_text())
    obj = owned(state)
    if a.action == 'inspect':
        print(json.dumps(obj, indent=2))
    elif a.action == 'cleanup':
        if obj['State']['Running']:
            subprocess.run(['docker', 'stop', '--time', '20', state['container_id']], check=True)
        print('Owned container stopped; logs, data and stopped container retained.')
    else:
        cmd = a.command[1:] if a.command[:1] == ['--'] else a.command
        if not cmd:
            p.error('exec requires an explicit command')
        raise SystemExit(subprocess.call(['docker', 'exec', state['container_id'],
            'env', '-u', 'CYCLONEDDS_URI', '-u', 'FASTRTPS_DEFAULT_PROFILES_FILE',
            '-u', 'FASTDDS_DEFAULT_PROFILES_FILE',
            '-u', 'ROS_DISCOVERY_SERVER', f'ROS_DOMAIN_ID={state["domain"]}',
            'ROS_LOCALHOST_ONLY=1', 'RMW_IMPLEMENTATION=rmw_fastrtps_cpp',
            f'VSLAM_LAB_RUN_ID={state["run_id"]}',
            'VSLAM_LAB_DDS_PROFILE=local-shm-v1',
            'FASTRTPS_DEFAULT_PROFILES_FILE=/lab/code/config/fastdds-local.xml', *cmd]))


if __name__ == '__main__':
    main()
