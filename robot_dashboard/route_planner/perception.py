"""Typed, freshness-gated inputs supplied by the Track G perception teams."""

from __future__ import annotations

import copy
import math
import re
import time
from typing import Any, Mapping, Protocol


MAX_SNAPSHOT_AGE_S = 1.0
_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class PerceptionContractError(ValueError):
    pass


class RoutePerceptionProvider(Protocol):
    def snapshot(self) -> dict[str, Any]: ...


def empty_perception_snapshot(*, now_ns: int | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source": "route-planner-mock",
        "frame_id": "base_link",
        "observed_at_ns": int(now_ns if now_ns is not None else time.time_ns()),
        "sequence": 0,
        "state": "UNKNOWN",
        "confidence": 0.0,
        "traffic": [],
        "crosswalks": [],
        "people": [],
        "aruco": [],
        "underpass_blocked": None,
    }


def _finite(value: object, field: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PerceptionContractError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise PerceptionContractError(f"{field} is outside the supported range")
    return number


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise PerceptionContractError(f"{field} is invalid")
    return value


def _exact_entry(value: Mapping[str, Any], required: set[str], optional: set[str], field: str) -> None:
    keys = set(value)
    if not required <= keys or not keys <= required | optional:
        raise PerceptionContractError(f"{field} schema is invalid")


def _confidence(value: Mapping[str, Any], field: str) -> float | None:
    return _finite(value["confidence"], f"{field} confidence", 0.0, 1.0) if "confidence" in value else None


def _normalize_traffic(value: Mapping[str, Any]) -> dict[str, Any]:
    _exact_entry(value, {"crosswalk_id", "signal"}, {"confidence", "consecutive_frames"}, "traffic entry")
    result: dict[str, Any] = {
        "crosswalk_id": _token(value["crosswalk_id"], "traffic crosswalk_id"),
        "signal": str(value["signal"]),
    }
    if result["signal"] not in {"RED", "GREEN", "UNKNOWN"}:
        raise PerceptionContractError("traffic signal is invalid")
    confidence = _confidence(value, "traffic")
    if confidence is not None:
        result["confidence"] = round(confidence, 6)
    if "consecutive_frames" in value:
        frames = value["consecutive_frames"]
        if isinstance(frames, bool) or not isinstance(frames, int) or not 0 <= frames <= 10_000:
            raise PerceptionContractError("traffic consecutive_frames is invalid")
        result["consecutive_frames"] = frames
    return result


def _normalize_crosswalk(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "crosswalk_id", "visible", "lateral_offset_m", "heading_error_rad",
        "left_boundary_distance_m", "right_boundary_distance_m",
    }
    _exact_entry(value, required, {"confidence"}, "crosswalk entry")
    if not isinstance(value["visible"], bool):
        raise PerceptionContractError("crosswalk visibility is invalid")
    result = {
        "crosswalk_id": _token(value["crosswalk_id"], "crosswalk crosswalk_id"),
        "visible": value["visible"],
        "lateral_offset_m": _finite(value["lateral_offset_m"], "crosswalk lateral offset", -100.0, 100.0),
        "heading_error_rad": _finite(value["heading_error_rad"], "crosswalk heading error", -math.pi, math.pi),
        "left_boundary_distance_m": _finite(value["left_boundary_distance_m"], "left boundary distance", 0.0, 100.0),
        "right_boundary_distance_m": _finite(value["right_boundary_distance_m"], "right boundary distance", 0.0, 100.0),
    }
    confidence = _confidence(value, "crosswalk")
    if confidence is not None:
        result["confidence"] = round(confidence, 6)
    return result


def _normalize_person(value: Mapping[str, Any]) -> dict[str, Any]:
    _exact_entry(value, {"crosswalk_id", "occupancy"}, {"nearest_distance_m", "collision_risk", "confidence"}, "person entry")
    result: dict[str, Any] = {
        "crosswalk_id": _token(value["crosswalk_id"], "person crosswalk_id"),
        "occupancy": str(value["occupancy"]),
    }
    if result["occupancy"] not in {"CLEAR", "OCCUPIED", "UNKNOWN"}:
        raise PerceptionContractError("person occupancy is invalid")
    if "nearest_distance_m" in value:
        result["nearest_distance_m"] = _finite(value["nearest_distance_m"], "nearest person distance", 0.0, 1_000.0)
    if "collision_risk" in value:
        if not isinstance(value["collision_risk"], bool):
            raise PerceptionContractError("person collision_risk is invalid")
        result["collision_risk"] = value["collision_risk"]
    confidence = _confidence(value, "person")
    if confidence is not None:
        result["confidence"] = round(confidence, 6)
    return result


def _normalize_aruco(value: Mapping[str, Any]) -> dict[str, Any]:
    _exact_entry(value, {"venue_id", "docking_ready"}, {"zone_id", "marker_ids", "target_pose", "confidence"}, "aruco entry")
    if not isinstance(value["docking_ready"], bool):
        raise PerceptionContractError("aruco docking_ready is invalid")
    result: dict[str, Any] = {
        "venue_id": _token(value["venue_id"], "aruco venue_id"),
        "docking_ready": value["docking_ready"],
    }
    if "zone_id" in value:
        result["zone_id"] = _token(value["zone_id"], "aruco zone_id")
    if "marker_ids" in value:
        marker_ids = value["marker_ids"]
        if not isinstance(marker_ids, list) or len(marker_ids) > 16 or any(isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 2_147_483_647 for item in marker_ids):
            raise PerceptionContractError("aruco marker_ids are invalid")
        result["marker_ids"] = list(dict.fromkeys(marker_ids))
    if "target_pose" in value:
        pose = value["target_pose"]
        if not isinstance(pose, Mapping) or set(pose) != {"x", "y", "z", "yaw"}:
            raise PerceptionContractError("aruco target_pose schema is invalid")
        result["target_pose"] = {
            key: _finite(pose[key], f"aruco target_pose {key}", -1_000.0, 1_000.0)
            for key in ("x", "y", "z", "yaw")
        }
    confidence = _confidence(value, "aruco")
    if confidence is not None:
        result["confidence"] = round(confidence, 6)
    return result


def normalize_perception_snapshot(value: Mapping[str, Any], *, now_ns: int | None = None) -> dict[str, Any]:
    allowed = {
        "schema_version", "source", "frame_id", "observed_at_ns", "sequence", "state", "confidence",
        "traffic", "crosswalks", "people", "aruco", "underpass_blocked",
    }
    if not isinstance(value, Mapping) or set(value) != allowed or value.get("schema_version") != 1:
        raise PerceptionContractError("perception snapshot schema is invalid")
    source = value.get("source")
    frame_id = value.get("frame_id")
    if not isinstance(source, str) or not 1 <= len(source) <= 64 or not isinstance(frame_id, str) or not 1 <= len(frame_id) <= 128:
        raise PerceptionContractError("perception source or frame is invalid")
    observed = value.get("observed_at_ns")
    sequence = value.get("sequence")
    if isinstance(observed, bool) or not isinstance(observed, int) or observed < 0 or isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise PerceptionContractError("perception timestamp or sequence is invalid")
    state = value.get("state")
    if state not in {"READY", "UNKNOWN", "FAILED"}:
        raise PerceptionContractError("perception state is invalid")
    confidence = _finite(value.get("confidence"), "perception confidence", 0.0, 1.0)
    lists: dict[str, list[dict[str, Any]]] = {}
    normalizers = {
        "traffic": _normalize_traffic,
        "crosswalks": _normalize_crosswalk,
        "people": _normalize_person,
        "aruco": _normalize_aruco,
    }
    for key, normalizer in normalizers.items():
        items = value.get(key)
        if not isinstance(items, list) or len(items) > 32 or any(not isinstance(item, Mapping) for item in items):
            raise PerceptionContractError(f"perception {key} list is invalid")
        lists[key] = [normalizer(item) for item in items]
    underpass = value.get("underpass_blocked")
    if underpass is not None and not isinstance(underpass, bool):
        raise PerceptionContractError("underpass state is invalid")
    current_ns = int(now_ns if now_ns is not None else time.time_ns())
    age_s = max(0.0, (current_ns - observed) / 1_000_000_000.0)
    fresh = state == "READY" and age_s <= MAX_SNAPSHOT_AGE_S
    return {
        "schema_version": 1,
        "source": source,
        "frame_id": frame_id,
        "observed_at_ns": observed,
        "sequence": sequence,
        "state": state,
        "confidence": round(confidence, 6),
        **lists,
        "underpass_blocked": underpass,
        "age_s": round(age_s, 3),
        "fresh": fresh,
    }


def requirement_states(snapshot: Mapping[str, Any]) -> dict[str, str]:
    """Project model outputs into route requirements without choosing actions."""

    if snapshot.get("fresh") is not True:
        return {
            "TRAFFIC_GREEN": "UNKNOWN", "PEDESTRIAN_CLEAR": "UNKNOWN",
            "CROSSWALK_ALIGNMENT": "UNKNOWN", "LANE_BOUNDARY_VALID": "UNKNOWN",
            "ARUCO_DOCKING": "UNKNOWN", "SPECIAL_GAIT": "OPERATOR",
            "OPERATOR_CONFIRMATION": "OPERATOR",
        }
    traffic = [str(item.get("signal", "UNKNOWN")) for item in snapshot.get("traffic", [])]
    people = [str(item.get("occupancy", "UNKNOWN")) for item in snapshot.get("people", [])]
    crosswalks = list(snapshot.get("crosswalks", []))
    aruco = list(snapshot.get("aruco", []))
    traffic_state = "READY" if traffic and all(item == "GREEN" for item in traffic) else "BLOCKED" if "RED" in traffic else "UNKNOWN"
    people_state = "READY" if people and all(item == "CLEAR" for item in people) else "BLOCKED" if "OCCUPIED" in people else "UNKNOWN"
    alignment_state = "READY" if crosswalks and all(item.get("visible") is True and abs(float(item.get("lateral_offset_m", 99))) <= 0.15 and abs(float(item.get("heading_error_rad", 99))) <= 0.2 for item in crosswalks) else "UNKNOWN"
    boundary_state = "READY" if crosswalks and all(float(item.get("left_boundary_distance_m", -1)) >= 0 and float(item.get("right_boundary_distance_m", -1)) >= 0 for item in crosswalks) else "UNKNOWN"
    aruco_state = "READY" if aruco and any(item.get("docking_ready") is True for item in aruco) else "UNKNOWN"
    return {
        "TRAFFIC_GREEN": traffic_state,
        "PEDESTRIAN_CLEAR": people_state,
        "CROSSWALK_ALIGNMENT": alignment_state,
        "LANE_BOUNDARY_VALID": boundary_state,
        "ARUCO_DOCKING": aruco_state,
        "SPECIAL_GAIT": "OPERATOR",
        "OPERATOR_CONFIRMATION": "OPERATOR",
    }


class MockRoutePerceptionProvider:
    """In-memory test provider; it never trains or runs inference."""

    def __init__(self, value: Mapping[str, Any] | None = None, *, now_ns: Any = time.time_ns) -> None:
        self._now_ns = now_ns
        self._value = dict(value) if value is not None else empty_perception_snapshot(now_ns=now_ns())
        self._last_sequence = -1

    def set_snapshot(self, value: Mapping[str, Any]) -> None:
        normalized = normalize_perception_snapshot(value, now_ns=self._now_ns())
        if int(normalized["sequence"]) <= self._last_sequence:
            raise PerceptionContractError("perception sequence must increase monotonically")
        self._last_sequence = int(normalized["sequence"])
        self._value = dict(value)

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(normalize_perception_snapshot(self._value, now_ns=self._now_ns()))


__all__ = [
    "MAX_SNAPSHOT_AGE_S", "MockRoutePerceptionProvider", "PerceptionContractError",
    "RoutePerceptionProvider", "empty_perception_snapshot", "normalize_perception_snapshot", "requirement_states",
]
