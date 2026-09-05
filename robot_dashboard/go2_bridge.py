"""Pure safety core for the standalone Unitree Go2 ROS 2 control bridge."""

from __future__ import annotations

import json
import math
import numbers
import re
import secrets
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path
from typing import Any, Mapping


API_STOP_MOVE = 1003
API_MOVE = 1008
BRIDGE_ROLE_CONTROL = "control"
BRIDGE_ROLE_MOTION_OBSERVER = "motion_observer"
SPORT_REQUEST_EVIDENCE_SCHEMA = "robot-scope.sport-request-evidence.v1"
SPORT_REQUEST_EVIDENCE_MAX_COUNT = 2_147_483_647
SPORT_MODE_STATE_TOPICS = ("/sportmodestate", "/lf/sportmodestate")
SPORT_MODE_STATE_MAX_AGE_MS = 2_147_483_647
SPORT_MODE_STATE_MAX_ERROR_CODE = 4_294_967_295
SPORT_MODE_STATE_MAX_ABS_VELOCITY = 20.0
MOTION_OBSERVATION_SCHEMA = "robot-scope.motion-observation"
MOTION_OBSERVATION_SCHEMA_VERSION = 1
MOTION_OBSERVATION_SOURCE_ID = "unitree_go.sport_mode_state.position"
MOTION_OBSERVATION_COORDINATE_SPACE = "unitree_go.sport_mode_state.local"
MOTION_OBSERVATION_SOURCE_CLOCK = "unitree_go.timespec.unverified"
MOTION_OBSERVATION_CALLBACK_CLOCK = "bridge_process.monotonic"
MOTION_OBSERVATION_MAX_ABS_POSITION_M = 1_000_000.0
MOTION_OBSERVATION_MAX_SAMPLE_JUMP_M = 1.0
MOTION_OBSERVATION_MAX_SOURCE_PROGRESS_LEAD_MS = 250
MOTION_OBSERVATION_MAX_COUNT = 2_147_483_647
MOTION_OBSERVATION_PUBLIC_FIELDS = (
    "schema", "schema_version", "source_id", "producer_generation",
    "release_commit", "source_sequence", "source_stamp_ns",
    "source_clock_domain", "source_age_ms", "sample_progression",
    "callback_receive_age_ms", "last_callback_gap_ms", "max_callback_gap_ms",
    "callback_clock_domain", "receiver_status_age_ms", "receiver_clock_domain",
    "stale_after_ms", "coordinate_space", "frame_id", "origin",
    "position_xyz", "orientation_xyzw", "quality", "invalid_reason",
    "origin_reset_detected", "accepted_sample_count", "duplicate_sample_count",
    "rejected_sample_count",
)
SPORT_MODE_STATE_PUBLIC_FIELDS = (
    "topic", "mode", "gait_type", "velocity", "error_code", "age_ms",
    "stale_after_ms", "fresh",
)
RELEASE_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

# This deliberately excludes Damp, flips, jumps, handstands, dances, direct
# motor control, and deprecated sport APIs.
SAFE_ACTION_API_IDS: dict[str, int] = {
    "balance_stand": 1002,
    "stand_up": 1004,
    "stand_down": 1005,
    "recovery_stand": 1006,
    "sit": 1009,
    "rise_sit": 1010,
    "hello": 1016,
    "stretch": 1017,
    "content": 1020,
    "scrape": 1029,
    "heart": 1036,
    "static_walk": 1061,
    "economic_gait": 1063,
    "free_walk": 2045,
}

SAFE_ACTION_GUARD_S: dict[str, float] = {
    "balance_stand": 3.0,
    "stand_up": 5.0,
    "stand_down": 5.0,
    "recovery_stand": 8.0,
    "sit": 5.0,
    "rise_sit": 5.0,
    "hello": 8.0,
    "stretch": 8.0,
    "content": 8.0,
    "scrape": 8.0,
    "heart": 8.0,
    "static_walk": 3.0,
    "economic_gait": 3.0,
    "free_walk": 3.0,
}


class BridgeCommandError(ValueError):
    """Raised when the dashboard sends an unsafe bridge command."""


BARE_DDS_NODE_NAME = "_CREATED_BY_BARE_DDS_APP_"


def runtime_release_commit(module_file: str | Path = __file__) -> str | None:
    """Return the immutable release directory SHA, never an environment hint."""

    release_name = Path(module_file).resolve().parents[1].name
    return release_name if RELEASE_COMMIT_RE.fullmatch(release_name) else None


