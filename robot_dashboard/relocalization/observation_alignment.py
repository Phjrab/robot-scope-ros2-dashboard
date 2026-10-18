"""Bounded scan-to-map hypotheses from cached observations. Never publishes ROS.

Raw scans are explicitly projected through an unverified configured extrinsic
and receipt-paired odometry. A candidate is a display estimate, not localization
qualification. Original offline results and all experimental gates are unchanged.
"""
from __future__ import annotations

import itertools
import threading
import time
from typing import Any

import numpy as np

from .experimental_se3 import (
    Cloud, ExperimentalSE3Error, MAX_CORRESPONDENCE_M, compose, from_translation_quaternion,
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
        for i, (point, cell) in enumerate(zip(query, np.floor(query / MAX_CORRESPONDENCE_M).astype(np.int64))):
            if time.monotonic() > deadline:
                raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")
            key = x, y, z = tuple(int(v) for v in cell)
            candidates = self.neighbour_cache.get(key)
            if candidates is None:
                values = [j for dx, dy, dz in self.offsets
                          for j in self.buckets.get((x + dx, y + dy, z + dz), ())]
                candidates = np.asarray(values, dtype=np.int64)
                # Bound reusable index storage to 4 MB and 2,048 cells. The
                # candidate set remains exact when a new cell is not cached.
                if self.cached_indices + len(candidates) <= 500_000 and len(self.neighbour_cache) < 2048:
                    self.neighbour_cache[key] = candidates
                    self.cached_indices += len(candidates)
            if not len(candidates):
                continue
            diff = self.points[candidates] - point
            squared = np.einsum("ij,ij->i", diff, diff)
            # Ties select the lowest original index, matching the reference implementation.
            minimum = squared.min()
            if minimum <= MAX_CORRESPONDENCE_M ** 2:
                ids[i] = candidates[squared == minimum].min()
                distances[i] = minimum
        if time.monotonic() > deadline:
            raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")
        return ids, distances


def observed_key(value: dict[str, Any]) -> tuple[str, str]:
    observation = value.get("observation") or {}
    if (observation.get("identity_status") != "OBSERVED_PUBLISHER"
            or observation.get("publisher_count") != 1
            or not observation.get("publisher_gid") or observation.get("invalidated")):
        raise ObservationAlignmentError("SOURCE_IDENTITY_UNAVAILABLE")
    return str(observation["observer_id"]), str(observation["publisher_epoch"])


def project_query(cloud: dict[str, Any], pose: dict[str, Any], now: float) -> tuple[np.ndarray, str, dict[str, Any]]:
    cloud_key, pose_key = observed_key(cloud), observed_key(pose)
    co, po = cloud["observation"], pose["observation"]
    delta = po["received_monotonic_s"] - co["received_monotonic_s"]
    if cloud_key[0] != pose_key[0] or abs(delta) > .15:
        raise ObservationAlignmentError("RECEIPT_TIME_MISMATCH")
    if any(not 0 <= now - o["received_monotonic_s"] <= 1 for o in (co, po)):
        raise ObservationAlignmentError("STALE_INPUT")
    if (cloud.get("units") != "m" or pose.get("state") != "ok"
            or pose.get("child_frame_id") != "base_link"):
        raise ObservationAlignmentError("INVALID_INPUT")
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
        "pair_method": "HOST_RECEIPT_NEAREST", "deskew_verified": False,
        "pose_source_stamp_ns": po["source_stamp_ns"],
        "received_monotonic_s": co["received_monotonic_s"],
        "pose_received_monotonic_s": po["received_monotonic_s"],
    }


