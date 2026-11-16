#!/usr/bin/env python3
"""Stationary preparation only; default is offline validation, never sends a goal.

Replaces the one-off prepare_latest_pose_20261116.py. Live use requires a fresh
operator draft, explicit supervision and the existing local dashboard APIs.
No safety parameter, STOP latch, sensor freshness or matching gate is changed.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import uuid

from field_trial_evidence import initial_pose_payload, write_json

BASE = 'navigation/operational-3d'
HTTP_TIMEOUT_S = 10
# START validates map files and may wait for the startup snapshot before its
# acknowledgement. Do not mistake that admission work for a 10-second failure.
# This bounds only the client request; server readiness/safety gates stay intact.
NAVIGATION_START_HTTP_TIMEOUT_S = 90
# Only lifecycle failures may be reset automatically. Map/calibration/source
# changes require a newly reviewed context, not a broader recovery allow-list.
RETRY_CODES = frozenset({
    'INITIAL_HEIGHT_TILT_REQUIRED', 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED',
    'OBSERVATION_SESSION_CHANGED', 'HANDOFF_ALREADY_USED', 'HANDOFF_EXPIRED',
})


class PreparationError(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise PreparationError(reason)


def identity(pair):
    return tuple(pair[k][v] for k in ('localization_3d', 'navigation_2d')
                 for v in ('map_id', 'revision')) + (pair['calibration_sha256'],)


def validate_draft(draft):
    pair = draft['pair']
    for key in ('localization_3d', 'navigation_2d'):
        initial_pose_payload(pair[key]['map_id'], pair[key]['revision'], draft['pose'])
    require(isinstance(pair['generation'], str) and len(pair['generation']) == 32,
            'draft needs the current pair generation')
    require(isinstance(pair['calibration_sha256'], str)
            and len(pair['calibration_sha256']) == 64, 'draft needs calibration identity')


def call(path, body=None):
    origin = 'http://127.0.0.1:8088'
    request = urllib.request.Request(origin + '/api/v1/' + path,
        data=None if body is None else json.dumps(body, allow_nan=False).encode(),
        headers={'Origin': origin, 'Content-Type': 'application/json'})
    timeout = NAVIGATION_START_HTTP_TIMEOUT_S if path == 'navigation/start' and body is not None else HTTP_TIMEOUT_S
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Preserve the conflict reason, rather than only "HTTP 409".
        raise PreparationError(f'{path}: HTTP {exc.code}: '
                               + exc.read(4096).decode(errors='replace')) from exc


class Preparation:
    def __init__(self, api, save, *, clock=time.monotonic, sleep=time.sleep):
        self.api, self.save, self.clock, self.sleep = api, save, clock, sleep
        self.session = None
        self.nav_attempted = False
        self.job = None

    def read(self, path, name):
        value = self.api(path)
        self.save(name, value)
        return value

    def wait(self, path, predicate, seconds, name):
        deadline = self.clock() + seconds
        while True:
            value = self.read(path, name)
            require(self.clock() <= deadline, name + ': bounded wait expired')
            if predicate(value):
                return value
            self.sleep(.5)

    def idle(self):
        c = self.read('control', 'control-before')['control']
        n = self.read('navigation', 'navigation-before')
        o = self.read('observations/fastlio', 'observation-before')
        require(c['available'] is True and n['robot_online'] is True, 'robot offline')
        require(c['lease']['active'] is False and c['command']['deadman'] is False
                and all(c['command'][k] == 0 for k in ('linear_x', 'linear_y', 'angular_z')),
                'control is not released and stationary')
        require(n['pipeline']['state'] in {'idle', 'failed', 'stopped'}
                and n['pipeline']['job_id'] is None and n['goal']['state'] != 'active',
                'navigation still owns a job or goal')
        require(o['active'] is False and o['busy'] is False and o['bridge_guard'] is None,
                'observation stop/guard release not confirmed')
        return n

    def fresh_pair(self, draft):
        self.idle()
        state = self.read(BASE, 'pair-before')
        pair = state['pair']
        require(identity(pair) == identity(draft['pair'])
                and pair['generation'] == draft['pair']['generation'], 'draft context changed')
        codes = {c['code'] for c in pair['checks']}
        require(codes <= RETRY_CODES, 'pair has non-lifecycle errors; review required')
        require(pair['valid'] is True or bool(codes), 'invalid pair without explanation')
        if pair.get('seed_geometry') is None:
            require(pair['valid'] is True, 'invalid pair without old geometry')
            return pair
        # Reuse precisely the existing relationship, never invent an operator
        # declaration for a lineage-bound pair or change a map to get past a gate.
        require(not state['selected'].get('course_region'), 'course selection needs manual renewal')
        body = dict(zip(('map_id', 'map_revision', 'navigation_map_id', 'navigation_map_revision'),
                        identity(pair)[:4]))
        if pair['binding_source'] == 'operator_confirmed':
            confirmation = pair['operator_confirmation']
            require(confirmation['statement'] == 'derived_same_coordinates'
                    and confirmation['generation'] == pair['generation']
                    and all(confirmation[k] == {v: pair[k][v] for v in ('map_id', 'revision')}
                            for k in ('localization_3d', 'navigation_2d')),
                    'operator map relationship changed')
            body['pair_confirmation'] = confirmation['statement']
        else:
            require(pair['binding_source'] == 'conversion_lineage', 'unknown map relationship')
        self.idle()
        check = self.api(BASE)['pair']
        require(identity(check) == identity(pair) and check['generation'] == pair['generation']
                and check.get('seed_geometry') == pair.get('seed_geometry')
                and {c['code'] for c in check['checks']} <= RETRY_CODES,
                'pair changed before renewal')
        renewed = self.api(BASE + '/pair', body)['pair']
        self.save('pair-renewed', renewed)
        require(identity(renewed) == identity(pair)
                and renewed['binding_source'] == pair['binding_source']
                and renewed['generation'] != pair['generation']
                and renewed.get('seed_geometry') is None and renewed['valid'] is True
                and {c['code'] for c in renewed['checks']} <= {'INITIAL_HEIGHT_TILT_REQUIRED'},
                'pair renewal was not verified')
        return renewed

    def wait_initial_pose(self, pair):
        runtime = None
        def ready(n):
            nonlocal runtime
            require(n['pipeline']['state'] in {'starting', 'running'}, 'navigation startup ended')
            job = n['pipeline']['job_id']
            if job is not None:
                require(self.job is None or self.job == job, 'navigation job changed')
                self.job = job
            if n['safety']['can_set_initial_pose'] is not True:
                return False  # RUNNING alone is not node/TF/API readiness.
            require(n['pipeline']['state'] == 'running' and self.job is not None,
                    'initial pose ready without running job')
            require((n['map']['id'], n['map']['revision']) ==
                    (pair['navigation_2d']['map_id'], pair['navigation_2d']['revision']),
                    'navigation map changed')
            # The coarse UI flag can precede the server's measured-stop gate.
            # Wait for its actual fresh dwell, never infer stop from elapsed time.
            op = n.get('operational_localization') or {}
            if op.get('fresh') is not True:
                return False
            require(op.get('job_id') == self.job
                    and op.get('bundle_generation') == pair['generation']
                    and (op.get('map_id'), op.get('map_revision')) ==
                    (pair['navigation_2d']['map_id'], pair['navigation_2d']['revision'])
                    and (op.get('localization_map_id'), op.get('localization_map_revision')) ==
                    (pair['localization_3d']['map_id'], pair['localization_3d']['revision']),
                    'initial pose observation context changed')
            instance = op.get('runtime_instance_generation')
            if not isinstance(instance, str) or not instance:
                return False
            require(runtime is None or runtime == instance, 'initial pose runtime changed')
            runtime = instance
            stopped = op.get('stopped_seconds')
            return type(stopped) in (float, int) and math.isfinite(stopped) and stopped >= 2.
        return self.wait('navigation', ready, 45, 'nav-before-initial')

    def run(self, draft):
        validate_draft(draft)
        try:
            return self._run(copy.deepcopy(draft))
        except BaseException:
            self.cleanup()
            raise

    def _run(self, draft):
        pair = self.fresh_pair(draft)
        obs = self.api('observations/fastlio/start', {'confirmed': True})
        self.session = obs['session_id']
        def observation_ready(o):
            require(o['session_id'] == self.session, 'observation session changed')
            require(o['state'] not in {'FAILED', 'INVALIDATED', 'STOPPED'}, 'observation ended')
            return o['state'] == 'READY' and o['active'] is True
        self.wait('observations/fastlio', observation_ready, 20, 'observation-ready')
        prior = {'frame': 'map', 'pose_reference': 'base_link', 'units': 'metres_radians',
                 'pose': draft['pose'], 'source': 'OPERATOR_CURRENT_MAP_DRAFT',
                 'stationary_current_pose_confirmed': True,
                 'navigation_map_id': pair['navigation_2d']['map_id'],
                 'navigation_map_revision': pair['navigation_2d']['revision'],
                 'calibration_sha256': pair['calibration_sha256']}
        request = {'request_id': uuid.uuid4().hex, 'bundle_generation': pair['generation'],
                   'observation_session_id': self.session, 'operator_prior': prior}
        self.save('proposal-request', request)
        proposal = self.api(BASE + '/initialization-proposals', request)
        path = BASE + '/initialization-proposals/' + proposal['proposal_id']
        proposal = self.wait(path, lambda p: p['state'] not in {'capturing', 'running'},
                             45, 'proposal')
        require(proposal['state'] == 'ready', 'proposal rejected: ' + str(proposal.get('reason')))
        require(proposal['current_vs_prior']['within_existing_handoff_reference'] is True
                and proposal['current_vs_prior']['all_members_within_prior_bounds'] is True,
                'proposal outside existing bounds')
        handoff = self.api(path + '/confirm-geometry', {
            'request_id': uuid.uuid4().hex, 'bundle_generation': pair['generation'],
            'observation_session_id': self.session, 'confirmed': True,
            'stationary_supervision_acknowledged': True, 'conditional_prior_acknowledged': True})
        self.save('handoff', handoff)
        self.api('observations/fastlio/stop', {'confirmed': True, 'session_id': self.session})
        self.wait('observations/fastlio', lambda o: o['session_id'] in (None, self.session)
                  and o['state'] == 'STOPPED'
                  and o['active'] is False and o['busy'] is False and o['bridge_guard'] is None,
                  15, 'observation-stopped')
        def handoff_ready(state):
            current = state['pair']
            require(current['generation'] == pair['generation'] and identity(current) == identity(pair),
                    'pair changed during observation stop')
            return current['valid'] is True and current['can_start'] is True
        # Service inactivity can precede the handoff monitor's stop receipt.
        # Wait for the server's normal admission rather than dropping that gate.
        self.wait(BASE, handoff_ready, 15, 'pair-before-start')
        n = self.read('navigation', 'before-start')
        require(n['safety']['can_start'] is True, 'navigation start not permitted')
        params = n['parameter_evidence']['saved_and_generated']['stored']
        require(all(params['values'][k] == v for k, v in {
            'desired_linear_vel': .2, 'robot_radius': .22,
            'xy_goal_tolerance': .05, 'yaw_goal_tolerance': .1}.items()), 'field policy changed')
        self.nav_attempted = True
        self.save('nav-start', self.api('navigation/start', {
            'map_id': prior['navigation_map_id'], 'map_revision': prior['navigation_map_revision'],
            'parameters_revision': params['revision']}))
        self.wait_initial_pose(pair)
        response = self.api('navigation/initial-pose', initial_pose_payload(
            prior['navigation_map_id'], prior['navigation_map_revision'], draft['pose']))
        self.save('initial-pose-response', response)
        require(response['accepted'] is True, 'initial pose not accepted')
        n = self.wait('navigation', lambda n: bool((n.get('operational_localization') or {})
                     .get('accepted_initial_pose')), 8, 'initial-pose-receipt')
        require(n['pipeline']['job_id'] == self.job, 'navigation job changed')
        op = n['operational_localization']
        self.save('match-response', self.api(BASE + '/match', {
            'map_id': n['map']['id'], 'map_revision': n['map']['revision'],
            'bundle_generation': op['bundle_generation'],
            'localization_generation': op['localization_generation'],
            'initial_pose_stamp_ns': op['accepted_initial_pose']['stamp_ns']}))
        def goal_ready(n):
            require(n['pipeline']['job_id'] == self.job
                    and n['pipeline']['state'] == 'running', 'navigation job ended or changed')
            return n['safety']['can_send_goal'] is True
        result = self.wait('navigation', goal_ready, 40, 'goal-ready')
        c = self.read('control', 'control-ready')['control']
        require(result['goal']['state'] != 'active' and c['command']['deadman'] is False
                and all(c['command'][k] == 0 for k in ('linear_x', 'linear_y', 'angular_z')),
                'unexpected goal or command during stationary preparation')
        return result

    def cleanup(self):
        # Independent cleanup attempts; a failed export must never skip stopping.
        actions = []
        if self.nav_attempted:
            actions.append(('navigation', lambda: self.api('navigation/stop', {})))
        if self.session:
            actions.append(('observation', lambda: self.api('observations/fastlio/stop',
                            {'confirmed': True, 'session_id': self.session})))
        for name, action in actions:
            try:
                result = action()
            except Exception as exc:
                result = {'cleanup_error': str(exc)}
            try:
                self.save('cleanup-' + name, result)
            except Exception:
                pass
        for path in ('navigation', 'observations/fastlio', 'control'):
            try:
                self.read(path, 'cleanup-readback-' + path.replace('/', '-'))
            except Exception:
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--draft', type=Path, required=True,
                        help='fresh JSON: pair from operational-3d status and operator pose x/y/yaw')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--stationary-supervision', action='store_true')
    parser.add_argument('--conditional-prior-acknowledged', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    draft = json.loads(args.draft.read_text(encoding='utf-8-sig'))
    validate_draft(draft)
    if not args.execute:
        print(json.dumps({'draft_valid': True, 'network_used': False, 'goal_sent': False}))
        return 0
    if not (sys.platform == 'linux' and args.stationary_supervision
            and args.conditional_prior_acknowledged and args.output):
        parser.error('live preparation requires Linux, output, and both current supervision acknowledgements')
    args.output.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        write_json(args.output / (name + '.json'), value)
    prep = Preparation(call, save)
    try:
        prep.run(draft)
    except Exception as exc:
        save('error', {'error': str(exc), 'goal_sent': False})
        return 1
    print('Ready for user goal; no goal sent. Preparation remains subject to live freshness.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
