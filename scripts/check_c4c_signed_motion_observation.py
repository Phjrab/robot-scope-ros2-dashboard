#!/usr/bin/env python3
"""Read-only qualification of signed C4C motion evidence via the dashboard."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.request import urlopen


CONTROL_URL = "http://127.0.0.1:8088/api/v1/control"
SOURCE_ID = "unitree_go.sport_mode_state.position"
SCHEMA = "robot-scope.c4c-signed-observation/v1"
FULL_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_HTTP_BYTES = 1024 * 1024
POLL_S = 0.10
DURATIONS_S = {"stationary": 300.0, "dynamic": 20.0}
MAX_STATIONARY_DRIFT_M = 0.005
MIN_DYNAMIC_DISPLACEMENT_M = 0.005
MAX_DYNAMIC_DISPLACEMENT_M = 0.30
OUTPUT_DIRECTORY = Path.home() / ".robot-scope" / "c4c-observations"


class SignedObservationError(ValueError):
    """Raised when signed observation evidence fails closed."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SignedObservationError(f"{label} is invalid")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SignedObservationError(f"{label} is invalid")
    result = float(value)
    if not math.isfinite(result):
        raise SignedObservationError(f"{label} is invalid")
    return result


def _exact_zero(value: Any, label: str) -> None:
    command = _mapping(value, label)
    if command.get("deadman") is not False:
        raise SignedObservationError(f"{label} is not exact zero")
    for field in ("linear_x", "linear_y", "angular_z"):
        if _finite(command.get(field), f"{label} {field}") != 0.0:
            raise SignedObservationError(f"{label} is not exact zero")


@dataclass(frozen=True)
class QualifiedSample:
    generation: str
    sequence: int
    stamp_ns: int
    position: tuple[float, float, float]
    callback_age_ms: float
    receiver_age_ms: float


def validate_snapshot(
    payload: Mapping[str, Any], *, expected_release: str
) -> QualifiedSample:
    """Validate one public snapshot without granting any control authority."""

    if FULL_COMMIT_RE.fullmatch(expected_release) is None:
        raise SignedObservationError("expected release is not an exact commit")
    control = _mapping(payload.get("control"), "control")
    if control.get("available") is not False:
        raise SignedObservationError("control became available during observation")
    lease = _mapping(control.get("lease"), "lease")
    if lease.get("active") is True or lease.get("token"):
        raise SignedObservationError("control lease exists during observation")
    _exact_zero(control.get("command"), "manager command")

    bridge = _mapping(control.get("bridge"), "bridge")
    if (
        bridge.get("bridge_role") != "motion_observer"
        or bridge.get("authenticated") is not True
        or bridge.get("observation_connected") is not True
        or any(
            bridge.get(field) is not False
            for field in ("ready", "connected", "available")
        )
        or bridge.get("release_commit") != expected_release
    ):
        raise SignedObservationError("signed observation role is not isolated")
    expected_bare = bridge.get("expected_bare_sport_publishers")
    if (
        isinstance(expected_bare, bool)
        or not isinstance(expected_bare, int)
        or not 0 <= expected_bare <= 64
        or bridge.get("own_sport_publishers") != 0
        or bridge.get("foreign_named_sport_publishers") != 0
        or bridge.get("bare_unitree_sport_publishers") != expected_bare
        or bridge.get("total_sport_publishers") != expected_bare
        or bridge.get("lowstate_publishers") != 1
    ):
        raise SignedObservationError("observer graph isolation is invalid")
    _exact_zero(bridge.get("accepted_command"), "observer accepted command")

    evidence = _mapping(bridge.get("request_evidence"), "request evidence")
    zero_fields = (
        "published_count",
        "stop_count",
        "move_count",
        "zero_move_count",
        "nonzero_move_count",
        "malformed_move_count",
        "action_count",
        "other_count",
        "motion_run_id",
        "motion_run_nonzero_move_count",
    )
    if (
        evidence.get("last_api_id") is not None
        or evidence.get("motion_run_active") is not False
        or any(evidence.get(field) != 0 for field in zero_fields)
    ):
        raise SignedObservationError("observer published a request")

    observation = _mapping(bridge.get("motion_observation"), "motion observation")
    if (
        observation.get("schema") != "robot-scope.motion-observation"
        or observation.get("schema_version") != 1
        or observation.get("source_id") != SOURCE_ID
        or observation.get("release_commit") != expected_release
        or observation.get("quality") != "READY"
        or observation.get("invalid_reason") != ""
        or observation.get("origin_reset_detected") is not False
        or observation.get("coordinate_space") != "unitree_go.sport_mode_state.local"
        or observation.get("frame_id") is not None
        or observation.get("origin") != "vendor_local_origin_unverified"
        or observation.get("orientation_xyzw") is not None
    ):
        raise SignedObservationError("motion observation contract is invalid")
    generation = observation.get("producer_generation")
    sequence = observation.get("source_sequence")
    stamp_ns = observation.get("source_stamp_ns")
    if (
        not isinstance(generation, str)
        or not 16 <= len(generation) <= 128
        or isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or sequence <= 0
        or isinstance(stamp_ns, bool)
        or not isinstance(stamp_ns, int)
        or stamp_ns <= 0
    ):
        raise SignedObservationError("motion observation progression is invalid")
    position_value = observation.get("position_xyz")
    if not isinstance(position_value, list) or len(position_value) != 3:
        raise SignedObservationError("motion observation position is invalid")
    position = tuple(
        _finite(value, "motion observation position") for value in position_value
    )
    callback_age_ms = _finite(
        observation.get("callback_receive_age_ms"), "callback age"
    )
    receiver_age_ms = _finite(observation.get("receiver_status_age_ms"), "receiver age")
    if not 0.0 <= callback_age_ms <= 500.0 or not 0.0 <= receiver_age_ms <= 750.0:
        raise SignedObservationError("motion observation is stale")
    return QualifiedSample(
        generation=generation,
        sequence=sequence,
        stamp_ns=stamp_ns,
        position=position,
        callback_age_ms=callback_age_ms,
        receiver_age_ms=receiver_age_ms,
    )


