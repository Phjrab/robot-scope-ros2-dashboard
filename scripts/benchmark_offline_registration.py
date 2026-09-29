#!/usr/bin/env python3
"""Generate a deterministic, hardware-free D1 registration benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
import resource
import statistics
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from robot_dashboard.relocalization.models import SUPPORTED_BACKENDS  # noqa: E402
from robot_dashboard.relocalization.process_adapter import OfflineRegistrationProcess  # noqa: E402
from robot_dashboard.relocalization.process_adapter import (  # noqa: E402
    RegistrationProcessError,
)
from robot_dashboard.relocalization.models import RegistrationContractError  # noqa: E402


CASES = (
    (0.40, -0.30, 0.20),
    (-0.35, 0.25, -0.18),
    (0.00, 0.00, 0.25),
    (0.45, -0.20, 0.00),
    (-0.30, 0.30, -0.22),
    (0.35, 0.20, 0.18),
    (0.25, -0.25, 0.15),
    (-0.25, -0.35, -0.17),
    (0.30, -0.25, 0.20),
    (-0.40, 0.15, 0.12),
)

MAX_TRANSLATION_MEDIAN_M = 0.15
MAX_TRANSLATION_P95_M = 0.30
MAX_YAW_MEDIAN_DEG = 3.0
MAX_YAW_P95_DEG = 8.0


def cloud() -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []
    for layer in range(5):
        z = -0.4 + layer * 0.2
        for step in range(121):
            value = -6.0 + step * 0.1
            points.extend(((value, -4.0, z), (value, 4.0, z), (-6.0, value * 2 / 3, z)))
            if step < 80:
                points.append((6.0, -4.0 + step * 0.1, z))
        for step in range(63):
            angle = step * 0.1
            points.append((2.1 + 0.35 * math.cos(angle), 1.2 + 0.35 * math.sin(angle), z))
    return points


def inverse(
    points: list[tuple[float, float, float]],
    pose: tuple[float, float, float],
) -> list[tuple[float, float, float]]:
    x_pose, y_pose, yaw = pose
    cosine, sine = math.cos(yaw), math.sin(yaw)
    return [
        (cosine * (x - x_pose) + sine * (y - y_pose),
         -sine * (x - x_pose) + cosine * (y - y_pose), z)
        for x, y, z in points
    ]


def write_pcd(path: Path, points: list[tuple[float, float, float]]) -> None:
    header = (
        "# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\n"
        f"COUNT 1 1 1\nWIDTH {len(points)}\nHEIGHT 1\nPOINTS {len(points)}\nDATA binary\n"
    ).encode("ascii")
    path.write_bytes(header + b"".join(struct.pack("fff", *point) for point in points))


def percentile(values: list[float], fraction: float) -> float:
    return sorted(values)[max(0, math.ceil(fraction * len(values)) - 1)]


def l_corridor() -> list[tuple[float, float, float]]:
    points = []
    for layer in range(5):
        z = -0.4 + layer * 0.2
        for step in range(161):
            value = -8.0 + step * 0.1
            points.append((value, -2.5, z))
            if value <= 2.5:
                points.append((value, 2.5, z))
            points.append((2.5, value, z))
    return points


def pillars() -> list[tuple[float, float, float]]:
    points = []
    for layer in range(15):
        z = -1.4 + layer * 0.2
        for center_x, center_y in ((-3.0, -2.0), (2.0, -1.0), (3.5, 2.5), (-1.0, 3.0)):
            for step in range(64):
                angle = step * 2 * math.pi / 64
                points.append((center_x + 0.4 * math.cos(angle), center_y + 0.4 * math.sin(angle), z))
    return points


def repeated_corridor() -> list[tuple[float, float, float]]:
    points = []
    for layer in range(5):
        z = -0.4 + layer * 0.2
        for step in range(181):
            x = -9.0 + step * 0.1
            points.extend(((x, -2.0, z), (x, 2.0, z)))
        for center in range(-8, 9, 2):
            for step in range(32):
                angle = step * 2 * math.pi / 32
                points.append((center + 0.25 * math.cos(angle), 0.25 * math.sin(angle), z))
    return points


def degrade(
    points: list[tuple[float, float, float]],
    *,
    dropout: float = 0.0,
    noise: float = 0.0,
    outliers: float = 0.0,
    partial: bool = False,
) -> list[tuple[float, float, float]]:
    rng = random.Random(2048)
    selected = [point for point in points if not partial or point[0] >= -0.5]
    selected = [point for point in selected if rng.random() >= dropout]
    result = [tuple(value + rng.gauss(0.0, noise) for value in point) for point in selected]
    for _ in range(int(len(result) * outliers)):
        result.append((rng.uniform(-15, 15), rng.uniform(-15, 15), rng.uniform(-1, 2)))
    return result


def matrix_cases() -> list[dict]:
    """Fixed synthetic corpus. Truth exists only for deliberately transformed queries."""
    cases = []
    room = cloud()
    for index, pose in enumerate(CASES):
        cases.append({"id": f"baseline-{index:02d}", "group": "baseline",
                      "reference": room, "query": inverse(room, pose), "truth": pose,
                      "expectation": "accept"})
    variants = (
        ("asymmetric-l-corridor", l_corridor(), (-0.35, 0.25, -0.18), {}),
        ("pillars-height-structure", pillars(), (0.30, 0.35, 0.22), {}),
        ("partial-fov", room, (0.30, -0.25, 0.20), {"partial": True}),
        ("density-dropout-30", room, (-0.30, 0.30, -0.22), {"dropout": 0.30}),
        ("density-dropout-50", room, (0.35, 0.20, 0.18), {"dropout": 0.50}),
        ("gaussian-noise-002", l_corridor(), (0.25, -0.25, 0.15), {"noise": 0.02}),
        ("outliers-20-percent", pillars(), (-0.25, -0.35, -0.17), {"outliers": 0.20}),
    )
    for name, reference, pose, degradation in variants:
        cases.append({"id": name, "group": "degraded", "reference": reference,
                      "query": degrade(inverse(reference, pose), **degradation),
                      "truth": pose, "expectation": "observe"})
    pose = (0.40, -0.30, 0.20)
    for name, seed in (
        ("initial-xy-offset", {"x": 0.25, "y": -0.25}),
        ("initial-yaw-offset", {"yaw": 0.35}),
        ("large-initial-yaw-error", {"yaw": 2.5, "yaw_range_rad": 0.1}),
    ):
        cases.append({"id": name, "group": "seed_sensitivity", "reference": room,
                      "query": inverse(room, pose), "truth": pose,
                      "seed": seed, "expectation": "observe"})
    repeated = repeated_corridor()
    cases.append({"id": "repeated-symmetric-corridor", "group": "ambiguity",
                  "reference": repeated, "query": inverse(repeated, (0.5, 0.0, 0.0)),
                  "truth": (0.5, 0.0, 0.0), "expectation": "not_high"})
    cases.extend((
        {"id": "wrong-map-no-overlap", "group": "invalid", "reference": room,
         "query": [(x + 30.0, y + 30.0, z) for x, y, z in room], "expectation": "reject"},
        {"id": "wrong-seed", "group": "invalid", "reference": room,
         "query": room, "seed": {"x": 50.0, "y": 50.0, "radius_m": 0.2,
                                  "yaw_range_rad": 0.1}, "expectation": "reject"},
        {"id": "millimetre-unit-mismatch", "group": "invalid", "reference": room,
         "query": [(x * 1000.0, y * 1000.0, z * 1000.0) for x, y, z in room],
         "expectation": "reject"},
        {"id": "z-frame-offset", "group": "invalid", "reference": room,
         "query": [(x, y, z + 5.0) for x, y, z in room], "expectation": "reject"},
        {"id": "insufficient-points", "group": "invalid", "reference": room,
         "query": room[:100], "expectation": "reject"},
        {"id": "nonfinite-points", "group": "invalid", "reference": room,
         "query": [(float("nan"), y, z) for _, y, z in room], "expectation": "reject"},
    ))
    return cases


def _request(reference: Path, query: Path, seed: dict | None = None,
             timeout_ms: int = 15_000) -> dict:
    return {
        "reference_pcd": str(reference), "query_pcd": str(query),
        "seed": {"x": 0.0, "y": 0.0, "yaw": 0.0, "radius_m": 0.8,
                 "yaw_range_rad": 0.5, **(seed or {})},
        "limits": {"max_reference_points": 100_000, "max_query_points": 100_000,
                   "timeout_ms": timeout_ms},
    }


def _git_commit() -> str | None:
    completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                               capture_output=True, text=True, check=False)
    return completed.stdout.strip() if completed.returncode == 0 else None


def _source_tree_dirty() -> bool:
    completed = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                               capture_output=True, text=True, check=False)
    return completed.returncode != 0 or bool(completed.stdout.strip())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extended_benchmark(executable: Path, backend: str, build_label: str) -> dict:
    cases = matrix_cases()
    records = []
    with tempfile.TemporaryDirectory(prefix="robot-scope-d1-matrix-") as directory:
        root = Path(directory)
        adapter = OfflineRegistrationProcess(executable.resolve(strict=True), [root],
                                             expected_backend=backend)
        for case in cases:
            reference = root / f"{case['id']}-reference.pcd"
            query = root / f"{case['id']}-query.pcd"
            write_pcd(reference, case["reference"])
            write_pcd(query, case["query"])
            record = {"id": case["id"], "group": case["group"],
                      "data_kind": "SYNTHETIC", "expectation": case["expectation"],
                      "reference_points": len(case["reference"]),
                      "query_points": len(case["query"]),
                      "reference_sha256": _sha256(reference), "query_sha256": _sha256(query),
                      "seed": _request(reference, query, case.get("seed"))["seed"]}
            started = time.monotonic()
            try:
                result = adapter.run(_request(reference, query, case.get("seed")))
                candidate = result["results"][0]
                record.update(outcome="accepted" if candidate["confidence"] != "REJECTED" else "rejected",
                              converged=candidate["converged"], confidence=candidate["confidence"],
                              metrics=candidate["metrics"], pose=candidate["pose"])
                if "truth" in case:
                    truth = case["truth"]
                    record["truth"] = {"x": truth[0], "y": truth[1], "yaw": truth[2]}
                    record["translation_error_m"] = math.hypot(
                        candidate["pose"]["x"] - truth[0], candidate["pose"]["y"] - truth[1])
                    record["yaw_error_deg"] = math.degrees(abs(math.atan2(
                        math.sin(candidate["pose"]["yaw"] - truth[2]),
                        math.cos(candidate["pose"]["yaw"] - truth[2]))))
            except RegistrationContractError as exc:
                record["outcome"] = "input_rejected"
                record["failure_reason"] = str(exc)[:256]
            except RegistrationProcessError as exc:
                record["outcome"] = "timeout" if "timed out" in str(exc) else "process_error"
                record["failure_reason"] = str(exc)[:256]
            record["wall_ms"] = round((time.monotonic() - started) * 1000.0, 3)
            record["expectation_met"] = None if case["expectation"] == "observe" else (
                (case["expectation"] == "accept" and record["outcome"] == "accepted")
                or (case["expectation"] == "reject" and record["outcome"] in
                    {"rejected", "input_rejected", "process_error"})
                or (case["expectation"] == "not_high" and record["outcome"] in
                    {"accepted", "rejected"} and record.get("confidence") != "HIGH")
            )
            records.append(record)
        engine_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        reference = root / "failure-injection-reference.pcd"
        query = root / "failure-injection-query.pcd"
        write_pcd(reference, cloud())
        write_pcd(query, cloud())
        for name, body, timeout_ms, expected in (
            ("injected-timeout", "import time\ntime.sleep(1)\n", 100, "timeout"),
            ("injected-crash", "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n",
             1000, "process_error"),
        ):
            fake_executable = root / name
            fake_executable.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
            fake_executable.chmod(0o700)
            fake_adapter = OfflineRegistrationProcess(fake_executable, [root],
                                                      expected_backend=backend)
            started = time.monotonic()
            try:
                fake_adapter.run(_request(reference, query, timeout_ms=timeout_ms))
                outcome = "unexpected_success"
            except RegistrationProcessError as exc:
                outcome = "timeout" if "timed out" in str(exc) else "process_error"
            records.append({"id": name, "group": "harness_failure_injection",
                            "data_kind": "SYNTHETIC", "expectation": expected,
                            "outcome": outcome, "expectation_met": outcome == expected,
                            "wall_ms": round((time.monotonic() - started) * 1000.0, 3),
                            "timeout_ms": timeout_ms, "injected_executable_sha256": _sha256(fake_executable)})
    negative = [record for record in records if record["expectation"] == "reject"]
    runtimes = [record["metrics"]["runtime_ms"] for record in records if "metrics" in record]
    scored = [record for record in records if record["outcome"] == "accepted" and
              "translation_error_m" in record]
    translation_errors = [record["translation_error_m"] for record in scored]
    yaw_errors = [record["yaw_error_deg"] for record in scored]
    wall = [record["wall_ms"] for record in records]
    manifest = [{key: record[key] for key in ("id", "expectation", "reference_sha256",
                                              "query_sha256", "seed") if key in record}
                for record in records]
    harness_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "schema": "robot-scope.registration-matrix.v1", "backend": backend,
        "source_commit": _git_commit(), "executable_sha256": _sha256(executable),
        "source_tree_dirty": _source_tree_dirty(),
        "benchmark_sha256": _sha256(Path(__file__)),
        "registration_source_sha256": {
            name: _sha256(ROOT / "ros2" / "robot_scope_registration" / name)
            for name in ("CMakeLists.txt", "src/registration_core.cpp",
                         "src/offline_registration_cli.cpp")
        },
        "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
        "build_label": build_label, "platform": platform.platform(),
        "python": platform.python_version(), "data_kind": "SYNTHETIC",
        "ground_truth_source": "known inverse transform of the same generated reference cloud",
        "request_limits": {"max_reference_points": 100_000, "max_query_points": 100_000,
                           "timeout_ms": 15_000},
        "degradation_random_seed": 2048,
        "case_count": len(records),
        "accepted_count": sum(record["outcome"] == "accepted" for record in records),
        "converged_count": sum(record.get("converged") is True for record in records),
        "false_acceptance_count": sum(record["outcome"] == "accepted" for record in negative),
        "expected_rejection_count": len(negative),
        "observation_count": sum(record["expectation"] == "observe" for record in records),
        "accepted_with_truth_count": len(scored),
        "translation_median_m": statistics.median(translation_errors) if scored else None,
        "translation_p95_m": percentile(translation_errors, 0.95) if scored else None,
        "yaw_median_deg": statistics.median(yaw_errors) if scored else None,
        "yaw_p95_deg": percentile(yaw_errors, 0.95) if scored else None,
        "expectation_failure_count": sum(record["expectation_met"] is False
                                         for record in records),
        "timeout_count": sum(record["outcome"] == "timeout" for record in records),
        "process_error_count": sum(record["outcome"] == "process_error" for record in records),
        "engine_process_error_count": sum(record["outcome"] == "process_error" and
                                          record["group"] != "harness_failure_injection"
                                          for record in records),
        "runtime_p50_ms": statistics.median(runtimes) if runtimes else None,
        "runtime_p95_ms": percentile(runtimes, 0.95) if runtimes else None,
        "wall_p50_ms": statistics.median(wall), "wall_p95_ms": percentile(wall, 0.95),
        "engine_child_peak_rss_platform_units": engine_usage.ru_maxrss,
        "harness_child_peak_rss_platform_units": harness_usage.ru_maxrss,
        "cases": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--suite", choices=("baseline", "extended"), default="baseline")
    parser.add_argument("--output", type=Path, help="write a structured local result file")
    parser.add_argument("--build-label", default="unspecified",
                        help="human-readable compiler/options label for extended results")
    parser.add_argument(
        "--backend",
        choices=sorted(SUPPORTED_BACKENDS),
        default="bounded-se2-icp",
    )
    parser.add_argument(
        "--require-acceptance",
        action="store_true",
        help="exit non-zero unless every case converges and D1 error limits pass",
    )
    args = parser.parse_args()
    if args.suite == "extended":
        report = extended_benchmark(args.executable, args.backend, args.build_label)
        if args.output is not None:
            args.output.write_text(json.dumps(report, indent=2, sort_keys=True,
                                              allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({key: value for key, value in report.items() if key != "cases"},
                         sort_keys=True, allow_nan=False))
        return int(args.require_acceptance and (
            report["false_acceptance_count"] != 0
            or report["expectation_failure_count"] != 0
        ))
    translation_errors: list[float] = []
    yaw_errors: list[float] = []
    runtimes: list[float] = []
    converged_cases = 0
    accepted_cases = 0
    source = cloud()
    with tempfile.TemporaryDirectory(prefix="robot-scope-d1-benchmark-") as directory:
        root = Path(directory)
        reference = root / "reference.pcd"
        write_pcd(reference, source)
        adapter = OfflineRegistrationProcess(
            args.executable.resolve(strict=True),
            [root],
            expected_backend=args.backend,
        )
        for index, truth in enumerate(CASES):
            query = root / f"query-{index}.pcd"
            write_pcd(query, inverse(source, truth))
            result = adapter.run({
                "reference_pcd": str(reference),
                "query_pcd": str(query),
                "seed": {"x": 0.0, "y": 0.0, "yaw": 0.0, "radius_m": 0.8, "yaw_range_rad": 0.5},
                "limits": {"max_reference_points": 100_000, "max_query_points": 100_000, "timeout_ms": 15_000},
            })
            best = result["results"][0]
            converged_cases += int(best["converged"] is True)
            accepted_cases += int(best["confidence"] != "REJECTED")
            translation_errors.append(math.hypot(best["pose"]["x"] - truth[0], best["pose"]["y"] - truth[1]))
            yaw_errors.append(math.degrees(abs(math.atan2(
                math.sin(best["pose"]["yaw"] - truth[2]),
                math.cos(best["pose"]["yaw"] - truth[2]),
            ))))
            runtimes.append(best["metrics"]["runtime_ms"])
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    translation_median = statistics.median(translation_errors)
    translation_p95 = percentile(translation_errors, 0.95)
    yaw_median = statistics.median(yaw_errors)
    yaw_p95 = percentile(yaw_errors, 0.95)
    acceptance_pass = (
        converged_cases == len(CASES)
        and accepted_cases == len(CASES)
        and translation_median <= MAX_TRANSLATION_MEDIAN_M
        and translation_p95 <= MAX_TRANSLATION_P95_M
        and yaw_median <= MAX_YAW_MEDIAN_DEG
        and yaw_p95 <= MAX_YAW_P95_DEG
    )
    report = {
        "schema": "robot-scope.registration-benchmark.v1",
        "backend": args.backend,
        "cases": len(CASES),
        "converged_cases": converged_cases,
        "accepted_cases": accepted_cases,
        "acceptance_pass": acceptance_pass,
        "input_points": len(source),
        "translation_median_m": translation_median,
        "translation_p95_m": translation_p95,
        "yaw_median_deg": yaw_median,
        "yaw_p95_deg": yaw_p95,
        "runtime_p50_ms": statistics.median(runtimes),
        "runtime_p95_ms": percentile(runtimes, 0.95),
        "child_peak_rss_platform_units": usage.ru_maxrss,
    }
    if args.output is not None:
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True,
                                          allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if acceptance_pass or not args.require_acceptance else 1


if __name__ == "__main__":
    raise SystemExit(main())
