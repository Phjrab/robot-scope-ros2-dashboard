"""Chunked full PCD materialization and immutable atomic candidate bundles.

Reuses existing binary PCD schema parser and private store I/O/locking contract.
Does not register with the product catalogue or invent a mapping session.
"""

import copy
from contextlib import nullcontext
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone

import numpy as np

from robot_dashboard.expansion_contracts import (
    ContractError,
    MapSourceDescriptor,
    canonical,
    digest,
)
from robot_dashboard.expansion_contracts.messages import ID, token, validate_transform
from robot_dashboard.pcd_editing.pcd import _read_header
from robot_dashboard.pcd_editing.store import (
    _safe_path,
    _open_regular,
    _signature,
    _digest,
    _registry_lock,
    _sync_directory,
    SourceAsset,
)
from .catalogue import Conflict, ResolvedSource, validate_dag

_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


def transform_masks(sources, transforms):
    candidates = []
    for s in sources:
        t = np.array(transforms[s.descriptor.key]).reshape(4, 4)
        for original in s.semantic_masks:
            m = copy.deepcopy(original)
            # Preserve full vertices including tilted Z; never replace by a smaller XY bbox.
            valid = (
                m.get("frame_key") == s.descriptor.key
                and isinstance(m.get("polygon"), list)
                and len(m["polygon"]) >= 3
                and m.get("z_min") is not None
                and m.get("z_max") is not None
            )
            item = {
                "source_key": s.descriptor.key,
                "original": m,
                "operational_installed": False,
                "review_required": True,
                "transformed_prism": None,
            }
            if valid or (
                m.get("frame_key") == s.descriptor.key
                and isinstance(m.get("prism_vertices"), list)
            ):
                try:
                    vertices = (
                        np.array([[*p, 1.0] for p in m["prism_vertices"]], dtype=float)
                        if "prism_vertices" in m
                        else np.array(
                            [
                                [p[0], p[1], z, 1.0]
                                for z in (m["z_min"], m["z_max"])
                                for p in m["polygon"]
                            ],
                            dtype=float,
                        )
                    )
                    if (
                        vertices.ndim != 2
                        or vertices.shape[1] != 4
                        or len(vertices) < 3
                    ):
                        raise ValueError("invalid prism")
                    if not np.all(np.isfinite(vertices)):
                        raise ValueError("nonfinite mask")
                    item["transformed_prism"] = (vertices @ t.T)[:, :3].tolist()
                    item["reason"] = (
                        "transformed 3D candidate; explicit semantic review required"
                    )
                except (TypeError, ValueError, IndexError):
                    item["reason"] = (
                        "untransformable annotation; original retained for review"
                    )
            else:
                item["reason"] = (
                    "missing frame or Z bounds; original retained for review"
                )
            candidates.append(item)
    canonical(candidates)
    return candidates


