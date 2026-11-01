"""Small, strict JSON contracts. T_A_B maps B column vectors into A; xyzw, m/rad."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import copy
import hashlib
import json
import math
import re
from typing import Any, ClassVar

MAX_DOCUMENT_BYTES = 128 * 1024
ID = re.compile(r"[0-9a-f]{24}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
TOKEN = re.compile(r"[A-Za-z0-9_:.@-]{1,128}\Z")
IDENTITY = (
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
)


class ContractError(ValueError):
    pass


def canonical(value: Any, limit=MAX_DOCUMENT_BYTES) -> bytes:
    try:
        data = json.dumps(
            value, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode()
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ContractError("document requires bounded finite JSON") from exc
    if len(data) > limit:
        raise ContractError("document exceeds byte limit")
    return data


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def token(value, label="identifier", pattern=TOKEN):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ContractError(f"invalid {label}")
    return value


def integer(value, label, low=0, high=2**53 - 1):
    if type(value) is not int or not low <= value <= high:
        raise ContractError(f"invalid {label}")
    return value


def number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ContractError(f"invalid {label}")
    return value


def validate_transform(value):
    if not isinstance(value, (list, tuple)) or len(value) != 16:
        raise ContractError("transform requires 16 row-major SE3 values")
    v = [number(x, "transform") for x in value]
    if any(abs(v[12 + i] - (1 if i == 3 else 0)) > 1e-7 for i in range(4)):
        raise ContractError("invalid homogeneous row")
    r = [[v[i * 4 + j] for j in range(3)] for i in range(3)]
    if any(
        abs(sum(r[k][i] * r[k][j] for k in range(3)) - (i == j)) > 1e-6
        for i in range(3)
        for j in range(3)
    ):
        raise ContractError("transform rotation must be orthonormal with unit scale")
    det = sum(
        r[0][i]
        * (
            r[1][(i + 1) % 3] * r[2][(i + 2) % 3]
            - r[1][(i + 2) % 3] * r[2][(i + 1) % 3]
        )
        for i in range(3)
    )
    if abs(det - 1) > 1e-6:
        raise ContractError("transform rotation must have positive determinant")
    return tuple(float(x) for x in v)


class Wire:
    def to_dict(self):
        # JSON normalizes tuples and returns a detached copy.
        return json.loads(canonical(asdict(self)))

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {f.name for f in fields(cls)}:
            raise ContractError(f"{cls.__name__} fields differ from contract")
        canonical(value)
        try:
            return cls(**copy.deepcopy(value))
        except (TypeError, KeyError) as exc:
            raise ContractError(f"invalid {cls.__name__}") from exc


@dataclass(frozen=True, kw_only=True)
class Message(Wire):
    versions: ClassVar[frozenset] = frozenset({"0.1"})
    schema_version: str
    evidence_kind: str
    producer: str
    sequence: int
    source_epoch: str

    def __post_init__(self):
        if self.schema_version not in self.versions or self.evidence_kind not in {
            "SYNTHETIC",
            "REPLAY",
            "LIVE",
        }:
            raise ContractError("unsupported schema/evidence")
        token(self.producer, "producer")
        token(self.source_epoch, "epoch")
        integer(self.sequence, "sequence")
        canonical(asdict(self))


@dataclass(frozen=True, kw_only=True)
class MapSourceDescriptor(Message):
    map_id: str
    revision: str
    sha256: str
    frame_id: str
    units: str
    asset_role: str
    mapping_session_id: str | None
    gravity_or_plane: dict | None
    point_count: int
    point_schema: list
    acquisition: dict

    def __post_init__(self):
        super().__post_init__()
        token(self.map_id, "map ID", ID)
        token(self.revision, "revision", HASH)
        token(self.sha256, "hash", HASH)
        token(self.frame_id, "frame")
        if self.units != "m" or self.asset_role != "full_source":
            raise ContractError("requires full source in metres")
        if self.mapping_session_id is not None:
            token(self.mapping_session_id, "session", ID)
        integer(self.point_count, "point count", 1, 20_000_000)
        if (
            not isinstance(self.point_schema, list)
            or not 3 <= len(self.point_schema) <= 256
        ):
            raise ContractError("point schema required")
        names = set()
        for f in self.point_schema:
            if not isinstance(f, dict) or set(f) != {"name", "size", "type", "count"}:
                raise ContractError("invalid point field")
            token(f["name"], "field")
            if (
                f["name"] in names
                or f["type"] not in {"F", "I", "U"}
                or f["size"] not in {1, 2, 4, 8}
            ):
                raise ContractError("invalid/duplicate point schema")
            names.add(f["name"])
            integer(f["count"], "field count", 1, 1024)
        if not {"x", "y", "z"} <= names or not isinstance(self.acquisition, dict):
            raise ContractError("missing XYZ or acquisition provenance")

    @property
    def key(self):
        return f"{self.map_id}:{self.revision}:{self.frame_id}"


@dataclass(frozen=True, kw_only=True)
class FusionRequest(Message):
    request_id: str
    anchor_source_key: str
    sources: list
    source_pins: dict
    initial_guesses: list
    correspondences: list
    mode: str
    options: dict

    def __post_init__(self):
        super().__post_init__()
        token(self.request_id)
        if not isinstance(self.sources, list) or not 2 <= len(self.sources) <= 8:
            raise ContractError("fusion requires 2..8 sources")
        descriptors = [MapSourceDescriptor.from_dict(v) for v in self.sources]
        keys = [d.key for d in descriptors]
        if (
            len(set(d.map_id for d in descriptors)) != len(keys)
            or self.anchor_source_key not in keys
        ):
            raise ContractError("duplicate sources or missing anchor")
        if self.source_pins != {d.key: d.sha256 for d in descriptors}:
            raise ContractError("source pins do not match descriptors")
        if self.mode not in {"auto", "seeded", "manual_review"}:
            raise ContractError("unsupported fusion mode")
        if not isinstance(self.initial_guesses, list) or len(self.initial_guesses) > 8:
            raise ContractError("too many guesses")
        for g in self.initial_guesses:
            if (
                not isinstance(g, dict)
                or set(g) != {"source_key", "T_anchor_source"}
                or g["source_key"] not in keys
            ):
                raise ContractError("invalid initial guess")
            validate_transform(g["T_anchor_source"])
        if (
            not isinstance(self.correspondences, list)
            or len(self.correspondences) > 256
        ):
            raise ContractError("too many correspondences")
        for c in self.correspondences:
            if (
                not isinstance(c, dict)
                or set(c) != {"source_key", "source_xyz", "anchor_xyz"}
                or c["source_key"] not in keys
            ):
                raise ContractError("invalid correspondence")
            for field in ("source_xyz", "anchor_xyz"):
                if not isinstance(c[field], list) or len(c[field]) != 3:
                    raise ContractError("correspondence requires XYZ")
                for n in c[field]:
                    number(n, field)
        if not isinstance(self.options, dict) or set(self.options) - {
            "voxel_size",
            "max_iterations",
            "max_runtime_s",
        }:
            raise ContractError("unsupported algorithm option")
        for k, v in self.options.items():
            number(v, k)
            if (
                not 0
                < v
                <= {"voxel_size": 10, "max_iterations": 10000, "max_runtime_s": 300}[k]
            ):
                raise ContractError("algorithm option outside bound")
        if "max_iterations" in self.options:
            integer(self.options["max_iterations"], "max_iterations", 1, 10000)

    @property
    def fingerprint(self):
        return digest(
            {
                k: v
                for k, v in self.to_dict().items()
                if k not in {"request_id", "sequence"}
            }
        )


TERMINAL = {
    "SOLVED_CANDIDATE",
    "NEEDS_PRIOR",
    "DISCONNECTED",
    "REJECTED",
    "CANCELED",
    "FAILED",
}


@dataclass(frozen=True, kw_only=True)
class FusionProposal(Message):
    job_id: str
    proposal_revision: int
    state: str
    anchor_source_key: str
    T_fused_source: dict
    pairwise_edges: list
    connected_components: list
    quality: dict
    ambiguous_candidates: list
    warnings: list
    input_pins: dict
    solver_version: str
    elapsed_ms: float

    def __post_init__(self):
        super().__post_init__()
        token(self.job_id, "job ID", ID)
        integer(self.proposal_revision, "proposal revision", 1)
        if self.state not in TERMINAL:
            raise ContractError("unsupported solver terminal")
        if (
            not isinstance(self.input_pins, dict)
            or not self.input_pins
            or self.anchor_source_key not in self.input_pins
        ):
            raise ContractError("proposal pins required")
        if not isinstance(self.T_fused_source, dict):
            raise ContractError("transform dictionary required")
        if self.state == "SOLVED_CANDIDATE" and set(self.T_fused_source) != set(
            self.input_pins
        ):
            raise ContractError("solved candidate must transform every source")
        for t in self.T_fused_source.values():
            validate_transform(t)
        if self.state == "SOLVED_CANDIDATE" and any(
            abs(a - b) > 1e-7
            for a, b in zip(self.T_fused_source[self.anchor_source_key], IDENTITY)
        ):
            raise ContractError("anchor must remain identity")
        if not all(isinstance(e, dict) for e in self.pairwise_edges):
            raise ContractError("pairwise edges require named metrics")
        for field in (
            self.pairwise_edges,
            self.connected_components,
            self.ambiguous_candidates,
            self.warnings,
        ):
            if not isinstance(field, list) or len(field) > 256:
                raise ContractError("invalid bounded proposal list")
        if not isinstance(self.quality, dict):
            raise ContractError("quality must retain separate metrics")
        token(self.solver_version)
        if number(self.elapsed_ms, "elapsed") < 0:
            raise ContractError("negative elapsed")


def host_ns(value, version):
    """v0.2 uses lossless decimal strings; v0.1 remains explicitly legacy."""
    if version == "0.2":
        token(
            value, "decimal host nanoseconds", re.compile(r"(?:0|[1-9][0-9]{0,18})\Z")
        )
        value = int(value)
    return integer(value, "host nanoseconds", 0, 2**63 - 1)


def _observation(message):
    token(
        message.stamp_ns, "decimal nanoseconds", re.compile(r"(?:0|[1-9][0-9]{0,24})\Z")
    )
    token(message.clock_domain)
    token(message.host_clock_id)
    host_ns(message.received_monotonic_ns, message.schema_version)
    if (
        not isinstance(message.frame_key, dict)
        or set(message.frame_key) != {"source_epoch", "frame_id"}
        or message.frame_key["source_epoch"] != message.source_epoch
    ):
        raise ContractError("frame requires matching epoch and frame ID")
    token(message.frame_key["frame_id"])
    if not isinstance(message.map_binding, dict) or set(message.map_binding) != {
        "map_id",
        "revision",
        "generation",
    }:
        raise ContractError("map binding required")
    token(message.map_binding["map_id"], "map ID", ID)
    token(message.map_binding["revision"], "revision", HASH)
    integer(message.map_binding["generation"], "map generation")


@dataclass(frozen=True, kw_only=True)
class Observation(Message):
    versions: ClassVar[frozenset] = frozenset({"0.1", "0.2"})
    frame_key: dict
    stamp_ns: str
    clock_domain: str
    host_clock_id: str
    received_monotonic_ns: int | str
    map_binding: dict

    def __post_init__(self):
        super().__post_init__()
        _observation(self)


@dataclass(frozen=True, kw_only=True)
class ObstacleFrame(Observation):
    calibration_id: str | None
    input_sources: list
    obstacles: list
    health: dict
    dropped_counts: dict
    observation_only: bool = True
    published_to_nav2: bool = False
    costmap_ingestion_observed: bool = False
    controller_consumption_observed: bool = False

    def __post_init__(self):
        super().__post_init__()
        if self.calibration_id is not None:
            token(self.calibration_id)
        if (
            not isinstance(self.obstacles, list)
            or len(self.obstacles) > 512
            or not isinstance(self.input_sources, list)
            or len(self.input_sources) > 16
        ):
            raise ContractError("obstacle frame exceeds bounds")
        for obstacle in self.obstacles:
            if not isinstance(obstacle, dict) or not {
                "track_id",
                "geometry",
                "state",
                "novelty",
                "provenance",
            } <= set(obstacle):
                raise ContractError("invalid obstacle")
            token(obstacle["track_id"])
            if obstacle["state"] not in {
                "OBSERVED",
                "OCCLUDED",
                "STALE",
                "REJECTED",
            } or obstacle["novelty"] not in {"NEW_TO_REFERENCE", "KNOWN", "UNRESOLVED"}:
                raise ContractError("invalid obstacle status")
        if not isinstance(self.health, dict) or not isinstance(
            self.dropped_counts, dict
        ):
            raise ContractError("health and dropped counts required")
        for v in self.dropped_counts.values():
            integer(v, "dropped count")
        if self.observation_only is not True or any(
            v is not False
            for v in (
                self.published_to_nav2,
                self.costmap_ingestion_observed,
                self.controller_consumption_observed,
            )
        ):
            raise ContractError("v0.1 sink is observation only")


@dataclass(frozen=True, kw_only=True)
class CollisionAssessment(Observation):
    robot_pose_ref: dict | None
    joint_state_ref: dict | None
    robot_geometry_hash: str | None
    obstacle_frame_ref: dict | None
    path_ref: dict | None
    padded_envelope: dict | None
    unpadded_envelope: dict | None
    min_clearance: float | None
    predicted_overlap: bool | None
    modeled_ttc: float | None
    freshness: dict
    validity_interval: dict
    reason: str
    severity: str
    recommendation: str

    def __post_init__(self):
        super().__post_init__()
        if self.robot_geometry_hash is not None:
            token(self.robot_geometry_hash, "geometry hash", HASH)
        if self.severity not in {
            "CLEAR",
            "CAUTION",
            "STOP_REQUIRED",
            "UNKNOWN",
        } or self.reason not in {
            "MODEL_OVERLAP",
            "PREDICTED_COLLISION",
            "CONTACT_UNCONFIRMED",
            "UNKNOWN",
            "CLEAR",
        }:
            raise ContractError(
                "invalid assessment; contact confirmation is unsupported"
            )
        for v in (self.min_clearance, self.modeled_ttc):
            if v is not None:
                number(v, "collision metric")
        if self.modeled_ttc is not None and self.modeled_ttc < 0:
            raise ContractError("negative TTC")
        if not isinstance(self.freshness, dict) or not isinstance(
            self.validity_interval, dict
        ):
            raise ContractError("freshness and host validity interval required")
        expected = {"host_clock_id", "start_monotonic_ns", "end_monotonic_ns"}
        if self.validity_interval:
            if set(self.validity_interval) != expected:
                raise ContractError(
                    "validity interval requires explicit host clock and monotonic bounds"
                )
            token(self.validity_interval["host_clock_id"])
            start = host_ns(
                self.validity_interval["start_monotonic_ns"], self.schema_version
            )
            end = host_ns(
                self.validity_interval["end_monotonic_ns"], self.schema_version
            )
            if end < start:
                raise ContractError("reversed validity interval")
        if (
            self.predicted_overlap is not None
            and type(self.predicted_overlap) is not bool
        ):
            raise ContractError("invalid overlap")


@dataclass(frozen=True, kw_only=True)
class ScenePacket(Message):
    versions: ClassVar[frozenset] = frozenset({"0.1", "0.2"})
    map_binding: dict
    stream_epoch: str
    robot_pose: dict | None
    obstacle_frame: dict | None
    global_path: dict | None
    controller_local_trajectory: dict | None
    costmap_snapshot: dict | None
    collision_assessment: dict | None
    sources: dict

    def __post_init__(self):
        super().__post_init__()
        token(self.stream_epoch)
        if not isinstance(self.map_binding, dict) or set(self.map_binding) != {
            "map_id",
            "revision",
            "generation",
        }:
            raise ContractError("scene map binding required")
        token(self.map_binding["map_id"], pattern=ID)
        token(self.map_binding["revision"], pattern=HASH)
        integer(self.map_binding["generation"], "map generation")
        if self.obstacle_frame is not None:
            ObstacleFrame.from_dict(self.obstacle_frame)
        if self.collision_assessment is not None:
            CollisionAssessment.from_dict(self.collision_assessment)
