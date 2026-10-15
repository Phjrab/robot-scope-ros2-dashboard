#!/usr/bin/env python3
"""Offline recorded SE3 evaluation with explicit, independently qualified inputs.

This CLI never imports ROS, publishes a pose or feeds the synthetic-only UI.
Input .npy files must already be registered and bounded; no calibration,
odometry application, downsampling or ground-truth seed is performed here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from robot_dashboard.relocalization.experimental_se3 import (  # noqa: E402
    Cloud, ExperimentalSE3Error, MAX_POINTS, register_se3,
    validate_experimental_result, validate_transform,
)

MAX_MANIFEST_BYTES = 64 * 1024
MAX_CLOUD_BYTES = MAX_POINTS * 3 * 8 + 4096
INPUT_SCHEMA = "robot-scope.recorded-se3-input.v1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qualified_inputs(manifest: dict, directory: Path):
    if not isinstance(manifest, dict):
        raise ExperimentalSE3Error("manifest must be an object")
    if manifest.get("schema") != INPUT_SCHEMA or manifest.get("evidence_type") != "recorded_real":
        raise ExperimentalSE3Error("explicit recorded-real manifest required")
    provenance = manifest.get("provenance", {})
    if not isinstance(provenance, dict):
        raise ExperimentalSE3Error("provenance must be an object")
    for key in ("calibration_verified", "clock_verified", "frames_connected_verified",
                "independent_collection_verified"):
        if provenance.get(key) is not True:
            raise ExperimentalSE3Error(f"unqualified provenance: {key}")
    if provenance.get("reference_contains_query") is not False:
        raise ExperimentalSE3Error("reference/query overlap in acquisition lineage is unqualified")
    if provenance.get("transform_direction") != "T_target_source":
        raise ExperimentalSE3Error("explicit T_target_source direction required")
    count = provenance.get("query_registration_application_count")
    if type(count) is not int or count != 1:
        raise ExperimentalSE3Error("query must be registered exactly once before evaluation")
    for key in ("sensor_config_sha256", "calibration_sha256"):
        value = provenance.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ExperimentalSE3Error(f"missing qualified provenance hash: {key}")
    reference, query = manifest.get("reference", {}), manifest.get("query", {})
    for item in (reference, query):
        if not isinstance(item, dict):
            raise ExperimentalSE3Error("cloud identity must be an object")
        for key in ("session_id", "map_family_id", "map_revision", "frame"):
            if not isinstance(item.get(key), str) or not item[key] or len(item[key]) > 128:
                raise ExperimentalSE3Error(f"missing input identity: {key}")
    if reference["session_id"] == query["session_id"]:
        raise ExperimentalSE3Error("same-session query is not an independent acquisition")
    if reference.get("sha256") == query.get("sha256"):
        raise ExperimentalSE3Error("byte-identical reference/query is not an independent acquisition")
    if (reference["map_family_id"], reference["map_revision"]) != (query["map_family_id"], query["map_revision"]):
        raise ExperimentalSE3Error("reference/query map-family revision mismatch")
    seeds = manifest.get("seeds")
    if not isinstance(seeds, list) or not 1 <= len(seeds) <= 5:
        raise ExperimentalSE3Error("one to five seeds must be fixed before execution")
    transforms = []
    for seed in seeds:
        if not isinstance(seed, dict):
            raise ExperimentalSE3Error("seed must be an object")
        if seed.get("source") not in {"operator_survey", "independent_odometry_estimate", "pose_prior_with_uncertainty"}:
            raise ExperimentalSE3Error("seed source is unqualified or uses evaluation truth")
        transforms.append(validate_transform(seed.get("T_target_source")))

    def load(item, *, is_reference):
        path = (directory / str(item.get("path", ""))).resolve(strict=True)
        if path.suffix != ".npy" or not path.is_file() or path.stat().st_size > MAX_CLOUD_BYTES:
            raise ExperimentalSE3Error("cloud must be a bounded numeric .npy file")
        if sha(path) != item.get("sha256"):
            raise ExperimentalSE3Error("cloud hash mismatch")
        try:
            points = np.load(path, mmap_mode="r", allow_pickle=False)
        except ValueError as exc:
            raise ExperimentalSE3Error("cloud is not a numeric array") from exc
        if points.dtype not in (np.dtype("float32"), np.dtype("float64")):
            raise ExperimentalSE3Error("cloud must contain float32/float64 metre coordinates")
        return Cloud(points, item["frame"], item.get("kind"), item.get("unit"),
                     item.get("source_stamp_ns")).validated(reference=is_reference)
    return load(reference, is_reference=True), load(query, is_reference=False), transforms


def evaluate(manifest_path: Path, *, repeats: int = 1) -> dict:
    if not 1 <= repeats <= 10 or manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ExperimentalSE3Error("manifest/repeat bound exceeded")
    manifest = json.loads(manifest_path.read_text())
    reference, query, seeds = qualified_inputs(manifest, manifest_path.parent)
    started = time.monotonic()
    measurements = []
    for seed_index, transform in enumerate(seeds):
        for repeat in range(repeats):
            result = validate_experimental_result(register_se3(reference, query, transform))
            measurements.append({"seed_index": seed_index, "repeat": repeat,
                                 "temperature": "cold_process_first_call" if not measurements else "warm_same_process",
                                 "se3": result})
    times = sorted(row["se3"]["metrics"]["runtime_ms"] for row in measurements)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
    return {"schema": "robot-scope.recorded-se3-evaluation.v1", "evidence_type": "recorded_real",
            "experimental": True, "manifest_sha256": sha(manifest_path),
            "source_commit": revision.stdout.strip(), "source_dirty": bool(dirty.stdout.strip()),
            "cli_sha256": sha(Path(__file__)), "module_sha256": sha(ROOT / "robot_dashboard/relocalization/experimental_se3.py"),
            "platform": platform.platform(), "python": platform.python_version(), "numpy": np.__version__,
            "input_points": {"reference": len(reference.points), "query": len(query.points)},
            "sample_count": len(times), "runtime_p50_ms": statistics.median(times),
            "runtime_p95_ms": times[math.ceil(.95*len(times))-1], "runtime_max_ms": max(times),
            "max_rss_native": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "max_rss_unit": "bytes" if sys.platform == "darwin" else "KiB",
            "preprocessing_included": False, "elapsed_s": time.monotonic()-started,
            "absolute_position_error_m": None, "absolute_rotation_error_rad": None,
            "independent_ground_truth": None, "global_relocalization": "NOT_RUN",
            "operational_application": "NOT_RUN", "measurements": measurements}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be a new private artifact path")
    try:
        result = evaluate(args.manifest, repeats=args.repeats)
        exit_code = 0
    except (ExperimentalSE3Error, ValueError, OSError, TypeError, KeyError) as exc:
        result = {"schema": "robot-scope.recorded-se3-evaluation.v1", "status": "BLOCKED",
                  "reason": str(exc), "absolute_position_error_m": None,
                  "absolute_rotation_error_rad": None, "operational_application": "NOT_RUN"}
        exit_code = 2
    descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"status": result.get("status", "EVALUATED"), "output": str(args.output)}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
