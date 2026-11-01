"""Actual pinned D2/C1/C4 core composition. C4 sink is explicitly memory-only.
No HTTP/ROS/native claim; native results are produced by the separate CI driver.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

from robot_dashboard.collision_geometry_core import assess
from robot_dashboard.collision_geometry_core.contracts import (
    canonical_assessment,
    c4_constraint,
)
from .fixtures import coverage_evidence, frame, model, sensor_points, state

C1_SHA = "cb8ccc68be8d96a44b0d38adcff8186893ba2b08"
C4_SHA = "b9d700d754f0d3d43b9afdcffcb86e9deb7b1020"
D2_SHA = "7313f0a31c00ae87ae216b84ca41a23804e91917"


def run(c1_root, c4_root, d2_root, d2_sha=D2_SHA):
    for root in (c1_root, c4_root, d2_root):
        sys.path.insert(0, str(root / "robot_dashboard"))
    from expansion_contracts import CollisionAssessment, ObstacleFrame
    from expansion_contracts.time_binding import (
        ClockBinding,
        normalize_collision_assessment,
    )
    from obstacle_runtime_adapter.command import (
        Binding,
        CommandGate,
        MockCommandSink,
        RawCommand,
        constraint_from_d3,
    )
    from obstacle_fusion_core import process_lidar, Tracker

    s = state()
    points = sensor_points([(1.0, 0, 0.13), (2.0, 0, 0.13)])
    f = Tracker().step(process_lidar(points, s))["obstacle_frame"]
    ObstacleFrame.from_dict(f)
    assert len(f["obstacles"]) == 1
    host = 2**53 + 12345
    clock = ClockBinding(
        s["clock_domain"],
        s["source_epoch"],
        s["host_clock_id"],
        host - 1_000_000_000,
        2,
        "synthetic-binding",
    )
    s["received_monotonic_ns"] = host
    f["received_monotonic_ns"] = host
    command_ref = {"command_sequence": 1}
    path = {"ref": command_ref, "poses": [{"time_s": 0, "pose": s["pose"]}]}

    def compute(objects, now=1_000_000_000, coverage=None):
        raw = assess(
            model(),
            s,
            objects,
            path,
            now_stamp_ns=now,
            now_clock_domain=s["clock_domain"],
            coverage=coverage,
        )
        return canonical_assessment(
            raw, normalize=normalize_collision_assessment, clock_binding=clock
        )

    a = compute(f)
    CollisionAssessment.from_dict(a)
    assert a["schema_version"] == "0.2" and a["received_monotonic_ns"] == str(host)
    assert a["severity"] == "UNKNOWN"
    assert a["robot_pose_ref"]["received_monotonic_ns"] == str(host)
    assert a["obstacle_frame_ref"]["received_monotonic_ns"] == str(host)
    interval = a["validity_interval"]
    assert interval == dict(
        host_clock_id=s["host_clock_id"],
        start_monotonic_ns=str(host + 2),
        end_monotonic_ns=str(host + 250_000_000 - 2),
    )
    later = compute(f, 1_100_000_000)
    assert (
        later["validity_interval"] == interval
    )  # adapter/recompute does NOT restart TTL
    encoded = json.dumps(a, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert json.loads(encoded)["validity_interval"] == interval
    binding = Binding(
        "synthetic-goal",
        0,
        "synthetic-lease",
        s["source_epoch"],
        json.dumps(s["frame_key"], sort_keys=True, separators=(",", ":")),
        s["host_clock_id"],
    )

    def consume(payload, mode="ACTIVE"):
        return c4_constraint(
            payload,
            validate_canonical=CollisionAssessment.from_dict,
            consume=constraint_from_d3,
            binding=binding,
            command_sequence=1,
            enforcement_mode=mode,
        )

    constraint = consume(a)
    raw_command = RawCommand(1, binding, host, host + 250_000_000, (0.1, 0.0, 0.0))
    gate = CommandGate(MockCommandSink(), binding)
    checked = gate.apply(raw_command, constraint, now_ns=host + 5)
    assert checked.hold and checked.reason == "UNKNOWN"
    assert consume(a, "ADVISORY_ONLY") is None
    empty = frame()
    empty["received_monotonic_ns"] = host
    unknown = compute(empty)
    assert unknown["severity"] == "UNKNOWN"
    clear = compute(empty, coverage=coverage_evidence(s))
    assert clear["severity"] == "CLEAR"
    active = CommandGate(MockCommandSink(), binding)
    assert not active.apply(raw_command, consume(clear), now_ns=host + 5).hold
    assert active.tick(now_ns=host + 250_000_000).hold
    expired = CommandGate(MockCommandSink(), binding)
    assert expired.apply(raw_command, consume(clear), now_ns=host + 250_000_000).hold
    assert gate.apply(
        RawCommand(2, binding, host, host + 250_000_000, (0.1, 0.0, 0.0)),
        consume(clear),
        now_ns=host + 6,
    ).hold
    for key, value in [("source_epoch", "wrong"), ("host_clock_id", "wrong")]:
        bad = copy.deepcopy(a)
        bad[key] = value
        try:
            consume(bad)
        except (ValueError, KeyError):
            pass
        else:
            raise AssertionError("invalid context accepted")
    # Real C4 old projection with real canonical validator rejects mismatched keys.
    try:
        constraint_from_d3(
            a,
            validate_assessment=CollisionAssessment.from_dict,
            binding=binding,
            command_sequence=1,
        )
    except ValueError:
        direct = "REJECTED_CONFIRMED"
    else:
        raise AssertionError("unadapted C4 unexpectedly accepted canonical keys")
    return dict(
        status="PASS",
        C1_SHA=C1_SHA,
        C4_SHA=C4_SHA,
        D2_SHA=d2_sha,
        checks=[
            "real_D2",
            "real_C1_v02",
            "real_C4_consumer_and_gate",
            "UNKNOWN_HOLD",
            "explicit_ADVISORY_ONLY",
            "no_TTL_restart",
            "expired_HOLD",
            "epoch_host_mismatch",
            "JSON_above_2pow53_lossless",
        ],
        unadapted_C4=direct,
        example_sha256=hashlib.sha256(encoded.encode()).hexdigest(),
        example=a,
        execution=dict(
            core="ACTUAL",
            command_sink="MEMORY_ONLY",
            HTTP="NOT_RUN",
            ROS="NOT_RUN",
            native="SEPARATE_CI",
        ),
    )


def main():
    p = argparse.ArgumentParser()
    for role in ("c1", "c4", "d2"):
        p.add_argument("--" + role + "-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--d2-sha", default=D2_SHA)
    args = p.parse_args()
    report = run(args.c1_root, args.c4_root, args.d2_root, args.d2_sha)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "example"}))


if __name__ == "__main__":
    main()
