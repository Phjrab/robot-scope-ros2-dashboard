"""Immutable binary-PCD export, independent of HTTP, catalogue and ROS.

Only explicit named height-band occupancy is supported. No observation of free
space is inferred. Descriptor provenance is a bounded DAG of {id, parents};
leaves are immutable root identifiers. Duplicate leaves across input sources
require review rather than silently changing density. This is not C1 validation.
"""

from __future__ import annotations
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

import numpy as np
from robot_dashboard.pcd_editing.pcd import (
    _read_header,
    _output_header,
    _identity,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_POINTS,
    MAX_CHUNK_BYTES,
)
from robot_dashboard.relocalization.experimental_se3 import validate_transform


class ExportError(ValueError):
    """Stale, unsupported or unsafe export; no candidate is published."""


def source_key(source):
    return "@".join(str(source[k]) for k in ("map_id", "revision", "frame_id"))


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(MAX_CHUNK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def provenance_roots(sources):
    """Reject cycles, excessive depth/size and repeated root contributions."""
    roots, nodes, definitions = set(), 0, {}

    def visit(node, active, depth):
        nonlocal nodes
        nodes += 1
        if nodes > 1024 or depth > 32:
            raise ExportError("Provenance bounds exceeded")
        ident = node["id"]
        if not isinstance(ident, str) or not ident or ident in active:
            raise ExportError("Provenance cycle/invalid identity")
        encoded = _canonical(node)
        if ident in definitions and definitions[ident] != encoded:
            raise ExportError("Conflicting provenance identity")
        definitions[ident] = encoded
        parents = node.get("parents", [])
        if not parents:
            return {ident}
        result = set()
        for parent in parents:
            leaves = visit(parent, active | {ident}, depth + 1)
            if result & leaves:
                raise ExportError("Duplicate root within provenance requires review")
            result |= leaves
        return result

    for source in sources:
        leaves = visit(source.get("provenance", {"id": source_key(source)}), set(), 0)
        if roots & leaves:
            raise ExportError(
                "Duplicate root sources require review (including transform conflicts)"
            )
        roots |= leaves
    return sorted(roots)


def _surface(value):
    if value is None:
        return None
    result = {k: value[k] for k in ("name", "z_min", "z_max", "resolution")}
    if not isinstance(result["name"], str) or not result["name"]:
        raise ExportError("Occupancy requires a named surface")
    vals = [float(result[k]) for k in ("z_min", "z_max", "resolution")]
    if not np.isfinite(vals).all() or vals[0] >= vals[1] or not 0.01 <= vals[2] <= 10:
        raise ExportError("Invalid bounded occupancy height band/resolution")
    return dict(zip(("name", "z_min", "z_max", "resolution"), [result["name"], *vals]))


def export(proposal, expected_revision, resolver, output_root, *, chunk_points=65536):
    """Export every full-source record, atomically and idempotently.

    Resolver accepts a descriptor, returns its trusted local Path. Inputs must
    be pinned by descriptor sha256. Optional occupancy_surface is a named,
    user-selected obstacle height band in the final fused frame, not a claim
    that a multi-floor/ramp scene can be flattened safely. Source raw files are
    copied privately for provenance. Existing publications are never replaced.
    """
    if proposal.get("status") != "SOLVED_CANDIDATE":
        raise ExportError("Only a solved candidate may be exported")
    if proposal.get("proposal_revision") != expected_revision:
        raise ExportError("Stale proposal revision")
    if type(chunk_points) is not int or not 1 <= chunk_points <= 1000000:
        raise ExportError("Invalid chunk bound")
    sources = proposal["sources"]
    if proposal.get("input_pins") != sources:
        raise ExportError("Input pins/revisions do not match sources")
    if proposal.get("evidence_kind", "SYNTHETIC") not in ("SYNTHETIC", "REPLAY"):
        raise ExportError("Offline evidence required")
    if not 2 <= len(sources) <= 32:
        raise ExportError("Expected 2..32 full sources")
    roots = provenance_roots(sources)
    transforms = {
        item["source_key"]: validate_transform(item["T"])
        for item in proposal["T_fused_source"]
    }
    if len(transforms) != len(sources) or set(transforms) != {
        source_key(s) for s in sources
    }:
        raise ExportError("Source transforms do not match inputs")
    surface = _surface(proposal.get("occupancy_surface"))
    fingerprint = hashlib.sha256(_canonical(proposal)).hexdigest()
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    # Lock covers idempotency lookup and rename; private local filesystem only.
    with (root / ".export.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        destination = root / fingerprint
        if destination.exists():
            for source in sources:
                if _hash(Path(resolver(source))) != source["sha256"]:
                    raise ExportError("Source changed before idempotent return")
            manifest = json.loads((destination / "manifest.json").read_text())
            if manifest["proposal_hash"] != fingerprint or any(
                _hash(destination / name) != digest
                for name, digest in manifest["output_hashes"].items()
            ):
                raise ExportError("Existing publication is corrupt")
            return manifest
        stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=root))
        try:
            snapshots, total, layout = [], 0, None
            (stage / "sources").mkdir()
            for index, source in enumerate(sources):
                if (
                    source.get("units") != "m"
                    or source.get("asset_role") != "full_source"
                ):
                    raise ExportError("Require metre full_source descriptor")
                path = Path(resolver(source))
                with path.open("rb") as original:
                    initial = os.fstat(original.fileno())
                    if (
                        not stat.S_ISREG(initial.st_mode)
                        or initial.st_size > DEFAULT_MAX_BYTES
                    ):
                        raise ExportError("Source not regular or too large")
                    snapshot = stage / "sources" / f"{index}.pcd"
                    with snapshot.open("xb") as copy:
                        shutil.copyfileobj(original, copy, MAX_CHUNK_BYTES)
                    if _identity(os.fstat(original.fileno())) != _identity(initial):
                        raise ExportError("Source changed during snapshot")
                if _hash(snapshot) != source["sha256"]:
                    raise ExportError("Source hash/revision changed")
                with snapshot.open("rb") as stream:
                    lines, header, dtype, count, fields = _read_header(
                        stream, snapshot.stat().st_size, DEFAULT_MAX_POINTS
                    )
                if layout is not None and fields != layout:
                    raise ExportError(
                        "Different record schemas require explicit normalization; none performed"
                    )
                layout = fields
                names = set(dtype.names)
                normal = {"normal_x", "normal_y", "normal_z"}
                if names & normal and not normal <= names:
                    raise ExportError("Incomplete normal vector")
                for field in fields:
                    name = field["name"]
                    if field["count"] != 1 or (
                        name not in {"x", "y", "z"} | normal
                        and (
                            name.endswith(("_x", "_y", "_z"))
                            or name in {"normal", "velocity", "vector", "position"}
                        )
                    ):
                        raise ExportError(
                            "Unsupported coordinate/vector field: " + name
                        )
                    if name in {"x", "y", "z"} | normal and field["type"] != "F":
                        raise ExportError(
                            "Transformed coordinates must have floating-point fields"
                        )
                total += count
                if (
                    total > DEFAULT_MAX_POINTS
                    or total * dtype.itemsize > DEFAULT_MAX_BYTES
                ):
                    raise ExportError("Merged output exceeds bounds")
                snapshots.append(
                    (source, path, snapshot, lines, len(header), dtype, count)
                )
            occupied, nonfinite = set(), 0
            merged = stage / "merged.pcd"
            with merged.open("xb") as output:
                # No sensor VIEWPOINT is valid for a multi-session materialization.
                lines = [
                    (key, raw) for key, raw in snapshots[0][3] if key != "VIEWPOINT"
                ]
                output.write(_output_header(lines, total))
                for source, path, snapshot, _, offset, dtype, count in snapshots:
                    transform = transforms[source_key(source)]
                    with snapshot.open("rb") as stream:
                        stream.seek(offset)
                        step = min(
                            chunk_points, max(1, MAX_CHUNK_BYTES // dtype.itemsize)
                        )
                        for start in range(0, count, step):
                            n = min(step, count - start)
                            records = np.frombuffer(
                                stream.read(n * dtype.itemsize), dtype=dtype
                            ).copy()
                            xyz = np.column_stack(
                                [records[k] for k in ("x", "y", "z")]
                            ).astype(float)
                            finite = np.isfinite(xyz).all(axis=1)
                            nonfinite += int((~finite).sum())
                            xyz[finite] = (
                                xyz[finite] @ transform[:3, :3].T + transform[:3, 3]
                            )
                            for axis, name in enumerate(("x", "y", "z")):
                                records[name][finite] = xyz[finite, axis]
                                if not np.isfinite(records[name][finite]).all():
                                    raise ExportError("Coordinate overflow")
                            if "normal_x" in dtype.names:
                                normals = np.column_stack(
                                    [
                                        records[k]
                                        for k in ("normal_x", "normal_y", "normal_z")
                                    ]
                                )
                                valid = np.isfinite(normals).all(axis=1)
                                normals[valid] = normals[valid] @ transform[:3, :3].T
                                for axis, name in enumerate(
                                    ("normal_x", "normal_y", "normal_z")
                                ):
                                    records[name][valid] = normals[valid, axis]
                            if surface:
                                selected = xyz[
                                    finite
                                    & (xyz[:, 2] >= surface["z_min"])
                                    & (xyz[:, 2] <= surface["z_max"])
                                ]
                                cells = np.floor(
                                    selected[:, :2] / surface["resolution"]
                                )
                                if np.any(np.abs(cells) > 10000000):
                                    raise ExportError(
                                        "Occupancy coordinate bound exceeded"
                                    )
                                occupied.update(
                                    map(tuple, cells.astype(np.int64).tolist())
                                )
                                if len(occupied) > 1000000:
                                    raise ExportError("Occupancy cell bound exceeded")
                            output.write(records.tobytes())
                output.flush()
                os.fsync(output.fileno())
            occupancy = {
                "status": "UNSUPPORTED",
                "reason": "Explicit named height surface required; no multi-floor flattening",
            }
            if surface:
                occupancy = {
                    "status": "CANDIDATE",
                    **surface,
                    "frame": "fused",
                    "origin": [0, 0],
                    "axis": "x-right/y-up",
                    "background": "UNKNOWN",
                    "free_cells": [],
                    "occupied_cells": sorted(occupied),
                    "policy": "height-band conservative occupied union; no ray/free evidence; no ground inference",
                    "annotation_policy": "Not transferred; requires frame-bound explicit transformation",
                    "operational_installed": False,
                }
            (stage / "occupancy.json").write_bytes(_canonical(occupancy))
            for source, path, *_ in snapshots:
                if _hash(path) != source["sha256"]:
                    raise ExportError("Source changed before publication")
            hashes = {
                str(p.relative_to(stage)): _hash(p)
                for p in stage.rglob("*")
                if p.is_file()
            }
            manifest = {
                "schema_version": "robot-scope.multimap-fusion.v1",
                "result_id": fingerprint[:24],
                "revision": fingerprint,
                "proposal_hash": fingerprint,
                "frame_key": {
                    "map_id": fingerprint[:24],
                    "revision": fingerprint,
                    "frame_id": "fused",
                },
                "anchor_source_key": proposal["anchor_source_key"],
                "sources": sources,
                "T_fused_source": proposal["T_fused_source"],
                "root_sources": roots,
                "pairwise_edges": proposal.get("pairwise_edges", []),
                "quality": proposal.get("quality", {}),
                "history": proposal.get("history", []),
                "manual_history": proposal.get("manual_history", []),
                "job_id": proposal.get("job_id"),
                "evidence_kind": proposal.get("evidence_kind", "SYNTHETIC"),
                "producer": "multimap_core.exporter",
                "sequence": proposal.get("sequence", 0),
                "source_epoch": proposal.get(
                    "source_epoch", proposal.get("job_id", fingerprint)
                ),
                "input_pins": proposal["input_pins"],
                "solver_version": proposal.get("solver_version"),
                "output_hashes": hashes,
                "point_count": total,
                "nonfinite_xyz_preserved": nonfinite,
                "field_policy": "XYZ transformed; normals rotated; scalar bytes preserved; unsupported vectors/schema mismatch rejected",
                "viewpoint_policy": "omitted: no common acquisition viewpoint",
                "time_policy": "source-local point time preserved; source record ranges identify epochs, never a continuous scan",
                "source_record_ranges": [],
                "losses": [],
                "deduplication": "none; all input records retained",
                "semantic_mask": None,
                "occupancy": {
                    k: v for k, v in occupancy.items() if k != "occupied_cells"
                },
                "operational_installed": False,
            }
            start = 0
            for source, _, _, _, _, _, count in snapshots:
                manifest["source_record_ranges"].append(
                    {"source_key": source_key(source), "start": start, "count": count}
                )
                start += count
            (stage / "manifest.json").write_bytes(_canonical(manifest))
            for item in stage.rglob("*"):
                if item.is_file():
                    with item.open("rb") as stream:
                        os.fsync(stream.fileno())
            for directory in (stage / "sources", stage):
                fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            os.rename(stage, destination)
            fd = os.open(root, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            return manifest
        finally:
            if stage.exists():
                shutil.rmtree(stage)
