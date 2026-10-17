"""Stationary depth collection, using the existing SLAM session authority."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import Field, StrictBool, StrictInt

from ...depth_capture_contract import validate_confirmation
from ...depth_capture_store import DepthCaptureError
from ...slam_sessions import SlamError
from ..dependencies import require_same_origin
from ..models import StrictRequest
from .slam import _error, _manager, _mutation

router = APIRouter()


class DepthStartRequest(StrictRequest):
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,96}$")
    robot_seated: StrictBool
    robot_stationary: StrictBool
    camera_stationary: StrictBool


class DepthSampleRequest(DepthStartRequest):
    generation: StrictInt = Field(ge=1)
    body_attitude: dict[str, Any] | None = None


def _confirmation(body: DepthStartRequest) -> dict[str, Any]:
    value = body.model_dump(exclude={"generation", "request_id"})
    validate_confirmation(value)
    return value


@router.post("/api/v1/slam/depth/sessions", status_code=202)
async def start(body: DepthStartRequest, request: Request) -> dict[str, Any]:
    require_same_origin(request)
    try:
        _confirmation(body)
        _store(request)
        return await _mutation(request).start(engine_id="realsense_depth", task="calibration",
            request_id=body.request_id, operator_confirmed=True)
    except SlamError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/slam/sessions/{session_id}/depth-samples", status_code=201)
async def capture(session_id: str, body: DepthSampleRequest, request: Request) -> dict[str, Any]:
    require_same_origin(request)
    try:
        return await _mutation(request).capture_depth(session_id, generation=body.generation,
            request_id=body.request_id, confirmation=_confirmation(body))
    except SlamError as exc:
        raise _error(exc) from exc


def _store(request: Request):
    store = getattr(_manager(request), "depth_samples", None)
    if store is None:
        raise HTTPException(503, detail={"code": "DEPTH_CAPTURE_UNAVAILABLE"})
    return store


@router.get("/api/v1/slam/depth/samples")
async def samples(request: Request) -> JSONResponse:
    try:
        return JSONResponse({"samples": await asyncio.to_thread(_store(request).list_samples)},
                            headers={"Cache-Control": "no-store"})
    except DepthCaptureError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code}) from exc


async def _download(request: Request, sample_id: str, kind: str) -> Response:
    try:
        store = _store(request)
        artifact_headers = {}
        if kind == "compatibility":
            payload, receipt = await asyncio.to_thread(store.verified_artifact, sample_id, "compatibility.json")
            mime, suffix = "application/json", "json"
        elif kind == "image":
            payload, receipt = await asyncio.to_thread(store.verified_artifact, sample_id, "click.png")
            mime, suffix = "image/png", "png"
        else:
            payload = await asyncio.to_thread(store.export_zip, sample_id)
            mime, suffix = "application/zip", "zip"
        if kind in {"compatibility", "image"}:
            artifact_headers = {"X-Robot-Scope-Artifact-SHA256": receipt["sha256"],
                                "X-Robot-Scope-Artifact-Bytes": str(receipt["bytes"])}
        return Response(payload, media_type=mime, headers={
            "Content-Disposition": f'{"inline" if kind == "image" else "attachment"}; filename="{sample_id}.{suffix}"',
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", **artifact_headers})
    except DepthCaptureError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code}) from exc


@router.get("/api/v1/slam/depth/samples/{sample_id}/export")
async def export(sample_id: str, request: Request) -> Response:
    return await _download(request, sample_id, "export")


@router.get("/api/v1/slam/depth/samples/{sample_id}/compatibility")
async def compatibility(sample_id: str, request: Request) -> Response:
    return await _download(request, sample_id, "compatibility")


@router.get("/api/v1/slam/depth/samples/{sample_id}/image")
async def image(sample_id: str, request: Request) -> Response:
    return await _download(request, sample_id, "image")
