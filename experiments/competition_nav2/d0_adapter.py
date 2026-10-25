"""Opt-in, hash-pinned D0 input/body/sensor adapter for the existing native runner."""

import hashlib
import json
import math
import os
from pathlib import Path
import select
import subprocess
import sys
import time

import numpy as np

from core import polygon, rectangle, intersects, clearance, point_segment_distance
from fixtures import ROOT, digest, World


def pin():
    return json.loads((ROOT / "repro/d0-source.json").read_text())


def input_path(name):
    return (
        ROOT / "d0_input" / pin()["shared_path"] / "fixtures" / (name + ".truth.json")
    )


def verify_bundle(bundle):
    expected = pin()
    manifest = bundle["manifest"]
    if digest(manifest) != expected["manifest_sha256"]:
        raise ValueError("D0 canonical manifest mismatch")
    for key, name in [
        ("truth", bundle["name"]),
        ("geometry", "geometry.json"),
        ("observations", bundle["name"].replace(".truth.", ".observations.")),
    ]:
        if digest(bundle[key]) != manifest["files"].get(name):
            raise ValueError("D0 canonical input mismatch: " + name)
    truth, geometry = bundle["truth"], bundle["geometry"]
    if truth["schema"] != "d0-scene-truth.v1" or truth["geometry_sha256"] != digest(
        geometry
    ):
        raise ValueError("unsupported D0 truth/geometry")
    transform = geometry["simulation_transform"]
    if (
        transform["matrix_xyz"]
        != [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        or transform["yaw_offset_rad"] != 0
    ):
        raise ValueError("unsupported simulation transform")
    if truth["frame_id"] != "arena_design" or truth["map_transform"] is not None:
        raise ValueError("D0 adapter is design simulation only")
    return truth


def load_fixture(path):
    path = Path(path).resolve()
    expected = pin()
    root = ROOT / "d0_input"
    if not path.is_relative_to(root.resolve()) or path.suffix != ".json":
        raise ValueError("fixture must be inside prepared read-only D0 input")
    for name, sha in expected["files_sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != sha:
            raise ValueError("D0 dependency changed: " + name)
    bundle = dict(
        name=path.name,
        truth=json.loads(path.read_text()),
        geometry=json.loads((path.parent / "geometry.json").read_text()),
        observations=json.loads(
            path.with_name(path.name.replace(".truth.", ".observations.")).read_text()
        ),
        manifest=json.loads((path.parent / "manifest.json").read_text()),
    )
    truth = verify_bundle(bundle)
    sensor = truth["sensor"]
    margin = truth["clearance_m"]
    body = truth["footprint"]
    effective = rectangle(
        min(p[0] for p in body) - margin,
        min(p[1] for p in body) - margin,
        max(p[0] for p in body) + margin,
        max(p[1] for p in body) + margin,
    )
    fixture = dict(
        scenario="d0_" + truth["scenario"],
        world_kind="d0_shared",
        seed=truth["seed"],
        start=truth["start"],
        goal=truth["goal"],
        footprint=body,
        effective_footprint=effective,
        clearance_m=margin,
        resolution_m=0.02,
        pose_source="SIM_GT",
        timeout_s=65.0,
        parking_allowed=truth["parking_allowed"],
        sensor_delay_s=sensor["sensor_delay_s"],
        sensor_period_s=sensor["sensor_period_s"],
        sensor_ttl_s=sensor["freshness_limit_s"],
        scan_beams=sensor["beams"],
        sensor_frame=sensor["frame_id"],
        obstacles=truth["obstacles"],
        scope=truth["scope"],
        map_transform=None,
        d0_bundle=bundle,
        d0_source_commit=expected["source_commit"],
        d0_manifest_sha256=expected["manifest_sha256"],
        d0_scene_sha256=truth["scene_sha256"],
        d0_input_relative=str(path.relative_to(ROOT)),
        frame_mapping="arena_design -> d0_sim_map -> map: identity simulation only",
        grid_policy="20 mm closed cells; all boundary corners contained; forbidden polygon SAT; hidden cones excluded",
        margin_policy="axis-pad raw body by 0.03 m once; Nav2 footprint_padding=0; independent padded-body sweep",
    )
    if sensor["dropout_start_s"] is not None:
        fixture["sensor_dropout_s"] = sensor["dropout_start_s"]
    return fixture


class Sensor:
    def __init__(self, path):
        self.process = subprocess.Popen(
            [sys.executable, str(ROOT / "d0_sensor_worker.py"), str(path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            bufsize=0,
        )
        self.buffer = b""
        if self.receive(8.0) != {"ready": True}:
            self.close()
            raise ValueError("D0 sensor startup handshake failed")

    def receive(self, timeout):
        deadline = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([self.process.stdout], [], [], left)[0]:
                raise TimeoutError("D0 sensor response deadline exceeded")
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk or len(self.buffer) + len(chunk) > 65536:
                raise RuntimeError("D0 sensor stream ended/oversized")
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)

    def observe(self, pose, stamp):
        self.process.stdin.write(
            (json.dumps(dict(pose=list(pose), stamp_s=stamp)) + "\n").encode()
        )
        return self.receive(0.20)

    def close(self):
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=2.0)
        self.process.stdout.close()


def sensor_conformance(fixture):
    sensor = Sensor(ROOT / fixture["d0_input_relative"])
    maximum = 0.0
    try:
        for probe in fixture["d0_bundle"]["observations"]["probes"]:
            observed = sensor.observe(
                probe["requested_pose_sim"], probe["probe_stamp_s"]
            )
            expected = probe["observation"]
            if expected is None:
                if observed is not None:
                    raise ValueError("D0 dropout conformance mismatch")
                continue
            if observed is None or len(observed["ranges_m"]) != 360:
                raise ValueError("D0 sensor range count mismatch")
            maximum = max(
                maximum,
                max(
                    abs(a - b)
                    for a, b in zip(observed["ranges_m"], expected["ranges_m"])
                ),
            )
            if maximum > 1e-9 or any(
                observed[k] != expected[k]
                for k in (
                    "source_stamp_s",
                    "source_epoch",
                    "acquisition_pose_sim",
                    "source",
                )
            ):
                raise ValueError("D0 sensor conformance mismatch")
    finally:
        sensor.close()
    return dict(
        status="PASS",
        probes=3,
        beams_per_delivered_probe=360,
        max_range_delta_m=maximum,
        source_commit=fixture["d0_source_commit"],
        manifest_sha256=fixture["d0_manifest_sha256"],
    )


def contains(poly, x, y):
    inside = np.zeros(np.broadcast(x, y).shape, dtype=bool)
    for a, b in zip(poly, poly[1:] + poly[:1]):
        if b[1] != a[1]:
            inside ^= ((a[1] > y) != (b[1] > y)) & (
                x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]
            )
    return inside


def cell_touch(poly, x, y, half):
    overlap = np.ones(np.broadcast(x, y).shape, dtype=bool)
    axes = [(1.0, 0.0), (0.0, 1.0)] + [
        (a[1] - b[1], b[0] - a[0]) for a, b in zip(poly, poly[1:] + poly[:1])
    ]
    for ax, ay in axes:
        values = [u * ax + v * ay for u, v in poly]
        center = x * ax + y * ay
        radius = half * (abs(ax) + abs(ay))
        overlap &= (center + radius >= min(values) - 1e-10) & (
            center - radius <= max(values) + 1e-10
        )
    return overlap


def edge_distance(a, b):
    return min(
        point_segment_distance(p, u, v)
        for one, two in ((a, b), (b, a))
        for p in one
        for u, v in zip(two, two[1:] + two[:1])
    )


class D0World:
    _cache = {}

    def __init__(self, fixture):
        self.fixture = fixture
        truth = verify_bundle(fixture["d0_bundle"])
        margin = truth["clearance_m"]
        raw = truth["footprint"]
        padded = rectangle(
            min(p[0] for p in raw) - margin,
            min(p[1] for p in raw) - margin,
            max(p[0] for p in raw) + margin,
            max(p[1] for p in raw) + margin,
        )
        if (
            fixture["footprint"] != raw
            or [list(p) for p in fixture["effective_footprint"]]
            != [list(p) for p in padded]
            or any(
                fixture[k] != truth[k]
                for k in ("start", "goal", "parking_allowed", "seed", "obstacles")
            )
            or fixture["sensor_ttl_s"] != truth["sensor"]["freshness_limit_s"]
            or fixture["sensor_period_s"] != truth["sensor"]["sensor_period_s"]
        ):
            raise ValueError("D0 effective fixture changed from original input")
        self.boundary = truth["boundary_polygon"]
        self.forbidden = truth["forbidden_polygons"]
        self.body = fixture["effective_footprint"]
        self.raw_body = truth["footprint"]
        self.radius = max(math.hypot(*p) for p in self.body)
        self.res = fixture["resolution_m"]
        self.width, self.height = round(8 / self.res), round(6 / self.res)
        key = digest([self.boundary, self.forbidden, self.res])
        if key not in self._cache:
            yy, xx = np.indices((self.height, self.width))
            x, y = (xx + 0.5) * self.res, (yy + 0.5) * self.res
            free = np.ones_like(x, dtype=bool)
            for dx, dy in [
                (-0.5, -0.5),
                (-0.5, 0.5),
                (0.5, -0.5),
                (0.5, 0.5),
                (0.0, 0.0),
            ]:
                free &= contains(self.boundary, x + dx * self.res, y + dy * self.res)
            for p in self.forbidden:
                free &= ~cell_touch(p, x, y, self.res / 2)
            self._cache[key] = ~free
            self._cache[key].flags.writeable = False
        self.static = self._cache[key]
        self.sensor = None
        self.last_observation = None

    def obstacles(self, t):
        return [o["polygon"] for o in self.fixture["obstacles"] if t >= o["appears_s"]]

    def boundary_violation(self, pose):
        body = polygon(pose, self.body)
        if not contains(
            self.boundary,
            np.array([p[0] for p in body]),
            np.array([p[1] for p in body]),
        ).all():
            return True
        if any(
            intersects(body, [a, b])
            for a, b in zip(self.boundary, self.boundary[1:] + self.boundary[:1])
        ):
            return True
        return any(intersects(body, p) for p in self.forbidden)

    def collision(self, pose, t):
        return self.boundary_violation(pose) or any(
            intersects(polygon(pose, self.body), p) for p in self.obstacles(t)
        )

    def clearance(self, pose, t):
        body = polygon(pose, self.raw_body)
        return min(
            [edge_distance(body, self.boundary)]
            + [clearance(body, p) for p in self.forbidden + self.obstacles(t)]
        )

    def start_sensor(self):
        if self.sensor is None:
            self.sensor = Sensor(ROOT / self.fixture["d0_input_relative"])

    def scan(self, pose, t):
        self.start_sensor()
        self.last_observation = self.sensor.observe(pose, t)
        if self.last_observation is None:
            raise ValueError(
                "D0 dropout must suppress publishing, never produce clear ranges"
            )
        return self.last_observation["ranges_m"]

    def close(self):
        if self.sensor is not None:
            self.sensor.close()
            self.sensor = None

    write_map = World.write_map
