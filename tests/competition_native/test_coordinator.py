import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from robot_dashboard.application.mission_coordinator import MissionCoordinator
from robot_dashboard.mission_routes.competition_native.coordinator import CoordinatorNavigationPort, LegBinding
from .helpers import POSE, Rig


class SavedMaps:
    def annotations(self, map_id):
        return {"map_id": map_id, "map_revision": "b" * 64,
                "annotation_revision": "c" * 64, "points": []}


class Navigation:
    def __init__(self, lock):
        self.coordination_lock = lock
        self.goal = {"state": "idle", "goal_id": None}
        self.sent, self.canceled = [], []
        self.cancel_ack = True

    def view(self):
        return {"pipeline": {"state": "running"}, "map": {"id": "a" * 24, "revision": "b" * 64},
                "localization": {"state": "localized"}, "safety": {"can_send_goal": True},
                "goal": dict(self.goal)}

    async def send_goal(self, *, map_id, map_revision, x, y, yaw, confirmed):
        async with self.coordination_lock:
            self.sent.append((map_id, map_revision, x, y, yaw, confirmed))
            self.goal = {"state": "active", "goal_id": "nav-goal-nonhex-id-" + str(len(self.sent))}
        return {"accepted": True, "navigation": self.view()}

    async def cancel_goal(self, *, goal_id):
        self.canceled.append(goal_id)
        self.goal = {"state": "canceled" if self.cancel_ack else "canceling", "goal_id": goal_id}
        return {"navigation": self.view()}


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.lock = asyncio.Lock()
        self.nav = Navigation(self.lock)
        self.coordinator = MissionCoordinator(self.nav, SavedMaps(), Path(self.temp.name) / "missions",
            coordination_lock=self.lock, poll_interval_s=0.05, cancel_timeout_s=0.1)
        self.admission = object()
        self.coordinator._managed_admission = self.admission
        async def preflight(mission):
            return None
        self.coordinator._dispatch_preflight = preflight
        self.visits = ("1" * 32, "2" * 32)
        result = await self.coordinator.create(label="Native binding test", map_id="a" * 24,
            map_revision="b" * 64, annotation_revision="c" * 64, context_revision="d" * 64,
            waypoints=[{"visit_id": visit, "mission_local_pose": POSE, "label": "Leg",
                        "after_arrival_confirmation": True} for visit in self.visits])
        self.mission_id = result["mission"]["id"]
        self.scope = replace(Rig().scope, mission_run_id=self.mission_id)
        self.port = CoordinatorNavigationPort(self.coordinator, self.nav, mission_id=self.mission_id,
            admission=self.admission, legs={(self.scope.step_id, leg): LegBinding(visit, tuple(POSE.values()))
                                           for leg, visit in zip(("approach", "exit"), self.visits)})

    async def asyncTearDown(self):
        self.nav.cancel_ack = True
        await self.coordinator.close()
        self.temp.cleanup()

    async def dispatch(self, scope=None, leg="approach", request_id="start-request-001"):
        return await self.port.dispatch(scope or self.scope, leg=leg, pose=POSE, request_id=request_id)

    async def test_real_coordinator_admission_shared_lock_and_idempotence(self):
        await self.lock.acquire()
        task = asyncio.create_task(self.dispatch())
        await asyncio.sleep(0)
        self.assertEqual(self.nav.sent, [])
        self.lock.release()
        receipt = await asyncio.wait_for(task, 1)
        repeated = await self.dispatch()
        self.assertEqual(receipt, repeated)
        self.assertEqual(len(self.nav.sent), 1)
        self.assertTrue(self.coordinator.blocks_navigation_goal())
        observation = self.port.goal_observation(self.scope)
        self.assertEqual(observation["goal_id"], self.scope.goal_id)
        self.assertNotEqual(receipt.actual_goal_id, self.scope.goal_id)
        await self.port.cancel(self.scope, request_id="cancel-request-001")
        self.assertEqual(self.nav.canceled, [receipt.actual_goal_id])
        self.assertTrue(self.port.goal_observation(self.scope)["cancel_ack"])
        self.assertTrue(self.coordinator.blocks_navigation_goal())

    async def test_real_success_barrier_continues_with_exact_token(self):
        await self.dispatch()
        self.nav.goal["state"] = "succeeded"
        for _ in range(30):
            if self.coordinator.snapshot(self.mission_id)["mission"]["phase"] == "after_arrival_confirmation":
                break
            await asyncio.sleep(0.01)
        self.assertEqual(len(self.nav.sent), 1)
        next_scope = replace(self.scope, goal_id="e" * 32, goal_generation=2)
        receipt = await self.dispatch(next_scope, "exit", "exit-request-0001")
        self.assertEqual(receipt.scope, next_scope)
        self.assertEqual(len(self.nav.sent), 2)
        with self.assertRaisesRegex(ValueError, "LATE_CANCEL"):
            await self.port.cancel(self.scope, request_id="old-cancel-request")
        self.assertEqual(self.nav.canceled, [])

    async def test_cancel_ack_delay_keeps_owner_and_cannot_dispatch_exit(self):
        await self.dispatch()
        self.nav.cancel_ack = False
        with self.assertRaisesRegex(Exception, "not confirmed"):
            await self.port.cancel(self.scope, request_id="cancel-request-001")
        self.assertTrue(self.coordinator.blocks_navigation_goal())
        self.assertEqual(self.coordinator.snapshot(self.mission_id)["mission"]["state"], "pausing")
        next_scope = replace(self.scope, goal_id="e" * 32, goal_generation=2)
        with self.assertRaisesRegex(ValueError, "HOOK_REQUIRED"):
            await self.dispatch(next_scope, "exit", "exit-request-0001")
        self.assertEqual(len(self.nav.sent), 1)
        self.nav.goal["state"] = "canceled"

    async def test_canceled_approach_missing_hook_is_explicit(self):
        await self.dispatch()
        await self.port.cancel(self.scope, request_id="cancel-request-001")
        next_scope = replace(self.scope, goal_id="e" * 32, goal_generation=2)
        with self.assertRaisesRegex(ValueError, "HOOK_REQUIRED"):
            await self.dispatch(next_scope, "exit", "exit-request-0001")
        self.assertEqual(len(self.nav.sent), 1)

    async def test_foreign_goal_never_canceled_or_normalized(self):
        await self.dispatch()
        self.nav.goal = {"state": "active", "goal_id": "some-unrelated-goal"}
        with self.assertRaisesRegex(ValueError, "FOREIGN"):
            await self.port.cancel(self.scope, request_id="cancel-request-001")
        self.assertEqual(self.nav.canceled, [])
        with self.assertRaisesRegex(ValueError, "OWNERSHIP_CHANGED"):
            self.port.goal_observation(self.scope)
        self.nav.goal["state"] = "canceled"

    async def test_wrong_admission_and_wrong_lock_are_refused(self):
        with self.assertRaisesRegex(ValueError, "ADMISSION"):
            CoordinatorNavigationPort(self.coordinator, self.nav, mission_id=self.mission_id,
                                      admission=object(), legs={})
        self.nav.coordination_lock = asyncio.Lock()
        with self.assertRaisesRegex(ValueError, "SHARED"):
            CoordinatorNavigationPort(self.coordinator, self.nav, mission_id=self.mission_id,
                                      admission=self.admission, legs={})
