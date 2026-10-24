from contextlib import redirect_stdout, redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import optional_deps  # noqa: F401 -- dependency guard precedes optional imports

import cv2
from robot_dashboard.competition_traffic.config import TrafficConfig
from robot_dashboard.competition_traffic.model import OwnerModel
from robot_dashboard.competition_traffic.replay import main
from robot_dashboard.competition_traffic.replay_input import inspect_inputs, iter_frames
from .helpers import config, lamp, Detector


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.images = self.root / "input"
        self.images.mkdir()
        self.input = self.images / "sample.jpg"
        cv2.imwrite(str(self.input), lamp())

    def cli(self, *args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return main(["--input", str(self.input), "--output", str(self.root / "output"), "--fps", "5", *args])

    def test_dry_run_decodes_without_weights(self):
        with patch("robot_dashboard.competition_traffic.model.OwnerModel", side_effect=AssertionError("must not load")):
            self.assertEqual(self.cli("--dry-run"), 2)
        report = json.loads((self.root / "output/summary.json").read_text())
        self.assertEqual(report["real_rgb_decode"], "PASS")
        self.assertEqual(report["real_model_inference"], "NOT_RUN")

    def test_corrupt_image_nonzero_exit(self):
        self.input.write_bytes(b"invalid jpeg")
        self.assertEqual(self.cli("--dry-run"), 4)
        report = json.loads((self.root / "output/summary.json").read_text())
        self.assertEqual(report["decode_errors"], 1)

    def test_existing_output_is_preserved(self):
        (self.root / "output").mkdir()
        keep = self.root / "output/keep.txt"
        keep.write_text("preserve")
        self.assertEqual(self.cli("--dry-run"), 3)
        self.assertEqual(keep.read_text(), "preserve")

    def test_missing_model_does_not_claim_inference(self):
        self.assertEqual(self.cli(), 2)
        self.assertFalse((self.root / "output/frames").exists())

    def test_changed_input_rejected_after_inspection(self):
        items = inspect_inputs(self.input)
        self.input.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "INPUT_CHANGED"):
            list(iter_frames(items, fps=5, binding_id="binding"))

    def test_directory_does_not_follow_external_image_symlink(self):
        outside = self.root / "outside.jpg"
        cv2.imwrite(str(outside), lamp())
        (self.images / "escape.jpg").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "SYMLINK_ESCAPE"):
            inspect_inputs(self.images)

    def test_manifest_preserves_real_gaps_as_virtual_clock(self):
        manifest = self.images / "input.jsonl"
        digest = hashlib.sha256(self.input.read_bytes()).hexdigest()
        manifest.write_text("\n".join(json.dumps({"image": self.input.name, "sha256": digest,
                                               "replay_time_s": t}) for t in (0., .7)))
        frames = list(iter_frames(inspect_inputs(manifest), fps=5, binding_id="binding"))
        self.assertEqual(frames[1].received_s, .7)
        self.assertEqual(frames[1].source_clock, "fixture")
        self.assertEqual(frames[1].source_stamp_ns, "700000000")

    def test_file_video_only(self):
        video = self.root / "input.avi"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 5., (64, 64))
        self.assertTrue(writer.isOpened())
        for color in [(0, 230, 0), (0, 0, 230), (230, 230, 230)]:
            writer.write(lamp(color))
        writer.release()
        frames = list(iter_frames(inspect_inputs(video), fps=5, binding_id="binding"))
        self.assertEqual(len(frames), 3)
        self.assertEqual(frames[-1].original_metadata["video_frame_index"], 2)

    def test_model_sha_and_pickle_guard_precede_vm_loader(self):
        weights = self.root / "owner.pt"
        weights.write_bytes(b"untrusted-data")
        doc = config().document
        doc["model"]["sha256"] = hashlib.sha256(weights.read_bytes()).hexdigest()
        with patch("robot_dashboard.competition_traffic.model.LocalUltralytics", side_effect=AssertionError("no load")):
            with self.assertRaisesRegex(ValueError, "TRUSTED_PICKLE_ACK"):
                OwnerModel(weights, TrafficConfig.parse(doc))
            doc["model"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "CHECKSUM"):
                OwnerModel(weights, TrafficConfig.parse(doc), acknowledge_trusted_pickle=True)

    def test_loaded_model_names_must_match(self):
        weights = self.root / "owner.pt"
        weights.write_bytes(b"synthetic loader test")
        doc = config().document
        doc["model"].update(sha256=hashlib.sha256(weights.read_bytes()).hexdigest(), trusted_pickle=True)
        class Wrong:
            names = {0: "crosswalk"}
        class FakeVM:
            model = Wrong()
        with patch("robot_dashboard.competition_traffic.model.LocalUltralytics", return_value=FakeVM()):
            with self.assertRaisesRegex(ValueError, "CLASS_NAME_MISMATCH"):
                OwnerModel(weights, TrafficConfig.parse(doc), acknowledge_trusted_pickle=True)

    def test_full_cli_uses_detector_and_writes_artifacts(self):
        model = self.root / "stub.onnx"
        model.write_bytes(b"not actual onnx; test loader injection")
        doc = config().document
        digest = hashlib.sha256(model.read_bytes()).hexdigest()
        doc["model"]["sha256"] = digest
        cfg = self.root / "config.json"
        cfg.write_text(json.dumps(doc))
        detector = Detector()
        detector.sha256 = digest
        with patch("robot_dashboard.competition_traffic.model.OwnerModel", return_value=detector):
            self.assertEqual(self.cli("--model", str(model), "--config", str(cfg)), 0)
        self.assertEqual(len(list((self.root / "output/frames").glob("*.png"))), 3)
        obs = json.loads((self.root / "output/observations.jsonl").read_text())
        self.assertFalse(obs["context"]["departure_authorized"])

    def test_failed_setup_summary_never_says_pass(self):
        self.assertEqual(self.cli("--config", str(self.root / "missing.json")), 3)
        self.assertEqual(json.loads((self.root / "output/summary.json").read_text())["status"], "FAILED")

    def test_strict_config_rejects_guessed_class_map_and_unknown_keys(self):
        for key, value in [("class_map", {}), ("min_confidence", True), ("extra", True)]:
            doc = config().document
            doc[key] = value
            with self.assertRaises(ValueError):
                TrafficConfig.parse(doc)


if __name__ == "__main__":
    unittest.main()
