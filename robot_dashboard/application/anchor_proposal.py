"""Global search in the captured FAST-LIO IMU frame; editable priors only.

Registered points are already in O. Rebase them with inverse(T_O_I(t0)),
then propagate the resulting T_M_I(t0) using the same odometry generation.
No static LiDAR extrinsic, ROS write, timestamp substitution or body claim.
"""
from __future__ import annotations

import hashlib
import math
import time

import numpy as np

from ..relocalization.experimental_se3 import (
    _rpy, compose, from_translation_quaternion, inverse, transform_points, validate_transform,
)
from ..relocalization.observation_alignment import (
    ObservationAlignmentError, observed_key, paired_pose, project_query,
)
from ..relocalization.global_observation_jobs import GlobalObservationConflict, GlobalObservationUnavailable
from ..relocalization.external_global_observation import ExternalGlobalObservationRunner
from ..relocalization.v031_observation_compat import SELECTION_POLICY
from ..ros.observation_identity import subscription_evidence_key
from .sensor_tracking import _admissible_gates


INPUT_KIND = "fastlio_imu"


def imu_matrix(pose):
    q = np.array([pose["orientation"][k] for k in ("x", "y", "z", "w")], dtype=float)
    norm = np.linalg.norm(q)
    if not math.isfinite(norm) or abs(norm - 1) > .01:
        raise ObservationAlignmentError("INVALID_QUATERNION")
    return from_translation_quaternion([pose["position"][k] for k in ("x", "y", "z")], q / norm)


def source_contract(cloud, pose, mode, now):
    if ((cloud.get("topic"), cloud.get("pipeline_stage"), cloud.get("frame_id"), cloud.get("units"))
            != ("/cloud_registered", "registered", "camera_init", "m")
            or (pose.get("topic"), pose.get("frame_id"), pose.get("child_frame_id"), pose.get("state"))
            != ("/Odometry", "camera_init", "body", "ok")):
        raise ObservationAlignmentError("FASTLIO_REGISTERED_IMU_REQUIRED")
    ck, pk = observed_key(cloud, provenance_mode=mode, now=now), observed_key(pose, provenance_mode=mode, now=now)
    if ck[0] != pk[0]:
        raise ObservationAlignmentError("SOURCE_CHANGED")
    for value in (cloud, pose):
        observation = value["observation"]
        stamp, received = observation.get("source_stamp_ns"), observation.get("received_monotonic_s")
        if (not isinstance(stamp, str) or not stamp.isdecimal() or not 0 < len(stamp) <= 20
                or int(stamp) <= 0 or observation.get("receipt_clock") != "OBSERVER_HOST_MONOTONIC"
                or type(received) not in (int, float) or not 0 <= now - received <= 1.):
            raise ObservationAlignmentError("STALE_INPUT")
    return dict(observer_id=ck[0], cloud_epoch=ck[1], pose_epoch=pk[1], provenance_mode=mode,
                cloud_subscription=list(subscription_evidence_key(cloud["observation"], now) or []) if mode == "subscription_observation" else None,
                pose_subscription=list(subscription_evidence_key(pose["observation"], now) or []) if mode == "subscription_observation" else None)


