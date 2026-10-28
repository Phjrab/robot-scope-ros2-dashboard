"""Selection transport; goal/STOP and ownership stay with existing coordinators."""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ...saved_maps import SavedMapError
from ..dependencies import require_component, require_competition_unlocked, require_manual_operation_mode, require_same_origin, runtime_from_request

router = APIRouter()


class SeedPose(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True)
    x: float = Field(ge=-1000, le=1000)
    y: float = Field(ge=-1000, le=1000)
    z: float = Field(ge=-1000, le=1000)
    roll: float = Field(ge=-3.141593, le=3.141593)
    pitch: float = Field(ge=-1.570797, le=1.570797)
    yaw: float = Field(ge=-3.141593, le=3.141593)


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    map_id: str = Field(pattern=r'^[a-f0-9]{24}$')
    map_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    navigation_map_id: str = Field(pattern=r'^[a-f0-9]{24}$')
    navigation_map_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    seed_pose: SeedPose
    course_region: dict | None = None


def health(runtime):
    return runtime.agent._navigation_runtime_health_snapshot(time.monotonic()) if runtime.agent else {}


@router.get('/api/v1/navigation/operational-3d')
async def status(request: Request):
    runtime = runtime_from_request(request)
    manager = require_component(runtime.operational_navigation, 'operational localization is not configured')
    state = await asyncio.to_thread(manager.status)
    current = health(runtime)
    return {**state, 'runtime': current.get('operational_3d'), 'runtime_fresh': current.get('fresh', False)}


async def select_idle(request, body):
    require_same_origin(request)
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, '3D localization source selection')
    require_manual_operation_mode(runtime)
    manager = require_component(runtime.operational_navigation, 'operational localization is not configured')
    nav = require_component(runtime.navigation, 'navigation is not configured')
    async with runtime.pipeline_coordination_lock:
        if nav.start_task is not None and not nav.start_task.done():
            raise HTTPException(409, 'NAVIGATION_START_PENDING')
        if runtime.mission and runtime.mission.blocks_navigation_goal():
            raise HTTPException(409, 'MISSION_OWNS_NAVIGATION')
        if runtime.mapping and runtime.mapping.activity()[0]:
            raise HTTPException(409, 'MAPPING_TRANSITION_ACTIVE')
        snapshot = nav.view()
        if snapshot.get('localization_session', {}).get('active') or snapshot.get('mode') == 'navigation':
            raise HTTPException(409, 'STOP_NAVIGATION_BEFORE_SOURCE_SELECTION')
        try:
            return await asyncio.to_thread(manager.select, body)
        except (ValueError, KeyError, SavedMapError) as exc:
            raise HTTPException(409, str(exc)) from exc


@router.post('/api/v1/navigation/operational-3d')
async def select(body: Selection, request: Request):
    require_same_origin(request)
    return await select_idle(request, body.model_dump(exclude_none=True))


@router.delete('/api/v1/navigation/operational-3d')
async def clear(request: Request):
    require_same_origin(request)
    return await select_idle(request, {})
