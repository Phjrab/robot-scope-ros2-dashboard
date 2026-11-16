"""Explicit local expansion workbench. No robot application, ROS or network clients."""

import argparse
from contextlib import asynccontextmanager
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from robot_dashboard.expansion_contracts import FusionProposal, MapSourceDescriptor
from robot_dashboard.expansion_services.catalogue import (
    CatalogueAdapter,
    ResolvedSource,
)
from robot_dashboard.expansion_services.export import BundleStore
from robot_dashboard.expansion_services.jobs import FusionJobManager
from robot_dashboard.expansion_services.router import create_router
from robot_dashboard.multimap_core.contract_adapter import solve_contract
from robot_dashboard.pcd_editing.store import SourceAsset, _digest, _open_regular
from robot_dashboard.pcd_editing.pcd import _read_header
from .access import AccessPolicy
from .server import create_app as trajectory_app
from .maps import pcd_bytes

STATIC = Path(__file__).resolve().parents[1] / "static"


def create_app(root, *, synthetic_demo=False, access=None):
    access = access or AccessPolicy()
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    sources = {}
    if synthetic_demo:
        from robot_dashboard.expansion_contracts.fixtures import source

        rng = np.random.default_rng(425)
        cloud = rng.uniform([-2, -1, -0.5], [2, 2, 1], (1200, 3))
        for i in (1, 2):
            path = root / f"synthetic-{i}.pcd"
            raw = pcd_bytes(cloud + ([0, 0, 0] if i == 1 else [0.12, -0.08, 0.03]))
            if not path.exists():
                path.write_bytes(raw)
            elif path.read_bytes() != raw:
                raise ValueError("SYNTHETIC_SOURCE_CHANGED")
            descriptor = replace(
                source(i, _digest(path)),
                point_count=len(cloud),
                acquisition={
                    "origin": "generated synthetic fixture",
                    "display_name": f"합성 지도 {i}",
                },
            )
            sources[descriptor.map_id] = ResolvedSource(
                descriptor,
                SourceAsset(
                    descriptor.map_id, descriptor.revision, path, descriptor.frame_id
                ),
            )
    manifest = root / "sources.json"
    if manifest.exists():
        for item in json.loads(manifest.read_text(encoding="utf-8")):
            descriptor = MapSourceDescriptor.from_dict(item["descriptor"])
            path = (root / item["file"]).resolve()
            if not path.is_relative_to(root) or descriptor.map_id in sources:
                raise ValueError("INVALID_LOCAL_SOURCE")
            sources[descriptor.map_id] = ResolvedSource(
                descriptor,
                SourceAsset(
                    descriptor.map_id, descriptor.revision, path, descriptor.frame_id
                ),
                item.get("lineage", {}),
            )

    def resolve(map_id):
        return sources[map_id] if map_id in sources else bundle.reload(map_id)

    def preview(d):
        path = resolve(d.map_id).asset.path
        with _open_regular(path, 256 * 1024**2) as stream:
            _, _, dtype, count, _ = _read_header(
                stream, path.stat().st_size, 20_000_000
            )
            stride = max(1, int(np.ceil(count / 300)))
            points = []
            for offset in range(0, count, 8192):
                size = min(8192, count - offset)
                records = np.frombuffer(stream.read(size * dtype.itemsize), dtype=dtype)
                if len(records) != size:
                    raise ValueError("TRUNCATED_SOURCE")
                records = records[(-offset) % stride :: stride]
                xyz = np.column_stack([records[n] for n in ("x", "y", "z")])
                points.extend(xyz[np.isfinite(xyz).all(axis=1)].ravel().tolist())
        if _digest(path) != d.sha256:
            raise ValueError("SOURCE_CONTENT_CHANGED")
        return dict(
            schema="robot-scope.multimap-ui.v1",
            units="m",
            input_pin=dict(
                id=d.map_id,
                revision=d.revision,
                sha256=d.sha256,
                session_id=d.mapping_session_id,
            ),
            points=points,
        )

    catalogue = CatalogueAdapter(
        lambda: [*sources, *(row["id"] for row in bundle.list())], resolve, preview
    )
    bundle = BundleStore(root / "merged", catalogue)

    def solve(request, resolved, cancel, progress, *, job_id):
        paths = {s.descriptor.map_id: s.asset.path for s in resolved}
        return solve_contract(
            request,
            lambda d: paths[d["map_id"]],
            FusionProposal,
            job_id=job_id,
            cancel_token=cancel,
            progress=lambda e: progress(min(0.95, e["completed_pairs"] / 28)),
        )

    trajectory = trajectory_app(root / "trajectory", access=access)
    manager = FusionJobManager(catalogue, solve, bundle)

    @asynccontextmanager
    async def lifespan(app):
        try:
            async with trajectory.router.lifespan_context(trajectory):
                yield
        finally:
            manager.close()

    app = FastAPI(lifespan=lifespan)
    app.state.trajectory = trajectory
    app.state.manager = manager

    @app.middleware("http")
    async def boundary(request, call_next):
        try:
            access.authorize(request)
            if request.method not in {"GET", "HEAD"}:
                access.mutation(request)
            if request.url.path.startswith("/api/v1/extensions/scene/"):
                raise HTTPException(404, "FEATURE_DISABLED")
        except HTTPException as exc:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(
        create_router(
            manager,
            catalogue,
            None,
            bundle,
            authorize=access.authorize,
            require_origin=access.mutation,
        )
    )

    @app.get("/")
    def entry():
        # Serve only the dashboard shell; operational APIs remain absent locally.
        return FileResponse(
            STATIC / "index.html", headers={"Cache-Control": "no-store"}
        )

    @app.get("/extensions", response_class=HTMLResponse)
    def extensions():
        config = dict(
            flags=dict(multimap=True, replay=True, usability=True),
            auth="AUTHENTICATED_LAN" if access.authorities else "LOCAL_ONLY",
            analysis_local=True,
        )
        html = (STATIC / "features/expansion/index.html").read_text(encoding="utf-8")
        html = html.replace("__I0_CONFIG__", json.dumps(config))
        if synthetic_demo:
            html = html.replace(
                "<h1>확장 기능</h1>", "<h1>확장 기능 · 로컬 합성 시험</h1>"
            )
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    app.mount("/analysis", trajectory)
    app.mount("/static", StaticFiles(directory=STATIC))
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--allow-host",
        action="append",
        default=[],
        help="Exact allowed Host, including port; repeat for each address",
    )
    parser.add_argument(
        "--allow-network",
        action="append",
        default=[],
        help="Allowed private client CIDR, e.g. 192.168.0.0/24",
    )
    parser.add_argument(
        "--password-file",
        type=Path,
        help="Private file with a random 32+ character password; username is review",
    )
    parser.add_argument("--ssl-certfile", type=Path)
    parser.add_argument("--ssl-keyfile", type=Path)
    parser.add_argument("--synthetic-demo", action="store_true")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not args.allow_host:
        parser.error(
            "Network binding requires --allow-host, --allow-network and --password-file"
        )
    if bool(args.ssl_certfile) != bool(args.ssl_keyfile):
        parser.error("Both TLS certificate and key are required")
    try:
        access = AccessPolicy(
            authorities=args.allow_host,
            password=args.password_file.read_text(encoding="ascii").strip()
            if args.password_file
            else None,
            networks=args.allow_network,
        )
    except (ValueError, OSError):
        parser.error("Invalid network access configuration or password file")
    import uvicorn

    uvicorn.run(
        create_app(args.root, synthetic_demo=args.synthetic_demo, access=access),
        host=args.host,
        port=args.port,
        proxy_headers=False,
        ssl_certfile=str(args.ssl_certfile) if args.ssl_certfile else None,
        ssl_keyfile=str(args.ssl_keyfile) if args.ssl_keyfile else None,
    )


if __name__ == "__main__":
    main()
