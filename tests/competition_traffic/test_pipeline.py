from dataclasses import replace
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from . import optional_deps  # noqa: F401 -- dependency guard precedes optional imports

import numpy as np
from jsonschema import Draft202012Validator
from experiments.competition_vm.traffic_signals.detector import Detection
from robot_dashboard.competition_traffic.artifacts import save_images
from robot_dashboard.competition_traffic.frames import Frame, from_owner_jpeg
from robot_dashboard.competition_traffic.pipeline import TrafficPipeline
from robot_dashboard.competition_traffic.projection import signal_fragment
from .helpers import Detector, config, frame, lamp


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.detector = Detector()
        self.pipeline = TrafficPipeline(config(), self.detector)

    def warm(self):
        for n in range(5):
            obs = self.pipeline.process(frame(n), now_s=n / 10)
        self.assertEqual(obs.signal["stable_state"], "GREEN")
        return obs

    def check_unknown(self, f, reason, now=None):
        obs = self.pipeline.process(f, now_s=f.received_s if now is None else now)
        self.assertEqual(obs.signal["stable_state"], "UNKNOWN")
        self.assertIn(reason, obs.signal["quality_flags"])
        self.assertFalse(obs.context["departure_authorized"])
        return obs

    def test_stability_and_no_motion_evidence(self):
        first = self.pipeline.process(frame(), now_s=0.)
        self.assertEqual(first.signal["raw_state"], "GREEN")
        self.assertEqual(first.signal["stable_state"], "UNKNOWN")
        for n in range(1, 5):
            obs = self.pipeline.process(frame(n), now_s=n / 10.)
        self.assertEqual(obs.signal["stable_state"], "GREEN")
        for key in ("feet", "physical_stop", "posture", "path_clear"):
            self.assertIsNone(obs.context[key])

    def test_white_and_black(self):
        for value in (0, 255):
            with self.subTest(value=value):
                self.setUp()
                obs = self.check_unknown(frame(image=np.full((64, 64, 3), value, np.uint8)), "LOW_CHROMA")
                self.assertEqual(obs.signal["raw_state"], "UNKNOWN")

    def test_truncated_roi(self):
        self.detector.detections = [Detection((-1, 0, 64, 64), .9, 0, "a")]
        self.check_unknown(frame(), "ROI_TRUNCATED")

    def test_small_roi(self):
        self.pipeline = TrafficPipeline(config(roi=(1, 1, 3, 3)), Detector([Detection((1, 1, 3, 3), .9, 0, "a")]))
        self.check_unknown(frame(), "TOO_SMALL")

    def test_multiple_signals(self):
        self.detector.detections = [Detection((0, 0, 64, 64), .9, 0, x) for x in ("a", "b")]
        self.check_unknown(frame(), "ASSOCIATION_UNCERTAIN")

    def test_different_binding(self):
        self.warm()
        self.check_unknown(frame(5, binding_id="opposite-signal"), "SIGNAL_BINDING_MISMATCH")
        self.assertEqual(self.detector.calls, 5)

    def test_resolution_change(self):
        self.check_unknown(frame(image=lamp(size=(128, 64))), "BINDING_IMAGE_SIZE_MISMATCH")

    def test_letterbox(self):
        self.detector.coordinate_space = "letterbox_xyxy"
        self.detector.model_size = (640, 640)
        self.detector.detections = [Detection((0, 160, 640, 480), .9, 0, "a")]
        self.pipeline = TrafficPipeline(config(size=(128, 64)), self.detector)
        obs = self.pipeline.process(frame(image=lamp(size=(128, 64))), now_s=0.)
        self.assertEqual(obs.signal["roi_xyxy_native"], [0, 0, 128, 64])
        self.assertEqual(obs.signal["raw_state"], "GREEN")

    def test_letterbox_padding_is_not_clamped_into_valid_signal(self):
        self.detector.coordinate_space = "letterbox_xyxy"
        self.detector.model_size = (640, 640)
        self.detector.detections = [Detection((0, 159, 640, 480), .9, 0, "a")]
        self.pipeline = TrafficPipeline(config(size=(128, 64)), self.detector)
        self.check_unknown(frame(image=lamp(size=(128, 64))), "ROI_TRUNCATED")

    def test_native_boxes_are_not_scaled_twice(self):
        self.detector.model_size = (640, 640)
        obs = self.pipeline.process(frame(), now_s=0.)
        self.assertEqual(obs.signal["roi_xyxy_native"], [0, 0, 64, 64])

    def test_unknown_coordinate_contract(self):
        self.detector.coordinate_space = "resized-unspecified"
        self.check_unknown(frame(), "COORDINATE_SPACE_UNKNOWN")

    def test_green_to_red_and_back(self):
        self.warm()
        obs = self.pipeline.process(frame(5, image=lamp((0, 0, 230))), now_s=.5)
        self.assertEqual(obs.signal["raw_state"], "RED")
        self.assertEqual(obs.signal["stable_state"], "UNKNOWN")
        for n in range(6, 10):
            obs = self.pipeline.process(frame(n, image=lamp((0, 0, 230))), now_s=n / 10)
        self.assertEqual(obs.signal["stable_state"], "RED")
        obs = self.pipeline.process(frame(10), now_s=1.)
        self.assertEqual(obs.signal["stable_state"], "UNKNOWN")

    def test_duplicate(self):
        self.warm()
        self.check_unknown(frame(4), "REPEATED_OR_REVERSED_FRAME", now=.5)
        self.assertEqual(self.pipeline.current_state(now_s=.5), "UNKNOWN")

    def test_identical_content_with_advancing_trusted_source_identity(self):
        self.warm()
        obs = self.pipeline.process(frame(5, image_handle="frame-4"), now_s=.5)
        self.assertEqual(obs.signal["stable_state"], "GREEN")
        self.assertTrue(obs.context["diagnostics"]["same_content_as_previous"])

    def test_poll_counter_without_trusted_source_identity_cannot_renew_green(self):
        self.warm()
        self.check_unknown(frame(5, image_handle="frame-4", identity_verified=False), "SOURCE_IDENTITY_UNVERIFIED")

    def test_out_of_order_sequence(self):
        self.warm()
        self.check_unknown(frame(3, received_s=.5), "REPEATED_OR_REVERSED_FRAME")

    def test_reverse_source_stamp(self):
        self.warm()
        self.check_unknown(frame(5, source_stamp_ns="1"), "REPEATED_OR_REVERSED_FRAME")

    def test_frame_missing(self):
        self.warm()
        self.check_unknown(frame(6), "FRAME_SEQUENCE_GAP")

    def test_receipt_gap(self):
        self.warm()
        self.check_unknown(frame(5, received_s=1.), "FRAME_RECEIPT_GAP")

    def test_stale_source(self):
        self.warm()
        self.check_unknown(frame(5, source_age_s=1.), "SOURCE_STALE")
        self.check_unknown(frame(5, source_age_s=0., received_s=.6), "REPEATED_OR_REVERSED_FRAME")

    def test_source_clock_not_verified(self):
        self.check_unknown(frame(clock_verified=False), "SOURCE_CLOCK_UNVERIFIED")

    def test_receiver_ttl(self):
        self.warm()
        self.check_unknown(frame(5), "RECEIPT_EXPIRED", now=.8)

    def test_watchdog_expires_without_minting_observations(self):
        obs = self.warm()
        self.assertEqual(self.pipeline.current_state(now_s=.6), "GREEN")
        self.assertEqual(self.pipeline.current_state(now_s=.7), "UNKNOWN")
        self.assertEqual(obs.context["sequence"], 4)
        self.assertIs(self.pipeline.latest, obs)

    def test_watchdog_uses_capture_age_too(self):
        for n in range(5):
            self.pipeline.process(frame(n, source_age_s=.2), now_s=n / 10)
        self.assertEqual(self.pipeline.current_state(now_s=.46), "UNKNOWN")

    def test_new_epoch_and_retired_replay_after_stale(self):
        self.warm()
        obs = self.pipeline.process(frame(0, producer_epoch="epoch-2", received_s=.5), now_s=.5)
        self.assertEqual(obs.signal["stable_state"], "UNKNOWN")
        self.check_unknown(frame(1, producer_epoch="epoch-2", received_s=.6, source_age_s=1.), "SOURCE_STALE")
        self.check_unknown(frame(99, received_s=.7), "RETIRED_EPOCH")

    def test_corrupt_image_clears_green(self):
        self.warm()
        self.check_unknown(replace(frame(5), bgr=None), "IMAGE_DECODE_FAILED")
        self.assertEqual(self.pipeline.current_state(now_s=.5), "UNKNOWN")

    def test_model_exception_clears_green(self):
        self.warm()
        def fail(image):
            raise RuntimeError("synthetic failure")
        self.detector.infer = fail
        self.check_unknown(frame(5), "MODEL_EXCEPTION")

    def test_missing_model(self):
        self.pipeline = TrafficPipeline(config())
        self.check_unknown(frame(), "MODEL_UNAVAILABLE")

    def test_class_map_mismatch(self):
        self.detector.names = {"0": "crosswalk"}
        self.check_unknown(frame(), "MODEL_CLASS_NAME_MISMATCH")

    def test_invalid_detection(self):
        for box, confidence, cls in [((0, 0, 64, 64), float("nan"), 0),
                                     ((0, 0, 64, 64), .9, 1), ((64, 0, 0, 64), .9, 0)]:
            self.setUp()
            self.detector.detections = [Detection(box, confidence, cls, "a")]
            self.check_unknown(frame(), "DETECTION_INVALID")

    def test_settling(self):
        self.check_unknown(frame(exposure_settling=True), "EXPOSURE_SETTLING")

    def test_invalid_metadata_revokes_previous_green(self):
        self.warm()
        with self.assertRaises(ValueError):
            self.pipeline.process(frame(5, sequence=True), now_s=.5)
        self.assertEqual(self.pipeline.current_state(now_s=.5), "UNKNOWN")

    def test_invalid_receiver_clock_revokes_previous_green(self):
        self.warm()
        for value in (float("nan"), "invalid", True):
            with self.assertRaises(ValueError):
                self.pipeline.process(frame(5), now_s=value)
            self.assertEqual(self.pipeline.current_state(now_s=.5), "UNKNOWN")

    def test_color_exception_revokes_previous_green(self):
        self.warm()
        with patch("robot_dashboard.competition_traffic.pipeline.classify_roi", side_effect=RuntimeError("failure")):
            self.check_unknown(frame(5), "COLOR_ANALYSIS_EXCEPTION")

    def test_unverified_binding_keeps_raw_analysis_but_never_stable_green(self):
        from robot_dashboard.competition_traffic.config import TrafficConfig
        doc = config().document
        doc["association"]["verified"] = False
        self.pipeline = TrafficPipeline(TrafficConfig.parse(doc), self.detector)
        for n in range(8):
            obs = self.check_unknown(frame(n), "ASSOCIATION_UNVERIFIED")
            self.assertEqual(obs.signal["raw_state"], "GREEN")

    def test_inference_latency_counts_in_live_age(self):
        self.pipeline = TrafficPipeline(config(), self.detector, clock=lambda: .4)
        self.check_unknown(frame(source_clock="synchronized_utc"), "SOURCE_STALE")

    def test_partial_projection_matches_canonical_field_definitions(self):
        obs = self.warm()
        schema = json.loads((Path(__file__).resolve().parents[2] / "docs/mission-competition/evidence.schema.json").read_text())
        schema.pop("required")
        Draft202012Validator(schema).validate(obs.signal)
        self.assertNotIn("frame_id", obs.signal)
        self.assertNotIn("body_motion_status", obs.signal)

    def test_offline_projection_rejected(self):
        with self.assertRaisesRegex(ValueError, "OFFLINE_REPLAY"):
            signal_fragment(self.warm(), now_s=.4, received_s=.4)

    def test_live_projection_checks_receiver_age(self):
        self.pipeline = TrafficPipeline(config(), self.detector, clock=lambda: 0.)
        obs = self.pipeline.process(frame(source_clock="synchronized_utc"), now_s=0.)
        fragment = signal_fragment(obs, now_s=.1, received_s=0.)
        self.assertEqual(fragment["stable_state"], "UNKNOWN")
        with self.assertRaisesRegex(ValueError, "EXPIRED"):
            signal_fragment(obs, now_s=.3, received_s=0.)

    def test_original_roi_and_mask_are_separate(self):
        f = frame()
        obs = self.pipeline.process(f, now_s=0.)
        with tempfile.TemporaryDirectory() as tmp:
            assets = save_images(tmp, f, obs)
            self.assertEqual(set(assets), {"decoded_original_bgr", "native_roi_crop", "processed_color_mask", "detection_only_overlay"})
            self.assertNotEqual(obs.signal["native_image"], obs.signal["processed_image"])
            self.assertNotEqual(assets["decoded_original_bgr"]["sha256"], assets["processed_color_mask"]["sha256"])

    def test_owner_jpeg_is_passive(self):
        # Keep the pre-follow-up positional exposure argument; it cannot silently
        # turn into authorization for source identity.
        legacy = Frame(lamp(), "camera", "epoch", 1, "1", "fixture", 0., 0., True,
                       "owner", "handle", "binding", True)
        self.assertTrue(legacy.exposure_settling)
        self.assertFalse(legacy.identity_verified)
        f = from_owner_jpeg(b"corrupt", source_id="camera", producer_epoch="epoch", sequence=1,
                            source_stamp_ns="1", source_clock="synchronized_ros", source_age_s=None,
                            received_s=0., clock_verified=False, provenance="owner", binding_id="binding")
        self.assertIsNone(f.bgr)
        self.assertEqual(f.sequence, 1)


if __name__ == "__main__":
    unittest.main()
