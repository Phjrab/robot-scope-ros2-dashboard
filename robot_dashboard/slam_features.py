"""Read-only, bounded SLAM visualization contracts, without a ROS dependency.

An adapter must supply confirmed engine output and capture the StreamContext in
its subscriptions. This module never opens a camera, looks up a latest TF,
detects replacement features, or constructs native landmark identities.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import hashlib
import json
import math
import struct
import threading
import time
from typing import Any, Mapping, Sequence


class FeatureValidationError(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _get(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, Mapping) else getattr(value, key, default)


def _integer(value: Any, minimum: int = 0, maximum: int = 2**63 - 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise FeatureValidationError("INVALID_INTEGER")
    return value


def timestamp_ns(value: Any) -> str:
    """Keep exact ROS nanoseconds on the wire; floating point stamps are forbidden."""
    if isinstance(value, str):
        if not value or len(value) > 20 or not value.isascii() or not value.isdecimal():
            raise FeatureValidationError("INVALID_TIMESTAMP")
        value = int(value)
    try:
        return str(_integer(value, maximum=2**64 - 1))
    except FeatureValidationError as exc:
        raise FeatureValidationError("INVALID_TIMESTAMP") from exc


def _header(message: Any) -> tuple[str, str]:
    header = _get(message, "header")
    stamp = _get(header, "stamp")
    seconds = _integer(_get(stamp, "sec"), maximum=2**34)
    nanos = _integer(_get(stamp, "nanosec"), maximum=999_999_999)
    return timestamp_ns(seconds * 1_000_000_000 + nanos), _label(_get(header, "frame_id"))


def _label(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or any(ord(c) < 32 for c in value):
        raise FeatureValidationError("INVALID_SOURCE_IDENTITY")
    return value


def _numbers(values: Sequence[float], size: int) -> tuple[float, ...]:
    try:
        if len(values) != size or any(isinstance(v, bool) for v in values):
            raise ValueError()
        result = tuple(float(v) for v in values)
        if not all(math.isfinite(v) and abs(v) <= 1e12 for v in result):
            raise ValueError()
        return result
    except (ValueError, TypeError, OverflowError) as exc:
        raise FeatureValidationError("INVALID_NUMERIC_VALUE") from exc


@dataclass(frozen=True)
class StreamContext:
    session_id: str
    generation: int
    map_epoch: str
    clock_domain: str = "ros"

    def __post_init__(self) -> None:
        _label(self.session_id)
        _integer(self.generation, maximum=2**53 - 1)
        _label(self.map_epoch)
        _label(self.clock_domain)


@dataclass(frozen=True)
class ParsedCloud:
    points: tuple[tuple[float, float, float], ...]
    source_count: int
    rejected_nonfinite: int
    rejected_range: int
    source_timestamp_ns: str
    frame_id: str
    source_cloud_sha256: str


@dataclass(frozen=True)
class NativeFullSnapshotEvidence:
    """Adapter attestation from a qualified, frozen native full-export API.

    Counts inferred from PointCloud2 are not independent retained-map counts.
    The adapter must verify the named API's full-export semantics and freeze a
    revision before constructing this envelope. This store checks the envelope
    against the exact cloud; it cannot qualify a vendor API from an assertion.
    Native IDs reject duplicate/missing entries; they are never derived from
    color or XYZ and never exposed as observation identities.
    """
    export_contract: str
    snapshot_id: str
    engine_revision: str
    source_timestamp_ns: str
    engine_total_count: int
    engine_total_source: str
    native_landmark_ids: tuple[int, ...]
    source_cloud_sha256: str

    def __post_init__(self) -> None:
        for value in (self.export_contract, self.snapshot_id, self.engine_revision,
                      self.engine_total_source):
            _label(value)
        timestamp_ns(self.source_timestamp_ns)
        _integer(self.engine_total_count)
        if (not isinstance(self.source_cloud_sha256, str)
                or len(self.source_cloud_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.source_cloud_sha256)):
            raise FeatureValidationError("INVALID_FULL_SNAPSHOT_DIGEST")
        if (not isinstance(self.native_landmark_ids, tuple)
                or len(self.native_landmark_ids) > 250_000):
            raise FeatureValidationError("INVALID_FULL_SNAPSHOT_IDENTITIES")
        for identity in self.native_landmark_ids:
            # Installed LL_MAP uses int64 IDs; the VO landmark API uses uint64.
            # Keep either exact native representation without coercing a sign.
            _integer(identity, minimum=-(2**63), maximum=2**64 - 1)
        if len(set(self.native_landmark_ids)) != len(self.native_landmark_ids):
            raise FeatureValidationError("DUPLICATE_FULL_SNAPSHOT_IDENTITY")

    def validate(self, parsed: ParsedCloud, *, engine_revision: str | None,
                 engine_total_count: int | None) -> None:
        if (self.engine_revision != engine_revision
                or timestamp_ns(self.source_timestamp_ns) != parsed.source_timestamp_ns
                or self.engine_total_count != engine_total_count
                or self.source_cloud_sha256 != parsed.source_cloud_sha256
                or len(self.native_landmark_ids) != parsed.source_count
                or self.engine_total_count != parsed.source_count):
            raise FeatureValidationError("FULL_SNAPSHOT_EVIDENCE_MISMATCH")

    def summary(self) -> dict[str, Any]:
        return dict(kind="qualified_native_full_snapshot", export_contract=self.export_contract,
                    snapshot_id=self.snapshot_id, engine_revision=self.engine_revision,
                    source_timestamp_ns=timestamp_ns(self.source_timestamp_ns),
                    source_cloud_sha256=self.source_cloud_sha256,
                    engine_total_source=self.engine_total_source,
                    unique_native_id_count=len(self.native_landmark_ids))


_FIELD_FORMATS = {1: ("b", 1), 2: ("B", 1), 3: ("h", 2), 4: ("H", 2),
                  5: ("i", 4), 6: ("I", 4), 7: ("f", 4), 8: ("d", 8)}


def parse_pointcloud2(message: Any, *, max_points: int = 250_000,
                      max_bytes: int = 32 * 1024 * 1024,
                      max_coordinate_abs: float = 1_000_000.0) -> ParsedCloud:
    """Validate an entire PointCloud2 layout before bounded XYZ decoding.

    Organized clouds, row padding, field padding, both endiannesses and float64
    coordinates are supported. Colors and undocumented fields never become IDs.
    Nonfinite/range-invalid XYZ are counted and omitted; malformed layouts fail.
    """
    _integer(max_points, 1)
    _integer(max_bytes, 1)
    if not math.isfinite(max_coordinate_abs) or max_coordinate_abs <= 0:
        raise FeatureValidationError("INVALID_COORDINATE_LIMIT")
    stamp, frame = _header(message)
    width = _integer(_get(message, "width"), maximum=max_points)
    height = _integer(_get(message, "height"), maximum=max_points)
    count = width * height
    if count > max_points:
        raise FeatureValidationError("CLOUD_POINT_LIMIT")
    point_step = _integer(_get(message, "point_step"), 1, 4096)
    row_step = _integer(_get(message, "row_step"), maximum=max_bytes)
    if row_step < width * point_step or row_step * height > max_bytes:
        raise FeatureValidationError("INVALID_CLOUD_STRIDE")
    endian = _get(message, "is_bigendian")
    if not isinstance(endian, bool):
        raise FeatureValidationError("INVALID_CLOUD_ENDIAN")
    fields = _get(message, "fields")
    if not isinstance(fields, (list, tuple)) or not 3 <= len(fields) <= 64:
        raise FeatureValidationError("INVALID_CLOUD_FIELDS")
    layout: dict[str, tuple[int, int, int]] = {}
    occupied: set[int] = set()
    for field in fields:
        name = _label(_get(field, "name"))
        datatype = _integer(_get(field, "datatype"), 1, 8)
        elements = _integer(_get(field, "count"), 1, 4096)
        offset = _integer(_get(field, "offset"), maximum=point_step - 1)
        size = _FIELD_FORMATS[datatype][1] * elements
        if name in layout or offset + size > point_step:
            raise FeatureValidationError("INVALID_CLOUD_FIELDS")
        covered = set(range(offset, offset + size))
        if occupied.intersection(covered):
            raise FeatureValidationError("OVERLAPPING_CLOUD_FIELDS")
        occupied.update(covered)
        layout[name] = (offset, datatype, elements)
    for name in ("x", "y", "z"):
        if name not in layout or layout[name][1] not in (7, 8) or layout[name][2] != 1:
            raise FeatureValidationError("INVALID_XYZ_LAYOUT")
    try:
        data = memoryview(_get(message, "data")).cast("B")
    except (TypeError, ValueError) as exc:
        raise FeatureValidationError("INVALID_CLOUD_PAYLOAD") from exc
    if len(data) != row_step * height or len(data) > max_bytes:
        raise FeatureValidationError("INVALID_CLOUD_PAYLOAD_LENGTH")
    decoders = [(layout[name][0], struct.Struct((">" if endian else "<") +
                _FIELD_FORMATS[layout[name][1]][0])) for name in ("x", "y", "z")]
    points = []
    nonfinite = outside_range = 0
    for row in range(height):
        for col in range(width):
            base = row * row_step + col * point_step
            xyz = tuple(decoder.unpack_from(data, base + offset)[0] for offset, decoder in decoders)
            if not all(math.isfinite(v) for v in xyz):
                nonfinite += 1
            elif any(abs(v) > max_coordinate_abs for v in xyz):
                outside_range += 1
            else:
                points.append(xyz)
    # Bind completeness metadata to exact source identity, layout and bytes;
    # equal counts/timestamps cannot relabel a different XYZ snapshot.
    identity = json.dumps(dict(stamp=stamp, frame=frame, width=width, height=height,
        point_step=point_step, row_step=row_step, endian=endian, layout=layout),
        sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(identity)
    digest.update(data)
    return ParsedCloud(tuple(points), count, nonfinite, outside_range, stamp, frame, digest.hexdigest())


def _spread(value: int) -> int:
    value = (value | value << 16) & 0x030000FF
    value = (value | value << 8) & 0x0300F00F
    value = (value | value << 4) & 0x030C30C3
    return (value | value << 2) & 0x09249249


def spatial_lod(points: Sequence[tuple[float, float, float]], limit: int) -> list[list[float]]:
    """Order-independent spatial quantiles, retaining all six axis extrema.

    Morton order distributes samples over space instead of retaining the first
    received region. This is display decimation, never an engine export claim.
    """
    _integer(limit, 1, 250_000)
    if len(points) <= limit:
        return [list(p) for p in sorted(points)]
    lo = [min(p[a] for p in points) for a in range(3)]
    hi = [max(p[a] for p in points) for a in range(3)]
    span = [hi[a] - lo[a] or 1.0 for a in range(3)]
    def key(p: tuple[float, float, float]) -> tuple[Any, ...]:
        q = [max(0, min(1023, int((p[a] - lo[a]) / span[a] * 1023))) for a in range(3)]
        return (_spread(q[0]) | _spread(q[1]) << 1 | _spread(q[2]) << 2, *p)
    ordered = sorted(points, key=key)
    # Indices keep coincident native points valid without inventing an identity.
    extrema = set()
    if limit >= 6:
        for axis in range(3):
            extrema.add(min(range(len(ordered)), key=lambda i: (ordered[i][axis], ordered[i])))
            extrema.add(max(range(len(ordered)), key=lambda i: (ordered[i][axis], ordered[i])))
    remaining = [i for i in range(len(ordered)) if i not in extrema]
    slots = limit - len(extrema)
    selected = set(extrema)
    for n in range(slots):
        selected.add(remaining[min(len(remaining) - 1, int((n + 0.5) * len(remaining) / slots))])
    return [list(ordered[i]) for i in sorted(selected)]


def project_map_points(points: Sequence[tuple[float, float, float]], *,
                       position: Sequence[float], quaternion_xyzw: Sequence[float],
                       intrinsics: Sequence[float], width: int, height: int
                       ) -> tuple[list[list[float]], dict[str, int]]:
    """p_C = inverse(T_M_C) p_M, with camera coordinates already rectified."""
    px, py, pz = _numbers(position, 3)
    x, y, z, w = _numbers(quaternion_xyzw, 4)
    norm = math.sqrt(x*x + y*y + z*z + w*w)
    if norm < 1e-12 or abs(norm - 1.0) > 0.01:
        raise FeatureValidationError("INVALID_QUATERNION")
    x, y, z, w = x/norm, y/norm, z/norm, w/norm
    fx, fy, cx, cy = _numbers(intrinsics, 4)
    if fx <= 0 or fy <= 0:
        raise FeatureValidationError("INVALID_CALIBRATION")
    _integer(width, 1, 16384)
    _integer(height, 1, 16384)
    # Columns of T_M_C rotation implement the inverse rotation (transpose).
    rotation = ((1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)),
                (2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)),
                (2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)))
    projected = []
    rejected: Counter[str] = Counter()
    for point in points:
        if len(point) != 3 or not all(math.isfinite(v) for v in point):
            rejected["nonfinite"] += 1
            continue
        delta = (point[0]-px, point[1]-py, point[2]-pz)
        X, Y, Z = [sum(rotation[r][c] * delta[r] for r in range(3)) for c in range(3)]
        if Z <= 1e-9:
            rejected["behind_camera"] += 1
            continue
        u, v = fx*X/Z+cx, fy*Y/Z+cy
        if not math.isfinite(u) or not math.isfinite(v):
            rejected["nonfinite"] += 1
        elif not 0 <= u < width or not 0 <= v < height:
            rejected["outside_image"] += 1
        else:
            projected.append([u, v])
    return projected, dict(rejected)


class FeatureStream:
    """One shared adapter cache; independent consumers get latest snapshots.

    All mutation and serialization is serialized. A fresh context clears image,
    pose, observation and global caches. Callbacks holding old contexts fail
    closed. Limits reduce visualization only and never alter estimator inputs.
    Image bytes travel through the existing media path; image_sequence/stamp
    identify the immutable image to which this overlay belongs.
    """
    def __init__(self, context: StreamContext, *, engine_id: str = "visual_stereo",
                 map_frame: str = "map", camera_id: str = "left",
                 max_observations: int = 4096, max_global_points: int = 60_000,
                 max_wire_bytes: int = 8 * 1024 * 1024, cache_size: int = 32,
                 tolerance_ns: int = 20_000_000, stale_after: float = 1.0):
        self.engine_id, self.map_frame, self.camera_id = map(_label, (engine_id, map_frame, camera_id))
        self.max_observations = _integer(max_observations, 1, 4096)
        self.max_global_points = _integer(max_global_points, 1, 250_000)
        self.max_wire_bytes = _integer(max_wire_bytes, 4096, 8 * 1024 * 1024)
        self.cache_size = _integer(cache_size, 1, 128)
        self.tolerance_ns = _integer(tolerance_ns, maximum=20_000_000)
        if not math.isfinite(stale_after) or stale_after <= 0:
            raise FeatureValidationError("INVALID_STALE_LIMIT")
        self.stale_after = stale_after
        self._lock = threading.RLock()
        self._sequence = 0
        self.reset(context)

    def reset(self, context: StreamContext) -> None:
        if not isinstance(context, StreamContext):
            raise FeatureValidationError("INVALID_CONTEXT")
        with self._lock:
            self.context = context
            self._images: deque[dict[str, Any]] = deque(maxlen=self.cache_size)
            self._calibrations: deque[dict[str, Any]] = deque(maxlen=self.cache_size)
            self._poses: deque[dict[str, Any]] = deque(maxlen=self.cache_size)
            self._observations: deque[dict[str, Any]] = deque(maxlen=self.cache_size)
            self._global: dict[str, Any] | None = None
            self._global_points: tuple[tuple[float, float, float], ...] = ()
            self._global_render: list[list[float]] = []
            self._trajectory: dict[str, Any] | None = None
            self._tracking_state = "WAITING_INPUT"
            self._heartbeat_at: float | None = None
            self._discarded_contexts = 0
            self._clock_reset = False
            self._high_water: dict[str, int] = {}
            self._snapshot_sequence = 0

    def _accept(self, context: StreamContext) -> bool:
        if context != self.context:
            self._discarded_contexts += 1
            return False
        return True

    def _stamp(self, source: str, stamp: Any) -> str:
        result = timestamp_ns(stamp)
        value = int(result)
        high = self._high_water.get(source, value)
        if value + 1_000_000_000 < high:
            self._clock_reset = True
            self._images.clear()
            self._poses.clear()
            self._observations.clear()
            raise FeatureValidationError("SOURCE_CLOCK_RESET")
        self._high_water[source] = max(high, value)
        return result

    @staticmethod
    def _received(received_at: float | None) -> float:
        result = time.monotonic() if received_at is None else float(received_at)
        if not math.isfinite(result) or result < 0:
            raise FeatureValidationError("INVALID_RECEIPT_TIME")
        return result

    def record_image(self, *, context: StreamContext, stamp_ns: Any, camera_id: str,
                     width: int, height: int, calibration_revision: str, frame_id: str,
                     sequence: int | None = None, received_at: float | None = None,
                     rectified: bool = True, source_id: str = "left_rectified_input") -> bool:
        with self._lock:
            if not self._accept(context):
                return False
            if camera_id != self.camera_id or rectified is not True:
                raise FeatureValidationError("UNSUPPORTED_IMAGE_CONVENTION")
            _integer(width, 1, 16384)
            _integer(height, 1, 16384)
            if sequence is not None:
                _integer(sequence)
            entry = dict(camera_id=camera_id, width=width, height=height,
                calibration_revision=_label(calibration_revision), frame_id=_label(frame_id),
                source_id=_label(source_id), sequence=sequence, received=self._received(received_at))
            entry["stamp"] = self._stamp("image", stamp_ns)
            self._images.append(entry)
            return True

    def record_camera_info(self, *, context: StreamContext, stamp_ns: Any, camera_id: str,
                           width: int, height: int, calibration_revision: str, frame_id: str,
                           k: Sequence[float] | None = None, p: Sequence[float] | None = None,
                           rectified: bool = True, roi: Sequence[int] = (0, 0, 0, 0),
                           binning_x: int = 0, binning_y: int = 0) -> bool:
        with self._lock:
            if not self._accept(context):
                return False
            if camera_id != self.camera_id or rectified is not True or tuple(roi) != (0, 0, 0, 0):
                raise FeatureValidationError("UNSUPPORTED_CALIBRATION_CONVENTION")
            if binning_x not in (0, 1) or binning_y not in (0, 1) or isinstance(binning_x, bool) or isinstance(binning_y, bool):
                raise FeatureValidationError("UNSUPPORTED_CALIBRATION_BINNING")
            _integer(width, 1, 16384)
            _integer(height, 1, 16384)
            if p is not None:
                model = _numbers(p, 12)
                if any(abs(model[i]) > 1e-9 for i in (1, 3, 4, 7, 8, 9, 11)) or abs(model[10]-1) > 1e-9:
                    raise FeatureValidationError("UNSUPPORTED_PROJECTION_MATRIX")
                intrinsics = (model[0], model[5], model[2], model[6])
            elif k is not None:
                model = _numbers(k, 9)
                if any(abs(model[i]) > 1e-9 for i in (1, 3, 6, 7)) or abs(model[8]-1) > 1e-9:
                    raise FeatureValidationError("UNSUPPORTED_PROJECTION_MATRIX")
                intrinsics = (model[0], model[4], model[2], model[5])
            else:
                raise FeatureValidationError("INVALID_CALIBRATION")
            if intrinsics[0] <= 0 or intrinsics[1] <= 0:
                raise FeatureValidationError("INVALID_CALIBRATION")
            entry = dict(
                camera_id=camera_id, width=width, height=height,
                calibration_revision=_label(calibration_revision), frame_id=_label(frame_id),
                intrinsics=intrinsics)
            entry["stamp"] = self._stamp("calibration", stamp_ns)
            self._calibrations.append(entry)
            return True

    def record_pose(self, *, context: StreamContext, stamp_ns: Any, frame_id: str,
                    camera_frame_id: str, position: Sequence[float],
                    quaternion_xyzw: Sequence[float], received_at: float | None = None) -> bool:
        with self._lock:
            if not self._accept(context):
                return False
            if frame_id != self.map_frame:
                raise FeatureValidationError("POSE_MAP_FRAME_MISMATCH")
            position = _numbers(position, 3)
            quaternion = _numbers(quaternion_xyzw, 4)
            norm = math.sqrt(sum(v*v for v in quaternion))
            if norm < 1e-12 or abs(norm-1) > 0.01:
                raise FeatureValidationError("INVALID_QUATERNION")
            entry = dict(
                camera_frame_id=_label(camera_frame_id), position=position,
                quaternion=quaternion, received=self._received(received_at))
            entry["stamp"] = self._stamp("pose", stamp_ns)
            self._poses.append(entry)
            return True

    def update_observations(self, cloud: Any, *, context: StreamContext, source_id: str,
                            camera_id: str, calibration_revision: str,
                            provenance: str, received_at: float | None = None) -> bool:
        with self._lock:
            if not self._accept(context):
                return False
            if camera_id != self.camera_id:
                raise FeatureValidationError("CAMERA_IDENTITY_MISMATCH")
            source_id, provenance, calibration_revision = map(_label, (source_id, provenance, calibration_revision))
            received = self._received(received_at)
            parsed = parse_pointcloud2(cloud, max_points=32_768, max_bytes=8 * 1024 * 1024)
            if parsed.frame_id != self.map_frame:
                raise FeatureValidationError("OBSERVATIONS_MAP_FRAME_MISMATCH")
            self._observations.append(dict(stamp=self._stamp("observations", parsed.source_timestamp_ns),
                cloud=parsed, camera_id=camera_id, calibration_revision=_label(calibration_revision),
                source_id=source_id, provenance=provenance, received=received))
            return True

    def replace_global(self, cloud: Any, *, context: StreamContext, source_id: str,
                       provenance: str, coverage: str = "unknown", backend_limit: int | None = None,
                       engine_total_count: int | None = None, engine_revision: str | None = None,
                       full_snapshot_evidence: NativeFullSnapshotEvidence | None = None,
                       received_at: float | None = None) -> bool:
        with self._lock:
            if not self._accept(context):
                return False
            if coverage not in ("complete", "subset", "unknown"):
                raise FeatureValidationError("INVALID_COVERAGE")
            if backend_limit is not None:
                _integer(backend_limit)
            if engine_total_count is not None:
                _integer(engine_total_count)
            parsed = parse_pointcloud2(cloud)
            if parsed.frame_id != self.map_frame:
                raise FeatureValidationError("GLOBAL_MAP_FRAME_MISMATCH")
            # Static map stamps need not advance; older snapshots cannot replace newer ones.
            if self._global and int(parsed.source_timestamp_ns) < int(self._global["source_timestamp_ns"]):
                return False
            if engine_total_count is not None and engine_total_count < parsed.source_count:
                raise FeatureValidationError("INVALID_ENGINE_TOTAL")
            if backend_limit is not None and backend_limit < parsed.source_count:
                raise FeatureValidationError("INVALID_BACKEND_LIMIT")
            source_id, provenance = map(_label, (source_id, provenance))
            if engine_revision is not None:
                engine_revision = _label(engine_revision)
            evidence = None
            if full_snapshot_evidence is not None:
                if not isinstance(full_snapshot_evidence, NativeFullSnapshotEvidence):
                    raise FeatureValidationError("INVALID_FULL_SNAPSHOT_EVIDENCE")
                full_snapshot_evidence.validate(parsed, engine_revision=engine_revision,
                                                engine_total_count=engine_total_count)
                evidence = full_snapshot_evidence.summary()
            coverage_reason = "SOURCE_DECLARED_" + coverage.upper()
            if coverage == "complete" and evidence is None:
                coverage, coverage_reason = "unknown", "FULL_SNAPSHOT_EVIDENCE_UNAVAILABLE"
            elif coverage == "complete":
                coverage_reason = "QUALIFIED_NATIVE_FULL_SNAPSHOT"
            if engine_total_count is not None and engine_total_count > parsed.source_count:
                coverage, coverage_reason = "subset", "RETAINED_TOTAL_EXCEEDS_SOURCE_COUNT"
            # Even a qualified native export is incomplete in this store when
            # validation omits coordinates. Display LOD is independent below.
            if parsed.rejected_nonfinite or parsed.rejected_range:
                coverage, coverage_reason = "subset", "SOURCE_POINTS_REJECTED"
            received = self._received(received_at)
            render = spatial_lod(parsed.points, self.max_global_points)
            self._snapshot_sequence += 1
            self._global_points = parsed.points
            self._global_render = render
            self._global = dict(spatial_scope="global_map", coverage=coverage,
                coverage_reason=coverage_reason, completeness_evidence=evidence,
                source_timestamp_ns=parsed.source_timestamp_ns, coordinate_frame=parsed.frame_id,
                source_id=source_id, provenance=provenance,
                snapshot_id=str(self._snapshot_sequence),
                engine_revision=engine_revision,
                map_epoch=context.map_epoch, update_kind="replace", native_ids_available=False,
                exported_count=len(parsed.points), source_count=parsed.source_count,
                rejected_nonfinite=parsed.rejected_nonfinite, rejected_range=parsed.rejected_range,
                engine_total_count=engine_total_count, backend_limit=backend_limit,
                received_at=received)
            return True

    def replace_trajectory(self, points: Sequence[Sequence[float]], *, context: StreamContext,
                           stamp_ns: Any, source_id: str, provenance: str,
                           frame_id: str = "map", trajectory_kind: str = "slam") -> bool:
        with self._lock:
            if not self._accept(context):
                return False
            if frame_id != self.map_frame or trajectory_kind not in ("slam", "vo"):
                raise FeatureValidationError("INVALID_TRAJECTORY_CONVENTION")
            if len(points) > 100_000:
                raise FeatureValidationError("TRAJECTORY_POINT_LIMIT")
            stamp = timestamp_ns(stamp_ns)
            if self._trajectory and int(stamp) < int(self._trajectory["source_timestamp_ns"]):
                return False
            validated = [_numbers(p, 3) for p in points]
            # Preserve temporal ordering and endpoints; never connect shuffled spatial LOD.
            step = max(1, math.ceil(len(validated) / 10_000))
            delivered = validated[::step]
            if validated and delivered[-1] != validated[-1]:
                delivered.append(validated[-1])
            self._trajectory = dict(points=[list(p) for p in delivered],
                source_timestamp_ns=stamp, coordinate_frame=frame_id,
                trajectory_kind=trajectory_kind, source_id=_label(source_id),
                provenance=_label(provenance), source_count=len(validated),
                map_epoch=context.map_epoch, update_kind="replace")
            return True

    def heartbeat(self, *, context: StreamContext, tracking_state: str,
                  received_at: float | None = None) -> bool:
        with self._lock:
            if not self._accept(context):
                return False
            if tracking_state not in ("TRACKING", "MAPPING", "LOCALIZING", "LOST", "WAITING_INPUT", "STOPPED"):
                raise FeatureValidationError("INVALID_TRACKING_STATE")
            received = self._received(received_at)
            self._tracking_state = tracking_state
            self._heartbeat_at = received
            if tracking_state in ("LOST", "STOPPED", "WAITING_INPUT"):
                self._observations.clear()
                self._poses.clear()
            return True

    def _image(self, stamp: str | None = None) -> dict[str, Any] | None:
        images = [p for p in self._images if stamp is None or p["stamp"] == stamp]
        return max(images, key=lambda p: int(p["stamp"])) if images else None

    def _alignment_diagnostics(self, now: float, candidates: list[dict[str, Any]],
                               pixel_stamps: list[str] | None) -> dict[str, Any]:
        """Bounded source evidence, without inferring why callbacks were absent."""
        caches = {}
        for name, cache in (("image", self._images), ("calibration", self._calibrations),
                            ("pose", self._poses), ("observations", self._observations)):
            stamps = [int(item["stamp"]) for item in cache]
            ages = [max(0.0, now-item["received"]) for item in cache if "received" in item]
            caches[name] = dict(count=len(cache), capacity=self.cache_size,
                min_stamp_ns=str(min(stamps)) if stamps else None,
                max_stamp_ns=str(max(stamps)) if stamps else None,
                fresh_count=sum(age <= self.stale_after for age in ages) if ages else None,
                max_receive_age_s=max(ages) if ages else None)
        return dict(schema_version=1, tolerance_ns=str(self.tolerance_ns),
            stale_after_s=self.stale_after, metadata_caches=caches,
            pixel_candidate_count=None if pixel_stamps is None else len(pixel_stamps),
            pixel_min_stamp_ns=min(pixel_stamps, key=int) if pixel_stamps else None,
            pixel_max_stamp_ns=max(pixel_stamps, key=int) if pixel_stamps else None,
            evaluated_count=len(candidates),
            candidate_reason_counts=dict(Counter(item.get("reason") or "ALIGNED" for item in candidates)),
            candidate_details_limit=4,
            evaluated_candidates=[dict(
                image_stamp_ns=item.get("image", {}).get("source_timestamp_ns"),
                reason=item.get("reason"), skew_ns=item.get("overlay_skew_ns"),
                source_stamps=item.get("alignment_source_timestamps_ns"),
                image_receive_age_s=item.get("receive_age_seconds")) for item in candidates[:4]],
            evidence_scope="retained_candidates_only; absent callbacks are not diagnosed")

    def _overlay(self, now: float, image_stamp: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = dict(overlay_kind="unavailable", reason="WAITING_IMAGE", points=[],
                                    native_ids_available=False, confidence=None, track_age=None)
        if self._clock_reset:
            result["reason"] = "SOURCE_CLOCK_RESET"
            return result
        image = self._image(image_stamp)
        if image is None:
            return result
        result["image"] = {k: v for k, v in image.items() if k not in ("received", "stamp")}
        result["image"]["source_timestamp_ns"] = image["stamp"]
        result["receive_age_seconds"] = max(0.0, now-image["received"])
        result["sensor_to_browser_latency_seconds"] = None
        if self._tracking_state in ("LOST", "STOPPED"):
            result["reason"] = self._tracking_state
            return result
        if now-image["received"] > self.stale_after:
            result["reason"] = "STALE_SOURCE"
            return result
        def nearest(cache: Any, predicate: Any) -> Any:
            candidates = [p for p in cache if predicate(p)]
            return min(candidates, key=lambda p: (abs(int(p["stamp"])-int(image["stamp"])), -int(p["stamp"]))) if candidates else None
        info = nearest(self._calibrations, lambda p: all(p[k] == image[k] for k in
                       ("camera_id", "width", "height", "calibration_revision", "frame_id")))
        observations = nearest(self._observations, lambda p: p["camera_id"] == image["camera_id"] and
                               p["calibration_revision"] == image["calibration_revision"])
        pose = nearest(self._poses, lambda p: p["camera_frame_id"] == image["frame_id"])
        if info is None:
            result["reason"] = "CALIBRATION_UNAVAILABLE"
            return result
        if observations is None:
            result["reason"] = "OBSERVATIONS_UNAVAILABLE"
            return result
        if pose is None:
            result["reason"] = "SLAM_CAMERA_POSE_UNAVAILABLE"
            return result
        stamps = [int(p["stamp"]) for p in (image, info, observations, pose)]
        skew = max(stamps)-min(stamps)
        result["alignment_source_timestamps_ns"] = dict(image=image["stamp"],
            calibration=info["stamp"], observations=observations["stamp"], pose=pose["stamp"])
        result["overlay_skew_ns"] = str(skew)
        if skew > self.tolerance_ns:
            result["reason"] = "NO_VALID_TIME_ALIGNMENT"
            return result
        if any(now-p["received"] > self.stale_after for p in (observations, pose)):
            result["reason"] = "STALE_SOURCE"
            return result
        parsed = observations["cloud"]
        # Projection precedes display decimation so off-screen map points cannot
        # consume the current-observation budget.
        pixels, rejected = project_map_points(parsed.points, position=pose["position"],
            quaternion_xyzw=pose["quaternion"], intrinsics=info["intrinsics"],
            width=image["width"], height=image["height"])
        valid_count = len(pixels)
        if len(pixels) > self.max_observations:
            pixels = [pixels[int(i*len(pixels)/self.max_observations)] for i in range(self.max_observations)]
        result.update(overlay_kind="current_observations_reprojected", reason=None,
            points=pixels, displayed_count=len(pixels), projected_count=valid_count,
            exported_count=len(parsed.points), source_count=parsed.source_count,
            source_timestamp_ns=observations["stamp"], source_id=observations["source_id"],
            provenance=observations["provenance"], rejected=dict(rejected,
                cloud_nonfinite=parsed.rejected_nonfinite, cloud_range=parsed.rejected_range),
            decimation=valid_count > len(pixels), pose_source="timestamped_slam_map_camera")
        return result

    def global_snapshot(self, *, region: Sequence[float] | None = None,
                        limit: int | None = None) -> dict[str, Any] | None:
        """Bounded detail query over exported points, without starting a runtime."""
        with self._lock:
            if self._global is None:
                return None
            limit = self.max_global_points if limit is None else _integer(limit, 1, self.max_global_points)
            points = self._global_points
            if region is not None:
                bounds = _numbers(region, 6)
                if any(bounds[a] > bounds[a+3] for a in range(3)):
                    raise FeatureValidationError("INVALID_REGION")
                points = tuple(p for p in points if all(bounds[a] <= p[a] <= bounds[a+3] for a in range(3)))
            sampled = [list(p) for p in self._global_render] if region is None and limit == self.max_global_points else spatial_lod(points, limit)
            return dict(self._global, points=sampled, displayed_count=len(sampled),
                        completeness_evidence=(dict(self._global["completeness_evidence"])
                            if self._global["completeness_evidence"] is not None else None),
                        region_exported_count=len(points), decimation=len(points) > len(sampled))

    def _current_observations(self, now: float) -> dict[str, Any]:
        result: dict[str, Any] = dict(available=False, spatial_scope="current_observations",
            points=[], reason="OBSERVATIONS_UNAVAILABLE", coordinate_frame=self.map_frame,
            map_epoch=self.context.map_epoch, native_ids_available=False)
        if self._clock_reset:
            result["reason"] = "SOURCE_CLOCK_RESET"
            return result
        if self._tracking_state in ("LOST", "STOPPED"):
            result["reason"] = self._tracking_state
            return result
        if not self._observations:
            return result
        observations = max(self._observations, key=lambda p: int(p["stamp"]))
        if now-observations["received"] > self.stale_after:
            result["reason"] = "STALE_SOURCE"
            return result
        parsed = observations["cloud"]
        points = spatial_lod(parsed.points, self.max_observations)
        result.update(available=True, reason=None, points=points,
            source_timestamp_ns=observations["stamp"], source_id=observations["source_id"],
            provenance=observations["provenance"], received_at=observations["received"],
            displayed_count=len(points), exported_count=len(parsed.points),
            source_count=parsed.source_count, decimation=len(points) < len(parsed.points))
        return result

    def camera_view(self, *, now_monotonic: float | None = None,
                    image_timestamp_ns: Any = None) -> dict[str, Any]:
        """Confirmed optical camera geometry, independent of feature export.

        A renderer may use this pinhole pose for illustrative rays/frusta. Its
        ray length is not measured scene depth. Body/odometry poses cannot enter
        this cache: record_pose accepts only the configured map and optical frame
        matched below to the rectified image and calibration identity.
        """
        with self._lock:
            now = self._received(now_monotonic)
            context = self.context
            result: dict[str, Any] = dict(available=False, reason="WAITING_IMAGE",
                session_id=context.session_id, generation=context.generation,
                engine_id=self.engine_id, map_epoch=context.map_epoch,
                coordinate_frame=self.map_frame,
                projection_convention="rectified_optical_x_right_y_down_z_forward",
                provenance="timestamped_slam_map_rectified_optical_pose")
            if self._clock_reset:
                result["reason"] = "SOURCE_CLOCK_RESET"
                return result
            if self._tracking_state in ("LOST", "STOPPED"):
                result["reason"] = self._tracking_state
                return result
            image = self._image(None if image_timestamp_ns is None else timestamp_ns(image_timestamp_ns))
            if image is None:
                return result
            if now-image["received"] > self.stale_after:
                result["reason"] = "STALE_SOURCE"
                return result
            infos = [p for p in self._calibrations if all(p[k] == image[k] for k in
                     ("camera_id", "width", "height", "calibration_revision", "frame_id"))]
            poses = [p for p in self._poses if p["camera_frame_id"] == image["frame_id"]]
            def nearest(values: Any) -> Any:
                return min(values, key=lambda p: (abs(int(p["stamp"])-int(image["stamp"])), -int(p["stamp"])))
            if not infos:
                result["reason"] = "CALIBRATION_UNAVAILABLE"
                return result
            if not poses:
                result["reason"] = "SLAM_CAMERA_POSE_UNAVAILABLE"
                return result
            info, pose = nearest(infos), nearest(poses)
            stamps = [int(p["stamp"]) for p in (image, info, pose)]
            skew = max(stamps)-min(stamps)
            result["alignment_source_timestamps_ns"] = dict(image=image["stamp"],
                calibration=info["stamp"], pose=pose["stamp"])
            result["skew_ns"] = str(skew)
            if skew > self.tolerance_ns:
                result["reason"] = "NO_VALID_TIME_ALIGNMENT"
                return result
            if now-pose["received"] > self.stale_after:
                result["reason"] = "STALE_SOURCE"
                return result
            result.update(available=True, reason=None,
                camera_frame_id=image["frame_id"], width=image["width"], height=image["height"],
                position=list(pose["position"]), quaternion_xyzw=list(pose["quaternion"]),
                intrinsics=list(info["intrinsics"]), calibration_revision=image["calibration_revision"],
                source_timestamp_ns=image["stamp"], image_source_timestamp_ns=image["stamp"],
                pose_source_timestamp_ns=pose["stamp"], calibration_source_timestamp_ns=info["stamp"],
                skew_ns=str(skew), image_sequence=image["sequence"])
            return result

    def frame(self, *, now_monotonic: float | None = None,
              image_timestamps_ns: Sequence[Any] | None = None) -> dict[str, Any]:
        with self._lock:
            now = self._received(now_monotonic)
            self._sequence += 1
            context = self.context
            overlay = self._overlay(now)
            selected_stamp = None
            evaluated = []
            stamps = None
            # Only the adapter can attest that exact pixels remain available.
            # A metadata-only historical image must never replace current media.
            if image_timestamps_ns is not None:
                if len(image_timestamps_ns) > self.cache_size:
                    raise FeatureValidationError("IMAGE_SELECTION_LIMIT")
                stamps = sorted({timestamp_ns(stamp) for stamp in image_timestamps_ns}, key=int, reverse=True)
                for stamp in stamps:
                    candidate = overlay if stamp == overlay.get("image", {}).get("source_timestamp_ns") else self._overlay(now, stamp)
                    evaluated.append(candidate)
                    if candidate["reason"] is None:
                        overlay, selected_stamp = candidate, stamp
                        break
            observations = self._current_observations(now)
            latest_image = max(self._images, key=lambda p: int(p["stamp"])) if self._images else None
            selected_image = self._image(selected_stamp) if selected_stamp is not None else latest_image
            source_stamp = overlay.get("source_timestamp_ns", overlay.get("image", {}).get("source_timestamp_ns"))
            source_id = overlay.get("source_id", overlay.get("image", {}).get("source_id"))
            receipt = selected_image["received"] if selected_image is not None else None
            if source_stamp is None and observations.get("available"):
                source_stamp, source_id = observations["source_timestamp_ns"], observations["source_id"]
                receipt = observations["received_at"]
            if source_stamp is None and self._global:
                source_stamp, source_id = self._global["source_timestamp_ns"], self._global["source_id"]
                receipt = self._global["received_at"]
            result = dict(schema_version=1, engine_id=self.engine_id,
                session_id=context.session_id, generation=context.generation,
                map_epoch=context.map_epoch, frame_id=self.map_frame,
                clock_domain=context.clock_domain, sequence=self._sequence,
                source_timestamp_ns=source_stamp, source_id=source_id, received_at=receipt,
                published_at=now,
                received_clock_domain="host_monotonic", provenance="validated_engine_visualization",
                tracking_state=self._tracking_state,
                heartbeat_receive_age_seconds=None if self._heartbeat_at is None else max(0, now-self._heartbeat_at),
                stream_connected=self._heartbeat_at is not None and now-self._heartbeat_at <= self.stale_after,
                discarded_context_frames=self._discarded_contexts, overlay=overlay,
                camera_view=self.camera_view(now_monotonic=now, image_timestamp_ns=selected_stamp),
                current_observations=observations,
                alignment_diagnostics=self._alignment_diagnostics(now, evaluated, stamps),
                global_map=self.global_snapshot(), trajectory=None if self._trajectory is None else dict(self._trajectory))
            if image_timestamps_ns is not None:
                result["image_selection"] = dict(kind="newest_fresh_completed_quartet" if selected_stamp else "latest_input",
                    selected_timestamp_ns=None if selected_image is None else selected_image["stamp"],
                    latest_timestamp_ns=None if latest_image is None else latest_image["stamp"],
                    receive_age_seconds=None if selected_image is None else max(0.0, now-selected_image["received"]))
            # Each call returns a detached snapshot. No consumer queue can append
            # to this source; transports retain at most their latest two frames.
            while True:
                encoded = json.dumps(result, separators=(",", ":"), allow_nan=False).encode("utf-8")
                if len(encoded) <= self.max_wire_bytes:
                    return json.loads(encoded)
                # Optional diagnostics must never consume a visualization's
                # existing media/geometry budget or prevent a valid frame.
                if "alignment_diagnostics" in result:
                    diagnostic = result["alignment_diagnostics"]
                    details = diagnostic.get("evaluated_candidates", [])
                    if details:
                        details.pop()
                        diagnostic["candidate_details_omitted_for_wire_budget"] = (
                            diagnostic.get("candidate_details_omitted_for_wire_budget", 0) + 1)
                    else:
                        result.pop("alignment_diagnostics")
                    continue
                candidates = [item for item in (result["global_map"], result["trajectory"], overlay, observations)
                              if item is not None and item.get("points")]
                if not candidates:
                    raise FeatureValidationError("FRAME_METADATA_LIMIT")
                item = max(candidates, key=lambda p: len(p["points"]))
                if item is result["global_map"] and len(item["points"]) > 1:
                    item["points"] = spatial_lod(item["points"], max(1, len(item["points"]) // 2))
                elif item is result["trajectory"] and len(item["points"]) > 2:
                    endpoint = item["points"][-1]
                    item["points"] = item["points"][::2]
                    if item["points"][-1] != endpoint:
                        item["points"].append(endpoint)
                else:
                    item["points"] = item["points"][::2] if len(item["points"]) > 1 else []
                item["displayed_count"] = len(item["points"])
                item["decimation"] = True
                item["wire_decimated"] = True
