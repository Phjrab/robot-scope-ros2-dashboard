"""Read-only projections for explicit 3D/2D map-family lineage."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ...saved_maps import SavedMapCatalog, SavedMapError


def create_router(
    catalog_provider: Callable[[], SavedMapCatalog],
    error_mapper: Callable[[Exception], HTTPException],
) -> APIRouter:
    """Bind lineage reads to the existing catalog and error contract."""

    router = APIRouter()

    @router.get("/api/v1/saved-maps/{map_id}/family")
    async def saved_map_family(map_id: str) -> Dict[str, Any]:
        try:
            return await asyncio.to_thread(catalog_provider().map_family, map_id)
        except SavedMapError as exc:
            raise error_mapper(exc) from exc

    @router.get("/api/v1/saved-maps/{map_id}/download")
    async def saved_map_download(map_id: str) -> StreamingResponse:
        try:
            handle, metadata = await asyncio.to_thread(
                catalog_provider().download_bundle,
                map_id,
            )
        except SavedMapError as exc:
            raise error_mapper(exc) from exc

        def chunks() -> Any:
            try:
                while True:
                    chunk = handle.read(256 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                handle.close()

        return StreamingResponse(
            chunks(),
            media_type="application/zip",
            headers={
                "Cache-Control": "private, no-store",
                "Content-Disposition": f'attachment; filename="{metadata["filename"]}"',
                "Content-Length": str(metadata["bytes"]),
                "X-Content-Type-Options": "nosniff",
                "X-Map-Revision": str(metadata["revision"]),
            },
        )

    @router.get("/api/v1/map-families/{family_id}")
    async def saved_map_family_members(family_id: str) -> Dict[str, Any]:
        try:
            return await asyncio.to_thread(
                catalog_provider().map_family_by_id,
                family_id,
            )
        except SavedMapError as exc:
            raise error_mapper(exc) from exc

    return router
