"""D0 shared inputs through the existing native executor, plus one C3 regression."""

import argparse
from pathlib import Path
import json
from run_minimum import execute

ROOT = Path(__file__).resolve().parent
D0 = json.loads((ROOT / "repro/d0-source.json").read_text())


def input_path(name):
    return ROOT / "d0_input" / D0["shared_path"] / "fixtures" / (name + ".truth.json")


NAMES = [
    "empty",
    "feasible1",
    "feasible2",
    "original_tight5",
    "blocked",
    "sensor_dropout",
]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    order = [("rpp", "diagnostic_single_obstacle", 0)] + [
        ("rpp", "d0_" + name, 0) for name in NAMES
    ]
    fixtures = {"d0_" + name: input_path(name) for name in NAMES}
    raise SystemExit(
        execute(args.lock, args.output, order, "d0-summary.json", fixtures)
    )