def classify_sport_request_publishers(
    endpoints: Any,
    *,
    own_node_name: str,
    own_node_namespace: str,
) -> dict[str, int]:
    """Classify Unitree request writers without treating robot DDS as ROS nodes.

    Go2 firmware exposes several request-capable CycloneDDS endpoints without
    ROS node metadata.  They all appear as ``_CREATED_BY_BARE_DDS_APP_`` in a
    ROS graph, so the total publisher count cannot establish exclusive bridge
    ownership.  Named publishers remain attributable and therefore fail the
    control gate unless the endpoint belongs to this bridge instance.

    An endpoint with incomplete metadata is deliberately classified as a
    foreign named publisher rather than trusted as Unitree firmware.
    """

    own = 0
    foreign_named = 0
    bare_unitree = 0
    total = 0
    for endpoint in endpoints:
        total += 1
        node_name = getattr(endpoint, "node_name", None)
        node_namespace = getattr(endpoint, "node_namespace", None)
        if node_name == own_node_name and node_namespace == own_node_namespace:
            own += 1
        elif (
            node_name == BARE_DDS_NODE_NAME
            and node_namespace == BARE_DDS_NODE_NAME
        ):
            bare_unitree += 1
        else:
            foreign_named += 1
    return {
        "sport_publishers": total,
        "own_sport_publishers": own,
        "foreign_named_sport_publishers": foreign_named,
        "bare_unitree_sport_publishers": bare_unitree,
    }


@dataclass(frozen=True)
class SportRequest:
    api_id: int
    parameter: str = ""
    reason: str = ""


