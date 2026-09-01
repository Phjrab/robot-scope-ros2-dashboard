#!/usr/bin/env python3
"""Receive authenticated Go2 IMU samples and publish exactly /imu/body."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from wireless_imu_protocol import (
    ConnectedImuDatagram,
    ImuEnvelope,
    ReceiverCore,
    WirelessImuError,
    load_private_key,
    system_clock_synchronized,
)


OUTPUT_TOPIC = "/imu/body"
OUTPUT_FRAME = "body_imu"
RECEIVE_PERIOD_S = 0.005
REPORT_INTERVAL_S = 5.0
MAX_PACKETS_PER_TICK = 4


@dataclass(frozen=True)
class RosImuValues:
    stamp_sec: int
    stamp_nanosec: int
    orientation_xyzw: tuple[float, float, float, float]
    angular_velocity_xyz: tuple[float, float, float]
    linear_acceleration_xyz: tuple[float, float, float]


def sample_to_ros_values(sample: ImuEnvelope) -> RosImuValues:
    """Map a validated source timestamp and WXYZ sample without rebasing time."""

    w, x, y, z = sample.quaternion_wxyz
    return RosImuValues(
        stamp_sec=sample.realtime_ns // 1_000_000_000,
        stamp_nanosec=sample.realtime_ns % 1_000_000_000,
        orientation_xyzw=(x, y, z, w),
        angular_velocity_xyz=sample.gyroscope_xyz,
        linear_acceleration_xyz=sample.accelerometer_xyz,
    )


def main() -> int:
    if os.geteuid() == 0:
        raise SystemExit("wireless IMU receiver refuses to run as root")

    try:
        import rclpy  # type: ignore[import-not-found]
        from rclpy.node import Node  # type: ignore[import-not-found]
        from rclpy.qos import (  # type: ignore[import-not-found]
            DurabilityPolicy,
            HistoryPolicy,
            QoSProfile,
            ReliabilityPolicy,
        )
        from sensor_msgs.msg import Imu  # type: ignore[import-not-found]
    except (ImportError, ModuleNotFoundError) as exc:
        raise SystemExit("ROS 2 Humble sensor_msgs are unavailable") from exc

    key = load_private_key()
    core = ReceiverCore(key)
    transport = ConnectedImuDatagram("receiver")

    class WirelessImuReceiver(Node):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__("robot_scope_wireless_imu_receiver")
            output_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=5,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            self._publisher = self.create_publisher(Imu, OUTPUT_TOPIC, output_qos)
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
                except (OSError, WirelessImuError):
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
                except WirelessImuError:
                    continue
                if not self._publisher_exclusive:
                    continue
                values = sample_to_ros_values(sample)
                message = Imu()
                message.header.stamp.sec = values.stamp_sec
                message.header.stamp.nanosec = values.stamp_nanosec
                message.header.frame_id = OUTPUT_FRAME
                message.orientation.x, message.orientation.y = values.orientation_xyzw[
                    0:2
                ]
                message.orientation.z, message.orientation.w = values.orientation_xyzw[
                    2:4
                ]
                message.angular_velocity.x, message.angular_velocity.y = (
                    values.angular_velocity_xyz[0:2]
                )
                message.angular_velocity.z = values.angular_velocity_xyz[2]
                message.linear_acceleration.x, message.linear_acceleration.y = (
                    values.linear_acceleration_xyz[0:2]
                )
                message.linear_acceleration.z = values.linear_acceleration_xyz[2]
                self._publisher.publish(message)
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
            self.get_logger().info(f"wireless_imu_receiver {fields}")

    rclpy.init(args=None)
    node = WirelessImuReceiver()
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
