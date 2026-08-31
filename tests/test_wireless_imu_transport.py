import hashlib
import hmac
import importlib
import math
import os
import socket
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

protocol = importlib.import_module("wireless_imu_protocol")
sender = importlib.import_module("wireless_imu_sender_foxy")
receiver = importlib.import_module("wireless_imu_receiver_humble")

KEY = bytes(range(protocol.KEY_BYTES))
OTHER_KEY = bytes(reversed(range(protocol.KEY_BYTES)))
BOOT = uuid.UUID("12345678-1234-5678-1234-567812345678")
BASE_REALTIME = 2_000_000_000_000_000_000
BASE_MONOTONIC = 500_000_000_000


def make_sample(
    sequence=1,
    *,
    boot_id=BOOT,
    realtime_ns=BASE_REALTIME,
    monotonic_ns=BASE_MONOTONIC,
    source_tick=42,
    quaternion=(1.0, 0.0, 0.0, 0.0),
):
    return protocol.ImuEnvelope(
        boot_id=boot_id,
        sequence=sequence,
        realtime_ns=realtime_ns,
        monotonic_ns=monotonic_ns,
        source_tick=source_tick,
        quaternion_wxyz=quaternion,
        gyroscope_xyz=(0.1, 0.2, 0.3),
        accelerometer_xyz=(1.0, 2.0, 9.8),
    )


def packet_for(sequence=1, **kwargs):
    return protocol.encode_envelope(make_sample(sequence, **kwargs), KEY)


def accept(core, sequence, *, receive_offset=10_000_000, **kwargs):
    realtime_ns = kwargs.get("realtime_ns", BASE_REALTIME + sequence * 10_000_000)
    monotonic_ns = kwargs.get("monotonic_ns", BASE_MONOTONIC + sequence * 10_000_000)
    packet = packet_for(
        sequence,
        realtime_ns=realtime_ns,
        monotonic_ns=monotonic_ns,
        **{
            key: value
            for key, value in kwargs.items()
            if key not in {"realtime_ns", "monotonic_ns"}
        },
    )
    return core.accept(
        packet,
        received_realtime_ns=realtime_ns + receive_offset,
        received_monotonic_ns=monotonic_ns + receive_offset,
        clock_synchronized=True,
    )


def resign_body(body, key=KEY):
    return body + hmac.new(key, body, hashlib.sha256).digest()


