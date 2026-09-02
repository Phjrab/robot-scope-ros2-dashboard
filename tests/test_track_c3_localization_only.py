import asyncio
import math
import threading
import time
import types
import unittest

from robot_dashboard.application.mission_coordinator import MissionConflict
from robot_dashboard.application.navigation_coordinator import NavigationCoordinator
from robot_dashboard.control import (
    CommandValidationError,
    ControlManager,
    ControlNotReady,
    LeaseBusy,
)
from robot_dashboard.navigation_jobs import (
    NavigationBusy,
    NavigationConflict,
    NavigationPoseError,
)
from robot_dashboard.ros.navigation_gateway import (
    NAVIGATION_CLEAR_SERVICES,
    NAVIGATION_CONTROLLER_ODOM_TOPIC,
    NAVIGATION_FAST_LIO_ODOM_TOPIC,
    NAVIGATION_RUNTIME_HEALTH_TOPIC,
    NavigationRosGateway,
)


MAP_ID = "97bae189b35182c688cecb3c"
MAP_REVISION = "60becc42ecb58aca30834c92ed4778e0a38d31562950524a5871808d225ae4ae"
PARAMETERS_REVISION = "a" * 64
MAPPING_JOB_ID = "b" * 32
NAVIGATION_JOB_ID = "c" * 32


class FakeAgent:
    def __init__(self):
        self.events = []
        self.localization_failure_callback = None
        self.control = {"lease": {"active": False, "input_source": None}}
        self.runtime = {
            "seq": 1,
            "available": True,
            "robot_online": False,
            "active": False,
            "cleanup_required": False,
            "readiness": {
                "map_server": True,
                "localization": False,
                "planner": False,
                "controller": True,
                "behavior": False,
                "cmd_bridge": False,
                "map": True,
                "scan": True,
                "odometry": True,
                "tf": True,
            },
            "safety": {
                "can_start": False,
                "can_set_initial_pose": False,
                "can_send_goal": False,
                "can_start_localization_only": True,
                "can_set_localization_only_initial_pose": False,
                "blockers": [],
            },
            "localization": {"state": "uninitialized", "pose": None},
            "localization_session": {
                "active": False,
                "mode": "localization_only",
                "state": "idle",
                "initial_pose_count": 0,
                "goal_allowed": False,
                "motion_allowed": False,
            },
            "goal": {"state": "idle", "recoveries": 0},
            "bindings": {
                "navigation_profile": "go2-xt16-wireless-competition-fastlio",
                "controller_odometry": "/robot_scope/nav/controller_odom_fastlio",
            },
        }

    def control_snapshot(self):
        return self.control

    def navigation_runtime_snapshot(self):
        return self.runtime

    def navigation_prelocalization_snapshot(self, *, ready_after):
        self.events.append(("prelocalization", ready_after))
        return {"ready": True, "reason": None}

    def navigation_localization_only_preflight(self):
        self.events.append("localization_preflight")
        if self.control["lease"]["active"]:
            raise LeaseBusy("control lease is active")
        return {"ready": True, "lease_active": False}

    def navigation_set_localization_failure_callback(self, callback):
        self.localization_failure_callback = callback

    def navigation_start_preflight(self):
        self.events.append("navigation_preflight")

    def navigation_activate_localization_only(self, **kwargs):
        self.events.append(("localization_activate", kwargs["map_id"]))
        self.runtime["cleanup_required"] = True
        self.runtime["localization_session"] = {
            "active": True,
            "mode": "localization_only",
            "state": "waiting_initial_pose",
            "map_id": kwargs["map_id"],
            "map_revision": kwargs["map_revision"],
            "initial_pose_count": 0,
            "initial_pose": None,
            "goal_allowed": False,
            "motion_allowed": False,
            "raw_command_count": 0,
            "zero_command_count": 0,
            "nonzero_command_count": 0,
        }
        self.runtime["safety"]["can_set_localization_only_initial_pose"] = True
        return self.runtime

    def navigation_deactivate_localization_only(self, *, reason):
        self.events.append(("localization_deactivate", reason))
        self.runtime["cleanup_required"] = False
        self.runtime["localization_session"]["active"] = False
        self.runtime["localization_session"]["state"] = "idle"
        return self.runtime

    def navigation_set_localization_only_initial_pose(self, **kwargs):
        self.events.append(("localization_pose", kwargs))
        session = self.runtime["localization_session"]
        session.update(
            state="localizing",
            initial_pose_count=1,
            initial_pose={key: kwargs[key] for key in ("x", "y", "yaw")},
        )
        self.runtime["localization"] = {
            "state": "localizing",
            "pose": session["initial_pose"],
        }
        return self.runtime

    def navigation_activate(self, **kwargs):
        self.events.append(("navigation_activate", kwargs["map_id"]))
        self.runtime["active"] = True
        return self.runtime

    def navigation_deactivate(self, *, reason):
        self.events.append(("navigation_deactivate", reason))
        self.runtime["active"] = False
        return self.runtime

    def navigation_set_initial_pose(self, **kwargs):
        self.events.append(("navigation_pose", kwargs))
        return self.runtime

    def navigation_send_goal(self, **kwargs):
        self.events.append(("goal", kwargs))
        return self.runtime

    def navigation_cancel_goal(self, *, goal_id):
        self.events.append(("cancel", goal_id))
        return self.runtime

    def navigation_clear_costmaps(self, *, scope):
        self.events.append(("clear", scope))
        return self.runtime


