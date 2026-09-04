"""Deterministic server-authoritative competition rehearsal state."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from .behaviors import DeliveryWorkflow, make_advisory_snapshot
from .mission_dry_run import DRY_RUN_SIDE_EFFECT_COUNTERS
from .replay import BASE_TIME_NS, SCENARIO_ROOT, load_scenario, replay_scenario


ALLOWED_SPEEDS = frozenset({0.5, 1.0, 2.0, 5.0})
MAX_REPORT_BYTES = 128 * 1024
MAX_ADVISORY_TRANSITIONS = 256
MAX_UINT64 = (1 << 64) - 1
BANNER = "REHEARSAL — VIRTUAL DATA — ROBOT WILL NOT MOVE"


class RehearsalError(ValueError):
    """A bounded rehearsal request or state error."""


def available_scenarios(root: Path = SCENARIO_ROOT) -> list[dict[str, Any]]:
    values = []
    for path in sorted(root.glob("*.json"))[:128]:
        scenario = load_scenario(path)
        values.append(
            {
                "scenario_id": scenario["scenario_id"],
                "description": scenario["description"],
                "event_count": len(scenario["events"]),
                "duration_ms": max(
                    1,
                    max((int(item["at_ms"]) for item in scenario["events"]), default=0),
                ),
            }
        )
    return values


def _route_legs(
    route: Mapping[str, Any],
) -> list[tuple[int, float, float, float, float, float]]:
    legs: list[tuple[int, float, float, float, float, float]] = []
    for segment_index, segment in enumerate(route.get("segments", [])[:512]):
        if not isinstance(segment, Mapping):
            continue
        points = segment.get("polyline", [])
        if not isinstance(points, list):
            continue
        for left, right in zip(points[:128], points[1:128]):
            if not isinstance(left, Mapping) or not isinstance(right, Mapping):
                continue
            try:
                x1, y1 = float(left["x"]), float(left["y"])
                x2, y2 = float(right["x"]), float(right["y"])
            except (KeyError, TypeError, ValueError):
                continue
            values = (x1, y1, x2, y2)
            if not all(
                math.isfinite(item) and abs(item) <= 1_000_000.0 for item in values
            ):
                continue
            length = math.hypot(x2 - x1, y2 - y1)
            if length > 0:
                legs.append((segment_index, x1, y1, x2, y2, length))
    return legs


def interpolate_virtual_pose(
    route: Mapping[str, Any], progress: float, *, off_route: bool = False
) -> dict[str, Any]:
    """Interpolate a labeled virtual pose by polyline distance."""

    if isinstance(progress, bool) or not isinstance(progress, (int, float)):
        raise RehearsalError("progress must be numeric")
    normalized = float(progress)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise RehearsalError("progress is outside the supported range")
    legs = _route_legs(route)
    if not legs:
        raise RehearsalError("selected route has no interpolable polyline")
    total = sum(item[5] for item in legs)
    target = normalized * total
    traversed = 0.0
    selected = legs[-1]
    local = 1.0
    for leg in legs:
        if target <= traversed + leg[5]:
            selected = leg
            local = (target - traversed) / leg[5]
            break
        traversed += leg[5]
    segment_index, x1, y1, x2, y2, _ = selected
    yaw = math.atan2(y2 - y1, x2 - x1)
    x = x1 + (x2 - x1) * local
    y = y1 + (y2 - y1) * local
    if off_route:
        x += -math.sin(yaw) * 2.0
        y += math.cos(yaw) * 2.0
    segment_count = max(1, len(route.get("segments", [])))
    segment_progress = min(1.0, max(0.0, normalized * segment_count - segment_index))
    return {
        "label": "VIRTUAL ROBOT",
        "source": "VIRTUAL_ROUTE_REPLAY",
        "frame_id": "map",
        "x": round(x, 6),
        "y": round(y, 6),
        "yaw": round(yaw, 6),
        "segment_index": segment_index,
        "segment_progress": round(segment_progress, 6),
        "off_route": off_route,
        "update_rate_hz": 10,
    }


def explain_recommendation(
    selected: Mapping[str, Any], alternatives: list[Mapping[str, Any]]
) -> dict[str, Any]:
    metrics = selected.get("metrics", {})
    if not isinstance(metrics, Mapping):
        metrics = {}
    keys = (
        "travel_time_s",
        "food_wait_s",
        "signal_wait_s",
        "distance_m",
        "risk_score",
        "crosswalk_count",
        "underpass_count",
        "turn_count",
        "special_behavior_count",
    )
    breakdown = {key: round(float(metrics.get(key, 0.0)), 3) for key in keys}
    comparisons = []
    for route in alternatives[:2]:
        candidate = route.get("metrics", {})
        if not isinstance(candidate, Mapping):
            continue
        comparisons.append(
            {
                "profile": str(route.get("profile", ""))[:16],
                "eta_delta_s": round(
                    float(candidate.get("eta_s", 0.0))
                    - float(metrics.get("eta_s", 0.0)),
                    3,
                ),
                "distance_delta_m": round(
                    float(candidate.get("distance_m", 0.0))
                    - float(metrics.get("distance_m", 0.0)),
                    3,
                ),
                "risk_delta": round(
                    float(candidate.get("risk_score", 0.0))
                    - float(metrics.get("risk_score", 0.0)),
                    3,
                ),
            }
        )
    profile = str(selected.get("profile", "BALANCED"))[:16]
    reason = (
        f"{profile}: ETA {float(metrics.get('eta_s', 0.0)):.1f}s, "
        f"distance {float(metrics.get('distance_m', 0.0)):.1f}m, "
        f"risk {float(metrics.get('risk_score', 0.0)):.1f}."
    )[:240]
    return {
        "template": "DETERMINISTIC_METRICS_V1",
        "reason": reason,
        "score_breakdown": breakdown,
        "alternatives": comparisons,
    }


class RehearsalSession:
    """One in-memory replay session. It owns no timers, sockets, or action ports."""

    def __init__(
        self,
        *,
        scenario_path: Path,
        route: Mapping[str, Any],
        alternatives: list[Mapping[str, Any]],
        order: Mapping[str, Any],
        mission_dry_run: Mapping[str, Any],
        now: Callable[[], float],
    ) -> None:
        self._scenario = load_scenario(scenario_path)
        self._route = copy.deepcopy(dict(route))
        self._order = copy.deepcopy(dict(order))
        self._mission_dry_run = copy.deepcopy(dict(mission_dry_run))
        self._now = now
        self._duration_ms = max(
            1,
            max(
                (int(item["at_ms"]) for item in self._scenario["events"]),
                default=0,
            ),
        )
        self._position_ms = 0
        self._applied_count = 0
        self._playback_state = "PAUSED"
        self._speed = 1.0
        self._last_clock_s = float(now())
        self._off_route = False
        self._advisory_transitions: list[dict[str, Any]] = []
        self._last_advisory_key: tuple[str, str, str] | None = None
        self._delivery_tick = 0
        self._delivery = DeliveryWorkflow(self._order)
        self._delivery.transition("START", now_ns=self._delivery_now_ns())
        self._explainability = explain_recommendation(route, alternatives)

    @property
    def route_revision(self) -> str:
        return str(self._route.get("revision", ""))

    def _delivery_now_ns(self) -> int:
        self._delivery_tick += 1
        value = BASE_TIME_NS + self._delivery_tick
        return min(MAX_UINT64, int(value))

    def _sync(self) -> None:
        current = float(self._now())
        if not math.isfinite(current):
            raise RehearsalError("server clock is invalid")
        if self._playback_state == "PLAYING":
            elapsed_ms = max(0.0, current - self._last_clock_s) * 1000.0 * self._speed
            self._position_ms = min(
                self._duration_ms, self._position_ms + int(elapsed_ms)
            )
            self._applied_count = sum(
                int(item["at_ms"]) <= self._position_ms
                for item in self._scenario["events"]
            )
            if self._position_ms >= self._duration_ms:
                self._playback_state = "COMPLETE"
        self._last_clock_s = current

    def _replay(self) -> dict[str, Any]:
        value = copy.deepcopy(self._scenario)
        value["events"] = value["events"][: self._applied_count]
        last_at = int(value["events"][-1]["at_ms"]) if value["events"] else 0
        effective_at = max(
            self._position_ms,
            max(
                (
                    int(event["at_ms"]) + int(event["payload"].get("advance_ms", 0))
                    for event in value["events"]
                    if event["kind"] == "TIME_ADVANCE"
                ),
                default=0,
            ),
        )
        if last_at < effective_at:
            value["events"].append(
                {
                    "at_ms": effective_at,
                    "kind": "TIME_ADVANCE",
                    "payload": {"advance_ms": 0},
                }
            )
        return cast(dict[str, Any], replay_scenario(value))

    def _advisory(self, replay: Mapping[str, Any]) -> dict[str, Any]:
        if self._off_route:
            return cast(
                dict[str, Any],
                make_advisory_snapshot(
                    behavior="NORMAL_GUIDANCE",
                    state="HOLD",
                    advisory="REPLAN_RECOMMENDED",
                    ready_for_manual_proceed=False,
                    autonomous_edge_ready=False,
                    reason_codes=["ROUTE_DEVIATION"],
                    requirements={"virtual_off_route": True},
                    updated_at_ns=BASE_TIME_NS + self._position_ms * 1_000_000,
                ),
            )
        return copy.deepcopy(dict(replay["advisory_behavior"]))

    def _record_advisory(self, advisory: Mapping[str, Any]) -> None:
        key = (
            str(advisory.get("behavior", "")),
            str(advisory.get("state", "")),
            str(advisory.get("advisory", "")),
        )
        if key == self._last_advisory_key:
            return
        self._last_advisory_key = key
        self._advisory_transitions.append(
            {
                "position_ms": self._position_ms,
                "behavior": key[0],
                "state": key[1],
                "advisory": key[2],
            }
        )
        self._advisory_transitions = self._advisory_transitions[
            -MAX_ADVISORY_TRANSITIONS:
        ]

    def _delivery_snapshot(self) -> dict[str, Any]:
        audit = self._delivery.audit()
        picked = {
            str(item.get("venue_id"))
            for item in audit
            if item.get("event") == "CONFIRM_PICKUP"
        }
        arrival_cursor = 0.0
        items = []
        lines = self._order.get("lines", [])
        for line in lines[:5] if isinstance(lines, list) else []:
            if not isinstance(line, Mapping):
                continue
            arrival_cursor += max(
                1.0, float(self._route.get("metrics", {}).get("travel_time_s", 0.0))
            ) / max(1, len(lines))
            ready = float(line.get("ready_at_s", 0.0))
            venue = str(line.get("restaurant_id", ""))[:32]
            items.append(
                {
                    "sequence": int(line.get("sequence", 0)),
                    "venue_id": venue,
                    "menu_id": str(line.get("menu_id", ""))[:32],
                    "quantity": int(line.get("quantity", 0)),
                    "estimated_ready_s": round(ready, 3),
                    "arrival_estimate_s": round(arrival_cursor, 3),
                    "wait_estimate_s": round(max(0.0, ready - arrival_cursor), 3),
                    "pickup_state": "CONFIRMED" if venue in picked else "PENDING",
                }
            )
        snapshot = self._delivery.snapshot(self._delivery_now_ns())
        return {
            "state": snapshot["state"],
            "advisory": snapshot["advisory"],
            "cargo_count": self._delivery.cargo_count,
            "cargo_capacity": 5,
            "next_venue_id": self._delivery.next_venue_id,
            "items": items,
            "destination_id": str(self._order.get("destination_id", ""))[:32],
            "destination_state": "COMPLETE"
            if snapshot["state"] == "ORDER_COMPLETE"
            else "PENDING",
            "audit": audit[-32:],
        }

    def control(self, action: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._sync()
        if action == "RESET":
            if payload:
                raise RehearsalError("reset payload must be empty")
            self._position_ms = 0
            self._applied_count = 0
            self._playback_state = "PAUSED"
            self._off_route = False
            self._advisory_transitions = []
            self._last_advisory_key = None
            self._delivery_tick = 0
            self._delivery = DeliveryWorkflow(self._order)
            self._delivery.transition("START", now_ns=self._delivery_now_ns())
        elif action == "PLAY":
            if payload:
                raise RehearsalError("play payload must be empty")
            if self._position_ms >= self._duration_ms:
                self._position_ms = 0
                self._applied_count = 0
            self._playback_state = "PLAYING"
        elif action == "PAUSE":
            if payload:
                raise RehearsalError("pause payload must be empty")
            self._playback_state = "PAUSED"
        elif action == "STEP":
            if payload:
                raise RehearsalError("step payload must be empty")
            self._playback_state = "PAUSED"
            if self._applied_count < len(self._scenario["events"]):
                event = self._scenario["events"][self._applied_count]
                self._applied_count += 1
                self._position_ms = int(event["at_ms"])
            else:
                self._position_ms = self._duration_ms
                self._playback_state = "COMPLETE"
        elif action == "SCRUB":
            if set(payload) != {"position_ms"}:
                raise RehearsalError("scrub payload is invalid")
            position = payload.get("position_ms")
            if isinstance(position, bool) or not isinstance(position, int):
                raise RehearsalError("scrub position must be an integer")
            self._position_ms = min(self._duration_ms, max(0, position))
            self._applied_count = sum(
                int(item["at_ms"]) <= self._position_ms
                for item in self._scenario["events"]
            )
            self._playback_state = "PAUSED"
        elif action == "SET_SPEED":
            if set(payload) != {"speed"}:
                raise RehearsalError("playback speed payload is invalid")
            speed = payload.get("speed")
            if isinstance(speed, bool) or not isinstance(speed, (int, float)):
                raise RehearsalError("playback speed is invalid")
            speed_value = float(speed)
            if speed_value not in ALLOWED_SPEEDS:
                raise RehearsalError("playback speed is not allowed")
            self._speed = speed_value
        elif action == "OFF_ROUTE":
            if set(payload) != {"enabled"} or not isinstance(
                payload.get("enabled"), bool
            ):
                raise RehearsalError("off-route injection payload is invalid")
            self._off_route = bool(payload["enabled"])
        elif action == "CONFIRM_PICKUP":
            venue = payload.get("venue_id")
            if set(payload) != {"venue_id"} or venue != self._delivery.next_venue_id:
                raise RehearsalError("pickup confirmation is out of sequence")
            for event, event_payload in (
                ("ARRIVE_PICKUP", {"venue_id": venue}),
                ("PICKUP_DOCKED", {}),
                ("CONFIRM_PICKUP", {"venue_id": venue}),
                ("DEPART_PICKUP", {}),
            ):
                self._delivery.transition(
                    event, now_ns=self._delivery_now_ns(), payload=event_payload
                )
        elif action == "CONFIRM_DROPOFF":
            destination = payload.get("destination_id")
            if (
                set(payload) != {"destination_id"}
                or destination != self._order.get("destination_id")
                or self._delivery.next_venue_id is not None
            ):
                raise RehearsalError("drop-off confirmation is invalid")
            for event, event_payload in (
                ("ARRIVE_DESTINATION", {"destination_id": destination}),
                ("DROPOFF_DOCKED", {}),
                ("CONFIRM_DROPOFF", {"destination_id": destination}),
            ):
                self._delivery.transition(
                    event, now_ns=self._delivery_now_ns(), payload=event_payload
                )
        else:
            raise RehearsalError("rehearsal action is unsupported")
        self._last_clock_s = float(self._now())
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        self._sync()
        replay = self._replay()
        progress = self._position_ms / self._duration_ms
        pose = interpolate_virtual_pose(
            self._route, progress, off_route=self._off_route
        )
        advisory = self._advisory(replay)
        self._record_advisory(advisory)
        segment_index = int(pose["segment_index"])
        return {
            "enabled": True,
            "active": True,
            "mode": "REHEARSAL",
            "banner": BANNER,
            "virtual_data_only": True,
            "scenario": {
                "scenario_id": self._scenario["scenario_id"],
                "description": self._scenario["description"],
            },
            "playback": {
                "state": self._playback_state,
                "speed": self._speed,
                "position_ms": self._position_ms,
                "duration_ms": self._duration_ms,
                "event_index": self._applied_count,
                "event_count": len(self._scenario["events"]),
            },
            "events": [
                {
                    "index": index,
                    "at_ms": int(event["at_ms"]),
                    "kind": str(event["kind"]),
                    "status": "APPLIED" if index < self._applied_count else "PENDING",
                }
                for index, event in enumerate(self._scenario["events"][:256])
            ],
            "expected_actual": copy.deepcopy(replay["expected_vs_actual"]),
            "virtual_robot": pose,
            "overlay": {
                "current_segment_index": segment_index,
                "current_segment_progress": pose["segment_progress"],
                "completed_segment_indices": list(range(segment_index)),
                "actual_nav2_path_status": "UNAVAILABLE_IN_REHEARSAL",
            },
            "advisory_behavior": advisory,
            "advisory_transitions": copy.deepcopy(self._advisory_transitions),
            "delivery": self._delivery_snapshot(),
            "explainability": copy.deepcopy(self._explainability),
            "mission_dry_run": copy.deepcopy(self._mission_dry_run),
            "restrictions": {
                "control_api_enabled": False,
                "navigation_start_enabled": False,
                "navigation_goal_enabled": False,
                "mission_create_enabled": False,
                "mission_start_enabled": False,
                "real_service_state_included": False,
            },
            "side_effect_count": 0,
            "side_effect_counters": dict(DRY_RUN_SIDE_EFFECT_COUNTERS),
            "report_available": True,
        }

    def report(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        report = {
            "schema_version": 1,
            "kind": "ROUTE_PLANNER_REHEARSAL_REPORT",
            "order_summary": {
                "label": str(self._order.get("label", ""))[:64],
                "destination_id": str(self._order.get("destination_id", ""))[:32],
                "total_quantity": int(self._order.get("total_quantity", 0)),
            },
            "selected_route": {
                "id": str(self._route.get("id", ""))[:32],
                "revision": self.route_revision,
                "profile": str(self._route.get("profile", ""))[:16],
                "metrics": copy.deepcopy(self._route.get("metrics", {})),
            },
            "scenario_timeline": snapshot["events"],
            "advisory_transitions": snapshot["advisory_transitions"],
            "cargo_events": snapshot["delivery"],
            "mission_dry_run": snapshot["mission_dry_run"],
            "side_effect_count": 0,
            "side_effect_counters": dict(DRY_RUN_SIDE_EFFECT_COUNTERS),
        }
        markdown = "\n".join(
            (
                "# Route Planner Rehearsal Report",
                "",
                f"- Mode: {BANNER}",
                f"- Order: {report['order_summary']['label']}",
                f"- Route: {report['selected_route']['profile']} ({report['selected_route']['id']})",
                f"- Scenario: {snapshot['scenario']['scenario_id']}",
                f"- Playback: {snapshot['playback']['state']} at {snapshot['playback']['position_ms']} ms",
                f"- Advisory: {snapshot['advisory_behavior']['behavior']} / {snapshot['advisory_behavior']['state']} / {snapshot['advisory_behavior']['advisory']}",
                f"- Cargo: {snapshot['delivery']['cargo_count']} / 5",
                f"- Mission dry-run eligible: {snapshot['mission_dry_run']['eligibility']}",
                "- Side effects: 0",
            )
        )
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")
        if (
            len(encoded) > MAX_REPORT_BYTES
            or len(markdown.encode("utf-8")) > MAX_REPORT_BYTES
        ):
            raise RehearsalError("rehearsal report exceeds its byte budget")
        return {"json": report, "markdown": markdown}


__all__ = [
    "ALLOWED_SPEEDS",
    "BANNER",
    "MAX_REPORT_BYTES",
    "RehearsalError",
    "RehearsalSession",
    "available_scenarios",
    "explain_recommendation",
    "interpolate_virtual_pose",
]
