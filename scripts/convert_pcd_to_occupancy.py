#!/usr/bin/env python3
"""Convert one staged binary PCD with Robot Scope's bounded local converter."""

from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path
from typing import Any, Iterable


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from robot_dashboard.saved_maps import (  # noqa: E402
    SavedMapCatalog,
    SavedMapError,
    SavedMapFormatError,
)


MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_POINTS = 2_000_000
MAX_GRID_CELLS = 16_000_000


def _prefix(value: Path) -> Path:
    prefix = value.expanduser()
    if not prefix.is_absolute():
        prefix = Path.cwd() / prefix
    if not prefix.name or prefix.name.startswith(".") or prefix.suffix:
        raise SavedMapFormatError("output prefix must be a simple extension-free name")
    parent = prefix.parent
    try:
        parent_stat = parent.lstat()
    except OSError as exc:
        raise SavedMapFormatError("output directory does not exist") from exc
    if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
        raise SavedMapFormatError("output directory must be a real directory")
    return prefix


def convert_staged_pcd(
    value: Path,
    *,
    z_min: float = -0.2,
    z_max: float = 0.8,
    resolution: float = 0.05,
    noise_radius: float = 0.1,
    min_neighbors: int = 10,
) -> dict[str, Any]:
    """Create ``.yaml``/``.pgm`` beside an already staged ``.pcd``."""

    prefix = _prefix(value)
    pcd = prefix.with_name(prefix.name + ".pcd")
    try:
        pcd_stat = pcd.lstat()
    except OSError as exc:
        raise SavedMapFormatError("staged PCD does not exist") from exc
    if stat.S_ISLNK(pcd_stat.st_mode) or not stat.S_ISREG(pcd_stat.st_mode):
        raise SavedMapFormatError("staged PCD must be a regular file")
    if pcd_stat.st_size <= 0 or pcd_stat.st_size > MAX_FILE_BYTES:
        raise SavedMapFormatError("staged PCD exceeds the supported file limit")
    for suffix in (".yaml", ".pgm"):
        target = prefix.with_name(prefix.name + suffix)
        if target.exists() or target.is_symlink():
            raise SavedMapFormatError(f"staged output already exists: {target.name}")

    catalog = SavedMapCatalog(
        [prefix.parent],
        managed_roots=[prefix.parent],
        max_files=10,
        max_depth=0,
        max_file_bytes=MAX_FILE_BYTES,
        max_full_view_points=MAX_POINTS,
        max_grid_cells=MAX_GRID_CELLS,
    )
    source = next(
        (
            item
            for item in catalog.list_snapshot()["maps"]
            if item.get("file_name") == pcd.name
            and item.get("kind") == "pointcloud3d"
            and item.get("format") == "pcd-binary"
            and item.get("manageable") is True
        ),
        None,
    )
    if source is None:
        raise SavedMapFormatError("staged PCD did not pass catalog validation")
    return catalog.convert_pcd_to_2d(
        str(source["id"]),
        prefix.name,
        z_min=z_min,
        z_max=z_max,
        resolution=resolution,
        noise_radius=noise_radius,
        min_neighbors=min_neighbors,
        background="unknown",
        expected_revision=str(source["revision"]),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a staged binary PCD to a bounded trinary PGM/YAML map."
    )
    parser.add_argument("output_prefix", type=Path)
    parser.add_argument("--z-min", type=float, default=-0.2)
    parser.add_argument("--z-max", type=float, default=0.8)
    parser.add_argument("--resolution", type=float, default=0.05)
    parser.add_argument("--noise-radius", type=float, default=0.1)
    parser.add_argument("--min-neighbors", type=int, default=10)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    options = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = convert_staged_pcd(
            options.output_prefix,
            z_min=options.z_min,
            z_max=options.z_max,
            resolution=options.resolution,
            noise_radius=options.noise_radius,
            min_neighbors=options.min_neighbors,
        )
    except SavedMapError as exc:
        print(f"[Robot Scope] PCD conversion rejected: {exc}", file=sys.stderr)
        return 2
    details = result.get("details", {})
    print(
        "[Robot Scope] occupancy map saved: "
        f"{details.get('width', 0)}x{details.get('height', 0)}, "
        f"selected={details.get('selected_points', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
