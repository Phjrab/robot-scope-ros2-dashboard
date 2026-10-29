"""Serialized offline InputFramePacket -> real D2 -> real D3 -> C1/intent.

The caller owns calibrated transforms, clock correspondence and authority.
The default is diagnostic only. No services, subscriptions or command publisher.
"""
from copy import deepcopy
from dataclasses import dataclass, field
import math
import time

from .binding import decimal, digest, integer


@dataclass(frozen=True)
class InputFramePacket:
    meta: dict
    context_key: str
    clock_epoch: str
    tf_epoch: str
    lidar_points: object  # XYZ already in meta.frame_key; never guessed TF.
    sensor_evidence: dict
    ground: dict | None = None
    self_boxes: tuple = ()
    reference: dict | None = None
    depth: object = None
    detections: tuple = ()
    calibration: dict | None = None
    model_manifest: dict | None = None


@dataclass(frozen=True)
class SyntheticCoverage:
    """Harness attestation for one finite synthetic command, NOT a sensor result."""
    context_key: str
    motion_hash: str
    observation_sequence: int
    valid_until_ns: int
    fixture_id: str

    def __post_init__(self):
        integer(self.observation_sequence)
        integer(self.valid_until_ns)
        if not isinstance(self.fixture_id, str) or not 0 < len(self.fixture_id) <= 128:
            raise ValueError("BOUNDED_SYNTHETIC_FIXTURE_ID_REQUIRED")

    def matches(self, packet, context, motion, now_ns):
        return (packet.meta["evidence_kind"] == "SYNTHETIC" and self.fixture_id
            and self.context_key == context.key and self.motion_hash == digest(motion)
            and self.observation_sequence == packet.meta["sequence"] and now_ns < self.valid_until_ns)


@dataclass(frozen=True)
class Intent:
    mode: str
    context_key: str
    command_sequence: int
    velocity: tuple
    severity: str
    reason: str
    sequence: int
    valid_from_ns: int | None = None
    valid_until_ns: int | None = None
    stamp_ns: str = "0"


@dataclass(frozen=True)
class Result:
    intent: Intent
    obstacle_frame: dict | None = None
    assessment: dict | None = None
    raw_observations: dict = field(default_factory=dict)
    clearing_evidence: tuple = ()
    timing: dict = field(default_factory=dict)
    sensor_processed: bool = False
    adapter_published: bool = False
    native_costmap_ingestion_observed: bool = False
    controller_consumption_observed: bool = False


