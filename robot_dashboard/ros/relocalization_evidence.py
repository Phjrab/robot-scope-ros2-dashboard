"""Fixed, opt-in ROS evidence owner for stationary D2 relocalization.

This component is deliberately independent from the operator-selected point
cloud preview.  It owns no publisher and does not expose any motion or Nav2
operation; it only validates three fixed competition-profile subscriptions.
"""

from __future__ import annotations

import copy
import math
import time
from typing import Any, Callable, Mapping

import numpy as np

from ..pointcloud import extract_xyz


PROFILE = "go2-xt16-wireless-competition-fastlio"
CLOUD_TOPIC = "/cloud_registered"
ODOMETRY_TOPIC = "/Odometry"
IMU_TOPIC = "/imu/body"
CLOUD_TYPE = "sensor_msgs/msg/PointCloud2"
ODOMETRY_TYPE = "nav_msgs/msg/Odometry"
IMU_TYPE = "sensor_msgs/msg/Imu"
CLOUD_FRAME = "camera_init"
ODOMETRY_CHILD_FRAME = "body"
MAX_SOURCE_POINTS = 100_000
MAX_SOURCE_AGE_S = 0.50
MAX_SOURCE_FUTURE_S = 0.10
MAX_SOURCE_GAP_S = MAX_SOURCE_AGE_S

FIXED_TOPICS: Mapping[str, str] = {
    CLOUD_TOPIC: CLOUD_TYPE,
    ODOMETRY_TOPIC: ODOMETRY_TYPE,
    IMU_TOPIC: IMU_TYPE,
}


