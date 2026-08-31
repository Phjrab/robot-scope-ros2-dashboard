#!/usr/bin/env python3
"""Passively copy the fixed XT16 stream onto the private Wi-Fi link.

The established wired relay parser remains the single definition of the
measured XT16 IPv4/UDP payload contract.  This process adds UDP-checksum
validation and emits a new, ordinary UDP datagram through one fixed connected
peer.  It never binds the LiDAR receiver port, changes the LiDAR destination,
or enables forwarding between the sensor and management networks.
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

try:
    from xt16_udp_relay import (
        ETH_P_IP,
        MAX_CAPTURE_BYTES,
        MAX_COUNTER,
        PACKET_HOST,
        REJECT_REASONS as WIRED_REJECT_REASONS,
        XT16_DESTINATION_PORT,
        XT16_HEADER as WIRED_XT16_HEADER,
        XT16_PAYLOAD_LENGTH as WIRED_XT16_PAYLOAD_LENGTH,
        XT16_SOURCE_IP,
        XT16_SOURCE_PORT,
        PacketRejected as WiredPacketRejected,
        ParsedPacket,
        RelayConfig as WiredRelayConfig,
        parse_xt16_ipv4_udp,
    )
except ModuleNotFoundError:  # pragma: no cover - repository import fallback
    from scripts.xt16_udp_relay import (
        ETH_P_IP,
        MAX_CAPTURE_BYTES,
        MAX_COUNTER,
        PACKET_HOST,
        REJECT_REASONS as WIRED_REJECT_REASONS,
        XT16_DESTINATION_PORT,
        XT16_HEADER as WIRED_XT16_HEADER,
        XT16_PAYLOAD_LENGTH as WIRED_XT16_PAYLOAD_LENGTH,
        XT16_SOURCE_IP,
        XT16_SOURCE_PORT,
        PacketRejected as WiredPacketRejected,
        ParsedPacket,
        RelayConfig as WiredRelayConfig,
        parse_xt16_ipv4_udp,
    )


SOCKET_TIMEOUT_S = 0.25
STATS_INTERVAL_S = 5.0
MAX_REPORTED_AGE_S = 999_999.999

# Fixed dual-homed robot and dashboard contract.  These values are not exposed
# through command-line arguments or environment variables.
CAPTURE_INTERFACE = "eth0"
LOCAL_RECEIVER_IP = "192.168.123.18"
WIRELESS_SOURCE_IP = "192.168.50.30"
WIRELESS_SOURCE_PORT = 46236
DASHBOARD_IP = "192.168.50.10"
DASHBOARD_PORT = 2368

REJECT_REASONS = (*WIRED_REJECT_REASONS, "udp_checksum")
XT16_HEADER = WIRED_XT16_HEADER
XT16_PAYLOAD_LENGTH = WIRED_XT16_PAYLOAD_LENGTH


class RelayError(RuntimeError):
    """Base class for an expected wireless relay failure."""


class RelaySetupError(RelayError):
    """Raised when the process cannot safely own its fixed sockets."""


class RelayRuntimeError(RelayError):
    """Raised when an established capture socket stops working."""


class PacketRejected(ValueError):
    """A packet that does not match the complete wireless relay contract."""

    def __init__(self, reason: str) -> None:
        if reason not in REJECT_REASONS:
            raise ValueError("unknown packet rejection reason")
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, init=False)
class WirelessRelayConfig:
    """Immutable defaults for the only supported private-lab path."""

    interface: str = CAPTURE_INTERFACE
    source_ip: str = XT16_SOURCE_IP
    source_port: int = XT16_SOURCE_PORT
    local_ip: str = LOCAL_RECEIVER_IP
    local_port: int = XT16_DESTINATION_PORT
    wireless_ip: str = WIRELESS_SOURCE_IP
    wireless_port: int = WIRELESS_SOURCE_PORT
    dashboard_ip: str = DASHBOARD_IP
    dashboard_port: int = DASHBOARD_PORT

    @property
    def wired_packet_contract(self) -> WiredRelayConfig:
        return WiredRelayConfig(
            interface=self.interface,
            source_ip=self.source_ip,
            source_port=self.source_port,
            local_ip=self.local_ip,
            local_port=self.local_port,
        )

    @property
    def wireless_address(self) -> tuple[str, int]:
        return (self.wireless_ip, self.wireless_port)

    @property
    def dashboard_address(self) -> tuple[str, int]:
        return (self.dashboard_ip, self.dashboard_port)


def _saturating_add(value: int, increment: int = 1) -> int:
    return min(MAX_COUNTER, value + max(0, increment))


def _age(now: float, recorded_at: float | None) -> float | None:
    if recorded_at is None:
        return None
    return min(MAX_REPORTED_AGE_S, max(0.0, now - recorded_at))


def _format_age(value: float | None) -> str:
    return "none" if value is None else f"{value:.3f}"


@dataclass
class WirelessRelayStats:
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
    _last_accepted_at: float | None = None
    _last_forwarded_at: float | None = None

    def add(self, name: str, increment: int = 1) -> None:
        setattr(self, name, _saturating_add(getattr(self, name), increment))

    def reject(self, reason: str) -> None:
        if reason not in self.rejected:
            raise ValueError("unknown packet rejection reason")
        self.rejected[reason] = _saturating_add(self.rejected[reason])

    def accept(self, sequence: int, now: float) -> None:
        self.add("accepted")
        self._last_accepted_at = now
        self.observe_sequence(sequence)

    def forward(self, byte_count: int, now: float) -> None:
        self.add("forwarded")
        self.add("forwarded_bytes", byte_count)
        self._last_forwarded_at = now

    def observe_sequence(self, sequence: int) -> None:
        previous = self._last_sequence
        if previous is None:
            self._last_sequence = sequence
            return
        delta = (sequence - previous) & 0xFFFFFFFF
        if delta == 0:
            self.sequence_duplicates = _saturating_add(
                self.sequence_duplicates
            )
        elif delta < 0x80000000:
            if delta > 1:
                self.sequence_lost = _saturating_add(
                    self.sequence_lost, delta - 1
                )
            self._last_sequence = sequence
        else:
            self.sequence_reordered = _saturating_add(
                self.sequence_reordered
            )

    def last_accepted_age_s(self, now: float) -> float | None:
        return _age(now, self._last_accepted_at)

    def last_forwarded_age_s(self, now: float) -> float | None:
        return _age(now, self._last_forwarded_at)

    def format(self, label: str, now: float) -> str:
        rejected_total = sum(self.rejected.values())
        details = ",".join(
            f"{reason}:{self.rejected[reason]}"
            for reason in REJECT_REASONS
            if self.rejected[reason]
        ) or "none"
        accepted_age = _format_age(self.last_accepted_age_s(now))
        forwarded_age = _format_age(self.last_forwarded_age_s(now))
        return (
            f"[Robot Scope wireless XT16 relay] {label} "
            f"captured={self.captured} accepted={self.accepted} "
            f"forwarded={self.forwarded} bytes={self.forwarded_bytes} "
            f"send_errors={self.send_errors} seq_lost={self.sequence_lost} "
            f"seq_duplicate={self.sequence_duplicates} "
            f"seq_reordered={self.sequence_reordered} "
            f"last_accepted_age_s={accepted_age} "
            f"last_forwarded_age_s={forwarded_age} "
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


def _validate_udp_checksum(packet: bytes) -> None:
    """Validate a supplied IPv4 UDP checksum; zero means not supplied."""

    udp_offset = 20
    udp_length = struct.unpack_from("!H", packet, udp_offset + 4)[0]
    supplied = struct.unpack_from("!H", packet, udp_offset + 6)[0]
    if supplied == 0:
        return
    pseudo_header = (
        packet[12:20]
        + bytes((0, socket.IPPROTO_UDP))
        + struct.pack("!H", udp_length)
    )
    udp_datagram = packet[udp_offset : udp_offset + udp_length]
    if _internet_checksum(pseudo_header + udp_datagram) != 0:
        _reject("udp_checksum")


def parse_wireless_xt16_packet(
    packet: bytes, config: WirelessRelayConfig
) -> ParsedPacket:
    """Apply the unchanged wired parser plus the IPv4 UDP checksum rule."""

    try:
        parsed = parse_xt16_ipv4_udp(packet, config.wired_packet_contract)
    except WiredPacketRejected as exc:
        raise PacketRejected(exc.reason) from exc
    _validate_udp_checksum(packet)
    return parsed


def _make_capture_socket(config: WirelessRelayConfig) -> socket.socket:
    af_packet = getattr(socket, "AF_PACKET", None)
    if not sys.platform.startswith("linux") or af_packet is None:
        raise RelaySetupError("Linux AF_PACKET support is required")

    capture: socket.socket | None = None
    try:
        capture = socket.socket(
            af_packet, socket.SOCK_DGRAM, socket.htons(ETH_P_IP)
        )
        capture.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        capture.bind((config.interface, ETH_P_IP))
        capture.settimeout(SOCKET_TIMEOUT_S)
        return capture
    except (OSError, ValueError) as exc:
        if capture is not None:
            capture.close()
        raise RelaySetupError(
            f"cannot capture IPv4 on {config.interface}; "
            "verify the interface and CAP_NET_RAW"
        ) from exc


def _make_sender_socket(config: WirelessRelayConfig) -> socket.socket:
    sender: socket.socket | None = None
    try:
        sender = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
        )
        sender.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)
        sender.bind(config.wireless_address)
        sender.connect(config.dashboard_address)
        return sender
    except OSError as exc:
        if sender is not None:
            sender.close()
        raise RelaySetupError(
            "cannot own the fixed private Wi-Fi XT16 relay endpoint"
        ) from exc


def run_relay(
    capture: socket.socket,
    sender: socket.socket,
    config: WirelessRelayConfig,
    stopping: threading.Event,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    output: Callable[[str], None] = lambda line: print(line, flush=True),
) -> WirelessRelayStats:
    """Copy valid packets while tolerating transient Wi-Fi send failures."""

    stats = WirelessRelayStats()
    next_report = monotonic() + STATS_INTERVAL_S
    current = monotonic()
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

            current = monotonic()
            if packet is not None:
                stats.add("captured")
                packet_type = address[2] if len(address) >= 3 else None
                if packet_type != PACKET_HOST:
                    stats.reject("packet_type")
                else:
                    try:
                        parsed = parse_wireless_xt16_packet(packet, config)
                    except PacketRejected as exc:
                        stats.reject(exc.reason)
                    else:
                        stats.accept(parsed.sequence, current)
                        try:
                            sent = sender.send(parsed.payload)
                        except OSError:
                            stats.add("send_errors")
                        else:
                            if sent != len(parsed.payload):
                                stats.add("send_errors")
                            else:
                                stats.forward(sent, current)

            if current >= next_report:
                output(stats.format("periodic", current))
                next_report = current + STATS_INTERVAL_S
    finally:
        output(stats.format("final", current))
    return stats


def _install_signal_handlers(stopping: threading.Event) -> None:
    def request_stop(_signum: int, _frame: object) -> None:
        stopping.set()

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, request_stop)


def _parse_args(argv: Sequence[str] | None) -> None:
    parser = argparse.ArgumentParser(
        description="Relay the fixed robot-side XT16 stream over private Wi-Fi.",
        epilog="All interfaces, addresses and ports are fixed in this script.",
    )
    parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    _parse_args(argv)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise RelaySetupError(
            "refusing to run as root; use unitree with CAP_NET_RAW"
        )

    config = WirelessRelayConfig()
    stopping = threading.Event()
    _install_signal_handlers(stopping)
    capture: socket.socket | None = None
    sender: socket.socket | None = None
    try:
        capture = _make_capture_socket(config)
        sender = _make_sender_socket(config)
        print(
            "[Robot Scope wireless XT16 relay] ready "
            f"{config.interface} {config.source_ip}:{config.source_port} -> "
            f"{config.local_ip}:{config.local_port} copy from "
            f"{config.wireless_ip}:{config.wireless_port} -> "
            f"{config.dashboard_ip}:{config.dashboard_port}",
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
        print(
            f"Robot Scope wireless XT16 relay failed: {exc}",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(2) from exc
