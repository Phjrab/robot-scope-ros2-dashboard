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
WIRED_SCRIPT = ROOT / "scripts" / "xt16_udp_relay.py"
SCRIPT = ROOT / "scripts" / "xt16_wireless_udp_relay.py"
SERVICE = ROOT / "deploy" / "robot-scope-xt16-wireless-relay.service.example"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


wired = sys.modules.get("xt16_udp_relay") or load_module(
    "xt16_udp_relay", WIRED_SCRIPT
)
relay = load_module("xt16_wireless_udp_relay", SCRIPT)


def checksum(data):
    if len(data) % 2:
        data += b"\x00"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def make_payload(sequence=7):
    payload = bytearray(relay.XT16_PAYLOAD_LENGTH)
    payload[: len(relay.XT16_HEADER)] = relay.XT16_HEADER
    payload[-4:] = int(sequence).to_bytes(4, "little")
    return bytes(payload)


def make_packet(
    *,
    payload=None,
    source_ip=relay.XT16_SOURCE_IP,
    destination_ip=relay.LOCAL_RECEIVER_IP,
    source_port=relay.XT16_SOURCE_PORT,
    destination_port=relay.XT16_DESTINATION_PORT,
    fragment=0x4000,
    udp_length=None,
    udp_checksum="zero",
):
    payload = make_payload() if payload is None else payload
    udp_length = 8 + len(payload) if udp_length is None else udp_length
    udp = bytearray(
        struct.pack(
            "!HHHH", source_port, destination_port, udp_length, 0
        )
        + payload
    )
    source = socket.inet_aton(source_ip)
    destination = socket.inet_aton(destination_ip)
    if udp_checksum == "valid":
        pseudo = (
            source
            + destination
            + bytes((0, socket.IPPROTO_UDP))
            + struct.pack("!H", udp_length)
        )
        value = checksum(pseudo + bytes(udp)) or 0xFFFF
        struct.pack_into("!H", udp, 6, value)
    elif udp_checksum == "invalid":
        struct.pack_into("!H", udp, 6, 1)
    elif udp_checksum != "zero":
        raise ValueError("unknown checksum mode")

    total_length = 20 + len(udp)
    ip = bytearray(20)
    ip[0] = 0x45
    struct.pack_into("!H", ip, 2, total_length)
    struct.pack_into("!H", ip, 6, fragment)
    ip[8] = 64
    ip[9] = socket.IPPROTO_UDP
    ip[12:16] = source
    ip[16:20] = destination
    struct.pack_into("!H", ip, 10, checksum(bytes(ip)))
    return bytes(ip) + bytes(udp)


class PacketContractTests(unittest.TestCase):
    def setUp(self):
        self.config = relay.WirelessRelayConfig()

    def assert_rejected(self, packet, reason):
        with self.assertRaises(relay.PacketRejected) as raised:
            relay.parse_wireless_xt16_packet(packet, self.config)
        self.assertEqual(raised.exception.reason, reason)

    def test_all_input_and_output_values_are_fixed(self):
        self.assertEqual(self.config.interface, "eth0")
        self.assertEqual(self.config.source_ip, "192.168.123.20")
        self.assertEqual(self.config.source_port, 10000)
        self.assertEqual(self.config.local_ip, "192.168.123.18")
        self.assertEqual(self.config.local_port, 2368)
        self.assertEqual(
            self.config.wireless_address, ("192.168.50.30", 46236)
        )
        self.assertEqual(
            self.config.dashboard_address, ("192.168.50.10", 2368)
        )
        with self.assertRaises(TypeError):
            relay.WirelessRelayConfig(dashboard_ip="192.168.50.11")

    def test_exact_packet_with_zero_or_valid_udp_checksum_is_accepted(self):
        for mode in ("zero", "valid"):
            with self.subTest(mode=mode):
                parsed = relay.parse_wireless_xt16_packet(
                    make_packet(
                        payload=make_payload(0x78563412),
                        udp_checksum=mode,
                    ),
                    self.config,
                )
                self.assertEqual(parsed.sequence, 0x78563412)
                self.assertEqual(parsed.payload, make_payload(0x78563412))

    def test_invalid_supplied_udp_checksum_is_rejected(self):
        self.assert_rejected(
            make_packet(udp_checksum="invalid"), "udp_checksum"
        )

    def test_unchanged_wired_parser_still_enforces_network_contract(self):
        cases = (
            (make_packet(source_ip="192.168.123.21"), "ip_address"),
            (make_packet(destination_ip="192.168.123.19"), "ip_address"),
            (make_packet(source_port=10001), "udp_port"),
            (make_packet(destination_port=2369), "udp_port"),
            (make_packet(fragment=0x2000), "ip_fragment"),
            (make_packet(udp_length=575), "udp_length"),
            (make_packet(payload=make_payload()[:-1]), "xt16_length"),
        )
        for packet, reason in cases:
            with self.subTest(reason=reason):
                self.assert_rejected(packet, reason)

        bad_header = bytearray(make_payload())
        bad_header[0] ^= 0xFF
        self.assert_rejected(
            make_packet(payload=bytes(bad_header)), "xt16_header"
        )

    def test_ipv4_checksum_remains_enforced_by_the_wired_parser(self):
        packet = bytearray(make_packet())
        packet[8] ^= 1
        self.assert_rejected(bytes(packet), "ip_checksum")


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
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.payloads = []

    def send(self, payload):
        self.payloads.append(payload)
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return len(payload)


