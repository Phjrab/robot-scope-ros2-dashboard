#!/usr/bin/env python3
"""Convert a binary XYZ/XYZI PCD file to a bounded Robot Scope snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


PCD_TYPES = {
    ("F", 4): "f4",
    ("F", 8): "f8",
    ("I", 1): "i1",
    ("I", 2): "i2",
    ("I", 4): "i4",
    ("U", 1): "u1",
    ("U", 2): "u2",
    ("U", 4): "u4",
}


def read_binary_pcd(path: Path) -> tuple[np.ndarray, int]:
    metadata: dict[str, list[str]] = {}
    with path.open("rb") as stream:
        while True:
            line = stream.readline()
            if not line:
                raise ValueError("PCD header ended before DATA")
            decoded = line.decode("ascii", errors="strict").strip()
            if not decoded or decoded.startswith("#"):
                continue
            key, *values = decoded.split()
            metadata[key.upper()] = values
            if key.upper() == "DATA":
                if values != ["binary"]:
                    raise ValueError("only uncompressed binary PCD is supported")
                payload = stream.read()
                break

    fields = metadata.get("FIELDS", [])
    sizes = [int(value) for value in metadata.get("SIZE", [])]
    kinds = metadata.get("TYPE", [])
    counts = [int(value) for value in metadata.get("COUNT", ["1"] * len(fields))]
    if not fields or not (len(fields) == len(sizes) == len(kinds) == len(counts)):
        raise ValueError("invalid PCD field metadata")
    if any(count != 1 for count in counts):
        raise ValueError("multi-count PCD fields are not supported")
    if any(name not in fields for name in ("x", "y", "z")):
        raise ValueError("PCD requires x, y and z fields")

    dtype_fields = []
    for name, size, kind in zip(fields, sizes, kinds):
        scalar = PCD_TYPES.get((kind, size))
        if not scalar:
            raise ValueError(f"unsupported PCD field: {name} {kind}{size}")
        dtype_fields.append((name, "<" + scalar))
    dtype = np.dtype(dtype_fields)
    points = int(metadata.get("POINTS", metadata.get("WIDTH", ["0"]))[0])
    records = np.frombuffer(payload, dtype=dtype, count=points)
    xyz = np.column_stack((records["x"], records["y"], records["z"])).astype(np.float32, copy=False)
    return xyz, points


def reject_outliers(points: np.ndarray) -> np.ndarray:
    finite = points[np.isfinite(points).all(axis=1)]
    if len(finite) < 64:
        return finite
    center = np.median(finite, axis=0)
    distance = np.linalg.norm(finite - center, axis=1)
    robust_radius = float(np.quantile(distance, 0.98))
    limit = max(5.0, min(500.0, robust_radius * 2.0))
    filtered = finite[distance <= limit]
    return filtered if len(filtered) >= 64 else finite


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--max-points", type=int, default=10_000)
    parser.add_argument("--frame-id", default="camera_init")
    parser.add_argument("--topic", default="/saved/Laser_map")
    args = parser.parse_args()

    points, source_points = read_binary_pcd(args.input)
    points = reject_outliers(points)
    max_points = max(100, int(args.max_points))
    if len(points) > max_points:
        indexes = np.linspace(0, len(points) - 1, max_points, dtype=np.int64)
        points = points[indexes]

    points = np.round(points, 4)
    bounds = {
        "min": [float(value) for value in np.min(points, axis=0)],
        "max": [float(value) for value in np.max(points, axis=0)],
    }
    snapshot = {
        "seq": 1,
        "topic": args.topic,
        "frame_id": args.frame_id,
        "source_points": source_points,
        "sent_points": int(len(points)),
        "units": "m",
        "bounds": bounds,
        "offline_snapshot": True,
        "points": [round(float(value), 4) for value in points.reshape(-1)],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print(
        f"{args.input}: {source_points} source -> {len(points)} points, "
        f"bounds={bounds}, output={args.output}"
    )


if __name__ == "__main__":
    main()
