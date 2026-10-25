from dataclasses import replace
from types import SimpleNamespace
import unittest

from . import optional_deps  # noqa: F401
import numpy as np
from experiments.competition_vm.traffic_signals.detector import Detection
from robot_dashboard.competition_traffic.association import BoundedAssociation
from robot_dashboard.competition_traffic.inference import (
    settings,
    regions,
    interior_edge,
    native_nms,
)
from robot_dashboard.competition_traffic.model import OwnerModel
from robot_dashboard.competition_traffic.pipeline import TrafficPipeline
from robot_dashboard.competition_traffic.projection import (
    signal_fragment,
    signal_status,
)
from .helpers import config, frame, Detector, lamp


class RecoveryTests(unittest.TestCase):
    def test_profiles_are_fixed_and_hash_covers_resolution_confidence_model(self):
        p, h = settings(
            "upper-overlap640", confidence_floor=0.25, model_sha256="a" * 64
        )
        self.assertEqual(
            regions((1280, 720), p),
            [
                (0, 0, 1280, 720),
                (0, 0, 640, 432),
                (320, 0, 960, 432),
                (640, 0, 1280, 432),
            ],
        )
        for name, conf, sha in [
            ("full960", 0.25, "a" * 64),
            ("upper-overlap640", 0.1, "a" * 64),
            ("upper-overlap640", 0.25, "b" * 64),
        ]:
            self.assertNotEqual(
                h, settings(name, confidence_floor=conf, model_sha256=sha)[1]
            )
        with self.assertRaises(ValueError):
            settings(
                "label-specific-tile", confidence_floor=0.25, model_sha256="a" * 64
            )

    def test_tile_offsets_map_to_native_once_and_internal_cut_is_rejected(self):
        m = OwnerModel.__new__(OwnerModel)
        m.confidence_floor = 0.25
        m.inference_settings, m.inference_settings_sha256 = settings(
            "upper-overlap640", confidence_floor=0.25, model_sha256="a" * 64
        )
        image = np.zeros((720, 1280, 3), np.uint8)
        calls = []

        def predict(**kwargs):
            n = len(calls)
            calls.append(kwargs)
            boxes = (
                [[0.0, 10.0, 20.0, 40.0]]
                if n == 2
                else [[20.0, 10.0, 40.0, 40.0]]
                if n == 3
                else []
            )
            return [
                SimpleNamespace(
                    orig_shape=kwargs["source"].shape[:2],
                    boxes=SimpleNamespace(
                        xyxy=np.array(boxes),
                        conf=np.array([0.8] * len(boxes)),
                        cls=np.array([9] * len(boxes)),
                    ),
                )
            ]

        m.adapter = SimpleNamespace(model=SimpleNamespace(predict=predict), allowed={9})
        ds = m.infer(image)
        self.assertEqual([d.bbox for d in ds], [(660.0, 10.0, 680.0, 40.0)])
        self.assertEqual(m.last_diagnostics["tile_edge_rejected"], 1)
        self.assertTrue(all(c["imgsz"] == 640 for c in calls))
        self.assertTrue(interior_edge((5, 5, 640, 40), (0, 0, 640, 432), (1280, 720)))

    def test_native_fusion_keeps_distinct_signal_and_class(self):
        ds = [
            Detection((10, 10, 50, 60), 0.8, 9, "a"),
            Detection((11, 11, 51, 61), 0.9, 9, "b"),
            Detection((80, 10, 120, 60), 0.7, 9, "c"),
            Detection((10, 10, 50, 60), 0.6, 1, "d"),
        ]
        self.assertEqual([d.track_id for d in native_nms(ds)], ["b", "c", "d"])

    def test_occlusion_revokes_green_and_requires_two_new_detections(self):
        detector = Detector()
        p = TrafficPipeline(config(), detector)
        for n in range(5):
            o = p.process(frame(n), now_s=n / 10)
        self.assertEqual(o.signal["stable_state"], "GREEN")
        detector.detections = []
        self.assertEqual(
            p.process(frame(5), now_s=0.5).signal["stable_state"], "UNKNOWN"
        )
        detector.detections = None
        o = p.process(frame(6), now_s=0.6)
        self.assertIn("ASSOCIATION_REACQUIRING", o.signal["quality_flags"])
        self.assertEqual(o.context["free_observations"][0]["raw_state"], "GREEN")
        o = p.process(frame(7), now_s=0.7)
        self.assertEqual(o.signal["raw_state"], "GREEN")
        self.assertEqual(o.signal["stable_state"], "UNKNOWN")
        self.assertEqual(o.context["image_association"]["track_generation"], 2)

    def test_detection_indices_can_swap_without_selecting_other_geometry(self):
        a = BoundedAssociation()
        target = (0, 0, 40, 40)
        other = (70, 0, 110, 40)
        selected, _ = a.select(
            [Detection(target, 0.6, 9, "A"), Detection(other, 0.99, 9, "B")],
            target,
            ("bound",),
        )
        self.assertEqual(selected.bbox, target)
        selected, _ = a.select(
            [Detection(other, 0.99, 9, "A"), Detection(target, 0.6, 9, "B")],
            target,
            ("bound",),
        )
        self.assertEqual(selected.bbox, target)
        self.assertFalse(a.snapshot()["external_detection_ids_used"])

    def test_decode_or_model_failure_requires_fresh_reconfirmation(self):
        for failure in ("image", "model"):
            with self.subTest(failure=failure):
                detector = Detector()
                p = TrafficPipeline(config(), detector)
                for n in range(5):
                    p.process(frame(n), now_s=n/10)
                if failure == "model":
                    detector.sha256 = "0" * 64
                    bad = frame(5)
                else:
                    bad = replace(frame(5), bgr=None)
                o = p.process(bad, now_s=.5)
                self.assertEqual(o.signal["stable_state"], "UNKNOWN")
                self.assertEqual(o.context["image_association"]["status"], "unassociated")
                detector.sha256 = config().document["model"]["sha256"]
                o = p.process(frame(6), now_s=.6)
                self.assertIn("ASSOCIATION_REACQUIRING", o.signal["quality_flags"])

    def test_ambiguous_merge_and_geometry_jump_do_not_inherit_track(self):
        a = BoundedAssociation()
        roi = (0, 0, 100, 100)
        a.select([Detection((0, 0, 50, 100), 0.9, 9, "a")], roi, ("bound",))
        chosen, error = a.select(
            [
                Detection((0, 0, 50, 100), 0.9, 9, "a"),
                Detection((50, 0, 100, 100), 0.9, 9, "b"),
            ],
            roi,
            ("bound",),
        )
        self.assertIsNone(chosen)
        self.assertEqual(error, "ASSOCIATION_UNCERTAIN")
        self.assertEqual(
            a.select([Detection((0, 0, 50, 100), 0.9, 9, "new")], roi, ("bound",))[1],
            "ASSOCIATION_REACQUIRING",
        )
        a.select([Detection((0, 0, 50, 100), 0.9, 9, "new")], roi, ("bound",))
        chosen, error = a.select(
            [Detection((60, 0, 100, 100), 0.9, 9, "new")], roi, ("bound",)
        )
        self.assertIsNone(chosen)
        self.assertEqual(error, "TRACK_RESET")

    def test_detection_only_never_claims_association_even_with_verified_config(self):
        p = TrafficPipeline(config(), Detector(), observation_mode="detection-only")
        for n in range(5):
            o = p.process(frame(n, binding_id="free-view"), now_s=n / 10)
        self.assertEqual(o.context["observation_stage"], "detection-only")
        self.assertFalse(o.context["association_verified"])
        self.assertEqual(o.context["free_observations"][0]["raw_state"], "GREEN")
        self.assertEqual(o.signal["raw_state"], "UNKNOWN")
        self.assertEqual(o.signal["stable_state"], "UNKNOWN")
        self.assertIsNone(o.signal["roi_xyxy_native"])

    def test_lamp_experiment_does_not_rewrite_signal_color(self):
        image = lamp((255, 255, 255))
        outputs = []
        for option in (False, True):
            o = TrafficPipeline(config(), Detector(), lamp_experiment=option).process(
                frame(image=image), now_s=0.0
            )
            outputs.append(o.signal)
            if option:
                self.assertTrue(
                    o.context["free_observations"][0]["lamp_diagnostic"][
                        "diagnostic_only"
                    ]
                )
        self.assertEqual(outputs[0], outputs[1])

    def test_new_inference_hash_resets_previous_green_and_keeps_latency_visible(self):
        d = Detector()
        d.inference_settings_sha256 = "a" * 64
        p = TrafficPipeline(config(), d)
        for n in range(5):
            o = p.process(frame(n), now_s=n / 10)
        d.inference_settings_sha256 = "b" * 64
        o = p.process(frame(5), now_s=0.55)
        self.assertIn("INFERENCE_SETTINGS_CHANGED", o.signal["quality_flags"])
        self.assertEqual(o.signal["stable_state"], "UNKNOWN")
        self.assertEqual(o.context["inference_settings_sha256"], "b" * 64)
        self.assertAlmostEqual(o.context["queue_residence_s"], 0.05)

    def test_exact_c2_timing_example_first_receipt_positive_and_processed_receipt_rejected(
        self,
    ):
        p = TrafficPipeline(config(), Detector(), clock=lambda: 10.08)
        f = replace(
            frame(), source_clock="synchronized_ros", received_s=10.0, source_age_s=0.02
        )
        o = p.process(f, now_s=10.01)
        self.assertAlmostEqual(o.context["source_age_s"], 0.10)
        self.assertEqual(o.context["first_received_s"], 10.0)
        signal_fragment(o, now_s=10.15, received_s=10.0)
        with self.assertRaisesRegex(ValueError, "FIRST_RECEIPT_MISMATCH"):
            signal_fragment(o, now_s=10.15, received_s=10.08)
        self.assertIsNone(signal_status(p, now_s=10.240001)["fragment"])
        self.assertEqual(o.context["first_received_s"], 10.0)

    def test_slow_processing_leaves_raw_diagnostics_without_green_fragment(self):
        p = TrafficPipeline(config(), Detector(), clock=lambda: 0.4)
        o = p.process(frame(source_clock="synchronized_ros"), now_s=0.01)
        self.assertEqual(o.context["free_observations"][0]["raw_state"], "GREEN")
        self.assertIn("SOURCE_STALE", o.signal["quality_flags"])
        self.assertIsNone(signal_status(p, now_s=0.4)["fragment"])
