#!/usr/bin/env python3
"""Relay only the fixed Go2 front-camera RTP stream to the dashboard host.

The Go2 publishes H.264 RTP multicast on the isolated robot LAN.  This process
joins that one group on the robot-mounted Jetson and sends unchanged, validated
RTP packets to one fixed dashboard address on the management LAN.  It does not
route either subnet, expose a configurable destination, decode video, or carry
ROS/DDS/control traffic.
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, NoReturn, Sequence


SOCKET_TIMEOUT_S = 0.25
STATS_INTERVAL_S = 5.0
MAX_COUNTER = (1 << 63) - 1
MIN_RTP_PACKET_BYTES = 13
MAX_RTP_PACKET_BYTES = 2048
RTP_VERSION = 2
RTP_PAYLOAD_TYPE_H264 = 96

# Fixed, field-validated wireless camera contract.  Operational addresses,
# interfaces and ports are intentionally not supplied by HTTP, environment or
# command-line input.
CAPTURE_INTERFACE = "eth0"
CAPTURE_INTERFACE_IP = "192.168.123.18"
GO2_SOURCE_IP = "192.168.123.161"
GO2_MULTICAST_ADDRESS = "230.1.1.1"
GO2_CAMERA_PORT = 1720
RELAY_SOURCE_IP = "192.168.50.30"
RELAY_SOURCE_PORT = 46120
DASHBOARD_IP = "192.168.50.10"
DASHBOARD_PORT = 1720

REJECT_REASONS = (
    "source",
    "size",
    "version",
    "header",
    "payload_type",
    "h264",
)


class RelayError(RuntimeError):
    """Base class for an expected relay failure."""


class RelaySetupError(RelayError):
    """Raised when the fixed input or output socket cannot be owned."""


class RelayRuntimeError(RelayError):
    """Raised when an established relay socket stops working."""


class PacketRejected(ValueError):
    """A datagram that does not match the fixed Go2 H.264 RTP contract."""

    def __init__(self, reason: str) -> None:
        if reason not in REJECT_REASONS:
            raise ValueError("unknown packet rejection reason")
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class RelayConfig:
    interface: str = CAPTURE_INTERFACE
    interface_ip: str = CAPTURE_INTERFACE_IP
    source_ip: str = GO2_SOURCE_IP
    multicast_address: str = GO2_MULTICAST_ADDRESS
    input_port: int = GO2_CAMERA_PORT
    relay_ip: str = RELAY_SOURCE_IP
    relay_port: int = RELAY_SOURCE_PORT
    dashboard_ip: str = DASHBOARD_IP
    dashboard_port: int = DASHBOARD_PORT

    @property
    def dashboard_address(self) -> tuple[str, int]:
        return (self.dashboard_ip, self.dashboard_port)


@dataclass(frozen=True)
class ParsedRtp:
    packet: bytes
    sequence: int
    timestamp: int
    ssrc: int


def _saturating_add(value: int, increment: int = 1) -> int:
    return min(MAX_COUNTER, value + max(0, increment))


@dataclass
class RelayStats:
    captured: int = 0
    accepted: int = 0
    forwarded: int = 0
    forwarded_bytes: int = 0
    send_errors: int = 0
    sequence_lost: int = 0
    sequence_duplicates: int = 0
    sequence_reordered: int = 0
    ssrc_changes: int = 0
    rejected: dict[str, int] = field(
        default_factory=lambda: {reason: 0 for reason in REJECT_REASONS}
    )
    _last_sequence: int | None = None
    _last_ssrc: int | None = None

    def add(self, name: str, increment: int = 1) -> None:
        setattr(self, name, _saturating_add(getattr(self, name), increment))

    def reject(self, reason: str) -> None:
        if reason not in self.rejected:
            raise ValueError("unknown packet rejection reason")
        self.rejected[reason] = _saturating_add(self.rejected[reason])

    def observe(self, packet: ParsedRtp) -> None:
        if self._last_ssrc is not None and packet.ssrc != self._last_ssrc:
            self.ssrc_changes = _saturating_add(self.ssrc_changes)
            self._last_sequence = None
        self._last_ssrc = packet.ssrc

        previous = self._last_sequence
        if previous is None:
            self._last_sequence = packet.sequence
            return
        delta = (packet.sequence - previous) & 0xFFFF
        if delta == 0:
            self.sequence_duplicates = _saturating_add(self.sequence_duplicates)
        elif delta < 0x8000:
            if delta > 1:
                self.sequence_lost = _saturating_add(
                    self.sequence_lost, delta - 1
                )
            self._last_sequence = packet.sequence
        else:
            self.sequence_reordered = _saturating_add(self.sequence_reordered)

    def format(self, label: str) -> str:
        rejected_total = sum(self.rejected.values())
        details = ",".join(
            f"{reason}:{self.rejected[reason]}"
            for reason in REJECT_REASONS
            if self.rejected[reason]
        ) or "none"
        return (
            f"[Robot Scope Go2 camera relay] {label} "
            f"captured={self.captured} accepted={self.accepted} "
            f"forwarded={self.forwarded} bytes={self.forwarded_bytes} "
            f"send_errors={self.send_errors} seq_lost={self.sequence_lost} "
            f"seq_duplicate={self.sequence_duplicates} "
            f"seq_reordered={self.sequence_reordered} "
            f"ssrc_changes={self.ssrc_changes} "
            f"rejected={rejected_total}({details})"
        )


def _reject(reason: str) -> NoReturn:
    raise PacketRejected(reason)


def parse_go2_camera_rtp(
    packet: bytes,
    source: tuple[object, ...],
    config: RelayConfig,
) -> ParsedRtp:
    """Validate one RTP/H.264 datagram from the fixed Go2 source."""

    if (
        len(source) < 2
        or source[0] != config.source_ip
        or not isinstance(source[1], int)
        or not 1 <= source[1] <= 65535
    ):
        _reject("source")
    if not MIN_RTP_PACKET_BYTES <= len(packet) <= MAX_RTP_PACKET_BYTES:
        _reject("size")

    first = packet[0]
    if first >> 6 != RTP_VERSION:
        _reject("version")
    csrc_count = first & 0x0F
    header_length = 12 + csrc_count * 4
    if header_length >= len(packet):
        _reject("header")

    if first & 0x10:
        if header_length + 4 > len(packet):
            _reject("header")
        extension_words = struct.unpack_from("!H", packet, header_length + 2)[0]
        header_length += 4 + extension_words * 4
        if header_length >= len(packet):
            _reject("header")

    payload_end = len(packet)
    if first & 0x20:
        padding = packet[-1]
        if padding < 1 or padding >= payload_end - header_length:
            _reject("header")
        payload_end -= padding

    if packet[1] & 0x7F != RTP_PAYLOAD_TYPE_H264:
        _reject("payload_type")
    if header_length >= payload_end:
        _reject("h264")

    h264_payload = packet[header_length:payload_end]
    nal_type = h264_payload[0] & 0x1F
    if 1 <= nal_type <= 23:
        pass
    elif nal_type == 24:  # STAP-A aggregation packet
        offset = 1
        units = 0
        while offset < len(h264_payload):
            if offset + 2 > len(h264_payload):
                _reject("h264")
            length = struct.unpack_from("!H", h264_payload, offset)[0]
            offset += 2
            if length < 1 or offset + length > len(h264_payload):
                _reject("h264")
            unit_type = h264_payload[offset] & 0x1F
            if not 1 <= unit_type <= 23:
                _reject("h264")
            units += 1
            offset += length
        if units < 1:
            _reject("h264")
    elif nal_type == 28:  # FU-A fragmentation packet
        if len(h264_payload) < 3:
            _reject("h264")
        fu_header = h264_payload[1]
        unit_type = fu_header & 0x1F
        if not 1 <= unit_type <= 23 or fu_header & 0xC0 == 0xC0:
            _reject("h264")
    else:
        _reject("h264")

    return ParsedRtp(
        packet=packet,
        sequence=struct.unpack_from("!H", packet, 2)[0],
        timestamp=struct.unpack_from("!I", packet, 4)[0],
        ssrc=struct.unpack_from("!I", packet, 8)[0],
    )


def _make_receiver_socket(config: RelayConfig) -> socket.socket:
    receiver: socket.socket | None = None
    try:
        if socket.if_nametoindex(config.interface) < 1:
            raise OSError("interface unavailable")
        receiver = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
        )
        receiver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        receiver.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        receiver.bind(("", config.input_port))
        membership = socket.inet_aton(config.multicast_address) + socket.inet_aton(
            config.interface_ip
        )
        receiver.setsockopt(
            socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership
        )
        receiver.settimeout(SOCKET_TIMEOUT_S)
        return receiver
    except (OSError, ValueError) as exc:
        if receiver is not None:
            receiver.close()
        raise RelaySetupError(
            "cannot join the fixed Go2 camera multicast group on eth0/.18"
        ) from exc


def _make_sender_socket(config: RelayConfig) -> socket.socket:
    sender: socket.socket | None = None
    try:
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sender.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
        # The fixed, non-reused source port is also the single-instance guard:
        # a second relay fails closed instead of duplicating every video packet.
        sender.bind((config.relay_ip, config.relay_port))
        sender.connect(config.dashboard_address)
        return sender
    except OSError as exc:
        if sender is not None:
            sender.close()
        raise RelaySetupError(
            "cannot own the fixed wireless relay source or dashboard peer"
        ) from exc


def run_relay(
    receiver: socket.socket,
    sender: socket.socket,
    config: RelayConfig,
    stopping: threading.Event,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    output: Callable[[str], None] = lambda line: print(line, flush=True),
) -> RelayStats:
    """Forward validated Go2 RTP packets until ``stopping`` is set."""

    stats = RelayStats()
    next_report = monotonic() + STATS_INTERVAL_S
    try:
        while not stopping.is_set():
            try:
                packet, source = receiver.recvfrom(MAX_RTP_PACKET_BYTES + 1)
            except socket.timeout:
                packet = None
                source = ()
            except InterruptedError:
                continue
            except OSError as exc:
                if stopping.is_set():
                    break
                raise RelayRuntimeError("camera receive socket failed") from exc

            if packet is not None:
                stats.add("captured")
                try:
                    parsed = parse_go2_camera_rtp(packet, source, config)
                except PacketRejected as exc:
                    stats.reject(exc.reason)
                else:
                    stats.add("accepted")
                    stats.observe(parsed)
                    try:
                        sent = sender.send(parsed.packet)
                    except OSError:
                        stats.add("send_errors")
                    else:
                        if sent != len(parsed.packet):
                            stats.add("send_errors")
                        else:
                            stats.add("forwarded")
                            stats.add("forwarded_bytes", sent)

            current = monotonic()
            if current >= next_report:
                output(stats.format("periodic"))
                next_report = current + STATS_INTERVAL_S
    finally:
        output(stats.format("final"))
    return stats


def _install_signal_handlers(stopping: threading.Event) -> None:
    def request_stop(_signum: int, _frame: object) -> None:
        stopping.set()

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, request_stop)


def _parse_args(argv: Sequence[str] | None) -> None:
    parser = argparse.ArgumentParser(
        description="Relay the fixed Go2 front-camera RTP stream to Robot Scope.",
        epilog="Interfaces, addresses and ports are fixed in the audited script.",
    )
    parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    _parse_args(argv)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise RelaySetupError("refusing to run as root; use the unitree service user")

    config = RelayConfig()
    stopping = threading.Event()
    _install_signal_handlers(stopping)
    receiver: socket.socket | None = None
    sender: socket.socket | None = None
    try:
        receiver = _make_receiver_socket(config)
        sender = _make_sender_socket(config)
        print(
            "[Robot Scope Go2 camera relay] ready "
            f"{config.interface}/{config.interface_ip} "
            f"{config.source_ip} -> {config.multicast_address}:{config.input_port} "
            f"copy {config.relay_ip}:{config.relay_port} -> "
            f"{config.dashboard_ip}:{config.dashboard_port}",
            flush=True,
        )
        run_relay(receiver, sender, config, stopping)
        return 0
    finally:
        if sender is not None:
            sender.close()
        if receiver is not None:
            receiver.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RelayError as exc:
        print(
            f"Robot Scope Go2 camera relay failed: {exc}",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(2) from exc
