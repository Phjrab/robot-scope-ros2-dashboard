"""Offline-testable evidence/contract helpers; no network or motion authority."""
from __future__ import annotations

import json
import math
import numbers
import os
from pathlib import Path
import tempfile
import threading
import time


def json_value(value):
    """Normalize ROS/numpy scalars, reject invalid evidence, redact credentials."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('nonfinite evidence')
        return result
    if isinstance(value, dict):
        return {str(k): '[REDACTED]' if str(k).lower() in {
            'lease_id', 'token', 'password', 'authorization', 'secret'
        } else json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    raise TypeError(f'unsupported evidence type: {type(value).__name__}')


def encoded(value):
    return (json.dumps(json_value(value), allow_nan=False, ensure_ascii=True) + '\n').encode()


def write_json(path, value):
    """Do not truncate an existing good artifact if conversion/write fails."""
    data = encoded(value)
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Journal:
    """Append complete rows while collecting, with bounded memory and periodic fsync.

    A hard power loss may lose up to one second since the last fsync. A partial
    trailing row after process termination is not valid evidence. Never overwrite
    an earlier recording. File permissions are private on POSIX.
    """
    def __init__(self, path, *, clock=time.monotonic):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.stream = os.fdopen(fd, 'wb')
        self.lock = threading.Lock()
        self.clock = clock
        self.synced = clock()
        self.count = 0

    def append(self, row):
        data = encoded(row)
        with self.lock:
            self.stream.write(data)
            self.stream.flush()
            self.count += 1
            now = self.clock()
            if now - self.synced >= 1.:
                os.fsync(self.stream.fileno())
                self.synced = now

    def close(self):
        with self.lock:
            if not self.stream.closed:
                try:
                    self.stream.flush()
                    os.fsync(self.stream.fileno())
                finally:
                    self.stream.close()


def stop_and_finalize(stop, readback, cleanup, artifacts, *, save=write_json):
    """Every cleanup step runs even if STOP, ROS shutdown or one export fails.

    STOP acknowledgement alone is not proof of stopping. Return a separately
    checked fresh readback; a caller must report unconfirmed STOP as failure.
    Call only for a trial that has taken control, not a failed read-only preflight.
    """
    errors = []
    result = {'stop_requested': False, 'stop_confirmed': False}
    try:
        stop()
        result['stop_requested'] = True
    except Exception as exc:
        errors.append('stop:' + type(exc).__name__)
    try:
        snapshot = readback()
        c = snapshot['control']
        result['stop_confirmed'] = (
            c['estop_latched'] is True and c['lease']['active'] is False
            and c['command']['deadman'] is False
            and all(type(c['command'][k]) in (int, float) and c['command'][k] == 0
                    for k in ('linear_x', 'linear_y', 'angular_z')))
        result['readback'] = snapshot
    except Exception as exc:
        errors.append('readback:' + type(exc).__name__)
    for name, action in cleanup:
        try:
            action()
        except Exception as exc:
            errors.append(name + ':' + type(exc).__name__)
    for path, value in artifacts:
        try:
            save(path, value)
        except Exception as exc:
            errors.append(Path(path).name + ':' + type(exc).__name__)
    result['errors'] = errors
    return result


def initial_pose_payload(map_id, map_revision, pose):
    # job_id selects a different (manual experiment) API path. It is never part
    # of the standard stored-map initial-pose request.
    import re
    if not re.fullmatch('[0-9a-f]{24}', map_id) or not re.fullmatch('[0-9a-f]{64}', map_revision):
        raise ValueError('invalid map identity')
    if set(pose) != {'x', 'y', 'yaw'}:
        raise ValueError('pose must contain x/y/yaw only')
    if any(isinstance(v, bool) or not isinstance(v, numbers.Real) for v in pose.values()):
        raise ValueError('invalid pose number')
    return {'map_id': map_id, 'map_revision': map_revision, 'pose': json_value(pose)}


def check_navigation_trial(navigation, control, plan):
    """Read-only check of saved/current snapshots, NOT permission to send a goal.

    Preserve the field trial's guards. The healthy navigation lease is required,
    unlike a manual probe which requires no existing lease. Do not use assert:
    Python -O must not remove these checks.
    """
    n, c = navigation, control['control'] if 'control' in control else control
    if n['pipeline']['state'] != 'running' or not plan['job_id'] or n['pipeline']['job_id'] != plan['job_id']:
        raise ValueError('navigation job changed')
    if n['safety']['can_send_goal'] is not True or n['goal']['state'] == 'active':
        raise ValueError('navigation not ready for a new goal')
    if n['localization_health']['state'] != 'READY' or n['operational_localization']['ready'] is not True:
        raise ValueError('localization not ready')
    if c['estop_latched'] is not False or c['lease']['active'] is not True or c['lease']['input_source'] != 'navigation':
        raise ValueError('navigation lease missing or stopped')
    if c['command']['deadman'] is not False or any(c['command'][k] != 0 for k in ('linear_x', 'linear_y', 'angular_z')):
        raise ValueError('nonzero command before trial')
    if c['bridge']['motion_observation']['quality'] != 'READY':
        raise ValueError('motion observation invalid')
    if n['map']['id'] != plan['map_id'] or n['map']['revision'] != plan['map_revision']:
        raise ValueError('map changed')
    p, start = n['localization']['pose'], plan['start']
    values = [p[k] for k in ('x', 'y', 'yaw')] + [start[k] for k in ('x', 'y', 'yaw')]
    if any(isinstance(v, bool) or not isinstance(v, numbers.Real) or not math.isfinite(v) for v in values):
        raise ValueError('invalid start pose')
    yaw_error = abs(math.atan2(math.sin(p['yaw'] - start['yaw']), math.cos(p['yaw'] - start['yaw'])))
    if math.hypot(p['x'] - start['x'], p['y'] - start['y']) >= .05 or yaw_error >= .1:
        raise ValueError('start position or direction changed')
    live = n['parameter_evidence']['live_ros']
    v = live['parameters']['/controller_server']
    if live['status'] != 'current' or v['FollowPath.desired_linear_vel'] != .2 or v['FollowPath.use_collision_detection'] is not True:
        raise ValueError('live controller policy mismatch')
    return {'snapshot_checks_passed': True, 'motion_authorized': False}
