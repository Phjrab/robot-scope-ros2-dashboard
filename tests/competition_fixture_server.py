"""Local-only E2E server. Real mission API/store, explicit fake sensors, no ROS.

Do not import production app.py: starting this fixture must never start owners.
"""
import base64
import os
from contextlib import asynccontextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from robot_dashboard.api.routers.mission_routes import router
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.application.mission_coordinator import MissionCoordinator
from robot_dashboard.mission_routes.context import NavigationContext
from robot_dashboard.mission_routes.service import MissionRoutes
from test_mission_route_service import FixturePlanner, Navigation
from test_spatial_routes import MapProvider, family, MAP_ID, MAP_REVISION


class NoMotionNavigation(Navigation):
    async def send_goal(self, **_kwargs):
        raise AssertionError('E2E server has no motion adapter')

    async def cancel_goal(self, **_kwargs):
        raise AssertionError('E2E server has no motion adapter')


@asynccontextmanager
async def lifespan(app):
    with tempfile.TemporaryDirectory(prefix='competition-explicit-fixture-') as tmp:
        root = Path(tmp)
        maps, nav = MapProvider(), NoMotionNavigation()
        maps.is_fixture = True
        mission = MissionCoordinator(nav, maps, root/'legacy')
        context = NavigationContext(nav, policy_provider=lambda: {}, runtime_provider=lambda: {})
        service = MissionRoutes(root/'plans', maps, SimpleNamespace(), mission, context, FixturePlanner())
        app.state.runtime = ApplicationRuntime(mission_routes=service, competition=SimpleNamespace(require_unlocked=lambda _: None))
        try:
            yield
        finally:
            await service.close()
            await mission.close()


app = FastAPI(lifespan=lifespan)
app.include_router(router)


@app.get('/api/v1/saved-maps')
async def maps():
    return {'maps':[{'id':MAP_ID, 'revision':MAP_REVISION, 'kind':'occupancy2d', 'name':'SYNTHETIC competition fixture'}]}


@app.get('/api/v1/routes')
async def routes():
    return {'routes': []}


@app.get('/api/v1/saved-maps/{identifier}/{part}')
async def map_part(identifier: str, part: str):
    f = family()
    if part == 'family':
        return {'map_id':MAP_ID, 'map_revision':MAP_REVISION, 'families':[{'family_id':f['family_id'], 'family_revision':f['family_revision'], 'source':{'pcd_map_id':f['pcd_map_id'], 'pcd_revision':f['pcd_revision']}, 'occupancy':{'map_id':MAP_ID, 'map_revision':MAP_REVISION}}]}
    if part == 'annotations':
        return MapProvider().document
    g = MapProvider().geometry
    return {'map_id':MAP_ID, 'revision':MAP_REVISION, 'kind':'occupancy2d', 'frame_id':'map', 'width':g.width, 'height':g.height, 'resolution':g.resolution, 'origin':list(g.origin), 'data_b64':base64.b64encode(g.occupancy).decode()}


app.mount('/static', StaticFiles(directory='robot_dashboard/static'), name='static')
app.mount('/', StaticFiles(directory='robot_dashboard/static', html=True), name='ui')

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=int(os.environ.get('COMPETITION_FIXTURE_PORT', '4187')))
