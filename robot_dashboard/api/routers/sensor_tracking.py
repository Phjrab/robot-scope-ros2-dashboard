"""Explicit observation-only sensor tracking; never issues ROS control writes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from ...application.sensor_tracking import (
    SensorTrackingConflict, SensorTrackingNotFound, SensorTrackingUnavailable,
    SensorTrackingValidation,
)
from ..dependencies import require_same_origin, runtime_from_request


router = APIRouter()


class SensorTrackingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    global_job_id: str = Field(pattern=r"^[a-f0-9]{24}$")
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _owner(request: Request):
    owner = runtime_from_request(request).sensor_tracking
    if owner is None:
        raise HTTPException(status_code=503, detail="SENSOR_TRACKING_UNAVAILABLE")
    return owner


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, SensorTrackingNotFound):
        status = 404
    elif isinstance(exc, SensorTrackingValidation):
        status = 422
    elif isinstance(exc, SensorTrackingUnavailable):
        status = 503
    else:
        status = 409
    return HTTPException(status_code=status, detail=str(exc))


_ERRORS = (SensorTrackingConflict, SensorTrackingNotFound,
           SensorTrackingUnavailable, SensorTrackingValidation)


@router.get("/api/v1/observations/sensor-tracking")
async def sensor_tracking_status(request: Request) -> JSONResponse:
    owner = runtime_from_request(request).sensor_tracking
    if owner is None:
        return JSONResponse({"schema": "robot-scope.sensor-tracking.v1",
            "state": "WAITING_GLOBAL", "reason": "SENSOR_TRACKING_UNAVAILABLE",
            "generation": 0, "worker_active": False, "source_global_job": None,
            "map": None, "source": None, "sensor_pose": None, "trail": [],
            "ambiguity_override": None, "ambiguity_source": None, "last_alignment": None,
            "estimate_label": "UNVERIFIED_SENSOR_ESTIMATE",
            "temporal_consistency_confirmed": False, "globally_verified": False,
            "body_pose": None, "tracking_verified": False,
            "source_clock_verified": False, "body_extrinsic_verified": False,
            "operational_application": "NOT_RUN"})
    return JSONResponse(owner.snapshot())


@router.post("/api/v1/observations/sensor-tracking")
async def start_sensor_tracking(request: Request, body: SensorTrackingRequest) -> JSONResponse:
    require_same_origin(request)
    try:
        value = await run_in_threadpool(_owner(request).start, **body.model_dump())
    except _ERRORS as exc:
        raise _error(exc) from exc
    return JSONResponse(value, status_code=202)


@router.post("/api/v1/observations/sensor-tracking/stop")
async def stop_sensor_tracking(request: Request) -> JSONResponse:
    require_same_origin(request)
    try:
        value = await run_in_threadpool(_owner(request).stop)
    except _ERRORS as exc:
        raise _error(exc) from exc
    return JSONResponse(value)
