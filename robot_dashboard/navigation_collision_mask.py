"""Deterministic geometry-only mask artifacts; no ROS or enforcement authority.

The derived grid blocks source non-free cells and every cell touched by KEEP_OUT.
It does not expand a robot footprint, publish a mask, or establish native ingestion.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .map_annotations import (
    MapAnnotationError,
    parse_annotation_document,
    serialized_annotation_document,
)
from .saved_maps import NavigationMapSnapshot


SCHEMA = "robot-scope.collision-mask-artifact.v1"
PROFILE = "geometry-only-source-nonfree-and-keepout.v1"
MAX_CELLS = 1_048_576
MAX_RASTER_WORK = 2_000_000  # Sum of candidate cells times polygon vertices.
FAMILY_KEYS = frozenset({
    "family_id", "family_revision", "pcd_map_id", "pcd_revision",
    "occupancy_map_id", "occupancy_revision",
})
_PUBLIC_ANNOTATION_FIELDS = frozenset({"exists", "limits", "semantics"})
Point = tuple[float, float]


class CollisionMaskError(ValueError):
    """An input, pin, numerical/work bound, or immutable output is invalid."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class CollisionMaskArtifact:
    """Immutable in-memory payloads; the manifest is the completion marker."""

    digest: str
    manifest: bytes
    source_occupancy: bytes
    mask: bytes
    pgm: bytes
    yaml: bytes
    annotations: bytes

    def files(self) -> tuple[tuple[str, bytes], ...]:
        return (
            ("source.occupancy.bin", self.source_occupancy),
            ("mask.occupancy.bin", self.mask),
            ("mask.pgm", self.pgm),
            ("mask.yaml", self.yaml),
            ("annotations.json", self.annotations),
            ("manifest.json", self.manifest),
        )


def _check_pins(geometry: NavigationMapSnapshot, family: Mapping[str, str]) -> None:
    if not isinstance(family, Mapping) or set(family) != FAMILY_KEYS:
        raise CollisionMaskError("exact six-field map family is required")
    for key, value in family.items():
        length = 24 if key.endswith("_id") else 64
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{%d}" % length, value):
            raise CollisionMaskError("map family pin format is invalid")
    if (geometry.map_id, geometry.revision) != (
        family["occupancy_map_id"], family["occupancy_revision"]
    ):
        raise CollisionMaskError("occupancy map pin mismatch")
    try:
        geometry.require_map_family(
            family_id=family["family_id"], family_revision=family["family_revision"],
            source_pcd_id=family["pcd_map_id"], source_pcd_revision=family["pcd_revision"],
        )
    except ValueError as exc:
        raise CollisionMaskError("map family pin mismatch") from exc


def _cross(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: Point, b: Point, p: Point, epsilon: float) -> bool:
    return (abs(_cross(a, b, p)) <= epsilon * max(1.0, math.dist(a, b))
            and min(a[0], b[0]) - epsilon <= p[0] <= max(a[0], b[0]) + epsilon
            and min(a[1], b[1]) - epsilon <= p[1] <= max(a[1], b[1]) + epsilon)


def _segments_intersect(a: Point, b: Point, c: Point, d: Point, epsilon: float) -> bool:
    if any((_on_segment(a, b, c, epsilon), _on_segment(a, b, d, epsilon),
            _on_segment(c, d, a, epsilon), _on_segment(c, d, b, epsilon))):
        return True
    return ((_cross(a, b, c) > 0) != (_cross(a, b, d) > 0)
            and (_cross(c, d, a) > 0) != (_cross(c, d, b) > 0))


def _simple_polygon(vertices: tuple[Point, ...], epsilon: float) -> None:
    count = len(vertices)
    perimeter = sum(math.dist(vertices[i], vertices[(i + 1) % count]) for i in range(count))
    area2 = abs(sum(_cross(vertices[0], vertices[i], vertices[(i + 1) % count])
                    for i in range(1, count - 1)))
    if area2 <= epsilon * max(1.0, perimeter):
        raise CollisionMaskError("KEEP_OUT polygon is numerically degenerate")
    for i, a in enumerate(vertices):
        b = vertices[(i + 1) % count]
        if math.dist(a, b) <= epsilon:
            raise CollisionMaskError("KEEP_OUT polygon has a repeated vertex")
        previous = vertices[(i - 1) % count]
        if (_on_segment(previous, a, b, epsilon)
                or _on_segment(a, b, previous, epsilon)):
            raise CollisionMaskError("KEEP_OUT polygon has overlapping adjacent edges")
        for j in range(i + 1, count):
            if j == i + 1 or (i == 0 and j == count - 1):
                continue
            if _segments_intersect(a, b, vertices[j], vertices[(j + 1) % count], epsilon):
                raise CollisionMaskError("KEEP_OUT polygon is not simple")


