"""Non-metric schematic authority. Never an occupancy map or robot command source."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

ASSETS = Path(__file__).resolve().parents[1] / "static/assets/competition/gangnam2026"
ASSET_ID = "gangnam-2026-schematic"
FRAME = "schematic_px"
VENUES = {
    "COEX": "ZONE1",
    "DOMINO": "ZONE1",
    "WHIMOON": "ZONE2",
    "HANSOT": "ZONE2",
    "GANGNAM_POLICE": "ZONE3",
    "EDIYA": "ZONE3",
    "GTX_SITE": "ZONE4",
}
CORNERS = {
    "A": [[14, 14], [233, 14], [233, 196], [201, 229], [14, 229]],
    "B": [[812, 14], [1027, 14], [1027, 229], [842, 229], [812, 196]],
    "C": [[844, 579], [1027, 579], [1027, 794], [812, 794], [812, 613]],
    "D": [[14, 579], [201, 579], [233, 613], [233, 794], [14, 794]],
}


class SchematicError(ValueError):
    def __init__(self, detail: str, status: int = 422):
        super().__init__(detail)
        self.status = status


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def number(value, low, high):
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise SchematicError("coordinate/value is outside the supported range")
    return float(value)


def point(value):
    if not isinstance(value, list) or len(value) != 2:
        raise SchematicError("point must contain x_px, y_px")
    return [number(value[0], 0, 1135), number(value[1], 0, 812)]


def rect(x1, y1, x2, y2):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def inside(p, polygon):
    x, y = p
    result = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        cross = (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0])
        if (
            abs(cross) < 1e-7
            and min(a[0], b[0]) - 1e-7 <= x <= max(a[0], b[0]) + 1e-7
            and min(a[1], b[1]) - 1e-7 <= y <= max(a[1], b[1]) + 1e-7
        ):
            return True
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (
            b[1] - a[1]
        ) + a[0]:
            result = not result
    return result


def segment_covered(a, b, polygons):
    # Split at every polygon boundary, then test every open interval. Endpoint
    # checks or coarse sampling would miss diagonals through the central road.
    cuts = {0.0, 1.0}
    dx, dy = b[0] - a[0], b[1] - a[1]
    for poly in polygons:
        for c, d in zip(poly, poly[1:] + poly[:1]):
            ex, ey = d[0] - c[0], d[1] - c[1]
            denominator = dx * ey - dy * ex
            if abs(denominator) < 1e-12:
                continue
            t = ((c[0] - a[0]) * ey - (c[1] - a[1]) * ex) / denominator
            u = ((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) / denominator
            if 0 <= t <= 1 and 0 <= u <= 1:
                cuts.add(t)
    times = sorted(cuts)
    return all(any(inside(p, poly) for poly in polygons) for p in [a, b]) and all(
        any(
            inside(
                [a[0] + dx * (left + right) / 2, a[1] + dy * (left + right) / 2], poly
            )
            for poly in polygons
        )
        for left, right in zip(times, times[1:])
    )


def corridors(kind):
    result = list(CORNERS.values())
    if kind == "CROSSWALK":
        result += [
            rect(220, 122, 825, 179),
            rect(860, 216, 915, 596),
            rect(220, 631, 825, 688),
            rect(128, 216, 184, 596),
        ]
    if kind == "UNDERPASS":
        result += [
            rect(890, 130, 1095, 165),
            rect(1060, 146, 1095, 666),
            rect(890, 650, 1095, 682),
        ]
    return result


def template(usage):
    raw = json.loads((ASSETS / "schematic_template.json").read_text())
    nodes = [
        {k: n[k] for k in ("id", "label", "x_px", "y_px", "role")}
        | ({"venue_id": n["venue_id"]} if "venue_id" in n else {})
        for n in raw["nodes"]
    ]
    edges = [
        {
            k: e[k]
            for k in (
                "id",
                "from",
                "to",
                "type",
                "bidirectional",
                "enabled",
                "polyline_px",
            )
        }
        for e in raw["edges"]
    ]
    field = json.loads((ASSETS / "field_binding_template.json").read_text())
    bindings = [
        {
            k: v[k]
            for k in (
                "venue_id",
                "corner",
                "approach_point_px",
                "dock_point_px",
                "dock_yaw_rad",
            )
        }
        for v in field["venue_bindings"]
    ]
    if usage == "DEMO":
        for binding in bindings:
            v = next(v for v in raw["venues"] if v["id"] == binding["venue_id"])
            n = next(n for n in nodes if n["id"] == v["id"])
            binding.update(
                corner=v["demo_corner"],
                approach_point_px=[n["x_px"], n["y_px"]],
                dock_point_px=[n["x_px"], n["y_px"]],
            )
    else:
        nodes = [n for n in nodes if "venue_id" not in n]
        edges = [e for e in edges if not e["id"].startswith("ACCESS_")]
    return validate_layout(
        {
            "nodes": nodes,
            "edges": edges,
            "corner_zones": raw["demo_corner_zone_binding"]
            if usage == "DEMO"
            else {c: None for c in CORNERS},
            "bindings": bindings,
            "rules_profile": "UNCONFIRMED",
            "static_reference_allowed": False,
            "underpass_verified": False,
        }
    )


def validate_layout(value):
    expected = {
        "nodes",
        "edges",
        "corner_zones",
        "bindings",
        "rules_profile",
        "static_reference_allowed",
        "underpass_verified",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise SchematicError(
            "schematic layout has unknown/missing fields; approval is server-owned"
        )
    if len(json.dumps(value, allow_nan=False)) > 1024 * 1024:
        raise SchematicError("layout exceeds 1MiB")
    value = copy.deepcopy(value)
    nodes, edges = value["nodes"], value["edges"]
    if (
        not isinstance(nodes, list)
        or not 4 <= len(nodes) <= 128
        or not isinstance(edges, list)
        or not 1 <= len(edges) <= 512
    ):
        raise SchematicError("node/edge count invalid")
    index = {}
    venue_ids = set()
    for n in nodes:
        if (
            not isinstance(n, dict)
            or set(n) - {"id", "label", "x_px", "y_px", "role", "venue_id"}
            or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", str(n.get("id", "")))
            or n["id"] in index
        ):
            raise SchematicError("invalid or duplicate node")
        if (
            n.get("role") not in {"INTERSECTION", "RESTAURANT", "DESTINATION", "START"}
            or not isinstance(n.get("label"), str)
            or not 1 <= len(n["label"]) <= 64
        ):
            raise SchematicError("invalid node role/label")
        point([n.get("x_px"), n.get("y_px")])
        if not any(inside([n["x_px"], n["y_px"]], p) for p in CORNERS.values()):
            raise SchematicError("node outside pedestrian corner")
        if n.get("venue_id") is not None and n["venue_id"] not in VENUES:
            raise SchematicError("unknown venue")
        if n.get("venue_id") is not None:
            venue = n["venue_id"]
            if venue in venue_ids or n["role"] != (
                "RESTAURANT"
                if venue in {"DOMINO", "HANSOT", "EDIYA"}
                else "DESTINATION"
            ):
                raise SchematicError("venue role mismatch or duplicate venue")
            venue_ids.add(venue)
        elif n["role"] in {"RESTAURANT", "DESTINATION"}:
            raise SchematicError("venue node must identify a catalog venue")
        index[n["id"]] = n
    ids = set()
    total = 0
    adjacency = {n: set() for n in index}
    for e in edges:
        if (
            not isinstance(e, dict)
            or set(e)
            != {"id", "from", "to", "type", "bidirectional", "enabled", "polyline_px"}
            or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", str(e.get("id", "")))
            or e["id"] in ids
        ):
            raise SchematicError("invalid or duplicate edge")
        ids.add(e["id"])
        if (
            e["from"] not in index
            or e["to"] not in index
            or e["from"] == e["to"]
            or e["type"] not in {"WALKWAY", "CROSSWALK", "UNDERPASS"}
            or type(e["enabled"]) is not bool
            or type(e["bidirectional"]) is not bool
        ):
            raise SchematicError("invalid edge endpoints/type")
        poly = e["polyline_px"]
        if not isinstance(poly, list) or not 2 <= len(poly) <= 128:
            raise SchematicError("polyline bounds invalid")
        total += len(poly)
        if total > 4096:
            raise SchematicError("total polyline limit")
        for p in poly:
            point(p)
        for key, p in (("from", poly[0]), ("to", poly[-1])):
            n = index[e[key]]
            if p != [n["x_px"], n["y_px"]]:
                raise SchematicError("polyline does not meet its node")
        if not all(
            segment_covered(a, b, corridors(e["type"])) for a, b in zip(poly, poly[1:])
        ):
            raise SchematicError("polyline crosses road/outside semantic corridor")
        if e["enabled"]:
            if e["type"] == "UNDERPASS" and value["underpass_verified"] is not True:
                raise SchematicError("underpass requires explicit field verification")
            adjacency[e["from"]].add(e["to"])
            if e["bidirectional"]:
                adjacency[e["to"]].add(e["from"])
    # Require a strongly connected enabled graph; closures may not silently
    # strand a venue or make a return journey impossible.
    for start in index:
        seen = set()
        pending = [start]
        while pending:
            n = pending.pop()
            if n not in seen:
                seen.add(n)
                pending.extend(adjacency[n] - seen)
        if len(seen) != len(index):
            raise SchematicError("GRAPH_DISCONNECTED")
    zones = value["corner_zones"]
    if (
        not isinstance(zones, dict)
        or set(zones) != set(CORNERS)
        or any(
            z not in {None, "ZONE1", "ZONE2", "ZONE3", "ZONE4"} for z in zones.values()
        )
    ):
        raise SchematicError("corner-zone binding invalid")
    assigned = [z for z in zones.values() if z is not None]
    if len(assigned) != len(set(assigned)):
        raise SchematicError("duplicate zone binding")
    if (
        not isinstance(value["bindings"], list)
        or len(value["bindings"]) != 7
        or {b.get("venue_id") for b in value["bindings"] if isinstance(b, dict)}
        != set(VENUES)
    ):
        raise SchematicError("exactly seven distinct venue bindings required")
    for b in value["bindings"]:
        if set(b) != {
            "venue_id",
            "corner",
            "approach_point_px",
            "dock_point_px",
            "dock_yaw_rad",
        } or b["corner"] not in {*CORNERS, None}:
            raise SchematicError("venue binding invalid")
        for key in ("approach_point_px", "dock_point_px"):
            if b[key] is not None:
                p = point(b[key])
                if b["corner"] is None or not inside(p, CORNERS[b["corner"]]):
                    raise SchematicError("venue point outside assigned corner")
        if b["dock_yaw_rad"] is not None:
            number(b["dock_yaw_rad"], -math.pi, math.pi)
    if (
        value["rules_profile"] not in {"UNCONFIRMED", "MANUAL_PREPARED_2_CONFIRMED"}
        or type(value["static_reference_allowed"]) is not bool
        or type(value["underpass_verified"]) is not bool
    ):
        raise SchematicError("rules/confirmation invalid")
    return value


def missing_field(layout):
    missing = [
        f"corner {c}: zone" for c, z in layout["corner_zones"].items() if z is None
    ]
    if layout["rules_profile"] != "MANUAL_PREPARED_2_CONFIRMED":
        missing.append("manual rules profile confirmation")
    if not layout["static_reference_allowed"]:
        missing.append("organizer static-reference permission")
    for b in layout["bindings"]:
        name = b["venue_id"]
        for key in ("corner", "approach_point_px", "dock_point_px", "dock_yaw_rad"):
            if b[key] is None:
                missing.append(f"{name}: {key}")
        if b["corner"] and layout["corner_zones"][b["corner"]] != VENUES[name]:
            missing.append(f"{name}: official zone mismatch")
        matches = [n for n in layout["nodes"] if n.get("venue_id") == name]
        if (
            len(matches) != 1
            or [matches[0]["x_px"], matches[0]["y_px"]] != b["dock_point_px"]
        ):
            missing.append(f"{name}: unique connected dock node")
        approaches = [
            n
            for n in layout["nodes"]
            if [n["x_px"], n["y_px"]] == b["approach_point_px"]
        ]
        if not approaches:
            missing.append(f"{name}: connected approach node")
    return missing
