"""ROS Humble message layout readers, without ROS imports or sensor algorithms.

Only transport guards live here. C1 remains the shared schema validator owner.
Source clock metadata is supplied by the existing owner (ROS 2 Header has no seq).
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
import math
import struct

MAX_BYTES = 8 * 1024 * 1024
MAX_POINTS = 200_000


def get(value, name):
    return value[name] if isinstance(value, dict) else getattr(value, name)


def finite(values):
    result = tuple(float(v) for v in values)
    if not all(math.isfinite(v) for v in result):
        raise ValueError("NONFINITE_MESSAGE")
    return result


def stamp_ns(message):
    stamp = get(get(message, "header"), "stamp")
    sec, nsec = get(stamp, "sec"), get(stamp, "nanosec")
    if type(sec) is not int or type(nsec) is not int or not 0 <= nsec < 1_000_000_000:
        raise ValueError("STAMP_INVALID")
    return str(sec * 1_000_000_000 + nsec)


@dataclass(frozen=True)
class Identity:
    source_id: str
    source_epoch: str
    sequence: int
    stamp_ns: str
    clock_domain: str
    frame_id: str
    received_ns: int
    receipt_clock_id: str
    tf_epoch: str
    map_id: str = "synthetic-map"
    revision: str = "r1"
    evidence_kind: str = "SYNTHETIC"
    producer: str = "c4-fixture"
    map_generation: int = 0

    def __post_init__(self):
        if self.evidence_kind not in {"SYNTHETIC", "REPLAY"}:
            raise ValueError("LIVE_EVIDENCE_FORBIDDEN")
        if (type(self.sequence) is not int or self.sequence < 0
                or type(self.map_generation) is not int or self.map_generation < 0
                or not isinstance(self.stamp_ns, str) or not self.stamp_ns.isdecimal()
                or type(self.received_ns) is not int or self.received_ns < 0
                or not all(isinstance(v, str) and v and len(v) <= 256 for v in (
                    self.source_id, self.source_epoch, self.clock_domain, self.frame_id,
                    self.receipt_clock_id, self.tf_epoch, self.map_id, self.revision, self.producer))):
            raise ValueError("IDENTITY_INVALID")

    @property
    def binding(self):
        return (self.map_id, self.revision, self.tf_epoch, self.map_generation)

    def packet(self):
        result = asdict(self)
        result["frame_key"] = {"source_epoch": self.source_epoch, "frame_id": self.frame_id}
        result["map_binding"] = {"map_id": self.map_id, "revision": self.revision, "generation": self.map_generation}
        return result


@dataclass(frozen=True)
class Sample:
    identity: Identity
    kind: str
    payload: dict
    origin_m: tuple | None = None
    diagnostics: tuple = ()


def header_matches(message, identity):
    if stamp_ns(message) != identity.stamp_ns or get(get(message, "header"), "frame_id") != identity.frame_id:
        raise ValueError("SOURCE_HEADER_MISMATCH")


def pointcloud2(message, identity, *, origin_m=None):
    header_matches(message, identity)
    width, height = get(message, "width"), get(message, "height")
    step, row = get(message, "point_step"), get(message, "row_step")
    data = bytes(get(message, "data"))
    if (any(type(v) is not int for v in (width, height, step, row))
            or not 0 <= width * height <= MAX_POINTS or width < 0 or height < 1
            or step < 1 or row < width * step or len(data) != height * row or len(data) > MAX_BYTES):
        raise ValueError("POINTCLOUD_LAYOUT_INVALID")
    fields = [{k: get(f, k) for k in ("name", "offset", "datatype", "count")}
              for f in get(message, "fields")]
    if len(fields) > 64 or len({f["name"] for f in fields}) != len(fields):
        raise ValueError("POINTCLOUD_FIELDS_INVALID")
    sizes = {1: 1, 2: 1, 3: 2, 4: 2, 5: 4, 6: 4, 7: 4, 8: 8}
    for f in fields:
        if (f["datatype"] not in sizes or type(f["count"]) is not int or f["count"] < 1
                or type(f["offset"]) is not int or f["offset"] < 0
                or f["offset"] + sizes[f["datatype"]] * f["count"] > step):
            raise ValueError("POINTCLOUD_FIELD_OUT_OF_RECORD")
    xyz_fields = []
    for name in ("x", "y", "z"):
        f = next((f for f in fields if f["name"] == name), None)
        if f is None or f["datatype"] not in (7, 8) or f["count"] != 1:
            raise ValueError("POINTCLOUD_XYZ_REQUIRED")
        xyz_fields.append(f)
    big = bool(get(message, "is_bigendian"))
    readers = [(struct.Struct((">" if big else "<") + ("f" if f["datatype"] == 7 else "d")), f["offset"])
               for f in xyz_fields]
    xyz, invalid = [], 0
    for y in range(height):
        for x in range(width):
            offset = y * row + x * step
            p = tuple(reader.unpack_from(data, offset + field_offset)[0] for reader, field_offset in readers)
            if all(math.isfinite(v) for v in p):
                xyz.append(p)
            else:
                invalid += 1
    origin = finite(origin_m) if origin_m is not None else None
    if origin is not None and len(origin) != 3:
        raise ValueError("ORIGIN_XYZ_REQUIRED")
    return Sample(identity, "PointCloud2", {"xyz_m": tuple(xyz), "invalid_points": invalid,
        "raw_data": data, "fields": fields, "width": width, "height": height,
        "point_step": step, "row_step": row, "is_bigendian": big}, origin,
        () if origin else ("SENSOR_ORIGIN_UNAVAILABLE",))


def camera_info(message, identity, *, device_id, profile_id, calibration_id=None):
    header_matches(message, identity)
    payload = {k: deepcopy(get(message, k)) for k in (
        "width", "height", "distortion_model", "d", "k", "r", "p", "binning_x", "binning_y")}
    payload["roi"] = {k: get(get(message, "roi"), k) for k in (
        "x_offset", "y_offset", "width", "height", "do_rectify")}
    if (len(payload["k"]) != 9 or len(payload["r"]) != 9 or len(payload["p"]) != 12
            or len(payload["d"]) > 16 or payload["width"] <= 0 or payload["height"] <= 0):
        raise ValueError("CAMERA_INFO_LAYOUT_INVALID")
    finite((*payload["d"], *payload["k"], *payload["r"], *payload["p"]))
    payload.update(device_id=device_id, profile_id=profile_id, calibration_id=calibration_id)
    return Sample(identity, "CameraInfo", payload)


def color_image(message, identity, *, metadata=None):
    """Read existing owner's Image bytes only; no decoding/model acquisition."""
    header_matches(message, identity)
    encoding = get(message, "encoding")
    channels = {"rgb8": 3, "bgr8": 3, "mono8": 1}.get(encoding)
    if channels is None:
        raise ValueError("COLOR_ENCODING_UNSUPPORTED")
    width, height, step = (get(message, k) for k in ("width", "height", "step"))
    data = bytes(get(message, "data"))
    if (any(type(v) is not int for v in (width, height, step)) or width < 1 or height < 1
            or step < width*channels or len(data) != height*step or len(data) > MAX_BYTES):
        raise ValueError("COLOR_LAYOUT_INVALID")
    return Sample(identity, "Image/color", {"width": width, "height": height, "step": step,
        "encoding": encoding, "is_bigendian": bool(get(message, "is_bigendian")),
        "raw_data": data, "metadata": deepcopy(metadata or {})})


