"""Additive MR facade with fixed actions and existing origin/competition gates."""
from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response

from ..dependencies import require_same_origin, require_component, runtime_from_request, require_competition_unlocked
from ...application.mission_coordinator import MissionError
from ...mission_routes.models import CreateRequest, UpdateRequest, RevisionRequest, PreviewRequest, RunActionRequest, FixtureRunRequest
from ...mission_routes.competition_contract import capabilities, template_visits
from ...mission_routes.competition_assets import ARENA, arena_manifest, checked_file
from .missions import _error

router = APIRouter()


def service(request):
    return require_component(getattr(runtime_from_request(request), "mission_routes", None), "mission-route integration unavailable")


def write_gate(request):
    require_competition_unlocked(runtime_from_request(request), "mission-route mutation")


@router.get("/api/v1/mission-competition/capabilities")
async def competition_capabilities():
    return capabilities()


@router.get("/api/v1/mission-competition/arena")
async def competition_arena():
    return arena_manifest()


@router.get("/api/v1/mission-competition/arena/asset")
async def competition_arena_asset():
    try:
        data, sha = checked_file(ARENA, "arena.glb")
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "VM_ARENA_MISSING_OR_HASH_MISMATCH") from exc
    return Response(data, media_type="model/gltf-binary", headers={"ETag": '"' + sha + '"', "Cache-Control": "no-cache"})


@router.get("/api/v1/mission-competition/template")
async def competition_template():
    return template_visits()


@router.post("/api/v1/mission-plans/{identifier}/fixture-runs", status_code=201)
async def fixture_run(identifier: str, body: FixtureRunRequest, request: Request):
    require_same_origin(request)
    write_gate(request)
    try:
        return await service(request).create_fixture_run(identifier, body)
    except MissionError as exc:
        raise _error(exc) from exc


@router.get("/api/v1/mission-plans")
async def plans(request: Request):
    return service(request).definitions()


@router.post("/api/v1/mission-plans", status_code=201)
async def create(body: CreateRequest, request: Request):
    require_same_origin(request)
    write_gate(request)
    try:
        return await service(request).write(body)
    except MissionError as exc:
        raise _error(exc) from exc


@router.get("/api/v1/mission-plans/{identifier}")
async def detail(identifier: str, request: Request):
    try:
        return {"plan": service(request).definition(identifier)}
    except MissionError as exc:
        raise _error(exc) from exc


@router.patch("/api/v1/mission-plans/{identifier}")
async def update(identifier: str, body: UpdateRequest, request: Request):
    require_same_origin(request)
    write_gate(request)
    try:
        return await service(request).write(body, identifier=identifier)
    except MissionError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/mission-plans/{identifier}/copy", status_code=201)
async def copy_plan(identifier: str, body: RevisionRequest, request: Request):
    require_same_origin(request)
    write_gate(request)
    try:
        source = service(request).definition(identifier, body.revision)
        payload = CreateRequest.model_validate({**source["definition"], "request_id": body.request_id})
        return await service(request).write(payload, copy_from=identifier)
    except MissionError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/mission-plans/{identifier}/validate")
async def validate(identifier: str, body: RevisionRequest, request: Request):
    require_same_origin(request)
    try:
        import asyncio
        return await asyncio.to_thread(service(request).validate, identifier, body.revision)
    except MissionError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/mission-plans/{identifier}/plan-preview")
async def preview(identifier: str, body: PreviewRequest, request: Request):
    require_same_origin(request)
    try:
        return await service(request).preview(identifier, body)
    except MissionError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/mission-plans/{identifier}/compile")
async def compile_plan(identifier: str, body: RevisionRequest, request: Request):
    require_same_origin(request)
    write_gate(request)
    try:
        return await service(request).compile(identifier, body)
    except MissionError as exc:
        raise _error(exc) from exc


@router.get("/api/v1/mission-route-drafts/{route_id}")
async def route_draft(route_id: str, request: Request):
    try:
        return service(request).route_draft(route_id)
    except MissionError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/mission-plans/{identifier}/runs", status_code=201)
async def create_run(identifier: str, body: RevisionRequest, request: Request):
    require_same_origin(request)
    write_gate(request)
    try:
        return await service(request).create_run(identifier, body)
    except MissionError as exc:
        raise _error(exc) from exc


@router.get("/api/v1/mission-runs")
async def runs(request: Request):
    return service(request).runs()


@router.get("/api/v1/mission-runs/{identifier}")
async def run(identifier: str, request: Request):
    try:
        return service(request).run(identifier)
    except MissionError as exc:
        raise _error(exc) from exc


async def action(identifier, name, body, request):
    if name in {"start", "resume", "retry", "skip"}:
        require_competition_unlocked(runtime_from_request(request), "mission-route execution")
    try:
        return await service(request).action(identifier, name, body)
    except MissionError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/mission-runs/{identifier}/start")
async def start(identifier: str, body: RunActionRequest, request: Request):
    require_same_origin(request)
    return await action(identifier, "start", body, request)


@router.post("/api/v1/mission-runs/{identifier}/pause")
async def pause(identifier: str, body: RunActionRequest, request: Request):
    require_same_origin(request)
    return await action(identifier, "pause", body, request)


@router.post("/api/v1/mission-runs/{identifier}/resume")
async def resume(identifier: str, body: RunActionRequest, request: Request):
    require_same_origin(request)
    return await action(identifier, "resume", body, request)


@router.post("/api/v1/mission-runs/{identifier}/retry")
async def retry(identifier: str, body: RunActionRequest, request: Request):
    require_same_origin(request)
    return await action(identifier, "retry", body, request)


@router.post("/api/v1/mission-runs/{identifier}/skip")
async def skip(identifier: str, body: RunActionRequest, request: Request):
    require_same_origin(request)
    return await action(identifier, "skip", body, request)


@router.post("/api/v1/mission-runs/{identifier}/abort")
async def abort(identifier: str, body: RunActionRequest, request: Request):
    require_same_origin(request)
    return await action(identifier, "abort", body, request)


@router.get("/api/v1/mission-runs/{identifier}/export")
async def export_run(identifier: str, request: Request):
    try:
        return service(request).export_run(identifier)
    except MissionError as exc:
        raise _error(exc) from exc


@router.delete("/api/v1/mission-plans/{identifier}")
async def delete_definition(identifier: str, body: RevisionRequest, request: Request):
    require_same_origin(request)
    write_gate(request)
    try:
        return await service(request).delete_definition(identifier, body)
    except MissionError as exc:
        raise _error(exc) from exc
