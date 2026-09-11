#!/usr/bin/env python3
"""Restricted robot-side lifecycle/status command for wireless mapping inputs."""

from __future__ import annotations

import os
import json
import re
import stat
import subprocess
import sys
import time
from pathlib import Path


SYSTEMCTL = "/usr/bin/systemctl"
JOURNALCTL = "/usr/bin/journalctl"
TIMEDATECTL = "/usr/bin/timedatectl"
SUDO = "/usr/bin/sudo"
RELAY_SERVICE = "robot-scope-xt16-wireless-relay.service"
IMU_SERVICE = "robot-scope-wireless-imu-sender.service"
ODOM_SERVICE = "robot-scope-wireless-odom-sender.service"
REALSENSE_SERVICE = "robot-scope-realsense-camera.service"
REALSENSE_ENV_FILE = Path("/home/unitree/.config/robot-scope/realsense-camera.env")
SERVICES = {"relay": RELAY_SERVICE, "imu": IMU_SERVICE, "odom": ODOM_SERVICE}
REALSENSE_PROFILES = {
    "320x240": (320, 240),
    "640x480": (640, 480),
    "1280x720": (1280, 720),
}
REALSENSE_ALLOWED_FPS = {5, 10, 15, 30}
REALSENSE_MAX_ENV_BYTES = 8192
FIXED_ENVIRONMENT = {
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
}
_COUNT = r"[0-9]{1,20}"
_AGE = r"(?:none|[0-9]{1,6}\.[0-9]{3})"
_REJECTS = rf"(?:none|[a-z_]+:{_COUNT}(?:,[a-z_]+:{_COUNT})*)"
_RELAY_HEALTH_LINE = re.compile(
    rf"^\[Robot Scope wireless XT16 relay\] (?:periodic|final) "
    rf"captured={_COUNT} accepted={_COUNT} forwarded={_COUNT} "
    rf"bytes={_COUNT} send_errors={_COUNT} seq_lost={_COUNT} "
    rf"seq_duplicate={_COUNT} seq_reordered={_COUNT} "
    rf"last_accepted_age_s={_AGE} last_forwarded_age_s={_AGE} "
    rf"rejected={_COUNT}\({_REJECTS}\)$"
)
_REALSENSE_KEYS = {
    "ROBOT_SCOPE_REALSENSE_WIDTH",
    "ROBOT_SCOPE_REALSENSE_HEIGHT",
    "ROBOT_SCOPE_REALSENSE_FPS",
    "ROBOT_SCOPE_REALSENSE_JPEG_QUALITY",
}


def _run_fixed(
    command: tuple[str, ...], *, capture: bool = False, timeout: float = 5.0
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        shell=False,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=timeout,
        env=FIXED_ENVIRONMENT,
    )


def _read_realsense_environment() -> tuple[bytes, list[str], dict[str, str]]:
    details = REALSENSE_ENV_FILE.lstat()
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_uid != os.geteuid()
        or details.st_nlink != 1
        or stat.S_IMODE(details.st_mode) & 0o077
        or details.st_size < 1
        or details.st_size > REALSENSE_MAX_ENV_BYTES
    ):
        raise ValueError("untrusted RealSense environment file")
    raw = REALSENSE_ENV_FILE.read_bytes()
    if len(raw) != details.st_size or b"\0" in raw:
        raise ValueError("invalid RealSense environment file")
    lines = raw.decode("utf-8").splitlines()
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if not separator or key in values:
            raise ValueError("invalid RealSense environment assignment")
        if key in _REALSENSE_KEYS:
            values[key] = value
    if set(values) != _REALSENSE_KEYS:
        raise ValueError("incomplete RealSense environment profile")
    return raw, lines, values


def _validated_realsense_values(values: dict[str, str]) -> tuple[str, int, int]:
    try:
        width = int(values["ROBOT_SCOPE_REALSENSE_WIDTH"], 10)
        height = int(values["ROBOT_SCOPE_REALSENSE_HEIGHT"], 10)
        fps = int(values["ROBOT_SCOPE_REALSENSE_FPS"], 10)
        quality = int(values["ROBOT_SCOPE_REALSENSE_JPEG_QUALITY"], 10)
    except ValueError as exc:
        raise ValueError("invalid RealSense numeric profile") from exc
    profile = next(
        (key for key, dimensions in REALSENSE_PROFILES.items() if dimensions == (width, height)),
        "",
    )
    if not profile or fps not in REALSENSE_ALLOWED_FPS or not 40 <= quality <= 90:
        raise ValueError("RealSense profile is outside the allowlist")
    return profile, fps, quality


def _write_realsense_environment(lines: list[str], width: int, height: int) -> bytes:
    replacements = {
        "ROBOT_SCOPE_REALSENSE_WIDTH": str(width),
        "ROBOT_SCOPE_REALSENSE_HEIGHT": str(height),
    }
    output: list[str] = []
    replaced: set[str] = set()
    for line in lines:
        stripped = line.strip()
        key, separator, _value = stripped.partition("=")
        if separator and key in replacements:
            output.append(f"{key}={replacements[key]}")
            replaced.add(key)
        else:
            output.append(line)
    if replaced != set(replacements):
        raise ValueError("RealSense resolution assignment is missing")
    return ("\n".join(output) + "\n").encode("utf-8")


