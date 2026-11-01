"""Read-only, evidence-bound preparation preview; never applies a pose."""
from __future__ import annotations

import math
import time

from .runtime_health_sample import capture_runtime_health

from .anchor_proposal import imu_matrix, source_contract
from ..observation_service import inspect_inputs
from ..relocalization.experimental_se3 import _rpy, validate_transform
from ..relocalization.observation_alignment import ObservationAlignmentError, paired_pose, project_query


SCHEMA = 'robot-scope.navigation-preparation-inputs.v1'


def observation_start_blockers(runtime):
    """Advisory copy under pipeline_coordination_lock; admission rechecks independently."""
    from .ownership_readback import ownership_readback

    owner = runtime.fastlio_observation
    if owner is None:
        return {'items': ['OBSERVATION_STATUS_UNAVAILABLE'], 'advisory': True}
    items = []
    try:
        session = owner.snapshot()
        if not session.get('can_start'):
            items.append('OBSERVATION_SESSION_NOT_STARTABLE')
        owners = ownership_readback(runtime)
        allowed = {'fastlio_observation', 'legacy_alignment'}
        items.extend('OWNER_BUSY:' + item for item in owners['busy_components'] if item not in allowed)
        items.extend('OWNER_UNKNOWN:' + item for item in owners['unknown_components'] if item not in allowed)
        # Fixed systemd read only: avoid the lifecycle snapshot's unrelated preflight callbacks.
        bridge = runtime.lifecycle.control_bridge_lifecycle._read_systemd()
        if bridge.get('available') is not True or bridge.get('active_state') == 'unknown':
            items.append('CONTROL_BRIDGE_STATE_UNKNOWN')
        elif bridge.get('active_state') != 'inactive':
            items.append('CONTROL_BRIDGE_NOT_INACTIVE')
    except Exception:
        items.append('START_BLOCKERS_UNAVAILABLE')
    return {'items': list(dict.fromkeys(items)), 'advisory': True}


def _summary(sample):
    observation = sample.get('observation') or {}
    return {**{key: sample.get(key) for key in ('topic', 'frame_id', 'child_frame_id', 'seq')},
            **{key: observation.get(key) for key in ('source_stamp_ns', 'received_monotonic_s',
                'observer_id', 'publisher_epoch', 'receipt_clock')}}


def _source_identity(sample):
    """Fence actual source/session/graph changes even if evidence becomes invalid."""
    observation = sample.get('observation') or {}
    subscription = observation.get('subscription_evidence') or {}
    graph = subscription.get('graph') or {}
    return (sample.get('topic'), sample.get('frame_id'), sample.get('child_frame_id'),
            sample.get('pipeline_stage'), observation.get('observer_id'), observation.get('publisher_epoch'),
            subscription.get('session_id'), subscription.get('topic'), subscription.get('type_name'),
            graph.get('fingerprint'))


def _pair(state):
    pair = state.get('pair')
    if not pair:
        return None
    return {key: pair.get(key) for key in ('generation', 'localization_3d', 'navigation_2d',
                                           'calibration_sha256', 'valid')}


