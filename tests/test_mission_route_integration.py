"""SYNTHETIC MR/MS contract tests; no ROS, camera, service, or device evidence.

Use the real MS manager, navigation projection, MS blocker wiring, and MR
configure hook. Only hardware-facing providers and native planner transport are
fixtures. All persistence is inside a TemporaryDirectory. The fixture planner's
native-result flag exercises admission only; it is not a native planning run.
"""

import asyncio
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from robot_dashboard.application.mission_coordinator import MissionConflict, MissionCoordinator
from robot_dashboard.mission_routes.models import CreateRequest, RevisionRequest, RunActionRequest, UpdateRequest
from robot_dashboard.mission_routes.wiring import configure_mission_routes
from robot_dashboard.slam_sessions import SlamError, SlamSessionManager, project_navigation_context
from robot_dashboard.slam_wiring import configure_slam
from test_slam_sessions import SyntheticCamera, SyntheticEngine
from test_spatial_routes import MAP_ID, MAP_REVISION, MapProvider, family, normalized, pose


class SyntheticNavigation:
    """Independent port signals make the mission gate testable in isolation."""

    def __init__(self):
        self.goal = {"state": "idle", "goal_id": None}
        self.sent = []
        self.cancels = []
        self.cancel_settles = True
        self.sequence = 1
        self.pose = pose(1.5, 2.0)

    def is_active(self):
        # Deliberately keep the navigation resource blocker clear. These are
        # interface fixtures, not a claim that a live running Nav stack is idle.
        # Otherwise navigation_active could conceal a missing mission gate.
        return False

    def view(self):
        return {
            "seq": self.sequence,
            "pipeline": {"state": "running", "job_id": "synthetic-nav-1"},
            "localization_pipeline": {"job_id": "synthetic-lio-1"},
            "map": {"id": MAP_ID, "revision": MAP_REVISION, "frame_id": "map"},
            "bindings": {"localization_pose": "/amcl_pose", "localization_odometry": "/Odometry"},
            "localization": {"state": "localized", "pose": dict(self.pose)},
            "readiness": {"pose_seq": self.sequence, "localization": True},
            "safety": {"can_send_goal": True},
            "goal": dict(self.goal),
        }

    async def send_goal(self, **values):
        self.sent.append(values)
        self.goal = {"state": "active", "goal_id": f"{len(self.sent):032x}"}
        return {"navigation": self.view()}

    async def cancel_goal(self, *, goal_id):
        self.cancels.append(goal_id)
        if self.cancel_settles:
            self.goal = {"state": "canceled", "goal_id": goal_id}
        return {"navigation": self.view()}


class SyntheticMapping:
    """Capture the real configure_slam legacy guard without starting mapping."""

    def __init__(self):
        self.activity = None
        self.mutation_blocked = None

    def task_active(self):
        return False

    def pipeline_state(self):
        return "idle"

    def configure_external_guards(self, *, activity, mutation_blocked):
        self.activity = activity
        self.mutation_blocked = mutation_blocked

    def save(self, **_values):
        raise AssertionError("The integration fixture must not save a legacy map")


class SyntheticPlannerTransport:
    def __init__(self):
        self.calls = []

    async def plan(self, start, goal):
        self.calls.append((deepcopy(start), deepcopy(goal)))
        return {
            "poses": [deepcopy(start), deepcopy(goal)],
            "frame": "map",
            "actual_nav2_run": True,
            "evidence_type": "synthetic_admission_fixture_not_native_evidence",
        }


class MissionRouteMultiSlamIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="robot-scope-mr-ms-fixture-")
        self.root = Path(self.temporary.name).resolve()
        self.navigation = SyntheticNavigation()
        self.mapping = SyntheticMapping()
        self.maps = MapProvider()
        self.maps.is_fixture = True
        self.engine = SyntheticEngine()
        self.camera = SyntheticCamera()
        self.raw_navigation = {
            "runtime_health": {"process_generation": "synthetic-process-1"},
            "bindings": {"localization_pose": "/amcl_pose"},
        }
        self.mission = MissionCoordinator(
            self.navigation, self.maps, self.root / "legacy",
            poll_interval_s=0.05, cancel_timeout_s=0.1,
        )
        self.runtime = SimpleNamespace(
            navigation=self.navigation,
            mission=self.mission,
            mission_routes=None,
            saved_maps=self.maps,
            spatial_routes=SimpleNamespace(detail=lambda _identifier: {"route": normalized()}),
            pipeline_coordination_lock=asyncio.Lock(),
            slam=None,
            mapping=self.mapping,
            dataset_capture=SimpleNamespace(is_active=lambda: False),
            lifecycle=SimpleNamespace(require_idle=lambda: None),
            agent=SimpleNamespace(
                control_snapshot=lambda: {"lease": {"active": False}},
                navigation_runtime_snapshot=lambda: deepcopy(self.raw_navigation),
                pointcloud_binary_snapshot=lambda: {},
            ),
        )
        # Replace only provider construction. configure_slam's actual blockers,
        # project_navigation_context, MapPackageStore, and manager remain real.
        with mock.patch("robot_dashboard.slam_wiring.CameraOwnerCoordinator", return_value=self.camera), \
                mock.patch("robot_dashboard.slam_wiring.IsaacStereoAdapter.from_environment", return_value=self.engine):
            configure_slam(self.runtime, self.root, self.root / "slam")
        self.manager = self.runtime.slam
        self.policy = {
            "runtime_policy_enforced": True,
            "planner_config_digest": "b" * 64,
            "footprint_revision": "c" * 64,
            "robot_radius_m": 0.25,
        }
        configure_mission_routes(
            self.runtime, self.root / "plans", native_planner_window=False,
            policy_provider=lambda: deepcopy(self.policy),
        )
        self.service = self.runtime.mission_routes
        self.configured_native_planner = self.service.planner
        self.planner = SyntheticPlannerTransport()
        self.service.planner = self.planner

    async def asyncTearDown(self):
        # Test-controlled uncertain cancellation must settle for fixture cleanup.
        self.navigation.cancel_settles = True
        self.engine.start_gate.set()
        self.engine.save_gate.set()
        self.engine.stop_error = None
        self.engine.status_error = None
        try:
            await asyncio.wait_for(self.mission.close(), 3)
            await asyncio.wait_for(self.manager.close(), 3)
        finally:
            self.temporary.cleanup()

    async def create_plan(self, *, request_id="create-plan-000001"):
        payload = CreateRequest.model_validate({
            "label": "합성 교차 계약",
            "map_family": family(),
            "annotation_revision": "7" * 64,
            "visits": [{"visit_id": "a" * 32, "label": "합성 방문", "pose": pose()}],
            "request_id": request_id,
        })
        return (await self.service.write(payload))["plan"]

    async def create_run(self):
        plan = await self.create_plan()
        result = await self.service.create_run(plan["id"], RevisionRequest(
            request_id="create-run-000001", revision=plan["revision"],
        ))
        return result["run"]["id"]

    async def start_slam(self):
        session = await self.manager.start(
            engine_id="visual_stereo", task="mapping",
            request_id="synthetic-ms-start", operator_confirmed=True,
        )
        operation = self.manager._operation
        if operation is not None:
            await asyncio.wait_for(asyncio.shield(operation), 3)
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "MAPPING")
        return session

    async def assert_mission_blocks_ms_changes(self, expected_state):
        snapshot = self.mission.snapshot()
        mission = self.mission.snapshot(snapshot["active_mission_id"])["mission"]
        self.assertEqual(mission["state"], expected_state)
        self.assertTrue(self.mission.blocks_navigation_goal())
        # Check the actual shared integration closure, not a locally reimplemented
        # equivalent. Navigation/dataset/control/mapping blockers are all clear.
        blockers = self.manager._blockers()
        self.assertIn("mission_active", blockers)
        self.assertTrue(set(blockers) <= {"mission_active", "mission_route_active"})
        self.assertTrue(self.mapping.mutation_blocked())
        for engine_id in ("visual_stereo", "lidar_fastlio"):
            with self.subTest(state=expected_state, engine=engine_id):
                with self.assertRaises(SlamError) as raised:
                    await self.manager.start(
                        engine_id=engine_id, task="mapping", operator_confirmed=True,
                        request_id=f"blocked-{expected_state}-{engine_id}",
                    )
                self.assertEqual(raised.exception.code, "RESOURCE_CONFLICT")
        for operation in ("rename_package", "copy_package", "delete_package"):
            with self.subTest(state=expected_state, operation=operation):
                with mock.patch.object(self.manager.packages, operation) as mutation:
                    with self.assertRaises(SlamError) as raised:
                        await self.manager.mutate_package(operation, "d" * 32)
                    self.assertEqual(raised.exception.code, "RESOURCE_CONFLICT")
                    mutation.assert_not_called()
        self.assertIsNone(self.manager.snapshot()["active_session"])
        self.assertEqual(self.engine.calls, [])
        self.assertEqual(self.camera.acquisitions, [])

    async def test_configuration_reuses_real_owners_and_same_coordination_lock(self):
        self.assertIsInstance(self.manager, SlamSessionManager)
        self.assertIs(self.runtime.mission, self.mission)
        self.assertIs(self.manager.coordination_lock, self.runtime.pipeline_coordination_lock)
        self.assertIs(self.mission._coordination_lock, self.runtime.pipeline_coordination_lock)
        self.assertFalse(self.configured_native_planner.enabled)
        self.assertEqual(self.manager.navigation_context(), project_navigation_context(self.runtime))
        self.assertEqual(self.engine.calls, [])
        self.assertEqual(self.camera.acquisitions, [])
        self.assertEqual(self.navigation.sent, [])
        self.assertEqual(self.planner.calls, [])

    async def test_running_paused_and_canceling_mission_block_ms_engine_and_map_mutations(self):
        identifier = await self.create_run()
        await self.service.action(identifier, "start", RunActionRequest(request_id="start-mr-00000001"))
        await self.assert_mission_blocks_ms_changes("running")
        await self.service.action(identifier, "pause", RunActionRequest(request_id="pause-mr-00000001"))
        await self.assert_mission_blocks_ms_changes("paused")
        await self.service.action(identifier, "resume", RunActionRequest(request_id="resume-mr-0000001"))
        self.navigation.cancel_settles = False
        with self.assertRaisesRegex(MissionConflict, "cancellation was not confirmed"):
            await self.service.action(identifier, "abort", RunActionRequest(request_id="abort-mr-00000001"))
        await self.assert_mission_blocks_ms_changes("canceling")

    async def test_active_ms_session_blocks_mr_start_before_planning_or_goal(self):
        identifier = await self.create_run()
        session = await self.start_slam()
        with self.assertRaisesRegex(MissionConflict, "SLAM_CONTEXT_BUSY"):
            await self.service.action(identifier, "start", RunActionRequest(request_id="blocked-start-0001"))
        self.assertFalse(self.mission.blocks_navigation_goal())
        self.assertEqual(self.mission.snapshot(identifier)["mission"]["state"], "ready")
        self.assertEqual(self.navigation.sent, [])
        self.assertEqual(self.planner.calls, [])
        self.assertEqual(self.manager.snapshot()["active_session"]["session_id"], session["session_id"])
        self.assertEqual(self.engine.owner, (session["session_id"], session["generation"]))

    async def test_configure_guard_also_blocks_legacy_mission_start_during_ms(self):
        legacy = await self.mission.create(
            label="합성 legacy", map_id=MAP_ID, map_revision=MAP_REVISION,
            annotation_revision="7" * 64,
            waypoints=[{"mission_local_pose": pose(), "label": "legacy 좌표"}],
        )
        await self.start_slam()
        with self.assertRaisesRegex(MissionConflict, "SLAM_CONTEXT_BUSY"):
            await self.mission.start(legacy["mission"]["id"])
        self.assertFalse(self.mission.blocks_navigation_goal())
        self.assertEqual(self.navigation.sent, [])

    async def test_mr_authoring_during_ms_does_not_claim_resources_or_change_session(self):
        session = await self.start_slam()
        engine_calls = list(self.engine.calls)
        camera_acquisitions = list(self.camera.acquisitions)
        plan = await self.create_plan()
        updated = await self.service.write(UpdateRequest.model_validate({
            **plan["definition"], "label": "매핑 중 편집한 합성 초안",
            "base_revision": plan["revision"], "request_id": "update-plan-000001",
        }), identifier=plan["id"])
        plan = updated["plan"]
        report = self.service.validate(plan["id"], plan["revision"])
        self.assertEqual(report["status"], "PASS")
        self.assertIn("SLAM_CONTEXT_BUSY", report["execution_readiness"]["blocking_reasons"])
        compiled = await self.service.compile(plan["id"], RevisionRequest(
            request_id="compile-plan-0001", revision=plan["revision"],
        ))
        self.assertFalse(compiled["compiled"]["start_sent"])
        self.assertFalse(self.mission.blocks_navigation_goal())
        self.assertEqual(self.navigation.sent, [])
        self.assertEqual(self.planner.calls, [])
        self.assertEqual(self.engine.calls, engine_calls)
        self.assertEqual(self.camera.acquisitions, camera_acquisitions)
        self.assertEqual(self.manager.snapshot()["active_session"]["session_id"], session["session_id"])

    async def test_projected_pose_authority_and_generation_reach_mr_without_visual_engine_promotion(self):
        before = self.service.context.snapshot()
        self.assertEqual(before["pose_source"]["source"], "/amcl_pose")
        self.assertEqual(before["pose_source"]["odometry_source"], "/Odometry")
        self.assertFalse(self.manager.navigation_context()["alignment"]["verified"])
        await self.start_slam()
        while_observing = self.service.context.snapshot()
        self.assertEqual(while_observing["pose_source"]["source"], "/amcl_pose")
        self.assertEqual(before["navigation_context_revision"], while_observing["navigation_context_revision"])
        self.navigation.sequence += 1
        self.navigation.pose = pose(1.6, 2.0)
        self.assertEqual(before["navigation_context_revision"], self.service.context.snapshot()["navigation_context_revision"])
        self.raw_navigation["runtime_health"]["process_generation"] = "synthetic-process-2"
        self.assertNotEqual(before["navigation_context_revision"], self.service.context.snapshot()["navigation_context_revision"])
        self.raw_navigation["bindings"].clear()
        self.assertIsNone(self.manager.navigation_context()["operational_pose"]["source"])
        self.assertIsNone(self.service.context.snapshot()["pose_source"]["source"])
        self.assertEqual(self.navigation.sent, [])

    async def test_source_generation_change_cancels_only_the_owned_moving_goal(self):
        identifier = await self.create_run()
        await self.service.action(identifier, "start", RunActionRequest(request_id="source-start-00001"))
        owned = self.navigation.goal["goal_id"]
        self.raw_navigation["runtime_health"]["process_generation"] = "changed-runtime"
        for _ in range(50):
            await asyncio.sleep(0.02)
            mission = self.mission.snapshot(identifier)["mission"]
            if mission["state"] == "failed":
                break
        self.assertEqual(mission["outcome"], "context_changed")
        self.assertFalse(mission["ownership_active"])
        self.assertEqual(self.navigation.cancels, [owned])
        self.assertEqual(len(self.navigation.sent), 1)

    async def test_paused_run_cannot_resume_after_annotation_revision_change(self):
        identifier = await self.create_run()
        await self.service.action(identifier, "start", RunActionRequest(request_id="ann-start-0000001"))
        await self.service.action(identifier, "pause", RunActionRequest(request_id="ann-pause-0000001"))
        self.maps.document["annotation_revision"] = "9" * 64
        with self.assertRaisesRegex(MissionConflict, "ANNOTATION_REVISION_CHANGED"):
            await self.service.action(identifier, "resume", RunActionRequest(request_id="ann-resume-000001"))
        self.assertEqual(len(self.navigation.sent), 1)
        self.assertEqual(self.mission.snapshot(identifier)["mission"]["state"], "paused")
