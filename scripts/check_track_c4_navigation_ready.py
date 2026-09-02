#!/usr/bin/env python3
"""Read-only pre-goal checker for the normal Track C4 navigation session."""

from __future__ import annotations

import argparse
import base64
import binascii
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


PROFILE = "go2-xt16-wireless-competition-fastlio"
MAP_ID = "f292601e2c8b269eb635cb0f"
MAP_REVISION = "7c48dd9d8d1d11fbc7ff39ccd6b854d58c7dc5863072bb548eba570e5044ea93"
CONTROLLER_ODOM = "/robot_scope/nav/controller_odom_fastlio"
RAW_COMMAND_TOPIC = "/robot_scope/nav/cmd_vel_raw"
TIMEOUT = "/usr/bin/timeout"
CONTROL_URL = "http://127.0.0.1:8088/api/v1/control"
NAVIGATION_URL = "http://127.0.0.1:8088/api/v1/navigation"
PARAMETERS_URL = "http://127.0.0.1:8088/api/v1/navigation/parameters"
MAP_DATA_URL = f"http://127.0.0.1:8088/api/v1/saved-maps/{MAP_ID}/data"
EXPECTED_SPEED_SCALE = 0.35
START_POSE = (0.0, 0.0, 0.0)
GOAL_POSE = (0.25, 0.0, 0.0)
ROBOT_RADIUS_M = 0.22
STOP_BUFFER_M = 0.15
ROUTE_SAMPLE_STEP_M = 0.01
READY_ENTER_HZ = 9.5
READY_EXIT_HZ = 9.0
READY_ENTER_DWELL_S = 10.0
READY_EXIT_DWELL_S = 2.0
MAX_GAP_S = 0.25
C4_PARAMETER_VALUES = {
    "desired_linear_vel": 0.10,
    "xy_goal_tolerance": 0.05,
    "yaw_goal_tolerance": 0.10,
    "required_movement_radius": 0.05,
    "robot_radius": 0.22,
    "inflation_radius": 0.25,
}
LIFECYCLE_NODES = (
    "/map_server",
    "/controller_server",
    "/planner_server",
    "/behavior_server",
    "/bt_navigator",
)
FRESH_TOPICS = (
    "/scan",
    "/Odometry",
    CONTROLLER_ODOM,
    "/amcl_pose",
    "/global_costmap/costmap",
    "/local_costmap/costmap",
)


class C4ReadyError(RuntimeError):
    """A fail-closed Track C4 pre-goal readiness failure."""


Runner = Callable[..., subprocess.CompletedProcess[str]]
Fetcher = Callable[[], Mapping[str, Any]]


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


def _fetch(url: str, label: str) -> Mapping[str, Any]:
    try:
        with urlopen(url, timeout=3.0) as response:  # noqa: S310 - fixed loopback URL
            if response.status != 200:
                raise C4ReadyError(f"TRACK C4 BLOCKED: {label} status is unavailable")
            payload = json.loads(response.read(1024 * 1024))
    except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
        raise C4ReadyError(f"TRACK C4 BLOCKED: {label} status is unavailable") from exc
    if not isinstance(payload, Mapping):
        raise C4ReadyError(f"TRACK C4 BLOCKED: {label} status is invalid")
    return payload


def _fetch_control() -> Mapping[str, Any]:
    return _fetch(CONTROL_URL, "control")


def _fetch_navigation() -> Mapping[str, Any]:
    return _fetch(NAVIGATION_URL, "navigation")


def _fetch_parameters() -> Mapping[str, Any]:
    return _fetch(PARAMETERS_URL, "navigation parameters")


def _fetch_map_data() -> Mapping[str, Any]:
    return _fetch(MAP_DATA_URL, "pinned map data")


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise C4ReadyError(f"TRACK C4 BLOCKED: {label} is invalid")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise C4ReadyError(f"TRACK C4 BLOCKED: {label} is invalid") from exc
    if not math.isfinite(number):
        raise C4ReadyError(f"TRACK C4 BLOCKED: {label} is invalid")
    return number


