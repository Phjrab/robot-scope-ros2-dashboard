"""Allowlisted ROS source identity, selection policy, and persistence."""

from __future__ import annotations

import copy
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Dict


HESAI_XT16_POINTCLOUD_STAGES = {
    "/lidar_points": "raw",
    "/velodyne_points": "converted",
    "/cloud_registered": "registered",
    "/Laser_map": "map",
}
GO2_UTLIDAR_POINTCLOUD_STAGES = {
    "/utlidar/cloud": "raw",
    "/utlidar/cloud_deskewed": "deskewed",
    "/utlidar/cloud_base": "base_frame",
    "/utlidar/grid_map": "local_map",
    "/utlidar/height_map": "height_map",
    "/utlidar/range_map": "range_map",
    "/utlidar/voxel_map": "voxel_map",
}
GO2_USLAM_POINTCLOUD_STAGES = {"/uslam/cloud_map": "map"}
POINTCLOUD_STAGE_LABELS = {
    "raw": "Raw points",
    "converted": "Converted points",
    "deskewed": "Deskewed points",
    "base_frame": "Base-frame points",
    "registered": "Registered cloud",
    "local_map": "Local map",
    "height_map": "Height map",
    "range_map": "Range map",
    "voxel_map": "Voxel map",
    "map": "SLAM map",
    "unknown": "PointCloud",
}
SOURCE_CATEGORIES = ("camera", "pointcloud", "odometry", "occupancy_grid")
SOURCE_SELECTION_STATE_VERSION = 1
SOURCE_SELECTION_STATE_MAX_BYTES = 16 * 1024


def pointcloud_source_metadata(topic: str) -> Dict[str, str]:
    normalized = str(topic or "")
    if normalized in HESAI_XT16_POINTCLOUD_STAGES:
        sensor_id = "hesai_xt16"
        sensor_label = "Hesai XT16"
        stage = HESAI_XT16_POINTCLOUD_STAGES[normalized]
    elif normalized in GO2_UTLIDAR_POINTCLOUD_STAGES:
        sensor_id = "go2_builtin_lidar"
        sensor_label = "Go2 Built-in LiDAR"
        stage = GO2_UTLIDAR_POINTCLOUD_STAGES[normalized]
    elif normalized in GO2_USLAM_POINTCLOUD_STAGES:
        sensor_id = "go2_builtin_lidar"
        sensor_label = "Go2 Built-in LiDAR"
        stage = GO2_USLAM_POINTCLOUD_STAGES[normalized]
    else:
        sensor_id = "generic_pointcloud"
        sensor_label = "Generic PointCloud"
        stage = "unknown"
    stage_label = POINTCLOUD_STAGE_LABELS[stage]
    return {
        "sensor_id": sensor_id,
        "sensor_label": sensor_label,
        "pipeline_stage": stage,
        "pipeline_stage_label": stage_label,
        "display_label": f"{sensor_label} · {stage_label} · {normalized}",
    }


