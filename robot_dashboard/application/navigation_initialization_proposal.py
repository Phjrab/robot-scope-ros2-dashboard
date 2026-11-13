"""Information-only bootstrap hypotheses from the existing global observation owner.

No pose, TF, navigation, control or service commands are issued by this owner.
Admission and reads are serialized by the caller's pipeline coordination lock.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import secrets
import threading
import time

from .anchor_proposal import source_contract, imu_matrix, current_imu
from .ownership_readback import ownership_readback
from .observation_bridge import bridge_observation_error
from .navigation_preparation_inputs import _source_identity
from .operational_navigation import _navigation_map_body_pose
from .planar_prior_selection import select_candidates, validate_prior, PriorRejected
from ..observation_service import inputs_ready
from ..relocalization.experimental_se3 import _rpy, from_translation_rpy, validate_transform, inverse
from ..relocalization.handoff_policy import MAX_XY_M, MAX_YAW_RAD, resolution_bounds
from ..relocalization.external_global_observation import ExternalGlobalObservationError
from ..relocalization.operational import display_pose
from ..relocalization.v031_observation_compat import supports_pin
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
            bridge_error = bridge_observation_error(self.runtime)
            if bridge_error:
                raise ProposalConflict(bridge_error)
            if busy or unknown:
                raise ProposalConflict('OWNERSHIP_BUSY_OR_UNKNOWN')
        except ProposalConflict:
            raise
        except Exception as exc:
            raise ProposalUnavailable('OWNERSHIP_READBACK_UNAVAILABLE') from exc

    def _source(self, session, expected_identity=None, *, capture_anchor=False):
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
            if capture_anchor:
                return contract, identity, stamps, {'T_odom_imu': imu_matrix(pose).tolist(),
                    'stamp_ns': pose['observation']['source_stamp_ns'],
                    'received_monotonic_s': pose['observation']['received_monotonic_s']}
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
    def _empty(record, state, reason=None, *, prior_rejection_diagnostics=None):
        with record['gate_lock']:
            cleanup = copy.deepcopy(record['cleanup'])
        return {'schema': SCHEMA, 'proposal_id': record['job_id'], 'state': state, 'reason': reason,
                'pair': copy.deepcopy(record['pair']), 'observation_session_id': record['session']['session_id'],
                'imu_hypothesis': None, 'body_candidate': None, 'navigation_geometry_candidate': None,
                'quality': None, 'provenance': None,
                'absolute_accuracy_m': None, 'operational_application': 'NOT_RUN', 'cleanup': cleanup,
                **({'prior_rejection_diagnostics': copy.deepcopy(prior_rejection_diagnostics)}
                   if state == 'rejected' and prior_rejection_diagnostics is not None else {})}

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
                    # The session snapshot consumes the sticky in-memory bridge/
                    # control guard. Full owner sampling runs on its coordinated
                    # async monitor; a worker thread must not bypass that lock.
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
                                or current['selected']['calibration']['T_imu_base'] != record['T_imu_base']
                                or current['selected']['calibration']['T_nav_map_from_localization_map'] != record['T_nav_map_from_localization_map']):
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

    def start(self, request_id, generation, session_id, *, operator_prior=None):
        """Admission must be called under the shared pipeline lock."""
        with self._lock:
            if operator_prior is not None:
                try:
                    operator_prior = validate_prior(operator_prior)
                except PriorRejected as exc:
                    raise ProposalConflict(str(exc)) from exc
            prior = self._requests.get(request_id)
            if prior:
                record = self._records[prior]
                if ((record['pair']['generation'], record['session']['session_id']) != (generation, session_id)
                        or record.get('operator_prior') != operator_prior):
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
            nav_transform = validate_transform(state['selected']['calibration']['T_nav_map_from_localization_map']).tolist()
            # Slow asset and source reads are not atomic; fence the session and selection again.
            after = self._selected(generation)
            if (self._pair(after) != pair or after['selected']['calibration']['T_imu_base'] != transform
                    or after['selected']['calibration']['T_nav_map_from_localization_map'] != nav_transform
                    or self._session_binding(self._session(session_id)) != self._session_binding(session)
                    or self._source(session, identity)[0] != contract):
                raise ProposalConflict('MAP_OR_SESSION_CHANGED')
            prior_anchor = None
            if operator_prior is not None:
                if ((operator_prior['navigation_map_id'], operator_prior['navigation_map_revision'],
                        operator_prior['calibration_sha256']) !=
                        (pair['navigation_2d']['map_id'], pair['navigation_2d']['revision'], pair['calibration_sha256'])):
                    raise ProposalConflict('MAP_PAIR_CHANGED')
                anchor_contract, anchor_identity, anchor_stamps, prior_anchor = self._source(session, identity, capture_anchor=True)
                if anchor_contract != contract or anchor_identity != identity or any(a < b for a, b in zip(anchor_stamps, stamps)):
                    raise ProposalConflict('SOURCE_OR_CONTEXT_CHANGED')
                prior_anchor['accepted_monotonic_s'] = time.monotonic()
                prior_anchor['expires_monotonic_s'] = prior_anchor['accepted_monotonic_s'] + 120.
                prior_anchor['prior_id'] = secrets.token_hex(16)
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
                    start_options = dict(input_kind='fastlio_imu', provenance_mode='subscription_observation', search_mode='global')
                    if operator_prior is not None:
                        start_options['retained_candidates'] = True
                    job = owner.start(global_request_id, pair['localization_3d']['map_id'],
                                      pair['localization_3d']['revision'], **start_options)
            except GlobalObservationUnavailable as exc:
                raise ProposalUnavailable(str(exc)) from exc
            except (GlobalObservationBusy, GlobalObservationConflict, ValueError) as exc:
                raise ProposalConflict(str(exc)) from exc
            record = {'job_id': job['job_id'], 'request_id': request_id, 'owner': owner,
                      'pair': pair, 'session': self._session_binding(session),
                      'source_contract': contract, 'source_identity': identity, 'initial_stamps': stamps,
                      'T_imu_base': transform, 'T_nav_map_from_localization_map': nav_transform,
                      'operator_prior': copy.deepcopy(operator_prior), 'prior_anchor': copy.deepcopy(prior_anchor),
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

    def validate_conditional_confirmation(self, proposal_id, expected_resolution):
        """Recompute from the owner record, never trust a client-provided proof."""
        with self._lock:
            current = self.get(proposal_id)
            if (current.get('state') != 'ready'
                    or current.get('classification') != 'CONDITIONAL_ON_OPERATOR_PRIOR'
                    or current.get('operator_prior_resolution') != expected_resolution):
                raise ProposalConflict('OPERATOR_PRIOR_PROOF_CHANGED')
            return current

    def owns_observation_job(self, job_id, session_id):
        with self._lock:
            record = self._records.get(job_id)
            return bool(record and record['session']['session_id'] == session_id
                        and record['owner'] is self.runtime.global_observation)

    def handoff_watch_context(self, proposal_id, session_id):
        """Revalidate and capture the real source identity for the handoff watcher."""
        with self._lock:
            record = self._records.get(proposal_id)
            if record is None:
                raise ProposalNotFound('PROPOSAL_NOT_FOUND')
            if self.runtime.global_observation is not record['owner']:
                raise ProposalConflict('SOURCE_OR_CONTEXT_CHANGED')
            session = self._session(session_id)
            if self._session_binding(session) != record['session']:
                raise ProposalConflict('OBSERVATION_SESSION_CHANGED')
            contract, identity, stamps = self._source(session, record['source_identity'])
            if contract != record['source_contract']:
                raise ProposalConflict('SOURCE_OR_CONTEXT_CHANGED')
            return {'identity': identity, 'stamps': stamps, 'session': self._session_binding(session)}

    def handoff_watch_sample(self):
        """In-memory observation snapshots only; never issue a control command."""
        agent = self.runtime.agent
        observation = self.runtime.fastlio_observation
        if agent is None or observation is None:
            raise ProposalUnavailable('HANDOFF_MONITOR_UNAVAILABLE')
        session = observation.snapshot()
        cloud, pose = agent.pointcloud_binary_snapshot(), agent.pose_snapshot()
        identity = (_source_identity(cloud), _source_identity(pose))
        stamps = (int(cloud['observation']['source_stamp_ns']), int(pose['observation']['source_stamp_ns']))
        return {'identity': identity, 'stamps': stamps, 'session': self._session_binding(session),
                'state': session.get('state'), 'active': session.get('active'),
                'sample_end_ns': time.monotonic_ns()}

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
                        or state['selected']['calibration']['T_nav_map_from_localization_map'] != record['T_nav_map_from_localization_map']
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
                ambiguous = ((observation.get('ambiguity_override') or {}).get('applied') is True
                        or observation.get('estimate_label') == 'AMBIGUOUS_UNVERIFIED_ESTIMATE'
                        or 'AMBIGUOUS_ALTERNATIVES' in (observation.get('gate_reasons') or []))
                resolution = None
                if record.get('operator_prior') is not None:
                    anchor = record['prior_anchor']
                    if not 0 < anchor['expires_monotonic_s'] - time.monotonic() <= 120.:
                        raise ProposalConflict('OPERATOR_PRIOR_EXPIRED')
                    if (job['result']['captured_context'] != context or job['result']['historical_only'] is not True
                            or int(context['source_stamp_ns']) < int(anchor['stamp_ns'])
                            or scan['received_monotonic_s'] < anchor['received_monotonic_s']):
                        raise ProposalConflict('SOURCE_OR_CONTEXT_CHANGED')
                    try:
                        _, _, source_pin, pin_sha = owner._runner._configuration()
                    except (AttributeError, KeyError, TypeError, ValueError, OSError, ExternalGlobalObservationError) as exc:
                        raise ProposalConflict('CANDIDATE_RETENTION_UNCONFIRMED') from exc
                    if (not supports_pin(source_pin['files']) or observation.get('execution', {}).get('source_pin_sha256') != pin_sha
                            or observation.get('execution', {}).get('worker_reaped') is not True):
                        raise ProposalConflict('CANDIDATE_RETENTION_UNCONFIRMED')
                    try:
                        resolution = select_candidates(observation, context, record['operator_prior'],
                            nav_from_localization=record['T_nav_map_from_localization_map'],
                            odom_from_imu_at_prior=anchor['T_odom_imu'], imu_from_base=record['T_imu_base'],
                            allow_ambiguous=owner.provider_status()['allow_ambiguous'])
                    except PriorRejected as exc:
                        return self._empty(record, 'rejected', str(exc),
                            prior_rejection_diagnostics=exc.diagnostics)
                    selected = observation['candidates'][resolution['candidate_index']]
                    _, current_pose, odom_now, now = current_imu(self.runtime.agent, context)
                    map_imu = validate_transform(selected['map_from_scan']) @ inverse(validate_transform(captured['T_odom_imu'])) @ odom_now
                    angles = [math.degrees(v) for v in _rpy(map_imu[:3, :3])]
                    proposal = {'pose': dict(zip(('x','y','z','roll','pitch','yaw'), [*map(float,map_imu[:3,3]), *angles])),
                        'pose_reference': 'FASTLIO_IMU', 'units': 'metres_degrees',
                        'map': {'id':pin['map_id'], 'revision':pin['revision'], 'frame':pin['frame']},
                        'capture_stamp_ns': context['source_stamp_ns'],
                        'proposal_stamp_ns': current_pose['observation']['source_stamp_ns'],
                        'pose_age_s': now-current_pose['observation']['received_monotonic_s'],
                        'ambiguity_unresolved': ambiguous, 'overlap': selected['overlap'], 'rmse_m': selected['rmse_m']}
                    proposal_read_at = time.monotonic()
                    resolution.update(schema='robot-scope.operator-prior-resolution.v1', prior_id=anchor['prior_id'],
                        operator_prior=copy.deepcopy(record['operator_prior']),
                        accepted_monotonic_s=anchor['accepted_monotonic_s'], expires_monotonic_s=anchor['expires_monotonic_s'],
                        prior_anchor_stamp_ns=anchor['stamp_ns'], bundle_generation=record['pair']['generation'],
                        localization_3d=copy.deepcopy(record['pair']['localization_3d']),
                        navigation_2d=copy.deepcopy(record['pair']['navigation_2d']),
                        observation_session_id=session['session_id'], calibration_sha256=record['pair']['calibration_sha256'],
                        source_contract_sha256=hashlib.sha256(json.dumps(record['source_contract'], sort_keys=True, allow_nan=False).encode()).hexdigest(),
                        original_observation_sha256=hashlib.sha256(json.dumps(observation,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()).hexdigest(),
                        projection_basis='NAV_LOCALIZATION_CAPTURE_TO_PRIOR_ODOM_IMU_BASE')
                elif ambiguous:
                    return self._empty(record, 'rejected', 'GLOBAL_AMBIGUOUS')
                else:
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
                # Finish both frame conversions before checking the original pose's
                # age and current source/map fences; conversion time is not fresh evidence.
                navigation_pose = _navigation_map_body_pose(state['selected']['calibration'], body)
                # A cheap in-memory fence follows this request's full asset validation.
                # Rehashing a second time after pose capture can consume its entire
                # freshness window; no validation result is cached across requests.
                latest = getattr(self.runtime.operational_navigation, 'preparation_snapshot',
                                 self.runtime.operational_navigation.status)()
                if (not latest.get('pair') or self._pair(latest) != record['pair']
                        or latest['selected']['calibration']['T_imu_base'] != record['T_imu_base']
                        or latest['selected']['calibration']['T_nav_map_from_localization_map'] != record['T_nav_map_from_localization_map']
                        or self._session_binding(self._session(record['session']['session_id'])) != record['session']
                        or self._source(session, record['source_identity'])[0] != record['source_contract']
                        or self._session_binding(self._session(record['session']['session_id'])) != record['session']):
                    raise ProposalConflict('SOURCE_OR_CONTEXT_CHANGED')
                self.runtime.operational_navigation.verify_preparation_calibration(
                    record['pair']['generation'], record['pair']['calibration_sha256'], record['T_imu_base'])
                self._ownership(own_job=proposal_id)
                pose_age = proposal['pose_age_s'] + time.monotonic() - proposal_read_at
                if not math.isfinite(pose_age) or not 0 <= pose_age <= 1.:
                    raise ProposalConflict('OBSERVATION_INPUTS_UNAVAILABLE')
                if resolution is not None and not 0 < resolution['expires_monotonic_s'] - time.monotonic() <= 120.:
                    raise ProposalConflict('OPERATOR_PRIOR_EXPIRED')
                with record['gate_lock']:
                    invalidated = record.get('invalidated_reason')
                if invalidated:
                    return self._empty(record, 'stale', invalidated)
                result = self._empty(record, 'ready')
                result.update(imu_hypothesis={'frame': proposal['map']['frame'], 'pose_reference': 'FASTLIO_IMU',
                    'units': 'metres_degrees', 'pose': imu, 'approximate_only': True, 'requires_reanchor': True},
                    body_candidate={'frame': proposal['map']['frame'], 'pose_reference': 'base_link',
                    'units': 'metres_radians', 'pose': body, 'qualification': 'INFORMATIONAL_LOCALIZATION_MAP_ONLY'},
                    navigation_geometry_candidate={'frame': 'map', 'pose_reference': 'base_link',
                    'units': 'metres_radians', 'pose': {k: navigation_pose[k] for k in ('z', 'roll', 'pitch')}},
                    quality={'overlap': proposal['overlap'], 'rmse_m': proposal['rmse_m'],
                    'hypothesis_overlap_min': .6, 'operational_initial_overlap_min': .85,
                    'residual_selection_gate_enabled': False,
                    'qualification': 'GLOBAL_HYPOTHESIS_ONLY_NOT_OPERATIONAL_QUALITY',
                    'ambiguity_unresolved': ambiguous if resolution is not None else False},
                    provenance={'source_contract': copy.deepcopy(record['source_contract']),
                    'capture_stamp_ns': proposal['capture_stamp_ns'], 'proposal_stamp_ns': proposal['proposal_stamp_ns'],
                    'pose_age_s': pose_age, 'capture_age_s': max(0., time.monotonic() - scan['received_monotonic_s']),
                    'receipt_clock': 'OBSERVER_HOST_MONOTONIC', 'source_clock_verified': False,
                    'per_message_publisher_verified': False, 'deskew_verified': False,
                    'calibration_sha256': record['pair']['calibration_sha256'],
                    'observation_session_id': record['session']['session_id'],
                    'bundle_generation': record['pair']['generation']})
                if resolution is not None:
                    result['operator_prior_resolution'] = resolution
                    result['classification'] = 'CONDITIONAL_ON_OPERATOR_PRIOR'
                    prior_pose = record['operator_prior']['pose']
                    prior_bounds = resolution_bounds(resolution)
                    dx, dy = navigation_pose['x'] - prior_pose['x'], navigation_pose['y'] - prior_pose['y']
                    yaw_delta = math.atan2(math.sin(navigation_pose['yaw'] - prior_pose['yaw']),
                                           math.cos(navigation_pose['yaw'] - prior_pose['yaw']))
                    distance = math.hypot(dx, dy)
                    result['current_vs_prior'] = {'xy_distance_m': distance, 'yaw_delta_rad': yaw_delta,
                        'within_prior_bounds': distance <= prior_bounds['xy_m'] and abs(yaw_delta) <= prior_bounds['yaw_rad'],
                        'within_existing_handoff_reference': distance <= MAX_XY_M and abs(yaw_delta) <= MAX_YAW_RAD,
                        'pose_stamp_ns': proposal['proposal_stamp_ns'], 'pose_age_s': pose_age}
                    checks = []
                    for member_index in resolution['matching_member_indices']:
                        member = observation['candidates'][member_index]
                        projected = display_pose(validate_transform(record['T_nav_map_from_localization_map'])
                            @ validate_transform(member['map_from_scan']) @ inverse(validate_transform(captured['T_odom_imu']))
                            @ odom_now @ validate_transform(record['T_imu_base']))
                        member_distance = math.hypot(projected['x']-prior_pose['x'], projected['y']-prior_pose['y'])
                        member_yaw = abs(math.atan2(math.sin(projected['yaw']-prior_pose['yaw']),
                                                    math.cos(projected['yaw']-prior_pose['yaw'])))
                        checks.append({'candidate_index':member_index, 'xy_distance_m':member_distance,
                                       'absolute_wrapped_yaw_rad':member_yaw,
                                       'within_prior_bounds':member_distance <= prior_bounds['xy_m'] and member_yaw <= prior_bounds['yaw_rad']})
                    result['current_vs_prior']['member_checks'] = checks
                    result['current_vs_prior']['all_members_within_prior_bounds'] = all(c['within_prior_bounds'] for c in checks)
                    # The member projections consume time too; never present the
                    # earlier pose age or bypass the final source/TTL fences.
                    self.runtime.operational_navigation.verify_preparation_calibration(
                        record['pair']['generation'], record['pair']['calibration_sha256'], record['T_imu_base'])
                    latest = getattr(self.runtime.operational_navigation, 'preparation_snapshot',
                                     self.runtime.operational_navigation.status)()
                    if (not latest.get('pair') or self._pair(latest) != record['pair']
                            or latest['selected']['calibration']['T_imu_base'] != record['T_imu_base']
                            or latest['selected']['calibration']['T_nav_map_from_localization_map'] != record['T_nav_map_from_localization_map']):
                        raise ProposalConflict('SOURCE_OR_CONTEXT_CHANGED')
                    if not 0 < resolution['expires_monotonic_s'] - time.monotonic() <= 120.:
                        raise ProposalConflict('OPERATOR_PRIOR_EXPIRED')
                    if (self._session_binding(self._session(record['session']['session_id'])) != record['session']
                            or self._source(session, record['source_identity'])[0] != record['source_contract']):
                        raise ProposalConflict('SOURCE_OR_CONTEXT_CHANGED')
                    with record['gate_lock']:
                        invalidated = record.get('invalidated_reason')
                    if invalidated:
                        return self._empty(record, 'stale', invalidated)
                    age_after_members = proposal['pose_age_s'] + time.monotonic() - proposal_read_at
                    if not math.isfinite(age_after_members) or not 0 <= age_after_members <= 1.:
                        raise ProposalConflict('OBSERVATION_INPUTS_UNAVAILABLE')
                    result['provenance']['pose_age_s'] = age_after_members
                    result['current_vs_prior']['pose_age_s'] = age_after_members
                return result
            except (ProposalConflict, ProposalUnavailable, GlobalObservationConflict, ObservationAlignmentError, ExternalGlobalObservationError,
                    AttributeError, KeyError, TypeError, ValueError, OSError, OverflowError) as exc:
                reason = str(exc) or 'SOURCE_OR_CONTEXT_CHANGED'
                if reason in {'MAP_PAIR_REQUIRED', 'MAP_PAIR_CHANGED', 'OBSERVATION_SESSION_CHANGED',
                              'SOURCE_OR_CONTEXT_CHANGED', 'CALIBRATION_CHANGED', 'OWNERSHIP_BUSY_OR_UNKNOWN'} or reason.startswith('CONTROL_'):
                    with record['gate_lock']:
                        record['invalidated_reason'] = reason
                return self._empty(record, 'stale', reason)
