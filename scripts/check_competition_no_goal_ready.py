#!/usr/bin/env python3
"""Read-only Track C checker for an already-running, goal-free Nav2 stack."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable, Mapping, Sequence


PROFILE = "competition-pdf-direct"
LIFECYCLE_NODES = (
    "/map_server",
    "/controller_server",
    "/planner_server",
    "/behavior_server",
    "/bt_navigator",
)
REQUIRED_TOPICS = (
    "/map",
    "/scan",
    "/Odometry",
    "/utlidar/robot_odom",
    "/global_costmap/costmap",
    "/local_costmap/costmap",
)
MOTION_TOPICS = (
    "/robot_scope/nav/cmd_vel_raw",
    "/api/sport/request",
)
TIMEOUT = "/usr/bin/timeout"


class NoGoalError(RuntimeError):
    """Expected no-goal readiness failure."""


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run(
    argv: Sequence[str],
    *,
    runner: Runner = subprocess.run,
    timeout: float = 6.0,
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


def check(
    *,
    environment: Mapping[str, str] = os.environ,
    runner: Runner = subprocess.run,
    ros2: str | None = None,
) -> None:
    if environment.get("ROBOT_SCOPE_MAPPING_PROFILE") != PROFILE:
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: explicit profile is required")
    if environment.get("ROS_DISTRO") != "humble":
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: ROS 2 Humble is required")
    ros2_command = ros2 or shutil.which("ros2")
    if not ros2_command or not Path(ros2_command).is_absolute():
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: ros2 command is unavailable")

    for node in LIFECYCLE_NODES:
        result = _run((ros2_command, "lifecycle", "get", node), runner=runner)
        if result.returncode != 0 or not re.search(r"\bactive\b", result.stdout):
            raise NoGoalError(f"TRACK C NO-GOAL BLOCKED: {node} is not active")

    for topic in REQUIRED_TOPICS:
        result = _run((ros2_command, "topic", "info", topic), runner=runner)
        match = re.search(r"^Publisher count:\s*(\d+)\s*$", result.stdout, re.MULTILINE)
        if result.returncode != 0 or match is None or int(match.group(1)) < 1:
            raise NoGoalError(f"TRACK C NO-GOAL BLOCKED: {topic} has no publisher")

    transform = _run(
        (
            TIMEOUT,
            "5",
            ros2_command,
            "run",
            "tf2_ros",
            "tf2_echo",
            "map",
            "base_link",
        ),
        runner=runner,
        timeout=7.0,
    )
    if transform.returncode not in (0, 124) or not all(
        marker in transform.stdout for marker in ("Translation:", "Rotation:")
    ):
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: map to base_link TF is disconnected")

    for topic in MOTION_TOPICS:
        result = _run(
            (TIMEOUT, "2", ros2_command, "topic", "echo", topic, "--once"),
            runner=runner,
            timeout=4.0,
        )
        if result.returncode == 0:
            raise NoGoalError(f"TRACK C NO-GOAL BLOCKED: unexpected output on {topic}")
        if result.returncode not in (124,):
            raise NoGoalError(f"TRACK C NO-GOAL BLOCKED: cannot monitor {topic}")


def main() -> int:
    try:
        check()
    except NoGoalError as exc:
        print(f"[Robot Scope] {exc}")
        return 2
    print("[Robot Scope] Track C no-goal readiness passed; motion outputs remained quiet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
