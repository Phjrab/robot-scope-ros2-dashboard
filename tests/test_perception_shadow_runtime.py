import ast
import hashlib
import importlib.util
import json
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "robot_side_perception_shadow.py"
SPEC = importlib.util.spec_from_file_location("robot_side_perception_shadow", SCRIPT)
shadow = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = shadow
SPEC.loader.exec_module(shadow)


def manifest(task="lane", backend="onnx"):
    output_adapter = {
        "lane": "lane_v1",
        "object": "yolo_xyxy_v1",
        "depth_summary": "depth_summary_v1",
    }[task]
    return shadow.ModelManifest(
        model_id=f"{task}-test",
        task=task,
        backend=backend,
        artifact=Path(f"{task}.onnx"),
        artifact_sha256="a" * 64,
        source_model_sha256="b" * 64,
        output_adapter=output_adapter,
        input_width=640,
        input_height=480,
        input_color="RGB",
        classes=("person",) if task == "object" else (),
        target=shadow.RuntimeIdentity("aarch64", "R35.3.1", "8.5.2.2"),
    )


def frame(sequence, *, age_s=0.0, source_sequence=None, source_epoch=1):
    return shadow.Frame(
        sequence=sequence,
        capture_monotonic_ns=time.monotonic_ns() - int(age_s * 1e9),
        received_monotonic_ns=time.monotonic_ns(),
        width=640,
        height=480,
        pixel_format="JPEG",
        jpeg=b"\xff\xd8synthetic\xff\xd9",
        source_sequence=sequence if source_sequence is None else source_sequence,
        source_epoch=source_epoch,
    )


