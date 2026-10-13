"""Resource monitoring remains available independently of ROS readiness."""

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from ..dependencies import runtime_from_request

router = APIRouter()


@router.get("/api/v1/system/resources")
async def resources(request: Request) -> dict[str, Any]:
    runtime = runtime_from_request(request)
    return await asyncio.to_thread(runtime.resources.snapshot, runtime.agent)
