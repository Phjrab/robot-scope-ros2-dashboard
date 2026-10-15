"""Small application hook; no sensor, camera, service or ROS lifecycle start."""
from __future__ import annotations

from ..application.mission_coordinator import MissionConflict
from .context import NavigationContext
from .planner import NativePlanner
from .service import MissionRoutes


def configure_mission_routes(runtime, state_root, *, native_planner_window=False, policy_provider=None):
    if runtime.mission is None or runtime.navigation is None or runtime.saved_maps is None or runtime.spatial_routes is None:
        return
    slam = getattr(runtime, "slam", None)
    context = NavigationContext(runtime.navigation, slam=slam, policy_provider=policy_provider, runtime_provider=lambda: runtime.agent.navigation_runtime_snapshot() if getattr(runtime, "agent", None) else {})

    def guard(mission):
        if slam is not None:
            try:
                slam.require_context_idle()
            except Exception as exc:
                raise MissionConflict("SLAM_CONTEXT_BUSY") from exc
        revision = mission.get("context_revision")
        if revision:
            runtime.mission_routes.require_run_context(mission)

    # The legacy owner is reused, never replaced and never auto-started.
    runtime.mission._coordination_lock = runtime.pipeline_coordination_lock
    runtime.mission._context_guard = guard
    runtime.mission_routes = MissionRoutes(state_root, runtime.saved_maps, runtime.spatial_routes, runtime.mission, context, NativePlanner(enabled=native_planner_window))

    runtime.mission._run_observer = runtime.mission_routes.observe
