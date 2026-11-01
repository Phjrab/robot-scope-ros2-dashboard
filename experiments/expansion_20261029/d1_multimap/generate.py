"""Synthetic-only fixture writer; generated PCDs belong in temporary directories."""

import hashlib
from pathlib import Path
import numpy as np
from robot_dashboard.relocalization.experimental_se3 import (
    from_translation_rpy,
    inverse,
    transform_points,
)


def write_cloud(path, points):
    data = np.zeros(
        len(points),
        dtype=[
            (k, "<f4")
            for k in ("x", "y", "z", "normal_x", "normal_y", "normal_z", "intensity")
        ],
    )
    for i, k in enumerate(("x", "y", "z")):
        data[k] = points[:, i]
    data["normal_z"] = 1
    data["intensity"] = np.arange(len(points))
    header = f"VERSION .7\nFIELDS x y z normal_x normal_y normal_z intensity\nSIZE 4 4 4 4 4 4 4\nTYPE F F F F F F F\nCOUNT 1 1 1 1 1 1 1\nWIDTH {len(points)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS {len(points)}\nDATA binary\n".encode()
    Path(path).write_bytes(header + data.tobytes())
    return dict(
        map_id=Path(path).stem,
        revision="1",
        frame_id="camera_init",
        units="m",
        asset_role="full_source",
        sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
    )


def fixture(root, count=700, noise=0.001, partial=False):
    rng = np.random.default_rng(92)
    world = rng.uniform([-3, -2, -1], [3, 2, 2], (count, 3))
    poses = [
        np.eye(4),
        from_translation_rpy([0.35, -0.2, 0.15], [0.06, -0.04, 0.18]),
        from_translation_rpy([-0.3, 0.15, -0.1], [-0.03, 0.08, -0.13]),
    ]
    sources = []
    paths = {}
    for i, T in enumerate(poses):
        w = (
            world
            if not partial
            else world[
                (world[:, 0] > [-4, -1, -0.2][i]) & (world[:, 0] < [1, 2.5, 4][i])
            ]
        )
        p = transform_points(inverse(T), w) + rng.normal(0, noise, w.shape)
        path = Path(root) / f"map{i}.pcd"
        d = write_cloud(path, p)
        sources.append(d)
        paths[d["map_id"]] = path
    return sources, lambda d: paths[d["map_id"]], poses
