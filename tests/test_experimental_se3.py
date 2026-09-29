"""Offline-only SE(3) experiment; no ROS node, pose apply, or control transport."""

import copy
import math
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from robot_dashboard.relocalization.experimental_se3 import (
    Cloud,
    ExperimentalSE3Error,
    compose,
    from_translation_quaternion,
    from_translation_rpy,
    inverse,
    matrix_to_quaternion_xyzw,
    quaternion_xyzw_to_matrix,
    register_se3,
    rotation_error_rad,
    transform_points,
    validate_experimental_result,
    validate_transform,
)


ROOT = Path(__file__).resolve().parents[1]


def structured_scene():
    coordinates = np.linspace(-2, 2, 21)
    floor = np.array([(x, y, 0.0) for x in coordinates for y in coordinates])
    heights = np.linspace(0.0, 2.0, 13)
    pillar = np.array([(1.2 + 0.25 * math.cos(angle), -0.7 + 0.25 * math.sin(angle), z)
                       for z in heights for angle in np.linspace(0, 2 * math.pi, 24, endpoint=False)])
    wall = np.array([(-1.7, y, z) for y in np.linspace(-1.5, 1.5, 17)
                     for z in np.linspace(0.0, 1.5, 11)])
    return np.vstack((floor, pillar, wall))


def run(reference, query, initial=None):
    return register_se3(
        Cloud(reference, "map", "REGISTERED_MAP"),
        Cloud(query, "camera_init", "REGISTERED_QUERY", stamp_ns=1_000_000_000),
        np.eye(4) if initial is None else initial,
    )


