"""Strict bounded HTTP transport for the Competition Route Planner."""

from __future__ import annotations

from typing import Any, Dict, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ...application.route_planner_coordinator import (
    RoutePlannerConflict,
    RoutePlannerCoordinator,
    RoutePlannerError,
    RoutePlannerNotFound,
    RoutePlannerUnavailable,
    RoutePlannerValidationError,
)
from ...application.runtime import ApplicationRuntime
from ..dependencies import require_competition_unlocked, require_component, require_same_origin, runtime_from_request
from ..models import (
    RouteGraphPutRequest,
    RouteDropoffRequest,
    RouteGuidanceStartRequest,
    RouteGuidanceStopRequest,
    RouteMissionExportRequest,
    RouteOrderCreateRequest,
    RouteOrderUpdateRequest,
    RoutePickupRequest,
    RouteRecommendationRequest,
    RouteSelectionRequest,
)


router = APIRouter()


class RehearsalStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    route_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")


class RehearsalControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal[
        "RESET",
        "PLAY",
        "PAUSE",
        "STEP",
        "SCRUB",
        "SET_SPEED",
        "OFF_ROUTE",
        "CONFIRM_PICKUP",
        "CONFIRM_DROPOFF",
        "EXIT",
    ]
    speed: Literal[0.5, 1.0, 2.0, 5.0] | None = None
    position_ms: int | None = Field(default=None, strict=True, ge=0, le=3_600_000)
    enabled: bool | None = Field(default=None, strict=True)
    venue_id: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    destination_id: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")


def _coordinator(runtime: ApplicationRuntime) -> RoutePlannerCoordinator:
    return require_component(runtime.route_planner, "route planner is not configured")


def _error(exc: RoutePlannerError) -> HTTPException:
    if isinstance(exc, RoutePlannerNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, RoutePlannerConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, RoutePlannerValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, RoutePlannerUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail="route planner operation failed")


def _mutation(request: Request, action: str) -> tuple[ApplicationRuntime, RoutePlannerCoordinator]:
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, action)
    return runtime, _coordinator(runtime)


@router.get("/api/v1/route-planner")
async def route_planner_status(request: Request) -> Dict[str, Any]:
    return _coordinator(runtime_from_request(request)).snapshot()


@router.get("/api/v1/route-planner/catalog")
async def route_planner_catalog(request: Request) -> Dict[str, Any]:
    return _coordinator(runtime_from_request(request)).catalog()


@router.post("/api/v1/route-planner/orders", status_code=201)
async def route_order_create(body: RouteOrderCreateRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    _, coordinator = _mutation(request, "route planner order creation")
    try:
        return await coordinator.create_order(body.model_dump())
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.patch("/api/v1/route-planner/orders/{order_id}")
async def route_order_update(order_id: str, body: RouteOrderUpdateRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    _, coordinator = _mutation(request, "route planner order update")
    payload = body.model_dump()
    base_revision = payload.pop("base_revision")
    try:
        return await coordinator.update_order(order_id, base_revision=base_revision, payload=payload)
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.get("/api/v1/route-planner/orders/{order_id}")
async def route_order_detail(order_id: str, request: Request) -> Dict[str, Any]:
    try:
        return _coordinator(runtime_from_request(request)).order(order_id)
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.get("/api/v1/route-planner/graph")
async def route_graph_detail(request: Request) -> Dict[str, Any]:
    return _coordinator(runtime_from_request(request)).graph()


@router.put("/api/v1/route-planner/graph")
async def route_graph_put(body: RouteGraphPutRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    _, coordinator = _mutation(request, "route planner graph update")
    payload = body.model_dump(by_alias=True)
    base_revision = payload.pop("base_graph_revision")
    try:
        return await coordinator.put_graph(payload, base_graph_revision=base_revision)
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/route-planner/recommendations")
async def route_recommendations(body: RouteRecommendationRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    _, coordinator = _mutation(request, "route recommendation")
    try:
        return await coordinator.recommendations(**body.model_dump())
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.get("/api/v1/route-planner/recommendations/{route_id}")
async def route_recommendation_detail(route_id: str, request: Request) -> Dict[str, Any]:
    coordinator = _coordinator(runtime_from_request(request))
    try:
        return coordinator.recommendation(route_id)
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/route-planner/recommendations/{route_id}/select")
async def route_recommendation_select(route_id: str, body: RouteSelectionRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    _, coordinator = _mutation(request, "route selection")
    try:
        return await coordinator.select(route_id, route_revision=body.route_revision)
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/route-planner/guidance/start")
async def route_guidance_start(body: RouteGuidanceStartRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    _, coordinator = _mutation(request, "manual route guidance start")
    try:
        return await coordinator.start_guidance(**body.model_dump())
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/route-planner/guidance/stop")
async def route_guidance_stop(body: RouteGuidanceStopRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    del body
    _, coordinator = _mutation(request, "manual route guidance stop")
    try:
        return await coordinator.stop_guidance()
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/route-planner/guidance/pickup")
async def route_guidance_pickup(body: RoutePickupRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    _, coordinator = _mutation(request, "manual pickup confirmation")
    try:
        return await coordinator.mark_pickup(body.venue_id)
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/route-planner/guidance/dropoff")
async def route_guidance_dropoff(body: RouteDropoffRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    _, coordinator = _mutation(request, "manual dropoff confirmation")
    try:
        return await coordinator.mark_dropoff(body.destination_id)
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/route-planner/routes/{route_id}/preview")
async def route_preview(route_id: str, body: RouteSelectionRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    _, coordinator = _mutation(request, "route preview")
    try:
        preview = coordinator.preview(route_id)
        if preview["route_revision"] != body.route_revision:
            raise RoutePlannerConflict("route revision changed")
        return preview
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.get("/api/v1/route-planner/rehearsal/scenarios")
async def route_rehearsal_scenarios(request: Request) -> Dict[str, Any]:
    try:
        return _coordinator(runtime_from_request(request)).rehearsal_scenarios()
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/route-planner/rehearsal/start")
async def route_rehearsal_start(body: RehearsalStartRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    _, coordinator = _mutation(request, "route planner rehearsal start")
    try:
        return await coordinator.begin_rehearsal(**body.model_dump())
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/route-planner/rehearsal/control")
async def route_rehearsal_control(body: RehearsalControlRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    _, coordinator = _mutation(request, "route planner rehearsal control")
    values = body.model_dump(exclude_none=True)
    action = values.pop("action")
    try:
        return await coordinator.control_rehearsal(action=action, payload=values)
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.get("/api/v1/route-planner/rehearsal/report")
async def route_rehearsal_report(request: Request) -> Dict[str, Any]:
    try:
        return _coordinator(runtime_from_request(request)).rehearsal_report()
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/route-planner/routes/{route_id}/mission-dry-run")
async def route_mission_dry_run(route_id: str, body: RouteSelectionRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    _, coordinator = _mutation(request, "route mission dry-run")
    try:
        return coordinator.mission_dry_run(route_id, route_revision=body.route_revision)
    except RoutePlannerError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/route-planner/routes/{route_id}/export-mission", status_code=201)
async def route_export_mission(route_id: str, body: RouteMissionExportRequest, request: Request) -> Dict[str, Any]:
    require_same_origin(request)
    _, coordinator = _mutation(request, "route mission draft export")
    try:
        return await coordinator.export_mission(route_id, route_revision=body.route_revision)
    except RoutePlannerError as exc:
        raise _error(exc) from exc
