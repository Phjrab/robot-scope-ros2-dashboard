"""Independent numerical stress cases; exclusively synthetic, never bag evidence."""

from copy import deepcopy
from dataclasses import asdict
import unittest

import numpy as np

from robot_dashboard.offline_slam.core import (
    Settings, inverse, optimize, pose, project, register,
)
from robot_dashboard.offline_slam.demo import fixture
from robot_dashboard.offline_slam.maps import rebuild
from robot_dashboard.offline_slam.record import Recorder


def partial_fixture(seed=182):
    """Restrict visibility to 3.4 m XY, drop 18%, add 15 mm XYZ noise."""
    data = fixture()
    truth = []
    rng = np.random.default_rng(seed)
    for k, frame in enumerate(data["keyframes"]):
        drift = pose(np.array([0.45, 0.2, 0.08, 0.02, 0.01, 0.07]) * (k / 20))
        truth.append(inverse(drift) @ np.asarray(frame["T_parent_body"]))
        points = np.asarray(frame["points"])
        points = points[np.linalg.norm(points[:, :2], axis=1) < 3.4]
        points = points[rng.random(len(points)) > 0.18]
        frame["points"] = (points + rng.normal(0, 0.015, points.shape)).tolist()
    return data, np.asarray(truth)


def translation_rmse(poses, truth):
    delta = np.asarray(poses)[:, :3, 3] - truth[:, :3, 3]
    return float(np.sqrt(np.mean(np.sum(delta**2, axis=1))))


def doubled_geometry():
    source = np.random.default_rng(10).uniform([-2, -2, -1], [2, 2, 1], (200, 3))
    return source, np.concatenate([source, source + [0, 0, 0.35]])


class StressTests(unittest.TestCase):
    def test_noisy_partial_loops_improve_ground_truth_error_over_multiple_seeds(self):
        settings = Settings(search_radius=1.2, min_separation=10, correspondence=0.35)
        for seed in (21, 182, 909):
            with self.subTest(seed=seed):
                data, truth = partial_fixture(seed)
                before = deepcopy(data)
                result = optimize(data, settings)
                self.assertEqual(data, before)
                self.assertEqual(result["state"], "SUCCEEDED")
                self.assertGreater(result["metrics"]["accepted_loops"], 0)
                self.assertLess(result["metrics"]["final_cost"], 0.6)
                self.assertLess(result["metrics"]["endpoint_gap_after_m"], 0.04)
                self.assertLess(translation_rmse(result["poses_after"], truth), 0.1)
                self.assertLess(
                    translation_rmse(result["poses_after"], truth),
                    translation_rmse(result["poses_before"], truth) * 0.4,
                )
                np.testing.assert_array_equal(result["poses_before"][0], result["poses_after"][0])

    def test_default_correspondence_conservatively_rejects_partial_case(self):
        data, _ = partial_fixture()
        result = optimize(data, Settings(search_radius=1.2, min_separation=10))
        self.assertEqual(result["state"], "NO_LOOP")
        self.assertTrue(result["candidates"])
        self.assertTrue(all(c["reason"] == "HIGH_RESIDUAL" for c in result["candidates"]))

    def test_deformed_duplicate_layer_rejected_in_both_registration_directions(self):
        source, target = doubled_geometry()
        for a, b in ((source, target), (target, source)):
            with self.subTest(source_count=len(a)):
                measurement, metrics = register(a, b, np.eye(4), Settings())
                self.assertIsNone(measurement)
                self.assertEqual(metrics["reason"], "HIGH_RESIDUAL")
                self.assertEqual(metrics["overlap"], 1.0)
                self.assertGreater(metrics["rmse_m"], 0.12)
        _, metrics = register(source, target, np.eye(4), Settings())
        self.assertLess(metrics["forward_rmse_m"], 1e-12)
        self.assertGreater(metrics["reverse_rmse_m"], 0.2)

    def test_deformed_false_loop_never_enters_optimizer(self):
        data = fixture()
        data["keyframes"] = data["keyframes"][:4]
        source, target = doubled_geometry()
        for frame, xy in zip(data["keyframes"], ((0, 0), (4, 0), (4, 4), (0.1, 0))):
            frame["T_parent_body"] = pose(np.array([*xy, 0, 0, 0, 0])).tolist()
        data["keyframes"][0]["points"] = target.tolist()
        data["keyframes"][-1]["points"] = source.tolist()
        result = optimize(data, Settings(min_separation=3))
        self.assertEqual(result["state"], "NO_LOOP")
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["reason"], "HIGH_RESIDUAL")
        self.assertNotIn("poses_after", result)

    def test_unrelated_nearby_clouds_rejected(self):
        rng = np.random.default_rng(56)
        a, b = rng.uniform(-2, 2, (2, 300, 3))
        measurement, metrics = register(a, b, np.eye(4), Settings())
        self.assertIsNone(measurement)
        self.assertEqual(metrics["reason"], "HIGH_RESIDUAL")

    def test_rigid_3d_alignment_with_noise_and_unequal_sampling(self):
        rng = np.random.default_rng(76)
        source = rng.uniform(-2, 2, (500, 3))
        expected = pose(np.array([0.13, -0.08, 0.1, 0.1, -0.07, 0.08]))
        target = project(source, expected) + rng.normal(0, 0.007, source.shape)
        target = target[rng.random(len(target)) > 0.1]
        measured, metrics = register(source, target, np.eye(4), Settings(correspondence=0.25))
        self.assertEqual(metrics["reason"], "ACCEPTED")
        np.testing.assert_allclose(measured, expected, atol=0.005)

    def test_keyframes_accumulate_motion_and_capture_rotation_only(self):
        recorder = Recorder("synthetic-calibration")
        local = np.random.default_rng(34).uniform(-2, 2, (100, 3))
        vectors = ([0, 0, 0, 0, 0, 0], [0.2, 0, 0, 0, 0, 0],
                   [0.31, 0, 0, 0, 0, 0], [0.31, 0, 0, 0.16, 0, 0])
        for k, value in enumerate(vectors):
            transform = pose(np.array(value))
            recorder.add("pose", (k + 1) * 1_000_000_000, transform, "camera_init", "body")
            recorder.add("cloud", (k + 1) * 1_000_000_000, project(local, transform), "camera_init")
        self.assertEqual([f["stamp_ns"] for f in recorder.data["keyframes"]],
                         [1_000_000_000, 3_000_000_000, 4_000_000_000])


