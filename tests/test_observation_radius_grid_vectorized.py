"""Exact radius-search checks without ROS, hardware, or wall-clock limits."""
import itertools
import unittest
from unittest.mock import patch

import numpy as np

from robot_dashboard.relocalization.experimental_se3 import MAX_CORRESPONDENCE_M
from robot_dashboard.relocalization.observation_alignment import ObservationAlignmentError, RadiusGrid


def direct_nearest(reference, query):
    """Use direct differences, avoiding cancellation from squared-norm matmul."""
    ids = np.zeros(len(query), dtype=np.int64)
    distances = np.full(len(query), np.inf)
    for i, point in enumerate(query):
        diff = reference - point
        squared = np.einsum("ij,ij->i", diff, diff)
        winner = int(np.argmin(squared))
        if squared[winner] <= MAX_CORRESPONDENCE_M ** 2:
            ids[i], distances[i] = winner, squared[winner]
    return ids, distances


class RadiusGridVectorizedTests(unittest.TestCase):
    def assert_exact(self, reference, query, grid=None):
        actual = (grid or RadiusGrid(reference)).nearest(query)
        expected = direct_nearest(reference, query)
        np.testing.assert_array_equal(actual[0], expected[0])
        np.testing.assert_array_equal(actual[1], expected[1])
        return actual

    def test_dense_random_same_and_different_cells_match_direct_search(self):
        rng = np.random.default_rng(712)
        reference = rng.uniform(-.74, .74, (8205, 3))
        same_cell = rng.uniform(.02, .72, (37, 3))
        other_cells = rng.uniform(-2, 2, (39, 3))
        query = np.vstack((other_cells[:17], same_cell, other_cells[17:]))
        self.assert_exact(reference, query)

    def test_dense_ties_across_candidate_chunks_and_bounded_query_chunks(self):
        reference = np.full((8205, 3), .65)
        # The lower original index is in a later spatial bucket. Both ties
        # survive candidate sorting and fall into different 4096-index chunks.
        reference[17] = [.125, 0, 0]
        reference[5003] = [-.125, 0, 0]
        query = np.zeros((35, 3))
        grid = RadiusGrid(reference)
        expected = direct_nearest(reference, query)
        einsum, shapes = np.einsum, []

        def recorded(subscripts, diff, other):
            shapes.append(diff.shape)
            return einsum(subscripts, diff, other)

        with patch("robot_dashboard.relocalization.observation_alignment.np.einsum", side_effect=recorded):
            actual = grid.nearest(query)
        np.testing.assert_array_equal(actual[0], expected[0])
        np.testing.assert_array_equal(actual[1], expected[1])
        self.assertTrue((actual[0] == 17).all())
        self.assertTrue(shapes)
        self.assertTrue(all(len(shape) == 3 and shape[0] <= 16 and shape[1] <= 4096
                            and shape[2] == 3 for shape in shapes))
        self.assertTrue(any(shape[:2] == (16, 4096) for shape in shapes))
        self.assertTrue(any(shape[0] == 3 for shape in shapes))

    def test_radius_boundary_and_missing_candidates_remain_exact(self):
        radius = MAX_CORRESPONDENCE_M
        reference = np.array([[radius, 0, 0], [np.nextafter(radius, np.inf), 10, 0],
                              [np.nextafter(radius, 0), 20, 0]])
        query = np.array([[0., 0, 0], [0, 10, 0], [0, 20, 0], [0, 100, 0]])
        ids, distances = self.assert_exact(reference, query)
        np.testing.assert_array_equal(ids, [0, 0, 2, 0])
        self.assertEqual(distances[0], radius ** 2)
        self.assertLess(distances[2], radius ** 2)
        self.assertTrue(np.isinf(distances[[1, 3]]).all())

    def test_cache_index_limit_keeps_uncached_search_exact(self):
        # Each of four separated buckets contributes 5000 candidates to each
        # of its 27 neighbouring query cells: the 101st admission exceeds 4 MB.
        origins = np.array([[x, 0, 0] for x in (0, 10, 20, 30)])
        reference = np.repeat((origins + .5) * MAX_CORRESPONDENCE_M, 5000, axis=0)
        offsets = np.array(list(itertools.product((-1, 0, 1), repeat=3)))
        query = np.vstack([(origin + offsets + .5) * MAX_CORRESPONDENCE_M for origin in origins])
        grid = RadiusGrid(reference)
        self.assert_exact(reference, query, grid)
        self.assertEqual(grid.cached_indices, 500_000)
        self.assertEqual(len(grid.neighbour_cache), 100)
        self.assertEqual(sum(len(indices) for indices in grid.neighbour_cache.values()), grid.cached_indices)
        # The exact-radius final-group hit is after the cache became full.
        uncached = (origins[-1] + [1.5, .5, .5]) * MAX_CORRESPONDENCE_M
        key = tuple(np.floor(uncached / MAX_CORRESPONDENCE_M).astype(np.int64))
        self.assertNotIn(key, grid.neighbour_cache)
        ids, distances = self.assert_exact(reference, uncached[None, :], grid)
        self.assertEqual(ids[0], 15_000)
        self.assertEqual(distances[0], MAX_CORRESPONDENCE_M ** 2)
        self.assertEqual(grid.cached_indices, 500_000)

    def test_cache_cell_limit_includes_empty_cells(self):
        reference = np.zeros((1, 3))
        query = np.zeros((2051, 3))
        query[:, 0] = (np.arange(len(query)) * 3 + 10) * MAX_CORRESPONDENCE_M
        grid = RadiusGrid(reference)
        ids, distances = grid.nearest(query)
        self.assertTrue((ids == 0).all())
        self.assertTrue(np.isinf(distances).all())
        self.assertEqual(len(grid.neighbour_cache), 2048)
        self.assertEqual(grid.cached_indices, 0)
        self.assertTrue(all(len(indices) == 0 for indices in grid.neighbour_cache.values()))

    def test_deadline_is_checked_between_dense_candidate_chunks(self):
        grid = RadiusGrid(np.full((8205, 3), .1))
        clock, calls, einsum = [0.], [], np.einsum

        def expire_after_chunk(subscripts, diff, other):
            calls.append(diff.shape)
            result = einsum(subscripts, diff, other)
            clock[0] = 2.
            return result

        with patch("robot_dashboard.relocalization.observation_alignment.time.monotonic", side_effect=lambda: clock[0]), \
                patch("robot_dashboard.relocalization.observation_alignment.np.einsum", side_effect=expire_after_chunk):
            with self.assertRaisesRegex(ObservationAlignmentError, "^COMPUTE_BUDGET_EXCEEDED$"):
                grid.nearest(np.zeros((1, 3)), deadline=1.)
        self.assertEqual(calls, [(1, 4096, 3)])


