"""Local, bounded policy for explicitly confirmed proposal handoffs."""
import math
import re
import time

POLICY_ID = 'robot-scope.proposal-handoff.local-v1'
CONDITIONAL_POLICY_ID = 'robot-scope.proposal-handoff.operator-prior-v1'
GROUPING_POLICY = 'PINNED_V031_SE3_FIRST_REPRESENTATIVE_V1'
TTL_S, MAX_XY_M, MAX_YAW_RAD = 120., .25, .20


def process_identity(pid):
    # Linux start ticks distinguish a restarted process even if its PID is reused.
    with open(f'/proc/{pid}/stat', encoding='ascii') as stream:
        value = stream.read().rsplit(')', 1)[1].split()
    return value[19]


def _valid_prior_group(resolution, current_members):
    """Validate the stored grouping and all-member confirmation diagnostics."""
    indices = resolution.get('matching_member_indices')
    geometry = resolution.get('matching_member_geometry')
    raw_count = resolution.get('matching_candidate_count')
    retained_count = resolution.get('retained_candidate_count')
    eligible_count = resolution.get('eligible_candidate_count')
    duplicates = resolution.get('verified_duplicate_count')
    if (resolution.get('grouping_policy') != GROUPING_POLICY
            or type(raw_count) is not int or type(retained_count) is not int or type(eligible_count) is not int
            or type(duplicates) is not int or type(resolution.get('matching_hypothesis_count')) is not int
            or resolution['matching_hypothesis_count'] != 1
            or type(resolution.get('matching_retained_candidate_count')) is not int
            or resolution['matching_retained_candidate_count'] != raw_count
            or not 1 <= raw_count <= eligible_count <= retained_count <= 18
            or not raw_count-1 <= duplicates < eligible_count
            or not isinstance(indices, list) or len(indices) != raw_count
            or any(type(i) is not int or not 0 <= i < retained_count for i in indices)
            or indices != sorted(set(indices)) or indices[0] != resolution.get('candidate_index')
            or not isinstance(geometry, list) or len(geometry) != raw_count):
        return False
    keys = {'candidate_index','z_m','roll_rad','pitch_rad','z_delta_m','roll_delta_rad','pitch_delta_rad'}
    for i, member in zip(indices, geometry):
        if (not isinstance(member, dict) or set(member) != keys or type(member['candidate_index']) is not int
                or member['candidate_index'] != i
                or any(type(member[k]) not in (int, float) or not math.isfinite(member[k]) for k in keys - {'candidate_index'})):
            return False
    first = geometry[0]
    for member in geometry:
        for axis, delta_key in (('z_m','z_delta_m'), ('roll_rad','roll_delta_rad'), ('pitch_rad','pitch_delta_rad')):
            delta = member[axis] - first[axis]
            if axis != 'z_m':
                delta = math.atan2(math.sin(delta), math.cos(delta))
            if not math.isclose(delta, member[delta_key], rel_tol=0., abs_tol=1e-9):
                return False
    if not isinstance(current_members, dict) or set(current_members) != {'pose_stamp_ns', 'member_checks'}:
        return False
    stamp, checks = current_members['pose_stamp_ns'], current_members['member_checks']
    if (not isinstance(stamp, str) or not stamp.isdecimal() or int(stamp) <= 0
            or not isinstance(checks, list) or len(checks) != raw_count):
        return False
    bounds = resolution['operator_prior']['bounds']
    for i, check in zip(indices, checks):
        if (not isinstance(check, dict) or set(check) != {'candidate_index','xy_distance_m','absolute_wrapped_yaw_rad','within_prior_bounds'}
                or type(check['candidate_index']) is not int or check['candidate_index'] != i
                or check['within_prior_bounds'] is not True
                or any(type(check[k]) not in (int, float) or not math.isfinite(check[k]) or check[k] < 0
                       for k in ('xy_distance_m','absolute_wrapped_yaw_rad'))
                or check['xy_distance_m'] > bounds['xy_m'] or check['absolute_wrapped_yaw_rad'] > bounds['yaw_rad']):
            return False
    return True