def _segment_touches_cell(a: Point, b: Point, x: int, y: int, epsilon: float) -> bool:
    # Closed rectangle clipping includes an edge/corner touch. Expanding by a
    # recorded numerical margin can only add blocked cells, never free them.
    low, high = 0.0, 1.0
    for axis, cell in ((0, x), (1, y)):
        delta = b[axis] - a[axis]
        lower, upper = cell - epsilon, cell + 1.0 + epsilon
        if delta == 0:
            if not lower <= a[axis] <= upper:
                return False
            continue
        first, last = (lower - a[axis]) / delta, (upper - a[axis]) / delta
        low, high = max(low, min(first, last)), min(high, max(first, last))
        if low > high:
            return False
    return True


def _cell_intersects(vertices: tuple[Point, ...], x: int, y: int, epsilon: float) -> bool:
    inside = False
    px, py = x + 0.5, y + 0.5
    for i, a in enumerate(vertices):
        b = vertices[(i + 1) % len(vertices)]
        if _segment_touches_cell(a, b, x, y, epsilon):
            return True
        if (a[1] > py) != (b[1] > py):
            if px < a[0] + (py - a[1]) * (b[0] - a[0]) / (b[1] - a[1]):
                inside = not inside
    return inside


def build_collision_mask(
    geometry: NavigationMapSnapshot,
    annotations: Mapping[str, Any],
    *,
    expected_family: Mapping[str, str],
    expected_annotation_revision: str,
) -> CollisionMaskArtifact:
    """Build only from exact pins; reject ambiguity and oversized work in full."""
    if not isinstance(expected_family, Mapping):
        raise CollisionMaskError("exact six-field map family is required")
    family = dict(expected_family)
    _check_pins(geometry, family)
    if geometry.width * geometry.height > MAX_CELLS:
        raise CollisionMaskError("collision mask cell limit exceeded")
    if (not isinstance(geometry.frame_id, str) or not geometry.frame_id
            or len(geometry.frame_id) > 128 or any(ord(c) < 32 for c in geometry.frame_id)):
        raise CollisionMaskError("collision mask frame is invalid")
    if not isinstance(expected_annotation_revision, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_annotation_revision
    ):
        raise CollisionMaskError("exact annotation revision is required")
    if not isinstance(annotations, Mapping):
        raise CollisionMaskError("annotation document must be an object")
    try:
        document = parse_annotation_document(
            {key: value for key, value in annotations.items() if key not in _PUBLIC_ANNOTATION_FIELDS},
            geometry=geometry,
        )
        annotation_bytes = serialized_annotation_document(document)
    except MapAnnotationError as exc:
        raise CollisionMaskError("annotation document or content revision is invalid") from exc
    if document["annotation_revision"] != expected_annotation_revision:
        raise CollisionMaskError("annotation revision pin mismatch")

    ox, oy, yaw = geometry.origin
    resolution = float(geometry.resolution)
    # Allow ordinary map coordinates, but fail closed when floating-point
    # conditioning would require more than 1/1000 cell of boundary expansion.
    magnitude = max(1.0, abs(ox), abs(oy), geometry.width * resolution,
                    geometry.height * resolution,
                    *(abs(v[k]) for p in document["polygons"] for v in p["vertices"] for k in ("x", "y")))
    epsilon = max(1e-9, 64.0 * math.ulp(magnitude) / resolution,
                  64.0 * math.ulp(float(max(geometry.width, geometry.height))))
    if not math.isfinite(epsilon) or epsilon > 0.001:
        raise CollisionMaskError("collision mask geometry is numerically ill-conditioned")
    cosine, sine = math.cos(yaw), math.sin(yaw)
    polygons = []
    work = 0
    for polygon in document["polygons"]:
        if polygon["type"] != "KEEP_OUT":
            continue
        vertices = tuple(((cosine * (v["x"] - ox) + sine * (v["y"] - oy)) / resolution,
                          (-sine * (v["x"] - ox) + cosine * (v["y"] - oy)) / resolution)
                         for v in polygon["vertices"])
        if not all(math.isfinite(c) for vertex in vertices for c in vertex):
            raise CollisionMaskError("collision mask grid transform is non-finite")
        _simple_polygon(vertices, epsilon)
        x0 = max(0, math.floor(min(v[0] for v in vertices) - epsilon))
        x1 = min(geometry.width - 1, math.floor(max(v[0] for v in vertices) + epsilon))
        y0 = max(0, math.floor(min(v[1] for v in vertices) - epsilon))
        y1 = min(geometry.height - 1, math.floor(max(v[1] for v in vertices) + epsilon))
        work += (x1 - x0 + 1) * (y1 - y0 + 1) * len(vertices)
        if work > MAX_RASTER_WORK:
            raise CollisionMaskError("collision mask raster work limit exceeded")
        polygons.append((vertices, x0, x1, y0, y1))

    mask = bytearray(0 if value == 0 else 100 for value in geometry.occupancy)
    for vertices, x0, x1, y0, y1 in polygons:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if _cell_intersects(vertices, x, y, epsilon):
                    mask[y * geometry.width + x] = 100
    mask_bytes = bytes(mask)
    pgm = f"P5\n{geometry.width} {geometry.height}\n255\n".encode("ascii") + bytes(
        255 if mask[y * geometry.width + x] == 0 else 0
        for y in range(geometry.height - 1, -1, -1) for x in range(geometry.width)
    )
    # JSON scalars/lists are valid YAML and preserve exact finite geometry.
    yaml = ("image: mask.pgm\nmode: trinary\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n"
            f"resolution: {json.dumps(resolution)}\norigin: {json.dumps([float(v) for v in geometry.origin])}\n").encode("ascii")
    payloads = {"source.occupancy.bin": geometry.occupancy, "mask.occupancy.bin": mask_bytes,
                "mask.pgm": pgm, "mask.yaml": yaml, "annotations.json": annotation_bytes}
    manifest = {
        "schema": SCHEMA, "profile": PROFILE, "map_family": family,
        "annotation_revision": expected_annotation_revision,
        "geometry": {"width": geometry.width, "height": geometry.height,
                     "resolution": resolution, "origin": [float(v) for v in geometry.origin],
                     "frame_id": geometry.frame_id, "grid_order": "ros-row-major-bottom-up"},
        "rasterization": {"cell_rule": "closed-cell-intersects-KEEP_OUT",
                          "boundary_margin_cells": epsilon, "candidate_vertex_work": work,
                          "max_cells": MAX_CELLS, "max_raster_work": MAX_RASTER_WORK},
        "semantics": {"source_bytes_preserved": True, "source_unknown_byte": 255,
                      "free_only_when_source_zero_and_outside_keepout": True,
                      "derived_free": 0, "derived_blocked": 100,
                      "footprint_expansion": "none", "runtime_policy_enforced": False,
                      "native_ingestion_evidence": "not_provided",
                      "advisory_types": ["SLOW_ZONE", "WAIT_ZONE"]},
        "counts": {"source_nonfree": sum(v != 0 for v in geometry.occupancy),
                   "derived_blocked": sum(v == 100 for v in mask_bytes),
                   "keepout_polygons": len(polygons)},
        "files": {name: {"sha256": _sha256(payload), "bytes": len(payload)}
                  for name, payload in payloads.items()},
    }
    digest = _sha256(_canonical(manifest))
    manifest["artifact_digest"] = digest
    return CollisionMaskArtifact(digest, _canonical(manifest) + b"\n", geometry.occupancy,
                                 mask_bytes, pgm, yaml, annotation_bytes)


