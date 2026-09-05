#!/usr/bin/env python3
"""Bounded, read-only evidence capture for Go2 SportModeState.

The default invocation only prints the fixed observation plan.  Live capture
requires ``--observe`` and can subscribe to one of two literal, allowlisted
topics.  ROS imports are deliberately local to the live path so repository
tests and dry runs do not require a ROS installation.
"""

from __future__ import annotations

import argparse
import json
import math
import numbers
import os
import stat
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "robot-scope/go2-locomotion-state-observation"
SCHEMA_VERSION = 2
ALLOWLISTED_TOPICS = ("/sportmodestate", "/lf/sportmodestate")
MODE_DURATIONS_S = {"S0": 10.0, "S1": 10.0, "STOCK-1": 20.0}
MAX_RETAINED_SAMPLES = 128
MAX_RETAINED_TRANSITIONS = 32
MAX_ABS_VELOCITY_MPS = 20.0
MAX_ABS_POSITION_M = 1_000_000.0
BODY_VELOCITY_OVER_NOISE_MPS = 0.01
MIN_SAMPLE_COUNT = 10
MIN_OBSERVED_RATE_HZ = 5.0
MAX_INTERSAMPLE_GAP_S = 0.5
MAX_FINAL_SAMPLE_AGE_S = 0.5
MAX_INITIAL_SAMPLE_AGE_S = 0.5
DURATION_COMPLETION_TOLERANCE_S = 0.25
MIN_PUBLISHER_COUNT = 1
MAX_PUBLISHER_COUNT = 4
PUBLISHER_SAMPLE_PERIOD_S = 0.5
PUBLISHER_DISCOVERY_TIMEOUT_S = 2.0
PUBLISHER_DISCOVERY_POLL_S = 0.05
FIRST_SAMPLE_READY_TIMEOUT_S = 2.0
OUTPUT_DIRECTORY = Path.home() / ".robot-scope" / "locomotion-observations"


class ObservationError(ValueError):
    """Raised when a SportModeState sample violates its fixed contract."""


@dataclass(frozen=True)
class StateSample:
    elapsed_s: float
    mode: int
    gait_type: int
    error_code: int
    velocity: tuple[float, float, float]
    position: tuple[float, float, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "elapsed_s": round(self.elapsed_s, 6),
            "mode": self.mode,
            "gait_type": self.gait_type,
            "error_code": self.error_code,
            "velocity": [round(value, 6) for value in self.velocity],
            "position": [round(value, 6) for value in self.position],
        }


