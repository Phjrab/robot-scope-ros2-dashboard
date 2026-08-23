import json
import os
import tempfile
import unittest
from pathlib import Path

from robot_dashboard.map_annotations import (
    MapAnnotationFormatError,
    empty_annotation_document,
    normalize_annotation_document,
    parse_annotation_document,
    resolve_annotation_goal,
    serialized_annotation_document,
)
from robot_dashboard.saved_maps import (
    SavedMapCatalog,
    SavedMapConflict,
    SavedMapFormatError,
    SavedMapReadOnly,
)


class Geometry:
    map_id = "a" * 24
    revision = "b" * 64

    def contains(self, x, y):
        return 0 <= x < 10 and 0 <= y < 10

    def known_free(self, x, y, *, clearance_radius):
        return self.contains(x, y) and not (4 <= x < 6 and 4 <= y < 6)


def point(kind="POI", name="Loading bay", x=1.0, y=2.0, yaw=0.0, identifier=None):
    return {
        "id": identifier,
        "type": kind,
        "name": name,
        "pose": {"x": x, "y": y, "yaw": yaw},
    }


def polygon(kind="KEEP_OUT", name="Shelf", identifier=None):
    return {
        "id": identifier,
        "type": kind,
        "name": name,
        "vertices": [{"x": 1.0, "y": 1.0}, {"x": 2.0, "y": 1.0}, {"x": 1.5, "y": 2.0}],
    }


class MapAnnotationSchemaTests(unittest.TestCase):
    def test_empty_revision_is_deterministic_and_documents_semantics(self):
        first = empty_annotation_document("a" * 24, "b" * 64)
        second = empty_annotation_document("a" * 24, "b" * 64)
        self.assertEqual(first["annotation_revision"], second["revision"])
        self.assertFalse(first["exists"])
        self.assertIn("single", first["semantics"]["HOME"])
        self.assertIn("not implied", first["semantics"]["DOCK"])
        self.assertIn("no costmap", first["semantics"]["KEEP_OUT"])

    def test_normalization_bounds_geometry_ids_home_and_names(self):
        identifiers = iter(("1" * 24, "2" * 24))
        document = normalize_annotation_document(
            map_id=Geometry.map_id,
            map_revision=Geometry.revision,
            points=[point(kind="HOME", name="홈")],
            polygons=[polygon(kind="SLOW_ZONE", name="Slow zone")],
            geometry=Geometry(),
            identifier_factory=lambda: next(identifiers),
        )
        self.assertEqual(document["points"][0]["name"], "홈")
        self.assertEqual(document["polygons"][0]["id"], "2" * 24)
        self.assertEqual(document["annotation_revision"], document["revision"])

        invalid_documents = (
            ([point(x=float("nan"))], []),
            ([point(x=20.0)], []),
            ([point(x=5.0, y=5.0)], []),
            ([point(kind="HOME"), point(kind="HOME")], []),
            ([point(name="../../secret")], []),
            ([], [{**polygon(), "vertices": [{"x": 1.0, "y": 1.0}] * 3}]),
            ([], [{**polygon(), "vertices": [{"x": 1.0, "y": 1.0}, {"x": 20.0, "y": 1.0}, {"x": 1.0, "y": 2.0}]}]),
        )
        for points, polygons in invalid_documents:
            with self.subTest(points=points, polygons=polygons):
                with self.assertRaises(MapAnnotationFormatError):
                    normalize_annotation_document(
                        map_id=Geometry.map_id,
                        map_revision=Geometry.revision,
                        points=points,
                        polygons=polygons,
                        geometry=Geometry(),
                    )

    def test_serialization_revision_and_goal_resolution_are_strict(self):
        document = normalize_annotation_document(
            map_id=Geometry.map_id,
            map_revision=Geometry.revision,
            points=[point(identifier="1" * 24)],
            polygons=[polygon(identifier="2" * 24)],
            geometry=Geometry(),
        )
        stored = json.loads(serialized_annotation_document(document))
        parsed = parse_annotation_document(stored, geometry=Geometry())
        goal = resolve_annotation_goal(parsed, "1" * 24)
        self.assertEqual((goal.name, goal.x, goal.y), ("Loading bay", 1.0, 2.0))
        stored["points"][0]["pose"]["x"] = 3.0
        with self.assertRaisesRegex(MapAnnotationFormatError, "revision"):
            parse_annotation_document(stored, geometry=Geometry())
        with self.assertRaisesRegex(MapAnnotationFormatError, "not found"):
            resolve_annotation_goal(parsed, "2" * 24)


class MapAnnotationCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        # ROS rows after flip: [unknown, free], [free, occupied].
        (self.root / "floor.pgm").write_bytes(
            b"P5\n2 2\n255\n" + bytes([255, 0, 128, 255])
        )
        (self.root / "floor.yaml").write_text(
            "image: floor.pgm\nresolution: 1\norigin: [0, 0, 0]\n"
            "negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n",
            encoding="utf-8",
        )
        self.catalog = SavedMapCatalog(
            [self.root], managed_roots=[self.root], max_grid_cells=1_000
        )
        self.map = self.catalog.list_snapshot()["maps"][0]

    def tearDown(self):
        self.temporary.cleanup()

    def test_cas_update_is_atomic_private_and_does_not_mutate_map_pair(self):
        before_yaml = (self.root / "floor.yaml").read_bytes()
        before_pgm = (self.root / "floor.pgm").read_bytes()
        empty = self.catalog.annotations(self.map["id"])
        saved = self.catalog.update_annotations(
            self.map["id"],
            self.map["revision"],
            empty["annotation_revision"],
            [point(x=1.5, y=0.5, identifier=None)],
            [
                {
                    **polygon(identifier=None),
                    "vertices": [
                        {"x": 0.1, "y": 0.1},
                        {"x": 1.8, "y": 0.1},
                        {"x": 1.0, "y": 1.8},
                    ],
                }
            ],
        )
        sidecar = self.root / "floor.annotations.json"
        self.assertTrue(sidecar.is_file())
        self.assertEqual(sidecar.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / "floor.yaml").read_bytes(), before_yaml)
        self.assertEqual((self.root / "floor.pgm").read_bytes(), before_pgm)
        self.assertEqual(saved["map_revision"], self.map["revision"])
        self.assertNotEqual(saved["annotation_revision"], empty["annotation_revision"])
        self.assertNotIn("floor.annotations.json", {item["file_name"] for item in self.catalog.list_snapshot()["maps"]})
        self.assertEqual(
            self.catalog.resolve_annotation_goal(
                self.map["id"],
                self.map["revision"],
                saved["annotation_revision"],
                saved["points"][0]["id"],
            ).name,
            "Loading bay",
        )

        with self.assertRaises(SavedMapConflict):
            self.catalog.update_annotations(
                self.map["id"], self.map["revision"], empty["annotation_revision"], [], []
            )
        with self.assertRaises(SavedMapConflict):
            self.catalog.resolve_annotation_goal(
                self.map["id"], self.map["revision"], "0" * 64, saved["points"][0]["id"]
            )

    def test_symlink_permissions_corruption_and_map_revision_fail_closed(self):
        sidecar = self.root / "floor.annotations.json"
        sidecar.symlink_to(self.root / "floor.yaml")
        with self.assertRaises((SavedMapReadOnly, SavedMapFormatError)):
            self.catalog.annotations(self.map["id"])
        sidecar.unlink()
        sidecar.write_text("{}", encoding="utf-8")
        os.chmod(sidecar, 0o600)
        with self.assertRaises(SavedMapFormatError):
            self.catalog.annotations(self.map["id"])
        sidecar.unlink()
        empty = self.catalog.annotations(self.map["id"])
        with self.assertRaises(SavedMapConflict):
            self.catalog.update_annotations(
                self.map["id"], "0" * 64, empty["annotation_revision"], [], []
            )

    def test_map_rename_repins_and_delete_removes_the_sidecar(self):
        empty = self.catalog.annotations(self.map["id"])
        saved = self.catalog.update_annotations(
            self.map["id"],
            self.map["revision"],
            empty["annotation_revision"],
            [point(x=1.5, y=0.5, identifier="1" * 24)],
            [],
        )

        renamed = self.catalog.rename(self.map["id"], "renamed")
        migrated = self.catalog.annotations(renamed["id"])

        self.assertFalse((self.root / "floor.annotations.json").exists())
        self.assertTrue((self.root / "renamed.annotations.json").is_file())
        self.assertNotEqual(migrated["map_id"], saved["map_id"])
        self.assertNotEqual(migrated["map_revision"], saved["map_revision"])
        self.assertEqual(migrated["points"][0]["id"], "1" * 24)
        deleted = self.catalog.delete(renamed["id"])
        self.assertIn("renamed.annotations.json", deleted["files"])
        self.assertFalse((self.root / "renamed.annotations.json").exists())


if __name__ == "__main__":
    unittest.main()