class FakeJobs:
    def __init__(self):
        self.on_terminal = None
        self.state = "idle"
        self.job_id = None
        self.map = None
        self.events = []

    def snapshot(self):
        return {
            "seq": len(self.events),
            "available": True,
            "parameters_revision": PARAMETERS_REVISION,
            "navigation_profile": "go2-xt16-wireless-competition-fastlio",
            "controller_odometry_topic": "/robot_scope/nav/controller_odom_fastlio",
            "pipeline": {
                "state": self.state,
                "job_id": self.job_id,
                "error": None,
                "started_at": None,
            },
            "map": self.map,
        }

    def progress_snapshot(self, *, after=0, limit=80):
        return {"after": after, "limit": limit, "entries": []}

    def parameters_snapshot(self):
        return {"revision": PARAMETERS_REVISION, "values": {"robot_radius": 0.22}}

    def update_parameters(self, base_revision, patch):
        del base_revision, patch
        return self.parameters_snapshot()

    def start(self, *, map_id, map_revision, parameters_revision):
        if parameters_revision != PARAMETERS_REVISION:
            raise NavigationConflict("parameters changed")
        self.events.append("jobs_start")
        self.state = "running"
        self.job_id = NAVIGATION_JOB_ID
        self.map = {
            "id": map_id,
            "revision": map_revision,
            "name": "map_20260813_125411",
            "frame_id": "map",
        }
        return self.snapshot()

    def stop(self):
        self.events.append("jobs_stop")
        self.state = "idle"
        self.job_id = None
        self.map = None
        return self.snapshot()

    def validate_active_pose(self, *, map_id, map_revision, x, y, yaw):
        if self.state != "running":
            raise NavigationConflict("pipeline is not running")
        if map_id != MAP_ID or map_revision != MAP_REVISION:
            raise NavigationConflict("pose map mismatch")
        values = (float(x), float(y), float(yaw))
        if not all(math.isfinite(value) for value in values):
            raise NavigationPoseError("pose must be finite")
        if x < 0.0:
            raise NavigationPoseError(
                "pose must be inside known-free map space with robot-radius clearance"
            )
        return {"x": values[0], "y": values[1], "yaw": values[2]}

    def close(self):
        self.events.append("jobs_close")
        self.stop()


class FakeMapping:
    def __init__(self):
        self.state = "idle"
        self.job_id = None
        self.events = []

    def activity(self):
        return False, []

    def pipeline_state(self):
        return self.state

    def snapshot(self, *, since_log_seq=0):
        del since_log_seq
        return {"pipeline": {"state": self.state, "job_id": self.job_id}}

    def start_mapping(self):
        self.events.append("mapping_start")
        self.state = "running"
        self.job_id = MAPPING_JOB_ID
        return self.snapshot()

    def stop_mapping_if_job_id(self, job_id):
        self.events.append(("mapping_stop", job_id))
        if self.job_id == job_id:
            self.state = "idle"
            self.job_id = None
        return True, self.snapshot()


class FakeMaps:
    def resolve_navigation_map(self, map_id, revision):
        if map_id != MAP_ID or revision != MAP_REVISION:
            raise NavigationConflict("map revision mismatch")
        return types.SimpleNamespace(
            map_id=map_id,
            revision=revision,
            name="map_20260813_125411",
        )

    def resolve_annotation_goal(self, *_args):
        raise AssertionError("annotation goal must remain closed")


class LocalizationCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.agent = FakeAgent()
        self.jobs = FakeJobs()
        self.mapping = FakeMapping()
        self.coordinator = NavigationCoordinator(
            self.agent,
            self.jobs,
            self.mapping,
            FakeMaps(),
            coordination_lock=asyncio.Lock(),
            require_lifecycle_idle=lambda: None,
            poll_interval_s=0.001,
        )

    async def start_session(self):
        result = await self.coordinator.start_localization_only(
            map_id=MAP_ID,
            map_revision=MAP_REVISION,
            parameters_revision=PARAMETERS_REVISION,
        )
        self.assertTrue(result["accepted"])
        task = self.coordinator.start_task
        self.assertIsNotNone(task)
        await task

    async def test_start_is_lease_free_and_separate_from_navigation(self):
        await self.start_session()
        view = self.coordinator.view()
        session = view["localization_session"]
        self.assertEqual(session["state"], "waiting_initial_pose")
        self.assertEqual(session["map_id"], MAP_ID)
        self.assertFalse(session["goal_allowed"])
        self.assertFalse(session["motion_allowed"])
        self.assertFalse(self.agent.control["lease"]["active"])
        self.assertNotIn("navigation_activate", [event[0] for event in self.agent.events if isinstance(event, tuple)])
        self.assertTrue(self.coordinator.manual_control_blocked())

    async def test_start_rejects_parameter_and_map_revision_mismatch(self):
        with self.assertRaises(NavigationConflict):
            await self.coordinator.start_localization_only(
                map_id=MAP_ID,
                map_revision=MAP_REVISION,
                parameters_revision="d" * 64,
            )
        with self.assertRaises(NavigationConflict):
            await self.coordinator.start_localization_only(
                map_id=MAP_ID,
                map_revision="e" * 64,
                parameters_revision=PARAMETERS_REVISION,
            )

    async def test_initial_pose_requires_session_confirmation_and_free_clearance(self):
        with self.assertRaises(NavigationPoseError):
            await self.coordinator.set_localization_only_initial_pose(
                map_id=MAP_ID,
                map_revision=MAP_REVISION,
                x=1.0,
                y=1.0,
                yaw=0.0,
                confirmed=False,
            )
        with self.assertRaisesRegex(NavigationBusy, "session is not active"):
            await self.coordinator.set_localization_only_initial_pose(
                map_id=MAP_ID,
                map_revision=MAP_REVISION,
                x=1.0,
                y=1.0,
                yaw=0.0,
                confirmed=True,
            )
        await self.start_session()
        with self.assertRaises(NavigationPoseError):
            await self.coordinator.set_localization_only_initial_pose(
                map_id=MAP_ID,
                map_revision=MAP_REVISION,
                x=-1.0,
                y=1.0,
                yaw=0.0,
                confirmed=True,
            )

    async def test_initial_pose_is_exactly_once_and_goal_remains_closed(self):
        await self.start_session()
        result = await self.coordinator.set_localization_only_initial_pose(
            map_id=MAP_ID,
            map_revision=MAP_REVISION,
            x=1.0,
            y=2.0,
            yaw=0.25,
            confirmed=True,
        )
        self.assertTrue(result["accepted"])
        self.assertEqual(
            self.coordinator.view()["localization_session"]["initial_pose_count"],
            1,
        )
        with self.assertRaises(NavigationConflict):
            await self.coordinator.set_localization_only_initial_pose(
                map_id=MAP_ID,
                map_revision=MAP_REVISION,
                x=1.0,
                y=2.0,
                yaw=0.25,
                confirmed=True,
            )
        with self.assertRaisesRegex(NavigationConflict, "unavailable"):
            await self.coordinator.send_goal(
                map_id=MAP_ID,
                map_revision=MAP_REVISION,
                x=1.0,
                y=2.0,
                yaw=0.25,
                confirmed=True,
            )

    async def test_stop_reverse_cleans_exact_owned_processes(self):
        await self.start_session()
        await self.coordinator.stop_localization_only()
        self.assertEqual(self.jobs.state, "idle")
        self.assertEqual(self.mapping.state, "idle")
        self.assertFalse(self.coordinator.view()["localization_session"]["active"])
        self.assertIn(("localization_deactivate", "localization_stop"), self.agent.events)
        self.assertNotIn("navigation_deactivate", [event[0] for event in self.agent.events if isinstance(event, tuple)])
        with self.assertRaisesRegex(NavigationBusy, "session is not active"):
            await self.coordinator.set_localization_only_initial_pose(
                map_id=MAP_ID,
                map_revision=MAP_REVISION,
                x=1.0,
                y=2.0,
                yaw=0.0,
                confirmed=True,
            )

    async def test_runtime_failure_reverse_cleans_without_motion_output(self):
        await self.start_session()
        self.assertIsNotNone(self.agent.localization_failure_callback)
        self.agent.localization_failure_callback("non-zero raw command observed")
        view = self.coordinator.view()
        self.assertFalse(view["localization_session"]["active"])
        self.assertEqual(self.jobs.state, "idle")
        self.assertEqual(self.mapping.state, "idle")
        self.assertNotIn(
            "navigation_deactivate",
            [event[0] for event in self.agent.events if isinstance(event, tuple)],
        )


