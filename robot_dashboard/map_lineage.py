"""Bounded, path-free lineage contract for 3D and derived 2D maps."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Mapping


SCHEMA = "robot-scope.map-family.v1"
OPAQUE_ID_RE = re.compile(r"^[0-9a-f]{24}$")
REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_DOCUMENT_BYTES = 16 * 1024
CONVERSION_KEYS = (
    "z_min",
    "z_max",
    "resolution",
    "noise_radius",
    "min_neighbors",
    "background",
)


class MapLineageError(ValueError):
    """A map-family document violates the fixed v1 contract."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MapLineageError("map-family value is not JSON-safe") from exc


def conversion_parameters_hash(parameters: Mapping[str, Any]) -> str:
    """Hash only the fixed semantic conversion inputs in canonical order."""

    if not isinstance(parameters, Mapping) or set(parameters) != set(CONVERSION_KEYS):
        raise MapLineageError("conversion parameters do not match the fixed schema")
    numeric = {}
    for key in ("z_min", "z_max", "resolution", "noise_radius"):
        numeric[key] = _number(
            parameters[key], key, positive=key in {"resolution", "noise_radius"}
        )
    if numeric["z_min"] >= numeric["z_max"]:
        raise MapLineageError("z_min must be less than z_max")
    neighbors = parameters["min_neighbors"]
    if isinstance(neighbors, bool) or not isinstance(neighbors, int) or not 1 <= neighbors <= 1_000:
        raise MapLineageError("min_neighbors is invalid")
    background = parameters["background"]
    if background not in {"unknown", "free"}:
        raise MapLineageError("background is invalid")
    normalized = {**numeric, "min_neighbors": neighbors, "background": background}
    return hashlib.sha256(_canonical(normalized)).hexdigest()


def family_revision(document: Mapping[str, Any]) -> str:
    semantic = {key: value for key, value in document.items() if key != "family_revision"}
    return hashlib.sha256(_canonical(semantic)).hexdigest()


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not OPAQUE_ID_RE.fullmatch(value):
        raise MapLineageError(f"{label} is not a 24-character opaque id")
    return value


def _revision(value: Any, label: str) -> str:
    if not isinstance(value, str) or not REVISION_RE.fullmatch(value):
        raise MapLineageError(f"{label} is not a 64-character revision")
    return value


def _frame(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or any(ord(character) < 32 for character in value)
    ):
        raise MapLineageError(f"{label} is invalid")
    return value


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MapLineageError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0.0):
        raise MapLineageError(f"{label} is invalid")
    return number


def build_family_document(
    *,
    family_id: str,
    mapping_session_id: str,
    pcd_map_id: str,
    pcd_revision: str,
    source_frame_id: str,
    occupancy_map_id: str,
    occupancy_revision: str,
    occupancy_frame_id: str,
    resolution: float,
    width: int,
    height: int,
    origin: tuple[float, float, float] | list[float],
    parameters: Mapping[str, Any],
    created_at: str | None = None,
    derived_from_family_revision: str | None = None,
) -> dict[str, Any]:
    normalized_parameters = {key: parameters.get(key) for key in CONVERSION_KEYS}
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "family_id": _identifier(family_id, "family_id"),
        "source": {
            "pcd_map_id": _identifier(pcd_map_id, "pcd_map_id"),
            "pcd_revision": _revision(pcd_revision, "pcd_revision"),
            "frame_id": _frame(source_frame_id, "source frame_id"),
            "mapping_session_id": _identifier(
                mapping_session_id, "mapping_session_id"
            ),
        },
        "occupancy": {
            "map_id": _identifier(occupancy_map_id, "occupancy map_id"),
            "map_revision": _revision(occupancy_revision, "occupancy revision"),
            "frame_id": _frame(occupancy_frame_id, "occupancy frame_id"),
            "resolution": _number(resolution, "resolution", positive=True),
            "width": width,
            "height": height,
            "origin": list(origin),
        },
        "frame_projection": {
            "method": "planar_xy_identity",
            "source_frame_id": source_frame_id,
            "occupancy_frame_id": occupancy_frame_id,
            "translation": [0.0, 0.0, 0.0],
            "rotation_rpy": [0.0, 0.0, 0.0],
        },
        "conversion": {
            **normalized_parameters,
            "parameters_hash": conversion_parameters_hash(normalized_parameters),
        },
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "derived_from_family_revision": derived_from_family_revision,
    }
    document["family_revision"] = family_revision(document)
    return parse_family_document(document)


