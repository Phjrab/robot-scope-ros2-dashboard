"""Conditional comparison of the pinned backend's retained candidate set.

This is not global uniqueness, measured accuracy, or a command authorization.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from copy import deepcopy

import numpy as np

from ..relocalization.experimental_se3 import inverse, validate_transform
from ..relocalization.external_global_observation import ExternalGlobalObservationRunner
from ..relocalization.handoff_policy import GROUPING_POLICY, MAX_XY_M, MAX_YAW_RAD, prior_bounds_policy
from ..relocalization.operational import display_pose
from ..relocalization.v031_observation_compat import SELECTION_POLICY, _ambiguity_eligible


class PriorRejected(ValueError):
    pass


# These are the defaults of the hash-pinned v031 SE3Config used by this
# worker, not a new clustering policy. Preserve its first-representative order.
_PINNED_DUPLICATE_TRANSLATION_M = .10
_PINNED_DUPLICATE_ROTATION_RAD = .05


def _pinned_duplicate(first, other):
    relative = first[:3, :3].T @ other[:3, :3]
    angle = np.arccos(np.clip((np.trace(relative) - 1) / 2, -1, 1))
    return (np.linalg.norm(first[:3, 3] - other[:3, 3]) <= _PINNED_DUPLICATE_TRANSLATION_M
            and angle <= _PINNED_DUPLICATE_ROTATION_RAD)


def validate_prior(prior):
    required = {'frame', 'pose_reference', 'units', 'pose', 'source',
            'stationary_current_pose_confirmed', 'navigation_map_id', 'navigation_map_revision', 'calibration_sha256'}
    if type(prior) is not dict or set(prior) not in (required, required | {'bounds'}):
        raise PriorRejected('PRIOR_INVALID')
    if ((prior['frame'], prior['pose_reference'], prior['units'], prior['source']) !=
            ('map', 'base_link', 'metres_radians', 'OPERATOR_CURRENT_MAP_DRAFT')
            or prior['stationary_current_pose_confirmed'] is not True):
        raise PriorRejected('PRIOR_INVALID')
    pose, bounds = prior['pose'], prior.get('bounds')
    if (type(pose) is not dict or set(pose) != {'x', 'y', 'yaw'}
            or (bounds is not None and (type(bounds) is not dict or set(bounds) != {'xy_m', 'yaw_rad'}))):
        raise PriorRejected('PRIOR_INVALID')
    for value in list(pose.values()) + (list(bounds.values()) if bounds is not None else []):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise PriorRejected('PRIOR_INVALID')
    if (abs(pose['x']) > 1000 or abs(pose['y']) > 1000 or abs(pose['yaw']) > math.pi
            or (bounds is not None and (not .1 <= bounds['xy_m'] <= 3.
                                       or not math.pi / 180 <= bounds['yaw_rad'] <= math.pi / 2))):
        raise PriorRejected('PRIOR_INVALID')
    for key, length in (('navigation_map_id', 24), ('navigation_map_revision', 64), ('calibration_sha256', 64)):
        if type(prior[key]) is not str or not re.fullmatch('[a-f0-9]{%d}' % length, prior[key]):
            raise PriorRejected('PRIOR_INVALID')
    normalized = deepcopy(prior)
    if bounds is None:
        normalized.pop('bounds', None)
    return normalized


def retained_candidate_digest(observation):
    try:
        candidates = observation['candidates']
        if type(candidates) is not list or not 6 <= len(candidates) <= 18:
            raise PriorRejected('CANDIDATE_RETENTION_UNCONFIRMED')
        attempts = [c.get('attempt') if type(c) is dict else None for c in candidates]
        if (any(type(x) is not int or not 0 <= x < 6 for x in attempts)
                or set(attempts) != set(range(6)) or any(n > 3 for n in Counter(attempts).values())):
            raise PriorRejected('CANDIDATE_RETENTION_UNCONFIRMED')
        encoded = json.dumps(candidates, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        return {'schema': 'robot-scope.retained-candidates.v1', 'count': len(candidates),
                'attempts': sorted(set(attempts)), 'sha256': hashlib.sha256(encoded).hexdigest(),
                'scope': 'PINNED_V031_RETAINED_SUBSET_NOT_GLOBAL_EXHAUSTIVE'}
    except (KeyError, TypeError, ValueError) as exc:
        raise PriorRejected('CANDIDATE_RETENTION_UNCONFIRMED') from exc


def select_candidates(observation, context, prior, *, nav_from_localization, odom_from_imu_at_prior,
                      imu_from_base, allow_ambiguous):
    prior = validate_prior(prior)
    bounds_source, bounds = prior_bounds_policy(prior)
    ExternalGlobalObservationRunner._validate_result(observation, context, allow_ambiguous=allow_ambiguous)
    top_gates = observation.get('gate_reasons')
    if (observation.get('selection_policy') != SELECTION_POLICY
            or top_gates not in ([], ['AMBIGUOUS_ALTERNATIVES'])):
        raise PriorRejected('UNSUPPORTED_CANDIDATE_SET')
    retention = retained_candidate_digest(observation)
    if observation.get('candidate_retention') != retention:
        raise PriorRejected('CANDIDATE_RETENTION_UNCONFIRMED')
    n = context['scan']['point_count']
    nav = validate_transform(nav_from_localization)
    prior_imu = validate_transform(odom_from_imu_at_prior)
    body = validate_transform(imu_from_base)
    capture_inverse = inverse(validate_transform(context['anchor_capture']['T_odom_imu']))
    eligible_candidates = []
    for index, candidate in enumerate(observation['candidates']):
        gates = candidate['gate_reasons']
        if ('duplicate_of' not in candidate or
                (candidate['duplicate_of'] is not None and type(candidate['duplicate_of']) is not int)):
            raise PriorRejected('CANDIDATE_DUPLICATE_INVALID')
        known_rejections = {'INVALID_SE3', 'FEWER_THAN_60_DISTINCT_INLIER_VOXELS',
            'DEGENERATE_INLIER_GEOMETRY', 'DEGENERATE_GEOMETRY', 'OVERLAP_BELOW_0.60',
            'FEWER_THAN_60_INLIERS', 'FAILED_RANSAC', 'REFINEMENT_NOT_STATIONARY'}
        if any(type(reason) is not str or not reason or not
                (reason in known_rejections or reason == 'AMBIGUOUS_ALTERNATIVES'
                 or re.fullmatch(r'REGISTRATION_ERROR:(RuntimeError|ValueError):.*', reason)) for reason in gates):
            raise PriorRejected('CANDIDATE_QUALITY_UNAVAILABLE')
        if gates not in ([], ['AMBIGUOUS_ALTERNATIVES']):
            if 'AMBIGUOUS_ALTERNATIVES' in gates:
                raise PriorRejected('CANDIDATE_QUALITY_UNAVAILABLE')
            if candidate['duplicate_of'] is not None:
                raise PriorRejected('CANDIDATE_DUPLICATE_INVALID')
            continue
        if ((top_gates and gates != ['AMBIGUOUS_ALTERNATIVES']) or (not top_gates and gates)
                or not _ambiguity_eligible({**candidate, 'gate_reasons': ['AMBIGUOUS_ALTERNATIVES']})
                or candidate.get('scan_count') != n):
            raise PriorRejected('CANDIDATE_QUALITY_UNAVAILABLE')
        matrix = validate_transform(candidate['map_from_scan'])
        p = display_pose(nav @ matrix @ capture_inverse @ prior_imu @ body)
        q = prior['pose']
        angle = abs(math.atan2(math.sin(p['yaw'] - q['yaw']), math.cos(p['yaw'] - q['yaw'])))
        distance = math.hypot(p['x'] - q['x'], p['y'] - q['y'])
        eligible_candidates.append((index, candidate['duplicate_of'], matrix, distance, angle,
                                    distance <= bounds['xy_m'] and angle <= bounds['yaw_rad'], p))
    # Replay _finish's accepted-representative search in original order, then
    # require every member of each verified group to agree on prior membership.
    representatives = []
    matches = []
    matched_retained = 0
    matching_members = []
    for index, marker, matrix, distance, angle, inside, p in eligible_candidates:
        representative = next((item for item in representatives if _pinned_duplicate(item[1], matrix)), None)
        if marker != (representative[0] if representative is not None else None):
            raise PriorRejected('CANDIDATE_DUPLICATE_INVALID')
        if representative is not None:
            if inside != representative[2]:
                raise PriorRejected('PRIOR_DUPLICATE_BOUNDARY')
        else:
            representatives.append((index, matrix, inside))
            if inside:
                matches.append((index, distance, angle))
        if inside:
            matched_retained += 1
            matching_members.append((index, p))
    if len(matches) != 1:
        raise PriorRejected('PRIOR_NO_MATCH' if not matches else 'PRIOR_MULTIPLE_MATCHES')
    index, distance, angle = matches[0]
    representative_pose = matching_members[0][1]
    def delta(a, b):
        return math.atan2(math.sin(a-b), math.cos(a-b))
    geometry = [{'candidate_index': i, 'z_m': p['z'], 'roll_rad': p['roll'], 'pitch_rad': p['pitch'],
                 'z_delta_m': p['z']-representative_pose['z'],
                 'roll_delta_rad': delta(p['roll'],representative_pose['roll']),
                 'pitch_delta_rad': delta(p['pitch'],representative_pose['pitch'])}
                for i, p in matching_members]
    return {'candidate_index': index, 'classification': 'CONDITIONAL_ON_OPERATOR_PRIOR',
            'bounds_source': bounds_source, 'effective_bounds': bounds,
            'retained_candidate_count': retention['count'], 'eligible_candidate_count': len(eligible_candidates),
            'grouping_policy': GROUPING_POLICY, 'matching_candidate_count': matched_retained,
            'matching_hypothesis_count': 1, 'matching_retained_candidate_count': matched_retained,
            'matching_member_indices': [i for i, _ in matching_members], 'matching_member_geometry': geometry,
            'verified_duplicate_count': len(eligible_candidates) - len(representatives),
            'original_ambiguity_preserved': True,
            'original_ambiguity_unresolved': bool(top_gates),
            'candidate_vs_prior': {'xy_distance_m': distance, 'absolute_wrapped_yaw_rad': angle,
                'within_existing_handoff_reference': distance <= MAX_XY_M and angle <= MAX_YAW_RAD},
            'global_uniqueness_verified': False, 'absolute_accuracy_m': None}
