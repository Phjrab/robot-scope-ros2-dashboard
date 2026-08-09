"""Direct Go2 front-camera receiver for the factory RTP/H.264 multicast.

The Go2 publishes its front camera independently from ROS 2 on
``230.1.1.1:1720``.  This module keeps that transport isolated behind a
bounded GStreamer subprocess and emits complete JPEG frames to the dashboard.
No command is evaluated by a shell and the network interface must be present
in an explicit allowlist.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
from collections import deque
from typing import Callable, Dict, Optional, Sequence, Tuple


GO2_CAMERA_MULTICAST_ADDRESS = "230.1.1.1"
GO2_CAMERA_MULTICAST_PORT = 1720
_INTERFACE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,32}$")


class Go2MulticastCamera:
    """Receive the Go2 RTP/H.264 multicast and publish bounded JPEG frames."""

    def __init__(
        self,
        on_jpeg: Callable[[bytes], None],
        *,
        enabled: bool,
        interface: str,
        allowed_interfaces: Sequence[str],
        width: int = 1280,
        height: int = 720,
        fps_limit: int = 15,
        jpeg_quality: int = 80,
        stale_after_s: float = 3.0,
        startup_frame_timeout_s: float = 8.0,
        frame_timeout_s: Optional[float] = None,
        restart_initial_s: float = 0.5,
        restart_max_s: float = 8.0,
        gst_binary: str = "gst-launch-1.0",
    ) -> None:
        self.on_jpeg = on_jpeg
        self.enabled = bool(enabled)
        self.interface = str(interface or "").strip()
        self.allowed_interfaces = tuple(
            dict.fromkeys(str(value).strip() for value in allowed_interfaces if str(value).strip())
        )
        self.width = max(160, min(int(width), 1920))
        self.height = max(90, min(int(height), 1080))
        self.fps_limit = max(1, min(int(fps_limit), 30))
        self.jpeg_quality = max(40, min(int(jpeg_quality), 95))
        self.stale_after_s = max(0.5, min(float(stale_after_s), 15.0))
        self.startup_frame_timeout_s = max(
            2.0,
            min(float(startup_frame_timeout_s), 60.0),
        )
        default_frame_timeout = max(self.stale_after_s * 2.0, 6.0)
        self.frame_timeout_s = max(
            default_frame_timeout,
            min(
                float(frame_timeout_s) if frame_timeout_s is not None else default_frame_timeout,
                60.0,
            ),
        )
        self.restart_initial_s = max(0.1, min(float(restart_initial_s), 5.0))
        self.restart_max_s = max(
            self.restart_initial_s,
            min(float(restart_max_s), 30.0),
        )
        self.gst_binary = str(gst_binary)
        # Availability is immutable for this process lifetime.  Caching avoids
        # a PATH lookup for every 20 ms WebSocket camera snapshot.
        self._gst_executable = shutil.which(self.gst_binary)

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen] = None
        self._termination_requested_for: Optional[subprocess.Popen] = None
        self._process_failure_reason = ""
        self._state = "disabled" if not self.enabled else "waiting"
        self._last_error = ""
        self._last_frame_at = 0.0
        self._frames = 0
        self._restart_count = 0
        self._restart_in_s: Optional[float] = None
        self._frame_times: deque[float] = deque(maxlen=120)
        self._stderr_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self._configuration_error = self._validate_configuration()
        if self._configuration_error:
            self._state = "error"
            self._last_error = self._configuration_error

    def _validate_configuration(self) -> str:
        if not self.enabled:
            return ""
        if not self.interface or not _INTERFACE_RE.fullmatch(self.interface):
            return "Go2 camera interface is missing or invalid"
        if not self.allowed_interfaces:
            return "Go2 camera interface allowlist is empty"
        if self.interface not in self.allowed_interfaces:
            return f"Go2 camera interface {self.interface!r} is not allowlisted"
        return ""

    @property
    def configured(self) -> bool:
        return self.enabled and not self._configuration_error

    @property
    def source_uri(self) -> str:
        return f"go2-camera://{GO2_CAMERA_MULTICAST_ADDRESS}:{GO2_CAMERA_MULTICAST_PORT}"

    def command(self) -> Tuple[str, ...]:
        """Return the fixed, shell-free GStreamer command for this receiver."""

        if self._configuration_error:
            raise ValueError(self._configuration_error)
        return (
            self.gst_binary,
            "-q",
            "udpsrc",
            f"address={GO2_CAMERA_MULTICAST_ADDRESS}",
            f"port={GO2_CAMERA_MULTICAST_PORT}",
            f"multicast-iface={self.interface}",
            "auto-multicast=true",
            "!",
            "application/x-rtp,media=video,encoding-name=H264",
            "!",
            "rtpjitterbuffer",
            "latency=80",
            "drop-on-latency=true",
            "!",
            "rtph264depay",
            "!",
            "h264parse",
            "disable-passthrough=true",
            "!",
            "avdec_h264",
            "output-corrupt=false",
            "!",
            "videoconvert",
            "!",
            "videoscale",
            "method=0",
            "!",
            "videorate",
            "drop-only=true",
            "!",
            (
                "video/x-raw,format=I420,"
                f"width={self.width},height={self.height},framerate={self.fps_limit}/1"
            ),
            "!",
            "jpegenc",
            f"quality={self.jpeg_quality}",
            "!",
            "fdsink",
            "fd=1",
            "sync=false",
        )

    def start(self) -> bool:
        with self._lock:
            if not self.configured:
                return False
            if self._thread and self._thread.is_alive():
                return True
            self._stop_event.clear()
            self._state = "starting"
            self._restart_in_s = None
            self._thread = threading.Thread(
                target=self._supervise,
                name="go2-multicast-camera",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            process = self._process
        self._request_process_termination(process)
        self._wait_process_exit(process)
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=3.0)
        with self._lock:
            self._process = None
            self._restart_in_s = None
            if self.enabled and not self._configuration_error:
                self._state = "stopped"

    def _supervise(self) -> None:
        delay = self.restart_initial_s
        while not self._stop_event.is_set():
            with self._lock:
                frame_count_before = self._frames
                self._state = "starting" if self._restart_count == 0 else "restarting"
                self._restart_in_s = None
            error = self._run_once()
            if self._stop_event.is_set():
                break
            with self._lock:
                delivered = self._frames > frame_count_before
                self._restart_count += 1
                self._state = "restarting"
                self._restart_in_s = round(delay, 2)
                if error:
                    self._last_error = error[-400:]
            if self._stop_event.wait(delay):
                break
            delay = self.restart_initial_s if delivered else min(delay * 2.0, self.restart_max_s)
        with self._lock:
            self._process = None
            self._restart_in_s = None
            if not self._configuration_error:
                self._state = "stopped"

    def _run_once(self) -> str:
        executable = self._gst_executable
        if not executable:
            return f"{self.gst_binary} is not installed"
        command = list(self.command())
        command[0] = executable
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                shell=False,
            )
        except OSError as exc:
            return f"failed to start Go2 camera pipeline: {exc}"

        with self._lock:
            self._process = process
            self._termination_requested_for = None
            self._process_failure_reason = ""
            self._state = "waiting"
            self._last_error = ""
            process_started_at = time.monotonic()
            initial_frame_count = self._frames
        self._stderr_thread = threading.Thread(
            target=self._read_stderr,
            args=(process,),
            name="go2-camera-stderr",
            daemon=True,
        )
        self._stderr_thread.start()
        self._watchdog_thread = threading.Thread(
            target=self._watch_process,
            args=(process, process_started_at, initial_frame_count),
            name="go2-camera-watchdog",
            daemon=True,
        )
        self._watchdog_thread.start()

        error = ""
        try:
            if process.stdout is None:
                return "Go2 camera pipeline stdout is unavailable"
            self._read_jpegs(process.stdout)
            returncode = process.poll()
            if returncode not in (None, 0) and not self._stop_event.is_set():
                error = f"Go2 camera pipeline exited with status {returncode}"
        except OSError as exc:
            if not self._stop_event.is_set():
                error = f"Go2 camera pipeline read failed: {exc}"
        finally:
            self._request_process_termination(process)
            self._wait_process_exit(process)
            watchdog_thread = self._watchdog_thread
            if watchdog_thread and watchdog_thread is not threading.current_thread():
                watchdog_thread.join(timeout=2.25)
            stderr_thread = self._stderr_thread
            if stderr_thread and stderr_thread is not threading.current_thread():
                stderr_thread.join(timeout=0.5)
            with self._lock:
                forced_error = (
                    self._process_failure_reason if self._process is process else ""
                )
                if self._process is process:
                    self._process = None
                    self._termination_requested_for = None
                    self._process_failure_reason = ""
                stderr_error = self._last_error
            if forced_error and not self._stop_event.is_set():
                error = forced_error
            elif stderr_error and not self._stop_event.is_set():
                error = f"{error}: {stderr_error}" if error else stderr_error
        return error or "Go2 camera pipeline ended"

    def _read_jpegs(self, stream: object) -> None:
        buffer = bytearray()
        max_buffer = 8 * 1024 * 1024
        while not self._stop_event.is_set():
            chunk = stream.read(65536)  # type: ignore[attr-defined]
            if not chunk:
                break
            buffer.extend(chunk)
            while True:
                start = buffer.find(b"\xff\xd8")
                if start < 0:
                    if len(buffer) > max_buffer:
                        del buffer[:-1]
                    break
                if start:
                    del buffer[:start]
                end = buffer.find(b"\xff\xd9", 2)
                if end < 0:
                    if len(buffer) > max_buffer:
                        buffer.clear()
                    break
                jpeg = bytes(buffer[: end + 2])
                del buffer[: end + 2]
                self._publish_jpeg(jpeg)

    def _publish_jpeg(self, jpeg: bytes) -> None:
        if len(jpeg) < 4 or not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
            return
        try:
            self.on_jpeg(jpeg)
        except Exception as exc:
            with self._lock:
                self._last_error = f"camera JPEG callback failed: {exc}"[-400:]
            return
        # A decoded frame only counts as delivered after the dashboard callback
        # accepts it.  Otherwise a broken callback could keep the receiver
        # falsely LIVE and prevent the no-frame watchdog from recovering it.
        now = time.monotonic()
        with self._lock:
            self._frames += 1
            self._last_frame_at = now
            self._frame_times.append(now)
            self._state = "ok"
            self._last_error = ""

    def _read_stderr(self, process: subprocess.Popen) -> None:
        if process.stderr is None:
            return
        while not self._stop_event.is_set() and process.poll() is None:
            try:
                line = process.stderr.readline()
            except OSError:
                return
            if not line:
                return
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                with self._lock:
                    self._last_error = text[-400:]

    def _watch_process(
        self,
        process: subprocess.Popen,
        started_at: float,
        initial_frame_count: int,
    ) -> None:
        """Restart a live process that never produces, or stops producing, JPEGs."""

        while not self._stop_event.wait(0.2):
            now = time.monotonic()
            with self._lock:
                if self._process is not process or process.poll() is not None:
                    return
                frame_count = self._frames
                last_frame_at = self._last_frame_at
            if frame_count <= initial_frame_count:
                if now - started_at < self.startup_frame_timeout_s:
                    continue
                reason = (
                    "Go2 camera startup frame timeout "
                    f"after {self.startup_frame_timeout_s:.1f}s"
                )
            else:
                if last_frame_at and now - last_frame_at < self.frame_timeout_s:
                    continue
                reason = (
                    "Go2 camera frame stream stalled "
                    f"for {self.frame_timeout_s:.1f}s"
                )
            requested = self._request_process_termination(process, reason=reason)
            if requested:
                # A SIGTERM-resistant gst-launch would otherwise leave the
                # supervisor blocked in stdout.read forever.  The watchdog owns
                # the bounded wait/kill fallback for the signal it initiated.
                self._wait_process_exit(process)
            return

    def _request_process_termination(
        self,
        process: Optional[subprocess.Popen],
        *,
        reason: str = "",
    ) -> bool:
        if process is None:
            return False
        with self._lock:
            if self._process is not process or process.poll() is not None:
                return False
            if reason:
                self._process_failure_reason = reason[-400:]
                self._last_error = self._process_failure_reason
                self._state = "restarting"
            if self._termination_requested_for is process:
                return False
            self._termination_requested_for = process
            try:
                process.terminate()
            except OSError as exc:
                self._last_error = f"Go2 camera terminate failed: {exc}"[-400:]
                return False
            return True

    @staticmethod
    def _wait_process_exit(process: Optional[subprocess.Popen]) -> None:
        if process is None or process.poll() is not None:
            return
        try:
            process.wait(timeout=1.5)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=0.5)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def _fps_locked(self) -> Optional[float]:
        if len(self._frame_times) < 2:
            return None
        elapsed = self._frame_times[-1] - self._frame_times[0]
        if elapsed <= 0:
            return None
        return round((len(self._frame_times) - 1) / elapsed, 2)

    def status(self) -> Dict[str, object]:
        now = time.monotonic()
        with self._lock:
            age = round(now - self._last_frame_at, 3) if self._last_frame_at else None
            state = self._state
            process_running = self._process is not None and self._process.poll() is None
            if (
                self.enabled
                and not self._configuration_error
                and self._last_frame_at
                and state == "ok"
            ):
                state = "ok" if age is not None and age <= self.stale_after_s else "stale"
            return {
                "enabled": self.enabled,
                "configured": self.configured,
                "available": self._gst_executable is not None,
                "state": state,
                "live": state == "ok",
                "source": "go2_multicast",
                "source_label": "Go2 front camera",
                "transport": "udp_multicast_rtp_h264",
                "uri": self.source_uri,
                "multicast_address": GO2_CAMERA_MULTICAST_ADDRESS,
                "port": GO2_CAMERA_MULTICAST_PORT,
                "interface": self.interface,
                "width": self.width,
                "height": self.height,
                "fps_limit": self.fps_limit,
                "startup_frame_timeout_s": self.startup_frame_timeout_s,
                "frame_timeout_s": self.frame_timeout_s,
                "fps": self._fps_locked(),
                "frames": self._frames,
                "age_s": age,
                "process_running": process_running,
                "watchdog_running": bool(
                    self._watchdog_thread and self._watchdog_thread.is_alive()
                ),
                "restart_count": self._restart_count,
                "restart_in_s": self._restart_in_s,
                "last_error": self._last_error,
            }
