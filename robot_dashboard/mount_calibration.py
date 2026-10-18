"""Conservative, offline wall-normal comparison; this is NOT an extrinsic solver.

Input coordinates are rectified pinhole pixels (u right, v down). Depth is optical
Z in metres, NOT ray length. Camera coordinates are x right, y down, z forward:
    X = (u - cx) * Z / fx; Y = (v - cy) * Z / fy.
The fitted wall normal is oriented toward positive camera z. The reported angle
is atan2(-normal_y, normal_z), and relative angles subtract an explicit reference.
Under a fixed wall and a pure pitch change, a positive difference corresponds to
the camera looking farther downward (rotation about negative optical x). No robot
body-axis mapping, absolute pitch, translation, or camera-to-body transform is
established by this method. Operator confirmations are assertions, not evidence.

No camera, robot, network, file write, or persistent calibration is used here.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

import numpy as np


SCHEMA_VERSION = "1.0.0"
MAX_WIDTH = 640
MAX_HEIGHT = 480
MAX_SAMPLES = 12
MAX_POINTS = 100
MIN_POINTS = 6
MIN_DEPTH_M = 0.10
MAX_DEPTH_M = 30.0
NEIGHBORHOOD_RADIUS = 2
MAX_JSON_DEPTH = 24
MAX_JSON_VALUES = 4_000_000
COORDINATE_CONVENTION = {
    "camera": "optical: x right, y down, z forward",
    "pixels": "u right, v down; rectified pinhole intrinsics",
    "depth": "optical Z in metres, not Euclidean ray range",
    "normal_orientation": "positive camera z",
    "pitch_formula": "degrees(atan2(-normal_y, normal_z)) minus reference",
    "positive_relative_pitch": "camera looks farther downward for a fixed wall and pure pitch; negative optical-x rotation",
    "robot_body_transform": "not inferred or validated",
}


class CalibrationError(ValueError):
    """A request is unsafe, malformed, or geometrically insufficient."""

    def __init__(self, message: str, diagnostics: dict[str, Any] | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics


def _validate_json_values(value: Any) -> None:
    """Validate retained export data, including unknown metadata, without copying it."""
    count = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal count
        count += 1
        if count > MAX_JSON_VALUES or depth > MAX_JSON_DEPTH:
            raise CalibrationError("Request JSON exceeds the supported value count or nesting depth.")
        if item is None or isinstance(item, (str, bool)):
            return
        if isinstance(item, (int, float)):
            try:
                finite = math.isfinite(float(item))
            except (OverflowError, ValueError):
                finite = False
            if not finite:
                raise CalibrationError("All numeric JSON values must be finite and representable; use null or zero for missing depth.")
            return
        if isinstance(item, list):
            for child in item:
                visit(child, depth + 1)
            return
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise CalibrationError("JSON object keys must be strings.")
                visit(child, depth + 1)
            return
        raise CalibrationError("Request contains a value that is not supported by JSON.")

    visit(value, 0)


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalibrationError(f"{path} must be a finite number.")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise CalibrationError(f"{path} must be a finite number.")
    if not math.isfinite(result):
        raise CalibrationError(f"{path} must be a finite number.")
    return result


def _integer(value: Any, path: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise CalibrationError(f"{path} must be an integer from {low} to {high}.")
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise CalibrationError(f"{path} must be a nonempty string of at most 200 characters.")
    return value


def _frame_id(value: Any, path: str) -> str | int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise CalibrationError(f"{path} must be a nonempty string or integer.")
    if isinstance(value, str):
        return _text(value, path)
    if value < 0 or value > 2**53 - 1:
        raise CalibrationError(f"{path} must be a nonnegative JSON-safe integer.")
    return value


def _capture_evidence(meta: dict[str, Any], k: dict[str, float], width: int,
                      height: int, prefix: str) -> tuple[Any, ...] | None:
    """Check retained collector evidence, without turning it into live readiness.

    A retained capture has no age expiry. Its source clock must not be replaced
    by import time; repeated source frames are not a second angle measurement.
    Generic rectified imports may omit this evidence and remain unverified.
    """
    path = f"{prefix}.metadata"
    if "source_timestamp_unit" in meta and meta["source_timestamp_unit"] != "seconds":
        raise CalibrationError(f"{path}.source_timestamp_unit must be seconds.")
    if "timestamp_domain" in meta and meta["timestamp_domain"] != meta.get("clock_domain"):
        raise CalibrationError(f"{path}.timestamp_domain must match clock_domain.")
    counters = meta.get("frame_numbers")
    if counters is not None:
        if not isinstance(counters, dict):
            raise CalibrationError(f"{path}.frame_numbers must contain ir1 and depth counters.")
        for stream in ("ir1", "depth"):
            _integer(counters.get(stream), f"{path}.frame_numbers.{stream}", 0, 2**53 - 1)
    timestamps, synchronization = meta.get("source_timestamps_ms"), meta.get("synchronization")
    exposure = None
    paired_evidence = False
    if meta.get("capture_session_id") is not None:
        _text(meta["capture_session_id"], f"{path}.capture_session_id")
    if timestamps is not None or synchronization is not None:
        if not isinstance(timestamps, dict) or not isinstance(synchronization, dict):
            raise CalibrationError(f"{path} requires source_timestamps_ms and synchronization together.")
        times = {stream: _number(timestamps.get(stream), f"{path}.source_timestamps_ms.{stream}")
                 for stream in ("ir1", "depth")}
        if any(value < 0 for value in times.values()):
            raise CalibrationError(f"{path}.source_timestamps_ms cannot be negative.")
        if meta.get("source_timestamp_unit") != "seconds" or meta.get("source_timestamp_stream") != "ir1":
            raise CalibrationError(f"{path} paired timestamps require the ir1 source_timestamp in seconds.")
        if not math.isclose(_number(meta.get("source_timestamp"), f"{path}.source_timestamp"),
                            times["ir1"] / 1000, rel_tol=0, abs_tol=1e-6):
            raise CalibrationError(f"{path}.source_timestamp does not match the original ir1 timestamp.")
        skew = abs(times["ir1"] - times["depth"])
        reported_skew = _number(synchronization.get("source_skew_ms"), f"{path}.synchronization.source_skew_ms")
        maximum = _number(synchronization.get("max_source_skew_ms"), f"{path}.synchronization.max_source_skew_ms")
        if (synchronization.get("frameset_verified") is not True or not 0 <= maximum <= 1
                or skew > maximum or not math.isclose(skew, reported_skew, rel_tol=0, abs_tol=1e-6)):
            raise CalibrationError(f"{path}.synchronization contradicts the paired timestamps or exceeds the 1 ms collector contract.")
        if counters is not None:
            paired_evidence = True
            # Hardware-clock counters restart when the device starts. Without
            # a capture-session epoch, matching numbers across files are
            # ambiguous and must not reject legitimate historical captures.
            domain, epoch = meta.get("clock_domain"), meta.get("capture_session_id")
            if epoch is not None or domain in ("global_time", "system_time", "timestamp_domain.global_time", "timestamp_domain.system_time"):
                exposure = (domain, epoch, times["ir1"], times["depth"], counters["ir1"], counters["depth"])

    alignment = meta.get("alignment")
    identity_method = "verified_identity_depth_to_ir1_no_resampling"
    identity_basis = "actual_zero_distortion_intrinsics_and_identity_depth_to_ir1_no_resampling"
    if (isinstance(alignment, dict) and alignment.get("method") == identity_method
            or meta.get("rectification_basis") == identity_basis):
        if not isinstance(alignment, dict) or alignment.get("method") != identity_method:
            raise CalibrationError(f"{path}.alignment must contain the claimed identity projection evidence.")
        if not paired_evidence:
            raise CalibrationError(f"{path} identity collector exports require original frame_numbers and synchronization evidence.")
        for name in ("ir1_intrinsics", "depth_intrinsics"):
            intrinsics = alignment.get(name)
            if not isinstance(intrinsics, dict):
                raise CalibrationError(f"{path}.alignment.{name} is required.")
            if (type(intrinsics.get("width")) is not int or type(intrinsics.get("height")) is not int
                    or intrinsics["width"] != width or intrinsics["height"] != height):
                raise CalibrationError(f"{path}.alignment.{name} does not match the image profile.")
            for key, sdk_key in (("fx", "fx"), ("fy", "fy"), ("cx", "ppx"), ("cy", "ppy")):
                if not math.isclose(_number(intrinsics.get(sdk_key), f"{path}.alignment.{name}.{sdk_key}"),
                                    k[key], rel_tol=1e-9, abs_tol=1e-9):
                    raise CalibrationError(f"{path}.alignment.{name} does not match the click intrinsics.")
            coeffs = intrinsics.get("coeffs")
            if (intrinsics.get("model") not in ("none", "brown_conrady", "distortion.none", "distortion.brown_conrady")
                    or not isinstance(coeffs, list) or len(coeffs) != 5
                    or any(_number(value, f"{path}.alignment.{name}.coeffs") != 0 for value in coeffs)):
                raise CalibrationError(f"{path}.alignment.{name} must be actual zero-distortion pinhole intrinsics.")
        extrinsics = alignment.get("depth_to_ir1")
        if not isinstance(extrinsics, dict):
            raise CalibrationError(f"{path}.alignment.depth_to_ir1 is required.")
        for name, expected in (("rotation", (1, 0, 0, 0, 1, 0, 0, 0, 1)), ("translation", (0, 0, 0))):
            values = extrinsics.get(name)
            if (not isinstance(values, list) or len(values) != len(expected)
                    or any(abs(_number(value, f"{path}.alignment.depth_to_ir1.{name}") - target) > 1e-8
                           for value, target in zip(values, expected))):
                raise CalibrationError(f"{path}.alignment.depth_to_ir1 must be identity; no-resampling pixels would otherwise differ.")
        if extrinsics.get("translation_unit", "metres") not in ("m", "metres", "meters"):
            raise CalibrationError(f"{path}.alignment.depth_to_ir1 translation_unit must be metres.")
    return exposure


def _validate_sample(raw: Any, index: int) -> dict[str, Any]:
    prefix = f"samples[{index}]"
    if not isinstance(raw, dict):
        raise CalibrationError(f"{prefix} must be an object.")
    sid = _text(raw.get("id"), f"{prefix}.id")
    width = _integer(raw.get("width"), f"{prefix}.width", 8, MAX_WIDTH)
    height = _integer(raw.get("height"), f"{prefix}.height", 8, MAX_HEIGHT)
    intrinsics = raw.get("intrinsics")
    if not isinstance(intrinsics, dict):
        raise CalibrationError(f"{prefix}.intrinsics must contain fx, fy, cx, cy.")
    k = {key: _number(intrinsics.get(key), f"{prefix}.intrinsics.{key}") for key in ("fx", "fy", "cx", "cy")}
    if k["fx"] <= 0 or k["fy"] <= 0 or k["fx"] > 100000 or k["fy"] > 100000:
        raise CalibrationError(f"{prefix} focal lengths must be positive and plausible (at most 100000 pixels).")
    if not (0 <= k["cx"] < width and 0 <= k["cy"] < height):
        raise CalibrationError(f"{prefix} principal point must be within this image profile.")
    for key, expected in (("width", width), ("height", height)):
        if key in intrinsics and intrinsics[key] != expected:
            raise CalibrationError(f"{prefix}.intrinsics.{key} does not match the image profile.")
    if intrinsics.get("model", "pinhole") not in ("pinhole", "none", "rectified"):
        raise CalibrationError(f"{prefix} requires rectified pinhole intrinsics, without distortion.")
    if "coeffs" in intrinsics:
        coeffs = intrinsics["coeffs"]
        if not isinstance(coeffs, list) or len(coeffs) > 16 or any(abs(_number(v, f"{prefix}.intrinsics.coeffs")) > 1e-12 for v in coeffs):
            raise CalibrationError(f"{prefix} nonzero distortion coefficients are unsupported; rectify first.")
    meta = raw.get("metadata")
    if not isinstance(meta, dict):
        raise CalibrationError(f"{prefix}.metadata is required.")
    serial = _text(meta.get("serial"), f"{prefix}.metadata.serial")
    # frame_id names the shared optical coordinate frame, not an exposure.
    fid = _text(meta.get("frame_id"), f"{prefix}.metadata.frame_id")
    for key in ("frame_number", "capture_id"):
        if key in meta:
            _frame_id(meta[key], f"{prefix}.metadata.{key}")
    if meta.get("rectified") is not True:
        raise CalibrationError(f"{prefix} must explicitly confirm metadata.rectified=true; distorted images are unsupported.")
    if not isinstance(meta.get("synthetic"), bool):
        raise CalibrationError(f"{prefix}.metadata.synthetic must explicitly be true or false.")
    if not meta["synthetic"]:
        for key in ("profile_id", "depth_semantics", "source_timestamp", "clock_domain"):
            if key not in meta:
                raise CalibrationError(f"{prefix}.metadata.{key} is required for real captures; capture provenance cannot be assumed.")
    if "clock_domain" in meta:
        _text(meta["clock_domain"], f"{prefix}.metadata.clock_domain")
    if "source_timestamp" in meta:
        timestamp = meta["source_timestamp"]
        if isinstance(timestamp, str):
            _text(timestamp, f"{prefix}.metadata.source_timestamp")
        elif _number(timestamp, f"{prefix}.metadata.source_timestamp") < 0:
            raise CalibrationError(f"{prefix}.metadata.source_timestamp cannot be negative.")
    if meta.get("depth_semantics", "optical_z") != "optical_z":
        raise CalibrationError(f"{prefix} depth_semantics must be optical_z; ray-range depth is unsupported.")
    if any(meta.get(key, "m") not in ("m", "metres", "meters") for key in ("depth_unit", "depth_units")):
        raise CalibrationError(f"{prefix} depth units must be metres.")
    if meta.get("projection_model", "pinhole") != "pinhole":
        raise CalibrationError(f"{prefix} projection_model must be pinhole.")
    if meta.get("distortion_model", "none") not in ("none", "rectified", "pinhole"):
        raise CalibrationError(f"{prefix} distortion_model must describe rectified pinhole data.")
    for key in ("depth_frame_id", "image_frame_id", "intrinsics_frame_id"):
        if key in meta and meta[key] != fid:
            raise CalibrationError(f"{prefix}.metadata.{key} does not match frame_id; capture components must match.")
    for key in ("depth_serial", "image_serial", "intrinsics_serial"):
        if key in meta and meta[key] != serial:
            raise CalibrationError(f"{prefix}.metadata.{key} does not match serial.")
    if "profile_id" in meta:
        _text(meta["profile_id"], f"{prefix}.metadata.profile_id")
    for key in ("depth_profile_id", "image_profile_id", "intrinsics_profile_id"):
        if key in meta and ("profile_id" not in meta or meta[key] != meta["profile_id"]):
            raise CalibrationError(f"{prefix}.metadata.{key} does not match profile_id.")
    exposure = _capture_evidence(meta, k, width, height, prefix)
    depth_raw = raw.get("depth_m")
    if not isinstance(depth_raw, list) or len(depth_raw) != width * height:
        raise CalibrationError(f"{prefix}.depth_m must be a flat array of exactly width*height values in metres.")
    if any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))) for v in depth_raw):
        raise CalibrationError(f"{prefix}.depth_m values must be numbers or null (invalid depth).")
    try:
        depth = np.asarray(depth_raw, dtype=np.float64).reshape(height, width)
    except (ValueError, OverflowError, TypeError):
        raise CalibrationError(f"{prefix}.depth_m contains an unrepresentable value.")
    selections = raw.get("points")
    if not isinstance(selections, list) or not MIN_POINTS <= len(selections) <= MAX_POINTS:
        raise CalibrationError(f"{prefix}.points must contain {MIN_POINTS} to {MAX_POINTS} points spread over the wall.")
    picks = []
    seen = set()
    for j, point in enumerate(selections):
        if not isinstance(point, dict):
            raise CalibrationError(f"{prefix}.points[{j}] must contain u and v.")
        u = _number(point.get("u"), f"{prefix}.points[{j}].u")
        v = _number(point.get("v"), f"{prefix}.points[{j}].v")
        if not (0 <= u < width and 0 <= v < height):
            raise CalibrationError(f"{prefix}.points[{j}] is outside the image.")
        # Use the same integer pixel for neighborhood depth and deprojection.
        ui, vi = min(width - 1, int(math.floor(u + .5))), min(height - 1, int(math.floor(v + .5)))
        if (ui, vi) in seen:
            raise CalibrationError(f"{prefix} contains duplicate selected pixels.")
        seen.add((ui, vi))
        picks.append((ui, vi))
    warnings = []
    if "profile_id" not in meta:
        warnings.append("No SDK profile_id supplied; profile consistency is checked using dimensions and intrinsics only.")
    if "depth_semantics" not in meta:
        warnings.append("depth_m is interpreted as optical Z by the API contract; source depth semantics were not independently verified.")
    if not all(key in meta for key in ("depth_frame_id", "image_frame_id")):
        warnings.append("Only the shared coordinate frame_id was supplied; image/depth projection alignment was not independently verified.")
    if not any(key in meta for key in ("frame_number", "capture_id")):
        warnings.append("No exposure frame_number/capture_id supplied; unique sample ids do not independently prove distinct exposures.")
    if "source_timestamps_ms" in meta and exposure is None:
        warnings.append("No capture-session epoch for paired hardware-clock frames; matching timestamps/counters across retained sessions do not prove repeated exposures.")
    return {"id": sid, "width": width, "height": height, "intrinsics": k, "metadata": meta, "depth": depth, "picks": picks, "warnings": warnings,
            "source_exposure": exposure}


def _deproject(sample: dict[str, Any]) -> tuple[np.ndarray, list[dict[str, Any]], list[str]]:
    k, depth, points = sample["intrinsics"], sample["depth"], []
    picked, warnings = [], list(sample["warnings"])
    for u, v in sample["picks"]:
        patch = depth[max(0, v - NEIGHBORHOOD_RADIUS):v + NEIGHBORHOOD_RADIUS + 1,
                      max(0, u - NEIGHBORHOOD_RADIUS):u + NEIGHBORHOOD_RADIUS + 1]
        valid = patch[np.isfinite(patch) & (patch >= MIN_DEPTH_M) & (patch <= MAX_DEPTH_M)]
        required = max(5, math.ceil(patch.size * .5))
        center = float(depth[v, u])
        item: dict[str, Any] = {
            "u": u, "v": v, "valid": False, "inlier": None, "plane_residual_m": None,
            "center_depth_m": center if math.isfinite(center) and center > 0 else None,
            "center_valid": bool(math.isfinite(center) and MIN_DEPTH_M <= center <= MAX_DEPTH_M),
            "neighborhood_pixel_count": int(patch.size), "neighborhood_valid_count": len(valid),
            "neighborhood_required_count": required, "neighborhood_valid_fraction": len(valid) / patch.size,
            "neighborhood_median_m": None, "neighborhood_iqr_m": None, "discontinuity_limit_m": None,
        }
        picked.append(item)
        # Report robust patch statistics even if too few samples pass the gate.
        if len(valid):
            z = float(np.median(valid))
            q25, q75 = np.percentile(valid, [25, 75])
            item.update(neighborhood_median_m=z, neighborhood_iqr_m=float(q75 - q25),
                        discontinuity_limit_m=max(.03, .03 * z))
        if len(valid) < required:
            item.update(inlier=False, reason="insufficient valid neighborhood depth")
            continue
        # A discontinuity-rich patch must not produce a fictitious midpoint.
        if item["neighborhood_iqr_m"] > item["discontinuity_limit_m"]:
            item.update(inlier=False, reason="depth discontinuity in neighborhood")
            continue
        points.append([(u - k["cx"]) * z / k["fx"], (v - k["cy"]) * z / k["fy"], z])
        item.update(valid=True, depth_m=z, reason="plane not checked")
    if len(points) < len(sample["picks"]):
        warnings.append(f"{len(sample['picks']) - len(points)} selected point(s) excluded for invalid/discontinuous depth.")
    return np.asarray(points), picked, warnings


def _pixel_distribution(sample: dict[str, Any]) -> dict[str, Any]:
    pixels = np.asarray(sample["picks"], dtype=float)
    lo, hi = pixels.min(axis=0), pixels.max(axis=0)
    singular = np.linalg.svd(pixels - pixels.mean(axis=0), compute_uv=False)
    return {"bounds_uv": [float(x) for x in (*lo, *hi)],
            "width_fraction": float((hi[0] - lo[0]) / sample["width"]),
            "height_fraction": float((hi[1] - lo[1]) / sample["height"]),
            "minor_major_ratio": float(singular[1] / max(singular[0], 1e-12)),
            "basis": "all_selected_pixels_not_metric_plane_coverage"}


def _svd_plane(points: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    center = points.mean(axis=0)
    _, singular, vh = np.linalg.svd(points - center, full_matrices=False)
    normal = vh[-1]
    if normal[2] < 0:
        normal = -normal
    return normal, float(normal @ center), singular


def _fit(sample: dict[str, Any]) -> dict[str, Any]:
    points, picked, warnings = _deproject(sample)
    n = len(points)
    diagnostics: dict[str, Any] = {
        "id": sample["id"], "status": "QUALITY_REJECTED", "failure_code": None,
        "selected_points": len(picked), "valid_points": n, "inlier_points": None,
        "minimum_inlier_points": max(MIN_POINTS, math.ceil(.65 * n)),
        "neighborhood_size": 2 * NEIGHBORHOOD_RADIUS + 1,
        "validated_points": picked, "pixel_distribution": _pixel_distribution(sample),
        "residual_basis": "not_computed", "warnings": warnings,
    }

    def fail(code: str, message: str) -> None:
        diagnostics.update(failure_code=code, reason=message)
        raise CalibrationError(message, diagnostics)

    def record_plane(residuals: np.ndarray, mask: np.ndarray) -> None:
        diagnostics.update(inlier_points=int(mask.sum()), residual_basis="rejected_candidate_plane")
        for item, residual, inlier in zip((p for p in picked if p["valid"]), residuals, mask):
            item.update(inlier=bool(inlier), plane_residual_m=float(residual),
                        reason="within candidate plane tolerance" if inlier else "outside plane tolerance")

    if n < MIN_POINTS:
        fail("INSUFFICIENT_NEIGHBORHOOD_DEPTH", f"Sample '{sample['id']}' has only {n} valid depth points; at least {MIN_POINTS} are required.")
    median_depth = float(np.median(points[:, 2]))
    tolerance = max(.004, min(.020, .005 * median_depth))
    diagnostics["ransac_tolerance_m"] = tolerance
    total_combinations = math.comb(n, 3)
    if total_combinations <= 512:
        candidates = list(itertools.combinations(range(n), 3))
    else:
        rng = np.random.default_rng(0)
        triples: set[tuple[int, int, int]] = set()
        while len(triples) < 512:
            triples.add(tuple(sorted(int(x) for x in rng.choice(n, 3, replace=False))))
        candidates = sorted(triples)
    best_mask = None
    best_score = (-1, -float("inf"))
    for a, b, c in candidates:
        ab, ac = points[b] - points[a], points[c] - points[a]
        normal = np.cross(ab, ac)
        norm = float(np.linalg.norm(normal))
        if norm <= 1e-8 or norm <= 1e-3 * np.linalg.norm(ab) * np.linalg.norm(ac):
            continue
        normal /= norm
        residuals = np.abs((points - points[a]) @ normal)
        mask = residuals <= tolerance
        score = (int(mask.sum()), -float(np.median(residuals[mask])))
        if score > best_score:
            best_score, best_mask = score, mask
            record_plane((points - points[a]) @ normal, mask)
    minimum_inliers = max(MIN_POINTS, math.ceil(.65 * n))
    if best_mask is None or best_mask.sum() < minimum_inliers:
        fail("NO_PLANAR_CONSENSUS", f"Sample '{sample['id']}' has no reliable planar consensus; spread points across one wall and avoid outliers.")
    mask = best_mask
    for _ in range(4):
        normal, distance, singular = _svd_plane(points[mask])
        candidate_residuals = points @ normal - distance
        new_mask = np.abs(candidate_residuals) <= tolerance
        record_plane(candidate_residuals, new_mask)
        if np.array_equal(mask, new_mask):
            break
        if new_mask.sum() < minimum_inliers:
            fail("REFINEMENT_LOST_CONSENSUS", f"Sample '{sample['id']}' loses planar consensus after robust refinement.")
        mask = new_mask
    normal, distance, singular = _svd_plane(points[mask])
    residuals = points @ normal - distance
    record_plane(residuals, mask)
    rmse = float(np.sqrt(np.mean(residuals[mask] ** 2)))
    spread_major, spread_minor = float(singular[0] / math.sqrt(mask.sum())), float(singular[1] / math.sqrt(mask.sum()))
    spread_ratio = spread_minor / max(spread_major, 1e-12)
    normalized_spread = spread_minor / median_depth
    diagnostics.update(plane_rmse_m=rmse, spread_ratio=spread_ratio, normalized_minor_spread=normalized_spread,
                       normalized_major_spread=spread_major / median_depth)
    if spread_ratio < .08 or normalized_spread < .008 or spread_major / median_depth < .03:
        fail("NARROW_POINT_DISTRIBUTION", f"Sample '{sample['id']}' points are collinear, clustered, or too narrow; cover a broad two-dimensional wall area.")
    normalized_planarity = rmse / max(spread_minor, 1e-12)
    diagnostics["normalized_planarity"] = normalized_planarity
    if rmse > tolerance * .8 or normalized_planarity > .06:
        fail("UNSTABLE_PLANE_NORMAL", f"Sample '{sample['id']}' is not sufficiently planar for a stable normal estimate.")
    if normal[2] < .35:
        fail("WALL_NOT_FRONT_FACING", f"Sample '{sample['id']}' is not a front-facing wall; positive normal_z must be at least 0.35.")
    if distance <= 0:
        fail("INVALID_WALL_DISTANCE", f"Sample '{sample['id']}' has an invalid wall distance.")
    diagnostics.update(status="PLANE_ACCEPTED", residual_basis="accepted_plane")
    j = 0
    for item in picked:
        if item["valid"]:
            item["inlier"] = bool(mask[j])
            item["plane_residual_m"] = float(residuals[j])
            item["reason"] = "accepted plane inlier" if mask[j] else "outside plane tolerance"
            j += 1
    if not mask.all():
        warnings.append(f"{int((~mask).sum())} valid-depth point(s) rejected as plane outliers.")
    return {
        "id": sample["id"], "normal_camera": [float(x) for x in normal],
        "plane_rmse_m": rmse, "all_points_rmse_m": float(np.sqrt(np.mean(residuals ** 2))),
        "plane_distance_m": distance, "inlier_ratio": float(mask.mean()),
        "valid_points": n, "inlier_points": int(mask.sum()), "selected_points": len(picked),
        "spread_ratio": spread_ratio, "normalized_minor_spread": normalized_spread,
        "normalized_planarity": normalized_planarity, "ransac_tolerance_m": tolerance,
        "pitch_proxy_deg": math.degrees(math.atan2(-normal[1], normal[2])),
        "relative_pitch_deg": None, "relative_pitch_candidate_deg": None,
        "pitch_only_consistent": True, "validated_points": picked, "warnings": warnings, "diagnostics": diagnostics,
    }


def estimate(payload: Any) -> dict[str, Any]:
    """Validate all captures and return a conditional, relative-only comparison."""
    _validate_json_values(payload)
    if not isinstance(payload, dict):
        raise CalibrationError("The request must be a JSON object.")
    for flag in ("robot_stationary_confirmed", "wall_same_confirmed", "mount_only_pitch_confirmed"):
        if payload.get(flag) is not True:
            raise CalibrationError(f"{flag} must be explicitly true. This is an operator assertion, not measured verification.")
    raw_samples = payload.get("samples")
    if not isinstance(raw_samples, list) or not 2 <= len(raw_samples) <= MAX_SAMPLES:
        raise CalibrationError(f"Provide 2 to {MAX_SAMPLES} captures, including a reference and a comparison.")
    reference_id = _text(payload.get("reference_id"), "reference_id")
    samples = [_validate_sample(s, i) for i, s in enumerate(raw_samples)]
    ids = [s["id"] for s in samples]
    if len(set(ids)) != len(ids):
        raise CalibrationError("Sample ids must be unique.")
    if reference_id not in ids:
        raise CalibrationError("reference_id must match an explicitly supplied sample id.")
    reference_sample = samples[ids.index(reference_id)]
    meta0 = reference_sample["metadata"]
    exposure_ids: dict[str, list[Any]] = {"frame_number": [], "capture_id": []}
    source_exposures: set[tuple[Any, ...]] = set()
    for sample in samples:
        meta = sample["metadata"]
        for key in ("serial", "frame_id", "synthetic", "profile_id", "camera_model", "model", "product_id",
                    "stream", "stream_type", "stream_index", "format", "fps", "depth_scale",
                    "alignment", "alignment_target", "projection_model", "distortion_model",
                    "depth_semantics", "clock_domain"):
            defaults = {"projection_model": "pinhole", "distortion_model": "none", "depth_semantics": "optical_z"}
            if meta.get(key, defaults.get(key)) != meta0.get(key, defaults.get(key)):
                raise CalibrationError(f"All captures must have matching metadata.{key}; mixed cameras/profiles/models or synthetic/real data are not supported.")
        if (sample["width"], sample["height"]) != (reference_sample["width"], reference_sample["height"]):
            raise CalibrationError("All captures must use the same image dimensions/profile.")
        if not all(math.isclose(sample["intrinsics"][key], reference_sample["intrinsics"][key], rel_tol=1e-9, abs_tol=1e-9) for key in ("fx", "fy", "cx", "cy")):
            raise CalibrationError("All captures must use identical rectified intrinsics/profile; do not mix models or stereo streams.")
        for key in exposure_ids:
            if key in meta:
                value = meta[key]
                if value in exposure_ids[key]:
                    raise CalibrationError(f"Each capture must have a distinct metadata.{key}; frame_id is the common coordinate frame.")
                exposure_ids[key].append(value)
        if sample["source_exposure"] is not None:
            if sample["source_exposure"] in source_exposures:
                raise CalibrationError("Each capture must contain a distinct source exposure; a retained frame replay is not another angle sample.")
            source_exposures.add(sample["source_exposure"])
    results, sample_diagnostics, failures = [], [], []
    for sample in samples:
        try:
            fitted = _fit(sample)
            results.append(fitted)
            sample_diagnostics.append(fitted["diagnostics"])
        except CalibrationError as exc:
            failures.append(str(exc))
            sample_diagnostics.append(exc.diagnostics)
    if failures:
        raise CalibrationError(failures[0], {
            "status": "QUALITY_REJECTED", "mode": "RELATIVE_ONLY", "samples": sample_diagnostics,
            "body_extrinsic_validated": False, "absolute_pitch_validated": False,
            "relative_angles_available": False,
        })
    reference = results[ids.index(reference_id)]
    for result in results:
        angle = result["pitch_proxy_deg"] - reference["pitch_proxy_deg"]
        angle = (angle + 180) % 360 - 180
        result["relative_pitch_candidate_deg"] = angle
        nx_change = abs(result["normal_camera"][0] - reference["normal_camera"][0])
        result["lateral_normal_change"] = nx_change
        if nx_change > .04:
            result["pitch_only_consistent"] = False
            result["warnings"].append("Lateral normal component changed beyond 0.04. Pitch-only rotation is inconsistent; relative_pitch_candidate_deg is diagnostic only, and relative_pitch_deg is withheld.")
        distance_change = abs(result["plane_distance_m"] - reference["plane_distance_m"])
        result["plane_distance_change_m"] = distance_change
        if distance_change > max(.03, .015 * reference["plane_distance_m"]):
            result["warnings"].append("Wall distance changed materially. Camera-center motion, another wall, or depth error may be present; a fixed-center rotation is not verified.")
        if result["pitch_only_consistent"]:
            result["relative_pitch_deg"] = angle
    synthetic = bool(meta0["synthetic"])
    warnings = [
        "RELATIVE ONLY: wall normals do not establish absolute pitch, mount translation, or a camera-to-robot-body extrinsic transform.",
        "Stationarity, the same wall, and pitch-only adjustment are user assertions, not independently verified measurements.",
        "Image/depth capture-time synchronization is not independently verified; matching coordinate-frame names do not prove synchronization.",
        "A plane alone cannot fully constrain extrinsics. Fixed height/left-right settings and a visible wall do not prove body-axis alignment.",
        "This output is not a VSLAM calibration or readiness check. Validate time synchronization, camera/IMU intrinsics, and body extrinsics separately before VSLAM integration.",
    ]
    if synthetic:
        warnings.insert(0, "SYNTHETIC DEMO: simulated depth only; this is not evidence of a connected or calibrated camera/robot.")
    if not all(s["pitch_only_consistent"] for s in results):
        warnings.append("At least one capture contradicts the pitch-only model; its relative pitch has been withheld.")
    return {
        "schema_version": SCHEMA_VERSION, "status": "RELATIVE_ONLY", "samples": results,
        "reference_id": reference_id, "coordinate_convention": COORDINATE_CONVENTION,
        "body_extrinsic_validated": False, "absolute_pitch_validated": False,
        "capture_verification": "USER_ASSERTED_NOT_INDEPENDENTLY_VERIFIED",
        "pitch_only_consistent": all(s["pitch_only_consistent"] for s in results),
        "synthetic": synthetic, "warnings": warnings,
    }


def export_analysis(payload: Any) -> dict[str, Any]:
    """Recompute from the supplied data; return JSON without writing host files."""
    analysis = estimate(payload)
    return {"schema_version": SCHEMA_VERSION, "export_kind": "relative_wall_pitch_analysis", "input": payload, "analysis": analysis}