def _bounded_integer(value: Any, label: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise ObservationError(f"{label} must be an integer")
    result = int(value)
    if result < 0 or result > maximum:
        raise ObservationError(f"{label} is outside 0..{maximum}")
    return result


def validate_sample(message: Any, elapsed_s: float) -> StateSample:
    if not math.isfinite(elapsed_s) or elapsed_s < 0.0:
        raise ObservationError("elapsed_s must be finite and non-negative")
    raw_velocity = getattr(message, "velocity", None)
    if not isinstance(raw_velocity, Sequence) or len(raw_velocity) != 3:
        raise ObservationError("velocity must contain exactly three values")
    try:
        velocity = tuple(float(value) for value in raw_velocity)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ObservationError("velocity values must be numeric") from exc
    if any(
        not math.isfinite(value) or abs(value) > MAX_ABS_VELOCITY_MPS
        for value in velocity
    ):
        raise ObservationError("velocity contains a non-finite or unsafe value")
    raw_position = getattr(message, "position", None)
    if not isinstance(raw_position, Sequence) or len(raw_position) != 3:
        raise ObservationError("position must contain exactly three values")
    try:
        position = tuple(float(value) for value in raw_position)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ObservationError("position values must be numeric") from exc
    if any(
        not math.isfinite(value) or abs(value) > MAX_ABS_POSITION_M
        for value in position
    ):
        raise ObservationError("position contains a non-finite or unsafe value")
    return StateSample(
        elapsed_s=elapsed_s,
        mode=_bounded_integer(getattr(message, "mode", None), "mode", 255),
        gait_type=_bounded_integer(
            getattr(message, "gait_type", None), "gait_type", 255
        ),
        error_code=_bounded_integer(
            getattr(message, "error_code", None), "error_code", 0xFFFFFFFF
        ),
        velocity=velocity,  # type: ignore[arg-type]
        position=position,  # type: ignore[arg-type]
    )


class ObservationAccumulator:
    """Keep online statistics plus explicitly bounded raw evidence."""

    def __init__(self) -> None:
        self.sample_count = 0
        self.rejected_count = 0
        self.first_sample: StateSample | None = None
        self.last_sample: StateSample | None = None
        self.samples: deque[StateSample] = deque(maxlen=MAX_RETAINED_SAMPLES)
        self.transitions: list[dict[str, Any]] = []
        self.transition_count = 0
        self.first_mode_or_gait_transition: dict[str, Any] | None = None
        self.first_mode_transition_elapsed_s: float | None = None
        self.first_gait_transition_elapsed_s: float | None = None
        self.first_velocity_over_noise: dict[str, Any] | None = None
        self.max_intersample_gap_s = 0.0
        self.velocity_sum = [0.0, 0.0, 0.0]
        self.velocity_sum_squares = [0.0, 0.0, 0.0]
        self.velocity_abs_max = [0.0, 0.0, 0.0]
        self.speed_max = 0.0
        self.position_min = [math.inf, math.inf, math.inf]
        self.position_max = [-math.inf, -math.inf, -math.inf]

    def add(self, message: Any, elapsed_s: float) -> bool:
        try:
            sample = validate_sample(message, elapsed_s)
        except ObservationError:
            self.rejected_count += 1
            return False

        previous = self.last_sample
        if previous is not None and sample.elapsed_s < previous.elapsed_s:
            self.rejected_count += 1
            return False
        if previous is not None:
            self.max_intersample_gap_s = max(
                self.max_intersample_gap_s,
                sample.elapsed_s - previous.elapsed_s,
            )
        if previous is not None and (
            sample.mode != previous.mode or sample.gait_type != previous.gait_type
        ):
            transition = {
                "elapsed_s": round(sample.elapsed_s, 6),
                "from": {
                    "mode": previous.mode,
                    "gait_type": previous.gait_type,
                },
                "to": {
                    "mode": sample.mode,
                    "gait_type": sample.gait_type,
                },
            }
            self.transition_count += 1
            if self.first_mode_or_gait_transition is None:
                self.first_mode_or_gait_transition = transition
            if (
                sample.mode != previous.mode
                and self.first_mode_transition_elapsed_s is None
            ):
                self.first_mode_transition_elapsed_s = sample.elapsed_s
            if (
                sample.gait_type != previous.gait_type
                and self.first_gait_transition_elapsed_s is None
            ):
                self.first_gait_transition_elapsed_s = sample.elapsed_s
            if len(self.transitions) < MAX_RETAINED_TRANSITIONS:
                self.transitions.append(transition)

        if self.first_sample is None:
            self.first_sample = sample
        self.last_sample = sample
        self.samples.append(sample)
        self.sample_count += 1
        speed = math.sqrt(sum(value * value for value in sample.velocity))
        if (
            self.first_velocity_over_noise is None
            and speed > BODY_VELOCITY_OVER_NOISE_MPS
        ):
            self.first_velocity_over_noise = {
                "elapsed_s": round(sample.elapsed_s, 6),
                "speed_mps": round(speed, 6),
                "velocity_mps": [round(value, 6) for value in sample.velocity],
            }
        self.speed_max = max(self.speed_max, speed)
        for index, value in enumerate(sample.velocity):
            self.velocity_sum[index] += value
            self.velocity_sum_squares[index] += value * value
            self.velocity_abs_max[index] = max(
                self.velocity_abs_max[index], abs(value)
            )
        for index, value in enumerate(sample.position):
            self.position_min[index] = min(self.position_min[index], value)
            self.position_max[index] = max(self.position_max[index], value)
        return True

    def evidence(self) -> dict[str, Any]:
        divisor = max(self.sample_count, 1)
        return {
            "sample_count": self.sample_count,
            "rejected_count": self.rejected_count,
            "retained_sample_count": len(self.samples),
            "retained_sample_limit": MAX_RETAINED_SAMPLES,
            "first_sample": self.first_sample.as_dict() if self.first_sample else None,
            "last_sample": self.last_sample.as_dict() if self.last_sample else None,
            "recent_samples": [sample.as_dict() for sample in self.samples],
            "transition_count": self.transition_count,
            "retained_transition_count": len(self.transitions),
            "retained_transition_limit": MAX_RETAINED_TRANSITIONS,
            "transitions": self.transitions,
            "first_mode_or_gait_transition": self.first_mode_or_gait_transition,
            "first_mode_transition_elapsed_s": (
                round(self.first_mode_transition_elapsed_s, 6)
                if self.first_mode_transition_elapsed_s is not None
                else None
            ),
            "first_gait_transition_elapsed_s": (
                round(self.first_gait_transition_elapsed_s, 6)
                if self.first_gait_transition_elapsed_s is not None
                else None
            ),
            "body_velocity_over_noise_threshold_mps": (
                BODY_VELOCITY_OVER_NOISE_MPS
            ),
            "body_velocity_threshold_interpretation": (
                "CANDIDATE_ONLY_UNTIL_S0_NOISE_IS_MEASURED"
            ),
            "first_body_velocity_over_noise": self.first_velocity_over_noise,
            "max_intersample_gap_s": (
                round(self.max_intersample_gap_s, 6)
                if self.sample_count >= 2
                else None
            ),
            "velocity_noise": {
                "axis_mean_mps": [
                    round(total / divisor, 6) for total in self.velocity_sum
                ],
                "axis_rms_mps": [
                    round(math.sqrt(total / divisor), 6)
                    for total in self.velocity_sum_squares
                ],
                "axis_max_abs_mps": [
                    round(value, 6) for value in self.velocity_abs_max
                ],
                "max_vector_speed_mps": round(self.speed_max, 6),
            },
            "position_noise": {
                "axis_span_m": [
                    round(self.position_max[index] - self.position_min[index], 6)
                    if self.sample_count
                    else 0.0
                    for index in range(3)
                ],
                "first_to_last_delta_m": [
                    round(self.last_sample.position[index] - self.first_sample.position[index], 6)
                    if self.first_sample is not None and self.last_sample is not None
                    else 0.0
                    for index in range(3)
                ],
            },
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=tuple(MODE_DURATIONS_S), default="S0")
    parser.add_argument(
        "--topic", choices=ALLOWLISTED_TOPICS, default=ALLOWLISTED_TOPICS[0]
    )
    parser.add_argument(
        "--observe",
        action="store_true",
        help="perform the fixed-duration read-only subscription",
    )
    return parser


def require_fixed_selection(mode: str, topic: str) -> None:
    if mode not in MODE_DURATIONS_S:
        raise ObservationError("mode is not one of the fixed observations")
    if topic not in ALLOWLISTED_TOPICS:
        raise ObservationError("topic is not in the fixed SportModeState allowlist")


def observation_plan(mode: str, topic: str) -> dict[str, Any]:
    require_fixed_selection(mode, topic)
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "dry_run": True,
        "read_only": True,
        "mode": mode,
        "topic": topic,
        "duration_s": MODE_DURATIONS_S[mode],
        "creates_publishers": False,
        "creates_control_requests": False,
        "writes_evidence": False,
    }


