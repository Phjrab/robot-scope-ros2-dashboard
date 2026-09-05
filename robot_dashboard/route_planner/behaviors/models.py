"""Strict public model for advisory decisions."""

from __future__ import annotations

import copy
import math
import re
from typing import Any, Mapping

from ..perception import MAX_UINT64


ADVISORIES = frozenset(
    {
        "WAIT",
        "ALIGN",
        "PROCEED_RECOMMENDED",
        "HOLD",
        "REPLAN_RECOMMENDED",
        "SEARCH_MARKER",
        "DOCKING_READY",
        "PICKUP_CONFIRMATION_REQUIRED",
        "DROPOFF_CONFIRMATION_REQUIRED",
        "COMPLETE",
        "FAULT",
    }
)
BEHAVIORS = frozenset(
    {"CROSSWALK", "DOCKING", "UNDERPASS", "DELIVERY", "NORMAL_GUIDANCE", "FAULT"}
)
_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_FORBIDDEN_OUTPUT_FIELDS = frozenset(
    {"linear_x", "linear_y", "angular_z", "cmd_vel", "sport_request", "navigation_goal"}
)


class BehaviorContractError(ValueError):
    """Raised when an advisory input or output is outside its fixed contract."""


def uint64(value: object, field: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= MAX_UINT64
    ):
        raise BehaviorContractError(f"{field} must be uint64-compatible")
    return value


def finite(value: object, field: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BehaviorContractError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise BehaviorContractError(f"{field} is outside the supported range")
    return number


def token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise BehaviorContractError(f"{field} is invalid")
    return value


def make_advisory_snapshot(
    *,
    behavior: str,
    state: str,
    advisory: str,
    ready_for_manual_proceed: bool,
    autonomous_edge_ready: bool,
    reason_codes: list[str] | tuple[str, ...],
    requirements: Mapping[str, bool | int | str | None],
    updated_at_ns: int,
) -> dict[str, Any]:
    """Return one exact JSON-safe advisory snapshot."""

    if behavior not in BEHAVIORS:
        raise BehaviorContractError("behavior is invalid")
    state_value = token(state, "behavior state")
    if advisory not in ADVISORIES:
        raise BehaviorContractError("advisory is invalid")
    if not isinstance(ready_for_manual_proceed, bool) or not isinstance(
        autonomous_edge_ready, bool
    ):
        raise BehaviorContractError("readiness flags must be boolean")
    if not isinstance(reason_codes, (list, tuple)) or len(reason_codes) > 16:
        raise BehaviorContractError("reason code list is invalid")
    reasons = list(dict.fromkeys(token(item, "reason code") for item in reason_codes))
    if not isinstance(requirements, Mapping) or len(requirements) > 16:
        raise BehaviorContractError("behavior requirements are invalid")
    normalized_requirements: dict[str, bool | int | str | None] = {}
    for key, value in requirements.items():
        if not isinstance(key, str) or not re.fullmatch(r"^[a-z][a-z0-9_]{0,63}$", key):
            raise BehaviorContractError("behavior requirement name is invalid")
        if not isinstance(value, (bool, int, str)) and value is not None:
            raise BehaviorContractError("behavior requirement value is invalid")
        normalized_requirements[key] = copy.deepcopy(value)
    result = {
        "behavior": behavior,
        "state": state_value,
        "advisory": advisory,
        "ready_for_manual_proceed": ready_for_manual_proceed,
        "autonomous_edge_ready": autonomous_edge_ready,
        "reason_codes": reasons,
        "requirements": normalized_requirements,
        "updated_at_ns": uint64(updated_at_ns, "updated_at_ns"),
    }
    if set(result) & _FORBIDDEN_OUTPUT_FIELDS:
        raise BehaviorContractError("control output fields are forbidden")
    return result


__all__ = [
    "ADVISORIES",
    "BEHAVIORS",
    "BehaviorContractError",
    "finite",
    "make_advisory_snapshot",
    "token",
    "uint64",
]
