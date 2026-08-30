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
SCRIPT = ROOT / "scripts" / "go2_camera_rtp_relay.py"
SPEC = importlib.util.spec_from_file_location("go2_camera_rtp_relay", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
relay = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = relay
SPEC.loader.exec_module(relay)


def make_rtp(
    *,
    sequence=7,
    timestamp=1234,
    ssrc=0x9277F21B,
    payload_type=relay.RTP_PAYLOAD_TYPE_H264,
    h264=b"\x67\x64\x10\x28",
    first=0x80,
):
    return (
        bytes((first, payload_type))
        + struct.pack("!HII", sequence, timestamp, ssrc)
        + h264
    )


class PacketValidationTests(unittest.TestCase):
    def setUp(self):
        self.config = relay.RelayConfig()
        self.source = (relay.GO2_SOURCE_IP, 49365)

    def assert_rejected(self, packet, reason, source=None):
        with self.assertRaises(relay.PacketRejected) as raised:
            relay.parse_go2_camera_rtp(
                packet,
                self.source if source is None else source,
                self.config,
            )
        self.assertEqual(raised.exception.reason, reason)

    def test_fixed_field_contract_and_measured_packet_are_accepted(self):
        self.assertEqual(
            self.config,
            relay.RelayConfig(
                interface="eth0",
                interface_ip="192.168.123.18",
                source_ip="192.168.123.161",
                multicast_address="230.1.1.1",
                input_port=1720,
                relay_ip="192.168.50.30",
                relay_port=46120,
                dashboard_ip="192.168.50.10",
                dashboard_port=1720,
            ),
        )
        packet = bytes.fromhex("8060f776b042a86e9277f21b") + b"\x7c\x85frame"
        parsed = relay.parse_go2_camera_rtp(packet, self.source, self.config)
        self.assertEqual(parsed.packet, packet)
        self.assertEqual(parsed.sequence, 0xF776)
        self.assertEqual(parsed.ssrc, 0x9277F21B)

    def test_only_fixed_go2_source_is_accepted(self):
        packet = make_rtp()
        self.assert_rejected(packet, "source", ("192.168.123.160", 49365))
        self.assert_rejected(packet, "source", (relay.GO2_SOURCE_IP, 0))
        self.assert_rejected(packet, "source", ())

    def test_size_version_and_payload_type_are_strict(self):
        self.assert_rejected(b"short", "size")
        self.assert_rejected(
            make_rtp() + b"x" * relay.MAX_RTP_PACKET_BYTES,
            "size",
        )
        self.assert_rejected(make_rtp(first=0x40), "version")
        self.assert_rejected(make_rtp(payload_type=97), "payload_type")

    def test_header_extensions_and_padding_are_bounded(self):
        extended = (
            bytes((0x90, relay.RTP_PAYLOAD_TYPE_H264))
            + struct.pack("!HII", 9, 22, 33)
            + b"\xbe\xde\x00\x01"
            + b"abcd"
            + b"\x67payload"
        )
        parsed = relay.parse_go2_camera_rtp(extended, self.source, self.config)
        self.assertEqual(parsed.sequence, 9)

        padded = make_rtp(first=0xA0, h264=b"\x67data") + b"\x00\x02"
        self.assertEqual(
            relay.parse_go2_camera_rtp(padded, self.source, self.config).packet,
            padded,
        )
        self.assert_rejected(make_rtp(first=0x90), "header")
        self.assert_rejected(make_rtp(first=0xA0, h264=b"\x67\x00"), "header")

    def test_h264_single_stap_a_and_fu_a_packets_are_validated(self):
        for payload in (
            b"\x65whole",
            b"\x78\x00\x03\x67ab\x00\x02\x68c",
            b"\x7c\x85fragment",
            b"\x7c\x45fragment",
        ):
            relay.parse_go2_camera_rtp(
                make_rtp(h264=payload), self.source, self.config
            )

        for payload in (
            b"\x00bad",
            b"\x79unsupported",
            b"\x78\x00\x08short",
            b"\x7c\x85",
            b"\x7c\xc5bad-flags",
        ):
            self.assert_rejected(make_rtp(h264=payload), "h264")


class FakeReceiver:
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

    def send(self, packet):
        self.calls.append(packet)
        if self.fail:
            raise OSError("simulated send failure")
        return len(packet)


class RelayLoopTests(unittest.TestCase):
    def test_only_valid_go2_rtp_is_forwarded(self):
        stopping = threading.Event()
        valid = make_rtp(sequence=42, h264=b"\x7c\x85frame")
        invalid = make_rtp(payload_type=97)
        receiver = FakeReceiver(
            [
                (invalid, (relay.GO2_SOURCE_IP, 49365)),
                (valid, (relay.GO2_SOURCE_IP, 49365)),
            ],
            stopping,
        )
        sender = FakeSender()
        lines = []
        stats = relay.run_relay(
            receiver,
            sender,
            relay.RelayConfig(),
            stopping,
            monotonic=lambda: 0.0,
            output=lines.append,
        )

        self.assertEqual(stats.captured, 2)
        self.assertEqual(stats.accepted, 1)
        self.assertEqual(stats.forwarded, 1)
        self.assertEqual(stats.rejected["payload_type"], 1)
        self.assertEqual(sender.calls, [valid])
        self.assertEqual(len(lines), 1)
        self.assertIn("final", lines[0])

    def test_send_failure_is_counted_without_forward_success(self):
        stopping = threading.Event()
        valid = make_rtp(h264=b"\x7c\x85frame")
        stats = relay.run_relay(
            FakeReceiver(
                [(valid, (relay.GO2_SOURCE_IP, 49365))], stopping
            ),
            FakeSender(fail=True),
            relay.RelayConfig(),
            stopping,
            monotonic=lambda: 0.0,
            output=lambda _line: None,
        )
        self.assertEqual(stats.accepted, 1)
        self.assertEqual(stats.forwarded, 0)
        self.assertEqual(stats.send_errors, 1)

    def test_sequence_and_ssrc_statistics_are_bounded(self):
        stats = relay.RelayStats()
        packets = (
            relay.ParsedRtp(b"a", 0xFFFE, 1, 4),
            relay.ParsedRtp(b"b", 0, 2, 4),
            relay.ParsedRtp(b"c", 0, 3, 4),
            relay.ParsedRtp(b"d", 0xFFFF, 4, 4),
            relay.ParsedRtp(b"e", 8, 5, 5),
        )
        for packet in packets:
            stats.observe(packet)
        self.assertEqual(stats.sequence_lost, 1)
        self.assertEqual(stats.sequence_duplicates, 1)
        self.assertEqual(stats.sequence_reordered, 1)
        self.assertEqual(stats.ssrc_changes, 1)
        stats.forwarded = relay.MAX_COUNTER
        stats.add("forwarded")
        self.assertEqual(stats.forwarded, relay.MAX_COUNTER)

    def test_rejection_summary_uses_only_fixed_categories(self):
        stats = relay.RelayStats()
        stats.reject("h264")
        self.assertIn("rejected=1(h264:1)", stats.format("periodic"))
        with self.assertRaises(ValueError):
            stats.reject("192.168.50.99")


class ProcessContractTests(unittest.TestCase):
    def test_operational_arguments_are_rejected(self):
        with mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit) as raised:
                relay._parse_args(["--dashboard-ip", "127.0.0.1"])
        self.assertEqual(raised.exception.code, 2)

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

    def test_receiver_joins_only_fixed_group_on_fixed_interface_ip(self):
        fake_socket = mock.Mock()
        with (
            mock.patch.object(relay.socket, "if_nametoindex", return_value=3),
            mock.patch.object(
                relay.socket, "socket", return_value=fake_socket
            ) as constructor,
        ):
            receiver = relay._make_receiver_socket(relay.RelayConfig())
        self.assertIs(receiver, fake_socket)
        constructor.assert_called_once_with(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
        )
        fake_socket.bind.assert_called_once_with(("", relay.GO2_CAMERA_PORT))
        membership = socket.inet_aton(relay.GO2_MULTICAST_ADDRESS) + socket.inet_aton(
            relay.CAPTURE_INTERFACE_IP
        )
        self.assertIn(
            mock.call(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership),
            fake_socket.setsockopt.call_args_list,
        )

    def test_sender_owns_fixed_wireless_ip_and_connects_fixed_peer(self):
        fake_socket = mock.Mock()
        with mock.patch.object(relay.socket, "socket", return_value=fake_socket):
            sender = relay._make_sender_socket(relay.RelayConfig())
        self.assertIs(sender, fake_socket)
        fake_socket.bind.assert_called_once_with(
            (relay.RELAY_SOURCE_IP, relay.RELAY_SOURCE_PORT)
        )
        fake_socket.connect.assert_called_once_with(
            (relay.DASHBOARD_IP, relay.DASHBOARD_PORT)
        )

    def test_socket_ownership_failures_are_fail_closed(self):
        fake_receiver = mock.Mock()
        fake_receiver.bind.side_effect = OSError("unavailable")
        with (
            mock.patch.object(relay.socket, "if_nametoindex", return_value=3),
            mock.patch.object(relay.socket, "socket", return_value=fake_receiver),
        ):
            with self.assertRaises(relay.RelaySetupError):
                relay._make_receiver_socket(relay.RelayConfig())
        fake_receiver.close.assert_called_once_with()

        fake_sender = mock.Mock()
        fake_sender.bind.side_effect = OSError("unavailable")
        with mock.patch.object(relay.socket, "socket", return_value=fake_sender):
            with self.assertRaises(relay.RelaySetupError):
                relay._make_sender_socket(relay.RelayConfig())
        fake_sender.close.assert_called_once_with()

    def test_root_execution_is_refused_before_socket_setup(self):
        with mock.patch.object(relay.os, "geteuid", return_value=0):
            with self.assertRaises(relay.RelaySetupError):
                relay.main([])

    def test_source_has_no_configurable_network_or_shell_surface(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("sender.send(", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("SO_REUSEPORT", source)
        self.assertNotIn("CAP_NET_ADMIN", source)

    def test_service_is_non_root_capability_free_and_manual_by_default(self):
        unit = (
            ROOT / "deploy" / "robot-scope-go2-camera-relay.service.example"
        ).read_text(encoding="utf-8")
        self.assertIn("User=unitree", unit)
        self.assertIn("CapabilityBoundingSet=\n", unit)
        self.assertIn("RestrictAddressFamilies=AF_INET", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("StartLimitIntervalSec=0", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertIn("WorkingDirectory=/", unit)
        self.assertIn(
            "ExecStart=/usr/bin/python3 "
            "/usr/local/libexec/robot-scope/go2_camera_rtp_relay.py",
            unit,
        )
        self.assertIn("ProtectHome=true", unit)
        self.assertNotIn("AmbientCapabilities=", unit)
        self.assertNotIn("CAP_NET_RAW", unit)
        self.assertNotIn("CAP_NET_ADMIN", unit)
        self.assertNotIn("User=root", unit)


if __name__ == "__main__":
    unittest.main()
