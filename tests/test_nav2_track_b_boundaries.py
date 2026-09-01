import sys
import threading
import types
import unittest
import uuid
from pathlib import Path

from robot_dashboard import navigation_runtime
from robot_dashboard.ros.navigation_gateway import (
    NAVIGATION_CONTROLLER_ODOM_TOPIC,
    NAVIGATION_FAST_LIO_ODOM_TOPIC,
    NavigationRosGateway,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wireless_odom_protocol as protocol
import wireless_odom_sender_foxy as sender


NOW_NS = 2_000_000_000_000_000_000
FIXED_PAST_OFFSET_NS = 227_874_000_000
BOOT_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")
KEY = bytes(range(protocol.KEY_BYTES))


class FixedClockNode:
    def get_clock(self):
        return types.SimpleNamespace(
            now=lambda: types.SimpleNamespace(nanoseconds=NOW_NS)
        )


def gateway() -> NavigationRosGateway:
    control = types.SimpleNamespace(manager=None, operation_lock=threading.RLock())
    return NavigationRosGateway(
        control,
        node_getter=lambda: FixedClockNode(),
        tick=lambda *_args: None,
        graph_getter=lambda: {},
    )


def stamped_message(stamp_ns: int):
    return types.SimpleNamespace(
        header=types.SimpleNamespace(
            stamp=types.SimpleNamespace(
                sec=stamp_ns // 1_000_000_000,
                nanosec=stamp_ns % 1_000_000_000,
            )
        )
    )


def envelope(sequence: int) -> protocol.OdomEnvelope:
    sender_realtime_ns = NOW_NS + sequence * 10_000_000
    return protocol.OdomEnvelope(
        boot_id=BOOT_ID,
        sequence=sequence,
        sender_realtime_ns=sender_realtime_ns,
        sender_monotonic_ns=500_000_000_000 + sequence * 10_000_000,
        source_stamp_ns=sender_realtime_ns - 1_000_000,
        position_xyz=(0.0, 0.0, 0.0),
        orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
        linear_xyz=(0.0, 0.0, 0.0),
        angular_xyz=(0.0, 0.0, 0.0),
        pose_covariance=(0.0,) * 36,
        twist_covariance=(0.0,) * 36,
    )


class TrackBClockBoundaryTests(unittest.TestCase):
    def test_fixed_past_controller_stamp_is_not_gateway_absolute_age_gated(self):
        navigation = gateway()
        past_ns = NOW_NS - FIXED_PAST_OFFSET_NS
        message = stamped_message(past_ns)

        self.assertEqual(
            navigation._navigation_validate_odom_stamp(
                NAVIGATION_CONTROLLER_ODOM_TOPIC, message
            ),
            past_ns,
        )
        with self.assertRaisesRegex(ValueError, "timestamp is stale"):
            navigation._navigation_validate_odom_stamp(
                NAVIGATION_FAST_LIO_ODOM_TOPIC, message
            )

    def test_controller_stamp_must_advance_even_without_absolute_age_gate(self):
        navigation = gateway()
        past_ns = NOW_NS - FIXED_PAST_OFFSET_NS

        self.assertFalse(
            navigation._navigation_commit_odom_stamp(
                NAVIGATION_CONTROLLER_ODOM_TOPIC, past_ns
            )
        )
        self.assertTrue(
            navigation._navigation_commit_odom_stamp(
                NAVIGATION_CONTROLLER_ODOM_TOPIC, past_ns + 10_000_000
            )
        )
        with self.assertRaisesRegex(ValueError, "timestamp did not increase"):
            navigation._navigation_commit_odom_stamp(
                NAVIGATION_CONTROLLER_ODOM_TOPIC, past_ns + 10_000_000
            )

    def test_strict_wireless_sender_rejects_fixed_past_and_future_sources(self):
        with self.assertRaisesRegex(protocol.WirelessOdomError, "stale"):
            sender.validate_source_clock(
                NOW_NS - FIXED_PAST_OFFSET_NS,
                NOW_NS,
            )
        with self.assertRaisesRegex(protocol.WirelessOdomError, "future"):
            sender.validate_source_clock(
                NOW_NS + protocol.MAX_FUTURE_SKEW_NS + 1,
                NOW_NS,
            )

    def test_navigation_runtime_requires_host_current_fast_lio_stamp(self):
        node = FixedClockNode()
        current = stamped_message(NOW_NS - 10_000_000)
        fixed_past = stamped_message(NOW_NS - FIXED_PAST_OFFSET_NS)

        self.assertTrue(
            navigation_runtime._message_stamp_is_fresh(node, current, 1.5)
        )
        self.assertFalse(
            navigation_runtime._message_stamp_is_fresh(node, fixed_past, 1.5)
        )

    def test_transport_arrival_staleness_closes_readiness(self):
        core = protocol.ReceiverCore(KEY)
        last = None
        for sequence in range(1, protocol.READY_SAMPLE_COUNT + 1):
            sample = envelope(sequence)
            core.accept(
                protocol.encode_envelope(sample, KEY),
                received_realtime_ns=sample.sender_realtime_ns + 5_000_000,
                received_monotonic_ns=sample.sender_monotonic_ns + 5_000_000,
                clock_synchronized=True,
            )
            last = sample
        assert last is not None
        received_ns = last.sender_monotonic_ns + 5_000_000
        self.assertTrue(
            core.snapshot(
                now_monotonic_ns=received_ns,
                clock_synchronized=True,
            )["ready"]
        )
        self.assertFalse(
            core.snapshot(
                now_monotonic_ns=received_ns + protocol.FRESH_AFTER_NS + 1,
                clock_synchronized=True,
            )["ready"]
        )

    def test_fast_lio_frame_contract_rejects_controller_frame_alias(self):
        self.assertTrue(
            navigation_runtime.odometry_frames_are_expected("camera_init", "body")
        )
        self.assertFalse(
            navigation_runtime.odometry_frames_are_expected("odom", "base_link")
        )

    def test_sensor_restamp_boundary_does_not_rebase_controller_odometry(self):
        receiver_source = (
            SCRIPTS / "wireless_odom_receiver_humble.py"
        ).read_text(encoding="utf-8")
        runtime_source = (
            ROOT / "robot_dashboard" / "navigation_runtime.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "message.header.stamp.sec = sample.source_stamp_ns // 1_000_000_000",
            receiver_source,
        )
        self.assertIn("scan.header.stamp = message.header.stamp", runtime_source)
        self.assertIn("odom_tf.header.stamp = now", runtime_source)


if __name__ == "__main__":
    unittest.main()
