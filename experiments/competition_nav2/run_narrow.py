"""ROUND4 bounded selection using the existing isolated native case executor.

One optional feasible1 baseline diagnostic; one fixed candidate. Only a successful
first feasible1 permits the three regressions, one repeat and one feasible2 run.
No search, tuning, generated path, or geometry change is performed here.
"""

import argparse
from pathlib import Path
from run_d0 import input_path
from run_minimum import execute


ORDER = [
    ("rpp", "d0_feasible1", 0),
    ("rpp", "d0_empty", 0),
    ("rpp", "d0_blocked", 0),
    ("rpp", "d0_sensor_dropout", 0),
    ("rpp", "d0_feasible1", 1),
    ("rpp", "d0_feasible2", 0),
]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-debug", action="store_true")
    args = parser.parse_args()
    fixtures = {name: input_path(name.removeprefix("d0_")) for _, name, _ in ORDER}
    if args.baseline_debug:
        baseline = execute(
            args.lock,
            args.output / "baseline-debug",
            ORDER[:1],
            "baseline-debug-summary.json",
            fixtures,
            expected_outcomes={"d0_feasible1": "SAFE_WAIT"},
        )
        if baseline:
            raise SystemExit(baseline)
    raise SystemExit(
        execute(
            args.lock,
            args.output / "se2-rpp",
            ORDER,
            "narrow-summary.json",
            fixtures,
            variant="se2_rpp",
        )
    )
