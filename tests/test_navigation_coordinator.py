import ast
import asyncio
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from robot_dashboard.application.navigation_coordinator import NavigationCoordinator
from robot_dashboard.mapping_jobs import MappingJobError
from robot_dashboard.navigation_jobs import (
    NavigationBusy,
    NavigationPoseError,
)


ROOT = Path(__file__).resolve().parents[1]
COORDINATOR_PATH = (
    ROOT / "robot_dashboard" / "application" / "navigation_coordinator.py"
)


class FakeAgent:
    def __init__(self):
        self.events = []
        self.active = False
        self.preflight_ready = True
        self.activation_entered = threading.Event()
        self.activation_release = threading.Event()
        self.block_activation = False
        self.fail_deactivate = False
        self.runtime_error = False
        self.runtime = {
            "seq": 4,
            "available": True,
            "robot_online": True,
            "active": False,
            "cleanup_required": False,
            "map": None,
            "navigation_lease_active": False,
            "readiness": {
                "map_server": True,
                "localization": True,
                "planner": True,
                "controller": True,
                "behavior": True,
                "cmd_bridge": True,
                "map": True,
                "scan": True,
                "odometry": True,
                "tf": True,
                "action_server": True,
                "cmd_vel_publishers": 1,
                "scan_publishers": 1,
                "odometry_publishers": 1,
                "controller_odometry_publishers": 1,
                "runtime_health_publishers": 1,
                "localization_publishers": 1,
            },
            "safety": {
                "can_start": True,
                "can_set_initial_pose": True,
                "can_send_goal": True,
                "blockers": [],
            },
            "localization": {"state": "localized", "pose": None},
            "goal": {"state": "idle", "recoveries": 0},
        }
        self.control = {
            "lease": {"active": False, "input_source": None},
        }

    def control_snapshot(self):
        self.events.append("control_snapshot")
        return self.control

    def navigation_runtime_snapshot(self):
        self.events.append("runtime_snapshot")
        if self.runtime_error:
            raise RuntimeError("runtime unavailable")
        return dict(self.runtime)

    def navigation_prelocalization_snapshot(self, *, ready_after):
        self.events.append(("readiness", ready_after))
        return {
            "ready": self.preflight_ready,
            "reason": "waiting for fresh receipts",
        }

    def navigation_start_preflight(self):
        self.events.append("preflight")

    def navigation_activate(self, **kwargs):
        self.events.append(("activate", kwargs["map_id"]))
        self.activation_entered.set()
        if self.block_activation:
            self.activation_release.wait(timeout=2.0)
        self.active = True
        self.runtime["active"] = True
        self.runtime["map"] = {
            "id": kwargs["map_id"],
            "revision": kwargs["map_revision"],
        }
        self.runtime["navigation_lease_active"] = True
        return {}

    def navigation_deactivate(self, *, reason):
        self.events.append(("deactivate", reason))
        self.active = False
        self.runtime["active"] = False
        self.runtime["map"] = None
        self.runtime["navigation_lease_active"] = False
        if self.fail_deactivate:
            raise RuntimeError("robot transport unavailable")
        return {}

    def navigation_set_initial_pose(self, **kwargs):
        self.events.append(("initial_pose", kwargs))
        return {}

    def navigation_send_goal(self, **kwargs):
        self.events.append(("goal", kwargs))
        self.runtime["goal"] = {
            "state": "active",
            "goal_id": "goal-1",
            "recoveries": 0,
        }
        return {}

    def navigation_cancel_goal(self, *, goal_id):
        self.events.append(("cancel", goal_id))
        return {}

    def navigation_clear_costmaps(self, *, scope):
        self.events.append(("clear", scope))
        return {}


