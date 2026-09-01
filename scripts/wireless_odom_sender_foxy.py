#!/usr/bin/env python3
"""Send fixed authenticated Go2 controller odometry to the external Orin."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from wireless_odom_protocol import (
    CHILD_FRAME,
    SOURCE_FRAME,
    ConnectedOdomDatagram,
    OdomEnvelope,
    WirelessOdomError,
    encode_envelope,
    load_private_key,
    read_boot_id,
    system_clock_synchronized,
)


INPUT_TOPIC = "/utlidar/robot_odom"
REPORT_INTERVAL_S = 5.0
MIN_SEND_INTERVAL_NS = 10_000_000
MAX_COUNTER = (1 << 63) - 1


@dataclass(frozen=True)
class SourceOdometry:
    source_stamp_ns: int
    position_xyz: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float]
    linear_xyz: tuple[float, float, float]
    angular_xyz: tuple[float, float, float]
    pose_covariance: tuple[float, ...]
    twist_covariance: tuple[float, ...]


def extract_source_odometry(message: Any) -> SourceOdometry:
    """Extract the complete fixed nav_msgs/Odometry numeric contract."""

    try:
        if str(message.header.frame_id) != SOURCE_FRAME:
            raise WirelessOdomError("bounds")
        if str(message.child_frame_id) != CHILD_FRAME:
            raise WirelessOdomError("bounds")
        stamp = message.header.stamp
        if (
            isinstance(stamp.sec, bool)
            or not isinstance(stamp.sec, int)
            or isinstance(stamp.nanosec, bool)
            or not isinstance(stamp.nanosec, int)
            or stamp.sec < 0
            or stamp.nanosec < 0
            or stamp.nanosec >= 1_000_000_000
        ):
            raise WirelessOdomError("timestamp")
        source_stamp_ns = stamp.sec * 1_000_000_000 + stamp.nanosec
        pose = message.pose.pose
        twist = message.twist.twist
        values = SourceOdometry(
            source_stamp_ns=source_stamp_ns,
            position_xyz=(pose.position.x, pose.position.y, pose.position.z),
            orientation_xyzw=(
                pose.orientation.x,
                pose.orientation.y,
                pose.orientation.z,
                pose.orientation.w,
            ),
            linear_xyz=(twist.linear.x, twist.linear.y, twist.linear.z),
            angular_xyz=(twist.angular.x, twist.angular.y, twist.angular.z),
            pose_covariance=tuple(message.pose.covariance),
            twist_covariance=tuple(message.twist.covariance),
        )
    except AttributeError as exc:
        raise WirelessOdomError("nonfinite") from exc
    if source_stamp_ns <= 0:
        raise WirelessOdomError("timestamp")
    return values


def main() -> int:
    if os.geteuid() == 0:
        raise SystemExit("wireless odometry sender refuses to run as root")
    try:
        import rclpy  # type: ignore[import-not-found]
        from nav_msgs.msg import Odometry  # type: ignore[import-not-found]
        from rclpy.node import Node  # type: ignore[import-not-found]
        from rclpy.qos import (  # type: ignore[import-not-found]
            DurabilityPolicy,
            HistoryPolicy,
            QoSProfile,
            ReliabilityPolicy,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise SystemExit("ROS 2 Foxy nav_msgs are unavailable") from exc

    key = load_private_key()
    boot_id = read_boot_id()
    transport = ConnectedOdomDatagram("sender")

    class WirelessOdomSender(Node):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__("robot_scope_wireless_odom_sender")
            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            self._sequence = max(1, time.monotonic_ns())
            self._input_ready = False
            self._last_sent_monotonic_ns = 0
            self._last_source_stamp_ns = 0
            self._received = 0
            self._sent = 0
            self._rate_limited = 0
            self._invalid = 0
            self._send_errors = 0
            self._clock_blocks = 0
            self.create_subscription(Odometry, INPUT_TOPIC, self._handle, qos)
            self.create_timer(1.0, self._update_graph_state)
            self.create_timer(REPORT_INTERVAL_S, self._report)

        @staticmethod
        def _increment(value: int) -> int:
            return min(MAX_COUNTER, value + 1)

        def _update_graph_state(self) -> None:
            self._input_ready = self.count_publishers(INPUT_TOPIC) == 1

        def _handle(self, message: Any) -> None:
            self._received = self._increment(self._received)
            if not self._input_ready:
                return
            if not system_clock_synchronized():
                self._clock_blocks = self._increment(self._clock_blocks)
                return
            sender_monotonic_ns = time.monotonic_ns()
            if (
                self._last_sent_monotonic_ns
                and sender_monotonic_ns - self._last_sent_monotonic_ns
                < MIN_SEND_INTERVAL_NS
            ):
                self._rate_limited = self._increment(self._rate_limited)
                return
            try:
                source = extract_source_odometry(message)
                if source.source_stamp_ns <= self._last_source_stamp_ns:
                    raise WirelessOdomError("replay")
                sender_realtime_ns = time.time_ns()
                self._sequence = min(0xFFFFFFFFFFFFFFFF, self._sequence + 1)
                sample = OdomEnvelope(
                    boot_id=boot_id,
                    sequence=self._sequence,
                    sender_realtime_ns=sender_realtime_ns,
                    sender_monotonic_ns=sender_monotonic_ns,
                    source_stamp_ns=source.source_stamp_ns,
                    position_xyz=source.position_xyz,
                    orientation_xyzw=source.orientation_xyzw,
                    linear_xyz=source.linear_xyz,
                    angular_xyz=source.angular_xyz,
                    pose_covariance=source.pose_covariance,
                    twist_covariance=source.twist_covariance,
                )
                transport.send(encode_envelope(sample, key))
                self._last_source_stamp_ns = source.source_stamp_ns
                self._last_sent_monotonic_ns = sender_monotonic_ns
                self._sent = self._increment(self._sent)
            except WirelessOdomError:
                self._invalid = self._increment(self._invalid)
            except OSError:
                self._send_errors = self._increment(self._send_errors)

        def _report(self) -> None:
            self.get_logger().info(
                "wireless_odom_sender "
                f"input_ready={str(self._input_ready).lower()} "
                f"clock_synchronized={str(system_clock_synchronized()).lower()} "
                f"received={self._received} sent={self._sent} "
                f"rate_limited={self._rate_limited} invalid={self._invalid} "
                f"send_errors={self._send_errors} clock_blocks={self._clock_blocks}"
            )

    rclpy.init(args=None)
    node = WirelessOdomSender()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        transport.close()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
