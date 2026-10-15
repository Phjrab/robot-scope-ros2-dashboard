"""Bounded localization input evidence; cannot grant readiness or alter clocks."""

from __future__ import annotations

import copy
import math
import re
from collections import deque
from typing import Any, Mapping


SCHEMA = "robot-scope.localization-input-diagnostics.v1"
MAX_COUNTER = 2**53 - 1
MAX_TRACE = 8
REASONS = frozenset({
    "accepted", "publisher_not_unique", "unexpected_frame", "missing_stamp",
    "stale_stamp", "future_stamp", "invalid_stamp", "nonincreasing_stamp",
    "invalid_pose", "invalid_cloud_layout", "insufficient_scan_bins",
    "translation_jump", "heading_jump", "timing_discontinuity",
    "controller_gate_rejected", "callback_error",
})
NULL_REASONS = frozenset({
    "no_callbacks", "all_received_rejected", "rewarming_after_source_change",
    "insufficient_accepted_samples", "unobservable",
})
WAIT_REASONS = frozenset({
    "publishers_not_unique", "cloud_not_fresh", "odometry_not_fresh",
    "inputs_ready_waiting_initial_pose", "localized",
})
_INPUTS = {
    "cloud": ("/velodyne_points", "sensor_msgs/msg/PointCloud2"),
    "odometry": ("/Odometry", "nav_msgs/msg/Odometry"),
}


def _counter(value: Any, maximum: int = MAX_COUNTER) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ValueError("localization diagnostic counter is invalid")
    return value


