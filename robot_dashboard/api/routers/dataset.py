"""Dataset capture and gallery HTTP transport routes."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response

from ...application.runtime import ApplicationRuntime
from ...dataset_capture import (
    CAMERA_SOURCE_IDS,
    DatasetCaptureBusy,
    DatasetCaptureConflict,
    DatasetCaptureError,
    DatasetCaptureManager,
    DatasetCaptureNotFound,
    DatasetCaptureUnavailable,
    DatasetCaptureValidationError,
)
from ..dependencies import require_component, require_same_origin, runtime_from_request
from ..models import DatasetCaptureStartRequest, DatasetCaptureStopRequest


def _manager(runtime: ApplicationRuntime) -> DatasetCaptureManager:
    return require_component(runtime.dataset_capture, "dataset capture is not configured")


def _error(exc: DatasetCaptureError) -> HTTPException:
    if isinstance(exc, DatasetCaptureNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (DatasetCaptureBusy, DatasetCaptureConflict)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, DatasetCaptureValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, DatasetCaptureUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail="dataset capture operation failed")


def create_router(require_service_lifecycle_idle: Callable[[], None]) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/datasets/capture")
    async def dataset_capture_status(request: Request) -> Dict[str, Any]:
        runtime = runtime_from_request(request)
        return await asyncio.to_thread(_manager(runtime).snapshot)

    @router.post("/api/v1/datasets/capture/start", status_code=202)
    async def dataset_capture_start(
        body: DatasetCaptureStartRequest,
        request: Request,
    ) -> Dict[str, Any]:
        require_same_origin(request)
        runtime = runtime_from_request(request)
        sources = CAMERA_SOURCE_IDS if body.sources == "both" else (body.sources,)
        async with runtime.pipeline_coordination_lock:
            require_service_lifecycle_idle()
            try:
                return await asyncio.to_thread(
                    _manager(runtime).start,
                    sources,
                    body.capture_hz,
                    body.label,
                )
            except DatasetCaptureError as exc:
                raise _error(exc) from exc

    @router.post("/api/v1/datasets/capture/stop")
    async def dataset_capture_stop(
        body: DatasetCaptureStopRequest,
        request: Request,
    ) -> Dict[str, Any]:
        require_same_origin(request)
        runtime = runtime_from_request(request)
        async with runtime.pipeline_coordination_lock:
            try:
                return await asyncio.to_thread(
                    _manager(runtime).stop,
                    body.session_id,
                )
            except DatasetCaptureError as exc:
                raise _error(exc) from exc

    @router.get("/api/v1/datasets")
    async def dataset_sessions(request: Request) -> Dict[str, Any]:
        runtime = runtime_from_request(request)
        try:
            return await asyncio.to_thread(_manager(runtime).list_sessions)
        except DatasetCaptureError as exc:
            raise _error(exc) from exc

    @router.post("/api/v1/datasets/{session_id}/export", status_code=201)
    async def dataset_export(
        request: Request,
        session_id: str,
    ) -> Dict[str, Any]:
        require_same_origin(request)
        runtime = runtime_from_request(request)
        async with runtime.pipeline_coordination_lock:
            require_service_lifecycle_idle()
            try:
                return await asyncio.to_thread(
                    _manager(runtime).export_session,
                    session_id,
                )
            except DatasetCaptureError as exc:
                raise _error(exc) from exc

    @router.get("/api/v1/datasets/exports/{export_id}")
    async def dataset_export_download(
        request: Request,
        export_id: str,
    ) -> FileResponse:
        runtime = runtime_from_request(request)
        try:
            path, metadata = await asyncio.to_thread(
                _manager(runtime).export_download,
                export_id,
            )
        except DatasetCaptureError as exc:
            raise _error(exc) from exc
        return FileResponse(
            path,
            media_type="application/zip",
            filename=str(metadata["filename"]),
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Archive-SHA256": str(metadata["sha256"]),
            },
        )

    @router.get("/api/v1/datasets/{session_id}")
    async def dataset_session(
        request: Request,
        session_id: str,
        before: int | None = Query(default=None, ge=1, le=100_000_000),
        limit: int = Query(default=24, ge=1, le=48),
    ) -> Dict[str, Any]:
        runtime = runtime_from_request(request)
        try:
            return await asyncio.to_thread(
                _manager(runtime).session_detail,
                session_id,
                before,
                limit,
            )
        except DatasetCaptureError as exc:
            raise _error(exc) from exc

    @router.get("/api/v1/datasets/{session_id}/samples/{sample_index}/{source_id}.jpg")
    async def dataset_image(
        request: Request,
        session_id: str,
        sample_index: int,
        source_id: str,
    ) -> Response:
        runtime = runtime_from_request(request)
        try:
            payload = await asyncio.to_thread(
                _manager(runtime).read_image,
                session_id,
                sample_index,
                source_id,
            )
        except DatasetCaptureError as exc:
            raise _error(exc) from exc
        return Response(
            content=payload,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": (
                    f'inline; filename="{source_id}-{sample_index:08d}.jpg"'
                ),
            },
        )

    return router
