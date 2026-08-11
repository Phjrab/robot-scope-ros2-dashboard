"""FastAPI entrypoint for Robot Scope."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .control import (
    ClientFrameClock,
    CommandValidationError,
    ControlClosed,
    ControlDisabled,
    ControlError,
    ControlNotReady,
    EmergencyStopLatched,
    LeaseBindingError,
    LeaseBusy,
    LeaseInvalid,
    SequenceError,
)
from .discovery import (
    DiscoveryBusy,
    DiscoveryUnavailable,
    LocalRobotDiscovery,
    UnknownRobotType,
    public_robot_types,
)
from .mapping_jobs import (
    InvalidMapName,
    JobBusyError,
    MappingJobError,
    MappingJobManager,
    PipelineNotRunning,
    SaveCommandSpec,
    SaveResultError,
)
from .navigation_jobs import (
    NavigationBusy,
    NavigationConflict,
    NavigationJobError,
    NavigationJobManager,
    NavigationParameterError,
    NavigationPoseError,
    NavigationUnavailable,
)
from .http_security import is_same_origin
from .pointcloud_stream import PointCloudFrameError, encode_pointcloud_frame
from .ros_agent import RosAgent
from .service_lifecycle import (
    ServiceLifecycleBlocked,
    ServiceLifecycleBusy,
    ServiceLifecycleConfirmationRequired,
    ServiceLifecycleError,
    ServiceLifecycleManager,
    ServiceLifecycleUnavailable,
    collect_service_lifecycle_blockers,
)
from .saved_maps import (
    SavedMapCatalog,
    SavedMapConflict,
    SavedMapError,
    SavedMapFormatError,
    SavedMapInvalidName,
    SavedMapMutationError,
    SavedMapNotFound,
    SavedMapPointLimitError,
    SavedMapReadOnly,
)
from .websocket_stream import stream_until_disconnect


STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGGER = logging.getLogger(__name__)
AGENT: RosAgent | None = None
SAVED_MAPS: SavedMapCatalog | None = None
MAPPING_JOBS: MappingJobManager | None = None
NAVIGATION_JOBS: NavigationJobManager | None = None
SERVICE_LIFECYCLE: ServiceLifecycleManager | None = None
MAPPING_TASK: asyncio.Task[None] | None = None
PIPELINE_COORDINATION_LOCK = asyncio.Lock()
JSON_CACHE: Dict[str, tuple[int, bytes]] = {}
POINTCLOUD_BINARY_CACHE: tuple[int, bytes, bytes] | None = None
POINTCLOUD_BINARY_LOCK = asyncio.Lock()
CONTROL_BINDINGS: Dict[str, str] = {}
ROBOT_DISCOVERY = LocalRobotDiscovery()


class DashboardStaticFiles(StaticFiles):
    """Prevent stale frontend code after an operator service restart."""

    async def get_response(self, path: str, scope: Dict[str, Any]) -> Response:
        response = await super().get_response(path, scope)
        if path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "no-store"
        return response


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSelection(StrictRequest):
    camera: str | None = None
    pointcloud: str | None = None
    odometry: str | None = None
    occupancy_grid: str | None = None


class RobotTarget(StrictRequest):
    ip: str = Field(min_length=7, max_length=45)
    robot_type: str = Field(min_length=2, max_length=32)
    hostname: str | None = Field(default=None, max_length=253)


class RobotDiscoveryRequest(StrictRequest):
    robot_type: str = Field(min_length=2, max_length=32)


class MapSaveRequest(StrictRequest):
    name: str
    create_2d: bool = True


class CloudPointLimitRequest(StrictRequest):
    max_points: int | None


class SavedMapRenameRequest(StrictRequest):
    name: str


class SavedMapConvert2DRequest(StrictRequest):
    name: str
    z_min: float = Field(strict=True, ge=-20.0, le=20.0)
    z_max: float = Field(strict=True, ge=-20.0, le=20.0)
    resolution: float = Field(strict=True, ge=0.01, le=1.0)
    noise_radius: float = Field(default=0.1, strict=True, ge=0.01, le=2.0)
    min_neighbors: int = Field(default=10, strict=True, ge=1, le=1_000)
    background: Literal["unknown", "free"] = "unknown"


class SavedMapEditRun(StrictRequest):
    start: int = Field(strict=True, ge=0)
    length: int = Field(strict=True, ge=1)
    value: int = Field(strict=True)


class SavedMapEditedCopyRequest(StrictRequest):
    name: str
    source_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    runs: list[SavedMapEditRun] = Field(min_length=1, max_length=10_000)


class ControlArmRequest(StrictRequest):
    input_source: Literal["keyboard", "gamepad"]


class ControlLeaseRequest(StrictRequest):
    lease_id: str = Field(min_length=16, max_length=256)


class ControlStopRequest(StrictRequest):
    reason: str = Field(default="dashboard_button", min_length=1, max_length=128)


class ControlClearEstopRequest(StrictRequest):
    confirmed: bool


class NavigationParameterPatchRequest(StrictRequest):
    base_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    values: Dict[str, Any] = Field(min_length=1, max_length=27)


class NavigationStartRequest(StrictRequest):
    map_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    map_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    parameters_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class NavigationStopRequest(StrictRequest):
    pass


class NavigationPose(StrictRequest):
    x: float = Field(strict=True, ge=-1_000_000.0, le=1_000_000.0)
    y: float = Field(strict=True, ge=-1_000_000.0, le=1_000_000.0)
    yaw: float = Field(strict=True, ge=-3.141592653589793, le=3.141592653589793)


class NavigationPoseRequest(StrictRequest):
    map_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    map_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    pose: NavigationPose


class NavigationGoalRequest(NavigationPoseRequest):
    confirmed: bool = Field(strict=True)


class NavigationCancelRequest(StrictRequest):
    goal_id: str = Field(pattern=r"^[A-Za-z0-9_-]{16,128}$")


class NavigationClearCostmapsRequest(StrictRequest):
    scope: Literal["both"]


class ServiceLifecycleRequest(StrictRequest):
    confirmed: bool = Field(strict=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if AGENT is None:
        raise RuntimeError("ROS agent has not been configured")
    AGENT.start()
    if MAPPING_JOBS is not None:
        try:
            await asyncio.to_thread(MAPPING_JOBS.start_preview)
        except MappingJobError:
            # Raw XT16 preview is optional observability.  Keep the dashboard
            # available and expose WAITING/failed state when its fixed local
            # dependencies are unavailable.
            LOGGER.exception("XT16 point-cloud preview startup failed")
    try:
        yield
    finally:
        # A lifecycle request that has not reached its fixed systemctl command
        # must never fire during an unrelated application shutdown.
        if SERVICE_LIFECYCLE is not None:
            SERVICE_LIFECYCLE.close()
        # Close the navigation velocity gate and signed motion lease before
        # waiting on either process manager.
        if NAVIGATION_JOBS is not None:
            try:
                AGENT.navigation_deactivate(reason="server_shutdown")
            except Exception:
                LOGGER.exception("navigation shutdown stop failed")
            await asyncio.to_thread(NAVIGATION_JOBS.close)
        # Motion stop takes priority over potentially slow mapping cleanup.
        AGENT.shutdown_control()
        if MAPPING_JOBS is not None:
            await asyncio.to_thread(MAPPING_JOBS.close)
        if MAPPING_TASK is not None and not MAPPING_TASK.done():
            try:
                await asyncio.wait_for(asyncio.shield(MAPPING_TASK), timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        AGENT.stop()


app = FastAPI(
    title="Robot Scope",
    version="0.2.0",
    description="ROS 2 observability, allowlisted mapping, and fail-safe Go2 control",
    lifespan=lifespan,
)
app.mount("/static", DashboardStaticFiles(directory=STATIC_DIR), name="static")


def agent() -> RosAgent:
    if AGENT is None:
        raise HTTPException(status_code=503, detail="ROS agent is not configured")
    return AGENT


def saved_maps() -> SavedMapCatalog:
    if SAVED_MAPS is None:
        raise HTTPException(status_code=503, detail="saved map catalog is not configured")
    return SAVED_MAPS


def mapping_jobs() -> MappingJobManager:
    if MAPPING_JOBS is None:
        raise HTTPException(status_code=503, detail="mapping operations are not configured")
    return MAPPING_JOBS


def navigation_jobs() -> NavigationJobManager:
    if NAVIGATION_JOBS is None:
        raise HTTPException(status_code=503, detail="navigation is not configured")
    return NAVIGATION_JOBS


def service_lifecycle() -> ServiceLifecycleManager:
    if SERVICE_LIFECYCLE is None:
        raise HTTPException(
            status_code=503,
            detail="service lifecycle control is not configured",
        )
    return SERVICE_LIFECYCLE


def require_same_origin(request: Request) -> None:
    """Reject browser control mutations that did not originate at this host."""

    if not is_same_origin(
        request.headers.get("origin", ""),
        request.headers.get("host", ""),
    ):
        raise HTTPException(status_code=403, detail="mutation requests must be same-origin")


def websocket_same_origin(websocket: WebSocket) -> bool:
    return is_same_origin(
        websocket.headers.get("origin", ""),
        websocket.headers.get("host", ""),
    )


def control_error(exc: ControlError) -> HTTPException:
    if isinstance(exc, (LeaseBusy, LeaseBindingError, SequenceError, LeaseInvalid)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, CommandValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, EmergencyStopLatched):
        return HTTPException(status_code=423, detail=str(exc))
    if isinstance(exc, ControlDisabled):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, (ControlNotReady, ControlClosed)):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail="control operation failed")


def navigation_error(exc: NavigationJobError) -> HTTPException:
    if isinstance(exc, NavigationUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, (NavigationBusy, NavigationConflict)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (NavigationParameterError, NavigationPoseError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="navigation operation failed")


def navigation_agent_error(exc: ControlError) -> HTTPException:
    if isinstance(exc, (LeaseBusy, LeaseBindingError, LeaseInvalid, SequenceError)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, CommandValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, EmergencyStopLatched):
        return HTTPException(status_code=423, detail=str(exc))
    if isinstance(exc, (ControlDisabled, ControlNotReady, ControlClosed)):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail="navigation ROS operation failed")


def mapping_activity() -> tuple[bool, list[str]]:
    """Return operations/transitions that conflict with navigation.

    A running Hesai + FAST-LIO pipeline is shared sensor/localization
    infrastructure for Nav2, not a conflict.  Only a map mutation/save or a
    process transition is mutually exclusive with navigation startup.
    """

    blockers: list[str] = []
    task = MAPPING_TASK
    if task is not None and not task.done():
        blockers.append("mapping_operation_active")
    if MAPPING_JOBS is not None:
        snapshot = MAPPING_JOBS.snapshot()
        pipeline_state = str((snapshot.get("pipeline") or {}).get("state", "idle"))
        operation_state = str((snapshot.get("operation") or {}).get("state", "idle"))
        if pipeline_state in {"starting", "stopping"}:
            blockers.append("mapping_transition")
        if operation_state in {"saving", "stopping"}:
            blockers.append("mapping_operation_active")
    return bool(blockers), list(dict.fromkeys(blockers))


def mapping_pipeline_state() -> str:
    if MAPPING_JOBS is None:
        return "unavailable"
    snapshot = MAPPING_JOBS.snapshot()
    state = str((snapshot.get("pipeline") or {}).get("state", "failed"))
    return state if state in {"idle", "starting", "running", "stopping", "failed"} else "failed"


def service_lifecycle_blockers() -> list[str]:
    """Fail closed while robot work could be interrupted by this service."""

    control: Dict[str, Any] | None = None
    navigation_runtime: Dict[str, Any] | None = None
    navigation_snapshot: Dict[str, Any] | None = None
    mapping_snapshot: Dict[str, Any] | None = None
    current_agent = AGENT
    if current_agent is not None:
        try:
            control = current_agent.control_snapshot()
        except Exception:
            control = None

        try:
            navigation_runtime = current_agent.navigation_runtime_snapshot()
        except Exception:
            navigation_runtime = None

    if NAVIGATION_JOBS is not None:
        try:
            navigation_snapshot = NAVIGATION_JOBS.snapshot()
        except Exception:
            navigation_snapshot = None

    if MAPPING_JOBS is not None:
        try:
            mapping_snapshot = MAPPING_JOBS.snapshot()
        except Exception:
            mapping_snapshot = None

    task = MAPPING_TASK
    try:
        mapping_task_active = bool(task is not None and not task.done())
    except Exception:
        mapping_task_active = True
    return collect_service_lifecycle_blockers(
        control=control,
        navigation_runtime=navigation_runtime,
        navigation_jobs=navigation_snapshot,
        mapping_jobs=mapping_snapshot,
        mapping_task_active=mapping_task_active,
    )


def service_lifecycle_error(exc: ServiceLifecycleError) -> HTTPException:
    if isinstance(exc, ServiceLifecycleBlocked):
        return HTTPException(
            status_code=409,
            detail={
                "code": "service_lifecycle_blocked",
                "blockers": list(exc.blockers),
            },
        )
    if isinstance(exc, ServiceLifecycleBusy):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ServiceLifecycleConfirmationRequired):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ServiceLifecycleUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail="service lifecycle operation failed")


def require_service_lifecycle_idle() -> None:
    """Prevent new robot work during the response grace before service stop."""

    manager = SERVICE_LIFECYCLE
    if manager is not None and manager.is_busy():
        raise HTTPException(
            status_code=409,
            detail="a dashboard service lifecycle operation is pending",
        )


def navigation_active() -> bool:
    manager_active = bool(
        NAVIGATION_JOBS is not None and NAVIGATION_JOBS.is_active()
    )
    if manager_active or AGENT is None:
        return manager_active
    try:
        # The ROS lease can remain active for a very short interval while an
        # unexpected process-exit callback runs.  Include it in the mutation
        # interlock so a pinned map cannot be changed during that handoff.
        return bool(AGENT.navigation_runtime_snapshot().get("active", False))
    except Exception:
        snapshot = NAVIGATION_JOBS.snapshot() if NAVIGATION_JOBS is not None else {}
        pipeline = snapshot.get("pipeline") if isinstance(snapshot.get("pipeline"), dict) else {}
        return bool(pipeline.get("state") == "failed" and pipeline.get("job_id"))


def require_navigation_idle(detail: str) -> None:
    if navigation_active():
        raise HTTPException(status_code=409, detail=detail)


def require_navigation_runtime_capability(capability: str) -> None:
    runtime = agent().navigation_runtime_snapshot()
    safety = runtime.get("safety") if isinstance(runtime.get("safety"), dict) else {}
    if safety.get(capability) is not True:
        raise NavigationUnavailable(
            f"navigation runtime safety gate {capability} is not ready"
        )


def navigation_view() -> Dict[str, Any]:
    """Merge process ownership with ROS readiness into the stable UI contract."""

    manager = navigation_jobs().snapshot()
    try:
        runtime = agent().navigation_runtime_snapshot()
    except Exception:
        LOGGER.exception("navigation runtime snapshot failed")
        runtime = {}

    manager_pipeline = manager.get("pipeline") if isinstance(manager.get("pipeline"), dict) else {}
    pipeline_state = str(manager_pipeline.get("state", "failed"))
    if pipeline_state not in {"idle", "starting", "running", "stopping", "failed"}:
        pipeline_state = "failed"
    pipeline = {
        "state": pipeline_state,
        "job_id": manager_pipeline.get("job_id"),
        "error": manager_pipeline.get("error"),
        "started_at": manager_pipeline.get("started_at"),
    }

    runtime_readiness = runtime.get("readiness") if isinstance(runtime.get("readiness"), dict) else {}
    readiness = {
        key: bool(runtime_readiness.get(key, False))
        for key in (
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
        )
    }
    manager_available = bool(manager.get("available", False))
    runtime_available = bool(runtime.get("available", False))
    available = manager_available and runtime_available
    robot_online = bool(runtime.get("robot_online", False))
    mapping_busy, mapping_blockers = mapping_activity()
    shared_mapping_state = mapping_pipeline_state()

    runtime_safety = runtime.get("safety") if isinstance(runtime.get("safety"), dict) else {}
    blockers = [
        str(item)
        for item in runtime_safety.get("blockers", [])
        if isinstance(item, str) and item
    ]
    blockers.extend(mapping_blockers)
    if not manager_available or not runtime_available:
        blockers.append("navigation_unavailable")
    if not robot_online:
        blockers.append("robot_offline")
    if pipeline_state in {"starting", "stopping"}:
        blockers.append("navigation_transition")
    if pipeline_state == "running" and shared_mapping_state != "running":
        blockers.append("localization_pipeline_not_running")
    blockers = list(dict.fromkeys(blockers))

    manager_map = manager.get("map") if isinstance(manager.get("map"), dict) else None
    localization = runtime.get("localization") if isinstance(runtime.get("localization"), dict) else {}
    localization_state = str(localization.get("state", "uninitialized"))
    if localization_state not in {"uninitialized", "localizing", "localized", "lost"}:
        localization_state = "lost"
    localization_view = {
        "state": localization_state,
        "pose": localization.get("pose") if isinstance(localization.get("pose"), dict) else None,
    }
    goal = runtime.get("goal") if isinstance(runtime.get("goal"), dict) else {}
    goal_state = str(goal.get("state", "idle"))
    if goal_state not in {
        "idle", "pending", "active", "canceling", "succeeded", "failed", "canceled"
    }:
        goal_state = "failed"
    goal_view = {
        "state": goal_state,
        "goal_id": goal.get("goal_id"),
        "pose": goal.get("pose") if isinstance(goal.get("pose"), dict) else None,
        "distance_remaining": goal.get("distance_remaining"),
        "navigation_time": goal.get("navigation_time"),
        "recoveries": int(goal.get("recoveries", 0) or 0),
        "error": goal.get("error"),
    }
    running = pipeline_state == "running" and manager_map is not None
    safety = {
        "can_start": bool(
            available
            and robot_online
            and not mapping_busy
            and pipeline_state in {"idle", "failed"}
            and runtime_safety.get("can_start", False)
        ),
        "can_set_initial_pose": bool(
            running
            and shared_mapping_state == "running"
            and runtime_safety.get("can_set_initial_pose", False)
        ),
        "can_send_goal": bool(
            running
            and shared_mapping_state == "running"
            and runtime_safety.get("can_send_goal", False)
        ),
        "blockers": blockers,
    }
    result: Dict[str, Any] = {
        "seq": max(int(manager.get("seq", 0) or 0), int(runtime.get("seq", 0) or 0)),
        "available": available,
        "robot_online": robot_online,
        "pipeline": pipeline,
        "readiness": readiness,
        "map": manager_map,
        "localization": localization_view,
        "goal": goal_view,
        "safety": safety,
        "command_topic": str(manager.get("command_topic", "/robot_scope/nav/cmd_vel_raw")),
        "bindings": {
            "scan": "/scan",
            "odometry": "/utlidar/robot_odom",
            "localization_odometry": "/Odometry",
            "command": "/robot_scope/nav/cmd_vel_raw",
        },
        "localization_pipeline": {"state": shared_mapping_state, "shared": True},
    }
    path = runtime.get("path")
    if isinstance(path, list):
        result["path"] = path
    return result


def control_view(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Translate the internal safety snapshot to the stable browser contract."""

    limits = snapshot.get("limits", {})
    readiness = snapshot.get("readiness", {})
    bridge = dict(snapshot.get("bridge", {}))
    estop = snapshot.get("estop", {})
    lease = dict(snapshot.get("lease", {}))
    action_guard = dict(snapshot.get("action_guard", {}))
    enabled = bool(snapshot.get("enabled", False))
    configured = bool(snapshot.get("configured", False)) and bool(
        snapshot.get("transport_configured", True)
    )
    available = bool(snapshot.get("ready", snapshot.get("available", False)))
    target_supported = bool(snapshot.get("target_supported", True))
    target_matches_startup = bool(snapshot.get("target_matches_startup", True))
    restart_required = bool(
        snapshot.get("control_restart_required", snapshot.get("restart_required", False))
    )
    target_reason = str(snapshot.get("control_target_reason", ""))
    estop_latched = bool(estop.get("latched", snapshot.get("estop_latched", False)))
    if not target_supported:
        state = (
            "로봇 유형 또는 IP가 실행 중 변경되었습니다. 선택한 Go2 설정으로 "
            "대시보드를 재시작해야 제어할 수 있습니다."
            if restart_required
            else "현재 시작 프로필과 IP는 Go2 제어 브리지에 연결되어 있지 않습니다."
        )
    elif not enabled:
        state = "서버 시작 설정에서 제어가 비활성화되어 있습니다."
    elif not configured:
        state = "제어 브리지 키 또는 ROS 전송이 설정되지 않았습니다."
    elif estop_latched:
        state = "대시보드 SOFTWARE STOP이 잠겨 있습니다."
    elif action_guard.get("active"):
        state = (
            f"{action_guard.get('action') or 'Go2 동작'} 안전 대기 중 "
            f"({float(action_guard.get('remaining_s', 0.0)):.1f}s)"
        )
    elif not available:
        state = "Go2 LowState와 제어 브리지를 기다리는 중입니다."
    else:
        state = "제어 서버 준비 완료"
    lease["source"] = lease.get("input_source")
    bridge.setdefault("connected", bool(readiness.get("bridge_fresh", False)))
    bridge.setdefault("available", bool(bridge.get("ready", False)))
    bridge.setdefault("state", "ready" if bridge.get("available") else "waiting")
    return {
        "enabled": enabled,
        "configured": configured,
        "available": available,
        "state": state,
        "target_supported": target_supported,
        "target_matches_startup": target_matches_startup,
        "restart_required": restart_required,
        "control_restart_required": restart_required,
        "control_target_reason": target_reason,
        "estop_latched": estop_latched,
        "estop_reason": estop.get("reason"),
        "lease": lease,
        "bridge": bridge,
        "action_guard": action_guard,
        "limits": {
            "max_linear_x": float(limits.get("vx_mps", limits.get("max_linear_x", 0.0))),
            "max_linear_y": float(limits.get("vy_mps", limits.get("max_linear_y", 0.0))),
            "max_angular_z": float(limits.get("wz_rps", limits.get("max_angular_z", 0.0))),
            "default_speed_scale": float(limits.get("default_speed_scale", 0.35)),
            "command_timeout_s": float(limits.get("command_timeout_s", 0.20)),
            "bind_timeout_s": float(limits.get("bind_timeout_s", 4.0)),
        },
        "command": snapshot.get(
            "command",
            {
                "source": lease.get("source") or "keyboard",
                "deadman": False,
                "linear_x": 0.0,
                "linear_y": 0.0,
                "angular_z": 0.0,
            },
        ),
        "actions": snapshot.get("actions", []),
    }