def validate_handoff(geometry, bundle=None):
    if geometry.get('source') != 'proposal_confirmed':
        return
    proof = geometry.get('handoff')
    if not isinstance(proof, dict) or proof.get('policy_id') not in {POLICY_ID, CONDITIONAL_POLICY_ID}:
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
    resolution = proof.get('operator_prior_resolution')
    if proof['policy_id'] == CONDITIONAL_POLICY_ID:
        if (not isinstance(resolution, dict) or resolution.get('schema') != 'robot-scope.operator-prior-resolution.v1'
                or resolution.get('classification') != 'CONDITIONAL_ON_OPERATOR_PRIOR'
                or resolution.get('original_ambiguity_preserved') is not True
                or type(resolution.get('original_ambiguity_unresolved')) is not bool
                or resolution.get('global_uniqueness_verified') is not False
                or resolution.get('absolute_accuracy_m') is not None
                or type(resolution.get('candidate_index')) is not int
                or type(resolution.get('retained_candidate_count')) is not int
                or type(resolution.get('eligible_candidate_count')) is not int
                or not 0 <= resolution['candidate_index'] < resolution['retained_candidate_count'] <= 18
                or not 1 <= resolution['eligible_candidate_count'] <= resolution['retained_candidate_count']
                or resolution.get('bundle_generation') != proof['bundle_generation']
                or resolution.get('observation_session_id') != proof['observation_session_id']
                or resolution.get('calibration_sha256') != proof['calibration_sha256']
                or resolution.get('source_contract_sha256') != proof['source_contract_sha256']
                or resolution.get('projection_basis') != 'NAV_LOCALIZATION_CAPTURE_TO_PRIOR_ODOM_IMU_BASE'):
            raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
        for key, size in (('prior_id',32), ('original_observation_sha256',64)):
            if not isinstance(resolution.get(key), str) or not re.fullmatch(r'[a-f0-9]{%d}' % size, resolution[key]):
                raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
        accepted, prior_expiry = resolution.get('accepted_monotonic_s'), resolution.get('expires_monotonic_s')
        if (type(accepted) not in (int,float) or type(prior_expiry) not in (int,float)
                or not math.isfinite(accepted) or not math.isfinite(prior_expiry)
                or not 0 < prior_expiry-accepted <= 120. or accepted > time.monotonic() or deadline > prior_expiry):
            raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
        prior = resolution.get('operator_prior')
        if (not isinstance(prior, dict) or set(prior) != {'frame','pose_reference','units','pose','bounds','source',
                'stationary_current_pose_confirmed','navigation_map_id','navigation_map_revision','calibration_sha256'}
                or prior.get('frame') != 'map' or prior.get('pose_reference') != 'base_link'
                or prior.get('units') != 'metres_radians' or prior.get('source') != 'OPERATOR_CURRENT_MAP_DRAFT'
                or prior.get('stationary_current_pose_confirmed') is not True
                or prior.get('navigation_map_id') != proof['navigation_map_id']
                or prior.get('navigation_map_revision') != proof['navigation_map_revision']
                or prior.get('calibration_sha256') != proof['calibration_sha256']):
            raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
        prior_pose, prior_bounds = prior.get('pose'), prior.get('bounds')
        if (not isinstance(prior_pose, dict) or set(prior_pose) != {'x','y','yaw'}
                or not isinstance(prior_bounds, dict) or set(prior_bounds) != {'xy_m','yaw_rad'}
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in list(prior_pose.values())+list(prior_bounds.values()))
                or abs(prior_pose['x']) > 1000 or abs(prior_pose['y']) > 1000 or abs(prior_pose['yaw']) > math.pi
                or not .1 <= prior_bounds['xy_m'] <= 3. or not math.pi/180 <= prior_bounds['yaw_rad'] <= math.pi/2):
            raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
        if not _valid_prior_group(resolution, proof.get('operator_prior_current_members')):
            raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
        anchor_stamp = resolution.get('prior_anchor_stamp_ns')
        diagnostic = resolution.get('candidate_vs_prior')
        if (not isinstance(anchor_stamp,str) or not anchor_stamp.isdecimal() or int(anchor_stamp) <= 0
                or not isinstance(diagnostic,dict) or set(diagnostic) != {'xy_distance_m','absolute_wrapped_yaw_rad','within_existing_handoff_reference'}
                or any(type(diagnostic[k]) not in (int,float) or not math.isfinite(diagnostic[k]) or diagnostic[k] < 0
                       for k in ('xy_distance_m','absolute_wrapped_yaw_rad'))
                or diagnostic['xy_distance_m'] > MAX_XY_M or diagnostic['absolute_wrapped_yaw_rad'] > MAX_YAW_RAD
                or diagnostic['within_existing_handoff_reference'] is not True):
            raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
        if (resolution.get('navigation_2d',{}).get('map_id') != proof['navigation_map_id']
                or resolution.get('navigation_2d',{}).get('revision') != proof['navigation_map_revision']
                or resolution.get('localization_3d',{}).get('map_id') != proof['localization_map_id']
                or resolution.get('localization_3d',{}).get('revision') != proof['localization_map_revision']):
            raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
    elif resolution is not None or proof.get('operator_prior_current_members') is not None:
        raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
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
    if geometry['handoff']['policy_id'] == CONDITIONAL_POLICY_ID:
        prior = geometry['handoff']['operator_prior_resolution']['operator_prior']
        p, bounds = prior['pose'], prior['bounds']
        prior_angle = math.atan2(math.sin(yaw-p['yaw']), math.cos(yaw-p['yaw']))
        if math.hypot(x-p['x'], y-p['y']) > bounds['xy_m'] or abs(prior_angle) > bounds['yaw_rad']:
            raise ValueError('INITIAL_POSE_PRIOR_MISMATCH')