def _number(value: Any, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("localization diagnostic number is invalid")
    if not math.isfinite(value) or not 0 <= value <= 2**63 - 1:
        raise ValueError("localization diagnostic number is invalid")
    return float(value)


def _label(value: Any, maximum: int = 128) -> str:
    if not isinstance(value, str) or len(value) > maximum or not re.fullmatch(r"[A-Za-z0-9_/:.\-]*", value):
        raise ValueError("localization diagnostic label is invalid")
    return value


def _receipt(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("localization diagnostic receipt is invalid")
    stamp = value.get("source_stamp_ns")
    return {
        "source_stamp_ns": None if stamp is None else _counter(stamp, 2**63 - 1),
        "wall_ns": _counter(value.get("wall_ns"), 2**63 - 1),
        "monotonic_s": _number(value.get("monotonic_s")),
        "frame": _label(value.get("frame")),
        "child_frame": _label(value.get("child_frame")),
        "publisher_count": _counter(value.get("publisher_count"), 1_000_000),
        "source_generation": _counter(value.get("source_generation")),
    }


def sanitize_localization_diagnostics(value: Any) -> dict[str, Any] | None:
    """Whitelist optional runtime telemetry before API projection.

    An old producer may omit this object. Invalid optional diagnostics are
    unavailable, and cannot invalidate or approve the independent health gate.
    """
    try:
        if not isinstance(value, Mapping) or value.get("schema") != SCHEMA:
            return None
        result = {
            "schema": SCHEMA,
            "process_generation": _counter(value.get("process_generation"), 2**31 - 1),
            "runtime_instance_generation": _label(value.get("runtime_instance_generation"), 80),
            "health_sequence": _counter(value.get("health_sequence")),
            "observed_wall_ns": _counter(value.get("observed_wall_ns"), 2**63 - 1),
            "observed_monotonic_s": _number(value.get("observed_monotonic_s")),
            "executor_lock_wait_s": None,
            "inputs": {},
        }
        if value.get("initialization_wait_reason") not in WAIT_REASONS:
            return None
        result["initialization_wait_reason"] = value["initialization_wait_reason"]
        inputs = value.get("inputs")
        if not isinstance(inputs, Mapping):
            return None
        for name, (topic, message_type) in _INPUTS.items():
            raw = inputs.get(name)
            if not isinstance(raw, Mapping) or raw.get("topic") != topic or raw.get("message_type") != message_type:
                return None
            if raw.get("qos") != {"reliability": "BEST_EFFORT", "durability": "VOLATILE", "history": "KEEP_LAST", "depth": 5}:
                return None
            item = {"topic": topic, "message_type": message_type, "qos": dict(raw["qos"])}
            for key in ("callback_count", "accepted_count", "rejected_count", "accepted_since_generation", "source_generation", "publisher_change_count"):
                item[key] = _counter(raw.get(key))
            publisher_count = raw.get("publisher_count")
            item["publisher_count"] = None if publisher_count is None else _counter(publisher_count, 1_000_000)
            item["reject_counts"] = {reason: _counter(raw.get("reject_counts", {}).get(reason, 0)) for reason in sorted(REASONS - {"accepted"})}
            for key in ("age_null_reason", "rate_null_reason"):
                reason = raw.get(key)
                if reason is not None and reason not in NULL_REASONS:
                    return None
                item[key] = reason
            for key in ("accepted_age_s", "accepted_frequency_hz"):
                item[key] = _number(raw.get(key), nullable=True)
            item["last_received"] = _receipt(raw.get("last_received"))
            item["last_accepted"] = _receipt(raw.get("last_accepted"))
            item["graph_observed_monotonic_s"] = _number(raw.get("graph_observed_monotonic_s"), nullable=True)
            identities = raw.get("publishers")
            if identities is None:
                item["publishers"] = None
            elif isinstance(identities, list) and len(identities) <= 4:
                item["publishers"] = []
                for identity in identities:
                    item["publishers"].append({key: _label(identity.get(key), 128) for key in ("gid", "node_name", "node_namespace", "reliability", "durability")})
            else:
                return None
            trace = raw.get("trace")
            if not isinstance(trace, list) or len(trace) > MAX_TRACE:
                return None
            item["trace"] = []
            for event in trace:
                if not isinstance(event, Mapping) or event.get("reason") not in REASONS:
                    return None
                item["trace"].append({**_receipt(event), "reason": event["reason"]})
            result["inputs"][name] = item
        return result
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


class LocalizationInputDiagnostics:
    """One input's counters and small receipt ring, owned by one ROS executor."""

    def __init__(self, name: str) -> None:
        self.topic, self.message_type = _INPUTS[name]
        self.callback_count = self.accepted_count = self.rejected_count = 0
        self.source_generation = self.publisher_change_count = 0
        self._accepted: deque[dict[str, Any]] = deque(maxlen=32)
        self._trace: deque[dict[str, Any]] = deque(maxlen=MAX_TRACE)
        self._reject_counts = {reason: 0 for reason in REASONS - {"accepted"}}
        self._accepted_since_generation = 0
        self._last_received: dict[str, Any] | None = None
        self._publishers: list[dict[str, str]] | None = None
        self._identity: tuple[str, ...] | None = None
        self._publisher_count: int | None = None
        self._graph_observed_at: float | None = None

    def observe_publishers(self, publishers: list[dict[str, str]] | None, count: int, observed_at: float) -> bool:
        self._publisher_count = count
        self._graph_observed_at = observed_at
        self._publishers = publishers
        if publishers is None:
            return False
        # Empty GIDs cannot establish a publisher generation. Names alone do
        # not distinguish two invocations of the same FAST-LIO executable.
        if any(not item["gid"] for item in publishers) or count > len(publishers):
            return False
        identity = tuple(sorted(item["gid"] for item in publishers))
        changed = self._identity is not None and self._identity != identity
        if self._identity is None or changed:
            self.source_generation = min(MAX_COUNTER, self.source_generation + 1)
            self._identity = identity
        if changed:
            self.publisher_change_count = min(MAX_COUNTER, self.publisher_change_count + 1)
            self._accepted.clear()
            self._accepted_since_generation = 0
        return changed

    def observe(self, message: Any, *, reason: str, wall_ns: int, monotonic_s: float, publisher_count: int) -> None:
        if reason not in REASONS:
            raise ValueError("unknown localization input reason")
        header = getattr(message, "header", None)
        stamp = getattr(header, "stamp", None)
        sec, nanosec = getattr(stamp, "sec", None), getattr(stamp, "nanosec", None)
        stamp_ns = None
        if isinstance(sec, int) and not isinstance(sec, bool) and isinstance(nanosec, int) and not isinstance(nanosec, bool) and sec >= 0 and 0 <= nanosec < 1_000_000_000:
            stamp_ns = sec * 1_000_000_000 + nanosec
            if stamp_ns > 2**63 - 1:
                stamp_ns = None
        receipt = {
            "source_stamp_ns": stamp_ns,
            "wall_ns": wall_ns,
            "monotonic_s": monotonic_s,
            "frame": re.sub(r"[^A-Za-z0-9_/:.\-]", "_", str(getattr(header, "frame_id", "")))[:128],
            "child_frame": re.sub(r"[^A-Za-z0-9_/:.\-]", "_", str(getattr(message, "child_frame_id", "")))[:128],
            "publisher_count": publisher_count,
            "source_generation": self.source_generation,
        }
        self.callback_count = min(MAX_COUNTER, self.callback_count + 1)
        self._last_received = receipt
        self._trace.append({**receipt, "reason": reason})
        if reason == "accepted":
            self.accepted_count = min(MAX_COUNTER, self.accepted_count + 1)
            self._accepted_since_generation = min(MAX_COUNTER, self._accepted_since_generation + 1)
            self._accepted.append(receipt)
        else:
            self.rejected_count = min(MAX_COUNTER, self.rejected_count + 1)
            self._reject_counts[reason] = min(MAX_COUNTER, self._reject_counts[reason] + 1)

    def snapshot(self, observed_at: float) -> dict[str, Any]:
        null_reason = None
        if not self._accepted:
            null_reason = "rewarming_after_source_change" if self.publisher_change_count else ("no_callbacks" if not self.callback_count else "all_received_rejected")
        frequency = None
        if len(self._accepted) >= 2:
            duration = self._accepted[-1]["monotonic_s"] - self._accepted[0]["monotonic_s"]
            frequency = (len(self._accepted) - 1) / duration if duration > 0 else None
        return copy.deepcopy({
            "topic": self.topic, "message_type": self.message_type,
            "qos": {"reliability": "BEST_EFFORT", "durability": "VOLATILE", "history": "KEEP_LAST", "depth": 5},
            "callback_count": self.callback_count, "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count, "reject_counts": self._reject_counts,
            "accepted_since_generation": self._accepted_since_generation,
            "source_generation": self.source_generation, "publisher_change_count": self.publisher_change_count,
            "publisher_count": self._publisher_count, "publishers": self._publishers,
            "graph_observed_monotonic_s": self._graph_observed_at,
            "last_received": self._last_received,
            "last_accepted": self._accepted[-1] if self._accepted else None,
            "accepted_age_s": max(0.0, observed_at - self._accepted[-1]["monotonic_s"]) if self._accepted else None,
            "accepted_frequency_hz": frequency,
            "age_null_reason": null_reason,
            "rate_null_reason": null_reason or ("insufficient_accepted_samples" if frequency is None else None),
            "trace": list(self._trace),
        })
