#!/usr/bin/env python3
"""Read-only, fixed-topology preflight for the wireless XT16 mapping profile."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence


EXTERNAL_INTERFACE = "eno1"
EXTERNAL_ADDRESS = "192.168.50.10"
EXTERNAL_PREFIX = 24
ROBOT_HOST = "192.168.50.30"
ROBOT_USER = "unitree"
MIN_RMEM_MAX = 8_388_608
SSH = "/usr/bin/ssh"
IP = "/usr/sbin/ip"
PING = "/usr/bin/ping"
TIMEDATECTL = "/usr/bin/timedatectl"
SYSTEMCTL = "/usr/bin/systemctl"
FIREWALL_UNIT = "robot-scope-wireless-firewall.service"
SSH_IDENTITY_ENV = "ROBOT_SCOPE_WIRELESS_MAPPING_SSH_IDENTITY"
SSH_KNOWN_HOSTS_ENV = "ROBOT_SCOPE_WIRELESS_MAPPING_SSH_KNOWN_HOSTS"

EXIT_REASONS = {
    61: "WIRELESS XT16 RELAY OFFLINE",
    62: "XT16 PACKETS STALE",
    63: "HESAI DRIVER WAITING",
    64: "WIRELESS IMU UNAUTHENTICATED",
    65: "IMU STALE",
    66: "CLOCK NOT SYNCHRONIZED",
    67: "CLOUD BRIDGE STALE",
    68: "FAST-LIO NOT READY",
    69: "WIRELESS MAPPING PREFLIGHT BLOCKED",
}

_RELAY_STATS_RE = re.compile(
    r"^\[Robot Scope wireless XT16 relay\].*\baccepted=(\d+)\s+"
    r"forwarded=(\d+).*\bsend_errors=(\d+)\b"
)
_CONFLICT_MARKERS = (
    "hesai_ros_driver_node",
    "robot_scope_wireless_imu_receiver",
    "robot_scope_xt16_cloud_bridge_node",
    "robot_scope_xt16_bridge_node",
    "start_hesai_mapping_humble.sh",
    "start_xt16_preview_humble.sh",
    "fastlio_mapping",
    "nav2_bringup",
    "navigation_launch.py",
    "/nav2_map_server/map_server",
    "/nav2_controller/controller_server",
    "/nav2_planner/planner_server",
    "/nav2_behaviors/behavior_server",
    "/nav2_bt_navigator/bt_navigator",
    "/nav2_lifecycle_manager/lifecycle_manager",
    "ros2 bag record",
)


class PreflightError(RuntimeError):
    def __init__(self, reason: str, exit_code: int) -> None:
        if EXIT_REASONS.get(exit_code) != reason:
            raise ValueError("wireless mapping failure reason is not allowlisted")
        super().__init__(reason)
        self.reason = reason
        self.exit_code = exit_code


def _run(
    argv: Sequence[str],
    *,
    timeout: float = 5.0,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    command = tuple(argv)
    try:
        return runner(
            command,
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        return subprocess.CompletedProcess(command, 124, "", "")


def _private_regular_file(raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        raise PreflightError("WIRELESS MAPPING PREFLIGHT BLOCKED", 69)
    try:
        details = path.lstat()
    except OSError as exc:
        raise PreflightError("WIRELESS MAPPING PREFLIGHT BLOCKED", 69) from exc
    if not stat.S_ISREG(details.st_mode) or path.is_symlink():
        raise PreflightError("WIRELESS MAPPING PREFLIGHT BLOCKED", 69)
    if stat.S_IMODE(details.st_mode) & 0o077 or details.st_uid != os.geteuid():
        raise PreflightError("WIRELESS MAPPING PREFLIGHT BLOCKED", 69)
    return path


def ssh_files(environment: dict[str, str]) -> tuple[Path, Path]:
    return (
        _private_regular_file(environment.get(SSH_IDENTITY_ENV, "")),
        _private_regular_file(environment.get(SSH_KNOWN_HOSTS_ENV, "")),
    )


def remote_command(
    action: str,
    *,
    environment: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    identity, known_hosts = ssh_files(environment)
    return _run(
        (
            SSH,
            "-T",
            "-i",
            str(identity),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "ConnectTimeout=3",
            "-o",
            "ConnectionAttempts=1",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={known_hosts}",
            f"{ROBOT_USER}@{ROBOT_HOST}",
            action,
        ),
        runner=runner,
    )


def _service_active(output: str) -> bool:
    values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    return (
        values.get("LoadState") == "loaded"
        and values.get("ActiveState") == "active"
        and values.get("SubState") == "running"
    )


def check_host(
    environment: dict[str, str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    proc_root: Path = Path("/proc"),
) -> None:
    firewall = _run(
        (
            SYSTEMCTL,
            "show",
            FIREWALL_UNIT,
            "--property=LoadState,ActiveState,SubState,Result,ExecMainStatus",
        ),
        runner=runner,
    )
    firewall_state = dict(
        line.split("=", 1) for line in firewall.stdout.splitlines() if "=" in line
    )
    if firewall.returncode != 0 or firewall_state != {
        "LoadState": "loaded",
        "ActiveState": "active",
        "SubState": "exited",
        "Result": "success",
        "ExecMainStatus": "0",
    }:
        raise PreflightError("WIRELESS MAPPING PREFLIGHT BLOCKED", 69)

    addresses = _run(
        (IP, "-j", "-4", "address", "show", "dev", EXTERNAL_INTERFACE), runner=runner
    )
    if addresses.returncode != 0:
        raise PreflightError("WIRELESS XT16 RELAY OFFLINE", 61)
    try:
        records = json.loads(addresses.stdout)
        owns_address = any(
            item.get("local") == EXTERNAL_ADDRESS
            and int(item.get("prefixlen", -1)) == EXTERNAL_PREFIX
            for record in records
            for item in record.get("addr_info", [])
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PreflightError("WIRELESS XT16 RELAY OFFLINE", 61) from exc
    if not owns_address:
        raise PreflightError("WIRELESS XT16 RELAY OFFLINE", 61)
    if _run((PING, "-c", "1", "-W", "1", ROBOT_HOST), runner=runner).returncode != 0:
        raise PreflightError("WIRELESS XT16 RELAY OFFLINE", 61)

    clock = _run(
        (TIMEDATECTL, "show", "--property=NTPSynchronized", "--value"), runner=runner
    )
    robot_clock = remote_command("clock-status", environment=environment, runner=runner)
    if robot_clock.returncode != 0:
        raise PreflightError("WIRELESS XT16 RELAY OFFLINE", 61)
    if (
        clock.returncode != 0
        or clock.stdout.strip().lower() != "yes"
        or robot_clock.stdout.strip().lower() != "yes"
    ):
        raise PreflightError("CLOCK NOT SYNCHRONIZED", 66)

    try:
        rmem_max = int(
            (proc_root / "sys/net/core/rmem_max").read_text(encoding="ascii").strip()
        )
    except (OSError, ValueError) as exc:
        raise PreflightError("WIRELESS MAPPING PREFLIGHT BLOCKED", 69) from exc
    if rmem_max < MIN_RMEM_MAX:
        raise PreflightError("WIRELESS MAPPING PREFLIGHT BLOCKED", 69)

    ancestors: set[int] = set()
    current = os.getpid()
    while current > 1 and current not in ancestors:
        ancestors.add(current)
        try:
            current = int((proc_root / str(current) / "stat").read_text().split()[3])
        except (OSError, ValueError, IndexError):
            break
    for command_file in proc_root.glob("[0-9]*/cmdline"):
        try:
            pid = int(command_file.parent.name)
            command = (
                command_file.read_bytes()
                .replace(b"\0", b" ")
                .decode("utf-8", "replace")
            )
        except (OSError, ValueError):
            continue
        if pid not in ancestors and any(
            marker in command for marker in _CONFLICT_MARKERS
        ):
            raise PreflightError("WIRELESS MAPPING PREFLIGHT BLOCKED", 69)


def check_remote_service(
    service: str,
    environment: dict[str, str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    if service not in {"relay", "imu"}:
        raise ValueError("unsupported remote service")
    result = remote_command(f"{service}-status", environment=environment, runner=runner)
    reason, code = (
        ("WIRELESS XT16 RELAY OFFLINE", 61)
        if service == "relay"
        else ("WIRELESS IMU UNAUTHENTICATED", 64)
    )
    if result.returncode != 0 or not _service_active(result.stdout):
        raise PreflightError(reason, code)


def check_relay_health(
    environment: dict[str, str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    check_remote_service("relay", environment, runner=runner)
    result = remote_command("relay-health", environment=environment, runner=runner)
    samples = [
        tuple(map(int, match.groups()))
        for line in result.stdout.splitlines()
        if (match := _RELAY_STATS_RE.match(line))
    ]
    if result.returncode != 0 or len(samples) != 2:
        raise PreflightError("XT16 PACKETS STALE", 62)
    first, second = samples
    if second[0] <= first[0] or second[1] <= first[1] or second[2] > first[2]:
        raise PreflightError("XT16 PACKETS STALE", 62)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check one fixed wireless mapping preflight stage."
    )
    parser.add_argument(
        "--stage", required=True, choices=("host", "relay", "imu-service")
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    options = _parser().parse_args(argv)
    environment = dict(os.environ)
    try:
        if options.stage == "host":
            check_host(environment)
        elif options.stage == "relay":
            check_relay_health(environment)
        else:
            check_remote_service("imu", environment)
    except PreflightError as exc:
        print(f"[Robot Scope] {exc.reason}", file=sys.stderr)
        return exc.exit_code
    print("[Robot Scope] wireless mapping preflight ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
