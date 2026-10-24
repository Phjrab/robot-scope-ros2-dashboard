"""Bounded scan-to-map hypotheses from cached observations. Never publishes ROS.

Raw scans are explicitly projected through an unverified configured extrinsic
and receipt-paired odometry. A candidate is a display estimate, not localization
qualification. The original offline result is retained alongside an explicit
provisional residual policy; all other input and numerical gates remain in place.
"""
from __future__ import annotations

import itertools
import re
import threading
import time
from typing import Any

import numpy as np

from ..ros.observation_identity import subscription_evidence_key
from .observation_timing import measure, note
from .observation_policy import qualify_observation

from .experimental_se3 import (
    Cloud, MAX_CORRESPONDENCE_M, compose, from_translation_quaternion,
    from_translation_rpy, inverse, register_se3, transform_points, validate_transform, MIN_GEOMETRY_RATIO,
)


class ObservationAlignmentError(ValueError):
    pass


class RadiusGrid:
    """Exact nearest neighbours inside the unchanged correspondence radius.

    No downsampling of the reference. Outside-radius distances are infinity;
    ICP only uses inside-radius distances. Deadline includes each query search.
    """
    def __init__(self, points: np.ndarray, *, deadline: float = float("inf")) -> None:
        self.points = points
        self.buckets: dict[tuple[int, ...], list[int]] = {}
        for i, cell in enumerate(np.floor(points / MAX_CORRESPONDENCE_M).astype(np.int64)):
            if i % 256 == 0 and time.monotonic() > deadline:
                raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")
            self.buckets.setdefault(tuple(cell), []).append(i)
        self.offsets = tuple(itertools.product((-1, 0, 1), repeat=3))
        self.neighbour_cache: dict[tuple[int, ...], np.ndarray] = {}
        self.cached_indices = 0

    def nearest(self, query: np.ndarray, *, deadline: float = float("inf")) -> tuple[np.ndarray, np.ndarray]:
        ids = np.zeros(len(query), dtype=np.int64)
        distances = np.full(len(query), np.inf)
        groups: dict[tuple[int, ...], list[int]] = {}
        for i, cell in enumerate(np.floor(query / MAX_CORRESPONDENCE_M).astype(np.int64)):
            groups.setdefault(tuple(int(v) for v in cell), []).append(i)
        for key, query_indices in groups.items():
            if time.monotonic() > deadline:
                raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")
            x, y, z = key
            candidates = self.neighbour_cache.get(key)
            if candidates is None:
                values = [j for dx, dy, dz in self.offsets
                          for j in self.buckets.get((x + dx, y + dy, z + dz), ())]
                candidates = np.sort(np.asarray(values, dtype=np.int64))
                # Bound reusable index storage to 4 MB and 2,048 cells. The
                # candidate set remains exact when a new cell is not cached.
                if self.cached_indices + len(candidates) <= 500_000 and len(self.neighbour_cache) < 2048:
                    self.neighbour_cache[key] = candidates
                    self.cached_indices += len(candidates)
            if not len(candidates):
                continue
            # Bound the largest float64 difference array to 16 * 4096 * 3
            # elements (1.5 MiB), independent of cell density. Sorted candidate
            # chunks and strict improvement retain the lowest original ID on ties.
            for query_start in range(0, len(query_indices), 16):
                rows = np.asarray(query_indices[query_start:query_start + 16], dtype=np.int64)
                query_chunk = query[rows]
                for candidate_start in range(0, len(candidates), 4096):
                    if time.monotonic() > deadline:
                        raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")
                    candidate_ids = candidates[candidate_start:candidate_start + 4096]
                    diff = self.points[candidate_ids][None, :, :] - query_chunk[:, None, :]
                    squared = np.einsum("qci,qci->qc", diff, diff)
                    local_ids = np.argmin(squared, axis=1)
                    minimum = squared[np.arange(len(rows)), local_ids]
                    improved = (minimum <= MAX_CORRESPONDENCE_M ** 2) & (minimum < distances[rows])
                    ids[rows[improved]] = candidate_ids[local_ids[improved]]
                    distances[rows[improved]] = minimum[improved]
                    del diff, squared
        if time.monotonic() > deadline:
            raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")
        return ids, distances


