"""Fixed ROS 2 Humble localization and XT16 scan runtime for Robot Scope.

This module deliberately keeps the HTTP-facing dashboard out of the sensor
and transform path.  It consumes only the fixed ROS topics documented below,
normalizes them into the frames expected by Nav2, and exposes a fail-closed
health signal that the signed control transport can use as an interlock.

Inputs
------
``/velodyne_points`` (``sensor_msgs/msg/PointCloud2``)
    Projected to the fixed ``/scan`` topic without relying on the optional
    ``pointcloud_to_laserscan`` package.
``/Odometry`` (``nav_msgs/msg/Odometry``)
    Re-broadcast as ``odom -> base_link``.
``/initialpose`` (``geometry_msgs/msg/PoseWithCovarianceStamped``)
    Establishes ``map -> odom`` from the latest, fresh odometry sample.

The pure projection and planar-transform helpers are intentionally importable
on machines that do not have ROS installed.  ROS imports occur only when
``main`` constructs the runtime node.
"""

from __future__ import annotations

import argparse
import json
import math
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


POINT_FIELD_DTYPES: Mapping[int, str] = {
    1: "i1",  # INT8
    2: "u1",  # UINT8
    3: "i2",  # INT16
    4: "u2",  # UINT16
    5: "i4",  # INT32
    6: "u4",  # UINT32
    7: "f4",  # FLOAT32
    8: "f8",  # FLOAT64
}


class NavigationRuntimeError(ValueError):
    """Raised when an incoming sensor layout or transform is unsafe."""


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise NavigationRuntimeError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise NavigationRuntimeError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise NavigationRuntimeError(f"{label} must be finite")
    return number


def normalize_angle(value: float) -> float:
    """Return an angle in ``[-pi, pi)`` and reject non-finite input."""

    angle = _finite_number(value, "angle")
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def normalize_frame_id(value: Any) -> str:
    """Normalize ROS's optional leading slash without accepting aliases."""

    if not isinstance(value, str):
        return ""
    return value[1:] if value.startswith("/") else value


def odometry_frames_are_expected(parent_frame: Any, child_frame: Any) -> bool:
    return (
        normalize_frame_id(parent_frame) == "camera_init"
        and normalize_frame_id(child_frame) == "body"
    )


def bounded_pose_position(
    x: Any,
    y: Any,
    z: Any,
    *,
    horizontal_limit: float = 10_000.0,
    vertical_limit: float = 100.0,
) -> tuple[float, float, float]:
    """Validate a sensor pose before it enters the TF tree."""

    values = (
        _finite_number(x, "pose x"),
        _finite_number(y, "pose y"),
        _finite_number(z, "pose z"),
    )
    if abs(values[0]) > horizontal_limit or abs(values[1]) > horizontal_limit:
        raise NavigationRuntimeError("pose exceeds the supported horizontal bounds")
    if abs(values[2]) > vertical_limit:
        raise NavigationRuntimeError("pose exceeds the supported vertical bounds")
    return values


@dataclass(frozen=True)
class PlanarTransform:
    """A rigid two-dimensional transform represented as ``x, y, yaw``."""

    x: float
    y: float
    yaw: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite_number(self.x, "x"))
        object.__setattr__(self, "y", _finite_number(self.y, "y"))
        object.__setattr__(self, "yaw", normalize_angle(self.yaw))

    def compose(self, other: "PlanarTransform") -> "PlanarTransform":
        """Compose ``self`` with ``other`` (``T_a_c = T_a_b * T_b_c``)."""

        cosine = math.cos(self.yaw)
        sine = math.sin(self.yaw)
        return PlanarTransform(
            self.x + cosine * other.x - sine * other.y,
            self.y + sine * other.x + cosine * other.y,
            self.yaw + other.yaw,
        )

    def inverse(self) -> "PlanarTransform":
        cosine = math.cos(self.yaw)
        sine = math.sin(self.yaw)
        return PlanarTransform(
            -cosine * self.x - sine * self.y,
            sine * self.x - cosine * self.y,
            -self.yaw,
        )


def map_to_odom_transform(
    initial_map_to_base: PlanarTransform,
    current_odom_to_base: PlanarTransform,
) -> PlanarTransform:
    """Solve ``T_map_odom`` from an initial base pose and current odometry."""

    return initial_map_to_base.compose(current_odom_to_base.inverse())


