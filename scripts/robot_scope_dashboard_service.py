#!/usr/bin/env python3
"""SSH operator command for the fixed Robot Scope dashboard service.

This is an administrative recovery path, not a generic systemctl wrapper. It
accepts no unit, command, URL, shell text, or environment-file input. Mutations
match the exact sudoers entries in the dashboard operator example.
"""

from __future__ import annotations

import argparse
import fcntl
import http.client
import ipaddress
import json
import os
import re
import socket
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping, Sequence


SERVICE = "robot-scope.service"
SYSTEMCTL = "/usr/bin/systemctl"
JOURNALCTL = "/usr/bin/journalctl"
SUDO = "/usr/bin/sudo"
STATUS_PATH = "/api/v1/system/service"
HEALTH_PATH = "/api/v1/health"
DEFAULT_STATUS_PORT = 8088
PORT_CONFIG_PATH = Path("/etc/robot-scope-dashboard-operator.port")
COMMAND_TIMEOUT_SECONDS = 5.0
TRANSITION_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.25

SAFE_ENVIRONMENT = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
}
MUTATION_COMMANDS = {
    # systemctl restart also starts an inactive unit, so the operator needs
    # only the existing exact restart/stop sudoers policy.
    "start": (SUDO, "-n", SYSTEMCTL, "--no-block", "restart", SERVICE),
    "restart": (SUDO, "-n", SYSTEMCTL, "--no-block", "restart", SERVICE),
    "stop": (SUDO, "-n", SYSTEMCTL, "--no-block", "stop", SERVICE),
}
STATUS_PROPERTIES = (
    "Id",
    "LoadState",
    "UnitFileState",
    "ActiveState",
    "SubState",
    "Result",
    "MainPID",
    "InvocationID",
    "NRestarts",
)
STATUS_COMMAND = (
    SYSTEMCTL,
    "show",
    SERVICE,
    "--no-pager",
    "--property=" + ",".join(STATUS_PROPERTIES),
)
LOGS_COMMAND = (
    JOURNALCTL,
    "--unit",
    SERVICE,
    "--lines",
    "150",
    "--no-pager",
    "--output",
    "short-iso",
)


class DashboardServiceError(RuntimeError):
    """A fixed service operation could not be completed safely."""


class TransitionTimeout(DashboardServiceError):
    """Systemd did not reach the requested state within the bounded wait."""


