"""Deterministic synthetic checks; none of these tests imply hardware validation."""

import ast
import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from fastapi import FastAPI

from robot_dashboard.api.routers import mount_calibration as mount_api

from robot_dashboard.mount_calibration import CalibrationError, estimate, export_analysis


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
    def test_failed_neighborhood_retains_every_point_and_sample_diagnostics(self):
        payload = request()
        sample = payload["samples"][0]
        sample["points"] = sample["points"][:6]
        depth = np.array(sample["depth_m"]).reshape(sample["height"], sample["width"])
        for point in sample["points"]:
            u, v = point["u"], point["v"]
            depth[v - 2:v + 3, u - 2:u + 3] = 0
            depth[v, u] = 2.0  # A valid single pixel cannot pass the 5x5 gate.
        sample["depth_m"] = depth.ravel().tolist()
        with self.assertRaises(CalibrationError) as raised:
            estimate(payload)
        diagnostics = raised.exception.diagnostics
        self.assertEqual(diagnostics["status"], "QUALITY_REJECTED")
        self.assertEqual(len(diagnostics["samples"]), 2)
        rejected, passed = diagnostics["samples"]
        self.assertEqual(rejected["failure_code"], "INSUFFICIENT_NEIGHBORHOOD_DEPTH")
        self.assertEqual(rejected["valid_points"], 0)
        self.assertEqual(rejected["selected_points"], 6)
        self.assertEqual(len(rejected["validated_points"]), 6)
        point = rejected["validated_points"][0]
        self.assertTrue(point["center_valid"])
        self.assertEqual(point["neighborhood_valid_fraction"], 1 / 25)
        self.assertEqual(point["neighborhood_required_count"], 13)
        self.assertIsNone(point["plane_residual_m"])
        self.assertEqual(passed["status"], "PLANE_ACCEPTED")
        self.assertNotIn("relative_pitch_deg", json.dumps(diagnostics))
        json.dumps(diagnostics, allow_nan=False)

    def test_discontinuity_diagnostics_and_boundary_patch_keep_existing_thresholds(self):
        payload = request()
        sample = payload["samples"][0]
        sample["points"] = [{"u": 0, "v": 0}] + sample["points"]
        depth = np.array(sample["depth_m"]).reshape(sample["height"], sample["width"])
        point = sample["points"][1]
        depth[point["v"] - 2:point["v"] + 3, point["u"] - 2:point["u"]] = 5
        sample["depth_m"] = depth.ravel().tolist()
        result = estimate(payload)["samples"][0]
        corner, rejected = result["validated_points"][:2]
        self.assertEqual(corner["neighborhood_pixel_count"], 9)
        self.assertEqual(corner["neighborhood_required_count"], 5)
        self.assertEqual(rejected["reason"], "depth discontinuity in neighborhood")
        self.assertEqual(rejected["neighborhood_valid_fraction"], 1)
        self.assertEqual(rejected["neighborhood_iqr_m"], 3)
        self.assertEqual(rejected["discontinuity_limit_m"], .06)
        self.assertFalse(rejected["valid"])
        self.assertIsNone(rejected["plane_residual_m"])
        self.assertEqual(result["diagnostics"]["status"], "PLANE_ACCEPTED")

    def test_failed_six_point_consensus_retains_candidate_residuals_without_pitch(self):
        payload = request()
        sample = payload["samples"][0]
        sample["points"] = [sample["points"][i] for i in (0, 1, 3, 8, 9, 11)]
        point = sample["points"][-1]
        depth = np.array(sample["depth_m"]).reshape(sample["height"], sample["width"])
        depth[point["v"] - 2:point["v"] + 3, point["u"] - 2:point["u"] + 3] += .2
        sample["depth_m"] = depth.ravel().tolist()
        with self.assertRaisesRegex(CalibrationError, "planar consensus") as raised:
            estimate(payload)
        detail = raised.exception.diagnostics["samples"][0]
        self.assertEqual(detail["minimum_inlier_points"], 6)
        self.assertEqual(detail["inlier_points"], 5)
        self.assertEqual(detail["failure_code"], "NO_PLANAR_CONSENSUS")
        self.assertEqual(detail["residual_basis"], "rejected_candidate_plane")
        self.assertGreater(detail["validated_points"][-1]["plane_residual_m"], .1)
        self.assertEqual(detail["validated_points"][-1]["reason"], "outside plane tolerance")
        self.assertGreater(detail["pixel_distribution"]["width_fraction"], .5)
        self.assertNotIn("pitch_proxy_deg", detail)

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



