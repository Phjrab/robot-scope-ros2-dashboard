"""Bounded binary PCD filtering that copies complete original point records.

Only DATA binary (little-endian, as used by the existing catalogue) is
supported. The caller owns source snapshotting, provenance and registration.
"""

import hashlib
import os
from pathlib import Path
import re
import stat

import numpy as np

from .geometry import PcdEditError, _compile_region, _selection_mask, validate_regions


DEFAULT_MAX_POINTS = 20_000_000
DEFAULT_MAX_BYTES = 256 * 1024 ** 2
MAX_HEADER_BYTES = 64 * 1024
MAX_RECORD_BYTES = 64 * 1024
MAX_CHUNK_BYTES = 8 * 1024 * 1024
_FIELD_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_UNSIGNED = re.compile(r"[0-9]{1,20}\Z")


def _positive(value, label):
    if type(value) is not int or value <= 0:
        raise PcdEditError(f"{label} must be a positive integer")
    return value


def _integer(values, label, *, positive=False):
    if len(values) != 1 or not _UNSIGNED.fullmatch(values[0]):
        raise PcdEditError(f"PCD {label} must be one nonnegative integer")
    value = int(values[0])
    if positive and value == 0:
        raise PcdEditError(f"PCD {label} must be positive")
    return value


def _read_header(stream, file_size, max_points):
    lines, metadata, header_bytes = [], {}, bytearray()
    allowed = {"VERSION", "FIELDS", "SIZE", "TYPE", "COUNT", "WIDTH", "HEIGHT", "VIEWPOINT", "POINTS", "DATA"}
    while True:
        line = stream.readline(MAX_HEADER_BYTES + 1)
        if not line or len(header_bytes) + len(line) > MAX_HEADER_BYTES:
            raise PcdEditError("PCD header is missing DATA or exceeds the header limit")
        header_bytes.extend(line)
        try:
            text = line.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise PcdEditError("PCD header must be ASCII") from exc
        if not text or text.startswith("#"):
            lines.append((None, line))
            continue
        tokens = text.split()
        key, values = tokens[0].upper(), tokens[1:]
        if key not in allowed or key in metadata or not values:
            raise PcdEditError("PCD has an unsupported, repeated, or empty header field")
        metadata[key] = values
        lines.append((key, line))
        if key == "DATA":
            if len(values) != 1 or values[0].lower() != "binary":
                raise PcdEditError("Only DATA binary PCD is supported")
            break
    required = {"FIELDS", "SIZE", "TYPE", "WIDTH", "HEIGHT", "POINTS", "DATA"}
    if not required <= metadata.keys():
        raise PcdEditError("PCD header is missing required fields")
    if "VERSION" in metadata and metadata["VERSION"] not in (["0.7"], [".7"]):
        raise PcdEditError("Only PCD VERSION 0.7 is supported")
    fields = metadata["FIELDS"]
    if len(fields) > 256 or len(fields) != len(set(fields)) or any(not _FIELD_NAME.fullmatch(name) for name in fields):
        raise PcdEditError("PCD FIELDS must contain at most 256 unique field names")
    if not {"x", "y", "z"} <= set(fields):
        raise PcdEditError("PCD requires x, y and z fields")
    sizes, types = metadata["SIZE"], metadata["TYPE"]
    counts = metadata.get("COUNT", ["1"] * len(fields))
    if not len(fields) == len(sizes) == len(types) == len(counts):
        raise PcdEditError("PCD FIELDS, SIZE, TYPE and COUNT lengths must agree")
    descriptors, field_info, record_bytes = [], [], 0
    for name, size_text, kind, count_text in zip(fields, sizes, types, counts):
        size = _integer([size_text], "SIZE", positive=True)
        count = _integer([count_text], "COUNT", positive=True)
        if kind not in ("F", "I", "U") or size not in ((4, 8) if kind == "F" else (1, 2, 4, 8)):
            raise PcdEditError("PCD has an unsupported field TYPE/SIZE combination")
        if name in ("x", "y", "z") and count != 1:
            raise PcdEditError("PCD x, y and z must each have COUNT 1")
        record_bytes += size * count
        if record_bytes > MAX_RECORD_BYTES:
            raise PcdEditError("PCD point record exceeds the size limit")
        dtype = np.dtype(f"<{ {'F': 'f', 'I': 'i', 'U': 'u'}[kind]}{size}")
        descriptors.append((name, dtype) if count == 1 else (name, dtype, (count,)))
        field_info.append({"name": name, "size": size, "type": kind, "count": count})
    width = _integer(metadata["WIDTH"], "WIDTH", positive=True)
    height = _integer(metadata["HEIGHT"], "HEIGHT", positive=True)
    points = _integer(metadata["POINTS"], "POINTS", positive=True)
    if points != width * height:
        raise PcdEditError("PCD POINTS must equal WIDTH times HEIGHT")
    if points > max_points:
        raise PcdEditError("PCD exceeds the point limit")
    if "VIEWPOINT" in metadata:
        try:
            viewpoint = np.array(metadata["VIEWPOINT"], dtype=np.float64)
        except (ValueError, OverflowError) as exc:
            raise PcdEditError("PCD VIEWPOINT must contain seven finite numbers") from exc
        if len(viewpoint) != 7 or not np.all(np.isfinite(viewpoint)):
            raise PcdEditError("PCD VIEWPOINT must contain seven finite numbers")
    if points * record_bytes != file_size - len(header_bytes):
        raise PcdEditError("PCD binary payload length does not match POINTS and field layout")
    return lines, bytes(header_bytes), np.dtype(descriptors), points, field_info


