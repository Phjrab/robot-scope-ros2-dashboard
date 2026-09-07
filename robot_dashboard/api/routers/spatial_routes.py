"""Path-free CRUD transport for non-executing spatial route artifacts."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from ...application.runtime import ApplicationRuntime
from ...spatial_routes import (
    SpatialRouteCatalog,
    SpatialRouteConflict,
    SpatialRouteError,
    SpatialRouteFormatError,
    SpatialRouteNotFound,
    SpatialRouteUnavailable,
)
from ..dependencies import (
    require_competition_unlocked,
    require_component,
    require_same_origin,
    runtime_from_request,
)
from ..models import (
    SpatialRouteCopyRequest,
    SpatialRouteCreateRequest,
    SpatialRouteUpdateRequest,
)


router = APIRouter()


def _catalog(runtime: ApplicationRuntime) -> SpatialRouteCatalog:
    return require_component(runtime.spatial_routes, "spatial routes are not configured")


def _error(exc: SpatialRouteError) -> HTTPException:
    if isinstance(exc, SpatialRouteNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, SpatialRouteConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, SpatialRouteFormatError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, SpatialRouteUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail="spatial route operation failed")


def _write_payload(body: SpatialRouteCreateRequest) -> dict[str, Any]:
    return {
        "label": body.label,
        "map_family": body.map_family.model_dump(),
        "authoring_source": body.authoring_source,
        "policy": body.policy.model_dump(),
        "poses": [pose.model_dump(exclude_none=True) for pose in body.poses],
    }


@router.get("/api/v1/routes")
async def spatial_route_list(request: Request) -> dict[str, Any]:
    return await asyncio.to_thread(_catalog(runtime_from_request(request)).list_snapshot)


@router.post("/api/v1/routes", status_code=201)
async def spatial_route_create(body: SpatialRouteCreateRequest, request: Request) -> dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, "spatial route revision creation")
    try:
        return await asyncio.to_thread(_catalog(runtime).create, **_write_payload(body))
    except SpatialRouteError as exc:
        raise _error(exc) from exc


@router.get("/api/v1/routes/{route_id}")
async def spatial_route_detail(route_id: str, request: Request) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_catalog(runtime_from_request(request)).detail, route_id)
    except SpatialRouteError as exc:
        raise _error(exc) from exc


@router.patch("/api/v1/routes/{route_id}")
async def spatial_route_update(route_id: str, body: SpatialRouteUpdateRequest, request: Request) -> dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, "spatial route revision update")
    try:
        return await asyncio.to_thread(
            _catalog(runtime).update,
            route_id,
            base_revision=body.base_revision,
            **_write_payload(body),
        )
    except SpatialRouteError as exc:
        raise _error(exc) from exc


@router.delete("/api/v1/routes/{route_id}")
async def spatial_route_delete(
    route_id: str,
    request: Request,
    base_revision: str = Query(pattern=r"^[0-9a-f]{64}$"),
) -> dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, "spatial route deletion")
    try:
        return await asyncio.to_thread(_catalog(runtime).delete, route_id, base_revision=base_revision)
    except SpatialRouteError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/routes/{route_id}/copy", status_code=201)
async def spatial_route_copy(route_id: str, body: SpatialRouteCopyRequest, request: Request) -> dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, "spatial route copy creation")
    try:
        return await asyncio.to_thread(
            _catalog(runtime).copy,
            route_id,
            base_revision=body.base_revision,
            label=body.label,
        )
    except SpatialRouteError as exc:
        raise _error(exc) from exc