class FakeNavigationJobs:
    def __init__(self):
        self.on_terminal = None
        self.events = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.fail_start = False
        self.fail_snapshot = False
        self.fail_stop = False
        self.pipeline_state = "idle"
        self.job_id = None
        self.available = True
        self.parameters_revision = "c" * 64
        self.map = None
        self.seq = 3
        self.pipeline_error = None

    def snapshot(self):
        if self.fail_snapshot:
            raise RuntimeError("snapshot unavailable")
        return {
            "seq": self.seq,
            "available": self.available,
            "pipeline": {
                "state": self.pipeline_state,
                "job_id": self.job_id,
                "error": self.pipeline_error,
                "started_at": "2026-01-01T00:00:00Z" if self.job_id else None,
            },
            "map": self.map,
            "parameters_revision": self.parameters_revision,
            "command_topic": "/robot_scope/nav/cmd_vel_raw",
        }

    def progress_snapshot(self, *, after=0, limit=80):
        return {"cursor": after, "limit": limit}

    def parameters_snapshot(self):
        return {"revision": self.parameters_revision}

    def update_parameters(self, base_revision, patch):
        self.events.append(("parameters", base_revision, dict(patch)))
        return {"revision": base_revision, "values": dict(patch)}

    def start(self, *, map_id, map_revision, parameters_revision):
        self.events.append("start")
        self.pipeline_state = "starting"
        self.job_id = "b" * 32
        self.entered.set()
        self.release.wait(timeout=2.0)
        if self.fail_start:
            self.pipeline_state = "failed"
            raise RuntimeError("start failed after publishing job")
        self.pipeline_state = "running"
        self.map = {
            "id": map_id,
            "revision": map_revision,
            "name": "classroom",
        }
        return self.snapshot()

    def stop(self):
        self.events.append("stop")
        self.pipeline_state = "idle"
        self.job_id = None
        self.map = None
        if self.fail_stop:
            raise NavigationBusy("manager stop failed")
        return self.snapshot()

    def validate_active_pose(self, **kwargs):
        self.events.append(("validate_pose", kwargs["map_id"]))
        return {
            "x": float(kwargs["x"]),
            "y": float(kwargs["y"]),
            "yaw": float(kwargs["yaw"]),
        }

    def close(self):
        self.events.append("close")
        self.pipeline_state = "idle"
        self.job_id = None
        self.map = None


class FakeMappingCoordinator:
    def __init__(self):
        self.events = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.state = "idle"
        self.job_id = "a" * 32
        self.operation_state = "idle"
        self.task_busy = False
        self.fail_start = False
        self.cleanup_error = False

    def activity(self):
        blockers = []
        if self.task_busy or self.operation_state in {"saving", "stopping"}:
            blockers.append("mapping_operation_active")
        if self.state in {"starting", "stopping"}:
            blockers.append("mapping_transition")
        blockers = list(dict.fromkeys(blockers))
        return bool(blockers), blockers

    def pipeline_state(self):
        if self.state == "stopped":
            return "idle"
        return self.state

    def snapshot(self, *, since_log_seq=0):
        del since_log_seq
        return {
            "pipeline": {"state": self.state, "job_id": self.job_id},
            "operation": {"state": self.operation_state},
        }

    def start_mapping(self):
        self.events.append("start_mapping")
        self.state = "starting"
        if self.job_id is None:
            self.job_id = "a" * 32
        self.entered.set()
        self.release.wait(timeout=2.0)
        if self.fail_start:
            self.state = "failed"
            raise MappingJobError("mapping launcher failed")
        self.state = "running"
        return self.snapshot()

    def stop_mapping_if_job_id(self, job_id):
        self.events.append(("stop_mapping", job_id))
        if self.cleanup_error:
            raise MappingJobError("mapping cleanup failed")
        if job_id == self.job_id and self.state in {"starting", "running", "stopping"}:
            self.state = "stopped"
            return True, self.snapshot()
        return False, self.snapshot()


