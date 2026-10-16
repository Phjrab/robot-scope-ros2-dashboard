import copy
import hashlib
import json
import math
from pathlib import Path
import stat
import tempfile
import unittest

import numpy as np

from robot_dashboard.pose_precision import (
    EVIDENCE_ROLES,
    INPUT_SCHEMA,
    PosePrecisionError,
    evaluate,
    inverse,
    transform,
)
from scripts.evaluate_pose_precision import evaluate_file, main


def se3(parent, child, xyz=(0, 0, 0), yaw=0):
    return {
        "parent_frame": parent,
        "child_frame": child,
        "translation_m": list(xyz),
        "quaternion_xyzw": [0, 0, math.sin(yaw / 2), math.cos(yaw / 2)],
    }


def fixture():
    return {
        "schema": INPUT_SCHEMA,
        "evidence_type": "synthetic",
        "units": "m_rad",
        "convention": "T_parent_child_column_vectors",
        "frames": {
            "world": "survey",
            "map": "slam_map",
            "camera": "camera_link",
            "body": "base_link",
        },
        "camera_axes": "ros_link_x_forward_y_left_z_up",
        "body_axes": "ros_x_forward_y_left_z_up",
        "provenance": {
            "truth_method": "surveyed_rigid_target",
            "truth_independent_of_estimate": True,
            "alignment_independent_of_evaluation_samples": True,
            "extrinsic_independently_measured": True,
            "mount_unchanged": True,
            "current_camera_chain_verified": True,
            "instrument_id": "FAKE",
            "mount_id": "FAKE",
            "measured_at_utc": "2026-01-01T00:00:00Z",
            "estimate_source_commit": "a" * 40,
            "estimate_runtime_identity": "FAKE",
            "estimate_config_sha256": "b" * 64,
        },
        "evidence": {
            role: {
                "path": role + ".txt",
                "sha256": hashlib.sha256(role.encode()).hexdigest(),
            }
            for role in EVIDENCE_ROLES
        },
        "uncertainty": {
            role: {"translation_bound_m": 0.001, "rotation_bound_rad": 0.002}
            for role in ("truth", "extrinsic", "world_alignment")
        },
        "timing": {
            "estimate_clock": "FAKE_EST",
            "truth_clock": "FAKE_TRUTH",
            "offset_convention": "estimate_ns=truth_ns+offset_ns",
            "truth_to_estimate_offset_ns": "0",
            "offset_uncertainty_ns": "0",
            "max_pair_skew_ns": "20",
            "offset_measured_independently": True,
            "matching": "mutual_unique_nearest_no_interpolation",
        },
        "fixed_transforms": {
            "T_world_map": se3("survey", "slam_map"),
            "T_body_camera": se3("base_link", "camera_link"),
        },
        "estimate": {
            "acquisition_id": "FAKE_EST",
            "parent_frame": "slam_map",
            "child_frame": "camera_link",
            "epoch": "estimate-1",
            "samples": [
                {
                    "stamp_ns": "100",
                    "epoch": "estimate-1",
                    "pose": se3("slam_map", "camera_link"),
                }
            ],
        },
        "truth": {
            "acquisition_id": "FAKE_TRUTH",
            "parent_frame": "survey",
            "child_frame": "base_link",
            "epoch": "truth-1",
            "samples": [
                {
                    "stamp_ns": "100",
                    "epoch": "truth-1",
                    "pose": se3("survey", "base_link"),
                }
            ],
        },
    }


