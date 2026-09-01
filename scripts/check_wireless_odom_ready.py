#!/usr/bin/env python3
"""Boundedly verify the fixed external controller-odometry projection."""

from __future__ import annotations

import argparse
import math
import time
from typing import Any, Sequence

from wireless_odom_protocol import (
    CHILD_FRAME,
    MAX_ANGULAR_ABS_RADPS,
    MAX_COVARIANCE_ABS,
    MAX_LINEAR_ABS_MPS,
    MAX_POSITION_ABS_M,
    MAX_QUATERNION_NORM_ERROR,
    SOURCE_FRAME,
)


TOPIC = "/utlidar/robot_odom"
MIN_ADVANCING_SAMPLES = 3
MAX_SAMPLE_AGE_NS = 750_000_000
MAX_FUTURE_SKEW_NS = 100_000_000


class ReadinessError(RuntimeError):
    pass


def validate_message(message: Any, *, now_realtime_ns: int) -> int:
    try:
        if str(message.header.frame_id) != SOURCE_FRAME:
            raise ReadinessError("controller odometry parent frame is invalid")
        if str(message.child_frame_id) != CHILD_FRAME:
            raise ReadinessError("controller odometry child frame is invalid")
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
            raise ReadinessError("controller odometry timestamp is malformed")
        stamp_ns = stamp.sec * 1_000_000_000 + stamp.nanosec
        pose = message.pose.pose
        twist = message.twist.twist
        values = (
            pose.position.x,
            pose.position.y,
            pose.position.z,
            pose.orientation.x,
            pose.orientation.y,
            pose.orientation.z,
            pose.orientation.w,
            twist.linear.x,
            twist.linear.y,
            twist.linear.z,
            twist.angular.x,
            twist.angular.y,
            twist.angular.z,
            *message.pose.covariance,
            *message.twist.covariance,
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise ReadinessError("controller odometry message is malformed") from exc
    if len(values) != 85 or not all(math.isfinite(float(value)) for value in values):
        raise ReadinessError("controller odometry contains non-finite values")
    orientation = tuple(float(value) for value in values[3:7])
    norm = math.sqrt(sum(value * value for value in orientation))
    if abs(norm - 1.0) > MAX_QUATERNION_NORM_ERROR:
        raise ReadinessError("controller odometry quaternion is invalid")
    if any(abs(float(value)) > MAX_POSITION_ABS_M for value in values[0:3]):
        raise ReadinessError("controller odometry position is out of bounds")
    if any(abs(float(value)) > MAX_LINEAR_ABS_MPS for value in values[7:10]):
        raise ReadinessError("controller odometry linear velocity is out of bounds")
    if any(abs(float(value)) > MAX_ANGULAR_ABS_RADPS for value in values[10:13]):
        raise ReadinessError("controller odometry angular velocity is out of bounds")
    if any(abs(float(value)) > MAX_COVARIANCE_ABS for value in values[13:85]):
        raise ReadinessError("controller odometry covariance is out of bounds")
    if stamp_ns <= 0:
        raise ReadinessError("controller odometry timestamp is zero")
    age_ns = now_realtime_ns - stamp_ns
    if age_ns > MAX_SAMPLE_AGE_NS:
        raise ReadinessError("controller odometry timestamp is stale")
    if age_ns < -MAX_FUTURE_SKEW_NS:
        raise ReadinessError("controller odometry timestamp is in the future")
    return stamp_ns


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=15.0)
    options = parser.parse_args(argv)
    if not math.isfinite(options.timeout) or not 1.0 <= options.timeout <= 60.0:
        parser.error("--timeout must be between 1 and 60 seconds")
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
    except (ImportError, ModuleNotFoundError):
        print("[Robot Scope] wireless controller odometry ROS runtime is unavailable")
        return 69

    rclpy.init(args=None)
    node = Node("robot_scope_wireless_odom_readiness")
    stamps: list[int] = []
    error = "controller odometry has not published a fresh sample"

    def receive(message: Any) -> None:
        nonlocal error
        try:
            stamp_ns = validate_message(message, now_realtime_ns=time.time_ns())
        except ReadinessError as exc:
            error = str(exc)
            stamps.clear()
            return
        if stamps and stamp_ns <= stamps[-1]:
            error = "controller odometry timestamp did not advance"
            stamps.clear()
            return
        stamps.append(stamp_ns)
        del stamps[:-MIN_ADVANCING_SAMPLES]

    qos = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.VOLATILE,
    )
    subscription = node.create_subscription(Odometry, TOPIC, receive, qos)
    deadline = time.monotonic() + options.timeout
    try:
        while time.monotonic() < deadline:
            if node.count_publishers(TOPIC) != 1:
                error = "controller odometry requires exactly one publisher"
                stamps.clear()
            rclpy.spin_once(node, timeout_sec=0.1)
            if len(stamps) >= MIN_ADVANCING_SAMPLES and node.count_publishers(TOPIC) == 1:
                print("[Robot Scope] authenticated wireless controller odometry ready")
                return 0
    finally:
        node.destroy_subscription(subscription)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    print(f"[Robot Scope] {error}")
    return 69


if __name__ == "__main__":
    raise SystemExit(main())
