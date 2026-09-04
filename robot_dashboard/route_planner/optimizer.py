"""Deterministic bounded competition route recommendation engine."""

from __future__ import annotations

import hashlib
import heapq
import itertools
import json
import math
from typing import Any, Mapping

from .catalog import CATALOG_REVISION, competition_catalog
from .graph import node_poses
from .perception import requirement_states


PROFILES = ("BALANCED", "FASTEST", "SAFEST")
OPERATION_MODES = frozenset({"MANUAL_GUIDANCE", "AUTO_NAV2"})


class RoutePlanningError(RuntimeError):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason


def _edge_metrics(edge: Mapping[str, Any]) -> dict[str, float]:
    distance = float(edge["distance_m"])
    speed = min(float(edge["nominal_speed_mps"]), float(edge["speed_limit_mps"]))
    travel = distance / max(speed, 0.01)
    return {
        "distance_m": distance,
        "travel_time_s": travel,
        "signal_wait_s": float(edge["expected_wait_s"]) if "TRAFFIC_GREEN" in edge["requirements"] else 0.0,
        "risk_score": float(edge["risk"]) + float(edge["penalty_risk"]),
        "crosswalk_count": 1.0 if edge["type"] == "CROSSWALK" else 0.0,
        "underpass_count": 1.0 if edge["type"] == "UNDERPASS" else 0.0,
        "special_behavior_count": 1.0 if edge["requirements"] else 0.0,
    }


def _edge_cost(edge: Mapping[str, Any], profile: str) -> float:
    weights = competition_catalog()["profiles"][profile]
    metrics = _edge_metrics(edge)
    return (
        weights["time"] * (metrics["travel_time_s"] + metrics["signal_wait_s"])
        + weights["risk"] * metrics["risk_score"]
        + weights["crosswalk"] * metrics["crosswalk_count"]
        + weights["underpass"] * metrics["underpass_count"]
    )


def _adjacency(graph: Mapping[str, Any], operation_mode: str) -> dict[str, list[tuple[str, Mapping[str, Any], bool]]]:
    result: dict[str, list[tuple[str, Mapping[str, Any], bool]]] = {str(node["id"]): [] for node in graph["nodes"]}
    nodes = {str(node["id"]): node for node in graph["nodes"]}
    for edge in graph["edges"]:
        allowed = edge["allow_manual"] if operation_mode == "MANUAL_GUIDANCE" else edge["allow_autonomous"]
        if not allowed:
            continue
        if operation_mode == "MANUAL_GUIDANCE" and not (nodes[str(edge["from"])]["manual_guidance"] and nodes[str(edge["to"])]["manual_guidance"]):
            continue
        if operation_mode == "AUTO_NAV2" and not (nodes[str(edge["from"])]["autonomous_eligible"] and nodes[str(edge["to"])]["autonomous_eligible"]):
            continue
        result[str(edge["from"])].append((str(edge["to"]), edge, False))
        if edge["bidirectional"]:
            result[str(edge["to"])].append((str(edge["from"]), edge, True))
    for values in result.values():
        values.sort(key=lambda item: (str(item[1]["id"]), item[0], item[2]))
    return result


def _shortest(graph: Mapping[str, Any], source: str, target: str, profile: str, operation_mode: str) -> list[tuple[Mapping[str, Any], bool]]:
    adjacency = _adjacency(graph, operation_mode)
    heap: list[tuple[float, tuple[str, ...], str, list[tuple[Mapping[str, Any], bool]]]] = [(0.0, (source,), source, [])]
    best: dict[str, tuple[float, tuple[str, ...]]] = {}
    while heap:
        cost, sequence, current, path = heapq.heappop(heap)
        prior = best.get(current)
        if prior is not None and prior <= (cost, sequence):
            continue
        best[current] = (cost, sequence)
        if current == target:
            return path
        for neighbor, edge, reverse in adjacency.get(current, []):
            next_cost = cost + _edge_cost(edge, profile)
            heapq.heappush(heap, (next_cost, sequence + (neighbor,), neighbor, path + [(edge, reverse)]))
    raise RoutePlanningError("GRAPH_DISCONNECTED", f"no route from {source} to {target}")


def _venue_node(graph: Mapping[str, Any], venue_id: str, roles: set[str], operation_mode: str) -> str:
    eligible = []
    for node in graph["nodes"]:
        if node.get("venue_id") != venue_id or node.get("role") not in roles:
            continue
        if operation_mode == "MANUAL_GUIDANCE" and node.get("manual_guidance") is not True:
            continue
        if operation_mode == "AUTO_NAV2" and node.get("autonomous_eligible") is not True:
            continue
        eligible.append(str(node["id"]))
    if not eligible:
        reason = "NO_AUTONOMOUS_ELIGIBLE_ROUTE" if operation_mode == "AUTO_NAV2" else "RESTAURANT_UNREACHABLE"
        raise RoutePlanningError(reason, f"no eligible route node for {venue_id}")
    return sorted(eligible)[0]


