"""D3 assessment -> checked command -> memory-only sink. No collision math.

This is a proposed final-consumer port, not a product bridge or lease authority.
All times for enforcement are receiver-local monotonic ns with an explicit ID.
"""
from collections import deque
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Binding:
    goal_id: str
    generation: int
    lease_id: str
    source_epoch: str
    frame_key: str
    clock_id: str


@dataclass(frozen=True)
class RawCommand:
    sequence: int
    binding: Binding
    issued_ns: int
    expires_ns: int
    velocity: tuple


@dataclass(frozen=True)
class Constraint:
    sequence: int
    command_sequence: int
    binding: Binding
    valid_from_ns: int
    valid_until_ns: int
    severity: str
    speed_scale: float = 1.
    # Source stamp and D3's full assessment remain distinct from local TTL.
    source_stamp_ns: str = "0"
    assessment_ref: str = "fixture"


def constraint_from_d3(assessment, *, validate_assessment, binding, command_sequence):
    """Project an injected D3 assessment; do not calculate or upgrade severity.

    Proposed extension fields are explicit fixture ports until D3 publishes its
    exact API. C1 validates the complete assessment first. D3 must bind command,
    local clock/validity and owner generation; absent fields fail closed.
    """
    validate_assessment(assessment)
    fresh, interval, ref = assessment["freshness"], assessment["validity_interval"], assessment["path_ref"]
    if (assessment.get("source_epoch") != binding.source_epoch
            or fresh.get("c4_binding") != binding.__dict__ or ref != {"command_sequence": command_sequence}
            or interval.get("clock_id") != binding.clock_id):
        raise ValueError("D3_COMMAND_CONTEXT_MISMATCH")
    return Constraint(sequence=assessment["sequence"], command_sequence=command_sequence,
        binding=binding, valid_from_ns=interval["valid_from_ns"], valid_until_ns=interval["valid_until_ns"],
        severity=assessment["severity"], speed_scale=fresh.get("speed_scale", 1.),
        source_stamp_ns=assessment["stamp_ns"], assessment_ref=f"{assessment['source_epoch']}/{assessment['sequence']}")


@dataclass(frozen=True)
class CheckedCommand:
    sequence: int
    velocity: tuple
    hold: bool
    reason: str
    assessment_ref: str | None


class MockCommandSink:
    def __init__(self):
        self.history = deque(maxlen=32)
        self.current = CheckedCommand(-1, (0., 0., 0.), True, "INITIAL_HOLD", None)

    def write(self, command):
        if not isinstance(command, CheckedCommand):
            raise TypeError("CHECKED_COMMAND_REQUIRED")
        self.current = command
        self.history.append(command)