class SportModeStateObservation:
    """Bounded, read-only observation of one configured Unitree state topic."""

    def __init__(self, *, topic: str, stale_after_s: float) -> None:
        if topic not in SPORT_MODE_STATE_TOPICS:
            raise ValueError("SportModeState topic is not allowlisted")
        timeout = float(stale_after_s)
        if not math.isfinite(timeout) or not 0.20 <= timeout <= 1.0:
            raise ValueError("SportModeState freshness limit is invalid")
        self.topic = topic
        self.stale_after_ms = round(timeout * 1_000)
        self._received_at: float | None = None
        self._values: dict[str, Any] = {}
        self._motion_received_at: float | None = None
        self._motion_last_callback_gap_ms: int | None = None
        self._motion_max_callback_gap_ms: int | None = None
        self._motion_position: tuple[float, float, float] | None = None
        self._motion_source_stamp_ns: int | None = None
        self._motion_source_sequence = 0
        self._motion_accepted_count = 0
        self._motion_duplicate_count = 0
        self._motion_rejected_count = 0
        self._motion_invalid_reason = ""
        self._motion_reset_detected = False

    @staticmethod
    def _unsigned(value: Any, *, label: str, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"SportModeState {label} is invalid")
        if not 0 <= value <= maximum:
            raise ValueError(f"SportModeState {label} is invalid")
        return value

    @staticmethod
    def _velocity(value: Any) -> list[float]:
        try:
            items = list(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("SportModeState velocity is invalid") from exc
        if len(items) != 3:
            raise ValueError("SportModeState velocity is invalid")
        velocity: list[float] = []
        for item in items:
            if isinstance(item, bool) or not isinstance(item, numbers.Real):
                raise ValueError("SportModeState velocity is invalid")
            number = float(item)
            if (
                not math.isfinite(number)
                or abs(number) > SPORT_MODE_STATE_MAX_ABS_VELOCITY
            ):
                raise ValueError("SportModeState velocity is invalid")
            velocity.append(round(number, 6))
        return velocity

    @staticmethod
    def _fixed_vector(
        value: Any, *, label: str, maximum_abs: float
    ) -> tuple[float, float, float]:
        """Accept ROS fixed arrays without accepting arbitrary iterables."""

        if isinstance(value, (str, bytes, bytearray, memoryview)):
            raise ValueError(f"SportModeState {label} is invalid")
        try:
            length = len(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"SportModeState {label} is invalid") from exc
        if length != 3:
            raise ValueError(f"SportModeState {label} is invalid")
        values: list[float] = []
        for index in range(3):
            try:
                item = value[index]
            except (TypeError, ValueError, IndexError, KeyError, OverflowError) as exc:
                raise ValueError(f"SportModeState {label} is invalid") from exc
            if isinstance(item, bool) or not isinstance(item, numbers.Real):
                raise ValueError(f"SportModeState {label} is invalid")
            number = float(item)
            if not math.isfinite(number) or abs(number) > maximum_abs:
                raise ValueError(f"SportModeState {label} is invalid")
            values.append(number)
        return values[0], values[1], values[2]

    @staticmethod
    def _source_stamp_ns(message: Any) -> int:
        stamp = getattr(message, "stamp", None)
        seconds = getattr(stamp, "sec", None)
        nanoseconds = getattr(stamp, "nanosec", None)
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, numbers.Integral)
            or isinstance(nanoseconds, bool)
            or not isinstance(nanoseconds, numbers.Integral)
        ):
            raise ValueError("SportModeState source stamp is invalid")
        seconds = int(seconds)
        nanoseconds = int(nanoseconds)
        if seconds < 0 or not 0 <= nanoseconds < 1_000_000_000:
            raise ValueError("SportModeState source stamp is invalid")
        result = seconds * 1_000_000_000 + nanoseconds
        if result <= 0 or result > 0x7FFF_FFFF_FFFF_FFFF:
            raise ValueError("SportModeState source stamp is invalid")
        return result

    def _reject_motion(self, reason: str, *, reset: bool = False) -> None:
        self._motion_rejected_count = min(
            MOTION_OBSERVATION_MAX_COUNT,
            self._motion_rejected_count + 1,
        )
        # A malformed, duplicate or regressed source sample invalidates this
        # process generation. It is never silently adopted as a new origin.
        self._motion_invalid_reason = str(reason)[:80]
        self._motion_reset_detected = self._motion_reset_detected or reset

    def _observe_motion(self, message: Any, *, now: float) -> None:
        if self._motion_invalid_reason:
            self._reject_motion(self._motion_invalid_reason)
            return
        try:
            position = self._fixed_vector(
                getattr(message, "position", None),
                label="position",
                maximum_abs=MOTION_OBSERVATION_MAX_ABS_POSITION_M,
            )
            source_stamp_ns = self._source_stamp_ns(message)
            previous_stamp = self._motion_source_stamp_ns
            previous_position = self._motion_position
            if previous_stamp is not None and source_stamp_ns == previous_stamp:
                self._motion_duplicate_count = min(
                    MOTION_OBSERVATION_MAX_COUNT,
                    self._motion_duplicate_count + 1,
                )
                # A duplicate callback is not new evidence. Do not advance the
                # sequence or refresh callback age; persistent duplicates
                # therefore become STALE rather than appearing fresh.
                return
            if previous_stamp is not None and source_stamp_ns < previous_stamp:
                self._reject_motion("source_stamp_regressed", reset=True)
                return
            if previous_stamp is not None and self._motion_received_at is not None:
                callback_delta_ns = max(
                    0,
                    round((now - self._motion_received_at) * 1_000_000_000),
                )
                source_delta_ns = source_stamp_ns - previous_stamp
                if source_delta_ns > callback_delta_ns + (
                    MOTION_OBSERVATION_MAX_SOURCE_PROGRESS_LEAD_MS * 1_000_000
                ):
                    self._reject_motion("source_stamp_future_progress", reset=True)
                    return
            if previous_position is not None:
                jump = math.sqrt(
                    sum(
                        (value - previous) ** 2
                        for value, previous in zip(position, previous_position)
                    )
                )
                if jump > MOTION_OBSERVATION_MAX_SAMPLE_JUMP_M:
                    self._reject_motion("position_jump", reset=True)
                    return
        except ValueError as exc:
            self._reject_motion(str(exc))
            return
        if self._motion_received_at is not None:
            callback_gap_ms = max(0, math.ceil((now - self._motion_received_at) * 1_000))
            if callback_gap_ms > self.stale_after_ms:
                self._reject_motion("evidence_gap", reset=True)
                return
            self._motion_last_callback_gap_ms = callback_gap_ms
            self._motion_max_callback_gap_ms = max(
                callback_gap_ms,
                self._motion_max_callback_gap_ms or 0,
            )
        self._motion_source_sequence = min(
            MOTION_OBSERVATION_MAX_COUNT,
            self._motion_source_sequence + 1,
        )
        self._motion_accepted_count = min(
            MOTION_OBSERVATION_MAX_COUNT,
            self._motion_accepted_count + 1,
        )
        self._motion_position = position
        self._motion_source_stamp_ns = source_stamp_ns
        self._motion_received_at = now

    def observe(self, message: Any, *, now: float) -> None:
        observed_at = float(now)
        if not math.isfinite(observed_at) or observed_at < 0.0:
            raise ValueError("SportModeState observation time is invalid")
        values = {
            "mode": self._unsigned(
                getattr(message, "mode", None),
                label="mode",
                maximum=255,
            ),
            "gait_type": self._unsigned(
                getattr(message, "gait_type", None),
                label="gait type",
                maximum=255,
            ),
            "velocity": self._velocity(getattr(message, "velocity", None)),
            # Unitree publishes this raw field, but its values are not interpreted
            # here because no authoritative error-code mapping is available.
            "error_code": self._unsigned(
                getattr(message, "error_code", None),
                label="error code",
                maximum=SPORT_MODE_STATE_MAX_ERROR_CODE,
            ),
        }
        self._values = values
        self._received_at = observed_at
        self._observe_motion(message, now=observed_at)

    def snapshot(self, *, now: float) -> dict[str, Any]:
        observed_at = float(now)
        if not math.isfinite(observed_at):
            raise ValueError("SportModeState snapshot time is invalid")
        age_s = (
            None
            if self._received_at is None
            else max(0.0, observed_at - self._received_at)
        )
        age_ms = (
            None
            if age_s is None
            else min(
                SPORT_MODE_STATE_MAX_AGE_MS,
                max(0, math.ceil(age_s * 1_000)),
            )
        )
        fresh = age_ms is not None and age_ms <= self.stale_after_ms
        visible = self._values if fresh else {}
        return {
            "topic": self.topic,
            "mode": visible.get("mode"),
            "gait_type": visible.get("gait_type"),
            "velocity": visible.get("velocity"),
            "error_code": visible.get("error_code"),
            "age_ms": age_ms,
            "stale_after_ms": self.stale_after_ms,
            "fresh": fresh,
        }

    def motion_snapshot(
        self,
        *,
        now: float,
        producer_generation: str,
        release_commit: str | None,
    ) -> dict[str, Any]:
        """Return C4C-only relative-position evidence; never general odometry."""

        observed_at = float(now)
        if not math.isfinite(observed_at):
            raise ValueError("MotionObservation snapshot time is invalid")
        age_ms = (
            None
            if self._motion_received_at is None
            else min(
                SPORT_MODE_STATE_MAX_AGE_MS,
                max(0, math.ceil((observed_at - self._motion_received_at) * 1_000)),
            )
        )
        if self._motion_invalid_reason:
            quality = "INVALID"
            reason = self._motion_invalid_reason
        elif self._motion_position is None:
            quality = "WAITING"
            reason = "sample_unavailable"
        elif age_ms is None or age_ms > self.stale_after_ms:
            quality = "STALE"
            reason = "callback_receive_stale"
        else:
            quality = "READY"
            reason = ""
        return {
            "schema": MOTION_OBSERVATION_SCHEMA,
            "schema_version": MOTION_OBSERVATION_SCHEMA_VERSION,
            "source_id": MOTION_OBSERVATION_SOURCE_ID,
            "producer_generation": producer_generation,
            "release_commit": release_commit,
            "source_sequence": self._motion_source_sequence,
            "source_stamp_ns": self._motion_source_stamp_ns,
            "source_clock_domain": MOTION_OBSERVATION_SOURCE_CLOCK,
            "source_age_ms": None,
            "sample_progression": "source_stamp_strict_increase",
            "callback_receive_age_ms": age_ms,
            "last_callback_gap_ms": self._motion_last_callback_gap_ms,
            "max_callback_gap_ms": self._motion_max_callback_gap_ms,
            "callback_clock_domain": MOTION_OBSERVATION_CALLBACK_CLOCK,
            "stale_after_ms": self.stale_after_ms,
            "coordinate_space": MOTION_OBSERVATION_COORDINATE_SPACE,
            "frame_id": None,
            "origin": "vendor_local_origin_unverified",
            "position_xyz": (
                None
                if self._motion_position is None
                else [round(value, 6) for value in self._motion_position]
            ),
            "orientation_xyzw": None,
            "quality": quality,
            "invalid_reason": reason,
            "origin_reset_detected": self._motion_reset_detected,
            "accepted_sample_count": self._motion_accepted_count,
            "duplicate_sample_count": self._motion_duplicate_count,
            "rejected_sample_count": self._motion_rejected_count,
        }


