"""Single-owner stationary 3D relocalization candidate jobs.

The manager is deliberately transport and ROS independent.  A future D2 live
owner must supply the fixed-source collector and immutable map snapshotter;
this module never acquires control authority or applies a candidate.
"""

from __future__ import annotations

import copy
import hashlib
import math
import os
import secrets
import shutil
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from .models import RegistrationContractError
from .process_adapter import RegistrationCanceled, RegistrationProcessError


PROFILE = "go2-xt16-wireless-competition-fastlio"
SOURCE_TOPIC = "/cloud_registered"
SOURCE_FRAME = "camera_init"
COLLECTION_DURATION_S = 2.5
MAX_COLLECTION_DURATION_S = 5.0
MIN_FRAMES = 20
MAX_FRAMES = 50
MAX_RAW_POINTS = 1_000_000
MIN_FILTERED_POINTS = 500
MAX_FILTERED_POINTS = 100_000
REFERENCE_PREVIEW_LIMIT = 50_000
CURRENT_PREVIEW_LIMIT = 30_000
ALIGNED_PREVIEW_LIMIT = 30_000
ROBOT_CLEARANCE_M = 0.35
MAX_STATIONARY_TRANSLATION_M = 0.005
MAX_STATIONARY_YAW_RAD = 0.01
MAX_STATIONARY_TWIST_MPS = 0.01
MAX_STATIONARY_IMU_RPS = 0.05
MAX_JOBS_RETAINED = 8
TERMINAL_STATES = frozenset({"candidate_ready", "ambiguous", "rejected", "failed"})


class RelocalizationError(RuntimeError):
    """Base class for fail-closed relocalization job errors."""


class RelocalizationBusy(RelocalizationError):
    pass


class RelocalizationConflict(RelocalizationError):
    pass


class RelocalizationUnavailable(RelocalizationError):
    pass


class RelocalizationNotFound(RelocalizationError):
    pass


class RelocalizationValidationError(RelocalizationError):
    pass


class Geometry(Protocol):
    def contains(self, x: float, y: float) -> bool: ...
    def known_free(self, x: float, y: float, *, clearance_radius: float) -> bool: ...


@dataclass(frozen=True)
class RelocalizationMapBundle:
    family_id: str
    family_revision: str
    map_id: str
    map_revision: str
    source_pcd_id: str
    source_pcd_revision: str
    reference_pcd: Path
    reference_points: int
    geometry: Geometry
    annotations: Mapping[str, Any]


@dataclass(frozen=True)
class LiveCollection:
    topic: str
    frame_id: str
    duration_s: float
    frame_stamps_ns: tuple[int, ...]
    raw_points: int
    points: tuple[tuple[float, float, float], ...]
    base_pose_odom: tuple[float, float, float]
    controller_translation_delta_m: float
    controller_yaw_delta_rad: float
    maximum_fastlio_twist_mps: float
    maximum_imu_angular_rate_rps: float
    publisher_count: int = 1


class Collector(Protocol):
    def collect(self, cancel_event: threading.Event) -> LiveCollection: ...


class Registration(Protocol):
    def run(
        self, payload: Any, *, cancel_event: threading.Event | None = None
    ) -> dict[str, Any]: ...


Snapshotter = Callable[[str, str, str, str, Path], RelocalizationMapBundle]
CurrentChecker = Callable[[RelocalizationMapBundle], bool]
SafetyProvider = Callable[[], Mapping[str, Any]]


