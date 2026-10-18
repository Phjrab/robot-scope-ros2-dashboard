"""Stateless, single-flight numerical observation analysis; no ROS mutation."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from ...relocalization.observation_alignment import ObservationAligner, ObservationAlignmentError
from ...saved_maps import SavedMapError
from ..dependencies import require_component, require_same_origin, runtime_from_request

router = APIRouter()
Row = Annotated[list[float], Field(min_length=4, max_length=4)]


class ObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    map_id: str = Field(pattern=r"^[a-f0-9]{24}$")
    map_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    observer_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    cloud_epoch: str = Field(pattern=r"^[a-f0-9]{32}$")
    pose_epoch: str = Field(pattern=r"^[a-f0-9]{32}$")
    T_map_odom_seed: list[Row] = Field(min_length=4, max_length=4)


@router.post("/api/v1/observations/map-alignment")
async def estimate_observation(request: Request, body: ObservationRequest) -> dict:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    catalog = require_component(runtime.saved_maps, "saved maps unavailable")
    agent = require_component(runtime.agent, "observations unavailable")
    if runtime.observation_aligner is None:
        runtime.observation_aligner = ObservationAligner()
    try:
        return await run_in_threadpool(runtime.observation_aligner.estimate, catalog, agent, body.model_dump())
    except ObservationAlignmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SavedMapError as exc:
        raise HTTPException(status_code=409, detail="saved map changed or unavailable") from exc