def depth_image(message, identity, *, depth_scale_m, minimum_m=.1, maximum_m=10., metadata=None):
    header_matches(message, identity)
    width, height, step = (get(message, k) for k in ("width", "height", "step"))
    encoding = get(message, "encoding")
    if encoding not in ("16UC1", "32FC1"):
        raise ValueError("DEPTH_ENCODING_UNSUPPORTED")
    unit, size = ("H", 2) if encoding == "16UC1" else ("f", 4)
    scale, lower, upper = finite((depth_scale_m, minimum_m, maximum_m))
    if scale <= 0 or lower < 0 or lower >= upper or (encoding == "32FC1" and scale != 1.):
        raise ValueError("DEPTH_UNITS_INVALID")
    data = bytes(get(message, "data"))
    if (any(type(v) is not int for v in (width, height, step)) or width < 1 or height < 1
            or width * height > MAX_POINTS or step < width * size
            or len(data) != height * step or len(data) > MAX_BYTES):
        raise ValueError("DEPTH_LAYOUT_INVALID")
    big = bool(get(message, "is_bigendian"))
    reader = struct.Struct((">" if big else "<") + unit)
    values = []
    for y in range(height):
        for x in range(width):
            value = reader.unpack_from(data, y * step + x * size)[0] * scale
            values.append(value if math.isfinite(value) and lower <= value <= upper else None)
    return Sample(identity, "Image/depth", {"depth_m": tuple(values), "width": width, "height": height,
        "encoding": encoding, "depth_scale_m": scale, "step": step, "is_bigendian": big,
        "raw_data": data, "metadata": deepcopy(metadata or {})}, diagnostics=("GEOMETRY_REQUIRES_D2_CALIBRATION",))


