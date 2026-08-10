import importlib.util
import signal
import socket
import struct
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "xt16_udp_relay.py"
SPEC = importlib.util.spec_from_file_location("xt16_udp_relay", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
relay = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = relay
SPEC.loader.exec_module(relay)

MEASURED_XT16_HEADER = bytes.fromhex("eeff06010000100801040201")


def make_payload(sequence=7):
    payload = bytearray(relay.XT16_PAYLOAD_LENGTH)
    payload[: len(MEASURED_XT16_HEADER)] = MEASURED_XT16_HEADER
    payload[-4:] = int(sequence).to_bytes(4, "little")
    return bytes(payload)


def checksum(data):
    if len(data) % 2:
        data += b"\x00"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def make_packet(
    *,
    payload=None,
    source_ip=relay.XT16_SOURCE_IP,
    destination_ip=relay.LOCAL_RECEIVER_IP,
    source_port=relay.XT16_SOURCE_PORT,
    destination_port=relay.XT16_DESTINATION_PORT,
    protocol=socket.IPPROTO_UDP,
    fragment=0x4000,
    ihl_words=5,
    total_length=None,
    udp_length=None,
):
    payload = make_payload() if payload is None else payload
    udp_length = 8 + len(payload) if udp_length is None else udp_length
    udp = struct.pack(
        "!HHHH", source_port, destination_port, udp_length, 0
    ) + payload
    header_size = ihl_words * 4
    total_length = header_size + len(udp) if total_length is None else total_length
    ip = bytearray(header_size)
    ip[0] = (4 << 4) | ihl_words
    struct.pack_into("!H", ip, 2, total_length)
    struct.pack_into("!H", ip, 6, fragment)
    ip[8] = 64
    ip[9] = protocol
    ip[12:16] = socket.inet_aton(source_ip)
    ip[16:20] = socket.inet_aton(destination_ip)
    struct.pack_into("!H", ip, 10, checksum(bytes(ip)))
    return bytes(ip) + udp


class PacketParserTests(unittest.TestCase):
    def setUp(self):
        self.config = relay.RelayConfig()

    def assert_rejected(self, packet, reason):
        with self.assertRaises(relay.PacketRejected) as raised:
            relay.parse_xt16_ipv4_udp(packet, self.config)
        self.assertEqual(raised.exception.reason, reason)

    def test_exact_measured_xt16_packet_is_accepted(self):
        self.assertEqual(relay.XT16_HEADER, MEASURED_XT16_HEADER)
        self.assertEqual(
            self.config,
            relay.RelayConfig(
                interface="eth0",
                source_ip="192.168.123.20",
                source_port=10000,
                local_ip="192.168.123.18",
                local_port=2368,
                forward_ip="192.168.123.99",
                forward_port=2368,
            ),
        )
        parsed = relay.parse_xt16_ipv4_udp(
            make_packet(payload=make_payload(0x78563412)), self.config
        )
        self.assertEqual(parsed.sequence, 0x78563412)
        self.assertEqual(parsed.payload, make_payload(0x78563412))

    def test_ip_contract_is_strict(self):
        self.assert_rejected(b"short", "ip_short")
        self.assert_rejected(make_packet(ihl_words=6), "ip_header")
        damaged = bytearray(make_packet())
        damaged[8] ^= 1
        self.assert_rejected(bytes(damaged), "ip_checksum")
        self.assert_rejected(make_packet(fragment=0x2000), "ip_fragment")
        self.assert_rejected(make_packet(fragment=0x4001), "ip_fragment")
        self.assert_rejected(make_packet(protocol=socket.IPPROTO_TCP), "ip_protocol")
        self.assert_rejected(make_packet(total_length=595), "ip_length")

    def test_only_the_measured_source_and_local_destination_are_accepted(self):
        self.assert_rejected(
            make_packet(source_ip="192.168.123.21"), "ip_address"
        )
        self.assert_rejected(
            make_packet(destination_ip="192.168.123.99"), "ip_address"
        )

    def test_udp_ports_and_lengths_are_strict(self):
        self.assert_rejected(make_packet(source_port=9999), "udp_port")
        self.assert_rejected(make_packet(destination_port=2369), "udp_port")
        self.assert_rejected(make_packet(udp_length=575), "udp_length")

    def test_xt16_payload_length_and_header_are_strict(self):
        short_payload = make_payload()[:-1]
        self.assert_rejected(make_packet(payload=short_payload), "xt16_length")
        bad_header = bytearray(make_payload())
        bad_header[0] = 0
        self.assert_rejected(make_packet(payload=bytes(bad_header)), "xt16_header")
        bad_model = bytearray(make_payload())
        bad_model[6] = 32
        self.assert_rejected(make_packet(payload=bytes(bad_model)), "xt16_header")


class FakeCapture:
    def __init__(self, frames, stopping):
        self.frames = list(frames)
        self.stopping = stopping

    def recvfrom(self, _size):
        frame = self.frames.pop(0)
        if not self.frames:
            self.stopping.set()
        return frame


class FakeSender:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = []

    def sendto(self, payload, address):
        self.calls.append((payload, address))
        if self.fail:
            raise OSError("simulated send failure")
        return len(payload)


class RelayLoopTests(unittest.TestCase):
    def test_only_packet_host_valid_frames_are_forwarded_with_sendto(self):
        stopping = threading.Event()
        valid = make_packet(payload=make_payload(42))
        capture = FakeCapture(
            [
                (valid, (relay.CAPTURE_INTERFACE, 0, 4)),
                (valid, (relay.CAPTURE_INTERFACE, 0, relay.PACKET_HOST)),
            ],
            stopping,
        )
        sender = FakeSender()
        lines = []
        stats = relay.run_relay(
            capture,
            sender,
            relay.RelayConfig(),
            stopping,
            monotonic=lambda: 0.0,
            output=lines.append,
        )
        self.assertEqual(stats.captured, 2)
        self.assertEqual(stats.accepted, 1)
        self.assertEqual(stats.forwarded, 1)
        self.assertEqual(stats.rejected["packet_type"], 1)
        self.assertEqual(
            sender.calls,
            [(make_payload(42), (relay.ROBOT_SCOPE_JETSON_IP, 2368))],
        )
        self.assertEqual(len(lines), 1)
        self.assertIn("final", lines[0])

    def test_send_error_is_counted_without_forward_success(self):
        stopping = threading.Event()
        capture = FakeCapture(
            [
                (
                    make_packet(),
                    (relay.CAPTURE_INTERFACE, 0, relay.PACKET_HOST),
                )
            ],
            stopping,
        )
        stats = relay.run_relay(
            capture,
            FakeSender(fail=True),
            relay.RelayConfig(),
            stopping,
            monotonic=lambda: 0.0,
            output=lambda _line: None,
        )
        self.assertEqual(stats.accepted, 1)
        self.assertEqual(stats.forwarded, 0)
        self.assertEqual(stats.send_errors, 1)

    def test_sequence_gap_duplicate_wrap_and_reorder_are_bounded(self):
        stats = relay.RelayStats()
        for sequence in (0xFFFFFFFE, 0, 0, 0xFFFFFFFF, 2):
            stats.observe_sequence(sequence)
        self.assertEqual(stats.sequence_lost, 2)
        self.assertEqual(stats.sequence_duplicates, 1)
        self.assertEqual(stats.sequence_reordered, 1)
        stats.forwarded = relay.MAX_COUNTER
        stats.add("forwarded")
        self.assertEqual(stats.forwarded, relay.MAX_COUNTER)

    def test_reject_summary_has_only_fixed_categories(self):
        stats = relay.RelayStats()
        stats.reject("xt16_header")
        line = stats.format("periodic")
        self.assertIn("rejected=1(xt16_header:1)", line)
        with self.assertRaises(ValueError):
            stats.reject("192.168.123.250")

    def test_periodic_and_final_statistics_are_bounded(self):
        stopping = threading.Event()
        capture = FakeCapture(
            [
                (
                    make_packet(),
                    (relay.CAPTURE_INTERFACE, 0, relay.PACKET_HOST),
                )
            ],
            stopping,
        )
        moments = iter((0.0, relay.STATS_INTERVAL_S))
        lines = []
        relay.run_relay(
            capture,
            FakeSender(),
            relay.RelayConfig(),
            stopping,
            monotonic=lambda: next(moments),
            output=lines.append,
        )
        self.assertEqual(len(lines), 2)
        self.assertIn("periodic", lines[0])
        self.assertIn("final", lines[1])

        stats = relay.RelayStats()
        for reason in relay.REJECT_REASONS:
            stats.rejected[reason] = relay.MAX_COUNTER
        self.assertLess(len(stats.format("periodic")), 1024)


class ProcessContractTests(unittest.TestCase):
    def test_operational_arguments_are_rejected(self):
        with mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit) as raised:
                relay._parse_args(["--source-ip", "127.0.0.1"])
        self.assertEqual(raised.exception.code, 2)

    def test_signals_only_request_a_graceful_stop(self):
        stopping = threading.Event()
        handlers = {}

        def record(signum, handler):
            handlers[signum] = handler

        with mock.patch.object(relay.signal, "signal", side_effect=record):
            relay._install_signal_handlers(stopping)
        self.assertEqual(
            set(handlers), {signal.SIGTERM, signal.SIGINT, signal.SIGHUP}
        )
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        self.assertTrue(stopping.is_set())

    def test_sender_must_own_exact_local_address_and_never_connects(self):
        fake = mock.Mock()
        fake_socket = mock.Mock()
        fake.socket.return_value = fake_socket
        with mock.patch.object(relay, "socket", wraps=relay.socket) as module:
            module.socket = fake.socket
            sender = relay._make_sender_socket(relay.RelayConfig())
        self.assertIs(sender, fake_socket)
        fake_socket.bind.assert_called_once_with((relay.LOCAL_RECEIVER_IP, 0))
        fake_socket.connect.assert_not_called()

    def test_sender_ownership_failure_is_fail_closed(self):
        fake_socket = mock.Mock()
        fake_socket.bind.side_effect = OSError("address unavailable")
        with mock.patch.object(relay.socket, "socket", return_value=fake_socket):
            with self.assertRaises(relay.RelaySetupError):
                relay._make_sender_socket(relay.RelayConfig())
        fake_socket.close.assert_called_once_with()

    def test_capture_ownership_failure_is_fail_closed(self):
        fake_socket = mock.Mock()
        fake_socket.bind.side_effect = OSError("interface unavailable")
        with (
            mock.patch.object(relay.sys, "platform", "linux"),
            mock.patch.object(relay.socket, "AF_PACKET", 17, create=True),
            mock.patch.object(relay.socket, "socket", return_value=fake_socket),
        ):
            with self.assertRaises(relay.RelaySetupError):
                relay._make_capture_socket(relay.RelayConfig())
        fake_socket.close.assert_called_once_with()

    def test_source_uses_sendto_without_udp_port_reuse_or_shells(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("sender.sendto(", source)
        self.assertNotIn(".connect(", source)
        self.assertNotIn("SO_REUSE", source)
        self.assertNotIn("subprocess", source)

    def test_root_execution_is_refused_before_socket_setup(self):
        with mock.patch.object(relay.os, "geteuid", return_value=0):
            with self.assertRaises(relay.RelaySetupError):
                relay.main([])

    def test_service_has_least_privilege_packet_capture_contract(self):
        unit = (
            ROOT / "deploy" / "robot-scope-xt16-relay.service.example"
        ).read_text(encoding="utf-8")
        self.assertIn("User=unitree", unit)
        self.assertIn("CapabilityBoundingSet=CAP_NET_RAW", unit)
        self.assertIn("AmbientCapabilities=CAP_NET_RAW", unit)
        self.assertIn("RestrictAddressFamilies=AF_PACKET AF_INET", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("StartLimitIntervalSec=0", unit)
        self.assertNotIn("StartLimitBurst=", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertIn("RestartSec=2", unit)
        self.assertIn("WorkingDirectory=/", unit)
        self.assertIn(
            "ExecStart=/usr/bin/python3 "
            "/usr/local/libexec/robot-scope/xt16_udp_relay.py",
            unit,
        )
        self.assertIn("ProtectHome=true", unit)
        self.assertNotIn("ExecStart=/home/", unit)
        self.assertNotIn("ProtectProc=", unit)
        self.assertNotIn("ProcSubset=", unit)
        self.assertNotIn("CAP_NET_ADMIN", unit)
        self.assertNotIn("User=root", unit)


if __name__ == "__main__":
    unittest.main()
