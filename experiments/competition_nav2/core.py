"""Offline geometry and simulated final command boundary; no ROS imports or planner."""

from dataclasses import dataclass
import math

FOOTPRINT = ((-0.358, -0.162), (0.358, -0.162), (0.358, 0.162), (-0.358, 0.162))
RADIUS = max(math.hypot(*p) for p in FOOTPRINT)
LIMITS = dict(v=0.18, w=0.6, a=0.3, alpha=1.2, command_ttl=0.25, sensor_ttl=0.3)


def polygon(pose, body=FOOTPRINT):
    x, y, yaw = pose
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x + c * u - s * v, y + s * u + c * v) for u, v in body]


def rectangle(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def intersects(a, b):
    """Convex SAT, touching is contact."""
    for poly in (a, b):
        for p, q in zip(poly, poly[1:] + poly[:1]):
            axis = (p[1] - q[1], q[0] - p[0])
            aa = [x * axis[0] + y * axis[1] for x, y in a]
            bb = [x * axis[0] + y * axis[1] for x, y in b]
            if max(aa) < min(bb) - 1e-10 or max(bb) < min(aa) - 1e-10:
                return False
    return True


def point_segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    norm = dx * dx + dy * dy
    u = (
        0.0
        if norm == 0
        else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / norm))
    )
    return math.hypot(p[0] - a[0] - u * dx, p[1] - a[1] - u * dy)


def clearance(a, b):
    if intersects(a, b):
        return 0.0
    return min(
        point_segment_distance(p, u, v)
        for one, two in ((a, b), (b, a))
        for p in one
        for u, v in zip(two, two[1:] + two[:1])
    )


def propagate(pose, v, w, dt):
    x, y, yaw = pose
    if abs(w) < 1e-9:
        return x + v * math.cos(yaw) * dt, y + v * math.sin(yaw) * dt, yaw
    return (
        x + v / w * (math.sin(yaw + w * dt) - math.sin(yaw)),
        y - v / w * (math.cos(yaw + w * dt) - math.cos(yaw)),
        yaw + w * dt,
    )


def swept_poses(pose, v, w, dt, radius=RADIUS):
    """<=5 mm footprint-corner displacement and <=0.01 rad per sample."""
    n = max(
        1,
        math.ceil((abs(v) + radius * abs(w)) * dt / 0.005),
        math.ceil(abs(w) * dt / 0.01),
    )
    return [propagate(pose, v, w, dt * i / n) for i in range(n + 1)]


@dataclass(frozen=True)
class Command:
    sequence: int
    epoch: int
    sent: float  # receiver-host monotonic time in this same-host simulation only
    received: float
    v: float
    w: float


class Boundary:
    """Final simulated actuator gate. HOLD/fault clears cached commands immediately.

    Receipt TTL and source age are independent. RELEASE changes epoch and requires
    a fresh command; terminal faults cannot be auto-released. Zero bypasses slew.
    This is an experimental gate, not a second production arbiter.
    """

    def __init__(self, sensor_ttl=LIMITS["sensor_ttl"]):
        if not 0 < sensor_ttl <= LIMITS["sensor_ttl"]:
            raise ValueError("sensor TTL may only become stricter")
        self.sensor_ttl = sensor_ttl
        self.epoch = 0
        self.hold = True
        self.fault = None
        self.command = None
        self.last_sequence = -1
        self.scan_received = None
        self.scan_source = None
        self.output = (0.0, 0.0)
        self.last_now = None
        self.release_at = math.inf
        self.reason = "HOLD"

    def set_hold(self, hold, now):
        if not math.isfinite(now):
            self.stop("INVALID_TIME")
            return
        if hold != self.hold:
            self.epoch += 1
            self.command = None
            self.output = (0.0, 0.0)
            self.hold = hold
            self.release_at = now if not hold else math.inf

    def stop(self, reason):
        self.fault = reason
        self.command = None
        self.output = (0.0, 0.0)
        self.reason = reason

    def sensor(self, received, source_age):
        if (
            not all(math.isfinite(x) for x in (received, source_age))
            or not 0 <= source_age <= self.sensor_ttl
        ):
            self.stop("SENSOR_SOURCE_STALE_OR_INVALID")
            return False
        if self.scan_received is not None and received < self.scan_received:
            self.stop("SENSOR_TIME_RESET")
            return False
        self.scan_received, self.scan_source = received, source_age
        return True

    def accept(self, command, now):
        vals = (command.sent, command.received, command.v, command.w, now)
        if not all(math.isfinite(x) for x in vals):
            self.stop("NONFINITE_COMMAND")
            return False
        valid = (
            not self.hold
            and not self.fault
            and command.epoch == self.epoch
            and command.sequence > self.last_sequence
            and self.release_at <= command.sent <= command.received <= now
            and now - command.sent <= LIMITS["command_ttl"]
            and now - command.received <= LIMITS["command_ttl"]
        )
        if not valid:
            return False
        self.command = command
        self.last_sequence = command.sequence
        return True

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
            self.output = (0.0, 0.0)
        else:
            v = max(0.0, min(LIMITS["v"], cmd.v))
            w = max(-LIMITS["w"], min(LIMITS["w"], cmd.w))
            # Emergency zero is immediate. Normal nonzero commands share slew limits.
            if v == 0 and w == 0:
                self.output = (0.0, 0.0)
            else:
                a, b = self.output
                self.output = (
                    max(a - LIMITS["a"] * dt, min(a + LIMITS["a"] * dt, v)),
                    max(b - LIMITS["alpha"] * dt, min(b + LIMITS["alpha"] * dt, w)),
                )
            reason = "RELEASE"
        self.reason = reason
        return self.output
