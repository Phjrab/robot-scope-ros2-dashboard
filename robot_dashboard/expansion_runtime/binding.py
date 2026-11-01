"""Trusted runtime identity and explicit, bounded unit-rate clock conversion."""
from dataclasses import asdict, dataclass
import hashlib
import json

D3_PROFILE = "d3-09b68b692fa4b7ccdea39b1a16e3ff150794e12d/0.1"
C1_PROFILE = "c1-54629c793ad4ae0ea88127f00ed1b7f8805fc4e2/0.1"
JS_MAX = 2**53 - 1


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def integer(value):
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise ValueError("INTEGER_NANOSECONDS_REQUIRED")
    return value


def decimal(value):
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value) > 25:
        raise ValueError("DECIMAL_SOURCE_TIME_REQUIRED")
    if str(int(value)) != value:
        raise ValueError("CANONICAL_SOURCE_TIME_REQUIRED")
    return int(value)


def browser_safe(value):
    """C1 0.1 uses JSON host integers. Reject loss rather than silently stringify."""
    if type(value) is int and abs(value) > JS_MAX:
        raise ValueError("C1_V01_UNSAFE_JS_INTEGER")
    if isinstance(value, dict):
        for child in value.values():
            browser_safe(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            browser_safe(child)
    return value


@dataclass(frozen=True)
class RuntimeContext:
    runtime_generation: int
    map_id: str
    map_revision: str
    map_generation: int
    family_id: str
    family_revision: str
    footprint_revision: str
    robot_geometry_hash: str
    controller_goal_id: str
    authority_generation: int
    lease_id: str
    command_scope: str
    source_epoch: str
    frame_id: str
    tf_epoch: str
    clock_epoch: str
    host_clock_id: str

    def __post_init__(self):
        for name, value in asdict(self).items():
            if name in {"runtime_generation", "map_generation", "authority_generation"}:
                integer(value)
            elif not isinstance(value, str) or not value or len(value) > 128:
                raise ValueError("TRUSTED_CONTEXT_REQUIRED: " + name)

    @property
    def map_binding(self):
        return dict(map_id=self.map_id, revision=self.map_revision, generation=self.map_generation)

    @property
    def key(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class ClockMapping:
    source_domain: str
    source_epoch: str
    clock_epoch: str
    host_clock_id: str
    offset_ns: int
    uncertainty_ns: int
    source_start_ns: int
    source_end_ns: int
    evidence_id: str

    def __post_init__(self):
        if not all(isinstance(v, str) and v and v.lower() != "unknown" for v in (
            self.source_domain, self.source_epoch, self.clock_epoch, self.host_clock_id, self.evidence_id
        )):
            raise ValueError("CLOCK_MAPPING_EVIDENCE_REQUIRED")
        if type(self.offset_ns) is not int:
            raise ValueError("INTEGER_CLOCK_OFFSET_REQUIRED")
        integer(self.uncertainty_ns)
        if not (type(self.source_start_ns) is int and type(self.source_end_ns) is int
                and 0 <= self.source_start_ns < self.source_end_ns):
            raise ValueError("CLOCK_MAPPING_WINDOW_REQUIRED")

    def check(self, context, domain):
        if (domain != self.source_domain or context.source_epoch != self.source_epoch
                or context.clock_epoch != self.clock_epoch or context.host_clock_id != self.host_clock_id):
            raise ValueError("CLOCK_MAPPING_CONTEXT_MISMATCH")

    def host(self, source_ns):
        if not self.source_start_ns <= source_ns <= self.source_end_ns:
            raise ValueError("OUTSIDE_CLOCK_MAPPING_WINDOW")
        return integer(source_ns + self.offset_ns)

    def interval(self, value, *, profile, context):
        if profile == D3_PROFILE:
            if set(value) != {"clock_domain", "from_ns", "until_ns"}:
                raise ValueError("UNSUPPORTED_D3_VALIDITY")
            self.check(context, value["clock_domain"])
            start = self.host(decimal(value["from_ns"])) + self.uncertainty_ns
            end = self.host(decimal(value["until_ns"])) - self.uncertainty_ns
        elif profile == C1_PROFILE:
            if set(value) != {"host_clock_id", "start_monotonic_ns", "end_monotonic_ns"}:
                raise ValueError("UNSUPPORTED_C1_VALIDITY")
            if value["host_clock_id"] != context.host_clock_id:
                raise ValueError("UNMAPPED_HOST_CLOCK")
            start, end = value["start_monotonic_ns"], value["end_monotonic_ns"]
        else:
            raise ValueError("UNSUPPORTED_VALIDITY_PROFILE")
        integer(start)
        integer(end)
        if end <= start:
            raise ValueError("EMPTY_CONSERVATIVE_VALIDITY")
        return dict(host_clock_id=context.host_clock_id, start_monotonic_ns=start, end_monotonic_ns=end)