def parse_family_document(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema",
        "family_id",
        "family_revision",
        "source",
        "occupancy",
        "frame_projection",
        "conversion",
        "created_at",
        "derived_from_family_revision",
    }:
        raise MapLineageError("map-family document schema is invalid")
    if payload.get("schema") != SCHEMA:
        raise MapLineageError("map-family schema is unsupported")
    source = payload.get("source")
    occupancy = payload.get("occupancy")
    conversion = payload.get("conversion")
    projection = payload.get("frame_projection")
    if not isinstance(source, Mapping) or set(source) != {
        "pcd_map_id", "pcd_revision", "frame_id", "mapping_session_id"
    }:
        raise MapLineageError("map-family source schema is invalid")
    if not isinstance(occupancy, Mapping) or set(occupancy) != {
        "map_id", "map_revision", "frame_id", "resolution", "width", "height", "origin"
    }:
        raise MapLineageError("map-family occupancy schema is invalid")
    if not isinstance(conversion, Mapping) or set(conversion) != {
        *CONVERSION_KEYS, "parameters_hash"
    }:
        raise MapLineageError("map-family conversion schema is invalid")
    if not isinstance(projection, Mapping) or set(projection) != {
        "method", "source_frame_id", "occupancy_frame_id", "translation", "rotation_rpy"
    }:
        raise MapLineageError("map-family frame projection schema is invalid")
    family_id = _identifier(payload.get("family_id"), "family_id")
    revision = _revision(payload.get("family_revision"), "family_revision")
    pcd_map_id = _identifier(source.get("pcd_map_id"), "pcd_map_id")
    pcd_revision = _revision(source.get("pcd_revision"), "pcd_revision")
    mapping_session_id = _identifier(
        source.get("mapping_session_id"), "mapping_session_id"
    )
    source_frame = _frame(source.get("frame_id"), "source frame_id")
    occupancy_map_id = _identifier(occupancy.get("map_id"), "occupancy map_id")
    occupancy_revision = _revision(
        occupancy.get("map_revision"), "occupancy revision"
    )
    occupancy_frame = _frame(occupancy.get("frame_id"), "occupancy frame_id")
    if (
        projection.get("method") != "planar_xy_identity"
        or projection.get("source_frame_id") != source_frame
        or projection.get("occupancy_frame_id") != occupancy_frame
        or projection.get("translation") != [0.0, 0.0, 0.0]
        or projection.get("rotation_rpy") != [0.0, 0.0, 0.0]
    ):
        raise MapLineageError("map-family frame projection is incompatible")
    width, height = occupancy.get("width"), occupancy.get("height")
    if (
        isinstance(width, bool)
        or not isinstance(width, int)
        or width <= 0
        or isinstance(height, bool)
        or not isinstance(height, int)
        or height <= 0
        or width * height > 64_000_000
    ):
        raise MapLineageError("map-family dimensions are invalid")
    resolution = _number(occupancy.get("resolution"), "resolution", positive=True)
    origin = occupancy.get("origin")
    if not isinstance(origin, list) or len(origin) != 3:
        raise MapLineageError("map-family origin is invalid")
    normalized_origin = [_number(item, "origin") for item in origin]
    normalized_parameters = {key: conversion.get(key) for key in CONVERSION_KEYS}
    expected_hash = conversion_parameters_hash(normalized_parameters)
    if float(normalized_parameters["resolution"]) != resolution:
        raise MapLineageError("conversion and occupancy resolutions differ")
    if conversion.get("parameters_hash") != expected_hash:
        raise MapLineageError("conversion parameter hash does not match its content")
    derived = payload.get("derived_from_family_revision")
    if derived is not None:
        derived = _revision(derived, "derived family revision")
    created_at = payload.get("created_at")
    if not isinstance(created_at, str) or len(created_at) > 64:
        raise MapLineageError("map-family created_at is invalid")
    try:
        parsed_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MapLineageError("map-family created_at is invalid") from exc
    if parsed_time.tzinfo is None:
        raise MapLineageError("map-family created_at must include a timezone")
    normalized = {
        "schema": SCHEMA,
        "family_id": family_id,
        "source": {
            "pcd_map_id": pcd_map_id,
            "pcd_revision": pcd_revision,
            "frame_id": source_frame,
            "mapping_session_id": mapping_session_id,
        },
        "occupancy": {
            "map_id": occupancy_map_id,
            "map_revision": occupancy_revision,
            "frame_id": occupancy_frame,
            "resolution": resolution,
            "width": width,
            "height": height,
            "origin": normalized_origin,
        },
        "frame_projection": {
            "method": "planar_xy_identity",
            "source_frame_id": source_frame,
            "occupancy_frame_id": occupancy_frame,
            "translation": [0.0, 0.0, 0.0],
            "rotation_rpy": [0.0, 0.0, 0.0],
        },
        "conversion": {**normalized_parameters, "parameters_hash": expected_hash},
        "created_at": created_at,
        "derived_from_family_revision": derived,
    }
    expected_revision = family_revision(normalized)
    if revision != expected_revision:
        raise MapLineageError("family revision does not match its content")
    normalized["family_revision"] = revision
    return normalized


def serialize_family_document(document: Mapping[str, Any]) -> bytes:
    normalized = parse_family_document(document)
    encoded = (json.dumps(normalized, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > MAX_DOCUMENT_BYTES:
        raise MapLineageError("map-family document exceeds the size limit")
    return encoded


def public_family_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return the complete bounded semantic document (which contains no paths)."""

    return parse_family_document(document)


__all__ = [
    "CONVERSION_KEYS",
    "MAX_DOCUMENT_BYTES",
    "MapLineageError",
    "SCHEMA",
    "build_family_document",
    "conversion_parameters_hash",
    "family_revision",
    "parse_family_document",
    "public_family_document",
    "serialize_family_document",
]
