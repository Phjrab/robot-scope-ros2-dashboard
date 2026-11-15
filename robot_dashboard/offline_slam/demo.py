"""Explicit SYNTHETIC fixture for offline acceptance; never hardware evidence."""

import argparse
from pathlib import Path

import numpy as np

from .core import SCHEMA, encoded, inverse, pose, project


def fixture():
    rng = np.random.default_rng(8)
    world = rng.uniform([-2, -2, 0.3], [6, 6, 2.5], (600, 3))
    frames = []
    corners = np.array([[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]], dtype=float)
    for k in range(21):
        fraction = k / 20
        segment = min(k // 5, 3)
        alpha = (k - segment * 5) / 5
        xy = corners[segment] * (1 - alpha) + corners[segment + 1] * alpha
        truth = pose(
            np.r_[
                xy,
                0.1 * np.sin(2 * np.pi * fraction),
                0.03 * np.sin(2 * np.pi * fraction),
                0,
                0.2 * np.sin(2 * np.pi * fraction),
            ]
        )
        drift = pose(np.array([0.45, 0.2, 0.08, 0.02, 0.01, 0.07]) * fraction)
        estimated = drift @ truth
        local = project(world, inverse(truth)) + rng.normal(0, 0.002, world.shape)
        frames.append(
            dict(
                stamp_ns=1_000_000_000 + k * 1_000_000_000,
                T_parent_body=estimated.tolist(),
                points=local.tolist(),
            )
        )
    return dict(
        schema=SCHEMA,
        session_id="synthetic-square-3d",
        provenance="synthetic_fixture",
        parent_frame="camera_init",
        local_frame="body",
        calibration_id="synthetic-identity",
        sensor_origin_body=[0, 0, 0],
        keyframes=frames,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with Path(args.output).open("xb") as handle:
        handle.write(encoded(fixture()))
