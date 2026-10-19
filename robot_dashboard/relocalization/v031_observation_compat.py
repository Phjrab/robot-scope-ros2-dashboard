"""Dashboard policy adapter for the received v0.3.1 source, kept byte intact.

Only the residual gate changes, before the original branch ranking/retention
and ambiguity checks. Original scoring, fitting and lifecycle code is reused.
This never verifies a body pose, coordinate calibration or temporal tracking.
"""
from __future__ import annotations

from dataclasses import dataclass, field


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
    "schema": "robot-scope.global-provisional-selection.v1",
    "adapter": "dashboard-v031-residual-gate-v1",
    "original_max_rmse_m": 0.05,
    "provisional_max_rmse_m": 0.10,
    "scoring": "UNCHANGED_ORIGINAL_REFERENCE_POPULATION",
    "scope": "PROVISIONAL_OBSERVATION_ONLY",
    "original_selection_replayed": False,
}
ORIGINAL_GATE = "RMSE_ABOVE_0.05M"
PROVISIONAL_GATE = "RMSE_ABOVE_0.10M"


def supports_pin(files: dict[str, str]) -> bool:
    return files == REVIEWED_HASHES


def observer_class(backend):
    """Called only for the hash-verified backend inside its disposable child."""
    base = backend.SE3Observation
    @dataclass
    class ComparedCandidate(backend.Candidate):
        # Records the original residual gate, not an original 5 cm selection.
        # Subsequent stationarity/error/ambiguity gates stay in gate_reasons.
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
                PROVISIONAL_GATE if reason == ORIGINAL_GATE else reason
                for reason in original.gate_reasons
                if reason != ORIGINAL_GATE or not candidate.rmse_m <= 0.10
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
