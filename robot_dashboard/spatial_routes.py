"""Revisioned map-frame route storage and hardware-free 2D safety checks.

Spatial routes are authoring artifacts, not motion requests.  The catalog has
no dependency on ROS, Navigation, Mission, ControlManager, or a command topic.
"""

from __future__ import annotations

import copy
import heapq
import hashlib
import json
import math
import os
import re
import secrets
import stat
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence


ROUTE_SCHEMA = "robot-scope.spatial-route.v1"
ROUTE_ID_RE = re.compile(r"^[0-9a-f]{24}$")
REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
ROUTE_MODES = frozenset({"FLEXIBLE", "CORRIDOR", "STRICT"})
AUTHORING_SOURCES = frozenset({"POINT_CLICK", "GHOST_DRIVE", "IMPORT"})
BLOCKED_BEHAVIORS = frozenset({"REPLAN", "STOP", "REQUIRE_OPERATOR"})
MAX_RAW_POSES = 4_096
MAX_EXECUTION_WAYPOINTS = 32
MAX_LABEL_CHARS = 64
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_ROUTE_LENGTH_M = 1_000.0
MAX_VALIDATION_SAMPLES = 100_000
ROBOT_RADIUS_M = 0.25
MAX_VIOLATIONS = 256


class SpatialRouteError(RuntimeError):
    """Base class for bounded route failures."""


class SpatialRouteNotFound(SpatialRouteError):
    pass


class SpatialRouteConflict(SpatialRouteError):
    pass


class SpatialRouteFormatError(SpatialRouteError):
    pass


class SpatialRouteUnavailable(SpatialRouteError):
    pass


class RouteMapGeometry(Protocol):
    map_id: str
    revision: str
    family_id: str | None
    family_revision: str | None
    source_pcd_id: str | None
    source_pcd_revision: str | None
    occupancy_map_id: str | None
    occupancy_map_revision: str | None
    width: int
    height: int
    resolution: float
    origin: tuple[float, float, float]
    occupancy: bytes

    def contains(self, x: float, y: float) -> bool: ...

    def known_free(self, x: float, y: float, *, clearance_radius: float) -> bool: ...


