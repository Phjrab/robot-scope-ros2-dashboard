"""Immutable fixture generator. Static prior never contains hidden obstacles."""

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt

from core import FOOTPRINT, RADIUS, intersects, polygon, rectangle, clearance

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
RESOLUTION = 0.04
_STATIC_CACHE = {}


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def arena_geometry():
    p = REPO / "assets/competition-arena/revisions/rulebook-20261015/geometry.py"
    spec = importlib.util.spec_from_file_location("c3_arena_geometry", p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cases(seed=20261024):
    def box(x, y, sx=0.26, sy=0.26, appears=0.0):
        return dict(
            polygon=rectangle(x - sx / 2, y - sy / 2, x + sx / 2, y + sy / 2),
            appears_s=appears,
        )

    common = dict(
        seed=seed,
        start=[5.99, 1.65, math.pi / 2],
        goal=[5.99, 4.35, math.pi / 2],
        footprint=[list(p) for p in FOOTPRINT],
        resolution_m=RESOLUTION,
        pose_source="SIM_GT",
        timeout_s=45.0,
        sensor_delay_s=0.05,
        sensor_period_s=0.1,
        scan_beams=360,
        parking_allowed=True,
        scope="right straight and provisional parking extension; not whole course",
        map_transform=None,
        course_graph_status="DRAFT_UNCONFIRMED",
    )
    specifications = [
        ("empty", [], {}),
        ("single_cone", [box(5.70, 3.0)], {}),
        ("central_cone_failure", [box(5.99, 3.0)], {}),
        ("offcenter_575_failure", [box(5.75, 3.0)], {}),
        ("multiple_obstacles", [box(5.70, 2.5), box(6.30, 3.5)], {}),
        ("narrow_corridor", [box(5.58, 3.0, 0.12, 0.35)], {}),
        ("fully_blocked", [box(x, 2.4) for x in [5.60, 5.86, 6.12, 6.38]], {}),
        ("late_obstacle", [box(5.99, 3.0, appears=2.0)], {}),
        ("sensor_stale", [], dict(sensor_dropout_s=2.0)),
        (
            "hold_release_delayed",
            [],
            dict(hold_window_s=[2.0, 4.0], delayed_command_at_s=4.05),
        ),
        (
            "signal_hold_recovery",
            [box(x, 2.4) for x in [5.60, 5.86, 6.12, 6.38]],
            dict(hold_window_s=[1.0, 40.0], recovery_probe_s=2.0),
        ),
        ("parking_forbidden", [box(5.70, 3.0)], dict(parking_allowed=False)),
    ]
    return [
        dict(common, scenario=name, obstacles=obs, **extra)
        for name, obs, extra in specifications
    ]


def diagnostic_cases(seed=20261024):
    """Separate spacious synthetic room; original arena fixtures stay immutable."""
    fixture = dict(cases(seed)[0])
    fixture.update(
        scenario="diagnostic_single_obstacle",
        world_kind="diagnostic_room",
        scope="additional synthetic feasibility diagnostic; NOT competition arena",
        start=[2.0, 3.0, 0.0],
        goal=[6.0, 3.0, 0.0],
        timeout_s=65.0,
        obstacles=[dict(polygon=rectangle(3.7, 2.7, 4.3, 3.3), appears_s=0.0)],
        reference_waypoints=[
            [2.0, 3.0],
            [3.0, 3.0],
            [3.0, 2.0],
            [5.0, 2.0],
            [5.0, 3.0],
            [6.0, 3.0],
        ],
        reference_usage="offline full-footprint feasibility only; never sent to Nav2 or plant",
    )
    return [fixture]


def reference_feasibility(fixture):
    """Sweep rotate-in-place and straight segments at <=5 mm corner displacement."""
    from core import propagate, swept_poses

    world = World(fixture)
    pose = tuple(fixture["start"])
    poses = [pose]
    for target in fixture["reference_waypoints"][1:]:
        yaw = math.atan2(target[1] - pose[1], target[0] - pose[0])
        rotation = (yaw - pose[2] + math.pi) % (2 * math.pi) - math.pi
        poses.extend(swept_poses(pose, 0.0, rotation, 1.0))
        pose = propagate(pose, 0.0, rotation, 1.0)
        distance = math.dist(pose[:2], target)
        poses.extend(swept_poses(pose, distance, 0.0, 1.0))
        pose = propagate(pose, distance, 0.0, 1.0)
    rotation = (fixture["goal"][2] - pose[2] + math.pi) % (2 * math.pi) - math.pi
    poses.extend(swept_poses(pose, 0.0, rotation, 1.0))
    return dict(
        status="PASS" if all(not world.collision(p, 0.0) for p in poses) else "FAIL",
        samples=len(poses),
        min_conservative_clearance_m=min(world.clearance(p, 0.0) for p in poses),
        usage=fixture["reference_usage"],
        fixture_sha256=digest(fixture),
    )


class World:
    def __init__(self, fixture):
        self.fixture = fixture
        self.res = RESOLUTION
        self.width, self.height = 200, 150
        if fixture.get("world_kind") == "diagnostic_room":
            self.geometry = None
            self.static = np.ones((self.height, self.width), dtype=bool)
            self.static[20:130, 20:180] = False  # [0.8, 7.2] x [0.8, 5.2] m
            self.distance = distance_transform_edt(~self.static) * self.res
            self.static.flags.writeable = False
            self.distance.flags.writeable = False
            return
        self.geometry = arena_geometry()
        if fixture["parking_allowed"] in _STATIC_CACHE:
            self.static, self.distance = _STATIC_CACHE[fixture["parking_allowed"]]
            return
        g = self.geometry
        floors = dict(g.FLOORS)
        if not fixture["parking_allowed"]:
            floors.pop("floor_parking_bay")
        terrain = [
            z["polygon"] for z in g.zones() if z["type"] in ("RAMP", "STAIRS")
        ] + [g.FLOORS["floor_center_base"]]
        self.static = np.ones((self.height, self.width), dtype=bool)
        # Conservative occupied cells: all four corners and center must lie on floor;
        # any SAT intersection with a terrain polygon blocks the entire cell.
        for iy in range(self.height):
            for ix in range(self.width):
                cell = rectangle(
                    ix * self.res,
                    iy * self.res,
                    (ix + 1) * self.res,
                    (iy + 1) * self.res,
                )
                samples = cell + [((ix + 0.5) * self.res, (iy + 0.5) * self.res)]
                if all(
                    any(g.contains(p, point) for p in floors.values())
                    for point in samples
                ):
                    self.static[iy, ix] = any(intersects(cell, p) for p in terrain)
        self.distance = distance_transform_edt(~self.static) * self.res
        self.static.flags.writeable = False
        self.distance.flags.writeable = False
        _STATIC_CACHE[fixture["parking_allowed"]] = self.static, self.distance

    def obstacles(self, t):
        return [o["polygon"] for o in self.fixture["obstacles"] if t >= o["appears_s"]]

    def occupied(self, x, y):
        ix, iy = math.floor(x / self.res), math.floor(y / self.res)
        return not (0 <= ix < self.width and 0 <= iy < self.height) or bool(
            self.static[iy, ix]
        )

    def collision(self, pose, t):
        body = polygon(pose)
        if any(intersects(body, p) for p in self.obstacles(t)):
            return True
        return self.boundary_violation(pose)

    def boundary_violation(self, pose):
        body = polygon(pose)
        x0, x1 = (
            math.floor(min(p[0] for p in body) / self.res),
            math.floor(max(p[0] for p in body) / self.res),
        )
        y0, y1 = (
            math.floor(min(p[1] for p in body) / self.res),
            math.floor(max(p[1] for p in body) / self.res),
        )
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if (
                    not (0 <= x < self.width and 0 <= y < self.height)
                    or self.static[y, x]
                ) and intersects(
                    body,
                    rectangle(
                        x * self.res,
                        y * self.res,
                        (x + 1) * self.res,
                        (y + 1) * self.res,
                    ),
                ):
                    return True
        return False

    def clearance(self, pose, t):
        x, y = math.floor(pose[0] / self.res), math.floor(pose[1] / self.res)
        if not (0 <= x < self.width and 0 <= y < self.height):
            return 0.0
        # EDT cell-center distance minus body radius AND two cell diagonals is a
        # conservative proxy, reported separately from dynamic polygon distances.
        proxy = max(
            0.0, float(self.distance[y, x]) - RADIUS - 2 * math.sqrt(2) * self.res
        )
        return min([proxy] + [clearance(polygon(pose), p) for p in self.obstacles(t)])

    def scan(self, pose, t):
        """First hit against prior plus hidden projected cone bases; <=2 cm ray step."""
        n = self.fixture["scan_beams"]
        angles = np.arange(n) * 2 * math.pi / n - math.pi + pose[2]
        rr = np.arange(0.02, 8.001, self.res / 2)
        x = pose[0] + np.cos(angles)[:, None] * rr
        y = pose[1] + np.sin(angles)[:, None] * rr
        ix, iy = np.floor(x / self.res).astype(int), np.floor(y / self.res).astype(int)
        outside = (ix < 0) | (ix >= self.width) | (iy < 0) | (iy >= self.height)
        hit = (
            outside
            | self.static[
                np.clip(iy, 0, self.height - 1), np.clip(ix, 0, self.width - 1)
            ]
        )
        for poly in self.obstacles(t):
            hit |= (
                (x >= poly[0][0])
                & (x <= poly[2][0])
                & (y >= poly[0][1])
                & (y <= poly[2][1])
            )
        first = hit.argmax(axis=1)
        return np.where(hit.any(axis=1), rr[first], 8.0).tolist()

    def write_map(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        image = np.where(self.static, 0, 254).astype(np.uint8)[::-1]
        (directory / "map.pgm").write_bytes(
            f"P5\n{self.width} {self.height}\n255\n".encode() + image.tobytes()
        )
        (directory / "map.yaml").write_text(
            "image: map.pgm\nmode: trinary\nresolution: 0.04\norigin: [0.0, 0.0, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n"
        )
        return hashlib.sha256((directory / "map.pgm").read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for f in cases():
        path = args.output / f["scenario"]
        world = World(f)
        f["map_sha256"] = world.write_map(path)
        f["fixture_sha256"] = digest(f)
        (path / "fixture.json").write_text(json.dumps(f, indent=2) + "\n")
        manifest.append(
            dict(
                scenario=f["scenario"],
                fixture_sha256=f["fixture_sha256"],
                map_sha256=f["map_sha256"],
            )
        )
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
