"""Generated SYNTHETIC inputs through the existing GoalPrecision + sink and C1 producer."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace as N
import math

from robot_dashboard.goal_precision import GoalPrecision
from robot_dashboard.goal_evidence_sink import GoalEvidenceSink
from robot_dashboard.run_review.review import MANIFEST

BASE = 1793244678803000000


def message(ns, x=1.0, y=2.0, yaw=0.0, frame="map"):
    return N(
        header=N(frame_id=frame, stamp=N(sec=ns // 10**9, nanosec=ns % 10**9)),
        child_frame_id="base_link",
        pose=N(
            position=N(x=x, y=y, z=0.0),
            orientation=N(x=0.0, y=0.0, z=math.sin(yaw / 2), w=math.cos(yaw / 2)),
        ),
    )


def goal_fixture(root, name="arrival", state="succeeded", yaw=0.0):
    folder = Path(root) / name
    meter = GoalPrecision()
    goal = dict(x=1.0, y=2.0, yaw=0.0)
    meter.start(
        name,
        goal,
        dict(map_id="a" * 24, map_revision="b" * 64, parameters_revision="c" * 64),
    )
    meter.sent(message(BASE), BASE, 10.0)
    sink = GoalEvidenceSink(folder)
    sink.submit("dispatch", meter.snapshot(10.0))
    meter.accepted(N(goal_id=N(uuid=list(range(16)))))
    sink.submit("accepted", meter.snapshot(10.0))
    for i in range(32):
        ns = BASE + i * 100_000_000
        meter.observe_odom(message(ns, yaw=yaw, frame="odom"), ns, 10 + i * 0.1)
        meter.observe_map(message(ns, yaw=yaw), ns, 10 + i * 0.1, "synthetic-epoch")
        if i == 3:
            meter.finish(state, ns, 10 + i * 0.1, {})
            sink.submit("result", meter.snapshot(10 + i * 0.1))
            meter.issued_zero(ns, 10 + i * 0.1)
            sink.submit("zero_issued", meter.snapshot(10 + i * 0.1))
        elif i == 30:
            sink.submit("first_measured_stop", meter.snapshot(10 + i * 0.1))
        else:
            sink.submit("sample", meter.snapshot(10 + i * 0.1))
    sink.close(3)
    if sink.snapshot()["errors"] or sink.snapshot()["dropped"]:
        raise AssertionError("sink failed")
    return dict(
        schema=MANIFEST,
        format="goal-evidence-v1",
        file=f"{name}/events.jsonl",
        goal_id=name,
        code_sha="5154761bba6fa4f171881e61f986901e2b415ed9",
        data_kind="SYNTHETIC",
        source_id="generated-existing-producer",
        clock_domain="synthetic-ros",
        source_epoch="synthetic-epoch",
        map_id="a" * 24,
        map_revision="b" * 64,
        parameters_revision="c" * 64,
    )


def scene_fixture(root, validator):
    from robot_dashboard.expansion_services.scene import SceneSnapshotService

    binding = dict(map_id="a" * 24, revision="b" * 64, generation=1)
    now = [9007199254740993]
    service = SceneSnapshotService(
        binding,
        schema_version="0.2",
        clock=lambda: now[0],
        host_clock_id="fixture-host",
        stream_epoch="stream-1",
    )
    records = []

    def add(epoch="sensor-1"):
        wire = service.snapshot()
        validator(wire)
        records.append(
            dict(
                schema="robot-scope.c1-scene-record.v1",
                packet=wire,
                context=dict(
                    **service.map_binding,
                    frame_id="map",
                    source_epoch=epoch,
                    stream_epoch=service.stream_epoch,
                    clock_domain="synthetic-sim",
                    calibration_id="fixture-calibration",
                    units="m",
                ),
                recorded_at=dict(
                    stamp_ns=str(now[0]),
                    clock_domain="fixture-host",
                    source_epoch="host-1",
                ),
            )
        )

    def observation(seq=1, epoch="sensor-1"):
        return dict(
            schema_version="0.2",
            evidence_kind="SYNTHETIC",
            producer="c6.fixture",
            sequence=seq,
            source_epoch=epoch,
            frame_key=dict(source_epoch=epoch, frame_id="map"),
            stamp_ns=str(BASE),
            clock_domain="synthetic-sim",
            host_clock_id="fixture-host",
            received_monotonic_ns=str(now[0]),
            map_binding=copy.deepcopy(service.map_binding),
            data=dict(
                points_m=[[0, 0], [1, 2]],
                dimensions=2,
                representation="2D_GROUND_PLANE",
                plane_z_m=0,
                generation="path-1",
            ),
            health={},
        )

    service.ingest("global_path", observation())
    from robot_dashboard.expansion_contracts.fixtures import obstacle

    obstacle_wire = obstacle(
        epoch="sensor-1", calibration_id="fixture-calibration"
    ).to_dict()
    obstacle_wire.update(
        schema_version="0.2",
        frame_key=dict(source_epoch="sensor-1", frame_id="map"),
        stamp_ns=str(BASE),
        clock_domain="synthetic-sim",
        host_clock_id="fixture-host",
        received_monotonic_ns=str(now[0]),
        map_binding=binding,
        obstacles=[
            dict(
                track_id="generated-box",
                state="OBSERVED",
                novelty="NEW_TO_REFERENCE",
                provenance={"origin": "SYNTHETIC"},
                sensor_support=["LIDAR"],
                geometry=dict(
                    center=[0.5, 1.0, 0.2],
                    extent=[0.3, 0.3, 0.4],
                    orientation_xyzw=[0, 0, 0, 1],
                ),
            )
        ],
    )
    service.ingest("obstacle_frame", obstacle_wire)
    add()
    now[0] += 1_000_000_000
    add()  # stale remains expired at replay/paused/seek
    service.reset_source("global_path", "sensor-2")
    service.ingest("global_path", observation(epoch="sensor-2"))
    add("sensor-2")
    now[0] += 1_000_000_000
    service.reset(dict(map_id="d" * 24, revision="e" * 64, generation=2), "stream-2")
    add("sensor-2")
    (Path(root) / "scenes.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records)
    )
    return dict(
        schema=MANIFEST,
        format="c1-scene-v1",
        file="scenes.jsonl",
        goal_id=None,
        code_sha="50600c7bce6f5fae743cd836ca1d8ee68d91b05a",
        data_kind="SYNTHETIC",
        source_id="existing-c1-producer",
        map_id=None,
        map_revision=None,
        parameters_revision=None,
    )


if __name__ == "__main__":
    import argparse
    from robot_dashboard.run_review.dependencies import c1_validator
    from robot_dashboard.run_review.review import load_run
    from robot_dashboard.run_review.io import write_new

    p = argparse.ArgumentParser()
    p.add_argument("directory", type=Path)
    p.add_argument("--deps", type=Path, required=True)
    args = p.parse_args()
    args.directory.mkdir(mode=0o700)
    validate = c1_validator(args.deps)
    manifests = [
        goal_fixture(args.directory),
        goal_fixture(args.directory, "heading", yaw=0.5),
        goal_fixture(args.directory, "cancel", state="canceled"),
        scene_fixture(args.directory, validate),
    ]
    for i, m in enumerate(manifests):
        write_new(args.directory / f"manifest-{i}.json", m)
        write_new(
            args.directory / f"review-{i}.json",
            load_run(args.directory, m, validator=validate),
        )
    print("Generated four SYNTHETIC review bundles using actual producers.")