class ReferenceIndex:
    """Use an already installed native index, retaining exact radius/tie semantics.

    SciPy is optional: environments without it use the existing RadiusGrid.
    Batches and post-call checks preserve the same wall-clock deadline. The
    native index releases the GIL during searches in the dashboard process.
    """
    def __init__(self, points: np.ndarray, *, deadline: float = float("inf")) -> None:
        self.points = points
        self.coarse_cache = None
        try:
            from scipy.spatial import cKDTree
        except ImportError:
            self.tree = None
            self.fallback = RadiusGrid(points, deadline=deadline)
        else:
            self.tree = cKDTree(points)
        if time.monotonic() > deadline:
            raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")

    def coarse_index(self, *, deadline: float):
        from .observation_seed import voxel_centroids
        if time.monotonic() > deadline:
            raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")
        if self.coarse_cache is None:
            # Only immutable derived map geometry survives between requests.
            points = voxel_centroids(self.points)
            self.coarse_cache = (points, ReferenceIndex(points, deadline=deadline))
        return self.coarse_cache

    def nearest(self, query: np.ndarray, *, deadline: float = float("inf")) -> tuple[np.ndarray, np.ndarray]:
        if self.tree is None:
            return self.fallback.nearest(query, deadline=deadline)
        ids = np.zeros(len(query), dtype=np.int64)
        squared = np.full(len(query), np.inf)
        # Slightly over-fetch at the boundary, then apply the original squared gate.
        radius = MAX_CORRESPONDENCE_M + 1e-12
        for start in range(0, len(query), 64):
            if time.monotonic() > deadline:
                raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")
            rows = query[start:start + 64]
            distance, indices = self.tree.query(rows, k=2, eps=0, distance_upper_bound=radius, workers=1)
            valid_rows = np.flatnonzero(indices[:, 0] < len(self.points))
            winners = indices[valid_rows, 0].copy()
            # A tree may return any duplicate/equidistant point. Inspect
            # ties using original coordinates, retaining lowest input ID.
            ties = np.flatnonzero(distance[valid_rows, 1] - distance[valid_rows, 0] <= 1e-12)
            for slot in ties:
                local = valid_rows[slot]
                candidates = np.sort(self.tree.query_ball_point(rows[local], distance[local, 0] + 1e-12))
                diff = self.points[candidates] - rows[local]
                costs = np.einsum("ij,ij->i", diff, diff)
                winners[slot] = candidates[np.argmin(costs)]
            diff = self.points[winners] - rows[valid_rows]
            costs = np.einsum("ij,ij->i", diff, diff)
            inside = costs <= MAX_CORRESPONDENCE_M ** 2
            ids[start + valid_rows[inside]] = winners[inside]
            squared[start + valid_rows[inside]] = costs[inside]
            if time.monotonic() > deadline:
                raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")
        return ids, squared


