"""Explicit localhost SYNTHETIC test host; no product runtime/ROS imports."""

from contextlib import asynccontextmanager
from dataclasses import replace
import hmac
from pathlib import Path
import secrets
import tempfile

from fastapi import FastAPI, HTTPException, Request

from robot_dashboard.expansion_contracts import FusionProposal
from robot_dashboard.expansion_contracts.fixtures import envelope, source, obstacle
from robot_dashboard.expansion_contracts.messages import IDENTITY
from robot_dashboard.expansion_services.catalogue import (
    CatalogueAdapter,
    ResolvedSource,
)
from robot_dashboard.expansion_services.export import BundleStore
from robot_dashboard.expansion_services.jobs import FusionJobManager
from robot_dashboard.expansion_services.router import create_router
from robot_dashboard.expansion_services.scene import SceneSnapshotService
from robot_dashboard.pcd_editing.store import SourceAsset, _digest


def write_synthetic_pcd(path, *, normals=False, offset=0):
    import numpy as np

    names = ["x", "y", "z"] + (
        ["normal_x", "normal_y", "normal_z", "intensity"] if normals else []
    )
    records = np.zeros(3, dtype=[(name, "<f4") for name in names])
    records["x"], records["y"] = [offset, offset + 1, offset + 1], [0, 0, 1]
    if normals:
        records["normal_x"], records["intensity"] = 1, [10, 20, 30]
    header = (
        "VERSION 0.7\nFIELDS "
        + " ".join(names)
        + "\nSIZE "
        + " ".join(["4"] * len(names))
        + "\nTYPE "
        + " ".join(["F"] * len(names))
        + "\nCOUNT "
        + " ".join(["1"] * len(names))
        + "\nWIDTH 3\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS 3\nDATA binary\n"
    )
    Path(path).write_bytes(header.encode() + records.tobytes())
    return [dict(name=n, size=4, type="F", count=1) for n in names]


def fixture_solver(request, sources, cancel, progress, *, job_id):
    """Plumbing fixture. Identity is never claimed to be estimated registration."""
    progress(0.25)
    return FusionProposal(
        **envelope(epoch=request.source_epoch),
        job_id=job_id,
        proposal_revision=1,
        state="SOLVED_CANDIDATE",
        anchor_source_key=request.anchor_source_key,
        T_fused_source={s.descriptor.key: list(IDENTITY) for s in sources},
        pairwise_edges=[],
        connected_components=[[s.descriptor.key for s in sources]],
        quality={"registration": "NOT_RUN"},
        ambiguous_candidates=[],
        warnings=["SYNTHETIC identity fixture; no solver/quality validation"],
        input_pins=request.source_pins,
        solver_version="c1-synthetic-identity",
        elapsed_ms=0.0,
    )


def create_test_host(root, token):
    if not isinstance(token, str) or len(token) < 24:
        raise ValueError("explicit test bearer must have at least 24 characters")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    resolved = {}
    for index in (1, 2):
        path = root / f"synthetic-{index}.pcd"
        schema = write_synthetic_pcd(path, offset=index)
        descriptor = replace(source(index, _digest(path)), point_schema=schema)
        resolved[descriptor.map_id] = ResolvedSource(
            descriptor,
            SourceAsset(
                descriptor.map_id, descriptor.revision, path, descriptor.frame_id
            ),
        )
    catalogue = CatalogueAdapter(lambda: list(resolved), lambda i: resolved[i])
    store = BundleStore(root / "bundles", catalogue)
    manager = FusionJobManager(catalogue, fixture_solver, store)
    frame = obstacle()
    scene = SceneSnapshotService(frame.map_binding, host_clock_id="test-host")
    scene.ingest("obstacle_frame", frame.to_dict())

    def authorize(request: Request):
        if request.client is None or request.client.host not in {
            "127.0.0.1",
            "::1",
            "testclient",
        }:
            raise HTTPException(403, "localhost test host only")
        if not hmac.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + token
        ):
            raise HTTPException(401, "test authentication required")

    def origin(request: Request):
        if request.headers.get("origin") != "http://" + request.headers.get("host", ""):
            raise HTTPException(403, "exact same-origin required by fixture host")

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            manager.close()

    app = FastAPI(title="C1 SYNTHETIC offline fixture host", lifespan=lifespan)
    app.include_router(
        create_router(
            manager, catalogue, scene, store, authorize=authorize, require_origin=origin
        )
    )
    app.state.c1 = (manager, catalogue, scene, store)
    return app


def main():
    import uvicorn

    bearer = secrets.token_urlsafe(32)
    print("SYNTHETIC localhost test bearer:", bearer, flush=True)
    with tempfile.TemporaryDirectory(prefix="c1-localhost-") as directory:
        uvicorn.run(
            create_test_host(directory, bearer),
            host="127.0.0.1",
            port=8765,
            limit_concurrency=16,
            backlog=16,
        )


if __name__ == "__main__":
    main()
