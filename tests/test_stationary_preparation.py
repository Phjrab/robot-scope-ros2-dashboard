"""Replay preparation failures with fake time/APIs; never contacts a robot."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


load('field_trial_evidence')
prep = load('prepare_go2_stationary')


def pair(old=True):
    p = {'generation': 'a' * 32, 'calibration_sha256': 'b' * 64,
         'localization_3d': {'map_id': 'c' * 24, 'revision': 'd' * 64},
         'navigation_2d': {'map_id': 'e' * 24, 'revision': 'f' * 64},
         'binding_source': 'operator_confirmed', 'valid': not old,
         'seed_geometry': {'source': 'proposal_confirmed'} if old else None,
         'checks': [{'code': c} for c in (['INITIAL_GEOMETRY_RECONFIRM_REQUIRED',
                                         'OBSERVATION_SESSION_CHANGED'] if old else
                                        ['INITIAL_HEIGHT_TILT_REQUIRED'])]}
    p['operator_confirmation'] = {k: copy.deepcopy(p[k]) for k in ('localization_3d', 'navigation_2d')}
    p['operator_confirmation'].update(generation=p['generation'], statement='derived_same_coordinates')
    return p


class FakeAPI:
    def __init__(self):
        self.pair = pair()
        self.draft = {'pair': copy.deepcopy(self.pair), 'pose': {'x': 1.25, 'y': -2.5, 'yaw': .1}}
        self.calls, self.saved = [], {}
        self.t = 0
        self.c = {'available': True, 'lease': {'active': False},
                  'command': {'deadman': False, 'linear_x': 0., 'linear_y': 0., 'angular_z': 0.}}
        self.n = {'robot_online': True, 'pipeline': {'state': 'failed', 'job_id': None},
                  'goal': {'state': 'idle'}, 'safety': {'can_start': False,
                  'can_set_initial_pose': False, 'can_send_goal': False},
                  'parameter_evidence': {'saved_and_generated': {'stored': {'revision': 'params',
                      'values': {'desired_linear_vel': .2, 'robot_radius': .22,
                                 'xy_goal_tolerance': .05, 'yaw_goal_tolerance': .1}}}}}
        self.o = {'session_id': None, 'state': 'STOPPED', 'active': False,
                  'busy': False, 'bridge_guard': None}
        self.start_reads = 0
        self.fail_proposal = False

    def sleep(self, seconds):
        self.t += seconds

    def runner(self):
        return prep.Preparation(self, lambda k, v: self.saved.__setitem__(k, copy.deepcopy(v)),
                                clock=lambda: self.t, sleep=self.sleep)

    def __call__(self, path, body=None):
        self.calls.append((path, copy.deepcopy(body)))
        if body is None:
            if path == 'control':
                return {'control': copy.deepcopy(self.c)}
            if path == prep.BASE:
                return {'pair': copy.deepcopy(self.pair), 'selected': {}}
            if path == 'observations/fastlio':
                return copy.deepcopy(self.o)
            if path == 'navigation':
                if self.start_reads:
                    self.start_reads += 1
                    self.n['pipeline'] = {'state': 'running', 'job_id': 'job'}
                    # Startup RUNNING lasts 2 polls without initial-pose readiness.
                    self.n['safety']['can_set_initial_pose'] = self.start_reads >= 4
                return copy.deepcopy(self.n)
            if '/initialization-proposals/' in path:
                return {'state': 'rejected' if self.fail_proposal else 'ready',
                        'reason': 'PRIOR_NO_MATCH' if self.fail_proposal else None,
                        'current_vs_prior': {'within_existing_handoff_reference': True,
                                             'all_members_within_prior_bounds': True}}
        elif path == prep.BASE + '/pair':
            self.pair.update(generation='1' * 32, seed_geometry=None, valid=True,
                             checks=[{'code': 'INITIAL_HEIGHT_TILT_REQUIRED'}])
            return {'pair': copy.deepcopy(self.pair)}
        elif path == 'observations/fastlio/start':
            self.o.update(session_id='2' * 32, state='READY', active=True, busy=True,
                          bridge_guard='HELD')
            return copy.deepcopy(self.o)
        elif path.endswith('/confirm-geometry'):
            self.pair.update(seed_geometry={'source': 'proposal_confirmed'}, can_start=True)
            return {'state': 'CONFIRMED_OBSERVATION_ACTIVE'}
        elif path == prep.BASE + '/initialization-proposals':
            return {'proposal_id': 'proposal'}
        elif path == 'observations/fastlio/stop':
            self.o.update(session_id=None, state='STOPPED', active=False, busy=False, bridge_guard=None)
            self.n['safety']['can_start'] = True
            return copy.deepcopy(self.o)
        elif path == 'navigation/start':
            self.start_reads = 1
            self.n['map'] = {'id': self.pair['navigation_2d']['map_id'],
                             'revision': self.pair['navigation_2d']['revision']}
            return {'accepted': True, 'pending': True}
        elif path == 'navigation/initial-pose':
            if not self.n['safety']['can_set_initial_pose']:
                raise RuntimeError('early initial pose')
            self.n['operational_localization'] = {'accepted_initial_pose': {'stamp_ns': '1'},
                'bundle_generation': self.pair['generation'], 'localization_generation': 3}
            return {'accepted': True}
        elif path == prep.BASE + '/match':
            self.n['safety']['can_send_goal'] = True
            return {'accepted': True}
        elif path == 'navigation/stop':
            self.start_reads = 0
            self.n['pipeline'] = {'state': 'failed', 'job_id': None}
            return copy.deepcopy(self.n)
        raise AssertionError('unexpected API request: ' + path)


class PreparationTests(unittest.TestCase):
    def test_retry_then_delayed_startup_completes_with_new_draft_and_no_goal(self):
        api = FakeAPI()
        result = api.runner().run(api.draft)
        self.assertTrue(result['safety']['can_send_goal'])
        posts = [(p, b) for p, b in api.calls if b is not None]
        self.assertEqual(posts[0][0], prep.BASE + '/pair')
        self.assertEqual(posts[1][0], 'observations/fastlio/start')
        self.assertGreaterEqual(api.t, 1.)
        sent = next(b for p, b in posts if p == 'navigation/initial-pose')
        self.assertEqual(sent['pose'], api.draft['pose'])
        self.assertNotIn('job_id', sent)
        self.assertFalse(any('/goal' in p or '/parameters' in p or '/control/' in p for p, _ in posts))
        self.assertFalse(any(p == 'navigation/stop' for p, _ in posts))

    def test_clean_pair_does_not_renew(self):
        api = FakeAPI()
        api.pair = pair(False)
        api.draft['pair'] = copy.deepcopy(api.pair)
        api.runner().fresh_pair(api.draft)
        self.assertFalse(any(b is not None for _, b in api.calls))

    def test_recovery_does_not_require_can_start_before_clearing_old_geometry(self):
        api = FakeAPI()
        self.assertFalse(api.n['safety']['can_start'])
        p = api.runner().fresh_pair(api.draft)
        self.assertTrue(p['valid'])
        self.assertIsNone(p['seed_geometry'])

    def test_conversion_lineage_is_not_replaced_by_operator_assumption(self):
        api = FakeAPI()
        api.pair['binding_source'] = 'conversion_lineage'
        api.draft['pair'] = copy.deepcopy(api.pair)
        api.runner().fresh_pair(api.draft)
        self.assertNotIn('pair_confirmation', next(b for _, b in api.calls if b is not None))

    def test_blocked_contexts_do_not_mutate(self):
        changes = [lambda a: a.c['lease'].update(active=True),
                   lambda a: a.c['command'].update(linear_x=.01),
                   lambda a: a.n.update(robot_online=False),
                   lambda a: a.n['pipeline'].update(job_id='another'),
                   lambda a: a.n['goal'].update(state='active'),
                   lambda a: a.o.update(busy=True),
                   lambda a: a.o.update(bridge_guard='HELD'),
                   lambda a: a.pair.update(calibration_sha256='9' * 64),
                   lambda a: a.pair['navigation_2d'].update(revision='8' * 64),
                   lambda a: a.pair.update(generation='7' * 32),
                   lambda a: a.pair.update(checks=[{'code': 'SOURCE_OR_CONTEXT_CHANGED'}])]
        for change in changes:
            with self.subTest(change=change):
                api = FakeAPI()
                change(api)
                with self.assertRaises(prep.PreparationError):
                    api.runner().run(api.draft)
                self.assertFalse(any(b is not None for _, b in api.calls))

    def test_rejected_proposal_stops_observation_without_starting_nav(self):
        api = FakeAPI()
        api.fail_proposal = True
        with self.assertRaisesRegex(prep.PreparationError, 'PRIOR_NO_MATCH'):
            api.runner().run(api.draft)
        posts = [p for p, b in api.calls if b is not None]
        self.assertIn('observations/fastlio/stop', posts)
        self.assertNotIn('navigation/start', posts)

    def test_startup_wait_times_out_without_accepting_running(self):
        api = FakeAPI()
        api.n['pipeline'] = {'state': 'running', 'job_id': 'job'}
        with self.assertRaisesRegex(prep.PreparationError, 'bounded wait expired'):
            api.runner().wait_initial_pose(api.pair)
        self.assertLessEqual(api.t, 45.5)

    def test_terminal_startup_fails_immediately(self):
        for state in ('failed', 'idle', 'stopped'):
            api = FakeAPI()
            api.n['pipeline']['state'] = state
            with self.assertRaisesRegex(prep.PreparationError, 'startup ended'):
                api.runner().wait_initial_pose(api.pair)
            self.assertEqual(api.t, 0)

    def test_changed_job_or_map_is_rejected(self):
        for change in ('job', 'map'):
            api = FakeAPI()
            api.n['pipeline'] = {'state': 'running', 'job_id': 'new'}
            api.n['safety']['can_set_initial_pose'] = True
            api.n['map'] = {'id': 'wrong', 'revision': 'wrong'}
            runner = api.runner()
            runner.job = 'old' if change == 'job' else None
            with self.assertRaisesRegex(prep.PreparationError, 'changed'):
                runner.wait_initial_pose(api.pair)

    def test_cleanup_continues_after_stop_and_export_failures(self):
        calls = []
        def broken(path, body=None):
            calls.append(path)
            raise RuntimeError('unavailable')
        def no_disk(*args):
            raise OSError('disk full')
        runner = prep.Preparation(broken, no_disk)
        runner.nav_attempted, runner.session = True, 'session'
        runner.cleanup()
        self.assertEqual(calls[:2], ['navigation/stop', 'observations/fastlio/stop'])
        self.assertEqual(calls[-3:], ['navigation', 'observations/fastlio', 'control'])

    def test_offline_default_uses_no_network(self):
        with tempfile.TemporaryDirectory() as directory:
            f = Path(directory) / 'draft.json'
            f.write_text(json.dumps(FakeAPI().draft))
            with patch.object(prep, 'call', side_effect=AssertionError('network forbidden')):
                self.assertEqual(prep.main(['--draft', str(f)]), 0)

    def test_live_requires_current_acknowledgements(self):
        with tempfile.TemporaryDirectory() as directory:
            f = Path(directory) / 'draft.json'
            f.write_text(json.dumps(FakeAPI().draft))
            with patch.object(prep, 'call', side_effect=AssertionError('network forbidden')):
                with self.assertRaises(SystemExit):
                    prep.main(['--draft', str(f), '--execute'])

    def test_real_catalogue_renewal_clears_used_geometry_without_changing_maps_or_policy(self):
        from test_operational_navigation_bundle import OperationalNavigationBundleTests
        fixture = OperationalNavigationBundleTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        manager = fixture.manager
        selection = {k: v for k, v in fixture.selection.items() if k != 'seed_pose'}
        selection['pair_confirmation'] = 'derived_same_coordinates'
        selected = manager.select_pair(selection)
        manager.seed_geometry({'generation': selected['pair']['generation'], 'z': .1, 'roll': 0., 'pitch': 0.})
        manager.used_geometry = (manager.selected['generation'], manager.selected['seed_geometry']['confirmed_at'])
        before = manager.status()
        api = FakeAPI()
        api.pair = before['pair']
        draft = {'pair': copy.deepcopy(api.pair), 'pose': api.draft['pose']}
        policy = copy.deepcopy(manager.selected['policy'])
        map_bytes = fixture.pcd.read_bytes(), fixture.image.read_bytes()
        def real_pair(path, body=None):
            if path == prep.BASE:
                return manager.status()
            if path == prep.BASE + '/pair':
                return manager.select_pair(body)
            return api(path, body)
        result = prep.Preparation(real_pair, lambda *_: None).fresh_pair(draft)
        self.assertNotEqual(result['generation'], before['pair']['generation'])
        self.assertIsNone(result['seed_geometry'])
        self.assertEqual(manager.selected['policy'], policy)
        self.assertEqual(map_bytes, (fixture.pcd.read_bytes(), fixture.image.read_bytes()))


if __name__ == '__main__':
    unittest.main()
