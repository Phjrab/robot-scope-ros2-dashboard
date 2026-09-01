#!/usr/bin/env python3
"""Receive authenticated controller odometry and publish one fixed ROS topic."""

from __future__ import annotations

import os
import time
from typing import Any

from wireless_odom_protocol import (
    CHILD_FRAME,
    SOURCE_FRAME,
    ConnectedOdomDatagram,
    OdomEnvelope,
    ReceiverCore,
    WirelessOdomError,
    load_private_key,
    system_clock_synchronized,
)


OUTPUT_TOPIC = "/utlidar/robot_odom"
RECEIVE_PERIOD_S = 0.005
REPORT_INTERVAL_S = 5.0
MAX_PACKETS_PER_TICK = 8


def fill_message(message: Any, sample: OdomEnvelope) -> None:
    message.header.stamp.sec = sample.source_stamp_ns // 1_000_000_000
    message.header.stamp.nanosec = sample.source_stamp_ns % 1_000_000_000
    message.header.frame_id = SOURCE_FRAME
    message.child_frame_id = CHILD_FRAME
    pose = message.pose.pose
    pose.position.x, pose.position.y, pose.position.z = sample.position_xyz
    (
        pose.orientation.x,
        pose.orientation.y,
        pose.orientation.z,
        pose.orientation.w,
    ) = sample.orientation_xyzw
    twist = message.twist.twist
    twist.linear.x, twist.linear.y, twist.linear.z = sample.linear_xyz
    twist.angular.x, twist.angular.y, twist.angular.z = sample.angular_xyz
    message.pose.covariance = list(sample.pose_covariance)
    message.twist.covariance = list(sample.twist_covariance)


def main() -> int:
    if os.geteuid() == 0:
        raise SystemExit("wireless odometry receiver refuses to run as root")
    try:
        import rclpy  # type: ignore[import-not-found]
        from nav_msgs.msg import Odometry  # type: ignore[import-not-found]
        from rclpy._rclpy_pybind11 import RCLError  # type: ignore[import-not-found]
        from rclpy.node import Node  # type: ignore[import-not-found]
        from rclpy.qos import (  # type: ignore[import-not-found]
            DurabilityPolicy,
            HistoryPolicy,
            QoSProfile,
            ReliabilityPolicy,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise SystemExit("ROS 2 Humble nav_msgs are unavailable") from exc

    key = load_private_key()
    core = ReceiverCore(key)
    transport = ConnectedOdomDatagram("receiver")

    class WirelessOdomReceiver(Node):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__("robot_scope_wireless_odom_receiver")
            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            self._publisher = self.create_publisher(Odometry, OUTPUT_TOPIC, qos)
            self._publisher_exclusive = False
            self.create_timer(1.0, self._update_graph_state)
            self.create_timer(RECEIVE_PERIOD_S, self._receive)
            self.create_timer(REPORT_INTERVAL_S, self._report)

        def _update_graph_state(self) -> None:
            self._publisher_exclusive = self.count_publishers(OUTPUT_TOPIC) == 1

        def _receive(self) -> None:
            for _ in range(MAX_PACKETS_PER_TICK):
                try:
                    packet = transport.receive()
                except (OSError, WirelessOdomError):
                    core.note_transport_loss()
                    return
                if packet is None:
                    return
                now_realtime_ns = time.time_ns()
                now_monotonic_ns = time.monotonic_ns()
                try:
                    sample = core.accept(
                        packet,
                        received_realtime_ns=now_realtime_ns,
                        received_monotonic_ns=now_monotonic_ns,
                        clock_synchronized=system_clock_synchronized(),
                    )
                except WirelessOdomError:
                    continue
                ready = core.snapshot(
                    now_monotonic_ns=now_monotonic_ns,
                    clock_synchronized=system_clock_synchronized(),
                )["ready"]
                if not ready or not self._publisher_exclusive:
                    continue
                message = Odometry()
                fill_message(message, sample)
                try:
                    self._publisher.publish(message)
                except RCLError:
                    if rclpy.ok():
                        raise
                    return
                core.note_published()

        def _report(self) -> None:
            status = core.snapshot(
                now_monotonic_ns=time.monotonic_ns(),
                clock_synchronized=system_clock_synchronized(),
            )
            status["transport_ready"] = status["ready"]
            status["ready"] = bool(status["ready"] and self._publisher_exclusive)
            status["publisher_state"] = (
                "exclusive" if self._publisher_exclusive else "conflict_or_waiting"
            )
            fields = " ".join(f"{name}={value}" for name, value in status.items())
            self.get_logger().info(f"wireless_odom_receiver {fields}")

    rclpy.init(args=None)
    node = WirelessOdomReceiver()
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
