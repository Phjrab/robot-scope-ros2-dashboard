import io
import threading
import time
import unittest
from unittest.mock import Mock, patch

from robot_dashboard.remote_mjpeg_camera import (
    MAX_JPEG_BYTES,
    MAX_METRIC_SAMPLES,
    METRIC_WINDOW_S,
    RemoteMjpegCamera,
    _bounded_relay_health,
    allowed_realsense_relay_host,
    allowed_realsense_relay_port,
)


URL = "http://192.168.123.18:8090/stream"


def jpeg_with_sof(width, height, *, marker=0xC0):
    sof = (
        bytes((0xFF, marker))
        + (11).to_bytes(2, "big")
        + bytes((8,))
        + int(height).to_bytes(2, "big")
        + int(width).to_bytes(2, "big")
        + b"\x01\x01\x11\x00"
    )
    return b"\xff\xd8\xff\xe0\x00\x04RS" + sof + b"\xff\xd9"


def camera(callback=lambda _jpeg: None, **overrides):
    values = {
        "enabled": True,
        "url": URL,
        "allowed_urls": [URL],
    }
    values.update(overrides)
    return RemoteMjpegCamera(callback, **values)


class RemoteMjpegCameraTests(unittest.TestCase):
    def test_only_exact_fixed_realsense_endpoint_is_configured(self):
        self.assertTrue(camera().configured)
        for value in (
            "http://192.168.123.18:8090/other",
            "http://192.168.123.19:8090/stream",
            "https://192.168.123.18:8090/stream",
            "http://user@192.168.123.18:8090/stream",
        ):
            with self.subTest(url=value):
                receiver = camera(url=value, allowed_urls=[value])
                self.assertFalse(receiver.configured)

    def test_private_runtime_relay_host_is_exactly_allowlisted(self):
        runtime_url = "http://192.168.50.103:8090/stream"
        receiver = camera(
            url=runtime_url,
            allowed_urls=[runtime_url],
            relay_host="192.168.50.103",
        )
        self.assertTrue(receiver.configured)
        self.assertTrue(allowed_realsense_relay_host("169.254.10.2"))
        for value in (
            "0.0.0.0",
            "127.0.0.1",
            "192.168.50.0",
            "192.168.50.255",
            "224.0.0.1",
            "8.8.8.8",
            "relay.local",
            "::1",
        ):
            with self.subTest(value=value):
                self.assertFalse(allowed_realsense_relay_host(value))
                blocked = camera(relay_host=value)
                self.assertFalse(blocked.configured)

    def test_relay_port_is_explicit_and_bounded(self):
        for value in (1024, 8090, 65535, "18090"):
            with self.subTest(value=value):
                self.assertTrue(allowed_realsense_relay_port(value))
        for value in (None, "", 0, 80, 65536, "8090/path", "port"):
            with self.subTest(value=value):
                self.assertFalse(allowed_realsense_relay_port(value))
        for url in (
            "http://192.168.123.18:80/stream",
            "http://192.168.123.18:65536/stream",
        ):
            with self.subTest(url=url):
                self.assertFalse(camera(url=url, allowed_urls=[url]).configured)

    def test_extracts_complete_jpegs_and_rejects_oversize_frame(self):
        frames = []
        receiver = camera(frames.append)
        receiver._read_jpegs(io.BytesIO(b"header\xff\xd8one\xff\xd9tail\xff\xd8two\xff\xd9"))
        self.assertEqual(frames, [b"\xff\xd8one\xff\xd9", b"\xff\xd8two\xff\xd9"])

        oversized = b"\xff\xd8" + (b"x" * MAX_JPEG_BYTES) + b"\xff\xd9"
        receiver._read_jpegs(io.BytesIO(oversized))
        self.assertEqual(receiver.status()["oversize_frames"], 1)
        self.assertEqual(len(frames), 2)

    def test_published_jpeg_exposes_bounded_sof_dimensions(self):
        receiver = camera()
        receiver._publish_jpeg(jpeg_with_sof(640, 480))
        status = receiver.status()
        self.assertEqual((status["width"], status["height"]), (640, 480))

        receiver._publish_jpeg(jpeg_with_sof(1280, 720, marker=0xC2))
        status = receiver.status()
        self.assertEqual((status["width"], status["height"]), (1280, 720))

    def test_dimension_scan_rejects_embedded_or_unbounded_sof_metadata(self):
        receiver = camera()
        embedded_sof = b"\xff\xd8\xff\xe0\x00\x0bxx\xff\xc0\x00\x03abc\xff\xd9"
        receiver._publish_jpeg(embedded_sof)
        self.assertEqual(
            (receiver.status()["width"], receiver.status()["height"]),
            (0, 0),
        )

        receiver._publish_jpeg(jpeg_with_sof(9000, 480))
        self.assertEqual(
            (receiver.status()["width"], receiver.status()["height"]),
            (0, 0),
        )

    def test_run_once_uses_direct_http_connection_and_rejects_redirect(self):
        response = Mock()
        response.status = 302
        response.headers = {"Location": "http://evil.example/stream"}
        connection = Mock()
        connection.getresponse.return_value = response
        with patch(
            "robot_dashboard.remote_mjpeg_camera.http.client.HTTPConnection",
            return_value=connection,
        ) as constructor:
            error = camera()._run_once()
        constructor.assert_called_once_with("192.168.123.18", 8090, timeout=6.0)
        connection.request.assert_called_once()
        self.assertEqual(error, "remote camera returned HTTP 302")

    def test_valid_multipart_response_publishes_jpeg(self):
        frames = []
        response = Mock()
        response.status = 200
        response.headers = {"Content-Type": "multipart/x-mixed-replace; boundary=frame"}
        response.read1.side_effect = [b"--frame\r\n\xff\xd8ok\xff\xd9\r\n", b""]
        connection = Mock()
        connection.getresponse.return_value = response
        with patch(
            "robot_dashboard.remote_mjpeg_camera.http.client.HTTPConnection",
            return_value=connection,
        ):
            receiver = camera(frames.append)
            error = receiver._run_once()
        self.assertEqual(error, "remote MJPEG stream ended")
        self.assertEqual(frames, [b"\xff\xd8ok\xff\xd9"])
        self.assertEqual(receiver.status()["frames"], 1)
        self.assertGreater(receiver.status()["network_bytes"], 0)
        self.assertGreaterEqual(receiver.status()["receive_bitrate_mbps"], 0)
        self.assertEqual(receiver.status()["decode_successes"], 1)
        self.assertEqual(receiver.status()["decode_failures"], 0)
        self.assertEqual(receiver.status()["metric_window_s"], METRIC_WINDOW_S)
        self.assertLessEqual(len(receiver._transport_samples), MAX_METRIC_SAMPLES)
        self.assertEqual(
            receiver.status()["cross_host_latency_state"],
            "UNVERIFIED_CLOCK_DOMAIN",
        )

    def test_relay_health_projection_rejects_malformed_and_bounds_nested_fields(self):
        self.assertEqual(_bounded_relay_health("not an object"), {})
        projected = _bounded_relay_health(
            {
                "state": "streaming",
                "fps": "15.2",
                "frames": "bad",
                "profile": {"width": 99_999, "height": -1, "fps": float("nan")},
                "wifi": {
                    "state": "unexpected",
                    "interface": "x" * 100,
                    "rssi_dbm": -52,
                    "link_mbps": float("inf"),
                    "reason": "r" * 500,
                },
            }
        )
        self.assertEqual(projected["fps"], 15.2)
        self.assertEqual(projected["frames"], 0)
        self.assertEqual(projected["profile"]["width"], 8192)
        self.assertEqual(projected["profile"]["height"], 0)
        self.assertIsNone(projected["profile"]["fps"])
        self.assertEqual(projected["wifi"]["state"], "UNVERIFIED")
        self.assertLessEqual(len(projected["wifi"]["interface"]), 32)
        self.assertIsNone(projected["wifi"]["link_mbps"])
        self.assertLessEqual(len(projected["wifi"]["reason"]), 120)

    def test_expired_windows_and_relay_health_transition_to_stale(self):
        receiver = camera()
        now = time.monotonic()
        with receiver._lock:
            receiver._frame_times.extend((now - 10.0, now - 9.0))
            receiver._transport_samples.append((now - 10.0, 100_000))
            receiver._relay_health = {
                "state": "streaming",
                "wifi": {"state": "LIVE"},
            }
            receiver._relay_health_at = now - 10.0
        status = receiver.status()
        self.assertIsNone(status["receive_fps"])
        self.assertEqual(status["receive_bitrate_mbps"], 0.0)
        self.assertEqual(status["relay_health"]["state"], "stale")
        self.assertEqual(status["relay_health"]["wifi"]["state"], "STALE")

    def test_stop_closes_blocking_response_and_joins_thread(self):
        receiver = camera()
        response = Mock()
        receiver._response = response
        receiver._thread = threading.current_thread()
        receiver.stop()
        response.close.assert_called_once_with()
        self.assertEqual(receiver.status()["state"], "stopped")


if __name__ == "__main__":
    unittest.main()
