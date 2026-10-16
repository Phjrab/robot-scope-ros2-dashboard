"""Bounded native-localization evidence without native DB interpretation.

The ROS service exposes a boolean, not the SDK callback status. Allowlisted log
events can be candidates in a source-clock window, never an attributed callback
or localization success. No raw log, filesystem path or exception text is kept.
"""
from __future__ import annotations

from collections import deque
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
from typing import Any


MAX_NATIVE_HASH_BYTES = 256 * 1024 * 1024
MAX_LOG_EVENTS = 128
MAX_LINE_BYTES = 4096
SDK_12_6_STATUS_NAMES = {
    0: "CUVSLAM_SUCCESS", 1: "CUVSLAM_TRACKING_LOST", 2: "CUVSLAM_INVALID_ARG",
    3: "CUVSLAM_CAN_NOT_LOCALIZE", 4: "CUVSLAM_GENERIC_ERROR",
    5: "CUVSLAM_UNSUPPORTED_NUMBER_OF_CAMERAS", 6: "CUVSLAM_SLAM_IS_NOT_INITIALIZED",
    7: "CUVSLAM_NOT_IMPLEMENTED", 8: "CUVSLAM_READING_SLAM_INTERNALS_DISABLED",
}
_ROS_LINE = re.compile(
    r"\[(?:INFO|WARN|ERROR)\] \[(\d{1,12})\.(\d{1,9})\] "
    r"\[vslam_lab\.visual_slam_node\]: (.*)$")
_FAILURE = re.compile(r"Failed to localize in map\. Error (\d{1,3})$")
_CALL_FAILURE = re.compile(r"CUVSLAM_LocalizeInExistDb Error (\d{1,3})$")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def opaque_native_identity(path: Path) -> dict[str, Any]:
    """Hash bounded opaque bytes, reporting uncertainty without blocking service."""
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return {"status": "NOT_REGULAR", "sha256": None, "size_bytes": None}
        if not 0 < before.st_size <= MAX_NATIVE_HASH_BYTES:
            return {"status": "HASH_BOUND_EXCEEDED", "sha256": None, "size_bytes": before.st_size}
        checksum = hashlib.sha256()
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            total = 0
            while chunk := stream.read(min(1024 * 1024, MAX_NATIVE_HASH_BYTES + 1 - total)):
                total += len(chunk)
                if total > MAX_NATIVE_HASH_BYTES:
                    return {"status": "HASH_BOUND_EXCEEDED", "sha256": None, "size_bytes": total}
                checksum.update(chunk)
            after = os.fstat(stream.fileno())
        def identity(value):
            return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        stable = identity(before) == identity(after) and total == before.st_size
        return {"status": "OPAQUE_BYTES_HASHED" if stable else "CHANGED_DURING_HASH",
                "sha256": checksum.hexdigest() if stable else None, "size_bytes": total}
    except OSError:
        return {"status": "HASH_UNAVAILABLE", "sha256": None, "size_bytes": None}
    finally:
        if descriptor is not None:
            os.close(descriptor)


class NativeLogDiagnostics:
    """Keep only recognized event codes from bounded complete ROS log lines."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending = b""
        self._dropping = False
        self._events: deque[dict[str, Any]] = deque(maxlen=MAX_LOG_EVENTS)
        self._sequence = 0
        self._oversized_lines = 0

    @property
    def sequence(self) -> int:
        with self._lock:
            return self._sequence

    def feed(self, chunk: bytes) -> None:
        with self._lock:
            for part in chunk.splitlines(keepends=True):
                complete = part.endswith((b"\n", b"\r"))
                if len(self._pending) + len(part) > MAX_LINE_BYTES:
                    if not self._dropping:
                        self._oversized_lines += 1
                    self._dropping = True
                    self._pending = b""
                if not self._dropping:
                    self._pending += part
                if complete:
                    if not self._dropping:
                        self._parse(self._pending)
                    self._pending, self._dropping = b"", False

    def _parse(self, line: bytes) -> None:
        match = _ROS_LINE.search(_ANSI.sub("", line.decode("utf-8", errors="replace").rstrip()))
        if match is None:
            return
        seconds, fraction, message = match.groups()
        stamp = int(seconds) * 1_000_000_000 + int(fraction.ljust(9, "0"))
        status = None
        failure = _FAILURE.fullmatch(message)
        call_failure = _CALL_FAILURE.fullmatch(message)
        if failure or call_failure:
            kind = "CALLBACK_FAILED" if failure else "NATIVE_DISPATCH_FAILED"
            code = int((failure or call_failure).group(1))
            status = code if code in SDK_12_6_STATUS_NAMES else None
        elif message.startswith("Trying to localize in map '"):
            kind = "REQUEST_LOGGED"
        elif message.startswith("Successfully localized at {"):
            kind, status = "CALLBACK_SUCCESS_LOGGED", 0
        else:
            return
        self._sequence += 1
        self._events.append({"sequence": self._sequence, "source_stamp_ns": str(stamp),
            "event": kind, "sdk_status_candidate": status,
            "sdk_name_candidate": SDK_12_6_STATUS_NAMES.get(status)})

    def window(self, since: int, start_ns: int | None, end_ns: int | None) -> dict[str, Any]:
        with self._lock:
            valid = (type(start_ns) is int and type(end_ns) is int and 0 <= start_ns <= end_ns)
            events = [copy.deepcopy(value) for value in self._events if valid
                and value["sequence"] > since and start_ns <= int(value["source_stamp_ns"]) <= end_ns]
            return {"correlation": "unknown", "reason": "NATIVE_CALLBACK_HAS_NO_REQUEST_ID" if valid
                    else "SOURCE_CLOCK_FENCE_UNAVAILABLE", "attributed_sdk_status": None,
                    "candidate_events": events[-16:], "candidate_events_truncated": len(events) > 16,
                    "oversized_lines_dropped": self._oversized_lines,
                    "sdk_name_reference": "preserved_cuvslam_api_12_6_header"}


def persist_attempt(run_dir: Any, attempt: int, phase: str, value: dict[str, Any]) -> bool:
    """Save bounded structured evidence in the existing private owned run dir."""
    if (not isinstance(run_dir, Path) or not run_dir.is_absolute() or run_dir.is_symlink()
            or type(attempt) is not int or not 1 <= attempt <= 64 or phase not in {"request", "result"}):
        return False
    try:
        content = json.dumps(value, sort_keys=True, allow_nan=False).encode()
        if len(content) > 32 * 1024:
            return False
        path = run_dir / ("native-localization-%d-%s.json" % (attempt, phase))
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
        return True
    except (OSError, TypeError, ValueError):
        return False
