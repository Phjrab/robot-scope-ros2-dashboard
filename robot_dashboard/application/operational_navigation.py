"""Explicit idle selection and immutable per-Nav2-job 3D map bundles."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import threading
import uuid
import time

from ..relocalization.experimental_se3 import from_translation_rpy, validate_transform
from ..relocalization.operational import SCHEMA, digest, validate_bundle, display_pose
from ..relocalization.handoff_policy import POLICY_ID, TTL_S, MAX_XY_M, MAX_YAW_RAD, process_identity, validate_handoff, validate_candidate
from ..saved_maps import SavedMapError
from .runtime_health_sample import RuntimeHealthSample


def _navigation_map_body_pose(calibration, body):
    """Transform the localization-map body hypothesis into the navigation map."""
    transformed = (validate_transform(calibration['T_nav_map_from_localization_map'])
        @ from_translation_rpy([body[k] for k in ('x', 'y', 'z')],
                               [body[k] for k in ('roll', 'pitch', 'yaw')]))
    return display_pose(transformed)


class OperationalNavigation:
    def __init__(self, catalog, root, jobs):
        self.catalog, self.root, self.jobs = catalog, Path(root), jobs
        self.lock = threading.RLock()
        self._handoff_watch_lock = threading.RLock()
        # Never restore execution selection/seed across dashboard restarts.
        self.selected = None
        # Private path identities for status reads, never cached content/proof.
        self._selected_records = None
        self.used_geometry = None
        self.snapshot_binding = None
        self._snapshot_binding_monotonic_ns = None
        self._handoffs = {}
        self._handoff_requests = {}
        self._handoff_watch_thread = None
        self._handoff_watch_closed = False

    def status(self):
        with self.lock:
            return self._status_locked()

    def _status_locked(self, *, pair_validated=False):
        """Project this request's proof; public reads always revalidate assets."""
        initial = None
        if self.selected and self.selected.get('seed_T_map_imu') is not None:
            calibration = self.selected['calibration']
            pose = (validate_transform(calibration['T_nav_map_from_localization_map'])
                    @ validate_transform(self.selected['seed_T_map_imu'])
                    @ validate_transform(calibration['T_imu_base']))
            initial = {'map_id': self.selected['navigation_2d']['map_id'],
                       'map_revision': self.selected['navigation_2d']['revision'],
                       'pose': {'x': float(pose[0, 3]), 'y': float(pose[1, 3]),
                                'yaw': math.atan2(pose[1, 0], pose[0, 0])}}
        pair = self._pair_status(validated=pair_validated)
        handoff = None
        geometry = (self.selected or {}).get('seed_geometry') or {}
        identifier = (geometry.get('handoff') or {}).get('handoff_id')
        record = self._handoffs.get(identifier)
        if record:
            context = self._handoff_job_context(record)
            # A different identified job/map is never restored into this view.
            if context != 'HANDOFF_RUNTIME_CHANGED':
                handoff = self.handoff_status(identifier, validate_assets=False)
            if handoff and pair and any(item['code'] not in {'INITIAL_HEIGHT_TILT_REQUIRED', 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED',
                            'HANDOFF_EXPIRED', 'HANDOFF_ALREADY_USED', 'HANDOFF_OBSERVATION_STOP_REQUIRED',
                            'HANDOFF_STOP_OUTCOME_UNKNOWN', 'HANDOFF_WORKER_NOT_SETTLED', 'HANDOFF_MONITOR_PENDING',
                            'SOURCE_OR_CONTEXT_CHANGED', 'HANDOFF_MONITOR_UNAVAILABLE', 'OBSERVATION_SESSION_CHANGED'} for item in pair['checks']):
                handoff.update(state='INVALID', reason='MAP_PAIR_CHANGED', geometry=None, initial_pose_reference=None)
        return {'selected': copy.deepcopy(self.selected), 'pair': pair,
                'initialization_handoff': handoff,
                'initial_pose_confirmation': initial,
                'calibration_available': (self.root / 'operational-calibration.json').is_file(),
                'activation': 'NEXT_NAVIGATION_START' if self.selected else 'LEGACY_2D'}

    def _idle(self):
        if self.jobs.snapshot()['pipeline']['state'] not in {'idle', 'stopped', 'failed'}:
            raise ValueError('STOP_NAVIGATION_BEFORE_SOURCE_SELECTION')

    def _calibration(self):
        path = self.root / 'operational-calibration.json'
        if not path.is_file():
            raise ValueError('DEVICE_BODY_MAP_ALIGNMENT_READBACK_REQUIRED')
        if path.is_symlink() or path.stat().st_size > 128 * 1024:
            raise ValueError('INVALID_CALIBRATION_FILE')
        calibration = json.loads(path.read_text())
        if calibration.get('verified') is not True or not calibration.get('evidence'):
            raise ValueError('BODY_AND_MAP_CALIBRATION_REQUIRED')
        from ..relocalization.transform_authority import TransformAuthorityMonitor
        TransformAuthorityMonitor(calibration.get('tf_publishers'))
        validate_transform(calibration['T_imu_base'])
        return calibration, digest(path)

    def _family(self, source, nav, *, geometry=None):
        """Use persisted conversion proof, never map names or coincident frame labels."""
        from ..map_lineage import parse_family_document
        # resolve_navigation_map already read and validated the exact occupancy
        # sidecar. Reuse that same request's proof, not another whole catalog scan.
        if nav.family is None:
            raise ValueError('MAP_PAIR_LINEAGE_MISMATCH')
        family = parse_family_document(nav.family)
        if (family['source']['pcd_map_id'] != source['map_id']
                or family['source']['pcd_revision'] != source['revision']
                or family['source']['frame_id'] != source['frame_id']
                or family['occupancy']['map_id'] != nav.map_id
                or family['occupancy']['map_revision'] != nav.revision):
            raise ValueError('MAP_PAIR_LINEAGE_MISMATCH')
        geometry = geometry if geometry is not None else self.catalog._read_map_yaml(nav.yaml_path)
        _, width, height, _ = self.catalog._read_pgm_header(nav.image_path)
        expected = {'frame_id': nav.frame_id, 'resolution': geometry['resolution'],
                    'origin': list(geometry['origin']), 'width': width, 'height': height}
        if any(family['occupancy'].get(key) != value for key, value in expected.items()):
            raise ValueError('MAP_PAIR_GEOMETRY_MISMATCH')
        return family

    def _pair_status(self, *, validated=False):
        bundle = self.selected
        if not bundle or bundle.get('workflow') != 'staged_navigation_pair':
            return None
        checks = []
        try:
            if not validated:
                self._revalidate_pair(bundle, references=self._selected_records)
        except (ValueError, KeyError, OSError, SavedMapError) as exc:
            checks.append({'code': str(exc), 'current': '지도 또는 교정 확인이 무효가 됨',
                'required': '현재 ID·revision·교정과 일치하는 지도 조합',
                'remedy': '정상 정지 후 지도를 다시 선택하고 ①부터 연결 확인'})
        geometry = bundle.get('seed_geometry')
        if geometry is not None and self.used_geometry == (bundle['generation'], geometry['confirmed_at']) and self.jobs.snapshot()['pipeline']['state'] in {'idle', 'stopped', 'failed'}:
            checks.append({'code': 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED', 'current': '이전 실행에서 사용한 높이·기울기',
                'required': '새 실행의 현재 초기 높이·기울기 확인', 'remedy': '②에서 현재 값을 다시 확인하고 적용'})
        if (geometry is not None and geometry.get('source') == 'proposal_confirmed'
                and self.jobs.snapshot()['pipeline']['state'] != 'running'):
            try:
                self._check_proposal_geometry(geometry)
            except (ValueError, KeyError, OSError) as exc:
                checks.append({'code': str(exc), 'current': '제안 확인 또는 관측 종료 확인 필요',
                    'required': '유효한 제안과 확인된 관측 종료', 'remedy': '상태 확인 후 정상 절차를 다시 진행'})
        if geometry is None:
            checks.append({'code': 'INITIAL_HEIGHT_TILT_REQUIRED', 'current': '초기 높이·기울기 미지정',
                'required': '지도 좌표의 본체 높이(z)·roll·pitch 초기값',
                'remedy': '②에서 확인한 높이·기울기를 입력하고 적용. 미확인 값은 비워 두기'})
        return {'generation': bundle['generation'], 'localization_3d': copy.deepcopy(bundle['localization_3d']),
                'navigation_2d': copy.deepcopy(bundle['navigation_2d']),
                'family': copy.deepcopy(bundle['map_binding']['family']),
                'calibration_sha256': bundle['map_binding']['calibration_sha256'],
                'seed_geometry': copy.deepcopy(geometry), 'checks': checks,
                'valid': not any(item['code'] not in {'INITIAL_HEIGHT_TILT_REQUIRED', 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED'} for item in checks),
                'can_start': not checks, 'restart_from_step': 1 if any(item['code'] not in {'INITIAL_HEIGHT_TILT_REQUIRED', 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED'} for item in checks) else 2 if checks else None}

    def _revalidate_pair(self, bundle, *, references=None):
        with self.catalog.pinned_lookup(references=references):
            source = self.catalog.pcd_edit_source(bundle['localization_3d']['map_id'])
            if source['revision'] != bundle['localization_3d']['revision'] or source['sha256'] != bundle['localization_3d']['sha256']:
                raise ValueError('LOCALIZATION_MAP_REVISION_CHANGED')
            pin = bundle['navigation_2d']
            nav = self.catalog.resolve_navigation_map(pin['map_id'], pin['revision'])
            family = self._family(source, nav)
            if family != bundle['map_binding']['family']:
                raise ValueError('MAP_PAIR_LINEAGE_CHANGED')
            calibration, sha = self._calibration()
            if sha != bundle['map_binding']['calibration_sha256']:
                raise ValueError('CALIBRATION_CHANGED_REAPPLY_PAIR')
            if (calibration.get('controller_odom_topic') != self.jobs.controller_odom_topic
                    or calibration.get('navigation_profile') != self.jobs.navigation_profile):
                raise ValueError('CALIBRATION_PROFILE_OR_MAP_MISMATCH')

    def confirm_proposal(self, proposal_owner, observation, proposal_id, request_id, generation, session_id):
        with self.lock:
            key = (proposal_id, generation, session_id)
            prior = self._handoff_requests.get(request_id)
            if prior:
                if prior[0] != key:
                    raise ValueError('REQUEST_ID_CONTEXT_CONFLICT')
                identifier = prior[1]
            else:
                self._idle()
                proposal = proposal_owner.get(proposal_id)
                proposal_read_at = time.monotonic()
                if proposal.get('state') != 'ready':
                    raise ValueError(proposal.get('reason') or 'PROPOSAL_NOT_READY')
                bundle = self.selected
                if (not bundle or bundle.get('generation') != generation
                        or proposal.get('observation_session_id') != session_id
                        or proposal.get('pair', {}).get('generation') != generation):
                    raise ValueError('MAP_PAIR_CHANGED')
                provenance = proposal.get('provenance') or {}
                pair = proposal.get('pair') or {}
                if (pair.get('localization_3d') != bundle['localization_3d']
                        or pair.get('navigation_2d') != bundle['navigation_2d']
                        or pair.get('calibration_sha256') != bundle['map_binding']['calibration_sha256']
                        or provenance.get('bundle_generation') != generation
                        or provenance.get('observation_session_id') != session_id
                        or provenance.get('calibration_sha256') != bundle['map_binding']['calibration_sha256']
                        or (proposal.get('quality') or {}).get('ambiguity_unresolved') is not False
                        or (proposal.get('body_candidate') or {}).get('pose_reference') != 'base_link'
                        or (proposal.get('body_candidate') or {}).get('units') != 'metres_radians'):
                    raise ValueError('SOURCE_OR_CONTEXT_CHANGED')
                age = provenance.get('pose_age_s')
                if type(age) not in (int, float) or not math.isfinite(age) or not 0 <= age + time.monotonic() - proposal_read_at <= 1.:
                    raise ValueError('OBSERVATION_INPUTS_UNAVAILABLE')
                session = observation.snapshot()
                if session.get('session_id') != session_id or session.get('state') != 'READY':
                    raise ValueError('OBSERVATION_SESSION_CHANGED')
                body = proposal['body_candidate']['pose']
                pose = _navigation_map_body_pose(bundle['calibration'], body)
                identifier = uuid.uuid4().hex
                try:
                    watch_context = proposal_owner.handoff_watch_context(proposal_id, session_id)
                except AttributeError as exc:
                    raise ValueError('HANDOFF_MONITOR_UNAVAILABLE') from exc
                if not isinstance(watch_context, dict) or watch_context.get('session') != {'session_id': session_id, 'started_monotonic_s': session['started_monotonic_s']}:
                    raise ValueError('OBSERVATION_SESSION_CHANGED')
                if (not isinstance(watch_context.get('identity'), tuple) or len(watch_context['identity']) != 2
                        or not isinstance(watch_context.get('stamps'), tuple) or len(watch_context['stamps']) != 2
                        or any(type(stamp) is not int or stamp <= 0 for stamp in watch_context['stamps'])):
                    raise ValueError('HANDOFF_MONITOR_UNAVAILABLE')
                if self._handoff_watch_closed:
                    raise ValueError('HANDOFF_MONITOR_UNAVAILABLE')
                observation.reserve_handoff_receipt(identifier, session_id, session['started_monotonic_s'])
                now = time.monotonic()
                proof = {'policy_id': POLICY_ID, 'handoff_id': identifier, 'proposal_id': proposal_id,
                    'bundle_generation': generation, 'observation_session_id': session_id,
                    'calibration_sha256': bundle['map_binding']['calibration_sha256'],
                    'localization_map_id': bundle['localization_3d']['map_id'],
                    'localization_map_revision': bundle['localization_3d']['revision'],
                    'navigation_map_id': bundle['navigation_2d']['map_id'],
                    'navigation_map_revision': bundle['navigation_2d']['revision'],
                    'observation_started_monotonic_s': session['started_monotonic_s'],
                    'capture_stamp_ns': str(provenance['capture_stamp_ns']),
                    'source_contract_sha256': hashlib.sha256(json.dumps(provenance['source_contract'], sort_keys=True, allow_nan=False).encode()).hexdigest(),
                    'reference': {k: pose[k] for k in ('x','y','yaw')},
                    'expires_monotonic_s': now + TTL_S, 'owner_pid': os.getpid(),
                    'owner_start_ticks': process_identity(os.getpid()), 'stop_nonce': '', 'stop_state': 'NOT_REQUESTED'}
                geometry = {k: pose[k] for k in ('z','roll','pitch')}
                geometry.update(source='proposal_confirmed', frame='map', confirmed_at=time.time(), handoff=proof)
                self.selected = copy.deepcopy(bundle)
                self.selected['seed_geometry'] = geometry
                with self._handoff_watch_lock:
                    if len(self._handoffs) >= 32:
                        old = next(iter(self._handoffs))
                        self._handoffs.pop(old)
                        self._handoff_requests = {k:v for k,v in self._handoff_requests.items() if v[1] != old}
                    self._handoffs[identifier] = {'geometry': geometry, 'observation': observation,
                        'proposal_owner': proposal_owner, 'proposal_id': proposal_id, 'generation': generation,
                        'session_id': session_id, 'session_started': session['started_monotonic_s'], 'bound_nonce': None,
                        'snapshotted': False, 'job_id': None, 'match_binding': None, 'invalid': None,
                        'global_owner': proposal_owner.runtime.global_observation, 'watch_state': 'RUNNING',
                        'watch_identity': watch_context['identity'], 'watch_stamps': watch_context['stamps'],
                        'watch_last': now}
                    self._handoff_requests[request_id] = (key, identifier)
                    self._start_handoff_watcher()
        # Asset reads can be slow; let the observer watch throughout them.
        return self.handoff_status(identifier)

    def _start_handoff_watcher(self):
        # One bounded watcher per manager, never a watcher or callback in stop().
        thread = self._handoff_watch_thread
        if thread is None or not thread.is_alive():
            thread = threading.Thread(target=self._watch_handoffs, name='proposal-handoff-watch', daemon=True)
            self._handoff_watch_thread = thread
            try:
                thread.start()
            except Exception:
                self._handoff_watch_thread = None
                for record in self._handoffs.values():
                    if record.get('watch_state') == 'RUNNING':
                        record.update(watch_state='INVALID', invalid='HANDOFF_MONITOR_UNAVAILABLE')
                raise ValueError('HANDOFF_MONITOR_UNAVAILABLE') from None

    def close_handoff_monitor(self):
        with self.lock, self._handoff_watch_lock:
            self._handoff_watch_closed = True
            for record in self._handoffs.values():
                if record.get('watch_state') == 'RUNNING':
                    record.update(watch_state='INVALID', invalid='HANDOFF_MONITOR_UNAVAILABLE')

    def _watch_handoffs(self):
        while True:
            with self._handoff_watch_lock:
                if self._handoff_watch_closed:
                    self._handoff_watch_thread = None
                    return
                active = [(key, record) for key, record in self._handoffs.items()
                          if record.get('watch_state') == 'RUNNING']
                if not active:
                    self._handoff_watch_thread = None
                    return
            for identifier, record in active:
                try:
                    before = record['observation'].handoff_receipt(identifier)
                    state = before.get('state')
                    if state in {'DISPATCH_PENDING', 'DISPATCH_ACCEPTED', 'INACTIVE_CONFIRMED'}:
                        outcome = ('STOP_BOUNDARY', None, None)
                    elif state != 'NOT_REQUESTED':
                        outcome = ('INVALID', 'HANDOFF_STOP_OUTCOME_UNKNOWN', None)
                    elif record['proposal_owner'].runtime.global_observation is not record['global_owner']:
                        outcome = ('INVALID', 'SOURCE_OR_CONTEXT_CHANGED', None)
                    else:
                        sample = record['proposal_owner'].handoff_watch_sample()
                        after = record['observation'].handoff_receipt(identifier)
                        changed = (sample.get('session') != {'session_id': record['session_id'],
                                        'started_monotonic_s': record['session_started']}
                            or sample.get('state') != 'READY' or sample.get('active') is not True
                            or sample.get('identity') != record['watch_identity']
                            or not isinstance(sample.get('stamps'), tuple) or len(sample['stamps']) != 2
                            or any(type(a) is not int or a <= 0 for a in sample['stamps'])
                            or any(a < b for a, b in zip(sample['stamps'], record['watch_stamps'])))
                        if after.get('state') == 'NOT_REQUESTED':
                            outcome = ('INVALID', 'SOURCE_OR_CONTEXT_CHANGED', None) if changed else ('RUNNING', None, sample)
                        elif after.get('state') in {'DISPATCH_PENDING', 'DISPATCH_ACCEPTED', 'INACTIVE_CONFIRMED'}:
                            # A sample completed before dispatch is pre-stop evidence.
                            before_dispatch = (type(after.get('dispatch_monotonic_ns')) is int
                                and type(sample.get('sample_end_ns')) is int
                                and sample['sample_end_ns'] <= after['dispatch_monotonic_ns'])
                            outcome = (('INVALID', 'SOURCE_OR_CONTEXT_CHANGED', None) if changed and before_dispatch
                                       else ('STOP_BOUNDARY', None, None))
                        else:
                            outcome = ('INVALID', 'HANDOFF_STOP_OUTCOME_UNKNOWN', None)
                except Exception:
                    failed_at = time.monotonic_ns()
                    try:
                        after = record['observation'].handoff_receipt(identifier)
                        if (after.get('state') in {'DISPATCH_PENDING', 'DISPATCH_ACCEPTED', 'INACTIVE_CONFIRMED'}
                                and type(after.get('dispatch_monotonic_ns')) is int
                                and failed_at >= after['dispatch_monotonic_ns']):
                            outcome = ('STOP_BOUNDARY', None, None)
                        else:
                            outcome = ('INVALID', 'HANDOFF_MONITOR_UNAVAILABLE', None)
                    except Exception:
                        outcome = ('INVALID', 'HANDOFF_MONITOR_UNAVAILABLE', None)
                with self._handoff_watch_lock:
                    if self._handoffs.get(identifier) is not record or record.get('watch_state') != 'RUNNING':
                        continue
                    if record.get('invalid'):
                        record['watch_state'] = 'INVALID'
                        continue
                    if time.monotonic() >= record['geometry']['handoff']['expires_monotonic_s']:
                        outcome = ('INVALID', 'HANDOFF_EXPIRED', None)
                    elif ((self.selected or {}).get('generation') != record['generation']
                          or (((self.selected or {}).get('seed_geometry') or {}).get('handoff') or {}).get('handoff_id') != identifier):
                        outcome = ('INVALID', 'MAP_PAIR_CHANGED', None)
                    record['watch_state'] = outcome[0]
                    if outcome[1]:
                        record['invalid'] = outcome[1]
                    if outcome[2]:
                        record['watch_stamps'] = outcome[2]['stamps']
                        record['watch_last'] = time.monotonic()
            threading.Event().wait(.1)

    def _handoff_gate(self, record, *, require_stopped=True):
        # The watcher uses its own short lock, independent of slow map reads.
        with self._handoff_watch_lock:
            return self._handoff_gate_locked(record, require_stopped=require_stopped)

    def _handoff_gate_locked(self, record, *, require_stopped=True):
        geometry = record['geometry']
        proof = geometry['handoff']
        if record['invalid']:
            raise ValueError(record['invalid'])
        if time.monotonic() >= proof['expires_monotonic_s']:
            raise ValueError('HANDOFF_EXPIRED')
        if record['watch_state'] == 'RUNNING' and (self._handoff_watch_thread is None
                or not self._handoff_watch_thread.is_alive() or time.monotonic() - record['watch_last'] > 2.):
            record.update(watch_state='INVALID', invalid='HANDOFF_MONITOR_UNAVAILABLE')
            raise ValueError(record['invalid'])
        if (not self.selected or self.selected.get('generation') != record['generation']
                or (self.selected.get('seed_geometry') or {}).get('handoff', {}).get('handoff_id') != proof['handoff_id']):
            record['invalid'] = 'MAP_PAIR_CHANGED'
            raise ValueError(record['invalid'])
        receipt = record['observation'].handoff_receipt(proof['handoff_id'])
        receipt_state = receipt.get('state')
        nonce = receipt.get('nonce')
        if (receipt.get('session_id') != record['session_id']
                or receipt.get('started') != record['session_started']
                or receipt_state not in {'NOT_REQUESTED', 'DISPATCH_PENDING', 'DISPATCH_ACCEPTED', 'INACTIVE_CONFIRMED'}
                or (receipt_state == 'NOT_REQUESTED' and nonce is not None)
                or (receipt_state != 'NOT_REQUESTED' and (not isinstance(nonce, str)
                    or len(nonce) != 32 or any(c not in '0123456789abcdef' for c in nonce)))
                or (record['bound_nonce'] is not None and record['bound_nonce'] != nonce)):
            record['invalid'] = 'HANDOFF_STOP_OUTCOME_UNKNOWN'
            raise ValueError(record['invalid'])
        if nonce is not None and record['bound_nonce'] is None:
            record['bound_nonce'] = nonce
        if receipt_state != 'INACTIVE_CONFIRMED':
            if require_stopped:
                raise ValueError('HANDOFF_OBSERVATION_STOP_REQUIRED')
            return receipt
        if record['watch_state'] != 'STOP_BOUNDARY':
            raise ValueError('HANDOFF_MONITOR_PENDING')
        current = record['observation'].snapshot()
        if (current.get('active') is not False or current.get('state') != 'STOPPED'
                or current.get('session_id') not in (None, record['session_id'])):
            record['invalid'] = 'OBSERVATION_SESSION_CHANGED'
            raise ValueError(record['invalid'])
        try:
            if record['proposal_owner'].runtime.global_observation is not record['global_owner']:
                raise ValueError('HANDOFF_RUNTIME_CHANGED')
            job = record['global_owner'].job(record['proposal_id'])
        except Exception as exc:
            raise ValueError('HANDOFF_WORKER_NOT_SETTLED') from exc
        if job.get('worker_active'):
            raise ValueError('HANDOFF_WORKER_NOT_SETTLED')
        if proof['stop_nonce'] not in ('', record['bound_nonce']):
            record['invalid'] = 'HANDOFF_STOP_OUTCOME_UNKNOWN'
            raise ValueError(record['invalid'])
        proof.update(stop_nonce=record['bound_nonce'], stop_state='INACTIVE_CONFIRMED')
        self.selected['seed_geometry']['handoff'].update(stop_nonce=record['bound_nonce'], stop_state='INACTIVE_CONFIRMED')
        validate_handoff(geometry, self.selected)
        return receipt

    def _handoff_job_context(self, record):
        snapshot = self.jobs.snapshot()
        pipeline = snapshot.get('pipeline') or {}
        state = pipeline.get('state')
        job_id = pipeline.get('job_id')
        current_map = snapshot.get('map') or {}
        selected_map = (self.selected or {}).get('navigation_2d') or {}
        if not record['job_id']:
            if state in {'idle', 'stopped', 'failed'}:
                return None
            return 'HANDOFF_JOB_CONTEXT_UNCONFIRMED'
        if ((job_id and job_id != record['job_id'])
                or (current_map.get('id') and current_map['id'] != selected_map.get('map_id'))
                or (current_map.get('revision') and current_map['revision'] != selected_map.get('revision'))):
            return 'HANDOFF_RUNTIME_CHANGED'
        if not job_id or not current_map.get('id') or not current_map.get('revision'):
            return 'HANDOFF_JOB_CONTEXT_UNCONFIRMED'
        if state == 'running':
            return None
        if state in {'starting', 'stopping'}:
            return 'HANDOFF_JOB_' + state.upper()
        if state in {'idle', 'stopped', 'failed'}:
            return 'HANDOFF_JOB_NOT_RUNNING'
        return 'HANDOFF_JOB_CONTEXT_UNCONFIRMED'

    @staticmethod
    def _handoff_selection_identity(bundle):
        value = copy.deepcopy(bundle)
        if value:
            proof = ((value.get('seed_geometry') or {}).get('handoff') or {})
            for key in ('stop_nonce', 'stop_state', 'job_id'):
                proof.pop(key, None)
        return value

    def handoff_status(self, handoff_id, *, validate_assets=True, health=None):
        # Pin the selected context before slow reads. Never hold the manager lock
        # across a catalog/hash operation: the source watcher needs that lock.
        validation_error = None
        expected_record = None
        expected_generation = None
        if validate_assets:
            with self.lock:
                expected_record = self._handoffs.get(handoff_id)
                if not expected_record:
                    raise KeyError('HANDOFF_NOT_FOUND')
                candidate = copy.deepcopy(self.selected)
                references = self._selected_records
                expected_generation = expected_record['generation']
                expected_selection = self._handoff_selection_identity(candidate)
            try:
                if (not candidate or candidate.get('generation') != expected_generation
                        or ((candidate.get('seed_geometry') or {}).get('handoff') or {}).get('handoff_id') != handoff_id):
                    raise ValueError('MAP_PAIR_CHANGED')
                self._revalidate_pair(candidate, references=references)
            except (ValueError, KeyError, OSError, SavedMapError) as exc:
                validation_error = str(exc).strip("' ")
        with self.lock:
            record = self._handoffs.get(handoff_id)
            if not record:
                raise KeyError('HANDOFF_NOT_FOUND')
            geometry = record['geometry']
            proof = geometry['handoff']
            reason = None
            try:
                if validate_assets and (record is not expected_record
                        or self._handoff_selection_identity(self.selected) != expected_selection
                        or (self.selected or {}).get('generation') != expected_generation
                        or (((self.selected or {}).get('seed_geometry') or {}).get('handoff') or {}).get('handoff_id') != handoff_id):
                    raise ValueError('MAP_PAIR_CHANGED')
                if validation_error:
                    raise ValueError(validation_error)
                context = self._handoff_job_context(record)
                if context:
                    raise ValueError(context)
                if record['match_binding']:
                    binding = self.snapshot_binding or {}
                    current_geometry = (self.selected or {}).get('seed_geometry') or {}
                    if ((self.selected or {}).get('generation') != record['generation']
                            or (current_geometry.get('handoff') or {}).get('handoff_id') != handoff_id
                            or binding.get('job_id') != record['job_id']):
                        raise ValueError('HANDOFF_RUNTIME_CHANGED')
                    current = self._match_health_binding(health, record,
                                                         expected_stamp=record['match_binding']['initial_pose_stamp_ns'])
                    if current != record['match_binding']:
                        raise ValueError('HANDOFF_RUNTIME_CHANGED')
                    receipt = record['observation'].handoff_receipt(handoff_id)
                    state = 'MATCH_ARMED'
                else:
                    receipt = self._handoff_gate(record, require_stopped=False)
                    state = ('SNAPSHOTTED' if record['snapshotted'] else
                    'OBSERVATION_STOPPED' if receipt['state'] == 'INACTIVE_CONFIRMED' else
                    'STOP_PENDING' if receipt['state'] in {'DISPATCH_PENDING','DISPATCH_ACCEPTED'} else
                    'CONFIRMED_OBSERVATION_ACTIVE')
            except (ValueError, KeyError, OSError, SavedMapError) as exc:
                reason = str(exc).strip("' ")
                receipt = record['observation'].handoff_receipt(handoff_id)
                state = ('EXPIRED' if reason == 'HANDOFF_EXPIRED' else
                         'OUTCOME_UNKNOWN' if reason in {'HANDOFF_STOP_OUTCOME_UNKNOWN', 'HANDOFF_JOB_CONTEXT_UNCONFIRMED',
                            'HANDOFF_JOB_STARTING', 'HANDOFF_JOB_STOPPING', 'HANDOFF_MONITOR_PENDING',
                            'HANDOFF_MATCH_CURRENT_UNCONFIRMED'} else 'INVALID')
            return {'schema': 'robot-scope.proposal-geometry-handoff.v1', 'handoff_id': handoff_id,
                'proposal_id': record['proposal_id'], 'state': state, 'reason': reason,
                'source': 'proposal_confirmed', 'frame': 'map', 'bundle_generation': record['generation'],
                'observation_session_id': record['session_id'], 'job_id': record['job_id'],
                'expires_in_s': max(0., proof['expires_monotonic_s']-time.monotonic()),
                'policy': {'id': POLICY_ID, 'ttl_s': TTL_S, 'max_xy_m': MAX_XY_M, 'max_yaw_rad': MAX_YAW_RAD},
                'continuity': 'SUPERVISED_GAP_UNMEASURED', 'stop_receipt': {'state': receipt['state']},
                'match_history': copy.deepcopy(record['match_binding']),
                'geometry': ({k: geometry[k] for k in ('z','roll','pitch')} if reason is None else None),
                'initial_pose_reference': (copy.deepcopy(proof['reference']) if reason is None else None), 'operational_application': 'NOT_RUN'}

    def _check_proposal_geometry(self, geometry):
        if geometry.get('source') != 'proposal_confirmed':
            return
        record = self._handoffs.get(geometry.get('handoff', {}).get('handoff_id'))
        if not record:
            raise ValueError('HANDOFF_RUNTIME_CHANGED')
        self._handoff_gate(record)
        if record['snapshotted']:
            raise ValueError('HANDOFF_ALREADY_USED')

    def check_initial_pose(self, map_id, revision, pose):
        with self.lock:
            binding = self.snapshot_binding
            geometry = (self.selected or {}).get('seed_geometry') or {}
            if geometry.get('source') != 'proposal_confirmed':
                return
            if not binding or (binding['map_id'], binding['map_revision']) != (map_id, revision):
                raise ValueError('HANDOFF_RUNTIME_CHANGED')
            self._revalidate_pair(self.selected, references=self._selected_records)
            validate_candidate(geometry, pose['x'], pose['y'], pose['yaw'], self.selected)

    def _match_health_binding(self, sample, record, *, expected_stamp=None):
        if not isinstance(sample, RuntimeHealthSample):
            raise ValueError('HANDOFF_MATCH_CURRENT_UNCONFIRMED')
        health = sample.snapshot()
        if not isinstance(health, dict) or health.get('fresh') is not True:
            raise ValueError('HANDOFF_MATCH_CURRENT_UNCONFIRMED')
        age = sample.age_s()
        if age is None or age > .75:
            raise ValueError('HANDOFF_MATCH_CURRENT_UNCONFIRMED')
        source = health.get('operational_3d') or {}
        instance = source.get('runtime_instance_generation')
        generation = source.get('localization_generation')
        old = record.get('match_binding')
        if old and ((instance is not None and instance != old['runtime_instance_generation'])
                    or (generation is not None and generation != old['localization_generation'])):
            raise ValueError('HANDOFF_RUNTIME_CHANGED')
        try:
            pid, started = (int(part) for part in instance.split(':'))
        except (AttributeError, TypeError, ValueError):
            raise ValueError('HANDOFF_MATCH_CURRENT_UNCONFIRMED') from None
        binding = self.snapshot_binding or {}
        bundle = self.selected or {}
        initial = source.get('accepted_initial_pose') or {}
        initial_receipt = source.get('initial_pose_receipt') or {}
        receipt = source.get('match_receipt') or {}
        stamp = initial.get('stamp_ns')
        if (health.get('runtime_instance_generation') != instance or health.get('process_generation') != pid
                or pid <= 0 or type(self._snapshot_binding_monotonic_ns) is not int
                or not self._snapshot_binding_monotonic_ns <= started <= time.monotonic_ns()
                or binding.get('job_id') != record['job_id']
                or source.get('source') != 'STORED_PCD_FASTLIO'
                or (source.get('bundle_generation'), source.get('map_id'), source.get('map_revision')) !=
                    (record['generation'], binding.get('map_id'), binding.get('map_revision'))
                or (source.get('localization_map_id'), source.get('localization_map_revision')) !=
                    (binding.get('localization_map_id'), binding.get('localization_map_revision'))
                or source.get('reference_sha256') != (bundle.get('localization_3d') or {}).get('sha256')
                or type(generation) is not int or generation < 1
                or source.get('match_armed') is not True or receipt.get('accepted') is not True
                or receipt.get('localization_generation') != generation
                or not isinstance(receipt.get('request_id'), str) or not receipt['request_id']
                or initial.get('accepted') is not True or initial.get('localization_generation') != generation
                or initial.get('runtime_instance_generation') != instance
                or initial.get('geometry_source') != 'proposal_confirmed'
                or initial_receipt.get('accepted') is not True
                or initial_receipt.get('stamp_ns') != stamp
                or initial_receipt.get('localization_generation') != generation
                or initial.get('bundle_generation') != record['generation']
                or (initial.get('map_id'), initial.get('map_revision')) != (binding.get('map_id'), binding.get('map_revision'))
                or not isinstance(stamp, str) or not stamp.isdigit()
                or (expected_stamp is not None and stamp != str(expected_stamp))):
            raise ValueError('HANDOFF_MATCH_CURRENT_UNCONFIRMED')
        return {'runtime_instance_generation': instance, 'localization_generation': generation,
                'initial_pose_stamp_ns': stamp, 'match_request_id': receipt['request_id']}

    def record_match_armed(self, generation, map_id, revision, receipt, health, *, expected_stamp=None, allow_replace=False):
        with self.lock:
            geometry = (self.selected or {}).get('seed_geometry') or {}
            if geometry.get('source') != 'proposal_confirmed':
                return
            binding = self.snapshot_binding or {}
            record = self._handoffs.get((geometry.get('handoff') or {}).get('handoff_id'))
            if (not record or receipt.get('accepted') is not True
                    or (binding.get('bundle_generation'), binding.get('map_id'), binding.get('map_revision'))
                        != (generation, map_id, revision)
                    or binding.get('job_id') != record.get('job_id')):
                raise ValueError('HANDOFF_RUNTIME_CHANGED')
            if not isinstance(health, RuntimeHealthSample):
                raise ValueError('HANDOFF_MATCH_CURRENT_UNCONFIRMED')
            if (health.snapshot().get('operational_3d') or {}).get('match_receipt') != receipt:
                raise ValueError('HANDOFF_MATCH_CURRENT_UNCONFIRMED')
            old = record['match_binding']
            if allow_replace:
                record['match_binding'] = None
            try:
                current = self._match_health_binding(health, record, expected_stamp=expected_stamp)
            except Exception:
                record['match_binding'] = old
                raise
            if old and not allow_replace and old != current:
                raise ValueError('HANDOFF_RUNTIME_CHANGED')
            record['match_binding'] = current

    def check_match(self, generation, map_id, revision):
        with self.lock:
            geometry = (self.selected or {}).get('seed_geometry') or {}
            if geometry.get('source') != 'proposal_confirmed':
                return
            binding = self.snapshot_binding or {}
            if (binding.get('bundle_generation'), binding.get('map_id'), binding.get('map_revision')) != (generation, map_id, revision):
                raise ValueError('HANDOFF_RUNTIME_CHANGED')
            self._revalidate_pair(self.selected, references=self._selected_records)
            validate_handoff(geometry, self.selected)

    def select_pair(self, body):
        return self._select(body, paired=True)

    def seed_geometry(self, body):
        with self.lock:
            self._idle()
            bundle = self.selected
            if not bundle or bundle.get('workflow') != 'staged_navigation_pair' or body.get('generation') != bundle['generation']:
                raise ValueError('MAP_PAIR_GENERATION_CHANGED')
            self._revalidate_pair(bundle)
            if set(body) != {'generation', 'z', 'roll', 'pitch'}:
                raise ValueError('INVALID_SEED_GEOMETRY')
            for key, limit in (('z', 1000), ('roll', math.pi), ('pitch', math.pi / 2)):
                value = body[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > limit:
                    raise ValueError('INVALID_SEED_GEOMETRY')
            candidate = copy.deepcopy(bundle)
            candidate['seed_geometry'] = {key: float(body[key]) for key in ('z', 'roll', 'pitch')}
            candidate['seed_geometry'].update(frame='map', source='operator',
                confirmed_at=time.time())
            self.selected = validate_bundle(candidate)
            return self._status_locked(pair_validated=True)

    def select(self, body):
        return self._select(body)

    def _select(self, body, *, paired=False):
        allowed = {'map_id', 'map_revision', 'navigation_map_id', 'navigation_map_revision', 'seed_pose', 'course_region'}
        if not isinstance(body, dict) or set(body) - allowed:
            raise ValueError('INVALID_SELECTION_FIELDS')
        with self.lock:
            self._idle()
            if not body:
                self.selected = None
                self._selected_records = None
                return self.status()
            with self.catalog.pinned_lookup() as admitted:
                source = self.catalog.pcd_edit_source(body['map_id'])
                if source['revision'] != body['map_revision']:
                    raise ValueError('LOCALIZATION_MAP_REVISION_CHANGED')
                nav = self.catalog.resolve_navigation_map(body['navigation_map_id'], body['navigation_map_revision'])
                nav_geometry = self.catalog._read_map_yaml(nav.yaml_path)
                calibration, calibration_sha = self._calibration()
                expected = {'localization_frame': source['frame_id'],
                            'controller_odom_topic': self.jobs.controller_odom_topic,
                            'navigation_profile': self.jobs.navigation_profile}
                if not paired:
                    expected.update(navigation_map_id=nav.map_id, navigation_map_revision=nav.revision)
                if any(calibration.get(k) != v for k, v in expected.items()):
                    raise ValueError('CALIBRATION_PROFILE_OR_MAP_MISMATCH')
                family = self._family(source, nav, geometry=nav_geometry) if paired else None
                source_metadata = self.catalog.metadata(body['map_id'])
                if source_metadata['revision'] != source['revision']:
                    raise ValueError('LOCALIZATION_MAP_REVISION_CHANGED')
                if paired:
                    # Reuse only the trusted body/TF/profile/quality calibration. Map-to-map
                    # binding comes from the exact conversion document, not the old map pin.
                    root = source_metadata.get('origin') or source
                    calibration['localization_root'] = {key: root[key] for key in ('map_id', 'revision', 'sha256', 'frame_id', 'units')}
                    calibration.update(navigation_map_id=nav.map_id, navigation_map_revision=nav.revision)
                    projection = family['frame_projection']
                    calibration['T_nav_map_from_localization_map'] = from_translation_rpy(
                        projection['translation'], projection['rotation_rpy']).tolist()
                    seed = None
                else:
                    pose = body['seed_pose']
                    seed = from_translation_rpy([pose[k] for k in ('x', 'y', 'z')],
                        [pose[k] for k in ('roll', 'pitch', 'yaw')]).tolist()
                bundle = {'schema': SCHEMA, 'generation': uuid.uuid4().hex,
                    'localization_3d': {'map_id': body['map_id'], 'revision': source['revision'],
                        'sha256': source['sha256'], 'frame': source['frame_id'], 'units': source['units'],
                        'lineage': source_metadata.get('origin'),
                        'source': source_metadata.get('source'),
                        'edit_history': source_metadata.get('edit_history', [])},
                    'navigation_2d': {'map_id': nav.map_id, 'revision': nav.revision, 'frame': nav.frame_id,
                        'resolution': nav_geometry['resolution'], 'origin': nav_geometry['origin'],
                        'metadata_revision': nav.revision,
                        'yaml_sha256': digest(nav.yaml_path), 'image_sha256': digest(nav.image_path)},
                    'calibration': calibration, 'policy': calibration['policy'], 'seed_T_map_imu': seed}
                if paired:
                    bundle.update(workflow='staged_navigation_pair', seed_geometry=None,
                        map_binding={'family': family, 'calibration_sha256': calibration_sha})
                    bundle['localization_3d']['name'] = source_metadata['name']
                    bundle['navigation_2d']['name'] = nav.name
                course = body.get('course_region')
                if course is not None:
                    from ..course_regions import course_values
                    bundle['course_region'] = course_values(course)
                    if (course['map_id'], course['map_revision'], course['map_frame']) != (body['map_id'], source['revision'], source['frame_id']):
                        raise ValueError('COURSE_REFERENCE_CHANGED')
                candidate = validate_bundle(bundle)
                references = tuple(admitted[item] for item in (body['map_id'], nav.map_id))
                self.selected = candidate
                self._selected_records = references
                return self._status_locked(pair_validated=paired)

    def preparation_snapshot(self):
        """Copy tentative context for capture; it is not map or calibration proof.

        The caller must revalidate through status() before returning any result.
        """
        with self.lock:
            bundle = copy.deepcopy(self.selected)
            if not bundle or bundle.get('workflow') != 'staged_navigation_pair':
                return {'selected': bundle, 'pair': None}
            return {'selected': bundle, 'pair': {
                'generation': bundle['generation'],
                'localization_3d': bundle['localization_3d'],
                'navigation_2d': bundle['navigation_2d'],
                'calibration_sha256': bundle['map_binding']['calibration_sha256'],
                'valid': None,
            }}

    def verify_preparation_calibration(self, generation, expected_sha, expected_imu_base):
        """Re-read the small calibration file immediately before candidate return."""
        with self.lock:
            if not self.selected or self.selected.get('generation') != generation:
                raise ValueError('MAP_PAIR_CHANGED')
            try:
                calibration, sha = self._calibration()
            except (ValueError, KeyError, OSError) as exc:
                raise ValueError('CALIBRATION_CHANGED') from exc
            if (sha != expected_sha or calibration['T_imu_base'] != expected_imu_base
                    or self.selected['calibration']['T_imu_base'] != expected_imu_base):
                raise ValueError('CALIBRATION_CHANGED')
            return True

    def preparation_execution(self):
        """Copy the current job binding and its pre-launch monotonic boundary."""
        with self.lock:
            pipeline = self.jobs.snapshot().get('pipeline') or {}
            binding = self.snapshot_binding
            if (pipeline.get('state') != 'running' or not binding
                    or pipeline.get('job_id') != binding.get('job_id')
                    or not self._snapshot_binding_monotonic_ns):
                return None
            return {**copy.deepcopy(binding), 'snapshot_monotonic_ns': self._snapshot_binding_monotonic_ns}

    def expected_source(self, job_id, map_id, revision):
        with self.lock:
            value = self.snapshot_binding
            if value and (value['job_id'], value['map_id'], value['map_revision']) == (job_id, map_id, revision):
                return copy.deepcopy(value)
            return None

    def preflight(self, map_id, revision):
        """Reject missing evidence before starting the shared sensor pipeline."""
        with self.lock:
            if self.selected is None:
                return
            bundle = self.selected
            if (bundle['navigation_2d']['map_id'], bundle['navigation_2d']['revision']) != (map_id, revision):
                raise ValueError('SELECTED_3D_BUNDLE_REQUIRES_ITS_PINNED_2D_MAP')
            if bundle.get('workflow') == 'staged_navigation_pair':
                self._revalidate_pair(bundle)
                geometry = bundle.get('seed_geometry')
                if geometry is None:
                    raise ValueError('INITIAL_HEIGHT_TILT_REQUIRED')
                if self.used_geometry == (bundle['generation'], geometry['confirmed_at']):
                    raise ValueError('INITIAL_GEOMETRY_RECONFIRM_REQUIRED')
                self._check_proposal_geometry(geometry)

    def snapshot_for_job(self, map_id, revision, destination, navigation_snapshot=None):
        with self.lock:
            if self.selected is None:
                return
            with self.catalog.pinned_lookup():
                bundle = copy.deepcopy(self.selected)
                if bundle.get('workflow') == 'staged_navigation_pair':
                    self._revalidate_pair(bundle)
                    if bundle.get('seed_geometry') is None:
                        raise ValueError('INITIAL_HEIGHT_TILT_REQUIRED')
                    if self.used_geometry == (bundle['generation'], bundle['seed_geometry']['confirmed_at']):
                        raise ValueError('INITIAL_GEOMETRY_RECONFIRM_REQUIRED')
                    self._check_proposal_geometry(self.selected['seed_geometry'])
                    bundle['seed_geometry'] = copy.deepcopy(self.selected['seed_geometry'])
                if (bundle['navigation_2d']['map_id'], bundle['navigation_2d']['revision']) != (map_id, revision):
                    raise ValueError('SELECTED_3D_BUNDLE_REQUIRES_ITS_PINNED_2D_MAP')
                source = self.catalog._pcd_edit_source_asset(bundle['localization_3d']['map_id'])
                if source.revision != bundle['localization_3d']['revision']:
                    raise ValueError('LOCALIZATION_REFERENCE_CHANGED')
                nav = self.catalog.resolve_navigation_map(map_id, revision)
                if (digest(nav.yaml_path) != bundle['navigation_2d']['yaml_sha256']
                        or digest(nav.image_path) != bundle['navigation_2d']['image_sha256']):
                    raise ValueError('NAVIGATION_MAP_GEOMETRY_CHANGED')
                if navigation_snapshot is not None:
                    import yaml
                    document = yaml.safe_load(navigation_snapshot.yaml_path.read_text())
                    original = yaml.safe_load(nav.yaml_path.read_text())
                    def geometry(value):
                        return {k: v for k, v in value.items() if k != 'image'}
                    if (navigation_snapshot.map_id != map_id or navigation_snapshot.revision != revision
                            or navigation_snapshot.frame_id != 'map'
                            or digest(navigation_snapshot.image_path) != bundle['navigation_2d']['image_sha256']
                            or document.get('image') != navigation_snapshot.image_path.name
                            or navigation_snapshot.image_path.parent != navigation_snapshot.yaml_path.parent
                            or navigation_snapshot.image_path.parent != Path(destination)
                            or document.get('resolution') != navigation_snapshot.resolution
                            or tuple(document.get('origin', ())) != tuple(navigation_snapshot.origin)
                            or geometry(document) != geometry(original)):
                        raise ValueError('NAVIGATION_JOB_SNAPSHOT_MISMATCH')
                    bundle['navigation_2d']['consumer_yaml_sha256'] = digest(navigation_snapshot.yaml_path)
                    bundle['navigation_2d']['resolution'] = navigation_snapshot.resolution
                    bundle['navigation_2d']['origin'] = list(navigation_snapshot.origin)
                destination = Path(destination)
                target = destination / 'localization-reference.pcd'
                # No overwrite, original file and all attributes survive unchanged.
                with source.path.open('rb') as reader, target.open('xb') as writer:
                    shutil.copyfileobj(reader, writer, 1024 * 1024)
                if digest(target) != bundle['localization_3d']['sha256']:
                    target.unlink()
                    raise ValueError('LOCALIZATION_REFERENCE_HASH_CHANGED')
                if bundle.get('workflow') == 'staged_navigation_pair':
                    self._check_proposal_geometry(self.selected['seed_geometry'])
                    bundle['seed_geometry'] = copy.deepcopy(self.selected['seed_geometry'])
                output = destination / 'operational-3d.json'
                if (bundle.get('seed_geometry') or {}).get('source') == 'proposal_confirmed':
                    bundle['seed_geometry']['handoff']['job_id'] = destination.name
                with output.open('x') as stream:
                    json.dump(bundle, stream, allow_nan=False, sort_keys=True)
                try:
                    if bundle.get('workflow') == 'staged_navigation_pair':
                        self._revalidate_pair(self.selected, references=self._selected_records)
                        self._check_proposal_geometry(self.selected['seed_geometry'])
                except Exception:
                    output.unlink(missing_ok=True)
                    target.unlink(missing_ok=True)
                    raise
                self._snapshot_binding_monotonic_ns = time.monotonic_ns()
                self.snapshot_binding = {'job_id': destination.name, 'source': 'STORED_PCD_FASTLIO',
                    'bundle_generation': bundle['generation'], 'map_id': map_id, 'map_revision': revision,
                    'localization_map_id': bundle['localization_3d']['map_id'],
                    'localization_map_revision': bundle['localization_3d']['revision']}
                if bundle.get('workflow') == 'staged_navigation_pair':
                    self.used_geometry = (bundle['generation'], bundle['seed_geometry']['confirmed_at'])
                    if bundle['seed_geometry'].get('source') == 'proposal_confirmed':
                        record = self._handoffs[bundle['seed_geometry']['handoff']['handoff_id']]
                        record.update(snapshotted=True, job_id=destination.name)
                        self.selected['seed_geometry']['handoff']['job_id'] = destination.name
