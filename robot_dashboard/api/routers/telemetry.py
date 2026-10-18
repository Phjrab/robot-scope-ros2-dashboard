"""Observation-only HTTP transport routes."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from ...application.runtime import ApplicationRuntime
from ...pointcloud_stream import PointCloudFrameError, encode_pointcloud_frame
from ...ros_agent import RosAgent
from ...websocket_stream import stream_until_disconnect
from ..dependencies import (
    require_competition_unlocked,
    require_component,
    require_same_origin,
    runtime_from_request,
    runtime_from_websocket,
    websocket_same_origin,
)
from ..models import CloudPointLimitRequest, SourceSelection


router = APIRouter()


def _agent(runtime: ApplicationRuntime) -> RosAgent:
    return require_component(runtime.agent, "ROS agent is not configured")


def _encode_json(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")


async def _cached_json_response(
    runtime: ApplicationRuntime,
    key: str,
    payload: Dict[str, Any],
) -> Response:
    seq = int(payload.get("seq", 0))
    cached = runtime.json_cache.get(key)
    if cached is None or cached[0] != seq:
        cached = (seq, await asyncio.to_thread(_encode_json, payload))
        runtime.json_cache[key] = cached
    return Response(
        content=cached[1],
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


async def _cached_pointcloud_binary_frame(
    runtime: ApplicationRuntime,
    snapshot: Dict[str, Any],
) -> bytes:
    seq = int(snapshot.get("seq", 0))
    point_bytes = snapshot.get("points_bytes", b"")
    cached = runtime.pointcloud_binary_cache
    if cached is not None and cached[0] == seq and cached[1] is point_bytes:
        return cached[2]
    async with runtime.pointcloud_binary_lock:
        cached = runtime.pointcloud_binary_cache
        if cached is not None and cached[0] == seq and cached[1] is point_bytes:
            return cached[2]
        metadata = {key: value for key, value in snapshot.items() if key != "points_bytes"}
        frame = await asyncio.to_thread(encode_pointcloud_frame, metadata, point_bytes)
        runtime.pointcloud_binary_cache = (seq, point_bytes, frame)
        return frame


@router.get("/api/v1/health")
async def health(request: Request) -> Dict[str, Any]:
    runtime = runtime_from_request(request)
    return await asyncio.to_thread(_agent(runtime).health_snapshot)


@router.get("/api/v1/state")
async def state(request: Request) -> Dict[str, Any]:
    runtime = runtime_from_request(request)
    return await asyncio.to_thread(_agent(runtime).state_snapshot)


@router.get("/api/v1/topics")
async def topics(request: Request) -> Dict[str, Any]:
    runtime = runtime_from_request(request)
    return {"topics": await asyncio.to_thread(_agent(runtime).topics_snapshot)}


@router.get("/api/v1/sources")
async def sources(request: Request) -> Dict[str, Any]:
    runtime = runtime_from_request(request)
    return await asyncio.to_thread(_agent(runtime).sources_snapshot)


@router.post("/api/v1/sources")
async def select_sources(
    selection: SourceSelection,
    request: Request,
) -> Dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, "sensor source selection")
    values = selection.model_dump(exclude_none=True)
    try:
        return await asyncio.to_thread(_agent(runtime).set_sources, values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/v1/pointcloud")
async def pointcloud(request: Request, since: int = -1) -> Response:
    runtime = runtime_from_request(request)
    current = _agent(runtime)
    metadata = await asyncio.to_thread(current.pointcloud_binary_snapshot)
    if int(metadata.get("seq", 0)) == since:
        return Response(status_code=204)
    snapshot = await asyncio.to_thread(current.pointcloud_snapshot)
    return await _cached_json_response(runtime, "pointcloud", snapshot)


@router.get("/api/v1/pointcloud.bin")
async def pointcloud_binary(request: Request, since: int = -1) -> Response:
    runtime = runtime_from_request(request)
    snapshot = await asyncio.to_thread(_agent(runtime).pointcloud_binary_snapshot)
    if int(snapshot.get("seq", 0)) == since:
        return Response(status_code=204)
    frame = await _cached_pointcloud_binary_frame(runtime, snapshot)
    return Response(
        content=frame,
        media_type="application/vnd.robot-scope.pointcloud",
        headers={"Cache-Control": "no-store", "X-Robot-Scope-Stream": "pointcloud-v1"},
    )


@router.get("/api/v1/pointcloud/settings")
async def pointcloud_settings(request: Request) -> Dict[str, Any]:
    runtime = runtime_from_request(request)
    return await asyncio.to_thread(_agent(runtime).cloud_point_settings)


@router.post("/api/v1/pointcloud/settings")
async def set_pointcloud_settings(
    body: CloudPointLimitRequest,
    request: Request,
) -> Dict[str, Any]:
    require_same_origin(request)
    runtime = runtime_from_request(request)
    require_competition_unlocked(runtime, "PointCloud diagnostic settings")
    try:
        settings = await asyncio.to_thread(_agent(runtime).set_cloud_max_points, body.max_points)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    runtime.json_cache.pop("pointcloud", None)
    return settings


@router.get("/api/v1/map")
async def occupancy_map(request: Request, since: int = -1) -> Response:
    runtime = runtime_from_request(request)
    snapshot = await asyncio.to_thread(_agent(runtime).map_snapshot)
    if int(snapshot.get("seq", 0)) == since:
        return Response(status_code=204)
    return await _cached_json_response(runtime, "map", snapshot)


@router.get("/api/v1/joints")
async def robot_joints(request: Request) -> Dict[str, Any]:
    runtime = runtime_from_request(request)
    return await asyncio.to_thread(_agent(runtime).joint_snapshot)


@router.get("/api/v1/pose")
async def robot_pose(request: Request) -> Dict[str, Any]:
    runtime = runtime_from_request(request)
    return await asyncio.to_thread(_agent(runtime).pose_snapshot)


@router.websocket("/api/v1/ws/pointcloud")
async def pointcloud_stream(websocket: WebSocket) -> None:
    if not websocket_same_origin(websocket):
        await websocket.close(code=4403, reason="same-origin point-cloud WebSocket required")
        return
    runtime = runtime_from_websocket(websocket)
    current = _agent(runtime)
    await websocket.accept()
    last_seq = -1

    async def send_next() -> None:
        nonlocal last_seq
        snapshot = current.pointcloud_binary_snapshot()
        seq = int(snapshot.get("seq", 0))
        if seq != last_seq and snapshot.get("points_bytes"):
            await websocket.send_bytes(
                await _cached_pointcloud_binary_frame(runtime, snapshot)
            )
            last_seq = seq

    try:
        await stream_until_disconnect(websocket, send_next)
    except (WebSocketDisconnect, RuntimeError, PointCloudFrameError):
        return


@router.websocket("/api/v1/ws/joints")
async def joint_stream(websocket: WebSocket) -> None:
    if not websocket_same_origin(websocket):
        await websocket.close(code=4403, reason="same-origin joint WebSocket required")
        return
    current = _agent(runtime_from_websocket(websocket))
    await websocket.accept()
    last_signature: tuple[int, str] | None = None
    try:
        while True:
            snapshot = current.joint_snapshot()
            signature = (int(snapshot.get("seq", 0)), str(snapshot.get("state", "waiting")))
            if signature != last_signature:
                await websocket.send_text(
                    json.dumps(snapshot, separators=(",", ":"), allow_nan=False)
                )
                last_signature = signature
            await asyncio.sleep(0.02)
    except (WebSocketDisconnect, RuntimeError):
        return


@router.websocket("/api/v1/ws/pose")
async def pose_stream(websocket: WebSocket) -> None:
    if not websocket_same_origin(websocket):
        await websocket.close(code=4403, reason="same-origin pose WebSocket required")
        return
    current = _agent(runtime_from_websocket(websocket))
    await websocket.accept()
    last_signature: tuple[int, str, str] | None = None
    try:
        while True:
            snapshot = current.pose_snapshot()
            signature = (
                int(snapshot.get("seq", 0)),
                str(snapshot.get("state", "waiting")),
                str(snapshot.get("topic", "")),
            )
            if signature != last_signature:
                await websocket.send_text(
                    json.dumps(snapshot, separators=(",", ":"), allow_nan=False)
                )
                last_signature = signature
            await asyncio.sleep(0.02)
    except (WebSocketDisconnect, RuntimeError):
        return