class RelayLoopTests(unittest.TestCase):
    def frame(self, sequence, packet_type=relay.PACKET_HOST):
        return (
            make_packet(payload=make_payload(sequence)),
            (relay.CAPTURE_INTERFACE, 0, packet_type),
        )

    def run_frames(self, frames, sender, moments=None):
        stopping = threading.Event()
        capture = FakeCapture(frames, stopping)
        values = iter(moments) if moments is not None else None
        monotonic = (lambda: next(values)) if values else (lambda: 10.0)
        lines = []
        stats = relay.run_relay(
            capture,
            sender,
            relay.WirelessRelayConfig(),
            stopping,
            monotonic=monotonic,
            output=lines.append,
        )
        return stats, lines

    def test_only_packet_host_valid_frames_are_forwarded(self):
        sender = FakeSender()
        stats, _lines = self.run_frames(
            [self.frame(40, 4), self.frame(41)], sender
        )
        self.assertEqual(stats.captured, 2)
        self.assertEqual(stats.accepted, 1)
        self.assertEqual(stats.forwarded, 1)
        self.assertEqual(stats.rejected["packet_type"], 1)
        self.assertEqual(sender.payloads, [make_payload(41)])

    def test_transient_send_failure_recovers_in_the_same_process(self):
        sender = FakeSender(
            [OSError("simulated Wi-Fi loss"), relay.XT16_PAYLOAD_LENGTH]
        )
        stats, _lines = self.run_frames(
            [self.frame(100), self.frame(101)], sender
        )
        self.assertEqual(stats.accepted, 2)
        self.assertEqual(stats.forwarded, 1)
        self.assertEqual(stats.forwarded_bytes, relay.XT16_PAYLOAD_LENGTH)
        self.assertEqual(stats.send_errors, 1)
        self.assertEqual(len(sender.payloads), 2)

    def test_short_udp_send_is_an_error_and_capture_continues(self):
        sender = FakeSender([1, relay.XT16_PAYLOAD_LENGTH])
        stats, _lines = self.run_frames(
            [self.frame(200), self.frame(201)], sender
        )
        self.assertEqual(stats.accepted, 2)
        self.assertEqual(stats.forwarded, 1)
        self.assertEqual(stats.send_errors, 1)

    def test_sequence_and_counter_accounting_is_saturating(self):
        stats = relay.WirelessRelayStats()
        for sequence in (0xFFFFFFFE, 0, 0, 0xFFFFFFFF, 2):
            stats.observe_sequence(sequence)
        self.assertEqual(stats.sequence_lost, 2)
        self.assertEqual(stats.sequence_duplicates, 1)
        self.assertEqual(stats.sequence_reordered, 1)
        stats.captured = relay.MAX_COUNTER
        stats.add("captured")
        self.assertEqual(stats.captured, relay.MAX_COUNTER)

    def test_last_accepted_and_forwarded_ages_are_explicit_and_bounded(self):
        stats = relay.WirelessRelayStats()
        self.assertIsNone(stats.last_accepted_age_s(10.0))
        self.assertIsNone(stats.last_forwarded_age_s(10.0))
        stats.accept(1, 10.0)
        stats.forward(568, 11.0)
        self.assertEqual(stats.last_accepted_age_s(12.5), 2.5)
        self.assertEqual(stats.last_forwarded_age_s(12.5), 1.5)
        self.assertEqual(stats.last_accepted_age_s(1e20), 999_999.999)
        line = stats.format("periodic", 12.5)
        self.assertIn("last_accepted_age_s=2.500", line)
        self.assertIn("last_forwarded_age_s=1.500", line)

    def test_periodic_and_final_statistics_are_bounded(self):
        stats, lines = self.run_frames(
            [self.frame(1)],
            FakeSender(),
            moments=(0.0, 0.0, relay.STATS_INTERVAL_S),
        )
        self.assertEqual(stats.forwarded, 1)
        self.assertEqual(len(lines), 2)
        self.assertIn("periodic", lines[0])
        self.assertIn("final", lines[1])
        for reason in relay.REJECT_REASONS:
            stats.rejected[reason] = relay.MAX_COUNTER
        self.assertLess(len(stats.format("periodic", 1e20)), 1200)

    def test_reject_summary_accepts_only_fixed_categories(self):
        stats = relay.WirelessRelayStats()
        stats.reject("udp_checksum")
        self.assertIn(
            "rejected=1(udp_checksum:1)", stats.format("periodic", 0.0)
        )
        with self.assertRaises(ValueError):
            stats.reject("192.168.50.250")