class RouteMapProvider(Protocol):
    def route_geometry(self, map_id: str, expected_revision: str) -> RouteMapGeometry: ...

    def annotations(self, map_id: str) -> Mapping[str, Any]: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _number(value: Any, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpatialRouteFormatError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < minimum or result > maximum:
        raise SpatialRouteFormatError(f"{label} is outside the supported range")
    return round(result, 6)


def _label(value: Any) -> str:
    if not isinstance(value, str):
        raise SpatialRouteFormatError("route label must be text")
    result = unicodedata.normalize("NFC", value).strip()
    if not result or len(result) > MAX_LABEL_CHARS:
        raise SpatialRouteFormatError(f"route label must contain 1 to {MAX_LABEL_CHARS} characters")
    if any(unicodedata.category(char).startswith("C") for char in result):
        raise SpatialRouteFormatError("route label contains unsupported characters")
    return result


def wrap_yaw(value: float) -> float:
    result = (float(value) + math.pi) % (2.0 * math.pi) - math.pi
    return math.pi if result == -math.pi and value > 0 else result


def unwrap_yaws(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    result = [float(values[0])]
    for raw in values[1:]:
        candidate = float(raw)
        previous = result[-1]
        while candidate - previous > math.pi:
            candidate -= 2.0 * math.pi
        while candidate - previous < -math.pi:
            candidate += 2.0 * math.pi
        result.append(candidate)
    return result


def route_length(poses: Sequence[Mapping[str, Any]]) -> float:
    return sum(
        math.hypot(float(right["x"]) - float(left["x"]), float(right["y"]) - float(left["y"]))
        for left, right in zip(poses, poses[1:])
    )


def remove_duplicate_poses(
    poses: Sequence[Mapping[str, Any]], *, distance_epsilon: float = 1e-6
) -> list[dict[str, Any]]:
    if not poses:
        return []
    result = [copy.deepcopy(dict(poses[0]))]
    for pose in poses[1:]:
        if math.hypot(float(pose["x"]) - result[-1]["x"], float(pose["y"]) - result[-1]["y"]) > distance_epsilon:
            result.append(copy.deepcopy(dict(pose)))
        else:
            # Preserve the final authoring intent even for a zero-length turn.
            result[-1] = copy.deepcopy(dict(pose))
    return result


def _point_segment_distance(point: Mapping[str, Any], start: Mapping[str, Any], end: Mapping[str, Any]) -> float:
    dx = float(end["x"]) - float(start["x"])
    dy = float(end["y"]) - float(start["y"])
    if dx == 0.0 and dy == 0.0:
        return math.hypot(float(point["x"]) - float(start["x"]), float(point["y"]) - float(start["y"]))
    ratio = max(0.0, min(1.0, ((float(point["x"]) - float(start["x"])) * dx + (float(point["y"]) - float(start["y"])) * dy) / (dx * dx + dy * dy)))
    return math.hypot(float(point["x"]) - (float(start["x"]) + ratio * dx), float(point["y"]) - (float(start["y"]) + ratio * dy))


def simplify_rdp(poses: Sequence[Mapping[str, Any]], epsilon_m: float) -> list[dict[str, Any]]:
    """Deterministic planar RDP while retaining the exact final orientation."""

    values = remove_duplicate_poses(poses)
    if len(values) <= 2:
        return values
    if not math.isfinite(epsilon_m) or epsilon_m < 0.0:
        raise SpatialRouteFormatError("simplification epsilon is invalid")

    indices = {0, len(values) - 1}
    pending = [(0, len(values) - 1)]
    while pending:
        first, last = pending.pop()
        distance, selected = -1.0, -1
        for index in range(first + 1, last):
            candidate = _point_segment_distance(values[index], values[first], values[last])
            if candidate > distance:
                distance, selected = candidate, index
        if selected >= 0 and distance > epsilon_m:
            indices.add(selected)
            pending.append((first, selected))
            pending.append((selected, last))
    result = [copy.deepcopy(values[index]) for index in sorted(indices)]
    result[-1]["yaw"] = values[-1]["yaw"]
    return result


def enforce_max_segment_length(
    poses: Sequence[Mapping[str, Any]], maximum_m: float
) -> list[dict[str, Any]]:
    if not math.isfinite(maximum_m) or maximum_m <= 0.0:
        raise SpatialRouteFormatError("maximum segment length is invalid")
    values = remove_duplicate_poses(poses)
    if not values:
        return []
    unwrapped = unwrap_yaws([float(item["yaw"]) for item in values])
    result = [copy.deepcopy(values[0])]
    for index, (left, right) in enumerate(zip(values, values[1:])):
        distance = math.hypot(float(right["x"]) - float(left["x"]), float(right["y"]) - float(left["y"]))
        steps = max(1, math.ceil(distance / maximum_m))
        for step in range(1, steps + 1):
            ratio = step / steps
            item = copy.deepcopy(right)
            item["x"] = round(float(left["x"]) + ratio * (float(right["x"]) - float(left["x"])), 6)
            item["y"] = round(float(left["y"]) + ratio * (float(right["y"]) - float(left["y"])), 6)
            item["yaw"] = round(wrap_yaw(unwrapped[index] + ratio * (unwrapped[index + 1] - unwrapped[index])), 6)
            result.append(item)
    result[-1]["yaw"] = values[-1]["yaw"]
    return result


def select_execution_waypoints(
    poses: Sequence[Mapping[str, Any]], *, limit: int = MAX_EXECUTION_WAYPOINTS
) -> list[dict[str, Any]]:
    """Spatially resample an authoring route into a bounded Mission candidate."""

    values = remove_duplicate_poses(poses)
    if len(values) <= limit:
        return values
    if limit < 2:
        raise SpatialRouteFormatError("execution waypoint limit is invalid")
    selected_indices = {0, len(values) - 1}
    pending: list[tuple[float, int, int, int]] = []

    def offer(first: int, last: int) -> None:
        if last - first <= 1:
            return
        distance, selected = -1.0, -1
        for index in range(first + 1, last):
            candidate = _point_segment_distance(values[index], values[first], values[last])
            if candidate > distance:
                distance, selected = candidate, index
        if selected >= 0:
            # Highest error first; the index is the deterministic tie-breaker.
            heapq.heappush(pending, (-distance, selected, first, last))

    offer(0, len(values) - 1)
    while pending and len(selected_indices) < limit:
        _, selected, first, last = heapq.heappop(pending)
        selected_indices.add(selected)
        offer(first, selected)
        offer(selected, last)
    result = [copy.deepcopy(values[index]) for index in sorted(selected_indices)]
    result[-1]["yaw"] = values[-1]["yaw"]
    return result


def _normalize_pose(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SpatialRouteFormatError("route pose must be an object")
    allowed = {"x", "y", "yaw", "z", "arrival_tolerance", "speed_scale", "hold_seconds", "requires_operator_confirmation"}
    if set(value) - allowed or not {"x", "y", "yaw"}.issubset(value):
        raise SpatialRouteFormatError("route pose contains unknown or missing fields")
    result: dict[str, Any] = {
        "x": _number(value.get("x"), "pose x", -1_000_000.0, 1_000_000.0),
        "y": _number(value.get("y"), "pose y", -1_000_000.0, 1_000_000.0),
        "yaw": _number(value.get("yaw"), "pose yaw", -math.pi, math.pi),
        "arrival_tolerance": _number(value.get("arrival_tolerance", 0.35), "arrival tolerance", 0.05, 2.0),
        "speed_scale": _number(value.get("speed_scale", 0.5), "speed scale", 0.05, 1.0),
        "hold_seconds": _number(value.get("hold_seconds", 0.0), "hold seconds", 0.0, 300.0),
    }
    confirmation = value.get("requires_operator_confirmation", False)
    if not isinstance(confirmation, bool):
        raise SpatialRouteFormatError("operator confirmation flag must be boolean")
    result["requires_operator_confirmation"] = confirmation
    if "z" in value and value.get("z") is not None:
        result["z"] = _number(value.get("z"), "visual z", -1_000.0, 1_000.0)
    return result


def _normalize_family(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"family_id", "family_revision", "pcd_map_id", "pcd_revision", "occupancy_map_id", "occupancy_revision"}:
        raise SpatialRouteFormatError("route map family pins are invalid")
    result = {key: str(value[key]) for key in value}
    for key in ("family_id", "pcd_map_id", "occupancy_map_id"):
        if not ROUTE_ID_RE.fullmatch(result[key]):
            raise SpatialRouteFormatError(f"{key} is invalid")
    for key in ("family_revision", "pcd_revision", "occupancy_revision"):
        if not REVISION_RE.fullmatch(result[key]):
            raise SpatialRouteFormatError(f"{key} is invalid")
    return result


def _normalize_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"mode", "corridor_width_m", "blocked_behavior"}:
        raise SpatialRouteFormatError("route policy is invalid")
    if value.get("mode") not in ROUTE_MODES or value.get("blocked_behavior") not in BLOCKED_BEHAVIORS:
        raise SpatialRouteFormatError("route policy value is unsupported")
    return {
        "mode": value["mode"],
        "corridor_width_m": _number(value.get("corridor_width_m"), "corridor width", 0.1, 5.0),
        "blocked_behavior": value["blocked_behavior"],
    }


def normalize_route(
    *, route_id: str, label: Any, map_family: Any, authoring_source: Any,
    parent_revision: str | None, policy: Any, poses: Any, created_at: str | None = None,
) -> dict[str, Any]:
    if not ROUTE_ID_RE.fullmatch(route_id):
        raise SpatialRouteFormatError("route id is invalid")
    if authoring_source not in AUTHORING_SOURCES:
        raise SpatialRouteFormatError("authoring source is unsupported")
    if parent_revision is not None and not REVISION_RE.fullmatch(parent_revision):
        raise SpatialRouteFormatError("parent route revision is invalid")
    if not isinstance(poses, list) or not 1 <= len(poses) <= MAX_RAW_POSES:
        raise SpatialRouteFormatError(f"route poses must contain 1 to {MAX_RAW_POSES} entries")
    normalized_poses = [_normalize_pose(item) for item in poses]
    if route_length(normalized_poses) > MAX_ROUTE_LENGTH_M:
        raise SpatialRouteFormatError("route length exceeds the supported limit")
    timestamp = created_at or _utc_now()
    if not isinstance(timestamp, str) or len(timestamp) > 64 or not timestamp.endswith("Z"):
        raise SpatialRouteFormatError("route creation time is invalid")
    base = {
        "schema": ROUTE_SCHEMA,
        "route_id": route_id,
        "label": _label(label),
        "map_family": _normalize_family(map_family),
        "authoring": {"source": authoring_source, "created_at": timestamp, "parent_revision": parent_revision},
        "policy": _normalize_policy(policy),
        "poses": normalized_poses,
    }
    encoded = json.dumps(base, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_DOCUMENT_BYTES:
        raise SpatialRouteFormatError("route document exceeds the supported size")
    result = {**base, "revision": hashlib.sha256(encoded).hexdigest()}
    return result


def _point_in_polygon(x: float, y: float, vertices: Sequence[Mapping[str, Any]]) -> bool:
    inside = False
    previous = vertices[-1]
    for current in vertices:
        x1, y1 = float(previous["x"]), float(previous["y"])
        x2, y2 = float(current["x"]), float(current["y"])
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if (
            abs(cross) <= 1e-9
            and min(x1, x2) - 1e-9 <= x <= max(x1, x2) + 1e-9
            and min(y1, y2) - 1e-9 <= y <= max(y1, y2) + 1e-9
        ):
            return True
        if ((y1 > y) != (y2 > y)) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
        previous = current
    return inside


def _cell_value(geometry: RouteMapGeometry, x: float, y: float) -> int | None:
    ox, oy, yaw = geometry.origin
    dx, dy = x - ox, y - oy
    cosine, sine = math.cos(yaw), math.sin(yaw)
    local_x = cosine * dx + sine * dy
    local_y = -sine * dx + cosine * dy
    cell_x = math.floor(local_x / geometry.resolution)
    cell_y = math.floor(local_y / geometry.resolution)
    if not (0 <= cell_x < geometry.width and 0 <= cell_y < geometry.height):
        return None
    return geometry.occupancy[cell_y * geometry.width + cell_x]


def validate_route(
    route: Mapping[str, Any], geometry: RouteMapGeometry,
    annotations: Mapping[str, Any], *, robot_radius_m: float = ROBOT_RADIUS_M,
    _include_execution: bool = True,
) -> dict[str, Any]:
    """Validate every pose and sampled segment against one exact 2D snapshot."""

    family = route["map_family"]
    expected = (
        family["family_id"], family["family_revision"], family["pcd_map_id"],
        family["pcd_revision"], family["occupancy_map_id"], family["occupancy_revision"],
    )
    actual = (
        geometry.family_id, geometry.family_revision, geometry.source_pcd_id,
        geometry.source_pcd_revision, geometry.occupancy_map_id, geometry.occupancy_map_revision,
    )
    if expected != actual or geometry.map_id != family["occupancy_map_id"] or geometry.revision != family["occupancy_revision"]:
        raise SpatialRouteConflict("route map family revision changed")
    if annotations.get("map_id") != geometry.map_id or annotations.get("map_revision") != geometry.revision:
        raise SpatialRouteConflict("route annotation map revision changed")
    if not math.isfinite(robot_radius_m) or robot_radius_m <= 0.0:
        raise SpatialRouteFormatError("robot radius is invalid")
    spacing = min(float(geometry.resolution), robot_radius_m / 2.0)
    poses = route["poses"]
    length = route_length(poses)
    estimated_samples = 1 + sum(max(1, math.ceil(math.hypot(right["x"] - left["x"], right["y"] - left["y"]) / spacing)) for left, right in zip(poses, poses[1:]))
    if estimated_samples > MAX_VALIDATION_SAMPLES:
        raise SpatialRouteFormatError("route requires too many validation samples")
    polygons = annotations.get("polygons", []) if isinstance(annotations.get("polygons"), list) else []
    violations: list[dict[str, Any]] = []
    violation_total = 0
    zones: dict[tuple[str, str], dict[str, Any]] = {}
    minimum_clearance = 2.0

    def inspect(x: float, y: float, index: int, segment: int | None) -> None:
        nonlocal minimum_clearance, violation_total
        cell = _cell_value(geometry, x, y)
        kind: str | None = None
        if cell is None:
            kind = "BOUNDARY"
        elif cell == 255:
            kind = "UNKNOWN"
        elif cell != 0:
            kind = "OCCUPIED"
        elif not geometry.known_free(x, y, clearance_radius=robot_radius_m):
            kind = "FOOTPRINT_CLEARANCE"
        # This is a conservative lower-bound estimate.  Do not claim more
        # clearance than the circular footprint check actually proved.
        minimum_clearance = min(
            minimum_clearance,
            robot_radius_m if kind is None else 0.0,
        )
        for polygon in polygons:
            vertices = polygon.get("vertices")
            if not isinstance(vertices, list) or len(vertices) < 3 or not _point_in_polygon(x, y, vertices):
                continue
            zone_type = polygon.get("type")
            if zone_type == "KEEP_OUT":
                kind = kind or "KEEP_OUT"
            elif zone_type in {"SLOW_ZONE", "WAIT_ZONE"}:
                key = (str(zone_type), str(polygon.get("id", "")))
                zones.setdefault(key, {"type": zone_type, "id": polygon.get("id"), "name": polygon.get("name"), "first_pose_index": index})
        if kind is not None:
            violation_total += 1
            if len(violations) < MAX_VIOLATIONS:
                item: dict[str, Any] = {"index": index, "kind": kind, "x": round(x, 6), "y": round(y, 6)}
                if segment is not None:
                    item["segment"] = segment
                violations.append(item)

    inspect(float(poses[0]["x"]), float(poses[0]["y"]), 0, None)
    for segment, (left, right) in enumerate(zip(poses, poses[1:])):
        distance = math.hypot(float(right["x"]) - float(left["x"]), float(right["y"]) - float(left["y"]))
        steps = max(1, math.ceil(distance / spacing))
        for step in range(1, steps + 1):
            ratio = step / steps
            inspect(
                float(left["x"]) + ratio * (float(right["x"]) - float(left["x"])),
                float(left["y"]) + ratio * (float(right["y"]) - float(left["y"])),
                segment + 1,
                segment,
            )
    valid = not violations
    execution = select_execution_waypoints(poses)
    execution_valid = valid
    if _include_execution and execution != poses:
        projected = dict(route)
        projected["poses"] = execution
        execution_valid = validate_route(
            projected,
            geometry,
            annotations,
            robot_radius_m=robot_radius_m,
            _include_execution=False,
        )["valid"]
    mode_eligible = route["policy"]["mode"] == "FLEXIBLE"
    eligible = bool(valid and execution_valid and mode_eligible)
    if not valid:
        execution_reason = "ROUTE_INVALID"
    elif not execution_valid:
        execution_reason = "SIMPLIFIED_ROUTE_INVALID"
    elif not mode_eligible:
        execution_reason = "MODE_AUTHORING_ONLY"
    else:
        execution_reason = None
    return {
        "valid": valid,
        "pose_count": len(poses),
        "segment_count": max(0, len(poses) - 1),
        "sample_count": estimated_samples,
        "length_m": round(length, 6),
        "minimum_clearance_m": round(minimum_clearance if poses else 0.0, 6),
        "violations": violations,
        "violation_count": violation_total,
        "violations_truncated": violation_total > len(violations),
        "zones": list(zones.values()),
        "annotation_revision": annotations.get("annotation_revision"),
        "execution": {
            "eligible": eligible if _include_execution else False,
            "waypoint_count": len(execution),
            "maximum_waypoints": MAX_EXECUTION_WAYPOINTS,
            "mission_created": False,
            "route_executed": False,
            "reason": execution_reason if _include_execution else "INTERNAL_VALIDATION_ONLY",
        },
    }


def _safe_root(root: Path) -> Path:
    requested = Path(root).expanduser()
    if not requested.is_absolute() or requested == Path("/"):
        raise SpatialRouteUnavailable("route catalog root must be a non-root absolute path")
    if requested.is_symlink():
        raise SpatialRouteUnavailable("route catalog root cannot be a symlink")
    # Canonicalize platform aliases such as macOS /var -> /private/var before
    # creating or retaining the trusted, non-HTTP-configurable private root.
    requested = requested.resolve(strict=False)
    requested.mkdir(parents=True, exist_ok=True, mode=0o700)
    if requested.is_symlink() or not requested.is_dir() or requested.resolve(strict=True) != requested:
        raise SpatialRouteUnavailable("route catalog root must be a real directory")
    info = requested.stat()
    if info.st_uid != os.geteuid():
        raise SpatialRouteUnavailable("route catalog root must be owned by the service user")
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise SpatialRouteUnavailable("route catalog root must have mode 0700")
    return requested


class SpatialRouteCatalog:
    """Private immutable revision store with an atomic current pointer."""

    def __init__(
        self, root: Path, maps: RouteMapProvider, *,
        identifier_factory: Callable[[], str] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.root = _safe_root(Path(root))
        self.maps = maps
        self._identifier_factory = identifier_factory or (lambda: secrets.token_hex(12))
        self._clock = clock or _utc_now
        self._lock = threading.RLock()

    def _current_path(self, route_id: str) -> Path:
        if not ROUTE_ID_RE.fullmatch(route_id):
            raise SpatialRouteNotFound("spatial route not found")
        return self.root / f"{route_id}.current"

    def _new_identifier(self) -> str:
        route_id = self._identifier_factory()
        if not isinstance(route_id, str) or not ROUTE_ID_RE.fullmatch(route_id):
            raise SpatialRouteUnavailable("route identifier source is invalid")
        if self._current_path(route_id).exists() or any(self.root.glob(f"{route_id}.*.json")):
            raise SpatialRouteConflict("route identifier already exists")
        return route_id

    def _revision_path(self, route_id: str, revision: str) -> Path:
        if not ROUTE_ID_RE.fullmatch(route_id) or not REVISION_RE.fullmatch(revision):
            raise SpatialRouteNotFound("spatial route not found")
        return self.root / f"{route_id}.{revision}.json"

    @staticmethod
    def _regular(path: Path, *, max_bytes: int = MAX_DOCUMENT_BYTES + 262_144) -> bytes:
        if path.is_symlink() or not path.is_file():
            raise SpatialRouteUnavailable("route catalog entry is unavailable")
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= max_bytes:
            raise SpatialRouteUnavailable("route catalog entry is invalid")
        return path.read_bytes()

    def _current_revision(self, route_id: str) -> str:
        try:
            value = self._regular(self._current_path(route_id), max_bytes=65).decode("ascii").strip()
        except (OSError, UnicodeError, SpatialRouteUnavailable) as exc:
            raise SpatialRouteNotFound("spatial route not found") from exc
        if not REVISION_RE.fullmatch(value):
            raise SpatialRouteUnavailable("route current revision is invalid")
        return value

    def _read(self, route_id: str, revision: str | None = None) -> dict[str, Any]:
        selected = revision or self._current_revision(route_id)
        try:
            value = json.loads(self._regular(self._revision_path(route_id, selected)).decode("utf-8"))
        except SpatialRouteError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SpatialRouteUnavailable("route revision is unreadable") from exc
        if not isinstance(value, Mapping) or set(value) != {"route", "validation"}:
            raise SpatialRouteUnavailable("route revision wrapper is invalid")
        route = value.get("route")
        if not isinstance(route, Mapping) or route.get("route_id") != route_id or route.get("revision") != selected:
            raise SpatialRouteUnavailable("route revision identity is invalid")
        rebuilt = normalize_route(
            route_id=route_id, label=route.get("label"), map_family=route.get("map_family"),
            authoring_source=route.get("authoring", {}).get("source") if isinstance(route.get("authoring"), Mapping) else None,
            parent_revision=route.get("authoring", {}).get("parent_revision") if isinstance(route.get("authoring"), Mapping) else None,
            policy=route.get("policy"), poses=route.get("poses"),
            created_at=route.get("authoring", {}).get("created_at") if isinstance(route.get("authoring"), Mapping) else None,
        )
        if dict(route) != rebuilt:
            raise SpatialRouteUnavailable("route revision content is invalid")
        if not isinstance(value.get("validation"), Mapping):
            raise SpatialRouteUnavailable("route validation snapshot is invalid")
        return {"route": rebuilt, "validation": copy.deepcopy(dict(value["validation"]))}

    def _validate(self, route: Mapping[str, Any]) -> dict[str, Any]:
        family = route["map_family"]
        try:
            geometry = self.maps.route_geometry(family["occupancy_map_id"], family["occupancy_revision"])
            annotations = self.maps.annotations(family["occupancy_map_id"])
            return validate_route(route, geometry, annotations)
        except SpatialRouteError:
            raise
        except Exception as exc:
            raise SpatialRouteConflict("exact route map family is unavailable") from exc

    def _write_exclusive(self, path: Path, payload: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short route write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _publish(self, route: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
        route_id, revision = route["route_id"], route["revision"]
        target = self._revision_path(route_id, revision)
        temporary = self.root / f".{route_id}.current.{secrets.token_hex(8)}"
        payload = json.dumps({"route": route, "validation": validation}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(payload) > MAX_DOCUMENT_BYTES + 262_144:
            raise SpatialRouteFormatError("route result exceeds the supported size")
        try:
            if not target.exists():
                self._write_exclusive(target, payload)
            elif self._regular(target) != payload:
                raise SpatialRouteConflict("route revision collision")
            self._write_exclusive(temporary, (revision + "\n").encode("ascii"))
            os.replace(temporary, self._current_path(route_id))
            directory = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except SpatialRouteError:
            temporary.unlink(missing_ok=True)
            raise
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise SpatialRouteUnavailable("route revision could not be published") from exc
        return {"route": copy.deepcopy(dict(route)), "validation": copy.deepcopy(dict(validation))}

    def list_snapshot(self) -> dict[str, Any]:
        with self._lock:
            routes = []
            for path in sorted(self.root.glob("*.current"))[:2_000]:
                route_id = path.name.removesuffix(".current")
                try:
                    item = self._read(route_id)
                except SpatialRouteError:
                    continue
                route, validation = item["route"], item["validation"]
                routes.append({
                    "route_id": route_id, "revision": route["revision"], "label": route["label"],
                    "map_family": copy.deepcopy(route["map_family"]), "authoring": copy.deepcopy(route["authoring"]),
                    "policy": copy.deepcopy(route["policy"]), "pose_count": len(route["poses"]),
                    "valid": validation.get("valid") is True,
                    "execution_eligible": validation.get("execution", {}).get("eligible") is True,
                })
            return {"schema": ROUTE_SCHEMA, "count": len(routes), "routes": routes, "limits": {"max_raw_poses": MAX_RAW_POSES, "max_execution_waypoints": MAX_EXECUTION_WAYPOINTS, "max_document_bytes": MAX_DOCUMENT_BYTES}, "motion_authority": "NONE"}

    def detail(self, route_id: str) -> dict[str, Any]:
        with self._lock:
            return self._read(route_id)

    def create(self, *, label: Any, map_family: Any, authoring_source: Any, policy: Any, poses: Any) -> dict[str, Any]:
        with self._lock:
            route_id = self._new_identifier()
            route = normalize_route(route_id=route_id, label=label, map_family=map_family, authoring_source=authoring_source, parent_revision=None, policy=policy, poses=poses, created_at=self._clock())
            return self._publish(route, self._validate(route))

    def update(self, route_id: str, *, base_revision: str, label: Any, map_family: Any, authoring_source: Any, policy: Any, poses: Any) -> dict[str, Any]:
        with self._lock:
            if self._current_revision(route_id) != base_revision:
                raise SpatialRouteConflict("route changed; reload it before saving")
            route = normalize_route(route_id=route_id, label=label, map_family=map_family, authoring_source=authoring_source, parent_revision=base_revision, policy=policy, poses=poses, created_at=self._clock())
            return self._publish(route, self._validate(route))

    def copy(self, route_id: str, *, base_revision: str, label: Any) -> dict[str, Any]:
        with self._lock:
            current = self._read(route_id)
            if current["route"]["revision"] != base_revision:
                raise SpatialRouteConflict("route changed; reload it before copying")
            source = current["route"]
            new_id = self._new_identifier()
            route = normalize_route(route_id=new_id, label=label, map_family=source["map_family"], authoring_source="IMPORT", parent_revision=base_revision, policy=source["policy"], poses=source["poses"], created_at=self._clock())
            return self._publish(route, self._validate(route))

    def delete(self, route_id: str, *, base_revision: str) -> dict[str, Any]:
        with self._lock:
            if self._current_revision(route_id) != base_revision:
                raise SpatialRouteConflict("route changed; reload it before deleting")
            current = self._current_path(route_id)
            try:
                current.unlink()
                directory = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except OSError as exc:
                raise SpatialRouteUnavailable("route could not be deleted") from exc
            # Immutable revision files remain private for audit/recovery and no
            # longer appear in the active route catalog.
            return {"route_id": route_id, "revision": base_revision, "deleted": True, "route_executed": False}
