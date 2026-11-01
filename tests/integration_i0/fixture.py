"""Synthetic local host using the actual product mount, catalogue and D1 solver."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles

from experiments.expansion_20261029.d1_multimap.generate import fixture
from robot_dashboard.saved_maps import SavedMapCatalog
from robot_dashboard.expansion_integration.catalogue import compose_maps
from robot_dashboard.expansion_integration.flags import ExpansionFlags
from robot_dashboard.expansion_integration.host import ExpansionOwner, STATIC, install_expansion


def compose(root, flags=None):
    root = Path(root)
    maps = root / "sources"
    maps.mkdir()
    fixture(maps, count=400)
    saved = SavedMapCatalog([maps])
    qualified = {}
    for row in saved.list_snapshot()["maps"]:
        asset = saved._pcd_edit_source_asset(row["id"])
        qualified[row["id"]] = dict(map_id=row["id"], revision=row["revision"],
            sha256=hashlib.sha256(asset.path.read_bytes()).hexdigest(), frame_id=asset.frame_id,
            units="m", evidence_kind="SYNTHETIC", source_epoch="i0-generated",
            display_name=row["name"], mapping_session_id=None)
    catalogue, manager, store = compose_maps(saved, qualified.get, root / "review-bundles")

    def authorize(request: Request):
        if request.headers.get("x-i0-synthetic-fixture") != "local-test-only":
            raise HTTPException(401, "synthetic test authorization required")

    def mutation(request: Request):
        authorize(request)

    owner = ExpansionOwner(authorize=authorize, require_mutation=mutation,
                           catalogue=catalogue, manager=manager, store=store)
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    install_expansion(app, flags or ExpansionFlags(multimap=True), owner)
    return SimpleNamespace(app=app, owner=owner, saved=saved, qualified=qualified)


def attach_runtime(composition):
    """Test-only generated source owner; all algorithms and product ports are real."""
    import asyncio
    from contextlib import asynccontextmanager
    from dataclasses import replace
    import time
    from tests.expansion_runtime.async_fixtures import setup
    from robot_dashboard.expansion_integration.runtime import create_review_runtime
    from robot_dashboard.api.dependencies import require_same_origin
    original, packet, _, captures, _ = setup()
    anchor = [0, time.monotonic_ns()]
    def clock():
        return anchor[0] + time.monotonic_ns() - anchor[1]
    adapter = create_review_runtime(ExpansionFlags(runtime=True, scene=True),
        geometry=original.runtime.ports.geometry, context=original.context,
        mapping=replace(original.mapping, source_end_ns=2**63-1),
        capture_provider=lambda i:captures[(i.source_epoch,i.sequence)],
        clock_ns=clock, source_id='lidar')
    sequence = [2**44]

    async def seed():
        sequence[0] += 1_000_000
        msg, identity = packet(sequence[0], context=adapter.context)
        anchor[:] = [identity.received_ns+1_000_000, time.monotonic_ns()]
        if not adapter.offer_raw(msg, identity):
            raise AssertionError(adapter.health())
        await asyncio.wait_for(adapter.worker.queue.join(),5)
        if adapter.delivered < 1:
            raise AssertionError(adapter.health())
        return adapter.health()

    composition.owner.scene = adapter.scene
    composition.owner.scene_context = lambda:dict(**adapter.context.map_binding,
        frame_id=adapter.context.frame_id, source_epoch=adapter.context.source_epoch,
        stream_epoch=f'c4-{adapter.context.runtime_generation}', clock_domain='fixture-clock',
        calibration_id='fixture-calibration', units='m', source_identity='SYNTHETIC-generated-owner')
    app=composition.app
    previous=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        adapter.start()
        try:
            async with previous(application) as state:
                yield state
        finally:
            await adapter.close()
    app.router.lifespan_context=lifespan

    @app.post('/__i0_test__/frame')
    async def frame(request: Request):
        composition.owner.authorize(request)
        require_same_origin(request)
        return await seed()

    @app.get('/__i0_test__/health')
    async def health(request: Request):
        composition.owner.authorize(request)
        return adapter.health()


if __name__ == "__main__":
    import argparse
    import tempfile
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4191)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="i0-fixture-") as root:
        composition = compose(root, ExpansionFlags(multimap=True,scene=args.all,replay=args.all,
                                                  usability=args.all,runtime=args.all))
        if args.all:
            attach_runtime(composition)
        uvicorn.run(composition.app, host="127.0.0.1", port=args.port, log_level="warning")
