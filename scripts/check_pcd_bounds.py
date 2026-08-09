#!/usr/bin/env python3
"""Reject a saved binary PCD that could create an unsafe 2D grid."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np


def read_xyz(path: Path) -> np.ndarray:
    with path.open("rb") as stream:
        header_lines: list[bytes] = []
        header_bytes = 0
        while header_bytes < 65_536:
            line = stream.readline()
            if not line:
                raise ValueError("PCD header is incomplete")
            header_lines.append(line)
            header_bytes += len(line)
            if line.strip().upper().startswith(b"DATA "):
                break
        else:
            raise ValueError("PCD header is too large")
        payload = stream.read()

    fields: list[str] = []
    point_count = 0
    data_kind = ""
    for raw in header_lines:
        parts = raw.decode("ascii", "replace").strip().split()
        if not parts:
            continue
        key = parts[0].upper()
        if key == "FIELDS":
            fields = [value.lower() for value in parts[1:]]
        elif key == "POINTS" and len(parts) == 2:
            point_count = int(parts[1])
        elif key == "DATA" and len(parts) == 2:
            data_kind = parts[1].lower()

    if data_kind != "binary" or point_count < 1:
        raise ValueError("only non-empty binary PCD files are supported")
    if fields[:3] != ["x", "y", "z"]:
        raise ValueError("PCD must begin with x/y/z float fields")
    point_step = len(payload) // point_count
    if point_step < 12 or len(payload) != point_count * point_step:
        raise ValueError("PCD payload size does not match POINTS")

    dtype = np.dtype({
        "names": ["x", "y", "z"],
        "formats": ["<f4", "<f4", "<f4"],
        "offsets": [0, 4, 8],
        "itemsize": point_step,
    })
    values = np.frombuffer(payload, dtype=dtype, count=point_count)
    return np.column_stack((values["x"], values["y"], values["z"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pcd", type=Path)
    parser.add_argument("--resolution", type=float, default=0.05)
    parser.add_argument("--z-min", type=float, default=-0.2)
    parser.add_argument("--z-max", type=float, default=0.8)
    parser.add_argument("--max-cells", type=int, default=16_000_000)
    args = parser.parse_args()

    if not 0.02 <= args.resolution <= 0.2 or args.z_min >= args.z_max:
        raise SystemExit("unsafe 2D conversion parameters")
    xyz = read_xyz(args.pcd.resolve(strict=True))
    mask = np.isfinite(xyz).all(axis=1) & (xyz[:, 2] >= args.z_min) & (xyz[:, 2] <= args.z_max)
    selected = xyz[mask]
    if selected.size == 0:
        raise SystemExit("no finite points remain inside the configured z range")
    spans = np.ptp(selected[:, :2], axis=0)
    width = max(1, math.ceil(float(spans[0]) / args.resolution))
    height = max(1, math.ceil(float(spans[1]) / args.resolution))
    cells = width * height
    if cells > args.max_cells:
        raise SystemExit(f"2D grid would be too large: {width}x{height} ({cells} cells)")
    print(f"[Robot Scope] 2D grid preflight: {width}x{height} ({cells} cells)", flush=True)


if __name__ == "__main__":
    main()
