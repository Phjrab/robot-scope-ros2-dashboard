"""Bounded HTTP projection for stationary relocalization candidate jobs."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from ...application.runtime import ApplicationRuntime
from ...relocalization.manager import (
    RelocalizationBusy,
    RelocalizationConflict,
    RelocalizationError,
    RelocalizationNotFound,
    RelocalizationUnavailable,
    RelocalizationValidationError,
    StationaryRelocalizationManager,
)
from ..dependencies import (
    require_competition_unlocked,
    require_component,
    require_same_origin,
    runtime_from_request,
)
from ..models import RelocalizationCancelRequest, RelocalizationStartRequest


def _manager(runtime: ApplicationRuntime) -> StationaryRelocalizationManager:
    return require_component(runtime.relocalization, "relocalization is not configured")


def _error(exc: RelocalizationError) -> HTTPException:
    if isinstance(exc, RelocalizationNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (RelocalizationBusy, RelocalizationConflict)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, RelocalizationValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, RelocalizationUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail="relocalization operation failed")


router = APIRouter()


@router.get("/api/v1/relocalization")
async def relocalization_status(request: Request) -> dict[str, Any]:
    return await asyncio.to_thread(_manager(runtime_from_request(request)).snapshot)


@router.post("/api/v1/relocalization/jobs", status_code=202)
async def relocalization_start(
    body: RelocalizationStartRequest,
    request: Request,
) -> dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, "start stationary relocalization")
    async with runtime.pipeline_coordination_lock:
        try:
            return await asyncio.to_thread(
                _manager(runtime).start,
                body.model_dump(mode="python"),
            )
        except RelocalizationError as exc:
            raise _error(exc) from exc


@router.get("/api/v1/relocalization/{job_id}")
async def relocalization_job(job_id: str, request: Request) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_manager(runtime_from_request(request)).job, job_id)
    except RelocalizationError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/relocalization/{job_id}/cancel")
async def relocalization_cancel(
    job_id: str,
    body: RelocalizationCancelRequest,
    request: Request,
) -> dict[str, Any]:
    del body
    require_same_origin(request)
    runtime = runtime_from_request(request)
    async with runtime.pipeline_coordination_lock:
        try:
            return await asyncio.to_thread(_manager(runtime).cancel, job_id)
        except RelocalizationError as exc:
            raise _error(exc) from exc


@router.get("/api/v1/relocalization/{job_id}/preview")
async def relocalization_preview(
    job_id: str,
    request: Request,
    layer: str = Query(pattern=r"^(reference|current|aligned)$"),
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            _manager(runtime_from_request(request)).preview,
            job_id,
            layer,
        )
    except RelocalizationError as exc:
        raise _error(exc) from exc
