"""Fail-closed Competition Cockpit operation mode and configuration lock."""

from __future__ import annotations

import copy
import json
import os
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping


COMPETITION_SCHEMA = "robot-scope.competition-state/v1"
OPERATION_MODES = frozenset({"MANUAL", "ASSISTED", "AUTO", "SAFE_STOP", "SHADOW"})
ENABLED_OPERATION_MODES = frozenset({"MANUAL", "SHADOW"})


class CompetitionError(RuntimeError):
    """Base error for bounded competition-state operations."""


class CompetitionConflict(CompetitionError):
    pass


class CompetitionConfirmationRequired(CompetitionError):
    pass


class CompetitionUnavailable(CompetitionError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_root(root: Path) -> Path:
    requested = Path(root).expanduser()
    if not requested.is_absolute():
        raise CompetitionUnavailable("competition state root must be absolute")
    normalized = Path(os.path.abspath(str(requested)))
    if normalized == Path("/"):
        raise CompetitionUnavailable("competition state root cannot be filesystem root")
    probe = normalized
    missing: list[Path] = []
    while not probe.exists():
        missing.append(probe)
        if probe.parent == probe:
            raise CompetitionUnavailable("competition state root has no existing parent")
        probe = probe.parent
    if probe.is_symlink() or probe.resolve(strict=True) != probe:
        raise CompetitionUnavailable("competition state root cannot contain symlinks")
    for path in reversed(missing):
        path.mkdir(mode=0o700)
    if normalized.is_symlink() or normalized.resolve(strict=True) != normalized:
        raise CompetitionUnavailable("competition state root cannot contain symlinks")
    info = normalized.stat()
    if info.st_uid != os.geteuid():
        raise CompetitionUnavailable("competition state root must be owned by the service user")
    if missing:
        os.chmod(normalized, 0o700)
    elif stat.S_IMODE(info.st_mode) != 0o700:
        raise CompetitionUnavailable("existing competition state root must have mode 0700")
    return normalized


class CompetitionStateManager:
    """Persist one requested mode and lock without owning robot motion authority."""

    def __init__(
        self,
        root: Path,
        *,
        blockers_provider: Callable[[], Mapping[str, bool]] | None = None,
        control_provider: Callable[[], Mapping[str, Any]] | None = None,
    ) -> None:
        self.root = _safe_root(Path(root))
        self.path = self.root / "state.json"
        self._blockers_provider = blockers_provider or (lambda: {})
        self._control_provider = control_provider or (lambda: {})
        self._lock = threading.RLock()
        if self.path.exists():
            self._state = self._read()
        else:
            self._state = {
                "schema_version": COMPETITION_SCHEMA,
                "requested_mode": "MANUAL",
                "locked": False,
                "revision": 1,
                "updated_at": _utc_now(),
            }
            self._write(self._state)

    def _validate(self, value: object) -> Dict[str, Any]:
        if not isinstance(value, dict) or set(value) != {
            "schema_version", "requested_mode", "locked", "revision", "updated_at"
        }:
            raise CompetitionUnavailable("competition state file is invalid")
        if value.get("schema_version") != COMPETITION_SCHEMA:
            raise CompetitionUnavailable("competition state schema is unsupported")
        mode = value.get("requested_mode")
        if mode not in ENABLED_OPERATION_MODES:
            raise CompetitionUnavailable("competition operation mode is invalid")
        locked = value.get("locked")
        revision = value.get("revision")
        updated_at = value.get("updated_at")
        if not isinstance(locked, bool):
            raise CompetitionUnavailable("competition lock state is invalid")
        if isinstance(revision, bool) or not isinstance(revision, int) or not 0 < revision <= 9_007_199_254_740_991:
            raise CompetitionUnavailable("competition state revision is invalid")
        if not isinstance(updated_at, str) or len(updated_at) > 64 or not updated_at.endswith("Z"):
            raise CompetitionUnavailable("competition state timestamp is invalid")
        return copy.deepcopy(value)

    def _read(self) -> Dict[str, Any]:
        if self.path.is_symlink() or not self.path.is_file():
            raise CompetitionUnavailable("competition state file is unavailable")
        info = self.path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > 16_384:
            raise CompetitionUnavailable("competition state file is invalid")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise CompetitionUnavailable("competition state file must have mode 0600")
        try:
            return self._validate(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CompetitionUnavailable("competition state file is unreadable") from exc

    def _write(self, state: Mapping[str, Any]) -> None:
        payload = json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        temporary = self.root / ".state.json.new"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(temporary, flags, 0o600)
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise OSError("short competition state write")
                    view = view[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
            directory = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise CompetitionUnavailable("competition state could not be persisted") from exc

    def _blockers(self) -> list[str]:
        try:
            values = self._blockers_provider()
        except Exception as exc:
            raise CompetitionUnavailable("competition safety state is unavailable") from exc
        if not isinstance(values, Mapping):
            raise CompetitionUnavailable("competition safety state is unavailable")
        return sorted(str(key) for key, active in values.items() if active is True)

    def _control_state(self) -> tuple[bool, bool]:
        """Return (known, stop_latched) without accepting authority from cache."""

        try:
            value = self._control_provider()
        except Exception:
            return False, False
        if not isinstance(value, Mapping):
            return False, False
        stop = value.get("estop_latched")
        if stop is None and isinstance(value.get("estop"), Mapping):
            stop = value["estop"].get("latched")
        lease = value.get("lease")
        known = isinstance(stop, bool) and isinstance(lease, Mapping) and isinstance(lease.get("active"), bool)
        return known, stop is True

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            state = copy.deepcopy(self._state)
        known, stop_latched = self._control_state()
        effective_mode = "SAFE_STOP" if stop_latched or not known else state["requested_mode"]
        return {
            "schema_version": COMPETITION_SCHEMA,
            "operation_mode": effective_mode,
            "requested_mode": state["requested_mode"],
            "available_modes": list(sorted(OPERATION_MODES)),
            "enabled_modes": list(sorted(ENABLED_OPERATION_MODES)),
            "disabled_modes": {
                "ASSISTED": "hardware acceptance and competition-rule review required",
                "AUTO": "hardware acceptance and competition-rule review required",
                "SAFE_STOP": "derived safety state; cannot be selected",
            },
            "locked": state["locked"],
            "revision": state["revision"],
            "updated_at": state["updated_at"],
            "motion_authority": "NONE",
            "perception_mode": "SHADOW",
            "lock_is_physical_safety": False,
            "unlock_requirements": [
                "stationary confirmation", "DISARMED", "no active navigation or mission",
                "no active dataset capture", "no active mapping operation",
            ],
        }

    def _commit(self, **changes: Any) -> Dict[str, Any]:
        next_state = copy.deepcopy(self._state)
        next_state.update(changes)
        next_state["revision"] += 1
        next_state["updated_at"] = _utc_now()
        self._write(next_state)
        self._state = next_state
        return self.snapshot()

    def lock(self, confirmation: str) -> Dict[str, Any]:
        if confirmation != "LOCK":
            raise CompetitionConfirmationRequired("type LOCK to enable Competition Lock")
        with self._lock:
            if self._state["locked"]:
                return self.snapshot()
            return self._commit(locked=True)

    def unlock(self, confirmation: str, *, stationary_confirmed: bool) -> Dict[str, Any]:
        if confirmation != "UNLOCK" or stationary_confirmed is not True:
            raise CompetitionConfirmationRequired("UNLOCK and stationary confirmation are required")
        with self._lock:
            blockers = self._blockers()
            if blockers:
                raise CompetitionConflict("Competition Lock cannot be released: " + ", ".join(blockers))
            if not self._state["locked"]:
                return self.snapshot()
            return self._commit(locked=False)

    def set_mode(self, mode: str, confirmation: str) -> Dict[str, Any]:
        normalized = str(mode).upper()
        if normalized not in OPERATION_MODES:
            raise CompetitionConflict("unknown competition operation mode")
        if normalized not in ENABLED_OPERATION_MODES:
            raise CompetitionConflict(f"{normalized} is disabled pending hardware acceptance")
        if confirmation != normalized:
            raise CompetitionConfirmationRequired(f"type {normalized} to change operation mode")
        with self._lock:
            if self._state["locked"]:
                raise CompetitionConflict("Competition Lock blocks operation mode changes")
            blockers = self._blockers()
            if blockers:
                raise CompetitionConflict("operation mode cannot change: " + ", ".join(blockers))
            if self._state["requested_mode"] == normalized:
                return self.snapshot()
            return self._commit(requested_mode=normalized)

    def require_unlocked(self, action: str) -> None:
        with self._lock:
            if self._state["locked"]:
                raise CompetitionConflict(f"Competition Lock blocks {action}")

    def require_manual_mode(self) -> None:
        with self._lock:
            if self._state["requested_mode"] != "MANUAL":
                raise CompetitionConflict("MANUAL operation mode is required for motion authority")
