"""Display-only schematic sessions. No robot, map, Mission or ROS ports exist here."""

from __future__ import annotations

import copy
import math
import re
from pathlib import Path

from .catalog import CATALOG_REVISION
from .optimizer import PROFILES, shortest_path, visit_orders
from .orders import normalize_order
from .schematic import (
    ASSET_ID,
    FRAME,
    SchematicError,
    digest,
    missing_field,
    template,
    validate_layout,
)
from .state_store import RoutePlannerStateStore, RoutePlannerStorageError

CONTEXTS = {"SAVED_OCCUPANCY", "DEMO", "FIELD"}
AUTHORITY = {"motion_authority": False, "control_authority": False}


def idle():
    return dict(
        active=False,
        state="IDLE",
        current_segment_index=0,
        progress_revision=0,
        completed_pickups=[],
        completed_dropoffs=[],
        cargo=0,
        operator_point=None,
    )


def bucket(usage):
    layout = template(usage)
    return dict(
        layout=layout,
        layout_revision=digest(layout),
        approval=None,
        order=None,
        start_node_id=None,
        recommendations=[],
        selected_route_id=None,
        guidance=idle(),
        state="IDLE",
    )


def relative_cost(edge, profile):
    length = sum(
        math.dist(a, b) for a, b in zip(edge["polyline_px"], edge["polyline_px"][1:])
    )
    penalty = {"FASTEST": 0, "BALANCED": 100, "SAFEST": 400}[profile]
    return length + (
        penalty
        if edge["type"] == "CROSSWALK"
        else 2 * penalty
        if edge["type"] == "UNDERPASS"
        else 0
    )


def recommend(value, usage):
    layout, order, start = value["layout"], value["order"], value["start_node_id"]
    if not order or not order["locked"]:
        raise SchematicError("주문서를 잠근 뒤 추천하세요", 409)
    if order["total_quantity"] > 5:
        raise SchematicError("적재 한도 5개 초과")
    if layout["rules_profile"] == "MANUAL_PREPARED_2_CONFIRMED":
        foods = {}
        for line in order["lines"]:
            key = (line["restaurant_id"], line["menu_id"])
            foods[key] = foods.get(key, 0) + line["quantity"]
        if max(foods.values()) > 2:
            raise SchematicError(
                "확인된 사전준비 규칙: 같은 음식은 2개까지; 추가 준비 시간은 미확인"
            )
    nodes = {n["id"]: n for n in layout["nodes"]}
    if start not in nodes or nodes[start]["role"] != "DESTINATION":
        raise SchematicError("4개 배달 장소 중 연결된 출발점을 명시적으로 선택하세요")
    restaurants = sorted({line["restaurant_id"] for line in order["lines"]})
    destinations = sorted({line["destination_id"] for line in order["lines"]})
    venues = {}
    for venue in restaurants + destinations:
        matches = [n["id"] for n in nodes.values() if n.get("venue_id") == venue]
        if len(matches) != 1:
            raise SchematicError(f"{venue}: 장소 연결은 정확히 한 개 필요합니다")
        venues[venue] = matches[0]
    adjacency = {n: [] for n in nodes}
    for e in layout["edges"]:
        if not e["enabled"]:
            continue
        adjacency[e["from"]].append((e["to"], e, False))
        if e["bidirectional"]:
            adjacency[e["to"]].append((e["from"], e, True))
    for neighbors in adjacency.values():
        neighbors.sort(key=lambda item: (item[1]["id"], item[0], item[2]))
    context = dict(
        map_kind="SCHEMATIC_MANUAL",
        usage=usage,
        asset_id=ASSET_ID,
        frame_id=FRAME,
        operation_mode="MANUAL_GUIDANCE",
        progress_source="MANUAL_STEP",
        layout_revision=value["layout_revision"],
        approval=value["approval"],
        order_revision=order["revision"],
        start_node_id=start,
        rules_profile=layout["rules_profile"],
        planner_revision=CATALOG_REVISION + ":schematic-1",
    )
    results = []
    for profile in PROFILES:
        candidates = []
        for pickups, dropoffs in visit_orders(restaurants, destinations):
            current, node_ids, segments, stops, cost = start, [start], [], [], 0.0
            for venue in pickups + dropoffs:
                for edge, reverse in shortest_path(
                    adjacency,
                    current,
                    venues[venue],
                    lambda e: relative_cost(e, profile),
                ):
                    target = edge["from"] if reverse else edge["to"]
                    segments.append(
                        dict(
                            index=len(segments),
                            edge_id=edge["id"],
                            type=edge["type"],
                            from_node_id=current,
                            to_node_id=target,
                            label=f'{nodes[current]["label"]} → {nodes[target]["label"]}',
                            polyline_px=list(reversed(edge["polyline_px"]))
                            if reverse
                            else edge["polyline_px"],
                            signal_state="UNKNOWN",
                            distance_m=None,
                            eta_s=None,
                        )
                    )
                    cost += relative_cost(edge, profile)
                    current = target
                    node_ids.append(current)
                stops.append(
                    dict(
                        venue_id=venue,
                        kind="PICKUP" if venue in pickups else "DROPOFF",
                        after_segment=len(segments),
                        label=nodes[current]["label"],
                    )
                )
            route = dict(
                context=context,
                profiles=[profile],
                node_ids=node_ids,
                segments=segments,
                stops=stops,
                relative_cost=round(cost, 3),
                cost_unit="RELATIVE_NOT_METRIC",
                distance_m=None,
                eta_s=None,
                **AUTHORITY,
            )
            route["revision"] = digest(route)
            route["id"] = "schematic-" + route["revision"][:32]
            candidates.append(route)
        winner = min(
            candidates, key=lambda r: (r["relative_cost"], tuple(r["node_ids"]))
        )
        duplicate = next(
            (r for r in results if r["node_ids"] == winner["node_ids"]), None
        )
        if duplicate:
            duplicate["profiles"].append(profile)
        else:
            results.append(winner)
    for route in results:
        route.pop("id")
        route.pop("revision")
        route["revision"] = digest(route)
        route["id"] = "schematic-" + route["revision"][:32]
    return results[:3]


