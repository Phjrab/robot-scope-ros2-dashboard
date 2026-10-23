#!/usr/bin/env python3
"""Verify and replay three archived sensor observations; never contact ROS.

The separate pinned v0.3.1 backend must be supplied by the operator. This
script does not turn a historical sensor observation into a current/body pose.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import threading

import numpy as np


BUNDLE = Path(__file__).resolve().parent
MAP_FILE_SHA256 = "c347faea6fd7a2f353b39f1f69f93cab8f2c6243299f90f87e54b7d8172ce4b8"
MAP_XYZ_SHA256 = "2e436c8cd41db44ac7130d81df8b23dd01e4875dd42ffcb1c1dbd18780da5852"
CAPTURE_MANIFEST_SHA256 = "abbaeaeddb72737faaf71a3438315275c76e96a2d49ba6f96e909a301d9f8ffe"
RAW_SCAN_SHA256 = (
    "fbb730e5716bb7a59c5614e463c30e4d4a30e625ed160eebc44d935d5349d7dd",
    "05291f8cc6146fecf5c8a2b80225b2c40086a6e60cbc0479d4a2fe97cb04716c",
    "42e922e5cce17d9218bf055bbf988e5c5168e3507c15bb67f50f373ec1387157",
)
XYZ_SCAN_SHA256 = (
    "b3baef87577566a72066c8ecec84d66be0fae616b7d535ac9d6580b2bc36f9c2",
    "3ad5726691ef8ef5f23bfee82ab7e4194b8fe6c53056b7e583687a9275fd7c07",
    "eae0d6daf11e4103489f8faff35cd0801c04370bdad049d52890a345a86a9b52",
)
SOURCE_STAMP_NS = (
    "1792406869346463680", "1792406869446533680", "1792406869546594620",
)
POINTS_PER_SCAN = 16000
MAP_POINTS = 25666
MATCH_RADIUS_M = 0.75


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def _checked_bytes(relative: str, expected_sha256: str, expected_size: int | None = None) -> bytes:
    path = BUNDLE / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError("required regular file missing: " + relative)
    data = path.read_bytes()
    if _sha(data) != expected_sha256 or (expected_size is not None and len(data) != expected_size):
        raise ValueError("input bytes changed: " + relative)
    return data


def _verify_listed_files() -> None:
    public = _json(BUNDLE / "PUBLIC_MANIFEST.json")
    if public.get("schema") != "robot-scope.public-replay-selected-files.v1":
        raise ValueError("public manifest schema changed")
    files = public.get("files")
    if not isinstance(files, list) or len(files) < 13:
        raise ValueError("public manifest incomplete")
    paths: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("public manifest entry invalid")
        relative = item.get("path")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("public manifest path invalid")
        if relative in paths or type(item.get("bytes")) is not int or item["bytes"] < 0:
            raise ValueError("public manifest duplicate or size invalid")
        paths.add(relative)
        _checked_bytes(relative, item["sha256"], item["bytes"])
    required = {"maps/map_20261018_162315.pcd", "capture/manifest.json",
                "results/ambiguity-off.json", "results/ambiguity-on.json",
                "reference/runtime-pin.receipt-generated.json"}
    if not required.issubset(paths):
        raise ValueError("public manifest omits a required input")


def _map_xyz() -> bytes:
    raw = _checked_bytes("maps/map_20261018_162315.pcd", MAP_FILE_SHA256, 410813)
    marker = b"DATA binary\n"
    boundary = raw.find(marker)
    if boundary < 0 or boundary > 65536:
        raise ValueError("binary PCD header missing or too large")
    header = raw[:boundary + len(marker)].decode("ascii").splitlines()
    fields: dict[str, list[str]] = {}
    for line in header:
        if line.startswith("#") or not line:
            continue
        key, *values = line.split()
        fields[key] = values
    expected = {"FIELDS": ["x", "y", "z", "intensity"],
                "SIZE": ["4"] * 4, "TYPE": ["F"] * 4,
                "COUNT": ["1"] * 4, "WIDTH": [str(MAP_POINTS)],
                "HEIGHT": ["1"], "POINTS": [str(MAP_POINTS)],
                "DATA": ["binary"]}
    if any(fields.get(key) != value for key, value in expected.items()):
        raise ValueError("PCD layout changed")
    payload = raw[boundary + len(marker):]
    if len(payload) != MAP_POINTS * 16:
        raise ValueError("PCD population changed")
    records = np.frombuffer(payload, dtype=np.dtype([
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("intensity", "<f4")]))
    xyz = np.column_stack((records["x"], records["y"], records["z"])).astype("<f8", copy=False)
    if not np.isfinite(xyz).all():
        raise ValueError("nonfinite map rows unsupported; no points may be removed")
    packed = xyz.tobytes(order="C")
    if _sha(packed) != MAP_XYZ_SHA256:
        raise ValueError("full map XYZ hash changed")
    return packed


def _scan_xyz(index: int, cloud: dict) -> bytes:
    prefix = f"capture/cloud-{index:03d}"
    raw = _checked_bytes(prefix + ".pointcloud2-data.bin", RAW_SCAN_SHA256[index], POINTS_PER_SCAN * 22)
    stored = _checked_bytes(prefix + ".xyz-f64le.bin", XYZ_SCAN_SHA256[index], POINTS_PER_SCAN * 24)
    layout = cloud["layout"]
    expected_fields = [("x", 0, 7), ("y", 4, 7), ("z", 8, 7),
                       ("intensity", 12, 7), ("time", 16, 7), ("ring", 20, 4)]
    if ([(item.get("name"), item.get("offset"), item.get("datatype")) for item in layout["fields"]]
            != expected_fields or any(item.get("count") != 1 for item in layout["fields"])
            or layout.get("is_bigendian") is not False or layout.get("height") != 1
            or layout.get("width") != POINTS_PER_SCAN or layout.get("point_step") != 22
            or layout.get("row_step") != len(raw)):
        raise ValueError("PointCloud2 layout changed")
    records = np.frombuffer(raw, dtype=np.dtype({
        "names": ["x", "y", "z", "intensity", "time", "ring"],
        "formats": ["<f4"] * 5 + ["<u2"],
        "offsets": [0, 4, 8, 12, 16, 20], "itemsize": 22,
    }))
    xyz = np.column_stack((records["x"], records["y"], records["z"])).astype("<f8", copy=False)
    if not np.isfinite(xyz).all() or xyz.tobytes(order="C") != stored:
        raise ValueError("stored XYZ differs from every original raw XYZ point")
    if (cloud["raw_data"].get("sha256") != RAW_SCAN_SHA256[index]
            or cloud["full_xyz"].get("sha256") != XYZ_SCAN_SHA256[index]
            or cloud["full_xyz"].get("source_points") != POINTS_PER_SCAN
            or cloud["full_xyz"].get("captured_points") != POINTS_PER_SCAN
            or cloud.get("source_stamp_ns") != SOURCE_STAMP_NS[index]
            or cloud.get("frame_id") != "hesai_lidar"):
        raise ValueError("capture metadata disagrees with raw scan")
    return stored


def _inputs() -> tuple[bytes, list[bytes], list[dict], dict, dict]:
    _verify_listed_files()
    _checked_bytes("capture/manifest.json", CAPTURE_MANIFEST_SHA256)
    capture = _json(BUNDLE / "capture/manifest.json")
    off = _json(BUNDLE / "results/ambiguity-off.json")
    on = _json(BUNDLE / "results/ambiguity-on.json")
    if (capture.get("status") != "READY_FOR_OFFLINE_INSPECTION" or len(capture.get("clouds", [])) != 3
            or len(off.get("scans", [])) != 3 or len(on.get("scans", [])) != 3
            or off.get("capture_manifest_sha256") != CAPTURE_MANIFEST_SHA256
            or on.get("capture_manifest_sha256") != CAPTURE_MANIFEST_SHA256):
        raise ValueError("capture/result identity mismatch")
    map_bytes = _map_xyz()
    scans = [_scan_xyz(i, cloud) for i, cloud in enumerate(capture["clouds"])]
    contexts = []
    for i, (off_scan, on_scan, cloud, scan_bytes) in enumerate(zip(off["scans"], on["scans"], capture["clouds"], scans)):
        if off_scan.get("cloud_index") != i or on_scan.get("cloud_index") != i:
            raise ValueError("scan result index mismatch")
        context = off_scan.get("captured_context")
        if not isinstance(context, dict) or context != on_scan.get("captured_context"):
            raise ValueError("OFF/ON contexts differ")
        m, s = context.get("map"), context.get("scan")
        if (not isinstance(m, dict) or not isinstance(s, dict)
                or m.get("source_sha256") != MAP_FILE_SHA256
                or m.get("sha256") != MAP_XYZ_SHA256 or m.get("point_count") != MAP_POINTS
                or s.get("raw_data_sha256") != RAW_SCAN_SHA256[i]
                or s.get("sha256") != _sha(scan_bytes) or s.get("point_count") != POINTS_PER_SCAN
                or context.get("source_stamp_ns") != SOURCE_STAMP_NS[i]
                or context.get("source_frame") != cloud["frame_id"]
                or context.get("observer_id") != cloud["identity"]["observer_id"]
                or context.get("observer_epoch") != cloud["identity"]["observer_epoch"]
                or context.get("map_frame") != "camera_init"
                or context.get("source_clock_verified") is not False
                or context.get("body_extrinsic_verified") is not False):
            raise ValueError("archived context does not bind original arrays and capture")
        contexts.append(context)
    return map_bytes, scans, contexts, off, on


def _score_stored(map_bytes: bytes, scans: list[bytes], on: dict) -> list[dict]:
    # This independently checks recorded scores. It does not choose candidates,
    # run registration, estimate accuracy, or alter the backend's ambiguity gate.
    from scipy.spatial import cKDTree

    reference = np.frombuffer(map_bytes, dtype="<f8").reshape((-1, 3))
    tree = cKDTree(reference)
    summaries = []
    for i, scan_bytes in enumerate(scans):
        result = on["scans"][i]["backend_result"]
        selected = result.get("selected_candidate")
        if (type(selected) is not int or not 0 <= selected < len(result.get("candidates", []))
                or result.get("gate_reasons") != ["AMBIGUOUS_ALTERNATIVES"]
                or result.get("estimate_label") != "AMBIGUOUS_UNVERIFIED_ESTIMATE"
                or result.get("ambiguity_override", {}).get("applied") is not True):
            raise ValueError("stored ON result is not an explicit ambiguous observation")
        candidate = result["candidates"][selected]
        transform = np.asarray(candidate["map_from_scan"], dtype="<f8")
        if transform.shape != (4, 4) or not np.isfinite(transform).all():
            raise ValueError("stored transform invalid")
        scan = np.frombuffer(scan_bytes, dtype="<f8").reshape((-1, 3))
        mapped = scan @ transform[:3, :3].T + transform[:3, 3]
        distance, _ = tree.query(mapped)
        inlier = distance <= MATCH_RADIUS_M
        if not inlier.any():
            raise ValueError("recorded candidate has no full-population inliers")
        metrics = {"rmse_m": float(np.sqrt(np.mean(np.square(distance[inlier])))),
                   "full_scan_rmse_m": float(np.sqrt(np.mean(np.square(distance)))),
                   "capped_full_rmse_m": float(np.sqrt(np.mean(np.square(np.minimum(distance, MATCH_RADIUS_M))))),
                   "overlap": float(np.mean(inlier)), "inlier_count": int(inlier.sum())}
        for key, value in metrics.items():
            original = candidate.get(key)
            if not isinstance(original, (int, float)) or not math.isclose(value, original, rel_tol=0., abs_tol=1e-10):
                raise ValueError("whole-scan score disagrees: scan " + str(i) + " " + key)
        summaries.append({"scan_index": i, "selected_candidate": selected,
                          "source_stamp_ns": SOURCE_STAMP_NS[i], "input_points": len(scan),
                          "reference_points": len(reference), **metrics,
                          "gate_reasons": result["gate_reasons"]})
    return summaries


def _replay(args: argparse.Namespace, map_bytes: bytes, scans: list[bytes], contexts: list[dict],
            off: dict, on: dict) -> dict:
    dashboard = Path(args.dashboard_root)
    if not dashboard.is_absolute() or not (dashboard / "robot_dashboard/relocalization/external_global_observation.py").is_file():
        raise ValueError("dashboard root must be an absolute checkout with the committed runner")
    output = Path(args.output_dir)
    if not output.is_absolute() or output.resolve().is_relative_to(BUNDLE) or output.exists():
        raise ValueError("output must be a new absolute directory outside the packet")
    for name in ("backend_python", "backend_source", "pin_file"):
        if not Path(getattr(args, name)).is_absolute():
            raise ValueError("backend interpreter, source and pin paths must be absolute")
    sys.path.insert(0, str(dashboard))
    from robot_dashboard.relocalization.external_global_observation import ExternalGlobalObservationRunner

    runner = ExternalGlobalObservationRunner(args.backend_python, args.backend_source,
                                             args.pin_file, timeout_s=120.,
                                             allow_ambiguous=args.mode == "on")
    status = runner.status()
    if not status["available"]:
        raise ValueError("pinned external backend unavailable: " + str(status["reason"]))
    indexes = range(3) if args.scan_index is None else [args.scan_index]
    output.mkdir(mode=0o700, parents=False)
    summaries = []
    for i in indexes:
        context = contexts[i]
        worker_context = {key: context[key] for key in
                          ("map_id", "map_revision", "map_frame", "source_frame", "observer_id",
                           "observer_epoch", "source_stamp_ns")}
        worker_context["map"] = {key: context["map"][key] for key in ("encoding", "point_count", "sha256")}
        worker_context["scan"] = {key: context["scan"][key] for key in ("encoding", "point_count", "sha256")}
        result = runner.run_arrays(scan_bytes=scans[i], map_bytes=map_bytes,
                                   context=worker_context, cancel_event=threading.Event())
        if (result.get("tracking_verified") is True
                or result.get("body_pose") is not None
                or result.get("current_pose") is not None):
            raise ValueError("historical sensor result unexpectedly claimed operational pose")
        expected = (on if args.mode == "on" else off)["scans"][i]["backend_result"]
        path = output / f"scan-{i:03d}.result.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        path.chmod(0o600)
        chosen = result.get("selected_candidate")
        candidate = result["candidates"][chosen] if type(chosen) is int else None
        summaries.append({"scan_index": i, "source_stamp_ns": SOURCE_STAMP_NS[i],
                          "selected_candidate": chosen, "recorded_selected_candidate": expected.get("selected_candidate"),
                          "rmse_m": candidate.get("rmse_m") if candidate else None,
                          "recorded_rmse_m": expected["candidates"][expected["selected_candidate"]]["rmse_m"]
                          if type(expected.get("selected_candidate")) is int else None,
                          "gate_reasons": result.get("gate_reasons"), "input_points": result.get("input_points"),
                          "reference_points": result.get("reference_points"),
                          "historical_sensor_observation_only": True})
    summary = {"schema": "robot-scope.public-replay-result.v1", "mode": args.mode,
               "source_pin_sha256": status["source_pin_sha256"],
               "historical_only": True, "source_clock_verified": False,
               "body_extrinsic_verified": False, "tracking_verified": False,
               "body_pose": None, "current_pose": None, "absolute_accuracy_m": None,
               "scans": summaries}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "summary.json").chmod(0o600)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify", help="verify exact archived bytes and full-point stored ON scores; no backend")
    replay = sub.add_parser("replay", help="run the separate pinned backend on archived full XYZ arrays")
    replay.add_argument("--dashboard-root", required=True)
    replay.add_argument("--backend-python", required=True)
    replay.add_argument("--backend-source", required=True)
    replay.add_argument("--pin-file", required=True)
    replay.add_argument("--output-dir", required=True)
    replay.add_argument("--mode", choices=("off", "on"), required=True)
    replay.add_argument("--scan-index", type=int, choices=(0, 1, 2))
    args = parser.parse_args()
    map_bytes, scans, contexts, off, on = _inputs()
    if args.command == "verify":
        summary = {"schema": "robot-scope.public-replay-verification.v1",
                   "exact_source_map_sha256": MAP_FILE_SHA256,
                   "full_map_xyz_sha256": MAP_XYZ_SHA256,
                   "capture_manifest_sha256": CAPTURE_MANIFEST_SHA256,
                   "full_original_xyz_points_per_scan": POINTS_PER_SCAN,
                   "full_original_map_points": MAP_POINTS,
                   "stored_on_full_point_scores": _score_stored(map_bytes, scans, on),
                   "historical_only": True, "source_clock_verified": False,
                   "body_extrinsic_verified": False, "tracking_verified": False,
                   "body_pose": None, "current_pose": None, "absolute_accuracy_m": None}
    else:
        summary = _replay(args, map_bytes, scans, contexts, off, on)
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("replay input or execution rejected: " + str(exc), file=sys.stderr)
        raise SystemExit(2) from None