class FakeSavedMaps:
    def __init__(self):
        self.calls = []

    def resolve_navigation_map(self, map_id, revision):
        self.calls.append((map_id, revision))
        return SimpleNamespace(map_id=map_id, revision=revision, name="classroom")

    def resolve_annotation_goal(
        self,
        map_id,
        map_revision,
        annotation_revision,
        annotation_id,
    ):
        self.calls.append(
            (
                "annotation_goal",
                map_id,
                map_revision,
                annotation_revision,
                annotation_id,
            )
        )
        return SimpleNamespace(
            annotation_id=annotation_id,
            annotation_type="POI",
            name="Inspection A",
            x=3.0,
            y=4.0,
            yaw=0.5,
        )


class FakeLogger:
    def __init__(self):
        self.events = []

    def exception(self, message, *args):
        self.events.append(("exception", message, args))

    def warning(self, message, *args):
        self.events.append(("warning", message, args))


class NavigationCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = FakeAgent()
        self.jobs = FakeNavigationJobs()
        self.mapping = FakeMappingCoordinator()
        self.catalog = FakeSavedMaps()
        self.logger = FakeLogger()
        self.lock = asyncio.Lock()
        self.lifecycle_calls = 0

        def lifecycle_gate():
            self.lifecycle_calls += 1

        self.coordinator = NavigationCoordinator(
            self.agent,
            self.jobs,
            self.mapping,
            self.catalog,
            coordination_lock=self.lock,
            require_lifecycle_idle=lifecycle_gate,
            ready_timeout_s=0.2,
            localization_timeout_s=0.2,
            poll_interval_s=0.001,
            logger=self.logger,
        )

    async def wait_for_start_settlement(self):
        for _ in range(500):
            if self.coordinator.start_task is None:
                return
            await asyncio.sleep(0.001)
        self.fail("navigation background start did not settle")

    async def test_single_owner_state_hides_token_and_uses_shared_lock(self):
        self.assertIs(self.coordinator.coordination_lock, self.lock)
        self.assertEqual(self.jobs.on_terminal, self.coordinator.handle_terminal)
        token = self.coordinator.begin_start()
        self.assertRegex(token, r"^[0-9a-f]{32}$")
        self.assertNotIn("token", self.coordinator.start_state())
        self.assertEqual(self.coordinator.internal_start_state()["token"], token)
        self.assertIsInstance(self.coordinator.state_lock, type(threading.RLock()))

    async def test_stop_fence_prevents_commit_and_replacement_start(self):
        token = self.coordinator.begin_start()
        self.assertEqual(self.coordinator.request_start_cancel(), token)
        self.assertFalse(self.coordinator.commit_start(token))
        with self.assertRaises(NavigationBusy):
            self.coordinator.begin_start()

    async def test_exact_owned_mapping_cleanup_and_failed_retry_ownership(self):
        token = self.coordinator.begin_start()
        self.mapping.state = "running"
        self.coordinator.update_start(
            token,
            "waiting_localization",
            mapping_job_id=self.mapping.job_id,
            mapping_owned=True,
            navigation_job_id="b" * 32,
        )
        self.mapping.cleanup_error = True
        self.assertFalse(
            self.coordinator.cleanup_localization_dependency_sync(token)
        )
        self.coordinator.finish_start_failure(
            token,
            "cleanup failed",
            cleanup_complete=False,
        )
        retained = self.coordinator.internal_start_state()
        self.assertEqual(retained["token"], token)
        self.assertTrue(retained["mapping_owned"])

        self.mapping.cleanup_error = False
        self.assertTrue(
            self.coordinator.cleanup_localization_dependency_sync(token)
        )
        self.assertEqual(
            self.mapping.events[-1],
            ("stop_mapping", "a" * 32),
        )

    async def test_manual_shared_mapping_is_never_stopped(self):
        token = self.coordinator.begin_start()
        self.mapping.state = "running"
        self.coordinator.update_start(
            token,
            "waiting_localization",
            mapping_job_id=self.mapping.job_id,
            mapping_owned=False,
        )
        self.assertTrue(
            self.coordinator.cleanup_localization_dependency_sync(token)
        )
        self.assertEqual(self.mapping.events, [])
        self.assertEqual(self.mapping.state, "running")

    async def test_cancel_during_mapping_start_settles_and_claims_job(self):
        token = self.coordinator.begin_start()
        self.mapping.release.clear()
        task = asyncio.create_task(
            self.coordinator.start_localization_dependency(
                token,
                previous_job_id=None,
            )
        )
        await asyncio.to_thread(self.mapping.entered.wait, 1.0)
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        self.mapping.release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        state = self.coordinator.internal_start_state()
        self.assertTrue(state["mapping_owned"])
        self.assertEqual(state["mapping_job_id"], "a" * 32)
        self.assertEqual(state["phase"], "stopping")

    async def test_manager_start_cancellation_waits_then_disarms_and_stops(self):
        self.jobs.release.clear()
        task = asyncio.create_task(
            self.coordinator.run_manager_start(
                self.jobs,
                map_id="m" * 24,
                map_revision="r" * 64,
                parameters_revision="c" * 64,
            )
        )
        await asyncio.to_thread(self.jobs.entered.wait, 1.0)
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        self.jobs.release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIn(("deactivate", "navigation_start_cancelled"), self.agent.events)
        self.assertIn("stop", self.jobs.events)

    async def test_activation_cancellation_waits_then_releases_motion(self):
        self.jobs.pipeline_state = "running"
        self.jobs.job_id = "b" * 32
        self.jobs.map = {"id": "m" * 24, "revision": "r" * 64}
        self.mapping.state = "running"
        self.agent.block_activation = True
        task = asyncio.create_task(
            self.coordinator.run_activation(
                self.jobs,
                map_id="m" * 24,
                map_revision="r" * 64,
                map_name="classroom",
                ready_after=1.0,
            )
        )
        await asyncio.to_thread(self.agent.activation_entered.wait, 1.0)
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        self.agent.activation_release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.agent.active)
        self.assertIn("stop", self.jobs.events)

    async def test_full_start_reuses_manual_mapping_and_commits(self):
        self.mapping.state = "running"
        self.jobs.pipeline_state = "idle"
        response = await self.coordinator.start(
            map_id="m" * 24,
            map_revision="r" * 64,
            parameters_revision="c" * 64,
        )
        self.assertTrue(response["accepted"])
        self.assertTrue(response["pending"])
        await self.wait_for_start_settlement()
        state = self.coordinator.internal_start_state()
        self.assertEqual(state["phase"], "active")
        self.assertFalse(state["pending"])
        self.assertFalse(state["mapping_owned"])
        self.assertEqual(state["mapping_job_id"], "a" * 32)
        self.assertEqual(state["navigation_job_id"], "b" * 32)
        self.assertEqual(self.agent.events.count("preflight"), 2)
        self.assertEqual(self.mapping.events, [])
        self.assertEqual(self.lifecycle_calls, 1)

    async def test_full_start_cold_mapping_claims_exact_job(self):
        self.mapping.state = "idle"
        self.mapping.job_id = None
        order = []
        original_preflight = self.agent.navigation_start_preflight
        original_mapping_start = self.mapping.start_mapping

        def preflight():
            order.append("preflight")
            return original_preflight()

        def start_mapping():
            order.append("mapping_start")
            return original_mapping_start()

        self.agent.navigation_start_preflight = preflight
        self.mapping.start_mapping = start_mapping
        await self.coordinator.start(
            map_id="m" * 24,
            map_revision="r" * 64,
            parameters_revision="c" * 64,
        )
        await self.wait_for_start_settlement()
        state = self.coordinator.internal_start_state()
        self.assertEqual(state["phase"], "active")
        self.assertTrue(state["mapping_owned"])
        self.assertEqual(state["mapping_job_id"], "a" * 32)
        self.assertEqual(self.mapping.events, ["start_mapping"])
        self.assertEqual(order[:2], ["preflight", "mapping_start"])

    async def test_terminal_failure_disarms_then_cleans_and_stale_job_is_ignored(self):
        token = self.coordinator.begin_start()
        self.mapping.state = "running"
        self.coordinator.update_start(
            token,
            "waiting_localization",
            mapping_job_id="a" * 32,
            mapping_owned=True,
            navigation_job_id="b" * 32,
        )
        self.assertTrue(self.coordinator.commit_start(token))
        self.agent.fail_deactivate = True
        order = []
        original_deactivate = self.agent.navigation_deactivate
        original_mapping_stop = self.mapping.stop_mapping_if_job_id

        def deactivate(**kwargs):
            order.append("deactivate")
            return original_deactivate(**kwargs)

        def stop_mapping(job_id):
            order.append("mapping_stop")
            return original_mapping_stop(job_id)

        self.agent.navigation_deactivate = deactivate
        self.mapping.stop_mapping_if_job_id = stop_mapping
        self.coordinator.handle_terminal("pipeline_exit", "b" * 32)
        self.assertEqual(order, ["deactivate", "mapping_stop"])
        self.assertEqual(self.agent.events[-1], ("deactivate", "pipeline_exit"))
        self.assertEqual(self.mapping.events[-1], ("stop_mapping", "a" * 32))
        state = self.coordinator.internal_start_state()
        self.assertIsNone(state["token"])
        self.assertEqual(state["phase"], "failed")

        event_count = len(self.agent.events)
        self.coordinator.handle_terminal("stale", "c" * 32)
        self.assertEqual(len(self.agent.events), event_count)

    async def test_stop_order_disarms_manager_then_exact_mapping_cleanup(self):
        token = self.coordinator.begin_start()
        self.mapping.state = "running"
        self.jobs.pipeline_state = "running"
        self.jobs.job_id = "b" * 32
        self.jobs.map = {"id": "m" * 24, "revision": "r" * 64}
        self.coordinator.update_start(
            token,
            "active",
            mapping_job_id="a" * 32,
            mapping_owned=True,
            navigation_job_id="b" * 32,
        )
        events = []
        original_deactivate = self.agent.navigation_deactivate
        original_stop = self.jobs.stop
        original_mapping_stop = self.mapping.stop_mapping_if_job_id

        def deactivate(**kwargs):
            events.append("deactivate")
            return original_deactivate(**kwargs)

        def stop_jobs():
            events.append("nav_stop")
            return original_stop()

        def stop_mapping(job_id):
            events.append("mapping_stop")
            return original_mapping_stop(job_id)

        self.agent.navigation_deactivate = deactivate
        self.jobs.stop = stop_jobs
        self.mapping.stop_mapping_if_job_id = stop_mapping
        await self.coordinator.stop()
        self.assertEqual(events, ["deactivate", "nav_stop", "mapping_stop"])
        self.assertEqual(self.coordinator.internal_start_state()["phase"], "idle")

    async def test_goal_confirmation_and_pose_validation_precede_agent_calls(self):
        self.mapping.state = "running"
        self.jobs.pipeline_state = "running"
        self.jobs.job_id = "b" * 32
        self.jobs.map = {"id": "m" * 24, "revision": "r" * 64}
        with self.assertRaises(NavigationPoseError):
            await self.coordinator.send_goal(
                map_id="m" * 24,
                map_revision="r" * 64,
                x=1,
                y=2,
                yaw=0,
                confirmed=False,
            )
        self.assertFalse(any(isinstance(item, tuple) and item[0] == "goal" for item in self.agent.events))

        await self.coordinator.set_initial_pose(
            map_id="m" * 24,
            map_revision="r" * 64,
            x=1,
            y=2,
            yaw=0,
        )
        await self.coordinator.send_goal(
            map_id="m" * 24,
            map_revision="r" * 64,
            x=3,
            y=4,
            yaw=0.5,
            confirmed=True,
        )
        validate_indices = [
            index
            for index, event in enumerate(self.jobs.events)
            if isinstance(event, tuple) and event[0] == "validate_pose"
        ]
        pose_index = next(
            index
            for index, event in enumerate(self.agent.events)
            if isinstance(event, tuple) and event[0] == "initial_pose"
        )
        goal_index = next(
            index
            for index, event in enumerate(self.agent.events)
            if isinstance(event, tuple) and event[0] == "goal"
        )
        self.assertEqual(len(validate_indices), 2)
        self.assertGreater(pose_index, 0)
        self.assertGreater(goal_index, pose_index)
        self.assertEqual(self.lifecycle_calls, 2)

    async def test_annotation_goal_resolves_exact_pins_then_uses_goal_safety_path(self):
        self.mapping.state = "running"
        self.jobs.pipeline_state = "running"
        self.jobs.job_id = "b" * 32
        self.jobs.map = {"id": "m" * 24, "revision": "r" * 64}

        with self.assertRaises(NavigationPoseError):
            await self.coordinator.send_annotation_goal(
                map_id="m" * 24,
                map_revision="r" * 64,
                annotation_revision="a" * 64,
                annotation_id="f" * 24,
                confirmed=False,
            )
        self.assertEqual(self.catalog.calls, [])

        result = await self.coordinator.send_annotation_goal(
            map_id="m" * 24,
            map_revision="r" * 64,
            annotation_revision="a" * 64,
            annotation_id="f" * 24,
            confirmed=True,
        )
        self.assertEqual(
            self.catalog.calls[-1],
            (
                "annotation_goal",
                "m" * 24,
                "r" * 64,
                "a" * 64,
                "f" * 24,
            ),
        )
        self.assertEqual(result["annotation"], {
            "id": "f" * 24,
            "type": "POI",
            "name": "Inspection A",
        })
        self.assertEqual(self.jobs.events[-1], ("validate_pose", "m" * 24))
        goal = next(
            event for event in reversed(self.agent.events)
            if isinstance(event, tuple) and event[0] == "goal"
        )
        self.assertEqual(goal[1]["x"], 3.0)
        self.assertEqual(goal[1]["y"], 4.0)
        self.assertEqual(goal[1]["yaw"], 0.5)
        self.assertEqual(self.lifecycle_calls, 1)

    async def test_view_preserves_cleanup_union_fixed_bindings_and_hides_token(self):
        token = self.coordinator.begin_start()
        self.mapping.state = "running"
        self.coordinator.update_start(
            token,
            "waiting_localization",
            mapping_job_id="a" * 32,
            mapping_owned=False,
        )
        view = self.coordinator.view()
        self.assertTrue(view["safety"]["can_stop"])
        self.assertNotIn("token", view["localization_pipeline"])
        self.assertEqual(view["bindings"]["scan"], "/scan")
        self.assertEqual(view["bindings"]["odometry"], "/utlidar/robot_odom")
        self.assertEqual(
            view["bindings"]["localization_odometry"],
            "/Odometry",
        )
        self.assertEqual(
            view["bindings"]["command"],
            "/robot_scope/nav/cmd_vel_raw",
        )
        self.assertFalse(view["localization_pipeline"]["owned_by_navigation"])
        self.assertTrue(view["readiness"]["action_server"])
        for key in (
            "cmd_vel_publishers",
            "scan_publishers",
            "odometry_publishers",
            "controller_odometry_publishers",
            "runtime_health_publishers",
            "localization_publishers",
        ):
            self.assertEqual(view["readiness"][key], 1)

    async def test_view_preserves_first_nonready_goal_health_evidence(self):
        first_nonready = {
            "goal_id": "goal-1",
            "captured_age_s": 0.25,
            "state": "DEGRADED",
            "reason_code": "GOAL_PROGRESS_TOO_LOW",
            "threshold_basis": "goal_progress_rate_mps<0.01",
            "metrics": {
                "goal_progress_rate_mps": 0.0,
                "controller_stall_duration_s": 3.0,
            },
        }
        self.agent.runtime["goal"] = {
            "state": "canceled",
            "goal_id": "goal-1",
            "recoveries": 0,
            "first_nonready_health": first_nonready,
        }

        view = self.coordinator.view()

        self.assertEqual(view["goal"]["first_nonready_health"], first_nonready)
        self.assertNotIn(
            "observed_at_monotonic_s",
            view["goal"]["first_nonready_health"],
        )

    async def test_view_redacts_navigation_runtime_and_startup_diagnostics(self):
        private_path = "/private/robot-scope/navigation.yaml"
        private_secret = "navigation-password-do-not-expose"
        private_error = f"failed at {private_path} password={private_secret}"
        token = self.coordinator.begin_start()
        self.coordinator.finish_start_failure(
            token,
            private_error,
            cleanup_complete=False,
        )
        self.jobs.pipeline_error = private_error
        self.agent.runtime["goal"] = {
            "state": "failed",
            "recoveries": 0,
            "error": private_error,
        }
        self.agent.runtime["deactivation_reason"] = private_error

        view = self.coordinator.view()
        public_values = (
            view["pipeline"]["error"],
            view["localization_pipeline"]["error"],
            view["goal"]["error"],
            view["deactivation_reason"],
        )
        for value in public_values:
            self.assertTrue(value)
            self.assertNotIn(private_path, value)
            self.assertNotIn(private_secret, value)
            self.assertLessEqual(len(value), 160)

    async def test_is_active_fails_closed_on_manager_or_runtime_snapshot_error(self):
        self.jobs.fail_snapshot = True
        self.assertTrue(self.coordinator.is_active())
        self.jobs.fail_snapshot = False
        self.agent.runtime_error = True
        self.assertTrue(self.coordinator.is_active())

    async def test_close_order_settles_navigation_before_owned_mapping(self):
        token = self.coordinator.begin_start()
        self.mapping.state = "running"
        self.jobs.pipeline_state = "running"
        self.jobs.job_id = "b" * 32
        self.coordinator.update_start(
            token,
            "active",
            mapping_job_id="a" * 32,
            mapping_owned=True,
            navigation_job_id="b" * 32,
        )
        events = []
        original_deactivate = self.agent.navigation_deactivate
        original_close = self.jobs.close
        original_mapping_stop = self.mapping.stop_mapping_if_job_id

        def deactivate(**kwargs):
            events.append("deactivate")
            return original_deactivate(**kwargs)

        def close_jobs():
            events.append("nav_close")
            return original_close()

        def stop_mapping(job_id):
            events.append("mapping_stop")
            return original_mapping_stop(job_id)

        self.agent.navigation_deactivate = deactivate
        self.jobs.close = close_jobs
        self.mapping.stop_mapping_if_job_id = stop_mapping
        await self.coordinator.close()
        self.assertEqual(events, ["deactivate", "nav_close", "mapping_stop"])

    async def test_startup_settlement_is_fenced_and_idempotent_before_close(self):
        token = self.coordinator.begin_start()
        entered = asyncio.Event()

        async def pending_start():
            entered.set()
            await asyncio.Future()

        task = asyncio.create_task(pending_start())
        self.coordinator._start_task = task
        await entered.wait()

        await self.coordinator.settle_startup()
        state = self.coordinator.internal_start_state()
        self.assertTrue(task.done())
        self.assertTrue(state["cancel_requested"])
        self.assertEqual(state["phase"], "stopping")
        self.assertEqual(state["token"], token)
        settled_seq = state["seq"]

        await self.coordinator.settle_startup()
        self.assertEqual(
            self.coordinator.internal_start_state()["seq"],
            settled_seq,
        )


class NavigationCoordinatorBoundaryTests(unittest.TestCase):
    def test_coordinator_has_no_transport_ros_process_or_filesystem_dependency(self):
        tree = ast.parse(COORDINATOR_PATH.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            (node.module or "").split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.level == 0
        )
        self.assertTrue(
            {"fastapi", "starlette", "rclpy", "subprocess", "pathlib", "os"}.isdisjoint(
                imported
            )
        )
        source = COORDINATOR_PATH.read_text(encoding="utf-8")
        self.assertNotIn("Popen", source)
        self.assertNotIn("shell=", source)
        self.assertNotIn("/api/v1/", source)


if __name__ == "__main__":
    unittest.main()
