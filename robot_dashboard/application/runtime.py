"""Explicit single-process runtime ownership for the FastAPI application."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from ..discovery import LocalRobotDiscovery
from ..resource_monitor import ResourceMonitor

if TYPE_CHECKING:
    from ..competition import CompetitionStateManager
    from ..dataset_capture import DatasetCaptureManager
    from ..diagnostics import DiagnosticsBundleService
    from ..operator_events import OperatorEventTimeline
    from ..perception import PerceptionBridgeClient
    from ..realsense_profile import RealSenseProfileManager
    from ..model_registry import ModelRegistry
    from ..ros_agent import RosAgent
    from ..saved_maps import SavedMapCatalog
    from ..spatial_routes import SpatialRouteCatalog
    from ..slam_sessions import SlamSessionManager
    from ..relocalization.manager import StationaryRelocalizationManager
    from .lifecycle_coordinator import LifecycleCoordinator
    from .mapping_coordinator import MappingCoordinator
    from .mission_coordinator import MissionCoordinator
    from .navigation_coordinator import NavigationCoordinator
    from .route_planner_coordinator import RoutePlannerCoordinator


@dataclass
class ApplicationRuntime:
    """Own every mutable manager, task, lock, and transport cache.

    Robot Scope deliberately remains a one-worker application.  Centralizing
    ownership here makes that constraint explicit without turning the runtime
    into a service locator for arbitrary plugins or changing manager behavior.
    """

    agent: RosAgent | None = None
    saved_maps: SavedMapCatalog | None = None
    dataset_capture: DatasetCaptureManager | None = None
    mapping: MappingCoordinator | None = None
    navigation: NavigationCoordinator | None = None
    mission: MissionCoordinator | None = None
    route_planner: RoutePlannerCoordinator | None = None
    lifecycle: LifecycleCoordinator | None = None
    operator_events: OperatorEventTimeline | None = None
    diagnostics: DiagnosticsBundleService | None = None
    perception: PerceptionBridgeClient | None = None
    realsense_profile: RealSenseProfileManager | None = None
    model_registry: ModelRegistry | None = None
    competition: CompetitionStateManager | None = None
    relocalization: StationaryRelocalizationManager | None = None
    spatial_routes: SpatialRouteCatalog | None = None
    slam: SlamSessionManager | None = None
    mission_routes: Any | None = None

    pipeline_coordination_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    json_cache: Dict[str, tuple[int, bytes]] = field(default_factory=dict)
    pointcloud_binary_cache: tuple[int, bytes, bytes] | None = None
    pointcloud_binary_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    control_bindings: Dict[str, str] = field(default_factory=dict)
    robot_discovery: LocalRobotDiscovery = field(default_factory=LocalRobotDiscovery)
    resources: ResourceMonitor = field(default_factory=ResourceMonitor)

    def require_agent(self) -> RosAgent:
        if self.agent is None:
            raise RuntimeError("ROS agent is not configured")
        return self.agent


async def close_relocalization(runtime: ApplicationRuntime, logger: Any) -> None:
    """Close the optional worker without preventing remaining safety cleanup."""

    if runtime.relocalization is None:
        return
    try:
        await asyncio.to_thread(runtime.relocalization.close)
    except Exception:
        logger.exception("relocalization manager shutdown failed")


def configure_stationary_relocalization(
    runtime: ApplicationRuntime,
    args: Any,
    project_dir: Any,
    catalog: Any,
) -> None:
    """Delegate optional D2 construction outside the application hotspot."""

    from ..relocalization.runtime_wiring import configure_stationary_relocalization

    configure_stationary_relocalization(runtime, args, project_dir, catalog)


def configure_realsense_profile(runtime: ApplicationRuntime) -> None:
    """Wire optional fixed RealSense profile control after dataset ownership."""

    from ..realsense_profile import RealSenseProfileManager

    dataset = runtime.dataset_capture
    runtime.realsense_profile = RealSenseProfileManager.from_environment(
        dataset_active=(dataset.is_active if dataset is not None else lambda: True),
    )


def configure_competition(runtime: ApplicationRuntime, state_dir: Path) -> None:
    """Keep competition admission tied to the existing live owners."""

    from ..competition import CompetitionStateManager

    def competition_blockers() -> Dict[str, bool]:
        control = runtime.require_agent().control_snapshot()
        lease = control.get("lease", {})
        mapping_active, _ = runtime.mapping.activity()
        return {
            "control_armed": bool(isinstance(lease, dict) and lease.get("active")),
            "navigation_active": runtime.navigation.is_active(),
            "mission_active": runtime.mission.blocks_navigation_goal(),
            "dataset_capture_active": runtime.dataset_capture.is_active(),
            "mapping_active": mapping_active,
        }

    runtime.competition = CompetitionStateManager(
        state_dir,
        blockers_provider=competition_blockers,
        control_provider=runtime.require_agent().control_snapshot,
    )
