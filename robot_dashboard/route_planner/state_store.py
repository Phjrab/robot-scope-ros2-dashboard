"""Private bounded persistence for the single active Route Planner session."""

from __future__ import annotations

import json
import os
import secrets
import stat
from pathlib import Path
from typing import Any, Mapping


STATE_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1024 * 1024


class RoutePlannerStorageError(RuntimeError):
    pass


def _safe_root(root: Path) -> Path:
    requested = Path(root)
    if not requested.is_absolute():
        raise RoutePlannerStorageError("route planner state root must be absolute")
    normalized = Path(os.path.abspath(str(requested)))
    if normalized == Path("/"):
        raise RoutePlannerStorageError("route planner state root cannot be filesystem root")
    probe = normalized
    missing: list[Path] = []
    while not probe.exists():
        missing.append(probe)
        if probe.parent == probe:
            raise RoutePlannerStorageError("route planner state root has no existing parent")
        probe = probe.parent
    if probe.is_symlink() or probe.resolve(strict=True) != probe:
        raise RoutePlannerStorageError("route planner state root cannot contain symlinks")
    for path in reversed(missing):
        path.mkdir(mode=0o700)
    if normalized.is_symlink() or normalized.resolve(strict=True) != normalized:
        raise RoutePlannerStorageError("route planner state root cannot contain symlinks")
    info = normalized.stat()
    if info.st_uid != os.geteuid():
        raise RoutePlannerStorageError("route planner state root must be owned by the service user")
    if missing:
        os.chmod(normalized, 0o700)
    elif stat.S_IMODE(info.st_mode) != 0o700:
        raise RoutePlannerStorageError("existing route planner state root must have mode 0700")
    return normalized


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "state": "EMPTY",
        "order": None,
        "graph": None,
        "recommendations": [],
        "selected_route_id": None,
        "selected_context": None,
        "guidance": {
            "active": False,
            "completed_pickups": [],
            "dropoff_complete": False,
            "current_segment_index": 0,
        },
        "mission_links": [],
        "error": None,
    }


class RoutePlannerStateStore:
    def __init__(self, root: Path) -> None:
        self.root = _safe_root(root)
        self.path = self.root / "route-planner.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return empty_state()
        if self.path.is_symlink():
            raise RoutePlannerStorageError("route planner state file cannot be a symlink")
        info = self.path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise RoutePlannerStorageError("route planner state file must be private")
        if info.st_size <= 0 or info.st_size > MAX_STATE_BYTES:
            raise RoutePlannerStorageError("route planner state file has invalid size")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RoutePlannerStorageError("route planner state file is unreadable") from exc
        expected = set(empty_state())
        if not isinstance(value, dict) or set(value) != expected or value.get("schema_version") != STATE_SCHEMA_VERSION:
            raise RoutePlannerStorageError("route planner state document is invalid")
        # Guidance never resumes after a process restart.
        guidance = value.get("guidance")
        if not isinstance(guidance, dict):
            raise RoutePlannerStorageError("route planner guidance state is invalid")
        value["guidance"] = {
            "active": False,
            "completed_pickups": list(guidance.get("completed_pickups", []))[:5],
            "dropoff_complete": guidance.get("dropoff_complete") is True,
            "current_segment_index": max(0, int(guidance.get("current_segment_index", 0))),
        }
        if value.get("state") == "GUIDANCE_ACTIVE":
            value["state"] = "ROUTE_SELECTED" if value.get("selected_route_id") else "RECOMMENDATIONS_READY"
        return value

    def save(self, value: Mapping[str, Any]) -> None:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_STATE_BYTES:
            raise RoutePlannerStorageError("route planner state exceeds the size limit")
        temporary = self.root / f".route-planner.{secrets.token_hex(8)}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
            directory = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


__all__ = ["MAX_STATE_BYTES", "RoutePlannerStateStore", "RoutePlannerStorageError", "empty_state"]
