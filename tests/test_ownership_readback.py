"""Synthetic ownership readback only: no ROS, native backend or device starts."""
import asyncio
import copy
import json
import os
import threading
import tempfile
import time
import unittest
from collections import deque
from types import SimpleNamespace as NS
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI

from robot_dashboard.api.routers.system import router
from robot_dashboard.application.ownership_readback import ownership_readback, SCHEMA, _thread
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.control import ControlManager


def forbidden(*args, **kwargs):
    raise AssertionError("readback invoked a stateful method")


def idle_runtime():
    manager = ControlManager(clock=lambda: 1000.)
    manager.snapshot = forbidden
    transport = NS(operation_lock=threading.RLock(), manager=manager, raw_snapshot=forbidden,
                   flush_outputs=forbidden)
    gateway = NS(_navigation_lock=threading.RLock(),
                 _navigation=dict(active=False, map=None, goal=dict(state="idle")),
                 _localization_only=dict(active=False, state="idle"),
                 _navigation_token="", _navigation_goal_handle=None, runtime_snapshot=forbidden)
    agent = NS(_control_transport=transport, _navigation_gateway=gateway,
               _pointcloud_hub=NS(_raw_capture=NS(_lock=threading.RLock(), _record=None,
                                                 _in_flight=None, _generation=0)),
               control_snapshot=forbidden, navigation_runtime_snapshot=forbidden)
    mapping_manager = NS(_lock=threading.RLock(), _pipeline=dict(state="idle", job_id=None),
                         _preview=dict(state="running"), _operation=dict(state="idle"),
                         _pipeline_process=None, _save_process=None, _pipeline_pgid=None,
                         _save_pgid=None, snapshot=forbidden)
    mapping = NS(_manager=mapping_manager, _task=None, _preview_recovery_task=None,
                 _preview_recovery_inflight=None, snapshot=forbidden)
    jobs = NS(_lock=threading.RLock(), _pipeline=dict(state="idle", job_id=None),
              _process=None, _pgid=None, _map_snapshot=None, snapshot=forbidden)
    navigation = NS(_state_lock=threading.RLock(),
                    _start=dict(pending=False, mapping_owned=False, phase="idle", token=None,
                                mapping_job_id=None, navigation_job_id=None, terminal_cleanup=False),
                    _localization_session=dict(active=False, state="idle", token=None),
                    _start_task=None, _jobs=jobs, _agent=agent, view=forbidden)
    camera = NS(_owner=None, _reservation_unknown=False, snapshot=forbidden)
    slam = NS(_session=None, _operation=None, camera=camera, _camera_owned=False,
              _camera_acquisition_pending=False, _runtime_start_attempted=False,
              _scratch=None, _generation=3, snapshot=forbidden)
    dataset = NS(_lock=threading.RLock(), _state="idle", _session_id="", _sampler_thread=None,
                 _writer_thread=None, _export_active=False, snapshot=forbidden)
    mission = NS(_task=None, _active_id=None, _operation_lock=asyncio.Lock(),
                 _storage_error="", _generation=2, snapshot=forbidden)
    planner = NS(_admission_lock=threading.Lock(), _foreground_workers=set(),
                 _quarantine=None, diagnostics=forbidden)
    routes = NS(planner=planner, _preview_active=False, _lock=asyncio.Lock(), _generation=4)
    route_planner = NS(_lock=asyncio.Lock(), _state=dict(state="EMPTY", guidance=dict(active=False)),
                       _storage_error="", snapshot=forbidden)
    service = NS(_lock=threading.RLock(), _operation=None, snapshot=forbidden)
    bridge = NS(_lock=threading.RLock(), _operation=None, snapshot=forbidden)
    lifecycle = NS(_service_lifecycle=service, _control_bridge_lifecycle=bridge,
                   _control_bridge_autostart=False, service_snapshot=forbidden)
    return ApplicationRuntime(agent=agent, mapping=mapping, navigation=navigation, slam=slam,
                              dataset_capture=dataset, mission=mission, mission_routes=routes,
                              route_planner=route_planner, lifecycle=lifecycle)


def native_jobs():
    return NS(_lock=threading.RLock(), _active_job_id=None, _jobs={}, _threads={},
              _generation=7, snapshot=forbidden)


