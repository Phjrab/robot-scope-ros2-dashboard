#!/usr/bin/env python3
"""Fail-closed readiness probes for the local XT16 mapping pipeline.

Each invocation subscribes with volatile durability, so only messages produced
after the probe starts can count.  The validation core has no ROS dependency
and is covered by the regular unit-test suite.
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Hashable, Optional, Sequence


FLOAT32 = 7
FLOAT64 = 8
UINT16 = 4
POINTCLOUD_TYPE = "sensor_msgs/msg/PointCloud2"
IMU_TYPE = "sensor_msgs/msg/Imu"
ODOMETRY_TYPE = "nav_msgs/msg/Odometry"
MAX_HEADER_AGE_S = 0.50
MAX_HEADER_FUTURE_S = 0.10
RAW_HEADER_SCAN_START_TOLERANCE_S = 0.01


class ReadinessError(ValueError):
    """Raised when a ROS message or publisher violates a fixed contract."""


@dataclass(frozen=True)
class FieldContract:
    name: str
    offset: int
    datatype: int
    count: int = 1


# Keep these layouts in lock-step with scripts/xt16_fastlio_bridge.py.
XT16_FIELDS = (
    FieldContract("x", 0, FLOAT32),
    FieldContract("y", 4, FLOAT32),
    FieldContract("z", 8, FLOAT32),
    FieldContract("intensity", 12, FLOAT32),
    FieldContract("ring", 16, UINT16),
    FieldContract("timestamp", 18, FLOAT64),
)
VELODYNE_FIELDS = (
    FieldContract("x", 0, FLOAT32),
    FieldContract("y", 4, FLOAT32),
    FieldContract("z", 8, FLOAT32),
    FieldContract("intensity", 12, FLOAT32),
    FieldContract("time", 16, FLOAT32),
    FieldContract("ring", 20, UINT16),
)


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ReadinessError(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReadinessError(f"{label} must be an integer") from exc
    return result


def _header(message: Any) -> Any:
    header = getattr(message, "header", None)
    if header is None:
        raise ReadinessError("message header is missing")
    return header


def require_frame_id(message: Any, expected: str) -> None:
    actual = str(getattr(_header(message), "frame_id", ""))
    if actual != expected:
        raise ReadinessError(
            f"frame_id is {actual!r}; expected the fixed frame {expected!r}"
        )


def header_stamp_seconds(message: Any) -> float:
    stamp = getattr(_header(message), "stamp", None)
    seconds = _integer(getattr(stamp, "sec", None), "header.stamp.sec")
    nanoseconds = _integer(
        getattr(stamp, "nanosec", None), "header.stamp.nanosec"
    )
    if seconds < 0 or nanoseconds < 0 or nanoseconds >= 1_000_000_000:
        raise ReadinessError("header stamp is outside the supported range")
    return float(seconds) + float(nanoseconds) * 1e-9


def require_absolute_stamp_age(
    stamp: float,
    *,
    host_now_s: float,
    label: str,
    max_age_s: float = MAX_HEADER_AGE_S,
    max_future_s: float = MAX_HEADER_FUTURE_S,
) -> float:
    """Reject stale/future epoch stamps and return their signed numeric age."""

    if not all(math.isfinite(value) for value in (stamp, host_now_s)):
        raise ReadinessError(f"{label} stamp age inputs are not finite")
    age_s = host_now_s - stamp
    if age_s > max_age_s:
        raise ReadinessError(
            f"{label} header age {age_s:.3f}s exceeds {max_age_s:.3f}s"
        )
    if age_s < -max_future_s:
        raise ReadinessError(
            f"{label} header age {age_s:.3f}s exceeds future skew "
            f"{max_future_s:.3f}s"
        )
    return age_s


def _cloud_layout(
    message: Any,
    *,
    fields_contract: Sequence[FieldContract],
    minimum_point_step: int,
    minimum_points: int,
    maximum_points: int,
    exact_row_layout: bool,
) -> int:
    width = _integer(getattr(message, "width", None), "width")
    height = _integer(getattr(message, "height", None), "height")
    point_step = _integer(getattr(message, "point_step", None), "point_step")
    row_step = _integer(getattr(message, "row_step", None), "row_step")
    points = width * height
    if width <= 0 or height <= 0 or points < minimum_points:
        raise ReadinessError(f"cloud has {max(points, 0)} points; expected at least {minimum_points}")
    if points > maximum_points:
        raise ReadinessError(f"cloud has {points} points; maximum is {maximum_points}")
    if point_step < minimum_point_step:
        raise ReadinessError(
            f"point_step {point_step} is smaller than the required layout"
        )
    if bool(getattr(message, "is_bigendian", False)):
        raise ReadinessError("big-endian point clouds are not supported")

    fields = getattr(message, "fields", None)
    if not isinstance(fields, Sequence):
        raise ReadinessError("PointCloud2 fields are missing")
    by_name: dict[str, Any] = {}
    for field in fields:
        name = str(getattr(field, "name", ""))
        if not name:
            raise ReadinessError("PointCloud2 contains an unnamed field")
        if name in by_name:
            raise ReadinessError(f"duplicate PointCloud2 field: {name}")
        by_name[name] = field

    for expected in fields_contract:
        actual = by_name.get(expected.name)
        if actual is None:
            raise ReadinessError(f"missing PointCloud2 field: {expected.name}")
        offset = _integer(getattr(actual, "offset", None), f"{expected.name}.offset")
        datatype = _integer(
            getattr(actual, "datatype", None), f"{expected.name}.datatype"
        )
        count = _integer(getattr(actual, "count", None), f"{expected.name}.count")
        if (offset, datatype, count) != (
            expected.offset,
            expected.datatype,
            expected.count,
        ):
            raise ReadinessError(
                f"field {expected.name} has layout offset={offset}, "
                f"datatype={datatype}, count={count}; expected "
                f"offset={expected.offset}, datatype={expected.datatype}, "
                f"count={expected.count}"
            )

    minimum_row_step = point_step * width
    if row_step < minimum_row_step or (exact_row_layout and row_step != minimum_row_step):
        relation = "equal to" if exact_row_layout else "at least"
        raise ReadinessError(
            f"row_step {row_step} must be {relation} width * point_step "
            f"({minimum_row_step})"
        )
    data = getattr(message, "data", None)
    try:
        data_length = len(data)
    except (TypeError, AttributeError) as exc:
        raise ReadinessError("PointCloud2 data is missing") from exc
    minimum_data_length = row_step * height
    if data_length < minimum_data_length or (
        exact_row_layout and data_length != minimum_data_length
    ):
        relation = "exactly" if exact_row_layout else "at least"
        raise ReadinessError(
            f"cloud data has {data_length} bytes; expected {relation} "
            f"{minimum_data_length}"
        )
    return points


def validate_xt16_cloud(message: Any) -> int:
    require_frame_id(message, "hesai_lidar")
    if _integer(getattr(message, "height", None), "height") != 1:
        raise ReadinessError("XT16 raw cloud height must be 1")
    return _cloud_layout(
        message,
        fields_contract=XT16_FIELDS,
        minimum_point_step=26,
        minimum_points=1_000,
        maximum_points=100_000,
        exact_row_layout=True,
    )


def validate_velodyne_cloud(message: Any) -> int:
    require_frame_id(message, "hesai_lidar")
    if _integer(getattr(message, "height", None), "height") != 1:
        raise ReadinessError("converted XT16 cloud height must be 1")
    return _cloud_layout(
        message,
        fields_contract=VELODYNE_FIELDS,
        minimum_point_step=22,
        minimum_points=1_000,
        maximum_points=100_000,
        exact_row_layout=True,
    )


def validate_laser_map(message: Any) -> int:
    header = _header(message)
    if not str(getattr(header, "frame_id", "")):
        raise ReadinessError("/Laser_map frame_id is empty")
    header_stamp_seconds(message)
    width = _integer(getattr(message, "width", None), "width")
    height = _integer(getattr(message, "height", None), "height")
    point_step = _integer(getattr(message, "point_step", None), "point_step")
    row_step = _integer(getattr(message, "row_step", None), "row_step")
    if width < 0 or height < 0 or width > 10_000_000 or height > 4_096:
        raise ReadinessError("/Laser_map dimensions are outside the supported range")
    if point_step < 0 or point_step > 4_096 or row_step < 0 or row_step > 512 * 1024 * 1024:
        raise ReadinessError("/Laser_map byte layout is outside the supported range")
    try:
        data_length = len(getattr(message, "data", None))
    except (TypeError, AttributeError) as exc:
        raise ReadinessError("PointCloud2 data is missing") from exc
    if data_length > 512 * 1024 * 1024:
        raise ReadinessError("/Laser_map data exceeds the supported range")
    if width * height == 0:
        if data_length != 0:
            raise ReadinessError("empty /Laser_map placeholder contains unexpected data")
        return 0
    return _cloud_layout(
        message,
        fields_contract=(
            FieldContract("x", 0, FLOAT32),
            FieldContract("y", 4, FLOAT32),
            FieldContract("z", 8, FLOAT32),
        ),
        minimum_point_step=12,
        minimum_points=1,
        maximum_points=10_000_000,
        exact_row_layout=False,
    )


def observe_laser_map(
    gate: "FreshSequenceGate",
    message: Any,
    *,
    received_at: float,
    publisher: Hashable,
    host_now_s: float | None = None,
) -> bool:
    """Ignore a safe startup placeholder until FAST-LIO publishes real map data."""

    points = validate_laser_map(message)
    if points == 0:
        return False
    return gate.observe(
        stamp=header_stamp_seconds(message),
        received_at=received_at,
        publisher=publisher,
        item_count=points,
        host_now_s=host_now_s,
    )


def xt16_scan_timestamp(message: Any) -> float:
    """Read the absolute double timestamp consumed by the conversion bridge."""

    data = getattr(message, "data", None)
    try:
        value = float(struct.unpack_from("<d", data, 18)[0])
    except (TypeError, struct.error) as exc:
        raise ReadinessError("first XT16 payload timestamp cannot be decoded") from exc
    if not math.isfinite(value) or value <= 0:
        raise ReadinessError("first XT16 payload timestamp is not positive and finite")
    return value


def publisher_identity(
    publishers: Sequence[Any],
    *,
    topic: str,
    expected_type: str,
    reliable_policy: Any,
    volatile_policy: Any,
) -> Hashable:
    """Validate one reliable/volatile publisher and return its stable DDS GID."""

    if len(publishers) != 1:
        raise ReadinessError(
            f"{topic} requires exactly one publisher; found {len(publishers)}"
        )
    info = publishers[0]
    actual_type = str(getattr(info, "topic_type", ""))
    if actual_type != expected_type:
        raise ReadinessError(
            f"{topic} publisher type is {actual_type!r}; expected {expected_type!r}"
        )
    qos = getattr(info, "qos_profile", None)
    if getattr(qos, "reliability", None) != reliable_policy:
        raise ReadinessError(f"{topic} publisher must offer reliable QoS")
    if getattr(qos, "durability", None) != volatile_policy:
        raise ReadinessError(f"{topic} publisher must use volatile durability")
    raw_gid = getattr(info, "endpoint_gid", None)
    try:
        gid = tuple(int(value) for value in raw_gid)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReadinessError(f"{topic} publisher GID is unavailable") from exc
    if not gid:
        raise ReadinessError(f"{topic} publisher GID is empty")
    return gid


class FreshSequenceGate:
    """Accept only a recent window from one publisher with increasing stamps."""

    def __init__(
        self,
        *,
        required_frames: int,
        max_gap_seconds: float,
        minimum_rate_hz: float,
    ) -> None:
        if required_frames < 1 or required_frames > 20:
            raise ValueError("required_frames must be between 1 and 20")
        if not math.isfinite(max_gap_seconds) or not 0.05 <= max_gap_seconds <= 5.0:
            raise ValueError("max_gap_seconds must be between 0.05 and 5.0")
        if not math.isfinite(minimum_rate_hz) or not 0 <= minimum_rate_hz <= 1000:
            raise ValueError("minimum_rate_hz must be between 0 and 1000")
        self.required_frames = int(required_frames)
        self.max_gap_seconds = float(max_gap_seconds)
        self.minimum_rate_hz = float(minimum_rate_hz)
        self.arrivals: deque[float] = deque(maxlen=self.required_frames)
        self.stamps: deque[float] = deque(maxlen=self.required_frames)
        self.total_frames = 0
        self.last_stamp: Optional[float] = None
        self.last_arrival: Optional[float] = None
        self.last_publisher: Optional[Hashable] = None
        self.last_reset_reason: Optional[str] = None
        self.last_item_count = 0
        self.last_header_age_s: Optional[float] = None

    @property
    def consecutive_frames(self) -> int:
        return len(self.arrivals)

    @property
    def observed_rate_hz(self) -> float:
        if len(self.arrivals) < 2:
            return 0.0
        span = self.arrivals[-1] - self.arrivals[0]
        return math.inf if span <= 0 else (len(self.arrivals) - 1) / span

    @property
    def observed_stamp_rate_hz(self) -> float:
        if len(self.stamps) < 2:
            return 0.0
        span = self.stamps[-1] - self.stamps[0]
        return math.inf if span <= 0 else (len(self.stamps) - 1) / span

    @property
    def ready(self) -> bool:
        if len(self.arrivals) < self.required_frames:
            return False
        return self.required_frames == 1 or (
            self.observed_rate_hz >= self.minimum_rate_hz
            and self.observed_stamp_rate_hz >= self.minimum_rate_hz
        )

    def observe(
        self,
        *,
        stamp: float,
        received_at: float,
        publisher: Hashable,
        item_count: int = 0,
        host_now_s: float | None = None,
        header_age_s: float | None = None,
        require_host_age: bool = True,
    ) -> bool:
        if not math.isfinite(float(stamp)) or not math.isfinite(received_at):
            raise ReadinessError("message stamp and arrival time must be finite")
        if not require_host_age:
            self.last_header_age_s = None
        elif header_age_s is None:
            observed_host_s = float(stamp) if host_now_s is None else float(host_now_s)
            self.last_header_age_s = require_absolute_stamp_age(
                float(stamp), host_now_s=observed_host_s, label="readiness"
            )
        elif not math.isfinite(float(header_age_s)):
            raise ReadinessError("message header age must be finite")
        else:
            self.last_header_age_s = float(header_age_s)
        self.total_frames += 1
        reset_reason: Optional[str] = None
        if self.last_publisher is not None and publisher != self.last_publisher:
            reset_reason = "publisher GID changed"
        elif self.last_stamp is not None and float(stamp) <= self.last_stamp:
            reset_reason = "message timestamp did not increase"
        elif self.last_stamp is not None and float(stamp) - self.last_stamp > self.max_gap_seconds:
            reset_reason = f"message timestamp gap exceeded {self.max_gap_seconds:.2f}s"
        elif self.last_arrival is not None and received_at - self.last_arrival > self.max_gap_seconds:
            reset_reason = f"inter-frame gap exceeded {self.max_gap_seconds:.2f}s"
        if reset_reason is not None:
            self.arrivals.clear()
            self.stamps.clear()
        self.arrivals.append(received_at)
        self.stamps.append(float(stamp))
        self.last_stamp = float(stamp)
        self.last_arrival = received_at
        self.last_publisher = publisher
        self.last_item_count = int(item_count)
        self.last_reset_reason = reset_reason
        return self.ready

    def ready_at(self, now: float) -> bool:
        return bool(
            self.ready
            and self.last_arrival is not None
            and 0.0 <= now - self.last_arrival <= self.max_gap_seconds
        )


class Xt16ReadinessGate(FreshSequenceGate):
    """Validate raw clouds and require a sustained fresh scan rate."""

    def __init__(self) -> None:
        super().__init__(required_frames=5, max_gap_seconds=0.35, minimum_rate_hz=5.0)

    def observe_cloud(
        self,
        message: Any,
        *,
        received_at: float,
        publisher: Hashable,
    ) -> bool:
        points = validate_xt16_cloud(message)
        payload_stamp = xt16_scan_timestamp(message)
        if (
            abs(header_stamp_seconds(message) - payload_stamp)
            > RAW_HEADER_SCAN_START_TOLERANCE_S
        ):
            raise ReadinessError(
                "/lidar_points header does not match the device scan start"
            )
        return self.observe(
            stamp=payload_stamp,
            received_at=received_at,
            publisher=publisher,
            item_count=points,
            require_host_age=False,
        )


class StageState:
    def __init__(self, stage: str) -> None:
        self.stage = stage
        if stage == "raw":
            self.gates = {"/lidar_points": Xt16ReadinessGate()}
        elif stage == "imu":
            self.gates = {
                "/imu/body": FreshSequenceGate(
                    required_frames=5,
                    max_gap_seconds=0.20,
                    minimum_rate_hz=10.0,
                ),
            }
        elif stage == "bridge":
            self.gates = {
                "/velodyne_points": FreshSequenceGate(
                    required_frames=5,
                    max_gap_seconds=0.40,
                    minimum_rate_hz=4.0,
                ),
                "/imu/body": FreshSequenceGate(
                    required_frames=5,
                    max_gap_seconds=0.20,
                    minimum_rate_hz=10.0,
                ),
            }
        elif stage == "fastlio":
            self.gates = {
                "/Odometry": FreshSequenceGate(
                    required_frames=3,
                    max_gap_seconds=0.75,
                    minimum_rate_hz=2.0,
                ),
                "/Laser_map": FreshSequenceGate(
                    required_frames=1,
                    max_gap_seconds=5.0,
                    minimum_rate_hz=0.0,
                ),
            }
        else:
            raise ValueError(f"unsupported readiness stage: {stage}")

    @property
    def ready(self) -> bool:
        return all(gate.ready for gate in self.gates.values())

    def ready_at(self, now: float) -> bool:
        return all(gate.ready_at(now) for gate in self.gates.values())

    def summary(self, now: float | None = None) -> str:
        return ", ".join(
            f"{topic}={gate.consecutive_frames}/{gate.required_frames},"
            f"header_age_s={gate.last_header_age_s if gate.last_header_age_s is not None else float('nan'):.3f},"
            f"arrival_age_s={max(0.0, now - gate.last_arrival) if now is not None and gate.last_arrival is not None else float('nan'):.3f}"
            for topic, gate in self.gates.items()
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wait for a fixed XT16 mapping-pipeline readiness stage."
    )
    parser.add_argument(
        "--stage",
        choices=("raw", "imu", "bridge", "fastlio"),
        default="raw",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser


def _validate_options(options: argparse.Namespace) -> None:
    if not math.isfinite(options.timeout) or options.timeout < 1.0 or options.timeout > 90.0:
        raise ValueError("timeout must be between 1 and 90 seconds")


def wait_for_ros_stage(
    options: argparse.Namespace,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], float] = time.time,
) -> int:
    """Run one short-lived ROS stage probe; imports stay local for tests."""

    try:
        import rclpy
        from nav_msgs.msg import Odometry
        from rclpy.node import Node
        from rclpy.qos import (
            DurabilityPolicy,
            HistoryPolicy,
            QoSProfile,
            ReliabilityPolicy,
        )
        from sensor_msgs.msg import Imu, PointCloud2
    except ImportError as exc:
        print(f"[Robot Scope] mapping readiness cannot import ROS: {exc}", file=sys.stderr)
        return 2

    state = StageState(options.stage)
    fatal_error: list[str] = []

    class ReadinessNode(Node):
        def __init__(self) -> None:
            super().__init__(f"robot_scope_{options.stage}_readiness")
            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                # All accepted publishers are required to offer reliable QoS.
                # PointCloud2 samples are large enough to span many DDS
                # fragments, so the probe also requests reliability while a
                # depth of one prevents stale samples accumulating.
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            self._readiness_subscriptions = []
            if options.stage == "raw":
                self._readiness_subscriptions.append(
                    self.create_subscription(PointCloud2, "/lidar_points", self.on_raw, qos)
                )
            elif options.stage == "imu":
                self._readiness_subscriptions.append(
                    self.create_subscription(Imu, "/imu/body", self.on_imu, qos)
                )
            elif options.stage == "bridge":
                self._readiness_subscriptions.extend(
                    (
                        self.create_subscription(
                            PointCloud2, "/velodyne_points", self.on_velodyne, qos
                        ),
                        self.create_subscription(Imu, "/imu/body", self.on_imu, qos),
                    )
                )
            else:
                self._readiness_subscriptions.extend(
                    (
                        self.create_subscription(Odometry, "/Odometry", self.on_odometry, qos),
                        self.create_subscription(
                            PointCloud2, "/Laser_map", self.on_laser_map, qos
                        ),
                    )
                )

        def identity(self, topic: str, expected_type: str) -> Hashable:
            return publisher_identity(
                self.get_publishers_info_by_topic(topic),
                topic=topic,
                expected_type=expected_type,
                reliable_policy=ReliabilityPolicy.RELIABLE,
                volatile_policy=DurabilityPolicy.VOLATILE,
            )

        def fail(self, exc: ReadinessError) -> None:
            if not fatal_error:
                fatal_error.append(str(exc))

        def on_raw(self, message: Any) -> None:
            try:
                identity = self.identity("/lidar_points", POINTCLOUD_TYPE)
                gate = state.gates["/lidar_points"]
                assert isinstance(gate, Xt16ReadinessGate)
                gate.observe_cloud(
                    message,
                    received_at=monotonic(),
                    publisher=identity,
                )
            except ReadinessError as exc:
                self.fail(exc)

        def on_velodyne(self, message: Any) -> None:
            try:
                points = validate_velodyne_cloud(message)
                state.gates["/velodyne_points"].observe(
                    stamp=header_stamp_seconds(message),
                    received_at=monotonic(),
                    publisher=self.identity("/velodyne_points", POINTCLOUD_TYPE),
                    item_count=points,
                    host_now_s=wall_clock(),
                )
            except ReadinessError as exc:
                self.fail(exc)

        def on_imu(self, message: Any) -> None:
            try:
                require_frame_id(message, "body_imu")
                state.gates["/imu/body"].observe(
                    stamp=header_stamp_seconds(message),
                    received_at=monotonic(),
                    publisher=self.identity("/imu/body", IMU_TYPE),
                    host_now_s=wall_clock(),
                )
            except ReadinessError as exc:
                self.fail(exc)

        def on_odometry(self, message: Any) -> None:
            try:
                state.gates["/Odometry"].observe(
                    stamp=header_stamp_seconds(message),
                    received_at=monotonic(),
                    publisher=self.identity("/Odometry", ODOMETRY_TYPE),
                    host_now_s=wall_clock(),
                )
            except ReadinessError as exc:
                self.fail(exc)

        def on_laser_map(self, message: Any) -> None:
            try:
                identity = self.identity("/Laser_map", POINTCLOUD_TYPE)
                observe_laser_map(
                    state.gates["/Laser_map"],
                    message,
                    received_at=monotonic(),
                    publisher=identity,
                    host_now_s=wall_clock(),
                )
            except ReadinessError as exc:
                self.fail(exc)

    rclpy.init(args=None)
    node: Optional[Any] = None
    try:
        node = ReadinessNode()
        deadline = monotonic() + options.timeout
        while not state.ready_at(monotonic()) and not fatal_error and monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        if fatal_error:
            print(
                f"[Robot Scope] {options.stage} readiness rejected: {fatal_error[0]}",
                file=sys.stderr,
            )
            return 3
        final_now = monotonic()
        final_ready = state.ready_at(final_now)
        if not final_ready:
            print(
                f"[Robot Scope] {options.stage} readiness timed out after "
                f"{options.timeout:.1f}s ({state.summary(final_now)})",
                file=sys.stderr,
            )
            return 4
        print(
            f"[Robot Scope] {options.stage} readiness verified "
            f"({state.summary(final_now)})"
        )
        return 0
    except KeyboardInterrupt:
        return 130
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _parser()
    options = parser.parse_args(argv)
    try:
        _validate_options(options)
        StageState(options.stage)
    except ValueError as exc:
        parser.error(str(exc))
    return wait_for_ros_stage(options)


if __name__ == "__main__":
    raise SystemExit(main())
