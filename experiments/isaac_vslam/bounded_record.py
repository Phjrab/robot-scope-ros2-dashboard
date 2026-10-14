#!/usr/bin/env python3
"""Record selected lab inputs for <=60 s with guarded storage and owned cleanup.

Use the SAME dedicated --bag-root for every live recording: its entire contents
count toward the cumulative budget. A lock coordinates this recorder only, not
other camera users. Camera ownership must already be coordinated separately.

Polling is not a filesystem hard quota. The stop threshold reserves one polling
interval, both shutdown timeouts, the bounded ROS cache and metadata headroom at
the declared maximum write rate. A rate-bound or final-cap violation is reported
as failure, never hidden as a successful bounded recording. Hard guarantees
against arbitrary publishers/bursts require a separately provisioned FS quota.
"""
import argparse
import datetime
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

MIB = 1024**2
GIB = 1024**3
RUN_CAP = 2 * GIB
ARCHIVE_CAP = 8 * GIB
POLL_SECONDS = 1.0
INT_TIMEOUT = 3.0
TERM_TIMEOUT = 2.0
CACHE_BYTES = 32 * MIB
METADATA_RESERVE = 16 * MIB
STEREO_TOPICS = (
    '/vslam_lab/camera/infra1/image_rect_raw',
    '/vslam_lab/camera/infra1/camera_info',
    '/vslam_lab/camera/infra2/image_rect_raw',
    '/vslam_lab/camera/infra2/camera_info',
)
STATIC_TOPIC = '/vslam_lab/tf_static'
IMU_TOPIC = '/vslam_lab/camera/imu'
ALLOWED_TOPICS = frozenset((*STEREO_TOPICS, STATIC_TOPIC, IMU_TOPIC))
UNSAFE_ENV = ('CYCLONEDDS_URI', 'FASTRTPS_DEFAULT_PROFILES_FILE',
              'FASTDDS_DEFAULT_PROFILES_FILE', 'ROS_DISCOVERY_SERVER')


def validate_environment(domain, env):
    if not 1 <= domain <= 101 or env.get('ROS_DOMAIN_ID') != str(domain):
        raise ValueError('Explicit lab domain must match ROS_DOMAIN_ID (1..101)')
    if env.get('ROS_LOCALHOST_ONLY') != '1':
        raise ValueError('ROS_LOCALHOST_ONLY=1 is required')
    if env.get('RMW_IMPLEMENTATION') != 'rmw_fastrtps_cpp':
        raise ValueError('Explicit rmw_fastrtps_cpp is required for this lab')
    approved = (env.get('VSLAM_LAB_DDS_PROFILE') == 'local-shm-v1' and
                env.get('FASTRTPS_DEFAULT_PROFILES_FILE') == '/lab/code/config/fastdds-local.xml')
    if any(env.get(key) for key in UNSAFE_ENV if key != 'FASTRTPS_DEFAULT_PROFILES_FILE') or (env.get('FASTRTPS_DEFAULT_PROFILES_FILE') and not approved):
        raise ValueError('Inherited DDS routing/profile configuration is not permitted')


def validate_topics(topics):
    if len(topics) != len(set(topics)) or not set(topics) <= ALLOWED_TOPICS:
        raise ValueError('Only unique explicitly allowlisted lab camera/static inputs are permitted')
    if not set((*STEREO_TOPICS, STATIC_TOPIC)) <= set(topics):
        raise ValueError('Both stereo Image/CameraInfo pairs and lab static TF are required')
    return list(topics)


def tree_bytes(root):
    """Include all files, including SQLite WAL/cache artifacts; reject symlinks."""
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError('Symlink in recording archive: ' + str(path))
        for name in files:
            try:
                total += (Path(directory) / name).stat().st_size
            except FileNotFoundError:
                pass  # SQLite can remove its WAL while a scan is in progress.
    return total


def reserve_bytes(max_write_rate):
    if not math.isfinite(max_write_rate) or max_write_rate <= 0:
        raise ValueError('Finite positive maximum write rate is required')
    return math.ceil(max_write_rate * (POLL_SECONDS + INT_TIMEOUT + TERM_TIMEOUT)) + CACHE_BYTES + METADATA_RESERVE


