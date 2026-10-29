"""Explicit exact-SHA composition, separate from mock/unit tests and native ROS.

Run after exporting pins read-only (see prepare_dependencies.py). A reported
consumer FAIL is expected evidence, never relabeled end-to-end PASS.
"""

import argparse
import asyncio
import copy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
import time

import numpy as np

from robot_dashboard.expansion_contracts import (
    CollisionAssessment,
    ContractError,
    FusionProposal,
    ObstacleFrame,
    canonical,
)
from robot_dashboard.expansion_contracts.fixtures import source, request
from robot_dashboard.expansion_contracts.time_binding import (
    ClockBinding,
    normalize_collision_assessment,
)
from robot_dashboard.expansion_services.catalogue import (
    CatalogueAdapter,
    ResolvedSource,
    Conflict,
    validate_dag,
)
from robot_dashboard.expansion_services.export import BundleStore
from robot_dashboard.expansion_services.jobs import FusionJobManager
from robot_dashboard.expansion_services.router import create_router
from robot_dashboard.expansion_services.scene import SceneSnapshotService
from robot_dashboard.pcd_editing.store import SourceAsset, _digest
from robot_dashboard.pcd_editing.pcd import _read_header
from tests.expansion_services.http_client import TestClient

HERE = Path(__file__).parent


def dependencies(root):
    import robot_dashboard
    import experiments.expansion_20261029

    pins = json.loads((HERE / "pins.json").read_text())
    for role, sha in pins.items():
        path = root / role
        assert (path / ".c1-dependency-sha").read_text().strip() == sha, role
        assert path.stat().st_mode & 0o222 == 0, f"{role} dependency must be read-only"
        robot_dashboard.__path__.append(str(path / "robot_dashboard"))
        experiments.expansion_20261029.__path__.append(
            str(path / "experiments/expansion_20261029")
        )
    return pins


def node(node_binary, data):
    run = subprocess.run(
        [node_binary, str(HERE / "check_consumers.mjs")],
        input=json.dumps(data),
        text=True,
        capture_output=True,
        timeout=40,
    )
    if run.returncode:
        raise AssertionError(run.stderr)
    return json.loads(run.stdout)


def records(path):
    with path.open("rb") as f:
        _, _, dtype, count, _ = _read_header(f, path.stat().st_size, 20000000)
        return np.frombuffer(f.read(), dtype=dtype), count


