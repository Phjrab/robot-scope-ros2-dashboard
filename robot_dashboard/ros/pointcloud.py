"""Bounded point-cloud extraction, state, and snapshot transport data."""

from __future__ import annotations

import secrets
import threading
from typing import Any, Callable, Dict

import numpy as np

from ..pointcloud import extract_xyz, reject_spatial_outliers


class PointCloudHub:
    MIN_CLOUD_POINTS = 1_000
    MAX_CUSTOM_CLOUD_POINTS = 1_000_000

    def __init__(
        self,
        lock: threading.RLock,
        *,
        max_points: int | None,
        radius_limit_m: float,
        frame_interval_s: float,
    ) -> None:
        self._lock = lock
        self.max_points = self.normalize_limit(max_points)
        self.radius_limit_m = radius_limit_m
        self.base_frame_interval_s = frame_interval_s
        self.cloud: Dict[str, Any] = {
            "seq": 0,
            "points_bytes": b"",
            "source_points": 0,
            "frame_id": "",
            "bounds": None,
            "updated": 0.0,
        }
        self.stream_id = secrets.token_urlsafe(12)
        self.last_processed = 0.0

    @classmethod
    def normalize_limit(cls, value: int | None) -> int | None:
        if value is None:
            return None
        limit = int(value)
        if limit < cls.MIN_CLOUD_POINTS or limit > cls.MAX_CUSTOM_CLOUD_POINTS:
            raise ValueError(
                f"max_points must be between {cls.MIN_CLOUD_POINTS} and "
                f"{cls.MAX_CUSTOM_CLOUD_POINTS}, or null for all points"
            )
        return limit

    def frame_interval(self, point_limit: int | None) -> float:
        effective = self.MAX_CUSTOM_CLOUD_POINTS if point_limit is None else point_limit
        byte_budget_interval = (effective * 12) / 4_000_000.0
        return min(3.0, max(self.base_frame_interval_s, byte_budget_interval))

    def settings(self) -> Dict[str, Any]:
        with self._lock:
            limit = self.max_points
            source_points = int(self.cloud.get("source_points", 0))
            sent_points = int(self.cloud.get("sent_points", 0))
        return {
            "max_points": limit,
            "all_points": limit is None,
            "min_points": self.MIN_CLOUD_POINTS,
            "max_custom_points": self.MAX_CUSTOM_CLOUD_POINTS,
            "source_points": source_points,
            "sent_points": sent_points,
            "frame_interval_s": self.frame_interval(limit),
            "transport": "binary_websocket",
        }

    def set_limit(self, value: int | None, selected_topic: str) -> Dict[str, Any]:
        limit = self.normalize_limit(value)
        with self._lock:
            if limit != self.max_points:
                self.max_points = limit
                self.reset(selected_topic)
            else:
                self.last_processed = 0.0
        return self.settings()

    def reset(self, topic: str) -> None:
        self.cloud = {
            "seq": int(self.cloud.get("seq", 0)) + 1,
            "points_bytes": b"",
            "sent_points": 0,
            "source_points": 0,
            "frame_id": "",
            "stamp_ns": 0,
            "units": "m",
            "bounds": None,
            "topic": topic,
            "robot_pose_in_frame": None,
            "updated": 0.0,
        }
        self.last_processed = 0.0

    def process(
        self,
        topic: str,
        message: Any,
        now: float,
        *,
        selected_topic: Callable[[], str],
        stamp_ns: Callable[[Any], int],
        robot_pose_in_frame: Callable[[str], Dict[str, Any] | None],
    ) -> bool:
        with self._lock:
            if topic != selected_topic():
                return False
            point_limit = self.max_points
            frame_interval = self.frame_interval(point_limit)
            if now - self.last_processed < frame_interval:
                return False
            self.last_processed = now
        extraction_limit = (
            self.MAX_CUSTOM_CLOUD_POINTS if point_limit is None else point_limit
        )
        array, source_points = extract_xyz(message, extraction_limit)
        array = reject_spatial_outliers(array, self.radius_limit_m)
        if not len(array):
            return False
        mins = [float(value) for value in np.min(array, axis=0)]
        maxs = [float(value) for value in np.max(array, axis=0)]
        packed = np.ascontiguousarray(array, dtype="<f4").reshape(-1).tobytes()
        frame_id = str(getattr(getattr(message, "header", None), "frame_id", ""))
        with self._lock:
            if topic != selected_topic():
                return False
            self.cloud = {
                "seq": self.cloud["seq"] + 1,
                "points_bytes": packed,
                "sent_points": int(array.shape[0]),
                "source_points": source_points,
                "frame_id": frame_id,
                "stamp_ns": stamp_ns(message),
                "units": "m",
                "bounds": {"min": mins, "max": maxs},
                "topic": topic,
                "robot_pose_in_frame": robot_pose_in_frame(frame_id),
                "updated": now,
            }
        return True

    def json_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            snapshot = {
                key: value for key, value in self.cloud.items() if key != "points_bytes"
            }
            point_bytes = self.cloud.get("points_bytes", b"")
            snapshot["stream_id"] = self.stream_id
        snapshot["points"] = np.frombuffer(point_bytes, dtype="<f4").tolist()
        return snapshot

    def binary_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            snapshot = dict(self.cloud)
            snapshot["stream_id"] = self.stream_id
            return snapshot
