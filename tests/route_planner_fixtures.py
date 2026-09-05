from __future__ import annotations

import math

from robot_dashboard.map_annotations import annotation_revision


MAP_ID = "a" * 24
MAP_REVISION = "b" * 64


POINTS = [
    {"id": "1" * 24, "type": "HOME", "name": "Start", "pose": {"x": 0.0, "y": 0.0, "yaw": 0.0}},
    {"id": "2" * 24, "type": "DOCK", "name": "Hansot", "pose": {"x": 1.0, "y": 0.0, "yaw": 0.0}},
    {"id": "3" * 24, "type": "DOCK", "name": "Ediya", "pose": {"x": 2.0, "y": 0.0, "yaw": 0.0}},
    {"id": "4" * 24, "type": "DOCK", "name": "Coex", "pose": {"x": 3.0, "y": 0.0, "yaw": 0.0}},
    {"id": "5" * 24, "type": "POI", "name": "Safe", "pose": {"x": 1.5, "y": 1.0, "yaw": 0.0}},
]
ANNOTATION_REVISION = annotation_revision(map_id=MAP_ID, map_revision=MAP_REVISION, points=POINTS, polygons=[])


def annotations():
    return {
        "schema_version": 1,
        "map_id": MAP_ID,
        "map_revision": MAP_REVISION,
        "annotation_revision": ANNOTATION_REVISION,
        "revision": ANNOTATION_REVISION,
        "points": [dict(item) for item in POINTS],
        "polygons": [],
    }


class Geometry:
    map_id = MAP_ID
    revision = MAP_REVISION
    resolution = 0.05

    def contains(self, x, y):
        return -1 <= x <= 5 and -1 <= y <= 3

    def known_free(self, x, y, *, clearance_radius):
        del clearance_radius
        return self.contains(x, y)


def node(identifier, annotation_id, role, venue_id=None):
    return {
        "id": identifier,
        "annotation_id": annotation_id,
        "role": role,
        "zone_id": None,
        "venue_id": venue_id,
        "label": identifier.replace("_", " ").title(),
        "manual_guidance": True,
        "autonomous_eligible": True,
    }


def edge(identifier, source, target, points, *, risk=1.0, kind="NORMAL_WALKWAY", requirements=None, wait=0.0):
    distance = sum(math.hypot(right[0] - left[0], right[1] - left[1]) for left, right in zip(points, points[1:]))
    return {
        "id": identifier,
        "from": source,
        "to": target,
        "type": kind,
        "bidirectional": True,
        "polyline": [{"x": x, "y": y} for x, y in points],
        "distance_m": distance,
        "nominal_speed_mps": 0.2,
        "risk": risk,
        "requirements": list(requirements or []),
        "allow_manual": True,
        "allow_autonomous": True,
        "allow_replan": True,
        "allow_turning": True,
        "allow_lateral_motion": False,
        "speed_limit_mps": 0.2,
        "expected_wait_s": wait,
        "penalty_risk": 0.0,
    }


def graph_payload():
    return {
        "schema_version": 1,
        "map_id": MAP_ID,
        "map_revision": MAP_REVISION,
        "annotation_revision": ANNOTATION_REVISION,
        "nodes": [
            node("START_NODE", "1" * 24, "START"),
            node("HANSOT_DOCK", "2" * 24, "RESTAURANT_DOCK", "HANSOT"),
            node("EDIYA_DOCK", "3" * 24, "RESTAURANT_DOCK", "EDIYA"),
            node("COEX_DOCK", "4" * 24, "DESTINATION_DOCK", "COEX"),
            node("SAFE_HOLD", "5" * 24, "SAFE_HOLD"),
        ],
        "edges": [
            edge("START_TO_HANSOT", "START_NODE", "HANSOT_DOCK", [(0, 0), (1, 0)], risk=7),
            edge("HANSOT_TO_EDIYA", "HANSOT_DOCK", "EDIYA_DOCK", [(1, 0), (2, 0)], kind="CROSSWALK", requirements=["TRAFFIC_GREEN", "PEDESTRIAN_CLEAR"], wait=5),
            edge("EDIYA_TO_COEX", "EDIYA_DOCK", "COEX_DOCK", [(2, 0), (3, 0)], risk=7),
            edge("START_TO_SAFE", "START_NODE", "SAFE_HOLD", [(0, 0), (1.5, 1.0)], risk=0.1),
            edge("SAFE_TO_HANSOT", "SAFE_HOLD", "HANSOT_DOCK", [(1.5, 1.0), (1, 0)], risk=0.1, kind="UNDERPASS", requirements=["SPECIAL_GAIT"]),
            edge("SAFE_TO_EDIYA", "SAFE_HOLD", "EDIYA_DOCK", [(1.5, 1.0), (2, 0)], risk=0.1),
            edge("SAFE_TO_COEX", "SAFE_HOLD", "COEX_DOCK", [(1.5, 1.0), (3, 0)], risk=0.1),
        ],
    }


def order_payload():
    return {
        "label": "예선 주문 1",
        "destination_id": "COEX",
        "lines": [
            {"sequence": 1, "restaurant_id": "HANSOT", "menu_id": "CHICKEN_MAYO", "quantity": 2},
            {"sequence": 2, "restaurant_id": "EDIYA", "menu_id": "AMERICANO", "quantity": 1},
        ],
        "order_started_at": None,
        "locked": False,
    }


def ready_perception(now_ns=1_000_000_000):
    return {
        "schema_version": 1,
        "source": "mock-team",
        "frame_id": "base_link",
        "observed_at_ns": now_ns,
        "sequence": 1,
        "state": "READY",
        "confidence": 0.95,
        "traffic": [{"crosswalk_id": "NORTH", "signal": "GREEN"}],
        "crosswalks": [{"crosswalk_id": "NORTH", "visible": True, "lateral_offset_m": 0.02, "heading_error_rad": 0.01, "left_boundary_distance_m": 0.2, "right_boundary_distance_m": 0.2}],
        "people": [{"crosswalk_id": "NORTH", "occupancy": "CLEAR"}],
        "aruco": [{"venue_id": "HANSOT", "docking_ready": True}],
        "underpass_blocked": False,
    }
