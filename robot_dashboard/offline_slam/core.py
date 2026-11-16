"""Bounded 3D keyframe registration and anchored pose-graph reconstruction.

T_parent_body maps body-local points into the parent frame. An edge Z_ij
maps j-local points to i-local coordinates. Residuals use translation and
SO(3) log of inv(Z_ij) @ inv(T_i) @ T_j (metres, then radians).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from robot_dashboard.relocalization.experimental_se3 import _rigid_fit, inverse

SCHEMA = "robot-scope.offline-keyframes/v1"
MAX_BYTES = 64 * 1024 * 1024
MAX_FRAMES = 400
MAX_POINTS = 2000


def encoded(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def transform(value):
    t = np.asarray(value, dtype=float)
    if (
        t.shape != (4, 4)
        or not np.isfinite(t).all()
        or not np.allclose(t[3], [0, 0, 0, 1], atol=1e-8)
        or not np.allclose(t[:3, :3].T @ t[:3, :3], np.eye(3), atol=1e-5)
        or not np.isclose(np.linalg.det(t[:3, :3]), 1, atol=1e-5)
        or np.max(np.abs(t[:3, 3])) > 10000
    ):
        raise ValueError("INVALID_SE3")
    return t


def project(points, t):
    return np.asarray(points) @ t[:3, :3].T + t[:3, 3]


def vector(t):
    return np.r_[t[:3, 3], Rotation.from_matrix(t[:3, :3]).as_rotvec()]


def pose(x):
    t = np.eye(4)
    t[:3, :3] = Rotation.from_rotvec(x[3:]).as_matrix()
    t[:3, 3] = x[:3]
    return t


def validate_session(data):
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("SESSION_SCHEMA")
    if not isinstance(data.get("provenance"), str) or data["provenance"] not in {
        "recorded_fastlio",
        "synthetic_fixture",
    }:
        raise ValueError("PROVENANCE_REQUIRED")
    try:
        origin = np.asarray(data.get("sensor_origin_body"), dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("SENSOR_ORIGIN_REQUIRED") from exc
    if (
        origin.shape != (3,)
        or not np.isfinite(origin).all()
        or np.max(np.abs(origin)) > 5
    ):
        raise ValueError("SENSOR_ORIGIN_REQUIRED")
    for key in ("session_id", "parent_frame", "local_frame", "calibration_id"):
        if not isinstance(data.get(key), str) or not 1 <= len(data[key]) <= 128:
            raise ValueError("SESSION_METADATA_REQUIRED")
    frames = data.get("keyframes")
    if not isinstance(frames, list) or not 3 <= len(frames) <= MAX_FRAMES:
        raise ValueError("KEYFRAME_COUNT")
    last = -1
    for frame in frames:
        if (
            not isinstance(frame, dict)
            or not {"stamp_ns", "T_parent_body", "points"} <= frame.keys()
        ):
            raise ValueError("KEYFRAME_FIELDS_REQUIRED")
        stamp = frame.get("stamp_ns")
        if type(stamp) is not int or not last < stamp < 2**63:
            raise ValueError("NONMONOTONIC_SOURCE_TIME")
        last = stamp
        try:
            transform(frame["T_parent_body"])
            points = np.asarray(frame["points"], dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError("INVALID_KEYFRAME_GEOMETRY") from exc
        if (
            points.ndim != 2
            or points.shape[1] != 3
            or not 30 <= len(points) <= MAX_POINTS
            or not np.isfinite(points).all()
            or np.max(np.abs(points)) > 500
        ):
            raise ValueError("INVALID_LOCAL_POINTS")
    return data


@dataclass(frozen=True)
class Settings:
    search_radius: float = 3.0
    min_separation: int = 15
    correspondence: float = 0.6
    max_rmse: float = 0.12
    min_overlap: float = 0.55
    odom_translation_sigma: float = 0.08
    odom_rotation_sigma: float = 0.04
    loop_translation_sigma: float = 0.03
    loop_rotation_sigma: float = 0.02
    robust_scale: float = 2.0
    resolution: float = 0.1
    min_height: float = 0.15
    max_height: float = 1.8

    def validate(self):
        bounds = {
            "search_radius": (0.2, 10),
            "min_separation": (3, 399),
            "correspondence": (0.05, 2),
            "max_rmse": (0.005, 0.5),
            "min_overlap": (0.3, 1),
            "robust_scale": (0.1, 10),
            "resolution": (0.05, 0.5),
            "min_height": (-5, 5),
            "max_height": (-5, 5),
        }
        for key, val in asdict(self).items():
            lo, hi = bounds.get(key, (0.001, 1))
            if (
                type(val) not in (float, int)
                or not np.isfinite(val)
                or not lo <= val <= hi
            ):
                raise ValueError("INVALID_SETTING_" + key)
        if type(self.min_separation) is not int or self.max_height <= self.min_height:
            raise ValueError("INVALID_SETTINGS")
        return self


def fit_registration(source, target, seed, settings):
    """Fit a local hypothesis, including rejected candidates for offline diagnosis.

    Call register() when an accepted graph measurement is required. A returned
    matrix here is only an optimizer candidate; all gate failures remain explicit.
    """
    tree = cKDTree(target)
    current = seed.copy()
    for _ in range(40):
        moved = project(source, current)
        distances, indices = tree.query(moved)
        mask = distances < settings.correspondence
        if mask.sum() < 30:
            return None, {
                "reason": "TOO_FEW_CORRESPONDENCES",
                "failures": ["TOO_FEW_CORRESPONDENCES"],
            }
        selected = np.flatnonzero(mask)
        selected = selected[
            np.argsort(distances[selected])[: max(30, int(len(selected) * 0.85))]
        ]
        a, b = moved[selected], target[indices[selected]]
        ac, bc = a.mean(0), b.mean(0)
        singular = np.linalg.svd((a - ac).T @ (b - bc), compute_uv=False)
        # Refuse line-like/point-like geometry. A plane can constrain point-to-point ICP.
        if singular[1] < 1e-4 or singular[1] / max(singular[0], 1e-12) < 0.01:
            return None, {
                "reason": "DEGENERATE_GEOMETRY",
                "failures": ["DEGENERATE_GEOMETRY"],
            }
        step = _rigid_fit(a, b)
        current = step @ current
        if np.linalg.norm(vector(step)) < 1e-6:
            break
    moved = project(source, current)
    distances, indices = tree.query(moved)
    mask = distances < settings.correspondence
    reverse = cKDTree(moved).query(target)[0]
    forward_overlap = float(mask.mean())
    reverse_overlap = float((reverse < settings.correspondence).mean())
    overlap = min(forward_overlap, reverse_overlap)
    rmse = float(np.sqrt(np.mean(distances[mask] ** 2))) if mask.any() else 1e9
    counts = np.unique(indices[mask], return_counts=True)[1]
    unique = len(counts) / max(1, int(mask.sum()))
    shift = vector(inverse(seed) @ current)
    failures = []
    if overlap < settings.min_overlap:
        failures.append("LOW_OVERLAP")
    if unique < 0.35:
        failures.append("MANY_TO_ONE_CORRESPONDENCES")
    if rmse > settings.max_rmse:
        failures.append("HIGH_RESIDUAL")
    if (
        np.linalg.norm(shift[:3]) > settings.search_radius
        or np.linalg.norm(shift[3:]) > 0.8
    ):
        failures.append("EXCESSIVE_CORRECTION")
    return current, dict(
        reason=failures[0] if failures else "ACCEPTED",
        failures=failures,
        overlap=overlap,
        forward_overlap=forward_overlap,
        reverse_overlap=reverse_overlap,
        rmse_m=rmse,
        unique_ratio=unique,
        inlier_count=int(mask.sum()),
        unique_target_count=len(counts),
        max_target_multiplicity=int(counts.max()) if len(counts) else 0,
        correction_translation_m=float(np.linalg.norm(shift[:3])),
        correction_rotation_rad=float(np.linalg.norm(shift[3:])),
    )


def register(source, target, seed, settings):
    """Return only a candidate that passed the unchanged graph-edge gates."""
    candidate, metrics = fit_registration(source, target, seed, settings)
    return (candidate if metrics["reason"] == "ACCEPTED" else None), metrics


def optimize(data, settings):
    validate_session(data)
    settings.validate()
    frames = data["keyframes"]
    original = np.array([transform(f["T_parent_body"]) for f in frames])
    clouds = [np.asarray(f["points"]) for f in frames]
    edges, candidates = [], []
    for j in range(1, len(frames)):
        edges.append((j - 1, j, inverse(original[j - 1]) @ original[j], "odometry"))
    # At most three spatial candidates per keyframe, and one accepted loop per keyframe.
    for j in range(settings.min_separation, len(frames)):
        distances = np.linalg.norm(
            original[: j - settings.min_separation + 1, :3, 3] - original[j, :3, 3],
            axis=1,
        )
        for i in np.argsort(distances)[:3]:
            i = int(i)
            if distances[i] > settings.search_radius:
                continue
            measurement, metrics = register(
                clouds[j], clouds[i], inverse(original[i]) @ original[j], settings
            )
            candidates.append(dict(i=i, j=j, **metrics))
            if measurement is not None:
                edges.append((i, j, measurement, "loop"))
                break
    if not any(e[3] == "loop" for e in edges):
        return dict(
            state="NO_LOOP", candidates=candidates, source_revision=digest(data)
        )
    weights = [
        np.diag(
            1
            / np.array(
                (
                    [settings.loop_translation_sigma] * 3
                    + [settings.loop_rotation_sigma] * 3
                )
                if kind == "loop"
                else (
                    [settings.odom_translation_sigma] * 3
                    + [settings.odom_rotation_sigma] * 3
                )
            )
        )
        for _, _, _, kind in edges
    ]

    def decode(x):
        return np.array([original[0], *[pose(row) for row in x.reshape(-1, 6)]])

    def residual(x):
        poses = decode(x)
        return np.concatenate(
            [
                w @ vector(inverse(z) @ inverse(poses[i]) @ poses[j])
                for (i, j, z, _), w in zip(edges, weights)
            ]
        )

    sparsity = lil_matrix((6 * len(edges), 6 * (len(frames) - 1)), dtype=int)
    for k, (i, j, _, _) in enumerate(edges):
        for n in (i, j):
            if n:
                sparsity[k * 6 : k * 6 + 6, (n - 1) * 6 : n * 6] = 1
    x0 = np.concatenate([vector(t) for t in original[1:]])
    result = least_squares(
        residual,
        x0,
        jac_sparsity=sparsity.tocsr(),
        loss="soft_l1",
        f_scale=settings.robust_scale,
        max_nfev=150,
        ftol=1e-6,
    )
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError("SOLVER_DID_NOT_CONVERGE")
    corrected = decode(result.x)

    def cost(r):
        s = settings.robust_scale
        return float(s * s * np.sum(np.sqrt(1 + (r / s) ** 2) - 1))

    initial_cost, final_cost = cost(residual(x0)), cost(residual(result.x))
    if final_cost > initial_cost + 1e-6:
        raise ValueError("OBJECTIVE_INCREASED")
    graph = [
        dict(
            i=i, j=j, kind=kind, measurement=z.tolist(), information=(w.T @ w).tolist()
        )
        for (i, j, z, kind), w in zip(edges, weights)
    ]
    output = dict(
        state="SUCCEEDED",
        source_revision=digest(data),
        settings=asdict(settings),
        poses_before=original.tolist(),
        poses_after=corrected.tolist(),
        edges=graph,
        candidates=candidates,
        metrics=dict(
            initial_cost=initial_cost,
            final_cost=final_cost,
            evaluations=int(result.nfev),
            accepted_loops=sum(e[3] == "loop" for e in edges),
            endpoint_gap_before_m=float(
                np.linalg.norm(original[-1, :3, 3] - original[0, :3, 3])
            ),
            endpoint_gap_after_m=float(
                np.linalg.norm(corrected[-1, :3, 3] - corrected[0, :3, 3])
            ),
        ),
        provenance=data["provenance"],
        operational_application="NOT_APPLIED",
    )
    output["revision"] = digest(output)
    return output


def preview(data, result=None):
    before, after = [], []
    poses = [f["T_parent_body"] for f in data["keyframes"]]
    corrected = (
        result["poses_after"] if result and result["state"] == "SUCCEEDED" else poses
    )
    per_frame = max(1, 16000 // len(poses))
    for frame, a, b in zip(data["keyframes"], poses, corrected):
        points = np.asarray(frame["points"])[
            :: max(1, int(np.ceil(len(frame["points"]) / per_frame)))
        ]
        before.extend(project(points, np.asarray(a)).tolist())
        after.extend(project(points, np.asarray(b)).tolist())
    return dict(
        before=before,
        after=after,
        path_before=[np.asarray(t)[:3, 3].tolist() for t in poses],
        path_after=[np.asarray(t)[:3, 3].tolist() for t in corrected],
        candidates=result.get("candidates", []) if result else [],
        revision=result.get("revision") if result else digest(data),
    )
