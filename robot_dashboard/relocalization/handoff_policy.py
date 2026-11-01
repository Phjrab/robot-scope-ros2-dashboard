"""Local, bounded policy for explicitly confirmed proposal handoffs."""
import math
import re
import time

POLICY_ID = 'robot-scope.proposal-handoff.local-v1'
TTL_S, MAX_XY_M, MAX_YAW_RAD = 120., .25, .20


def process_identity(pid):
    # Linux start ticks distinguish a restarted process even if its PID is reused.
    with open(f'/proc/{pid}/stat', encoding='ascii') as stream:
        value = stream.read().rsplit(')', 1)[1].split()
    return value[19]


def validate_handoff(geometry, bundle=None):
    if geometry.get('source') != 'proposal_confirmed':
        return
    proof = geometry.get('handoff')
    if not isinstance(proof, dict) or proof.get('policy_id') != POLICY_ID:
        raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
    if any(not isinstance(proof.get(k), str) or not proof[k] for k in
           ('handoff_id', 'proposal_id', 'bundle_generation', 'observation_session_id',
            'calibration_sha256', 'owner_start_ticks', 'stop_nonce', 'source_contract_sha256',
            'capture_stamp_ns', 'localization_map_id', 'localization_map_revision',
            'navigation_map_id', 'navigation_map_revision')):
        raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
    for key, size in (('handoff_id',32), ('proposal_id',24), ('bundle_generation',32),
                      ('observation_session_id',32), ('stop_nonce',32), ('calibration_sha256',64),
                      ('source_contract_sha256',64), ('localization_map_id',24),
                      ('localization_map_revision',64), ('navigation_map_id',24), ('navigation_map_revision',64)):
        if not re.fullmatch(r'[a-f0-9]{%d}' % size, proof[key]):
            raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
    started = proof.get('observation_started_monotonic_s')
    if type(started) not in (int, float) or not math.isfinite(started) or started <= 0 or not proof['capture_stamp_ns'].isdigit():
        raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
    if proof.get('stop_state') != 'INACTIVE_CONFIRMED':
        raise ValueError('HANDOFF_STOP_OUTCOME_UNKNOWN')
    reference = proof.get('reference')
    if not isinstance(reference, dict) or any(type(reference.get(k)) not in (int, float)
            or not math.isfinite(reference[k]) for k in ('x', 'y', 'yaw')):
        raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
    deadline = proof.get('expires_monotonic_s')
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
    if not 0 < deadline - time.monotonic() <= TTL_S:
        raise ValueError('HANDOFF_EXPIRED')
    try:
        if process_identity(proof['owner_pid']) != proof['owner_start_ticks']:
            raise ValueError('HANDOFF_RUNTIME_CHANGED')
    except (OSError, KeyError, TypeError, IndexError):
        raise ValueError('HANDOFF_RUNTIME_CHANGED') from None
    if bundle is not None and (proof['bundle_generation'] != bundle.get('generation')
            or proof['calibration_sha256'] != (bundle.get('map_binding') or {}).get('calibration_sha256')
            or (proof['localization_map_id'], proof['localization_map_revision']) !=
                (bundle['localization_3d']['map_id'], bundle['localization_3d']['revision'])
            or (proof['navigation_map_id'], proof['navigation_map_revision']) !=
                (bundle['navigation_2d']['map_id'], bundle['navigation_2d']['revision'])):
        raise ValueError('MAP_PAIR_CHANGED')


def validate_candidate(geometry, x, y, yaw, bundle=None):
    validate_handoff(geometry, bundle)
    if geometry.get('source') != 'proposal_confirmed':
        return
    ref = geometry['handoff']['reference']
    angle = math.atan2(math.sin(yaw-ref['yaw']), math.cos(yaw-ref['yaw']))
    if math.hypot(x-ref['x'], y-ref['y']) > MAX_XY_M or abs(angle) > MAX_YAW_RAD:
        raise ValueError('INITIAL_POSE_CANDIDATE_MISMATCH')
