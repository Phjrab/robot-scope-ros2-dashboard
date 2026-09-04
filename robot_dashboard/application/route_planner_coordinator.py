"""Server-authoritative Track G Route Planner application coordinator."""

from __future__ import annotations

import asyncio
import copy
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from ..route_planner.catalog import CATALOG_REVISION, competition_catalog
from ..route_planner.graph import RouteGraphError, normalize_graph
from ..route_planner.guidance import project_guidance
from ..route_planner.optimizer import RoutePlanningError, recommend_routes
from ..route_planner.orders import OrderValidationError, normalize_order
from ..route_planner.perception import RoutePerceptionProvider
from ..route_planner.state_store import RoutePlannerStateStore, RoutePlannerStorageError, empty_state


PLANNER_STATES = frozenset(
    {
        "EMPTY", "DRAFT", "VALIDATING_ORDER", "ORDER_READY", "PLANNING",
        "RECOMMENDATIONS_READY", "ROUTE_SELECTED", "GUIDANCE_ACTIVE",
        "MISSION_EXPORTED", "STALE", "INVALID", "FAILED",
    }
)
MISSION_NODE_ROLES = frozenset(
    {
        "SAFE_HOLD", "RESTAURANT_APPROACH", "RESTAURANT_DOCK",
        "DESTINATION_APPROACH", "DESTINATION_DOCK", "CROSSWALK_WAIT",
        "CROSSWALK_EXIT", "UNDERPASS_ENTRY", "UNDERPASS_EXIT",
    }
)


class RoutePlannerError(RuntimeError):
    pass


class RoutePlannerNotFound(RoutePlannerError):
    pass


class RoutePlannerConflict(RoutePlannerError):
    pass


class RoutePlannerValidationError(RoutePlannerError):
    pass


class RoutePlannerUnavailable(RoutePlannerError):
    pass


class SavedMapsPort(Protocol):
    def annotations(self, map_id: str) -> dict[str, Any]: ...

    def route_geometry(self, map_id: str, expected_revision: str) -> Any: ...


class MissionPort(Protocol):
    def blocks_navigation_goal(self) -> bool: ...

    def snapshot(self, mission_id: str | None = None) -> dict[str, Any]: ...

    async def create(self, *, label: str, map_id: str, map_revision: str, annotation_revision: str, waypoints: list[Mapping[str, Any]]) -> dict[str, Any]: ...


