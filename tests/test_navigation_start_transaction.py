import ast
import asyncio
import threading
import unittest
from pathlib import Path


APP_PATH = Path(__file__).parents[1] / "robot_dashboard" / "app.py"


def load_transaction_functions():
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    names = {
        "rollback_navigation_start",
        "run_navigation_manager_start",
        "run_navigation_activation",
    }
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name in names
    ]
    module = ast.Module(body=nodes, type_ignores=[])
    namespace = {
        "asyncio": asyncio,
        "LOGGER": __import__("logging").getLogger(__name__),
        "NavigationJobManager": object,
        "Dict": dict,
        "Any": object,
        "agent": None,
        "navigation_view": lambda: {},
    }
    exec(compile(ast.fix_missing_locations(module), str(APP_PATH), "exec"), namespace)
    return namespace


class FakeAgent:
    def __init__(self):
        self.active = False
        self.events = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block_activation = False

    def navigation_deactivate(self, *, reason):
        self.events.append(("deactivate", reason))
        self.active = False

    def navigation_activate(self, **_kwargs):
        self.events.append(("activate", None))
        self.entered.set()
        if self.block_activation:
            self.release.wait(timeout=2.0)
        self.active = True


class FakeManager:
    def __init__(self, *, fail=False):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.fail = fail
        self.state = "idle"
        self.job_id = None
        self.events = []

    def start(self, **_kwargs):
        self.events.append("start")
        self.state = "starting"
        self.job_id = "f" * 32
        self.entered.set()
        self.release.wait(timeout=2.0)
        if self.fail:
            self.state = "failed"
            raise RuntimeError("start failed after publishing job")
        self.state = "running"
        return {}

    def stop(self):
        self.events.append("stop")
        self.state = "idle"
        self.job_id = None


class NavigationStartTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.functions = load_transaction_functions()
        self.agent = FakeAgent()
        self.functions["agent"] = lambda: self.agent

    async def test_cancel_waits_for_thread_then_rolls_back_both_sides(self):
        manager = FakeManager()
        task = asyncio.create_task(
            self.functions["run_navigation_manager_start"](
                manager,
                map_id="a" * 24,
                map_revision="b" * 64,
                parameters_revision="c" * 64,
            )
        )
        await asyncio.to_thread(manager.entered.wait, 1.0)
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done(), "cancel must wait for the to_thread worker")
        manager.release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(manager.state, "idle")
        self.assertIsNone(manager.job_id)
        self.assertIn("stop", manager.events)
        self.assertIn(("deactivate", "navigation_start_cancelled"), self.agent.events)

    async def test_failed_start_with_job_id_is_normalized_to_idle(self):
        manager = FakeManager(fail=True)
        manager.release.set()
        with self.assertRaisesRegex(RuntimeError, "start failed"):
            await self.functions["run_navigation_manager_start"](
                manager,
                map_id="a" * 24,
                map_revision="b" * 64,
                parameters_revision="c" * 64,
            )
        self.assertEqual(manager.state, "idle")
        self.assertIsNone(manager.job_id)
        self.assertIn("stop", manager.events)
        self.assertIn(("deactivate", "navigation_start_failed"), self.agent.events)

    async def test_cancel_waits_for_activation_then_releases_new_lease(self):
        manager = FakeManager()
        manager.state = "running"
        manager.job_id = "f" * 32
        self.agent.block_activation = True
        task = asyncio.create_task(
            self.functions["run_navigation_activation"](
                manager,
                map_id="a" * 24,
                map_revision="b" * 64,
                map_name="classroom",
                ready_after=1.0,
            )
        )
        await asyncio.to_thread(self.agent.entered.wait, 1.0)
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done(), "cancel must wait for activation worker")
        self.agent.release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.agent.active)
        self.assertEqual(manager.state, "idle")
        self.assertIsNone(manager.job_id)
        self.assertLess(
            self.agent.events.index(("activate", None)),
            self.agent.events.index(("deactivate", "navigation_start_cancelled")),
        )

    async def test_cancel_during_final_projection_rolls_back_active_session(self):
        manager = FakeManager()
        manager.state = "running"
        manager.job_id = "f" * 32
        projection_entered = threading.Event()
        projection_release = threading.Event()

        def blocked_projection():
            projection_entered.set()
            projection_release.wait(timeout=2.0)
            return {"pipeline": {"state": "running"}}

        self.functions["navigation_view"] = blocked_projection
        task = asyncio.create_task(
            self.functions["run_navigation_activation"](
                manager,
                map_id="a" * 24,
                map_revision="b" * 64,
                map_name="classroom",
                ready_after=1.0,
            )
        )
        await asyncio.to_thread(projection_entered.wait, 1.0)
        self.assertTrue(self.agent.active)
        task.cancel()
        projection_release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.agent.active)
        self.assertEqual(manager.state, "idle")
        self.assertIsNone(manager.job_id)
        self.assertIn(("deactivate", "navigation_start_cancelled"), self.agent.events)


if __name__ == "__main__":
    unittest.main()
