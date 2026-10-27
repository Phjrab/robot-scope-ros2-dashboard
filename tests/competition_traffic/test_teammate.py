import copy
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from . import optional_deps  # noqa: F401
import cv2
import numpy as np

from experiments.competition_vm.traffic_signals.core import classify_roi
from experiments.competition_vm.traffic_signals.detector import Detection
from robot_dashboard.competition_traffic.config import TrafficConfig, sha256_file
from robot_dashboard.competition_traffic.consensus import POLICY, SIGNAL_CLASSES, MODEL_CLASSES, combine
from robot_dashboard.competition_traffic.inference import settings
from robot_dashboard.competition_traffic.model import OwnerModel
from robot_dashboard.competition_traffic.pipeline import TrafficPipeline
from robot_dashboard.competition_traffic.teammate_compare import compare_color, load_comparator, score_target, summarize
from .helpers import config, Detector, frame, lamp


def teammate_config():
    doc = copy.deepcopy(config().document)
    doc.update(class_map=dict(SIGNAL_CLASSES), color_policy=POLICY)
    return TrafficConfig.parse(doc)


class TeammateDetector(Detector):
    names = dict(MODEL_CLASSES)

    def __init__(self, class_id=0, detections=None):
        super().__init__(detections if detections is not None else [Detection((0, 0, 64, 64), .9, class_id, "a")])
        self.inference_settings, self.inference_settings_sha256 = settings(
            "full640", confidence_floor=.25, model_sha256=self.sha256, color_policy=POLICY)


