"""Bounded, append-only operator intent timeline.

The timeline records browser request identity, not a verified human identity.
It contains fixed event names and bounded opaque identifiers only; request
bodies, credentials, paths, ROS messages, and exception text are never stored.
"""

from __future__ import annotations

import json
import os
import re
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping


EVENT_SCHEMA = "robot-scope.operator-event.v1"
EVENT_LINE_MAX_BYTES = 1_024
EVENT_FILE_MAX_BYTES = 256 * 1_024
EVENT_RETENTION_FILES = 4
EVENT_EXPORT_MAX_ENTRIES = 256

_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_REASON_RE = re.compile(r"^[a-z0-9_]{1,64}$")
_EVENT_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_REQUEST_SEQUENCE_RE = re.compile(r"^[0-9]{1,16}$")
_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$"
)

_HTTP_EVENTS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("POST", re.compile(r"^/api/v1/control/arm$"), "control_arm"),
    ("POST", re.compile(r"^/api/v1/control/disarm$"), "control_disarm"),
    ("POST", re.compile(r"^/api/v1/control/stop$"), "estop_latch"),
    ("POST", re.compile(r"^/api/v1/control/estop/clear$"), "estop_clear"),
    ("POST", re.compile(r"^/api/v1/mapping/start$"), "mapping_start"),
    ("POST", re.compile(r"^/api/v1/mapping/stop$"), "mapping_stop"),
    ("POST", re.compile(r"^/api/v1/mapping/save$"), "mapping_save"),
    ("POST", re.compile(r"^/api/v1/navigation/start$"), "navigation_start"),
    ("POST", re.compile(r"^/api/v1/navigation/stop$"), "navigation_stop"),
    ("POST", re.compile(r"^/api/v1/navigation/initial-pose$"), "initial_pose"),
    ("POST", re.compile(r"^/api/v1/navigation/goal$"), "goal_send"),
    ("POST", re.compile(r"^/api/v1/navigation/goal/annotation$"), "annotation_goal_send"),
    ("POST", re.compile(r"^/api/v1/navigation/cancel$"), "goal_cancel"),
    ("POST", re.compile(r"^/api/v1/navigation/clear-costmaps$"), "costmap_clear"),
    ("POST", re.compile(r"^/api/v1/missions$"), "mission_create"),
    ("POST", re.compile(r"^/api/v1/missions/(?P<mission_id>[0-9a-f]{32})/start$"), "mission_start"),
    ("POST", re.compile(r"^/api/v1/missions/(?P<mission_id>[0-9a-f]{32})/pause$"), "mission_pause"),
    ("POST", re.compile(r"^/api/v1/missions/(?P<mission_id>[0-9a-f]{32})/resume$"), "mission_resume"),
    ("POST", re.compile(r"^/api/v1/missions/(?P<mission_id>[0-9a-f]{32})/skip$"), "mission_skip"),
    ("POST", re.compile(r"^/api/v1/missions/(?P<mission_id>[0-9a-f]{32})/retry$"), "mission_retry"),
    ("POST", re.compile(r"^/api/v1/missions/(?P<mission_id>[0-9a-f]{32})/abort$"), "mission_abort"),
    ("POST", re.compile(r"^/api/v1/datasets/capture/start$"), "dataset_start"),
    ("POST", re.compile(r"^/api/v1/datasets/capture/stop$"), "dataset_stop"),
    ("POST", re.compile(r"^/api/v1/system/service/restart$"), "service_restart"),
    ("POST", re.compile(r"^/api/v1/system/service/stop$"), "service_stop"),
    ("POST", re.compile(r"^/api/v1/control/bridge-service/start$"), "bridge_service_start"),
    ("POST", re.compile(r"^/api/v1/control/bridge-service/stop$"), "bridge_service_stop"),
    ("POST", re.compile(r"^/api/v1/system/diagnostics/export$"), "diagnostics_export"),
    ("POST", re.compile(r"^/api/v1/saved-maps/(?P<map_id>[0-9a-f]{24})/convert-2d$"), "map_convert"),
    ("POST", re.compile(r"^/api/v1/saved-maps/(?P<map_id>[0-9a-f]{24})/edited-copy$"), "map_edit"),
    ("PATCH", re.compile(r"^/api/v1/saved-maps/(?P<map_id>[0-9a-f]{24})/annotations$"), "map_annotations_update"),
    ("PATCH", re.compile(r"^/api/v1/saved-maps/(?P<map_id>[0-9a-f]{24})$"), "map_rename"),
    ("DELETE", re.compile(r"^/api/v1/saved-maps/(?P<map_id>[0-9a-f]{24})$"), "map_delete"),
)


