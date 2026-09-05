from __future__ import annotations

import ast
import copy
import json
import tempfile
import unittest
from pathlib import Path

from robot_dashboard.application.route_planner_coordinator import (
    RoutePlannerConflict,
    RoutePlannerCoordinator,
    RoutePlannerUnavailable,
    RoutePlannerValidationError,
)
from robot_dashboard.route_planner.mission_dry_run import compile_mission_dry_run
from robot_dashboard.route_planner.perception import MockRoutePerceptionProvider
from robot_dashboard.route_planner.rehearsal import (
    BANNER,
    RehearsalError,
    available_scenarios,
    explain_recommendation,
    interpolate_virtual_pose,
)
from route_planner_fixtures import (
    Geometry,
    annotations,
    graph_payload,
    order_payload,
    ready_perception,
)


class FakeSavedMaps:
    def __init__(self) -> None:
        self.document = annotations()

    def annotations(self, map_id: str) -> dict:
        if map_id != self.document["map_id"]:
            raise ValueError("map mismatch")
        return copy.deepcopy(self.document)

    def route_geometry(self, map_id: str, expected_revision: str) -> Geometry:
        if (
            map_id != self.document["map_id"]
            or expected_revision != self.document["map_revision"]
        ):
            raise ValueError("map revision mismatch")
        return Geometry()


class RecordingMission:
    def __init__(self) -> None:
        self.active = False
        self.created: list[dict] = []

    def blocks_navigation_goal(self) -> bool:
        return self.active

    async def create(self, **kwargs: object) -> dict:
        self.created.append(copy.deepcopy(kwargs))
        return {"mission": {"id": "9" * 32, "state": "ready", **kwargs}}

    def snapshot(self, mission_id: str | None = None) -> dict:
        return {"mission": {"id": mission_id or "9" * 32, "state": "ready"}}


class RehearsalCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.clock = [100.0]
        self.saved_maps = FakeSavedMaps()
        self.mission = RecordingMission()
        self.navigation = {
            "pipeline": {"state": "idle"},
            "goal": {"state": "idle"},
            "localization": {
                "state": "localized",
                "pose": {"x": 0.0, "y": 0.0, "yaw": 0.0},
            },
            "localization_health": {"state": "READY"},
            "map": {"id": "a" * 24, "revision": "b" * 64},
            "path": [],
        }
        self.mapping_active = False
        self.coordinator = RoutePlannerCoordinator(
            self.saved_maps,
            self.mission,
            Path(self.temporary.name).resolve() / "route-planner",
            navigation_view=lambda: copy.deepcopy(self.navigation),
            mapping_activity=lambda: (self.mapping_active, []),
            perception=MockRoutePerceptionProvider(
                ready_perception(), now_ns=lambda: 1_000_000_000
            ),
            now=lambda: self.clock[0],
            allow_rehearsal=True,
        )

    async def asyncTearDown(self) -> None:
        await self.coordinator.close()
        self.temporary.cleanup()

    async def ready(self) -> tuple[dict, dict, dict]:
        order = (await self.coordinator.create_order(order_payload()))["order"]
        graph = (
            await self.coordinator.put_graph(graph_payload(), base_graph_revision=None)
        )["graph"]
        routes = (
            await self.coordinator.recommendations(
                order_id=order["id"],
                order_revision=order["revision"],
                graph_revision=graph["graph_revision"],
                start_node_id="START_NODE",
                operation_mode="AUTO_NAV2",
            )
        )["recommendations"]
        route = (
            await self.coordinator.select(
                routes[0]["id"], route_revision=routes[0]["revision"]
            )
        )["selected_route"]
        return order, graph, route

    async def begin(
        self, scenario_id: str = "traffic-red-to-green"
    ) -> tuple[dict, dict, dict, dict]:
        order, graph, route = await self.ready()
        rehearsal = (
            await self.coordinator.begin_rehearsal(
                route_id=route["id"],
                route_revision=route["revision"],
                scenario_id=scenario_id,
            )
        )["rehearsal"]
        return order, graph, route, rehearsal

    async def test_server_feature_flag_exposes_bounded_scenario_catalog(self) -> None:
        catalog = self.coordinator.rehearsal_scenarios()
        self.assertTrue(catalog["enabled"])
        self.assertEqual(catalog["banner"], BANNER)
        self.assertGreaterEqual(len(catalog["scenarios"]), 20)
        self.assertLessEqual(len(catalog["scenarios"]), 128)

    async def test_every_gp1_scenario_replays_to_completion_without_side_effects(
        self,
    ) -> None:
        _, _, route = await self.ready()
        for scenario in self.coordinator.rehearsal_scenarios()["scenarios"]:
            with self.subTest(scenario=scenario["scenario_id"]):
                started = (
                    await self.coordinator.begin_rehearsal(
                        route_id=route["id"],
                        route_revision=route["revision"],
                        scenario_id=scenario["scenario_id"],
                    )
                )["rehearsal"]
                completed = (
                    await self.coordinator.control_rehearsal(
                        action="SCRUB",
                        payload={"position_ms": started["playback"]["duration_ms"]},
                    )
                )["rehearsal"]
                self.assertEqual(
                    completed["playback"]["position_ms"],
                    completed["playback"]["duration_ms"],
                )
                self.assertEqual(
                    completed["playback"]["event_index"],
                    completed["playback"]["event_count"],
                )
                self.assertEqual(completed["side_effect_count"], 0)
                self.assertTrue(
                    all(
                        value == 0
                        for value in completed["side_effect_counters"].values()
                    )
                )
        self.assertEqual(self.mission.created, [])

    async def test_disabled_server_feature_flag_fails_closed(self) -> None:
        disabled = RoutePlannerCoordinator(
            self.saved_maps,
            self.mission,
            Path(self.temporary.name).resolve() / "disabled",
            navigation_view=lambda: copy.deepcopy(self.navigation),
            mapping_activity=lambda: (False, []),
            perception=MockRoutePerceptionProvider(),
            allow_rehearsal=False,
        )
        try:
            self.assertFalse(disabled.snapshot()["rehearsal"]["enabled"])
            with self.assertRaises(RoutePlannerUnavailable):
                disabled.rehearsal_scenarios()
        finally:
            await disabled.close()

    async def test_begin_is_virtual_only_and_has_zero_side_effects(self) -> None:
        _, _, _, rehearsal = await self.begin()
        self.assertEqual(rehearsal["banner"], BANNER)
        self.assertTrue(rehearsal["virtual_data_only"])
        self.assertFalse(any(rehearsal["restrictions"].values()))
        self.assertEqual(rehearsal["side_effect_count"], 0)
        self.assertTrue(
            all(value == 0 for value in rehearsal["side_effect_counters"].values())
        )
        self.assertEqual(self.mission.created, [])

    async def test_begin_requires_idle_navigation_mission_and_mapping(self) -> None:
        _, _, route = await self.ready()
        for blocker in ("navigation", "mission", "mapping"):
            with self.subTest(blocker=blocker):
                self.navigation["pipeline"]["state"] = (
                    "running" if blocker == "navigation" else "idle"
                )
                self.mission.active = blocker == "mission"
                self.mapping_active = blocker == "mapping"
                with self.assertRaises(RoutePlannerConflict):
                    await self.coordinator.begin_rehearsal(
                        route_id=route["id"],
                        route_revision=route["revision"],
                        scenario_id="traffic-red-to-green",
                    )
        self.navigation["pipeline"]["state"] = "idle"
        self.mission.active = False
        self.mapping_active = False

    async def test_step_pause_scrub_speed_and_reset_are_server_authoritative(
        self,
    ) -> None:
        _, _, _, initial = await self.begin()
        self.assertEqual(initial["playback"]["event_index"], 0)
        stepped = (await self.coordinator.control_rehearsal(action="STEP", payload={}))[
            "rehearsal"
        ]
        self.assertEqual(stepped["playback"]["event_index"], 1)
        await self.coordinator.control_rehearsal(
            action="SET_SPEED", payload={"speed": 2.0}
        )
        await self.coordinator.control_rehearsal(action="PLAY", payload={})
        self.clock[0] += 0.025
        playing = self.coordinator.snapshot()["rehearsal"]
        self.assertEqual(playing["playback"]["speed"], 2.0)
        self.assertGreaterEqual(playing["playback"]["position_ms"], 50)
        paused = (await self.coordinator.control_rehearsal(action="PAUSE", payload={}))[
            "rehearsal"
        ]
        self.assertEqual(paused["playback"]["state"], "PAUSED")
        scrubbed = (
            await self.coordinator.control_rehearsal(
                action="SCRUB", payload={"position_ms": 0}
            )
        )["rehearsal"]
        self.assertEqual(
            scrubbed["playback"]["event_index"],
            sum(item["at_ms"] == 0 for item in scrubbed["events"]),
        )
        reset = (await self.coordinator.control_rehearsal(action="RESET", payload={}))[
            "rehearsal"
        ]
        self.assertEqual(reset["playback"]["event_index"], 0)

    async def test_invalid_control_payload_is_rejected(self) -> None:
        await self.begin()
        with self.assertRaises(RoutePlannerValidationError):
            await self.coordinator.control_rehearsal(
                action="STEP", payload={"position_ms": 1}
            )
        with self.assertRaises(RoutePlannerValidationError):
            await self.coordinator.control_rehearsal(
                action="SET_SPEED", payload={"speed": 3.0}
            )

    async def test_off_route_injection_is_labeled_and_recommends_replan(self) -> None:
        await self.begin()
        rehearsal = (
            await self.coordinator.control_rehearsal(
                action="OFF_ROUTE", payload={"enabled": True}
            )
        )["rehearsal"]
        self.assertTrue(rehearsal["virtual_robot"]["off_route"])
        self.assertEqual(
            rehearsal["advisory_behavior"]["advisory"], "REPLAN_RECOMMENDED"
        )
        self.assertEqual(
            rehearsal["overlay"]["actual_nav2_path_status"], "UNAVAILABLE_IN_REHEARSAL"
        )

    async def test_stale_scenario_fails_closed(self) -> None:
        _, _, _, rehearsal = await self.begin("traffic-green-to-stale")
        duration = rehearsal["playback"]["duration_ms"]
        completed = (
            await self.coordinator.control_rehearsal(
                action="SCRUB", payload={"position_ms": duration}
            )
        )["rehearsal"]
        self.assertFalse(completed["advisory_behavior"]["autonomous_edge_ready"])
        self.assertIn(completed["advisory_behavior"]["advisory"], {"HOLD", "FAULT"})

    async def test_pickups_and_dropoff_change_rehearsal_cargo_only(self) -> None:
        await self.begin()
        first = (
            await self.coordinator.control_rehearsal(
                action="CONFIRM_PICKUP", payload={"venue_id": "HANSOT"}
            )
        )["rehearsal"]
        self.assertEqual(first["delivery"]["cargo_count"], 2)
        second = (
            await self.coordinator.control_rehearsal(
                action="CONFIRM_PICKUP", payload={"venue_id": "EDIYA"}
            )
        )["rehearsal"]
        self.assertEqual(second["delivery"]["cargo_count"], 3)
        complete = (
            await self.coordinator.control_rehearsal(
                action="CONFIRM_DROPOFF", payload={"destination_id": "COEX"}
            )
        )["rehearsal"]
        self.assertEqual(complete["delivery"]["state"], "ORDER_COMPLETE")
        self.assertEqual(complete["delivery"]["cargo_count"], 0)
        self.assertEqual(self.mission.created, [])

    async def test_dropoff_before_pickups_is_rejected(self) -> None:
        await self.begin()
        with self.assertRaises(RoutePlannerValidationError):
            await self.coordinator.control_rehearsal(
                action="CONFIRM_DROPOFF", payload={"destination_id": "COEX"}
            )

    async def test_mission_dry_run_is_pure_and_revision_pinned(self) -> None:
        _, _, route = await self.ready()
        dry_run = self.coordinator.mission_dry_run(
            route["id"], route_revision=route["revision"]
        )
        self.assertTrue(dry_run["eligibility"])
        self.assertGreater(dry_run["waypoint_count"], 0)
        self.assertEqual(dry_run["mission_created"], False)
        self.assertEqual(dry_run["side_effect_count"], 0)
        self.assertEqual(self.mission.created, [])
        with self.assertRaises(RoutePlannerConflict):
            self.coordinator.mission_dry_run(route["id"], route_revision="0" * 64)

    async def test_rehearsal_blocks_existing_guidance_and_mission_export(self) -> None:
        _, _, route, _ = await self.begin()
        with self.assertRaises(RoutePlannerConflict):
            await self.coordinator.start_guidance(
                route_id=route["id"], route_revision=route["revision"]
            )
        with self.assertRaises(RoutePlannerConflict):
            await self.coordinator.export_mission(
                route["id"], route_revision=route["revision"]
            )
        self.assertEqual(self.mission.created, [])

    async def test_report_is_bounded_json_markdown_with_zero_effects(self) -> None:
        await self.begin()
        await self.coordinator.control_rehearsal(action="STEP", payload={})
        report = self.coordinator.rehearsal_report()
        self.assertLess(len(json.dumps(report["json"]).encode()), 128 * 1024)
        self.assertLess(len(report["markdown"].encode()), 128 * 1024)
        self.assertEqual(report["json"]["side_effect_count"], 0)
        self.assertIn("ROBOT WILL NOT MOVE", report["markdown"])

    async def test_exit_restores_normal_route_planner_mutations(self) -> None:
        _, _, route, _ = await self.begin()
        exited = (await self.coordinator.control_rehearsal(action="EXIT", payload={}))[
            "rehearsal"
        ]
        self.assertFalse(exited["active"])
        guidance = await self.coordinator.start_guidance(
            route_id=route["id"], route_revision=route["revision"]
        )
        self.assertTrue(guidance["guidance"]["active"])


