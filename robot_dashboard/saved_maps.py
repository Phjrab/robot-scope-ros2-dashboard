"""Catalog, preview loader, and bounded manager for maps on the robot host.

Only files discovered below profile-configured roots receive an opaque ID.  API
callers never supply a path, which keeps traversal and accidental arbitrary-file
access out of the HTTP surface.  Rename and delete are additionally restricted
to explicit managed roots; other catalog roots remain read-only.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import stat
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, ContextManager, Dict, Iterable, Optional

import numpy as np

from .map_annotations import (
    AnnotationGoal,
    MAX_DOCUMENT_BYTES,
    MapAnnotationConflict,
    MapAnnotationError,
    empty_annotation_document,
    normalize_annotation_document,
    parse_annotation_document,
    resolve_annotation_goal,
    serialized_annotation_document,
)
from .map_lineage import (
    MAX_DOCUMENT_BYTES as MAX_LINEAGE_DOCUMENT_BYTES,
    MapLineageError,
    build_family_document,
    parse_family_document,
    public_family_document,
    serialize_family_document,
)


class SavedMapError(Exception):
    """Base class for expected saved-map failures."""


class SavedMapNotFound(SavedMapError):
    """Raised when an opaque map ID is not in the current catalog."""


class SavedMapFormatError(SavedMapError):
    """Raised when a configured file is not a supported map snapshot."""


class SavedMapPointLimitError(SavedMapError):
    """Raised when a point-cloud response limit is invalid or unsafe."""


def prepare_private_map_root(path: Path) -> Path:
    """Create or validate the real, operator-private managed-map root."""

    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError("mapping output directory must be a real directory")
    resolved = path.resolve(strict=True)
    mode = stat.S_IMODE(resolved.stat().st_mode)
    if mode & 0o077:
        raise RuntimeError(
            "mapping output directory must not be accessible by group or others"
        )
    return resolved


class SavedMapMutationError(SavedMapError):
    """Base class for a saved-map mutation that could not be completed safely."""


class SavedMapInvalidName(SavedMapMutationError):
    """Raised when a requested map name is not a safe portable filename."""


class SavedMapReadOnly(SavedMapMutationError):
    """Raised when a catalog record is outside the explicit managed roots."""


class SavedMapConflict(SavedMapMutationError):
    """Raised when a rename target already exists."""


MAP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
REVISION_RE = re.compile(r"^[0-9a-f]{64}$")

PCD_Z_LIMIT_M = 20.0
MIN_MAP_RESOLUTION_M = 0.01
MAX_MAP_RESOLUTION_M = 1.0
MIN_NOISE_RADIUS_M = 0.01
MAX_NOISE_RADIUS_M = 2.0
MAX_NOISE_NEIGHBORS = 1_000
MAX_EDIT_RUNS = 10_000
DEFAULT_MAX_EDITED_CELLS = 2_000_000
BACKGROUND_MODES = frozenset({"unknown", "free"})


@dataclass(frozen=True)
class SavedMapRecord:
    map_id: str
    name: str
    kind: str
    format: str
    path: Path
    root: Path
    modified_ns: int
    revision: str
    size_bytes: int
    details: Dict[str, Any]
    manageable: bool = False
    auxiliary_path: Optional[Path] = None

    def public(self) -> Dict[str, Any]:
        modified = datetime.fromtimestamp(
            self.modified_ns / 1_000_000_000,
            tz=timezone.utc,
        ).isoformat()
        result: Dict[str, Any] = {
            "id": self.map_id,
            "name": self.name,
            "kind": self.kind,
            "format": self.format,
            "file_name": self.path.name,
            "modified_at": modified,
            "size_bytes": self.size_bytes,
            "manageable": self.manageable,
            # The filesystem signature revision is an opaque string so it is
            # exact across the JavaScript boundary and changes when either
            # artifact in a YAML/PGM pair is replaced.
            "revision": self.revision,
            "data_url": f"/api/v1/saved-maps/{self.map_id}/data",
        }
        result.update(self.details)
        if self.format == "map-server-pgm":
            result["annotations_url"] = (
                f"/api/v1/saved-maps/{self.map_id}/annotations"
            )
        return result


@dataclass(frozen=True)
class NavigationMapSource:
    """Private, revision-pinned occupancy pair resolved from an opaque ID."""

    map_id: str
    revision: str
    name: str
    frame_id: str
    yaml_path: Path
    image_path: Path
    yaml_signature: tuple[int, int, int, int]
    image_signature: tuple[int, int, int, int]
    family: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class NavigationMapSnapshot:
    """Independent private map copy retained for one navigation job.

    ``occupancy`` is ROS row-major map order, encoded as bytes containing
    ``0`` (free), ``100`` (occupied) or ``255`` (unknown/-1).  Paths are
    intentionally private implementation details and are never serialized by
    the HTTP layer.
    """

    map_id: str
    revision: str
    name: str
    frame_id: str
    yaml_path: Path
    image_path: Path
    width: int
    height: int
    resolution: float
    origin: tuple[float, float, float]
    occupancy: bytes
    family_id: Optional[str] = None
    family_revision: Optional[str] = None
    source_pcd_id: Optional[str] = None
    source_pcd_revision: Optional[str] = None
    occupancy_map_id: Optional[str] = None
    occupancy_map_revision: Optional[str] = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.width, bool)
            or isinstance(self.height, bool)
            or not isinstance(self.width, int)
            or not isinstance(self.height, int)
            or self.width <= 0
            or self.height <= 0
        ):
            raise ValueError("navigation map dimensions are invalid")
        if (
            isinstance(self.resolution, bool)
            or not isinstance(self.resolution, (int, float))
            or not math.isfinite(float(self.resolution))
            or float(self.resolution) <= 0.0
        ):
            raise ValueError("navigation map resolution is invalid")
        if (
            not isinstance(self.origin, tuple)
            or len(self.origin) != 3
            or not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                for value in self.origin
            )
        ):
            raise ValueError("navigation map origin is invalid")
        if not isinstance(self.occupancy, bytes) or len(self.occupancy) != self.width * self.height:
            raise ValueError("navigation occupancy payload is invalid")

    def known_free(self, x: float, y: float, *, clearance_radius: float) -> bool:
        """Return true only when a circular footprint is entirely known-free."""

        if (
            not all(math.isfinite(value) for value in (x, y, clearance_radius))
            or clearance_radius < 0
            or self.resolution <= 0
        ):
            return False
        ox, oy, origin_yaw = self.origin
        dx, dy = x - ox, y - oy
        cosine, sine = math.cos(origin_yaw), math.sin(origin_yaw)
        local_x = cosine * dx + sine * dy
        local_y = -sine * dx + cosine * dy
        center_x = math.floor(local_x / self.resolution)
        center_y = math.floor(local_y / self.resolution)
        if not (0 <= center_x < self.width and 0 <= center_y < self.height):
            return False

        # Keep the full footprint within map bounds.  A tiny margin makes
        # exact cell/map boundaries conservative instead of floating-point
        # dependent.
        epsilon = max(1e-12, self.resolution * 1e-12)
        footprint_radius = clearance_radius + epsilon
        map_width = self.width * self.resolution
        map_height = self.height * self.resolution
        if (
            local_x - footprint_radius < 0.0
            or local_y - footprint_radius < 0.0
            or local_x + footprint_radius > map_width
            or local_y + footprint_radius > map_height
        ):
            return False
        first_x = max(0, math.floor((local_x - footprint_radius) / self.resolution))
        last_x = min(
            self.width - 1,
            math.floor((local_x + footprint_radius) / self.resolution),
        )
        first_y = max(0, math.floor((local_y - footprint_radius) / self.resolution))
        last_y = min(
            self.height - 1,
            math.floor((local_y + footprint_radius) / self.resolution),
        )
        for cell_y in range(first_y, last_y + 1):
            lower_y = cell_y * self.resolution
            upper_y = lower_y + self.resolution
            distance_y = max(lower_y - local_y, 0.0, local_y - upper_y)
            for cell_x in range(first_x, last_x + 1):
                lower_x = cell_x * self.resolution
                upper_x = lower_x + self.resolution
                distance_x = max(lower_x - local_x, 0.0, local_x - upper_x)
                if math.hypot(distance_x, distance_y) > footprint_radius:
                    continue
                if self.occupancy[cell_y * self.width + cell_x] != 0:
                    return False
        return True

    def require_map_family(
        self,
        *,
        family_id: str,
        family_revision: str,
        source_pcd_id: str,
        source_pcd_revision: str,
    ) -> None:
        """Fail closed when a future relocalization candidate is not exact."""

        expected = (
            family_id,
            family_revision,
            source_pcd_id,
            source_pcd_revision,
            self.map_id,
            self.revision,
        )
        actual = (
            self.family_id,
            self.family_revision,
            self.source_pcd_id,
            self.source_pcd_revision,
            self.occupancy_map_id,
            self.occupancy_map_revision,
        )
        if actual != expected:
            raise ValueError("navigation map family does not match the candidate")

    def contains(self, x: float, y: float) -> bool:
        """Return true when a finite map-frame point lies inside the grid."""

        if not all(math.isfinite(value) for value in (x, y)):
            return False
        ox, oy, origin_yaw = self.origin
        dx, dy = x - ox, y - oy
        cosine, sine = math.cos(origin_yaw), math.sin(origin_yaw)
        local_x = cosine * dx + sine * dy
        local_y = -sine * dx + cosine * dy
        return bool(
            0.0 <= local_x < self.width * self.resolution
            and 0.0 <= local_y < self.height * self.resolution
        )


class SavedMapCatalog:
    """Discover and normalize saved maps under an explicit root allowlist."""

    def __init__(
        self,
        roots: Iterable[Path],
        *,
        managed_roots: Iterable[Path] = (),
        max_files: int = 100,
        max_depth: int = 3,
        max_file_bytes: int = 256 * 1024 * 1024,
        preview_points: int = 10_000,
        max_requested_points: int = 1_000_000,
        max_full_view_points: int = 2_000_000,
        cloud_radius_limit_m: float = 500.0,
        max_grid_cells: int = 16_000_000,
        max_edited_cells: int = DEFAULT_MAX_EDITED_CELLS,
    ) -> None:
        resolved_roots = []
        for value in roots:
            try:
                root = value.expanduser().resolve(strict=True)
            except OSError:
                continue
            if root.is_dir() and root not in resolved_roots:
                resolved_roots.append(root)
        self.roots = tuple(resolved_roots)
        resolved_managed_roots = []
        for value in managed_roots:
            raw_root = value.expanduser()
            if raw_root.is_symlink():
                continue
            try:
                root = raw_root.resolve(strict=True)
            except OSError:
                continue
            if root in self.roots and root.is_dir() and root not in resolved_managed_roots:
                resolved_managed_roots.append(root)
        self.managed_roots = tuple(resolved_managed_roots)
        self.max_files = max(1, min(int(max_files), 2_000))
        self.max_depth = max(0, min(int(max_depth), 10))
        self.max_file_bytes = max(1024, min(int(max_file_bytes), 2 * 1024**3))
        self.preview_points = max(100, min(int(preview_points), 50_000))
        self.max_requested_points = max(
            1,
            min(int(max_requested_points), 5_000_000),
        )
        self.max_full_view_points = max(
            1,
            min(int(max_full_view_points), 5_000_000),
        )
        self.cloud_radius_limit_m = max(5.0, min(float(cloud_radius_limit_m), 10_000.0))
        self.max_grid_cells = max(1_000, min(int(max_grid_cells), 64_000_000))
        self.max_edited_cells = max(
            1,
            min(int(max_edited_cells), self.max_grid_cells, 8_000_000),
        )
        self._lock = threading.RLock()

    @classmethod
    def from_profile(
        cls,
        profile: Dict[str, Any],
        *,
        base_dir: Optional[Path] = None,
        additional_roots: Iterable[Path] = (),
        managed_roots: Iterable[Path] = (),
    ) -> "SavedMapCatalog":
        settings = profile.get("saved_maps", {}) if isinstance(profile, dict) else {}
        if not isinstance(settings, dict) or settings.get("enabled", True) is False:
            return cls(())
        base = (base_dir or Path.cwd()).expanduser().resolve()
        roots = []
        raw_directories = settings.get("directories", [])
        if isinstance(raw_directories, list):
            for raw in raw_directories:
                if not isinstance(raw, str) or not raw.strip():
                    continue
                expanded = Path(os.path.expandvars(raw)).expanduser()
                roots.append(expanded if expanded.is_absolute() else base / expanded)
        roots.extend(additional_roots)
        return cls(
            roots,
            managed_roots=managed_roots,
            max_files=settings.get("max_files", 100),
            max_depth=settings.get("max_depth", 3),
            max_file_bytes=settings.get("max_file_bytes", 256 * 1024 * 1024),
            preview_points=settings.get("preview_points", 10_000),
            max_requested_points=settings.get("max_requested_points", 1_000_000),
            max_full_view_points=settings.get("max_full_view_points", 2_000_000),
            cloud_radius_limit_m=settings.get(
                "cloud_radius_limit_m",
                profile.get("cloud_radius_limit_m", 500.0),
            ),
            max_grid_cells=settings.get("max_grid_cells", 16_000_000),
            max_edited_cells=settings.get(
                "max_edited_cells",
                DEFAULT_MAX_EDITED_CELLS,
            ),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.roots)

    def list_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            records = self._scan()
            return {
                "enabled": self.enabled,
                "count": len(records),
                "maps": [record.public() for record in records],
            }

    def metadata(self, map_id: str) -> Dict[str, Any]:
        with self._lock:
            return self._find(map_id).public()

    def map_family(self, map_id: str) -> Dict[str, Any]:
        """Return bounded lineage for one catalog ID without exposing paths."""

        with self._lock:
            record = self._find(map_id)
            direct = (
                self._read_lineage(record)
                if record.format == "map-server-pgm"
                else None
            )
            matches = (
                [direct]
                if direct is not None
                else [
                    document
                    for document in self._scan_lineage_documents()
                    if document["source"]["pcd_map_id"] == map_id
                ]
            )
            matches.sort(key=lambda item: (item["created_at"], item["family_revision"]))
            return {
                "map_id": record.map_id,
                "map_revision": record.revision,
                "status": "linked" if matches else "unlinked",
                "families": [public_family_document(item) for item in matches],
            }

    def map_family_by_id(self, family_id: str) -> Dict[str, Any]:
        if not isinstance(family_id, str) or not re.fullmatch(r"[0-9a-f]{24}", family_id):
            raise SavedMapNotFound("map family not found")
        with self._lock:
            matches = [
                document
                for document in self._scan_lineage_documents()
                if document["family_id"] == family_id
            ]
            if not matches:
                raise SavedMapNotFound("map family not found")
            matches.sort(key=lambda item: (item["created_at"], item["family_revision"]))
            return {
                "family_id": family_id,
                "members": [public_family_document(item) for item in matches],
            }

    def annotations(self, map_id: str) -> Dict[str, Any]:
        """Return one validated, revision-pinned annotation document."""

        with self._lock:
            record = self._annotation_record(map_id)
            geometry = self._annotation_geometry(record)
            return self._read_annotations(record, geometry)

    def route_geometry(
        self,
        map_id: str,
        expected_revision: str,
    ) -> NavigationMapSnapshot:
        """Return validated in-memory geometry for server-side route checks.

        Filesystem paths remain private; Route Planner callers use only the
        ``MapGeometry`` methods and exact map/revision fields.
        """

        if (
            not isinstance(expected_revision, str)
            or not REVISION_RE.fullmatch(expected_revision)
        ):
            raise SavedMapConflict("saved map revision is invalid")
        with self._lock:
            record = self._annotation_record(map_id)
            if record.revision != expected_revision:
                raise SavedMapConflict(
                    "saved map changed; reload it before validating the route graph"
                )
            return self._annotation_geometry(record)

    def update_annotations(
        self,
        map_id: str,
        map_revision: str,
        base_annotation_revision: str,
        points: Any,
        polygons: Any,
    ) -> Dict[str, Any]:
        """Atomically publish a full annotation document using two CAS pins."""

        if not isinstance(base_annotation_revision, str) or not REVISION_RE.fullmatch(
            base_annotation_revision
        ):
            raise SavedMapConflict("annotation revision is invalid")
        with self._lock:
            record = self._annotation_record(map_id)
            if record.revision != map_revision:
                raise SavedMapConflict(
                    "saved map changed; reload annotations before saving"
                )
            geometry = self._annotation_geometry(record)
            current = self._read_annotations(record, geometry)
            if current["annotation_revision"] != base_annotation_revision:
                raise SavedMapConflict(
                    "annotations changed; reload them before saving"
                )
            try:
                document = normalize_annotation_document(
                    map_id=record.map_id,
                    map_revision=record.revision,
                    points=points,
                    polygons=polygons,
                    geometry=geometry,
                    exists=True,
                )
                encoded = serialized_annotation_document(document)
            except MapAnnotationConflict as exc:
                raise SavedMapConflict(str(exc)) from exc
            except MapAnnotationError as exc:
                raise SavedMapFormatError(str(exc)) from exc
            self._publish_annotations(record, encoded)
            # Re-read the published regular file and its content revision.
            return self._read_annotations(record, geometry)

    def resolve_annotation_goal(
        self,
        map_id: str,
        map_revision: str,
        annotation_revision: str,
        annotation_id: str,
    ) -> AnnotationGoal:
        """Resolve one goal-capable point under exact map and document pins."""

        if not isinstance(annotation_revision, str) or not REVISION_RE.fullmatch(
            annotation_revision
        ):
            raise SavedMapConflict("annotation revision is invalid")
        with self._lock:
            record = self._annotation_record(map_id)
            if record.revision != map_revision:
                raise SavedMapConflict(
                    "saved map changed; reload the annotation goal"
                )
            geometry = self._annotation_geometry(record)
            document = self._read_annotations(record, geometry)
            if document["annotation_revision"] != annotation_revision:
                raise SavedMapConflict(
                    "annotations changed; reload the annotation goal"
                )
            try:
                return resolve_annotation_goal(document, annotation_id)
            except MapAnnotationError as exc:
                raise SavedMapFormatError(str(exc)) from exc

    def resolve_navigation_map(
        self,
        map_id: str,
        expected_revision: str,
    ) -> NavigationMapSource:
        """Resolve one managed, revision-pinned map without exposing its path."""

        if (
            not isinstance(expected_revision, str)
            or not REVISION_RE.fullmatch(expected_revision)
        ):
            raise SavedMapConflict("saved map revision is invalid")
        with self._lock:
            record = self._find(map_id)
            self._require_manageable(record)
            if record.format != "map-server-pgm" or record.auxiliary_path is None:
                raise SavedMapFormatError(
                    "navigation requires a managed 2D occupancy map"
                )
            self._require_editable_record(record)
            if record.revision != expected_revision:
                raise SavedMapConflict(
                    "saved map changed; reload it before starting navigation"
                )
            metadata = self._read_map_yaml(record.path)
            magic, _, _, maximum = self._read_pgm_header(record.auxiliary_path)
            if metadata["mode"] != "trinary" or magic != "P5" or maximum != 255:
                raise SavedMapFormatError(
                    "navigation requires a managed trinary P5/255 occupancy map"
                )
            family = self._read_lineage(record)
            return NavigationMapSource(
                map_id=record.map_id,
                revision=record.revision,
                name=record.name,
                frame_id=str(record.details.get("frame_id", "map")) or "map",
                yaml_path=record.path,
                image_path=record.auxiliary_path,
                yaml_signature=self._regular_signature(record.path),
                image_signature=self._regular_signature(record.auxiliary_path),
                family=family,
            )

    def snapshot_navigation_map(
        self,
        map_id: str,
        expected_revision: str,
        destination: Path,
    ) -> NavigationMapSnapshot:
        """Copy a validated map pair into one manager-owned private job dir."""

        target_dir = Path(destination)
        created: list[Path] = []
        try:
            current = target_dir.lstat()
            if not stat.S_ISDIR(current.st_mode) or target_dir.is_symlink():
                raise SavedMapMutationError(
                    "navigation snapshot directory is unsafe"
                )
        except OSError as exc:
            raise SavedMapMutationError(
                "navigation snapshot directory is unavailable"
            ) from exc

        with self._lock:
            source = self.resolve_navigation_map(map_id, expected_revision)
            source_yaml = target_dir / "map.source.yaml"
            target_yaml = target_dir / "map.yaml"
            target_pgm = target_dir / "map.pgm"
            if any(os.path.lexists(path) for path in (source_yaml, target_yaml, target_pgm)):
                raise SavedMapMutationError(
                    "navigation snapshot targets already exist"
                )
            try:
                self._copy_regular_snapshot(
                    source.yaml_path,
                    source_yaml,
                    source.yaml_signature,
                )
                created.append(source_yaml)
                self._copy_regular_snapshot(
                    source.image_path,
                    target_pgm,
                    source.image_signature,
                )
                created.append(target_pgm)
                rewritten = self._rewrite_yaml_image(
                    source_yaml.read_text(encoding="utf-8"),
                    target_pgm.name,
                ).encode("utf-8")
                if len(rewritten) > self.max_file_bytes:
                    raise SavedMapFormatError(
                        "navigation map YAML exceeds the configured limit"
                    )
                self._write_exclusive(target_yaml, rewritten)
                created.append(target_yaml)
                source_yaml.unlink()
                created.remove(source_yaml)

                # Exact source signatures must still match after both copies.
                if (
                    self._regular_signature(source.yaml_path)
                    != source.yaml_signature
                    or self._regular_signature(source.image_path)
                    != source.image_signature
                    or self._signature_revision(
                        (source.yaml_path, source.image_path)
                    )
                    != source.revision
                ):
                    raise SavedMapConflict(
                        "saved map changed while preparing navigation"
                    )

                metadata = self._read_map_yaml(target_yaml)
                magic, width, height, maximum = self._read_pgm_header(target_pgm)
                if (
                    metadata["image"] != target_pgm.name
                    or metadata["mode"] != "trinary"
                    or magic != "P5"
                    or maximum != 255
                ):
                    raise SavedMapFormatError(
                        "navigation map snapshot did not pass validation"
                    )
                if width * height > self.max_grid_cells:
                    raise SavedMapFormatError(
                        "navigation map exceeds the configured cell limit"
                    )
                image_width, image_height, pixels = self._read_pgm(
                    target_pgm,
                    pixels=True,
                )
                if (image_width, image_height) != (width, height) or pixels is None:
                    raise SavedMapFormatError(
                        "navigation map image dimensions changed"
                    )
                grid = self._pixels_to_occupancy(pixels, metadata)
                encoded = bytes(
                    255 if int(value) == -1 else int(value)
                    for value in grid.reshape(-1)
                )
                family = source.family
                return NavigationMapSnapshot(
                    map_id=source.map_id,
                    revision=source.revision,
                    name=source.name,
                    frame_id=source.frame_id,
                    yaml_path=target_yaml,
                    image_path=target_pgm,
                    width=width,
                    height=height,
                    resolution=float(metadata["resolution"]),
                    origin=tuple(float(value) for value in metadata["origin"]),
                    occupancy=encoded,
                    family_id=family["family_id"] if family else None,
                    family_revision=family["family_revision"] if family else None,
                    source_pcd_id=family["source"]["pcd_map_id"] if family else None,
                    source_pcd_revision=(
                        family["source"]["pcd_revision"] if family else None
                    ),
                    occupancy_map_id=(
                        family["occupancy"]["map_id"] if family else None
                    ),
                    occupancy_map_revision=(
                        family["occupancy"]["map_revision"] if family else None
                    ),
                )
            except SavedMapError:
                for path in reversed(created):
                    try:
                        path.unlink()
                    except OSError:
                        pass
                raise
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                for path in reversed(created):
                    try:
                        path.unlink()
                    except OSError:
                        pass
                raise SavedMapMutationError(
                    "navigation map snapshot could not be created"
                ) from exc

    def data(
        self,
        map_id: str,
        max_points: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return normalized map data.

        ``max_points=None`` requests every usable saved point.  A positive
        integer requests an evenly distributed subset no larger than that
        value.  Occupancy maps do not use the point-cloud response limit.
        """

        with self._lock:
            record = self._find(map_id)
            try:
                self._validate_record(record)
                if record.format == "pcd-binary":
                    payload = self._pcd_snapshot(
                        record,
                        self._point_limit(max_points),
                    )
                elif record.format == "robot-scope-json":
                    payload = self._json_snapshot(
                        record,
                        self._point_limit(max_points),
                    )
                elif record.format == "map-server-pgm":
                    payload = self._occupancy_snapshot(record)
                else:
                    raise SavedMapFormatError(
                        f"unsupported saved map format: {record.format}"
                    )
                payload["revision"] = record.revision
                return payload
            except SavedMapError:
                raise
            except (OSError, ValueError, TypeError, OverflowError, UnicodeError) as exc:
                raise SavedMapFormatError("saved map data could not be read") from exc

    def _annotation_record(self, map_id: str) -> SavedMapRecord:
        record = self._find(map_id)
        self._require_manageable(record)
        if record.format != "map-server-pgm" or record.auxiliary_path is None:
            raise SavedMapFormatError(
                "annotations require a managed 2D occupancy map"
            )
        self._require_editable_record(record)
        return record

    @staticmethod
    def _annotation_path(record: SavedMapRecord) -> Path:
        return record.path.with_name(f"{record.path.stem}.annotations.json")

    @staticmethod
    def _lineage_path(record: SavedMapRecord) -> Path:
        return record.path.with_name(f"{record.path.stem}.map-family.json")

    @staticmethod
    def _lineage_target(root: Path, name: str) -> Path:
        return root / f"{name}.map-family.json"

    def _read_lineage_path(self, root: Path, path: Path) -> Dict[str, Any]:
        try:
            candidate = path.lstat()
            if (
                not stat.S_ISREG(candidate.st_mode)
                or path.is_symlink()
                or candidate.st_uid != os.geteuid()
                or stat.S_IMODE(candidate.st_mode) & 0o077
                or candidate.st_size <= 0
                or candidate.st_size > MAX_LINEAGE_DOCUMENT_BYTES
                or path.resolve(strict=True).parent != root
            ):
                raise SavedMapReadOnly("map-family sidecar is unsafe")
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(path, flags)
            try:
                current = os.fstat(descriptor)
                if self._stat_signature(current) != self._stat_signature(candidate):
                    raise SavedMapConflict("map-family sidecar changed while reading")
                payload = os.read(descriptor, current.st_size + 1)
                if len(payload) != current.st_size:
                    raise SavedMapFormatError("map-family sidecar is truncated")
            finally:
                os.close(descriptor)
            return parse_family_document(json.loads(payload.decode("utf-8")))
        except SavedMapError:
            raise
        except MapLineageError as exc:
            raise SavedMapFormatError(str(exc)) from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SavedMapFormatError("map-family sidecar could not be read safely") from exc

    def _read_lineage(self, record: SavedMapRecord) -> Optional[Dict[str, Any]]:
        path = self._lineage_path(record)
        if not os.path.lexists(path):
            return None
        document = self._read_lineage_path(record.root, path)
        occupancy = document["occupancy"]
        if occupancy["map_id"] != record.map_id or occupancy["map_revision"] != record.revision:
            raise SavedMapConflict("map-family occupancy pin does not match the saved map")
        return document

    def _scan_lineage_documents(self) -> list[Dict[str, Any]]:
        documents: list[Dict[str, Any]] = []
        maximum = max(1, self.max_files)
        for root in self.managed_roots:
            count = 0
            for current, directories, files in os.walk(root, followlinks=False):
                current_path = Path(current)
                depth = len(current_path.relative_to(root).parts)
                directories[:] = [
                    name
                    for name in directories
                    if not name.startswith(".") and depth < self.max_depth
                ]
                if depth > self.max_depth:
                    continue
                for name in files:
                    if name.startswith(".") or not name.endswith(".map-family.json"):
                        continue
                    documents.append(self._read_lineage_path(root, current_path / name))
                    count += 1
                    if count >= maximum:
                        break
                if count >= maximum:
                    break
        return documents

    def _stage_lineage(self, transaction: Path, document: Dict[str, Any]) -> Path:
        staged = transaction / "map-family.json"
        try:
            self._write_exclusive(staged, serialize_family_document(document))
        except MapLineageError as exc:
            raise SavedMapFormatError(str(exc)) from exc
        return staged

    def _annotation_geometry(self, record: SavedMapRecord) -> NavigationMapSnapshot:
        metadata = self._read_map_yaml(record.path)
        width, height, pixels = self._read_pgm(record.auxiliary_path, pixels=True)
        if pixels is None or width * height > self.max_grid_cells:
            raise SavedMapFormatError("annotation map geometry is unavailable")
        occupancy = self._pixels_to_occupancy(pixels, metadata)
        encoded = bytes(
            255 if int(value) == -1 else int(value)
            for value in occupancy.reshape(-1)
        )
        return NavigationMapSnapshot(
            map_id=record.map_id,
            revision=record.revision,
            name=record.name,
            frame_id=str(record.details.get("frame_id", "map")) or "map",
            yaml_path=record.path,
            image_path=record.auxiliary_path,
            width=width,
            height=height,
            resolution=float(metadata["resolution"]),
            origin=tuple(float(value) for value in metadata["origin"]),
            occupancy=encoded,
        )

    def _read_annotations(
        self,
        record: SavedMapRecord,
        geometry: NavigationMapSnapshot,
    ) -> Dict[str, Any]:
        path = self._annotation_path(record)
        if not os.path.lexists(path):
            return empty_annotation_document(record.map_id, record.revision)
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = -1
        try:
            descriptor = os.open(path, flags)
            current = os.fstat(descriptor)
            if (
                not stat.S_ISREG(current.st_mode)
                or current.st_uid != os.geteuid()
                or stat.S_IMODE(current.st_mode) & 0o077
                or current.st_size <= 0
                or current.st_size > MAX_DOCUMENT_BYTES
            ):
                raise SavedMapReadOnly("annotation file is unsafe")
            chunks: list[bytes] = []
            remaining = current.st_size
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    raise SavedMapFormatError("annotation file is truncated")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise SavedMapFormatError("annotation file changed while reading")
            payload = json.loads(b"".join(chunks).decode("utf-8"))
            return parse_annotation_document(payload, geometry=geometry)
        except SavedMapError:
            raise
        except MapAnnotationConflict as exc:
            raise SavedMapConflict(str(exc)) from exc
        except MapAnnotationError as exc:
            raise SavedMapFormatError(str(exc)) from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SavedMapFormatError("annotation file could not be read safely") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def _publish_annotations(self, record: SavedMapRecord, encoded: bytes) -> None:
        if len(encoded) <= 0 or len(encoded) > MAX_DOCUMENT_BYTES:
            raise SavedMapFormatError("annotation document exceeds the size limit")
        path = self._annotation_path(record)
        target_signature: tuple[int, int, int, int] | None = None
        if os.path.lexists(path):
            try:
                current = path.lstat()
            except OSError as exc:
                raise SavedMapMutationError(
                    "annotation target could not be inspected"
                ) from exc
            if (
                not stat.S_ISREG(current.st_mode)
                or path.is_symlink()
                or current.st_uid != os.geteuid()
                or stat.S_IMODE(current.st_mode) & 0o077
            ):
                raise SavedMapReadOnly("annotation target is unsafe")
            target_signature = self._stat_signature(current)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = -1
        try:
            descriptor = os.open(temporary, flags, 0o600)
            view = memoryview(encoded)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("annotation write made no progress")
                view = view[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            # The map pins are checked again immediately before publication.
            current_record = self._record_for(record.root, record.path)
            if (
                current_record is None
                or current_record.map_id != record.map_id
                or current_record.revision != record.revision
            ):
                raise SavedMapConflict(
                    "saved map changed before annotations were published"
                )
            if target_signature is None:
                if os.path.lexists(path):
                    raise SavedMapConflict(
                        "annotations changed before they were published"
                    )
            elif (
                not os.path.lexists(path)
                or self._regular_signature(path) != target_signature
            ):
                raise SavedMapConflict(
                    "annotations changed before they were published"
                )
            os.replace(temporary, path)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except SavedMapError:
            raise
        except OSError as exc:
            raise SavedMapMutationError(
                "annotations could not be published atomically"
            ) from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                temporary.unlink()
            except OSError:
                pass

    def _point_limit(self, max_points: Optional[int]) -> Optional[int]:
        if max_points is None:
            return None
        if isinstance(max_points, bool) or not isinstance(max_points, int):
            raise SavedMapPointLimitError("max_points must be a positive integer or null")
        if max_points <= 0:
            raise SavedMapPointLimitError("max_points must be a positive integer or null")
        if max_points > self.max_requested_points:
            raise SavedMapPointLimitError(
                f"max_points exceeds the configured limit of {self.max_requested_points}"
            )
        return max_points

    def rename(self, map_id: str, new_name: str) -> Dict[str, Any]:
        """Rename one managed map without allowing a target to be replaced.

        An occupancy map is a logical YAML/PGM pair.  Both files are published
        under the new stem and the YAML image reference is rewritten before the
        old pair is removed.  Hidden hard-link backups make ordinary I/O
        failures rollback-safe without copying a potentially large PCD.
        """

        safe_name = self.validate_map_name(new_name)
        with self._lock:
            record = self._find(map_id)
            self._require_manageable(record)
            if safe_name == record.name:
                return record.public()

            target_primary = record.path.with_name(f"{safe_name}{record.path.suffix}")
            target_auxiliary = (
                record.auxiliary_path.with_name(
                    f"{safe_name}{record.auxiliary_path.suffix}"
                )
                if record.auxiliary_path is not None
                else None
            )
            targets = [target_primary]
            if target_auxiliary is not None:
                targets.append(target_auxiliary)
            annotation_document: Dict[str, Any] | None = None
            lineage_document: Dict[str, Any] | None = None
            source_annotation: Path | None = None
            source_lineage: Path | None = None
            target_annotation: Path | None = None
            target_lineage: Path | None = None
            annotation_geometry: NavigationMapSnapshot | None = None
            if record.format == "map-server-pgm":
                lineage_document = self._read_lineage(record)
                if lineage_document is not None:
                    source_lineage = self._lineage_path(record)
                    target_lineage = self._lineage_target(record.root, safe_name)
                    targets.append(target_lineage)
                source_annotation = self._annotation_path(record)
                if os.path.lexists(source_annotation):
                    annotation_geometry = self._annotation_geometry(record)
                    annotation_document = self._read_annotations(
                        record,
                        annotation_geometry,
                    )
                    target_annotation = target_primary.with_name(
                        f"{target_primary.stem}.annotations.json"
                    )
                    targets.append(target_annotation)
            self._ensure_targets_absent(targets)

            shared_auxiliary = (
                record.auxiliary_path is not None
                and self._auxiliary_has_other_reference(record)
            )
            sources = [record.path]
            if record.auxiliary_path is not None:
                sources.append(record.auxiliary_path)
            if source_annotation is not None and annotation_document is not None:
                sources.append(source_annotation)
            if source_lineage is not None and lineage_document is not None:
                sources.append(source_lineage)
            remove_sources = [record.path]
            if record.auxiliary_path is not None and not shared_auxiliary:
                remove_sources.append(record.auxiliary_path)
            if source_annotation is not None and annotation_document is not None:
                remove_sources.append(source_annotation)
            if source_lineage is not None and lineage_document is not None:
                remove_sources.append(source_lineage)

            transaction_root, transaction = self._create_transaction(record.root)
            backups: Dict[Path, Path] = {}
            source_identities: Dict[Path, tuple[int, int]] = {}
            published: Dict[Path, tuple[int, int]] = {}
            try:
                backups, source_identities = self._backup_sources(transaction, sources)
                if target_auxiliary is None:
                    published[target_primary] = self._publish_link(
                        record.path,
                        target_primary,
                    )
                else:
                    staged_yaml = self._stage_renamed_yaml(
                        record,
                        transaction,
                        target_auxiliary.name,
                    )
                    if lineage_document is not None and target_lineage is not None:
                        renamed_lineage = build_family_document(
                            family_id=lineage_document["family_id"],
                            mapping_session_id=lineage_document["source"]["mapping_session_id"],
                            pcd_map_id=lineage_document["source"]["pcd_map_id"],
                            pcd_revision=lineage_document["source"]["pcd_revision"],
                            source_frame_id=lineage_document["source"]["frame_id"],
                            occupancy_map_id=self._opaque_id(record.kind, target_primary),
                            occupancy_revision=self._signature_revision(
                                (staged_yaml, record.auxiliary_path)
                            ),
                            occupancy_frame_id=lineage_document["occupancy"]["frame_id"],
                            resolution=lineage_document["occupancy"]["resolution"],
                            width=lineage_document["occupancy"]["width"],
                            height=lineage_document["occupancy"]["height"],
                            origin=lineage_document["occupancy"]["origin"],
                            parameters={
                                key: lineage_document["conversion"][key]
                                for key in (
                                    "z_min", "z_max", "resolution", "noise_radius",
                                    "min_neighbors", "background",
                                )
                            },
                            derived_from_family_revision=lineage_document["family_revision"],
                        )
                        staged_lineage = self._stage_lineage(
                            transaction, renamed_lineage
                        )
                        published[target_lineage] = self._publish_link(
                            staged_lineage, target_lineage
                        )
                    if (
                        annotation_document is not None
                        and annotation_geometry is not None
                        and target_annotation is not None
                    ):
                        target_revision = self._signature_revision(
                            (staged_yaml, record.auxiliary_path)
                        )
                        target_map_id = self._opaque_id(record.kind, target_primary)
                        target_geometry = NavigationMapSnapshot(
                            map_id=target_map_id,
                            revision=target_revision,
                            name=safe_name,
                            frame_id=annotation_geometry.frame_id,
                            yaml_path=staged_yaml,
                            image_path=record.auxiliary_path,
                            width=annotation_geometry.width,
                            height=annotation_geometry.height,
                            resolution=annotation_geometry.resolution,
                            origin=annotation_geometry.origin,
                            occupancy=annotation_geometry.occupancy,
                        )
                        try:
                            migrated = normalize_annotation_document(
                                map_id=target_map_id,
                                map_revision=target_revision,
                                points=annotation_document["points"],
                                polygons=annotation_document["polygons"],
                                geometry=target_geometry,
                                exists=True,
                            )
                            staged_annotation = transaction / "renamed.annotations.json"
                            self._write_exclusive(
                                staged_annotation,
                                serialized_annotation_document(migrated),
                            )
                        except MapAnnotationError as exc:
                            raise SavedMapFormatError(str(exc)) from exc
                        # Publish the sidecar first; it is undiscoverable until
                        # the target YAML appears, so clients never see an
                        # unpinned annotation document for the renamed map.
                        published[target_annotation] = self._publish_link(
                            staged_annotation,
                            target_annotation,
                        )
                    published[target_auxiliary] = self._publish_link(
                        record.auxiliary_path,
                        target_auxiliary,
                    )
                    published[target_primary] = self._publish_link(
                        staged_yaml,
                        target_primary,
                    )

                renamed = self._record_for(record.root, target_primary)
                if renamed is None or not renamed.manageable:
                    raise SavedMapMutationError("renamed map did not pass validation")
                self._validate_record(renamed)
                if annotation_document is not None:
                    self._read_annotations(
                        renamed,
                        self._annotation_geometry(renamed),
                    )
                if lineage_document is not None:
                    self._read_lineage(renamed)
                for source in remove_sources:
                    self._unlink_verified(source, source_identities[source])
            except SavedMapError:
                rolled_back = self._rollback_mutation(backups, published)
                if rolled_back:
                    self._cleanup_transaction(transaction_root, transaction)
                else:
                    raise SavedMapMutationError(
                        "saved map rename failed and requires manual recovery"
                    )
                raise
            except (OSError, ValueError, TypeError, UnicodeError) as exc:
                rolled_back = self._rollback_mutation(backups, published)
                if rolled_back:
                    self._cleanup_transaction(transaction_root, transaction)
                else:
                    raise SavedMapMutationError(
                        "saved map rename failed and requires manual recovery"
                    ) from exc
                raise SavedMapMutationError("saved map could not be renamed safely") from exc

            self._cleanup_transaction(transaction_root, transaction)
            return renamed.public()

    def delete(self, map_id: str) -> Dict[str, Any]:
        """Delete one managed logical map, rolling back a partial pair removal."""

        with self._lock:
            record = self._find(map_id)
            self._require_manageable(record)
            shared_auxiliary = (
                record.auxiliary_path is not None
                and self._auxiliary_has_other_reference(record)
            )
            sources = [record.path]
            if record.auxiliary_path is not None and not shared_auxiliary:
                sources.append(record.auxiliary_path)
            if record.format == "map-server-pgm":
                lineage_path = self._lineage_path(record)
                if os.path.lexists(lineage_path):
                    self._read_lineage(record)
                    sources.append(lineage_path)
                annotation_path = self._annotation_path(record)
                if os.path.lexists(annotation_path):
                    # Validate pins, ownership, type and permissions before
                    # adding the sidecar to the rollback-safe delete set.
                    self._read_annotations(record, self._annotation_geometry(record))
                    sources.append(annotation_path)

            transaction_root, transaction = self._create_transaction(record.root)
            backups: Dict[Path, Path] = {}
            source_identities: Dict[Path, tuple[int, int]] = {}
            try:
                backups, source_identities = self._backup_sources(transaction, sources)
                for source in sources:
                    self._unlink_verified(source, source_identities[source])
            except SavedMapError:
                rolled_back = self._rollback_mutation(backups, {})
                if rolled_back:
                    self._cleanup_transaction(transaction_root, transaction)
                else:
                    raise SavedMapMutationError(
                        "saved map delete failed and requires manual recovery"
                    )
                raise
            except OSError as exc:
                rolled_back = self._rollback_mutation(backups, {})
                if rolled_back:
                    self._cleanup_transaction(transaction_root, transaction)
                else:
                    raise SavedMapMutationError(
                        "saved map delete failed and requires manual recovery"
                    ) from exc
                raise SavedMapMutationError("saved map could not be deleted safely") from exc

            self._cleanup_transaction(transaction_root, transaction)
            return {
                "deleted": True,
                "id": record.map_id,
                "name": record.name,
                "kind": record.kind,
                "files": [path.name for path in sources],
            }

    def validate_pcd_conversion(
        self,
        map_id: str,
        name: str,
        *,
        z_min: object,
        z_max: object,
        resolution: object,
        noise_radius: object = 0.1,
        min_neighbors: object = 10,
        background: object = "unknown",
    ) -> Dict[str, Any]:
        """Validate a managed PCD conversion without exposing its path."""

        safe_name = self.validate_map_name(name)
        parameters = self._conversion_parameters(
            z_min=z_min,
            z_max=z_max,
            resolution=resolution,
            noise_radius=noise_radius,
            min_neighbors=min_neighbors,
            background=background,
        )
        with self._lock:
            record = self._find(map_id)
            self._require_manageable(record)
            if record.format != "pcd-binary":
                raise SavedMapFormatError("only a managed binary PCD can be converted")
            if int(record.details.get("point_count", 0)) > self.max_full_view_points:
                raise SavedMapPointLimitError(
                    "PCD conversion exceeds the configured point limit of "
                    f"{self.max_full_view_points}"
                )
            self._ensure_targets_absent(self._occupancy_targets(record.root, safe_name))
            return {
                "source": record.public(),
                "output_name": safe_name,
                "parameters": parameters,
                "filter": "projected_xy_density",
            }

    def convert_pcd_to_2d(
        self,
        map_id: str,
        name: str,
        *,
        z_min: object,
        z_max: object,
        resolution: object,
        noise_radius: object = 0.1,
        min_neighbors: object = 10,
        background: object = "unknown",
        expected_revision: Optional[str] = None,
        cancelled: Optional[Callable[[], bool]] = None,
        publication_guard: Optional[Callable[[], ContextManager[bool]]] = None,
    ) -> Dict[str, Any]:
        """Create a new map-server PGM/YAML pair from one managed binary PCD.

        The automatic filter is deliberately described as a projected XY
        density filter.  It is not PCL's 3D RadiusOutlierRemoval.  Manual brush
        edits are a separate :meth:`save_edited_copy` operation.
        """

        safe_name = self.validate_map_name(name)
        parameters = self._conversion_parameters(
            z_min=z_min,
            z_max=z_max,
            resolution=resolution,
            noise_radius=noise_radius,
            min_neighbors=min_neighbors,
            background=background,
        )
        if expected_revision is not None and (
            not isinstance(expected_revision, str)
            or not REVISION_RE.fullmatch(expected_revision)
        ):
            raise SavedMapFormatError(
                "expected_revision must be a 64-character lowercase hex string"
            )
        with self._lock:
            record = self._find(map_id)
            self._require_manageable(record)
            if record.format != "pcd-binary":
                raise SavedMapFormatError("only a managed binary PCD can be converted")
            if int(record.details.get("point_count", 0)) > self.max_full_view_points:
                raise SavedMapPointLimitError(
                    "PCD conversion exceeds the configured point limit of "
                    f"{self.max_full_view_points}"
                )
            if expected_revision is not None and expected_revision != record.revision:
                raise SavedMapConflict(
                    "saved PCD changed; validate it again before conversion"
                )
            if self._operation_cancelled(cancelled):
                raise SavedMapMutationError("PCD conversion was cancelled")
            targets = (*self._occupancy_targets(record.root, safe_name), self._lineage_target(record.root, safe_name))
            self._ensure_targets_absent(targets)
            source_signature = self._regular_signature(record.path)
            source_revision = record.revision
            transaction_root, transaction = self._create_transaction(record.root)
            source_snapshot = transaction / "source.pcd"
            try:
                self._copy_regular_snapshot(
                    record.path,
                    source_snapshot,
                    source_signature,
                )
            except Exception:
                self._cleanup_transaction(transaction_root, transaction)
                raise

        published: Dict[Path, tuple[int, int]] = {}
        try:
            points, source_points = self._pcd_xyz(source_snapshot)
            pixels, details = self._project_xy_occupancy(points, parameters)
            staged_yaml, staged_pgm = self._stage_occupancy_pair(
                transaction,
                safe_name,
                pixels,
                resolution=parameters["resolution"],
                origin=(details["origin_x"], details["origin_y"], 0.0),
                occupied_thresh=0.65,
                free_thresh=0.196,
            )
            target_yaml, _ = self._occupancy_targets(record.root, safe_name)
            target_revision = self._signature_revision((staged_yaml, staged_pgm))
            lineage = build_family_document(
                family_id=secrets.token_hex(12),
                mapping_session_id=secrets.token_hex(12),
                pcd_map_id=record.map_id,
                pcd_revision=source_revision,
                source_frame_id=str(record.details.get("frame_id", "camera_init")),
                occupancy_map_id=self._opaque_id("occupancy2d", target_yaml),
                occupancy_revision=target_revision,
                occupancy_frame_id="map",
                resolution=parameters["resolution"],
                width=int(details["width"]),
                height=int(details["height"]),
                origin=(float(details["origin_x"]), float(details["origin_y"]), 0.0),
                parameters=parameters,
            )
            staged_lineage = self._stage_lineage(transaction, lineage)

            with self._lock:
                if self._regular_signature(record.path) != source_signature:
                    raise SavedMapMutationError("PCD changed during conversion")
                self._ensure_targets_absent(targets)
                if publication_guard is None:
                    if self._operation_cancelled(cancelled):
                        raise SavedMapMutationError(
                            "PCD conversion was cancelled before publication"
                        )
                    lineage_target = self._lineage_target(record.root, safe_name)
                    published[lineage_target] = self._publish_link(
                        staged_lineage, lineage_target
                    )
                    created = self._publish_occupancy_pair(
                        record.root,
                        safe_name,
                        staged_yaml,
                        staged_pgm,
                        published,
                    )
                else:
                    with publication_guard() as authorized:
                        if not authorized:
                            raise SavedMapMutationError(
                                "PCD conversion was cancelled before publication"
                            )
                        lineage_target = self._lineage_target(record.root, safe_name)
                        published[lineage_target] = self._publish_link(
                            staged_lineage, lineage_target
                        )
                        created = self._publish_occupancy_pair(
                            record.root,
                            safe_name,
                            staged_yaml,
                            staged_pgm,
                            published,
                        )
        except SavedMapError:
            rolled_back = self._rollback_mutation({}, published)
            if rolled_back:
                self._cleanup_transaction(transaction_root, transaction)
            else:
                raise SavedMapMutationError(
                    "PCD conversion failed and requires manual recovery"
                )
            raise
        except (OSError, ValueError, TypeError, OverflowError, UnicodeError) as exc:
            rolled_back = self._rollback_mutation({}, published)
            if rolled_back:
                self._cleanup_transaction(transaction_root, transaction)
            else:
                raise SavedMapMutationError(
                    "PCD conversion failed and requires manual recovery"
                ) from exc
            raise SavedMapMutationError("PCD could not be converted safely") from exc
        else:
            self._cleanup_transaction(transaction_root, transaction)
            conversion = {
                "filter": "projected_xy_density",
                "result_map_id": created.map_id,
                "source_revision": source_revision,
                "source_points": source_points,
                **details,
                **parameters,
            }
            public = created.public()
            public["map_family"] = public_family_document(lineage)
            public["conversion"] = conversion
            return {
                "map": public,
                "files": [
                    created.path.name,
                    created.auxiliary_path.name if created.auxiliary_path else "",
                ],
                "details": conversion,
            }

    def save_edited_copy(
        self,
        map_id: str,
        name: str,
        source_revision: str,
        runs: Iterable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Publish bounded RLE brush edits as a new occupancy-map pair."""

        safe_name = self.validate_map_name(name)
        if not isinstance(source_revision, str) or not REVISION_RE.fullmatch(source_revision):
            raise SavedMapFormatError("source_revision must be a 64-character lowercase hex string")
        with self._lock:
            record = self._find(map_id)
            self._require_manageable(record)
            if record.format != "map-server-pgm" or record.auxiliary_path is None:
                raise SavedMapFormatError("only a managed 2D occupancy map can be edited")
            self._require_editable_record(record)
            if source_revision != record.revision:
                raise SavedMapConflict("saved map changed; reload it before saving edits")
            source_lineage = self._read_lineage(record)
            targets = (*self._occupancy_targets(record.root, safe_name), self._lineage_target(record.root, safe_name))
            self._ensure_targets_absent(targets)

            yaml_signature = self._regular_signature(record.path)
            pgm_signature = self._regular_signature(record.auxiliary_path)
            transaction_root, transaction = self._create_transaction(record.root)
            yaml_snapshot = transaction / "source.yaml"
            pgm_snapshot = transaction / "source.pgm"
            try:
                self._copy_regular_snapshot(record.path, yaml_snapshot, yaml_signature)
                self._copy_regular_snapshot(
                    record.auxiliary_path,
                    pgm_snapshot,
                    pgm_signature,
                )
            except Exception:
                self._cleanup_transaction(transaction_root, transaction)
                raise

        published: Dict[Path, tuple[int, int]] = {}
        try:
            metadata = self._read_map_yaml(yaml_snapshot)
            pgm_magic, header_width, header_height, pgm_maximum = self._read_pgm_header(
                pgm_snapshot
            )
            if metadata["mode"] != "trinary":
                raise SavedMapFormatError("only absent/trinary map mode is editable")
            if pgm_magic != "P5":
                raise SavedMapFormatError("only binary P5 occupancy images are editable")
            if pgm_maximum != 255:
                raise SavedMapFormatError("only 8-bit maxval=255 occupancy images are editable")
            width, height, source_pixels = self._read_pgm(pgm_snapshot, pixels=True)
            if (width, height) != (header_width, header_height):
                raise SavedMapFormatError("occupancy image header changed during editing")
            assert source_pixels is not None
            normalized_runs = self._validate_edit_runs(runs, width * height)
            output_pixels = np.rint(source_pixels * 255.0).astype(np.uint8)
            edited_cells = self._apply_edit_runs(
                output_pixels,
                width,
                height,
                normalized_runs,
                metadata,
            )
            staged_yaml, staged_pgm = self._stage_occupancy_pair(
                transaction,
                safe_name,
                output_pixels,
                resolution=metadata["resolution"],
                origin=tuple(metadata["origin"]),
                occupied_thresh=metadata["occupied_thresh"],
                free_thresh=metadata["free_thresh"],
                negate=metadata["negate"],
            )
            lineage: Optional[Dict[str, Any]] = None
            staged_lineage: Optional[Path] = None
            if source_lineage is not None:
                target_yaml, _ = self._occupancy_targets(record.root, safe_name)
                lineage = build_family_document(
                    family_id=source_lineage["family_id"],
                    mapping_session_id=source_lineage["source"]["mapping_session_id"],
                    pcd_map_id=source_lineage["source"]["pcd_map_id"],
                    pcd_revision=source_lineage["source"]["pcd_revision"],
                    source_frame_id=source_lineage["source"]["frame_id"],
                    occupancy_map_id=self._opaque_id("occupancy2d", target_yaml),
                    occupancy_revision=self._signature_revision((staged_yaml, staged_pgm)),
                    occupancy_frame_id=str(record.details.get("frame_id", "map")),
                    resolution=float(metadata["resolution"]),
                    width=width,
                    height=height,
                    origin=tuple(float(value) for value in metadata["origin"]),
                    parameters={
                        key: source_lineage["conversion"][key]
                        for key in (
                            "z_min", "z_max", "resolution", "noise_radius",
                            "min_neighbors", "background",
                        )
                    },
                    derived_from_family_revision=source_lineage["family_revision"],
                )
                staged_lineage = self._stage_lineage(transaction, lineage)

            with self._lock:
                if (
                    self._regular_signature(record.path) != yaml_signature
                    or self._regular_signature(record.auxiliary_path) != pgm_signature
                ):
                    raise SavedMapMutationError("2D map changed while applying edits")
                self._ensure_targets_absent(targets)
                if staged_lineage is not None:
                    lineage_target = self._lineage_target(record.root, safe_name)
                    published[lineage_target] = self._publish_link(
                        staged_lineage, lineage_target
                    )
                created = self._publish_occupancy_pair(
                    record.root,
                    safe_name,
                    staged_yaml,
                    staged_pgm,
                    published,
                )
        except SavedMapError:
            rolled_back = self._rollback_mutation({}, published)
            if rolled_back:
                self._cleanup_transaction(transaction_root, transaction)
            else:
                raise SavedMapMutationError(
                    "edited map save failed and requires manual recovery"
                )
            raise
        except (OSError, ValueError, TypeError, OverflowError, UnicodeError) as exc:
            rolled_back = self._rollback_mutation({}, published)
            if rolled_back:
                self._cleanup_transaction(transaction_root, transaction)
            else:
                raise SavedMapMutationError(
                    "edited map save failed and requires manual recovery"
                ) from exc
            raise SavedMapMutationError("edited map could not be saved safely") from exc
        else:
            self._cleanup_transaction(transaction_root, transaction)
            public = created.public()
            public["edit"] = {
                "source_revision": source_revision,
                "run_count": len(normalized_runs),
                "edited_cells": edited_cells,
            }
            if lineage is not None:
                public["map_family"] = public_family_document(lineage)
            return public

    @staticmethod
    def validate_map_name(name: str) -> str:
        if not isinstance(name, str) or not MAP_NAME_RE.fullmatch(name):
            raise SavedMapInvalidName(
                "map name must be 1-64 ASCII letters, numbers, underscores or hyphens"
            )
        return name

    @staticmethod
    def _finite_parameter(value: object, label: str, low: float, high: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SavedMapFormatError(f"{label} must be a finite number")
        normalized = float(value)
        if not np.isfinite(normalized):
            raise SavedMapFormatError(f"{label} must be a finite number")
        if normalized < low or normalized > high:
            raise SavedMapFormatError(f"{label} must be between {low:g} and {high:g}")
        return normalized

    @staticmethod
    def _operation_cancelled(callback: Optional[Callable[[], bool]]) -> bool:
        if callback is None:
            return False
        try:
            return bool(callback())
        except Exception:
            # A broken lifecycle callback cannot authorize publication.
            return True

    @classmethod
    def _conversion_parameters(
        cls,
        *,
        z_min: object,
        z_max: object,
        resolution: object,
        noise_radius: object,
        min_neighbors: object,
        background: object,
    ) -> Dict[str, Any]:
        lower = cls._finite_parameter(z_min, "z_min", -PCD_Z_LIMIT_M, PCD_Z_LIMIT_M)
        upper = cls._finite_parameter(z_max, "z_max", -PCD_Z_LIMIT_M, PCD_Z_LIMIT_M)
        if lower >= upper:
            raise SavedMapFormatError("z_min must be less than z_max")
        cell_size = cls._finite_parameter(
            resolution,
            "resolution",
            MIN_MAP_RESOLUTION_M,
            MAX_MAP_RESOLUTION_M,
        )
        radius = cls._finite_parameter(
            noise_radius,
            "noise_radius",
            MIN_NOISE_RADIUS_M,
            MAX_NOISE_RADIUS_M,
        )
        if (
            isinstance(min_neighbors, bool)
            or not isinstance(min_neighbors, int)
            or min_neighbors < 1
            or min_neighbors > MAX_NOISE_NEIGHBORS
        ):
            raise SavedMapFormatError(
                f"min_neighbors must be an integer from 1 to {MAX_NOISE_NEIGHBORS}"
            )
        if not isinstance(background, str) or background not in BACKGROUND_MODES:
            raise SavedMapFormatError("background must be 'unknown' or 'free'")
        return {
            "z_min": lower,
            "z_max": upper,
            "resolution": cell_size,
            "noise_radius": radius,
            "min_neighbors": min_neighbors,
            "background": background,
        }

    @staticmethod
    def _occupancy_targets(root: Path, name: str) -> tuple[Path, Path]:
        return root / f"{name}.yaml", root / f"{name}.pgm"

    @staticmethod
    def _stat_signature(current: os.stat_result) -> tuple[int, int, int, int]:
        if not stat.S_ISREG(current.st_mode):
            raise SavedMapReadOnly("saved map artifact is not a regular file")
        return current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns

    @classmethod
    def _regular_signature(cls, path: Path) -> tuple[int, int, int, int]:
        return cls._stat_signature(path.lstat())

    @classmethod
    def _signature_revision(cls, paths: Iterable[Path]) -> str:
        digest = hashlib.sha256()
        for path in paths:
            signature = cls._regular_signature(path)
            digest.update((":".join(str(value) for value in signature) + "\n").encode("ascii"))
        return digest.hexdigest()

    def _copy_regular_snapshot(
        self,
        source: Path,
        target: Path,
        expected: tuple[int, int, int, int],
    ) -> None:
        """Copy one bounded regular file while detecting replacement races."""

        source_flags = os.O_RDONLY
        target_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            source_flags |= os.O_NOFOLLOW
            target_flags |= os.O_NOFOLLOW
        source_fd = -1
        target_fd = -1
        try:
            source_fd = os.open(source, source_flags)
            before = self._stat_signature(os.fstat(source_fd))
            if before != expected:
                raise SavedMapMutationError("saved map changed before its snapshot")
            if before[2] <= 0 or before[2] > self.max_file_bytes:
                raise SavedMapFormatError("saved map snapshot exceeds the configured limit")
            target_fd = os.open(target, target_flags, 0o600)
            target_stat = self._stat_signature(os.fstat(target_fd))
            if target_stat[:2] == before[:2]:
                raise SavedMapMutationError("saved map snapshot must be an independent copy")

            copied = 0
            while copied < before[2]:
                chunk = os.read(source_fd, min(1024 * 1024, before[2] - copied))
                if not chunk:
                    raise SavedMapMutationError("saved map changed while being copied")
                view = memoryview(chunk)
                while view:
                    written = os.write(target_fd, view)
                    if written <= 0:
                        raise SavedMapMutationError("saved map snapshot could not be written")
                    view = view[written:]
                copied += len(chunk)
            if os.read(source_fd, 1):
                raise SavedMapMutationError("saved map grew while being copied")
            os.fsync(target_fd)
            after = self._stat_signature(os.fstat(source_fd))
            snapshot = self._stat_signature(os.fstat(target_fd))
            if after != expected or snapshot[2] != expected[2]:
                raise SavedMapMutationError("saved map changed while taking its snapshot")
        except SavedMapError:
            raise
        except OSError as exc:
            raise SavedMapMutationError("saved map snapshot could not be created") from exc
        finally:
            if target_fd >= 0:
                os.close(target_fd)
            if source_fd >= 0:
                os.close(source_fd)

    def _pcd_xyz(self, path: Path) -> tuple[np.ndarray, int]:
        header = self._read_pcd_header(path)
        if header["data"] != "binary":
            raise SavedMapFormatError("only binary PCD data can be converted")
        if header["points"] > self.max_full_view_points:
            raise SavedMapPointLimitError(
                "PCD conversion exceeds the configured point limit of "
                f"{self.max_full_view_points}"
            )
        scalar_types = {
            ("F", 4): "<f4", ("F", 8): "<f8",
            ("I", 1): "i1", ("I", 2): "<i2", ("I", 4): "<i4",
            ("U", 1): "u1", ("U", 2): "<u2", ("U", 4): "<u4",
        }
        names: list[str] = []
        formats: list[str] = []
        offsets: list[int] = []
        point_step = 0
        for name, size, kind, count in zip(
            header["fields"], header["sizes"], header["types"], header["counts"]
        ):
            scalar = scalar_types.get((kind, size))
            if scalar is None or count != 1:
                raise SavedMapFormatError(
                    f"unsupported PCD field: {name} {kind}{size}x{count}"
                )
            names.append(name)
            formats.append(scalar)
            offsets.append(point_step)
            point_step += size
        expected_size = header["data_offset"] + header["points"] * point_step
        if expected_size > path.stat().st_size:
            raise SavedMapFormatError("PCD payload is truncated")
        dtype = np.dtype(
            {
                "names": names,
                "formats": formats,
                "offsets": offsets,
                "itemsize": point_step,
            }
        )
        records = np.memmap(
            path,
            mode="r",
            dtype=dtype,
            offset=header["data_offset"],
            shape=(header["points"],),
        )
        points = np.empty((header["points"], 3), dtype=np.float32)
        points[:, 0] = records["x"]
        points[:, 1] = records["y"]
        points[:, 2] = records["z"]
        return points, header["points"]

    def _project_xy_occupancy(
        self,
        points: np.ndarray,
        parameters: Dict[str, Any],
    ) -> tuple[np.ndarray, Dict[str, Any]]:
        finite = np.isfinite(points).all(axis=1)
        height_slice = finite & (points[:, 2] >= parameters["z_min"]) & (
            points[:, 2] <= parameters["z_max"]
        )
        xy = points[height_slice, :2].astype(np.float64, copy=True)
        z_slice_points = int(len(xy))
        if not z_slice_points:
            raise SavedMapFormatError("no finite PCD points remain inside the z range")

        radius = parameters["noise_radius"]
        xy_min = np.min(xy, axis=0)
        normalized = (xy - xy_min) / radius
        if not np.isfinite(normalized).all():
            raise SavedMapFormatError("projected PCD bounds are not finite")
        max_bin = np.max(normalized, axis=0)
        integer_limit = np.iinfo(np.int64).max
        if np.any(max_bin > integer_limit - 2):
            raise SavedMapFormatError("projected PCD span is too large")
        bins = np.floor(normalized).astype(np.int64)
        span_y = int(np.max(bins[:, 1])) + 1
        max_x_bin = int(np.max(bins[:, 0]))
        if span_y <= 0 or max_x_bin > integer_limit // span_y:
            raise SavedMapFormatError("projected PCD density grid is too large")
        keys = bins[:, 0] * span_y + bins[:, 1]
        unique_keys, inverse, counts = np.unique(
            keys,
            return_inverse=True,
            return_counts=True,
        )
        unique_x = unique_keys // span_y
        unique_y = unique_keys % span_y
        density = np.zeros(len(unique_keys), dtype=np.int64)
        for x_offset in (-1, 0, 1):
            for y_offset in (-1, 0, 1):
                neighbor_x = unique_x + x_offset
                neighbor_y = unique_y + y_offset
                valid = (
                    (neighbor_x >= 0)
                    & (neighbor_x <= max_x_bin)
                    & (neighbor_y >= 0)
                    & (neighbor_y < span_y)
                )
                neighbor_keys = neighbor_x[valid] * span_y + neighbor_y[valid]
                positions = np.searchsorted(unique_keys, neighbor_keys)
                matched = positions < len(unique_keys)
                matched[matched] &= unique_keys[positions[matched]] == neighbor_keys[matched]
                valid_indexes = np.flatnonzero(valid)[matched]
                density[valid_indexes] += counts[positions[matched]]
        keep = density[inverse] >= parameters["min_neighbors"]
        selected = xy[keep]
        selected_points = int(len(selected))
        if not selected_points:
            raise SavedMapFormatError(
                "no PCD points remain after the projected XY density filter"
            )

        selected_min = np.min(selected, axis=0)
        selected_max = np.max(selected, axis=0)
        resolution = parameters["resolution"]
        width = int(np.floor((selected_max[0] - selected_min[0]) / resolution)) + 1
        height = int(np.floor((selected_max[1] - selected_min[1]) / resolution)) + 1
        if (
            width <= 0
            or height <= 0
            or width > self.max_grid_cells
            or height > self.max_grid_cells
            or width * height > self.max_grid_cells
        ):
            raise SavedMapFormatError(
                "converted occupancy grid exceeds the configured limit of "
                f"{self.max_grid_cells} cells"
            )

        x_indexes = np.floor((selected[:, 0] - selected_min[0]) / resolution).astype(
            np.int64
        )
        y_indexes = np.floor((selected[:, 1] - selected_min[1]) / resolution).astype(
            np.int64
        )
        np.clip(x_indexes, 0, width - 1, out=x_indexes)
        np.clip(y_indexes, 0, height - 1, out=y_indexes)
        occupied_cells = int(np.unique(y_indexes * width + x_indexes).size)
        values = self._occupancy_pixel_values(
            {
                "occupied_thresh": 0.65,
                "free_thresh": 0.196,
                "negate": 0,
            }
        )
        background_value = values[-1] if parameters["background"] == "unknown" else values[0]
        pixels = np.full((height, width), background_value, dtype=np.uint8)
        pixels[height - 1 - y_indexes, x_indexes] = values[100]
        return pixels, {
            "z_slice_points": z_slice_points,
            "selected_points": selected_points,
            "occupied_cells": occupied_cells,
            "width": width,
            "height": height,
            "origin_x": float(selected_min[0]),
            "origin_y": float(selected_min[1]),
        }

    @staticmethod
    def _write_exclusive(path: Path, content: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)

    def _stage_occupancy_pair(
        self,
        transaction: Path,
        name: str,
        pixels: np.ndarray,
        *,
        resolution: float,
        origin: tuple[float, float, float],
        occupied_thresh: float,
        free_thresh: float,
        negate: int = 0,
    ) -> tuple[Path, Path]:
        image = np.asarray(pixels, dtype=np.uint8)
        if image.ndim != 2:
            raise SavedMapFormatError("occupancy image must be two-dimensional")
        height, width = image.shape
        if width <= 0 or height <= 0 or width * height > self.max_grid_cells:
            raise SavedMapFormatError("occupancy image exceeds the configured grid limit")
        if len(origin) != 3 or not all(np.isfinite(value) for value in origin):
            raise SavedMapFormatError("occupancy origin must contain three finite values")
        if not np.isfinite(resolution) or resolution <= 0:
            raise SavedMapFormatError("occupancy resolution must be positive")
        if not (0 <= free_thresh < occupied_thresh <= 1) or negate not in {0, 1}:
            raise SavedMapFormatError("occupancy thresholds are invalid")

        staged_yaml = transaction / f"{name}.yaml"
        staged_pgm = transaction / f"{name}.pgm"
        pgm = (
            f"P5\n# Robot Scope occupancy map\n{width} {height}\n255\n".encode("ascii")
            + np.ascontiguousarray(image).tobytes()
        )
        yaml = (
            f"image: {name}.pgm\n"
            "mode: trinary\n"
            f"resolution: {resolution:.12g}\n"
            f"origin: [{origin[0]:.12g}, {origin[1]:.12g}, {origin[2]:.12g}]\n"
            f"negate: {negate}\n"
            f"occupied_thresh: {occupied_thresh:.12g}\n"
            f"free_thresh: {free_thresh:.12g}\n"
        ).encode("utf-8")
        if len(pgm) > self.max_file_bytes or len(yaml) > self.max_file_bytes:
            raise SavedMapFormatError("converted map exceeds the configured file limit")
        self._write_exclusive(staged_pgm, pgm)
        self._write_exclusive(staged_yaml, yaml)
        parsed = self._read_map_yaml(staged_yaml)
        staged_width, staged_height, _ = self._read_pgm(staged_pgm, pixels=False)
        if (
            parsed["image"] != staged_pgm.name
            or staged_width != width
            or staged_height != height
        ):
            raise SavedMapMutationError("staged occupancy pair did not pass validation")
        return staged_yaml, staged_pgm

    def _publish_occupancy_pair(
        self,
        root: Path,
        name: str,
        staged_yaml: Path,
        staged_pgm: Path,
        published: Dict[Path, tuple[int, int]],
    ) -> SavedMapRecord:
        target_yaml, target_pgm = self._occupancy_targets(root, name)
        self._ensure_targets_absent((target_yaml, target_pgm))
        # Publish the image first.  The catalog discovers the logical map only
        # after its YAML is visible, and the caller can roll back either link.
        published[target_pgm] = self._publish_link(staged_pgm, target_pgm)
        published[target_yaml] = self._publish_link(staged_yaml, target_yaml)
        created = self._record_for(root, target_yaml)
        if created is None or not created.manageable:
            raise SavedMapMutationError("new occupancy map did not pass validation")
        self._validate_record(created)
        return created

    def _validate_edit_runs(
        self,
        runs: Iterable[Dict[str, Any]],
        cells: int,
    ) -> list[tuple[int, int, int]]:
        if isinstance(runs, (str, bytes, dict)):
            raise SavedMapFormatError("runs must be a list")
        try:
            items = list(runs)
        except TypeError as exc:
            raise SavedMapFormatError("runs must be a list") from exc
        if not items or len(items) > MAX_EDIT_RUNS:
            raise SavedMapFormatError(f"runs must contain 1 to {MAX_EDIT_RUNS} entries")
        normalized: list[tuple[int, int, int]] = []
        previous_end = 0
        edited_cells = 0
        for item in items:
            if not isinstance(item, dict) or set(item) != {"start", "length", "value"}:
                raise SavedMapFormatError("each edit run requires start, length and value")
            start, length, value = item["start"], item["length"], item["value"]
            if (
                isinstance(start, bool)
                or not isinstance(start, int)
                or isinstance(length, bool)
                or not isinstance(length, int)
                or start < 0
                or length <= 0
            ):
                raise SavedMapFormatError("edit run start and length must be positive integers")
            if isinstance(value, bool) or not isinstance(value, int) or value not in {-1, 0, 100}:
                raise SavedMapFormatError("edit run value must be -1, 0 or 100")
            end = start + length
            if start < previous_end or end > cells:
                raise SavedMapFormatError("edit runs must be sorted, non-overlapping and in bounds")
            edited_cells += length
            if edited_cells > self.max_edited_cells:
                raise SavedMapFormatError(
                    "edit runs exceed the configured limit of "
                    f"{self.max_edited_cells} cells"
                )
            normalized.append((start, length, value))
            previous_end = end
        return normalized

    @staticmethod
    def _occupancy_pixel_values(metadata: Dict[str, Any]) -> Dict[int, int]:
        free = float(metadata["free_thresh"])
        occupied = float(metadata["occupied_thresh"])
        negate = int(metadata.get("negate", 0))
        raw = np.arange(256, dtype=np.float64)
        probability = raw / 255.0 if negate else 1.0 - raw / 255.0
        groups = {
            0: np.flatnonzero(probability < free),
            -1: np.flatnonzero((probability >= free) & (probability <= occupied)),
            100: np.flatnonzero(probability > occupied),
        }
        if any(not len(group) for group in groups.values()):
            raise SavedMapFormatError("map thresholds cannot encode all occupancy values")
        targets = {0: 0.0, -1: (free + occupied) / 2.0, 100: 1.0}
        return {
            value: int(group[np.argmin(np.abs(probability[group] - targets[value]))])
            for value, group in groups.items()
        }

    def _apply_edit_runs(
        self,
        pixels: np.ndarray,
        width: int,
        height: int,
        runs: Iterable[tuple[int, int, int]],
        metadata: Dict[str, Any],
    ) -> int:
        values = self._occupancy_pixel_values(metadata)
        flat = pixels.reshape(-1)
        changed = 0
        for start, length, value in runs:
            indexes = np.arange(start, start + length, dtype=np.int64)
            ros_y = indexes // width
            image_indexes = (height - 1 - ros_y) * width + indexes % width
            changed += int(np.count_nonzero(flat[image_indexes] != values[value]))
            flat[image_indexes] = values[value]
        return changed

    @staticmethod
    def _pixels_to_occupancy(pixels: np.ndarray, metadata: Dict[str, Any]) -> np.ndarray:
        occupancy_probability = pixels if metadata["negate"] else 1.0 - pixels
        height, width = pixels.shape
        grid = np.full((height, width), -1, dtype=np.int16)
        grid[occupancy_probability > metadata["occupied_thresh"]] = 100
        grid[occupancy_probability < metadata["free_thresh"]] = 0
        return np.flipud(grid)

    def _occupancy_to_pixels(
        self,
        occupancy: np.ndarray,
        metadata: Dict[str, Any],
    ) -> np.ndarray:
        grid = np.asarray(occupancy)
        if grid.ndim != 2 or not np.isin(grid, (-1, 0, 100)).all():
            raise SavedMapFormatError("occupancy data may contain only -1, 0 or 100")
        values = self._occupancy_pixel_values(metadata)
        image_grid = np.flipud(grid)
        pixels = np.empty(image_grid.shape, dtype=np.uint8)
        for value, pixel in values.items():
            pixels[image_grid == value] = pixel
        return pixels

    def _require_manageable(self, record: SavedMapRecord) -> None:
        if not record.manageable or record.root not in self.managed_roots:
            raise SavedMapReadOnly("saved map is read-only")
        try:
            self._validate_record(record)
            self._regular_identity(record.path)
            if record.auxiliary_path is not None:
                self._regular_identity(record.auxiliary_path)
                metadata = self._read_map_yaml(record.path)
                image = metadata["image"]
                if (
                    Path(image).name != image
                    or record.auxiliary_path.parent != record.path.parent
                    or (record.path.parent / image).resolve(strict=True)
                    != record.auxiliary_path
                ):
                    raise SavedMapReadOnly("saved map pair is read-only")
        except SavedMapError:
            raise
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            raise SavedMapReadOnly("saved map is no longer safely manageable") from exc

    @staticmethod
    def _require_editable_record(record: SavedMapRecord) -> None:
        if not bool(record.details.get("editable", False)):
            reason = str(
                record.details.get(
                    "edit_reason",
                    "saved occupancy map is not editable",
                )
            )
            raise SavedMapFormatError(reason)

    def _auxiliary_has_other_reference(self, record: SavedMapRecord) -> bool:
        if record.auxiliary_path is None:
            return False
        return any(
            candidate.path != record.path
            and candidate.auxiliary_path == record.auxiliary_path
            for candidate in self._scan(apply_limit=False)
        )

    @staticmethod
    def _ensure_targets_absent(targets: Iterable[Path]) -> None:
        for target in targets:
            if os.path.lexists(target):
                raise SavedMapConflict("a map with the requested name already exists")

    @staticmethod
    def _regular_identity(path: Path) -> tuple[int, int]:
        current = path.lstat()
        if not stat.S_ISREG(current.st_mode):
            raise SavedMapReadOnly("saved map artifact is not a regular file")
        return current.st_dev, current.st_ino

    def _create_transaction(self, root: Path) -> tuple[Path, Path]:
        transaction_root = root / ".robot_scope_transactions"
        try:
            transaction_root.mkdir(mode=0o700, exist_ok=True)
            if (
                transaction_root.is_symlink()
                or not transaction_root.is_dir()
                or transaction_root.resolve(strict=True).parent != root
            ):
                raise SavedMapMutationError("saved map transaction directory is unsafe")
            transaction = transaction_root / uuid.uuid4().hex
            transaction.mkdir(mode=0o700, exist_ok=False)
        except SavedMapError:
            raise
        except OSError as exc:
            raise SavedMapMutationError("saved map transaction could not be created") from exc
        return transaction_root, transaction

    def _backup_sources(
        self,
        transaction: Path,
        sources: Iterable[Path],
    ) -> tuple[Dict[Path, Path], Dict[Path, tuple[int, int]]]:
        backups: Dict[Path, Path] = {}
        identities: Dict[Path, tuple[int, int]] = {}
        for index, source in enumerate(sources):
            identity = self._regular_identity(source)
            backup = transaction / f"source-{index}{source.suffix}"
            try:
                os.link(source, backup, follow_symlinks=False)
            except OSError as exc:
                raise SavedMapMutationError("saved map backup could not be created") from exc
            if self._regular_identity(backup) != identity:
                raise SavedMapMutationError("saved map changed while creating its backup")
            backups[source] = backup
            identities[source] = identity
        return backups, identities

    @staticmethod
    def _publish_link(source: Path, target: Path) -> tuple[int, int]:
        source_stat = source.lstat()
        if not stat.S_ISREG(source_stat.st_mode):
            raise SavedMapReadOnly("saved map artifact is not a regular file")
        source_identity = source_stat.st_dev, source_stat.st_ino
        try:
            os.link(source, target, follow_symlinks=False)
        except FileExistsError as exc:
            raise SavedMapConflict("a map with the requested name already exists") from exc
        except OSError as exc:
            raise SavedMapMutationError("renamed map could not be published") from exc
        try:
            current = target.lstat()
            target_identity = current.st_dev, current.st_ino
            if not stat.S_ISREG(current.st_mode) or target_identity != source_identity:
                raise SavedMapMutationError("renamed map target changed during publication")
            return target_identity
        except OSError as exc:
            # A concurrent actor may have removed the new name.  Never remove a
            # replacement whose inode is not the hard link created above.
            try:
                current = target.lstat()
                if (current.st_dev, current.st_ino) == source_identity:
                    target.unlink()
            except OSError:
                pass
            raise SavedMapMutationError("renamed map target could not be verified") from exc

    def _stage_renamed_yaml(
        self,
        record: SavedMapRecord,
        transaction: Path,
        image_name: str,
    ) -> Path:
        try:
            rewritten = self._rewrite_yaml_image(
                record.path.read_text(encoding="utf-8"),
                image_name,
            )
            staged = transaction / f"renamed{record.path.suffix}"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(
                staged,
                flags,
                stat.S_IMODE(record.path.stat().st_mode),
            )
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(rewritten)
                stream.flush()
                os.fsync(stream.fileno())
            if self._read_map_yaml(staged)["image"] != image_name:
                raise SavedMapMutationError("renamed map YAML image reference is invalid")
            return staged
        except SavedMapError:
            raise
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            raise SavedMapMutationError("renamed map YAML could not be prepared") from exc

    @staticmethod
    def _rewrite_yaml_image(content: str, image_name: str) -> str:
        lines = content.splitlines(keepends=True)
        rewritten: list[str] = []
        replacements = 0
        image_line = re.compile(
            r"^(?P<prefix>\s*image\s*:\s*)(?P<value>[^#\r\n]*?)"
            r"(?P<suffix>\s*(?:#.*)?)(?P<ending>\r?\n)?$"
        )
        for line in lines:
            match = image_line.match(line)
            if match is None:
                rewritten.append(line)
                continue
            replacements += 1
            rewritten.append(
                f"{match.group('prefix')}{image_name}"
                f"{match.group('suffix')}{match.group('ending') or ''}"
            )
        if replacements != 1:
            raise SavedMapMutationError("map YAML must contain exactly one image field")
        return "".join(rewritten)

    def _unlink_verified(self, path: Path, identity: tuple[int, int]) -> None:
        if self._regular_identity(path) != identity:
            raise SavedMapMutationError("saved map changed during the operation")
        os.unlink(path)

    def _rollback_mutation(
        self,
        backups: Dict[Path, Path],
        published: Dict[Path, tuple[int, int]],
    ) -> bool:
        complete = True
        for source, backup in backups.items():
            try:
                backup_identity = self._regular_identity(backup)
                if os.path.lexists(source):
                    if self._regular_identity(source) != backup_identity:
                        complete = False
                else:
                    os.link(backup, source, follow_symlinks=False)
                    if self._regular_identity(source) != backup_identity:
                        complete = False
            except (OSError, SavedMapError):
                complete = False
        for target, identity in reversed(tuple(published.items())):
            try:
                if not os.path.lexists(target):
                    continue
                if self._regular_identity(target) != identity:
                    complete = False
                    continue
                os.unlink(target)
            except (OSError, SavedMapError):
                complete = False
        return complete

    @staticmethod
    def _cleanup_transaction(transaction_root: Path, transaction: Path) -> None:
        shutil.rmtree(transaction, ignore_errors=True)
        try:
            transaction_root.rmdir()
        except OSError:
            pass

    def _find(self, map_id: str) -> SavedMapRecord:
        if not isinstance(map_id, str) or len(map_id) != 24:
            raise SavedMapNotFound("saved map not found")
        record = next((item for item in self._scan() if item.map_id == map_id), None)
        if record is None:
            raise SavedMapNotFound("saved map not found")
        return record

    def _scan(self, *, apply_limit: bool = True) -> list[SavedMapRecord]:
        records: list[SavedMapRecord] = []
        for root in self.roots:
            for path in self._iter_candidates(root):
                try:
                    record = self._record_for(root, path)
                except (
                    OSError,
                    ValueError,
                    RuntimeError,
                    UnicodeError,
                    SavedMapFormatError,
                    json.JSONDecodeError,
                ):
                    continue
                if record is not None:
                    records.append(record)
        records.sort(key=lambda record: (-record.modified_ns, record.name.lower(), record.map_id))
        return records[: self.max_files] if apply_limit else records

    def _iter_candidates(self, root: Path) -> Iterable[Path]:
        for current, directories, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            depth = len(current_path.relative_to(root).parts)
            directories[:] = [
                name
                for name in directories
                if not name.startswith(".") and depth < self.max_depth
            ]
            if depth > self.max_depth:
                continue
            for name in files:
                path = current_path / name
                if (
                    name.startswith(".")
                    or name.endswith(".annotations.json")
                    or name.endswith(".map-family.json")
                    or path.is_symlink()
                ):
                    continue
                if path.suffix.lower() in {".pcd", ".json", ".yaml", ".yml"}:
                    yield path

    def _record_for(self, root: Path, path: Path) -> Optional[SavedMapRecord]:
        resolved = self._contained_file(root, path)
        stat = resolved.stat()
        if stat.st_size <= 0 or stat.st_size > self.max_file_bytes:
            return None
        suffix = resolved.suffix.lower()
        details: Dict[str, Any]
        auxiliary: Optional[Path] = None
        manageable = root in self.managed_roots
        if suffix == ".pcd":
            header = self._read_pcd_header(resolved)
            if header["data"] != "binary":
                return None
            kind, fmt = "pointcloud3d", "pcd-binary"
            details = {
                "point_count": header["points"],
                "fields": header["fields"],
                "frame_id": "camera_init",
            }
        elif suffix == ".json":
            payload = self._read_json(resolved)
            points = payload.get("points")
            if not isinstance(points, list) or len(points) < 3 or len(points) % 3:
                return None
            kind, fmt = "pointcloud3d", "robot-scope-json"
            details = {
                "point_count": len(points) // 3,
                "frame_id": str(payload.get("frame_id", "")),
            }
            if isinstance(payload.get("bounds"), dict):
                details["bounds"] = payload["bounds"]
        else:
            metadata = self._read_map_yaml(resolved)
            image_reference = metadata["image"]
            auxiliary_candidate = resolved.parent / image_reference
            auxiliary = self._contained_file(root, auxiliary_candidate)
            if auxiliary.suffix.lower() != ".pgm":
                return None
            image_stat = auxiliary.stat()
            if image_stat.st_size <= 0 or image_stat.st_size > self.max_file_bytes:
                return None
            pgm_magic, width, height, pgm_maximum = self._read_pgm_header(auxiliary)
            kind, fmt = "occupancy2d", "map-server-pgm"
            manageable = bool(
                manageable
                and Path(image_reference).name == image_reference
                and auxiliary.parent == resolved.parent
                and not auxiliary_candidate.is_symlink()
            )
            editable = bool(
                manageable
                and metadata["mode"] == "trinary"
                and pgm_magic == "P5"
                and pgm_maximum == 255
            )
            if not manageable:
                edit_reason = "saved map is read-only"
            elif metadata["mode"] != "trinary":
                edit_reason = "only absent/trinary map mode is editable"
            elif pgm_magic != "P5":
                edit_reason = "only binary P5 occupancy images are editable"
            elif pgm_maximum != 255:
                edit_reason = "only 8-bit maxval=255 occupancy images are editable"
            else:
                edit_reason = None
            details = {
                "width": width,
                "height": height,
                "resolution": metadata["resolution"],
                "origin": metadata["origin"],
                "mode": metadata["mode"],
                "frame_id": "map",
                "image_file_name": auxiliary.name,
                "editable": editable,
            }
            if edit_reason:
                details["edit_reason"] = edit_reason
            stat_size = stat.st_size + image_stat.st_size
            stat_mtime = max(stat.st_mtime_ns, image_stat.st_mtime_ns)
            return SavedMapRecord(
                map_id=self._opaque_id(kind, resolved),
                name=resolved.stem,
                kind=kind,
                format=fmt,
                path=resolved,
                root=root,
                modified_ns=stat_mtime,
                revision=self._signature_revision((resolved, auxiliary)),
                size_bytes=stat_size,
                details=details,
                manageable=manageable,
                auxiliary_path=auxiliary,
            )
        return SavedMapRecord(
            map_id=self._opaque_id(kind, resolved),
            name=resolved.stem,
            kind=kind,
            format=fmt,
            path=resolved,
            root=root,
            modified_ns=stat.st_mtime_ns,
            revision=self._signature_revision((resolved,)),
            size_bytes=stat.st_size,
            details=details,
            manageable=manageable,
            auxiliary_path=auxiliary,
        )

    @staticmethod
    def _opaque_id(kind: str, path: Path) -> str:
        digest = hashlib.sha256(f"{kind}\0{path}".encode("utf-8")).hexdigest()
        return digest[:24]

    @staticmethod
    def _contained_file(root: Path, path: Path) -> Path:
        try:
            candidate_stat = path.lstat()
        except OSError as exc:
            raise SavedMapFormatError("map path is not a regular file") from exc
        if not stat.S_ISREG(candidate_stat.st_mode):
            raise SavedMapFormatError("map path is not a regular file")
        resolved = path.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise SavedMapFormatError("map file escapes its configured root") from exc
        if not resolved.is_file():
            raise SavedMapFormatError("map path is not a regular file")
        return resolved

    def _validate_record(self, record: SavedMapRecord) -> None:
        current = self._contained_file(record.root, record.path).stat()
        if current.st_size <= 0 or current.st_size > self.max_file_bytes:
            raise SavedMapFormatError("saved map is empty or exceeds the configured limit")
        if record.auxiliary_path is not None:
            auxiliary = self._contained_file(record.root, record.auxiliary_path).stat()
            if auxiliary.st_size <= 0 or auxiliary.st_size > self.max_file_bytes:
                raise SavedMapFormatError("saved map image exceeds the configured limit")

    def _read_json(self, path: Path) -> Dict[str, Any]:
        if path.stat().st_size > self.max_file_bytes:
            raise SavedMapFormatError("saved map exceeds the configured limit")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SavedMapFormatError("saved map JSON must be an object")
        return payload

    @staticmethod
    def _read_pcd_header(path: Path) -> Dict[str, Any]:
        metadata: Dict[str, list[str]] = {}
        consumed = 0
        with path.open("rb") as stream:
            while consumed < 64 * 1024:
                line = stream.readline()
                consumed += len(line)
                if not line:
                    break
                decoded = line.decode("ascii", errors="strict").strip()
                if not decoded or decoded.startswith("#"):
                    continue
                key, *values = decoded.split()
                metadata[key.upper()] = values
                if key.upper() == "DATA":
                    break
        if "DATA" not in metadata:
            raise SavedMapFormatError("PCD header ended before DATA")
        fields = metadata.get("FIELDS", [])
        sizes = [int(value) for value in metadata.get("SIZE", [])]
        kinds = metadata.get("TYPE", [])
        counts = [int(value) for value in metadata.get("COUNT", ["1"] * len(fields))]
        if not fields or not (len(fields) == len(sizes) == len(kinds) == len(counts)):
            raise SavedMapFormatError("invalid PCD field metadata")
        if any(name not in fields for name in ("x", "y", "z")):
            raise SavedMapFormatError("PCD requires x, y and z fields")
        points = int(metadata.get("POINTS", metadata.get("WIDTH", ["0"]))[0])
        if points <= 0:
            raise SavedMapFormatError("PCD has no points")
        return {
            "fields": fields,
            "sizes": sizes,
            "types": kinds,
            "counts": counts,
            "points": points,
            "data": metadata["DATA"][0].lower(),
            "data_offset": consumed,
        }

    def _pcd_snapshot(
        self,
        record: SavedMapRecord,
        max_points: Optional[int],
    ) -> Dict[str, Any]:
        header = self._read_pcd_header(record.path)
        if max_points is None and header["points"] > self.max_full_view_points:
            raise SavedMapPointLimitError(
                "saved point cloud exceeds the configured full-view limit of "
                f"{self.max_full_view_points} points"
            )
        scalar_types = {
            ("F", 4): "<f4", ("F", 8): "<f8",
            ("I", 1): "i1", ("I", 2): "<i2", ("I", 4): "<i4",
            ("U", 1): "u1", ("U", 2): "<u2", ("U", 4): "<u4",
        }
        names, formats, offsets = [], [], []
        offset = 0
        for name, size, kind, count in zip(
            header["fields"], header["sizes"], header["types"], header["counts"]
        ):
            scalar = scalar_types.get((kind, size))
            if scalar is None or count != 1:
                raise SavedMapFormatError(f"unsupported PCD field: {name} {kind}{size}x{count}")
            names.append(name)
            formats.append(scalar)
            offsets.append(offset)
            offset += size
        expected = header["data_offset"] + header["points"] * offset
        if expected > record.path.stat().st_size:
            raise SavedMapFormatError("PCD payload is truncated")
        dtype = np.dtype({"names": names, "formats": formats, "offsets": offsets, "itemsize": offset})
        records = np.memmap(
            record.path,
            mode="r",
            dtype=dtype,
            offset=header["data_offset"],
            shape=(header["points"],),
        )
        if max_points is None:
            points = np.column_stack((records["x"], records["y"], records["z"]))
        else:
            sample_count = min(header["points"], max_points * 4)
            indexes = np.linspace(
                0,
                header["points"] - 1,
                sample_count,
                dtype=np.int64,
            )
            points = np.column_stack(
                (records["x"][indexes], records["y"][indexes], records["z"][indexes])
            )
        return self._cloud_payload(
            record,
            points,
            header["points"],
            "camera_init",
            max_points,
        )

    def _json_snapshot(
        self,
        record: SavedMapRecord,
        max_points: Optional[int],
    ) -> Dict[str, Any]:
        source = self._read_json(record.path)
        raw = np.asarray(source["points"], dtype=np.float64).reshape((-1, 3))
        if max_points is None and len(raw) > self.max_full_view_points:
            raise SavedMapPointLimitError(
                "saved point cloud exceeds the configured full-view limit of "
                f"{self.max_full_view_points} points"
            )
        frame_id = str(source.get("frame_id", ""))
        source_count = int(source.get("source_points", len(raw)))
        payload = self._cloud_payload(
            record,
            raw,
            source_count,
            frame_id,
            max_points,
        )
        payload["topic"] = str(source.get("topic", "/saved/map"))
        return payload

    def _cloud_payload(
        self,
        record: SavedMapRecord,
        points: np.ndarray,
        source_count: int,
        frame_id: str,
        max_points: Optional[int],
    ) -> Dict[str, Any]:
        finite = points[np.isfinite(points).all(axis=1)]
        if not len(finite):
            raise SavedMapFormatError("saved point cloud has no finite points")
        center = np.median(finite, axis=0)
        distances = np.linalg.norm(finite - center, axis=1)
        finite = finite[distances <= self.cloud_radius_limit_m]
        if not len(finite):
            raise SavedMapFormatError("saved point cloud is outside the configured radius")
        if max_points is not None and len(finite) > max_points:
            indexes = np.linspace(0, len(finite) - 1, max_points, dtype=np.int64)
            finite = finite[indexes]
        finite = np.round(finite.astype(np.float64, copy=False), 4)
        return {
            "seq": max(1, record.modified_ns),
            "map_id": record.map_id,
            "name": record.name,
            "kind": "pointcloud3d",
            "topic": "/saved/map",
            "frame_id": frame_id,
            "source_points": int(source_count),
            "sent_points": int(len(finite)),
            "units": "m",
            "bounds": {
                "min": [float(value) for value in np.min(finite, axis=0)],
                "max": [float(value) for value in np.max(finite, axis=0)],
            },
            "offline_snapshot": True,
            "points": [round(float(value), 4) for value in finite.reshape(-1)],
        }

    @staticmethod
    def _read_map_yaml(path: Path) -> Dict[str, Any]:
        values: Dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
        if not values.get("image"):
            raise SavedMapFormatError("map YAML has no image")
        try:
            origin = ast.literal_eval(values.get("origin", "[0, 0, 0]"))
            origin = [float(value) for value in origin]
            resolution = float(values["resolution"])
            occupied = float(values.get("occupied_thresh", "0.65"))
            free = float(values.get("free_thresh", "0.196"))
            negate = int(values.get("negate", "0"))
            mode = values.get("mode", "trinary").strip().strip("'\"").lower()
        except (KeyError, ValueError, SyntaxError, TypeError) as exc:
            raise SavedMapFormatError("invalid map YAML metadata") from exc
        if (
            len(origin) != 3
            or not all(np.isfinite(value) for value in origin)
            or not np.isfinite(resolution)
            or resolution <= 0
            or not np.isfinite(free)
            or not np.isfinite(occupied)
            or not (0 <= free < occupied <= 1)
            or negate not in {0, 1}
            or mode not in {"trinary", "scale", "raw"}
        ):
            raise SavedMapFormatError("invalid map YAML ranges")
        image = values["image"].strip().strip("'\"")
        if not image or "\x00" in image:
            raise SavedMapFormatError("invalid map YAML image")
        return {
            "image": image,
            "resolution": resolution,
            "origin": origin,
            "occupied_thresh": occupied,
            "free_thresh": free,
            "negate": negate,
            "mode": mode,
        }

    def _read_pgm_header(self, path: Path) -> tuple[str, int, int, int]:
        size = path.stat().st_size
        if size <= 0 or size > self.max_file_bytes:
            raise SavedMapFormatError("PGM exceeds the configured limit")
        with path.open("rb") as stream:
            content = stream.read(min(size, 64 * 1024))
        position = 0

        def token() -> bytes:
            nonlocal position
            while position < len(content):
                if content[position] == 35:
                    end = content.find(b"\n", position)
                    position = len(content) if end < 0 else end + 1
                elif chr(content[position]).isspace():
                    position += 1
                else:
                    break
            start = position
            while position < len(content) and not chr(content[position]).isspace():
                position += 1
            if start == position:
                raise SavedMapFormatError("truncated PGM header")
            return content[start:position]

        magic = token()
        try:
            width, height, maximum = int(token()), int(token()), int(token())
        except ValueError as exc:
            raise SavedMapFormatError("invalid PGM header") from exc
        if magic not in {b"P2", b"P5"}:
            raise SavedMapFormatError("only P2 and P5 PGM maps are supported")
        if (
            width <= 0
            or height <= 0
            or width * height > self.max_grid_cells
            or maximum <= 0
            or maximum > 65_535
        ):
            raise SavedMapFormatError("invalid PGM dimensions")
        return magic.decode("ascii"), width, height, maximum

    def _read_pgm(self, path: Path, *, pixels: bool) -> tuple[int, int, Optional[np.ndarray]]:
        content = path.read_bytes()
        if len(content) > self.max_file_bytes:
            raise SavedMapFormatError("PGM exceeds the configured limit")
        position = 0

        def token() -> bytes:
            nonlocal position
            while position < len(content):
                if content[position] == 35:
                    end = content.find(b"\n", position)
                    position = len(content) if end < 0 else end + 1
                elif chr(content[position]).isspace():
                    position += 1
                else:
                    break
            start = position
            while position < len(content) and not chr(content[position]).isspace():
                position += 1
            if start == position:
                raise SavedMapFormatError("truncated PGM header")
            return content[start:position]

        magic = token()
        try:
            width, height, maximum = int(token()), int(token()), int(token())
        except ValueError as exc:
            raise SavedMapFormatError("invalid PGM header") from exc
        cells = width * height
        if (
            width <= 0
            or height <= 0
            or cells > self.max_grid_cells
            or maximum <= 0
            or maximum > 65_535
        ):
            raise SavedMapFormatError("invalid PGM dimensions")
        if not pixels:
            return width, height, None
        if magic == b"P5":
            if position >= len(content) or not chr(content[position]).isspace():
                raise SavedMapFormatError("invalid binary PGM separator")
            position += 2 if content[position:position + 2] == b"\r\n" else 1
            item_size = 1 if maximum < 256 else 2
            expected = cells * item_size
            if len(content) - position < expected:
                raise SavedMapFormatError("truncated PGM pixels")
            dtype = np.dtype("u1" if item_size == 1 else ">u2")
            values = np.frombuffer(content, dtype=dtype, count=cells, offset=position)
        elif magic == b"P2":
            values = np.asarray([int(token()) for _ in range(cells)], dtype=np.uint32)
        else:
            raise SavedMapFormatError("only P2 and P5 PGM maps are supported")
        normalized = np.clip(values.astype(np.float64) / maximum, 0.0, 1.0)
        return width, height, normalized.reshape((height, width))

    def _occupancy_snapshot(self, record: SavedMapRecord) -> Dict[str, Any]:
        if record.auxiliary_path is None:
            raise SavedMapFormatError("2D map has no image")
        metadata = self._read_map_yaml(record.path)
        width, height, pixels = self._read_pgm(record.auxiliary_path, pixels=True)
        assert pixels is not None
        occupancy_probability = pixels if metadata["negate"] else 1.0 - pixels
        grid = np.full((height, width), -1, dtype=np.int16)
        grid[occupancy_probability > metadata["occupied_thresh"]] = 100
        grid[occupancy_probability < metadata["free_thresh"]] = 0
        # map_server converts top-left image rows into bottom-left ROS map rows.
        grid = np.flipud(grid)
        encoded = bytes((int(value) & 0xFF for value in grid.reshape(-1)))
        return {
            "seq": max(1, record.modified_ns),
            "map_id": record.map_id,
            "name": record.name,
            "kind": "occupancy2d",
            "width": width,
            "height": height,
            "resolution": metadata["resolution"],
            "origin": metadata["origin"],
            "frame_id": "map",
            "topic": "/saved/map",
            "data_b64": base64.b64encode(encoded).decode("ascii"),
            "data_encoding": "int8-base64",
            "cell_order": "row-major; cell(0,0) at origin",
            "offline_snapshot": True,
        }
