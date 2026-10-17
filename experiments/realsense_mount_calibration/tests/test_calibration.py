"""Deterministic synthetic checks; none of these tests imply hardware validation."""

import copy
import json
import math
import unittest

import numpy as np
from fastapi.testclient import TestClient

from app import app
from calibration import CalibrationError, estimate, export_analysis


def capture(sid, angle=0.0, *, normal=None, distance=2.0, synthetic=True):
    width, height = 160, 120
    k = {"fx": 140.0, "fy": 140.0, "cx": 80.0, "cy": 60.0}
    if normal is None:
        theta = math.radians(angle)
        normal = np.array([0.0, -math.sin(theta), math.cos(theta)])
    else:
        normal = np.array(normal, dtype=float)
        normal /= np.linalg.norm(normal)
    yy, xx = np.indices((height, width))
    denom = normal[0] * (xx - k["cx"]) / k["fx"] + normal[1] * (yy - k["cy"]) / k["fy"] + normal[2]
    depth = distance / denom
    points = [{"u": u, "v": v} for v in (20, 60, 100) for u in (20, 60, 100, 140)]
    return {"id": sid, "width": width, "height": height, "intrinsics": k,
            "depth_m": depth.ravel().tolist(), "points": points,
            "metadata": {"serial": "DEMO-ONLY", "frame_id": "camera_depth_optical_frame", "capture_id": sid, "rectified": True,
                         "synthetic": synthetic, "profile_id": "rectified-depth-160x120",
                         "depth_semantics": "optical_z", "depth_units": "m",
                         "source_timestamp": 1000.0, "clock_domain": "synthetic",
                         "depth_frame_id": "camera_depth_optical_frame", "image_frame_id": "camera_depth_optical_frame"}}


def request(*samples, reference_id=None):
    if not samples:
        samples = (capture("reference"), capture("tilt", 10))
    return {"samples": list(samples), "reference_id": reference_id or samples[0]["id"],
            "robot_stationary_confirmed": True, "wall_same_confirmed": True,
            "mount_only_pitch_confirmed": True}


