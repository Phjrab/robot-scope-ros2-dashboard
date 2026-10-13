import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from robot_dashboard.map_annotations import annotation_revision, normalize_annotation_document, serialized_annotation_document
from robot_dashboard.map_lineage import build_family_document, serialize_family_document
from robot_dashboard.route_planner.state_store import RoutePlannerStateStore, empty_state
from robot_dashboard.saved_maps import SavedMapCatalog, SavedMapConflict, SavedMapFormatError
from scripts.onboard_map_identity_migration import IdentityMigrationError, adapt, capture, plan, validate_unreferenced_routes


class OnboardMapIdentityMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.source = self.base / "source"
        self.source.mkdir(mode=0o700)
        header = b"VERSION .7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 3\nHEIGHT 1\nPOINTS 3\nDATA binary\n"
        (self.source / "room.pcd").write_bytes(header + b"".join(struct.pack("<fff", i, i, 0.1) for i in range(3)))
        (self.source / "room.pgm").write_bytes(b"P5\n20 20\n255\n" + bytes([255] * 400))
        (self.source / "room.yaml").write_text("image: room.pgm\nresolution: 1.0\norigin: [0, 0, 0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n")
        catalog = SavedMapCatalog([self.source], managed_roots=[self.source])
        records = catalog.list_snapshot()["maps"]
        self.pcd = next(r for r in records if r["kind"] == "pointcloud3d")
        self.occupancy = next(r for r in records if r["kind"] == "occupancy2d")
        self.family = build_family_document(family_id="1" * 24, mapping_session_id="2" * 24,
            pcd_map_id=self.pcd["id"], pcd_revision=self.pcd["revision"], source_frame_id="camera_init",
            occupancy_map_id=self.occupancy["id"], occupancy_revision=self.occupancy["revision"],
            occupancy_frame_id="map", resolution=1.0, width=20, height=20, origin=[0.0, 0.0, 0.0],
            parameters={"z_min": -1.0, "z_max": 1.0, "resolution": 1.0, "noise_radius": 0.1, "min_neighbors": 1, "background": "free"},
            created_at="2026-09-01T00:00:00Z")
        self.family_path = self.source / "room.map-family.json"
        self.family_path.write_bytes(serialize_family_document(self.family))
        self.family_path.chmod(0o600)
        geometry = catalog.route_geometry(self.occupancy["id"], self.occupancy["revision"])
        annotation = normalize_annotation_document(map_id=geometry.map_id, map_revision=geometry.revision,
            points=[{"id": "3" * 24, "type": "POI", "name": "Source point", "pose": {"x": 10.0, "y": 10.0, "yaw": 0.0}}],
            polygons=[], geometry=geometry)
        self.annotation_path = self.source / "room.annotations.json"
        self.annotation_path.write_bytes(serialized_annotation_document(annotation))
        self.annotation_path.chmod(0o600)
        self.document = capture(self.source)
        self.target = self.base / "target"
        self.preserved = self.base / "preserved"
        shutil.copytree(self.source, self.target)
        shutil.copytree(self.source, self.preserved)
        self.report = self.base / "provenance.json"

    def test_real_catalog_copy_requires_rebinding_and_preserves_geometry_lineage(self):
        catalog = SavedMapCatalog([self.target], managed_roots=[self.target])
        target_map = next(r for r in catalog.list_snapshot()["maps"] if r["kind"] == "occupancy2d")
        self.assertNotEqual(target_map["id"], self.occupancy["id"])
        self.assertNotEqual(target_map["revision"], self.occupancy["revision"])
        with self.assertRaises(SavedMapConflict):
            catalog.resolve_navigation_map(target_map["id"], target_map["revision"])
        old_annotation = json.loads(self.annotation_path.read_text())
        result = adapt(self.document, self.preserved, self.target, self.report)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual((result["families_validated"], result["annotations_validated"]), (1, 1))
        family = catalog.map_family(target_map["id"])["families"][0]
        self.assertEqual(family["family_id"], self.family["family_id"])
        self.assertEqual(family["created_at"], self.family["created_at"])
        self.assertEqual(family["source"]["mapping_session_id"], self.family["source"]["mapping_session_id"])
        self.assertEqual(family["occupancy"]["map_id"], target_map["id"])
        annotations = catalog.annotations(target_map["id"])
        self.assertEqual(annotations["points"], old_annotation["points"])
        for name in ("room.pcd", "room.pgm", "room.yaml"):
            self.assertEqual((self.target / name).read_bytes(), (self.source / name).read_bytes())
        for name in self.document["artifacts"]:
            self.assertEqual((self.preserved / name).read_bytes(), (self.source / name).read_bytes())
        self.assertEqual(len(json.loads(self.report.read_text())["changes"]), 2)

    def test_changed_cloud_or_preservation_is_rejected_before_writes(self):
        original = (self.target / "room.map-family.json").read_bytes()
        (self.target / "room.pcd").write_bytes(b"changed")
        with self.assertRaises(IdentityMigrationError):
            adapt(self.document, self.preserved, self.target, self.report)
        self.assertEqual((self.target / "room.map-family.json").read_bytes(), original)
        self.assertFalse(self.report.exists())

    def test_existing_report_or_linked_root_cannot_be_overwritten(self):
        self.report.write_text("keep")
        with self.assertRaises(IdentityMigrationError):
            adapt(self.document, self.preserved, self.target, self.report)
        self.assertEqual(self.report.read_text(), "keep")
        linked = self.base / "linked"
        linked.symlink_to(self.target, target_is_directory=True)
        with self.assertRaises(IdentityMigrationError):
            plan(self.document, self.preserved, linked)

    def test_failed_final_catalog_validation_restores_original_sidecars(self):
        original = {name: (self.target / name).read_bytes() for name in self.document["families"] | self.document["annotations"]}
        with patch.object(SavedMapCatalog, "resolve_navigation_map", side_effect=SavedMapConflict("injected failure")):
            with self.assertRaises(SavedMapConflict):
                adapt(self.document, self.preserved, self.target, self.report)
        for name, payload in original.items():
            self.assertEqual((self.target / name).read_bytes(), payload)
        report = json.loads(self.report.read_text())
        self.assertEqual((report["status"], report["sidecar_rollback"]), ("FAIL", "PASS"))

    def test_failed_final_provenance_write_restores_original_sidecars(self):
        from scripts.onboard_map_identity_migration import _write
        original = {name: (self.target / name).read_bytes() for name in self.document["families"] | self.document["annotations"]}
        def fail_pass_report(path, payload):
            if path == self.report and json.loads(payload)["status"] == "PASS":
                raise OSError("injected final report write failure")
            _write(path, payload)
        with patch("scripts.onboard_map_identity_migration._write", side_effect=fail_pass_report):
            with self.assertRaises(OSError):
                adapt(self.document, self.preserved, self.target, self.report)
        for name, payload in original.items():
            self.assertEqual((self.target / name).read_bytes(), payload)
        report = json.loads(self.report.read_text())
        self.assertEqual((report["status"], report["sidecar_rollback"]), ("FAIL", "PASS"))

    def test_stale_source_family_is_not_rebound_to_current_data(self):
        family = dict(self.family)
        family["source"] = {**family["source"], "pcd_revision": "f" * 64}
        from robot_dashboard.map_lineage import family_revision
        family["family_revision"] = family_revision(family)
        self.family_path.write_bytes(serialize_family_document(family))
        with self.assertRaises(IdentityMigrationError):
            capture(self.source)

    def test_known_rounded_pi_defect_requires_explicit_capture_and_strict_derivative(self):
        import math
        raw = json.loads(self.annotation_path.read_text())
        raw["points"][0]["pose"]["yaw"] = round(math.pi, 6)
        raw["revision"] = raw["annotation_revision"] = annotation_revision(
            map_id=raw["map_id"], map_revision=raw["map_revision"], points=raw["points"], polygons=raw["polygons"])
        self.annotation_path.write_text(json.dumps(raw))
        with self.assertRaises(SavedMapFormatError):
            capture(self.source)
        source_bytes = self.annotation_path.read_bytes()
        document = capture(self.source, canonicalize_rounded_pi=True)
        self.assertEqual(document["annotation_canonicalizations"]["room.annotations.json"]["source_validation"], "FAIL")
        for destination in (self.target, self.preserved):
            shutil.rmtree(destination)
            shutil.copytree(self.source, destination)
        result = adapt(document, self.preserved, self.target, self.report)
        self.assertEqual(result["status"], "PASS")
        target_catalog = SavedMapCatalog([self.target], managed_roots=[self.target])
        target_map = next(r for r in target_catalog.list_snapshot()["maps"] if r["kind"] == "occupancy2d")
        annotation = target_catalog.annotations(target_map["id"])
        self.assertEqual(annotation["points"][0]["pose"]["yaw"], math.pi)
        self.assertEqual(self.annotation_path.read_bytes(), source_bytes)
        self.assertEqual((self.preserved / "room.annotations.json").read_bytes(), source_bytes)
        self.assertIn("room.annotations.json", result["source_annotation_canonicalizations"])

    def test_rounded_pi_option_does_not_accept_corrupt_content_hash(self):
        raw = json.loads(self.annotation_path.read_text())
        raw["annotation_revision"] = raw["revision"] = "f" * 64
        self.annotation_path.write_text(json.dumps(raw))
        with self.assertRaises(IdentityMigrationError):
            capture(self.source, canonicalize_rounded_pi=True)

    def test_rounded_pi_option_does_not_rewrite_other_authoring_fields(self):
        import math
        raw = json.loads(self.annotation_path.read_text())
        raw["points"][0]["pose"]["yaw"] = round(math.pi, 6)
        raw["points"][0]["name"] = " Source point "
        raw["revision"] = raw["annotation_revision"] = annotation_revision(
            map_id=raw["map_id"], map_revision=raw["map_revision"], points=raw["points"], polygons=raw["polygons"])
        self.annotation_path.write_text(json.dumps(raw))
        with self.assertRaises(IdentityMigrationError):
            capture(self.source, canonicalize_rounded_pi=True)

    def test_actual_unreferenced_route_schema_validates_without_file_mutation(self):
        root = self.base / "routes"
        root.mkdir(mode=0o700)
        state = empty_state()
        state["guidance"]["active"] = True
        RoutePlannerStateStore(root).save(state)
        before = (root / "route-planner.json").read_bytes()
        result = validate_unreferenced_routes(root)
        self.assertEqual((result["status"], result["saved_map_pins"], result["guidance_resumed"]), ("PASS", 0, False))
        self.assertEqual((root / "route-planner.json").read_bytes(), before)
        state["graph"] = {"map_id": "1" * 24}
        RoutePlannerStateStore(root).save(state)
        with self.assertRaises(IdentityMigrationError):
            validate_unreferenced_routes(root)


if __name__ == "__main__":
    unittest.main()
