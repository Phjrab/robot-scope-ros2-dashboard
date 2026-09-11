"""Non-destructive occupancy-map crop transport boundary."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from ...application.lifecycle_coordinator import LifecycleTransitionBusy
from ...application.mapping_coordinator import (
    MappingCoordinator,
    MappingCoordinatorConflict,
    MappingCoordinatorError,
    MappingCoordinatorUnavailable,
)
from ...saved_maps import (
    SavedMapConflict,
    SavedMapError,
    SavedMapFormatError,
    SavedMapInvalidName,
    SavedMapMutationError,
    SavedMapNotFound,
    SavedMapReadOnly,
)
from ..dependencies import require_component, require_competition_unlocked, require_same_origin, runtime_from_request
from ..models import SavedMapCroppedCopyRequest


router = APIRouter()


def _mapping(request: Request) -> MappingCoordinator:
    return require_component(runtime_from_request(request).mapping, "mapping coordinator is not configured")


def mapping_coordination_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SavedMapNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, SavedMapInvalidName):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, SavedMapReadOnly):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, (SavedMapConflict, MappingCoordinatorConflict, LifecycleTransitionBusy)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, SavedMapFormatError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, MappingCoordinatorUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, SavedMapMutationError):
        return HTTPException(status_code=500, detail="saved map mutation failed")
    return HTTPException(status_code=500, detail="map crop operation failed")


@router.post("/api/v1/saved-maps/{map_id}/cropped-copy")
async def save_cropped_map_copy(
    map_id: str,
    body: SavedMapCroppedCopyRequest,
    request: Request,
) -> Dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, "cropped map revision creation")
    try:
        metadata = await _mapping(request).save_cropped_copy(
            map_id, body.name, body.source_revision, body.crop.model_dump()
        )
    except (LifecycleTransitionBusy, MappingCoordinatorError, SavedMapError) as exc:
        raise mapping_coordination_error(exc) from exc
    return {"map": metadata}
