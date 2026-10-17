"""Small operator-attestation contract; never an inferred body attitude."""
from __future__ import annotations

import math
from typing import Any

from .slam_sessions import SlamError


def validate_confirmation(value: Any) -> None:
    required = {"robot_seated", "robot_stationary", "camera_stationary"}
    if (not isinstance(value, dict) or set(value) - required - {"body_attitude"}
            or any(value.get(key) is not True for key in required)):
        raise SlamError("DEPTH_STATIONARY_CONFIRMATION_REQUIRED", 422)
    attitude = value.get("body_attitude")
    if attitude is None:
        return
    fields = {"quaternion_xyzw", "frame_id", "source", "source_timestamp_ns", "clock_domain"}
    if not isinstance(attitude, dict) or set(attitude) != fields:
        raise SlamError("INVALID_BODY_ATTITUDE", 422)
    for key in fields - {"quaternion_xyzw"}:
        item = attitude[key]
        if not isinstance(item, str) or not 1 <= len(item) <= 128 or any(ord(c) < 32 for c in item):
            raise SlamError("INVALID_BODY_ATTITUDE", 422)
    if not attitude["source_timestamp_ns"].isdigit() or len(attitude["source_timestamp_ns"]) > 30:
        raise SlamError("INVALID_BODY_ATTITUDE", 422)
    q = attitude["quaternion_xyzw"]
    if (not isinstance(q, list) or len(q) != 4
            or any(type(v) not in {float, int} or not math.isfinite(v) for v in q)
            or abs(sum(v*v for v in q) - 1) > 1e-3):
        raise SlamError("INVALID_BODY_ATTITUDE", 422)
