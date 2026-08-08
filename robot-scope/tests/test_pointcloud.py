import unittest
from types import SimpleNamespace

import numpy as np

from robot_dashboard.pointcloud import extract_xyz, reject_spatial_outliers


class PointCloudTests(unittest.TestCase):
    def test_extract_xyz_is_bounded_and_filters_nan(self):
        values = np.zeros(12, dtype={
            "names": ["x", "y", "z", "ring"],
            "formats": ["<f4", "<f4", "<f4", "<u2"],
            "offsets": [0, 4, 8, 12],
            "itemsize": 16,
        })
        values["x"] = np.arange(12)
        values["y"] = np.arange(12) + 10
        values["z"] = 1
        values["z"][6] = np.nan
        fields = [
            SimpleNamespace(name="x", offset=0, datatype=7),
            SimpleNamespace(name="y", offset=4, datatype=7),
            SimpleNamespace(name="z", offset=8, datatype=7),
            SimpleNamespace(name="ring", offset=12, datatype=4),
        ]
        message = SimpleNamespace(
            width=12, height=1, point_step=16, row_step=192,
            fields=fields, is_bigendian=False, data=values.tobytes(),
        )

        xyz, source_points = extract_xyz(message, max_points=4)

        self.assertEqual(source_points, 12)
        self.assertLessEqual(len(xyz), 4)
        self.assertTrue(np.isfinite(xyz).all())
        np.testing.assert_allclose(xyz[:, 0], [0, 3, 9])

    def test_extract_xyz_rejects_short_row_stride(self):
        fields = [
            SimpleNamespace(name="x", offset=0, datatype=7),
            SimpleNamespace(name="y", offset=4, datatype=7),
            SimpleNamespace(name="z", offset=8, datatype=7),
        ]
        message = SimpleNamespace(
            width=2, height=1, point_step=12, row_step=12,
            fields=fields, is_bigendian=False, data=bytes(24),
        )

        with self.assertRaisesRegex(ValueError, "row_step"):
            extract_xyz(message, max_points=2)

    def test_reject_spatial_outliers_removes_power_down_spike(self):
        room = np.column_stack((
            np.linspace(-25, 30, 200),
            np.linspace(-12, 24, 200),
            np.linspace(-3, 5, 200),
        )).astype(np.float32)
        points = np.vstack((room, [[-1_400_000, -650_000, 400_000]])).astype(np.float32)

        filtered = reject_spatial_outliers(points, max_radius=150)

        self.assertEqual(len(filtered), len(room))
        self.assertLess(float(np.max(np.abs(filtered))), 100)


if __name__ == "__main__":
    unittest.main()
