"""Exact-pin read-only preparation, not a replacement C4 adapter.

Uses git objects already fetched, optionally fetching exact pins on the existing
GitHub-hosted CI runner. Does not launch ROS, Docker or a worker.
"""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess

from experiments.expansion_20261029.d3_collision_sim.c4_input_fixture import CASES

ROOT = Path(__file__).resolve().parents[3]
PINS = {
    "c1": "e0bc9cf8ba8bd22b406a287e1a9ef867a0cd367b",
    "c4": "7ac0d55b07abd20902d6d756c6b225733613fea7",
    "d2": "7313f0a31c00ae87ae216b84ca41a23804e91917",
    "d3_baseline": "356d0a036eb62d546e159e12a0691d7f5ea278f6",
}
FILES = {
    "c4": ("robot_dashboard/obstacle_runtime_adapter/runtime.py",
           "robot_dashboard/obstacle_runtime_adapter/ros_port.py",
           "robot_dashboard/expansion_runtime/composition.py",
           "robot_dashboard/expansion_runtime/canonical_ports.py",
           "docs/parallel-expansion-20261029/C4/FOLLOWUP.md"),
    "c1": ("robot_dashboard/expansion_contracts/time_binding.py",),
    "d2": ("robot_dashboard/obstacle_fusion_core/consumer_port.py",),
}


def inspect_sources():
    rows, sources = [], {}
    for owner, paths in FILES.items():
        for path in paths:
            value = subprocess.check_output(["git", "show", f"{PINS[owner]}:{path}"], cwd=ROOT)
            sources[path] = value.decode()
            rows.append(dict(owner=owner, sha=PINS[owner], path=path,
                             sha256=hashlib.sha256(value).hexdigest()))
    worker = ast.parse(sources[FILES["c4"][0]])
    pipeline = next(n for n in worker.body if isinstance(n, ast.ClassDef) and n.name == "_Pipeline")
    calls = sorted({ast.unparse(n.func) for n in ast.walk(pipeline) if isinstance(n, ast.Call)})
    # Deliberately pinned finding, not speculative auto-detection of future APIs.
    assert "self.owner.d2.process" in calls
    assert not any("assess" in c or "runtime.process" in c for c in calls)
    assert "synchronous Runtime is not claimed" in sources[FILES["c4"][4]]
    return dict(dependencies=PINS, source_files=rows, inspected_worker_calls=calls,
        status="INPUT_REQUIRED", blocker="C4_BOUNDED_WORKER_RUNTIME_BRIDGE_NOT_SUBMITTED",
        actual_ros="NOT_RUN", new_native_chain="NOT_RUN",
        baseline_native="SEPARATE_EXISTING_FIVE_CASE_RUN",
        cases={name: "NOT_RUN" for name in CASES},
        required_owner_connection="ReviewRosPort -> bounded worker -> expansion_runtime.Runtime.process",
        mode="ADVISORY_ONLY", product_command_connection=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    if args.fetch:
        if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
            raise ValueError("FETCH_ONLY_ON_EXISTING_HOSTED_CI")
        subprocess.run(["git", "fetch", "--no-tags", "origin", *PINS.values()], cwd=ROOT, check=True)
    result = inspect_sources()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print("D3_C4_READINESS="+json.dumps(result, sort_keys=True), flush=True)
    # Preparation success is NOT adapter/native integration success.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
