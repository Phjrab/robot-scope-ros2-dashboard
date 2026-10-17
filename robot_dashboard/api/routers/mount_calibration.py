"""Imported-depth relative pitch analysis, without live hardware or persistence.

These endpoints do not acquire cameras, read a runtime component, modify the
RealSense stream profile, or apply results to ROS, TF, or a VSLAM session.
"""

from __future__ import annotations

import json
import math
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ...mount_calibration import CalibrationError, SCHEMA_VERSION, estimate, export_analysis
from ..dependencies import require_same_origin


MAX_REQUEST_BYTES = 64 * 1024 * 1024
router = APIRouter()


def _finite_json_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("Nonfinite JSON numeric value")
    return value


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"Nonstandard JSON constant: {token}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON object key")
        value[key] = item
    return value


async def _read_payload(request: Request) -> bytearray:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(status_code=415, detail="Use Content-Type: application/json.")
    advertised_length = request.headers.get("content-length")
    if advertised_length is not None:
        if not advertised_length.isascii() or not advertised_length.isdecimal():
            raise HTTPException(status_code=400, detail="Invalid Content-Length.")
        try:
            length = int(advertised_length)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length.") from exc
        if length > MAX_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="Request exceeds the 64 MiB offline limit.")
    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > MAX_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="Request exceeds the 64 MiB offline limit.")
        chunks.extend(chunk)
    return chunks


def _render_analysis(
    body: bytearray, operation: Callable[[Any], dict[str, Any]], headers: dict[str, str]
) -> JSONResponse:
    # Parsing, numerical work and potentially large export serialization all
    # run off the dashboard event loop, not in its request/control handlers.
    try:
        payload = json.loads(
            body,
            parse_float=_finite_json_float,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise HTTPException(
            status_code=422,
            detail="Request must contain valid JSON with unique keys; use null or zero for invalid depth.",
        ) from exc
    try:
        result = operation(payload)
    except CalibrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(result, headers=headers)


@router.get("/api/v1/settings/mount-calibration/status")
async def mount_calibration_status() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "schema_version": SCHEMA_VERSION,
            "mode": "offline",
            "input_source": "imported_depth_json",
            "live_capture_available": False,
            "hardware_access": False,
            "persistence": False,
            "body_extrinsic_validated": False,
            "absolute_pitch_validated": False,
            "max_request_bytes": MAX_REQUEST_BYTES,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/v1/settings/mount-calibration/estimate")
async def mount_calibration_estimate(request: Request) -> JSONResponse:
    require_same_origin(request)
    body = await _read_payload(request)
    return await run_in_threadpool(_render_analysis, body, estimate, {"Cache-Control": "no-store"})


@router.post("/api/v1/settings/mount-calibration/export")
async def mount_calibration_export(request: Request) -> JSONResponse:
    require_same_origin(request)
    body = await _read_payload(request)
    return await run_in_threadpool(
        _render_analysis,
        body,
        export_analysis,
        {
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="relative-wall-pitch-analysis.json"',
        },
    )
