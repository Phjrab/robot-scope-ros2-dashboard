"""Pure synthetic checks of the seeded branches; no native registration runs."""
from __future__ import annotations

from dataclasses import dataclass, field
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

from robot_dashboard.relocalization import sensor_tracking_worker as subject
from robot_dashboard.relocalization import v031_observation_compat


@dataclass
class Candidate:
    map_from_scan: np.ndarray
    rmse_m: float = .14
    overlap: float = .94
    scan_count: int = 0
    inlier_count: int = 0
    full_scan_rmse_m: float = .21
    capped_full_rmse_m: float = .16
    distinct_inlier_voxel_count: int = 100
    geometry_min_max_eigen_ratio: float = .1
    inlier_geometry_min_max_eigen_ratio: float = .1
    refinement_stationary: bool | None = None
    gate_reasons: list[str] = field(default_factory=list)
    refinement_diagnostics: dict = field(default_factory=dict)
    refinement_stages: list = field(default_factory=list)
    selected_refinement_stage: str | None = None
    proposal_transform: np.ndarray | None = None
    phase_seconds: dict = field(default_factory=dict)


class FakeObserver:
    map_frame = "camera_init"
    scan_frame = "hesai_lidar"

    def __init__(self, stationary=(True, True, True)):
        self.stationary = stationary
        self.scored_lengths = []
        self.calls = []
        self.finished = None
        self._last_refinement_diagnostics = {}

    def _features(self, scan):
        self.calls.append(("features", len(scan)))
        return SimpleNamespace(points=scan[:100]), None

    def _refine(self, source, matrix):
        self.calls.append(("coarse", len(source.points)))
        result = matrix.copy(); result[0, 3] = .01
        self._last_refinement_diagnostics = {"branch": "coarse"}
        return result, self.stationary[0]

    def _refine_full(self, scan, matrix):
        self.calls.append(("robust", len(scan), float(matrix[0, 3])))
        result = matrix.copy(); result[0, 3] = .02
        self._last_refinement_diagnostics = {"branch": "robust"}
        return result, self.stationary[1]

    def _refine_plane(self, scan, matrix):
        self.calls.append(("plane", len(scan), float(matrix[0, 3])))
        result = matrix.copy(); result[0, 3] = .03
        self._last_refinement_diagnostics = {"branch": "plane"}
        return result, self.stationary[2]

    def _score(self, scan, matrix, attempt):
        self.scored_lengths.append(len(scan))
        return Candidate(matrix.copy(), scan_count=len(scan), inlier_count=int(.94 * len(scan)))

    def _stage(self, name, candidate):
        return {"stage": name, "gate_reasons": list(candidate.gate_reasons),
                "rmse_m": candidate.rmse_m}

    def _finish(self, candidates):
        self.finished = candidates
        acceptable = [index for index, item in enumerate(candidates) if not item.gate_reasons]
        if len(acceptable) > 1:
            for candidate in candidates:
                if not candidate.gate_reasons:
                    candidate.gate_reasons.append("AMBIGUOUS_ALTERNATIVES")
            return SimpleNamespace(candidates=candidates, selected_candidate=None,
                                   gate_reasons=["AMBIGUOUS_ALTERNATIVES"],
                                   map_frame=self.map_frame, scan_frame=self.scan_frame)
        return SimpleNamespace(candidates=candidates,
                               selected_candidate=acceptable[0] if acceptable else None,
                               gate_reasons=[] if acceptable else ["NO_ACCEPTABLE_CANDIDATE"],
                               map_frame=self.map_frame, scan_frame=self.scan_frame)


def json_observation(value):
    candidates = []
    for item in value.candidates:
        converted = vars(item).copy()
        converted["map_from_scan"] = item.map_from_scan.tolist()
        converted["proposal_transform"] = item.proposal_transform.tolist()
        candidates.append(converted)
    return dict(candidates=candidates, selected_candidate=value.selected_candidate,
                gate_reasons=value.gate_reasons, map_frame=value.map_frame,
                scan_frame=value.scan_frame)


