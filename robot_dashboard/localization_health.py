"""Bounded, read-only localization health classification.

The classifier consumes only already validated navigation telemetry.  It does
not publish ROS messages, mutate configuration, or participate in motion
gating.  Safety interlocks remain owned by ``NavigationRosGateway``.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping


LOCALIZATION_HEALTH_STATES = frozenset(
    {
        "READY",
        "DEGRADED",
        "STALE",
        "DISCONTINUITY",
        "FRAME_MISMATCH",
        "CALIBRATION_SUSPECTED",
        "UNAVAILABLE",
    }
)


def _bounded_float(
    values: Mapping[str, Any], key: str, default: float, minimum: float, maximum: float
) -> float:
    try:
        value = float(values.get(key, default))
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value):
        return default
    return max(minimum, min(value, maximum))


def _bounded_int(
    values: Mapping[str, Any], key: str, default: int, minimum: int, maximum: int
) -> int:
    value = values.get(key, default)
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


@dataclass(frozen=True)
class LocalizationHealthThresholds:
    cloud_min_hz: float = 4.0
    cloud_max_jitter_s: float = 0.25
    cloud_stale_s: float = 0.75
    runtime_health_stale_s: float = 0.75
    odometry_min_hz: float = 10.0
    odometry_max_jitter_s: float = 0.10
    odometry_stale_s: float = 0.50
    tf_stale_s: float = 0.50
    accepted_points_min: int = 32
    fresh_sequence_min: int = 3
    discontinuity_recent_s: float = 10.0
    goal_progress_min_mps: float = 0.01
    controller_stall_s: float = 3.0

    @classmethod
    def from_profile(cls, profile: Mapping[str, Any] | None) -> "LocalizationHealthThresholds":
        configured = (
            profile.get("navigation_health", {}) if isinstance(profile, Mapping) else {}
        )
        values = configured if isinstance(configured, Mapping) else {}
        defaults = cls()
        return cls(
            cloud_min_hz=_bounded_float(values, "cloud_min_hz", defaults.cloud_min_hz, 0.1, 100.0),
            cloud_max_jitter_s=_bounded_float(values, "cloud_max_jitter_s", defaults.cloud_max_jitter_s, 0.001, 5.0),
            cloud_stale_s=_bounded_float(values, "cloud_stale_s", defaults.cloud_stale_s, 0.1, 10.0),
            runtime_health_stale_s=_bounded_float(values, "runtime_health_stale_s", defaults.runtime_health_stale_s, 0.1, 10.0),
            odometry_min_hz=_bounded_float(values, "odometry_min_hz", defaults.odometry_min_hz, 0.1, 500.0),
            odometry_max_jitter_s=_bounded_float(values, "odometry_max_jitter_s", defaults.odometry_max_jitter_s, 0.001, 5.0),
            odometry_stale_s=_bounded_float(values, "odometry_stale_s", defaults.odometry_stale_s, 0.1, 10.0),
            tf_stale_s=_bounded_float(values, "tf_stale_s", defaults.tf_stale_s, 0.1, 10.0),
            accepted_points_min=_bounded_int(values, "accepted_points_min", defaults.accepted_points_min, 3, 1_000_000),
            fresh_sequence_min=_bounded_int(values, "fresh_sequence_min", defaults.fresh_sequence_min, 1, 100),
            discontinuity_recent_s=_bounded_float(values, "discontinuity_recent_s", defaults.discontinuity_recent_s, 0.1, 120.0),
            goal_progress_min_mps=_bounded_float(values, "goal_progress_min_mps", defaults.goal_progress_min_mps, 0.0, 5.0),
            controller_stall_s=_bounded_float(values, "controller_stall_s", defaults.controller_stall_s, 0.25, 120.0),
        )

    def public(self) -> dict[str, Any]:
        return asdict(self)


def _number(metrics: Mapping[str, Any], key: str) -> float | None:
    value = metrics.get(key)
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0.0 else None


def classify_localization_health(
    metrics: Mapping[str, Any],
    *,
    active: bool,
    localized: bool,
    thresholds: LocalizationHealthThresholds,
) -> dict[str, Any]:
    """Return one explicit state and reason without inventing a confidence score."""

    def result(state: str, reason: str, basis: str) -> dict[str, Any]:
        return {"state": state, "reason_code": reason, "threshold_basis": basis}

    frame_error = str(metrics.get("frame_error") or "").strip()
    if frame_error:
        return result("FRAME_MISMATCH", "FRAME_CONTRACT_MISMATCH", frame_error[:160])
    jump_age = _number(metrics, "last_jump_age_s")
    if jump_age is not None and jump_age <= thresholds.discontinuity_recent_s:
        reason = str(metrics.get("last_jump_reason") or "ODOMETRY_DISCONTINUITY")
        return result(
            "DISCONTINUITY",
            reason.upper().replace(" ", "_")[:64],
            f"last_jump_age_s <= {thresholds.discontinuity_recent_s}",
        )
    if bool(metrics.get("calibration_suspected")):
        return result(
            "CALIBRATION_SUSPECTED",
            str(metrics.get("calibration_reason") or "CALIBRATION_CONTRACT_MISMATCH")[:64],
            "calibration assistant observed a fixed-contract mismatch",
        )
    if not active:
        return result("UNAVAILABLE", "NAVIGATION_INACTIVE", "navigation.active == false")

    cloud_age = _number(metrics, "cloud_age_s")
    runtime_health_age = _number(metrics, "runtime_health_age_s")
    odom_age = _number(metrics, "odometry_age_s")
    odom_tf_age = _number(metrics, "odom_to_base_age_s")
    map_tf_age = _number(metrics, "map_to_odom_age_s")
    if cloud_age is None or runtime_health_age is None or odom_age is None or odom_tf_age is None:
        return result("UNAVAILABLE", "TELEMETRY_MISSING", "required bounded telemetry is absent")
    stale = []
    if cloud_age > thresholds.cloud_stale_s:
        stale.append(f"cloud_age_s>{thresholds.cloud_stale_s}")
    if runtime_health_age > thresholds.runtime_health_stale_s:
        stale.append(f"runtime_health_age_s>{thresholds.runtime_health_stale_s}")
    if odom_age > thresholds.odometry_stale_s:
        stale.append(f"odometry_age_s>{thresholds.odometry_stale_s}")
    if odom_tf_age > thresholds.tf_stale_s:
        stale.append(f"odom_to_base_age_s>{thresholds.tf_stale_s}")
    if localized and (map_tf_age is None or map_tf_age > thresholds.tf_stale_s):
        stale.append(f"map_to_odom_age_s>{thresholds.tf_stale_s}")
    if stale:
        return result("STALE", "FRESHNESS_THRESHOLD_EXCEEDED", ", ".join(stale))

    fresh_sequence = int(_number(metrics, "fresh_sequence_count") or 0)
    if fresh_sequence < thresholds.fresh_sequence_min:
        return result(
            "DEGRADED",
            "FRESH_SEQUENCE_WARMUP",
            f"fresh_sequence_count < {thresholds.fresh_sequence_min}",
        )
    if not localized:
        return result("DEGRADED", "INITIAL_POSE_REQUIRED", "localization.localized == false")

    cloud_hz = _number(metrics, "cloud_frequency_hz")
    odom_hz = _number(metrics, "odometry_frequency_hz")
    cloud_jitter = _number(metrics, "cloud_jitter_s")
    odom_jitter = _number(metrics, "odometry_jitter_s")
    accepted_points = int(_number(metrics, "accepted_points") or 0)
    degraded = []
    if cloud_hz is None or cloud_hz < thresholds.cloud_min_hz:
        degraded.append(f"cloud_frequency_hz<{thresholds.cloud_min_hz}")
    if odom_hz is None or odom_hz < thresholds.odometry_min_hz:
        degraded.append(f"odometry_frequency_hz<{thresholds.odometry_min_hz}")
    if cloud_jitter is None or cloud_jitter > thresholds.cloud_max_jitter_s:
        degraded.append(f"cloud_jitter_s>{thresholds.cloud_max_jitter_s}")
    if odom_jitter is None or odom_jitter > thresholds.odometry_max_jitter_s:
        degraded.append(f"odometry_jitter_s>{thresholds.odometry_max_jitter_s}")
    if accepted_points < thresholds.accepted_points_min:
        degraded.append(f"accepted_points<{thresholds.accepted_points_min}")
    stall = _number(metrics, "controller_stall_duration_s")
    if stall is not None and stall >= thresholds.controller_stall_s:
        degraded.append(f"controller_stall_duration_s>={thresholds.controller_stall_s}")
        progress_rate = _number(metrics, "goal_progress_rate_mps")
        if bool(metrics.get("goal_active")) and (
            progress_rate is None or progress_rate < thresholds.goal_progress_min_mps
        ):
            degraded.append(f"goal_progress_rate_mps<{thresholds.goal_progress_min_mps}")
    if degraded:
        return result("DEGRADED", "PERFORMANCE_THRESHOLD_EXCEEDED", ", ".join(degraded))
    return result("READY", "HEALTHY", "all configured thresholds satisfied")


def build_calibration_assistant(
    runtime_health: Mapping[str, Any],
    *,
    static_tf_publishers: int,
    topic_publishers: Mapping[str, Any],
    metrics: Mapping[str, Any],
    expected_model: Any,
) -> dict[str, Any]:
    """Build a fixed read-only calibration checklist from public telemetry."""

    frames = runtime_health.get("frames")
    frames = frames if isinstance(frames, Mapping) else {}
    extrinsic = runtime_health.get("lidar_extrinsic")
    extrinsic = extrinsic if isinstance(extrinsic, Mapping) else {}
    domains = runtime_health.get("clock_domains")
    domains = domains if isinstance(domains, Mapping) else {}
    if isinstance(expected_model, Mapping):
        try:
            position = [round(float(value), 6) for value in expected_model.get("position", [])]
            rpy = [round(float(value), 6) for value in expected_model.get("rpy", [])]
        except (TypeError, ValueError):
            expected_model = None
        else:
            expected_model = (
                {"position": position, "rpy": rpy}
                if len(position) == 3
                and len(rpy) == 3
                and all(math.isfinite(value) for value in position + rpy)
                else None
            )
    else:
        expected_model = None
    publisher_count = max(0, min(int(static_tf_publishers), 128))

    def item(
        code: str,
        status: str,
        suspected: str,
        observed: Any,
        expected: Any,
        key: str,
        file_name: str,
        verification: str,
    ) -> dict[str, Any]:
        return {
            "code": code,
            "status": status,
            "suspected_cause": suspected,
            "observed": observed,
            "expected": expected,
            "related_config_key": key,
            "related_file": file_name,
            "safe_manual_verification": verification,
        }

    cloud_frame = frames.get("cloud") or "unknown"
    odom_pair = (
        f"{frames.get('odometry_parent', 'unknown')}"
        f"->{frames.get('odometry_child', 'unknown')}"
    )
    items = [
        item(
            "LIDAR_EXTRINSIC",
            "OK"
            if extrinsic.get("parent") == "base_link"
            and extrinsic.get("child") == "hesai_lidar"
            else "UNKNOWN",
            "LiDAR-to-base extrinsic may not match the fixed runtime",
            dict(extrinsic),
            "base_link -> hesai_lidar",
            "navigation runtime --lidar-{x,y,z,yaw}",
            "scripts/run_go2_navigation_humble.sh",
            "With motion disabled, compare cloud forward with the 3D model axes.",
        ),
        item(
            "POINTCLOUD_FRAME",
            "OK" if cloud_frame == "hesai_lidar" else "MISMATCH",
            "PointCloud frame_id does not match the trusted calibration frame",
            cloud_frame,
            "hesai_lidar",
            "navigation runtime --cloud-frame",
            "scripts/run_go2_navigation_humble.sh",
            "Inspect one /velodyne_points header without publishing or changing parameters.",
        ),
        item(
            "ODOMETRY_FRAMES",
            "OK" if odom_pair == "camera_init->body" else "MISMATCH",
            "FAST-LIO parent/child frames are inconsistent",
            odom_pair,
            "camera_init->body",
            "navigation fixed odometry contract",
            "config/fastlio_xt16.yaml",
            "Inspect one /Odometry header and child_frame_id while stationary.",
        ),
        item(
            "STATIC_TF_DUPLICATE",
            "REVIEW" if publisher_count > 1 else "OK" if publisher_count == 1 else "UNKNOWN",
            "Multiple static-TF publishers are a review hint, not duplicate proof",
            {"tf_static_publishers": publisher_count},
            "exactly one base_link -> hesai_lidar transform",
            "static transform ownership",
            "robot_dashboard/navigation_runtime.py",
            "List /tf_static publishers and compare child pairs without stopping them.",
        ),
        item(
            "SENSOR_CLOCK_DOMAIN",
            "OK" if domains.get("pointcloud") == "host_ros_normalized" else "UNKNOWN",
            "Sensor timestamps may be in a device clock domain",
            {"domains": dict(domains), "offsets_s": metrics.get("host_clock_offsets_s")},
            "cloud normalized to host ROS; controller clock checked by progression",
            "timestamp normalization contract",
            "scripts/xt16_fastlio_bridge.py",
            "Compare five increasing stamps with receive time; never stamp with now().",
        ),
        item(
            "CLOUD_MODEL_DIRECTION",
            "REVIEW" if expected_model else "UNKNOWN",
            "Cloud axes may be mirrored or rotated relative to the robot model",
            {"runtime_extrinsic": dict(extrinsic)},
            expected_model or "robot_pose_in_cloud_frames.hesai_lidar",
            "robot_pose_in_cloud_frames.hesai_lidar",
            "config/go2.json",
            "With motion disabled, use XYZ and verify forward/left/up in a static scene.",
        ),
    ]
    publisher_counts = runtime_health.get("publisher_counts")
    publisher_counts = publisher_counts if isinstance(publisher_counts, Mapping) else {}
    return {
        "read_only": True,
        "writes_configuration": False,
        "items": items,
        "source_publishers": {
            "pointcloud": int(publisher_counts.get("/velodyne_points", 0) or 0),
            "fast_lio_odometry": int(topic_publishers.get("/Odometry", 0) or 0),
            "runtime_health": int(
                topic_publishers.get("/robot_scope/nav/runtime_health", 0) or 0
            ),
            "static_tf": publisher_count,
        },
    }


__all__ = [
    "LOCALIZATION_HEALTH_STATES",
    "LocalizationHealthThresholds",
    "build_calibration_assistant",
    "classify_localization_health",
]
