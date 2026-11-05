"""Isolated HTTP fixture with production preset and parameter entry points.

Only a temporary runtime is used. The app lifespan, ROS and robot endpoints
are never mounted. The launcher fails if accidentally invoked.
"""
import ast
import asyncio
from pathlib import Path
import sys
import socket

from fastapi import FastAPI, HTTPException, Request
from typing import Any, Dict
import uvicorn

from robot_dashboard.api.models import NavigationParameterPatchRequest
from robot_dashboard.api.dependencies import require_same_origin, require_competition_unlocked
from robot_dashboard.api.routers.navigation_presets import router
from robot_dashboard.application.navigation_coordinator import NavigationCoordinator
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.competition import CompetitionStateManager
from robot_dashboard.navigation_jobs import (NavigationCommandSpec, NavigationJobManager, MAP_YAML_TOKEN, PARAMS_FILE_TOKEN, NavigationJobError, NavigationUnavailable, NavigationBusy, NavigationConflict, NavigationParameterError, NavigationPoseError)

root = Path(sys.argv[1]).resolve(strict=True)
repository = Path(__file__).resolve().parents[2]


def forbidden(*args, **kwargs):
    raise AssertionError("fixture must never start navigation")


manager = NavigationJobManager(
    project_dir=repository,
    runtime_dir=root / "navigation",
    base_parameters_file=repository / "config/nav2_params_go2_humble.yaml",
    start_command=NavigationCommandSpec(("/usr/bin/false", MAP_YAML_TOKEN, PARAMS_FILE_TOKEN), cwd=repository),
    map_snapshotter=forbidden,
)
coordinator = NavigationCoordinator(
    None, manager, None, None, coordination_lock=asyncio.Lock(),
    require_lifecycle_idle=forbidden,
)
runtime = ApplicationRuntime(navigation=coordinator, competition=CompetitionStateManager(root / "competition"))
RUNTIME = runtime
app = FastAPI()
app.state.runtime = runtime
app.include_router(router)
# Execute the exact production handlers without importing the ROS app lifespan.
source = ast.parse((repository / "robot_dashboard/app.py").read_text())
handlers = {"navigation_coordinator", "navigation_error", "navigation_parameters", "update_navigation_parameters"}
module = ast.Module(body=[node for node in source.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in handlers], type_ignores=[])
exec(compile(module, "robot_dashboard/app.py", "exec"), globals())
# Test fixture state is set over stdin-free CLI startup only.
if len(sys.argv) > 3 and sys.argv[3] == "running":
    manager._pipeline["state"] = "running"

listener = socket.socket()
listener.bind(("127.0.0.1", 0))
print("PORT=" + str(listener.getsockname()[1]), flush=True)
uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[listener])
