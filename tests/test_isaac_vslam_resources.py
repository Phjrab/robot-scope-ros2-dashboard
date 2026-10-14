"""Host resource parser/ownership tests: no real tegrastats or Docker calls."""
import signal
import subprocess
import unittest
from unittest.mock import Mock, patch

from experiments.isaac_vslam import resource_watch as watch


class TegrastatsParsingTests(unittest.TestCase):
    def test_orin_sample_with_offline_cores_and_power(self):
        line = ('RAM 4530/15379MB (lfb 1452x4MB) SWAP 5/7689MB (cached 0MB) '
                'CPU [10%@729,20%@729,off,off,30%@729,40%@729] EMC_FREQ 3%@2133 '
                'GR3D_FREQ 29%@[306,306] CPU@52.125C GPU@50.687C tj@52.125C '
                'VDD_IN 6990mW/7030mW VDD_CPU_GPU_CV 1166mW/1209mW')
        values = watch.parse_line(line)
        self.assertEqual(values['ram_used_mb'], 4530)
        self.assertEqual(values['swap_used_mb'], 5)
        self.assertEqual(values['cpu_avg_online_percent'], 25)
        self.assertEqual(values['cpu_online_cores'], 4)
        self.assertEqual(values['cpu_offline_cores'], 2)
        self.assertEqual(values['gr3d_percent'], 29)
        self.assertEqual(values['temperature_c/CPU'], 52.125)
        self.assertEqual(values['power_mw/VDD_IN'], 6990)
        self.assertEqual(values['power_reported_average_mw/VDD_IN'], 7030)

    def test_unitless_vendor_power_and_missing_metrics(self):
        values = watch.parse_line('GR3D 0%@306 VDD_IN 4000/4500 CPU@-2C')
        self.assertEqual(values['power_mw/VDD_IN'], 4000)
        self.assertEqual(values['temperature_c/CPU'], -2)
        self.assertNotIn('ram_used_mb', values)
        self.assertNotIn('cpu_avg_online_percent', values)
        self.assertEqual(watch.parse_line('permission denied'), {})

    def test_summary_preserves_samples_duration_and_quantiles(self):
        samples = [{'values': {'gr3d_percent': value}} for value in (0, 10, 20, 30, 40)]
        summary = watch.summarize(samples, 0, 5_000_000_000, 'fixture', [])
        self.assertEqual(summary['samples'], 5)
        self.assertEqual(summary['elapsed_seconds'], 5)
        self.assertEqual(summary['metrics']['gr3d_percent']['p50'], 20)
        self.assertEqual(summary['metrics']['gr3d_percent']['p95'], 38)


class SafetyTests(unittest.TestCase):
    def test_five_consecutive_hot_samples_required(self):
        safety = watch.SafetyWindow()
        for _ in range(4):
            self.assertEqual(safety.observe({'temperature_c/CPU': 85}), [])
        self.assertEqual(safety.observe({'temperature_c/CPU': 85}), ['temperature'])

    def test_safe_or_missing_sample_resets_each_condition(self):
        safety = watch.SafetyWindow()
        for _ in range(4):
            safety.observe({'cpu_avg_online_percent': 91, 'mem_available_bytes': 1})
        self.assertEqual(safety.observe({'cpu_avg_online_percent': 90, 'mem_available_bytes': 2 * 1024 ** 3}), [])
        for _ in range(4):
            self.assertEqual(safety.observe({'cpu_avg_online_percent': 100}), [])
        self.assertEqual(safety.observe({}), [])
        self.assertEqual(safety.counts['cpu'], 0)

    def test_low_available_ram_not_total_minus_used(self):
        safety = watch.SafetyWindow()
        for _ in range(10):
            self.assertEqual(safety.observe({'ram_used_mb': 15000, 'ram_total_mb': 15300}), [])
        for _ in range(4):
            safety.observe({'mem_available_bytes': 2 * 1024 ** 3 - 1})
        self.assertEqual(safety.observe({'mem_available_bytes': 2 * 1024 ** 3 - 1}), ['available_ram'])

    def test_stop_revalidates_owned_container_and_uses_exact_id(self):
        state = {'container_id': 'owned-exact-id'}
        with patch.object(watch.labctl, 'owned', return_value={'State': {'Running': True}}) as owned, \
                patch.object(watch.subprocess, 'run') as run:
            self.assertEqual(watch.stop_container(state), 'OWNED_CONTAINER_STOPPED')
        owned.assert_called_once_with(state)
        self.assertEqual(run.call_args.args[0], ['docker', 'stop', '--time', '20', 'owned-exact-id'])

    def test_bad_ownership_prevents_container_stop(self):
        with patch.object(watch.labctl, 'owned', side_effect=RuntimeError('mismatch')), patch.object(watch.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                watch.stop_container({'container_id': 'not-ours'})
        run.assert_not_called()


class ChildOwnershipTests(unittest.TestCase):
    def test_already_exited_no_signal(self):
        child = Mock(pid=987654)
        child.poll.return_value = 0
        with patch.object(watch.os, 'killpg') as kill:
            watch.stop_child(child, '100')
        kill.assert_not_called()

    def test_changed_start_or_group_no_signal(self):
        for group, token in ((987655, '100'), (987654, '101')):
            child = Mock(pid=987654)
            child.poll.return_value = None
            with self.subTest(group=group, token=token), patch.object(watch.os, 'getpgid', return_value=group), \
                    patch.object(watch, 'start_ticks', return_value=token), patch.object(watch.os, 'killpg') as kill:
                with self.assertRaises(RuntimeError):
                    watch.stop_child(child, '100')
                kill.assert_not_called()

    def test_escalates_only_owned_group(self):
        child = Mock(pid=987654)
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired('owned', 3), 0]
        with patch.object(watch.os, 'getpgid', return_value=987654), patch.object(watch, 'start_ticks', return_value='100'), \
                patch.object(watch.os, 'killpg') as kill:
            watch.stop_child(child, '100')
        self.assertEqual([call.args for call in kill.call_args_list], [(987654, signal.SIGINT), (987654, signal.SIGTERM)])


if __name__ == '__main__':
    unittest.main()
