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
    pass


def acquire_producer_lock(path: Path) -> int:
    """Shared by stereo sessions and the on-demand RGB producer."""
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
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
    if not devices or not Path("/proc").is_dir():
        return False
    if any(not re.fullmatch(r"/dev/(?:video[0-9]+|bus/usb/[0-9]{3}/[0-9]{3})", p) for p in devices):
        return False
    executable = next((p for p in ("/usr/bin/fuser", "/bin/fuser") if Path(p).is_file()), None)
    if executable is None or any(not Path(p).exists() for p in devices):
        return False
    try:
        result = subprocess.run([executable, *devices], capture_output=True, timeout=3, check=False)
        return result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip()
    except (OSError, subprocess.TimeoutExpired):
        return False


class CameraOwnerCoordinator:
    def __init__(self, lock_path: Path, handoff_path: Path | None, *,
                 owner_probe: Callable[[list[str]], bool] = devices_free,
                 wall_clock: Callable[[], float] = time.time) -> None:
        self.lock_path = lock_path
        self.handoff_path = handoff_path
        self._probe = owner_probe
        self._clock = wall_clock
        self._fd: int | None = None
        self._owner: tuple[str, int] | None = None

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
            age = self._clock() - float(value["checked_at_epoch"])
            if not (0 <= age <= 300) or value.get("relay_released") is not True or value.get("lock_protocol") != "robot-scope-camera-v1":
                raise CameraBusy("CAMERA_HANDOFF_REQUIRED")
            devices = value["devices"]
            if not isinstance(devices, list) or not 1 <= len(devices) <= 16 or not all(isinstance(p, str) for p in devices):
                raise CameraBusy("CAMERA_HANDOFF_REQUIRED")
            self.lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = acquire_producer_lock(self.lock_path)
            try:
                # Check after reservation; every cooperating producer uses this lock.
                if not self._probe(devices):
                    raise CameraBusy("CAMERA_BUSY")
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
