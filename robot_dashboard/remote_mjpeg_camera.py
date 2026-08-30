"""On-demand, bounded receiver for a profile-allowlisted remote MJPEG feed."""

from __future__ import annotations

import http.client
import ipaddress
import socket
import threading
import time
from collections import deque
from typing import BinaryIO, Callable, Dict, Optional, Sequence
from urllib.parse import urlsplit


MAX_JPEG_BYTES = 4 * 1024 * 1024
MAX_JPEG_HEADER_BYTES = 128 * 1024
MAX_JPEG_DIMENSION = 8192
MAX_JPEG_PIXELS = 32 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
REALSENSE_RELAY_HOST = "192.168.123.18"
REALSENSE_RELAY_PORT = 8090
REALSENSE_RELAY_PORT_ENV = "ROBOT_SCOPE_REALSENSE_PORT"
MIN_REALSENSE_RELAY_PORT = 1024
MAX_REALSENSE_RELAY_PORT = 65535
JPEG_SOF_MARKERS = frozenset(
    {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
)


def allowed_realsense_relay_host(value: str) -> bool:
    """Allow only an explicit RFC1918 or link-local IPv4 relay endpoint."""

    try:
        address = ipaddress.ip_address(str(value or "").strip())
    except ValueError:
        return False
    allowed_networks = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("169.254.0.0/16"),
    )
    return (
        isinstance(address, ipaddress.IPv4Address)
        and any(address in network for network in allowed_networks)
        and not address.is_unspecified
        and not address.is_loopback
        and not address.is_multicast
        and int(str(address).rsplit(".", 1)[1]) not in {0, 255}
    )


def allowed_realsense_relay_port(value: object) -> bool:
    text = str(value or "").strip()
    if not text.isascii() or not text.isdecimal():
        return False
    return MIN_REALSENSE_RELAY_PORT <= int(text, 10) <= MAX_REALSENSE_RELAY_PORT


def _jpeg_dimensions(jpeg: bytes) -> Optional[tuple[int, int]]:
    """Return bounded JPEG SOF dimensions without decoding image content."""

    if len(jpeg) < 4 or not jpeg.startswith(b"\xff\xd8"):
        return None
    limit = min(len(jpeg), MAX_JPEG_HEADER_BYTES)
    offset = 2
    while offset < limit:
        if jpeg[offset] != 0xFF:
            return None
        while offset < limit and jpeg[offset] == 0xFF:
            offset += 1
        if offset >= limit:
            return None
        marker = jpeg[offset]
        offset += 1
        if marker in {0x00, 0xD8}:
            return None
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker in {0xD9, 0xDA} or offset + 2 > limit:
            return None
        segment_length = int.from_bytes(jpeg[offset : offset + 2], "big")
        if segment_length < 2:
            return None
        segment_end = offset + segment_length
        if segment_end > limit or segment_end > len(jpeg):
            return None
        if marker in JPEG_SOF_MARKERS:
            if segment_length < 8:
                return None
            height = int.from_bytes(jpeg[offset + 3 : offset + 5], "big")
            width = int.from_bytes(jpeg[offset + 5 : offset + 7], "big")
            if (
                width < 1
                or height < 1
                or width > MAX_JPEG_DIMENSION
                or height > MAX_JPEG_DIMENSION
                or width * height > MAX_JPEG_PIXELS
            ):
                return None
            return width, height
        offset = segment_end
    return None


