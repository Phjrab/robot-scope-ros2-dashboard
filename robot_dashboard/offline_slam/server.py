"""Standalone offline dashboard. Never instantiates the robot application."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from ..http_security import is_same_origin
from .core import MAX_BYTES, Settings
from .store import Store


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    expected_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    settings: dict = Field(default_factory=dict)


class SaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")


def create_app(root):
    store = Store(root)

    @asynccontextmanager
    async def lifespan(app):
        async def monitor():
            while True:
                await asyncio.to_thread(store.tick)
                await asyncio.sleep(1)

        task = asyncio.create_task(monitor())
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.to_thread(store.close)

    app = FastAPI(title="Robot Scope · Offline SLAM", lifespan=lifespan)
    app.state.store = store

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        # Loopback service, no CORS; hostile origins cannot mutate or import.
        host = request.headers.get("host", "").split(":")[0]
        if host not in {"127.0.0.1", "localhost", "testserver"}:
            return JSONResponse({"detail": "LOOPBACK_HOST_REQUIRED"}, status_code=403)
        if request.method not in {"GET", "HEAD"} and not is_same_origin(
            request.headers.get("origin", ""), request.headers.get("host", "")
        ):
            return JSONResponse({"detail": "SAME_ORIGIN_REQUIRED"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ValueError)
    async def validation_error(request, exc):
        # No filesystem paths or parser inputs in HTTP errors.
        message = str(exc)
        code = (
            message
            if message.replace("_", "").isalnum() and len(message) < 100
            else "INVALID_INPUT"
        )
        return JSONResponse({"detail": code}, status_code=422)

    @app.get("/api/sessions")
    async def sessions():
        return dict(
            sessions=await asyncio.to_thread(store.list_sessions),
            defaults=asdict(Settings()),
        )

    @app.post("/api/sessions", status_code=201)
    async def upload(request: Request):
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_BYTES:
                raise HTTPException(413, "SESSION_TOO_LARGE")
            raw.extend(chunk)
        return await asyncio.to_thread(store.import_session, bytes(raw))

    @app.get("/api/sessions/{identifier}")
    async def status(identifier: str):
        return await asyncio.to_thread(store.status, identifier)

    @app.get("/api/sessions/{identifier}/comparison")
    async def comparison(identifier: str):
        return await asyncio.to_thread(store.comparison, identifier)

    @app.post("/api/sessions/{identifier}/optimize", status_code=202)
    async def start(identifier: str, body: RunRequest):
        if set(body.settings) - set(asdict(Settings())):
            raise ValueError("UNKNOWN_SETTINGS")
        return await asyncio.to_thread(
            store.start, identifier, Settings(**body.settings), body.expected_revision
        )

    @app.post("/api/sessions/{identifier}/cancel")
    async def cancel(identifier: str):
        return await asyncio.to_thread(store.cancel, identifier)

    @app.post("/api/sessions/{identifier}/save")
    async def save(identifier: str, body: SaveRequest):
        return await asyncio.to_thread(store.save, identifier, body.revision)

    @app.get("/api/sessions/{identifier}/export")
    async def export(identifier: str, revision: str):
        path = await asyncio.to_thread(store.export, identifier, revision)
        return FileResponse(
            path, media_type="application/zip", filename=f"offline-map-{identifier}.zip"
        )

    static = (
        Path(__file__).resolve().parents[1] / "static" / "features" / "offline_slam"
    )
    app.mount("/", StaticFiles(directory=static, html=True), name="offline-slam")
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        required=True,
        help="Dedicated offline output directory, not the operational map directory",
    )
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(create_app(args.root), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
