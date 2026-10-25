"""Read-only scan/costmap/path evidence. No publisher, planner or plant control."""

import base64
import json
import math
import zlib


def grid_payload(data):
    return base64.b64encode(zlib.compress(bytes(int(v) % 256 for v in data))).decode()


def grid_values(row):
    data = zlib.decompress(base64.b64decode(row["data_zlib_base64"]))
    if len(data) != row["width"] * row["height"]:
        raise ValueError("costmap size mismatch")
    return [v if v < 128 else v - 256 for v in data]


def inside(point, poly, margin=0.0):
    return (
        min(p[0] for p in poly) - margin <= point[0] <= max(p[0] for p in poly) + margin
        and min(p[1] for p in poly) - margin
        <= point[1]
        <= max(p[1] for p in poly) + margin
    )


def scan_hits(row, poly):
    x, y, yaw = row["source_pose"]
    return [
        i
        for i, r in enumerate(row["ranges"])
        if 0.02 <= r < 8.0
        and inside(
            (
                x + r * math.cos(yaw - math.pi + i * 2 * math.pi / len(row["ranges"])),
                y + r * math.sin(yaw - math.pi + i * 2 * math.pi / len(row["ranges"])),
            ),
            poly,
            0.025,
        )
    ]


def lethal_cells(row, poly):
    data = grid_values(row)
    res, (ox, oy) = row["resolution"], row["origin"]
    return sum(
        v == 100
        and inside(
            (ox + (i % row["width"] + 0.5) * res, oy + (i // row["width"] + 0.5) * res),
            poly,
            res,
        )
        for i, v in enumerate(data)
    )


def path_crosses(row, poly):
    points = row["points"]
    for a, b in zip(points, points[1:]):
        n = max(1, math.ceil(math.dist(a, b) / 0.01))
        if any(
            inside((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n), poly)
            for i in range(n + 1)
        ):
            return True
    return False


def replan_evidence(fixture, observations, scans):
    """Recompute chronology and geometric path change from retained messages."""
    obstacle = fixture["obstacles"][0]
    appears, poly = obstacle["appears_s"], obstacle["polygon"]
    appearances = [r for r in observations if r["kind"] == "appearance"]
    maps = [r for r in observations if r["kind"] == "costmap" and r["frame"] == "map"]
    paths = [
        r
        for r in observations
        if r["kind"] == "path" and r["frame"] == "map" and len(r["points"]) > 1
    ]
    seen = [
        r
        for r in scans
        if r.get("source_elapsed_s", -1) >= appears and scan_hits(r, poly)
    ]
    before = [
        r
        for r in maps
        if 0 <= r["source_elapsed_s"] < appears and lethal_cells(r, poly) == 0
    ]
    inserted = [
        r
        for r in maps
        if r["source_elapsed_s"] >= appears and lethal_cells(r, poly) > 0
    ]
    old = [
        r
        for r in paths
        if 0 <= r["source_elapsed_s"] < appears and path_crosses(r, poly)
    ]
    changed = [
        r
        for r in paths
        if inserted
        and r["source_sim_s"] >= inserted[0]["source_sim_s"]
        and not path_crosses(r, poly)
        and math.dist(r["points"][-1], fixture["goal"][:2]) <= 0.12
    ]
    errors = []
    for ok, message in [
        (appearances, "actual obstacle appearance absent"),
        (seen, "virtual scan first hit absent"),
        (before, "no pre-appearance free native costmap"),
        (inserted, "native costmap insertion absent"),
        (old, "no initial native path through future obstacle"),
        (changed, "no subsequent native detour path"),
    ]:
        if not ok:
            errors.append(message)
    if (
        seen
        and inserted
        and inserted[0]["source_sim_s"] + 1e-6 < seen[0]["source_sim_s"]
    ):
        errors.append("costmap precedes sensor observation")
    if appearances and not appears <= appearances[0]["elapsed_s"] <= appears + 0.051:
        errors.append("appearance timing mismatch")

    def first(rows, key):
        return rows[0][key] if rows else None

    return dict(
        status="PASS" if not errors else "FAIL",
        errors=errors,
        requested_appearance_elapsed_s=appears,
        actual_appearance_elapsed_s=first(appearances, "elapsed_s"),
        first_scan_elapsed_s=first(seen, "source_elapsed_s"),
        first_scan_receipt_sim_s=first(seen, "sim_t"),
        first_costmap_elapsed_s=first(inserted, "source_elapsed_s"),
        first_detour_path_elapsed_s=first(changed, "source_elapsed_s"),
        first_scan_hit_beams=len(scan_hits(seen[0], poly)) if seen else 0,
        inserted_lethal_cells=lethal_cells(inserted[0], poly) if inserted else 0,
        initial_path_points=len(old[0]["points"]) if old else 0,
        detour_path_points=len(changed[0]["points"]) if changed else 0,
        scope="Native centerline path change; body safety is independently swept from actuator trace",
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]
