"""FastAPI entrypoint for Robot Scope."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .mapping_jobs import (
    InvalidMapName,
    JobBusyError,
    MappingJobError,
    MappingJobManager,
    PipelineNotRunning,
    SaveCommandSpec,
    SaveResultError,
)
from .ros_agent import RosAgent
from .saved_maps import SavedMapCatalog, SavedMapFormatError, SavedMapNotFound


STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGGER = logging.getLogger(__name__)
AGENT: RosAgent | None = None
SAVED_MAPS: SavedMapCatalog | None = None
MAPPING_JOBS: MappingJobManager | None = None
MAPPING_TASK: asyncio.Task[None] | None = None
JSON_CACHE: Dict[str, tuple[int, bytes]] = {}


class SourceSelection(BaseModel):
    camera: str | None = None
    pointcloud: str | None = None
    odometry: str | None = None
    occupancy_grid: str | None = None


class RobotTarget(BaseModel):
    ip: str


class MapSaveRequest(BaseModel):
    name: str
    create_2d: bool = True


@asynccontextmanager
async def lifespan(_: FastAPI):
    if AGENT is None:
        raise RuntimeError("ROS agent has not been configured")
    AGENT.start()
    try:
        yield
    finally:
        if MAPPING_JOBS is not None:
            await asyncio.to_thread(MAPPING_JOBS.close)
        if MAPPING_TASK is not None and not MAPPING_TASK.done():
            try:
                await asyncio.wait_for(asyncio.shield(MAPPING_TASK), timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        AGENT.stop()


app = FastAPI(
    title="Robot Scope",
    version="0.1.0",
    description="ROS 2 observability and allowlisted mapping operations",
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


def mapping_jobs() -> MappingJobManager:
    if MAPPING_JOBS is None:
        raise HTTPException(status_code=503, detail="mapping operations are not configured")
    return MAPPING_JOBS


def mapping_error(exc: MappingJobError) -> HTTPException:
    if isinstance(exc, InvalidMapName):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (JobBusyError, PipelineNotRunning)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, SaveResultError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


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


@app.get("/api/v1/joints")
async def robot_joints() -> Dict[str, Any]:
    return await asyncio.to_thread(agent().joint_snapshot)


@app.get("/api/v1/mapping/control")
async def mapping_control(since_log_seq: int = 0) -> Dict[str, Any]:
    return await asyncio.to_thread(mapping_jobs().snapshot, since_log_seq=since_log_seq)


@app.post("/api/v1/mapping/start")
async def mapping_start() -> Dict[str, Any]:
    global MAPPING_TASK
    if MAPPING_TASK is not None and not MAPPING_TASK.done():
        raise HTTPException(status_code=409, detail="a map save is in progress")
    try:
        return await asyncio.to_thread(mapping_jobs().start_mapping)
    except MappingJobError as exc:
        raise mapping_error(exc) from exc


@app.post("/api/v1/mapping/stop")
async def mapping_stop() -> Dict[str, Any]:
    if MAPPING_TASK is not None and not MAPPING_TASK.done():
        raise HTTPException(status_code=409, detail="map save must finish before mapping can stop")
    try:
        return await asyncio.to_thread(mapping_jobs().stop_mapping)
    except MappingJobError as exc:
        raise mapping_error(exc) from exc


async def run_map_save(name: str, kind: str) -> None:
    try:
        await asyncio.to_thread(mapping_jobs().save_map, name, kind)
    except MappingJobError:
        # Expected failures are recorded in the bounded operation snapshot and
        # displayed by the mapping console on its next poll.
        return
    except Exception:
        LOGGER.exception("unexpected map save failure")


@app.post("/api/v1/mapping/save", status_code=202)
async def mapping_save(request: MapSaveRequest) -> Dict[str, Any]:
    global MAPPING_TASK
    manager = mapping_jobs()
    if MAPPING_TASK is not None and not MAPPING_TASK.done():
        raise HTTPException(status_code=409, detail="another map save is already in progress")
    try:
        name = manager.validate_map_name(request.name)
    except MappingJobError as exc:
        raise mapping_error(exc) from exc
    kind = "pointcloud3d_2d" if request.create_2d else "pointcloud3d"
    if kind not in manager.allowed_save_kinds:
        raise HTTPException(status_code=503, detail="requested map save recipe is unavailable")
    MAPPING_TASK = asyncio.create_task(run_map_save(name, kind), name=f"map-save-{name}")
    return {"accepted": True, "map_name": name, "kind": kind}


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


@app.websocket("/api/v1/ws/joints")
async def joint_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    last_signature: tuple[int, str] | None = None
    try:
        while True:
            snapshot = agent().joint_snapshot()
            signature = (int(snapshot.get("seq", 0)), str(snapshot.get("state", "waiting")))
            if signature != last_signature:
                await websocket.send_text(
                    json.dumps(snapshot, separators=(",", ":"), allow_nan=False)
                )
                last_signature = signature
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
    parser.add_argument("--mapping-output-dir", default="~/ws/go2_3d/maps")
    return parser.parse_args()


def main() -> None:
    global AGENT, SAVED_MAPS, MAPPING_JOBS
    args = parse_args()
    AGENT = RosAgent(
        robot_ip=args.robot_ip,
        profile_path=args.profile or None,
        cloud_max_points=args.cloud_max_points,
    )
    profile_base = Path(args.profile).expanduser().resolve().parent if args.profile else Path.cwd()
    SAVED_MAPS = SavedMapCatalog.from_profile(AGENT.profile, base_dir=profile_base)
    project_dir = Path(__file__).resolve().parents[1]
    save_script = project_dir / "scripts" / "save_hesai_map_humble.sh"
    MAPPING_JOBS = MappingJobManager.for_robot_scope(
        project_dir=project_dir,
        output_dir=Path(args.mapping_output_dir).expanduser(),
        save_commands={
            "pointcloud3d": SaveCommandSpec(
                (str(save_script), "{output_prefix}", "pcd"),
                (".pcd",),
                cwd=project_dir,
                timeout_seconds=35,
                min_result_bytes=128,
                max_result_bytes=1024 * 1024 * 1024,
            ),
            "pointcloud3d_2d": SaveCommandSpec(
                (str(save_script), "{output_prefix}", "pcd-and-2d"),
                (".pcd", ".yaml", ".pgm"),
                cwd=project_dir,
                timeout_seconds=90,
                min_result_bytes=4,
                max_result_bytes=1024 * 1024 * 1024,
            ),
        },
        # Existing classroom sessions may have been started in a terminal.
        # The one-shot saver still requires a fresh /Laser_map and will time
        # out safely, while stop only affects dashboard-owned process groups.
        require_pipeline_for_save=False,
    )
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
