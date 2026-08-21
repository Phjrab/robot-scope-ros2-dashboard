"""Explicit single-process runtime ownership for the FastAPI application."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict

from ..discovery import LocalRobotDiscovery

if TYPE_CHECKING:
    from ..control_bridge_lifecycle import ControlBridgeLifecycleManager
    from ..dataset_capture import DatasetCaptureManager
    from ..mapping_jobs import MappingJobManager
    from ..navigation_jobs import NavigationJobManager
    from ..ros_agent import RosAgent
    from ..saved_maps import SavedMapCatalog
    from ..service_lifecycle import ServiceLifecycleManager


def navigation_start_state() -> Dict[str, Any]:
    return {
        "seq": 0,
        "token": None,
        "phase": "idle",
        "pending": False,
        "cancel_requested": False,
        "mapping_job_id": None,
        "mapping_owned": False,
        "navigation_job_id": None,
        "terminal_cleanup": False,
        "error": None,
    }


@dataclass
class ApplicationRuntime:
    """Own every mutable manager, task, lock, and transport cache.

    Robot Scope deliberately remains a one-worker application.  Centralizing
    ownership here makes that constraint explicit without turning the runtime
    into a service locator for arbitrary plugins or changing manager behavior.
    """

    agent: RosAgent | None = None
    saved_maps: SavedMapCatalog | None = None
    mapping_jobs: MappingJobManager | None = None
    navigation_jobs: NavigationJobManager | None = None
    service_lifecycle: ServiceLifecycleManager | None = None
    control_bridge_lifecycle: ControlBridgeLifecycleManager | None = None
    dataset_capture: DatasetCaptureManager | None = None

    mapping_task: asyncio.Task[None] | None = None
    navigation_start_task: asyncio.Task[None] | None = None

    pipeline_coordination_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    navigation_start_state_lock: threading.RLock = field(default_factory=threading.RLock)
    navigation_start: Dict[str, Any] = field(default_factory=navigation_start_state)
    json_cache: Dict[str, tuple[int, bytes]] = field(default_factory=dict)
    pointcloud_binary_cache: tuple[int, bytes, bytes] | None = None
    pointcloud_binary_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    control_bindings: Dict[str, str] = field(default_factory=dict)
    robot_discovery: LocalRobotDiscovery = field(default_factory=LocalRobotDiscovery)

    def require_agent(self) -> RosAgent:
        if self.agent is None:
            raise RuntimeError("ROS agent is not configured")
        return self.agent