class ExperimentalSE3Tests(unittest.TestCase):
    def test_quaternion_inverse_composition_and_target_source_convention(self):
        transform = from_translation_rpy([0.4, -0.3, 0.2], [0.13, -0.08, 0.24])
        self.assertTrue(np.allclose(compose(transform, inverse(transform)), np.eye(4), atol=1e-9))
        point = np.array([[0.3, -0.5, 1.1]])
        self.assertTrue(np.allclose(transform_points(inverse(transform),
                                                   transform_points(transform, point)), point))
        quaternion = matrix_to_quaternion_xyzw(transform[:3, :3])
        self.assertTrue(np.allclose(quaternion_xyzw_to_matrix(quaternion), transform[:3, :3]))
        self.assertTrue(np.allclose(from_translation_quaternion(transform[:3, 3], quaternion), transform))
        self.assertAlmostEqual(rotation_error_rad(transform, transform), 0.0, places=7)

    def test_invalid_rotation_quaternion_and_units_fail_before_registration(self):
        reflection = np.eye(4)
        reflection[0, 0] = -1
        for invalid in (reflection, np.ones((4, 4)), np.eye(3)):
            with self.subTest(invalid=invalid.shape), self.assertRaises(ExperimentalSE3Error):
                validate_transform(invalid)
        with self.assertRaises(ExperimentalSE3Error):
            quaternion_xyzw_to_matrix([0.0, 0.0, 0.0, 0.5])
        scene = structured_scene()
        with self.assertRaises(ExperimentalSE3Error):
            register_se3(Cloud(scene, "map", "REGISTERED_MAP", unit="mm"),
                         Cloud(scene, "camera_init", "REGISTERED_QUERY", stamp_ns=1), np.eye(4))

    def test_registered_cloud_recovers_height_and_tilt_without_projecting_to_se2(self):
        reference = structured_scene()
        truth = from_translation_rpy([0.15, -0.12, 0.18], [0.09, -0.07, 0.11])
        query = transform_points(inverse(truth), reference)
        result = run(reference, query)
        self.assertEqual(result["schema"], "robot-scope.experimental-se3-result.v1")
        self.assertTrue(result["experimental"])
        self.assertEqual(result["transform_convention"], "T_target_source")
        self.assertEqual(result["status"], "CANDIDATE")
        self.assertLess(np.linalg.norm(np.array([result["pose"][axis] for axis in "xyz"])
                                       - truth[:3, 3]), 0.03)
        self.assertAlmostEqual(result["pose"]["roll_rad"], 0.09, delta=0.02)
        self.assertAlmostEqual(result["pose"]["pitch_rad"], -0.07, delta=0.02)
        self.assertLess(result["metrics"]["rmse_m"], 0.03)

    def test_partial_view_retains_a_bounded_candidate(self):
        reference = structured_scene()
        truth = from_translation_rpy([0.12, -0.08, 0.14], [0.07, 0.04, -0.06])
        query = transform_points(inverse(truth), reference[reference[:, 0] > -0.5])
        result = run(reference, query)
        self.assertEqual(result["status"], "CANDIDATE")
        self.assertLess(result["metrics"]["rmse_m"], 0.08)

    def test_single_plane_wrong_map_and_far_seed_reject(self):
        floor = structured_scene()[:441]
        truth = from_translation_rpy([0.1, -0.1, 0.2], [0.1, 0.07, 0.0])
        result = run(floor, transform_points(inverse(truth), floor))
        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["reason"], "DEGENERATE_GEOMETRY")
        self.assertLess(result["metrics"]["geometry_min_max_eigen_ratio"], 0.002)
        reference = structured_scene()
        self.assertEqual(run(reference + [20, 20, 20], reference)["status"], "REJECTED")
        far_seed = from_translation_rpy([20, 20, 20], [0, 0, 0])
        self.assertEqual(run(reference, reference, far_seed)["status"], "REJECTED")

    def test_repeated_structure_exposes_two_distinct_local_solutions(self):
        rng = np.random.default_rng(7)
        module = rng.uniform(-0.4, 0.4, size=(250, 3))
        reference = np.vstack((module + [-2, 0, 0], module + [2, 0, 0]))
        left = run(reference, module, from_translation_rpy([-2, 0, 0], [0, 0, 0]))
        right = run(reference, module, from_translation_rpy([2, 0, 0], [0, 0, 0]))
        self.assertEqual(left["status"], "CANDIDATE")
        self.assertEqual(right["status"], "CANDIDATE")
        self.assertGreater(abs(left["pose"]["x"] - right["pose"]["x"]), 3.5)
        self.assertLess(abs(left["metrics"]["rmse_m"] - right["metrics"]["rmse_m"]), 1e-5)

    def test_raw_cloud_and_missing_time_are_not_silently_fused(self):
        scene = structured_scene()
        with self.assertRaises(ExperimentalSE3Error):
            register_se3(Cloud(scene, "map", "REGISTERED_MAP"),
                         Cloud(scene, "lidar", "RAW_SENSOR", stamp_ns=1), np.eye(4))
        with self.assertRaises(ExperimentalSE3Error):
            register_se3(Cloud(scene, "map", "REGISTERED_MAP"),
                         Cloud(scene, "camera_init", "REGISTERED_QUERY"), np.eye(4))

    def test_experimental_result_schema_rejects_tampering_and_se2_projection(self):
        scene = structured_scene()
        truth = from_translation_rpy([0.12, -0.08, 0.09], [0.06, -0.04, 0.05])
        result = run(scene, transform_points(inverse(truth), scene))
        self.assertEqual(validate_experimental_result(result), result)
        schema_path = ROOT / "docs" / "contracts" / "relocalization" / "experimental-se3-result-v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema"]["const"], result["schema"])
        self.assertIn("z", schema["properties"]["pose"]["required"])
        for mutate in (
            lambda value: value.update(experimental=False),
            lambda value: value["pose"].pop("z"),
            lambda value: value["pose"].update(quaternion_xyzw=[0, 0, 0, 1]),
            lambda value: value["metrics"].update(overlap_ratio=0.1),
            lambda value: value["metrics"].update(runtime_ms=float("nan")),
            lambda value: value.update(status="REJECTED"),
        ):
            tampered = copy.deepcopy(result)
            mutate(tampered)
            with self.subTest(tampered=tampered.get("status")), self.assertRaises(ExperimentalSE3Error):
                validate_experimental_result(tampered)

    def test_cli_compares_identical_synthetic_inputs_without_se2_projection(self):
        compiler = shutil.which("c++")
        if compiler is None:
            self.skipTest("C++17 compiler is unavailable")
        with tempfile.TemporaryDirectory(prefix="robot-scope-se3-test-") as directory:
            output = Path(directory) / "result.json"
            executable = Path(directory) / "robot_scope_offline_registration"
            package = ROOT / "ros2" / "robot_scope_registration"
            subprocess.run([
                compiler, "-std=c++17", "-O2", f"-I{package / 'include'}",
                str(package / "src" / "registration_core.cpp"),
                str(package / "src" / "offline_registration_cli.cpp"),
                "-o", str(executable),
            ], check=True, timeout=60)
            completed = subprocess.run([
                sys.executable, str(ROOT / "scripts" / "benchmark_experimental_se3.py"),
                "--se2-executable", str(executable), "--output", str(output),
                "--require-expected",
            ], check=True, capture_output=True, text=True, timeout=90)
            summary = json.loads(completed.stdout)
            report = json.loads(output.read_text(encoding="utf-8"))
            repeated_output = Path(directory) / "result-repeat.json"
            repeated_command = [*completed.args]
            repeated_command[repeated_command.index(str(output))] = str(repeated_output)
            subprocess.run(repeated_command, check=True, capture_output=True, text=True, timeout=90)
            repeated = json.loads(repeated_output.read_text(encoding="utf-8"))
        self.assertEqual(report["schema"], "robot-scope.experimental-se3-benchmark.v1")
        self.assertEqual(report["case_count"], 11)
        self.assertEqual(report["candidate_count"], 6)
        self.assertEqual(report["false_candidate_count"], 0)
        self.assertEqual(report["expected_status_mismatch_count"], 0)
        self.assertTrue(report["repeated_structure_seed_ambiguity"])
        self.assertEqual(report["module_sha256"], summary["module_sha256"])
        self.assertEqual(report["manifest_sha256"], repeated["manifest_sha256"])
        self.assertEqual(
            [(case["id"], case["se3"]["status"], case["se3"]["reason"])
             for case in report["cases"]],
            [(case["id"], case["se3"]["status"], case["se3"]["reason"])
             for case in repeated["cases"]],
        )
        cases = {record["id"]: record for record in report["cases"]}
        self.assertEqual(cases["tilted-query"]["se3"]["status"], "CANDIDATE")
        self.assertLess(cases["tilted-query"]["se3_position_error_m"], 0.03)
        self.assertLess(cases["tilted-query"]["se3_rotation_error_deg"], 1.0)
        self.assertEqual(cases["tilted-query"]["se2"]["z_roll_pitch"],
                         "UNAVAILABLE_BY_CONTRACT")
        self.assertEqual(cases["ground-removed"]["se3"]["reason"], "HIGH_RESIDUAL")
        self.assertEqual(cases["flat-ground-only"]["se3"]["reason"], "DEGENERATE_GEOMETRY")
        self.assertEqual(cases["wrong-map"]["se3"]["status"], "REJECTED")
        self.assertEqual(cases["far-initial-pose"]["se3"]["status"], "REJECTED")
        self.assertNotIn("truth_t_target_source", cases["repeated-left-seed"])


if __name__ == "__main__":
    unittest.main()