class TeammateTests(unittest.TestCase):
    def test_class_map_and_policy_are_explicit_and_strict(self):
        cfg = teammate_config()
        for mapping in ({"0": "traffic_light_red", "1": "traffic_light_green"}, MODEL_CLASSES, {"9": "traffic light"}):
            doc = copy.deepcopy(cfg.document)
            doc["class_map"] = mapping
            with self.assertRaisesRegex(ValueError, "CLASS_MAP_MISMATCH"):
                TrafficConfig.parse(doc)
        doc = copy.deepcopy(cfg.document)
        doc["color_policy"] = "unreviewed"
        with self.assertRaisesRegex(ValueError, "POLICY_UNKNOWN"):
            TrafficConfig.parse(doc)

    def test_actual_loader_checks_all_three_names_and_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.pt"
            path.write_bytes(b"mocked loader; not a pickle")
            doc = copy.deepcopy(teammate_config().document)
            doc["model"].update(sha256=sha256_file(path), trusted_pickle=True)
            cfg = TrafficConfig.parse(doc)
            for names, task, valid in [(dict(MODEL_CLASSES), "detect", True),
                                       ({**MODEL_CLASSES, "2": "other"}, "detect", False),
                                       (dict(MODEL_CLASSES), "classify", False)]:
                adapter = SimpleNamespace(model=SimpleNamespace(names={int(k): v for k, v in names.items()}, task=task),
                                          sha256=doc["model"]["sha256"])
                with patch("robot_dashboard.competition_traffic.model.LocalUltralytics", return_value=adapter):
                    if valid:
                        loaded = OwnerModel(path, cfg, acknowledge_trusted_pickle=True)
                        self.assertEqual(loaded.names, MODEL_CLASSES)
                    else:
                        with self.assertRaisesRegex(ValueError, "METADATA_MISMATCH"):
                            OwnerModel(path, cfg, acknowledge_trusted_pickle=True)

    def test_crosswalk_never_enters_color_route(self):
        detector = OwnerModel.__new__(OwnerModel)
        result = SimpleNamespace(orig_shape=(64, 64), boxes=SimpleNamespace(
            xyxy=np.array([[0., 0., 64., 64.]]*3), conf=np.array([.9]*3), cls=np.array([0., 1., 2.])))
        detector.adapter = SimpleNamespace(model=SimpleNamespace(predict=lambda **kw: [result]), allowed={0, 1})
        detector.confidence_floor = .25
        detector.inference_settings, detector.inference_settings_sha256 = settings(
            "full640", confidence_floor=.25, model_sha256="a"*64, color_policy=POLICY)
        self.assertEqual([d.class_id for d in detector.infer(lamp())], [0, 1])
        self.assertEqual(detector.last_diagnostics["non_allowlist_boxes"], 1)
        pipeline = TrafficPipeline(teammate_config(), TeammateDetector(2))
        with patch("robot_dashboard.competition_traffic.pipeline.classify_roi") as classify:
            observation = pipeline.process(frame(), now_s=0.)
        classify.assert_not_called()
        self.assertIn("DETECTION_INVALID", observation.signal["quality_flags"])

    def test_red_green_agreement_and_both_conflict_directions(self):
        for class_id, rgb, expected in [(0, (0, 230, 0), "GREEN"), (1, (0, 0, 230), "RED"),
                                        (0, (0, 0, 230), "AMBIGUOUS"), (1, (0, 230, 0), "AMBIGUOUS")]:
            with self.subTest(class_id=class_id, rgb=rgb):
                pipeline = TrafficPipeline(teammate_config(), TeammateDetector(class_id))
                for n in range(6):
                    obs = pipeline.process(frame(n, image=lamp(rgb)), now_s=n/10)
                self.assertEqual(obs.signal["raw_state"], expected)
                box = obs.context["free_observations"][0]
                self.assertEqual(box["class_name"], MODEL_CLASSES[str(class_id)])
                self.assertEqual(box["model_state"], "GREEN" if class_id == 0 else "RED")
                self.assertEqual(obs.context["selected_model_color"]["final_state"], expected)
                self.assertEqual(obs.signal["stable_state"], expected if expected != "AMBIGUOUS" else "UNKNOWN")
                self.assertFalse(obs.context["departure_authorized"])

    def test_colorless_and_reflection_inputs_do_not_inherit_model_green(self):
        for bgr in ((0, 0, 0), (255, 255, 255), (128, 128, 128), (246, 250, 246), (255, 0, 0)):
            for image in (lamp(bgr), np.full((64, 64, 3), bgr, np.uint8)):
                raw = classify_roi(image)
                result, diag = combine(raw, "traffic_light_green")
                self.assertEqual(result["raw_state"], "UNKNOWN")
                self.assertEqual(diag["model_state"], "GREEN")
                self.assertEqual(diag["c4_raw_state"], raw["raw_state"])
                self.assertIsNot(result, raw)

    def test_simultaneous_colors_and_exposure_settling(self):
        image = lamp((0, 230, 0))
        cv2.circle(image, (8, 8), 6, (0, 0, 230), -1)
        result, _ = combine(classify_roi(image), "traffic_light_green")
        self.assertEqual(result["raw_state"], "AMBIGUOUS")
        result, _ = combine(classify_roi(lamp(), exposure_settling=True), "traffic_light_green")
        self.assertEqual(result["raw_state"], "UNKNOWN")

    def test_consensus_hash_pinned_and_changed_settings_revoke_green(self):
        old = settings("full640", confidence_floor=.25, model_sha256="a"*64)
        detector = TeammateDetector()
        self.assertNotEqual(old[1], detector.inference_settings_sha256)
        pipeline = TrafficPipeline(teammate_config(), detector)
        for n in range(5):
            pipeline.process(frame(n), now_s=n/10)
        detector.inference_settings_sha256 = "b"*64
        obs = pipeline.process(frame(5), now_s=.5)
        self.assertEqual(obs.signal["stable_state"], "UNKNOWN")
        self.assertIn("INFERENCE_SETTINGS_CHANGED", obs.signal["quality_flags"])
        detector.inference_settings, detector.inference_settings_sha256 = old
        with self.assertRaisesRegex(ValueError, "COLOR_POLICY_SETTINGS_MISMATCH"):
            pipeline.process(frame(6), now_s=.6)
        self.assertIsNone(pipeline.latest)

    def test_new_sequence_retransmit_gap_and_reload_do_not_reuse_green(self):
        pipeline = TrafficPipeline(teammate_config(), TeammateDetector())
        for n in range(5):
            obs = pipeline.process(frame(n, image_handle="same-pixels"), now_s=n/10)
        self.assertEqual(obs.signal["stable_state"], "GREEN")
        repeated = pipeline.process(frame(4, received_s=.5, image_handle="same-pixels"), now_s=.5)
        self.assertEqual(repeated.context["first_received_s"], .4)
        self.assertIn("REPEATED_OR_REVERSED_FRAME", repeated.signal["quality_flags"])
        for f in (frame(8), frame(0, producer_epoch="reload", received_s=.9)):
            obs = pipeline.process(f, now_s=f.received_s)
            self.assertEqual(obs.signal["stable_state"], "UNKNOWN")

    def test_slow_inference_diagnostic_color_survives_without_freshness(self):
        pipeline = TrafficPipeline(teammate_config(), TeammateDetector(), clock=lambda: .4)
        obs = pipeline.process(frame(source_clock="synchronized_ros", source_age_s=.02), now_s=0.)
        self.assertEqual(obs.context["first_received_s"], 0.)
        self.assertAlmostEqual(obs.context["source_age_s"], .42)
        self.assertEqual(obs.context["free_observations"][0]["model_state"], "GREEN")
        self.assertEqual(obs.signal["stable_state"], "UNKNOWN")

    def test_bad_geometry_missing_detection_and_exceptions_fail_closed(self):
        for box in ((0, 0, 0, 0), (-10, -10, -1, -1), (-1, 0, 64, 64),
                    (64, 0, 0, 64), (0, 0, 90, 90), (0, 0, float("nan"), 64)):
            detector = TeammateDetector(detections=[Detection(box, .9, 0, "a")])
            pipeline = TrafficPipeline(teammate_config(), detector)
            obs = pipeline.process(frame(), now_s=0.)
            self.assertNotEqual(obs.signal["raw_state"], "GREEN")
            self.assertEqual(compare_color(None, lamp(), box)["reason"], "INVALID_NATIVE_CROP")
        for fail in (False, True):
            detector = TeammateDetector(detections=[])
            if fail:
                detector.infer = lambda bgr: (_ for _ in ()).throw(RuntimeError("test"))
            obs = TrafficPipeline(teammate_config(), detector).process(frame(), now_s=0.)
            self.assertEqual(obs.signal["raw_state"], "UNKNOWN")

    def test_multiple_signals_and_target_switch_reset_association(self):
        detector = TeammateDetector(detections=[Detection((0, 0, 64, 64), .9, 0, "a"),
                                               Detection((0, 0, 64, 64), .95, 1, "b")])
        pipeline = TrafficPipeline(teammate_config(), detector)
        obs = pipeline.process(frame(), now_s=0.)
        self.assertIsNone(obs.signal["roi_xyxy_native"])
        self.assertEqual(len(obs.context["free_observations"]), 2)
        detector.detections = [Detection((0, 0, 64, 64), .9, 0, "a")]
        for n in range(1, 8):
            pipeline.process(frame(n), now_s=n/10)
        detector.detections = [Detection((0, 0, 30, 30), .9, 0, "other")]
        obs = pipeline.process(frame(8), now_s=.8)
        self.assertEqual(obs.signal["stable_state"], "UNKNOWN")

    def test_no_pickle_ros_camera_or_upstream_execution_on_import(self):
        code = '''
import builtins, cv2
original = builtins.__import__
def guard(name, *args, **kwargs):
    if name.split('.')[0] in ('torch', 'ultralytics', 'rclpy', 'robot_node', 'behavior'):
        raise AssertionError(name)
    return original(name, *args, **kwargs)
builtins.__import__ = guard
cv2.VideoCapture = lambda *a: (_ for _ in ()).throw(AssertionError('camera'))
from robot_dashboard.competition_traffic import model, pipeline, teammate_compare
'''
        subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)

    def test_comparator_requires_source_ack_and_hash(self):
        with self.assertRaisesRegex(ValueError, "ACK_REQUIRED"):
            load_comparator("not-a-source")
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"raise AssertionError('must not execute')")
            f.flush()
            with self.assertRaisesRegex(ValueError, "CHECKSUM_MISMATCH"):
                load_comparator(f.name, acknowledge_source=True)

    def test_comparison_scores_remain_uncalibrated_and_exceptions_are_reported(self):
        stub = SimpleNamespace(detect_color=lambda *a: ("GREEN", 1.5),
                               detect_color_by_hue=lambda *a: ("GREEN", .8),
                               detect_color_combined=lambda *a: ("GREEN", 1.5))
        result = compare_color(stub, lamp(), [0, 0, 64, 64])
        self.assertEqual(result["combined"]["uncalibrated_score"], 1.5)
        self.assertFalse(result["score_is_probability"])
        self.assertGreaterEqual(result["combined"]["wall_s"], 0.)
        stub.detect_color = lambda *a: (_ for _ in ()).throw(RuntimeError("test"))
        self.assertEqual(compare_color(stub, lamp(), [0, 0, 64, 64])["reason"], "UPSTREAM_COLOR_EXCEPTION")

    def test_scoring_separates_missing_unreadable_and_wrong_green(self):
        label = {"id": "a", "label": "GREEN", "sha256": "a"*64, "roi_xyxy_native": [0, 0, 64, 64]}
        missing = score_target(label, [])
        self.assertFalse(missing["target_matched"])
        record = {"bbox_xyxy_native": [0, 0, 64, 64], "model_state": "RED", "c4_raw_state": "GREEN",
                  "upstream_state": "GREEN", "raw_state": "AMBIGUOUS"}
        conflict = score_target({**label, "label": "UNREADABLE"}, [record])
        result = summarize([missing, conflict])
        self.assertEqual(result["candidate"]["GREEN"]["states"], {"UNKNOWN": 1})
        self.assertEqual(result["candidate"]["UNREADABLE"]["states"], {"AMBIGUOUS": 1})
