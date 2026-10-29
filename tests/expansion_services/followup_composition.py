"""Replay latest published owner ports; exit 2 for a reproduced consumer failure.

No output rewriting or engine doubles. Generated inputs, explicit clock binding,
loopback HTTP and memory-only command demonstrations are separately identified.
Run manually after prepare_dependencies --pins followup_pins.json; never fetches.
"""

import argparse
import asyncio
import copy
from dataclasses import asdict, replace
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

import numpy as np

from robot_dashboard.expansion_contracts import (
    CollisionAssessment,
    ObstacleFrame,
    canonical,
)
from robot_dashboard.expansion_contracts.time_binding import (
    ClockBinding,
    normalize_collision_assessment,
)
from robot_dashboard.expansion_services.router import create_router
from robot_dashboard.expansion_services.scene import SceneSnapshotService
from tests.expansion_services.composition import map_flow
from tests.expansion_services.http_client import TestClient

HERE = Path(__file__).parent


def dependencies(root):
    import robot_dashboard
    import experiments.expansion_20261029

    pins = json.loads((HERE / "followup_pins.json").read_text())
    for role, sha in pins.items():
        path = root / role
        assert (path / ".c1-dependency-sha").read_text().strip() == sha
        assert path.stat().st_mode & 0o222 == 0
        robot_dashboard.__path__.append(str(path / "robot_dashboard"))
        experiments.expansion_20261029.__path__.append(
            str(path / "experiments/expansion_20261029")
        )
    return pins


