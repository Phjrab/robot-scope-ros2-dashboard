"""Fixed-source camera demand, decode state, and bounded snapshots."""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Mapping
from typing import Any, Callable, Dict, Optional, Tuple

from ..public_diagnostics import public_diagnostic


CAMERA_SOURCE_IDS = ("go2_front", "realsense_color")
MAX_ACTIVE_CAMERA_SOURCES = 2
MAX_CAMERA_VIEWERS = 8
MAX_CAMERA_VIEWERS_PER_SOURCE = 4

_PUBLIC_CAMERA_STATUS_FIELDS = frozenset(
    {
        "enabled",
        "configured",
        "available",
        "state",
        "live",
        "source",
        "source_id",
        "source_label",
        "transport",
        "uri",
        "multicast_address",
        "port",
        "interface",
        "format",
        "width",
        "height",
        "max_frame_bytes",
        "fps_limit",
        "startup_frame_timeout_s",
        "frame_timeout_s",
        "fps",
        "frames",
        "age_s",
        "process_running",
        "watchdog_running",
        "restart_count",
        "restart_in_s",
        "oversize_frames",
        "invalid_frames",
        "receive_fps",
        "last_complete_jpeg_age_s",
        "network_bytes",
        "receive_bitrate_mbps",
        "metric_window_s",
        "decode_successes",
        "decode_failures",
        "status_class",
        "configured_robot_ip",
        "clock_domain",
        "cross_host_latency_state",
        "relay_health",
        "relay_health_age_s",
        "last_error",
    }
)


def public_camera_status(status: Mapping[str, Any]) -> Dict[str, Any]:
    """Project one receiver status without leaking future internal fields."""

    projected = {
        key: value for key, value in status.items() if key in _PUBLIC_CAMERA_STATUS_FIELDS
    }
    projected["last_error"] = public_diagnostic(status.get("last_error", ""))
    return projected


