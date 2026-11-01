"""Latest actual owner profile. Historical profiles and failures remain intact.

Generated input fixtures are imported from C4; algorithms/DTOs are not copied.
Fault input mutation is explicitly separate from actual successful production.
"""

import argparse
import copy
from dataclasses import fields, replace, asdict
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types

from robot_dashboard.expansion_contracts import canonical
from robot_dashboard.expansion_contracts.messages import Observation
from robot_dashboard.expansion_services.scene import SceneSnapshotService
from robot_dashboard.expansion_services.router import create_router
from tests.expansion_services.composition import map_flow
from tests.expansion_services.http_client import TestClient

HERE = Path(__file__).parent
OWNER_PATHS = {
    "D1": [
        "robot_dashboard/multimap_core",
        "experiments/expansion_20261029/d1_multimap",
    ],
    "D2": ["robot_dashboard/obstacle_fusion_core"],
    "D3": ["robot_dashboard/collision_geometry_core"],
    "C4": [
        "robot_dashboard/expansion_runtime",
        "robot_dashboard/obstacle_runtime_adapter",
        "tests/expansion_runtime/fixtures.py",
        "tests/expansion_runtime/latest_fixtures.py",
    ],
    "C2": ["robot_dashboard/static/features/multimap_fusion"],
    "C3": ["robot_dashboard/static/features/obstacle_scene"],
}


def verify_exports(root, pins):
    receipt = {}
    for role, paths in OWNER_PATHS.items():
        target = root / role
        assert (target / ".c1-dependency-sha").read_text().strip() == pins[role]
        assert not target.stat().st_mode & 0o222
        entries = subprocess.check_output(
            ["git", "ls-tree", "-r", pins[role], "--", *paths], text=True
        )
        files = {}
        for line in entries.splitlines():
            metadata, name = line.split("\t")
            mode, kind, blob = metadata.split()
            assert mode in ("100644", "100755") and kind == "blob"
            path = target / name
            assert not path.stat().st_mode & 0o222
            data = path.read_bytes()
            assert (
                hashlib.sha1(
                    b"blob " + str(len(data)).encode() + b"\0" + data
                ).hexdigest()
                == blob
            ), name
            files[name] = blob
        assert files, role
        receipt[role] = dict(
            sha=pins[role],
            files=len(files),
            manifest_sha256=hashlib.sha256(canonical(files)).hexdigest(),
        )
    return receipt


def dependencies(root):
    import robot_dashboard
    import experiments.expansion_20261029

    pins = json.loads((HERE / "current_pins.json").read_text())
    verified = verify_exports(root, pins)
    for (
        role
    ) in OWNER_PATHS:  # C7 is documentation review only; never a module provider.
        robot_dashboard.__path__.append(str(root / role / "robot_dashboard"))
        experiments.expansion_20261029.__path__.append(
            str(root / role / "experiments/expansion_20261029")
        )
    package = types.ModuleType("c1_readonly_c4_inputs")
    package.__path__ = [str(root / "C4/tests/expansion_runtime")]
    sys.modules[package.__name__] = package
    fixture = importlib.import_module(package.__name__ + ".latest_fixtures")
    return pins, verified, fixture


def http_scene(service):
    from fastapi import FastAPI, HTTPException, Request

    def authorize(request: Request):
        if (
            request.client.host != "127.0.0.1"
            or request.headers.get("authorization")
            != "Bearer public-c1-composition-test-only"
        ):
            raise HTTPException(401)

    def origin(request: Request):
        raise HTTPException(403)

    app = FastAPI()
    app.include_router(
        create_router(
            None, None, service, None, authorize=authorize, require_origin=origin
        )
    )
    return TestClient(app)


def context(rt, service):
    return {
        **rt.context.map_binding,
        "stream_epoch": service.stream_epoch,
        "source_epoch": rt.context.source_epoch,
        "frame_id": rt.context.frame_id,
        "clock_domain": rt.mapping.source_domain,
        "units": "m",
        "calibration_id": "fixture-calibration",
    }


