"""Bounded dashboard control for the robot-side RealSense capture profile.

Only three repository-owned resolution identifiers can cross the SSH boundary.
The remote forced command owns the environment-file mutation and the fixed
camera service transition; browsers cannot provide hosts, paths, commands or
arbitrary camera parameters.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import stat
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Mapping


SSH_PATH = "/usr/bin/ssh"
ENABLED_ENV = "ROBOT_SCOPE_REALSENSE_PROFILE_CONTROL_ENABLED"
HOST_ENV = "ROBOT_SCOPE_ROBOT_GATEWAY_IP"
IDENTITY_ENV = "ROBOT_SCOPE_WIRELESS_MAPPING_SSH_IDENTITY"
KNOWN_HOSTS_ENV = "ROBOT_SCOPE_WIRELESS_MAPPING_SSH_KNOWN_HOSTS"
REMOTE_USER = "unitree"
STATUS_ACTION = "realsense-profile-status"
ALLOWED_PROFILES = {
    "320x240": (320, 240),
    "640x480": (640, 480),
    "1280x720": (1280, 720),
}
_SYSTEMD_VALUE = re.compile(r"^[A-Za-z0-9_.:@-]{1,64}$")


class RealSenseProfileError(RuntimeError):
    """Base class for expected profile-control failures."""


class RealSenseProfileUnavailable(RealSenseProfileError):
    """Raised when the fixed remote control path is not configured."""


class RealSenseProfileBlocked(RealSenseProfileError):
    """Raised when a capture operation makes a relay restart unsafe."""


class RealSenseProfileConfirmationRequired(RealSenseProfileError):
    """Raised when the operator has not confirmed the brief stream outage."""


class RealSenseProfileBusy(RealSenseProfileError):
    """Raised when another resolution transition is already running."""


Runner = Callable[[str, float], subprocess.CompletedProcess[str]]
FlagProvider = Callable[[], bool]


def _enabled(value: object) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _private_host(value: object) -> str:
    try:
        address = ipaddress.ip_address(str(value or "").strip())
    except ValueError as exc:
        raise ValueError("RealSense profile host must be a private IPv4 address") from exc
    if not isinstance(address, ipaddress.IPv4Address) or not address.is_private:
        raise ValueError("RealSense profile host must be a private IPv4 address")
    if address.is_loopback or address.is_unspecified or address.is_multicast:
        raise ValueError("RealSense profile host is not allowed")
    return str(address)


def _private_file(value: object, *, owner_required: bool) -> Path:
    path = Path(str(value or ""))
    if not path.is_absolute() or path == Path("/"):
        raise ValueError("RealSense profile SSH file must be absolute")
    details = path.lstat()
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or (owner_required and details.st_uid != os.geteuid())
        or (owner_required and stat.S_IMODE(details.st_mode) & 0o077)
        or not os.access(path, os.R_OK)
    ):
        raise ValueError("RealSense profile SSH file is not trusted")
    return path


class FixedSshRealSenseProfileRunner:
    """Dispatch only the fixed profile vocabulary through one forced SSH key."""

    def __init__(self, *, host: str, identity_file: str, known_hosts_file: str) -> None:
        self.host = _private_host(host)
        self.identity_file = _private_file(identity_file, owner_required=True)
        self.known_hosts_file = _private_file(known_hosts_file, owner_required=False)
        if not Path(SSH_PATH).is_file() or not os.access(SSH_PATH, os.X_OK):
            raise ValueError("SSH executable is unavailable")

    def _command(self, action: str) -> tuple[str, ...]:
        allowed = {STATUS_ACTION, *(f"realsense-profile-{item}" for item in ALLOWED_PROFILES)}
        if action not in allowed:
            raise ValueError("RealSense profile action is not allowlisted")
        return (
            SSH_PATH,
            "-F",
            "/dev/null",
            "-T",
            "-i",
            str(self.identity_file),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self.known_hosts_file}",
            "-o",
            "ConnectTimeout=3",
            "--",
            f"{REMOTE_USER}@{self.host}",
            action,
        )

    def __call__(self, action: str, timeout_seconds: float) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self._command(action),
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout_seconds,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"},
        )


def parse_profile_status(value: object) -> dict[str, Any]:
    """Validate the complete bounded status emitted by the forced command."""

    try:
        payload = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError as exc:
        raise ValueError("RealSense profile status is not valid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema",
        "profile",
        "width",
        "height",
        "fps",
        "jpeg_quality",
        "service",
    }:
        raise ValueError("RealSense profile status fields are invalid")
    profile_value = payload.get("profile")
    if not isinstance(profile_value, str):
        raise ValueError("RealSense profile status resolution is invalid")
    profile = profile_value
    dimensions = ALLOWED_PROFILES.get(profile)
    if dimensions is None or (payload.get("width"), payload.get("height")) != dimensions:
        raise ValueError("RealSense profile status resolution is invalid")
    if payload.get("schema") != "robot-scope.realsense-profile.v1":
        raise ValueError("RealSense profile status schema is invalid")
    fps = payload.get("fps")
    quality = payload.get("jpeg_quality")
    if isinstance(fps, bool) or fps not in {5, 10, 15, 30}:
        raise ValueError("RealSense profile status FPS is invalid")
    if isinstance(quality, bool) or not isinstance(quality, int) or not 40 <= quality <= 90:
        raise ValueError("RealSense profile status quality is invalid")
    service = payload.get("service")
    if not isinstance(service, dict) or set(service) != {"load", "active", "sub"}:
        raise ValueError("RealSense profile service status is invalid")
    if any(not _SYSTEMD_VALUE.fullmatch(str(service.get(key, ""))) for key in service):
        raise ValueError("RealSense profile service value is invalid")
    return {
        "schema": payload["schema"],
        "profile": profile,
        "width": dimensions[0],
        "height": dimensions[1],
        "fps": fps,
        "jpeg_quality": quality,
        "service": {key: str(service[key]) for key in ("load", "active", "sub")},
    }


class RealSenseProfileManager:
    """Validate status and serialize one fixed robot-side profile transition."""

    def __init__(
        self,
        *,
        enabled: bool,
        runner: Runner | None = None,
        dataset_active: FlagProvider | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.runner = runner
        self.dataset_active = dataset_active or (lambda: False)
        self._lock = threading.RLock()
        self._last_error = ""

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        dataset_active: FlagProvider | None = None,
    ) -> "RealSenseProfileManager":
        values = os.environ if environ is None else environ
        enabled = _enabled(values.get(ENABLED_ENV))
        if not enabled:
            return cls(enabled=False, dataset_active=dataset_active)
        try:
            runner: Runner | None = FixedSshRealSenseProfileRunner(
                host=str(values.get(HOST_ENV, "")),
                identity_file=str(values.get(IDENTITY_ENV, "")),
                known_hosts_file=str(values.get(KNOWN_HOSTS_ENV, "")),
            )
        except (OSError, ValueError):
            runner = None
        return cls(enabled=True, runner=runner, dataset_active=dataset_active)

    def _status(self) -> dict[str, Any] | None:
        if self.runner is None:
            return None
        try:
            result = self.runner(STATUS_ACTION, 5.0)
            if result.returncode != 0 or len(result.stdout) > 2048:
                return None
            return parse_profile_status(result.stdout)
        except (OSError, ValueError, subprocess.SubprocessError):
            return None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            status = self._status()
            dataset_active = True
            try:
                dataset_active = bool(self.dataset_active())
            except Exception:
                pass
            blockers = ["dataset_capture_active"] if dataset_active else []
            if self.enabled and self.runner is not None and status is None:
                blockers.append("remote_status_unavailable")
            return {
                "source_id": "realsense_color",
                "enabled": self.enabled,
                "configured": bool(self.enabled and self.runner is not None),
                "available": status is not None,
                "profiles": [
                    {"id": key, "width": width, "height": height}
                    for key, (width, height) in ALLOWED_PROFILES.items()
                ],
                "selected": status,
                "blockers": blockers,
                "can_apply": bool(status is not None and not blockers),
                "last_error": self._last_error,
            }

    def apply(self, profile: str, *, confirmed: bool) -> dict[str, Any]:
        if confirmed is not True:
            raise RealSenseProfileConfirmationRequired("confirmed=true is required")
        if profile not in ALLOWED_PROFILES:
            raise RealSenseProfileUnavailable("RealSense profile is not allowlisted")
        if not self.enabled or self.runner is None:
            raise RealSenseProfileUnavailable("RealSense profile control is unavailable")
        if not self._lock.acquire(blocking=False):
            raise RealSenseProfileBusy("another RealSense profile change is active")
        try:
            try:
                if self.dataset_active():
                    raise RealSenseProfileBlocked("dataset capture is active")
            except RealSenseProfileBlocked:
                raise
            except Exception as exc:
                raise RealSenseProfileBlocked("dataset capture state is unavailable") from exc
            result = self.runner(f"realsense-profile-{profile}", 20.0)
            if result.returncode != 0 or len(result.stdout) > 2048:
                self._last_error = "remote profile transition failed"
                raise RealSenseProfileUnavailable(self._last_error)
            try:
                status = parse_profile_status(result.stdout)
            except ValueError as exc:
                self._last_error = "remote profile acknowledgement is invalid"
                raise RealSenseProfileUnavailable(self._last_error) from exc
            if status["profile"] != profile or status["service"]["active"] != "active":
                self._last_error = "remote profile was not applied"
                raise RealSenseProfileUnavailable(self._last_error)
            self._last_error = ""
            return self.snapshot()
        finally:
            self._lock.release()