class WirelessImuProtocolTests(unittest.TestCase):
    def test_valid_datagram_is_fixed_binary_and_maps_without_rebasing(self):
        packet = packet_for()
        self.assertEqual(len(packet), 184)
        self.assertEqual(len(packet), protocol.PACKET_BYTES)
        decoded = protocol.decode_envelope(packet, KEY)
        self.assertEqual(decoded.boot_id, BOOT)
        self.assertEqual(decoded.source_tick, 42)
        self.assertEqual(decoded.quaternion_wxyz, (1.0, 0.0, 0.0, 0.0))

        values = receiver.sample_to_ros_values(decoded)
        self.assertEqual(values.stamp_sec, BASE_REALTIME // 1_000_000_000)
        self.assertEqual(values.stamp_nanosec, BASE_REALTIME % 1_000_000_000)
        self.assertEqual(values.orientation_xyzw, (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(values.angular_velocity_xyz, (0.1, 0.2, 0.3))

    def test_optional_source_tick_uses_canonical_zero_encoding(self):
        packet = packet_for(source_tick=None)
        decoded = protocol.decode_envelope(packet, KEY)
        self.assertIsNone(decoded.source_tick)

    def test_zero_boot_uuid_and_nonbinary_keys_fail_closed(self):
        with self.assertRaisesRegex(protocol.WirelessImuError, "boot_id"):
            packet_for(boot_id=uuid.UUID(int=0))
        for key in (b"short", "x" * protocol.KEY_BYTES):
            with self.assertRaisesRegex(protocol.WirelessImuError, "key_file"):
                protocol.encode_envelope(make_sample(), key)

    def test_hmac_mismatch_and_wrong_key_are_rejected(self):
        packet = bytearray(packet_for())
        packet[80] ^= 1
        for candidate, key in ((bytes(packet), KEY), (packet_for(), OTHER_KEY)):
            with self.assertRaisesRegex(protocol.WirelessImuError, "authentication"):
                protocol.decode_envelope(candidate, key)

    def test_noncanonical_header_and_length_fields_are_rejected(self):
        original = packet_for()
        body = bytearray(original[: protocol._BODY.size])
        cases = (
            (0, b"BAD!", "magic"),
            (4, b"\x02", "version"),
            (5, b"\x02", "message_type"),
            (6, b"\x00\x02", "flags"),
            (8, b"wrong-sender-id!\x00", "sender_id"),
        )
        for offset, replacement, reason in cases:
            changed = bytearray(body)
            changed[offset : offset + len(replacement)] = replacement
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(protocol.WirelessImuError, reason):
                    protocol.decode_envelope(resign_body(bytes(changed)), KEY)
        for packet in (b"", original[:-1], original + b"x"):
            with self.assertRaisesRegex(protocol.WirelessImuError, "packet_length"):
                protocol.decode_envelope(packet, KEY)

    def test_nan_inf_and_quaternion_norm_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            sample = make_sample()
            sample = protocol.ImuEnvelope(
                **{**sample.__dict__, "gyroscope_xyz": (value, 0.0, 0.0)}
            )
            with self.assertRaisesRegex(protocol.WirelessImuError, "nonfinite"):
                protocol.encode_envelope(sample, KEY)
        for quaternion in ((0.0, 0.0, 0.0, 0.0), (2.0, 0.0, 0.0, 0.0)):
            with self.assertRaisesRegex(protocol.WirelessImuError, "quaternion_norm"):
                packet_for(quaternion=quaternion)

    def test_private_key_requires_exact_owner_mode_size_and_no_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "imu.key"
            path.write_bytes(KEY)
            path.chmod(0o600)
            self.assertEqual(protocol.load_private_key(path), KEY)

            path.chmod(0o640)
            with self.assertRaisesRegex(protocol.WirelessImuError, "key_file"):
                protocol.load_private_key(path)
            path.chmod(0o600)
            with mock.patch.object(
                protocol.os, "geteuid", return_value=os.geteuid() + 1
            ):
                with self.assertRaisesRegex(protocol.WirelessImuError, "key_file"):
                    protocol.load_private_key(path)
            link = Path(directory) / "link.key"
            link.symlink_to(path)
            with self.assertRaisesRegex(protocol.WirelessImuError, "key_file"):
                protocol.load_private_key(link)
            path.write_bytes(KEY[:-1])
            with self.assertRaisesRegex(protocol.WirelessImuError, "key_file"):
                protocol.load_private_key(path)

    def test_clock_marker_fails_closed_for_missing_or_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "synchronized"
            self.assertFalse(protocol.system_clock_synchronized(marker))
            marker.write_text("yes", encoding="ascii")
            self.assertTrue(protocol.system_clock_synchronized(marker))
            link = Path(directory) / "linked"
            link.symlink_to(marker)
            self.assertFalse(protocol.system_clock_synchronized(link))


class ReceiverStateMachineTests(unittest.TestCase):
    def test_five_consecutive_fresh_packets_are_required_for_readiness(self):
        core = protocol.ReceiverCore(KEY)
        for sequence in range(1, protocol.READY_SAMPLE_COUNT + 1):
            accept(core, sequence)
            snapshot = core.snapshot(
                now_monotonic_ns=BASE_MONOTONIC + sequence * 10_000_000 + 10_000_000,
                clock_synchronized=True,
            )
            self.assertEqual(snapshot["ready"], sequence == protocol.READY_SAMPLE_COUNT)
        self.assertTrue(snapshot["authenticated"])
        self.assertEqual(snapshot["last_sequence"], protocol.READY_SAMPLE_COUNT)

    def test_duplicate_reorder_replay_and_loss_are_accounted(self):
        core = protocol.ReceiverCore(KEY)
        accept(core, 1)
        with self.assertRaisesRegex(protocol.WirelessImuError, "duplicate"):
            accept(core, 1)

        core = protocol.ReceiverCore(KEY)
        accept(core, 2)
        with self.assertRaisesRegex(protocol.WirelessImuError, "reorder"):
            accept(core, 1)

        core = protocol.ReceiverCore(KEY)
        accept(core, 1)
        with self.assertRaisesRegex(protocol.WirelessImuError, "replay"):
            accept(core, 2, realtime_ns=BASE_REALTIME + 10_000_000)

        core = protocol.ReceiverCore(KEY)
        accept(core, 1)
        accept(core, 4)
        self.assertEqual(core.stats.lost, 2)

    def test_boot_change_resets_sequence_but_retired_boot_cannot_return(self):
        core = protocol.ReceiverCore(KEY)
        accept(core, 10)
        second_boot = uuid.UUID("22345678-1234-5678-1234-567812345678")
        accept(core, 1, boot_id=second_boot, realtime_ns=BASE_REALTIME + 20_000_000)
        self.assertEqual(core.stats.boot_changes, 1)
        with self.assertRaisesRegex(protocol.WirelessImuError, "retired_boot"):
            accept(core, 11, boot_id=BOOT, realtime_ns=BASE_REALTIME + 30_000_000)

    def test_stale_future_unsynchronized_and_invalid_receive_time_fail_closed(self):
        packet = packet_for()
        cases = (
            (
                BASE_REALTIME + protocol.MAX_SOURCE_AGE_NS + 1,
                BASE_MONOTONIC,
                True,
                "stale",
            ),
            (
                BASE_REALTIME - protocol.MAX_FUTURE_SKEW_NS - 1,
                BASE_MONOTONIC,
                True,
                "future",
            ),
            (BASE_REALTIME, BASE_MONOTONIC, False, "clock_unsynchronized"),
            (0, BASE_MONOTONIC, True, "timestamp"),
            (BASE_REALTIME, 0, True, "timestamp"),
        )
        for realtime_ns, monotonic_ns, synchronized, reason in cases:
            with self.subTest(reason=reason):
                core = protocol.ReceiverCore(KEY)
                with self.assertRaisesRegex(protocol.WirelessImuError, reason):
                    core.accept(
                        packet,
                        received_realtime_ns=realtime_ns,
                        received_monotonic_ns=monotonic_ns,
                        clock_synchronized=synchronized,
                    )

    def test_transport_loss_invalidates_and_five_samples_recover(self):
        core = protocol.ReceiverCore(KEY)
        for sequence in range(1, 6):
            accept(core, sequence)
        core.note_transport_loss()
        status = core.snapshot(
            now_monotonic_ns=BASE_MONOTONIC + 60_000_000,
            clock_synchronized=True,
        )
        self.assertFalse(status["ready"])
        self.assertEqual(status["receive_errors"], 1)
        for sequence in range(6, 11):
            accept(core, sequence)
        status = core.snapshot(
            now_monotonic_ns=BASE_MONOTONIC + 110_000_000,
            clock_synchronized=True,
        )
        self.assertTrue(status["ready"])

    def test_stale_snapshot_and_receive_jitter_health(self):
        core = protocol.ReceiverCore(KEY)
        accept(core, 1)
        accept(core, 2, receive_offset=15_000_000)
        status = core.snapshot(
            now_monotonic_ns=BASE_MONOTONIC + 35_000_000,
            clock_synchronized=True,
        )
        self.assertEqual(status["jitter_ms"], 5.0)
        self.assertEqual(status["max_jitter_ms"], 5.0)
        stale = core.snapshot(
            now_monotonic_ns=BASE_MONOTONIC + protocol.FRESH_AFTER_NS + 40_000_000,
            clock_synchronized=True,
        )
        self.assertFalse(stale["authenticated"])
        self.assertFalse(stale["ready"])

    def test_auth_and_validation_failures_are_exposed_without_payloads(self):
        core = protocol.ReceiverCore(KEY)
        with self.assertRaisesRegex(protocol.WirelessImuError, "authentication"):
            core.accept(
                packet_for()[:-1] + b"x",
                received_realtime_ns=BASE_REALTIME,
                received_monotonic_ns=BASE_MONOTONIC,
                clock_synchronized=True,
            )
        status = core.snapshot(
            now_monotonic_ns=BASE_MONOTONIC,
            clock_synchronized=True,
        )
        self.assertEqual(status["authentication_failures"], 1)
        self.assertEqual(status["rejected"], 1)


class FakeSocket:
    def __init__(self, *_args):
        self.calls = []
        self.closed = False
        self.payload = None

    def bind(self, address):
        self.calls.append(("bind", address))

    def connect(self, address):
        self.calls.append(("connect", address))

    def settimeout(self, timeout):
        self.calls.append(("timeout", timeout))

    def send(self, packet):
        self.payload = packet
        return len(packet)

    def recv(self, _size):
        raise socket.timeout()

    def close(self):
        self.closed = True


class SocketAndSourceContractTests(unittest.TestCase):
    def test_connected_udp_endpoints_fix_both_peer_ip_and_port(self):
        for role, local_ip, peer_ip in (
            ("sender", "192.168.50.30", "192.168.50.10"),
            ("receiver", "192.168.50.10", "192.168.50.30"),
        ):
            created = []

            def factory(*args):
                endpoint = FakeSocket(*args)
                created.append(endpoint)
                return endpoint

            transport = protocol.ConnectedImuDatagram(role, socket_factory=factory)
            endpoint = created[0]
            self.assertEqual(endpoint.calls[0], ("bind", (local_ip, 46020)))
            self.assertEqual(endpoint.calls[1], ("connect", (peer_ip, 46020)))
            self.assertIsNone(transport.receive())
            transport.close()
            self.assertTrue(endpoint.closed)

    def test_socket_setup_failure_closes_the_endpoint(self):
        endpoint = FakeSocket()

        def failing_factory(*_args):
            def fail(_address):
                raise OSError("bind failed")

            endpoint.bind = fail
            return endpoint

        with self.assertRaisesRegex(protocol.WirelessImuError, "socket"):
            protocol.ConnectedImuDatagram("sender", socket_factory=failing_factory)
        self.assertTrue(endpoint.closed)

    def test_lowstate_extraction_is_minimal_and_finite(self):
        class ImuState:
            quaternion = (1.0, 0.0, 0.0, 0.0)
            gyroscope = (0.1, 0.2, 0.3)
            accelerometer = (1.0, 2.0, 3.0)

        class Message:
            imu_state = ImuState()
            tick = 99

        result = sender.extract_lowstate_imu(Message())
        self.assertEqual(result.source_tick, 99)
        self.assertEqual(result.accelerometer_xyz, (1.0, 2.0, 3.0))
        Message.imu_state.gyroscope = (math.nan, 0.0, 0.0)
        with self.assertRaisesRegex(protocol.WirelessImuError, "nonfinite"):
            sender.extract_lowstate_imu(Message())

    def test_source_and_service_contracts_are_fixed_and_separate(self):
        protocol_source = (SCRIPTS / "wireless_imu_protocol.py").read_text()
        sender_source = (SCRIPTS / "wireless_imu_sender_foxy.py").read_text()
        receiver_source = (SCRIPTS / "wireless_imu_receiver_humble.py").read_text()
        combined = protocol_source + sender_source + receiver_source
        self.assertNotIn("ROBOT_SCOPE_CONTROL_BRIDGE_KEY", combined)
        self.assertNotIn("/lowstate", receiver_source)
        self.assertNotIn("create_subscription", receiver_source)
        self.assertIn('OUTPUT_TOPIC = "/imu/body"', receiver_source)
        self.assertIn("depth=5", receiver_source)
        self.assertIn("ReliabilityPolicy.RELIABLE", receiver_source)
        self.assertIn("DurabilityPolicy.VOLATILE", receiver_source)
        self.assertIn('OUTPUT_FRAME = "body_imu"', receiver_source)
        self.assertIn('status["ready"] and self._publisher_exclusive', receiver_source)
        self.assertIn("depth=1", sender_source)
        self.assertIn("ReliabilityPolicy.BEST_EFFORT", sender_source)

        for name, user in (
            ("sender", "unitree"),
            ("receiver", "jetson_orin_nano"),
        ):
            service = (
                ROOT / "deploy" / f"robot-scope-wireless-imu-{name}.service.example"
            ).read_text()
            self.assertIn(f"User={user}", service)
            self.assertIn(
                "ConditionPathIsRegular=/etc/robot-scope/wireless-imu.key", service
            )
            self.assertIn("CapabilityBoundingSet=", service)
            self.assertIn("NoNewPrivileges=true", service)
            self.assertIn("StartLimitBurst=5", service)
            self.assertIn("disabled", service)
            self.assertNotIn("Environment=", service)


if __name__ == "__main__":
    unittest.main()
