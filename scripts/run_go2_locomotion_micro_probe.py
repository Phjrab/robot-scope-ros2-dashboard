#!/usr/bin/env python3
"""Fixed, supervised Go2 locomotion micro-probe over the existing dashboard.

The default invocation is a hardware-free dry run.  Live invocations expose
only four reviewed probe envelopes and use the same HTTP/WebSocket contract as
the manual dashboard, so every command still crosses ControlManager, the
signed transport, and Go2ControlBridge.  This module never creates a ROS
publisher or subscriber and never addresses the Unitree Sport request topic.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:8088"
CONTROL_PATH = "/api/v1/control"
NAVIGATION_PATH = "/api/v1/navigation"
HEALTH_PATH = "/api/v1/health"
POSE_PATH = "/api/v1/pose"
COMPETITION_PATH = "/api/v1/competition"
MISSIONS_PATH = "/api/v1/missions"
MAPPING_PATH = "/api/v1/mapping/control"
CONTROL_WS = "ws://127.0.0.1:8088/api/v1/ws/control"
DASHBOARD_UNIT = "robot-scope.service"
EXPECTED_PROFILE = "go2-xt16-wireless"
MOTION_OBSERVATION_SOURCE = "unitree_go.sport_mode_state.position"
MOTION_OBSERVATION_SCHEMA = "robot-scope.motion-observation"
MOTION_USE_APPROVED = False
API_STOP_MOVE = 1003
API_MOVE = 1008
DRIVE_WINDOW_S = 0.70
DRIVE_PERIOD_S = 0.05
WATCHDOG_TAIL_S = 0.25
FRAME_LATE_TOLERANCE_S = 0.025
FIRST_ACCEPTANCE_TIMEOUT_S = 0.15
FIRST_ACCEPTANCE_POLL_S = 0.025
POST_ARM_LOWSTATE_TIMEOUT_S = 0.50
POST_ARM_LOWSTATE_POLL_S = 0.025
PRE_SEND_SAFETY_LEAD_S = 0.025
MAX_POSE_AGE_S = 0.50
MAX_PRECOMMAND_DRIFT_M = 0.005
MAX_OBSERVED_TRAVEL_M = 0.10
MAX_HTTP_BYTES = 1024 * 1024
MAX_SAMPLES = 32
MAX_SAFE_TEXT = 240
CLEANUP_CONFIRM_TIMEOUT_S = 1.0
CLEANUP_CONFIRM_PERIOD_S = 0.05
REPORT_SCHEMA = "robot-scope.c4c-micro-probe/v1"
EVENT_SCHEMA = "robot-scope.c4c-operator-event/v1"
FULL_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class ProbeError(RuntimeError):
    """A fail-closed probe error safe to retain in the private result."""


def _bounded_report_samples(
    samples: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Bound intermediate evidence while always retaining final cleanup."""

    if len(samples) <= MAX_SAMPLES:
        return list(samples)
    return [*samples[: MAX_SAMPLES - 1], samples[-1]]


@dataclass(frozen=True)
class ProbeSpec:
    probe_id: str
    velocity_x_mps: float
    command_window_s: float = DRIVE_WINDOW_S
    period_s: float = DRIVE_PERIOD_S

    @property
    def predicted_max_travel_m(self) -> float:
        return self.velocity_x_mps * (self.command_window_s + WATCHDOG_TAIL_S)


@dataclass(frozen=True)
class RuntimeCursor:
    ack_seq: int
    published_count: int
    stop_count: int
    move_count: int
    nonzero_move_count: int
    motion_run_id: int
    motion_run_nonzero_move_count: int
    joint_seq: int
    observation_seq: int
    max_observed_travel_m: float
    drive_stop_count: int | None = None


PROBES = {
    "MP-030": ProbeSpec("MP-030", 0.03),
    "MP-050": ProbeSpec("MP-050", 0.05),
    "MP-080": ProbeSpec("MP-080", 0.08),
    "MP-100": ProbeSpec("MP-100", 0.10),
}
EXECUTE_FLAGS = {
    "execute_mp_030": "MP-030",
    "execute_mp_050": "MP-050",
    "execute_mp_080": "MP-080",
    "execute_mp_100": "MP-100",
}
CONFIRMATION_FLAGS = (
    "confirm_stock_baseline_pass",
    "confirm_robot_stopped",
    "confirm_corridor_clear",
    "confirm_estop_ready",
    "confirm_safety_operator",
)


class ControlStream(Protocol):
    def bind(self, lease_id: str, *, client_time_ms: float) -> None: ...

    def send_twist(self, payload: Mapping[str, Any]) -> None: ...

    def release(self, lease_id: str, *, client_time_ms: float) -> bool: ...

    def close(self) -> None: ...


class DashboardAdapter(Protocol):
    def snapshots(self) -> Mapping[str, Mapping[str, Any]]: ...

    def arm(self) -> str: ...

    def open_stream(self) -> ControlStream: ...

    def disarm(self, lease_id: str) -> None: ...

    def software_stop(self) -> None: ...


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProbeError(f"{label} is invalid")
    number = float(value)
    if not math.isfinite(number):
        raise ProbeError(f"{label} is invalid")
    return number


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProbeError(f"{label} is invalid")
    return value


def _exact_zero(command: Mapping[str, Any], label: str) -> None:
    if command.get("deadman") is not False:
        raise ProbeError(f"{label} is not authoritative exact zero")
    for key in ("linear_x", "linear_y", "angular_z"):
        if _finite(command.get(key), f"{label} {key}") != 0.0:
            raise ProbeError(f"{label} is not authoritative exact zero")


def _bridge_cardinality(bridge: Mapping[str, Any]) -> None:
    expected = bridge.get("expected_bare_sport_publishers")
    counts = {
        "lowstate_publishers": 1,
        "sport_subscribers": 1,
        "own_sport_publishers": 1,
        "foreign_named_sport_publishers": 0,
    }
    if isinstance(expected, bool) or not isinstance(expected, int) or not 0 <= expected <= 64:
        raise ProbeError("Bridge expected publisher count is invalid")
    counts["bare_unitree_sport_publishers"] = expected
    counts["total_sport_publishers"] = expected + 1
    for key, required in counts.items():
        if type(bridge.get(key)) is not int or bridge.get(key) != required:
            raise ProbeError(f"Bridge {key} changed")


def _request_evidence(bridge: Mapping[str, Any]) -> Mapping[str, Any]:
    evidence = _mapping(bridge.get("request_evidence"), "Bridge request evidence")
    if evidence.get("schema") != "robot-scope.sport-request-evidence.v1":
        raise ProbeError("Bridge request evidence schema is invalid")
    for key in (
        "published_count", "stop_count", "move_count", "zero_move_count",
        "nonzero_move_count", "malformed_move_count", "action_count", "other_count", "motion_run_id",
        "motion_run_nonzero_move_count",
    ):
        value = evidence.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= 2_147_483_647
        ):
            raise ProbeError("Bridge request evidence is invalid")
    if not isinstance(evidence.get("motion_run_active"), bool):
        raise ProbeError("Bridge request evidence is invalid")
    last_api_id = evidence.get("last_api_id")
    if (
        last_api_id is not None
        and (
            isinstance(last_api_id, bool)
            or not isinstance(last_api_id, int)
            or not 0 <= last_api_id <= 65_535
        )
    ):
        raise ProbeError("Bridge request evidence is invalid")
    return evidence


def _sport_state(bridge: Mapping[str, Any]) -> Mapping[str, Any]:
    state = _mapping(bridge.get("sport_mode_state"), "SportModeState")
    if state.get("fresh") is not True:
        raise ProbeError("SportModeState is stale")
    if type(state.get("mode")) is not int or type(state.get("gait_type")) is not int:
        raise ProbeError("SportModeState mode or gait is invalid")
    if type(state.get("error_code")) is not int:
        raise ProbeError("SportModeState error code is invalid")
    velocity = state.get("velocity")
    if not isinstance(velocity, list) or len(velocity) != 3:
        raise ProbeError("SportModeState velocity is invalid")
    for value in velocity:
        _finite(value, "SportModeState velocity")
    return state


