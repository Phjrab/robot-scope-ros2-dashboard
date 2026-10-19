"""One explicitly requested, bounded PointCloud2 XYZ capture.

This is separate from the viewport decoder: it never samples, removes rows,
converts through float32, applies a transform, or rejects spatial outliers.
The immutable output is packed little-endian float64 XYZ in source row order.
All PointField numeric values are represented exactly, including float64 and
32-bit integers; IEEE NaN payload bits and non-XYZ fields are not a raw archive.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import math
import secrets
import threading
import time
from typing import Any, Callable

import numpy as np


DEFAULT_MAX_POINTS = 1_000_000
DEFAULT_MAX_BYTES = 32 * 1024 * 1024
HARD_MAX_POINTS = 4_000_000
HARD_MAX_BYTES = 128 * 1024 * 1024
_DTYPES = {1: "i1", 2: "u1", 3: "i2", 4: "u2", 5: "i4", 6: "u4", 7: "f4", 8: "f8"}


class RawCaptureError(RuntimeError):
    pass


class RawCaptureBusy(RawCaptureError):
    pass


class RawCaptureNotFound(RawCaptureError):
    pass


class RawCaptureUnavailable(RawCaptureError):
    pass


class RawCaptureValidationError(RawCaptureError, ValueError):
    pass


def _limits(max_points: int, max_bytes: int) -> None:
    if (type(max_points) is not int or not 1 <= max_points <= HARD_MAX_POINTS
            or type(max_bytes) is not int or not 24 <= max_bytes <= HARD_MAX_BYTES):
        raise RawCaptureValidationError("invalid raw XYZ point or byte limit")


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise RawCaptureValidationError(f"invalid PointCloud2 {label}")
    return value


def capture_xyz(message: Any, *, max_points: int, max_bytes: int) -> dict[str, Any]:
    """Copy every XYZ row only after checking source and output byte limits.

    max_bytes bounds both the already-received source payload and the retained
    XYZ bytes independently. Working storage is bounded by two XYZ buffers plus
    two point-count boolean masks; it does not depend on unbounded source sizes.
    Invalid XYZ rows, signed zero and source order are preserved. Metadata says
    explicitly that this is numeric XYZ capture, not the original ROS message.
    """
    _limits(max_points, max_bytes)
    width = _integer(getattr(message, "width", None), "width", minimum=1)
    height = _integer(getattr(message, "height", None), "height", minimum=1)
    point_step = _integer(getattr(message, "point_step", None), "point_step", minimum=1)
    row_step = _integer(getattr(message, "row_step", 0), "row_step") or width * point_step
    count = width * height
    if count > max_points or count * 24 > max_bytes:
        raise RawCaptureValidationError("raw XYZ exceeds its point or byte limit")
    if row_step < width * point_step:
        raise RawCaptureValidationError("PointCloud2 row_step is smaller than its packed row")
    required_bytes = (height - 1) * row_step + width * point_step
    if required_bytes > max_bytes:
        raise RawCaptureValidationError("PointCloud2 source layout exceeds its byte limit")
    try:
        payload = memoryview(getattr(message, "data", b""))
        if not payload.c_contiguous:
            raise TypeError("noncontiguous payload")
        payload = payload.cast("B")
    except (TypeError, ValueError) as exc:
        raise RawCaptureValidationError("PointCloud2 data must be a contiguous byte buffer") from exc
    if payload.nbytes > max_bytes:
        raise RawCaptureValidationError("PointCloud2 source payload exceeds its byte limit")
    if payload.nbytes < required_bytes:
        raise RawCaptureValidationError("PointCloud2 payload is truncated")
    fields = {}
    for field in getattr(message, "fields", ()):
        name = getattr(field, "name", None)
        if name in ("x", "y", "z"):
            if name in fields:
                raise RawCaptureValidationError("PointCloud2 has duplicate XYZ fields")
            fields[name] = field
    if set(fields) != {"x", "y", "z"}:
        raise RawCaptureValidationError("PointCloud2 requires x, y and z fields")
    endian = ">" if bool(getattr(message, "is_bigendian", False)) else "<"
    formats, offsets, source_fields = [], [], []
    for name in ("x", "y", "z"):
        field = fields[name]
        datatype = _integer(getattr(field, "datatype", None), f"{name} datatype", minimum=1)
        kind = _DTYPES.get(datatype)
        if kind is None or _integer(getattr(field, "count", 1), f"{name} count", minimum=1) != 1:
            raise RawCaptureValidationError("PointCloud2 XYZ fields must have supported scalar datatypes")
        offset = _integer(getattr(field, "offset", None), f"{name} offset")
        dtype = np.dtype(kind if kind.endswith("1") else endian + kind)
        if offset + dtype.itemsize > point_step:
            raise RawCaptureValidationError("PointCloud2 XYZ field exceeds point_step")
        formats.append(dtype)
        offsets.append(offset)
        source_fields.append({"name": name, "datatype": datatype, "offset": offset, "count": 1})
    dtype = np.dtype({"names": ["x", "y", "z"], "formats": formats,
                      "offsets": offsets, "itemsize": point_step})
    source = np.ndarray((height, width), dtype=dtype, buffer=payload, strides=(row_step, point_step))
    xyz = np.empty((count, 3), dtype="<f8")
    # Reshaping a structured padded cloud would copy all fields. Each assignment
    # copies only one XYZ component into its final row/column position instead.
    for index, name in enumerate(("x", "y", "z")):
        xyz[:, index].reshape(height, width)[:] = source[name]
    finite = np.isfinite(xyz[:, 0])
    finite &= np.isfinite(xyz[:, 1])
    finite &= np.isfinite(xyz[:, 2])
    finite_points = int(np.count_nonzero(finite))
    packed = xyz.tobytes(order="C")
    return {"xyz_bytes": packed, "xyz_sha256": hashlib.sha256(packed).hexdigest(),
            "encoding": "float64_le_xyz", "point_step": 24, "source_points": count,
            "captured_points": count, "finite_points": finite_points,
            "nonfinite_points": count - finite_points, "xyz_bytes_count": len(packed),
            "source_payload_bytes": payload.nbytes, "source_width": width, "source_height": height,
            "source_point_step": point_step, "source_row_step": row_step,
            "source_is_bigendian": endian == ">", "source_xyz_fields": source_fields,
            "source_order_preserved": True, "nonfinite_rows_preserved": True,
            "zero_rows_preserved": True, "sampling_applied": False, "spatial_filter_applied": False,
            "transform_applied": False, "raw_message_archive": False,
            "units": "m", "units_basis": "ROS_POINTCLOUD2_CONVENTION_UNVERIFIED"}


@dataclass(frozen=True)
class CaptureTicket:
    capture_id: str
    generation: int
    topic: str
    observer_epoch: str
    max_points: int
    max_bytes: int


class RawPointCloudCaptureLatch:
    """Own one pending/copying/ready capture, sharing the PointCloudHub lock.

    Cancellation immediately suppresses publication. A copying callback keeps
    the slot until it returns so repeated cancellation cannot multiply buffers.
    Snapshot methods never expose the payload; take() transfers immutable bytes.
    """

    def __init__(self, lock: Any, *, now: Callable[[], float] = time.monotonic) -> None:
        self._lock, self._now = lock, now
        self._generation = 0
        self._record: dict[str, Any] | None = None
        self._in_flight: CaptureTicket | None = None
        self._timer: threading.Timer | None = None

    def request(self, topic: str, observer_epoch: str, *, timeout_s: float = 5.,
                max_points: int = DEFAULT_MAX_POINTS, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, Any]:
        _limits(max_points, max_bytes)
        if (not isinstance(topic, str) or not topic.startswith("/") or len(topic) > 512
                or not isinstance(observer_epoch, str) or not observer_epoch
                or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 30):
            raise RawCaptureValidationError("invalid raw XYZ capture request")
        with self._lock:
            if self._in_flight is not None or (self._record and self._record["state"] in {"awaiting", "ready"}):
                raise RawCaptureBusy("a raw XYZ capture still owns the slot")
            self._generation += 1
            created, capture_id = self._now(), secrets.token_hex(12)
            self._record = {"schema": "robot-scope.raw-xyz-capture.v1", "capture_id": capture_id,
                            "generation": self._generation, "state": "awaiting", "reason": None,
                            "topic": topic, "observer_epoch": observer_epoch, "capture_active": False,
                            "created_monotonic_s": created, "deadline_monotonic_s": created + timeout_s,
                            "completed_monotonic_s": None, "max_points": max_points, "max_bytes": max_bytes,
                            "historical_only": True, "body_pose": None, "body_extrinsic_verified": False,
                            "tracking_verified": False, "operational_application": "NOT_RUN"}
            timer = threading.Timer(timeout_s, self._expire, args=(capture_id, self._generation))
            timer.daemon = True
            self._timer = timer
            timer.start()
            return self._public()

    def begin(self, *, topic: str, frame_id: str, source_stamp_ns: int,
              received_monotonic_s: float, observation: dict[str, Any]) -> CaptureTicket | None:
        with self._lock:
            record = self._record
            # This is the entire no-request path. No layout inspection, copy,
            # hash, full-cloud extraction, timer or background worker occurs.
            if record is None or record["state"] != "awaiting":
                return None
            if self._now() >= record["deadline_monotonic_s"]:
                self._terminal("timed_out", "CAPTURE_TIMEOUT")
                return None
            if topic != record["topic"] or observation.get("publisher_epoch") != record["observer_epoch"]:
                self.invalidate("SOURCE_CHANGED")
                return None
            # Do not satisfy a new request with a callback already queued at
            # request time. The receipt is the original callback's timestamp.
            if received_monotonic_s < record["created_monotonic_s"]:
                return None
            if (not isinstance(frame_id, str) or not frame_id or type(source_stamp_ns) is not int
                    or source_stamp_ns <= 0 or observation.get("source_stamp_ns") != str(source_stamp_ns)):
                self._terminal("failed", "SOURCE_FRAME_OR_STAMP_UNAVAILABLE")
                return None
            record.update(state="capturing", capture_active=True, source_frame=frame_id, frame_id=frame_id,
                          source_stamp_ns=str(source_stamp_ns), observer_id=observation.get("observer_id"),
                          received_monotonic_s=received_monotonic_s,
                          receipt_clock="OBSERVER_HOST_MONOTONIC", observation=copy.deepcopy(observation))
            ticket = CaptureTicket(record["capture_id"], record["generation"], topic,
                                   record["observer_epoch"], record["max_points"], record["max_bytes"])
            self._in_flight = ticket
            return ticket

    def finish(self, ticket: CaptureTicket, result: dict[str, Any] | None = None, *,
               reason: str | None = None, current_topic: str, observer_epoch: str) -> None:
        with self._lock:
            if self._in_flight != ticket:
                return
            self._in_flight = None
            record = self._record
            if record is None or record["capture_id"] != ticket.capture_id:
                return
            record["capture_active"] = False
            if record["state"] != "capturing":
                return
            if self._now() >= record["deadline_monotonic_s"]:
                self._terminal("timed_out", "CAPTURE_TIMEOUT")
            elif (ticket.generation != self._generation or current_topic != ticket.topic
                  or observer_epoch != ticket.observer_epoch):
                self._terminal("stale", "SOURCE_CHANGED")
            elif reason is not None or result is None:
                self._terminal("failed", reason or "CAPTURE_FAILED")
            else:
                record.update(result)
                self._terminal("ready", None)

    def snapshot(self, capture_id: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            if capture_id is not None:
                self._get(capture_id)
            return self._public() if self._record else None

    def take(self, capture_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._get(capture_id)
            if record["state"] != "ready":
                raise RawCaptureUnavailable("raw XYZ capture is not ready")
            packed = record.pop("xyz_bytes")
            record["state"] = "consumed"
            return {**self._public(), "xyz_bytes": packed}

    def cancel(self, capture_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._get(capture_id)
            if record["state"] in {"awaiting", "capturing", "ready"}:
                self._terminal("cancelled", "CAPTURE_CANCELLED")
            return self._public()

    def invalidate(self, reason: str = "CONTEXT_CHANGED") -> None:
        with self._lock:
            self._generation += 1
            if self._record and self._record["state"] in {"awaiting", "capturing", "ready"}:
                self._terminal("stale", reason)

    def _expire(self, capture_id: str, generation: int) -> None:
        with self._lock:
            if (self._record and self._record["capture_id"] == capture_id
                    and self._record["generation"] == generation
                    and self._record["state"] in {"awaiting", "capturing"}):
                self._terminal("timed_out", "CAPTURE_TIMEOUT")

    def _terminal(self, state: str, reason: str | None) -> None:
        assert self._record is not None
        self._record.update(state=state, reason=reason, completed_monotonic_s=self._now())
        if state != "ready":
            self._record.pop("xyz_bytes", None)
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _get(self, capture_id: str) -> dict[str, Any]:
        if self._record is None or capture_id != self._record["capture_id"]:
            raise RawCaptureNotFound("raw XYZ capture was not found")
        return self._record

    def _public(self) -> dict[str, Any]:
        assert self._record is not None
        return copy.deepcopy({key: value for key, value in self._record.items() if key != "xyz_bytes"})
