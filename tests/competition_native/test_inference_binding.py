"""Pinned C4 profile/projection with synthetic pixels, detector and local clock.

No weights, real RGB replay, raw-color accuracy or physical-motion claim.
"""
import copy
from dataclasses import FrozenInstanceError, replace
import importlib
from types import SimpleNamespace
import unittest

from robot_dashboard.mission_routes.competition_native.fragments import join_signal, project_signal
from robot_dashboard.mission_routes.competition_native.observations import ObservationRejected
from .dependency_overlay import C4_PROFILE_SHA, pinned_dependencies


class InferenceBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.overlay = pinned_dependencies(c4_sha=C4_PROFILE_SHA,
                                          c4_modules=("association", "lamp", "inference"))
        cls.deps = cls.overlay.__enter__()
        cls.addClassCleanup(cls.overlay.__exit__, None, None, None)
        print(f"C2 inference binding cross dependency C4={C4_PROFILE_SHA}")

    def setUp(self):
        import cv2
        import numpy as np
        from experiments.competition_vm.traffic_signals.detector import Detection
        from .test_runtime_contract import SignalFragmentTests
        self.f = SignalFragmentTests()
        self.f.setUp()
        c4 = self.deps.c4_package
        self.settings = importlib.import_module(c4 + ".inference").settings
        self.frames = importlib.import_module(c4 + ".frames")
        self.pipeline_type = importlib.import_module(c4 + ".pipeline").TrafficPipeline
        # Trusted owner chooses this before processing any observation.
        self.profile, digest = self.settings("full640", confidence_floor=.25, model_sha256="f" * 64)
        self.binding = replace(self.f.binding, inference_settings_sha256=digest)
        self.config = SimpleNamespace(sha256=self.binding.config_hash, document={
            "model": {"sha256": self.binding.model_sha256}, "class_map": {"0": "traffic_light"},
            "min_confidence": .25, "association": {
                "signal_id": "signal-1", "crossing_id": "crossing-1",
                "binding_id": self.binding.binding_id, "native_image_size": [64, 64],
                "verified": True, "expected_roi_native": [0, 0, 64, 64]}})
        self.detector = SimpleNamespace(sha256="f" * 64, names={"0": "traffic_light"},
            inference_settings_sha256=digest, coordinate_space="native_xyxy",
            infer=lambda _: [Detection((0, 0, 64, 64), .9, 0, "stub")])
        pixels = np.full((64, 64, 3), 15, np.uint8)
        cv2.circle(pixels, (32, 32), 12, (0, 230, 0), -1)
        ok, encoded = cv2.imencode(".jpg", pixels)
        self.assertTrue(ok)
        self.jpeg = encoded.tobytes()
        self.clock = [0.]
        self.pipeline = self.pipeline_type(self.config, self.detector, clock=lambda: self.clock[0])

    def sample(self, index, *, epoch="camera-boot", pipeline=None):
        first = round(9.4 + index * .1, 2)
        self.clock[0] = first + .08
        frame = self.frames.from_owner_jpeg(self.jpeg, source_id="camera", producer_epoch=epoch,
            sequence=index, source_stamp_ns=str(1_000_000_000 + index * 100_000_000),
            source_clock="synchronized_ros", source_age_s=.02, received_s=first,
            clock_verified=True, identity_verified=True, provenance="SYNTHETIC_C2_PROFILE_TEST",
            binding_id=self.binding.binding_id)
        return (pipeline or self.pipeline).process(frame, now_s=first)

    def green(self):
        for index in range(7):
            observed = self.sample(index)
        self.assertEqual(observed.signal["stable_state"], "GREEN")
        return observed

    def project(self, observation, *, now=10.15, binding=None):
        return project_signal(self.f.r.packet(), observation=observation,
            projection=self.deps.projection, binding=binding or self.binding,
            now_s=now, receiver_clock_id="local")

    def test_owner_pin_is_required_validated_and_immutable(self):
        for value in (None, "", "A" * 64, "a" * 63, "g" * 64, "a" * 64 + "\n", 1, True):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "EXPECTED_INFERENCE_SETTINGS_INVALID"):
                replace(self.binding, inference_settings_sha256=value)
        with self.assertRaises(FrozenInstanceError):
            self.binding.inference_settings_sha256 = "b" * 64

    def test_same_settings_pass_preserving_original_age_and_independent_facts(self):
        observed = self.green()
        original = copy.deepcopy(observed.json_record())
        packet = self.project(observed)
        frame = self.f.normalizer.receive(packet, 10.15)
        stamp = frame.components["signal"]
        self.assertAlmostEqual(stamp.stamp.source_age_s + frame.now - stamp.receipt_s, .17)
        self.assertEqual(stamp.receipt_s, 10.)
        self.assertEqual(packet.evidence["stable_state"], "GREEN")
        self.assertEqual(observed.context["receipt_ttl_s"], .25)
        self.assertEqual(observed.context["stability_s"], .4)
        self.assertEqual(observed.json_record(), original)
        self.assertIsNone(observed.context["feet"])
        self.assertIsNone(observed.context["physical_stop"])
        self.assertFalse(observed.context["departure_authorized"])

    def test_same_model_tile_change_rejects_mission_and_keeps_diagnostics(self):
        self.green()
        tiled, digest = self.settings("upper-overlap640", confidence_floor=.25, model_sha256="f" * 64)
        self.assertEqual(tiled["model_sha256"], self.profile["model_sha256"])
        self.assertEqual(tiled["imgsz"], self.profile["imgsz"])
        self.assertNotEqual(tiled["search"], self.profile["search"])
        self.assertNotEqual(digest, self.binding.inference_settings_sha256)
        self.detector.inference_settings_sha256 = digest
        changed = self.sample(7)
        self.assertIn("INFERENCE_SETTINGS_CHANGED", changed.signal["quality_flags"])
        for index in range(8, 15):
            changed = self.sample(index)
        self.assertEqual(changed.signal["stable_state"], "GREEN")
        before = copy.deepcopy(changed.json_record())
        with self.assertRaisesRegex(ObservationRejected, "INFERENCE_SETTINGS_MISMATCH"):
            self.project(changed, now=self.clock[0])
        self.assertEqual(changed.json_record(), before)
        self.assertTrue(changed.context["detection_candidates"])
        self.assertTrue(changed.context["free_observations"])
        self.assertEqual(self.pipeline.latest.signal["native_image"], changed.signal["native_image"])

    def test_missing_invalid_or_different_observed_digest_cannot_pin_itself(self):
        observed = self.green()
        for value, reason in ((None, "REQUIRED"), ("", "INVALID"), ("F" * 64, "INVALID"),
                              ("g" * 64, "INVALID"), (False, "INVALID"), ("b" * 64, "MISMATCH")):
            context = {**observed.context, "inference_settings_sha256": value}
            if value is None:
                context.pop("inference_settings_sha256")
            with self.subTest(value=value), self.assertRaisesRegex(ObservationRejected, "INFERENCE_SETTINGS_" + reason):
                self.project(SimpleNamespace(signal=observed.signal, context=context))
        self.assertEqual(self.binding.inference_settings_sha256, self.detector.inference_settings_sha256)

    def test_epoch_change_requires_owner_rebinding_and_cannot_reuse_green(self):
        self.f.normalizer.receive(self.project(self.green()), 10.15)
        changed = self.sample(7, epoch="camera-new-boot")
        self.assertEqual(changed.signal["stable_state"], "UNKNOWN")
        with self.assertRaisesRegex(ObservationRejected, "SOURCE_OR_ASSOCIATION_MISMATCH"):
            self.project(changed, now=10.18)
        packet = self.project(changed, now=10.18, binding=replace(self.binding, epoch="camera-new-boot"))
        with self.assertRaises(ObservationRejected):
            self.f.normalizer.receive(packet, 10.18)  # Existing runtime still owns the old epoch.

    def test_old_green_polling_and_expiry_do_not_renew_receipt(self):
        observed = self.green()
        self.f.normalizer.receive(self.project(observed), 10.15)
        repeat = self.f.normalizer.receive(self.project(observed, now=10.2), 10.2)
        self.assertEqual(repeat.components["signal"].receipt_s, 10.)
        with self.assertRaisesRegex(ValueError, "EXPIRED"):
            self.project(observed, now=10.24)
        with self.assertRaisesRegex(ValueError, "FIRST_RECEIPT_MISMATCH"):
            self.deps.projection(observed, now_s=10.2, received_s=10.08)

    def test_same_jpeg_new_source_frame_advances_but_same_stamp_does_not(self):
        old = self.green()
        self.f.normalizer.receive(self.project(old), 10.15)
        fresh = self.sample(7)
        self.assertEqual(old.signal["native_image"], fresh.signal["native_image"])
        self.assertTrue(fresh.context["diagnostics"]["same_content_as_previous"])
        result = self.f.normalizer.receive(self.project(fresh, now=10.18), 10.18)
        self.assertEqual(result.components["signal"].receipt_s, 10.1)
        forged = SimpleNamespace(signal=fresh.signal, context={**fresh.context, "sequence": 8})
        with self.assertRaisesRegex(ObservationRejected, "REPLAY"):
            self.f.normalizer.receive(self.project(forged, now=10.2), 10.2)

    def test_detection_only_keeps_bbox_but_cannot_create_mission_facts(self):
        diagnostic = self.pipeline_type(self.config, self.detector,
            clock=lambda: self.clock[0], observation_mode="detection-only")
        observed = self.sample(6, pipeline=diagnostic)
        before = copy.deepcopy(observed.json_record())
        self.assertTrue(observed.context["free_observations"])
        self.assertTrue(observed.context["detection_candidates"])
        self.assertEqual(observed.signal["stable_state"], "UNKNOWN")
        with self.assertRaises(ValueError):
            self.project(observed)
        donor = self.f.r.packet(front_left_status="OUTSIDE", body_motion_status="MOVING", path_clear=False)
        with self.assertRaisesRegex(ObservationRejected, "MISSION_OBSERVATION_REQUIRED"):
            join_signal(donor, fragment=observed.signal,
                context={**observed.context, "association_verified": True},
                binding=self.binding, now_s=10.15, receiver_clock_id="local")
        self.assertEqual(observed.json_record(), before)
        self.assertEqual(donor.evidence["front_left_status"], "OUTSIDE")
        self.assertEqual(donor.evidence["body_motion_status"], "MOVING")
        self.assertFalse(donor.evidence["path_clear"])
        self.assertFalse(observed.context["departure_authorized"])

    def test_legacy_mode_missing_or_fixture_clock_is_not_native_authority(self):
        observed = self.green()
        context = dict(observed.context)
        context.pop("observation_mode")
        with self.assertRaisesRegex(ObservationRejected, "MISSION_OBSERVATION_REQUIRED"):
            self.project(SimpleNamespace(signal=observed.signal, context=context))
        context = {**observed.context, "source_clock": "fixture"}
        with self.assertRaisesRegex(ValueError, "OFFLINE_REPLAY_NOT_ROBOT_EVIDENCE"):
            self.project(SimpleNamespace(signal=observed.signal, context=context))
