"""Selection transport; goal/STOP and ownership stay with existing coordinators."""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ...saved_maps import SavedMapError
from ...control import ControlError
from ...navigation_jobs import NavigationJobError
from ...application.runtime_health_sample import capture_runtime_health
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


class PairSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    map_id: str = Field(pattern=r'^[a-f0-9]{24}$')
    map_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    navigation_map_id: str = Field(pattern=r'^[a-f0-9]{24}$')
    navigation_map_revision: str = Field(pattern=r'^[a-f0-9]{64}$')


class Selection(PairSelection):
    seed_pose: SeedPose
    course_region: dict | None = None


class SeedGeometry(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True)
    generation: str = Field(pattern=r'^[a-f0-9]{32}$')
    z: float = Field(ge=-1000, le=1000)
    roll: float = Field(ge=-3.141592653589793, le=3.141592653589793)
    pitch: float = Field(ge=-1.5707963267948966, le=1.5707963267948966)


class InitializationProposalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$')
    bundle_generation: str = Field(pattern=r'^[a-f0-9]{32}$')
    observation_session_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class HandoffConfirmation(InitializationProposalRequest):
    confirmed: bool
    stationary_supervision_acknowledged: bool


def _proposal_owner(runtime):
    from ...application.navigation_initialization_proposal import NavigationInitializationProposals
    owner = getattr(runtime, '_navigation_initialization_proposals', None)
    if owner is None:
        owner = runtime._navigation_initialization_proposals = NavigationInitializationProposals(runtime)
    return owner


def health(runtime):
    return runtime.agent._navigation_runtime_health_snapshot(time.monotonic()) if runtime.agent else {}



@router.get('/api/v1/navigation/operational-3d')
async def status(request: Request):
    runtime = runtime_from_request(request)
    manager = require_component(runtime.operational_navigation, 'operational localization is not configured')
    state = await asyncio.to_thread(manager.status)
    current = health(runtime)
    return {**state, 'runtime': current.get('operational_3d'), 'runtime_fresh': current.get('fresh', False)}


@router.get('/api/v1/navigation/operational-3d/preparation-inputs')
async def preparation_inputs(request: Request, response: Response):
    from ...application.navigation_preparation_inputs import (
        observation_start_blockers, preparation_inputs as collect,
    )

    response.headers['Cache-Control'] = 'no-store'
    runtime = runtime_from_request(request)
    manager = require_component(runtime.operational_navigation, 'operational localization is not configured')
    async with runtime.pipeline_coordination_lock:
        blockers = await asyncio.to_thread(observation_start_blockers, runtime)
    result = await asyncio.to_thread(collect, manager, runtime.fastlio_observation, runtime.agent)
    result['start_blockers'] = blockers
    return result


@router.post('/api/v1/navigation/operational-3d/initialization-proposals', status_code=202)
async def start_initialization_proposal(body: InitializationProposalRequest, request: Request):
    from ...application.navigation_initialization_proposal import ProposalConflict, ProposalUnavailable

    require_same_origin(request)
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, 'initial localization proposal')
    require_manual_operation_mode(runtime)
    async with runtime.pipeline_coordination_lock:
        try:
            return await asyncio.to_thread(_proposal_owner(runtime).start, body.request_id,
                                           body.bundle_generation, body.observation_session_id)
        except ProposalConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ProposalUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc


@router.get('/api/v1/navigation/operational-3d/initialization-proposals/{proposal_id}')
async def get_initialization_proposal(proposal_id: str, request: Request, response: Response):
    from ...application.navigation_initialization_proposal import ProposalNotFound

    response.headers['Cache-Control'] = 'no-store'
    runtime = runtime_from_request(request)
    async with runtime.pipeline_coordination_lock:
        try:
            return await asyncio.to_thread(_proposal_owner(runtime).get, proposal_id)
        except ProposalNotFound as exc:
            raise HTTPException(404, str(exc)) from exc


@router.post('/api/v1/navigation/operational-3d/initialization-proposals/{proposal_id}/confirm-geometry')
async def confirm_proposal_geometry(proposal_id: str, body: HandoffConfirmation, request: Request):
    from ...application.navigation_initialization_proposal import ProposalNotFound, ProposalConflict, ProposalUnavailable
    require_same_origin(request)
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, 'initial geometry confirmation')
    require_manual_operation_mode(runtime)
    if body.confirmed is not True or body.stationary_supervision_acknowledged is not True:
        raise HTTPException(409, 'CONFIRMATION_REQUIRED')
    manager = require_component(runtime.operational_navigation, 'operational localization is not configured')
    observation = require_component(runtime.fastlio_observation, 'observation is not configured')
    async with runtime.pipeline_coordination_lock:
        try:
            return await asyncio.to_thread(manager.confirm_proposal, _proposal_owner(runtime), observation,
                proposal_id, body.request_id, body.bundle_generation, body.observation_session_id)
        except ProposalNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except ProposalUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except (ProposalConflict, ValueError, KeyError, OSError, SavedMapError) as exc:
            raise HTTPException(409, str(exc)) from exc


