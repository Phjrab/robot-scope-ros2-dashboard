"""Revision-pinned semantic Route Graph validation."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Mapping, Protocol


GRAPH_SCHEMA_VERSION = 1
GRAPH_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
HEX24_RE = re.compile(r"^[0-9a-f]{24}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
NODE_ROLES = frozenset(
    {
        "START",
        "INTERSECTION",
        "SAFE_HOLD",
        "RESTAURANT_APPROACH",
        "RESTAURANT_DOCK",
        "DESTINATION_APPROACH",
        "DESTINATION_DOCK",
        "CROSSWALK_WAIT",
        "CROSSWALK_ENTRY",
        "CROSSWALK_EXIT",
        "UNDERPASS_ENTRY",
        "UNDERPASS_EXIT",
    }
)
EDGE_TYPES = frozenset({"NORMAL_WALKWAY", "CROSSWALK", "UNDERPASS", "DOCKING_APPROACH"})
REQUIREMENTS = frozenset(
    {
        "TRAFFIC_GREEN",
        "PEDESTRIAN_CLEAR",
        "CROSSWALK_ALIGNMENT",
        "LANE_BOUNDARY_VALID",
        "ARUCO_DOCKING",
        "SPECIAL_GAIT",
        "OPERATOR_CONFIRMATION",
    }
)
MAX_NODES = 128
MAX_EDGES = 512
MAX_POLYLINE_POINTS = 128
MAX_TOTAL_POLYLINE_POINTS = 4096
MAX_GRAPH_BYTES = 1024 * 1024


class RouteGraphError(ValueError):
    """A bounded public Route Graph validation error."""


class MapGeometry(Protocol):
    map_id: str
    revision: str

    def contains(self, x: float, y: float) -> bool: ...

    def known_free(self, x: float, y: float, *, clearance_radius: float) -> bool: ...


def _number(value: object, field: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RouteGraphError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise RouteGraphError(f"{field} is outside the supported range")
    return round(number, 6)


def _label(value: object) -> str:
    if not isinstance(value, str):
        raise RouteGraphError("node label must be text")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized or len(normalized) > 64 or any(unicodedata.category(character).startswith("C") for character in normalized):
        raise RouteGraphError("node label is invalid")
    return normalized


def _token(value: object, field: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not GRAPH_ID_RE.fullmatch(value):
        raise RouteGraphError(f"{field} is invalid")
    return value


def _pose_index(annotations: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    points = annotations.get("points")
    if not isinstance(points, list):
        raise RouteGraphError("annotation points are unavailable")
    result: dict[str, dict[str, float]] = {}
    for point in points:
        if not isinstance(point, Mapping) or not isinstance(point.get("pose"), Mapping):
            continue
        identifier = point.get("id")
        if isinstance(identifier, str) and HEX24_RE.fullmatch(identifier):
            pose = point["pose"]
            try:
                result[identifier] = {
                    "x": _number(pose.get("x"), "annotation x", -1_000_000.0, 1_000_000.0),
                    "y": _number(pose.get("y"), "annotation y", -1_000_000.0, 1_000_000.0),
                    "yaw": _number(pose.get("yaw", 0.0), "annotation yaw", -math.pi, math.pi),
                }
            except RouteGraphError:
                continue
    return result


def graph_revision(value: Mapping[str, Any]) -> str:
    canonical = {key: value[key] for key in ("schema_version", "map_id", "map_revision", "annotation_revision", "nodes", "edges")}
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_graph(
    payload: Mapping[str, Any],
    *,
    annotations: Mapping[str, Any],
    geometry: MapGeometry | None = None,
) -> dict[str, Any]:
    """Validate graph pins, annotation references, geometry, and bounds."""

    if not isinstance(payload, Mapping) or set(payload) != {
        "schema_version", "map_id", "map_revision", "annotation_revision", "nodes", "edges"
    }:
        raise RouteGraphError("route graph schema is invalid")
    if payload.get("schema_version") != GRAPH_SCHEMA_VERSION:
        raise RouteGraphError("route graph schema version is unsupported")
    map_id = payload.get("map_id")
    map_revision = payload.get("map_revision")
    annotation_revision = payload.get("annotation_revision")
    if not isinstance(map_id, str) or not HEX24_RE.fullmatch(map_id):
        raise RouteGraphError("route graph map id is invalid")
    if not isinstance(map_revision, str) or not HEX64_RE.fullmatch(map_revision):
        raise RouteGraphError("route graph map revision is invalid")
    if not isinstance(annotation_revision, str) or not HEX64_RE.fullmatch(annotation_revision):
        raise RouteGraphError("route graph annotation revision is invalid")
    if (
        annotations.get("map_id") != map_id
        or annotations.get("map_revision") != map_revision
        or annotations.get("annotation_revision") != annotation_revision
    ):
        raise RouteGraphError("route graph annotation pins changed")
    if geometry is not None and (geometry.map_id != map_id or geometry.revision != map_revision):
        raise RouteGraphError("route graph map geometry pins changed")
    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    if not isinstance(raw_nodes, list) or not 2 <= len(raw_nodes) <= MAX_NODES:
        raise RouteGraphError("route graph must contain 2 to 128 nodes")
    if not isinstance(raw_edges, list) or not 1 <= len(raw_edges) <= MAX_EDGES:
        raise RouteGraphError("route graph must contain 1 to 512 edges")
    poses = _pose_index(annotations)
    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    for raw in raw_nodes:
        allowed = {"id", "annotation_id", "role", "zone_id", "venue_id", "label", "manual_guidance", "autonomous_eligible"}
        if not isinstance(raw, Mapping) or set(raw) != allowed:
            raise RouteGraphError("route graph node schema is invalid")
        identifier = _token(raw.get("id"), "node id")
        annotation_id = raw.get("annotation_id")
        if not isinstance(annotation_id, str) or not HEX24_RE.fullmatch(annotation_id) or annotation_id not in poses:
            raise RouteGraphError("route graph node annotation is missing")
        if identifier in node_ids:
            raise RouteGraphError("route graph node ids must be unique")
        node_ids.add(str(identifier))
        role = raw.get("role")
        if role not in NODE_ROLES:
            raise RouteGraphError("route graph node role is invalid")
        manual = raw.get("manual_guidance")
        autonomous = raw.get("autonomous_eligible")
        if not isinstance(manual, bool) or not isinstance(autonomous, bool):
            raise RouteGraphError("route graph node eligibility must be boolean")
        nodes.append(
            {
                "id": identifier,
                "annotation_id": annotation_id,
                "role": role,
                "zone_id": _token(raw.get("zone_id"), "node zone", optional=True),
                "venue_id": _token(raw.get("venue_id"), "node venue", optional=True),
                "label": _label(raw.get("label")),
                "manual_guidance": manual,
                "autonomous_eligible": autonomous,
            }
        )
    nodes_by_id = {str(node["id"]): node for node in nodes}
    edges: list[dict[str, Any]] = []
    edge_ids: set[str] = set()
    incidence = {identifier: 0 for identifier in node_ids}
    total_points = 0
    for raw in raw_edges:
        allowed = {
            "id", "from", "to", "type", "bidirectional", "polyline", "distance_m",
            "nominal_speed_mps", "risk", "requirements", "allow_manual", "allow_autonomous",
            "allow_replan", "allow_turning", "allow_lateral_motion", "speed_limit_mps",
            "expected_wait_s", "penalty_risk",
        }
        if not isinstance(raw, Mapping) or set(raw) != allowed:
            raise RouteGraphError("route graph edge schema is invalid")
        identifier = _token(raw.get("id"), "edge id")
        source = _token(raw.get("from"), "edge source")
        target = _token(raw.get("to"), "edge target")
        if identifier in edge_ids:
            raise RouteGraphError("route graph edge ids must be unique")
        edge_ids.add(str(identifier))
        if source not in nodes_by_id or target not in nodes_by_id or source == target:
            raise RouteGraphError("route graph edge endpoints are invalid")
        kind = raw.get("type")
        if kind not in EDGE_TYPES:
            raise RouteGraphError("route graph edge type is invalid; use UNDERPASS")
        requirements = raw.get("requirements")
        if not isinstance(requirements, list) or len(requirements) > len(REQUIREMENTS) or any(item not in REQUIREMENTS for item in requirements):
            raise RouteGraphError("route graph edge requirements are invalid")
        if len(set(requirements)) != len(requirements):
            raise RouteGraphError("route graph edge requirements must be unique")
        polyline = raw.get("polyline")
        if not isinstance(polyline, list) or not 2 <= len(polyline) <= MAX_POLYLINE_POINTS:
            raise RouteGraphError("route graph edge polyline is invalid")
        total_points += len(polyline)
        if total_points > MAX_TOTAL_POLYLINE_POINTS:
            raise RouteGraphError("route graph polyline point limit exceeded")
        normalized_points: list[dict[str, float]] = []
        for point in polyline:
            if not isinstance(point, Mapping) or set(point) != {"x", "y"}:
                raise RouteGraphError("route graph polyline point is invalid")
            x = _number(point.get("x"), "polyline x", -1_000_000.0, 1_000_000.0)
            y = _number(point.get("y"), "polyline y", -1_000_000.0, 1_000_000.0)
            if geometry is not None and (not geometry.contains(x, y) or not geometry.known_free(x, y, clearance_radius=0.0)):
                raise RouteGraphError("route graph polyline must remain on known-free map cells")
            normalized_points.append({"x": x, "y": y})
        source_pose = poses[str(nodes_by_id[str(source)]["annotation_id"])]
        target_pose = poses[str(nodes_by_id[str(target)]["annotation_id"])]
        endpoint_tolerance = max(0.05, float(getattr(geometry, "resolution", 0.05)) * 2.0)
        if math.hypot(normalized_points[0]["x"] - source_pose["x"], normalized_points[0]["y"] - source_pose["y"]) > endpoint_tolerance:
            raise RouteGraphError("route graph edge does not start at its annotation node")
        if math.hypot(normalized_points[-1]["x"] - target_pose["x"], normalized_points[-1]["y"] - target_pose["y"]) > endpoint_tolerance:
            raise RouteGraphError("route graph edge does not end at its annotation node")
        measured = sum(math.hypot(right["x"] - left["x"], right["y"] - left["y"]) for left, right in zip(normalized_points, normalized_points[1:]))
        supplied = _number(raw.get("distance_m"), "edge distance", 0.001, 100_000.0)
        if abs(measured - supplied) > max(0.05, measured * 0.02):
            raise RouteGraphError("route graph edge distance does not match its polyline")
        booleans = {}
        for field in ("bidirectional", "allow_manual", "allow_autonomous", "allow_replan", "allow_turning", "allow_lateral_motion"):
            if not isinstance(raw.get(field), bool):
                raise RouteGraphError(f"edge {field} must be boolean")
            booleans[field] = raw[field]
        incidence[str(source)] += 1
        incidence[str(target)] += 1
        edges.append(
            {
                "id": identifier,
                "from": source,
                "to": target,
                "type": kind,
                **booleans,
                "polyline": normalized_points,
                "distance_m": round(measured, 6),
                "nominal_speed_mps": _number(raw.get("nominal_speed_mps"), "edge nominal speed", 0.01, 3.0),
                "risk": _number(raw.get("risk"), "edge risk", 0.0, 100.0),
                "requirements": list(requirements),
                "speed_limit_mps": _number(raw.get("speed_limit_mps"), "edge speed limit", 0.01, 3.0),
                "expected_wait_s": _number(raw.get("expected_wait_s"), "edge expected wait", 0.0, 600.0),
                "penalty_risk": _number(raw.get("penalty_risk"), "edge penalty risk", 0.0, 100.0),
            }
        )
    if any(count == 0 for count in incidence.values()):
        raise RouteGraphError("route graph contains an isolated node")
    document = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "map_id": map_id,
        "map_revision": map_revision,
        "annotation_revision": annotation_revision,
        "nodes": nodes,
        "edges": edges,
    }
    document["graph_revision"] = graph_revision(document)
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_GRAPH_BYTES:
        raise RouteGraphError("route graph exceeds the size limit")
    return document


def node_poses(graph: Mapping[str, Any], annotations: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    """Resolve graph node poses from the exact annotation document."""

    poses = _pose_index(annotations)
    result: dict[str, dict[str, float]] = {}
    for node in graph.get("nodes", []):
        if isinstance(node, Mapping) and node.get("annotation_id") in poses:
            result[str(node["id"])] = dict(poses[str(node["annotation_id"])])
    return result


__all__ = [
    "EDGE_TYPES", "GRAPH_SCHEMA_VERSION", "MAX_EDGES", "MAX_GRAPH_BYTES", "MAX_NODES",
    "MAX_POLYLINE_POINTS", "MAX_TOTAL_POLYLINE_POINTS", "NODE_ROLES", "REQUIREMENTS",
    "RouteGraphError", "graph_revision", "node_poses", "normalize_graph",
]
