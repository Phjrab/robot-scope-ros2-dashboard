# ruff: noqa: E402
"""Coverage correction must not turn the circumscribed circle into a hard body."""

import copy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configure import candidate
from core import polygon
from d0_adapter import load_fixture, input_path
from footprint_coverage import (
    PublishedGrid,
    coverage,
    inflation_cost,
    interpolated_poses,
    path_footprints,
)
from observations import grid_payload


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = load_fixture(input_path("feasible1"))
        self.body = self.fixture["effective_footprint"]

    def grid(self, floor=0):
        # Synthetic closed 1m-wide corridor. Not a native execution or D0 prior.
        return PublishedGrid(
            dict(
                width=50,
                height=100,
                resolution=0.02,
                origin=[0, 0],
                data_zlib_base64=grid_payload(
                    [
                        100 if x in (0, 49) or y <= floor or y == 99 else 0
                        for y in range(100)
                        for x in range(50)
                    ]
                ),
            )
        )

    def test_only_two_inflation_radii_change(self):
        old = candidate("mppi", "omni_lattice", self.fixture)
        new = candidate("mppi", "omni_coverage", self.fixture)
        for name in ("global_costmap", "local_costmap"):
            cm = new[name][name]["ros__parameters"]
            self.assertEqual(cm["inflation_layer"]["inflation_radius"], 0.58)
            cm["inflation_layer"]["inflation_radius"] = 0.4
        self.assertEqual(new, old)
        with self.assertRaises(ValueError):
            candidate("rpp", "omni_coverage", self.fixture)
        with self.assertRaises(ValueError):
            candidate("mppi", "omni_coverage")

    def test_support_is_derived_and_grid_rounded(self):
        c = coverage(self.body, 0.02)
        self.assertAlmostEqual(c["circumscribed_radius_m"], 0.5341582162618114)
        self.assertAlmostEqual(c["inscribed_radius_m"], 0.31)
        self.assertEqual(c["inflation_radius_m"], 0.58)
        self.assertLess(0.56, c["required_support_m"])
        self.assertGreaterEqual(0.58, c["required_support_m"])
        self.assertEqual(
            inflation_cost(c["circumscribed_radius_m"], c["inscribed_radius_m"]), 82
        )
        larger = copy.deepcopy(self.body)
        larger = [(x * 2, y * 2) for x, y in larger]
        self.assertGreater(coverage(larger, 0.02)["inflation_radius_m"], 0.58)

    def test_overlay_has_identical_b1_navigation_parameters(self):
        self.assertEqual(
            candidate("mppi", "omni_checked_overlay", self.fixture),
            candidate("mppi", "omni_coverage", self.fixture),
        )

    def test_saved_unsafe_corner_now_reaches_full_footprint_branch(self):
        grid = self.grid(floor=24)
        pose = (0.5099999886006117, 0.9499999787658453, 1.4162471294403076)
        self.assertEqual(grid.center_cost(pose, 0.4, 0.31)["raw_cost"], 0)
        self.assertGreaterEqual(grid.center_cost(pose, 0.58, 0.31)["raw_cost"], 82)
        self.assertEqual(grid.overlaps(polygon(pose, self.body)), "lethal_or_unknown")

    def test_positive_cost_does_not_make_normal_corridor_impassable(self):
        grid = self.grid()
        pose = (0.5, 1.0, math.pi / 2)
        cost = grid.center_cost(pose, 0.58, 0.31)["raw_cost"]
        self.assertGreaterEqual(cost, 82)
        self.assertLess(cost, 253)
        self.assertIsNone(grid.overlaps(polygon(pose, self.body)))
        # Circumradius exceeds half corridor width; it is not the collision body.
        self.assertGreater(coverage(self.body, 0.02)["circumscribed_radius_m"], 0.5)

    def test_interval_rotation_detects_collision_between_free_endpoints(self):
        grid = self.grid()
        a, b = (0.5, 1.0, math.pi / 2), (0.5, 1.0, -math.pi / 2)
        self.assertIsNone(grid.overlaps(polygon(a, self.body)))
        self.assertIsNone(grid.overlaps(polygon(b, self.body)))
        poses = list(
            interpolated_poses(
                a, b, coverage(self.body, 0.02)["circumscribed_radius_m"]
            )
        )
        self.assertTrue(any(grid.overlaps(polygon(p, self.body)) for p in poses))
        self.assertLessEqual(
            max(
                math.dist(p[:2], q[:2]) + 0.5341582163 * abs(p[2] - q[2])
                for p, q in zip(poses, poses[1:])
            ),
            0.0020001,
        )

    def test_path_review_uses_orientation_intervals_and_requires_z(self):
        grid = self.grid().row
        grid.update(kind="costmap", source_sim_s=1.0, receipt_monotonic=100.0)
        path = dict(
            kind="path",
            frame="map",
            source_sim_s=1.1,
            source_elapsed_s=0.0,
            receipt_monotonic=100.1,
            points=[[0.5, 1.0], [0.5, 1.0]],
            z=[0, 0],
            quaternions=[[0, 0, math.sin(math.pi / 4), math.cos(math.pi / 4)]] * 2,
        )
        self.assertEqual(path_footprints(self.fixture, [grid, path])["status"], "PASS")
        # Same source time does not authorize a map received after the path.
        later = copy.deepcopy(grid)
        later.update(
            source_sim_s=1.1,
            receipt_monotonic=100.2,
            data_zlib_base64=grid_payload([100] * (50 * 100)),
        )
        self.assertEqual(
            path_footprints(self.fixture, [grid, later, path])["status"], "PASS"
        )
        with self.assertRaisesRegex(ValueError, "preceding global map"):
            path_footprints(self.fixture, [later, path])
        path["quaternions"] = [
            path["quaternions"][0],
            [0, 0, -math.sin(math.pi / 4), math.cos(math.pi / 4)],
        ]
        reviewed = path_footprints(self.fixture, [grid, path])
        self.assertEqual(reviewed["status"], "FAIL")
        self.assertIsNotNone(reviewed["paths"][0]["first_grid_collision"])
        path.pop("z")
        with self.assertRaisesRegex(ValueError, "path Z"):
            path_footprints(self.fixture, [grid, path])
