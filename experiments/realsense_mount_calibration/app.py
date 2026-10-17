"""Loopback-only offline prototype. Run: uvicorn app:app --host 127.0.0.1."""

from pathlib import Path
import json
import math

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from calibration import CalibrationError, SCHEMA_VERSION, estimate, export_analysis


ROOT = Path(__file__).resolve().parent
MAX_REQUEST_BYTES = 64 * 1024 * 1024
app = FastAPI(title="RealSense Mount Relative Pitch • Offline Prototype", version=SCHEMA_VERSION)
app.mount("/static", StaticFiles(directory=ROOT / "static", check_dir=False), name="static")


def _finite_json_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("Nonfinite JSON numeric value")
    return value


@app.get("/")
async def index():
    path = ROOT / "static" / "index.html"
    if not path.is_file():
        raise HTTPException(status_code=503, detail="Dashboard assets are not available yet. The offline API is ready.")
    return FileResponse(path, headers={"Cache-Control": "no-store"})


@app.get("/api/health")
async def health():
    return {"status": "ok", "schema_version": SCHEMA_VERSION, "mode": "offline",
            "camera_connected": False, "robot_connected": False, "hardware_access": False,
            "persistence": False, "body_extrinsic_validated": False}


async def _read_payload(request: Request):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(status_code=415, detail="Use Content-Type: application/json.")
    advertised_length = request.headers.get("content-length")
    if advertised_length:
        try:
            if int(advertised_length) > MAX_REQUEST_BYTES:
                raise HTTPException(status_code=413, detail="Request exceeds the 64 MiB offline limit.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length.")
    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > MAX_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="Request exceeds the 64 MiB offline limit.")
        chunks.extend(chunk)
    try:
        # JSON NaN and Infinity are not portable interchange values; use null for holes.
        return json.loads(chunks, parse_float=_finite_json_float,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise HTTPException(status_code=422, detail="Request must contain valid JSON; use null or zero for invalid depth.")


@app.exception_handler(CalibrationError)
async def calibration_error_handler(_request: Request, exc: CalibrationError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.post("/api/estimate")
async def estimate_endpoint(request: Request):
    payload = await _read_payload(request)
    result = await run_in_threadpool(estimate, payload)
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.post("/api/export")
async def export_endpoint(request: Request):
    payload = await _read_payload(request)
    result = await run_in_threadpool(export_analysis, payload)
    return JSONResponse(result, headers={"Cache-Control": "no-store",
                                         "Content-Disposition": 'attachment; filename="relative-wall-pitch-analysis.json"'})
