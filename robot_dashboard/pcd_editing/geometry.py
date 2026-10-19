"""The existing map-editor polygon contract, without browser or ROS state.

The arithmetic and epsilon intentionally match map_editor3d/core.js. In
particular, an outside selection complements XY membership, not the Z slab.
"""

from dataclasses import dataclass
import math

import numpy as np


class PcdEditError(ValueError):
    """An invalid edit or unsupported/malformed full-source PCD."""


KINDS = ("visibility", "localization", "keepout")
MAX_REGIONS = 100
MAX_VERTICES = 256
EPSILON = 1e-12


def _finite(value, label):
    if type(value) not in (int, float):
        raise PcdEditError(f"{label} must be finite")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise PcdEditError(f"{label} must be finite") from exc
    if not math.isfinite(result):
        raise PcdEditError(f"{label} must be finite")
    return result


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(point, a, b):
    return (
        abs(_cross(a, b, point)) <= EPSILON
        and min(a[0], b[0]) - EPSILON <= point[0] <= max(a[0], b[0]) + EPSILON
        and min(a[1], b[1]) - EPSILON <= point[1] <= max(a[1], b[1]) + EPSILON
    )


def _intersects(a, b, c, d):
    ab_c, ab_d = _cross(a, b, c), _cross(a, b, d)
    cd_a, cd_b = _cross(c, d, a), _cross(c, d, b)
    if (
        ((ab_c > EPSILON and ab_d < -EPSILON) or (ab_c < -EPSILON and ab_d > EPSILON))
        and ((cd_a > EPSILON and cd_b < -EPSILON) or (cd_a < -EPSILON and cd_b > EPSILON))
    ):
        return True
    return any((_on_segment(c, a, b), _on_segment(d, a, b), _on_segment(a, c, d), _on_segment(b, c, d)))


@dataclass(frozen=True)
class _CompiledRegion:
    kind: str
    selection: str
    polygon: tuple
    coordinate_scale: float
    origin_x: float
    origin_y: float
    extent: float
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    z_min: float
    z_max: float


def _compile_region(region):
    polygon = region["polygon"]
    coordinate_scale = max(abs(value) for vertex in polygon for value in vertex) or 1.0
    origin_x = polygon[0][0] / coordinate_scale
    origin_y = polygon[0][1] / coordinate_scale
    relative = [(x / coordinate_scale - origin_x, y / coordinate_scale - origin_y) for x, y in polygon]
    extent = max(abs(value) for vertex in relative for value in vertex)
    if not extent:
        raise PcdEditError("Polygon is degenerate")
    normalized = tuple((x / extent, y / extent) for x, y in relative)
    count = len(normalized)
    for index, a in enumerate(normalized):
        for b in normalized[index + 1:]:
            if abs(a[0] - b[0]) <= EPSILON and abs(a[1] - b[1]) <= EPSILON:
                raise PcdEditError("Polygon has repeated or numerically indistinguishable vertices; do not repeat the closing vertex")
        previous, following = normalized[(index - 1) % count], normalized[(index + 1) % count]
        if (
            abs(_cross(previous, a, following)) <= EPSILON
            and (a[0] - previous[0]) * (following[0] - a[0])
            + (a[1] - previous[1]) * (following[1] - a[1]) < 0
        ):
            raise PcdEditError("Polygon edges must not overlap")
        for other in range(index + 2, count):
            if index == 0 and other == count - 1:
                continue
            if _intersects(a, following, normalized[other], normalized[(other + 1) % count]):
                raise PcdEditError("Polygon must not self-intersect or touch itself")
    twice_area = sum(
        a[0] * normalized[(index + 1) % count][1] - normalized[(index + 1) % count][0] * a[1]
        for index, a in enumerate(normalized)
    )
    if abs(twice_area) <= EPSILON:
        raise PcdEditError("Polygon is degenerate or numerically too thin")
    return _CompiledRegion(
        region["kind"], region["selection"], normalized, coordinate_scale, origin_x, origin_y, extent,
        min(x for x, _ in polygon), min(y for _, y in polygon),
        max(x for x, _ in polygon), max(y for _, y in polygon), region["z_min"], region["z_max"],
    )