class PosePrecisionTests(unittest.TestCase):
    def test_noncommuting_world_camera_body_chain_and_known_error(self):
        data = fixture()
        data["fixed_transforms"]["T_world_map"] = se3(
            "survey", "slam_map", (2, 1, 0.2), math.pi / 2
        )
        data["fixed_transforms"]["T_body_camera"] = se3(
            "base_link", "camera_link", (0.3, -0.2, 0.1), math.pi / 2
        )
        # Body at [4, 3, 1] yaw0 -> world camera [4.3,2.8,1.1] yaw90.
        # In map this is [1.8,-2.3,.9] yaw0. Wrong inversion/order is observable.
        data["estimate"]["samples"][0]["pose"] = se3(
            "slam_map", "camera_link", (1.8, -2.3, 0.9)
        )
        data["truth"]["samples"][0]["pose"] = se3("survey", "base_link", (4, 3, 1))
        result = evaluate(data)
        self.assertAlmostEqual(result["position_error_m"]["max"], 0)
        self.assertAlmostEqual(result["rotation_error_rad"]["max"], 0)
        data["truth"]["samples"][0]["pose"] = se3(
            "survey", "base_link", (3, 3, 1), math.pi / 2
        )
        result = evaluate(data)
        self.assertAlmostEqual(result["position_error_m"]["rmse"], 1)
        self.assertAlmostEqual(result["rotation_error_rad"]["rmse"], math.pi / 2)
        self.assertFalse(result["accuracy_acceptance"])
        self.assertFalse(result["body_extrinsic_qualified_by_tool"])

    def test_quaternion_sign_and_pi_rotation(self):
        data = fixture()
        data["estimate"]["samples"][0]["pose"]["quaternion_xyzw"] = [0, 0, 0, -1]
        self.assertEqual(evaluate(data)["rotation_error_rad"]["max"], 0)
        data["estimate"]["samples"][0]["pose"]["quaternion_xyzw"] = [1, 0, 0, 0]
        self.assertAlmostEqual(evaluate(data)["rotation_error_rad"]["max"], math.pi)

    def test_se3_matrix_shear_reflection_scale_and_nonfinite_rejected(self):
        for index, value in [
            ((0, 1), 0.1),
            ((0, 0), -1),
            ((0, 0), 2),
            ((0, 3), float("nan")),
            ((3, 0), 1),
        ]:
            matrix = np.eye(4)
            matrix[index] = value
            with (
                self.subTest(index=index, value=value),
                self.assertRaises(PosePrecisionError),
            ):
                transform(
                    {
                        "parent_frame": "a",
                        "child_frame": "b",
                        "T_parent_child": matrix.tolist(),
                    },
                    "a",
                    "b",
                )
        value = se3("a", "b", (1, 2, 3), 0.4)
        matrix = transform(value, "a", "b")
        np.testing.assert_allclose(inverse(matrix) @ matrix, np.eye(4), atol=1e-12)

    def test_frame_direction_nonunit_boolean_and_representation_ambiguity_rejected(
        self,
    ):
        cases = [
            dict(parent_frame="camera_link"),
            dict(quaternion_xyzw=[0, 0, 0, 2]),
            dict(translation_m=[True, 0, 0]),
            dict(T_parent_child=np.eye(4).tolist()),
        ]
        for change in cases:
            data = fixture()
            data["fixed_transforms"]["T_body_camera"].update(change)
            with self.subTest(change=change), self.assertRaises(PosePrecisionError):
                evaluate(data)

    def test_unqualified_provenance_and_slam_truth_rejected(self):
        for change in [
            {"truth_method": "FAST_LIO"},
            {"truth_independent_of_estimate": False},
            {"alignment_independent_of_evaluation_samples": False},
            {"mount_unchanged": False},
            {"current_camera_chain_verified": False},
            {"estimate_source_commit": "main"},
        ]:
            data = fixture()
            data["provenance"].update(change)
            with self.subTest(change=change), self.assertRaises(PosePrecisionError):
                evaluate(data)

    def test_unknown_uncertainty_and_identical_truth_or_acquisition_rejected(self):
        cases = []
        a = fixture()
        a["uncertainty"]["truth"]["translation_bound_m"] = None
        cases.append(a)
        a = fixture()
        a["uncertainty"]["extrinsic"]["rotation_bound_rad"] = -1
        cases.append(a)
        a = fixture()
        a["evidence"]["truth"] = copy.deepcopy(a["evidence"]["estimate"])
        cases.append(a)
        a = fixture()
        a["truth"]["acquisition_id"] = "FAKE_EST"
        cases.append(a)
        for data in cases:
            with self.assertRaises(PosePrecisionError):
                evaluate(data)

    def test_optical_axes_must_be_explicit_and_extrinsic_names_exact(self):
        data = fixture()
        data["frames"]["camera"] = "left_optical"
        with self.assertRaisesRegex(PosePrecisionError, "optical"):
            evaluate(data)
        data["camera_axes"] = "optical_x_right_y_down_z_forward"
        with self.assertRaisesRegex(PosePrecisionError, "frame"):
            evaluate(data)

    def test_nanosecond_precision_and_offset_sign(self):
        data = fixture()
        data["estimate"]["samples"][0]["stamp_ns"] = "1792149540723526656"
        data["truth"]["samples"][0]["stamp_ns"] = "1792149540723526156"
        data["timing"]["truth_to_estimate_offset_ns"] = "500"
        self.assertEqual(evaluate(data)["pairs"][0]["pair_skew_ns"], "0")
        data["timing"]["truth_to_estimate_offset_ns"] = "-500"
        with self.assertRaisesRegex(PosePrecisionError, "no unambiguous"):
            evaluate(data)

    def test_timing_uncertainty_is_inside_skew_budget(self):
        data = fixture()
        data["truth"]["samples"][0]["stamp_ns"] = "90"
        data["timing"]["offset_uncertainty_ns"] = "10"
        self.assertEqual(evaluate(data)["matched_pairs"], 1)
        data["timing"]["offset_uncertainty_ns"] = "11"
        with self.assertRaises(PosePrecisionError):
            evaluate(data)

    def test_strict_stamps_epoch_and_tie_fail_closed(self):
        for stamp in [100, 100.1, "0100", "-1", str(2**63)]:
            data = fixture()
            data["estimate"]["samples"][0]["stamp_ns"] = stamp
            with self.subTest(stamp=stamp), self.assertRaises(PosePrecisionError):
                evaluate(data)
        for stamp, epoch in [
            ("100", "estimate-1"),
            ("99", "estimate-1"),
            ("101", "other"),
        ]:
            data = fixture()
            row = copy.deepcopy(data["estimate"]["samples"][0])
            row.update(stamp_ns=stamp, epoch=epoch)
            data["estimate"]["samples"].append(row)
            with (
                self.subTest(stamp=stamp, epoch=epoch),
                self.assertRaises(PosePrecisionError),
            ):
                evaluate(data)
        data = fixture()
        first = data["truth"]["samples"][0]
        first["stamp_ns"] = "90"
        second = copy.deepcopy(first)
        second["stamp_ns"] = "110"
        data["truth"]["samples"].append(second)
        with self.assertRaisesRegex(PosePrecisionError, "no unambiguous"):
            evaluate(data)

    def test_no_truth_reuse_and_unmatched_coverage_preserved(self):
        data = fixture()
        second = copy.deepcopy(data["estimate"]["samples"][0])
        second["stamp_ns"] = "110"
        data["estimate"]["samples"].append(second)
        data["truth"]["samples"][0]["stamp_ns"] = "106"
        result = evaluate(data)
        self.assertEqual(result["matched_pairs"], 1)
        self.assertEqual(result["pairs"][0]["estimate_index"], 1)
        self.assertEqual(result["unmatched_estimate_samples"], 1)
        self.assertEqual(result["estimate_matched_fraction"], 0.5)
        self.assertFalse(result["alignment_fitted"])

    def test_recorded_label_does_not_certify_self_reported_calibration(self):
        data = fixture()
        data["evidence_type"] = "recorded_real"
        result = evaluate(data)
        self.assertFalse(result["independent_truth_verified_by_tool"])
        self.assertFalse(result["body_extrinsic_qualified_by_tool"])
        self.assertFalse(result["accuracy_acceptance"])


class PosePrecisionFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.manifest = fixture()
        for role in EVIDENCE_ROLES:
            content = (
                json.dumps(self.manifest[role])
                if role in {"estimate", "truth"}
                else role
            )
            (self.directory / (role + ".txt")).write_text(content)
            self.manifest["evidence"][role]["sha256"] = hashlib.sha256(
                content.encode()
            ).hexdigest()
        self.input = self.directory / "input.json"
        self.write()

    def write(self):
        self.input.write_text(json.dumps(self.manifest))

    def test_file_hashes_no_overwrite_and_private_output(self):
        result = evaluate_file(self.input)
        self.assertTrue(result["evidence_bytes_verified"])
        self.assertEqual(
            result["manifest_sha256"],
            hashlib.sha256(self.input.read_bytes()).hexdigest(),
        )
        output = self.directory / "result.json"
        self.assertEqual(main([str(self.input), "--output", str(output)]), 0)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        before = output.read_bytes()
        with self.assertRaises(SystemExit):
            main([str(self.input), "--output", str(output)])
        self.assertEqual(before, output.read_bytes())

    def test_tampered_artifact_and_path_escape_rejected(self):
        (self.directory / "truth.txt").write_text("changed")
        with self.assertRaisesRegex(PosePrecisionError, "hash mismatch"):
            evaluate_file(self.input)
        self.manifest["evidence"]["truth"]["path"] = "/etc/hosts"
        self.write()
        with self.assertRaisesRegex(PosePrecisionError, "relative"):
            evaluate_file(self.input)
        self.manifest["evidence"]["truth"]["path"] = "../outside.txt"
        self.write()
        (self.directory / "outside-link").symlink_to("/etc/hosts")
        self.manifest["evidence"]["truth"]["path"] = "outside-link"
        self.write()
        with self.assertRaisesRegex(PosePrecisionError, "escapes"):
            evaluate_file(self.input)

    def test_pose_samples_must_match_hashed_series(self):
        self.manifest["estimate"]["samples"][0]["pose"]["translation_m"] = [1, 0, 0]
        self.write()
        with self.assertRaisesRegex(PosePrecisionError, "does not match artifact"):
            evaluate_file(self.input)

    def test_duplicate_and_nonfinite_json_and_empty_template_blocked(self):
        self.input.write_text('{"schema":"x","schema":"y"}')
        with self.assertRaisesRegex(PosePrecisionError, "duplicate"):
            evaluate_file(self.input)
        self.input.write_text('{"schema":NaN}')
        with self.assertRaisesRegex(PosePrecisionError, "nonfinite"):
            evaluate_file(self.input)
        output = self.directory / "blocked.json"
        example = (
            Path(__file__).resolve().parents[1]
            / "docs/integration-acceptance/pose_precision_input.example.json"
        )
        self.assertEqual(main([str(example), "--output", str(output)]), 2)
        result = json.loads(output.read_text())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["position_error_m"])
        self.assertFalse(result["body_extrinsic_qualified_by_tool"])


if __name__ == "__main__":
    unittest.main()
