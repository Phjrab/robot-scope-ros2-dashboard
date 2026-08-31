#!/usr/bin/env python3
"""Fixed, on-demand RealSense color MJPEG relay for the robot-side Jetson."""

from __future__ import annotations

import glob
import ipaddress
import json
import os
import re
import signal
import socket
import stat
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence


class RelaySetupError(RuntimeError):
    """Bounded startup/runtime error suitable for service logs and health."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


DEFAULT_BIND_HOST = "192.168.123.18"
DEFAULT_DASHBOARD_HOST = "192.168.123.99"
DEFAULT_BIND_PORT = 8090
DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480
DEFAULT_FPS = 15
DEFAULT_JPEG_QUALITY = 72
RELAY_BIND_HOST_ENV = "ROBOT_SCOPE_REALSENSE_BIND_HOST"
RELAY_DASHBOARD_HOST_ENV = "ROBOT_SCOPE_REALSENSE_DASHBOARD_HOST"
RELAY_PORT_ENV = "ROBOT_SCOPE_REALSENSE_PORT"
RELAY_WIDTH_ENV = "ROBOT_SCOPE_REALSENSE_WIDTH"
RELAY_HEIGHT_ENV = "ROBOT_SCOPE_REALSENSE_HEIGHT"
RELAY_FPS_ENV = "ROBOT_SCOPE_REALSENSE_FPS"
RELAY_JPEG_QUALITY_ENV = "ROBOT_SCOPE_REALSENSE_JPEG_QUALITY"
RELAY_WIFI_INTERFACE_ENV = "ROBOT_SCOPE_REALSENSE_WIFI_INTERFACE"
PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
)
ALLOWED_CAPTURE_RESOLUTIONS = frozenset({(320, 240), (640, 480), (1280, 720)})
ALLOWED_CAPTURE_FPS = frozenset({5, 10, 15, 30})
MIN_BIND_PORT = 1024
MAX_BIND_PORT = 65535
MIN_JPEG_QUALITY = 40
MAX_JPEG_QUALITY = 90
METRIC_WINDOW_S = 5.0
MAX_METRIC_SAMPLES = 120
WIFI_PROBE_TIMEOUT_S = 1.0
MAX_WIFI_PROBE_OUTPUT_BYTES = 4096
WIFI_INTERFACE_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,32}\Z")
IW_EXECUTABLES = ("/usr/sbin/iw", "/usr/bin/iw")


@dataclass(frozen=True)
class RelayConfig:
    bind_host: str
    dashboard_host: str
    port: int
    width: int
    height: int
    fps: int
    jpeg_quality: int
    wifi_interface: str = ""


def _local_link_ipv4(value: str, label: str, error_code: str) -> ipaddress.IPv4Address:
    """Return one explicit RFC1918/link-local IPv4 or fail closed."""

    text = str(value or "").strip()
    try:
        address = ipaddress.ip_address(text)
    except ValueError as exc:
        raise RelaySetupError(
            error_code, f"{label} must be a valid IPv4 address"
        ) from exc
    if not isinstance(address, ipaddress.IPv4Address) or not any(
        address in network for network in PRIVATE_NETWORKS
    ):
        raise RelaySetupError(
            error_code, f"{label} must be a private or link-local IPv4 address"
        )
    if (
        address.is_unspecified
        or address.is_loopback
        or address.is_multicast
        or address == ipaddress.ip_address("255.255.255.255")
    ):
        raise RelaySetupError(error_code, f"{label} is not an allowed relay address")
    return address


def _bounded_integer(
    value: object,
    label: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    text = str(value or "").strip()
    if not text.isascii() or not text.isdecimal():
        raise RelaySetupError("INVALID_CONFIG", f"{label} must be a decimal integer")
    parsed = int(text, 10)
    if not minimum <= parsed <= maximum:
        raise RelaySetupError(
            "INVALID_CONFIG", f"{label} is outside the allowed range"
        )
    return parsed


def _local_bind_available(bind_host: str) -> bool:
    """Prove that the kernel currently owns the exact configured IPv4."""

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((bind_host, 0))
    except OSError:
        return False
    finally:
        probe.close()
    return True


def relay_configuration(
    environ: Optional[Mapping[str, str]] = None,
    *,
    validate_local_bind: bool = False,
    local_bind_check: Optional[Callable[[str], bool]] = None,
) -> RelayConfig:
    """Load one bounded relay contract without a wildcard or silent fallback."""

    values = os.environ if environ is None else environ
    bind_address = _local_link_ipv4(
        values.get(RELAY_BIND_HOST_ENV, DEFAULT_BIND_HOST),
        RELAY_BIND_HOST_ENV,
        "INVALID_CONFIG",
    )
    dashboard_address = _local_link_ipv4(
        values.get(RELAY_DASHBOARD_HOST_ENV, DEFAULT_DASHBOARD_HOST),
        RELAY_DASHBOARD_HOST_ENV,
        "DASHBOARD_ADDRESS_REJECTED",
    )
    pair_network = ipaddress.ip_network(f"{bind_address}/24", strict=False)
    if bind_address in {pair_network.network_address, pair_network.broadcast_address}:
        raise RelaySetupError(
            "INVALID_CONFIG", f"{RELAY_BIND_HOST_ENV} is a /24 network or broadcast address"
        )
    if dashboard_address not in pair_network or dashboard_address in {
        pair_network.network_address,
        pair_network.broadcast_address,
    }:
        raise RelaySetupError(
            "DASHBOARD_ADDRESS_REJECTED",
            f"{RELAY_DASHBOARD_HOST_ENV} must be a usable host in the bind address /24",
        )
    if dashboard_address == bind_address:
        raise RelaySetupError(
            "DASHBOARD_ADDRESS_REJECTED",
            f"{RELAY_DASHBOARD_HOST_ENV} must differ from the relay bind address",
        )

    port = _bounded_integer(
        values.get(RELAY_PORT_ENV, str(DEFAULT_BIND_PORT)),
        RELAY_PORT_ENV,
        minimum=MIN_BIND_PORT,
        maximum=MAX_BIND_PORT,
    )
    width = _bounded_integer(
        values.get(RELAY_WIDTH_ENV, str(DEFAULT_WIDTH)),
        RELAY_WIDTH_ENV,
        minimum=min(item[0] for item in ALLOWED_CAPTURE_RESOLUTIONS),
        maximum=max(item[0] for item in ALLOWED_CAPTURE_RESOLUTIONS),
    )
    height = _bounded_integer(
        values.get(RELAY_HEIGHT_ENV, str(DEFAULT_HEIGHT)),
        RELAY_HEIGHT_ENV,
        minimum=min(item[1] for item in ALLOWED_CAPTURE_RESOLUTIONS),
        maximum=max(item[1] for item in ALLOWED_CAPTURE_RESOLUTIONS),
    )
    if (width, height) not in ALLOWED_CAPTURE_RESOLUTIONS:
        raise RelaySetupError(
            "INVALID_CONFIG", "RealSense width and height are not an allowlisted profile"
        )
    fps = _bounded_integer(
        values.get(RELAY_FPS_ENV, str(DEFAULT_FPS)),
        RELAY_FPS_ENV,
        minimum=min(ALLOWED_CAPTURE_FPS),
        maximum=max(ALLOWED_CAPTURE_FPS),
    )
    if fps not in ALLOWED_CAPTURE_FPS:
        raise RelaySetupError("INVALID_CONFIG", "RealSense FPS is not allowlisted")
    jpeg_quality = _bounded_integer(
        values.get(RELAY_JPEG_QUALITY_ENV, str(DEFAULT_JPEG_QUALITY)),
        RELAY_JPEG_QUALITY_ENV,
        minimum=MIN_JPEG_QUALITY,
        maximum=MAX_JPEG_QUALITY,
    )
    wifi_interface = str(values.get(RELAY_WIFI_INTERFACE_ENV, "") or "").strip()
    if wifi_interface and not WIFI_INTERFACE_PATTERN.fullmatch(wifi_interface):
        raise RelaySetupError(
            "INVALID_CONFIG",
            f"{RELAY_WIFI_INTERFACE_ENV} is not a valid interface name",
        )

    bind_host = str(bind_address)
    if validate_local_bind:
        checker = local_bind_check or _local_bind_available
        if not checker(bind_host):
            raise RelaySetupError(
                "BIND_ADDRESS_MISSING",
                f"{RELAY_BIND_HOST_ENV} is not assigned to a local interface",
            )
    return RelayConfig(
        bind_host=bind_host,
        dashboard_host=str(dashboard_address),
        port=port,
        width=width,
        height=height,
        fps=fps,
        jpeg_quality=jpeg_quality,
        wifi_interface=wifi_interface,
    )


def relay_network_hosts(
    environ: Optional[dict[str, str]] = None,
) -> tuple[str, str]:
    config = relay_configuration(environ)
    return config.bind_host, config.dashboard_host


REFERENCE_CONFIG = relay_configuration({})
BIND_HOST = REFERENCE_CONFIG.bind_host
BIND_PORT = REFERENCE_CONFIG.port
DASHBOARD_HOST = REFERENCE_CONFIG.dashboard_host
HEALTH_CLIENTS = frozenset({"127.0.0.1", BIND_HOST, DASHBOARD_HOST})
STREAM_CLIENTS = frozenset({DASHBOARD_HOST})
DEVICE_GLOB = "/dev/v4l/by-path/*-video-index0"
DEVICE_LINK_DIR = Path("/dev/v4l/by-path")
SYSFS_VIDEO_ROOT = Path("/sys/class/video4linux")
REALSENSE_VENDOR_ID = "8086"
REALSENSE_PRODUCT_ID = "0b3a"
REALSENSE_COLOR_INTERFACE = "03"
REALSENSE_VIDEO_INDEX = "0"
WIDTH = REFERENCE_CONFIG.width
HEIGHT = REFERENCE_CONFIG.height
FPS = REFERENCE_CONFIG.fps
JPEG_QUALITY = REFERENCE_CONFIG.jpeg_quality
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


class WifiLinkProbe:
    """Optional, cached and bounded read-only Wi-Fi link probe."""

    def __init__(self, interface: str, *, cache_s: float = 2.0):
        self.interface = str(interface or "")
        self.cache_s = max(0.5, min(float(cache_s), 10.0))
        self._lock = threading.Lock()
        self._last_probe_at = 0.0
        self._cached: dict[str, object] = self._unverified("interface not configured")

    def _unverified(self, reason: str) -> dict[str, object]:
        return {
            "state": "UNVERIFIED",
            "interface": self.interface,
            "rssi_dbm": None,
            "link_mbps": None,
            "reason": reason[:120],
        }

    @staticmethod
    def _parse(output: str, interface: str) -> dict[str, object]:
        if "Not connected." in output:
            return {
                "state": "OFFLINE",
                "interface": interface,
                "rssi_dbm": None,
                "link_mbps": None,
                "reason": "not connected",
            }
        signal_match = re.search(r"^\s*signal:\s*(-?\d+)\s+dBm\s*$", output, re.MULTILINE)
        bitrate_match = re.search(
            r"^\s*tx bitrate:\s*([0-9]+(?:\.[0-9]+)?)\s+MBit/s(?:\s|$)",
            output,
            re.MULTILINE,
        )
        rssi = int(signal_match.group(1)) if signal_match else None
        link = float(bitrate_match.group(1)) if bitrate_match else None
        if rssi is None and link is None:
            return {
                "state": "UNVERIFIED",
                "interface": interface,
                "rssi_dbm": None,
                "link_mbps": None,
                "reason": "link metrics unavailable",
            }
        return {
            "state": "LIVE",
            "interface": interface,
            "rssi_dbm": rssi,
            "link_mbps": link,
            "reason": "",
        }

    def status(self) -> dict[str, object]:
        if not self.interface:
            return dict(self._cached)
        now = time.monotonic()
        with self._lock:
            if self._last_probe_at and now - self._last_probe_at < self.cache_s:
                return dict(self._cached)
            executable = next(
                (path for path in IW_EXECUTABLES if os.path.isfile(path) and os.access(path, os.X_OK)),
                "",
            )
            if not executable:
                result = self._unverified("iw executable unavailable")
            else:
                try:
                    completed = subprocess.run(
                        [executable, "dev", self.interface, "link"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        timeout=WIFI_PROBE_TIMEOUT_S,
                        check=False,
                        shell=False,
                    )
                    bounded = completed.stdout[:MAX_WIFI_PROBE_OUTPUT_BYTES].decode(
                        "utf-8", errors="replace"
                    )
                    result = (
                        self._parse(bounded, self.interface)
                        if completed.returncode == 0
                        else self._unverified("iw link probe failed")
                    )
                except subprocess.TimeoutExpired:
                    result = self._unverified("iw link probe timed out")
                except OSError:
                    result = self._unverified("iw link probe unavailable")
            self._last_probe_at = now
            self._cached = result
            return dict(result)


def client_allowed(
    client_host: str, path: str, config: RelayConfig = REFERENCE_CONFIG
) -> bool:
    """Keep the sensor feed on the fixed robot-to-dashboard link."""

    if path == "/health":
        return client_host in {"127.0.0.1", config.bind_host, config.dashboard_host}
    if path == "/stream":
        # The robot-side shadow runtime may consume the same producer through
        # the host's exact configured address.  No subnet or wildcard client
        # is admitted and the dashboard remains the only remote viewer.
        return client_host in {config.bind_host, config.dashboard_host}
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
            "DEVICE_NOT_FOUND",
            f"expected exactly one verified RealSense color interface, found {len(trusted)}",
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


def gstreamer_command(
    device: str, config: RelayConfig = REFERENCE_CONFIG
) -> tuple[str, ...]:
    # JetPack 5's nvjpegenc can discover successfully yet crash at runtime in
    # a hardened service (NVMAP_IOC_GET_FD / NvRmStream failures).  At the
    # bounded 640x480@15 profile, jpegenc is the reliable default and avoids
    # relaxing the service sandbox.  Keep nvjpegenc only as an installation
    # fallback for images that do not provide the software encoder.
    encoder = "jpegenc" if _plugin_available("jpegenc") else "nvjpegenc"
    if encoder == "nvjpegenc" and not _plugin_available("nvjpegenc"):
        raise RelaySetupError(
            "ENCODER_UNAVAILABLE", "neither nvjpegenc nor jpegenc is installed"
        )
    return (
        "/usr/bin/gst-launch-1.0",
        "-q",
        "v4l2src",
        f"device={device}",
        "do-timestamp=true",
        "!",
        (
            "video/x-raw,format=YUY2,"
            f"width={config.width},height={config.height},framerate={config.fps}/1"
        ),
        "!",
        "videoconvert",
        "!",
        "video/x-raw,format=I420",
        "!",
        encoder,
        f"quality={config.jpeg_quality}",
        "!",
        "fdsink",
        "fd=1",
        "sync=false",
    )


class FrameHub:
    """Latest-frame broadcaster with one source and bounded viewer count."""

    def __init__(
        self,
        producer_factory: Callable[[Callable[[bytes], None]], "GstProducer"],
        config: RelayConfig = REFERENCE_CONFIG,
        wifi_probe: Optional[WifiLinkProbe] = None,
    ):
        self._producer_factory = producer_factory
        self._config = config
        self._wifi_probe = wifi_probe or WifiLinkProbe(config.wifi_interface)
        self._condition = threading.Condition()
        self._producer: Optional[GstProducer] = None
        self._producer_generation = 0
        self._stop_timer: Optional[threading.Timer] = None
        self._frame: Optional[bytes] = None
        self._sequence = 0
        self._viewers = 0
        self._frames = 0
        self._bytes = 0
        self._invalid = 0
        self._source_epoch = time.monotonic_ns()
        self._started_at = time.monotonic()
        self._last_frame_at = 0.0
        self._capture_monotonic_ns = 0
        self._frame_samples: deque[tuple[float, int]] = deque(
            maxlen=MAX_METRIC_SAMPLES
        )

    def add_viewer(self) -> bool:
        with self._condition:
            if self._viewers >= MAX_VIEWERS:
                return False
            self._viewers += 1
            if self._stop_timer:
                self._stop_timer.cancel()
                self._stop_timer = None
            if self._producer is None:
                self._producer_generation += 1
                generation = self._producer_generation
                self._producer = self._producer_factory(
                    lambda jpeg: self.publish(jpeg, generation=generation)
                )
                self._producer.start()
            return True

    @property
    def source_epoch(self) -> int:
        return self._source_epoch

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
            self._producer_generation += 1
            self._stop_timer = None
        producer.stop()
        with self._condition:
            # GstProducer may deliver one final frame while stop() joins its
            # native process. Its invalidated callback is rejected above, and
            # a concurrently started replacement producer keeps its own frame.
            if self._producer is None and self._viewers == 0:
                self._clear_frame_locked()

    def _clear_frame_locked(self) -> None:
        """Remove session-local image state while preserving lifetime counters."""

        self._frame = None
        self._last_frame_at = 0.0
        self._capture_monotonic_ns = 0
        self._frame_samples.clear()

    def publish(
        self,
        jpeg: bytes,
        *,
        generation: Optional[int] = None,
        capture_monotonic_ns: Optional[int] = None,
    ) -> bool:
        with self._condition:
            if generation is not None and generation != self._producer_generation:
                return False
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
        capture_ns = capture_monotonic_ns or time.monotonic_ns()
        if capture_ns <= 0:
            with self._condition:
                self._invalid += 1
            return False
        with self._condition:
            if generation is not None and generation != self._producer_generation:
                return False
            self._frame = jpeg
            self._sequence += 1
            self._frames += 1
            self._bytes += len(jpeg)
            self._last_frame_at = now
            self._capture_monotonic_ns = capture_ns
            self._frame_samples.append((now, len(jpeg)))
            self._condition.notify_all()
        return True

    def _recent_metrics_locked(self, now: float) -> tuple[float, float]:
        while self._frame_samples and now - self._frame_samples[0][0] > METRIC_WINDOW_S:
            self._frame_samples.popleft()
        if not self._frame_samples:
            return 0.0, 0.0
        elapsed = max(1.0, min(METRIC_WINDOW_S, now - self._frame_samples[0][0]))
        fps = len(self._frame_samples) / elapsed
        bitrate_mbps = (
            sum(size for _stamp, size in self._frame_samples)
            * 8
            / elapsed
            / 1_000_000
        )
        return fps, bitrate_mbps

    def wait_after(self, sequence: int) -> tuple[int, Optional[bytes]]:
        packet_sequence, frame, _capture_ns = self.wait_packet_after(sequence)
        return packet_sequence, frame

    def wait_packet_after(
        self, sequence: int
    ) -> tuple[int, Optional[bytes], Optional[int]]:
        with self._condition:
            self._condition.wait_for(
                lambda: self._sequence > sequence, timeout=VIEWER_WAIT_S
            )
            if self._sequence > sequence:
                return self._sequence, self._frame, self._capture_monotonic_ns
            return self._sequence, None, None

    def health(self) -> dict[str, object]:
        with self._condition:
            now = time.monotonic()
            fps, bitrate_mbps = self._recent_metrics_locked(now)
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
                        "SOURCE_STALE: no RealSense JPEG received after "
                        f"{producer_age_s:.1f}s"
                    )
                else:
                    state = "starting"
            elif last_error:
                state = "error"
            elif bool(producer_status.get("thread_running", False)):
                state = "starting"
            else:
                state = "error"
                last_error = "SOURCE_STALE: RealSense producer stopped unexpectedly"

            payload: dict[str, object] = {
                "status": state,
                "source": "realsense_color",
                "state": state,
                "viewers": self._viewers,
                "max_viewers": MAX_VIEWERS,
                "frames": self._frames,
                "bytes": self._bytes,
                "payload_bytes": self._bytes,
                "fps": round(fps, 2),
                "payload_bitrate_mbps": round(bitrate_mbps, 3),
                "metric_window_s": METRIC_WINDOW_S,
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
                "producer_generation": self._producer_generation,
                "profile": {
                    "width": self._config.width,
                    "height": self._config.height,
                    "fps": self._config.fps,
                    "jpeg_quality": self._config.jpeg_quality,
                },
                "clock_domain": "relay_monotonic",
                "cross_host_latency_state": "UNVERIFIED_CLOCK_DOMAIN",
            }
        # Never hold the frame condition while an optional OS probe is running.
        payload["wifi"] = self._wifi_probe.status()
        return payload

    def close(self) -> None:
        with self._condition:
            if self._stop_timer:
                self._stop_timer.cancel()
                self._stop_timer = None
            producer, self._producer = self._producer, None
            self._producer_generation += 1
            self._clear_frame_locked()
            self._condition.notify_all()
        if producer:
            producer.stop()


class GstProducer:
    def __init__(
        self,
        publish: Callable[[bytes], bool],
        config: RelayConfig = REFERENCE_CONFIG,
    ):
        self._publish = publish
        self._config = config
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
            except RelaySetupError as exc:
                error = str(exc)
            except (OSError, subprocess.SubprocessError):
                error = "SOURCE_STALE: RealSense capture process unavailable"
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
            list(gstreamer_command(device, self._config)),
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
            return (
                "SOURCE_STALE: RealSense GStreamer stdout closed while the process was running"
            )
        if returncode == 0:
            return "SOURCE_STALE: RealSense GStreamer stream ended unexpectedly"
        return f"SOURCE_STALE: RealSense GStreamer exited with status {returncode}"

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
    # A supervised service restart can leave the previous MJPEG connection in
    # TCP teardown after the listener has closed.  SO_REUSEADDR permits the
    # single replacement listener to reclaim the fixed port without enabling
    # parallel listeners (SO_REUSEPORT remains disabled).
    allow_reuse_address = True
    request_queue_size = MAX_HTTP_CLIENTS

    def __init__(
        self, hub: FrameHub, config: RelayConfig = REFERENCE_CONFIG
    ):
        self.hub = hub
        self.config = config
        self._client_slots = threading.BoundedSemaphore(MAX_HTTP_CLIENTS)
        super().__init__((config.bind_host, config.port), RelayHandler)

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
        if not client_allowed(
            str(self.client_address[0]), self.path, self.server.config
        ):
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
                sequence, jpeg, capture_monotonic_ns = hub.wait_packet_after(sequence)
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
                    f"Content-Length: {len(jpeg)}\r\n"
                    f"X-Robot-Scope-Source-Epoch: {hub.source_epoch}\r\n"
                    f"X-Robot-Scope-Sequence: {sequence}\r\n"
                    "X-Robot-Scope-Capture-Clock: robot-monotonic\r\n"
                    "X-Robot-Scope-Capture-Monotonic-Ns: "
                    f"{capture_monotonic_ns}\r\n\r\n"
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
    config = relay_configuration(validate_local_bind=True)
    # Fail before binding so a missing/ambiguous USB camera is explicit.
    device = resolve_realsense_device()
    gstreamer_command(device, config)
    hub = FrameHub(lambda publish: GstProducer(publish, config), config)
    server = RelayServer(hub, config)
    stopping = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        if not stopping.is_set():
            stopping.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        print(
            "[Robot Scope RealSense] listening on "
            f"http://{config.bind_host}:{config.port} "
            f"profile={config.width}x{config.height}@{config.fps} q={config.jpeg_quality}"
        )
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        hub.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(os.sys.argv[1:]))
    except RelaySetupError as exc:
        print(f"[Robot Scope RealSense] {exc}", file=os.sys.stderr)
        raise SystemExit(2) from None
