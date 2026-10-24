"""Pure command contract reference for tests/integration at ONE final authority.

Not a controller, lease, ROS publisher, or replacement for ControlManager.
A live ConstraintPort must apply equivalent gates at the existing final command
consumer. Returning a tuple here does not stop any real robot.
"""
from dataclasses import dataclass
import math


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class Command:
    scope: object
    sequence: int
    receipt_s: float
    velocity: tuple[float, float, float]


class CommandBoundary:
    def __init__(self, scope, *, owners=("mission",), command_ttl_s=0.25):
        if not owners or len(set(owners)) != len(owners) or not all(isinstance(x, str) and x for x in owners):
            raise ValueError("EXPECTED_OWNERS_REQUIRED")
        if not finite(command_ttl_s) or not 0 < command_ttl_s <= 0.25:
            raise ValueError("INVALID_COMMAND_TTL")
        self.scope, self.owners, self.ttl = scope, frozenset(owners), command_ttl_s
        self.modes = {}  # Missing owner fails closed; HOLD never expires open.
        self.requests = {}
        self.owner_sequences = {}
        self.last_sequence = -1
        self.release_barrier = -1
        self.release_time = float("inf")
        self.last_now = None
        self.retired = False

    def apply_constraint(self, owner, request, now):
        if (self.retired or owner not in self.owners or request.scope != self.scope
                or request.mode not in {"HOLD", "RELEASE"} or not finite(now)
                or (self.last_now is not None and now < self.last_now)):
            self.modes.clear()
            return False
        self.last_now = now
        if request.request_id in self.requests:
            if self.requests[request.request_id] != (owner, request):
                self.modes.clear()
                return False
            return True  # duplicate does not refresh a release timestamp
        if (type(request.sequence) is not int
                or request.sequence <= self.owner_sequences.get(owner, -1)):
            self.modes[owner] = "HOLD"
            return False
        self.owner_sequences[owner] = request.sequence
        self.requests[request.request_id] = (owner, request)
        self.modes[owner] = request.mode
        self.release_barrier = self.last_sequence
        if request.mode == "RELEASE":
            self.release_time = now
        return True

    def retire(self):
        self.retired = True
        self.modes.clear()

    def evaluate(self, command, *, now, goal_scope=None, goal_receipt_s=None,
                 inputs_fresh=False, estop=False, collision=False, terrain_caps=None):
        zero = (0.0, 0.0, 0.0)
        if not all(type(v) is bool for v in (inputs_fresh, estop, collision)):
            return zero, "INVALID_SAFETY"
        # Consume even inhibited commands: they cannot be replayed after RELEASE.
        seq = command.sequence
        new = type(seq) is int and seq >= 0 and seq > self.last_sequence
        if type(seq) is int and seq >= 0:
            self.last_sequence = max(self.last_sequence, seq)
        if estop or collision:
            return zero, "ESTOP" if estop else "COLLISION"
        if (not finite(now) or (self.last_now is not None and now < self.last_now)):
            self.retire()
            return zero, "RECEIVER_CLOCK_ROLLBACK"
        self.last_now = now
        if self.retired or any(self.modes.get(owner) != "RELEASE" for owner in self.owners):
            return zero, "HOLD"
        if (not new or seq <= self.release_barrier or command.scope != self.scope
                or not finite(command.receipt_s) or not 0 <= now - command.receipt_s <= self.ttl
                or command.receipt_s < self.release_time or not inputs_fresh
                or goal_scope != self.scope or not finite(goal_receipt_s)
                or not 0 <= now - goal_receipt_s <= self.ttl):
            return zero, "FRESH_GOAL_AND_COMMAND_REQUIRED"
        if len(command.velocity) != 3 or not all(finite(v) for v in command.velocity):
            return zero, "INVALID_COMMAND"
        if terrain_caps is not None:
            if len(terrain_caps) != 3 or not all(finite(v) and v >= 0 for v in terrain_caps):
                return zero, "INVALID_TERRAIN_CAP"
            return tuple(max(-cap, min(v, cap)) for v, cap in zip(command.velocity, terrain_caps)), "TERRAIN_CAP"
        return command.velocity, "TRACKING"


@dataclass(frozen=True)
class ConsumerReceipt:
    """Issued ONLY after the existing final consumer installs this exact request."""
    consumer_id: str
    request: object
    installed: bool


class FinalConsumerConstraintPort:
    """ACK plumbing, not a command consumer and not proof of live qualification.

    install(request) is C1's async callback at the EXISTING final consumer. It
    must atomically fence sequence/generation there, including after awaited IO.
    Enqueueing a message returns None; a later consumer receipt is acknowledged
    with acknowledge(). ack() is read-only and never refreshes any timestamp.
    """
    def __init__(self, *, consumer_id, install):
        if not isinstance(consumer_id, str) or not consumer_id or not callable(install):
            raise ValueError("FINAL_CONSUMER_CALLBACK_REQUIRED")
        self.consumer_id, self.install = consumer_id, install
        self.current = None
        self.receipt = None
        self.requests = {}

    async def apply(self, request):
        from .contracts import ConstraintRequest
        if (not isinstance(request, ConstraintRequest) or request.mode not in {"HOLD", "RELEASE"}
                or type(request.sequence) is not int or request.sequence < 1
                or not request.request_id or not finite(request.command_ttl_s)
                or not 0 < request.command_ttl_s <= .25):
            raise ValueError("INVALID_CONSUMER_REQUEST")
        if request.request_id in self.requests:
            if self.requests[request.request_id] != request:
                raise ValueError("CONSUMER_REQUEST_REUSED")
            return self.ack(request)
        if self.current is not None:
            old, new = self.current.scope, request.scope
            if (request.sequence <= self.current.sequence
                    or any(getattr(old, k) != getattr(new, k)
                           for k in ("owner_id", "mission_run_id", "step_id", "config_hash"))
                    or new.goal_generation < old.goal_generation
                    or (new.goal_generation == old.goal_generation and new != old)
                    or (new.goal_generation > old.goal_generation and request.mode != "HOLD")):
                raise ValueError("CONSUMER_REQUEST_RETIRED_OR_FOREIGN")
        if len(self.requests) >= 128:
            raise ValueError("CONSUMER_REQUEST_LEDGER_FULL")
        self.requests[request.request_id] = request
        self.current, self.receipt = request, None
        receipt = await self.install(request)
        if receipt is not None:
            self.acknowledge(receipt)
        return self.ack(request)

    def acknowledge(self, receipt):
        if (not isinstance(receipt, ConsumerReceipt) or receipt.installed is not True
                or receipt.consumer_id != self.consumer_id or receipt.request != self.current):
            raise ValueError("FINAL_CONSUMER_ACK_MISMATCH")
        self.receipt = receipt

    def ack(self, request):
        from .contracts import ConstraintAck
        if self.receipt is not None and self.current == request:
            return ConstraintAck(request.scope, request.request_id, request.mode, True)
        return None
