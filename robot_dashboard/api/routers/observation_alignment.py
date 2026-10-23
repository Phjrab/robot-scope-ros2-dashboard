"""Stateless, single-flight numerical observation analysis; no ROS mutation."""
from __future__ import annotations

from typing import Annotated, Literal
import json
import logging
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from ...relocalization.observation_timing import ObservationTiming, measure, note

from ...relocalization.observation_alignment import ObservationAligner, ObservationAlignmentError
from ...saved_maps import SavedMapError
from ..dependencies import require_component, require_same_origin, runtime_from_request

router = APIRouter()
LOGGER = logging.getLogger("uvicorn.error.observation")
Row = Annotated[list[float], Field(min_length=4, max_length=4)]


class ObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    map_id: str = Field(pattern=r"^[a-f0-9]{24}$")
    map_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    observer_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    cloud_epoch: str = Field(pattern=r"^[a-f0-9]{32}$")
    pose_epoch: str = Field(pattern=r"^[a-f0-9]{32}$")
    T_map_odom_seed: list[Row] = Field(min_length=4, max_length=4)
    provenance_mode: Literal["native_publisher", "subscription_observation"] = "native_publisher"
    capture_inputs: StrictBool = False


@router.post("/api/v1/observations/map-alignment")
async def estimate_observation(request: Request, body: ObservationRequest) -> JSONResponse:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    catalog = require_component(runtime.saved_maps, "saved maps unavailable")
    agent = require_component(runtime.agent, "observations unavailable")
    if runtime.observation_aligner is None:
        runtime.observation_aligner = ObservationAligner(isolated=True)
    trace = ObservationTiming()
    def worker():
        with trace.bind():
            # Includes AnyIO dispatch, thread scheduling and GIL delay, not just queueing.
            note("dispatch_to_worker_ms", (time.monotonic() - trace.started) * 1000)
            with measure("worker"):
                return runtime.observation_aligner.estimate(catalog, agent, body.model_dump())
    status = 200
    try:
        payload = await run_in_threadpool(worker)
    except ObservationAlignmentError as exc:
        status, payload = 409, {"detail": str(exc)}
    except SavedMapError:
        status, payload = 409, {"detail": "saved map changed or unavailable"}
    except Exception:
        LOGGER.info("observation_timing %s", json.dumps(dict(trace.summary(), http_status=500)))
        raise
    with trace.bind(), measure("serialization"):
        # The opt-in reference array can be ~3.2 MiB; keep its JSON encoding
        # off the event loop that serves live pose/cloud WebSockets.
        if body.capture_inputs:
            response = await run_in_threadpool(JSONResponse, payload, status_code=status)
        else:
            response = JSONResponse(payload, status_code=status)
    # Fixed-size aggregate only; no inputs, coordinates, tokens or source identifiers.
    LOGGER.info("observation_timing %s", json.dumps(dict(trace.summary(), http_status=status)))
    return response
