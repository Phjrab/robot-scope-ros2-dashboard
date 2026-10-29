"""Read-only exact-SHA dependency exports; no copied/merged C1 or D2 code.

Usage: python -m ...compatibility --c1-root /tmp/c1 --d2-root /tmp/d2
Export root contains robot_dashboard. C1 owns validation, invoked here only.
"""

import argparse
import json
from pathlib import Path
import sys

from robot_dashboard.collision_geometry_core import assess, obstacle_primitives
from .fixtures import sensor_points, state

C1_SHA = "2402c02c6f91ba54064894b21735e01b98610acd"
D2_SHA = "c0d266e290a2d29c173d3b83520f8c96efea9447"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--c1-root", type=Path, required=True)
    p.add_argument("--d2-root", type=Path, required=True)
    args = p.parse_args()
    sys.path.insert(0, str(args.c1_root / "robot_dashboard"))
    sys.path.insert(0, str(args.d2_root / "robot_dashboard"))
    from expansion_contracts import CollisionAssessment, ObstacleFrame
    from obstacle_fusion_core import process_lidar, Tracker
    from .fixtures import model

    s = state()
    # Only visible noisy raw points go to D2. Hidden truth is not injected.
    points = sensor_points([(1.0, 0, 0.13), (2.0, 0, 0.13)])
    observation = process_lidar(points, s)
    f = Tracker().step(observation)["obstacle_frame"]
    ObstacleFrame.from_dict(f)
    primitives = obstacle_primitives(f, uncertainty_in_extent=True)
    assert len(primitives) == 1
    a = assess(
        model(), s, f, now_stamp_ns=1_000_000_000, now_clock_domain="fixture-clock"
    )
    CollisionAssessment.from_dict(a)
    assert a["severity"] == "UNKNOWN"  # sparse cloud does not establish free space
    assert a["min_clearance"] is not None
    print(
        json.dumps(
            dict(
                C1_SHA=C1_SHA,
                D2_SHA=D2_SHA,
                status="PASS",
                objects=len(primitives),
                evidence_kind="SYNTHETIC",
                severity=a["severity"],
                interpretation="wire/geometry compatibility only, not product integration",
            )
        )
    )


if __name__ == "__main__":
    main()