def _control_is_ready_and_zero(fetcher: Fetcher) -> None:
    payload = fetcher()
    control = payload.get("control")
    if not isinstance(control, Mapping):
        raise C4ReadyError("TRACK C4 BLOCKED: control snapshot is invalid")
    if any(control.get(key) is not True for key in ("enabled", "configured", "available")):
        raise C4ReadyError("TRACK C4 BLOCKED: control is unavailable")
    if control.get("estop_latched") is not False:
        raise C4ReadyError("TRACK C4 BLOCKED: dashboard software stop is latched")

    bridge = control.get("bridge")
    lease = control.get("lease")
    command = control.get("command")
    limits = control.get("limits")
    if not all(
        isinstance(value, Mapping) for value in (bridge, lease, command, limits)
    ):
        raise C4ReadyError("TRACK C4 BLOCKED: control safety fields are invalid")
    assert isinstance(bridge, Mapping)
    assert isinstance(lease, Mapping)
    assert isinstance(command, Mapping)
    assert isinstance(limits, Mapping)
    if any(
        bridge.get(key) is not True
        for key in ("ready", "authenticated", "connected", "available")
    ):
        raise C4ReadyError("TRACK C4 BLOCKED: signed Control Bridge is not ready")
    expected_counts = {
        "lowstate_publishers": 1,
        "sport_subscribers": 1,
        "own_sport_publishers": 1,
        "foreign_named_sport_publishers": 0,
        "bare_unitree_sport_publishers": 10,
        "expected_bare_sport_publishers": 10,
        "total_sport_publishers": 11,
    }
    for key, expected in expected_counts.items():
        if type(bridge.get(key)) is not int or bridge.get(key) != expected:
            raise C4ReadyError(f"TRACK C4 BLOCKED: Bridge {key} is invalid")
    status_age = _finite_number(bridge.get("status_age_s"), "Bridge status age")
    lowstate_age = _finite_number(bridge.get("lowstate_age_ms"), "LowState age")
    if status_age < 0.0 or status_age > 0.75 or lowstate_age < 0.0 or lowstate_age > 500.0:
        raise C4ReadyError("TRACK C4 BLOCKED: Bridge or LowState telemetry is stale")

    if (
        lease.get("active") is not True
        or lease.get("bound") is not True
        or lease.get("input_source") != "navigation"
    ):
        raise C4ReadyError("TRACK C4 BLOCKED: navigation lease is not exclusively bound")
    if command.get("deadman") is not False:
        raise C4ReadyError("TRACK C4 BLOCKED: deadman is active before the goal")
    for key in ("linear_x", "linear_y", "angular_z"):
        if _finite_number(command.get(key), f"command {key}") != 0.0:
            raise C4ReadyError("TRACK C4 BLOCKED: command is non-zero before the goal")
    if (
        _finite_number(limits.get("default_speed_scale"), "speed scale")
        != EXPECTED_SPEED_SCALE
    ):
        raise C4ReadyError("TRACK C4 BLOCKED: speed scale is not exactly 35 percent")
    if _finite_number(limits.get("max_linear_x"), "linear velocity limit") != 0.30:
        raise C4ReadyError("TRACK C4 BLOCKED: linear velocity clamp is invalid")


def _parameters_are_c4_safe(fetcher: Fetcher) -> str:
    payload = fetcher()
    revision = payload.get("revision")
    values = payload.get("values")
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{64}", revision) is None:
        raise C4ReadyError("TRACK C4 BLOCKED: parameter revision is invalid")
    if not isinstance(values, Mapping):
        raise C4ReadyError("TRACK C4 BLOCKED: parameter values are invalid")
    for key, expected in C4_PARAMETER_VALUES.items():
        if _finite_number(values.get(key), f"parameter {key}") != expected:
            raise C4ReadyError(f"TRACK C4 BLOCKED: parameter {key} is not pinned")
    if values.get("closed_loop") is not False:
        raise C4ReadyError("TRACK C4 BLOCKED: closed-loop controller is not disabled")
    if values.get("use_rotate_to_heading") is not False:
        raise C4ReadyError("TRACK C4 BLOCKED: rotate-to-heading is not disabled")
    return revision