class CommandGate:
    """Independent of UI lifetime; fail closed; no retry/recovery timer.

    STOP_REQUIRED latches. A newer CLEAR assessment alone cannot release it.
    Only an explicit owner resume acknowledging that exact stop revision can;
    global STOP/estop/canceled lease remain independently higher priority.
    Serialize all methods in the trusted final consumer's control loop.
    """
    def __init__(self, sink, binding, *, maximum_ttl_ns=500_000_000):
        if not isinstance(sink, MockCommandSink):
            raise TypeError("THIS_CANDIDATE_REQUIRES_MOCK_SINK")
        if type(maximum_ttl_ns) is not int or not 0 < maximum_ttl_ns <= 500_000_000:
            raise ValueError("COMMAND_TTL_BOUND_REQUIRED")
        self.sink, self.binding, self.maximum_ttl_ns = sink, binding, maximum_ttl_ns
        self.command_seq = self.assessment_seq = -1
        self.stop_revision = 0
        self.collision_stop = self.global_stop = self.estop = False
        self.lease_active = True
        self.deadline_ns = None
        self.rejected = 0

    def _zero(self, reason, sequence=-1, assessment=None):
        checked = CheckedCommand(sequence, (0., 0., 0.), True, reason, assessment)
        self.sink.write(checked)
        self.deadline_ns = None
        return checked

    def set_authority(self, *, global_stop=False, estop=False, lease_active=True):
        # False values cannot release an existing external STOP/estop. Only the
        # existing authority can create a new generation after clearing it.
        self.global_stop |= global_stop
        self.estop |= estop
        self.lease_active &= lease_active
        if self.estop or self.global_stop or not self.lease_active:
            self.stop_revision += 1
            self._zero("ESTOP" if self.estop else "GLOBAL_STOP" if self.global_stop else "LEASE_CANCELED")

    def _valid_constraint(self, constraint, now_ns, command_sequence=None):
        return (type(now_ns) is int and now_ns >= 0 and isinstance(constraint, Constraint) and constraint.binding == self.binding
            and type(constraint.sequence) is int and constraint.sequence > self.assessment_seq
            and (command_sequence is None or constraint.command_sequence == command_sequence)
            and type(constraint.valid_from_ns) is int and type(constraint.valid_until_ns) is int
            and constraint.valid_from_ns <= now_ns < constraint.valid_until_ns
            and 0 < constraint.valid_until_ns - constraint.valid_from_ns <= self.maximum_ttl_ns
            and constraint.severity in {"CLEAR", "CAUTION", "STOP_REQUIRED", "UNKNOWN"}
            and isinstance(constraint.source_stamp_ns, str) and constraint.source_stamp_ns.isdecimal())

    def apply(self, raw, constraint, *, now_ns):
        if self.estop or self.global_stop or not self.lease_active:
            return self._zero("ESTOP" if self.estop else "GLOBAL_STOP" if self.global_stop else "LEASE_CANCELED")
        valid_raw = (isinstance(raw, RawCommand) and raw.binding == self.binding
            and type(raw.sequence) is int and raw.sequence > self.command_seq
            and type(raw.issued_ns) is int and type(raw.expires_ns) is int
            and raw.issued_ns <= now_ns < raw.expires_ns
            and 0 < raw.expires_ns - raw.issued_ns <= self.maximum_ttl_ns
            and len(raw.velocity) == 3 and all(type(v) in (float, int) and math.isfinite(v) for v in raw.velocity))
        if not valid_raw or not self._valid_constraint(constraint, now_ns, raw.sequence):
            self.rejected += 1
            return self._zero("REJECTED_BINDING_ORDER_OR_TTL")
        self.command_seq, self.assessment_seq = raw.sequence, constraint.sequence
        if constraint.severity in {"STOP_REQUIRED", "UNKNOWN"}:
            self.collision_stop = True
            self.stop_revision += 1
            return self._zero(constraint.severity, raw.sequence, constraint.assessment_ref)
        if self.collision_stop:
            return self._zero("COLLISION_STOP_LATCHED", raw.sequence, constraint.assessment_ref)
        scale = constraint.speed_scale if constraint.severity == "CAUTION" else 1.
        if type(scale) not in (int, float) or not math.isfinite(scale) or not 0 <= scale <= 1:
            self.rejected += 1
            return self._zero("INVALID_SPEED_SCALE")
        checked = CheckedCommand(raw.sequence, tuple(v*scale for v in raw.velocity), False,
                                 constraint.severity, constraint.assessment_ref)
        self.deadline_ns = min(raw.expires_ns, constraint.valid_until_ns)
        self.sink.write(checked)
        return checked

    def resume(self, clearance, *, acknowledged_stop_revision, now_ns):
        if (self.global_stop or self.estop or not self.lease_active or not self.collision_stop
                or acknowledged_stop_revision != self.stop_revision
                or not self._valid_constraint(clearance, now_ns)
                or clearance.command_sequence != self.command_seq or clearance.severity != "CLEAR"):
            self.rejected += 1
            self._zero("RELEASE_REJECTED")
            return False
        self.assessment_seq = clearance.sequence
        self.collision_stop = False
        # Release never replays a previous nonzero command.
        self._zero("RESUMED_WAITING_FOR_NEW_COMMAND")
        return True

    def tick(self, *, now_ns):
        """Trusted consumer watchdog, not a browser callback."""
        if self.deadline_ns is not None and now_ns >= self.deadline_ns:
            self._zero("COMMAND_OR_ASSESSMENT_EXPIRED")
        return self.sink.current