def odometry_discontinuity_reason(
    previous: PlanarTransform,
    current: PlanarTransform,
    elapsed_s: float,
) -> str:
    """Detect a FAST-LIO reset without rejecting ordinary high-rate jitter."""

    elapsed = _finite_number(elapsed_s, "odometry elapsed time")
    if elapsed <= 0.0 or elapsed > 2.0:
        return "odometry timing is discontinuous"
    distance = math.hypot(current.x - previous.x, current.y - previous.y)
    heading = abs(normalize_angle(current.yaw - previous.yaw))
    # These are deliberately far above the dashboard motion envelope.  They
    # catch estimator resets/jumps while tolerating packet jitter and a rough
    # FAST-LIO pose during normal walking.
    if distance > 0.25 + 5.0 * elapsed:
        return "odometry translation jumped"
    if heading > 0.35 + 8.0 * elapsed:
        return "odometry heading jumped"
    return ""


def quaternion_to_yaw(x: float, y: float, z: float, w: float) -> float:
    """Normalize a quaternion and return its planar yaw component."""

    values = np.asarray(
        [
            _finite_number(x, "quaternion x"),
            _finite_number(y, "quaternion y"),
            _finite_number(z, "quaternion z"),
            _finite_number(w, "quaternion w"),
        ],
        dtype=np.float64,
    )
    norm = float(np.linalg.norm(values))
    if norm < 0.5 or norm > 1.5:
        raise NavigationRuntimeError("quaternion norm is outside the supported range")
    x_value, y_value, z_value, w_value = values / norm
    return normalize_angle(
        math.atan2(
            2.0 * (w_value * z_value + x_value * y_value),
            1.0 - 2.0 * (y_value * y_value + z_value * z_value),
        )
    )


def yaw_to_quaternion(yaw: float) -> tuple[float, float, float, float]:
    half = normalize_angle(yaw) * 0.5
    return (0.0, 0.0, math.sin(half), math.cos(half))


@dataclass(frozen=True)
class ScanGeometry:
    """Trusted geometry and filtering limits for PointCloud2 projection."""

    angle_min: float = -math.pi
    angle_max: float = math.pi
    bins: int = 1441
    range_min: float = 0.15
    range_max: float = 20.0
    z_min: float = -0.5
    z_max: float = 2.0

    def __post_init__(self) -> None:
        angle_min = _finite_number(self.angle_min, "angle_min")
        angle_max = _finite_number(self.angle_max, "angle_max")
        range_min = _finite_number(self.range_min, "range_min")
        range_max = _finite_number(self.range_max, "range_max")
        z_min = _finite_number(self.z_min, "z_min")
        z_max = _finite_number(self.z_max, "z_max")
        if not isinstance(self.bins, int) or isinstance(self.bins, bool):
            raise NavigationRuntimeError("bins must be an integer")
        if self.bins < 2 or self.bins > 65_536:
            raise NavigationRuntimeError("bins must be between 2 and 65536")
        if angle_min >= angle_max or angle_max - angle_min > 2.0 * math.pi + 1e-9:
            raise NavigationRuntimeError("scan angles must form a valid arc")
        if range_min <= 0.0 or range_min >= range_max:
            raise NavigationRuntimeError("scan range limits are invalid")
        if z_min >= z_max:
            raise NavigationRuntimeError("scan height limits are invalid")
        object.__setattr__(self, "angle_min", angle_min)
        object.__setattr__(self, "angle_max", angle_max)
        object.__setattr__(self, "range_min", range_min)
        object.__setattr__(self, "range_max", range_max)
        object.__setattr__(self, "z_min", z_min)
        object.__setattr__(self, "z_max", z_max)

    @property
    def angle_increment(self) -> float:
        return (self.angle_max - self.angle_min) / float(self.bins - 1)


@dataclass(frozen=True)
class ScanProjection:
    ranges: np.ndarray
    input_points: int
    accepted_points: int


@dataclass(frozen=True)
class RuntimeFilterSettings:
    """Validated scan-projection settings derived from the private job YAML."""

    z_min: float
    z_max: float
    range_min: float
    range_max: float


RUNTIME_PARAMETER_KEYS = frozenset(
    {
        "scan_topic",
        "odom_topic",
        "cmd_vel_topic",
        "min_obstacle_height",
        "max_obstacle_height",
        "obstacle_max_range",
        "raytrace_max_range",
    }
)


