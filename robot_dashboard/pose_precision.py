"""Offline SE3 comparison using declared independent measurements, never ROS.

T_A_B maps column coordinates in B into A. No trajectory alignment, calibration
estimation, interpolation, scale fitting, or operational pose application occurs.
Provenance declarations are input checks, not proof of physical independence.
"""

from __future__ import annotations

import math
import re
from typing import Any

import numpy as np

INPUT_SCHEMA = "robot-scope.pose-precision-input.v1"
OUTPUT_SCHEMA = "robot-scope.pose-precision-result.v1"
MAX_SAMPLES = 100_000
MAX_BYTES = 32 * 1024 * 1024
EVIDENCE_ROLES = (
    "estimate",
    "truth",
    "extrinsic",
    "world_alignment",
    "timing",
    "camera_calibration",
)


class PosePrecisionError(ValueError):
    """Missing or inconsistent offline evaluation input."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise PosePrecisionError(reason)


def _text(value: Any, name: str) -> str:
    require(isinstance(value, str) and 0 < len(value) <= 256, name + " required")
    return value


def _number(value: Any, name: str, *, nonnegative: bool = False) -> float:
    require(type(value) in (int, float), name + " must be numeric")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    require(finite, name + " must be finite")
    require(not nonnegative or value >= 0, name + " must be nonnegative")
    return float(value)


def _integer(value: Any, name: str, *, signed: bool = False) -> int:
    # Decimal strings preserve integer nanoseconds across JSON/JavaScript tools.
    require(
        isinstance(value, str)
        and re.fullmatch(r"-?(?:0|[1-9][0-9]*)", value) is not None,
        name + " must be a decimal nanosecond string",
    )
    result = int(value)
    require(
        -(2**63) <= result <= 2**63 - 1 and (signed or result >= 0),
        name + " out of range",
    )
    return result


def _array(value: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
    def numeric(item):
        return (
            all(numeric(x) for x in item)
            if isinstance(item, list)
            else type(item) in (int, float)
        )

    require(
        isinstance(value, list) and numeric(value),
        name + " must contain numeric values",
    )
    try:
        result = np.asarray(value, dtype=np.float64)
    except (ValueError, OverflowError) as exc:
        raise PosePrecisionError(name + " malformed") from exc
    require(
        result.shape == shape and bool(np.isfinite(result).all()),
        name + " shape/finite check failed",
    )
    return result


def transform(value: Any, parent: str, child: str) -> np.ndarray:
    """Validate explicit frame direction and either a rigid matrix or xyzw pose."""
    require(isinstance(value, dict), "transform object required")
    require(
        value.get("parent_frame") == parent and value.get("child_frame") == child,
        "transform frame/direction mismatch: " + parent + " <- " + child,
    )
    matrix_mode = "T_parent_child" in value
    pose_mode = "translation_m" in value or "quaternion_xyzw" in value
    require(matrix_mode != pose_mode, "provide exactly one transform representation")
    if matrix_mode:
        result = _array(value["T_parent_child"], (4, 4), "T_parent_child")
    else:
        translation = _array(value.get("translation_m"), (3,), "translation_m")
        q = _array(value.get("quaternion_xyzw"), (4,), "quaternion_xyzw")
        norm = float(np.linalg.norm(q))
        require(abs(norm - 1.0) <= 1e-6, "quaternion must be unit length within 1e-6")
        # Numeric unit correction only; source values are retained unchanged.
        x, y, z, w = q / norm
        result = np.eye(4)
        result[:3, :3] = [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
        result[:3, 3] = translation
    rotation = result[:3, :3]
    require(
        bool((np.abs(rotation) <= 1 + 1e-6).all())
        and bool((np.abs(result[:3, 3]) <= 1e9).all()),
        "transform numeric bound exceeded",
    )
    require(
        bool(np.allclose(result[3], [0, 0, 0, 1], rtol=0, atol=1e-9)),
        "invalid homogeneous row",
    )
    require(
        bool(np.allclose(rotation.T @ rotation, np.eye(3), rtol=0, atol=1e-6))
        and abs(float(np.linalg.det(rotation)) - 1.0) <= 1e-6,
        "rotation must be proper orthonormal SE3",
    )
    return result.copy()


def inverse(value: np.ndarray) -> np.ndarray:
    result = np.eye(4)
    result[:3, :3] = value[:3, :3].T
    result[:3, 3] = -result[:3, :3] @ value[:3, 3]
    return result


def _uncertainty(value: Any, name: str) -> dict:
    require(isinstance(value, dict), name + " uncertainty required")
    return {
        key: _number(value.get(key), name + "." + key, nonnegative=True)
        for key in ("translation_bound_m", "rotation_bound_rad")
    }


def _series(value: Any, parent: str, child: str, name: str) -> list:
    require(isinstance(value, dict), name + " series required")
    _text(value.get("acquisition_id"), name + " acquisition_id")
    require(
        value.get("parent_frame") == parent and value.get("child_frame") == child,
        name + " series frame mismatch",
    )
    _text(value.get("epoch"), name + " epoch")
    rows = value.get("samples")
    require(
        isinstance(rows, list) and 1 <= len(rows) <= MAX_SAMPLES,
        name + " sample bound exceeded/empty",
    )
    result, previous = [], -1
    for row in rows:
        require(isinstance(row, dict), name + " sample object required")
        stamp = _integer(row.get("stamp_ns"), name + " stamp_ns")
        require(stamp > previous, name + " timestamps must strictly increase")
        require(row.get("epoch") == value["epoch"], name + " epoch changed")
        result.append((stamp, transform(row.get("pose"), parent, child)))
        previous = stamp
    return result


def evaluate(manifest: Any) -> dict:
    """Compute descriptive absolute errors; never certify truth or body calibration."""
    require(
        isinstance(manifest, dict) and manifest.get("schema") == INPUT_SCHEMA,
        "input schema mismatch",
    )
    kind = manifest.get("evidence_type")
    require(kind in {"recorded_real", "synthetic"}, "explicit evidence_type required")
    require(
        manifest.get("units") == "m_rad"
        and manifest.get("convention") == "T_parent_child_column_vectors",
        "metre/radian and column-vector transform convention required",
    )
    frames = manifest.get("frames")
    require(isinstance(frames, dict), "frames required")
    world, map_frame, camera, body = [
        _text(frames.get(key), key + " frame")
        for key in ("world", "map", "camera", "body")
    ]
    require(
        len({world, map_frame, camera, body}) == 4,
        "distinct semantic frame IDs required",
    )
    axes = manifest.get("camera_axes")
    require(
        axes in {"ros_link_x_forward_y_left_z_up", "optical_x_right_y_down_z_forward"},
        "explicit camera axes required",
    )
    require(
        not (
            "optical" in camera.lower() and axes != "optical_x_right_y_down_z_forward"
        ),
        "optical frame cannot be relabeled camera link",
    )
    require(
        manifest.get("body_axes") == "ros_x_forward_y_left_z_up",
        "explicit ROS body axes required",
    )
    provenance = manifest.get("provenance")
    require(isinstance(provenance, dict), "measurement provenance required")
    require(
        provenance.get("truth_method")
        in {
            "motion_capture",
            "laser_tracker",
            "surveyed_rigid_target",
            "calibrated_external_camera",
        },
        "independent external 6DoF truth method required",
    )
    for key in (
        "truth_independent_of_estimate",
        "alignment_independent_of_evaluation_samples",
        "extrinsic_independently_measured",
        "mount_unchanged",
        "current_camera_chain_verified",
    ):
        require(provenance.get(key) is True, "unqualified declared provenance: " + key)
    for key in (
        "instrument_id",
        "mount_id",
        "measured_at_utc",
        "estimate_source_commit",
        "estimate_runtime_identity",
        "estimate_config_sha256",
    ):
        _text(provenance.get(key), key)
    require(
        re.fullmatch(r"[0-9a-f]{40}", provenance["estimate_source_commit"]) is not None,
        "exact estimate source commit required",
    )
    require(
        re.fullmatch(r"[0-9a-f]{64}", provenance["estimate_config_sha256"]) is not None,
        "estimate config SHA256 required",
    )
    evidence = manifest.get("evidence")
    require(isinstance(evidence, dict), "evidence references required")
    for role in EVIDENCE_ROLES:
        item = evidence.get(role)
        require(isinstance(item, dict), "evidence reference required: " + role)
        _text(item.get("path"), "evidence path " + role)
        require(
            isinstance(item.get("sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is not None,
            "evidence SHA256 required: " + role,
        )
    require(
        evidence["truth"]["sha256"] != evidence["estimate"]["sha256"],
        "truth cannot be byte-identical estimate",
    )
    uncertainties = manifest.get("uncertainty")
    require(isinstance(uncertainties, dict), "measurement uncertainty required")
    uncertainty = {
        role: _uncertainty(uncertainties.get(role), role)
        for role in ("truth", "extrinsic", "world_alignment")
    }
    timing = manifest.get("timing")
    require(isinstance(timing, dict), "timing contract required")
    _text(timing.get("estimate_clock"), "estimate clock")
    _text(timing.get("truth_clock"), "truth clock")
    require(
        timing.get("offset_convention") == "estimate_ns=truth_ns+offset_ns",
        "explicit clock offset direction required",
    )
    offset = _integer(
        timing.get("truth_to_estimate_offset_ns"), "clock offset", signed=True
    )
    clock_bound = _integer(timing.get("offset_uncertainty_ns"), "clock uncertainty")
    skew_limit = _integer(timing.get("max_pair_skew_ns"), "max pair skew")
    require(
        skew_limit <= 1_000_000_000 and clock_bound <= skew_limit,
        "timing budget invalid",
    )
    require(
        timing.get("offset_measured_independently") is True,
        "clock offset must be independently measured",
    )
    require(
        timing.get("matching") == "mutual_unique_nearest_no_interpolation",
        "explicit matching rule required",
    )
    fixed = manifest.get("fixed_transforms")
    require(isinstance(fixed, dict), "fixed measured transforms required")
    world_from_map = transform(fixed.get("T_world_map"), world, map_frame)
    body_from_camera = transform(fixed.get("T_body_camera"), body, camera)
    estimates = _series(manifest.get("estimate"), map_frame, camera, "estimate")
    truths = _series(manifest.get("truth"), world, body, "truth")
    require(
        manifest["estimate"]["acquisition_id"] != manifest["truth"]["acquisition_id"],
        "independent truth acquisition required",
    )
    truth_stamps = [stamp + offset for stamp, _ in truths]
    require(
        all(0 <= stamp <= 2**63 - 1 for stamp in truth_stamps),
        "clock offset moved timestamp out of range",
    )
    estimate_stamps = [stamp for stamp, _ in estimates]
    # Sorted unique stamps allow bounded O(n log n) matching; avoid quadratic scans.
    import bisect

    def nearest(stamps, target):
        index = bisect.bisect_left(stamps, target)
        choices = [i for i in (index - 1, index) if 0 <= i < len(stamps)]
        distances = [(abs(stamps[i] - target), i) for i in choices]
        best = min(distance for distance, _ in distances)
        winners = [i for distance, i in distances if distance == best]
        return winners[0] if len(winners) == 1 else None

    rows = []
    for ei, (stamp, camera_pose) in enumerate(estimates):
        ti = nearest(truth_stamps, stamp)
        if ti is None or nearest(estimate_stamps, truth_stamps[ti]) != ei:
            continue
        skew = abs(stamp - truth_stamps[ti])
        if skew + clock_bound > skew_limit:
            continue
        body_pose = world_from_map @ camera_pose @ inverse(body_from_camera)
        delta = inverse(truths[ti][1]) @ body_pose
        cosine = max(-1.0, min(1.0, (float(np.trace(delta[:3, :3])) - 1.0) / 2.0))
        rows.append(
            {
                "estimate_index": ei,
                "truth_index": ti,
                "estimate_stamp_ns": str(stamp),
                "truth_stamp_ns": str(truths[ti][0]),
                "pair_skew_ns": str(skew),
                "position_error_m": float(np.linalg.norm(delta[:3, 3])),
                "rotation_error_rad": math.acos(cosine),
                "T_world_body_estimate": body_pose.tolist(),
            }
        )
    require(bool(rows), "no unambiguous time-qualified pose pairs")

    def statistics(key):
        values = sorted(row[key] for row in rows)
        return {
            "count": len(values),
            "rmse": math.sqrt(sum(x * x for x in values) / len(values)),
            "p50": float(np.median(values)),
            "p95_nearest_rank": values[math.ceil(0.95 * len(values)) - 1],
            "max": values[-1],
        }

    return {
        "schema": OUTPUT_SCHEMA,
        "status": "COMPUTED_DECLARED_INPUTS",
        "evidence_type": kind,
        "qualification_scope": "declared provenance and mathematical consistency only",
        "independent_truth_verified_by_tool": False,
        "body_extrinsic_qualified_by_tool": False,
        "accuracy_acceptance": False,
        "operational_application": "NOT_RUN",
        "alignment_fitted": False,
        "interpolation_used": False,
        "scale_fitted": False,
        "quaternion_numeric_policy": "unit norm checked within 1e-6; numeric unit correction only; input bytes unchanged",
        "estimate_samples": len(estimates),
        "truth_samples": len(truths),
        "matched_pairs": len(rows),
        "estimate_matched_fraction": len(rows) / len(estimates),
        "truth_matched_fraction": len(rows) / len(truths),
        "unmatched_estimate_samples": len(estimates) - len(rows),
        "unmatched_truth_samples": len(truths) - len(rows),
        "position_error_m": statistics("position_error_m"),
        "rotation_error_rad": statistics("rotation_error_rad"),
        "declared_uncertainty": uncertainty,
        "timing": dict(timing),
        "frames": dict(frames),
        "provenance": dict(provenance),
        "evidence": dict(evidence),
        "pairs": rows,
        "limits": [
            "Input declarations and file hashes do not prove independent measurement or physical calibration.",
            "Errors combine estimate, truth, alignment, extrinsic and timing uncertainty; no uncertainty propagation or subtraction.",
            "No RPE, whole-trajectory coverage, independent accuracy PASS or calibrated operational body pose is inferred.",
        ],
    }
