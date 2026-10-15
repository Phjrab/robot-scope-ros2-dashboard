"""Single integration point for MS; no device is opened during configuration."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from .slam_camera import CameraOwnerCoordinator
from .slam_packages import MapPackageStore
from .slam_ros_runtime import IsaacStereoAdapter
from .slam_sessions import FastLioAdapter, SlamSessionManager, project_navigation_context


async def close_slam(runtime: Any, logger: Any) -> None:
    """Settle owned resources after control shutdown, preserving diagnostics."""
    if runtime.slam is not None:
        try:
            await runtime.slam.close()
        except Exception:
            logger.exception("SLAM session shutdown requires owner inspection")


def configure_slam(runtime: Any, project_dir: Path, runtime_root: Path) -> None:
    runtime_root = Path(runtime_root)
    handoff = os.environ.get("ROBOT_SCOPE_SLAM_CAMERA_HANDOFF", "")
    camera = CameraOwnerCoordinator(
        Path(os.environ.get("ROBOT_SCOPE_CAMERA_LOCK", str(runtime_root / "camera.lock"))),
        Path(handoff) if handoff else None)

    def blockers() -> list[str]:
        result: list[str] = []
        if runtime.navigation is None or runtime.navigation.is_active():
            result.append("navigation_active")
        if runtime.mission is None or runtime.mission.blocks_navigation_goal():
            result.append("mission_active")
        mr = getattr(runtime, "mission_routes", None)
        if mr is not None and hasattr(mr, "blocks_context_change") and mr.blocks_context_change():
            result.append("mission_route_active")
        if runtime.dataset_capture is None or runtime.dataset_capture.is_active():
            result.append("dataset_capture_active")
        if runtime.agent is None:
            result.append("control_state_unavailable")
        else:
            lease = runtime.agent.control_snapshot().get("lease")
            if not isinstance(lease, dict) or lease.get("active"):
                result.append("control_lease_active")
        if runtime.mapping is None or runtime.mapping.task_active():
            result.append("mapping_operation_active")
        if runtime.mapping is not None and runtime.mapping.pipeline_state() in {"starting", "running", "stopping"}:
            slam = getattr(runtime, "slam", None)
            if slam is None or slam.active_engine() != "lidar_fastlio":
                result.append("existing_lidar_pipeline_active")
        if runtime.lifecycle is None:
            result.append("lifecycle_unavailable")
        else:
            runtime.lifecycle.require_idle()
        return result

    def lidar_ready() -> bool:
        if runtime.agent is None:
            return False
        cloud = runtime.agent.pointcloud_binary_snapshot()
        # Existing source freshness is authoritative; receipt alone is insufficient.
        updated = cloud.get("updated")
        return bool(type(updated) in {int, float} and 0 <= time.monotonic() - updated <= 1.0
                    and cloud.get("topic") in {"/cloud_registered", "/Laser_map"}
                    and cloud.get("frame_id"))

    adapters = {"visual_stereo": IsaacStereoAdapter.from_environment(project_dir, runtime_root / "sessions")}
    camera = getattr(adapters["visual_stereo"], "camera_coordinator", camera)
    if runtime.mapping is not None:
        adapters["lidar_fastlio"] = FastLioAdapter(runtime.mapping, input_ready=lidar_ready)
    runtime.slam = SlamSessionManager(adapters, MapPackageStore(runtime_root / "packages"),
        coordination_lock=runtime.pipeline_coordination_lock, blockers=blockers,
        navigation_context=lambda: project_navigation_context(runtime), camera=camera,
        legacy_save=runtime.mapping.save if runtime.mapping else None)

    def legacy_blocked() -> bool:
        mission = runtime.mission
        mission_active = mission is None or mission.blocks_navigation_goal()
        mr = getattr(runtime, "mission_routes", None)
        if mr is not None and hasattr(mr, "blocks_context_change"):
            mission_active = mission_active or mr.blocks_context_change()
        return mission_active or (runtime.slam.blocks_context_change() and not runtime.slam.owns_current_operation())

    if runtime.mapping is not None:
        runtime.mapping.configure_external_guards(
            activity=lambda: ["slam_session_active"] if runtime.slam.blocks_context_change() else [],
            mutation_blocked=legacy_blocked)
