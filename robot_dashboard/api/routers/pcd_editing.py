"""Bounded HTTP transport for immutable full-source PCD copies."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict

from fastapi import APIRouter, HTTPException, Request

from ...application.runtime import ApplicationRuntime
from ...pcd_editing.store import MAX_DOCUMENT_BYTES, PcdEditConflict, PcdEditError
from ...saved_maps import SavedMapCatalog, SavedMapError
from ..dependencies import require_competition_unlocked, require_same_origin


def create_router(
    catalog_provider: Callable[[], SavedMapCatalog],
    error_mapper: Callable[[Exception], HTTPException],
    runtime: ApplicationRuntime,
) -> APIRouter:
    """Bind PCD editing to the app's catalogue and competition state."""

    router = APIRouter()

    @router.get("/api/v1/saved-maps/{map_id}/pcd-edit-source")
    async def saved_pcd_edit_source(map_id: str) -> Dict[str, Any]:
        try:
            return await asyncio.to_thread(catalog_provider().pcd_edit_source, map_id)
        except SavedMapError as exc:
            raise error_mapper(exc) from exc
        except PcdEditConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PcdEditError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/api/v1/saved-maps/{map_id}/pcd-edited-copy", status_code=201)
    async def save_pcd_edited_copy(map_id: str, request: Request) -> Dict[str, Any]:
        require_same_origin(request)
        require_competition_unlocked(runtime, "full-source PCD revision creation")
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise HTTPException(status_code=415, detail="PCD edit request requires application/json")
        advertised = request.headers.get("content-length")
        if advertised is not None:
            if not advertised.isascii() or not advertised.isdecimal():
                raise HTTPException(status_code=400, detail="invalid PCD edit Content-Length")
            if len(advertised) > len(str(MAX_DOCUMENT_BYTES)) or int(advertised) > MAX_DOCUMENT_BYTES:
                raise HTTPException(status_code=413, detail="PCD edit request exceeds 2 MiB")
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_DOCUMENT_BYTES:
                raise HTTPException(status_code=413, detail="PCD edit request exceeds 2 MiB")
            raw.extend(chunk)

        def unique_object(pairs: list[tuple[str, Any]]) -> Dict[str, Any]:
            value: Dict[str, Any] = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate PCD edit JSON field")
                value[key] = item
            return value

        try:
            body = json.loads(raw, object_pairs_hook=unique_object)
            if not isinstance(body, dict):
                raise ValueError("PCD edit request must be a JSON object")
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise HTTPException(status_code=422, detail="invalid PCD edit JSON document") from exc
        try:
            metadata = await asyncio.to_thread(catalog_provider().save_pcd_edited_copy, map_id, body)
        except SavedMapError as exc:
            raise error_mapper(exc) from exc
        except PcdEditConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PcdEditError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"map": metadata}

    return router
