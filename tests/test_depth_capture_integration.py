"""Synthetic shared ownership/API/IPC regressions; no camera or calibration."""
import asyncio
import hashlib
from copy import deepcopy
import io
import tempfile
from pathlib import Path
import unittest
import zipfile
from unittest.mock import Mock

from fastapi import FastAPI

from robot_dashboard.api.routers.depth_capture import router
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.depth_capture_contract import validate_confirmation
from robot_dashboard.depth_capture_store import DepthCaptureStore
from robot_dashboard.slam_broker import BrokerDepthAdapter
from robot_dashboard.slam_packages import MapPackageStore
from robot_dashboard.slam_sessions import SlamError, SlamSessionManager
import test_slam_api as api_fixture
from test_slam_api import SyntheticApiManager, SyntheticCompetition
import test_slam_broker as broker_fixture
from test_slam_broker import SyntheticBrokerEngine, SESSION
from test_slam_sessions import SyntheticCamera, SyntheticEngine
from test_depth_capture_store import capture_fixture

CONFIRM = dict(robot_seated=True, robot_stationary=True, camera_stationary=True)
DEPTH_SESSION = dict(SESSION, engine_id="realsense_depth", task="calibration")


class DepthOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.camera = SyntheticCamera()
        self.stereo, self.depth = SyntheticEngine(), SyntheticEngine()
        self.depth.capability = lambda: {"available_now": True, "tasks": ["calibration"]}
        self.depth.capture = Mock(return_value={"sample_id": "c"*32})
        self.manager = SlamSessionManager({"visual_stereo": self.stereo, "realsense_depth": self.depth},
            MapPackageStore(Path(self.temp.name)), coordination_lock=asyncio.Lock(),
            blockers=lambda: [], navigation_context=lambda: {}, camera=self.camera)

    async def asyncTearDown(self):
        self.depth.stop_error = None
        await self.manager.close()
        self.temp.cleanup()

    async def start_depth(self):
        value = await self.manager.start(engine_id="realsense_depth", task="calibration",
            request_id="depth-start-1", operator_confirmed=True)
        await self.manager._operation
        return value

    async def test_shared_session_camera_exclusion_and_explicit_return_to_stereo(self):
        identity = await self.start_depth()
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "CAPTURING")
        self.assertTrue(self.manager.blocks_context_change())
        self.assertIsNotNone(self.camera.owner)
        with self.assertRaises(SlamError):
            await self.manager.start(engine_id="visual_stereo", task="mapping", request_id="stereo-denied", operator_confirmed=True)
        self.assertEqual(self.stereo.calls, [])
        self.assertEqual(self.manager.frame()["reason"], "DEPTH_CAPTURE_SEPARATE_MODE")
        await self.manager.stop(**identity, request_id="stop-depth-1")
        await self.manager._operation
        self.assertIsNone(self.camera.owner)
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "IDLE")
        await self.manager.start(engine_id="visual_stereo", task="tracking", request_id="stereo-after", operator_confirmed=True)
        await self.manager._operation
        self.assertEqual(self.manager.snapshot()["active_session"]["state"], "TRACKING")

    async def test_capture_idempotency_attestation_context_and_no_map_save(self):
        identity = await self.start_depth()
        receipt = await self.manager.capture_depth(**identity, request_id="capture-one", confirmation=CONFIRM)
        self.assertEqual(receipt, await self.manager.capture_depth(**identity, request_id="capture-one", confirmation=CONFIRM))
        self.depth.capture.assert_called_once()
        for values in (dict(CONFIRM, camera_stationary=False), dict(CONFIRM, robot_seated=1)):
            with self.assertRaises(SlamError):
                await self.manager.capture_depth(**identity, request_id="capture-bad", confirmation=values)
        with self.assertRaises(SlamError):
            await self.manager.capture_depth(**dict(identity, generation=999), request_id="capture-bad", confirmation=CONFIRM)
        with self.assertRaises(SlamError):
            await self.manager.save(**identity, request_id="no-map-save", name="not-a-map")

    async def test_stop_failure_retains_owner_and_blocks_restart(self):
        identity = await self.start_depth()
        self.depth.stop_error = RuntimeError("fixture stop failed")
        await self.manager.stop(**identity, request_id="failed-stop")
        await self.manager._operation
        self.assertIsNotNone(self.camera.owner)
        self.assertTrue(self.manager.snapshot()["active_session"]["cleanup_required"])
        self.assertTrue(self.manager.blocks_context_change())

    def test_body_attitude_is_optional_but_never_default_level(self):
        validate_confirmation(CONFIRM)
        value = dict(CONFIRM, body_attitude={"quaternion_xyzw": [0,0,0,1], "frame_id": "body",
            "source": "operator-measurement", "source_timestamp_ns": "1234", "clock_domain": "utc"})
        validate_confirmation(value)
        value["body_attitude"].pop("source")
        with self.assertRaises(SlamError):
            validate_confirmation(value)