def _bridge_telemetry(bridge: Mapping[str, Any]) -> dict[str, Any]:
    telemetry = _mapping(bridge.get("telemetry"), "Bridge telemetry")
    battery = _mapping(telemetry.get("battery"), "Bridge battery telemetry")
    joints = _mapping(telemetry.get("joints"), "Bridge joint telemetry")
    battery_soc = _finite(battery.get("battery_soc"), "Bridge battery state")
    joint_seq = joints.get("seq")
    if not 0.0 <= battery_soc <= 100.0:
        raise ProbeError("Bridge battery state is invalid")
    if isinstance(joint_seq, bool) or not isinstance(joint_seq, int) or joint_seq < 0:
        raise ProbeError("Bridge joint sequence is invalid")
    return {"battery_soc": battery_soc, "joint_seq": joint_seq}


def _command_ack(bridge: Mapping[str, Any]) -> dict[str, Any]:
    ack = _mapping(bridge.get("command_ack"), "Bridge command ACK")
    sequence = ack.get("seq")
    age_ms = _finite(ack.get("age_ms"), "Bridge command ACK age")
    if (
        isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or sequence < 0
        or ack.get("type") not in {"stop", "drive", "action"}
        or not isinstance(ack.get("source_matches_dashboard"), bool)
        or not 0.0 <= age_ms <= 2_147_483_647.0
    ):
        raise ProbeError("Bridge command ACK is invalid")
    return {
        "seq": sequence,
        "type": ack["type"],
        "age_ms": age_ms,
        "source_matches_dashboard": ack["source_matches_dashboard"],
    }


def _validate_exclusions(
    snapshots: Mapping[str, Mapping[str, Any]], *, lease_active: bool
) -> Mapping[str, Any]:
    health = _mapping(snapshots.get("health"), "health snapshot")
    control_payload = _mapping(snapshots.get("control"), "control snapshot")
    navigation = _mapping(snapshots.get("navigation"), "navigation snapshot")
    competition = _mapping(snapshots.get("competition"), "competition snapshot")
    missions = _mapping(snapshots.get("missions"), "mission snapshot")
    mapping = _mapping(snapshots.get("mapping"), "mapping snapshot")
    control = _mapping(control_payload.get("control"), "control state")

    runtime_profile = _mapping(health.get("runtime_profile"), "runtime profile")
    if runtime_profile.get("id") != "go2" or health.get("target_matches_startup") is not True:
        raise ProbeError("dashboard is not bound to the startup Go2 target")
    if competition.get("operation_mode") != "MANUAL":
        raise ProbeError("competition operation mode is not MANUAL")
    if any(control.get(key) is not True for key in ("enabled", "configured", "available")):
        raise ProbeError("control is unavailable")
    if control.get("estop_latched") is not False:
        raise ProbeError("dashboard software stop is latched")
    lease = _mapping(control.get("lease"), "control lease")
    if lease.get("active") is not lease_active:
        raise ProbeError("control lease state changed")
    if lease_active and lease.get("source") != "keyboard":
        raise ProbeError("control lease source changed")
    action_guard = _mapping(control.get("action_guard"), "action guard")
    if action_guard.get("active") is not False:
        raise ProbeError("a robot action guard is active")

    pipeline = _mapping(navigation.get("pipeline"), "navigation pipeline")
    goal = _mapping(navigation.get("goal"), "navigation goal")
    localization = _mapping(
        navigation.get("localization_session"), "localization-only session"
    )
    bindings = _mapping(navigation.get("bindings"), "navigation bindings")
    if (
        pipeline.get("state") != "idle"
        or navigation.get("session_mode") != "idle"
        or goal.get("state") != "idle"
        or localization.get("active") is not False
    ):
        raise ProbeError("Navigation or localization is active")
    if bindings.get("navigation_profile") != EXPECTED_PROFILE:
        raise ProbeError("dashboard profile is not the fixed production profile")
    if missions.get("active_mission_id") is not None:
        raise ProbeError("a Mission is active")
    mapping_pipeline = _mapping(mapping.get("pipeline"), "mapping pipeline")
    mapping_operation = _mapping(mapping.get("operation"), "mapping operation")
    if mapping_pipeline.get("state") != "idle" or mapping_operation.get("state") in {
        "saving", "stopping"
    }:
        raise ProbeError("mapping is active")
    return control


