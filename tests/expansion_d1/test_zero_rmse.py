"""Candidate-stage injected numerical boundaries plus unmocked solver regressions."""

import unittest
from unittest.mock import patch
import numpy as np
from robot_dashboard.multimap_core import solver


class ZeroResidualTests(unittest.TestCase):
    def setUp(self):
        self.points = np.random.default_rng(710).normal(size=(100, 3))
        self.transforms = []
        for x in (0.3, 0.2, 0.1):
            t = np.eye(4)
            t[0, 3] = x
            self.transforms.append(t)

    def fine(self, residuals, transforms=None, overlap=None):
        transforms = transforms or self.transforms
        values = iter(residuals)

        def metric(a, b, t, resolution):
            return dict(
                overlap_source=overlap or 0.9,
                overlap_target=overlap or 0.9,
                rmse_m=next(values),
                inliers=100,
                geometry_ratio=0.2,
            )

        # Inject numerical measurement boundary, not replacement pair/solver.
        with patch.object(
            solver, "refine", side_effect=lambda a, b, t, r, c: t
        ), patch.object(solver, "metrics", side_effect=metric):
            return solver.pair(
                self.points, self.points, transforms, 0.05, lambda: False
            )

    def test_fine_zero_positive_missing(self):
        t, m, accepted, alternatives = self.fine([0.02, 0.0, None])
        self.assertEqual(m["rmse_m"], 0.0)
        np.testing.assert_array_equal(t, self.transforms[1])
        self.assertFalse(accepted)  # valid competing hypothesis stays ambiguous
        self.assertEqual(len(alternatives), 1)

    def test_fine_invalid_residual_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf"), -0.01):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError, "residual"
            ):
                self.fine([0.0, 0.02, value])

    def test_fine_missing_all_and_missing_high_overlap(self):
        self.assertFalse(self.fine([None, None, None])[2])
        values = iter(
            [
                dict(
                    overlap_source=1.0,
                    overlap_target=1.0,
                    rmse_m=None,
                    inliers=100,
                    geometry_ratio=0.2,
                ),
                dict(
                    overlap_source=0.9,
                    overlap_target=0.9,
                    rmse_m=0.0,
                    inliers=100,
                    geometry_ratio=0.2,
                ),
            ]
        )
        with patch.object(
            solver, "refine", side_effect=lambda a, b, t, r, c: t
        ), patch.object(solver, "metrics", side_effect=lambda *args: next(values)):
            _, m, accepted, _ = solver.pair(
                self.points, self.points, self.transforms[:2], 0.05, lambda: False
            )
        self.assertEqual(m["overlap_source"], 1.0)  # overlap priority unchanged
        self.assertFalse(accepted)

    def test_fine_ties_independent_of_candidate_order(self):
        a = self.fine([0.0, 0.0, 0.0])[0]
        b = self.fine([0.0, 0.0, 0.0], list(reversed(self.transforms)))[0]
        np.testing.assert_array_equal(a, b)

    def coarse(self, values, transforms=None):
        generated = transforms or self.transforms
        count = 0

        def fit(*args):
            nonlocal count
            result = generated[count % len(generated)]
            count += 1
            return result

        values = iter(values)
        with patch.object(solver, "_rigid_fit", side_effect=fit), patch.object(
            solver.np, "quantile", side_effect=lambda *args: next(values)
        ):
            return solver.coarse(self.points, self.points)

    def test_coarse_zero_positive_missing_and_ties(self):
        # Last six outputs are actual coarse shortlisting, not PCA supplements.
        out = self.coarse([0.02, 0.0, None] + [0.5] * 125)
        np.testing.assert_array_equal(out[-6], self.transforms[1])
        np.testing.assert_array_equal(out[-5], self.transforms[0])
        a = self.coarse([0.0] * 128)
        b = self.coarse([0.0] * 128, list(reversed(self.transforms)))
        np.testing.assert_array_equal(a[-6:], b[-6:])

    def test_coarse_invalid_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf"), -0.01):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError, "residual"
            ):
                self.coarse([value] + [0.02] * 127)

    def test_unmocked_identity_fine_and_automatic(self):
        for seeds in ([np.eye(4)], []):
            t, m, accepted, alternatives = solver.pair(
                self.points, self.points, seeds, 0.05, lambda: False
            )
            self.assertTrue(accepted)
            self.assertEqual(alternatives, [])
            self.assertLess(m["rmse_m"], 1e-12)
            np.testing.assert_allclose(t, np.eye(4), atol=1e-12)


if __name__ == "__main__":
    unittest.main()
