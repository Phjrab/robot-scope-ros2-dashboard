"""Read-only bounded shadow-perception projections."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Query, Request

from ...application.runtime import ApplicationRuntime
from ...perception import PerceptionBridgeClient
from ..dependencies import require_component, runtime_from_request


router = APIRouter()


def _component(runtime: ApplicationRuntime) -> PerceptionBridgeClient:
    return require_component(runtime.perception, "shadow perception receiver is not configured")


@router.get("/api/v1/perception/health")
async def perception_health(request: Request) -> Dict[str, Any]:
    component = _component(runtime_from_request(request))
    return await asyncio.to_thread(component.store.health_snapshot)


@router.get("/api/v1/perception/latest")
async def perception_latest(request: Request) -> Dict[str, Any]:
    component = _component(runtime_from_request(request))
    return await asyncio.to_thread(component.store.latest_snapshot)


@router.get("/api/v1/perception/history")
async def perception_history(
    request: Request,
    limit: int = Query(default=50, ge=1, le=120),
) -> Dict[str, Any]:
    component = _component(runtime_from_request(request))
    return await asyncio.to_thread(component.store.history_snapshot, limit)