def load_runtime_filter_settings(path: str | Path) -> RuntimeFilterSettings:
    """Load only the allowlisted runtime sidecar from a Nav2 params snapshot.

    The navigation manager owns this regular-file snapshot.  Fixed topic names
    are assertions, not configurable routing: any mismatch aborts startup.
    """

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - exercised on Jetson startup
        raise NavigationRuntimeError("PyYAML is required for navigation params") from exc

    params_path = Path(path)
    try:
        if params_path.is_symlink() or not params_path.is_file():
            raise NavigationRuntimeError("runtime params must be a regular file")
        if params_path.stat().st_size > 2 * 1024 * 1024:
            raise NavigationRuntimeError("runtime params file is too large")
        document = yaml.safe_load(params_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise NavigationRuntimeError(f"could not read runtime params: {exc}") from exc
    if not isinstance(document, Mapping):
        raise NavigationRuntimeError("runtime params root must be a mapping")
    node = document.get("robot_scope_navigation_runtime")
    if not isinstance(node, Mapping) or set(node) != {"ros__parameters"}:
        raise NavigationRuntimeError("runtime params node is missing or has extra keys")
    values = node.get("ros__parameters")
    if not isinstance(values, Mapping) or set(values) != RUNTIME_PARAMETER_KEYS:
        raise NavigationRuntimeError("runtime parameter allowlist does not match")

    fixed_topics = {
        "scan_topic": "/scan",
        "odom_topic": "/Odometry",
        "cmd_vel_topic": "/robot_scope/nav/cmd_vel_raw",
    }
    for key, expected in fixed_topics.items():
        if values.get(key) != expected:
            raise NavigationRuntimeError(f"{key} must remain fixed at {expected}")

    z_min = _finite_number(values.get("min_obstacle_height"), "min_obstacle_height")
    z_max = _finite_number(values.get("max_obstacle_height"), "max_obstacle_height")
    obstacle_range = _finite_number(values.get("obstacle_max_range"), "obstacle_max_range")
    raytrace_range = _finite_number(values.get("raytrace_max_range"), "raytrace_max_range")
    if z_min < -2.0 or z_min > 1.0 or z_max < 0.1 or z_max > 3.0 or z_min >= z_max:
        raise NavigationRuntimeError("runtime obstacle height limits are invalid")
    if obstacle_range < 0.5 or obstacle_range > 12.0:
        raise NavigationRuntimeError("runtime obstacle range is invalid")
    if raytrace_range < obstacle_range or raytrace_range > 20.0:
        raise NavigationRuntimeError("runtime raytrace range is invalid")
    settings = RuntimeFilterSettings(
        z_min=z_min,
        z_max=z_max,
        range_min=0.4,
        range_max=max(obstacle_range, raytrace_range),
    )
    # Reuse the projection validator for all cross-field invariants.
    ScanGeometry(
        range_min=settings.range_min,
        range_max=settings.range_max,
        z_min=settings.z_min,
        z_max=settings.z_max,
    )
    return settings


def project_xyz_to_scan(xyz: np.ndarray, geometry: ScanGeometry) -> ScanProjection:
    """Project an ``N x 3`` XYZ array to nearest-range angular bins.

    All filters are vectorized and ``numpy.minimum.at`` performs the only
    scatter operation.  Bins without a valid return contain positive infinity,
    matching ``sensor_msgs/msg/LaserScan`` conventions.
    """

    points = np.asarray(xyz)
    if points.ndim != 2 or points.shape[1] < 3:
        raise NavigationRuntimeError("point cloud must be an N x 3 array")
    input_points = int(points.shape[0])
    ranges = np.full(geometry.bins, np.inf, dtype=np.float32)
    if input_points == 0:
        return ScanProjection(ranges, 0, 0)

    coordinates = points[:, :3]
    if not (
        np.issubdtype(coordinates.dtype, np.floating)
        or np.issubdtype(coordinates.dtype, np.integer)
    ):
        raise NavigationRuntimeError("point cloud coordinates must be numeric")
    finite = np.isfinite(coordinates).all(axis=1)
    height = coordinates[:, 2]
    planar_range = np.hypot(coordinates[:, 0], coordinates[:, 1])
    angles = np.arctan2(coordinates[:, 1], coordinates[:, 0])
    angle_tolerance = max(1.0e-7, geometry.angle_increment * 1.0e-6)
    valid = (
        finite
        & (height >= geometry.z_min)
        & (height <= geometry.z_max)
        & (planar_range >= geometry.range_min)
        & (planar_range <= geometry.range_max)
        & (angles >= geometry.angle_min - angle_tolerance)
        & (angles <= geometry.angle_max + angle_tolerance)
    )
    if not np.any(valid):
        return ScanProjection(ranges, input_points, 0)

    valid_angles = np.clip(angles[valid], geometry.angle_min, geometry.angle_max)
    valid_ranges = planar_range[valid].astype(np.float32, copy=False)
    indices = np.floor(
        (valid_angles - geometry.angle_min) / geometry.angle_increment + 1.0e-6
    ).astype(np.int64)
    np.clip(indices, 0, geometry.bins - 1, out=indices)
    np.minimum.at(ranges, indices, valid_ranges)
    return ScanProjection(ranges, input_points, int(valid_ranges.size))


def _field_value(field: Any, name: str) -> Any:
    if isinstance(field, Mapping):
        return field.get(name)
    return getattr(field, name, None)


def xyz_from_pointcloud2_layout(
    data: bytes | bytearray | memoryview,
    *,
    fields: Iterable[Any],
    width: int,
    height: int,
    point_step: int,
    row_step: int,
    is_bigendian: bool,
) -> np.ndarray:
    """Decode the x/y/z fields of a PointCloud2-compatible binary layout.

    ``fields`` may contain ROS ``PointField`` instances or mappings with
    ``name``, ``offset``, ``datatype`` and ``count`` keys.  Organized clouds
    with row padding are handled through NumPy strides without copying the full
    message buffer.
    """

    dimensions = {
        "width": width,
        "height": height,
        "point_step": point_step,
        "row_step": row_step,
    }
    for label, value in dimensions.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise NavigationRuntimeError(f"{label} must be a non-negative integer")
    if width == 0 or height == 0:
        return np.empty((0, 3), dtype=np.float32)
    if width * height > 20_000_000:
        raise NavigationRuntimeError("PointCloud2 exceeds the supported point count")
    if point_step <= 0 or point_step > 4096 or row_step < width * point_step:
        raise NavigationRuntimeError("PointCloud2 strides are invalid")
    required_bytes = (height - 1) * row_step + width * point_step
    buffer = memoryview(data)
    if buffer.nbytes < required_bytes:
        raise NavigationRuntimeError("PointCloud2 data is shorter than its layout")

    selected: dict[str, tuple[int, str]] = {}
    endian = ">" if bool(is_bigendian) else "<"
    for field in fields:
        name = _field_value(field, "name")
        if name not in {"x", "y", "z"}:
            continue
        if name in selected:
            raise NavigationRuntimeError(f"PointCloud2 field {name!r} is duplicated")
        offset = _field_value(field, "offset")
        datatype = _field_value(field, "datatype")
        count = _field_value(field, "count")
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or offset < 0
            or isinstance(datatype, bool)
            or not isinstance(datatype, int)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count != 1
        ):
            raise NavigationRuntimeError(f"PointCloud2 field {name!r} is invalid")
        scalar = POINT_FIELD_DTYPES.get(datatype)
        if scalar not in {"f4", "f8"}:
            raise NavigationRuntimeError(f"PointCloud2 field {name!r} must be float32/64")
        dtype = np.dtype(endian + scalar)
        if offset + dtype.itemsize > point_step:
            raise NavigationRuntimeError(f"PointCloud2 field {name!r} exceeds point_step")
        selected[str(name)] = (offset, dtype.str)
    if set(selected) != {"x", "y", "z"}:
        raise NavigationRuntimeError("PointCloud2 must contain x, y and z fields")
    if len({selected[name][0] for name in ("x", "y", "z")}) != 3:
        raise NavigationRuntimeError("PointCloud2 x, y and z fields overlap")

    dtype = np.dtype(
        {
            "names": ["x", "y", "z"],
            "formats": [selected[name][1] for name in ("x", "y", "z")],
            "offsets": [selected[name][0] for name in ("x", "y", "z")],
            "itemsize": point_step,
        }
    )
    structured = np.ndarray(
        shape=(height, width),
        dtype=dtype,
        buffer=buffer,
        strides=(row_step, point_step),
    )
    flattened = structured.reshape(-1) if row_step == width * point_step else structured.ravel()
    return np.column_stack(
        (flattened["x"], flattened["y"], flattened["z"])
    ).astype(np.float32, copy=False)


