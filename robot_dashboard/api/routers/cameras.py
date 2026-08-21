"""Camera catalog and bounded WebSocket transport routes."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from ...application.runtime import ApplicationRuntime
from ...ros_agent import RosAgent
from ...websocket_stream import stream_until_disconnect
from ..dependencies import (
    require_component,
    runtime_from_request,
    runtime_from_websocket,
    websocket_same_origin,
)


router = APIRouter()
CAMERA_WS_SEND_TIMEOUT_S = 2.0
CAMERA_SOURCE_IDS = frozenset({"go2_front", "realsense_color"})


def _agent(runtime: ApplicationRuntime) -> RosAgent:
    return require_component(runtime.agent, "ROS agent is not configured")


@router.get("/api/v1/cameras")
async def cameras(request: Request) -> Dict[str, Any]:
    runtime = runtime_from_request(request)
    return await asyncio.to_thread(_agent(runtime).cameras_snapshot)


async def _camera_stream_source(websocket: WebSocket, source_id: str) -> None:
    if not websocket_same_origin(websocket):
        await websocket.close(code=4403, reason="same-origin camera WebSocket required")
        return
    if source_id not in CAMERA_SOURCE_IDS:
        await websocket.close(code=4404, reason="camera source is not allowlisted")
        return
    runtime = runtime_from_websocket(websocket)
    await websocket.accept()
    current = _agent(runtime)
    opened = await asyncio.to_thread(current.camera_stream_open, source_id)
    if not opened.get("accepted", False):
        reason = str(opened.get("reason", "camera source unavailable"))
        code = 1013 if "limit" in reason else 1012
        await websocket.close(code=code, reason=reason[:123])
        return
    token = str(opened["token"])
    last_seq = -1
    last_stream_id = ""

    async def send_next() -> None:
        nonlocal last_seq, last_stream_id
        snapshot = current.camera_snapshot(source_id)
        seq = int(snapshot.get("seq", 0))
        stream_id = str(snapshot.get("stream_id", ""))
        if (
            seq
            and (stream_id != last_stream_id or seq != last_seq)
            and snapshot.get("data")
        ):
            metadata = {key: value for key, value in snapshot.items() if key != "data"}
            await asyncio.wait_for(
                websocket.send_text(json.dumps(metadata, separators=(",", ":"))),
                timeout=CAMERA_WS_SEND_TIMEOUT_S,
            )
            await asyncio.wait_for(
                websocket.send_bytes(snapshot["data"]),
                timeout=CAMERA_WS_SEND_TIMEOUT_S,
            )
            last_seq = seq
            last_stream_id = stream_id

    try:
        await stream_until_disconnect(websocket, send_next)
    except (asyncio.TimeoutError, WebSocketDisconnect, RuntimeError):
        return
    finally:
        await asyncio.to_thread(current.camera_stream_close, source_id, token)


@router.websocket("/api/v1/ws/camera")
async def camera_stream(websocket: WebSocket, source_id: str = "go2_front") -> None:
    """Legacy route; omitted source id remains the Go2 front camera."""

    await _camera_stream_source(websocket, source_id)


@router.websocket("/api/v1/ws/cameras/{source_id}")
async def camera_source_stream(websocket: WebSocket, source_id: str) -> None:
    await _camera_stream_source(websocket, source_id)
