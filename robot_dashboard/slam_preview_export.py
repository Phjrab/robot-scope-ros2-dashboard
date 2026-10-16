"""Derived files from one saved visualization snapshot; never reads native DBs."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from typing import Any, NoReturn

MAX_POINTS = 60_000
MAX_EXPORT_BYTES = 32 * 1024**2


class PreviewExportError(ValueError):
    pass


def _invalid() -> NoReturn:
    raise PreviewExportError("INVALID_PREVIEW_EXPORT")


def _vector(value: Any, dimensions: int) -> list[float]:
    if (not isinstance(value, list) or len(value) != dimensions or
            any(isinstance(x, bool) or not isinstance(x, (int, float)) or
                abs(x) > 1_000_000 or not math.isfinite(x) for x in value)):
        _invalid()
    return value


def _label(value: Any) -> str | None:
    if value is None:
        return None
    if (not isinstance(value, str) or not value or len(value) > 256 or
            any(ord(char) < 32 for char in value)):
        _invalid()
    return value


def _stamp(value: Any) -> str | None:
    if value is None:
        return None
    if (not isinstance(value, str) or not value.isascii() or not value.isdigit()
            or not 1 <= len(value) <= 20):
        _invalid()
    return value


def _frame(value: Any) -> str | None:
    result = _label(value)
    if result is not None and (result.startswith("-") or any(
            not char.isascii() or not (char.isalnum() or char in "_/-") for char in result)):
        _invalid()
    return result


def _csv(headers: list[str], rows: Any) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def preview_export_files(manifest: dict, preview: Any, *, max_bytes: int) -> dict[str, bytes]:
    """Validate all coordinates atomically, with no sampling or coverage inference.

    Source labels/times describe the saved preview, not this download or a live
    runtime. Native completeness and IDs cannot be established by this exporter.
    """
    if not isinstance(preview, dict):
        _invalid()
    frame = _frame(preview.get("frame_id"))
    epoch = _label(preview.get("map_epoch"))
    if frame is None or epoch is None or frame != manifest.get("map_frame"):
        _invalid()
    if (preview.get("engine_id") not in (None, manifest.get("engine_id")) or
            (manifest.get("source_session_id") is not None and
             preview.get("session_id") not in (None, manifest["source_session_id"]))):
        _invalid()
    generation = preview.get("generation")
    if generation is not None and (type(generation) is not int or not 1 <= generation <= 1_000_000_000):
        _invalid()
    files: dict[str, bytes] = {}
    layers: dict[str, Any] = {}
    for key, filename in (("global_map", "global-map.xyz"), ("trajectory", "trajectory.csv")):
        layer = preview.get(key)
        if layer is None:
            layers[key] = {"available": False}
            continue
        if (not isinstance(layer, dict) or layer.get("coordinate_frame") != frame or
                layer.get("map_epoch") != epoch or not isinstance(layer.get("points"), list) or
                len(layer["points"]) > MAX_POINTS):
            _invalid()
        points = [_vector(point, 3) for point in layer["points"]]
        if key == "global_map":
            files[filename] = "".join(" ".join(format(x, ".17g") for x in p) + "\n" for p in points).encode("ascii")
        else:
            files[filename] = _csv(["index", "x", "y", "z"], ((i, *p) for i, p in enumerate(points)))
        layers[key] = {
            "available": True, "file": filename, "exported_rows": len(points),
            "coordinate_frame": frame, "map_epoch": epoch,
            "source_id": _label(layer.get("source_id")),
            "source_timestamp_ns": _stamp(layer.get("source_timestamp_ns")),
            "provenance": _label(layer.get("provenance")),
            "trajectory_kind": _label(layer.get("trajectory_kind")),
            "source_declared_coverage": _label(layer.get("coverage")),
            "coverage": "subset" if layer.get("coverage") == "subset" else "unknown",
            "engine_total_count": None, "native_ids_exported": False,
            "source_declared_decimation": (layer.get("decimation")
                if type(layer.get("decimation")) is bool else None),
            "scope": ("saved_exported_global_points" if key == "global_map" else
                      "bounded_saved_trajectory; not a full observed camera path"),
        }
    pose = preview.get("camera_pose")
    if pose is not None:
        if not isinstance(pose, dict) or pose.get("frame_id") != frame:
            _invalid()
        # Older saved poses carry only frame_id. If a producer supplies more
        # context, it must not contradict the snapshot receiving this pose.
        pose_context = {
            "coordinate_frame": frame, "map_epoch": epoch,
            "session_id": preview.get("session_id") or manifest.get("source_session_id"),
            "generation": generation, "engine_id": manifest.get("engine_id"),
        }
        for key, expected in pose_context.items():
            if key in pose and (type(pose[key]) is not type(expected) or pose[key] != expected):
                _invalid()
        position = _vector(pose.get("position"), 3)
        quaternion = _vector(pose.get("quaternion_xyzw"), 4)
        if abs(sum(x*x for x in quaternion) - 1) > 0.02:
            _invalid()
        pose_stamp = _stamp(pose.get("stamp_ns"))
        reference = _frame(pose.get("pose_reference"))
        files["camera-pose.csv"] = _csv(
            ["stamp_ns", "frame_id", "pose_reference", "x", "y", "z", "qx", "qy", "qz", "qw"],
            [(pose_stamp, frame, reference, *position, *quaternion)])
        layers["camera_pose"] = {"available": True, "file": "camera-pose.csv", "exported_rows": 1,
            "source_id": _label(pose.get("source_topic")), "source_timestamp_ns": pose_stamp,
            "coordinate_frame": frame, "pose_reference": reference,
            "scope": "single_saved_camera_pose; not Go2 body or ground truth"}
    else:
        layers["camera_pose"] = {"available": False}
    if not files:
        raise PreviewExportError("PREVIEW_EXPORT_UNAVAILABLE")
    provenance = {
        "schema": "robot-scope.saved-preview-export/v1", "export_kind": "saved_visualization_snapshot",
        "package_id": manifest["package_id"], "revision": manifest["revision"],
        "preview_revision": manifest["preview_revision"],
        "native_content_revision": manifest["native_content_revision"],
        "preview_consistency": manifest["preview_consistency"],
        "preview_capture_time": manifest.get("preview_capture_time"),
        "session_id": _label(preview.get("session_id")), "map_epoch": epoch,
        "generation": generation,
        "engine_id": _label(manifest.get("engine_id")),
        "engine_version": manifest.get("engine_version"),
        "native_format_version": manifest.get("native_format_version"),
        "calibration_hash": manifest.get("calibration_hash"),
        "sensor_config_hash": manifest.get("sensor_config_hash"),
        "data_provenance": manifest.get("data_provenance", "unknown"),
        "frame_id": frame, "units": manifest.get("units"), "axes": manifest.get("axes"),
        "native_full_map_export": False, "native_completeness_verified": False,
        "coverage_note": "Saved visualization only. Source declarations do not attest full native coverage.",
        "layers": layers,
        "files": {name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                  for name, raw in files.items()},
    }
    try:
        files["provenance.json"] = json.dumps(provenance, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        _invalid()
    if sum(map(len, files.values())) > min(max_bytes, MAX_EXPORT_BYTES):
        raise PreviewExportError("PACKAGE_LIMIT")
    return files
