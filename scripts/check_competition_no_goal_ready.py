#!/usr/bin/env python3
"""Read-only staged checker for an already-running, goal-free Nav2 stack."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Callable, Mapping, Sequence
from urllib.error import URLError
from urllib.request import urlopen


PROFILE = "competition-pdf-direct"
TRACK_C2_PROFILE = "go2-xt16-wireless-competition-fastlio"
TRACK_C2_CONTROLLER_ODOM = "/robot_scope/nav/controller_odom_fastlio"
STRICT_CONTROLLER_ODOM = "/utlidar/robot_odom"
STAGES = ("prelocalization", "localized")
LIFECYCLE_NODES = (
    "/map_server",
    "/controller_server",
    "/planner_server",
    "/behavior_server",
    "/bt_navigator",
)
PRELOCALIZATION_ACTIVE_NODES = (
    "/map_server",
    "/controller_server",
)
FRESH_TOPICS = ("/scan", "/Odometry")
LOCALIZED_TOPICS = (
    "/global_costmap/costmap",
    "/local_costmap/costmap",
    "/amcl_pose",
)
RAW_COMMAND_TOPIC = "/robot_scope/nav/cmd_vel_raw"
SPORT_TOPIC = "/api/sport/request"
TIMEOUT = "/usr/bin/timeout"
CONTROL_URL = "http://127.0.0.1:8088/api/v1/control"
NAVIGATION_URL = "http://127.0.0.1:8088/api/v1/navigation"
C3_MAP_ID = "f292601e2c8b269eb635cb0f"
C3_MAP_REVISION = "7c48dd9d8d1d11fbc7ff39ccd6b854d58c7dc5863072bb548eba570e5044ea93"


class NoGoalError(RuntimeError):
    """Expected staged no-goal readiness failure."""


Runner = Callable[..., subprocess.CompletedProcess[str]]
ControlFetcher = Callable[[], Mapping[str, Any]]
NavigationFetcher = Callable[[], Mapping[str, Any]]


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


def _fetch_control() -> Mapping[str, Any]:
    try:
        with urlopen(CONTROL_URL, timeout=3.0) as response:  # noqa: S310 - fixed loopback URL
            if response.status != 200:
                raise NoGoalError("TRACK C NO-GOAL BLOCKED: control status is unavailable")
            payload = json.loads(response.read(1024 * 1024))
    except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: control status is unavailable") from exc
    if not isinstance(payload, Mapping):
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: control status is invalid")
    return payload


def _fetch_navigation() -> Mapping[str, Any]:
    try:
        with urlopen(NAVIGATION_URL, timeout=3.0) as response:  # noqa: S310 - fixed loopback URL
            if response.status != 200:
                raise NoGoalError(
                    "TRACK C NG1 BLOCKED: navigation status is unavailable"
                )
            payload = json.loads(response.read(1024 * 1024))
    except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
        raise NoGoalError(
            "TRACK C NG1 BLOCKED: navigation status is unavailable"
        ) from exc
    if not isinstance(payload, Mapping):
        raise NoGoalError("TRACK C NG1 BLOCKED: navigation status is invalid")
    return payload


def _control_is_stationary(fetcher: ControlFetcher) -> None:
    payload = fetcher()
    control = payload.get("control")
    if not isinstance(control, Mapping):
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: control snapshot is invalid")
    lease = control.get("lease")
    command = control.get("command")
    if not isinstance(lease, Mapping) or not isinstance(command, Mapping):
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: control safety fields are invalid")
    if lease.get("active") is not False:
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: control lease is active")
    if command.get("deadman") is not False:
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: deadman is active")
    for key in ("linear_x", "linear_y", "angular_z"):
        value = command.get(key)
        if isinstance(value, bool):
            raise NoGoalError("TRACK C NO-GOAL BLOCKED: command velocity is invalid")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise NoGoalError("TRACK C NO-GOAL BLOCKED: command velocity is invalid") from exc
        if not math.isfinite(number) or number != 0.0:
            raise NoGoalError("TRACK C NO-GOAL BLOCKED: command velocity is non-zero")


def _topic_has_publisher(topic: str, ros2: str, runner: Runner) -> None:
    result = _run((ros2, "topic", "info", topic), runner=runner)
    match = re.search(r"^Publisher count:\s*(\d+)\s*$", result.stdout, re.MULTILINE)
    if result.returncode != 0 or match is None or int(match.group(1)) < 1:
        raise NoGoalError(f"TRACK C NO-GOAL BLOCKED: {topic} has no publisher")


def _topic_has_exactly_one_publisher(topic: str, ros2: str, runner: Runner) -> None:
    result = _run((ros2, "topic", "info", topic), runner=runner)
    match = re.search(r"^Publisher count:\s*(\d+)\s*$", result.stdout, re.MULTILINE)
    if result.returncode != 0 or match is None or int(match.group(1)) != 1:
        raise NoGoalError(
            f"TRACK C NO-GOAL BLOCKED: {topic} must have exactly one publisher"
        )


def _localization_session_is_safe(fetcher: NavigationFetcher) -> None:
    payload = fetcher()
    session = payload.get("localization_session")
    goal = payload.get("goal")
    if not isinstance(session, Mapping) or not isinstance(goal, Mapping):
        raise NoGoalError("TRACK C NG1 BLOCKED: localization session status is invalid")
    expected = {
        "active": True,
        "mode": "localization_only",
        "state": "localized",
        "map_id": C3_MAP_ID,
        "map_revision": C3_MAP_REVISION,
        "initial_pose_count": 1,
        "goal_allowed": False,
        "motion_allowed": False,
    }
    for key, value in expected.items():
        if session.get(key) != value:
            raise NoGoalError(
                f"TRACK C NG1 BLOCKED: localization session {key} is invalid"
            )
    if str(payload.get("session_mode")) != "localization_only":
        raise NoGoalError("TRACK C NG1 BLOCKED: session mode is not localization-only")
    if str(goal.get("state", "idle")) != "idle":
        raise NoGoalError("TRACK C NG1 BLOCKED: navigation goal state is not idle")
    if int(session.get("nonzero_command_count", 0) or 0) != 0:
        raise NoGoalError("TRACK C NG1 BLOCKED: non-zero raw command was observed")


def _lifecycle_is_active(node: str, ros2: str, runner: Runner) -> None:
    result = _run(
        (TIMEOUT, "3", ros2, "lifecycle", "get", node),
        runner=runner,
        timeout=5.0,
    )
    if result.returncode != 0 or not re.search(r"\bactive\b", result.stdout):
        raise NoGoalError(f"TRACK C NO-GOAL BLOCKED: {node} is not active")


def _required_nodes_are_present(ros2: str, runner: Runner) -> None:
    result = _run((ros2, "node", "list"), runner=runner)
    nodes = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    if result.returncode != 0 or not set(LIFECYCLE_NODES).issubset(nodes):
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: a Nav2 child node is missing")


def _topic_has_fresh_sample(topic: str, ros2: str, runner: Runner) -> None:
    result = _run(
        (TIMEOUT, "3", ros2, "topic", "echo", topic, "--once"),
        runner=runner,
        timeout=5.0,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise NoGoalError(f"TRACK C NO-GOAL BLOCKED: {topic} has no fresh sample")


def _transform_available(parent: str, child: str, ros2: str, runner: Runner) -> bool:
    result = _run(
        (TIMEOUT, "3", ros2, "run", "tf2_ros", "tf2_echo", parent, child),
        runner=runner,
        timeout=5.0,
    )
    return result.returncode in (0, 124) and all(
        marker in result.stdout for marker in ("Translation:", "Rotation:")
    )


def _raw_command_is_quiet_or_zero(ros2: str, runner: Runner) -> str:
    result = _run(
        (TIMEOUT, "2", ros2, "topic", "echo", RAW_COMMAND_TOPIC, "--once"),
        runner=runner,
        timeout=4.0,
    )
    if result.returncode == 124:
        return "quiet"
    if result.returncode != 0:
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: cannot monitor raw command")
    numeric = re.findall(r"^\s*[xyz]:\s*([-+0-9.eE]+)\s*$", result.stdout, re.MULTILINE)
    if len(numeric) < 6:
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: raw command shape is invalid")
    try:
        values = [float(value) for value in numeric]
    except ValueError as exc:
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: raw command is invalid") from exc
    if any(not math.isfinite(value) or value != 0.0 for value in values):
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: non-zero raw command observed")
    return "zero_only"


def _sport_request_is_quiet(ros2: str, runner: Runner) -> None:
    listed = _run((ros2, "topic", "list"), runner=runner)
    topics = {line.strip() for line in listed.stdout.splitlines() if line.strip()}
    if listed.returncode != 0:
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: cannot list sport requests")
    if SPORT_TOPIC not in topics:
        return
    info = _run((ros2, "topic", "info", SPORT_TOPIC), runner=runner)
    match = re.search(r"^Publisher count:\s*(\d+)\s*$", info.stdout, re.MULTILINE)
    if info.returncode != 0 or match is None:
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: cannot inspect sport requests")
    if int(match.group(1)) == 0:
        return
    result = _run(
        (TIMEOUT, "2", ros2, "topic", "echo", SPORT_TOPIC, "--once"),
        runner=runner,
        timeout=4.0,
    )
    if result.returncode == 0:
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: unexpected sport request")
    if result.returncode != 124:
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: cannot monitor sport requests")


def check(
    *,
    stage: str,
    environment: Mapping[str, str] = os.environ,
    runner: Runner = subprocess.run,
    control_fetcher: ControlFetcher = _fetch_control,
    navigation_fetcher: NavigationFetcher = _fetch_navigation,
    ros2: str | None = None,
) -> dict[str, str]:
    if stage not in STAGES:
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: checker stage is invalid")
    profile = environment.get("ROBOT_SCOPE_MAPPING_PROFILE")
    if stage == "prelocalization" and profile != TRACK_C2_PROFILE:
        raise NoGoalError("TRACK C NG0 BLOCKED: explicit Track C2 profile is required")
    if stage == "localized" and profile not in {PROFILE, TRACK_C2_PROFILE}:
        raise NoGoalError("TRACK C NG1 BLOCKED: explicit competition profile is required")
    if environment.get("ROS_DISTRO") != "humble":
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: ROS 2 Humble is required")
    ros2_command = ros2 or shutil.which("ros2")
    if not ros2_command or not Path(ros2_command).is_absolute():
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: ros2 command is unavailable")

    _control_is_stationary(control_fetcher)
    if stage == "localized" and profile == TRACK_C2_PROFILE:
        _localization_session_is_safe(navigation_fetcher)
    _required_nodes_are_present(ros2_command, runner)
    active_nodes = (
        PRELOCALIZATION_ACTIVE_NODES if stage == "prelocalization" else LIFECYCLE_NODES
    )
    for node in active_nodes:
        _lifecycle_is_active(node, ros2_command, runner)

    controller_topic = (
        TRACK_C2_CONTROLLER_ODOM if profile == TRACK_C2_PROFILE else STRICT_CONTROLLER_ODOM
    )
    _topic_has_publisher("/map", ros2_command, runner)
    for topic in (*FRESH_TOPICS, controller_topic):
        _topic_has_exactly_one_publisher(topic, ros2_command, runner)
        _topic_has_fresh_sample(topic, ros2_command, runner)

    if not _transform_available("odom", "base_link", ros2_command, runner):
        raise NoGoalError("TRACK C NO-GOAL BLOCKED: odom to base_link TF is disconnected")
    localized_tf = _transform_available("map", "base_link", ros2_command, runner)
    if stage == "localized":
        if not _transform_available("map", "odom", ros2_command, runner):
            raise NoGoalError("TRACK C NG1 BLOCKED: map to odom TF is disconnected")
        if not localized_tf:
            raise NoGoalError("TRACK C NG1 BLOCKED: map to base_link TF is disconnected")
        for topic in LOCALIZED_TOPICS:
            _topic_has_exactly_one_publisher(topic, ros2_command, runner)
        _topic_has_fresh_sample("/amcl_pose", ros2_command, runner)

    raw_command_policy = _raw_command_is_quiet_or_zero(ros2_command, runner)
    _sport_request_is_quiet(ros2_command, runner)
    return {
        "stage": stage,
        "profile": str(profile),
        "controller_odometry": controller_topic,
        "localization": "LOCALIZED" if localized_tf else "WAITING_FOR_INITIAL_POSE",
        "raw_command": raw_command_policy,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Robot Scope staged no-goal checker")
    parser.add_argument("--stage", choices=STAGES, required=True)
    args = parser.parse_args(argv)
    try:
        result = check(stage=args.stage)
    except NoGoalError as exc:
        print(f"[Robot Scope] {exc}")
        return 2
    print(
        "[Robot Scope] Track C no-goal readiness passed | "
        f"stage={result['stage']} localization={result['localization']} "
        f"raw_command={result['raw_command']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