class RemoteMjpegCamera:
    """Receive one fixed HTTP MJPEG source without exposing an HTTP proxy.

    The URL is read only from the trusted robot profile and must be an exact
    member of ``allowed_urls``.  Browser input selects a fixed source id in
    :class:`RosAgent`; it can never provide or modify this URL.
    """

    def __init__(
        self,
        on_jpeg: Callable[[bytes], None],
        *,
        enabled: bool,
        url: str,
        allowed_urls: Sequence[str],
        relay_host: str = REALSENSE_RELAY_HOST,
        source_id: str = "realsense_color",
        source_label: str = "RealSense color camera",
        stale_after_s: float = 3.0,
        request_timeout_s: float = 6.0,
        restart_initial_s: float = 0.5,
        restart_max_s: float = 8.0,
    ) -> None:
        self.on_jpeg = on_jpeg
        self.enabled = bool(enabled)
        self.url = str(url or "").strip()
        self.allowed_urls = tuple(
            dict.fromkeys(str(value).strip() for value in allowed_urls if str(value).strip())
        )
        self.relay_host = str(relay_host or "").strip()
        self.source_id = str(source_id)
        self.source_label = str(source_label)
        self.stale_after_s = max(0.5, min(float(stale_after_s), 15.0))
        self.request_timeout_s = max(1.0, min(float(request_timeout_s), 30.0))
        self.restart_initial_s = max(0.1, min(float(restart_initial_s), 5.0))
        self.restart_max_s = max(
            self.restart_initial_s,
            min(float(restart_max_s), 30.0),
        )

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._connection: Optional[http.client.HTTPConnection] = None
        self._response: Optional[BinaryIO] = None
        self._state = "disabled" if not self.enabled else "waiting"
        self._last_error = ""
        self._last_frame_at = 0.0
        self._frames = 0
        self._width = 0
        self._height = 0
        self._oversize_frames = 0
        self._invalid_frames = 0
        self._restart_count = 0
        self._restart_in_s: Optional[float] = None
        self._frame_times: deque[float] = deque(maxlen=120)
        self._configuration_error = self._validate_configuration()
        if self._configuration_error:
            self._state = "error"
            self._last_error = self._configuration_error

    def _validate_configuration(self) -> str:
        if not self.enabled:
            return ""
        if self.source_id != "realsense_color":
            return "remote MJPEG camera source id is not allowlisted"
        if not allowed_realsense_relay_host(self.relay_host):
            return "remote MJPEG camera relay host is not allowlisted"
        if not self.url or self.url not in self.allowed_urls:
            return "remote MJPEG camera URL is not allowlisted"
        try:
            parsed = urlsplit(self.url)
            port = parsed.port
        except ValueError:
            return "remote MJPEG camera URL is invalid"
        if parsed.scheme != "http":
            return "remote MJPEG camera URL must use http"
        if not parsed.hostname or parsed.username or parsed.password:
            return "remote MJPEG camera URL authority is invalid"
        if parsed.hostname != self.relay_host:
            return "remote MJPEG camera host is not allowlisted"
        if port is None or not allowed_realsense_relay_port(port):
            return "remote MJPEG camera URL requires an allowlisted explicit port"
        if parsed.path != "/stream" or parsed.query or parsed.fragment:
            return "remote MJPEG camera URL must use the fixed /stream path"
        return ""

    @property
    def configured(self) -> bool:
        return self.enabled and not self._configuration_error

    def start(self) -> bool:
        with self._lock:
            if not self.configured:
                return False
            if self._thread and self._thread.is_alive():
                return True
            self._stop_event.clear()
            self._state = "starting"
            self._restart_in_s = None
            self._width = 0
            self._height = 0
            self._thread = threading.Thread(
                target=self._supervise,
                name="realsense-mjpeg-camera",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            connection = self._connection
            response = self._response
        if response is not None:
            try:
                response.close()
            except OSError:
                pass
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=self.request_timeout_s + 1.0)
        with self._lock:
            self._connection = None
            self._response = None
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
                self._last_error = error[-400:]
            if self._stop_event.wait(delay):
                break
            delay = self.restart_initial_s if delivered else min(delay * 2.0, self.restart_max_s)
        with self._lock:
            self._connection = None
            self._response = None
            self._restart_in_s = None
            if not self._configuration_error:
                self._state = "stopped"

    def _run_once(self) -> str:
        parsed = urlsplit(self.url)
        connection = http.client.HTTPConnection(
            parsed.hostname,
            parsed.port,
            timeout=self.request_timeout_s,
        )
        with self._lock:
            self._connection = connection
        try:
            connection.request(
                "GET",
                "/stream",
                headers={
                    "Accept": "multipart/x-mixed-replace",
                    "Connection": "close",
                    "Host": f"{self.relay_host}:{parsed.port}",
                    "User-Agent": "Robot-Scope/0.2",
                },
            )
            response = connection.getresponse()
        except (OSError, http.client.HTTPException) as exc:
            connection.close()
            with self._lock:
                if self._connection is connection:
                    self._connection = None
            return f"remote MJPEG connection failed: {exc}"

        try:
            if response.status != 200:
                return f"remote camera returned HTTP {response.status}"
            content_type = str(response.headers.get("Content-Type", "")).lower()
            media_type = content_type.split(";", 1)[0].strip()
            if media_type != "multipart/x-mixed-replace":
                return "remote camera response is not multipart MJPEG"
            with self._lock:
                self._response = response
                self._state = "waiting"
                self._last_error = ""
            self._read_jpegs(response)
            return "remote MJPEG stream ended"
        except (OSError, socket.timeout, TimeoutError) as exc:
            if self._stop_event.is_set():
                return "remote MJPEG receiver stopped"
            return f"remote MJPEG read failed: {exc}"
        finally:
            try:
                response.close()
            except OSError:
                pass
            connection.close()
            with self._lock:
                if self._connection is connection:
                    self._connection = None
                if self._response is response:
                    self._response = None

    def _read_jpegs(self, stream: BinaryIO) -> None:
        """Extract complete JPEG frames while keeping memory strictly bounded."""

        buffer = bytearray()
        read_chunk = getattr(stream, "read1", stream.read)
        while not self._stop_event.is_set():
            # ``HTTPResponse.read(size)`` may wait for all ``size`` bytes;
            # ``read1`` returns the next socket-buffered part immediately and
            # avoids adding visible latency to small 15 fps JPEG frames.
            chunk = read_chunk(READ_CHUNK_BYTES)
            if not chunk:
                break
            buffer.extend(chunk)
            while True:
                start = buffer.find(b"\xff\xd8")
                if start < 0:
                    if len(buffer) > 1:
                        del buffer[:-1]
                    break
                if start:
                    del buffer[:start]
                end = buffer.find(b"\xff\xd9", 2)
                if end < 0:
                    if len(buffer) > MAX_JPEG_BYTES:
                        with self._lock:
                            self._oversize_frames += 1
                        # Discard this SOI and search the remaining bytes for a
                        # later frame instead of growing the buffer indefinitely.
                        del buffer[:2]
                        continue
                    break
                frame_size = end + 2
                jpeg = bytes(buffer[:frame_size])
                del buffer[:frame_size]
                if frame_size > MAX_JPEG_BYTES:
                    with self._lock:
                        self._oversize_frames += 1
                    continue
                self._publish_jpeg(jpeg)

    def _publish_jpeg(self, jpeg: bytes) -> None:
        if (
            not 4 <= len(jpeg) <= MAX_JPEG_BYTES
            or not jpeg.startswith(b"\xff\xd8")
            or not jpeg.endswith(b"\xff\xd9")
        ):
            with self._lock:
                self._invalid_frames += 1
            return
        dimensions = _jpeg_dimensions(jpeg)
        try:
            self.on_jpeg(jpeg)
        except Exception as exc:
            with self._lock:
                self._last_error = f"remote camera JPEG callback failed: {exc}"[-400:]
            return
        now = time.monotonic()
        with self._lock:
            self._frames += 1
            self._width, self._height = dimensions or (0, 0)
            self._last_frame_at = now
            self._frame_times.append(now)
            self._state = "ok"
            self._last_error = ""

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
            if self.configured and self._last_frame_at and state == "ok":
                state = "ok" if age is not None and age <= self.stale_after_s else "stale"
            return {
                "enabled": self.enabled,
                "configured": self.configured,
                "available": self.configured,
                "state": state,
                "live": state == "ok",
                "source": "remote_mjpeg",
                "source_id": self.source_id,
                "source_label": self.source_label,
                "transport": "http_mjpeg",
                "uri": self.url,
                "format": "jpeg",
                "max_frame_bytes": MAX_JPEG_BYTES,
                "width": self._width,
                "height": self._height,
                "fps": self._fps_locked(),
                "frames": self._frames,
                "age_s": age,
                "process_running": bool(self._thread and self._thread.is_alive()),
                "restart_count": self._restart_count,
                "restart_in_s": self._restart_in_s,
                "oversize_frames": self._oversize_frames,
                "invalid_frames": self._invalid_frames,
                "last_error": self._last_error,
            }