def _pose_sample(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    state = snapshot.get("state")
    if state not in {"ok", "waiting", "stale"}:
        raise ProbeError("odometry pose state is invalid")
    sequence = snapshot.get("seq")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ProbeError("odometry pose sequence is invalid")
    result = {
        "state": state,
        "topic": str(snapshot.get("topic", ""))[:128],
        "seq": sequence,
        "age_s": snapshot.get("age_s"),
    }
    if state != "ok":
        return result
    age_s = _finite(snapshot.get("age_s"), "odometry pose age")
    if age_s < 0.0:
        raise ProbeError("odometry pose age is invalid")
    result["age_s"] = age_s
    position = _mapping(snapshot.get("position"), "odometry position")
    orientation = _mapping(snapshot.get("orientation"), "odometry orientation")
    result["position"] = {
        key: _finite(position.get(key), f"odometry position {key}")
        for key in ("x", "y", "z")
    }
    result["orientation"] = {
        key: _finite(orientation.get(key), f"odometry orientation {key}")
        for key in ("x", "y", "z", "w")
    }
    return result


def _validate_pose_travel(
    pose: Mapping[str, Any],
    *,
    baseline_pose: Mapping[str, Any],
    maximum_m: float,
) -> float:
    """Require fresh, monotonic pose evidence inside a fixed planar bound."""

    if pose.get("state") != "ok" or baseline_pose.get("state") != "ok":
        raise ProbeError("fresh odometry pose is unavailable")
    if not 0.0 <= _finite(pose.get("age_s"), "odometry pose age") <= MAX_POSE_AGE_S:
        raise ProbeError("odometry pose is stale")
    if not 0.0 <= _finite(
        baseline_pose.get("age_s"), "baseline odometry pose age"
    ) <= MAX_POSE_AGE_S:
        raise ProbeError("baseline odometry pose is stale")
    if not pose.get("topic") or pose.get("topic") != baseline_pose.get("topic"):
        raise ProbeError("odometry pose topic changed")
    sequence = pose.get("seq")
    baseline_sequence = baseline_pose.get("seq")
    if (
        isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or isinstance(baseline_sequence, bool)
        or not isinstance(baseline_sequence, int)
        or sequence < baseline_sequence
    ):
        raise ProbeError("odometry pose sequence reset")
    position = _mapping(pose.get("position"), "odometry position")
    baseline_position = _mapping(
        baseline_pose.get("position"), "baseline odometry position"
    )
    delta_x = _finite(position.get("x"), "odometry position x") - _finite(
        baseline_position.get("x"), "baseline odometry position x"
    )
    delta_y = _finite(position.get("y"), "odometry position y") - _finite(
        baseline_position.get("y"), "baseline odometry position y"
    )
    displacement = math.hypot(delta_x, delta_y)
    if displacement > maximum_m + 1e-9:
        raise ProbeError("observed travel exceeded the fixed probe envelope")
    return displacement


def _motion_observation(bridge: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the explicit C4C-only relative-position projection."""

    value = _mapping(bridge.get("motion_observation"), "motion observation")
    if (
        value.get("schema") != MOTION_OBSERVATION_SCHEMA
        or value.get("schema_version") != 1
        or value.get("source_id") != MOTION_OBSERVATION_SOURCE
        or value.get("source_clock_domain") != "unitree_go.timespec.unverified"
        or value.get("source_age_ms") is not None
        or value.get("sample_progression") != "source_stamp_strict_increase"
        or value.get("callback_clock_domain") != "bridge_process.monotonic"
        or value.get("receiver_clock_domain") != "dashboard_process.monotonic"
        or value.get("coordinate_space") != "unitree_go.sport_mode_state.local"
        or value.get("frame_id") is not None
        or value.get("origin") != "vendor_local_origin_unverified"
        or value.get("orientation_xyzw") is not None
    ):
        raise ProbeError("motion observation contract is invalid")
    if value.get("quality") != "READY" or value.get("invalid_reason") != "":
        raise ProbeError("qualified motion observation is unavailable")
    if value.get("origin_reset_detected") is not False:
        raise ProbeError("motion observation origin reset")
    generation = value.get("producer_generation")
    if not isinstance(generation, str) or not 16 <= len(generation) <= 128:
        raise ProbeError("motion observation generation is invalid")
    release = value.get("release_commit")
    if not isinstance(release, str) or FULL_COMMIT_RE.fullmatch(release) is None:
        raise ProbeError("motion observation release is invalid")
    sequence = value.get("source_sequence")
    accepted_count = value.get("accepted_sample_count")
    rejected_count = value.get("rejected_sample_count")
    if (
        isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or sequence <= 0
        or sequence != accepted_count
        or isinstance(rejected_count, bool)
        or not isinstance(rejected_count, int)
        or rejected_count < 0
    ):
        raise ProbeError("motion observation progression is invalid")
    stamp = value.get("source_stamp_ns")
    if isinstance(stamp, bool) or not isinstance(stamp, int) or stamp <= 0:
        raise ProbeError("motion observation source stamp is invalid")
    callback_age_ms = _finite(
        value.get("callback_receive_age_ms"), "motion observation callback age"
    )
    last_gap_ms = _finite(
        value.get("last_callback_gap_ms"), "motion observation callback gap"
    )
    max_gap_ms = _finite(
        value.get("max_callback_gap_ms"), "motion observation maximum callback gap"
    )
    receiver_age_ms = _finite(
        value.get("receiver_status_age_ms"), "motion observation receiver age"
    )
    stale_after_ms = _finite(
        value.get("stale_after_ms"), "motion observation stale limit"
    )
    if (
        not 200.0 <= stale_after_ms <= 1_000.0
        or not 0.0 <= callback_age_ms <= min(500.0, stale_after_ms)
        or not 0.0 <= last_gap_ms <= min(500.0, stale_after_ms)
        or not last_gap_ms <= max_gap_ms <= min(500.0, stale_after_ms)
        or not 0.0 <= receiver_age_ms <= 750.0
    ):
        raise ProbeError("motion observation is stale")
    position = value.get("position_xyz")
    if not isinstance(position, list) or len(position) != 3:
        raise ProbeError("motion observation position is invalid")
    safe_position = [
        _finite(item, f"motion observation position {axis}")
        for item, axis in zip(position, "xyz")
    ]
    return {
        "source_id": value["source_id"],
        "producer_generation": generation,
        "release_commit": release,
        "source_sequence": sequence,
        "source_stamp_ns": stamp,
        "callback_receive_age_ms": callback_age_ms,
        "last_callback_gap_ms": last_gap_ms,
        "max_callback_gap_ms": max_gap_ms,
        "receiver_status_age_ms": receiver_age_ms,
        "coordinate_space": value["coordinate_space"],
        "origin": value["origin"],
        "position_xyz": safe_position,
        "quality": "READY",
        "rejected_sample_count": rejected_count,
    }


def _validate_observed_travel(
    observation: Mapping[str, Any],
    *,
    baseline_observation: Mapping[str, Any],
    maximum_m: float,
) -> float:
    """Validate one fixed-source sample and its planar start displacement."""

    stable_fields = (
        "source_id", "producer_generation", "release_commit",
        "coordinate_space", "origin",
    )
    if any(
        observation.get(name) != baseline_observation.get(name)
        for name in stable_fields
    ):
        raise ProbeError("motion observation source or origin changed")
    sequence = observation.get("source_sequence")
    baseline_sequence = baseline_observation.get("source_sequence")
    stamp = observation.get("source_stamp_ns")
    baseline_stamp = baseline_observation.get("source_stamp_ns")
    if (
        isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or isinstance(baseline_sequence, bool)
        or not isinstance(baseline_sequence, int)
        or sequence < baseline_sequence
        or isinstance(stamp, bool)
        or not isinstance(stamp, int)
        or isinstance(baseline_stamp, bool)
        or not isinstance(baseline_stamp, int)
        or (sequence > baseline_sequence and stamp <= baseline_stamp)
        or (sequence == baseline_sequence and stamp != baseline_stamp)
    ):
        raise ProbeError("motion observation sequence or stamp reset")
    position = observation.get("position_xyz")
    baseline_position = baseline_observation.get("position_xyz")
    if (
        not isinstance(position, list)
        or len(position) != 3
        or not isinstance(baseline_position, list)
        or len(baseline_position) != 3
    ):
        raise ProbeError("motion observation position is invalid")
    displacement = math.hypot(
        _finite(position[0], "motion observation x")
        - _finite(baseline_position[0], "baseline motion observation x"),
        _finite(position[1], "motion observation y")
        - _finite(baseline_position[1], "baseline motion observation y"),
    )
    if displacement > maximum_m + 1e-9:
        raise ProbeError("observed travel exceeded the fixed probe envelope")
    return displacement


def _validate_bridge(bridge: Mapping[str, Any]) -> None:
    if any(
        bridge.get(key) is not True
        for key in ("ready", "authenticated", "connected", "available")
    ):
        raise ProbeError("signed Control Bridge is not ready")
    if not 0.0 <= _finite(bridge.get("status_age_s"), "Bridge status age") <= 0.75:
        raise ProbeError("Bridge status is stale")
    if not 0.0 <= _finite(bridge.get("lowstate_age_ms"), "LowState age") <= 500.0:
        raise ProbeError("LowState is stale")
    _bridge_cardinality(bridge)
    _sport_state(bridge)
    _bridge_telemetry(bridge)


def validate_preflight(
    snapshots: Mapping[str, Mapping[str, Any]],
    *,
    expected_release: str,
) -> dict[str, Any]:
    """Validate only read-only state.  This function cannot acquire a lease."""

    if FULL_COMMIT_RE.fullmatch(expected_release) is None:
        raise ProbeError("dashboard release identity is not an exact commit")
    control = _validate_exclusions(snapshots, lease_active=False)
    _exact_zero(_mapping(control.get("command"), "manager command"), "manager command")
    bridge = _mapping(control.get("bridge"), "Bridge status")
    _validate_bridge(bridge)
    if bridge.get("release_commit") != expected_release:
        raise ProbeError("Bridge and dashboard releases do not match exactly")
    _exact_zero(
        _mapping(bridge.get("accepted_command"), "Bridge accepted command"),
        "Bridge accepted command",
    )
    evidence = _request_evidence(bridge)
    if evidence.get("motion_run_active") is not False or evidence.get("last_api_id") != API_STOP_MOVE:
        raise ProbeError("Bridge motion run is not idle on StopMove")
    if (
        evidence.get("zero_move_count") != 0
        or evidence.get("malformed_move_count") != 0
        or evidence.get("other_count") != 0
    ):
        raise ProbeError("Bridge retained malformed or unknown requests")

    state = _sport_state(bridge)
    telemetry = _bridge_telemetry(bridge)
    ack = _command_ack(bridge)
    if ack["type"] != "stop" or ack["source_matches_dashboard"] is not True:
        raise ProbeError("Bridge is not idle on the dashboard Stop acknowledgement")
    motion_observation = _motion_observation(bridge)
    if motion_observation["producer_generation"] != bridge.get("bridge_epoch"):
        raise ProbeError("motion observation does not belong to the active Bridge")
    if motion_observation["release_commit"] != expected_release:
        raise ProbeError("motion observation release does not match the dashboard")
    _validate_observed_travel(
        motion_observation,
        baseline_observation=motion_observation,
        maximum_m=MAX_PRECOMMAND_DRIFT_M,
    )
    return {
        "release": expected_release,
        "profile": EXPECTED_PROFILE,
        "published_count": evidence["published_count"],
        "motion_run_id": evidence["motion_run_id"],
        "motion_run_nonzero_move_count": evidence[
            "motion_run_nonzero_move_count"
        ],
        "move_count": evidence["move_count"],
        "nonzero_move_count": evidence["nonzero_move_count"],
        "zero_move_count": evidence["zero_move_count"],
        "malformed_move_count": evidence["malformed_move_count"],
        "stop_count": evidence["stop_count"],
        "action_count": evidence["action_count"],
        "mode": state["mode"],
        "gait_type": state["gait_type"],
        "error_code": state["error_code"],
        "ack_seq": ack["seq"],
        "motion_observation": motion_observation,
        "legacy_pose": _pose_sample(_mapping(snapshots.get("pose"), "pose snapshot")),
        **telemetry,
    }


def safe_sample(snapshots: Mapping[str, Mapping[str, Any]], *, elapsed_s: float) -> dict[str, Any]:
    control = _validate_exclusions(snapshots, lease_active=True)
    bridge = _mapping(control.get("bridge"), "Bridge status")
    _validate_bridge(bridge)
    evidence = _request_evidence(bridge)
    state = _sport_state(bridge)
    telemetry = _bridge_telemetry(bridge)
    command_ack = _command_ack(bridge)
    return {
        "elapsed_s": round(max(0.0, elapsed_s), 4),
        "bridge_release": bridge.get("release_commit"),
        "manager_command": dict(_mapping(control.get("command"), "manager command")),
        "accepted_command": dict(_mapping(bridge.get("accepted_command"), "Bridge accepted command")),
        "request": {
            key: evidence[key]
            for key in (
                "published_count", "stop_count", "move_count", "zero_move_count", "nonzero_move_count",
                "malformed_move_count", "action_count", "other_count", "last_api_id",
                "motion_run_id", "motion_run_active",
                "motion_run_nonzero_move_count", "motion_run_max_abs_linear_x",
                "motion_run_max_abs_linear_y", "motion_run_max_abs_angular_z",
            )
        },
        "command_ack": {
            key: command_ack.get(key)
            for key in ("source_matches_dashboard", "seq", "type", "age_ms")
        },
        "sport_mode_state": {
            key: state[key]
            for key in ("topic", "mode", "gait_type", "velocity", "error_code", "age_ms")
        },
        "bridge_telemetry": telemetry,
        "motion_observation": _motion_observation(bridge),
        "legacy_pose": _pose_sample(_mapping(snapshots.get("pose"), "pose snapshot")),
    }


def validate_runtime_sample(
    sample: Mapping[str, Any],
    *,
    spec: ProbeSpec,
    baseline: Mapping[str, Any],
    require_motion_evidence: bool,
    previous: RuntimeCursor,
    require_ack_advance: bool,
) -> RuntimeCursor:
    manager = _mapping(sample.get("manager_command"), "manager command")
    accepted = _mapping(sample.get("accepted_command"), "Bridge accepted command")
    request = _mapping(sample.get("request"), "request evidence")
    ack = _mapping(sample.get("command_ack"), "command ACK")
    telemetry = _mapping(sample.get("bridge_telemetry"), "Bridge telemetry")
    sport_state = _mapping(sample.get("sport_mode_state"), "SportModeState")
    if sample.get("bridge_release") != baseline.get("release"):
        raise ProbeError("Bridge release changed during the probe")
    if sport_state.get("error_code") != baseline.get("error_code"):
        raise ProbeError("SportModeState error evidence changed during the probe")
    observation = _mapping(sample.get("motion_observation"), "motion observation")
    observed_travel_m = _validate_observed_travel(
        observation,
        baseline_observation=_mapping(
            baseline.get("motion_observation"), "baseline motion observation"
        ),
        maximum_m=MAX_OBSERVED_TRAVEL_M,
    )
    maximum_observed_travel_m = max(
        previous.max_observed_travel_m,
        observed_travel_m,
    )
    if isinstance(sample, dict):
        sample["observed_travel_m"] = round(observed_travel_m, 6)
        sample["max_observed_travel_m"] = round(maximum_observed_travel_m, 6)
    for command in (manager, accepted):
        if not isinstance(command.get("deadman"), bool):
            raise ProbeError("command evidence is not authoritative")
        x = _finite(command.get("linear_x"), "forward command")
        y = _finite(command.get("linear_y"), "lateral command")
        yaw = _finite(command.get("angular_z"), "yaw command")
        if x < -1e-9 or x > spec.velocity_x_mps + 1e-6 or y != 0.0 or yaw != 0.0:
            raise ProbeError("actual command exceeded the fixed probe envelope")
    run_id = request.get("motion_run_id")
    if type(run_id) is not int or run_id not in {
        baseline["motion_run_id"], baseline["motion_run_id"] + 1
    }:
        raise ProbeError("unexpected Bridge motion-run identity")
    if (
        request.get("zero_move_count") != baseline["zero_move_count"]
        or request.get("malformed_move_count") != baseline["malformed_move_count"]
        or request.get("action_count") != baseline["action_count"]
        or request.get("other_count") != 0
    ):
        raise ProbeError("unexpected Bridge request class")
    counts: dict[str, int] = {}
    for key in (
        "published_count",
        "stop_count",
        "move_count",
        "nonzero_move_count",
        "motion_run_nonzero_move_count",
    ):
        value = request.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= 2_147_483_647
        ):
            raise ProbeError("Bridge request counter is invalid")
        counts[key] = value
    for key in ("published_count", "stop_count", "move_count", "nonzero_move_count"):
        if counts[key] < getattr(previous, key):
            raise ProbeError("Bridge request counters regressed")
    if run_id == previous.motion_run_id:
        if (
            counts["motion_run_nonzero_move_count"]
            < previous.motion_run_nonzero_move_count
        ):
            raise ProbeError("Bridge motion-run counter regressed")
    elif run_id != baseline["motion_run_id"] + 1:
        raise ProbeError("unexpected Bridge motion-run identity")
    joint_seq = telemetry.get("joint_seq")
    if (
        isinstance(joint_seq, bool)
        or not isinstance(joint_seq, int)
        or joint_seq < previous.joint_seq
    ):
        raise ProbeError("Bridge joint sequence regressed")
    ack_seq = ack.get("seq")
    if (
        isinstance(ack_seq, bool)
        or not isinstance(ack_seq, int)
        or ack_seq < previous.ack_seq
    ):
        raise ProbeError("Bridge command acknowledgement regressed")
    for key in ("motion_run_max_abs_linear_y", "motion_run_max_abs_angular_z"):
        if _finite(request.get(key), key) != 0.0:
            raise ProbeError("Bridge published lateral or yaw motion")
    if _finite(request.get("motion_run_max_abs_linear_x"), "Bridge run max x") > spec.velocity_x_mps + 1e-6:
        raise ProbeError("Bridge published above the fixed forward target")
    if require_motion_evidence:
        if any(
            command.get("deadman") is not True
            or _finite(command.get("linear_x"), "accepted forward command") <= 0.0
            for command in (manager, accepted)
        ):
            raise ProbeError("current signed drive acceptance is unconfirmed")
        move_delta = counts["move_count"] - baseline["move_count"]
        nonzero_delta = (
            counts["nonzero_move_count"] - baseline["nonzero_move_count"]
        )
        drive_stop_count = (
            previous.drive_stop_count
            if previous.drive_stop_count is not None
            else counts["stop_count"]
        )
        if (
            run_id != baseline["motion_run_id"] + 1
            or request.get("motion_run_active") is not True
            or request.get("last_api_id") != API_MOVE
            or move_delta <= 0
            or nonzero_delta <= 0
            or move_delta != nonzero_delta
            or counts["motion_run_nonzero_move_count"] != nonzero_delta
            or counts["stop_count"] != drive_stop_count
            or (require_ack_advance and ack_seq <= previous.ack_seq)
            or ack.get("source_matches_dashboard") is not True
            or ack.get("type") != "drive"
            or not 0 <= _finite(ack.get("age_ms"), "command ACK age") <= 750
        ):
            raise ProbeError("signed Bridge drive acceptance is unconfirmed")
    else:
        drive_stop_count = previous.drive_stop_count
    return RuntimeCursor(
        ack_seq=ack_seq,
        published_count=counts["published_count"],
        stop_count=counts["stop_count"],
        move_count=counts["move_count"],
        nonzero_move_count=counts["nonzero_move_count"],
        motion_run_id=run_id,
        motion_run_nonzero_move_count=counts["motion_run_nonzero_move_count"],
        joint_seq=joint_seq,
        observation_seq=int(observation["source_sequence"]),
        max_observed_travel_m=maximum_observed_travel_m,
        drive_stop_count=drive_stop_count,
    )


def _baseline_cursor(baseline: Mapping[str, Any]) -> RuntimeCursor:
    return RuntimeCursor(
        ack_seq=baseline["ack_seq"],
        published_count=baseline["published_count"],
        stop_count=baseline["stop_count"],
        move_count=baseline["move_count"],
        nonzero_move_count=baseline["nonzero_move_count"],
        motion_run_id=baseline["motion_run_id"],
        motion_run_nonzero_move_count=baseline["motion_run_nonzero_move_count"],
        joint_seq=baseline["joint_seq"],
        observation_seq=baseline["motion_observation"]["source_sequence"],
        max_observed_travel_m=0.0,
    )


def validate_post_arm_sample(
    sample: Mapping[str, Any],
    *,
    baseline: Mapping[str, Any],
    previous: RuntimeCursor,
) -> RuntimeCursor:
    """Close the preflight-to-ARM race before any non-zero frame is sent."""

    cursor = validate_runtime_sample(
        sample,
        spec=PROBES["MP-100"],
        baseline=baseline,
        require_motion_evidence=False,
        previous=previous,
        require_ack_advance=False,
    )
    manager = _mapping(sample.get("manager_command"), "manager command")
    accepted = _mapping(sample.get("accepted_command"), "Bridge accepted command")
    _exact_zero(manager, "post-ARM manager command")
    _exact_zero(accepted, "post-ARM Bridge accepted command")
    request = _mapping(sample.get("request"), "request evidence")
    if (
        request.get("move_count") != baseline["move_count"]
        or request.get("nonzero_move_count") != baseline["nonzero_move_count"]
        or request.get("motion_run_id") != baseline["motion_run_id"]
        or request.get("motion_run_active") is not False
        or request.get("last_api_id") != API_STOP_MOVE
    ):
        raise ProbeError("motion appeared during the post-ARM safety check")
    ack = _mapping(sample.get("command_ack"), "command ACK")
    if (
        ack.get("source_matches_dashboard") is not True
        or ack.get("type") != "stop"
        or type(ack.get("seq")) is not int
        or ack.get("seq") < baseline["ack_seq"]
    ):
        raise ProbeError("post-ARM Stop acknowledgement is not authoritative")
    displacement = _validate_observed_travel(
        _mapping(sample.get("motion_observation"), "motion observation"),
        baseline_observation=_mapping(
            baseline.get("motion_observation"), "baseline motion observation"
        ),
        maximum_m=MAX_PRECOMMAND_DRIFT_M,
    )
    if isinstance(sample, dict):
        sample["phase"] = "post_arm"
        sample["observed_travel_m"] = round(displacement, 6)
    return cursor


def first_command_pending(
    sample: Mapping[str, Any], *, baseline: Mapping[str, Any]
) -> bool:
    """Recognize only the untouched signed-zero state while the first ACK is pending."""

    manager = _mapping(sample.get("manager_command"), "manager command")
    accepted = _mapping(sample.get("accepted_command"), "Bridge accepted command")
    request = _mapping(sample.get("request"), "request evidence")
    ack = _mapping(sample.get("command_ack"), "command ACK")
    if (
        accepted.get("deadman") is False
        and all(
            _finite(accepted.get(key), f"accepted command {key}") == 0.0
            for key in ("linear_x", "linear_y", "angular_z")
        )
        and request.get("move_count") == baseline["move_count"]
        and request.get("nonzero_move_count") == baseline["nonzero_move_count"]
        and request.get("motion_run_id") == baseline["motion_run_id"]
        and request.get("motion_run_active") is False
        and request.get("last_api_id") == API_STOP_MOVE
        and ack.get("source_matches_dashboard") is True
        and ack.get("type") == "stop"
        and type(ack.get("seq")) is int
        and ack.get("seq") >= baseline["ack_seq"]
    ):
        # The dashboard manager may already show the just-submitted bounded
        # intent while the signed Bridge status still reports authoritative
        # zero. Any out-of-envelope manager value is rejected by the caller.
        return manager.get("deadman") in {False, True}
    return False


def cleanup_sample(
    snapshots: Mapping[str, Mapping[str, Any]], *, elapsed_s: float
) -> dict[str, Any]:
    """Project only the signed fields needed to prove a fail-closed cleanup."""

    control = _validate_exclusions(snapshots, lease_active=False)
    bridge = _mapping(control.get("bridge"), "Bridge status")
    _validate_bridge(bridge)
    evidence = _request_evidence(bridge)
    state = _sport_state(bridge)
    status_age_s = _finite(bridge.get("status_age_s"), "Bridge status age")
    return {
        "elapsed_s": round(max(0.0, elapsed_s), 4),
        "phase": "cleanup",
        "bridge_release": bridge.get("release_commit"),
        "bridge_authenticated": bridge.get("authenticated"),
        "bridge_status_age_s": status_age_s,
        "lease_active": _mapping(control.get("lease"), "control lease").get("active"),
        "manager_command": dict(_mapping(control.get("command"), "manager command")),
        "accepted_command": dict(
            _mapping(bridge.get("accepted_command"), "Bridge accepted command")
        ),
        "motion_observation": _motion_observation(bridge),
        "legacy_pose": _pose_sample(_mapping(snapshots.get("pose"), "pose snapshot")),
        "sport_mode_state": {
            key: state[key]
            for key in (
                "topic", "mode", "gait_type", "velocity", "error_code", "age_ms"
            )
        },
        "request": {
            key: evidence[key]
            for key in (
                "stop_count", "move_count", "nonzero_move_count", "last_api_id",
                "motion_run_id", "motion_run_active",
                "motion_run_nonzero_move_count", "motion_run_max_abs_linear_x",
                "motion_run_max_abs_linear_y", "motion_run_max_abs_angular_z",
            )
        },
    }


def validate_cleanup_sample(
    sample: Mapping[str, Any], *, expected_release: str
) -> None:
    if sample.get("bridge_release") != expected_release:
        raise ProbeError("final Bridge release identity changed")
    if sample.get("bridge_authenticated") is not True:
        raise ProbeError("final signed Bridge status is unauthenticated")
    if not 0.0 <= _finite(
        sample.get("bridge_status_age_s"), "final Bridge status age"
    ) <= 0.75:
        raise ProbeError("final signed Bridge status is stale")
    if sample.get("lease_active") is not False:
        raise ProbeError("control lease remained active")
    _exact_zero(_mapping(sample.get("manager_command"), "manager command"), "manager command")
    _exact_zero(
        _mapping(sample.get("accepted_command"), "Bridge accepted command"),
        "Bridge accepted command",
    )
    request = _mapping(sample.get("request"), "final request evidence")
    if request.get("last_api_id") != API_STOP_MOVE or request.get("motion_run_active") is not False:
        raise ProbeError("final signed StopMove is unconfirmed")


def _twist(
    *, lease_id: str, seq: int, normalized_x: float, deadman: bool, client_time_ms: float
) -> dict[str, Any]:
    return {
        "type": "twist",
        "lease_id": lease_id,
        "seq": seq,
        "source": "keyboard",
        "deadman": deadman,
        "linear_x": normalized_x if deadman else 0.0,
        "linear_y": 0.0,
        "angular_z": 0.0,
        "speed_scale": 1.0,
        "client_time_ms": client_time_ms,
    }


class ProbeSupervisor:
    def __init__(
        self,
        adapter: DashboardAdapter,
        *,
        release_provider: Callable[[], str],
        monotonic: Callable[[], float] = time.monotonic,
        wall_ms: Callable[[], float] = lambda: time.time_ns() / 1_000_000.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.adapter = adapter
        self.release_provider = release_provider
        self.monotonic = monotonic
        self.wall_ms = wall_ms
        self.sleep = sleep

    def run(self, spec: ProbeSpec) -> dict[str, Any]:
        started = self.monotonic()
        release = self.release_provider()
        initial_snapshots = self.adapter.snapshots()
        baseline = validate_preflight(initial_snapshots, expected_release=release)
        limits = _mapping(
            _mapping(
                _mapping(initial_snapshots.get("control"), "control snapshot").get("control"),
                "control state",
            ).get("limits"),
            "control limits",
        )
        max_linear_x = _finite(limits.get("max_linear_x"), "linear clamp")
        if max_linear_x != 0.30:
            raise ProbeError("server linear clamp is not the fixed 0.30 m/s")
        normalized_x = spec.velocity_x_mps / max_linear_x
        if not 0.0 < normalized_x <= 1.0 or spec.predicted_max_travel_m > 0.10:
            raise ProbeError("fixed probe envelope violates the travel bound")

        lease_id = ""
        stream: ControlStream | None = None
        arm_attempted = False
        valid_lease = False
        released = False
        fallback_disarm = False
        fallback_stop = False
        software_stop_attempted = False
        sequence = -1
        samples: list[dict[str, Any]] = []
        runtime_cursor = _baseline_cursor(baseline)
        error = ""
        cleanup_errors: list[str] = []

        def remember_cleanup(value: BaseException | str) -> None:
            nonlocal error
            detail = str(value)[:MAX_SAFE_TEXT] or type(value).__name__
            cleanup_errors.append(detail)
            if not error:
                error = detail

        def request_software_stop() -> None:
            nonlocal fallback_stop, software_stop_attempted
            if software_stop_attempted:
                return
            software_stop_attempted = True
            try:
                self.adapter.software_stop()
                fallback_stop = True
            except BaseException as exc:
                remember_cleanup(f"software STOP failed: {exc}")

        try:
            arm_attempted = True
            lease_response = self.adapter.arm()
            if not isinstance(lease_response, str) or not 16 <= len(lease_response) <= 256:
                raise ProbeError("dashboard returned an invalid lease")
            lease_id = lease_response
            valid_lease = True
            stream = self.adapter.open_stream()
            stream.bind(lease_id, client_time_ms=self.wall_ms())
            lowstate_deadline = self.monotonic() + POST_ARM_LOWSTATE_TIMEOUT_S
            while True:
                post_arm = safe_sample(
                    self.adapter.snapshots(), elapsed_s=self.monotonic() - started
                )
                runtime_cursor = validate_post_arm_sample(
                    post_arm,
                    baseline=baseline,
                    previous=runtime_cursor,
                )
                samples.append(post_arm)
                if (
                    runtime_cursor.joint_seq > baseline["joint_seq"]
                    and runtime_cursor.observation_seq
                    > baseline["motion_observation"]["source_sequence"]
                ):
                    break
                now = self.monotonic()
                if now >= lowstate_deadline:
                    raise ProbeError(
                        "LowState joint sequence did not advance before motion"
                    )
                self.sleep(
                    min(POST_ARM_LOWSTATE_POLL_S, lowstate_deadline - now)
                )
            drive_started = self.monotonic()
            frame_count = int(round(spec.command_window_s / spec.period_s))
            if frame_count <= 0 or not math.isclose(
                frame_count * spec.period_s, spec.command_window_s, abs_tol=1e-9
            ):
                raise ProbeError("fixed drive schedule is not integral")
            first_acceptance_deadline = drive_started + FIRST_ACCEPTANCE_TIMEOUT_S
            sequence += 1
            stream.send_twist(
                _twist(
                    lease_id=lease_id,
                    seq=sequence,
                    normalized_x=normalized_x,
                    deadman=True,
                    client_time_ms=self.wall_ms(),
                )
            )
            while True:
                first_sample = safe_sample(
                    self.adapter.snapshots(),
                    elapsed_s=self.monotonic() - drive_started,
                )
                first_sample_received = self.monotonic()
                samples.append(first_sample)
                if first_sample_received > first_acceptance_deadline:
                    raise ProbeError("first signed Bridge drive acceptance timed out")
                try:
                    accepted_cursor = validate_runtime_sample(
                        first_sample,
                        spec=spec,
                        baseline=baseline,
                        require_motion_evidence=True,
                        previous=runtime_cursor,
                        require_ack_advance=True,
                    )
                except ProbeError:
                    pending_cursor = validate_runtime_sample(
                        first_sample,
                        spec=spec,
                        baseline=baseline,
                        require_motion_evidence=False,
                        previous=runtime_cursor,
                        require_ack_advance=False,
                    )
                    if not first_command_pending(first_sample, baseline=baseline):
                        raise
                    runtime_cursor = pending_cursor
                    accepted_cursor = None
                if accepted_cursor is not None:
                    runtime_cursor = accepted_cursor
                    break
                now = self.monotonic()
                if now >= first_acceptance_deadline:
                    raise ProbeError("first signed Bridge drive acceptance timed out")
                self.sleep(
                    min(FIRST_ACCEPTANCE_POLL_S, first_acceptance_deadline - now)
                )

            # Frame zero is the single bounded acceptance handshake. Never
            # catch up missed slots; the original absolute 0.70 s window stays
            # authoritative even when a signed status update is delayed.
            next_index = 1
            now = self.monotonic()
            while (
                next_index < frame_count
                and drive_started + next_index * spec.period_s < now
            ):
                next_index += 1
            awaiting_ack = False

            def confirm_runtime_before(deadline: float) -> None:
                nonlocal runtime_cursor, awaiting_ack
                while True:
                    sample = safe_sample(
                        self.adapter.snapshots(),
                        elapsed_s=self.monotonic() - drive_started,
                    )
                    received_at = self.monotonic()
                    samples.append(sample)
                    if received_at > deadline:
                        raise ProbeError(
                            "runtime safety snapshot missed the command deadline"
                        )
                    candidate = validate_runtime_sample(
                        sample,
                        spec=spec,
                        baseline=baseline,
                        require_motion_evidence=True,
                        previous=runtime_cursor,
                        require_ack_advance=False,
                    )
                    if not awaiting_ack or candidate.ack_seq > runtime_cursor.ack_seq:
                        runtime_cursor = candidate
                        awaiting_ack = False
                        return
                    now = self.monotonic()
                    if now >= deadline:
                        raise ProbeError(
                            "signed Bridge drive acknowledgement did not advance"
                        )
                    self.sleep(min(FIRST_ACCEPTANCE_POLL_S, deadline - now))

            for index in range(next_index, frame_count):
                due = drive_started + index * spec.period_s
                now = self.monotonic()
                if now > due + FRAME_LATE_TOLERANCE_S:
                    raise ProbeError("drive scheduler missed its absolute deadline")
                pre_send_at = due - PRE_SEND_SAFETY_LEAD_S
                if now < pre_send_at:
                    self.sleep(pre_send_at - now)
                confirm_runtime_before(due + FRAME_LATE_TOLERANCE_S)
                now = self.monotonic()
                if now < due:
                    self.sleep(due - now)
                if self.monotonic() > due + FRAME_LATE_TOLERANCE_S:
                    raise ProbeError("drive scheduler missed its absolute deadline")
                sequence += 1
                stream.send_twist(
                    _twist(
                        lease_id=lease_id,
                        seq=sequence,
                        normalized_x=normalized_x,
                        deadman=True,
                        client_time_ms=self.wall_ms(),
                    )
                )
                awaiting_ack = True
            drive_deadline = drive_started + spec.command_window_s
            if awaiting_ack:
                confirm_runtime_before(drive_deadline)
            remaining = drive_deadline - self.monotonic()
            if remaining > 0.0:
                self.sleep(remaining)
            elif remaining < -FRAME_LATE_TOLERANCE_S:
                raise ProbeError("drive window cleanup missed its absolute deadline")
        except BaseException as exc:
            error = str(exc)[:MAX_SAFE_TEXT] or type(exc).__name__
        finally:
            if stream is not None and lease_id:
                try:
                    sequence += 1
                    stream.send_twist(
                        _twist(
                            lease_id=lease_id,
                            seq=sequence,
                            normalized_x=0.0,
                            deadman=False,
                            client_time_ms=self.wall_ms(),
                        )
                    )
                except BaseException as exc:
                    remember_cleanup(f"explicit zero failed: {exc}")
                try:
                    release_result = stream.release(
                        lease_id, client_time_ms=self.wall_ms()
                    )
                    if release_result is not True:
                        remember_cleanup(
                            "WebSocket release acknowledgement was not authoritative"
                        )
                    else:
                        released = True
                except BaseException as exc:
                    remember_cleanup(f"WebSocket release failed: {exc}")
                finally:
                    try:
                        stream.close()
                    except BaseException as exc:
                        remember_cleanup(f"control WebSocket close failed: {exc}")
            if valid_lease and not released:
                try:
                    self.adapter.disarm(lease_id)
                    fallback_disarm = True
                except BaseException as exc:
                    remember_cleanup(f"HTTP disarm failed: {exc}")
                    request_software_stop()
            elif arm_attempted and not valid_lease:
                request_software_stop()

        def poll_cleanup() -> tuple[dict[str, Any] | None, str]:
            deadline = self.monotonic() + CLEANUP_CONFIRM_TIMEOUT_S
            latest_fault = ""
            while True:
                try:
                    candidate = cleanup_sample(
                        self.adapter.snapshots(),
                        elapsed_s=self.monotonic() - started,
                    )
                    validate_cleanup_sample(candidate, expected_release=release)
                    return candidate, ""
                except BaseException as exc:
                    latest_fault = str(exc)[:MAX_SAFE_TEXT] or type(exc).__name__
                if self.monotonic() >= deadline:
                    return None, latest_fault
                self.sleep(CLEANUP_CONFIRM_PERIOD_S)

        final_sample, cleanup_fault = poll_cleanup()
        if final_sample is None:
            remember_cleanup(f"cleanup confirmation failed: {cleanup_fault}")
            request_software_stop()
            final_sample, cleanup_fault = poll_cleanup()
        cleanup_confirmed = final_sample is not None
        if final_sample is None:
            remember_cleanup(f"final exact-zero state is unconfirmed: {cleanup_fault}")
            final_sample = {
                "phase": "cleanup",
                "elapsed_s": round(max(0.0, self.monotonic() - started), 4),
                "error": cleanup_fault or "unavailable",
            }
        samples.append(final_sample)

        if cleanup_confirmed:
            try:
                final_travel_m = _validate_observed_travel(
                    _mapping(
                        final_sample.get("motion_observation"),
                        "final motion observation",
                    ),
                    baseline_observation=_mapping(
                        baseline.get("motion_observation"),
                        "baseline motion observation",
                    ),
                    maximum_m=MAX_OBSERVED_TRAVEL_M,
                )
                final_sample["observed_travel_m"] = round(final_travel_m, 6)
                final_request = _mapping(
                    final_sample.get("request"), "final request evidence"
                )
                if final_request.get("motion_run_id") != baseline["motion_run_id"] + 1:
                    raise ProbeError("exactly one Bridge motion run was not observed")
                active_sample = next(
                    (
                        item
                        for item in reversed(samples[:-1])
                        if isinstance(item.get("bridge_telemetry"), Mapping)
                    ),
                    None,
                )
                if active_sample is None or _mapping(
                    active_sample.get("bridge_telemetry"), "Bridge telemetry"
                ).get("joint_seq", -1) <= baseline["joint_seq"]:
                    raise ProbeError("Bridge joint sequence did not advance during the probe")
                actual_x = _finite(
                    final_request.get("motion_run_max_abs_linear_x"),
                    "final Bridge run max x",
                )
                if not math.isclose(actual_x, spec.velocity_x_mps, abs_tol=1e-6):
                    raise ProbeError("Bridge output did not reach the fixed probe target")
            except ProbeError as exc:
                if not error:
                    error = str(exc)

        return {
            "schema": REPORT_SCHEMA,
            "status": "PASS" if not error else "FAIL",
            "status_scope": "SIGNED_COMMAND_PATH_ONLY",
            "locomotion_acceptance": "NOT_EVALUATED",
            "physical_motion": "OPERATOR_CONFIRMATION_REQUIRED",
            "probe": asdict(spec),
            "predicted_max_travel_m": round(spec.predicted_max_travel_m, 6),
            "release": release,
            "profile": EXPECTED_PROFILE,
            "observation_source": MOTION_OBSERVATION_SOURCE,
            "baseline": baseline,
            "samples": _bounded_report_samples(samples),
            "cleanup": {
                "websocket_release_acknowledged": released,
                "http_disarm_fallback": fallback_disarm,
                "software_stop_attempted": software_stop_attempted,
                "software_stop_fallback": fallback_stop,
                "final_exact_zero_confirmed": cleanup_confirmed,
                "errors": cleanup_errors[:8],
            },
            "error": error or None,
        }


class WebSocketControlStream:
    def __init__(self) -> None:
        try:
            from websockets.sync.client import connect
        except ImportError as exc:  # pragma: no cover - deployment dependency gate
            raise ProbeError("websockets sync client is unavailable") from exc
        self._socket = connect(
            CONTROL_WS,
            origin=ORIGIN,
            open_timeout=3.0,
            close_timeout=1.0,
            max_size=MAX_HTTP_BYTES,
        )

    def _receive(self, expected: str) -> Mapping[str, Any]:
        try:
            payload = json.loads(self._socket.recv(timeout=3.0))
        except Exception as exc:
            raise ProbeError(f"control WebSocket {expected} acknowledgement failed") from exc
        if not isinstance(payload, Mapping) or payload.get("type") != expected:
            detail = str(payload.get("detail", "")) if isinstance(payload, Mapping) else ""
            raise ProbeError(detail[:MAX_SAFE_TEXT] or f"control WebSocket did not {expected}")
        return payload

    def bind(self, lease_id: str, *, client_time_ms: float) -> None:
        self._socket.send(json.dumps({
            "type": "bind", "lease_id": lease_id, "client_time_ms": client_time_ms,
        }, separators=(",", ":")))
        self._receive("bound")

    def send_twist(self, payload: Mapping[str, Any]) -> None:
        self._socket.send(json.dumps(dict(payload), separators=(",", ":"), allow_nan=False))

    def release(self, lease_id: str, *, client_time_ms: float) -> bool:
        self._socket.send(json.dumps({
            "type": "release", "lease_id": lease_id, "reason": "c4c_probe_complete",
            "client_time_ms": client_time_ms,
        }, separators=(",", ":")))
        self._receive("released")
        return True

    def close(self) -> None:
        try:
            self._socket.close()
        except Exception:
            pass


class LoopbackDashboardAdapter:
    def _request(self, path: str, *, method: str = "GET", body: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        data = None if body is None else json.dumps(dict(body), separators=(",", ":")).encode("utf-8")
        request = Request(
            ORIGIN + path,
            data=data,
            method=method,
            headers={"Origin": ORIGIN, "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=3.0) as response:  # noqa: S310 - fixed loopback URL
                if response.status < 200 or response.status >= 300:
                    raise ProbeError(f"dashboard {path} returned HTTP {response.status}")
                raw = response.read(MAX_HTTP_BYTES + 1)
                if len(raw) > MAX_HTTP_BYTES:
                    raise ProbeError(f"dashboard {path} response is too large")
                payload = json.loads(raw)
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise ProbeError(f"dashboard {path} is unavailable") from exc
        if not isinstance(payload, Mapping):
            raise ProbeError(f"dashboard {path} returned invalid JSON")
        return payload

    def snapshots(self) -> Mapping[str, Mapping[str, Any]]:
        return {
            "health": self._request(HEALTH_PATH),
            "pose": self._request(POSE_PATH),
            "control": self._request(CONTROL_PATH),
            "navigation": self._request(NAVIGATION_PATH),
            "competition": self._request(COMPETITION_PATH),
            "missions": self._request(MISSIONS_PATH),
            "mapping": self._request(MAPPING_PATH),
        }

    def arm(self) -> str:
        payload = self._request(
            "/api/v1/control/arm", method="POST", body={"input_source": "keyboard"}
        )
        return str(payload.get("lease_id", ""))

    def open_stream(self) -> ControlStream:
        return WebSocketControlStream()

    def disarm(self, lease_id: str) -> None:
        self._request(
            "/api/v1/control/disarm", method="POST", body={"lease_id": lease_id}
        )

    def software_stop(self) -> None:
        self._request(
            "/api/v1/control/stop",
            method="POST",
            body={"reason": "c4c_probe_cleanup_failure"},
        )


def _linux_process_cwd(pid: int) -> Path:
    return (Path("/proc") / str(pid) / "cwd").resolve(strict=True)


def deployed_release_identity(
    *, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    root: Path = ROOT,
    process_cwd: Callable[[int], Path] = _linux_process_cwd,
) -> str:
    """Require the script and dashboard process to share one full-SHA release."""

    try:
        result = runner(
            ("/usr/bin/systemctl", "show", DASHBOARD_UNIT, "-p", "MainPID", "--value"),
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
        if result.returncode != 0:
            raise ProbeError("dashboard service identity is unavailable")
        pid = int(result.stdout.strip())
        if pid <= 0:
            raise ProbeError("dashboard service is inactive")
        process_root = process_cwd(pid).resolve(strict=True)
        script_root = root.resolve(strict=True)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise ProbeError("dashboard service identity is unavailable") from exc
    if process_root != script_root or FULL_COMMIT_RE.fullmatch(process_root.name) is None:
        raise ProbeError("probe and dashboard do not share one exact immutable release")
    return process_root.name


def _private_root(root: Path | None = None) -> Path:
    requested = root or Path(tempfile.gettempdir()) / f"robot-scope-c4c-{os.getuid()}"
    requested = Path(os.path.abspath(str(requested)))
    if requested == Path("/") or requested.is_symlink():
        raise ProbeError("private result directory is unsafe")
    requested.mkdir(mode=0o700, parents=False, exist_ok=True)
    info = requested.stat()
    if info.st_uid != os.geteuid() or not stat.S_ISDIR(info.st_mode):
        raise ProbeError("private result directory ownership is unsafe")
    os.chmod(requested, 0o700)
    return requested


def _write_all(descriptor: int, payload: bytes) -> None:
    """Write a bounded payload completely or fail without reporting success."""

    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise ProbeError("private evidence write did not make progress")
        view = view[written:]


def _write_private_json(payload: Mapping[str, Any], *, root: Path | None = None) -> Path:
    directory = _private_root(root)
    name = f"c4c-{time.time_ns()}-{os.getpid()}.json"
    path = directory / name
    encoded = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > 128 * 1024:
        raise ProbeError("private result exceeds the bounded size")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def _append_event(payload: Mapping[str, Any], *, root: Path | None = None) -> None:
    directory = _private_root(root)
    event = {
        "schema": EVENT_SCHEMA,
        "probe_id": payload.get("probe", {}).get("probe_id"),
        "status": payload.get("status"),
        "release": payload.get("release"),
        "profile": payload.get("profile"),
        "physical_motion": "OPERATOR_CONFIRMATION_REQUIRED",
    }
    encoded = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    path = directory / "operator-events.jsonl"
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def dry_run(spec: ProbeSpec | None = None) -> dict[str, Any]:
    specs = [spec] if spec is not None else list(PROBES.values())
    return {
        "schema": REPORT_SCHEMA,
        "status": "DRY_RUN",
        "network_access": False,
        "mutation_count": 0,
        "probes": [
            {
                **asdict(item),
                "predicted_max_travel_m": round(item.predicted_max_travel_m, 6),
                "normalization": "target_x / server_max_linear_x; speed_scale=1.0 once",
            }
            for item in specs
        ],
        "safety": {
            "one_probe_per_invocation": True,
            "automatic_retry": False,
            "automatic_escalation": False,
            "nav2": False,
            "direct_ros_or_sdk": False,
            "watchdog_tail_s": WATCHDOG_TAIL_S,
            "motion_observation_source": MOTION_OBSERVATION_SOURCE,
            "automatic_observation_fallback": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Default-dry-run fixed C4C Go2 locomotion micro-probe"
    )
    live = parser.add_mutually_exclusive_group()
    live.add_argument("--execute-mp-030", action="store_true")
    live.add_argument("--execute-mp-050", action="store_true")
    live.add_argument("--execute-mp-080", action="store_true")
    live.add_argument("--execute-mp-100", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-stock-baseline-pass", action="store_true")
    parser.add_argument("--confirm-robot-stopped", action="store_true")
    parser.add_argument("--confirm-corridor-clear", action="store_true")
    parser.add_argument("--confirm-estop-ready", action="store_true")
    parser.add_argument("--confirm-safety-operator", action="store_true")
    parser.add_argument(
        "--observation-source",
        choices=(MOTION_OBSERVATION_SOURCE,),
        help="required fixed C4C relative-position evidence source for live probes",
    )
    return parser


def selected_probe(args: argparse.Namespace, parser: argparse.ArgumentParser) -> ProbeSpec | None:
    selected = [probe_id for flag, probe_id in EXECUTE_FLAGS.items() if getattr(args, flag)]
    if args.dry_run and selected:
        parser.error("--dry-run cannot be combined with a live probe")
    if not selected:
        if any(getattr(args, flag) for flag in CONFIRMATION_FLAGS) or args.observation_source:
            parser.error("live confirmations require one fixed live probe")
        return None
    missing = [flag.replace("_", "-") for flag in CONFIRMATION_FLAGS if not getattr(args, flag)]
    if missing:
        parser.error("live probe requires: " + ", ".join("--" + value for value in missing))
    if args.observation_source != MOTION_OBSERVATION_SOURCE:
        parser.error(
            "live probe requires --observation-source " + MOTION_OBSERVATION_SOURCE
        )
    if not MOTION_USE_APPROVED:
        parser.error(
            "C4C motion use is not approved; stationary and dynamic observation "
            "qualification are still required"
        )
    return PROBES[selected[0]]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    spec = selected_probe(args, parser)
    if spec is None:
        payload = dry_run()
    else:
        supervisor = ProbeSupervisor(
            LoopbackDashboardAdapter(), release_provider=deployed_release_identity
        )
        try:
            payload = supervisor.run(spec)
        except ProbeError as exc:
            payload = {
                "schema": REPORT_SCHEMA,
                "status": "BLOCKED",
                "probe": asdict(spec),
                "predicted_max_travel_m": round(spec.predicted_max_travel_m, 6),
                "release": None,
                "profile": EXPECTED_PROFILE,
                "observation_source": MOTION_OBSERVATION_SOURCE,
                "status_scope": "SIGNED_COMMAND_PATH_ONLY",
                "locomotion_acceptance": "NOT_EVALUATED",
                "physical_motion": "NOT_EVALUATED",
                "error": str(exc)[:MAX_SAFE_TEXT],
            }
    output = _write_private_json(payload)
    if spec is not None:
        _append_event(payload)
    print(json.dumps({
        "status": payload["status"],
        "probe_id": payload.get("probe", {}).get("probe_id"),
        "physical_motion": payload.get("physical_motion"),
        "result_file": str(output),
    }, separators=(",", ":")))
    return 0 if payload["status"] in {"PASS", "DRY_RUN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
