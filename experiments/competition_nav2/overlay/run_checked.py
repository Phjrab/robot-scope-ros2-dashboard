"""One fixed correctness candidate: planner-only first; no navigation after failure."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run_d0 import input_path  # noqa: E402
from run_minimum import execute  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lock", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    planner = args.output / "planner-only"
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "container/manage.py"),
            "run",
            "--lock",
            str(args.lock),
            "--controller",
            "mppi",
            "--variant",
            "omni_checked_overlay",
            "--planner-only",
            "--fixture",
            str(input_path("feasible1")),
            "--output",
            str(planner),
        ],
        check=False,
    )
    gate = dict(
        planner_returncode=process.returncode,
        closed_loop="NOT_RUN",
        regressions="NOT_RUN",
    )
    (args.output / "gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    if process.returncode:
        return process.returncode
    order = [
        ("mppi", "d0_feasible1", 0),
        ("mppi", "d0_feasible1", 1),
        ("mppi", "d0_empty", 0),
        ("mppi", "d0_blocked", 0),
        ("mppi", "d0_sensor_dropout", 0),
        ("mppi", "d0_feasible2", 0),
    ]
    fixtures = {s: input_path(s.removeprefix("d0_")) for _, s, _ in order}
    code = execute(
        args.lock,
        args.output / "closed-loop",
        order,
        "checked-summary.json",
        fixtures,
        variant="omni_checked_overlay",
        stop_on_failure=True,
    )
    gate.update(
        closed_loop="EXECUTED",
        returncode=code,
        regressions="See bounded summary; first feasible1 failure stops fanout",
    )
    (args.output / "gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