def quota_reason(run_bytes, archive_bytes, disk, reserve):
    """Thresholds are total-recording limits, independent of file splitting."""
    if run_bytes + reserve >= RUN_CAP:
        return 'run_budget_reserve'
    if archive_bytes + reserve >= ARCHIVE_CAP:
        return 'archive_budget_reserve'
    if disk.free - reserve <= max(10 * GIB, math.ceil(disk.total * 0.10)):
        return 'filesystem_free_reserve'
    return None


def rate_exceeded(size, previous_size, interval, elapsed, rate):
    # Permit one bounded cache flush, not a fresh cache allowance every second.
    return (size > rate * elapsed + CACHE_BYTES + METADATA_RESERVE or
            size - previous_size > rate * interval + CACHE_BYTES + METADATA_RESERVE)


def start_ticks(pid):
    """Linux process birth identity; Popen ownership+session check still applies."""
    if not Path('/proc').is_dir():
        return None  # Non-Linux unit-test/development host.
    stat = Path('/proc') / str(pid) / 'stat'
    text = stat.read_text()
    return text[text.rfind(')') + 2:].split()[19]


class OwnedProcess:
    """Only this invocation's Popen child and its new process group may be signalled."""
    def __init__(self, process):
        self.process = process
        self.pid = process.pid
        try:
            self.birth = start_ticks(self.pid)
        except FileNotFoundError:
            if process.poll() is None:
                raise
            self.birth = None

    def signal(self, sig):
        if self.process.poll() is not None:
            return False
        try:
            if self.process.pid != self.pid or os.getpgid(self.pid) != self.pid:
                raise RuntimeError('Recorder process-group ownership mismatch')
            if start_ticks(self.pid) != self.birth:
                raise RuntimeError('Recorder process birth identity changed')
            os.killpg(self.pid, sig)
        except (ProcessLookupError, FileNotFoundError):
            if self.process.poll() is None:
                raise
            return False
        return True

    def stop(self):
        escalated = []
        for sig, timeout in ((signal.SIGINT, INT_TIMEOUT), (signal.SIGTERM, TERM_TIMEOUT)):
            if not self.signal(sig):
                return self.process.returncode, escalated
            escalated.append(signal.Signals(sig).name)
            try:
                return self.process.wait(timeout=timeout), escalated
            except subprocess.TimeoutExpired:
                pass
        # Preserve failure logs; never signal a process discovered by a name/PID file.
        if self.signal(signal.SIGKILL):
            escalated.append('SIGKILL')
        return self.process.wait(timeout=2), escalated


def make_plan(args, env):
    validate_environment(args.domain, env)
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 60:
        raise ValueError('Recording duration must be >0 and <=60 seconds')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', args.run_id):
        raise ValueError('Invalid run ID')
    root = Path(args.bag_root).absolute()
    if root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError('Dedicated existing bag root must not contain symlink components')
    output = root / args.run_id
    if output.exists() or output.is_symlink():
        raise ValueError('Output run must be a new directory')
    topics = validate_topics(args.topic or [*STEREO_TOPICS, STATIC_TOPIC])
    rate = args.max_write_mibps * MIB
    reserve = reserve_bytes(rate)
    if reserve >= RUN_CAP:
        raise ValueError('Maximum write rate leaves no space in the 2 GiB run cap')
    reason = quota_reason(0, tree_bytes(root), shutil.disk_usage(root), reserve)
    if reason:
        raise ValueError('Preflight storage gate: ' + reason)
    command = ['ros2', 'bag', 'record', '--storage', 'sqlite3',
               '--output', str(output / 'bag'), '--max-cache-size', str(CACHE_BYTES),
               '--max-bag-size', str(512 * MIB),
               '--qos-profile-overrides-path', str(output / 'qos.yaml'), *topics]
    return {'root': str(root), 'output': str(output), 'topics': topics,
            'command': command, 'domain': args.domain, 'seconds': args.seconds,
            'run_cap_bytes': RUN_CAP, 'archive_cap_bytes': ARCHIVE_CAP,
            'per_file_split_bytes': 512 * MIB, 'max_write_bytes_per_second': rate,
            'stop_reserve_bytes': reserve, 'poll_seconds': POLL_SECONDS,
            'scope': 'Input recording only; no live camera or motion validation implied'}


