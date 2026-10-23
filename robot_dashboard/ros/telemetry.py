"""Bounded telemetry summaries, joint pose, odometry pose, and occupancy map."""

from __future__ import annotations

import base64
import math
import threading
from collections import deque
from typing import Any, Callable, Dict, Optional

import numpy as np
from .observation_identity import ObservationIdentity, subscription_evidence_key

from ..serializers import (
    classify_type,
    extract_go2_imu_rpy,
    extract_go2_joint_positions,
    extract_odometry_pose,
    go2_joint_state_payload,
    odometry_pose_payload,
    summarize_message,
)


class RateMeter:
    def __init__(self, maxlen: int = 180) -> None:
        self.times: deque[float] = deque(maxlen=maxlen)
        self.samples = 0

    def tick(self, now: float) -> None:
        self.times.append(now)
        self.samples += 1

    def hz(self) -> Optional[float]:
        if len(self.times) < 2:
            return None
        elapsed = self.times[-1] - self.times[0]
        if elapsed <= 0:
            return None
        return round((len(self.times) - 1) / elapsed, 2)

    def jitter_ms(self) -> Optional[float]:
        if len(self.times) < 4:
            return None
        intervals = np.diff(np.asarray(self.times, dtype=np.float64))
        return round(float(np.std(intervals) * 1000.0), 2)

    @property
    def last(self) -> Optional[float]:
        return self.times[-1] if self.times else None


