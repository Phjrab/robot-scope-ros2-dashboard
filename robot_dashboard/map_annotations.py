"""Pure schema and geometry validation for map annotation documents.

Filesystem discovery and publication stay in :mod:`robot_dashboard.saved_maps`.
This module deliberately has no ROS, FastAPI, subprocess, or path access.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Protocol


ANNOTATION_SCHEMA_VERSION = 1
ANNOTATION_ID_RE = re.compile(r"^[0-9a-f]{24}$")
REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
POINT_TYPES = frozenset({"POI", "HOME", "DOCK", "INSPECTION_POINT"})
POLYGON_TYPES = frozenset({"KEEP_OUT", "SLOW_ZONE", "WAIT_ZONE"})
GOAL_POINT_TYPES = POINT_TYPES
MAX_POINTS = 64
MAX_POLYGONS = 32
MAX_ANNOTATIONS = 96
MAX_POLYGON_VERTICES = 64
MAX_TOTAL_VERTICES = 2_048
MAX_NAME_CHARS = 64
MAX_DOCUMENT_BYTES = 128 * 1024


class MapAnnotationError(ValueError):
    """Base class for bounded annotation contract failures."""


class MapAnnotationConflict(MapAnnotationError):
    """Raised when a map or annotation revision changed."""


class MapAnnotationFormatError(MapAnnotationError):
    """Raised when a document or geometry violates the fixed schema."""


class MapGeometry(Protocol):
    map_id: str
    revision: str

    def contains(self, x: float, y: float) -> bool: ...

    def known_free(self, x: float, y: float, *, clearance_radius: float) -> bool: ...


def _canonical_payload(
    *,
    map_id: str,
    map_revision: str,
    points: Iterable[Mapping[str, Any]],
    polygons: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": ANNOTATION_SCHEMA_VERSION,
        "map_id": map_id,
        "map_revision": map_revision,
        "points": list(points),
        "polygons": list(polygons),
    }


def annotation_revision(
    *,
    map_id: str,
    map_revision: str,
    points: Iterable[Mapping[str, Any]],
    polygons: Iterable[Mapping[str, Any]],
) -> str:
    payload = _canonical_payload(
        map_id=map_id,
        map_revision=map_revision,
        points=points,
        polygons=polygons,
    )
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _document(
    *,
    map_id: str,
    map_revision: str,
    points: list[dict[str, Any]],
    polygons: list[dict[str, Any]],
    exists: bool,
) -> dict[str, Any]:
    revision = annotation_revision(
        map_id=map_id,
        map_revision=map_revision,
        points=points,
        polygons=polygons,
    )
    return {
        "schema_version": ANNOTATION_SCHEMA_VERSION,
        "map_id": map_id,
        "map_revision": map_revision,
        "annotation_revision": revision,
        "revision": revision,
        "points": points,
        "polygons": polygons,
        "exists": exists,
        "limits": {
            "max_points": MAX_POINTS,
            "max_polygons": MAX_POLYGONS,
            "max_annotations": MAX_ANNOTATIONS,
            "max_polygon_vertices": MAX_POLYGON_VERTICES,
            "max_total_vertices": MAX_TOTAL_VERTICES,
            "max_name_chars": MAX_NAME_CHARS,
        },
        "semantics": {
            "HOME": "single safe default return pose",
            "DOCK": "named docking approach pose; docking actuation is not implied",
            "KEEP_OUT": "display-only safety zone; no costmap filter is generated",
            "SLOW_ZONE": "display-only advisory zone; no speed command is generated",
            "WAIT_ZONE": "display-only mission wait area",
        },
    }


def empty_annotation_document(map_id: str, map_revision: str) -> dict[str, Any]:
    _validate_pins(map_id, map_revision)
    return _document(
        map_id=map_id,
        map_revision=map_revision,
        points=[],
        polygons=[],
        exists=False,
    )


def _validate_pins(map_id: Any, map_revision: Any) -> None:
    if not isinstance(map_id, str) or not ANNOTATION_ID_RE.fullmatch(map_id):
        raise MapAnnotationFormatError("annotation map_id is invalid")
    if not isinstance(map_revision, str) or not REVISION_RE.fullmatch(map_revision):
        raise MapAnnotationFormatError("annotation map_revision is invalid")


def _name(value: Any) -> str:
    if not isinstance(value, str):
        raise MapAnnotationFormatError("annotation name must be text")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized or len(normalized) > MAX_NAME_CHARS:
        raise MapAnnotationFormatError(
            f"annotation name must contain 1 to {MAX_NAME_CHARS} characters"
        )
    allowed_punctuation = " _-.()"
    if any(
        unicodedata.category(character).startswith("C")
        or not (character.isalnum() or character in allowed_punctuation)
        for character in normalized
    ):
        raise MapAnnotationFormatError(
            "annotation name contains unsupported characters"
        )
    return normalized


def _number(value: Any, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MapAnnotationFormatError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise MapAnnotationFormatError(f"{label} is outside the supported range")
    return round(number, 6)


def _identifier(value: Any, identifier_factory: Callable[[], str]) -> str:
    if value is None:
        value = identifier_factory()
    if not isinstance(value, str) or not ANNOTATION_ID_RE.fullmatch(value):
        raise MapAnnotationFormatError("annotation id is invalid")
    return value


def _point(
    value: Any,
    geometry: MapGeometry,
    identifier_factory: Callable[[], str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise MapAnnotationFormatError("point annotation must be an object")
    if set(value) - {"id", "type", "name", "pose"}:
        raise MapAnnotationFormatError("point annotation contains unknown fields")
    kind = value.get("type")
    if kind not in POINT_TYPES:
        raise MapAnnotationFormatError("point annotation type is unsupported")
    pose = value.get("pose")
    if not isinstance(pose, Mapping) or set(pose) != {"x", "y", "yaw"}:
        raise MapAnnotationFormatError("point annotation pose is invalid")
    x = _number(pose.get("x"), "point x", -1_000_000.0, 1_000_000.0)
    y = _number(pose.get("y"), "point y", -1_000_000.0, 1_000_000.0)
    yaw = _number(pose.get("yaw"), "point yaw", -math.pi, math.pi)
    if not geometry.contains(x, y):
        raise MapAnnotationFormatError("point annotation is outside the map bounds")
    if not geometry.known_free(x, y, clearance_radius=0.0):
        raise MapAnnotationFormatError("point annotation must be on a known-free cell")
    return {
        "id": _identifier(value.get("id"), identifier_factory),
        "type": kind,
        "name": _name(value.get("name")),
        "pose": {"x": x, "y": y, "yaw": yaw},
    }


def _polygon(
    value: Any,
    geometry: MapGeometry,
    identifier_factory: Callable[[], str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise MapAnnotationFormatError("polygon annotation must be an object")
    if set(value) - {"id", "type", "name", "vertices"}:
        raise MapAnnotationFormatError("polygon annotation contains unknown fields")
    kind = value.get("type")
    if kind not in POLYGON_TYPES:
        raise MapAnnotationFormatError("polygon annotation type is unsupported")
    vertices = value.get("vertices")
    if not isinstance(vertices, list) or not 3 <= len(vertices) <= MAX_POLYGON_VERTICES:
        raise MapAnnotationFormatError(
            f"polygon must contain 3 to {MAX_POLYGON_VERTICES} vertices"
        )
    normalized: list[dict[str, float]] = []
    for vertex in vertices:
        if not isinstance(vertex, Mapping) or set(vertex) != {"x", "y"}:
            raise MapAnnotationFormatError("polygon vertex is invalid")
        x = _number(vertex.get("x"), "polygon x", -1_000_000.0, 1_000_000.0)
        y = _number(vertex.get("y"), "polygon y", -1_000_000.0, 1_000_000.0)
        if not geometry.contains(x, y):
            raise MapAnnotationFormatError("polygon vertex is outside the map bounds")
        normalized.append({"x": x, "y": y})
    twice_area = abs(
        sum(
            normalized[index]["x"] * normalized[(index + 1) % len(normalized)]["y"]
            - normalized[(index + 1) % len(normalized)]["x"] * normalized[index]["y"]
            for index in range(len(normalized))
        )
    )
    if twice_area <= 1e-9:
        raise MapAnnotationFormatError("polygon area must be non-zero")
    return {
        "id": _identifier(value.get("id"), identifier_factory),
        "type": kind,
        "name": _name(value.get("name")),
        "vertices": normalized,
    }


def normalize_annotation_document(
    *,
    map_id: str,
    map_revision: str,
    points: Any,
    polygons: Any,
    geometry: MapGeometry,
    identifier_factory: Callable[[], str] | None = None,
    exists: bool = True,
) -> dict[str, Any]:
    _validate_pins(map_id, map_revision)
    if geometry.map_id != map_id or geometry.revision != map_revision:
        raise MapAnnotationConflict("annotation map revision changed")
    if not isinstance(points, list) or len(points) > MAX_POINTS:
        raise MapAnnotationFormatError(f"points must contain at most {MAX_POINTS} entries")
    if not isinstance(polygons, list) or len(polygons) > MAX_POLYGONS:
        raise MapAnnotationFormatError(
            f"polygons must contain at most {MAX_POLYGONS} entries"
        )
    if len(points) + len(polygons) > MAX_ANNOTATIONS:
        raise MapAnnotationFormatError(
            f"annotations must contain at most {MAX_ANNOTATIONS} entries"
        )
    if sum(
        len(item.get("vertices", [])) if isinstance(item, Mapping) else 0
        for item in polygons
    ) > MAX_TOTAL_VERTICES:
        raise MapAnnotationFormatError(
            f"polygon vertices must total at most {MAX_TOTAL_VERTICES}"
        )
    factory = identifier_factory or (lambda: secrets.token_hex(12))
    normalized_points = [_point(item, geometry, factory) for item in points]
    normalized_polygons = [_polygon(item, geometry, factory) for item in polygons]
    identifiers = [item["id"] for item in normalized_points + normalized_polygons]
    if len(set(identifiers)) != len(identifiers):
        raise MapAnnotationFormatError("annotation ids must be unique")
    if sum(item["type"] == "HOME" for item in normalized_points) > 1:
        raise MapAnnotationFormatError("a map may contain only one HOME annotation")
    return _document(
        map_id=map_id,
        map_revision=map_revision,
        points=normalized_points,
        polygons=normalized_polygons,
        exists=exists,
    )


def parse_annotation_document(
    payload: Any,
    *,
    geometry: MapGeometry,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema_version",
        "map_id",
        "map_revision",
        "annotation_revision",
        "revision",
        "points",
        "polygons",
    }:
        raise MapAnnotationFormatError("annotation document schema is invalid")
    if payload.get("schema_version") != ANNOTATION_SCHEMA_VERSION:
        raise MapAnnotationFormatError("annotation schema version is unsupported")
    normalized = normalize_annotation_document(
        map_id=payload.get("map_id"),
        map_revision=payload.get("map_revision"),
        points=payload.get("points"),
        polygons=payload.get("polygons"),
        geometry=geometry,
        identifier_factory=lambda: "",
        exists=True,
    )
    expected = normalized["annotation_revision"]
    if payload.get("annotation_revision") != expected or payload.get("revision") != expected:
        raise MapAnnotationFormatError("annotation revision does not match its content")
    return normalized


def serialized_annotation_document(document: Mapping[str, Any]) -> bytes:
    stored = {
        key: document[key]
        for key in (
            "schema_version",
            "map_id",
            "map_revision",
            "annotation_revision",
            "revision",
            "points",
            "polygons",
        )
    }
    encoded = (
        json.dumps(stored, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(encoded) > MAX_DOCUMENT_BYTES:
        raise MapAnnotationFormatError("annotation document exceeds the size limit")
    return encoded


@dataclass(frozen=True)
class AnnotationGoal:
    annotation_id: str
    annotation_type: str
    name: str
    x: float
    y: float
    yaw: float


def resolve_annotation_goal(
    document: Mapping[str, Any], annotation_id: str
) -> AnnotationGoal:
    if not isinstance(annotation_id, str) or not ANNOTATION_ID_RE.fullmatch(annotation_id):
        raise MapAnnotationFormatError("annotation id is invalid")
    points = document.get("points")
    if not isinstance(points, list):
        raise MapAnnotationFormatError("annotation points are unavailable")
    entry = next(
        (
            item
            for item in points
            if isinstance(item, Mapping) and item.get("id") == annotation_id
        ),
        None,
    )
    if entry is None or entry.get("type") not in GOAL_POINT_TYPES:
        raise MapAnnotationFormatError("goal annotation was not found")
    pose = entry.get("pose")
    if not isinstance(pose, Mapping):
        raise MapAnnotationFormatError("goal annotation pose is unavailable")
    return AnnotationGoal(
        annotation_id=annotation_id,
        annotation_type=str(entry["type"]),
        name=str(entry["name"]),
        x=float(pose["x"]),
        y=float(pose["y"]),
        yaw=float(pose["yaw"]),
    )


__all__ = [
    "ANNOTATION_SCHEMA_VERSION",
    "GOAL_POINT_TYPES",
    "MAX_ANNOTATIONS",
    "MAX_DOCUMENT_BYTES",
    "MAX_POINTS",
    "MAX_POLYGONS",
    "MAX_POLYGON_VERTICES",
    "MAX_TOTAL_VERTICES",
    "POINT_TYPES",
    "POLYGON_TYPES",
    "AnnotationGoal",
    "MapAnnotationConflict",
    "MapAnnotationError",
    "MapAnnotationFormatError",
    "annotation_revision",
    "empty_annotation_document",
    "normalize_annotation_document",
    "parse_annotation_document",
    "resolve_annotation_goal",
    "serialized_annotation_document",
]
