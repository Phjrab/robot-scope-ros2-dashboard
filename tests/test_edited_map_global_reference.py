"""Synthetic semantic-revision binding for immutable edited PCD observations."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from robot_dashboard.application.global_observation import GlobalObservationCoordinator
from robot_dashboard.saved_maps import SavedMapCatalog, SavedMapConflict, SavedMapFormatError


POINTS = (
    (0.0, 0.0, 0.0, (1.0, 2.0, 3.0), 11),
    (2.0, 1.0, 0.5, (4.0, 5.0, 6.0), 12),
    (-3.0, 2.0, 1.0, (7.0, 8.0, 9.0), 13),
    (0.0, 0.0, 3.0, (10.0, 11.0, 12.0), 14),
)


def make_pcd(rows):
    header = (
        "VERSION 0.7\nFIELDS x y z histogram stamp\n"
        "SIZE 8 8 8 4 8\nTYPE F F F F U\nCOUNT 1 1 1 3 1\n"
        f"WIDTH {len(rows)}\nHEIGHT 1\nPOINTS {len(rows)}\nDATA binary\n"
    ).encode("ascii")
    return header + b"".join(
        struct.pack("<dddfffQ", x, y, z, *histogram, stamp)
        for x, y, z, histogram, stamp in rows
    )


def edit_request(descriptor, *, name="edited-one", version="synthetic-v1", polygon=None):
    polygon = polygon or [[-.5, -.5], [.5, -.5], [.5, .5], [-.5, .5]]
    return {
        "schema": "robot-scope.pcd-edit-request.v1",
        "name": name, "purpose": "localization", "source": descriptor,
        "annotation": {
            "schema": "robot-dashboard.map-editor3d", "schema_version": 1,
            "version_id": version,
            "source": {key: descriptor[key] for key in ("map_id", "revision", "frame_id")},
            "runtime_installed": False,
            "regions": [{"kind": "localization", "selection": "inside",
                         "polygon": polygon, "z_min": -1.0, "z_max": 1.0}],
        },
    }


class LocalScanAgent:
    """Synthetic capture only; no ROS, network or robot control."""

    def __init__(self):
        self.epoch = "epoch-one"
        self.stamp = "1792380422951489687"

    def raw_pointcloud_context_snapshot(self):
        return {"topic": "/synthetic/raw", "frame_id": "synthetic_lidar",
                "pipeline_stage": "raw", "observation": {
                    "observer_id": "synthetic-observer", "publisher_epoch": self.epoch,
                    "source_stamp_ns": self.stamp, "received_monotonic_s": time.monotonic()}}

    def request_raw_pointcloud_capture(self, **kwargs):
        return {"capture_id": "synthetic-capture"}

    def raw_pointcloud_capture_snapshot(self, capture_id):
        return {"capture_id": capture_id, "state": "ready"}

    def take_raw_pointcloud_capture(self, capture_id):
        packed = struct.pack("<ddd", 1., 2., 3.)
        return {"xyz_bytes": packed, "xyz_sha256": hashlib.sha256(packed).hexdigest(),
                "encoding": "float64_le_xyz", "captured_points": 1, "source_points": 1,
                "source_frame": "synthetic_lidar", "source_stamp_ns": self.stamp,
                "topic": "/synthetic/raw", "observer_epoch": self.epoch,
                "pipeline_stage": "raw",
                "observation": self.raw_pointcloud_context_snapshot()["observation"],
                "received_monotonic_s": time.monotonic(),
                "receipt_clock": "OBSERVER_HOST_MONOTONIC", "units": "m"}

    def cancel_raw_pointcloud_capture(self, capture_id):
        return None


class LocalObservationRunner:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.context = None

    def status(self):
        return {"available": True, "backend_id": "synthetic-only"}

    def run_arrays(self, *, scan_bytes, map_bytes, context, cancel_event):
        self.context = context
        self.entered.set()
        self.release.wait(2.)
        return {"status": "OBSERVATION_ONLY_UNVERIFIED", "selected_candidate": None,
                "candidates": [], "source_stamp_ns": context["source_stamp_ns"]}


class EditedGlobalReferenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source.pcd"
        self.source.write_bytes(make_pcd(POINTS))
        self.catalogue = SavedMapCatalog([self.root], managed_roots=[self.root])
        self.legacy = self.catalogue.list_snapshot()["maps"][0]

    def make_edited(self, *, frame="survey_origin"):
        original_resolver = self.catalogue._pcd_edit_source_asset
        with patch.object(self.catalogue, "_pcd_edit_source_asset",
                          side_effect=lambda map_id: replace(original_resolver(map_id), frame_id=frame)):
            descriptor = self.catalogue.pcd_edit_source(self.legacy["id"])
            result = self.catalogue.save_pcd_edited_copy(
                self.legacy["id"], edit_request(descriptor))
        return descriptor, result

    def test_legacy_signature_revision_and_default_frame_stay_unchanged(self):
        raw = self.catalogue.raw_global_reference(self.legacy["id"], self.legacy["revision"])
        self.assertEqual(raw["map_revision"], self.legacy["revision"])
        self.assertEqual(raw["source_sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(raw["frame_id"], "camera_init")
        self.assertEqual(raw["frame_basis"], "PCD_PRODUCT_DEFAULT_UNVERIFIED")
        self.assertNotIn("reference_provenance", raw)
        self.assertEqual(np.frombuffer(raw["xyz_bytes"], dtype="<f8").reshape(-1, 3).tolist(),
                         [list(row[:3]) for row in POINTS])

    def test_edited_semantic_revision_full_population_frame_and_lineage(self):
        before = self.source.read_bytes()
        descriptor, edited = self.make_edited()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertNotEqual(edited["revision"], self.catalogue._signature_revision(
            (self.root / "pcd-edits" / edited["id"] / "map.pcd",)))
        with self.assertRaises(SavedMapConflict):
            self.catalogue.raw_global_reference(
                edited["id"], self.catalogue._signature_revision(
                    (self.root / "pcd-edits" / edited["id"] / "map.pcd",)))
        raw = self.catalogue.raw_global_reference(edited["id"], edited["revision"])
        self.assertEqual(raw["map_id"], edited["id"])
        self.assertEqual(raw["map_revision"], edited["revision"])
        self.assertEqual(raw["source_sha256"], edited["sha256"])
        self.assertEqual(raw["frame_id"], "survey_origin")
        self.assertEqual(raw["frame_basis"], "PCD_EDIT_MANIFEST_DECLARED_UNVERIFIED")
        self.assertEqual(raw["units"], "m")
        self.assertEqual(raw["units_basis"], "PCD_EDIT_MANIFEST_DECLARED_UNVERIFIED")
        self.assertEqual(raw["point_count"], 3)
        self.assertEqual(np.frombuffer(raw["xyz_bytes"], dtype="<f8").reshape(-1, 3).tolist(),
                         [list(row[:3]) for row in POINTS[1:]])
        self.assertFalse(raw["sampling_applied"])
        self.assertFalse(raw["spatial_filter_applied"])
        provenance = raw["reference_provenance"]
        self.assertEqual(provenance["asset_role"], "EDITED_FULL_SOURCE")
        self.assertEqual(provenance["scoring_population"], "THIS_EDITED_MAP_COMPLETE_XYZ")
        self.assertEqual(provenance["direct_parent"], {
            key: descriptor[key] for key in ("map_id", "revision", "sha256")})
        self.assertEqual(provenance["original_root"], provenance["direct_parent"])
        self.assertFalse(provenance["parent_score_comparable"])
        self.assertEqual(set(provenance), {"asset_role", "scoring_population", "direct_parent",
                                           "original_root", "parent_score_comparable"})

        fresh = SavedMapCatalog([self.root], managed_roots=[self.root])
        self.assertIn(edited["id"], {item["id"] for item in fresh.list_snapshot()["maps"]})
        preview = fresh.data(edited["id"], max_points=None)
        self.assertEqual(preview["revision"], edited["revision"])
        self.assertEqual(preview["frame_id"], "survey_origin")
        self.assertEqual((preview["source_points"], preview["sent_points"]), (3, 3))
        self.assertEqual(np.asarray(preview["points"]).reshape(-1, 3).tolist(),
                         [list(row[:3]) for row in POINTS[1:]])
        limited_preview = fresh.data(edited["id"], max_points=2)
        self.assertEqual(limited_preview["source_points"], 3)
        self.assertEqual(limited_preview["sent_points"], 2)
        child_descriptor = fresh.pcd_edit_source(edited["id"])
        child = fresh.save_pcd_edited_copy(edited["id"], edit_request(
            child_descriptor, name="edited-two", version="synthetic-v2",
            polygon=[[20., 20.], [21., 20.], [21., 21.], [20., 21.]]))
        child_raw = fresh.raw_global_reference(child["id"], child["revision"])
        self.assertEqual(child_raw["point_count"], raw["point_count"])
        self.assertEqual(child_raw["frame_id"], "survey_origin")
        self.assertEqual(child_raw["reference_provenance"]["direct_parent"], {
            key: child_descriptor[key] for key in ("map_id", "revision", "sha256")})
        self.assertEqual(child_raw["reference_provenance"]["original_root"],
                         provenance["original_root"])
        self.assertNotIn("edit_history", child_raw["reference_provenance"])

    def test_stale_revision_and_hash_tamper_fail_closed(self):
        _, edited = self.make_edited()
        with self.assertRaises(SavedMapConflict):
            self.catalogue.raw_global_reference(edited["id"], "0" * 64)
        original_read = self.catalogue._read_download_source

        def changed_snapshot(path, signature):
            value = bytearray(original_read(path, signature))
            value[-1] ^= 1
            return bytes(value)

        with patch.object(self.catalogue, "_read_download_source", side_effect=changed_snapshot):
            with self.assertRaisesRegex(SavedMapConflict, "hash changed"):
                self.catalogue.raw_global_reference(edited["id"], edited["revision"])

        def changed_manifest(path, signature):
            value = original_read(path, signature)
            manifest = path.parent / "manifest.json"
            document = json.loads(manifest.read_text())
            document["frame_id"] = "wrong_frame"
            manifest.write_text(json.dumps(document))
            return value

        with patch.object(self.catalogue, "_read_download_source", side_effect=changed_manifest):
            with self.assertRaisesRegex(SavedMapConflict, "manifest changed"):
                self.catalogue.raw_global_reference(edited["id"], edited["revision"])

    def test_multi_count_attribute_and_nonfinite_rows_are_preserved(self):
        # The editor preserves a multi-count non-XYZ field, and no nonfinite
        # source row is silently omitted from the raw reference.
        rows = list(POINTS)
        rows[2] = (float("nan"), 2.0, 1.0, (7.0, 8.0, 9.0), 13)
        self.source.write_bytes(make_pcd(rows))
        self.catalogue = SavedMapCatalog([self.root], managed_roots=[self.root])
        self.legacy = self.catalogue.list_snapshot()["maps"][0]
        _, edited = self.make_edited()
        raw = self.catalogue.raw_global_reference(edited["id"], edited["revision"])
        xyz = np.frombuffer(raw["xyz_bytes"], dtype="<f8").reshape(-1, 3)
        self.assertEqual(len(xyz), 3)
        self.assertTrue(np.isnan(xyz[1, 0]))
        self.assertTrue(raw["nonfinite_rows_preserved"])

    def test_multi_count_xyz_is_rejected_instead_of_reinterpreted(self):
        self.source.write_bytes((
            "VERSION 0.7\nFIELDS x y z\nSIZE 8 8 8\nTYPE F F F\n"
            "COUNT 2 1 1\nWIDTH 1\nHEIGHT 1\nPOINTS 1\nDATA binary\n"
        ).encode() + struct.pack("<dddd", 1., 2., 3., 4.))
        self.catalogue = SavedMapCatalog([self.root], managed_roots=[self.root])
        metadata = self.catalogue.list_snapshot()["maps"][0]
        with self.assertRaises(SavedMapFormatError):
            self.catalogue.raw_global_reference(metadata["id"], metadata["revision"])
        with self.assertRaises(SavedMapFormatError):
            self.catalogue.data(metadata["id"], max_points=1)

    def test_edited_reference_job_binds_metadata_and_epoch_without_promotion(self):
        _, edited = self.make_edited()
        agent, runner = LocalScanAgent(), LocalObservationRunner()
        owner = GlobalObservationCoordinator(self.catalogue, agent, runner)
        self.addCleanup(lambda: (runner.release.set(), owner.close()))
        job = owner.start("edited-synthetic", edited["id"], edited["revision"])
        self.assertTrue(runner.entered.wait(1.), owner.job(job["job_id"]))
        context = runner.context
        self.assertEqual(context["map_id"], edited["id"])
        self.assertEqual(context["map_revision"], edited["revision"])
        self.assertEqual(context["map_frame"], "survey_origin")
        self.assertEqual(context["map"]["source_sha256"], edited["sha256"])
        self.assertEqual(context["map"]["frame_id"], "survey_origin")
        self.assertEqual(context["map"]["units"], "m")
        self.assertEqual(context["map"]["reference_provenance"]["asset_role"],
                         "EDITED_FULL_SOURCE")
        self.assertNotIn("edit_history", context["map"])
        agent.epoch = "epoch-two"
        runner.release.set()
        for _ in range(200):
            result = owner.job(job["job_id"])
            if not result["worker_active"]:
                break
            time.sleep(.005)
        self.assertFalse(result["worker_active"])
        self.assertEqual(result["state"], "stale")
        self.assertIsNone(result["result"])
        self.assertIsNone(result["current_result"])
        self.assertFalse(result["tracking_verified"])


if __name__ == "__main__":
    unittest.main()