def capture_registered_imu(agent, *, mode, cancel, deadline, max_points, max_bytes, minimum_stamp_ns=None):
    """Capture one fresh, exact output-stamp pair inside the existing timeout."""
    reason = "FASTLIO_INPUTS_UNAVAILABLE"
    while not cancel.is_set() and time.monotonic() < deadline:
        try:
            cloud = agent.pointcloud_binary_snapshot()
            latest = agent.pose_snapshot()
            contract = source_contract(cloud, latest, mode, time.monotonic())
            if minimum_stamp_ns is not None and int(cloud['observation']['source_stamp_ns']) < int(minimum_stamp_ns):
                raise ObservationAlignmentError('SEED_CAPTURE_WAITING_FOR_NEWER_SCAN')
            pose = paired_pose(agent, cloud, contract, deadline)
            if pose is None:
                raise ObservationAlignmentError("FASTLIO_EXACT_POSE_PENDING")
            now = time.monotonic()
            contract = source_contract(cloud, pose, mode, now)
            _, _, provenance = project_query(cloud, pose, now, provenance_mode=mode)
            points = np.frombuffer(cloud["points_bytes"], dtype="<f4").reshape(-1, 3)
            if not 60 <= len(points) <= min(max_points, max_bytes // 24) or not np.isfinite(points).all():
                raise ObservationAlignmentError("REGISTERED_QUERY_POINT_LIMIT")
            odom_from_imu = imu_matrix(pose)
            rebased = transform_points(inverse(odom_from_imu), points)
            if np.max(np.abs(rebased)) > 1000:
                raise ObservationAlignmentError("REGISTERED_QUERY_COORDINATE_LIMIT")
            data = rebased.astype("<f8").tobytes()
            stamp = cloud["observation"]["source_stamp_ns"]
            scan = dict(encoding="float64_le_xyz", sha256=hashlib.sha256(data).hexdigest(),
                        point_count=len(points), shape=[len(points), 3], dtype="<f8", units="m",
                        source_frame="body", source_topic=cloud["topic"], topic=cloud["topic"],
                        observer_epoch=contract["cloud_epoch"], source_stamp_ns=stamp,
                        received_monotonic_s=cloud["observation"]["received_monotonic_s"],
                        receipt_clock="OBSERVER_HOST_MONOTONIC", transform_applied=True,
                        transform_basis="INVERSE_EXACT_STAMP_FASTLIO_ODOMETRY",
                        input_population="CACHED_REGISTERED_XYZ", source_order_preserved=True,
                        source_points=cloud.get("source_points"), sampling_applied=cloud.get("source_points") != len(points),
                        spatial_filter_applied=False, nonfinite_rows_preserved=True, zero_rows_preserved=True)
            return data, scan, dict(contract=contract, T_odom_imu=odom_from_imu.tolist(),
                                    provenance=provenance, pose_reference="FASTLIO_IMU")
        except (ObservationAlignmentError, ValueError, KeyError, TypeError) as exc:
            reason = str(exc)
            cancel.wait(min(.025, max(0., deadline - time.monotonic())))
    raise GlobalObservationUnavailable(reason if not cancel.is_set() else "CANCELLED")


def current_imu(agent, context):
    capture = context["anchor_capture"]
    contract = capture["contract"]
    cloud, pose = agent.pointcloud_binary_snapshot(), agent.pose_snapshot()
    now = time.monotonic()
    if source_contract(cloud, pose, contract["provenance_mode"], now) != contract:
        raise GlobalObservationConflict("ANCHOR_SOURCE_SESSION_CHANGED")
    if any(int(v["observation"]["source_stamp_ns"]) < int(context["source_stamp_ns"]) for v in (cloud, pose)):
        raise GlobalObservationConflict("ANCHOR_SOURCE_TIME_REVERSED")
    return cloud, pose, imu_matrix(pose), now


def proposal_from_job(job, catalog, agent, *, allow_ambiguous=False):
    if job.get("input_kind") != INPUT_KIND or job["state"] != "succeeded" or job["worker_active"]:
        raise GlobalObservationConflict("ANCHOR_PROPOSAL_NOT_READY")
    context, result = job["captured_context"], job["result"]
    if result["captured_context"] != context or not result["historical_only"]:
        raise GlobalObservationConflict("ANCHOR_RESULT_CONTEXT_CHANGED")
    metadata = catalog.metadata(job["map_id"])
    if metadata.get("revision") != job["map_revision"] or metadata.get("frame_id") != context["map_frame"]:
        raise GlobalObservationConflict("ANCHOR_MAP_CHANGED")
    observation = result["observation"]
    ExternalGlobalObservationRunner._validate_result(observation, context, allow_ambiguous=allow_ambiguous)
    index = observation.get("selected_candidate")
    if type(index) is not int or index < 0:
        raise GlobalObservationConflict("NO_SELECTED_GLOBAL_CANDIDATE")
    candidate = observation["candidates"][index]
    numbers = [candidate.get(k) for k in ("rmse_m", "full_scan_rmse_m", "overlap",
               "geometry_min_max_eigen_ratio", "inlier_geometry_min_max_eigen_ratio")]
    counts = [candidate.get(k) for k in ("distinct_inlier_voxel_count", "inlier_count", "scan_count")]
    if (observation.get("selection_policy") != SELECTION_POLICY
            or not _admissible_gates(observation, candidate, allowed=allow_ambiguous)
            or not all(type(n) in (int, float) and math.isfinite(n) and n >= 0 for n in numbers)
            or not .6 <= numbers[2] <= 1 or min(numbers[3:]) < .002
            or not all(type(n) is int for n in counts) or not 60 <= counts[0] <= counts[1] <= counts[2]
            or counts[2] != context["scan"]["point_count"] or candidate.get("refinement_stationary") is not True):
        raise GlobalObservationConflict("GLOBAL_CANDIDATE_NOT_ADMISSIBLE")
    _, pose, odom_now, now = current_imu(agent, context)
    map_from_odom = compose(validate_transform(candidate["map_from_scan"]), inverse(context["anchor_capture"]["T_odom_imu"]))
    proposed = compose(map_from_odom, odom_now)
    angles = [math.degrees(v) for v in _rpy(proposed[:3, :3])]
    return dict(schema="robot-scope.anchor-proposal.v1", job_id=job["job_id"],
                map=dict(id=job["map_id"], revision=job["map_revision"], frame=context["map_frame"]),
                pose=dict(zip(("x", "y", "z", "roll", "pitch", "yaw"), [*proposed[:3, 3].tolist(), *angles])),
                pose_reference="FASTLIO_IMU", units="metres_degrees", approximate_only=True, requires_reanchor=True,
                source_contract=context["anchor_capture"]["contract"],
                capture_stamp_ns=context["source_stamp_ns"], proposal_stamp_ns=pose["observation"]["source_stamp_ns"],
                pose_age_s=now - pose["observation"]["received_monotonic_s"],
                ambiguity_unresolved=(observation.get("ambiguity_override") or {}).get("applied") is True,
                rmse_m=candidate["rmse_m"], overlap=candidate["overlap"],
                absolute_accuracy_m=None, body_extrinsic_verified=False, operational_application="NOT_RUN")


def bind_local_seed(agent, seed, mode):
    """The explicit local-search action confirms the draft at this fresh pose."""
    from ..relocalization.seeded_initialization import seed_matrix
    cloud, pose = agent.pointcloud_binary_snapshot(), agent.pose_snapshot()
    contract = source_contract(cloud, pose, mode, time.monotonic())
    if contract != seed['source_contract']:
        raise GlobalObservationConflict('SEED_SOURCE_CHANGED_RECONFIRM')
    return dict(contract=contract, source_stamp_ns=pose['observation']['source_stamp_ns'],
                T_map_odom_seed=compose(seed_matrix(seed), inverse(imu_matrix(pose))).tolist(),
                T_odom_imu=imu_matrix(pose).tolist(), basis='EXPLICIT_SEARCH_ACTION_CURRENT_IMU')


def local_proposal_from_job(job, catalog, agent):
    context, result = job['captured_context'], job['result']
    if (job['state'] != 'succeeded' or job['worker_active'] or result is None
            or result['captured_context'] != context or not result['historical_only']):
        raise GlobalObservationConflict('ANCHOR_PROPOSAL_NOT_READY')
    metadata = catalog.metadata(job['map_id'])
    if metadata.get('revision') != job['map_revision'] or metadata.get('frame_id') != context['map_frame']:
        raise GlobalObservationConflict('ANCHOR_MAP_CHANGED')
    value = result['observation']
    if (value.get('schema') != 'robot-scope.seeded-local-result.v1'
            or value.get('seed_revision') != context['seed']['revision'] or 'map_from_scan' not in value):
        raise GlobalObservationConflict(value.get('reason') or 'LOCAL_RESULT_INVALID')
    _, pose, odom_now, now = current_imu(agent, context)
    transform = compose(validate_transform(value['map_from_scan']), inverse(context['anchor_capture']['T_odom_imu']))
    proposed = compose(transform, odom_now)
    return dict(schema='robot-scope.anchor-proposal.v1', job_id=job['job_id'], search_mode='seeded_local',
                map=dict(id=job['map_id'], revision=job['map_revision'], frame=context['map_frame']),
                seed_revision=context['seed']['revision'], seed=context['seed'],
                pose=dict(zip(('x','y','z','roll','pitch','yaw'), [*proposed[:3,3].tolist(),
                     *[math.degrees(v) for v in _rpy(proposed[:3,:3])]])), T_map_odom=transform.tolist(),
                pose_reference='FASTLIO_IMU', units='metres_degrees', approximate_only=True, requires_reanchor=True,
                source_contract=context['anchor_capture']['contract'], capture_stamp_ns=context['source_stamp_ns'],
                seed_stamp_ns=context['seed_binding']['source_stamp_ns'],
                proposal_stamp_ns=pose['observation']['source_stamp_ns'],
                pose_age_s=now-pose['observation']['received_monotonic_s'], admissible=value['admissible'],
                reason=value['reason'], delta=value['delta'], bounds=value['bounds'],
                ambiguity_unresolved=value['ambiguity_unresolved'], runtime_ms=value['runtime_ms'],
                rmse_m=value['numerical']['metrics']['rmse_m'], overlap=value['numerical']['metrics']['overlap_ratio'],
                numerical=value['numerical'], evaluation_scope=value['evaluation_scope'],
                absolute_accuracy_m=None, body_extrinsic_verified=False, operational_application='NOT_RUN')
