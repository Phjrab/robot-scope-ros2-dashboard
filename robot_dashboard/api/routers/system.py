"""Fixed dashboard and control-bridge lifecycle HTTP transport."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from ...application.lifecycle_coordinator import LifecycleCoordinator
from ...application.runtime import ApplicationRuntime
from ...control_bridge_lifecycle import (
    ControlBridgeLifecycleBlocked,
    ControlBridgeLifecycleBusy,
    ControlBridgeLifecycleConfirmationRequired,
    ControlBridgeLifecycleError,
    ControlBridgeLifecycleUnavailable,
)
from ...service_lifecycle import (
    ServiceLifecycleBlocked,
    ServiceLifecycleBusy,
    ServiceLifecycleConfirmationRequired,
    ServiceLifecycleError,
    ServiceLifecycleUnavailable,
)
from ..dependencies import require_component, require_same_origin, runtime_from_request
from ..models import ControlBridgeLifecycleRequest, ServiceLifecycleRequest


router = APIRouter()


def _service(runtime: ApplicationRuntime) -> LifecycleCoordinator:
    return require_component(
        runtime.lifecycle,
        "service lifecycle control is not configured",
    )


def _bridge(runtime: ApplicationRuntime) -> LifecycleCoordinator:
    return require_component(
        runtime.lifecycle,
        "control bridge service lifecycle is not configured",
    )


def _service_error(exc: ServiceLifecycleError) -> HTTPException:
    if isinstance(exc, ServiceLifecycleBlocked):
        return HTTPException(
            status_code=409,
            detail={"code": "service_lifecycle_blocked", "blockers": list(exc.blockers)},
        )
    if isinstance(exc, ServiceLifecycleBusy):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ServiceLifecycleConfirmationRequired):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ServiceLifecycleUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail="service lifecycle operation failed")


def _bridge_error(exc: ControlBridgeLifecycleError) -> HTTPException:
    if isinstance(exc, ControlBridgeLifecycleBlocked):
        return HTTPException(
            status_code=409,
            detail={
                "code": "control_bridge_service_blocked",
                "action": exc.action,
                "blockers": list(exc.blockers),
            },
        )
    if isinstance(exc, ControlBridgeLifecycleBusy):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ControlBridgeLifecycleConfirmationRequired):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ControlBridgeLifecycleUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(
        status_code=500,
        detail="control bridge service lifecycle operation failed",
    )


@router.get("/api/v1/system/service")
async def service_lifecycle_status(request: Request) -> Dict[str, Any]:
    runtime = runtime_from_request(request)
    return await asyncio.to_thread(_service(runtime).service_snapshot)


@router.post("/api/v1/system/service/restart", status_code=202)
async def service_lifecycle_restart(
    request: Request,
    body: ServiceLifecycleRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    async with runtime.pipeline_coordination_lock:
        try:
            return await asyncio.to_thread(
                _service(runtime).schedule_service_restart,
                confirmed=body.confirmed,
            )
        except ServiceLifecycleError as exc:
            raise _service_error(exc) from exc


@router.post("/api/v1/system/service/stop", status_code=202)
async def service_lifecycle_stop(
    request: Request,
    body: ServiceLifecycleRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    async with runtime.pipeline_coordination_lock:
        try:
            return await asyncio.to_thread(
                _service(runtime).schedule_service_stop,
                confirmed=body.confirmed,
            )
        except ServiceLifecycleError as exc:
            raise _service_error(exc) from exc


@router.get("/api/v1/control/bridge-service")
async def control_bridge_lifecycle_status(request: Request) -> Dict[str, Any]:
    runtime = runtime_from_request(request)
    return await asyncio.to_thread(_bridge(runtime).control_bridge_snapshot)


@router.post("/api/v1/control/bridge-service/start", status_code=202)
async def control_bridge_lifecycle_start(
    request: Request,
    body: ControlBridgeLifecycleRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    async with runtime.pipeline_coordination_lock:
        try:
            return await asyncio.to_thread(
                _bridge(runtime).schedule_control_bridge_start,
                confirmed=body.confirmed,
            )
        except ControlBridgeLifecycleError as exc:
            raise _bridge_error(exc) from exc


@router.post("/api/v1/control/bridge-service/stop", status_code=202)
async def control_bridge_lifecycle_stop(
    request: Request,
    body: ControlBridgeLifecycleRequest,
) -> Dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    async with runtime.pipeline_coordination_lock:
        try:
            return await asyncio.to_thread(
                _bridge(runtime).schedule_control_bridge_stop,
                confirmed=body.confirmed,
            )
        except ControlBridgeLifecycleError as exc:
            raise _bridge_error(exc) from exc
