"""Team preset storage only: no pipeline, goal or live-parameter mutations."""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ...navigation_jobs import NavigationParameterError
from ...navigation_presets import PresetConflict, PresetInvalid, PresetUnavailable
from ..dependencies import require_component, require_same_origin, runtime_from_request
from ..models import NavigationPresetCreateRequest

router = APIRouter()


@router.get("/api/v1/navigation/presets")
async def navigation_presets(request: Request) -> dict[str, Any]:
    navigation = require_component(runtime_from_request(request).navigation, "navigation is not configured")
    try:
        return await asyncio.to_thread(navigation.saved_presets)
    except PresetUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/v1/navigation/presets", status_code=201)
async def navigation_preset_create(body: NavigationPresetCreateRequest, request: Request) -> dict[str, Any]:
    require_same_origin(request)
    navigation = require_component(runtime_from_request(request).navigation, "navigation is not configured")
    try:
        return await asyncio.to_thread(navigation.create_preset, body.name, body.values)
    except (PresetInvalid, NavigationParameterError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PresetConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PresetUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