def capture(client, rt, service):
    path = "/api/v1/extensions/scene/snapshot"
    assert client.get(path).status_code == 401
    response = client.get(
        path, headers={"Authorization": "Bearer public-c1-composition-test-only"}
    )
    assert response.status_code == 200, response.text
    return dict(
        raw=response.text,
        context=context(rt, service),
        sha256=hashlib.sha256(response.content).hexdigest(),
        bytes=len(response.content),
    )


def expect_rejection(call, text=None):
    try:
        call()
    except (ValueError, TypeError) as exc:
        if text:
            assert text in str(exc), str(exc)
        return str(exc)
    raise AssertionError("expected rejection")


def hold(rt, result, clock):
    from robot_dashboard.expansion_runtime import FinalIntentPort

    gate = FinalIntentPort(rt.context, mode=rt.mode)
    command = gate.apply(
        result.intent,
        now_ns=clock(),
        issued_ns=clock(),
        expires_ns=clock() + 100_000_000,
    )
    assert result.intent.severity == "UNKNOWN" and rt.mode == "ACTIVE_CONSTRAINT"
    assert command.hold and command.velocity == (0.0, 0.0, 0.0)
    return asdict(command)


def rebind_inputs(rt, packet, state):
    """Explicit generated source event, not an assessment/output rewrite."""
    meta = copy.deepcopy(packet.meta)
    meta.update(
        source_epoch=rt.context.source_epoch,
        frame_key=dict(
            source_epoch=rt.context.source_epoch, frame_id=rt.context.frame_id
        ),
        map_binding=rt.context.map_binding,
    )
    evidence = copy.deepcopy(packet.sensor_evidence)
    for sensor in evidence.values():
        sensor["meta"] = copy.deepcopy(meta)
    state = {**state, **meta}
    return replace(
        packet, meta=meta, sensor_evidence=evidence, context_key=rt.context.key
    ), state


def size_faults(rt, result, clock):
    from robot_dashboard.expansion_runtime.canonical_ports import legacy_observation

    service = SceneSnapshotService(
        rt.context.map_binding,
        host_clock_id=rt.context.host_clock_id,
        schema_version="0.2",
        clock=clock,
    )
    frame = rt.ports.scene_obstacle(result.obstacle_frame)
    # Negative injections into an actual output. These are not additional sensor executions.
    large = copy.deepcopy(frame)
    large["health"]["fault_padding"] = "x" * (128 * 1024)
    wire_error = expect_rejection(lambda: canonical(large))
    compact_error = expect_rejection(lambda: rt.ports.scene_obstacle(large))
    legacy = legacy_observation(
        frame, validate=rt.ports.contracts.ObstacleFrame.from_dict
    )
    legacy["health"]["fault_padding"] = ""
    legacy["health"]["fault_padding"] = "x" * (16384 - len(canonical(legacy)))
    assert len(canonical(legacy)) == 16384
    normalized = rt.ports.time_binding.upgrade_observation(legacy)
    assert len(canonical(normalized)) > 16384
    normalization_error = expect_rejection(
        lambda: service.ingest("obstacle_frame", legacy)
    )
    assert service.snapshot()["obstacle_frame"] is None
    envelope = {f.name: frame[f.name] for f in fields(Observation)}
    generic = {**envelope, "data": {"fault_padding": ""}, "health": {}}
    generic["data"]["fault_padding"] = "x" * (16384 - len(canonical(generic)))
    for slot in (
        "robot_pose",
        "global_path",
        "controller_local_trajectory",
        "costmap_snapshot",
    ):
        assert service.ingest(slot, generic)
    frame["health"]["fault_padding"] = ""
    frame["health"]["fault_padding"] = "x" * (16384 - len(canonical(frame)))
    assert service.ingest("obstacle_frame", frame)
    assessment = copy.deepcopy(result.assessment)
    assessment["freshness"]["fault_padding"] = ""
    assessment["freshness"]["fault_padding"] = "x" * (
        16384 - len(canonical(assessment))
    )
    assert service.ingest("collision_assessment", assessment) is False
    assert sum(len(canonical(v)) for v in service._latest.values()) == 81920
    return dict(
        scope="FAULT_INJECTION_ON_ACTUAL_OUTPUT_NO_LIMIT_CHANGES",
        wire=wire_error,
        c4_compaction=compact_error,
        input_bytes=16384,
        normalized_bytes=len(canonical(normalized)),
        normalization=normalization_error,
        latest_storage_bytes=81920,
        sixth_sample="REJECTED_FALSE",
    )


