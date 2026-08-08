"""Small, bounded summaries for common ROS 2 messages.

The dashboard never forwards an arbitrary full ROS message.  Large arrays are
summarised so a malformed or high-bandwidth topic cannot flood the web API.
"""

from __future__ import annotations

import math
import numbers
from typing import Any, Dict, Iterable, List, Optional, Sequence


# Unitree documents the first twelve LowState motors in FR, FL, RR, RL order,
# with hip, thigh, and calf motors within each leg.  This is also the order
# stored in the official Go2 web-model asset.  Keeping it here makes the ROS
# bridge contract explicit and independent of browser implementation details.
GO2_JOINT_ORDER = (
    "FR_hip_joint",
    "FR_thigh_joint",
    "FR_calf_joint",
    "FL_hip_joint",
    "FL_thigh_joint",
    "FL_calf_joint",
    "RR_hip_joint",
    "RR_thigh_joint",
    "RR_calf_joint",
    "RL_hip_joint",
    "RL_thigh_joint",
    "RL_calf_joint",
)

# Limits come from unitreerobotics/unitree_ros go2_description.  Clamping
# corrupt/out-of-range telemetry to these limits prevents an invalid ROS
# sample from exploding the web model while preserving every physically valid
# Go2 joint position.
GO2_JOINT_LIMITS = {
    "FR_hip_joint": (-1.0472, 1.0472),
    "FR_thigh_joint": (-1.5708, 3.4907),
    "FR_calf_joint": (-2.7227, -0.83776),
    "FL_hip_joint": (-1.0472, 1.0472),
    "FL_thigh_joint": (-1.5708, 3.4907),
    "FL_calf_joint": (-2.7227, -0.83776),
    "RR_hip_joint": (-1.0472, 1.0472),
    "RR_thigh_joint": (-0.5236, 4.5379),
    "RR_calf_joint": (-2.7227, -0.83776),
    "RL_hip_joint": (-1.0472, 1.0472),
    "RL_thigh_joint": (-0.5236, 4.5379),
    "RL_calf_joint": (-2.7227, -0.83776),
}

_GO2_JOINT_BY_CASEFOLD = {name.casefold(): name for name in GO2_JOINT_ORDER}


def _number(value: Any, digits: int = 4) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Real):
        result = float(value)
        if not math.isfinite(result):
            return None
        if isinstance(value, numbers.Integral):
            return int(value)
        return round(result, digits)
    return value


def _vector(value: Iterable[Any], limit: int = 16) -> List[Any]:
    return [_number(item) for item in list(value)[:limit]]


def _xyz(value: Any) -> Dict[str, Any]:
    return {
        "x": _number(getattr(value, "x", 0.0)),
        "y": _number(getattr(value, "y", 0.0)),
        "z": _number(getattr(value, "z", 0.0)),
    }


def _quat(value: Any) -> Dict[str, Any]:
    return {
        "x": _number(getattr(value, "x", 0.0)),
        "y": _number(getattr(value, "y", 0.0)),
        "z": _number(getattr(value, "z", 0.0)),
        "w": _number(getattr(value, "w", 1.0)),
    }


def _bounded_go2_position(value: Any, joint_name: str) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return None
    result = float(value)
    if not math.isfinite(result):
        return None
    lower, upper = GO2_JOINT_LIMITS[joint_name]
    return round(max(lower, min(upper, result)), 6)