def point_message(points, identity):
    stamp = int(identity.stamp_ns)
    return dict(
        header=dict(
            stamp=dict(sec=stamp // 10**9, nanosec=stamp % 10**9), frame_id="odom"
        ),
        fields=[
            dict(name=n, offset=i * 4, datatype=7, count=1)
            for i, n in enumerate(("x", "y", "z"))
        ],
        width=len(points),
        height=1,
        point_step=12,
        row_step=len(points) * 12,
        is_bigendian=False,
        data=np.asarray(points, dtype="<f4").tobytes(),
    )


def consumer_http(deps, node, scene):
    from fastapi import FastAPI, HTTPException, Request

    def authorize(request: Request):
        if (
            request.client.host != "127.0.0.1"
            or request.headers.get("authorization")
            != "Bearer public-c1-composition-test-only"
        ):
            raise HTTPException(401)

    def no_writes(request: Request):
        raise HTTPException(403)

    app = FastAPI()
    app.include_router(
        create_router(
            None, None, scene, None, authorize=authorize, require_origin=no_writes
        )
    )
    with TestClient(app) as client:
        result = subprocess.run(
            [node, str(HERE / "check_followup_consumer.mjs")],
            input=json.dumps(dict(deps=str(deps), url=client.url)),
            capture_output=True,
            text=True,
            timeout=40,
        )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


async def observation(deps, node):
    from robot_dashboard.obstacle_fusion_core.consumer_port import C4CorePort
    from experiments.expansion_20261029.d2_perception.scenarios import (
        scene as lidar_scene,
        metadata,
    )
    from robot_dashboard.collision_geometry_core import assess
    from robot_dashboard.collision_geometry_core.contracts import (
        canonical_assessment,
        c4_constraint,
    )
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
        CommandGate,
        MockCommandSink,
        RawCommand,
    )

    now = [1_000_000_010]
    meta = metadata()
    points, ground, _ = lidar_scene(cones=1, body=False)
    identity = Identity(
        "lidar",
        "synthetic-1",
        1,
        "1000000000",
        "fixture-clock",
        "odom",
        1_000_000_000,
        "fixture-host",
        "tf-synthetic",
        "a" * 24,
        "b" * 64,
    )
    port = C4CorePort(
        canonical=canonical,
        validate_frame=ObstacleFrame.from_dict,
        geometry_context=lambda sample: dict(ground=ground),
        clock_ns=lambda: now[0],
        processing_clock_id="fixture-host",
    )
    v2 = SceneSnapshotService(
        meta["map_binding"],
        host_clock_id="fixture-host",
        schema_version="0.2",
        clock=lambda: now[0],
    )
    projection = C1ObstacleProjection(ObstacleFrame)
    runtime = RuntimeAdapter(
        d2=port,
        scene_sink=C1SceneSink(v2, obstacle_projection=projection),
        validate_obstacle=projection,
        source_epochs={"lidar": "synthetic-1"},
        binding=identity.binding,
        receipt_clock_id="fixture-host",
        config=RuntimeConfig(mode="synthetic"),
        clock_ns=lambda: now[0],
    )

    async def offer(i):
        assert runtime.offer_raw(
            point_message(points, i), i, pointcloud2, origin_m=(0, 0, 0)
        )
        for _ in range(500):
            if runtime.latest_scene and (
                runtime.latest_scene["sequence"],
                runtime.latest_scene["source_epoch"],
            ) == (i.sequence, i.source_epoch):
                return
            assert not runtime.worker.error, runtime.health()
            await asyncio.sleep(0.005)
        raise AssertionError(runtime.health())

    runtime.start()
    try:
        await offer(identity)
        packet4 = runtime.latest_scene
        frame = packet4["obstacle_frame"]
        full = port.last_result["obstacle_frame"]
        assert [o["geometry"] for o in frame["obstacles"]] == [
            o["geometry"] for o in full["obstacles"]
        ]
        # PointCloud2's actual port has no calibration metadata argument: keep it unknown.
        assert frame["calibration_id"] is None
        assert (
            v2.snapshot()["sources"]["obstacle_frame"]["calibration_status"]
            == "UNKNOWN"
        )
        robot = state()  # Explicit generated pose/joints; not native sensor state.
        motion = dict(
            ref=dict(command_sequence=1),
            command=dict(linear_x_mps=0.1, angular_z_radps=0.0, horizon_s=0.1),
        )
        raw = assess(
            model(),
            robot,
            frame,
            motion,
            now_stamp_ns=10**9,
            now_clock_domain="fixture-clock",
            coverage="SPARSE",
        )
        assert raw["schema_version"] == "0.2" and raw["severity"] == "UNKNOWN"
        assert not raw["validity_interval"]
        assert not raw["freshness"]["coverage"]["complete_for_motion"]
        binding = ClockBinding(
            "fixture-clock",
            "synthetic-1",
            "fixture-host",
            0,
            0,
            "explicit-synthetic-shared-time",
        )
        converted = canonical_assessment(
            raw, normalize=normalize_collision_assessment, clock_binding=binding
        )
        original = raw["freshness"]["source_validity_interval"]
        assert (
            converted["freshness"]["time_conversion"]["original_interval"] == original
        )
        assert (
            converted["validity_interval"]["end_monotonic_ns"] == original["until_ns"]
        )
        assert converted["received_monotonic_ns"] == raw["received_monotonic_ns"]
        assert converted["obstacle_frame_ref"] == raw["obstacle_frame_ref"]
        assert v2.ingest("collision_assessment", converted)
        snapshot = v2.snapshot()
        assert snapshot["collision_assessment"]["severity"] == "UNKNOWN"
        assert packet4["collision_assessment"] is None

        legacy = SceneSnapshotService(
            meta["map_binding"], host_clock_id="fixture-host", clock=lambda: now[0]
        )
        C1SceneSink(legacy, obstacle_projection=projection).ingest(packet4)
        consumers = [consumer_http(deps, node, service) for service in (legacy, v2)]

        trusted = Binding(
            "synthetic-goal",
            0,
            "synthetic-lease",
            "synthetic-1",
            json.dumps(converted["frame_key"], sort_keys=True, separators=(",", ":")),
            "fixture-host",
        )
        constraint = c4_constraint(
            converted,
            validate_canonical=CollisionAssessment.from_dict,
            consume=constraint_from_d3,
            binding=trusted,
            command_sequence=1,
            enforcement_mode="ACTIVE",
        )
        assert constraint.severity == "UNKNOWN" and constraint.valid_until_ns == int(
            original["until_ns"]
        )
        sink = MockCommandSink()
        checked = CommandGate(sink, trusted).apply(
            RawCommand(1, trusted, now[0], now[0] + 100_000_000, (0.1, 0.0, 0.0)),
            constraint,
            now_ns=now[0],
        )
        assert checked.hold and checked.velocity == (0.0, 0.0, 0.0)
        faults = {}
        for name, s, f, stamp, clock in (
            (
                "calibration_unknown",
                {**robot, "calibration_known": False},
                frame,
                10**9,
                "fixture-clock",
            ),
            ("stale", robot, frame, 2 * 10**9, "fixture-clock"),
            (
                "map_revision",
                robot,
                {**frame, "map_binding": {**meta["map_binding"], "revision": "c" * 64}},
                10**9,
                "fixture-clock",
            ),
            ("wrong_clock", robot, frame, 10**9, "other-clock"),
        ):
            bad = assess(
                model(),
                s,
                f,
                now_stamp_ns=stamp,
                now_clock_domain=clock,
                coverage="SPARSE",
            )
            assert bad["severity"] == "UNKNOWN" and not bad["validity_interval"]
            faults[name] = bad["freshness"]
        for name, bad_binding in (
            ("wrong_host_clock", replace(binding, host_clock_id="other")),
            ("wrong_source_epoch", replace(binding, source_epoch="other")),
        ):
            try:
                canonical_assessment(
                    raw,
                    normalize=normalize_collision_assessment,
                    clock_binding=bad_binding,
                )
            except ValueError as exc:
                faults[name] = str(exc)
            else:
                raise AssertionError(name)
        bad_ttl = copy.deepcopy(raw)
        bad_ttl["freshness"]["source_validity_interval"]["until_ns"] = "2000000000"
        try:
            canonical_assessment(
                bad_ttl, normalize=normalize_collision_assessment, clock_binding=binding
            )
        except ValueError as exc:
            faults["wrong_ttl"] = str(exc)
        else:
            raise AssertionError("oversized TTL accepted")
        now[0] = int(original["until_ns"]) + 1
        assert v2.snapshot()["collision_assessment"] is None
        faults["original_expiry"] = "SUPPRESSED_WITHOUT_TTL_RESTART"
        now[0] = 2 * 10**9
        assert v2.snapshot()["obstacle_frame"] is None
        assert not runtime.offer_raw(
            point_message(points, identity), identity, pointcloud2
        )
        now[0] = 1_000_000_010
        new = replace(identity, source_epoch="synthetic-2", sequence=0)
        runtime.rebind(source_epochs={"lidar": "synthetic-2"}, binding=identity.binding)
        v2.reset_source("obstacle_frame", "synthetic-2")
        assert v2.snapshot()["sources"]["obstacle_frame"]["status"] == "pending"
        await offer(new)
        assert v2.snapshot()["obstacle_frame"]["sequence"] == 0
        assert v2.snapshot()["collision_assessment"] is None
        assert not runtime.offer_raw(
            point_message(points, identity), identity, pointcloud2
        )
        faults["restart_sequence_reset"] = "NEW_EPOCH_ACCEPTED_OLD_EPOCH_REJECTED"
        v2.reset(
            {**meta["map_binding"], "generation": 1, "revision": "c" * 64}, "new-map"
        )
        assert not v2.ingest("obstacle_frame", frame)
        assert v2.snapshot()["obstacle_frame"] is None
        faults["map_reset_missing_input"] = "UNAVAILABLE_OLD_MAP_REJECTED"

        sizes = []
        for count in (0, 1, 4, 12, 16, 32):
            p, g, _ = lidar_scene(cones=count, wall=False, body=False)
            size_port = C4CorePort(
                canonical=canonical,
                validate_frame=ObstacleFrame.from_dict,
                geometry_context=lambda sample: dict(ground=g),
                clock_ns=lambda: now[0],
                processing_clock_id="fixture-host",
            )
            sample = pointcloud2(
                point_message(p, identity), identity, origin_m=(0, 0, 0)
            )
            assert len(sample.payload["xyz_m"]) == len(p)
            service = SceneSnapshotService(
                meta["map_binding"],
                host_clock_id="fixture-host",
                schema_version="0.2",
                clock=lambda: now[0],
            )
            wire = None
            try:
                wire = size_port.process(sample)
                assert [o["geometry"] for o in wire["obstacles"]] == [
                    o["geometry"]
                    for o in size_port.last_result["obstacle_frame"]["obstacles"]
                ]
                assert service.ingest("obstacle_frame", wire)
                outcome = "ACCEPTED_ALL_GEOMETRY"
            except ValueError as exc:
                outcome = str(exc)
            full_size = size_port.last_result["obstacle_frame"]
            sizes.append(
                dict(
                    requested_cones=count,
                    input_points=len(p),
                    objects=len(full_size["obstacles"]),
                    full_bytes=len(canonical(full_size)),
                    compact_bytes=len(canonical(wire)) if wire else None,
                    snapshot_bytes=len(canonical(service.snapshot())),
                    outcome=outcome,
                )
            )
            if count == 0:
                empty = assess(
                    model(),
                    robot,
                    wire,
                    now_stamp_ns=10**9,
                    now_clock_domain="fixture-clock",
                    coverage="SPARSE",
                )
                assert empty["severity"] == "UNKNOWN"
        return dict(
            actual_d2_owned_c4_port="PASS",
            input_points=len(points),
            calibration="UNKNOWN_NO_METADATA_IN_POINTCLOUD2_PORT",
            actual_d3_owned_c1_converter="PASS",
            severity=raw["severity"],
            coverage=raw["freshness"]["coverage"],
            original_interval=original,
            canonical_interval=converted["validity_interval"],
            snapshot_bytes=len(canonical(snapshot)),
            snapshot_sha256=hashlib.sha256(canonical(snapshot)).hexdigest(),
            c4_obstacle_sink="PASS",
            c4_old_sink_assessment="NOT_FORWARDED_EXPLICIT_D3_C1_PORT_USED",
            c3_http=consumers,
            d3_legacy_c4_constraint="PASS_UNKNOWN_PRESERVED",
            command_memory_only=asdict(checked),
            cases=faults,
            sizes=sizes,
        )
    finally:
        await runtime.close()
        assert runtime.worker.closed