class SensorTrackingWorkerTests(unittest.TestCase):
    def setUp(self):
        self.module_patch = mock.patch.dict(sys.modules, {"v031_observation_compat": v031_observation_compat})
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)
        self.coarse_patch = mock.patch.object(
            subject, "_coarse_source", side_effect=lambda observer, scan: observer._features(scan)[0])
        self.coarse_patch.start()
        self.addCleanup(self.coarse_patch.stop)
        self.scan = np.zeros((16_000, 3), dtype="<f8")
        self.seed = np.eye(4).tolist()
        self.context = dict(source_frame="hesai_lidar", observer_epoch="epoch",
                            observer_id="observer", source_stamp_ns="1000", map_revision="r1")
        self.metadata = dict(point_count=25_666, sha256="a" * 64)
        self.backend = SimpleNamespace(_rigid=lambda m: m.shape == (4, 4) and np.isfinite(m).all())
        self.isolated = SimpleNamespace(_json_observation=json_observation)

    def test_full_source_scoring_and_local_ambiguity_remain_observation_only(self):
        observer = FakeObserver()
        result = subject._align(observer, self.backend, self.isolated, self.scan, self.seed,
                                self.context, self.metadata, "b" * 64)
        self.assertEqual(observer.scored_lengths, [16_000] * 3)
        self.assertEqual(observer.calls[2], ("robust", 16_000, .01))
        self.assertEqual(observer.calls[3], ("plane", 16_000, 0.))
        self.assertEqual(len(observer.finished), 3)
        self.assertEqual(result["gate_reasons"], ["AMBIGUOUS_ALTERNATIVES"])
        self.assertIsNone(result["selected_candidate"])
        self.assertNotIn("map_from_scan", result)
        self.assertFalse(result["tracking_verified"])
        self.assertIsNone(result["body_pose"])
        self.assertEqual(result["local_scope"],
                         "ONE_SEED_THREE_REFINEMENT_BRANCHES_NOT_GLOBAL_AMBIGUITY_RECHECK")

    def test_explicit_local_ambiguity_opt_in_selects_only_observation_branch(self):
        observer = FakeObserver()
        result = subject._align(observer, self.backend, self.isolated, self.scan, self.seed,
                                self.context, self.metadata, "b" * 64, allow_ambiguous=True)
        self.assertEqual(result["selected_candidate"], 0)
        self.assertEqual(result["gate_reasons"], ["AMBIGUOUS_ALTERNATIVES"])
        self.assertEqual([candidate["gate_reasons"] for candidate in result["candidates"]],
                         [["AMBIGUOUS_ALTERNATIVES"]] * 3)
        self.assertTrue(result["ambiguity_override"]["applied"])
        self.assertEqual(result["estimate_label"], "AMBIGUOUS_UNVERIFIED_ESTIMATE")
        self.assertEqual(result["rmse_m"], .14)
        self.assertEqual(result["input_points"], 16_000)
        self.assertEqual(result["reference_points"], 25_666)
        self.assertFalse(result["tracking_verified"])
        self.assertIsNone(result["body_pose"])

    def test_nonstationary_branches_are_not_selected(self):
        observer = FakeObserver(stationary=(False, True, False))
        result = subject._align(observer, self.backend, self.isolated, self.scan, self.seed,
                                self.context, self.metadata, "b" * 64)
        self.assertIsNotNone(result["selected_candidate"])
        self.assertEqual(result["gate_reasons"], [])
        self.assertEqual(result["rmse_m"], .14)
        self.assertTrue(result["refinement_stationary"])
        self.assertEqual(sum("REFINEMENT_NOT_STATIONARY" in item.gate_reasons
                             for item in observer.finished), 2)
        self.assertEqual(result["input_points"], 16_000)
        self.assertEqual(result["reference_points"], 25_666)


class CoarseSourceTests(unittest.TestCase):
    def test_same_voxel_and_deterministic_fit_cap_without_fpfh(self):
        calls = []

        class Cloud:
            def __init__(self, points):
                self.points = np.asarray(points)

            def voxel_down_sample(self, voxel):
                calls.append(("voxel", voxel))
                return self

            def select_by_index(self, indices):
                calls.append(("indices", indices))
                return Cloud(self.points[indices])

        observer = SimpleNamespace(cfg=SimpleNamespace(voxel_m=.15, max_fit_points=60, seed=41),
                                   o3d=SimpleNamespace(geometry=SimpleNamespace(PointCloud=Cloud),
                                                       utility=SimpleNamespace(Vector3dVector=lambda value: value)))
        scan = np.arange(300, dtype=float).reshape(100, 3)
        result = subject._coarse_source(observer, scan)
        indices = sorted(np.random.default_rng(41).choice(100, 60, replace=False).tolist())
        self.assertEqual(calls, [("voxel", .15), ("indices", indices)])
        np.testing.assert_array_equal(result.points, scan[indices])


if __name__ == "__main__":
    unittest.main()
