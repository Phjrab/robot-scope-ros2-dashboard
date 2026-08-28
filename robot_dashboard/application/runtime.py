"""Explicit single-process runtime ownership for the FastAPI application."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict

from ..discovery import LocalRobotDiscovery

if TYPE_CHECKING:
    from ..dataset_capture import DatasetCaptureManager
    from ..diagnostics import DiagnosticsBundleService
    from ..operator_events import OperatorEventTimeline
    from ..ros_agent import RosAgent
    from ..saved_maps import SavedMapCatalog
    from .lifecycle_coordinator import LifecycleCoordinator
    from .mapping_coordinator import MappingCoordinator
    from .mission_coordinator import MissionCoordinator
    from .navigation_coordinator import NavigationCoordinator


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
    lifecycle: LifecycleCoordinator | None = None
    operator_events: OperatorEventTimeline | None = None
    diagnostics: DiagnosticsBundleService | None = None

    pipeline_coordination_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    json_cache: Dict[str, tuple[int, bytes]] = field(default_factory=dict)
    pointcloud_binary_cache: tuple[int, bytes, bytes] | None = None
    pointcloud_binary_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    control_bindings: Dict[str, str] = field(default_factory=dict)
    robot_discovery: LocalRobotDiscovery = field(default_factory=LocalRobotDiscovery)

    def require_agent(self) -> RosAgent:
        if self.agent is None:
            raise RuntimeError("ROS agent is not configured")
        return self.agent
