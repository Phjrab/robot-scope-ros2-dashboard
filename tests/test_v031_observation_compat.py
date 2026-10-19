"""Policy boundary tests; actual private backend replay is tested separately."""
from dataclasses import dataclass, field
import copy
from types import SimpleNamespace
import unittest

from robot_dashboard.relocalization.v031_observation_compat import (
    AMBIGUITY_GATE, AMBIGUOUS_ESTIMATE_LABEL, AMBIGUITY_SELECTION_RULE,
    ORIGINAL_GATE, REVIEWED_HASHES, SELECTION_POLICY,
    apply_ambiguity_override, observer_class, supports_pin, valid_ambiguity_override,
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

    def _finish(self, candidates):
        return "ORIGINAL_FINISH", candidates

    def observe(self, scan_points):
        return Observation([self._score(scan_points, "matrix", 0)])


class V031CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.module = SimpleNamespace(Candidate=Candidate, Observation=Observation,
                                      SE3Observation=Backend)
        self.observer = observer_class(self.module)

    def test_all_numerical_rmse_boundaries_are_comparisons_only(self):
        for rmse in (.05, .050000001, .07, .10, .100000001, .14, float("inf")):
            with self.subTest(rmse=rmse):
                # The pinned backend also rejects an infinite score for missing
                # matched support; removing its residual gate cannot remove that.
                support_gates = ["FEWER_THAN_60_INLIERS", "OVERLAP_BELOW_0.60"] if rmse == float("inf") else []
                original_gates = ([ORIGINAL_GATE] if rmse > .05 else []) + support_gates
                original = Candidate(rmse, original_gates.copy())
                observer = self.observer(original)
                candidate = observer._score("all_scan", "same_matrix", 2, .95)
                self.assertEqual(observer.score_arguments, ("all_scan", "same_matrix", 2, .95))
                self.assertEqual(candidate.rmse_m, rmse)
                self.assertEqual(candidate.scan_count, 879)
                self.assertEqual(candidate.inlier_count, 835)
                self.assertEqual(candidate.full_scan_rmse_m, .31)
                self.assertEqual(candidate.gate_reasons, support_gates)
                self.assertEqual(candidate.original_residual_gate, ORIGINAL_GATE if rmse > .05 else None)
                self.assertEqual(original.gate_reasons, original_gates)

    def test_original_candidate_finish_and_ambiguity_logic_are_inherited(self):
        self.assertIs(self.observer._finish, Backend._finish)
        candidates = [Candidate(.14), Candidate(.07)]
        self.assertEqual(self.observer(candidates[0])._finish(candidates),
                         ("ORIGINAL_FINISH", candidates))

    def test_non_residual_rejections_survive_before_and_after_scoring(self):
        reasons = ["INVALID_SE3", "FEWER_THAN_60_DISTINCT_INLIER_VOXELS",
                   "DEGENERATE_INLIER_GEOMETRY", "DEGENERATE_GEOMETRY",
                   "OVERLAP_BELOW_0.60", "FEWER_THAN_60_INLIERS"]
        candidate = self.observer(Candidate(.14, reasons + [ORIGINAL_GATE]))._score(None, None, 0)
        self.assertEqual(candidate.gate_reasons, reasons)
        candidate.gate_reasons += ["REFINEMENT_NOT_STATIONARY", "REGISTRATION_ERROR",
                                   "FAILED_RANSAC", "AMBIGUOUS_ALTERNATIVES"]
        stage = self.observer._stage("refinement", candidate)
        self.assertEqual(stage["gate_reasons"], candidate.gate_reasons)
        self.assertEqual(stage["original_residual_gate"], ORIGINAL_GATE)

    def test_child_binding_patch_does_not_recurse_and_result_stays_unverified(self):
        self.module.SE3Observation = self.observer
        result = self.observer(Candidate(.14, [ORIGINAL_GATE])).observe("scan")
        stage = self.observer._stage("proposal", result.candidates[0])
        self.assertEqual(stage["rmse_m"], .14)
        self.assertEqual(stage["gate_reasons"], [])
        self.assertEqual(result.status, "OBSERVATION_ONLY_UNVERIFIED")
        self.assertEqual(result.selection_policy, SELECTION_POLICY)
        self.assertFalse(result.selection_policy["original_selection_replayed"])
        self.assertFalse(result.selection_policy["rmse_selection_gate_enabled"])
        self.assertEqual(result.selection_policy["rmse_thresholds_purpose"], "COMPARISON_ONLY")

    def test_only_reviewed_source_receives_adapter(self):
        self.assertTrue(supports_pin(dict(REVIEWED_HASHES)))
        for filename in REVIEWED_HASHES:
            files = dict(REVIEWED_HASHES)
            files[filename] = "0" * 64
            self.assertFalse(supports_pin(files))
        self.assertFalse(supports_pin({}))
        self.assertFalse(supports_pin({**REVIEWED_HASHES, "extra.py": "0" * 64}))

    @staticmethod
    def ambiguous_result():
        matrix = [[1., 0., 0., 0.], [0., 1., 0., 0.],
                  [0., 0., 1., 0.], [0., 0., 0., 1.]]
        candidates = []
        for rmse in (.16, .14, .14):
            candidates.append(dict(map_from_scan=copy.deepcopy(matrix), rmse_m=rmse,
                overlap=.94, scan_count=16000, inlier_count=15000,
                distinct_inlier_voxel_count=100, full_scan_rmse_m=.22,
                capped_full_rmse_m=.17, geometry_min_max_eigen_ratio=.1,
                inlier_geometry_min_max_eigen_ratio=.08,
                refinement_stationary=True, gate_reasons=[AMBIGUITY_GATE]))
        return dict(candidates=candidates, selected_candidate=None,
                    gate_reasons=[AMBIGUITY_GATE], status="OBSERVATION_ONLY_UNVERIFIED")

    def test_explicit_ambiguity_opt_in_preserves_original_gates_and_chooses_lowest_rmse(self):
        original = self.ambiguous_result()
        disabled = apply_ambiguity_override(copy.deepcopy(original), allow_ambiguous=False)
        self.assertIsNone(disabled["selected_candidate"])
        self.assertEqual(disabled["ambiguity_override"], {"enabled": False, "applied": False})
        enabled = apply_ambiguity_override(copy.deepcopy(original), allow_ambiguous=True)
        self.assertEqual(enabled["selected_candidate"], 1)  # index resolves equal RMSE
        self.assertEqual(enabled["gate_reasons"], original["gate_reasons"])
        self.assertEqual([item["gate_reasons"] for item in enabled["candidates"]],
                         [item["gate_reasons"] for item in original["candidates"]])
        self.assertEqual([item["rmse_m"] for item in enabled["candidates"]], [.16, .14, .14])
        self.assertEqual(enabled["ambiguity_override"]["selection_rule"], AMBIGUITY_SELECTION_RULE)
        self.assertIsNone(enabled["ambiguity_override"]["original_selected_candidate"])
        self.assertEqual(enabled["ambiguity_override"]["original_gate_reasons"], [AMBIGUITY_GATE])
        self.assertEqual(enabled["estimate_label"], AMBIGUOUS_ESTIMATE_LABEL)
        self.assertTrue(valid_ambiguity_override(enabled, allowed=True))
        self.assertFalse(valid_ambiguity_override(enabled, allowed=False))

    def test_ambiguity_opt_in_never_bypasses_other_gates_or_accepts_forged_metadata(self):
        with_extra_top_gate = self.ambiguous_result()
        with_extra_top_gate["gate_reasons"].append("OVERLAP_BELOW_0.60")
        self.assertIsNone(apply_ambiguity_override(
            with_extra_top_gate, allow_ambiguous=True)["selected_candidate"])
        not_stationary = self.ambiguous_result()
        not_stationary["candidates"][1]["refinement_stationary"] = False
        self.assertEqual(apply_ambiguity_override(
            not_stationary, allow_ambiguous=True)["selected_candidate"], 2)
        other_candidate_gate = self.ambiguous_result()
        other_candidate_gate["candidates"][1]["gate_reasons"].append("INVALID_SE3")
        self.assertEqual(apply_ambiguity_override(
            other_candidate_gate, allow_ambiguous=True)["selected_candidate"], 2)
        no_eligible = self.ambiguous_result()
        for item in no_eligible["candidates"]:
            item["rmse_m"] = float("inf")
        no_eligible = apply_ambiguity_override(no_eligible, allow_ambiguous=True)
        self.assertIsNone(no_eligible["selected_candidate"])
        self.assertFalse(no_eligible["ambiguity_override"]["applied"])
        valid = apply_ambiguity_override(self.ambiguous_result(), allow_ambiguous=True)
        for mutation in (lambda value: value.update(selected_candidate=2),
                         lambda value: value["candidates"][1]["gate_reasons"].append("INVALID_SE3"),
                         lambda value: value["ambiguity_override"].update(original_gate_reasons=[]),
                         lambda value: value["ambiguity_override"].update(enabled=1),
                         lambda value: value["ambiguity_override"].update(applied=1),
                         lambda value: value.update(estimate_label="VERIFIED")):
            with self.subTest(mutation=mutation):
                altered = copy.deepcopy(valid)
                mutation(altered)
                self.assertFalse(valid_ambiguity_override(altered, allowed=True))
        huge_score = self.ambiguous_result()
        huge_score["candidates"][1]["rmse_m"] = 10 ** 10000
        self.assertEqual(apply_ambiguity_override(
            huge_score, allow_ambiguous=True)["selected_candidate"], 2)


if __name__ == "__main__":
    unittest.main()
