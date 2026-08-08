"""Bounded, zero-copy-friendly PointCloud2 XYZ extraction helpers."""

from __future__ import annotations

import math
from typing import Any, Tuple

import numpy as np


_POINT_FIELD_DTYPES = {
    1: "i1",   # INT8
    2: "u1",   # UINT8
    3: "i2",   # INT16
    4: "u2",   # UINT16
    5: "i4",   # INT32
    6: "u4",   # UINT32
    7: "f4",   # FLOAT32
    8: "f8",   # FLOAT64
}


def extract_xyz(message: Any, max_points: int) -> Tuple[np.ndarray, int]:
    """Return at most ``max_points`` finite XYZ rows and the source point count.

    Unlike ``sensor_msgs_py.read_points()``, this samples before materializing an
    accumulated map, which keeps a growing ``/Laser_map`` bounded in memory.
    """

    width = int(getattr(message, "width", 0))
    height = int(getattr(message, "height", 0))
    point_step = int(getattr(message, "point_step", 0))
    row_step = int(getattr(message, "row_step", 0)) or width * point_step
    source_points = width * height
    if width <= 0 or height <= 0 or source_points <= 0 or point_step <= 0:
        return np.empty((0, 3), dtype=np.float32), 0
    if row_step < width * point_step:
        raise ValueError(
            f"PointCloud2 row_step is smaller than its packed row: "
            f"{row_step} < {width * point_step}"
        )

    fields = {str(field.name): field for field in getattr(message, "fields", [])}
    if any(name not in fields for name in ("x", "y", "z")):
        raise ValueError("PointCloud2 requires x, y and z fields")

    endian = ">" if bool(getattr(message, "is_bigendian", False)) else "<"
    formats = []
    offsets = []
    for name in ("x", "y", "z"):
        field = fields[name]
        kind = _POINT_FIELD_DTYPES.get(int(field.datatype))
        if not kind:
            raise ValueError(f"unsupported PointField datatype for {name}: {field.datatype}")
        formats.append(kind if kind.endswith("1") else endian + kind)
        offsets.append(int(field.offset))

    dtype = np.dtype({
        "names": ["x", "y", "z"],
        "formats": formats,
        "offsets": offsets,
        "itemsize": point_step,
    })
    required_bytes = (height - 1) * row_step + width * point_step
    payload = memoryview(getattr(message, "data", b""))
    if len(payload) < required_bytes:
        raise ValueError(f"PointCloud2 payload is truncated: {len(payload)} < {required_bytes}")

    cloud = np.ndarray(
        shape=(height, width),
        dtype=dtype,
        buffer=payload,
        strides=(row_step, point_step),
    )
    stride = max(1, int(math.ceil(source_points / max(1, int(max_points)))))
    indexes = np.arange(0, source_points, stride, dtype=np.int64)
    sampled = cloud[indexes // width, indexes % width]
    xyz = np.column_stack((sampled["x"], sampled["y"], sampled["z"])).astype(np.float32, copy=False)
    return xyz[np.isfinite(xyz).all(axis=1)], source_points


def reject_spatial_outliers(points: np.ndarray, max_radius: float = 500.0) -> np.ndarray:
    """Remove catastrophic SLAM outliers around a robust cloud center.

    FAST-LIO can briefly emit numerically invalid but finite coordinates while
    a sensor powers down.  A median-centered radius prevents a single frame
    from making the 3D viewport span hundreds of kilometres.
    """

    if len(points) < 64:
        return points
    center = np.median(points, axis=0)
    distances = np.linalg.norm(points - center, axis=1)
    robust_radius = float(np.quantile(distances, 0.98))
    limit = max(5.0, min(float(max_radius), robust_radius * 2.0))
    filtered = points[distances <= limit]
    return filtered if len(filtered) >= 64 else points
