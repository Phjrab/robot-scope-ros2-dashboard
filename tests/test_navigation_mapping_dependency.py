import asyncio
import threading
import unittest

from robot_dashboard.application.navigation_coordinator import NavigationCoordinator
from robot_dashboard.mapping_jobs import MappingJobError
from robot_dashboard.navigation_jobs import NavigationBusy


class FakeMappingManager:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.job_id = "a" * 32
        self.state = "starting"
        self.fail_start = False
        self.cleanup_error = False
        self.stop_calls = []

    def activity(self):
        blockers = ["mapping_transition"] if self.state in {"starting", "stopping"} else []
        return bool(blockers), blockers

    def pipeline_state(self):
        return "idle" if self.state == "stopped" else self.state

    def start_mapping(self):
        self.entered.set()
        self.release.wait(timeout=2.0)
        if self.fail_start:
            self.state = "failed"
            raise MappingJobError("launcher failed")
        return self.snapshot()

    def snapshot(self, *, since_log_seq=0):
        del since_log_seq
        return {"pipeline": {"state": self.state, "job_id": self.job_id}}

    def stop_mapping_if_job_id(self, job_id):
        self.stop_calls.append(job_id)
        if self.cleanup_error:
            raise MappingJobError("stop failed")
        if job_id == self.job_id and self.state in {"starting", "running", "stopping"}:
            self.state = "stopped"
            return True, self.snapshot()
        return False, self.snapshot()


class FailingTerminalAgent:
    def __init__(self):
        self.reasons = []

    def navigation_deactivate(self, *, reason):
        self.reasons.append(reason)
        raise RuntimeError("robot transport unavailable")

    def navigation_runtime_snapshot(self):
        return {}

    def control_snapshot(self):
        return {}


class FakeNavigationJobs:
    def __init__(self):
        self.on_terminal = None

    def snapshot(self):
        return {
            "available": True,
            "pipeline": {"state": "idle", "job_id": None},
            "map": None,
        }


class FakeSavedMaps:
    def resolve_navigation_map(self, _map_id, _revision):
        raise AssertionError("map resolution is not used by these focused tests")


class SilentLogger:
    def exception(self, _message, *args):
        del args

    def warning(self, _message, *args):
        del args


class NavigationMappingDependencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = FakeMappingManager()
        self.agent = FailingTerminalAgent()
        self.coordinator = NavigationCoordinator(
            self.agent,
            FakeNavigationJobs(),
            self.manager,
            FakeSavedMaps(),
            coordination_lock=asyncio.Lock(),
            require_lifecycle_idle=lambda: None,
            logger=SilentLogger(),
        )
        self.token = self.coordinator.begin_start()

    async def test_manual_running_mapping_is_never_claimed_or_stopped(self):
        self.manager.state = "running"
        self.coordinator.update_start(
            self.token,
            "waiting_localization",
            mapping_job_id=self.manager.job_id,
            mapping_owned=False,
        )

        cleaned = self.coordinator.cleanup_localization_dependency_sync(self.token)

        self.assertTrue(cleaned)
        self.assertEqual(self.manager.stop_calls, [])
        self.assertEqual(self.manager.state, "running")

    async def test_auto_started_mapping_cleanup_uses_only_the_exact_job_id(self):
        self.coordinator.update_start(
            self.token,
            "waiting_localization",
            mapping_job_id=self.manager.job_id,
            mapping_owned=True,
            navigation_job_id="b" * 32,
        )

        cleaned = self.coordinator.cleanup_localization_dependency_sync(self.token)

        self.assertTrue(cleaned)
        self.assertEqual(self.manager.stop_calls, ["a" * 32])
        self.assertEqual(self.manager.state, "stopped")

    async def test_failed_cleanup_retains_retryable_ownership(self):
        self.coordinator.update_start(
            self.token,
            "waiting_localization",
            mapping_job_id=self.manager.job_id,
            mapping_owned=True,
            navigation_job_id="b" * 32,
        )
        self.manager.cleanup_error = True

        cleaned = self.coordinator.cleanup_localization_dependency_sync(self.token)
        self.coordinator.finish_start_failure(
            self.token,
            "cleanup failed",
            cleanup_complete=cleaned,
        )

        state = self.coordinator.internal_start_state()
        self.assertFalse(cleaned)
        self.assertEqual(state["token"], self.token)
        self.assertTrue(state["mapping_owned"])
        self.assertEqual(state["phase"], "failed")

    async def test_cancel_during_mapping_start_settles_worker_and_claims_job(self):
        task = asyncio.create_task(
            self.coordinator.start_localization_dependency(
                self.token,
                previous_job_id=None,
            )
        )
        await asyncio.to_thread(self.manager.entered.wait, 1.0)
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done(), "cancellation must settle the launcher thread")
        self.manager.release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task

        state = self.coordinator.internal_start_state()
        self.assertTrue(state["mapping_owned"])
        self.assertEqual(state["mapping_job_id"], self.manager.job_id)
        self.assertEqual(state["phase"], "stopping")

    async def test_launcher_failure_still_claims_the_published_job_for_rollback(self):
        self.manager.fail_start = True
        self.manager.release.set()

        with self.assertRaisesRegex(MappingJobError, "launcher failed"):
            await self.coordinator.start_localization_dependency(
                self.token,
                previous_job_id=None,
            )

        state = self.coordinator.internal_start_state()
        self.assertTrue(state["mapping_owned"])
        self.assertEqual(state["mapping_job_id"], self.manager.job_id)

    async def test_stop_fence_prevents_commit_and_concurrent_new_start(self):
        self.coordinator.request_start_cancel()

        self.assertFalse(self.coordinator.commit_start(self.token))
        with self.assertRaises(NavigationBusy):
            self.coordinator.begin_start()

    async def test_terminal_agent_failure_still_cleans_the_exact_owned_mapping(self):
        self.manager.state = "running"
        self.coordinator.update_start(
            self.token,
            "waiting_localization",
            mapping_job_id=self.manager.job_id,
            mapping_owned=True,
            navigation_job_id="b" * 32,
        )
        self.assertTrue(self.coordinator.commit_start(self.token))

        self.coordinator.handle_terminal("pipeline_exit", "b" * 32)

        self.assertEqual(self.agent.reasons, ["pipeline_exit"])
        self.assertEqual(self.manager.stop_calls, [self.manager.job_id])
        self.assertEqual(self.manager.state, "stopped")
        state = self.coordinator.internal_start_state()
        self.assertIsNone(state["token"])
        self.assertFalse(state["mapping_owned"])
        self.assertEqual(state["phase"], "failed")

    async def test_stale_terminal_callback_cannot_cancel_replacement_start(self):
        self.manager.state = "running"
        replacement_mapping_id = "c" * 32
        self.manager.job_id = replacement_mapping_id
        self.coordinator.update_start(
            self.token,
            "waiting_localization",
            mapping_job_id=replacement_mapping_id,
            mapping_owned=True,
            navigation_job_id="d" * 32,
        )

        self.coordinator.handle_terminal("pipeline_exit", "e" * 32)

        self.assertEqual(self.agent.reasons, [])
        self.assertEqual(self.manager.stop_calls, [])
        state = self.coordinator.internal_start_state()
        self.assertEqual(state["token"], self.token)
        self.assertFalse(state["cancel_requested"])
        self.assertEqual(state["mapping_job_id"], replacement_mapping_id)
        self.assertEqual(state["navigation_job_id"], "d" * 32)


if __name__ == "__main__":
    unittest.main()
