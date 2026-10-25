"""Explicit simulated Omni revision. The existing DiffDrive core stays unchanged."""

from dataclasses import dataclass
import math

from core import Boundary, Command, LIMITS

LATERAL_LIMIT = 0.08  # Simulation experiment only, not a robot/gait qualification.
OMNI_ZERO = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class OmniCommand(Command):
    vy: float = 0.0


def propagate_omni(pose, vx, vy, wz, dt):
    """Exact constant body-twist integration, including yaw-dependent lateral motion."""
    x, y, yaw = pose
    if abs(wz) < 1e-9:
        return (
            x + dt * (vx * math.cos(yaw) - vy * math.sin(yaw)),
            y + dt * (vx * math.sin(yaw) + vy * math.cos(yaw)),
            yaw,
        )
    end = yaw + wz * dt
    return (
        x
        + (vx * (math.sin(end) - math.sin(yaw)) + vy * (math.cos(end) - math.cos(yaw)))
        / wz,
        y
        + (vx * (math.cos(yaw) - math.cos(end)) + vy * (math.sin(end) - math.sin(yaw)))
        / wz,
        end,
    )


def swept_omni(pose, vx, vy, wz, dt, radius):
    n = max(
        1,
        math.ceil((math.hypot(vx, vy) + radius * abs(wz)) * dt / 0.005),
        math.ceil(abs(wz) * dt / 0.01),
    )
    return [propagate_omni(pose, vx, vy, wz, dt * i / n) for i in range(n + 1)]


class OmniBoundary(Boundary):
    """Reuse source/receipt/epoch acceptance; explicitly gate and slew all 3 axes."""

    def __init__(self, sensor_ttl=0.25):
        super().__init__(sensor_ttl)
        self.output = OMNI_ZERO

    def set_hold(self, hold, now):
        changed = self.hold != hold
        super().set_hold(hold, now)
        if changed or self.fault:
            self.output = OMNI_ZERO

    def stop(self, reason):
        super().stop(reason)
        self.output = OMNI_ZERO

    def accept(self, command, now):
        if not isinstance(command, OmniCommand) or not math.isfinite(command.vy):
            self.stop("NONFINITE_OR_WRONG_MODEL_COMMAND")
            return False
        if (
            abs(command.vy) > LATERAL_LIMIT + 1e-9
            or math.hypot(command.v, command.vy) > LIMITS["v"] + 1e-9
            or command.v < 0
            or abs(command.w) > LIMITS["w"] + 1e-9
        ):
            self.stop("OMNI_COMMAND_LIMIT")
            return False
        return super().accept(command, now)

    def step(self, now, dt):
        if not math.isfinite(now) or not math.isfinite(dt) or not 0 < dt <= 0.1:
            self.stop("INVALID_STEP")
        elif self.last_now is not None and now < self.last_now:
            self.stop("CLOCK_RESET")
        self.last_now = now
        reason = self.fault or ("HOLD" if self.hold else "")
        if not reason and (
            self.scan_received is None
            or now < self.scan_received
            or now - self.scan_received + self.scan_source > self.sensor_ttl
        ):
            self.stop("SENSOR_STALE")
            reason = self.fault
        cmd = self.command
        if not reason and (
            cmd is None
            or now - cmd.received > LIMITS["command_ttl"]
            or now - cmd.sent > LIMITS["command_ttl"]
        ):
            reason = "COMMAND_TTL"
        if reason:
            self.command = None
            self.output = OMNI_ZERO
        elif (cmd.v, cmd.vy, cmd.w) == OMNI_ZERO:
            self.output = OMNI_ZERO  # Native exact stop bypasses slew on every axis.
            reason = "RELEASE"
        else:
            vx, vy, wz = self.output
            dx, dy = cmd.v - vx, cmd.vy - vy
            distance = math.hypot(dx, dy)
            scale = min(1.0, LIMITS["a"] * dt / distance) if distance else 1.0
            self.output = (
                vx + scale * dx,
                vy + scale * dy,
                max(wz - LIMITS["alpha"] * dt, min(wz + LIMITS["alpha"] * dt, cmd.w)),
            )
            reason = "RELEASE"
        self.reason = reason
        return self.output