class SourceRegistry:
    """Own selected topics and fail-closed profile-scoped persistence."""

    def __init__(self, profile: Dict[str, Any], state_path: str | None) -> None:
        self.profile = profile
        self.sources = {category: "" for category in SOURCE_CATEGORIES}
        self.requested_sources = dict(self.sources)
        self.state_path = self.normalize_state_path(state_path)
        self.policies = self.policies_from_profile()
        self.overrides = self.load_overrides()
        self.pins: set[str] = set()
        self.origins = {category: "auto" for category in SOURCE_CATEGORIES}
        self.apply_startup_selection()

    @staticmethod
    def normalize_state_path(value: str | None) -> Path | None:
        if value is None or not str(value).strip():
            return None
        path = Path(str(value)).expanduser()
        return path if path.is_absolute() else Path.cwd() / path

    @staticmethod
    def valid_source_name(value: object) -> bool:
        if not isinstance(value, str) or not 1 <= len(value) <= 255:
            return False
        if not value.startswith("/") or value.endswith("/") or "//" in value:
            return False
        return all(character.isalnum() or character in "_~/" for character in value)

    def profile_scope(self) -> Dict[str, str]:
        return {
            "robot_type": str(self.profile.get("robot_type", "")),
            "name": str(self.profile.get("name", "Generic ROS 2")),
        }

    def policies_from_profile(self) -> Dict[str, Dict[str, Any]]:
        raw = self.profile.get("source_selection", {}) if self.profile else {}
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ValueError("source_selection profile setting must be an object")
        unknown = set(raw) - set(SOURCE_CATEGORIES)
        if unknown:
            raise ValueError(
                f"unknown source_selection categories: {', '.join(sorted(unknown))}"
            )
        policies: Dict[str, Dict[str, Any]] = {}
        for category, value in raw.items():
            if not isinstance(value, dict):
                raise ValueError(f"source_selection.{category} must be an object")
            persistent = value.get("persistent", False)
            fail_closed = value.get("fail_closed", False)
            if not isinstance(persistent, bool) or not isinstance(fail_closed, bool):
                raise ValueError(f"source_selection.{category} flags must be booleans")
            allowed = value.get("allowed_offline", [])
            if not isinstance(allowed, list) or any(
                not self.valid_source_name(topic) for topic in allowed
            ):
                raise ValueError(
                    f"source_selection.{category}.allowed_offline must contain ROS topics"
                )
            if len(set(allowed)) != len(allowed):
                raise ValueError(
                    f"source_selection.{category}.allowed_offline contains duplicates"
                )
            default = value.get("default", "")
            if default and not self.valid_source_name(default):
                raise ValueError(
                    f"source_selection.{category}.default must be a ROS topic"
                )
            if default and default not in allowed:
                raise ValueError(
                    f"source_selection.{category}.default must be allowed offline"
                )
            if default and not fail_closed:
                raise ValueError(
                    f"source_selection.{category}.default requires fail_closed"
                )
            policies[category] = {
                "persistent": persistent,
                "fail_closed": fail_closed,
                "allowed_offline": frozenset(allowed),
                "default": default,
            }
        return policies

    @staticmethod
    def validate_state_file(path: Path) -> os.stat_result:
        result = path.lstat()
        if stat.S_ISLNK(result.st_mode) or not stat.S_ISREG(result.st_mode):
            raise ValueError("source selection state must be a regular file")
        if result.st_uid != os.geteuid():
            raise ValueError("source selection state must be owned by the service user")
        if stat.S_IMODE(result.st_mode) != 0o600:
            raise ValueError("source selection state permissions must be 0600")
        if result.st_size > SOURCE_SELECTION_STATE_MAX_BYTES:
            raise ValueError("source selection state exceeds the size limit")
        return result

    def load_overrides(self) -> Dict[str, Dict[str, str]]:
        path = self.state_path
        if path is None:
            return {}
        try:
            expected = self.validate_state_file(path)
        except FileNotFoundError:
            return {}
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise ValueError(f"cannot open source selection state: {exc}") from exc
        try:
            actual = os.fstat(descriptor)
            if (
                not stat.S_ISREG(actual.st_mode)
                or actual.st_dev != expected.st_dev
                or actual.st_ino != expected.st_ino
            ):
                raise ValueError("source selection state changed while opening")
            payload = os.read(descriptor, SOURCE_SELECTION_STATE_MAX_BYTES + 1)
        finally:
            os.close(descriptor)
        if len(payload) > SOURCE_SELECTION_STATE_MAX_BYTES:
            raise ValueError("source selection state exceeds the size limit")
        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("source selection state is not valid JSON") from exc
        if not isinstance(document, dict):
            raise ValueError("source selection state must be an object")
        if document.get("version") != SOURCE_SELECTION_STATE_VERSION:
            raise ValueError("unsupported source selection state version")
        if document.get("profile") != self.profile_scope():
            return {}
        selections = document.get("selections", {})
        if not isinstance(selections, dict):
            raise ValueError("source selection state selections must be an object")
        overrides: Dict[str, Dict[str, str]] = {}
        for category, entry in selections.items():
            policy = self.policies.get(category)
            if not policy or not policy["persistent"]:
                continue
            if not isinstance(entry, dict):
                raise ValueError(f"persisted {category} selection must be an object")
            mode = entry.get("mode")
            topic = entry.get("topic")
            if mode != "pinned" or not self.valid_source_name(topic):
                raise ValueError(f"persisted {category} selection is invalid")
            if topic not in policy["allowed_offline"]:
                raise ValueError(
                    f"persisted {category} selection is not allowed by this profile"
                )
            overrides[category] = {"mode": "pinned", "topic": str(topic)}
        return overrides

    def apply_startup_selection(self) -> None:
        for category, policy in self.policies.items():
            override = self.overrides.get(category)
            if override:
                topic = override["topic"]
                self.requested_sources[category] = topic
                self.sources[category] = topic
                if policy["fail_closed"]:
                    self.pins.add(category)
                self.origins[category] = "persisted"
                continue
            default = str(policy.get("default", ""))
            if default:
                self.requested_sources[category] = default
                self.sources[category] = default
                self.pins.add(category)
                self.origins[category] = "profile_default"

    def write_overrides(self, overrides: Dict[str, Dict[str, str]]) -> None:
        path = self.state_path
        if path is None:
            return
        document = {
            "version": SOURCE_SELECTION_STATE_VERSION,
            "profile": self.profile_scope(),
            "selections": overrides,
        }
        payload = (
            json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        if len(payload) > SOURCE_SELECTION_STATE_MAX_BYTES:
            raise ValueError("source selection state exceeds the size limit")
        parent = path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent_stat = parent.lstat()
        if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
            raise ValueError("source selection state directory must be a real directory")
        try:
            self.validate_state_file(path)
        except FileNotFoundError:
            pass
        descriptor = -1
        temporary = ""
        try:
            descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = ""
            os.chmod(path, 0o600, follow_symlinks=False)
            directory_flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                directory_flags |= os.O_DIRECTORY
            directory_fd = os.open(parent, directory_flags)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise ValueError(f"cannot persist source selection: {exc}") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def apply_selection(
        self,
        values: Dict[str, str],
        graph: Dict[str, Dict[str, Any]],
        *,
        direct_camera_configured: bool,
        direct_camera_uri: str,
    ) -> None:
        """Validate and commit one source-selection transaction."""

        requested = dict(self.requested_sources)
        origins = dict(self.origins)
        pins = set(self.pins)
        overrides = copy.deepcopy(self.overrides)
        for category in self.requested_sources:
            candidate = values.get(category)
            if candidate is None:
                continue
            if category == "camera" and direct_camera_configured:
                if candidate == direct_camera_uri:
                    continue
                raise ValueError(
                    "Go2 direct camera is active; ROS camera selection is locked"
                )
            policy = self.policies.get(category)
            item = graph.get(candidate) if candidate else None
            allowed_offline = bool(
                candidate and policy and candidate in policy["allowed_offline"]
            )
            if candidate and item is None and not allowed_offline:
                raise ValueError(f"unknown ROS topic: {candidate}")
            if candidate and item is not None and item.get("category") != category:
                raise ValueError(f"{candidate} is not a {category} topic")
            if (
                candidate
                and policy
                and policy["persistent"]
                and policy["fail_closed"]
                and candidate not in policy["allowed_offline"]
            ):
                raise ValueError(
                    f"{candidate} is not allowed for persistent {category} selection"
                )
            if not policy:
                requested[category] = candidate
                origins[category] = "user" if candidate else "auto"
                pins.discard(category)
                continue
            if candidate:
                requested[category] = candidate
                origins[category] = "user"
                if policy["fail_closed"]:
                    pins.add(category)
                else:
                    pins.discard(category)
                if policy["persistent"]:
                    overrides[category] = {"mode": "pinned", "topic": candidate}
            else:
                overrides.pop(category, None)
                default = str(policy.get("default", ""))
                requested[category] = default
                origins[category] = "profile_default" if default else "auto"
                if default and policy["fail_closed"]:
                    pins.add(category)
                else:
                    pins.discard(category)
        if overrides != self.overrides:
            self.write_overrides(overrides)
        self.overrides = overrides
        self.requested_sources = requested
        self.origins = origins
        self.pins = pins
