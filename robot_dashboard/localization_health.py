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

COMPETITION_FASTLIO_PROFILE = "go2-xt16-wireless-competition-fastlio"


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


@dataclass(frozen=True)
class OdometryRateReadinessPolicy:
    """Immutable, server-owned policy for the one competition profile."""

    profile: str
    source: str
    enabled: bool
    nominal_hz: float
    ready_enter_hz: float
    ready_exit_hz: float
    ready_enter_dwell_s: float
    ready_exit_dwell_s: float
    max_gap_s: float | None

    @classmethod
    def for_navigation_profile(
        cls,
        navigation_profile: str,
        *,
        legacy_min_hz: float,
    ) -> "OdometryRateReadinessPolicy":
        if navigation_profile == COMPETITION_FASTLIO_PROFILE:
            return cls(
                profile=navigation_profile,
                source="server_fixed_competition_fastlio",
                enabled=True,
                nominal_hz=10.0,
                ready_enter_hz=9.5,
                ready_exit_hz=9.0,
                ready_enter_dwell_s=10.0,
                ready_exit_dwell_s=2.0,
                max_gap_s=0.25,
            )
        minimum = max(0.1, min(float(legacy_min_hz), 500.0))
        return cls(
            profile=navigation_profile or "go2-xt16-wired",
            source="profile.navigation_health.odometry_min_hz",
            enabled=False,
            nominal_hz=minimum,
            ready_enter_hz=minimum,
            ready_exit_hz=minimum,
            ready_enter_dwell_s=0.0,
            ready_exit_dwell_s=0.0,
            max_gap_s=None,
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
    rate_policy: OdometryRateReadinessPolicy | None = None,
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
    source_error = str(metrics.get("source_error") or "").strip()
    if source_error:
        return result(
            "UNAVAILABLE",
            "SOURCE_PUBLISHER_CONFLICT",
            source_error[:160],
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
    odom_hz = (
        _number(metrics, "odometry_frequency_hz_raw")
        if rate_policy is not None and rate_policy.enabled
        else _number(metrics, "odometry_frequency_hz")
    )
    cloud_jitter = _number(metrics, "cloud_jitter_s")
    odom_jitter = _number(metrics, "odometry_jitter_s")
    accepted_points = int(_number(metrics, "accepted_points") or 0)
    if cloud_hz is None or cloud_hz < thresholds.cloud_min_hz:
        return result(
            "DEGRADED",
            "CLOUD_RATE_BELOW_MINIMUM",
            f"cloud_frequency_hz<{thresholds.cloud_min_hz}",
        )
    if rate_policy is not None and rate_policy.enabled:
        max_gap = _number(metrics, "odometry_max_gap_s")
        if max_gap is None:
            return result(
                "DEGRADED",
                "ODOMETRY_RATE_METRICS_MISSING",
                "odometry_max_gap_s is unavailable",
            )
        if rate_policy.max_gap_s is None or max_gap > rate_policy.max_gap_s:
            return result(
                "DEGRADED",
                "ODOMETRY_MAX_GAP_EXCEEDED",
                f"odometry_max_gap_s>{rate_policy.max_gap_s}",
            )
        if odom_hz is None or odom_hz < rate_policy.ready_enter_hz:
            return result(
                "DEGRADED",
                "ODOMETRY_RATE_BELOW_ENTER",
                f"odometry_frequency_hz_raw<{rate_policy.ready_enter_hz}",
            )
    elif odom_hz is None or odom_hz < thresholds.odometry_min_hz:
        return result(
            "DEGRADED",
            "ODOMETRY_RATE_BELOW_MINIMUM",
            f"odometry_frequency_hz<{thresholds.odometry_min_hz}",
        )
    if cloud_jitter is None or cloud_jitter > thresholds.cloud_max_jitter_s:
        return result(
            "DEGRADED",
            "CLOUD_JITTER_EXCEEDED",
            f"cloud_jitter_s>{thresholds.cloud_max_jitter_s}",
        )
    if odom_jitter is None or odom_jitter > thresholds.odometry_max_jitter_s:
        return result(
            "DEGRADED",
            "ODOMETRY_JITTER_EXCEEDED",
            f"odometry_jitter_s>{thresholds.odometry_max_jitter_s}",
        )
    if accepted_points < thresholds.accepted_points_min:
        return result(
            "DEGRADED",
            "ACCEPTED_POINTS_TOO_LOW",
            f"accepted_points<{thresholds.accepted_points_min}",
        )
    stall = _number(metrics, "controller_stall_duration_s")
    if stall is not None and stall >= thresholds.controller_stall_s:
        progress_rate = _number(metrics, "goal_progress_rate_mps")
        if bool(metrics.get("goal_active")) and (
            progress_rate is None or progress_rate < thresholds.goal_progress_min_mps
        ):
            return result(
                "DEGRADED",
                "GOAL_PROGRESS_TOO_LOW",
                f"goal_progress_rate_mps<{thresholds.goal_progress_min_mps}",
            )
        return result(
            "DEGRADED",
            "CONTROLLER_STALL_EXCEEDED",
            f"controller_stall_duration_s>={thresholds.controller_stall_s}",
        )
    return result("READY", "HEALTHY", "all configured thresholds satisfied")


class LocalizationReadinessStabilizer:
    """Session-owned hysteresis over only the competition odometry rate."""

    _RATE_REASON = "ODOMETRY_RATE_BELOW_ENTER"
    _HARD_STATES = frozenset(
        {
            "STALE",
            "DISCONTINUITY",
            "FRAME_MISMATCH",
            "CALIBRATION_SUSPECTED",
            "UNAVAILABLE",
        }
    )

    def __init__(self, policy: OdometryRateReadinessPolicy) -> None:
        self.policy = policy
        self._generation: Any = None
        self._state = "UNAVAILABLE"
        self._enter_since: float | None = None
        self._exit_since: float | None = None
        self._ready_since: float | None = None
        self._transition_count = 0
        self._last_transition_reason = "INITIALIZED"
        self._latest = {
            "state": "UNAVAILABLE",
            "reason_code": "READINESS_NOT_OBSERVED",
            "threshold_basis": "no session-owned health observation",
            "instantaneous_state": "UNAVAILABLE",
            "instantaneous_reason_code": "READINESS_NOT_OBSERVED",
            "stable_ready_duration_s": 0.0,
            "enter_candidate_duration_s": 0.0,
            "exit_candidate_duration_s": 0.0,
            "rate_band": "UNAVAILABLE",
            "transition_count": 0,
            "last_transition_reason": "INITIALIZED",
            "hard_fault": True,
        }

    def reset(self, generation: Any, reason: str) -> None:
        self._generation = generation
        self._state = "UNAVAILABLE"
        self._enter_since = None
        self._exit_since = None
        self._ready_since = None
        self._transition_count = 0
        self._last_transition_reason = str(reason or "RESET")[:64]
        self._latest = {
            **self._latest,
            "state": "UNAVAILABLE",
            "reason_code": "READINESS_RESET",
            "threshold_basis": self._last_transition_reason,
            "instantaneous_state": "UNAVAILABLE",
            "instantaneous_reason_code": "READINESS_RESET",
            "stable_ready_duration_s": 0.0,
            "enter_candidate_duration_s": 0.0,
            "exit_candidate_duration_s": 0.0,
            "rate_band": "UNAVAILABLE",
            "transition_count": 0,
            "last_transition_reason": self._last_transition_reason,
            "hard_fault": True,
        }

    @classmethod
    def is_hard_fault(cls, instantaneous: Mapping[str, Any]) -> bool:
        state = str(instantaneous.get("state") or "UNAVAILABLE")
        reason = str(instantaneous.get("reason_code") or "")
        return state in cls._HARD_STATES or (
            state == "DEGRADED" and reason != cls._RATE_REASON
        )

    def _transition(self, state: str, reason: str) -> None:
        if state != self._state:
            self._transition_count += 1
            self._state = state
        self._last_transition_reason = reason[:64]

    def update(
        self,
        instantaneous: Mapping[str, Any],
        metrics: Mapping[str, Any],
        *,
        now: float,
        generation: Any,
    ) -> dict[str, Any]:
        current = float(now)
        if not math.isfinite(current) or current < 0.0:
            raise ValueError("readiness monotonic time is invalid")
        generation_changed = generation != self._generation
        if generation_changed:
            self.reset(generation, "GENERATION_CHANGED")
        if not self.policy.enabled:
            self._latest = {
                **dict(instantaneous),
                "instantaneous_state": instantaneous.get("state"),
                "instantaneous_reason_code": instantaneous.get("reason_code"),
                "stable_ready_duration_s": 0.0,
                "enter_candidate_duration_s": 0.0,
                "exit_candidate_duration_s": 0.0,
                "rate_band": "LEGACY",
                "transition_count": 0,
                "last_transition_reason": "LEGACY_INSTANTANEOUS",
                "hard_fault": self.is_hard_fault(instantaneous),
            }
            return dict(self._latest)

        if generation_changed:
            self._latest = {
                **self._latest,
                "instantaneous_state": str(instantaneous.get("state"))[:32],
                "instantaneous_reason_code": str(
                    instantaneous.get("reason_code")
                )[:64],
                "rate_band": "HARD_FAULT",
                "last_transition_reason": "GENERATION_CHANGED",
                "hard_fault": True,
            }
            return dict(self._latest)

        raw_rate = _number(metrics, "odometry_frequency_hz_raw")
        hard_fault = self.is_hard_fault(instantaneous)
        if hard_fault:
            self._enter_since = None
            self._exit_since = None
            self._ready_since = None
            self._transition(str(instantaneous.get("state")), str(instantaneous.get("reason_code")))
            rate_band = "HARD_FAULT"
            reason_code = str(instantaneous.get("reason_code"))
            basis = str(instantaneous.get("threshold_basis"))
        elif self._state == "READY":
            assert raw_rate is not None
            if raw_rate < self.policy.ready_exit_hz:
                if self._exit_since is None:
                    self._exit_since = current
                exit_duration = max(0.0, current - self._exit_since)
                if exit_duration >= self.policy.ready_exit_dwell_s:
                    self._enter_since = None
                    self._ready_since = None
                    self._transition("DEGRADED", "READY_EXIT_DWELL_SATISFIED")
                    reason_code = "ODOMETRY_RATE_BELOW_EXIT"
                    basis = f"raw rate below {self.policy.ready_exit_hz} Hz for {self.policy.ready_exit_dwell_s} s"
                else:
                    reason_code = "ODOMETRY_RATE_EXIT_DWELL"
                    basis = f"raw rate below {self.policy.ready_exit_hz} Hz; exit dwell pending"
                rate_band = "EXIT_FAILURE"
            else:
                self._exit_since = None
                reason_code = "HEALTHY_STABLE"
                basis = "competition odometry rate hysteresis satisfied"
                rate_band = (
                    "ENTER"
                    if raw_rate >= self.policy.ready_enter_hz
                    else "HYSTERESIS"
                )
        elif instantaneous.get("state") == "READY" and raw_rate is not None:
            self._exit_since = None
            if self._enter_since is None:
                self._enter_since = current
            enter_duration = max(0.0, current - self._enter_since)
            if enter_duration >= self.policy.ready_enter_dwell_s:
                self._ready_since = self._enter_since
                self._transition("READY", "READY_ENTER_DWELL_SATISFIED")
                reason_code = "HEALTHY_STABLE"
                basis = "competition odometry rate enter dwell satisfied"
            else:
                self._transition("DEGRADED", "READY_ENTER_DWELL_PENDING")
                reason_code = "ODOMETRY_READY_DWELL"
                basis = f"continuous enter dwell < {self.policy.ready_enter_dwell_s} s"
            rate_band = "ENTER"
        else:
            self._enter_since = None
            self._exit_since = None
            self._ready_since = None
            self._transition("DEGRADED", str(instantaneous.get("reason_code")))
            reason_code = str(instantaneous.get("reason_code"))
            basis = str(instantaneous.get("threshold_basis"))
            rate_band = "EXIT_FAILURE"

        self._latest = {
            "state": self._state,
            "reason_code": reason_code[:64],
            "threshold_basis": basis[:160],
            "instantaneous_state": str(instantaneous.get("state"))[:32],
            "instantaneous_reason_code": str(instantaneous.get("reason_code"))[:64],
            "stable_ready_duration_s": round(
                max(0.0, current - self._ready_since)
                if self._ready_since is not None
                else 0.0,
                3,
            ),
            "enter_candidate_duration_s": round(
                max(0.0, current - self._enter_since)
                if self._enter_since is not None and self._state != "READY"
                else 0.0,
                3,
            ),
            "exit_candidate_duration_s": round(
                max(0.0, current - self._exit_since)
                if self._exit_since is not None
                else 0.0,
                3,
            ),
            "rate_band": rate_band,
            "transition_count": self._transition_count,
            "last_transition_reason": self._last_transition_reason,
            "hard_fault": hard_fault,
        }
        return dict(self._latest)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._latest)


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
            "ros2/robot_scope_xt16_bridge/src/xt16_fastlio_bridge.cpp",
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
    "COMPETITION_FASTLIO_PROFILE",
    "LOCALIZATION_HEALTH_STATES",
    "LocalizationHealthThresholds",
    "LocalizationReadinessStabilizer",
    "OdometryRateReadinessPolicy",
    "build_calibration_assistant",
    "classify_localization_health",
]
