import json
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from robot_dashboard.saved_maps import (
    SavedMapCatalog,
    SavedMapConflict,
    SavedMapInvalidName,
    SavedMapMutationError,
    SavedMapNotFound,
    SavedMapPointLimitError,
    SavedMapReadOnly,
)


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
        self.managed_catalog = SavedMapCatalog(
            [self.root],
            managed_roots=[self.root],
            preview_points=100,
            cloud_radius_limit_m=100,
        )

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

    def test_pcd_custom_limit_is_normalized_for_scene_renderer(self):
        record = next(item for item in self.catalog.list_snapshot()["maps"] if item["file_name"] == "room.pcd")
        payload = self.catalog.data(record["id"], max_points=100)
        self.assertEqual(payload["kind"], "pointcloud3d")
        self.assertEqual(payload["source_points"], 120)
        self.assertEqual(payload["sent_points"], 100)
        self.assertEqual(len(payload["points"]), 300)
        self.assertTrue(payload["offline_snapshot"])

    def test_pcd_none_returns_every_finite_in_radius_point(self):
        write_pcd(
            self.root / "filtered.pcd",
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (float("nan"), 0.0, 0.0),
                (1_000.0, 0.0, 0.0),
                (2.0, 0.0, 0.0),
            ],
        )
        record = next(
            item
            for item in self.catalog.list_snapshot()["maps"]
            if item["file_name"] == "filtered.pcd"
        )

        payload = self.catalog.data(record["id"], max_points=None)

        self.assertEqual(payload["source_points"], 5)
        self.assertEqual(payload["sent_points"], 3)
        self.assertEqual(payload["points"], [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 2.0, 0.0, 0.0])

    def test_custom_point_limit_and_json_all_are_truthful(self):
        records = self.catalog.list_snapshot()["maps"]
        room = next(item for item in records if item["file_name"] == "room.pcd")
        scene = next(item for item in records if item["file_name"] == "scene.json")

        limited = self.catalog.data(room["id"], max_points=37)
        complete = self.catalog.data(room["id"], max_points=None)
        json_complete = self.catalog.data(scene["id"], max_points=None)

        self.assertEqual((limited["source_points"], limited["sent_points"]), (120, 37))
        self.assertEqual((complete["source_points"], complete["sent_points"]), (120, 120))
        self.assertEqual((json_complete["source_points"], json_complete["sent_points"]), (3, 3))
        self.assertEqual(len(complete["points"]), 360)

    def test_invalid_custom_limits_and_full_view_safety_are_rejected(self):
        room = next(
            item
            for item in self.catalog.list_snapshot()["maps"]
            if item["file_name"] == "room.pcd"
        )
        for invalid in (0, -1, True, 1.5, "100", 1_000_001):
            with self.assertRaises(SavedMapPointLimitError):
                self.catalog.data(room["id"], max_points=invalid)

        guarded = SavedMapCatalog(
            [self.root],
            max_requested_points=100,
            max_full_view_points=100,
            cloud_radius_limit_m=100,
        )
        guarded_room = next(
            item
            for item in guarded.list_snapshot()["maps"]
            if item["file_name"] == "room.pcd"
        )
        with self.assertRaises(SavedMapPointLimitError):
            guarded.data(guarded_room["id"], max_points=None)
        self.assertEqual(
            guarded.data(guarded_room["id"], max_points=50)["sent_points"],
            50,
        )

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

    def test_only_explicit_managed_roots_are_mutable(self):
        read_only = self.catalog.list_snapshot()["maps"]
        managed = self.managed_catalog.list_snapshot()["maps"]
        self.assertTrue(all(item["manageable"] is False for item in read_only))
        self.assertTrue(all(item["manageable"] is True for item in managed))

        room = next(item for item in read_only if item["file_name"] == "room.pcd")
        with self.assertRaises(SavedMapReadOnly):
            self.catalog.rename(room["id"], "forbidden")
        with self.assertRaises(SavedMapReadOnly):
            self.catalog.delete(room["id"])
        self.assertTrue((self.root / "room.pcd").is_file())

    def test_renames_single_file_map_and_returns_new_opaque_id(self):
        room = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["file_name"] == "room.pcd"
        )
        renamed = self.managed_catalog.rename(room["id"], "lecture_room")

        self.assertFalse((self.root / "room.pcd").exists())
        self.assertTrue((self.root / "lecture_room.pcd").is_file())
        self.assertEqual(renamed["name"], "lecture_room")
        self.assertEqual(renamed["file_name"], "lecture_room.pcd")
        self.assertNotEqual(renamed["id"], room["id"])
        self.assertTrue(renamed["manageable"])
        self.assertNotIn(str(self.root), json.dumps(renamed))
        with self.assertRaises(SavedMapNotFound):
            self.managed_catalog.metadata(room["id"])
        self.assertEqual(self.managed_catalog.data(renamed["id"])["source_points"], 120)
        self.assertFalse((self.root / ".robot_scope_transactions").exists())

    def test_renames_yaml_and_pgm_as_one_valid_pair(self):
        floor = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["kind"] == "occupancy2d"
        )
        renamed = self.managed_catalog.rename(floor["id"], "west_floor")

        self.assertFalse((self.root / "floor.yaml").exists())
        self.assertFalse((self.root / "floor.pgm").exists())
        self.assertTrue((self.root / "west_floor.yaml").is_file())
        self.assertTrue((self.root / "west_floor.pgm").is_file())
        self.assertIn(
            "image: west_floor.pgm",
            (self.root / "west_floor.yaml").read_text(encoding="utf-8"),
        )
        self.assertEqual(renamed["image_file_name"], "west_floor.pgm")
        payload = self.managed_catalog.data(renamed["id"])
        self.assertEqual((payload["width"], payload["height"]), (2, 2))
        self.assertFalse((self.root / ".robot_scope_transactions").exists())

    def test_delete_single_file_and_paired_map(self):
        records = self.managed_catalog.list_snapshot()["maps"]
        room = next(item for item in records if item["file_name"] == "room.pcd")
        floor = next(item for item in records if item["kind"] == "occupancy2d")

        deleted_room = self.managed_catalog.delete(room["id"])
        self.assertEqual(deleted_room["files"], ["room.pcd"])
        self.assertFalse((self.root / "room.pcd").exists())
        with self.assertRaises(SavedMapNotFound):
            self.managed_catalog.metadata(room["id"])

        deleted_floor = self.managed_catalog.delete(floor["id"])
        self.assertEqual(deleted_floor["files"], ["floor.yaml", "floor.pgm"])
        self.assertNotIn(str(self.root), json.dumps(deleted_floor))
        self.assertFalse((self.root / "floor.yaml").exists())
        self.assertFalse((self.root / "floor.pgm").exists())
        self.assertFalse((self.root / ".robot_scope_transactions").exists())

    def test_invalid_names_and_existing_targets_do_not_change_sources(self):
        room = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["file_name"] == "room.pcd"
        )
        for invalid in (
            "",
            ".hidden",
            "../escape",
            "has space",
            "한글",
            "a" * 65,
            "/absolute",
        ):
            with self.assertRaises(SavedMapInvalidName):
                self.managed_catalog.rename(room["id"], invalid)

        occupied = self.root / "occupied.pcd"
        occupied.write_bytes(b"do-not-replace")
        with self.assertRaises(SavedMapConflict):
            self.managed_catalog.rename(room["id"], "occupied")
        self.assertTrue((self.root / "room.pcd").is_file())
        self.assertEqual(occupied.read_bytes(), b"do-not-replace")

    def test_pair_target_collision_rolls_back_without_half_rename(self):
        floor = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["kind"] == "occupancy2d"
        )
        occupied_image = self.root / "occupied.pgm"
        occupied_image.write_bytes(b"do-not-replace")

        with self.assertRaises(SavedMapConflict):
            self.managed_catalog.rename(floor["id"], "occupied")

        self.assertTrue((self.root / "floor.yaml").is_file())
        self.assertTrue((self.root / "floor.pgm").is_file())
        self.assertFalse((self.root / "occupied.yaml").exists())
        self.assertEqual(occupied_image.read_bytes(), b"do-not-replace")

    def test_target_symlink_is_a_conflict_and_is_never_followed(self):
        room = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["file_name"] == "room.pcd"
        )
        outside = self.root.parent / "outside-target.pcd"
        outside.write_bytes(b"outside-must-not-change")
        try:
            (self.root / "linked_target.pcd").symlink_to(outside)
            with self.assertRaises(SavedMapConflict):
                self.managed_catalog.rename(room["id"], "linked_target")
            self.assertEqual(outside.read_bytes(), b"outside-must-not-change")
            self.assertTrue((self.root / "room.pcd").is_file())
        finally:
            outside.unlink(missing_ok=True)

    def test_auxiliary_symlink_is_not_catalogued_or_manageable(self):
        (self.root / "linked.yaml").write_text(
            "image: linked.pgm\nresolution: 0.05\norigin: [0, 0, 0]\n",
            encoding="utf-8",
        )
        (self.root / "linked.pgm").symlink_to(self.root / "floor.pgm")
        names = {
            item["file_name"]
            for item in self.managed_catalog.list_snapshot()["maps"]
        }
        self.assertNotIn("linked.yaml", names)

    def test_mid_pair_unlink_failure_restores_originals_and_removes_targets(self):
        floor = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["kind"] == "occupancy2d"
        )
        original_unlink = self.managed_catalog._unlink_verified
        calls = 0

        def fail_second_unlink(path, identity):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected unlink failure")
            return original_unlink(path, identity)

        with patch.object(
            self.managed_catalog,
            "_unlink_verified",
            side_effect=fail_second_unlink,
        ):
            with self.assertRaises(SavedMapMutationError):
                self.managed_catalog.rename(floor["id"], "rollback_floor")

        self.assertTrue((self.root / "floor.yaml").is_file())
        self.assertTrue((self.root / "floor.pgm").is_file())
        self.assertFalse((self.root / "rollback_floor.yaml").exists())
        self.assertFalse((self.root / "rollback_floor.pgm").exists())
        self.assertEqual(
            self.managed_catalog.data(floor["id"])["kind"],
            "occupancy2d",
        )
        self.assertFalse((self.root / ".robot_scope_transactions").exists())

    def test_mid_pair_publish_failure_removes_first_target(self):
        floor = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["kind"] == "occupancy2d"
        )
        original_publish = self.managed_catalog._publish_link
        calls = 0

        def fail_second_publish(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise SavedMapConflict("injected target race")
            return original_publish(source, target)

        with patch.object(
            self.managed_catalog,
            "_publish_link",
            side_effect=fail_second_publish,
        ):
            with self.assertRaises(SavedMapConflict):
                self.managed_catalog.rename(floor["id"], "publish_race")

        self.assertTrue((self.root / "floor.yaml").is_file())
        self.assertTrue((self.root / "floor.pgm").is_file())
        self.assertFalse((self.root / "publish_race.yaml").exists())
        self.assertFalse((self.root / "publish_race.pgm").exists())
        self.assertFalse((self.root / ".robot_scope_transactions").exists())

    def test_mid_pair_delete_failure_restores_both_files(self):
        floor = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["kind"] == "occupancy2d"
        )
        original_unlink = self.managed_catalog._unlink_verified
        calls = 0

        def fail_second_unlink(path, identity):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected unlink failure")
            return original_unlink(path, identity)

        with patch.object(
            self.managed_catalog,
            "_unlink_verified",
            side_effect=fail_second_unlink,
        ):
            with self.assertRaises(SavedMapMutationError):
                self.managed_catalog.delete(floor["id"])

        self.assertTrue((self.root / "floor.yaml").is_file())
        self.assertTrue((self.root / "floor.pgm").is_file())
        self.assertEqual(
            self.managed_catalog.data(floor["id"])["kind"],
            "occupancy2d",
        )
        self.assertFalse((self.root / ".robot_scope_transactions").exists())

    def test_shared_pgm_is_preserved_for_other_yaml_on_delete(self):
        (self.root / "floor_copy.yaml").write_text(
            (self.root / "floor.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        records = self.managed_catalog.list_snapshot()["maps"]
        floor = next(item for item in records if item["file_name"] == "floor.yaml")
        floor_copy = next(
            item for item in records if item["file_name"] == "floor_copy.yaml"
        )

        deleted = self.managed_catalog.delete(floor["id"])
        self.assertEqual(deleted["files"], ["floor.yaml"])
        self.assertFalse((self.root / "floor.yaml").exists())
        self.assertTrue((self.root / "floor.pgm").is_file())
        self.assertEqual(
            self.managed_catalog.data(floor_copy["id"])["kind"],
            "occupancy2d",
        )

    def test_shared_pgm_rename_copies_reference_without_breaking_other_yaml(self):
        (self.root / "floor_copy.yaml").write_text(
            (self.root / "floor.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        records = self.managed_catalog.list_snapshot()["maps"]
        floor = next(item for item in records if item["file_name"] == "floor.yaml")
        floor_copy = next(
            item for item in records if item["file_name"] == "floor_copy.yaml"
        )

        renamed = self.managed_catalog.rename(floor["id"], "renamed_floor")
        self.assertFalse((self.root / "floor.yaml").exists())
        self.assertTrue((self.root / "floor.pgm").is_file())
        self.assertTrue((self.root / "renamed_floor.yaml").is_file())
        self.assertTrue((self.root / "renamed_floor.pgm").is_file())
        self.assertEqual(self.managed_catalog.data(renamed["id"])["kind"], "occupancy2d")
        self.assertEqual(
            self.managed_catalog.data(floor_copy["id"])["kind"],
            "occupancy2d",
        )

    def test_concurrent_mutations_of_one_opaque_id_are_serialized(self):
        room = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["file_name"] == "room.pcd"
        )
        outcomes = []
        barrier = threading.Barrier(3)

        def rename(name):
            barrier.wait()
            try:
                outcomes.append(("ok", self.managed_catalog.rename(room["id"], name)))
            except SavedMapNotFound:
                outcomes.append(("not-found", None))

        threads = [
            threading.Thread(target=rename, args=("room_a",)),
            threading.Thread(target=rename, args=("room_b",)),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=2)

        self.assertEqual([status for status, _ in outcomes].count("ok"), 1)
        self.assertEqual([status for status, _ in outcomes].count("not-found"), 1)
        self.assertEqual(
            sum((self.root / name).exists() for name in ("room_a.pcd", "room_b.pcd")),
            1,
        )


if __name__ == "__main__":
    unittest.main()
