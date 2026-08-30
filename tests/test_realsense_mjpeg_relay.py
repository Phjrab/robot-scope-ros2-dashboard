import importlib.util
import stat
import sys
import tempfile
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
        self.assertEqual(relay.METRIC_WINDOW_S, 5.0)
        self.assertEqual(relay.MAX_METRIC_SAMPLES, 120)

    def test_private_or_link_local_network_hosts_are_configurable(self):
        self.assertEqual(
            relay.relay_network_hosts(
                {
                    relay.RELAY_BIND_HOST_ENV: "192.168.50.103",
                    relay.RELAY_DASHBOARD_HOST_ENV: "192.168.50.10",
                }
            ),
            ("192.168.50.103", "192.168.50.10"),
        )
        self.assertEqual(
            relay.relay_network_hosts(
                {
                    relay.RELAY_BIND_HOST_ENV: "169.254.50.103",
                    relay.RELAY_DASHBOARD_HOST_ENV: "169.254.50.10",
                }
            ),
            ("169.254.50.103", "169.254.50.10"),
        )
        for value in (
            "0.0.0.0",
            "127.0.0.1",
            "192.168.50.255",
            "224.0.0.1",
            "8.8.8.8",
            "relay.local",
            "::1",
        ):
            with self.subTest(value=value):
                with self.assertRaises(relay.RelaySetupError):
                    relay.relay_network_hosts(
                        {
                            relay.RELAY_BIND_HOST_ENV: value,
                            relay.RELAY_DASHBOARD_HOST_ENV: "192.168.50.10",
                        }
                    )

    def test_reference_defaults_are_explicit_and_missing_env_is_compatible(self):
        config = relay.relay_configuration({})
        self.assertEqual(
            config,
            relay.RelayConfig(
                bind_host="192.168.123.18",
                dashboard_host="192.168.123.99",
                port=8090,
                width=640,
                height=480,
                fps=15,
                jpeg_quality=72,
            ),
        )

    def test_profile_and_port_are_bounded_without_silent_fallback(self):
        base = {
            relay.RELAY_BIND_HOST_ENV: "192.168.50.30",
            relay.RELAY_DASHBOARD_HOST_ENV: "192.168.50.10",
        }
        configured = relay.relay_configuration(
            {
                **base,
                relay.RELAY_PORT_ENV: "18090",
                relay.RELAY_WIDTH_ENV: "1280",
                relay.RELAY_HEIGHT_ENV: "720",
                relay.RELAY_FPS_ENV: "30",
                relay.RELAY_JPEG_QUALITY_ENV: "80",
            }
        )
        self.assertEqual(
            (configured.port, configured.width, configured.height),
            (18090, 1280, 720),
        )
        self.assertEqual((configured.fps, configured.jpeg_quality), (30, 80))

        invalid_values = {
            relay.RELAY_PORT_ENV: ("", "80", "65536"),
            relay.RELAY_WIDTH_ENV: ("0", "641", "1920"),
            relay.RELAY_HEIGHT_ENV: ("0", "481", "1080"),
            relay.RELAY_FPS_ENV: ("0", "16", "60"),
            relay.RELAY_JPEG_QUALITY_ENV: ("39", "91", "quality"),
        }
        for key, values in invalid_values.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    with self.assertRaisesRegex(
                        relay.RelaySetupError, "INVALID_CONFIG"
                    ):
                        relay.relay_configuration({**base, key: value})

    def test_dashboard_pair_and_local_bind_fail_closed(self):
        with self.assertRaisesRegex(
            relay.RelaySetupError, "DASHBOARD_ADDRESS_REJECTED"
        ):
            relay.relay_configuration(
                {
                    relay.RELAY_BIND_HOST_ENV: "192.168.50.30",
                    relay.RELAY_DASHBOARD_HOST_ENV: "192.168.51.10",
                }
            )
        with self.assertRaisesRegex(
            relay.RelaySetupError, "BIND_ADDRESS_MISSING"
        ):
            relay.relay_configuration(
                {
                    relay.RELAY_BIND_HOST_ENV: "192.168.50.30",
                    relay.RELAY_DASHBOARD_HOST_ENV: "192.168.50.10",
                },
                validate_local_bind=True,
                local_bind_check=lambda _host: False,
            )
        config = relay.relay_configuration(
            {
                relay.RELAY_BIND_HOST_ENV: "192.168.50.30",
                relay.RELAY_DASHBOARD_HOST_ENV: "192.168.50.10",
            },
            validate_local_bind=True,
            local_bind_check=lambda host: host == "192.168.50.30",
        )
        self.assertEqual(config.bind_host, "192.168.50.30")

    def test_optional_wifi_interface_is_validated_without_shell_input(self):
        config = relay.relay_configuration(
            {relay.RELAY_WIFI_INTERFACE_ENV: "wlx001122aabbcc"}
        )
        self.assertEqual(config.wifi_interface, "wlx001122aabbcc")
        for value in ("wlan0;id", "$(id)", "wifi interface", "x" * 33):
            with self.subTest(value=value):
                with self.assertRaises(relay.RelaySetupError):
                    relay.relay_configuration({relay.RELAY_WIFI_INTERFACE_ENV: value})

    def test_wifi_probe_is_fixed_argv_cached_and_bounded(self):
        completed = types.SimpleNamespace(
            returncode=0,
            stdout=b"Connected\n\tsignal: -51 dBm\n\ttx bitrate: 433.3 MBit/s\n",
        )
        with (
            mock.patch.object(relay.os.path, "isfile", return_value=True),
            mock.patch.object(relay.os, "access", return_value=True),
            mock.patch.object(relay.subprocess, "run", return_value=completed) as run,
        ):
            probe = relay.WifiLinkProbe("wlan0")
            first = probe.status()
            second = probe.status()
        self.assertEqual(first["state"], "LIVE")
        self.assertEqual(first["rssi_dbm"], -51)
        self.assertEqual(first["link_mbps"], 433.3)
        self.assertEqual(first, second)
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command[1:], ["dev", "wlan0", "link"])
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(run.call_args.kwargs["timeout"], relay.WIFI_PROBE_TIMEOUT_S)

    def test_wifi_probe_timeout_is_unverified(self):
        with (
            mock.patch.object(relay.os.path, "isfile", return_value=True),
            mock.patch.object(relay.os, "access", return_value=True),
            mock.patch.object(
                relay.subprocess,
                "run",
                side_effect=relay.subprocess.TimeoutExpired(["iw"], 1.0),
            ),
        ):
            status = relay.WifiLinkProbe("wlan0").status()
        self.assertEqual(status["state"], "UNVERIFIED")
        self.assertIn("timed out", status["reason"])

    def test_wifi_probe_missing_executable_is_unverified(self):
        with mock.patch.object(relay.os.path, "isfile", return_value=False):
            status = relay.WifiLinkProbe("wlan0").status()
        self.assertEqual(status["state"], "UNVERIFIED")
        self.assertIn("unavailable", status["reason"])

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

        custom = relay.RelayConfig(
            bind_host="192.168.50.30",
            dashboard_host="192.168.50.10",
            port=18090,
            width=1280,
            height=720,
            fps=30,
            jpeg_quality=80,
        )
        custom_command = relay.gstreamer_command("/dev/video6", custom)
        self.assertIn(
            "video/x-raw,format=YUY2,width=1280,height=720,framerate=30/1",
            custom_command,
        )
        self.assertIn("quality=80", custom_command)

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

    @mock.patch.object(relay, "_plugin_available", return_value=False)
    def test_pipeline_reports_bounded_encoder_error(self, _available):
        with self.assertRaises(relay.RelaySetupError) as captured:
            relay.gstreamer_command("/dev/video6")
        self.assertEqual(captured.exception.code, "ENCODER_UNAVAILABLE")

    def test_capture_process_error_does_not_expose_raw_exception_text(self):
        producer = relay.GstProducer(lambda _jpeg: True)
        with mock.patch.object(
            producer,
            "_run_once",
            side_effect=OSError("/private/operator/path must not leak"),
        ), mock.patch.object(producer._stop, "wait", return_value=True):
            producer._run()
        error = producer.status()["last_error"]
        self.assertEqual(
            error,
            "SOURCE_STALE: RealSense capture process unavailable",
        )
        self.assertNotIn("/private", error)

    def test_device_resolution_requires_exactly_one_verified_color_device(self):
        with mock.patch.object(relay.glob, "glob", return_value=[]):
            with self.assertRaises(relay.RelaySetupError) as captured:
                relay.resolve_realsense_device()
            self.assertEqual(captured.exception.code, "DEVICE_NOT_FOUND")
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

    def test_health_uses_bounded_recent_rate_window_and_explicit_clock_domain(self):
        class Probe:
            @staticmethod
            def status():
                return {"state": "UNVERIFIED"}

        hub = relay.FrameHub(FakeProducer, wifi_probe=Probe())
        with hub._condition:
            hub._frame_samples.extend(
                ((100.0, 100_000), (102.0, 200_000), (105.0, 300_000))
            )
        with mock.patch.object(relay.time, "monotonic", return_value=106.0):
            health = hub.health()
        self.assertEqual(len(hub._frame_samples), 2)
        self.assertEqual(health["metric_window_s"], 5.0)
        self.assertGreater(health["payload_bitrate_mbps"], 0)
        self.assertLessEqual(len(hub._frame_samples), relay.MAX_METRIC_SAMPLES)
        self.assertEqual(health["clock_domain"], "relay_monotonic")
        self.assertEqual(
            health["cross_host_latency_state"], "UNVERIFIED_CLOCK_DOMAIN"
        )

    def test_invalid_and_oversize_frames_are_rejected(self):
        hub = relay.FrameHub(FakeProducer)
        self.assertFalse(hub.publish(b"not jpeg"))
        self.assertFalse(hub.publish(b"\xff\xd8" + b"x" * relay.MAX_JPEG_BYTES + b"\xff\xd9"))
        self.assertEqual(hub.health()["invalid_frames"], 2)

    def test_stream_is_only_readable_by_fixed_dashboard_and_local_shadow_host(self):
        self.assertTrue(relay.client_allowed("192.168.123.99", "/stream"))
        self.assertTrue(relay.client_allowed("192.168.123.18", "/stream"))
        self.assertFalse(relay.client_allowed("192.168.123.161", "/stream"))
        self.assertTrue(relay.client_allowed("127.0.0.1", "/health"))
        self.assertTrue(relay.client_allowed("192.168.123.18", "/health"))
        self.assertTrue(relay.client_allowed("192.168.123.99", "/health"))
        self.assertFalse(relay.client_allowed("192.168.123.161", "/health"))

        wireless = relay.RelayConfig(
            bind_host="192.168.50.30",
            dashboard_host="192.168.50.10",
            port=8090,
            width=640,
            height=480,
            fps=15,
            jpeg_quality=72,
        )
        self.assertTrue(relay.client_allowed("192.168.50.10", "/stream", wireless))
        self.assertTrue(relay.client_allowed("192.168.50.30", "/stream", wireless))
        self.assertFalse(relay.client_allowed("192.168.50.11", "/stream", wireless))
        self.assertTrue(relay.client_allowed("192.168.50.30", "/health", wireless))

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

    def test_late_frame_from_stopped_generation_cannot_repopulate_idle_health(self):
        class LateProducer(FakeProducer):
            def stop(self):
                self.publish(b"\xff\xd8late\xff\xd9")
                super().stop()

        hub = relay.FrameHub(LateProducer)
        self.assertTrue(hub.add_viewer())
        self.assertTrue(hub.publish(b"\xff\xd8live\xff\xd9"))
        hub.remove_viewer()
        hub._stop_if_idle()

        health = hub.health()
        self.assertEqual(health["state"], "idle")
        self.assertEqual(health["frames"], 1)
        self.assertIsNone(health["last_frame_age_s"])

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

            def wait_packet_after(self, sequence):
                return sequence, None, None

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

    def test_stream_frame_carries_source_sequence_and_capture_clock(self):
        jpeg = b"\xff\xd8frame\xff\xd9"

        class OneFrameHub:
            removed = 0
            source_epoch = 987654321

            @staticmethod
            def add_viewer():
                return True

            @staticmethod
            def wait_packet_after(_sequence):
                return 7, jpeg, 123456789

            def remove_viewer(self):
                self.removed += 1

        class OneFrameWriter:
            def __init__(self):
                self.payload = b""

            def write(self, payload):
                self.payload += payload
                if jpeg in self.payload:
                    raise BrokenPipeError("done")

            @staticmethod
            def flush():
                return None

        hub = OneFrameHub()
        writer = OneFrameWriter()
        handler = object.__new__(relay.RelayHandler)
        handler.server = types.SimpleNamespace(hub=hub)
        handler.wfile = writer
        handler.send_response = mock.Mock()
        handler.send_header = mock.Mock()
        handler.end_headers = mock.Mock()
        handler._stream()
        self.assertIn(b"X-Robot-Scope-Source-Epoch: 987654321\r\n", writer.payload)
        self.assertIn(b"X-Robot-Scope-Sequence: 7\r\n", writer.payload)
        self.assertIn(b"X-Robot-Scope-Capture-Clock: robot-monotonic\r\n", writer.payload)
        self.assertIn(
            b"X-Robot-Scope-Capture-Monotonic-Ns: 123456789\r\n",
            writer.payload,
        )
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
        self.assertIn(
            "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK",
            service,
        )
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("StartLimitIntervalSec=60", service)
        self.assertIn("StartLimitBurst=5", service)
        self.assertIn(
            "EnvironmentFile=/home/unitree/.config/robot-scope/realsense-camera.env",
            service,
        )
        self.assertIn("/usr/local/libexec/robot-scope/realsense_mjpeg_relay.py", service)
        self.assertNotIn("AmbientCapabilities=", service)
        self.assertNotIn("MemoryDenyWriteExecute=true", service)
        self.assertNotIn("ProtectClock=true", service)


if __name__ == "__main__":
    unittest.main()
