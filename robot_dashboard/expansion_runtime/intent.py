"""Final-arbitration intent demonstration, restricted to the old memory sink.

ACTIVE never falls back to advisory. An advisory result never grants movement.
The existing product arbiter remains responsible for STOP/lease/estop/watchdog.
"""
from .binding import RuntimeContext
from .composition import Intent
from robot_dashboard.obstacle_runtime_adapter.command import (
    Binding, CommandGate, Constraint, MockCommandSink, RawCommand,
)


class FinalIntentPort:
    def __init__(self, context: RuntimeContext, *, mode="ADVISORY_ONLY"):
        if mode not in {"ADVISORY_ONLY", "ACTIVE_CONSTRAINT"}:
            raise ValueError("EXPLICIT_MODE_REQUIRED")
        self.context, self._mode = context, mode
        self.binding = Binding(context.controller_goal_id, context.authority_generation,
            context.lease_id, context.source_epoch, context.key, context.host_clock_id)
        self.sink = MockCommandSink()
        self.gate = CommandGate(self.sink, self.binding)

    @property
    def mode(self):
        return self._mode

    def apply(self, intent: Intent, *, now_ns, issued_ns, expires_ns):
        if self.mode == "ADVISORY_ONLY":
            return dict(action="DIAGNOSTIC_ONLY", urdf_constraint_enforced=False,
                        severity=intent.severity, reason=intent.reason)
        valid = (intent.mode == self.mode and intent.context_key == self.context.key
                 and intent.severity in {"CLEAR", "STOP_REQUIRED", "UNKNOWN"})
        constraint = Constraint(intent.sequence, intent.command_sequence, self.binding,
            intent.valid_from_ns if intent.valid_from_ns is not None else now_ns,
            intent.valid_until_ns if intent.valid_until_ns is not None else now_ns,
            intent.severity, source_stamp_ns=intent.stamp_ns, assessment_ref="c4/" + str(intent.sequence)) if valid else None
        raw = RawCommand(intent.command_sequence, self.binding, issued_ns, expires_ns, intent.velocity)
        return self.gate.apply(raw, constraint, now_ns=now_ns)

    def tick(self, *, now_ns):
        return self.gate.tick(now_ns=now_ns)
