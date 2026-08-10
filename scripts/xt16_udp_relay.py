#!/usr/bin/env python3
"""Passively copy the lab XT16 UDP stream from the Go2 Jetson to Robot Scope.

The relay deliberately does not bind UDP port 2368.  It observes packets already
addressed to the Go2-mounted Jetson with a non-promiscuous Linux packet socket,
validates the complete fixed lab contract, and sends a new UDP copy to the
Robot Scope Jetson.  The LiDAR destination and the original local receiver are
therefore left unchanged.
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


ETH_P_IP = 0x0800
PACKET_HOST = 0
MAX_CAPTURE_BYTES = 2048
SOCKET_TIMEOUT_S = 0.25
STATS_INTERVAL_S = 5.0
MAX_COUNTER = (1 << 63) - 1

# Fixed, measured lab contract.  These values are intentionally not read from
# environment variables or command-line options.
CAPTURE_INTERFACE = "eth0"
XT16_SOURCE_IP = "192.168.123.20"
XT16_SOURCE_PORT = 10000
LOCAL_RECEIVER_IP = "192.168.123.18"
XT16_DESTINATION_PORT = 2368
ROBOT_SCOPE_JETSON_IP = "192.168.123.99"
ROBOT_SCOPE_JETSON_PORT = 2368
XT16_PAYLOAD_LENGTH = 568
XT16_HEADER = bytes.fromhex("eeff06010000100801040201")

REJECT_REASONS = (
    "packet_type",
    "ip_short",
    "ip_header",
    "ip_checksum",
    "ip_fragment",
    "ip_protocol",
    "ip_length",
    "ip_address",
    "udp_header",
    "udp_port",
    "udp_length",
    "xt16_length",
    "xt16_header",
)


class RelayError(RuntimeError):
    """Base class for an expected relay failure."""


class RelaySetupError(RelayError):
    """Raised when the process cannot safely own the required sockets."""


class RelayRuntimeError(RelayError):
    """Raised when an established capture socket stops working."""


class PacketRejected(ValueError):
    """A packet that does not match the fixed XT16 stream contract."""

    def __init__(self, reason: str) -> None:
        if reason not in REJECT_REASONS:
            raise ValueError("unknown packet rejection reason")
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class RelayConfig:
    interface: str = CAPTURE_INTERFACE
    source_ip: str = XT16_SOURCE_IP
    source_port: int = XT16_SOURCE_PORT
    local_ip: str = LOCAL_RECEIVER_IP
    local_port: int = XT16_DESTINATION_PORT
    forward_ip: str = ROBOT_SCOPE_JETSON_IP
    forward_port: int = ROBOT_SCOPE_JETSON_PORT

    @property
    def forward_address(self) -> tuple[str, int]:
        return (self.forward_ip, self.forward_port)


@dataclass(frozen=True)
class ParsedPacket:
    payload: bytes
    sequence: int


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
    rejected: dict[str, int] = field(
        default_factory=lambda: {reason: 0 for reason in REJECT_REASONS}
    )
    _last_sequence: int | None = None

    def add(self, name: str, increment: int = 1) -> None:
        setattr(self, name, _saturating_add(getattr(self, name), increment))

    def reject(self, reason: str) -> None:
        if reason not in self.rejected:
            raise ValueError("unknown packet rejection reason")
        self.rejected[reason] = _saturating_add(self.rejected[reason])

    def observe_sequence(self, sequence: int) -> None:
        previous = self._last_sequence
        if previous is None:
            self._last_sequence = sequence
            return
        delta = (sequence - previous) & 0xFFFFFFFF
        if delta == 0:
            self.sequence_duplicates = _saturating_add(self.sequence_duplicates)
        elif delta < 0x80000000:
            if delta > 1:
                self.sequence_lost = _saturating_add(
                    self.sequence_lost, delta - 1
                )
            self._last_sequence = sequence
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
            f"[Robot Scope XT16 relay] {label} captured={self.captured} "
            f"accepted={self.accepted} forwarded={self.forwarded} "
            f"bytes={self.forwarded_bytes} send_errors={self.send_errors} "
            f"seq_lost={self.sequence_lost} "
            f"seq_duplicate={self.sequence_duplicates} "
            f"seq_reordered={self.sequence_reordered} "
            f"rejected={rejected_total}({details})"
        )


def _reject(reason: str) -> NoReturn:
    raise PacketRejected(reason)


def _internet_checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    words = struct.unpack(f"!{len(data) // 2}H", data)
    total = sum(words)
    total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def parse_xt16_ipv4_udp(packet: bytes, config: RelayConfig) -> ParsedPacket:
    """Return a validated XT16 payload from one AF_PACKET/SOCK_DGRAM frame."""

    if len(packet) < 20:
        _reject("ip_short")

    version = packet[0] >> 4
    header_length = (packet[0] & 0x0F) * 4
    if version != 4 or header_length != 20:
        _reject("ip_header")
    if _internet_checksum(packet[:header_length]) != 0:
        _reject("ip_checksum")

    fragment = struct.unpack_from("!H", packet, 6)[0]
    if fragment & 0x3FFF:
        _reject("ip_fragment")
    if packet[9] != socket.IPPROTO_UDP:
        _reject("ip_protocol")

    total_length = struct.unpack_from("!H", packet, 2)[0]
    if total_length < header_length + 8 or len(packet) != total_length:
        _reject("ip_length")

    if (
        packet[12:16] != socket.inet_aton(config.source_ip)
        or packet[16:20] != socket.inet_aton(config.local_ip)
    ):
        _reject("ip_address")

    udp_offset = header_length
    if len(packet) < udp_offset + 8:
        _reject("udp_header")
    source_port, destination_port, udp_length = struct.unpack_from(
        "!HHH", packet, udp_offset
    )
    if source_port != config.source_port or destination_port != config.local_port:
        _reject("udp_port")
    if udp_length < 8 or udp_length != total_length - header_length:
        _reject("udp_length")

    payload = packet[udp_offset + 8 : total_length]
    if len(payload) != XT16_PAYLOAD_LENGTH:
        _reject("xt16_length")
    if not payload.startswith(XT16_HEADER):
        _reject("xt16_header")

    sequence = int.from_bytes(payload[-4:], "little", signed=False)
    return ParsedPacket(payload=payload, sequence=sequence)


def _make_capture_socket(config: RelayConfig) -> socket.socket:
    af_packet = getattr(socket, "AF_PACKET", None)
    if not sys.platform.startswith("linux") or af_packet is None:
        raise RelaySetupError("Linux AF_PACKET support is required")

    protocol = socket.htons(ETH_P_IP)
    capture: socket.socket | None = None
    try:
        capture = socket.socket(af_packet, socket.SOCK_DGRAM, protocol)
        capture.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        capture.bind((config.interface, protocol))
        capture.settimeout(SOCKET_TIMEOUT_S)
        return capture
    except (OSError, ValueError) as exc:
        if capture is not None:
            capture.close()
        raise RelaySetupError(
            f"cannot capture IPv4 on {config.interface}; "
            "verify the interface and CAP_NET_RAW"
        ) from exc


def _make_sender_socket(config: RelayConfig) -> socket.socket:
    sender: socket.socket | None = None
    try:
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sender.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)
        # An exact local bind proves this host still owns .18 and fixes the
        # relayed source address without raw-IP spoofing.
        sender.bind((config.local_ip, 0))
        return sender
    except OSError as exc:
        if sender is not None:
            sender.close()
        raise RelaySetupError(
            f"cannot own relay source address {config.local_ip}"
        ) from exc


def run_relay(
    capture: socket.socket,
    sender: socket.socket,
    config: RelayConfig,
    stopping: threading.Event,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    output: Callable[[str], None] = lambda line: print(line, flush=True),
) -> RelayStats:
    """Copy valid packets until ``stopping`` is set."""

    stats = RelayStats()
    next_report = monotonic() + STATS_INTERVAL_S
    try:
        while not stopping.is_set():
            try:
                packet, address = capture.recvfrom(MAX_CAPTURE_BYTES)
            except socket.timeout:
                packet = None
                address = ()
            except InterruptedError:
                continue
            except OSError as exc:
                if stopping.is_set():
                    break
                raise RelayRuntimeError("packet capture socket failed") from exc

            if packet is not None:
                stats.add("captured")
                packet_type = address[2] if len(address) >= 3 else None
                if packet_type != PACKET_HOST:
                    stats.reject("packet_type")
                else:
                    try:
                        parsed = parse_xt16_ipv4_udp(packet, config)
                    except PacketRejected as exc:
                        stats.reject(exc.reason)
                    else:
                        stats.add("accepted")
                        stats.observe_sequence(parsed.sequence)
                        try:
                            sent = sender.sendto(parsed.payload, config.forward_address)
                        except OSError:
                            stats.add("send_errors")
                        else:
                            if sent != len(parsed.payload):
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
        description="Relay the fixed 192.168.123.20 -> .18 XT16 stream to .99.",
        epilog="Operational addresses and ports are fixed in the audited script.",
    )
    parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    _parse_args(argv)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise RelaySetupError(
            "refusing to run as root; use the unitree user with CAP_NET_RAW"
        )

    config = RelayConfig()
    stopping = threading.Event()
    _install_signal_handlers(stopping)
    capture: socket.socket | None = None
    sender: socket.socket | None = None
    try:
        capture = _make_capture_socket(config)
        sender = _make_sender_socket(config)
        print(
            "[Robot Scope XT16 relay] ready "
            f"{config.interface} {config.source_ip}:{config.source_port} -> "
            f"{config.local_ip}:{config.local_port} copy -> "
            f"{config.forward_ip}:{config.forward_port}",
            flush=True,
        )
        run_relay(capture, sender, config, stopping)
        return 0
    finally:
        if sender is not None:
            sender.close()
        if capture is not None:
            capture.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RelayError as exc:
        print(f"Robot Scope XT16 relay failed: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(2) from exc
