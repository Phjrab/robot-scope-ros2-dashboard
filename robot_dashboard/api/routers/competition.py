"""Competition Cockpit operation state and lock HTTP transport."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from ...application.runtime import ApplicationRuntime
from ...competition import (
    CompetitionConfirmationRequired,
    CompetitionConflict,
    CompetitionError,
    CompetitionStateManager,
    CompetitionUnavailable,
)
from ..dependencies import require_component, require_same_origin, runtime_from_request
from ..models import CompetitionLockRequest, CompetitionModeRequest, CompetitionUnlockRequest


router = APIRouter()


def _manager(runtime: ApplicationRuntime) -> CompetitionStateManager:
    return require_component(runtime.competition, "competition state is not configured")


def _error(exc: CompetitionError) -> HTTPException:
    if isinstance(exc, CompetitionConfirmationRequired):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, CompetitionConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, CompetitionUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail="competition state operation failed")


@router.get("/api/v1/competition")
async def competition_status(request: Request) -> Dict[str, Any]:
    return await asyncio.to_thread(_manager(runtime_from_request(request)).snapshot)


@router.post("/api/v1/competition/lock")
async def competition_lock(request: Request, body: CompetitionLockRequest) -> Dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    async with runtime.pipeline_coordination_lock:
        try:
            return await asyncio.to_thread(_manager(runtime).lock, body.confirmation)
        except CompetitionError as exc:
            raise _error(exc) from exc


@router.post("/api/v1/competition/unlock")
async def competition_unlock(request: Request, body: CompetitionUnlockRequest) -> Dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    async with runtime.pipeline_coordination_lock:
        try:
            return await asyncio.to_thread(
                _manager(runtime).unlock,
                body.confirmation,
                stationary_confirmed=body.stationary_confirmed,
            )
        except CompetitionError as exc:
            raise _error(exc) from exc


@router.post("/api/v1/competition/mode")
async def competition_mode(request: Request, body: CompetitionModeRequest) -> Dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    async with runtime.pipeline_coordination_lock:
        try:
            return await asyncio.to_thread(
                _manager(runtime).set_mode,
                body.mode,
                body.confirmation,
            )
        except CompetitionError as exc:
            raise _error(exc) from exc
