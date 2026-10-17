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
    if meta.get("depth_units", "m") not in ("m", "metres", "meters"):
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
    return {"id": sid, "width": width, "height": height, "intrinsics": k, "metadata": meta, "depth": depth, "picks": picks, "warnings": warnings}


def _deproject(sample: dict[str, Any]) -> tuple[np.ndarray, list[dict[str, Any]], list[str]]:
    k, depth, points = sample["intrinsics"], sample["depth"], []
    picked, warnings = [], list(sample["warnings"])
    for u, v in sample["picks"]:
        patch = depth[max(0, v - NEIGHBORHOOD_RADIUS):v + NEIGHBORHOOD_RADIUS + 1,
                      max(0, u - NEIGHBORHOOD_RADIUS):u + NEIGHBORHOOD_RADIUS + 1]
        valid = patch[np.isfinite(patch) & (patch >= MIN_DEPTH_M) & (patch <= MAX_DEPTH_M)]
        if len(valid) < max(5, math.ceil(patch.size * .5)):
            picked.append({"u": u, "v": v, "valid": False, "inlier": False, "reason": "insufficient valid neighborhood depth"})
            continue
        z = float(np.median(valid))
        # A discontinuity-rich patch must not produce a fictitious midpoint.
        q25, q75 = np.percentile(valid, [25, 75])
        if float(q75 - q25) > max(.03, .03 * z):
            picked.append({"u": u, "v": v, "valid": False, "inlier": False, "reason": "depth discontinuity in neighborhood"})
            continue
        p = [(u - k["cx"]) * z / k["fx"], (v - k["cy"]) * z / k["fy"], z]
        points.append(p)
        picked.append({"u": u, "v": v, "valid": True, "depth_m": z})
    if len(points) < MIN_POINTS:
        raise CalibrationError(f"Sample '{sample['id']}' has only {len(points)} valid depth points; at least {MIN_POINTS} are required.")
    if len(points) < len(sample["picks"]):
        warnings.append(f"{len(sample['picks']) - len(points)} selected point(s) excluded for invalid/discontinuous depth.")
    return np.asarray(points), picked, warnings


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
    median_depth = float(np.median(points[:, 2]))
    tolerance = max(.004, min(.020, .005 * median_depth))
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
    minimum_inliers = max(MIN_POINTS, math.ceil(.65 * n))
    if best_mask is None or best_mask.sum() < minimum_inliers:
        raise CalibrationError(f"Sample '{sample['id']}' has no reliable planar consensus; spread points across one wall and avoid outliers.")
    mask = best_mask
    for _ in range(4):
        normal, distance, singular = _svd_plane(points[mask])
        new_mask = np.abs(points @ normal - distance) <= tolerance
        if np.array_equal(mask, new_mask):
            break
        if new_mask.sum() < minimum_inliers:
            raise CalibrationError(f"Sample '{sample['id']}' loses planar consensus after robust refinement.")
        mask = new_mask
    normal, distance, singular = _svd_plane(points[mask])
    residuals = points @ normal - distance
    rmse = float(np.sqrt(np.mean(residuals[mask] ** 2)))
    spread_major, spread_minor = float(singular[0] / math.sqrt(mask.sum())), float(singular[1] / math.sqrt(mask.sum()))
    spread_ratio = spread_minor / max(spread_major, 1e-12)
    normalized_spread = spread_minor / median_depth
    if spread_ratio < .08 or normalized_spread < .008 or spread_major / median_depth < .03:
        raise CalibrationError(f"Sample '{sample['id']}' points are collinear, clustered, or too narrow; cover a broad two-dimensional wall area.")
    normalized_planarity = rmse / max(spread_minor, 1e-12)
    if rmse > tolerance * .8 or normalized_planarity > .06:
        raise CalibrationError(f"Sample '{sample['id']}' is not sufficiently planar for a stable normal estimate.")
    if normal[2] < .35:
        raise CalibrationError(f"Sample '{sample['id']}' is not a front-facing wall; positive normal_z must be at least 0.35.")
    if distance <= 0:
        raise CalibrationError(f"Sample '{sample['id']}' has an invalid wall distance.")
    j = 0
    for item in picked:
        if item["valid"]:
            item["inlier"] = bool(mask[j])
            item["plane_residual_m"] = float(residuals[j])
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
        "pitch_only_consistent": True, "validated_points": picked, "warnings": warnings,
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
    results = [_fit(sample) for sample in samples]
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
