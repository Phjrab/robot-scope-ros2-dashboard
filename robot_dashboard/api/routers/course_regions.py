"""Map-local course regions for observation registration only."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from ...navigation_presets import PresetConflict, PresetInvalid, PresetUnavailable
from ...saved_maps import SavedMapError
from ..dependencies import require_component, require_same_origin, runtime_from_request

router = APIRouter()


class CourseRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=64)
    map_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    map_frame: str = Field(min_length=1, max_length=160)
    polygon: list[list[float]] = Field(min_length=3, max_length=64)
    outside_weight: float = Field(ge=.1, le=1)
    confirmed: Literal[True]


async def _call(request, action, map_id, **kwargs):
    owner = require_component(runtime_from_request(request).course_regions, '코스 영역 저장소를 사용할 수 없습니다.')
    try:
        result = await run_in_threadpool(getattr(owner, action), map_id, **kwargs)
        return JSONResponse(result, status_code=201 if action == 'create' else 200, headers={'Cache-Control': 'no-store'})
    except PresetInvalid as exc:
        raise HTTPException(422, str(exc)) from exc
    except (PresetConflict, SavedMapError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except (PresetUnavailable, OSError) as exc:
        raise HTTPException(503, '코스 영역 저장소에 접근할 수 없습니다.') from exc


@router.get('/api/v1/observations/course-regions/{map_id}')
async def course_regions(request: Request, map_id: str):
    return await _call(request, 'snapshot', map_id)


@router.post('/api/v1/observations/course-regions/{map_id}')
async def save_course_region(request: Request, map_id: str, body: CourseRequest):
    require_same_origin(request)
    return await _call(request, 'create', map_id, **body.model_dump())
