"""Pure advisory progress projection for a selected RoutePlan."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .perception import requirement_states


OFF_ROUTE_WARNING_M = 0.75
OFF_ROUTE_REPLAN_M = 1.50


def _point(value: Mapping[str, Any]) -> tuple[float, float] | None:
    try:
        x, y = float(value["x"]), float(value["y"])
    except (KeyError, TypeError, ValueError):
        return None
    return (x, y) if math.isfinite(x) and math.isfinite(y) else None


def _projection(px: float, py: float, left: tuple[float, float], right: tuple[float, float]) -> tuple[float, float, float, float]:
    dx, dy = right[0] - left[0], right[1] - left[1]
    length_sq = dx * dx + dy * dy
    fraction = 0.0 if length_sq <= 1e-12 else max(0.0, min(1.0, ((px - left[0]) * dx + (py - left[1]) * dy) / length_sq))
    x, y = left[0] + fraction * dx, left[1] + fraction * dy
    return math.hypot(px - x, py - y), fraction, x, y


def _segment_progress(points: list[Mapping[str, Any]], px: float, py: float) -> tuple[float, float, float]:
    pairs = []
    accumulated = 0.0
    for left_raw, right_raw in zip(points, points[1:]):
        left, right = _point(left_raw), _point(right_raw)
        if left is None or right is None:
            continue
        length = math.hypot(right[0] - left[0], right[1] - left[1])
        distance, fraction, _, _ = _projection(px, py, left, right)
        pairs.append((distance, accumulated + fraction * length))
        accumulated += length
    if not pairs:
        return math.inf, 0.0, 0.0
    best = min(pairs, key=lambda item: (item[0], -item[1]))
    return best[0], best[1], accumulated


def _turn_type(current: Mapping[str, Any], following: Mapping[str, Any] | None) -> str:
    if following is None:
        return "CONTINUE_STRAIGHT"
    current_points = current.get("polyline", [])
    following_points = following.get("polyline", [])
    if len(current_points) < 2 or len(following_points) < 2:
        return "CONTINUE_STRAIGHT"
    a, b = _point(current_points[-2]), _point(current_points[-1])
    c, d = _point(following_points[0]), _point(following_points[1])
    if None in {a, b, c, d}:
        return "CONTINUE_STRAIGHT"
    first = math.atan2(b[1] - a[1], b[0] - a[0])
    second = math.atan2(d[1] - c[1], d[0] - c[0])
    delta = math.atan2(math.sin(second - first), math.cos(second - first))
    if delta > math.radians(25):
        return "TURN_LEFT"
    if delta < -math.radians(25):
        return "TURN_RIGHT"
    return "CONTINUE_STRAIGHT"


def _instruction(segment: Mapping[str, Any], next_segment: Mapping[str, Any] | None, requirement_projection: Mapping[str, str]) -> tuple[str, str]:
    requirements = [str(item.get("id")) for item in segment.get("requirements", [])]
    if "TRAFFIC_GREEN" in requirements and requirement_projection.get("TRAFFIC_GREEN") != "READY":
        return "WAIT_TRAFFIC_GREEN", "신호 대기"
    if "PEDESTRIAN_CLEAR" in requirements and requirement_projection.get("PEDESTRIAN_CLEAR") != "READY":
        return "WAIT_PEDESTRIAN_CLEAR", "보행자 통행 확인"
    kind = segment.get("type")
    if kind == "CROSSWALK":
        if any(requirement_projection.get(item) != "READY" for item in requirements if item in {"CROSSWALK_ALIGNMENT", "LANE_BOUNDARY_VALID"}):
            return "ALIGN_CROSSWALK", "횡단보도 정렬"
        return "CROSS_STRAIGHT", "횡단보도를 직진"
    if kind == "UNDERPASS":
        return "ENTER_UNDERPASS", "UNDERPASS 진입"
    if kind == "DOCKING_APPROACH":
        if "ARUCO_DOCKING" in requirements and requirement_projection.get("ARUCO_DOCKING") != "READY":
            return "ARUCO_DOCK", "ArUco 도킹 준비 대기"
        return "APPROACH_RESTAURANT", "정지구역 접근"
    action = _turn_type(segment, next_segment)
    labels = {"TURN_LEFT": "왼쪽 방향", "TURN_RIGHT": "오른쪽 방향", "CONTINUE_STRAIGHT": "직진"}
    return action, labels[action]


def project_guidance(
    route: Mapping[str, Any],
    pose: Mapping[str, Any] | None,
    perception: Mapping[str, Any],
    *,
    previous_segment_index: int = 0,
    completed_pickups: list[str] | None = None,
    dropoff_complete: bool = False,
) -> dict[str, Any]:
    """Project pose onto route polylines; never produce a control command."""

    segments = list(route.get("segments", []))[:512]
    completed = list(dict.fromkeys(completed_pickups or []))[:5]
    if not segments:
        return {
            "active": False,
            "paused": True,
            "reason": "ROUTE_EMPTY",
            "instruction": "GUIDANCE PAUSED",
            "completed_pickups": completed,
            "dropoff_complete": dropoff_complete,
        }
    if not isinstance(pose, Mapping) or _point(pose) is None:
        return {
            "active": True, "paused": True, "reason": "MAP_POSE_UNAVAILABLE", "instruction_type": "OFF_ROUTE",
            "instruction": "GUIDANCE PAUSED · map pose unavailable", "current_segment_index": min(previous_segment_index, len(segments) - 1),
            "completed_pickups": completed,
            "dropoff_complete": dropoff_complete,
            "control_authority": False,
        }
    px, py = _point(pose) or (0.0, 0.0)
    candidates = []
    for index, segment in enumerate(segments):
        cross_track, along, length = _segment_progress(list(segment.get("polyline", [])), px, py)
        # Keep progress monotonic unless a dramatically closer prior segment is found.
        penalty = 0.5 if index < max(0, previous_segment_index - 1) else 0.0
        candidates.append((cross_track + penalty, index, cross_track, along, length))
    _, index, cross_track, along, length = min(candidates, key=lambda item: (item[0], -item[1]))
    index = max(min(previous_segment_index, len(segments) - 1), index) if cross_track <= OFF_ROUTE_WARNING_M else index
    cross_track, along, length = _segment_progress(list(segments[index].get("polyline", [])), px, py)
    remaining = max(0.0, length - along) + sum(float(item.get("distance_m", 0.0)) for item in segments[index + 1 :])
    off_route = cross_track > OFF_ROUTE_WARNING_M
    replan = cross_track > OFF_ROUTE_REPLAN_M and bool(segments[index].get("allow_replan", True))
    requirements = requirement_states(perception)
    if off_route:
        instruction_type = "REPLAN_AVAILABLE" if replan else "OFF_ROUTE"
        instruction = "경로 이탈 · 재계산 가능" if replan else "경로로 복귀"
    else:
        instruction_type, instruction = _instruction(segments[index], segments[index + 1] if index + 1 < len(segments) else None, requirements)
    eta_total = float(route.get("metrics", {}).get("eta_s", 0.0))
    distance_total = max(float(route.get("metrics", {}).get("distance_m", 0.0)), 0.001)
    eta_remaining = eta_total * min(1.0, remaining / distance_total)
    return {
        "active": True,
        "paused": False,
        "reason": "OFF_ROUTE" if off_route else "",
        "instruction_type": instruction_type,
        "instruction": instruction,
        "current_segment_index": index,
        "current_segment": segments[index],
        "segment_progress": round(0.0 if length <= 0 else min(1.0, along / length), 4),
        "cross_track_error_m": round(cross_track, 3),
        "remaining_distance_m": round(remaining, 3),
        "eta_remaining_s": round(eta_remaining, 3),
        "next_node_id": segments[index].get("to_node_id"),
        "requirements": requirements,
        "off_route": off_route,
        "replan_available": replan,
        "completed_pickups": completed,
        "dropoff_complete": dropoff_complete,
        "control_authority": False,
    }


__all__ = ["OFF_ROUTE_REPLAN_M", "OFF_ROUTE_WARNING_M", "project_guidance"]
