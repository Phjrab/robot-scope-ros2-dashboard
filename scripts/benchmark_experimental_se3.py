#!/usr/bin/env python3
"""Deterministic synthetic-only 6DoF experiment, never a live pose source."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import resource
import statistics
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from robot_dashboard.relocalization.experimental_se3 import (  # noqa: E402
    Cloud,
    from_translation_rpy,
    inverse,
    register_se3,
    rotation_error_rad,
    transform_points,
    validate_experimental_result,
)
from robot_dashboard.relocalization.process_adapter import (  # noqa: E402
    OfflineRegistrationProcess,
    RegistrationProcessError,
)


def scene() -> np.ndarray:
    coordinates = np.linspace(-3.2, 3.2, 33)
    floor = np.array([(x, y, 0.0) for x in coordinates for y in coordinates])
    floor[:, :2] += np.random.default_rng(421).uniform(-0.045, 0.045, size=(len(floor), 2))
    heights = np.linspace(0.0, 2.0, 13)
    pillar = np.array([(1.2 + 0.25 * math.cos(angle), -0.7 + 0.25 * math.sin(angle), z)
                       for z in heights for angle in np.linspace(0, 2 * math.pi, 24, endpoint=False)])
    wall = np.array([(-1.7, y, z) for y in np.linspace(-1.5, 1.5, 17)
                     for z in np.linspace(0.0, 1.5, 11)])
    return np.vstack((floor, pillar, wall))


def cases() -> list[dict]:
    reference = scene()
    floor_count = 33 * 33
    pillar_count = 13 * 24
    easy = from_translation_rpy([0.12, -0.09, 0.06], [0.0, 0.0, 0.08])
    tilt = from_translation_rpy([0.15, -0.12, 0.18], [0.09, -0.07, 0.11])
    easy_seed = from_translation_rpy([0.06, -0.04, 0.03], [0.0, 0.0, 0.04])
    tilt_seed = from_translation_rpy([0.08, -0.06, 0.09], [0.045, -0.035, 0.055])
    slope_seed = from_translation_rpy([0.12, -0.10, 0.14], [0.075, -0.055, 0.09])
    slope = transform_points(from_translation_rpy([0, 0, 0], [0.0, 0.13, 0.0]), reference)
    floor = reference[:floor_count]
    rng = np.random.default_rng(7)
    module = rng.uniform(-0.4, 0.4, size=(250, 3))
    repeated = np.vstack((module + [-2, 0, 0], module + [2, 0, 0]))
    return [
        {"id": "level-with-height-structure", "target": reference,
         "source": transform_points(inverse(easy), reference), "truth": easy,
         "initial": easy_seed, "expect": "CANDIDATE"},
        {"id": "tilted-query", "target": reference,
         "source": transform_points(inverse(tilt), reference), "truth": tilt,
         "initial": tilt_seed, "expect": "CANDIDATE"},
        {"id": "sloped-ground", "target": slope,
         "source": transform_points(inverse(tilt), slope), "truth": tilt,
         "initial": slope_seed, "expect": "CANDIDATE"},
        {"id": "partial-occlusion", "target": reference,
         "source": transform_points(inverse(tilt), reference[reference[:, 0] > -0.5]),
         "truth": tilt, "initial": tilt_seed, "expect": "CANDIDATE"},
        {"id": "ground-removed", "target": reference[reference[:, 2] > 0.05],
         "source": transform_points(inverse(tilt), reference[reference[:, 2] > 0.05]),
         "truth": tilt, "initial": tilt_seed, "expect": "REJECTED"},
        {"id": "flat-ground-only", "target": floor,
         "source": transform_points(inverse(tilt), floor), "truth": tilt,
         "initial": tilt_seed, "expect": "REJECTED"},
        {"id": "single-plane", "target": reference[floor_count + pillar_count:],
         "source": transform_points(inverse(easy), reference[floor_count + pillar_count:]),
         "truth": easy, "initial": easy_seed, "expect": "REJECTED"},
        {"id": "repeated-left-seed", "target": repeated, "source": module,
         "initial": from_translation_rpy([-2, 0, 0], [0, 0, 0]), "expect": "CANDIDATE"},
        {"id": "repeated-right-seed", "target": repeated, "source": module,
         "initial": from_translation_rpy([2, 0, 0], [0, 0, 0]), "expect": "CANDIDATE"},
        {"id": "wrong-map", "target": reference + [20, 20, 20], "source": reference,
         "initial": np.eye(4), "expect": "REJECTED"},
        {"id": "far-initial-pose", "target": reference, "source": reference,
         "initial": from_translation_rpy([20, 20, 20], [0, 0, 0]), "expect": "REJECTED"},
    ]


def _write_pcd(path: Path, points: np.ndarray) -> None:
    header = ("# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\n"
              f"COUNT 1 1 1\nWIDTH {len(points)}\nHEIGHT 1\nPOINTS {len(points)}\nDATA binary\n")
    path.write_bytes(header.encode("ascii") + b"".join(struct.pack("fff", *point) for point in points))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str | None:
    completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                               capture_output=True, text=True, check=False)
    return completed.stdout.strip() if completed.returncode == 0 else None


def _source_tree_dirty() -> bool:
    completed = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                               capture_output=True, text=True, check=False)
    return completed.returncode != 0 or bool(completed.stdout.strip())


def _se2_run(adapter: OfflineRegistrationProcess, reference: Path, query: Path,
             truth: np.ndarray | None, initial: np.ndarray) -> dict:
    request = {
        "reference_pcd": str(reference), "query_pcd": str(query),
        "seed": {"x": float(initial[0, 3]), "y": float(initial[1, 3]),
                 "yaw": math.atan2(initial[1, 0], initial[0, 0]),
                 "radius_m": 0.8, "yaw_range_rad": 0.5},
        "limits": {"max_reference_points": 100_000, "max_query_points": 100_000,
                   "timeout_ms": 15_000},
    }
    try:
        candidate = adapter.run(request)["results"][0]
    except RegistrationProcessError as exc:
        return {"status": "PROCESS_ERROR", "reason": str(exc)[:128],
                "z_roll_pitch": "UNAVAILABLE_BY_CONTRACT"}
    record = {"status": "ACCEPTED" if candidate["confidence"] != "REJECTED" else "REJECTED",
              "converged": candidate["converged"], "confidence": candidate["confidence"],
              "runtime_ms": candidate["metrics"]["runtime_ms"],
              "z_roll_pitch": "UNAVAILABLE_BY_CONTRACT"}
    if truth is not None:
        pose = candidate["pose"]
        record["planar_translation_error_m"] = math.hypot(
            pose["x"] - truth[0, 3], pose["y"] - truth[1, 3])
        true_yaw = math.atan2(truth[1, 0], truth[0, 0])
        record["yaw_error_deg"] = math.degrees(abs(math.atan2(
            math.sin(pose["yaw"] - true_yaw), math.cos(pose["yaw"] - true_yaw))))
    return record


def run_matrix(se2_executable: Path | None = None) -> dict:
    measurements = []
    with tempfile.TemporaryDirectory(prefix="robot-scope-se3-experiment-") as directory:
        root = Path(directory)
        se2_adapter = (OfflineRegistrationProcess(se2_executable.resolve(strict=True), [root])
                       if se2_executable is not None else None)
        for index, case in enumerate(cases()):
            target_path, source_path = root / f"target-{index}.pcd", root / f"source-{index}.pcd"
            _write_pcd(target_path, case["target"])
            _write_pcd(source_path, case["source"])
            result = validate_experimental_result(register_se3(
                Cloud(case["target"], "map", "REGISTERED_MAP"),
                Cloud(case["source"], "camera_init", "REGISTERED_QUERY", stamp_ns=1_000_000_000),
                case["initial"],
            ))
            record = {"id": case["id"], "data_kind": "SYNTHETIC", "expected_status": case["expect"],
                      "target_sha256": _sha256(target_path), "source_sha256": _sha256(source_path),
                      "initial_t_target_source": case["initial"].tolist(), "se3": result}
            if "truth" in case:
                truth = case["truth"]
                estimate = from_translation_rpy(
                    [result["pose"][axis] for axis in "xyz"],
                    [result["pose"][key] for key in ("roll_rad", "pitch_rad", "yaw_rad")],
                )
                record["truth_t_target_source"] = truth.tolist()
                record["se3_position_error_m"] = float(np.linalg.norm(
                    estimate[:3, 3] - truth[:3, 3]))
                record["se3_rotation_error_deg"] = math.degrees(rotation_error_rad(estimate, truth))
            if se2_adapter is not None:
                record["se2"] = _se2_run(se2_adapter, target_path, source_path,
                                          case.get("truth"), case["initial"])
            measurements.append(record)
    left, right = (next(record for record in measurements if record["id"] == name)
                   for name in ("repeated-left-seed", "repeated-right-seed"))
    ambiguous = (left["se3"]["status"] == right["se3"]["status"] == "CANDIDATE"
                 and abs(left["se3"]["pose"]["x"] - right["se3"]["pose"]["x"]) > 1.0
                 and abs(left["se3"]["metrics"]["rmse_m"]
                         - right["se3"]["metrics"]["rmse_m"]) < 0.005)
    runtimes = sorted(record["se3"]["metrics"]["runtime_ms"] for record in measurements)
    manifest = [{key: record[key] for key in (
        "id", "target_sha256", "source_sha256", "initial_t_target_source")}
        for record in measurements]
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {"schema": "robot-scope.experimental-se3-benchmark.v1", "experimental": True,
            "data_kind": "SYNTHETIC", "ground_truth_source": "same-map inverse transforms where present",
            "source_commit": _git_commit(), "benchmark_sha256": _sha256(Path(__file__)),
            "source_tree_dirty": _source_tree_dirty(),
            "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
            "module_sha256": _sha256(ROOT / "robot_dashboard" / "relocalization" / "experimental_se3.py"),
            "se2_executable_sha256": _sha256(se2_executable) if se2_executable is not None else None,
            "platform": platform.platform(), "python": platform.python_version(),
            "numpy": np.__version__, "case_count": len(measurements),
            "candidate_count": sum(item["se3"]["status"] == "CANDIDATE" for item in measurements),
            "false_candidate_count": sum(item["se3"]["status"] == "CANDIDATE"
                                         and item["expected_status"] == "REJECTED" for item in measurements),
            "expected_status_mismatch_count": sum(item["se3"]["status"] != item["expected_status"]
                                                   for item in measurements),
            "repeated_structure_seed_ambiguity": ambiguous,
            "runtime_p50_ms": statistics.median(runtimes),
            "runtime_p95_ms": runtimes[math.ceil(0.95 * len(runtimes)) - 1],
            "peak_rss_platform_units": usage.ru_maxrss, "cases": measurements}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--se2-executable", type=Path,
                        help="optional existing bounded-se2-icp CLI for identical-input comparison")
    parser.add_argument("--output", type=Path, help="local structured result path")
    parser.add_argument("--require-expected", action="store_true")
    args = parser.parse_args()
    report = run_matrix(args.se2_executable)
    if args.output is not None:
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                               encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"},
                     sort_keys=True, allow_nan=False))
    return int(args.require_expected and (report["expected_status_mismatch_count"] != 0
                                          or report["false_candidate_count"] != 0
                                          or not report["repeated_structure_seed_ambiguity"]))


if __name__ == "__main__":
    raise SystemExit(main())