class RelocalizationEvidenceHub:
    """Validate and retain the latest bounded sample from each fixed source."""

    def __init__(
        self,
        lock: Any,
        *,
        enabled: bool,
        monotonic: Callable[[], float] = time.monotonic,
        realtime_ns: Callable[[], int] = time.time_ns,
    ) -> None:
        self._lock = lock
        self._enabled = enabled is True
        self._monotonic = monotonic
        self._realtime_ns = realtime_ns
        self._contracts = {
            topic: {
                "type": type_name,
                "publisher_count": 0,
                "qos_valid": False,
                "generation": 0,
            }
            for topic, type_name in FIXED_TOPICS.items()
        }
        self._samples: dict[str, dict[str, Any]] = {
            topic: self._waiting_sample(0) for topic in FIXED_TOPICS
        }

    @property
    def enabled(self) -> bool:
        return self._enabled

    def update_contract(
        self,
        topic: str,
        type_name: str,
        *,
        publisher_count: int,
        qos_valid: bool,
    ) -> None:
        if topic not in FIXED_TOPICS:
            return
        expected = FIXED_TOPICS[topic]
        count = publisher_count if isinstance(publisher_count, int) and not isinstance(publisher_count, bool) else 0
        with self._lock:
            previous = self._contracts[topic]
            generation = int(previous.get("generation", 0))
            previous_count = int(previous.get("publisher_count", 0))
            if count == 1 and previous_count != 1:
                generation += 1
                self._samples[topic] = self._waiting_sample(generation)
            elif count != 1 and previous_count == 1:
                self._samples[topic]["continuity_broken"] = True
                self._samples[topic]["invalid_reason"] = (
                    "source publisher cardinality changed"
                )
            self._contracts[topic] = {
                "type": str(type_name),
                "publisher_count": max(0, count),
                "qos_valid": bool(qos_valid and type_name == expected),
                "generation": generation,
            }

    def ingest(self, topic: str, type_name: str, message: Any) -> bool:
        if not self._enabled or FIXED_TOPICS.get(topic) != type_name:
            return False
        received = self._monotonic()
        try:
            stamp_ns, source_age_s = self._validated_stamp(message)
            if topic == CLOUD_TOPIC:
                sample = self._cloud_sample(message)
            elif topic == ODOMETRY_TOPIC:
                sample = self._odometry_sample(message)
            else:
                sample = self._imu_sample(message)
            with self._lock:
                previous = self._samples[topic]
                if previous.get("continuity_broken") is True:
                    return False
                previous_received = float(previous.get("received_monotonic", 0.0))
                if (
                    previous_received > 0.0
                    and received - previous_received > MAX_SOURCE_GAP_S
                ):
                    previous["continuity_broken"] = True
                    previous["last_gap_s"] = received - previous_received
                    previous["invalid_reason"] = "source receipt continuity gap"
                    return False
                if stamp_ns <= int(previous.get("stamp_ns", 0)):
                    previous["continuity_broken"] = True
                    previous["invalid_reason"] = "source stamp did not progress"
                    return False
                self._samples[topic] = {
                    **sample,
                    "seq": int(previous.get("seq", 0)) + 1,
                    "stamp_ns": stamp_ns,
                    "source_age_at_receive_s": source_age_s,
                    "received_monotonic": received,
                    "generation": int(previous.get("generation", 0)),
                    "continuity_broken": False,
                    "last_gap_s": received - previous_received if previous_received > 0.0 else None,
                    "invalid_reason": "",
                }
            return True
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            with self._lock:
                self._samples[topic]["continuity_broken"] = True
                self._samples[topic]["invalid_reason"] = str(exc)[:160] or "invalid source sample"
            return False

    def cloud_snapshot(self) -> dict[str, Any]:
        with self._lock:
            sample = copy.deepcopy(self._samples[CLOUD_TOPIC])
            contract = dict(self._contracts[CLOUD_TOPIC])
        readiness = self._readiness(CLOUD_TOPIC, sample, contract)
        return {
            "schema": "robot-scope.relocalization-cloud-evidence.v1",
            "enabled": self._enabled,
            "topic": CLOUD_TOPIC,
            "frame_id": sample.get("frame_id", ""),
            "generation": sample.get("generation", 0),
            "seq": sample.get("seq", 0),
            "stamp_ns": sample.get("stamp_ns", 0),
            "source_points": sample.get("source_points", 0),
            "points_bytes": sample.get("points_bytes", b""),
            "publisher_count": contract["publisher_count"],
            "qos_valid": contract["qos_valid"],
            **readiness,
        }

    def motion_snapshot(self) -> dict[str, Any]:
        with self._lock:
            odometry = copy.deepcopy(self._samples[ODOMETRY_TOPIC])
            imu = copy.deepcopy(self._samples[IMU_TOPIC])
            odometry_contract = dict(self._contracts[ODOMETRY_TOPIC])
            imu_contract = dict(self._contracts[IMU_TOPIC])
        odometry_ready = self._readiness(ODOMETRY_TOPIC, odometry, odometry_contract)
        imu_ready = self._readiness(IMU_TOPIC, imu, imu_contract)
        fresh = odometry_ready["fresh"] is True and imu_ready["fresh"] is True
        reasons = [
            value
            for value in (odometry_ready["invalid_reason"], imu_ready["invalid_reason"])
            if value
        ]
        return {
            "schema": "robot-scope.relocalization-motion-evidence.v1",
            "enabled": self._enabled,
            "fresh": fresh,
            "invalid_reason": "; ".join(reasons)[:320],
            "base_pose_odom": odometry.get("base_pose_odom"),
            "fastlio_twist_mps": odometry.get("fastlio_twist_mps"),
            "imu_angular_rate_rps": imu.get("imu_angular_rate_rps"),
            "odometry": {
                "topic": ODOMETRY_TOPIC,
                "frame_id": odometry.get("frame_id", ""),
                "child_frame_id": odometry.get("child_frame_id", ""),
                "generation": odometry.get("generation", 0),
                "seq": odometry.get("seq", 0),
                "stamp_ns": odometry.get("stamp_ns", 0),
                "publisher_count": odometry_contract["publisher_count"],
                "qos_valid": odometry_contract["qos_valid"],
                **odometry_ready,
            },
            "imu": {
                "topic": IMU_TOPIC,
                "generation": imu.get("generation", 0),
                "seq": imu.get("seq", 0),
                "stamp_ns": imu.get("stamp_ns", 0),
                "publisher_count": imu_contract["publisher_count"],
                "qos_valid": imu_contract["qos_valid"],
                **imu_ready,
            },
        }

    def status_snapshot(self) -> dict[str, Any]:
        cloud = self.cloud_snapshot()
        motion = self.motion_snapshot()
        cloud.pop("points_bytes", None)
        return {
            "schema": "robot-scope.relocalization-evidence.v1",
            "enabled": self._enabled,
            "profile": PROFILE,
            "cloud": cloud,
            "motion": motion,
            "publisher_count": 0,
        }

    def _readiness(
        self,
        topic: str,
        sample: Mapping[str, Any],
        contract: Mapping[str, Any],
    ) -> dict[str, Any]:
        invalid_reason = str(sample.get("invalid_reason", ""))
        if not self._enabled:
            invalid_reason = "observer disabled"
        elif sample.get("continuity_broken") is True:
            invalid_reason = invalid_reason or "source continuity is broken"
        elif contract.get("type") != FIXED_TOPICS[topic]:
            invalid_reason = "source type mismatch"
        elif contract.get("publisher_count") != 1:
            invalid_reason = "source publisher cardinality is not one"
        elif contract.get("qos_valid") is not True:
            invalid_reason = "source QoS is invalid"
        elif int(sample.get("seq", 0)) <= 0:
            invalid_reason = invalid_reason or "waiting"
        received = float(sample.get("received_monotonic", 0.0))
        receipt_age_s = self._monotonic() - received if received > 0.0 else None
        stamp_ns = int(sample.get("stamp_ns", 0))
        source_age_s = (
            (self._realtime_ns() - stamp_ns) / 1_000_000_000.0
            if stamp_ns > 0
            else None
        )
        if not invalid_reason and (
            receipt_age_s is None or receipt_age_s < 0.0 or receipt_age_s > MAX_SOURCE_AGE_S
        ):
            invalid_reason = "source receipt is stale"
        if not invalid_reason and (
            source_age_s is None
            or source_age_s > MAX_SOURCE_AGE_S
            or source_age_s < -MAX_SOURCE_FUTURE_S
        ):
            invalid_reason = "source stamp is stale or future"
        return {
            "fresh": not invalid_reason,
            "invalid_reason": invalid_reason,
            "receipt_age_s": receipt_age_s,
            "source_age_s": source_age_s,
            "last_gap_s": sample.get("last_gap_s"),
        }

    @staticmethod
    def _waiting_sample(generation: int) -> dict[str, Any]:
        return {
            "seq": 0,
            "stamp_ns": 0,
            "received_monotonic": 0.0,
            "generation": generation,
            "continuity_broken": False,
            "last_gap_s": None,
            "invalid_reason": "waiting",
        }

    def _validated_stamp(self, message: Any) -> tuple[int, float]:
        stamp = getattr(getattr(message, "header", None), "stamp", None)
        sec = getattr(stamp, "sec", None)
        nanosec = getattr(stamp, "nanosec", None)
        if (
            isinstance(sec, bool)
            or not isinstance(sec, int)
            or isinstance(nanosec, bool)
            or not isinstance(nanosec, int)
            or sec < 0
            or not 0 <= nanosec < 1_000_000_000
        ):
            raise ValueError("source stamp is invalid")
        stamp_ns = sec * 1_000_000_000 + nanosec
        if stamp_ns <= 0:
            raise ValueError("source stamp is unavailable")
        age_s = (self._realtime_ns() - stamp_ns) / 1_000_000_000.0
        if age_s > MAX_SOURCE_AGE_S:
            raise ValueError("source stamp is stale")
        if age_s < -MAX_SOURCE_FUTURE_S:
            raise ValueError("source stamp is future")
        return stamp_ns, age_s

    @staticmethod
    def _cloud_sample(message: Any) -> dict[str, Any]:
        frame_id = str(getattr(getattr(message, "header", None), "frame_id", ""))
        if frame_id != CLOUD_FRAME:
            raise ValueError("cloud frame is invalid")
        array, source_points = extract_xyz(message, MAX_SOURCE_POINTS)
        if source_points <= 0 or source_points > MAX_SOURCE_POINTS or not len(array):
            raise ValueError("cloud point count is invalid")
        packed = np.ascontiguousarray(array, dtype="<f4").reshape(-1).tobytes()
        return {
            "frame_id": frame_id,
            "source_points": source_points,
            "points_bytes": packed,
        }

    @staticmethod
    def _odometry_sample(message: Any) -> dict[str, Any]:
        header = getattr(message, "header", None)
        frame_id = str(getattr(header, "frame_id", ""))
        child_frame_id = str(getattr(message, "child_frame_id", ""))
        if frame_id != CLOUD_FRAME or child_frame_id != ODOMETRY_CHILD_FRAME:
            raise ValueError("odometry frame is invalid")
        pose = getattr(getattr(message, "pose", None), "pose", None)
        position = getattr(pose, "position", None)
        orientation = getattr(pose, "orientation", None)
        x = _finite(getattr(position, "x", None), "odometry x")
        y = _finite(getattr(position, "y", None), "odometry y")
        qx = _finite(getattr(orientation, "x", None), "odometry qx")
        qy = _finite(getattr(orientation, "y", None), "odometry qy")
        qz = _finite(getattr(orientation, "z", None), "odometry qz")
        qw = _finite(getattr(orientation, "w", None), "odometry qw")
        norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
        if not 0.95 <= norm <= 1.05:
            raise ValueError("odometry quaternion is invalid")
        qx, qy, qz, qw = (value / norm for value in (qx, qy, qz, qw))
        yaw = math.atan2(
            2.0 * (qw * qz + qx * qy),
            1.0 - 2.0 * (qy * qy + qz * qz),
        )
        linear = getattr(getattr(getattr(message, "twist", None), "twist", None), "linear", None)
        vx = _finite(getattr(linear, "x", None), "odometry vx")
        vy = _finite(getattr(linear, "y", None), "odometry vy")
        vz = _finite(getattr(linear, "z", None), "odometry vz")
        return {
            "frame_id": frame_id,
            "child_frame_id": child_frame_id,
            "base_pose_odom": (x, y, yaw),
            "fastlio_twist_mps": math.sqrt(vx * vx + vy * vy + vz * vz),
        }

    @staticmethod
    def _imu_sample(message: Any) -> dict[str, Any]:
        angular = getattr(message, "angular_velocity", None)
        x = _finite(getattr(angular, "x", None), "IMU angular x")
        y = _finite(getattr(angular, "y", None), "IMU angular y")
        z = _finite(getattr(angular, "z", None), "IMU angular z")
        return {"imu_angular_rate_rps": math.sqrt(x * x + y * y + z * z)}


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} is invalid")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{label} is invalid")
    return normalized


__all__ = [
    "CLOUD_FRAME",
    "CLOUD_TOPIC",
    "CLOUD_TYPE",
    "FIXED_TOPICS",
    "IMU_TOPIC",
    "IMU_TYPE",
    "MAX_SOURCE_AGE_S",
    "MAX_SOURCE_FUTURE_S",
    "MAX_SOURCE_GAP_S",
    "ODOMETRY_CHILD_FRAME",
    "ODOMETRY_TOPIC",
    "ODOMETRY_TYPE",
    "PROFILE",
    "RelocalizationEvidenceHub",
]
