"""SYNTHETIC lifecycle fixtures; native files below are not engine evidence."""

import asyncio
from copy import deepcopy
from pathlib import Path
import tempfile
import threading
import unittest

from robot_dashboard.slam_packages import MapPackageError, MapPackageStore
from robot_dashboard.slam_sessions import FastLioAdapter, SlamError, SlamSessionManager


COMPATIBILITY = dict(engine_id="visual_stereo", engine_version="synthetic-1",
    native_format_version="fixture-native-v1", calibration_hash="a" * 64,
    sensor_config_hash="b" * 64)
HINT = dict(frame_id="map", position=[1.0, 2.0, 3.0],
            quaternion_xyzw=[0.0, 0.0, 0.0, 1.0], operator_verified=True)


class SyntheticEngine:
    """Injectable owner whose gates make lifecycle races deterministic."""
    def __init__(self):
        self.calls = []
        self.start_entered = threading.Event()
        self.start_gate = threading.Event()
        self.start_gate.set()
        self.save_entered = threading.Event()
        self.save_gate = threading.Event()
        self.save_gate.set()
        self.preflight_error = None
        self.start_error = None
        self.stop_error = None
        self.save_error = None
        self.status_error = None
        self.health = dict(ready=True, alive=True)
        self.owner = None
        self.saved_complete = True
        self.stale_frame = False
        self.stale_epoch = False
        self.localize_result = dict(native_load="SUCCEEDED", localize_success=True)
        self.compatibility = deepcopy(COMPATIBILITY)

    def capability(self):
        return dict(supported_in_source=True, installed=True, available_now=True,
                    tasks=["tracking", "mapping"], compatibility=deepcopy(self.compatibility),
                    software_verified=False, hardware_verified=False)

    def preflight(self, task):
        self.calls.append(("preflight", task))
        if self.preflight_error:
            raise self.preflight_error

    def start(self, session, cancel):
        self.calls.append(("start", session["session_id"]))
        self.start_entered.set()
        if not self.start_gate.wait(3):
            raise RuntimeError("synthetic gate timeout")
        if self.start_error:
            raise self.start_error
        self.owner = (session["session_id"], session["generation"])
        return dict(effective_mode="synthetic-slam", ready=self.health["ready"])

    def stop(self, session):
        self.calls.append(("stop", session["session_id"]))
        if self.stop_error:
            raise self.stop_error
        self.owner = None

    def status(self, session):
        if self.status_error:
            raise self.status_error
        return dict(self.health)

    def frame(self, session):
        return dict(session_id=session["session_id"],
            generation=session["generation"]-1 if self.stale_frame else session["generation"],
            map_epoch="previous-epoch" if self.stale_epoch else session["map_epoch"],
            provenance="synthetic_fixture", image_jpeg_base64="private-camera-pixels",
            global_map=dict(points=[[1, 2, 3]], coverage="unknown", engine_total_count=None))

    def save(self, session, native_path):
        self.calls.append(("save", session["session_id"]))
        self.save_entered.set()
        if not self.save_gate.wait(3):
            raise RuntimeError("synthetic gate timeout")
        (native_path / "data.mdb").write_bytes(b"SYNTHETIC native fixture")
        if self.save_error:
            raise self.save_error
        return dict(official_save_completed=self.saved_complete,
                    required_native_files=["data.mdb"], data_provenance="synthetic_fixture",
                    metadata={**COMPATIBILITY, "map_frame": "map", "units": "m", "axes": "ros"})

    def localize(self, session, native_path, hint):
        self.calls.append(("localize", str(native_path)))
        self.received_hint = deepcopy(hint)
        (native_path / "data.mdb").write_bytes(b"SYNTHETIC scratch update")
        return deepcopy(self.localize_result)


class SyntheticCamera:
    def __init__(self):
        self.owner = None
        self.acquisitions = []
        self.releases = []

    def acquire(self, session):
        if self.owner:
            raise RuntimeError("synthetic camera conflict")
        self.owner = (session["session_id"], session["generation"])
        self.acquisitions.append(self.owner)

    def release(self, session):
        identity = session["session_id"], session["generation"]
        if identity != self.owner:
            raise RuntimeError("synthetic owner mismatch")
        self.releases.append(identity)
        self.owner = None

    def release_if_owned(self, session):
        if self.owner == (session["session_id"], session["generation"]):
            self.release(session)

    def snapshot(self):
        return {"reserved": self.owner is not None}


class SlamSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = MapPackageStore(self.root / "packages", quiescence_seconds=0.001)
        self.engine = SyntheticEngine()
        self.camera = SyntheticCamera()
        self.blockers = []
        self.context = dict(operational_pose=dict(source="existing-lidar", generation="99"),
                            navigation_map={"id": "existing-map"})
        self.lock = asyncio.Lock()
        self.manager = SlamSessionManager({"visual_stereo": self.engine}, self.store,
            coordination_lock=self.lock, blockers=lambda: list(self.blockers),
            navigation_context=lambda: deepcopy(self.context), camera=self.camera)

    async def asyncTearDown(self):
        self.engine.start_gate.set()
        self.engine.save_gate.set()
        self.engine.stop_error = None
        self.engine.status_error = None
        await asyncio.wait_for(self.manager.close(), 3)
        self.temporary.cleanup()

    async def settled(self):
        operation = self.manager._operation
        if operation:
            await asyncio.wait_for(asyncio.shield(operation), 3)

    async def start(self, task="mapping", request_id="start-0001"):
        result = await self.manager.start(engine_id="visual_stereo", task=task,
            request_id=request_id, operator_confirmed=True)
        await self.settled()
        return result

    async def error(self, code, awaitable):
        with self.assertRaises(SlamError) as raised:
            await awaitable
        self.assertEqual(raised.exception.code, code)

    async def saved_package(self, started):
        result = await self.manager.save(started["session_id"], generation=started["generation"],
                                         request_id="save-0001", name="Synthetic room")
        await self.settled()
        job = self.manager.job(result["job_id"])
        self.assertEqual(job["state"], "SUCCEEDED", job)
        return job["package"]

    async def test_catalog_snapshot_and_frames_never_start_a_driver(self):
        self.assertFalse(self.manager.blocks_context_change())
        self.assertIsNone(self.manager.snapshot()["active_session"])
        self.manager.engines()
        self.manager.navigation_context()
        self.assertEqual(self.manager.frame()["reason"], "NO_ACTIVE_STREAM")
        self.assertEqual(self.engine.calls, [])
        self.assertEqual(self.camera.acquisitions, [])
        self.assertEqual(self.manager.navigation_context(), self.context)

    async def test_start_is_idempotent_and_preserves_operational_context(self):
        result = await self.start()
        duplicate = await self.manager.start(engine_id="visual_stereo", task="mapping",
            request_id="start-0001", operator_confirmed=True)
        self.assertEqual(duplicate, result)
        self.assertEqual(len([c for c in self.engine.calls if c[0] == "start"]), 1)
        self.assertEqual(len(self.camera.acquisitions), 1)
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "MAPPING")
        self.assertFalse(self.manager.snapshot()["active_session"]["operational_pose_applied"])
        self.assertEqual(self.manager.navigation_context(), self.context)
        await self.error("REQUEST_ID_CONFLICT", self.manager.start(engine_id="visual_stereo",
            task="tracking", request_id="start-0001", operator_confirmed=True))

    async def test_delayed_health_cannot_revive_stopped_or_replace_new_session(self):
        first = await self.start()
        entered, release = threading.Event(), threading.Event()
        def delayed_status(session):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("synthetic health timeout")
            return dict(alive=False, ready=False)
        self.engine.status = delayed_status
        pending = asyncio.create_task(asyncio.to_thread(self.manager.snapshot))
        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
        try:
            await self.manager.stop(first["session_id"], generation=first["generation"],
                request_id="stop-race-0001", discard_unsaved=True)
            await self.settled()
            second = await self.start(request_id="start-race-0002")
        finally:
            release.set()
        result = await pending
        self.assertEqual(result["active_session"]["session_id"], second["session_id"])
        self.assertEqual(self.manager._session["state"], "MAPPING")

    async def test_save_checks_current_health_without_prior_viewer_poll(self):
        started = await self.start()
        self.engine.health["ready"] = False
        await self.error("MAPPING_NOT_READY", self.manager.save(started["session_id"],
            generation=started["generation"], request_id="save-health-0001", name="room"))
        self.engine.health["ready"] = True
        await self.saved_package(started)

    async def test_request_confirmation_allowlist_and_resource_blockers_fail_before_launch(self):
        await self.error("OPERATOR_CONFIRMATION_REQUIRED", self.manager.start(
            engine_id="visual_stereo", task="mapping", request_id="request-0001"))
        await self.error("ENGINE_UNAVAILABLE", self.manager.start(engine_id="arbitrary-shell",
            task="mapping", request_id="request-0002", operator_confirmed=True))
        await self.error("MODE_UNSUPPORTED", self.manager.start(engine_id="visual_stereo",
            task="localize_saved", request_id="request-0003", operator_confirmed=True))
        await self.error("INVALID_REQUEST_ID", self.manager.start(engine_id="visual_stereo",
            task="mapping", request_id="../bad/argument", operator_confirmed=True))
        self.blockers.append("control_lease")
        await self.error("RESOURCE_CONFLICT", self.manager.start(engine_id="visual_stereo",
            task="mapping", request_id="request-0004", operator_confirmed=True))
        self.assertEqual(self.engine.calls, [])
        self.assertEqual(self.camera.acquisitions, [])

    async def test_shared_coordination_lock_orders_existing_context_mutation_before_start(self):
        await self.lock.acquire()
        task = asyncio.create_task(self.manager.start(engine_id="visual_stereo", task="mapping",
            request_id="start-0001", operator_confirmed=True))
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        self.assertEqual(self.engine.calls, [])
        self.blockers.append("navigation_transition")
        self.lock.release()
        await self.error("RESOURCE_CONFLICT", task)

    async def test_resource_conflict_preserves_specific_blocker_and_never_launches(self):
        self.blockers.extend(["navigation_active", "control_lease_active", "/private/state"])
        with self.assertRaises(SlamError) as raised:
            await self.manager.start(engine_id="visual_stereo", task="mapping",
                request_id="resource-detail-01", operator_confirmed=True)
        self.assertEqual(raised.exception.resources, [
            {"resource": "navigation", "reason": "navigation_active"},
            {"resource": "control", "reason": "control_lease_active"}])
        self.assertEqual(self.engine.calls, [])

    async def test_async_broker_conflict_survives_owned_cleanup_for_display(self):
        self.engine.preflight_error = SlamError("RESOURCE_CONFLICT", resources=[
            {"resource": "ros_domain", "reason": "domain_busy"}])
        await self.manager.start(engine_id="visual_stereo", task="mapping",
            request_id="resource-detail-02", operator_confirmed=True)
        await self.settled()
        current = self.manager.snapshot()["active_session"]
        self.assertEqual(current["state"], "IDLE")
        self.assertEqual(current["reason"], "RESOURCE_CONFLICT")
        self.assertEqual(current["resource_conflicts"], [
            {"resource": "ros_domain", "reason": "domain_busy"}])
        self.assertEqual(self.camera.acquisitions, [])

    async def test_two_concurrent_starts_cannot_own_two_sessions(self):
        self.engine.start_gate.clear()
        first = await self.manager.start(engine_id="visual_stereo", task="mapping",
            request_id="start-0001", operator_confirmed=True)
        await self.error("SLAM_SESSION_ACTIVE", self.manager.start(engine_id="visual_stereo",
            task="mapping", request_id="start-0002", operator_confirmed=True))
        self.assertTrue(self.manager.blocks_context_change())
        with self.assertRaisesRegex(SlamError, "SLAM_SESSION_ACTIVE"):
            self.manager.require_context_idle()
        self.engine.start_gate.set()
        await self.settled()
        self.assertEqual(self.manager.snapshot()["active_session"]["session_id"], first["session_id"])

    async def test_stop_during_start_waits_for_owned_child_and_releases_exact_camera(self):
        self.engine.start_gate.clear()
        started = await self.manager.start(engine_id="visual_stereo", task="mapping",
            request_id="start-0001", operator_confirmed=True)
        self.assertTrue(await asyncio.to_thread(self.engine.start_entered.wait, 2))
        stopped = await self.manager.stop(started["session_id"], generation=started["generation"],
            request_id="stop-0001")
        self.assertEqual(stopped["state"], "STOPPING")
        self.assertTrue(self.manager.blocks_context_change())
        self.engine.start_gate.set()
        await self.settled()
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "IDLE")
        self.assertEqual(self.camera.acquisitions, self.camera.releases)
        self.assertEqual(len(self.camera.releases), 1)
        self.assertIsNone(self.engine.owner)

    async def test_unsaved_stop_requires_confirmation_but_cleanup_ignores_foreign_blockers(self):
        started = await self.start()
        await self.error("UNSAVED_MAP_CONFIRMATION_REQUIRED", self.manager.stop(started["session_id"],
            generation=started["generation"], request_id="stop-0001"))
        self.blockers.append("foreign_context_transition")
        stopped = await self.manager.stop(started["session_id"], generation=started["generation"],
            request_id="stop-0002", discard_unsaved=True)
        duplicate = await self.manager.stop(started["session_id"], generation=started["generation"],
            request_id="stop-0002", discard_unsaved=True)
        self.assertEqual(stopped, duplicate)
        await self.settled()
        self.assertFalse(self.manager.blocks_context_change())
        self.assertIsNone(self.camera.owner)

    async def test_stale_generation_stop_save_and_frame_are_rejected(self):
        started = await self.start()
        await self.error("SESSION_GENERATION_CONFLICT", self.manager.stop(started["session_id"],
            generation=started["generation"]-1, request_id="stop-0001", discard_unsaved=True))
        await self.error("SESSION_GENERATION_CONFLICT", self.manager.save(started["session_id"],
            generation=started["generation"]+1, request_id="save-0001", name="room"))
        self.engine.stale_frame = True
        with self.assertRaisesRegex(SlamError, "STALE_GENERATION"):
            self.manager.frame()
        self.assertTrue(self.manager.blocks_context_change())

    async def test_same_session_and_generation_with_previous_map_epoch_cannot_stream(self):
        await self.start()
        self.engine.stale_epoch = True
        with self.assertRaises(SlamError):
            self.manager.frame()

    async def test_start_failure_cleans_owned_resources_and_sanitizes_private_error(self):
        self.engine.start_error = RuntimeError("/private/credentials must not leak")
        await self.start()
        session = self.manager.snapshot()["active_session"]
        self.assertEqual(session["state"], "IDLE")
        self.assertEqual(session["reason"], "ENGINE_OPERATION_FAILED")
        self.assertFalse(session["cleanup_required"])
        self.assertIsNone(self.camera.owner)
        self.assertIsNone(self.engine.owner)

    async def test_failed_mapping_start_clears_unsaved_only_after_owned_cleanup(self):
        self.engine.start_error = RuntimeError("synthetic start failed")
        await self.start()
        session = self.manager.snapshot()["active_session"]
        self.assertFalse(session["unsaved"])
        self.assertFalse(self.manager.blocks_context_change())
        self.engine.start_error = None
        await self.start(request_id="retry-start-0002")
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "MAPPING")
        self.assertTrue(self.manager.snapshot()["active_session"]["unsaved"])

    async def test_lost_camera_reserve_ack_reconciles_owner_without_native_start(self):
        acquire = self.camera.acquire
        def lost_ack(session):
            acquire(session)
            raise SlamError("BROKER_TIMEOUT", 503)
        self.camera.acquire = lost_ack
        await self.start()
        session = self.manager.snapshot()["active_session"]
        self.assertEqual(session["state"], "IDLE")
        self.assertEqual(session["reason"], "BROKER_TIMEOUT")
        self.assertFalse(session["cleanup_required"])
        self.assertIsNone(self.camera.owner)
        self.assertFalse(self.manager._camera_owned)
        self.assertFalse(self.manager._camera_acquisition_pending)
        self.assertEqual(self.camera.acquisitions, self.camera.releases)
        self.assertFalse(any(c[0] in {"start", "stop"} for c in self.engine.calls))

    async def test_failed_camera_acquire_leaves_foreign_owner_and_child_untouched(self):
        self.camera.owner = ("synthetic-foreign-producer", 77)
        await self.start()
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "IDLE")
        self.assertEqual(self.camera.owner, ("synthetic-foreign-producer", 77))
        self.assertFalse(self.manager._camera_acquisition_pending)
        self.assertEqual(self.camera.releases, [])
        self.assertFalse(any(c[0] in {"start", "stop"} for c in self.engine.calls))

    async def test_uncertain_reservation_cleanup_blocks_context_and_retry_settles(self):
        acquire, reconcile = self.camera.acquire, self.camera.release_if_owned
        def lost_ack(session):
            acquire(session)
            raise SlamError("BROKER_TIMEOUT", 503)
        def failed_cleanup(session):
            raise SlamError("BROKER_TIMEOUT", 503)
        self.camera.acquire = lost_ack
        self.camera.release_if_owned = failed_cleanup
        started = await self.start()
        session = self.manager.snapshot()["active_session"]
        self.assertEqual(session["state"], "ERROR")
        self.assertEqual(session["reason"], "CLEANUP_REQUIRED")
        self.assertTrue(session["cleanup_required"])
        self.assertTrue(self.manager._camera_acquisition_pending)
        self.assertTrue(self.manager.blocks_context_change())
        self.assertIsNotNone(self.camera.owner)
        self.camera.release_if_owned = reconcile
        await self.manager.stop(started["session_id"], generation=started["generation"],
            request_id="stop-reconcile-0001", discard_unsaved=True)
        await self.settled()
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "IDLE")
        self.assertFalse(self.manager.blocks_context_change())
        self.assertFalse(self.manager._camera_acquisition_pending)
        self.assertIsNone(self.camera.owner)
        self.assertFalse(any(c[0] in {"start", "stop"} for c in self.engine.calls))

    async def test_camera_release_wait_does_not_block_async_event_loop(self):
        started = await self.start()
        entered, release, expired = threading.Event(), threading.Event(), threading.Event()
        original = self.camera.release
        def delayed_release(session):
            entered.set()
            if not release.wait(2):
                expired.set()
            original(session)
        self.camera.release = delayed_release
        try:
            await self.manager.stop(started["session_id"], generation=started["generation"],
                request_id="stop-nonblocking-0001", discard_unsaved=True)
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            await asyncio.sleep(0)
            self.assertFalse(expired.is_set())
            self.assertFalse(self.manager._operation.done())
            self.assertTrue(self.manager.blocks_context_change())
        finally:
            release.set()
            await self.settled()
        self.assertIsNone(self.camera.owner)

    async def test_start_capability_wait_does_not_block_async_event_loop(self):
        entered, release, expired = threading.Event(), threading.Event(), threading.Event()
        original = self.engine.capability
        def delayed_capability():
            entered.set()
            if not release.wait(2):
                expired.set()
            return original()
        self.engine.capability = delayed_capability
        pending = asyncio.create_task(self.manager.start(engine_id="visual_stereo", task="mapping",
            request_id="start-nonblocking-0001", operator_confirmed=True))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            await asyncio.sleep(0)
            self.assertFalse(expired.is_set())
            self.assertFalse(pending.done())
            self.assertIsNone(self.camera.owner)
        finally:
            release.set()
            await pending
            await self.settled()

    async def test_localize_capability_wait_does_not_block_async_event_loop(self):
        started = await self.start()
        package = await self.saved_package(started)
        entered, release, expired = threading.Event(), threading.Event(), threading.Event()
        original = self.engine.capability
        def delayed_capability():
            entered.set()
            if not release.wait(2):
                expired.set()
            return original()
        self.engine.capability = delayed_capability
        pending = asyncio.create_task(self.manager.localize(started["session_id"],
            generation=started["generation"], request_id="localize-nonblocking-0001",
            package_id=package["id"], revision=package["revision"], hint=HINT, discard_unsaved=True))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            await asyncio.sleep(0)
            self.assertFalse(expired.is_set())
            self.assertFalse(pending.done())
            self.assertIsNone(self.manager._scratch)
            self.assertFalse(any(c[0] == "localize" for c in self.engine.calls))
        finally:
            release.set()
            await pending
            await self.settled()

    async def test_cleanup_failure_keeps_reservation_and_blocks_context_until_retry(self):
        started = await self.start()
        self.engine.stop_error = RuntimeError("synthetic child still owns camera")
        await self.manager.stop(started["session_id"], generation=started["generation"],
            request_id="stop-0001", discard_unsaved=True)
        await self.settled()
        session = self.manager.snapshot()["active_session"]
        self.assertEqual(session["state"], "ERROR")
        self.assertTrue(session["cleanup_required"])
        self.assertTrue(self.manager.blocks_context_change())
        self.assertIsNotNone(self.camera.owner)
        self.engine.stop_error = None
        await self.manager.stop(started["session_id"], generation=started["generation"],
            request_id="stop-0002", discard_unsaved=True)
        await self.settled()
        self.assertFalse(self.manager.blocks_context_change())

    async def test_save_completion_publishes_real_fixture_files_and_strips_camera_pixels(self):
        started = await self.start()
        package = await self.saved_package(started)
        self.assertEqual(package["data_provenance"], "synthetic_fixture")
        self.assertFalse(package["navigation_eligible"])
        self.assertEqual(package["preview_consistency"], "approximate")
        preview = self.store.get_preview(package["id"])
        self.assertNotIn("image_jpeg_base64", preview)
        self.assertEqual(preview["global_map"]["points"], [[1, 2, 3]])
        self.assertEqual((self.store.root / "packages" / package["id"] / "native/data.mdb").read_bytes(),
                         b"SYNTHETIC native fixture")
        self.assertTrue(self.manager.snapshot()["active_session"]["unsaved"])

    async def test_save_is_idempotent_and_stop_cannot_interrupt_native_writer(self):
        started = await self.start()
        self.engine.save_gate.clear()
        args = dict(generation=started["generation"], request_id="save-0001", name="room")
        job = await self.manager.save(started["session_id"], **args)
        self.assertTrue(await asyncio.to_thread(self.engine.save_entered.wait, 2))
        self.assertEqual(await self.manager.save(started["session_id"], **args), job)
        await self.error("OPERATION_IN_PROGRESS", self.manager.stop(started["session_id"],
            generation=started["generation"], request_id="stop-0001", discard_unsaved=True))
        await self.error("MAPPING_NOT_READY", self.manager.save(started["session_id"],
            generation=started["generation"], request_id="save-0002", name="second"))
        self.engine.save_gate.set()
        await self.settled()
        self.assertEqual(len(self.store.list_packages()), 1)
        self.assertEqual(len([c for c in self.engine.calls if c[0] == "save"]), 1)

    async def test_incomplete_save_never_publishes_and_cleans_private_staging(self):
        started = await self.start()
        self.engine.saved_complete = False
        result = await self.manager.save(started["session_id"], generation=started["generation"],
            request_id="save-0001", name="room")
        await self.settled()
        self.assertEqual(self.manager.job(result["job_id"])["state"], "FAILED")
        self.assertEqual(self.manager.job(result["job_id"])["reason"], "SAVE_INCOMPLETE")
        self.assertEqual(self.store.list_packages(), [])
        self.assertEqual(list((self.store.root / "staging").iterdir()), [])
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "IDLE")
        self.assertIsNone(self.camera.owner)

    async def test_tracking_mode_and_waiting_input_cannot_save(self):
        started = await self.start(task="tracking")
        await self.error("MAPPING_NOT_READY", self.manager.save(started["session_id"],
            generation=started["generation"], request_id="save-0001", name="room"))
        self.engine.health["ready"] = False
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "WAITING_INPUT")
        self.engine.health["ready"] = True
        self.engine.health["tracking_state"] = "LOST"
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "LOST")
        self.assertIsNotNone(self.camera.owner)

    async def test_save_failure_with_unsettled_writer_keeps_staging_and_camera_reserved(self):
        started = await self.start()
        self.engine.saved_complete = False
        self.engine.stop_error = RuntimeError("synthetic writer still active")
        result = await self.manager.save(started["session_id"], generation=started["generation"],
            request_id="save-0001", name="room")
        await self.settled()
        self.assertEqual(self.manager.job(result["job_id"])["state"], "FAILED")
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "ERROR")
        self.assertTrue(self.manager.blocks_context_change())
        self.assertIsNotNone(self.camera.owner)
        self.assertEqual(self.store.list_packages(), [])
        self.assertTrue(list((self.store.root / "staging").iterdir()))

    async def test_close_waits_for_save_completion_before_releasing_owned_runtime(self):
        started = await self.start()
        self.engine.save_gate.clear()
        await self.manager.save(started["session_id"], generation=started["generation"],
            request_id="save-0001", name="room")
        self.assertTrue(await asyncio.to_thread(self.engine.save_entered.wait, 2))
        closing = asyncio.create_task(self.manager.close())
        await asyncio.sleep(0)
        self.assertFalse(closing.done())
        self.assertFalse(any(c[0] == "stop" for c in self.engine.calls))
        self.assertIsNotNone(self.camera.owner)
        self.engine.save_gate.set()
        await asyncio.wait_for(closing, 3)
        self.assertEqual(len(self.store.list_packages()), 1)
        self.assertIsNone(self.camera.owner)

    async def test_localize_incompatible_calibration_rejects_before_native_load(self):
        started = await self.start()
        package = await self.saved_package(started)
        self.engine.compatibility["calibration_hash"] = "c" * 64
        with self.assertRaises(MapPackageError) as raised:
            await self.manager.localize(started["session_id"], generation=started["generation"],
                request_id="localize-0001", package_id=package["id"],
                revision=package["revision"], hint=HINT, discard_unsaved=True)
        self.assertEqual(raised.exception.code, "MAP_INCOMPATIBLE")
        self.assertIsNone(self.manager._scratch)
        self.assertFalse(any(c[0] == "localize" for c in self.engine.calls))
        self.assertEqual(self.manager.navigation_context(), self.context)

    async def test_child_exit_retains_ownership_for_cleanup_and_stops_stream(self):
        await self.start()
        self.engine.health["alive"] = False
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "ERROR")
        self.assertEqual(self.manager.frame()["reason"], "NO_ACTIVE_STREAM")
        self.assertIsNotNone(self.camera.owner)
        self.assertTrue(self.manager.blocks_context_change())

    async def test_status_probe_failure_persists_error_and_stops_stream(self):
        await self.start()
        self.engine.status_error = RuntimeError("synthetic missing process status")
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "ERROR")
        self.assertEqual(self.manager.frame().get("reason"), "NO_ACTIVE_STREAM")
        self.assertTrue(self.manager.blocks_context_change())

    async def test_localize_requires_verified_hint_matching_map_frame_and_revision(self):
        started = await self.start()
        package = await self.saved_package(started)
        args = dict(generation=started["generation"], package_id=package["id"],
                    revision=package["revision"], discard_unsaved=True)
        for i, hint in enumerate(({}, {**HINT, "operator_verified": False},
                                 {**HINT, "quaternion_xyzw": [0, 0, 0, 0]},
                                 {**HINT, "position": [True, 0, 0]},
                                 {**HINT, "position": [float("nan"), 0, 0]})):
            with self.subTest(hint=i):
                with self.assertRaises(SlamError):
                    await self.manager.localize(started["session_id"], **args,
                        request_id=f"localize-{i:04d}", hint=hint)
        await self.error("POSE_HINT_FRAME_MISMATCH", self.manager.localize(started["session_id"],
            **args, request_id="localize-frame", hint={**HINT, "frame_id": "odom"}))
        with self.assertRaises(MapPackageError) as raised:
            await self.manager.localize(started["session_id"], **(args | dict(revision="0"*64)),
                request_id="localize-revision", hint=HINT)
        self.assertEqual(raised.exception.code, "REVISION_CONFLICT")
        self.assertFalse(any(c[0] == "localize" for c in self.engine.calls))

    async def test_failed_save_after_localize_releases_scratch_and_package_reference(self):
        started = await self.start()
        package = await self.saved_package(started)
        await self.manager.localize(started["session_id"], generation=started["generation"],
            request_id="localize-cleanup-0001", package_id=package["id"],
            revision=package["revision"], hint=HINT, discard_unsaved=True)
        await self.settled()
        self.assertIsNotNone(self.manager._scratch)
        self.engine.save_error = RuntimeError("synthetic failed writer")
        await self.manager.save(started["session_id"], generation=started["generation"],
            request_id="save-cleanup-0002", name="failed")
        await self.settled()
        self.assertIsNone(self.manager._scratch)
        self.assertEqual(list((self.store.root / "scratch").iterdir()), [])
        self.store.delete_package(package["id"], expected_revision=package["revision"])

    async def test_localize_preserves_unsaved_mapping_until_explicit_discard_consent(self):
        started = await self.start()
        package = await self.saved_package(started)
        epoch = self.manager._session["map_epoch"]
        original = self.store.root / "packages" / package["id"] / "native/data.mdb"
        before = original.read_bytes()
        args = dict(generation=started["generation"], package_id=package["id"],
                    revision=package["revision"], hint=HINT, request_id="localize-consent-0001")
        await self.error("UNSAVED_MAP_CONFIRMATION_REQUIRED",
            self.manager.localize(started["session_id"], **args))
        for truthy in (1, "true"):
            await self.error("UNSAVED_MAP_CONFIRMATION_REQUIRED",
                self.manager.localize(started["session_id"], **args, discard_unsaved=truthy))
        self.assertEqual(self.manager._session["map_epoch"], epoch)
        self.assertEqual(self.manager._session["state"], "MAPPING")
        self.assertTrue(self.manager._session["unsaved"])
        self.assertIsNone(self.manager._scratch)
        self.assertEqual(list((self.store.root / "scratch").iterdir()), [])
        self.assertEqual(original.read_bytes(), before)
        self.assertFalse(any(c[0] == "localize" for c in self.engine.calls))
        accepted = await self.manager.localize(started["session_id"], **args, discard_unsaved=True)
        self.assertEqual(accepted["native_load"], "PENDING")
        await self.settled()
        self.assertNotEqual(self.manager._session["map_epoch"], epoch)
        self.assertIsNotNone(self.manager._scratch)
        self.assertEqual(original.read_bytes(), before)
        self.assertEqual(len([c for c in self.engine.calls if c[0] == "localize"]), 1)
        self.assertEqual(await self.manager.localize(started["session_id"], **args,
            discard_unsaved=True), accepted)
        await self.error("REQUEST_ID_CONFLICT",
            self.manager.localize(started["session_id"], **args, discard_unsaved=False))
        self.assertEqual(self.manager.navigation_context(), self.context)

    async def test_native_localize_uses_scratch_retains_original_and_never_changes_navigation(self):
        started = await self.start()
        package = await self.saved_package(started)
        original = self.store.root / "packages" / package["id"] / "native/data.mdb"
        before = original.read_bytes()
        result = await self.manager.localize(started["session_id"], generation=started["generation"],
            request_id="localize-0001", package_id=package["id"], revision=package["revision"],
            hint=HINT, discard_unsaved=True)
        self.assertEqual(result["native_load"], "PENDING")
        await self.settled()
        self.assertEqual(self.manager.snapshot()["active_session"]["localization_result"]["localize_success"], True)
        self.assertEqual(original.read_bytes(), before)
        self.assertEqual(self.engine.received_hint, HINT)
        self.assertEqual(self.manager.navigation_context(), self.context)
        scratch = self.manager._scratch.native_path
        self.assertTrue(scratch.exists())
        with self.assertRaises(MapPackageError):
            self.store.delete_package(package["id"], expected_revision=package["revision"])
        await self.manager.stop(started["session_id"], generation=started["generation"],
            request_id="stop-0001", discard_unsaved=True)
        await self.settled()
        self.assertFalse(scratch.exists())
        self.assertEqual(original.read_bytes(), before)

    async def test_package_mutations_are_blocked_bidirectionally_by_active_session(self):
        started = await self.start()
        package = await self.saved_package(started)
        await self.error("SLAM_SESSION_ACTIVE", self.manager.mutate_package("rename_package", package["id"],
            name="mutated", expected_revision=package["revision"]))
        self.assertEqual(self.store.get_package(package["id"])["name"], "Synthetic room")

    async def test_lidar_adapter_stops_only_its_owned_job(self):
        class ExistingMapping:
            job = "existing-owned-job"
            state = "idle"
            def snapshot(self):
                return {"pipeline": {"job_id": self.job, "state": self.state}}
            def start_mapping(self):
                self.state = "running"
                return self.snapshot()
            def stop_mapping_if_job_id(self, job):
                if self.job != job:
                    return False, self.snapshot()
                self.state = "stopped"
                return True, self.snapshot()
        mapping = ExistingMapping()
        adapter = FastLioAdapter(mapping, input_ready=lambda: True)
        adapter.preflight("mapping")
        adapter.start({}, threading.Event())
        mapping.job = "foreign-new-job"
        with self.assertRaisesRegex(SlamError, "RESOURCE_OWNER_MISMATCH"):
            adapter.stop({})
        self.assertEqual(mapping.state, "running")


if __name__ == "__main__":
    unittest.main()
