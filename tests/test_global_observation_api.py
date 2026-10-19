"""Synthetic ASGI and cancellation checks; never starts ROS or an external backend."""
import asyncio
import copy
import hashlib
import json
import os
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from fastapi import FastAPI

from robot_dashboard.api.routers.global_observation import router
from robot_dashboard.application.global_observation import (
    GlobalObservationCoordinator, close_global_observation, configure_global_observation,
)
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.relocalization.global_observation_jobs import GlobalObservationBusy
from robot_dashboard.saved_maps import SavedMapCatalog, SavedMapConflict, SavedMapFormatError
from robot_dashboard.ros.pointcloud import PointCloudHub


STAMP = "1792026000123456789"
MAP_ID, REVISION = "a" * 24, "b" * 64


class SyntheticCatalog:
    revision = REVISION

    def metadata(self, identifier):
        assert identifier == MAP_ID
        return dict(kind="pointcloud3d", format="pcd-binary", revision=self.revision)

    def raw_global_reference(self, identifier, revision, **kwargs):
        if revision != self.revision:
            raise SavedMapConflict("changed")
        packed = struct.pack("<ddd", 1., 2., 3.)
        return dict(xyz_bytes=packed, encoding="float64_le_xyz", sha256=hashlib.sha256(packed).hexdigest(),
                    array_sha256=hashlib.sha256(packed).hexdigest(), source_sha256="c" * 64,
                    point_count=1, frame_id="camera_init", units="m")


class SyntheticAgent:
    def __init__(self):
        self.armed, self.release = threading.Event(), threading.Event()
        self.epoch = "d" * 32
        self.stamp, self.topic, self.frame = STAMP, "/lidar_points", "hesai_lidar"
        self.pipeline_stage, self.received = "raw", None
        self.calls = []

    def raw_pointcloud_context_snapshot(self):
        return dict(topic=self.topic, frame_id=self.frame, pipeline_stage=self.pipeline_stage,
                    observation=dict(observer_id="e" * 32, publisher_epoch=self.epoch,
                                     source_stamp_ns=self.stamp, received_monotonic_s=(
                                         time.monotonic() if self.received is None else self.received)))

    def request_raw_pointcloud_capture(self, **kwargs):
        self.calls.append(("request", kwargs))
        self.armed.set()
        return dict(capture_id="f" * 24, state="awaiting")

    def raw_pointcloud_capture_snapshot(self, identifier):
        return dict(capture_id=identifier, state="ready" if self.release.is_set() else "awaiting")

    def take_raw_pointcloud_capture(self, identifier):
        packed = struct.pack("<ddd", 0., 0., 0.)
        return dict(xyz_bytes=packed, xyz_sha256=hashlib.sha256(packed).hexdigest(),
                    encoding="float64_le_xyz", captured_points=1, source_points=1,
                    source_frame=self.frame, source_stamp_ns=self.stamp,
                    topic=self.topic, observer_epoch=self.epoch,
                    pipeline_stage=self.pipeline_stage,
                    observation=self.raw_pointcloud_context_snapshot()["observation"],
                    received_monotonic_s=time.monotonic(), receipt_clock="OBSERVER_HOST_MONOTONIC",
                    source_order_preserved=True, nonfinite_rows_preserved=True,
                    zero_rows_preserved=True, sampling_applied=False, spatial_filter_applied=False,
                    transform_applied=False, units="m")

    def cancel_raw_pointcloud_capture(self, identifier):
        self.calls.append(("cancel", identifier))


class SyntheticRunner:
    def __init__(self, available=True):
        self.available, self.entered, self.release = available, threading.Event(), threading.Event()
        self.inputs = []
        self.error = None

    def status(self):
        return dict(available=self.available, reason=None if self.available else "TRUSTED_LOCAL_RUNNER_UNAVAILABLE",
                    backend_id="synthetic")

    def run_arrays(self, *, scan_bytes, map_bytes, context, cancel_event):
        self.inputs.append((scan_bytes, map_bytes, copy.deepcopy(context), cancel_event))
        self.entered.set()
        self.release.wait(3)
        if self.error:
            raise self.error
        return dict(status="OBSERVATION_ONLY_UNVERIFIED", selected_candidate=None, candidates=[],
                    source_stamp_ns=context["source_stamp_ns"])


class GlobalObservationApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent, self.catalog, self.runner = SyntheticAgent(), SyntheticCatalog(), SyntheticRunner()
        self.owner = GlobalObservationCoordinator(self.catalog, self.agent, self.runner)
        self.runtime = ApplicationRuntime(global_observation=self.owner)
        self.app = FastAPI()
        self.app.state.runtime = self.runtime
        self.app.include_router(router)

    async def asyncTearDown(self):
        self.runner.release.set()
        self.owner.close()

    async def request(self, method, path, body=None, origin="http://testserver"):
        headers = {"host": "testserver", "content-type": "application/json"}
        if origin is not None:
            headers["origin"] = origin
        events, sent = [dict(type="http.request", body=json.dumps(body or {}).encode(), more_body=False)], []
        async def receive():
            return events.pop(0) if events else dict(type="http.disconnect")
        async def send(message):
            sent.append(message)
        scope = dict(type="http", asgi={"version": "3.0", "spec_version": "2.4"},
                     http_version="1.1", method=method, scheme="http", path=path, raw_path=path.encode(),
                     query_string=b"", root_path="", server=("testserver", 80), client=("127.0.0.1", 1),
                     headers=[(key.encode(), value.encode()) for key, value in headers.items()])
        await self.app(scope, receive, send)
        status = next(row["status"] for row in sent if row["type"] == "http.response.start")
        content = b"".join(row.get("body", b"") for row in sent if row["type"] == "http.response.body")
        return status, json.loads(content)

    @staticmethod
    def body(**changes):
        return dict(request_id="synthetic-1", map_id=MAP_ID, map_revision=REVISION) | changes

    async def settle(self, job_id):
        for _ in range(300):
            job = self.owner.job(job_id)
            if not job["worker_active"]:
                return job
            await asyncio.sleep(.005)
        self.fail("synthetic worker did not settle")

    async def test_read_unavailable_and_start_never_arms_capture(self):
        self.runner.available = False
        status, value = await self.request("GET", "/api/v1/observations/global-jobs", origin=None)
        self.assertEqual(status, 200)
        self.assertFalse(value["provider"]["available"])
        self.assertIsNone(value["current_result"])
        status, _ = await self.request("POST", "/api/v1/observations/global-jobs", self.body())
        self.assertEqual(status, 503)
        self.assertEqual(self.agent.calls, [])

    async def test_registered_or_map_source_is_not_a_raw_sensor_capture(self):
        self.agent.pipeline_stage = "registered"
        status, value = await self.request("POST", "/api/v1/observations/global-jobs", self.body())
        self.assertEqual(status, 503)
        self.assertEqual(value["detail"], "RAW_OR_CONVERTED_POINTCLOUD_SOURCE_REQUIRED")
        self.assertEqual(self.agent.calls, [])

    async def test_body_paths_and_client_fences_are_forbidden_and_origin_is_required(self):
        for field in ("path", "command", "module", "source_frame", "source_stamp_ns", "observer_epoch", "scan"):
            status, _ = await self.request("POST", "/api/v1/observations/global-jobs", self.body(**{field: "x"}))
            self.assertEqual(status, 422, field)
        for origin in (None, "null", "http://attacker.example"):
            status, _ = await self.request("POST", "/api/v1/observations/global-jobs", self.body(), origin=origin)
            self.assertEqual(status, 403)
        self.assertEqual(self.agent.calls, [])

    async def test_capture_start_is_async_idempotent_and_cancel_preserves_single_owner(self):
        status, job = await self.request("POST", "/api/v1/observations/global-jobs", self.body())
        self.assertEqual(status, 202)
        self.assertEqual(job["state"], "capturing")
        duplicate_status, duplicate = await self.request("POST", "/api/v1/observations/global-jobs", self.body())
        self.assertEqual((duplicate_status, duplicate["job_id"]), (202, job["job_id"]))
        status, _ = await self.request("POST", "/api/v1/observations/global-jobs", self.body(request_id="other"))
        self.assertEqual(status, 409)
        status, _ = await self.request("POST", f"/api/v1/observations/global-jobs/{job['job_id']}/cancel", origin=None)
        self.assertEqual(status, 403)
        status, cancelled = await self.request("POST", f"/api/v1/observations/global-jobs/{job['job_id']}/cancel")
        self.assertEqual((status, cancelled["state"]), (200, "cancelled"))
        settled = await self.settle(job["job_id"])
        self.assertIsNone(settled["result"])
        self.assertEqual(self.runner.inputs, [])

    async def test_original_buffers_exact_stamp_and_historical_result_only(self):
        self.agent.release.set()
        self.runner.release.set()
        status, job = await self.request("POST", "/api/v1/observations/global-jobs", self.body())
        self.assertEqual(status, 202)
        result = await self.settle(job["job_id"])
        self.assertEqual(result["state"], "succeeded", result)
        scan, reference, context, _ = self.runner.inputs[0]
        self.assertEqual(scan, struct.pack("<ddd", 0., 0., 0.))
        self.assertEqual(reference, struct.pack("<ddd", 1., 2., 3.))
        self.assertEqual(context["source_stamp_ns"], STAMP)
        self.assertEqual(context["scan"]["point_count"], 1)
        self.assertIsNone(result["current_result"])
        self.assertIsNone(result["body_pose"])
        self.assertFalse(result["tracking_verified"])
        self.assertEqual(result["operational_application"], "NOT_RUN")
        self.assertEqual(result["result"]["job_id"], result["job_id"])
        self.assertGreaterEqual(result["capture_age_s"], 0)
        self.assertEqual(result["capture_age_basis"], "OBSERVER_HOST_RECEIPT_MONOTONIC_ONLY")
        serialized = json.dumps(result)
        self.assertNotIn("xyz_bytes", serialized)
        self.assertNotIn("input_ticket", serialized)

    async def test_converted_callback_is_complete_only_within_received_xyz_scope(self):
        self.agent.pipeline_stage, self.agent.topic = "converted", "/velodyne_points"
        self.agent.release.set()
        self.runner.release.set()
        job = self.owner.start("converted-fixture", MAP_ID, REVISION)
        result = await self.settle(job["job_id"])
        self.assertEqual(result["state"], "succeeded", result)
        context = result["captured_context"]
        self.assertEqual(context["source_pipeline_stage"], "converted")
        self.assertEqual(context["full_original_scope"], "RECEIVED_POINTCLOUD2_XYZ_ONLY")
        self.assertFalse(context["upstream_processing_verified"])
        self.assertFalse(context["original_raw_sensor_archive"])
        self.assertFalse(context["source_clock_verified"])

    async def test_cancel_before_manager_admission_never_launches_the_runner(self):
        self.agent.release.set()
        entered, release = threading.Event(), threading.Event()
        original = self.owner._manager.start
        def delayed(*args, **kwargs):
            entered.set()
            release.wait(1)
            return original(*args, **kwargs)
        with patch.object(self.owner._manager, "start", side_effect=delayed):
            job = self.owner.start("cancel-admission", MAP_ID, REVISION)
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            self.owner.cancel(job["job_id"])
            release.set()
            result = await self.settle(job["job_id"])
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(self.runner.inputs, [])

    async def test_changed_map_epoch_frame_or_reversed_stamp_discards_late_result(self):
        for name in ("map", "epoch", "frame", "stamp"):
            with self.subTest(name=name):
                self.agent, self.catalog, self.runner = SyntheticAgent(), SyntheticCatalog(), SyntheticRunner()
                owner = GlobalObservationCoordinator(self.catalog, self.agent, self.runner)
                self.agent.release.set()
                job = owner.start("fixture", MAP_ID, REVISION)
                self.assertTrue(await asyncio.to_thread(self.runner.entered.wait, 1))
                if name == "map":
                    self.catalog.revision = "c" * 64
                elif name == "epoch":
                    self.agent.epoch = "f" * 32
                elif name == "frame":
                    self.agent.frame = "other"
                else:
                    self.agent.stamp = str(int(STAMP) - 1)
                self.runner.release.set()
                for _ in range(200):
                    result = owner.job(job["job_id"])
                    if not result["worker_active"]:
                        break
                    await asyncio.sleep(.005)
                self.assertEqual(result["state"], "stale", result)
                self.assertIsNone(result["result"])
                owner.close()

    async def test_cancelled_runner_cannot_release_slot_until_subprocess_owner_returns(self):
        self.agent.release.set()
        job = self.owner.start("fixture", MAP_ID, REVISION)
        self.assertTrue(await asyncio.to_thread(self.runner.entered.wait, 1))
        self.owner.cancel(job["job_id"])
        self.assertTrue(self.runner.inputs[0][3].is_set())
        with self.assertRaises(GlobalObservationBusy):
            self.owner.start("next", MAP_ID, REVISION)
        self.runner.release.set()
        result = await self.settle(job["job_id"])
        self.assertEqual(result["state"], "cancelled")
        self.assertIsNone(result["result"])

    async def test_timeout_suppresses_late_result_and_keeps_worker_owned_until_return(self):
        self.owner.close()
        self.owner = GlobalObservationCoordinator(self.catalog, self.agent, self.runner, timeout_s=.025)
        self.runtime.global_observation = self.owner
        self.agent.release.set()
        job = self.owner.start("fixture-timeout", MAP_ID, REVISION)
        self.assertTrue(await asyncio.to_thread(self.runner.entered.wait, 1))
        for _ in range(100):
            current = self.owner.job(job["job_id"])
            if current["state"] == "timed_out":
                break
            await asyncio.sleep(.005)
        self.assertEqual(current["state"], "timed_out")
        self.assertTrue(current["worker_active"])
        self.assertTrue(self.runner.inputs[0][3].is_set())
        self.runner.release.set()
        result = await self.settle(job["job_id"])
        self.assertEqual(result["state"], "timed_out")
        self.assertIsNone(result["result"])

    async def test_unknown_or_stale_receipt_never_promotes_a_result(self):
        self.agent.release.set()
        job = self.owner.start("fixture-receipt", MAP_ID, REVISION)
        self.assertTrue(await asyncio.to_thread(self.runner.entered.wait, 1))
        self.agent.received = time.monotonic() - 2
        self.runner.release.set()
        result = await self.settle(job["job_id"])
        self.assertEqual(result["state"], "failed")
        self.assertIsNone(result["result"])

    async def test_missing_job_and_unconfigured_runtime_are_explicit(self):
        status, _ = await self.request("GET", "/api/v1/observations/global-jobs/unknown", origin=None)
        self.assertEqual(status, 404)
        self.runtime.global_observation = None
        status, value = await self.request("GET", "/api/v1/observations/global-jobs", origin=None)
        self.assertEqual(status, 200)
        self.assertFalse(value["provider"]["available"])
        status, _ = await self.request("POST", "/api/v1/observations/global-jobs", self.body())
        self.assertEqual(status, 503)

    async def test_shutdown_cleanup_failure_does_not_escape(self):
        logger = SimpleNamespace(exception=lambda *args: None, error=lambda *args: None)
        self.runtime.global_observation = SimpleNamespace(close=lambda: False)
        await close_global_observation(self.runtime, logger)

    async def test_default_factory_never_launches_a_process_or_requests_a_capture(self):
        runtime = ApplicationRuntime(agent=self.agent, saved_maps=self.catalog)
        with patch.dict(os.environ, {}, clear=True), patch(
                "robot_dashboard.relocalization.external_global_observation.subprocess.Popen") as launch:
            configure_global_observation(runtime)
            try:
                self.assertFalse(runtime.global_observation.snapshot()["provider"]["available"])
                with self.assertRaisesRegex(Exception, "TRUSTED_LOCAL_RUNNER_UNAVAILABLE"):
                    runtime.global_observation.start("default-disabled", MAP_ID, REVISION)
                self.assertEqual(self.agent.calls, [])
                launch.assert_not_called()
            finally:
                runtime.global_observation.close()

    async def test_close_cancels_the_runner_and_settles_before_returning(self):
        entered = threading.Event()
        def cooperative(**kwargs):
            entered.set()
            kwargs["cancel_event"].wait(1)
            return dict(status="OBSERVATION_ONLY_UNVERIFIED", selected_candidate=None, candidates=[])
        self.agent.release.set()
        with patch.object(self.runner, "run_arrays", side_effect=cooperative):
            job = self.owner.start("close-fixture", MAP_ID, REVISION)
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            self.assertTrue(await asyncio.to_thread(self.owner.close))
        result = self.owner.job(job["job_id"])
        self.assertEqual(result["state"], "cancelled")
        self.assertFalse(result["worker_active"])
        self.assertIsNone(result["result"])


