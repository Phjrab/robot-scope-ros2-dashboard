"""Compact binary frames for low-latency browser point-cloud streaming."""

from __future__ import annotations

import json
import struct
from typing import Any, Mapping


MAGIC = b"RSPC"
VERSION = 1
HEADER = struct.Struct("<4sBBHII")
MAX_METADATA_BYTES = 16_384
MAX_POINT_BYTES = 12_000_000  # one million XYZ float32 points


class PointCloudFrameError(ValueError):
    """Raised when a point-cloud frame violates the bounded wire contract."""


def encode_pointcloud_frame(metadata: Mapping[str, Any], point_bytes: bytes) -> bytes:
    """Encode metadata plus little-endian packed XYZ float32 values.

    The small JSON metadata block keeps the protocol extensible while the
    point payload avoids Python-float JSON materialization and browser JSON
    parsing.  Metadata is padded to four bytes so JavaScript can create a
    zero-copy ``Float32Array`` over the payload.
    """

    if not isinstance(point_bytes, bytes):
        raise PointCloudFrameError("point payload must be immutable bytes")
    if len(point_bytes) % 12:
        raise PointCloudFrameError("point payload must contain packed XYZ float32 triples")
    if len(point_bytes) > MAX_POINT_BYTES:
        raise PointCloudFrameError("point payload exceeds the one-million-point limit")

    point_count = len(point_bytes) // 12
    public_metadata = dict(metadata)
    public_metadata.pop("points", None)
    public_metadata.pop("points_bytes", None)
    public_metadata.update(
        {
            "encoding": "float32le",
            "point_count": point_count,
            "stream_protocol": "robot-scope-pointcloud-v1",
            "prevalidated": True,
        }
    )
    try:
        encoded_metadata = json.dumps(
            public_metadata,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PointCloudFrameError(f"point-cloud metadata is not valid JSON: {exc}") from exc
    if not encoded_metadata or len(encoded_metadata) > MAX_METADATA_BYTES:
        raise PointCloudFrameError("point-cloud metadata exceeds the bounded frame header")

    padding = (-len(encoded_metadata)) & 3
    header = HEADER.pack(
        MAGIC,
        VERSION,
        0,
        len(encoded_metadata),
        point_count,
        len(point_bytes),
    )
    return b"".join((header, encoded_metadata, b"\0" * padding, point_bytes))


def decode_pointcloud_frame(frame: bytes) -> tuple[dict[str, Any], bytes]:
    """Strict decoder used by tests and diagnostics."""

    if not isinstance(frame, bytes) or len(frame) < HEADER.size:
        raise PointCloudFrameError("point-cloud frame is truncated")
    magic, version, flags, metadata_size, point_count, point_size = HEADER.unpack_from(frame)
    if magic != MAGIC or version != VERSION or flags != 0:
        raise PointCloudFrameError("unsupported point-cloud frame header")
    if not 0 < metadata_size <= MAX_METADATA_BYTES:
        raise PointCloudFrameError("invalid point-cloud metadata length")
    if point_size != point_count * 12 or point_size > MAX_POINT_BYTES:
        raise PointCloudFrameError("invalid point-cloud payload length")
    payload_offset = (HEADER.size + metadata_size + 3) & ~3
    if len(frame) != payload_offset + point_size:
        raise PointCloudFrameError("point-cloud frame length does not match its header")
    try:
        metadata = json.loads(frame[HEADER.size : HEADER.size + metadata_size])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PointCloudFrameError("invalid point-cloud metadata JSON") from exc
    if not isinstance(metadata, dict):
        raise PointCloudFrameError("point-cloud metadata must be an object")
    if metadata.get("point_count") != point_count or metadata.get("encoding") != "float32le":
        raise PointCloudFrameError("point-cloud metadata does not match the binary payload")
    return metadata, frame[payload_offset:]