def map_flow(root, deps, node_binary):
    from contextlib import asynccontextmanager
    from fastapi import FastAPI, HTTPException, Request
    from robot_dashboard.multimap_core.contract_adapter import solve_contract
    from experiments.expansion_20261029.d1_multimap.generate import fixture

    raw, resolver, poses = fixture(root, count=400)
    resolved = {}
    for i, d in enumerate(raw[:2]):
        path = resolver(d)
        data, count = records(path)
        wire = replace(
            source(i + 1, d["sha256"]),
            revision=d["sha256"],
            point_count=count,
            mapping_session_id=f"{101+i:024x}",
            point_schema=[
                dict(name=n, size=4, type="F", count=1) for n in data.dtype.names
            ],
            acquisition={"origin": "SYNTHETIC D1 generator"},
        )
        resolved[wire.map_id] = ResolvedSource(
            wire, SourceAsset(wire.map_id, wire.revision, path, wire.frame_id)
        )
    before = {k: _digest(s.asset.path) for k, s in resolved.items()}
    catalogue = CatalogueAdapter(lambda: list(resolved), lambda k: resolved[k])
    store = BundleStore(root / "bundles", catalogue)

    def solve(req, sources, cancel, progress, *, job_id):
        paths = {s.descriptor.map_id: s.asset.path for s in sources}
        return solve_contract(
            req,
            lambda d: paths[d["map_id"]],
            FusionProposal,
            job_id=job_id,
            cancel_token=cancel,
            progress=lambda event: progress(min(0.95, event["completed_pairs"])),
        )

    manager = FusionJobManager(catalogue, solve, store)

    def authorize(r: Request):
        if (
            r.client.host != "127.0.0.1"
            or r.headers.get("authorization")
            != "Bearer public-c1-composition-test-only"
        ):
            raise HTTPException(401)

    def origin(r: Request):
        if r.headers.get("origin") != "http://" + r.headers.get("host", ""):
            raise HTTPException(403)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            manager.close()

    app = FastAPI(lifespan=lifespan)
    app.include_router(
        create_router(
            manager,
            catalogue,
            SceneSnapshotService(
                {"map_id": "a" * 24, "revision": "b" * 64, "generation": 0}
            ),
            store,
            authorize=authorize,
            require_origin=origin,
        )
    )
    with TestClient(app) as client:
        result = node(
            node_binary,
            dict(
                mode="map",
                deps=str(deps),
                url=client.url,
                poses=[p.reshape(-1).tolist() for p in poses[:2]],
            ),
        )
        manifest = store.get(result["export_id"])
        job = manager.status(result["job_id"])
        output, count = records(store.root / manifest["id"] / "map.pcd")
        assert count == 800
        offset = 0
        for s in resolved.values():
            original, n = records(s.asset.path)
            t = np.asarray(job["proposal"]["T_fused_source"][s.descriptor.key]).reshape(
                4, 4
            )
            xyz = (
                np.column_stack([original[k] for k in ("x", "y", "z")]) @ t[:3, :3].T
                + t[:3, 3]
            )
            normals = (
                np.column_stack(
                    [original[k] for k in ("normal_x", "normal_y", "normal_z")]
                )
                @ t[:3, :3].T
            )
            np.testing.assert_allclose(
                np.column_stack(
                    [output[k][offset : offset + n] for k in ("x", "y", "z")]
                ),
                xyz,
                atol=1e-6,
            )
            np.testing.assert_allclose(
                np.column_stack(
                    [
                        output[k][offset : offset + n]
                        for k in ("normal_x", "normal_y", "normal_z")
                    ]
                ),
                normals,
                atol=1e-6,
            )
            np.testing.assert_array_equal(
                output["intensity"][offset : offset + n], original["intensity"]
            )
            offset += n
        assert before == {k: _digest(s.asset.path) for k, s in resolved.items()}
        assert (
            _digest(store.root / manifest["id"] / "map.pcd")
            == manifest["output_hashes"]["map.pcd"]
        )
        reloaded = store.reload(manifest["id"])
        try:
            validate_dag([reloaded, next(iter(resolved.values()))])
        except Conflict:
            pass
        else:
            raise AssertionError("shared-root fusion must reject")
        try:
            manager.export(result["job_id"], "stale", 1)
        except Conflict:
            pass
        else:
            raise AssertionError("stale apply must reject")
        # Real D1 job cancellation (no fake solver); result publication is fenced.
        cancel_req = replace(
            request(
                [s.descriptor for s in resolved.values()], request_id="actual-d1-cancel"
            ),
            options={},
        )
        canceled = manager.enqueue(cancel_req)
        manager.cancel(canceled["job_id"])
        deadline = time.monotonic() + 5
        while manager._outstanding and time.monotonic() < deadline:
            time.sleep(0.005)
        assert manager.status(canceled["job_id"])["state"] == "CANCELED"
        assert manager.status(canceled["job_id"])["proposal"] is None
        result.update(
            points=count,
            attributes=list(output.dtype.names),
            source_hashes=before,
            output_hashes=manifest["output_hashes"],
            shared_root="REJECTED",
            stale_apply="REJECTED",
            cancel="CANCELED",
            solver=job["proposal"]["solver_version"],
            list_reload="PASS",
            frozen=True,
        )
    assert not manager._worker.is_alive()
    return result


