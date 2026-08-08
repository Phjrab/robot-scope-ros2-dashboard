import json
import struct
import tempfile
import unittest
from pathlib import Path

from robot_dashboard.saved_maps import SavedMapCatalog, SavedMapNotFound


def write_pcd(path: Path, points):
    header = (
        "# .PCD v0.7\n"
        "VERSION 0.7\n"
        "FIELDS x y z intensity\n"
        "SIZE 4 4 4 4\n"
        "TYPE F F F F\n"
        "COUNT 1 1 1 1\n"
        f"WIDTH {len(points)}\n"
        "HEIGHT 1\n"
        f"POINTS {len(points)}\n"
        "DATA binary\n"
    ).encode("ascii")
    payload = b"".join(struct.pack("<ffff", x, y, z, 1.0) for x, y, z in points)
    path.write_bytes(header + payload)


class SavedMapCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

        write_pcd(
            self.root / "room.pcd",
            [(float(index) / 10.0, float(index % 3), 0.25) for index in range(120)],
        )
        (self.root / "scene.json").write_text(
            json.dumps(
                {
                    "frame_id": "camera_init",
                    "source_points": 3,
                    "points": [0, 0, 0, 1, 2, 3, 2, 4, 6],
                }
            ),
            encoding="utf-8",
        )
        # PGM rows are: free/occupied then unknown/free. The API flips rows to
        # match ROS OccupancyGrid's bottom-left origin.
        (self.root / "floor.pgm").write_bytes(b"P5\n2 2\n255\n" + bytes([255, 0, 128, 255]))
        (self.root / "floor.yaml").write_text(
            "\n".join(
                [
                    "image: floor.pgm",
                    "resolution: 0.05",
                    "origin: [-1.0, -2.0, 0.0]",
                    "negate: 0",
                    "occupied_thresh: 0.65",
                    "free_thresh: 0.25",
                ]
            ),
            encoding="utf-8",
        )
        self.catalog = SavedMapCatalog([self.root], preview_points=100, cloud_radius_limit_m=100)

    def tearDown(self):
        self.temporary.cleanup()

    def test_lists_supported_maps_without_exposing_paths(self):
        snapshot = self.catalog.list_snapshot()
        self.assertTrue(snapshot["enabled"])
        self.assertEqual(snapshot["count"], 3)
        self.assertEqual(
            {item["kind"] for item in snapshot["maps"]},
            {"pointcloud3d", "occupancy2d"},
        )
        serialized = json.dumps(snapshot)
        self.assertNotIn(str(self.root), serialized)
        self.assertTrue(all(len(item["id"]) == 24 for item in snapshot["maps"]))

    def test_pcd_is_bounded_and_normalized_for_scene_renderer(self):
        record = next(item for item in self.catalog.list_snapshot()["maps"] if item["file_name"] == "room.pcd")
        payload = self.catalog.data(record["id"])
        self.assertEqual(payload["kind"], "pointcloud3d")
        self.assertEqual(payload["source_points"], 120)
        self.assertEqual(payload["sent_points"], 100)
        self.assertEqual(len(payload["points"]), 300)
        self.assertTrue(payload["offline_snapshot"])

    def test_map_server_pgm_becomes_occupancy_grid_payload(self):
        record = next(item for item in self.catalog.list_snapshot()["maps"] if item["kind"] == "occupancy2d")
        payload = self.catalog.data(record["id"])
        self.assertEqual((payload["width"], payload["height"]), (2, 2))
        self.assertEqual(payload["resolution"], 0.05)
        self.assertEqual(payload["origin"], [-1.0, -2.0, 0.0])
        decoded = __import__("base64").b64decode(payload["data_b64"])
        self.assertEqual(list(decoded), [255, 0, 0, 100])

    def test_unknown_and_traversal_like_ids_are_rejected(self):
        for map_id in ("../floor.yaml", "0" * 24, "/etc/passwd"):
            with self.assertRaises(SavedMapNotFound):
                self.catalog.data(map_id)

    def test_yaml_image_cannot_escape_configured_root(self):
        outside = self.root.parent / "outside-map.pgm"
        outside.write_bytes(b"P5\n1 1\n255\n\x00")
        try:
            (self.root / "escape.yaml").write_text(
                "image: ../outside-map.pgm\nresolution: 1\norigin: [0,0,0]\n",
                encoding="utf-8",
            )
            names = {item["file_name"] for item in self.catalog.list_snapshot()["maps"]}
            self.assertNotIn("escape.yaml", names)
        finally:
            outside.unlink(missing_ok=True)

    def test_profile_resolves_relative_roots_from_profile_directory(self):
        profile_dir = self.root / "config"
        data_dir = self.root / "data"
        profile_dir.mkdir()
        data_dir.mkdir()
        (data_dir / "map.json").write_text('{"points":[0,0,0]}', encoding="utf-8")
        catalog = SavedMapCatalog.from_profile(
            {"saved_maps": {"directories": ["../data"]}},
            base_dir=profile_dir,
        )
        self.assertEqual(catalog.list_snapshot()["count"], 1)


if __name__ == "__main__":
    unittest.main()
