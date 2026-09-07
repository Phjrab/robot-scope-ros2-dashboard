#!/usr/bin/env python3
"""Count bounded XT16-related UDP header tuples without capturing payloads."""

from __future__ import annotations

import socket
import struct
import sys
import time
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Sequence


ETH_P_IP = 0x0800
CAPTURE_INTERFACE = "eth0"
EXPECTED_XT16_SOURCE_IP = "192.168.123.20"
EXPECTED_RECEIVER_PORT = 2368
CAPTURE_DURATION_S = 8.0
MAX_RELEVANT_PACKETS = 40
MAX_CAPTURE_BYTES = 2048
MAX_DISTINCT_TUPLES = 16
SOCKET_TIMEOUT_S = 0.25


@dataclass(frozen=True, order=True)
class UdpHeaderTuple:
    source_ip: str
    source_port: int
    destination_ip: str
    destination_port: int
    payload_length: int
    packet_type: int


def parse_relevant_udp_header(
    packet: bytes, packet_type: int
) -> UdpHeaderTuple | None:
    """Return only a validated relevant IPv4/UDP header; never retain payload."""

    if len(packet) < 28:
        return None
    version = packet[0] >> 4
    header_length = (packet[0] & 0x0F) * 4
    if version != 4 or header_length < 20 or header_length > 60:
        return None
    if len(packet) < header_length + 8 or packet[9] != socket.IPPROTO_UDP:
        return None
    total_length = struct.unpack_from("!H", packet, 2)[0]
    if total_length < header_length + 8 or total_length > len(packet):
        return None
    source_port, destination_port, udp_length = struct.unpack_from(
        "!HHH", packet, header_length
    )
    if udp_length < 8 or udp_length > total_length - header_length:
        return None
    source_ip = socket.inet_ntoa(packet[12:16])
    destination_ip = socket.inet_ntoa(packet[16:20])
    if (
        source_ip != EXPECTED_XT16_SOURCE_IP
        and destination_port != EXPECTED_RECEIVER_PORT
    ):
        return None
    return UdpHeaderTuple(
        source_ip=source_ip,
        source_port=source_port,
        destination_ip=destination_ip,
        destination_port=destination_port,
        payload_length=udp_length - 8,
        packet_type=packet_type,
    )


def collect_headers(
    *,
    socket_factory: Callable[..., socket.socket] = socket.socket,
    monotonic: Callable[[], float] = time.monotonic,
) -> tuple[int, int, Counter[UdpHeaderTuple], int]:
    """Collect bounded header counts from one non-promiscuous packet socket."""

    af_packet = getattr(socket, "AF_PACKET", None)
    if not isinstance(af_packet, int):
        raise OSError("Linux AF_PACKET is unavailable")
    capture = socket_factory(
        af_packet,
        socket.SOCK_DGRAM,
        socket.htons(ETH_P_IP),
    )
    inspected = 0
    relevant = 0
    overflow = 0
    headers: Counter[UdpHeaderTuple] = Counter()
    try:
        capture.bind((CAPTURE_INTERFACE, ETH_P_IP))
        capture.settimeout(SOCKET_TIMEOUT_S)
        deadline = monotonic() + CAPTURE_DURATION_S
        while relevant < MAX_RELEVANT_PACKETS and monotonic() < deadline:
            try:
                packet, address = capture.recvfrom(MAX_CAPTURE_BYTES)
            except socket.timeout:
                continue
            inspected += 1
            packet_type = int(address[2]) if len(address) >= 3 else -1
            header = parse_relevant_udp_header(packet, packet_type)
            if header is None:
                continue
            relevant += 1
            if header in headers or len(headers) < MAX_DISTINCT_TUPLES:
                headers[header] += 1
            else:
                overflow += 1
    finally:
        capture.close()
    return inspected, relevant, headers, overflow


def main(argv: Sequence[str] | None = None) -> int:
    options = list(sys.argv[1:] if argv is None else argv)
    if options:
        print("[Robot Scope] XT16 header audit accepts no arguments", file=sys.stderr)
        return 2
    try:
        inspected, relevant, headers, overflow = collect_headers()
    except PermissionError:
        print(
            "[Robot Scope] XT16 header audit requires CAP_NET_RAW (run with sudo)",
            file=sys.stderr,
        )
        return 77
    except OSError:
        print("[Robot Scope] XT16 header audit could not open eth0", file=sys.stderr)
        return 69

    print(
        "[Robot Scope XT16 header audit] "
        f"interface={CAPTURE_INTERFACE} inspected={inspected} relevant={relevant}"
    )
    for header, count in sorted(headers.items()):
        print(
            f"{header.source_ip}:{header.source_port} -> "
            f"{header.destination_ip}:{header.destination_port} "
            f"payload={header.payload_length} packet_type={header.packet_type} "
            f"count={count}"
        )
    if overflow:
        print(f"additional_distinct_tuple_packets={overflow}")
    if relevant == 0:
        print("no XT16-source or UDP/2368 headers observed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