def observed_key(value: dict[str, Any], *, provenance_mode: str = "native_publisher",
                 now: float | None = None) -> tuple[str, str]:
    observation = value.get("observation") or {}
    if provenance_mode == "subscription_observation":
        evidence = observation.get("subscription_evidence") or {}
        if (observation.get("invalidated")
                or type(observation.get("publisher_count")) is not int or observation.get("publisher_count") != 1
                or observation.get("reset_reason") == "SOURCE_STAMP_STALLED"
                or observation.get("receipt_clock") != "OBSERVER_HOST_MONOTONIC"
                or subscription_evidence_key(observation, time.monotonic() if now is None else now) is None
                or evidence.get("topic") != value.get("topic")
                or not re.fullmatch(r"[a-f0-9]{32}", str(observation.get("observer_id", "")))
                or not re.fullmatch(r"[a-f0-9]{32}", str(observation.get("publisher_epoch", "")))
                or not re.fullmatch(r"[1-9][0-9]*", str(observation.get("source_stamp_ns", "")))):
            raise ObservationAlignmentError("SUBSCRIPTION_EVIDENCE_UNAVAILABLE")
        return observation["observer_id"], observation["publisher_epoch"]
    if provenance_mode != "native_publisher":
        raise ObservationAlignmentError("INVALID_PROVENANCE_MODE")
    if (observation.get("identity_status") != "OBSERVED_PUBLISHER"
            or observation.get("publisher_count") != 1
            or not observation.get("publisher_gid") or observation.get("invalidated")):
        raise ObservationAlignmentError("SOURCE_IDENTITY_UNAVAILABLE")
    return str(observation["observer_id"]), str(observation["publisher_epoch"])


def project_query(cloud: dict[str, Any], pose: dict[str, Any], now: float, *,
                  provenance_mode: str = "native_publisher") -> tuple[np.ndarray, str, dict[str, Any]]:
    cloud_key = observed_key(cloud, provenance_mode=provenance_mode, now=now)
    pose_key = observed_key(pose, provenance_mode=provenance_mode, now=now)
    co, po = cloud["observation"], pose["observation"]
    if provenance_mode == "subscription_observation" and (
        co["subscription_evidence"].get("type_name") != "sensor_msgs/msg/PointCloud2"
        or po["subscription_evidence"].get("type_name") != "nav_msgs/msg/Odometry"
    ):
        raise ObservationAlignmentError("SUBSCRIPTION_TYPE_MISMATCH")
    delta = po["received_monotonic_s"] - co["received_monotonic_s"]
    if cloud_key[0] != pose_key[0] or abs(delta) > .15:
        raise ObservationAlignmentError("RECEIPT_TIME_MISMATCH")
    if any(not 0 <= now - o["received_monotonic_s"] <= 1 for o in (co, po)):
        raise ObservationAlignmentError("STALE_INPUT")
    fastlio_imu = (pose.get("topic") == "/Odometry" and pose.get("frame_id") == "camera_init"
                   and pose.get("child_frame_id") == "body")
    if (cloud.get("units") != "m" or pose.get("state") != "ok"
            or (pose.get("child_frame_id") != "base_link" and not fastlio_imu)):
        raise ObservationAlignmentError("INVALID_INPUT")
    if fastlio_imu:
        # This installed FAST-LIO emits both outputs at lidar_end_time. Its
        # `body` is the filter IMU state, not the Go2 base_link. Do not apply
        # the configured body extrinsic or receipt-nearest pairing to it.
        if (cloud.get("topic") != "/cloud_registered" or cloud.get("pipeline_stage") != "registered"
                or cloud.get("frame_id") != pose["frame_id"]
                or co["source_stamp_ns"] != po["source_stamp_ns"]):
            raise ObservationAlignmentError("FASTLIO_SOURCE_TIME_MISMATCH")
    raw = np.frombuffer(cloud["points_bytes"], dtype="<f4").reshape(-1, 3)
    raw = raw[::max(1, int(np.ceil(len(raw) / 512)))].astype(np.float64)
    if len(raw) < 60 or not np.isfinite(raw).all():
        raise ObservationAlignmentError("INSUFFICIENT_POINTS")
    position, q = pose["position"], pose["orientation"]
    quaternion = np.asarray([q[k] for k in ("x", "y", "z", "w")])
    norm = np.linalg.norm(quaternion)
    if not np.isfinite(norm) or abs(norm - 1) > .01:
        raise ObservationAlignmentError("INVALID_QUATERNION")
    t_odom_child = from_translation_quaternion([position[k] for k in ("x", "y", "z")], quaternion / norm)
    relation = cloud.get("robot_pose_in_frame") or {}
    if (cloud.get("topic") == "/cloud_registered" and cloud.get("pipeline_stage") == "registered"
            and cloud["frame_id"] == pose["frame_id"]):
        points = raw
        method = "REGISTERED_CLOUD_FIXED_FRAME_UNVERIFIED"
    elif ((cloud.get("topic"), cloud.get("pipeline_stage")) in {("/lidar_points", "raw"), ("/velodyne_points", "converted")}
          and relation.get("source") == "configured_sensor_extrinsic"
          and relation.get("frame_id") == cloud.get("frame_id")):
        t_sensor_body = from_translation_rpy([relation[k] for k in ("x", "y", "z")], [relation[k] for k in ("roll", "pitch", "yaw")])
        points = transform_points(compose(t_odom_child, inverse(t_sensor_body)), raw)
        method = "RAW_CLOUD_CONFIGURED_EXTRINSIC_UNVERIFIED"
    else:
        raise ObservationAlignmentError("FRAME_RELATION_UNAVAILABLE")
    return points, pose["frame_id"], {
        "method": method, "receipt_pair_delta_s": delta,
        "source_delta_ns": str(int(po["source_stamp_ns"]) - int(co["source_stamp_ns"])),
        "source_stamp_ns": co["source_stamp_ns"], "cloud_seq": cloud["seq"],
        "cloud_epoch": cloud_key[1], "pose_epoch": pose_key[1], "observer_id": cloud_key[0],
        "clock_relation": "UNVERIFIED", "body_extrinsic_verified": False,
        "pair_method": "FASTLIO_OUTPUT_STAMP_EXACT" if fastlio_imu else "HOST_RECEIPT_NEAREST", "deskew_verified": False,
        "tracked_frame": pose["child_frame_id"], "pose_topic": pose["topic"],
        "pose_reference": "FASTLIO_IMU" if fastlio_imu else "UNVERIFIED_BODY",
        "pose_source_stamp_ns": po["source_stamp_ns"],
        "received_monotonic_s": co["received_monotonic_s"],
        "pose_received_monotonic_s": po["received_monotonic_s"],
        "provenance_mode": provenance_mode,
        "per_message_publisher_verified": provenance_mode == "native_publisher",
        "cloud_subscription_evidence": co.get("subscription_evidence"),
        "pose_subscription_evidence": po.get("subscription_evidence"),
        "map_origin_verified": False,
    }


