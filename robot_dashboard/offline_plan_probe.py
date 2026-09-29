"""Bounded, read-only occupancy connectivity probe; never a Nav2 plan.

This deliberately has no ROS, control, mission, or transport imports.  The
cell-center path is diagnostic evidence only and must not be sent to a robot.
"""

from __future__ import annotations

import heapq
import math
from typing import Any, Mapping

from robot_dashboard.saved_maps import NavigationMapSnapshot
from robot_dashboard.spatial_routes import SpatialRouteError, validate_route


MAX_CELLS = 100_000


def _cell(snapshot: NavigationMapSnapshot, point: tuple[float, float]) -> tuple[int, int] | None:
    x, y = point
    if not all(math.isfinite(value) for value in point):
        return None
    ox, oy, yaw = snapshot.origin
    dx, dy = x - ox, y - oy
    local_x = math.cos(yaw) * dx + math.sin(yaw) * dy
    local_y = -math.sin(yaw) * dx + math.cos(yaw) * dy
    cell = (math.floor(local_x / snapshot.resolution), math.floor(local_y / snapshot.resolution))
    return cell if 0 <= cell[0] < snapshot.width and 0 <= cell[1] < snapshot.height else None


def _center(snapshot: NavigationMapSnapshot, cell: tuple[int, int]) -> tuple[float, float]:
    local_x = (cell[0] + 0.5) * snapshot.resolution
    local_y = (cell[1] + 0.5) * snapshot.resolution
    ox, oy, yaw = snapshot.origin
    return (
        ox + math.cos(yaw) * local_x - math.sin(yaw) * local_y,
        oy + math.sin(yaw) * local_x + math.cos(yaw) * local_y,
    )


def probe_connectivity(
    snapshot: NavigationMapSnapshot,
    *,
    map_family: Mapping[str, str],
    annotations: Mapping[str, Any],
    start: tuple[float, float],
    goal: tuple[float, float],
    pose_age_s: float | None,
    max_pose_age_s: float,
    tf_authorities: Mapping[str, int],
    robot_radius_m: float,
) -> dict:
    """Check exact lineage, input validity, then conservative 4-neighbor reachability.

    ``max_pose_age_s`` and ``robot_radius_m`` are explicit experiment inputs,
    not changes to any runtime safety threshold.  Only a bounded synthetic or
    recorded snapshot may be passed by the caller.  No path is executable.
    """

    result = {
        "engine": "OFFLINE_GRID_CONNECTIVITY_NOT_NAV2",
        "actual_nav2_run": False,
        "map_id": snapshot.map_id,
        "map_revision": snapshot.revision,
        "reachable": False,
        "reason": None,
        "cell_count": 0,
        "path_cells": [],
    }

    def reject(reason: str) -> dict:
        result["reason"] = reason
        return result

    if snapshot.width * snapshot.height > MAX_CELLS:
        return reject("MAP_TOO_LARGE")
    expected = (
        map_family.get("family_id"), map_family.get("family_revision"),
        map_family.get("pcd_map_id"), map_family.get("pcd_revision"),
        map_family.get("occupancy_map_id"), map_family.get("occupancy_revision"),
    )
    actual = (
        snapshot.family_id, snapshot.family_revision,
        snapshot.source_pcd_id, snapshot.source_pcd_revision,
        snapshot.occupancy_map_id, snapshot.occupancy_map_revision,
    )
    if expected != actual or expected[-2:] != (snapshot.map_id, snapshot.revision):
        return reject("MAP_LINEAGE_MISMATCH")
    if annotations.get("map_id") != snapshot.map_id or annotations.get("map_revision") != snapshot.revision:
        return reject("ANNOTATION_MAP_REVISION_MISMATCH")
    if any(tf_authorities.get(edge) != 1 for edge in ("map_to_odom", "odom_to_base")):
        return reject("TF_MISSING_OR_CONFLICTING")
    if (
        pose_age_s is None or not math.isfinite(pose_age_s) or pose_age_s < 0
        or not math.isfinite(max_pose_age_s) or max_pose_age_s <= 0
        or pose_age_s > max_pose_age_s
    ):
        return reject("POSE_MISSING_OR_STALE")
    if not math.isfinite(robot_radius_m) or robot_radius_m <= 0:
        return reject("INVALID_FOOTPRINT")
    for label, point in (("START", start), ("GOAL", goal)):
        if len(point) != 2 or not all(math.isfinite(value) for value in point):
            return reject(f"{label}_INVALID")
        if _cell(snapshot, point) is None:
            return reject(f"{label}_OUTSIDE_MAP")
        if not snapshot.known_free(*point, clearance_radius=robot_radius_m):
            return reject(f"{label}_NOT_KNOWN_FREE")

    first = _cell(snapshot, start)
    last = _cell(snapshot, goal)
    assert first is not None and last is not None
    queue = [(0, first)]
    distance = {first: 0}
    previous = {}
    while queue:
        cost, cell = heapq.heappop(queue)
        if cost != distance[cell]:
            continue
        if cell == last:
            path = [cell]
            while path[-1] != first:
                path.append(previous[path[-1]])
            path.reverse()
            # Reuse E1's exact-map route check for polygon constraints.  An
            # E1 rejection remains diagnostic; this is not a Nav2 result.
            poses = [dict(zip(("x", "y"), _center(snapshot, item)), yaw=0.0) for item in path]
            route = {"map_family": map_family, "poses": poses, "policy": {"mode": "FLEXIBLE"}}
            try:
                e1 = validate_route(route, snapshot, annotations, robot_radius_m=robot_radius_m)
            except SpatialRouteError:
                return reject("E1_VALIDATION_FAILED")
            if not e1["valid"]:
                return reject("E1_CONSTRAINT_REJECTED")
            result.update(reachable=True, reason="CONNECTED", cell_count=len(path), path_cells=path)
            return result
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            neighbor = (cell[0] + dx, cell[1] + dy)
            if neighbor in distance or not (0 <= neighbor[0] < snapshot.width and 0 <= neighbor[1] < snapshot.height):
                continue
            if not snapshot.known_free(*_center(snapshot, neighbor), clearance_radius=robot_radius_m):
                continue
            distance[neighbor] = cost + 1
            previous[neighbor] = cell
            heapq.heappush(queue, (cost + 1, neighbor))
    return reject("NO_KNOWN_FREE_CONNECTION")
