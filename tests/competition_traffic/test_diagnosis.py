from dataclasses import replace
import unittest

from . import optional_deps  # noqa: F401
from experiments.competition_vm.traffic_signals.detector import Detection
from robot_dashboard.competition_traffic.pipeline import TrafficPipeline
from robot_dashboard.competition_traffic.projection import signal_fragment, signal_status
from robot_dashboard.competition_traffic.replay_clock import ReplayClock
from .helpers import config, frame, Detector


class DiagnosisTests(unittest.TestCase):
    def test_box_outside_expected_roi_is_not_detector_missing(self):
        p = TrafficPipeline(config(roi=(0, 0, 10, 10)), Detector())
        o = p.process(frame(), now_s=0.)
        self.assertIn("EXPECTED_ROI_MISMATCH", o.signal["quality_flags"])
        self.assertNotIn("DETECTOR_MISSING", o.signal["quality_flags"])
        self.assertEqual(o.context["diagnostics"]["terminal_rejection"], "EXPECTED_ROI_MISMATCH")

    def test_confidence_and_absent_candidate_are_distinct(self):
        for ds, reason in [([], "DETECTOR_MISSING"), ([Detection((0, 0, 64, 64), .1, 0, "a")], "CONFIDENCE_REJECTED")]:
            p = TrafficPipeline(config(), Detector(ds))
            o = p.process(frame(), now_s=0.)
            self.assertIn(reason, o.signal["quality_flags"])

    def test_identity_cannot_be_laundered_by_receipt_or_content_nonce(self):
        p = TrafficPipeline(config(), Detector())
        for n in range(5):
            p.process(frame(n, source_age_s=.1), now_s=n/10)
        o = p.process(frame(4, received_s=.5, image_handle="new-nonce", source_age_s=0.), now_s=.5)
        self.assertIn("REPEATED_OR_REVERSED_FRAME", o.signal["quality_flags"])
        self.assertEqual(o.context["first_received_s"], .4)
        self.assertAlmostEqual(o.context["source_age_s"], .2)
        self.assertEqual(o.context["sequence"], 4)
        self.assertEqual(o.context["diagnostics"]["terminal_rejection"], "SOURCE_IDENTITY_REJECTED")

    def test_new_sequence_with_old_source_stamp_still_rejected(self):
        p = TrafficPipeline(config(), Detector())
        p.process(frame(), now_s=0.)
        o = p.process(frame(1, source_stamp_ns="0"), now_s=.1)
        self.assertIn("REPEATED_OR_REVERSED_FRAME", o.signal["quality_flags"])

    def test_receiver_rollback_is_not_hidden_by_new_epoch(self):
        p = TrafficPipeline(config(), Detector())
        p.process(frame(2), now_s=.2)
        o = p.process(frame(0, producer_epoch="new"), now_s=.3)
        self.assertIn("REPEATED_OR_REVERSED_FRAME", o.signal["quality_flags"])

    def test_projection_cannot_reanchor_first_receipt(self):
        p = TrafficPipeline(config(), Detector(), clock=lambda: .1)
        o = p.process(frame(source_clock="synchronized_ros", source_age_s=.02), now_s=0.)
        self.assertAlmostEqual(o.context["source_age_s"], .12)
        self.assertEqual(o.context["source_age_at_first_receipt_s"], .02)
        signal_fragment(o, now_s=.2)
        with self.assertRaisesRegex(ValueError, "FIRST_RECEIPT_MISMATCH"):
            signal_fragment(o, now_s=1., received_s=1.)
        with self.assertRaisesRegex(ValueError, "EXPIRED"):
            signal_fragment(o, now_s=.24)

    def test_availability_expires_without_reissuing_green_or_changing_last_valid_time(self):
        now = [0.]
        p = TrafficPipeline(config(), Detector(), clock=lambda: now[0])
        for n in range(5):
            now[0] = n/10
            p.process(frame(n, source_clock="synchronized_ros"), now_s=now[0])
        self.assertEqual(signal_status(p, now_s=.5)["fragment"]["stable_state"], "GREEN")
        stale = signal_status(p, now_s=.7)
        self.assertIsNone(stale["fragment"])
        self.assertEqual(stale["last_valid_observation_s"], .4)
        self.assertEqual(stale["first_received_s"], .4)
        self.assertEqual(stale["identity"]["sequence"], 4)
        p.invalidate()
        self.assertEqual(signal_status(p, now_s=.8)["reasons"], ["NO_OBSERVATION"])

    def test_source_timeline_never_charges_cpu_latency_as_capture_staleness(self):
        p = TrafficPipeline(config(), Detector(), clock=lambda: 999.)
        o = p.process(frame(), now_s=0.)
        self.assertEqual(o.context["source_age_s"], 0.)
        self.assertNotIn("SOURCE_STALE", o.signal["quality_flags"])

    def test_wall_workload_charges_latency_but_stays_fixture(self):
        p = TrafficPipeline(config(), Detector(), clock=lambda: .4, measure_wall_latency=True)
        o = p.process(frame(), now_s=0.)
        self.assertIn("SOURCE_STALE", o.signal["quality_flags"])
        with self.assertRaisesRegex(ValueError, "OFFLINE_REPLAY"):
            signal_fragment(o, now_s=.4)

    def test_wall_clock_backlog_preserves_scheduled_receipt(self):
        now = [10.]
        c = ReplayClock("wall-clock", clock=lambda: now[0], sleep=lambda dt: now.__setitem__(0, now[0]+dt))
        f, t = c.arrive(frame())
        self.assertEqual((f.received_s, t), (10., 10.))
        now[0] = 11.
        f, t = c.arrive(frame(1))
        self.assertEqual((f.received_s, t), (10.1, 11.))
        self.assertEqual(f.source_stamp_ns, "100000000")
        self.assertEqual(f.source_clock, "fixture")

    def test_nonmonotonic_replay_manifest_not_turned_into_fresh_samples(self):
        c = ReplayClock("source-timeline")
        c.arrive(frame())
        with self.assertRaisesRegex(ValueError, "NOT_INCREASING"):
            c.arrive(replace(frame(1), received_s=0.))

    def test_increasing_processing_latency_cannot_manufacture_stability_duration(self):
        finish = [0.]
        p = TrafficPipeline(config(), Detector(), clock=lambda: finish[0])
        for n in range(3):
            finish[0] = n * .2
            o = p.process(frame(n, source_clock="synchronized_ros"), now_s=n/10)
        self.assertEqual(o.signal["raw_state"], "GREEN")
        self.assertEqual(o.signal["stable_state"], "UNKNOWN")
        self.assertAlmostEqual(o.context["receiver_age_s"], .2)

    def test_label_metrics_exclude_unreadable_and_do_not_treat_unknown_as_green_success(self):
        from robot_dashboard.competition_traffic.diagnose import audit_case, metrics
        f = frame()
        base = {"id": "synthetic", "sha256": "a"*64, "split": "test", "label": "GREEN", "roi_xyxy_native": [0, 0, 64, 64]}
        r = audit_case(base, f.bgr, [])
        self.assertEqual(r["localized_raw_prediction"], "UNKNOWN")
        self.assertEqual(r["manual_crop_oracle"]["raw_state"], "GREEN")
        summary = metrics([r, {**r, "label": "UNREADABLE"}])
        self.assertEqual(summary["valid_green_rejected"], {"count": 1, "denominator": 1})
        self.assertEqual(summary["false_green"]["denominator"], 0)

    def test_loader_diagnostics_preserve_bgr_input_and_post_nms_class_counts(self):
        from types import SimpleNamespace
        import numpy as np
        from robot_dashboard.competition_traffic.model import OwnerModel
        model = OwnerModel.__new__(OwnerModel)
        image = frame().bgr
        calls = []
        result = SimpleNamespace(orig_shape=image.shape[:2], boxes=SimpleNamespace(
            xyxy=np.array([[1., 2., 10., 20.], [4., 5., 30., 31.]]),
            conf=np.array([.9, .8]), cls=np.array([0., 1.])))
        def predict(**kwargs):
            calls.append(kwargs)
            return [result]
        model.adapter = SimpleNamespace(model=SimpleNamespace(predict=predict), allowed={0})
        model.confidence_floor = .25
        detections = model.infer(image)
        self.assertIs(calls[0]["source"], image)
        self.assertEqual(calls[0]["device"], "cpu")
        self.assertEqual(calls[0]["conf"], .25)
        self.assertEqual(len(detections), 1)
        self.assertEqual(model.last_diagnostics["post_nms_boxes"], 2)
        self.assertEqual(model.last_diagnostics["non_allowlist_boxes"], 1)
        result.orig_shape = (32, 32)
        with self.assertRaisesRegex(ValueError, "ORIGINAL_SHAPE"):
            model.infer(image)

    def test_no_light_negative_counts_false_green_anywhere_in_image(self):
        from robot_dashboard.competition_traffic.diagnose import audit_case, metrics
        f = frame()
        label = {"id": "negative", "sha256": "b"*64, "split": "test", "label": "NO_LIGHT", "roi_xyxy_native": None}
        r = audit_case(label, f.bgr, [Detection((0, 0, 64, 64), .9, 0, "a")])
        self.assertEqual(metrics([r])["false_green"], {"count": 1, "denominator": 1})