def _canonical_go2_joint_name(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    # Accept a namespace prefix (for example ``go2/FR_hip_joint``) while
    # requiring an exact canonical basename so unrelated joints cannot be
    # accidentally assigned to the robot model.
    basename = value.strip().rstrip("/").rsplit("/", 1)[-1]
    return _GO2_JOINT_BY_CASEFOLD.get(basename.casefold())


def extract_go2_joint_positions(message: Any, type_name: str) -> Optional[List[float]]:
    """Extract exactly twelve safe Go2 joint positions in model order.

    ``LowState`` uses Unitree's fixed motor order. ``JointState`` is reordered
    by joint name, so arbitrary message order is safe.  Missing, non-finite, or
    incomplete telemetry rejects the whole sample instead of partially moving
    the browser model.
    """

    if type_name.casefold().endswith("/lowstate"):
        motors = list(getattr(message, "motor_state", []))[: len(GO2_JOINT_ORDER)]
        if len(motors) != len(GO2_JOINT_ORDER):
            return None
        positions = [
            _bounded_go2_position(getattr(motor, "q", None), joint_name)
            for motor, joint_name in zip(motors, GO2_JOINT_ORDER)
        ]
        return None if any(value is None for value in positions) else positions  # type: ignore[return-value]

    if type_name != "sensor_msgs/msg/JointState":
        return None
    names = list(getattr(message, "name", []))
    values = list(getattr(message, "position", []))
    if len(names) != len(values):
        return None
    named_positions: Dict[str, float] = {}
    for raw_name, raw_value in zip(names[:64], values[:64]):
        joint_name = _canonical_go2_joint_name(raw_name)
        if not joint_name or joint_name in named_positions:
            continue
        bounded = _bounded_go2_position(raw_value, joint_name)
        if bounded is None:
            return None
        named_positions[joint_name] = bounded
    if any(name not in named_positions for name in GO2_JOINT_ORDER):
        return None
    return [named_positions[name] for name in GO2_JOINT_ORDER]


def extract_go2_imu_rpy(message: Any, type_name: str) -> Optional[List[float]]:
    """Return the LowState body IMU roll/pitch/yaw in radians when valid."""

    if not type_name.casefold().endswith("/lowstate"):
        return None
    try:
        values = list(getattr(getattr(message, "imu_state", None), "rpy", []))
    except TypeError:
        return None
    if len(values) != 3:
        return None
    result: List[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            return None
        number = float(value)
        if not math.isfinite(number):
            return None
        result.append(round(number, 6))
    return result


def go2_joint_state_payload(
    *,
    topic: str,
    type_name: str,
    positions: Optional[Sequence[float]],
    updated_at: float,
    now: float,
    stale_after_s: float,
    seq: int = 0,
    stamp_ns: int = 0,
    source_order: str = "",
    imu_rpy_rad: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """Build the bounded, freshness-aware ``/api/v1/state`` joint contract."""

    age = max(0.0, now - updated_at) if updated_at > 0.0 else None
    valid = positions is not None and len(positions) == len(GO2_JOINT_ORDER)
    if not topic or not valid or age is None:
        state = "waiting"
    elif age > stale_after_s:
        state = "stale"
    else:
        state = "ok"

    safe_positions: Optional[List[float]] = None
    safe_imu_rpy: Optional[List[float]] = None
    if state == "ok":
        candidate = [
            _bounded_go2_position(value, joint_name)
            for value, joint_name in zip(positions or (), GO2_JOINT_ORDER)
        ]
        if len(candidate) == len(GO2_JOINT_ORDER) and all(value is not None for value in candidate):
            safe_positions = candidate  # type: ignore[assignment]
        else:
            state = "waiting"
        if imu_rpy_rad is not None and len(imu_rpy_rad) == 3:
            candidate_rpy = []
            for value in imu_rpy_rad:
                if isinstance(value, bool) or not isinstance(value, numbers.Real) or not math.isfinite(float(value)):
                    candidate_rpy = []
                    break
                candidate_rpy.append(round(float(value), 6))
            if len(candidate_rpy) == 3:
                safe_imu_rpy = candidate_rpy

    return {
        "state": state,
        "topic": topic,
        "type": type_name,
        "seq": int(seq),
        "age_s": round(age, 3) if age is not None else None,
        "stamp_ns": int(stamp_ns),
        "order": list(GO2_JOINT_ORDER),
        # A stale or incomplete sample must never continue driving the model.
        "position_rad": safe_positions,
        "imu_rpy_rad": safe_imu_rpy if state == "ok" else None,
        "source_order": source_order,
        "limit_policy": "clamped_to_go2_urdf",
    }


def classify_type(type_name: str) -> str:
    exact = {
        "sensor_msgs/msg/Image": "camera",
        "sensor_msgs/msg/CompressedImage": "camera",
        "sensor_msgs/msg/PointCloud2": "pointcloud",
        "sensor_msgs/msg/LaserScan": "lidar",
        "sensor_msgs/msg/Imu": "imu",
        "sensor_msgs/msg/BatteryState": "battery",
        "sensor_msgs/msg/JointState": "joints",
        "sensor_msgs/msg/NavSatFix": "gnss",
        "sensor_msgs/msg/Range": "range",
        "sensor_msgs/msg/Temperature": "environment",
        "sensor_msgs/msg/FluidPressure": "environment",
        "sensor_msgs/msg/MagneticField": "environment",
        "nav_msgs/msg/Odometry": "odometry",
        "nav_msgs/msg/OccupancyGrid": "occupancy_grid",
        "nav_msgs/msg/Path": "path",
    }
    if type_name in exact:
        return exact[type_name]
    lowered = type_name.lower()
    if lowered.endswith("/go2frontvideodata"):
        return "camera"
    if lowered.endswith("/lowstate") or lowered.endswith("/sportmodestate"):
        return "robot_state"
    if lowered.endswith("/lidarstate"):
        return "lidar"
    if "battery" in lowered or "bms" in lowered:
        return "battery"
    if "imu" in lowered:
        return "imu"
    if "camera" in lowered or "video" in lowered:
        return "camera"
    return "other"


def is_observable_type(type_name: str) -> bool:
    return classify_type(type_name) in {
        "imu",
        "battery",
        "joints",
        "gnss",
        "range",
        "environment",
        "odometry",
        "robot_state",
        "lidar",
    }


def summarize_message(message: Any, type_name: str) -> Dict[str, Any]:
    """Return a JSON-safe, compact message summary."""
    if type_name.endswith("/LowState"):
        imu = getattr(message, "imu_state", None)
        bms = getattr(message, "bms_state", None)
        motors = list(getattr(message, "motor_state", []))
        joint_positions = extract_go2_joint_positions(message, type_name)
        return {
            "battery_soc": int(getattr(bms, "soc", 0)) if bms else None,
            "battery_current_ma": int(getattr(bms, "current", 0)) if bms else None,
            "power_v": _number(getattr(message, "power_v", 0.0)),
            "power_a": _number(getattr(message, "power_a", 0.0)),
            "imu_rpy": extract_go2_imu_rpy(message, type_name),
            "gyro": _vector(getattr(imu, "gyroscope", []), 3) if imu else [],
            "accel": _vector(getattr(imu, "accelerometer", []), 3) if imu else [],
            "imu_temperature_c": int(getattr(imu, "temperature", 0)) if imu else None,
            "foot_force": _vector(getattr(message, "foot_force", []), 4),
            "motor_temperature_c": [int(getattr(m, "temperature", 0)) for m in motors[:12]],
            "motor_position_rad": joint_positions,
            "motor_joint_order": list(GO2_JOINT_ORDER),
            "error_code": int(getattr(message, "error_code", 0)),
        }

    if type_name.endswith("/SportModeState"):
        imu = getattr(message, "imu_state", None)
        return {
            "mode": int(getattr(message, "mode", 0)),
            "gait_type": int(getattr(message, "gait_type", 0)),
            "progress": _number(getattr(message, "progress", 0.0)),
            "position": _vector(getattr(message, "position", []), 3),
            "velocity": _vector(getattr(message, "velocity", []), 3),
            "body_height": _number(getattr(message, "body_height", 0.0)),
            "yaw_speed": _number(getattr(message, "yaw_speed", 0.0)),
            "range_obstacle": _vector(getattr(message, "range_obstacle", []), 4),
            "imu_rpy": _vector(getattr(imu, "rpy", []), 3) if imu else [],
        }

    if type_name.endswith("/LidarState"):
        return {
            "firmware": str(getattr(message, "firmware_version", "")),
            "software": str(getattr(message, "software_version", "")),
            "error_state": int(getattr(message, "error_state", 0)),
            "cloud_hz": _number(getattr(message, "cloud_frequency", 0.0)),
            "cloud_loss_pct": _number(getattr(message, "cloud_packet_loss_rate", 0.0)),
            "cloud_size": int(getattr(message, "cloud_size", 0)),
            "imu_hz": _number(getattr(message, "imu_frequency", 0.0)),
            "imu_loss_pct": _number(getattr(message, "imu_packet_loss_rate", 0.0)),
            "imu_rpy": _vector(getattr(message, "imu_rpy", []), 3),
        }

    if type_name == "sensor_msgs/msg/Imu":
        return {
            "orientation": _quat(getattr(message, "orientation", None)),
            "angular_velocity": _xyz(getattr(message, "angular_velocity", None)),
            "linear_acceleration": _xyz(getattr(message, "linear_acceleration", None)),
        }

    if type_name == "sensor_msgs/msg/BatteryState":
        return {
            "percentage": _number(getattr(message, "percentage", 0.0)),
            "voltage": _number(getattr(message, "voltage", 0.0)),
            "current": _number(getattr(message, "current", 0.0)),
            "temperature": _number(getattr(message, "temperature", 0.0)),
            "status": int(getattr(message, "power_supply_status", 0)),
        }

    if type_name == "sensor_msgs/msg/JointState":
        names = list(getattr(message, "name", []))[:24]
        positions = _vector(getattr(message, "position", []), 24)
        velocities = _vector(getattr(message, "velocity", []), 24)
        return {
            "joint_count": len(getattr(message, "name", [])),
            "name": names,
            "position": positions,
            "velocity": velocities,
        }

    if type_name == "sensor_msgs/msg/NavSatFix":
        return {
            "latitude": _number(getattr(message, "latitude", 0.0), 7),
            "longitude": _number(getattr(message, "longitude", 0.0), 7),
            "altitude": _number(getattr(message, "altitude", 0.0)),
            "status": int(getattr(getattr(message, "status", None), "status", 0)),
        }

    if type_name == "nav_msgs/msg/Odometry":
        pose = getattr(getattr(message, "pose", None), "pose", None)
        twist = getattr(getattr(message, "twist", None), "twist", None)
        return {
            "frame_id": str(getattr(getattr(message, "header", None), "frame_id", "")),
            "child_frame_id": str(getattr(message, "child_frame_id", "")),
            "position": _xyz(getattr(pose, "position", None)),
            "orientation": _quat(getattr(pose, "orientation", None)),
            "linear_velocity": _xyz(getattr(twist, "linear", None)),
            "angular_velocity": _xyz(getattr(twist, "angular", None)),
        }

    if type_name == "sensor_msgs/msg/LaserScan":
        ranges = list(getattr(message, "ranges", []))
        finite = [float(v) for v in ranges if isinstance(v, (int, float)) and math.isfinite(v)]
        return {
            "sample_count": len(ranges),
            "min_range": _number(min(finite)) if finite else None,
            "max_range": _number(max(finite)) if finite else None,
            "angle_min": _number(getattr(message, "angle_min", 0.0)),
            "angle_max": _number(getattr(message, "angle_max", 0.0)),
        }

    if type_name == "sensor_msgs/msg/Range":
        return {
            "range": _number(getattr(message, "range", 0.0)),
            "min_range": _number(getattr(message, "min_range", 0.0)),
            "max_range": _number(getattr(message, "max_range", 0.0)),
        }

    return _bounded_generic_summary(message)


def _bounded_generic_summary(message: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    getter = getattr(message, "get_fields_and_field_types", None)
    if not getter:
        return {"value": str(message)[:200]}
    for field in list(getter().keys())[:16]:
        value = getattr(message, field, None)
        if isinstance(value, (str, int, float, bool)):
            result[field] = _number(value)
        elif isinstance(value, (list, tuple)):
            if value and all(isinstance(item, (str, int, float, bool)) for item in value[:12]):
                result[field] = [_number(item) for item in value[:12]]
                if len(value) > 12:
                    result[field + "_count"] = len(value)
        elif value is not None and hasattr(value, "x"):
            result[field] = _xyz(value)
    return result
