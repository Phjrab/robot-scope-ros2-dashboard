"""Read-only dashboard projection of the local model registry."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Request

from ...application.runtime import ApplicationRuntime
from ...model_registry import ModelRegistry
from ..dependencies import require_component, runtime_from_request


router = APIRouter()


def _registry(runtime: ApplicationRuntime) -> ModelRegistry:
    return require_component(runtime.model_registry, "model registry is not configured")


@router.get("/api/v1/models")
async def model_registry_list(request: Request) -> Dict[str, Any]:
    registry = _registry(runtime_from_request(request))
    return await asyncio.to_thread(registry.list_models)


@router.get("/api/v1/models/active")
async def model_registry_active(request: Request) -> Dict[str, Any]:
    registry = _registry(runtime_from_request(request))
    return await asyncio.to_thread(registry.active_snapshot)