def _route_clearance(fetcher: Fetcher) -> float:
    payload = fetcher()
    if payload.get("map_id") != MAP_ID or payload.get("revision") != MAP_REVISION:
        raise C4ReadyError("TRACK C4 BLOCKED: route map or revision is invalid")
    if payload.get("data_encoding") != "int8-base64":
        raise C4ReadyError("TRACK C4 BLOCKED: route map encoding is invalid")
    try:
        width = int(payload.get("width"))
        height = int(payload.get("height"))
        resolution = _finite_number(payload.get("resolution"), "map resolution")
        origin = payload.get("origin")
        if (
            width <= 0
            or height <= 0
            or resolution <= 0.0
            or not isinstance(origin, list)
            or len(origin) != 3
        ):
            raise ValueError
        origin_x, origin_y, origin_yaw = (
            _finite_number(value, "map origin") for value in origin
        )
        encoded = payload.get("data_b64")
        if not isinstance(encoded, str):
            raise ValueError
        occupancy = base64.b64decode(encoded, validate=True)
    except (TypeError, ValueError, binascii.Error) as exc:
        raise C4ReadyError("TRACK C4 BLOCKED: route map data is invalid") from exc
    if len(occupancy) != width * height or not set(occupancy).issubset({0, 100, 255}):
        raise C4ReadyError("TRACK C4 BLOCKED: route occupancy is invalid")

    cosine, sine = math.cos(origin_yaw), math.sin(origin_yaw)

    def local_coordinates(x: float, y: float) -> tuple[float, float]:
        delta_x, delta_y = x - origin_x, y - origin_y
        return (
            cosine * delta_x + sine * delta_y,
            -sine * delta_x + cosine * delta_y,
        )

    nonfree = [
        (index % width, index // width)
        for index, value in enumerate(occupancy)
        if value != 0
    ]

    def clearance(x: float, y: float) -> float:
        local_x, local_y = local_coordinates(x, y)
        map_width, map_height = width * resolution, height * resolution
        if not 0.0 <= local_x < map_width or not 0.0 <= local_y < map_height:
            return -1.0
        result = min(local_x, local_y, map_width - local_x, map_height - local_y)
        for column, row in nonfree:
            lower_x, lower_y = column * resolution, row * resolution
            upper_x, upper_y = lower_x + resolution, lower_y + resolution
            distance_x = max(lower_x - local_x, 0.0, local_x - upper_x)
            distance_y = max(lower_y - local_y, 0.0, local_y - upper_y)
            result = min(result, math.hypot(distance_x, distance_y))
        return result

    start_x, start_y, start_yaw = START_POSE
    goal_x, goal_y, goal_yaw = GOAL_POSE
    distance = math.hypot(goal_x - start_x, goal_y - start_y)
    if distance <= 0.0 or distance > 0.30 or goal_yaw != start_yaw:
        raise C4ReadyError("TRACK C4 BLOCKED: fixed short goal is invalid")
    forward_x, forward_y = math.cos(start_yaw), math.sin(start_yaw)
    if not math.isclose(goal_x, start_x + forward_x * distance, abs_tol=1e-9) or not math.isclose(
        goal_y,
        start_y + forward_y * distance,
        abs_tol=1e-9,
    ):
        raise C4ReadyError("TRACK C4 BLOCKED: fixed goal is not straight ahead")
    corridor_length = distance + STOP_BUFFER_M
    samples = max(1, math.ceil(corridor_length / ROUTE_SAMPLE_STEP_M))
    minimum_clearance = min(
        clearance(
            start_x + forward_x * corridor_length * index / samples,
            start_y + forward_y * corridor_length * index / samples,
        )
        for index in range(samples + 1)
    )
    if minimum_clearance <= ROBOT_RADIUS_M:
        raise C4ReadyError("TRACK C4 BLOCKED: fixed route corridor is not known-free")
    return minimum_clearance


def _navigation_is_localized_and_idle(fetcher: Fetcher) -> dict[str, float | str]:
    payload = fetcher()
    pipeline = payload.get("pipeline")
    map_state = payload.get("map")
    localization = payload.get("localization")
    goal = payload.get("goal")
    safety = payload.get("safety")
    readiness = payload.get("readiness")
    bindings = payload.get("bindings")
    localization_session = payload.get("localization_session")
    health = payload.get("localization_health")
    values = (
        pipeline,
        map_state,
        localization,
        goal,
        safety,
        readiness,
        bindings,
        localization_session,
        health,
    )
    if not all(isinstance(value, Mapping) for value in values):
        raise C4ReadyError("TRACK C4 BLOCKED: navigation snapshot is incomplete")
    assert isinstance(pipeline, Mapping)
    assert isinstance(map_state, Mapping)
    assert isinstance(localization, Mapping)
    assert isinstance(goal, Mapping)
    assert isinstance(safety, Mapping)
    assert isinstance(readiness, Mapping)
    assert isinstance(bindings, Mapping)
    assert isinstance(localization_session, Mapping)
    assert isinstance(health, Mapping)
    if payload.get("available") is not True or payload.get("robot_online") is not True:
        raise C4ReadyError("TRACK C4 BLOCKED: navigation or robot is unavailable")
    if pipeline.get("state") != "running" or payload.get("session_mode") != "navigation":
        raise C4ReadyError("TRACK C4 BLOCKED: normal navigation session is not running")
    if localization_session.get("active") is not False:
        raise C4ReadyError("TRACK C4 BLOCKED: localization-only session is still active")
    if map_state.get("id") != MAP_ID or map_state.get("revision") != MAP_REVISION:
        raise C4ReadyError("TRACK C4 BLOCKED: pinned map or revision is invalid")
    if localization.get("state") != "localized":
        raise C4ReadyError("TRACK C4 BLOCKED: localization is not stable")
    if goal.get("state") != "idle":
        raise C4ReadyError("TRACK C4 BLOCKED: a navigation goal already exists")
    if safety.get("can_send_goal") is not True:
        raise C4ReadyError("TRACK C4 BLOCKED: goal safety gate is closed")
    if health.get("state") != "READY":
        raise C4ReadyError("TRACK C4 BLOCKED: localization health is not READY")
    rate_gate = health.get("rate_gate")
    metrics = health.get("metrics")
    if not isinstance(rate_gate, Mapping) or not isinstance(metrics, Mapping):
        raise C4ReadyError("TRACK C4 BLOCKED: stabilized rate evidence is missing")
    if (
        rate_gate.get("enabled") is not True
        or rate_gate.get("profile") != PROFILE
        or rate_gate.get("source") != "server_fixed_competition_fastlio"
    ):
        raise C4ReadyError("TRACK C4 BLOCKED: rate gate profile is invalid")
    for key, expected in (
        ("nominal_hz", 10.0),
        ("ready_enter_hz", READY_ENTER_HZ),
        ("ready_exit_hz", READY_EXIT_HZ),
        ("ready_enter_dwell_s", READY_ENTER_DWELL_S),
        ("ready_exit_dwell_s", READY_EXIT_DWELL_S),
        ("max_gap_s", MAX_GAP_S),
    ):
        if not math.isclose(
            _finite_number(rate_gate.get(key), f"rate gate {key}"),
            expected,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise C4ReadyError(f"TRACK C4 BLOCKED: rate gate {key} is invalid")
    stable_duration = _finite_number(
        health.get("stable_ready_duration_s"),
        "stable READY duration",
    )
    if stable_duration < READY_ENTER_DWELL_S:
        raise C4ReadyError("TRACK C4 BLOCKED: stable READY dwell is incomplete")
    if health.get("hard_fault") is not False:
        raise C4ReadyError("TRACK C4 BLOCKED: localization hard fault is present")
    raw_rate = _finite_number(
        metrics.get("odometry_frequency_hz_raw"),
        "raw odometry frequency",
    )
    display_rate = _finite_number(
        metrics.get("odometry_frequency_hz_display"),
        "display odometry frequency",
    )
    p95_period = _finite_number(
        metrics.get("odometry_p95_period_s"),
        "odometry p95 period",
    )
    max_gap = _finite_number(
        metrics.get("odometry_max_gap_s"),
        "odometry maximum gap",
    )
    if max_gap > MAX_GAP_S:
        raise C4ReadyError("TRACK C4 BLOCKED: odometry maximum gap is unsafe")
    if (
        bindings.get("navigation_profile") != PROFILE
        or bindings.get("controller_odometry") != CONTROLLER_ODOM
        or bindings.get("command") != RAW_COMMAND_TOPIC
    ):
        raise C4ReadyError("TRACK C4 BLOCKED: navigation bindings are invalid")
    required_readiness = (
        "map_server",
        "localization",
        "planner",
        "controller",
        "behavior",
        "cmd_bridge",
        "map",
        "scan",
        "odometry",
        "tf",
        "action_server",
    )
    for key in required_readiness:
        if readiness.get(key) is not True:
            raise C4ReadyError(f"TRACK C4 BLOCKED: readiness {key} is false")
    for key in (
        "cmd_vel_publishers",
        "scan_publishers",
        "odometry_publishers",
        "controller_odometry_publishers",
        "runtime_health_publishers",
        "localization_publishers",
    ):
        if type(readiness.get(key)) is not int or readiness.get(key) != 1:
            raise C4ReadyError(f"TRACK C4 BLOCKED: readiness {key} is invalid")
    return {
        "odometry_frequency_hz_raw": raw_rate,
        "odometry_frequency_hz_display": display_rate,
        "odometry_p95_period_s": p95_period,
        "odometry_max_gap_s": max_gap,
        "stable_ready_duration_s": stable_duration,
        "rate_band": str(health.get("rate_band") or "")[:32],
    }


def _required_nodes_are_active(ros2: str, runner: Runner) -> None:
    listed = _run((ros2, "node", "list"), runner=runner)
    nodes = {line.strip() for line in listed.stdout.splitlines() if line.strip()}
    if listed.returncode != 0 or not set(LIFECYCLE_NODES).issubset(nodes):
        raise C4ReadyError("TRACK C4 BLOCKED: a Nav2 child node is missing")
    for node in LIFECYCLE_NODES:
        state = _run(
            (TIMEOUT, "3", ros2, "lifecycle", "get", node),
            runner=runner,
            timeout=5.0,
        )
        if state.returncode != 0 or not re.search(r"\bactive\b", state.stdout):
            raise C4ReadyError(f"TRACK C4 BLOCKED: {node} is not active")


def _topics_are_fresh(ros2: str, runner: Runner) -> None:
    for topic in FRESH_TOPICS:
        info = _run((ros2, "topic", "info", topic), runner=runner)
        match = re.search(r"^Publisher count:\s*(\d+)\s*$", info.stdout, re.MULTILINE)
        if info.returncode != 0 or match is None or int(match.group(1)) != 1:
            raise C4ReadyError(
                f"TRACK C4 BLOCKED: {topic} must have exactly one publisher"
            )
        sample = _run(
            (TIMEOUT, "3", ros2, "topic", "echo", topic, "--once"),
            runner=runner,
            timeout=5.0,
        )
        if sample.returncode != 0 or not sample.stdout.strip():
            raise C4ReadyError(f"TRACK C4 BLOCKED: {topic} has no fresh sample")


def _transform_is_available(parent: str, child: str, ros2: str, runner: Runner) -> None:
    result = _run(
        (TIMEOUT, "3", ros2, "run", "tf2_ros", "tf2_echo", parent, child),
        runner=runner,
        timeout=5.0,
    )
    if result.returncode not in (0, 124) or not all(
        marker in result.stdout for marker in ("Translation:", "Rotation:")
    ):
        raise C4ReadyError(f"TRACK C4 BLOCKED: {parent} to {child} TF is unavailable")


def _raw_command_is_quiet_or_zero(ros2: str, runner: Runner) -> str:
    result = _run(
        (TIMEOUT, "2", ros2, "topic", "echo", RAW_COMMAND_TOPIC, "--once"),
        runner=runner,
        timeout=4.0,
    )
    if result.returncode == 124:
        return "quiet"
    if result.returncode != 0:
        raise C4ReadyError("TRACK C4 BLOCKED: raw command cannot be monitored")
    numeric = re.findall(r"^\s*[xyz]:\s*([-+0-9.eE]+)\s*$", result.stdout, re.MULTILINE)
    if len(numeric) < 6:
        raise C4ReadyError("TRACK C4 BLOCKED: raw command shape is invalid")
    if any(_finite_number(value, "raw command") != 0.0 for value in numeric):
        raise C4ReadyError("TRACK C4 BLOCKED: raw command is non-zero before the goal")
    return "zero_only"


def check(
    *,
    environment: Mapping[str, str] = os.environ,
    runner: Runner = subprocess.run,
    control_fetcher: Fetcher = _fetch_control,
    navigation_fetcher: Fetcher = _fetch_navigation,
    parameters_fetcher: Fetcher = _fetch_parameters,
    map_data_fetcher: Fetcher = _fetch_map_data,
    ros2: str | None = None,
) -> dict[str, str]:
    if environment.get("ROBOT_SCOPE_MAPPING_PROFILE") != PROFILE:
        raise C4ReadyError("TRACK C4 BLOCKED: explicit competition profile is required")
    if environment.get("ROS_DISTRO") != "humble":
        raise C4ReadyError("TRACK C4 BLOCKED: ROS 2 Humble is required")
    ros2_command = ros2 or shutil.which("ros2")
    if not ros2_command or not Path(ros2_command).is_absolute():
        raise C4ReadyError("TRACK C4 BLOCKED: ros2 command is unavailable")

    _control_is_ready_and_zero(control_fetcher)
    parameters_revision = _parameters_are_c4_safe(parameters_fetcher)
    route_clearance = _route_clearance(map_data_fetcher)
    rate_evidence = _navigation_is_localized_and_idle(navigation_fetcher)
    _required_nodes_are_active(ros2_command, runner)
    _topics_are_fresh(ros2_command, runner)
    for parent, child in (
        ("map", "odom"),
        ("odom", "base_link"),
        ("map", "base_link"),
    ):
        _transform_is_available(parent, child, ros2_command, runner)
    raw_command = _raw_command_is_quiet_or_zero(ros2_command, runner)
    return {
        "profile": PROFILE,
        "map_id": MAP_ID,
        "map_revision": MAP_REVISION,
        "controller_odometry": CONTROLLER_ODOM,
        "parameters_revision": parameters_revision,
        "route_clearance_m": f"{route_clearance:.3f}",
        "goal": "IDLE",
        "raw_command": raw_command,
        "odometry_frequency_hz_raw": f"{rate_evidence['odometry_frequency_hz_raw']:.6f}",
        "odometry_frequency_hz_display": f"{rate_evidence['odometry_frequency_hz_display']:.3f}",
        "odometry_p95_period_s": f"{rate_evidence['odometry_p95_period_s']:.6f}",
        "odometry_max_gap_s": f"{rate_evidence['odometry_max_gap_s']:.6f}",
        "stable_ready_duration_s": f"{rate_evidence['stable_ready_duration_s']:.3f}",
        "rate_band": rate_evidence["rate_band"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Robot Scope Track C4 normal-navigation pre-goal checker"
    )
    parser.parse_args(argv)
    try:
        result = check()
    except C4ReadyError as exc:
        print(f"[Robot Scope] {exc}")
        return 2
    print(
        "[Robot Scope] Track C4 pre-goal readiness passed | "
        f"map={result['map_id']} goal={result['goal']} "
        f"raw_command={result['raw_command']} "
        f"odom_raw_hz={result['odometry_frequency_hz_raw']} "
        f"stable_ready_s={result['stable_ready_duration_s']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
