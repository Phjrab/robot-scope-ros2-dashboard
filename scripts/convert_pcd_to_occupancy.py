#!/usr/bin/env python3
"""Convert one staged binary PCD with Robot Scope's bounded local converter."""

from __future__ import annotations

import argparse
import os
import stat
import sys
import uuid
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
from robot_dashboard.map_lineage import (  # noqa: E402
    build_family_document,
    serialize_family_document,
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
    publication_root: Path | None = None,
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
    result = catalog.convert_pcd_to_2d(
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
    if publication_root is not None:
        final_root = publication_root.expanduser().resolve(strict=True)
        if final_root == Path("/") or final_root.is_symlink() or not final_root.is_dir():
            raise SavedMapFormatError("publication root must be a real non-root directory")
        family = result["map"]["map_family"]
        parameters = {
            key: family["conversion"][key]
            for key in (
                "z_min", "z_max", "resolution", "noise_radius",
                "min_neighbors", "background",
            )
        }
        repinned = build_family_document(
            family_id=family["family_id"],
            mapping_session_id=family["source"]["mapping_session_id"],
            pcd_map_id=SavedMapCatalog._opaque_id(
                "pointcloud3d", final_root / f"{prefix.name}.pcd"
            ),
            pcd_revision=family["source"]["pcd_revision"],
            source_frame_id=family["source"]["frame_id"],
            occupancy_map_id=SavedMapCatalog._opaque_id(
                "occupancy2d", final_root / f"{prefix.name}.yaml"
            ),
            occupancy_revision=family["occupancy"]["map_revision"],
            occupancy_frame_id=family["occupancy"]["frame_id"],
            resolution=family["occupancy"]["resolution"],
            width=family["occupancy"]["width"],
            height=family["occupancy"]["height"],
            origin=family["occupancy"]["origin"],
            parameters=parameters,
            created_at=family["created_at"],
        )
        sidecar = prefix.with_name(f"{prefix.name}.map-family.json")
        temporary = sidecar.with_name(f".{sidecar.name}.{uuid.uuid4().hex}.tmp")
        descriptor = -1
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            content = serialize_family_document(repinned)
            view = memoryview(content)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("map-family write made no progress")
                view = view[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary, sidecar)
            directory_fd = os.open(sidecar.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)
        result["map"]["map_family"] = repinned
    return result


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
    parser.add_argument("--publication-root", type=Path)
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
            publication_root=options.publication_root,
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
