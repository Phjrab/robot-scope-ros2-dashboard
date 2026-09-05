import hashlib
import hmac
import importlib
import math
import os
import socket
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

protocol = importlib.import_module("wireless_odom_protocol")
sender = importlib.import_module("wireless_odom_sender_foxy")
receiver = importlib.import_module("wireless_odom_receiver_humble")
readiness = importlib.import_module("check_wireless_odom_ready")

KEY = bytes(range(protocol.KEY_BYTES))
OTHER_KEY = bytes(reversed(range(protocol.KEY_BYTES)))
BOOT = uuid.UUID("12345678-1234-5678-1234-567812345678")
BASE_REALTIME = 2_000_000_000_000_000_000
BASE_MONOTONIC = 500_000_000_000


def make_sample(sequence=1, **overrides):
    values = {
        "boot_id": BOOT,
        "sequence": sequence,
        "sender_realtime_ns": BASE_REALTIME + sequence * 10_000_000,
        "sender_monotonic_ns": BASE_MONOTONIC + sequence * 10_000_000,
        "source_stamp_ns": BASE_REALTIME + sequence * 10_000_000 - 1_000_000,
        "position_xyz": (1.0, 2.0, 0.1),
        "orientation_xyzw": (0.0, 0.0, 0.0, 1.0),
        "linear_xyz": (0.1, 0.0, 0.0),
        "angular_xyz": (0.0, 0.0, 0.1),
        "pose_covariance": (0.0,) * 36,
        "twist_covariance": (0.0,) * 36,
    }
    values.update(overrides)
    return protocol.OdomEnvelope(**values)


def packet_for(sequence=1, **overrides):
    return protocol.encode_envelope(make_sample(sequence, **overrides), KEY)


def accept(core, sequence, **overrides):
    sample = make_sample(sequence, **overrides)
    return core.accept(
        protocol.encode_envelope(sample, KEY),
        received_realtime_ns=sample.sender_realtime_ns + 5_000_000,
        received_monotonic_ns=sample.sender_monotonic_ns + 5_000_000,
        clock_synchronized=True,
    )


def fake_message(stamp_ns=BASE_REALTIME):
    def vector(x=0.0, y=0.0, z=0.0):
        return types.SimpleNamespace(x=x, y=y, z=z)

    return types.SimpleNamespace(
        header=types.SimpleNamespace(
            stamp=types.SimpleNamespace(
                sec=stamp_ns // 1_000_000_000,
                nanosec=stamp_ns % 1_000_000_000,
            ),
            frame_id="odom",
        ),
        child_frame_id="base_link",
        pose=types.SimpleNamespace(
            pose=types.SimpleNamespace(
                position=vector(1.0, 2.0, 0.1),
                orientation=types.SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
            ),
            covariance=[0.0] * 36,
        ),
        twist=types.SimpleNamespace(
            twist=types.SimpleNamespace(
                linear=vector(0.1, 0.0, 0.0),
                angular=vector(0.0, 0.0, 0.1),
            ),
            covariance=[0.0] * 36,
        ),
    )


