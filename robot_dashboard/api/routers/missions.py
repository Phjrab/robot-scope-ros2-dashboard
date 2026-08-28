"""Strict bounded mission HTTP transport routes."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from ...application.mission_coordinator import (
    MissionConflict,
    MissionCoordinator,
    MissionError,
    MissionNotFound,
    MissionUnavailable,
    MissionValidationError,
)
from ...application.runtime import ApplicationRuntime
from ..dependencies import require_component, require_same_origin, runtime_from_request
from ..models import MissionActionRequest, MissionCreateRequest


router = APIRouter()


def _coordinator(runtime: ApplicationRuntime) -> MissionCoordinator:
    return require_component(runtime.mission, "missions are not configured")


def _error(exc: MissionError) -> HTTPException:
    if isinstance(exc, MissionNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, MissionConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, MissionValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, MissionUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail="mission operation failed")


@router.get("/api/v1/missions")
async def mission_list(request: Request) -> Dict[str, Any]:
    return _coordinator(runtime_from_request(request)).snapshot()


@router.post("/api/v1/missions", status_code=201)
async def mission_create(body: MissionCreateRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    try:
        return await _coordinator(runtime_from_request(request)).create(
            label=body.label,
            map_id=body.map_id,
            map_revision=body.map_revision,
            annotation_revision=body.annotation_revision,
            waypoints=[waypoint.model_dump() for waypoint in body.waypoints],
        )
    except MissionError as exc:
        raise _error(exc) from exc


@router.get("/api/v1/missions/{mission_id}")
async def mission_detail(mission_id: str, request: Request) -> Dict[str, Any]:
    try:
        return _coordinator(runtime_from_request(request)).snapshot(mission_id)
    except MissionError as exc:
        raise _error(exc) from exc


async def _action(mission_id: str, action: str, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    coordinator = _coordinator(runtime_from_request(request))
    try:
        return await getattr(coordinator, action)(mission_id)
    except MissionError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/missions/{mission_id}/start", status_code=202)
async def mission_start(mission_id: str, body: MissionActionRequest, request: Request) -> Dict[str, Any]:
    del body
    require_same_origin(request)
    return await _action(mission_id, "start", request)


@router.post("/api/v1/missions/{mission_id}/pause")
async def mission_pause(mission_id: str, body: MissionActionRequest, request: Request) -> Dict[str, Any]:
    del body
    require_same_origin(request)
    return await _action(mission_id, "pause", request)


@router.post("/api/v1/missions/{mission_id}/resume")
async def mission_resume(mission_id: str, body: MissionActionRequest, request: Request) -> Dict[str, Any]:
    del body
    require_same_origin(request)
    return await _action(mission_id, "resume", request)


@router.post("/api/v1/missions/{mission_id}/skip")
async def mission_skip(mission_id: str, body: MissionActionRequest, request: Request) -> Dict[str, Any]:
    del body
    require_same_origin(request)
    return await _action(mission_id, "skip", request)


@router.post("/api/v1/missions/{mission_id}/retry")
async def mission_retry(mission_id: str, body: MissionActionRequest, request: Request) -> Dict[str, Any]:
    del body
    require_same_origin(request)
    return await _action(mission_id, "retry", request)


@router.post("/api/v1/missions/{mission_id}/abort")
async def mission_abort(mission_id: str, body: MissionActionRequest, request: Request) -> Dict[str, Any]:
    del body
    require_same_origin(request)
    return await _action(mission_id, "abort", request)
