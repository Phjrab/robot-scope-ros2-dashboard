"""Local-only E2E server. Real mission API/store, explicit fake sensors, no ROS.

Do not import production app.py: starting this fixture must never start owners.
"""
import base64
import argparse
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response
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


def replay_options(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--private-replay-manifest', type=Path)
    source.add_argument('--synthetic-rgb-review', action='store_true')
    parser.add_argument('--replay-config', type=Path)
    parser.add_argument('--replay-model', type=Path)
    parser.add_argument('--replay-fps', type=float, default=5.)
    parser.add_argument('--replay-max-frames', type=int, default=10000)
    parser.add_argument('--inference-profile', choices=['full640', 'full960', 'full1280', 'upper-overlap640'], default='full640')
    parser.add_argument('--replay-observation-mode', choices=['detection-only', 'mission'], default='detection-only')
    parser.add_argument('--acknowledge-trusted-pickle', action='store_true')
    args = parser.parse_args(argv)
    if args.private_replay_manifest:
        if os.environ.get('CI'):
            parser.error('Private RGB replay is prohibited in public CI/artifact jobs')
        if args.private_replay_manifest.suffix.lower() != '.jsonl' or not args.replay_config or not args.replay_model:
            parser.error('Private replay requires a C4 JSONL manifest, explicit config and local model')
    return args


def make_rgb_review(root, args):
    if not args.private_replay_manifest and not args.synthetic_rgb_review:
        return None
    from robot_dashboard.competition_traffic.config import TrafficConfig, sha256_file
    from robot_dashboard.competition_traffic.replay_input import inspect_inputs
    from robot_dashboard.mission_routes.competition_native.replay_review import RGBReplayReview
    if args.private_replay_manifest:
        from robot_dashboard.competition_traffic.model import OwnerModel
        config = TrafficConfig.read(args.replay_config)
        detector = OwnerModel(args.replay_model, config,
            acknowledge_trusted_pickle=args.acknowledge_trusted_pickle, inference_profile=args.inference_profile)
        manifest = args.private_replay_manifest
    else:
        import cv2
        from competition_integration.harness import PinnedDetector
        from competition_traffic.helpers import config as fixture_config, lamp
        config, detector = fixture_config(), PinnedDetector(args.inference_profile)
        manifest = root / 'synthetic-rgb.jsonl'
        lines = []
        for i in range(8):
            path = root / f'synthetic-{i}.png'
            cv2.imwrite(str(path), lamp((0, 0, 230) if i % 2 == 0 else (0, 230, 0)))
            lines.append(json.dumps({'image': path.name, 'sha256': sha256_file(path), 'replay_time_s': i / 5.}))
        manifest.write_text('\n'.join(lines))
    return RGBReplayReview(inspect_inputs(manifest, max_frames=args.replay_max_frames), config, detector,
        fps=args.replay_fps, max_frames=args.replay_max_frames, private=bool(args.private_replay_manifest),
        observation_mode=args.replay_observation_mode)


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
        from competition_integration.demo import SignalDemo
        app.state.signal_demo = SignalDemo()
        app.state.rgb_review = make_rgb_review(root, app.state.replay_options)
        if app.state.rgb_review:
            app.state.rgb_review.start()
        try:
            yield
        finally:
            if app.state.rgb_review:
                await app.state.rgb_review.close()
            await app.state.signal_demo.close()
            await service.close()
            await mission.close()


app = FastAPI(lifespan=lifespan)
app.state.replay_options = replay_options([])
app.include_router(router)


@app.middleware('http')
async def private_review_boundary(request, call_next):
    if request.url.path.startswith('/__fixture/rgb-review'):
        origin = request.headers.get('origin')
        if (request.url.hostname not in {'127.0.0.1', 'localhost', '[::1]', '::1'}
                or request.headers.get('sec-fetch-site') == 'cross-site'
                or (origin is not None and origin != str(request.base_url).rstrip('/'))):
            return JSONResponse({'detail': 'LOOPBACK_SAME_ORIGIN_ONLY'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    return await call_next(request)


@app.get('/__fixture/rgb-review')
async def rgb_review_snapshot(request: Request):
    if request.query_params:
        raise HTTPException(400, 'REPLAY_SOURCE_IS_SERVER_CLI_ONLY')
    review = app.state.rgb_review
    return review.snapshot() if review else {'state': 'DISABLED', 'departure_authorized': False}


@app.get('/__fixture/rgb-review/image/{run_id}/{sequence}/{kind}')
async def rgb_review_image(run_id: str, sequence: int, kind: str):
    review = app.state.rgb_review
    image = review.image(run_id, sequence, kind) if review else None
    if image is None:
        raise HTTPException(404, 'FRAME_NOT_RETAINED')
    return Response(image, media_type='image/png')


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


@app.get('/__fixture/native-signal')
async def native_signal_snapshot():
    return app.state.signal_demo.snapshot()


@app.post('/__fixture/native-signal')
async def native_signal_command(request: Request):
    body = await request.json()
    try:
        if body.get('action') == 'stop':
            return await app.state.signal_demo.stop()
        return await app.state.signal_demo.start(body['scenario'], body['request_id'])
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, str(exc)) from exc


app.mount('/static' , StaticFiles(directory='robot_dashboard/static'), name='static')
app.mount('/', StaticFiles(directory='robot_dashboard/static', html=True), name='ui')

if __name__ == '__main__':
    app.state.replay_options = replay_options()
    uvicorn.run(app, host='127.0.0.1', port=int(os.environ.get('COMPETITION_FIXTURE_PORT', '4187')))
