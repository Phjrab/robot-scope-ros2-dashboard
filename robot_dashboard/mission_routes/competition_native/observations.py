"""One canonical v0.1 validation boundary with per-component receipt clocks.

Clock relations/epochs are installed by trusted binding code, never accepted
from a network payload. No subtraction of clocks from different hosts occurs.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import secrets
from typing import Mapping

from ..competition_contract import Evidence
from .contracts import Scope, TimingPolicy

FIELDS = {
    "navigation": ("goal_state", "cancel_ack"),
    "pose": ("pose",),
    "path": ("path_clear", "obstacle_state", "observation_age_s", "obstacle_source",
             "planned_path_revision", "minimum_clearance_m"),
    "signal": ("signal_id", "crossing_id", "raw_state", "stable_state", "quality_flags",
               "confidence", "roi_xyxy_native", "native_image_size", "model_sha256"),
    "feet": ("zone_id", "front_left_status", "front_right_status", "feet_evidence_kind"),
    "motion": ("body_motion_status",),
    "body": ("zone_id", "full_body_inside", "full_body_crossed"),
    "posture": ("posture",),
    "terrain": ("terrain_complete",),
    "departure": (), "safety": (), "coverage": (),
}


class ObservationRejected(ValueError):
    pass


@dataclass(frozen=True)
class ClockBinding:
    producer_id: str
    epoch: str
    source_clock: str
    relation_verified: bool = False

    def __post_init__(self):
        if (not self.producer_id or not self.epoch or type(self.relation_verified) is not bool
                or self.source_clock not in {"fixture", "synchronized_ros", "synchronized_utc"}):
            raise ValueError("INVALID_CLOCK_BINDING")


@dataclass(frozen=True)
class ComponentStamp:
    scope: Scope
    producer_id: str
    epoch: str
    sequence: int
    source_stamp_ns: str
    source_age_s: float
    source_clock: str
    first_received_s: float | None = None
    receiver_clock_id: str | None = None
    validity_s: float | None = None


@dataclass(frozen=True)
class Extras:
    # These fields are internal sidecars; the canonical schema is unchanged.
    departure_observed: bool = False
    posture_verified: bool = False
    terrain_verified: bool = False
    validation_reference: str = ""
    estop: bool = False
    collision: bool = False
    attempted_steps: tuple[str, ...] = ()
    traversed_segments: tuple[str, ...] = ()


@dataclass(frozen=True)
class Packet:
    evidence: Mapping
    components: Mapping[str, ComponentStamp]
    extras: Extras = Extras()
    receiver_session_id: str = ""


@dataclass(frozen=True)
class Received:
    stamp: ComponentStamp
    receipt_s: float
    fingerprint: str


@dataclass(frozen=True)
class Frame:
    evidence: Evidence
    extras: Extras
    components: Mapping[str, Received]
    now: float
    policy: TimingPolicy

    def supported_end(self, *names):
        """Conservative acquisition bound in receiver time, never remote monotonic."""
        return min(self.components[name].receipt_s - self.components[name].stamp.source_age_s
                   for name in names)

    def acquired_after(self, boundary, *names):
        return boundary is not None and self.fresh(*names) and self.supported_end(*names) > boundary

    def fresh(self, *names):
        for name in names:
            received = self.components.get(name)
            if received is None:
                return False
            elapsed = self.now - received.receipt_s
            bound = received.stamp.validity_s
            receipt_ttl = min(self.policy.receiver_ttl_s, bound) if bound is not None else self.policy.receiver_ttl_s
            source_ttl = min(self.policy.source_max_age_s, bound) if bound is not None else self.policy.source_max_age_s
            if not 0 <= elapsed <= receipt_ttl:
                return False
            source_age = received.stamp.source_age_s
            if name == "path" and self.evidence.observation_age_s is not None:
                source_age = max(source_age, self.evidence.observation_age_s)
            if self.now > received.receipt_s + source_ttl - source_age:
                return False
        return True


class Normalizer:
    def __init__(self, scope: Scope, policy: TimingPolicy, bindings: Mapping[str, ClockBinding],
                 *, synthetic=False, receiver_session_id=None, receiver_clock_id=None):
        policy.validate()
        self.receiver_session_id = receiver_session_id or secrets.token_hex(16)
        self.receiver_clock_id = receiver_clock_id or self.receiver_session_id
        self.scope, self.policy = scope, policy
        self.bindings, self.synthetic = dict(bindings), synthetic
        self.received = {}
        self.highwater = {}
        self.last_now = None
        self.envelope_sequence = -1
        self.latest = None

    def change_scope(self, scope):
        self.scope = scope
        self.received.clear()
        self.latest = None
        # Keep high water marks: a new generation does not renew old samples.

    def invalidate(self):
        self.received.clear()
        self.latest = None

    def _time(self, now):
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ObservationRejected("INVALID_RECEIVER_CLOCK")
        if self.last_now is not None and now < self.last_now:
            raise ObservationRejected("RECEIVER_CLOCK_ROLLBACK")
        self.last_now = now

    def receive(self, packet: Packet, now: float):
        try:
            return self._receive(packet, now)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            self.invalidate()
            raise ObservationRejected(str(exc)) from exc

    def _receive(self, packet, now):
        self._time(now)
        if packet.receiver_session_id != self.receiver_session_id:
            raise ObservationRejected("RECEIVER_SESSION_RETIRED")
        evidence = Evidence.model_validate(packet.evidence)
        if not self.scope.matches(evidence):
            raise ObservationRejected("OBSERVATION_SCOPE_MISMATCH")
        envelope = self.bindings.get("envelope")
        if (envelope is None or not envelope.relation_verified
                or (evidence.producer_id, evidence.producer_epoch, evidence.source_clock)
                != (envelope.producer_id, envelope.epoch, envelope.source_clock)):
            raise ObservationRejected("ENVELOPE_CLOCK_OR_EPOCH_UNVERIFIED")
        if evidence.sequence <= self.envelope_sequence:
            raise ObservationRejected("DUPLICATE_OR_RETIRED_ENVELOPE")
        if evidence.source_age_s > self.policy.source_max_age_s:
            raise ObservationRejected("ENVELOPE_SOURCE_STALE")
        if not self.synthetic and (evidence.evidence_type != "robot_observation"
                                   or evidence.source_clock == "fixture"):
            raise ObservationRejected("SYNTHETIC_EVIDENCE_NOT_NATIVE")
        if not isinstance(packet.extras, Extras):
            raise ObservationRejected("INVALID_EXTRAS")
        for key in ("departure_observed", "posture_verified", "terrain_verified", "estop", "collision"):
            if type(getattr(packet.extras, key)) is not bool:
                raise ObservationRejected("INVALID_BOOLEAN_EVIDENCE")
        if any(type(v) is not tuple or any(type(x) is not str or not x for x in v)
               for v in (packet.extras.attempted_steps, packet.extras.traversed_segments)):
            raise ObservationRejected("INVALID_COVERAGE")
        values = evidence.model_dump()
        staged = {}
        highwater = dict(self.highwater)
        for name, stamp in packet.components.items():
            binding = self.bindings.get(name)
            if name not in FIELDS or binding is None or not binding.relation_verified:
                raise ObservationRejected("SOURCE_CLOCK_UNVERIFIED")
            if stamp.scope != self.scope:
                raise ObservationRejected("COMPONENT_SCOPE_MISMATCH")
            if (stamp.producer_id, stamp.epoch, stamp.source_clock) != (
                    binding.producer_id, binding.epoch, binding.source_clock):
                raise ObservationRejected("RETIRED_EPOCH_OR_CLOCK_MISMATCH")
            if not self.synthetic and stamp.source_clock == "fixture":
                raise ObservationRejected("FIXTURE_CLOCK_NOT_NATIVE")
            if (type(stamp.sequence) is not int or stamp.sequence < 0
                    or type(stamp.source_age_s) not in (int, float)
                    or not math.isfinite(stamp.source_age_s) or stamp.source_age_s < 0
                    or not isinstance(stamp.source_stamp_ns, str)
                    or not stamp.source_stamp_ns.isascii() or not stamp.source_stamp_ns.isdigit()
                    or not 1 <= len(stamp.source_stamp_ns) <= 24):
                raise ObservationRejected("INVALID_COMPONENT_STAMP")
            if stamp.validity_s is not None and (type(stamp.validity_s) not in (int, float)
                    or not math.isfinite(stamp.validity_s) or not 0 < stamp.validity_s <= 0.25):
                raise ObservationRejected("INVALID_COMPONENT_VALIDITY")
            payload = {key: values[key] for key in FIELDS[name]}
            extra_fields = {"departure": ("departure_observed",),
                            "posture": ("posture_verified", "validation_reference"),
                            "terrain": ("terrain_verified", "validation_reference"),
                            "safety": ("estop", "collision"),
                            "coverage": ("attempted_steps", "traversed_segments")}
            payload.update({key: getattr(packet.extras, key) for key in extra_fields.get(name, ())})
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
            previous = self.received.get(name)
            last_seq, last_source = self.highwater.get(name, (-1, -1))
            if stamp.sequence == last_seq and previous is not None:
                if stamp != previous.stamp or fingerprint != previous.fingerprint:
                    raise ObservationRejected("DUPLICATE_COMPONENT_CHANGED")
                staged[name] = previous  # Never refresh receiver TTL on duplicates.
            elif stamp.sequence <= last_seq or int(stamp.source_stamp_ns) <= last_source:
                raise ObservationRejected("COMPONENT_REPLAY")
            else:
                receipt = now if stamp.first_received_s is None else stamp.first_received_s
                if (type(receipt) not in (int, float) or not math.isfinite(receipt) or receipt > now
                        or (stamp.first_received_s is not None and stamp.receiver_clock_id != self.receiver_clock_id)):
                    raise ObservationRejected("FOREIGN_OR_INVALID_RECEIVER_ARRIVAL")
                staged[name] = Received(stamp, receipt, fingerprint)
                highwater[name] = (stamp.sequence, int(stamp.source_stamp_ns))
        self.received, self.highwater = staged, highwater
        self.envelope_sequence = evidence.sequence
        self.latest = (evidence, packet.extras)
        return self.current(now)

    def current(self, now):
        try:
            self._time(now)
        except ObservationRejected:
            self.invalidate()
            raise
        if self.latest is None:
            return None
        return Frame(*self.latest, dict(self.received), now, self.policy)


def from_vm_stop_input(value, *, envelope, stamps, receiver_session_id):
    """Adapt the actual VM core.StopInput shape, without importing OpenCV/ROS.

    Names SignalObservation/StopZoneObservation/RouteStatus in handoff are
    conceptual: this base revision supplies StopInput, not three ROS messages.
    Trusted caller supplies canonical identity and per-component clock metadata.
    """
    if (value.run_id != envelope["mission_run_id"] or value.step_id != envelope["step_id"]
            or value.generation != envelope["goal_generation"]):
        raise ObservationRejected("VM_SCOPE_MISMATCH")
    if type(value.sequence) is not int or value.sequence < 0:
        raise ObservationRejected("VM_SEQUENCE_REQUIRED")
    for name in ("signal", "feet", "motion", "path", "body", "departure", "safety"):
        if (name not in stamps or stamps[name].epoch != value.epoch
                or stamps[name].sequence != value.sequence):
            raise ObservationRejected("VM_EPOCH_OR_SEQUENCE_NOT_PRESERVED")
    for name, age in (("signal", value.signal_age_s), ("path", value.observation_age_s)):
        if (type(age) not in (int, float) or not math.isfinite(age) or age < 0
                or name not in stamps or stamps[name].source_age_s < age):
            raise ObservationRejected("VM_COMPONENT_AGE_NOT_PRESERVED")
    for name in ("left_inside", "right_inside", "body_stopped", "path_clear", "fully_crossed", "localization_ready"):
        if type(getattr(value, name)) is not bool:
            raise ObservationRejected("VM_BOOLEAN_REQUIRED")
    data = dict(envelope)
    data.update(signal_id=value.signal_id, crossing_id=value.crossing_id,
                stable_state=value.stable_state, raw_state=value.stable_state,
                zone_id=value.zone_id, front_left_status="INSIDE" if value.left_inside else "OUTSIDE",
                front_right_status="INSIDE" if value.right_inside else "OUTSIDE",
                feet_evidence_kind=value.feet_kind,
                body_motion_status="STOPPED" if value.body_stopped else "MOVING",
                path_clear=value.path_clear, full_body_crossed=value.fully_crossed,
                observation_age_s=value.observation_age_s)
    # VM approach_ack does not prove SUCCEEDED/cancel ACK; preserve goal input.
    if not value.localization_ready:
        data["pose"] = None
    if any(type(v) is not bool for v in (value.departure_observed, value.safety_stop)):
        raise ObservationRejected("VM_BOOLEAN_REQUIRED")
    return Packet(data, stamps, Extras(departure_observed=value.departure_observed,
                                       estop=value.safety_stop), receiver_session_id)