def solve_prepared(reference, grid, target_frame, points, frame, stamp_ns, seed, deadline):
    """Pure numerical work shared by inline diagnostics and the isolated worker."""
    from .observation_seed import prepare_seed
    with measure("local_seed"):
        seed, refinement = prepare_seed(grid, points, target_frame, frame, stamp_ns, seed, deadline)
    def nearest(query, _):
        with measure("nearest"):
            return grid.nearest(query, deadline=deadline)
    with measure("registration"):
        result = register_se3(Cloud(reference, target_frame, "REGISTERED_MAP"),
            Cloud(points, frame, "REGISTERED_QUERY", stamp_ns=stamp_ns), seed,
            reference_limit=100_000, nearest=nearest)
    p = result["pose"]
    transform = from_translation_rpy([p[k] for k in ("x", "y", "z")], [p[k] for k in ("roll_rad", "pitch_rad", "yaw_rad")])
    indices, squared = nearest(transform_points(transform, points), reference)
    note("iterations", result["metrics"]["iterations"])
    matched = reference[indices[squared <= MAX_CORRESPONDENCE_M ** 2]]
    ratio = 0.0
    if len(matched) >= 60:
        centered = matched - matched.mean(axis=0)
        eigen = np.linalg.eigvalsh(centered.T @ centered / len(matched))
        ratio = float(eigen[0] / max(eigen[-1], 1e-12))
    if ratio < MIN_GEOMETRY_RATIO:
        result["status"], result["reason"] = "REJECTED", "DEGENERATE_MATCHED_GEOMETRY"
    result["metrics"]["matched_geometry_min_max_eigen_ratio"] = ratio
    result["metrics"]["inlier_count"] = len(matched)
    if refinement is not None:
        result["seed_refinement"] = refinement
    return result, transform


