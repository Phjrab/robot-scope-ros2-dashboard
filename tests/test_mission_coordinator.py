import asyncio
import tempfile
import unittest
from pathlib import Path

from robot_dashboard.application.mission_coordinator import (
    MissionConflict,
    MissionCoordinator,
    MissionValidationError,
)


MAP_ID = "a" * 24
MAP_REVISION = "b" * 64
ANNOTATION_REVISION = "c" * 64
FIRST = "d" * 24
SECOND = "e" * 24


class FakeSavedMaps:
    def __init__(self):
        self.annotation_revision = ANNOTATION_REVISION

    def annotations(self, map_id):
        return {
            "map_id": map_id,
            "map_revision": MAP_REVISION,
            "annotation_revision": self.annotation_revision,
            "points": [
                {"id": FIRST, "type": "HOME", "name": "Home"},
                {"id": SECOND, "type": "INSPECTION_POINT", "name": "Inspect"},
            ],
        }


class FakeNavigation:
    def __init__(self):
        self.sent = []
        self.canceled = []
        self.goal = {"state": "idle", "goal_id": None}
        self.ready = True

    def view(self):
        return {
            "pipeline": {"state": "running"},
            "map": {"id": MAP_ID, "revision": MAP_REVISION},
            "localization": {"state": "localized"},
            "safety": {"can_send_goal": self.ready},
            "goal": dict(self.goal),
        }

    async def send_annotation_goal(self, **kwargs):
        if self.goal["state"] in {"pending", "active", "canceling"}:
            raise AssertionError("a second goal was submitted")
        self.sent.append(kwargs["annotation_id"])
        goal_id = f"{len(self.sent):032x}"
        self.goal = {"state": "active", "goal_id": goal_id}
        return {"navigation": self.view()}

    async def cancel_goal(self, *, goal_id):
        self.canceled.append(goal_id)
        self.goal = {"state": "canceled", "goal_id": goal_id}
        return {"navigation": self.view()}


def waypoint(annotation_id, *, confirmation=False, hold=0.0):
    return {
        "annotation_id": annotation_id,
        "arrival_tolerance": None,
        "hold_seconds": hold,
        "requires_operator_confirmation": confirmation,
        "label": "Route point",
    }


