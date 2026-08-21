"""Fail-closed process and parameter manager for Go2 Humble navigation.

The HTTP layer supplies only opaque map/revision identifiers and a flat,
allowlisted parameter patch.  Filesystem paths, commands, ROS names and YAML
documents are trusted constructor configuration and can never be supplied by
an API caller.  The launcher is always executed with ``shell=False`` in a new
process group.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

import yaml

from .public_diagnostics import (
    PUBLIC_DIAGNOSTIC_INPUT_CHARS,
    PUBLIC_DIAGNOSTIC_MESSAGE_CHARS,
    public_diagnostic as _public_log_message,
)
from .saved_maps import NavigationMapSnapshot


PARAMS_FILE_TOKEN = "{params_file}"
MAP_YAML_TOKEN = "{map_yaml}"
ALLOWED_COMMAND_TOKENS = frozenset({PARAMS_FILE_TOKEN, MAP_YAML_TOKEN})
REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
MAP_ID_RE = re.compile(r"^[0-9a-f]{24}$")
PRIVATE_CMD_VEL_TOPIC = "/robot_scope/nav/cmd_vel_raw"
PUBLIC_LOG_DEFAULT_ENTRIES = 80
PUBLIC_LOG_MAX_ENTRIES = 100
PUBLIC_LOG_MESSAGE_CHARS = PUBLIC_DIAGNOSTIC_MESSAGE_CHARS
PUBLIC_LOG_INPUT_CHARS = PUBLIC_DIAGNOSTIC_INPUT_CHARS
PUBLIC_LOG_MAX_CURSOR = 9_007_199_254_740_991
PUBLIC_LOG_PHASES = frozenset({"idle", "starting", "running", "stopping", "failed"})
PUBLIC_LOG_SOURCES = frozenset({"manager", "runtime", "parameters"})
COSTMAP_MIN_OBSTACLE_HEIGHT = -1.0
COSTMAP_MAX_OBSTACLE_HEIGHT = 3.0
HUMBLE_BT_PLUGIN_LIBRARIES = (
    "nav2_compute_path_to_pose_action_bt_node",
    "nav2_compute_path_through_poses_action_bt_node",
    "nav2_smooth_path_action_bt_node",
    "nav2_follow_path_action_bt_node",
    "nav2_spin_action_bt_node",
    "nav2_wait_action_bt_node",
    "nav2_assisted_teleop_action_bt_node",
    "nav2_back_up_action_bt_node",
    "nav2_drive_on_heading_bt_node",
    "nav2_clear_costmap_service_bt_node",
    "nav2_is_stuck_condition_bt_node",
    "nav2_goal_reached_condition_bt_node",
    "nav2_goal_updated_condition_bt_node",
    "nav2_globally_updated_goal_condition_bt_node",
    "nav2_is_path_valid_condition_bt_node",
    "nav2_initial_pose_received_condition_bt_node",
    "nav2_reinitialize_global_localization_service_bt_node",
    "nav2_rate_controller_bt_node",
    "nav2_distance_controller_bt_node",
    "nav2_speed_controller_bt_node",
    "nav2_truncate_path_action_bt_node",
    "nav2_truncate_path_local_action_bt_node",
    "nav2_goal_updater_node_bt_node",
    "nav2_recovery_node_bt_node",
    "nav2_pipeline_sequence_bt_node",
    "nav2_round_robin_node_bt_node",
    "nav2_transform_available_condition_bt_node",
    "nav2_time_expired_condition_bt_node",
    "nav2_path_expiring_timer_condition",
    "nav2_distance_traveled_condition_bt_node",
    "nav2_single_trigger_bt_node",
    "nav2_goal_updated_controller_bt_node",
    "nav2_is_battery_low_condition_bt_node",
    "nav2_navigate_through_poses_action_bt_node",
    "nav2_navigate_to_pose_action_bt_node",
    "nav2_remove_passed_goals_action_bt_node",
    "nav2_planner_selector_bt_node",
    "nav2_controller_selector_bt_node",
    "nav2_goal_checker_selector_bt_node",
    "nav2_controller_cancel_bt_node",
    "nav2_path_longer_on_approach_bt_node",
    "nav2_wait_cancel_bt_node",
    "nav2_spin_cancel_bt_node",
    "nav2_back_up_cancel_bt_node",
    "nav2_assisted_teleop_cancel_bt_node",
    "nav2_drive_on_heading_cancel_bt_node",
    "nav2_is_battery_charging_condition_bt_node",
)

class NavigationJobError(RuntimeError):
    """Base class for expected navigation-control failures."""


class NavigationUnavailable(NavigationJobError):
    """Raised when a configured prerequisite is absent or unsafe."""


class NavigationBusy(NavigationJobError):
    """Raised when an operation conflicts with an active navigation job."""


class NavigationConflict(NavigationJobError):
    """Raised when a pinned map or parameter revision no longer matches."""


class NavigationParameterError(NavigationJobError):
    """Raised for an unknown, malformed or unsafe parameter value."""


class NavigationPoseError(NavigationJobError):
    """Raised when a pose is outside known-free map space."""


@dataclass(frozen=True)
class NavigationCommandSpec:
    """One trusted launcher argv template.

    Both private snapshot tokens are required.  No other interpolation is
    accepted, and the executable must be an absolute regular executable.
    """

    argv: tuple[str, ...]
    cwd: Optional[Path] = None

    def __post_init__(self) -> None:
        if not isinstance(self.argv, tuple) or not self.argv:
            raise ValueError("navigation command argv must be a non-empty tuple")
        if not isinstance(self.argv[0], str) or not Path(self.argv[0]).is_absolute():
            raise ValueError("navigation command executable must be absolute")
        seen: set[str] = set()
        for value in self.argv:
            if not isinstance(value, str) or not value or "\x00" in value:
                raise ValueError("navigation command arguments must be non-empty strings")
            for token in ALLOWED_COMMAND_TOKENS:
                if token in value:
                    seen.add(token)
            remainder = value
            for token in ALLOWED_COMMAND_TOKENS:
                remainder = remainder.replace(token, "")
            if "{" in remainder or "}" in remainder:
                raise ValueError("navigation command contains an unsupported token")
        if seen != set(ALLOWED_COMMAND_TOKENS):
            raise ValueError("navigation command must use map and parameter snapshot tokens")


@dataclass(frozen=True)
class ParameterSpec:
    kind: str
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    locked: Optional[bool] = None


PARAMETER_FIELDS = (
    "use_rotate_to_heading",
    "rotation_shim_enabled",
    "rotate_to_goal_heading",
    "desired_linear_vel",
    "controller_frequency",
    "lookahead_time",
    "min_lookahead_dist",
    "use_velocity_scaled_lookahead_dist",
    "rotate_to_heading_angular_vel",
    "max_angular_accel",
    "transform_tolerance",
    "closed_loop",
    "angular_dist_threshold",
    "robot_radius",
    "inflation_radius",
    "cost_scaling_factor",
    "min_obstacle_height",
    "max_obstacle_height",
    "obstacle_max_range",
    "raytrace_max_range",
    "always_send_full_costmap",
    "track_unknown_space",
    "xy_goal_tolerance",
    "yaw_goal_tolerance",
    "required_movement_radius",
    "use_astar",
    "enable_stamped_cmd_vel",
)

PARAMETER_SPECS: Mapping[str, ParameterSpec] = {
    "use_rotate_to_heading": ParameterSpec("bool", locked=False),
    "rotation_shim_enabled": ParameterSpec("bool", locked=True),
    "rotate_to_goal_heading": ParameterSpec("bool", locked=True),
    "desired_linear_vel": ParameterSpec("number", 0.05, 0.30),
    "controller_frequency": ParameterSpec("number", 10.0, 20.0),
    "lookahead_time": ParameterSpec("number", 0.2, 2.0),
    "min_lookahead_dist": ParameterSpec("number", 0.10, 0.60),
    "use_velocity_scaled_lookahead_dist": ParameterSpec("bool"),
    "rotate_to_heading_angular_vel": ParameterSpec("number", 0.10, 0.50),
    "max_angular_accel": ParameterSpec("number", 0.10, 1.20),
    "transform_tolerance": ParameterSpec("number", 0.05, 1.0),
    "closed_loop": ParameterSpec("bool", locked=False),
    "angular_dist_threshold": ParameterSpec("number", 0.10, math.pi),
    "robot_radius": ParameterSpec("number", 0.15, 0.40),
    "inflation_radius": ParameterSpec("number", 0.16, 1.0),
    "cost_scaling_factor": ParameterSpec("number", 1.0, 20.0),
    "min_obstacle_height": ParameterSpec("number", -1.0, 1.0),
    "max_obstacle_height": ParameterSpec("number", 0.1, 3.0),
    "obstacle_max_range": ParameterSpec("number", 0.5, 12.0),
    "raytrace_max_range": ParameterSpec("number", 0.5, 15.0),
    "always_send_full_costmap": ParameterSpec("bool"),
    "track_unknown_space": ParameterSpec("bool"),
    "xy_goal_tolerance": ParameterSpec("number", 0.05, 1.0),
    "yaw_goal_tolerance": ParameterSpec("number", 0.05, math.pi / 2.0),
    "required_movement_radius": ParameterSpec("number", 0.05, 1.0),
    "use_astar": ParameterSpec("bool"),
    "enable_stamped_cmd_vel": ParameterSpec("bool", locked=False),
}

SAFE_TUNED_PARAMETERS: Mapping[str, Any] = {
    "use_rotate_to_heading": False,
    "rotation_shim_enabled": True,
    "rotate_to_goal_heading": True,
    "desired_linear_vel": 0.25,
    "controller_frequency": 10.0,
    "lookahead_time": 0.8,
    "min_lookahead_dist": 0.25,
    "use_velocity_scaled_lookahead_dist": True,
    # PDF 11 uses 0.9 rad/s and 2.0 rad/s^2.  Dashboard control caps are
    # intentionally lower and remain the authoritative safety envelope.
    "rotate_to_heading_angular_vel": 0.50,
    "max_angular_accel": 1.20,
    "transform_tolerance": 0.3,
    "closed_loop": False,
    "angular_dist_threshold": 0.785,
    "robot_radius": 0.22,
    "inflation_radius": 0.25,
    "cost_scaling_factor": 5.0,
    "min_obstacle_height": -0.5,
    "max_obstacle_height": 2.0,
    "obstacle_max_range": 8.0,
    "raytrace_max_range": 10.0,
    "always_send_full_costmap": True,
    "track_unknown_space": True,
    "xy_goal_tolerance": 0.35,
    "yaw_goal_tolerance": 0.45,
    "required_movement_radius": 0.20,
    "use_astar": True,
    "enable_stamped_cmd_vel": False,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parameter_revision(values: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        {key: values[key] for key in PARAMETER_FIELDS},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class NavigationJobManager:
    """Own one allowlisted Humble navigation process group and its snapshots."""

    def __init__(
        self,
        *,
        project_dir: Path,
        runtime_dir: Path,
        base_parameters_file: Path,
        start_command: NavigationCommandSpec,
        map_snapshotter: Callable[[str, str, Path], NavigationMapSnapshot],
        prerequisites: Optional[Mapping[str, Path]] = None,
        on_terminal: Optional[Callable[[str, str], None]] = None,
        stop_grace_seconds: float = 3.0,
        startup_grace_seconds: float = 0.15,
        max_parameter_bytes: int = 1024 * 1024,
        log_capacity: int = 300,
    ) -> None:
        self.project_dir = project_dir.expanduser().resolve(strict=True)
        if not self.project_dir.is_dir():
            raise ValueError("project_dir must be a directory")
        raw_runtime = runtime_dir.expanduser()
        raw_runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
        if raw_runtime.is_symlink():
            raise ValueError("navigation runtime directory must not be a symlink")
        self.runtime_dir = raw_runtime.resolve(strict=True)
        if not self.runtime_dir.is_dir():
            raise ValueError("navigation runtime directory must be a directory")
        try:
            os.chmod(self.runtime_dir, 0o700)
        except OSError:
            pass

        self.base_parameters_file = base_parameters_file.expanduser()
        self.start_command = self._prepare_command(start_command)
        self.map_snapshotter = map_snapshotter
        if not callable(map_snapshotter):
            raise ValueError("map_snapshotter must be callable")
        self.prerequisites = {
            self._safe_label(label): path.expanduser()
            for label, path in (prerequisites or {}).items()
        }
        self.on_terminal = on_terminal
        if on_terminal is not None and not callable(on_terminal):
            raise ValueError("on_terminal must be callable")
        if not 0.05 <= stop_grace_seconds <= 30.0:
            raise ValueError("stop_grace_seconds is outside the supported range")
        if not 0.0 <= startup_grace_seconds <= 5.0:
            raise ValueError("startup_grace_seconds is outside the supported range")
        if not 4096 <= max_parameter_bytes <= 8 * 1024 * 1024:
            raise ValueError("max_parameter_bytes is outside the supported range")
        if not 10 <= log_capacity <= 5000:
            raise ValueError("log_capacity is outside the supported range")
        self.stop_grace_seconds = float(stop_grace_seconds)
        self.startup_grace_seconds = float(startup_grace_seconds)
        self.max_parameter_bytes = int(max_parameter_bytes)

        self.generated_parameters_file = self.runtime_dir / "nav2_params.generated.yaml"
        self.previous_parameters_file = self.runtime_dir / "nav2_params.previous.yaml"
        self.jobs_dir = self.runtime_dir / "jobs"
        self._lock = threading.RLock()
        self._logs: deque[dict[str, Any]] = deque(maxlen=int(log_capacity))
        self._log_stream_id = uuid.uuid4().hex
        self._seq = 0
        self._closing = False
        self._stop_requested = False
        self._pipeline_token = ""
        self._terminal_notified_token = ""
        self._process: Optional[subprocess.Popen[str]] = None
        self._pgid: Optional[int] = None
        self._job_dir: Optional[Path] = None
        self._map_snapshot: Optional[NavigationMapSnapshot] = None
        self._pipeline: dict[str, Any] = {
            "state": "idle",
            "job_id": None,
            "error": None,
            "started_at": None,
            "stopped_at": None,
        }
        self._parameters = dict(SAFE_TUNED_PARAMETERS)
        self._parameter_error: Optional[str] = None
        self._load_existing_parameters()

    @classmethod
    def for_go2_humble(
        cls,
        *,
        project_dir: Path,
        runtime_dir: Path,
        map_snapshotter: Callable[[str, str, Path], NavigationMapSnapshot],
        on_terminal: Optional[Callable[[str, str], None]] = None,
        **kwargs: Any,
    ) -> "NavigationJobManager":
        project = project_dir.expanduser().resolve(strict=True)
        launcher = project / "scripts" / "run_go2_navigation_humble.sh"
        return cls(
            project_dir=project,
            runtime_dir=runtime_dir,
            base_parameters_file=project / "config" / "nav2_params_go2_humble.yaml",
            start_command=NavigationCommandSpec(
                (
                    str(launcher),
                    "--map-yaml",
                    MAP_YAML_TOKEN,
                    "--params-file",
                    PARAMS_FILE_TOKEN,
                ),
                cwd=project,
            ),
            map_snapshotter=map_snapshotter,
            prerequisites={
                "launcher": launcher,
                "runtime_module": project / "robot_dashboard" / "navigation_runtime.py",
                "ros2": Path("/opt/ros/humble/bin/ros2"),
                "map_server": Path("/opt/ros/humble/lib/nav2_map_server/map_server"),
                "controller_server": Path(
                    "/opt/ros/humble/lib/nav2_controller/controller_server"
                ),
                "planner_server": Path(
                    "/opt/ros/humble/lib/nav2_planner/planner_server"
                ),
                "behavior_server": Path(
                    "/opt/ros/humble/lib/nav2_behaviors/behavior_server"
                ),
                "bt_navigator": Path(
                    "/opt/ros/humble/lib/nav2_bt_navigator/bt_navigator"
                ),
                "lifecycle_manager": Path(
                    "/opt/ros/humble/lib/nav2_lifecycle_manager/lifecycle_manager"
                ),
            },
            on_terminal=on_terminal,
            **kwargs,
        )

    @staticmethod
    def _safe_label(value: object) -> str:
        label = str(value)
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", label):
            raise ValueError("navigation prerequisite label is invalid")
        return label

    def _prepare_command(self, spec: NavigationCommandSpec) -> NavigationCommandSpec:
        executable = spec.argv[0]
        cwd = (spec.cwd or self.project_dir).expanduser().resolve(strict=True)
        if not cwd.is_dir():
            raise ValueError("navigation command cwd must be a directory")
        return NavigationCommandSpec(spec.argv, cwd=cwd)

    @property
    def parameter_fields(self) -> tuple[str, ...]:
        return PARAMETER_FIELDS

    @property
    def command_topic(self) -> str:
        return PRIVATE_CMD_VEL_TOPIC

    def is_active(self) -> bool:
        with self._lock:
            return self._pipeline["state"] in {"starting", "running", "stopping"}

    def active_map_identity(self) -> Optional[tuple[str, str]]:
        with self._lock:
            if self._map_snapshot is None:
                return None
            return self._map_snapshot.map_id, self._map_snapshot.revision

    def snapshot(self, *, since_log_seq: int = 0) -> dict[str, Any]:
        with self._lock:
            missing = self._missing_prerequisites_locked()
            available = not missing and self._parameter_error is None and not self._closing
            progress = self._progress_snapshot_locked(
                after=max(0, int(since_log_seq)),
                limit=PUBLIC_LOG_MAX_ENTRIES,
            )
            return {
                "seq": self._seq,
                "available": available,
                "pipeline": dict(self._pipeline),
                "map": self._public_map_locked(),
                "parameters_revision": _parameter_revision(self._parameters),
                "command_topic": PRIVATE_CMD_VEL_TOPIC,
                "missing_prerequisites": missing,
                "configuration_error": self._parameter_error,
                # Compatibility fields retain the existing manager snapshot
                # shape, but now contain only the bounded public projection.
                "logs": progress["entries"],
                "log_cursor": progress["cursor"],
                "logs_truncated": progress["truncated"],
            }

    def progress_snapshot(
        self,
        *,
        after: int = 0,
        limit: int = PUBLIC_LOG_DEFAULT_ENTRIES,
    ) -> dict[str, Any]:
        """Return a bounded read-only public navigation progress stream."""

        if (
            isinstance(after, bool)
            or not isinstance(after, int)
            or not 0 <= after <= PUBLIC_LOG_MAX_CURSOR
        ):
            raise ValueError("navigation log cursor is outside the supported range")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= PUBLIC_LOG_MAX_ENTRIES
        ):
            raise ValueError(
                f"navigation log limit must be from 1 to {PUBLIC_LOG_MAX_ENTRIES}"
            )
        with self._lock:
            return self._progress_snapshot_locked(after=after, limit=limit)

    def _progress_snapshot_locked(self, *, after: int, limit: int) -> dict[str, Any]:
        entries = list(self._logs)
        latest = self._seq
        oldest_seq = entries[0]["seq"] if entries else latest + 1
        truncated = bool(after > latest or (after > 0 and after < oldest_seq - 1))
        if after == 0:
            selected = entries[-limit:]
            truncated = truncated or oldest_seq > 1 or len(entries) > limit
            has_more = False
        else:
            candidates = [item for item in entries if item["seq"] > after]
            selected = candidates[:limit]
            has_more = len(candidates) > len(selected)
        public_entries = [dict(item) for item in selected]
        cursor = public_entries[-1]["seq"] if public_entries else latest

        phase = str(self._pipeline.get("state", "failed"))
        if phase not in PUBLIC_LOG_PHASES:
            phase = "failed"
        raw_job_id = self._pipeline.get("job_id")
        job_id = (
            str(raw_job_id)
            if phase != "idle"
            and isinstance(raw_job_id, str)
            and re.fullmatch(r"[0-9a-f]{32}", raw_job_id)
            else None
        )
        started_at = self._pipeline.get("started_at") if job_id else None
        return {
            "stream_id": self._log_stream_id,
            "job": {
                "id": job_id,
                "phase": phase,
                "started_at": started_at if isinstance(started_at, str) else None,
            },
            "entries": public_entries,
            "cursor": cursor,
            "latest_cursor": latest,
            "truncated": truncated,
            "has_more": has_more,
            "limits": {
                "max_entries": PUBLIC_LOG_MAX_ENTRIES,
                "max_message_chars": PUBLIC_LOG_MESSAGE_CHARS,
            },
        }

    def parameters_snapshot(self) -> dict[str, Any]:
        with self._lock:
            values = {key: self._parameters[key] for key in PARAMETER_FIELDS}
            active = "go2-safe" if values == dict(SAFE_TUNED_PARAMETERS) else "custom"
            return {
                "revision": _parameter_revision(values),
                "active_preset": active,
                "presets": [
                    {
                        "id": "go2-safe",
                        "label": "Go2 실내 안전 튜닝",
                        "description": (
                            "PDF 11 튜닝을 기반으로 하되 dashboard safety cap을 적용합니다: "
                            "linear 0.30 m/s, rotation 0.50 rad/s, angular accel 1.20 rad/s²."
                        ),
                        "values": dict(SAFE_TUNED_PARAMETERS),
                    }
                ],
                "values": values,
                "requires_restart": True,
                "command_topic": PRIVATE_CMD_VEL_TOPIC,
            }

    def update_parameters(
        self,
        base_revision: str,
        patch: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(base_revision, str) or not REVISION_RE.fullmatch(base_revision):
            raise NavigationParameterError("base_revision is invalid")
        if not isinstance(patch, Mapping) or not patch:
            raise NavigationParameterError("parameter values must be a non-empty object")
        with self._lock:
            if self._pipeline["state"] in {"starting", "running", "stopping"}:
                raise NavigationBusy("navigation parameters cannot change while navigation is active")
            current_revision = _parameter_revision(self._parameters)
            if base_revision != current_revision:
                raise NavigationConflict("navigation parameters changed; reload before saving")
            candidate = dict(self._parameters)
            for key, value in patch.items():
                if key not in PARAMETER_SPECS:
                    raise NavigationParameterError(f"unknown navigation parameter: {key}")
                candidate[key] = self._normalize_parameter(key, value)
            candidate = self._validate_parameter_set(candidate)
            self._materialize_parameters(candidate)
            self._parameters = candidate
            self._parameter_error = None
            self._append_log_locked("parameters", "published validated Humble Nav2 parameters")
            return self.parameters_snapshot()

    def start(
        self,
        *,
        map_id: str,
        map_revision: str,
        parameters_revision: str,
    ) -> dict[str, Any]:
        if not isinstance(map_id, str) or not MAP_ID_RE.fullmatch(map_id):
            raise NavigationConflict("saved navigation map was not found")
        if not isinstance(map_revision, str) or not REVISION_RE.fullmatch(map_revision):
            raise NavigationConflict("saved navigation map revision is invalid")
        if not isinstance(parameters_revision, str) or not REVISION_RE.fullmatch(
            parameters_revision
        ):
            raise NavigationConflict("navigation parameter revision is invalid")

        with self._lock:
            if self._closing:
                raise NavigationUnavailable("navigation manager is shutting down")
            if self._pipeline["state"] in {"starting", "running", "stopping"}:
                raise NavigationBusy("navigation pipeline is already active")
            missing = self._missing_prerequisites_locked()
            if missing or self._parameter_error:
                raise NavigationUnavailable("navigation prerequisites are unavailable")
            if parameters_revision != _parameter_revision(self._parameters):
                raise NavigationConflict("navigation parameters changed; reload before starting")
            token = uuid.uuid4().hex
            self._pipeline_token = token
            self._terminal_notified_token = ""
            self._stop_requested = False
            self._pipeline = {
                "state": "starting",
                "job_id": token,
                "error": None,
                "started_at": _utc_now(),
                "stopped_at": None,
            }
            self._append_log_locked("pipeline", "preparing private navigation snapshots")

        job_dir: Optional[Path] = None
        process: Optional[subprocess.Popen[str]] = None
        try:
            job_dir = self._create_job_dir(token)
            map_snapshot = self.map_snapshotter(map_id, map_revision, job_dir)
            if not isinstance(map_snapshot, NavigationMapSnapshot):
                raise NavigationUnavailable("navigation map snapshotter returned invalid data")
            if (
                map_snapshot.map_id != map_id
                or map_snapshot.revision != map_revision
                or map_snapshot.frame_id != "map"
            ):
                raise NavigationConflict(
                    "navigation map snapshot identity does not match the request"
                )
            self._validate_map_snapshot_paths(map_snapshot, job_dir)
            params_file = job_dir / "nav2_params.yaml"
            with self._lock:
                if parameters_revision != _parameter_revision(self._parameters):
                    raise NavigationConflict("navigation parameters changed during startup")
                self._materialize_parameters(self._parameters)
                generated_signature = self._regular_signature(self.generated_parameters_file)
                self._copy_bounded(
                    self.generated_parameters_file,
                    params_file,
                    generated_signature,
                    self.max_parameter_bytes,
                )
            argv = self._render_argv(
                map_yaml=map_snapshot.yaml_path,
                params_file=params_file,
            )
            process = self._spawn(argv, self.start_command.cwd)
            pgid = process.pid
            with self._lock:
                if token != self._pipeline_token or self._stop_requested:
                    raise NavigationBusy("navigation startup was cancelled")
                self._process = process
                self._pgid = pgid
                self._job_dir = job_dir
                self._map_snapshot = map_snapshot
            self._start_reader(token, process)
            if self.startup_grace_seconds:
                deadline = time.monotonic() + self.startup_grace_seconds
                while time.monotonic() < deadline:
                    if process.poll() is not None and not self._group_alive(pgid):
                        raise NavigationUnavailable("navigation launcher exited during startup")
                    time.sleep(0.01)
            with self._lock:
                if token != self._pipeline_token or self._stop_requested:
                    raise NavigationBusy("navigation startup was cancelled")
                self._pipeline["state"] = "running"
                self._append_log_locked("pipeline", "navigation process group started")
            threading.Thread(
                target=self._monitor,
                args=(token, process, pgid),
                name="robot-scope-navigation-monitor",
                daemon=True,
            ).start()
            return self.snapshot()
        except Exception as exc:
            if process is not None:
                self._terminate_group(process, process.pid)
            if job_dir is not None:
                self._cleanup_job_dir(job_dir)
            message = _public_log_message(exc, runtime=False)[:240]
            if not message:
                message = "navigation pipeline could not be started"
            with self._lock:
                if self._pipeline_token == token:
                    self._process = None
                    self._pgid = None
                    self._job_dir = None
                    self._map_snapshot = None
                    self._pipeline.update(
                        state="failed",
                        error=message,
                        stopped_at=_utc_now(),
                    )
                    self._append_log_locked("pipeline", message)
            if isinstance(exc, NavigationJobError):
                raise
            raise NavigationUnavailable("navigation pipeline could not be started") from exc

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._pipeline["state"] not in {"starting", "running", "stopping", "failed"}:
                return self.snapshot()
            self._stop_requested = True
            self._pipeline["state"] = "stopping"
            process = self._process
            pgid = self._pgid
            job_dir = self._job_dir
            self._append_log_locked("pipeline", "stopping navigation process group")
        if pgid is not None:
            self._terminate_group(process, pgid)
        if job_dir is not None:
            self._cleanup_job_dir(job_dir)
        with self._lock:
            self._process = None
            self._pgid = None
            self._job_dir = None
            self._map_snapshot = None
            self._pipeline.update(
                state="idle",
                job_id=None,
                error=None,
                started_at=None,
                stopped_at=_utc_now(),
            )
            self._append_log_locked("pipeline", "navigation pipeline stopped")
            return self.snapshot()

    def validate_active_pose(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: object,
        y: object,
        yaw: object,
    ) -> dict[str, float]:
        px = self._finite_pose_value(x, "x", -1_000_000.0, 1_000_000.0)
        py = self._finite_pose_value(y, "y", -1_000_000.0, 1_000_000.0)
        heading = self._finite_pose_value(yaw, "yaw", -math.pi, math.pi)
        with self._lock:
            if self._pipeline["state"] != "running" or self._map_snapshot is None:
                raise NavigationBusy("navigation pipeline is not running")
            snapshot = self._map_snapshot
            if map_id != snapshot.map_id or map_revision != snapshot.revision:
                raise NavigationConflict("navigation request does not match the pinned map")
            radius = float(self._parameters["robot_radius"])
            if not snapshot.known_free(px, py, clearance_radius=radius):
                raise NavigationPoseError(
                    "pose must be inside known-free map space with robot-radius clearance"
                )
        return {"x": px, "y": py, "yaw": heading}

    def close(self) -> None:
        with self._lock:
            self._closing = True
        try:
            self.stop()
        except NavigationJobError:
            pass

    def _load_existing_parameters(self) -> None:
        if not os.path.lexists(self.generated_parameters_file):
            return
        try:
            signature = self._regular_signature(self.generated_parameters_file)
            content = self._read_bounded(
                self.generated_parameters_file,
                signature,
                self.max_parameter_bytes,
            )
            payload = yaml.safe_load(content.decode("utf-8"))
            self._parameters = self._extract_parameters(payload)
        except Exception:
            self._parameter_error = "generated navigation parameters are invalid"

    def _missing_prerequisites_locked(self) -> list[str]:
        missing: list[str] = []
        checks = {"base_parameters": self.base_parameters_file, **self.prerequisites}
        checks["launcher_executable"] = Path(self.start_command.argv[0])
        for label, path in checks.items():
            try:
                current = path.lstat()
                if not stat.S_ISREG(current.st_mode):
                    raise OSError
                if (
                    label not in {"base_parameters", "runtime_module"}
                    and not os.access(path, os.X_OK)
                ):
                    raise OSError
            except OSError:
                missing.append(label)
        return sorted(set(missing))

    def _public_map_locked(self) -> Optional[dict[str, Any]]:
        if self._map_snapshot is None:
            return None
        return {
            "id": self._map_snapshot.map_id,
            "revision": self._map_snapshot.revision,
            "name": self._map_snapshot.name,
            "frame_id": self._map_snapshot.frame_id,
        }

    @classmethod
    def _normalize_parameter(cls, key: str, value: Any) -> Any:
        spec = PARAMETER_SPECS[key]
        if spec.kind == "bool":
            if not isinstance(value, bool):
                raise NavigationParameterError(f"{key} must be a boolean")
            if spec.locked is not None and value is not spec.locked:
                raise NavigationParameterError(f"{key} is locked to {str(spec.locked).lower()}")
            return value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise NavigationParameterError(f"{key} must be a finite number")
        normalized = float(value)
        if not math.isfinite(normalized):
            raise NavigationParameterError(f"{key} must be a finite number")
        assert spec.minimum is not None and spec.maximum is not None
        if normalized < spec.minimum or normalized > spec.maximum:
            raise NavigationParameterError(
                f"{key} must be between {spec.minimum:g} and {spec.maximum:g}"
            )
        return normalized

    @classmethod
    def _validate_parameter_set(cls, values: Mapping[str, Any]) -> dict[str, Any]:
        if set(values) != set(PARAMETER_FIELDS):
            raise NavigationParameterError("navigation parameter set is incomplete")
        normalized = {
            key: cls._normalize_parameter(key, values[key])
            for key in PARAMETER_FIELDS
        }
        if normalized["inflation_radius"] < normalized["robot_radius"]:
            raise NavigationParameterError("inflation_radius must be at least robot_radius")
        if normalized["max_obstacle_height"] <= normalized["min_obstacle_height"]:
            raise NavigationParameterError(
                "max_obstacle_height must be greater than min_obstacle_height"
            )
        if normalized["raytrace_max_range"] < normalized["obstacle_max_range"]:
            raise NavigationParameterError(
                "raytrace_max_range must be at least obstacle_max_range"
            )
        return normalized

    def _materialize_parameters(self, values: Mapping[str, Any]) -> None:
        normalized = self._validate_parameter_set(values)
        try:
            base_signature = self._regular_signature(self.base_parameters_file)
            source = self._read_bounded(
                self.base_parameters_file,
                base_signature,
                self.max_parameter_bytes,
            )
            document = yaml.safe_load(source.decode("utf-8"))
            if not isinstance(document, dict):
                raise NavigationParameterError("base Nav2 YAML must be an object")
            patched = self._patch_yaml(copy.deepcopy(document), normalized)
            rendered = yaml.safe_dump(
                patched,
                allow_unicode=False,
                default_flow_style=False,
                sort_keys=False,
            ).encode("utf-8")
            if len(rendered) > self.max_parameter_bytes:
                raise NavigationParameterError("generated Nav2 YAML exceeds the configured limit")
            parsed = yaml.safe_load(rendered.decode("utf-8"))
            if self._extract_parameters(parsed) != normalized:
                raise NavigationParameterError("generated Nav2 YAML did not pass validation")
            self._publish_parameter_file(rendered)
        except NavigationJobError:
            raise
        except (OSError, UnicodeError, yaml.YAMLError, TypeError, ValueError) as exc:
            raise NavigationParameterError("Nav2 parameters could not be generated safely") from exc

    @staticmethod
    def _at(document: dict[str, Any], *parts: str) -> dict[str, Any]:
        current: Any = document
        for part in parts:
            if not isinstance(current, dict):
                raise NavigationParameterError("base Nav2 YAML structure is invalid")
            value = current.get(part)
            if value is None:
                value = {}
                current[part] = value
            if not isinstance(value, dict):
                raise NavigationParameterError("base Nav2 YAML structure is invalid")
            current = value
        return current

    @classmethod
    def _patch_yaml(
        cls,
        document: dict[str, Any],
        values: Mapping[str, Any],
    ) -> dict[str, Any]:
        bt = cls._at(document, "bt_navigator", "ros__parameters")
        controller = cls._at(document, "controller_server", "ros__parameters")
        follow = cls._at(document, "controller_server", "ros__parameters", "FollowPath")
        progress = cls._at(
            document, "controller_server", "ros__parameters", "progress_checker"
        )
        goal = cls._at(document, "controller_server", "ros__parameters", "goal_checker")
        planner = cls._at(document, "planner_server", "ros__parameters", "GridBased")
        behavior = cls._at(document, "behavior_server", "ros__parameters")
        global_cost = cls._at(
            document, "global_costmap", "global_costmap", "ros__parameters"
        )
        local_cost = cls._at(
            document, "local_costmap", "local_costmap", "ros__parameters"
        )
        global_scan = cls._at(
            document,
            "global_costmap",
            "global_costmap",
            "ros__parameters",
            "obstacle_layer",
            "scan",
        )
        local_scan = cls._at(
            document,
            "local_costmap",
            "local_costmap",
            "ros__parameters",
            "obstacle_layer",
            "scan",
        )
        global_inflation = cls._at(
            document,
            "global_costmap",
            "global_costmap",
            "ros__parameters",
            "inflation_layer",
        )
        local_inflation = cls._at(
            document,
            "local_costmap",
            "local_costmap",
            "ros__parameters",
            "inflation_layer",
        )

        bt["odom_topic"] = "/utlidar/robot_odom"
        bt["plugin_lib_names"] = list(HUMBLE_BT_PLUGIN_LIBRARIES)
        controller.update(
            {
                "odom_topic": "/utlidar/robot_odom",
                "controller_frequency": values["controller_frequency"],
                "progress_checker_plugin": "progress_checker",
            }
        )
        controller.pop("progress_checker_plugins", None)
        controller.pop("enable_stamped_cmd_vel", None)
        follow.update(
            {
                "plugin": "nav2_rotation_shim_controller::RotationShimController",
                "primary_controller": (
                    "nav2_regulated_pure_pursuit_controller::"
                    "RegulatedPurePursuitController"
                ),
                "use_rotate_to_heading": False,
                "rotate_to_goal_heading": True,
                "desired_linear_vel": values["desired_linear_vel"],
                "lookahead_time": values["lookahead_time"],
                "min_lookahead_dist": values["min_lookahead_dist"],
                "use_velocity_scaled_lookahead_dist": values[
                    "use_velocity_scaled_lookahead_dist"
                ],
                "rotate_to_heading_angular_vel": values[
                    "rotate_to_heading_angular_vel"
                ],
                "max_angular_accel": values["max_angular_accel"],
                "transform_tolerance": values["transform_tolerance"],
                "closed_loop": False,
                "angular_dist_threshold": values["angular_dist_threshold"],
            }
        )
        progress["required_movement_radius"] = values["required_movement_radius"]
        goal["xy_goal_tolerance"] = values["xy_goal_tolerance"]
        goal["yaw_goal_tolerance"] = values["yaw_goal_tolerance"]
        planner.update(
            {
                "plugin": "nav2_navfn_planner/NavfnPlanner",
                "use_astar": values["use_astar"],
            }
        )
        behavior.pop("enable_stamped_cmd_vel", None)
        for plugin_name, plugin_type in (
            ("spin", "nav2_behaviors/Spin"),
            ("backup", "nav2_behaviors/BackUp"),
            ("wait", "nav2_behaviors/Wait"),
        ):
            cls._at(
                document,
                "behavior_server",
                "ros__parameters",
                plugin_name,
            )["plugin"] = plugin_type

        for costmap, scan, inflation in (
            (global_cost, global_scan, global_inflation),
            (local_cost, local_scan, local_inflation),
        ):
            costmap["robot_radius"] = values["robot_radius"]
            costmap["always_send_full_costmap"] = values["always_send_full_costmap"]
            scan.update(
                {
                    "topic": "/scan",
                    # The runtime sidecar applies the user-selected z slice
                    # while PointCloud2 still carries height.  /scan has no z
                    # dimension, so Nav2 must retain a fixed trusted range
                    # containing the sensor origin or it can silently reject
                    # every projected return.
                    "min_obstacle_height": COSTMAP_MIN_OBSTACLE_HEIGHT,
                    "max_obstacle_height": COSTMAP_MAX_OBSTACLE_HEIGHT,
                    "obstacle_max_range": values["obstacle_max_range"],
                    "raytrace_max_range": values["raytrace_max_range"],
                }
            )
            inflation["inflation_radius"] = values["inflation_radius"]
            inflation["cost_scaling_factor"] = values["cost_scaling_factor"]
        global_cost["track_unknown_space"] = values["track_unknown_space"]

        if isinstance(document.get("velocity_smoother"), dict):
            smoother = cls._at(document, "velocity_smoother", "ros__parameters")
            smoother.pop("enable_stamped_cmd_vel", None)
            smoother["odom_topic"] = "/utlidar/robot_odom"

        map_server = cls._at(document, "map_server", "ros__parameters")
        map_server["use_sim_time"] = False
        lifecycle = cls._at(
            document, "lifecycle_manager_navigation", "ros__parameters"
        )
        lifecycle.update(
            {
                "use_sim_time": False,
                "autostart": True,
                "node_names": [
                    "map_server",
                    "controller_server",
                    "planner_server",
                    "behavior_server",
                    "bt_navigator",
                ],
            }
        )
        runtime = cls._at(
            document, "robot_scope_navigation_runtime", "ros__parameters"
        )
        runtime.clear()
        runtime.update(
            {
                "scan_topic": "/scan",
                "odom_topic": "/Odometry",
                "cmd_vel_topic": PRIVATE_CMD_VEL_TOPIC,
                "min_obstacle_height": values["min_obstacle_height"],
                "max_obstacle_height": values["max_obstacle_height"],
                "obstacle_max_range": values["obstacle_max_range"],
                "raytrace_max_range": values["raytrace_max_range"],
            }
        )
        return document

    @classmethod
    def _extract_parameters(cls, document: Any) -> dict[str, Any]:
        if not isinstance(document, dict):
            raise NavigationParameterError("generated Nav2 YAML must be an object")
        controller = cls._at(document, "controller_server", "ros__parameters")
        follow = cls._at(document, "controller_server", "ros__parameters", "FollowPath")
        progress = cls._at(
            document, "controller_server", "ros__parameters", "progress_checker"
        )
        goal = cls._at(document, "controller_server", "ros__parameters", "goal_checker")
        planner = cls._at(document, "planner_server", "ros__parameters", "GridBased")
        global_cost = cls._at(
            document, "global_costmap", "global_costmap", "ros__parameters"
        )
        local_cost = cls._at(
            document, "local_costmap", "local_costmap", "ros__parameters"
        )
        global_scan = cls._at(
            document,
            "global_costmap",
            "global_costmap",
            "ros__parameters",
            "obstacle_layer",
            "scan",
        )
        global_inflation = cls._at(
            document,
            "global_costmap",
            "global_costmap",
            "ros__parameters",
            "inflation_layer",
        )
        values = {
            "use_rotate_to_heading": follow.get("use_rotate_to_heading"),
            "rotation_shim_enabled": follow.get("plugin")
            == "nav2_rotation_shim_controller::RotationShimController",
            "rotate_to_goal_heading": follow.get("rotate_to_goal_heading"),
            "desired_linear_vel": follow.get("desired_linear_vel"),
            "controller_frequency": controller.get("controller_frequency"),
            "lookahead_time": follow.get("lookahead_time"),
            "min_lookahead_dist": follow.get("min_lookahead_dist"),
            "use_velocity_scaled_lookahead_dist": follow.get(
                "use_velocity_scaled_lookahead_dist"
            ),
            "rotate_to_heading_angular_vel": follow.get(
                "rotate_to_heading_angular_vel"
            ),
            "max_angular_accel": follow.get("max_angular_accel"),
            "transform_tolerance": follow.get("transform_tolerance"),
            "closed_loop": follow.get("closed_loop"),
            "angular_dist_threshold": follow.get("angular_dist_threshold"),
            "robot_radius": global_cost.get("robot_radius"),
            "inflation_radius": global_inflation.get("inflation_radius"),
            "cost_scaling_factor": global_inflation.get("cost_scaling_factor"),
            # These two values tune the runtime PointCloud2 -> LaserScan
            # projection, not the post-projection Nav2 height gate.
            "min_obstacle_height": cls._at(
                document, "robot_scope_navigation_runtime", "ros__parameters"
            ).get("min_obstacle_height"),
            "max_obstacle_height": cls._at(
                document, "robot_scope_navigation_runtime", "ros__parameters"
            ).get("max_obstacle_height"),
            "obstacle_max_range": global_scan.get("obstacle_max_range"),
            "raytrace_max_range": global_scan.get("raytrace_max_range"),
            "always_send_full_costmap": global_cost.get("always_send_full_costmap"),
            "track_unknown_space": global_cost.get("track_unknown_space"),
            "xy_goal_tolerance": goal.get("xy_goal_tolerance"),
            "yaw_goal_tolerance": goal.get("yaw_goal_tolerance"),
            "required_movement_radius": progress.get("required_movement_radius"),
            "use_astar": planner.get("use_astar"),
            # Humble controller_server emits plain Twist and does not declare
            # Jazzy's enable_stamped_cmd_vel parameter.  The API keeps the
            # locked false value without writing an undeclared ROS parameter.
            "enable_stamped_cmd_vel": False,
        }
        normalized = cls._validate_parameter_set(values)
        local_scan = cls._at(
            document,
            "local_costmap",
            "local_costmap",
            "ros__parameters",
            "obstacle_layer",
            "scan",
        )
        local_inflation = cls._at(
            document,
            "local_costmap",
            "local_costmap",
            "ros__parameters",
            "inflation_layer",
        )
        fixed_checks = (
            controller.get("odom_topic") == "/utlidar/robot_odom",
            controller.get("progress_checker_plugin") == "progress_checker",
            "progress_checker_plugins" not in controller,
            cls._at(document, "bt_navigator", "ros__parameters").get("odom_topic")
            == "/utlidar/robot_odom",
            cls._at(document, "bt_navigator", "ros__parameters").get(
                "plugin_lib_names"
            )
            == list(HUMBLE_BT_PLUGIN_LIBRARIES),
            planner.get("plugin") == "nav2_navfn_planner/NavfnPlanner",
            global_scan.get("topic") == "/scan",
            local_scan.get("topic") == "/scan",
            local_cost.get("robot_radius") == normalized["robot_radius"],
            local_inflation.get("inflation_radius") == normalized["inflation_radius"],
            local_inflation.get("cost_scaling_factor")
            == normalized["cost_scaling_factor"],
            global_scan.get("min_obstacle_height") == COSTMAP_MIN_OBSTACLE_HEIGHT,
            global_scan.get("max_obstacle_height") == COSTMAP_MAX_OBSTACLE_HEIGHT,
            local_scan.get("min_obstacle_height") == COSTMAP_MIN_OBSTACLE_HEIGHT,
            local_scan.get("max_obstacle_height") == COSTMAP_MAX_OBSTACLE_HEIGHT,
            local_scan.get("obstacle_max_range") == normalized["obstacle_max_range"],
            local_scan.get("raytrace_max_range") == normalized["raytrace_max_range"],
            "enable_stamped_cmd_vel" not in controller,
            cls._at(document, "behavior_server", "ros__parameters", "spin").get(
                "plugin"
            )
            == "nav2_behaviors/Spin",
            cls._at(document, "behavior_server", "ros__parameters", "backup").get(
                "plugin"
            )
            == "nav2_behaviors/BackUp",
            cls._at(document, "behavior_server", "ros__parameters", "wait").get(
                "plugin"
            )
            == "nav2_behaviors/Wait",
        )
        runtime = cls._at(
            document, "robot_scope_navigation_runtime", "ros__parameters"
        )
        fixed_checks += (
            set(runtime)
            == {
                "scan_topic",
                "odom_topic",
                "cmd_vel_topic",
                "min_obstacle_height",
                "max_obstacle_height",
                "obstacle_max_range",
                "raytrace_max_range",
            },
            runtime.get("scan_topic") == "/scan",
            runtime.get("odom_topic") == "/Odometry",
            runtime.get("cmd_vel_topic") == PRIVATE_CMD_VEL_TOPIC,
            runtime.get("min_obstacle_height") == normalized["min_obstacle_height"],
            runtime.get("max_obstacle_height") == normalized["max_obstacle_height"],
            runtime.get("obstacle_max_range") == normalized["obstacle_max_range"],
            runtime.get("raytrace_max_range") == normalized["raytrace_max_range"],
        )
        if not all(fixed_checks):
            raise NavigationParameterError("generated Nav2 YAML fixed bindings are invalid")
        return normalized

    def _publish_parameter_file(self, content: bytes) -> None:
        transactions = self.runtime_dir / ".parameter_transactions"
        transactions.mkdir(mode=0o700, exist_ok=True)
        if transactions.is_symlink() or transactions.resolve(strict=True).parent != self.runtime_dir:
            raise NavigationParameterError("parameter transaction directory is unsafe")
        transaction = transactions / uuid.uuid4().hex
        transaction.mkdir(mode=0o700, exist_ok=False)
        staged = transaction / "nav2_params.yaml"
        previous = transaction / "previous.yaml"
        try:
            self._write_exclusive(staged, content, 0o600)
            if os.path.lexists(self.generated_parameters_file):
                signature = self._regular_signature(self.generated_parameters_file)
                self._copy_bounded(
                    self.generated_parameters_file,
                    previous,
                    signature,
                    self.max_parameter_bytes,
                )
                if self._regular_signature(self.generated_parameters_file) != signature:
                    raise NavigationConflict("generated Nav2 parameters changed during update")
                os.replace(previous, self.previous_parameters_file)
            os.replace(staged, self.generated_parameters_file)
            self._fsync_directory(self.runtime_dir)
        except NavigationJobError:
            raise
        except OSError as exc:
            raise NavigationParameterError("Nav2 parameters could not be published") from exc
        finally:
            shutil.rmtree(transaction, ignore_errors=True)
            try:
                transactions.rmdir()
            except OSError:
                pass

    def _create_job_dir(self, token: str) -> Path:
        self.jobs_dir.mkdir(mode=0o700, exist_ok=True)
        if self.jobs_dir.is_symlink() or self.jobs_dir.resolve(strict=True).parent != self.runtime_dir:
            raise NavigationUnavailable("navigation job directory is unsafe")
        job = self.jobs_dir / token
        job.mkdir(mode=0o700, exist_ok=False)
        return job

    def _render_argv(self, *, map_yaml: Path, params_file: Path) -> tuple[str, ...]:
        replacements = {
            MAP_YAML_TOKEN: str(map_yaml),
            PARAMS_FILE_TOKEN: str(params_file),
        }
        return tuple(
            self._replace_tokens(value, replacements)
            for value in self.start_command.argv
        )

    @staticmethod
    def _validate_map_snapshot_paths(
        snapshot: NavigationMapSnapshot,
        job_dir: Path,
    ) -> None:
        resolved_job = job_dir.resolve(strict=True)
        identities: list[tuple[int, int]] = []
        for path in (snapshot.yaml_path, snapshot.image_path):
            candidate = Path(path)
            try:
                current = candidate.lstat()
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise NavigationUnavailable(
                    "navigation map snapshot file is unavailable"
                ) from exc
            if (
                not stat.S_ISREG(current.st_mode)
                or candidate.is_symlink()
                or resolved.parent != resolved_job
            ):
                raise NavigationUnavailable("navigation map snapshot path is unsafe")
            identities.append((current.st_dev, current.st_ino))
        if len(set(identities)) != len(identities):
            raise NavigationUnavailable("navigation map snapshot files must be distinct")

    @staticmethod
    def _replace_tokens(value: str, replacements: Mapping[str, str]) -> str:
        rendered = value
        for token, replacement in replacements.items():
            rendered = rendered.replace(token, replacement)
        if "{" in rendered or "}" in rendered or "\x00" in rendered:
            raise NavigationUnavailable("navigation command rendering failed")
        return rendered

    @staticmethod
    def _finite_pose_value(value: object, label: str, low: float, high: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise NavigationPoseError(f"{label} must be a finite number")
        normalized = float(value)
        if not math.isfinite(normalized) or normalized < low or normalized > high:
            raise NavigationPoseError(f"{label} is outside the supported range")
        return normalized

    @staticmethod
    def _regular_signature(path: Path) -> tuple[int, int, int, int]:
        current = path.lstat()
        if not stat.S_ISREG(current.st_mode):
            raise NavigationUnavailable("navigation file is not a regular file")
        return current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns

    @classmethod
    def _read_bounded(
        cls,
        path: Path,
        expected: tuple[int, int, int, int],
        limit: int,
    ) -> bytes:
        flags = os.O_RDONLY | (getattr(os, "O_NOFOLLOW", 0))
        descriptor = os.open(path, flags)
        try:
            before = os.fstat(descriptor)
            signature = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            if not stat.S_ISREG(before.st_mode) or signature != expected:
                raise NavigationConflict("navigation file changed before it was read")
            if before.st_size <= 0 or before.st_size > limit:
                raise NavigationUnavailable("navigation file exceeds the configured limit")
            content = bytearray()
            while len(content) < before.st_size:
                chunk = os.read(descriptor, min(1024 * 1024, before.st_size - len(content)))
                if not chunk:
                    raise NavigationConflict("navigation file changed while it was read")
                content.extend(chunk)
            if os.read(descriptor, 1):
                raise NavigationConflict("navigation file grew while it was read")
            after = os.fstat(descriptor)
            after_signature = (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            )
            if after_signature != expected:
                raise NavigationConflict("navigation file changed while it was read")
            return bytes(content)
        finally:
            os.close(descriptor)

    @classmethod
    def _copy_bounded(
        cls,
        source: Path,
        target: Path,
        expected: tuple[int, int, int, int],
        limit: int,
    ) -> None:
        content = cls._read_bounded(source, expected, limit)
        cls._write_exclusive(target, content, 0o600)
        if cls._regular_signature(target)[:2] == expected[:2]:
            raise NavigationUnavailable("navigation snapshot must be an independent copy")

    @staticmethod
    def _write_exclusive(path: Path, content: bytes, mode: int) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, mode)
        try:
            view = memoryview(content)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _spawn(argv: Sequence[str], cwd: Optional[Path]) -> subprocess.Popen[str]:
        return subprocess.Popen(
            list(argv),
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,
            start_new_session=True,
            close_fds=True,
        )

    def _start_reader(self, token: str, process: subprocess.Popen[str]) -> None:
        def read_output() -> None:
            if process.stdout is None:
                return
            try:
                while True:
                    line = process.stdout.readline(PUBLIC_LOG_INPUT_CHARS + 1)
                    if not line:
                        break
                    self._append_runtime_log(token, line)
            finally:
                process.stdout.close()

        threading.Thread(
            target=read_output,
            name="robot-scope-navigation-log",
            daemon=True,
        ).start()

    def _monitor(self, token: str, process: subprocess.Popen[str], pgid: int) -> None:
        exit_code = process.wait()
        callback: Optional[Callable[[str, str], None]] = None
        reason = "pipeline_exit"
        job_dir: Optional[Path] = None
        with self._lock:
            if token != self._pipeline_token or self._pipeline["state"] == "idle":
                return
            expected_stop = self._stop_requested or self._pipeline["state"] == "stopping"
            if expected_stop:
                # The operator/close path owns process-group teardown and state
                # publication.  Returning here keeps concurrent stop idempotent.
                return
            self._process = None
            self._pgid = None
            job_dir = self._job_dir
            self._job_dir = None
            self._map_snapshot = None
            self._pipeline.update(
                state="failed",
                error=f"navigation pipeline exited unexpectedly (status {exit_code})",
                stopped_at=_utc_now(),
            )
            self._append_log_locked("pipeline", self._pipeline["error"])
            if self._terminal_notified_token != token:
                self._terminal_notified_token = token
                callback = self.on_terminal

        # The launcher is the process-group leader, but its Nav2 children can
        # survive a shell crash or SIGKILL.  Close the signed motion gate before
        # waiting on process teardown, then terminate the now-orphaned group.
        # Never wait indefinitely for the group to disappear on its own.
        if callback is not None:
            try:
                callback(reason, token)
            except Exception as exc:
                self._append_log(
                    "pipeline",
                    f"navigation terminal callback failed: {type(exc).__name__}",
                )
        if self._group_alive(pgid):
            self._terminate_group(process, pgid)
        if job_dir is not None:
            self._cleanup_job_dir(job_dir)

    def _terminate_group(
        self,
        process: Optional[subprocess.Popen[str]],
        pgid: int,
    ) -> None:
        try:
            os.killpg(pgid, signal.SIGINT)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + self.stop_grace_seconds
        while time.monotonic() < deadline:
            if not self._group_alive(pgid):
                return
            time.sleep(0.03)
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + min(1.0, self.stop_grace_seconds)
        while time.monotonic() < deadline:
            if not self._group_alive(pgid):
                return
            time.sleep(0.03)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if process is not None:
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass

    @staticmethod
    def _group_alive(pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _cleanup_job_dir(self, job_dir: Path) -> None:
        try:
            candidate = Path(job_dir)
            if (
                candidate.parent == self.jobs_dir
                and re.fullmatch(r"[0-9a-f]{32}", candidate.name)
            ):
                try:
                    current = candidate.lstat()
                    jobs_root = self.jobs_dir.resolve(strict=True)
                    safe = bool(
                        stat.S_ISDIR(current.st_mode)
                        and not candidate.is_symlink()
                        and candidate.resolve(strict=True).parent == jobs_root
                    )
                except OSError:
                    safe = False
                if safe:
                    shutil.rmtree(candidate, ignore_errors=True)
            try:
                self.jobs_dir.rmdir()
            except OSError:
                pass
        except OSError:
            pass

    def _append_log(self, source: str, message: object) -> None:
        clean = _public_log_message(message, runtime=False)
        if not clean:
            return
        with self._lock:
            self._append_log_locked(source, clean)

    def _append_runtime_log(self, token: str, message: object) -> None:
        clean = _public_log_message(message, runtime=True)
        if not clean:
            return
        with self._lock:
            # A pipe reader may drain buffered output after stop, or after a
            # replacement process has already started.  Never attach that old
            # output to idle state or to the replacement job identity.
            if (
                token != self._pipeline_token
                or self._pipeline.get("job_id") != token
                or self._pipeline.get("state") == "idle"
            ):
                return
            self._append_public_log_locked("runtime", clean)

    def _append_log_locked(self, source: str, message: object) -> None:
        clean = _public_log_message(message, runtime=False)
        if not clean:
            return
        public_source = "parameters" if source == "parameters" else "manager"
        self._append_public_log_locked(public_source, clean)

    def _append_public_log_locked(self, source: str, message: str) -> None:
        public_source = source if source in PUBLIC_LOG_SOURCES else "manager"
        phase = str(self._pipeline.get("state", "failed"))
        if phase not in PUBLIC_LOG_PHASES:
            phase = "failed"
        raw_job_id = self._pipeline.get("job_id")
        job_id = (
            str(raw_job_id)
            if public_source != "parameters"
            and isinstance(raw_job_id, str)
            and re.fullmatch(r"[0-9a-f]{32}", raw_job_id)
            else None
        )
        self._seq += 1
        self._logs.append(
            {
                "seq": self._seq,
                "timestamp": _utc_now(),
                "job_id": job_id,
                "phase": phase,
                "source": public_source,
                "message": str(message)[:PUBLIC_LOG_MESSAGE_CHARS],
            }
        )
