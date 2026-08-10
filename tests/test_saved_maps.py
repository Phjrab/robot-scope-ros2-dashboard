import json
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from robot_dashboard.saved_maps import (
    NavigationMapSnapshot,
    SavedMapCatalog,
    SavedMapConflict,
    SavedMapFormatError,
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
        self.assertFalse(record["editable"])
        self.assertEqual(record["edit_reason"], "saved map is read-only")
        self.assertEqual(record["mode"], "trinary")
        managed_record = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["kind"] == "occupancy2d"
        )
        self.assertTrue(managed_record["editable"])
        payload = self.catalog.data(record["id"])
        self.assertEqual((payload["width"], payload["height"]), (2, 2))
        self.assertEqual(payload["resolution"], 0.05)
        self.assertEqual(payload["origin"], [-1.0, -2.0, 0.0])
        decoded = __import__("base64").b64decode(payload["data_b64"])
        self.assertEqual(list(decoded), [255, 0, 0, 100])

    def test_navigation_map_resolver_copies_and_pins_managed_trinary_pair(self):
        floor = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["file_name"] == "floor.yaml"
        )
        private = self.root / "private-navigation-job"
        private.mkdir()

        source = self.managed_catalog.resolve_navigation_map(
            floor["id"], floor["revision"]
        )
        snapshot = self.managed_catalog.snapshot_navigation_map(
            floor["id"], floor["revision"], private
        )

        self.assertEqual((source.map_id, source.revision), (floor["id"], floor["revision"]))
        self.assertEqual((snapshot.width, snapshot.height), (2, 2))
        self.assertEqual(snapshot.occupancy, bytes([255, 0, 0, 100]))
        self.assertEqual(
            self.managed_catalog._read_map_yaml(snapshot.yaml_path)["image"],
            "map.pgm",
        )
        self.assertNotEqual(source.yaml_path.stat().st_ino, snapshot.yaml_path.stat().st_ino)
        self.assertNotEqual(source.image_path.stat().st_ino, snapshot.image_path.stat().st_ino)
        # Cell (1,0) is free; unknown, occupied and out-of-map cells fail closed.
        self.assertTrue(snapshot.known_free(-0.925, -1.975, clearance_radius=0.0))
        self.assertFalse(snapshot.known_free(-0.975, -1.975, clearance_radius=0.0))
        self.assertFalse(snapshot.known_free(-0.925, -1.925, clearance_radius=0.0))
        self.assertFalse(snapshot.known_free(10.0, 10.0, clearance_radius=0.0))

    def test_navigation_map_resolver_rejects_read_only_stale_and_unsupported_maps(self):
        managed_floor = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["file_name"] == "floor.yaml"
        )
        read_only_floor = next(
            item
            for item in self.catalog.list_snapshot()["maps"]
            if item["file_name"] == "floor.yaml"
        )
        with self.assertRaises(SavedMapReadOnly):
            self.catalog.resolve_navigation_map(
                read_only_floor["id"], read_only_floor["revision"]
            )
        with self.assertRaises(SavedMapConflict):
            self.managed_catalog.resolve_navigation_map(
                managed_floor["id"], "0" * 64
            )

        (self.root / "unsupported.pgm").write_bytes(b"P2\n1 1\n255\n255\n")
        (self.root / "unsupported.yaml").write_text(
            "image: unsupported.pgm\nresolution: 0.05\norigin: [0, 0, 0]\n"
            "negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n",
            encoding="utf-8",
        )
        unsupported = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["file_name"] == "unsupported.yaml"
        )
        with self.assertRaisesRegex(SavedMapFormatError, "P5"):
            self.managed_catalog.resolve_navigation_map(
                unsupported["id"], unsupported["revision"]
            )

    def test_navigation_snapshot_aborts_if_source_pair_changes_mid_copy(self):
        floor = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["file_name"] == "floor.yaml"
        )
        private = self.root / "racing-navigation-job"
        private.mkdir()
        real_copy = self.managed_catalog._copy_regular_snapshot
        calls = 0

        def mutate_after_first_copy(source_path, target_path, signature):
            nonlocal calls
            real_copy(source_path, target_path, signature)
            calls += 1
            if calls == 1:
                (self.root / "floor.pgm").write_bytes(
                    b"P5\n2 2\n255\n" + bytes([255, 0, 128, 254])
                )

        with patch.object(
            self.managed_catalog,
            "_copy_regular_snapshot",
            side_effect=mutate_after_first_copy,
        ):
            with self.assertRaises((SavedMapConflict, SavedMapMutationError)):
                self.managed_catalog.snapshot_navigation_map(
                    floor["id"], floor["revision"], private
                )
        self.assertEqual(list(private.iterdir()), [])

    def test_navigation_clearance_uses_actual_subcell_pose_and_grid_limit(self):
        occupancy = bytearray([0] * 9)
        occupancy[1] = 100
        snapshot = NavigationMapSnapshot(
            map_id="a" * 24,
            revision="b" * 64,
            name="subcell",
            frame_id="map",
            yaml_path=self.root / "floor.yaml",
            image_path=self.root / "floor.pgm",
            width=3,
            height=3,
            resolution=1.0,
            origin=(0.0, 0.0, 0.0),
            occupancy=bytes(occupancy),
        )
        # The pose is still in cell (0,0), but its footprint crosses into the
        # occupied neighbor. Checking only cell-center offsets would miss it.
        self.assertFalse(snapshot.known_free(0.99, 0.5, clearance_radius=0.2))
        self.assertTrue(snapshot.known_free(0.5, 0.5, clearance_radius=0.2))
        with self.assertRaises(ValueError):
            NavigationMapSnapshot(
                map_id="a" * 24,
                revision="b" * 64,
                name="bad",
                frame_id="map",
                yaml_path=self.root / "floor.yaml",
                image_path=self.root / "floor.pgm",
                width=2,
                height=2,
                resolution=1.0,
                origin=(0.0, 0.0, 0.0),
                occupancy=b"\x00",
            )

        (self.root / "large_navigation.pgm").write_bytes(
            b"P5\n32 32\n255\n" + bytes([255]) * (32 * 32)
        )
        (self.root / "large_navigation.yaml").write_text(
            "image: large_navigation.pgm\nresolution: 0.05\norigin: [0, 0, 0]\n"
            "negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n",
            encoding="utf-8",
        )
        limited = SavedMapCatalog(
            [self.root],
            managed_roots=[self.root],
            max_grid_cells=1_000,
        )
        self.assertNotIn(
            "large_navigation.yaml",
            {item["file_name"] for item in limited.list_snapshot()["maps"]},
        )

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

    def test_profile_additional_managed_root_is_catalogued(self):
        profile_dir = self.root / "config"
        output_dir = self.root / "custom-workspace" / "maps"
        profile_dir.mkdir()
        output_dir.mkdir(parents=True)
        (output_dir / "portable.json").write_text(
            '{"points":[0,0,0]}', encoding="utf-8"
        )
        catalog = SavedMapCatalog.from_profile(
            {"saved_maps": {"directories": []}},
            base_dir=profile_dir,
            additional_roots=[output_dir],
            managed_roots=[output_dir],
        )
        maps = catalog.list_snapshot()["maps"]
        self.assertEqual([item["file_name"] for item in maps], ["portable.json"])
        self.assertTrue(maps[0]["manageable"])

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

    def test_revisions_are_exact_signature_hashes_in_metadata_and_data(self):
        room = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["file_name"] == "room.pcd"
        )
        self.assertRegex(room["revision"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            self.managed_catalog.data(room["id"], max_points=10)["revision"],
            room["revision"],
        )

    def _clustered_pcd(self, name="clusters.pcd"):
        points = []
        for x_origin in (0.0, 0.4):
            points.extend(
                (
                    x_origin + (index % 5) * 0.005,
                    (index // 5) * 0.005,
                    0.2,
                )
                for index in range(10)
            )
        points.append((0.2, 0.0, 1.5))
        write_pcd(self.root / name, points)
        return next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["file_name"] == name
        )

    def test_converts_managed_pcd_to_new_unknown_background_pair(self):
        source = self._clustered_pcd()
        original = (self.root / "clusters.pcd").read_bytes()
        source_inode = (self.root / "clusters.pcd").stat().st_ino
        observed_snapshot = []
        real_reader = self.managed_catalog._pcd_xyz

        def observe_copy(path):
            observed_snapshot.append(path.stat().st_ino)
            return real_reader(path)

        with patch.object(self.managed_catalog, "_pcd_xyz", side_effect=observe_copy):
            result = self.managed_catalog.convert_pcd_to_2d(
                source["id"],
                "clusters_2d",
                z_min=-0.2,
                z_max=0.8,
                resolution=0.05,
                noise_radius=0.1,
                min_neighbors=10,
            )

        self.assertNotEqual(observed_snapshot, [source_inode])
        self.assertEqual((self.root / "clusters.pcd").read_bytes(), original)
        self.assertEqual(result["files"], ["clusters_2d.yaml", "clusters_2d.pgm"])
        self.assertEqual(result["details"]["filter"], "projected_xy_density")
        self.assertEqual(result["details"]["background"], "unknown")
        self.assertEqual(result["details"]["source_points"], 21)
        self.assertEqual(result["details"]["z_slice_points"], 20)
        self.assertEqual(result["details"]["selected_points"], 20)
        self.assertEqual(result["details"]["occupied_cells"], 2)
        self.assertEqual(result["details"]["result_map_id"], result["map"]["id"])
        payload = self.managed_catalog.data(result["map"]["id"])
        decoded = list(__import__("base64").b64decode(payload["data_b64"]))
        self.assertIn(255, decoded)
        self.assertIn(100, decoded)
        self.assertNotIn(0, decoded)
        self.assertFalse((self.root / ".robot_scope_transactions").exists())

    def test_free_background_is_an_explicit_pdf_compatible_option(self):
        source = self._clustered_pcd("free_source.pcd")
        result = self.managed_catalog.convert_pcd_to_2d(
            source["id"],
            "free_background",
            z_min=-0.2,
            z_max=0.8,
            resolution=0.05,
            noise_radius=0.1,
            min_neighbors=10,
            background="free",
        )
        decoded = list(
            __import__("base64").b64decode(
                self.managed_catalog.data(result["map"]["id"])["data_b64"]
            )
        )
        self.assertIn(0, decoded)
        self.assertIn(100, decoded)
        self.assertNotIn(255, decoded)

    def test_conversion_rejects_empty_filter_and_full_view_point_overflow(self):
        source = self._clustered_pcd("filtered_out.pcd")
        with self.assertRaises(SavedMapFormatError):
            self.managed_catalog.convert_pcd_to_2d(
                source["id"],
                "empty_filter",
                z_min=-0.2,
                z_max=0.8,
                resolution=0.05,
                noise_radius=0.01,
                min_neighbors=100,
            )
        self.assertFalse((self.root / "empty_filter.yaml").exists())

        guarded = SavedMapCatalog(
            [self.root],
            managed_roots=[self.root],
            max_full_view_points=10,
        )
        guarded_source = next(
            item
            for item in guarded.list_snapshot()["maps"]
            if item["file_name"] == "filtered_out.pcd"
        )
        with self.assertRaises(SavedMapPointLimitError):
            guarded.validate_pcd_conversion(
                guarded_source["id"],
                "too_many",
                z_min=-0.2,
                z_max=0.8,
                resolution=0.05,
            )

    def test_conversion_checks_grid_limit_before_dense_allocation(self):
        write_pcd(
            self.root / "wide.pcd",
            [(0.0, 0.0, 0.2), (50.0, 50.0, 0.2)],
        )
        source = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["file_name"] == "wide.pcd"
        )
        self.assertEqual(self.managed_catalog.max_grid_cells, 16_000_000)
        with patch("robot_dashboard.saved_maps.np.full") as allocate:
            with self.assertRaises(SavedMapFormatError):
                self.managed_catalog.convert_pcd_to_2d(
                    source["id"],
                    "too_wide",
                    z_min=-0.2,
                    z_max=0.8,
                    resolution=0.01,
                    noise_radius=0.1,
                    min_neighbors=1,
                )
        allocate.assert_not_called()
        self.assertFalse((self.root / "too_wide.yaml").exists())

    def test_conversion_aborts_on_source_inode_race(self):
        source = self._clustered_pcd("racing.pcd")
        real_reader = self.managed_catalog._pcd_xyz

        def replace_source(path):
            result = real_reader(path)
            replacement = self.root / "replacement.pcd"
            write_pcd(replacement, [(0.0, 0.0, 0.2)] * 20)
            replacement.replace(self.root / "racing.pcd")
            return result

        with patch.object(self.managed_catalog, "_pcd_xyz", side_effect=replace_source):
            with self.assertRaises(SavedMapMutationError):
                self.managed_catalog.convert_pcd_to_2d(
                    source["id"],
                    "raced_output",
                    z_min=-0.2,
                    z_max=0.8,
                    resolution=0.05,
                    noise_radius=0.1,
                    min_neighbors=10,
                )
        self.assertFalse((self.root / "raced_output.yaml").exists())
        self.assertFalse((self.root / "raced_output.pgm").exists())

    def test_conversion_requires_the_revision_captured_during_preflight(self):
        source = self._clustered_pcd("preflight_source.pcd")
        expected_revision = source["revision"]
        replacement = self.root / "preflight_replacement.pcd"
        write_pcd(replacement, [(0.0, 0.0, 0.2)] * 20)
        replacement.replace(self.root / "preflight_source.pcd")

        with patch.object(self.managed_catalog, "_copy_regular_snapshot") as copy_snapshot:
            with self.assertRaisesRegex(SavedMapConflict, "validate it again"):
                self.managed_catalog.convert_pcd_to_2d(
                    source["id"],
                    "stale_preflight",
                    z_min=-0.2,
                    z_max=0.8,
                    resolution=0.05,
                    noise_radius=0.1,
                    min_neighbors=10,
                    expected_revision=expected_revision,
                )
        copy_snapshot.assert_not_called()
        self.assertFalse((self.root / "stale_preflight.yaml").exists())

    def test_conversion_cancellation_is_checked_again_before_publication(self):
        source = self._clustered_pcd("cancel_source.pcd")
        checks = iter((False, True))
        with patch.object(self.managed_catalog, "_publish_occupancy_pair") as publish:
            with self.assertRaisesRegex(SavedMapMutationError, "before publication"):
                self.managed_catalog.convert_pcd_to_2d(
                    source["id"],
                    "cancelled_output",
                    z_min=-0.2,
                    z_max=0.8,
                    resolution=0.05,
                    noise_radius=0.1,
                    min_neighbors=10,
                    expected_revision=source["revision"],
                    cancelled=lambda: next(checks),
                )
        publish.assert_not_called()
        self.assertFalse((self.root / "cancelled_output.yaml").exists())
        self.assertFalse((self.root / "cancelled_output.pgm").exists())
        self.assertFalse((self.root / ".robot_scope_transactions").exists())

    def test_conversion_pair_publish_failure_rolls_back_both_outputs(self):
        source = self._clustered_pcd("rollback_source.pcd")
        real_publish = self.managed_catalog._publish_link
        calls = 0

        def fail_second(source_path, target_path):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise SavedMapConflict("injected pair publication race")
            return real_publish(source_path, target_path)

        with patch.object(self.managed_catalog, "_publish_link", side_effect=fail_second):
            with self.assertRaises(SavedMapConflict):
                self.managed_catalog.convert_pcd_to_2d(
                    source["id"],
                    "rollback_2d",
                    z_min=-0.2,
                    z_max=0.8,
                    resolution=0.05,
                    noise_radius=0.1,
                    min_neighbors=10,
                )
        self.assertFalse((self.root / "rollback_2d.yaml").exists())
        self.assertFalse((self.root / "rollback_2d.pgm").exists())
        self.assertFalse((self.root / ".robot_scope_transactions").exists())

    def test_edited_copy_preserves_unedited_pixels_and_requires_exact_revision(self):
        source = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["file_name"] == "floor.yaml"
        )
        result = self.managed_catalog.save_edited_copy(
            source["id"],
            "floor_brushed",
            source["revision"],
            [{"start": 0, "length": 1, "value": 100}],
        )
        _, _, pixels = self.managed_catalog._read_pgm(
            self.root / "floor_brushed.pgm",
            pixels=True,
        )
        self.assertEqual(np.rint(pixels * 255).astype(int).tolist(), [[255, 0], [0, 255]])
        self.assertEqual((self.root / "floor.pgm").read_bytes()[-4:], bytes([255, 0, 128, 255]))
        output_bytes = (self.root / "floor_brushed.pgm").read_bytes()[-4:]
        self.assertEqual(
            [output_bytes[index] for index in (0, 1, 3)],
            [255, 0, 255],
        )
        self.assertEqual(result["edit"]["source_revision"], source["revision"])
        self.assertEqual(result["edit"]["edited_cells"], 1)
        self.assertRegex(result["revision"], r"^[0-9a-f]{64}$")

        (self.root / "floor.yaml").write_text(
            (self.root / "floor.yaml").read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(SavedMapConflict):
            self.managed_catalog.save_edited_copy(
                source["id"],
                "stale_edit",
                source["revision"],
                [{"start": 0, "length": 1, "value": 0}],
            )
        self.assertFalse((self.root / "stale_edit.yaml").exists())

    def test_threshold_aware_pixels_round_trip_unknown_for_narrow_valid_gap(self):
        metadata = {
            "free_thresh": 0.49,
            "occupied_thresh": 0.51,
            "negate": 0,
        }
        grid = np.asarray([[0, -1, 100], [100, -1, 0]], dtype=np.int16)
        pixels = self.managed_catalog._occupancy_to_pixels(grid, metadata)
        normalized = pixels.astype(np.float64) / 255.0
        self.assertTrue(
            np.array_equal(
                self.managed_catalog._pixels_to_occupancy(normalized, metadata),
                grid,
            )
        )

    def test_edit_limits_and_pair_rollback_leave_no_partial_copy(self):
        source = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["file_name"] == "floor.yaml"
        )
        limited = SavedMapCatalog(
            [self.root],
            managed_roots=[self.root],
            max_edited_cells=2,
        )
        limited_source = next(
            item
            for item in limited.list_snapshot()["maps"]
            if item["file_name"] == "floor.yaml"
        )
        with self.assertRaises(SavedMapFormatError):
            limited.save_edited_copy(
                limited_source["id"],
                "too_many_edits",
                limited_source["revision"],
                [{"start": 0, "length": 3, "value": 100}],
            )

        real_publish = self.managed_catalog._publish_link
        calls = 0

        def fail_second(source_path, target_path):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise SavedMapConflict("injected edit pair race")
            return real_publish(source_path, target_path)

        with patch.object(self.managed_catalog, "_publish_link", side_effect=fail_second):
            with self.assertRaises(SavedMapConflict):
                self.managed_catalog.save_edited_copy(
                    source["id"],
                    "rollback_edit",
                    source["revision"],
                    [{"start": 0, "length": 1, "value": 100}],
                )
        self.assertFalse((self.root / "rollback_edit.yaml").exists())
        self.assertFalse((self.root / "rollback_edit.pgm").exists())
        self.assertFalse((self.root / ".robot_scope_transactions").exists())

    def test_editor_rejects_p2_16bit_scale_and_raw_maps(self):
        variants = {
            "ascii_map": (
                b"P2\n2 1\n255\n0 255\n",
                None,
                "binary P5",
            ),
            "wide_map": (
                b"P5\n2 1\n65535\n" + struct.pack(">HH", 0, 65535),
                None,
                "maxval=255",
            ),
            "scale_map": (b"P5\n2 1\n255\n\x00\xff", "scale", "trinary"),
            "raw_map": (b"P5\n2 1\n255\n\x00\xff", "raw", "trinary"),
        }
        for stem, (pgm, mode, expected_reason) in variants.items():
            (self.root / f"{stem}.pgm").write_bytes(pgm)
            lines = [
                f"image: {stem}.pgm",
                "resolution: 0.05",
                "origin: [0, 0, 0]",
                "negate: 0",
                "occupied_thresh: 0.65",
                "free_thresh: 0.196",
            ]
            if mode:
                lines.append(f"mode: {mode}")
            (self.root / f"{stem}.yaml").write_text("\n".join(lines), encoding="utf-8")

        records = {
            item["name"]: item for item in self.managed_catalog.list_snapshot()["maps"]
        }
        for stem, (_, _, expected_reason) in variants.items():
            record = records[stem]
            self.assertFalse(record["editable"])
            self.assertIn(expected_reason, record["edit_reason"])
            with self.assertRaisesRegex(SavedMapFormatError, expected_reason):
                self.managed_catalog.save_edited_copy(
                    record["id"],
                    f"{stem}_edited",
                    record["revision"],
                    [{"start": 0, "length": 1, "value": 100}],
                )
            self.assertFalse((self.root / f"{stem}_edited.yaml").exists())

    def test_editor_revalidates_copied_snapshot_format(self):
        source = next(
            item
            for item in self.managed_catalog.list_snapshot()["maps"]
            if item["file_name"] == "floor.yaml"
        )
        real_copy = self.managed_catalog._copy_regular_snapshot

        def alter_yaml_snapshot(source_path, target_path, signature):
            real_copy(source_path, target_path, signature)
            if target_path.name == "source.yaml":
                target_path.write_text(
                    target_path.read_text(encoding="utf-8") + "\nmode: raw\n",
                    encoding="utf-8",
                )

        with patch.object(
            self.managed_catalog,
            "_copy_regular_snapshot",
            side_effect=alter_yaml_snapshot,
        ):
            with self.assertRaisesRegex(SavedMapFormatError, "trinary"):
                self.managed_catalog.save_edited_copy(
                    source["id"],
                    "snapshot_bypass",
                    source["revision"],
                    [{"start": 0, "length": 1, "value": 100}],
                )
        self.assertFalse((self.root / "snapshot_bypass.yaml").exists())
        self.assertFalse((self.root / "snapshot_bypass.pgm").exists())
        self.assertFalse((self.root / ".robot_scope_transactions").exists())

    def test_invalid_negate_and_nonfinite_yaml_geometry_are_not_catalogued(self):
        invalid_lines = {
            "bad_negate": "negate: 2",
            "nan_resolution": "resolution: nan",
            "nan_origin": "origin: [nan, 0, 0]",
        }
        for stem, override in invalid_lines.items():
            (self.root / f"{stem}.pgm").write_bytes(b"P5\n1 1\n255\n\x00")
            values = {
                "resolution": "resolution: 0.05",
                "origin": "origin: [0, 0, 0]",
                "negate": "negate: 0",
            }
            values[override.split(":", 1)[0]] = override
            (self.root / f"{stem}.yaml").write_text(
                "\n".join(
                    [
                        f"image: {stem}.pgm",
                        values["resolution"],
                        values["origin"],
                        values["negate"],
                        "occupied_thresh: 0.65",
                        "free_thresh: 0.196",
                    ]
                ),
                encoding="utf-8",
            )
        names = {
            item["name"] for item in self.managed_catalog.list_snapshot()["maps"]
        }
        self.assertTrue(set(invalid_lines).isdisjoint(names))

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