def _stamp_seconds(stamp: Any) -> float:
    return float(getattr(stamp, "sec", 0)) + float(getattr(stamp, "nanosec", 0)) * 1e-9


def _message_stamp_is_fresh(node: Any, message: Any, timeout_s: float) -> bool:
    stamp = getattr(getattr(message, "header", None), "stamp", None)
    source_seconds = _stamp_seconds(stamp)
    if source_seconds <= 0.0:
        return False
    now_seconds = float(node.get_clock().now().nanoseconds) * 1e-9
    age = now_seconds - source_seconds
    return -0.25 <= age <= timeout_s


def _build_ros_runtime_node_class() -> type[Any]:
    """Import ROS lazily and construct the runtime Node class."""

    from geometry_msgs.msg import PoseWithCovarianceStamped, TransformStamped
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import (
        DurabilityPolicy,
        HistoryPolicy,
        QoSProfile,
        ReliabilityPolicy,
        qos_profile_sensor_data,
    )
    from sensor_msgs.msg import LaserScan, PointCloud2
    from std_msgs.msg import String
    from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster

    class NavigationRuntimeNode(Node):
        """ROS adapter around the pure scan and transform helpers."""

        def __init__(self, options: argparse.Namespace) -> None:
            super().__init__("robot_scope_navigation_runtime")
            self._options = options
            self._geometry = ScanGeometry(
                bins=options.scan_bins,
                range_min=options.range_min,
                range_max=options.range_max,
                z_min=options.z_min,
                z_max=options.z_max,
            )
            self._last_cloud_monotonic = 0.0
            self._last_odom_monotonic = 0.0
            self._last_cloud_error = "waiting for /velodyne_points"
            self._last_odom_error = "waiting for /Odometry"
            self._odom_frame_error = ""
            self._publisher_counts = {
                "/velodyne_points": 0,
                "/Odometry": 0,
                "/initialpose": 0,
            }
            self._odom_to_base: PlanarTransform | None = None
            self._odom_z = 0.0
            self._odom_quaternion = (0.0, 0.0, 0.0, 1.0)
            self._map_to_odom: PlanarTransform | None = None
            self._pose_covariance = [0.0] * 36
            self._last_scan_counts = (0, 0)
            self._last_scan_bins = 0

            self._scan_publisher = self.create_publisher(
                LaserScan, "/scan", qos_profile_sensor_data
            )
            self._pose_publisher = self.create_publisher(
                PoseWithCovarianceStamped, "/amcl_pose", 10
            )
            health_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            self._health_publisher = self.create_publisher(
                String, "/robot_scope/nav/runtime_health", health_qos
            )
            self._tf_broadcaster = TransformBroadcaster(self)
            self._static_tf_broadcaster = StaticTransformBroadcaster(self)

            self.create_subscription(
                PointCloud2,
                "/velodyne_points",
                self._on_cloud,
                qos_profile_sensor_data,
            )
            self.create_subscription(
                Odometry,
                "/Odometry",
                self._on_odometry,
                qos_profile_sensor_data,
            )
            self.create_subscription(
                PoseWithCovarianceStamped,
                "/initialpose",
                self._on_initial_pose,
                10,
            )
            self.create_timer(0.1, self._on_health_timer)
            self._publish_static_lidar_transform(TransformStamped)
            self.get_logger().info(
                "fixed navigation runtime ready: /velodyne_points -> /scan; "
                "/Odometry -> odom/base_link"
            )

        def _publish_static_lidar_transform(self, transform_type: type[Any]) -> None:
            transform = transform_type()
            transform.header.stamp = self.get_clock().now().to_msg()
            transform.header.frame_id = "base_link"
            transform.child_frame_id = self._options.cloud_frame
            transform.transform.translation.x = self._options.lidar_x
            transform.transform.translation.y = self._options.lidar_y
            transform.transform.translation.z = self._options.lidar_z
            qx, qy, qz, qw = yaw_to_quaternion(self._options.lidar_yaw)
            transform.transform.rotation.x = qx
            transform.transform.rotation.y = qy
            transform.transform.rotation.z = qz
            transform.transform.rotation.w = qw
            self._static_tf_broadcaster.sendTransform(transform)

        def _on_cloud(self, message: Any) -> None:
            if self._publisher_counts["/velodyne_points"] != 1:
                self._last_cloud_monotonic = 0.0
                self._last_cloud_error = "PointCloud2 source is not unique"
                return
            frame_id = normalize_frame_id(getattr(message.header, "frame_id", ""))
            if frame_id != self._options.cloud_frame:
                self._last_cloud_monotonic = 0.0
                self._last_cloud_error = (
                    f"unexpected cloud frame {frame_id!r}; expected "
                    f"{self._options.cloud_frame!r}"
                )
                return
            if not _message_stamp_is_fresh(self, message, self._options.cloud_timeout):
                self._last_cloud_monotonic = 0.0
                self._last_cloud_error = "stale or missing PointCloud2 timestamp"
                return
            try:
                xyz = xyz_from_pointcloud2_layout(
                    message.data,
                    fields=message.fields,
                    width=int(message.width),
                    height=int(message.height),
                    point_step=int(message.point_step),
                    row_step=int(message.row_step),
                    is_bigendian=bool(message.is_bigendian),
                )
                projection = project_xyz_to_scan(xyz, self._geometry)
            except (NavigationRuntimeError, TypeError, ValueError) as exc:
                self._last_cloud_monotonic = 0.0
                self._last_cloud_error = str(exc)[:200]
                return

            finite_bins = int(np.count_nonzero(np.isfinite(projection.ranges)))
            self._last_scan_counts = (
                projection.input_points,
                projection.accepted_points,
            )
            self._last_scan_bins = finite_bins
            if finite_bins < 3:
                self._last_cloud_monotonic = 0.0
                self._last_cloud_error = "PointCloud2 produced fewer than three scan bins"
                return

            scan = LaserScan()
            scan.header.stamp = message.header.stamp
            scan.header.frame_id = self._options.cloud_frame
            scan.angle_min = self._geometry.angle_min
            scan.angle_max = self._geometry.angle_max
            scan.angle_increment = self._geometry.angle_increment
            scan.time_increment = 0.0
            scan.scan_time = 0.0
            scan.range_min = self._geometry.range_min
            scan.range_max = self._geometry.range_max
            scan.ranges = projection.ranges.tolist()
            self._scan_publisher.publish(scan)
            self._last_cloud_monotonic = time.monotonic()
            self._last_cloud_error = ""

        def _on_odometry(self, message: Any) -> None:
            if self._publisher_counts["/Odometry"] != 1:
                self._last_odom_monotonic = 0.0
                self._last_odom_error = "Odometry source is not unique"
                return
            parent_frame = normalize_frame_id(getattr(message.header, "frame_id", ""))
            child_frame = normalize_frame_id(getattr(message, "child_frame_id", ""))
            if not odometry_frames_are_expected(parent_frame, child_frame):
                self._last_odom_monotonic = 0.0
                self._odom_frame_error = (
                    f"unexpected Odometry frames {parent_frame!r}->{child_frame!r}; "
                    "expected 'camera_init'->'body'"
                )
                self._last_odom_error = self._odom_frame_error
                return
            if not _message_stamp_is_fresh(self, message, self._options.odom_timeout):
                self._last_odom_monotonic = 0.0
                self._last_odom_error = "stale or missing Odometry timestamp"
                return
            pose = message.pose.pose
            try:
                x_value, y_value, z_value = bounded_pose_position(
                    pose.position.x,
                    pose.position.y,
                    pose.position.z,
                )
                yaw = quaternion_to_yaw(
                    pose.orientation.x,
                    pose.orientation.y,
                    pose.orientation.z,
                    pose.orientation.w,
                )
                odom_to_base = PlanarTransform(x_value, y_value, yaw)
            except NavigationRuntimeError as exc:
                self._last_odom_monotonic = 0.0
                self._last_odom_error = str(exc)[:200]
                return

            now = time.monotonic()
            previous = self._odom_to_base
            previous_at = self._last_odom_monotonic
            if previous is not None and previous_at > 0.0:
                elapsed = now - previous_at
                if elapsed > self._options.odom_timeout:
                    # A localization outage requires a new operator-approved
                    # initial pose; never silently reuse the old map alignment.
                    self._map_to_odom = None
                else:
                    discontinuity = odometry_discontinuity_reason(
                        previous,
                        odom_to_base,
                        elapsed,
                    )
                    if discontinuity:
                        self._last_odom_monotonic = 0.0
                        self._last_odom_error = discontinuity
                        self._odom_to_base = None
                        self._map_to_odom = None
                        return

            self._odom_to_base = odom_to_base
            self._odom_z = z_value
            self._odom_quaternion = yaw_to_quaternion(yaw)
            self._last_odom_monotonic = now
            self._last_odom_error = ""
            self._odom_frame_error = ""
            self._broadcast_dynamic_transforms()

        def _on_initial_pose(self, message: Any) -> None:
            if self._publisher_counts["/initialpose"] != 1:
                self.get_logger().warning(
                    "rejected /initialpose because its publisher is not unique"
                )
                return
            frame_id = normalize_frame_id(getattr(message.header, "frame_id", ""))
            if frame_id != "map":
                self.get_logger().warning("rejected /initialpose outside the map frame")
                return
            if not self._odom_fresh():
                self.get_logger().warning("rejected /initialpose without fresh odometry")
                return
            pose = message.pose.pose
            try:
                x_value, y_value, _ = bounded_pose_position(
                    pose.position.x,
                    pose.position.y,
                    pose.position.z,
                )
                initial = PlanarTransform(
                    x_value,
                    y_value,
                    quaternion_to_yaw(
                        pose.orientation.x,
                        pose.orientation.y,
                        pose.orientation.z,
                        pose.orientation.w,
                    ),
                )
            except NavigationRuntimeError as exc:
                self.get_logger().warning(f"rejected invalid /initialpose: {exc}")
                return
            assert self._odom_to_base is not None
            self._map_to_odom = map_to_odom_transform(initial, self._odom_to_base)
            covariance = list(message.pose.covariance)
            if len(covariance) == 36 and all(math.isfinite(float(v)) for v in covariance):
                self._pose_covariance = [float(v) for v in covariance]
            self._broadcast_dynamic_transforms()
            self.get_logger().info("accepted initial pose; map -> odom is active")

        def _cloud_fresh(self) -> bool:
            return (
                self._last_cloud_monotonic > 0.0
                and time.monotonic() - self._last_cloud_monotonic
                <= self._options.cloud_timeout
            )

        def _odom_fresh(self) -> bool:
            return (
                self._last_odom_monotonic > 0.0
                and time.monotonic() - self._last_odom_monotonic
                <= self._options.odom_timeout
            )

        def _broadcast_dynamic_transforms(self) -> None:
            if not self._odom_fresh() or self._odom_to_base is None:
                return
            now = self.get_clock().now().to_msg()
            odom_tf = TransformStamped()
            odom_tf.header.stamp = now
            odom_tf.header.frame_id = "odom"
            odom_tf.child_frame_id = "base_link"
            odom_tf.transform.translation.x = self._odom_to_base.x
            odom_tf.transform.translation.y = self._odom_to_base.y
            odom_tf.transform.translation.z = self._odom_z
            qx, qy, qz, qw = self._odom_quaternion
            odom_tf.transform.rotation.x = qx
            odom_tf.transform.rotation.y = qy
            odom_tf.transform.rotation.z = qz
            odom_tf.transform.rotation.w = qw
            self._tf_broadcaster.sendTransform(odom_tf)

            if self._map_to_odom is None:
                return
            map_tf = TransformStamped()
            map_tf.header.stamp = now
            map_tf.header.frame_id = "map"
            map_tf.child_frame_id = "odom"
            map_tf.transform.translation.x = self._map_to_odom.x
            map_tf.transform.translation.y = self._map_to_odom.y
            map_tf.transform.translation.z = 0.0
            qx, qy, qz, qw = yaw_to_quaternion(self._map_to_odom.yaw)
            map_tf.transform.rotation.x = qx
            map_tf.transform.rotation.y = qy
            map_tf.transform.rotation.z = qz
            map_tf.transform.rotation.w = qw
            self._tf_broadcaster.sendTransform(map_tf)

            map_pose = self._map_to_odom.compose(self._odom_to_base)
            pose_message = PoseWithCovarianceStamped()
            pose_message.header.stamp = now
            pose_message.header.frame_id = "map"
            pose_message.pose.pose.position.x = map_pose.x
            pose_message.pose.pose.position.y = map_pose.y
            pose_message.pose.pose.position.z = self._odom_z
            qx, qy, qz, qw = yaw_to_quaternion(map_pose.yaw)
            pose_message.pose.pose.orientation.x = qx
            pose_message.pose.pose.orientation.y = qy
            pose_message.pose.pose.orientation.z = qz
            pose_message.pose.pose.orientation.w = qw
            pose_message.pose.covariance = self._pose_covariance
            self._pose_publisher.publish(pose_message)

        def _on_health_timer(self) -> None:
            self._publisher_counts = {
                topic: int(self.count_publishers(topic))
                for topic in ("/velodyne_points", "/Odometry", "/initialpose")
            }
            cloud_fresh = self._cloud_fresh()
            odom_fresh = self._odom_fresh()
            localized = self._map_to_odom is not None and odom_fresh
            sensor_sources_unique = (
                self._publisher_counts["/velodyne_points"] == 1
                and self._publisher_counts["/Odometry"] == 1
            )
            source_error = ""
            if not sensor_sources_unique:
                source_error = (
                    "expected exactly one publisher for /velodyne_points and /Odometry"
                )
            if localized:
                self._broadcast_dynamic_transforms()
            input_points, accepted_points = self._last_scan_counts
            payload = {
                "schema": "robot-scope.navigation-runtime-health.v1",
                "ready": bool(
                    cloud_fresh and odom_fresh and localized and sensor_sources_unique
                ),
                "cloud_fresh": cloud_fresh,
                "odom_fresh": odom_fresh,
                "localized": localized,
                "cloud_topic": "/velodyne_points",
                "scan_topic": "/scan",
                "odometry_topic": "/Odometry",
                "cloud_frame": self._options.cloud_frame,
                "publisher_counts": dict(self._publisher_counts),
                "input_points": input_points,
                "accepted_points": accepted_points,
                "finite_scan_bins": self._last_scan_bins,
                "cloud_error": self._last_cloud_error if not cloud_fresh else "",
                "odom_error": self._last_odom_error if not odom_fresh else "",
                "odom_frame_error": self._odom_frame_error,
                "source_error": source_error,
            }
            message = String()
            message.data = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            self._health_publisher.publish(message)

    return NavigationRuntimeNode


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Robot Scope fixed Humble Nav2 runtime")
    parser.add_argument("--runtime-params-file", required=True)
    parser.add_argument("--cloud-frame", default="hesai_lidar")
    parser.add_argument("--lidar-x", type=float, default=0.25)
    parser.add_argument("--lidar-y", type=float, default=0.0)
    parser.add_argument("--lidar-z", type=float, default=0.0)
    parser.add_argument("--lidar-yaw", type=float, default=math.pi / 2.0)
    parser.add_argument("--scan-bins", type=int, default=1441)
    parser.add_argument("--cloud-timeout", type=float, default=0.75)
    parser.add_argument("--odom-timeout", type=float, default=0.50)
    return parser


