"""Dashboard policy adapter for the received v0.3.1 source, kept byte intact.

Only the numerical residual selection gate is removed, before the original
branch ranking/retention and ambiguity checks. The 5 cm and 10 cm thresholds
remain comparison metrics. Original scoring, fitting and lifecycle code is reused.
This never verifies a body pose, coordinate calibration or temporal tracking.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

import numpy as np


REVIEWED_HASHES = {
    "auto_localization/__init__.py": "f25384be464f4f5262f3c218b83fd9aadb8e511ee72ade354c20a48e10fb7711",
    "auto_localization/engine.py": "8b38adcc876b3dfb9b7277e0190e465f1fafa3e2731412e20b2101609a6c0061",
    "auto_localization/observation_adapter.py": "c1a01e6aad05fda1ab962cbb4e7b3e23792fc7cccdbf7e52236dae583ed1908d",
    "auto_localization/open3d_backend.py": "d28f216f973d69e60a2c273d92c177ec4ccdeab0bc613e518b54ccab239b1036",
    "auto_localization/replay.py": "7fffb24b6899c758647ff6197bdb1ed16dd6efa637f73a0667ef92c398bd5a0a",
    "auto_localization/se3_observation.py": "bb3205011ae188bfc20d059c9708e31fb0270fdac515b7663093aad3fccfd5a9",
    "auto_localization/isolated.py": "a9693de08db555c95d59d864df8d5a8ccd52610aaeb50f08f541cec6288f39a2",
}
SELECTION_POLICY = {
    "schema": "robot-scope.global-provisional-selection.v2",
    "adapter": "dashboard-v031-observation-no-rmse-gate-v1",
    "original_max_rmse_m": 0.05,
    "provisional_max_rmse_m": 0.10,
    "rmse_thresholds_purpose": "COMPARISON_ONLY",
    "rmse_selection_gate_enabled": False,
    "scoring": "UNCHANGED_ORIGINAL_REFERENCE_POPULATION",
    "scope": "PROVISIONAL_OBSERVATION_ONLY",
    "original_selection_replayed": False,
}
ORIGINAL_GATE = "RMSE_ABOVE_0.05M"
AMBIGUITY_GATE = "AMBIGUOUS_ALTERNATIVES"
AMBIGUITY_SELECTION_RULE = "LOWEST_RMSE_M_THEN_ORIGINAL_INDEX"
AMBIGUOUS_ESTIMATE_LABEL = "AMBIGUOUS_UNVERIFIED_ESTIMATE"


def supports_pin(files: dict[str, str]) -> bool:
    return files == REVIEWED_HASHES


def _finite_nonnegative(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _ambiguity_eligible(candidate: Any) -> bool:
    """The original finish may add only its ambiguity reason to a sound fit."""
    if not isinstance(candidate, dict) or candidate.get("gate_reasons") != [AMBIGUITY_GATE]:
        return False
    count, inliers, voxels = (candidate.get(key) for key in
                              ("scan_count", "inlier_count", "distinct_inlier_voxel_count"))
    if (candidate.get("refinement_stationary") is not True
            or type(count) is not int or type(inliers) is not int or type(voxels) is not int
            or not 60 <= voxels <= inliers <= count
            or not all(_finite_nonnegative(candidate.get(key)) for key in
                       ("rmse_m", "full_scan_rmse_m", "capped_full_rmse_m",
                        "overlap", "geometry_min_max_eigen_ratio",
                        "inlier_geometry_min_max_eigen_ratio"))
            or not .60 <= candidate["overlap"] <= 1.
            or candidate["geometry_min_max_eigen_ratio"] < .002
            or candidate["inlier_geometry_min_max_eigen_ratio"] < .002):
        return False
    try:
        matrix = np.asarray(candidate["map_from_scan"], dtype=float)
        return bool(matrix.shape == (4, 4) and np.isfinite(matrix).all()
                    and np.allclose(matrix[3], [0., 0., 0., 1.], atol=1e-8)
                    and np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-6)
                    and math.isclose(float(np.linalg.det(matrix[:3, :3])), 1., abs_tol=1e-6))
    except (KeyError, TypeError, ValueError):
        return False


def _ambiguity_choice(observation: dict[str, Any]) -> int | None:
    candidates = observation.get("candidates")
    if not isinstance(candidates, list):
        return None
    eligible = [(candidate["rmse_m"], index) for index, candidate in enumerate(candidates)
                if _ambiguity_eligible(candidate)]
    return min(eligible)[1] if eligible else None


def apply_ambiguity_override(observation: dict[str, Any], *, allow_ambiguous: bool) -> dict[str, Any]:
    """After the original finish, select one ambiguous fit for observation only.

    The original top and candidate gates, alternatives, scores and diagnostics
    remain untouched. An absent/false opt-in never selects an ambiguous fit.
    """
    if type(allow_ambiguous) is not bool:
        raise TypeError("allow_ambiguous must be a bool")
    observation["ambiguity_override"] = {"enabled": allow_ambiguous, "applied": False}
    if (not allow_ambiguous or observation.get("gate_reasons") != [AMBIGUITY_GATE]
            or observation.get("selected_candidate") is not None):
        return observation
    selected = _ambiguity_choice(observation)
    if selected is None:
        return observation
    observation["selected_candidate"] = selected
    observation["ambiguity_override"] = {
        "enabled": True, "applied": True,
        "selection_rule": AMBIGUITY_SELECTION_RULE,
        "original_selected_candidate": None,
        "original_gate_reasons": [AMBIGUITY_GATE],
    }
    observation["estimate_label"] = AMBIGUOUS_ESTIMATE_LABEL
    return observation


def valid_ambiguity_override(observation: Any, *, allowed: bool) -> bool:
    """Fail-closed check shared by global/local result consumers and owners."""
    if type(allowed) is not bool or not allowed or not isinstance(observation, dict):
        return False
    override = observation.get("ambiguity_override")
    if (not isinstance(override, dict)
            or type(override.get("enabled")) is not bool
            or type(override.get("applied")) is not bool
            or override != {"enabled": True, "applied": True,
                            "selection_rule": AMBIGUITY_SELECTION_RULE,
                            "original_selected_candidate": None,
                            "original_gate_reasons": [AMBIGUITY_GATE]}
            or observation.get("estimate_label") != AMBIGUOUS_ESTIMATE_LABEL
            or observation.get("gate_reasons") != [AMBIGUITY_GATE]):
        return False
    selected = observation.get("selected_candidate")
    return type(selected) is int and selected == _ambiguity_choice(observation)


def observer_class(backend):
    """Called only for the hash-verified backend inside its disposable child."""
    base = backend.SE3Observation
    @dataclass
    class ComparedCandidate(backend.Candidate):
        # Records the original residual comparison, not an original 5 cm selection.
        # Other geometry/overlap/stationarity/error/ambiguity gates stay intact.
        original_residual_gate: str | None = None

    @dataclass
    class ProvisionalObservation(backend.Observation):
        selection_policy: dict = field(default_factory=lambda: dict(SELECTION_POLICY))

    class ProvisionalObserver(base):
        def _score(self, scan, matrix, attempt, fitness=None):
            original = super()._score(scan, matrix, attempt, fitness)
            candidate = ComparedCandidate(**vars(original))
            candidate.original_residual_gate = (
                ORIGINAL_GATE if ORIGINAL_GATE in original.gate_reasons else None
            )
            candidate.gate_reasons = [
                reason for reason in original.gate_reasons if reason != ORIGINAL_GATE
            ]
            return candidate

        @staticmethod
        def _stage(name, candidate):
            value = base._stage(name, candidate)
            value["original_residual_gate"] = candidate.original_residual_gate
            return value

        def observe(self, scan_points):
            result = super().observe(scan_points)
            return ProvisionalObservation(**vars(result))

    return ProvisionalObserver


def _provisional_worker(manifest_path, unused_backend, output):
    # The original isolated worker imports SE3Observation in this child. Patch
    # that in-memory binding only; the verified source copy is never edited.
    from auto_localization import isolated, se3_observation

    original = se3_observation.SE3Observation
    se3_observation.SE3Observation = observer_class(se3_observation)
    try:
        isolated._se3_worker(manifest_path, unused_backend, output)
    finally:
        se3_observation.SE3Observation = original


def run_provisional_isolated(manifest_path, timeout_s, max_results):
    from auto_localization.isolated import _run_isolated

    return _run_isolated(manifest_path, timeout_s, None, False,
                         max_results, _provisional_worker)
