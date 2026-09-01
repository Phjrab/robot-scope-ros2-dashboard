#!/usr/bin/env python3
"""Fixed authenticated binary protocol for Go2 controller odometry."""

from __future__ import annotations

import hashlib
import hmac
import math
import os
import socket
import stat
import struct
import uuid
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


MAGIC = b"RSOD"
PROTOCOL_VERSION = 1
MESSAGE_TYPE_ODOMETRY = 1
FLAGS = 0
SENDER_ID = b"go2-ctrl-odom"
KEY_BYTES = 32
KEY_PATH = Path("/etc/robot-scope/wireless-odom.key")
CLOCK_SYNC_MARKER = Path("/run/systemd/timesync/synchronized")

ROBOT_IP = "192.168.50.30"
EXTERNAL_IP = "192.168.50.10"
WIRELESS_ODOM_PORT = 46030
SOCKET_TIMEOUT_S = 0.05

SOURCE_FRAME = "odom"
CHILD_FRAME = "base_link"
VALUE_COUNT = 85
MAX_COUNTER = (1 << 63) - 1
MAX_SOURCE_AGE_NS = 500_000_000
MAX_FUTURE_SKEW_NS = 100_000_000
MAX_STAMP_SENDER_DELTA_NS = 500_000_000
FRESH_AFTER_NS = 250_000_000
MAX_CONSECUTIVE_GAP_NS = 250_000_000
READY_SAMPLE_COUNT = 5
MAX_RETIRED_BOOTS = 4
MAX_POSITION_ABS_M = 1_000_000.0
MAX_LINEAR_ABS_MPS = 20.0
MAX_ANGULAR_ABS_RADPS = 20.0
MAX_COVARIANCE_ABS = 1_000_000_000_000.0
MAX_QUATERNION_NORM_ERROR = 0.1

_BODY = struct.Struct(f"!4sBBH16s16sQQQQ{VALUE_COUNT}d")
PACKET_BYTES = _BODY.size + hashlib.sha256().digest_size

REJECT_REASONS = (
    "packet_length",
    "authentication",
    "magic",
    "version",
    "message_type",
    "flags",
    "sender_id",
    "boot_id",
    "sequence",
    "timestamp",
    "nonfinite",
    "bounds",
    "quaternion_norm",
    "clock_unsynchronized",
    "stale",
    "future",
    "duplicate",
    "reorder",
    "replay",
    "retired_boot",
)


class WirelessOdomError(ValueError):
    """A bounded setup, packet, or state-contract failure."""

    def __init__(self, reason: str) -> None:
        if reason not in REJECT_REASONS and reason not in {"key_file", "socket"}:
            raise ValueError("unknown wireless odometry failure reason")
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class OdomEnvelope:
    boot_id: uuid.UUID
    sequence: int
    sender_realtime_ns: int
    sender_monotonic_ns: int
    source_stamp_ns: int
    position_xyz: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float]
    linear_xyz: tuple[float, float, float]
    angular_xyz: tuple[float, float, float]
    pose_covariance: tuple[float, ...]
    twist_covariance: tuple[float, ...]


@dataclass(frozen=True, init=False)
class SenderPeer:
    local_ip: str = ROBOT_IP
    peer_ip: str = EXTERNAL_IP
    port: int = WIRELESS_ODOM_PORT


@dataclass(frozen=True, init=False)
class ReceiverPeer:
    local_ip: str = EXTERNAL_IP
    peer_ip: str = ROBOT_IP
    port: int = WIRELESS_ODOM_PORT


def _saturating_add(value: int, increment: int = 1) -> int:
    return min(MAX_COUNTER, value + max(0, increment))