class SportRequestEvidence:
    """Bounded process-lifetime evidence for successfully published requests.

    The bridge node calls :meth:`record` only after its existing publisher
    returns successfully.  This class owns no ROS entity, transport, control
    source or timer and cannot influence request selection.
    """

    def __init__(self) -> None:
        self._published_count = 0
        self._stop_count = 0
        self._move_count = 0
        self._zero_move_count = 0
        self._nonzero_move_count = 0
        self._malformed_move_count = 0
        self._action_count = 0
        self._other_count = 0
        self._last_api_id: int | None = None
        self._last_publish: float | None = None
        self._max_abs_velocity = [0.0, 0.0, 0.0]
        self._motion_run_id = 0
        self._motion_run_active = False
        self._motion_run_nonzero_move_count = 0
        self._motion_run_max_abs_velocity = [0.0, 0.0, 0.0]

    @staticmethod
    def _increment(value: int) -> int:
        return min(SPORT_REQUEST_EVIDENCE_MAX_COUNT, value + 1)

    @staticmethod
    def _move_axes(parameter: str) -> tuple[float, float, float] | None:
        try:
            payload = json.loads(parameter)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(payload, Mapping) or set(payload) != {"x", "y", "z"}:
            return None
        values = payload.get("x"), payload.get("y"), payload.get("z")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in values
        ):
            return None
        return float(values[0]), float(values[1]), float(values[2])

    def record(self, request: SportRequest, *, now: float) -> None:
        """Record one already-published request without changing bridge state."""

        self._published_count = self._increment(self._published_count)
        self._last_api_id = int(request.api_id)
        self._last_publish = float(now)
        if request.api_id == API_STOP_MOVE:
            self._stop_count = self._increment(self._stop_count)
            self._motion_run_active = False
            return
        if request.api_id == API_MOVE:
            self._move_count = self._increment(self._move_count)
            axes = self._move_axes(request.parameter)
            if axes is None:
                self._malformed_move_count = self._increment(
                    self._malformed_move_count
                )
                return
            limits = (
                Go2BridgeCore.HARD_MAX_LINEAR_X,
                Go2BridgeCore.HARD_MAX_LINEAR_Y,
                Go2BridgeCore.HARD_MAX_ANGULAR_Z,
            )
            if any(abs(value) > limit for value, limit in zip(axes, limits)):
                self._malformed_move_count = self._increment(
                    self._malformed_move_count
                )
                return
            if any(value != 0.0 for value in axes):
                self._nonzero_move_count = self._increment(
                    self._nonzero_move_count
                )
                if not self._motion_run_active:
                    self._motion_run_id = self._increment(self._motion_run_id)
                    self._motion_run_nonzero_move_count = 0
                    self._motion_run_max_abs_velocity = [0.0, 0.0, 0.0]
                    self._motion_run_active = True
                self._motion_run_nonzero_move_count = self._increment(
                    self._motion_run_nonzero_move_count
                )
            else:
                self._zero_move_count = self._increment(self._zero_move_count)
            for index, value in enumerate(axes):
                self._max_abs_velocity[index] = max(
                    self._max_abs_velocity[index], abs(value)
                )
                if self._motion_run_active:
                    self._motion_run_max_abs_velocity[index] = max(
                        self._motion_run_max_abs_velocity[index], abs(value)
                    )
            return
        if request.api_id in SAFE_ACTION_API_IDS.values():
            self._action_count = self._increment(self._action_count)
            self._motion_run_active = False
            return
        self._motion_run_active = False
        self._other_count = self._increment(self._other_count)

    def snapshot(self, *, now: float) -> dict[str, Any]:
        age_ms = (
            None
            if self._last_publish is None
            else min(
                SPORT_REQUEST_EVIDENCE_MAX_COUNT,
                max(0, round((float(now) - self._last_publish) * 1_000)),
            )
        )
        return {
            "schema": SPORT_REQUEST_EVIDENCE_SCHEMA,
            "scope": "bridge_process",
            "published_count": self._published_count,
            "stop_count": self._stop_count,
            "move_count": self._move_count,
            "zero_move_count": self._zero_move_count,
            "nonzero_move_count": self._nonzero_move_count,
            "malformed_move_count": self._malformed_move_count,
            "action_count": self._action_count,
            "other_count": self._other_count,
            "last_api_id": self._last_api_id,
            "last_publish_age_ms": age_ms,
            "max_abs_linear_x": self._max_abs_velocity[0],
            "max_abs_linear_y": self._max_abs_velocity[1],
            "max_abs_angular_z": self._max_abs_velocity[2],
            "motion_run_id": self._motion_run_id,
            "motion_run_active": self._motion_run_active,
            "motion_run_nonzero_move_count": self._motion_run_nonzero_move_count,
            "motion_run_max_abs_linear_x": self._motion_run_max_abs_velocity[0],
            "motion_run_max_abs_linear_y": self._motion_run_max_abs_velocity[1],
            "motion_run_max_abs_angular_z": self._motion_run_max_abs_velocity[2],
        }


