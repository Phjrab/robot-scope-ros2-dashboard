import copy
import os
import tempfile
import unittest
from pathlib import Path

from scripts.onboard_data_migration import MigrationError, copy_bundle, inventory, validate_manifest, verify


class OnboardDataMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.source = self.base / "source"
        self.source.mkdir()
        (self.source / "map.pcd").write_bytes(b"original map bytes")
        (self.source / "map.map-family.json").write_bytes(b'{"revision":"original"}')
        self.document = inventory(self.source, "maps", ["map.pcd", "map.map-family.json"])

    def test_copy_preserves_bytes_original_and_private_permissions(self):
        target = self.base / "new"
        result = copy_bundle(self.source, target, self.document)
        self.assertEqual(result["files"], 2)
        self.assertEqual((target / "map.pcd").read_bytes(), (self.source / "map.pcd").read_bytes())
        self.assertEqual((target / "map.pcd").stat().st_mode & 0o777, 0o600)
        self.assertEqual(target.stat().st_mode & 0o777, 0o700)
        self.assertEqual(verify(target, self.document, exact=True), result)

    def test_existing_destination_is_never_overwritten(self):
        target = self.base / "new"
        target.mkdir()
        sentinel = target / "keep"
        sentinel.write_text("keep")
        with self.assertRaises(MigrationError):
            copy_bundle(self.source, target, self.document)
        self.assertEqual(sentinel.read_text(), "keep")

    def test_source_hash_change_prevents_any_copy(self):
        (self.source / "map.pcd").write_bytes(b"changed")
        target = self.base / "new"
        with self.assertRaises(MigrationError):
            copy_bundle(self.source, target, self.document)
        self.assertFalse(target.exists())

    def test_symlink_files_directories_and_destinations_are_rejected(self):
        (self.source / "link.pcd").symlink_to(self.source / "map.pcd")
        with self.assertRaises(MigrationError):
            inventory(self.source, "maps", ["link.pcd"])
        linked_root = self.base / "linked-root"
        linked_root.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(MigrationError):
            inventory(linked_root, "maps", ["map.pcd"])
        with self.assertRaises(MigrationError):
            copy_bundle(self.source, linked_root / "new", self.document)

    def test_hardlinks_are_rejected(self):
        os.link(self.source / "map.pcd", self.source / "hardlink.pcd")
        with self.assertRaises(MigrationError):
            verify(self.source, self.document)

    def test_manifest_cannot_select_credentials_or_live_authority(self):
        for kind, name in (("settings", "control.env"), ("settings", "state.json"),
                           ("routes", "navigation/jobs/job.json"), ("models", ".ssh/key.pem"),
                           ("maps", "../elsewhere.pcd"), ("maps", "/elsewhere.pcd")):
            with self.subTest(kind=kind, name=name):
                document = copy.deepcopy(self.document)
                document["kind"] = kind
                document["files"] = [{"path": name, "bytes": 0, "sha256": "0" * 64}]
                with self.assertRaises(MigrationError):
                    validate_manifest(document)

    def test_explicit_selection_does_not_pick_unrelated_data(self):
        (self.source / "control.env").write_text("private")
        self.assertEqual(inventory(self.source, "maps", ["map.pcd"])["files"][0]["path"], "map.pcd")

    def test_exact_verification_rejects_extra_files(self):
        target = self.base / "new"
        copy_bundle(self.source, target, self.document)
        (target / "unexpected.pcd").write_bytes(b"extra")
        with self.assertRaises(MigrationError):
            verify(target, self.document, exact=True)

    def test_datasets_preserve_nested_samples_and_metadata(self):
        samples = self.source / "sessions" / "example" / "samples" / "00000001"
        samples.mkdir(parents=True)
        (samples / "go2_front.jpg").write_bytes(b"jpeg bytes")
        (samples / "metadata.json").write_text("{}")
        (samples.parent.parent / "manifest.json").write_text('{"state":"completed","sample_count":1}')
        document = inventory(self.source, "datasets", ["sessions"])
        self.assertEqual(copy_bundle(self.source, self.base / "datasets", document)["files"], 3)

    def test_only_fixed_dataset_export_names_can_preserve_opaque_zip(self):
        exports = self.source / "exports"
        exports.mkdir()
        export = exports / ("1" * 32 + ".zip")
        export.write_bytes(b"opaque bytes are copied, never extracted")
        document = inventory(self.source, "datasets", ["exports"])
        target = self.base / "datasets"
        copy_bundle(self.source, target, document)
        self.assertEqual((target / "exports" / export.name).read_bytes(), export.read_bytes())
        (exports / "unexpected.zip").write_bytes(b"no")
        with self.assertRaises(MigrationError):
            inventory(self.source, "datasets", ["exports"])

    def test_mission_document_is_history_not_route_runtime_data(self):
        (self.source / "missions.json").write_text('{"active_mission_id":"old-session"}')
        with self.assertRaises(MigrationError):
            inventory(self.source, "routes", ["missions.json"])
        document = inventory(self.source, "mission-history", ["missions.json"])
        self.assertEqual(copy_bundle(self.source, self.base / "history", document)["files"], 1)


if __name__ == "__main__":
    unittest.main()