def write_collision_mask(artifact: CollisionMaskArtifact, destination: Path) -> Path:
    """Create a new private directory exclusively; never replace existing files.

    Manifest is written last. A process crash can leave an incomplete directory;
    absence of the manifest means it is not a completed artifact. Reuse is refused.
    """
    destination = Path(destination)
    parent = destination.parent
    if (not destination.is_absolute() or destination.name in {"", ".", ".."}
            or parent.resolve(strict=True) != parent or not parent.is_dir()):
        raise CollisionMaskError("output requires a real absolute parent directory")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_fd = os.open(parent, flags)
    directory_fd = None
    created = []
    made_directory = False
    try:
        os.mkdir(destination.name, mode=0o700, dir_fd=parent_fd)
        made_directory = True
        directory_fd = os.open(destination.name, flags, dir_fd=parent_fd)
        for name, payload in artifact.files():
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o400, dir_fd=directory_fd)
            created.append(name)
            with os.fdopen(fd, "wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
        os.fsync(directory_fd)
        os.fchmod(directory_fd, 0o500)
        os.fsync(parent_fd)
    except OSError as exc:
        if directory_fd is not None:
            os.fchmod(directory_fd, 0o700)
            for name in reversed(created):
                os.unlink(name, dir_fd=directory_fd)
        if made_directory:
            os.rmdir(destination.name, dir_fd=parent_fd)
        raise CollisionMaskError("immutable output publication failed or target already exists") from exc
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        os.close(parent_fd)
    return destination
