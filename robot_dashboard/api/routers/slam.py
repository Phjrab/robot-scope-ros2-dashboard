"""Same-origin SLAM control and bounded, read-only visualization transport."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import Field, StrictBool, StrictInt

from ...slam_packages import MapPackageError
from ...slam_sessions import SlamError, SlamSessionManager
from ..dependencies import (require_component, require_competition_unlocked,
                            require_manual_operation_mode, require_same_origin,
                            runtime_from_request, runtime_from_websocket, websocket_same_origin)
from ..models import StrictRequest

router = APIRouter()


class StartRequest(StrictRequest):
    engine_id: Literal["lidar_fastlio", "visual_stereo", "visual_inertial"]
    task: Literal["tracking", "mapping"]
    request_id: str = Field(min_length=8, max_length=96)
    operator_confirmed: StrictBool = False


class StopRequest(StrictRequest):
    generation: StrictInt = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=96)
    discard_unsaved: StrictBool = False


class SaveRequest(StrictRequest):
    generation: StrictInt = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=96)
    name: str = Field(min_length=1, max_length=64)
    create_2d: StrictBool = False


class LocalizeRequest(StrictRequest):
    generation: StrictInt = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=96)
    package_id: str = Field(pattern=r"^np_[0-9a-f]{32}$")
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    hint: dict[str, Any]
    discard_unsaved: StrictBool = False


class RenameRequest(StrictRequest):
    name: str = Field(min_length=1, max_length=120)
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


def _manager(request: Request) -> SlamSessionManager:
    return require_component(runtime_from_request(request).slam, "SLAM integration is not configured")


def _mutation(request: Request) -> SlamSessionManager:
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, "SLAM operation")
    require_manual_operation_mode(runtime)
    return _manager(request)


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, SlamError):
        detail: dict[str, Any] = {"code": exc.code}
        if exc.resources:
            detail["resources"] = exc.resources
        return HTTPException(status_code=exc.status, detail=detail)
    if isinstance(exc, MapPackageError):
        code = exc.code
        status = 404 if code == "PACKAGE_NOT_FOUND" else 409 if code in {"REVISION_CONFLICT", "MAP_IN_USE", "MAP_INCOMPATIBLE"} else 422
        return HTTPException(status_code=status, detail={"code": code})
    return HTTPException(status_code=503, detail={"code": "ENGINE_OPERATION_FAILED"})


@router.get("/api/v1/slam/engines")
async def engines(request: Request) -> dict[str, Any]:
    return await asyncio.to_thread(_manager(request).engines)


@router.get("/api/v1/slam/session")
async def session(request: Request) -> dict[str, Any]:
    return await asyncio.to_thread(_manager(request).snapshot)


@router.get("/api/v1/slam/navigation-context")
async def navigation_context(request: Request) -> dict[str, Any]:
    return await asyncio.to_thread(_manager(request).navigation_context)


@router.post("/api/v1/slam/sessions", status_code=202)
async def start(body: StartRequest, request: Request) -> dict[str, Any]:
    require_same_origin(request)
    try:
        return await _mutation(request).start(**body.model_dump())
    except (SlamError, MapPackageError) as exc:
        raise _error(exc) from exc


@router.post("/api/v1/slam/sessions/{session_id}/stop", status_code=202)
async def stop(session_id: str, body: StopRequest, request: Request) -> dict[str, Any]:
    require_same_origin(request)
    try:
        return await _manager(request).stop(session_id, **body.model_dump())
    except (SlamError, MapPackageError) as exc:
        raise _error(exc) from exc


@router.post("/api/v1/slam/sessions/{session_id}/save", status_code=202)
async def save(session_id: str, body: SaveRequest, request: Request) -> dict[str, Any]:
    require_same_origin(request)
    try:
        return await _mutation(request).save(session_id, **body.model_dump())
    except (SlamError, MapPackageError) as exc:
        raise _error(exc) from exc


@router.post("/api/v1/slam/sessions/{session_id}/localize", status_code=202)
async def localize(session_id: str, body: LocalizeRequest, request: Request) -> dict[str, Any]:
    require_same_origin(request)
    try:
        return await _mutation(request).localize(session_id, **body.model_dump())
    except (SlamError, MapPackageError) as exc:
        raise _error(exc) from exc


@router.get("/api/v1/slam/jobs/{job_id}")
async def job(job_id: str, request: Request) -> dict[str, Any]:
    try:
        return _manager(request).job(job_id)
    except SlamError as exc:
        raise _error(exc) from exc


@router.get("/api/v1/slam/packages")
async def packages(request: Request) -> dict[str, Any]:
    manager = _manager(request)
    records = await asyncio.to_thread(manager.packages.list_packages)
    capabilities = {key: await asyncio.to_thread(adapter.capability) for key, adapter in manager.adapters.items()}
    for item in records:
        cap = capabilities.get(item.get("engine_id"), {})
        item["compatibility"] = manager.packages.compatibility(item["id"], runtime=cap.get("compatibility", {}))
    return {"packages": records}


@router.get("/api/v1/slam/packages/{package_id}")
async def package(package_id: str, request: Request) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_manager(request).packages.get_package, package_id)
    except MapPackageError as exc:
        raise _error(exc) from exc


@router.get("/api/v1/slam/packages/{package_id}/preview")
async def preview(package_id: str, request: Request, expected_revision: str | None = None) -> Any:
    try:
        return await asyncio.to_thread(_manager(request).packages.get_preview, package_id, expected_revision=expected_revision)
    except MapPackageError as exc:
        raise _error(exc) from exc


@router.post("/api/v1/slam/packages/{package_id}/rename")
async def rename(package_id: str, body: RenameRequest, request: Request) -> dict[str, Any]:
    require_same_origin(request)
    try:
        return await _mutation(request).mutate_package("rename_package", package_id, **body.model_dump())
    except (SlamError, MapPackageError) as exc:
        raise _error(exc) from exc


@router.post("/api/v1/slam/packages/{package_id}/copy")
async def copy(package_id: str, body: RenameRequest, request: Request) -> dict[str, Any]:
    require_same_origin(request)
    try:
        return await _mutation(request).mutate_package("copy_package", package_id, **body.model_dump())
    except (SlamError, MapPackageError) as exc:
        raise _error(exc) from exc


@router.delete("/api/v1/slam/packages/{package_id}")
async def delete(package_id: str, request: Request,
                 expected_revision: str = Query(pattern=r"^[0-9a-f]{64}$")) -> dict[str, Any]:
    require_same_origin(request)
    try:
        return await _mutation(request).mutate_package("delete_package", package_id, expected_revision=expected_revision)
    except (SlamError, MapPackageError) as exc:
        raise _error(exc) from exc


@router.get("/api/v1/slam/packages/{package_id}/export")
async def export(package_id: str, request: Request,
                 expected_revision: str = Query(pattern=r"^[0-9a-f]{64}$")) -> StreamingResponse:
    try:
        handle, _ = await asyncio.to_thread(_manager(request).packages.export_package, package_id, expected_revision=expected_revision)
    except MapPackageError as exc:
        raise _error(exc) from exc

    def chunks():
        try:
            while chunk := handle.read(65536):
                yield chunk
        finally:
            handle.close()
    return StreamingResponse(chunks(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{package_id}.zip"'})


@router.get("/api/v1/slam/packages/{package_id}/preview-export")
async def export_preview(package_id: str, request: Request,
                         expected_revision: str = Query(pattern=r"^[0-9a-f]{64}$")) -> StreamingResponse:
    try:
        handle, _ = await asyncio.to_thread(_manager(request).packages.export_preview,
                                           package_id, expected_revision=expected_revision)
    except MapPackageError as exc:
        raise _error(exc) from exc

    def chunks():
        try:
            while chunk := handle.read(65536):
                yield chunk
        finally:
            handle.close()
    return StreamingResponse(chunks(), media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{package_id}-preview.zip"'})


@router.post("/api/v1/slam/packages/import", status_code=201)
async def import_package(request: Request) -> dict[str, Any]:
    require_same_origin(request)
    manager = _mutation(request)
    maximum = min(manager.packages.max_archive_bytes, 128 * 1024**2)
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > maximum:
            raise HTTPException(status_code=413, detail={"code": "ARCHIVE_TOO_LARGE"})
        data.extend(chunk)
    try:
        return await manager.mutate_package("import_package", source=bytes(data))
    except (SlamError, MapPackageError) as exc:
        raise _error(exc) from exc


@router.websocket("/api/v1/ws/slam")
async def stream(websocket: WebSocket) -> None:
    if not websocket_same_origin(websocket):
        await websocket.close(code=4403)
        return
    manager = runtime_from_websocket(websocket).slam
    if manager is None:
        await websocket.close(code=1013)
        return
    await websocket.accept()
    # One latest snapshot, no client queues and no client-created ROS subscriptions.
    try:
        while True:
            frame = await asyncio.to_thread(manager.frame)
            wire = json.dumps(frame, allow_nan=False, separators=(",", ":"))
            if len(wire.encode()) > 8 * 1024**2:
                raise SlamError("VISUALIZATION_LIMIT")
            await asyncio.wait_for(websocket.send_text(wire), timeout=1)
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=0.1)
                if message["type"] == "websocket.disconnect":
                    break
            except asyncio.TimeoutError:
                pass
    except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError, ValueError):
        return
