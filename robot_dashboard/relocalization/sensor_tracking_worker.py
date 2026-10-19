"""Fixed persistent child for unverified, seeded v0.3.1 sensor observations.

The parent supplies only bounded arrays and an SE3 seed. This child never
imports ROS, publishes a transform, or treats a sensor hypothesis as a pose.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
from typing import Any, cast


MAX_MESSAGE_BYTES = 65_536
MAX_ARRAY_BYTES = 32 * 1024 * 1024


def _read_exact(channel: int, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = os.read(channel, size - len(data))
        if not chunk:
            raise EOFError("parent closed the tracking channel")
        data.extend(chunk)
    return bytes(data)


def _receive(channel: int) -> dict[str, Any]:
    size = struct.unpack("!I", _read_exact(channel, 4))[0]
    if not 0 < size <= MAX_MESSAGE_BYTES:
        raise ValueError("SENSOR_COMMAND_LIMIT")
    value = json.loads(_read_exact(channel, size))
    if not isinstance(value, dict):
        raise ValueError("SENSOR_COMMAND_INVALID")
    return cast(dict[str, Any], value)


def _send(channel: int, value: dict[str, Any]) -> None:
    payload = json.dumps(value, allow_nan=False, separators=(",", ":")).encode()
    if len(payload) > MAX_MESSAGE_BYTES:
        payload = b'{"error":"SENSOR_RESULT_LIMIT_NO_TRUNCATION"}'
    packet = memoryview(struct.pack("!I", len(payload)) + payload)
    while packet:
        packet = packet[os.write(channel, packet):]


def _array(path: Path, metadata: dict[str, Any]) -> Any:
    import numpy as np

    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_ARRAY_BYTES:
        raise ValueError("SENSOR_ARRAY_FILE_INVALID")
    raw = path.read_bytes()
    if (len(raw) % 24 or metadata.get("encoding") != "float64_le_xyz"
            or type(metadata.get("point_count")) is not int
            or metadata["point_count"] != len(raw) // 24
            or metadata.get("sha256") != hashlib.sha256(raw).hexdigest()):
        raise ValueError("SENSOR_ARRAY_CONTRACT_MISMATCH")
    result = np.frombuffer(raw, dtype="<f8").reshape(-1, 3)
    if not np.isfinite(result).all():
        raise ValueError("SENSOR_NONFINITE_INPUT")
    # Open3D's Vector3dVector rejects read-only NumPy views of immutable bytes.
    # Copy all original rows unchanged; scoring still uses this full population.
    return result.copy()


def _source(folder: Path, configuration: dict[str, Any]) -> tuple[Any, Any, Any]:
    source = Path(configuration["source_root"])
    files = configuration["pin"]["files"]
    actual = {str(path.relative_to(source)) for path in (source / "auto_localization").rglob("*.py")}
    if actual != set(files):
        raise ValueError("SENSOR_SOURCE_COVERAGE_CHANGED")
    verified = folder / "verified-source"
    for name, expected in files.items():
        path = source / name
        raw = path.read_bytes()
        if path.resolve() != path or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("SENSOR_SOURCE_CHANGED")
        target = verified / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    sys.path.insert(0, str(verified))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from v031_observation_compat import observer_class, supports_pin

    if not supports_pin(files):
        raise ValueError("SENSOR_REVIEWED_SOURCE_REQUIRED")
    from auto_localization import isolated, se3_observation
    return observer_class(se3_observation), se3_observation, isolated


def _coarse_source(observer: Any, scan: Any) -> Any:
    """Use the original `_features` fit points without unused FPFH/normals.

    The pinned `_refine` is point-to-point ICP: it reads only these points.
    Keep its original voxel and deterministic max-fit population exactly.
    """
    import numpy as np

    cfg = observer.cfg
    cloud = observer.o3d.geometry.PointCloud(observer.o3d.utility.Vector3dVector(scan))
    cloud = cloud.voxel_down_sample(cfg.voxel_m)
    if len(cloud.points) > cfg.max_fit_points:
        indices = np.random.default_rng(cfg.seed).choice(len(cloud.points), cfg.max_fit_points,
                                                         replace=False)
        cloud = cloud.select_by_index(sorted(indices.tolist()))
    return cloud


def _align(observer: Any, backend: Any, isolated: Any, scan: Any, seed: Any,
           context: dict[str, Any], map_metadata: dict[str, Any],
           pin_sha: str) -> dict[str, Any]:
    import numpy as np
    from v031_observation_compat import SELECTION_POLICY

    started = time.monotonic()
    matrix = np.asarray(seed, dtype=float)
    if not backend._rigid(matrix):
        raise ValueError("SENSOR_SEED_NOT_RIGID")
    source = _coarse_source(observer, scan)
    if len(source.points) < 4:
        raise ValueError("SENSOR_FEATURE_SUPPORT_INSUFFICIENT")
    branches = []
    coarse_matrix = matrix
    for name in ("coarse_icp", "robust_full_reference", "multiscale_point_to_plane"):
        incoming = coarse_matrix if name == "robust_full_reference" else matrix
        observer._last_refinement_diagnostics = {}
        phase_start = time.monotonic()
        try:
            if name == "coarse_icp":
                refined, stationary = observer._refine(source, incoming)
            elif name == "robust_full_reference":
                refined, stationary = observer._refine_full(scan, incoming)
            else:
                refined, stationary = observer._refine_plane(scan, incoming)
            candidate = observer._score(scan, refined, 0)
            candidate.refinement_stationary = bool(stationary)
            if not stationary:
                candidate.gate_reasons.append("REFINEMENT_NOT_STATIONARY")
            if name == "coarse_icp" and backend._rigid(np.asarray(refined)):
                coarse_matrix = np.asarray(refined).copy()
        except (RuntimeError, ValueError) as error:
            # Keep the failed branch as rejected evidence. Never promote its
            # incoming seed just because another refinement raised an error.
            candidate = observer._score(scan, incoming, 0)
            candidate.gate_reasons.append("REGISTRATION_ERROR:" + type(error).__name__)
            candidate.refinement_stationary = False
        candidate.selected_refinement_stage = name
        candidate.proposal_transform = matrix.copy()
        candidate.phase_seconds = {name: time.monotonic() - phase_start}
        candidate.refinement_diagnostics = dict(observer._last_refinement_diagnostics)
        candidate.refinement_stages = [observer._stage(name, candidate)]
        branches.append(candidate)
    # Preserve the pinned backend's ranking and duplicate/ambiguity decision.
    # These are only three local branches of one supplied seed, not a global
    # search for alternate basins.
    ranked = sorted(branches, key=lambda item: (bool(item.gate_reasons), item.capped_full_rmse_m))
    result: dict[str, Any] = isolated._json_observation(observer._finish(ranked))
    result.update(status="OBSERVATION_ONLY_UNVERIFIED",
                  backend="open3d_unrestricted_se3_observation",
                  selection_policy=dict(SELECTION_POLICY),
                  local_scope="ONE_SEED_THREE_REFINEMENT_BRANCHES_NOT_GLOBAL_AMBIGUITY_RECHECK",
                  elapsed_s=time.monotonic() - started,
                  source_pin_sha256=pin_sha,
                  frame_id=context["source_frame"],
                  session_id=context["observer_epoch"],
                  observer_id=context["observer_id"],
                  source_stamp_ns=context["source_stamp_ns"],
                  input_points=len(scan), reference_points=map_metadata["point_count"],
                  map_id="sha256:" + map_metadata["sha256"],
                  map_revision=context["map_revision"],
                  body_pose=None, current_pose=None, tracking_verified=False,
                  operational_tf_applied=False)
    selected = result["selected_candidate"]
    if selected is not None:
        candidate = result["candidates"][selected]
        for field in ("map_from_scan", "rmse_m", "overlap", "scan_count",
                      "full_scan_rmse_m", "capped_full_rmse_m", "inlier_count",
                      "distinct_inlier_voxel_count", "geometry_min_max_eigen_ratio",
                      "inlier_geometry_min_max_eigen_ratio", "refinement_stationary"):
            result[field] = candidate[field]
    return result


def main(folder: Path, channel: int) -> None:
    configuration = json.loads((folder / "config.json").read_text())
    observer_class, backend, isolated = _source(folder, configuration)
    map_metadata = configuration["context"]["map"]
    world = _array(folder / "map.f64", map_metadata)
    observer = observer_class(world, map_frame=configuration["context"]["map_frame"],
                              scan_frame=configuration["context"]["source_frame"])
    _send(channel, {"ready": True, "source_pin_sha256": configuration["pin_sha256"],
                    "map_sha256": map_metadata["sha256"], "reference_points": len(world)})
    last_sequence = 0
    while True:
        request = _receive(channel)
        if request.get("operation") == "close":
            _send(channel, {"closed": True})
            return
        if request.get("operation") != "align":
            raise ValueError("SENSOR_OPERATION_INVALID")
        sequence = request.get("sequence")
        if type(sequence) is not int or not last_sequence < sequence <= 99_999_999:
            raise ValueError("SENSOR_SEQUENCE_INVALID")
        last_sequence = sequence
        context = request["context"]
        if (context["map"]["sha256"] != map_metadata["sha256"]
                or context["map"]["point_count"] != map_metadata["point_count"]
                or context["map_frame"] != observer.map_frame
                or context["source_frame"] != observer.scan_frame):
            raise ValueError("SENSOR_CONTEXT_CHANGED")
        scan = _array(folder / f"scan-{sequence:08d}.f64", context["scan"])
        try:
            result = _align(observer, backend, isolated, scan, request["seed_matrix"],
                            context, map_metadata, configuration["pin_sha256"])
            _send(channel, {"sequence": sequence, "result": result})
        except (ValueError, RuntimeError, TypeError, KeyError) as error:
            _send(channel, {"sequence": sequence, "error": "SENSOR_LOCAL_ALIGNMENT_FAILED",
                            "error_type": type(error).__name__})


if __name__ == "__main__":
    connection = int(sys.argv[2])
    try:
        main(Path(sys.argv[1]), connection)
    finally:
        os.close(connection)
