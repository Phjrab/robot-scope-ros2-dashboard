import asyncio
from collections import namedtuple
import json
from pathlib import Path
import tempfile
import unittest

from robot_dashboard.host_resources import HostResourceMonitor, cpu_times, cpu_percent, memory_values


class HostResourceTests(unittest.TestCase):
    def test_guest_time_not_double_counted_and_counter_reset_unavailable(self):
        times = cpu_times('cpu 50 0 20 100 10 0 0 0 25 0')['cpu']
        self.assertEqual(times, (180, 110))
        self.assertEqual(cpu_percent((100, 80), times), 62.5)
        self.assertIsNone(cpu_percent(times, (100, 80)))
        self.assertIsNone(cpu_percent(None, times))

    def test_memory_uses_available_and_no_swap_is_zero(self):
        values = memory_values('MemTotal: 1000 kB\nMemAvailable: 600 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB')
        self.assertEqual(values['ram']['percent'], 40)
        self.assertEqual(values['swap']['used_bytes'], 0)
        self.assertIsNone(memory_values('')['ram']['percent'])

    def test_cached_single_sampler_missing_gpu_and_bounded_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'proc').mkdir()
            stat = root / 'proc/stat'
            stat.write_text('cpu 0 0 0 100 0 0 0 0\ncpu0 0 0 0 100 0 0 0 0')
            (root / 'proc/meminfo').write_text('MemTotal: 1000 kB\nMemAvailable: 600 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB')
            instant = [0]
            disk = namedtuple('Disk', 'total used free')(1000, 400, 600)
            monitor = HostResourceMonitor(root, lambda: instant[0], lambda _: disk)
            first = monitor.snapshot()
            self.assertIsNone(first['cpu']['percent'])
            self.assertIsNone(first['gpu']['percent'])
            self.assertEqual(first['throttling']['state'], 'NOT_OBSERVED')
            first['history'].clear()  # caller cannot mutate the sampler cache
            instant[0] = 1
            self.assertEqual(len(monitor.snapshot()['history']), 1)
            for i in range(1, 70):
                instant[0] = i * 2
                stat.write_text(f'cpu {i * 10} 0 0 {100 + i * 10} 0 0 0 0')
                result = monitor.snapshot()
            self.assertEqual(result['cpu']['percent'], 50)
            self.assertEqual(len(result['history']), 60)
            json.dumps(result, allow_nan=False)

    def test_jetson_gpu_scale_and_thermal_sensor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpu = root / 'sys/devices/platform/bus@0/17000000.gpu'
            gpu.mkdir(parents=True)
            (gpu / 'load').write_text('173')
            zone = root / 'sys/class/thermal/thermal_zone0'
            zone.mkdir(parents=True)
            (zone / 'temp').write_text('62000')
            (zone / 'type').write_text('cpu-thermal')
            snapshot = HostResourceMonitor(root).snapshot()
            self.assertEqual(snapshot['gpu']['percent'], 17.3)
            self.assertEqual(snapshot['temperature']['max_celsius'], 62)

    def test_http_endpoint_needs_no_ros_agent_or_mutation(self):
        try:
            from fastapi import FastAPI
            from robot_dashboard.api.routers.system import router
            from robot_dashboard.application.runtime import ApplicationRuntime
        except ImportError:
            self.skipTest('FastAPI test dependencies unavailable')
        app = FastAPI()
        app.state.runtime = ApplicationRuntime()
        app.include_router(router)
        async def request(method):
            messages = []
            async def receive():
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            async def send(message):
                messages.append(message)
            await app({'type': 'http', 'http_version': '1.1', 'method': method,
                       'scheme': 'http', 'path': '/api/v1/system/resources', 'raw_path': b'/api/v1/system/resources',
                       'query_string': b'', 'root_path': '', 'headers': [],
                       'server': ('localhost', 80), 'client': ('localhost', 1)}, receive, send)
            status = next(m['status'] for m in messages if m['type'] == 'http.response.start')
            body = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
            return status, body
        status, body = asyncio.run(request('GET'))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['scope'], 'dashboard_host')
        self.assertEqual(asyncio.run(request('POST'))[0], 405)


if __name__ == '__main__':
    unittest.main()