class StationaryRelocalizationManager:
    """Own exactly one generation-fenced candidate job at a time."""

    def __init__(
        self,
        runtime_root: Path,
        *,
        snapshotter: Snapshotter,
        current_checker: CurrentChecker,
        collector: Collector,
        registration: Registration,
        safety_provider: SafetyProvider,
        global_search_enabled: bool = False,
    ) -> None:
        root = Path(runtime_root)
        if not root.is_absolute() or root.is_symlink():
            raise RelocalizationValidationError("runtime root must be an absolute real directory")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        resolved = root.resolve(strict=True)
        if not resolved.is_dir():
            raise RelocalizationValidationError("runtime root is unavailable")
        os.chmod(resolved, 0o700)
        self._root = resolved
        self._snapshotter = snapshotter
        self._current_checker = current_checker
        self._collector = collector
        self._registration = registration
        self._safety_provider = safety_provider
        self._global_search_enabled = bool(global_search_enabled)
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._active_job_id: str | None = None
        self._generation = 0
        self._cancel_events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}

    def start(self, request: Mapping[str, Any]) -> dict[str, Any]:
        normalized = _parse_request(request, self._global_search_enabled)
        _require_stationary_preflight(self._safety_provider())
        with self._lock:
            if self._active_job_id is not None:
                raise RelocalizationBusy("a relocalization job is already active")
            self._generation += 1
            generation = self._generation
            job_id = secrets.token_hex(12)
            job = {
                "schema": "robot-scope.relocalization-job.v1",
                "job_id": job_id,
                "generation": generation,
                "state": "preflighting",
                "message": "stationary preflight passed",
                "map_id": normalized["map_id"],
                "map_revision": normalized["map_revision"],
                "source_pcd_id": normalized["source_pcd_id"],
                "source_pcd_revision": normalized["source_pcd_revision"],
                "family_id": None,
                "family_revision": None,
                "source": {"topic": SOURCE_TOPIC, "frame_id": SOURCE_FRAME},
                "collection": None,
                "candidates": [],
                "candidate_applied": False,
                "created_monotonic": time.monotonic(),
                "updated_monotonic": time.monotonic(),
                "error": None,
                "preview_layers": [],
            }
            self._jobs[job_id] = job
            self._active_job_id = job_id
            cancel_event = threading.Event()
            self._cancel_events[job_id] = cancel_event
            worker = threading.Thread(
                target=self._run,
                args=(job_id, generation, normalized, cancel_event),
                name=f"robot-scope-relocalization-{generation}",
                daemon=True,
            )
            self._threads[job_id] = worker
            worker.start()
            return self._public(job)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active = self._jobs.get(self._active_job_id or "")
            latest = next(reversed(self._jobs.values()), None) if self._jobs else None
            return {
                "schema": "robot-scope.relocalization.v1",
                "active": self._public(active) if active is not None else None,
                "latest": self._public(latest) if latest is not None else None,
                "limits": {
                    "collection_duration_s": COLLECTION_DURATION_S,
                    "maximum_duration_s": MAX_COLLECTION_DURATION_S,
                    "top_k": 3,
                    "candidate_apply_supported": False,
                },
            }

    def job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(_job_id(job_id))
            if job is None:
                raise RelocalizationNotFound("relocalization job was not found")
            return self._public(job)

    def preview(self, job_id: str, layer: str) -> dict[str, Any]:
        if layer not in {"reference", "current", "aligned"}:
            raise RelocalizationValidationError("preview layer is invalid")
        with self._lock:
            job = self._jobs.get(_job_id(job_id))
            if job is None:
                raise RelocalizationNotFound("relocalization job was not found")
            preview = job.get("_previews", {}).get(layer)
            if preview is None:
                raise RelocalizationConflict("preview layer is not ready")
            result = copy.deepcopy(preview)
            result["job_id"] = job_id
            result["generation"] = job["generation"]
            return result

    def cancel(self, job_id: str) -> dict[str, Any]:
        identifier = _job_id(job_id)
        with self._lock:
            job = self._jobs.get(identifier)
            if job is None:
                raise RelocalizationNotFound("relocalization job was not found")
            if job["state"] in TERMINAL_STATES:
                return self._public(job)
            job["state"] = "canceling"
            job["message"] = "cancel requested"
            job["updated_monotonic"] = time.monotonic()
            self._cancel_events[identifier].set()
            return self._public(job)

    def close(self) -> None:
        with self._lock:
            events = list(self._cancel_events.values())
            threads = list(self._threads.values())
        for event in events:
            event.set()
        for thread in threads:
            thread.join(timeout=6.0)

    def _run(
        self,
        job_id: str,
        generation: int,
        request: dict[str, Any],
        cancel_event: threading.Event,
    ) -> None:
        job_dir = self._root / f"job-{generation:08d}-{job_id}"
        try:
            job_dir.mkdir(mode=0o700)
            bundle = self._snapshotter(
                request["map_id"], request["map_revision"],
                request["source_pcd_id"], request["source_pcd_revision"], job_dir,
            )
            self._transition(job_id, generation, "collecting", "collecting fixed live source")
            collection = self._collector.collect(cancel_event)
            _validate_collection(collection)
            self._check_cancel(cancel_event)
            query_path = job_dir / "current.pcd"
            _write_binary_pcd(query_path, collection.points)
            self._transition(job_id, generation, "preprocessing", "validating bounded submap")
            seed = request["seed"]
            payload = {
                "reference_pcd": str(bundle.reference_pcd),
                "query_pcd": str(query_path),
                "seed": {
                    "x": seed["x"], "y": seed["y"], "yaw": seed["yaw"],
                    "radius_m": seed["radius_m"],
                    "yaw_range_rad": seed["yaw_half_range"],
                },
                "limits": {
                    "max_reference_points": 1_000_000,
                    "max_query_points": MAX_FILTERED_POINTS,
                    "timeout_ms": 15_000,
                },
            }
            self._transition(job_id, generation, "coarse_search", "bounded coarse search")
            self._transition(job_id, generation, "refining", "bounded candidate refinement")
            result = self._registration.run(payload, cancel_event=cancel_event)
            self._check_cancel(cancel_event)
            if not self._current_checker(bundle):
                raise RelocalizationConflict("map family or revision changed during registration")
            candidates = _validate_candidates(result, collection, bundle)
            previews = _build_previews(bundle, collection, candidates)
            state = _terminal_state(candidates)
            with self._lock:
                job = self._owned(job_id, generation)
                job.update({
                    "state": state,
                    "message": "candidate review is ready" if state == "candidate_ready" else state,
                    "family_id": bundle.family_id,
                    "family_revision": bundle.family_revision,
                    "collection": _collection_public(collection, bundle.reference_points),
                    "candidates": candidates,
                    "preview_layers": sorted(previews),
                    "_previews": previews,
                    "updated_monotonic": time.monotonic(),
                })
        except (RegistrationCanceled, _Canceled):
            self._fail(job_id, generation, "relocalization job canceled", canceled=True)
        except (
            RelocalizationError,
            RegistrationContractError,
            RegistrationProcessError,
            OSError,
            ValueError,
        ) as exc:
            self._fail(
                job_id,
                generation,
                str(exc)[:512] or "relocalization job failed",
                canceled=cancel_event.is_set(),
            )
        except Exception:
            self._fail(job_id, generation, "relocalization job failed")
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)
            with self._lock:
                if self._active_job_id == job_id:
                    self._active_job_id = None
                self._cancel_events.pop(job_id, None)
                self._threads.pop(job_id, None)
                while len(self._jobs) > MAX_JOBS_RETAINED:
                    oldest = next(iter(self._jobs))
                    if oldest == self._active_job_id:
                        break
                    self._jobs.pop(oldest, None)

    def _transition(self, job_id: str, generation: int, state: str, message: str) -> None:
        with self._lock:
            job = self._owned(job_id, generation)
            if job["state"] == "canceling":
                raise _Canceled()
            job["state"] = state
            job["message"] = message
            job["updated_monotonic"] = time.monotonic()

    def _owned(self, job_id: str, generation: int) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if job is None or job["generation"] != generation:
            raise RelocalizationConflict("relocalization generation lost ownership")
        return job

    def _fail(self, job_id: str, generation: int, reason: str, *, canceled: bool = False) -> None:
        with self._lock:
            try:
                job = self._owned(job_id, generation)
            except RelocalizationConflict:
                return
            job["state"] = "failed"
            job["message"] = "canceled" if canceled else "failed"
            job["error"] = reason
            job["updated_monotonic"] = time.monotonic()

    @staticmethod
    def _check_cancel(cancel_event: threading.Event) -> None:
        if cancel_event.is_set():
            raise _Canceled()

    @staticmethod
    def _public(job: Mapping[str, Any] | None) -> dict[str, Any]:
        if job is None:
            return {}
        hidden = {"_previews", "created_monotonic", "updated_monotonic"}
        return copy.deepcopy({key: value for key, value in job.items() if key not in hidden})


