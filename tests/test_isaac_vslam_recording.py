"""Finite recorder guards; no ROS, camera, network, or robot operations."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / 'experiments/isaac_vslam/bounded_record.py'
SPEC = importlib.util.spec_from_file_location('vslam_bounded_record', SOURCE)
record = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(record)


class RecordingGuards(unittest.TestCase):
    def disk(self, free=80 * record.GIB, total=100 * record.GIB):
        return SimpleNamespace(free=free, total=total)

    def test_poll_and_shutdown_write_reserve_is_included(self):
        rate = 64 * record.MIB
        reserve = record.reserve_bytes(rate)
        self.assertEqual(reserve, 432 * record.MIB)
        self.assertEqual(record.quota_reason(record.RUN_CAP - reserve, 0, self.disk(), reserve),
                         'run_budget_reserve')
        self.assertIsNone(record.quota_reason(record.RUN_CAP - reserve - 1, 0, self.disk(), reserve))

    def test_cumulative_limit_is_not_per_file_split_limit(self):
        reserve = record.reserve_bytes(64 * record.MIB)
        self.assertEqual(record.quota_reason(512 * record.MIB, record.ARCHIVE_CAP - reserve,
                                             self.disk(), reserve), 'archive_budget_reserve')
        self.assertIsNone(record.quota_reason(512 * record.MIB, record.GIB, self.disk(), reserve))

    def test_rate_budget_does_not_allow_repeated_cache_bursts(self):
        rate = 64 * record.MIB
        self.assertFalse(record.rate_exceeded(96 * record.MIB, 0, 1, 1, rate))
        self.assertTrue(record.rate_exceeded(192 * record.MIB, 96 * record.MIB, 1, 2, rate))

    def test_filesystem_threshold_uses_larger_of_10gib_and_ten_percent(self):
        reserve = record.reserve_bytes(64 * record.MIB)
        for total, floor in ((50 * record.GIB, 10 * record.GIB), (500 * record.GIB, 50 * record.GIB)):
            self.assertEqual(record.quota_reason(0, 0, self.disk(floor + reserve, total), reserve),
                             'filesystem_free_reserve')

    def test_reject_operational_outputs_dynamic_tf_wildcard_and_all_flag(self):
        topics = [*record.STEREO_TOPICS, record.STATIC_TOPIC]
        for bad in ('-a', '/tf', '/vslam_lab/tf', '/camera/imu',
                    '/vslam_lab/visual_slam/tracking/odometry', '/vslam_lab/camera/*'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                record.validate_topics(topics + [bad])
        self.assertEqual(record.validate_topics(topics + [record.IMU_TOPIC])[-1], record.IMU_TOPIC)
        with self.assertRaises(ValueError):
            record.validate_topics(topics[:-1])

    def test_environment_rejects_mismatch_and_external_discovery(self):
        env = {'ROS_DOMAIN_ID': '71', 'ROS_LOCALHOST_ONLY': '1',
               'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp'}
        record.validate_environment(71, env)
        for change in ({'ROS_DOMAIN_ID': '0'}, {'ROS_LOCALHOST_ONLY': '0'},
                       {'ROS_DISCOVERY_SERVER': 'remote:11811'},
                       {'FASTDDS_DEFAULT_PROFILES_FILE': '/operational.xml'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                record.validate_environment(71, dict(env, **change))

    def test_archive_counts_wal_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'run').mkdir()
            (root / 'run/db.db3').write_bytes(b'a' * 10)
            (root / 'run/db.db3-wal').write_bytes(b'a' * 7)
            self.assertEqual(record.tree_bytes(root), 17)
            (root / 'escape').symlink_to(root / 'run', target_is_directory=True)
            with self.assertRaises(ValueError):
                record.tree_bytes(root)

    def test_plan_new_output_explicit_inputs_and_no_side_effects(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            args = SimpleNamespace(domain=71, seconds=60, run_id='test', bag_root=str(root),
                                   topic=None, max_write_mibps=64)
            env = {'ROS_DOMAIN_ID': '71', 'ROS_LOCALHOST_ONLY': '1',
                   'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp'}
            with patch.object(record.shutil, 'disk_usage', return_value=self.disk()):
                plan = record.make_plan(args, env)
                self.assertNotIn('-a', plan['command'])
                self.assertEqual(plan['per_file_split_bytes'], 512 * record.MIB)
                self.assertFalse((root / 'test').exists())
                (root / 'test').mkdir()
                with self.assertRaises(ValueError):
                    record.make_plan(args, env)

    def test_invalid_duration_and_rate_fail_closed(self):
        for value in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                record.reserve_bytes(value)


class OwnedCleanup(unittest.TestCase):
    def process(self):
        proc = Mock(pid=456)
        proc.poll.return_value = None
        proc.wait.return_value = 0
        return proc

    def test_normal_interrupt_targets_only_own_new_session(self):
        proc = self.process()
        with patch.object(record, 'start_ticks', return_value='123'), \
                patch.object(record.os, 'getpgid', return_value=456), \
                patch.object(record.os, 'killpg') as kill:
            owned = record.OwnedProcess(proc)
            code, signals = owned.stop()
            self.assertEqual(code, 0)
            self.assertEqual(signals, ['SIGINT'])
            kill.assert_called_once_with(456, signal.SIGINT)

    def test_wrong_process_group_or_reused_pid_never_signalled(self):
        for pgid, ticks in ((999, ['123', '123']), (456, ['123', '456'])):
            with self.subTest(pgid=pgid), \
                    patch.object(record, 'start_ticks', side_effect=ticks), \
                    patch.object(record.os, 'getpgid', return_value=pgid), \
                    patch.object(record.os, 'killpg') as kill:
                owned = record.OwnedProcess(self.process())
                with self.assertRaises(RuntimeError):
                    owned.signal(signal.SIGINT)
                kill.assert_not_called()

    def test_already_exited_child_is_not_signalled(self):
        proc = self.process()
        proc.poll.return_value = 0
        with patch.object(record, 'start_ticks', return_value='123'), \
                patch.object(record.os, 'killpg') as kill:
            self.assertFalse(record.OwnedProcess(proc).signal(signal.SIGINT))
            kill.assert_not_called()

    def test_timeout_escalates_only_same_owned_group(self):
        proc = self.process()
        proc.wait.side_effect = [subprocess.TimeoutExpired('ros2', 3), 0]
        with patch.object(record, 'start_ticks', return_value='123'), \
                patch.object(record.os, 'getpgid', return_value=456), \
                patch.object(record.os, 'killpg') as kill:
            _, signals = record.OwnedProcess(proc).stop()
            self.assertEqual(signals, ['SIGINT', 'SIGTERM'])
            self.assertEqual([c.args for c in kill.call_args_list],
                             [(456, signal.SIGINT), (456, signal.SIGTERM)])


if __name__ == '__main__':
    unittest.main()