class Go2BridgeCore:
    """Last-line motion watchdog, independent from the web process."""

    HARD_MAX_LINEAR_X = 0.30
    HARD_MAX_LINEAR_Y = 0.20
    HARD_MAX_ANGULAR_Z = 0.50
    HARD_MAX_COMMAND_TIMEOUT_S = 0.20

    def __init__(
        self,
        *,
        max_linear_x: float = HARD_MAX_LINEAR_X,
        max_linear_y: float = HARD_MAX_LINEAR_Y,
        max_angular_z: float = HARD_MAX_ANGULAR_Z,
        command_timeout_s: float = HARD_MAX_COMMAND_TIMEOUT_S,
        telemetry_timeout_s: float = 0.50,
        source_timeout_s: float = 2.0,
        expected_bare_sport_publishers: int = 0,
    ) -> None:
        self.max_linear_x = self._bounded_limit(
            max_linear_x, self.HARD_MAX_LINEAR_X
        )
        self.max_linear_y = self._bounded_limit(
            max_linear_y, self.HARD_MAX_LINEAR_Y
        )
        self.max_angular_z = self._bounded_limit(
            max_angular_z, self.HARD_MAX_ANGULAR_Z
        )
        # The ROS timer runs every 50 ms.  A 200 ms age limit therefore gives
        # a nominal StopMove dispatch no later than the following timer cycle
        # (<= 250 ms under a normally scheduled executor).
        self.command_timeout_s = max(
            0.10,
            min(float(command_timeout_s), self.HARD_MAX_COMMAND_TIMEOUT_S),
        )
        self.telemetry_timeout_s = max(
            0.20, min(float(telemetry_timeout_s), 1.0)
        )
        self.source_timeout_s = max(0.5, min(float(source_timeout_s), 5.0))
        if (
            isinstance(expected_bare_sport_publishers, bool)
            or not isinstance(expected_bare_sport_publishers, int)
            or not 0 <= expected_bare_sport_publishers <= 64
        ):
            raise ValueError(
                "expected_bare_sport_publishers must be an integer from 0 to 64"
            )
        self.expected_bare_sport_publishers = expected_bare_sport_publishers
        # A new, unpredictable epoch is created for every bridge process.  A
        # signed command from an earlier process can therefore never be
        # replayed into this instance, even if its timestamp is still fresh.
        self._bridge_epoch = secrets.token_urlsafe(32)

        self._source_id = ""
        self._last_seq_by_source: dict[str, int] = {}
        self._last_received = 0.0
        self._last_command_ack: dict[str, Any] | None = None
        self._last_drive = 0.0
        self._target = (0.0, 0.0, 0.0)
        self._deadman = False
        self._moving = False
        self._pending_stop = True
        self._pending_action: tuple[str, float] | None = None
        self._action_guard_until = 0.0
        self._action_hold_until = 0.0
        self._action_hold_name = ""
        self._last_stop = 0.0
        self._last_error = ""
        self._last_request: SportRequest | None = None

    @property
    def bridge_epoch(self) -> str:
        return self._bridge_epoch

    @staticmethod
    def _bounded_limit(value: float, ceiling: float) -> float:
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ValueError("control limit must be a positive finite number")
        return min(number, ceiling)

    def _graph_ready(
        self,
        *,
        lowstate_publishers: Any,
        sport_subscribers: Any,
        sport_publishers: Any,
        own_sport_publishers: Any,
        foreign_named_sport_publishers: Any,
        bare_unitree_sport_publishers: Any,
    ) -> bool:
        counts = (
            lowstate_publishers,
            sport_subscribers,
            sport_publishers,
            own_sport_publishers,
            foreign_named_sport_publishers,
            bare_unitree_sport_publishers,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            return False
        return (
            lowstate_publishers == 1
            and sport_subscribers == 1
            and own_sport_publishers == 1
            and foreign_named_sport_publishers == 0
            and bare_unitree_sport_publishers
            == self.expected_bare_sport_publishers
            and sport_publishers
            == own_sport_publishers
            + foreign_named_sport_publishers
            + bare_unitree_sport_publishers
        )

    @staticmethod
    def _source(payload: Mapping[str, Any]) -> str:
        value = payload.get("source_id")
        if not isinstance(value, str) or not 8 <= len(value) <= 128:
            raise BridgeCommandError("source_id is invalid")
        return value

    @staticmethod
    def _sequence(payload: Mapping[str, Any]) -> int:
        value = payload.get("seq")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BridgeCommandError("command sequence is invalid")
        return value

    @staticmethod
    def _finite(value: Any, label: str) -> float:
        if isinstance(value, bool):
            raise BridgeCommandError(f"{label} must be numeric")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise BridgeCommandError(f"{label} must be numeric") from exc
        if not math.isfinite(number):
            raise BridgeCommandError(f"{label} must be finite")
        return number

    def _accept_source(self, source_id: str, seq: int, now: float, kind: str) -> None:
        previous_seq = self._last_seq_by_source.get(source_id, -1)
        if seq <= previous_seq:
            raise BridgeCommandError("replayed or out-of-order command")
        if (
            kind != "stop"
            and self._source_id
            and source_id != self._source_id
            and now - self._last_received <= self.source_timeout_s
        ):
            raise BridgeCommandError("another dashboard source owns the bridge")
        self._last_seq_by_source[source_id] = seq
        if len(self._last_seq_by_source) > 16:
            oldest = next(iter(self._last_seq_by_source))
            if oldest != source_id:
                self._last_seq_by_source.pop(oldest, None)
        self._source_id = source_id
        self._last_received = now

    def _record_command_ack(
        self,
        *,
        source_id: str,
        sequence: int,
        kind: str,
        now: float,
    ) -> None:
        """Remember only a fully accepted signed command for status ACK."""

        self._last_command_ack = {
            "source_id": source_id,
            "seq": sequence,
            "type": kind,
            "accepted_at": float(now),
        }

    def accept(
        self,
        payload: Mapping[str, Any],
        *,
        now: float,
        transport_age_s: float = 0.0,
    ) -> None:
        kind = payload.get("type")
        if kind not in {"drive", "stop", "action"}:
            raise BridgeCommandError("unknown bridge command")
        bridge_epoch = payload.get("bridge_epoch")
        if not isinstance(bridge_epoch, str) or not compare_digest(
            bridge_epoch.encode("utf-8"),
            self._bridge_epoch.encode("ascii"),
        ):
            raise BridgeCommandError("bridge epoch does not match")
        source_id = self._source(payload)
        seq = self._sequence(payload)
        transport_age = self._finite(transport_age_s, "transport_age_s")
        if transport_age < 0.0:
            raise BridgeCommandError("transport_age_s must not be negative")
        if kind != "stop" and transport_age > self.command_timeout_s:
            raise BridgeCommandError("bridge command exceeded its transport deadline")
        self._accept_source(source_id, seq, float(now), str(kind))
        self._last_error = ""

        if kind == "stop":
            self.force_stop(str(payload.get("reason", "dashboard stop")))
            self._record_command_ack(
                source_id=source_id,
                sequence=seq,
                kind=str(kind),
                now=now,
            )
            return

        if kind == "action":
            if float(now) < self._action_hold_until:
                raise BridgeCommandError("action safety window is still active")
            action_id = payload.get("action_id")
            if not isinstance(action_id, str) or action_id not in SAFE_ACTION_API_IDS:
                raise BridgeCommandError("action is not allowlisted")
            self._target = (0.0, 0.0, 0.0)
            self._deadman = False
            self._pending_stop = True
            self._pending_action = (action_id, float(now) + 0.10)
            self._action_hold_until = float(now) + SAFE_ACTION_GUARD_S[action_id]
            self._action_hold_name = action_id
            # A browser's 20 Hz teleop loop may already have one frame in
            # flight.  Consume its sequence but do not let it cancel the
            # one-shot action before the ROS request has been published.
            self._action_guard_until = float(now) + 0.25
            self._record_command_ack(
                source_id=source_id,
                sequence=seq,
                kind=str(kind),
                now=now,
            )
            return

        if float(now) < max(self._action_guard_until, self._action_hold_until):
            return
        deadman = payload.get("deadman")
        if not isinstance(deadman, bool):
            raise BridgeCommandError("deadman must be boolean")
        if not deadman:
            self.force_stop("deadman released")
            self._record_command_ack(
                source_id=source_id,
                sequence=seq,
                kind=str(kind),
                now=now,
            )
            return
        x = self._finite(payload.get("linear_x"), "linear_x")
        y = self._finite(payload.get("linear_y"), "linear_y")
        z = self._finite(payload.get("angular_z"), "angular_z")
        self._target = (
            max(-self.max_linear_x, min(self.max_linear_x, x)),
            max(-self.max_linear_y, min(self.max_linear_y, y)),
            max(-self.max_angular_z, min(self.max_angular_z, z)),
        )
        self._deadman = True
        self._last_drive = float(now) - transport_age
        self._pending_action = None
        self._action_guard_until = 0.0
        self._record_command_ack(
            source_id=source_id,
            sequence=seq,
            kind=str(kind),
            now=now,
        )

    def force_stop(self, reason: str = "stop") -> None:
        self._target = (0.0, 0.0, 0.0)
        self._deadman = False
        self._moving = False
        self._pending_action = None
        self._pending_stop = True
        self._action_guard_until = 0.0
        self._action_hold_until = 0.0
        self._action_hold_name = ""
        self._last_error = str(reason)[:160]

    @staticmethod
    def _move_request(target: tuple[float, float, float]) -> SportRequest:
        parameter = json.dumps(
            {"x": target[0], "y": target[1], "z": target[2]},
            separators=(",", ":"),
            allow_nan=False,
        )
        return SportRequest(API_MOVE, parameter, "fresh deadman command")

    def tick(
        self,
        *,
        now: float,
        lowstate_age_s: float | None,
        sport_subscribers: int,
        sport_publishers: int,
        lowstate_publishers: int = 1,
        own_sport_publishers: int = 1,
        foreign_named_sport_publishers: int = 0,
        bare_unitree_sport_publishers: int = 0,
    ) -> list[SportRequest]:
        now = float(now)
        telemetry_fresh = (
            lowstate_age_s is not None
            and math.isfinite(float(lowstate_age_s))
            and 0.0 <= float(lowstate_age_s) <= self.telemetry_timeout_s
        )
        ready = (
            telemetry_fresh
            and self._graph_ready(
                lowstate_publishers=lowstate_publishers,
                sport_subscribers=sport_subscribers,
                sport_publishers=sport_publishers,
                own_sport_publishers=own_sport_publishers,
                foreign_named_sport_publishers=foreign_named_sport_publishers,
                bare_unitree_sport_publishers=bare_unitree_sport_publishers,
            )
        )
        requests: list[SportRequest] = []

        if not ready and (
            self._deadman or any(value != 0.0 for value in self._target)
        ):
            # An accepted drive must never survive a transient readiness loss,
            # even when no non-zero Move has yet made ``_moving`` true and the
            # ordinary idle Stop heartbeat is still inside its 500 ms throttle.
            self.force_stop("telemetry unavailable")

        if now < self._action_hold_until and not ready:
            self.force_stop("telemetry unavailable during action")

        if self._pending_stop:
            requests.append(SportRequest(API_STOP_MOVE, "", self._last_error or "stop"))
            self._pending_stop = False
            self._last_stop = now

        if self._pending_action is not None:
            action_id, due_at = self._pending_action
            if not ready:
                self._pending_action = None
                self.force_stop("bridge unavailable before action")
            elif now >= due_at:
                requests.append(
                    SportRequest(
                        SAFE_ACTION_API_IDS[action_id],
                        "",
                        f"allowlisted action: {action_id}",
                    )
                )
                self._pending_action = None
                self._last_request = requests[-1]
                return requests

        # Unitree actions are asynchronous.  Do not let the normal idle
        # StopMove heartbeat truncate the accepted action; explicit software
        # stop, telemetry loss, and bridge shutdown still stop immediately.
        if now < self._action_hold_until:
            return requests

        command_fresh = (
            self._deadman
            and now - self._last_drive <= self.command_timeout_s
            and now - self._last_received <= self.source_timeout_s
        )
        if ready and command_fresh:
            request = self._move_request(self._target)
            requests.append(request)
            self._moving = any(abs(value) > 1e-6 for value in self._target)
            self._last_request = request
            return requests

        if self._moving or now - self._last_stop >= 0.50:
            reason = "telemetry unavailable" if not ready else "command watchdog"
            request = SportRequest(API_STOP_MOVE, "", reason)
            requests.append(request)
            self._moving = False
            self._deadman = False
            self._target = (0.0, 0.0, 0.0)
            self._last_stop = now
            self._last_request = request
        return requests

    def snapshot(
        self,
        *,
        now: float,
        lowstate_age_s: float | None,
        sport_subscribers: int,
        sport_publishers: int,
        lowstate_publishers: int = 1,
        own_sport_publishers: int = 1,
        foreign_named_sport_publishers: int = 0,
        bare_unitree_sport_publishers: int = 0,
    ) -> dict[str, Any]:
        telemetry_fresh = (
            lowstate_age_s is not None
            and math.isfinite(float(lowstate_age_s))
            and 0.0 <= float(lowstate_age_s) <= self.telemetry_timeout_s
        )
        ready = (
            telemetry_fresh
            and self._graph_ready(
                lowstate_publishers=lowstate_publishers,
                sport_subscribers=sport_subscribers,
                sport_publishers=sport_publishers,
                own_sport_publishers=own_sport_publishers,
                foreign_named_sport_publishers=foreign_named_sport_publishers,
                bare_unitree_sport_publishers=bare_unitree_sport_publishers,
            )
        )
        command_age = None if not self._last_drive else max(0.0, now - self._last_drive)
        command_ack = self._last_command_ack
        projected_command_ack = (
            None
            if command_ack is None
            else {
                "source_id": command_ack["source_id"],
                "seq": command_ack["seq"],
                "type": command_ack["type"],
                "age_ms": min(
                    2_147_483_647,
                    max(
                        0,
                        round((now - float(command_ack["accepted_at"])) * 1_000),
                    ),
                ),
            }
        )
        action_remaining = max(0.0, self._action_hold_until - now)
        control_ready = ready and action_remaining <= 0.0
        return {
            "ready": control_ready,
            "state": (
                "action"
                if action_remaining > 0.0
                else "moving"
                if self._moving
                else "idle"
                if ready
                else "unavailable"
            ),
            "bridge_epoch": self._bridge_epoch,
            "lowstate_age_ms": (
                None if lowstate_age_s is None else round(float(lowstate_age_s) * 1_000)
            ),
            "lowstate_publishers": max(0, int(lowstate_publishers)),
            "sport_subscribers": max(0, int(sport_subscribers)),
            "sport_publishers": max(0, int(sport_publishers)),
            "own_sport_publishers": max(0, int(own_sport_publishers)),
            "foreign_named_sport_publishers": max(
                0, int(foreign_named_sport_publishers)
            ),
            "bare_unitree_sport_publishers": max(
                0, int(bare_unitree_sport_publishers)
            ),
            "expected_bare_sport_publishers": self.expected_bare_sport_publishers,
            "command_age_ms": (
                None if command_age is None else round(command_age * 1_000)
            ),
            "accepted_command": {
                "deadman": self._deadman,
                "linear_x": self._target[0],
                "linear_y": self._target[1],
                "angular_z": self._target[2],
            },
            "command_ack": projected_command_ack,
            "last_error": self._last_error,
            "action_guard": {
                "active": action_remaining > 0.0,
                "action": self._action_hold_name or None,
                "remaining_ms": round(action_remaining * 1_000),
            },
            "limits": {
                "max_linear_x": self.max_linear_x,
                "max_linear_y": self.max_linear_y,
                "max_angular_z": self.max_angular_z,
                "command_timeout_ms": round(self.command_timeout_s * 1_000),
            },
        }
