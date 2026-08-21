import ast
import asyncio
import logging
import re
import secrets
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace


APP_PATH = Path(__file__).parents[1] / "robot_dashboard" / "app.py"


class FakeNavigationBusy(RuntimeError):
    pass


class FakeMappingError(RuntimeError):
    pass


class FakeMappingManager:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.job_id = "a" * 32
        self.state = "starting"
        self.fail_start = False
        self.cleanup_error = False
        self.stop_calls = []

    def start_mapping(self):
        self.entered.set()
        self.release.wait(timeout=2.0)
        if self.fail_start:
            self.state = "failed"
            raise FakeMappingError("launcher failed")
        return self.snapshot()

    def snapshot(self):
        return {"pipeline": {"state": self.state, "job_id": self.job_id}}

    def stop_mapping_if_job_id(self, job_id):
        self.stop_calls.append(job_id)
        if self.cleanup_error:
            raise FakeMappingError("stop failed")
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


def load_dependency_functions(manager):
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    names = {
        "navigation_start_state",
        "_navigation_start_internal",
        "begin_navigation_start",
        "update_navigation_start",
        "navigation_start_cancelled",
        "request_navigation_start_cancel",
        "request_navigation_terminal_cancel",
        "request_navigation_terminal_cancel",
        "commit_navigation_start",
        "finish_navigation_start_failure",
        "reset_navigation_start",
        "start_navigation_localization_dependency",
        "cleanup_navigation_localization_dependency_sync",
    }
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    ]
    nodes.append(
        next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "navigation_terminal"
        )
    )
    runtime = SimpleNamespace(
        agent=None,
        navigation_start_state_lock=threading.RLock(),
        navigation_start={
            "seq": 0,
            "token": None,
            "phase": "idle",
            "pending": False,
            "cancel_requested": False,
            "mapping_job_id": None,
            "mapping_owned": False,
            "navigation_job_id": None,
            "terminal_cleanup": False,
            "error": None,
        },
    )
    namespace = {
        "Any": object,
        "Dict": dict,
        "asyncio": asyncio,
        "LOGGER": logging.getLogger(__name__),
        "MappingJobError": FakeMappingError,
        "NavigationBusy": FakeNavigationBusy,
        "NavigationConflict": RuntimeError,
        "NavigationUnavailable": RuntimeError,
        "RUNTIME": runtime,
        "mapping_jobs": lambda: manager,
        "re": re,
        "secrets": secrets,
    }
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(APP_PATH), "exec"), namespace)
    return namespace


class NavigationMappingDependencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = FakeMappingManager()
        self.functions = load_dependency_functions(self.manager)
        self.token = self.functions["begin_navigation_start"]()

    async def test_manual_running_mapping_is_never_claimed_or_stopped(self):
        self.manager.state = "running"
        self.functions["update_navigation_start"](
            self.token,
            "waiting_localization",
            mapping_job_id=self.manager.job_id,
            mapping_owned=False,
        )

        cleaned = self.functions["cleanup_navigation_localization_dependency_sync"](
            self.token
        )

        self.assertTrue(cleaned)
        self.assertEqual(self.manager.stop_calls, [])
        self.assertEqual(self.manager.state, "running")

    async def test_auto_started_mapping_cleanup_uses_only_the_exact_job_id(self):
        self.functions["update_navigation_start"](
            self.token,
            "waiting_localization",
            mapping_job_id=self.manager.job_id,
            mapping_owned=True,
            navigation_job_id="b" * 32,
        )

        cleaned = self.functions["cleanup_navigation_localization_dependency_sync"](
            self.token
        )

        self.assertTrue(cleaned)
        self.assertEqual(self.manager.stop_calls, ["a" * 32])
        self.assertEqual(self.manager.state, "stopped")

    async def test_failed_cleanup_retains_retryable_ownership(self):
        self.functions["update_navigation_start"](
            self.token,
            "waiting_localization",
            mapping_job_id=self.manager.job_id,
            mapping_owned=True,
            navigation_job_id="b" * 32,
        )
        self.manager.cleanup_error = True

        cleaned = self.functions["cleanup_navigation_localization_dependency_sync"](
            self.token
        )
        self.functions["finish_navigation_start_failure"](
            self.token,
            "cleanup failed",
            cleanup_complete=cleaned,
        )

        state = self.functions["_navigation_start_internal"]()
        self.assertFalse(cleaned)
        self.assertEqual(state["token"], self.token)
        self.assertTrue(state["mapping_owned"])
        self.assertEqual(state["phase"], "failed")

    async def test_cancel_during_mapping_start_settles_worker_and_claims_job(self):
        task = asyncio.create_task(
            self.functions["start_navigation_localization_dependency"](
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

        state = self.functions["_navigation_start_internal"]()
        self.assertTrue(state["mapping_owned"])
        self.assertEqual(state["mapping_job_id"], self.manager.job_id)
        self.assertEqual(state["phase"], "stopping")

    async def test_launcher_failure_still_claims_the_published_job_for_rollback(self):
        self.manager.fail_start = True
        self.manager.release.set()

        with self.assertRaisesRegex(FakeMappingError, "launcher failed"):
            await self.functions["start_navigation_localization_dependency"](
                self.token,
                previous_job_id=None,
            )

        state = self.functions["_navigation_start_internal"]()
        self.assertTrue(state["mapping_owned"])
        self.assertEqual(state["mapping_job_id"], self.manager.job_id)

    async def test_stop_fence_prevents_commit_and_concurrent_new_start(self):
        self.functions["request_navigation_start_cancel"]()

        self.assertFalse(self.functions["commit_navigation_start"](self.token))
        with self.assertRaises(FakeNavigationBusy):
            self.functions["begin_navigation_start"]()

    async def test_terminal_agent_failure_still_cleans_the_exact_owned_mapping(self):
        failing_agent = FailingTerminalAgent()
        self.functions["RUNTIME"].agent = failing_agent
        self.manager.state = "running"
        self.functions["update_navigation_start"](
            self.token,
            "waiting_localization",
            mapping_job_id=self.manager.job_id,
            mapping_owned=True,
            navigation_job_id="b" * 32,
        )
        self.assertTrue(self.functions["commit_navigation_start"](self.token))

        self.functions["navigation_terminal"]("pipeline_exit", "b" * 32)

        self.assertEqual(failing_agent.reasons, ["pipeline_exit"])
        self.assertEqual(self.manager.stop_calls, [self.manager.job_id])
        self.assertEqual(self.manager.state, "stopped")
        state = self.functions["_navigation_start_internal"]()
        self.assertIsNone(state["token"])
        self.assertFalse(state["mapping_owned"])
        self.assertEqual(state["phase"], "failed")

    async def test_stale_terminal_callback_cannot_cancel_replacement_start(self):
        failing_agent = FailingTerminalAgent()
        self.functions["RUNTIME"].agent = failing_agent
        self.manager.state = "running"
        replacement_mapping_id = "c" * 32
        self.manager.job_id = replacement_mapping_id
        self.functions["update_navigation_start"](
            self.token,
            "waiting_localization",
            mapping_job_id=replacement_mapping_id,
            mapping_owned=True,
            navigation_job_id="d" * 32,
        )

        self.functions["navigation_terminal"]("pipeline_exit", "e" * 32)

        self.assertEqual(failing_agent.reasons, [])
        self.assertEqual(self.manager.stop_calls, [])
        state = self.functions["_navigation_start_internal"]()
        self.assertEqual(state["token"], self.token)
        self.assertFalse(state["cancel_requested"])
        self.assertEqual(state["mapping_job_id"], replacement_mapping_id)
        self.assertEqual(state["navigation_job_id"], "d" * 32)


if __name__ == "__main__":
    unittest.main()