async def wait_for(predicate, timeout=1.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        value = predicate()
        if value:
            return value
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not reached")


class MissionCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve() / "missions"
        self.navigation = FakeNavigation()
        self.saved_maps = FakeSavedMaps()
        self.coordinator = MissionCoordinator(
            self.navigation,
            self.saved_maps,
            self.root,
            poll_interval_s=0.01,
            cancel_timeout_s=0.2,
        )

    async def asyncTearDown(self):
        await self.coordinator.close()
        self.temporary.cleanup()

    async def create(self, route=None):
        response = await self.coordinator.create(
            label="Competition route",
            map_id=MAP_ID,
            map_revision=MAP_REVISION,
            annotation_revision=ANNOTATION_REVISION,
            waypoints=route or [waypoint(FIRST), waypoint(SECOND)],
        )
        return response["mission"]

    async def test_schema_is_bounded_and_every_annotation_is_validated_at_creation(self):
        with self.assertRaises(MissionValidationError):
            await self.coordinator.create(
                label="Bad route",
                map_id=MAP_ID,
                map_revision=MAP_REVISION,
                annotation_revision=ANNOTATION_REVISION,
                waypoints=[waypoint("invalid")],
            )
        mission = await self.create()
        self.assertEqual(len(mission["waypoints"]), 2)
        self.assertEqual(mission["state"], "ready")
        self.assertNotIn("path", str(mission).lower())

    async def test_corrupt_persisted_state_disables_missions_without_submitting_navigation(self):
        await self.create()
        state_file = self.root / "missions.json"
        state_file.write_text('{"schema_version":1,"missions":"corrupt"}', encoding="utf-8")
        recovered_navigation = FakeNavigation()
        recovered = MissionCoordinator(recovered_navigation, self.saved_maps, self.root, poll_interval_s=0.01)
        try:
            snapshot = recovered.snapshot()
            self.assertFalse(snapshot["available"])
            self.assertEqual(snapshot["missions"], [])
            self.assertEqual(recovered_navigation.sent, [])
        finally:
            await recovered.close()

    async def test_revision_change_blocks_start_before_any_goal(self):
        mission = await self.create()
        self.saved_maps.annotation_revision = "f" * 64
        with self.assertRaises(MissionConflict):
            await self.coordinator.start(mission["id"])
        self.assertEqual(self.navigation.sent, [])
        self.assertEqual(self.coordinator.snapshot(mission["id"])["mission"]["state"], "failed")

    async def test_duplicate_start_is_idempotent_and_only_one_goal_runs_at_a_time(self):
        mission = await self.create()
        first = await self.coordinator.start(mission["id"])
        second = await self.coordinator.start(mission["id"])
        self.assertEqual(first["mission"]["id"], second["mission"]["id"])
        self.assertEqual(self.navigation.sent, [FIRST])
        self.assertEqual(second["mission"]["current_waypoint"]["goal_id"], self.navigation.goal["goal_id"])

    async def test_waypoints_advance_only_after_terminal_success(self):
        mission = await self.create()
        await self.coordinator.start(mission["id"])
        await asyncio.sleep(0.04)
        self.assertEqual(self.navigation.sent, [FIRST])
        self.navigation.goal["state"] = "succeeded"
        await wait_for(lambda: len(self.navigation.sent) == 2)
        self.assertEqual(self.navigation.sent, [FIRST, SECOND])
        self.navigation.goal["state"] = "succeeded"
        completed = await wait_for(lambda: self.coordinator.snapshot(mission["id"])["mission"]["state"] == "completed")
        self.assertTrue(completed)
        self.assertEqual(self.coordinator.snapshot(mission["id"])["mission"]["completed_count"], 2)

    async def test_pause_confirms_cancel_and_resume_requires_an_explicit_new_goal(self):
        mission = await self.create()
        await self.coordinator.start(mission["id"])
        paused = await self.coordinator.pause(mission["id"])
        self.assertEqual(paused["mission"]["state"], "paused")
        self.assertEqual(len(self.navigation.canceled), 1)
        self.assertEqual(len(self.navigation.sent), 1)
        resumed = await self.coordinator.resume(mission["id"])
        self.assertEqual(resumed["mission"]["state"], "running")
        self.assertEqual(self.navigation.sent, [FIRST, FIRST])

    async def test_next_confirmation_pause_skip_retry_and_abort_are_operator_driven(self):
        mission = await self.create([waypoint(FIRST), waypoint(SECOND, confirmation=True)])
        await self.coordinator.start(mission["id"])
        self.navigation.goal["state"] = "succeeded"
        await wait_for(lambda: self.coordinator.snapshot(mission["id"])["mission"]["state"] == "paused")
        self.assertEqual(self.navigation.sent, [FIRST])
        await self.coordinator.resume(mission["id"])
        self.assertEqual(self.navigation.sent, [FIRST, SECOND])
        aborted = await self.coordinator.abort(mission["id"])
        self.assertEqual(aborted["mission"]["outcome"], "aborted")
        self.assertFalse(aborted["mission"]["ownership_active"])

    async def test_failed_waypoint_retries_only_explicitly_and_skip_advances_once(self):
        mission = await self.create()
        await self.coordinator.start(mission["id"])
        self.navigation.goal["state"] = "failed"
        await wait_for(lambda: self.coordinator.snapshot(mission["id"])["mission"]["state"] == "failed")
        self.assertEqual(self.navigation.sent, [FIRST])
        await self.coordinator.retry(mission["id"])
        self.assertEqual(self.navigation.sent, [FIRST, FIRST])
        await self.coordinator.pause(mission["id"])
        skipped = await self.coordinator.skip(mission["id"])
        self.assertEqual(skipped["mission"]["current_index"], 1)
        self.assertEqual(self.navigation.sent, [FIRST, FIRST, SECOND])

    async def test_manual_conflict_fails_closed_through_navigation_readiness(self):
        mission = await self.create()
        self.navigation.ready = False
        with self.assertRaises(MissionConflict):
            await self.coordinator.start(mission["id"])
        self.assertEqual(self.navigation.sent, [])

    async def test_restart_marks_running_mission_interrupted_without_resubmitting(self):
        mission = await self.create()
        await self.coordinator.start(mission["id"])
        self.coordinator._generation += 1
        if self.coordinator._task:
            self.coordinator._task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await self.coordinator._task
            self.coordinator._task = None
        recovered_navigation = FakeNavigation()
        recovered = MissionCoordinator(recovered_navigation, self.saved_maps, self.root, poll_interval_s=0.01)
        try:
            snapshot = recovered.snapshot(mission["id"])["mission"]
            self.assertEqual(snapshot["state"], "failed")
            self.assertEqual(snapshot["outcome"], "interrupted")
            self.assertEqual(recovered_navigation.sent, [])
        finally:
            await recovered.close()


if __name__ == "__main__":
    unittest.main()