class _Canceled(RuntimeError):
    pass


def _parse_request(payload: Mapping[str, Any], global_search_enabled: bool) -> dict[str, Any]:
    expected = {"map_id", "map_revision", "source_pcd_id", "source_pcd_revision", "seed"}
    if not isinstance(payload, Mapping) or set(payload) != expected:
        raise RelocalizationValidationError("relocalization request schema is invalid")
    for key, length in (("map_id", 24), ("source_pcd_id", 24), ("map_revision", 64), ("source_pcd_revision", 64)):
        value = payload.get(key)
        if not isinstance(value, str) or len(value) != length or any(c not in "0123456789abcdef" for c in value):
            raise RelocalizationValidationError(f"{key} is invalid")
    seed = payload.get("seed")
    if not isinstance(seed, Mapping) or set(seed) != {"mode", "x", "y", "yaw", "radius_m", "yaw_half_range"}:
        raise RelocalizationValidationError("seed schema is invalid")
    mode = seed.get("mode")
    if mode not in {"REGION", "POSE", "NONE"}:
        raise RelocalizationValidationError("seed mode is invalid")
    if mode == "NONE" and not global_search_enabled:
        raise RelocalizationValidationError("global relocalization search is disabled")
    normalized_seed: dict[str, Any] = {"mode": mode}
    for key, minimum, maximum in (
        ("x", -1_000_000.0, 1_000_000.0), ("y", -1_000_000.0, 1_000_000.0),
        ("yaw", -math.pi, math.pi), ("radius_m", 0.0, 10.0),
        ("yaw_half_range", 0.0, math.pi),
    ):
        value = seed.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not minimum <= float(value) <= maximum:
            raise RelocalizationValidationError(f"seed {key} is invalid")
        normalized_seed[key] = float(value)
    return {key: str(payload[key]) for key in expected - {"seed"}} | {"seed": normalized_seed}


