import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from robot_dashboard.resource_monitor import ResourceMonitor, delta, utilization


class Clock:
    value = 0.0

    def __call__(self):
        return self.value


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


class ResourceMonitorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.clock = Clock()
        self.monitor = ResourceMonitor(root=self.root, clock=self.clock, wall_clock=lambda: 1000 + self.clock.value)

    def test_missing_resources_are_null_and_json_is_finite(self):
        value = self.monitor.snapshot()
        for group in ['cpu', 'gpu', 'memory']:
            self.assertIsNone(value[group]['percent'])
        self.assertIsNone(value['network']['rx_bytes_s'])
        self.assertIsNone(value['power']['watts'])
        self.assertEqual(value['thermal'], [])
        self.assertFalse(value['sensors']['topics_available'])
        json.dumps(value, allow_nan=False)

    def test_cpu_uses_two_samples_ignores_guest_and_reports_single_core_pressure(self):
        write(self.root, 'proc/stat', 'cpu 100 0 0 100 0 0 0 0 90 0\ncpu0 50 0 0 50 0 0 0 0\ncpu1 50 0 0 50 0 0 0 0\n')
        first = self.monitor.snapshot()
        self.assertIsNone(first['cpu']['percent'])
        write(self.root, 'proc/stat', 'cpu 200 0 0 200 0 0 0 0 200 0\ncpu0 150 0 0 50 0 0 0 0\ncpu1 50 0 0 150 0 0 0 0\n')
        self.clock.value = 1
        second = self.monitor.snapshot()
        self.assertEqual(second['cpu']['percent'], 50)
        self.assertEqual(second['cpu']['max_core_percent'], 100)
        self.assertEqual(second['sample_interval_s'], 1)
        write(self.root, 'sys/devices/system/cpu/cpu0/online', '0')
        self.clock.value = 2
        self.assertIsNone(self.monitor.snapshot()['cpu']['cores'][0]['percent'])

    def test_tabs_share_one_delta_window_and_reset_counters_remain_null(self):
        first = self.monitor.snapshot()
        self.clock.value = .5
        self.assertIs(first, self.monitor.snapshot())
        self.clock.value = 1
        self.assertEqual(self.monitor.snapshot()['seq'], 2)
        self.assertIsNone(utilization((200, 100), (100, 50)))
        self.assertIsNone(delta(100, 10, 1))
        self.assertIsNone(delta(100, 110, None))

    def test_memory_available_gpu_power_temperature_and_oom(self):
        write(self.root, 'proc/meminfo', 'MemTotal: 1000 kB\nMemAvailable: 400 kB\nSwapTotal: 100 kB\nSwapFree: 90 kB\n')
        write(self.root, 'sys/class/devfreq/17000000.gpu/device/load', '521')
        write(self.root, 'sys/class/devfreq/17000000.gpu/cur_freq', '612000000')
        write(self.root, 'sys/class/thermal/thermal_zone0/type', 'cpu-thermal')
        write(self.root, 'sys/class/thermal/thermal_zone0/temp', '75000')
        write(self.root, 'sys/class/thermal/thermal_zone0/trip_point_0_type', 'passive')
        write(self.root, 'sys/class/thermal/thermal_zone0/trip_point_0_temp', '85000')
        write(self.root, 'sys/class/hwmon/hwmon1/name', 'ina3221')
        write(self.root, 'sys/class/hwmon/hwmon1/in1_label', 'VDD_IN')
        write(self.root, 'sys/class/hwmon/hwmon1/in1_input', '5000')
        write(self.root, 'sys/class/hwmon/hwmon1/curr1_input', '2000')
        write(self.root, 'proc/vmstat', 'oom_kill 2\n')
        value = self.monitor.snapshot()
        self.assertEqual(value['memory']['percent'], 60)
        self.assertEqual(value['memory']['swap_used_bytes'], 10240)
        self.assertEqual(value['gpu']['percent'], 52.1)
        self.assertEqual(value['gpu']['frequency_mhz'], 612)
        self.assertEqual(value['power']['watts'], 10)
        self.assertEqual(value['thermal'][0]['trips'], [{'type': 'passive', 'celsius': 85}])
        self.assertIsNone(value['oom_kill_delta'])
        write(self.root, 'proc/vmstat', 'oom_kill 3\n')
        self.clock.value = 1
        self.assertEqual(self.monitor.snapshot()['oom_kill_delta'], 1)

    def test_physical_network_totals_do_not_double_count_virtual_traffic(self):
        for name, physical in [('eth0', True), ('wlan0', True), ('veth0', False)]:
            if physical:
                (self.root / f'sys/class/net/{name}/device').mkdir(parents=True)
            write(self.root, f'sys/class/net/{name}/operstate', 'up')
            write(self.root, f'sys/class/net/{name}/speed', '100' if name == 'eth0' else '-1')
            for counter in ['rx_bytes', 'tx_bytes', 'rx_dropped', 'tx_dropped', 'rx_errors', 'tx_errors']:
                write(self.root, f'sys/class/net/{name}/statistics/{counter}', '0')
        self.assertIsNone(self.monitor.snapshot()['network']['rx_bytes_s'])
        for name in ['eth0', 'wlan0', 'veth0']:
            write(self.root, f'sys/class/net/{name}/statistics/rx_bytes', '1250000')
        self.clock.value = 1
        value = self.monitor.snapshot()['network']
        self.assertEqual(value['rx_bytes_s'], 2500000)
        eth = next(row for row in value['interfaces'] if row['name'] == 'eth0')
        wifi = next(row for row in value['interfaces'] if row['name'] == 'wlan0')
        self.assertEqual(eth['link_percent'], 10)
        self.assertIsNone(wifi['link_percent'])
        write(self.root, 'sys/class/net/eth0/statistics/rx_bytes', '0')
        self.clock.value = 2
        self.assertIsNone(self.monitor.snapshot()['network']['rx_bytes_s'])

    def test_process_cpu_identity_prevents_pid_reuse_spikes(self):
        def process(ticks, start=100):
            fields = ['S'] + ['0'] * 21
            fields[11], fields[19], fields[21] = str(ticks), str(start), '4'
            write(self.root, 'proc/123/stat', '123 (lio (worker)) ' + ' '.join(fields))
        process(100)
        self.assertIsNone(self.monitor.snapshot()['processes']['items'][0]['cpu_percent'])
        self.clock.value = 1
        process(100 + self.monitor._tick_hz * 2)
        value = self.monitor.snapshot()['processes']['items'][0]
        self.assertEqual(value['cpu_percent'], 200)
        self.assertEqual(value['name'], 'lio (worker)')
        self.clock.value = 2
        process(1000, 200)
        self.assertIsNone(self.monitor.snapshot()['processes']['items'][0]['cpu_percent'])

    def test_sensor_catalog_reads_only_status_and_failures_are_independent(self):
        class Agent:
            def cameras_snapshot(self):
                return {'sources': [{'id': 'go2_front', 'state': 'ok', 'live': True, 'fps': 15, 'width': 1280, 'height': 720, 'age_s': .1}]}

            def topics_snapshot(self):
                raise RuntimeError('private diagnostic must not escape')
        value = self.monitor.snapshot(Agent())['sensors']
        self.assertEqual(value['cameras'][0]['receive_fps'], 15)
        self.assertFalse(value['topics_available'])
        self.assertTrue(value['cameras_available'])
        self.assertNotIn('private diagnostic', json.dumps(value))


class ResourceEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_host_monitor_does_not_require_ros_and_uses_runtime_owned_sampler(self):
        from starlette.requests import Request
        from robot_dashboard.application.runtime import ApplicationRuntime
        from robot_dashboard.api.routers.resources import resources
        from robot_dashboard.resource_server import create_app

        app = create_app()
        self.assertIsNone(app.state.runtime.agent)
        self.assertIsNot(app.state.runtime.resources, ApplicationRuntime().resources)
        request = Request({'type': 'http', 'method': 'GET', 'path': '/api/v1/system/resources', 'headers': [], 'app': app})
        with patch('robot_dashboard.api.routers.resources.asyncio.to_thread',
                   new=AsyncMock(side_effect=lambda function, *args: function(*args))) as worker:
            result = await resources(request)
        self.assertEqual(result['schema'], 'robot-scope.resources.v1')
        self.assertFalse(result['sensors']['topics_available'])
        worker.assert_awaited_once_with(app.state.runtime.resources.snapshot, None)


if __name__ == '__main__':
    unittest.main()
