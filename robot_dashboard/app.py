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
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from .application.lifecycle_coordinator import (
    LifecycleCoordinator,
    LifecycleTransitionBusy,
)
from .application.mapping_coordinator import (
    MappingCoordinator,
    MappingCoordinatorConflict,
    MappingCoordinatorError,
    MappingCoordinatorUnavailable,
)
from .application.mission_coordinator import MissionCoordinator, MissionError
from .application.navigation_coordinator import NavigationCoordinator
from .application.runtime import ApplicationRuntime
from .api.dependencies import require_same_origin, websocket_same_origin
from .api.routers.cameras import router as cameras_router
from .api.routers.dataset import create_router as create_dataset_router
from .api.routers.discovery import router as discovery_router
from .api.routers.missions import router as missions_router
from .api.routers.model_registry import router as model_registry_router
from .api.routers.perception import router as perception_router
from .api.routers.system import router as system_router
from .api.routers.telemetry import router as telemetry_router
from .api.models import (
    ControlArmRequest,
    ControlClearEstopRequest,
    ControlLeaseRequest,
    ControlStopRequest,
    MapSaveRequest,
    NavigationAnnotationGoalRequest,
    NavigationCancelRequest,
    NavigationClearCostmapsRequest,
    NavigationGoalRequest,
    NavigationParameterPatchRequest,
    NavigationPoseRequest,
    NavigationStartRequest,
    NavigationStopRequest,
    SavedMapConvert2DRequest,
    SavedMapEditedCopyRequest,
    SavedMapAnnotationsRequest,
    SavedMapRenameRequest,
)
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
from .public_diagnostics import public_diagnostic
from .dataset_capture import DatasetCaptureManager
from .diagnostics import DiagnosticsBundleService
from .mapping_jobs import (
    InvalidMapName,
    JobBusyError,
    MappingJobError,
    MappingJobManager,
    PipelineNotRunning,
    SaveCommandSpec,
    SaveResultError,
)
from .model_registry import ModelRegistry
from .navigation_jobs import (
    NavigationBusy,
    NavigationConflict,
    NavigationJobError,
    NavigationJobManager,
    NavigationParameterError,
    NavigationPoseError,
    NavigationUnavailable,
)
from .operator_events import (
    OperatorEventTimeline,
    classify_http_event,
    record_http_event,
)
from .perception import PerceptionBridgeClient, PerceptionPolicy, PerceptionStore
from .ros_agent import RosAgent
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
    prepare_private_map_root,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGGER = logging.getLogger(__name__)
RUNTIME = ApplicationRuntime()


class DashboardStaticFiles(StaticFiles):
    """Prevent stale frontend code after an operator service restart."""

    async def get_response(self, path: str, scope: Dict[str, Any]) -> Response:
        response = await super().get_response(path, scope)
        if path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "no-store"
        return response


@asynccontextmanager
async def lifespan(fastapi: FastAPI):
    runtime = fastapi.state.runtime
    if runtime.agent is None:
        raise RuntimeError("ROS agent has not been configured")
    runtime.agent.start()
    if runtime.perception is not None:
        runtime.perception.start()
    if runtime.mapping is not None:
        try:
            await runtime.mapping.start_preview()
        except MappingJobError:
            # Raw XT16 preview is optional observability. Keep the dashboard
            # available and expose WAITING when fixed dependencies are absent.
            LOGGER.exception("XT16 point-cloud preview startup failed")
    try:
        yield
    finally:
        # Mission state is persisted and active goals are canceled before the
        # lower-level navigation owner begins its terminal cleanup.
        if runtime.mission is not None:
            try:
                await runtime.mission.close()
            except Exception:
                LOGGER.exception("mission coordinator shutdown failed")
        # Fence and settle any background START before lifecycle observers are
        # closed, matching the original shutdown transaction boundary.
        if runtime.navigation is not None:
            try:
                await runtime.navigation.settle_startup()
            except Exception:
                LOGGER.exception("navigation startup shutdown settlement failed")
        # Closing observers cannot start or stop either fixed service.
        if runtime.lifecycle is not None:
            runtime.lifecycle.close()
        # Settle START, close navigation motion/process ownership, and clean
        # only the exact localization job owned by the Nav transaction.
        if runtime.navigation is not None:
            try:
                await runtime.navigation.close()
            except Exception:
                # Remaining motion cleanup must still run after manager errors.
                LOGGER.exception("navigation coordinator shutdown failed")
        # Motion stop takes priority over potentially slow storage/process work.
        runtime.agent.shutdown_control()
        if runtime.perception is not None:
            runtime.perception.close()
        if runtime.dataset_capture is not None:
            try:
                await asyncio.to_thread(runtime.dataset_capture.close)
            except Exception:
                # Dataset durability must not skip the remaining ROS cleanup.
                LOGGER.exception("dataset capture shutdown failed")
        if runtime.mapping is not None:
            await runtime.mapping.close()
        runtime.agent.stop()


