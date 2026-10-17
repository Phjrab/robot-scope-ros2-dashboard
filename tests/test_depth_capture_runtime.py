"""Hardware-free SDK boundary, ownership and raw-capture regressions."""
from contextlib import ExitStack
import json
from pathlib import Path
import queue
import tempfile
import threading
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from robot_dashboard.depth_capture_runtime import (
    CAPTURE_WAIT_S, MAX_PAIR_SKEW_MS, RealSenseDepthCaptureAdapter,
)
from robot_dashboard.depth_capture_store import DepthCaptureStore
from robot_dashboard.slam_sessions import SlamError


SESSION = {"session_id": "depth-session", "generation": 1, "engine_id": "realsense_depth", "task": "calibration"}
CONFIRMATION = {"robot_seated": True, "robot_stationary": True, "camera_stationary": True}


class Profile:
    def __init__(self, stream, index, fmt, width=4, height=3, fps=30):
        self.stream, self.index, self.fmt = stream, index, fmt
        self.w, self.h, self.rate = width, height, fps
        self.intrinsics = NS(width=width, height=height, fx=100., fy=101., ppx=2., ppy=1., model="distortion.none", coeffs=[0.] * 5)

    def stream_type(self): return self.stream
    def stream_index(self): return self.index
    def format(self): return self.fmt
    def fps(self): return self.rate
    def is_video_stream_profile(self): return True
    def as_video_stream_profile(self): return self
    def width(self): return self.w
    def height(self): return self.h
    def get_intrinsics(self): return self.intrinsics
    def get_extrinsics_to(self, other):
        return NS(rotation=[1., 0., 0., 0., 1., 0., 0., 0., 1.], translation=[0., 0., 0.])


class Frame:
    def __init__(self, profile, number, timestamp, domain="timestamp_domain.hardware_clock", padding=0):
        self.profile, self.number, self.timestamp, self.domain = profile, number, timestamp, domain
        self.bits = 8 if profile.stream == "stream.infrared" else 16
        self.stride = profile.w * self.bits // 8 + padding
        self.data = bytes([number % 255]) * (self.stride * profile.h)

    def get_profile(self): return self.profile
    def get_width(self): return self.profile.w
    def get_height(self): return self.profile.h
    def get_stride_in_bytes(self): return self.stride
    def get_bits_per_pixel(self): return self.bits
    def get_data(self): return self.data
    def get_frame_number(self): return self.number
    def get_timestamp(self): return self.timestamp
    def get_frame_timestamp_domain(self): return self.domain
    def supports_frame_metadata(self, key): return key == "frame_counter"
    def get_frame_metadata(self, key): return self.number


class Device:
    def __init__(self, sdk): self.sdk = sdk
    def supports(self, key): return key in {"serial_number", "name", "firmware_version"}
    def get_info(self, key): return {"serial_number": self.sdk.serial, "name": "fixture D435i", "firmware_version": "fixture"}[key]
    def query_sensors(self): return [self]
    def get_stream_profiles(self):
        self.sdk.events.append("supported_profiles")
        return self.sdk.profiles
    def get_supported_options(self): return ["option.emitter_enabled"]
    def get_option(self, key): return 1.0
    def first_depth_sensor(self): return self
    def get_depth_scale(self): return self.sdk.depth_scale


class Pipeline:
    def __init__(self, sdk):
        self.sdk, self.started, self.stopped, self.counter = sdk, False, False, 0
        self.stop_fail = False
        self.automatic = True
        self.queue = queue.Queue()

    def start(self, config):
        self.sdk.events.append("pipeline_start")
        self.started = True
        if self.sdk.start_fail:
            raise RuntimeError("fixture start failed after device acquisition")
        return NS(get_device=lambda: self.sdk.device, get_streams=lambda: self.sdk.effective_profiles)

    def wait_for_frames(self, timeout_ms):
        if self.automatic:
            time.sleep(0.01)
            self.counter += 1
            return self.sdk.frames(self.counter)
        try:
            return self.queue.get(timeout=0.02)
        except queue.Empty:
            raise RuntimeError("fixture wait timeout") from None

    def stop(self):
        self.sdk.events.append("pipeline_stop")
        if self.stop_fail:
            raise RuntimeError("fixture stop not confirmed")
        self.stopped = True


