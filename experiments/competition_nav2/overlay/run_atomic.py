"""Exactly one existing feasible1 case; no ROUND6 checker/planner-only repetition."""

import argparse
from pathlib import Path
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
    return execute(
        args.lock,
        args.output,
        [("mppi", "d0_feasible1", 0)],
        "atomic-summary.json",
        {"d0_feasible1": input_path("feasible1")},
        variant="omni_checked_overlay",
        stop_on_failure=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
