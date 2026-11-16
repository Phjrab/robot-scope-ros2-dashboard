"""Local scan/map diagnostics, with density balancing and fixed-population scores.

This module is not used by the live matcher or the graph's register() path.
A locally passing fit cannot establish a unique global location or body pose.
"""

from dataclasses import asdict

import numpy as np
from scipy.spatial import cKDTree

from .core import Settings, fit_registration, project, register, transform

MAX_DIAGNOSTIC_POINTS = 250_000


def _points(value):
    points = np.asarray(value, dtype=float)
    if (
        points.ndim != 2
        or points.shape[1] != 3
        or not 30 <= len(points) <= MAX_DIAGNOSTIC_POINTS
        or not np.isfinite(points).all()
        or np.max(np.abs(points)) > 500
    ):
        raise ValueError("INVALID_DIAGNOSTIC_POINTS")
    return points


def voxel_centroids(points, size=0.08):
    """Equal spatial support, independent of exact duplicate row multiplicity."""
    if not np.isfinite(size) or not 0.02 <= size <= 0.5:
        raise ValueError("INVALID_DIAGNOSTIC_VOXEL")
    points = np.unique(_points(points), axis=0)
    _, inverse = np.unique(
        np.floor(points / size).astype(np.int64), axis=0, return_inverse=True
    )
    counts = np.bincount(inverse)
    return np.column_stack(
        [np.bincount(inverse, weights=points[:, axis]) / counts for axis in range(3)]
    )


def alignment_score(source, target, candidate, radius=0.75):
    """Score every supplied row; no trim, resampling or hidden population change."""
    if not np.isfinite(radius) or not 0 < radius <= 2:
        raise ValueError("INVALID_SCORE_RADIUS")
    moved = project(_points(source), transform(candidate))
    distance = cKDTree(_points(target)).query(moved)[0]
    mask = distance <= radius
    return dict(
        point_count=len(source),
        reference_count=len(target),
        radius_m=radius,
        inlier_count=int(mask.sum()),
        overlap=float(mask.mean()),
        inlier_rmse_m=float(np.sqrt(np.mean(distance[mask] ** 2)))
        if mask.any()
        else None,
        all_point_rmse_m=float(np.sqrt(np.mean(distance**2))),
        capped_rmse_m=float(np.sqrt(np.mean(np.minimum(distance, radius) ** 2))),
        p50_m=float(np.median(distance)),
        p95_m=float(np.percentile(distance, 95)),
    )


def transfer_local_hypothesis(
    reference_scan, source_scan, map_from_reference, *, settings=None
):
    """Compose an UNVERIFIED map seed with an accepted sensor-to-sensor fit.

    Identity is a local relative seed, not a global search. Failure returns no
    transferred seed. Success preserves the original global uncertainty.
    """
    settings = (settings or Settings()).validate()
    reference_scan, source_scan = _points(reference_scan), _points(source_scan)
    reference = voxel_centroids(reference_scan[np.any(reference_scan != 0, axis=1)])
    source = voxel_centroids(source_scan[np.any(source_scan != 0, axis=1)])
    original_seed = transform(map_from_reference)
    if min(len(reference), len(source)) < 30:
        relative, metrics = (
            None,
            dict(reason="TOO_FEW_SPATIAL_POINTS", failures=["TOO_FEW_SPATIAL_POINTS"]),
        )
    else:
        relative, metrics = register(source, reference, np.eye(4), settings)
    return dict(
        state="UNVERIFIED_LOCAL_HYPOTHESIS"
        if relative is not None
        else "RELATIVE_FIT_REJECTED",
        metrics=metrics,
        reference_from_source=relative.tolist() if relative is not None else None,
        map_from_source=(original_seed @ relative).tolist()
        if relative is not None
        else None,
        global_location_verified=False,
        operational_application="NOT_APPLIED",
    )


def inspect_saved_map(
    source, target, seed, *, ambiguity_reasons=(), settings=None, voxel_size=0.08
):
    """Compare legacy full-density ICP and opt-in density-balanced local ICP.

    Zero source XYZ is a declared no-return filter for raw LiDAR. Map origin
    points are retained. Both fits are rescored on the same original arrays and
    on the same nonzero source population. A candidate's transform is diagnostic
    only, including when its numerical gates pass.
    """
    source, target = _points(source), _points(target)
    seed = transform(seed)
    settings = (settings or Settings()).validate()
    if not isinstance(ambiguity_reasons, (tuple, list)) or any(
        not isinstance(reason, str) for reason in ambiguity_reasons
    ):
        raise ValueError("INVALID_AMBIGUITY_REASONS")
    valid_source = source[np.any(source != 0, axis=1)]
    _points(valid_source)
    balanced_source = voxel_centroids(valid_source, voxel_size)
    balanced_target = voxel_centroids(target, voxel_size)
    before = alignment_score(source, target, seed)
    before_valid = alignment_score(valid_source, target, seed)
    fits = {}
    for name, fit_source, fit_target in (
        ("legacy_density", valid_source, target),
        ("balanced_density", balanced_source, balanced_target),
    ):
        if min(len(fit_source), len(fit_target)) < 30:
            candidate, metrics = (
                None,
                dict(
                    reason="TOO_FEW_SPATIAL_POINTS", failures=["TOO_FEW_SPATIAL_POINTS"]
                ),
            )
        else:
            candidate, metrics = fit_registration(
                fit_source, fit_target, seed.copy(), settings
            )
        fits[name] = dict(
            source_fit_points=len(fit_source),
            target_fit_points=len(fit_target),
            geometry_pass=metrics["reason"] == "ACCEPTED",
            metrics=metrics,
            diagnostic_transform=candidate.tolist() if candidate is not None else None,
            # Raw-to-raw scoring has the same 0.75 m gate and population in both methods.
            original_population_after=alignment_score(source, target, candidate)
            if candidate is not None
            else None,
            nonzero_population_after=alignment_score(valid_source, target, candidate)
            if candidate is not None
            else None,
        )
    return dict(
        schema="robot-scope.offline-scan-map-diagnostic/v1",
        state="DIAGNOSTIC_ONLY",
        operational_application="NOT_APPLIED",
        global_location_verified=False,
        body_pose_verified=False,
        absolute_accuracy_m=None,
        ambiguity_reasons=list(ambiguity_reasons),
        settings=asdict(settings),
        preprocessing=dict(
            source_points=len(source),
            source_zero_rows=len(source) - len(valid_source),
            source_nonzero_points=len(valid_source),
            source_unique_nonzero_points=len(np.unique(valid_source, axis=0)),
            target_points=len(target),
            target_unique_points=len(np.unique(target, axis=0)),
            exact_duplicates_removed_for_balanced_fit=True,
            voxel_size_m=voxel_size,
            voxel_representative="centroid_of_unique_points",
            source_range_crop=False,
            raw_population_preserved_for_scoring=True,
        ),
        seed=seed.tolist(),
        original_population_before=before,
        nonzero_population_before=before_valid,
        fits=fits,
    )