class TelemetryHub:
    """Own bounded decoded observation state behind the RosAgent facade."""

    def __init__(
        self,
        lock: threading.RLock,
        *,
        joint_stale_after_s: float,
        pose_stale_after_s: float,
        pose_position_limit_m: float,
    ) -> None:
        self._lock = lock
        self.summaries: Dict[str, Dict[str, Any]] = {}
        self.summary_updated: Dict[str, float] = {}
        self.joint_stale_after_s = joint_stale_after_s
        self.joint_last_processed = 0.0
        self.joints: Dict[str, Any] = {
            "seq": 0,
            "topic": "",
            "type": "",
            "position_rad": None,
            "imu_rpy_rad": None,
            "source_order": "",
            "stamp_ns": 0,
            "updated": 0.0,
        }
        self.pose_stale_after_s = pose_stale_after_s
        self.pose_position_limit_m = pose_position_limit_m
        self.pose_identity = ObservationIdentity()
        self.pose_history: deque[Dict[str, Any]] = deque(maxlen=160)
        self.pose: Dict[str, Any] = {
            "seq": 0,
            "topic": "",
            "type": "",
            "pose": None,
            "stamp_ns": 0,
            "updated": 0.0,
        }
        self.map: Dict[str, Any] = {
            "seq": 0,
            "width": 0,
            "height": 0,
            "resolution": 0.0,
            "origin": [0.0, 0.0, 0.0],
            "frame_id": "",
            "data_b64": "",
            "updated": 0.0,
        }

    def reset_pose(self, topic: str, type_name: str) -> None:
        self.pose_identity.reset()
        self.pose_history.clear()
        self.pose = {
            "seq": int(self.pose.get("seq", 0)) + 1,
            "topic": topic,
            "type": type_name,
            "pose": None,
            "stamp_ns": 0,
            "updated": 0.0,
        }

    def update_pose(
        self,
        topic: str,
        type_name: str,
        message: Any,
        now: float,
        *,
        selected_topic: Callable[[], str],
        stamp_ns: Callable[[Any], int],
        message_info: Any = None,
        publisher_count: int | None = None,
        observation_context: Any = None,
    ) -> None:
        with self._lock:
            if topic != selected_topic():
                return
            if callable(observation_context):
                observation_context = observation_context()
                if observation_context is None:
                    return
            graph = (observation_context or {}).get("graph") or {}
            graph_received = graph.get("observed_monotonic_s")
            if graph.get("state") == "ok" and type(graph_received) in {int, float} and graph_received > now:
                return
            header = getattr(message, "header", None)
            observation = self.pose_identity.observe(
                topic=topic, frame=str(getattr(header, "frame_id", "")),
                child=str(getattr(message, "child_frame_id", "")), stamp_ns=stamp_ns(message),
                received=now, message_info=message_info, publisher_count=publisher_count,
                observation_context=observation_context,
            )
            if observation["reset_reason"] or (
                observation["identity_status"] != "OBSERVED_PUBLISHER"
                and subscription_evidence_key(observation, now) is None
            ):
                self.pose_history.clear()
                self.pose = {"seq": self.pose["seq"] + 1, "topic": topic, "type": type_name,
                             "pose": None, "stamp_ns": stamp_ns(message), "updated": now,
                             "observation": {**observation, "invalidated": True}}
        pose = extract_odometry_pose(
            message,
            type_name,
            position_limit_m=self.pose_position_limit_m,
        )
        if pose is None:
            return
        with self._lock:
            if (topic != selected_topic() or observation["publisher_epoch"] != self.pose_identity.epoch
                    or now < self.pose.get("updated", 0)):
                return
            self.pose = {
                "seq": int(self.pose.get("seq", 0)) + 1,
                "topic": topic,
                "type": type_name,
                "pose": pose,
                "stamp_ns": stamp_ns(message),
                "updated": now,
                "observation": observation,
            }
            self.pose_history.append(dict(self.pose))

    def store_summary(self, topic: str, type_name: str, message: Any, now: float) -> None:
        with self._lock:
            last = self.summary_updated.get(topic, 0.0)
        if now - last < 0.2:
            return
        summary = summarize_message(message, type_name)
        with self._lock:
            self.summaries[topic] = {
                "topic": topic,
                "type": type_name,
                "category": classify_type(type_name),
                "values": summary,
            }
            self.summary_updated[topic] = now

    def update_joints(
        self,
        topic: str,
        type_name: str,
        message: Any,
        now: float,
        *,
        selected_topic: Callable[[], str],
        stamp_ns: Callable[[Any], int],
    ) -> None:
        with self._lock:
            if (
                topic != selected_topic()
                or now - self.joint_last_processed < 0.02
            ):
                return
            self.joint_last_processed = now
        positions = extract_go2_joint_positions(message, type_name)
        if positions is None:
            return
        imu_rpy = extract_go2_imu_rpy(message, type_name)
        source_order = (
            "named_joint_state"
            if type_name == "sensor_msgs/msg/JointState"
            else "unitree_lowstate"
        )
        with self._lock:
            if topic != selected_topic():
                return
            self.joints = {
                "seq": self.joints["seq"] + 1,
                "topic": topic,
                "type": type_name,
                "position_rad": positions,
                "imu_rpy_rad": imu_rpy,
                "source_order": source_order,
                "stamp_ns": stamp_ns(message),
                "updated": now,
            }

    def update_map(
        self,
        topic: str,
        message: Any,
        now: float,
        *,
        stamp_ns: Callable[[Any], int],
    ) -> None:
        info = message.info
        width = int(info.width)
        height = int(info.height)
        cells = width * height
        if width <= 0 or height <= 0 or cells > 16_000_000 or len(message.data) != cells:
            raise ValueError(
                f"invalid OccupancyGrid dimensions/data: {width}x{height}, "
                f"{len(message.data)} cells"
            )
        origin = info.origin.position
        orientation = info.origin.orientation
        yaw = math.atan2(
            2.0 * (orientation.w * orientation.z + orientation.x * orientation.y),
            1.0 - 2.0 * (orientation.y * orientation.y + orientation.z * orientation.z),
        )
        raw = bytes((int(value) & 0xFF for value in message.data))
        with self._lock:
            self.map = {
                "seq": self.map["seq"] + 1,
                "width": width,
                "height": height,
                "resolution": float(info.resolution),
                "origin": [float(origin.x), float(origin.y), float(yaw)],
                "origin_pose": {
                    "position": {
                        "x": float(origin.x),
                        "y": float(origin.y),
                        "z": float(origin.z),
                    },
                    "orientation": {
                        "x": float(orientation.x),
                        "y": float(orientation.y),
                        "z": float(orientation.z),
                        "w": float(orientation.w),
                    },
                    "yaw": float(yaw),
                },
                "frame_id": str(message.header.frame_id),
                "stamp_ns": stamp_ns(message),
                "data_b64": base64.b64encode(raw).decode("ascii"),
                "data_encoding": "int8-base64",
                "cell_order": "row-major; cell(0,0) at origin",
                "topic": topic,
                "updated": now,
            }

    def joint_snapshot_locked(self, now: float) -> Dict[str, Any]:
        data = dict(self.joints)
        return go2_joint_state_payload(
            topic=str(data.get("topic", "")),
            type_name=str(data.get("type", "")),
            positions=data.get("position_rad"),
            updated_at=float(data.get("updated", 0.0)),
            now=now,
            stale_after_s=self.joint_stale_after_s,
            seq=int(data.get("seq", 0)),
            stamp_ns=int(data.get("stamp_ns", 0)),
            source_order=str(data.get("source_order", "")),
            imu_rpy_rad=data.get("imu_rpy_rad"),
        )

    def pose_snapshot_locked(self, now: float) -> Dict[str, Any]:
        return self._pose_payload(dict(self.pose), now)

    def observation_pose_near(
        self, observation: Dict[str, Any], now: float, *, provenance_mode: str = "native_publisher",
    ) -> Dict[str, Any] | None:
        from ..relocalization.observation_timing import measured_lock, note

        with measured_lock(self._lock, "pose_lock"):
            return self._observation_pose_near_locked(observation, now, provenance_mode, note)

    def _observation_pose_near_locked(
        self, observation: Dict[str, Any], now: float, provenance_mode: str, note: Callable[[str, Any], None],
    ) -> Dict[str, Any] | None:
        evidence_checks = 0
        note("pose_history_count", len(self.pose_history))
        try:
            if provenance_mode not in {"native_publisher", "subscription_observation"}:
                return None
            current_epoch = (self.pose.get("observation") or {}).get("publisher_epoch")
            candidates = [p for p in self.pose_history
                          if p["observation"]["publisher_epoch"] == current_epoch
                          and p["observation"]["observer_id"] == observation.get("observer_id")]
            if (self.pose.get("topic") == "/Odometry"
                    and (observation.get("subscription_evidence") or {}).get("topic") == "/cloud_registered"):
                # FAST-LIO registered cloud and IMU state share lidar_end_time.
                # Retain the exact original stamp; never substitute receipt time.
                candidates = [p for p in candidates if p["observation"].get("source_stamp_ns")
                              == observation.get("source_stamp_ns")]
            if provenance_mode == "subscription_observation":
                evidence_checks += 1
                current_key = subscription_evidence_key(self.pose.get("observation"), now)
                if current_key is None:
                    return None
                evidence_checks += 1
                if subscription_evidence_key(observation, now) is None:
                    return None
            received = observation.get("received_monotonic_s")
            if not candidates or not isinstance(received, (int, float)):
                return None
            if provenance_mode == "subscription_observation":
                ranked = [(abs(p["updated"] - received), p) for p in candidates]
                if all(math.isfinite(distance) for distance, _ in ranked):
                    # Stable sorting preserves the history order for equal
                    # distances, matching min() after the original filtering.
                    for _, candidate in sorted(ranked, key=lambda item: item[0]):
                        evidence_checks += 1
                        if subscription_evidence_key(candidate["observation"], now) == current_key:
                            return self._pose_payload(candidate, now)
                    return None
                # Preserve the original min/filter behavior for nonfinite
                # distances rather than introducing a new input policy here.
                valid = []
                for candidate in candidates:
                    evidence_checks += 1
                    if subscription_evidence_key(candidate["observation"], now) == current_key:
                        valid.append(candidate)
                candidates = valid
                if not candidates:
                    return None
            best = min(candidates, key=lambda p: abs(p["updated"] - received))
            return self._pose_payload(best, now)
        finally:
            note("pose_evidence_checks", evidence_checks)

    def _pose_payload(self, data: Dict[str, Any], now: float) -> Dict[str, Any]:
        payload = odometry_pose_payload(
            topic=str(data.get("topic", "")),
            type_name=str(data.get("type", "")),
            pose=data.get("pose"),
            updated_at=float(data.get("updated", 0.0)),
            now=now,
            stale_after_s=self.pose_stale_after_s,
            seq=int(data.get("seq", 0)),
            stamp_ns=int(data.get("stamp_ns", 0)),
        )
        payload["observation"] = dict(data.get("observation") or {})
        return payload

    def map_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.map)
