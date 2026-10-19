"""Policy boundary tests; actual private backend replay is tested separately."""
from dataclasses import dataclass, field
from types import SimpleNamespace
import unittest

from robot_dashboard.relocalization.v031_observation_compat import (
    ORIGINAL_GATE, PROVISIONAL_GATE, REVIEWED_HASHES, SELECTION_POLICY,
    observer_class, supports_pin,
)


@dataclass
class Candidate:
    rmse_m: float
    gate_reasons: list = field(default_factory=list)
    scan_count: int = 879
    inlier_count: int = 835
    full_scan_rmse_m: float = .31


@dataclass
class Observation:
    candidates: list
    status: str = "OBSERVATION_ONLY_UNVERIFIED"


class Backend:
    def __init__(self, candidate):
        self.candidate = candidate

    def _score(self, scan, matrix, attempt, fitness=None):
        self.score_arguments = (scan, matrix, attempt, fitness)
        return self.candidate

    @staticmethod
    def _stage(name, candidate):
        return dict(stage=name, gate_reasons=list(candidate.gate_reasons),
                    rmse_m=candidate.rmse_m)

    def observe(self, scan_points):
        return Observation([self._score(scan_points, "matrix", 0)])


class V031CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.module = SimpleNamespace(Candidate=Candidate, Observation=Observation,
                                      SE3Observation=Backend)
        self.observer = observer_class(self.module)

    def test_gate_boundary_and_original_score_are_preserved(self):
        for rmse in (.05, .050000001, .07, .10, .100000001, float("inf")):
            with self.subTest(rmse=rmse):
                original_gates = [ORIGINAL_GATE] if rmse > .05 else []
                original = Candidate(rmse, original_gates.copy())
                observer = self.observer(original)
                candidate = observer._score("all_scan", "same_matrix", 2, .95)
                self.assertEqual(observer.score_arguments, ("all_scan", "same_matrix", 2, .95))
                self.assertEqual(candidate.rmse_m, rmse)
                self.assertEqual(candidate.scan_count, 879)
                self.assertEqual(candidate.inlier_count, 835)
                self.assertEqual(candidate.full_scan_rmse_m, .31)
                self.assertEqual(candidate.gate_reasons, [PROVISIONAL_GATE] if rmse > .10 else [])
                self.assertEqual(candidate.original_residual_gate, ORIGINAL_GATE if rmse > .05 else None)
                self.assertEqual(original.gate_reasons, original_gates)

    def test_non_residual_rejections_survive_before_and_after_scoring(self):
        reasons = ["INVALID_SE3", "FEWER_THAN_60_DISTINCT_INLIER_VOXELS",
                   "DEGENERATE_INLIER_GEOMETRY", "DEGENERATE_GEOMETRY",
                   "OVERLAP_BELOW_0.60", "FEWER_THAN_60_INLIERS"]
        candidate = self.observer(Candidate(.07, reasons + [ORIGINAL_GATE]))._score(None, None, 0)
        self.assertEqual(candidate.gate_reasons, reasons)
        candidate.gate_reasons += ["REFINEMENT_NOT_STATIONARY", "REGISTRATION_ERROR",
                                   "FAILED_RANSAC", "AMBIGUOUS_ALTERNATIVES"]
        stage = self.observer._stage("refinement", candidate)
        self.assertEqual(stage["gate_reasons"], candidate.gate_reasons)
        self.assertEqual(stage["original_residual_gate"], ORIGINAL_GATE)

    def test_child_binding_patch_does_not_recurse_and_result_stays_unverified(self):
        self.module.SE3Observation = self.observer
        result = self.observer(Candidate(.07, [ORIGINAL_GATE])).observe("scan")
        stage = self.observer._stage("proposal", result.candidates[0])
        self.assertEqual(stage["rmse_m"], .07)
        self.assertEqual(result.status, "OBSERVATION_ONLY_UNVERIFIED")
        self.assertEqual(result.selection_policy, SELECTION_POLICY)
        self.assertFalse(result.selection_policy["original_selection_replayed"])

    def test_only_reviewed_source_receives_adapter(self):
        self.assertTrue(supports_pin(dict(REVIEWED_HASHES)))
        for filename in REVIEWED_HASHES:
            files = dict(REVIEWED_HASHES)
            files[filename] = "0" * 64
            self.assertFalse(supports_pin(files))
        self.assertFalse(supports_pin({}))
        self.assertFalse(supports_pin({**REVIEWED_HASHES, "extra.py": "0" * 64}))


if __name__ == "__main__":
    unittest.main()
