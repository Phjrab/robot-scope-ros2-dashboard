"""Small RosAgent facade for an existing subscription's raw XYZ capture."""
from __future__ import annotations

from typing import Any

from .raw_pointcloud_capture import RawCaptureUnavailable
from .sources import pointcloud_source_metadata


class RawObservationAccessMixin:
    def request_raw_pointcloud_capture(
        self, *, timeout_s: float = 5., max_points: int = 1_000_000,
        max_bytes: int = 32 * 1024 * 1024,
    ) -> dict[str, Any]:
        """Arm the existing selected subscription without starting a producer."""
        with self._lock:
            topic = self._sources.get("pointcloud", "")
            if not topic:
                raise RawCaptureUnavailable("raw point-cloud source is not selected")
            return self._pointcloud_hub.request_raw_capture(topic, timeout_s=timeout_s,
                max_points=max_points, max_bytes=max_bytes)

    def raw_pointcloud_capture_snapshot(self, capture_id: str | None = None) -> dict[str, Any] | None:
        return self._pointcloud_hub.raw_capture_snapshot(capture_id)

    def take_raw_pointcloud_capture(self, capture_id: str) -> dict[str, Any]:
        snapshot = self._pointcloud_hub.take_raw_capture(capture_id)
        snapshot.update(pointcloud_source_metadata(snapshot.get("topic", "")))
        return snapshot

    def cancel_raw_pointcloud_capture(self, capture_id: str) -> dict[str, Any]:
        return self._pointcloud_hub.cancel_raw_capture(capture_id)

    def raw_pointcloud_context_snapshot(self) -> dict[str, Any]:
        with self._lock:
            selected = self._sources.get("pointcloud", "")
            snapshot = self._pointcloud_hub.raw_context_snapshot()
            if snapshot.get("topic") != selected:
                snapshot = {"topic": selected, "frame_id": "", "observation": {}}
            snapshot.update(pointcloud_source_metadata(selected))
            return snapshot