class BundleStore:
    def __init__(
        self,
        root,
        catalogue,
        *,
        max_bytes=256 * 1024**2,
        max_points=20_000_000,
        chunk_points=16384,
        max_cells=1_000_000,
        resolution=0.25,
    ):
        if (
            any(
                type(v) is not int or v <= 0
                for v in (max_bytes, max_points, chunk_points, max_cells)
            )
            or max_bytes > 256 * 1024**2
            or not 0.01 <= resolution <= 10
        ):
            raise ValueError("invalid export bounds")
        self.root, self.catalogue = _safe_path(Path(root)), catalogue
        self.max_bytes, self.max_points = max_bytes, max_points
        self.chunk_points, self.max_cells, self.resolution = (
            min(chunk_points, 65536),
            min(max_cells, 1_000_000),
            resolution,
        )

    def _merge(self, stage, sources, transforms, cancel):
        total, layout, source_metadata = 0, None, []
        for s in sources:
            with _open_regular(s.asset.path, self.max_bytes) as stream:
                header_lines, _, dtype, points, fields = _read_header(
                    stream, os.fstat(stream.fileno()).st_size, self.max_points
                )
            original = {
                key: raw.decode("ascii").strip().split()[1:]
                for key, raw in header_lines
                if key in {"VIEWPOINT", "WIDTH", "HEIGHT", "POINTS"}
            }
            source_metadata.append(
                {"source_key": s.descriptor.key, "original_header": original}
            )
            if (
                fields != s.descriptor.point_schema
                or points != s.descriptor.point_count
            ):
                raise Conflict("PCD schema/count differs from pinned descriptor")
            if layout is not None and layout != fields:
                raise ContractError(
                    "heterogeneous schemas rejected; no implicit field loss"
                )
            layout = fields
            total += points
        if total > self.max_points:
            raise ContractError("merged point limit exceeded")
        for names in (("x", "y", "z"), ("normal_x", "normal_y", "normal_z")):
            present = [n in dtype.names for n in names]
            if any(present) and not all(present):
                raise ContractError("partial vector schema rejected")
            if any(present) and any(
                dtype[n].kind != "f" or dtype[n].shape for n in names
            ):
                raise ContractError("XYZ/normals require scalar float fields")
        # Unknown multi-count/vector fields need an explicit future policy.
        if any(f["count"] != 1 for f in layout):
            raise ContractError(
                "multi-count fields require an explicit normalization policy"
            )
        lines = [
            "# robot-scope merged candidate; VIEWPOINT is synthetic, not acquisition",
            "VERSION 0.7",
            "FIELDS " + " ".join(f["name"] for f in layout),
            "SIZE " + " ".join(str(f["size"]) for f in layout),
            "TYPE " + " ".join(f["type"] for f in layout),
            "COUNT " + " ".join(str(f["count"]) for f in layout),
            f"WIDTH {total}",
            "HEIGHT 1",
            "VIEWPOINT 0 0 0 1 0 0 0",
            f"POINTS {total}",
            "DATA binary",
        ]
        header = ("\n".join(lines) + "\n").encode()
        if len(header) + total * dtype.itemsize > self.max_bytes:
            raise ContractError("merged byte limit exceeded")
        occupied, max_side = set(), int(self.max_cells**0.5)
        lower, upper = None, None
        with (stage / "map.pcd").open("xb") as out:
            out.write(header)
            for s in sources:
                t = np.array(validate_transform(transforms[s.descriptor.key])).reshape(
                    4, 4
                )
                with _open_regular(s.asset.path, self.max_bytes) as stream:
                    before = _signature(os.fstat(stream.fileno()))
                    _, raw_header, dtype, points, _ = _read_header(
                        stream, before[2], self.max_points
                    )
                    source_hash = hashlib.sha256(raw_header)
                    chunk = min(
                        self.chunk_points, max(1, 1024 * 1024 // dtype.itemsize)
                    )
                    for start in range(0, points, chunk):
                        if cancel.is_set():
                            raise Conflict("export canceled")
                        count = min(chunk, points - start)
                        raw = stream.read(count * dtype.itemsize)
                        if len(raw) != count * dtype.itemsize:
                            raise Conflict("truncated full source")
                        source_hash.update(raw)
                        records = np.frombuffer(raw, dtype=dtype).copy()
                        xyz = np.column_stack([records[n] for n in ("x", "y", "z")])
                        if not np.all(np.isfinite(xyz)):
                            raise ContractError(
                                "nonfinite XYZ rejected for materialization"
                            )
                        xyz = xyz @ t[:3, :3].T + t[:3, 3]
                        for i, n in enumerate(("x", "y", "z")):
                            records[n] = xyz[:, i]
                        if "normal_x" in dtype.names:
                            normals = (
                                np.column_stack(
                                    [
                                        records[n]
                                        for n in ("normal_x", "normal_y", "normal_z")
                                    ]
                                )
                                @ t[:3, :3].T
                            )
                            for i, n in enumerate(("normal_x", "normal_y", "normal_z")):
                                records[n] = normals[:, i]
                        if any(
                            not np.all(np.isfinite(records[n])) for n in ("x", "y", "z")
                        ):
                            raise ContractError(
                                "transformed coordinates overflow output dtype"
                            )
                        # Candidate marking only. No rays/trajectory => no observed free cells.
                        cells = np.floor(xyz[:, :2] / self.resolution)
                        if np.any(np.abs(cells) > 2**31):
                            raise ContractError("occupancy extent exceeds bound")
                        for xy in cells.astype(np.int64):
                            c = (int(xy[0]), int(xy[1]))
                            occupied.add(c)
                            lower = (
                                c
                                if lower is None
                                else (min(lower[0], c[0]), min(lower[1], c[1]))
                            )
                            upper = (
                                c
                                if upper is None
                                else (max(upper[0], c[0]), max(upper[1], c[1]))
                            )
                        if (
                            len(occupied) > self.max_cells
                            or (upper[0] - lower[0] + 1) * (upper[1] - lower[1] + 1)
                            > self.max_cells
                            or max(upper[0] - lower[0], upper[1] - lower[1])
                            > max_side * 10
                        ):
                            raise ContractError("occupancy grid exceeds bound")
                        out.write(records.tobytes())
                    if (
                        stream.read(1)
                        or before != _signature(os.fstat(stream.fileno()))
                        or source_hash.hexdigest() != s.descriptor.sha256
                    ):
                        raise Conflict("full source changed during export")
            out.flush()
            os.fsync(out.fileno())
        width, height = upper[0] - lower[0] + 1, upper[1] - lower[1] + 1
        pixels = bytearray([205]) * (width * height)
        for x, y in occupied:
            pixels[(height - 1 - (y - lower[1])) * width + (x - lower[0])] = 0
        (stage / "occupancy.pgm").write_bytes(
            f"P5\n{width} {height}\n255\n".encode() + pixels
        )
        origin = [lower[0] * self.resolution, lower[1] * self.resolution, 0.0]
        yaml = f"image: occupancy.pgm\nresolution: {self.resolution}\norigin: {origin}\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n"
        (stage / "occupancy.yaml").write_text(yaml)
        return {
            "point_count": total,
            "point_schema": layout,
            "field_policy": "XYZ SE3; normal_xyz rotation; other scalar fields preserved; heterogeneous/multicount rejected",
            "viewpoint_policy": "synthetic identity; original source VIEWPOINT retained separately",
            "source_pcd_metadata": source_metadata,
            "occupancy": {
                "resolution": self.resolution,
                "width": width,
                "height": height,
                "origin": origin,
                "default": "UNKNOWN",
                "free_evidence": None,
                "policy": "point marking only; no free reconstruction",
            },
        }

    def save(
        self, request, proposal, name, cancel, review, *, publication_guard=nullcontext
    ):
        token(name, "export name", _NAME)
        sources = self.catalogue.pinned(request)
        graph = validate_dag(sources)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        _safe_path(self.root)
        with _registry_lock(self.root, fcntl.LOCK_EX, create=True):
            pass
        stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=self.root))
        published = None
        try:
            details = self._merge(stage, sources, proposal.T_fused_source, cancel)
            result_id = uuid.uuid4().hex[:24]
            hashes = {
                f: _digest(stage / f, self.max_bytes)
                for f in ("map.pcd", "occupancy.pgm", "occupancy.yaml")
            }
            manifest = {
                "schema": "robot-scope.multimap-fusion.v1",
                "id": result_id,
                "name": name,
                "frame_id": f"fused_{result_id}",
                "sources": request.sources,
                "anchor_source_key": request.anchor_source_key,
                "T_fused_source": proposal.T_fused_source,
                "input_pins": request.source_pins,
                "pairwise_edges": proposal.pairwise_edges,
                "quality": proposal.quality,
                "review": review,
                "accepted_edges": [
                    e for e in proposal.pairwise_edges if e.get("accepted") is True
                ],
                "rejected_edges": [
                    e for e in proposal.pairwise_edges if e.get("accepted") is False
                ],
                "request_fingerprint": request.fingerprint,
                "options_hash": digest(request.options),
                "initial_guesses": request.initial_guesses,
                "correspondences": request.correspondences,
                "mode": request.mode,
                "warnings": proposal.warnings,
                "job_id": proposal.job_id,
                "proposal_revision": proposal.proposal_revision,
                "solver_version": proposal.solver_version,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "output_hashes": hashes,
                "provenance_dag": graph,
                "operational_installed": False,
                "semantic_masks": transform_masks(sources, proposal.T_fused_source),
                **details,
                "legacy_family": {
                    "status": "DEFERRED",
                    "reason": "map-family.v1 requires real mapping_session_id; no fictitious session",
                    "projection": "planar_xy_identity_after_materialization",
                },
            }
            manifest["revision"] = digest(manifest)
            (stage / "manifest.json").write_bytes(canonical(manifest))
            for file in stage.iterdir():
                with file.open("rb") as stream:
                    os.fsync(stream.fileno())
                os.chmod(file, 0o400)
            _sync_directory(stage)
            self.catalogue.pinned(
                request
            )  # Last pin/hash fence before atomic publication.
            with _registry_lock(self.root, fcntl.LOCK_EX), publication_guard():
                if cancel.is_set():
                    raise Conflict("export canceled before publication")
                for directory in self.root.iterdir():
                    if (
                        ID.fullmatch(directory.name)
                        and self._read(directory)["name"] == name
                    ):
                        raise Conflict("immutable export name already exists")
                destination = self.root / result_id
                if destination.exists():
                    raise Conflict("output ID exists")
                os.rename(stage, destination)
                published = destination
                try:
                    _sync_directory(self.root)
                except BaseException:
                    shutil.rmtree(destination)
                    published = None
                    raise
            return copy.deepcopy(manifest)
        except BaseException:
            if published is not None:
                shutil.rmtree(published)
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)

    def _read(self, directory):
        with _open_regular(directory / "manifest.json", 128 * 1024) as stream:
            m = json.loads(stream.read())
        if (
            m.get("schema") != "robot-scope.multimap-fusion.v1"
            or m.get("id") != directory.name
            or m.get("operational_installed") is not False
            or m.get("revision")
            != digest({k: v for k, v in m.items() if k != "revision"})
        ):
            raise ContractError("invalid fusion manifest")
        if set(m["output_hashes"]) != {"map.pcd", "occupancy.pgm", "occupancy.yaml"}:
            raise ContractError("unexpected output assets")
        for filename, sha in m["output_hashes"].items():
            if _digest(directory / filename, self.max_bytes) != sha:
                raise Conflict("output checksum mismatch")
        return m

    def get(self, result_id):
        token(result_id, "export ID", ID)
        _safe_path(self.root / result_id)
        with _registry_lock(self.root, fcntl.LOCK_SH):
            return self._read(self.root / result_id)

    def reload(self, result_id):
        m = self.get(result_id)
        d = MapSourceDescriptor(
            schema_version="0.1",
            evidence_kind=m["sources"][0]["evidence_kind"],
            producer="c1-bundle",
            sequence=0,
            source_epoch=m["id"],
            map_id=m["id"],
            revision=m["revision"],
            sha256=m["output_hashes"]["map.pcd"],
            frame_id=m["frame_id"],
            units="m",
            asset_role="full_source",
            mapping_session_id=None,
            gravity_or_plane=None,
            point_count=m["point_count"],
            point_schema=m["point_schema"],
            acquisition={"origin": "materialized fusion", "job_id": m["job_id"]},
        )
        graph = {
            **m["provenance_dag"],
            d.key: [MapSourceDescriptor.from_dict(s).key for s in m["sources"]],
        }
        masks = tuple(
            {
                "frame_key": d.key,
                "prism_vertices": item["transformed_prism"],
                "prior_candidate": item,
                "review_required": True,
            }
            for item in m["semantic_masks"]
        )
        return ResolvedSource(
            d,
            SourceAsset(
                d.map_id, d.revision, self.root / result_id / "map.pcd", d.frame_id
            ),
            graph,
            masks,
        )
