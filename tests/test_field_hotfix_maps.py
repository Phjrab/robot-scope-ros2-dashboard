"""Same-source synthetic checks isolate display, height and density effects."""
import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np

from robot_dashboard.saved_maps import SavedMapCatalog, SavedMapFormatError, SavedMapConflict
from test_saved_maps import write_pcd


class FieldHotfixMapsTests(unittest.TestCase):
    def test_sparse_wall_low_obstacle_ceiling_and_height_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # Sparse boundary, low obstacle, a dense cluster, outer hall,
            # ceiling over the same XY and a rising ramp segment.
            wall = [(i * .5, 0., .2) for i in range(9)]
            low = [(2., 2., -.1)]
            cluster = [(3. + i * .001, 3., .2) for i in range(12)]
            hall = [(30., 30., .2)]
            ceiling = [(x, y, 3.) for x, y, _ in wall]
            ramp = [(i * .5, 4., i * .2) for i in range(7)]
            points = wall + low + cluster + hall + ceiling + ramp + [(float("nan"), 0, 0)]
            path = root / "hall.pcd"
            write_pcd(path, points)
            original = hashlib.sha256(path.read_bytes()).hexdigest()
            catalog = SavedMapCatalog([root], managed_roots=[root], preview_points=5)
            source = catalog.list_snapshot()["maps"][0]
            before = catalog.data(source["id"], max_points=5)
            self.assertLess(before["sent_points"], len(points))
            kwargs = dict(z_min=-.2, z_max=.8, resolution=.05, noise_radius=.1, expected_revision=source["revision"])
            dense = catalog.convert_pcd_to_2d(source["id"], "dense", min_neighbors=10, **kwargs)
            sparse = catalog.convert_pcd_to_2d(source["id"], "sparse", min_neighbors=1, **kwargs)
            d, s = dense["details"], sparse["details"]
            self.assertEqual(d["source_points"], len(points))
            self.assertEqual(s["finite_points"], len(points) - 1)
            self.assertEqual(d["z_slice_points"], s["z_slice_points"])
            self.assertEqual(s["selected_points"], s["z_slice_points"])
            self.assertEqual(d["selected_points"], len(cluster))
            self.assertGreater(s["occupied_cells"], d["occupied_cells"])
            grid = catalog.data(sparse["map"]["id"])
            cells = base64.b64decode(grid["data_b64"])
            self.assertEqual(set(cells), {255, 100})
            def cell(x, y):
                i = int(np.floor((x - grid["origin"][0]) / grid["resolution"]))
                j = int(np.floor((y - grid["origin"][1]) / grid["resolution"]))
                return cells[j * grid["width"] + i]
            self.assertEqual(cell(2, 0), 100)
            self.assertEqual(cell(2, 2), 100)
            self.assertEqual(cell(3, 4), 255)  # elevated ramp lies outside slab
            result = catalog.save_cropped_copy(
                sparse["map"]["id"], "arena", sparse["map"]["revision"],
                {"min_x": 0, "min_y": 0, "max_x": 101, "max_y": 101},
            )
            cropped = catalog.data(result["id"])
            self.assertEqual(set(base64.b64decode(cropped["data_b64"])), {255, 100})
            family = catalog.map_family(result["id"])["families"][0]
            self.assertEqual(family["source"]["pcd_revision"], source["revision"])
            self.assertEqual(family["derived_from_family_revision"], sparse["map"]["map_family"]["family_revision"])
            self.assertEqual(cropped["origin"], grid["origin"])
            self.assertEqual(cropped["resolution"], grid["resolution"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), original)
            reloaded = SavedMapCatalog([root], managed_roots=[root])
            self.assertEqual(reloaded.data(result["id"])["data_b64"], cropped["data_b64"])
            with self.assertRaises(SavedMapConflict):
                catalog.convert_pcd_to_2d(source["id"], "stale", min_neighbors=1, **{**kwargs, "expected_revision": "0" * 64})

    def test_empty_and_nonfinite_slice_fail_without_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_pcd(root / "empty.pcd", [(float("nan"), 0, 0), (1, 2, 3)])
            catalog = SavedMapCatalog([root], managed_roots=[root])
            source = catalog.list_snapshot()["maps"][0]
            with self.assertRaises(SavedMapFormatError):
                catalog.convert_pcd_to_2d(source["id"], "empty_2d", min_neighbors=1, z_min=-.2, z_max=.8, resolution=.05)
            self.assertFalse((root / "empty_2d.pgm").exists())