def detections(message, identity, *, metadata):
    """Detector-native boxes/class/preprocess metadata; no image-to-3D guessing."""
    header_matches(message, identity)
    items = deepcopy(get(message, "detections"))
    if len(items) > 256:
        raise ValueError("DETECTION_LIMIT")
    return Sample(identity, "detections", {"detections": items, "metadata": deepcopy(metadata),
                  "geometry_available": False}, diagnostics=("geometry_unavailable",))


def alignment_status(color: Sample, depth: Sample):
    """Permit same-pixel pairing only on owner-attested actual aligned profiles.

    Cross-device calibrated reprojection is D2's responsibility. Even attested
    metadata does not prove physical calibration accuracy.
    """
    c, d = color.payload, depth.payload.get("metadata", {})
    if color.identity.clock_domain != depth.identity.clock_domain or color.identity.clock_domain == "unknown":
        return "geometry_unavailable:CLOCK_UNKNOWN"
    if color.identity.binding != depth.identity.binding or color.identity.source_epoch != depth.identity.source_epoch:
        return "geometry_unavailable:EPOCH_MISMATCH"
    required = (c.get("device_id"), c.get("profile_id"), c.get("calibration_id"))
    if not all(required) or (d.get("device_id"), d.get("aligned_to_profile"), d.get("calibration_id")) != required:
        return "geometry_unavailable:CALIBRATION_OR_DEVICE_MISMATCH"
    if (d.get("alignment_verified") is not True or not d.get("depth_profile_id")
            or (c["width"], c["height"]) != (depth.payload["width"], depth.payload["height"])
            or color.identity.stamp_ns != depth.identity.stamp_ns):
        return "geometry_unavailable:PROFILE_OR_TIME_MISMATCH"
    return "ALIGNED_METADATA_ATTESTED"


def pose(message, identity, *, transform=False):
    header_matches(message, identity)
    value = get(message, "transform" if transform else "pose")
    p = get(value, "translation" if transform else "position")
    q = get(value, "rotation" if transform else "orientation")
    position = finite(get(p, k) for k in ("x", "y", "z"))
    rotation = finite(get(q, k) for k in ("x", "y", "z", "w"))
    if abs(sum(v*v for v in rotation) - 1.) > 1e-5:
        raise ValueError("QUATERNION_INVALID")
    payload = {"position_m": position, "orientation_xyzw": rotation}
    if transform:
        payload["child_frame_id"] = get(message, "child_frame_id")
    return Sample(identity, "TransformStamped" if transform else "PoseStamped", payload)


def joints(message, identity):
    header_matches(message, identity)
    names = tuple(get(message, "name"))
    if len(names) > 128 or len(set(names)) != len(names):
        raise ValueError("JOINT_NAMES_INVALID")
    payload = {k: finite(get(message, k)) for k in ("position", "velocity", "effort")}
    if any(len(v) not in (0, len(names)) for v in payload.values()):
        raise ValueError("JOINT_LAYOUT_INVALID")
    return Sample(identity, "JointState", dict(payload, name=names))
