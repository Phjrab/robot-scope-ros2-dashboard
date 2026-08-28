#!/usr/bin/env python3
"""Fixed, on-demand RealSense color MJPEG relay for the robot-side Jetson."""

from __future__ import annotations

import glob
import json
import os
import signal
import stat
import subprocess
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional, Sequence


BIND_HOST = "192.168.123.18"
BIND_PORT = 8090
DASHBOARD_HOST = "192.168.123.99"
HEALTH_CLIENTS = frozenset({"127.0.0.1", BIND_HOST, DASHBOARD_HOST})
STREAM_CLIENTS = frozenset({DASHBOARD_HOST})
DEVICE_GLOB = "/dev/v4l/by-path/*-video-index0"
DEVICE_LINK_DIR = Path("/dev/v4l/by-path")
SYSFS_VIDEO_ROOT = Path("/sys/class/video4linux")
REALSENSE_VENDOR_ID = "8086"
REALSENSE_PRODUCT_ID = "0b3a"
REALSENSE_COLOR_INTERFACE = "03"
REALSENSE_VIDEO_INDEX = "0"
WIDTH = 640
HEIGHT = 480
FPS = 15
JPEG_QUALITY = 72
PLUGIN_PROBE_TIMEOUT_S = 15.0
MAX_JPEG_BYTES = 4 * 1024 * 1024
MAX_VIEWERS = 4
MAX_HTTP_CLIENTS = 8
VIEWER_WAIT_S = 2.0
CLIENT_SOCKET_TIMEOUT_S = 10.0
SOURCE_STOP_GRACE_S = 3.0
SOURCE_STARTUP_TIMEOUT_S = 8.0
FRAME_STALE_S = 3.0
BOUNDARY = "robot-scope-frame"
KEEPALIVE_PART = (
    f"--{BOUNDARY}\r\n"
    "Content-Type: text/plain\r\n"
    "Content-Length: 0\r\n\r\n\r\n"
).encode("ascii")


class RelaySetupError(RuntimeError):
    pass


def client_allowed(client_host: str, path: str) -> bool:
    """Keep the sensor feed on the fixed robot-to-dashboard link."""

    if path == "/health":
        return client_host in HEALTH_CLIENTS
    if path == "/stream":
        return client_host in STREAM_CLIENTS
    return True


def _sysfs_text(path: Path) -> str:
    try:
        return path.read_text(encoding="ascii").strip().lower()
    except (OSError, UnicodeError):
        return ""


def _is_realsense_color_node(
    target: Path, sysfs_root: Path = SYSFS_VIDEO_ROOT
) -> bool:
    if target.parent != Path("/dev") or not target.name.startswith("video"):
        return False
    suffix = target.name[len("video") :]
    if not suffix.isdigit():
        return False
    video_root = sysfs_root / target.name
    try:
        interface_root = (video_root / "device").resolve(strict=True)
    except OSError:
        return False
    usb_root = interface_root.parent
    return (
        _sysfs_text(interface_root / "bInterfaceNumber")
        == REALSENSE_COLOR_INTERFACE
        and _sysfs_text(usb_root / "idVendor") == REALSENSE_VENDOR_ID
        and _sysfs_text(usb_root / "idProduct") == REALSENSE_PRODUCT_ID
        and _sysfs_text(video_root / "index") == REALSENSE_VIDEO_INDEX
    )


def resolve_realsense_device(pattern: str = DEVICE_GLOB) -> str:
    """Resolve exactly one sysfs-verified D435i color V4L2 character device."""

    trusted: set[Path] = set()
    for match in sorted(glob.glob(pattern)):
        link = Path(match)
        if not link.is_symlink() or link.parent != DEVICE_LINK_DIR:
            continue
        try:
            target = link.resolve(strict=True)
            mode = target.stat().st_mode
        except OSError:
            continue
        if stat.S_ISCHR(mode) and _is_realsense_color_node(target):
            trusted.add(target)
    if len(trusted) != 1:
        raise RelaySetupError(
            f"expected exactly one verified RealSense color interface, found {len(trusted)}"
        )
    return str(next(iter(trusted)))