app = FastAPI(
    title="Robot Scope",
    version="0.2.0",
    description="ROS2 Autonomous Mobile Robot Mapping, Navigation and Control Dashboard",
    lifespan=lifespan,
)
app.state.runtime = RUNTIME
app.mount("/static", DashboardStaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def api_response_security(request: Request, call_next: Any) -> Response:
    """Keep operational API responses out of browser and intermediary caches."""

    tracked_operator_event = classify_http_event(request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        if tracked_operator_event is not None:
            try:
                await asyncio.to_thread(
                    record_http_event,
                    getattr(request.app.state.runtime, "operator_events", None),
                    method=request.method,
                    path=request.url.path,
                    headers=request.headers,
                    status_code=500,
                )
            except Exception:
                LOGGER.exception("operator event recording failed")
        raise
    if request.url.path.startswith("/api/v1/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
    if tracked_operator_event is not None:
        try:
            await asyncio.to_thread(
                record_http_event,
                getattr(request.app.state.runtime, "operator_events", None),
                method=request.method,
                path=request.url.path,
                headers=request.headers,
                status_code=response.status_code,
            )
        except Exception:
            # Event persistence cannot change a robot request result or make a
            # cleanup route unavailable.
            LOGGER.exception("operator event recording failed")
    return response


def agent() -> RosAgent:
    if RUNTIME.agent is None:
        raise HTTPException(status_code=503, detail="ROS agent is not configured")
    return RUNTIME.agent


def _encode_json(payload: Dict[str, Any]) -> bytes:
    """Serialize one bounded server-owned response without NaN values."""

    return json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")


def saved_maps() -> SavedMapCatalog:
    if RUNTIME.saved_maps is None:
        raise HTTPException(status_code=503, detail="saved map catalog is not configured")
    return RUNTIME.saved_maps


def mapping_coordinator() -> MappingCoordinator:
    if RUNTIME.mapping is None:
        raise HTTPException(status_code=503, detail="mapping operations are not configured")
    return RUNTIME.mapping


def navigation_coordinator() -> NavigationCoordinator:
    if RUNTIME.navigation is None:
        raise HTTPException(status_code=503, detail="navigation is not configured")
    return RUNTIME.navigation


def mission_coordinator() -> MissionCoordinator:
    if RUNTIME.mission is None:
        raise HTTPException(status_code=503, detail="missions are not configured")
    return RUNTIME.mission


def lifecycle_coordinator() -> LifecycleCoordinator:
    if RUNTIME.lifecycle is None:
        raise HTTPException(
            status_code=503,
            detail="service lifecycle control is not configured",
        )
    return RUNTIME.lifecycle


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
    """Compatibility projection delegated to the mapping coordinator."""

    return mapping_coordinator().activity()


def mapping_pipeline_state() -> str:
    """Compatibility projection delegated to the mapping coordinator."""

    return mapping_coordinator().pipeline_state()


def navigation_start_state() -> Dict[str, Any]:
    """Compatibility projection delegated to the navigation coordinator."""

    return navigation_coordinator().start_state()


def _navigation_start_internal() -> Dict[str, Any]:
    return navigation_coordinator().internal_start_state()


def service_lifecycle_blockers() -> list[str]:
    """Compatibility projection delegated to the lifecycle coordinator."""

    return lifecycle_coordinator().service_blockers()


def control_bridge_lifecycle_preflight() -> Dict[str, list[str]]:
    """Compatibility projection delegated to the lifecycle coordinator."""

    return lifecycle_coordinator().control_bridge_preflight()


def signed_control_bridge_status_fresh() -> bool | None:
    return lifecycle_coordinator().signed_control_bridge_status_fresh()


def require_service_lifecycle_idle() -> None:
    """Translate the application lifecycle gate into the stable HTTP conflict."""

    try:
        lifecycle_coordinator().require_idle()
    except LifecycleTransitionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


app.include_router(system_router)
app.include_router(telemetry_router)
app.include_router(cameras_router)
app.include_router(discovery_router)
app.include_router(create_dataset_router(require_service_lifecycle_idle))
app.include_router(missions_router)
app.include_router(model_registry_router)
app.include_router(perception_router)


def navigation_active() -> bool:
    return navigation_coordinator().is_active()


def require_navigation_idle(detail: str) -> None:
    if navigation_active():
        raise HTTPException(status_code=409, detail=detail)


def navigation_view() -> Dict[str, Any]:
    """Compatibility projection delegated to the navigation coordinator."""

    return navigation_coordinator().view()


def require_mission_navigation_idle(detail: str) -> None:
    mission = RUNTIME.mission
    if mission is not None and mission.blocks_navigation_goal():
        raise HTTPException(status_code=409, detail=detail)


def control_view(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Translate the internal safety snapshot to the stable browser contract."""

    limits = snapshot.get("limits", {})
    readiness = snapshot.get("readiness", {})
    internal_bridge = dict(snapshot.get("bridge", {}))
    bridge = {
        key: internal_bridge[key]
        for key in (
            "state",
            "ready",
            "authenticated",
            "connected",
            "available",
            "status_age_s",
            "lowstate_age_ms",
            "sport_subscribers",
            "own_sport_publishers",
            "foreign_named_sport_publishers",
            "bare_unitree_sport_publishers",
            "expected_bare_sport_publishers",
            "total_sport_publishers",
            "lowstate_publishers",
            "transport",
        )
        if key in internal_bridge
    }
    if (
        "total_sport_publishers" not in bridge
        and "sport_publishers" in internal_bridge
    ):
        bridge["total_sport_publishers"] = internal_bridge["sport_publishers"]
    bridge["message"] = public_diagnostic(
        internal_bridge.get("message", internal_bridge.get("last_error", ""))
    )
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
        state = "제어 브리지 키 또는 제어 전송이 설정되지 않았습니다."
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
    return HTTPException(status_code=500, detail="mapping operation failed")


def mapping_coordination_error(exc: MappingCoordinatorError) -> HTTPException:
    if isinstance(exc, MappingCoordinatorConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, MappingCoordinatorUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail="mapping coordination failed")


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
        return HTTPException(status_code=500, detail="saved map mutation failed")
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



@app.get("/api/v1/control")
async def control_status() -> Dict[str, Any]:
    return {"control": control_view(agent().control_snapshot())}


@app.post("/api/v1/control/arm")
async def control_arm(request: Request, body: ControlArmRequest) -> Dict[str, Any]:
    require_same_origin(request)
    async with RUNTIME.pipeline_coordination_lock:
        require_service_lifecycle_idle()
        if navigation_coordinator().manual_control_blocked():
            raise HTTPException(
                status_code=409,
                detail="navigation startup must stop before manual control can arm",
            )
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
    binding = RUNTIME.control_bindings.pop(body.lease_id, None)
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
    RUNTIME.control_bindings.clear()
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
        RUNTIME.control_bindings[lease_id] = binding
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
                RUNTIME.control_bindings.pop(lease_id, None)
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
                RUNTIME.control_bindings.pop(lease_id, None)
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
            RUNTIME.control_bindings.pop(lease_id, None)
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
    return await asyncio.to_thread(navigation_coordinator().view)


@app.get("/api/v1/navigation/logs")
async def navigation_logs(
    response: Response,
    after: int = Query(default=0, ge=0, le=9_007_199_254_740_991),
    limit: int = Query(default=80, ge=1, le=100),
) -> Dict[str, Any]:
    """Return only the coordinator's bounded, redacted progress projection."""

    response.headers["Cache-Control"] = "no-store"
    return await asyncio.to_thread(
        navigation_coordinator().progress_snapshot,
        after=after,
        limit=limit,
    )


@app.get("/api/v1/navigation/parameters")
async def navigation_parameters() -> Dict[str, Any]:
    return await asyncio.to_thread(navigation_coordinator().parameters_snapshot)


@app.patch("/api/v1/navigation/parameters")
async def update_navigation_parameters(
    request: Request,
    body: NavigationParameterPatchRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        return await navigation_coordinator().update_parameters(
            body.base_revision,
            body.values,
        )
    except NavigationJobError as exc:
        raise navigation_error(exc) from exc


@app.post("/api/v1/navigation/start", status_code=202)
async def navigation_start(
    request: Request,
    body: NavigationStartRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        return await navigation_coordinator().start(
            map_id=body.map_id,
            map_revision=body.map_revision,
            parameters_revision=body.parameters_revision,
        )
    except LifecycleTransitionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SavedMapError as exc:
        raise saved_map_error(exc) from exc
    except NavigationJobError as exc:
        raise navigation_error(exc) from exc
    except ControlError as exc:
        raise navigation_agent_error(exc) from exc


@app.post("/api/v1/navigation/stop")
async def navigation_stop(
    request: Request,
    body: NavigationStopRequest,
) -> Dict[str, Any]:
    del body
    require_same_origin(request)
    try:
        if RUNTIME.mission is not None and RUNTIME.mission.blocks_navigation_goal():
            await RUNTIME.mission.abort_active(reason="navigation_stop")
        return await navigation_coordinator().stop()
    except MissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NavigationJobError as exc:
        raise navigation_error(exc) from exc


@app.post("/api/v1/navigation/initial-pose")
async def navigation_initial_pose(
    request: Request,
    body: NavigationPoseRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    require_mission_navigation_idle("active mission must pause or abort before changing initial pose")
    try:
        return await navigation_coordinator().set_initial_pose(
            map_id=body.map_id,
            map_revision=body.map_revision,
            **body.pose.model_dump(),
        )
    except LifecycleTransitionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NavigationJobError as exc:
        raise navigation_error(exc) from exc
    except ControlError as exc:
        raise navigation_agent_error(exc) from exc


@app.post("/api/v1/navigation/goal")
async def navigation_goal(
    request: Request,
    body: NavigationGoalRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    require_mission_navigation_idle("active mission owns navigation goals")
    try:
        return await navigation_coordinator().send_goal(
            map_id=body.map_id,
            map_revision=body.map_revision,
            confirmed=body.confirmed,
            **body.pose.model_dump(),
        )
    except LifecycleTransitionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NavigationJobError as exc:
        raise navigation_error(exc) from exc
    except ControlError as exc:
        raise navigation_agent_error(exc) from exc


@app.post("/api/v1/navigation/goal/annotation")
async def navigation_annotation_goal(
    request: Request,
    body: NavigationAnnotationGoalRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    require_mission_navigation_idle("active mission owns navigation goals")
    try:
        return await navigation_coordinator().send_annotation_goal(
            map_id=body.map_id,
            map_revision=body.map_revision,
            annotation_revision=body.annotation_revision,
            annotation_id=body.annotation_id,
            confirmed=body.confirmed,
        )
    except LifecycleTransitionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SavedMapError as exc:
        raise saved_map_error(exc) from exc
    except NavigationJobError as exc:
        raise navigation_error(exc) from exc
    except ControlError as exc:
        raise navigation_agent_error(exc) from exc


@app.post("/api/v1/navigation/cancel")
async def navigation_cancel(
    request: Request,
    body: NavigationCancelRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    require_mission_navigation_idle("use mission pause or abort for an active mission goal")
    try:
        return await navigation_coordinator().cancel_goal(goal_id=body.goal_id)
    except ControlError as exc:
        raise navigation_agent_error(exc) from exc


@app.post("/api/v1/navigation/clear-costmaps")
async def navigation_clear_costmaps(
    request: Request,
    body: NavigationClearCostmapsRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        return await navigation_coordinator().clear_costmaps(scope=body.scope)
    except ControlError as exc:
        raise navigation_agent_error(exc) from exc


@app.get("/api/v1/mapping/control")
async def mapping_control(since_log_seq: int = 0) -> Dict[str, Any]:
    return await asyncio.to_thread(
        mapping_coordinator().snapshot,
        since_log_seq=since_log_seq,
    )


@app.post("/api/v1/mapping/start")
async def mapping_start(request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        return await mapping_coordinator().start()
    except LifecycleTransitionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MappingCoordinatorError as exc:
        raise mapping_coordination_error(exc) from exc
    except MappingJobError as exc:
        raise mapping_error(exc) from exc


@app.post("/api/v1/mapping/stop")
async def mapping_stop(request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        return await mapping_coordinator().stop()
    except MappingCoordinatorError as exc:
        raise mapping_coordination_error(exc) from exc
    except MappingJobError as exc:
        raise mapping_error(exc) from exc


@app.post("/api/v1/mapping/save", status_code=202)
async def mapping_save(body: MapSaveRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        return await mapping_coordinator().save(
            body.name,
            create_2d=body.create_2d,
        )
    except LifecycleTransitionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MappingCoordinatorError as exc:
        raise mapping_coordination_error(exc) from exc
    except MappingJobError as exc:
        raise mapping_error(exc) from exc


@app.get("/api/v1/saved-maps")
async def saved_map_list() -> Dict[str, Any]:
    return await asyncio.to_thread(saved_maps().list_snapshot)


@app.post("/api/v1/saved-maps/{map_id}/convert-2d", status_code=202)
async def convert_saved_pcd_to_2d(
    map_id: str,
    body: SavedMapConvert2DRequest,
    request: Request,
) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        return await mapping_coordinator().convert_pcd_to_2d(
            map_id,
            body.name,
            body.model_dump(exclude={"name"}),
        )
    except LifecycleTransitionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MappingCoordinatorError as exc:
        raise mapping_coordination_error(exc) from exc
    except MappingJobError as exc:
        raise mapping_error(exc) from exc
    except SavedMapError as exc:
        raise saved_map_error(exc) from exc


@app.post("/api/v1/saved-maps/{map_id}/edited-copy")
async def save_edited_map_copy(
    map_id: str,
    body: SavedMapEditedCopyRequest,
    request: Request,
) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        metadata = await mapping_coordinator().save_edited_copy(
            map_id,
            body.name,
            body.source_revision,
            [run.model_dump() for run in body.runs],
        )
    except LifecycleTransitionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MappingCoordinatorError as exc:
        raise mapping_coordination_error(exc) from exc
    except SavedMapError as exc:
        raise saved_map_error(exc) from exc
    return {"map": metadata}


@app.get("/api/v1/saved-maps/{map_id}")
async def saved_map_metadata(map_id: str) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(saved_maps().metadata, map_id)
    except SavedMapNotFound as exc:
        raise saved_map_error(exc) from exc


@app.get("/api/v1/saved-maps/{map_id}/annotations")
async def saved_map_annotations(map_id: str) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(saved_maps().annotations, map_id)
    except SavedMapError as exc:
        raise saved_map_error(exc) from exc


@app.patch("/api/v1/saved-maps/{map_id}/annotations")
async def update_saved_map_annotations(
    map_id: str,
    body: SavedMapAnnotationsRequest,
    request: Request,
) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        return await mapping_coordinator().update_annotations(
            map_id,
            body.map_revision,
            body.base_annotation_revision,
            [item.model_dump() for item in body.points],
            [item.model_dump() for item in body.polygons],
        )
    except LifecycleTransitionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MappingCoordinatorError as exc:
        raise mapping_coordination_error(exc) from exc
    except SavedMapError as exc:
        raise saved_map_error(exc) from exc


@app.patch("/api/v1/saved-maps/{map_id}")
async def rename_saved_map(
    map_id: str,
    body: SavedMapRenameRequest,
    request: Request,
) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        metadata = await mapping_coordinator().rename(map_id, body.name)
    except LifecycleTransitionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MappingCoordinatorError as exc:
        raise mapping_coordination_error(exc) from exc
    except SavedMapError as exc:
        raise saved_map_error(exc) from exc
    return {"map": metadata}


@app.delete("/api/v1/saved-maps/{map_id}")
async def delete_saved_map(map_id: str, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        result = await mapping_coordinator().delete(map_id)
    except LifecycleTransitionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MappingCoordinatorError as exc:
        raise mapping_coordination_error(exc) from exc
    except SavedMapError as exc:
        raise saved_map_error(exc) from exc
    return {"deleted": result}


@app.get("/api/v1/saved-maps/{map_id}/data")
async def saved_map_data(map_id: str, max_points: str = "all") -> Response:
    point_limit = parse_saved_point_limit(max_points)
    try:
        payload = await asyncio.to_thread(saved_maps().data, map_id, point_limit)
    except (SavedMapNotFound, SavedMapFormatError, SavedMapPointLimitError) as exc:
        raise saved_map_error(exc) from exc
    content = await asyncio.to_thread(_encode_json, payload)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Cache-Control": "private, no-cache"},
    )



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
        "--dataset-output-dir",
        default=str(Path(__file__).resolve().parents[1] / "runtime" / "datasets"),
    )
    parser.add_argument(
        "--navigation-runtime-dir",
        default="~/.local/state/robot-scope/navigation",
    )
    parser.add_argument(
        "--operator-event-dir",
        default=str(
            Path(__file__).resolve().parents[1] / "runtime" / "operator-events"
        ),
    )
    parser.add_argument("--perception-source-ip", default="")
    parser.add_argument("--perception-result-port", type=int, default=8092)
    parser.add_argument("--perception-policy", default="")
    parser.add_argument(
        "--model-registry-dir",
        default=str(Path(__file__).resolve().parents[1] / "runtime" / "model-registry"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    RUNTIME.agent = RosAgent(
        robot_ip=args.robot_ip,
        profile_path=args.profile or None,
        cloud_max_points=args.cloud_max_points,
        source_selection_path=args.source_selection_state or None,
    )
    if bool(args.perception_source_ip) != bool(args.perception_policy):
        raise RuntimeError("perception source IP and policy must be configured together")
    if args.perception_source_ip:
        policy = PerceptionPolicy.load(Path(args.perception_policy).expanduser())
        RUNTIME.perception = PerceptionBridgeClient(
            PerceptionStore(args.perception_source_ip, policy),
            port=args.perception_result_port,
        )
    profile_base = (
        Path(args.profile).expanduser().resolve().parent
        if args.profile
        else Path.cwd()
    )
    project_dir = Path(__file__).resolve().parents[1]
    RUNTIME.model_registry = ModelRegistry(Path(args.model_registry_dir))
    save_script = project_dir / "scripts" / "save_hesai_map_humble.sh"
    requested_output_dir = Path(args.mapping_output_dir).expanduser()
    mapping_output_dir = prepare_private_map_root(requested_output_dir)

    # Establish one exact catalog limit for every trusted saver recipe.
    catalog = SavedMapCatalog.from_profile(
        RUNTIME.agent.profile,
        base_dir=profile_base,
        additional_roots=[mapping_output_dir],
        managed_roots=[mapping_output_dir],
    )
    map_file_limit = catalog.max_file_bytes
    mapping_manager = MappingJobManager.for_robot_scope(
        project_dir=project_dir,
        output_dir=mapping_output_dir,
        enable_preview=bool(
            isinstance(RUNTIME.agent.profile.get("xt16_preview"), dict)
            and RUNTIME.agent.profile["xt16_preview"].get("enabled") is True
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
        # The saver still requires a fresh /Laser_map; stop only affects
        # dashboard-owned process groups.
        require_pipeline_for_save=False,
    )
    RUNTIME.saved_maps = catalog
    def dataset_metadata_snapshot() -> Dict[str, Any]:
        metadata = RUNTIME.agent.pose_snapshot()
        if RUNTIME.perception is not None:
            metadata["perception_reference"] = RUNTIME.perception.store.metadata_reference()
        return metadata

    def dataset_session_context_snapshot() -> Dict[str, Any]:
        active_models = RUNTIME.model_registry.active_snapshot()["active"]
        perception_policy = (
            RUNTIME.perception.store.policy
            if RUNTIME.perception is not None
            else None
        )
        model_ids = [
            str(value["model_id"])
            for value in active_models.values()
            if isinstance(value, dict) and value.get("model_id")
        ]
        if RUNTIME.perception is not None:
            for result in RUNTIME.perception.store.latest_snapshot()["results"]:
                model_id = str(result.get("model_id", ""))
                if model_id and model_id not in model_ids:
                    model_ids.append(model_id)
        return {
            "capture_profile": "server-jpeg-fixed",
            "robot_side_source_id": (
                perception_policy.source_id if perception_policy is not None else "unknown"
            ),
            "network_topology_revision": os.environ.get(
                "ROBOT_SCOPE_NETWORK_TOPOLOGY_REVISION", "unknown"
            ),
            "git_commit": os.environ.get("ROBOT_SCOPE_GIT_COMMIT", "unknown"),
            "active_preview_profile": "realsense-mjpeg",
            "perception_shadow_enabled": RUNTIME.perception is not None,
            "model_ids": model_ids,
        }

    RUNTIME.dataset_capture = DatasetCaptureManager(
        Path(args.dataset_output_dir),
        camera_open=RUNTIME.agent.camera_stream_open,
        camera_close=RUNTIME.agent.camera_stream_close,
        camera_snapshots=RUNTIME.agent.camera_snapshots,
        metadata_snapshot=dataset_metadata_snapshot,
        session_context_snapshot=dataset_session_context_snapshot,
    )

    def require_lifecycle_idle_application() -> None:
        lifecycle = RUNTIME.lifecycle
        if lifecycle is None:
            raise RuntimeError("service lifecycle coordinator is not configured")
        lifecycle.require_idle()

    def navigation_is_active() -> bool:
        navigation = RUNTIME.navigation
        # Mapping mutations fail closed until the navigation owner is wired.
        return True if navigation is None else navigation.is_active()

    RUNTIME.mapping = MappingCoordinator(
        mapping_manager,
        catalog,
        coordination_lock=RUNTIME.pipeline_coordination_lock,
        navigation_active=navigation_is_active,
        require_lifecycle_idle=require_lifecycle_idle_application,
        logger=LOGGER,
    )
    navigation_manager = NavigationJobManager.for_go2_humble(
        project_dir=project_dir,
        runtime_dir=Path(args.navigation_runtime_dir),
        map_snapshotter=catalog.snapshot_navigation_map,
    )
    RUNTIME.navigation = NavigationCoordinator(
        RUNTIME.agent,
        navigation_manager,
        RUNTIME.mapping,
        catalog,
        coordination_lock=RUNTIME.pipeline_coordination_lock,
        require_lifecycle_idle=require_lifecycle_idle_application,
        logger=LOGGER,
    )
    RUNTIME.mission = MissionCoordinator(
        RUNTIME.navigation,
        catalog,
        Path(args.navigation_runtime_dir).expanduser().resolve() / "missions",
    )
    RUNTIME.lifecycle = LifecycleCoordinator.from_environment(
        control_snapshot_provider=RUNTIME.agent.control_snapshot,
        navigation_runtime_snapshot_provider=(
            RUNTIME.agent.navigation_runtime_snapshot
        ),
        navigation_jobs_snapshot_provider=RUNTIME.navigation.jobs.snapshot,
        mapping_jobs_snapshot_provider=RUNTIME.mapping.snapshot,
        mapping_task_active_provider=RUNTIME.mapping.task_active,
        navigation_start_snapshot_provider=(
            RUNTIME.navigation.internal_start_state
        ),
        dataset_capture_active_provider=RUNTIME.dataset_capture.is_active,
    )
    RUNTIME.operator_events = OperatorEventTimeline(
        Path(args.operator_event_dir).expanduser()
    )
    RUNTIME.diagnostics = DiagnosticsBundleService(
        project_dir=project_dir,
        profile_provider=lambda: RUNTIME.agent.profile if RUNTIME.agent else {},
        health_provider=RUNTIME.agent.health_snapshot,
        topics_provider=RUNTIME.agent.topics_snapshot,
        sources_provider=RUNTIME.agent.sources_snapshot,
        control_provider=RUNTIME.agent.control_snapshot,
        mapping_provider=RUNTIME.mapping.snapshot,
        navigation_provider=RUNTIME.navigation.view,
        navigation_events_provider=lambda: RUNTIME.navigation.progress_snapshot(
            after=0,
            limit=100,
        ),
        dataset_provider=RUNTIME.dataset_capture.snapshot,
        operator_events=RUNTIME.operator_events,
        disk_roots={
            "mapping_storage": mapping_output_dir,
            "dataset_storage": Path(args.dataset_output_dir).expanduser().resolve(),
        },
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