def sensor_owner():
    return NS(_lock=threading.RLock(), _state="WAITING_GLOBAL", _generation=9,
              _thread=None, _process=None, _cleanup_complete=None, _capture_id=None,
              _execution_policy=dict(processing_budget_s=None, child_resource_mode="user_scope_v1"),
              _resource_admission=dict(admitted=True, limits=dict(memory_max=2147483648)),
              _cancel=threading.Event(), snapshot=forbidden)


class OwnershipReadbackTests(unittest.TestCase):
    def setUp(self):
        self.runtime = idle_runtime()

    def test_clear_sample_is_advisory_and_preserves_preview_impact(self):
        value = ownership_readback(self.runtime)
        self.assertEqual(value["schema"], SCHEMA)
        self.assertEqual(value["process_id"], os.getpid())
        self.assertTrue(value["sampled_constraints_clear"])
        self.assertFalse(value["restart_authorized"])
        self.assertFalse(value["globally_atomic"])
        self.assertTrue(value["components"]["mapping"]["preview_restart_impact"])
        json.dumps(value, allow_nan=False)

    def test_expired_lease_and_queued_outputs_are_not_expired_or_drained(self):
        manager = self.runtime.agent._control_transport.manager
        manager._lease = dict(token="SECRET_TOKEN", input_source="keyboard", heartbeat_at=-1000.)
        manager._drive = dict(deadman=True, at=-1000.)
        manager._outputs = deque([dict(type="stop", reason="old"), dict(type="drive", velocity={})])
        manager._actions = deque([dict(type="action", action="sit")])
        before = copy.deepcopy((manager._lease, manager._drive, manager._outputs, manager._actions,
                                manager._action_guard_until, manager._motion_active,
                                manager._last_velocity, manager._last_tick))
        with patch.object(manager, "_expire_if_needed", side_effect=forbidden) as expire_lease, \
             patch.object(manager, "_expire_command_if_needed", side_effect=forbidden) as expire_command, \
             patch.object(manager, "drain_outputs", side_effect=forbidden) as drain, \
             patch.object(manager, "snapshot", side_effect=forbidden) as snapshot:
            value = ownership_readback(self.runtime)
        for spy in (expire_lease, expire_command, drain, snapshot):
            spy.assert_not_called()
        self.assertIn("control", value["busy_components"])
        self.assertEqual(before, (manager._lease, manager._drive, manager._outputs, manager._actions,
                                  manager._action_guard_until, manager._motion_active,
                                  manager._last_velocity, manager._last_tick))
        self.assertEqual(value["components"]["control"]["pending_outputs"], 2)
        self.assertNotIn("SECRET_TOKEN", json.dumps(value))

    def test_stale_sensor_owner_is_not_cancelled_or_invalidated(self):
        sensor = self.runtime.sensor_tracking = sensor_owner()
        sensor._state, sensor._capture_id = "SENSOR_CANDIDATE", "retained-capture"
        sensor._context = dict(source_stamp_ns="1", received_monotonic_s=-1000.)
        sensor._source = dict(received_monotonic_s=-1000.)
        sensor._trail = [dict(source_stamp_ns="1", unverified=True)]
        sensor._process = object()
        before = (sensor._state, sensor._generation, sensor._capture_id, sensor._process)
        before_data = copy.deepcopy((sensor._context, sensor._source, sensor._trail))
        with patch.object(sensor._cancel, "set", side_effect=forbidden) as cancel:
            value = ownership_readback(self.runtime)
        self.assertEqual(before, (sensor._state, sensor._generation, sensor._capture_id, sensor._process))
        self.assertEqual(before_data, (sensor._context, sensor._source, sensor._trail))
        self.assertFalse(sensor._cancel.is_set())
        cancel.assert_not_called()
        self.assertIn("sensor_tracking", value["busy_components"])
        self.assertTrue(value["components"]["sensor_tracking"]["capture_retained"])
        self.assertIsNone(value["components"]["sensor_tracking"]["execution_policy"]["processing_budget_s"])

    def test_returned_nested_policy_and_records_do_not_alias_owners(self):
        sensor = self.runtime.sensor_tracking = sensor_owner()
        self.runtime.slam._session = dict(session_id="abc", state="IDLE", unsaved=False, cleanup_required=False)
        value = ownership_readback(self.runtime)
        value["components"]["sensor_tracking"]["resource_admission"]["limits"]["memory_max"] = 0
        value["components"]["slam"]["session"]["state"] = "MAPPING"
        self.assertEqual(sensor._resource_admission["limits"]["memory_max"], 2147483648)
        self.assertEqual(self.runtime.slam._session["state"], "IDLE")

    def test_unsaved_idle_slam_remains_a_blocker_without_adapter_calls(self):
        self.runtime.slam._session = dict(session_id="abc", state="IDLE", unsaved=True, cleanup_required=False)
        self.assertIn("slam", ownership_readback(self.runtime)["busy_components"])

    def test_historical_start_attempt_does_not_make_cleaned_slam_busy(self):
        self.runtime.slam._session = dict(state="IDLE", unsaved=False, cleanup_required=False)
        self.runtime.slam._runtime_start_attempted = True
        self.assertNotIn("slam", ownership_readback(self.runtime)["busy_components"])

    def test_uncertain_camera_reservation_blocks(self):
        self.runtime.slam.camera._reservation_unknown = True
        self.assertIn("slam", ownership_readback(self.runtime)["busy_components"])

    def test_idle_slam_without_unsaved_contract_is_unknown(self):
        self.runtime.slam._session = dict(state="IDLE", cleanup_required=False)
        self.assertIn("slam", ownership_readback(self.runtime)["unknown_components"])

    def test_detached_raw_capture_still_in_flight_blocks_without_expiry(self):
        latch = self.runtime.agent._pointcloud_hub._raw_capture
        latch._record = dict(capture_id="a", state="cancelled", generation=2, capture_active=False)
        latch._in_flight = object()
        latch._generation = 3
        value = ownership_readback(self.runtime)
        self.assertIn("raw_capture", value["busy_components"])
        self.assertEqual(latch._record["state"], "cancelled")
        self.assertEqual(latch._generation, 3)

    def test_native_terminal_job_retains_owner_until_worker_settles(self):
        native = native_jobs()
        native._active_job_id = "a"
        native._jobs["a"] = dict(job_id="a", state="cancelled", cancellation_requested=True)
        global_owner = NS(_lock=threading.RLock(), _active=None, _jobs={}, _threads={},
                          _generation=3, _manager=native, snapshot=forbidden)
        self.runtime.global_observation = global_owner
        value = ownership_readback(self.runtime)
        self.assertIn("global_observation", value["busy_components"])
        self.assertEqual(native._generation, 7)
        self.assertEqual(native._active_job_id, "a")

    def test_navigation_start_and_lease_free_localization_are_copied(self):
        self.runtime.navigation._start.update(pending=True, phase="preflight")
        self.runtime.navigation._localization_session.update(active=True, state="waiting_initial_pose")
        value = ownership_readback(self.runtime)
        self.assertIn("navigation", value["busy_components"])
        self.assertTrue(value["components"]["navigation"]["localization"]["active"])

    def test_failed_navigation_retains_exact_rollback_owner(self):
        self.runtime.navigation._start.update(pending=False, phase="failed", token="PRIVATE_TOKEN")
        value = ownership_readback(self.runtime)
        self.assertIn("navigation", value["busy_components"])
        self.assertTrue(value["components"]["navigation"]["startup"]["token_retained"])
        self.assertNotIn("PRIVATE_TOKEN", json.dumps(value))

    def test_idle_preview_recovery_monitor_is_impact_not_busy_transition(self):
        loop = asyncio.new_event_loop()
        monitor = loop.create_future()
        self.runtime.mapping._preview_recovery_task = monitor
        try:
            value = ownership_readback(self.runtime)
        finally:
            monitor.cancel()
            loop.close()
        self.assertNotIn("mapping", value["busy_components"])
        self.assertTrue(value["components"]["mapping"]["preview_recovery_monitor_active"])

    def test_native_planner_quarantine_and_preview_are_constraints(self):
        self.runtime.mission_routes._preview_active = True
        self.runtime.mission_routes.planner._quarantine = dict(reason="cleanup pending")
        value = ownership_readback(self.runtime)
        self.assertIn("mission_routes", value["busy_components"])
        self.assertTrue(value["components"]["mission_routes"]["cleanup_quarantined"])

    def test_unknown_owner_shape_or_missing_required_owner_blocks(self):
        self.runtime.mapping = object()
        self.runtime.navigation = None
        value = ownership_readback(self.runtime)
        self.assertEqual(set(value["unknown_components"]), {"mapping", "navigation"})
        self.assertFalse(value["sampled_constraints_clear"])

    def test_contended_thread_lock_fails_unknown_without_wait(self):
        lock = threading.Lock()
        lock.acquire()
        self.runtime.mapping._manager._lock = lock
        try:
            value = ownership_readback(self.runtime)
        finally:
            lock.release()
        self.assertIn("mapping", value["unknown_components"])

    def test_custom_copy_hooks_are_never_invoked(self):
        hooks = []
        class Hook:
            def __deepcopy__(self, memo):
                hooks.append("deepcopy")
                raise AssertionError()
            def __reduce__(self):
                hooks.append("reduce")
                raise AssertionError()
        sensor = self.runtime.sensor_tracking = sensor_owner()
        sensor._execution_policy = dict(surprise=Hook())
        value = ownership_readback(self.runtime)
        self.assertEqual(hooks, [])
        self.assertIn("sensor_tracking", value["unknown_components"])

    def test_nonfinite_guard_or_malformed_boolean_is_unknown(self):
        self.runtime.agent._control_transport.manager._action_guard_until = float("nan")
        self.runtime.navigation._start["pending"] = None
        value = ownership_readback(self.runtime)
        self.assertIn("control", value["unknown_components"])
        self.assertIn("navigation", value["unknown_components"])

    def test_dataset_export_and_lifecycle_dispatch_block(self):
        self.runtime.dataset_capture._export_active = True
        self.runtime.lifecycle._service_lifecycle._operation = dict(id="x", action="restart", state="queued")
        value = ownership_readback(self.runtime)
        self.assertIn("dataset", value["busy_components"])
        self.assertIn("lifecycle", value["busy_components"])

    def test_dead_unjoined_thread_bookkeeping_is_not_finalized(self):
        worker = threading.Thread(target=lambda: None)
        worker.start()
        try:
            deadline = time.monotonic() + 2.
            while _thread(worker) and time.monotonic() < deadline:
                time.sleep(.001)
            self.assertFalse(_thread(worker))
            sensor = self.runtime.sensor_tracking = sensor_owner()
            sensor._thread, sensor._cleanup_complete = worker, True
            with patch.object(worker, "is_alive", side_effect=forbidden) as alive:
                before = dict(worker.__dict__)
                started_before = worker._started._flag
                value = ownership_readback(self.runtime)
                self.assertEqual(before, worker.__dict__)
                self.assertEqual(started_before, worker._started._flag)
                alive.assert_not_called()
            self.assertNotIn("sensor_tracking", value["busy_components"])
            self.assertNotIn("sensor_tracking", value["unknown_components"])
        finally:
            worker.join(timeout=2.)

    def test_legacy_unlocked_thread_lifetime_lock_is_read_without_clearing(self):
        # Synthetic CPython 3.10 object layout supplements the actual local
        # CPython 3.13 dead-unjoined-thread test above. It starts no thread.
        worker = threading.Thread()
        worker.__dict__.pop("_handle", None)
        worker._started._flag = True
        worker._is_stopped = False
        worker._tstate_lock = threading.Lock()
        before = dict(worker.__dict__)
        self.assertFalse(_thread(worker))
        self.assertEqual(before, worker.__dict__)


class OwnershipReadbackApiTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, app, path="/api/v1/system/ownership-readback"):
        sent = []
        async def receive():
            return dict(type="http.request", body=b"", more_body=False)
        async def send(message):
            sent.append(message)
        scope = dict(type="http", asgi={"version": "3.0", "spec_version": "2.4"},
                     http_version="1.1", method="GET", scheme="http", path=path,
                     raw_path=path.encode(), query_string=b"", root_path="",
                     server=("testserver", 80), client=("127.0.0.1", 1), headers=[])
        await app(scope, receive, send)
        head = next(row for row in sent if row["type"] == "http.response.start")
        body = b"".join(row.get("body", b"") for row in sent if row["type"] == "http.response.body")
        return head, json.loads(body)

    async def test_new_path_support_schema_pid_and_no_store(self):
        app = FastAPI()
        app.state.runtime = idle_runtime()
        app.include_router(router)
        head, body = await self.request(app)
        self.assertEqual(head["status"], 200)
        self.assertIn((b"cache-control", b"no-store"), head["headers"])
        self.assertEqual(body["schema"], SCHEMA)
        self.assertEqual(body["process_id"], os.getpid())
        self.assertTrue(body["sampled_constraints_clear"])

    async def test_busy_coordination_is_not_waited_or_used_as_idle(self):
        app = FastAPI()
        app.state.runtime = idle_runtime()
        app.include_router(router)
        await app.state.runtime.pipeline_coordination_lock.acquire()
        try:
            head, body = await self.request(app)
        finally:
            app.state.runtime.pipeline_coordination_lock.release()
        self.assertEqual(head["status"], 200)
        self.assertFalse(body["sampled_constraints_clear"])
        self.assertEqual(body["unknown_components"], ["owners_not_sampled"])

    async def test_old_runtime_path_absence_fails_404(self):
        head, _ = await self.request(FastAPI())
        self.assertEqual(head["status"], 404)

    async def test_unlocked_but_queued_non_cancelled_waiter_is_not_bypassed(self):
        app = FastAPI()
        app.state.runtime = idle_runtime()
        app.include_router(router)
        waiter = asyncio.get_running_loop().create_future()
        waiter.set_result(True)
        app.state.runtime.pipeline_coordination_lock._waiters = deque([waiter])
        head, body = await self.request(app)
        self.assertEqual(head["status"], 200)
        self.assertFalse(body["sampled_constraints_clear"])
        self.assertEqual(body["busy_components"], ["pipeline_coordination"])


