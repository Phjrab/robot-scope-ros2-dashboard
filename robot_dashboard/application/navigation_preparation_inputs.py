"""Read-only, evidence-bound preparation preview; never applies a pose."""
from __future__ import annotations

import math
import time

from .runtime_health_sample import capture_runtime_health

from .anchor_proposal import imu_matrix, source_contract
from ..observation_service import inputs_ready
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


def preparation_inputs(manager, observation_session, agent):
    # Capture against a tentative copy; only the final full validation can
    # authorize any returned reference or candidate. Never cache asset proof.
    state = getattr(manager, 'preparation_snapshot', manager.status)()
    pair = _pair(state)
    session = observation_session.snapshot() if observation_session else {'state': 'UNAVAILABLE', 'active': False}
    evidence = {'valid': False, 'reason': None, 'cloud': None, 'pose': None,
                'calibration_sha256': pair.get('calibration_sha256') if pair else None}
    reference = None
    capture_identity = None
    source_transition = False
    if not session.get('active') or session.get('state') != 'READY' or not session.get('session_id'):
        evidence['reason'] = 'OBSERVATION_INACTIVE'
    elif agent is None:
        evidence['reason'] = 'OBSERVATION_INPUTS_UNAVAILABLE'
    elif not pair:
        evidence['reason'] = 'MAP_PAIR_REQUIRED'
    else:
        try:
            started = session.get('started_monotonic_s')
            cloud, latest = agent.pointcloud_binary_snapshot(), agent.pose_snapshot()
            capture_identity = (_source_identity(cloud), _source_identity(latest))
            now = time.monotonic()
            if not inputs_ready(latest, cloud, started, now=now):
                raise ObservationAlignmentError('OBSERVATION_STALE_OR_SOURCE_INVALID')
            mode = 'subscription_observation'
            contract = source_contract(cloud, latest, mode, now)
            pose = paired_pose(agent, cloud, contract, now + .15)
            if pose is None:
                raise ObservationAlignmentError('POSE_PAIR_UNAVAILABLE')
            now = time.monotonic()
            if not inputs_ready(pose, cloud, started, now=now):
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
        except (KeyError, TypeError, ValueError, OSError, ObservationAlignmentError) as exc:
            evidence['reason'] = str(exc) if isinstance(exc, ObservationAlignmentError) else 'OBSERVATION_INPUTS_UNAVAILABLE'
    # Revalidate selection and session after sample capture; never return data across a transition.
    current = manager.status()
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
    if evidence['valid']:
        try:
            now = time.monotonic()
            current_cloud, current_pose = agent.pointcloud_binary_snapshot(), agent.pose_snapshot()
            if (_source_identity(current_cloud), _source_identity(current_pose)) != capture_identity:
                source_transition = True
                raise ObservationAlignmentError('SOURCE_CHANGED')
            if not inputs_ready(pose, cloud, session['started_monotonic_s'], now=now):
                raise ObservationAlignmentError('OBSERVATION_STALE_OR_SOURCE_INVALID')
            if source_contract(current_cloud, current_pose, 'subscription_observation', now) != contract:
                raise ObservationAlignmentError('SOURCE_CHANGED')
        except (KeyError, TypeError, ValueError, OSError, ObservationAlignmentError) as exc:
            reference = None
            evidence.update(valid=False, reason=str(exc) if isinstance(exc, ObservationAlignmentError)
                            else 'OBSERVATION_INPUTS_UNAVAILABLE', cloud=None, pose=None)
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
    # Subsequent job/health checks can also consume the observation budget.
    if evidence['valid'] and not inputs_ready(pose, cloud, session['started_monotonic_s'], now=time.monotonic()):
        reference = None
        evidence.update(valid=False, reason='OBSERVATION_STALE_OR_SOURCE_INVALID', cloud=None, pose=None)
    # A final cheap in-memory fence ensures the status and evidence refer to
    # the same selection/session/job; it does not cache or replace validation.
    latest_selection = getattr(manager, 'preparation_snapshot', lambda: current)()
    end_session = observation_session.snapshot() if observation_session else session
    changed = (context_changed or source_transition or job_changed or latest_selection.get('selected') != current.get('selected')
               or any(end_session.get(k) != session.get(k) for k in
                      ('session_id', 'state', 'active', 'started_monotonic_s')))
    if capture_identity is not None and not changed:
        try:
            final_cloud, final_pose = agent.pointcloud_binary_snapshot(), agent.pose_snapshot()
            if (_source_identity(final_cloud), _source_identity(final_pose)) != capture_identity:
                changed = True
            elif evidence['valid'] and source_contract(final_cloud, final_pose,
                    'subscription_observation', time.monotonic()) != contract:
                changed = True
        except (ObservationAlignmentError, KeyError, TypeError, ValueError, OSError):
            # A stale/temporarily unavailable input alone is not proof of a
            # source transition. Never retain the reference in that case.
            reference = None
            evidence.update(valid=False, reason='OBSERVATION_STALE_OR_SOURCE_INVALID', cloud=None, pose=None)
    if changed:
        reference = None
        evidence.update(valid=False, reason='CONTEXT_CHANGED', cloud=None, pose=None)
        execution = None
    elif evidence['valid'] and not inputs_ready(pose, cloud, session['started_monotonic_s'], now=time.monotonic()):
        reference = None
        evidence.update(valid=False, reason='OBSERVATION_STALE_OR_SOURCE_INVALID', cloud=None, pose=None)
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
    return {'schema': SCHEMA, 'pair': pair, 'observation': session, 'evidence': evidence,
            'reference_pose': reference, 'map_estimate_reason': reason, 'candidates': candidates,
            'operational_state': operational_state, 'operational_state_error': 'CONTEXT_CHANGED' if changed else None}
