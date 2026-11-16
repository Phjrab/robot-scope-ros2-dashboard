import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


evidence = load('field_trial_evidence')
probe = load('run_go2_bounded_diagnostic')


def control():
    return {'control': {'estop_latched': True, 'lease': {'active': False},
        'command': {'deadman': False, 'linear_x': 0., 'linear_y': 0., 'angular_z': 0.}}}


def trial():
    plan = {'job_id': 'current-job', 'map_id': 'a'*24, 'map_revision': 'b'*64,
            'start': {'x': 1., 'y': 2., 'yaw': .1}}
    n = {'pipeline': {'state': 'running', 'job_id': 'current-job'},
         'safety': {'can_send_goal': True}, 'goal': {'state': 'idle'},
         'localization_health': {'state': 'READY'}, 'operational_localization': {'ready': True},
         'map': {'id': plan['map_id'], 'revision': plan['map_revision']},
         'localization': {'pose': dict(plan['start'])},
         'parameter_evidence': {'live_ros': {'status': 'current', 'parameters': {
             '/controller_server': {'FollowPath.desired_linear_vel': .2,
                                    'FollowPath.use_collision_detection': True}}}}}
    c = control()
    c['control'].update(estop_latched=False, lease={'active': True, 'input_source': 'navigation'},
                        bridge={'motion_observation': {'quality': 'READY'}})
    return n, c, plan


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def test_reproduces_float32_failure_then_normalizes_ros_arrays(self):
        row = {'position': list(np.array([.1, .2, .3], dtype=np.float32)), 'seq': np.int64(5)}
        with self.assertRaises(TypeError):
            json.dumps(row)
        evidence.write_json(self.path / 'motion.json', row)
        actual = json.loads((self.path / 'motion.json').read_text())
        self.assertAlmostEqual(actual['position'][0], .1, places=6)
        self.assertEqual(actual['seq'], 5)

    def test_invalid_export_does_not_truncate_good_artifact(self):
        path = self.path / 'good.json'
        evidence.write_json(path, {'saved': True})
        before = path.read_bytes()
        for invalid in (np.float32(np.nan), float('inf'), object()):
            with self.subTest(invalid=type(invalid).__name__):
                with self.assertRaises((ValueError, TypeError)):
                    evidence.write_json(path, {'bad': invalid})
                self.assertEqual(path.read_bytes(), before)

    def test_failed_replace_preserves_original_and_removes_temporary(self):
        path = self.path / 'good.json'
        evidence.write_json(path, {'old': True})
        with patch.object(evidence.os, 'replace', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                evidence.write_json(path, {'new': True})
        self.assertEqual(json.loads(path.read_text()), {'old': True})
        self.assertEqual(list(self.path.iterdir()), [path])

    def test_journal_is_readable_before_finalization_and_keeps_good_prefix(self):
        path = self.path / 'motion.jsonl'
        journal = evidence.Journal(path)
        self.addCleanup(journal.close)
        journal.append({'position': [np.float32(.2)]})
        with self.assertRaises(ValueError):
            journal.append({'position': [np.float32(np.nan)]})
        self.assertAlmostEqual(json.loads(path.read_text())['position'][0], .2, places=6)
        with self.assertRaises(FileExistsError):
            evidence.Journal(path)

    def test_tokens_are_not_retained_even_in_nested_readback(self):
        value = json.loads(evidence.encoded({'control': {'lease_id': 'secret-value',
            'nested': [{'Authorization': 'Bearer secret-value'}]}}))
        self.assertNotIn('secret-value', json.dumps(value))

    def test_stop_readback_cleanup_and_each_export_are_independent(self):
        order = []

        def stop():
            order.append('stop')
            raise OSError('network')

        def cleanup():
            order.append('cleanup')
            raise RuntimeError('ROS')

        def save(path, value):
            order.append(path.name)
            evidence.write_json(path, value)

        result = evidence.stop_and_finalize(stop, lambda: control(),
            [('ros', cleanup), ('close', lambda: order.append('close'))],
            [(self.path / 'bad.json', object()), (self.path / 'sent.json', [1])], save=save)
        self.assertEqual(order, ['stop', 'cleanup', 'close', 'bad.json', 'sent.json'])
        self.assertFalse(result['stop_requested'])
        self.assertTrue(result['stop_confirmed'])  # independent returned STOP state
        self.assertEqual(len(result['errors']), 3)
        self.assertEqual(json.loads((self.path / 'sent.json').read_text()), [1])

    def test_unavailable_or_nonzero_readback_never_claims_stop(self):
        for bad in (None, {'control': {}}, control()):
            if bad and bad.get('control', {}).get('command'):
                bad['control']['command']['linear_x'] = .1
            result = evidence.stop_and_finalize(lambda: None, lambda: bad, [], [])
            self.assertFalse(result['stop_confirmed'])

    def test_observer_failure_is_visible_to_command_loop(self):
        journal = evidence.Journal(self.path / 'motion.jsonl')
        self.addCleanup(journal.close)
        samples = probe.Samples(journal)
        message = SimpleNamespace(position=np.zeros(3, dtype=np.float32),
            velocity=np.zeros(3, dtype=np.float32), imu_state=SimpleNamespace(rpy=np.zeros(3, dtype=np.float32)))
        samples.observe(message)
        self.assertEqual(samples.current()['position'], [0., 0., 0.])
        with patch.object(journal, 'append', side_effect=OSError('disk full')):
            samples.observe(message)
        with self.assertRaisesRegex(probe.DiagnosticError, 'telemetry/log failure'):
            samples.current()


class ContractTests(unittest.TestCase):
    def test_standard_pose_payload_cannot_leak_experiment_job_id(self):
        _, _, plan = trial()
        payload = evidence.initial_pose_payload(plan['map_id'], plan['map_revision'], plan['start'])
        self.assertEqual(set(payload), {'map_id', 'map_revision', 'pose'})
        with self.assertRaises(ValueError):
            evidence.initial_pose_payload(plan['map_id'], plan['map_revision'], {'x': float('nan'), 'y': 0., 'yaw': 0.})

    def test_navigation_lease_is_required_not_blanket_rejected(self):
        n, c, plan = trial()
        result = evidence.check_navigation_trial(n, c, plan)
        self.assertTrue(result['snapshot_checks_passed'])
        self.assertFalse(result['motion_authorized'])
        for source, active in [('keyboard', True), ('navigation', False)]:
            c['control']['lease'] = {'input_source': source, 'active': active}
            with self.assertRaises(ValueError):
                evidence.check_navigation_trial(n, c, plan)

    def test_old_job_map_heading_and_unready_snapshots_are_rejected(self):
        n, c, plan = trial()
        mutations = [lambda v: v['pipeline'].update(job_id='old'),
                     lambda v: v['map'].update(revision='c'*64),
                     lambda v: v['localization']['pose'].update(yaw=.3),
                     lambda v: v['localization']['pose'].update(x=1.1),
                     lambda v: v['safety'].update(can_send_goal=False),
                     lambda v: v['goal'].update(state='active'),
                     lambda v: v['parameter_evidence']['live_ros'].update(status='stale')]
        for mutation in mutations:
            changed = copy.deepcopy(n)
            mutation(changed)
            with self.assertRaises(ValueError):
                evidence.check_navigation_trial(changed, c, plan)

    def test_failed_manual_preflight_never_clears_stop_or_arms(self):
        n, c, _ = trial()
        calls = []

        def call(path, body=None):
            calls.append((path, body))
            return c if path == 'control' else n

        state = {'control_attempted': False}
        with patch.object(probe, 'call', side_effect=call):
            with self.assertRaises(probe.DiagnosticError):
                asyncio.run(probe.drive(None, [], state))
        self.assertFalse(state['control_attempted'])
        self.assertEqual(set(path for path, _ in calls), {'control', 'navigation'})
        self.assertTrue(all(body is None for _, body in calls))

    def test_dry_run_and_import_need_no_ros_or_network(self):
        with patch.object(probe, 'call', side_effect=AssertionError('network')):
            self.assertEqual(probe.main([]), 0)
            with self.assertRaises(SystemExit):
                probe.main(['--execute'])
        result = subprocess.run([sys.executable, '-O', str(ROOT / 'scripts/run_go2_bounded_diagnostic.py')],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('OFFLINE PLAN ONLY', result.stdout)

    def test_optimized_python_keeps_preflight_guards(self):
        result = subprocess.run([sys.executable, '-O', '-c',
            "import sys;sys.path.insert(0,'scripts');from run_go2_bounded_diagnostic import manual_preflight;"
            "manual_preflight({'control':{'estop_latched':False,'lease':{'active':False}}},{})"],
            cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('manual probe requires STOP', result.stderr)


if __name__ == '__main__':
    unittest.main()
