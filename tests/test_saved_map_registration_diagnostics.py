"""Synthetic regression cases for offline density and rejection diagnostics."""

import unittest

import numpy as np

from robot_dashboard.offline_slam.core import Settings, inverse, pose, project, register
from robot_dashboard.offline_slam.registration_diagnostics import (
    inspect_saved_map,
    transfer_local_hypothesis,
    voxel_centroids,
)


class SavedMapDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.points = np.random.default_rng(723).uniform(-2, 2, (350, 3))
        self.truth = pose(np.array([0.035, -0.025, 0.02, 0.01, -0.01, 0.015]))
        self.source = project(self.points, inverse(self.truth))

    def test_many_to_one_is_not_misreported_as_low_overlap(self):
        repeated = np.repeat(self.points, 10, axis=0)
        candidate, metrics = register(repeated, self.points, np.eye(4), Settings())
        self.assertIsNone(candidate)
        self.assertEqual(metrics["overlap"], 1)
        self.assertEqual(metrics["reason"], "MANY_TO_ONE_CORRESPONDENCES")
        self.assertEqual(metrics["failures"], ["MANY_TO_ONE_CORRESPONDENCES"])
        self.assertAlmostEqual(metrics["unique_ratio"], 0.1)

    def test_multiple_gate_failures_are_preserved(self):
        rng = np.random.default_rng(52)
        source = np.repeat(self.points, 10, axis=0) + rng.normal(0, 0.04, (3500, 3))
        candidate, metrics = register(
            source, self.points, np.eye(4), Settings(max_rmse=0.005)
        )
        self.assertIsNone(candidate)
        self.assertIn("MANY_TO_ONE_CORRESPONDENCES", metrics["failures"])
        self.assertIn("HIGH_RESIDUAL", metrics["failures"])

    def test_density_balancing_recovers_pose_without_changing_thresholds(self):
        source = np.repeat(self.source, 10, axis=0)
        result = inspect_saved_map(source, self.points, np.eye(4))
        legacy, balanced = (
            result["fits"]["legacy_density"],
            result["fits"]["balanced_density"],
        )
        self.assertFalse(legacy["geometry_pass"])
        self.assertTrue(balanced["geometry_pass"], balanced)
        np.testing.assert_allclose(
            balanced["diagnostic_transform"], self.truth, atol=0.003
        )
        self.assertLess(balanced["original_population_after"]["capped_rmse_m"], 0.003)
        self.assertEqual(result["settings"]["max_rmse"], Settings().max_rmse)
        self.assertEqual(
            balanced["original_population_after"]["point_count"], len(source)
        )

    def test_exact_duplicate_multiplicity_does_not_change_balanced_fit(self):
        duplicated = np.vstack((self.source, np.repeat(self.source[:80], 30, axis=0)))
        a = inspect_saved_map(self.source, self.points, np.eye(4))
        b = inspect_saved_map(duplicated, self.points, np.eye(4))
        np.testing.assert_array_equal(
            voxel_centroids(self.source), voxel_centroids(duplicated)
        )
        np.testing.assert_array_equal(
            a["fits"]["balanced_density"]["diagnostic_transform"],
            b["fits"]["balanced_density"]["diagnostic_transform"],
        )

    def test_zero_rows_and_raw_population_are_visible_and_inputs_unchanged(self):
        source = np.vstack((self.source, np.zeros((40, 3))))
        original_source, original_target = source.copy(), self.points.copy()
        result = inspect_saved_map(source, self.points, np.eye(4))
        self.assertEqual(result["preprocessing"]["source_zero_rows"], 40)
        self.assertEqual(result["original_population_before"]["point_count"], 390)
        self.assertEqual(result["nonzero_population_before"]["point_count"], 350)
        for fit in result["fits"].values():
            self.assertEqual(fit["original_population_after"]["point_count"], 390)
        np.testing.assert_array_equal(source, original_source)
        np.testing.assert_array_equal(self.points, original_target)

    def test_passing_fit_does_not_clear_ambiguity_or_become_operational(self):
        result = inspect_saved_map(
            self.source,
            self.points,
            np.eye(4),
            ambiguity_reasons=["AMBIGUOUS_ALTERNATIVES"],
        )
        self.assertTrue(result["fits"]["balanced_density"]["geometry_pass"])
        self.assertEqual(result["ambiguity_reasons"], ["AMBIGUOUS_ALTERNATIVES"])
        self.assertEqual(result["state"], "DIAGNOSTIC_ONLY")
        self.assertFalse(result["global_location_verified"])
        self.assertFalse(result["body_pose_verified"])
        self.assertIsNone(result["absolute_accuracy_m"])
        self.assertEqual(result["operational_application"], "NOT_APPLIED")

    def test_wrong_seed_and_line_geometry_remain_rejected(self):
        seed = np.eye(4)
        seed[:3, 3] = 50
        result = inspect_saved_map(self.source, self.points, seed)
        self.assertFalse(result["fits"]["balanced_density"]["geometry_pass"])
        line = np.column_stack((np.linspace(1, 5, 100), np.zeros((100, 2))))
        result = inspect_saved_map(line, line, np.eye(4))
        self.assertEqual(
            result["fits"]["balanced_density"]["metrics"]["reason"],
            "DEGENERATE_GEOMETRY",
        )

    def test_relative_seed_composition_direction_and_uncertainty(self):
        map_from_reference = pose(np.array([2, -1, 0.3, 0.1, -0.2, 0.3]))
        result = transfer_local_hypothesis(self.points, self.source, map_from_reference)
        self.assertEqual(result["state"], "UNVERIFIED_LOCAL_HYPOTHESIS")
        np.testing.assert_allclose(
            result["map_from_source"], map_from_reference @ self.truth, atol=0.003
        )
        self.assertFalse(result["global_location_verified"])
        rejected = transfer_local_hypothesis(
            self.points, self.source + 50, map_from_reference
        )
        self.assertEqual(rejected["state"], "RELATIVE_FIT_REJECTED")
        self.assertIsNone(rejected["map_from_source"])

    def test_invalid_clouds_and_voxel_settings_are_rejected(self):
        for bad in (np.zeros((29, 3)), np.ones((35, 2)), np.full((40, 3), np.nan)):
            with self.assertRaises(ValueError):
                inspect_saved_map(bad, self.points, np.eye(4))
        for size in (0, float("nan"), 1):
            with self.assertRaises(ValueError):
                inspect_saved_map(self.source, self.points, np.eye(4), voxel_size=size)


if __name__ == "__main__":
    unittest.main()
