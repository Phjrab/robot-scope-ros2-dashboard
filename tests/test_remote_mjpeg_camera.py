import io
import threading
import unittest
from unittest.mock import Mock, patch

from robot_dashboard.remote_mjpeg_camera import MAX_JPEG_BYTES, RemoteMjpegCamera


URL = "http://192.168.123.18:8090/stream"


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

    def test_extracts_complete_jpegs_and_rejects_oversize_frame(self):
        frames = []
        receiver = camera(frames.append)
        receiver._read_jpegs(io.BytesIO(b"header\xff\xd8one\xff\xd9tail\xff\xd8two\xff\xd9"))
        self.assertEqual(frames, [b"\xff\xd8one\xff\xd9", b"\xff\xd8two\xff\xd9"])

        oversized = b"\xff\xd8" + (b"x" * MAX_JPEG_BYTES) + b"\xff\xd9"
        receiver._read_jpegs(io.BytesIO(oversized))
        self.assertEqual(receiver.status()["oversize_frames"], 1)
        self.assertEqual(len(frames), 2)

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
