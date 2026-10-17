"""Offline fixtures only: no SDK, ROS, camera, HTTP or robot is used."""
from copy import deepcopy
import io
import json
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

from robot_dashboard.depth_capture_store import DepthCaptureError, DepthCaptureStore


def capture_fixture():
    intrinsics = {"width": 2, "height": 2, "fx": 100.0, "fy": 101.0,
                  "ppx": .5, "ppy": .5, "model": "distortion.none", "coeffs": [0.0]*5}

    def frame(stream, index, fmt, stride, raw):
        return {"width": 2, "height": 2, "stride_bytes": stride, "bytes_per_pixel": 1 if fmt == "Y8" else 2,
                "format": fmt, "byte_order": "not_applicable" if fmt == "Y8" else "little",
                "frame_id": "realsense_ir1_optical" if fmt == "Y8" else "realsense_depth_optical",
                "frame_id_source": "sdk_logical_optical_not_ros_tf", "frame_number": 17,
                "timestamp_ms": 1234.0, "timestamp_domain": "timestamp_domain.hardware_clock",
                "profile": {"width": 2, "height": 2, "fps": 30, "format": fmt, "stream": stream,
                            "index": index, "unique_id": 42+index},
                "intrinsics": deepcopy(intrinsics), "metadata": {"actual_exposure": 6000}, "data": raw}
    return {"schema_version": 1, "session_id": "fixture-session", "generation": 1,
            "captured_at_utc": "2026-10-17T00:00:00+00:00",
            "device": {"serial": "FIXTURE-NOT-A-DEVICE", "name": "fixture D435i", "firmware": "fixture"},
            "depth_scale_m": .001, "confirmation": {"robot_stationary": True, "camera_stationary": True, "robot_seated": True},
            "body_attitude": {"available": False, "reason": "not provided"},
            "frameset": {"verified": True, "ir_frame_number": 17, "depth_frame_number": 17},
            "extrinsics": {"depth_to_ir1": {"rotation": [1, 0, 0, 0, 1, 0, 0, 0, 1], "translation": [0, 0, 0]}},
            "frames": {"ir1": frame("infrared", 1, "Y8", 3, bytes([1, 2, 99, 3, 4, 98])),
                       "depth": frame("depth", 0, "Z16", 6, struct.pack("<6H", 0, 1000, 12345, 2000, 65535, 23456))}}


def png_pixels(raw):
    """Inspect original PNG dimensions/type and inflated filter-zero rows."""
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("not PNG")
    cursor, payload, header = 8, bytearray(), None
    while cursor < len(raw):
        length = struct.unpack_from(">I", raw, cursor)[0]
        kind = raw[cursor+4:cursor+8]
        data = raw[cursor+8:cursor+8+length]
        crc = struct.unpack_from(">I", raw, cursor+8+length)[0]
        if crc != zlib.crc32(kind+data)&0xffffffff:
            raise AssertionError("CRC mismatch")
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", data)
        if kind == b"IDAT":
            payload.extend(data)
        cursor += 12+length
    return header, zlib.decompress(payload)


class DepthCaptureStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()/"private-depth"
        self.store = DepthCaptureStore(self.root, minimum_free_bytes=0)

    def assert_raw_only(self, capture, reason):
        receipt = self.store.save_sample(capture)
        self.assertEqual(receipt["compatibility"], {"available": False, "reason": reason})
        with zipfile.ZipFile(io.BytesIO(self.store.export_zip(receipt["sample_id"]))) as archive:
            self.assertEqual(archive.read("ir1.y8"), capture["frames"]["ir1"]["data"])
            if capture["frames"].get("depth", {}).get("data") is not None:
                self.assertEqual(archive.read("depth.z16"), capture["frames"]["depth"]["data"])
            self.assertNotIn("compatibility.json", archive.namelist())
        with self.assertRaises(DepthCaptureError) as caught:
            self.store.compatibility_json(receipt["sample_id"])
        self.assertEqual(caught.exception.code, "COMPATIBILITY_UNAVAILABLE")
        return receipt

    def test_exact_original_bytes_lossless_png_and_flat_optical_z_compatibility(self):
        capture = capture_fixture()
        receipt = self.store.save_sample(capture)
        sample_id = receipt["sample_id"]
        self.assertRegex(sample_id, r"^[0-9a-f]{32}$")
        self.assertEqual(receipt["compatibility"], {"available": True, "reason": None})
        self.assertEqual(receipt["image"]["width"], 2)
        self.assertEqual(receipt["image"]["frame_id_source"], "sdk_logical_optical_not_ros_tf")
        self.assertEqual(receipt["valid_depth_ratio"], .75)
        self.assertEqual(receipt["actual_source_skew_ms"], 0)
        compatible = self.store.compatibility_json(sample_id)
        self.assertEqual(compatible["depth_m"], [None, 1.0, 2.0, 65.535])
        self.assertEqual(compatible["metadata"]["source_timestamp"], 1.234)
        self.assertEqual(compatible["metadata"]["source_timestamp_unit"], "seconds")
        self.assertEqual(compatible["metadata"]["clock_domain"], capture["frames"]["ir1"]["timestamp_domain"])
        self.assertEqual(compatible["points"], [])
        self.assertIs(compatible["metadata"]["synthetic"], False)
        self.assertEqual(compatible["metadata"]["depth_semantics"], "optical_z")
        self.assertEqual(compatible["intrinsics"], {"fx": 100.0, "fy": 101.0, "cx": .5, "cy": .5})
        self.assertEqual(png_pixels(self.store.click_png(sample_id)), ((2, 2, 8, 0, 0, 0, 0), b"\0\1\2\0\3\4"))
        with zipfile.ZipFile(io.BytesIO(self.store.export_zip(sample_id))) as archive:
            self.assertEqual(archive.read("ir1.y8"), capture["frames"]["ir1"]["data"])
            self.assertEqual(archive.read("depth.z16"), capture["frames"]["depth"]["data"])
            self.assertEqual(png_pixels(archive.read("depth.png")), ((2, 2, 16, 0, 0, 0, 0), b"\0\0\0\3\xe8\0\7\xd0\xff\xff"))
            metadata = json.loads(archive.read("metadata.json"))
            expected = deepcopy(capture)
            for frame in expected["frames"].values():
                frame.pop("data")
            self.assertEqual({key: metadata[key] for key in expected}, expected)
            self.assertEqual(metadata["sample_id"], sample_id)
            self.assertEqual(metadata["capture_session_id"], capture["session_id"])
            self.assertEqual(metadata["derived"], {"valid_depth_ratio": .75,
                "valid_depth_ratio_basis": "nonzero_raw_z16_pixels_over_width_times_height_not_geometric_accuracy",
                "actual_source_skew_ms": 0})
            info = json.loads(archive.read("camera_info.json"))
            self.assertEqual(info["ir1"]["k"], [100.0, 0, .5, 0, 101.0, .5, 0, 0, 1])
            self.assertIsNone(info["ir1"]["r"])
            self.assertNotIn("body_pitch", compatible)
        self.assertEqual(self.store.receipt(sample_id), receipt)
        self.assertEqual(self.store.list_samples(), [receipt])

    def test_big_endian_raw_depth_and_padding_are_handled_without_reprojection(self):
        capture = capture_fixture()
        capture["frames"]["depth"].update(byte_order="big", data=struct.pack(">6H", 0, 1000, 12345, 2000, 65535, 23456))
        receipt = self.store.save_sample(capture)
        self.assertEqual(self.store.compatibility_json(receipt["sample_id"])["depth_m"], [None, 1, 2, 65.535])
        self.assertEqual(receipt["valid_depth_ratio"], .75)

    def test_valid_depth_ratio_excludes_padding_and_does_not_claim_geometric_compatibility(self):
        capture = capture_fixture()
        capture["frames"]["depth"]["data"] = struct.pack("<6H", 0, 0, 65535, 0, 0, 65535)
        capture["extrinsics"]["depth_to_ir1"]["translation"] = [.1, 0, 0]
        receipt = self.assert_raw_only(capture, "DEPTH_TO_IR_NOT_IDENTITY")
        self.assertEqual(receipt["valid_depth_ratio"], 0)
        capture["frames"]["depth"]["data"] = struct.pack("<6H", 1, 2, 0, 3, 4, 0)
        self.assertEqual(self.store.save_sample(capture)["valid_depth_ratio"], 1)

    def test_missing_or_unverified_depth_has_null_ratio(self):
        for change in (lambda frame: frame.pop("data"), lambda frame: frame.update(stride_bytes=1000),
                       lambda frame: frame.update(byte_order="unknown"), lambda frame: frame.update(format="Y16")):
            capture = capture_fixture()
            change(capture["frames"]["depth"])
            receipt = self.store.save_sample(capture)
            self.assertIsNone(receipt["valid_depth_ratio"])
            with zipfile.ZipFile(io.BytesIO(self.store.export_zip(receipt["sample_id"]))) as archive:
                self.assertIsNone(json.loads(archive.read("metadata.json"))["derived"]["valid_depth_ratio"])

    def test_actual_source_skew_is_independent_of_compatibility_and_null_for_incomparable_clocks(self):
        capture = capture_fixture()
        capture["frames"]["depth"]["timestamp_ms"] += 2.5
        receipt = self.assert_raw_only(capture, "TIMESTAMP_SKEW")
        self.assertEqual(receipt["actual_source_skew_ms"], 2.5)
        for domain in ("timestamp_domain.system_time", "unknown"):
            capture["frames"]["depth"]["timestamp_domain"] = domain
            self.assertIsNone(self.store.save_sample(capture)["actual_source_skew_ms"])
        for frame in capture["frames"].values():
            frame["timestamp_domain"] = "unknown"
        self.assertIsNone(self.store.save_sample(capture)["actual_source_skew_ms"])
        capture["frames"]["depth"].pop("timestamp_ms")
        self.assertIsNone(self.store.save_sample(capture)["actual_source_skew_ms"])

    def test_actual_sdk_enum_and_device_serial_number_fields_are_supported(self):
        capture = capture_fixture()
        capture["device"]["serial_number"] = capture["device"].pop("serial")
        for frame in capture["frames"].values():
            frame["profile"]["stream"] = "stream."+frame["profile"]["stream"]
            frame["profile"]["format"] = "format."+frame["profile"]["format"].lower()
        receipt = self.store.save_sample(capture)
        self.assertEqual(self.store.compatibility_json(receipt["sample_id"])["metadata"]["serial"], "FIXTURE-NOT-A-DEVICE")

    def test_zero_brown_conrady_is_verified_while_original_sdk_model_is_preserved(self):
        capture = capture_fixture()
        for frame in capture["frames"].values():
            frame["intrinsics"]["model"] = "distortion.brown_conrady"
        receipt = self.store.save_sample(capture)
        proof = self.store.compatibility_json(receipt["sample_id"])["metadata"]["alignment"]
        self.assertEqual(proof["ir1_intrinsics"]["model"], "distortion.brown_conrady")

    def test_missing_depth_and_time_preserve_original_ir_without_compatibility(self):
        for mode, reason in (("depth", "DEPTH_MISSING"), ("time", "TIMESTAMP_UNVERIFIED")):
            capture = capture_fixture()
            if mode == "depth":
                capture["frames"]["depth"].pop("data")
            else:
                capture["frames"]["depth"].pop("timestamp_ms")
            with self.subTest(mode=mode):
                self.assert_raw_only(capture, reason)

    def test_distortion_intrinsics_extrinsics_profiles_and_frameset_mismatch_fail_closed(self):
        changes = [
            ("DISTORTION_NOT_PINHOLE", lambda c: c["frames"]["ir1"]["intrinsics"].update(coeffs=[1e-12, 0, 0, 0, 0])),
            ("DISTORTION_NOT_PINHOLE", lambda c: c["frames"]["depth"]["intrinsics"].update(model="distortion.kannala_brandt4")),
            ("INTRINSICS_INVALID", lambda c: c["frames"]["ir1"]["intrinsics"].update(fx=0)),
            ("INTRINSICS_MISMATCH", lambda c: c["frames"]["depth"]["intrinsics"].update(fx=100.001)),
            ("DEPTH_TO_IR_NOT_IDENTITY", lambda c: c["extrinsics"]["depth_to_ir1"].update(translation=[.001, 0, 0])),
            ("DEPTH_TO_IR_NOT_IDENTITY", lambda c: c["extrinsics"]["depth_to_ir1"].update(rotation=[0, -1, 0, 1, 0, 0, 0, 0, 1])),
            ("PROFILE_MISMATCH", lambda c: c["frames"]["depth"]["profile"].update(fps=15)),
            ("PROFILE_UNVERIFIED", lambda c: c["frames"]["depth"].pop("profile")),
            ("FRAMESET_UNVERIFIED", lambda c: c["frameset"].update(verified=False)),
            ("FRAMESET_UNVERIFIED", lambda c: c["frameset"].update(depth_frame_number=18)),
            ("OPTICAL_FRAME_UNVERIFIED", lambda c: c["frames"]["ir1"].update(frame_id_source="assumed_ros_tf")),
            ("DEPTH_SCALE_INVALID", lambda c: c.update(depth_scale_m=0)),
            ("DEVICE_UNVERIFIED", lambda c: c["device"].pop("serial")),
        ]
        for reason, change in changes:
            capture = capture_fixture()
            change(capture)
            with self.subTest(reason=reason):
                self.assert_raw_only(capture, reason)

    def test_exact_fixed_timestamp_limit_and_clock_domains(self):
        capture = capture_fixture()
        capture["frames"]["depth"]["timestamp_ms"] += 1
        self.assertTrue(self.store.save_sample(capture)["compatibility"]["available"])
        capture["frames"]["depth"]["timestamp_ms"] += .0001
        self.assert_raw_only(capture, "TIMESTAMP_SKEW")
        capture = capture_fixture()
        capture["frames"]["depth"]["timestamp_domain"] = "system_time"
        self.assert_raw_only(capture, "TIMESTAMP_UNVERIFIED")
        for frame in capture["frames"].values():
            frame["timestamp_domain"] = "unknown"
        self.assert_raw_only(capture, "TIMESTAMP_UNVERIFIED")

    def test_malformed_raw_layout_is_preserved_but_no_mislabelled_png_or_compatibility(self):
        capture = capture_fixture()
        capture["frames"]["ir1"]["stride_bytes"] = 1000
        receipt = self.assert_raw_only(capture, "FRAME_LAYOUT_MISMATCH")
        self.assertFalse(receipt["image"]["available"])
        self.assertNotIn("click.png", receipt["files"])

    def test_nonfinite_malformed_numeric_and_unconfirmed_capture_never_publish(self):
        for value in (float("nan"), float("inf"), float("-inf"), 2**65, 2**10000):
            capture = capture_fixture()
            capture["frames"]["ir1"]["intrinsics"]["fx"] = value
            with self.subTest(value=value), self.assertRaises(DepthCaptureError) as caught:
                self.store.save_sample(capture)
            self.assertEqual(caught.exception.code, "INVALID_CAPTURE_METADATA")
        capture = capture_fixture()
        capture["confirmation"]["robot_seated"] = False
        with self.assertRaises(DepthCaptureError) as caught:
            self.store.save_sample(capture)
        self.assertEqual(caught.exception.code, "CAPTURE_CONFIRMATION_REQUIRED")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_atomic_io_failure_keeps_existing_samples_and_removes_partial_directory(self):
        good = self.store.save_sample(capture_fixture())
        original = self.store._write
        calls = []

        def fail_write(path, raw):
            calls.append(path.name)
            if len(calls) == 2:
                raise OSError("PRIVATE_PATH_SHOULD_NOT_ESCAPE")
            original(path, raw)
        with patch.object(self.store, "_write", side_effect=fail_write), self.assertRaises(DepthCaptureError) as caught:
            self.store.save_sample(capture_fixture())
        self.assertEqual(caught.exception.code, "DEPTH_CAPTURE_IO_ERROR")
        self.assertNotIn("PRIVATE_PATH_SHOULD_NOT_ESCAPE", str(caught.exception))
        self.assertEqual([p.name for p in self.root.iterdir()], [good["sample_id"]])
        self.assertEqual(self.store.receipt(good["sample_id"]), good)

    def test_storage_and_sample_quota_fail_before_any_partial_publication(self):
        with patch("robot_dashboard.depth_capture_store.shutil.disk_usage", return_value=type("Disk", (), {"free": 0})()):
            with self.assertRaises(DepthCaptureError) as caught:
                self.store.save_sample(capture_fixture())
        self.assertEqual(caught.exception.code, "CAPTURE_STORAGE_FULL")
        self.assertEqual(list(self.root.iterdir()), [])
        self.store.max_samples = 1
        self.store.save_sample(capture_fixture())
        with self.assertRaises(DepthCaptureError) as caught:
            self.store.save_sample(capture_fixture())
        self.assertEqual(caught.exception.code, "CAPTURE_QUOTA_EXCEEDED")
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_uuid_only_retrieval_rejects_traversal_and_unknown_ids(self):
        for value in ("../outside", "/etc/passwd", "A"*32, "0"*32+"/file", "0"*31, None):
            for method in (self.store.receipt, self.store.compatibility_json, self.store.export_zip, self.store.click_png):
                with self.subTest(value=value, method=method.__name__), self.assertRaises(DepthCaptureError) as caught:
                    method(value)
                self.assertEqual(caught.exception.code, "INVALID_SAMPLE_ID")
        with self.assertRaises(DepthCaptureError) as caught:
            self.store.receipt("0"*32)
        self.assertEqual(caught.exception.status, 404)

    def test_symlink_root_ancestor_sample_and_files_are_never_exported(self):
        alias = self.root.parent/"alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(DepthCaptureError):
            DepthCaptureStore(alias/"child", minimum_free_bytes=0)
        sample_id = "a"*32
        (self.root/sample_id).symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(DepthCaptureError):
            self.store.export_zip(sample_id)
        (self.root/sample_id).unlink()
        receipt = self.store.save_sample(capture_fixture())
        raw = self.root/receipt["sample_id"]/"click.png"
        raw.unlink()
        raw.symlink_to(__file__)
        with self.assertRaises(DepthCaptureError):
            self.store.click_png(receipt["sample_id"])

    def test_artifact_integrity_and_private_permissions(self):
        receipt = self.store.save_sample(capture_fixture())
        path = self.root/receipt["sample_id"]
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in path.iterdir()))
        (path/"depth.z16").write_bytes(b"changed")
        with self.assertRaises(DepthCaptureError) as caught:
            self.store.export_zip(receipt["sample_id"])
        self.assertEqual(caught.exception.code, "CAPTURE_INTEGRITY_ERROR")

    def test_caller_mutation_cannot_change_saved_original_metadata_or_profiles(self):
        capture = capture_fixture()
        receipt = self.store.save_sample(capture)
        capture["frames"]["ir1"]["intrinsics"]["fx"] = 9999
        capture["confirmation"]["robot_seated"] = False
        self.assertEqual(self.store.compatibility_json(receipt["sample_id"])["intrinsics"]["fx"], 100)


if __name__ == "__main__":
    unittest.main()
