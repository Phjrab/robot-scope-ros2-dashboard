"""Small RPP follow-up, reusing the existing isolated native executor."""

import argparse
from pathlib import Path
from run_minimum import execute

ORDER = [("rpp", "diagnostic_single_obstacle", i) for i in range(3)] + [
    ("rpp", name, 0)
    for name in (
        "diagnostic_appearing_obstacle",
        "diagnostic_two_obstacles",
        "fully_blocked",
        "sensor_stale",
    )
]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(execute(args.lock, args.output, ORDER, "extension-summary.json"))
