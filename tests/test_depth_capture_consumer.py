"""Cross-task export contract only; no calibration algorithm or real accuracy."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from experiments.realsense_mount_calibration.calibration import _validate_sample
from robot_dashboard.depth_capture_store import DepthCaptureStore
from test_depth_capture_store import capture_fixture


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
