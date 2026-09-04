import asyncio
import ast
import logging
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from robot_dashboard.application.mapping_coordinator import MappingCoordinator
from robot_dashboard.mapping_jobs import (
    MappingJobError,
    MappingJobManager,
    wireless_preview_auto_recovery_enabled,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeManager:
    allowed_save_kinds = ()

    def __init__(self) -> None:
        self.preview_auto_recovery_enabled = False
        self.preview_state = "failed"
        self.pipeline_state = "idle"
        self.operation_state = "idle"
        self.calls: list[str] = []
        self.block_preview_start = False
        self.raise_preview_start = False
        self.preview_start_entered = threading.Event()
        self.preview_start_release = threading.Event()

    def snapshot(self, *, since_log_seq=0):
        self.calls.append("snapshot")
        return {
            "preview": {"state": self.preview_state, "pid": None},
            "pipeline": {"state": self.pipeline_state, "pid": None},
            "operation": {"state": self.operation_state},
            "logs": [],
        }

    def start_preview(self):
        self.calls.append("start_preview")
        if self.raise_preview_start:
            raise MappingJobError("preview spawn failed")
        self.preview_start_entered.set()
        if self.block_preview_start:
            self.preview_start_release.wait(timeout=2.0)
        self.preview_state = "running"
        self.calls.append("start_preview_finished")
        return self.snapshot()

    def close(self):
        self.calls.append("close")


class FakeCatalog:
    pass


class Xt16PreviewAutoRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def make_coordinator(self, *, enabled=False):
        manager = FakeManager()
        manager.preview_auto_recovery_enabled = enabled
        state = {
            "navigation": False,
            "control": False,
            "dataset": False,
            "lifecycle": False,
        }

        def lifecycle_idle():
            if state["lifecycle"]:
                raise RuntimeError("transition active")

        coordinator = MappingCoordinator(
            manager,
            FakeCatalog(),
            coordination_lock=asyncio.Lock(),
            navigation_active=lambda: state["navigation"],
            control_lease_active=lambda: state["control"],
            dataset_capture_active=lambda: state["dataset"],
            require_lifecycle_idle=lifecycle_idle,
            logger=logging.getLogger(__name__),
        )
        return coordinator, manager, state

    async def test_default_off_and_singleton_task(self):
        disabled, _, _ = self.make_coordinator()
        self.assertFalse(disabled.start_preview_auto_recovery())

        enabled, _, _ = self.make_coordinator(enabled=True)
        self.assertTrue(enabled.start_preview_auto_recovery())
        first = enabled._preview_recovery_task
        self.assertIsNotNone(first)
        self.assertFalse(enabled.start_preview_auto_recovery())
        self.assertIs(enabled._preview_recovery_task, first)
        await enabled.stop_preview_auto_recovery()
        self.assertIsNone(enabled._preview_recovery_task)
        self.assertTrue(first.done())

    async def test_retries_only_failed_preview_when_every_owner_is_idle(self):
        coordinator, manager, state = self.make_coordinator(enabled=True)
        for preview_state in ("idle", "starting", "running", "stopped", "disabled"):
            manager.preview_state = preview_state
            self.assertFalse(await coordinator._recover_failed_preview_if_safe())
        self.assertNotIn("start_preview", manager.calls)

        manager.preview_state = "failed"
        for blocker in ("navigation", "control", "dataset", "lifecycle"):
            state[blocker] = True
            self.assertFalse(await coordinator._recover_failed_preview_if_safe())
            state[blocker] = False
        for pipeline_state in ("starting", "running", "stopping"):
            manager.pipeline_state = pipeline_state
            self.assertFalse(await coordinator._recover_failed_preview_if_safe())
        manager.pipeline_state = "failed"
        manager.operation_state = "saving"
        self.assertFalse(await coordinator._recover_failed_preview_if_safe())
        self.assertNotIn("start_preview", manager.calls)

        manager.operation_state = "succeeded"
        self.assertTrue(await coordinator._recover_failed_preview_if_safe())
        self.assertEqual(manager.calls.count("start_preview"), 1)
        self.assertEqual(manager.pipeline_state, "failed")

    async def test_monitor_retries_with_bounded_backoff_and_close_stops_first(self):
        coordinator, manager, _ = self.make_coordinator(enabled=True)
        with patch(
            "robot_dashboard.application.mapping_coordinator."
            "PREVIEW_RECOVERY_INITIAL_DELAY_S",
            0.01,
        ), patch(
            "robot_dashboard.application.mapping_coordinator."
            "PREVIEW_RECOVERY_MAX_DELAY_S",
            0.02,
        ):
            coordinator.start_preview_auto_recovery()
            for _ in range(20):
                if "start_preview" in manager.calls:
                    break
                await asyncio.sleep(0.01)
            self.assertIn("start_preview", manager.calls)
            await coordinator.close()
        self.assertIsNone(coordinator._preview_recovery_task)
        self.assertEqual(manager.calls[-1], "close")

    async def test_close_settles_inflight_thread_before_manager_cleanup(self):
        coordinator, manager, _ = self.make_coordinator(enabled=True)
        manager.block_preview_start = True
        with patch(
            "robot_dashboard.application.mapping_coordinator."
            "PREVIEW_RECOVERY_INITIAL_DELAY_S",
            0.01,
        ):
            coordinator.start_preview_auto_recovery()
            entered = await asyncio.to_thread(
                manager.preview_start_entered.wait,
                1.0,
            )
            self.assertTrue(entered)
            closing = asyncio.create_task(coordinator.close())
            await asyncio.sleep(0.02)
            self.assertNotIn("close", manager.calls)
            manager.preview_start_release.set()
            await asyncio.wait_for(closing, timeout=1.0)

        self.assertLess(
            manager.calls.index("start_preview_finished"),
            manager.calls.index("close"),
        )
        self.assertIsNone(coordinator._preview_recovery_task)

    async def test_close_settles_worker_after_external_monitor_cancellation(self):
        coordinator, manager, _ = self.make_coordinator(enabled=True)
        manager.block_preview_start = True
        with patch(
            "robot_dashboard.application.mapping_coordinator."
            "PREVIEW_RECOVERY_INITIAL_DELAY_S",
            0.01,
        ):
            coordinator.start_preview_auto_recovery()
            monitor = coordinator._preview_recovery_task
            self.assertIsNotNone(monitor)
            entered = await asyncio.to_thread(
                manager.preview_start_entered.wait,
                1.0,
            )
            self.assertTrue(entered)
            monitor.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await monitor

            closing = asyncio.create_task(coordinator.close())
            await asyncio.sleep(0.02)
            self.assertNotIn("close", manager.calls)
            manager.preview_start_release.set()
            await asyncio.wait_for(closing, timeout=1.0)

        self.assertLess(
            manager.calls.index("start_preview_finished"),
            manager.calls.index("close"),
        )
        self.assertIsNone(coordinator._preview_recovery_inflight)

    async def test_cancelled_close_still_settles_worker_before_manager_cleanup(self):
        coordinator, manager, _ = self.make_coordinator(enabled=True)
        manager.block_preview_start = True
        with patch(
            "robot_dashboard.application.mapping_coordinator."
            "PREVIEW_RECOVERY_INITIAL_DELAY_S",
            0.01,
        ):
            coordinator.start_preview_auto_recovery()
            entered = await asyncio.to_thread(
                manager.preview_start_entered.wait,
                1.0,
            )
            self.assertTrue(entered)

            closing = asyncio.create_task(coordinator.close())
            await asyncio.sleep(0.02)
            closing.cancel()
            await asyncio.sleep(0.02)
            self.assertNotIn("close", manager.calls)
            manager.preview_start_release.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(closing, timeout=1.0)

        self.assertLess(
            manager.calls.index("start_preview_finished"),
            manager.calls.index("close"),
        )
        self.assertIsNone(coordinator._preview_recovery_task)
        self.assertIsNone(coordinator._preview_recovery_inflight)

    def test_app_opt_in_is_exact_and_wireless_only(self):
        for mapping_profile in (
            "go2-xt16-wireless",
            "go2-xt16-wireless-competition-fastlio",
        ):
            self.assertTrue(
                wireless_preview_auto_recovery_enabled(
                    mapping_profile,
                    True,
                    {"ROBOT_SCOPE_XT16_PREVIEW_AUTO_RECOVER": "1"},
                )
            )
            for value in ("", "0", "true", "TRUE", "yes"):
                self.assertFalse(
                    wireless_preview_auto_recovery_enabled(
                        mapping_profile,
                        True,
                        {"ROBOT_SCOPE_XT16_PREVIEW_AUTO_RECOVER": value},
                    )
                )

        for mapping_profile in (
            "go2-xt16-wired",
            "competition-pdf-direct",
            "unknown",
        ):
            self.assertFalse(
                wireless_preview_auto_recovery_enabled(
                    mapping_profile,
                    True,
                    {"ROBOT_SCOPE_XT16_PREVIEW_AUTO_RECOVER": "1"},
                )
            )

        self.assertFalse(
            wireless_preview_auto_recovery_enabled(
                "go2-xt16-wireless",
                False,
                {"ROBOT_SCOPE_XT16_PREVIEW_AUTO_RECOVER": "1"},
            )
        )

    async def test_initial_preview_starts_one_monitor(self):
        coordinator, manager, _ = self.make_coordinator(enabled=True)
        snapshot = await coordinator.start_preview()
        self.assertEqual(snapshot["preview"]["state"], "running")
        self.assertIsNotNone(coordinator._preview_recovery_task)
        await coordinator.stop_preview_auto_recovery()

    async def test_initial_preview_failure_still_starts_monitor(self):
        coordinator, manager, _ = self.make_coordinator(enabled=True)
        manager.raise_preview_start = True
        with self.assertRaisesRegex(MappingJobError, "preview spawn failed"):
            await coordinator.start_preview()
        self.assertIsNotNone(coordinator._preview_recovery_task)
        await coordinator.stop_preview_auto_recovery()

    async def test_cancelled_initial_preview_does_not_start_monitor(self):
        coordinator, _, _ = self.make_coordinator(enabled=True)
        with patch(
            "robot_dashboard.application.mapping_coordinator.asyncio.to_thread",
            side_effect=asyncio.CancelledError,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await coordinator.start_preview()
        self.assertIsNone(coordinator._preview_recovery_task)

    def test_manager_factory_derives_opt_in_and_rejects_override(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "maps"
            with patch.dict(
                os.environ,
                {"ROBOT_SCOPE_XT16_PREVIEW_AUTO_RECOVER": "1"},
            ):
                wireless = MappingJobManager.for_robot_scope(
                    project_dir=ROOT,
                    output_dir=output,
                    save_commands={},
                    enable_preview=True,
                    mapping_profile="go2-xt16-wireless",
                )
                wired = MappingJobManager.for_robot_scope(
                    project_dir=ROOT,
                    output_dir=output,
                    save_commands={},
                    enable_preview=True,
                    mapping_profile="go2-xt16-wired",
                )
                preview_off = MappingJobManager.for_robot_scope(
                    project_dir=ROOT,
                    output_dir=output,
                    save_commands={},
                    enable_preview=False,
                    mapping_profile="go2-xt16-wireless",
                )
            self.assertTrue(wireless.preview_auto_recovery_enabled)
            self.assertFalse(wired.preview_auto_recovery_enabled)
            self.assertFalse(preview_off.preview_auto_recovery_enabled)
            for manager in (wireless, wired, preview_off):
                manager.close()

            with self.assertRaisesRegex(TypeError, "derived from the fixed profile"):
                MappingJobManager.for_robot_scope(
                    project_dir=ROOT,
                    output_dir=output,
                    save_commands={},
                    preview_auto_recovery_enabled=True,
                )

    def test_lifespan_delegates_monitor_cleanup_to_mapping_close(self):
        source = (ROOT / "robot_dashboard" / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        lifespan = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan"
        )
        segment = ast.get_source_segment(source, lifespan)
        self.assertEqual(segment.count("start_preview_auto_recovery()"), 0)
        self.assertEqual(segment.count("stop_preview_auto_recovery()"), 0)
        self.assertIn("await runtime.mapping.start_preview()", segment)
        self.assertIn(
            "try:\n            if runtime.mapping is not None:\n"
            "                await runtime.mapping.close()\n"
            "        finally:\n            runtime.agent.stop()",
            segment,
        )

if __name__ == "__main__":
    unittest.main()
