import copy
import hashlib
import importlib.util
import json
import math
import os
import struct
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest import mock

from robot_dashboard.map_annotations import empty_annotation_document, normalize_annotation_document
from robot_dashboard.map_lineage import build_family_document, serialize_family_document
from robot_dashboard.navigation_collision_mask import (
    CollisionMaskError, MAX_CELLS, build_collision_mask, write_collision_mask,
)
from robot_dashboard.saved_maps import NavigationMapSnapshot, SavedMapCatalog


def geometry(**changes):
    values = dict(map_id="1" * 24, revision="2" * 64, name="private room", frame_id="map",
                  yaml_path=Path("private.yaml"), image_path=Path("private.pgm"),
                  width=8, height=8, resolution=1.0, origin=(0.0, 0.0, 0.0),
                  occupancy=bytes(64), family_id="3" * 24, family_revision="4" * 64,
                  source_pcd_id="5" * 24, source_pcd_revision="6" * 64,
                  occupancy_map_id="1" * 24, occupancy_map_revision="2" * 64)
    values.update(changes)
    return NavigationMapSnapshot(**values)


def pins(grid):
    return dict(family_id=grid.family_id, family_revision=grid.family_revision,
                pcd_map_id=grid.source_pcd_id, pcd_revision=grid.source_pcd_revision,
                occupancy_map_id=grid.map_id, occupancy_revision=grid.revision)


def annotations(grid, vertices=None, kind="KEEP_OUT"):
    if vertices is None:
        return empty_annotation_document(grid.map_id, grid.revision)
    return normalize_annotation_document(
        map_id=grid.map_id, map_revision=grid.revision, geometry=grid, points=[],
        polygons=[dict(id="7" * 24, name="Zone", type=kind,
                       vertices=[dict(x=x, y=y) for x, y in vertices])],
    )


def build(grid, document=None, **changes):
    if document is None:
        document = annotations(grid)
    values = dict(expected_family=pins(grid),
                  expected_annotation_revision=document["annotation_revision"])
    values.update(changes)
    return build_collision_mask(grid, document, **values)