def _map_candidates(pair, health, execution):
    """Only a live, quality-gated estimate from the identical active bundle qualifies."""
    if not pair:
        return None, 'MAP_PAIR_REQUIRED'
    if not pair.get('valid'):
        return None, 'MAP_PAIR_INVALID'
    if not execution:
        return None, 'NAVIGATION_JOB_NOT_RUNNING'
    source = (health or {}).get('operational_3d') or {}
    estimate = source.get('estimated_pose') or {}
    pins = {'bundle_generation': pair['generation'],
            'map_id': pair['navigation_2d']['map_id'], 'map_revision': pair['navigation_2d']['revision'],
            'localization_map_id': pair['localization_3d']['map_id'],
            'localization_map_revision': pair['localization_3d']['revision']}
    health_age, estimate_age = (health or {}).get('age_s'), estimate.get('age_s')
    age_ok = (type(health_age) in (int, float) and type(estimate_age) in (int, float)
              and math.isfinite(health_age) and math.isfinite(estimate_age)
              and 0 <= health_age and 0 <= estimate_age and health_age + estimate_age <= .5)
    generation = source.get('runtime_instance_generation')
    seq = source.get('correction_sequence')
    stamp = estimate.get('stamp_ns')
    try:
        pid, runtime_started = (int(part) for part in generation.split(':'))
        boundary = execution['snapshot_monotonic_ns']
        runtime_bound = (pid > 0 and type(boundary) is int
                         and (health or {}).get('process_generation') == pid
                         and boundary <= runtime_started <= time.monotonic_ns())
    except (AttributeError, KeyError, TypeError, ValueError):
        runtime_bound = False
    if not ((health or {}).get('fresh') is True and source.get('source') == 'STORED_PCD_FASTLIO'
            and source.get('ready') is True and estimate.get('stale') is False and age_ok
            and runtime_bound and generation == (health or {}).get('runtime_instance_generation')
            and execution.get('source') == 'STORED_PCD_FASTLIO'
            and all(execution.get(k) == v for k, v in pins.items())
            and isinstance(execution.get('job_id'), str) and len(execution['job_id']) == 32
            and estimate.get('source') == 'STORED_PCD_FASTLIO'
            and type(source.get('localization_generation')) is int and source['localization_generation'] > 0
            and type(seq) is int and seq > 0 and estimate.get('correction_sequence') == seq
            and isinstance(stamp, str) and stamp.isdecimal() and int(stamp) > 0
            and source.get('reference_sha256') == pair['localization_3d'].get('sha256')
            and all(source.get(k) == v and estimate.get(k) == v for k, v in pins.items())
            and all(estimate.get(k) == source.get(k) for k in ('runtime_instance_generation', 'localization_generation'))):
        return None, 'MAP_ESTIMATE_UNAVAILABLE_OR_STALE'
    pose = estimate.get('pose') or {}
    for name, limit in (('z', 1000), ('roll', math.pi), ('pitch', math.pi / 2)):
        value = pose.get(name)
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > limit:
            return None, 'MAP_ESTIMATE_INVALID'
    provenance = {**pins, 'source': source['source'], 'source_stamp_ns': stamp,
                  'job_id': execution['job_id'], 'runtime_instance_generation': generation, 'localization_generation': source['localization_generation'],
                  'correction_sequence': seq, 'age_s': health_age + estimate_age,
                  'calibration_sha256': pair['calibration_sha256']}
    return {axis: {'value': float(pose[axis]), 'frame': 'map', 'available': True,
                   'reason': None, 'provenance': provenance} for axis in ('z', 'roll', 'pitch')}, None



_DIAGNOSTIC_CODES = frozenset({
    'OBSERVATION_INACTIVE', 'OBSERVATION_INPUTS_UNAVAILABLE', 'MAP_PAIR_REQUIRED',
    'MAP_PAIR_INVALID', 'CONTEXT_CHANGED', 'OBSERVATION_STALE_OR_SOURCE_INVALID',
    'POSE_PAIR_UNAVAILABLE', 'SOURCE_CHANGED', 'STALE_INPUT', 'FASTLIO_REGISTERED_IMU_REQUIRED',
    'RECEIPT_TIME_MISMATCH', 'SUBSCRIPTION_TYPE_MISMATCH', 'INVALID_QUATERNION',
    'INVALID_INPUT', 'CALIBRATION_CHANGED', 'STAMP_REGRESSION', 'EXACT_STAMP_MISMATCH',
    'FASTLIO_SOURCE_TIME_MISMATCH', 'SOURCE_IDENTITY_UNAVAILABLE', 'SUBSCRIPTION_EVIDENCE_CHANGED',
    'SUBSCRIPTION_EVIDENCE_UNAVAILABLE', 'POSE_SOURCE_CHANGED', 'NO_PAIRED_POSE',
})


