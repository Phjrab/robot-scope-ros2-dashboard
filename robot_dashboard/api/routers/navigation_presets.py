"""Team preset storage only: no pipeline, goal or live-parameter mutations."""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ...navigation_jobs import NavigationParameterError
from ...navigation_presets import PresetConflict, PresetInvalid, PresetNotFound, PresetUnavailable
from ..dependencies import require_component, require_same_origin, runtime_from_request
from ..models import NavigationPresetCreateRequest, NavigationPresetUpdateRequest

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


@router.patch("/api/v1/navigation/presets/{preset_id}")
async def navigation_preset_update(preset_id: str, body: NavigationPresetUpdateRequest, request: Request) -> dict[str, Any]:
    require_same_origin(request)
    navigation = require_component(runtime_from_request(request).navigation, "navigation is not configured")
    try:
        return await asyncio.to_thread(navigation.update_preset, preset_id, body.base_revision, body.values)
    except PresetNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PresetInvalid, NavigationParameterError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PresetConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PresetUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