class MapProjectionTests(unittest.TestCase):
    def make_map(self, extra=()):
        data = fixture()
        data["keyframes"] = data["keyframes"][:3]
        data["sensor_origin_body"] = [1, 0, 0]
        points = [[2, 0, 1]] * 30 + list(extra)
        for frame in data["keyframes"]:
            frame["points"] = points
        corrected = pose(np.array([10, 20, 0, 0, 0, np.pi / 2]))
        result = {"settings": asdict(Settings()), "poses_after": [corrected.tolist()] * 3}
        return rebuild(data, result), project(points, corrected)

    def test_pcd_and_pgm_use_corrected_pose_and_calibrated_ray_origin(self):
        assets, expected = self.make_map()
        binary = assets["optimized.pcd"].split(b"DATA binary\n", 1)[1]
        actual = np.frombuffer(binary, dtype="<f4").reshape(-1, 3)
        np.testing.assert_allclose(actual, np.tile(expected, (3, 1)), atol=1e-5)
        _, shape, _, payload = assets["map.pgm"].split(b"\n", 3)
        width, height = map(int, shape.split())
        raster = np.frombuffer(payload, dtype=np.uint8).reshape(height, width)[::-1]
        # The transformed sensor is (10,21), the return is (10,22).
        origin = assets["map.yaml"].decode().split("origin: [", 1)[1].split("]", 1)[0]
        lower = np.array([float(v) for v in origin.split(",")[:2]])
        start = np.floor((np.array([10, 21]) - lower) / 0.1).astype(int)
        hit = np.floor((np.array([10, 22]) - lower) / 0.1).astype(int)
        self.assertEqual(raster[start[1], start[0]], 254)
        self.assertEqual(raster[hit[1], hit[0]], 0)

    def test_discarded_height_and_range_returns_do_not_expand_grid(self):
        original, _ = self.make_map()
        # These valid local points remain in the 3D PCD, but have no 2D ray.
        for extra in ([500, 0, 100], [500, 0, 1]):
            with self.subTest(extra=extra):
                assets, _ = self.make_map([extra])
                self.assertEqual(assets["map.pgm"], original["map.pgm"])
                self.assertEqual(assets["map.yaml"], original["map.yaml"])
                self.assertNotEqual(assets["optimized.pcd"], original["optimized.pcd"])

    def test_empty_height_band_rejects_map(self):
        data = fixture()
        result = {"settings": asdict(Settings(min_height=4, max_height=5)),
                  "poses_after": [f["T_parent_body"] for f in data["keyframes"]]}
        with self.assertRaisesRegex(ValueError, "NO_POINTS_IN_HEIGHT_BAND"):
            rebuild(data, result)


if __name__ == "__main__":
    unittest.main()