def wait_for(predicate, timeout=1.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class FakeAdapter:
    def __init__(self, task="lane", infer=None):
        self.manifest = manifest(task)
        self._infer = infer or (
            lambda _frame: {
                "lateral_error_normalized": 0.1,
                "heading_error_rad": 0.02,
                "curvature": 0.001,
                "left_lane_visible": True,
                "right_lane_visible": True,
                "confidence": 0.9,
                "reason": "test",
            }
        )

    def infer(self, value):
        return self._infer(value)


class Thermal:
    @staticmethod
    def status():
        return {"state": "LIVE", "max_c": 60.0, "throttling": False}


class PerceptionShadowTests(unittest.TestCase):
    def test_synthetic_frame_hub_is_depth_one_and_rejects_non_monotonic_sequence(self):
        hub = shadow.LatestFrameHub()
        self.assertTrue(hub.publish(frame(1)))
        self.assertTrue(hub.publish(frame(2)))
        self.assertFalse(hub.publish(frame(2)))
        self.assertFalse(hub.publish(frame(3, source_sequence=0)))
        self.assertFalse(hub.publish(frame(3, source_epoch=0)))
        latest = hub.wait_after(0)
        self.assertEqual(latest.sequence, 2)
        self.assertEqual(hub.snapshot()["queue_depth"], 1)
        self.assertEqual(hub.snapshot()["published"], 2)
        self.assertEqual(hub.snapshot()["rejected"], 3)

    def test_manifest_rejects_invalid_metadata_hash_and_target_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "lane.engine"
            artifact.write_bytes(b"target engine")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            payload = {
                "schema": shadow.MODEL_SCHEMA,
                "model_id": "lane-001",
                "task": "lane",
                "backend": "tensorrt",
                "artifact": artifact.name,
                "artifact_sha256": digest,
                "source_model_sha256": "b" * 64,
                "output_adapter": "lane_v1",
                "input": {"width": 640, "height": 480, "color": "RGB"},
                "target": {"machine": "aarch64", "jetpack": "R35.3.1", "tensorrt": "8.5.2.2"},
            }
            path = root / "lane.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = shadow.ModelManifest.load(
                path.name,
                model_root=root,
                runtime=shadow.RuntimeIdentity("aarch64", "R35.3.1", "8.5.2.2"),
            )
            self.assertEqual(loaded.artifact_sha256, digest)

            payload["artifact_sha256"] = "0" * 64
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(shadow.ShadowSetupError, "MODEL_HASH_MISMATCH"):
                shadow.ModelManifest.load(
                    path.name,
                    model_root=root,
                    runtime=shadow.RuntimeIdentity("aarch64", "R35.3.1", "8.5.2.2"),
                )

            payload["artifact_sha256"] = digest
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(shadow.ShadowSetupError, "RUNTIME_MISMATCH"):
                shadow.ModelManifest.load(
                    path.name,
                    model_root=root,
                    runtime=shadow.RuntimeIdentity("aarch64", "R36.0", "9.0"),
                )

    def test_manifest_rejects_path_traversal_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifact.onnx").write_bytes(b"model")
            outside = root.parent / "outside-shadow-manifest.json"
            outside.write_text("{}", encoding="utf-8")
            try:
                with self.assertRaises(shadow.ShadowSetupError):
                    shadow.ModelManifest.load("../outside-shadow-manifest.json", model_root=root)
                (root / "linked.json").symlink_to(outside)
                with self.assertRaises(shadow.ShadowSetupError):
                    shadow.ModelManifest.load("linked.json", model_root=root)
            finally:
                outside.unlink(missing_ok=True)

    def test_queue_supersedes_frames_while_slow_engine_does_not_block_fast_engine(self):
        hub = shadow.LatestFrameHub()
        entered = threading.Event()
        release = threading.Event()

        def slow(_frame):
            entered.set()
            release.wait(1.0)
            return {
                "lateral_error_normalized": 0,
                "heading_error_rad": 0,
                "curvature": 0,
                "left_lane_visible": True,
                "right_lane_visible": True,
                "confidence": 1,
                "reason": "test",
            }

        slow_worker = shadow.InferenceWorker(
            hub, FakeAdapter(infer=slow), max_hz=30, stale_after_s=1
        )
        fast_worker = shadow.InferenceWorker(
            hub, FakeAdapter(), max_hz=30, stale_after_s=1
        )
        runtime = shadow.PerceptionRuntime(
            (slow_worker, fast_worker), hub=hub, thermal_probe=Thermal()
        )
        runtime.start()
        try:
            runtime.submit(frame(1))
            self.assertTrue(entered.wait(0.5))
            runtime.submit(frame(2))
            runtime.submit(frame(3))
            self.assertTrue(
                wait_for(
                    lambda: fast_worker.health()["last_source_sequence"] == 3
                )
            )
            self.assertEqual(hub.snapshot()["queue_depth"], 1)
            release.set()
            self.assertTrue(
                wait_for(lambda: slow_worker.health()["last_source_sequence"] == 3)
            )
            self.assertGreaterEqual(slow_worker.health()["superseded_frames"], 1)
        finally:
            release.set()
            runtime.stop()

    def test_stale_frame_and_engine_exception_clear_result_and_redact_health(self):
        hub = shadow.LatestFrameHub()

        def failed(_frame):
            raise RuntimeError("token=private-value inference failure")

        worker = shadow.InferenceWorker(
            hub, FakeAdapter(infer=failed), max_hz=30, stale_after_s=0.2
        )
        runtime = shadow.PerceptionRuntime(
            (worker,), hub=hub, thermal_probe=Thermal(), source_stale_after_s=1
        )
        runtime.start()
        try:
            runtime.submit(frame(1))
            self.assertTrue(wait_for(lambda: worker.health()["failures"] == 1))
            failed_health = worker.health()
            self.assertEqual(failed_health["state"], "FAILED")
            self.assertIsNone(failed_health["latest_result"])
            self.assertIn("token=<redacted>", failed_health["last_error"])
            self.assertNotIn("private-value", failed_health["last_error"])

            time.sleep(0.04)
            runtime.submit(frame(2, age_s=0.5))
            self.assertTrue(wait_for(lambda: worker.health()["stale_frames"] == 1))
            self.assertIsNone(worker.health()["latest_result"])
        finally:
            runtime.stop()

    def test_result_sequence_increases_and_runtime_never_reuses_stale_result(self):
        hub = shadow.LatestFrameHub()
        worker = shadow.InferenceWorker(
            hub, FakeAdapter(), max_hz=30, stale_after_s=1
        )
        runtime = shadow.PerceptionRuntime(
            (worker,),
            hub=hub,
            thermal_probe=Thermal(),
            source_stale_after_s=0.1,
        )
        runtime.start()
        try:
            runtime.submit(frame(10, source_sequence=812, source_epoch=41))
            self.assertTrue(wait_for(lambda: worker.health()["latest_result"] is not None))
            first = worker.health()["latest_result"]
            self.assertEqual(first["source_sequence"], 812)
            self.assertEqual(first["source_epoch"], 41)
            self.assertEqual(
                first["capture_clock_domain"],
                "robot-monotonic",
            )
            time.sleep(0.04)
            runtime.submit(frame(11, source_sequence=1, source_epoch=42))
            self.assertTrue(
                wait_for(
                    lambda: worker.health()["latest_result"]
                    and worker.health()["latest_result"]["sequence"] == 11
                )
            )
            second = worker.health()["latest_result"]
            self.assertGreater(second["sequence"], first["sequence"])
            self.assertEqual(second["source_sequence"], 1)
            self.assertEqual(second["source_epoch"], 42)
            time.sleep(0.12)
            health = runtime.health()
            self.assertEqual(health["state"], "FAILED")
            self.assertIsNone(health["engines"][0]["latest_result"])
        finally:
            runtime.stop()

    def test_thermal_probe_unavailable_and_raw_cloud_mode_fail_closed(self):
        probe = shadow.ThermalProbe(paths=())
        self.assertEqual(probe.status()["state"], "UNVERIFIED")
        with self.assertRaisesRegex(shadow.ShadowSetupError, "raw/diagnostic"):
            shadow.PerceptionRuntime((), pointcloud_mode="RAW_DIAGNOSTIC")

    def test_engine_rates_are_independently_bounded(self):
        values = {
            "ROBOT_SCOPE_PERCEPTION_LANE_HZ": "12.5",
            "ROBOT_SCOPE_PERCEPTION_OBJECT_HZ": "7",
            "ROBOT_SCOPE_PERCEPTION_DEPTH_HZ": "2",
        }
        self.assertEqual(shadow._config_rate(values, "lane"), 12.5)
        self.assertEqual(shadow._config_rate(values, "object"), 7)
        self.assertEqual(shadow._config_rate(values, "depth_summary"), 2)
        with self.assertRaisesRegex(shadow.ShadowSetupError, "outside"):
            shadow._config_rate({"ROBOT_SCOPE_PERCEPTION_LANE_HZ": "31"}, "lane")

    def test_tensorrt_adapter_uses_fixed_binding_contract_without_backend_fallback(self):
        import numpy

        class Context:
            @staticmethod
            def get_binding_shape(index):
                return (1, 3, 480, 640) if index == 0 else (1, 6)

            @staticmethod
            def set_binding_shape(_index, _shape):
                return True

            @staticmethod
            def execute_v2(_bindings):
                return True

        class Engine:
            num_bindings = 2

            @staticmethod
            def binding_is_input(index):
                return index == 0

            @staticmethod
            def get_binding_shape(index):
                return (1, 3, 480, 640) if index == 0 else (1, 6)

            @staticmethod
            def get_binding_dtype(_index):
                return "float32"

            @staticmethod
            def create_execution_context():
                return Context()

        class TrtRuntime:
            @staticmethod
            def deserialize_cuda_engine(_serialized):
                return Engine()

        class Logger:
            ERROR = 1

            def __init__(self, _level):
                pass

        fake_trt = types.SimpleNamespace(
            Logger=Logger,
            Runtime=lambda _logger: TrtRuntime(),
            nptype=lambda _dtype: numpy.float32,
        )
        fake_cv2 = types.SimpleNamespace(
            COLOR_BGR2RGB=1,
            imdecode=lambda _payload, _mode: numpy.zeros((8, 8, 3), dtype=numpy.uint8),
            resize=lambda _image, size: numpy.zeros((size[1], size[0], 3), dtype=numpy.uint8),
            cvtColor=lambda image, _code: image,
        )

        class Cuda:
            def __init__(self):
                self.next_pointer = 1

            def allocate(self, _size):
                pointer = shadow.ctypes.c_void_p(self.next_pointer)
                self.next_pointer += 1
                return pointer

            @staticmethod
            def free(_pointer):
                return None

            @staticmethod
            def host_to_device(_pointer, _array):
                return None

            @staticmethod
            def device_to_host(array, _pointer):
                array[:] = numpy.asarray([[0.1, 0.02, 0.001, 1.0, 1.0, 0.9]])

            @staticmethod
            def synchronize():
                return None

        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "lane.engine"
            artifact.write_bytes(b"engine")
            contract = manifest(backend="tensorrt")
            contract = shadow.ModelManifest(
                **{**contract.__dict__, "artifact": artifact}
            )
            with (
                mock.patch.dict(sys.modules, {"cv2": fake_cv2, "tensorrt": fake_trt}),
                mock.patch.object(shadow, "_CudaRuntime", Cuda),
            ):
                adapter = shadow.TensorRtAdapter(contract)
                result = adapter.infer(frame(1))
                adapter.close()
        self.assertAlmostEqual(result["lateral_error_normalized"], 0.1)
        self.assertAlmostEqual(result["confidence"], 0.9)

    def test_source_disconnect_supervision_is_bounded_and_stoppable(self):
        source = shadow.MjpegFrameSource("192.168.50.30", 8090, 640, 480)
        stop = threading.Event()

        def disconnected(_runtime, _stop):
            stop.set()
            raise OSError("preview consumer disconnected")

        source.run_once = disconnected
        source.supervise(mock.Mock(), stop)
        self.assertEqual(source.reconnects, 1)
        self.assertIn("disconnected", source.last_error)

    def test_runtime_and_service_have_no_motion_ros_or_camera_device_authority(self):
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("rclpy", imports)
        self.assertFalse(any(name.startswith("robot_dashboard") for name in imports))
        self.assertNotIn("/dev/video", source)
        service = (
            ROOT / "deploy" / "robot-scope-perception-shadow.service.example"
        ).read_text(encoding="utf-8")
        self.assertIn("DevicePolicy=closed", service)
        self.assertIn("DeviceAllow=/dev/nvhost-gpu rw", service)
        self.assertNotIn("DeviceAllow=/dev/video", service)
        self.assertIn("CapabilityBoundingSet=\n", service)
        self.assertNotIn("Requires=robot-scope-realsense-camera.service", service)


if __name__ == "__main__":
    unittest.main()
