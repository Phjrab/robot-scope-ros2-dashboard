"""Offline-only experimental SE(3) point-to-point ICP.

T_target_source maps source points into the target frame. This module has no
ROS, control, map-runtime, pose-application, or 3DoF result dependencies.
Registered query clouds only: raw sensor extrinsics and odometry fusion are
deliberately outside this experiment, so neither can be applied twice here.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


SCHEMA = "robot-scope.experimental-se3-result.v1"
MAX_POINTS = 4_000
MIN_POINTS = 60
MAX_COORDINATE_M = 1_000.0
MAX_ITERATIONS = 40
MAX_CORRESPONDENCE_M = 0.75
MIN_OVERLAP = 0.60
MAX_RMSE_M = 0.05
MIN_GEOMETRY_RATIO = 0.002


class ExperimentalSE3Error(ValueError):
    """Invalid experimental input; never a production localization result."""


@dataclass(frozen=True)
class Cloud:
    points: np.ndarray
    frame: str
    kind: str
    unit: str = "m"
    stamp_ns: int | None = None

    def validated(self, *, reference: bool) -> "Cloud":
        expected = "REGISTERED_MAP" if reference else "REGISTERED_QUERY"
        if self.kind != expected:
            raise ExperimentalSE3Error(f"cloud kind must be {expected}; raw sensor clouds need explicit calibration")
        if not isinstance(self.frame, str) or not self.frame or len(self.frame) > 80:
            raise ExperimentalSE3Error("cloud frame is invalid")
        if self.unit != "m":
            raise ExperimentalSE3Error("cloud unit must be metres")
        if reference and self.stamp_ns is not None:
            raise ExperimentalSE3Error("the static reference must not carry a query timestamp")
        if not reference and (isinstance(self.stamp_ns, bool) or
                              not isinstance(self.stamp_ns, int) or self.stamp_ns <= 0):
            raise ExperimentalSE3Error("registered query needs a positive source timestamp")
        points = np.asarray(self.points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 3 or not MIN_POINTS <= len(points) <= MAX_POINTS:
            raise ExperimentalSE3Error("cloud point count or shape is invalid")
        if not np.isfinite(points).all() or np.max(np.abs(points)) > MAX_COORDINATE_M:
            raise ExperimentalSE3Error("cloud coordinates are nonfinite or outside metre bounds")
        return Cloud(points, self.frame, self.kind, self.unit, self.stamp_ns)


def validate_transform(transform: Any) -> np.ndarray:
    matrix = np.asarray(transform, dtype=np.float64)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ExperimentalSE3Error("T_target_source must be a finite 4x4 matrix")
    if not np.allclose(matrix[3], [0.0, 0.0, 0.0, 1.0], atol=1e-9):
        raise ExperimentalSE3Error("homogeneous transform last row is invalid")
    rotation = matrix[:3, :3]
    if (not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6)
            or not math.isclose(float(np.linalg.det(rotation)), 1.0, abs_tol=1e-6)):
        raise ExperimentalSE3Error("rotation must be proper and orthonormal")
    if np.max(np.abs(matrix[:3, 3])) > MAX_COORDINATE_M:
        raise ExperimentalSE3Error("transform translation is outside metre bounds")
    return matrix.copy()


def quaternion_xyzw_to_matrix(quaternion: Any) -> np.ndarray:
    q = np.asarray(quaternion, dtype=np.float64)
    if q.shape != (4,) or not np.isfinite(q).all():
        raise ExperimentalSE3Error("quaternion must be four finite xyzw values")
    norm = float(np.linalg.norm(q))
    if abs(norm - 1.0) > 1e-6:
        raise ExperimentalSE3Error("quaternion must be unit length")
    x, y, z, w = q / norm
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def matrix_to_quaternion_xyzw(rotation: Any) -> list[float]:
    candidate = np.eye(4)
    array = np.asarray(rotation, dtype=np.float64)
    if array.shape != (3, 3):
        raise ExperimentalSE3Error("rotation must be 3x3")
    candidate[:3, :3] = array
    rotation = validate_transform(candidate)[:3, :3]
    trace = float(np.trace(rotation))
    if trace > 0:
        scale = math.sqrt(trace + 1.0) * 2
        q = [(rotation[2, 1] - rotation[1, 2]) / scale,
             (rotation[0, 2] - rotation[2, 0]) / scale,
             (rotation[1, 0] - rotation[0, 1]) / scale, scale / 4]
    else:
        index = int(np.argmax(np.diag(rotation)))
        next_index, last_index = (index + 1) % 3, (index + 2) % 3
        scale = math.sqrt(1 + rotation[index, index] - rotation[next_index, next_index]
                          - rotation[last_index, last_index]) * 2
        xyz = [0.0, 0.0, 0.0]
        xyz[index] = scale / 4
        xyz[next_index] = (rotation[index, next_index] + rotation[next_index, index]) / scale
        xyz[last_index] = (rotation[index, last_index] + rotation[last_index, index]) / scale
        q = [*xyz, (rotation[last_index, next_index] - rotation[next_index, last_index]) / scale]
    if q[3] < 0:
        q = [-value for value in q]
    return [float(value / np.linalg.norm(q)) for value in q]


def from_translation_quaternion(translation: Any, quaternion_xyzw: Any) -> np.ndarray:
    position = np.asarray(translation, dtype=np.float64)
    if position.shape != (3,) or not np.isfinite(position).all():
        raise ExperimentalSE3Error("translation must be three finite metre values")
    transform = np.eye(4)
    transform[:3, :3] = quaternion_xyzw_to_matrix(quaternion_xyzw)
    transform[:3, 3] = position
    return validate_transform(transform)


def from_translation_rpy(translation: Any, rpy_rad: Any) -> np.ndarray:
    angles = np.asarray(rpy_rad, dtype=np.float64)
    if angles.shape != (3,) or not np.isfinite(angles).all():
        raise ExperimentalSE3Error("roll/pitch/yaw must be three finite radians")
    roll, pitch, yaw = angles
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    rotation = np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ])
    return from_translation_quaternion(translation, matrix_to_quaternion_xyzw(rotation))


def inverse(transform: Any) -> np.ndarray:
    matrix = validate_transform(transform)
    result = np.eye(4)
    result[:3, :3] = matrix[:3, :3].T
    result[:3, 3] = -result[:3, :3] @ matrix[:3, 3]
    return result


def compose(target_intermediate: Any, intermediate_source: Any) -> np.ndarray:
    return validate_transform(validate_transform(target_intermediate) @
                              validate_transform(intermediate_source))


def transform_points(transform: Any, points: Any) -> np.ndarray:
    matrix = validate_transform(transform)
    array = np.asarray(points, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3 or not np.isfinite(array).all():
        raise ExperimentalSE3Error("points must be finite Nx3 values")
    return array @ matrix[:3, :3].T + matrix[:3, 3]


def rotation_error_rad(estimated: Any, truth: Any) -> float:
    difference = validate_transform(estimated)[:3, :3] @ validate_transform(truth)[:3, :3].T
    return math.acos(float(np.clip((np.trace(difference) - 1) / 2, -1.0, 1.0)))


def _nearest(source: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    indices = np.empty(len(source), dtype=np.int64)
    distances = np.empty(len(source), dtype=np.float64)
    target_norms = np.sum(target * target, axis=1)
    for start in range(0, len(source), 128):
        block = source[start:start + 128]
        squared = np.maximum(np.sum(block * block, axis=1)[:, None] + target_norms[None, :]
                             - 2 * block @ target.T, 0.0)
        nearest = np.argmin(squared, axis=1)
        indices[start:start + len(block)] = nearest
        distances[start:start + len(block)] = squared[np.arange(len(block)), nearest]
    return indices, distances


def _rigid_fit(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    source_center, target_center = source.mean(axis=0), target.mean(axis=0)
    covariance = (source - source_center).T @ (target - target_center)
    u, _, vt = np.linalg.svd(covariance)
    correction = np.eye(3)
    correction[2, 2] = np.linalg.det(vt.T @ u.T)
    rotation = vt.T @ correction @ u.T
    result = np.eye(4)
    result[:3, :3] = rotation
    result[:3, 3] = target_center - rotation @ source_center
    return validate_transform(result)


def _rpy(rotation: np.ndarray) -> list[float]:
    pitch = math.asin(float(np.clip(-rotation[2, 0], -1.0, 1.0)))
    if abs(math.cos(pitch)) < 1e-8:
        roll = 0.0
        yaw = math.atan2(-rotation[0, 1], rotation[1, 1])
    else:
        roll = math.atan2(rotation[2, 1], rotation[2, 2])
        yaw = math.atan2(rotation[1, 0], rotation[0, 0])
    return [roll, pitch, yaw]


def register_se3(reference: Cloud, query: Cloud, initial_t_target_source: Any) -> dict[str, Any]:
    """One bounded local hypothesis, not global relocalization or pose application."""
    target = reference.validated(reference=True)
    source = query.validated(reference=False)
    pose = validate_transform(initial_t_target_source)
    started = time.monotonic()
    centered = target.points - target.points.mean(axis=0)
    eigenvalues, eigenvectors = np.linalg.eigh(centered.T @ centered / len(centered))
    geometry_ratio = float(eigenvalues[0] / max(eigenvalues[-1], 1e-12))
    weak_direction = [float(value) for value in eigenvectors[:, 0]]
    converged = False
    reason = "ITERATION_LIMIT"
    iterations = 0
    for iterations in range(1, MAX_ITERATIONS + 1):
        moved = transform_points(pose, source.points)
        indices, squared = _nearest(moved, target.points)
        mask = squared <= MAX_CORRESPONDENCE_M ** 2
        if int(mask.sum()) < MIN_POINTS:
            reason = "INSUFFICIENT_OVERLAP"
            break
        delta = _rigid_fit(moved[mask], target.points[indices[mask]])
        pose = compose(delta, pose)
        step_translation = float(np.linalg.norm(delta[:3, 3]))
        step_rotation = rotation_error_rad(delta, np.eye(4))
        if step_translation < 1e-5 and step_rotation < 1e-5:
            converged = True
            reason = "CANDIDATE"
            break
    moved = transform_points(pose, source.points)
    _, squared = _nearest(moved, target.points)
    mask = squared <= MAX_CORRESPONDENCE_M ** 2
    overlap = float(mask.mean())
    rmse = float(math.sqrt(float(squared[mask].mean()))) if mask.any() else None
    if geometry_ratio < MIN_GEOMETRY_RATIO:
        reason = "DEGENERATE_GEOMETRY"
    elif overlap < MIN_OVERLAP:
        reason = "LOW_OVERLAP"
    elif rmse is None or rmse > MAX_RMSE_M:
        reason = "HIGH_RESIDUAL"
    elif not converged and reason == "ITERATION_LIMIT":
        reason = "NOT_CONVERGED"
    status = "CANDIDATE" if reason == "CANDIDATE" else "REJECTED"
    roll, pitch, yaw = _rpy(pose[:3, :3])
    return {
        "schema": SCHEMA, "experimental": True, "status": status, "reason": reason,
        "method": "bounded-point-to-point-se3-icp", "target_frame": target.frame,
        "source_frame": source.frame, "query_stamp_ns": source.stamp_ns,
        "transform_convention": "T_target_source",
        "pose": {"x": float(pose[0, 3]), "y": float(pose[1, 3]), "z": float(pose[2, 3]),
                 "roll_rad": roll, "pitch_rad": pitch, "yaw_rad": yaw,
                 "quaternion_xyzw": matrix_to_quaternion_xyzw(pose[:3, :3])},
        "metrics": {"converged": converged, "iterations": iterations, "overlap_ratio": overlap,
                    "rmse_m": rmse, "geometry_min_max_eigen_ratio": geometry_ratio,
                    "weak_geometry_direction_target": weak_direction,
                    "runtime_ms": (time.monotonic() - started) * 1000.0},
    }


def validate_experimental_result(payload: Any) -> dict[str, Any]:
    """Validate a stored result without converting it to the 3DoF contract."""
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema", "experimental", "status", "reason", "method", "target_frame",
        "source_frame", "query_stamp_ns", "transform_convention", "pose", "metrics"
    }:
        raise ExperimentalSE3Error("experimental result fields are invalid")
    if (payload["schema"] != SCHEMA or payload["experimental"] is not True
            or payload["method"] != "bounded-point-to-point-se3-icp"
            or payload["transform_convention"] != "T_target_source"):
        raise ExperimentalSE3Error("experimental result identity is invalid")
    if payload["status"] not in {"CANDIDATE", "REJECTED"} or not isinstance(payload["reason"], str):
        raise ExperimentalSE3Error("experimental result status is invalid")
    if (payload["status"] == "CANDIDATE") != (payload["reason"] == "CANDIDATE"):
        raise ExperimentalSE3Error("candidate status and reason disagree")
    if any(not isinstance(payload[key], str) or not payload[key] or len(payload[key]) > 80
           for key in ("target_frame", "source_frame")):
        raise ExperimentalSE3Error("experimental frames are invalid")
    stamp = payload["query_stamp_ns"]
    if isinstance(stamp, bool) or not isinstance(stamp, int) or stamp <= 0:
        raise ExperimentalSE3Error("experimental query timestamp is invalid")
    pose, metrics = payload["pose"], payload["metrics"]
    if not isinstance(pose, Mapping) or set(pose) != {
        "x", "y", "z", "roll_rad", "pitch_rad", "yaw_rad", "quaternion_xyzw"
    }:
        raise ExperimentalSE3Error("experimental pose fields are invalid")
    if not isinstance(metrics, Mapping) or set(metrics) != {
        "converged", "iterations", "overlap_ratio", "rmse_m",
        "geometry_min_max_eigen_ratio", "weak_geometry_direction_target", "runtime_ms"
    }:
        raise ExperimentalSE3Error("experimental metric fields are invalid")
    numeric_pose = [pose[key] for key in ("x", "y", "z", "roll_rad", "pitch_rad", "yaw_rad")]
    numeric_metrics = [metrics[key] for key in (
        "overlap_ratio", "geometry_min_max_eigen_ratio", "runtime_ms")]
    if (any(isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) for value in numeric_pose + numeric_metrics)
            or max(abs(pose[key]) for key in ("x", "y", "z")) > MAX_COORDINATE_M):
        raise ExperimentalSE3Error("experimental numeric values are invalid")
    if not (-math.pi <= pose["roll_rad"] <= math.pi
            and -math.pi / 2 <= pose["pitch_rad"] <= math.pi / 2
            and -math.pi <= pose["yaw_rad"] <= math.pi):
        raise ExperimentalSE3Error("experimental angles are invalid")
    if (not isinstance(metrics["converged"], bool)
            or isinstance(metrics["iterations"], bool)
            or not isinstance(metrics["iterations"], int)
            or not 1 <= metrics["iterations"] <= MAX_ITERATIONS
            or not 0 <= metrics["overlap_ratio"] <= 1
            or not 0 <= metrics["geometry_min_max_eigen_ratio"] <= 1
            or not 0 <= metrics["runtime_ms"] <= 60_000):
        raise ExperimentalSE3Error("experimental metrics are invalid")
    rmse = metrics["rmse_m"]
    if rmse is not None and (isinstance(rmse, bool) or not isinstance(rmse, (int, float))
                             or not math.isfinite(rmse) or rmse < 0):
        raise ExperimentalSE3Error("experimental RMSE is invalid")
    direction = np.asarray(metrics["weak_geometry_direction_target"], dtype=np.float64)
    if direction.shape != (3,) or not np.isfinite(direction).all() or not math.isclose(
        float(np.linalg.norm(direction)), 1.0, abs_tol=1e-5
    ):
        raise ExperimentalSE3Error("weak geometry direction is invalid")
    quaternion = pose["quaternion_xyzw"]
    reconstructed = from_translation_rpy(
        [pose[key] for key in ("x", "y", "z")],
        [pose[key] for key in ("roll_rad", "pitch_rad", "yaw_rad")],
    )
    if not np.allclose(quaternion_xyzw_to_matrix(quaternion), reconstructed[:3, :3], atol=1e-5):
        raise ExperimentalSE3Error("quaternion and roll/pitch/yaw disagree")
    if payload["status"] == "CANDIDATE" and (
        not metrics["converged"] or metrics["overlap_ratio"] < MIN_OVERLAP
        or rmse is None or rmse > MAX_RMSE_M
        or metrics["geometry_min_max_eigen_ratio"] < MIN_GEOMETRY_RATIO
    ):
        raise ExperimentalSE3Error("candidate violates experimental quality gates")
    return dict(payload)
