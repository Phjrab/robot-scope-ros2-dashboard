"""C1 entry point. Manifest reads are ROS-free; execution creates an isolated SIM_GT run."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def manifest():
    contract = json.loads((ROOT / "repro/rpp-contract.json").read_text())
    for name, expected in contract["files_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("contract source changed: " + name)
    return contract


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["manifest", "run"])
    parser.add_argument("--mode", choices=["isolated-sim"])
    parser.add_argument("--scenario", default="diagnostic_single_obstacle")
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    contract = manifest()
    if args.operation == "manifest":
        print(json.dumps(contract, indent=2))
        return 0
    if args.mode != "isolated-sim" or args.lock is None or args.output is None:
        parser.error(
            "run requires --mode isolated-sim, --lock and --output; no live mode exists"
        )
    if args.scenario not in contract["scenarios"]:
        parser.error("scenario outside reviewed contract")
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "container/manage.py"),
            "run",
            "--controller",
            "rpp",
            "--variant",
            "baseline",
            "--scenario",
            args.scenario,
            "--lock",
            str(args.lock),
            "--output",
            str(args.output),
        ],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