async def observation_flow(deps, node_binary):
    from robot_dashboard.obstacle_fusion_core.core import process_lidar, Tracker
    from experiments.expansion_20261029.d2_perception.scenarios import (
        scene as lidar_scene,
        metadata,
    )
    from robot_dashboard.collision_geometry_core import assess
    from experiments.expansion_20261029.d3_collision_sim.fixtures import model, state
    from robot_dashboard.obstacle_runtime_adapter.messages import Identity, pointcloud2
    from robot_dashboard.obstacle_runtime_adapter.runtime import RuntimeAdapter
    from robot_dashboard.obstacle_runtime_adapter.isolation import RuntimeConfig
    from robot_dashboard.obstacle_runtime_adapter.c1_ports import (
        C1ObstacleProjection,
        C1SceneSink,
    )
    from robot_dashboard.obstacle_runtime_adapter.command import (
        Binding,
        constraint_from_d3,
    )

    now = [1_000_000_010]
    meta = metadata()
    meta["calibration_id"] = "synthetic-lidar-calibration"
    points, ground, _ = lidar_scene(cones=1, body=False)
    tracker = Tracker()
    assessments = []
    counts = []

    class D2Port:
        def process(self, sample):
            m = {
                **meta,
                **{
                    k: sample.identity.packet()[k]
                    for k in (
                        "frame_key",
                        "stamp_ns",
                        "source_epoch",
                        "sequence",
                        "clock_domain",
                        "evidence_kind",
                        "map_binding",
                    )
                },
                "received_monotonic_ns": sample.identity.received_ns,
                "host_clock_id": sample.identity.receipt_clock_id,
            }
            observation = process_lidar(sample.payload["xyz_m"], m, ground=ground)
            result = tracker.step(observation)
            frame = result["obstacle_frame"]
            ObstacleFrame.from_dict(frame)
            robot = state()
            robot.update(
                {
                    k: frame[k]
                    for k in (
                        "source_epoch",
                        "frame_key",
                        "stamp_ns",
                        "clock_domain",
                        "map_binding",
                        "sequence",
                        "host_clock_id",
                        "received_monotonic_ns",
                    )
                }
            )
            robot["joint_stamp_ns"] = frame["stamp_ns"]
            assessments.append(
                assess(
                    model(),
                    robot,
                    frame,
                    now_stamp_ns=int(frame["stamp_ns"]),
                    now_clock_domain=frame["clock_domain"],
                    coverage="SPARSE",
                )
            )
            counts.append(len(sample.payload["xyz_m"]))
            return frame

    v2 = SceneSnapshotService(
        meta["map_binding"],
        host_clock_id="fixture-host",
        schema_version="0.2",
        clock=lambda: now[0],
    )
    projection = C1ObstacleProjection(ObstacleFrame)
    runtime = RuntimeAdapter(
        d2=D2Port(),
        scene_sink=C1SceneSink(v2, obstacle_projection=projection),
        validate_obstacle=projection,
        source_epochs={"lidar": "synthetic-1"},
        binding=("a" * 24, "b" * 64, "tf-synthetic", 0),
        receipt_clock_id="fixture-host",
        config=RuntimeConfig(mode="synthetic"),
        clock_ns=lambda: now[0],
    )
    identity = Identity(
        "lidar",
        "synthetic-1",
        1,
        "1000000000",
        "fixture-clock",
        "odom",
        1000000000,
        "fixture-host",
        "tf-synthetic",
        "a" * 24,
        "b" * 64,
    )

    def message(identity):
        return {
            "header": {
                "stamp": {
                    "sec": int(identity.stamp_ns) // 10**9,
                    "nanosec": int(identity.stamp_ns) % 10**9,
                },
                "frame_id": "odom",
            },
            "fields": [
                {"name": n, "offset": i * 4, "datatype": 7, "count": 1}
                for i, n in enumerate(("x", "y", "z"))
            ],
            "width": len(points),
            "height": 1,
            "point_step": 12,
            "row_step": len(points) * 12,
            "is_bigendian": False,
            "data": np.asarray(points, dtype="<f4").tobytes(),
        }

    async def offer(i):
        assert runtime.offer_raw(message(i), i, pointcloud2, origin_m=(0, 0, 0))
        for _ in range(500):
            if (
                runtime.latest_scene
                and runtime.latest_scene["sequence"] == i.sequence
                and runtime.latest_scene["source_epoch"] == i.source_epoch
            ):
                return
            if runtime.worker.error:
                raise AssertionError(runtime.health())
            await asyncio.sleep(0.005)
        raise AssertionError(runtime.health())

    runtime.start()
    try:
        await offer(identity)
        packet4 = runtime.latest_scene
        raw = assessments[-1]
        assert raw["severity"] == "UNKNOWN", raw
        binding = ClockBinding(
            "fixture-clock",
            "synthetic-1",
            "fixture-host",
            0,
            0,
            "explicit-synthetic-shared-time",
        )
        converted = normalize_collision_assessment(raw, binding=binding)
        assert (
            converted["freshness"]["time_conversion"]["original_interval"]
            == raw["validity_interval"]
        )
        assert converted["obstacle_frame_ref"] == {
            **raw["obstacle_frame_ref"],
            "received_monotonic_ns": str(
                raw["obstacle_frame_ref"]["received_monotonic_ns"]
            ),
        }
        assert v2.ingest("collision_assessment", converted)
        packet = v2.snapshot()
        assert packet["collision_assessment"]["severity"] == "UNKNOWN"
        assert (
            packet["collision_assessment"]["validity_interval"]["end_monotonic_ns"]
            == raw["validity_interval"]["until_ns"]
        )
        assert counts == [len(points)]
        assert packet4["collision_assessment"] is None
        legacy = SceneSnapshotService(
            meta["map_binding"], host_clock_id="fixture-host", clock=lambda: now[0]
        )
        C1SceneSink(legacy, obstacle_projection=projection).ingest(packet4)
        consumers = node(
            node_binary,
            dict(mode="scene", deps=str(deps), packets=[legacy.snapshot(), packet]),
        )
        assert [v["reason"] for v in consumers] == [
            "C1_DISPLAY_PROFILE_REQUIRED",
            "C1_VERSION_UNSUPPORTED",
        ]
        try:
            constraint_from_d3(
                converted,
                validate_assessment=CollisionAssessment.from_dict,
                binding=Binding(
                    "offline-goal",
                    0,
                    "offline-lease",
                    "synthetic-1",
                    "odom",
                    "fixture-host",
                ),
                command_sequence=1,
            )
        except ValueError as exc:
            constraint_error = str(exc)
        else:
            raise AssertionError("unbound command constraint must reject")
        assert constraint_error == "D3_COMMAND_CONTEXT_MISMATCH"
        # Exact D3 fault inputs: unavailable calibration, stale and map mismatch.
        cases = {}
        for name, robot, frame, stamp, clock in (
            (
                "calibration_unknown",
                {**state(), "calibration_known": False},
                packet4["obstacle_frame"],
                10**9,
                "fixture-clock",
            ),
            ("stale", state(), packet4["obstacle_frame"], 2 * 10**9, "fixture-clock"),
            (
                "map_revision",
                state(),
                {
                    **packet4["obstacle_frame"],
                    "map_binding": {**meta["map_binding"], "revision": "c" * 64},
                },
                10**9,
                "fixture-clock",
            ),
            ("wrong_clock", state(), packet4["obstacle_frame"], 10**9, "other-clock"),
        ):
            bad = assess(
                model(),
                robot,
                frame,
                now_stamp_ns=stamp,
                now_clock_domain=clock,
                coverage="SPARSE",
            )
            assert bad["severity"] == "UNKNOWN" and not bad["validity_interval"]
            cases[name] = bad["freshness"]
        assert not runtime.offer_raw(message(identity), identity, pointcloud2)
        # A newly published calibration identity is a new observation; old pairing must disappear.
        meta["calibration_id"] = "synthetic-lidar-calibration-2"
        now[0] = 1_000_000_030
        await offer(
            replace(
                identity, sequence=2, stamp_ns="1000000020", received_ns=1_000_000_020
            )
        )
        assert (
            v2.snapshot()["obstacle_frame"]["calibration_id"] == meta["calibration_id"]
        )
        assert v2.snapshot()["collision_assessment"] is None
        cases["calibration_change"] = {
            "old_assessment_pairing": "REJECTED",
            "physical_accuracy": "NOT_RUN",
        }
        now[0] = 2 * 10**9
        assert not runtime.offer_raw(
            message(identity), replace(identity, sequence=2), pointcloud2
        )
        assert v2.snapshot()["obstacle_frame"] is None
        expired = v2.snapshot()
        now[0] = 10**9 + 10
        new = replace(identity, source_epoch="synthetic-2", sequence=0)
        runtime.rebind(source_epochs={"lidar": "synthetic-2"}, binding=identity.binding)
        v2.reset_source("obstacle_frame", "synthetic-2")
        pending = v2.snapshot()
        await offer(new)
        assert v2.snapshot()["obstacle_frame"]["sequence"] == 0
        assert v2.snapshot()["collision_assessment"] is None
        assert not runtime.offer_raw(message(identity), identity, pointcloud2)
        v2.reset(
            {**meta["map_binding"], "revision": "c" * 64, "generation": 1}, "map-2"
        )
        assert not v2.ingest("obstacle_frame", packet4["obstacle_frame"])
        sizes = []
        for n in (0, 1, 4, 12, 16):
            p, g, _ = lidar_scene(cones=n, wall=False, body=False)
            frame = Tracker().step(process_lidar(p, meta, ground=g))["obstacle_frame"]
            service = SceneSnapshotService(
                meta["map_binding"],
                host_clock_id="fixture-host",
                schema_version="0.2",
                clock=lambda: now[0],
            )
            try:
                service.ingest("obstacle_frame", frame)
                outcome = "ACCEPTED"
            except ContractError as exc:
                outcome = str(exc)
            sizes.append(
                dict(
                    requested_cones=n,
                    input_points=len(p),
                    objects=len(frame["obstacles"]),
                    frame_bytes=len(canonical(frame)),
                    snapshot_bytes=len(canonical(service.snapshot())),
                    outcome=outcome,
                )
            )
            if n == 0:
                empty = assess(
                    model(),
                    state(),
                    frame,
                    now_stamp_ns=10**9,
                    now_clock_domain="fixture-clock",
                    coverage="SPARSE",
                )
                assert empty["severity"] == "UNKNOWN"
        # Generated display-only examples from the real service, kept separate from safety input.
        display = SceneSnapshotService(
            meta["map_binding"],
            host_clock_id="fixture-host",
            schema_version="0.2",
            clock=lambda: now[0],
        )
        refs = [
            display.publish_asset(
                role,
                "synthetic-display",
                canonical({"points_m": [[0, 0, 0]], "evidence_kind": "SYNTHETIC"}),
                media_type="application/json",
            )
            for role in ("saved_reference_cloud", "live_cloud", "costmap")
        ]
        from dataclasses import fields
        from robot_dashboard.expansion_contracts.messages import Observation

        envelope = {
            f.name: packet4["obstacle_frame"][f.name] for f in fields(Observation)
        }
        for slot in ("global_path", "controller_local_trajectory"):
            display.ingest(
                slot,
                {
                    **envelope,
                    "data": {
                        "points_m": [[0, 0, 0], [1, 0, 0]],
                        "origin": "GENERATED_DISPLAY_EXAMPLE",
                    },
                    "health": {"state": "SYNTHETIC"},
                },
            )
        display.ingest(
            "costmap_snapshot",
            {
                **envelope,
                "data": {
                    "asset_ref": refs[-1],
                    "origin": "GENERATED_DISPLAY_EXAMPLE_NOT_NAV2",
                },
                "health": {"state": "SYNTHETIC"},
            },
        )
        return dict(
            actual_core="D2/D3 PASS on SYNTHETIC points",
            actual_c4_observation="PASS",
            c4_assessment_forwarding="FAIL: current C1SceneSink forwards obstacle only",
            c4_constraint="FAIL: " + constraint_error,
            c3_consumers=consumers,
            full_chain="FAIL",
            cases=cases,
            input_points=len(points),
            safety_input_points=counts[0],
            severity=raw["severity"],
            freshness=raw["freshness"],
            original_interval=raw["validity_interval"],
            canonical_interval=converted["validity_interval"],
            assessment_bytes=len(canonical(converted)),
            c4_packet_bytes=len(canonical(packet4)),
            snapshot_bytes=len(canonical(packet)),
            sizes=sizes,
            examples={
                "ready_partial": packet,
                "expired": expired,
                "pending_restart": pending,
                "unavailable_new_map": v2.snapshot(),
                "generated_display_assets_and_plans": display.snapshot(),
            },
            native_ros="NOT_RUN",
            actual_robot="NOT_RUN",
        )
    finally:
        await runtime.close()
        assert runtime.worker.closed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deps", type=Path, required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pins = dependencies(args.deps)
    with tempfile.TemporaryDirectory(prefix="c1-actual-composition-") as root:
        result = {
            "pins": pins,
            "evidence_kind": "SYNTHETIC",
            "map": map_flow(Path(root), args.deps, args.node),
        }
        result["observation"] = asyncio.run(observation_flow(args.deps, args.node))
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "observation"}))
    print(
        json.dumps({k: v for k, v in result["observation"].items() if k != "examples"})
    )


if __name__ == "__main__":
    main()
