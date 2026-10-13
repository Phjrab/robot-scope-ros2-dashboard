#!/usr/bin/env python3
"""Finite replay from a reviewed sensor-only topic map in one isolated container.

Source /opt/ros/humble/setup.bash first. Never starts a driver or publishes motion.
Each run gets new evidence; failed output is retained. Runtime success is assessed
from logs and metrics, not this launcher's exit status alone.
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

CODE = Path(__file__).resolve().parent
SENSOR_TYPES = {'sensor_msgs/msg/Image', 'sensor_msgs/msg/CameraInfo', 'sensor_msgs/msg/Imu'}


def replay_args(spec, bag):
    mapping = spec['topics']
    if not mapping or len(mapping) > 8:
        raise ValueError('Explicit bounded sensor topic selection required')
    sources, destinations = [], []
    for row in mapping:
        src, dst, typ = row['source'], row['destination'], row['type']
        if not src.startswith('/') or not dst.startswith('/vslam_lab/'):
            raise ValueError('Absolute source and lab destination required')
        if typ not in SENSOR_TYPES and not (typ == 'tf2_msgs/msg/TFMessage' and src == '/tf_static' and dst == '/vslam_lab/tf_static'):
            raise ValueError('Only raw sensors and reviewed static TF may be replayed')
        if typ == 'tf2_msgs/msg/TFMessage' and spec.get('static_tf_sensor_only_verified') is not True:
            raise ValueError('Review TF contents; do not replay estimator frames')
        sources.append(src)
        destinations.append(dst)
    if len(set(sources)) != len(sources) or len(set(destinations)) != len(destinations):
        raise ValueError('Duplicate/aliased input topics')
    return ['ros2', 'bag', 'play', str(bag), '--clock', '100', '--rate', '1.0',
            '--delay', '3', '--wait-for-all-acked', '5000',
            '--disable-keyboard-controls', '--topics', *sources, '--remap',
            *(f'{s}:={d}' for s, d in zip(sources, destinations))]


def stop_owned(child):
    """A fresh process group per Popen; only stop unreaped children we created."""
    if child.poll() is not None:
        return
    for sig, wait in ((signal.SIGINT, 15), (signal.SIGTERM, 5), (signal.SIGKILL, 2)):
        if child.poll() is not None:
            return
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            return
        try:
            child.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            pass


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bag', type=Path, required=True)
    p.add_argument('--contract', type=Path, required=True)
    p.add_argument('--replay-spec', type=Path, required=True)
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--mode', choices=['vo', 'vio', 'slam_vo', 'slam_vio'], default='vo')
    p.add_argument('--timeout', type=float, default=180)
    a = p.parse_args()
    if not 1 <= a.timeout <= 900:
        p.error('Finite timeout 1..900 seconds required')
    guard = runpy.run_path(str(CODE / 'config' / 'launch_contract.py'))
    guard['isolated_environment'](os.environ)
    contract = json.loads(a.contract.read_text())
    guard['validate_input'](contract, a.mode, True)
    spec = json.loads(a.replay_spec.read_text())
    replay = replay_args(spec, a.bag)
    destinations = {row['destination']: row['type'] for row in spec['topics']}
    expected = {}
    for side in ('left', 'right'):
        expected[contract[side]['image_topic']] = 'sensor_msgs/msg/Image'
        expected[contract[side]['camera_info_topic']] = 'sensor_msgs/msg/CameraInfo'
    if a.mode in ('vio', 'slam_vio'):
        expected[contract['imu']['topic']] = 'sensor_msgs/msg/Imu'
    for name, typ in expected.items():
        if destinations.get(name) != typ:
            raise ValueError('Replay destination/type does not match the observed input contract')
    # Read-only database inventory must match selected topic types before publication.
    import rosbag2_py
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(a.bag), storage_id='sqlite3'),
                rosbag2_py.ConverterOptions('', ''))
    actual = {t.name: t.type for t in reader.get_all_topics_and_types()}
    for row in json.loads(a.replay_spec.read_text())['topics']:
        if actual.get(row['source']) != row['type']:
            raise ValueError('Replay type/source differs from inspected bag')
    del reader
    # Check input publisher vacancy without starting a daemon.
    import rclpy
    rclpy.init(args=[])
    probe = rclpy.create_node('replay_vacancy_probe', namespace='/vslam_lab')
    until = time.monotonic() + 2
    while time.monotonic() < until:
        rclpy.spin_once(probe, timeout_sec=.1)
    occupied = [r['destination'] for r in json.loads(a.replay_spec.read_text())['topics']
                if probe.count_publishers(r['destination'])]
    probe.destroy_node()
    rclpy.shutdown()
    if occupied:
        raise RuntimeError(f'Existing input publishers; refusing live/replay overlap: {occupied}')
    a.run_dir.mkdir(parents=False, exist_ok=False)
    launch = ['ros2', 'launch', str(CODE / 'launch' / 'vslam.launch.py'),
              f'input_contract:={a.contract}', f'run_dir:={a.run_dir}',
              f'mode:={a.mode}', 'use_sim_time:=true']
    metrics = ['python3', str(CODE / 'metrics' / 'collect.py'),
               '--output', str(a.run_dir / 'metrics.jsonl'), '--run-id', a.run_dir.name,
               '--domain', os.environ['ROS_DOMAIN_ID'], '--duration', str(a.timeout + 10),
               '--evidence-type', 'official_bag', '--use-sim-time',
               '--left', contract['left']['image_topic'], '--right', contract['right']['image_topic'],
               '--left-info', contract['left']['camera_info_topic'],
               '--right-info', contract['right']['camera_info_topic'],
               '--static-tf', '/vslam_lab/tf_static']
    if a.mode in ('vio', 'slam_vio'):
        metrics += ['--imu', contract['imu']['topic']]
    if a.mode.startswith('slam'):
        metrics += ['--slam-path', '/vslam_lab/visual_slam/tracking/slam_path']
    manifest = {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'mode': a.mode, 'evidence_type': 'official_bag',
                'clock_age_policy': 'N/A; no header/ROS clock relationship asserted',
                'domain': os.environ['ROS_DOMAIN_ID'], 'use_sim_time': True,
                'commands': {'vslam': launch, 'metrics': metrics, 'player': replay},
                'contract_sha256': hashlib.sha256(a.contract.read_bytes()).hexdigest(),
                'timeout_s': a.timeout, 'status': 'RUNNING'}
    mf = a.run_dir / 'run.json'
    mf.write_text(json.dumps(manifest, indent=2))
    children, logs = [], []
    interrupted = [False]
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: interrupted.__setitem__(0, True))
    def start(name, cmd):
        log = (a.run_dir / (name + '.log')).open('x')
        logs.append(log)
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        children.append((name, proc))
        return proc
    try:
        if spec.get('static_tf_evidence_path'):
            if any(row['type'] == 'tf2_msgs/msg/TFMessage' for row in spec['topics']):
                raise ValueError('Select either filtered static evidence or recorded static TF, never both')
            static_cmd = ['python3', str(CODE / 'selected_static_tf.py'),
                          '--evidence', spec['static_tf_evidence_path'],
                          '--contract', str(a.contract), '--duration', str(a.timeout + 20)]
            static = start('static_tf', static_cmd)
            manifest['commands']['static_tf'] = static_cmd
        vslam = start('vslam', launch)
        collector = start('collector', metrics)
        # Discovery and cuVSLAM setup precede playback. Liveness is not PASS evidence.
        time.sleep(5)
        if interrupted[0] or any(child.poll() is not None for _, child in children):
            raise RuntimeError('Launch/collector failed before playback')
        player = start('player', replay)
        deadline = time.monotonic() + a.timeout
        while player.poll() is None:
            if interrupted[0] or time.monotonic() >= deadline:
                raise RuntimeError('Interrupted or bounded replay timeout')
            if vslam.poll() is not None or collector.poll() is not None:
                raise RuntimeError('Node/collector exited during playback')
            time.sleep(.5)
        if player.returncode:
            raise RuntimeError(f'Player exit {player.returncode}')
        time.sleep(2)
        manifest['status'] = 'REPLAY_FINISHED_REQUIRES_METRICS_REVIEW'
    except BaseException as exc:
        manifest['status'] = 'FAILED'
        manifest['error'] = str(exc)
        raise
    finally:
        for name, child in reversed(children):
            stop_owned(child)
        manifest['child_exit_codes'] = {name: child.poll() for name, child in children}
        manifest['ended_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        mf.write_text(json.dumps(manifest, indent=2))
        for log in logs:
            log.close()


if __name__ == '__main__':
    main()