def validate_regions(regions):
    """Return defensive, JSON-safe normalized regions using the editor limits."""
    if not isinstance(regions, list) or len(regions) > MAX_REGIONS:
        raise PcdEditError(f"regions must be a list of at most {MAX_REGIONS} regions")
    result = []
    for value in regions:
        if not isinstance(value, dict):
            raise PcdEditError("Region must be an object")
        required = {"kind", "polygon", "z_min", "z_max"}
        if set(value) not in (required, required | {"selection"}):
            raise PcdEditError("Region must contain only kind, polygon, z_min, z_max, and optional selection")
        kind, selection = value["kind"], value.get("selection", "inside")
        if kind not in KINDS:
            raise PcdEditError("Region kind must be visibility, localization, keepout")
        if selection not in ("inside", "outside"):
            raise PcdEditError("Region selection must be inside or outside")
        z_min, z_max = _finite(value["z_min"], "z_min"), _finite(value["z_max"], "z_max")
        if z_min > z_max:
            raise PcdEditError("z_min must be less than or equal to z_max")
        if not isinstance(value["polygon"], list) or not 3 <= len(value["polygon"]) <= MAX_VERTICES:
            raise PcdEditError(f"Polygon requires 3 to {MAX_VERTICES} vertices")
        polygon = []
        for vertex in value["polygon"]:
            if not isinstance(vertex, list) or len(vertex) != 2:
                raise PcdEditError("Polygon vertices must be [x, y] pairs")
            polygon.append([_finite(vertex[0], "Polygon x"), _finite(vertex[1], "Polygon y")])
        region = {"kind": kind, "selection": selection, "polygon": polygon, "z_min": z_min, "z_max": z_max}
        _compile_region(region)
        result.append(region)
    return result


def _selection_mask(x, y, z, region):
    """Vectorized membership for finite points and an already compiled region."""
    inside = np.zeros(len(x), dtype=bool)
    indices = np.flatnonzero((x >= region.min_x) & (x <= region.max_x) & (y >= region.min_y) & (y <= region.max_y))
    if len(indices):
        px = (x[indices] / region.coordinate_scale - region.origin_x) / region.extent
        py = (y[indices] / region.coordinate_scale - region.origin_y) / region.extent
        crossing = np.zeros(len(indices), dtype=bool)
        boundary = np.zeros(len(indices), dtype=bool)
        for index, b in enumerate(region.polygon):
            a = region.polygon[index - 1]
            cross = (b[0] - a[0]) * (py - a[1]) - (b[1] - a[1]) * (px - a[0])
            boundary |= (
                (np.abs(cross) <= EPSILON)
                & (px >= min(a[0], b[0]) - EPSILON) & (px <= max(a[0], b[0]) + EPSILON)
                & (py >= min(a[1], b[1]) - EPSILON) & (py <= max(a[1], b[1]) + EPSILON)
            )
            if a[1] != b[1]:
                crossing ^= ((a[1] > py) != (b[1] > py)) & (px < (b[0] - a[0]) * (py - a[1]) / (b[1] - a[1]) + a[0])
        inside[indices] = boundary | crossing
    if region.selection == "outside":
        inside = ~inside
    return inside & (z >= region.z_min) & (z <= region.z_max)


def point_in_region(point, region):
    """Scalar counterpart of core.js pointInRegion, useful to callers/tests."""
    if not isinstance(point, (list, tuple)) or len(point) != 3:
        raise PcdEditError("Point must be [x, y, z]")
    coordinates = [_finite(value, "Point coordinate") for value in point]
    compiled = _compile_region(validate_regions([region])[0])
    return bool(_selection_mask(*(np.array([value]) for value in coordinates), compiled)[0])
