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

from ..relocalization.experimental_se3 import inverse, validate_transform
from ..relocalization.external_global_observation import ExternalGlobalObservationRunner
from ..relocalization.handoff_policy import MAX_XY_M, MAX_YAW_RAD
from ..relocalization.operational import display_pose
from ..relocalization.v031_observation_compat import SELECTION_POLICY, _ambiguity_eligible


class PriorRejected(ValueError):
    pass


def validate_prior(prior):
    if type(prior) is not dict or set(prior) != {'frame', 'pose_reference', 'units', 'pose', 'bounds', 'source',
            'stationary_current_pose_confirmed', 'navigation_map_id', 'navigation_map_revision', 'calibration_sha256'}:
        raise PriorRejected('PRIOR_INVALID')
    if ((prior['frame'], prior['pose_reference'], prior['units'], prior['source']) !=
            ('map', 'base_link', 'metres_radians', 'OPERATOR_CURRENT_MAP_DRAFT')
            or prior['stationary_current_pose_confirmed'] is not True):
        raise PriorRejected('PRIOR_INVALID')
    pose, bounds = prior['pose'], prior['bounds']
    if type(pose) is not dict or set(pose) != {'x', 'y', 'yaw'} or type(bounds) is not dict or set(bounds) != {'xy_m', 'yaw_rad'}:
        raise PriorRejected('PRIOR_INVALID')
    for value in list(pose.values()) + list(bounds.values()):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise PriorRejected('PRIOR_INVALID')
    if (abs(pose['x']) > 1000 or abs(pose['y']) > 1000 or abs(pose['yaw']) > math.pi
            or not .1 <= bounds['xy_m'] <= 3. or not math.pi / 180 <= bounds['yaw_rad'] <= math.pi / 2):
        raise PriorRejected('PRIOR_INVALID')
    for key, length in (('navigation_map_id', 24), ('navigation_map_revision', 64), ('calibration_sha256', 64)):
        if type(prior[key]) is not str or not re.fullmatch('[a-f0-9]{%d}' % length, prior[key]):
            raise PriorRejected('PRIOR_INVALID')
    return deepcopy(prior)


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
    matches, eligible = [], 0
    for index, candidate in enumerate(observation['candidates']):
        gates = candidate['gate_reasons']
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
            continue
        if ((top_gates and gates != ['AMBIGUOUS_ALTERNATIVES']) or (not top_gates and gates)
                or not _ambiguity_eligible({**candidate, 'gate_reasons': ['AMBIGUOUS_ALTERNATIVES']})
                or candidate.get('scan_count') != n):
            raise PriorRejected('CANDIDATE_QUALITY_UNAVAILABLE')
        eligible += 1
        p = display_pose(nav @ validate_transform(candidate['map_from_scan']) @ capture_inverse @ prior_imu @ body)
        q, bounds = prior['pose'], prior['bounds']
        angle = abs(math.atan2(math.sin(p['yaw'] - q['yaw']), math.cos(p['yaw'] - q['yaw'])))
        distance = math.hypot(p['x'] - q['x'], p['y'] - q['y'])
        if distance <= bounds['xy_m'] and angle <= bounds['yaw_rad']:
            matches.append((index, distance, angle))
    if len(matches) != 1:
        raise PriorRejected('PRIOR_NO_MATCH' if not matches else 'PRIOR_MULTIPLE_MATCHES')
    index, distance, angle = matches[0]
    return {'candidate_index': index, 'classification': 'CONDITIONAL_ON_OPERATOR_PRIOR',
            'retained_candidate_count': retention['count'], 'eligible_candidate_count': eligible,
            'matching_candidate_count': 1, 'original_ambiguity_preserved': True,
            'original_ambiguity_unresolved': bool(top_gates),
            'candidate_vs_prior': {'xy_distance_m': distance, 'absolute_wrapped_yaw_rad': angle,
                'within_existing_handoff_reference': distance <= MAX_XY_M and angle <= MAX_YAW_RAD},
            'global_uniqueness_verified': False, 'absolute_accuracy_m': None}
