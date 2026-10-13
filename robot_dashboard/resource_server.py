"""Optional host-only monitor, without starting ROS or robot services.

Run: python3 -m robot_dashboard.resource_server --host 0.0.0.0 --port 8090
The integrated Robot Scope app additionally supplies sensor measurements.
"""

import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routers.resources import router
from .application.runtime import ApplicationRuntime


def create_app() -> FastAPI:
    app = FastAPI(title="Robot Scope · Jetson Resources")
    app.state.runtime = ApplicationRuntime()
    static = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")
    app.include_router(router)

    @app.middleware("http")
    async def no_cache(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/")
    async def index():
        return FileResponse(static / "resources.html")

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Jetson host resource monitor")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
