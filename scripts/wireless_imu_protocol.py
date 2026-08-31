#!/usr/bin/env python3
"""Fixed authenticated binary protocol for the minimum Go2 IMU transport."""

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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable


MAGIC = b"RSIM"
PROTOCOL_VERSION = 1
MESSAGE_TYPE_IMU = 1
FLAG_SOURCE_TICK = 1
ALLOWED_FLAGS = FLAG_SOURCE_TICK
SENDER_ID = b"go2-body-imu"
KEY_BYTES = 32
KEY_PATH = Path("/etc/robot-scope/wireless-imu.key")
CLOCK_SYNC_MARKER = Path("/run/systemd/timesync/synchronized")

ROBOT_IP = "192.168.50.30"
EXTERNAL_IP = "192.168.50.10"
WIRELESS_IMU_PORT = 46020
SOCKET_TIMEOUT_S = 0.05

MAX_COUNTER = (1 << 63) - 1
MAX_SOURCE_AGE_NS = 500_000_000
MAX_FUTURE_SKEW_NS = 100_000_000
FRESH_AFTER_NS = 250_000_000
MAX_CONSECUTIVE_GAP_NS = 250_000_000
READY_SAMPLE_COUNT = 5
MAX_RETIRED_BOOTS = 4
MAX_QUATERNION_NORM_ERROR = 0.5

_BODY = struct.Struct("!4sBBH16s16sQQQQ10d")
PACKET_BYTES = _BODY.size + hashlib.sha256().digest_size
_NO_SOURCE_TICK = 0

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
    "quaternion_norm",
    "clock_unsynchronized",
    "stale",
    "future",
    "duplicate",
    "reorder",
    "replay",
    "retired_boot",
)


class WirelessImuError(ValueError):
    """A bounded setup, packet, or state-contract failure."""

    def __init__(self, reason: str) -> None:
        if reason not in REJECT_REASONS and reason not in {"key_file", "socket"}:
            raise ValueError("unknown wireless IMU failure reason")
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ImuEnvelope:
    boot_id: uuid.UUID
    sequence: int
    realtime_ns: int
    monotonic_ns: int
    source_tick: int | None
    quaternion_wxyz: tuple[float, float, float, float]
    gyroscope_xyz: tuple[float, float, float]
    accelerometer_xyz: tuple[float, float, float]


@dataclass(frozen=True, init=False)
class SenderPeer:
    local_ip: str = ROBOT_IP
    peer_ip: str = EXTERNAL_IP
    port: int = WIRELESS_IMU_PORT


@dataclass(frozen=True, init=False)
class ReceiverPeer:
    local_ip: str = EXTERNAL_IP
    peer_ip: str = ROBOT_IP
    port: int = WIRELESS_IMU_PORT


def _saturating_add(value: int, increment: int = 1) -> int:
    return min(MAX_COUNTER, value + max(0, increment))


