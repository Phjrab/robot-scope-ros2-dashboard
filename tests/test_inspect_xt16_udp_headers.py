from __future__ import annotations

import importlib.util
import socket
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inspect_xt16_udp_headers.py"
SPEC = importlib.util.spec_from_file_location("inspect_xt16_udp_headers", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


def udp_packet(
    source_ip: str,
    source_port: int,
    destination_ip: str,
    destination_port: int,
    payload: bytes,
) -> bytes:
    udp_length = 8 + len(payload)
    total_length = 20 + udp_length
    ip = bytearray(20)
    ip[0] = 0x45
    struct.pack_into("!H", ip, 2, total_length)
    ip[9] = socket.IPPROTO_UDP
    ip[12:16] = socket.inet_aton(source_ip)
    ip[16:20] = socket.inet_aton(destination_ip)
    udp = struct.pack("!HHHH", source_port, destination_port, udp_length, 0)
    return bytes(ip) + udp + payload


class Xt16HeaderAuditTests(unittest.TestCase):
    def test_expected_source_to_changed_destination_is_reported(self) -> None:
        parsed = audit.parse_relevant_udp_header(
            udp_packet(
                "192.168.123.20",
                10000,
                "192.168.123.99",
                2368,
                b"x" * 568,
            ),
            3,
        )
        self.assertEqual(parsed.source_ip, "192.168.123.20")
        self.assertEqual(parsed.destination_ip, "192.168.123.99")
        self.assertEqual(parsed.payload_length, 568)
        self.assertEqual(parsed.packet_type, 3)

    def test_unrelated_udp_and_malformed_lengths_are_ignored(self) -> None:
        unrelated = udp_packet("192.168.123.161", 7400, "192.168.123.18", 7401, b"x")
        self.assertIsNone(audit.parse_relevant_udp_header(unrelated, 0))
        malformed = bytearray(
            udp_packet("192.168.123.20", 10000, "192.168.123.18", 2368, b"x")
        )
        struct.pack_into("!H", malformed, 24, 2048)
        self.assertIsNone(audit.parse_relevant_udp_header(bytes(malformed), 0))

    def test_script_is_fixed_bounded_and_observation_only(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('CAPTURE_INTERFACE = "eth0"', source)
        self.assertIn("CAPTURE_DURATION_S = 8.0", source)
        self.assertIn("MAX_RELEVANT_PACKETS = 40", source)
        self.assertIn("MAX_DISTINCT_TUPLES = 16", source)
        self.assertIn("socket.SOCK_DGRAM", source)
        self.assertNotIn("PACKET_ADD_MEMBERSHIP", source)
        self.assertNotIn("sendto(", source)
        self.assertNotIn("connect(", source)
        self.assertEqual(audit.main(["--interface", "wlan0"]), 2)


if __name__ == "__main__":
    unittest.main()
