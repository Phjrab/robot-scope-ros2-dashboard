"""Emit a deterministic real adapter/C1 snapshot for Node contract tests."""

import json
from robot_dashboard.expansion_integration.cone_demo import (
    adapt_cones,
    demo_context,
    load_scenario,
)
from robot_dashboard.expansion_services.scene import SceneSnapshotService
from experiments.expansion_20261101.cone_display.demo import SCENARIO


def wire():
    payload = load_scenario(SCENARIO)
    context = demo_context(payload)
    scene = SceneSnapshotService(
        {k: context[k] for k in ("map_id", "revision", "generation")},
        schema_version="0.2",
        stream_epoch=context["stream_epoch"],
        host_clock_id="test",
        clock=lambda: 9007199254740993,
        max_age_ns=1_000_000_000,
        max_sample_bytes=64 * 1024,
    )
    scene.ingest(
        "obstacle_frame",
        adapt_cones(
            dict(payload, stamp=1),
            context,
            sequence=1,
            received_monotonic_ns=9007199254740993,
            host_clock_id="test",
        ),
    )
    return dict(context=context, wire=scene.snapshot())


if __name__ == "__main__":
    print(json.dumps(wire()))
