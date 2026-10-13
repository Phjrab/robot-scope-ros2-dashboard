#!/usr/bin/env python3
"""Bounded host tegrastats capture and optional stop of one owned lab container.

No power/clock/fan settings, daemon actions or global tegrastats --stop calls.
CPU is the arithmetic average of online core utilization percentages. GR3D is
utilization, not CUDA compute time. Missing fields remain absent, not zero.
"""
import argparse
import datetime
import json
import math
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time

try:
    from . import labctl
    from .metrics.analyze import distribution
except ImportError:
    import labctl
    from metrics.analyze import distribution


def parse_line(line):
    values = {}
    for name in ('RAM', 'SWAP'):
        match = re.search(r'\b' + name + r'\s+(\d+)/(\d+)MB\b', line)
        if match:
            values[name.lower() + '_used_mb'] = int(match[1])
            values[name.lower() + '_total_mb'] = int(match[2])
    match = re.search(r'\bCPU\s+\[([^]]+)\]', line)
    if match:
        cores = [float(v) for v in re.findall(r'(\d+(?:\.\d+)?)%', match[1])]
        if cores:
            values['cpu_avg_online_percent'] = sum(cores) / len(cores)
            values['cpu_online_cores'] = len(cores)
        values['cpu_offline_cores'] = sum(v.strip() == 'off' for v in match[1].split(','))
    match = re.search(r'\bGR3D(?:_FREQ)?\s+(\d+(?:\.\d+)?)%', line)
    if match:
        values['gr3d_percent'] = float(match[1])
    for name, temperature in re.findall(r'\b([A-Za-z][A-Za-z0-9_]*)@(-?\d+(?:\.\d+)?)C\b', line):
        values['temperature_c/' + name] = float(temperature)
    for name, current, average in re.findall(r'\b(VDD_[A-Za-z0-9_]+|VIN_[A-Za-z0-9_]+|POM_[A-Za-z0-9_]+)\s+(\d+)(?:mW)?/(\d+)(?:mW)?(?=\s|$)', line):
        values['power_mw/' + name] = int(current)
        values['power_reported_average_mw/' + name] = int(average)
    return values


def mem_available_bytes():
    try:
        match = re.search(r'^MemAvailable:\s+(\d+)\s+kB$', Path('/proc/meminfo').read_text(), re.M)
        return int(match[1]) * 1024 if match else None
    except OSError:
        return None