class ConcreteOwnerContractTests(unittest.TestCase):
    def test_actual_constructors_support_pure_readback_without_starting_work(self):
        # Constructors create only private test storage. None of the start,
        # capture, timer, ROS setup, provider or service methods is invoked.
        from robot_dashboard.application.global_observation import GlobalObservationCoordinator
        from robot_dashboard.application.lifecycle_coordinator import LifecycleCoordinator
        from robot_dashboard.application.mapping_coordinator import MappingCoordinator
        from robot_dashboard.application.mission_coordinator import MissionCoordinator
        from robot_dashboard.application.navigation_coordinator import NavigationCoordinator
        from robot_dashboard.application.route_planner_coordinator import RoutePlannerCoordinator
        from robot_dashboard.application.sensor_tracking import SensorTrackingOwner
        from robot_dashboard.control_bridge_lifecycle import ControlBridgeLifecycleManager
        from robot_dashboard.dataset_capture import DatasetCaptureManager
        from robot_dashboard.mapping_jobs import MappingJobManager, CommandSpec
        from robot_dashboard.mission_routes.context import NavigationContext
        from robot_dashboard.mission_routes.planner import NativePlanner
        from robot_dashboard.mission_routes.service import MissionRoutes
        from robot_dashboard.navigation_jobs import NavigationJobManager, NavigationCommandSpec
        from robot_dashboard.relocalization.manager import StationaryRelocalizationManager
        from robot_dashboard.relocalization.sensor_tracking_process import SensorTrackingExecutionPolicy
        # Reuse the existing offline ROS import stubs; the production
        # ControlTransport constructor itself is unchanged and is not set up.
        from test_ros_control_transport import ControlTransport
        from robot_dashboard.ros.navigation_gateway import NavigationRosGateway
        from robot_dashboard.ros.pointcloud import PointCloudHub
        from robot_dashboard.service_lifecycle import ServiceLifecycleManager
        from robot_dashboard.slam_broker import BrokerIsaacAdapter
        from robot_dashboard.slam_packages import MapPackageStore
        from robot_dashboard.slam_sessions import SlamSessionManager

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            lock = asyncio.Lock()
            control = ControlTransport({}, environ={})
            gateway = NavigationRosGateway(control, node_getter=lambda: None,
                                           tick=forbidden, graph_getter=forbidden)
            agent = NS(_control_transport=control, _navigation_gateway=gateway,
                       _pointcloud_hub=PointCloudHub(threading.RLock(), max_points=1000,
                                                   radius_limit_m=10., frame_interval_s=.1))
            mapping_jobs = MappingJobManager(project_dir=root, output_dir=root / "maps",
                start_command=CommandSpec(("/usr/bin/false",)), save_commands={})
            mapping = MappingCoordinator(mapping_jobs, NS(), coordination_lock=lock,
                navigation_active=forbidden, control_lease_active=forbidden,
                dataset_capture_active=forbidden, require_lifecycle_idle=forbidden)
            nav_jobs = NavigationJobManager(project_dir=root, runtime_dir=root / "nav",
                base_parameters_file=Path(__file__).resolve().parents[1] / "config/nav2_go2.yaml",
                start_command=NavigationCommandSpec(("/usr/bin/false", "{params_file}", "{map_yaml}")),
                map_snapshotter=forbidden)
            navigation = NavigationCoordinator(agent, nav_jobs, mapping, NS(),
                coordination_lock=lock, require_lifecycle_idle=forbidden)
            broker = BrokerIsaacAdapter(root / "unused-broker.sock")
            slam = SlamSessionManager({}, MapPackageStore(root / "packages"),
                coordination_lock=lock, blockers=forbidden, navigation_context=forbidden,
                camera=broker.camera_coordinator)
            dataset = DatasetCaptureManager(root / "datasets", camera_open=forbidden,
                camera_close=forbidden, camera_snapshots=forbidden)
            mission = MissionCoordinator(navigation, NS(), root / "mission", coordination_lock=lock)
            routes = MissionRoutes(root / "routes", NS(), NS(), mission,
                NavigationContext(navigation), NativePlanner(enabled=False))
            route_planner = RoutePlannerCoordinator(NS(), mission, root / "planner",
                navigation_view=forbidden, mapping_activity=forbidden, perception=NS(),
                allow_rehearsal=False)
            service = ServiceLifecycleManager(enabled=False, blocker_provider=forbidden,
                command_runner=forbidden, executable_probe=lambda path: False)
            bridge = ControlBridgeLifecycleManager(enabled=False, preflight_provider=forbidden,
                bridge_status_provider=forbidden, mutation_runner=forbidden,
                status_runner=forbidden, executable_probe=lambda path: False)
            lifecycle = LifecycleCoordinator(control_snapshot_provider=forbidden,
                navigation_runtime_snapshot_provider=forbidden, navigation_jobs_snapshot_provider=forbidden,
                mapping_jobs_snapshot_provider=forbidden, mapping_task_active_provider=forbidden,
                navigation_start_snapshot_provider=forbidden, dataset_capture_active_provider=forbidden,
                service_lifecycle=service, control_bridge_lifecycle=bridge,
                control_bridge_autostart=False)
            global_owner = GlobalObservationCoordinator(NS(), agent, NS(status=forbidden))
            policy = SensorTrackingExecutionPolicy(processing_budget_s=None).snapshot()
            policy["resource_mode"] = "user_scope_v1"
            sensor = SensorTrackingOwner(NS(), agent, global_owner, forbidden, execution_policy=policy)
            relocalization = StationaryRelocalizationManager(root / "relocalization",
                snapshotter=forbidden, current_checker=forbidden, collector=forbidden,
                registration=forbidden, safety_provider=forbidden)
            runtime = ApplicationRuntime(agent=agent, mapping=mapping, navigation=navigation,
                slam=slam, dataset_capture=dataset, mission=mission, mission_routes=routes,
                route_planner=route_planner, lifecycle=lifecycle, global_observation=global_owner,
                sensor_tracking=sensor, relocalization=relocalization,
                pipeline_coordination_lock=lock)
            with patch("subprocess.Popen", side_effect=forbidden), patch("subprocess.run", side_effect=forbidden):
                value = ownership_readback(runtime)
            self.assertEqual(value["unknown_components"], [], value)
            self.assertTrue(value["sampled_constraints_clear"], value)
            self.assertEqual(value["components"]["sensor_tracking"]["execution_policy"], policy)
            token = navigation.begin_start()
            navigation.finish_start_failure(token, "synthetic cleanup failure", cleanup_complete=False)
            value = ownership_readback(runtime)
            self.assertIn("navigation", value["busy_components"])
            self.assertTrue(value["components"]["navigation"]["startup"]["token_retained"])


if __name__ == "__main__":
    unittest.main()