class RehearsalPureDomainTests(unittest.TestCase):
    def test_virtual_pose_uses_distance_and_tangent_with_bounded_rate(self) -> None:
        route = {
            "segments": [
                {"polyline": [{"x": 0.0, "y": 0.0}, {"x": 2.0, "y": 0.0}]},
                {"polyline": [{"x": 2.0, "y": 0.0}, {"x": 2.0, "y": 2.0}]},
            ]
        }
        pose = interpolate_virtual_pose(route, 0.75)
        self.assertEqual((pose["x"], pose["y"]), (2.0, 1.0))
        self.assertAlmostEqual(pose["yaw"], 1.570796, places=5)
        self.assertEqual((pose["label"], pose["update_rate_hz"]), ("VIRTUAL ROBOT", 10))

    def test_virtual_pose_rejects_bad_progress_or_empty_route(self) -> None:
        with self.assertRaises(RehearsalError):
            interpolate_virtual_pose({"segments": []}, 0.5)
        with self.assertRaises(RehearsalError):
            interpolate_virtual_pose({"segments": []}, float("nan"))

    def test_explainability_is_deterministic_metric_text(self) -> None:
        route = {
            "profile": "BALANCED",
            "metrics": {
                "eta_s": 20,
                "distance_m": 4,
                "risk_score": 2,
                "travel_time_s": 10,
            },
        }
        first = explain_recommendation(route, [])
        second = explain_recommendation(copy.deepcopy(route), [])
        self.assertEqual(first, second)
        self.assertEqual(first["template"], "DETERMINISTIC_METRICS_V1")
        self.assertIn("ETA 20.0s", first["reason"])

    def test_available_scenarios_reuses_gp1_fixture_root(self) -> None:
        scenarios = available_scenarios()
        self.assertGreaterEqual(len(scenarios), 20)
        self.assertEqual(
            len({item["scenario_id"] for item in scenarios}), len(scenarios)
        )

    def test_dry_run_rejects_revision_mismatch(self) -> None:
        route, graph, order, document = self._compiler_fixture()
        route["map_revision"] = "0" * 64
        result = compile_mission_dry_run(
            route=route, graph=graph, order=order, annotations=document
        )
        self.assertEqual(result["rejection_reason"], "REVISION_MISMATCH")
        self.assertEqual(result["side_effect_count"], 0)

    def test_dry_run_resolves_annotations_and_special_requirement_links(self) -> None:
        route, graph, order, document = self._compiler_fixture()
        result = compile_mission_dry_run(
            route=route, graph=graph, order=order, annotations=document
        )
        self.assertTrue(result["eligibility"])
        self.assertEqual(result["waypoint_count"], 3)
        self.assertEqual(
            result["special_segment_links"][0]["requirements"], ["TRAFFIC_GREEN"]
        )
        self.assertTrue(
            any(item["requires_operator_confirmation"] for item in result["waypoints"])
        )

    def test_dry_run_rejects_more_than_32_waypoints(self) -> None:
        route, graph, order, document = self._compiler_fixture()
        nodes = [
            {
                "id": f"SAFE_{index}",
                "annotation_id": f"{index + 10:024x}",
                "role": "SAFE_HOLD",
                "label": f"Safe {index}",
            }
            for index in range(33)
        ]
        graph["nodes"] = nodes
        route["node_ids"] = [item["id"] for item in nodes]
        result = compile_mission_dry_run(
            route=route, graph=graph, order=order, annotations=document
        )
        self.assertEqual(result["rejection_reason"], "MISSION_WAYPOINT_LIMIT")

    def test_dry_run_rejects_missing_annotation(self) -> None:
        route, graph, order, document = self._compiler_fixture()
        target = next(
            node
            for node in graph["nodes"]
            if node["role"] in {"RESTAURANT_DOCK", "DESTINATION_DOCK"}
        )
        target["annotation_id"] = "f" * 24
        result = compile_mission_dry_run(
            route=route, graph=graph, order=order, annotations=document
        )
        self.assertEqual(result["rejection_reason"], "MISSING_ANNOTATION")

    def test_rehearsal_sources_do_not_reference_runtime_action_owners(self) -> None:
        root = Path(__file__).parents[1]
        paths = [
            root / "robot_dashboard" / "route_planner" / "rehearsal.py",
            root / "robot_dashboard" / "route_planner" / "mission_dry_run.py",
        ]
        forbidden = {
            "ControlManager",
            "NavigationCoordinator",
            "NavigationRosGateway",
            "MissionCoordinator",
            "create",
            "start",
            "activate",
            "acquire",
        }
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            attributes = {
                node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
            }
            self.assertFalse(attributes & forbidden, path.name)

    @staticmethod
    def _compiler_fixture() -> tuple[dict, dict, dict, dict]:
        graph = graph_payload()
        route = {
            "id": "1" * 32,
            "revision": "2" * 64,
            "profile": "BALANCED",
            "map_id": graph["map_id"],
            "map_revision": graph["map_revision"],
            "annotation_revision": graph["annotation_revision"],
            "graph_revision": "3" * 64,
            "node_ids": ["START_NODE", "HANSOT_DOCK", "EDIYA_DOCK", "COEX_DOCK"],
            "segments": [
                {
                    "index": 0,
                    "edge_id": "EDGE",
                    "type": "CROSSWALK",
                    "requirements": [{"id": "TRAFFIC_GREEN"}],
                }
            ],
        }
        graph["graph_revision"] = route["graph_revision"]
        order = order_payload()
        order["total_quantity"] = 3
        return route, graph, order, annotations()


if __name__ == "__main__":
    unittest.main()
