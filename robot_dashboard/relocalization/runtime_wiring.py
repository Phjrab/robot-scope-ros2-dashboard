"""Fail-closed runtime wiring for the opt-in stationary D2 candidate owner."""

from __future__ import annotations

import math
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from ..saved_maps import SavedMapError, SavedMapNotFound
from .collector import FixedCloudRegisteredCollector
from .models import BACKEND
from .manager import (
    PROFILE,
    RelocalizationConflict,
    StationaryRelocalizationManager,
    require_stationary_preflight,
    sport_velocity_is_stationary,
)
from .process_adapter import OfflineRegistrationProcess


RELOCALIZATION_ENABLE_ENV = "ROBOT_SCOPE_D2_STATIONARY_RELOCALIZATION"
REGISTRATION_RELATIVE_PATH = Path(
    "build/robot_scope_registration/robot_scope_offline_registration"
)
REGISTRATION_BACKEND_ENV = "ROBOT_SCOPE_D2_REGISTRATION_BACKEND"
REGISTRATION_BACKENDS = {
    BACKEND: REGISTRATION_RELATIVE_PATH,
    "pcl-ndt2d": Path(
        "build/robot_scope_registration/robot_scope_offline_registration_pcl_ndt2d"
    ),
    "pcl-gicp": Path(
        "build/robot_scope_registration/robot_scope_offline_registration_pcl_gicp"
    ),
}


class AgentPort(Protocol):
    def control_snapshot(self) -> dict[str, Any]: ...
    def relocalization_cloud_snapshot(self) -> dict[str, Any]: ...
    def relocalization_motion_snapshot(self) -> dict[str, Any]: ...
    def relocalization_evidence_snapshot(self) -> dict[str, Any]: ...


class MappingPort(Protocol):
    def activity(self) -> tuple[bool, list[str]]: ...
    def pipeline_state(self) -> str: ...


class NavigationPort(Protocol):
    def is_active(self) -> bool: ...
    def view(self) -> dict[str, Any]: ...


class DatasetPort(Protocol):
    def is_active(self) -> bool: ...


class CatalogPort(Protocol):
    def snapshot_relocalization_family(self, *args: Any) -> Any: ...
    def relocalization_family_is_current(self, bundle: Any) -> bool: ...


def build_stationary_relocalization_manager(
    *,
    enabled: bool,
    project_dir: Path,
    runtime_root: Path,
    mapping_profile: str,
    agent: AgentPort,
    catalog: CatalogPort,
    mapping: MappingPort,
    navigation: NavigationPort,
    dataset_capture: DatasetPort,
) -> StationaryRelocalizationManager | None:
    """Build D2 only for the exact profile, observer and fixed executable."""

    if enabled is not True:
        return None
    if mapping_profile != PROFILE:
        raise RuntimeError("D2 relocalization requires the competition FAST-LIO profile")
    evidence = agent.relocalization_evidence_snapshot()
    if not isinstance(evidence, Mapping) or evidence.get("enabled") is not True:
        raise RuntimeError("D2 relocalization requires the fixed observer opt-in")

    root = _prepare_private_runtime_root(Path(runtime_root))
    backend = os.environ.get(REGISTRATION_BACKEND_ENV, BACKEND)
    executable_path = REGISTRATION_BACKENDS.get(backend)
    if executable_path is None:
        raise RuntimeError("D2 registration backend is not in the fixed allowlist")
    executable = Path(project_dir) / executable_path
    registration = OfflineRegistrationProcess(
        executable,
        (root,),
        expected_backend=backend,
    )

    def safety_snapshot() -> dict[str, Any]:
        return stationary_runtime_snapshot(
            mapping_profile=mapping_profile,
            agent=agent,
            mapping=mapping,
            navigation=navigation,
            dataset_capture=dataset_capture,
        )

    def safety_check() -> None:
        require_stationary_preflight(
            safety_snapshot(),
            physical_safety_confirmed=True,
        )

    collector = FixedCloudRegisteredCollector(
        agent.relocalization_cloud_snapshot,
        agent.relocalization_motion_snapshot,
        safety_check=safety_check,
    )

    def snapshot_exact_family(
        map_id: str,
        map_revision: str,
        source_pcd_id: str,
        source_pcd_revision: str,
        destination: Path,
    ) -> Any:
        try:
            return catalog.snapshot_relocalization_family(
                map_id,
                map_revision,
                source_pcd_id,
                source_pcd_revision,
                destination,
            )
        except SavedMapNotFound as exc:
            raise RelocalizationConflict(
                "exact saved map or source PCD is unavailable"
            ) from exc
        except SavedMapError as exc:
            raise RelocalizationConflict(
                "exact saved-map lineage is unavailable or changed"
            ) from exc

    return StationaryRelocalizationManager(
        root,
        snapshotter=snapshot_exact_family,
        current_checker=catalog.relocalization_family_is_current,
        collector=collector,
        registration=registration,
        safety_provider=safety_snapshot,
    )