def _run(command: Sequence[str], *, timeout: float = COMMAND_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        tuple(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        shell=False,
        timeout=timeout,
        env=SAFE_ENVIRONMENT,
    )


def _bounded_error(result: subprocess.CompletedProcess[str]) -> str:
    detail = (result.stderr or result.stdout or "command rejected").strip()
    return detail[-500:]


def _status_port() -> int:
    """Read an optional root-owned local dashboard port without sourcing env."""

    if not PORT_CONFIG_PATH.exists():
        return DEFAULT_STATUS_PORT
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(PORT_CONFIG_PATH, flags)
    except OSError as exc:
        raise DashboardServiceError("dashboard operator port config is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_size < 2
            or info.st_size > 16
            or info.st_mode & 0o022
        ):
            raise DashboardServiceError("dashboard operator port config is not trusted")
        raw = os.read(descriptor, 17)
    except OSError as exc:
        raise DashboardServiceError("dashboard operator port config is unreadable") from exc
    finally:
        os.close(descriptor)
    try:
        value = raw.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise DashboardServiceError("dashboard operator port config is malformed") from exc
    if not re.fullmatch(r"[1-9][0-9]{0,4}", value):
        raise DashboardServiceError("dashboard operator port config is malformed")
    port = int(value)
    if port > 65535:
        raise DashboardServiceError("dashboard operator port config is malformed")
    return port


def _snapshot() -> dict[str, str]:
    try:
        result = _run(STATUS_COMMAND)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DashboardServiceError("systemd status is unavailable") from exc
    if result.returncode != 0:
        raise DashboardServiceError(f"systemd status failed: {_bounded_error(result)}")
    values: dict[str, str] = {}
    for raw_line in result.stdout.splitlines():
        if "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        if key in STATUS_PROPERTIES:
            values[key] = value[:256]
    if values.get("LoadState") == "not-found" or values.get("Id") != SERVICE:
        raise DashboardServiceError(f"{SERVICE} is not installed")
    for required in ("ActiveState", "SubState", "InvocationID"):
        if required not in values:
            raise DashboardServiceError(f"systemd status omitted {required}")
    return values


def _print_snapshot(snapshot: Mapping[str, str]) -> None:
    for key in STATUS_PROPERTIES:
        if key in snapshot:
            print(f"{key}={snapshot[key]}")


def _dashboard_address() -> str:
    """Return the management address used by SSH, with a local-route fallback."""

    ssh_connection = os.environ.get("SSH_CONNECTION", "").split()
    if len(ssh_connection) == 4:
        try:
            address = ipaddress.ip_address(ssh_connection[2])
        except ValueError:
            address = None
        if address is not None and not address.is_unspecified:
            return str(address)

    # UDP connect selects a local source address without sending a datagram.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            candidate = probe.getsockname()[0]
        address = ipaddress.ip_address(candidate)
        if not address.is_unspecified:
            return str(address)
    except (OSError, ValueError):
        pass
    return "127.0.0.1"


def _dashboard_url() -> str:
    address = _dashboard_address()
    host = f"[{address}]" if ":" in address else address
    return f"http://{host}:{_status_port()}"


def _print_dashboard_url() -> None:
    print(f"[Robot Scope] dashboard URL: {_dashboard_url()}")


def _idle_preflight() -> None:
    port = _status_port()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
    try:
        connection.request(
            "GET",
            STATUS_PATH,
            headers={
                "Accept": "application/json",
                "Host": f"127.0.0.1:{port}",
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            raise DashboardServiceError("dashboard idle preflight returned a non-200 status")
        raw = response.read((64 * 1024) + 1)
        if len(raw) > 64 * 1024:
            raise DashboardServiceError("dashboard idle preflight response is too large")
        payload = json.loads(raw.decode("utf-8"))
    except DashboardServiceError:
        raise
    except (OSError, UnicodeError, ValueError, http.client.HTTPException) as exc:
        raise DashboardServiceError(
            "dashboard idle preflight is unavailable; no service change was sent"
        ) from exc
    finally:
        connection.close()
    blockers = payload.get("blockers") if isinstance(payload, dict) else None
    if not isinstance(blockers, list) or any(not isinstance(item, str) for item in blockers):
        raise DashboardServiceError("dashboard idle preflight response is malformed")
    if payload.get("service") != SERVICE:
        raise DashboardServiceError("dashboard idle preflight reported an unexpected service")
    operation = payload.get("operation")
    if operation is not None and not isinstance(operation, dict):
        raise DashboardServiceError("dashboard idle preflight response is malformed")
    if isinstance(operation, dict) and operation.get("state") in {
        "scheduled",
        "dispatching",
        "queued",
    }:
        raise DashboardServiceError("another dashboard service operation is active")
    if blockers:
        summary = ", ".join(blockers[:8])
        raise DashboardServiceError(f"active robot work blocks service change: {summary}")


def _wait_for_http_ready() -> None:
    port = _status_port()
    deadline = time.monotonic() + TRANSITION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1.0)
        try:
            connection.request(
                "GET",
                HEALTH_PATH,
                headers={"Host": f"127.0.0.1:{port}"},
            )
            response = connection.getresponse()
            response.read(1)
            if response.status == 200:
                return
        except (OSError, http.client.HTTPException):
            pass
        finally:
            connection.close()
        snapshot = _snapshot()
        if snapshot.get("ActiveState") == "failed":
            raise DashboardServiceError("dashboard entered failed state before HTTP became ready")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TransitionTimeout(
        "dashboard HTTP is not ready after 60 seconds; inspect status without retrying"
    )


def _dispatch(action: str) -> None:
    command = MUTATION_COMMANDS[action]
    try:
        result = _run(command)
    except subprocess.TimeoutExpired as exc:
        raise TransitionTimeout(
            "systemctl dispatch outcome is unknown; inspect status without retrying"
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise DashboardServiceError("systemctl dispatch is unavailable") from exc
    if result.returncode != 0:
        raise DashboardServiceError(f"systemctl dispatch failed: {_bounded_error(result)}")


def _wait_for_active(previous_invocation: str) -> dict[str, str]:
    deadline = time.monotonic() + TRANSITION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        snapshot = _snapshot()
        invocation = snapshot.get("InvocationID", "")
        if (
            snapshot.get("ActiveState") == "active"
            and invocation
            and invocation != previous_invocation
        ):
            return snapshot
        if snapshot.get("ActiveState") == "failed":
            raise DashboardServiceError("dashboard entered failed state")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TransitionTimeout(
        "dashboard transition is still pending after 60 seconds; inspect status without retrying"
    )


def _wait_for_existing_start() -> dict[str, str]:
    deadline = time.monotonic() + TRANSITION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        snapshot = _snapshot()
        if snapshot.get("ActiveState") == "active" and snapshot.get("InvocationID"):
            return snapshot
        if snapshot.get("ActiveState") in {"failed", "inactive"}:
            raise DashboardServiceError("dashboard did not complete its existing start")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TransitionTimeout(
        "dashboard start is still pending after 60 seconds; inspect status without retrying"
    )


def _wait_for_stopped() -> dict[str, str]:
    deadline = time.monotonic() + TRANSITION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        snapshot = _snapshot()
        if snapshot.get("ActiveState") == "inactive":
            return snapshot
        if snapshot.get("ActiveState") == "failed":
            raise DashboardServiceError("dashboard stopped but the unit entered failed state")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TransitionTimeout(
        "dashboard stop is still pending after 60 seconds; inspect status without retrying"
    )


@contextmanager
def _mutation_lock() -> Iterator[None]:
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    try:
        runtime_info = runtime.stat()
    except OSError:
        runtime_info = None
    if (
        not runtime.is_absolute()
        or runtime_info is None
        or not stat.S_ISDIR(runtime_info.st_mode)
        or runtime_info.st_uid != os.getuid()
    ):
        runtime = Path("/tmp")
    lock_path = runtime / f"robot-scope-dashboard-{os.getuid()}.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise DashboardServiceError("dashboard operation lock is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise DashboardServiceError("dashboard operation lock ownership is invalid")
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise DashboardServiceError("another dashboard service operation is active") from exc
        yield
    finally:
        os.close(descriptor)


def _dry_run(action: str) -> int:
    command = MUTATION_COMMANDS.get(action)
    if command is None:
        command = STATUS_COMMAND if action == "status" else LOGS_COMMAND
    print("[dry-run] " + " ".join(command))
    return 0


def execute(action: str, *, dry_run: bool = False) -> int:
    if dry_run:
        return _dry_run(action)
    if action == "status":
        snapshot = _snapshot()
        _print_snapshot(snapshot)
        if snapshot.get("ActiveState") == "active":
            _print_dashboard_url()
        return 0 if snapshot.get("ActiveState") == "active" else 3
    if action == "logs":
        try:
            result = _run(LOGS_COMMAND, timeout=10.0)
        except (OSError, subprocess.SubprocessError) as exc:
            raise DashboardServiceError("dashboard logs are unavailable") from exc
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        return result.returncode

    with _mutation_lock():
        before = _snapshot()
        state = before.get("ActiveState")
        if action == "start" and state == "active":
            _wait_for_http_ready()
            print("[Robot Scope] dashboard is already active")
            _print_snapshot(before)
            _print_dashboard_url()
            return 0
        if action == "start" and state == "activating":
            after = _wait_for_existing_start()
            _wait_for_http_ready()
            print("[Robot Scope] dashboard is active")
            _print_snapshot(after)
            _print_dashboard_url()
            return 0
        if action == "stop" and state == "inactive":
            print("[Robot Scope] dashboard is already stopped")
            _print_snapshot(before)
            return 0
        if action == "stop" and state == "failed":
            raise DashboardServiceError("dashboard is not running but the unit is failed")
        if state in {"deactivating", "reloading"}:
            raise DashboardServiceError(
                f"dashboard already has a systemd transition in progress: {state}"
            )
        if state in {"active", "activating"}:
            _idle_preflight()
        _dispatch(action)
        if action == "stop":
            after = _wait_for_stopped()
            print("[Robot Scope] dashboard is stopped")
        else:
            after = _wait_for_active(before.get("InvocationID", ""))
            _wait_for_http_ready()
            print("[Robot Scope] dashboard is active")
        _print_snapshot(after)
        if action != "stop":
            _print_dashboard_url()
        return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="robot-scope-dashboard",
        description="Manage only the fixed robot-scope.service from an SSH session.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("action", choices=("start", "stop", "restart", "status", "logs"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    options = _parser().parse_args(argv)
    try:
        return execute(options.action, dry_run=options.dry_run)
    except TransitionTimeout as exc:
        print(f"[Robot Scope] {exc}", file=sys.stderr)
        return 124
    except DashboardServiceError as exc:
        print(f"[Robot Scope] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