def _require_stationary_preflight(value: Mapping[str, Any]) -> None:
    required = {
        "profile": PROFILE, "stationary": True, "control_disarmed": True,
        "control_lease_active": False, "navigation_lease_active": False,
        "deadman": False, "goal_idle": True, "mapping_active": False,
        "dataset_active": False, "physical_safety_ready": True,
        "source_topic": SOURCE_TOPIC, "source_frame": SOURCE_FRAME,
        "source_publishers": 1, "source_fresh": True, "source_qos_valid": True,
    }
    if not isinstance(value, Mapping):
        raise RelocalizationUnavailable("motion-related state is unavailable")
    for key, expected in required.items():
        if value.get(key) != expected:
            raise RelocalizationUnavailable(f"stationary preflight failed: {key}")
    velocity = value.get("velocity")
    if not isinstance(velocity, Mapping) or any(velocity.get(axis) != 0.0 for axis in ("vx", "vy", "wz")):
        raise RelocalizationUnavailable("stationary preflight failed: exact-zero velocity")


def _validate_collection(value: LiveCollection) -> None:
    numeric = (
        value.duration_s, value.controller_translation_delta_m,
        value.controller_yaw_delta_rad, value.maximum_fastlio_twist_mps,
        value.maximum_imu_angular_rate_rps, *value.base_pose_odom,
    )
    if not all(math.isfinite(item) for item in numeric):
        raise RelocalizationValidationError("collection contains non-finite evidence")
    if value.topic != SOURCE_TOPIC or value.frame_id != SOURCE_FRAME or value.publisher_count != 1:
        raise RelocalizationValidationError("collection source identity changed")
    if not 2.0 <= value.duration_s <= MAX_COLLECTION_DURATION_S:
        raise RelocalizationValidationError("collection duration is invalid")
    if not MIN_FRAMES <= len(value.frame_stamps_ns) <= MAX_FRAMES:
        raise RelocalizationValidationError("collection frame count is invalid")
    if any(current <= previous for previous, current in zip(value.frame_stamps_ns, value.frame_stamps_ns[1:])):
        raise RelocalizationValidationError("collection stamps are duplicate or non-increasing")
    if value.raw_points <= 0 or value.raw_points > MAX_RAW_POINTS:
        raise RelocalizationValidationError("collection raw point count is invalid")
    if not MIN_FILTERED_POINTS <= len(value.points) <= MAX_FILTERED_POINTS:
        raise RelocalizationValidationError("collection filtered point count is invalid")
    if any(len(point) != 3 or not all(math.isfinite(item) for item in point) for point in value.points):
        raise RelocalizationValidationError("collection contains invalid points")
    if (
        value.controller_translation_delta_m > MAX_STATIONARY_TRANSLATION_M
        or value.controller_yaw_delta_rad > MAX_STATIONARY_YAW_RAD
        or value.maximum_fastlio_twist_mps > MAX_STATIONARY_TWIST_MPS
        or value.maximum_imu_angular_rate_rps > MAX_STATIONARY_IMU_RPS
    ):
        raise RelocalizationConflict("robot moved during stationary collection")


