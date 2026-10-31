"""Stored-map localization used by the existing Nav2 transform owner.

The browser supplies a seed, never a tracking result. Registered FAST-LIO
points are already in O (camera_init). Their fit is T_M_O, not T_M_I.
Only the ROS executor commits results; the bounded worker never publishes.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np

from ..pcd_editing.pcd import _read_header, DEFAULT_MAX_POINTS, DEFAULT_MAX_BYTES
from ..pcd_editing.geometry import _compile_region, _selection_mask, validate_regions
from .experimental_se3 import (
    from_translation_quaternion, from_translation_rpy, inverse, matrix_to_quaternion_xyzw,
    rotation_error_rad, transform_points, validate_transform,
)
from .observation_alignment import ReferenceIndex, solve_prepared
from .directional_weighting import CANDIDATE, DirectionalFrame, SurfaceSupport, sector_counts, validate_weighting


SCHEMA = "robot-scope.operational-3d-bundle.v1"
STAGED_WORKFLOW = 'staged_navigation_pair'
MATCH_TOPIC = '/robot_scope/nav/operational_match'

# A fresh stationary Navigation click is a rough seed, not a tracking result.
# These bounds apply only before the first correction, never during tracking.
INITIAL_REFINEMENT_M = .5
INITIAL_REFINEMENT_RAD = .3
INITIAL_CONFIRMATIONS = 3
INITIAL_CONSISTENCY_M = .05
INITIAL_CONSISTENCY_RAD = .05


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def read_reference(path, expected_hash):
    """Read complete PCD records, then bound the numerical reference to 100k."""
    path = Path(path)
    if path.is_symlink() or not 0 < path.stat().st_size <= DEFAULT_MAX_BYTES:
        raise ValueError('REFERENCE_FILE_INVALID')
    with path.open('rb') as stream:
        before = path.stat()
        _, header, dtype, count, _ = _read_header(stream, before.st_size, DEFAULT_MAX_POINTS)
        data = stream.read(DEFAULT_MAX_BYTES + 1)
    if hashlib.sha256(header + data).hexdigest() != expected_hash:
        raise ValueError('REFERENCE_HASH_CHANGED')
    records = np.frombuffer(data, dtype=dtype, count=count)
    # This is estimator downsampling of the whole file, not a UI preview.
    records = records[::max(1, math.ceil(count / 100_000))]
    points = np.column_stack([records[k] for k in ('x', 'y', 'z')]).astype(float)
    points = points[np.isfinite(points).all(axis=1)]
    if len(points) < 60:
        raise ValueError('REFERENCE_TOO_SMALL')
    return points, count


def pose_matrix(message):
    p, q = message.pose.pose.position, message.pose.pose.orientation
    quaternion = np.array([q.x, q.y, q.z, q.w], dtype=float)
    norm = np.linalg.norm(quaternion)
    if not np.isfinite(norm) or abs(norm - 1) > .01:
        raise ValueError('INVALID_ODOMETRY_QUATERNION')
    return from_translation_quaternion([p.x, p.y, p.z], quaternion / norm)


def write_pose(pose, transform):
    pose.position.x, pose.position.y, pose.position.z = map(float, transform[:3, 3])
    q = matrix_to_quaternion_xyzw(transform[:3, :3])
    pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w = q


def write_transform(message, transform):
    message.transform.translation.x, message.transform.translation.y, message.transform.translation.z = map(float, transform[:3, 3])
    q = matrix_to_quaternion_xyzw(transform[:3, :3])
    message.transform.rotation.x, message.transform.rotation.y, message.transform.rotation.z, message.transform.rotation.w = q


def display_pose(transform):
    """Full body pose for display only; it is never localization evidence."""
    matrix = validate_transform(transform)
    return {'x': float(matrix[0, 3]), 'y': float(matrix[1, 3]), 'z': float(matrix[2, 3]),
            'roll': math.atan2(matrix[2, 1], matrix[2, 2]),
            'pitch': math.asin(float(np.clip(-matrix[2, 0], -1., 1.))),
            'yaw': math.atan2(matrix[1, 0], matrix[0, 0])}


def validate_seed_geometry(value):
    if (not isinstance(value, dict) or value.get('frame') != 'map'
            or value.get('source') != 'operator'):
        raise ValueError('INITIAL_HEIGHT_TILT_REQUIRED')
    for key, bound in (('z', 10_000.), ('roll', math.pi), ('pitch', math.pi)):
        number = value.get(key)
        if type(number) not in (int, float) or not math.isfinite(number) or abs(number) > bound:
            raise ValueError('INITIAL_HEIGHT_TILT_REQUIRED')
    confirmed = value.get('confirmed_at')
    if type(confirmed) not in (int, float) or not math.isfinite(confirmed) or confirmed <= 0:
        raise ValueError('INITIAL_GEOMETRY_PROVENANCE_REQUIRED')
    return value


def validate_bundle(bundle):
    if bundle.get('schema') != SCHEMA:
        raise ValueError('INVALID_MAP_BUNDLE_SCHEMA')
    for name in ('localization_3d', 'navigation_2d'):
        pin = bundle[name]
        if not pin.get('map_id') or len(pin.get('revision', '')) != 64:
            raise ValueError('INVALID_MAP_PIN')
    if bundle['localization_3d'].get('units') != 'm' or bundle['navigation_2d']['frame'] != 'map':
        raise ValueError('INVALID_MAP_FRAMES')
    calibration = bundle['calibration']
    reference = bundle['localization_3d']
    root = reference.get('lineage') or {
        'map_id': reference['map_id'], 'revision': reference['revision'],
        'sha256': reference['sha256'], 'frame_id': reference['frame'], 'units': reference['units']}
    root_pin = {key: root[key] for key in ('map_id', 'revision', 'sha256', 'frame_id', 'units')}
    if (calibration.get('localization_root') != root_pin
            or root_pin['frame_id'] != reference['frame'] or root_pin['units'] != reference['units']):
        raise ValueError('CALIBRATION_LOCALIZATION_ROOT_MISMATCH')
    if not calibration.get('evidence') or calibration.get('verified') is not True:
        raise ValueError('BODY_AND_MAP_CALIBRATION_REQUIRED')
    for key in ('T_nav_map_from_localization_map', 'T_imu_base'):
        validate_transform(calibration[key])
    seed = bundle.get('seed_T_map_imu')
    if seed is None:
        if bundle.get('workflow') != STAGED_WORKFLOW:
            raise ValueError('INITIAL_SEED_REQUIRED')
        if bundle.get('seed_geometry') is not None:
            validate_seed_geometry(bundle['seed_geometry'])
    else:
        validate_transform(seed)
    policy = bundle['policy']
    for key, low, high in (('max_rmse_m', .01, .5), ('max_correction_age_s', .3, 3.),
                           ('max_translation_step_m', .01, .5), ('max_rotation_step_rad', .01, .3),
                           ('compute_budget_s', .05, 1.), ('max_propagation_m', .05, 1.)):
        value = policy[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('INVALID_OPERATIONAL_QUALITY_POLICY')
    if not policy.get('evidence'):
        raise ValueError('QUALITY_POLICY_EVIDENCE_REQUIRED')
    validate_weighting(policy.get('directional_weighting'))
    return bundle


def load_bundle(params_path):
    """A private per-job snapshot, made before Nav2 starts; no hot file switch."""
    if params_path is None:
        return None
    path = Path(params_path).parent / 'operational-3d.json'
    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size > 128 * 1024:
        raise ValueError('INVALID_MAP_BUNDLE_FILE')
    bundle = validate_bundle(json.loads(path.read_text()))
    result = OperationalLocalizer(bundle, path.parent / 'localization-reference.pcd')
    # A staged click is not authority to initialize a later process. The normal
    # /initialpose path confirms it only after fresh observed stop evidence.
    result.seed = None
    result.reason = 'WAITING_EXPLICIT_INITIAL_POSE'
    return result


class OperationalLocalizer:
    def __init__(self, bundle, reference_path, *, clock=time.monotonic):
        self.bundle = validate_bundle(bundle)
        self.clock = clock
        self.reference, self.full_count = read_reference(reference_path, bundle['localization_3d']['sha256'])
        self.index = ReferenceIndex(self.reference)
        self.weighting = validate_weighting(bundle['policy'].get('directional_weighting'))
        self.surface_support = SurfaceSupport(self.index) if self.weighting['mode'] == CANDIDATE else None
        self.directional_state = None
        self.exclusions = []
        for entry in bundle['localization_3d'].get('edit_history', []):
            if entry['purpose'] != 'localization':
                continue
            annotation = entry['annotation']
            if annotation['source']['frame_id'] != bundle['localization_3d']['frame']:
                raise ValueError('LOCALIZATION_EXCLUSION_FRAME_MISMATCH')
            self.exclusions.extend(_compile_region(region) for region in
                validate_regions(annotation['regions']) if region['kind'] == 'localization')
        self.imu_base = validate_transform(bundle['calibration']['T_imu_base'])
        self.nav_map = validate_transform(bundle['calibration']['T_nav_map_from_localization_map'])
        self.seed = (validate_transform(bundle['seed_T_map_imu'])
                     if bundle.get('seed_T_map_imu') is not None else None)
        self.match_armed = bundle.get('workflow') != STAGED_WORKFLOW
        self.match_receipt = None
        self.accepted_initial_pose = None
        self.last_estimated_pose = None
        self.last_estimated_receipt = None
        self.correction = None
        self.sequence = 0
        self.generation = 1
        self.last_accepted_receipt = None
        self.last_accepted_stamp = 0
        self.last_submitted_stamp = 0
        self.accepted_odom = None
        self.current_odom = None
        self.last_pose_stamp = 0
        self.last_pose_receipt = None
        self.stopped_since = None
        self.speed = None
        self.yaw_rate = None
        self.body_velocity = None
        self.metrics = {}
        self.initial_pose_receipt = None
        self.initializing = False
        self.initial_candidates = []
        self.reason = 'WAITING_EXACT_STAMP_PAIR'
        self.future = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='stored-map-fit')
        self.last_submit_time = -math.inf

    def invalidate(self, reason):
        self.generation += 1
        self.directional_state = None
        self.correction = None
        self.seed = None
        self.stopped_since = None
        self.initializing = False
        self.initial_candidates = []
        self.match_armed = False
        self.accepted_initial_pose = None
        self.last_estimated_pose = None
        self.last_estimated_receipt = None
        self.match_receipt = None
        self.reason = reason

    def reseed(self, nav_base, *, stamp_ns=None):
        if self.current_odom is None or self.stopped_seconds() < 2.:
            raise ValueError('RESEED_REQUIRES_OBSERVED_STOP')
        # A fresh, explicit Nav2 click updates body XY/heading. Keep the staged
        # body height and tilt; then recover the IMU seed through both calibrated
        # transforms. This also handles non-identity map/body calibrations.
        requested = validate_transform(nav_base)
        requested_yaw = math.atan2(requested[1, 0], requested[0, 0])
        if self.bundle.get('workflow') == STAGED_WORKFLOW:
            geometry = validate_seed_geometry(self.bundle.get('seed_geometry'))
            staged_body = from_translation_rpy(
                [requested[0, 3], requested[1, 3], geometry['z']],
                [geometry['roll'], geometry['pitch'], requested_yaw])
        else:
            staged = validate_transform(self.bundle['seed_T_map_imu'])
            staged_body = self.nav_map @ staged @ self.imu_base
            staged_yaw = math.atan2(staged_body[1, 0], staged_body[0, 0])
            delta = requested_yaw - staged_yaw
            c, s = math.cos(delta), math.sin(delta)
            staged_body[:3, :3] = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]]) @ staged_body[:3, :3]
            staged_body[:2, 3] = requested[:2, 3]
        seed = inverse(self.nav_map) @ staged_body @ inverse(self.imu_base)
        stopped_since = self.stopped_since
        self.invalidate('WAITING_MAP_CORRECTION')
        # Preserve the already observed dwell only for this explicit reseed.
        self.stopped_since = stopped_since
        self.seed = validate_transform(seed)
        self.initializing = True
        self.match_armed = self.bundle.get('workflow') != STAGED_WORKFLOW
        if not self.match_armed:
            self.reason = 'WAITING_EXPLICIT_MAP_MATCH'
        if stamp_ns is not None:
            self.accepted_initial_pose = {
                **self.pose_context(), 'accepted': True, 'source': 'USER_INITIAL_POSE',
                'stamp_ns': str(stamp_ns), 'pose': display_pose(staged_body),
                'geometry_source': ('operator' if self.bundle.get('workflow') == STAGED_WORKFLOW
                                    else 'staged_3d_seed'),
            }

    def pose_context(self):
        return {'bundle_generation': self.bundle['generation'],
                'localization_generation': self.generation,
                'map_id': self.bundle['navigation_2d']['map_id'],
                'map_revision': self.bundle['navigation_2d']['revision'],
                'localization_map_id': self.bundle['localization_3d']['map_id'],
                'localization_map_revision': self.bundle['localization_3d']['revision']}

    def start_matching(self, initial_pose_stamp_ns):
        if self.bundle.get('workflow') != STAGED_WORKFLOW:
            raise ValueError('EXPLICIT_MATCH_WORKFLOW_REQUIRED')
        if (self.seed is None or self.accepted_initial_pose is None
                or self.accepted_initial_pose['stamp_ns'] != str(initial_pose_stamp_ns)):
            raise ValueError('CURRENT_INITIAL_POSE_REQUIRED')
        if self.stopped_seconds() < 2.:
            raise ValueError('RESEED_REQUIRES_OBSERVED_STOP')
        if self.match_armed:
            raise ValueError('MAP_MATCH_ALREADY_STARTED')
        self.match_armed = True
        self.reason = 'WAITING_MAP_CORRECTION'

    def observe_odometry(self, stamp, odom_imu, receipt=None):
        now = self.clock() if receipt is None else receipt
        body = validate_transform(odom_imu) @ self.imu_base
        if self.current_odom is not None:
            dt = (stamp - self.last_pose_stamp) * 1e-9
            if not 0 < dt <= .5 or self.last_pose_receipt is None or not 0 <= now - self.last_pose_receipt <= .5:
                self.invalidate('ODOMETRY_GENERATION_CHANGED')
                self.speed = self.yaw_rate = None
                self.body_velocity = None
            else:
                previous = self.current_odom @ self.imu_base
                linear = body[:3, :3].T @ (body[:3, 3] - previous[:3, 3]) / dt
                rotation = previous[:3, :3].T @ body[:3, :3]
                quaternion = np.asarray(matrix_to_quaternion_xyzw(rotation))
                length = np.linalg.norm(quaternion[:3])
                angular_previous = (quaternion[:3] * (2 * math.atan2(length, quaternion[3]) / length / dt)
                                    if length > 1e-12 else np.zeros(3))
                angular = rotation.T @ angular_previous
                self.body_velocity = (tuple(float(v) for v in linear), tuple(float(v) for v in angular))
                self.speed = float(np.linalg.norm(body[:3, 3] - previous[:3, 3]) / dt)
                self.yaw_rate = rotation_error_rad(body, previous) / dt
                if self.speed > 3. or self.yaw_rate > 4.:
                    self.invalidate('ODOMETRY_JUMP')
                if self.speed <= .03 and self.yaw_rate <= .05:
                    if self.stopped_since is None:
                        self.stopped_since = now
                else:
                    self.stopped_since = None
        self.current_odom = odom_imu.copy()
        self.last_pose_stamp, self.last_pose_receipt = stamp, now
        return body

    def stopped_seconds(self):
        now = self.clock()
        if self.last_pose_receipt is None or not 0 <= now - self.last_pose_receipt <= .5 or self.stopped_since is None:
            return 0.
        return max(0., now - self.stopped_since)

    def submit(self, points, stamp, odom_at_stamp, receipt):
        now = self.clock()
        if self.future is not None or now - self.last_submit_time < .5 or stamp <= self.last_submitted_stamp:
            return False
        if not 0 <= now - receipt <= .5 or self.seed is None or not self.match_armed:
            return False
        query = np.asarray(points, dtype=float)
        query = query[np.isfinite(query).all(axis=1)]
        query = query[::max(1, math.ceil(len(query) / 1024))].copy()
        if len(query) < 60:
            self.reason = 'INSUFFICIENT_REGISTERED_POINTS'
            return False
        initial = self.correction.copy() if self.correction is not None else self.seed @ inverse(odom_at_stamp)
        token = self.generation
        deadline = now + self.bundle['policy']['compute_budget_s']
        directional_state = self.directional_state
        def solve():
            selected = query
            if self.exclusions:
                # The stored reference has already had these map-frame points
                # removed. Apply the same immutable edit to this estimator's
                # query, using the last accepted correction / explicit seed.
                # Raw clouds and the independent Nav2 scan path are untouched.
                mapped = transform_points(initial, query)
                excluded = np.zeros(len(query), dtype=bool)
                for region in self.exclusions:
                    excluded |= _selection_mask(*mapped.T, region)
                selected = query[~excluded]
                if len(selected) < 60:
                    raise ValueError('INSUFFICIENT_LOCALIZATION_POINTS_AFTER_EXCLUSION')
            weighting = None
            if self.surface_support is not None:
                weighting = DirectionalFrame(self.weighting, self.surface_support, selected,
                    odom_at_stamp @ self.imu_base, stamp, directional_state, deadline,
                    frame_verified=self.bundle['calibration']['verified'])
            result, transform = solve_prepared(self.reference, self.index,
                self.bundle['localization_3d']['frame'], selected, 'camera_init', stamp,
                initial, deadline, course_region=self.bundle.get('course_region'), enforce_residual_limit=False,
                **({'query_weighting': weighting} if weighting is not None else {}))
            if weighting is not None:
                result['_directional_state'] = weighting.next_state
            result['metrics']['registered_input_points'] = len(query)
            result['metrics']['localization_selected_points'] = len(selected)
            result['metrics']['localization_excluded_points'] = len(query) - len(selected)
            # Physical sectors use body heading at this exact source stamp.
            body = odom_at_stamp @ self.imu_base
            result['metrics']['body_sectors'] = sector_counts(selected, body)
            result['metrics']['body_sector_basis'] = 'FULL_EXACT_STAMP_BODY_AXES_NOT_TRAVEL_DIRECTION'
            result['metrics']['body_pitch_rad'] = math.asin(float(np.clip(-body[2, 0], -1, 1)))
            return token, stamp, receipt, odom_at_stamp.copy(), result, transform
        self.future = self.pool.submit(solve)
        self.last_submit_time, self.last_submitted_stamp = now, stamp
        return True

    def poll(self):
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        try:
            token, stamp, receipt, odom, result, transform = future.result()
        except Exception as exc:
            self.initial_candidates = []
            self.reason = str(exc)[:120] or 'REGISTRATION_FAILED'
            return
        if token != self.generation:
            return
        if '_directional_state' in result:
            self.directional_state = result.pop('_directional_state')
        self.metrics = result['metrics']
        policy = self.bundle['policy']
        if not 0 <= self.clock() - receipt <= policy['max_correction_age_s']:
            self.initial_candidates = []
            self.reason = 'CORRECTION_EXPIRED_BEFORE_APPLY'
            return
        if result['status'] != 'CANDIDATE' or self.metrics['rmse_m'] > policy['max_rmse_m']:
            self.initial_candidates = []
            self.reason = result['reason'] if result['status'] != 'CANDIDATE' else 'OPERATIONAL_RESIDUAL_LIMIT'
            return
        prior = self.correction if self.correction is not None else self.seed @ inverse(odom)
        before, after = prior @ odom @ self.imu_base, transform @ odom @ self.imu_base
        translation_step = float(np.linalg.norm(after[:3, 3] - before[:3, 3]))
        rotation_step = rotation_error_rad(after, before)
        self.metrics.update(correction_translation_m=translation_step, correction_rotation_rad=rotation_step)
        if self.initializing:
            if self.stopped_seconds() < 2.:
                self.invalidate('INITIAL_REFINEMENT_REQUIRES_STOP')
                return
            if translation_step > INITIAL_REFINEMENT_M or rotation_step > INITIAL_REFINEMENT_RAD:
                self.invalidate('INITIAL_REFINEMENT_OUT_OF_BOUNDS')
                return
            if self.metrics['overlap_ratio'] < .85:
                self.initial_candidates = []
                self.reason = 'INITIAL_REFINEMENT_LOW_OVERLAP'
                return
            # Independent fresh scans must agree with every retained correction.
            # Compare them at the same body pose to account for the IMU lever arm.
            if self.initial_candidates and self.clock() - self.initial_candidates[-1][1] > policy['max_correction_age_s']:
                self.initial_candidates = []
            if any(np.linalg.norm((candidate @ odom @ self.imu_base)[:3, 3] - after[:3, 3]) > INITIAL_CONSISTENCY_M
                   or rotation_error_rad(candidate @ odom @ self.imu_base, after) > INITIAL_CONSISTENCY_RAD
                   for candidate, _ in self.initial_candidates):
                self.initial_candidates = []
            self.initial_candidates.append((transform.copy(), receipt))
            self.metrics['initial_confirmations'] = len(self.initial_candidates)
            if len(self.initial_candidates) < INITIAL_CONFIRMATIONS:
                self.reason = 'INITIAL_REFINEMENT_CONFIRMING'
                return
            self.initializing = False
            self.initial_candidates = []
        elif (translation_step > policy['max_translation_step_m']
                or rotation_step > policy['max_rotation_step_rad']):
            self.invalidate('CORRECTION_JUMP_RESEED_REQUIRED')
            return
        self.correction = transform
        self.last_accepted_stamp, self.last_accepted_receipt = stamp, receipt
        self.accepted_odom = odom
        self.sequence += 1
        self.reason = 'MAP_TRACKING'

    def status(self):
        now = self.clock()
        age = None if self.last_accepted_receipt is None else now - self.last_accepted_receipt
        distance = None if self.accepted_odom is None or self.current_odom is None else float(np.linalg.norm(
            self.current_odom[:3, 3] - self.accepted_odom[:3, 3]))
        ready = bool(self.correction is not None and age is not None and 0 <= age <= self.bundle['policy']['max_correction_age_s']
                     and distance is not None and distance <= self.bundle['policy']['max_propagation_m']
                     and self.last_pose_receipt is not None and 0 <= now - self.last_pose_receipt <= .5)
        if ready:
            self.last_estimated_pose = {
                **self.pose_context(), 'source': 'STORED_PCD_FASTLIO',
                'pose': display_pose(self.nav_map @ self.correction @ self.current_odom @ self.imu_base),
                'stamp_ns': str(self.last_pose_stamp), 'correction_sequence': self.sequence,
            }
            self.last_estimated_receipt = self.last_pose_receipt
        estimated = (None if self.last_estimated_pose is None else {
            **self.last_estimated_pose, 'stale': not ready,
            'age_s': max(0., now - self.last_estimated_receipt)})
        return {'source': 'STORED_PCD_FASTLIO', 'ready': ready,
                'state': self.reason if ready or self.correction is None else 'MAP_CORRECTION_STALE',
                'bundle_generation': self.bundle['generation'], 'localization_generation': self.generation,
                'reference_sha256': self.bundle['localization_3d']['sha256'],
                'correction_sequence': self.sequence, 'correction_stamp_ns': str(self.last_accepted_stamp),
                'correction_age_s': age, 'propagated_distance_m': distance,
                'linear_speed_mps': self.speed, 'angular_speed_rps': self.yaw_rate,
                'stopped_seconds': self.stopped_seconds(), 'metrics': self.metrics,
                'initial_pose_receipt': self.initial_pose_receipt,
                **self.pose_context(),
                'workflow': self.bundle.get('workflow', 'legacy_stored_map'),
                'match_armed': self.match_armed, 'match_receipt': self.match_receipt,
                'seed_geometry': self.bundle.get('seed_geometry'),
                'accepted_initial_pose': self.accepted_initial_pose, 'estimated_pose': estimated,
                'weighting': self.weighting['mode'], 'reference_full_count': self.full_count,
                **({'weighting_config': self.weighting} if self.weighting['mode'] == CANDIDATE else {})}

    def nav_odom(self):
        return self.nav_map @ self.correction if self.status()['ready'] else None

    def close(self):
        self.generation += 1
        self.pool.shutdown(wait=True, cancel_futures=True)


def sanitize_status(value):
    """Bound ROS diagnostic data before using its stop/source proof in HTTP."""
    try:
        if not isinstance(value, dict) or len(json.dumps(value, allow_nan=False)) > 16_384:
            return None
        if value['source'] != 'STORED_PCD_FASTLIO' or type(value['ready']) is not bool:
            return None
        if any(not isinstance(value[k], str) or not 1 <= len(value[k]) <= 128 for k in ('bundle_generation', 'reference_sha256', 'state')):
            return None
        if any(type(value[k]) is not int or value[k] < 0 for k in ('localization_generation', 'correction_sequence')):
            return None
        for key in ('stopped_seconds', 'linear_speed_mps', 'angular_speed_rps', 'correction_age_s'):
            number = value[key]
            if number is None and key != 'stopped_seconds':
                continue
            if type(number) not in (int, float) or not math.isfinite(number) or number < 0:
                return None
        receipt = value.get('initial_pose_receipt')
        if receipt is not None:
            if (not isinstance(receipt, dict) or type(receipt.get('accepted')) is not bool
                    or not isinstance(receipt.get('stamp_ns'), str)
                    or not receipt['stamp_ns'].isdigit() or not 1 <= len(receipt['stamp_ns']) <= 20
                    or not isinstance(receipt.get('reason'), str) or not 1 <= len(receipt['reason']) <= 120
                    or type(receipt.get('localization_generation')) is not int
                    or receipt['localization_generation'] < 0):
                return None
        for key in ('accepted_initial_pose', 'estimated_pose'):
            marker = value.get(key)
            if marker is None:
                continue
            if not isinstance(marker, dict):
                return None
            if any(marker.get(pin) != value.get(pin) for pin in (
                    'map_id', 'map_revision', 'localization_map_id', 'localization_map_revision',
                    'bundle_generation', 'localization_generation', 'runtime_instance_generation')):
                return None
            pose = marker.get('pose')
            if (not isinstance(pose, dict) or any(type(pose.get(axis)) not in (int, float)
                    or not math.isfinite(pose[axis]) or abs(pose[axis]) > 1_000_000.
                    for axis in ('x', 'y', 'z', 'roll', 'pitch', 'yaw'))):
                return None
            stamp = marker.get('stamp_ns')
            if not isinstance(stamp, str) or not stamp.isdigit() or not 1 <= len(stamp) <= 20:
                return None
            if key == 'accepted_initial_pose' and marker.get('accepted') is not True:
                return None
            if key == 'estimated_pose' and (type(marker.get('stale')) is not bool
                    or type(marker.get('age_s')) not in (int, float)
                    or not math.isfinite(marker['age_s']) or marker['age_s'] < 0
                    or type(marker.get('correction_sequence')) is not int
                    or marker['correction_sequence'] < 1):
                return None
        match_receipt = value.get('match_receipt')
        if match_receipt is not None and (
                not isinstance(match_receipt, dict) or type(match_receipt.get('accepted')) is not bool
                or not isinstance(match_receipt.get('request_id'), str)
                or not 1 <= len(match_receipt['request_id']) <= 128
                or not isinstance(match_receipt.get('reason'), str)
                or not 1 <= len(match_receipt['reason']) <= 120
                or type(match_receipt.get('localization_generation')) is not int):
            return None
        return json.loads(json.dumps(value, allow_nan=False))
    except (KeyError, TypeError, ValueError):
        return None
