"""Bounded offline map-to-map registration. No runtime or device adapters."""

from __future__ import annotations
import copy
import hashlib
import itertools
import time
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from scipy.optimize import least_squares
from robot_dashboard.pcd_editing.pcd import (
    _read_header,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_POINTS,
)
from robot_dashboard.relocalization.experimental_se3 import (
    validate_transform,
    transform_points,
    inverse,
    _rigid_fit,
)

VERSION = "d1-rigid-0.1"
_CACHE = {}  # bounded process-local working-cloud cache, never full source
_FEATURE_CACHE = {}


def source_key(d):
    return "@".join(str(d[k]) for k in ("map_id", "revision", "frame_id"))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while b := f.read(1024 * 1024):
            h.update(b)
    return h.hexdigest()


def working_cloud(d, resolver, voxel, limit):
    if d.get("units") != "m" or d.get("asset_role") != "full_source":
        raise ValueError("full_source metres required")
    path = Path(resolver(d))
    if path.stat().st_size > DEFAULT_MAX_BYTES or digest(path) != d["sha256"]:
        raise ValueError("source size/hash changed")
    key = (d["sha256"], voxel, limit)
    if key in _CACHE:
        return _CACHE[key].copy()
    with path.open("rb") as f:
        _, _, dtype, count, _ = _read_header(f, path.stat().st_size, DEFAULT_MAX_POINTS)
        # Bounded reservoir-like deterministic stride; voxel representatives follow.
        stride = max(1, int(np.ceil(count / (limit * 8))))
        blocks = []
        for start in range(0, count, 16384):
            records = np.frombuffer(
                f.read(min(16384, count - start) * dtype.itemsize), dtype=dtype
            )
            records = records[(-start) % stride :: stride]
            blocks.append(np.column_stack([records[k] for k in ("x", "y", "z")]))
        p = np.concatenate(blocks).astype(float)
    p = p[np.isfinite(p).all(axis=1)]
    if len(p) < 12:
        raise ValueError("insufficient finite points")
    _, indices = np.unique(np.floor(p / voxel), axis=0, return_index=True)
    p = p[np.sort(indices)]
    p = p[np.linspace(0, len(p) - 1, min(limit, len(p)), dtype=int)]
    if digest(path) != d["sha256"]:
        raise ValueError("source changed during read")
    if len(_CACHE) >= 8:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = p.copy()
    return p


def normals(p):
    key = hashlib.sha256(p.tobytes()).hexdigest()
    if key in _FEATURE_CACHE:
        return _FEATURE_CACHE[key][0]
    _, ids = cKDTree(p).query(p, k=min(12, len(p)))
    q = p[ids]
    q -= q.mean(axis=1, keepdims=True)
    _, v = np.linalg.eigh(np.einsum("nki,nkj->nij", q, q))
    distances = cKDTree(p).query(p, k=9)[0][:, 1:]
    if len(_FEATURE_CACHE) >= 16:
        _FEATURE_CACHE.pop(next(iter(_FEATURE_CACHE)))
    _FEATURE_CACHE[key] = (v[:, :, 0], distances)
    return v[:, :, 0]


