"""Fixed small SYNTHETIC baseline; no tuning and no claims of native Nav2 motion."""

import argparse
import json
import time
from pathlib import Path

from robot_dashboard.collision_geometry_core import assess, transform
from .fixtures import frame, model, obstacle, scenarios, state, coverage_evidence
from .preflight import probe


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    results = []
    begin = time.perf_counter()
    for name, objects, path in (
        ("empty_known_synthetic", [], None),
        ("body_overlap", [obstacle((0.2, 0, 0.3))], None),
        (
            "translation_sweep",
            [obstacle((1, 0, 0.3))],
            {
                "ref": {"kind": "synthetic_path"},
                "poses": [
                    {"time_s": 0, "pose": state()["pose"]},
                    {"time_s": 2, "pose": transform((2, 0, 0.3)).tolist()},
                ],
            },
        ),
        (
            "rotation_sweep",
            [obstacle((0.30, 0.30, 0.3), (0.03, 0.03, 0.1))],
            {
                "ref": {"kind": "synthetic_rotation"},
                "poses": [
                    {"time_s": 0, "pose": state()["pose"]},
                    {
                        "time_s": 2,
                        "pose": transform(
                            (0, 0, 0.3), (0, 0, 1.5707963267948966)
                        ).tolist(),
                    },
                ],
            },
        ),
    ):
        result = assess(
            model(),
            state(),
            frame(objects),
            path,
            now_stamp_ns=1_000_000_000,
            now_clock_domain="fixture-clock",
            coverage=coverage_evidence(),
        )
        results.append(dict(name=name, assessment=result))
    report = dict(
        evidence_kind="SYNTHETIC",
        cases=results,
        elapsed_ms=(time.perf_counter() - begin) * 1000,
        native=probe(),
        native_scenarios=scenarios(),
        replay_real="INPUT_REQUIRED",
        device="DEVICE_NOT_RUN",
        physical_geometry="INPUT_REQUIRED",
    )
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({r["name"]: r["assessment"]["severity"] for r in results}))


if __name__ == "__main__":
    main()