def _write_binary_pcd(path: Path, points: Sequence[tuple[float, float, float]]) -> None:
    header = (
        "# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\n"
        f"COUNT 1 1 1\nWIDTH {len(points)}\nHEIGHT 1\nPOINTS {len(points)}\nDATA binary\n"
    ).encode("ascii")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(header)
            for point in points:
                stream.write(struct.pack("<fff", *point))
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def _compose_pose(map_odom: Sequence[float], odom_base: Sequence[float]) -> tuple[float, float, float]:
    cosine, sine = math.cos(map_odom[2]), math.sin(map_odom[2])
    return (
        map_odom[0] + cosine * odom_base[0] - sine * odom_base[1],
        map_odom[1] + sine * odom_base[0] + cosine * odom_base[1],
        math.atan2(math.sin(map_odom[2] + odom_base[2]), math.cos(map_odom[2] + odom_base[2])),
    )


def _validate_candidates(
    result: Mapping[str, Any], collection: LiveCollection, bundle: RelocalizationMapBundle
) -> list[dict[str, Any]]:
    raw = result.get("results")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 3:
        raise RelocalizationValidationError("registration result is unavailable")
    candidates = []
    for item in raw:
        pose = item.get("pose", {}) if isinstance(item, Mapping) else {}
        map_odom = tuple(float(pose.get(key)) for key in ("x", "y", "yaw"))
        map_base = _compose_pose(map_odom, collection.base_pose_odom)
        reasons: list[str] = []
        confidence = str(item.get("confidence"))
        if confidence == "REJECTED":
            reasons.append("registration_rejected")
        if not bundle.geometry.contains(map_base[0], map_base[1]):
            reasons.append("outside_occupancy_map")
        elif not bundle.geometry.known_free(map_base[0], map_base[1], clearance_radius=ROBOT_CLEARANCE_M):
            reasons.append("footprint_not_known_free")
        zone_labels = _zone_labels(bundle.annotations, map_base, ROBOT_CLEARANCE_M)
        if "KEEP_OUT" in zone_labels:
            reasons.append("keep_out")
        state = "REJECTED" if reasons else confidence
        candidates.append({
            "rank": int(item["rank"]),
            "state": state,
            "pose": {"x": map_base[0], "y": map_base[1], "yaw": map_base[2]},
            "transform_map_odom": {"x": map_odom[0], "y": map_odom[1], "yaw": map_odom[2]},
            "metrics": dict(item["metrics"]),
            "ambiguity_margin": float(item["ambiguity_margin"]),
            "zones": [zone for zone in zone_labels if zone != "KEEP_OUT"],
            "reasons": reasons,
            "out_of_plane_correction": {
                "estimated": False,
                "z": None,
                "roll": None,
                "pitch": None,
            },
        })
    if len(candidates) > 1:
        top, second = candidates[0], candidates[1]
        separation = math.hypot(top["pose"]["x"] - second["pose"]["x"], top["pose"]["y"] - second["pose"]["y"])
        yaw_separation = abs(math.atan2(math.sin(top["pose"]["yaw"] - second["pose"]["yaw"]), math.cos(top["pose"]["yaw"] - second["pose"]["yaw"])))
        if top["state"] != "REJECTED" and top["ambiguity_margin"] < 0.05 and (separation > 0.25 or yaw_separation > 0.15):
            top["state"] = "AMBIGUOUS"
            top["reasons"].append("spatially_distinct_second_candidate")
    return candidates


