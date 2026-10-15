"""Integration contracts for shared MS ownership; no ROS or devices."""

import asyncio
import ast
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException

from robot_dashboard.application.mapping_coordinator import MappingCoordinator, MappingCoordinatorConflict
from robot_dashboard.application.lifecycle_coordinator import LifecycleCoordinator
from robot_dashboard.api.routers import dataset
from robot_dashboard.control import ControlError
from robot_dashboard.slam_sessions import project_navigation_context
from robot_dashboard.slam_wiring import configure_slam

# This router imports RosAgent only for annotations. Keep the synthetic port
# local to its import; do not install persistent ROS stubs in the test process.
with patch.dict("sys.modules", {"robot_dashboard.ros_agent": NS(RosAgent=object)}):
    from robot_dashboard.api.routers import cameras


class SlamWiringTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.pipeline = "idle"
        self.nav_active = False
        self.mission_active = False
        self.dataset_active = False
        self.manager = NS(
            snapshot=lambda **kwargs: {"pipeline": {"state": self.pipeline}, "operation": {"state": "idle"}},
            preview_auto_recovery_enabled=False, start_mapping=Mock(), stop_mapping=Mock())
        self.runtime = NS(pipeline_coordination_lock=asyncio.Lock(), slam=None,
            navigation=NS(is_active=lambda: self.nav_active,
                          view=Mock(return_value={"map": None, "readiness": {}, "bindings": {}})),
            mission=NS(blocks_navigation_goal=lambda: self.mission_active),
            dataset_capture=NS(is_active=lambda: self.dataset_active, start=Mock(), snapshot=Mock(return_value={})),
            lifecycle=NS(require_idle=Mock()),
            agent=NS(control_snapshot=Mock(return_value={"lease": {"active": False}}),
                     navigation_runtime_snapshot=Mock(return_value={}),
                     pointcloud_binary_snapshot=Mock(return_value={"updated": time.monotonic(),
                         "topic": "/cloud_registered", "frame_id": "camera_init"})))
        self.runtime.mapping = MappingCoordinator(self.manager, Mock(),
            coordination_lock=self.runtime.pipeline_coordination_lock,
            navigation_active=lambda: self.nav_active, control_lease_active=lambda: False,
            dataset_capture_active=lambda: self.dataset_active,
            require_lifecycle_idle=self.runtime.lifecycle.require_idle)
        self.camera = NS(acquire=Mock(), release=Mock(), snapshot=Mock(return_value={}))
        self.visual = NS(capability=Mock(return_value={"available_now": False, "tasks": ["mapping", "tracking"]}),
                         preflight=Mock(), start=Mock(), stop=Mock(), camera_coordinator=self.camera)
        self.patcher = patch("robot_dashboard.slam_wiring.IsaacStereoAdapter.from_environment", return_value=self.visual)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        configure_slam(self.runtime, Path.cwd(), self.root / "runtime")

    async def test_configuration_and_get_snapshots_never_start_devices(self):
        self.assertIs(self.runtime.slam.coordination_lock, self.runtime.pipeline_coordination_lock)
        self.assertIs(self.runtime.mapping.coordination_lock, self.runtime.pipeline_coordination_lock)
        self.runtime.slam.engines()
        self.runtime.slam.snapshot()
        self.visual.preflight.assert_not_called()
        self.visual.start.assert_not_called()
        self.camera.acquire.assert_not_called()
        self.manager.start_mapping.assert_not_called()

    async def test_broker_camera_owner_replaces_dashboard_camera_owner(self):
        self.assertIs(self.runtime.slam.camera, self.camera)

    async def test_actual_manual_arm_hook_blocks_every_owned_slam_state_before_lease_acquisition(self):
        # Execute the actual route body without importing app.py's ROS startup.
        tree = ast.parse((Path(__file__).resolve().parents[1] / "robot_dashboard/app.py").read_text())
        route = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "control_arm")
        route.decorator_list = []
        def acquire(source):
            self.assertTrue(self.runtime.pipeline_coordination_lock.locked())
            self.assertEqual(source, "keyboard")
            return {"token": "reviewed-test-lease"}
        self.runtime.agent.control_acquire = Mock(side_effect=acquire)
        navigation = Mock(return_value=NS(manual_control_blocked=lambda: False))
        namespace = {"RUNTIME": self.runtime, "HTTPException": HTTPException, "ControlError": ControlError,
                     "require_same_origin": Mock(), "require_manual_operation_mode": Mock(),
                     "require_service_lifecycle_idle": Mock(), "navigation_coordinator": navigation,
                     "agent": lambda: self.runtime.agent, "control_view": lambda value: value}
        exec("from __future__ import annotations\n" + ast.unparse(route), namespace)
        arm = namespace["control_arm"]
        for state in ("PREFLIGHT", "STARTING", "WAITING_INPUT", "TRACKING", "MAPPING", "SAVING", "LOCALIZING", "STOPPING", "ERROR"):
            with self.subTest(state=state):
                self.runtime.slam._session = {"engine_id": "visual_stereo", "state": state}
                with self.assertRaises(HTTPException) as caught:
                    await arm(NS(), NS(input_source="keyboard"))
                self.assertEqual(caught.exception.status_code, 409)
                self.runtime.agent.control_acquire.assert_not_called()
                navigation.assert_not_called()
        self.runtime.slam._session = None
        result = await arm(NS(), NS(input_source="keyboard"))
        self.assertEqual(result["lease_id"], "reviewed-test-lease")
        self.runtime.agent.control_acquire.assert_called_once_with("keyboard")

    async def test_actual_lifecycle_injection_blocks_service_transition_for_slam_and_legacy_mapping(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "robot_dashboard/app.py").read_text())
        call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute) and node.func.attr == "from_environment"
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "LifecycleCoordinator")
        expression = next(item.value for item in call.keywords if item.arg == "mapping_task_active_provider")
        mapping_active = False
        injection_runtime = NS(mapping=NS(task_active=lambda: mapping_active), slam=self.runtime.slam)
        provider = eval(compile(ast.Expression(expression), "<app-lifecycle-provider>", "eval"), {"RUNTIME": injection_runtime})
        lifecycle = LifecycleCoordinator(control_snapshot_provider=lambda: {"lease": {"active": False}},
            navigation_runtime_snapshot_provider=lambda: {"active": False},
            navigation_jobs_snapshot_provider=lambda: {"pipeline": {"state": "idle"}},
            mapping_jobs_snapshot_provider=lambda: {"pipeline": {"state": "idle"}, "operation": {"state": "idle"}},
            mapping_task_active_provider=provider, navigation_start_snapshot_provider=lambda: {},
            dataset_capture_active_provider=lambda: False)
        self.assertNotIn("mapping_operation_active", lifecycle.service_blockers())
        for state in ("PREFLIGHT", "STARTING", "TRACKING", "MAPPING", "SAVING", "STOPPING", "ERROR"):
            with self.subTest(state=state):
                self.runtime.slam._session = {"engine_id": "visual_stereo", "state": state}
                self.assertIn("mapping_operation_active", lifecycle.service_blockers())
        self.runtime.slam._session = None
        mapping_active = True
        self.assertIn("mapping_operation_active", lifecycle.service_blockers())
        mapping_active = False
        injection_runtime.slam = NS(blocks_context_change=Mock(side_effect=RuntimeError("ownership unavailable")))
        self.assertIn("mapping_operation_active", lifecycle.service_blockers())

    async def test_mission_pause_and_cancel_ownership_block_legacy_mutations(self):
        for state in ("running", "pausing", "paused", "canceling"):
            with self.subTest(state=state):
                self.mission_active = True
                with self.assertRaises(MappingCoordinatorConflict):
                    await self.runtime.mapping.start()
        self.manager.start_mapping.assert_not_called()

    async def test_additional_mission_route_owner_blocks_both_sides(self):
        self.runtime.mission_routes = NS(blocks_context_change=lambda: True)
        self.assertIn("mission_route_active", self.runtime.slam._blockers())
        with self.assertRaises(MappingCoordinatorConflict):
            await self.runtime.mapping.stop()
        self.manager.stop_mapping.assert_not_called()

    async def test_active_slam_blocks_navigation_and_legacy_mutation(self):
        self.runtime.slam._session = {"engine_id": "visual_stereo", "state": "MAPPING"}
        busy, reasons = self.runtime.mapping.activity()
        self.assertTrue(busy)
        self.assertIn("slam_session_active", reasons)
        with self.assertRaises(MappingCoordinatorConflict):
            await self.runtime.mapping.start()

    async def test_exact_own_operation_can_use_legacy_lidar_save_but_other_task_cannot(self):
        self.runtime.slam._session = {"engine_id": "lidar_fastlio", "state": "SAVING"}
        self.runtime.slam._operation = asyncio.current_task()
        self.runtime.mapping._require_navigation_idle("owned legacy save")
        async def unrelated_request():
            with self.assertRaises(MappingCoordinatorConflict):
                self.runtime.mapping._require_navigation_idle("other request")
        await asyncio.create_task(unrelated_request())
        self.mission_active = True
        with self.assertRaises(MappingCoordinatorConflict):
            self.runtime.mapping._require_navigation_idle("mission remains authoritative")
        self.runtime.slam._operation = None

    async def test_resource_blockers_reject_nav_dataset_lease_and_existing_pipeline(self):
        self.nav_active = self.dataset_active = True
        self.pipeline = "running"
        self.runtime.agent.control_snapshot.return_value = {"lease": {"active": True}}
        reasons = self.runtime.slam._blockers()
        for expected in ("navigation_active", "dataset_capture_active", "control_lease_active", "existing_lidar_pipeline_active"):
            self.assertIn(expected, reasons)

    async def test_missing_resource_owners_fail_closed(self):
        self.runtime.navigation = self.runtime.mission = self.runtime.dataset_capture = self.runtime.agent = self.runtime.lifecycle = None
        reasons = self.runtime.slam._blockers()
        for expected in ("navigation_active", "mission_active", "dataset_capture_active", "control_state_unavailable", "lifecycle_unavailable"):
            self.assertIn(expected, reasons)

    async def test_stable_legacy_lidar_is_shared_until_ms_owns_a_session(self):
        self.pipeline = "running"
        self.assertEqual(self.runtime.mapping.activity(), (False, []))
        self.runtime.slam._session = {"engine_id": "lidar_fastlio", "state": "MAPPING"}
        self.assertNotIn("existing_lidar_pipeline_active", self.runtime.slam._blockers())
        self.assertIn("slam_session_active", self.runtime.mapping.activity()[1])

    async def test_dataset_capture_guard_runs_before_recorder_start(self):
        self.runtime.slam._session = {"engine_id": "visual_stereo", "state": "MAPPING"}
        router = dataset.create_router(lambda: None)
        endpoint = next(route.endpoint for route in router.routes if route.path.endswith("/capture/start"))
        with patch.object(dataset, "runtime_from_request", return_value=self.runtime), patch.object(dataset, "require_same_origin"):
            with self.assertRaises(HTTPException) as caught:
                await endpoint(NS(sources="both", capture_hz=1, label="test"), NS())
        self.assertEqual(caught.exception.status_code, 409)
        self.runtime.dataset_capture.start.assert_not_called()

    async def test_profile_change_guard_runs_before_service_operation(self):
        self.runtime.slam._session = {"engine_id": "visual_stereo", "state": "TRACKING"}
        profile = Mock()
        with patch.object(cameras, "runtime_from_request", return_value=self.runtime), patch.object(cameras, "require_same_origin"), patch.object(cameras, "require_competition_unlocked"), patch.object(cameras, "_realsense_profile", return_value=profile):
            with self.assertRaises(HTTPException) as caught:
                await cameras.set_realsense_profile(NS(), NS(resolution="640x480", confirmed=True))
        self.assertEqual(caught.exception.status_code, 409)
        profile.apply.assert_not_called()

    async def test_rgb_camera_guard_rejects_before_viewer_acquires_device(self):
        self.runtime.slam._session = {"engine_id": "visual_stereo", "state": "STARTING"}
        websocket = NS(close=AsyncMock(), accept=AsyncMock())
        with patch.object(cameras, "websocket_same_origin", return_value=True), patch.object(cameras, "runtime_from_websocket", return_value=self.runtime), patch.object(cameras, "_agent") as agent:
            await cameras._camera_stream_source(websocket, "realsense_color")
        websocket.close.assert_awaited_once()
        websocket.accept.assert_not_awaited()
        agent.assert_not_called()

    async def test_navigation_context_uses_exact_map_identity_and_never_invents_alignment(self):
        self.runtime.navigation.view.return_value = {"map": {"id": "occupancy-id", "revision": "exact-revision", "frame_id": "map"},
            "bindings": {"localization_odometry": "/Odometry"},
            "readiness": {"localization": False}, "localization": {"state": "lost"}}
        self.runtime.agent.navigation_runtime_snapshot.return_value = {"runtime_health": {"process_generation": 8123},
            "bindings": {"localization_pose": "/amcl_pose"}}
        first = project_navigation_context(self.runtime)
        self.assertEqual(first["navigation_map"], {"id": "occupancy-id", "revision": "exact-revision", "frame": "map"})
        self.assertEqual(first["operational_pose"]["generation"], 8123)
        self.assertEqual(first["operational_pose"]["source"], "/amcl_pose")
        self.assertEqual(first["operational_pose"]["odometry_source"], "/Odometry")
        self.assertFalse(first["alignment"]["verified"])
        self.assertIsNone(first["alignment"]["transform"])
        self.runtime.agent.navigation_runtime_snapshot.return_value = {"runtime_health": {"process_generation": 8124}}
        self.assertNotEqual(first["context_revision"], project_navigation_context(self.runtime)["context_revision"])

    async def test_context_missing_map_and_generation_stay_unknown(self):
        value = project_navigation_context(self.runtime)
        self.assertIsNone(value["navigation_map"]["id"])
        self.assertIsNone(value["navigation_map"]["revision"])
        self.assertIsNone(value["navigation_map"]["frame"])
        self.assertIsNone(value["operational_pose"]["generation"])

    async def test_external_ownership_provider_failure_blocks_both_directions(self):
        self.runtime.mapping.configure_external_guards(activity=Mock(side_effect=RuntimeError()),
                                                      mutation_blocked=Mock(side_effect=RuntimeError()))
        self.assertIn("external_session_state_unavailable", self.runtime.mapping.activity()[1])
        with self.assertRaises(MappingCoordinatorConflict):
            await self.runtime.mapping.start()


if __name__ == "__main__":
    unittest.main()
