import asyncio
import threading
import unittest

from robot_dashboard.application.navigation_coordinator import NavigationCoordinator


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

    def navigation_runtime_snapshot(self):
        return {
            "available": True,
            "robot_online": True,
            "active": self.active,
            "readiness": {},
            "safety": {},
            "localization": {"state": "uninitialized"},
            "goal": {"state": "idle"},
        }

    def control_snapshot(self):
        return {"lease": {"active": False, "input_source": None}}


class FakeManager:
    def __init__(self, *, fail=False):
        self.on_terminal = None
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
        return self.snapshot()

    def stop(self):
        self.events.append("stop")
        self.state = "idle"
        self.job_id = None

    def snapshot(self):
        return {
            "seq": 0,
            "available": True,
            "pipeline": {
                "state": self.state,
                "job_id": self.job_id,
                "error": None,
                "started_at": None,
            },
            "map": (
                {"id": "a" * 24, "revision": "b" * 64}
                if self.state == "running"
                else None
            ),
            "command_topic": "/robot_scope/nav/cmd_vel_raw",
        }


class FakeMapping:
    def activity(self):
        return False, []

    def pipeline_state(self):
        return "running"

    def snapshot(self, *, since_log_seq=0):
        del since_log_seq
        return {"pipeline": {"state": "running", "job_id": "m" * 32}}

    def start_mapping(self):
        return self.snapshot()

    def stop_mapping_if_job_id(self, _job_id):
        return False, self.snapshot()


class FakeSavedMaps:
    def resolve_navigation_map(self, _map_id, _revision):
        raise AssertionError("map resolution is not used by these focused tests")


class NavigationStartTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = FakeAgent()
        self.manager = FakeManager()
        self.coordinator = self.make_coordinator(self.manager)

    def make_coordinator(self, manager):
        return NavigationCoordinator(
            self.agent,
            manager,
            FakeMapping(),
            FakeSavedMaps(),
            coordination_lock=asyncio.Lock(),
            require_lifecycle_idle=lambda: None,
        )

    async def test_cancel_waits_for_thread_then_rolls_back_both_sides(self):
        manager = self.manager
        task = asyncio.create_task(
            self.coordinator.run_manager_start(
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
        coordinator = self.make_coordinator(manager)
        with self.assertRaisesRegex(RuntimeError, "start failed"):
            await coordinator.run_manager_start(
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
        manager = self.manager
        manager.state = "running"
        manager.job_id = "f" * 32
        self.agent.block_activation = True
        task = asyncio.create_task(
            self.coordinator.run_activation(
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
        manager = self.manager
        manager.state = "running"
        manager.job_id = "f" * 32
        projection_entered = threading.Event()
        projection_release = threading.Event()

        def blocked_projection():
            projection_entered.set()
            projection_release.wait(timeout=2.0)
            return {"pipeline": {"state": "running"}}

        self.coordinator.view = blocked_projection
        task = asyncio.create_task(
            self.coordinator.run_activation(
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