def load_private_key(path: Path = KEY_PATH) -> bytes:
    """Read one exact mode-0600, owner-only, non-symlinked binary key."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise WirelessImuError("key_file")
        if metadata.st_uid != os.geteuid():
            raise WirelessImuError("key_file")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise WirelessImuError("key_file")
        if metadata.st_size != KEY_BYTES:
            raise WirelessImuError("key_file")
        key = os.read(descriptor, KEY_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise WirelessImuError("key_file") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(key) != KEY_BYTES:
        raise WirelessImuError("key_file")
    return key


def read_boot_id(path: Path = Path("/proc/sys/kernel/random/boot_id")) -> uuid.UUID:
    try:
        value = path.read_text(encoding="ascii").strip()
        boot_id = uuid.UUID(value)
    except (OSError, UnicodeError, ValueError) as exc:
        raise WirelessImuError("boot_id") from exc
    if boot_id.int == 0:
        raise WirelessImuError("boot_id")
    return boot_id


def system_clock_synchronized(path: Path = CLOCK_SYNC_MARKER) -> bool:
    """Fail closed unless systemd-timesyncd exposes its synchronized marker."""

    try:
        metadata = os.lstat(path)
    except (OSError, ValueError):
        return False
    return stat.S_ISREG(metadata.st_mode)


def _fixed_values(value: object, length: int, reason: str) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise WirelessImuError(reason)
    try:
        values = tuple(float(item) for item in value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise WirelessImuError(reason) from exc
    if len(values) != length or not all(math.isfinite(item) for item in values):
        raise WirelessImuError(reason)
    return values


def validate_envelope(sample: ImuEnvelope) -> ImuEnvelope:
    if not isinstance(sample.boot_id, uuid.UUID) or sample.boot_id.int == 0:
        raise WirelessImuError("boot_id")
    if (
        isinstance(sample.sequence, bool)
        or sample.sequence <= 0
        or sample.sequence > 0xFFFFFFFFFFFFFFFF
    ):
        raise WirelessImuError("sequence")
    for value in (sample.realtime_ns, sample.monotonic_ns):
        if isinstance(value, bool) or value <= 0 or value > 0xFFFFFFFFFFFFFFFF:
            raise WirelessImuError("timestamp")
    if sample.source_tick is not None and (
        isinstance(sample.source_tick, bool)
        or sample.source_tick < 0
        or sample.source_tick > 0xFFFFFFFFFFFFFFFF
    ):
        raise WirelessImuError("timestamp")

    quaternion = _fixed_values(sample.quaternion_wxyz, 4, "nonfinite")
    gyroscope = _fixed_values(sample.gyroscope_xyz, 3, "nonfinite")
    accelerometer = _fixed_values(sample.accelerometer_xyz, 3, "nonfinite")
    norm = math.sqrt(sum(item * item for item in quaternion))
    if (
        not math.isfinite(norm)
        or norm < 1.0 - MAX_QUATERNION_NORM_ERROR
        or norm > 1.0 + MAX_QUATERNION_NORM_ERROR
    ):
        raise WirelessImuError("quaternion_norm")
    normalized = tuple(item / norm for item in quaternion)
    return replace(
        sample,
        quaternion_wxyz=normalized,  # type: ignore[arg-type]
        gyroscope_xyz=gyroscope,  # type: ignore[arg-type]
        accelerometer_xyz=accelerometer,  # type: ignore[arg-type]
    )


def encode_envelope(sample: ImuEnvelope, key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) != KEY_BYTES:
        raise WirelessImuError("key_file")
    sample = validate_envelope(sample)
    flags = FLAG_SOURCE_TICK if sample.source_tick is not None else 0
    sender = SENDER_ID.ljust(16, b"\x00")
    body = _BODY.pack(
        MAGIC,
        PROTOCOL_VERSION,
        MESSAGE_TYPE_IMU,
        flags,
        sender,
        sample.boot_id.bytes,
        sample.sequence,
        sample.realtime_ns,
        sample.monotonic_ns,
        sample.source_tick if sample.source_tick is not None else _NO_SOURCE_TICK,
        *sample.quaternion_wxyz,
        *sample.gyroscope_xyz,
        *sample.accelerometer_xyz,
    )
    signature = hmac.new(key, body, hashlib.sha256).digest()
    return body + signature


def decode_envelope(packet: bytes, key: bytes) -> ImuEnvelope:
    if not isinstance(key, bytes) or len(key) != KEY_BYTES:
        raise WirelessImuError("key_file")
    if not isinstance(packet, bytes) or len(packet) != PACKET_BYTES:
        raise WirelessImuError("packet_length")
    body = packet[: _BODY.size]
    supplied = packet[_BODY.size :]
    expected = hmac.new(key, body, hashlib.sha256).digest()
    if not hmac.compare_digest(supplied, expected):
        raise WirelessImuError("authentication")
    unpacked = _BODY.unpack(body)
    magic, version, message_type, flags, sender, boot_bytes = unpacked[:6]
    if magic != MAGIC:
        raise WirelessImuError("magic")
    if version != PROTOCOL_VERSION:
        raise WirelessImuError("version")
    if message_type != MESSAGE_TYPE_IMU:
        raise WirelessImuError("message_type")
    if flags & ~ALLOWED_FLAGS:
        raise WirelessImuError("flags")
    if sender.rstrip(b"\x00") != SENDER_ID:
        raise WirelessImuError("sender_id")
    try:
        boot_id = uuid.UUID(bytes=boot_bytes)
    except ValueError as exc:
        raise WirelessImuError("boot_id") from exc
    if boot_id.int == 0:
        raise WirelessImuError("boot_id")
    sequence, realtime_ns, monotonic_ns, encoded_tick = unpacked[6:10]
    values = unpacked[10:]
    source_tick = encoded_tick if flags & FLAG_SOURCE_TICK else None
    if source_tick is None and encoded_tick != _NO_SOURCE_TICK:
        raise WirelessImuError("flags")
    return validate_envelope(
        ImuEnvelope(
            boot_id=boot_id,
            sequence=sequence,
            realtime_ns=realtime_ns,
            monotonic_ns=monotonic_ns,
            source_tick=source_tick,
            quaternion_wxyz=tuple(values[0:4]),
            gyroscope_xyz=tuple(values[4:7]),
            accelerometer_xyz=tuple(values[7:10]),
        )
    )


class ConnectedImuDatagram:
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
            raise WirelessImuError("socket")
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
            raise WirelessImuError("socket") from exc
        self.peer = peer
        self._socket = endpoint

    def send(self, packet: bytes) -> None:
        if not isinstance(packet, bytes) or len(packet) != PACKET_BYTES:
            raise WirelessImuError("packet_length")
        sent = self._socket.send(packet)
        if sent != PACKET_BYTES:
            raise OSError("wireless IMU datagram send was incomplete")

    def receive(self) -> bytes | None:
        try:
            packet = self._socket.recv(PACKET_BYTES + 1)
        except (socket.timeout, BlockingIOError):
            return None
        if len(packet) != PACKET_BYTES:
            raise WirelessImuError("packet_length")
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
        setattr(
            self,
            field_name,
            _saturating_add(getattr(self, field_name), increment),
        )

    def reject(self, reason: str) -> None:
        if reason not in self.rejected:
            raise ValueError("unknown wireless IMU rejection reason")
        self.rejected[reason] = _saturating_add(self.rejected[reason])


class ReceiverCore:
    """Authenticated sequence, clock, boot, and freshness state machine."""

    def __init__(self, key: bytes) -> None:
        if not isinstance(key, bytes) or len(key) != KEY_BYTES:
            raise WirelessImuError("key_file")
        self._key = key
        self.stats = ReceiverStats()
        self._boot_id: uuid.UUID | None = None
        self._retired_boots: deque[uuid.UUID] = deque(maxlen=MAX_RETIRED_BOOTS)
        self._last_sequence: int | None = None
        self._last_source_realtime_ns: int | None = None
        self._last_source_monotonic_ns: int | None = None
        self._last_received_monotonic_ns: int | None = None
        self._consecutive = 0
        self._authenticated = False
        self._last_jitter_ns: int | None = None
        self._max_jitter_ns = 0

    def _fail(self, reason: str) -> None:
        self.stats.reject(reason)
        if reason == "duplicate":
            self.stats.add("duplicates")
        if reason in {"reorder", "replay"}:
            self.stats.add("reordered")
        self._authenticated = False
        self._consecutive = 0
        raise WirelessImuError(reason)

    def accept(
        self,
        packet: bytes,
        *,
        received_realtime_ns: int,
        received_monotonic_ns: int,
        clock_synchronized: bool,
    ) -> ImuEnvelope:
        self.stats.add("received")
        for timestamp in (received_realtime_ns, received_monotonic_ns):
            if (
                isinstance(timestamp, bool)
                or timestamp <= 0
                or timestamp > 0xFFFFFFFFFFFFFFFF
            ):
                self._fail("timestamp")
        if not clock_synchronized:
            self._fail("clock_unsynchronized")
        try:
            sample = decode_envelope(packet, self._key)
        except WirelessImuError as exc:
            if exc.reason in self.stats.rejected:
                self._fail(exc.reason)
            raise

        if sample.realtime_ns > received_realtime_ns + MAX_FUTURE_SKEW_NS:
            self._fail("future")
        if received_realtime_ns - sample.realtime_ns > MAX_SOURCE_AGE_NS:
            self._fail("stale")

        if self._boot_id is None:
            self._boot_id = sample.boot_id
        elif sample.boot_id != self._boot_id:
            if sample.boot_id in self._retired_boots:
                self._fail("retired_boot")
            self._retired_boots.append(self._boot_id)
            self._boot_id = sample.boot_id
            self._last_sequence = None
            self._last_source_realtime_ns = None
            self._last_source_monotonic_ns = None
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
        if (
            self._last_source_realtime_ns is not None
            and sample.realtime_ns <= self._last_source_realtime_ns
        ):
            self._fail("replay")
        if (
            self._last_source_monotonic_ns is not None
            and sample.monotonic_ns <= self._last_source_monotonic_ns
        ):
            self._fail("replay")

        previous_received = self._last_received_monotonic_ns
        previous_source = self._last_source_realtime_ns
        if previous_received is not None and received_monotonic_ns <= previous_received:
            self._fail("replay")
        if previous_received is not None and previous_source is not None:
            receive_delta = received_monotonic_ns - previous_received
            source_delta = sample.realtime_ns - previous_source
            self._last_jitter_ns = abs(receive_delta - source_delta)
            self._max_jitter_ns = max(self._max_jitter_ns, self._last_jitter_ns)
        self._last_sequence = sample.sequence
        self._last_source_realtime_ns = sample.realtime_ns
        self._last_source_monotonic_ns = sample.monotonic_ns
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
        """Invalidate readiness without terminating the receiver process."""

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
        authenticated = self._authenticated and fresh
        ready = (
            authenticated
            and clock_synchronized
            and self._consecutive >= READY_SAMPLE_COUNT
        )
        return {
            "authenticated": authenticated,
            "ready": ready,
            "clock_synchronized": bool(clock_synchronized),
            "boot_id": str(self._boot_id) if self._boot_id is not None else None,
            "last_sequence": self._last_sequence,
            "packet_age_ms": (
                None if age_ns is None else round(age_ns / 1_000_000.0, 3)
            ),
            "consecutive": self._consecutive,
            "received": self.stats.received,
            "accepted": self.stats.accepted,
            "published": self.stats.published,
            "lost": self.stats.lost,
            "duplicates": self.stats.duplicates,
            "reordered": self.stats.reordered,
            "boot_changes": self.stats.boot_changes,
            "receive_errors": self.stats.receive_errors,
            "jitter_ms": (
                None
                if self._last_jitter_ns is None
                else round(self._last_jitter_ns / 1_000_000.0, 3)
            ),
            "max_jitter_ms": round(self._max_jitter_ns / 1_000_000.0, 3),
            "authentication_failures": self.stats.rejected["authentication"],
            "nonfinite_failures": self.stats.rejected["nonfinite"],
            "quaternion_failures": self.stats.rejected["quaternion_norm"],
            "clock_failures": self.stats.rejected["clock_unsynchronized"],
            "rejected": sum(self.stats.rejected.values()),
        }


__all__ = [
    "CLOCK_SYNC_MARKER",
    "ConnectedImuDatagram",
    "EXTERNAL_IP",
    "FRESH_AFTER_NS",
    "ImuEnvelope",
    "KEY_BYTES",
    "KEY_PATH",
    "MAX_COUNTER",
    "MAX_FUTURE_SKEW_NS",
    "MAX_SOURCE_AGE_NS",
    "PACKET_BYTES",
    "READY_SAMPLE_COUNT",
    "ROBOT_IP",
    "ReceiverCore",
    "ReceiverPeer",
    "ReceiverStats",
    "SENDER_ID",
    "SenderPeer",
    "WIRELESS_IMU_PORT",
    "WirelessImuError",
    "decode_envelope",
    "encode_envelope",
    "load_private_key",
    "read_boot_id",
    "system_clock_synchronized",
    "validate_envelope",
]
