"""Test-only C1/D1 composition from read-only exact exports via PYTHONPATH.

C1 owns all APIs/jobs/export; D1 owns all registration. C2 provides test wiring,
SYNTHETIC generator invocation and a bounded preview provider only.
"""
import contextlib
from dataclasses import replace
from pathlib import Path
import socket
import tempfile

from fastapi import FastAPI, HTTPException, Request
import numpy as np
import uvicorn
from robot_dashboard.expansion_contracts import FusionProposal
from robot_dashboard.expansion_contracts.fixtures import source, obstacle
from robot_dashboard.expansion_services.catalogue import CatalogueAdapter, ResolvedSource
from robot_dashboard.expansion_services.export import BundleStore
from robot_dashboard.expansion_services.jobs import FusionJobManager
from robot_dashboard.expansion_services.router import create_router
from robot_dashboard.expansion_services.scene import SceneSnapshotService
from robot_dashboard.pcd_editing.store import SourceAsset
from robot_dashboard.multimap_core.contract_adapter import solve_contract
from experiments.expansion_20261029.d1_multimap.generate import fixture


def compose(root, *, source_count=2, include_bundles=False):
    """External modules remain untouched; optional catalogue contains offline bundles only."""
    raw, resolver, poses = fixture(root, count=400)
    resolved, points = {}, {}
    for i, descriptor in enumerate(raw[:source_count]):
        path = resolver(descriptor)
        from robot_dashboard.pcd_editing.pcd import _read_header
        with path.open("rb") as stream:
            _, _, dtype, count, _ = _read_header(stream, path.stat().st_size, 20000000)
            records = np.frombuffer(stream.read(), dtype=dtype)
        wire = replace(source(i+1, descriptor["sha256"]),
            revision=descriptor["sha256"], point_count=count,
            mapping_session_id=f"{101+i:024x}",
            point_schema=[dict(name=n,size=4,type="F",count=1) for n in dtype.names],
            acquisition={"origin":"SYNTHETIC D1 generator", "display_name":f"Exact D1 synthetic map {i+1}"})
        resolved[wire.map_id] = ResolvedSource(wire, SourceAsset(wire.map_id,wire.revision,path,wire.frame_id))
        points[wire.map_id] = np.column_stack([records[n] for n in ('x','y','z')])[::5].reshape(-1).tolist()
    def preview(d):
        if d.map_id not in points:
            path = resolve(d.map_id).asset.path
            from robot_dashboard.pcd_editing.pcd import _read_header
            with path.open("rb") as stream:
                _, _, dtype, _, _ = _read_header(stream, path.stat().st_size, 20000000)
                records = np.frombuffer(stream.read(), dtype=dtype)
            points[d.map_id] = np.column_stack([records[n] for n in ('x','y','z')])[::5].reshape(-1).tolist()
        return dict(schema="robot-scope.multimap-ui.v1",units="m",input_pin=dict(id=d.map_id,session_id=d.mapping_session_id or f"unverified:{d.map_id}",revision=d.revision,sha256=d.sha256),points=points[d.map_id])
    def resolve(map_id):
        if map_id in resolved:
            return resolved[map_id]
        if not include_bundles:
            raise KeyError(map_id)
        return store.reload(map_id)
    def list_ids():
        bundles = sorted(p.name for p in store.root.iterdir() if p.is_dir() and len(p.name) == 24) if include_bundles and store.root.exists() else []
        return [*resolved, *bundles]
    catalogue = CatalogueAdapter(list_ids, resolve, preview)
    store = BundleStore(root/"bundles",catalogue)
    def solver(request,sources,cancel,progress,*,job_id):
        paths={s.descriptor.map_id:s.asset.path for s in sources}
        return solve_contract(request,lambda d:paths[d['map_id']],FusionProposal,job_id=job_id,
            cancel_token=cancel,progress=lambda event:progress(min(.95,event['completed_pairs'])))
    manager=FusionJobManager(catalogue,solver,store)
    scene=SceneSnapshotService(obstacle().map_binding,host_clock_id="c2-exact-test")
    def authorize(request:Request):
        if request.client.host!='127.0.0.1' or request.headers.get('authorization')!='Bearer public-c2-exact-synthetic-only-bearer':
            raise HTTPException(401,'explicit loopback test auth required')
    def origin(request:Request):
        if request.headers.get('origin')!='http://'+request.headers.get('host',''):raise HTTPException(403,'same origin required')
    @contextlib.asynccontextmanager
    async def lifespan(app):
        try:yield
        finally:manager.close()
    app=FastAPI(lifespan=lifespan)
    app.include_router(create_router(manager,catalogue,scene,store,authorize=authorize,require_origin=origin))
    from types import SimpleNamespace
    return SimpleNamespace(app=app, manager=manager, store=store, catalogue=catalogue,
                           resolved=resolved, poses=poses, points=points)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--round2', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="c2-exact-synthetic-") as temporary:
        composition = compose(Path(temporary), source_count=3 if args.round2 else 2,
                              include_bundles=args.round2)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen(16)
            print('C2_EXACT_URL=http://127.0.0.1:'+str(listener.getsockname()[1]),flush=True)
            uvicorn.Server(uvicorn.Config(composition.app,log_level='error')).run(sockets=[listener])


if __name__=='__main__':main()
