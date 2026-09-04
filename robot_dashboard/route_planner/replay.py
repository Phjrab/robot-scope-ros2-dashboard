"""Deterministic, fixture-only Route Planner competition replay.

This module is advisory-only.  It has no HTTP, ROS, socket, service, mission, or
control adapter and records the absence of those effects in every result.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping

from .behaviors import AdvisoryBehaviorCoordinator
from .clock import VirtualClockError, VirtualMonotonicClock
from .graph import RouteGraphError, normalize_graph
from .guidance import project_guidance
from .optimizer import RoutePlanningError, recommend_routes
from .orders import OrderValidationError, normalize_order
from .perception import (
    MockRoutePerceptionProvider,
    PerceptionContractError,
    requirement_states,
)


BASE_TIME_NS = 10_000_000_000
MAX_SCENARIO_BYTES = 256 * 1024
MAX_SCENARIO_EVENTS = 256
MAX_SCENARIO_TIME_MS = 3_600_000
SCENARIO_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_EVENT_KINDS = frozenset(
    {
        "POSE",
        "PERCEPTION",
        "ORDER_STATUS",
        "PICKUP_CONFIRM",
        "DROPOFF_CONFIRM",
        "TIME_ADVANCE",
        "SERVER_RESTART",
        "MAP_REVISION_CHANGE",
        "GRAPH_REVISION_CHANGE",
    }
)
FORBIDDEN_CONTROL_EVENT_KINDS = frozenset(
    {
        "CMD_VEL",
        "ARM",
        "DEADMAN",
        "LEASE",
        "SPORT_REQUEST",
        "NAVIGATION_GOAL",
        "MISSION_START",
    }
)
PUBLIC_PROJECTION_KEYS = (
    "selected_route_profile",
    "next_instruction",
    "special_edge_readiness",
    "manual_warning",
    "autonomous_eligibility",
    "stale_or_invalid",
    "no_side_effects",
)
SIDE_EFFECT_COUNTERS = {
    "control_manager_calls": 0,
    "navigation_coordinator_calls": 0,
    "navigation_ros_gateway_calls": 0,
    "mission_start_calls": 0,
    "http_calls": 0,
    "ros_calls": 0,
    "socket_calls": 0,
    "service_calls": 0,
    "motion_commands": 0,
}
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_ROOT = _REPOSITORY_ROOT / "tests" / "fixtures" / "route_planner" / "scenarios"
GRAPH_FIXTURE_ROOT = (
    _REPOSITORY_ROOT / "tests" / "fixtures" / "route_planner" / "graphs"
)


class ScenarioReplayError(ValueError):
    """A bounded fixture or replay contract error."""


def _reject_json_constant(value: str) -> None:
    raise ScenarioReplayError(f"non-finite JSON number is forbidden: {value}")


def _read_fixture(path: Path, *, allowed_root: Path) -> Any:
    root = allowed_root.resolve()
    requested = path if path.is_absolute() else _REPOSITORY_ROOT / path
    if requested.is_symlink():
        raise ScenarioReplayError("fixture symlinks are forbidden")
    resolved = requested.resolve()
    if (
        resolved.suffix != ".json"
        or root not in resolved.parents
        or not resolved.is_file()
    ):
        raise ScenarioReplayError("fixture path is outside the allowed root")
    size = resolved.stat().st_size
    if size <= 0 or size > MAX_SCENARIO_BYTES:
        raise ScenarioReplayError("fixture size is outside the allowed range")
    try:
        return json.loads(
            resolved.read_text(encoding="utf-8"), parse_constant=_reject_json_constant
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScenarioReplayError("fixture is not valid UTF-8 JSON") from exc


def _exact(value: object, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ScenarioReplayError(f"{label} schema is invalid")
    return value


def _integer(value: object, label: str, low: int, high: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not low <= value <= high
    ):
        raise ScenarioReplayError(f"{label} is invalid")
    return value


def _number(value: object, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioReplayError(f"{label} is invalid")
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise ScenarioReplayError(f"{label} is invalid")
    return result


def _validate_event(event: object, *, prior_at_ms: int) -> dict[str, Any]:
    value = _exact(event, {"at_ms", "kind", "payload"}, "scenario event")
    at_ms = _integer(value["at_ms"], "event at_ms", 0, MAX_SCENARIO_TIME_MS)
    if at_ms < prior_at_ms:
        raise ScenarioReplayError(
            "scenario events must be ordered by non-decreasing at_ms"
        )
    kind = value["kind"]
    if kind in FORBIDDEN_CONTROL_EVENT_KINDS:
        raise ScenarioReplayError(f"control event kind is forbidden: {kind}")
    if kind not in ALLOWED_EVENT_KINDS:
        raise ScenarioReplayError("scenario event kind is unsupported")
    payload = value["payload"]
    if not isinstance(payload, Mapping):
        raise ScenarioReplayError("scenario event payload must be an object")
    if kind == "POSE":
        pose = _exact(payload, {"x", "y", "yaw"}, "pose event")
        for field in ("x", "y"):
            _number(pose[field], f"pose {field}", -1_000_000.0, 1_000_000.0)
        _number(pose["yaw"], "pose yaw", -math.pi, math.pi)
    elif kind == "PERCEPTION":
        if len(payload) > 12:
            raise ScenarioReplayError("perception event payload is oversized")
    elif kind == "ORDER_STATUS":
        status = _exact(payload, {"status"}, "order status event").get("status")
        if status not in {"VALIDATED", "LOCKED", "CANCELLED"}:
            raise ScenarioReplayError("order status is invalid")
    elif kind == "PICKUP_CONFIRM":
        venue_id = _exact(payload, {"venue_id"}, "pickup event").get("venue_id")
        if not isinstance(venue_id, str) or not re.fullmatch(
            r"^[A-Z][A-Z0-9_]{0,63}$", venue_id
        ):
            raise ScenarioReplayError("pickup venue_id is invalid")
    elif kind == "DROPOFF_CONFIRM":
        _exact(payload, set(), "dropoff event")
    elif kind == "TIME_ADVANCE":
        advance = _exact(payload, {"advance_ms"}, "time advance event").get(
            "advance_ms"
        )
        _integer(advance, "time advance", 0, MAX_SCENARIO_TIME_MS)
    elif kind == "SERVER_RESTART":
        _exact(payload, set(), "server restart event")
    else:
        revision = _exact(payload, {"revision"}, "revision event").get("revision")
        if not isinstance(revision, str) or not HEX64_RE.fullmatch(revision):
            raise ScenarioReplayError("revision event value is invalid")
    return {"at_ms": at_ms, "kind": kind, "payload": copy.deepcopy(dict(payload))}


def normalize_scenario(value: object) -> dict[str, Any]:
    scenario = _exact(
        value,
        {
            "schema_version",
            "scenario_id",
            "description",
            "order",
            "graph_fixture",
            "start_node",
            "events",
            "expected",
        },
        "scenario",
    )
    if scenario.get("schema_version") != 1:
        raise ScenarioReplayError("scenario schema version is unsupported")
    scenario_id = scenario.get("scenario_id")
    description = scenario.get("description")
    if not isinstance(scenario_id, str) or not SCENARIO_ID_RE.fullmatch(scenario_id):
        raise ScenarioReplayError("scenario_id is invalid")
    if not isinstance(description, str) or not 1 <= len(description) <= 240:
        raise ScenarioReplayError("scenario description is invalid")
    if (
        scenario.get("graph_fixture") != "competition-small-v1"
        or scenario.get("start_node") != "ZONE4_START"
    ):
        raise ScenarioReplayError(
            "scenario graph fixture or start node is not allowlisted"
        )
    if not isinstance(scenario.get("order"), Mapping):
        raise ScenarioReplayError("scenario order must be an object")
    raw_events = scenario.get("events")
    if not isinstance(raw_events, list) or len(raw_events) > MAX_SCENARIO_EVENTS:
        raise ScenarioReplayError("scenario event count is invalid")
    events = []
    prior = 0
    for event in raw_events:
        normalized = _validate_event(event, prior_at_ms=prior)
        prior = normalized["at_ms"]
        events.append(normalized)
    expected = _exact(
        scenario.get("expected"),
        set(PUBLIC_PROJECTION_KEYS),
        "scenario expected projection",
    )
    if expected.get("selected_route_profile") not in {
        None,
        "BALANCED",
        "FASTEST",
        "SAFEST",
    }:
        raise ScenarioReplayError("expected route profile is invalid")
    if not isinstance(expected.get("next_instruction"), str) or not re.fullmatch(
        r"^[A-Z][A-Z0-9_]{0,63}$", expected["next_instruction"]
    ):
        raise ScenarioReplayError("expected instruction is invalid")
    if expected.get("special_edge_readiness") not in {
        "READY",
        "BLOCKED",
        "UNKNOWN",
        "OPERATOR_REQUIRED",
        "NOT_APPLICABLE",
    }:
        raise ScenarioReplayError("expected special edge readiness is invalid")
    manual_warning = expected.get("manual_warning")
    if manual_warning is not None and (
        not isinstance(manual_warning, str)
        or not re.fullmatch(r"^[A-Z][A-Z0-9_]{0,63}$", manual_warning)
    ):
        raise ScenarioReplayError("expected manual warning is invalid")
    if not isinstance(expected.get("autonomous_eligibility"), bool):
        raise ScenarioReplayError("expected autonomous eligibility is invalid")
    if expected.get("stale_or_invalid") not in {
        "FRESH",
        "STALE",
        "INVALID_ORDER",
        "INVALID_PERCEPTION",
        "REVISION_CHANGED",
        "RESTARTED",
    }:
        raise ScenarioReplayError("expected stale or invalid state is invalid")
    if expected.get("no_side_effects") is not True:
        raise ScenarioReplayError("scenario must expect no side effects")
    return {
        "schema_version": 1,
        "scenario_id": scenario_id,
        "description": description,
        "order": copy.deepcopy(dict(scenario["order"])),
        "graph_fixture": "competition-small-v1",
        "start_node": "ZONE4_START",
        "events": events,
        "expected": {
            key: copy.deepcopy(expected[key]) for key in PUBLIC_PROJECTION_KEYS
        },
    }


def load_scenario(path: str | Path) -> dict[str, Any]:
    value = normalize_scenario(_read_fixture(Path(path), allowed_root=SCENARIO_ROOT))
    if Path(path).stem != value["scenario_id"]:
        raise ScenarioReplayError("scenario_id must match its fixture filename")
    return value


def _load_graph_fixture(identifier: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if identifier != "competition-small-v1":
        raise ScenarioReplayError("graph fixture is not allowlisted")
    value = _read_fixture(
        GRAPH_FIXTURE_ROOT / f"{identifier}.json", allowed_root=GRAPH_FIXTURE_ROOT
    )
    fixture = _exact(
        value, {"schema_version", "fixture_id", "annotations", "graph"}, "graph fixture"
    )
    if fixture.get("schema_version") != 1 or fixture.get("fixture_id") != identifier:
        raise ScenarioReplayError("graph fixture identity is invalid")
    try:
        graph = normalize_graph(fixture["graph"], annotations=fixture["annotations"])
    except RouteGraphError as exc:
        raise ScenarioReplayError("graph fixture contract is invalid") from exc
    return graph, copy.deepcopy(dict(fixture["annotations"]))


def _select_balanced(routes: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (route for route in routes if "BALANCED" in route.get("profiles", [])),
        routes[0] if routes else None,
    )


def _special_state(guidance: Mapping[str, Any], perception: Mapping[str, Any]) -> str:
    segment = guidance.get("current_segment")
    if not isinstance(segment, Mapping):
        return "NOT_APPLICABLE"
    if segment.get("type") == "UNDERPASS":
        blocked = perception.get("underpass_blocked")
        return (
            "BLOCKED"
            if blocked is True
            else "OPERATOR_REQUIRED"
            if blocked is False
            else "UNKNOWN"
        )
    requirements = [str(item.get("id")) for item in segment.get("requirements", [])]
    if not requirements:
        return "NOT_APPLICABLE"
    states = requirement_states(perception)
    values = [states.get(requirement, "UNKNOWN") for requirement in requirements]
    if values and all(value == "READY" for value in values):
        return "READY"
    return "BLOCKED" if "BLOCKED" in values else "UNKNOWN"


def _public_projection(
    *,
    route: Mapping[str, Any] | None,
    guidance: Mapping[str, Any],
    perception: Mapping[str, Any],
    order_error: str | None,
    perception_error: str | None,
    revision_changed: bool,
    restarted: bool,
) -> dict[str, Any]:
    special = _special_state(guidance, perception)
    if order_error:
        stale_state, warning = "INVALID_ORDER", "ORDER_INVALID"
    elif perception_error:
        stale_state, warning = "INVALID_PERCEPTION", "PERCEPTION_INVALID"
    elif restarted:
        stale_state, warning = "RESTARTED", "SERVER_RESTART_REQUIRES_EXPLICIT_PLAN"
    elif revision_changed:
        stale_state, warning = "REVISION_CHANGED", "REVISION_CHANGED"
    elif perception.get("fresh") is not True:
        stale_state, warning = "STALE", "PERCEPTION_STALE_OR_UNKNOWN"
    elif guidance.get("off_route") is True:
        stale_state, warning = "FRESH", "OFF_ROUTE"
    elif special == "OPERATOR_REQUIRED":
        stale_state, warning = "FRESH", "SPECIAL_GAIT_OPERATOR"
    elif (
        perception.get("underpass_blocked") is True
        and guidance.get("current_segment", {}).get("type") == "UNDERPASS"
    ):
        stale_state, warning = "FRESH", "UNDERPASS_BLOCKED"
    elif special in {"BLOCKED", "UNKNOWN"}:
        states = requirement_states(perception)
        requirements = [
            str(item.get("id"))
            for item in guidance.get("current_segment", {}).get("requirements", [])
        ]
        warning = next(
            (item for item in requirements if states.get(item) != "READY"),
            "SPECIAL_EDGE_NOT_READY",
        )
        stale_state = "FRESH"
    else:
        stale_state, warning = "FRESH", None
    active_route = (
        route is not None and not order_error and not revision_changed and not restarted
    )
    eligible = bool(
        active_route
        and not perception_error
        and perception.get("fresh") is True
        and guidance.get("off_route") is not True
        and special in {"READY", "NOT_APPLICABLE"}
    )
    return {
        "selected_route_profile": "BALANCED" if active_route else None,
        "next_instruction": str(guidance.get("instruction_type", "GUIDANCE_PAUSED")),
        "special_edge_readiness": special,
        "manual_warning": warning,
        "autonomous_eligibility": eligible,
        "stale_or_invalid": stale_state,
        "no_side_effects": True,
    }


def replay_scenario(scenario: Mapping[str, Any]) -> dict[str, Any]:
    value = normalize_scenario(scenario)
    graph, annotations = _load_graph_fixture(value["graph_fixture"])
    clock = VirtualMonotonicClock(BASE_TIME_NS)
    provider = MockRoutePerceptionProvider(now_ns=clock.now_ns)
    pose: dict[str, float] | None = None
    pickups: list[str] = []
    dropoff_complete = False
    order_error: str | None = None
    perception_error: str | None = None
    revision_changed = False
    restarted = False
    cancelled = False
    order: dict[str, Any] | None = None
    try:
        digest = hashlib.sha256(value["scenario_id"].encode("ascii")).hexdigest()[:32]
        order = normalize_order(value["order"], order_id=digest)
    except OrderValidationError as exc:
        order_error = str(exc)
    for event in value["events"]:
        scheduled = BASE_TIME_NS + int(event["at_ms"]) * 1_000_000
        try:
            clock.set_ns(scheduled)
        except VirtualClockError as exc:
            raise ScenarioReplayError(
                "event time moved behind the virtual clock"
            ) from exc
        kind, payload = event["kind"], event["payload"]
        if kind == "POSE":
            pose = {key: float(payload[key]) for key in ("x", "y", "yaw")}
        elif kind == "PERCEPTION":
            try:
                provider.set_snapshot(payload)
                perception_error = None
            except PerceptionContractError as exc:
                perception_error = str(exc)
        elif kind == "ORDER_STATUS":
            cancelled = payload["status"] == "CANCELLED"
        elif kind == "PICKUP_CONFIRM":
            if payload["venue_id"] not in pickups:
                pickups.append(str(payload["venue_id"]))
        elif kind == "DROPOFF_CONFIRM":
            dropoff_complete = True
        elif kind == "TIME_ADVANCE":
            try:
                clock.advance_ms(int(payload["advance_ms"]))
            except VirtualClockError as exc:
                raise ScenarioReplayError("time advance is invalid") from exc
        elif kind == "SERVER_RESTART":
            restarted = True
            pose = None
            pickups = []
            dropoff_complete = False
            provider = MockRoutePerceptionProvider(now_ns=clock.now_ns)
        else:
            revision_changed = True
    perception = provider.snapshot()
    route: dict[str, Any] | None = None
    route_error: str | None = None
    if order is not None and not cancelled and not revision_changed and not restarted:
        try:
            route = _select_balanced(
                recommend_routes(
                    order=order,
                    graph=graph,
                    annotations=annotations,
                    start_node_id=value["start_node"],
                    operation_mode="AUTO_NAV2",
                    perception=perception,
                )
            )
        except RoutePlanningError as exc:
            route_error = exc.reason
    if cancelled and order_error is None:
        order_error = "order was cancelled"
    guidance = (
        project_guidance(
            route,
            pose,
            perception,
            completed_pickups=pickups,
            dropoff_complete=dropoff_complete,
        )
        if route is not None
        else {
            "active": False,
            "paused": True,
            "instruction_type": "GUIDANCE_PAUSED",
            "instruction": "GUIDANCE PAUSED",
        }
    )
    actual = _public_projection(
        route=route,
        guidance=guidance,
        perception=perception,
        order_error=order_error or route_error,
        perception_error=perception_error,
        revision_changed=revision_changed,
        restarted=restarted,
    )
    behavior = AdvisoryBehaviorCoordinator().evaluate(
        route=route,
        guidance=guidance,
        perception=perception,
        now_ns=clock.now_ns(),
        pose_fresh=pose is not None,
        revisions_current=not revision_changed,
        server_restarted=restarted,
        external_fault=perception_error or order_error or route_error,
    )
    expected = value["expected"]
    warnings = [actual["manual_warning"]] if actual["manual_warning"] else []
    route_state = (
        "INVALID"
        if order_error or route_error
        else "RESTART_REQUIRED"
        if restarted
        else "REVISION_CHANGED"
        if revision_changed
        else "READY"
    )
    return {
        "scenario_id": value["scenario_id"],
        "event_count": len(value["events"]),
        "route_state": route_state,
        "guidance_state": actual["next_instruction"],
        "perception_freshness": {
            "state": perception["state"],
            "fresh": perception["fresh"],
            "age_s": perception["age_s"],
            "sequence": perception["sequence"],
        },
        "warnings": warnings,
        "recommendation_id": route.get("id") if route else None,
        "advisory_behavior": behavior,
        "expected_vs_actual": {
            "match": expected == actual,
            "expected": expected,
            "actual": actual,
        },
        "side_effect_count": 0,
        "side_effect_counters": dict(SIDE_EFFECT_COUNTERS),
    }


def replay_scenario_file(path: str | Path) -> dict[str, Any]:
    return replay_scenario(load_scenario(path))


__all__ = [
    "ALLOWED_EVENT_KINDS",
    "BASE_TIME_NS",
    "FORBIDDEN_CONTROL_EVENT_KINDS",
    "GRAPH_FIXTURE_ROOT",
    "MAX_SCENARIO_BYTES",
    "MAX_SCENARIO_EVENTS",
    "PUBLIC_PROJECTION_KEYS",
    "SCENARIO_ROOT",
    "SIDE_EFFECT_COUNTERS",
    "ScenarioReplayError",
    "load_scenario",
    "normalize_scenario",
    "replay_scenario",
    "replay_scenario_file",
]
