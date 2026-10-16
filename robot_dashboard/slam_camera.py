"""Cooperative device exclusion; a free flock alone is never a handoff."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from typing import Any, Callable


class CameraBusy(RuntimeError):
    def __init__(self, code: str, *, reason: str | None = None) -> None:
        self.code = code
        self.status = 409
        self.resources = [{"resource": "camera", "reason": reason or code.lower()}]
        super().__init__(code)


def acquire_producer_lock(path: Path) -> int:
    """Shared by stereo sessions and the on-demand RGB producer."""
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise CameraBusy("CAMERA_BUSY")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except (OSError, CameraBusy) as exc:
        os.close(fd)
        raise CameraBusy("CAMERA_BUSY") from exc


def release_producer_lock(fd: int) -> None:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def devices_free(devices: list[str]) -> bool:
    """Bounded OS ownership check, failing closed on unsupported/partial checks."""
    return device_owner_state(devices) == "free"


def device_owner_state(devices: list[str]) -> str:
    """Legacy bounded fuser observation; managed starts use the root helper."""
    if not devices or not Path("/proc").is_dir():
        return "unavailable"
    if any(not isinstance(p, str) or not re.fullmatch(r"/dev/(?:video[0-9]+|bus/usb/[0-9]{3}/[0-9]{3})", p) for p in devices):
        return "unavailable"
    executable = next((p for p in ("/usr/bin/fuser", "/bin/fuser") if Path(p).is_file()), None)
    if executable is None or any(not Path(p).exists() for p in devices):
        return "unavailable"
    try:
        result = subprocess.run([executable, *devices], capture_output=True, timeout=3, check=False)
        if result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip():
            return "free"
        return "occupied" if result.returncode == 0 and result.stdout.strip() else "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


class CameraOwnerCoordinator:
    def __init__(self, lock_path: Path, handoff_path: Path | None, *,
                 owner_probe: Callable[[list[str]], bool] | None = None,
                 relay_probe: Callable[[Path], bool] | None = None,
                 wall_clock: Callable[[], float] = time.time) -> None:
        self.lock_path = lock_path
        self.handoff_path = handoff_path
        self._probe = owner_probe
        self._clock = wall_clock
        self._relay_probe = relay_probe
        self._fd: int | None = None
        self._owner: tuple[str, int] | None = None
        self._reservation: dict[str, Any] | None = None

    def acquire(self, session: dict[str, Any]) -> None:
        if self._owner is not None:
            raise CameraBusy("CAMERA_BUSY")
        try:
            if self.handoff_path is None:
                raise CameraBusy("CAMERA_HANDOFF_REQUIRED")
            info = self.handoff_path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid() or info.st_size > 16384:
                raise CameraBusy("CAMERA_HANDOFF_REQUIRED")
            value = json.loads(self.handoff_path.read_text())
            # A managed scope is policy, not a claim that the device is free.
            # Keep legacy expiring handoffs unchanged for unmanaged callers.
            managed = value.get("lock_protocol") == "robot-scope-camera-managed-v1"
            scope = None
            if managed:
                from robot_dashboard.slam_managed_scope import load_managed_scope
                scope = load_managed_scope(self.handoff_path, camera_lock_path=self.lock_path)
            else:
                age = self._clock() - float(value["checked_at_epoch"])
                if not (0 <= age <= 300) or value.get("relay_released") is not True or value.get("lock_protocol") != "robot-scope-camera-v1":
                    raise CameraBusy("CAMERA_HANDOFF_REQUIRED")
            devices = scope["devices"] if scope is not None else value["devices"]
            if not isinstance(devices, list) or not 1 <= len(devices) <= 16 or not all(isinstance(p, str) for p in devices):
                raise CameraBusy("CAMERA_HANDOFF_REQUIRED")
            self.lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                fd = acquire_producer_lock(self.lock_path)
            except CameraBusy as exc:
                if managed:
                    raise CameraBusy("RESOURCE_CONFLICT", reason="reservation_unavailable") from exc
                raise
            try:
                # Check after reservation; every cooperating producer uses this lock.
                if managed:
                    from robot_dashboard.slam_managed_scope import cooperative_relay_ready, lock_evidence
                    relay_probe = self._relay_probe or (lambda _: cooperative_relay_ready(scope))
                    if not relay_probe(self.lock_path):
                        raise CameraBusy("RESOURCE_CONFLICT", reason="relay_not_cooperative")
                report = None
                if self._probe is not None:
                    state = "free" if self._probe(devices) else "occupied"
                elif managed:
                    from robot_dashboard.slam_managed_scope import probe_managed_camera_owner
                    report = probe_managed_camera_owner(scope)
                    state = report["state"]
                else:
                    state = device_owner_state(devices)
                if state != "free":
                    raise CameraBusy("RESOURCE_CONFLICT" if managed else "CAMERA_BUSY",
                                     reason="device_busy" if state == "occupied" else "owner_state_unavailable")
                if managed:
                    assert scope is not None
                    self._reservation = {"scope_id": scope["scope_id"], "scope_sha256": scope["scope_sha256"],
                        "devices": list(devices), "camera_lock": lock_evidence(fd, self.lock_path),
                        "checked_at_epoch": report["checked_at_epoch"] if report else self._clock(),
                        "checked_at_monotonic": report["checked_at_monotonic"] if report else time.monotonic(),
                        "owner_pid": os.getpid(), "owner_uid": os.geteuid()}
                self._fd = fd
                self._owner = (session["session_id"], session["generation"])
            except BaseException:
                release_producer_lock(fd)
                raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CameraBusy("CAMERA_HANDOFF_REQUIRED") from exc

    def release(self, session: dict[str, Any]) -> None:
        if self._owner != (session["session_id"], session["generation"]):
            raise CameraBusy("CAMERA_OWNER_MISMATCH")
        if self._fd is not None:
            release_producer_lock(self._fd)
        self._fd = None
        self._owner = None
        self._reservation = None

    def reservation_proof(self, session: dict[str, Any]) -> dict[str, Any]:
        """Return the original successful probe; never refresh its timestamp."""
        if self._owner != (session["session_id"], session["generation"]) or self._fd is None or self._reservation is None:
            raise CameraBusy("RESOURCE_CONFLICT", reason="managed_reservation_missing")
        from robot_dashboard.slam_managed_scope import lock_evidence
        current = lock_evidence(self._fd, self.lock_path)
        if current != self._reservation["camera_lock"]:
            raise CameraBusy("RESOURCE_CONFLICT", reason="reservation_lock_changed")
        from copy import deepcopy
        return deepcopy(self._reservation)

    def release_if_owned(self, session: dict[str, Any]) -> None:
        """Reconcile a failed acquisition without touching a foreign producer.

        Local acquisition is synchronous, so no matching owner conclusively
        means this session did not retain the lock. Ordinary release remains
        strict for reservations the caller knows it owns.
        """
        if self._owner == (session["session_id"], session["generation"]):
            self.release(session)

    def snapshot(self) -> dict[str, Any]:
        return {"reserved": self._owner is not None,
                "session_id": self._owner[0] if self._owner else None,
                "generation": self._owner[1] if self._owner else None,
                "rgb_available": self._owner is None}
