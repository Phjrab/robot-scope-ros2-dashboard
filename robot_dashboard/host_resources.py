"""Cached, read-only resources of the dashboard host. No commands or devices opened."""
from __future__ import annotations

import copy
import datetime as dt
import platform
from pathlib import Path
import shutil
import threading
import time


def cpu_times(text: str) -> dict[str, tuple[int, int]]:
    rows = {}
    for line in text.splitlines():
        fields = line.split()
        if fields and (fields[0] == 'cpu' or fields[0][3:].isdigit() and fields[0].startswith('cpu')):
            values = [int(value) for value in fields[1:9]]  # guest is already counted in user/nice
            if len(values) >= 4 and all(value >= 0 for value in values):
                rows[fields[0]] = (sum(values), values[3] + (values[4] if len(values) > 4 else 0))
    return rows


def cpu_percent(previous, current):
    if previous is None:
        return None
    total, idle = current[0] - previous[0], current[1] - previous[1]
    if total <= 0 or not 0 <= idle <= total:
        return None
    return round(100 * (total - idle) / total, 2)


def memory_values(text: str) -> dict:
    values = {}
    for line in text.splitlines():
        key, _, raw = line.partition(':')
        if key in {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}:
            fields = raw.split()
            if len(fields) == 2 and fields[1] == 'kB':
                values[key] = int(fields[0]) * 1024
    def usage(total_key, available_key):
        total, available = values.get(total_key), values.get(available_key)
        if total is None or available is None or not 0 <= available <= total:
            return {'used_bytes': None, 'total_bytes': None, 'percent': None}
        return {'used_bytes': total - available, 'total_bytes': total,
                'percent': round(100 * (total - available) / total, 2) if total else 0.0}
    return {'ram': usage('MemTotal', 'MemAvailable'), 'swap': usage('SwapTotal', 'SwapFree')}


class HostResourceMonitor:
    """Sample at most once per two seconds across all clients; bounded history."""
    def __init__(self, root: Path = Path('/'), monotonic=time.monotonic, disk_usage=shutil.disk_usage):
        self.root, self.clock, self.disk_usage = root, monotonic, disk_usage
        self.lock = threading.Lock()
        self.previous_cpu = {}
        self.cached = None
        self.sampled_at = None
        self.history = []

    def read(self, relative):
        try:
            return (self.root / relative).read_text().strip().strip('\0')
        except (OSError, UnicodeError):
            return None

    def number(self, relative, divisor=1):
        raw = self.read(relative)
        try:
            return float(raw) / divisor if raw is not None else None
        except ValueError:
            return None

    def snapshot(self):
        with self.lock:
            now = self.clock()
            if self.cached is not None and now - self.sampled_at < 2:
                result = copy.deepcopy(self.cached)
                result['sample_age_seconds'] = round(max(0, now - self.sampled_at), 3)
                return result
            errors = []
            try:
                times = cpu_times(self.read('proc/stat') or '')
            except ValueError:
                times = {}
            cpu = cpu_percent(self.previous_cpu.get('cpu'), times['cpu']) if 'cpu' in times else None
            cores = [{'id': name, 'percent': cpu_percent(self.previous_cpu.get(name), values),
                      'frequency_mhz': self.number(f'sys/devices/system/cpu/{name}/cpufreq/scaling_cur_freq', 1000)}
                     for name, values in times.items() if name != 'cpu']
            self.previous_cpu = times
            if cpu is None:
                errors.append('CPU: 두 표본이 필요하거나 /proc/stat을 읽을 수 없음')
            try:
                memory = memory_values(self.read('proc/meminfo') or '')
            except ValueError:
                memory = memory_values('')
            gpu = None
            gpu_source = None
            # NVIDIA Jetson load reports tenths of a percent; absent is N/A.
            candidates = ['sys/devices/platform/bus@0/17000000.gpu/load',
                          'sys/devices/platform/17000000.gpu/load']
            candidates += [str(path.relative_to(self.root)) for path in
                           (self.root / 'sys/class/devfreq').glob('*gpu*/device/load')]
            for candidate in candidates:
                value = self.number(candidate, 10)
                if value is not None and 0 <= value <= 100:
                    gpu, gpu_source = value, 'Jetson GPU sysfs load (0..1000)'
                    break
            if gpu is None:
                errors.append('GPU: 지원되는 Jetson sysfs 지표를 읽을 수 없음')
            temperatures = []
            for zone in (self.root / 'sys/class/thermal').glob('thermal_zone*'):
                relative = str(zone.relative_to(self.root))
                value = self.number(relative + '/temp', 1000)
                name = self.read(relative + '/type') or zone.name
                if value is not None and -40 <= value <= 150:
                    temperatures.append({'name': name, 'celsius': value})
            maximum = max((x['celsius'] for x in temperatures), default=None)
            try:
                disk = self.disk_usage(self.root)
                storage = {'total_bytes': disk.total, 'used_bytes': disk.used, 'free_bytes': disk.free,
                           'percent': round(100 * disk.used / disk.total, 2) if disk.total else None}
            except OSError:
                storage = {'total_bytes': None, 'used_bytes': None, 'free_bytes': None, 'percent': None}
                errors.append('디스크: 파일시스템 사용량을 읽을 수 없음')
            board = self.read('sys/firmware/devicetree/base/model')
            point = {'cpu_percent': cpu, 'gpu_percent': gpu, 'ram_percent': memory['ram']['percent'],
                     'temperature_c': maximum, 'timestamp': dt.datetime.now(dt.timezone.utc).isoformat()}
            self.history.append(point)
            self.history = self.history[-60:]
            self.cached = {'schema_version': 1, 'sampled_at': point['timestamp'], 'sample_age_seconds': 0,
                           'sample_interval_seconds': 2, 'scope': 'dashboard_host',
                           'host': {'model': board or platform.system(), 'is_jetson': bool(board and 'jetson' in board.lower())},
                           'cpu': {'percent': cpu, 'cores': cores, 'source': '/proc/stat deltas'},
                           'gpu': {'percent': gpu, 'source': gpu_source}, **memory, 'disk': storage,
                           'temperature': {'max_celsius': maximum, 'sensors': temperatures},
                           'history': copy.deepcopy(self.history), 'unavailable': errors,
                           'throttling': {'state': 'NOT_OBSERVED', 'reason': '온도만으로 throttling을 판정하지 않음'}}
            self.sampled_at = now
            return copy.deepcopy(self.cached)
