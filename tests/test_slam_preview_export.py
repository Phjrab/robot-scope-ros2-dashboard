"""Saved snapshot exports: synthetic fixtures, no runtime or native DB decoding."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from robot_dashboard.slam_packages import MapPackageError, MapPackageStore
from robot_dashboard.slam_preview_export import PreviewExportError, preview_export_files


def snapshot():
    return dict(frame_id="vslam_lab_map", map_epoch="epoch-a", session_id="session-a",
        generation=1, engine_id="visual_stereo",
        global_map=dict(points=[[1.23456789012345, -2, 3], [4, 5, 6]],
            coordinate_frame="vslam_lab_map", map_epoch="epoch-a", coverage="unknown",
            source_timestamp_ns="1792144977080785000", source_id="/native/landmarks",
            provenance="native_visualization", decimation=False),
        trajectory=dict(points=[[0, 0, 0], [1, 2, 3]], coordinate_frame="vslam_lab_map",
            map_epoch="epoch-a", source_timestamp_ns="1792145026398794752",
            source_id="/native/slam_path", provenance="bounded_slam_path"),
        camera_pose=dict(position=[1, 2, 3], quaternion_xyzw=[0, 0, 0, 1],
            frame_id="vslam_lab_map", pose_reference="vslam_lab_camera_link",
            source_topic="/native/slam_odometry", stamp_ns="1792145026398794752"))


class SavedPreviewExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = MapPackageStore(Path(self.temporary.name) / "managed", quiescence_seconds=0.001)
        staging = self.store.create_staging()
        self.native = b"synthetic native bytes must remain unchanged"
        (staging.native_path / "data.mdb").write_bytes(self.native)
        self.preview = snapshot()
        self.package = self.store.publish_staging(staging.token, metadata={
            "name": "Saved fixture", "engine_id": "visual_stereo", "map_frame": "vslam_lab_map",
            "data_provenance": "synthetic_fixture"}, official_save_completed=True,
            required_native_files=["data.mdb"], preview=self.preview)
        self.manifest = self.store._manifest(self.package["id"])

    def tearDown(self):
        self.temporary.cleanup()

    def export(self):
        handle, metadata = self.store.export_preview(self.package["id"],
            expected_revision=self.package["revision"])
        try:
            self.assertEqual(stat.S_IMODE(os.fstat(handle.fileno()).st_mode), 0o600)
            with zipfile.ZipFile(handle) as archive:
                self.assertIsNone(archive.testzip())
                self.assertTrue(all(stat.S_IMODE(info.external_attr >> 16) == 0o600 for info in archive.infolist()))
                files = {name: archive.read(name) for name in archive.namelist()}
            return files, metadata
        finally:
            handle.close()

    def test_derived_rows_and_hashes_preserve_saved_sources_without_native_access(self):
        with patch.object(self.store, "_verify_native", side_effect=AssertionError("native read")):
            files, metadata = self.export()
        self.assertEqual(set(files), {"global-map.xyz", "trajectory.csv", "camera-pose.csv", "provenance.json"})
        xyz = [[float(x) for x in line.split()] for line in files["global-map.xyz"].decode().splitlines()]
        self.assertEqual(xyz, self.preview["global_map"]["points"])
        trajectory = list(csv.DictReader(io.StringIO(files["trajectory.csv"].decode())))
        self.assertEqual([[float(row[k]) for k in ("x", "y", "z")] for row in trajectory], self.preview["trajectory"]["points"])
        self.assertEqual(len(list(csv.DictReader(io.StringIO(files["camera-pose.csv"].decode())))), 1)
        provenance = json.loads(files["provenance.json"])
        self.assertEqual(provenance["revision"], self.package["revision"])
        self.assertEqual(provenance["preview_revision"], self.package["preview_revision"])
        self.assertEqual(provenance["preview_consistency"], "approximate")
        self.assertIsNone(provenance["preview_capture_time"])
        self.assertEqual(provenance["units"], "unknown")
        self.assertEqual(provenance["data_provenance"], "synthetic_fixture")
        self.assertFalse(provenance["native_full_map_export"])
        self.assertFalse(provenance["native_completeness_verified"])
        self.assertEqual(provenance["layers"]["global_map"]["source_timestamp_ns"], "1792144977080785000")
        self.assertEqual(provenance["layers"]["trajectory"]["exported_rows"], 2)
        self.assertIsNone(provenance["layers"]["trajectory"]["source_declared_decimation"])
        for name, record in provenance["files"].items():
            self.assertEqual(record, dict(bytes=len(files[name]), sha256=hashlib.sha256(files[name]).hexdigest()))
        self.assertGreater(metadata["bytes"], 0)
        self.assertEqual(self.store.get_preview(self.package["id"]), self.preview)
        native = self.store.root / "packages" / self.package["id"] / "native" / "data.mdb"
        self.assertEqual(native.read_bytes(), self.native)

    def test_missing_layers_and_untrusted_completeness_never_create_points_ids_or_total(self):
        preview = snapshot()
        preview["global_map"].update(coverage="complete", engine_total_count=2, native_ids_available=True)
        preview.pop("trajectory")
        preview.pop("camera_pose")
        files = preview_export_files(self.manifest, preview, max_bytes=100_000)
        provenance = json.loads(files["provenance.json"])
        layer = provenance["layers"]["global_map"]
        self.assertEqual(layer["source_declared_coverage"], "complete")
        self.assertEqual(layer["coverage"], "unknown")
        self.assertIsNone(layer["engine_total_count"])
        self.assertFalse(layer["native_ids_exported"])
        self.assertEqual(set(files), {"global-map.xyz", "provenance.json"})
        self.assertFalse(provenance["layers"]["trajectory"]["available"])
        preview["global_map"]["coverage"] = "subset"
        subset = preview_export_files(self.manifest, preview, max_bytes=100_000)
        self.assertEqual(json.loads(subset["provenance.json"])["layers"]["global_map"]["coverage"], "subset")
        preview.pop("global_map")
        with self.assertRaisesRegex(PreviewExportError, "PREVIEW_EXPORT_UNAVAILABLE"):
            preview_export_files(self.manifest, preview, max_bytes=100_000)

    def test_invalid_coordinates_context_and_csv_identifiers_fail_atomically(self):
        cases = []
        for value in (float("nan"), float("inf"), True, 1_000_001, 10**400, "2"):
            preview = snapshot()
            preview["global_map"]["points"][0][0] = value
            cases.append(preview)
        for key, value in (("coordinate_frame", "other"), ("map_epoch", "other"), ("points", [[1, 2]])):
            preview = snapshot()
            preview["trajectory"][key] = value
            cases.append(preview)
        preview = snapshot()
        preview["global_map"]["points"] = [[0, 0, 0]] * 60_001
        cases.append(preview)
        preview = snapshot()
        preview["camera_pose"]["pose_reference"] = "=FORMULA()"
        cases.append(preview)
        preview = snapshot()
        preview["camera_pose"]["quaternion_xyzw"] = [0, 0, 0, 0]
        cases.append(preview)
        preview = snapshot()
        preview["generation"] = True
        cases.append(preview)
        preview = snapshot()
        preview["engine_id"] = "another_engine"
        cases.append(preview)
        for preview in cases:
            with self.subTest(case=len(cases)), self.assertRaisesRegex(PreviewExportError, "INVALID_PREVIEW_EXPORT"):
                preview_export_files(self.manifest, preview, max_bytes=100_000)
        self.assertEqual(self.preview, snapshot())

    def test_revision_preview_integrity_and_output_limits_are_enforced(self):
        with self.assertRaises(MapPackageError) as raised:
            self.store.export_preview(self.package["id"], expected_revision="0" * 64)
        self.assertEqual(raised.exception.code, "REVISION_CONFLICT")
        with self.assertRaisesRegex(PreviewExportError, "PACKAGE_LIMIT"):
            preview_export_files(self.manifest, self.preview, max_bytes=10)
        preview_path = self.store.root / "packages" / self.package["id"] / "preview" / "snapshot.json"
        preview_path.write_text("{}")
        with self.assertRaises(MapPackageError) as raised:
            self.store.export_preview(self.package["id"], expected_revision=self.package["revision"])
        self.assertEqual(raised.exception.code, "INVALID_PACKAGE")

    def test_optional_camera_pose_context_matches_snapshot_without_requiring_legacy_fields(self):
        baseline = preview_export_files(self.manifest, self.preview, max_bytes=100_000)
        matching = snapshot()
        context = dict(coordinate_frame=matching["frame_id"], map_epoch=matching["map_epoch"],
            session_id=matching["session_id"], generation=matching["generation"],
            engine_id=matching["engine_id"])
        matching["camera_pose"].update(context)
        files = preview_export_files(self.manifest, matching, max_bytes=100_000)
        self.assertEqual(files, baseline)
        for key, value in (("frame_id", "other-map"), ("coordinate_frame", "other-map"),
                ("map_epoch", "other-epoch"), ("session_id", "other-session"),
                ("generation", 2), ("generation", True), ("generation", "1"),
                ("generation", None), ("engine_id", "other-engine")):
            preview = snapshot()
            preview["camera_pose"][key] = value
            with self.subTest(key=key, value=value), self.assertRaisesRegex(PreviewExportError, "INVALID_PREVIEW_EXPORT"):
                preview_export_files(self.manifest, preview, max_bytes=100_000)
        legacy = snapshot()
        for key in ("session_id", "generation", "engine_id"):
            legacy.pop(key)
        legacy_files = preview_export_files(self.manifest, legacy, max_bytes=100_000)
        self.assertEqual(legacy_files["camera-pose.csv"], baseline["camera-pose.csv"])
        self.assertEqual(self.preview, snapshot())

    def test_native_archive_members_and_roundtrip_are_unchanged(self):
        handle, _ = self.store.export_package(self.package["id"], expected_revision=self.package["revision"])
        try:
            raw = handle.read()
        finally:
            handle.close()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertEqual(set(archive.namelist()), {"manifest.json", "native/data.mdb", "preview/snapshot.json"})
        imported = self.store.import_package(raw)
        self.assertEqual(self.store.get_preview(imported["id"]), self.preview)
        self.assertEqual(imported["native_content_revision"], self.package["native_content_revision"])
