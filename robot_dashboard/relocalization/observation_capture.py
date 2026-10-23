"""Opt-in exact numerical inputs; historical diagnostics, never pose application."""
from __future__ import annotations

import base64
import copy
import hashlib
import re
import time
from typing import Any

import numpy as np

from .experimental_se3 import Cloud, validate_transform

SCHEMA = "robot-scope.observation-input-capture.v1"
MAX_CAPTURE_BYTES = 4 * 1024 * 1024


def _encode(points: np.ndarray) -> dict[str, Any]:
    data = np.asarray(points, dtype="<f8").tobytes(order="C")
    return {"encoding": "base64-float64le-xyz", "point_count": len(points),
            "sha256": hashlib.sha256(data).hexdigest(), "data": base64.b64encode(data).decode("ascii")}


def capture_inputs(*, identifier, revision, reference, target_frame, points, frame, seed, pose, source):
    """Serialize only the exact projected/strided query and normalized reference.

    These are solver inputs, not raw sensor bytes or the original PCD. Called
    only for an explicit request, after normal completion validation succeeds.
    No file writes, new sensor reads, or changes to the worker result occur here.
    """
    return {
        "schema": SCHEMA, "data_kind": "HISTORICAL_NUMERICAL_INPUTS",
        "operational_application": "NOT_RUN", "absolute_accuracy_m": None,
        "map": {"id": identifier, "revision": revision, "frame": target_frame},
        "query_frame": frame, "units": "m", "source": copy.deepcopy(source),
        "reference": _encode(reference), "query": _encode(points),
        "T_map_odom_seed": seed.tolist(),
        "paired_pose": {key: copy.deepcopy(pose[key]) for key in
                        ("topic", "frame_id", "child_frame_id", "seq", "position", "orientation") if key in pose},
        "reference_processing": "EXACT_SOLVER_REFERENCE_NOT_ORIGINAL_PCD",
        "query_processing": "EXACT_PROJECTED_STRIDED_SOLVER_QUERY_NOT_RAW_SENSOR",
    }


def _decode(value, limit):
    count = value.get("point_count")
    if (value.get("encoding") != "base64-float64le-xyz" or type(count) is not int
            or not 60 <= count <= limit or not isinstance(value.get("data"), str)
            or len(value["data"]) != 4 * ((count * 24 + 2) // 3)):
        raise ValueError("CAPTURE_ARRAY_BOUNDS")
    data = base64.b64decode(value["data"], validate=True)
    if len(data) != count * 24 or hashlib.sha256(data).hexdigest() != value.get("sha256"):
        raise ValueError("CAPTURE_ARRAY_HASH")
    points = np.frombuffer(data, dtype="<f8").reshape(count, 3)
    if not np.isfinite(points).all():
        raise ValueError("CAPTURE_NONFINITE")
    return points


def decode_capture(payload):
    """Check a saved response before replay; no pickle or external file references."""
    try:
        value = payload["input_capture"]
        if (payload["schema"] != "robot-scope.observation-alignment.v1"
                or payload["operational_application"] != "NOT_RUN"
                or value["schema"] != SCHEMA or value["data_kind"] != "HISTORICAL_NUMERICAL_INPUTS"
                or value["operational_application"] != "NOT_RUN" or value["units"] != "m"
                or value["map"] != {"id": payload["map_id"], "revision": payload["map_revision"], "frame": payload["target_frame"]}
                or value["source"] != payload["source"]
                or not re.fullmatch(r"[a-f0-9]{24}", payload["map_id"])
                or not re.fullmatch(r"[a-f0-9]{64}", payload["map_revision"])):
            raise ValueError("CAPTURE_IDENTITY_MISMATCH")
        stamp = value["source"]["source_stamp_ns"]
        if not isinstance(stamp, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", stamp):
            raise ValueError("CAPTURE_SOURCE_STAMP")
        pose = value["paired_pose"]
        if pose["frame_id"] != value["query_frame"] or pose["topic"] != value["source"]["pose_topic"]:
            raise ValueError("CAPTURE_POSE_FRAME")
        reference, points = _decode(value["reference"], 100_000), _decode(value["query"], 512)
        if len(reference) != payload["reference_points"] or len(points) != payload["query_points"]:
            raise ValueError("CAPTURE_POINT_COUNT")
        Cloud(reference, value["map"]["frame"], "REGISTERED_MAP").validated(reference=True, max_points=100_000)
        Cloud(points, value["query_frame"], "REGISTERED_QUERY", stamp_ns=int(stamp)).validated(reference=False)
        return value, reference, points, validate_transform(value["T_map_odom_seed"])
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("CAPTURE_FIELDS") from exc


def replay_capture(payload, *, budget_s=10.0):
    """Offline numerical replay with an explicit budget; original result is retained."""
    from .observation_alignment import ReferenceIndex, solve_prepared
    from .observation_policy import qualify_observation

    if not isinstance(budget_s, (int, float)) or not 0 < budget_s <= 60:
        raise ValueError("REPLAY_BUDGET")
    value, reference, points, seed = decode_capture(payload)
    deadline = time.monotonic() + budget_s
    grid = ReferenceIndex(reference, deadline=deadline)
    result, transform = solve_prepared(reference, grid, value["map"]["frame"], points,
                                      value["query_frame"], int(value["source"]["source_stamp_ns"]), seed, deadline)
    assessment = qualify_observation(result, inlier_count=result["metrics"]["inlier_count"], query_count=len(points))
    return {"schema": "robot-scope.observation-input-replay.v1", "data_kind": "HISTORICAL_NUMERICAL_REPLAY",
            "operational_application": "NOT_RUN", "absolute_accuracy_m": None,
            "map": value["map"], "source_stamp_ns": value["source"]["source_stamp_ns"],
            "reference_sha256": value["reference"]["sha256"], "query_sha256": value["query"]["sha256"],
            "original": {key: copy.deepcopy(item) for key, item in payload.items() if key != "input_capture"},
            "replay": {**assessment, "metrics": result["metrics"], "T_map_odom": transform.tolist()},
            "budget_s": budget_s, "current_pose_valid": False,
            "qualification": "Offline current-solver replay; runtime, platform and library versions may differ."}