def readiness_marker(mode: str, topic: str, publisher_count: int) -> dict[str, Any]:
    """Build the live READY marker only after a valid first sample exists."""

    require_fixed_selection(mode, topic)
    if (
        isinstance(publisher_count, bool)
        or not isinstance(publisher_count, int)
        or not MIN_PUBLISHER_COUNT <= publisher_count <= MAX_PUBLISHER_COUNT
    ):
        raise ObservationError("observer publisher count is not ready")
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "status": "OBSERVER_READY",
        "read_only": True,
        "mode": mode,
        "topic": topic,
        "fixed_duration_s": MODE_DURATIONS_S[mode],
        "publisher_count": publisher_count,
        "valid_first_sample": True,
        "creates_publishers": False,
        "creates_control_requests": False,
    }


def assess_evidence(
    *,
    mode: str,
    actual_duration_s: float,
    evidence: dict[str, Any],
    publisher_counts: Sequence[int],
) -> dict[str, Any]:
    """Apply fixed evidence-quality gates without interpreting locomotion outcome."""

    duration_s = MODE_DURATIONS_S[mode]
    failures: list[str] = []
    if (
        not math.isfinite(actual_duration_s)
        or actual_duration_s < duration_s - DURATION_COMPLETION_TOLERANCE_S
    ):
        failures.append("OBSERVATION_DURATION_INCOMPLETE")

    sample_count = int(evidence.get("sample_count", 0))
    rejected_count = int(evidence.get("rejected_count", 0))
    observed_rate_hz = float(evidence.get("observed_rate_hz", 0.0))
    max_gap = evidence.get("max_intersample_gap_s")
    first_sample = evidence.get("first_sample")
    initial_sample_age = (
        first_sample.get("elapsed_s") if isinstance(first_sample, Mapping) else None
    )
    final_stale_age = evidence.get("final_sample_age_s")
    if sample_count < MIN_SAMPLE_COUNT:
        failures.append("SAMPLE_COUNT_TOO_LOW")
    if not math.isfinite(observed_rate_hz) or observed_rate_hz < MIN_OBSERVED_RATE_HZ:
        failures.append("SAMPLE_RATE_TOO_LOW")
    if rejected_count:
        failures.append("INVALID_SAMPLE_REJECTED")
    if (
        max_gap is None
        or not math.isfinite(float(max_gap))
        or float(max_gap) > MAX_INTERSAMPLE_GAP_S
    ):
        failures.append("INTERSAMPLE_GAP_TOO_LARGE")
    if (
        initial_sample_age is None
        or not math.isfinite(float(initial_sample_age))
        or not 0.0 <= float(initial_sample_age) <= MAX_INITIAL_SAMPLE_AGE_S
    ):
        failures.append("INITIAL_SAMPLE_LATE")
    if (
        final_stale_age is None
        or not math.isfinite(float(final_stale_age))
        or float(final_stale_age) > MAX_FINAL_SAMPLE_AGE_S
    ):
        failures.append("FINAL_SAMPLE_STALE")

    counts = [int(value) for value in publisher_counts]
    if not counts or min(counts) < MIN_PUBLISHER_COUNT:
        failures.append("PUBLISHER_COUNT_ZERO")
    if counts and max(counts) > MAX_PUBLISHER_COUNT:
        failures.append("PUBLISHER_COUNT_TOO_HIGH")
    if counts and len(set(counts)) != 1:
        failures.append("PUBLISHER_COUNT_CHANGED")

    return {
        "status": "PASS" if not failures else "FAIL",
        "failure_reasons": failures,
        "gates": {
            "duration_required_s": duration_s,
            "duration_tolerance_s": DURATION_COMPLETION_TOLERANCE_S,
            "minimum_sample_count": MIN_SAMPLE_COUNT,
            "minimum_rate_hz": MIN_OBSERVED_RATE_HZ,
            "maximum_intersample_gap_s": MAX_INTERSAMPLE_GAP_S,
            "maximum_initial_sample_age_s": MAX_INITIAL_SAMPLE_AGE_S,
            "maximum_final_sample_age_s": MAX_FINAL_SAMPLE_AGE_S,
            "publisher_count_range": [MIN_PUBLISHER_COUNT, MAX_PUBLISHER_COUNT],
            "publisher_count_must_remain_stable": True,
        },
        "publisher_counts_seen": counts,
    }


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise
    directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _prepare_output_directory(path: Path = OUTPUT_DIRECTORY) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or path.is_symlink():
        raise RuntimeError("fixed evidence directory is not a real directory")
    if metadata.st_uid != os.getuid():
        raise RuntimeError("fixed evidence directory is not owned by this user")
    os.chmod(path, 0o700)


