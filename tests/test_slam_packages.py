import hashlib
import io
import json
import os
import stat
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from robot_dashboard.slam_packages import MapPackageError, MapPackageStore


class NativeMapPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = MapPackageStore(self.root / "managed", quiescence_seconds=0.001)
        self.metadata = {
            "name": "Stereo room", "engine_id": "visual_stereo",
            "engine_version": "3.2", "native_format_version": "cu-v3",
            "source_session_id": "session-a", "map_frame": "map",
            "calibration_hash": "a" * 64, "sensor_config_hash": "b" * 64,
            "units": "m", "axes": "ros", "data_provenance": "synthetic_fixture",
        }
        self.preview = {"capture_time": "2026-10-15T00:00:00+00:00",
                        "spatial_scope": "global_map", "coverage": "unknown",
                        "points": [[1, 2, 3], [100, 2, 3]], "trajectory": [[0, 0, 0]]}

    def tearDown(self):
        self.temporary.cleanup()

    def assert_code(self, code, callback):
        with self.assertRaises(MapPackageError) as raised:
            callback()
        self.assertEqual(raised.exception.code, code)
        self.assertNotIn(str(self.root), str(raised.exception))

    def staging(self):
        staging = self.store.create_staging()
        (staging.native_path / "data.mdb").write_bytes(b"immutable-native-database\x00\x01")
        nested = staging.native_path / "auxiliary"
        nested.mkdir()
        (nested / "index.bin").write_bytes(b"official-complete-file-set")
        return staging

    def publish(self, **kwargs):
        staging = self.staging()
        return self.store.publish_staging(
            staging.token, metadata=kwargs.pop("metadata", self.metadata),
            official_save_completed=True,
            required_native_files=["data.mdb", "auxiliary/index.bin"],
            preview=kwargs.pop("preview", self.preview), **kwargs)

    def native_bytes(self, package):
        path = self.store.root / "packages" / package["id"] / "native"
        return {file.relative_to(path).as_posix(): file.read_bytes()
                for file in path.rglob("*") if file.is_file()}

    def archive(self, package):
        handle, metadata = self.store.export_package(package["id"], expected_revision=package["revision"])
        self.assertGreater(metadata["bytes"], 0)
        try:
            return handle.read()
        finally:
            handle.close()

    def rewrite_archive(self, source, change):
        with zipfile.ZipFile(io.BytesIO(source)) as archive:
            entries = {item.filename: archive.read(item) for item in archive.infolist()}
        change(entries)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, payload in entries.items():
                archive.writestr(name, payload)
        return output.getvalue()

    def test_official_completion_required_and_private_atomic_publication(self):
        staging = self.staging()
        for completed in (False, None, 1, "completed"):
            self.assert_code("SAVE_INCOMPLETE", lambda: self.store.publish_staging(
                staging.token, metadata=self.metadata, official_save_completed=completed,
                required_native_files=["data.mdb"]))
        self.assertEqual(self.store.list_packages(), [])
        package = self.store.publish_staging(
            staging.token, metadata=self.metadata, official_save_completed=True,
            required_native_files=["data.mdb", "auxiliary/index.bin"], preview=self.preview)
        self.assertRegex(package["id"], r"^np_[0-9a-f]{32}$")
        self.assertEqual(package["preview_consistency"], "approximate")
        self.assertEqual(package["compatibility"]["status"], "blocked")
        self.assertFalse(package["navigation_eligible"])
        self.assertEqual(package["validation"]["native_load"], "unknown")
        self.assertNotIn(str(self.root), json.dumps(package))
        self.assertFalse(staging.native_path.exists())
        for path in self.store.root.rglob("*"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600)
        self.assertEqual(len(package["native_artifacts"]), 2)
        native = self.native_bytes(package)
        for item in package["native_artifacts"]:
            self.assertEqual(item["size_bytes"], len(native[item["path"]]))
            self.assertEqual(item["sha256"], hashlib.sha256(native[item["path"]]).hexdigest())
        self.assertEqual(self.store.get_preview(package["id"]), self.preview)

    def test_missing_empty_required_files_and_zero_declared_requirements_block(self):
        staging = self.staging()
        (staging.native_path / "empty.bin").write_bytes(b"")
        for required in ([], ["absent.bin"], ["empty.bin"]):
            self.assert_code("NATIVE_FILES_MISSING", lambda: self.store.publish_staging(
                staging.token, metadata=self.metadata, official_save_completed=True,
                required_native_files=required))
        self.assertEqual(self.store.list_packages(), [])

    def test_quiescence_detects_writer_and_staging_remains_for_cleanup(self):
        staging = self.staging()
        def writer(_):
            (staging.native_path / "data.mdb").write_bytes(b"changed")
        with patch("robot_dashboard.slam_packages.time.sleep", side_effect=writer):
            self.assert_code("NATIVE_WRITE_ACTIVE", lambda: self.store.publish_staging(
                staging.token, metadata=self.metadata, official_save_completed=True,
                required_native_files=["data.mdb"]))
        self.assertEqual(self.store.list_packages(), [])
        self.assertTrue(staging.native_path.exists())
        self.store.discard_staging(staging.token)
        self.assertFalse(staging.native_path.exists())

    def test_failed_atomic_move_has_no_catalog_entry_or_publish_leftovers(self):
        staging = self.staging()
        with patch("robot_dashboard.slam_packages.os.replace", side_effect=OSError("synthetic")):
            self.assert_code("PACKAGE_IO_ERROR", lambda: self.store.publish_staging(
                staging.token, metadata=self.metadata, official_save_completed=True,
                required_native_files=["data.mdb"]))
        self.assertEqual(self.store.list_packages(), [])
        self.assertTrue(staging.native_path.exists())
        self.assertEqual([path.name for path in (self.store.root / "staging").iterdir()], [staging.token])

    def test_native_links_special_files_and_limits_rejected(self):
        for kind in ("symlink", "hardlink", "fifo"):
            staging = self.staging()
            target = staging.native_path / "unsafe"
            if kind == "symlink":
                target.symlink_to(staging.native_path / "data.mdb")
            elif kind == "hardlink":
                os.link(staging.native_path / "data.mdb", target)
            else:
                os.mkfifo(target)
            self.assert_code("UNSAFE_ARTIFACT", lambda: self.store.publish_staging(
                staging.token, metadata=self.metadata, official_save_completed=True,
                required_native_files=["data.mdb"]))
            self.store.discard_staging(staging.token)
        self.store.max_native_bytes = 1
        self.assert_code("PACKAGE_LIMIT", self.publish)
        self.assertEqual(self.store.list_packages(), [])

    def test_exact_preview_needs_matching_native_snapshot_evidence(self):
        self.assert_code("SNAPSHOT_MISMATCH", lambda: self.publish(preview_consistency="exact"))
        metadata = {**self.metadata, "native_snapshot_id": "native-snapshot-7"}
        preview = {**self.preview, "native_snapshot_id": "native-snapshot-7"}
        package = self.publish(metadata=metadata, preview=preview, preview_consistency="exact")
        self.assertEqual(package["preview_consistency"], "exact")

    def test_rename_identity_native_bytes_stale_revision_and_active_reference(self):
        package = self.publish()
        before = self.native_bytes(package)
        token = self.store.acquire_reference(package["id"], expected_revision=package["revision"],
                                             purpose="linked_navigation_map")
        self.assert_code("PACKAGE_IN_USE", lambda: self.store.rename_package(
            package["id"], name="Other", expected_revision=package["revision"]))
        self.assert_code("PACKAGE_IN_USE", lambda: self.store.delete_package(
            package["id"], expected_revision=package["revision"]))
        self.store.release_reference(token)
        renamed = self.store.rename_package(package["id"], name="새 지도", expected_revision=package["revision"])
        self.assertEqual(renamed["id"], package["id"])
        self.assertEqual(renamed["name"], "새 지도")
        self.assertEqual(renamed["native_content_revision"], package["native_content_revision"])
        self.assertEqual(renamed["preview_revision"], package["preview_revision"])
        self.assertNotEqual(renamed["revision"], package["revision"])
        self.assertEqual(self.native_bytes(renamed), before)
        self.assert_code("REVISION_CONFLICT", lambda: self.store.delete_package(
            package["id"], expected_revision=package["revision"]))
        result = self.store.delete_package(renamed["id"], expected_revision=renamed["revision"])
        self.assertEqual(result["cleanup"], "complete")
        self.assertEqual(self.store.list_packages(), [])

    def test_copy_export_import_preserve_native_hashes_and_reset_validation(self):
        package = self.publish()
        copied = self.store.copy_package(package["id"], name="Copy", expected_revision=package["revision"])
        self.assertNotEqual(copied["id"], package["id"])
        self.assertEqual(copied["native_content_revision"], package["native_content_revision"])
        self.assertEqual(self.native_bytes(copied), self.native_bytes(package))
        imported = self.store.import_package(self.archive(package), name="Imported")
        self.assertNotEqual(imported["id"], package["id"])
        self.assertEqual(imported["native_content_revision"], package["native_content_revision"])
        self.assertEqual(self.native_bytes(imported), self.native_bytes(package))
        self.assertEqual(imported["save_completion"]["evidence"], "imported_manifest_integrity_only")
        self.assertEqual(imported["validation"]["localization_success"], "unknown")
        self.assertEqual(self.store.get_preview(imported["id"]), self.preview)
        self.assertEqual(len(self.store.list_packages()), 3)

    def test_compatibility_defaults_blocked_and_scratch_never_modifies_original(self):
        package = self.publish()
        runtime = {key: self.metadata[key] for key in ("engine_id", "engine_version",
                  "native_format_version", "calibration_hash", "sensor_config_hash")}
        self.assertEqual(self.store.compatibility(package["id"], runtime={})["status"], "blocked")
        for field in runtime:
            incompatible = {**runtime, field: "other"}
            self.assert_code("MAP_INCOMPATIBLE", lambda: self.store.prepare_load(
                package["id"], expected_revision=package["revision"], runtime=incompatible))
        scratch = self.store.prepare_load(package["id"], expected_revision=package["revision"], runtime=runtime)
        before = self.native_bytes(package)
        (scratch.native_path / "data.mdb").write_bytes(b"native engine may update scratch")
        self.assertEqual(self.native_bytes(package), before)
        self.assert_code("PACKAGE_IN_USE", lambda: self.store.delete_package(
            package["id"], expected_revision=package["revision"]))
        self.store.release_scratch(scratch.scratch_id)
        self.assertFalse(scratch.native_path.exists())
        self.store.delete_package(package["id"], expected_revision=package["revision"])

    def test_native_integrity_tamper_blocks_load_copy_and_export(self):
        package = self.publish()
        native = self.store.root / "packages" / package["id"] / "native" / "data.mdb"
        native.write_bytes(b"tampered")
        for action in (
            lambda: self.store.copy_package(package["id"], expected_revision=package["revision"]),
            lambda: self.store.export_package(package["id"], expected_revision=package["revision"]),
            lambda: self.store.prepare_load(package["id"], expected_revision=package["revision"], runtime=self.metadata),
        ):
            self.assert_code("INVALID_PACKAGE", action)

    def test_zip_traversal_absolute_windows_links_special_duplicate_entries_rejected(self):
        for name in ("../escape", "/tmp/escape", "native/../../escape", "C:/escape",
                     "native\\escape", "native//escape", "native/./escape"):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr(name, b"malicious")
            self.assert_code("UNSAFE_ARCHIVE", lambda: self.store.import_package(output.getvalue()))
        for mode in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR, stat.S_IFDIR):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                info = zipfile.ZipInfo("native/bad")
                info.create_system = 3
                info.external_attr = (mode | 0o600) << 16
                archive.writestr(info, b"target")
            self.assert_code("UNSAFE_ARCHIVE", lambda: self.store.import_package(output.getvalue()))
        package = self.publish()
        raw = self.archive(package)
        output = io.BytesIO(raw)
        with zipfile.ZipFile(output, "a") as archive:
            with self.assertWarns(UserWarning):
                archive.writestr("manifest.json", b"{}")
        self.assert_code("UNSAFE_ARCHIVE", lambda: self.store.import_package(output.getvalue()))
        self.assertEqual(len(self.store.list_packages()), 1)

    def test_zip_bombs_count_bytes_invalid_metadata_and_hashes_rejected(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("native/bomb", b"0" * 100_000)
        self.assert_code("PACKAGE_LIMIT", lambda: self.store.import_package(output.getvalue()))
        package = self.publish()
        raw = self.archive(package)
        corrupted = self.rewrite_archive(raw, lambda entries: entries.__setitem__("native/data.mdb", b"tampered"))
        self.assert_code("INVALID_PACKAGE", lambda: self.store.import_package(corrupted))
        self.store.max_archive_bytes = 1
        self.assert_code("PACKAGE_LIMIT", lambda: self.store.import_package(raw))
        self.store.max_archive_bytes = len(raw) * 2
        self.store.max_files = 1
        self.assert_code("PACKAGE_LIMIT", lambda: self.store.import_package(raw))
        self.store.max_files = 4096
        self.assertEqual(len(self.store.list_packages()), 1)
        self.assertEqual(list((self.store.root / "staging").iterdir()), [])

    def test_rehashed_but_malformed_import_manifest_is_rejected_without_crashing(self):
        package = self.publish()
        raw = self.archive(package)
        mutations = (
            lambda manifest: manifest.pop("preview_revision"),
            lambda manifest: manifest.pop("name"),
            lambda manifest: manifest.__setitem__("units", []),
            lambda manifest: manifest.__setitem__("metadata_generation", True),
            lambda manifest: manifest.__setitem__("native_artifacts", [{"path": []}]),
        )
        for mutation in mutations:
            def change(entries):
                manifest = json.loads(entries["manifest.json"])
                mutation(manifest)
                manifest["revision"] = self.store._revision(manifest)
                entries["manifest.json"] = json.dumps(manifest).encode()
            malformed = self.rewrite_archive(raw, change)
            with self.assertRaises(MapPackageError):
                self.store.import_package(malformed)
        self.assertEqual(len(self.store.list_packages()), 1)

    def test_archive_directory_count_checked_before_eager_zip_parser(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for index in range(8):
                archive.writestr(f"native/{index}.bin", b"x")
        raw = bytearray(output.getvalue())
        end = raw.rfind(b"PK\x05\x06")
        # A false EOCD count must not bypass the actual central-record budget.
        struct.pack_into("<HH", raw, end + 8, 1, 1)
        self.store.max_files = 2
        with patch("robot_dashboard.slam_packages.zipfile.ZipFile") as eager_parser:
            self.assert_code("PACKAGE_LIMIT", lambda: self.store.import_package(bytes(raw)))
            eager_parser.assert_not_called()

    def test_archive_unix_hardlink_metadata_rejected(self):
        for field in (0x000D, 0x756E):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                info = zipfile.ZipInfo("native/linked")
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                info.extra = struct.pack("<HH", field, 4) + b"link"
                archive.writestr(info, b"target")
            self.assert_code("UNSAFE_ARCHIVE", lambda: self.store.import_package(output.getvalue()))

    def test_invalid_package_ids_names_and_nan_preview_rejected(self):
        for value in ("../../outside", "/tmp", "np_abc", None):
            self.assert_code("PACKAGE_NOT_FOUND", lambda: self.store.get_package(value))
        package = self.publish()
        for name in ("", "\x00secret", "a" * 121, 7):
            self.assert_code("INVALID_NAME", lambda: self.store.rename_package(
                package["id"], name=name, expected_revision=package["revision"]))
        self.assert_code("INVALID_METADATA", lambda: self.publish(preview={"x": float("nan")}))

    def test_public_root_permissions_rejected_and_reopen_catalog_works(self):
        exposed = self.root / "exposed"
        exposed.mkdir(mode=0o755)
        self.assert_code("UNSAFE_ROOT", lambda: MapPackageStore(exposed))
        package = self.publish()
        reopened = MapPackageStore(self.store.root, quiescence_seconds=0.001)
        self.assertEqual(reopened.get_package(package["id"])["revision"], package["revision"])
        self.assertEqual(len(reopened.list_packages()), 1)


if __name__ == "__main__":
    unittest.main()