class ObservationRun:
    def __init__(self, *, expected_release: str, mode: str) -> None:
        self.expected_release = expected_release
        self.mode = mode
        self.first: QualifiedSample | None = None
        self.previous: QualifiedSample | None = None
        self.sample_count = 0
        self.progress_count = 0
        self.max_displacement_m = 0.0
        self.max_callback_age_ms = 0.0
        self.max_receiver_age_ms = 0.0

    def add(self, payload: Mapping[str, Any]) -> None:
        sample = validate_snapshot(payload, expected_release=self.expected_release)
        if self.first is None:
            self.first = sample
        previous = self.previous
        if previous is not None:
            if sample.generation != previous.generation:
                raise SignedObservationError("observer generation changed")
            if (
                sample.sequence < previous.sequence
                or sample.stamp_ns < previous.stamp_ns
            ):
                raise SignedObservationError("source progression regressed")
            if (
                sample.sequence == previous.sequence
                and sample.stamp_ns != previous.stamp_ns
            ):
                raise SignedObservationError("source progression is inconsistent")
            if sample.sequence > previous.sequence:
                if sample.stamp_ns <= previous.stamp_ns:
                    raise SignedObservationError("source stamp did not progress")
                self.progress_count += 1
        baseline = self.first
        displacement = math.hypot(
            sample.position[0] - baseline.position[0],
            sample.position[1] - baseline.position[1],
        )
        limit = (
            MAX_STATIONARY_DRIFT_M
            if self.mode == "stationary"
            else MAX_DYNAMIC_DISPLACEMENT_M
        )
        if displacement > limit:
            raise SignedObservationError("observed displacement exceeded mode limit")
        self.max_displacement_m = max(self.max_displacement_m, displacement)
        self.max_callback_age_ms = max(self.max_callback_age_ms, sample.callback_age_ms)
        self.max_receiver_age_ms = max(self.max_receiver_age_ms, sample.receiver_age_ms)
        self.previous = sample
        self.sample_count += 1

    def result(self, *, duration_s: float) -> dict[str, Any]:
        if self.first is None or self.previous is None or self.progress_count == 0:
            raise SignedObservationError(
                "no progressing signed observation was captured"
            )
        if (
            self.mode == "dynamic"
            and self.max_displacement_m < MIN_DYNAMIC_DISPLACEMENT_M
        ):
            raise SignedObservationError(
                "dynamic observation did not reach significant displacement"
            )
        return {
            "schema": SCHEMA,
            "mode": self.mode,
            "status": "PASS",
            "expected_release": self.expected_release,
            "generation": self.first.generation,
            "duration_s": round(duration_s, 6),
            "sample_count": self.sample_count,
            "progress_count": self.progress_count,
            "first_sequence": self.first.sequence,
            "last_sequence": self.previous.sequence,
            "max_displacement_m": round(self.max_displacement_m, 6),
            "max_callback_age_ms": round(self.max_callback_age_ms, 3),
            "max_receiver_age_ms": round(self.max_receiver_age_ms, 3),
            "motion_command_created": False,
        }


def _read_snapshot() -> Mapping[str, Any]:
    with urlopen(CONTROL_URL, timeout=1.0) as response:
        encoded = response.read(MAX_HTTP_BYTES + 1)
    if len(encoded) > MAX_HTTP_BYTES:
        raise SignedObservationError("dashboard response is too large")
    value = json.loads(encoded)
    return _mapping(value, "dashboard response")


def _write_result(result: Mapping[str, Any]) -> Path:
    OUTPUT_DIRECTORY.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = OUTPUT_DIRECTORY / f"c4c-signed-{result['mode']}-{stamp}.json"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(dict(result), stream, indent=2, sort_keys=True)
        stream.write("\n")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--observe-stationary", action="store_true")
    mode.add_argument("--observe-dynamic", action="store_true")
    parser.add_argument("--expected-release")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected = "dynamic" if args.observe_dynamic else "stationary"
    if not args.observe_stationary and not args.observe_dynamic:
        print(
            json.dumps(
                {
                    "mode": "dry_run",
                    "status": "NOT_RUN",
                    "control_url": CONTROL_URL,
                    "creates_ros_endpoints": False,
                    "creates_motion_commands": False,
                    "durations_s": DURATIONS_S,
                },
                sort_keys=True,
            )
        )
        return 0
    expected_release = str(args.expected_release or "")
    if FULL_COMMIT_RE.fullmatch(expected_release) is None:
        raise SystemExit("--expected-release must be one exact 40-character commit")
    duration = DURATIONS_S[selected]
    run = ObservationRun(expected_release=expected_release, mode=selected)
    started = time.monotonic()
    deadline = started + duration
    while time.monotonic() < deadline:
        run.add(_read_snapshot())
        time.sleep(POLL_S)
    result = run.result(duration_s=time.monotonic() - started)
    path = _write_result(result)
    print(json.dumps({**result, "evidence_path": str(path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