class WirelessOdomProtocolTests(unittest.TestCase):
    def test_fixed_packet_round_trip_preserves_complete_odometry(self):
        packet = packet_for()
        self.assertEqual(len(packet), 784)
        self.assertLess(len(packet), 1200)
        decoded = protocol.decode_envelope(packet, KEY)
        self.assertEqual(decoded.boot_id, BOOT)
        self.assertEqual(decoded.position_xyz, (1.0, 2.0, 0.1))
        self.assertEqual(decoded.orientation_xyzw, (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(len(decoded.pose_covariance), 36)
        self.assertEqual(len(decoded.twist_covariance), 36)

    def test_authentication_header_length_and_key_fail_closed(self):
        packet = bytearray(packet_for())
        packet[80] ^= 1
        with self.assertRaisesRegex(protocol.WirelessOdomError, "authentication"):
            protocol.decode_envelope(bytes(packet), KEY)
        with self.assertRaisesRegex(protocol.WirelessOdomError, "authentication"):
            protocol.decode_envelope(packet_for(), OTHER_KEY)
        for candidate in (b"", packet_for()[:-1], packet_for() + b"x"):
            with self.assertRaisesRegex(protocol.WirelessOdomError, "packet_length"):
                protocol.decode_envelope(candidate, KEY)
        with self.assertRaisesRegex(protocol.WirelessOdomError, "key_file"):
            protocol.encode_envelope(make_sample(), b"short")
        with self.assertRaisesRegex(protocol.WirelessOdomError, "sequence"):
            protocol.encode_envelope(make_sample(sequence=1.5), KEY)
        with self.assertRaisesRegex(protocol.WirelessOdomError, "timestamp"):
            protocol.encode_envelope(make_sample(sender_realtime_ns=1.5), KEY)

        original = packet_for()
        body = bytearray(original[: protocol._BODY.size])
        cases = (
            (0, b"BAD!", "magic"),
            (4, b"\x02", "version"),
            (5, b"\x02", "message_type"),
            (6, b"\x00\x01", "flags"),
            (8, b"wrong-sender-id!\x00", "sender_id"),
        )
        for offset, replacement, reason in cases:
            changed = bytearray(body)
            changed[offset : offset + len(replacement)] = replacement
            resigned = bytes(changed) + hmac.new(
                KEY, bytes(changed), hashlib.sha256
            ).digest()
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(protocol.WirelessOdomError, reason):
                    protocol.decode_envelope(resigned, KEY)

    def test_nonfinite_bounds_and_quaternion_fail_closed(self):
        cases = (
            ({"linear_xyz": (math.nan, 0.0, 0.0)}, "nonfinite"),
            ({"linear_xyz": (21.0, 0.0, 0.0)}, "bounds"),
            ({"angular_xyz": (0.0, 0.0, 21.0)}, "bounds"),
            ({"position_xyz": (1_000_001.0, 0.0, 0.0)}, "bounds"),
            ({"orientation_xyzw": (0.0, 0.0, 0.0, 0.0)}, "quaternion_norm"),
        )
        for overrides, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(protocol.WirelessOdomError, reason):
                    protocol.encode_envelope(make_sample(**overrides), KEY)

    def test_private_key_requires_owner_mode_size_and_no_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "odom.key"
            path.write_bytes(KEY)
            path.chmod(0o600)
            self.assertEqual(protocol.load_private_key(path), KEY)
            path.chmod(0o640)
            with self.assertRaisesRegex(protocol.WirelessOdomError, "key_file"):
                protocol.load_private_key(path)
            path.chmod(0o600)
            with mock.patch.object(protocol.os, "geteuid", return_value=os.geteuid() + 1):
                with self.assertRaisesRegex(protocol.WirelessOdomError, "key_file"):
                    protocol.load_private_key(path)
            link = Path(directory) / "linked.key"
            link.symlink_to(path)
            with self.assertRaisesRegex(protocol.WirelessOdomError, "key_file"):
                protocol.load_private_key(link)


class ReceiverCoreTests(unittest.TestCase):
    def test_five_fresh_advancing_packets_are_required(self):
        core = protocol.ReceiverCore(KEY)
        for sequence in range(1, protocol.READY_SAMPLE_COUNT + 1):
            sample = accept(core, sequence)
            status = core.snapshot(
                now_monotonic_ns=sample.sender_monotonic_ns + 10_000_000,
                clock_synchronized=True,
            )
            self.assertEqual(status["ready"], sequence == protocol.READY_SAMPLE_COUNT)

    def test_replay_reorder_loss_boot_and_transport_loss_are_bounded(self):
        core = protocol.ReceiverCore(KEY)
        accept(core, 1)
        with self.assertRaisesRegex(protocol.WirelessOdomError, "duplicate"):
            accept(core, 1)

        core = protocol.ReceiverCore(KEY)
        accept(core, 2)
        with self.assertRaisesRegex(protocol.WirelessOdomError, "reorder"):
            accept(core, 1)

        core = protocol.ReceiverCore(KEY)
        accept(core, 1)
        accept(core, 4)
        self.assertEqual(core.stats.lost, 2)
        second_boot = uuid.UUID("22345678-1234-5678-1234-567812345678")
        accept(core, 1, boot_id=second_boot)
        self.assertEqual(core.stats.boot_changes, 1)
        with self.assertRaisesRegex(protocol.WirelessOdomError, "retired_boot"):
            accept(core, 5, boot_id=BOOT)

        core.note_transport_loss()
        status = core.snapshot(
            now_monotonic_ns=BASE_MONOTONIC + 100_000_000,
            clock_synchronized=True,
        )
        self.assertFalse(status["ready"])
        self.assertEqual(status["receive_errors"], 1)

    def test_clock_stale_future_and_source_stamp_delta_fail_closed(self):
        sample = make_sample()
        packet = protocol.encode_envelope(sample, KEY)
        cases = (
            (sample.sender_realtime_ns + protocol.MAX_SOURCE_AGE_NS + 1, True, "stale"),
            (sample.sender_realtime_ns - protocol.MAX_FUTURE_SKEW_NS - 1, True, "future"),
            (sample.sender_realtime_ns, False, "clock_unsynchronized"),
        )
        for received_realtime_ns, synchronized, reason in cases:
            with self.subTest(reason=reason):
                core = protocol.ReceiverCore(KEY)
                with self.assertRaisesRegex(protocol.WirelessOdomError, reason):
                    core.accept(
                        packet,
                        received_realtime_ns=received_realtime_ns,
                        received_monotonic_ns=sample.sender_monotonic_ns + 1,
                        clock_synchronized=synchronized,
                    )
        with self.assertRaisesRegex(protocol.WirelessOdomError, "stale"):
            accept(
                protocol.ReceiverCore(KEY),
                1,
                source_stamp_ns=BASE_REALTIME - protocol.MAX_STAMP_SENDER_DELTA_NS,
            )


class FakeSocket:
    def __init__(self, *_args):
        self.calls = []
        self.closed = False

    def bind(self, address):
        self.calls.append(("bind", address))

    def connect(self, address):
        self.calls.append(("connect", address))

    def settimeout(self, timeout):
        self.calls.append(("timeout", timeout))

    def send(self, packet):
        return len(packet)

    def recv(self, _size):
        raise socket.timeout()

    def close(self):
        self.closed = True


class RuntimeContractTests(unittest.TestCase):
    def test_connected_udp_fixes_peer_and_port(self):
        for role, local_ip, peer_ip in (
            ("sender", "192.168.50.30", "192.168.50.10"),
            ("receiver", "192.168.50.10", "192.168.50.30"),
        ):
            created = []

            def factory(*args):
                endpoint = FakeSocket(*args)
                created.append(endpoint)
                return endpoint

            transport = protocol.ConnectedOdomDatagram(role, socket_factory=factory)
            self.assertEqual(created[0].calls[0], ("bind", (local_ip, 46030)))
            self.assertEqual(created[0].calls[1], ("connect", (peer_ip, 46030)))
            self.assertIsNone(transport.receive())
            transport.close()
            self.assertTrue(created[0].closed)

    def test_source_extraction_and_receiver_preserve_fixed_frames_and_stamp(self):
        message = fake_message()
        extracted = sender.extract_source_odometry(message)
        self.assertEqual(extracted.source_stamp_ns, BASE_REALTIME)
        self.assertEqual(extracted.position_xyz, (1.0, 2.0, 0.1))
        message.header.frame_id = "map"
        with self.assertRaisesRegex(protocol.WirelessOdomError, "bounds"):
            sender.extract_source_odometry(message)

        output = fake_message(1)
        sample = make_sample()
        receiver.fill_message(output, sample)
        self.assertEqual(output.header.frame_id, "odom")
        self.assertEqual(output.child_frame_id, "base_link")
        self.assertEqual(
            output.header.stamp.sec * 1_000_000_000 + output.header.stamp.nanosec,
            sample.source_stamp_ns,
        )

    def test_sender_rejects_stale_and_future_source_clock_without_rebasing(self):
        self.assertEqual(
            sender.validate_source_clock(
                BASE_REALTIME - protocol.MAX_STAMP_SENDER_DELTA_NS,
                BASE_REALTIME,
            ),
            protocol.MAX_STAMP_SENDER_DELTA_NS,
        )
        self.assertEqual(
            sender.validate_source_clock(
                BASE_REALTIME + protocol.MAX_FUTURE_SKEW_NS,
                BASE_REALTIME,
            ),
            -protocol.MAX_FUTURE_SKEW_NS,
        )
        with self.assertRaisesRegex(protocol.WirelessOdomError, "stale"):
            sender.validate_source_clock(
                BASE_REALTIME - protocol.MAX_STAMP_SENDER_DELTA_NS - 1,
                BASE_REALTIME,
            )
        with self.assertRaisesRegex(protocol.WirelessOdomError, "future"):
            sender.validate_source_clock(
                BASE_REALTIME + protocol.MAX_FUTURE_SKEW_NS + 1,
                BASE_REALTIME,
            )
        with self.assertRaisesRegex(protocol.WirelessOdomError, "stale"):
            sender.validate_source_clock(
                BASE_REALTIME - 3_788_000_000,
                BASE_REALTIME,
            )
        for invalid in (0, -1, 1.5, True, 0x10000000000000000):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(protocol.WirelessOdomError, "timestamp"):
                    sender.validate_source_clock(invalid, BASE_REALTIME)

    def test_sender_reports_source_clock_failures_without_a_rebase_path(self):
        source = (SCRIPTS / "wireless_odom_sender_foxy.py").read_text(
            encoding="utf-8"
        )
        for required in (
            "validate_source_clock(source.source_stamp_ns, sender_realtime_ns)",
            "source_stamp_age_ms=",
            "source_stale=",
            "source_future=",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "source.source_stamp_ns = sender_realtime_ns",
            "source_stamp_ns=sender_realtime_ns",
        ):
            self.assertNotIn(forbidden, source)

    def test_sender_rate_limit_bounds_the_new_150_hz_source_before_send(self):
        source = (SCRIPTS / "wireless_odom_sender_foxy.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("MIN_SEND_INTERVAL_NS = 10_000_000", source)
        rate_guard = source.index("sender_monotonic_ns - self._last_sent_monotonic_ns")
        rate_counter = source.index("self._rate_limited = self._increment")
        datagram_send = source.index("transport.send(encode_envelope(sample, key))")
        sent_clock_commit = source.index(
            "self._last_sent_monotonic_ns = sender_monotonic_ns"
        )
        self.assertLess(rate_guard, rate_counter)
        self.assertLess(rate_counter, datagram_send)
        self.assertLess(datagram_send, sent_clock_commit)

    def test_readiness_requires_fixed_frames_fresh_finite_sample(self):
        message = fake_message(BASE_REALTIME)
        self.assertEqual(
            readiness.validate_message(message, now_realtime_ns=BASE_REALTIME + 1),
            BASE_REALTIME,
        )
        message.child_frame_id = "body"
        with self.assertRaisesRegex(readiness.ReadinessError, "child frame"):
            readiness.validate_message(message, now_realtime_ns=BASE_REALTIME + 1)
        message = fake_message(BASE_REALTIME)
        message.header.stamp.nanosec = 1_000_000_000
        with self.assertRaisesRegex(readiness.ReadinessError, "timestamp"):
            readiness.validate_message(message, now_realtime_ns=BASE_REALTIME + 1)
        message = fake_message(BASE_REALTIME)
        message.twist.twist.linear.x = 21.0
        with self.assertRaisesRegex(readiness.ReadinessError, "linear velocity"):
            readiness.validate_message(message, now_realtime_ns=BASE_REALTIME + 1)

    def test_services_keys_topics_and_navigation_launcher_are_fixed(self):
        combined = "".join(
            (SCRIPTS / name).read_text(encoding="utf-8")
            for name in (
                "wireless_odom_protocol.py",
                "wireless_odom_sender_foxy.py",
                "wireless_odom_receiver_humble.py",
            )
        )
        self.assertNotIn("ROBOT_SCOPE_CONTROL_BRIDGE_KEY", combined)
        self.assertNotIn("wireless-imu.key", combined)
        self.assertIn('/etc/robot-scope/wireless-odom.key', combined)
        self.assertIn('INPUT_TOPIC = "/utlidar/robot_odom"', combined)
        self.assertIn('OUTPUT_TOPIC = "/utlidar/robot_odom"', combined)
        self.assertIn("MIN_SEND_INTERVAL_NS = 10_000_000", combined)
        self.assertNotIn("argparse", combined)

        for role, user in (("sender", "unitree"), ("receiver", "jetson_orin_nano")):
            service = (
                ROOT / "deploy" / f"robot-scope-wireless-odom-{role}.service.example"
            ).read_text(encoding="utf-8")
            self.assertIn(f"User={user}", service)
            self.assertIn("ConditionFileNotEmpty=/etc/robot-scope/wireless-odom.key", service)
            self.assertIn("CapabilityBoundingSet=", service)
            self.assertIn("NoNewPrivileges=true", service)
            self.assertIn("disabled", service)

        launcher = (SCRIPTS / "run_go2_navigation_humble.sh").read_text(encoding="utf-8")
        self.assertIn("${ROBOT_SCOPE_MAPPING_PROFILE:-go2-xt16-wired}", launcher)
        self.assertIn("scripts/setup_go2_ros2_humble.sh", launcher)
        self.assertIn("scripts/setup_wireless_mapping_ros2_humble.sh", launcher)
        self.assertIn("--service odom --action ensure-started", launcher)
        self.assertIn("run_wireless_odom_receiver_humble.sh", launcher)
        self.assertIn("check_wireless_odom_ready.py", launcher)
        self.assertIn("--service odom --action stop", launcher)
        self.assertLess(
            launcher.index("check_wireless_odom_ready.py"),
            launcher.index("robot_dashboard.navigation_runtime"),
        )
        for forbidden in ("192.168.123.99/24\" #", "DDS Router", "iptables"):
            self.assertNotIn(forbidden, launcher)

    def test_architecture_and_deployment_docs_keep_the_boundary_explicit(self):
        adr = (
            ROOT / "docs" / "ADR_WIRELESS_CONTROLLER_ODOMETRY_TRANSPORT.md"
        ).read_text(encoding="utf-8")
        plan = (
            ROOT / "docs" / "WIRELESS_NAVIGATION_TRANSPORT_DEPLOYMENT_PLAN.md"
        ).read_text(encoding="utf-8")
        recovery = (
            ROOT / "docs" / "CONTROLLER_ODOMETRY_CLOCK_RECOVERY_PLAN.md"
        ).read_text(encoding="utf-8")
        normalized_recovery = " ".join(recovery.split())
        for value in (
            "/utlidar/robot_odom",
            "192.168.50.30:46030",
            "192.168.50.10:46030",
            "784-byte",
            "FAST-LIO `/Odometry` cannot replace",
            "five consecutive fresh",
            "no automatic Navigation activation",
        ):
            self.assertIn(value, adr)
        for value in (
            "APPROVE_WIRELESS_ODOM_DEPLOY",
            "WNO-1",
            "WNO-2",
            "WNO-3",
            "WNO-4",
            "does not authorize",
            "Rollback never deletes runtime maps",
        ):
            self.assertIn(value, plan)
        for value in (
            "APPROVE_WIRELESS_ODOM_SOURCE_CLOCK_GUARD",
            "original `/utlidar/robot_odom` header stamp",
            "source_stamp_age_ms",
            "sent=0",
            "Post-v1.1.15 read-only remeasurement",
            "approximately 681 ms future skew",
            "MIN_SEND_INTERVAL_NS=10_000_000",
            "does not authorize changing either Jetson clock",
            "WNO-2, WNO-3, WNO-4, localization and Nav2 remain blocked",
        ):
            self.assertIn(" ".join(value.split()), normalized_recovery)

    def test_vendor_support_request_is_complete_and_sanitized(self):
        request = (
            ROOT / "docs" / "UNITREE_CONTROLLER_ODOMETRY_CLOCK_SUPPORT_REQUEST.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(request.split())

        for value in (
            "/utlidar/robot_odom",
            "/utlidar/imu",
            "v1.1.15",
            "v2.0.0-8031e",
            "227.874 seconds",
            "approximately 681 ms",
            "500 ms",
            "100 ms",
            "L1 firmware/build",
            "persist across a robot reboot",
            "official rollback or downgrade procedure",
            "expected timestamp domain",
            "WNO-2, localization and Nav2 remain blocked",
        ):
            self.assertIn(value, normalized)

        for rejected in (
            "rebasing the ROS header stamp",
            "stepping either Linux host clock with `date -s`",
            "guessing an undocumented key for the generic SDK2 `ConfigClient`",
        ):
            self.assertIn(rejected, normalized)

        for secret in (
            "BEGIN OPENSSH PRIVATE KEY",
            "ROBOT_SCOPE_CONTROL_BRIDGE_KEY=",
            "ROBOT_SCOPE_WIRELESS_ODOM_KEY=",
            "Password:",
        ):
            self.assertNotIn(secret, request)


if __name__ == "__main__":
    unittest.main()