class CalibrationTests(unittest.TestCase):
    def test_known_signed_pitch_and_normal(self):
        result = estimate(request(capture("zero"), capture("down", 10), capture("up", -8)))
        self.assertEqual(result["status"], "RELATIVE_ONLY")
        self.assertFalse(result["body_extrinsic_validated"])
        self.assertFalse(result["absolute_pitch_validated"])
        self.assertTrue(result["synthetic"])
        for sample, angle in zip(result["samples"], (0, 10, -8)):
            self.assertAlmostEqual(sample["relative_pitch_deg"], angle, places=6)
            np.testing.assert_allclose(sample["normal_camera"], [0, -math.sin(math.radians(angle)), math.cos(math.radians(angle))], atol=1e-8)
            self.assertLess(sample["plane_rmse_m"], 1e-10)
            self.assertEqual(sample["inlier_points"], 12)

    def test_explicit_nonfirst_reference(self):
        result = estimate(request(capture("ten", 10), capture("twenty", 20), reference_id="twenty"))
        self.assertAlmostEqual(result["samples"][0]["relative_pitch_deg"], -10, places=6)
        self.assertEqual(result["samples"][1]["relative_pitch_deg"], 0)

    def test_nonzero_lateral_normal_not_forced_zero(self):
        initial = np.array([.2, 0, math.sqrt(.96)])
        theta = math.radians(10)
        tilted = [initial[0], -math.sin(theta) * initial[2], math.cos(theta) * initial[2]]
        result = estimate(request(capture("ref", normal=initial), capture("pitch", normal=tilted)))
        self.assertAlmostEqual(result["samples"][1]["relative_pitch_deg"], 10, places=3)
        self.assertAlmostEqual(result["samples"][1]["normal_camera"][0], .2, places=4)

    def test_duplicate_ids_and_reference_rejected(self):
        for field in ("duplicate_id", "missing_reference", "duplicate_capture"):
            payload = request()
            if field == "duplicate_id":
                payload["samples"][1]["id"] = payload["samples"][0]["id"]
            elif field == "missing_reference":
                payload["reference_id"] = "missing"
            else:
                meta = payload["samples"][1]["metadata"]
                meta["capture_id"] = "reference"
            with self.subTest(field=field), self.assertRaises(CalibrationError):
                estimate(payload)

    def test_mismatched_metadata_rejected(self):
        changes = {"serial": "another-camera", "profile_id": "another-profile", "frame_id": "another_optical_frame",
                   "depth_semantics": "ray_range", "synthetic": False,
                   "rectified": False, "depth_frame_id": "wrong-frame",
                   "image_frame_id": "wrong-frame", "clock_domain": "unmatched",
                   "projection_model": "fisheye", "depth_units": "mm",
                   "distortion_model": "brown_conrady"}
        for key, value in changes.items():
            payload = request()
            payload["samples"][1]["metadata"][key] = value
            with self.subTest(key=key), self.assertRaises(CalibrationError):
                estimate(payload)

    def test_frame_id_is_shared_coordinate_frame(self):
        payload = request()
        self.assertEqual(payload["samples"][0]["metadata"]["frame_id"], payload["samples"][1]["metadata"]["frame_id"])
        self.assertEqual(estimate(payload)["status"], "RELATIVE_ONLY")
        for sample in payload["samples"]:
            sample["metadata"].pop("capture_id")
        self.assertEqual(estimate(payload)["status"], "RELATIVE_ONLY")
        for sample in payload["samples"]:
            sample["metadata"]["frame_number"] = 1
        with self.assertRaisesRegex(CalibrationError, "frame_number"):
            estimate(payload)

    def test_raw_source_frames_can_be_different(self):
        payload = request()
        for sample in payload["samples"]:
            sample["metadata"]["raw_depth_frame_id"] = "camera_depth_optical_frame"
            sample["metadata"]["raw_image_frame_id"] = "camera_color_optical_frame"
        self.assertEqual(estimate(payload)["status"], "RELATIVE_ONLY")

    def test_huge_numbers_are_validation_errors(self):
        payload = request()
        payload["samples"][0]["intrinsics"]["fx"] = 10 ** 1000
        with self.assertRaises(CalibrationError):
            estimate(payload)
        payload = request()
        payload["samples"][0]["depth_m"][0] = 10 ** 1000
        with self.assertRaises(CalibrationError):
            estimate(payload)

    def test_real_capture_provenance_required(self):
        for field in ("profile_id", "depth_semantics", "source_timestamp", "clock_domain"):
            payload = request(capture("a", synthetic=False), capture("b", 10, synthetic=False))
            del payload["samples"][1]["metadata"][field]
            with self.subTest(field=field), self.assertRaisesRegex(CalibrationError, field):
                estimate(payload)

    def test_valid_real_capture_still_not_verified(self):
        result = estimate(request(capture("a", synthetic=False), capture("b", 10, synthetic=False)))
        self.assertFalse(result["synthetic"])
        self.assertFalse(result["body_extrinsic_validated"])
        self.assertEqual(result["capture_verification"], "USER_ASSERTED_NOT_INDEPENDENTLY_VERIFIED")

    def test_mismatched_intrinsics_rejected(self):
        payload = request()
        payload["samples"][1]["intrinsics"]["fx"] += 1
        with self.assertRaisesRegex(CalibrationError, "intrinsics"):
            estimate(payload)

    def test_stereo_stream_and_model_mismatch_rejected(self):
        for field, first, second in (("stream_index", 1, 2), ("camera_model", "D435", "D455"),
                                     ("stream_type", "depth", "color"), ("format", "Z16", "RGB8")):
            payload = request()
            payload["samples"][0]["metadata"][field] = first
            payload["samples"][1]["metadata"][field] = second
            with self.subTest(field=field), self.assertRaisesRegex(CalibrationError, field):
                estimate(payload)

    def test_nonplanar_points_rejected(self):
        payload = request()
        sample = payload["samples"][1]
        depth = np.array(sample["depth_m"]).reshape(sample["height"], sample["width"])
        offsets = [0.1, -.22, .31, -.44, .53, -.36, .17, -.58, .69, -.50, .41, -.12]
        for point, offset in zip(sample["points"], offsets):
            depth[point["v"] - 2:point["v"] + 3, point["u"] - 2:point["u"] + 3] += offset
        sample["depth_m"] = depth.ravel().tolist()
        with self.assertRaisesRegex(CalibrationError, "planar consensus"):
            estimate(payload)

    def test_missing_confirmations_rejected(self):
        for field in ("robot_stationary_confirmed", "wall_same_confirmed", "mount_only_pitch_confirmed"):
            for value in (False, None, 1, "true"):
                payload = request()
                payload[field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(CalibrationError, field):
                    estimate(payload)

    def test_collinear_and_clustered_rejected(self):
        for points in ([{"u": u, "v": 60} for u in (20, 40, 60, 80, 100, 120)],
                       [{"u": u, "v": v} for u in (79, 80, 81) for v in (59, 60)],
                       [{"u": 80, "v": 60}] * 6):
            payload = request()
            payload["samples"][1]["points"] = points
            with self.subTest(points=points), self.assertRaises(CalibrationError):
                estimate(payload)

    def test_outliers_robustly_rejected(self):
        payload = request()
        sample = payload["samples"][1]
        depth = np.array(sample["depth_m"]).reshape(sample["height"], sample["width"])
        for p in sample["points"][:3]:
            depth[p["v"] - 2:p["v"] + 3, p["u"] - 2:p["u"] + 3] += .35
        sample["depth_m"] = depth.ravel().tolist()
        result = estimate(payload)["samples"][1]
        self.assertAlmostEqual(result["relative_pitch_deg"], 10, places=6)
        self.assertEqual(result["inlier_points"], 9)
        self.assertAlmostEqual(result["inlier_ratio"], .75)
        self.assertTrue(any("outliers" in warning for warning in result["warnings"]))

    def test_invalid_depth_and_insufficient_picks_rejected(self):
        for invalid in (0, -1, None, 100, float("nan"), float("inf")):
            payload = request()
            sample = payload["samples"][1]
            sample["depth_m"] = [invalid] * (sample["width"] * sample["height"])
            with self.subTest(invalid=invalid), self.assertRaises(CalibrationError):
                estimate(payload)
        payload = request()
        payload["samples"][1]["points"] = payload["samples"][1]["points"][:5]
        with self.assertRaises(CalibrationError):
            estimate(payload)

    def test_some_depth_holes_can_be_excluded(self):
        payload = request()
        sample = payload["samples"][1]
        depth = np.array(sample["depth_m"]).reshape(sample["height"], sample["width"])
        point = sample["points"][0]
        depth[point["v"] - 2:point["v"] + 3, point["u"] - 2:point["u"] + 3] = 0
        sample["depth_m"] = depth.ravel().tolist()
        result = estimate(payload)["samples"][1]
        self.assertEqual(result["valid_points"], 11)
        self.assertFalse(result["validated_points"][0]["valid"])

    def test_depth_discontinuity_point_excluded(self):
        payload = request()
        sample = payload["samples"][1]
        depth = np.array(sample["depth_m"]).reshape(sample["height"], sample["width"])
        point = sample["points"][0]
        depth[point["v"] - 2:point["v"] + 3, point["u"]:point["u"] + 3] += 1
        sample["depth_m"] = depth.ravel().tolist()
        result = estimate(payload)["samples"][1]
        self.assertEqual(result["valid_points"], 11)
        self.assertEqual(result["validated_points"][0]["reason"], "depth discontinuity in neighborhood")

    def test_nonpitch_rotation_withholds_angle(self):
        result = estimate(request(capture("ref"), capture("yaw", normal=[.25, -.1, .96])))
        sample = result["samples"][1]
        self.assertFalse(result["pitch_only_consistent"])
        self.assertFalse(sample["pitch_only_consistent"])
        self.assertIsNone(sample["relative_pitch_deg"])
        self.assertIsInstance(sample["relative_pitch_candidate_deg"], float)
        self.assertGreater(sample["lateral_normal_change"], .04)

    def test_changed_distance_warns(self):
        result = estimate(request(capture("ref"), capture("moved", 10, distance=2.2)))
        self.assertTrue(any("Wall distance changed" in warning for warning in result["samples"][1]["warnings"]))

    def test_shapes_types_and_bounds(self):
        for field, value in (("width", 641), ("height", 481), ("width", True), ("depth_m", []), ("points", [])):
            payload = request()
            payload["samples"][1][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(CalibrationError):
                estimate(payload)
        payload = request()
        payload["samples"][1]["points"][0] = {"u": 160, "v": 30}
        with self.assertRaises(CalibrationError):
            estimate(payload)
        payload = request()
        payload["samples"] *= 7
        with self.assertRaises(CalibrationError):
            estimate(payload)

    def test_determinism_and_no_input_mutation(self):
        payload = request()
        original = copy.deepcopy(payload)
        self.assertEqual(estimate(payload), estimate(payload))
        self.assertEqual(payload, original)

    def test_export_recomputes(self):
        payload = request()
        result = export_analysis(payload)
        self.assertEqual(result["input"], payload)
        self.assertEqual(result["analysis"], estimate(payload))
        payload["robot_stationary_confirmed"] = False
        with self.assertRaises(CalibrationError):
            export_analysis(payload)


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_offline(self):
        result = self.client.get("/api/health")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["mode"], "offline")
        self.assertFalse(result.json()["camera_connected"])
        self.assertFalse(result.json()["persistence"])

    def test_estimate_and_export(self):
        payload = request()
        result = self.client.post("/api/estimate", json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.headers["cache-control"], "no-store")
        self.assertAlmostEqual(result.json()["samples"][1]["relative_pitch_deg"], 10, places=6)
        export = self.client.post("/api/export", json=payload)
        self.assertEqual(export.status_code, 200, export.text)
        self.assertEqual(export.json()["analysis"], result.json())
        self.assertIn("attachment", export.headers["content-disposition"])

    def test_errors_are_readable(self):
        result = self.client.post("/api/estimate", json=request(reference_id="missing"))
        self.assertEqual(result.status_code, 422)
        self.assertIn("reference_id", result.json()["detail"])

    def test_non_json_nan_and_body_limit(self):
        self.assertEqual(self.client.post("/api/estimate", content="{}").status_code, 415)
        result = self.client.post("/api/estimate", content='{"x": NaN}', headers={"content-type": "application/json"})
        self.assertEqual(result.status_code, 422)
        result = self.client.post("/api/estimate", content="{}", headers={"content-type": "application/json", "content-length": str(65 * 1024 * 1024)})
        self.assertEqual(result.status_code, 413)

    def test_nonfinite_and_huge_numbers_never_export(self):
        for value in (float("nan"), float("inf"), -float("inf"), 10 ** 400):
            for location in ("depth", "metadata"):
                payload = request()
                if location == "depth":
                    payload["samples"][0]["depth_m"][0] = value
                else:
                    payload["samples"][0]["metadata"]["unrecognized_field"] = value
                for route in ("/api/estimate", "/api/export"):
                    with self.subTest(value=str(value), location=location, route=route):
                        result = self.client.post(route, content=json.dumps(payload), headers={"content-type": "application/json"})
                        self.assertEqual(result.status_code, 422, result.text)
        payload = json.dumps(request())
        payload = payload[:-1] + ', "unrecognized_metadata": 1e309}'
        for route in ("/api/estimate", "/api/export"):
            result = self.client.post(route, content=payload, headers={"content-type": "application/json"})
            self.assertEqual(result.status_code, 422, result.text)

    def test_deep_unknown_metadata_rejected(self):
        payload = request()
        extra = {}
        payload["extra"] = extra
        for _ in range(30):
            extra["nested"] = {}
            extra = extra["nested"]
        for route in ("/api/estimate", "/api/export"):
            result = self.client.post(route, json=payload)
            self.assertEqual(result.status_code, 422, result.text)


if __name__ == "__main__":
    unittest.main()
