#!/usr/bin/env python3
"""Offline ROS bag input evidence, without publishing any recorded messages."""
import argparse
from contextlib import closing
import dataclasses
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import sqlite3
import struct


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def plain(value):
    """Convert a rosbags dataclass/numpy value without depending on numpy here."""
    if dataclasses.is_dataclass(value):
        return {field.name: plain(getattr(value, field.name)) for field in dataclasses.fields(value)
                if not field.name.startswith('__')}
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if hasattr(value, 'tolist'):
        return value.tolist()
    return value


def decoder(backend):
    if backend in ('auto', 'rclpy'):
        try:
            from rclpy.serialization import deserialize_message
            from rosidl_runtime_py.utilities import get_message
            from rosidl_runtime_py.convert import message_to_ordereddict
            return (lambda data, typ: message_to_ordereddict(deserialize_message(data, get_message(typ))),
                    {'backend': 'rclpy', 'types': 'installed ROS interface definitions'})
        except ImportError:
            if backend == 'rclpy':
                raise
    from rosbags.typesys import Stores, get_typestore
    store = get_typestore(Stores.ROS2_HUMBLE)
    return (lambda data, typ: plain(store.deserialize_cdr(data, typ)),
            {'backend': 'rosbags', 'version': importlib.metadata.version('rosbags'),
             'types': 'ROS2_HUMBLE'})


def cdr_header(data):
    """Read the leading std_msgs/Header of Humble Image/CameraInfo/Imu CDR.

    Reading only the header avoids decoding/copying every raw image payload.
    Unknown CDR formats fail closed rather than silently producing clock data.
    """
    if len(data) < 16 or data[:2] not in (b'\x00\x00', b'\x00\x01'):
        raise ValueError('Unsupported/truncated CDR encapsulation')
    endian = '<' if data[1] == 1 else '>'
    sec, nano, size = struct.unpack_from(endian + 'iII', data, 4)
    if nano >= 1000000000 or size < 1 or len(data) < 16 + size or data[15 + size] != 0:
        raise ValueError('Invalid CDR header timestamp or frame string')
    return sec * 1000000000 + nano, data[16:15 + size].decode('utf-8')


def summary(values):
    if not values:
        return {'n': 0, 'p50': None, 'p95': None}
    ordered = sorted(values)
    def quantile(fraction):
        index = (len(ordered) - 1) * fraction
        lower = math.floor(index)
        upper = math.ceil(index)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)
    return {'n': len(values), 'p50': quantile(.5), 'p95': quantile(.95)}


def camera_info_issues(info):
    issues = []
    for key, size in (('k', 9), ('r', 9), ('p', 12)):
        values = info.get(key, [])
        if len(values) != size or not all(isinstance(x, (float, int)) and math.isfinite(x) for x in values):
            issues.append(f'{key} is not a finite length-{size} calibration matrix')
    if info.get('width', 0) <= 0 or info.get('height', 0) <= 0:
        issues.append('Nonpositive CameraInfo dimensions')
    if len(info.get('k', [])) == 9 and (info['k'][0] <= 0 or info['k'][4] <= 0):
        issues.append('Nonpositive raw focal lengths')
    return issues


