"""Numerical qualification for live observation hypotheses, never body localization.

The solver's original 5 cm result is retained. Only this wrapper uses the fixed
provisional residual policy. It reevaluates every numerical gate independently;
removing HIGH_RESIDUAL from a reason string would hide nonconvergence.
"""
from __future__ import annotations

import math
from typing import Any

from .experimental_se3 import MIN_GEOMETRY_RATIO, MIN_OVERLAP, MIN_POINTS
from .residual_policy import PROVISIONAL_RESIDUAL_POLICY, evaluate_residual


def qualify_observation(result: dict[str, Any], *, inlier_count: int,
                        query_count: int) -> dict[str, Any]:
    """Assess unchanged final scores; caller must still enforce all source fences.

This function does not mutate the solver result or choose among global basins.
It is only for the existing bounded single-hypothesis point-to-point path.
"""
    metrics = result["metrics"]
    original = {"status": result["status"], "reason": result["reason"], "max_rmse_m": .05}
    reasons: list[str] = []
    rmse = metrics.get("rmse_m")
    try:
        residual = evaluate_residual(rmse, policy=PROVISIONAL_RESIDUAL_POLICY).as_dict()
    except ValueError:
        residual = None
        reasons.append("RESIDUAL_UNAVAILABLE")
    else:
        if not residual["residual_passed"]:
            reasons.append("HIGH_RESIDUAL")

    def bounded_number(value: Any, lower: float, upper: float = 1.) -> bool:
        return (type(value) in (int, float) and math.isfinite(value)
                and lower <= value <= upper)

    if metrics.get("converged") is not True:
        reasons.append("NOT_CONVERGED")
    if not bounded_number(metrics.get("overlap_ratio"), MIN_OVERLAP):
        reasons.append("LOW_OVERLAP")
    if (type(inlier_count) is not int or type(query_count) is not int
            or not MIN_POINTS <= inlier_count <= query_count):
        reasons.append("INSUFFICIENT_INLIERS")
    if not bounded_number(metrics.get("geometry_min_max_eigen_ratio"), MIN_GEOMETRY_RATIO):
        reasons.append("DEGENERATE_GEOMETRY")
    if not bounded_number(metrics.get("matched_geometry_min_max_eigen_ratio"), MIN_GEOMETRY_RATIO):
        reasons.append("DEGENERATE_MATCHED_GEOMETRY")
    # Only the residual-only failure may be relaxed. Retain explicit other
    # solver failures even if a future solver supplies contradictory metrics.
    original_pair = (result.get("status"), result.get("reason"))
    known_nonresidual = {"NOT_CONVERGED", "LOW_OVERLAP", "DEGENERATE_GEOMETRY",
                         "DEGENERATE_MATCHED_GEOMETRY"}
    if original_pair == ("REJECTED", "HIGH_RESIDUAL"):
        consistent = residual is not None and not residual["original_residual_passed"]
    elif original_pair == ("CANDIDATE", "CANDIDATE"):
        consistent = residual is not None and residual["original_residual_passed"]
    elif original_pair[0] == "REJECTED" and original_pair[1] in known_nonresidual:
        if original_pair[1] not in reasons:
            reasons.append(original_pair[1])
        consistent = True
    else:
        consistent = False
    if not consistent:
        reasons.append("ORIGINAL_SOLVER_REJECTED")
    return {"status": "REJECTED" if reasons else "CANDIDATE",
            "reason": reasons[0] if reasons else "CANDIDATE", "gate_reasons": reasons,
            "original_assessment": original, "residual_evaluation": residual,
            "provisional": True, "candidate_kind": "PROVISIONAL_OBSERVATION_HYPOTHESIS",
            "body_pose": None, "tracking_verified": False}