def _validate_runtime_options(options: argparse.Namespace) -> None:
    if options.cloud_frame != "hesai_lidar":
        raise NavigationRuntimeError("cloud frame must match the trusted Hesai calibration")
    ScanGeometry(
        bins=options.scan_bins,
        range_min=options.range_min,
        range_max=options.range_max,
        z_min=options.z_min,
        z_max=options.z_max,
    )
    for label in ("lidar_x", "lidar_y", "lidar_z", "lidar_yaw"):
        _finite_number(getattr(options, label), label)
    if abs(options.lidar_x) > 2.0 or abs(options.lidar_y) > 2.0:
        raise NavigationRuntimeError("LiDAR horizontal calibration is out of bounds")
    if options.lidar_z < -1.0 or options.lidar_z > 3.0:
        raise NavigationRuntimeError("LiDAR vertical calibration is out of bounds")
    for label in ("cloud_timeout", "odom_timeout"):
        value = _finite_number(getattr(options, label), label)
        if value < 0.1 or value > 2.0:
            raise NavigationRuntimeError(f"{label} must be between 0.1 and 2 seconds")


def main(argv: Sequence[str] | None = None) -> int:
    options = build_argument_parser().parse_args(argv)
    try:
        filters = load_runtime_filter_settings(options.runtime_params_file)
        options.range_min = filters.range_min
        options.range_max = filters.range_max
        options.z_min = filters.z_min
        options.z_max = filters.z_max
        _validate_runtime_options(options)
        import rclpy
    except (ImportError, NavigationRuntimeError) as exc:
        print(f"[Robot Scope] navigation runtime unavailable: {exc}", file=sys.stderr)
        return 2

    node_type = _build_ros_runtime_node_class()
    # The wrapper's private params-snapshot flag is consumed above and must
    # never leak into rclpy's ROS argument parser.  This runtime intentionally
    # accepts no ROS remaps or topic overrides.
    rclpy.init(args=[])
    node = node_type(options)

    def request_shutdown(_signum: int, _frame: Any) -> None:
        if rclpy.ok():
            rclpy.shutdown()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
