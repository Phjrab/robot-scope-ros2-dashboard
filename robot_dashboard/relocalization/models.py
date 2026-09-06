"""Strict bounded models for the offline 3DoF registration boundary."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


RESULT_SCHEMA = "robot-scope.relocalization-result.v1"
BACKEND = "bounded-se2-icp"
CONFIDENCE_VALUES = {"HIGH", "MEDIUM", "LOW", "REJECTED"}
MAX_INPUT_BYTES = 16 * 1024
MAX_OUTPUT_BYTES = 64 * 1024
MAX_ERROR_BYTES = 4 * 1024


class RegistrationContractError(ValueError):
    """Input or output does not satisfy the fixed offline contract."""


def finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RegistrationContractError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise RegistrationContractError(f"{label} must be finite")
    return number


def bounded_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise RegistrationContractError(f"{label} is outside the fixed bounds")
    return int(value)


@dataclass(frozen=True)
class RegistrationRequest:
    reference_pcd: str
    query_pcd: str
    seed_x: float
    seed_y: float
    seed_yaw: float
    radius_m: float
    yaw_range_rad: float
    max_reference_points: int
    max_query_points: int
    timeout_ms: int

    @classmethod
    def parse(cls, payload: Any) -> "RegistrationRequest":
        if not isinstance(payload, Mapping) or set(payload) != {
            "reference_pcd", "query_pcd", "seed", "limits"
        }:
            raise RegistrationContractError("registration request schema is invalid")
        reference = payload.get("reference_pcd")
        query = payload.get("query_pcd")
        if not isinstance(reference, str) or not reference or len(reference) > 1024:
            raise RegistrationContractError("reference_pcd is invalid")
        if not isinstance(query, str) or not query or len(query) > 1024:
            raise RegistrationContractError("query_pcd is invalid")
        seed = payload.get("seed")
        limits = payload.get("limits")
        if not isinstance(seed, Mapping) or set(seed) != {
            "x", "y", "yaw", "radius_m", "yaw_range_rad"
        }:
            raise RegistrationContractError("seed schema is invalid")
        if not isinstance(limits, Mapping) or set(limits) != {
            "max_reference_points", "max_query_points", "timeout_ms"
        }:
            raise RegistrationContractError("limits schema is invalid")
        radius = finite_number(seed.get("radius_m"), "radius_m")
        yaw_range = finite_number(seed.get("yaw_range_rad"), "yaw_range_rad")
        if not 0.0 <= radius <= 10.0 or not 0.0 <= yaw_range <= math.pi:
            raise RegistrationContractError("seed search bounds are invalid")
        return cls(
            reference_pcd=reference,
            query_pcd=query,
            seed_x=finite_number(seed.get("x"), "seed x"),
            seed_y=finite_number(seed.get("y"), "seed y"),
            seed_yaw=finite_number(seed.get("yaw"), "seed yaw"),
            radius_m=radius,
            yaw_range_rad=yaw_range,
            max_reference_points=bounded_int(
                limits.get("max_reference_points"), "max_reference_points", 500, 1_000_000
            ),
            max_query_points=bounded_int(
                limits.get("max_query_points"), "max_query_points", 500, 150_000
            ),
            timeout_ms=bounded_int(limits.get("timeout_ms"), "timeout_ms", 100, 15_000),
        )

    def argv(self, executable: str, reference: str, query: str) -> list[str]:
        return [
            executable, reference, query,
            str(self.seed_x), str(self.seed_y), str(self.seed_yaw),
            str(self.radius_m), str(self.yaw_range_rad),
            str(self.max_reference_points), str(self.max_query_points), str(self.timeout_ms),
        ]


@dataclass(frozen=True)
class RegistrationResultSet:
    payload: dict[str, Any]

    @classmethod
    def parse(cls, payload: Any) -> "RegistrationResultSet":
        if not isinstance(payload, Mapping) or set(payload) != {
            "schema", "backend", "results", "timing"
        }:
            raise RegistrationContractError("registration result schema is invalid")
        if payload.get("schema") != RESULT_SCHEMA or payload.get("backend") != BACKEND:
            raise RegistrationContractError("registration result identity is invalid")
        results = payload.get("results")
        timing = payload.get("timing")
        if not isinstance(results, list) or not 1 <= len(results) <= 3:
            raise RegistrationContractError("registration result count is invalid")
        if not isinstance(timing, Mapping) or set(timing) != {
            "preprocess_ms", "coarse_ms", "refine_ms"
        }:
            raise RegistrationContractError("registration timing schema is invalid")
        normalized_timing = {
            key: finite_number(timing.get(key), key)
            for key in ("preprocess_ms", "coarse_ms", "refine_ms")
        }
        if any(value < 0.0 or value > 15_000.0 for value in normalized_timing.values()):
            raise RegistrationContractError("registration timing is invalid")
        normalized_results = []
        for index, item in enumerate(results, start=1):
            normalized_results.append(_parse_candidate(item, index))
        return cls({
            "schema": RESULT_SCHEMA,
            "backend": BACKEND,
            "results": normalized_results,
            "timing": normalized_timing,
        })


def _parse_candidate(payload: Any, rank: int) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != {
        "converged", "pose", "metrics", "confidence", "rank", "ambiguity_margin"
    }:
        raise RegistrationContractError("registration candidate schema is invalid")
    if not isinstance(payload.get("converged"), bool) or payload.get("rank") != rank:
        raise RegistrationContractError("registration candidate rank is invalid")
    pose = payload.get("pose")
    metrics = payload.get("metrics")
    if not isinstance(pose, Mapping) or set(pose) != {"x", "y", "yaw"}:
        raise RegistrationContractError("registration pose schema is invalid")
    if not isinstance(metrics, Mapping) or set(metrics) != {
        "fitness", "overlap_ratio", "inlier_ratio", "query_points",
        "reference_points", "runtime_ms"
    }:
        raise RegistrationContractError("registration metrics schema is invalid")
    confidence = payload.get("confidence")
    if confidence not in CONFIDENCE_VALUES:
        raise RegistrationContractError("registration confidence is invalid")
    overlap = finite_number(metrics.get("overlap_ratio"), "overlap_ratio")
    inlier = finite_number(metrics.get("inlier_ratio"), "inlier_ratio")
    fitness = finite_number(metrics.get("fitness"), "fitness")
    runtime = finite_number(metrics.get("runtime_ms"), "runtime_ms")
    margin = finite_number(payload.get("ambiguity_margin"), "ambiguity_margin")
    if not 0.0 <= overlap <= 1.0 or not 0.0 <= inlier <= 1.0:
        raise RegistrationContractError("registration ratios are invalid")
    if fitness < 0.0 or runtime < 0.0 or runtime > 15_000.0 or not 0.0 <= margin <= 1.0:
        raise RegistrationContractError("registration metrics are invalid")
    from .scoring import confidence_for

    expected = confidence_for(
        converged=payload["converged"],
        query_points=bounded_int(metrics.get("query_points"), "query_points", 1, 150_000),
        overlap_ratio=overlap,
        fitness=fitness,
        ambiguity_margin=margin,
    )
    if confidence != expected:
        raise RegistrationContractError("registration confidence does not match policy")
    return {
        "converged": payload["converged"],
        "pose": {key: finite_number(pose.get(key), key) for key in ("x", "y", "yaw")},
        "metrics": {
            "fitness": fitness,
            "overlap_ratio": overlap,
            "inlier_ratio": inlier,
            "query_points": bounded_int(metrics.get("query_points"), "query_points", 1, 150_000),
            "reference_points": bounded_int(
                metrics.get("reference_points"), "reference_points", 1, 1_000_000
            ),
            "runtime_ms": runtime,
        },
        "confidence": confidence,
        "rank": rank,
        "ambiguity_margin": margin,
    }
