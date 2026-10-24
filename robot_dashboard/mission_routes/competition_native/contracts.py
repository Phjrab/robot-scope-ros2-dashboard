"""Internal injection contracts, not public ROS/API messages or qualification."""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Protocol

from ..competition_contract import REQUIREMENTS
from ..models import CompetitionAction


@dataclass(frozen=True)
class Scope:
    owner_id: str
    mission_run_id: str
    step_id: str
    config_hash: str
    goal_id: str
    goal_generation: int

    def __post_init__(self):
        if (not isinstance(self.owner_id, str) or not 1 <= len(self.owner_id) <= 64
                or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value)
                       for value in (self.mission_run_id, self.step_id, self.goal_id))
                or not isinstance(self.config_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", self.config_hash)
                or type(self.goal_generation) is not int or self.goal_generation < 1):
            raise ValueError("INVALID_NATIVE_SCOPE")

    def matches(self, evidence):
        return all(getattr(evidence, key) == value for key, value in vars(self).items())


@dataclass(frozen=True)
class TimingPolicy:
    # Native cadence must be provided from measurements; no fixture fallback.
    receiver_ttl_s: float | None = None
    source_max_age_s: float | None = None
    continuity_gap_s: float | None = None
    command_ttl_s: float = 0.25

    def validate(self):
        for value in vars(self).values():
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("MEASURED_TIMING_POLICY_REQUIRED")
        if self.command_ttl_s > 0.25:
            raise ValueError("COMMAND_TTL_EXCEEDS_BOUND")

    @classmethod
    def synthetic(cls):
        return cls(0.5, 0.5, 0.5, 0.25)


@dataclass(frozen=True)
class Activation:
    enabled: bool = False
    synthetic: bool = False
    binding_reference: str = ""
    validation_reference: str = ""
    capabilities: frozenset[str] = frozenset()

    def __post_init__(self):
        if (type(self.enabled) is not bool or type(self.synthetic) is not bool
                or not isinstance(self.capabilities, frozenset)
                or not isinstance(self.binding_reference, str)
                or not isinstance(self.validation_reference, str)):
            raise ValueError("INVALID_ACTIVATION_FACTS")

    def report(self, action: CompetitionAction):
        required = set(REQUIREMENTS[action.type])
        required.update(("navigation_adapter", "command_arbiter"))
        missing = sorted(required - self.capabilities)
        return {"action": action.type, "missing": missing,
                "enabled": self.enabled and bool(self.binding_reference)
                and bool(self.validation_reference) and not missing,
                "evidence_class": "SYNTHETIC_ONLY" if self.synthetic else "LIVE_BINDING_REQUIRED"}


@dataclass(frozen=True)
class GoalReceipt:
    scope: Scope
    actual_goal_id: str
    accepted: bool = True


@dataclass(frozen=True)
class ConstraintRequest:
    scope: Scope
    request_id: str
    mode: str
    reason: str
    # HOLD is latched; a missing/expired release must never restore tracking.
    command_ttl_s: float = 0.25
    sequence: int = 0


@dataclass(frozen=True)
class ConstraintAck:
    scope: Scope
    request_id: str
    mode: str
    accepted: bool

    def matches(self, request):
        return (self.accepted is True and self.scope == request.scope
                and self.request_id == request.request_id and self.mode == request.mode)


class NavigationPort(Protocol):
    async def dispatch(self, scope: Scope, *, leg: str, pose: dict,
                       request_id: str) -> GoalReceipt: ...
    async def cancel(self, scope: Scope, *, request_id: str) -> None: ...


class ConstraintPort(Protocol):
    async def apply(self, request: ConstraintRequest) -> ConstraintAck | None: ...
    def ack(self, request: ConstraintRequest) -> ConstraintAck | None: ...


class PosturePort(Protocol):
    async def cancel(self, scope: Scope, *, request_id: str) -> None: ...
    async def request(self, scope: Scope, *, posture: str, request_id: str) -> None: ...


class TerrainPort(Protocol):
    async def cancel(self, scope: Scope, *, request_id: str) -> None: ...
    async def begin(self, scope: Scope, *, segment: str, profile: str,
                    request_id: str) -> None: ...


class ObservationPort(Protocol):
    def sample(self, scope: Scope) -> Any: ...