def latest_runtime(deps):
    from robot_dashboard.expansion_runtime.intent import FinalIntentPort
    from robot_dashboard.expansion_runtime.ports import ingest_scene

    spec = importlib.util.spec_from_file_location(
        "c4_owner_fixtures", deps / "C4/tests/expansion_runtime/fixtures.py"
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    runtime, packet, state, clock = fixture.setup()
    result = fixture.run(runtime, packet, state)
    assert result.intent.reason == "UNSUPPORTED_D3_ASSESSMENT"
    assert result.intent.severity == "UNKNOWN" and runtime.mode == "ACTIVE_CONSTRAINT"
    assert (
        "d2_finished_monotonic_ns" in result.timing
        and "d3_finished_monotonic_ns" in result.timing
    )
    assert result.assessment is None
    service = SceneSnapshotService(
        runtime.context.map_binding,
        host_clock_id="fixture-host",
        schema_version="0.2",
        clock=clock,
    )
    try:
        ingest_scene(service, result)
    except ValueError as exc:
        scene_error = str(exc)
    else:
        raise AssertionError("invalid result ingested")
    assert scene_error == "NO_VALIDATED_SCENE_SAMPLE"
    port = FinalIntentPort(runtime.context, mode="ACTIVE_CONSTRAINT")
    checked = port.apply(
        result.intent,
        now_ns=clock(),
        issued_ns=clock(),
        expires_ns=clock() + 100_000_000,
    )
    assert checked.hold and checked.velocity == (0.0, 0.0, 0.0)
    return dict(
        result="FAIL",
        reason=result.intent.reason,
        active_mode_preserved=runtime.mode,
        scene_error=scene_error,
        timing=result.timing,
        command_memory_only=asdict(checked),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--deps", required=True, type=Path)
    p.add_argument("--node", required=True)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    pins = dependencies(args.deps)
    with tempfile.TemporaryDirectory(prefix="c1-followup-map-") as tmp:
        maps = map_flow(Path(tmp), args.deps, args.node)
    observations = asyncio.run(observation(args.deps, args.node))
    runtime = latest_runtime(args.deps)
    import robot_dashboard.multimap_core as d1
    import robot_dashboard.obstacle_fusion_core as d2
    import robot_dashboard.collision_geometry_core as d3
    import robot_dashboard.expansion_runtime as c4

    for role, module in (("D1", d1), ("D2", d2), ("D3", d3), ("C4", c4)):
        assert Path(module.__file__).is_relative_to(args.deps / role), module.__file__
    result = dict(
        pins=pins,
        sequence=["D1_C2_HTTP", "D2", "D3", "C4_RUNTIME"],
        map=maps,
        observation=observations,
        c4_runtime=runtime,
        full_chain="FAIL",
        local_ros_native="NOT_RUN",
        physical_robot="NOT_RUN",
        evidence_kind="SYNTHETIC_REAL_ALGORITHMS_AND_HTTP_WITH_SEPARATE_MEMORY_COMMAND_SINK",
    )
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            dict(
                map="PASS_FROZEN",
                observation_ports="PASS",
                full_chain="FAIL",
                output=str(args.output),
            )
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