def _output_path(mode: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return OUTPUT_DIRECTORY / f"go2-locomotion-{mode.lower()}-{stamp}.json"


def observe(mode: str, topic: str) -> tuple[dict[str, Any], Path]:
    require_fixed_selection(mode, topic)
    # These imports are intentionally unreachable during dry-run and unit tests.
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import (
        DurabilityPolicy,
        HistoryPolicy,
        QoSProfile,
        ReliabilityPolicy,
    )
    from unitree_go.msg import SportModeState

    duration_s = MODE_DURATIONS_S[mode]
    accumulator = ObservationAccumulator()
    started_monotonic = 0.0
    ended_monotonic = 0.0
    started_at = ""
    publisher_counts: list[int] = []
    warmup_message: Any | None = None
    warmup_error: ObservationError | None = None
    capture_started = False

    rclpy.init(args=[])
    node = None
    subscription = None

    def receive(message: Any) -> None:
        nonlocal warmup_error, warmup_message
        if not capture_started:
            try:
                validate_sample(message, 0.0)
            except ObservationError as exc:
                warmup_error = exc
            else:
                warmup_message = message
            return
        accumulator.add(message, time.monotonic() - started_monotonic)

    try:
        node = Node(
            "robot_scope_go2_locomotion_state_observer",
            enable_rosout=False,
            start_parameter_services=False,
        )
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        discovery_deadline = time.monotonic() + PUBLISHER_DISCOVERY_TIMEOUT_S
        publisher_count = len(node.get_publishers_info_by_topic(topic))
        while (
            publisher_count == 0
            and rclpy.ok()
            and time.monotonic() < discovery_deadline
        ):
            time.sleep(PUBLISHER_DISCOVERY_POLL_S)
            publisher_count = len(node.get_publishers_info_by_topic(topic))
        if not MIN_PUBLISHER_COUNT <= publisher_count <= MAX_PUBLISHER_COUNT:
            raise ObservationError("observer publisher discovery is not ready")
        subscription = node.create_subscription(SportModeState, topic, receive, qos)
        first_sample_deadline = time.monotonic() + FIRST_SAMPLE_READY_TIMEOUT_S
        while (
            warmup_message is None
            and warmup_error is None
            and rclpy.ok()
            and time.monotonic() < first_sample_deadline
        ):
            rclpy.spin_once(node, timeout_sec=PUBLISHER_DISCOVERY_POLL_S)
        if warmup_error is not None:
            raise ObservationError("observer rejected its first state sample") from warmup_error
        if warmup_message is None:
            raise ObservationError("observer did not receive a valid first state sample")
        confirmed_publishers = len(node.get_publishers_info_by_topic(topic))
        if confirmed_publishers != publisher_count:
            raise ObservationError("observer publisher count changed before READY")
        marker = readiness_marker(mode, topic, confirmed_publishers)
        publisher_counts.extend((publisher_count, confirmed_publishers))
        started_monotonic = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        capture_started = True
        if not accumulator.add(warmup_message, 0.0):
            raise ObservationError("observer could not retain its READY sample")
        print(json.dumps(marker, sort_keys=True), flush=True)
        deadline = started_monotonic + duration_s
        next_publisher_sample = started_monotonic + PUBLISHER_SAMPLE_PERIOD_S
        while rclpy.ok() and time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            rclpy.spin_once(node, timeout_sec=max(0.0, min(0.1, remaining)))
            now = time.monotonic()
            if now >= next_publisher_sample:
                publisher_counts.append(len(node.get_publishers_info_by_topic(topic)))
                next_publisher_sample = now + PUBLISHER_SAMPLE_PERIOD_S
        ended_monotonic = time.monotonic()
        publisher_counts.append(len(node.get_publishers_info_by_topic(topic)))
    finally:
        if node is not None and subscription is not None:
            node.destroy_subscription(subscription)
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    actual_duration_s = max(0.0, ended_monotonic - started_monotonic)
    evidence = accumulator.evidence()
    evidence["observed_rate_hz"] = round(
        accumulator.sample_count / max(actual_duration_s, 1e-9), 6
    )
    evidence["final_sample_age_s"] = (
        round(max(0.0, actual_duration_s - accumulator.last_sample.elapsed_s), 6)
        if accumulator.last_sample is not None
        else None
    )
    assessment = assess_evidence(
        mode=mode,
        actual_duration_s=actual_duration_s,
        evidence=evidence,
        publisher_counts=publisher_counts,
    )
    evidence["publisher_counts_seen"] = assessment["publisher_counts_seen"]
    evidence["publisher_count_before"] = (
        publisher_counts[0] if publisher_counts else None
    )
    evidence["publisher_count_after"] = (
        publisher_counts[-1] if publisher_counts else None
    )
    evidence["publisher_count_min"] = min(publisher_counts, default=None)
    evidence["publisher_count_max"] = max(publisher_counts, default=None)
    payload = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "status": assessment["status"],
        "failure_reasons": assessment["failure_reasons"],
        "dry_run": False,
        "read_only": True,
        "mode": mode,
        "topic": topic,
        "fixed_duration_s": duration_s,
        "actual_duration_s": round(actual_duration_s, 6),
        "started_at": started_at,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "creates_publishers": False,
        "creates_control_requests": False,
        "evidence_gates": assessment["gates"],
        "evidence": evidence,
    }
    _prepare_output_directory()
    output_path = _output_path(mode)
    _write_private_json(output_path, payload)
    return payload, output_path


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.observe:
        print(json.dumps(observation_plan(args.mode, args.topic), sort_keys=True))
        return 0
    payload, output_path = observe(args.mode, args.topic)
    print(
        json.dumps(
            {
                "evidence_path": str(output_path),
                "mode": payload["mode"],
                "sample_count": payload["evidence"]["sample_count"],
                "status": payload["status"],
                "failure_reasons": payload["failure_reasons"],
            },
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