class MountCalibrationApiTests(unittest.IsolatedAsyncioTestCase):
    """Synthetic ASGI requests only; no socket, TestClient, runtime or hardware."""

    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(mount_api.router)
        self.app.state.runtime = RuntimeMustNotBeUsed()

    async def request(self, method, endpoint, *, body=None, raw=None, headers=None, chunks=None,
                      forbid_body_read=False):
        path = "/api/v1/settings/mount-calibration/" + endpoint
        values = {"host": "testserver", "origin": "http://testserver", "content-type": "application/json"}
        values.update(headers or {})
        payload = raw if raw is not None else json.dumps(body if body is not None else {}).encode()
        pieces = chunks if chunks is not None else [payload]
        queue = [dict(type="http.request", body=piece, more_body=i < len(pieces) - 1)
                 for i, piece in enumerate(pieces)]
        messages = []

        async def receive():
            if forbid_body_read:
                raise AssertionError("The origin/type/size guard must reject before reading the body.")
            return queue.pop(0) if queue else {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        scope = dict(type="http", asgi={"version": "3.0", "spec_version": "2.4"},
                     http_version="1.1", method=method, scheme="http", path=path,
                     raw_path=path.encode(), query_string=b"", root_path="",
                     server=("testserver", 80), client=("127.0.0.1", 1000),
                     headers=[(k.lower().encode(), v.encode()) for k, v in values.items() if v is not None])
        await self.app(scope, receive, send)
        start = next(message for message in messages if message["type"] == "http.response.start")
        content = b"".join(message.get("body", b"") for message in messages
                           if message["type"] == "http.response.body")
        return SimpleNamespace(status=start["status"], content=content,
                               json=lambda: json.loads(content), headers=dict(start["headers"]))

    async def test_status_without_runtime_or_origin_is_offline_and_uncached(self):
        response = await self.request("GET", "status", headers={"origin": None}, forbid_body_read=True)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()["mode"], "offline")
        self.assertEqual(response.json()["input_source"], "imported_depth_json")
        for field in ("live_capture_available", "hardware_access", "persistence",
                      "body_extrinsic_validated", "absolute_pitch_validated"):
            self.assertIs(response.json()[field], False, field)
        self.assertEqual(response.json()["schema_version"], "1.0.0")
        self.assertEqual(response.json()["max_request_bytes"], 64 * 1024 * 1024)
        self.assertEqual(response.headers[b"cache-control"], b"no-store")

    async def test_estimate_and_export_recompute_canonical_relative_only_result(self):
        payload = request(capture("seated-reference", 14), capture("tilted", 24))
        expected = estimate(payload)
        response = await self.request("POST", "estimate", body=payload)
        self.assertEqual(response.status, 200, response.content)
        self.assertEqual(response.json(), expected)
        self.assertAlmostEqual(response.json()["samples"][1]["relative_pitch_deg"], 10, places=6)
        self.assertEqual(response.json()["samples"][0]["relative_pitch_deg"], 0)
        self.assertAlmostEqual(response.json()["samples"][0]["pitch_proxy_deg"], 14, places=6)
        exported = await self.request("POST", "export", body=payload)
        self.assertEqual(exported.status, 200, exported.content)
        self.assertEqual(exported.json()["analysis"], expected)
        self.assertEqual(exported.json()["input"], payload)
        self.assertEqual(exported.json()["export_kind"], "relative_wall_pitch_analysis")
        for item in (response, exported):
            self.assertEqual(item.headers[b"cache-control"], b"no-store")
            self.assertEqual(item.headers[b"content-type"], b"application/json")
        self.assertEqual(exported.headers[b"content-disposition"],
                         b'attachment; filename="relative-wall-pitch-analysis.json"')

    async def test_quality_rejection_returns_diagnostics_but_never_exports_an_angle(self):
        payload = request()
        sample = payload["samples"][0]
        sample["points"] = sample["points"][:6]
        depth = np.array(sample["depth_m"]).reshape(sample["height"], sample["width"])
        for point in sample["points"]:
            depth[point["v"] - 2:point["v"] + 3, point["u"] - 2:point["u"] + 3] = 0
            depth[point["v"], point["u"]] = 2.0
        sample["depth_m"] = depth.ravel().tolist()
        for endpoint in ("estimate", "export"):
            response = await self.request("POST", endpoint, body=payload)
            self.assertEqual(response.status, 422)
            self.assertIsInstance(response.json()["detail"], str)
            diagnostics = response.json()["diagnostics"]
            self.assertEqual(len(diagnostics["samples"]), 2)
            self.assertEqual(diagnostics["status"], "QUALITY_REJECTED")
            self.assertFalse(diagnostics["relative_angles_available"])
            self.assertNotIn("relative_pitch_deg", response.content.decode())
            self.assertNotIn(b"content-disposition", response.headers)
            self.assertEqual(response.headers[b"cache-control"], b"no-store")
        # A contract error cannot reuse a previously successful geometry report.
        payload["samples"][1]["metadata"]["profile_id"] = "wrong-profile"
        response = await self.request("POST", "estimate", body=payload)
        self.assertEqual(response.status, 422)
        self.assertNotIn("diagnostics", response.json())

    async def test_wrong_or_missing_origin_is_rejected_before_body_reads(self):
        for origin in (None, "null", "http://attacker.example", "http://testserver:81", "http://testserver/path"):
            for endpoint in ("estimate", "export"):
                with self.subTest(origin=origin, endpoint=endpoint):
                    response = await self.request("POST", endpoint, headers={"origin": origin},
                                                  raw=b"not json", forbid_body_read=True)
                    self.assertEqual(response.status, 403, response.content)

    async def test_both_posts_require_json_before_reading_body(self):
        for content_type in (None, "text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
            for endpoint in ("estimate", "export"):
                with self.subTest(content_type=content_type, endpoint=endpoint):
                    response = await self.request("POST", endpoint, headers={"content-type": content_type},
                                                  forbid_body_read=True)
                    self.assertEqual(response.status, 415)
        response = await self.request("POST", "estimate", body=request(),
                                      headers={"content-type": "application/json; charset=utf-8"})
        self.assertEqual(response.status, 200, response.content)

    async def test_malformed_nonfinite_duplicate_and_nonobject_json_is_rejected(self):
        invalid = (b"", b"{", b"[]", b"null", b"42", b"\xff", b'{"extra": NaN}',
                   b'{"extra": Infinity}', b'{"extra": -Infinity}', b'{"extra": 1e309}',
                   b'{"extra": 1, "extra": 2}', b"[" * 1100 + b"]" * 1100,
                   b'{"extra": ' + b"1" * 5000 + b"}")
        for raw in invalid:
            for endpoint in ("estimate", "export"):
                with self.subTest(raw=raw[:40], endpoint=endpoint):
                    response = await self.request("POST", endpoint, raw=raw)
                    self.assertEqual(response.status, 422, response.content)
                    self.assertIsInstance(response.json()["detail"], str)

    async def test_advertised_size_limit_and_bad_content_length_fail_before_read(self):
        for length, status in ((str(mount_api.MAX_REQUEST_BYTES + 1), 413), ("-1", 400),
                               ("oops", 400), ("1.5", 400), ("", 400), ("+5", 400)):
            for endpoint in ("estimate", "export"):
                with self.subTest(length=length, endpoint=endpoint):
                    response = await self.request("POST", endpoint, headers={"content-length": length},
                                                  forbid_body_read=True)
                    self.assertEqual(response.status, status, response.content)

    async def test_streamed_limit_cannot_be_bypassed_by_missing_or_false_length(self):
        with patch.object(mount_api, "MAX_REQUEST_BYTES", 8):
            for length in (None, "2"):
                for endpoint in ("estimate", "export"):
                    with self.subTest(length=length, endpoint=endpoint):
                        response = await self.request("POST", endpoint,
                                                      headers={"content-length": length},
                                                      chunks=[b'{"x":', b'1234}'])
                        self.assertEqual(response.status, 413, response.content)
            # An exact-boundary request passes the byte guard and reaches schema validation.
            response = await self.request("POST", "estimate", raw=b'{"x": 1}')
            self.assertEqual(response.status, 422)
            self.assertIn("robot_stationary_confirmed", response.json()["detail"])

    async def test_calibration_errors_are_readable_and_export_revalidates(self):
        for endpoint in ("estimate", "export"):
            payload = request(reference_id="not-a-sample")
            response = await self.request("POST", endpoint, body=payload)
            self.assertEqual(response.status, 422, response.content)
            self.assertIn("reference_id", response.json()["detail"])
            payload = request()
            payload["robot_stationary_confirmed"] = False
            payload["analysis"] = {"status": "VALIDATED", "body_extrinsic_validated": True}
            response = await self.request("POST", endpoint, body=payload)
            self.assertEqual(response.status, 422)
            self.assertIn("robot_stationary_confirmed", response.json()["detail"])

    async def test_nonfinite_unknown_metadata_is_rejected_by_both_routes(self):
        for value in (float("nan"), float("inf"), -float("inf"), 10 ** 400):
            payload = request()
            payload["samples"][0]["metadata"]["unrecognized_field"] = value
            for endpoint in ("estimate", "export"):
                with self.subTest(value=str(value), endpoint=endpoint):
                    response = await self.request("POST", endpoint, body=payload)
                    self.assertEqual(response.status, 422, response.content)

    async def test_deep_unknown_metadata_is_rejected_by_both_routes(self):
        payload = request()
        extra = {}
        payload["extra"] = extra
        for _ in range(30):
            extra["nested"] = {}
            extra = extra["nested"]
        for endpoint in ("estimate", "export"):
            response = await self.request("POST", endpoint, body=payload)
            self.assertEqual(response.status, 422, response.content)
            self.assertIn("nesting depth", response.json()["detail"])

    async def test_missing_exposure_ids_are_optional_but_mixed_coordinate_frames_fail(self):
        payload = request()
        for sample in payload["samples"]:
            sample["metadata"].pop("capture_id")
        response = await self.request("POST", "estimate", body=payload)
        self.assertEqual(response.status, 200, response.content)
        self.assertTrue(any("No exposure" in warning for warning in response.json()["samples"][0]["warnings"]))
        payload["samples"][1]["metadata"]["frame_id"] = "another_optical_frame"
        response = await self.request("POST", "estimate", body=payload)
        self.assertEqual(response.status, 422, response.content)

    async def test_real_import_and_nonpitch_rotation_never_claim_validated_extrinsics(self):
        payload = request(capture("reference", synthetic=False),
                          capture("yaw", normal=[.25, -.1, .96], synthetic=False))
        response = await self.request("POST", "estimate", body=payload)
        self.assertEqual(response.status, 200, response.content)
        result = response.json()
        self.assertEqual(result["status"], "RELATIVE_ONLY")
        self.assertFalse(result["synthetic"])
        self.assertFalse(result["body_extrinsic_validated"])
        self.assertFalse(result["absolute_pitch_validated"])
        self.assertEqual(result["capture_verification"], "USER_ASSERTED_NOT_INDEPENDENTLY_VERIFIED")
        self.assertIsNone(result["samples"][1]["relative_pitch_deg"])


class RuntimeMustNotBeUsed:
    def __getattribute__(self, name):
        raise AssertionError(f"Offline calibration must not access runtime.{name}")


class MountCalibrationIntegrationTests(unittest.TestCase):
    def test_experimental_compatibility_exports_are_the_canonical_functions(self):
        from experiments.realsense_mount_calibration import calibration as legacy
        self.assertIs(legacy.estimate, estimate)
        self.assertIs(legacy.export_analysis, export_analysis)
        self.assertIs(legacy.CalibrationError, CalibrationError)

    def test_experimental_sample_validator_preserves_the_depth_capture_contract(self):
        from experiments.realsense_mount_calibration import calibration as legacy
        from robot_dashboard import mount_calibration as canonical
        self.assertIs(legacy._validate_sample, canonical._validate_sample)
        sample = capture("imported-sample")
        parsed = legacy._validate_sample(sample, 0)
        self.assertEqual(parsed["depth"].shape, (sample["height"], sample["width"]))
        self.assertEqual(parsed["id"], sample["id"])
        sample["metadata"]["rectified"] = False
        with self.assertRaisesRegex(CalibrationError, "rectified"):
            legacy._validate_sample(sample, 0)

    def test_application_registers_only_status_estimate_and_export_routes(self):
        prefix = "/api/v1/settings/mount-calibration/"
        observed = {(method, route.path) for route in mount_api.router.routes for method in route.methods}
        self.assertEqual(observed, {
            ("GET", prefix + "status"), ("POST", prefix + "estimate"), ("POST", prefix + "export"),
        })
        # The full application imports ROS; check its wiring without requiring
        # ROS installation or starting an application/hardware lifecycle.
        source = Path(__file__).resolve().parents[1] / "robot_dashboard" / "app.py"
        tree = ast.parse(source.read_text())
        self.assertTrue(any(isinstance(node, ast.ImportFrom)
                            and node.module == "api.routers.mount_calibration"
                            and any(alias.name == "router" and alias.asname == "mount_calibration_router"
                                    for alias in node.names) for node in tree.body))
        self.assertTrue(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and isinstance(node.func.value, ast.Name) and node.func.value.id == "app"
                            and node.func.attr == "include_router" and len(node.args) == 1
                            and isinstance(node.args[0], ast.Name)
                            and node.args[0].id == "mount_calibration_router" for node in ast.walk(tree)))

    def test_canonical_module_never_imports_the_experiment_or_hardware(self):
        source = Path(__file__).resolve().parents[1] / "robot_dashboard" / "mount_calibration.py"
        tree = ast.parse(source.read_text())
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module)
        self.assertEqual(modules, {"__future__", "itertools", "math", "typing", "numpy"})


if __name__ == "__main__":
    unittest.main()