class ProcessContractTests(unittest.TestCase):
    def test_capture_is_non_promiscuous_packet_host_sock_dgram(self):
        fake_socket = mock.Mock()
        with (
            mock.patch.object(relay.sys, "platform", "linux"),
            mock.patch.object(relay.socket, "AF_PACKET", 17, create=True),
            mock.patch.object(
                relay.socket, "socket", return_value=fake_socket
            ) as constructor,
        ):
            capture = relay._make_capture_socket(relay.WirelessRelayConfig())
        self.assertIs(capture, fake_socket)
        constructor.assert_called_once_with(
            17, socket.SOCK_DGRAM, socket.htons(relay.ETH_P_IP)
        )
        fake_socket.bind.assert_called_once_with(("eth0", relay.ETH_P_IP))
        calls = " ".join(str(call) for call in fake_socket.mock_calls)
        self.assertNotIn("PACKET_ADD_MEMBERSHIP", calls)
        self.assertNotIn("PACKET_MR_PROMISC", calls)

    def test_sender_owns_and_connects_only_the_fixed_private_peer(self):
        fake_socket = mock.Mock()
        with mock.patch.object(
            relay.socket, "socket", return_value=fake_socket
        ) as constructor:
            sender = relay._make_sender_socket(relay.WirelessRelayConfig())
        self.assertIs(sender, fake_socket)
        constructor.assert_called_once_with(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
        )
        fake_socket.bind.assert_called_once_with(("192.168.50.30", 46236))
        fake_socket.connect.assert_called_once_with(("192.168.50.10", 2368))
        calls = " ".join(str(call) for call in fake_socket.mock_calls)
        self.assertNotIn("SO_REUSE", calls)

    def test_sender_ownership_failure_is_fail_closed(self):
        fake_socket = mock.Mock()
        fake_socket.bind.side_effect = OSError("address unavailable")
        with mock.patch.object(relay.socket, "socket", return_value=fake_socket):
            with self.assertRaises(relay.RelaySetupError):
                relay._make_sender_socket(relay.WirelessRelayConfig())
        fake_socket.close.assert_called_once_with()

    def test_operational_arguments_are_rejected(self):
        with mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit) as raised:
                relay._parse_args(["--dashboard-ip", "127.0.0.1"])
        self.assertEqual(raised.exception.code, 2)

    def test_root_execution_is_refused_before_socket_setup(self):
        with mock.patch.object(relay.os, "geteuid", return_value=0):
            with self.assertRaises(relay.RelaySetupError):
                relay.main([])

    def test_signals_only_request_graceful_stop(self):
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

    def test_source_has_no_runtime_network_override_or_payload_history(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("os.environ", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("SO_REUSE", source)
        self.assertNotIn(".sendto(", source)
        self.assertNotIn("0.0.0.0", source)
        self.assertNotIn("payloads =", source)
        self.assertNotIn("payload.hex", source)

    def test_legacy_relay_remains_a_separate_unchanged_network_path(self):
        source = WIRED_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('ROBOT_SCOPE_JETSON_IP = "192.168.123.99"', source)
        self.assertNotIn("192.168.50.30", source)
        self.assertNotIn("xt16_wireless_udp_relay", source)

    def test_service_is_disabled_by_default_and_least_privilege(self):
        unit = SERVICE.read_text(encoding="utf-8")
        self.assertIn("Installer must leave this unit disabled by default", unit)
        self.assertIn("User=unitree", unit)
        self.assertIn("Group=unitree", unit)
        self.assertIn("CapabilityBoundingSet=CAP_NET_RAW", unit)
        self.assertIn("AmbientCapabilities=CAP_NET_RAW", unit)
        self.assertIn("RestrictAddressFamilies=AF_PACKET AF_INET", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("StartLimitIntervalSec=60", unit)
        self.assertIn("StartLimitBurst=5", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertIn("RestartSec=3", unit)
        self.assertIn(
            "ExecStart=/usr/bin/python3 "
            "/usr/local/libexec/robot-scope/xt16_wireless_udp_relay.py",
            unit,
        )
        self.assertIn(
            "ConditionPathIsExecutable="
            "/usr/local/libexec/robot-scope/xt16_udp_relay.py",
            unit,
        )
        self.assertNotIn("CAP_NET_ADMIN", unit)
        self.assertNotIn("User=root", unit)
        self.assertNotIn("ExecStart=/home/", unit)


if __name__ == "__main__":
    unittest.main()