def configure_stationary_relocalization(
    runtime: Any,
    args: Any,
    project_dir: Path,
    catalog: CatalogPort,
) -> None:
    """Attach the optional manager without expanding the app composition root."""

    runtime.relocalization = build_stationary_relocalization_manager(
        enabled=os.environ.get(RELOCALIZATION_ENABLE_ENV) == "1",
        project_dir=project_dir,
        runtime_root=(
            Path(args.navigation_runtime_dir).expanduser().resolve()
            / "relocalization"
        ),
        mapping_profile=args.mapping_profile,
        agent=runtime.agent,
        catalog=catalog,
        mapping=runtime.mapping,
        navigation=runtime.navigation,
        dataset_capture=runtime.dataset_capture,
    )


def stationary_runtime_snapshot(
    *,
    mapping_profile: str,
    agent: AgentPort,
    mapping: MappingPort,
    navigation: NavigationPort,
    dataset_capture: DatasetPort,
) -> dict[str, Any]:
    """Project only fixed runtime facts used by the D2 stationary gate."""

    control = _mapping(agent.control_snapshot())
    lease = _mapping(control.get("lease"))
    command = _mapping(control.get("command"))
    bridge = _mapping(control.get("bridge"))
    sport = _mapping(bridge.get("sport_mode_state"))
    action_guard = _mapping(control.get("action_guard"))
    cloud = _mapping(agent.relocalization_cloud_snapshot())
    motion = _mapping(agent.relocalization_motion_snapshot())
    navigation_view = _mapping(navigation.view())
    goal = _mapping(navigation_view.get("goal"))
    mapping_active, _ = mapping.activity()

    command_velocity = {
        "vx": command.get("linear_x"),
        "vy": command.get("linear_y"),
        "wz": command.get("angular_z"),
    }
    sport_velocity = sport.get("velocity")
    velocity = (
        {"vx": sport_velocity[0], "vy": sport_velocity[1], "wz": sport_velocity[2]}
        if _finite_vector(sport_velocity, 3)
        else {}
    )
    command_zero = all(
        command_velocity[axis] == 0.0 for axis in ("vx", "vy", "wz")
    )
    stationary = bool(
        sport.get("fresh") is True
        and sport_velocity_is_stationary(velocity)
    )
    lease_active = lease.get("active") is True
    deadman = command.get("deadman") is True
    bridge_ready = bool(
        bridge.get("ready") is True
        and bridge.get("authenticated") is True
        and bridge.get("connected") is True
    )
    control_disarmed = bool(
        not lease_active
        and not deadman
        and command_zero
        and action_guard.get("active") is not True
    )
    navigation_active = navigation.is_active()

    return {
        "profile": mapping_profile,
        "stationary": stationary,
        "control_disarmed": control_disarmed,
        "control_lease_active": lease_active,
        "navigation_lease_active": bool(
            lease_active and lease.get("input_source") == "navigation"
        ),
        "deadman": deadman,
        "goal_idle": bool(not navigation_active and goal.get("state") == "idle"),
        "mapping_active": bool(mapping_active),
        "dataset_active": dataset_capture.is_active(),
        "observation_pipeline_running": mapping.pipeline_state() == "running",
        "motion_evidence_fresh": motion.get("fresh") is True,
        "control_bridge_ready": bridge_ready,
        "software_stop_latched": control.get("estop_latched") is True,
        "source_topic": cloud.get("topic"),
        "source_frame": cloud.get("frame_id"),
        "source_publishers": cloud.get("publisher_count"),
        "source_fresh": cloud.get("fresh") is True,
        "source_qos_valid": cloud.get("qos_valid") is True,
        "velocity": velocity,
    }


def _prepare_private_runtime_root(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise RuntimeError("D2 runtime root must be an absolute real directory")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError("D2 runtime root must be a real directory")
    resolved = path.resolve(strict=True)
    if stat.S_IMODE(resolved.stat().st_mode) & 0o077:
        raise RuntimeError("D2 runtime root must be private")
    return resolved


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _finite_vector(value: Any, length: int) -> bool:
    return bool(
        isinstance(value, (list, tuple))
        and len(value) == length
        and all(
            not isinstance(item, bool)
            and isinstance(item, (int, float))
            and math.isfinite(float(item))
            for item in value
        )
    )


__all__ = [
    "RELOCALIZATION_ENABLE_ENV",
    "build_stationary_relocalization_manager",
    "configure_stationary_relocalization",
    "stationary_runtime_snapshot",
]