class Runtime:
    def __init__(self, ports, context, mapping, *, mode="ADVISORY_ONLY", clock=time.monotonic_ns):
        if mode not in {"ADVISORY_ONLY", "ACTIVE_CONSTRAINT"}:
            raise ValueError("EXPLICIT_MODE_REQUIRED")
        if ports.geometry.geometry_hash != context.robot_geometry_hash:
            raise ValueError("GEOMETRY_CONTEXT_MISMATCH")
        self.ports, self.context, self.mapping = ports, context, mapping
        self._mode, self.clock = mode, clock
        self.last_sequence = self.last_stamp = -1
        self.result_sequence = 0

    @property
    def mode(self):
        return self._mode

    def rebind(self, context, mapping):
        if context.runtime_generation <= self.context.runtime_generation:
            raise ValueError("INCREASING_RUNTIME_GENERATION_REQUIRED")
        if context.robot_geometry_hash != self.ports.geometry.geometry_hash:
            raise ValueError("GEOMETRY_CONTEXT_MISMATCH")
        self.context, self.mapping = context, mapping
        self.last_sequence = self.last_stamp = -1
        self.ports.reset()
        # No mode downgrade or reuse of a previous CLEAR across rebind.

    def motion(self, command_sequence, velocity, horizon_s):
        integer(command_sequence)
        if (len(velocity) != 3 or not all(type(v) in (float, int) and math.isfinite(v) for v in velocity)
                or velocity[1] != 0 or not 0 < horizon_s <= .25):
            raise ValueError("UNSUPPORTED_COMMAND_HYPOTHESIS")
        return dict(ref=dict(context_key=self.context.key, command_sequence=command_sequence,
                             command_scope=self.context.command_scope),
                    command=dict(linear_x_mps=velocity[0], angular_z_radps=velocity[2], horizon_s=horizon_s))

    def _sensor_evidence(self, packet):
        raw, rays = deepcopy(packet.sensor_evidence), []
        if set(raw) - {"lidar", "depth"} or "lidar" not in raw:
            raise ValueError("PER_SENSOR_EVIDENCE_REQUIRED")
        for kind, source in raw.items():
            if (source["meta"] != packet.meta or source["tf_epoch"] != packet.tf_epoch
                    or not source["calibration_id"] or not source["raw_reference"]):
                raise ValueError("RAW_SOURCE_IDENTITY_MISMATCH")
            origin = source["origin_m"]
            if (len(origin) != 3 or not all(math.isfinite(x) for x in origin)
                    or not 0 < source["max_range_m"] <= self.ports.limits.range_m
                    or not 0 < source["fov_rad"] <= 2 * math.pi
                    or type(source["valid_measurement"]) is not bool):
                raise ValueError("SENSOR_RANGE_FOV_ORIGIN_REQUIRED")
            # No ray is inferred from a fused centroid/extent, missing detections,
            # source loss, or tracker expiry. Caller retains raw measurement proof.
            for ray in source.get("free_rays", ()):
                if (not source["valid_measurement"] or ray.get("measurement_valid") is not True
                        or ray.get("raw_reference") != source["raw_reference"]
                        or ray.get("meta") != packet.meta or ray.get("origin") != origin):
                    raise ValueError("UNSUPPORTED_FREE_RAY_EVIDENCE")
                end = ray["free_endpoint"]
                if (len(end) != 3 or not all(math.isfinite(x) for x in end)
                        or math.dist(origin, end) > source["max_range_m"]):
                    raise ValueError("FREE_RAY_OUTSIDE_SENSOR_RANGE")
                rays.append(deepcopy(ray))
            source["marking_candidate"] = source["valid_measurement"]
            source["clearing_candidate"] = bool(source.get("free_rays"))
            source["adapter_published"] = source["native_ingestion_observed"] = False
        if not raw["lidar"]["valid_measurement"]:
            raise ValueError("LIDAR_MEASUREMENT_UNAVAILABLE")
        return raw, rays

    def process(self, packet, state, *, command_sequence, velocity, horizon_s=.1,
                coverage=None, authority_present=False):
        self.result_sequence += 1
        now = integer(self.clock())
        timing = dict(c4_received_monotonic_ns=now)
        intent = dict(mode=self.mode, context_key=self.context.key, command_sequence=command_sequence,
                      velocity=tuple(velocity), sequence=self.result_sequence)
        try:
            packet, state = deepcopy(packet), deepcopy(state)
            motion = self.motion(command_sequence, velocity, horizon_s)
            meta = deepcopy(packet.meta)
            self.mapping.check(self.context, meta["clock_domain"])
            if (packet.context_key != self.context.key or packet.clock_epoch != self.context.clock_epoch
                    or packet.tf_epoch != self.context.tf_epoch or meta["source_epoch"] != self.context.source_epoch
                    or meta["frame_key"] != dict(source_epoch=self.context.source_epoch, frame_id=self.context.frame_id)
                    or meta["map_binding"] != self.context.map_binding or meta["host_clock_id"] != self.context.host_clock_id):
                raise ValueError("INPUT_BINDING_MISMATCH")
            stamp, sequence = decimal(meta["stamp_ns"]), integer(meta["sequence"])
            received = integer(meta["received_monotonic_ns"])
            age = now - self.mapping.host(stamp) + self.mapping.uncertainty_ns
            if (not 0 <= now - received <= self.ports.limits.max_delay_ns
                    or not 0 <= age <= self.ports.limits.max_delay_ns):
                raise ValueError("STALE_FUTURE_OR_LATE_INPUT")
            if sequence <= self.last_sequence or stamp <= self.last_stamp:
                raise ValueError("DUPLICATE_OR_REORDERED_INPUT")
            for name in ("source_epoch", "frame_key", "map_binding", "clock_domain", "host_clock_id", "evidence_kind"):
                if state[name] != meta[name]:
                    raise ValueError("ROBOT_STATE_BINDING_MISMATCH")
            raw, rays = self._sensor_evidence(packet)
            meta["source_age_ns"] = age
            timing.update(observation_stamp_ns=meta["stamp_ns"], observation_received_monotonic_ns=received,
                          source_clock_domain=meta["clock_domain"], d2_started_monotonic_ns=integer(self.clock()))
            perception = self.ports.perceive(packet, meta, rays)
            self.last_sequence, self.last_stamp = sequence, stamp
            timing["d2_finished_monotonic_ns"] = integer(self.clock())
            d3_now = integer(self.clock())
            timing["d3_started_monotonic_ns"] = d3_now
            complete = bool(coverage and coverage.matches(packet, self.context, motion, d3_now))
            outside_scope = coverage is not None and not complete
            assessment = self.ports.assess(state, perception["obstacle_frame"], motion,
                now_stamp_ns=d3_now - self.mapping.offset_ns, clock_domain=meta["clock_domain"], complete=complete)
            timing["d3_finished_monotonic_ns"] = integer(self.clock())
            timing["c4_converted_monotonic_ns"] = integer(self.clock())
            wire = self.ports.canonical_assessment(assessment, context=self.context,
                mapping=self.mapping, motion=motion, timing=timing)
            wire["freshness"]["c4"]["original_assessment_sequence"] = wire["sequence"]
            wire["sequence"] = self.result_sequence
            wire["producer"] = "c4.expansion_runtime"
            interval = wire["validity_interval"]
            start, end = interval.get("start_monotonic_ns"), interval.get("end_monotonic_ns")
            if complete and end is not None:
                # Scoped evidence can shorten enforcement, never extend D3 expiry.
                end = min(end, coverage.valid_until_ns)
                interval["end_monotonic_ns"] = end
                wire["freshness"]["c4"]["synthetic_scope"] = dict(
                    fixture_id=coverage.fixture_id, motion_hash=coverage.motion_hash,
                    observation_sequence=coverage.observation_sequence, valid_until_ns=end)
            severity, reason = wire["severity"], wire["reason"]
            if outside_scope:
                severity, reason = "UNKNOWN", "COVERAGE_OUTSIDE_MOTION_SCOPE"
            if start is None or not start <= timing["c4_converted_monotonic_ns"] < end:
                severity, reason = "UNKNOWN", "ASSESSMENT_EXPIRED_OR_UNMAPPED"
            if self.mode == "ACTIVE_CONSTRAINT" and not authority_present:
                severity, reason = "UNKNOWN", "MISSING_TRUSTED_AUTHORITY"
            self.ports.contracts.CollisionAssessment.from_dict(wire)
            return Result(Intent(**intent, severity=severity, reason=reason, valid_from_ns=start,
                valid_until_ns=end, stamp_ns=meta["stamp_ns"]), perception["obstacle_frame"], wire,
                raw, tuple(perception["clearing_evidence"]), timing, sensor_processed=True)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            return Result(Intent(**intent, severity="UNKNOWN", reason=str(exc)), timing=timing)
