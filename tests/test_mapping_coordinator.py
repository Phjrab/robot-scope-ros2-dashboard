import asyncio
import ast
import logging
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from robot_dashboard.application.mapping_coordinator import (
    MappingCoordinator,
    MappingCoordinatorConflict,
    MappingCoordinatorUnavailable,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "robot_dashboard" / "application" / "mapping_coordinator.py"


class FakeMappingManager:
    def __init__(self) -> None:
        self.allowed_save_kinds = ("pointcloud3d", "pointcloud3d_2d")
        self.pipeline_state = "idle"
        self.operation_state = "idle"
        self.job_id = "a" * 32
        self.calls = []
        self.coordination_lock = None
        self.save_entered = threading.Event()
        self.save_release = threading.Event()
        self.block_save = False

    def _record(self, *event) -> None:
        locked = (
            self.coordination_lock.locked()
            if self.coordination_lock is not None
            else None
        )
        self.calls.append((*event, locked))

    def snapshot(self, *, since_log_seq=0):
        self._record("snapshot", since_log_seq)
        return {
            "preview": {"state": "running", "pid": 4321},
            "pipeline": {
                "state": self.pipeline_state,
                "job_id": self.job_id,
                "pid": 8765,
            },
            "operation": {"state": self.operation_state},
            "logs": [],
        }

    def start_mapping(self):
        self._record("start_mapping")
        self.pipeline_state = "starting"
        return self.snapshot()

    def stop_mapping(self):
        self._record("stop_mapping")
        self.pipeline_state = "stopped"
        return self.snapshot()

    def stop_mapping_if_job_id(self, job_id):
        self._record("stop_mapping_if_job_id", job_id)
        if job_id == self.job_id:
            self.pipeline_state = "stopped"
            return True, self.snapshot()
        return False, self.snapshot()

    def validate_map_name(self, name):
        self._record("validate_map_name", name)
        return name

    def save_map(self, name, kind):
        self._record("save_map", name, kind)
        self.save_entered.set()
        if self.block_save:
            self.save_release.wait(timeout=2.0)
        self.operation_state = "succeeded"
        return self.snapshot()

    def reserve_local_operation(self, kind, name):
        self._record("reserve_local_operation", kind, name)
        self.operation_state = "saving"
        return {
            "operation": {
                "state": "saving",
                "job_id": self.job_id,
                "kind": kind,
                "map_name": name,
            }
        }

    def run_reserved_local_operation(self, job_id, worker):
        self._record("run_reserved_local_operation", job_id)
        result = worker()
        self.operation_state = "succeeded"
        return result

    def fail_reserved_local_operation(self, job_id, message):
        self._record("fail_reserved_local_operation", job_id, message)
        self.operation_state = "failed"
        return self.snapshot()

    def local_operation_cancelled(self, job_id):
        self._record("local_operation_cancelled", job_id)
        return False

    @contextmanager
    def local_publication_guard(self, job_id):
        self._record("local_publication_guard", job_id)
        yield True

    def start_preview(self):
        self._record("start_preview")
        return {"preview": {"state": "running", "pid": 4321}}

    def close(self):
        self._record("close")
        self.save_release.set()


class FakeSavedMapCatalog:
    def __init__(self) -> None:
        self.calls = []

    def validate_pcd_conversion(self, map_id, name, **parameters):
        self.calls.append(("validate", map_id, name, parameters))
        return {
            "source": {"id": map_id, "revision": "b" * 64},
            "parameters": dict(parameters),
        }

    def convert_pcd_to_2d(self, map_id, name, **options):
        cancelled = options.pop("cancelled")
        publication_guard = options.pop("publication_guard")
        self.calls.append(("convert", map_id, name, dict(options)))
        self.calls.append(("cancelled", cancelled()))
        with publication_guard() as allowed:
            self.calls.append(("publication_guard", allowed))
        return {"files": [f"{name}.yaml", f"{name}.pgm"], "details": {}}

    def save_edited_copy(self, map_id, name, source_revision, runs):
        self.calls.append(("edited", map_id, name, source_revision, runs))
        return {"id": "edited-map", "revision": "c" * 64}

    def rename(self, map_id, name):
        self.calls.append(("rename", map_id, name))
        return {"id": map_id, "name": name}

    def delete(self, map_id):
        self.calls.append(("delete", map_id))
        return {"id": map_id}

    def update_annotations(
        self,
        map_id,
        map_revision,
        base_annotation_revision,
        points,
        polygons,
    ):
        self.calls.append(
            (
                "annotations",
                map_id,
                map_revision,
                base_annotation_revision,
                points,
                polygons,
            )
        )
        return {
            "map_id": map_id,
            "map_revision": map_revision,
            "annotation_revision": "e" * 64,
            "points": points,
            "polygons": polygons,
        }


class MappingCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.manager = FakeMappingManager()
        self.catalog = FakeSavedMapCatalog()
        self.lock = asyncio.Lock()
        self.manager.coordination_lock = self.lock
        self.navigation_is_active = False
        self.control_lease_is_active = False
        self.dataset_is_active = False
        self.lifecycle_calls = 0

        def lifecycle_idle():
            self.lifecycle_calls += 1

        self.coordinator = MappingCoordinator(
            self.manager,
            self.catalog,
            coordination_lock=self.lock,
            navigation_active=lambda: self.navigation_is_active,
            control_lease_active=lambda: self.control_lease_is_active,
            dataset_capture_active=lambda: self.dataset_is_active,
            require_lifecycle_idle=lifecycle_idle,
            logger=logging.getLogger(__name__),
        )

    async def asyncTearDown(self) -> None:
        task = self.coordinator.task
        if task is not None and not task.done():
            self.manager.save_release.set()
            await task

    async def test_start_uses_shared_lock_and_stop_remains_cleanup_available(self):
        self.assertIs(self.coordinator.coordination_lock, self.lock)

        started = await self.coordinator.start()
        self.assertNotIn("pid", started["pipeline"])
        self.assertNotIn("pid", started["preview"])
        start = next(call for call in self.manager.calls if call[0] == "start_mapping")
        self.assertIs(start[-1], True)
        self.assertEqual(self.lifecycle_calls, 1)

        def unavailable_lifecycle():
            raise AssertionError("STOP must not require lifecycle idle")

        self.coordinator._require_lifecycle_idle = unavailable_lifecycle
        stopped = await self.coordinator.stop()
        self.assertNotIn("pid", stopped["pipeline"])
        self.assertNotIn("pid", stopped["preview"])
        stop = next(call for call in self.manager.calls if call[0] == "stop_mapping")
        self.assertIs(stop[-1], True)

    async def test_navigation_and_background_task_interlocks_fail_closed(self):
        self.navigation_is_active = True
        with self.assertRaisesRegex(
            MappingCoordinatorConflict,
            "navigation must stop before mapping can start",
        ):
            await self.coordinator.start()
        self.assertFalse(any(call[0] == "start_mapping" for call in self.manager.calls))

        failing = MappingCoordinator(
            self.manager,
            self.catalog,
            coordination_lock=self.lock,
            navigation_active=lambda: (_ for _ in ()).throw(RuntimeError("unknown")),
            control_lease_active=lambda: False,
            dataset_capture_active=lambda: False,
            require_lifecycle_idle=lambda: None,
        )
        with self.assertRaises(MappingCoordinatorConflict):
            await failing.stop()

        class UnreadableTask:
            def done(self):
                raise RuntimeError("task state unavailable")

        self.coordinator._task = UnreadableTask()
        self.assertTrue(self.coordinator.task_active())
        self.navigation_is_active = False
        with self.assertRaisesRegex(MappingCoordinatorConflict, "map save must finish"):
            await self.coordinator.stop()
        self.coordinator._task = None

    async def test_mapping_start_rejects_control_lease_and_dataset_capture(self):
        self.control_lease_is_active = True
        with self.assertRaisesRegex(MappingCoordinatorConflict, "control lease"):
            await self.coordinator.start()
        self.control_lease_is_active = False
        self.dataset_is_active = True
        with self.assertRaisesRegex(MappingCoordinatorConflict, "dataset capture"):
            await self.coordinator.start()
        self.assertFalse(any(call[0] == "start_mapping" for call in self.manager.calls))

    async def test_running_localization_is_shared_but_transitions_and_work_block(self):
        self.manager.pipeline_state = "running"
        busy, blockers = self.coordinator.activity()
        self.assertFalse(busy)
        self.assertEqual(blockers, [])
        self.assertEqual(self.coordinator.pipeline_state(), "running")

        self.manager.pipeline_state = "starting"
        self.manager.operation_state = "saving"
        busy, blockers = self.coordinator.activity()
        self.assertTrue(busy)
        self.assertEqual(
            blockers,
            ["mapping_transition", "mapping_operation_active"],
        )

        self.manager.pipeline_state = "stopped"
        self.assertEqual(self.coordinator.pipeline_state(), "idle")
        self.manager.pipeline_state = "invented"
        self.assertEqual(self.coordinator.pipeline_state(), "failed")

    async def test_save_owns_one_background_task_and_preserves_public_response(self):
        self.manager.block_save = True
        response = await self.coordinator.save("classroom", create_2d=True)
        self.assertEqual(
            response,
            {
                "accepted": True,
                "map_name": "classroom",
                "kind": "pointcloud3d_2d",
            },
        )
        await asyncio.to_thread(self.manager.save_entered.wait, 1.0)
        self.assertTrue(self.coordinator.task_active())
        with self.assertRaisesRegex(
            MappingCoordinatorConflict,
            "another map save is already in progress",
        ):
            await self.coordinator.save("replacement", create_2d=False)
        self.manager.save_release.set()
        await self.coordinator.task
        self.assertFalse(self.coordinator.task_active())
        self.assertIn(
            ("save_map", "classroom", "pointcloud3d_2d", False),
            self.manager.calls,
        )

    async def test_missing_save_recipe_is_unavailable_before_task_creation(self):
        self.manager.allowed_save_kinds = ("pointcloud3d",)
        with self.assertRaisesRegex(
            MappingCoordinatorUnavailable,
            "requested map save recipe is unavailable",
        ):
            await self.coordinator.save("classroom", create_2d=True)
        self.assertIsNone(self.coordinator.task)

    async def test_conversion_keeps_revision_and_exact_operation_job_fences(self):
        response = await self.coordinator.convert_pcd_to_2d(
            "opaque-map-id",
            "floor-copy",
            {"resolution": 0.05},
        )
        self.assertEqual(response["job_id"], "a" * 32)
        self.assertEqual(response["kind"], "pcd_to_2d")
        self.assertEqual(response["source"]["revision"], "b" * 64)
        await self.coordinator.task

        self.assertIn(
            ("reserve_local_operation", "pcd_to_2d", "floor-copy", True),
            self.manager.calls,
        )
        self.assertIn(
            ("run_reserved_local_operation", "a" * 32, False),
            self.manager.calls,
        )
        conversion = next(call for call in self.catalog.calls if call[0] == "convert")
        self.assertEqual(conversion[1:3], ("opaque-map-id", "floor-copy"))
        self.assertEqual(conversion[3]["expected_revision"], "b" * 64)
        self.assertIn(("cancelled", False), self.catalog.calls)
        self.assertIn(("publication_guard", True), self.catalog.calls)

    async def test_conversion_schedule_failure_releases_exact_reservation(self):
        with patch(
            "robot_dashboard.application.mapping_coordinator.asyncio.create_task",
            side_effect=RuntimeError("scheduler closed"),
        ):
            with self.assertRaisesRegex(
                MappingCoordinatorUnavailable,
                "map conversion worker could not be scheduled",
            ):
                await self.coordinator.convert_pcd_to_2d(
                    "opaque-map-id",
                    "floor-copy",
                    {"resolution": 0.05},
                )
        self.assertIn(
            (
                "fail_reserved_local_operation",
                "a" * 32,
                "map conversion worker could not be scheduled",
                True,
            ),
            self.manager.calls,
        )

    async def test_saved_map_mutations_preserve_opaque_arguments_and_interlocks(self):
        edited = await self.coordinator.save_edited_copy(
            "opaque-source",
            "edited-copy",
            "d" * 64,
            [{"row": 4, "start": 5, "end": 7, "value": 100}],
        )
        renamed = await self.coordinator.rename("opaque-edited", "new-name")
        deleted = await self.coordinator.delete("opaque-old")
        self.assertEqual(edited["id"], "edited-map")
        self.assertEqual(renamed["name"], "new-name")
        self.assertEqual(deleted["id"], "opaque-old")
        self.assertEqual(self.lifecycle_calls, 3)

        self.navigation_is_active = True
        before = list(self.catalog.calls)
        with self.assertRaises(MappingCoordinatorConflict):
            await self.coordinator.rename("opaque-edited", "blocked")
        self.assertEqual(self.catalog.calls, before)

    async def test_annotation_update_uses_exact_revision_pins_and_shared_gates(self):
        points = [{"id": None, "type": "HOME", "name": "Home", "x": 1.0, "y": 2.0, "yaw": 0.0}]
        polygons = [{"id": None, "type": "WAIT_ZONE", "name": "Wait", "vertices": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 0.0, "y": 1.0}]}]
        result = await self.coordinator.update_annotations(
            "f" * 24,
            "a" * 64,
            "b" * 64,
            points,
            polygons,
        )
        self.assertEqual(result["annotation_revision"], "e" * 64)
        self.assertEqual(
            self.catalog.calls[-1],
            (
                "annotations",
                "f" * 24,
                "a" * 64,
                "b" * 64,
                points,
                polygons,
            ),
        )
        self.assertEqual(self.lifecycle_calls, 1)

        self.navigation_is_active = True
        before = list(self.catalog.calls)
        with self.assertRaisesRegex(
            MappingCoordinatorConflict,
            "navigation must stop before map annotations can be changed",
        ):
            await self.coordinator.update_annotations(
                "f" * 24,
                "a" * 64,
                "b" * 64,
                [],
                [],
            )
        self.assertEqual(self.catalog.calls, before)

    async def test_nav_dependency_port_delegates_exact_job_identity(self):
        snapshot = self.coordinator.snapshot(since_log_seq=19)
        self.assertEqual(snapshot["pipeline"]["job_id"], "a" * 32)
        self.assertNotIn("pid", snapshot["pipeline"])
        self.assertNotIn("pid", snapshot["preview"])
        self.coordinator.start_mapping()
        stopped, _ = self.coordinator.stop_mapping_if_job_id("a" * 32)
        self.assertTrue(stopped)
        self.assertIn(
            ("stop_mapping_if_job_id", "a" * 32, False),
            self.manager.calls,
        )

    async def test_preview_and_close_delegate_without_reimplementing_processes(self):
        preview = await self.coordinator.start_preview()
        self.assertEqual(preview["preview"]["state"], "running")
        self.assertNotIn("pid", preview["preview"])
        await self.coordinator.close()
        self.assertTrue(any(call[0] == "close" for call in self.manager.calls))


class MappingCoordinatorArchitectureTests(unittest.TestCase):
    def test_application_component_has_no_transport_or_process_implementation(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertFalse(any(name.startswith("fastapi") for name in imports))
        self.assertNotIn("subprocess", imports)
        self.assertNotIn("pathlib", imports)
        self.assertNotIn("os", imports)
        self.assertNotIn("Popen", source)
        self.assertNotIn("shell=", source)


if __name__ == "__main__":
    unittest.main()
