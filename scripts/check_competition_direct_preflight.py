#!/usr/bin/env python3
"""Fail-closed, read-only preflight for the Track C direct-wired profile."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable, Mapping, Sequence


PROFILE = "competition-pdf-direct"
ROBOT_IP = "192.168.123.161"
XT16_IP = "192.168.123.20"
IP = "/usr/bin/ip"
PING = "/usr/bin/ping"
FORBIDDEN_PROCESS_MARKERS = (
    "run_wireless_odom_receiver_humble.sh",
    "run_wireless_odom_sender_foxy.sh",
    "wireless_odom_receiver_humble.py",
    "wireless_odom_sender_foxy.py",
)
BASE_TOPICS = {
    "/lowstate": "unitree_go/msg/LowState",
    "/utlidar/robot_odom": "nav_msgs/msg/Odometry",
    "/utlidar/imu": "sensor_msgs/msg/Imu",
    "/utlidar/cloud": "sensor_msgs/msg/PointCloud2",
}
NAVIGATION_TOPICS = {
    **BASE_TOPICS,
    "/lidar_points": "sensor_msgs/msg/PointCloud2",
    "/velodyne_points": "sensor_msgs/msg/PointCloud2",
    "/imu/body": "sensor_msgs/msg/Imu",
    "/Odometry": "nav_msgs/msg/Odometry",
}


class PreflightError(RuntimeError):
    """Expected safety preflight failure."""


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run(
    argv: Sequence[str],
    *,
    runner: Runner = subprocess.run,
    timeout: float = 5.0,
) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            tuple(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(tuple(argv), 124, "", "")


def validate_environment(environment: Mapping[str, str]) -> tuple[str, str]:
    if environment.get("ROBOT_SCOPE_MAPPING_PROFILE") != PROFILE:
        raise PreflightError("TRACK C PREFLIGHT BLOCKED: explicit profile is required")
    if environment.get("ROS_DISTRO") != "humble":
        raise PreflightError("TRACK C PREFLIGHT BLOCKED: ROS 2 Humble is required")
    if environment.get("RMW_IMPLEMENTATION") != "rmw_cyclonedds_cpp":
        raise PreflightError("TRACK C PREFLIGHT BLOCKED: CycloneDDS is required")
    interface = environment.get("ROBOT_SCOPE_GO2_INTERFACE", "")
    cidr = environment.get("ROBOT_SCOPE_GO2_INTERFACE_CIDR", "")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}", interface):
        raise PreflightError("TRACK C PREFLIGHT BLOCKED: direct interface is invalid")
    if not re.fullmatch(r"192\.168\.123\.[0-9]{1,3}/24", cidr):
        raise PreflightError("TRACK C PREFLIGHT BLOCKED: direct interface CIDR is invalid")
    return interface, cidr


def check_interface(
    interface: str,
    cidr: str,
    *,
    runner: Runner = subprocess.run,
) -> None:
    result = _run((IP, "-j", "address", "show", "dev", interface), runner=runner)
    if result.returncode != 0:
        raise PreflightError("TRACK C PREFLIGHT BLOCKED: direct interface is unavailable")
    try:
        records = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise PreflightError(
            "TRACK C PREFLIGHT BLOCKED: direct interface state is unreadable"
        ) from exc
    expected_ip, expected_prefix = cidr.rsplit("/", 1)
    addresses = [
        (item.get("local"), str(item.get("prefixlen")))
        for record in records
        for item in record.get("addr_info", [])
        if isinstance(item, dict)
    ]
    if (expected_ip, expected_prefix) not in addresses:
        raise PreflightError("TRACK C PREFLIGHT BLOCKED: direct interface CIDR is absent")


def check_reachability(*, runner: Runner = subprocess.run) -> None:
    for address, label in ((ROBOT_IP, "Go2"), (XT16_IP, "XT16")):
        result = _run((PING, "-n", "-c", "1", "-W", "1", address), runner=runner)
        if result.returncode != 0:
            raise PreflightError(f"TRACK C PREFLIGHT BLOCKED: direct {label} link is down")


def check_no_wireless_odom_processes(proc_root: Path = Path("/proc")) -> None:
    try:
        entries = tuple(proc_root.iterdir())
    except OSError as exc:
        raise PreflightError("TRACK C PREFLIGHT BLOCKED: process state is unreadable") from exc
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="replace"
            )
        except OSError:
            continue
        if any(marker in command for marker in FORBIDDEN_PROCESS_MARKERS):
            raise PreflightError(
                "TRACK C PREFLIGHT BLOCKED: wireless odometry transport is running"
            )


def check_topics(
    expected: Mapping[str, str],
    *,
    runner: Runner = subprocess.run,
    ros2: str | None = None,
) -> None:
    ros2_command = ros2 or shutil.which("ros2")
    if not ros2_command or not Path(ros2_command).is_absolute():
        raise PreflightError("TRACK C PREFLIGHT BLOCKED: ros2 command is unavailable")
    for topic, message_type in expected.items():
        result = _run((ros2_command, "topic", "info", topic, "--verbose"), runner=runner)
        if result.returncode != 0:
            raise PreflightError(f"TRACK C PREFLIGHT BLOCKED: {topic} is unavailable")
        if f"Type: {message_type}" not in result.stdout:
            raise PreflightError(f"TRACK C PREFLIGHT BLOCKED: {topic} type mismatch")
        match = re.search(r"^Publisher count:\s*(\d+)\s*$", result.stdout, re.MULTILINE)
        if match is None or int(match.group(1)) != 1:
            raise PreflightError(
                f"TRACK C PREFLIGHT BLOCKED: {topic} must have one publisher"
            )


def check(
    stage: str,
    *,
    environment: Mapping[str, str] = os.environ,
    runner: Runner = subprocess.run,
    proc_root: Path = Path("/proc"),
    ros2: str | None = None,
) -> None:
    interface, cidr = validate_environment(environment)
    check_interface(interface, cidr, runner=runner)
    check_reachability(runner=runner)
    check_no_wireless_odom_processes(proc_root)
    topics = BASE_TOPICS if stage == "base" else NAVIGATION_TOPICS
    check_topics(topics, runner=runner, ros2=ros2)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("base", "navigation"), required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        check(args.stage)
    except PreflightError as exc:
        print(f"[Robot Scope] {exc}")
        return 2
    print(f"[Robot Scope] Track C direct preflight passed | stage={args.stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