class RoutePlannerCoordinator:
    """Own one planner session without acquiring motion authority."""

    def __init__(
        self,
        saved_maps: SavedMapsPort,
        mission: MissionPort,
        state_root: Path,
        *,
        navigation_view: Callable[[], Mapping[str, Any]],
        mapping_activity: Callable[[], tuple[bool, list[str]]],
        perception: RoutePerceptionProvider,
        now: Callable[[], float] = time.time,
        allow_custom_orders: bool = False,
    ) -> None:
        self._saved_maps = saved_maps
        self._mission = mission
        self._navigation_view = navigation_view
        self._mapping_activity = mapping_activity
        self._perception = perception
        self._now = now
        self._allow_custom_orders = allow_custom_orders
        self._lock = asyncio.Lock()
        self._store: RoutePlannerStateStore | None = None
        self._storage_error = ""
        try:
            self._store = RoutePlannerStateStore(Path(state_root))
            self._state = self._store.load()
            self._validate_loaded_state()
            self._save()  # persist restart guidance fence
        except (RoutePlannerStorageError, RoutePlannerError, ValueError, TypeError):
            self._state = empty_state()
            self._storage_error = "route planner state storage is unavailable"

    def _validate_loaded_state(self) -> None:
        if self._state.get("state") not in PLANNER_STATES:
            raise RoutePlannerUnavailable("route planner state is invalid")
        if not isinstance(self._state.get("recommendations"), list) or len(self._state["recommendations"]) > 3:
            raise RoutePlannerUnavailable("route planner recommendation state is invalid")
        if not isinstance(self._state.get("mission_links"), list) or len(self._state["mission_links"]) > 32:
            raise RoutePlannerUnavailable("route planner mission link state is invalid")

    def _save(self) -> None:
        if self._store is None or self._storage_error:
            raise RoutePlannerUnavailable(self._storage_error or "route planner state storage is unavailable")
        try:
            self._store.save(self._state)
        except RoutePlannerStorageError as exc:
            self._storage_error = "route planner state storage is unavailable"
            raise RoutePlannerUnavailable(self._storage_error) from exc

    def _navigation_active(self) -> bool:
        value = self._navigation_view()
        pipeline = value.get("pipeline") if isinstance(value.get("pipeline"), Mapping) else {}
        goal = value.get("goal") if isinstance(value.get("goal"), Mapping) else {}
        return str(pipeline.get("state", "idle")).lower() in {"starting", "running", "stopping"} or str(goal.get("state", "idle")).lower() in {"pending", "active", "canceling"}

    def _require_editable(self, action: str, *, graph: bool = False) -> None:
        if self._state.get("guidance", {}).get("active"):
            raise RoutePlannerConflict(f"{action} is blocked while guidance is active")
        if self._mission.blocks_navigation_goal():
            raise RoutePlannerConflict(f"{action} is blocked while a mission is active")
        if self._navigation_active():
            raise RoutePlannerConflict(f"{action} is blocked while navigation is active")
        mapping_active, _ = self._mapping_activity()
        if graph and mapping_active:
            raise RoutePlannerConflict(f"{action} is blocked while mapping is active")

    def _annotations(self, graph: Mapping[str, Any] | None = None) -> dict[str, Any]:
        target = graph or self._state.get("graph")
        if not isinstance(target, Mapping):
            raise RoutePlannerConflict("route graph is not configured")
        try:
            annotations = self._saved_maps.annotations(str(target["map_id"]))
        except Exception as exc:
            raise RoutePlannerConflict("route graph annotations are unavailable") from exc
        if (
            annotations.get("map_id") != target.get("map_id")
            or annotations.get("map_revision") != target.get("map_revision")
            or annotations.get("annotation_revision") != target.get("annotation_revision")
        ):
            raise RoutePlannerConflict("route graph map or annotations changed")
        return annotations

    def _selected(self, route_id: str | None = None) -> dict[str, Any]:
        identifier = route_id or self._state.get("selected_route_id")
        for route in self._state.get("recommendations", []):
            if route.get("id") == identifier:
                return route
        raise RoutePlannerNotFound("selected route was not found")

    def _is_stale(self) -> tuple[bool, str]:
        graph = self._state.get("graph")
        order = self._state.get("order")
        context = self._state.get("selected_context")
        if not isinstance(graph, Mapping) or not isinstance(order, Mapping) or not isinstance(context, Mapping):
            return False, ""
        pins = {
            "order_revision": order.get("revision"),
            "graph_revision": graph.get("graph_revision"),
            "map_revision": graph.get("map_revision"),
            "annotation_revision": graph.get("annotation_revision"),
            "planner_config_revision": CATALOG_REVISION,
        }
        for key, value in pins.items():
            if context.get(key) != value:
                return True, key.upper() + "_CHANGED"
        try:
            self._annotations(graph)
        except RoutePlannerConflict:
            return True, "MAP_OR_ANNOTATION_REVISION_CHANGED"
        return False, ""

    def snapshot(self) -> dict[str, Any]:
        value = copy.deepcopy(self._state)
        stale, reason = self._is_stale()
        if stale and value.get("recommendations"):
            value["state"] = "STALE"
            value["stale_reason"] = reason
            value["selected_route_id"] = None
        selected = None
        if value.get("selected_route_id"):
            selected = next((item for item in value["recommendations"] if item.get("id") == value["selected_route_id"]), None)
        value.update(
            {
                "available": not bool(self._storage_error),
                "error": self._storage_error or value.get("error"),
                "catalog_revision": CATALOG_REVISION,
                "selected_route": selected,
                "perception": self._perception.snapshot(),
                "limits": {"max_recommendations": 3, "max_mission_waypoints": 32, "single_active_session": True},
                "motion_authority": False,
            }
        )
        if value.get("guidance", {}).get("active") and selected is not None:
            value["guidance"] = self.guidance_snapshot(selected=selected)
        return value

    @staticmethod
    def catalog() -> dict[str, Any]:
        return competition_catalog()

    async def create_order(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        async with self._lock:
            self._require_editable("order creation")
            self._state["state"] = "VALIDATING_ORDER"
            try:
                order = normalize_order(payload, allow_custom=self._allow_custom_orders)
            except OrderValidationError as exc:
                self._state.update(state="INVALID", error=str(exc))
                self._save()
                raise RoutePlannerValidationError(str(exc)) from exc
            self._state.update(
                state="ORDER_READY", order=order, recommendations=[], selected_route_id=None,
                selected_context=None,
                guidance={"active": False, "completed_pickups": [], "dropoff_complete": False, "current_segment_index": 0},
                mission_links=[], error=None,
            )
            self._save()
            return {"order": copy.deepcopy(order), "route_planner": self.snapshot()}

    async def update_order(self, order_id: str, *, base_revision: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        async with self._lock:
            self._require_editable("order update")
            current = self._state.get("order")
            if not isinstance(current, Mapping) or current.get("id") != order_id:
                raise RoutePlannerNotFound("order was not found")
            if current.get("revision") != base_revision:
                raise RoutePlannerConflict("order revision changed")
            if current.get("locked"):
                raise RoutePlannerConflict("locked order cannot be changed")
            try:
                order = normalize_order(payload, order_id=order_id, allow_custom=self._allow_custom_orders)
            except OrderValidationError as exc:
                raise RoutePlannerValidationError(str(exc)) from exc
            self._state.update(
                state="ORDER_READY", order=order, recommendations=[], selected_route_id=None,
                selected_context=None,
                guidance={"active": False, "completed_pickups": [], "dropoff_complete": False, "current_segment_index": 0},
                mission_links=[], error=None,
            )
            self._save()
            return {"order": copy.deepcopy(order), "route_planner": self.snapshot()}

    def order(self, order_id: str) -> dict[str, Any]:
        current = self._state.get("order")
        if not isinstance(current, Mapping) or current.get("id") != order_id:
            raise RoutePlannerNotFound("order was not found")
        return {"order": copy.deepcopy(current)}

    async def put_graph(self, payload: Mapping[str, Any], *, base_graph_revision: str | None) -> dict[str, Any]:
        async with self._lock:
            self._require_editable("route graph update", graph=True)
            current = self._state.get("graph")
            if current is not None and current.get("graph_revision") != base_graph_revision:
                raise RoutePlannerConflict("route graph revision changed")
            if current is None and base_graph_revision not in {None, ""}:
                raise RoutePlannerConflict("route graph does not yet have a revision")
            try:
                annotations = self._saved_maps.annotations(str(payload.get("map_id", "")))
                geometry = self._saved_maps.route_geometry(str(payload.get("map_id", "")), str(payload.get("map_revision", "")))
                graph = normalize_graph(payload, annotations=annotations, geometry=geometry)
            except RouteGraphError as exc:
                raise RoutePlannerValidationError(str(exc)) from exc
            except Exception as exc:
                raise RoutePlannerValidationError("route graph map geometry is unavailable") from exc
            self._state.update(
                graph=graph, recommendations=[], selected_route_id=None, selected_context=None,
                guidance={"active": False, "completed_pickups": [], "dropoff_complete": False, "current_segment_index": 0},
                mission_links=[], state="ORDER_READY" if self._state.get("order") else "DRAFT", error=None,
            )
            self._save()
            return {"graph": copy.deepcopy(graph), "route_planner": self.snapshot()}

    def graph(self) -> dict[str, Any]:
        graph = self._state.get("graph")
        return {"graph": copy.deepcopy(graph), "configured": isinstance(graph, Mapping)}

    def recommendation(self, route_id: str) -> dict[str, Any]:
        return {"recommendation": copy.deepcopy(self._selected(route_id))}

    async def recommendations(
        self,
        *,
        order_id: str,
        order_revision: str,
        graph_revision: str,
        start_node_id: str,
        operation_mode: str,
    ) -> dict[str, Any]:
        async with self._lock:
            self._require_editable("route recommendation", graph=True)
            order = self._state.get("order")
            graph = self._state.get("graph")
            if not isinstance(order, Mapping) or order.get("id") != order_id:
                raise RoutePlannerNotFound("order was not found")
            if order.get("revision") != order_revision:
                raise RoutePlannerConflict("order revision changed")
            if not isinstance(graph, Mapping) or graph.get("graph_revision") != graph_revision:
                raise RoutePlannerConflict("route graph revision changed")
            annotations = self._annotations(graph)
            self._state.update(state="PLANNING", error=None)
            try:
                routes = recommend_routes(
                    order=order, graph=graph, annotations=annotations, start_node_id=start_node_id,
                    operation_mode=operation_mode, perception=self._perception.snapshot(),
                )
            except RoutePlanningError as exc:
                self._state.update(state="FAILED", error=exc.reason)
                self._save()
                raise RoutePlannerConflict(f"{exc.reason}: {exc}") from exc
            context = {
                "order_revision": order["revision"], "graph_revision": graph["graph_revision"],
                "map_revision": graph["map_revision"], "annotation_revision": graph["annotation_revision"],
                "planner_config_revision": CATALOG_REVISION, "start_node_id": start_node_id,
                "operation_mode": operation_mode,
            }
            self._state.update(
                recommendations=routes, selected_route_id=None, selected_context=context,
                guidance={"active": False, "completed_pickups": [], "dropoff_complete": False, "current_segment_index": 0},
                mission_links=[], state="RECOMMENDATIONS_READY", error=None,
            )
            self._save()
            return {"recommendations": copy.deepcopy(routes), "route_planner": self.snapshot()}

    async def select(self, route_id: str, *, route_revision: str) -> dict[str, Any]:
        async with self._lock:
            self._require_editable("route selection")
            stale, reason = self._is_stale()
            if stale:
                raise RoutePlannerConflict(f"route recommendations are stale: {reason}")
            route = self._selected(route_id)
            if route.get("revision") != route_revision:
                raise RoutePlannerConflict("route revision changed")
            self._state.update(selected_route_id=route_id, state="ROUTE_SELECTED", error=None)
            self._save()
            return {"selected_route": copy.deepcopy(route), "route_planner": self.snapshot()}

    def _current_pose(self) -> Mapping[str, Any] | None:
        navigation = self._navigation_view()
        localization = navigation.get("localization") if isinstance(navigation.get("localization"), Mapping) else {}
        health = navigation.get("localization_health") if isinstance(navigation.get("localization_health"), Mapping) else {}
        pose = localization.get("pose")
        if localization.get("state") != "localized" or health.get("state") not in {None, "READY"}:
            return None
        return pose if isinstance(pose, Mapping) else None

    def guidance_snapshot(self, *, selected: Mapping[str, Any] | None = None) -> dict[str, Any]:
        route = dict(selected or self._selected())
        state = self._state.get("guidance", {})
        return project_guidance(
            route, self._current_pose(), self._perception.snapshot(),
            previous_segment_index=int(state.get("current_segment_index", 0)),
            completed_pickups=list(state.get("completed_pickups", [])),
            dropoff_complete=state.get("dropoff_complete") is True,
        )

    async def start_guidance(self, *, route_id: str, route_revision: str) -> dict[str, Any]:
        async with self._lock:
            stale, reason = self._is_stale()
            if stale:
                raise RoutePlannerConflict(f"route is stale: {reason}")
            route = self._selected(route_id)
            if self._state.get("selected_route_id") != route_id or route.get("revision") != route_revision:
                raise RoutePlannerConflict("selected route revision changed")
            if self._mission.blocks_navigation_goal():
                raise RoutePlannerConflict("guidance cannot start while a mission is active")
            self._state["guidance"] = {
                "active": True,
                "completed_pickups": [],
                "dropoff_complete": False,
                "current_segment_index": 0,
            }
            self._state["state"] = "GUIDANCE_ACTIVE"
            self._save()
            return {"guidance": self.guidance_snapshot(selected=route), "route_planner": self.snapshot()}

    async def stop_guidance(self) -> dict[str, Any]:
        async with self._lock:
            guidance = self._state.get("guidance", {})
            self._state["guidance"] = {
                "active": False,
                "completed_pickups": list(guidance.get("completed_pickups", []))[:5],
                "dropoff_complete": guidance.get("dropoff_complete") is True,
                "current_segment_index": int(guidance.get("current_segment_index", 0)),
            }
            self._state["state"] = "ROUTE_SELECTED" if self._state.get("selected_route_id") else "RECOMMENDATIONS_READY"
            self._save()
            return {"guidance": copy.deepcopy(self._state["guidance"]), "route_planner": self.snapshot()}

    async def mark_pickup(self, venue_id: str) -> dict[str, Any]:
        async with self._lock:
            if not self._state.get("guidance", {}).get("active"):
                raise RoutePlannerConflict("guidance is not active")
            route = self._selected()
            pickup_ids = {str(stop.get("venue_id")) for stop in route["stops"] if stop.get("role") in {"RESTAURANT_APPROACH", "RESTAURANT_DOCK"}}
            if venue_id not in pickup_ids:
                raise RoutePlannerValidationError("pickup venue is not on the selected route")
            completed = list(self._state["guidance"].get("completed_pickups", []))
            if venue_id not in completed:
                completed.append(venue_id)
            self._state["guidance"]["completed_pickups"] = completed[:5]
            projection = self.guidance_snapshot(selected=route)
            self._state["guidance"]["current_segment_index"] = int(projection.get("current_segment_index", 0))
            self._save()
            return {"guidance": projection, "route_planner": self.snapshot()}

    async def mark_dropoff(self, destination_id: str) -> dict[str, Any]:
        async with self._lock:
            if not self._state.get("guidance", {}).get("active"):
                raise RoutePlannerConflict("guidance is not active")
            route = self._selected()
            destination_ids = {
                str(stop.get("venue_id"))
                for stop in route["stops"]
                if stop.get("role") in {"DESTINATION_APPROACH", "DESTINATION_DOCK"}
            }
            if destination_id not in destination_ids:
                raise RoutePlannerValidationError("dropoff destination is not on the selected route")
            self._state["guidance"]["dropoff_complete"] = True
            projection = self.guidance_snapshot(selected=route)
            self._state["guidance"]["current_segment_index"] = int(
                projection.get("current_segment_index", 0)
            )
            self._save()
            return {"guidance": projection, "route_planner": self.snapshot()}

    def preview(self, route_id: str) -> dict[str, Any]:
        route = self._selected(route_id)
        stale, reason = self._is_stale()
        if stale:
            raise RoutePlannerConflict(f"route is stale: {reason}")
        points: list[dict[str, float]] = []
        for segment in route["segments"]:
            for point in segment["polyline"]:
                normalized = {"x": float(point["x"]), "y": float(point["y"]), "z": 0.035}
                if not points or points[-1] != normalized:
                    points.append(normalized)
        navigation = self._navigation_view()
        nav_map = navigation.get("map") if isinstance(navigation.get("map"), Mapping) else {}
        exact = nav_map.get("id") == route["map_id"] and nav_map.get("revision") == route["map_revision"]
        return {
            "route_id": route["id"],
            "route_revision": route["revision"],
            "map_id": route["map_id"],
            "map_revision": route["map_revision"],
            "route_graph_preview": {"status": "READY", "kind": "EXACT_2D_ROUTE_GRAPH", "points": points[:4096]},
            "live_nav2_preview": {
                "status": "BLOCKED",
                "reason": "SAFE_PLAN_ONLY_NAV2_INTERFACE_NOT_AVAILABLE",
                "actual_path": list(navigation.get("path", []))[:512] if exact else [],
            },
            "goal_submitted": False,
        }

    async def export_mission(self, route_id: str, *, route_revision: str) -> dict[str, Any]:
        async with self._lock:
            if self._mission.blocks_navigation_goal():
                raise RoutePlannerConflict("mission export is blocked while a mission is active")
            stale, reason = self._is_stale()
            if stale:
                raise RoutePlannerConflict(f"route is stale: {reason}")
            route = self._selected(route_id)
            if self._state.get("selected_route_id") != route_id or route.get("revision") != route_revision:
                raise RoutePlannerConflict("selected route revision changed")
            for link in self._state["mission_links"]:
                if link.get("route_revision") == route_revision:
                    try:
                        return {"mission": self._mission.snapshot(str(link["mission_id"]))["mission"], "link": copy.deepcopy(link), "created": False}
                    except Exception:
                        break
            graph = self._state.get("graph")
            order = self._state.get("order")
            if not isinstance(graph, Mapping) or not isinstance(order, Mapping):
                raise RoutePlannerConflict("route graph or order is unavailable")
            nodes = {str(node["id"]): node for node in graph["nodes"]}
            waypoint_nodes = []
            for node_id in route["node_ids"]:
                node = nodes.get(str(node_id))
                if node and node["role"] in MISSION_NODE_ROLES and (not waypoint_nodes or waypoint_nodes[-1]["id"] != node["id"]):
                    waypoint_nodes.append(node)
            if not waypoint_nodes:
                raise RoutePlannerConflict("route has no mission waypoint nodes")
            if len(waypoint_nodes) > 32:
                raise RoutePlannerConflict("MISSION_WAYPOINT_LIMIT")
            waypoints = [
                {
                    "annotation_id": node["annotation_id"],
                    "arrival_tolerance": None,
                    "hold_seconds": 0.0,
                    "requires_operator_confirmation": node["role"] in {"CROSSWALK_WAIT", "SAFE_HOLD", "RESTAURANT_DOCK", "DESTINATION_DOCK"},
                    "label": str(node["label"])[:64],
                }
                for node in waypoint_nodes
            ]
            response = await self._mission.create(
                label=f"{order['label']} · {route['profile']}",
                map_id=route["map_id"], map_revision=route["map_revision"],
                annotation_revision=route["annotation_revision"], waypoints=waypoints,
            )
            mission = response["mission"]
            link = {
                "route_id": route["id"], "route_revision": route["revision"],
                "mission_id": mission["id"], "map_revision": route["map_revision"],
                "annotation_revision": route["annotation_revision"],
                "segment_requirements": [
                    {"segment_index": segment["index"], "requirements": [item["id"] for item in segment["requirements"]]}
                    for segment in route["segments"] if segment["requirements"]
                ],
            }
            self._state["mission_links"] = (self._state["mission_links"] + [link])[-32:]
            self._state["state"] = "MISSION_EXPORTED"
            self._save()
            return {"mission": mission, "link": copy.deepcopy(link), "created": True, "mission_started": False, "navigation_goal_submitted": False}

    async def close(self) -> None:
        async with self._lock:
            guidance = self._state.get("guidance", {})
            if guidance.get("active"):
                self._state["guidance"] = {
                    "active": False,
                    "completed_pickups": list(guidance.get("completed_pickups", []))[:5],
                    "dropoff_complete": guidance.get("dropoff_complete") is True,
                    "current_segment_index": int(guidance.get("current_segment_index", 0)),
                }
                self._state["state"] = "ROUTE_SELECTED" if self._state.get("selected_route_id") else "RECOMMENDATIONS_READY"
                self._save()


__all__ = [
    "PLANNER_STATES", "RoutePlannerConflict", "RoutePlannerCoordinator", "RoutePlannerError",
    "RoutePlannerNotFound", "RoutePlannerUnavailable", "RoutePlannerValidationError",
]