def _utc_timestamp(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _safe_root(root: Path) -> Path:
    requested = Path(root)
    if not requested.is_absolute():
        raise ValueError("operator event root must be absolute")
    normalized = Path(os.path.abspath(str(requested)))
    if normalized == Path("/"):
        raise ValueError("operator event root cannot be filesystem root")
    probe = normalized
    missing: list[Path] = []
    while not probe.exists():
        missing.append(probe)
        if probe.parent == probe:
            raise ValueError("operator event root has no existing parent")
        probe = probe.parent
    if probe.is_symlink() or probe.resolve(strict=True) != probe:
        raise ValueError("operator event root cannot contain symlinks")
    for path in reversed(missing):
        path.mkdir(mode=0o700)
    if normalized.is_symlink() or normalized.resolve(strict=True) != normalized:
        raise ValueError("operator event root cannot contain symlinks")
    info = normalized.stat()
    if info.st_uid != os.geteuid():
        raise ValueError("operator event root must be owned by the service user")
    if missing:
        os.chmod(normalized, 0o700)
    elif stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("existing operator event root must have mode 0700")
    return normalized


def classify_http_event(method: str, path: str) -> tuple[str, Dict[str, str]] | None:
    """Map one fixed mutation route to its public event and opaque targets."""

    normalized_method = str(method or "").upper()
    for expected_method, pattern, event_type in _HTTP_EVENTS:
        if normalized_method != expected_method:
            continue
        match = pattern.fullmatch(str(path or ""))
        if match:
            return event_type, {
                key: value
                for key, value in match.groupdict().items()
                if value and _OPAQUE_ID_RE.fullmatch(value)
            }
    return None


def _project_event(value: object) -> Dict[str, Any] | None:
    """Return only the fixed public event schema from a persisted line."""

    if not isinstance(value, dict) or value.get("schema") != EVENT_SCHEMA:
        return None
    event_id = value.get("event_id")
    if (
        isinstance(event_id, bool)
        or not isinstance(event_id, int)
        or not 0 < event_id <= 9_007_199_254_740_991
    ):
        return None
    timestamp = str(value.get("timestamp", ""))
    event_type = str(value.get("event_type", ""))
    result = str(value.get("result", ""))
    reason = str(value.get("reason_code", ""))
    if (
        not _TIMESTAMP_RE.fullmatch(timestamp)
        or not _EVENT_RE.fullmatch(event_type)
        or result not in {"accepted", "rejected", "error"}
        or not _REASON_RE.fullmatch(reason)
    ):
        return None
    session = str(value.get("browser_session_id", ""))
    if not _SESSION_RE.fullmatch(session):
        session = "unknown"
    request_sequence = value.get("request_sequence")
    if (
        isinstance(request_sequence, bool)
        or not isinstance(request_sequence, int)
        or not 0 < request_sequence <= 9_007_199_254_740_991
    ):
        request_sequence = None
    raw_targets = value.get("targets")
    targets = {
        str(key): str(item)
        for key, item in list(raw_targets.items())[:8]
        if _EVENT_RE.fullmatch(str(key))
        and _OPAQUE_ID_RE.fullmatch(str(item))
    } if isinstance(raw_targets, dict) else {}
    return {
        "schema": EVENT_SCHEMA,
        "event_id": event_id,
        "timestamp": timestamp,
        "browser_session_id": session,
        "request_sequence": request_sequence,
        "event_type": event_type,
        "targets": dict(sorted(targets.items())),
        "result": result,
        "reason_code": reason,
    }


class OperatorEventTimeline:
    """Own one bounded JSONL file set with exact rotation and retention."""

    def __init__(
        self,
        root: Path,
        *,
        max_file_bytes: int = EVENT_FILE_MAX_BYTES,
        retention_files: int = EVENT_RETENTION_FILES,
    ) -> None:
        self.root = _safe_root(Path(root))
        self.path = self.root / "operator-events.jsonl"
        self.max_file_bytes = max(4_096, min(int(max_file_bytes), EVENT_FILE_MAX_BYTES))
        self.retention_files = max(1, min(int(retention_files), EVENT_RETENTION_FILES))
        self._lock = threading.RLock()
        self._sequence = self._load_last_sequence()

    def _paths_oldest_first(self) -> list[Path]:
        rotated = [
            self.root / f"operator-events.jsonl.{index}"
            for index in range(self.retention_files - 1, 0, -1)
        ]
        return rotated + [self.path]

    def _load_last_sequence(self) -> int:
        latest = 0
        for entry in self._read_entries_unlocked(EVENT_EXPORT_MAX_ENTRIES):
            value = entry.get("event_id")
            if isinstance(value, int) and 0 < value <= 9_007_199_254_740_991:
                latest = max(latest, value)
        return latest

    def _rotate_locked(self) -> None:
        oldest = self.root / f"operator-events.jsonl.{self.retention_files - 1}"
        if self.retention_files > 1 and oldest.exists():
            oldest.unlink()
        for index in range(self.retention_files - 2, 0, -1):
            source = self.root / f"operator-events.jsonl.{index}"
            target = self.root / f"operator-events.jsonl.{index + 1}"
            if source.exists():
                os.replace(source, target)
        if self.path.exists() and self.retention_files > 1:
            os.replace(self.path, self.root / "operator-events.jsonl.1")
        elif self.path.exists():
            self.path.unlink()

    def append(
        self,
        event_type: str,
        *,
        browser_session_id: str = "unknown",
        request_sequence: int | None = None,
        targets: Mapping[str, object] | None = None,
        result: str,
        reason_code: str,
        now: datetime | None = None,
    ) -> Dict[str, Any]:
        if not _EVENT_RE.fullmatch(event_type):
            raise ValueError("invalid operator event type")
        session = str(browser_session_id or "")
        if not _SESSION_RE.fullmatch(session):
            session = "unknown"
        request_seq = (
            int(request_sequence)
            if isinstance(request_sequence, int)
            and not isinstance(request_sequence, bool)
            and 0 < request_sequence <= 9_007_199_254_740_991
            else None
        )
        outcome = result if result in {"accepted", "rejected", "error"} else "error"
        reason = str(reason_code or "")
        if not _REASON_RE.fullmatch(reason):
            reason = "invalid_reason"
        safe_targets = {
            str(key): str(value)
            for key, value in list((targets or {}).items())[:8]
            if _EVENT_RE.fullmatch(str(key))
            and _OPAQUE_ID_RE.fullmatch(str(value))
        }
        with self._lock:
            self._sequence += 1
            event = {
                "schema": EVENT_SCHEMA,
                "event_id": self._sequence,
                "timestamp": _utc_timestamp(now),
                "browser_session_id": session,
                "request_sequence": request_seq,
                "event_type": event_type,
                "targets": dict(sorted(safe_targets.items())),
                "result": outcome,
                "reason_code": reason,
            }
            line = json.dumps(
                event, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode("utf-8") + b"\n"
            if len(line) > EVENT_LINE_MAX_BYTES:
                raise ValueError("operator event exceeds line budget")
            current_size = self.path.stat().st_size if self.path.exists() else 0
            if current_size + len(line) > self.max_file_bytes:
                self._rotate_locked()
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(self.path, flags, 0o600)
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError("operator event target must be a regular file")
                os.write(descriptor, line)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.chmod(self.path, 0o600)
            return dict(event)

    def _read_entries_unlocked(self, limit: int) -> list[Dict[str, Any]]:
        entries: list[Dict[str, Any]] = []
        for path in self._paths_oldest_first():
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    continue
                if info.st_size > self.max_file_bytes:
                    continue
                with path.open("rb") as stream:
                    for raw in stream:
                        if len(raw) > EVENT_LINE_MAX_BYTES:
                            continue
                        try:
                            value = json.loads(raw)
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            continue
                        projected = _project_event(value)
                        if projected is not None:
                            entries.append(projected)
            except OSError:
                continue
        return entries[-max(1, min(int(limit), EVENT_EXPORT_MAX_ENTRIES)) :]

    def recent(self, limit: int = EVENT_EXPORT_MAX_ENTRIES) -> list[Dict[str, Any]]:
        with self._lock:
            return [dict(entry) for entry in self._read_entries_unlocked(limit)]


def record_http_event(
    timeline: OperatorEventTimeline | None,
    *,
    method: str,
    path: str,
    headers: Mapping[str, str],
    status_code: int,
) -> Dict[str, Any] | None:
    """Best-effort adapter used by HTTP middleware after a response exists."""

    if timeline is None:
        return None
    classified = classify_http_event(method, path)
    if classified is None:
        return None
    event_type, targets = classified
    session = str(headers.get("x-robot-scope-browser-session", "unknown"))
    raw_sequence = str(headers.get("x-robot-scope-request-sequence", ""))
    request_sequence = (
        int(raw_sequence)
        if _REQUEST_SEQUENCE_RE.fullmatch(raw_sequence)
        else None
    )
    result = (
        "accepted"
        if 200 <= status_code < 400
        else "rejected"
        if 400 <= status_code < 500
        else "error"
    )
    reason = f"http_{status_code}" if 100 <= status_code <= 599 else "http_unknown"
    return timeline.append(
        event_type,
        browser_session_id=session,
        request_sequence=request_sequence,
        targets=targets,
        result=result,
        reason_code=reason,
    )