if __name__ == "__main__":
    unittest.main()


class ReferenceIndexTests(unittest.TestCase):
    def test_exact_index_matches_direct_search_at_boundaries_and_ties(self):
        from robot_dashboard.relocalization.observation_alignment import ReferenceIndex
        rng = np.random.default_rng(19)
        reference = np.vstack((rng.uniform(-3, 3, (5000, 3)), [[10.75, 0, 0], [20.125, 0, 0], [19.875, 0, 0], [40.45, .6, 0], [50.7500000000001, 0, 0]]))
        query = np.vstack((rng.uniform(-4, 4, (140, 3)), [[10, 0, 0], [20, 0, 0], [30, 0, 0], [40, 0, 0], [50, 0, 0]]))
        actual = ReferenceIndex(reference).nearest(query)
        expected = direct_nearest(reference, query)
        np.testing.assert_array_equal(actual[0], expected[0])
        np.testing.assert_allclose(actual[1], expected[1], atol=1e-15, rtol=1e-15)

    def test_exact_index_preserves_deadline(self):
        import time
        from robot_dashboard.relocalization.observation_alignment import ReferenceIndex
        points = np.zeros((1000, 3))
        with self.assertRaisesRegex(ObservationAlignmentError, 'COMPUTE_BUDGET_EXCEEDED'):
            ReferenceIndex(points, deadline=time.monotonic() - 1)
        index = ReferenceIndex(points)
        with self.assertRaisesRegex(ObservationAlignmentError, 'COMPUTE_BUDGET_EXCEEDED'):
            index.nearest(points[:200], deadline=time.monotonic() - 1)