class ObservationAligner:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.cache: tuple[tuple[str, str], np.ndarray, RadiusGrid, str] | None = None
        self.last_started = float("-inf")

    def estimate(self, catalog: Any, agent: Any, body: dict[str, Any]) -> dict[str, Any]:
        if not self.lock.acquire(blocking=False):
            raise ObservationAlignmentError("BUSY")
        try:
            started = time.monotonic()
            if started - self.last_started < 1:
                raise ObservationAlignmentError("RATE_LIMIT_1HZ")
            self.last_started = started
            deadline = started + .6
            identifier, revision = body["map_id"], body["map_revision"]
            meta = catalog.metadata(identifier)
            if meta.get("kind") != "pointcloud3d" or meta.get("revision") != revision:
                raise ObservationAlignmentError("MAP_CHANGED")
            if not 60 <= int(meta.get("point_count", 0)) <= 100_000:
                raise ObservationAlignmentError("REFERENCE_LIMIT_60_TO_100000")
            if self.cache is None or self.cache[0] != (identifier, revision):
                data = catalog.data(identifier, None)
                points = np.asarray(data["points"], dtype=np.float64).reshape(-1, 3)
                if (data.get("revision") != revision or data.get("display_capped")
                        or int(data.get("source_points", len(points))) != len(points)):
                    raise ObservationAlignmentError("INCOMPLETE_REFERENCE")
                Cloud(points, data["frame_id"], "REGISTERED_MAP").validated(reference=True, max_points=100_000)
                self.cache = ((identifier, revision), points, RadiusGrid(points, deadline=deadline), data["frame_id"])
            cloud = agent.pointcloud_binary_snapshot()
            pose = agent.observation_pose_near(cloud.get("observation") or {})
            if pose is None:
                raise ObservationAlignmentError("NO_PAIRED_POSE")
            points, frame, provenance = project_query(cloud, pose, time.monotonic())
            for key in ("observer_id", "cloud_epoch", "pose_epoch"):
                if body.get(key) != provenance[key]:
                    raise ObservationAlignmentError("SOURCE_CHANGED")
            seed = validate_transform(body["T_map_odom_seed"])
            _, reference, grid, target_frame = self.cache
            if time.monotonic() > deadline:
                raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")
            result = register_se3(Cloud(reference, target_frame, "REGISTERED_MAP"),
                Cloud(points, frame, "REGISTERED_QUERY", stamp_ns=int(provenance["source_stamp_ns"])), seed,
                reference_limit=100_000, nearest=lambda query, _: grid.nearest(query, deadline=deadline))
            p = result["pose"]
            transform = from_translation_rpy([p[k] for k in ("x", "y", "z")], [p[k] for k in ("roll_rad", "pitch_rad", "yaw_rad")])
            indices, squared = grid.nearest(transform_points(transform, points), deadline=deadline)
            matched = reference[indices[squared <= MAX_CORRESPONDENCE_M ** 2]]
            ratio = 0.0
            if len(matched) >= 60:
                centered = matched - matched.mean(axis=0)
                eigen = np.linalg.eigvalsh(centered.T @ centered / len(matched))
                ratio = float(eigen[0] / max(eigen[-1], 1e-12))
            if ratio < MIN_GEOMETRY_RATIO:
                result["status"], result["reason"] = "REJECTED", "DEGENERATE_MATCHED_GEOMETRY"
            result["metrics"]["matched_geometry_min_max_eigen_ratio"] = ratio
            if catalog.metadata(identifier).get("revision") != revision:
                raise ObservationAlignmentError("MAP_CHANGED")
            if observed_key(agent.pointcloud_binary_snapshot()) != observed_key(cloud):
                raise ObservationAlignmentError("SOURCE_CHANGED")
            if observed_key(agent.pose_snapshot()) != observed_key(pose):
                raise ObservationAlignmentError("POSE_SOURCE_CHANGED")
            # Revalidate the actual pair, not just the newest input, after the worker finishes.
            project_query(cloud, pose, time.monotonic())
            if time.monotonic() > deadline:
                raise ObservationAlignmentError("COMPUTE_BUDGET_EXCEEDED")
            return {"schema": "robot-scope.observation-alignment.v1", "experimental": True,
                "operational_application": "NOT_RUN", "body_pose_verified": False, "absolute_accuracy_m": None,
                "map_id": identifier, "map_revision": revision, "target_frame": target_frame,
                "source": provenance, "status": result["status"], "reason": result["reason"],
                "T_map_odom": transform.tolist(), "metrics": result["metrics"],
                "reference_points": len(reference), "query_points": len(points),
                "correspondence_gate_m": MAX_CORRESPONDENCE_M, "sampling": "uniform_stride_query_max512_full_normalized_reference",
                "reference_processing": "catalogue all usable points; count equality required; rounded 0.0001 m; catalogue frame unverified",
                "total_runtime_ms": (time.monotonic() - started) * 1000}
        except ObservationAlignmentError:
            raise
        except (KeyError, TypeError, ValueError, OverflowError, np.linalg.LinAlgError) as exc:
            raise ObservationAlignmentError(str(exc)) from exc
        finally:
            self.lock.release()