def _zone_labels(document: Mapping[str, Any], pose: Sequence[float], radius: float) -> list[str]:
    labels = []
    polygons = document.get("polygons", []) if isinstance(document, Mapping) else []
    if not isinstance(polygons, list):
        return labels
    for polygon in polygons[:32]:
        if not isinstance(polygon, Mapping) or polygon.get("type") not in {"KEEP_OUT", "SLOW_ZONE", "WAIT_ZONE"}:
            continue
        vertices = polygon.get("vertices")
        if isinstance(vertices, list) and 3 <= len(vertices) <= 64 and _circle_intersects_polygon(pose[0], pose[1], radius, vertices):
            labels.append(str(polygon["type"]))
    return sorted(set(labels))


def _circle_intersects_polygon(x: float, y: float, radius: float, vertices: Sequence[Any]) -> bool:
    points = [(float(item["x"]), float(item["y"])) for item in vertices if isinstance(item, Mapping) and "x" in item and "y" in item]
    if len(points) != len(vertices):
        return True
    inside = False
    previous = points[-1]
    for current in points:
        if (current[1] > y) != (previous[1] > y):
            crossing = (previous[0] - current[0]) * (y - current[1]) / (previous[1] - current[1]) + current[0]
            if x < crossing:
                inside = not inside
        if _point_segment_distance(x, y, previous, current) <= radius:
            return True
        previous = current
    return inside


def _point_segment_distance(x: float, y: float, start: tuple[float, float], end: tuple[float, float]) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    denominator = dx * dx + dy * dy
    scale = 0.0 if denominator == 0.0 else max(0.0, min(1.0, ((x - start[0]) * dx + (y - start[1]) * dy) / denominator))
    return math.hypot(x - (start[0] + scale * dx), y - (start[1] + scale * dy))


def _terminal_state(candidates: Sequence[Mapping[str, Any]]) -> str:
    if not candidates or candidates[0].get("state") == "REJECTED":
        return "rejected"
    if candidates[0].get("state") == "AMBIGUOUS":
        return "ambiguous"
    return "candidate_ready"


def _collection_public(collection: LiveCollection, reference_points: int) -> dict[str, Any]:
    return {
        "duration_s": collection.duration_s,
        "frames": len(collection.frame_stamps_ns),
        "raw_points": collection.raw_points,
        "filtered_points": len(collection.points),
        "reference_points": reference_points,
        "source_topic": collection.topic,
        "source_frame": collection.frame_id,
        "local_origin": "odom_at_collection_start",
    }


