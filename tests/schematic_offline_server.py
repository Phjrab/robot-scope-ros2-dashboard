"""Local-only integration harness: actual planner/API, every actuation port traps.

Run: .venv/bin/python -m uvicorn schematic_offline_server:app --app-dir tests --host 127.0.0.1 --port 4188
The normal ROS dashboard app is deliberately never imported or started.
"""
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from robot_dashboard.api.routers.route_catalogs import router
from robot_dashboard.api.routers.missions import router as mission_router
from robot_dashboard.api.models import NavigationGoalRequest
from robot_dashboard.application.route_planner_coordinator import RoutePlannerCoordinator
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.competition import CompetitionStateManager
from robot_dashboard.route_planner.perception import MockRoutePerceptionProvider


class ActuationTrap:
    def __init__(self):
        self.calls = []
        self.active = False

    def blocks_navigation_goal(self):
        return self.active

    def __getattr__(self, name):
        def forbidden(*args, **kwargs):
            self.calls.append(name)
            raise AssertionError(f"forbidden hardware/Mission/Navigation/Control call: {name}")
        return forbidden


def make_app(root):
    application = FastAPI()
    trap = ActuationTrap()
    runtime = ApplicationRuntime()
    runtime.agent = runtime.navigation = runtime.mission = runtime.lifecycle = trap
    runtime.competition = CompetitionStateManager(root / "competition", blockers_provider=lambda: {}, control_provider=lambda: {"estop_latched": False, "lease": {"active": False}})
    gates = {"navigation": False, "mapping": False}
    runtime.route_planner = RoutePlannerCoordinator(trap, trap, root / "planner", navigation_view=lambda: {"pipeline": {"state": "running" if gates["navigation"] else "idle"}}, mapping_activity=lambda: (gates["mapping"], []), perception=MockRoutePerceptionProvider())
    application.state.runtime = runtime
    application.state.trap = trap
    application.state.gates = gates
    application.include_router(router)
    application.include_router(mission_router)
    static = Path(__file__).resolve().parents[1] / "robot_dashboard/static"
    application.mount("/static", StaticFiles(directory=static), name="static")

    @application.get("/")
    def harness():
        return FileResponse(Path(__file__).parent / "fixtures/schematic_offline.html")

    @application.get("/dashboard")
    def dashboard_shell():
        return FileResponse(static / "index.html")

    @application.get("/test/traps")
    def traps():
        return {"calls": list(trap.calls)}

    @application.post("/api/v1/navigation/goal")
    async def goal_contract(body: NavigationGoalRequest):
        # Actual production request model; any accepted goal reaches a hard trap.
        return trap.send_goal(**body.model_dump())

    return application


temporary = tempfile.TemporaryDirectory(prefix="robot-scope-schematic-test-")
app = make_app(Path(temporary.name).resolve())
