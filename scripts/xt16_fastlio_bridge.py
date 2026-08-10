#!/usr/bin/env python3
"""Fixed XT16/Go2 telemetry bridge for the repository mapping pipeline.

The conversion core intentionally imports no ROS modules, which keeps its byte
layout and clock behavior testable on non-ROS development hosts.  ``main`` is
the only ROS-specific boundary and uses fixed topic names; this process never
creates a robot-control publisher or service client.

The deployed prototype copied into ``~/ws/go2_3d`` was captured at SHA-256
782a4d87e2d43f60af7cbf11ec7804cd90f141e08831dbc13ffbc76546048291.
This repository version preserves its measured wire layout while adding strict
bounds, finite-value checks and explicit publisher QoS.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np


RAW_TOPIC = "/lidar_points"
LOWSTATE_TOPIC = "/lowstate"
OUTPUT_CLOUD_TOPIC = "/velodyne_points"
OUTPUT_IMU_TOPIC = "/imu/body"
LIDAR_FRAME = "hesai_lidar"
IMU_FRAME = "body_imu"

FLOAT32 = 7
FLOAT64 = 8
UINT16 = 4
RAW_MIN_POINTS = 4_000
RAW_MAX_POINTS = 100_000
OUTPUT_MIN_POINTS = 1_000
CLOUD_DECIMATION = 4
RAW_MIN_POINT_STEP = 26
OUTPUT_POINT_STEP = 22
MAX_SCAN_DURATION_S = 0.25
CLOCK_OFFSET_RISE_PER_SCAN_S = 0.0001

RAW_FIELDS = (
    ("x", 0, FLOAT32, 1),
    ("y", 4, FLOAT32, 1),
    ("z", 8, FLOAT32, 1),
    ("intensity", 12, FLOAT32, 1),
    ("ring", 16, UINT16, 1),
    ("timestamp", 18, FLOAT64, 1),
)
OUTPUT_FIELDS = (
    ("x", 0, FLOAT32, 1),
    ("y", 4, FLOAT32, 1),
    ("z", 8, FLOAT32, 1),
    ("intensity", 12, FLOAT32, 1),
    ("time", 16, FLOAT32, 1),
    ("ring", 20, UINT16, 1),
)
OUTPUT_DTYPE = np.dtype(
    {
        "names": [item[0] for item in OUTPUT_FIELDS],
        "formats": ["<f4", "<f4", "<f4", "<f4", "<f4", "<u2"],
        "offsets": [item[1] for item in OUTPUT_FIELDS],
        "itemsize": OUTPUT_POINT_STEP,
    }
)


class BridgeContractError(ValueError):
    """A fixed XT16 or Go2 telemetry contract was violated."""


@dataclass(frozen=True)
class ConvertedCloud:
    data: bytes
    width: int
    frame_id: str
    stamp_sec: int
    stamp_nanosec: int
    scan_start_s: float
    scan_duration_s: float


@dataclass(frozen=True)
class ImuSample:
    orientation_xyzw: tuple[float, float, float, float]
    angular_velocity_xyz: tuple[float, float, float]
    linear_acceleration_xyz: tuple[float, float, float]


class ClockOffsetTracker:
    """Track a low-jitter LiDAR-clock to host-clock offset."""

    def __init__(self) -> None:
        self.offset_s: float | None = None

    def stamp(self, scan_start_s: float, scan_end_s: float, received_s: float) -> tuple[int, int]:
        if not all(math.isfinite(value) for value in (scan_start_s, scan_end_s, received_s)):
            raise BridgeContractError("cloud clocks must be finite")
        if scan_start_s <= 0 or scan_end_s < scan_start_s or received_s <= 0:
            raise BridgeContractError("cloud clocks are outside the supported range")
        instantaneous = received_s - scan_end_s
        if self.offset_s is None:
            self.offset_s = instantaneous
        else:
            self.offset_s = min(
                instantaneous,
                self.offset_s + CLOCK_OFFSET_RISE_PER_SCAN_S,
            )
        host_stamp = scan_start_s + self.offset_s
        if not math.isfinite(host_stamp) or host_stamp < 0:
            raise BridgeContractError("converted cloud stamp is outside the supported range")
        seconds = math.floor(host_stamp)
        nanoseconds = int(round((host_stamp - seconds) * 1_000_000_000))
        if nanoseconds >= 1_000_000_000:
            seconds += 1
            nanoseconds -= 1_000_000_000
        return int(seconds), nanoseconds


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise BridgeContractError(f"{label} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BridgeContractError(f"{label} must be an integer") from exc


def _field_map(message: Any) -> dict[str, Any]:
    fields = getattr(message, "fields", None)
    if not isinstance(fields, Sequence):
        raise BridgeContractError("PointCloud2 fields are missing")
    result: dict[str, Any] = {}
    for field in fields:
        name = str(getattr(field, "name", ""))
        if not name or name in result:
            raise BridgeContractError("PointCloud2 fields are unnamed or duplicated")
        result[name] = field
    return result


def _raw_records(message: Any) -> np.ndarray:
    header = getattr(message, "header", None)
    if str(getattr(header, "frame_id", "")) != LIDAR_FRAME:
        raise BridgeContractError(f"raw cloud frame must be {LIDAR_FRAME}")
    width = _integer(getattr(message, "width", None), "width")
    height = _integer(getattr(message, "height", None), "height")
    point_step = _integer(getattr(message, "point_step", None), "point_step")
    row_step = _integer(getattr(message, "row_step", None), "row_step")
    points = width * height
    if height != 1 or points < RAW_MIN_POINTS or points > RAW_MAX_POINTS:
        raise BridgeContractError(
            f"raw cloud must contain {RAW_MIN_POINTS}..{RAW_MAX_POINTS} points in one row"
        )
    if point_step < RAW_MIN_POINT_STEP or bool(getattr(message, "is_bigendian", False)):
        raise BridgeContractError("raw cloud byte layout is unsupported")
    if row_step != width * point_step:
        raise BridgeContractError("raw cloud row_step must equal width * point_step")
    try:
        data = memoryview(getattr(message, "data", None)).cast("B")
    except (TypeError, ValueError) as exc:
        raise BridgeContractError("raw cloud data is missing") from exc
    if data.nbytes != row_step:
        raise BridgeContractError("raw cloud payload length does not match its layout")

    fields = _field_map(message)
    for name, offset, datatype, count in RAW_FIELDS:
        field = fields.get(name)
        if field is None or (
            _integer(getattr(field, "offset", None), f"{name}.offset"),
            _integer(getattr(field, "datatype", None), f"{name}.datatype"),
            _integer(getattr(field, "count", None), f"{name}.count"),
        ) != (offset, datatype, count):
            raise BridgeContractError(f"raw cloud field {name} has an incompatible layout")
    dtype = np.dtype(
        {
            "names": [item[0] for item in RAW_FIELDS],
            "formats": ["<f4", "<f4", "<f4", "<f4", "<u2", "<f8"],
            "offsets": [item[1] for item in RAW_FIELDS],
            "itemsize": point_step,
        }
    )
    try:
        return np.frombuffer(data, dtype=dtype, count=points)
    except (TypeError, ValueError, BufferError) as exc:
        raise BridgeContractError("raw cloud payload cannot be decoded safely") from exc


def convert_xt16_cloud(
    message: Any,
    *,
    received_s: float,
    clock: ClockOffsetTracker,
) -> ConvertedCloud:
    """Convert one exact Hesai cloud to the FAST-LIO Velodyne layout."""

    source = _raw_records(message)[::CLOUD_DECIMATION]
    timestamps = source["timestamp"].astype(np.float64, copy=False)
    finite = (
        np.isfinite(source["x"])
        & np.isfinite(source["y"])
        & np.isfinite(source["z"])
        & np.isfinite(timestamps)
        & (timestamps > 0)
    )
    source = source[finite]
    timestamps = timestamps[finite]
    if len(source) < OUTPUT_MIN_POINTS:
        raise BridgeContractError("too few finite decimated XT16 points remain")
    scan_start = float(np.min(timestamps))
    scan_end = float(np.max(timestamps))
    duration = scan_end - scan_start
    if not math.isfinite(duration) or duration < 0 or duration > MAX_SCAN_DURATION_S:
        raise BridgeContractError("XT16 scan duration is outside the supported range")

    output = np.zeros(len(source), dtype=OUTPUT_DTYPE)
    for name in ("x", "y", "z", "ring"):
        output[name] = source[name]
    intensity = source["intensity"].astype(np.float32, copy=False)
    output["intensity"] = np.where(np.isfinite(intensity), intensity, 0.0)
    output["time"] = (timestamps - scan_start).astype(np.float32)
    stamp_sec, stamp_nanosec = clock.stamp(scan_start, scan_end, received_s)
    return ConvertedCloud(
        data=output.tobytes(),
        width=len(output),
        frame_id=LIDAR_FRAME,
        stamp_sec=stamp_sec,
        stamp_nanosec=stamp_nanosec,
        scan_start_s=scan_start,
        scan_duration_s=duration,
    )


def _finite_vector(value: Any, label: str, length: int) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)):
        raise BridgeContractError(f"{label} must contain {length} finite values")
    try:
        values = tuple(float(item) for item in value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BridgeContractError(f"{label} must contain {length} finite values") from exc
    if len(values) != length or not all(math.isfinite(item) for item in values):
        raise BridgeContractError(f"{label} must contain {length} finite values")
    return values


def extract_imu_sample(message: Any) -> ImuSample:
    state = getattr(message, "imu_state", None)
    if state is None:
        raise BridgeContractError("LowState imu_state is missing")
    quaternion_wxyz = _finite_vector(
        getattr(state, "quaternion", None),
        "imu quaternion",
        4,
    )
    norm = math.sqrt(sum(value * value for value in quaternion_wxyz))
    if norm < 0.5 or norm > 1.5:
        raise BridgeContractError("imu quaternion norm is outside the supported range")
    w, x, y, z = (value / norm for value in quaternion_wxyz)
    return ImuSample(
        orientation_xyzw=(x, y, z, w),
        angular_velocity_xyz=_finite_vector(
            getattr(state, "gyroscope", None),
            "imu gyroscope",
            3,
        ),
        linear_acceleration_xyz=_finite_vector(
            getattr(state, "accelerometer", None),
            "imu accelerometer",
            3,
        ),
    )


def _parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description="Run the fixed /lidar_points + /lowstate FAST-LIO bridge."
    )


def run_ros_bridge() -> int:
    try:
        import rclpy
        from rclpy.callback_groups import (
            MutuallyExclusiveCallbackGroup,
            ReentrantCallbackGroup,
        )
        from rclpy.executors import MultiThreadedExecutor
        from rclpy.node import Node
        from rclpy.qos import (
            DurabilityPolicy,
            HistoryPolicy,
            QoSProfile,
            ReliabilityPolicy,
        )
        from sensor_msgs.msg import Imu, PointCloud2, PointField
        from unitree_go.msg import LowState
    except ImportError as exc:
        print(f"[Robot Scope] XT16 bridge cannot import ROS: {exc}", file=sys.stderr)
        return 2

    reliable = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=5,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )
    best_effort = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=5,
        reliability=ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.VOLATILE,
    )

    class Xt16FastlioBridge(Node):
        def __init__(self) -> None:
            super().__init__("xt16_fastlio_bridge")
            self._clock_offset = ClockOffsetTracker()
            self._cloud_count = 0
            self._imu_count = 0
            self._reject_count = 0
            self._cloud_publisher = self.create_publisher(
                PointCloud2,
                OUTPUT_CLOUD_TOPIC,
                reliable,
            )
            self._imu_publisher = self.create_publisher(
                Imu,
                OUTPUT_IMU_TOPIC,
                reliable,
            )
            self._cloud_group = MutuallyExclusiveCallbackGroup()
            self._imu_group = ReentrantCallbackGroup()
            self._bridge_subscriptions = (
                self.create_subscription(
                    PointCloud2,
                    RAW_TOPIC,
                    self._on_cloud,
                    reliable,
                    callback_group=self._cloud_group,
                ),
                self.create_subscription(
                    LowState,
                    LOWSTATE_TOPIC,
                    self._on_lowstate,
                    best_effort,
                    callback_group=self._imu_group,
                ),
            )
            self._timer = self.create_timer(5.0, self._report)
            self.get_logger().info(
                "fixed XT16 bridge ready: /lidar_points -> /velodyne_points; "
                "/lowstate -> /imu/body"
            )

        def _rejected(self, exc: BridgeContractError) -> None:
            self._reject_count += 1
            if self._reject_count == 1 or self._reject_count % 50 == 0:
                self.get_logger().error(f"bridge rejected input: {exc}")

        def _on_cloud(self, message: Any) -> None:
            try:
                converted = convert_xt16_cloud(
                    message,
                    received_s=self.get_clock().now().nanoseconds * 1e-9,
                    clock=self._clock_offset,
                )
            except BridgeContractError as exc:
                self._rejected(exc)
                return
            output = PointCloud2()
            output.header.stamp.sec = converted.stamp_sec
            output.header.stamp.nanosec = converted.stamp_nanosec
            output.header.frame_id = converted.frame_id
            output.height = 1
            output.width = converted.width
            output.fields = [
                PointField(name=name, offset=offset, datatype=datatype, count=count)
                for name, offset, datatype, count in OUTPUT_FIELDS
            ]
            output.is_bigendian = False
            output.point_step = OUTPUT_POINT_STEP
            output.row_step = OUTPUT_POINT_STEP * converted.width
            output.data = converted.data
            output.is_dense = True
            self._cloud_publisher.publish(output)
            self._cloud_count += 1

        def _on_lowstate(self, message: Any) -> None:
            try:
                sample = extract_imu_sample(message)
            except BridgeContractError as exc:
                self._rejected(exc)
                return
            output = Imu()
            output.header.stamp = self.get_clock().now().to_msg()
            output.header.frame_id = IMU_FRAME
            (
                output.orientation.x,
                output.orientation.y,
                output.orientation.z,
                output.orientation.w,
            ) = sample.orientation_xyzw
            (
                output.angular_velocity.x,
                output.angular_velocity.y,
                output.angular_velocity.z,
            ) = sample.angular_velocity_xyz
            (
                output.linear_acceleration.x,
                output.linear_acceleration.y,
                output.linear_acceleration.z,
            ) = sample.linear_acceleration_xyz
            self._imu_publisher.publish(output)
            self._imu_count += 1

        def _report(self) -> None:
            self.get_logger().info(
                f"bridge 5s: clouds={self._cloud_count}, imu={self._imu_count}, "
                f"rejected={self._reject_count}"
            )
            self._cloud_count = 0
            self._imu_count = 0
            self._reject_count = 0

    # Ignore process-level ROS remap arguments so the audited topic allowlist
    # above cannot be widened at runtime.
    rclpy.init(args=[])
    node: Any | None = None
    executor: Any | None = None
    try:
        node = Xt16FastlioBridge()
        executor = MultiThreadedExecutor(num_threads=2)
        executor.add_node(node)
        executor.spin()
        return 0
    except KeyboardInterrupt:
        return 130
    finally:
        if executor is not None:
            executor.shutdown()
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def main(argv: Iterable[str] | None = None) -> int:
    _parser().parse_args(list(argv) if argv is not None else None)
    return run_ros_bridge()


if __name__ == "__main__":
    raise SystemExit(main())