def _plugin_available(name: str) -> bool:
    try:
        result = subprocess.run(
            ["/usr/bin/gst-inspect-1.0", name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # A hardened systemd service gets a private /tmp, so GStreamer may
            # need to build its plugin registry on every cold start.  The
            # Jetson Orin Nano needs more than three seconds for that first
            # scan even though the requested encoder is installed.
            timeout=PLUGIN_PROBE_TIMEOUT_S,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def gstreamer_command(device: str) -> tuple[str, ...]:
    # JetPack 5's nvjpegenc can discover successfully yet crash at runtime in
    # a hardened service (NVMAP_IOC_GET_FD / NvRmStream failures).  At the
    # bounded 640x480@15 profile, jpegenc is the reliable default and avoids
    # relaxing the service sandbox.  Keep nvjpegenc only as an installation
    # fallback for images that do not provide the software encoder.
    encoder = "jpegenc" if _plugin_available("jpegenc") else "nvjpegenc"
    if encoder == "nvjpegenc" and not _plugin_available("nvjpegenc"):
        raise RelaySetupError("neither nvjpegenc nor jpegenc is installed")
    return (
        "/usr/bin/gst-launch-1.0",
        "-q",
        "v4l2src",
        f"device={device}",
        "do-timestamp=true",
        "!",
        f"video/x-raw,format=YUY2,width={WIDTH},height={HEIGHT},framerate={FPS}/1",
        "!",
        "videoconvert",
        "!",
        "video/x-raw,format=I420",
        "!",
        encoder,
        f"quality={JPEG_QUALITY}",
        "!",
        "fdsink",
        "fd=1",
        "sync=false",
    )


class FrameHub:
    """Latest-frame broadcaster with one source and bounded viewer count."""

    def __init__(self, producer_factory: Callable[[Callable[[bytes], None]], "GstProducer"]):
        self._producer_factory = producer_factory
        self._condition = threading.Condition()
        self._producer: Optional[GstProducer] = None
        self._stop_timer: Optional[threading.Timer] = None
        self._frame: Optional[bytes] = None
        self._sequence = 0
        self._viewers = 0
        self._frames = 0
        self._bytes = 0
        self._invalid = 0
        self._started_at = time.monotonic()
        self._last_frame_at = 0.0
        self._frame_times: list[float] = []

    def add_viewer(self) -> bool:
        with self._condition:
            if self._viewers >= MAX_VIEWERS:
                return False
            self._viewers += 1
            if self._stop_timer:
                self._stop_timer.cancel()
                self._stop_timer = None
            if self._producer is None:
                self._producer = self._producer_factory(self.publish)
                self._producer.start()
            return True

    def remove_viewer(self) -> None:
        with self._condition:
            self._viewers = max(0, self._viewers - 1)
            if self._viewers == 0 and self._producer is not None:
                timer = threading.Timer(SOURCE_STOP_GRACE_S, self._stop_if_idle)
                timer.daemon = True
                self._stop_timer = timer
                timer.start()

    def _stop_if_idle(self) -> None:
        with self._condition:
            if self._viewers or self._producer is None:
                return
            producer = self._producer
            self._producer = None
            self._stop_timer = None
            self._clear_frame_locked()
        producer.stop()

    def _clear_frame_locked(self) -> None:
        """Remove session-local image state while preserving lifetime counters."""

        self._frame = None
        self._last_frame_at = 0.0
        self._frame_times.clear()

    def publish(self, jpeg: bytes) -> bool:
        if (
            len(jpeg) > MAX_JPEG_BYTES
            or len(jpeg) < 4
            or not jpeg.startswith(b"\xff\xd8")
            or not jpeg.endswith(b"\xff\xd9")
        ):
            with self._condition:
                self._invalid += 1
            return False
        now = time.monotonic()
        with self._condition:
            self._frame = jpeg
            self._sequence += 1
            self._frames += 1
            self._bytes += len(jpeg)
            self._last_frame_at = now
            self._frame_times.append(now)
            self._frame_times = self._frame_times[-120:]
            self._condition.notify_all()
        return True

    def wait_after(self, sequence: int) -> tuple[int, Optional[bytes]]:
        with self._condition:
            self._condition.wait_for(
                lambda: self._sequence > sequence, timeout=VIEWER_WAIT_S
            )
            return self._sequence, self._frame if self._sequence > sequence else None

    def health(self) -> dict[str, object]:
        with self._condition:
            now = time.monotonic()
            fps = 0.0
            if len(self._frame_times) > 1:
                elapsed = self._frame_times[-1] - self._frame_times[0]
                if elapsed > 0:
                    fps = (len(self._frame_times) - 1) / elapsed
            producer = self._producer
            producer_status = producer.status() if producer is not None else {}
            process_running = bool(producer_status.get("process_running", False))
            producer_started_at = float(producer_status.get("process_started_at", 0.0) or 0.0)
            producer_age_s = (
                max(0.0, now - producer_started_at) if producer_started_at else None
            )
            last_frame_age_s = (
                max(0.0, now - self._last_frame_at) if self._last_frame_at else None
            )
            last_error = str(producer_status.get("last_error", ""))

            if producer is None:
                state = "idle"
                process_running = False
                last_error = ""
            elif process_running:
                frame_from_current_process = bool(
                    self._last_frame_at
                    and producer_started_at
                    and self._last_frame_at >= producer_started_at
                )
                if frame_from_current_process:
                    state = (
                        "streaming"
                        if last_frame_age_s is not None
                        and last_frame_age_s <= FRAME_STALE_S
                        else "stale"
                    )
                elif producer_age_s is not None and producer_age_s > SOURCE_STARTUP_TIMEOUT_S:
                    state = "error"
                    last_error = (
                        f"no RealSense JPEG received after {producer_age_s:.1f}s"
                    )
                else:
                    state = "starting"
            elif last_error:
                state = "error"
            elif bool(producer_status.get("thread_running", False)):
                state = "starting"
            else:
                state = "error"
                last_error = "RealSense producer stopped unexpectedly"

            return {
                "status": state,
                "source": "realsense_color",
                "state": state,
                "viewers": self._viewers,
                "max_viewers": MAX_VIEWERS,
                "frames": self._frames,
                "bytes": self._bytes,
                "payload_bytes": self._bytes,
                "fps": round(fps, 2),
                "invalid_frames": self._invalid,
                "process_running": process_running,
                "producer_thread_running": bool(
                    producer_status.get("thread_running", False)
                ),
                "last_error": last_error,
                "last_frame_age_s": (
                    round(last_frame_age_s, 3)
                    if last_frame_age_s is not None
                    else None
                ),
                "uptime_s": round(now - self._started_at, 1),
            }

    def close(self) -> None:
        with self._condition:
            if self._stop_timer:
                self._stop_timer.cancel()
                self._stop_timer = None
            producer, self._producer = self._producer, None
            self._clear_frame_locked()
            self._condition.notify_all()
        if producer:
            producer.stop()


class GstProducer:
    def __init__(self, publish: Callable[[bytes], bool]):
        self._publish = publish
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._thread: Optional[threading.Thread] = None
        self._process_started_at = 0.0
        self._last_error = ""

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="realsense-source", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            error = ""
            try:
                error = self._run_once()
            except (OSError, RelaySetupError, subprocess.SubprocessError) as exc:
                error = str(exc)
            finally:
                with self._lock:
                    self._process = None
                    self._process_started_at = 0.0
                    if error and not self._stop.is_set():
                        self._last_error = error[-400:]
            if error and not self._stop.is_set():
                print(f"[Robot Scope RealSense] source error: {error}", file=os.sys.stderr)
            if self._stop.wait(1.0):
                break

    def _run_once(self) -> str:
        device = resolve_realsense_device()
        process = subprocess.Popen(
            list(gstreamer_command(device)),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            close_fds=True,
            shell=False,
        )
        with self._lock:
            self._process = process
            self._process_started_at = time.monotonic()
            self._last_error = ""
        if self._stop.is_set():
            self._terminate_process(process)
            return ""
        assert process.stdout is not None
        buffer = bytearray()
        while not self._stop.is_set():
            chunk = os.read(process.stdout.fileno(), 64 * 1024)
            if not chunk:
                break
            buffer.extend(chunk)
            while True:
                start = buffer.find(b"\xff\xd8")
                if start < 0:
                    del buffer[:-1]
                    break
                if start:
                    del buffer[:start]
                end = buffer.find(b"\xff\xd9", 2)
                if end < 0:
                    if len(buffer) > MAX_JPEG_BYTES:
                        del buffer[:2]
                    break
                frame = bytes(buffer[: end + 2])
                del buffer[: end + 2]
                self._publish(frame)
        if self._stop.is_set():
            return ""
        returncode = process.poll()
        if returncode is None:
            self._terminate_process(process)
            return "RealSense GStreamer stdout closed while the process was running"
        if returncode == 0:
            return "RealSense GStreamer stream ended unexpectedly"
        return f"RealSense GStreamer exited with status {returncode}"

    @staticmethod
    def _terminate_process(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=2.0)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def status(self) -> dict[str, object]:
        with self._lock:
            process = self._process
            return {
                "process_running": bool(
                    process is not None and process.poll() is None
                ),
                "process_started_at": self._process_started_at,
                "thread_running": bool(self._thread and self._thread.is_alive()),
                "last_error": self._last_error,
            }

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            process = self._process
        if process:
            self._terminate_process(process)
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=3.0)


class RelayServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    request_queue_size = MAX_HTTP_CLIENTS

    def __init__(self, hub: FrameHub):
        self.hub = hub
        self._client_slots = threading.BoundedSemaphore(MAX_HTTP_CLIENTS)
        super().__init__((BIND_HOST, BIND_PORT), RelayHandler)

    def process_request(self, request: object, client_address: object) -> None:
        if not self._client_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request: object, client_address: object) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._client_slots.release()


class RelayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "RobotScopeRealSense/1"
    sys_version = ""

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(CLIENT_SOCKET_TIMEOUT_S)

    def do_GET(self) -> None:
        if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length", "0") != "0":
            self.send_error(HTTPStatus.BAD_REQUEST, "request body is not accepted")
            return
        if not client_allowed(str(self.client_address[0]), self.path):
            self.send_error(HTTPStatus.FORBIDDEN, "client is not allowlisted")
            return
        if self.path == "/health":
            self._health()
        elif self.path == "/stream":
            self._stream()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_HEAD(self) -> None:
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    def _health(self) -> None:
        payload = json.dumps(self.server.hub.health(), separators=(",", ":")).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)

    def _stream(self) -> None:
        hub = self.server.hub
        if not hub.add_viewer():
            self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "viewer limit reached")
            return
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Connection", "close")
            self.end_headers()
            sequence = 0
            while True:
                sequence, jpeg = hub.wait_after(sequence)
                if jpeg is None:
                    # A producer can fail before its first JPEG.  Periodic
                    # multipart keepalives exercise the socket so a dashboard
                    # that has disconnected cannot occupy a viewer slot
                    # forever.  The fixed dashboard parser ignores non-JPEG
                    # parts and continues waiting for the next image.
                    self.wfile.write(KEEPALIVE_PART)
                    self.wfile.flush()
                    continue
                header = (
                    f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\n"
                    f"Content-Length: {len(jpeg)}\r\n\r\n"
                ).encode("ascii")
                self.wfile.write(header + jpeg + b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionError, OSError):
            pass
        finally:
            hub.remove_viewer()

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[Robot Scope RealSense] {self.client_address[0]} {fmt % args}")


def main(argv: Sequence[str] = ()) -> int:
    if argv:
        print("realsense_mjpeg_relay.py accepts no arguments", file=os.sys.stderr)
        return 2
    # Fail before binding so a missing/ambiguous USB camera is explicit.
    device = resolve_realsense_device()
    gstreamer_command(device)
    hub = FrameHub(GstProducer)
    server = RelayServer(hub)
    stopping = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        if not stopping.is_set():
            stopping.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        print(f"[Robot Scope RealSense] listening on http://{BIND_HOST}:{BIND_PORT}")
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        hub.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(os.sys.argv[1:]))