class DepthBrokerTests(unittest.TestCase):
    # Reuse the real-socket fixture, not its stereo test cases.
    def setUp(self):
        broker_fixture.SlamBrokerTests.setUp(self)
        self.depth = SyntheticBrokerEngine()
        self.depth.capture = Mock(return_value={"synthetic_fixture": True})
        self.dispatcher.depth_adapter = self.depth
        self.dispatcher.depth_store = Mock()
        self.dispatcher.depth_store.save_sample.return_value = {"sample_id": "c"*32}
        self.depth_proxy = BrokerDepthAdapter(self.socket_path)

    def tearDown(self):
        broker_fixture.SlamBrokerTests.tearDown(self)

    def test_depth_and_stereo_share_broker_reservation_and_capture_retry(self):
        self.depth_proxy.camera_coordinator.acquire(DEPTH_SESSION)
        with self.assertRaises(SlamError):
            broker_fixture.SlamBrokerTests.reserve(self)
        self.depth_proxy.start(DEPTH_SESSION, self.dispatcher._cancel)
        first = self.depth_proxy.capture(DEPTH_SESSION, CONFIRM, request_id="capture-111")
        second = self.depth_proxy.capture(DEPTH_SESSION, deepcopy(CONFIRM), request_id="capture-111")
        self.assertEqual(first, second)
        self.depth.capture.assert_called_once()
        self.dispatcher.depth_store.save_sample.assert_called_once()
        self.assertEqual(first["engine_id"], "realsense_depth")
        self.assertEqual(self.engine.calls, [])
        self.depth_proxy.camera_coordinator.release(DEPTH_SESSION)
        self.assertFalse(self.camera.snapshot()["reserved"])


class DepthApiTests(unittest.IsolatedAsyncioTestCase):
    request = api_fixture.SlamApiTests.request

    async def asyncSetUp(self):
        self.manager = SyntheticApiManager(None)
        self.manager.depth_samples = Mock()
        async def capture_depth(*args, **kwargs):
            return await self.manager._call("capture_depth", *args, **kwargs)
        self.manager.capture_depth = capture_depth
        self.runtime = ApplicationRuntime(competition=SyntheticCompetition(), slam=self.manager)
        self.app = FastAPI()
        self.app.state.runtime = self.runtime
        self.app.include_router(router)

    async def test_start_requires_seated_and_separately_stopped_camera(self):
        good = dict(CONFIRM, request_id="api-start-1")
        result = await self.request("POST", "/api/v1/slam/depth/sessions", body=good)
        self.assertEqual(result.status, 202)
        self.assertEqual(self.manager.calls[0][2]["engine_id"], "realsense_depth")
        for bad in (dict(good,camera_stationary=False), dict(good,robot_seated=1)):
            self.assertEqual((await self.request("POST", "/api/v1/slam/depth/sessions", body=bad)).status, 422)
        self.assertEqual(len(self.manager.calls), 1)

    async def test_same_origin_manual_guard_and_capture_confirmation(self):
        path = "/api/v1/slam/sessions/fixture/depth-samples"
        body = dict(CONFIRM,generation=1,request_id="api-capture-1")
        self.assertEqual((await self.request("POST",path,body=body,headers={"origin":"http://foreign"})).status,403)
        self.assertEqual(self.manager.calls, [])
        result = await self.request("POST",path,body=body)
        self.assertEqual(result.status,201)
        self.assertEqual(self.manager.calls[0][2]["confirmation"]["body_attitude"], None)

    async def test_exports_serve_exact_saved_pixels_depth_and_raw_only_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DepthCaptureStore(Path(directory).resolve() / "samples", minimum_free_bytes=0)
            self.manager.depth_samples = store
            value = capture_fixture()
            receipt = store.save_sample(value)
            base = "/api/v1/slam/depth/samples/" + receipt["sample_id"]
            listing = await self.request("GET", "/api/v1/slam/depth/samples")
            self.assertEqual(listing.json()["samples"][0]["sample_id"], receipt["sample_id"])
            self.assertEqual(listing.headers[b"cache-control"], b"no-store")
            image = await self.request("GET", base+"/image")
            self.assertEqual(image.content, store.click_png(receipt["sample_id"]))
            compatibility = await self.request("GET", base+"/compatibility")
            self.assertEqual(compatibility.json()["depth_m"], [None, 1.0, 2.0, 65.535])
            for response, name in ((image, "click.png"), (compatibility, "compatibility.json")):
                expected = receipt["files"][name]
                self.assertEqual(response.content, (store.root / receipt["sample_id"] / name).read_bytes())
                self.assertEqual(hashlib.sha256(response.content).hexdigest(), expected["sha256"])
                self.assertEqual(response.headers[b"x-robot-scope-artifact-sha256"].decode(), expected["sha256"])
                self.assertEqual(int(response.headers[b"x-robot-scope-artifact-bytes"]), len(response.content))
            archive = await self.request("GET", base+"/export")
            with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
                self.assertEqual(zipped.read("depth.z16"), value["frames"]["depth"]["data"])
                self.assertEqual(zipped.read("compatibility.json"), compatibility.content)
            # A changed on-disk artifact is refused, not labelled with the old receipt.
            (store.root / receipt["sample_id"] / "click.png").write_bytes(image.content + b"bad")
            failed_image = await self.request("GET", base+"/image")
            self.assertEqual(failed_image.status, 409)
            self.assertNotIn(b"x-robot-scope-artifact-sha256", failed_image.headers)
            self.assertEqual(self.manager.calls, [])
            value["frames"]["depth"] = {}
            receipt = store.save_sample(value)
            failed = await self.request("GET", "/api/v1/slam/depth/samples/"+receipt["sample_id"]+"/compatibility")
            self.assertEqual(failed.status,409)
            self.assertNotIn(directory.encode(), failed.content)