def record(args, env):
    plan = make_plan(args, env)
    if args.plan:
        print(json.dumps(plan, indent=2))
        return 0
    if not args.camera_window_confirmed:
        raise ValueError('Confirm the coordinated experimental camera window before recording')
    root = Path(plan['root'])
    # A stable dedicated root is mandatory for the cumulative 8 GiB budget.
    lock_path = root / '.record.lock'
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = make_plan(args, env)  # Recheck after acquiring the shared archive lock.
        output = Path(plan['output'])
        output.mkdir(mode=0o700, exist_ok=False)
        (output / 'qos.yaml').write_text(
            STATIC_TOPIC + ':\n  history: keep_last\n  depth: 100\n'
            '  reliability: reliable\n  durability: transient_local\n')
        plan['started_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (output / 'recording_plan.json').write_text(json.dumps(plan, indent=2) + '\n')
        child_env = dict(env)
        child_env.update(ROS_LOG_DIR=str(output / 'ros_logs'), ROS_HOME=str(output / 'ros_home'))
        owned = None
        started = time.monotonic()
        reason = 'NOT_STARTED'
        failure = None
        signals = []
        def interrupt_on_term(signum, frame):
            raise KeyboardInterrupt
        previous_term = signal.signal(signal.SIGTERM, interrupt_on_term)
        with (output / 'recorder.log').open('w') as log:
            try:
                proc = subprocess.Popen(plan['command'], env=child_env, stdout=log,
                                        stderr=subprocess.STDOUT, start_new_session=True)
                owned = OwnedProcess(proc)
                previous_size, previous_time = 0, time.monotonic()
                while proc.poll() is None:
                    now = time.monotonic()
                    size = tree_bytes(output)
                    elapsed = now - previous_time
                    if elapsed > 0 and rate_exceeded(size, previous_size, elapsed,
                                                     now - started, plan['max_write_bytes_per_second']):
                        reason = 'write_rate_bound_exceeded'
                        break
                    previous_size, previous_time = size, now
                    reason = quota_reason(size, tree_bytes(root), shutil.disk_usage(root), plan['stop_reserve_bytes'])
                    if reason:
                        break
                    if now - started >= args.seconds:
                        reason = 'duration_limit'
                        break
                    time.sleep(min(POLL_SECONDS, args.seconds - (now - started)))
                else:
                    reason = 'recorder_exited'
            except KeyboardInterrupt:
                reason = 'operator_interrupt'
            except Exception as exc:
                reason = 'recording_error'
                failure = repr(exc)
            finally:
                # A second external termination cannot interrupt owned cleanup.
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                old_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
                try:
                    if owned is not None:
                        returncode, signals = owned.stop()
                    else:
                        returncode = None
                finally:
                    signal.signal(signal.SIGTERM, previous_term)
                    signal.signal(signal.SIGINT, old_int)
        final_run, final_archive = tree_bytes(output), tree_bytes(root)
        disk = shutil.disk_usage(root)
        breached = final_run > RUN_CAP or final_archive > ARCHIVE_CAP or disk.free < max(10 * GIB, math.ceil(disk.total * .10))
        ok = (failure is None and not breached and returncode == 0 and
              reason != 'write_rate_bound_exceeded' and 'SIGTERM' not in signals and
              (output / 'bag' / 'metadata.yaml').is_file())
        result = {'status': 'RECORDING_SAVED' if ok else 'RECORDING_FAILED',
                  'stop_reason': reason, 'error': failure, 'returncode': returncode,
                  'signals_to_owned_group': signals, 'duration_seconds': time.monotonic() - started,
                  'final_run_bytes': final_run, 'final_archive_bytes': final_archive,
                  'final_free_bytes': disk.free, 'cap_or_free_space_breached': breached,
                  'pid': owned.pid if owned else None, 'process_start_ticks': owned.birth if owned else None}
        (output / 'recording_result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bag-root', required=True, help='Same dedicated existing archive root for ALL live recordings')
    p.add_argument('--run-id', required=True)
    p.add_argument('--domain', required=True, type=int)
    p.add_argument('--seconds', type=float, default=60)
    p.add_argument('--max-write-mibps', type=float, default=64,
                   help='Conservative upper write-rate bound including bag/log overhead (default:64)')
    p.add_argument('--topic', action='append', help='Allowlisted input only; defaults to stereo+CameraInfo+static TF')
    p.add_argument('--camera-window-confirmed', action='store_true')
    p.add_argument('--plan', '--dry-run', dest='plan', action='store_true')
    args = p.parse_args()
    try:
        return record(args, os.environ)
    except (ValueError, OSError, RuntimeError) as exc:
        p.error(str(exc))


if __name__ == '__main__':
    raise SystemExit(main())
