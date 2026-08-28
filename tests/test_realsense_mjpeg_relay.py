import importlib.util
import stat
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "realsense_mjpeg_relay.py"
SPEC = importlib.util.spec_from_file_location("realsense_mjpeg_relay", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
relay = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = relay
SPEC.loader.exec_module(relay)


class FakeProducer:
    def __init__(self, publish):
        self.publish = publish
        self.started = False
        self.stopped = False
        self.process_running = False
        self.process_started_at = 0.0
        self.last_error = ""

    def start(self):
        self.started = True
        self.process_running = True
        self.process_started_at = time.monotonic()

    def stop(self):
        self.stopped = True
        self.process_running = False

    def status(self):
        return {
            "process_running": self.process_running,
            "process_started_at": self.process_started_at,
            "thread_running": self.started and not self.stopped,
            "last_error": self.last_error,
        }


class RealSenseRelayTests(unittest.TestCase):
    def test_fixed_network_and_capture_contract(self):
        self.assertEqual((relay.BIND_HOST, relay.BIND_PORT), ("192.168.123.18", 8090))
        self.assertEqual(relay.DASHBOARD_HOST, "192.168.123.99")
        self.assertEqual((relay.WIDTH, relay.HEIGHT, relay.FPS), (640, 480, 15))
        self.assertEqual(relay.JPEG_QUALITY, 72)
        self.assertEqual(relay.PLUGIN_PROBE_TIMEOUT_S, 15.0)
        self.assertEqual(relay.MAX_VIEWERS, 4)
        self.assertEqual(relay.MAX_HTTP_CLIENTS, 8)
        self.assertEqual(relay.MAX_JPEG_BYTES, 4 * 1024 * 1024)
        self.assertEqual(
            relay.DEVICE_GLOB,
            "/dev/v4l/by-path/*-video-index0",
        )
        self.assertEqual(relay.REALSENSE_VENDOR_ID, "8086")
        self.assertEqual(relay.REALSENSE_PRODUCT_ID, "0b3a")
        self.assertEqual(relay.REALSENSE_COLOR_INTERFACE, "03")
        self.assertEqual(relay.REALSENSE_VIDEO_INDEX, "0")

    @mock.patch.object(relay, "_plugin_available")
    def test_pipeline_is_fixed_argv_and_prefers_software_jpeg(self, available):
        available.side_effect = lambda name: name == "jpegenc"
        command = relay.gstreamer_command("/dev/video6")
        self.assertIsInstance(command, tuple)
        self.assertEqual(command[0], "/usr/bin/gst-launch-1.0")
        self.assertIn("device=/dev/video6", command)
        self.assertIn("video/x-raw,format=YUY2,width=640,height=480,framerate=15/1", command)
        self.assertIn("video/x-raw,format=I420", command)
        self.assertIn("jpegenc", command)
        self.assertIn("quality=72", command)
        self.assertNotIn("sh", command)
        self.assertNotIn("-c", command)

    @mock.patch.object(relay.subprocess, "run")
    def test_plugin_probe_allows_a_cold_private_registry_scan(self, run):
        run.return_value.returncode = 0
        self.assertTrue(relay._plugin_available("nvjpegenc"))
        self.assertEqual(
            run.call_args.kwargs["timeout"], relay.PLUGIN_PROBE_TIMEOUT_S
        )

    @mock.patch.object(relay, "_plugin_available")
    def test_pipeline_falls_back_to_nvjpeg_when_software_encoder_is_absent(self, available):
        available.side_effect = lambda name: name == "nvjpegenc"
        self.assertIn("nvjpegenc", relay.gstreamer_command("/dev/video6"))

    def test_device_resolution_requires_exactly_one_verified_color_device(self):
        with mock.patch.object(relay.glob, "glob", return_value=[]):
            with self.assertRaises(relay.RelaySetupError):
                relay.resolve_realsense_device()
        link = mock.Mock()
        link.is_symlink.return_value = True
        link.parent = relay.DEVICE_LINK_DIR
        target = mock.Mock()
        target.parent = Path("/dev")
        target.name = "video6"
        target.stat.return_value.st_mode = stat.S_IFCHR
        link.resolve.return_value = target
        real_path = Path
        with mock.patch.object(relay.glob, "glob", return_value=["one"]), mock.patch.object(
            relay, "Path", side_effect=lambda value: link if value == "one" else real_path(value)
        ), mock.patch.object(relay, "_is_realsense_color_node", return_value=True):
            self.assertEqual(relay.resolve_realsense_device(), str(target))

    def test_sysfs_identity_selects_only_d435i_color_capture_index(self):
        with self.subTest("exact identity"):
            self.assertTrue(self._sysfs_identity_result("03", "8086", "0b3a", "0"))
        for field, values in {
            "interface": ("00", "8086", "0b3a", "0"),
            "vendor": ("03", "1234", "0b3a", "0"),
            "product": ("03", "8086", "ffff", "0"),
            "index": ("03", "8086", "0b3a", "1"),
        }.items():
            with self.subTest(field):
                self.assertFalse(self._sysfs_identity_result(*values))

    def _sysfs_identity_result(self, interface, vendor, product, index):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            usb_root = root / "usb-device"
            interface_root = usb_root / "usb-interface"
            video_root = root / "class" / "video6"
            interface_root.mkdir(parents=True)
            video_root.mkdir(parents=True)
            (video_root / "device").symlink_to(interface_root, target_is_directory=True)
            (interface_root / "bInterfaceNumber").write_text(interface, encoding="ascii")
            (usb_root / "idVendor").write_text(vendor, encoding="ascii")
            (usb_root / "idProduct").write_text(product, encoding="ascii")
            (video_root / "index").write_text(index, encoding="ascii")
            return relay._is_realsense_color_node(Path("/dev/video6"), root / "class")

    def test_latest_frame_only_and_viewer_cap(self):
        producers = []

        def factory(publish):
            producer = FakeProducer(publish)
            producers.append(producer)
            return producer

        hub = relay.FrameHub(factory)
        for _ in range(relay.MAX_VIEWERS):
            self.assertTrue(hub.add_viewer())
        self.assertFalse(hub.add_viewer())
        self.assertEqual(len(producers), 1)
        self.assertTrue(producers[0].started)
        first = b"\xff\xd8first\xff\xd9"
        latest = b"\xff\xd8latest\xff\xd9"
        self.assertTrue(hub.publish(first))
        self.assertTrue(hub.publish(latest))
        sequence, frame = hub.wait_after(0)
        self.assertEqual(sequence, 2)
        self.assertEqual(frame, latest)
        self.assertEqual(hub.health()["frames"], 2)
        self.assertEqual(hub.health()["bytes"], len(first) + len(latest))
        self.assertEqual(hub.health()["payload_bytes"], len(first) + len(latest))
        hub.close()

    def test_invalid_and_oversize_frames_are_rejected(self):
        hub = relay.FrameHub(FakeProducer)
        self.assertFalse(hub.publish(b"not jpeg"))
        self.assertFalse(hub.publish(b"\xff\xd8" + b"x" * relay.MAX_JPEG_BYTES + b"\xff\xd9"))
        self.assertEqual(hub.health()["invalid_frames"], 2)

    def test_stream_is_only_readable_by_the_fixed_dashboard_host(self):
        self.assertTrue(relay.client_allowed("192.168.123.99", "/stream"))
        self.assertFalse(relay.client_allowed("192.168.123.18", "/stream"))
        self.assertFalse(relay.client_allowed("192.168.123.161", "/stream"))
        self.assertTrue(relay.client_allowed("127.0.0.1", "/health"))
        self.assertTrue(relay.client_allowed("192.168.123.18", "/health"))
        self.assertTrue(relay.client_allowed("192.168.123.99", "/health"))
        self.assertFalse(relay.client_allowed("192.168.123.161", "/health"))

    def test_first_viewer_starts_source_and_last_uses_grace_timer(self):
        hub = relay.FrameHub(FakeProducer)
        with mock.patch.object(relay.threading, "Timer") as timer_type:
            timer = timer_type.return_value
            self.assertTrue(hub.add_viewer())
            producer = hub._producer
            hub.remove_viewer()
            timer_type.assert_called_once_with(relay.SOURCE_STOP_GRACE_S, hub._stop_if_idle)
            timer.start.assert_called_once()
            hub._stop_if_idle()
        self.assertTrue(producer.stopped)
        self.assertEqual(hub.health()["state"], "idle")

    def test_idle_stop_and_close_clear_stale_frame(self):
        hub = relay.FrameHub(FakeProducer)
        self.assertTrue(hub.add_viewer())
        self.assertTrue(hub.publish(b"\xff\xd8old\xff\xd9"))
        hub.remove_viewer()
        hub._stop_if_idle()
        sequence, frame = hub.wait_after(0)
        self.assertEqual(sequence, 1)
        self.assertIsNone(frame)
        self.assertIsNone(hub.health()["last_frame_age_s"])

        second = relay.FrameHub(FakeProducer)
        self.assertTrue(second.add_viewer())
        self.assertTrue(second.publish(b"\xff\xd8old\xff\xd9"))
        second.close()
        _sequence, frame = second.wait_after(0)
        self.assertIsNone(frame)
        self.assertIsNone(second.health()["last_frame_age_s"])

    def test_health_reports_starting_streaming_stale_and_error(self):
        producers = []

        def factory(publish):
            producer = FakeProducer(publish)
            producers.append(producer)
            return producer

        hub = relay.FrameHub(factory)
        self.assertEqual(hub.health()["state"], "idle")
        self.assertTrue(hub.add_viewer())
        producer = producers[0]
        starting = hub.health()
        self.assertEqual(starting["state"], "starting")
        self.assertTrue(starting["process_running"])
        self.assertEqual(starting["last_error"], "")
        self.assertIsNone(starting["last_frame_age_s"])

        producer.process_started_at = (
            time.monotonic() - relay.SOURCE_STARTUP_TIMEOUT_S - 1.0
        )
        no_frame = hub.health()
        self.assertEqual(no_frame["state"], "error")
        self.assertTrue(no_frame["process_running"])
        self.assertIn("no RealSense JPEG received", no_frame["last_error"])
        producer.process_started_at = time.monotonic()

        self.assertTrue(hub.publish(b"\xff\xd8live\xff\xd9"))
        streaming = hub.health()
        self.assertEqual(streaming["status"], "streaming")
        self.assertEqual(streaming["state"], "streaming")
        self.assertIsNotNone(streaming["last_frame_age_s"])

        now = time.monotonic()
        producer.process_started_at = now - relay.FRAME_STALE_S - 2.0
        with hub._condition:
            hub._last_frame_at = now - relay.FRAME_STALE_S - 1.0
        self.assertEqual(hub.health()["state"], "stale")

        producer.process_running = False
        producer.last_error = "camera disconnected"
        failed = hub.health()
        self.assertEqual(failed["status"], "error")
        self.assertEqual(failed["state"], "error")
        self.assertFalse(failed["process_running"])
        self.assertEqual(failed["last_error"], "camera disconnected")
        hub.close()

    def test_no_frame_keepalive_detects_peer_close_and_releases_viewer(self):
        class WaitingHub:
            def __init__(self):
                self.removed = 0

            def add_viewer(self):
                return True

            def wait_after(self, sequence):
                return sequence, None

            def remove_viewer(self):
                self.removed += 1

        class ClosedPeerWriter:
            def __init__(self):
                self.payloads = []

            def write(self, payload):
                self.payloads.append(payload)
                raise BrokenPipeError("peer closed")

            def flush(self):
                pass

        hub = WaitingHub()
        writer = ClosedPeerWriter()
        handler = object.__new__(relay.RelayHandler)
        handler.server = types.SimpleNamespace(hub=hub)
        handler.wfile = writer
        handler.send_response = mock.Mock()
        handler.send_header = mock.Mock()
        handler.end_headers = mock.Mock()
        handler._stream()

        self.assertEqual(writer.payloads, [relay.KEEPALIVE_PART])
        self.assertNotIn(b"\xff\xd8", relay.KEEPALIVE_PART)
        self.assertEqual(hub.removed, 1)

    def test_only_health_and_stream_get_routes_exist(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('self.path == "/health"', source)
        self.assertIn('self.path == "/stream"', source)
        self.assertNotIn("SimpleHTTPRequestHandler", source)
        self.assertNotIn("removeprefix", source)
        self.assertIn("shell=False", source)

    def test_service_is_non_root_capability_free_and_keeps_camera_devices(self):
        service = (ROOT / "deploy" / "robot-scope-realsense-camera.service.example").read_text(
            encoding="utf-8"
        )
        self.assertIn("User=unitree", service)
        self.assertIn("SupplementaryGroups=video", service)
        self.assertIn("PrivateDevices=false", service)
        self.assertIn("CapabilityBoundingSet=\n", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("StartLimitIntervalSec=0", service)
        self.assertIn("/usr/local/libexec/robot-scope/realsense_mjpeg_relay.py", service)
        self.assertNotIn("AmbientCapabilities=", service)
        self.assertNotIn("MemoryDenyWriteExecute=true", service)
        self.assertNotIn("ProtectClock=true", service)


if __name__ == "__main__":
    unittest.main()
