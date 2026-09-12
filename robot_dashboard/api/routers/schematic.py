"""One strictly bounded display-only command surface; never a generic dispatch API."""
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .route_planner import _coordinator, _error
from ...application.route_planner_coordinator import RoutePlannerError
from ...route_planner.schematic import SchematicError
from ...route_planner.orders import OrderValidationError
from ...route_planner.state_store import RoutePlannerStorageError
from ..dependencies import require_competition_unlocked, require_same_origin, runtime_from_request

router = APIRouter()


class SchematicCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["CONTEXT", "LAYOUT", "APPROVE", "ORDER", "UNLOCK", "START_POINT", "RECOMMEND", "SELECT", "START", "END", "STEP", "PICKUP", "DROPOFF"]
    expected_revision: int = Field(strict=True, ge=0)
    context: Literal["SAVED_OCCUPANCY", "DEMO", "FIELD"]
    data: dict[str, Any]


@router.get("/api/v1/route-planner/schematic")
async def schematic_status(request: Request):
    return _coordinator(runtime_from_request(request)).schematic_snapshot()


@router.post("/api/v1/route-planner/schematic")
async def schematic_command(request: Request):
    require_same_origin(request)
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, "schematic editing")
    # Bound the body before JSON/Pydantic allocation (also covers chunked input).
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 1024 * 1024:
            raise HTTPException(413, "schematic command exceeds 1MiB")
    try:
        command = SchematicCommand.model_validate(json.loads(body))
        return await _coordinator(runtime).schematic_command(**command.model_dump())
    except SchematicError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except RoutePlannerError as exc:
        raise _error(exc) from exc
    except RoutePlannerStorageError as exc:
        raise HTTPException(503, "schematic storage unavailable") from exc
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc)[:600] if isinstance(exc, OrderValidationError) else "invalid schematic document") from exc