def observation(root, node, f):
    rt, p, s, clock = f.setup()
    result = f.run(rt, p, s)  # No complete-coverage certificate fabricated.
    assert result.sensor_processed and result.assessment["schema_version"] == "0.2"
    assert result.assessment["severity"] == "UNKNOWN"
    assert not result.assessment["freshness"]["coverage"]["complete_for_motion"]
    interval = result.assessment["validity_interval"]
    assert (
        interval["end_monotonic_ns"]
        == result.assessment["freshness"]["source_validity_interval"]["until_ns"]
    )
    assert result.assessment["received_monotonic_ns"] == str(s["received_monotonic_ns"])
    assert result.assessment["obstacle_frame_ref"]["stamp_ns"] == p.meta["stamp_ns"]
    service = f.scene(rt, result, clock)
    responses, cases = {}, {}
    cases["unknown"] = hold(rt, result, clock)
    with http_scene(service) as client:
        responses["ready"] = capture(client, rt, service)
        assert not service.ingest(
            "obstacle_frame", rt.ports.scene_obstacle(result.obstacle_frame)
        )
        duplicate = f.run(rt, p, s)
        assert duplicate.intent.reason == "DUPLICATE_OR_REORDERED_INPUT"
        cases["duplicate"] = dict(
            reason=duplicate.intent.reason, memory=hold(rt, duplicate, clock)
        )
        clock.now = 1_020_000_000
        _, p2, s2, _ = f.setup(sequence=2, stamp=1_010_000_000, clock=clock)
        newer = f.run(rt, p2, s2)
        rt.ports.ingest_scene(service, newer)
        responses["newer"] = capture(client, rt, service)
        clock.now = 1_600_000_000
        responses["expired"] = capture(client, rt, service)
        expired = json.loads(responses["expired"]["raw"])
        assert (
            expired["collision_assessment"] is None
            and expired["obstacle_frame"] is None
        )
        assert newer.assessment["validity_interval"]["end_monotonic_ns"] == "1260000000"
        old_packet = p2
        rt.rebind(
            replace(rt.context, runtime_generation=2, source_epoch="synthetic-2"),
            replace(rt.mapping, source_epoch="synthetic-2"),
        )
        service.reset_source("obstacle_frame", "synthetic-2")
        assert service.snapshot()["sources"]["obstacle_frame"]["status"] == "pending"
        assert not service.ingest(
            "obstacle_frame", rt.ports.scene_obstacle(newer.obstacle_frame)
        )
        clock.now = 1_610_000_000
        _, p3, s3, _ = f.setup(sequence=0, stamp=1_600_000_000, clock=clock)
        p3, s3 = rebind_inputs(rt, p3, s3)
        restarted = f.run(rt, p3, s3)
        rt.ports.ingest_scene(service, restarted)
        assert restarted.obstacle_frame["sequence"] == 0
        responses["restart"] = capture(client, rt, service)
        old_epoch = f.run(rt, old_packet, s2)
        cases["old_epoch"] = dict(
            reason=old_epoch.intent.reason, memory=hold(rt, old_epoch, clock)
        )
        rt.rebind(
            replace(
                rt.context,
                runtime_generation=3,
                map_revision="c" * 64,
                map_generation=1,
            ),
            rt.mapping,
        )
        service.reset(rt.context.map_binding, "map-reset")
        assert not service.ingest(
            "obstacle_frame", rt.ports.scene_obstacle(restarted.obstacle_frame)
        )
        old_map = f.run(rt, p3, s3)
        cases["old_map"] = dict(
            reason=old_map.intent.reason, memory=hold(rt, old_map, clock)
        )
        responses["map_reset"] = capture(client, rt, service)

    for name in (
        "wrong_clock",
        "clock_epoch",
        "mapping_expired",
        "stale",
        "missing_pose",
        "missing_joints",
        "empty_geometry",
    ):
        rt, p, s, clock = f.setup(point_x=None if name == "empty_geometry" else 2.0)
        if name == "wrong_clock":
            rt.mapping = replace(rt.mapping, source_domain="other-clock")
        elif name == "clock_epoch":
            rt.mapping = replace(rt.mapping, clock_epoch="clock-2")
        elif name == "mapping_expired":
            rt.mapping = replace(rt.mapping, source_end_ns=1_100_000_000)
        elif name == "stale":
            clock.now = 2_000_000_000
        elif name == "missing_pose":
            s.pop("pose")
        elif name == "missing_joints":
            s.pop("joints")
        bad = f.run(rt, p, s)
        cases[name] = dict(
            reason=bad.intent.reason,
            memory=hold(rt, bad, clock),
            interval=bad.assessment["validity_interval"] if bad.assessment else None,
        )

    rt, p, s, clock = f.setup()
    result = f.run(rt, p, s)
    wrong_clock = SceneSnapshotService(
        rt.context.map_binding,
        host_clock_id="different-host",
        schema_version="0.2",
        clock=clock,
    )
    rt.ports.ingest_scene(wrong_clock, result)
    with http_scene(wrong_clock) as client:
        responses["wrong_host_clock"] = capture(client, rt, wrong_clock)
    assert json.loads(responses["wrong_host_clock"]["raw"])["obstacle_frame"] is None
    sizes = size_faults(rt, result, clock)
    from robot_dashboard.expansion_runtime import Runtime

    cases["missing_matching_geometry"] = expect_rejection(
        lambda: Runtime(
            rt.ports, replace(rt.context, robot_geometry_hash="0" * 64), rt.mapping
        ),
        "GEOMETRY_CONTEXT_MISMATCH",
    )

    high = 2**53 + 1000
    high_clock = f.fixtures.Clock(high + 10_000_000)
    high_rt, high_p, high_s, _ = f.setup(stamp=high, clock=high_clock)
    high_rt.mapping = replace(high_rt.mapping, source_end_ns=high + 1_000_000_000)
    high_result = f.run(high_rt, high_p, high_s)
    high_service = f.scene(high_rt, high_result, high_clock)
    with http_scene(high_service) as client:
        responses["high_ns"] = capture(client, high_rt, high_service)
    check = subprocess.run(
        [node, str(HERE / "current_consumer.mjs")],
        input=json.dumps(
            dict(
                deps=str(root),
                responses=responses,
                high_receipt_ns=str(high + 1_000_000),
            )
        ),
        text=True,
        capture_output=True,
        timeout=40,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    return dict(
        actual_core_runtime_c1_http_c3="PASS",
        input_evidence="SYNTHETIC_OWNER_FIXTURES",
        consumer=json.loads(check.stdout),
        cases=cases,
        limits=sizes,
        original_interval=interval,
        response_receipts={
            k: {x: v[x] for x in ("sha256", "bytes", "context")}
            for k, v in responses.items()
        },
        native_ros="NOT_RUN",
        browser_render="NOT_RUN",
        drawable_collision="UNAVAILABLE_INPUT_REQUIRED",
        physical_robot="NOT_RUN",
        command_sink="MEMORY_MOCK_ONLY",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deps", required=True, type=Path)
    parser.add_argument("--node", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    pins, before, fixture = dependencies(args.deps)
    with tempfile.TemporaryDirectory(prefix="c1-current-map-") as directory:
        maps = map_flow(Path(directory), args.deps, args.node, verify_errors=True)
    observations = observation(args.deps, args.node, fixture)
    origins = {}
    for role, package in (
        ("D1", "multimap_core"),
        ("D2", "obstacle_fusion_core"),
        ("D3", "collision_geometry_core"),
        ("C4", "expansion_runtime"),
    ):
        module = importlib.import_module("robot_dashboard." + package)
        path = Path(module.__file__)
        assert path.is_relative_to(args.deps / role)
        origins[role] = str(path.relative_to(args.deps))
    assert before == verify_exports(args.deps, pins)
    result = dict(
        pins=pins,
        verified_exports=before,
        owner_imports=origins,
        C7="READ_ONLY_DOCUMENT_REVIEW_NOT_EXECUTED",
        map=maps,
        observation=observations,
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                actual_composition="PASS",
                drawable_collision="UNAVAILABLE",
                output=str(args.output),
            )
        )
    )


if __name__ == "__main__":
    main()