class SDK:
    stream = NS(infrared="stream.infrared", depth="stream.depth")
    format = NS(y8="format.y8", z16="format.z16")
    camera_info = NS(serial_number="serial_number", name="name", firmware_version="firmware_version")
    frame_metadata_value = NS(__members__={"frame_counter": "frame_counter", "gain": "gain"})

    def __init__(self):
        self.events = []
        self.serial, self.depth_scale, self.start_fail, self.skew, self.domain = "12345", 0.001, False, 0., "timestamp_domain.hardware_clock"
        self.ir = Profile(self.stream.infrared, 1, self.format.y8)
        self.depth = Profile(self.stream.depth, 0, self.format.z16)
        self.profiles, self.effective_profiles = [self.ir, self.depth], [self.ir, self.depth]
        self.device = Device(self)
        self.devices = [self.device]
        self.pipe = Pipeline(self)
        self.configuration = NS(enable_device=Mock(), enable_stream=Mock())

    def context(self):
        self.events.append("sdk_context")
        return NS(query_devices=lambda: self.devices)
    def pipeline(self, context): return self.pipe
    def config(self): return self.configuration
    def frames(self, number):
        ir = Frame(self.ir, number, number * 1000 / 30, padding=1)
        depth = Frame(self.depth, number, number * 1000 / 30 + self.skew, self.domain, padding=2)
        return NS(get_infrared_frame=lambda index: ir, get_depth_frame=lambda: depth)


class DepthRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.path = Path(self.directory).resolve() / "depth.json"
        self.config = {"schema_version": 1, "serial": "12345", "width": 4, "height": 3, "fps": 30,
                       "managed_scope": str(self.path.parent / "scope.json"), "max_session_s": 120}
        self.write_config()
        self.sdk = SDK()
        self.scope = {"scope_id": "fixture-scope", "scope_sha256": "f" * 64, "domain_id": 71}
        self.stack.enter_context(patch("robot_dashboard.depth_capture_runtime.load_managed_scope", return_value=self.scope))
        self.domain = Mock()
        self.domain.evidence.return_value = {"fixture": True}
        self.stack.enter_context(patch("robot_dashboard.depth_capture_runtime.DomainReservation", return_value=self.domain))
        self.proof = self.stack.enter_context(patch("robot_dashboard.depth_capture_runtime.validate_reservation_proof"))
        self.adapter = RealSenseDepthCaptureAdapter(config_path=self.path, enabled=True,
            sdk_loader=lambda: self.sdk)
        self.camera = Mock()
        self.camera.reservation_proof.side_effect = self.reservation_proof
        self.adapter.bind_camera_coordinator(self.camera)

    def reservation_proof(self, session):
        self.sdk.events.append("reservation_proof")
        return dict(self.scope)

    def write_config(self):
        self.path.write_text(json.dumps(self.config))
        self.path.chmod(0o600)

    def tearDown(self):
        self.sdk.pipe.stop_fail = False
        try:
            self.adapter.stop(SESSION)
        finally:
            self.stack.close()

    def start(self):
        return self.adapter.start(SESSION, threading.Event())

    def await_condition(self, condition, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.005)
        self.fail("condition was not observed")

    def test_capability_checks_binding_but_never_enumerates_devices(self):
        loader = Mock(return_value=self.sdk)
        self.adapter._sdk_loader = loader
        self.assertTrue(self.adapter.capability()["available_now"])
        self.adapter.preflight()
        loader.assert_called_once()
        self.assertEqual(self.sdk.events, [])

    def test_sdk_namespace_without_pipeline_is_not_reported_installed(self):
        self.adapter._sdk_loader = lambda: NS()
        capability = self.adapter.capability()
        self.assertFalse(capability["installed"])
        self.assertFalse(capability["available_now"])
        self.assertEqual(capability["blocked_reason"], "REALSENSE_SDK_UNAVAILABLE")
        with self.assertRaisesRegex(SlamError, "REALSENSE_SDK_UNAVAILABLE"):
            self.start()
        self.assertNotIn("sdk_context", self.sdk.events)

    def test_sdk_native_binding_import_failure_is_reported_without_camera_access(self):
        self.adapter._sdk_loader = Mock(side_effect=OSError("missing shared library"))
        self.assertFalse(self.adapter.capability()["installed"])
        self.assertEqual(self.sdk.events, [])

    def test_default_is_disabled_and_environment_is_separate(self):
        with patch.dict("os.environ", {"ROBOT_SCOPE_DEPTH_CAPTURE_CONFIG": "/private/depth.json", "ROBOT_SCOPE_DEPTH_CAPTURE_ENABLE": "1"}):
            value = RealSenseDepthCaptureAdapter.from_environment()
        self.assertEqual(value.config_path, Path("/private/depth.json"))
        self.assertTrue(value.enabled)
        with self.assertRaisesRegex(SlamError, "DEPTH_CAPTURE_DISABLED"):
            RealSenseDepthCaptureAdapter().preflight()

    def test_private_exact_config_and_lifespan_bounds(self):
        for change in ({"serial": ""}, {"width": True}, {"fps": 0}, {"height": 2000},
                       {"max_session_s": 301}, {"max_session_s": True}, {"extra": True}):
            original = dict(self.config)
            self.config.update(change)
            self.write_config()
            with self.subTest(change=change), self.assertRaisesRegex(SlamError, "CONFIG_INVALID"):
                self.adapter.preflight()
            self.config = original
        self.write_config()
        self.path.chmod(0o644)
        with self.assertRaisesRegex(SlamError, "CONFIG_INVALID"):
            self.adapter.preflight()
        self.path.chmod(0o600)
        self.adapter.preflight()
        self.assertEqual(self.sdk.events, [])

    def test_reserved_supported_exact_profiles_precede_start_and_no_options_written(self):
        result = self.start()
        self.assertEqual(result["effective_mode"], "depth_calibration")
        self.assertFalse(result["ready"])
        self.assertEqual(self.sdk.events[:4], ["reservation_proof", "sdk_context", "supported_profiles", "pipeline_start"])
        self.domain.acquire.assert_called_once()
        self.proof.assert_called_once()
        self.sdk.configuration.enable_device.assert_called_once_with("12345")
        self.assertEqual(self.sdk.configuration.enable_stream.call_count, 2)
        self.await_condition(lambda: self.adapter.status(SESSION)["ready"])
        self.assertEqual(self.adapter.status(SESSION)["depth_scale_m"], 0.001)

    def test_missing_camera_proof_rejects_before_sdk_query(self):
        self.adapter.bind_camera_coordinator(None)
        with self.assertRaisesRegex(Exception, "RESOURCE_CONFLICT"):
            self.start()
        self.assertEqual(self.sdk.events, [])
        self.domain.acquire.assert_not_called()

    def test_wrong_scope_proof_rejects_before_sdk_query(self):
        self.camera.reservation_proof.side_effect = lambda _: {"scope_id": "other", "scope_sha256": "x"}
        with self.assertRaisesRegex(Exception, "RESOURCE_CONFLICT"):
            self.start()
        self.assertEqual(self.sdk.events, [])

    def test_missing_selected_serial_never_falls_back_to_other_device(self):
        self.sdk.serial = "other"
        with self.assertRaisesRegex(SlamError, "DEVICE_MISSING"):
            self.start()
        self.assertNotIn("pipeline_start", self.sdk.events)
        self.domain.release.assert_called_once()

    def test_unsupported_requested_profile_never_starts(self):
        self.sdk.profiles = [self.sdk.ir]
        with self.assertRaisesRegex(SlamError, "PROFILE_UNSUPPORTED"):
            self.start()
        self.assertNotIn("pipeline_start", self.sdk.events)

    def test_effective_profile_mismatch_stops_acquired_pipeline(self):
        self.sdk.effective_profiles = [self.sdk.ir, Profile("stream.depth", 0, "format.z16", fps=15)]
        with self.assertRaisesRegex(SlamError, "EFFECTIVE_PROFILE_MISMATCH"):
            self.start()
        self.assertTrue(self.sdk.pipe.stopped)
        self.camera.release.assert_not_called()

    def test_partial_start_failure_requires_confirmed_cleanup(self):
        self.sdk.start_fail = True
        self.sdk.pipe.stop_fail = True
        with self.assertRaisesRegex(SlamError, "CLEANUP_REQUIRED"):
            self.start()
        self.assertTrue(self.adapter.status(SESSION)["cleanup_required"])
        self.domain.release.assert_not_called()
        with self.assertRaisesRegex(SlamError, "CLEANUP_REQUIRED"):
            self.adapter.stop(SESSION)
        self.camera.release.assert_not_called()
        self.sdk.pipe.stop_fail = False
        self.adapter.stop(SESSION)
        self.assertTrue(self.sdk.pipe.stopped)

    def test_raw_capture_has_new_frames_after_confirmation_and_preserves_metadata(self):
        self.start()
        self.await_condition(lambda: self.adapter.status(SESSION)["ready"])
        before = self.sdk.pipe.counter
        result = self.adapter.capture(SESSION, CONFIRMATION)
        ir, depth = result["frames"]["ir1"], result["frames"]["depth"]
        self.assertGreater(ir["frame_number"], before)
        self.assertTrue(result["post_confirmation_sdk_wait"])
        self.assertFalse(result["sensor_exposure_after_confirmation_independently_verified"])
        self.assertEqual(ir["metadata"]["frame_counter"], ir["frame_number"])
        self.assertEqual(result["frameset"]["ir_frame_number"], ir["frame_number"])
        self.assertEqual(result["frameset"]["depth_frame_number"], depth["frame_number"])
        self.assertEqual(ir["stride_bytes"], 5)
        self.assertEqual(len(depth["data"]), 30)
        self.assertEqual(ir["frame_id_source"], "sdk_logical_optical_not_ros_tf")
        self.assertEqual(depth["byte_order"], __import__("sys").byteorder)
        self.assertEqual(result["sensor_options_after_start"][0]["options"]["option.emitter_enabled"]["value"], 1.)
        self.assertEqual(result["processing"]["alignment"], "none")
        self.assertFalse(result["processing"]["body_level_assumed"])
        result["confirmation"]["robot_seated"] = False
        self.assertTrue(CONFIRMATION["robot_seated"])

    def test_confirmation_requires_three_exact_true_and_does_not_infer_body_attitude(self):
        for key in CONFIRMATION:
            for invalid in (None, False, 1, "true"):
                with self.subTest(key=key, invalid=invalid), self.assertRaisesRegex(SlamError, "CONFIRMATION_REQUIRED"):
                    self.adapter.capture(SESSION, dict(CONFIRMATION, **{key: invalid}))

    def test_runtime_bundle_round_trips_store_with_correct_flat_depth_and_pinhole(self):
        self.start()
        captured = self.adapter.capture(SESSION, CONFIRMATION)
        store = DepthCaptureStore(self.path.parent / "private-samples", minimum_free_bytes=0)
        receipt = store.save_sample(captured)
        self.assertEqual(receipt["compatibility"], {"available": True, "reason": None})
        compatible = store.compatibility_json(receipt["sample_id"])
        frame = captured["frames"]["depth"]
        pixel_mm = int.from_bytes(frame["data"][:2], frame["byte_order"])
        self.assertEqual(compatible["depth_m"], [pixel_mm * .001] * 12)
        self.assertEqual(compatible["intrinsics"], {"fx": 100., "fy": 101., "cx": 2., "cy": 1.})
        self.assertEqual(compatible["metadata"]["serial"], "12345")
        self.assertEqual(compatible["metadata"]["depth_semantics"], "optical_z")
        self.assertNotIn("body_pitch", compatible)

    def test_missing_frames_stop_pipeline_and_expose_fixed_timeout_reason(self):
        self.sdk.pipe.automatic = False
        with patch("robot_dashboard.depth_capture_runtime.NO_FRAME_TIMEOUT_S", 0.03):
            self.start()
            self.await_condition(lambda: self.adapter.status(SESSION)["cleanup_complete"])
        self.assertEqual(self.adapter.status(SESSION)["reason"], "DEPTH_CAPTURE_FRAME_TIMEOUT")
        self.assertTrue(self.sdk.pipe.stopped)
        self.camera.release.assert_not_called()

    def test_partial_start_error_is_typed_without_forwarding_sdk_exception_text(self):
        self.sdk.start_fail = True
        with self.assertRaisesRegex(SlamError, "^DEPTH_CAPTURE_START_FAILED$"):
            self.start()
        self.assertTrue(self.sdk.pipe.stopped)

    def test_capture_rejects_wrong_generation_and_task(self):
        self.start()
        with self.assertRaisesRegex(SlamError, "SESSION_GENERATION_CONFLICT"):
            self.adapter.capture(dict(SESSION, generation=2), CONFIRMATION)
        with self.assertRaisesRegex(SlamError, "SESSION_INVALID"):
            self.adapter.capture(dict(SESSION, task="mapping"), CONFIRMATION)

    def test_timestamp_mismatch_fails_explicitly_and_stops(self):
        self.assertEqual(MAX_PAIR_SKEW_MS, 1.0)
        self.sdk.skew = 1.01
        self.start()
        self.await_condition(lambda: self.adapter.status(SESSION)["cleanup_complete"])
        self.assertEqual(self.adapter.status(SESSION)["reason"], "DEPTH_CAPTURE_TIMESTAMP_MISMATCH")
        with self.assertRaisesRegex(SlamError, "TIMESTAMP_MISMATCH"):
            self.adapter.capture(SESSION, CONFIRMATION)

    def test_timestamp_domains_must_match_even_with_equal_numbers(self):
        self.sdk.domain = "timestamp_domain.system_time"
        self.start()
        self.await_condition(lambda: self.adapter.status(SESSION)["cleanup_complete"])
        self.assertEqual(self.adapter.status(SESSION)["reason"], "DEPTH_CAPTURE_TIMESTAMP_DOMAIN_MISMATCH")

    def test_capture_does_not_reuse_preconfirmation_latest_after_stream_stalls(self):
        self.start()
        self.await_condition(lambda: self.adapter.status(SESSION)["ready"])
        self.sdk.pipe.automatic = False
        time.sleep(0.04)
        with patch("robot_dashboard.depth_capture_runtime.CAPTURE_WAIT_S", 0.05):
            with self.assertRaisesRegex(SlamError, "POST_CONFIRMATION_FRAME_TIMEOUT"):
                self.adapter.capture(SESSION, CONFIRMATION)
        self.assertEqual(CAPTURE_WAIT_S, 3.)

    def test_expiry_stops_pipeline_but_reservation_needs_parent_settlement(self):
        self.config["max_session_s"] = 1
        self.write_config()
        self.start()
        self.await_condition(lambda: self.adapter.status(SESSION)["cleanup_complete"])
        value = self.adapter.status(SESSION)
        self.assertFalse(value["alive"])
        self.assertFalse(value["ready"])
        self.assertEqual(value["reason"], "DEPTH_CAPTURE_SESSION_EXPIRED")
        self.assertTrue(self.sdk.pipe.stopped)
        self.camera.release.assert_not_called()
        with self.assertRaisesRegex(SlamError, "RESOURCE_CONFLICT"):
            self.adapter.preflight()
        self.adapter.stop(SESSION)
        self.adapter.preflight()

    def test_stop_failure_keeps_owned_state_and_domain_reservation(self):
        self.start()
        self.sdk.pipe.stop_fail = True
        with self.assertRaisesRegex(SlamError, "CLEANUP_REQUIRED"):
            self.adapter.stop(SESSION)
        self.assertTrue(self.adapter.status(SESSION)["cleanup_required"])
        self.domain.release.assert_not_called()
        self.camera.release.assert_not_called()
        self.sdk.pipe.stop_fail = False
        self.adapter.stop(SESSION)
        self.assertTrue(self.sdk.pipe.stopped)

    def test_cancelled_start_does_not_query_or_start_sdk(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaisesRegex(SlamError, "START_CANCELLED"):
            self.adapter.start(SESSION, cancel)
        self.assertNotIn("sdk_context", self.sdk.events)
        self.camera.release.assert_not_called()

    def test_stop_is_idempotent_but_cannot_stop_foreign_generation(self):
        self.start()
        with self.assertRaisesRegex(SlamError, "SESSION_GENERATION_CONFLICT"):
            self.adapter.stop(dict(SESSION, generation=2))
        self.assertFalse(self.sdk.pipe.stopped)
        self.adapter.stop(SESSION)
        self.adapter.stop(SESSION)
        self.camera.release.assert_not_called()


if __name__ == "__main__":
    unittest.main()
