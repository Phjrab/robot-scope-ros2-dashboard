#!/usr/bin/env python3
"""Generate a deterministic, hardware-free D1 registration benchmark."""

from __future__ import annotations

import argparse
import json
import math
import resource
import statistics
import struct
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from robot_dashboard.relocalization.models import SUPPORTED_BACKENDS  # noqa: E402
from robot_dashboard.relocalization.process_adapter import OfflineRegistrationProcess  # noqa: E402


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
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
    print(json.dumps({
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
    }, sort_keys=True))
    return 0 if acceptance_pass or not args.require_acceptance else 1


if __name__ == "__main__":
    raise SystemExit(main())
