import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from robot_dashboard.goal_evidence_sink import GoalEvidenceSink


class GoalEvidenceSinkTests(unittest.TestCase):
    def test_private_file_survives_without_browser_or_logging_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'private'
            sink = GoalEvidenceSink(root)
            for event in ['dispatch', 'result', 'first_measured_stop']:
                sink.submit(event, {'goal_id': 'new-goal', 'source_stamp_ns': '10000000000'})
            sink.close(2)
            records = [json.loads(line) for line in (root / 'events.jsonl').read_text().splitlines()]
            self.assertEqual([r['event'] for r in records], ['dispatch', 'result', 'first_measured_stop'])
            self.assertEqual(sink.snapshot()['written'], 3)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual((root / 'events.jsonl').stat().st_mode & 0o777, 0o600)

    def test_stalled_disk_does_not_block_submit_and_queue_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            release, entered = threading.Event(), threading.Event()
            def stalled(payload):
                entered.set()
                release.wait(2)
            with patch.object(GoalEvidenceSink, '_write', side_effect=stalled):
                sink = GoalEvidenceSink(Path(tmp))
                sink.submit('result', {})
                self.assertTrue(entered.wait(1))
                start = time.monotonic()
                for _ in range(200):
                    sink.submit('sample', {})
                self.assertLess(time.monotonic() - start, .1)
                self.assertLessEqual(sink.snapshot()['pending'], 64)
                self.assertGreater(sink.snapshot()['dropped'], 0)
                release.set()
                sink.close(2)

    def test_rotation_size_failure_and_symlink_are_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sink = GoalEvidenceSink(root / 'ok')
            sink.MAX_FILE_BYTES = 200
            for _ in range(20):
                sink.submit('sample', {'goal_id': 'g'})
            sink.close(2)
            self.assertLessEqual(len(list((root / 'ok').iterdir())), 4)
            self.assertEqual(sink.snapshot()['written'], 20)
            target = root / 'untouched'
            target.write_text('preserve')
            bad = root / 'bad'
            bad.mkdir()
            (bad / 'events.jsonl').symlink_to(target)
            sink = GoalEvidenceSink(bad)
            sink.submit('dispatch', {'goal_id': 'g'})
            sink.submit('result', {'too_big': 'x' * sink.MAX_RECORD_BYTES})
            sink.close(2)
            self.assertEqual(target.read_text(), 'preserve')
            self.assertEqual(sink.snapshot()['errors'], 1)
            self.assertEqual(sink.snapshot()['dropped'], 1)

    def test_gateway_dispatch_result_and_zero_reach_the_real_sink(self):
        from test_ros_navigation_gateway import gateway
        with tempfile.TemporaryDirectory() as tmp:
            g = gateway()
            g._goal_evidence_sink = GoalEvidenceSink(Path(tmp))
            g._goal_precision_call('start', 'new-goal', {'x': 1., 'y': 0., 'yaw': 0.}, {}, event='dispatch')
            g._goal_precision_call('finish', 'canceled', 10000000000, 10., {}, event='result')
            g._goal_precision_call('issued_zero', 10000000000, 10., event='zero_issued')
            g._goal_evidence_sink.close(2)
            rows = [json.loads(x) for x in (Path(tmp) / 'events.jsonl').read_text().splitlines()]
            self.assertEqual([r['event'] for r in rows], ['dispatch', 'result', 'zero_issued'])
            self.assertEqual(rows[1]['evidence']['result']['state'], 'canceled')
            self.assertIsNone(rows[1]['evidence']['result']['nav2_success_stamp_ns'])