def metrics(a, b, T, resolution):
    moved = transform_points(T, b)
    da, _ = cKDTree(moved).query(a)
    db, _ = cKDTree(a).query(moved)
    gate = 3 * resolution
    ma, mb = da < gate, db < gate
    eig = np.linalg.eigvalsh(np.cov(moved[mb].T)) if mb.sum() >= 4 else np.zeros(3)
    ns = normals(a)
    normal_eig = np.linalg.eigvalsh(ns.T @ ns / len(ns))
    return dict(
        overlap_target=float(ma.mean()),
        overlap_source=float(mb.mean()),
        rmse_m=float(np.sqrt(np.mean(db[mb] ** 2))) if mb.any() else None,
        distance_p50_m=float(np.median(db)),
        distance_p95_m=float(np.percentile(db, 95)),
        inliers=int(mb.sum()),
        spatial_eigenvalues=eig.tolist(),
        geometry_ratio=float(eig[0] / max(eig[-1], 1e-12)),
        normal_eigenvalues=normal_eig.tolist(),
        observability_condition=float(eig[-1] / max(eig[0], 1e-12)),
        residual_samples=[
            {"xyz": p.tolist(), "distance_m": float(d)}
            for p, d in zip(
                moved[:: max(1, len(moved) // 64)], db[:: max(1, len(db) // 64)]
            )
        ],
    )


def refine(a, b, seed, resolution, canceled):
    T = validate_transform(seed)
    tree = cKDTree(a)
    for gate in (12 * resolution, 6 * resolution, 3 * resolution):
        for _ in range(30):
            if canceled():
                raise InterruptedError()
            p = transform_points(T, b)
            distances, ids = tree.query(p)
            mask = distances < gate
            if mask.sum() < 12:
                break
            # Huber-like robust weights with the same tested rigid-fit primitive.
            weights = np.minimum(1, resolution / np.maximum(distances[mask], 1e-12))
            delta = _rigid_fit(p[mask], a[ids[mask]], weights)
            T = validate_transform(delta @ T)
            if np.linalg.norm(delta - np.eye(4)) < 1e-7:
                break
    return T


def residual_rank(value):
    """Zero is exact, None is missing, malformed residuals fail closed.

    A tuple separates missing data from any finite valid metric. This ranking
    never alters overlap priority. Transform values break exact ties in both
    candidate stages, independent of candidate enumeration order.
    """
    if value is None:
        return (1, 0.0)
    value = float(value)
    if not np.isfinite(value) or value < 0:
        raise ValueError("residual must be finite and nonnegative or None")
    return (0, value)


def _transform_tie(transform):
    return tuple(np.asarray(transform).ravel())


def coarse(a, b):
    """Fixed CPU baseline: local distance signatures + seeded deterministic RANSAC.

    Rigid invariant signatures propose, never certify, correspondences. PCA
    axis candidates supplement full overlap; ambiguous symmetries survive scoring.
    """
    out = []

    def basis(p):
        _, v = np.linalg.eigh(np.cov(p.T))
        return v

    va, vb = basis(a), basis(b)
    for signs in itertools.product((-1, 1), repeat=3):
        R = va @ np.diag(signs) @ vb.T
        if np.linalg.det(R) > 0:
            T = np.eye(4)
            T[:3, :3] = R
            T[:3, 3] = a.mean(0) - R @ b.mean(0)
            out.append(T)
    normals(a)
    normals(b)
    fa = _FEATURE_CACHE[hashlib.sha256(a.tobytes()).hexdigest()][1]
    fb = _FEATURE_CACHE[hashlib.sha256(b.tobytes()).hexdigest()][1]
    _, match = cKDTree(fa).query(fb)
    rng = np.random.default_rng(1234)
    tree = cKDTree(a)
    scored = []
    for _ in range(128):
        ids = rng.choice(len(b), 3, replace=False)
        if np.linalg.matrix_rank(b[ids] - b[ids].mean(0)) < 2:
            continue
        T = _rigid_fit(b[ids], a[match[ids]])
        d, _ = tree.query(transform_points(T, b))
        scored.append((np.quantile(d, 0.5), T))
    out.extend(
        t
        for _, t in sorted(
            scored, key=lambda x: (residual_rank(x[0]), _transform_tie(x[1]))
        )[:6]
    )
    return out


def pair(a, b, seeds, resolution, canceled):
    candidates = []
    for seed in seeds or coarse(a, b):
        T = refine(a, b, seed, resolution, canceled)
        m = metrics(a, b, T, resolution)
        if not any(np.linalg.norm(T - t) < resolution for t, _ in candidates):
            candidates.append((T, m))
    candidates.sort(
        key=lambda x: (
            -min(x[1]["overlap_target"], x[1]["overlap_source"]),
            residual_rank(x[1]["rmse_m"]),
            _transform_tie(x[0]),
        )
    )
    T, m = candidates[0]
    accepted = (
        min(m["overlap_target"], m["overlap_source"]) >= 0.35
        and m["inliers"] >= 12
        and m["geometry_ratio"] > 0.002
        and m["rmse_m"] is not None
        and m["rmse_m"] < 1.5 * resolution
    )
    alternatives = [
        {"T": t.tolist(), "metrics": q}
        for t, q in candidates[1:]
        if min(q["overlap_target"], q["overlap_source"])
        >= min(m["overlap_target"], m["overlap_source"]) - 0.03
        and q["rmse_m"] is not None
        and q["rmse_m"]
        < max(
            resolution, (m["rmse_m"] if m["rmse_m"] is not None else float("inf")) * 1.2
        )
    ]
    return T, m, accepted and not alternatives, alternatives


def optimize_graph(keys, edges, anchor, resolution):
    """Maximum-quality spanning initialization; uncertain loop edges are never odometry."""
    poses = {anchor: np.eye(4)}
    accepted = []
    rejected = []
    remaining = sorted(
        edges,
        key=lambda e: -min(
            e["metrics"]["overlap_source"], e["metrics"]["overlap_target"]
        ),
    )
    while True:
        added = False
        for e in remaining[:]:
            a, b = e["target"], e["source"]
            T = np.array(e["T"])
            if (a in poses) != (b in poses):
                poses[b if a in poses else a] = (
                    poses[a] @ T if a in poses else poses[b] @ inverse(T)
                )
                accepted.append(e)
                remaining.remove(e)
                added = True
        if not added:
            break
    for e in remaining:
        if e["target"] not in poses or e["source"] not in poses:
            continue
        delta = inverse(poses[e["target"]] @ e["T"]) @ poses[e["source"]]
        error = float(np.linalg.norm(delta[:3, 3]))
        angle = float(np.linalg.norm(Rotation.from_matrix(delta[:3, :3]).as_rotvec()))
        e["loop_translation_m"] = error
        e["loop_rotation_rad"] = angle
        if error > 6 * resolution or angle > 0.15:
            e["reason"] = "LOOP_INCONSISTENT"
            rejected.append(e)
        else:
            accepted.append(e)
    moving = [k for k in poses if k != anchor]

    def pack(T):
        return np.r_[T[:3, 3], Rotation.from_matrix(T[:3, :3]).as_rotvec()]

    def unpack(x):
        T = np.eye(4)
        T[:3, 3] = x[:3]
        T[:3, :3] = Rotation.from_rotvec(x[3:]).as_matrix()
        return T

    def residual(x):
        pp = {
            anchor: np.eye(4),
            **{k: unpack(x[i * 6 : i * 6 + 6]) for i, k in enumerate(moving)},
        }
        return np.concatenate(
            [
                pack(inverse(pp[e["target"]] @ e["T"]) @ pp[e["source"]])
                for e in accepted
            ]
        )

    if moving:
        result = least_squares(
            residual,
            np.concatenate([pack(poses[k]) for k in moving]),
            loss="soft_l1",
            f_scale=resolution,
            max_nfev=50,
        )
        poses.update(
            {k: unpack(result.x[i * 6 : i * 6 + 6]) for i, k in enumerate(moving)}
        )
    return poses, accepted, rejected


def solve(request, resolver, progress=None, cancel_token=None):
    started = time.monotonic()
    req = copy.deepcopy(request)

    def canceled():
        return bool(cancel_token and cancel_token.is_set())

    sources = req["sources"]
    keys = [source_key(s) for s in sources]
    if not 2 <= len(sources) <= 8 or len(set(keys)) != len(keys):
        raise ValueError("2..8 unique source keys required")
    anchor = req["anchor_source_key"]
    if anchor not in keys:
        raise ValueError("anchor missing")
    options = req.get("options", {})
    resolution = float(options.get("resolution_m", 0.05))
    limit = int(options.get("max_working_points", 1500))
    if not 0.005 <= resolution <= 0.5 or not 100 <= limit <= 4000:
        raise ValueError("algorithm bounds exceeded")
    if req.get("mode", "auto") not in ("auto", "seeded", "manual_review"):
        raise ValueError("unknown mode")
    pins = req.get("source_pins", sources)
    if pins != sources:
        raise ValueError("input pin/revision mismatch")
    proposal = dict(
        schema_version="0.1",
        evidence_kind=req.get("evidence_kind", "SYNTHETIC"),
        producer=VERSION,
        sequence=req.get("sequence", 0),
        source_epoch=req.get("source_epoch", "offline"),
        job_id=req["request_id"],
        proposal_revision=req.get("proposal_revision", 1),
        anchor_source_key=anchor,
        sources=sources,
        input_pins=pins,
        solver_version=VERSION,
        T_fused_source=[],
        pairwise_edges=[],
        ambiguous_candidates=[],
        warnings=["INDEPENDENT_ACCURACY_UNKNOWN", "RIGID_ONLY_NO_DRIFT_CORRECTION"],
        quality={"covariance": None, "information_convention": "unavailable"},
        manual_history=req.get("initial_guesses", []),
    )
    if proposal["evidence_kind"] not in ("SYNTHETIC", "REPLAY"):
        raise ValueError("offline evidence required")
    try:
        if canceled():
            raise InterruptedError()
        clouds = {
            k: working_cloud(s, resolver, resolution, limit)
            for k, s in zip(keys, sources)
        }
        good = []
        for a, b in itertools.combinations(keys, 2):
            if canceled():
                raise InterruptedError()
            seeds = [
                validate_transform(g["T"])
                for g in req.get("initial_guesses", [])
                if g["target"] == a and g["source"] == b
            ]
            seeds += [
                inverse(g["T"])
                for g in req.get("initial_guesses", [])
                if g["target"] == b and g["source"] == a
            ]
            for c in req.get("correspondences", []):
                if c["target"] == a and c["source"] == b:
                    x, y = np.array(c["source_points"]), np.array(c["target_points"])
                    if (
                        x.shape != y.shape
                        or len(x) < 3
                        or np.linalg.matrix_rank(x - x.mean(0)) < 2
                        or np.linalg.matrix_rank(y - y.mean(0)) < 2
                    ):
                        raise ValueError(
                            "distributed noncollinear correspondences required"
                        )
                    seeds.append(_rigid_fit(x, y))
            T, m, ok, alternatives = pair(
                clouds[a], clouds[b], seeds, resolution, canceled
            )
            edge = dict(
                target=a,
                source=b,
                T=T.tolist(),
                metrics=m,
                accepted=ok,
                seeded=bool(seeds),
                reason="CANDIDATE" if ok else "AMBIGUOUS_OR_LOW_OVERLAP_OR_DEGENERATE",
            )
            proposal["pairwise_edges"].append(edge)
            if ok:
                good.append(edge)
            if alternatives:
                proposal["ambiguous_candidates"].append(
                    {"target": a, "source": b, "alternatives": alternatives}
                )
            if progress:
                progress({"completed_pairs": len(proposal["pairwise_edges"])})
        poses, accepted, rejected = optimize_graph(keys, good, anchor, resolution)
        for e in rejected:
            e["accepted"] = False
        # Components use only retained accepted constraints, including disconnected subgraphs.
        unseen = set(keys)
        components = []
        while unseen:
            component = {min(unseen)}
            while True:
                more = {
                    v
                    for e in good
                    if e not in rejected and ({e["source"], e["target"]} & component)
                    for v in (e["source"], e["target"])
                }
                if more <= component:
                    break
                component |= more
            unseen -= component
            components.append(sorted(component))
        proposal["connected_components"] = components
        proposal["T_fused_source"] = [
            {"source_key": k, "T": v.tolist()} for k, v in poses.items()
        ]
        proposal["quality"]["source_previews"] = [
            {
                "source_key": key,
                "color_index": keys.index(key),
                "asset_role": "sampled_preview",
                "points": transform_points(
                    T, clouds[key][:: max(1, len(clouds[key]) // 64)]
                ).tolist(),
            }
            for key, T in poses.items()
        ]
        proposal["status"] = (
            "SOLVED_CANDIDATE"
            if len(poses) == len(keys)
            else ("NEEDS_PRIOR" if proposal["ambiguous_candidates"] else "DISCONNECTED")
        )
        if req.get("mode") == "manual_review":
            proposal["status"] = "NEEDS_PRIOR"
    except InterruptedError:
        proposal.update(
            status="CANCELED",
            T_fused_source=[],
            connected_components=[[k] for k in keys],
        )
    proposal["elapsed_ms"] = (time.monotonic() - started) * 1000
    return proposal
