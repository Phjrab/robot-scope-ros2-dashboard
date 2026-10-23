"""Explicitly requested, observation-only temporal LiDAR sensor tracking.

The global job remains historical. This owner accepts its verified *input
identity* and a selected sensor transform as a seed, then independently checks
new, complete XYZ captures. It never publishes TF, odometry or control, and it
never describes a sensor candidate as a body pose or verified current position.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
import copy
import hashlib
import math
import re
import threading
import time
from typing import Any, Callable, cast

import numpy as np

from ..relocalization.v031_observation_compat import SELECTION_POLICY, valid_ambiguity_override
from ..ros.raw_pointcloud_capture import RawCaptureBusy, RawCaptureUnavailable


class SensorTrackingConflict(RuntimeError):
    pass


class SensorTrackingUnavailable(RuntimeError):
    pass


class SensorTrackingValidation(ValueError):
    pass


class SensorTrackingNotFound(RuntimeError):
    pass


_HEX64 = re.compile(r"[a-f0-9]{64}\Z")
_REQUEST = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_STAMP = re.compile(r"[0-9]{1,30}\Z")
_ACTIVE = {"INITIALIZING", "ACQUIRING_FRESH_SCAN", "SENSOR_CANDIDATE"}
_MAX_TRAIL = 40
SESSION_WATCHDOG_S = 60.0


def _finite_number(value: Any) -> float | None:
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return float(value)


def _stamp(value: Any) -> int | None:
    if isinstance(value, str) and _STAMP.fullmatch(value):
        return int(value)
    return None


def _rigid(value: Any) -> list[list[float]] | None:
    try:
        matrix = np.asarray(value, dtype=float)
        if (matrix.shape != (4, 4) or not np.isfinite(matrix).all()
                or not np.allclose(matrix[3], [0., 0., 0., 1.], atol=1e-8)
                or not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-6)
                or not math.isclose(float(np.linalg.det(matrix[:3, :3])), 1., abs_tol=1e-6)):
            return None
        return cast(list[list[float]], matrix.tolist())
    except (TypeError, ValueError):
        return None


def _motion_consistent(before: list[list[float]], after: list[list[float]]) -> bool:
    a, b = np.asarray(before), np.asarray(after)
    translation = float(np.linalg.norm(a[:3, 3] - b[:3, 3]))
    relative = a[:3, :3].T @ b[:3, :3]
    cosine = float(np.clip((np.trace(relative) - 1.) / 2., -1., 1.))
    return translation <= 1. and math.acos(cosine) <= math.radians(60.)


def _safe_map(context: dict[str, Any]) -> dict[str, Any]:
    reference = context["map"]
    return {"map_id": context["map_id"], "map_revision": context["map_revision"],
            "frame_id": context["map_frame"], "source_sha256": reference["source_sha256"],
            "xyz_sha256": reference["sha256"]}


def _admissible_gates(observation: dict[str, Any], candidate: dict[str, Any], *, allowed: bool) -> bool:
    override = observation.get("ambiguity_override")
    if override is not None and not isinstance(override, dict):
        return False
    if override is not None and (type(override.get("enabled")) is not bool
                                 or type(override.get("applied")) is not bool):
        return False
    if ((override or {}).get("applied") is True
            or observation.get("estimate_label") == "AMBIGUOUS_UNVERIFIED_ESTIMATE"):
        return valid_ambiguity_override(observation, allowed=allowed)
    return not observation["gate_reasons"] and not candidate["gate_reasons"]


def _handoff(job: dict[str, Any], expected_id: str, *, allow_ambiguous: bool = False) -> tuple[dict[str, Any], list[list[float]], int]:
    """Check the immutable, successful historical result before admitting work."""
    try:
        context = job["captured_context"]
        result = job["result"]
        observation = result["observation"]
        index = observation["selected_candidate"]
        candidate = observation["candidates"][index]
        scan, reference = context["scan"], context["map"]
        matrix = _rigid(candidate["map_from_scan"])
        stamp = _stamp(context["source_stamp_ns"])
        residual = _finite_number(candidate["rmse_m"])
        overlap = _finite_number(candidate["overlap"])
        pin = observation["execution"]["source_pin_sha256"]
        valid = (job["job_id"] == expected_id and job["state"] == "succeeded"
                 and job["worker_active"] is False and result["captured_context"] == context
                 and job["historical_only"] is True and result["historical_only"] is True
                 and result["body_pose"] is None and result["tracking_verified"] is False
                 and result["job_id"] == expected_id and result["generation"] == job["generation"]
                 and observation["status"] == "OBSERVATION_ONLY_UNVERIFIED"
                 and observation["selection_policy"] == SELECTION_POLICY
                 and isinstance(pin, str) and _HEX64.fullmatch(pin)
                 and type(index) is int and index >= 0
                 and _admissible_gates(observation, candidate, allowed=allow_ambiguous)
                 and matrix is not None
                 and residual is not None and residual >= 0.
                 and overlap is not None and .60 <= overlap <= 1.
                 and type(candidate["scan_count"]) is int
                 and candidate["scan_count"] == scan["point_count"]
                 and type(candidate["inlier_count"]) is int and candidate["inlier_count"] >= 60
                 and candidate["inlier_count"] <= candidate["scan_count"]
                 and type(candidate["distinct_inlier_voxel_count"]) is int
                 and candidate["distinct_inlier_voxel_count"] >= 60
                 and candidate["distinct_inlier_voxel_count"] <= candidate["inlier_count"]
                 and (_finite_number(candidate["geometry_min_max_eigen_ratio"]) or 0.) >= .002
                 and (_finite_number(candidate["inlier_geometry_min_max_eigen_ratio"]) or 0.) >= .002
                 and _finite_number(candidate["full_scan_rmse_m"]) is not None
                 and candidate["full_scan_rmse_m"] >= 0.
                 and candidate["refinement_stationary"] is True
                 and context["map_id"] == job["map_id"] == reference["map_id"]
                 and context["map_revision"] == job["map_revision"] == reference["map_revision"]
                 and context["map_frame"] == reference["frame_id"] == observation["map_frame"]
                 and context["source_frame"] == scan["source_frame"] == observation["scan_frame"]
                 and context["observer_epoch"] == scan["observer_epoch"]
                 and context["source_stamp_ns"] == scan["source_stamp_ns"]
                 and scan["source_topic"] == scan["topic"]
                 and reference["encoding"] == scan["encoding"] == "float64_le_xyz"
                 and reference["units"] == scan["units"] == "m"
                 and reference["source_order_preserved"] is True
                 and scan["source_order_preserved"] is True
                 and reference["zero_rows_preserved"] is True
                 and reference["nonfinite_rows_preserved"] is True
                 and scan["zero_rows_preserved"] is True
                 and scan["nonfinite_rows_preserved"] is True
                 and scan["sampling_applied"] is False and scan["spatial_filter_applied"] is False
                 and scan["transform_applied"] is False
                 and scan["finite_points"] == scan["point_count"]
                 and reference["sampling_applied"] is False
                 and reference["spatial_filter_applied"] is False
                 and reference["transform_applied"] is False
                 and bool(context["observer_id"]) and bool(context["observer_epoch"])
                 and stamp is not None and stamp > 0
                 and all(isinstance(reference[k], str) and _HEX64.fullmatch(reference[k])
                         for k in ("sha256", "source_sha256"))
                 and isinstance(scan["sha256"], str) and _HEX64.fullmatch(scan["sha256"])
                 and observation["map_id"] == "sha256:" + reference["sha256"]
                 and observation["source_stamp_ns"] == context["source_stamp_ns"]
                 and observation["session_id"] == context["observer_epoch"]
                 and observation["input_points"] == scan["point_count"]
                 and observation["reference_points"] == reference["point_count"]
                 and observation["frame_id"] == context["source_frame"]
                 and observation["map_frame"] == context["map_frame"])
        if not valid:
            raise ValueError("historical selection or identity is not admissible")
        assert isinstance(context, dict) and matrix is not None and type(index) is int
        return context, matrix, index
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise SensorTrackingConflict("GLOBAL_CANDIDATE_NOT_ADMISSIBLE") from exc


class SensorTrackingOwner:
    def __init__(self, catalog: Any, agent: Any, global_observation: Any,
                 process_factory: Callable[[], Any], *, pin_provider: Callable[[], dict[str, Any]] | None = None,
                 allow_ambiguous: bool = False,
                 execution_policy: dict[str, Any] | None = None,
                 session_watchdog_s: float = SESSION_WATCHDOG_S,
                 capture_timeout_s: float = 1.,
                 max_points: int = 1_000_000, max_bytes: int = 32 * 1024 * 1024,
                 now: Callable[[], float] = time.monotonic) -> None:
        self._catalog, self._agent, self._global = catalog, agent, global_observation
        self._process_factory, self._pin_provider, self._now = process_factory, pin_provider, now
        if type(allow_ambiguous) is not bool:
            raise ValueError("allow_ambiguous must be an explicit boolean")
        self._allow_ambiguous = allow_ambiguous
        self._execution_policy = copy.deepcopy(execution_policy)
        if (type(session_watchdog_s) not in (int, float)
                or not math.isfinite(session_watchdog_s) or session_watchdog_s <= 0.):
            raise ValueError("session_watchdog_s must be finite and positive")
        self._session_watchdog_s = float(session_watchdog_s)
        self._session_timer: threading.Timer | None = None
        self._session_deadline: float | None = None
        self._ambiguity_override: dict[str, Any] | None = None
        self._ambiguity_source: str | None = None
        self._last_alignment: dict[str, Any] | None = None
        self._resource_admission: dict[str, Any] | None = None
        self._capture_timeout_s, self._max_points, self._max_bytes = capture_timeout_s, max_points, max_bytes
        self._lock = threading.RLock()
        self._generation = 0
        self._state = "WAITING_GLOBAL"
        self._reason: str | None = None
        self._context: dict[str, Any] | None = None
        self._global_job: dict[str, Any] | None = None
        self._source: dict[str, Any] | None = None
        self._sensor_pose: dict[str, Any] | None = None
        self._trail: list[dict[str, Any]] = []
        self._confirmations = 0
        self._last_stamp = 0
        self._last_receipt = 0.
        self._last_matrix: list[list[float]] | None = None
        self._used_global_jobs: set[str] = set()
        self._requests: OrderedDict[str, str] = OrderedDict()
        self._cancel: threading.Event | None = None
        self._capture_id: str | None = None
        self._process: Any | None = None
        self._cleanup_complete: bool | None = None
        self._thread: threading.Thread | None = None
        self._closed = False

    def _snapshot_locked(self) -> dict[str, Any]:
        source = copy.deepcopy(self._source)
        if source is not None:
            received = _finite_number(source.get("received_monotonic_s"))
            source["age_s"] = max(0., self._now() - received) if received is not None else None
        return {"schema": "robot-scope.sensor-tracking.v1", "state": self._state,
                "reason": self._reason, "generation": self._generation,
                "worker_active": self._thread is not None and self._thread.is_alive(),
                "cleanup_complete": (self._cleanup_complete is not False and self._process is None
                                     and (self._thread is None or not self._thread.is_alive())),
                "source_global_job": copy.deepcopy(self._global_job),
                "map": _safe_map(self._context) if self._context else None,
                "source": source, "sensor_pose": copy.deepcopy(self._sensor_pose),
                "trail": copy.deepcopy(self._trail),
                "ambiguity_override": copy.deepcopy(self._ambiguity_override),
                "ambiguity_source": self._ambiguity_source,
                "estimate_label": ("AMBIGUOUS_UNVERIFIED_ESTIMATE" if self._ambiguity_override
                                   else "UNVERIFIED_SENSOR_ESTIMATE"),
                "last_alignment": copy.deepcopy(self._last_alignment),
                "execution_policy": copy.deepcopy(self._execution_policy),
                "resource_admission": copy.deepcopy(self._resource_admission),
                "session_watchdog": {
                    "timeout_s": self._session_watchdog_s,
                    "active": self._session_timer is not None,
                    "remaining_s": (max(0., self._session_deadline - time.monotonic())
                                    if self._session_deadline is not None else None),
                    "scope": "STARTUP_CAPTURE_ALIGNMENT_UNTIL_CLEANUP",
                    "boundary": "GENERATION_CANCEL_OWNED_PROCESS_GROUP_REAP",
                    "hard_realtime_guarantee": False},
                "temporal_consistency_confirmed": self._state == "SENSOR_CANDIDATE",
                "globally_verified": False, "body_pose": None, "tracking_verified": False,
                "source_clock_verified": False, "body_extrinsic_verified": False,
                "operational_application": "NOT_RUN"}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            expired = (self._session_deadline is not None
                       and time.monotonic() >= self._session_deadline)
            generation, process = self._generation, self._process
        if expired and process is not None:
            self._expire_session(generation, process)
        with self._lock:
            active = self._state in {"INITIALIZING", "ACQUIRING_FRESH_SCAN", "SENSOR_CANDIDATE"}
            context = self._context if active else None
            candidate = self._state == "SENSOR_CANDIDATE"
            global_generation = (self._global_job or {}).get("generation")
            generation = self._generation
        if context is not None:
            global_matches = self._global_matches(global_generation)
            try:
                source_matches = not candidate or (global_matches and self._source_matches(context))
            except Exception:
                source_matches = False
            if not global_matches or not source_matches:
                with self._lock:
                    if self._state in {"INITIALIZING", "ACQUIRING_FRESH_SCAN", "SENSOR_CANDIDATE"} and self._generation == generation:
                        self._lose_locked("STALE", "GLOBAL_OBSERVATION_CHANGED" if not global_matches
                                          else "CURRENT_SOURCE_OR_MAP_CHANGED")
        with self._lock:
            cleanup_process, cleanup_capture = None, None
            if (self._session_deadline is not None
                    and time.monotonic() >= self._session_deadline and self._process is not None):
                cleanup_process = self._process
                _, cleanup_capture = self._expire_session_locked(self._generation, cleanup_process)
            if self._state == "SENSOR_CANDIDATE" and self._source is not None:
                receipt = _finite_number(self._source.get("received_monotonic_s"))
                if receipt is None or not 0 <= self._now() - receipt <= 1.:
                    self._lose_locked("STALE", "SCAN_RECEIPT_STALE")
            view = self._snapshot_locked()
        if cleanup_process is not None:
            self._cleanup_expired_session(cleanup_process, cleanup_capture)
            with self._lock:
                return self._snapshot_locked()
        return view

    def _lose_locked(self, state: str, reason: str) -> None:
        self._state, self._reason = state, reason
        self._sensor_pose, self._source = None, None
        self._trail.clear()
        self._confirmations = 0
        if self._cancel is not None:
            self._cancel.set()

    def _cancel_session_watchdog_locked(self) -> None:
        timer, self._session_timer = self._session_timer, None
        self._session_deadline = None
        if timer is not None:
            timer.cancel()

    def _close_owned_process(self, process: Any) -> bool:
        try:
            reaped = process.close() is True
        except Exception:
            reaped = False
        with self._lock:
            if self._process is process:
                self._cleanup_complete = reaped
                if reaped:
                    self._process = None
        return reaped

    def _require_session_live_locked(self) -> None:
        if (self._session_deadline is not None
                and time.monotonic() >= self._session_deadline):
            self._cancel_session_watchdog_locked()
            self._generation += 1
            self._lose_locked("LOST", "SENSOR_SESSION_WATCHDOG_EXCEEDED")
            raise SensorTrackingConflict("SENSOR_SESSION_WATCHDOG_EXCEEDED")

    def _expire_session_locked(self, generation: int, process: Any) -> tuple[bool, str | None]:
        if generation != self._generation or self._process is not process:
            return False, None
        self._cancel_session_watchdog_locked()
        # Invalidate before cancellation/cleanup so a concurrent old reply
        # can never republish a pose, even if its Python thread is delayed.
        self._generation += 1
        self._lose_locked("LOST", "SENSOR_SESSION_WATCHDOG_EXCEEDED")
        capture_id, self._capture_id = self._capture_id, None
        return True, capture_id

    def _cleanup_expired_session(self, process: Any, capture_id: str | None) -> None:
        if capture_id:
            try:
                self._agent.cancel_raw_pointcloud_capture(capture_id)
            except Exception:
                pass
        self._close_owned_process(process)

    def _expire_session(self, generation: int, process: Any) -> None:
        with self._lock:
            expired, capture_id = self._expire_session_locked(generation, process)
        if expired:
            self._cleanup_expired_session(process, capture_id)

    def _global_matches(self, expected_generation: Any) -> bool:
        if type(expected_generation) is not int:
            return False
        try:
            state = self._global.snapshot()
        except Exception:
            return False
        return (state.get("generation") == expected_generation
                and state.get("active") is None and state.get("closed") is False)

    def _source_matches(self, context: dict[str, Any]) -> bool:
        metadata = self._catalog.metadata(context["map_id"])
        live = self._agent.raw_pointcloud_context_snapshot()
        observation = live.get("observation") or {}
        received = _finite_number(observation.get("received_monotonic_s"))
        return (metadata.get("revision") == context["map_revision"]
                and metadata.get("kind") == "pointcloud3d"
                and metadata.get("format") == "pcd-binary"
                and live.get("topic") == context["scan"]["source_topic"]
                and live.get("pipeline_stage") == context["source_pipeline_stage"]
                and live.get("frame_id") == context["source_frame"]
                and observation.get("observer_id") == context["observer_id"]
                and observation.get("publisher_epoch") == context["observer_epoch"]
                and (_stamp(observation.get("source_stamp_ns")) or 0)
                >= (_stamp(context["source_stamp_ns"]) or 1)
                and received is not None and 0 <= self._now() - received <= 1.)

    def _current_matches(self, context: dict[str, Any], *, global_generation: int | None = None) -> bool:
        if global_generation is None:
            with self._lock:
                global_generation = (self._global_job or {}).get("generation")
        return self._global_matches(global_generation) and self._source_matches(context)

    def start(self, global_job_id: str, request_id: str) -> dict[str, Any]:
        if (not isinstance(global_job_id, str) or not re.fullmatch(r"[a-f0-9]{24}", global_job_id)
                or not isinstance(request_id, str) or not _REQUEST.fullmatch(request_id)):
            raise SensorTrackingValidation("invalid sensor tracking request")
        with self._lock:
            previous = self._requests.get(request_id)
            if previous is not None:
                if previous != global_job_id:
                    raise SensorTrackingConflict("REQUEST_ID_ALREADY_USED_FOR_DIFFERENT_GLOBAL_JOB")
                return self.snapshot()
        try:
            job = self._global.job(global_job_id)
        except Exception as exc:
            raise SensorTrackingNotFound("global observation job was not found") from exc
        context, matrix, index = _handoff(job, global_job_id, allow_ambiguous=self._allow_ambiguous)
        global_state = self._global.snapshot()
        if global_state.get("active") is not None:
            raise SensorTrackingConflict("GLOBAL_OBSERVATION_STILL_ACTIVE")
        if not self._global_matches(job["generation"]):
            raise SensorTrackingConflict("GLOBAL_OBSERVATION_CHANGED")
        if self._pin_provider is not None:
            try:
                pin = self._pin_provider()
            except Exception as exc:
                raise SensorTrackingUnavailable("LOCAL_SOURCE_PIN_UNAVAILABLE") from exc
            if (pin.get("available") is not True
                    or pin.get("source_pin_sha256") != job["result"]["observation"]["execution"]["source_pin_sha256"]):
                raise SensorTrackingConflict("GLOBAL_AND_LOCAL_SOURCE_PIN_DIFFER")
        try:
            current = self._current_matches(context, global_generation=job["generation"])
        except Exception as exc:
            raise SensorTrackingUnavailable("CURRENT_SOURCE_OR_MAP_UNAVAILABLE") from exc
        if not current:
            raise SensorTrackingConflict("CURRENT_SOURCE_OR_MAP_CHANGED")
        with self._lock:
            if self._closed:
                raise SensorTrackingUnavailable("SENSOR_TRACKING_OWNER_CLOSED")
            previous = self._requests.get(request_id)
            if previous is not None:
                if previous != global_job_id:
                    raise SensorTrackingConflict("REQUEST_ID_ALREADY_USED_FOR_DIFFERENT_GLOBAL_JOB")
                return self._snapshot_locked()
            if self._thread is not None and self._thread.is_alive():
                raise SensorTrackingConflict("SENSOR_TRACKING_ALREADY_ACTIVE")
            if self._process is not None or self._cleanup_complete is False:
                raise SensorTrackingConflict("SENSOR_PREVIOUS_PROCESS_CLEANUP_PENDING")
            if global_job_id in self._used_global_jobs:
                raise SensorTrackingConflict("GLOBAL_CANDIDATE_ALREADY_USED")
            if not self._global_matches(job["generation"]):
                raise SensorTrackingConflict("GLOBAL_OBSERVATION_CHANGED")
            try:
                process = self._process_factory()
            except Exception as exc:
                raise SensorTrackingUnavailable("LOCAL_TRACKING_PROCESS_UNAVAILABLE") from exc
            self._generation += 1
            generation = self._generation
            cancel = threading.Event()
            self._state, self._reason = "INITIALIZING", None
            self._context, self._last_matrix = copy.deepcopy(context), matrix
            self._global_job = {"job_id": global_job_id, "generation": job["generation"],
                                "selected_candidate": index}
            self._source, self._sensor_pose = None, None
            observation = job["result"]["observation"]
            ambiguous = valid_ambiguity_override(observation, allowed=self._allow_ambiguous)
            self._ambiguity_override = copy.deepcopy(observation["ambiguity_override"]) if ambiguous else None
            self._ambiguity_source = "GLOBAL" if ambiguous else None
            self._last_alignment = None
            self._resource_admission = None
            self._trail, self._confirmations = [], 0
            self._last_stamp, self._last_receipt = _stamp(context["source_stamp_ns"]) or 0, 0.
            self._cancel, self._process = cancel, process
            self._cleanup_complete = False
            self._used_global_jobs.add(global_job_id)
            self._requests[request_id] = global_job_id
            if len(self._requests) > 64:
                _, expired_job = self._requests.popitem(last=False)
                self._used_global_jobs.discard(expired_job)
            worker = threading.Thread(target=self._run, args=(generation, cancel, process),
                                      name=f"sensor-tracking-{generation}", daemon=True)
            self._thread = worker
            timer = threading.Timer(self._session_watchdog_s, self._expire_session,
                                    args=(generation, process))
            timer.daemon = True
            self._session_deadline = time.monotonic() + self._session_watchdog_s
            self._session_timer = timer
            try:
                timer.start()
                worker.start()
            except RuntimeError as exc:
                self._cancel_session_watchdog_locked()
                self._lose_locked("LOST", "WORKER_START_FAILED")
                self._thread = None
                self._close_owned_process(process)
                raise SensorTrackingUnavailable("LOCAL_TRACKING_WORKER_UNAVAILABLE") from exc
            return self._snapshot_locked()

    def _capture(self, context: dict[str, Any], cancel: threading.Event) -> tuple[bytes, dict[str, Any]]:
        with self._lock:
            self._require_session_live_locked()
        if not self._current_matches(context):
            raise SensorTrackingConflict("CURRENT_SOURCE_OR_MAP_CHANGED")
        try:
            ticket = self._agent.request_raw_pointcloud_capture(
                timeout_s=self._capture_timeout_s, max_points=self._max_points, max_bytes=self._max_bytes)
        except RawCaptureBusy as exc:
            raise SensorTrackingConflict("RAW_CAPTURE_BUSY") from exc
        except RawCaptureUnavailable as exc:
            raise SensorTrackingConflict("RAW_CAPTURE_UNAVAILABLE") from exc
        capture_id = ticket["capture_id"]
        try:
            with self._lock:
                self._require_session_live_locked()
                self._capture_id = capture_id
                if cancel.is_set():
                    raise SensorTrackingConflict("CAPTURE_CANCELLED")
            while not cancel.is_set():
                with self._lock:
                    self._require_session_live_locked()
                status = self._agent.raw_pointcloud_capture_snapshot(capture_id)
                if status and status.get("state") == "ready":
                    break
                if not status or status.get("state") in {"failed", "stale", "timed_out", "cancelled", "consumed"}:
                    raise SensorTrackingConflict((status or {}).get("reason") or "CAPTURE_UNAVAILABLE")
                cancel.wait(.02)
            if cancel.is_set():
                raise SensorTrackingConflict("CAPTURE_CANCELLED")
            captured = self._agent.take_raw_pointcloud_capture(capture_id)
            payload = captured.pop("xyz_bytes")
            return payload, captured
        finally:
            try:
                self._agent.cancel_raw_pointcloud_capture(capture_id)
            except Exception:
                pass
            with self._lock:
                if self._capture_id == capture_id:
                    self._capture_id = None

    def _validate_capture(self, payload: bytes, capture: dict[str, Any],
                          context: dict[str, Any]) -> tuple[int, float]:
        stamp = _stamp(capture.get("source_stamp_ns"))
        receipt = _finite_number(capture.get("received_monotonic_s"))
        count = capture.get("captured_points")
        observation = capture.get("observation") or {}
        with self._lock:
            last_stamp, last_receipt = self._last_stamp, self._last_receipt
        if (not isinstance(payload, bytes) or not 0 < len(payload) <= self._max_bytes
                or len(payload) % 24 or type(count) is not int or count != len(payload) // 24
                or count > self._max_points or capture.get("source_points") != count
                or capture.get("xyz_sha256") != hashlib.sha256(payload).hexdigest()
                or capture.get("encoding") != "float64_le_xyz"
                or capture.get("topic") != context["scan"]["source_topic"]
                or capture.get("pipeline_stage") != context["source_pipeline_stage"]
                or capture.get("source_frame") != context["source_frame"]
                or observation.get("observer_id") != context["observer_id"]
                or observation.get("publisher_epoch") != context["observer_epoch"]
                or capture.get("observer_epoch") != context["observer_epoch"]
                or observation.get("source_stamp_ns") != capture.get("source_stamp_ns")
                or capture.get("receipt_clock") != "OBSERVER_HOST_MONOTONIC"
                or capture.get("source_order_preserved") is not True
                or capture.get("zero_rows_preserved") is not True
                or capture.get("nonfinite_rows_preserved") is not True
                or capture.get("sampling_applied") is not False
                or capture.get("spatial_filter_applied") is not False
                or capture.get("transform_applied") is not False
                or capture.get("units") != "m"
                or stamp is None or stamp <= last_stamp or receipt is None or receipt <= last_receipt
                or (last_receipt > 0. and receipt - last_receipt > 1.)
                or not 0 <= self._now() - receipt <= 1.
                or not np.isfinite(np.frombuffer(payload, dtype="<f8")).all()):
            raise SensorTrackingConflict("NEW_FULL_SCAN_IDENTITY_OR_FRESHNESS_FAILED")
        return stamp, receipt

    @staticmethod
    def _validate_alignment(result: dict[str, Any], context: dict[str, Any],
                            scan: dict[str, Any], stamp: int, *, allow_ambiguous: bool = False) -> tuple[list[list[float]], float, float]:
        try:
            index = result["selected_candidate"]
            candidate = result["candidates"][index]
            matrix = _rigid(candidate["map_from_scan"])
            rmse = _finite_number(candidate["rmse_m"])
            overlap = _finite_number(candidate["overlap"])
            good = (result["status"] == "OBSERVATION_ONLY_UNVERIFIED"
                    and result["map_frame"] == context["map_frame"]
                    and result["scan_frame"] == context["source_frame"]
                    and result["frame_id"] == context["source_frame"]
                    and result["map_revision"] == context["map_revision"]
                    and result["observer_id"] == context["observer_id"]
                    and result["source_stamp_ns"] == str(stamp)
                    and result["session_id"] == context["observer_epoch"]
                    and result["map_id"] == "sha256:" + context["map"]["sha256"]
                    and result["input_points"] == scan["point_count"]
                    and result["reference_points"] == context["map"]["point_count"]
                    and type(index) is int and index >= 0
                    and result["selection_policy"] == SELECTION_POLICY
                    and _admissible_gates(result, candidate, allowed=allow_ambiguous)
                    and matrix is not None and rmse is not None and rmse >= 0.
                    and overlap is not None and .60 <= overlap <= 1.
                    and type(candidate["scan_count"]) is int
                    and candidate["scan_count"] == scan["point_count"]
                    and type(candidate["inlier_count"]) is int
                    and 60 <= candidate["inlier_count"] <= candidate["scan_count"]
                    and type(candidate["distinct_inlier_voxel_count"]) is int
                    and 60 <= candidate["distinct_inlier_voxel_count"] <= candidate["inlier_count"]
                    and (_finite_number(candidate["geometry_min_max_eigen_ratio"]) or 0.) >= .002
                    and (_finite_number(candidate["inlier_geometry_min_max_eigen_ratio"]) or 0.) >= .002
                    and _finite_number(candidate["full_scan_rmse_m"]) is not None
                    and candidate["full_scan_rmse_m"] >= 0.
                    and candidate["refinement_stationary"] is True)
            if not good:
                raise ValueError("local selected candidate failed")
            assert matrix is not None and rmse is not None and overlap is not None
            return matrix, rmse, overlap
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise SensorTrackingConflict("LOCAL_ALIGNMENT_REJECTED_OR_AMBIGUOUS") from exc

    def _run(self, generation: int, cancel: threading.Event, process: Any) -> None:
        try:
            with self._lock:
                context = copy.deepcopy(self._context)
                seed = copy.deepcopy(self._last_matrix)
            assert context is not None and seed is not None
            reference = self._catalog.raw_global_reference(context["map_id"], context["map_revision"],
                max_points=self._max_points, max_bytes=self._max_bytes)
            map_bytes = reference.pop("xyz_bytes")
            old = context["map"]
            if (reference.get("sha256") != old["sha256"]
                    or reference.get("source_sha256") != old["source_sha256"]
                    or reference.get("point_count") != old["point_count"]
                    or reference.get("frame_id") != context["map_frame"]
                    or reference.get("units") != "m"
                    or reference.get("source_order_preserved") is not True
                    or reference.get("zero_rows_preserved") is not True
                    or reference.get("nonfinite_rows_preserved") is not True
                    or hashlib.sha256(map_bytes).hexdigest() != old["sha256"]
                    or not np.isfinite(np.frombuffer(map_bytes, dtype="<f8")).all()):
                raise SensorTrackingConflict("MAP_INPUT_CHANGED")
            with self._lock:
                self._require_session_live_locked()
                if cancel.is_set() or generation != self._generation:
                    return
            process.start(map_bytes, context, cancel)
            with self._lock:
                self._resource_admission = (process.resource_admission_snapshot()
                    if hasattr(process, "resource_admission_snapshot") else None)
                self._require_session_live_locked()
                if cancel.is_set() or generation != self._generation:
                    return
                self._state = "ACQUIRING_FRESH_SCAN"
            while not cancel.is_set():
                payload, capture = self._capture(context, cancel)
                stamp, receipt = self._validate_capture(payload, capture, context)
                if not self._current_matches(context):
                    raise SensorTrackingConflict("CURRENT_SOURCE_OR_MAP_CHANGED")
                scan = {"encoding": "float64_le_xyz", "point_count": capture["captured_points"],
                        "sha256": capture["xyz_sha256"]}
                align_context = {key: context[key] for key in
                                 ("map_id", "map_revision", "map_frame", "source_frame",
                                  "observer_id", "observer_epoch")}
                align_context.update(map={key: context["map"][key] for key in
                                          ("encoding", "point_count", "sha256")},
                                     scan=scan, source_stamp_ns=str(stamp))
                with self._lock:
                    self._require_session_live_locked()
                    if cancel.is_set() or generation != self._generation:
                        return
                result = process.align(payload, align_context, seed, cancel)
                matrix, rmse, overlap = self._validate_alignment(
                    result, context, scan, stamp, allow_ambiguous=self._allow_ambiguous)
                if not self._current_matches(context) or not 0 <= self._now() - receipt <= 1.:
                    raise SensorTrackingConflict("ALIGNMENT_REPLY_STALE_OR_SOURCE_CHANGED")
                if not _motion_consistent(seed, matrix):
                    raise SensorTrackingConflict("TEMPORAL_POSE_JUMP")
                with self._lock:
                    self._require_session_live_locked()
                    if cancel.is_set() or generation != self._generation:
                        return
                    self._last_stamp, self._last_receipt, self._last_matrix = stamp, receipt, matrix
                    self._last_alignment = copy.deepcopy(result)
                    if (self._ambiguity_override is None
                            and valid_ambiguity_override(result, allowed=self._allow_ambiguous)):
                        self._ambiguity_override = copy.deepcopy(result["ambiguity_override"])
                        self._ambiguity_source = "LOCAL"
                    self._confirmations += 1
                    seed = matrix
                    self._source = {"topic": capture["topic"], "frame_id": capture["source_frame"],
                                    "observer_id": context["observer_id"],
                                    "observer_epoch": context["observer_epoch"],
                                    "source_stamp_ns": str(stamp), "received_monotonic_s": receipt,
                                    "age_s": max(0., self._now() - receipt)}
                    if self._confirmations >= 3:
                        self._state, self._reason = "SENSOR_CANDIDATE", None
                        self._sensor_pose = {"T_map_sensor": matrix, "source_stamp_ns": str(stamp),
                                             "received_monotonic_s": receipt,
                                             "map_frame": context["map_frame"],
                                             "source_frame": context["source_frame"],
                                             "rmse_m": rmse, "overlap": overlap}
                        self._trail.append({"source_stamp_ns": str(stamp),
                                            "received_monotonic_s": receipt, "T_map_sensor": matrix})
                        self._trail = self._trail[-_MAX_TRAIL:]
                    else:
                        self._state = "ACQUIRING_FRESH_SCAN"
        except Exception as exc:
            with self._lock:
                if not cancel.is_set() and generation == self._generation:
                    raw_reason = str(exc)
                    reason = (raw_reason if isinstance(exc, SensorTrackingConflict)
                              or (raw_reason.startswith("SENSOR_") and raw_reason.isupper()
                                  and len(raw_reason) <= 80) else "LOCAL_TRACKING_UNAVAILABLE")
                    state = "STALE" if "STALE" in reason or "FRESHNESS" in reason else "LOST"
                    self._lose_locked(state, reason)
        finally:
            if hasattr(process, "resource_admission_snapshot"):
                with self._lock:
                    if self._thread is threading.current_thread():
                        self._resource_admission = process.resource_admission_snapshot()
            self._close_owned_process(process)
            with self._lock:
                if self._thread is threading.current_thread():
                    self._cancel_session_watchdog_locked()
                    self._capture_id = None

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if (self._state == "STOPPED" and self._process is None
                    and self._cleanup_complete is not False
                    and (self._thread is None or not self._thread.is_alive())):
                return self._snapshot_locked()
            self._cancel_session_watchdog_locked()
            self._generation += 1
            if self._cancel is not None:
                self._cancel.set()
            capture_id, process, worker = self._capture_id, self._process, self._thread
            self._state, self._reason = "STOPPED", "OPERATOR_STOPPED"
            self._sensor_pose, self._source = None, None
            self._trail.clear()
            self._confirmations = 0
        if capture_id:
            try:
                self._agent.cancel_raw_pointcloud_capture(capture_id)
            except Exception:
                pass
        if process is not None:
            self._close_owned_process(process)
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=1.)
        with self._lock:
            if worker is not None and not worker.is_alive() and self._thread is worker:
                self._thread, self._cancel, self._capture_id = None, None, None
        return self.snapshot()

    def close(self) -> bool:
        with self._lock:
            self._closed = True
        self.stop()
        with self._lock:
            return ((self._thread is None or not self._thread.is_alive())
                    and self._process is None and self._cleanup_complete is not False)


def configure_sensor_tracking(runtime: Any) -> None:
    from ..relocalization.external_global_observation import ExternalGlobalObservationRunner
    from ..relocalization.sensor_tracking_process import (
        SensorTrackingExecutionPolicy, SensorTrackingProcess,
    )

    runner = ExternalGlobalObservationRunner.from_environment()
    policy = SensorTrackingExecutionPolicy.from_environment()
    if policy.processing_budget_s is None and not runner.resource_scope_enabled:
        raise ValueError("disabled tracking budget requires user_scope_v1 resource mode")
    readback = policy.snapshot()
    readback["resource_mode"] = "user_scope_v1" if runner.resource_scope_enabled else "DIRECT_LEGACY"
    runtime.sensor_tracking = SensorTrackingOwner(runtime.saved_maps, runtime.require_agent(),
        runtime.global_observation, lambda: SensorTrackingProcess(runner, execution_policy=policy),
        pin_provider=runner.status, allow_ambiguous=runner.allow_ambiguous,
        execution_policy=readback)


async def close_sensor_tracking(runtime: Any, logger: Any) -> None:
    if runtime.sensor_tracking is None:
        return
    try:
        if not await asyncio.to_thread(runtime.sensor_tracking.close):
            logger.error("sensor tracking cleanup did not settle within its bounded wait")
    except Exception:
        logger.exception("sensor tracking shutdown failed")