class ObservationAligner:
    def __init__(self, *, isolated: bool = False) -> None:
        self.lock = threading.Lock()
        self.cache: tuple[tuple[str, str], np.ndarray, ReferenceIndex | None, str] | None = None
        self.last_started = float("-inf")
        self.closed = False
        self.worker = None
        if isolated:
            from .observation_worker import RegistrationWorker
            self.worker = RegistrationWorker()

    def close(self) -> None:
        with self.lock:
            self.closed = True
            if self.worker is not None:
                self.worker.close()

    def estimate(self, catalog: Any, agent: Any, body: dict[str, Any]) -> dict[str, Any]:
        if not self.lock.acquire(blocking=False):
            raise ObservationAlignmentError("BUSY")
        try:
            if self.closed:
                raise ObservationAlignmentError("WORKER_CLOSED")
            started = time.monotonic()
            if started - self.last_started < 1:
                raise ObservationAlignmentError("RATE_LIMIT_1HZ")
            self.last_started = started
            deadline = started + .6
            provenance_mode = body.get("provenance_mode", "native_publisher")
            identifier, revision = body["map_id"], body["map_revision"]
            metadata = getattr(catalog, "observation_metadata", catalog.metadata)
            map_data = getattr(catalog, "observation_data", catalog.data)
            with measure("catalog_metadata"):
                meta = metadata(identifier)
            if meta.get("kind") != "pointcloud3d" or meta.get("revision") != revision:
                raise ObservationAlignmentError("MAP_CHANGED")
            if not 60 <= int(meta.get("point_count", 0)) <= 100_000:
                raise ObservationAlignmentError("REFERENCE_LIMIT_60_TO_100000")
            if time.monotonic() > deadline:
                raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")
            with measure("input_snapshot_and_validation"):
                cloud = agent.pointcloud_binary_snapshot()
                pose = (agent.observation_pose_near(cloud.get("observation") or {}, provenance_mode=provenance_mode)
                        if provenance_mode == "subscription_observation"
                        else agent.observation_pose_near(cloud.get("observation") or {}))
                if pose is None:
                    raise ObservationAlignmentError("NO_PAIRED_POSE")
                points, frame, provenance = project_query(cloud, pose, time.monotonic(), provenance_mode=provenance_mode)
            for key in ("observer_id", "cloud_epoch", "pose_epoch"):
                if body.get(key) != provenance[key]:
                    raise ObservationAlignmentError("SOURCE_CHANGED")
            note("reference_cache_hit", self.cache is not None and self.cache[0] == (identifier, revision))
            if self.cache is None or self.cache[0] != (identifier, revision):
                with measure("catalog_data"):
                    data = map_data(identifier, None)
                with measure("reference_array"):
                    reference_points = np.asarray(data["points"], dtype=np.float64).reshape(-1, 3)
                if (data.get("revision") != revision or data.get("display_capped")
                        or int(data.get("source_points", len(reference_points))) != len(reference_points)):
                    raise ObservationAlignmentError("INCOMPLETE_REFERENCE")
                Cloud(reference_points, data["frame_id"], "REGISTERED_MAP").validated(reference=True, max_points=100_000)
                # Keep immutable reference preparation across bounded attempts.
                # A slow file read cannot consume every retry's live budget.
                # No pose/result is retained: the next attempt selects fresh inputs.
                self.cache = ((identifier, revision), reference_points, None, data["frame_id"])
            seed = validate_transform(body["T_map_odom_seed"])
            _, reference, grid, target_frame = self.cache
            if time.monotonic() > deadline:
                raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")
            if grid is None and self.worker is None:
                with measure("reference_grid"):
                    grid = ReferenceIndex(reference, deadline=deadline)
                self.cache = ((identifier, revision), reference, grid, target_frame)
            if self.worker is None:
                result, transform = solve_prepared(reference, grid, target_frame, points, frame,
                                                   int(provenance["source_stamp_ns"]), seed, deadline)
            else:
                with measure("isolated_registration"):
                    result, transform = self.worker.solve((identifier, revision), reference, target_frame,
                        points, frame, int(provenance["source_stamp_ns"]), seed, deadline)
            assessment = qualify_observation(result, inlier_count=result["metrics"]["inlier_count"], query_count=len(points))
            with measure("completion_validation"):
                if metadata(identifier).get("revision") != revision:
                    raise ObservationAlignmentError("MAP_CHANGED")
                current_cloud, current_pose = agent.pointcloud_binary_snapshot(), agent.pose_snapshot()
                if observed_key(current_cloud, provenance_mode=provenance_mode) != observed_key(cloud, provenance_mode=provenance_mode):
                    raise ObservationAlignmentError("SOURCE_CHANGED")
                if observed_key(current_pose, provenance_mode=provenance_mode) != observed_key(pose, provenance_mode=provenance_mode):
                    raise ObservationAlignmentError("POSE_SOURCE_CHANGED")
                if provenance_mode == "subscription_observation":
                    for current, original in ((current_cloud, cloud), (current_pose, pose)):
                        if subscription_evidence_key(current["observation"], time.monotonic()) != subscription_evidence_key(original["observation"], time.monotonic()):
                            raise ObservationAlignmentError("SUBSCRIPTION_EVIDENCE_CHANGED")
                # Revalidate the actual pair, not just the newest input, after the worker finishes.
                project_query(cloud, pose, time.monotonic(), provenance_mode=provenance_mode)
                if time.monotonic() > deadline:
                    raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")
            if provenance_mode == "subscription_observation" and assessment["status"] == "CANDIDATE":
                assessment["status"] = "CANDIDATE_SOURCE_UNVERIFIED"
                assessment["reason"] = "CANDIDATE_SOURCE_UNVERIFIED"
            payload = {"schema": "robot-scope.observation-alignment.v1", "experimental": True,
                "operational_application": "NOT_RUN", "body_pose_verified": False, "absolute_accuracy_m": None,
                "body_extrinsic_verified": False,
                "provenance_mode": provenance_mode,
                "per_message_publisher_verified": provenance_mode == "native_publisher",
                "map_id": identifier, "map_revision": revision, "target_frame": target_frame,
                "source": provenance, **assessment,
                "T_map_odom": transform.tolist(), "metrics": result["metrics"],
                "reference_points": len(reference), "query_points": len(points),
                "correspondence_gate_m": MAX_CORRESPONDENCE_M, "sampling": "uniform_stride_query_max512_full_normalized_reference",
                "reference_processing": "catalogue all usable points; count equality required; rounded 0.0001 m; catalogue frame unverified",
                "total_runtime_ms": (time.monotonic() - started) * 1000}
            if "seed_refinement" in result:
                payload["seed_refinement"] = result["seed_refinement"]
            if body.get("capture_inputs") is True:
                from .observation_capture import capture_inputs
                capture_started = time.monotonic()
                with measure("input_capture"):
                    payload["input_capture"] = capture_inputs(identifier=identifier, revision=revision,
                        reference=reference, target_frame=target_frame, points=points, frame=frame,
                        seed=seed, pose=pose, source=provenance)
                payload["input_capture_runtime_ms"] = (time.monotonic() - capture_started) * 1000
                payload["total_runtime_ms"] = (time.monotonic() - started) * 1000
            return payload
        except ObservationAlignmentError:
            raise
        except (KeyError, TypeError, ValueError, OverflowError, np.linalg.LinAlgError) as exc:
            raise ObservationAlignmentError(str(exc)) from exc
        finally:
            self.lock.release()