def mapping_error(exc: MappingJobError) -> HTTPException:
    if isinstance(exc, InvalidMapName):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (JobBusyError, PipelineNotRunning)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, SaveResultError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def saved_map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SavedMapNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, SavedMapInvalidName):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, SavedMapReadOnly):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, SavedMapConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, SavedMapFormatError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, SavedMapPointLimitError):
        return HTTPException(status_code=413, detail=str(exc))
    if isinstance(exc, SavedMapMutationError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail="saved map operation failed")


def parse_saved_point_limit(value: str) -> int | None:
    normalized = value.strip().lower()
    if normalized == "all":
        return None
    try:
        limit = int(normalized)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="max_points must be 'all' or an integer from 1,000 to 1,000,000",
        ) from exc
    if limit < 1_000 or limit > 1_000_000:
        raise HTTPException(
            status_code=422,
            detail="max_points must be 'all' or an integer from 1,000 to 1,000,000",
        )
    return limit


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/v1/system/service")
async def service_lifecycle_status() -> Dict[str, Any]:
    return await asyncio.to_thread(service_lifecycle().snapshot)


@app.post("/api/v1/system/service/restart", status_code=202)
async def service_lifecycle_restart(
    request: Request,
    body: ServiceLifecycleRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    async with PIPELINE_COORDINATION_LOCK:
        try:
            return await asyncio.to_thread(
                service_lifecycle().schedule_restart,
                confirmed=body.confirmed,
            )
        except ServiceLifecycleError as exc:
            raise service_lifecycle_error(exc) from exc


@app.post("/api/v1/system/service/stop", status_code=202)
async def service_lifecycle_stop(
    request: Request,
    body: ServiceLifecycleRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    async with PIPELINE_COORDINATION_LOCK:
        try:
            return await asyncio.to_thread(
                service_lifecycle().schedule_stop,
                confirmed=body.confirmed,
            )
        except ServiceLifecycleError as exc:
            raise service_lifecycle_error(exc) from exc


@app.get("/api/v1/health")
async def health() -> Dict[str, Any]:
    return await asyncio.to_thread(agent().health_snapshot)


@app.get("/api/v1/state")
async def state() -> Dict[str, Any]:
    return await asyncio.to_thread(agent().state_snapshot)


@app.get("/api/v1/topics")
async def topics() -> Dict[str, Any]:
    return {"topics": await asyncio.to_thread(agent().topics_snapshot)}


@app.get("/api/v1/sources")
async def sources() -> Dict[str, Any]:
    return await asyncio.to_thread(agent().sources_snapshot)


@app.post("/api/v1/sources")
async def select_sources(selection: SourceSelection, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    values = selection.model_dump(exclude_none=True)
    try:
        return await asyncio.to_thread(agent().set_sources, values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/robots/types")
async def robot_types() -> Dict[str, Any]:
    selected_type = AGENT.robot_target_snapshot()["robot_type"] if AGENT is not None else ""
    return {"types": public_robot_types(), "selected_type": selected_type}


@app.post("/api/v1/robots/discover")
async def discover_robots(request: Request, body: RobotDiscoveryRequest) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        return await asyncio.to_thread(ROBOT_DISCOVERY.discover, body.robot_type)
    except UnknownRobotType as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DiscoveryBusy as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except DiscoveryUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/v1/robot")
async def set_robot(request: Request, target: RobotTarget) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        await asyncio.to_thread(
            ROBOT_DISCOVERY.validate_target,
            target.robot_type,
            target.ip,
        )
        selected = await asyncio.to_thread(
            agent().set_robot_target,
            target.ip,
            target.robot_type,
            target.hostname,
        )
        if selected.get("changed"):
            CONTROL_BINDINGS.clear()
        return {
            "robot": selected,
            "robot_ip": selected["ip"],
            "robot_type": selected["robot_type"],
            "hostname": selected["hostname"],
            "model": selected["model"],
        }
    except (UnknownRobotType, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DiscoveryUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.delete("/api/v1/robot")
async def disconnect_robot(request: Request) -> Dict[str, Any]:
    """Forget the selected target and revoke its motion authorization."""

    require_same_origin(request)
    selected = await asyncio.to_thread(agent().disconnect_robot_target)
    CONTROL_BINDINGS.clear()
    return {
        "robot": selected,
        "robot_ip": "",
        "robot_type": selected["robot_type"],
        "hostname": "",
        "model": selected["model"],
    }


def encode_json(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")


async def cached_json_response(key: str, payload: Dict[str, Any]) -> Response:
    seq = int(payload.get("seq", 0))
    cached = JSON_CACHE.get(key)
    if cached is None or cached[0] != seq:
        cached = (seq, await asyncio.to_thread(encode_json, payload))
        JSON_CACHE[key] = cached
    return Response(content=cached[1], media_type="application/json", headers={"Cache-Control": "no-store"})


async def cached_pointcloud_binary_frame(snapshot: Dict[str, Any]) -> bytes:
    global POINTCLOUD_BINARY_CACHE
    seq = int(snapshot.get("seq", 0))
    point_bytes = snapshot.get("points_bytes", b"")
    cached = POINTCLOUD_BINARY_CACHE
    if cached is not None and cached[0] == seq and cached[1] is point_bytes:
        return cached[2]
    async with POINTCLOUD_BINARY_LOCK:
        cached = POINTCLOUD_BINARY_CACHE
        if cached is not None and cached[0] == seq and cached[1] is point_bytes:
            return cached[2]
        metadata = {key: value for key, value in snapshot.items() if key != "points_bytes"}
        frame = await asyncio.to_thread(encode_pointcloud_frame, metadata, point_bytes)
        POINTCLOUD_BINARY_CACHE = (seq, point_bytes, frame)
        return frame


@app.get("/api/v1/pointcloud")
async def pointcloud(since: int = -1) -> Response:
    metadata = await asyncio.to_thread(agent().pointcloud_binary_snapshot)
    if int(metadata.get("seq", 0)) == since:
        return Response(status_code=204)
    snapshot = await asyncio.to_thread(agent().pointcloud_snapshot)
    return await cached_json_response("pointcloud", snapshot)


@app.get("/api/v1/pointcloud.bin")
async def pointcloud_binary(since: int = -1) -> Response:
    snapshot = await asyncio.to_thread(agent().pointcloud_binary_snapshot)
    if int(snapshot.get("seq", 0)) == since:
        return Response(status_code=204)
    frame = await cached_pointcloud_binary_frame(snapshot)
    return Response(
        content=frame,
        media_type="application/vnd.robot-scope.pointcloud",
        headers={"Cache-Control": "no-store", "X-Robot-Scope-Stream": "pointcloud-v1"},
    )


@app.get("/api/v1/pointcloud/settings")
async def pointcloud_settings() -> Dict[str, Any]:
    return await asyncio.to_thread(agent().cloud_point_settings)


@app.post("/api/v1/pointcloud/settings")
async def set_pointcloud_settings(
    body: CloudPointLimitRequest,
    request: Request,
) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        settings = await asyncio.to_thread(agent().set_cloud_max_points, body.max_points)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    JSON_CACHE.pop("pointcloud", None)
    return settings


@app.get("/api/v1/map")
async def occupancy_map(since: int = -1) -> Response:
    snapshot = await asyncio.to_thread(agent().map_snapshot)
    if int(snapshot.get("seq", 0)) == since:
        return Response(status_code=204)
    return await cached_json_response("map", snapshot)


@app.get("/api/v1/joints")
async def robot_joints() -> Dict[str, Any]:
    return await asyncio.to_thread(agent().joint_snapshot)


@app.get("/api/v1/pose")
async def robot_pose() -> Dict[str, Any]:
    return await asyncio.to_thread(agent().pose_snapshot)


@app.get("/api/v1/control")
async def control_status() -> Dict[str, Any]:
    return {"control": control_view(agent().control_snapshot())}


@app.post("/api/v1/control/arm")
async def control_arm(request: Request, body: ControlArmRequest) -> Dict[str, Any]:
    require_same_origin(request)
    async with PIPELINE_COORDINATION_LOCK:
        require_service_lifecycle_idle()
        try:
            result = agent().control_acquire(body.input_source)
        except ControlError as exc:
            raise control_error(exc) from exc
    return {
        "lease_id": result["token"],
        "control": control_view(agent().control_snapshot()),
    }


@app.post("/api/v1/control/disarm")
async def control_disarm(request: Request, body: ControlLeaseRequest) -> Dict[str, Any]:
    require_same_origin(request)
    binding = CONTROL_BINDINGS.pop(body.lease_id, None)
    try:
        agent().control_release(body.lease_id, binding)
    except LeaseInvalid:
        # WebSocket release and page-unload HTTP fallback deliberately race;
        # either one having already stopped the lease is a successful disarm.
        pass
    except ControlError as exc:
        raise control_error(exc) from exc
    return {"control": control_view(agent().control_snapshot())}


@app.post("/api/v1/control/stop")
async def control_stop(request: Request, body: ControlStopRequest) -> Dict[str, Any]:
    require_same_origin(request)
    CONTROL_BINDINGS.clear()
    try:
        agent().control_estop(body.reason)
    except ControlError as exc:
        raise control_error(exc) from exc
    return {"control": control_view(agent().control_snapshot())}


@app.post("/api/v1/control/estop/clear")
async def control_clear_estop(
    request: Request,
    body: ControlClearEstopRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        agent().control_clear_estop(confirm=body.confirmed)
    except ControlError as exc:
        raise control_error(exc) from exc
    return {"control": control_view(agent().control_snapshot())}


def validate_control_message(
    payload: object,
    *,
    message_type: str,
    allowed_keys: set[str],
) -> Dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("type") != message_type:
        raise CommandValidationError(f"expected {message_type} control message")
    if set(payload) - allowed_keys:
        raise CommandValidationError("unexpected control message fields")
    return payload


@app.websocket("/api/v1/ws/control")
async def control_stream(websocket: WebSocket) -> None:
    if not websocket_same_origin(websocket):
        await websocket.close(code=4403, reason="same-origin control WebSocket required")
        return
    await websocket.accept()
    lease_id = ""
    binding = f"ws-{secrets.token_urlsafe(24)}"
    released = False
    client_clock: ClientFrameClock | None = None
    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=3.0)
        bind = validate_control_message(
            first,
            message_type="bind",
            allowed_keys={"type", "lease_id", "client_time_ms"},
        )
        client_clock = ClientFrameClock(
            bind.get("client_time_ms"),
            time.time_ns() / 1_000_000.0,
        )
        lease_id = str(bind.get("lease_id", ""))
        agent().control_bind(lease_id, binding)
        CONTROL_BINDINGS[lease_id] = binding
        await websocket.send_json(
            {
                "type": "bound",
                "max_frame_age_ms": round(ClientFrameClock.MAX_AGE_MS),
                "control": control_view(agent().control_snapshot()),
            }
        )

        while True:
            payload = await asyncio.wait_for(websocket.receive_json(), timeout=2.25)
            if not isinstance(payload, dict):
                raise CommandValidationError("control message must be a JSON object")
            if str(payload.get("lease_id", "")) != lease_id:
                raise LeaseInvalid("control lease does not match this WebSocket")
            kind = payload.get("type")
            if kind == "twist":
                message = validate_control_message(
                    payload,
                    message_type="twist",
                    allowed_keys={
                        "type", "lease_id", "seq", "source", "deadman",
                        "linear_x", "linear_y", "angular_z", "speed_scale",
                        "client_time_ms",
                    },
                )
                frame_age_ms = client_clock.validate(
                    message.get("client_time_ms"),
                    time.time_ns() / 1_000_000.0,
                )
                agent().control_drive(
                    lease_id,
                    binding,
                    message.get("seq"),
                    vx=message.get("linear_x"),
                    vy=message.get("linear_y"),
                    wz=message.get("angular_z"),
                    speed_scale=message.get("speed_scale", 1.0),
                    deadman=message.get("deadman"),
                    client_age_s=max(0.0, frame_age_ms / 1_000.0),
                )
            elif kind == "heartbeat":
                message = validate_control_message(
                    payload,
                    message_type="heartbeat",
                    allowed_keys={"type", "lease_id", "seq", "client_time_ms"},
                )
                client_clock.validate(
                    message.get("client_time_ms"),
                    time.time_ns() / 1_000_000.0,
                )
                agent().control_heartbeat(
                    lease_id,
                    binding,
                    message.get("seq"),
                )
            elif kind == "action":
                message = validate_control_message(
                    payload,
                    message_type="action",
                    allowed_keys={
                        "type", "lease_id", "seq", "action_id", "confirmed",
                        "client_time_ms",
                    },
                )
                client_clock.validate(
                    message.get("client_time_ms"),
                    time.time_ns() / 1_000_000.0,
                )
                action_id = message.get("action_id")
                result = agent().control_action(
                    lease_id,
                    binding,
                    message.get("seq"),
                    action_id,
                    confirm=message.get("confirmed") is True,
                )
                await websocket.send_json(
                    {
                        "type": "action_accepted",
                        "action_id": action_id,
                        "lease_released": bool(result.get("lease_released")),
                        "detail": "대시보드가 동작 명령을 접수했습니다. 브리지 수신이나 로봇 실행 완료 신호가 아닙니다.",
                        "control": control_view(agent().control_snapshot()),
                    }
                )
                # One-shot actions consume the lease so guessed completion
                # timers can never resume teleoperation over an active motion.
                released = True
                CONTROL_BINDINGS.pop(lease_id, None)
                await websocket.close(code=1000)
                return
            elif kind == "release":
                validate_control_message(
                    payload,
                    message_type="release",
                    allowed_keys={"type", "lease_id", "reason", "client_time_ms"},
                )
                agent().control_release(lease_id, binding)
                released = True
                CONTROL_BINDINGS.pop(lease_id, None)
                await websocket.send_json(
                    {"type": "released", "control": control_view(agent().control_snapshot())}
                )
                await websocket.close(code=1000)
                return
            else:
                raise CommandValidationError("unknown control message type")
    except WebSocketDisconnect:
        pass
    except asyncio.TimeoutError:
        try:
            await websocket.send_json(
                {"type": "error", "detail": "control stream heartbeat timed out"}
            )
        except (RuntimeError, WebSocketDisconnect):
            pass
    except ControlError as exc:
        try:
            await websocket.send_json({"type": "error", "detail": str(exc)})
        except (RuntimeError, WebSocketDisconnect):
            pass
    except (TypeError, ValueError) as exc:
        try:
            await websocket.send_json({"type": "error", "detail": f"invalid control message: {exc}"})
        except (RuntimeError, WebSocketDisconnect):
            pass
    finally:
        if lease_id:
            CONTROL_BINDINGS.pop(lease_id, None)
            if not released:
                try:
                    agent().control_release(lease_id, binding)
                except ControlError:
                    pass
        try:
            await websocket.close(code=1000)
        except (RuntimeError, WebSocketDisconnect):
            pass


@app.get("/api/v1/navigation")
async def navigation_status() -> Dict[str, Any]:
    return await asyncio.to_thread(navigation_view)


@app.get("/api/v1/navigation/parameters")
async def navigation_parameters() -> Dict[str, Any]:
    return await asyncio.to_thread(navigation_jobs().parameters_snapshot)


@app.patch("/api/v1/navigation/parameters")
async def update_navigation_parameters(
    request: Request,
    body: NavigationParameterPatchRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    async with PIPELINE_COORDINATION_LOCK:
        try:
            return await asyncio.to_thread(
                navigation_jobs().update_parameters,
                body.base_revision,
                body.values,
            )
        except NavigationJobError as exc:
            raise navigation_error(exc) from exc


@app.post("/api/v1/navigation/start")
async def navigation_start(
    request: Request,
    body: NavigationStartRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    manager = navigation_jobs()
    async with PIPELINE_COORDINATION_LOCK:
        require_service_lifecycle_idle()
        mapping_busy, _ = mapping_activity()
        if mapping_busy:
            raise HTTPException(
                status_code=409,
                detail="a mapping save, conversion, or pipeline transition is active",
            )
        preflight = await asyncio.to_thread(manager.snapshot)
        pipeline_state = str((preflight.get("pipeline") or {}).get("state", "failed"))
        if pipeline_state in {"starting", "running", "stopping"}:
            raise HTTPException(status_code=409, detail="navigation is already active")
        if not preflight.get("available"):
            raise HTTPException(
                status_code=503,
                detail="navigation prerequisites are unavailable",
            )
        if body.parameters_revision != preflight.get("parameters_revision"):
            raise HTTPException(
                status_code=409,
                detail="navigation parameters changed; reload before starting",
            )
        try:
            source = await asyncio.to_thread(
                saved_maps().resolve_navigation_map,
                body.map_id,
                body.map_revision,
            )
        except SavedMapError as exc:
            raise saved_map_error(exc) from exc

        shared_pipeline_state = mapping_pipeline_state()
        if shared_pipeline_state in {"idle", "failed"}:
            try:
                shared_start = await asyncio.to_thread(mapping_jobs().start_mapping)
            except MappingJobError as exc:
                raise mapping_error(exc) from exc
            shared_pipeline_state = str(
                (shared_start.get("pipeline") or {}).get("state", "failed")
            )
            if shared_pipeline_state != "running":
                # The fail-closed mapping launcher remains in ``starting``
                # while it verifies fresh raw, bridge and FAST-LIO output.
                # Never activate Nav2 against process existence alone; the
                # client can retry once the mapping status becomes running.
                raise HTTPException(
                    status_code=409,
                    detail="localization pipeline is still verifying sensor readiness",
                )
        elif shared_pipeline_state != "running":
            raise HTTPException(
                status_code=409,
                detail="localization pipeline is changing state",
            )

        activated = False
        try:
            await asyncio.to_thread(
                agent().navigation_activate,
                map_id=source.map_id,
                map_revision=source.revision,
                map_name=source.name,
            )
            activated = True
            await asyncio.to_thread(
                manager.start,
                map_id=source.map_id,
                map_revision=source.revision,
                parameters_revision=body.parameters_revision,
            )
        except NavigationJobError as exc:
            if activated:
                await asyncio.to_thread(
                    agent().navigation_deactivate,
                    reason="navigation_start_failed",
                )
            raise navigation_error(exc) from exc
        except ControlError as exc:
            if activated:
                await asyncio.to_thread(
                    agent().navigation_deactivate,
                    reason="navigation_start_failed",
                )
            raise navigation_agent_error(exc) from exc
        except Exception:
            if activated:
                try:
                    await asyncio.to_thread(
                        agent().navigation_deactivate,
                        reason="navigation_start_failed",
                    )
                except Exception:
                    LOGGER.exception("navigation activation rollback failed")
            raise
    return {"accepted": True, "navigation": await asyncio.to_thread(navigation_view)}


@app.post("/api/v1/navigation/stop")
async def navigation_stop(
    request: Request,
    body: NavigationStopRequest,
) -> Dict[str, Any]:
    del body
    require_same_origin(request)
    async with PIPELINE_COORDINATION_LOCK:
        try:
            await asyncio.to_thread(
                agent().navigation_deactivate,
                reason="navigation_stop",
            )
        except Exception:
            # Process cleanup remains available even if the robot transport is
            # already offline.  The signed bridge also has its own watchdog.
            LOGGER.exception("navigation stop could not reach the ROS agent")
        try:
            await asyncio.to_thread(navigation_jobs().stop)
        except NavigationJobError as exc:
            raise navigation_error(exc) from exc
    return {"navigation": await asyncio.to_thread(navigation_view)}


@app.post("/api/v1/navigation/initial-pose")
async def navigation_initial_pose(
    request: Request,
    body: NavigationPoseRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    async with PIPELINE_COORDINATION_LOCK:
        require_service_lifecycle_idle()
        mapping_busy, _ = mapping_activity()
        if mapping_busy:
            raise HTTPException(status_code=409, detail="mapping is active")
        if mapping_pipeline_state() != "running":
            raise HTTPException(
                status_code=409,
                detail="shared Hesai + FAST-LIO localization pipeline is not running",
            )
        try:
            await asyncio.to_thread(
                require_navigation_runtime_capability,
                "can_set_initial_pose",
            )
            pose = await asyncio.to_thread(
                navigation_jobs().validate_active_pose,
                map_id=body.map_id,
                map_revision=body.map_revision,
                **body.pose.model_dump(),
            )
            await asyncio.to_thread(
                agent().navigation_set_initial_pose,
                map_id=body.map_id,
                map_revision=body.map_revision,
                **pose,
            )
        except NavigationJobError as exc:
            raise navigation_error(exc) from exc
        except ControlError as exc:
            raise navigation_agent_error(exc) from exc
    return {"accepted": True, "navigation": await asyncio.to_thread(navigation_view)}


@app.post("/api/v1/navigation/goal")
async def navigation_goal(
    request: Request,
    body: NavigationGoalRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    if body.confirmed is not True:
        raise HTTPException(
            status_code=422,
            detail="confirmed=true is required before sending a navigation goal",
        )
    async with PIPELINE_COORDINATION_LOCK:
        require_service_lifecycle_idle()
        mapping_busy, _ = mapping_activity()
        if mapping_busy:
            raise HTTPException(status_code=409, detail="mapping is active")
        if mapping_pipeline_state() != "running":
            raise HTTPException(
                status_code=409,
                detail="shared Hesai + FAST-LIO localization pipeline is not running",
            )
        try:
            await asyncio.to_thread(
                require_navigation_runtime_capability,
                "can_send_goal",
            )
            pose = await asyncio.to_thread(
                navigation_jobs().validate_active_pose,
                map_id=body.map_id,
                map_revision=body.map_revision,
                **body.pose.model_dump(),
            )
            await asyncio.to_thread(
                agent().navigation_send_goal,
                map_id=body.map_id,
                map_revision=body.map_revision,
                **pose,
            )
        except NavigationJobError as exc:
            raise navigation_error(exc) from exc
        except ControlError as exc:
            raise navigation_agent_error(exc) from exc
    return {"accepted": True, "navigation": await asyncio.to_thread(navigation_view)}


@app.post("/api/v1/navigation/cancel")
async def navigation_cancel(
    request: Request,
    body: NavigationCancelRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        await asyncio.to_thread(
            agent().navigation_cancel_goal,
            goal_id=body.goal_id,
        )
    except ControlError as exc:
        raise navigation_agent_error(exc) from exc
    return {"navigation": await asyncio.to_thread(navigation_view)}


@app.post("/api/v1/navigation/clear-costmaps")
async def navigation_clear_costmaps(
    request: Request,
    body: NavigationClearCostmapsRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        await asyncio.to_thread(
            agent().navigation_clear_costmaps,
            scope=body.scope,
        )
    except ControlError as exc:
        raise navigation_agent_error(exc) from exc
    return {"navigation": await asyncio.to_thread(navigation_view)}


@app.get("/api/v1/mapping/control")
async def mapping_control(since_log_seq: int = 0) -> Dict[str, Any]:
    return await asyncio.to_thread(mapping_jobs().snapshot, since_log_seq=since_log_seq)


@app.post("/api/v1/mapping/start")
async def mapping_start(request: Request) -> Dict[str, Any]:
    global MAPPING_TASK
    require_same_origin(request)
    async with PIPELINE_COORDINATION_LOCK:
        require_service_lifecycle_idle()
        require_navigation_idle("navigation must stop before mapping can start")
        if MAPPING_TASK is not None and not MAPPING_TASK.done():
            raise HTTPException(status_code=409, detail="a map save is in progress")
        try:
            return await asyncio.to_thread(mapping_jobs().start_mapping)
        except MappingJobError as exc:
            raise mapping_error(exc) from exc


@app.post("/api/v1/mapping/stop")
async def mapping_stop(request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    async with PIPELINE_COORDINATION_LOCK:
        require_navigation_idle("navigation must stop before the localization pipeline can stop")
        if MAPPING_TASK is not None and not MAPPING_TASK.done():
            raise HTTPException(status_code=409, detail="map save must finish before mapping can stop")
        try:
            return await asyncio.to_thread(mapping_jobs().stop_mapping)
        except MappingJobError as exc:
            raise mapping_error(exc) from exc


async def run_map_save(name: str, kind: str) -> None:
    try:
        await asyncio.to_thread(mapping_jobs().save_map, name, kind)
    except MappingJobError:
        # Expected failures are recorded in the bounded operation snapshot and
        # displayed by the mapping console on its next poll.
        return
    except Exception:
        LOGGER.exception("unexpected map save failure")


@app.post("/api/v1/mapping/save", status_code=202)
async def mapping_save(body: MapSaveRequest, request: Request) -> Dict[str, Any]:
    global MAPPING_TASK
    require_same_origin(request)
    async with PIPELINE_COORDINATION_LOCK:
        require_service_lifecycle_idle()
        require_navigation_idle("navigation must stop before a map can be saved")
        manager = mapping_jobs()
        if MAPPING_TASK is not None and not MAPPING_TASK.done():
            raise HTTPException(status_code=409, detail="another map save is already in progress")
        try:
            name = manager.validate_map_name(body.name)
        except MappingJobError as exc:
            raise mapping_error(exc) from exc
        kind = "pointcloud3d_2d" if body.create_2d else "pointcloud3d"
        if kind not in manager.allowed_save_kinds:
            raise HTTPException(status_code=503, detail="requested map save recipe is unavailable")
        MAPPING_TASK = asyncio.create_task(run_map_save(name, kind), name=f"map-save-{name}")
    return {"accepted": True, "map_name": name, "kind": kind}


@app.get("/api/v1/saved-maps")
async def saved_map_list() -> Dict[str, Any]:
    return await asyncio.to_thread(saved_maps().list_snapshot)


async def run_saved_pcd_conversion(
    manager: MappingJobManager,
    catalog: SavedMapCatalog,
    job_id: str,
    map_id: str,
    expected_revision: str,
    request: SavedMapConvert2DRequest,
) -> None:
    parameters = request.model_dump(exclude={"name"})

    def convert() -> Dict[str, Any]:
        return catalog.convert_pcd_to_2d(
            map_id,
            request.name,
            expected_revision=expected_revision,
            cancelled=lambda: manager.local_operation_cancelled(job_id),
            publication_guard=lambda: manager.local_publication_guard(job_id),
            **parameters,
        )

    try:
        await asyncio.to_thread(
            manager.run_reserved_local_operation,
            job_id,
            convert,
        )
    except (MappingJobError, SavedMapError):
        # The manager records the bounded failure for mapping/control polling.
        return
    except Exception:
        LOGGER.exception("unexpected saved PCD conversion failure")


@app.post("/api/v1/saved-maps/{map_id}/convert-2d", status_code=202)
async def convert_saved_pcd_to_2d(
    map_id: str,
    body: SavedMapConvert2DRequest,
    request: Request,
) -> Dict[str, Any]:
    global MAPPING_TASK
    require_same_origin(request)
    async with PIPELINE_COORDINATION_LOCK:
        require_service_lifecycle_idle()
        require_navigation_idle("navigation must stop before converting a map")
        if MAPPING_TASK is not None and not MAPPING_TASK.done():
            raise HTTPException(status_code=409, detail="another map operation is already in progress")
        manager = mapping_jobs()
        catalog = saved_maps()
        parameters = body.model_dump(exclude={"name"})
        try:
            validated = catalog.validate_pcd_conversion(
                map_id,
                body.name,
                **parameters,
            )
        except (
            SavedMapNotFound,
            SavedMapInvalidName,
            SavedMapReadOnly,
            SavedMapConflict,
            SavedMapFormatError,
            SavedMapPointLimitError,
        ) as exc:
            raise saved_map_error(exc) from exc
        try:
            reservation = manager.reserve_local_operation("pcd_to_2d", body.name)
        except MappingJobError as exc:
            raise mapping_error(exc) from exc
        operation = reservation["operation"]
        job_id = str(operation["job_id"])
        source_revision = str(validated["source"]["revision"])
        conversion_coroutine = run_saved_pcd_conversion(
            manager,
            catalog,
            job_id,
            map_id,
            source_revision,
            body,
        )
        try:
            MAPPING_TASK = asyncio.create_task(
                conversion_coroutine,
                name=f"pcd-to-2d-{job_id}",
            )
        except Exception as exc:
            conversion_coroutine.close()
            manager.fail_reserved_local_operation(
                job_id,
                "map conversion worker could not be scheduled",
            )
            raise HTTPException(
                status_code=503,
                detail="map conversion worker could not be scheduled",
            ) from exc
    return {
        "accepted": True,
        "job_id": job_id,
        "map_name": body.name,
        "kind": "pcd_to_2d",
        "operation": operation,
        "source": validated["source"],
        "parameters": validated["parameters"],
        "filter": "projected_xy_density",
    }


@app.post("/api/v1/saved-maps/{map_id}/edited-copy")
async def save_edited_map_copy(
    map_id: str,
    body: SavedMapEditedCopyRequest,
    request: Request,
) -> Dict[str, Any]:
    require_same_origin(request)
    async with PIPELINE_COORDINATION_LOCK:
        require_service_lifecycle_idle()
        require_navigation_idle("navigation must stop before editing a map")
        if MAPPING_TASK is not None and not MAPPING_TASK.done():
            raise HTTPException(status_code=409, detail="map operation must finish before editing")
        runs = [run.model_dump() for run in body.runs]
        try:
            metadata = await asyncio.to_thread(
                saved_maps().save_edited_copy,
                map_id,
                body.name,
                body.source_revision,
                runs,
            )
        except (
            SavedMapNotFound,
            SavedMapInvalidName,
            SavedMapReadOnly,
            SavedMapConflict,
            SavedMapFormatError,
            SavedMapMutationError,
        ) as exc:
            raise saved_map_error(exc) from exc
    return {"map": metadata}


@app.get("/api/v1/saved-maps/{map_id}")
async def saved_map_metadata(map_id: str) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(saved_maps().metadata, map_id)
    except SavedMapNotFound as exc:
        raise saved_map_error(exc) from exc


@app.patch("/api/v1/saved-maps/{map_id}")
async def rename_saved_map(
    map_id: str,
    body: SavedMapRenameRequest,
    request: Request,
) -> Dict[str, Any]:
    require_same_origin(request)
    async with PIPELINE_COORDINATION_LOCK:
        require_service_lifecycle_idle()
        require_navigation_idle("navigation must stop before a map can be renamed")
        if MAPPING_TASK is not None and not MAPPING_TASK.done():
            raise HTTPException(status_code=409, detail="map save must finish before a map can be renamed")
        try:
            metadata = await asyncio.to_thread(saved_maps().rename, map_id, body.name)
        except (
            SavedMapNotFound,
            SavedMapInvalidName,
            SavedMapReadOnly,
            SavedMapConflict,
            SavedMapMutationError,
        ) as exc:
            raise saved_map_error(exc) from exc
    return {"map": metadata}


@app.delete("/api/v1/saved-maps/{map_id}")
async def delete_saved_map(map_id: str, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    async with PIPELINE_COORDINATION_LOCK:
        require_service_lifecycle_idle()
        require_navigation_idle("navigation must stop before a map can be deleted")
        if MAPPING_TASK is not None and not MAPPING_TASK.done():
            raise HTTPException(status_code=409, detail="map save must finish before a map can be deleted")
        try:
            result = await asyncio.to_thread(saved_maps().delete, map_id)
        except (
            SavedMapNotFound,
            SavedMapReadOnly,
            SavedMapMutationError,
        ) as exc:
            raise saved_map_error(exc) from exc
    return {"deleted": result}


@app.get("/api/v1/saved-maps/{map_id}/data")
async def saved_map_data(map_id: str, max_points: str = "all") -> Response:
    point_limit = parse_saved_point_limit(max_points)
    try:
        payload = await asyncio.to_thread(saved_maps().data, map_id, point_limit)
    except (SavedMapNotFound, SavedMapFormatError, SavedMapPointLimitError) as exc:
        raise saved_map_error(exc) from exc
    content = await asyncio.to_thread(encode_json, payload)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Cache-Control": "private, no-cache"},
    )


@app.websocket("/api/v1/ws/pointcloud")
async def pointcloud_stream(websocket: WebSocket) -> None:
    if not websocket_same_origin(websocket):
        await websocket.close(code=4403, reason="same-origin point-cloud WebSocket required")
        return
    await websocket.accept()
    last_seq = -1

    async def send_next() -> None:
        nonlocal last_seq
        snapshot = agent().pointcloud_binary_snapshot()
        seq = int(snapshot.get("seq", 0))
        if seq != last_seq and snapshot.get("points_bytes"):
            await websocket.send_bytes(await cached_pointcloud_binary_frame(snapshot))
            last_seq = seq

    try:
        await stream_until_disconnect(websocket, send_next)
    except (WebSocketDisconnect, RuntimeError, PointCloudFrameError):
        return


@app.websocket("/api/v1/ws/camera")
async def camera_stream(websocket: WebSocket) -> None:
    if not websocket_same_origin(websocket):
        await websocket.close(code=4403, reason="same-origin camera WebSocket required")
        return
    await websocket.accept()
    runtime_agent = agent()
    opened = await asyncio.to_thread(runtime_agent.camera_stream_open)
    if not opened.get("accepted", False):
        await websocket.close(code=1012, reason="camera relay is shutting down")
        return
    last_seq = -1

    async def send_next() -> None:
        nonlocal last_seq
        snapshot = runtime_agent.camera_snapshot()
        seq = int(snapshot.get("seq", 0))
        if seq and seq != last_seq and snapshot.get("data"):
            metadata = {key: value for key, value in snapshot.items() if key != "data"}
            await websocket.send_text(json.dumps(metadata, separators=(",", ":")))
            await websocket.send_bytes(snapshot["data"])
            last_seq = seq

    try:
        await stream_until_disconnect(websocket, send_next)
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        await asyncio.to_thread(runtime_agent.camera_stream_close)


@app.websocket("/api/v1/ws/joints")
async def joint_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    last_signature: tuple[int, str] | None = None
    try:
        while True:
            snapshot = agent().joint_snapshot()
            signature = (int(snapshot.get("seq", 0)), str(snapshot.get("state", "waiting")))
            if signature != last_signature:
                await websocket.send_text(
                    json.dumps(snapshot, separators=(",", ":"), allow_nan=False)
                )
                last_signature = signature
            await asyncio.sleep(0.02)
    except (WebSocketDisconnect, RuntimeError):
        return


@app.websocket("/api/v1/ws/pose")
async def pose_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    last_signature: tuple[int, str, str] | None = None
    try:
        while True:
            snapshot = agent().pose_snapshot()
            signature = (
                int(snapshot.get("seq", 0)),
                str(snapshot.get("state", "waiting")),
                str(snapshot.get("topic", "")),
            )
            if signature != last_signature:
                await websocket.send_text(
                    json.dumps(snapshot, separators=(",", ":"), allow_nan=False)
                )
                last_signature = signature
            await asyncio.sleep(0.02)
    except (WebSocketDisconnect, RuntimeError):
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Robot Scope ROS 2 web agent")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--robot-ip", default="")
    parser.add_argument("--profile", default="")
    parser.add_argument("--cloud-max-points", type=int, default=18000)
    parser.add_argument(
        "--source-selection-state",
        default="~/.local/state/robot-scope/source-selection.json",
    )
    parser.add_argument("--mapping-output-dir", default="~/ws/go2_3d/maps")
    parser.add_argument(
        "--navigation-runtime-dir",
        default="~/.local/state/robot-scope/navigation",
    )
    return parser.parse_args()


def main() -> None:
    global AGENT, SAVED_MAPS, MAPPING_JOBS, NAVIGATION_JOBS, SERVICE_LIFECYCLE
    args = parse_args()
    AGENT = RosAgent(
        robot_ip=args.robot_ip,
        profile_path=args.profile or None,
        cloud_max_points=args.cloud_max_points,
        source_selection_path=args.source_selection_state or None,
    )
    profile_base = Path(args.profile).expanduser().resolve().parent if args.profile else Path.cwd()
    project_dir = Path(__file__).resolve().parents[1]
    save_script = project_dir / "scripts" / "save_hesai_map_humble.sh"
    requested_output_dir = Path(args.mapping_output_dir).expanduser()
    requested_output_dir.mkdir(parents=True, exist_ok=True)
    if requested_output_dir.is_symlink() or not requested_output_dir.is_dir():
        raise RuntimeError("mapping output directory must be a real directory")
    mapping_output_dir = requested_output_dir.resolve(strict=True)

    # Establish the catalog limit first, then give that exact per-artifact
    # limit to every saver recipe.  A successfully published file can therefore
    # never disappear merely because the catalog applies a smaller size bound.
    catalog = SavedMapCatalog.from_profile(
        AGENT.profile,
        base_dir=profile_base,
        additional_roots=[mapping_output_dir],
        managed_roots=[mapping_output_dir],
    )
    map_file_limit = catalog.max_file_bytes
    manager = MappingJobManager.for_robot_scope(
        project_dir=project_dir,
        output_dir=mapping_output_dir,
        enable_preview=bool(
            isinstance(AGENT.profile.get("xt16_preview"), dict)
            and AGENT.profile["xt16_preview"].get("enabled") is True
            and os.environ.get("ROBOT_SCOPE_DDS_INTERFACE_READY") == "1"
        ),
        save_commands={
            "pointcloud3d": SaveCommandSpec(
                (str(save_script), "{output_prefix}", "pcd"),
                (".pcd",),
                cwd=project_dir,
                timeout_seconds=35,
                min_result_bytes=128,
                max_result_bytes=map_file_limit,
            ),
            "pointcloud3d_2d": SaveCommandSpec(
                (str(save_script), "{output_prefix}", "pcd-and-2d"),
                (".pcd", ".yaml", ".pgm"),
                cwd=project_dir,
                timeout_seconds=90,
                min_result_bytes=4,
                max_result_bytes=map_file_limit,
            ),
        },
        # Existing classroom sessions may have been started in a terminal.
        # The one-shot saver still requires a fresh /Laser_map and will time
        # out safely, while stop only affects dashboard-owned process groups.
        require_pipeline_for_save=False,
    )
    SAVED_MAPS = catalog
    MAPPING_JOBS = manager

    def navigation_terminal(reason: str) -> None:
        current = AGENT
        if current is not None:
            current.navigation_deactivate(reason=reason)

    NAVIGATION_JOBS = NavigationJobManager.for_go2_humble(
        project_dir=project_dir,
        runtime_dir=Path(args.navigation_runtime_dir),
        map_snapshotter=catalog.snapshot_navigation_map,
        on_terminal=navigation_terminal,
    )
    SERVICE_LIFECYCLE = ServiceLifecycleManager.from_environment(
        blocker_provider=service_lifecycle_blockers,
    )
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        workers=1,
        access_log=False,
        timeout_graceful_shutdown=3,
    )


if __name__ == "__main__":
    main()
