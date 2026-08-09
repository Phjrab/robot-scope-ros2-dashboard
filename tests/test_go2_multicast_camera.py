import time
import unittest
from unittest.mock import patch

from robot_dashboard.go2_multicast_camera import Go2MulticastCamera


class ChunkStream:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def read(self, _size):
        return self.chunks.pop(0) if self.chunks else b""


class FakeProcess:
    def __init__(self):
        self.returncode = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def camera_for(callback=lambda _jpeg: None, **overrides):
    values = {
        "enabled": True,
        "interface": "eno1",
        "allowed_interfaces": ["eno1"],
        "restart_initial_s": 0.1,
        "restart_max_s": 0.25,
    }
    values.update(overrides)
    return Go2MulticastCamera(callback, **values)


class Go2MulticastCameraTests(unittest.TestCase):
    def test_rejects_interface_outside_explicit_allowlist(self):
        camera = camera_for(interface="wlan0")
        status = camera.status()
        self.assertFalse(status["configured"])
        self.assertEqual(status["state"], "error")
        self.assertIn("not allowlisted", status["last_error"])
        self.assertFalse(camera.start())
        with self.assertRaises(ValueError):
            camera.command()

    def test_builds_fixed_shell_free_rtp_h264_pipeline(self):
        command = camera_for().command()
        self.assertIsInstance(command, tuple)
        self.assertEqual(command[0], "gst-launch-1.0")
        self.assertIn("address=230.1.1.1", command)
        self.assertIn("port=1720", command)
        self.assertIn("multicast-iface=eno1", command)
        self.assertIn("application/x-rtp,media=video,encoding-name=H264", command)
        self.assertIn("rtph264depay", command)
        self.assertIn("avdec_h264", command)
        self.assertIn("jpegenc", command)
        self.assertNotIn("sh", command)
        self.assertNotIn("-c", command)

    def test_extracts_complete_jpegs_across_pipe_chunk_boundaries(self):
        frames = []
        camera = camera_for(frames.append)
        first = b"\xff\xd8first\xff\xd9"
        second = b"\xff\xd8second\xff\xd9"
        stream = ChunkStream(
            [b"garbage\xff", b"\xd8first\xff", b"\xd9noise" + second[:5], second[5:]]
        )

        camera._read_jpegs(stream)

        self.assertEqual(frames, [first, second])
        status = camera.status()
        self.assertEqual(status["frames"], 2)
        self.assertEqual(status["state"], "ok")
        self.assertEqual(status["source"], "go2_multicast")
        self.assertEqual(status["uri"], "go2-camera://230.1.1.1:1720")

    def test_supervisor_uses_capped_exponential_restart_delay(self):
        camera = camera_for()
        delays = []

        def fake_wait(delay):
            delays.append(delay)
            if len(delays) == 4:
                camera._stop_event.set()
                return True
            return False

        with patch.object(camera, "_run_once", return_value="pipeline failed"), patch.object(
            camera._stop_event, "wait", side_effect=fake_wait
        ):
            camera._supervise()

        self.assertEqual(delays, [0.1, 0.2, 0.25, 0.25])
        self.assertEqual(camera.status()["restart_count"], 4)
        self.assertEqual(camera.status()["state"], "stopped")

    def test_stop_terminates_running_pipeline_and_is_idempotent(self):
        camera = camera_for()
        process = FakeProcess()
        camera._process = process

        camera.stop()
        camera.stop()

        self.assertTrue(process.terminated)
        self.assertFalse(process.killed)
        self.assertEqual(camera.status()["state"], "stopped")

    def test_status_marks_old_frames_stale(self):
        camera = camera_for()
        camera._publish_jpeg(b"\xff\xd8frame\xff\xd9")
        camera._last_frame_at = time.monotonic() - 4.0
        self.assertEqual(camera.status()["state"], "stale")

    def test_callback_failure_does_not_count_as_a_live_delivered_frame(self):
        def fail(_jpeg):
            raise RuntimeError("dashboard unavailable")

        camera = camera_for(fail)
        camera._publish_jpeg(b"\xff\xd8frame\xff\xd9")

        status = camera.status()
        self.assertEqual(status["frames"], 0)
        self.assertFalse(status["live"])
        self.assertIsNone(status["age_s"])
        self.assertIn("callback failed", status["last_error"])

    def test_watchdog_terminates_process_that_never_produces_a_frame(self):
        camera = camera_for(startup_frame_timeout_s=2.0)
        process = FakeProcess()
        camera._process = process
        with patch.object(camera._stop_event, "wait", return_value=False), patch(
            "robot_dashboard.go2_multicast_camera.time.monotonic", return_value=12.0
        ):
            camera._watch_process(process, started_at=10.0, initial_frame_count=0)

        self.assertTrue(process.terminated)
        self.assertEqual(camera._state, "restarting")
        self.assertIn("startup frame timeout", camera._process_failure_reason)

    def test_watchdog_terminates_process_when_live_frames_stall(self):
        camera = camera_for(stale_after_s=1.0)
        process = FakeProcess()
        camera._process = process
        camera._frames = 4
        camera._last_frame_at = 20.0
        with patch.object(camera._stop_event, "wait", return_value=False), patch(
            "robot_dashboard.go2_multicast_camera.time.monotonic", return_value=26.0
        ):
            camera._watch_process(process, started_at=10.0, initial_frame_count=3)

        self.assertTrue(process.terminated)
        self.assertEqual(camera.frame_timeout_s, 6.0)
        self.assertEqual(camera._state, "restarting")
        self.assertIn("frame stream stalled", camera._process_failure_reason)

    def test_popen_receives_an_argument_array_with_shell_disabled(self):
        process = FakeProcess()
        process.returncode = 0
        process.stdout = ChunkStream([])
        process.stderr = ChunkStream([])
        with patch(
            "robot_dashboard.go2_multicast_camera.shutil.which",
            return_value="/usr/bin/gst-launch-1.0",
        ) as which:
            camera = camera_for()
            with patch(
                "robot_dashboard.go2_multicast_camera.subprocess.Popen", return_value=process
            ) as popen:
                camera._run_once()
            camera.status()
            camera.status()

        args, kwargs = popen.call_args
        self.assertIsInstance(args[0], list)
        self.assertEqual(args[0][0], "/usr/bin/gst-launch-1.0")
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(which.call_count, 1)


if __name__ == "__main__":
    unittest.main()
