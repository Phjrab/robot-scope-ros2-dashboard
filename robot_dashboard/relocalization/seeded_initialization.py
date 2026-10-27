"""Bounded local initialization through the existing isolated SE3 worker.

Search centre is an IMU prior, not a crop of LiDAR returns at robot radius.
No ROS output, global fallback, clamping or acceptance-threshold override.
"""
from __future__ import annotations

import copy
import math
import time

import numpy as np

from .experimental_se3 import MAX_CORRESPONDENCE_M, _rpy, from_translation_rpy, validate_transform
from .global_observation_jobs import GlobalObservationValidationError
from .observation_alignment import ObservationAlignmentError
from .observation_worker import RegistrationWorker

FIELDS = ('x', 'y', 'z', 'roll', 'pitch', 'yaw')
BOUNDS = {'xy_m': (.1, 3.), 'yaw_deg': (1., 90.), 'z_m': (.01, 1.), 'tilt_deg': (1., 30.)}


def validate_seed(value):
    def invalid():
        raise GlobalObservationValidationError('INVALID_LOCAL_SEED')
    if not isinstance(value, dict) or set(value) != {
        'revision', 'pose', 'pose_reference', 'units', 'map_frame', 'height_source', 'bounds', 'source_contract'
    }:
        invalid()
    if (type(value['revision']) is not int or not 1 <= value['revision'] <= 9_007_199_254_740_991
            or value['pose_reference'] != 'FASTLIO_IMU' or value['units'] != 'metres_degrees'
            or not isinstance(value['map_frame'], str) or not 0 < len(value['map_frame']) <= 80
            or value['height_source'] not in {'preserved_prior', 'active_imu', 'approximate', 'manual'}
            or not isinstance(value['source_contract'], dict)):
        invalid()
    pose, bounds = value['pose'], value['bounds']
    if not isinstance(pose, dict) or set(pose) != set(FIELDS) or not isinstance(bounds, dict) or set(bounds) != set(BOUNDS):
        invalid()
    for key, n in pose.items():
        limit = 1000 if key in FIELDS[:3] else 360
        if type(n) not in (int, float) or not math.isfinite(n) or abs(n) > limit:
            invalid()
    for key, (low, high) in BOUNDS.items():
        n = bounds[key]
        if type(n) not in (int, float) or not math.isfinite(n) or not low <= n <= high:
            invalid()
    return copy.deepcopy(value)


def seed_matrix(seed):
    p = seed['pose']
    return from_translation_rpy([p[k] for k in FIELDS[:3]], [math.radians(p[k]) for k in FIELDS[3:]])


def prior_delta(initial, candidate):
    a, b = validate_transform(initial), validate_transform(candidate)
    angles = _rpy(a[:3, :3]), _rpy(b[:3, :3])
    delta = [abs(math.degrees(math.atan2(math.sin(y-x), math.cos(y-x)))) for x, y in zip(*angles)]
    return dict(xy_m=float(np.linalg.norm(b[:2, 3]-a[:2, 3])), z_m=float(abs(b[2, 3]-a[2, 3])),
                yaw_deg=delta[2], tilt_deg=max(delta[:2]))


def run_seeded_arrays(*, scan_bytes, map_bytes, context, cancel_event, timeout_s):
    """Reuse ReferenceIndex/prepare_seed/register_se3 in RegistrationWorker."""
    started = time.monotonic()
    points = np.frombuffer(scan_bytes, dtype='<f8').reshape(-1, 3)
    reference = np.frombuffer(map_bytes, dtype='<f8').reshape(-1, 3)
    if not 60 <= len(points) <= 4000 or not np.isfinite(points).all():
        raise ObservationAlignmentError('LOCAL_QUERY_POINT_LIMIT_60_TO_4000')
    initial = validate_transform(context['T_map_imu_seed_capture'])
    bounds = context['seed']['bounds']
    # Every point reachable from any allowed IMU centre remains in the target.
    # Its extent is the full scan footprint + centre allowance + ICP gate.
    radius = float(np.linalg.norm(points, axis=1).max()) + math.hypot(bounds['xy_m'], bounds['z_m']) + MAX_CORRESPONDENCE_M
    selected = np.linalg.norm(reference-initial[:3, 3], axis=1) <= radius
    target = reference[selected].copy()
    if not 60 <= len(target) <= 100_000:
        raise ObservationAlignmentError('LOCAL_REFERENCE_POINT_LIMIT_60_TO_100000')
    worker = RegistrationWorker()
    try:
        result, transform = worker.solve(
            (context['map_id'], context['map_revision'], context['seed']['revision']), target,
            context['map_frame'], points, 'body', int(context['source_stamp_ns']), initial,
            started + timeout_s, cancel_event=cancel_event)
    finally:
        worker.close()
    delta = prior_delta(initial, transform)
    within = all(delta[k] <= bounds[k] + 1e-8 for k in BOUNDS)
    accepted = result['status'] == 'CANDIDATE' and within
    return dict(schema='robot-scope.seeded-local-result.v1', search_mode='seeded_local',
                status='CANDIDATE' if accepted else 'REJECTED',
                reason=('OUTSIDE_SEED_BOUNDS' if not within else result['reason']), admissible=accepted,
                seed_revision=context['seed']['revision'], map_from_scan=transform.tolist(),
                initial_map_from_scan=initial.tolist(), delta=delta, bounds=bounds,
                numerical=result, ambiguity_unresolved=True, hypotheses_tested=1,
                search_method='single-seed-coarse-to-fine',
                evaluation_scope='FULL_CAPTURE_AGAINST_PRIOR_REACHABLE_SCAN_FOOTPRINT',
                scan_points=len(points), reference_points=len(target), full_map_points=len(reference),
                target_radius_m=radius, runtime_ms=(time.monotonic()-started)*1000,
                operational_application='NOT_RUN', absolute_accuracy_m=None)