class RawGlobalReferenceTests(unittest.TestCase):
    def test_original_pcd_xyz_has_no_viewport_filter_rounding_or_row_removal(self):
        points = np.array([[0., 0., 0.], [10000.123456789, 2., 3.], [float("nan"), 4., 5.]], dtype="<f8")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "fixture.pcd"
            header = ("VERSION 0.7\nFIELDS x y z\nSIZE 8 8 8\nTYPE F F F\nCOUNT 1 1 1\n"
                      "WIDTH 3\nHEIGHT 1\nPOINTS 3\nDATA binary\n").encode()
            source.write_bytes(header + points.tobytes())
            catalog = SavedMapCatalog([root], cloud_radius_limit_m=1.)
            metadata = catalog.list_snapshot()["maps"][0]
            raw = catalog.raw_global_reference(metadata["id"], metadata["revision"])
            self.assertEqual(raw["xyz_bytes"], points.tobytes())
            self.assertEqual(raw["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(raw["point_count"], 3)
            self.assertFalse(raw["spatial_filter_applied"])
            with self.assertRaises(SavedMapConflict):
                catalog.raw_global_reference(metadata["id"], "0" * 64)
            with self.assertRaises(SavedMapFormatError):
                catalog.raw_global_reference(metadata["id"], metadata["revision"], max_points=2)
            source.write_bytes(header + points.tobytes() + b"x")
            updated = catalog.list_snapshot()["maps"][0]
            with self.assertRaises(SavedMapFormatError):
                catalog.raw_global_reference(updated["id"], updated["revision"])


class RawContextSnapshotTests(unittest.TestCase):
    def test_latest_callback_identity_is_independent_from_display_throttle_and_reset(self):
        hub = PointCloudHub(threading.RLock(), max_points=1000, radius_limit_m=500, frame_interval_s=1.)
        value = SimpleNamespace(width=1, height=1, point_step=24, row_step=24, is_bigendian=False,
            fields=[SimpleNamespace(name=name, datatype=8, offset=index * 8, count=1)
                    for index, name in enumerate(("x", "y", "z"))],
            data=struct.pack("<ddd", 1, 2, 3), header=SimpleNamespace(frame_id="lidar"))
        stamp = [100]
        def process(now):
            return hub.process("/lidar_points", value, now, selected_topic=lambda: "/lidar_points",
                               stamp_ns=lambda _: stamp[0], robot_pose_in_frame=lambda _: None)
        self.assertTrue(process(10.))
        stamp[0] += 1
        with patch("robot_dashboard.ros.pointcloud.extract_xyz") as viewport:
            self.assertFalse(process(10.01))
        viewport.assert_not_called()
        context = hub.raw_context_snapshot()
        self.assertEqual(context["observation"]["source_stamp_ns"], "101")
        self.assertEqual(hub.binary_snapshot()["stamp_ns"], 100)
        context["observation"]["publisher_epoch"] = "mutated"
        self.assertNotEqual(hub.raw_context_snapshot()["observation"]["publisher_epoch"], "mutated")
        hub.reset("/other")
        self.assertEqual(hub.raw_context_snapshot(), dict(topic="/other", frame_id="", observation={}))


if __name__ == "__main__":
    unittest.main()
