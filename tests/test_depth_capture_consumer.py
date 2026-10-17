"""Cross-task export contract only; no calibration algorithm or real accuracy."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from experiments.realsense_mount_calibration.calibration import _validate_sample
from robot_dashboard.depth_capture_store import DepthCaptureStore
from robot_dashboard.mount_calibration import CalibrationError, estimate, export_analysis
from test_depth_capture_store import capture_fixture


def collector_export(store, timestamp_ms=1234.0):
    """Synthetic SDK fixture through the real exporter, never a hardware claim."""
    capture = capture_fixture()
    for name, bpp in (("ir1", 1), ("depth", 2)):
        frame = capture["frames"][name]
        frame.update(width=16, height=16, stride_bytes=16*bpp, timestamp_ms=timestamp_ms,
                     data=bytes([80])*256 if bpp == 1 else b"\xe8\x03"*256)
        frame["profile"].update(width=16, height=16)
        frame["intrinsics"].update(width=16, height=16, fx=20., fy=20., ppx=7.5, ppy=7.5)
    receipt = store.save_sample(capture)
    sample = store.compatibility_json(receipt["sample_id"])
    sample["points"] = [{"u": u, "v": v} for v in (2, 7, 13) for u in (2, 7, 13)]
    return sample


def comparison(first, second):
    return {"samples": [first, second], "reference_id": first["id"],
            "robot_stationary_confirmed": True, "wall_same_confirmed": True,
            "mount_only_pitch_confirmed": True}


class DepthConsumerContractTests(unittest.TestCase):
    def test_export_enters_existing_pitch_tool_after_user_selects_points(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DepthCaptureStore(Path(directory).resolve() / "samples", minimum_free_bytes=0)
            capture = capture_fixture()
            for name, bpp in (("ir1", 1), ("depth", 2)):
                frame = capture["frames"][name]
                frame.update(width=8, height=8, stride_bytes=8*bpp,
                    data=bytes([80])*64 if bpp == 1 else b"\xe8\x03"*64)
                frame["profile"].update(width=8,height=8)
                frame["intrinsics"].update(width=8,height=8,ppx=3.5,ppy=3.5)
            exports = []
            for skew in (0.0, 0.5):
                capture["frames"]["depth"]["timestamp_ms"] = capture["frames"]["ir1"]["timestamp_ms"] + skew
                receipt = store.save_sample(capture)
                sample = store.compatibility_json(receipt["sample_id"])
                self.assertEqual(sample["points"], [])
                # These picks simulate the other UI's later user action. They
                # are never inserted into the stored capture or export.
                selected = deepcopy(sample)
                selected["points"] = [{"u":u,"v":v} for u,v in ((0,0),(3,0),(7,0),(0,7),(3,7),(7,7))]
                parsed = _validate_sample(selected,0)
                self.assertEqual(parsed["depth"].shape, (8,8))
                exports.append(sample)
            # Geometry alignment is invariant, while exposure pairing evidence
            # varies per sample. The consumer checks alignment across angles.
            self.assertEqual(exports[0]["metadata"]["alignment"], exports[1]["metadata"]["alignment"])
            self.assertNotEqual(exports[0]["metadata"]["synchronization"], exports[1]["metadata"]["synchronization"])
            self.assertNotEqual(exports[0]["metadata"]["capture_id"], exports[1]["metadata"]["capture_id"])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = DepthCaptureStore(Path(self.directory.name).resolve() / "samples", minimum_free_bytes=0)

    def test_retained_frames_do_not_expire_or_gain_new_timestamps_on_analysis(self):
        # Hardware-clock timestamps are not wall-clock age, and counters may
        # reset across sessions. Distinct timestamps still distinguish frames.
        first, second = collector_export(self.store), collector_export(self.store, 4567.)
        original = comparison(first, second)
        saved = deepcopy(original)
        result = export_analysis(original)
        self.assertEqual(result["input"], saved)
        self.assertEqual(original, saved)
        self.assertEqual(result["analysis"]["status"], "RELATIVE_ONLY")
        self.assertFalse(result["analysis"]["absolute_pitch_validated"])
        self.assertEqual(first["metadata"]["source_timestamp"], 1.234)
        self.assertEqual(first["metadata"]["frame_numbers"], second["metadata"]["frame_numbers"])

    def test_replayed_source_frames_rejected_even_with_new_sample_and_capture_ids(self):
        first, replay = collector_export(self.store), collector_export(self.store)
        for sample in (first, replay):
            sample["metadata"]["capture_session_id"] = "same-retained-session"
        self.assertNotEqual(first["id"], replay["id"])
        self.assertNotEqual(first["metadata"]["capture_id"], replay["metadata"]["capture_id"])
        with self.assertRaisesRegex(CalibrationError, "distinct source exposure"):
            estimate(comparison(first, replay))

    def test_hardware_clock_reset_across_sessions_is_not_a_replayed_exposure(self):
        first, second = collector_export(self.store), collector_export(self.store)
        first["metadata"]["capture_session_id"] = "before-restart"
        second["metadata"]["capture_session_id"] = "after-restart"
        self.assertEqual(estimate(comparison(first, second))["status"], "RELATIVE_ONLY")
        for sample in (first, second):
            sample["metadata"].pop("capture_session_id")
        result = estimate(comparison(first, second))
        self.assertTrue(any("epoch" in warning for warning in result["samples"][0]["warnings"]))
        for sample in (first, second):
            sample["metadata"]["capture_session_id"] = None
        self.assertEqual(estimate(comparison(first, second))["status"], "RELATIVE_ONLY")

    def test_collector_alignment_is_checked_against_click_pixels(self):
        original = collector_export(self.store)
        changes = (
            ("depth_intrinsics", "width", 32),
            ("ir1_intrinsics", "fx", 21.),
            ("depth_intrinsics", "ppx", 7.),
            ("ir1_intrinsics", "coeffs", [0., .001, 0., 0., 0.]),
            ("ir1_intrinsics", "model", "distortion.inverse_brown_conrady"),
            ("depth_to_ir1", "translation", [.01, 0., 0.]),
            ("depth_to_ir1", "rotation", [0., -1., 0., 1., 0., 0., 0., 0., 1.]),
            ("depth_to_ir1", "translation_unit", "mm"),
        )
        for section, field, value in changes:
            sample = deepcopy(original)
            sample["metadata"]["alignment"][section][field] = value
            # An imported tolerance cannot loosen the fixed producer contract.
            sample["metadata"]["alignment"]["extrinsics_absolute_tolerance"] = 100
            sample["metadata"]["alignment"]["intrinsics_relative_tolerance"] = 100
            with self.subTest(section=section, field=field), self.assertRaisesRegex(CalibrationError, "alignment"):
                _validate_sample(sample, 0)

    def test_contradictory_or_incomplete_pairing_evidence_rejected(self):
        original = collector_export(self.store)
        changes = (
            ("source_timestamp", 1234.), ("source_timestamp_unit", "milliseconds"),
            ("source_timestamp_stream", "depth"), ("timestamp_domain", "timestamp_domain.system_time"),
            ("source_timestamps_ms", {"ir1": 1234., "depth": 1236.}),
            ("source_timestamps_ms", {"ir1": 1234., "depth": -1.}),
            ("synchronization", {"frameset_verified": False, "source_skew_ms": 0., "max_source_skew_ms": 1.}),
            ("synchronization", {"frameset_verified": True, "source_skew_ms": .5, "max_source_skew_ms": 1.}),
            ("synchronization", {"frameset_verified": True, "source_skew_ms": 0., "max_source_skew_ms": 100.}),
            ("synchronization", None), ("frame_numbers", {"ir1": True, "depth": 17}),
            ("frame_numbers", {"ir1": 17., "depth": 17}), ("frame_numbers", None),
            ("alignment", None),
        )
        for field, value in changes:
            sample = deepcopy(original)
            sample["metadata"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(CalibrationError):
                _validate_sample(sample, 0)

    def test_collector_profile_units_and_coordinate_frame_mismatch_rejected(self):
        first, second = collector_export(self.store), collector_export(self.store, 4567.)
        for field, value in (("profile_id", "another-stream"), ("depth_units", "mm"), ("depth_unit", "mm"),
                             ("frame_id", "another_optical_frame"), ("image_frame_id", "color_frame")):
            changed = deepcopy(second)
            changed["metadata"][field] = value
            with self.subTest(field=field), self.assertRaises(CalibrationError):
                estimate(comparison(first, changed))