def load_private_key(path: Path = KEY_PATH) -> bytes:
    """Read one exact owner-only mode-0600, non-symlinked key."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise WirelessOdomError("key_file")
        if metadata.st_uid != os.geteuid():
            raise WirelessOdomError("key_file")
        if stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size != KEY_BYTES:
            raise WirelessOdomError("key_file")
        key = os.read(descriptor, KEY_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise WirelessOdomError("key_file") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(key) != KEY_BYTES:
        raise WirelessOdomError("key_file")
    return key


def read_boot_id(path: Path = Path("/proc/sys/kernel/random/boot_id")) -> uuid.UUID:
    try:
        value = uuid.UUID(path.read_text(encoding="ascii").strip())
    except (OSError, UnicodeError, ValueError) as exc:
        raise WirelessOdomError("boot_id") from exc
    if value.int == 0:
        raise WirelessOdomError("boot_id")
    return value


def system_clock_synchronized(path: Path = CLOCK_SYNC_MARKER) -> bool:
    try:
        metadata = os.lstat(path)
    except (OSError, ValueError):
        return False
    return stat.S_ISREG(metadata.st_mode)


def _fixed_values(value: object, length: int) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise WirelessOdomError("nonfinite")
    try:
        values = tuple(float(item) for item in value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise WirelessOdomError("nonfinite") from exc
    if len(values) != length or not all(math.isfinite(item) for item in values):
        raise WirelessOdomError("nonfinite")
    return values


def validate_envelope(sample: OdomEnvelope) -> OdomEnvelope:
    if not isinstance(sample.boot_id, uuid.UUID) or sample.boot_id.int == 0:
        raise WirelessOdomError("boot_id")
    if (
        isinstance(sample.sequence, bool)
        or not isinstance(sample.sequence, int)
        or sample.sequence <= 0
        or sample.sequence > 0xFFFFFFFFFFFFFFFF
    ):
        raise WirelessOdomError("sequence")
    for value in (
        sample.sender_realtime_ns,
        sample.sender_monotonic_ns,
        sample.source_stamp_ns,
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            or value > 0xFFFFFFFFFFFFFFFF
        ):
            raise WirelessOdomError("timestamp")

    position = _fixed_values(sample.position_xyz, 3)
    orientation = _fixed_values(sample.orientation_xyzw, 4)
    linear = _fixed_values(sample.linear_xyz, 3)
    angular = _fixed_values(sample.angular_xyz, 3)
    pose_covariance = _fixed_values(sample.pose_covariance, 36)
    twist_covariance = _fixed_values(sample.twist_covariance, 36)
    if any(abs(value) > MAX_POSITION_ABS_M for value in position):
        raise WirelessOdomError("bounds")
    if any(abs(value) > MAX_LINEAR_ABS_MPS for value in linear):
        raise WirelessOdomError("bounds")
    if any(abs(value) > MAX_ANGULAR_ABS_RADPS for value in angular):
        raise WirelessOdomError("bounds")
    if any(
        abs(value) > MAX_COVARIANCE_ABS
        for value in (*pose_covariance, *twist_covariance)
    ):
        raise WirelessOdomError("bounds")
    norm = math.sqrt(sum(value * value for value in orientation))
    if not math.isfinite(norm) or abs(norm - 1.0) > MAX_QUATERNION_NORM_ERROR:
        raise WirelessOdomError("quaternion_norm")
    return OdomEnvelope(
        boot_id=sample.boot_id,
        sequence=sample.sequence,
        sender_realtime_ns=sample.sender_realtime_ns,
        sender_monotonic_ns=sample.sender_monotonic_ns,
        source_stamp_ns=sample.source_stamp_ns,
        position_xyz=position,  # type: ignore[arg-type]
        orientation_xyzw=orientation,  # type: ignore[arg-type]
        linear_xyz=linear,  # type: ignore[arg-type]
        angular_xyz=angular,  # type: ignore[arg-type]
        pose_covariance=pose_covariance,
        twist_covariance=twist_covariance,
    )


def _values(sample: OdomEnvelope) -> tuple[float, ...]:
    return (
        *sample.position_xyz,
        *sample.orientation_xyzw,
        *sample.linear_xyz,
        *sample.angular_xyz,
        *sample.pose_covariance,
        *sample.twist_covariance,
    )


def encode_envelope(sample: OdomEnvelope, key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) != KEY_BYTES:
        raise WirelessOdomError("key_file")
    sample = validate_envelope(sample)
    body = _BODY.pack(
        MAGIC,
        PROTOCOL_VERSION,
        MESSAGE_TYPE_ODOMETRY,
        FLAGS,
        SENDER_ID.ljust(16, b"\x00"),
        sample.boot_id.bytes,
        sample.sequence,
        sample.sender_realtime_ns,
        sample.sender_monotonic_ns,
        sample.source_stamp_ns,
        *_values(sample),
    )
    return body + hmac.new(key, body, hashlib.sha256).digest()


def decode_envelope(packet: bytes, key: bytes) -> OdomEnvelope:
    if not isinstance(key, bytes) or len(key) != KEY_BYTES:
        raise WirelessOdomError("key_file")
    if not isinstance(packet, bytes) or len(packet) != PACKET_BYTES:
        raise WirelessOdomError("packet_length")
    body = packet[: _BODY.size]
    if not hmac.compare_digest(
        packet[_BODY.size :], hmac.new(key, body, hashlib.sha256).digest()
    ):
        raise WirelessOdomError("authentication")
    unpacked = _BODY.unpack(body)
    magic, version, message_type, flags, sender, boot_bytes = unpacked[:6]
    if magic != MAGIC:
        raise WirelessOdomError("magic")
    if version != PROTOCOL_VERSION:
        raise WirelessOdomError("version")
    if message_type != MESSAGE_TYPE_ODOMETRY:
        raise WirelessOdomError("message_type")
    if flags != FLAGS:
        raise WirelessOdomError("flags")
    if sender.rstrip(b"\x00") != SENDER_ID:
        raise WirelessOdomError("sender_id")
    try:
        boot_id = uuid.UUID(bytes=boot_bytes)
    except ValueError as exc:
        raise WirelessOdomError("boot_id") from exc
    values = unpacked[10:]
    return validate_envelope(
        OdomEnvelope(
            boot_id=boot_id,
            sequence=unpacked[6],
            sender_realtime_ns=unpacked[7],
            sender_monotonic_ns=unpacked[8],
            source_stamp_ns=unpacked[9],
            position_xyz=tuple(values[0:3]),
            orientation_xyzw=tuple(values[3:7]),
            linear_xyz=tuple(values[7:10]),
            angular_xyz=tuple(values[10:13]),
            pose_covariance=tuple(values[13:49]),
            twist_covariance=tuple(values[49:85]),
        )
    )


class ConnectedOdomDatagram:
    """One fixed connected UDP endpoint; the kernel rejects other peers."""

    def __init__(
        self,
        role: str,
        *,
        socket_factory: Callable[..., socket.socket] = socket.socket,
    ) -> None:
        if role == "sender":
            peer: SenderPeer | ReceiverPeer = SenderPeer()
        elif role == "receiver":
            peer = ReceiverPeer()
        else:
            raise WirelessOdomError("socket")
        endpoint: socket.socket | None = None
        try:
            endpoint = socket_factory(
                socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
            )
            endpoint.bind((peer.local_ip, peer.port))
            endpoint.connect((peer.peer_ip, peer.port))
            endpoint.settimeout(SOCKET_TIMEOUT_S)
        except (OSError, ValueError) as exc:
            if endpoint is not None:
                endpoint.close()
            raise WirelessOdomError("socket") from exc
        self.peer = peer
        self._socket = endpoint

    def send(self, packet: bytes) -> None:
        if not isinstance(packet, bytes) or len(packet) != PACKET_BYTES:
            raise WirelessOdomError("packet_length")
        if self._socket.send(packet) != PACKET_BYTES:
            raise OSError("wireless odometry datagram send was incomplete")

    def receive(self) -> bytes | None:
        try:
            packet = self._socket.recv(PACKET_BYTES + 1)
        except (socket.timeout, BlockingIOError):
            return None
        if len(packet) != PACKET_BYTES:
            raise WirelessOdomError("packet_length")
        return packet

    def close(self) -> None:
        self._socket.close()


@dataclass
class ReceiverStats:
    received: int = 0
    accepted: int = 0
    published: int = 0
    lost: int = 0
    duplicates: int = 0
    reordered: int = 0
    boot_changes: int = 0
    receive_errors: int = 0
    rejected: dict[str, int] = field(
        default_factory=lambda: {reason: 0 for reason in REJECT_REASONS}
    )

    def add(self, field_name: str, increment: int = 1) -> None:
        setattr(self, field_name, _saturating_add(getattr(self, field_name), increment))

    def reject(self, reason: str) -> None:
        self.rejected[reason] = _saturating_add(self.rejected[reason])


class ReceiverCore:
    """Authenticated sequence, boot, source-stamp, and freshness state machine."""

    def __init__(self, key: bytes) -> None:
        if not isinstance(key, bytes) or len(key) != KEY_BYTES:
            raise WirelessOdomError("key_file")
        self._key = key
        self.stats = ReceiverStats()
        self._boot_id: uuid.UUID | None = None
        self._retired_boots: deque[uuid.UUID] = deque(maxlen=MAX_RETIRED_BOOTS)
        self._last_sequence: int | None = None
        self._last_sender_realtime_ns: int | None = None
        self._last_sender_monotonic_ns: int | None = None
        self._last_source_stamp_ns: int | None = None
        self._last_received_monotonic_ns: int | None = None
        self._consecutive = 0
        self._authenticated = False

    def _fail(self, reason: str) -> None:
        self.stats.reject(reason)
        if reason == "duplicate":
            self.stats.add("duplicates")
        if reason in {"reorder", "replay"}:
            self.stats.add("reordered")
        self._authenticated = False
        self._consecutive = 0
        raise WirelessOdomError(reason)

    def accept(
        self,
        packet: bytes,
        *,
        received_realtime_ns: int,
        received_monotonic_ns: int,
        clock_synchronized: bool,
    ) -> OdomEnvelope:
        self.stats.add("received")
        for timestamp in (received_realtime_ns, received_monotonic_ns):
            if (
                isinstance(timestamp, bool)
                or not isinstance(timestamp, int)
                or timestamp <= 0
                or timestamp > 0xFFFFFFFFFFFFFFFF
            ):
                self._fail("timestamp")
        if not clock_synchronized:
            self._fail("clock_unsynchronized")
        try:
            sample = decode_envelope(packet, self._key)
        except WirelessOdomError as exc:
            self._fail(exc.reason)

        if sample.sender_realtime_ns > received_realtime_ns + MAX_FUTURE_SKEW_NS:
            self._fail("future")
        if received_realtime_ns - sample.sender_realtime_ns > MAX_SOURCE_AGE_NS:
            self._fail("stale")
        stamp_delta = sample.source_stamp_ns - sample.sender_realtime_ns
        if stamp_delta > MAX_FUTURE_SKEW_NS:
            self._fail("future")
        if stamp_delta < -MAX_STAMP_SENDER_DELTA_NS:
            self._fail("stale")

        if self._boot_id is None:
            self._boot_id = sample.boot_id
        elif sample.boot_id != self._boot_id:
            if sample.boot_id in self._retired_boots:
                self._fail("retired_boot")
            self._retired_boots.append(self._boot_id)
            self._boot_id = sample.boot_id
            self._last_sequence = None
            self._last_sender_realtime_ns = None
            self._last_sender_monotonic_ns = None
            self._last_source_stamp_ns = None
            self._last_received_monotonic_ns = None
            self._consecutive = 0
            self.stats.add("boot_changes")

        if self._last_sequence is not None:
            if sample.sequence == self._last_sequence:
                self._fail("duplicate")
            if sample.sequence < self._last_sequence:
                self._fail("reorder")
            if sample.sequence > self._last_sequence + 1:
                self.stats.add("lost", sample.sequence - self._last_sequence - 1)
        for current, previous in (
            (sample.sender_realtime_ns, self._last_sender_realtime_ns),
            (sample.sender_monotonic_ns, self._last_sender_monotonic_ns),
            (sample.source_stamp_ns, self._last_source_stamp_ns),
            (received_monotonic_ns, self._last_received_monotonic_ns),
        ):
            if previous is not None and current <= previous:
                self._fail("replay")

        previous_received = self._last_received_monotonic_ns
        self._last_sequence = sample.sequence
        self._last_sender_realtime_ns = sample.sender_realtime_ns
        self._last_sender_monotonic_ns = sample.sender_monotonic_ns
        self._last_source_stamp_ns = sample.source_stamp_ns
        self._last_received_monotonic_ns = received_monotonic_ns
        if (
            previous_received is None
            or received_monotonic_ns - previous_received > MAX_CONSECUTIVE_GAP_NS
        ):
            self._consecutive = 1
        else:
            self._consecutive = min(READY_SAMPLE_COUNT, self._consecutive + 1)
        self._authenticated = True
        self.stats.add("accepted")
        return sample

    def note_published(self) -> None:
        self.stats.add("published")

    def note_transport_loss(self) -> None:
        self.stats.add("receive_errors")
        self._authenticated = False
        self._consecutive = 0

    def snapshot(
        self, *, now_monotonic_ns: int, clock_synchronized: bool
    ) -> dict[str, object]:
        age_ns = (
            None
            if self._last_received_monotonic_ns is None
            else max(0, now_monotonic_ns - self._last_received_monotonic_ns)
        )
        fresh = age_ns is not None and age_ns <= FRESH_AFTER_NS
        authenticated = bool(self._authenticated and fresh)
        ready = bool(
            authenticated
            and clock_synchronized
            and self._consecutive >= READY_SAMPLE_COUNT
        )
        return {
            "authenticated": authenticated,
            "ready": ready,
            "clock_synchronized": bool(clock_synchronized),
            "boot_id": str(self._boot_id) if self._boot_id else None,
            "last_sequence": self._last_sequence,
            "packet_age_ms": None if age_ns is None else round(age_ns / 1_000_000, 3),
            "consecutive": self._consecutive,
            "received": self.stats.received,
            "accepted": self.stats.accepted,
            "published": self.stats.published,
            "lost": self.stats.lost,
            "duplicates": self.stats.duplicates,
            "reordered": self.stats.reordered,
            "boot_changes": self.stats.boot_changes,
            "receive_errors": self.stats.receive_errors,
            "authentication_failures": self.stats.rejected["authentication"],
            "nonfinite_failures": self.stats.rejected["nonfinite"],
            "clock_failures": self.stats.rejected["clock_unsynchronized"],
            "rejected": sum(self.stats.rejected.values()),
        }


__all__ = [
    "CHILD_FRAME",
    "ConnectedOdomDatagram",
    "EXTERNAL_IP",
    "FRESH_AFTER_NS",
    "KEY_BYTES",
    "KEY_PATH",
    "OdomEnvelope",
    "PACKET_BYTES",
    "READY_SAMPLE_COUNT",
    "ROBOT_IP",
    "ReceiverCore",
    "SOURCE_FRAME",
    "WIRELESS_ODOM_PORT",
    "WirelessOdomError",
    "decode_envelope",
    "encode_envelope",
    "load_private_key",
    "read_boot_id",
    "system_clock_synchronized",
    "validate_envelope",
]
