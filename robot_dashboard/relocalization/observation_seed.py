"""One coarse local initialization; only the original full inputs can qualify."""
from __future__ import annotations

import time

import numpy as np

from .experimental_se3 import (
    Cloud, MAX_CORRESPONDENCE_M, MIN_OVERLAP, MIN_POINTS,
    from_translation_rpy, register_se3, transform_points,
)

COARSE_VOXEL_M = .4


def voxel_centroids(points: np.ndarray) -> np.ndarray:
    """Derived seed geometry, never a replacement for the final scoring inputs."""
    _, inverse, counts = np.unique(np.floor(points / COARSE_VOXEL_M).astype(np.int64),
                                   axis=0, return_inverse=True, return_counts=True)
    sums = np.zeros((len(counts), 3))
    np.add.at(sums, inverse, points)
    return sums / counts[:, None]


def prepare_seed(grid, points, target_frame, frame, stamp_ns, seed, deadline, *, course_region=None):
    """Keep close seeds unchanged; smooth a poor local seed once, under one deadline.

    The half-voxel trigger is a work-selection threshold, not an acceptance
    threshold. No old query, pose, epoch or transform is retained. Even a coarse
    result that converges must be refined and scored on the original full pair.
    """
    started = time.monotonic()
    _, squared = grid.nearest(transform_points(seed, points), deadline=deadline)
    inside = squared <= MAX_CORRESPONDENCE_M ** 2
    if int(inside.sum()) < MIN_POINTS or float(inside.mean()) < MIN_OVERLAP:
        return seed, None
    initial_rmse = float(np.sqrt(squared[inside].mean()))
    if initial_rmse <= COARSE_VOXEL_M / 2:
        return seed, None
    coarse, coarse_grid = grid.coarse_index(deadline=deadline)
    query = voxel_centroids(points)
    if min(len(coarse), len(query)) < MIN_POINTS:
        return seed, None
    from ..course_regions import course_weights
    result = register_se3(
        Cloud(coarse, target_frame, 'REGISTERED_MAP'),
        Cloud(query, frame, 'REGISTERED_QUERY', stamp_ns=stamp_ns), seed,
        reference_limit=100_000,
        nearest=lambda moved, _: coarse_grid.nearest(moved, deadline=deadline),
        **({'reference_weights': course_weights(coarse, course_region)} if course_region else {}),
    )
    pose = result['pose']
    refined = from_translation_rpy([pose[k] for k in ('x', 'y', 'z')],
                                   [pose[k] for k in ('roll_rad', 'pitch_rad', 'yaw_rad')])
    return refined, {
        'method': 'single-coarse-local-seed', 'qualification': 'NUMERICAL_SEED_ONLY',
        'voxel_m': COARSE_VOXEL_M, 'initial_rmse_m': initial_rmse,
        'reference_points': len(coarse), 'query_points': len(query),
        'iterations': result['metrics']['iterations'],
        'runtime_ms': (time.monotonic() - started) * 1000,
    }