def start_ticks(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def stop_child(child, expected_start):
    """Only the unreaped Popen child in its own new session and matching start time."""
    if child.poll() is not None:
        return
    for sig, grace in ((signal.SIGINT, 3), (signal.SIGTERM, 2), (signal.SIGKILL, 2)):
        if child.poll() is not None:
            return
        try:
            if os.getpgid(child.pid) != child.pid or (expected_start is not None and start_ticks(child.pid) != expected_start):
                raise RuntimeError('tegrastats process ownership changed; refusing signal')
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            return
        try:
            child.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            pass


class SafetyWindow:
    def __init__(self):
        self.counts = {'temperature': 0, 'available_ram': 0, 'cpu': 0}

    def observe(self, values):
        temperatures = [v for k, v in values.items() if k.startswith('temperature_c/')]
        flags = {'temperature': bool(temperatures) and max(temperatures) >= 85,
                 'available_ram': values.get('mem_available_bytes', math.inf) < 2 * 1024 ** 3,
                 'cpu': values.get('cpu_avg_online_percent', 0) > 90}
        for key, active in flags.items():
            self.counts[key] = self.counts[key] + 1 if active else 0
        return [key for key, count in self.counts.items() if count >= 5]


def stop_container(state):
    obj = labctl.owned(state)  # Exact ID + label + Created checked immediately before stop.
    if obj['State']['Running']:
        subprocess.run(['docker', 'stop', '--time', '20', state['container_id']], check=True, timeout=30,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return 'OWNED_CONTAINER_STOPPED'
    return 'OWNED_CONTAINER_ALREADY_STOPPED'


def summarize(samples, start_ns, end_ns, reason, actions):
    fields = {}
    for sample in samples:
        for name, value in sample['values'].items():
            fields.setdefault(name, []).append(value)
    return {'schema_version': 1, 'samples': len(samples), 'start_monotonic_ns': start_ns,
            'end_monotonic_ns': end_ns, 'elapsed_seconds': (end_ns - start_ns) / 1e9,
            'end_reason': reason, 'safety_actions': actions,
            'metrics': {k: distribution(v) for k, v in sorted(fields.items())},
            'scope': 'Host-wide load including other workloads; no attribution to VSLAM alone.',
            'units': {'ram_swap': 'MB as printed by tegrastats', 'temperature': 'C', 'power': 'mW (instantaneous and vendor average separate)'},
            'missing_metrics': 'Absent fields were not observed; they are not zero.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--summary', type=Path, required=True)
    parser.add_argument('--state', type=Path, help='Optional labctl ownership.json; enables automatic stop of only this container')
    parser.add_argument('--interval-ms', type=int, default=1000)
    parser.add_argument('--from-stdin', action='store_true', help='Offline fixture mode; incompatible with --state')
    args = parser.parse_args()
    if not math.isfinite(args.duration) or not 1 <= args.duration <= 3600:
        parser.error('Finite duration 1..3600 seconds required')
    if not 200 <= args.interval_ms <= 5000:
        parser.error('Sampling interval must be 200..5000 ms')
    if args.from_stdin and args.state:
        parser.error('Fixture mode cannot stop a container')
    if args.output.exists() or args.summary.exists() or args.output.resolve() == args.summary.resolve():
        parser.error('New, distinct output and summary files required')
    state = json.loads(args.state.read_text()) if args.state else None
    if state:
        labctl.owned(state)
    stop = [None]
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda signum, frame: stop.__setitem__(0, signal.Signals(signum).name))
    samples, actions = [], []
    child = None
    child_start = None
    start_ns = time.monotonic_ns()
    safety = SafetyWindow()
    with args.output.open('x', encoding='utf-8', buffering=1) as output:
        def write(value):
            output.write(json.dumps(value, allow_nan=False) + '\n')
        write({'event': 'run_start', 'receipt_monotonic_ns': start_ns,
               'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'duration_seconds': args.duration,
               'source': 'stdin_fixture' if args.from_stdin else 'host_tegrastats', 'interval_ms': args.interval_ms,
               'safety_enabled': state is not None, 'owner_container_id': state['container_id'] if state else None,
               'thresholds': {'temperature_c_gte': 85, 'available_ram_bytes_lt': 2 * 1024 ** 3,
                              'cpu_avg_online_percent_gt': 90, 'consecutive_samples': 5}})
        try:
            if args.from_stdin:
                source = sys.stdin
            else:
                child = subprocess.Popen(['tegrastats', '--interval', str(args.interval_ms)], stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
                child_start = start_ticks(child.pid)
                source = child.stdout
            inbox = queue.Queue()
            def reader():
                try:
                    for line in source:
                        inbox.put(line)
                finally:
                    inbox.put(None)
            thread = threading.Thread(target=reader, daemon=True)
            thread.start()
            deadline = time.monotonic() + args.duration
            while not stop[0] and time.monotonic() < deadline:
                try:
                    line = inbox.get(timeout=.2)
                except queue.Empty:
                    continue
                if line is None:
                    stop[0] = 'source_ended'
                    break
                values = parse_line(line)
                available = mem_available_bytes() if not args.from_stdin else None
                if available is not None:
                    values['mem_available_bytes'] = available
                sample = {'event': 'sample', 'receipt_monotonic_ns': time.monotonic_ns(), 'raw': line.rstrip(), 'values': values}
                write(sample)
                samples.append(sample)
                triggered = safety.observe(values)
                if triggered:
                    action = {'event': 'safety_trigger', 'conditions': triggered, 'counts': dict(safety.counts),
                              'receipt_monotonic_ns': time.monotonic_ns()}
                    try:
                        action['result'] = stop_container(state) if state else 'NO_CONTAINER_STATE_NO_ACTION'
                    except Exception as exc:
                        action['result'] = 'STOP_FAILED'
                        action['error'] = str(exc)
                    actions.append(action)
                    write(action)
                    stop[0] = 'safety_threshold'
            stop[0] = stop[0] or 'duration_complete'
        except BaseException as exc:
            stop[0] = 'capture_error'
            write({'event': 'capture_error', 'error_type': type(exc).__name__, 'error': str(exc)})
            raise
        finally:
            if child is not None:
                try:
                    stop_child(child, child_start)
                except Exception as exc:
                    write({'event': 'cleanup_error', 'error': str(exc)})
                    stop[0] = 'cleanup_error'
            end_ns = time.monotonic_ns()
            write({'event': 'run_end', 'receipt_monotonic_ns': end_ns, 'reason': stop[0]})
            summary = summarize(samples, start_ns, end_ns, stop[0], actions)
            summary['source'] = 'stdin_fixture' if args.from_stdin else 'host_tegrastats'
            summary['evidence_type'] = 'synthetic_fixture' if args.from_stdin else 'host_resource_observation'
            with args.summary.open('x', encoding='utf-8') as handle:
                json.dump(summary, handle, indent=2, allow_nan=False)
                handle.write('\n')
    print(args.summary)


if __name__ == '__main__':
    main()
