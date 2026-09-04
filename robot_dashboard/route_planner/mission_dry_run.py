"""Pure Mission draft compiler for Route Planner previews and rehearsal."""

from __future__ import annotations

import copy
import re
from typing import Any, Mapping


MAX_MISSION_WAYPOINTS = 32
MISSION_NODE_ROLES = frozenset(
    {
        "SAFE_HOLD",
        "RESTAURANT_APPROACH",
        "RESTAURANT_DOCK",
        "DESTINATION_APPROACH",
        "DESTINATION_DOCK",
        "CROSSWALK_WAIT",
        "CROSSWALK_EXIT",
        "UNDERPASS_ENTRY",
        "UNDERPASS_EXIT",
    }
)
CONFIRMATION_ROLES = frozenset(
    {"CROSSWALK_WAIT", "SAFE_HOLD", "RESTAURANT_DOCK", "DESTINATION_DOCK"}
)
DRY_RUN_SIDE_EFFECT_COUNTERS = {
    "control_acquire": 0,
    "arm": 0,
    "deadman": 0,
    "velocity": 0,
    "navigation_activate": 0,
    "navigation_goal": 0,
    "mission_create": 0,
    "mission_start": 0,
    "sport": 0,
    "service_restart": 0,
}
_HEX24 = re.compile(r"^[0-9a-f]{24}$")


def _base(route: Mapping[str, Any], order: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "MISSION_DRAFT_DRY_RUN",
        "route_id": str(route.get("id", ""))[:32],
        "route_revision": str(route.get("revision", ""))[:64],
        "label": f"{str(order.get('label', 'Competition order'))[:48]} · {str(route.get('profile', ''))[:16]}"[
            :64
        ],
        "map_id": str(route.get("map_id", ""))[:24],
        "map_revision": str(route.get("map_revision", ""))[:64],
        "annotation_revision": str(route.get("annotation_revision", ""))[:64],
        "graph_revision": str(route.get("graph_revision", ""))[:64],
        "resolved_annotation_ids": [],
        "waypoints": [],
        "waypoint_count": 0,
        "special_segment_links": [],
        "eligibility": False,
        "rejection_reason": None,
        "mission_created": False,
        "mission_started": False,
        "navigation_goal_submitted": False,
        "motion_authority": False,
        "side_effect_count": 0,
        "side_effect_counters": dict(DRY_RUN_SIDE_EFFECT_COUNTERS),
    }


def compile_mission_dry_run(
    *,
    route: Mapping[str, Any],
    graph: Mapping[str, Any],
    order: Mapping[str, Any],
    annotations: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve a bounded Mission-shaped preview without calling a Mission port."""

    result = _base(route, order)
    pins = (
        ("map_id", graph.get("map_id")),
        ("map_revision", graph.get("map_revision")),
        ("annotation_revision", graph.get("annotation_revision")),
        ("graph_revision", graph.get("graph_revision")),
    )
    if any(route.get(key) != value for key, value in pins):
        result["rejection_reason"] = "REVISION_MISMATCH"
        return result
    if (
        annotations.get("map_id") != route.get("map_id")
        or annotations.get("map_revision") != route.get("map_revision")
        or annotations.get("annotation_revision") != route.get("annotation_revision")
    ):
        result["rejection_reason"] = "ANNOTATION_REVISION_MISMATCH"
        return result
    annotation_ids = {
        str(point.get("id"))
        for point in annotations.get("points", [])
        if isinstance(point, Mapping) and _HEX24.fullmatch(str(point.get("id", "")))
    }
    nodes = {
        str(node.get("id")): node
        for node in graph.get("nodes", [])
        if isinstance(node, Mapping)
    }
    waypoint_nodes: list[Mapping[str, Any]] = []
    for node_id in route.get("node_ids", []):
        node = nodes.get(str(node_id))
        if not node or node.get("role") not in MISSION_NODE_ROLES:
            continue
        if not waypoint_nodes or waypoint_nodes[-1].get("id") != node.get("id"):
            waypoint_nodes.append(node)
    if not waypoint_nodes:
        result["rejection_reason"] = "NO_MISSION_WAYPOINTS"
        return result
    if len(waypoint_nodes) > MAX_MISSION_WAYPOINTS:
        result["rejection_reason"] = "MISSION_WAYPOINT_LIMIT"
        return result
    waypoints = []
    for node in waypoint_nodes:
        annotation_id = str(node.get("annotation_id", ""))
        if not _HEX24.fullmatch(annotation_id) or annotation_id not in annotation_ids:
            result["rejection_reason"] = "MISSING_ANNOTATION"
            return result
        role = str(node.get("role", ""))
        waypoints.append(
            {
                "annotation_id": annotation_id,
                "label": str(node.get("label", "Waypoint"))[:64],
                "arrival_tolerance": None,
                "hold_seconds": 0.0,
                "requires_operator_confirmation": role in CONFIRMATION_ROLES,
                "role": role,
            }
        )
    special_links = [
        {
            "segment_index": int(segment.get("index", index)),
            "edge_id": str(segment.get("edge_id", ""))[:64],
            "type": str(segment.get("type", ""))[:32],
            "requirements": [
                str(item.get("id", ""))[:32]
                for item in segment.get("requirements", [])[:7]
                if isinstance(item, Mapping)
            ],
        }
        for index, segment in enumerate(route.get("segments", [])[:512])
        if isinstance(segment, Mapping) and segment.get("requirements")
    ]
    result.update(
        resolved_annotation_ids=[item["annotation_id"] for item in waypoints],
        waypoints=waypoints,
        waypoint_count=len(waypoints),
        special_segment_links=special_links[:64],
        eligibility=True,
    )
    return copy.deepcopy(result)


__all__ = [
    "DRY_RUN_SIDE_EFFECT_COUNTERS",
    "MAX_MISSION_WAYPOINTS",
    "MISSION_NODE_ROLES",
    "compile_mission_dry_run",
]