@router.get('/api/v1/navigation/operational-3d/initialization-handoffs/{handoff_id}')
async def get_initialization_handoff(handoff_id: str, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    runtime = runtime_from_request(request)
    manager = require_component(runtime.operational_navigation, 'operational localization is not configured')
    try:
        # Include any ensuing asset-validation and lock wait in health age.
        current_health = await asyncio.to_thread(capture_runtime_health, runtime.agent)
        return await asyncio.to_thread(manager.handoff_status, handoff_id, health=current_health)
    except KeyError as exc:
        raise HTTPException(404, 'HANDOFF_NOT_FOUND') from exc


async def select_idle(request, body, operation="select"):
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
        snapshot = await asyncio.to_thread(nav.view)
        if snapshot.get('localization_session', {}).get('active') or snapshot.get('session_mode', snapshot.get('mode')) == 'navigation':
            raise HTTPException(409, 'STOP_NAVIGATION_BEFORE_SOURCE_SELECTION')
        try:
            return await asyncio.to_thread(getattr(manager, operation), body)
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


@router.post('/api/v1/navigation/operational-3d/pair')
async def select_pair(body: PairSelection, request: Request):
    require_same_origin(request)
    return await select_idle(request, body.model_dump(), 'select_pair')


@router.post('/api/v1/navigation/operational-3d/seed-geometry')
async def seed_geometry(body: SeedGeometry, request: Request):
    require_same_origin(request)
    return await select_idle(request, body.model_dump(), 'seed_geometry')


class MatchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    map_id: str = Field(pattern=r'^[a-f0-9]{24}$')
    map_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    bundle_generation: str = Field(pattern=r'^[a-f0-9]{32}$')
    localization_generation: int = Field(ge=1, le=2**31 - 1)
    initial_pose_stamp_ns: str = Field(pattern=r'^[0-9]{1,19}$')


@router.post('/api/v1/navigation/operational-3d/match')
async def match(body: MatchRequest, request: Request):
    require_same_origin(request)
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, 'stored map initial matching')
    require_manual_operation_mode(runtime)
    nav = require_component(runtime.navigation, 'navigation is not configured')
    agent = require_component(runtime.agent, 'robot connection is not configured')
    async with runtime.pipeline_coordination_lock:
        if runtime.mission and runtime.mission.blocks_navigation_goal():
            raise HTTPException(409, 'MISSION_OWNS_NAVIGATION')
        if runtime.mapping and runtime.mapping.activity()[0]:
            raise HTTPException(409, 'MAPPING_TRANSITION_ACTIVE')
        if nav.start_task is not None and not nav.start_task.done():
            raise HTTPException(409, 'NAVIGATION_START_PENDING')
        snapshot = await asyncio.to_thread(nav.view)
        active_map = snapshot.get('map') or {}
        if (snapshot.get('pipeline', {}).get('state') != 'running'
                or active_map.get('id') != body.map_id
                or active_map.get('revision') != body.map_revision
                or snapshot.get('localization_session', {}).get('active')
                or snapshot.get('goal', {}).get('state') in {'pending', 'active', 'canceling'}):
            raise HTTPException(409, 'ACTIVE_NAVIGATION_CONTEXT_OR_STOP_REQUIRED')
        try:
            manager = getattr(runtime, 'operational_navigation', None)
            if manager is not None:
                await asyncio.to_thread(manager.check_match, body.bundle_generation, body.map_id, body.map_revision)
            receipt = await asyncio.to_thread(agent.navigation_start_operational_match, **body.model_dump())
            if manager is not None:
                try:
                    current_health = await asyncio.to_thread(capture_runtime_health, runtime.agent)
                    await asyncio.to_thread(manager.record_match_armed, body.bundle_generation, body.map_id, body.map_revision,
                                            receipt, current_health, expected_stamp=body.initial_pose_stamp_ns, allow_replace=True)
                except (ValueError, KeyError, TypeError):
                    pass  # Receipt was accepted; current status will be recovered from fresh health.
        except (ValueError, ControlError, NavigationJobError) as exc:
            raise HTTPException(409, str(exc)) from exc
    return {'accepted': True, 'receipt': receipt}
