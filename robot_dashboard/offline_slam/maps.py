"""Rebuild point maps and conservative single-level occupancy candidates."""

from __future__ import annotations

import numpy as np

from .core import Settings, project


def pcd_bytes(points):
    points = np.asarray(points, dtype="<f4")
    header = (
        "# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\n"
        f"COUNT 1 1 1\nWIDTH {len(points)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\n"
        f"POINTS {len(points)}\nDATA binary\n"
    )
    return header.encode() + points.tobytes()


def ray_cells(start, end):
    x, y = start
    ex, ey = end
    dx, dy = abs(ex - x), -abs(ey - y)
    sx, sy = (1 if x < ex else -1), (1 if y < ey else -1)
    error = dx + dy
    while True:
        yield x, y
        if x == ex and y == ey:
            return
        twice = 2 * error
        if twice >= dy:
            error += dy
            x += sx
        if twice <= dx:
            error += dx
            y += sy


def rebuild(data, result):
    settings = Settings(**result["settings"])
    clouds = [
        project(f["points"], np.asarray(t))
        for f, t in zip(data["keyframes"], result["poses_after"])
    ]
    points = np.concatenate(clouds)
    # Preserve the anchored coordinate system; no silent ground-plane fitting.
    origins = np.array(
        [
            project(np.asarray([data["sensor_origin_body"]]), np.asarray(t))[0]
            for t in result["poses_after"]
        ]
    )
    xy = np.concatenate([points[:, :2], origins[:, :2]])
    lower = (
        np.floor(xy.min(0) / settings.resolution) * settings.resolution
        - settings.resolution
    )
    size = np.ceil((xy.max(0) - lower) / settings.resolution).astype(int) + 2
    if np.prod(size) > 4_000_000 or max(size) > 4000:
        raise ValueError("GRID_TOO_LARGE")
    odds = np.zeros((size[1], size[0]), dtype=float)
    seen = np.zeros_like(odds, dtype=bool)
    hit_count = 0
    for cloud, origin in zip(clouds, origins):
        selected = cloud[
            (cloud[:, 2] >= settings.min_height) & (cloud[:, 2] <= settings.max_height)
        ]
        start = np.floor((origin[:2] - lower) / settings.resolution).astype(int)
        # One nearest endpoint per angular bin avoids clearing behind nearer returns.
        rays = {}
        for point in selected:
            delta = point[:2] - origin[:2]
            distance = float(np.linalg.norm(delta))
            if not 0.1 <= distance <= 30:
                continue
            angle = int(np.floor(np.arctan2(delta[1], delta[0]) * 720 / (2 * np.pi)))
            if angle not in rays or distance < rays[angle][0]:
                rays[angle] = (distance, point)
        free, hits = set(), set()
        for _, point in rays.values():
            end = np.floor((point[:2] - lower) / settings.resolution).astype(int)
            cells = list(ray_cells(tuple(start), tuple(end)))
            free.update(cells[:-1])
            hits.add(cells[-1])
        hit_count += len(hits)
        for x, y in free - hits:
            odds[y, x] = max(-4, odds[y, x] - 0.7)
            seen[y, x] = True
        for x, y in hits:
            odds[y, x] = min(4, odds[y, x] + 1.2)
            seen[y, x] = True
    if not hit_count:
        raise ValueError("NO_POINTS_IN_HEIGHT_BAND")
    pixels = np.full(odds.shape, 205, dtype=np.uint8)
    pixels[seen & (odds < -0.4)] = 254
    pixels[seen & (odds > 0.6)] = 0
    pgm = f"P5\n{size[0]} {size[1]}\n255\n".encode() + pixels[::-1].tobytes()
    yaml = (
        f"image: map.pgm\nresolution: {settings.resolution}\n"
        f"origin: [{lower[0]}, {lower[1]}, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n"
    )
    return {
        "optimized.pcd": pcd_bytes(points),
        "map.pgm": pgm,
        "map.yaml": yaml.encode(),
    }
