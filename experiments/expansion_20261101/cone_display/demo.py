"""Explicit loopback-only synthetic host for the installed /extensions product.

No runtime environment flags or production auth policy are changed. The demo
serves only committed public simulation data and has no map/control owners.
"""

import asyncio
from contextlib import asynccontextmanager
import secrets
import time
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from robot_dashboard.expansion_integration.cone_demo import (
    load_scenario,
    demo_context,
    adapt_cones,
)
from robot_dashboard.expansion_integration.flags import ExpansionFlags
from robot_dashboard.expansion_integration.host import (
    ExpansionOwner,
    STATIC,
    install_expansion,
)
from robot_dashboard.expansion_services.scene import SceneSnapshotService

SCENARIO = (
    Path(__file__).resolve().parents[3]
    / "assets/competition-arena/revisions/corridor-parallel-20261024/scenario_slalom_multi.json"
)


def compose_demo(*, port=4192):
    payload = load_scenario(SCENARIO)
    context = demo_context(payload)
    scene = SceneSnapshotService(
        {k: context[k] for k in ("map_id", "revision", "generation")},
        schema_version="0.2",
        stream_epoch=context["stream_epoch"],
        max_sample_bytes=64 * 1024,
        host_clock_id="cone-demo-host",
        max_age_ns=1_000_000_000,
    )
    state = SimpleNamespace(
        running=True,
        empty=False,
        sequence=0,
        payload=payload,
        context=context,
        scene=scene,
    )
    cookie = secrets.token_urlsafe(32)

    def local(request):
        if (
            request.client.host not in {"127.0.0.1", "::1", "testclient"}
            or request.headers.get("host") != f"127.0.0.1:{port}"
            or request.headers.get("sec-fetch-site") == "cross-site"
        ):
            raise HTTPException(403, "ISOLATED_LOOPBACK_DEMO_ONLY")

    def authorize(request):
        local(request)
        if not secrets.compare_digest(request.cookies.get("i0_cone_demo", ""), cookie):
            raise HTTPException(
                401, "DEMO_SESSION_REQUIRED: open / on this loopback demo"
            )

    def offer():
        state.sequence += 1
        now = time.monotonic_ns()
        # New samples are produced explicitly by this synthetic timer, never GET.
        value = dict(state.payload, stamp=state.sequence / 10)
        if state.empty:
            value["cones"] = []
        return scene.ingest(
            "obstacle_frame",
            adapt_cones(
                value,
                context,
                sequence=state.sequence,
                received_monotonic_ns=now,
                host_clock_id=scene.host_clock_id,
            ),
        )

    async def producer():
        while True:
            if state.running:
                offer()
            await asyncio.sleep(0.25)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(producer())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    owner = ExpansionOwner(
        authorize=authorize, scene=scene, scene_context=lambda: dict(context)
    )
    install_expansion(
        app, ExpansionFlags(scene=True, replay=True, usability=True), owner
    )

    @app.get("/")
    def entry(request: Request):
        local(request)
        response = RedirectResponse("/extensions")
        response.headers["Cache-Control"] = "no-store"
        response.set_cookie("i0_cone_demo", cookie, httponly=True, samesite="strict")
        return response

    state.app, state.owner, state.offer = app, owner, offer
    return state


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(
        description="Isolated cone display demo; no real producer"
    )
    parser.add_argument("--port", type=int, default=4192)
    args = parser.parse_args()
    uvicorn.run(
        compose_demo(port=args.port).app,
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
    )