class CameraHub:
    """Own fixed camera frames and exactly-once viewer demand tokens."""

    def __init__(
        self,
        lock: threading.RLock,
        *,
        tick: Callable[[str, float], None],
        selected_ros_topic: Callable[[], str],
    ) -> None:
        self._lock = lock
        self._tick = tick
        self._selected_ros_topic = selected_ros_topic
        self.direct_camera: Any = None
        self.remote_camera: Any = None
        self.decoder: Any = None
        self.camera: Dict[str, Any] = {
            "seq": 0,
            "format": "none",
            "data": b"",
            "stamp_us": 0,
            "key": False,
            "width": 0,
            "height": 0,
            "encoding": "",
            "source": "none",
            "transport": "",
            "state": "waiting",
            "fps": None,
            "age_s": None,
        }
        self.remote_frame: Dict[str, Any] = {
            "seq": 0,
            "format": "none",
            "data": b"",
            "stamp_us": 0,
            "key": False,
            "width": 0,
            "height": 0,
            "encoding": "",
            "source": "remote_mjpeg",
            "source_id": "realsense_color",
            "source_label": "RealSense color camera",
            "transport": "http_mjpeg",
            "state": "waiting",
            "fps": None,
            "age_s": None,
            "updated": 0.0,
        }
        self.stream_ids = {
            source_id: secrets.token_urlsafe(12) for source_id in CAMERA_SOURCE_IDS
        }
        self.demand_lock = threading.RLock()
        self.accepting_demand = False
        self.demand_tokens = {source_id: set() for source_id in CAMERA_SOURCE_IDS}
        self.token_sources: Dict[str, str] = {}
        self.h264_sps = b""
        self.h264_pps = b""
        self.h264_pending_stamp = 0
        self.h264_pending = bytearray()

    @property
    def consumers(self) -> int:
        return len(self.token_sources)

    def attach(self, direct_camera: Any, remote_camera: Any, decoder: Any) -> None:
        self.direct_camera = direct_camera
        self.remote_camera = remote_camera
        self.decoder = decoder

    @staticmethod
    def valid_source_id(source_id: object) -> bool:
        return isinstance(source_id, str) and source_id in CAMERA_SOURCE_IDS

    def stream_open(self, source_id: str = "go2_front") -> Dict[str, Any]:
        if not self.valid_source_id(source_id):
            return {
                "accepted": False,
                "reason": "camera_source_not_found",
                "consumers": self.consumers,
            }
        with self.demand_lock:
            if not self.accepting_demand:
                return {
                    "accepted": False,
                    "reason": "camera_relay_shutting_down",
                    "consumers": self.consumers,
                }
            if len(self.token_sources) >= MAX_CAMERA_VIEWERS:
                return {
                    "accepted": False,
                    "reason": "camera_viewer_limit_reached",
                    "consumers": self.consumers,
                }
            if len(self.demand_tokens[source_id]) >= MAX_CAMERA_VIEWERS_PER_SOURCE:
                return {
                    "accepted": False,
                    "reason": "camera_source_viewer_limit_reached",
                    "consumers": self.consumers,
                }
            active_sources = sum(1 for tokens in self.demand_tokens.values() if tokens)
            if not self.demand_tokens[source_id] and active_sources >= MAX_ACTIVE_CAMERA_SOURCES:
                return {
                    "accepted": False,
                    "reason": "active_camera_source_limit_reached",
                    "consumers": self.consumers,
                }
            receiver = self.direct_camera if source_id == "go2_front" else self.remote_camera
            status = receiver.status()
            if source_id != "go2_front" and not bool(status.get("configured", False)):
                return {
                    "accepted": False,
                    "reason": "camera_source_unavailable",
                    "consumers": self.consumers,
                }
            token = secrets.token_urlsafe(24)
            tokens = self.demand_tokens[source_id]
            first_for_source = not tokens
            tokens.add(token)
            self.token_sources[token] = source_id
            if first_for_source:
                self.clear_frame(source_id)
                try:
                    started = (
                        receiver.start()
                        if source_id != "go2_front" or self.direct_camera.configured
                        else True
                    )
                except Exception:
                    tokens.remove(token)
                    self.token_sources.pop(token, None)
                    raise
                if not started:
                    tokens.remove(token)
                    self.token_sources.pop(token, None)
                    return {
                        "accepted": False,
                        "reason": "camera_source_unavailable",
                        "consumers": self.consumers,
                    }
            return {
                "accepted": True,
                "source_id": source_id,
                "token": token,
                "consumers": self.consumers,
                "source_viewers": len(tokens),
            }

    def stream_close(
        self,
        source_id: str = "go2_front",
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.valid_source_id(source_id):
            return {"released": False, "consumers": self.consumers}
        with self.demand_lock:
            tokens = self.demand_tokens[source_id]
            if (
                not token
                or self.token_sources.get(token) != source_id
                or token not in tokens
            ):
                return {
                    "released": False,
                    "consumers": self.consumers,
                    "source_viewers": len(tokens),
                }
            tokens.remove(token)
            self.token_sources.pop(token, None)
            if not tokens:
                receiver = self.direct_camera if source_id == "go2_front" else self.remote_camera
                receiver.stop()
                self.clear_frame(source_id)
            return {
                "released": True,
                "consumers": self.consumers,
                "source_viewers": len(tokens),
            }

    def clear_frame(self, source_id: str) -> None:
        with self._lock:
            target = self.camera if source_id == "go2_front" else self.remote_frame
            cleared = {
                "seq": int(target.get("seq", 0)) + 1,
                "format": "none",
                "data": b"",
                "stamp_us": 0,
                "key": False,
                "width": 0,
                "height": 0,
                "encoding": "",
                "source": "go2_multicast" if source_id == "go2_front" else "remote_mjpeg",
                "source_id": source_id,
                "source_label": (
                    "Go2 front camera"
                    if source_id == "go2_front"
                    else "RealSense color camera"
                ),
                "transport": (
                    "udp_multicast_rtp_h264"
                    if source_id == "go2_front"
                    else "http_mjpeg"
                ),
                "state": "waiting",
                "fps": None,
                "age_s": None,
                "updated": 0.0,
            }
            if source_id == "go2_front":
                self.camera = cleared
            else:
                self.remote_frame = cleared

    def shutdown(self) -> None:
        with self.demand_lock:
            self.accepting_demand = False
            self.token_sources.clear()
            for tokens in self.demand_tokens.values():
                tokens.clear()
            self.direct_camera.stop()
            self.remote_camera.stop()
        self.decoder.stop()

    def ros_callback(self, topic: str, type_name: str, message: Any) -> None:
        now = time.monotonic()
        self._tick(topic, now)
        if self.direct_camera.configured:
            return
        camera: Dict[str, Any]
        if type_name.endswith("/Go2FrontVideoData"):
            payload = bytes(getattr(message, "video720p", b""))
            stamp = int(getattr(message, "time_frame", 0))
            start = self.first_start_code(payload)
            if 0 < start <= 16:
                payload = payload[start:]
            if not payload:
                return
            if self.h264_pending_stamp == 0:
                self.h264_pending_stamp = stamp
                self.h264_pending.extend(payload)
                return
            if stamp == self.h264_pending_stamp:
                self.h264_pending.extend(payload)
                if len(self.h264_pending) > 16 * 1024 * 1024:
                    self.h264_pending.clear()
                    self.h264_pending_stamp = 0
                return
            completed_stamp = self.h264_pending_stamp
            completed = bytes(self.h264_pending)
            self.h264_pending.clear()
            self.h264_pending.extend(payload)
            self.h264_pending_stamp = stamp
            payload, key = self.prepare_h264(completed)
            if self.decoder.feed(payload):
                return
            camera = {
                "format": "h264",
                "data": payload,
                "stamp_us": completed_stamp or int(time.time() * 1_000_000),
                "key": key,
                "width": 1280,
                "height": 720,
                "encoding": "avc1.42E01E",
                "source": "ros_topic",
                "transport": "ros2",
                "state": "ok",
            }
        elif type_name == "sensor_msgs/msg/CompressedImage":
            fmt = str(getattr(message, "format", "jpeg")).lower()
            camera = {
                "format": "jpeg" if "jpeg" in fmt or "jpg" in fmt else "png",
                "data": bytes(getattr(message, "data", b"")),
                "stamp_us": int(time.time() * 1_000_000),
                "key": True,
                "width": 0,
                "height": 0,
                "encoding": fmt,
                "source": "ros_topic",
                "transport": "ros2",
                "state": "ok",
            }
        else:
            camera = {
                "format": "raw",
                "data": bytes(getattr(message, "data", b"")),
                "stamp_us": int(time.time() * 1_000_000),
                "key": True,
                "width": int(getattr(message, "width", 0)),
                "height": int(getattr(message, "height", 0)),
                "step": int(getattr(message, "step", 0)),
                "encoding": str(getattr(message, "encoding", "")),
                "source": "ros_topic",
                "transport": "ros2",
                "state": "ok",
            }
        if not camera["data"]:
            return
        with self._lock:
            camera["seq"] = self.camera["seq"] + 1
            camera["topic"] = topic
            camera["updated"] = now
            self.camera = camera

    def decoded_callback(self, jpeg: bytes) -> None:
        if self.direct_camera.configured:
            return
        now = time.monotonic()
        with self._lock:
            self.camera = {
                "format": "jpeg",
                "data": jpeg,
                "stamp_us": int(time.time() * 1_000_000),
                "key": True,
                "width": 640,
                "height": 360,
                "encoding": "jpeg",
                "seq": self.camera["seq"] + 1,
                "topic": self._selected_ros_topic() or "/frontvideostream",
                "updated": now,
                "decoder": "gstreamer",
                "source": "ros_topic",
                "transport": "ros2",
                "state": "ok",
            }

    def direct_callback(self, jpeg: bytes) -> None:
        now = time.monotonic()
        status = self.direct_camera.status()
        with self._lock:
            self.camera = {
                "format": "jpeg",
                "data": jpeg,
                "stamp_us": int(time.time() * 1_000_000),
                "key": True,
                "width": int(status.get("width", 1280)),
                "height": int(status.get("height", 720)),
                "encoding": "jpeg",
                "seq": int(self.camera.get("seq", 0)) + 1,
                "topic": str(status.get("uri", "go2-camera://230.1.1.1:1720")),
                "source": "go2_multicast",
                "source_id": "go2_front",
                "source_label": str(status.get("source_label", "Go2 front camera")),
                "transport": str(status.get("transport", "udp_multicast_rtp_h264")),
                "interface": str(status.get("interface", "")),
                "fps": status.get("fps"),
                "age_s": status.get("age_s"),
                "state": "ok",
                "updated": now,
                "decoder": "gstreamer",
            }

    def remote_callback(self, jpeg: bytes) -> None:
        now = time.monotonic()
        status = self.remote_camera.status()
        with self._lock:
            self.remote_frame = {
                "format": "jpeg",
                "data": jpeg,
                "stamp_us": int(time.time() * 1_000_000),
                "key": True,
                "width": 0,
                "height": 0,
                "encoding": "jpeg",
                "seq": int(self.remote_frame.get("seq", 0)) + 1,
                "topic": str(status.get("uri", "")),
                "source": "remote_mjpeg",
                "source_id": "realsense_color",
                "source_label": str(status.get("source_label", "RealSense color camera")),
                "transport": "http_mjpeg",
                "fps": status.get("fps"),
                "age_s": status.get("age_s"),
                "state": "ok",
                "updated": now,
                "decoder": "upstream_jpeg",
            }

    @staticmethod
    def first_start_code(payload: bytes) -> int:
        indexes = [
            index
            for index in (
                payload.find(b"\x00\x00\x00\x01"),
                payload.find(b"\x00\x00\x01"),
            )
            if index >= 0
        ]
        return min(indexes) if indexes else -1

    @staticmethod
    def nal_units(payload: bytes) -> list[Tuple[int, int, int]]:
        starts: list[Tuple[int, int]] = []
        index = 0
        while index < len(payload) - 3:
            if payload[index : index + 4] == b"\x00\x00\x00\x01":
                starts.append((index, 4))
                index += 4
            elif payload[index : index + 3] == b"\x00\x00\x01":
                starts.append((index, 3))
                index += 3
            else:
                index += 1
        units = []
        for position, (start, prefix) in enumerate(starts):
            end = starts[position + 1][0] if position + 1 < len(starts) else len(payload)
            header = start + prefix
            if header < end:
                units.append((payload[header] & 0x1F, start, end))
        return units

    def prepare_h264(self, payload: bytes) -> Tuple[bytes, bool]:
        units = self.nal_units(payload)
        if units:
            payload = payload[units[0][1] :]
            units = self.nal_units(payload)
        present = {unit_type for unit_type, _, _ in units}
        for unit_type, start, end in units:
            if unit_type == 7:
                self.h264_sps = payload[start:end]
            elif unit_type == 8:
                self.h264_pps = payload[start:end]
        key = 5 in present
        if key:
            prefix = b""
            if 7 not in present:
                prefix += self.h264_sps
            if 8 not in present:
                prefix += self.h264_pps
            payload = prefix + payload
        return payload, key

    def camera_snapshot_locked(self) -> Dict[str, Any]:
        snapshot = dict(self.camera)
        snapshot["stream_id"] = self.stream_ids["go2_front"]
        snapshot["source_id"] = "go2_front"
        status = self.direct_camera.status()
        snapshot["direct_camera"] = public_camera_status(status)
        if status.get("enabled") and status.get("configured"):
            snapshot.update(
                {
                    "topic": status.get("uri", "go2-camera://230.1.1.1:1720"),
                    "source": status.get("source", "go2_multicast"),
                    "source_label": status.get("source_label", "Go2 front camera"),
                    "transport": status.get("transport", "udp_multicast_rtp_h264"),
                    "interface": status.get("interface", ""),
                    "state": status.get("state", "waiting"),
                    "fps": status.get("fps"),
                    "age_s": status.get("age_s"),
                }
            )
        else:
            updated = float(snapshot.get("updated", 0.0) or 0.0)
            snapshot["age_s"] = round(max(0.0, time.monotonic() - updated), 3) if updated else None
            if snapshot.get("state") == "ok" and (
                snapshot["age_s"] is None or snapshot["age_s"] > 2.0
            ):
                snapshot["state"] = "stale"
        return snapshot

    def remote_snapshot_locked(self) -> Dict[str, Any]:
        snapshot = dict(self.remote_frame)
        status = self.remote_camera.status()
        snapshot.update(
            {
                "stream_id": self.stream_ids["realsense_color"],
                "source_id": "realsense_color",
                "topic": status.get("uri", ""),
                "source": status.get("source", "remote_mjpeg"),
                "source_label": status.get("source_label", "RealSense color camera"),
                "transport": status.get("transport", "http_mjpeg"),
                "state": status.get("state", "waiting"),
                "width": int(status.get("width", 0) or 0),
                "height": int(status.get("height", 0) or 0),
                "fps": status.get("fps"),
                "age_s": status.get("age_s"),
                "receive_fps": status.get("receive_fps"),
                "last_complete_jpeg_age_s": status.get("last_complete_jpeg_age_s"),
                "network_bytes": status.get("network_bytes"),
                "receive_bitrate_mbps": status.get("receive_bitrate_mbps"),
                "metric_window_s": status.get("metric_window_s"),
                "decode_successes": status.get("decode_successes"),
                "decode_failures": status.get("decode_failures"),
                "restart_count": status.get("restart_count"),
                "status_class": status.get("status_class"),
                "configured_robot_ip": status.get("configured_robot_ip"),
                "clock_domain": status.get("clock_domain"),
                "cross_host_latency_state": status.get("cross_host_latency_state"),
                "relay_health": status.get("relay_health", {}),
                "relay_health_age_s": status.get("relay_health_age_s"),
            }
        )
        return snapshot

    def catalog_snapshot(self) -> Dict[str, Any]:
        with self.demand_lock:
            viewers = {
                source_id: len(tokens) for source_id, tokens in self.demand_tokens.items()
            }
            total_viewers = self.consumers
        entries = []
        for source_id, label, status in (
            ("go2_front", "Go2 front camera", self.direct_camera.status()),
            ("realsense_color", "RealSense color camera", self.remote_camera.status()),
        ):
            public_status = public_camera_status(status)
            entries.append(
                {
                    "id": source_id,
                    "source_id": source_id,
                    "label": str(status.get("source_label", label)),
                    "enabled": bool(status.get("enabled", False)),
                    "configured": bool(status.get("configured", False)),
                    "available": bool(status.get("available", False)),
                    "state": str(status.get("state", "disabled")),
                    "live": bool(status.get("live", False)),
                    "format": "jpeg",
                    "encoding": "jpeg",
                    "transport": str(status.get("transport", "")),
                    "topic": str(status.get("uri", "")),
                    "uri": str(status.get("uri", "")),
                    "width": int(status.get("width", 0) or 0),
                    "height": int(status.get("height", 0) or 0),
                    "stream_id": self.stream_ids[source_id],
                    "viewers": viewers[source_id],
                    "max_viewers": MAX_CAMERA_VIEWERS_PER_SOURCE,
                    "fps": status.get("fps"),
                    "age_s": status.get("age_s"),
                    "last_error": public_diagnostic(status.get("last_error", "")),
                    **{
                        key: public_status[key]
                        for key in (
                            "receive_fps",
                            "last_complete_jpeg_age_s",
                            "network_bytes",
                            "receive_bitrate_mbps",
                            "metric_window_s",
                            "decode_successes",
                            "decode_failures",
                            "restart_count",
                            "status_class",
                            "configured_robot_ip",
                            "clock_domain",
                            "cross_host_latency_state",
                            "relay_health",
                            "relay_health_age_s",
                        )
                        if key in public_status
                    },
                }
            )
        return {
            "sources": entries,
            "max_active": MAX_ACTIVE_CAMERA_SOURCES,
            "max_viewers": MAX_CAMERA_VIEWERS,
            "active_sources": sum(1 for count in viewers.values() if count),
            "viewers": total_viewers,
        }

    def snapshots(self, source_ids: Tuple[str, ...]) -> Dict[str, Dict[str, Any]]:
        if (
            not isinstance(source_ids, tuple)
            or not source_ids
            or len(source_ids) > len(CAMERA_SOURCE_IDS)
            or len(set(source_ids)) != len(source_ids)
            or any(not self.valid_source_id(source_id) for source_id in source_ids)
        ):
            raise ValueError("camera sources are not allowlisted")
        with self._lock:
            return {
                source_id: (
                    self.camera_snapshot_locked()
                    if source_id == "go2_front"
                    else self.remote_snapshot_locked()
                )
                for source_id in source_ids
            }