class FakeClock:
    def now(self):
        nanoseconds = int(time.time() * 1_000_000_000)
        return types.SimpleNamespace(
            nanoseconds=nanoseconds,
            to_msg=lambda: types.SimpleNamespace(
                sec=nanoseconds // 1_000_000_000,
                nanosec=nanoseconds % 1_000_000_000,
            ),
        )


class FakeNode:
    def __init__(self, publisher_count=1):
        self.publisher_count = publisher_count

    def count_publishers(self, _topic):
        return self.publisher_count

    def get_clock(self):
        return FakeClock()


class PoseMessage:
    def __init__(self):
        self.header = types.SimpleNamespace(frame_id="", stamp=None)
        self.pose = types.SimpleNamespace(
            pose=types.SimpleNamespace(
                position=types.SimpleNamespace(x=0.0, y=0.0, z=0.0),
                orientation=types.SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
            ),
            covariance=[],
        )


class RecorderPublisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


class LocalizationGatewayTests(unittest.TestCase):
    def setUp(self):
        self.outputs = []
        self.drives = []
        self.manager = ControlManager(
            {"name": "Unitree Go2", "control": {"enabled": True}},
            environ={"ROBOT_SCOPE_CONTROL_ENABLED": "1"},
            token_factory=lambda: "track-c3-control-token-long-enough",
        )
        original_submit = self.manager.submit_drive

        def submit_drive(*args, **kwargs):
            self.drives.append((args, kwargs))
            return original_submit(*args, **kwargs)

        self.manager.submit_drive = submit_drive
        self.node = FakeNode()
        control_port = types.SimpleNamespace(
            manager=self.manager,
            operation_lock=threading.RLock(),
            flush_outputs=lambda: None,
            publish_outputs=lambda outputs: self.outputs.extend(outputs),
            ensure_target=lambda: None,
            go2_target=lambda: True,
        )
        self.gateway = NavigationRosGateway(
            control_port,
            node_getter=lambda: self.node,
            tick=lambda *_: None,
            graph_getter=lambda: {},
        )
        self.publisher = RecorderPublisher()
        self.gateway._navigation_cmd_subscription = object()
        self.gateway._navigation_health_subscriptions = {
            "/scan": object(),
            NAVIGATION_FAST_LIO_ODOM_TOPIC: object(),
            NAVIGATION_CONTROLLER_ODOM_TOPIC: object(),
            "/amcl_pose": object(),
            NAVIGATION_RUNTIME_HEALTH_TOPIC: object(),
        }
        self.gateway._navigation_initial_pose_publisher = self.publisher
        self.gateway._navigation_pose_type = PoseMessage
        self.gateway._navigation_action_type = object()
        self.gateway._navigation_action_client = types.SimpleNamespace(
            server_is_ready=lambda: False
        )
        self.gateway._navigation_clear_service_type = object()
        self.gateway._navigation_clear_clients = {
            service: types.SimpleNamespace(service_is_ready=lambda: False)
            for service in NAVIGATION_CLEAR_SERVICES
        }
        now = time.monotonic()
        self.gateway._navigation_runtime_health_received = now
        self.gateway._navigation_runtime_health = {
            "ready": False,
            "cloud_fresh": True,
            "odom_fresh": True,
            "localized": False,
            "error": None,
        }
        for topic in (
            "/scan",
            NAVIGATION_FAST_LIO_ODOM_TOPIC,
            NAVIGATION_CONTROLLER_ODOM_TOPIC,
        ):
            self.gateway._navigation_validated_receipts[topic] = now

    def activate(self):
        return self.gateway.activate_localization_only(
            map_id=MAP_ID,
            map_revision=MAP_REVISION,
            map_name="map_20260813_125411",
        )

    def test_activation_never_acquires_control_lease(self):
        snapshot = self.activate()
        self.assertTrue(snapshot["localization_session"]["active"])
        self.assertFalse(snapshot["navigation_lease_active"])
        self.assertFalse(self.manager.snapshot()["lease"]["active"])
        with self.assertRaises(LeaseBusy):
            self.gateway.start_preflight()

    def test_initial_pose_publishes_exactly_once_with_fixed_frame(self):
        self.activate()
        result = self.gateway.set_localization_only_initial_pose(
            map_id=MAP_ID,
            map_revision=MAP_REVISION,
            x=1.0,
            y=2.0,
            yaw=0.5,
        )
        self.assertEqual(len(self.publisher.messages), 1)

        self.gateway._navigation_localization_callback(PoseMessage())
        self.gateway._navigation_runtime_health_callback(
            types.SimpleNamespace(data='{"ready":true}')
        )
        self.assertEqual(len(self.publisher.messages), 1)
        self.assertEqual(self.publisher.messages[0].header.frame_id, "map")
        self.assertEqual(result["localization_session"]["initial_pose_count"], 1)
        with self.assertRaises(CommandValidationError):
            self.gateway.set_localization_only_initial_pose(
                map_id=MAP_ID,
                map_revision=MAP_REVISION,
                x=1.0,
                y=2.0,
                yaw=0.5,
            )
        self.assertEqual(len(self.publisher.messages), 1)

    def test_map_mismatch_and_stale_inputs_fail_closed(self):
        self.activate()
        with self.assertRaises(CommandValidationError):
            self.gateway.set_localization_only_initial_pose(
                map_id=MAP_ID,
                map_revision="f" * 64,
                x=1.0,
                y=2.0,
                yaw=0.0,
            )
        self.gateway.deactivate_localization_only()
        self.gateway._navigation_runtime_health_received = time.monotonic() - 2.0
        with self.assertRaises(ControlNotReady):
            self.gateway.activate_localization_only(
                map_id=MAP_ID,
                map_revision=MAP_REVISION,
            )

    def test_nonzero_command_is_recorded_and_never_reaches_control(self):
        failures = []
        self.gateway.set_localization_failure_callback(failures.append)
        self.activate()
        message = types.SimpleNamespace(
            linear=types.SimpleNamespace(x=0.1, y=0.0),
            angular=types.SimpleNamespace(z=0.0),
        )
        self.gateway._navigation_cmd_vel_callback(message)
        session = self.gateway.runtime_snapshot()["localization_session"]
        self.assertFalse(session["active"])
        self.assertEqual(session["nonzero_command_count"], 1)
        self.assertEqual(len(failures), 1)
        self.assertIn("non-zero Nav2 velocity", failures[0])
        self.assertEqual(self.drives, [])
        self.assertEqual(self.outputs, [])

    def test_localization_callback_updates_only_one_owned_session(self):
        self.activate()
        self.gateway._localization_only["state"] = "localizing"
        message = PoseMessage()
        message.pose.pose.position.x = 1.0
        message.pose.pose.position.y = 2.0
        self.gateway._navigation_localization_callback(message)
        snapshot = self.gateway.runtime_snapshot()
        self.assertEqual(snapshot["localization_session"]["state"], "localized")
        self.assertEqual(snapshot["localization"]["state"], "localized")
        self.assertFalse(self.manager.snapshot()["lease"]["active"])

    def test_foreign_localization_publisher_fails_session(self):
        self.activate()
        self.node.publisher_count = 2
        self.gateway._navigation_localization_callback(PoseMessage())
        session = self.gateway.runtime_snapshot()["localization_session"]
        self.assertFalse(session["active"])
        self.assertEqual(session["state"], "failed")
        self.assertIn("expected one localization", session["error"])


class MissionLocalizationInterlockTests(unittest.IsolatedAsyncioTestCase):
    async def test_mission_ready_check_rejects_localization_only(self):
        navigation = types.SimpleNamespace(
            view=lambda: {"localization_session": {"active": True}}
        )
        from robot_dashboard.application.mission_coordinator import MissionCoordinator

        with self.assertRaises(MissionConflict):
            MissionCoordinator._navigation_ready(
                types.SimpleNamespace(_navigation=navigation),
                {"map_id": MAP_ID, "map_revision": MAP_REVISION},
            )
if __name__ == "__main__":
    unittest.main()