class SchematicSession:
    """Call under the owning coordinator's lock; commit state only after durable save."""

    def __init__(self, root: Path):
        self.store = RoutePlannerStateStore(root / "schematic")
        self.state = self.store.load_document()
        if self.state is None:
            # New independent schema: no migration of SavedMap IDs or coordinates.
            self.state = dict(
                schema_version=1,
                revision=0,
                context="SAVED_OCCUPANCY",
                buckets={u: bucket(u) for u in ("DEMO", "FIELD")},
                events=[],
            )
        if (
            not isinstance(self.state, dict)
            or set(self.state)
            != {"schema_version", "revision", "context", "buckets", "events"}
            or self.state["schema_version"] != 1
        ):
            raise RoutePlannerStorageError(
                "unsupported schematic schema; never infer a migration"
            )
        if (
            self.state["context"] not in CONTEXTS
            or type(self.state["revision"]) is not int
            or self.state["revision"] < 0
            or not isinstance(self.state["events"], list)
            or len(self.state["events"]) > 128
            or set(self.state["buckets"]) != {"DEMO", "FIELD"}
        ):
            raise RoutePlannerStorageError("invalid schematic state")
        for b in self.state["buckets"].values():
            if not isinstance(b, dict) or set(b) != {
                "layout",
                "layout_revision",
                "approval",
                "order",
                "start_node_id",
                "recommendations",
                "selected_route_id",
                "guidance",
                "state",
            }:
                raise RoutePlannerStorageError("invalid schematic bucket")
            validate_layout(b["layout"])
            if digest(b["layout"]) != b["layout_revision"]:
                raise RoutePlannerStorageError("schematic layout revision mismatch")
            approval = b["approval"]
            if approval is not None and (
                not isinstance(approval, dict)
                or set(approval) != {"reviewer", "layout_revision", "revision"}
                or approval["layout_revision"] != b["layout_revision"]
                or not isinstance(approval["reviewer"], str)
                or not 1 <= len(approval["reviewer"].strip()) <= 64
                or missing_field(b["layout"])
            ):
                raise RoutePlannerStorageError("invalid schematic approval")
            if b["order"] is not None:
                old = b["order"]
                normalized = normalize_order(
                    dict(
                        label=old["label"],
                        orders=old["orders"],
                        locked=old["locked"],
                        order_started_at=old["order_started_at"],
                    ),
                    order_id=old["id"],
                )
                if normalized != old:
                    raise RoutePlannerStorageError("invalid schematic order")
            g = b["guidance"]
            if (
                not isinstance(g, dict)
                or set(g) != set(idle())
                or any(
                    type(g[k]) is not int or g[k] < 0
                    for k in ("current_segment_index", "progress_revision", "cargo")
                )
                or g["cargo"] > 5
            ):
                raise RoutePlannerStorageError("invalid schematic progress")
            for key, venues in (
                ("completed_pickups", {"DOMINO", "HANSOT", "EDIYA"}),
                (
                    "completed_dropoffs",
                    {"COEX", "WHIMOON", "GANGNAM_POLICE", "GTX_SITE"},
                ),
            ):
                if (
                    not isinstance(g[key], list)
                    or len(g[key]) != len(set(g[key]))
                    or set(g[key]) - venues
                ):
                    raise RoutePlannerStorageError("invalid schematic confirmations")
            # Persisted plans are historical only. Explicit recommendation/select/start
            # is required after restart; retained records never create live authority.
            b.update(recommendations=[], selected_route_id=None, state="STALE")
            b["guidance"].update(active=False, state="STALE", operator_point=None)
        self.state["revision"] += 1
        self.store.save(self.state)

    def snapshot(self):
        s = self.state
        result = dict(
            context=s["context"], revision=s["revision"], available=True, **AUTHORITY
        )
        if s["context"] != "SAVED_OCCUPANCY":
            b = copy.deepcopy(s["buckets"][s["context"]])
            result.update(
                b,
                usage=s["context"],
                map_kind="SCHEMATIC_MANUAL",
                operation_mode="MANUAL_GUIDANCE",
                progress_source="MANUAL_STEP",
                field_approved=s["context"] == "FIELD" and bool(b["approval"]),
                missing=missing_field(b["layout"]),
                distance_m=None,
                eta_s=None,
                live_pose_status="LIVE_POSE_NOT_CONFIGURED",
                signal_state="UNKNOWN",
                frame_id=FRAME,
            )
            result.update(
                food_readiness_state="UNKNOWN", legacy_order_timing_applicable=False
            )
        return result

    @staticmethod
    def invalidate(b):
        b.update(
            recommendations=[], selected_route_id=None, guidance=idle(), state="STALE"
        )

    def execute(self, action, expected_revision, context, data):
        if context not in CONTEXTS or not isinstance(data, dict):
            raise SchematicError("invalid schematic context/payload")
        allowed = {
            "CONTEXT": {"context"},
            "LAYOUT": {"layout"},
            "APPROVE": {"reviewer", "layout_revision"},
            "ORDER": {"order"},
            "UNLOCK": set(),
            "START_POINT": {"node_id"},
            "RECOMMEND": set(),
            "SELECT": {"route_id", "route_revision"},
            "START": {"route_id", "route_revision"},
            "END": set(),
            "STEP": {
                "event_id",
                "route_id",
                "route_revision",
                "expected_progress_revision",
                "expected_segment_index",
            },
            "PICKUP": {
                "event_id",
                "route_id",
                "route_revision",
                "expected_progress_revision",
                "expected_segment_index",
                "venue_id",
            },
            "DROPOFF": {
                "event_id",
                "route_id",
                "route_revision",
                "expected_progress_revision",
                "expected_segment_index",
                "venue_id",
            },
        }
        if action not in allowed or set(data) != allowed[action]:
            raise SchematicError("unknown/missing schematic command fields")
        fingerprint = digest([action, context, expected_revision, data])
        event_id = data.get("event_id")
        if action in {"STEP", "PICKUP", "DROPOFF"}:
            if not isinstance(event_id, str) or not re.fullmatch(
                r"[a-zA-Z0-9-]{8,64}", event_id
            ):
                raise SchematicError("invalid event id")
            prior = next((e for e in self.state["events"] if e["id"] == event_id), None)
            if prior:
                if prior["fingerprint"] != fingerprint:
                    raise SchematicError(
                        "event id reused with a different request", 409
                    )
                if prior.get("applied_revision") != self.state["revision"]:
                    raise SchematicError(
                        "event was already applied; refresh current state", 409
                    )
                return self.snapshot()
        if (
            type(expected_revision) is not int
            or expected_revision != self.state["revision"]
            or context != self.state["context"]
        ):
            raise SchematicError(
                "상태가 변경되었습니다. 새로 고친 뒤 다시 선택하세요", 409
            )
        s = copy.deepcopy(self.state)
        b = s["buckets"].get(context)
        if (
            b
            and b["guidance"]["active"]
            and action not in {"STEP", "PICKUP", "DROPOFF", "END"}
        ):
            raise SchematicError(
                "안내를 명시적으로 종료한 뒤 변경하세요 (로봇 정지 아님)", 409
            )
        if action == "CONTEXT":
            if data["context"] not in CONTEXTS:
                raise SchematicError("invalid map context")
            for item in s["buckets"].values():
                self.invalidate(item)
            s["context"] = data["context"]
        elif b is None:
            raise SchematicError("select a schematic context first", 409)
        elif action == "LAYOUT":
            b["layout"] = validate_layout(data["layout"])
            b.update(
                layout_revision=digest(b["layout"]), approval=None, start_node_id=None
            )
            self.invalidate(b)
        elif action == "APPROVE":
            reviewer = data["reviewer"]
            if (
                not isinstance(reviewer, str)
                or not 1 <= len(reviewer.strip()) <= 64
                or any(ord(c) < 32 for c in reviewer)
            ):
                raise SchematicError("확인자 이름을 직접 입력하세요")
            if context != "FIELD" or data["layout_revision"] != b["layout_revision"]:
                raise SchematicError("field layout revision mismatch", 409)
            missing = missing_field(b["layout"])
            if missing:
                raise SchematicError("미확인: " + "; ".join(missing))
            self.invalidate(b)
            b["approval"] = dict(
                reviewer=reviewer.strip(),
                layout_revision=b["layout_revision"],
                revision=s["revision"] + 1,
            )
        elif action == "ORDER":
            if b["order"] and b["order"]["locked"]:
                raise SchematicError("주문 잠금을 먼저 해제하세요", 409)
            b["order"] = normalize_order(
                data["order"], order_id=b["order"]["id"] if b["order"] else None
            )
            self.invalidate(b)
        elif action == "UNLOCK":
            if not b["order"]:
                raise SchematicError("order missing", 409)
            old = b["order"]
            b["order"] = normalize_order(
                dict(label=old["label"], orders=old["orders"], locked=False),
                order_id=old["id"],
            )
            self.invalidate(b)
        elif action == "START_POINT":
            if not any(
                n["id"] == data["node_id"] and n["role"] == "DESTINATION"
                for n in b["layout"]["nodes"]
            ):
                raise SchematicError("연결된 배달 장소 출발점이 필요합니다")
            b["start_node_id"] = data["node_id"]
            self.invalidate(b)
        elif action == "RECOMMEND":
            if context == "FIELD" and (
                not b["approval"]
                or b["approval"]["layout_revision"] != b["layout_revision"]
            ):
                raise SchematicError(
                    "FIELD 승인 필요: " + "; ".join(missing_field(b["layout"])), 409
                )
            b.update(
                recommendations=recommend(b, context),
                selected_route_id=None,
                guidance=idle(),
                state="RECOMMENDATIONS_READY",
            )
        elif action in {"SELECT", "START"}:
            route = next(
                (
                    r
                    for r in b["recommendations"]
                    if r["id"] == data["route_id"]
                    and r["revision"] == data["route_revision"]
                ),
                None,
            )
            if not route:
                raise SchematicError("route revision is stale", 409)
            if action == "START" and b["selected_route_id"] != route["id"]:
                raise SchematicError("select route first", 409)
            b.update(
                selected_route_id=route["id"], state="ROUTE_SELECTED", guidance=idle()
            )
            if action == "START":
                n = next(
                    n for n in b["layout"]["nodes"] if n["id"] == b["start_node_id"]
                )
                b["guidance"].update(
                    active=True,
                    state="WAIT_OPERATOR",
                    operator_point=[n["x_px"], n["y_px"]],
                )
        elif action == "END":
            b["guidance"].update(active=False, state="ENDED", operator_point=None)
        else:
            self._event(b, action, data)
        s["revision"] += 1
        if event_id:
            s["events"] = (
                s["events"]
                + [
                    dict(
                        id=event_id,
                        fingerprint=fingerprint,
                        applied_revision=s["revision"],
                    )
                ]
            )[-128:]
        self.store.save(s)
        self.state = s
        return self.snapshot()

    @staticmethod
    def _event(b, action, data):
        g = b["guidance"]
        route = next(
            (r for r in b["recommendations"] if r["id"] == b["selected_route_id"]), None
        )
        if (
            not g["active"]
            or not route
            or data["route_id"] != route["id"]
            or data["route_revision"] != route["revision"]
            or type(data["expected_progress_revision"]) is not int
            or data["expected_progress_revision"] != g["progress_revision"]
            or type(data["expected_segment_index"]) is not int
            or data["expected_segment_index"] != g["current_segment_index"]
        ):
            raise SchematicError("manual progress/route is stale", 409)

        def done(stop):
            return (
                stop["venue_id"]
                in g[
                    "completed_pickups"
                    if stop["kind"] == "PICKUP"
                    else "completed_dropoffs"
                ]
            )

        pending = [
            stop
            for stop in route["stops"]
            if stop["after_segment"] == g["current_segment_index"] and not done(stop)
        ]
        if action == "STEP":
            if pending:
                raise SchematicError("현재 장소의 픽업·배달을 별도로 확인하세요", 409)
            if g["current_segment_index"] >= len(route["segments"]):
                raise SchematicError("no next segment", 409)
            segment = route["segments"][g["current_segment_index"]]
            g["operator_point"] = segment["polyline_px"][-1]
            g["current_segment_index"] += 1
        else:
            stop = next(
                (
                    p
                    for p in pending
                    if p["venue_id"] == data["venue_id"] and p["kind"] == action
                ),
                None,
            )
            if not stop:
                raise SchematicError(
                    "해당 장소에 도착하지 않았거나 이미 확인했습니다", 409
                )
            lines = [
                line
                for line in b["order"]["lines"]
                if line["restaurant_id" if action == "PICKUP" else "destination_id"]
                == data["venue_id"]
            ]
            quantity = sum(line["quantity"] for line in lines)
            if action == "PICKUP":
                if g["cargo"] + quantity > 5:
                    raise SchematicError("cargo capacity exceeded")
                g["cargo"] += quantity
                g["completed_pickups"].append(data["venue_id"])
            else:
                if any(
                    line["restaurant_id"] not in g["completed_pickups"]
                    for line in lines
                ):
                    raise SchematicError("미수령 음식은 배달 확인할 수 없습니다", 409)
                g["cargo"] -= quantity
                g["completed_dropoffs"].append(data["venue_id"])
        g["progress_revision"] += 1
        if g["current_segment_index"] == len(route["segments"]) and all(
            done(stop) for stop in route["stops"]
        ):
            g.update(active=False, state="COMPLETE")
