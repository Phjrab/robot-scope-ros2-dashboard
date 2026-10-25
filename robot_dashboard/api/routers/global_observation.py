"""Cancellable historical raw global observations; no operational ROS writes."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from ...relocalization.global_observation_jobs import (
    GlobalObservationBusy, GlobalObservationConflict, GlobalObservationNotFound,
    GlobalObservationUnavailable, GlobalObservationValidationError,
)
from ..dependencies import require_same_origin, runtime_from_request


router = APIRouter()


class GlobalObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    map_id: str = Field(pattern=r"^[a-f0-9]{24}$")
    map_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_kind: Literal["raw", "fastlio_imu"] = "raw"
    provenance_mode: Literal["native_publisher", "subscription_observation"] = "native_publisher"


def _owner(request: Request) -> Any:
    owner = runtime_from_request(request).global_observation
    if owner is None:
        raise HTTPException(status_code=503, detail="TRUSTED_LOCAL_RUNNER_UNAVAILABLE")
    return owner


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, GlobalObservationNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, GlobalObservationUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, GlobalObservationValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


_ERRORS = (GlobalObservationBusy, GlobalObservationConflict, GlobalObservationNotFound,
           GlobalObservationUnavailable, GlobalObservationValidationError)


@router.get("/api/v1/observations/global-jobs")
async def global_observation_status(request: Request) -> JSONResponse:
    owner = runtime_from_request(request).global_observation
    if owner is None:
        return JSONResponse(dict(schema="robot-scope.raw-global-observations.v1",
            provider=dict(available=False, reason="TRUSTED_LOCAL_RUNNER_UNAVAILABLE", backend_id=None),
            generation=0, closed=False, active=None, latest=None, historical_only=True,
            current_result=None, body_pose=None, tracking_verified=False, body_pose_verified=False,
            body_extrinsic_verified=False, operational_application="NOT_RUN", absolute_accuracy_m=None))
    return JSONResponse(owner.snapshot())


@router.post("/api/v1/observations/global-jobs")
async def start_global_observation(request: Request, body: GlobalObservationRequest) -> JSONResponse:
    require_same_origin(request)
    try:
        job = await run_in_threadpool(_owner(request).start, **body.model_dump())
    except _ERRORS as exc:
        raise _translate(exc) from exc
    return JSONResponse(job, status_code=202)


@router.get("/api/v1/observations/global-jobs/{job_id}")
async def get_global_observation(request: Request, job_id: str) -> JSONResponse:
    try:
        return JSONResponse(_owner(request).job(job_id))
    except _ERRORS as exc:
        raise _translate(exc) from exc


@router.post("/api/v1/observations/global-jobs/{job_id}/cancel")
async def cancel_global_observation(request: Request, job_id: str) -> JSONResponse:
    require_same_origin(request)
    try:
        return JSONResponse(await run_in_threadpool(_owner(request).cancel, job_id))
    except _ERRORS as exc:
        raise _translate(exc) from exc


@router.get("/api/v1/observations/global-jobs/{job_id}/anchor-proposal")
async def get_anchor_proposal(request: Request, job_id: str) -> JSONResponse:
    try:
        result = await run_in_threadpool(_owner(request).anchor_proposal, job_id)
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except _ERRORS as exc:
        raise _translate(exc) from exc
