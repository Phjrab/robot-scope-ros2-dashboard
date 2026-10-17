"""Private atomic SDK depth evidence; no camera, ROS, alignment or path APIs.

The installation chooses the root. Callers retrieve immutable samples only by
opaque UUID hex. Native IR/depth bytes and actual SDK metadata are preserved;
compatibility is an additional, fail-closed mathematical pinhole verification.
"""
from __future__ import annotations

import array
from functools import wraps
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import sys
import tempfile
import threading
import uuid
import zipfile
import zlib


SCHEMA = "robot-scope.depth-capture.v1"
MAX_PIXELS = 1920 * 1080
MAX_RAW_BYTES = 16 * 1024**2
MAX_METADATA_BYTES = 1024**2
MAX_SAMPLE_BYTES = 64 * 1024**2
MAX_SKEW_MS = 1.0
ID_RE = re.compile(r"^[0-9a-f]{32}$")
FILES = frozenset({"ir1.y8", "depth.z16", "click.png", "depth.png", "metadata.json",
                   "camera_info.json", "compatibility.json"})


class DepthCaptureError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status


def _fail(code, message, status=400):
    raise DepthCaptureError(code, message, status)


def _io_safe(method):
    @wraps(method)
    def call(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except OSError:
            _fail("DEPTH_CAPTURE_IO_ERROR", "Private capture storage operation failed.", 503)
    return call


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _json(value, limit=MAX_METADATA_BYTES):
    count = 0

    def check(item, depth=0):
        nonlocal count
        count += 1
        if depth > 12 or count > 30_000:
            _fail("INVALID_CAPTURE_METADATA", "Capture metadata is too complex.")
        if item is None or type(item) is bool:
            return
        if type(item) in (int, float):
            if not _finite(item) or abs(item) > 2**64:
                _fail("INVALID_CAPTURE_METADATA", "Capture metadata must contain finite bounded numbers.")
        elif isinstance(item, str):
            if len(item) > 4096 or "\x00" in item:
                _fail("INVALID_CAPTURE_METADATA", "Capture metadata string is invalid.")
        elif isinstance(item, dict):
            if len(item) > 512 or any(not isinstance(k, str) or not k or len(k) > 128 for k in item):
                _fail("INVALID_CAPTURE_METADATA", "Capture metadata keys are invalid.")
            for child in item.values():
                check(child, depth+1)
        elif isinstance(item, list):
            if len(item) > 4096:
                _fail("INVALID_CAPTURE_METADATA", "Capture metadata list is too large.")
            for child in item:
                check(child, depth+1)
        else:
            _fail("INVALID_CAPTURE_METADATA", "Capture metadata must be JSON data.")
    # Compatibility depth_m intentionally exceeds metadata's item-count limit.
    if limit == MAX_METADATA_BYTES:
        check(value)
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()
    except (ValueError, TypeError, RecursionError, OverflowError):
        _fail("INVALID_CAPTURE_METADATA", "Capture metadata is invalid.")
    if len(raw) > limit:
        _fail("CAPTURE_SIZE_LIMIT", "Capture data exceeds the storage limit.", 413)
    return raw


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _enum(value):
    return value.lower().rsplit(".", 1)[-1] if isinstance(value, str) else None


def _shape(frame, raw, bpp):
    width, height, stride = (frame.get(k) for k in ("width", "height", "stride_bytes"))
    return (all(type(v) is int for v in (width, height, stride)) and 0 < width <= 1920 and 0 < height <= 1080
            and width*height <= MAX_PIXELS and width*bpp <= stride <= width*bpp+4096
            and len(raw) == stride*height)


def _png(frame, raw, bpp):
    if not _shape(frame, raw, bpp) or _enum(frame.get("format")) != ("y8" if bpp == 1 else "z16"):
        return None
    rows = bytearray()
    for y in range(frame["height"]):
        row = raw[y*frame["stride_bytes"]:y*frame["stride_bytes"]+frame["width"]*bpp]
        if bpp == 2:
            if frame.get("byte_order") not in {"little", "big"}:
                return None
            if frame["byte_order"] == "little":
                swapped = bytearray(row)
                swapped[0::2], swapped[1::2] = row[1::2], row[0::2]
                row = swapped
        rows.append(0)  # lossless PNG filter: None
        rows.extend(row)

    def chunk(kind, payload):
        return struct.pack(">I", len(payload))+kind+payload+struct.pack(">I", zlib.crc32(kind+payload)&0xffffffff)
    header = struct.pack(">IIBBBBB", frame["width"], frame["height"], bpp*8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR", header)+chunk(b"IDAT", zlib.compress(rows))+chunk(b"IEND", b"")


def _intrinsics(frame):
    value = _mapping(frame.get("intrinsics"))
    if (any(type(frame.get(k)) is not int or frame[k] <= 0 for k in ("width", "height"))
            or value.get("width") != frame.get("width") or value.get("height") != frame.get("height")
            or any(not _finite(value.get(k)) for k in ("fx", "fy", "ppx", "ppy"))
            or value["fx"] <= 0 or value["fy"] <= 0
            or not 0 <= value["ppx"] < frame["width"] or not 0 <= value["ppy"] < frame["height"]):
        return None
    return value


def _camera_info(frame):
    intrinsics = _intrinsics(frame)
    return {"source": "derived_from_actual_sdk_intrinsics_not_a_ros_topic", "frame_id": frame.get("frame_id"),
            "frame_id_source": frame.get("frame_id_source"), "width": frame.get("width"), "height": frame.get("height"),
            "timestamp_ms": frame.get("timestamp_ms"), "timestamp_domain": frame.get("timestamp_domain"),
            "sdk_intrinsics": frame.get("intrinsics"),
            "k": [intrinsics["fx"], 0, intrinsics["ppx"], 0, intrinsics["fy"], intrinsics["ppy"], 0, 0, 1]
            if intrinsics else None,
            "d": intrinsics.get("coeffs") if intrinsics else None,
            "r": None, "p": None, "note": "No ROS CameraInfo message or rectification matrix was observed."}


def _valid_depth_ratio(frame, raw):
    """Count nonzero raw Z16 pixels, excluding row padding; no geometry claim."""
    if (raw is None or not _shape(frame, raw, 2) or _enum(frame.get("format")) != "z16"
            or frame.get("byte_order") not in {"little", "big"}):
        return None
    valid = 0
    for y in range(frame["height"]):
        row = raw[y*frame["stride_bytes"]:y*frame["stride_bytes"]+frame["width"]*2]
        valid += sum(row[x] != 0 or row[x+1] != 0 for x in range(0, len(row), 2))
    return valid / (frame["width"]*frame["height"])


def _source_skew_ms(ir, depth):
    domain = ir.get("timestamp_domain")
    if (_enum(domain) not in {"hardware_clock", "system_time", "global_time"}
            or domain != depth.get("timestamp_domain")
            or not all(_finite(frame.get("timestamp_ms")) and frame["timestamp_ms"] >= 0 for frame in (ir, depth))):
        return None
    return abs(ir["timestamp_ms"]-depth["timestamp_ms"])


def _compatibility(capture, ir, depth, ir_raw, depth_raw):
    if depth_raw is None:
        return "DEPTH_MISSING", None
    if not _shape(ir, ir_raw, 1) or not _shape(depth, depth_raw, 2):
        return "FRAME_LAYOUT_MISMATCH", None
    if _enum(ir.get("format")) != "y8" or _enum(depth.get("format")) != "z16" or depth.get("byte_order") not in {"little", "big"}:
        return "RAW_FORMAT_UNVERIFIED", None
    profiles = [_mapping(frame.get("profile")) for frame in (ir, depth)]
    for frame, profile, stream, index in zip((ir, depth), profiles, ("infrared", "depth"), (1, 0)):
        if (profile.get("width") != frame["width"] or profile.get("height") != frame["height"]
                or any(type(profile.get(k)) is not int for k in ("width", "height", "index"))
                or type(profile.get("fps")) is not int or not 0 < profile["fps"] <= 120
                or _enum(profile.get("format")) != _enum(frame.get("format"))
                or _enum(profile.get("stream")) != stream or profile.get("index") != index):
            return "PROFILE_UNVERIFIED", None
        if (not isinstance(frame.get("frame_id"), str) or not frame["frame_id"]
                or frame.get("frame_id_source") != "sdk_logical_optical_not_ros_tf"):
            return "OPTICAL_FRAME_UNVERIFIED", None
    if (ir["width"] != depth["width"] or ir["height"] != depth["height"]
            or profiles[0]["fps"] != profiles[1]["fps"]):
        return "PROFILE_MISMATCH", None
    pair = _mapping(capture.get("frameset"))
    if (pair.get("verified") is not True or any(type(frame.get("frame_number")) is not int or frame["frame_number"] < 0 for frame in (ir, depth))
            or pair.get("ir_frame_number") != ir["frame_number"] or pair.get("depth_frame_number") != depth["frame_number"]):
        return "FRAMESET_UNVERIFIED", None
    domain = ir.get("timestamp_domain")
    if (_enum(domain) not in {"hardware_clock", "system_time", "global_time"} or domain != depth.get("timestamp_domain")
            or not all(_finite(frame.get("timestamp_ms")) and frame["timestamp_ms"] >= 0 for frame in (ir, depth))):
        return "TIMESTAMP_UNVERIFIED", None
    skew = abs(ir["timestamp_ms"]-depth["timestamp_ms"])
    if skew > MAX_SKEW_MS:
        return "TIMESTAMP_SKEW", None
    a, b = _intrinsics(ir), _intrinsics(depth)
    if a is None or b is None:
        return "INTRINSICS_INVALID", None
    for intrinsics in (a, b):
        coeffs = intrinsics.get("coeffs")
        if (_enum(intrinsics.get("model")) not in {"none", "brown_conrady"}
                or not isinstance(coeffs, list) or len(coeffs) != 5
                or any(not _finite(v) or v != 0 for v in coeffs)):
            return "DISTORTION_NOT_PINHOLE", None
    if any(not math.isclose(a[k], b[k], rel_tol=1e-9, abs_tol=1e-9) for k in ("fx", "fy", "ppx", "ppy")):
        return "INTRINSICS_MISMATCH", None
    extrinsics = _mapping(_mapping(capture.get("extrinsics")).get("depth_to_ir1"))
    rotation, translation = extrinsics.get("rotation"), extrinsics.get("translation")
    if (not isinstance(rotation, list) or len(rotation) != 9 or not isinstance(translation, list) or len(translation) != 3
            or any(not _finite(v) for v in rotation+translation)
            or any(abs(v-expected) > 1e-8 for v, expected in zip(rotation, (1, 0, 0, 0, 1, 0, 0, 0, 1)))
            or any(abs(v) > 1e-8 for v in translation)):
        return "DEPTH_TO_IR_NOT_IDENTITY", None
    scale = capture.get("depth_scale_m")
    device = _mapping(capture.get("device"))
    serial = device.get("serial_number", device.get("serial"))
    if not _finite(scale) or not 0 < scale <= 1:
        return "DEPTH_SCALE_INVALID", None
    if not isinstance(serial, str) or not serial:
        return "DEVICE_UNVERIFIED", None
    values = []
    for y in range(depth["height"]):
        row = depth_raw[y*depth["stride_bytes"]:y*depth["stride_bytes"]+depth["width"]*2]
        numbers = array.array("H")
        numbers.frombytes(row)
        if sys.byteorder != depth["byte_order"]:
            numbers.byteswap()
        values.extend(None if number == 0 else number*scale for number in numbers)
    return None, {"width": ir["width"], "height": ir["height"],
        "intrinsics": {"fx": a["fx"], "fy": a["fy"], "cx": a["ppx"], "cy": a["ppy"]},
        "depth_m": values, "points": [], "metadata": {"serial": serial, "frame_id": ir["frame_id"],
            "frame_id_source": ir["frame_id_source"], "profile_id": hashlib.sha256(_json(profiles)).hexdigest(),
            "rectified": True, "synthetic": False, "depth_semantics": "optical_z", "click_image_file": "click.png",
            "rectification_basis": "actual_zero_distortion_intrinsics_and_identity_depth_to_ir1_no_resampling",
            "source_timestamps_ms": {"ir1": ir["timestamp_ms"], "depth": depth["timestamp_ms"]},
            "timestamp_domain": domain, "frame_numbers": {"ir1": ir["frame_number"], "depth": depth["frame_number"]},
            "alignment": {"frameset_verified": True, "source_skew_ms": skew, "max_source_skew_ms": MAX_SKEW_MS,
                "depth_to_ir1": extrinsics, "ir1_intrinsics": a, "depth_intrinsics": b,
                "intrinsics_relative_tolerance": 1e-9, "extrinsics_absolute_tolerance": 1e-8}}}


class DepthCaptureStore:
    @_io_safe
    def __init__(self, root: Path, *, minimum_free_bytes=64*1024**2, max_samples=64, max_total_bytes=1024**3):
        if any(type(v) is not int or v < (0 if i == 0 else 1) for i, v in enumerate((minimum_free_bytes, max_samples, max_total_bytes))):
            _fail("INVALID_STORE_LIMIT", "Capture storage limits are invalid.")
        self.root = Path(os.path.abspath(root))
        for path in reversed((self.root, *self.root.parents)):
            if path.is_symlink():
                _fail("UNSAFE_CAPTURE_ROOT", "Capture root must not traverse symbolic links.")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._identity = (self.root.stat().st_dev, self.root.stat().st_ino)
        self.minimum_free_bytes, self.max_samples, self.max_total_bytes = minimum_free_bytes, max_samples, max_total_bytes
        self._lock = threading.RLock()
        self._check_root()

    def _check_root(self):
        if any(path.is_symlink() for path in (self.root, *self.root.parents)):
            _fail("UNSAFE_CAPTURE_ROOT", "Capture root must not traverse symbolic links.")
        value = self.root.lstat()
        if (not stat.S_ISDIR(value.st_mode) or value.st_uid != os.geteuid() or stat.S_IMODE(value.st_mode)&0o077
                or (value.st_dev, value.st_ino) != self._identity):
            _fail("UNSAFE_CAPTURE_ROOT", "Capture root must remain a private real directory.")

    def _sample(self, sample_id):
        if not isinstance(sample_id, str) or ID_RE.fullmatch(sample_id) is None:
            _fail("INVALID_SAMPLE_ID", "Sample ID must be an opaque UUID.")
        self._check_root()
        path = self.root/sample_id
        try:
            value = path.lstat()
        except FileNotFoundError:
            _fail("SAMPLE_NOT_FOUND", "Capture sample was not found.", 404)
        if not stat.S_ISDIR(value.st_mode) or value.st_uid != os.geteuid() or stat.S_IMODE(value.st_mode)&0o077:
            _fail("UNSAFE_CAPTURE_SAMPLE", "Capture sample is not a private real directory.")
        return path

    @staticmethod
    def _write(path, payload):
        fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _read(path, limit):
        directory = os.open(path.parent, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            fd = os.open(path.name, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK, dir_fd=directory)
        finally:
            os.close(directory)
        with os.fdopen(fd, "rb") as stream:
            value = os.fstat(stream.fileno())
            if (not stat.S_ISREG(value.st_mode) or value.st_nlink != 1 or value.st_uid != os.geteuid()
                    or stat.S_IMODE(value.st_mode)&0o077 or value.st_size > limit):
                _fail("UNSAFE_CAPTURE_FILE", "Capture file is unsafe or too large.")
            raw = stream.read(limit+1)
            if len(raw) > limit:
                _fail("CAPTURE_SIZE_LIMIT", "Capture data exceeds the storage limit.", 413)
            return raw

    def _manifest(self, path):
        try:
            value = json.loads(self._read(path/"manifest.json", MAX_METADATA_BYTES),
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError, RecursionError):
            _fail("INVALID_CAPTURE_SAMPLE", "Capture manifest is invalid.")
        if not isinstance(value, dict):
            _fail("INVALID_CAPTURE_SAMPLE", "Capture manifest is invalid.")
        files = _mapping(value.get("files"))
        if (value.get("schema") != SCHEMA or value.get("sample_id") != path.name or not files or set(files)-FILES
                or not isinstance(value.get("compatibility"), dict)
                or any(not isinstance(row, dict) or type(row.get("bytes")) is not int or not 0 <= row["bytes"] <= MAX_SAMPLE_BYTES
                       or re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256"))) is None for row in files.values())
                or sum(row["bytes"] for row in files.values()) > MAX_SAMPLE_BYTES):
            _fail("INVALID_CAPTURE_SAMPLE", "Capture manifest is invalid.")
        return value

    def _verified_file(self, path, manifest, name):
        row = manifest["files"].get(name)
        if row is None:
            _fail("CAPTURE_FILE_UNAVAILABLE", "Requested capture artifact is unavailable.", 409)
        raw = self._read(path/name, MAX_SAMPLE_BYTES)
        if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            _fail("CAPTURE_INTEGRITY_ERROR", "Capture artifact no longer matches the original receipt.", 409)
        return raw

    @_io_safe
    def save_sample(self, capture: dict):
        with self._lock:
            self._check_root()
            if not isinstance(capture, dict):
                _fail("INVALID_CAPTURE_METADATA", "Capture must be an SDK evidence bundle.")
            confirmation = _mapping(capture.get("confirmation"))
            if any(confirmation.get(key) is not True for key in ("robot_stationary", "camera_stationary", "robot_seated")):
                _fail("CAPTURE_CONFIRMATION_REQUIRED", "Current stationary and seated confirmations are required.", 409)
            frames = _mapping(capture.get("frames"))
            ir, depth = (_mapping(frames.get(key)) for key in ("ir1", "depth"))
            ir_raw, depth_raw = ir.get("data"), depth.get("data")
            if not isinstance(ir_raw, bytes) or not 0 < len(ir_raw) <= MAX_RAW_BYTES:
                _fail("IR_RAW_REQUIRED", "A bounded original IR1 Y8 byte frame is required.")
            if depth_raw is not None and (not isinstance(depth_raw, bytes) or not 0 < len(depth_raw) <= MAX_RAW_BYTES):
                _fail("DEPTH_RAW_INVALID", "Original depth bytes are invalid.")
            metadata = {k: v for k, v in capture.items() if k != "frames"}
            metadata["frames"] = {name: {k: v for k, v in frame.items() if k != "data"} for name, frame in (("ir1", ir), ("depth", depth))}
            metadata_raw = _json(metadata)  # deep validation/detachment before publication
            metadata = json.loads(metadata_raw)
            ir, depth = (metadata["frames"][name] for name in ("ir1", "depth"))
            reason, compatibility = _compatibility(metadata, ir, depth, ir_raw, depth_raw)
            sample_id = uuid.uuid4().hex
            valid_depth_ratio = _valid_depth_ratio(depth, depth_raw)
            source_skew_ms = _source_skew_ms(ir, depth)
            metadata.update(sample_id=sample_id, capture_session_id=metadata.get("session_id"), derived={
                "valid_depth_ratio": valid_depth_ratio,
                "valid_depth_ratio_basis": "nonzero_raw_z16_pixels_over_width_times_height_not_geometric_accuracy",
                "actual_source_skew_ms": source_skew_ms})
            metadata_raw = _json(metadata)
            artifacts = {"ir1.y8": ir_raw, "metadata.json": metadata_raw,
                         "camera_info.json": _json({"ir1": _camera_info(ir), "depth": _camera_info(depth)})}
            if depth_raw is not None:
                artifacts["depth.z16"] = depth_raw
            ir_png = _png(ir, ir_raw, 1)
            if ir_png is not None:
                artifacts["click.png"] = ir_png
            if depth_raw is not None:
                depth_png = _png(depth, depth_raw, 2)
                if depth_png is not None:
                    artifacts["depth.png"] = depth_png
            if compatibility is not None:
                compatibility["id"] = sample_id
                artifacts["compatibility.json"] = _json(compatibility, MAX_SAMPLE_BYTES)
            total = sum(map(len, artifacts.values()))
            if total > MAX_SAMPLE_BYTES:
                _fail("CAPTURE_SIZE_LIMIT", "Capture data exceeds the storage limit.", 413)
            existing = [p for p in self.root.iterdir() if ID_RE.fullmatch(p.name)]
            used = sum(p.stat(follow_symlinks=False).st_size for directory in existing if directory.is_dir() and not directory.is_symlink()
                       for p in directory.iterdir() if p.is_file() and not p.is_symlink())
            if len(existing) >= self.max_samples or used+total > self.max_total_bytes:
                _fail("CAPTURE_QUOTA_EXCEEDED", "Private capture storage quota was reached.", 409)
            if shutil.disk_usage(self.root).free < self.minimum_free_bytes+total+MAX_METADATA_BYTES:
                _fail("CAPTURE_STORAGE_FULL", "Private capture storage has insufficient free space.", 507)
            manifest = {"schema": SCHEMA, "sample_id": sample_id, "compatibility": {"available": compatibility is not None, "reason": reason},
                        "session_id": metadata.get("session_id"), "generation": metadata.get("generation"),
                        "captured_at_utc": metadata.get("captured_at_utc"),
                        "valid_depth_ratio": valid_depth_ratio, "actual_source_skew_ms": source_skew_ms,
                        "image": {"available": ir_png is not None,
                            **{key: ir.get(key) for key in ("width", "height", "frame_id", "frame_id_source", "timestamp_ms", "timestamp_domain", "frame_number")}},
                        "files": {name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} for name, raw in artifacts.items()},
                        "total_bytes": total, "synthetic": False}
            staging = Path(tempfile.mkdtemp(prefix=".pending-", dir=self.root))
            try:
                for name, raw in artifacts.items():
                    self._write(staging/name, raw)
                self._write(staging/"manifest.json", _json(manifest))
                fd = os.open(staging, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
                self._check_root()
                os.rename(staging, self.root/sample_id)
                fd = os.open(self.root, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
            return manifest

    @_io_safe
    def receipt(self, sample_id):
        with self._lock:
            return self._manifest(self._sample(sample_id))

    @_io_safe
    def list_samples(self):
        with self._lock:
            self._check_root()
            ids = sorted(p.name for p in self.root.iterdir() if ID_RE.fullmatch(p.name))
            if len(ids) > self.max_samples:
                _fail("CAPTURE_QUOTA_EXCEEDED", "Private capture storage quota was reached.", 409)
            return [self._manifest(self._sample(sample_id)) for sample_id in ids]

    @_io_safe
    def compatibility_json(self, sample_id):
        with self._lock:
            path = self._sample(sample_id)
            manifest = self._manifest(path)
            if manifest["compatibility"].get("available") is not True:
                _fail("COMPATIBILITY_UNAVAILABLE", "This sample preserves raw evidence only; compatibility is unavailable.", 409)
            return json.loads(self._verified_file(path, manifest, "compatibility.json"))

    @_io_safe
    def click_png(self, sample_id):
        with self._lock:
            path = self._sample(sample_id)
            return self._verified_file(path, self._manifest(path), "click.png")

    @_io_safe
    def export_zip(self, sample_id):
        with self._lock:
            path = self._sample(sample_id)
            manifest = self._manifest(path)
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("manifest.json", _json(manifest))
                for name in manifest["files"]:
                    archive.writestr(name, self._verified_file(path, manifest, name))
            return output.getvalue()
