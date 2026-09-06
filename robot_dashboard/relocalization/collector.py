"""Bounded fixed-source collection logic for a future D2 ROS owner."""

from __future__ import annotations

import math
import struct
import threading
import time
from typing import Any, Callable, Mapping

from .manager import (
    COLLECTION_DURATION_S,
    MAX_FILTERED_POINTS,
    MAX_FRAMES,
    MAX_RAW_POINTS,
    SOURCE_FRAME,
    SOURCE_TOPIC,
    LiveCollection,
    RelocalizationConflict,
    RelocalizationUnavailable,
    RelocalizationValidationError,
)


CloudProvider = Callable[[], Mapping[str, Any]]
MotionProvider = Callable[[], Mapping[str, Any]]


class FixedCloudRegisteredCollector:
    """Collect fresh, increasing `/cloud_registered` samples without ROS imports.

    The injected provider must be owned by a dedicated, profile-fixed ROS
    subscriber. Reusing the operator-selected preview source is prohibited.
    """

    def __init__(
        self,
        cloud_provider: CloudProvider,
        motion_provider: MotionProvider,
        *,
        clock: Callable[[], float] = time.monotonic,
        duration_s: float = COLLECTION_DURATION_S,
        poll_interval_s: float = 0.01,
    ) -> None:
        if not 0.1 <= duration_s <= 5.0 or not 0.001 <= poll_interval_s <= 0.1:
            raise RelocalizationValidationError("collector timing is invalid")
        self._cloud_provider = cloud_provider
        self._motion_provider = motion_provider
        self._clock = clock
        self._duration_s = duration_s
        self._poll_interval_s = poll_interval_s

    def collect(self, cancel_event: threading.Event) -> LiveCollection:
        started = self._clock()
        deadline = started + self._duration_s
        stamps: list[int] = []
        points: list[tuple[float, float, float]] = []
        raw_points = 0
        last_seq: int | None = None
        start_pose: tuple[float, float, float] | None = None
        end_pose: tuple[float, float, float] | None = None
        maximum_twist = 0.0
        maximum_imu = 0.0
        maximum_yaw_delta = 0.0
        while self._clock() < deadline and len(stamps) < MAX_FRAMES:
            if cancel_event.is_set():
                raise RelocalizationConflict("collection canceled")
            cloud = self._cloud_provider()
            seq = cloud.get("seq") if isinstance(cloud, Mapping) else None
            if isinstance(seq, int) and not isinstance(seq, bool) and seq != last_seq:
                sample_points, source_points = _cloud_points(cloud)
                stamp = cloud.get("stamp_ns")
                if not isinstance(stamp, int) or isinstance(stamp, bool) or stamp <= 0:
                    raise RelocalizationUnavailable("cloud source stamp is unavailable")
                if stamps and stamp <= stamps[-1]:
                    raise RelocalizationConflict("cloud source stamp did not progress")
                if cloud.get("topic") != SOURCE_TOPIC or cloud.get("frame_id") != SOURCE_FRAME:
                    raise RelocalizationConflict("cloud source identity changed")
                if cloud.get("publisher_count") != 1 or cloud.get("fresh") is not True or cloud.get("qos_valid") is not True:
                    raise RelocalizationUnavailable("cloud source readiness failed")
                raw_points += source_points
                if raw_points > MAX_RAW_POINTS:
                    raise RelocalizationValidationError("raw point accumulator exceeded its bound")
                points.extend(sample_points)
                stamps.append(stamp)
                last_seq = seq
                motion = self._motion_provider()
                pose = _motion_pose(motion)
                start_pose = pose if start_pose is None else start_pose
                end_pose = pose
                maximum_twist = max(maximum_twist, _finite_nonnegative(motion.get("fastlio_twist_mps"), "FAST-LIO twist"))
                maximum_imu = max(maximum_imu, _finite_nonnegative(motion.get("imu_angular_rate_rps"), "IMU angular rate"))
                maximum_yaw_delta = max(maximum_yaw_delta, abs(_angle_delta(pose[2], start_pose[2])))
            time.sleep(self._poll_interval_s)
        if start_pose is None or end_pose is None:
            raise RelocalizationUnavailable("no live cloud frames were collected")
        dx, dy = end_pose[0] - start_pose[0], end_pose[1] - start_pose[1]
        filtered = _preprocess(points)
        return LiveCollection(
            topic=SOURCE_TOPIC, frame_id=SOURCE_FRAME,
            duration_s=max(0.0, self._clock() - started),
            frame_stamps_ns=tuple(stamps), raw_points=raw_points,
            points=tuple(filtered), base_pose_odom=end_pose,
            controller_translation_delta_m=math.hypot(dx, dy),
            controller_yaw_delta_rad=maximum_yaw_delta,
            maximum_fastlio_twist_mps=maximum_twist,
            maximum_imu_angular_rate_rps=maximum_imu,
            publisher_count=1,
        )


def _cloud_points(cloud: Mapping[str, Any]) -> tuple[list[tuple[float, float, float]], int]:
    payload = cloud.get("points_bytes")
    source_points = cloud.get("source_points")
    if not isinstance(payload, bytes) or len(payload) % 12 or len(payload) > MAX_RAW_POINTS * 12:
        raise RelocalizationValidationError("cloud point payload is invalid")
    if isinstance(source_points, bool) or not isinstance(source_points, int) or source_points < len(payload) // 12:
        raise RelocalizationValidationError("cloud source point count is invalid")
    points = [point for point in struct.iter_unpack("<fff", payload) if all(math.isfinite(value) for value in point)]
    return points, source_points


def _preprocess(points: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    """Apply the D1 query filters and deterministic 0.15 m voxel bound."""

    voxels: dict[tuple[int, int, int], tuple[float, float, float]] = {}
    for point in points:
        x, y, z = point
        radius = math.hypot(x, y)
        if radius < 0.5 or radius > 20.0 or z < -2.0 or z > 3.0:
            continue
        cell = (math.floor(x / 0.15), math.floor(y / 0.15), math.floor(z / 0.15))
        voxels.setdefault(cell, point)
        if len(voxels) > MAX_FILTERED_POINTS:
            raise RelocalizationValidationError("filtered point accumulator exceeded its bound")
    return [voxels[key] for key in sorted(voxels)]


def _motion_pose(value: Mapping[str, Any]) -> tuple[float, float, float]:
    if not isinstance(value, Mapping) or value.get("fresh") is not True:
        raise RelocalizationUnavailable("motion evidence is unavailable")
    pose = value.get("base_pose_odom")
    if not isinstance(pose, (tuple, list)) or len(pose) != 3:
        raise RelocalizationUnavailable("base pose evidence is unavailable")
    result = tuple(float(item) for item in pose)
    if not all(math.isfinite(item) for item in result):
        raise RelocalizationUnavailable("base pose evidence is invalid")
    return result


def _finite_nonnegative(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) < 0.0:
        raise RelocalizationUnavailable(f"{label} is unavailable")
    return float(value)


def _angle_delta(value: float, reference: float) -> float:
    return math.atan2(math.sin(value - reference), math.cos(value - reference))