def _atomic_replace_realsense_environment(payload: bytes) -> None:
    directory = REALSENSE_ENV_FILE.parent
    name = f".{REALSENSE_ENV_FILE.name}.robot-scope-{os.getpid()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    directory_fd = os.open(directory, os.O_RDONLY)
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)
    temporary = directory / name
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, REALSENSE_ENV_FILE)
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _realsense_systemd() -> dict[str, str]:
    result = _run_fixed(
        (
            SYSTEMCTL,
            "show",
            "--property=LoadState",
            "--property=ActiveState",
            "--property=SubState",
            REALSENSE_SERVICE,
        ),
        capture=True,
    )
    if result.returncode != 0:
        raise RuntimeError("RealSense service status unavailable")
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if set(values) != {"LoadState", "ActiveState", "SubState"}:
        raise RuntimeError("RealSense service status invalid")
    return {"load": values["LoadState"], "active": values["ActiveState"], "sub": values["SubState"]}


def _realsense_status() -> dict[str, object]:
    _raw, _lines, values = _read_realsense_environment()
    profile, fps, quality = _validated_realsense_values(values)
    width, height = REALSENSE_PROFILES[profile]
    return {
        "schema": "robot-scope.realsense-profile.v1",
        "profile": profile,
        "width": width,
        "height": height,
        "fps": fps,
        "jpeg_quality": quality,
        "service": _realsense_systemd(),
    }


def _wait_realsense_state(active: str, sub: str, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status = _realsense_systemd()
        except RuntimeError:
            status = {}
        if status.get("active") == active and status.get("sub") == sub:
            return True
        time.sleep(0.1)
    return False


def _cycle_realsense_service() -> bool:
    stopped = _run_fixed((SUDO, "-n", SYSTEMCTL, "--no-block", "stop", REALSENSE_SERVICE))
    if stopped.returncode != 0 or not _wait_realsense_state("inactive", "dead", 5.0):
        return False
    started = _run_fixed((SUDO, "-n", SYSTEMCTL, "--no-block", "start", REALSENSE_SERVICE))
    return started.returncode == 0 and _wait_realsense_state("active", "running", 8.0)


def _apply_realsense_profile(profile: str) -> dict[str, object]:
    dimensions = REALSENSE_PROFILES.get(profile)
    if dimensions is None:
        raise ValueError("RealSense profile is not allowlisted")
    original, lines, values = _read_realsense_environment()
    _validated_realsense_values(values)
    updated = _write_realsense_environment(lines, *dimensions)
    if updated != original:
        _atomic_replace_realsense_environment(updated)
        if not _cycle_realsense_service():
            _atomic_replace_realsense_environment(original)
            _cycle_realsense_service()
            raise RuntimeError("RealSense service transition failed")
    status = _realsense_status()
    service = status.get("service")
    if (
        status.get("profile") != profile
        or not isinstance(service, dict)
        or service.get("active") != "active"
    ):
        raise RuntimeError("RealSense profile acknowledgement failed")
    return status


def _relay_health_lines(output: str) -> tuple[str, str] | None:
    lines = [
        line
        for line in output.splitlines()
        if len(line) <= 1024 and _RELAY_HEALTH_LINE.fullmatch(line)
    ]
    if len(lines) < 2:
        return None
    return lines[-2], lines[-1]


def command_for(action: str) -> tuple[tuple[str, ...], bool] | None:
    if action == "clock-status":
        return (
            (TIMEDATECTL, "show", "--property=NTPSynchronized", "--value"),
            True,
        )
    if action == "relay-health":
        return (
            (
                SUDO,
                "-n",
                JOURNALCTL,
                "--no-pager",
                "-o",
                "cat",
                "--since=-15s",
                "-n",
                "32",
                "-u",
                RELAY_SERVICE,
            ),
            True,
        )
    for label, service in SERVICES.items():
        if action == f"{label}-status":
            return (
                (
                    SYSTEMCTL,
                    "show",
                    "--property=ActiveState",
                    "--property=SubState",
                    "--property=LoadState",
                    service,
                ),
                True,
            )
        if action == f"{label}-start":
            return ((SUDO, "-n", SYSTEMCTL, "--no-block", "start", service), False)
        if action == f"{label}-stop":
            return ((SUDO, "-n", SYSTEMCTL, "--no-block", "stop", service), False)
    return None


def main() -> int:
    action = os.environ.get("SSH_ORIGINAL_COMMAND", "").strip()
    if action == "realsense-profile-status":
        try:
            print(json.dumps(_realsense_status(), separators=(",", ":")))
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            return 1
        return 0
    prefix = "realsense-profile-"
    if action.startswith(prefix):
        try:
            print(json.dumps(_apply_realsense_profile(action[len(prefix) :]), separators=(",", ":")))
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            return 1
        return 0
    resolved = command_for(action)
    if resolved is None:
        return 2
    command, expose_stdout = resolved
    try:
        capture_health = action == "relay-health"
        completed = subprocess.run(
            command,
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=(
                subprocess.PIPE
                if capture_health
                else None if expose_stdout else subprocess.DEVNULL
            ),
            stderr=subprocess.DEVNULL,
            text=capture_health,
            timeout=5.0,
            env=FIXED_ENVIRONMENT,
        )
    except (OSError, subprocess.SubprocessError):
        return 1
    if capture_health:
        lines = _relay_health_lines(completed.stdout)
        if completed.returncode != 0 or lines is None:
            return 1
        print(*lines, sep="\n")
    return int(completed.returncode)


if __name__ == "__main__":
    sys.exit(main())
