import unittest

from . import optional_deps  # noqa: F401
import cv2
import numpy as np
from experiments.competition_vm.traffic_signals.core import classify_roi
from experiments.competition_vm.traffic_signals.detector import Detection
from robot_dashboard.competition_traffic.emitter import PROFILE_NAME, profile_settings, validate_emitter
from robot_dashboard.competition_traffic.inference import settings
from robot_dashboard.competition_traffic.pipeline import TrafficPipeline
from .helpers import config, frame, Detector


BOX = (20, 20, 120, 180)


def scene(color=(0, 230, 0), background=20):
    image = np.full((200, 200, 3), background, np.uint8)
    cv2.circle(image, (70, 125), 8, color, -1)
    return image


def detector(emitter=False):
    d = Detector([Detection(BOX, .9, 0, "transient")])
    d.inference_settings, d.inference_settings_sha256 = settings(
        "upper-overlap640", confidence_floor=.25, model_sha256=d.sha256,
        emitter_profile=PROFILE_NAME if emitter else None)
    return d


class EmitterTests(unittest.TestCase):
    def test_bright_red_and_green_on_dark_context_preserve_native_region(self):
        for bgr, state in [((0, 230, 0), "GREEN"), ((0, 0, 230), "RED")]:
            image = scene(bgr)
            color = classify_roi(image, BOX)
            result = validate_emitter(image, BOX, color)
            self.assertEqual(result["validated_state"], state)
            self.assertEqual(result["components"][0]["bbox_xyxy_native"], [62, 117, 79, 134])
            self.assertFalse(result["physical_emission_proven"])
            self.assertFalse(result["crossing_identity_verified"])

    def test_dim_colored_patch_does_not_become_green_evidence(self):
        image = scene((0, 90, 0))
        color = classify_roi(image, BOX)
        self.assertEqual(color["raw_state"], "GREEN")
        result = validate_emitter(image, BOX, color)
        self.assertEqual(result["validated_state"], "UNKNOWN")
        self.assertIn("COMPONENT_NOT_BRIGHT", result["reasons"])
        self.assertEqual(color["raw_state"], "GREEN")

    def test_green_background_attached_to_housing_edge_is_unsupported(self):
        image = scene((20, 20, 20))
        image[20:180, 20:55] = (0, 230, 0)
        result = validate_emitter(image, BOX, classify_roi(image, BOX))
        self.assertFalse(result["supported"])
        self.assertIn("COMPONENT_TOUCHES_CROP_EDGE", result["reasons"])

    def test_bright_surround_is_not_dark_enclosure(self):
        image = scene(background=210)
        result = validate_emitter(image, BOX, classify_roi(image, BOX))
        self.assertFalse(result["supported"])
        self.assertIn("DARK_ENCLOSURE_UNSUPPORTED", result["reasons"])

    def test_clipping_size_channel_and_missing_mask_fail_closed(self):
        image = scene()
        for box in [(20, 1, 120, 180), (20, 20, 201, 180), (20, 20, 25, 25)]:
            self.assertFalse(validate_emitter(image, box, classify_roi(image, box))["supported"])
        color = classify_roi(image, BOX)
        self.assertFalse(validate_emitter(image, BOX, color, encoding="rgb8")["supported"])
        color["mask"] = None
        self.assertFalse(validate_emitter(image, BOX, color)["supported"])

    def test_white_and_ambiguous_color_are_not_reconstructed(self):
        for image in [scene((255, 255, 255)), scene()]:
            if np.max(image[:, :, 0]) < 255:
                cv2.circle(image, (70, 60), 8, (0, 0, 230), -1)
            color = classify_roi(image, BOX)
            self.assertIn(color["raw_state"], ("UNKNOWN", "AMBIGUOUS"))
            self.assertEqual(validate_emitter(image, BOX, color)["validated_state"], "UNKNOWN")

    def test_optional_pipeline_gate_preserves_raw_diagnostic(self):
        outputs = []
        for enabled in (False, True):
            p = TrafficPipeline(config((200, 200), BOX), detector(enabled))
            for n in range(5):
                o = p.process(frame(n, image=scene((0, 90, 0))), now_s=n/10)
            outputs.append(o)
        self.assertEqual(outputs[0].signal["stable_state"], "GREEN")
        self.assertEqual(outputs[1].signal["raw_state"], "UNKNOWN")
        self.assertEqual(outputs[1].signal["stable_state"], "UNKNOWN")
        self.assertEqual(outputs[1].context["raw_state_before_emitter"], "GREEN")
        self.assertEqual(outputs[1].context["free_observations"][0]["raw_state"], "GREEN")
        self.assertIn("EMITTER_UNSUPPORTED", outputs[1].signal["quality_flags"])
        self.assertEqual(outputs[1].context["first_received_s"], .4)

    def test_profile_uses_existing_hash_and_change_revokes_previous_green(self):
        off, on = detector(), detector(True)
        self.assertNotEqual(off.inference_settings_sha256, on.inference_settings_sha256)
        self.assertEqual(on.inference_settings["emitter_validation"], profile_settings(PROFILE_NAME))
        self.assertNotIn("emitter_validation", off.inference_settings)
        with self.assertRaises(ValueError):
            profile_settings("tuned-profile")
        p = TrafficPipeline(config((200, 200), BOX), off)
        for n in range(5):
            o = p.process(frame(n, image=scene()), now_s=n/10)
        self.assertEqual(o.signal["stable_state"], "GREEN")
        p.detector = on
        o = p.process(frame(5, image=scene()), now_s=.5)
        self.assertIn("INFERENCE_SETTINGS_CHANGED", o.signal["quality_flags"])
        self.assertEqual(o.signal["stable_state"], "UNKNOWN")

    def test_supported_component_does_not_supply_crossing_identity(self):
        p = TrafficPipeline(config((200, 200), BOX), detector(True), observation_mode="detection-only")
        for n in range(5):
            o = p.process(frame(n, image=scene()), now_s=n/10)
        check = o.context["free_observations"][0]["emitter_validation"]
        self.assertEqual(check["validated_state"], "GREEN")
        self.assertEqual(o.context["observation_stage"], "detection-only")
        self.assertIsNone(o.signal["roi_xyxy_native"])
        self.assertEqual(o.signal["stable_state"], "UNKNOWN")
