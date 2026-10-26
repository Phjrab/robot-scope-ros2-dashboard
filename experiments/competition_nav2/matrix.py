"""Explicit 12 scenarios x 2 controllers x 2 candidates x 3 repetitions."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from fixtures import ROOT, cases


def plan():
    return [
        dict(
            controller=c,
            variant=v,
            scenario=f["scenario"],
            repeat=r,
            seed=f["seed"],
            status="NOT_RUN",
        )
        for f in cases()
        for v in ("baseline", "tuned")
        for r in range(3)
        for c in ("rpp", "mppi")
    ]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path)
    p.add_argument("--run", action="store_true")
    p.add_argument("--lock", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--runtime", choices=["docker", "podman"], default="docker")
    args = p.parse_args()
    rows = plan()
    if args.plan:
        args.plan.write_text(
            json.dumps(
                dict(backend="nav2_native_sim", scheduled=144, executed=0, runs=rows),
                indent=2,
            )
            + "\n"
        )
    if args.run:
        if not args.lock or not args.output:
            p.error("--run requires --lock and --output")
        args.output.mkdir(parents=True, exist_ok=True)
        for row in rows:
            name = f"{row['scenario']}-{row['variant']}-{row['controller']}-{row['repeat']}"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "container/manage.py"),
                    "run",
                    "--runtime",
                    args.runtime,
                    "--lock",
                    str(args.lock.resolve()),
                    "--output",
                    str(args.output / name),
                    "--controller",
                    row["controller"],
                    "--variant",
                    row["variant"],
                    "--scenario",
                    row["scenario"],
                    "--repeat",
                    str(row["repeat"]),
                    "--seed",
                    str(row["seed"]),
                ]
            )
            row["status"] = "PROCESS_OK" if result.returncode == 0 else "PROCESS_FAILED"
            row["exit_code"] = result.returncode
            (args.output / "execution_matrix.json").write_text(
                json.dumps(rows, indent=2) + "\n"
            )
        raise SystemExit(any(r["exit_code"] != 0 for r in rows))