def _diagnostic_metadata(sample, now, started):
    if not isinstance(sample, dict):
        sample = {}
    observation = sample.get('observation') if isinstance(sample.get('observation'), dict) else {}
    subscription = observation.get('subscription_evidence') if isinstance(observation.get('subscription_evidence'), dict) else {}
    graph = subscription.get('graph') if isinstance(subscription.get('graph'), dict) else {}
    def bounded(value, *, stamp=False):
        if not isinstance(value, str) or not value or len(value) > 128:
            return None
        if stamp and (not value.isdecimal() or len(value) > 20):
            return None
        return value
    def age(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            return None
        result = now - value
        return round(result, 6) if math.isfinite(result) else None
    def count(value):
        return value if type(value) is int and 0 <= value <= 2**31-1 else None
    received = observation.get('received_monotonic_s')
    after_start = (received >= started if type(received) in (int, float) and math.isfinite(received)
                   and type(started) in (int, float) and math.isfinite(started) else None)
    return {'topic': bounded(sample.get('topic')), 'frame_id': bounded(sample.get('frame_id')),
            'child_frame_id': bounded(sample.get('child_frame_id')), 'state': bounded(sample.get('state')),
            'units': bounded(sample.get('units')), 'sent_points': count(sample.get('sent_points')),
            'observer_id': bounded(observation.get('observer_id')),
            'publisher_epoch': bounded(observation.get('publisher_epoch')),
            'source_stamp_ns': bounded(observation.get('source_stamp_ns'), stamp=True),
            'subscription_session_id': bounded(subscription.get('session_id')),
            'graph_fingerprint': bounded(graph.get('fingerprint')),
            'receipt_age_s': age(received), 'receipt_after_session_start': after_start,
            'graph_age_s': age(graph.get('observed_monotonic_s')),
            'graph_state': bounded(graph.get('state')),
            'graph_endpoint_count': count(graph.get('endpoint_count')),
            'graph_publisher_count': count(graph.get('reported_publisher_count'))}


def _stamps(cloud, pose):
    values = tuple(int(sample['observation']['source_stamp_ns']) for sample in (cloud, pose))
    if any(value <= 0 for value in values):
        raise ValueError('INVALID_SOURCE_STAMP')
    return values


def preparation_inputs(manager, observation_session, agent):
    request_started = time.monotonic()
    phase_names = ('initial_snapshot', 'initial_capture', 'pair_validation', 'health_and_handoff',
                   'final_capture', 'calibration_fence', 'response_fence', 'total')
    diagnostic = {'schema': 'robot-scope.preparation-diagnostics.v1', 'failure_stage': None,
                  'failure_code': None, 'failure_sample': None, 'checks': [],
                  'phase_ms': {name: None for name in phase_names}}
    def elapsed(name, started):
        diagnostic['phase_ms'][name] = round(max(0., time.monotonic() - started) * 1000., 3)
    def fail(stage, code, sample_pose=None, sample_cloud=None, sampled_at=None, started=None):
        if diagnostic['failure_stage'] is None:
            diagnostic['failure_stage'] = stage
            diagnostic['failure_code'] = code if code in _DIAGNOSTIC_CODES else 'INPUT_UNAVAILABLE'
            if diagnostic['checks'] and diagnostic['checks'][-1]['stage'] == stage:
                value = diagnostic['checks'][-1]
                diagnostic['failure_sample'] = {'stage': stage, 'pose': value['pose'], 'cloud': value['cloud']}
            elif sample_pose is not None or sample_cloud is not None:
                now = time.monotonic() if sampled_at is None else sampled_at
                diagnostic['failure_sample'] = {'stage': stage,
                    'pose': _diagnostic_metadata(sample_pose, now, started),
                    'cloud': _diagnostic_metadata(sample_cloud, now, started)}
    def checked(stage, sample_name, sample_pose, sample_cloud, started):
        now = time.monotonic()
        value = inspect_inputs(sample_pose, sample_cloud, started, now=now)
        diagnostic['checks'].append({'stage': stage, 'sample': sample_name,
            'ready': value['ready'], 'failures': value['failures'],
            'pose': _diagnostic_metadata(sample_pose, now, started), 'cloud': _diagnostic_metadata(sample_cloud, now, started)})
        return value['ready']
    phase_at = time.monotonic()
    # Capture against a tentative copy; only the final full validation can
    # authorize any returned reference or candidate. Never cache asset proof.
    state = getattr(manager, 'preparation_snapshot', manager.status)()
    pair = _pair(state)
    session = observation_session.snapshot() if observation_session else {'state': 'UNAVAILABLE', 'active': False}
    elapsed('initial_snapshot', phase_at)
    phase_at = time.monotonic()
    evidence = {'valid': False, 'reason': None, 'cloud': None, 'pose': None,
                'calibration_sha256': pair.get('calibration_sha256') if pair else None}
    reference = None
    capture_identity = None
    source_transition = False
    initial_stamps = None
    last_stamps = None
    failure_stage = 'session'
    initial_capture_attempted = False
    if not session.get('active') or session.get('state') != 'READY' or not session.get('session_id'):
        evidence['reason'] = 'OBSERVATION_INACTIVE'
        fail('session', evidence['reason'])
    elif agent is None:
        evidence['reason'] = 'OBSERVATION_INPUTS_UNAVAILABLE'
        fail('session', evidence['reason'])
    elif not pair:
        evidence['reason'] = 'MAP_PAIR_REQUIRED'
        fail('session', evidence['reason'])
    else:
        initial_capture_attempted = True
        try:
            started = session.get('started_monotonic_s')
            failure_stage = 'initial_latest'
            cloud, latest = agent.pointcloud_binary_snapshot(), agent.pose_snapshot()
            capture_identity = (_source_identity(cloud), _source_identity(latest))
            now = time.monotonic()
            failure_stage = 'initial_latest'
            if not checked('initial_latest', 'initial', latest, cloud, started):
                raise ObservationAlignmentError('OBSERVATION_STALE_OR_SOURCE_INVALID')
            mode = 'subscription_observation'
            contract = source_contract(cloud, latest, mode, now)
            initial_stamps = _stamps(cloud, latest)
            failure_stage = 'initial_pairing'
            pose = paired_pose(agent, cloud, contract, now + .15)
            if pose is None:
                raise ObservationAlignmentError('POSE_PAIR_UNAVAILABLE')
            now = time.monotonic()
            failure_stage = 'initial_paired'
            if not checked('initial_paired', 'initial', pose, cloud, started):
                raise ObservationAlignmentError('OBSERVATION_STALE_OR_SOURCE_INVALID')
            if source_contract(cloud, pose, mode, now) != contract:
                source_transition = True
                raise ObservationAlignmentError('SOURCE_CHANGED')
            project_query(cloud, pose, now, provenance_mode=mode)
            transform = imu_matrix(pose) @ validate_transform(state['selected']['calibration']['T_imu_base'])
            roll, pitch, yaw = _rpy(transform[:3, :3])
            reference = {'frame': pose['frame_id'], 'child_frame': 'base_link',
                         'position': dict(zip(('x', 'y', 'z'), map(float, transform[:3, 3]))),
                         'orientation': dict(zip(('roll', 'pitch', 'yaw'), map(float, (roll, pitch, yaw)))),
                         'source_stamp_ns': cloud['observation']['source_stamp_ns'],
                         'qualification': 'OBSERVATION_FRAME_ONLY_MAP_RELATION_UNVERIFIED'}
            evidence.update(valid=True, cloud=_summary(cloud), pose=_summary(pose))
        except Exception as exc:
            evidence['reason'] = str(exc) if isinstance(exc, ObservationAlignmentError) else 'OBSERVATION_INPUTS_UNAVAILABLE'
            fail(failure_stage, evidence['reason'])
    if initial_capture_attempted:
        elapsed('initial_capture', phase_at)
    phase_at = time.monotonic()
    # Revalidate selection and session after sample capture; never return data across a transition.
    current = manager.status()
    elapsed('pair_validation', phase_at)
    phase_at = time.monotonic()
    latest_session = observation_session.snapshot() if observation_session else session
    current_pair = _pair(current)
    def identity(value):
        return {k: v for k, v in value.items() if k != 'valid'} if value else None
    context_changed = (identity(current_pair) != identity(pair)
        or state.get('selected') != current.get('selected')
        or any(latest_session.get(k) != session.get(k) for k in
               ('session_id', 'state', 'active', 'started_monotonic_s')))
    pair, session = current_pair, latest_session
    if context_changed or (pair and pair.get('valid') is not True):
        reference = None
        evidence = {'valid': False, 'reason': 'CONTEXT_CHANGED' if context_changed else 'MAP_PAIR_INVALID',
                    'cloud': None, 'pose': None,
                    'calibration_sha256': pair.get('calibration_sha256') if pair else None}
        fail('context_fence' if context_changed else 'pair_validation', evidence['reason'])
    if evidence['valid']:
        current_cloud = current_pose = None
        try:
            current_cloud, current_pose = agent.pointcloud_binary_snapshot(), agent.pose_snapshot()
            now = time.monotonic()
            if (_source_identity(current_cloud), _source_identity(current_pose)) != capture_identity:
                source_transition = True
                raise ObservationAlignmentError('SOURCE_CHANGED')
            last_stamps = _stamps(current_cloud, current_pose)
            if any(a < b for a, b in zip(last_stamps, initial_stamps)):
                source_transition = True
                raise ObservationAlignmentError('STAMP_REGRESSION')
            if source_contract(current_cloud, current_pose, 'subscription_observation', now) != contract:
                source_transition = True
                raise ObservationAlignmentError('SOURCE_CHANGED')
        except Exception as exc:
            reference = None
            reason = str(exc) if isinstance(exc, ObservationAlignmentError) else 'OBSERVATION_INPUTS_UNAVAILABLE'
            if reason == 'STALE_INPUT':
                reason = 'OBSERVATION_STALE_OR_SOURCE_INVALID'
            evidence.update(valid=False, reason=reason, cloud=None, pose=None)
            fail('context_fence', reason, current_pose, current_cloud, now, session.get('started_monotonic_s'))
    read_execution = getattr(manager, 'preparation_execution', lambda: None)
    execution = read_execution()
    health_sample = capture_runtime_health(agent)
    health_started = health_sample.sampled_at
    health_raw = health_sample.snapshot()
    health = health_raw
    job_changed = read_execution() != execution
    if job_changed:
        execution = None
    if type(health.get('age_s')) in (int, float):
        # Health ages are rounded to milliseconds by the gateway. Include time
        # spent rechecking the job and the rounding margin before presenting it.
        health = {**health, 'age_s': health['age_s'] + time.monotonic() - health_started + .001}
    # A final cheap in-memory fence ensures the status and evidence refer to
    # the same selection/session/job; it does not cache or replace validation.
    latest_selection = getattr(manager, 'preparation_snapshot', lambda: current)()
    end_session = observation_session.snapshot() if observation_session else session
    changed = (context_changed or source_transition or job_changed or latest_selection.get('selected') != current.get('selected')
               or any(end_session.get(k) != session.get(k) for k in
                      ('session_id', 'state', 'active', 'started_monotonic_s')))
    if capture_identity is not None and not changed:
        try:
            intermediate_cloud, intermediate_pose = agent.pointcloud_binary_snapshot(), agent.pose_snapshot()
            if (_source_identity(intermediate_cloud), _source_identity(intermediate_pose)) != capture_identity:
                changed = True
                fail('context_fence', 'CONTEXT_CHANGED', intermediate_pose, intermediate_cloud,
                     time.monotonic(), session.get('started_monotonic_s'))
            elif evidence['valid']:
                intermediate_stamps = _stamps(intermediate_cloud, intermediate_pose)
                if any(a < b for a, b in zip(intermediate_stamps, last_stamps or initial_stamps)):
                    changed = True
                    fail('context_fence', 'STAMP_REGRESSION', intermediate_pose, intermediate_cloud,
                         time.monotonic(), session.get('started_monotonic_s'))
                elif source_contract(intermediate_cloud, intermediate_pose,
                        'subscription_observation', time.monotonic()) != contract:
                    changed = True
                last_stamps = intermediate_stamps
        except Exception:
            # A stale/temporarily unavailable input alone is not proof of a
            # source transition. Never retain the reference in that case.
            reference = None
            evidence.update(valid=False, reason='OBSERVATION_STALE_OR_SOURCE_INVALID', cloud=None, pose=None)
            fail('context_fence', 'OBSERVATION_STALE_OR_SOURCE_INVALID')
    if changed:
        reference = None
        evidence.update(valid=False, reason='CONTEXT_CHANGED', cloud=None, pose=None)
        fail('context_fence', 'CONTEXT_CHANGED')
        execution = None
    runtime_fresh = bool(health.get('fresh') is True and type(health.get('age_s')) in (int, float)
                         and 0 <= health['age_s'] <= .75)
    operational_state = None if changed else {**current, 'runtime': health.get('operational_3d'),
                                                'runtime_fresh': runtime_fresh}
    # A match HTTP response may be lost after the runtime actually accepted it.
    # Recover only from the fresh, exact bound job/runtime/receipt, never by POST.
    if (operational_state and operational_state.get('initialization_handoff') is not None
            and runtime_fresh and execution and pair and pair.get('valid')):
        source = health.get('operational_3d') or {}
        receipt = source.get('match_receipt') or {}
        geometry = ((current.get('selected') or {}).get('seed_geometry') or {})
        proof = geometry.get('handoff') or {}
        try:
            instance = source.get('runtime_instance_generation')
            pid, started = (int(part) for part in instance.split(':'))
            bound = (health.get('runtime_instance_generation') == instance
                     and health.get('process_generation') == pid and pid > 0
                     and execution['snapshot_monotonic_ns'] <= started <= time.monotonic_ns())
            exact = (geometry.get('source') == 'proposal_confirmed' and bound
                     and source.get('source') == 'STORED_PCD_FASTLIO'
                     and source.get('match_armed') is True and receipt.get('accepted') is True
                     and type(source.get('localization_generation')) is int
                     and source['localization_generation'] == receipt.get('localization_generation')
                     and source.get('bundle_generation') == pair['generation'] == execution['bundle_generation']
                     and (source.get('map_id'), source.get('map_revision')) ==
                         (pair['navigation_2d']['map_id'], pair['navigation_2d']['revision'])
                     and (source.get('localization_map_id'), source.get('localization_map_revision')) ==
                         (pair['localization_3d']['map_id'], pair['localization_3d']['revision'])
                     and source.get('reference_sha256') == pair['localization_3d']['sha256']
                     and proof.get('job_id') == execution['job_id']
                     and read_execution() == execution
                     and type(health_raw.get('age_s')) in (int, float)
                     and health_raw['age_s'] + (time.monotonic() - health_started) + .001 <= .75)
            if exact:
                manager.record_match_armed(pair['generation'], source['map_id'], source['map_revision'], receipt, health_sample)
                operational_state['initialization_handoff'] = manager.handoff_status(proof['handoff_id'], validate_assets=False, health=health_sample)
        except (AttributeError, KeyError, TypeError, ValueError, OSError):
            pass  # Uncertain recovery never becomes a successful match.
        if geometry.get('source') == 'proposal_confirmed' and proof.get('handoff_id'):
            try:
                operational_state['initialization_handoff'] = manager.handoff_status(
                    proof['handoff_id'], validate_assets=False, health=health_sample)
            except (AttributeError, KeyError, TypeError, ValueError, OSError):
                pass
    elapsed('health_and_handoff', phase_at)
    # Discard the pre-validation pair and capture a new exact pair only after
    # all potentially slow map, health and handoff work has completed.
    final_cloud = final_pose = None
    if evidence['valid'] and not changed:
        phase_at = time.monotonic()
        stage = 'final_latest'
        final_latest = None
        try:
            final_cloud = agent.pointcloud_binary_snapshot()
            final_latest = agent.pose_snapshot()
            if (_source_identity(final_cloud), _source_identity(final_latest)) != capture_identity:
                changed = True
                raise ObservationAlignmentError('SOURCE_CHANGED')
            final_ready = checked('final_latest', 'final', final_latest, final_cloud, session['started_monotonic_s'])
            new_stamps = _stamps(final_cloud, final_latest)
            if any(a < b for a, b in zip(new_stamps, last_stamps or initial_stamps)):
                changed = True
                raise ObservationAlignmentError('STAMP_REGRESSION')
            if not final_ready:
                raise ObservationAlignmentError('OBSERVATION_STALE_OR_SOURCE_INVALID')
            now = time.monotonic()
            if source_contract(final_cloud, final_latest, 'subscription_observation', now) != contract:
                changed = True
                raise ObservationAlignmentError('SOURCE_CHANGED')
            stage = 'final_pairing'
            final_pose = paired_pose(agent, final_cloud, contract, now + .15)
            if final_pose is None:
                raise ObservationAlignmentError('POSE_PAIR_UNAVAILABLE')
            stage = 'final_paired'
            if not checked('final_paired', 'final', final_pose, final_cloud, session['started_monotonic_s']):
                raise ObservationAlignmentError('OBSERVATION_STALE_OR_SOURCE_INVALID')
            if source_contract(final_cloud, final_pose, 'subscription_observation', time.monotonic()) != contract:
                changed = True
                raise ObservationAlignmentError('SOURCE_CHANGED')
            if _stamps(final_cloud, final_pose)[0] != _stamps(final_cloud, final_pose)[1]:
                raise ObservationAlignmentError('EXACT_STAMP_MISMATCH')
            project_query(final_cloud, final_pose, time.monotonic(), provenance_mode='subscription_observation')
            transform = imu_matrix(final_pose) @ validate_transform(current['selected']['calibration']['T_imu_base'])
            roll, pitch, yaw = _rpy(transform[:3, :3])
            reference = {'frame': final_pose['frame_id'], 'child_frame': 'base_link',
                         'position': dict(zip(('x', 'y', 'z'), map(float, transform[:3, 3]))),
                         'orientation': dict(zip(('roll', 'pitch', 'yaw'), map(float, (roll, pitch, yaw)))),
                         'source_stamp_ns': final_cloud['observation']['source_stamp_ns'],
                         'qualification': 'OBSERVATION_FRAME_ONLY_MAP_RELATION_UNVERIFIED'}
            evidence.update(valid=True, reason=None, cloud=_summary(final_cloud), pose=_summary(final_pose))
            last_stamps = new_stamps
        except Exception as exc:
            reason = str(exc) if isinstance(exc, ObservationAlignmentError) else 'OBSERVATION_INPUTS_UNAVAILABLE'
            if reason == 'STALE_INPUT':
                reason = 'OBSERVATION_STALE_OR_SOURCE_INVALID'
            if stage == 'final_pairing':
                fail(stage, reason)  # No paired pose was obtained.
            else:
                fail(stage, reason, final_pose if stage == 'final_paired' else final_latest, final_cloud,
                     time.monotonic(), session.get('started_monotonic_s'))
            reference = None
            evidence.update(valid=False, reason=reason, cloud=None, pose=None)
        elapsed('final_capture', phase_at)
    if evidence['valid'] and not changed:
        phase_at = time.monotonic()
        try:
            verify = getattr(manager, 'verify_preparation_calibration', None)
            if verify is not None:
                verify(pair['generation'], pair['calibration_sha256'], current['selected']['calibration']['T_imu_base'])
        except (KeyError, TypeError, ValueError, OSError):
            changed = True
            fail('calibration_fence', 'CALIBRATION_CHANGED')
        elapsed('calibration_fence', phase_at)
    phase_at = time.monotonic()
    # A final same-request fence follows calibration and all handoff calls.
    latest_selection = getattr(manager, 'preparation_snapshot', lambda: current)()
    end_session = observation_session.snapshot() if observation_session else session
    changed = (changed or latest_selection.get('selected') != current.get('selected')
               or any(end_session.get(k) != session.get(k) for k in
                      ('session_id', 'state', 'active', 'started_monotonic_s'))
               or (execution is not None and read_execution() != execution))
    if evidence['valid'] and not changed:
        response_cloud = response_pose = None
        try:
            response_cloud, response_pose = agent.pointcloud_binary_snapshot(), agent.pose_snapshot()
            if (_source_identity(response_cloud), _source_identity(response_pose)) != capture_identity:
                changed = True
                fail('response_fence', 'CONTEXT_CHANGED', response_pose, response_cloud,
                     time.monotonic(), session.get('started_monotonic_s'))
            elif any(a < b for a, b in zip(_stamps(response_cloud, response_pose), last_stamps)):
                changed = True
                fail('response_fence', 'STAMP_REGRESSION', response_pose, response_cloud,
                     time.monotonic(), session.get('started_monotonic_s'))
            elif source_contract(response_cloud, response_pose, 'subscription_observation', time.monotonic()) != contract:
                changed = True
        except Exception:
            reference = None
            evidence.update(valid=False, reason='OBSERVATION_STALE_OR_SOURCE_INVALID', cloud=None, pose=None)
            fail('response_fence', 'OBSERVATION_STALE_OR_SOURCE_INVALID', response_pose, response_cloud,
                 time.monotonic(), session.get('started_monotonic_s'))
    if changed:
        reference = None
        evidence.update(valid=False, reason='CONTEXT_CHANGED', cloud=None, pose=None)
        fail('response_fence', 'CONTEXT_CHANGED')
        execution = None
        operational_state = None
    elapsed('response_fence', phase_at)
    # Recompute at the final response boundary: the manager or executor may
    # have waited after health was fetched. Never reset an already stale sample.
    if type(health_raw.get('age_s')) in (int, float):
        health = {**health_raw, 'age_s': health_raw['age_s'] + (time.monotonic() - health_started) + .001}
    runtime_fresh = bool(health.get('fresh') is True and type(health.get('age_s')) in (int, float)
                         and math.isfinite(health['age_s']) and 0 <= health['age_s'] <= .75)
    if operational_state:
        operational_state['runtime_fresh'] = runtime_fresh
        handoff = operational_state.get('initialization_handoff')
        if not runtime_fresh and handoff and handoff.get('state') == 'MATCH_ARMED':
            operational_state['initialization_handoff'] = {**handoff, 'state': 'OUTCOME_UNKNOWN',
                'reason': 'HANDOFF_MATCH_CURRENT_UNCONFIRMED', 'geometry': None, 'initial_pose_reference': None}
    candidates, reason = _map_candidates(pair, health, execution)
    if candidates is None:
        candidates = {axis: {'value': None, 'frame': 'map', 'available': False,
                             'reason': (reason if reason in ('MAP_PAIR_REQUIRED', 'MAP_PAIR_INVALID') else
                                        'MAP_ABSOLUTE_Z_UNVERIFIED' if axis == 'z' else 'MAP_GRAVITY_ALIGNMENT_UNVERIFIED'),
                             'provenance': None} for axis in ('z', 'roll', 'pitch')}
    # This is intentionally after every potentially slow manager operation.
    if evidence['valid'] and not checked('response_pair', 'response', final_pose, final_cloud,
                                         session['started_monotonic_s']):
        reference = None
        evidence.update(valid=False, reason='OBSERVATION_STALE_OR_SOURCE_INVALID', cloud=None, pose=None)
        fail('response_pair', 'OBSERVATION_STALE_OR_SOURCE_INVALID')
    if evidence['valid']:
        diagnostic['failure_stage'] = diagnostic['failure_code'] = diagnostic['failure_sample'] = None
    elif diagnostic['failure_stage'] is None:
        fail('response_fence', evidence.get('reason'))
    elapsed('total', request_started)
    evidence['diagnostics'] = diagnostic
    return {'schema': SCHEMA, 'pair': pair, 'observation': session, 'evidence': evidence,
            'reference_pose': reference, 'map_estimate_reason': reason, 'candidates': candidates,
            'operational_state': operational_state, 'operational_state_error': 'CONTEXT_CHANGED' if changed else None}