def _output_header(lines, points):
    # Fixed width lets us update counts after streaming without buffering points.
    counts = {"WIDTH": points, "HEIGHT": 1, "POINTS": points}
    return b"".join(
        f"{key} {counts[key]:<20d}\n".encode("ascii") if key in counts else raw
        for key, raw in lines
    )


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def filter_pcd(source: Path, target: Path, regions: list, purpose: str, *,
               max_points=DEFAULT_MAX_POINTS, max_bytes=DEFAULT_MAX_BYTES, chunk_points=65536) -> dict:
    """Remove the union of regions of one purpose from an entire binary PCD.

    Nonfinite XYZ records survive byte-for-byte. All other fields, their COUNT
    values, field order, and VIEWPOINT survive unchanged. The resulting cloud
    is unorganized (HEIGHT 1). Output creation is exclusive; failures remove
    only the output created by this invocation. No source bytes are written.
    """
    if purpose not in ("visibility", "localization"):
        raise PcdEditError("Edited copy purpose must be visibility or localization")
    normalized = validate_regions(regions)
    selected = [_compile_region(region) for region in normalized if region["kind"] == purpose]
    _positive(max_points, "max_points")
    _positive(max_bytes, "max_bytes")
    _positive(chunk_points, "chunk_points")
    source, target = Path(source), Path(target)
    created_identity = None
    try:
        with source.open("rb") as original:
            initial = os.fstat(original.fileno())
            if not stat.S_ISREG(initial.st_mode):
                raise PcdEditError("PCD source must be a regular file")
            if initial.st_size > max_bytes:
                raise PcdEditError("PCD exceeds the byte limit")
            lines, header, dtype, source_points, fields = _read_header(original, initial.st_size, max_points)
            source_hash = hashlib.sha256(header)
            try:
                output = target.open("x+b")
            except FileExistsError as exc:
                raise PcdEditError("Output path already exists") from exc
            with output:
                created_identity = os.fstat(output.fileno())
                output.write(_output_header(lines, 0))
                output_points = 0
                nonfinite_points = 0
                bounded_chunk = min(chunk_points, max(1, MAX_CHUNK_BYTES // dtype.itemsize))
                for start in range(0, source_points, bounded_chunk):
                    count = min(bounded_chunk, source_points - start)
                    payload = original.read(count * dtype.itemsize)
                    if len(payload) != count * dtype.itemsize:
                        raise PcdEditError("PCD source changed or has a truncated payload")
                    source_hash.update(payload)
                    records = np.frombuffer(payload, dtype=dtype, count=count)
                    x, y, z = records["x"], records["y"], records["z"]
                    finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
                    nonfinite_points += int(count - np.count_nonzero(finite))
                    remove = np.zeros(count, dtype=bool)
                    indices = np.flatnonzero(finite)
                    if len(indices):
                        finite_x, finite_y, finite_z = x[indices], y[indices], z[indices]
                        for region in selected:
                            remove[indices] |= _selection_mask(finite_x, finite_y, finite_z, region)
                    keep = ~remove
                    output_points += int(np.count_nonzero(keep))
                    # Copy raw records, including NaN payloads, integer fields,
                    # packed RGB, and multi-count descriptors without casting.
                    raw_records = np.frombuffer(payload, dtype=np.uint8).reshape(count, dtype.itemsize)
                    output.write(raw_records[keep].tobytes())
                if original.read(1) or _identity(os.fstat(original.fileno())) != _identity(initial):
                    raise PcdEditError("PCD source changed during filtering")
                if not output_points:
                    raise PcdEditError("Edited PCD would contain no points")
                output.seek(0)
                output.write(_output_header(lines, output_points))
                output.flush()
                if os.fstat(output.fileno()).st_size > max_bytes:
                    raise PcdEditError("Edited PCD exceeds the byte limit")
                os.fsync(output.fileno())
                output.seek(0)
                output_hash = hashlib.sha256()
                while block := output.read(MAX_CHUNK_BYTES):
                    output_hash.update(block)
                return {
                    "source_points": source_points,
                    "output_points": output_points,
                    "removed_points": source_points - output_points,
                    "nonfinite_points_preserved": nonfinite_points,
                    "fields": fields,
                    "source_sha256": source_hash.hexdigest(),
                    "output_sha256": output_hash.hexdigest(),
                }
    except BaseException as exc:
        if created_identity is not None:
            try:
                current = target.lstat()
                if (current.st_dev, current.st_ino) == (created_identity.st_dev, created_identity.st_ino):
                    target.unlink()
            except OSError:
                pass
        if isinstance(exc, OSError):
            raise PcdEditError(f"Unable to read or write PCD: {exc.strerror or type(exc).__name__}") from exc
        raise
