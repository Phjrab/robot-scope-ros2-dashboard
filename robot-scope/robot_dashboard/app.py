"""FastAPI entrypoint for Robot Scope."""

from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ros_agent import RosAgent
from .saved_maps import SavedMapCatalog, SavedMapFormatError, SavedMapNotFound


STATIC_DIR = Path(__file__).resolve().parent / "static"
AGENT: RosAgent | None = None
SAVED_MAPS: SavedMapCatalog | None = None
JSON_CACHE: Dict[str, tuple[int, bytes]] = {}


class SourceSelection(BaseModel):
    camera: str | None = None
    pointcloud: str | None = None
    odometry: str | None = None
    occupancy_grid: str | None = None


class RobotTarget(BaseModel):
    ip: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    if AGENT is None:
        raise RuntimeError("ROS agent has not been configured")
    AGENT.start()
    try:
        yield
    finally:
        AGENT.stop()


app = FastAPI(
    title="Robot Scope",
    version="0.1.0",
    description="Read-only ROS 2 robot observability agent",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def agent() -> RosAgent:
    if AGENT is None:
        raise HTTPException(status_code=503, detail="ROS agent is not configured")
    return AGENT


def saved_maps() -> SavedMapCatalog:
    if SAVED_MAPS is None:
        raise HTTPException(status_code=503, detail="saved map catalog is not configured")
    return SAVED_MAPS


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/v1/health")
async def health() -> Dict[str, Any]:
    return await asyncio.to_thread(agent().health_snapshot)


@app.get("/api/v1/state")
async def state() -> Dict[str, Any]:
    return await asyncio.to_thread(agent().state_snapshot)


@app.get("/api/v1/topics")
async def topics() -> Dict[str, Any]:
    return {"topics": await asyncio.to_thread(agent().topics_snapshot)}


@app.get("/api/v1/sources")
async def sources() -> Dict[str, Any]:
    return await asyncio.to_thread(agent().sources_snapshot)


@app.post("/api/v1/sources")
async def select_sources(selection: SourceSelection) -> Dict[str, Any]:
    values = selection.model_dump(exclude_none=True)
    try:
        return await asyncio.to_thread(agent().set_sources, values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/robot")
async def set_robot(target: RobotTarget) -> Dict[str, Any]:
    try:
        value = await asyncio.to_thread(agent().set_robot_ip, target.ip)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"robot_ip": value}


def cached_json_response(key: str, payload: Dict[str, Any]) -> Response:
    seq = int(payload.get("seq", 0))
    cached = JSON_CACHE.get(key)
    if cached is None or cached[0] != seq:
        cached = (seq, json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8"))
        JSON_CACHE[key] = cached
    return Response(content=cached[1], media_type="application/json", headers={"Cache-Control": "no-store"})


@app.get("/api/v1/pointcloud")
async def pointcloud(since: int = -1) -> Response:
    snapshot = await asyncio.to_thread(agent().pointcloud_snapshot)
    if int(snapshot.get("seq", 0)) == since:
        return Response(status_code=204)
    return cached_json_response("pointcloud", snapshot)


@app.get("/api/v1/map")
async def occupancy_map(since: int = -1) -> Response:
    snapshot = await asyncio.to_thread(agent().map_snapshot)
    if int(snapshot.get("seq", 0)) == since:
        return Response(status_code=204)
    return cached_json_response("map", snapshot)


@app.get("/api/v1/saved-maps")
async def saved_map_list() -> Dict[str, Any]:
    return await asyncio.to_thread(saved_maps().list_snapshot)


@app.get("/api/v1/saved-maps/{map_id}")
async def saved_map_metadata(map_id: str) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(saved_maps().metadata, map_id)
    except SavedMapNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/saved-maps/{map_id}/data")
async def saved_map_data(map_id: str) -> Response:
    try:
        payload = await asyncio.to_thread(saved_maps().data, map_id)
    except SavedMapNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SavedMapFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    content = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Cache-Control": "private, max-age=30"},
    )


@app.websocket("/api/v1/ws/camera")
async def camera_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    last_seq = -1
    try:
        while True:
            snapshot = agent().camera_snapshot()
            seq = int(snapshot.get("seq", 0))
            if seq and seq != last_seq and snapshot.get("data"):
                metadata = {key: value for key, value in snapshot.items() if key != "data"}
                await websocket.send_text(json.dumps(metadata, separators=(",", ":")))
                await websocket.send_bytes(snapshot["data"])
                last_seq = seq
            await asyncio.sleep(0.02)
    except (WebSocketDisconnect, RuntimeError):
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Robot Scope ROS 2 web agent")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--robot-ip", default="")
    parser.add_argument("--profile", default="")
    parser.add_argument("--cloud-max-points", type=int, default=18000)
    return parser.parse_args()


def main() -> None:
    global AGENT, SAVED_MAPS
    args = parse_args()
    AGENT = RosAgent(
        robot_ip=args.robot_ip,
        profile_path=args.profile or None,
        cloud_max_points=args.cloud_max_points,
    )
    profile_base = Path(args.profile).expanduser().resolve().parent if args.profile else Path.cwd()
    SAVED_MAPS = SavedMapCatalog.from_profile(AGENT.profile, base_dir=profile_base)
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        workers=1,
        access_log=False,
        timeout_graceful_shutdown=3,
    )


if __name__ == "__main__":
    main()