def _reverse_polyline(points: list[Mapping[str, Any]], reverse: bool) -> list[dict[str, float]]:
    values = reversed(points) if reverse else points
    return [{"x": float(point["x"]), "y": float(point["y"]), "z": 0.035} for point in values]


def _candidate(
    *,
    order: Mapping[str, Any],
    graph: Mapping[str, Any],
    annotations: Mapping[str, Any],
    start_node_id: str,
    permutation: tuple[str, ...],
    profile: str,
    operation_mode: str,
    perception: Mapping[str, Any],
) -> dict[str, Any]:
    nodes = {str(node["id"]): node for node in graph["nodes"]}
    restaurant_nodes = {venue: _venue_node(graph, venue, {"RESTAURANT_DOCK", "RESTAURANT_APPROACH"}, operation_mode) for venue in permutation}
    destination_node = _venue_node(graph, str(order["destination_id"]), {"DESTINATION_DOCK", "DESTINATION_APPROACH"}, operation_mode)
    stop_nodes = [restaurant_nodes[venue] for venue in permutation] + [destination_node]
    current = start_node_id
    edge_path: list[tuple[Mapping[str, Any], bool]] = []
    stop_edge_indexes: list[int] = []
    node_ids = [start_node_id]
    for target in stop_nodes:
        leg = _shortest(graph, current, target, profile, operation_mode)
        for edge, reverse in leg:
            next_node = str(edge["from"] if reverse else edge["to"])
            edge_path.append((edge, reverse))
            node_ids.append(next_node)
        stop_edge_indexes.append(len(edge_path))
        current = target
    elapsed = 0.0
    distance = 0.0
    travel = 0.0
    food_wait = 0.0
    signal_wait = 0.0
    risk = 0.0
    crosswalks = 0
    underpasses = 0
    special = 0
    turns = 0
    requirement_projection = requirement_states(perception)
    all_requirements_ready = True
    segments: list[dict[str, Any]] = []
    last_heading: float | None = None
    for index, (edge, reverse) in enumerate(edge_path):
        metrics = _edge_metrics(edge)
        elapsed += metrics["travel_time_s"] + metrics["signal_wait_s"]
        distance += metrics["distance_m"]
        travel += metrics["travel_time_s"]
        signal_wait += metrics["signal_wait_s"]
        risk += metrics["risk_score"]
        crosswalks += int(metrics["crosswalk_count"])
        underpasses += int(metrics["underpass_count"])
        special += int(metrics["special_behavior_count"])
        points = _reverse_polyline(edge["polyline"], reverse)
        if len(points) >= 2:
            heading = math.atan2(points[1]["y"] - points[0]["y"], points[1]["x"] - points[0]["x"])
            if last_heading is not None and abs(math.atan2(math.sin(heading - last_heading), math.cos(heading - last_heading))) > math.radians(25):
                turns += 1
            last_heading = heading
        requirements = [{"id": item, "state": requirement_projection.get(item, "UNKNOWN")} for item in edge["requirements"]]
        if operation_mode == "AUTO_NAV2" and any(item["state"] != "READY" for item in requirements):
            all_requirements_ready = False
        segments.append(
            {
                "index": index,
                "edge_id": edge["id"],
                "from_node_id": edge["to"] if reverse else edge["from"],
                "to_node_id": edge["from"] if reverse else edge["to"],
                "type": edge["type"],
                "label": f"{nodes[str(edge['to'] if reverse else edge['from'])]['label']} → {nodes[str(edge['from'] if reverse else edge['to'])]['label']}",
                "polyline": points,
                "distance_m": round(metrics["distance_m"], 3),
                "travel_time_s": round(metrics["travel_time_s"], 3),
                "expected_wait_s": round(float(edge["expected_wait_s"]), 3),
                "risk": round(metrics["risk_score"], 3),
                "requirements": requirements,
                "allow_replan": edge["allow_replan"],
            }
        )
        completed_edges = index + 1
        if completed_edges in stop_edge_indexes[:-1]:
            stop_position = stop_edge_indexes.index(completed_edges)
            venue = permutation[stop_position]
            ready_at = max(float(line["ready_at_s"]) for line in order["lines"] if line["restaurant_id"] == venue)
            wait = max(0.0, ready_at - elapsed)
            food_wait += wait
            elapsed += wait
    weights = competition_catalog()["profiles"][profile]
    score = (
        weights["time"] * elapsed
        + weights["risk"] * risk
        + weights["crosswalk"] * crosswalks
        + weights["underpass"] * underpasses
        + weights["turn"] * turns
    )
    stops = []
    for index, node_id in enumerate(stop_nodes):
        node = nodes[node_id]
        stops.append(
            {
                "index": index,
                "node_id": node_id,
                "annotation_id": node["annotation_id"],
                "role": node["role"],
                "venue_id": node.get("venue_id"),
                "label": node["label"],
            }
        )
    node_poses(graph, annotations)
    route_key = {"nodes": node_ids, "profile": profile, "operation_mode": operation_mode, "order_revision": order["revision"], "graph_revision": graph["graph_revision"]}
    digest = hashlib.sha256(json.dumps(route_key, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
    assumptions = ["ORDER_SEQUENCE_20S", "GRAPH_EDGE_SPEED_AND_WAIT"]
    if perception.get("fresh") is not True:
        assumptions.append("PERCEPTION_UNKNOWN_OR_STALE")
    return {
        "id": digest[:32],
        "revision": digest,
        "order_id": order["id"],
        "order_revision": order["revision"],
        "graph_revision": graph["graph_revision"],
        "map_id": graph["map_id"],
        "map_revision": graph["map_revision"],
        "annotation_revision": graph["annotation_revision"],
        "catalog_revision": CATALOG_REVISION,
        "planner_config_revision": CATALOG_REVISION,
        "profile": profile,
        "profiles": [profile],
        "operation_mode": operation_mode,
        "start_node_id": start_node_id,
        "node_ids": node_ids,
        "stops": stops,
        "segments": segments,
        "metrics": {
            "score": round(score, 3),
            "distance_m": round(distance, 3),
            "travel_time_s": round(travel, 3),
            "food_wait_s": round(food_wait, 3),
            "signal_wait_s": round(signal_wait, 3),
            "risk_score": round(risk, 3),
            "eta_s": round(elapsed, 3),
            "crosswalk_count": crosswalks,
            "underpass_count": underpasses,
            "turn_count": turns,
            "special_behavior_count": special,
        },
        "assumptions": assumptions,
        "autonomous_eligible": operation_mode == "AUTO_NAV2",
        "executable": operation_mode == "AUTO_NAV2" and all_requirements_ready,
        "reason": "" if all_requirements_ready else "SPECIAL_EDGE_NOT_READY",
        "preview_kind": "ROUTE_GRAPH_2D_PROJECTED_IN_3D",
    }


def recommend_routes(
    *,
    order: Mapping[str, Any],
    graph: Mapping[str, Any],
    annotations: Mapping[str, Any],
    start_node_id: str,
    operation_mode: str,
    perception: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return at most one deterministic recommendation per fixed profile."""

    if operation_mode not in OPERATION_MODES:
        raise RoutePlanningError("ORDER_INVALID", "operation mode is invalid")
    nodes = {str(node["id"]): node for node in graph.get("nodes", [])}
    if start_node_id not in nodes:
        raise RoutePlanningError("NO_START_NODE", "start node does not exist")
    restaurant_ids = sorted({str(line["restaurant_id"]) for line in order["lines"]})
    if not 2 <= len(restaurant_ids) <= 3:
        raise RoutePlanningError("ORDER_INVALID", "order restaurant count is invalid")
    results: list[dict[str, Any]] = []
    for profile in PROFILES:
        candidates = []
        errors: list[RoutePlanningError] = []
        for permutation in itertools.permutations(restaurant_ids):
            try:
                candidates.append(
                    _candidate(
                        order=order, graph=graph, annotations=annotations, start_node_id=start_node_id,
                        permutation=permutation, profile=profile, operation_mode=operation_mode, perception=perception,
                    )
                )
            except RoutePlanningError as exc:
                errors.append(exc)
        if not candidates:
            if errors:
                raise errors[0]
            raise RoutePlanningError("GRAPH_DISCONNECTED", "no candidate route exists")
        candidates.sort(key=lambda item: (item["metrics"]["score"], item["metrics"]["distance_m"], item["metrics"]["risk_score"], tuple(item["node_ids"])))
        winner = candidates[0]
        duplicate = next((item for item in results if item["node_ids"] == winner["node_ids"]), None)
        if duplicate is not None:
            duplicate["profiles"].append(profile)
        else:
            results.append(winner)
    return results[:3]


__all__ = ["OPERATION_MODES", "PROFILES", "RoutePlanningError", "recommend_routes"]
