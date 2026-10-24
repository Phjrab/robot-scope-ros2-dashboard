"""Known synthetic geometry; no private maps, ROS or device execution."""
import time
import unittest
from unittest.mock import patch

import numpy as np

from robot_dashboard.relocalization.experimental_se3 import (
    Cloud, from_translation_rpy, inverse, register_se3, rotation_error_rad, transform_points,
)
from robot_dashboard.relocalization.observation_alignment import (
    ObservationAlignmentError, ReferenceIndex, solve_prepared,
)
from robot_dashboard.relocalization.observation_policy import qualify_observation
from robot_dashboard.relocalization.observation_seed import voxel_centroids


def scene():
    rng = np.random.default_rng(981)
    floor = np.column_stack((rng.uniform(-3, 3, (1200, 2)), np.zeros(1200)))
    wall_x = np.column_stack((np.full(800, -3), rng.uniform(-3, 3, 800), rng.uniform(0, 2, 800)))
    wall_y = np.column_stack((rng.uniform(-3, 3, 800), np.full(800, 2), rng.uniform(0, 2, 800)))
    box = rng.uniform([.2, -.7, .2], [.8, .1, 1.3], (500, 3))
    return np.vstack((floor, wall_x, wall_y, box))


class LocalSeedTests(unittest.TestCase):
    def setUp(self):
        self.reference = scene()
        self.truth = from_translation_rpy([.2, -.1, .15], [.03, -.02, .08])
        self.query = transform_points(inverse(self.truth), self.reference[::8])
        self.grid = ReferenceIndex(self.reference)

    def solve(self, seed, query=None, grid=None):
        return solve_prepared(self.reference, grid or self.grid, 'map',
                              self.query if query is None else query, 'odom', 123, seed,
                              time.monotonic() + 5)

    def test_close_initialization_retains_original_solution_without_coarse_preparation(self):
        seed = from_translation_rpy([.01, -.01, .01], [.001, -.002, .003]) @ self.truth
        original = register_se3(Cloud(self.reference, 'map', 'REGISTERED_MAP'),
                               Cloud(self.query, 'odom', 'REGISTERED_QUERY', stamp_ns=123), seed,
                               nearest=lambda moved, _: self.grid.nearest(moved))
        with patch.object(self.grid, 'coarse_index', side_effect=AssertionError('unnecessary coarse work')):
            result, _ = self.solve(seed)
        self.assertEqual(result['pose'], original['pose'])
        for key in ('rmse_m', 'converged', 'overlap_ratio', 'iterations'):
            self.assertEqual(result['metrics'][key], original['metrics'][key])
        self.assertNotIn('seed_refinement', result)

    def test_rough_six_dof_seeds_recover_known_pose_and_score_every_original_query_point(self):
        original_reference, original_query = self.reference.copy(), self.query.copy()
        for xyz, rpy in [([.6, -.4, .3], [.1, -.1, .35]), ([-.5, .4, .2], [.03, .1, -.3])]:
            with self.subTest(xyz=xyz):
                seed = from_translation_rpy(xyz, rpy) @ self.truth
                result, transform = self.solve(seed)
                detail = result['seed_refinement']
                self.assertEqual(detail['qualification'], 'NUMERICAL_SEED_ONLY')
                self.assertLessEqual(detail['iterations'], 40)
                self.assertLess(detail['reference_points'], len(self.reference))
                self.assertLess(detail['query_points'], len(self.query))
                self.assertLess(np.linalg.norm(transform[:3, 3] - self.truth[:3, 3]), 1e-8)
                self.assertLess(rotation_error_rad(transform, self.truth), 1e-6)
                _, distances = self.grid.nearest(transform_points(transform, self.query))
                self.assertEqual(result['metrics']['inlier_count'], len(self.query))
                self.assertAlmostEqual(result['metrics']['rmse_m'], np.sqrt(distances.mean()), places=12)
                self.assertTrue(result['metrics']['converged'])
                self.assertLessEqual(result['metrics']['iterations'], 40)
        np.testing.assert_array_equal(self.reference, original_reference)
        np.testing.assert_array_equal(self.query, original_query)

    def test_derived_map_is_cached_but_each_scan_is_refined_and_scored_independently(self):
        seed = from_translation_rpy([.6, -.4, .3], [.1, -.1, .35]) @ self.truth
        self.solve(seed)
        cached = self.grid.coarse_cache
        query = transform_points(inverse(self.truth), self.reference[1::8])
        result, transform = self.solve(seed, query=query)
        self.assertIs(self.grid.coarse_cache, cached)
        self.assertEqual(result['metrics']['inlier_count'], len(query))
        self.assertLess(np.linalg.norm(transform[:3, 3] - self.truth[:3, 3]), 1e-8)
        self.assertEqual(result['query_stamp_ns'], 123)

    def test_far_seed_and_degenerate_geometry_are_not_promoted_by_coarse_initialization(self):
        result, _ = self.solve(from_translation_rpy([20, 20, 20], [0, 0, 0]))
        self.assertEqual(result['status'], 'REJECTED')
        self.assertNotIn('seed_refinement', result)
        plane = self.reference[:1200]
        query = plane[::4] + [.3, -.2, .3]
        result, _ = solve_prepared(plane, ReferenceIndex(plane), 'map', query, 'odom', 123,
                                   np.eye(4), time.monotonic() + 5)
        assessment = qualify_observation(result, inlier_count=result['metrics']['inlier_count'], query_count=len(query))
        self.assertEqual(assessment['status'], 'REJECTED')
        self.assertIn('DEGENERATE_GEOMETRY', assessment['gate_reasons'])

    def test_coarse_work_cannot_start_a_new_deadline(self):
        seed = from_translation_rpy([.6, -.4, .3], [.1, -.1, .35]) @ self.truth
        deadline = time.monotonic() + 5
        original_coarse = self.grid.coarse_index
        real_clock = time.monotonic
        clock = [None]

        def expire_after_map_preparation(**kwargs):
            result = original_coarse(**kwargs)
            clock[0] = deadline + 1
            return result

        with patch.object(self.grid, 'coarse_index', side_effect=expire_after_map_preparation), \
                patch('time.monotonic', side_effect=lambda: real_clock() if clock[0] is None else clock[0]):
            with self.assertRaisesRegex(ObservationAlignmentError, 'COMPUTE_BUDGET_EXCEEDED'):
                solve_prepared(self.reference, self.grid, 'map', self.query, 'odom', 123, seed, deadline)
        # The map may remain cached; no old scan result can be returned on retry.
        result, _ = self.solve(seed)
        self.assertTrue(result['metrics']['converged'])

    def test_centroids_preserve_negative_coordinates_and_do_not_modify_input(self):
        points = np.array([[-.3, -.2, -.1], [-.1, -.2, -.3], [.1, .2, .3], [.3, .2, .1]])
        original = points.copy()
        np.testing.assert_allclose(voxel_centroids(points), [[-.2, -.2, -.2], [.2, .2, .2]])
        np.testing.assert_array_equal(points, original)


if __name__ == '__main__':
    unittest.main()
