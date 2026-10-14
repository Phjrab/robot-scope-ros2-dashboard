#!/usr/bin/env python3
"""Finite owned camera+VO/VIO trial. No motion commands or operational services.

Source Humble and the pinned wrapper overlay, then use labctl exec. Camera
ownership must be checked freshly before each launch. Metadata is not PASS.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import time

from run_bag import stop_owned

CODE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--camera-contract', type=Path, required=True)
    p.add_argument('--input-contract', type=Path)
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--mode', choices=['input', 'vo', 'vio', 'slam_vo', 'slam_vio'], required=True)
    p.add_argument('--duration', type=float, required=True)
    p.add_argument('--stationary-confirmed', action='store_true')
    p.add_argument('--record-seconds', type=float, default=0)
    p.add_argument('--clock-evidence', default='')
    p.add_argument('--save-map-after', type=float, default=0, help='SLAM only; seconds after collection starts')
    a = p.parse_args()
    if not 1 <= a.duration <= 900 or not 0 <= a.record_seconds <= 60:
        p.error('Finite observation 1..900 s and recording 0..60 s required')
    if a.save_map_after and (not a.mode.startswith('slam') or not 10 <= a.save_map_after <= a.duration - 20):
        p.error('Map save requires SLAM and 20 s remaining for the bounded call')
    guard = runpy.run_path(str(CODE / 'config' / 'launch_contract.py'))
    guard['isolated_environment'](os.environ)
    camera = json.loads(a.camera_contract.read_text())
    camera_imu = a.mode in ('input', 'vio', 'slam_vio')
    guard['validate_camera'](camera, '640x480x30', camera_imu, 200 if camera_imu else 0, 100 if camera_imu else 0, 'preserve')
    contract = json.loads(a.input_contract.read_text()) if a.input_contract else None
    if a.mode != 'input':
        if not contract:
            p.error('Observed input contract required')
        guard['validate_input'](contract, a.mode, False)
    a.run_dir.mkdir(parents=False, exist_ok=False)
    camera_cmd = ['ros2', 'launch', str(CODE / 'launch/camera.launch.py'),
                  f'camera_contract:={a.camera_contract}', f'run_dir:={a.run_dir}',
                  'stereo_profile:=640x480x30', f'enable_imu:={str(camera_imu).lower()}',
                  f'gyro_fps:={200 if camera_imu else 0}',
                  f'accel_fps:={100 if camera_imu else 0}', 'emitter:=preserve']
    collector_cmd = ['python3', str(CODE / 'metrics/collect.py'), '--output',
                     str(a.run_dir / 'metrics.jsonl'), '--run-id', a.run_dir.name,
                     '--domain', os.environ['ROS_DOMAIN_ID'], '--duration', str(a.duration),
                     '--evidence-type', 'live_stationary' if a.stationary_confirmed else 'live_input']
    if camera_imu:
        collector_cmd += ['--imu', '/vslam_lab/camera/imu']
    if contract:
        collector_cmd += ['--left', contract['left']['image_topic'], '--right', contract['right']['image_topic'],
                          '--left-info', contract['left']['camera_info_topic'], '--right-info', contract['right']['camera_info_topic']]
    if a.clock_evidence:
        collector_cmd += ['--clock-contract-evidence', a.clock_evidence]
    if a.mode.startswith('slam'):
        collector_cmd += ['--slam-path', '/vslam_lab/visual_slam/tracking/slam_path']
    manifest = {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'mode': a.mode, 'stationarity_confirmed_by_operator': a.stationary_confirmed,
                'domain': os.environ['ROS_DOMAIN_ID'], 'use_sim_time': False,
                'duration_s': a.duration, 'emitter': 'preserved; no option requested',
                'camera_contract_sha256': hashlib.sha256(a.camera_contract.read_bytes()).hexdigest(),
                'code_sha256': {str(path.relative_to(CODE)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in CODE.rglob('*') if path.is_file() and not path.name.startswith('.') and path.suffix in ('.py', '.json', '.xml')},
                'commands': {'camera': camera_cmd, 'collector': collector_cmd}, 'status': 'RUNNING'}
    if contract:
        manifest['input_contract_sha256'] = hashlib.sha256(a.input_contract.read_bytes()).hexdigest()
    mf = a.run_dir / 'run.json'
    children, logs, interrupted = [], [], [False]
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: interrupted.__setitem__(0, True))
    def start(name, cmd):
        log = (a.run_dir / (name + '.log')).open('x')
        logs.append(log)
        child = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        children.append((name, child))
        return child
    def snapshot(name, cmd):
        log = (a.run_dir / name).open('x')
        with log:
            result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=15)
        manifest.setdefault('snapshot_exit_codes', {})[name] = result.returncode
    try:
        start('camera', camera_cmd)
        time.sleep(5)
        if interrupted[0] or any(c.poll() is not None for _, c in children):
            raise RuntimeError('Camera exited before observation')
        if a.mode != 'input':
            cmd = ['ros2', 'launch', str(CODE / 'launch/vslam.launch.py'),
                   f'input_contract:={a.input_contract}', f'run_dir:={a.run_dir}',
                   f'mode:={a.mode}', 'use_sim_time:=false']
            manifest['commands']['vslam'] = cmd
            start('vslam', cmd)
            time.sleep(3)
        collector = start('collector', collector_cmd)
        snapshot('topics.txt', ['ros2', 'topic', 'list', '-t', '--no-daemon'])
        snapshot('camera-parameters.yaml', ['ros2', 'param', 'dump', '/vslam_lab/camera/driver'])
        if a.mode != 'input':
            snapshot('vslam-parameters.yaml', ['ros2', 'param', 'dump', '/vslam_lab/visual_slam_node'])
        if a.record_seconds:
            bagroot = Path('/lab/recordings')
            if not bagroot.is_dir():
                raise RuntimeError('Shared lab recording archive mount is required')
            session = os.environ.get('VSLAM_LAB_RUN_ID')
            if not session:
                raise RuntimeError('labctl session identity is required for recording')
            suffix = hashlib.sha256((session + '/' + a.run_dir.name).encode()).hexdigest()[:8]
            recording_id = session[:30] + '-' + a.run_dir.name[:16] + '-' + suffix
            cmd = ['python3', str(CODE / 'bounded_record.py'), '--bag-root', str(bagroot),
                   '--run-id', recording_id, '--domain', os.environ['ROS_DOMAIN_ID'],
                   '--seconds', str(a.record_seconds), '--camera-window-confirmed']
            for topic in ('/vslam_lab/camera/infra1/image_rect_raw', '/vslam_lab/camera/infra1/camera_info',
                          '/vslam_lab/camera/infra2/image_rect_raw', '/vslam_lab/camera/infra2/camera_info',
                          '/vslam_lab/camera/imu', '/vslam_lab/tf_static'):
                cmd += ['--topic', topic]
            manifest['commands']['recorder'] = cmd
            start('recorder', cmd)
        collection_started = time.monotonic()
        deadline = collection_started + a.duration + 20
        map_started = False
        while collector.poll() is None:
            if interrupted[0] or time.monotonic() >= deadline:
                raise RuntimeError('Trial interrupted or timeout')
            if any(c.poll() is not None for n, c in children if n in ('camera', 'vslam')):
                raise RuntimeError('Sensor/estimator exited during observation')
            if a.save_map_after and not map_started and time.monotonic() - collection_started >= a.save_map_after:
                cmd = ['python3', str(CODE / 'save_map.py'), '--run-dir', str(a.run_dir), '--timeout', '15']
                manifest['commands']['save_map'] = cmd
                start('save_map', cmd)
                map_started = True
            time.sleep(.5)
        if collector.returncode:
            raise RuntimeError('Collector failed')
        manifest['status'] = 'OBSERVATION_FINISHED_REQUIRES_METRICS_REVIEW'
    except BaseException as exc:
        manifest['status'], manifest['error'] = 'FAILED', str(exc)
        raise
    finally:
        for _, child in reversed(children):
            stop_owned(child)
        manifest['child_exit_codes'] = {name: child.poll() for name, child in children}
        manifest['ended_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        mf.write_text(json.dumps(manifest, indent=2) + '\n')
        for log in logs:
            log.close()


if __name__ == '__main__':
    main()