def _build_previews(
    bundle: RelocalizationMapBundle,
    collection: LiveCollection,
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    reference = _read_binary_pcd_preview(bundle.reference_pcd, REFERENCE_PREVIEW_LIMIT)
    current = _sample_points(collection.points, CURRENT_PREVIEW_LIMIT)
    aligned: list[tuple[float, float, float]] = []
    if candidates:
        transform = candidates[0]["transform_map_odom"]
        cosine, sine = math.cos(transform["yaw"]), math.sin(transform["yaw"])
        aligned = [
            (transform["x"] + cosine * x - sine * y, transform["y"] + sine * x + cosine * y, z)
            for x, y, z in _sample_points(collection.points, ALIGNED_PREVIEW_LIMIT)
        ]
    return {
        "reference": _preview(bundle, "reference", "map", reference, REFERENCE_PREVIEW_LIMIT),
        "current": _preview(bundle, "current", SOURCE_FRAME, current, CURRENT_PREVIEW_LIMIT),
        "aligned": _preview(bundle, "aligned", "map", aligned, ALIGNED_PREVIEW_LIMIT),
    }


def _preview(bundle: RelocalizationMapBundle, layer: str, frame: str, points: Sequence[tuple[float, float, float]], limit: int) -> dict[str, Any]:
    flattened = [round(float(value), 4) for point in points for value in point]
    digest = hashlib.sha256(struct.pack(f"<{len(flattened)}f", *flattened)).hexdigest() if flattened else hashlib.sha256(b"").hexdigest()
    return {
        "schema": "robot-scope.relocalization-preview.v1", "layer": layer,
        "frame_id": frame, "family_revision": bundle.family_revision,
        "point_count": len(points), "maximum_points": limit,
        "content_revision": digest, "points": flattened,
    }


def _sample_points(points: Sequence[tuple[float, float, float]], limit: int) -> list[tuple[float, float, float]]:
    if len(points) <= limit:
        return list(points)
    return [points[(index * (len(points) - 1)) // (limit - 1)] for index in range(limit)]


def _read_binary_pcd_preview(path: Path, limit: int) -> list[tuple[float, float, float]]:
    with path.open("rb") as stream:
        header = b""
        while b"DATA binary\n" not in header and len(header) <= 64 * 1024:
            line = stream.readline()
            if not line:
                break
            header += line
        if b"DATA binary\n" not in header:
            raise RelocalizationValidationError("reference PCD is not bounded binary PCD")
        fields: dict[str, list[str]] = {}
        for line in header.decode("ascii").splitlines():
            parts = line.split()
            if parts and not parts[0].startswith("#"):
                fields[parts[0].upper()] = parts[1:]
        if fields.get("FIELDS", [])[:3] != ["x", "y", "z"] or fields.get("SIZE", [])[:3] != ["4", "4", "4"] or fields.get("TYPE", [])[:3] != ["F", "F", "F"]:
            raise RelocalizationValidationError("reference PCD XYZ layout is unsupported")
        count = int(fields.get("POINTS", ["0"])[0])
        if count <= 0 or count > 1_000_000:
            raise RelocalizationValidationError("reference PCD point count is invalid")
        step = sum(int(value) * int(multiplier) for value, multiplier in zip(fields["SIZE"], fields.get("COUNT", ["1"] * len(fields["SIZE"]))))
        indexes = set((index * (count - 1)) // (min(count, limit) - 1) for index in range(min(count, limit))) if min(count, limit) > 1 else {0}
        result = []
        for index in range(count):
            payload = stream.read(step)
            if len(payload) != step:
                raise RelocalizationValidationError("reference PCD payload is truncated")
            if index in indexes:
                point = struct.unpack_from("<fff", payload)
                if all(math.isfinite(value) for value in point):
                    result.append(point)
        return result


def _job_id(value: str) -> str:
    if not isinstance(value, str) or len(value) != 24 or any(character not in "0123456789abcdef" for character in value):
        raise RelocalizationNotFound("relocalization job was not found")
    return value


__all__ = [
    "LiveCollection", "RelocalizationBusy", "RelocalizationConflict",
    "RelocalizationError", "RelocalizationMapBundle", "RelocalizationNotFound",
    "RelocalizationUnavailable", "RelocalizationValidationError",
    "StationaryRelocalizationManager", "_compose_pose",
]