def inspect(bag, deserialize, backend_info):
    result = {'format': 'offline-sqlite-cdr', 'bag': str(bag), 'files': [], 'topics': {},
              'decoder': backend_info, 'static_transform_inventory': [],
              'limitations': [
                  'Offline schema/calibration consistency evidence only; no VSLAM/GPU execution.',
                  'Header minus recorder time is not end-to-end latency without clock relationship evidence.',
                  'Static transform content must be reviewed before setting sensor-only replay approval.',
                  'Declared IMU units, axes and physical calibration require sensor documentation/observation.']}
    header_samples, static_pairs = {}, {}
    databases = sorted(bag.glob('*.db3'))
    if not databases:
        raise ValueError('No .db3 files; this inspector supports SQLite ROS 2 bags only')
    for db in databases:
        with closing(sqlite3.connect(f'file:{db}?mode=ro', uri=True)) as con:
            result['files'].append({'name': db.name, 'sha256': sha256(db), 'bytes': db.stat().st_size})
            for tid, name, typ in con.execute('select id,name,type from topics'):
                count, start, end = con.execute('select count(*),min(timestamp),max(timestamp) from messages where topic_id=?', (tid,)).fetchone()
                row = result['topics'].setdefault(name, {'type': typ, 'count': 0, 'bag_start_ns': None, 'bag_end_ns': None})
                if row['type'] != typ:
                    raise ValueError(f'Topic type changed between bag segments: {name}')
                row['count'] += count
                if start is not None:
                    row['bag_start_ns'] = min(x for x in (row['bag_start_ns'], start) if x is not None)
                    row['bag_end_ns'] = max(x for x in (row['bag_end_ns'], end) if x is not None)
                if typ not in ('sensor_msgs/msg/Image', 'sensor_msgs/msg/CameraInfo',
                               'sensor_msgs/msg/Imu', 'tf2_msgs/msg/TFMessage'):
                    continue
                for recorded_ns, data in con.execute('select timestamp,data from messages where topic_id=? order by timestamp', (tid,)):
                    first = 'first' not in row
                    if typ != 'tf2_msgs/msg/TFMessage':
                        stamp, frame_id = cdr_header(data)
                        header_samples.setdefault(name, []).append((recorded_ns, stamp, frame_id))
                    if first or typ in ('tf2_msgs/msg/TFMessage', 'sensor_msgs/msg/CameraInfo'):
                        msg = deserialize(data, typ)
                    if first:
                        row['first'] = ({key: msg[key] for key in ('header', 'encoding', 'height', 'width', 'step')}
                                        if typ == 'sensor_msgs/msg/Image' else msg)
                    if typ == 'sensor_msgs/msg/CameraInfo':
                        calibration = {k: v for k, v in msg.items() if k != 'header'}
                        digest = hashlib.sha256(json.dumps(calibration, sort_keys=True).encode()).hexdigest()
                        variants = row.setdefault('calibration_variants', {})
                        if digest not in variants:
                            if len(variants) >= 32:
                                raise ValueError(f'Too many CameraInfo variants; review bag {name}')
                            variants[digest] = {'camera_info': calibration, 'count': 0,
                                                'issues': camera_info_issues(calibration)}
                        variants[digest]['count'] += 1
                    if typ == 'tf2_msgs/msg/TFMessage' and name == '/tf_static':
                        for transform in msg['transforms']:
                            key = (transform['header']['frame_id'], transform['child_frame_id'])
                            entry = static_pairs.setdefault(key, {'parent': key[0], 'child': key[1], 'variants': []})
                            value = transform['transform']
                            if value not in entry['variants']:
                                if len(entry['variants']) >= 32:
                                    raise ValueError(f'Static TF changes repeatedly: {key}')
                                entry['variants'].append(value)
    for name, samples in header_samples.items():
        samples.sort(key=lambda sample: sample[0])
        row = result['topics'][name]
        stamps = [sample[1] for sample in samples]
        deltas = [(b-a)/1e6 for a, b in zip(stamps, stamps[1:])]
        row['header_statistics'] = {
            'sample_count': len(samples), 'frames': sorted({sample[2] for sample in samples}),
            'first_stamp_ns': stamps[0], 'last_stamp_ns': stamps[-1],
            'nonpositive_stamp_intervals': sum(value <= 0 for value in deltas),
            'stamp_interval_ms': summary(deltas),
            'mean_stamp_fps': (len(stamps)-1)*1e9/(stamps[-1]-stamps[0]) if stamps[-1] > stamps[0] else None,
            'recorder_minus_header_ms_NOT_LATENCY': summary([(r-s)/1e6 for r, s, _ in samples]),
        }
    result['static_transform_inventory'] = list(static_pairs.values())
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bag', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--backend', choices=('auto', 'rclpy', 'rosbags'), default='auto',
                   help='rosbags is optional for offline macOS analysis; rclpy stays default when installed')
    a = p.parse_args()
    if a.output.exists():
        p.error('Refusing to overwrite evidence')
    deserialize, info = decoder(a.backend)
    result = inspect(a.bag, deserialize, info)
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