def blocked(artifact, width=8):
    return {(index % width, index // width) for index, value in enumerate(artifact.mask) if value}


class CollisionMaskGeometryTests(unittest.TestCase):
    def test_nonfree_source_bytes_are_preserved_and_derived_never_frees_unknown(self):
        source = bytes([0, 100, 255, 1, 99, 254] + [0] * 58)
        grid = geometry(occupancy=source)
        artifact = build(grid)
        self.assertEqual(artifact.source_occupancy, source)
        self.assertEqual(grid.occupancy, source)
        self.assertEqual(artifact.mask[:6], bytes([0, 100, 100, 100, 100, 100]))
        self.assertEqual(blocked(artifact), {(x, 0) for x in range(1, 6)})

    def test_polygon_inside_one_cell_is_blocked_without_containing_center(self):
        grid = geometry()
        artifact = build(grid, annotations(grid, [(2.1, 3.1), (2.2, 3.1), (2.1, 3.2)]))
        self.assertEqual(blocked(artifact), {(2, 3)})

    def test_thin_crossing_blocks_whole_cells_without_center_hits(self):
        grid = geometry()
        artifact = build(grid, annotations(grid, [(1.1, 2.1), (5.9, 2.1), (5.9, 2.2), (1.1, 2.2)]))
        self.assertEqual(blocked(artifact), {(x, 2) for x in range(1, 6)})

    def test_cells_inside_polygon_and_boundary_edge_corner_touches_are_blocked(self):
        grid = geometry()
        artifact = build(grid, annotations(grid, [(2, 2), (5, 2), (5, 5), (2, 5)]))
        self.assertEqual(blocked(artifact), {(x, y) for x in range(1, 6) for y in range(1, 6)})

    def test_rotated_and_translated_origin_uses_world_coordinates(self):
        base = geometry()
        rotated = geometry(origin=(20.0, -10.0, math.pi / 2))
        vertices = [(1.2, 2.2), (3.8, 2.2), (3.8, 4.8), (1.2, 4.8)]
        world = [(20.0 - y, -10.0 + x) for x, y in vertices]
        first, second = build(base, annotations(base, vertices)), build(rotated, annotations(rotated, world))
        self.assertEqual(first.mask, second.mask)
        self.assertNotEqual(first.digest, second.digest)

    def test_concave_polygon_preserves_the_free_notch(self):
        grid = geometry()
        artifact = build(grid, annotations(grid, [(1.2, 1.2), (5.8, 1.2), (5.8, 2.2),
                                                 (2.2, 2.2), (2.2, 5.8), (1.2, 5.8)]))
        self.assertIn((4, 1), blocked(artifact))
        self.assertIn((1, 4), blocked(artifact))
        self.assertNotIn((4, 4), blocked(artifact))

    def test_reverse_polygon_winding_keeps_same_mask(self):
        grid = geometry()
        vertices = [(1.2, 1.2), (5.8, 1.2), (5.8, 2.2), (2.2, 2.2), (2.2, 5.8), (1.2, 5.8)]
        self.assertEqual(build(grid, annotations(grid, vertices)).mask,
                         build(grid, annotations(grid, list(reversed(vertices)))).mask)

    def test_self_intersection_repeated_vertex_and_adjacent_overlap_reject(self):
        grid = geometry()
        cases = [
            [(1, 1), (6, 5), (1, 5), (5, 1)],
            [(1, 1), (5, 1), (5, 5), (1, 1), (1, 5)],
            [(1, 1), (5, 1), (3, 1), (5, 5), (1, 5)],
            [(1, 1), (5, 1), (5, 1), (5, 5), (1, 5)],
        ]
        for vertices in cases:
            with self.subTest(vertices=vertices), self.assertRaises(CollisionMaskError):
                build(grid, annotations(grid, vertices))

    def test_collinear_forward_edges_are_valid(self):
        grid = geometry()
        vertices = [(1.2, 1.2), (3, 1.2), (5.8, 1.2), (5.8, 3.8), (1.2, 3.8)]
        self.assertEqual(len(blocked(build(grid, annotations(grid, vertices)))), 15)

    def test_advisory_zones_do_not_create_mask_or_speed_effects(self):
        grid = geometry()
        for kind in ("SLOW_ZONE", "WAIT_ZONE"):
            artifact = build(grid, annotations(grid, [(1, 1), (5, 1), (1, 5)], kind=kind))
            self.assertEqual(artifact.mask, bytes(64))
            self.assertNotEqual(artifact.digest, build(grid).digest)
            semantics = json.loads(artifact.manifest)["semantics"]
            self.assertFalse(semantics["runtime_policy_enforced"])
            self.assertEqual(semantics["native_ingestion_evidence"], "not_provided")
            self.assertEqual(semantics["footprint_expansion"], "none")

    def test_exact_family_and_occupancy_pins_fail_closed(self):
        grid = geometry()
        for key in pins(grid):
            altered = pins(grid)
            altered[key] = "f" * len(altered[key])
            with self.subTest(key=key), self.assertRaises(CollisionMaskError):
                build(grid, expected_family=altered)
        for changes in ({"family_id": None}, {"occupancy_map_id": "f" * 24},
                        {"occupancy_map_revision": "f" * 64}):
            with self.assertRaises(CollisionMaskError):
                build(replace(grid, **changes), expected_family=pins(grid))
        with self.assertRaises(CollisionMaskError):
            build(grid, expected_family={**pins(grid), "extra": "value"})

    def test_annotation_revision_and_forged_content_fail_closed(self):
        grid = geometry()
        document = annotations(grid, [(1, 1), (5, 1), (1, 5)])
        with self.assertRaises(CollisionMaskError):
            build(grid, document, expected_annotation_revision="f" * 64)
        forged = copy.deepcopy(document)
        forged["polygons"][0]["vertices"][0]["x"] = 2
        with self.assertRaises(CollisionMaskError):
            build(grid, forged)
        for field in ("map_id", "map_revision"):
            forged = copy.deepcopy(document)
            forged[field] = "f" * len(forged[field])
            with self.assertRaises(CollisionMaskError):
                build(grid, forged)
        with self.assertRaises(CollisionMaskError):
            build(grid, {**document, "unexpected": True})

    def test_digest_is_path_time_independent_and_contains_exact_payload_hashes(self):
        grid = geometry()
        document = annotations(grid, [(1.2, 1.2), (2.2, 1.2), (1.2, 2.2)])
        before = copy.deepcopy(document)
        artifact = build(grid, document)
        relocated = replace(grid, name="other", yaml_path=Path("/elsewhere/map.yaml"), image_path=Path("/elsewhere/map.pgm"))
        self.assertEqual(artifact, build(relocated, document))
        self.assertEqual(document, before)
        manifest = json.loads(artifact.manifest)
        digest = manifest.pop("artifact_digest")
        canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        self.assertEqual(digest, hashlib.sha256(canonical).hexdigest())
        for name, payload in artifact.files()[:-1]:
            self.assertEqual(manifest["files"][name], {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
        self.assertNotIn(b"private", artifact.manifest)
        self.assertNotIn(b"timestamp", artifact.manifest)
        with self.assertRaises(FrozenInstanceError):
            artifact.mask = b""

    def test_source_pins_geometry_and_source_bytes_change_digest(self):
        grid = geometry()
        baseline = build(grid)
        for changes in ({"family_revision": "a" * 64}, {"source_pcd_revision": "b" * 64},
                        {"frame_id": "another_frame"}, {"resolution": 2.0},
                        {"origin": (1.0, 2.0, 0.0)}, {"occupancy": bytes([255] + [0] * 63)}):
            with self.subTest(changes=changes):
                self.assertNotEqual(baseline.digest, build(replace(grid, **changes)).digest)

    def test_pgm_has_one_vertical_flip_and_no_source_rethreshold(self):
        grid = geometry(width=2, height=2, occupancy=bytes([0, 255, 100, 0]))
        artifact = build(grid)
        self.assertEqual(artifact.pgm, b"P5\n2 2\n255\n" + bytes([0, 255, 255, 0]))
        self.assertIn(b"image: mask.pgm\n", artifact.yaml)
        self.assertEqual(artifact.source_occupancy, bytes([0, 255, 100, 0]))

    def test_cell_work_and_numerical_bounds_reject_without_truncation(self):
        oversized = geometry(width=MAX_CELLS + 1, height=1, occupancy=bytes(MAX_CELLS + 1))
        with self.assertRaisesRegex(CollisionMaskError, "cell limit"):
            build(oversized)
        grid = geometry()
        document = annotations(grid, [(1, 1), (5, 1), (5, 5), (1, 5)])
        with mock.patch("robot_dashboard.navigation_collision_mask.MAX_RASTER_WORK", 1):
            with self.assertRaisesRegex(CollisionMaskError, "work limit"):
                build(grid, document)
        for changes in ({"resolution": 1e-20}, {"resolution": 1e308}):
            with self.assertRaisesRegex(CollisionMaskError, "ill-conditioned"):
                build(replace(grid, **changes))


class CollisionMaskPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.artifact = build(geometry())

    def tearDown(self):
        for path in self.root.iterdir():
            if path.is_dir() and not path.is_symlink():
                path.chmod(0o700)
        self.temporary.cleanup()

    def test_new_immutable_artifact_writes_same_bytes_in_different_directories(self):
        for name in ("one", "two"):
            destination = write_collision_mask(self.artifact, self.root / name)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o500)
            for filename, payload in self.artifact.files():
                self.assertEqual((destination / filename).read_bytes(), payload)
                self.assertEqual((destination / filename).stat().st_mode & 0o777, 0o400)

    def test_existing_file_directory_and_symlink_are_never_overwritten(self):
        target = self.root / "existing"
        target.mkdir()
        (target / "keep").write_bytes(b"unchanged")
        file = self.root / "file"
        file.write_bytes(b"unchanged")
        link = self.root / "symlink"
        link.symlink_to(target, target_is_directory=True)
        for destination in (target, file, link):
            with self.subTest(destination=destination), self.assertRaises(CollisionMaskError):
                write_collision_mask(self.artifact, destination)
        self.assertEqual((target / "keep").read_bytes(), b"unchanged")
        self.assertEqual(file.read_bytes(), b"unchanged")
        self.assertTrue(link.is_symlink())

    def test_symlink_parent_and_relative_output_are_rejected(self):
        real = self.root / "real"
        real.mkdir()
        link = self.root / "linked"
        link.symlink_to(real, target_is_directory=True)
        for destination in (link / "artifact", Path("relative-artifact")):
            with self.assertRaises(CollisionMaskError):
                write_collision_mask(self.artifact, destination)
        self.assertEqual(list(real.iterdir()), [])

    def test_write_failure_cleans_only_new_owned_artifact(self):
        real_open = os.open
        def failing_open(path, *args, **kwargs):
            if path == "mask.yaml":
                raise OSError("injected storage error")
            return real_open(path, *args, **kwargs)
        with mock.patch("robot_dashboard.navigation_collision_mask.os.open", side_effect=failing_open):
            with self.assertRaises(CollisionMaskError):
                write_collision_mask(self.artifact, self.root / "incomplete")
        self.assertEqual(list(self.root.iterdir()), [])


class CollisionMaskCliTests(unittest.TestCase):
    def test_real_catalog_export_preserves_sources_and_rejects_stale_or_nested_output(self):
        script = Path(__file__).resolve().parents[1] / "scripts/build_navigation_collision_mask.py"
        spec = importlib.util.spec_from_file_location("mask_export_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            maps = root / "maps"
            maps.mkdir(mode=0o700)
            (maps / "floor.pgm").write_bytes(b"P5\n2 2\n255\n" + bytes([255, 0, 128, 255]))
            (maps / "floor.yaml").write_text("image: floor.pgm\nresolution: 1.0\norigin: [0, 0, 0]\nmode: trinary\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n")
            (maps / "source.pcd").write_bytes(b"VERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 1\nHEIGHT 1\nPOINTS 1\nDATA binary\n" + struct.pack("<fff", 0, 0, 0))
            for path in maps.iterdir():
                path.chmod(0o600)
            catalog = SavedMapCatalog([maps], managed_roots=[maps])
            entries = catalog.list_snapshot()["maps"]
            occupancy = next(item for item in entries if item["kind"] == "occupancy2d")
            pcd = next(item for item in entries if item["kind"] == "pointcloud3d")
            family = build_family_document(
                family_id="3" * 24, mapping_session_id="8" * 24,
                pcd_map_id=pcd["id"], pcd_revision=pcd["revision"], source_frame_id="camera_init",
                occupancy_map_id=occupancy["id"], occupancy_revision=occupancy["revision"],
                occupancy_frame_id="map", resolution=1.0, width=2, height=2, origin=(0.0, 0.0, 0.0),
                parameters=dict(z_min=-0.2, z_max=0.8, resolution=1.0, noise_radius=0.1,
                                min_neighbors=1, background="unknown"),
                created_at="2026-10-16T00:00:00Z",
            )
            (maps / "floor.map-family.json").write_bytes(serialize_family_document(family))
            (maps / "floor.map-family.json").chmod(0o600)
            expected = dict(family_id=family["family_id"], family_revision=family["family_revision"],
                            pcd_map_id=pcd["id"], pcd_revision=pcd["revision"],
                            occupancy_map_id=occupancy["id"], occupancy_revision=occupancy["revision"])
            revision = catalog.annotations(occupancy["id"])["annotation_revision"]
            before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
                      for path in maps.iterdir()}
            destination = root / "artifact"
            try:
                digest = module.export_mask(maps, destination, expected, revision)
                manifest = json.loads((destination / "manifest.json").read_bytes())
                self.assertEqual(manifest["artifact_digest"], digest)
                self.assertFalse(manifest["semantics"]["runtime_policy_enforced"])
                self.assertEqual((destination / "source.occupancy.bin").read_bytes(), bytes([255, 0, 0, 100]))
                self.assertEqual({path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
                                  for path in maps.iterdir()}, before)
                for output, family_pins, annotation_pin in (
                    (maps / "nested", expected, revision),
                    (root / "stale", expected, "f" * 64),
                    (root / "wrong-pcd", {**expected, "pcd_revision": "f" * 64}, revision),
                ):
                    with self.assertRaises(CollisionMaskError):
                        module.export_mask(maps, output, family_pins, annotation_pin)
                    self.assertFalse(output.exists())
            finally:
                if destination.exists():
                    destination.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
