"""Same-origin controls for the fixed, observation-only FAST-LIO service."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from ...application.fastlio_observation import ObservationSessionConflict
from ...application.lifecycle_coordinator import LifecycleTransitionBusy
from ...observation_service import ObservationServiceError
from ..dependencies import (
    require_component,
    require_competition_unlocked,
    require_same_origin,
    runtime_from_request,
)

router = APIRouter()


class StartObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: StrictBool


class StopObservation(StartObservation):
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")


def owner(request):
    runtime = runtime_from_request(request)
    return require_component(
        runtime.fastlio_observation, "관측 서비스가 구성되지 않았습니다."
    )


@router.get("/api/v1/observations/fastlio")
async def observation_status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return owner(request).snapshot()


@router.post("/api/v1/observations/fastlio/start", status_code=202)
async def start_observation(request: Request, body: StartObservation):
    require_same_origin(request)
    require_competition_unlocked(runtime_from_request(request), "observation start")
    if body.confirmed is not True:
        raise HTTPException(400, "관측 시작 확인이 필요합니다.")
    try:
        return await owner(request).start()
    except (ObservationSessionConflict, LifecycleTransitionBusy) as exc:
        raise HTTPException(409, str(exc)) from exc
    except ObservationServiceError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/api/v1/observations/fastlio/stop", status_code=202)
async def stop_observation(request: Request, body: StopObservation):
    require_same_origin(request)
    # Stopping this exact observation session remains available during interlocks.
    if body.confirmed is not True:
        raise HTTPException(400, "관측 종료 확인이 필요합니다.")
    try:
        return await owner(request).stop(body.session_id)
    except ObservationSessionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ObservationServiceError as exc:
        raise HTTPException(503, str(exc)) from exc
