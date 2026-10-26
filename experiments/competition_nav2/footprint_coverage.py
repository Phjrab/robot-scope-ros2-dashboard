"""B1 inflation coverage calculation and read-only full-body evidence checks.

No map or command is published here. Geometry passed to the independent validator
never becomes a planner prior. Native shortcut behavior is only reconstructed.
"""

import math

from core import point_segment_distance, polygon

OMNI_VARIANTS = ("omni_lattice", "omni_coverage")


def coverage(footprint, resolution):
    if resolution <= 0 or not math.isfinite(resolution):
        raise ValueError("invalid grid resolution")
    circum = max(math.hypot(*p) for p in footprint)
    inscribed = min(
        point_segment_distance((0, 0), a, b)
        for a, b in zip(footprint, footprint[1:] + footprint[:1])
    )
    # Pose-to-cell and touched-obstacle-to-cell each allow half a cell diagonal.
    # Round the resulting field support UP to a whole cell; never alter the body
    # or the upstream computeCost(circum/resolution) collision-check threshold.
    allowance = math.sqrt(2) * resolution
    cells = math.ceil((circum + allowance) / resolution)
    return dict(
        inscribed_radius_m=inscribed,
        circumscribed_radius_m=circum,
        grid_allowance_m=allowance,
        required_support_m=circum + allowance,
        inflation_cells=cells,
        inflation_radius_m=round(cells * resolution, 12),
    )


def inflation_cost(distance_m, inscribed, scaling=5.0):
    """Independent reconstruction of Humble 1.1.20 computeCost; not native code."""
    if distance_m == 0:
        return 254
    if distance_m <= inscribed:
        return 253
    return int(252 * math.exp(-scaling * (distance_m - inscribed)))


def interpolated_poses(a, b, radius):
    """Linear XY/shortest-yaw intervals, <=2mm corner motion and <=.005rad.

    This checks intervals between native poses, not only waypoints. It is bounded
    numerical sampling, not an exact continuous collision or hard realtime proof.
    """
    dyaw = math.atan2(math.sin(b[2] - a[2]), math.cos(b[2] - a[2]))
    count = max(
        1,
        math.ceil((math.dist(a[:2], b[:2]) + radius * abs(dyaw)) / 0.002),
        math.ceil(abs(dyaw) / 0.005),
    )
    for i in range(count + 1):
        u = i / count
        yield (a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1]), a[2] + u * dyaw)


class PublishedGrid:
    """Closed-cell polygon overlap, deliberately independent of native shortcuts."""

    def __init__(self, row):
        import numpy as np
        from observations import grid_values

        self.row = row
        self.values = np.array(grid_values(row)).reshape(row["height"], row["width"])

    def cell(self, pose):
        r, (ox, oy) = self.row["resolution"], self.row["origin"]
        return math.floor((pose[0] - ox) / r), math.floor((pose[1] - oy) / r)

    def overlaps(self, body):
        import numpy as np
        from d0_adapter import cell_touch

        r, (ox, oy) = self.row["resolution"], self.row["origin"]
        x0, y0 = self.cell((min(p[0] for p in body), min(p[1] for p in body)))
        x1, y1 = self.cell((max(p[0] for p in body), max(p[1] for p in body)))
        if x0 < 0 or y0 < 0 or x1 >= self.row["width"] or y1 >= self.row["height"]:
            return "outside_grid"
        sub = self.values[y0 : y1 + 1, x0 : x1 + 1]
        ys, xs = np.where((sub == 100) | (sub == -1))
        if (
            len(xs)
            and cell_touch(
                body, ox + (xs + x0 + 0.5) * r, oy + (ys + y0 + 0.5) * r, r / 2
            ).any()
        ):
            return "lethal_or_unknown"
        return None

    def center_cost(self, pose, radius, inscribed, scaling=5.0):
        """Reinflate retained lethal cells; unknown is retained, never made free."""
        import numpy as np

        x, y = self.cell(pose)
        current = int(self.values[y, x])
        if current in (-1, 100):
            return dict(occupancy=current, raw_cost=None, distance_m=None)
        ys, xs = np.where(self.values == 100)
        cells = float(np.hypot(xs - x, ys - y).min())
        nominal_resolution = round(
            self.row["resolution"], 8
        )  # OccupancyGrid float32; native parameter is .02 double.
        distance = cells * nominal_resolution
        # Humble cellDistance uses ceil; radius truncation occurs at enqueue.
        cost = (
            inflation_cost(distance, inscribed, scaling)
            if cells <= math.ceil(radius / nominal_resolution)
            else 0
        )
        return dict(observed_occupancy=current, raw_cost=cost, distance_m=distance)


def path_footprints(fixture, observations, require_z=True):
    """Post-run truth + bracketing-map audit. Never modifies planner inputs."""
    from fixtures import make_world

    world = make_world(fixture)
    maps = [r for r in observations if r["kind"] == "costmap"]
    grids = {}
    reports = []
    for row in (r for r in observations if r["kind"] == "path"):
        quats, points = row.get("quaternions", []), row["points"]
        if row["frame"] != "map" or len(quats) != len(points) or not points:
            raise ValueError("missing native path orientation/frame/points")
        if require_z and (
            len(row.get("z", [])) != len(points)
            or any(not math.isfinite(z) or abs(z) > 1e-6 for z in row.get("z", []))
        ):
            raise ValueError("missing/nonplanar native path Z")
        poses = []
        for point, q in zip(points, quats):
            if len(point) != 2 or len(q) != 4 or abs(q[0]) > 1e-6 or abs(q[1]) > 1e-6:
                raise ValueError("invalid/nonplanar native path pose")
            if (
                not all(math.isfinite(v) for v in [*point, *q])
                or abs(sum(v * v for v in q) - 1) > 1e-4
            ):
                raise ValueError("invalid native path quaternion/point")
            poses.append(
                (
                    *point,
                    math.atan2(
                        2 * (q[3] * q[2] + q[0] * q[1]), 1 - 2 * (q[1] ** 2 + q[2] ** 2)
                    ),
                )
            )
        preceding = [m for m in maps if m["source_sim_s"] <= row["source_sim_s"] + 1e-6]
        if not preceding:
            raise ValueError("native path lacks preceding global map")
        m = preceding[-1]
        key = m["receipt_monotonic"]
        if key not in grids:
            grids[key] = PublishedGrid(m)
        grid = grids[key]
        first_truth = first_grid = None
        count = 0
        for index, (a, b) in enumerate(zip(poses, poses[1:] or poses)):
            for pose in interpolated_poses(a, b, world.radius):
                count += 1
                if first_truth is None and world.collision(
                    pose, max(0.0, row["source_elapsed_s"])
                ):
                    first_truth = dict(segment=index, pose=list(pose))
                if first_grid is None:
                    kind = grid.overlaps(polygon(pose, world.body))
                    if kind:
                        first_grid = dict(segment=index, pose=list(pose), kind=kind)
        reports.append(
            dict(
                source_sim_s=row["source_sim_s"],
                receipt_monotonic=row["receipt_monotonic"],
                grid_source_sim_s=m["source_sim_s"],
                points=len(poses),
                samples=count,
                first_truth_collision=first_truth,
                first_grid_collision=first_grid,
            )
        )
    return dict(
        status="FAIL"
        if any(r["first_truth_collision"] or r["first_grid_collision"] for r in reports)
        else "PASS"
        if reports
        else "NO_PATH",
        path_count=len(reports),
        paths=reports,
        method="Independent original padded-body truth and closed lethal/unknown grid cells; <=2mm corner / .005rad interpolation. Published maps asynchronous, not atomic native checker snapshots.",
    )
