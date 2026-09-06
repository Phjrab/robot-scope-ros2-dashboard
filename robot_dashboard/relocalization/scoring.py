"""Evidence-derived D1 confidence policy; convergence alone never accepts."""

from __future__ import annotations


def confidence_for(
    *,
    converged: bool,
    query_points: int,
    overlap_ratio: float,
    fitness: float,
    ambiguity_margin: float,
) -> str:
    if (
        not converged
        or query_points < 500
        or overlap_ratio < 0.30
        or fitness > 0.16
    ):
        return "REJECTED"
    if overlap_ratio >= 0.70 and fitness <= 0.04 and ambiguity_margin >= 0.15:
        return "HIGH"
    if overlap_ratio >= 0.50 and fitness <= 0.09 and ambiguity_margin >= 0.05:
        return "MEDIUM"
    return "LOW"
