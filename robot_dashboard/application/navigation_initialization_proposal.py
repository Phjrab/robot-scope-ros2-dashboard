"""Information-only bootstrap hypotheses from the existing global observation owner.

No pose, TF, navigation, control or service commands are issued by this owner.
Admission and reads are serialized by the caller's pipeline coordination lock.
"""
from __future__ import annotations

import copy
import math
import secrets
import threading
import time

from .anchor_proposal import source_contract
from .ownership_readback import ownership_readback
from .navigation_preparation_inputs import _source_identity
from ..observation_service import inputs_ready
from ..relocalization.experimental_se3 import _rpy, from_translation_rpy, validate_transform
from ..relocalization.global_observation_jobs import (
    GlobalObservationBusy, GlobalObservationConflict, GlobalObservationNotFound, GlobalObservationUnavailable,
)
from ..relocalization.observation_alignment import ObservationAlignmentError, paired_pose, project_query


SCHEMA = 'robot-scope.navigation-initialization-proposal.v1'


class ProposalConflict(RuntimeError):
    pass


class ProposalUnavailable(RuntimeError):
    pass


class ProposalNotFound(RuntimeError):
    pass


class NavigationInitializationProposals:
    def __init__(self, runtime):
        self.runtime = runtime
        self._lock = threading.RLock()
        self._records = {}
        self._requests = {}

    def _selected(self, generation):
        manager = self.runtime.operational_navigation
        if manager is None:
            raise ProposalUnavailable('MAP_PAIR_REQUIRED')
        state = manager.status()
        pair, selected = state.get('pair'), state.get('selected')
        if not pair or not selected:
            raise ProposalConflict('MAP_PAIR_REQUIRED')
        if pair.get('valid') is not True or pair.get('generation') != generation:
            raise ProposalConflict('MAP_PAIR_CHANGED')
        return state

    def _session(self, identifier):
        owner = self.runtime.fastlio_observation
        if owner is None:
            raise ProposalUnavailable('OBSERVATION_INPUTS_UNAVAILABLE')
        state = owner.snapshot()
        if (state.get('session_id') != identifier or state.get('state') != 'READY'
                or state.get('active') is not True or state.get('observation_only') is not True
                or state.get('map_registration_applied') is not False):
            raise ProposalConflict('OBSERVATION_SESSION_CHANGED')
        return state

    def _ownership(self, *, own_job=None):
        try:
            owners = ownership_readback(self.runtime)
            allowed = {'fastlio_observation'}
            if own_job:
                active = (owners.get('components', {}).get('global_observation') or {}).get('active_id')
                if active == own_job:
                    allowed.add('global_observation')
            busy = [x for x in owners['busy_components'] if x not in allowed]
            unknown = list(owners['unknown_components'])
            bridge = self.runtime.lifecycle.control_bridge_lifecycle._read_systemd()
            if bridge.get('available') is not True or bridge.get('active_state') != 'inactive':
                raise ProposalConflict('CONTROL_BRIDGE_NOT_INACTIVE')
            if busy or unknown:
                raise ProposalConflict('OWNERSHIP_BUSY_OR_UNKNOWN')
        except ProposalConflict:
            raise
        except Exception as exc:
            raise ProposalUnavailable('OWNERSHIP_READBACK_UNAVAILABLE') from exc

    def _source(self, session, expected_identity=None):
        agent = self.runtime.agent
        if agent is None:
            raise ProposalUnavailable('OBSERVATION_INPUTS_UNAVAILABLE')
        try:
            cloud, latest = agent.pointcloud_binary_snapshot(), agent.pose_snapshot()
            identity = (_source_identity(cloud), _source_identity(latest))
            if expected_identity is not None and identity != expected_identity:
                raise ProposalConflict('SOURCE_OR_CONTEXT_CHANGED')
            now = time.monotonic()
            if not inputs_ready(latest, cloud, session['started_monotonic_s'], now=now):
                raise ProposalConflict('OBSERVATION_INPUTS_UNAVAILABLE')
            mode = 'subscription_observation'
            contract = source_contract(cloud, latest, mode, now)
            pose = paired_pose(agent, cloud, contract, now + .15)
            if pose is None:
                raise ProposalConflict('EXACT_STAMP_PAIR_UNAVAILABLE')
            now = time.monotonic()
            if not inputs_ready(pose, cloud, session['started_monotonic_s'], now=now):
                raise ProposalConflict('OBSERVATION_INPUTS_UNAVAILABLE')
            if source_contract(cloud, pose, mode, now) != contract:
                raise ProposalConflict('SOURCE_OR_CONTEXT_CHANGED')
            project_query(cloud, pose, now, provenance_mode=mode)
            stamps = (int(cloud['observation']['source_stamp_ns']), int(latest['observation']['source_stamp_ns']))
            return contract, identity, stamps
        except ProposalConflict:
            raise
        except (ObservationAlignmentError, KeyError, TypeError, ValueError, OSError) as exc:
            raise ProposalConflict('OBSERVATION_INPUTS_UNAVAILABLE') from exc

    @staticmethod
    def _pair(state):
        pair = state['pair']
        return {key: copy.deepcopy(pair[key]) for key in (
            'generation', 'localization_3d', 'navigation_2d', 'calibration_sha256')}

    @staticmethod
    def _session_binding(session):
        return {key: session.get(key) for key in ('session_id', 'started_monotonic_s')}

    @staticmethod
    def _empty(record, state, reason=None):
        with record['gate_lock']:
            cleanup = copy.deepcopy(record['cleanup'])
        return {'schema': SCHEMA, 'proposal_id': record['job_id'], 'state': state, 'reason': reason,
                'pair': copy.deepcopy(record['pair']), 'observation_session_id': record['session']['session_id'],
                'imu_hypothesis': None, 'body_candidate': None, 'quality': None, 'provenance': None,
                'absolute_accuracy_m': None, 'operational_application': 'NOT_RUN', 'cleanup': cleanup}

    def _watch(self, record):
        """Invalidate and cancel only our exact global job if its context ends.

        This runs independently of HTTP polling; GET remains a read operation.
        Cancellation is attempted once and the global owner retains its normal
        worker cleanup/timeout handling. A pending cleanup is never reported as
        completed merely because cancellation was requested.
        """
        owner = record['owner']
        deadline = time.monotonic() + owner._capture_timeout_s + owner._timeout_s + 5.
        previous_stamps = record['initial_stamps']
        cancel_at = None
        while time.monotonic() < deadline:
            try:
                job = owner.job(record['job_id'])
            except GlobalObservationNotFound:
                with record['gate_lock']:
                    record['cleanup']['state'] = 'JOB_UNAVAILABLE'
                return
            if not job.get('worker_active'):
                with record['gate_lock']:
                    record['cleanup'].update(state='SETTLED', worker_active=False,
                                             terminal_state=job.get('state'))
                return
            with record['gate_lock']:
                reason = record.get('invalidated_reason')
            if reason is None:
                try:
                    if self.runtime.global_observation is not owner:
                        raise ProposalConflict('SOURCE_OR_CONTEXT_CHANGED')
                    session = self._session(record['session']['session_id'])
                    if self._session_binding(session) != record['session']:
                        raise ProposalConflict('OBSERVATION_SESSION_CHANGED')
                    manager = self.runtime.operational_navigation
                    # Never wait behind slow map hashing before checking source/stop.
                    if manager.lock.acquire(blocking=False):
                        try:
                            current = manager.preparation_snapshot()
                        finally:
                            manager.lock.release()
                        if (not current.get('pair') or self._pair(current) != record['pair']
                                or current['selected']['calibration']['T_imu_base'] != record['T_imu_base']):
                            raise ProposalConflict('MAP_PAIR_CHANGED')
                    cloud, pose = self.runtime.agent.pointcloud_binary_snapshot(), self.runtime.agent.pose_snapshot()
                    identity = (_source_identity(cloud), _source_identity(pose))
                    stamps = (int(cloud['observation']['source_stamp_ns']),
                              int(pose['observation']['source_stamp_ns']))
                    if identity != record['source_identity'] or any(a < b for a, b in zip(stamps, previous_stamps)):
                        raise ProposalConflict('SOURCE_OR_CONTEXT_CHANGED')
                    previous_stamps = stamps
                except (ProposalConflict, ProposalUnavailable, AttributeError, KeyError, TypeError, ValueError, OSError) as exc:
                    reason = str(exc) if str(exc) in {'OBSERVATION_SESSION_CHANGED', 'MAP_PAIR_CHANGED'} else 'SOURCE_OR_CONTEXT_CHANGED'
                    with record['gate_lock']:
                        record.setdefault('invalidated_reason', reason)
            if reason is not None and cancel_at is None:
                cancel_at = time.monotonic()
                try:
                    cancelled = owner.cancel(record['job_id'])
                    with record['gate_lock']:
                        record['cleanup'].update(state='CANCELLING',
                            cancellation_requested=cancelled.get('cancellation_requested') is True,
                            worker_active=cancelled.get('worker_active') is True)
                except Exception:
                    with record['gate_lock']:
                        record['cleanup'].update(state='CANCEL_FAILED', cancellation_requested=False)
            elif cancel_at is not None and time.monotonic() - cancel_at > 3.:
                with record['gate_lock']:
                    if record['cleanup'].get('state') != 'CANCEL_FAILED':
                        record['cleanup'].update(state='CANCEL_PENDING', worker_active=True)
            threading.Event().wait(.2)
        with record['gate_lock']:
            record['cleanup']['state'] = 'CLEANUP_UNCONFIRMED'

    def start(self, request_id, generation, session_id):
        """Admission must be called under the shared pipeline lock."""
        with self._lock:
            prior = self._requests.get(request_id)
            if prior:
                record = self._records[prior]
                if (record['pair']['generation'], record['session']['session_id']) != (generation, session_id):
                    raise ProposalConflict('REQUEST_ID_CONTEXT_CHANGED')
                return self.get(prior)
            if len(self._records) >= 32:
                oldest_id = next(iter(self._records))
                oldest = self._records[oldest_id]
                try:
                    old_job = self.runtime.global_observation.job(oldest_id)
                except GlobalObservationNotFound:
                    old_job = None
                if old_job and (old_job.get('worker_active') or old_job.get('state') not in
                                {'succeeded', 'failed', 'stale', 'timed_out', 'cancelled'}):
                    raise ProposalConflict('PROPOSAL_HISTORY_FULL')
                self._records.pop(oldest_id)
                self._requests.pop(oldest['request_id'], None)
            state, session = self._selected(generation), self._session(session_id)
            self._ownership()
            contract, identity, stamps = self._source(session)
            pair = self._pair(state)
            transform = validate_transform(state['selected']['calibration']['T_imu_base']).tolist()
            # Slow asset and source reads are not atomic; fence the session and selection again.
            after = self._selected(generation)
            if (self._pair(after) != pair or after['selected']['calibration']['T_imu_base'] != transform
                    or self._session_binding(self._session(session_id)) != self._session_binding(session)
                    or self._source(session, identity)[0] != contract):
                raise ProposalConflict('MAP_OR_SESSION_CHANGED')
            self._ownership()
            owner = self.runtime.global_observation
            if owner is None or not owner.provider_status().get('available'):
                raise ProposalUnavailable('GLOBAL_BACKEND_UNAVAILABLE')
            try:
                # The client request ID is not the shared global owner's ID.
                # Reserve a fresh server-generated ID under its existing RLock,
                # so another feature's idempotent job can never become ours.
                with owner._lock:
                    global_request_id = 'navigation-proposal-' + secrets.token_hex(16)
                    if global_request_id in owner._requests:
                        raise ProposalConflict('GLOBAL_REQUEST_ID_COLLISION')
                    job = owner.start(global_request_id, pair['localization_3d']['map_id'],
                                      pair['localization_3d']['revision'], input_kind='fastlio_imu',
                                      provenance_mode='subscription_observation', search_mode='global')
            except GlobalObservationUnavailable as exc:
                raise ProposalUnavailable(str(exc)) from exc
            except (GlobalObservationBusy, GlobalObservationConflict, ValueError) as exc:
                raise ProposalConflict(str(exc)) from exc
            record = {'job_id': job['job_id'], 'request_id': request_id, 'owner': owner,
                      'pair': pair, 'session': self._session_binding(session),
                      'source_contract': contract, 'source_identity': identity, 'initial_stamps': stamps,
                      'T_imu_base': transform,
                      'cleanup': {'state': 'MONITORING', 'cancellation_requested': False},
                      'gate_lock': threading.Lock()}
            self._records[job['job_id']] = record
            self._requests[request_id] = job['job_id']
            watcher = threading.Thread(target=self._watch, args=(record,), daemon=True,
                                       name='navigation-proposal-watch-' + job['job_id'])
            try:
                watcher.start()
            except RuntimeError as exc:
                with record['gate_lock']:
                    record['invalidated_reason'] = 'PROPOSAL_MONITOR_UNAVAILABLE'
                    record['cleanup'] = {'state': 'CANCELLING', 'cancellation_requested': True}
                try:
                    owner.cancel(job['job_id'])
                except Exception:
                    with record['gate_lock']:
                        record['cleanup'] = {'state': 'CANCEL_FAILED', 'cancellation_requested': False}
                raise ProposalUnavailable('PROPOSAL_MONITOR_UNAVAILABLE') from exc
            return self._empty(record, job['state'], job.get('reason'))

    def get(self, proposal_id):
        """Read result; detected invalidation can trigger asynchronous owned-job cleanup."""
        with self._lock:
            record = self._records.get(proposal_id)
            if record is None:
                raise ProposalNotFound('PROPOSAL_NOT_FOUND')
            with record['gate_lock']:
                invalidated = record.get('invalidated_reason')
            if invalidated:
                return self._empty(record, 'stale', invalidated)
            owner = record['owner']
            if self.runtime.global_observation is not owner:
                return self._empty(record, 'stale', 'SOURCE_OR_CONTEXT_CHANGED')
            try:
                job = owner.job(proposal_id)
            except GlobalObservationNotFound as exc:
                raise ProposalNotFound('PROPOSAL_NOT_FOUND') from exc
            if job['state'] in {'cancelled', 'failed', 'stale', 'timed_out'}:
                return self._empty(record, job['state'], job.get('reason'))
            try:
                state = self._selected(record['pair']['generation'])
                session = self._session(record['session']['session_id'])
                self._ownership(own_job=proposal_id)
                if (self._pair(state) != record['pair']
                        or state['selected']['calibration']['T_imu_base'] != record['T_imu_base']
                        or self._session_binding(session) != record['session']
                        or self._source(session, record['source_identity'])[0] != record['source_contract']):
                    raise ProposalConflict('SOURCE_OR_CONTEXT_CHANGED')
                if job['state'] != 'succeeded' or job.get('worker_active'):
                    return self._empty(record, 'running' if job['state'] == 'succeeded' else job['state'])
                context = job['captured_context']
                scan = context['scan']
                captured = context['anchor_capture']
                provenance = captured['provenance']
                pin = record['pair']['localization_3d']
                if ((job.get('map_id'), job.get('map_revision'), context.get('map_id'), context.get('map_revision'), context.get('map_frame'))
                        != (pin['map_id'], pin['revision'], pin['map_id'], pin['revision'], pin['frame'])
                        or captured['contract'] != record['source_contract']
                        or provenance.get('pair_method') != 'FASTLIO_OUTPUT_STAMP_EXACT'
                        or provenance.get('source_delta_ns') != '0'
                        or provenance.get('source_stamp_ns') != context['source_stamp_ns']
                        or provenance.get('pose_source_stamp_ns') != context['source_stamp_ns']
                        or scan['received_monotonic_s'] < record['session']['started_monotonic_s']
                        or provenance['pose_received_monotonic_s'] < record['session']['started_monotonic_s']
                        or context['map']['source_sha256'] != record['pair']['localization_3d']['sha256']):
                    raise ProposalConflict('SOURCE_OR_CONTEXT_CHANGED')
                observation = job['result']['observation']
                if ((observation.get('ambiguity_override') or {}).get('applied') is True
                        or observation.get('estimate_label') == 'AMBIGUOUS_UNVERIFIED_ESTIMATE'
                        or 'AMBIGUOUS_ALTERNATIVES' in (observation.get('gate_reasons') or [])):
                    return self._empty(record, 'rejected', 'GLOBAL_AMBIGUOUS')
                if observation.get('selected_candidate') is None:
                    return self._empty(record, 'rejected', 'GLOBAL_CANDIDATE_REJECTED')
                proposal = owner.anchor_proposal(proposal_id)
                proposal_read_at = time.monotonic()
                if proposal.get('ambiguity_unresolved') is not False:
                    return self._empty(record, 'rejected', 'GLOBAL_AMBIGUOUS')
                imu = proposal['pose']
                if (proposal.get('pose_reference') != 'FASTLIO_IMU' or proposal.get('units') != 'metres_degrees'
                        or proposal.get('map') != {'id': pin['map_id'], 'revision': pin['revision'], 'frame': pin['frame']}):
                    raise ProposalConflict('GLOBAL_CANDIDATE_REJECTED')
                matrix = from_translation_rpy([imu[k] for k in ('x', 'y', 'z')],
                    [math.radians(imu[k]) for k in ('roll', 'pitch', 'yaw')]) @ validate_transform(record['T_imu_base'])
                roll, pitch, yaw = _rpy(matrix[:3, :3])
                body = dict(zip(('x', 'y', 'z', 'roll', 'pitch', 'yaw'),
                                [*map(float, matrix[:3, 3]), *map(float, (roll, pitch, yaw))]))
                # A cheap in-memory fence follows this request's full asset validation.
                # Rehashing a second time after pose capture can consume its entire
                # freshness window; no validation result is cached across requests.
                latest = getattr(self.runtime.operational_navigation, 'preparation_snapshot',
                                 self.runtime.operational_navigation.status)()
                if (not latest.get('pair') or self._pair(latest) != record['pair']
                        or latest['selected']['calibration']['T_imu_base'] != record['T_imu_base']
                        or self._session_binding(self._session(record['session']['session_id'])) != record['session']
                        or self._source(session, record['source_identity'])[0] != record['source_contract']
                        or self._session_binding(self._session(record['session']['session_id'])) != record['session']):
                    raise ProposalConflict('SOURCE_OR_CONTEXT_CHANGED')
                self.runtime.operational_navigation.verify_preparation_calibration(
                    record['pair']['generation'], record['pair']['calibration_sha256'], record['T_imu_base'])
                pose_age = proposal['pose_age_s'] + time.monotonic() - proposal_read_at
                if not math.isfinite(pose_age) or not 0 <= pose_age <= 1.:
                    raise ProposalConflict('OBSERVATION_INPUTS_UNAVAILABLE')
                with record['gate_lock']:
                    invalidated = record.get('invalidated_reason')
                if invalidated:
                    return self._empty(record, 'stale', invalidated)
                result = self._empty(record, 'ready')
                result.update(imu_hypothesis={'frame': proposal['map']['frame'], 'pose_reference': 'FASTLIO_IMU',
                    'units': 'metres_degrees', 'pose': imu, 'approximate_only': True, 'requires_reanchor': True},
                    body_candidate={'frame': proposal['map']['frame'], 'pose_reference': 'base_link',
                    'units': 'metres_radians', 'pose': body, 'qualification': 'INFORMATIONAL_LOCALIZATION_MAP_ONLY'},
                    quality={'overlap': proposal['overlap'], 'rmse_m': proposal['rmse_m'],
                    'hypothesis_overlap_min': .6, 'operational_initial_overlap_min': .85,
                    'residual_selection_gate_enabled': False,
                    'qualification': 'GLOBAL_HYPOTHESIS_ONLY_NOT_OPERATIONAL_QUALITY',
                    'ambiguity_unresolved': False},
                    provenance={'source_contract': copy.deepcopy(record['source_contract']),
                    'capture_stamp_ns': proposal['capture_stamp_ns'], 'proposal_stamp_ns': proposal['proposal_stamp_ns'],
                    'pose_age_s': pose_age, 'capture_age_s': max(0., time.monotonic() - scan['received_monotonic_s']),
                    'receipt_clock': 'OBSERVER_HOST_MONOTONIC', 'source_clock_verified': False,
                    'per_message_publisher_verified': False, 'deskew_verified': False,
                    'calibration_sha256': record['pair']['calibration_sha256'],
                    'observation_session_id': record['session']['session_id'],
                    'bundle_generation': record['pair']['generation']})
                return result
            except (ProposalConflict, ProposalUnavailable, GlobalObservationConflict, ObservationAlignmentError,
                    KeyError, TypeError, ValueError, OSError) as exc:
                reason = str(exc) or 'SOURCE_OR_CONTEXT_CHANGED'
                if reason in {'MAP_PAIR_REQUIRED', 'MAP_PAIR_CHANGED', 'OBSERVATION_SESSION_CHANGED',
                              'SOURCE_OR_CONTEXT_CHANGED', 'CALIBRATION_CHANGED'}:
                    with record['gate_lock']:
                        record['invalidated_reason'] = reason
                return self._empty(record, 'stale', reason)
