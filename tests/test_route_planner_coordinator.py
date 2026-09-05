import copy
import stat
import tempfile
import unittest
from pathlib import Path

from robot_dashboard.application.route_planner_coordinator import (
    RoutePlannerConflict,
    RoutePlannerCoordinator,
    RoutePlannerValidationError,
)
from robot_dashboard.route_planner.perception import MockRoutePerceptionProvider
from route_planner_fixtures import (
    Geometry,
    annotations,
    graph_payload,
    order_payload,
    ready_perception,
)


class FakeSavedMaps:
    def __init__(self):
        self.document = annotations()

    def annotations(self, map_id):
        assert map_id == self.document["map_id"]
        return copy.deepcopy(self.document)

    def route_geometry(self, map_id, expected_revision):
        assert map_id == self.document["map_id"]
        assert expected_revision == self.document["map_revision"]
        return Geometry()


class FakeMission:
    def __init__(self):
        self.active = False
        self.created = []

    def blocks_navigation_goal(self):
        return self.active

    async def create(self, **kwargs):
        self.created.append(kwargs)
        mission = {
            "id": f"{len(self.created):032x}", "state": "ready", "label": kwargs["label"],
            "map_id": kwargs["map_id"], "map_revision": kwargs["map_revision"],
            "annotation_revision": kwargs["annotation_revision"], "waypoints": kwargs["waypoints"],
        }
        return {"mission": mission}

    def snapshot(self, mission_id=None):
        index = int(mission_id or "0", 16) - 1
        kwargs = self.created[index]
        return {"mission": {"id": mission_id, "state": "ready", **kwargs}}


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve() / "route-planner"
        self.saved_maps = FakeSavedMaps()
        self.mission = FakeMission()
        self.navigation = {
            "pipeline": {"state": "idle"},
            "goal": {"state": "idle"},
            "localization": {"state": "localized", "pose": {"x": 0.1, "y": 0.0, "yaw": 0.0}},
            "localization_health": {"state": "READY"},
            "map": {"id": "a" * 24, "revision": "b" * 64},
            "path": [],
        }
        self.mapping_active = False
        self.perception = MockRoutePerceptionProvider(ready_perception(), now_ns=lambda: 1_000_000_000)
        self.coordinator = RoutePlannerCoordinator(
            self.saved_maps,
            self.mission,
            self.root,
            navigation_view=lambda: copy.deepcopy(self.navigation),
            mapping_activity=lambda: (self.mapping_active, []),
            perception=self.perception,
        )

    async def asyncTearDown(self):
        await self.coordinator.close()
        self.temporary.cleanup()

    async def ready(self):
        order = (await self.coordinator.create_order(order_payload()))["order"]
        graph = (await self.coordinator.put_graph(graph_payload(), base_graph_revision=None))["graph"]
        routes = (await self.coordinator.recommendations(
            order_id=order["id"], order_revision=order["revision"], graph_revision=graph["graph_revision"],
            start_node_id="START_NODE", operation_mode="AUTO_NAV2",
        ))["recommendations"]
        selected = (await self.coordinator.select(routes[0]["id"], route_revision=routes[0]["revision"]))["selected_route"]
        return order, graph, selected

    async def test_single_session_cas_and_private_atomic_store(self):
        order = (await self.coordinator.create_order(order_payload()))["order"]
        state_file = self.root / "route-planner.json"
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(state_file.stat().st_mode), 0o600)
        with self.assertRaises(RoutePlannerConflict):
            await self.coordinator.update_order(order["id"], base_revision="0" * 64, payload=order_payload())
        graph = (await self.coordinator.put_graph(graph_payload(), base_graph_revision=None))["graph"]
        with self.assertRaises(RoutePlannerConflict):
            await self.coordinator.put_graph(graph_payload(), base_graph_revision="0" * 64)
        self.assertEqual(len(graph["graph_revision"]), 64)

    async def test_locked_order_active_navigation_and_mapping_interlocks(self):
        payload = order_payload(); payload["locked"] = True
        order = (await self.coordinator.create_order(payload))["order"]
        with self.assertRaises(RoutePlannerConflict):
            await self.coordinator.update_order(order["id"], base_revision=order["revision"], payload=order_payload())
        self.navigation["pipeline"]["state"] = "running"
        with self.assertRaises(RoutePlannerConflict):
            await self.coordinator.create_order(order_payload())
        self.navigation["pipeline"]["state"] = "idle"; self.mapping_active = True
        with self.assertRaises(RoutePlannerConflict):
            await self.coordinator.put_graph(graph_payload(), base_graph_revision=None)

    async def test_route_is_reused_for_guidance_preview_and_mission_draft_without_motion(self):
        _, _, route = await self.ready()
        guidance = (await self.coordinator.start_guidance(route_id=route["id"], route_revision=route["revision"]))["guidance"]
        self.assertTrue(guidance["active"])
        self.assertFalse(guidance["control_authority"])
        await self.coordinator.stop_guidance()
        preview = self.coordinator.preview(route["id"])
        self.assertEqual(preview["route_graph_preview"]["status"], "READY")
        self.assertEqual(preview["live_nav2_preview"]["status"], "BLOCKED")
        self.assertFalse(preview["goal_submitted"])
        exported = await self.coordinator.export_mission(route["id"], route_revision=route["revision"])
        self.assertTrue(exported["created"])
        self.assertFalse(exported["mission_started"])
        self.assertFalse(exported["navigation_goal_submitted"])
        self.assertGreater(len(self.mission.created[0]["waypoints"]), 0)
        again = await self.coordinator.export_mission(route["id"], route_revision=route["revision"])
        self.assertFalse(again["created"])
        self.assertEqual(len(self.mission.created), 1)

    async def test_annotation_revision_change_marks_recommendations_stale(self):
        _, _, route = await self.ready()
        self.saved_maps.document["annotation_revision"] = "e" * 64
        snapshot = self.coordinator.snapshot()
        self.assertEqual(snapshot["state"], "STALE")
        self.assertIsNone(snapshot["selected_route_id"])
        with self.assertRaises(RoutePlannerConflict):
            await self.coordinator.start_guidance(route_id=route["id"], route_revision=route["revision"])

    async def test_restart_never_resumes_guidance(self):
        _, _, route = await self.ready()
        await self.coordinator.start_guidance(route_id=route["id"], route_revision=route["revision"])
        recovered = RoutePlannerCoordinator(
            self.saved_maps,
            self.mission,
            self.root,
            navigation_view=lambda: copy.deepcopy(self.navigation),
            mapping_activity=lambda: (False, []),
            perception=self.perception,
        )
        try:
            self.assertFalse(recovered.snapshot()["guidance"]["active"])
            self.assertEqual(recovered.snapshot()["state"], "ROUTE_SELECTED")
        finally:
            await recovered.close()

    async def test_operator_pickup_and_dropoff_confirmations_are_explicit_and_persisted(self):
        _, _, route = await self.ready()
        await self.coordinator.start_guidance(route_id=route["id"], route_revision=route["revision"])
        pickup = await self.coordinator.mark_pickup("HANSOT")
        self.assertIn("HANSOT", pickup["guidance"]["completed_pickups"])
        dropoff = await self.coordinator.mark_dropoff("COEX")
        self.assertTrue(dropoff["guidance"]["dropoff_complete"])
        with self.assertRaisesRegex(RoutePlannerValidationError, "not on the selected route"):
            await self.coordinator.mark_dropoff("WHIMOON")

        recovered = RoutePlannerCoordinator(
            self.saved_maps,
            self.mission,
            self.root,
            navigation_view=lambda: copy.deepcopy(self.navigation),
            mapping_activity=lambda: (False, []),
            perception=self.perception,
        )
        try:
            snapshot = recovered.snapshot()
            self.assertFalse(snapshot["guidance"]["active"])
            self.assertIn("HANSOT", snapshot["guidance"]["completed_pickups"])
            self.assertTrue(snapshot["guidance"]["dropoff_complete"])
        finally:
            await recovered.close()

    async def test_mission_active_blocks_export_and_no_navigation_method_is_called(self):
        _, _, route = await self.ready()
        self.mission.active = True
        with self.assertRaises(RoutePlannerConflict):
            await self.coordinator.export_mission(route["id"], route_revision=route["revision"])
        self.assertEqual(self.mission.created, [])

    async def test_mission_export_rejects_more_than_32_semantic_waypoints(self):
        _, _, route = await self.ready()
        route_state = next(
            item
            for item in self.coordinator._state["recommendations"]
            if item["id"] == route["id"]
        )
        graph = self.coordinator._state["graph"]
        synthetic = [
            {
                "id": f"SAFE_HOLD_{index}",
                "annotation_id": "1" * 24,
                "role": "SAFE_HOLD",
                "zone_id": None,
                "venue_id": None,
                "label": f"Safe hold {index}",
                "manual_guidance": True,
                "autonomous_eligible": True,
            }
            for index in range(33)
        ]
        graph["nodes"].extend(synthetic)
        route_state["node_ids"] = [item["id"] for item in synthetic]
        with self.assertRaisesRegex(RoutePlannerConflict, "MISSION_WAYPOINT_LIMIT"):
            await self.coordinator.export_mission(
                route["id"], route_revision=route["revision"]
            )
        self.assertEqual(self.mission.created, [])


if __name__ == "__main__":
    unittest.main()
