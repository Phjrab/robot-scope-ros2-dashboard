"""Local historical observation orchestration, separate from live alignment.

HTTP accepts opaque catalogue identities only. Immutable numeric input buffers
stay in this owner and are handed directly to a trusted local subprocess runner.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import secrets
import threading
import time
from typing import Any

from ..relocalization.global_observation_jobs import (
    GlobalObservationBusy, GlobalObservationConflict, GlobalObservationJobManager,
    GlobalObservationNotFound, GlobalObservationUnavailable, GlobalObservationValidationError,
)
from ..saved_maps import SavedMapError


_FLAGS = dict(historical_only=True, current_result=None, body_pose=None, tracking_verified=False,
              body_pose_verified=False, body_extrinsic_verified=False,
              operational_application="NOT_RUN", absolute_accuracy_m=None)
_TERMINAL = {"succeeded", "cancelled", "failed", "stale", "timed_out"}


def _lossless_json(value: Any) -> Any:
    """Keep large source integers exact across the browser JSON boundary."""
    if type(value) is int and abs(value) > 9_007_199_254_740_991:
        return str(value)
    if isinstance(value, dict):
        return {key: _lossless_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_lossless_json(item) for item in value]
    return value


class GlobalObservationCoordinator:
    def __init__(self, catalog: Any, agent: Any, runner: Any, *, capture_timeout_s: float = 5.,
                 timeout_s: float = 120., max_points: int = 1_000_000,
                 max_bytes: int = 32 * 1024 * 1024, max_jobs: int = 32) -> None:
        self._catalog, self._agent, self._runner = catalog, agent, runner
        self._capture_timeout_s, self._max_points, self._max_bytes = capture_timeout_s, max_points, max_bytes
        self._timeout_s, self._max_jobs = timeout_s, max_jobs
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._requests: dict[str, str] = {}
        self._events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._tickets: dict[str, tuple[bytes, bytes, dict[str, Any], threading.Event]] = {}
        self._generation, self._active, self._closed = 0, None, False
        self._manager = GlobalObservationJobManager(self._run_ticket, self._current_context,
                                                     timeout_s=timeout_s)

    def provider_status(self) -> dict[str, Any]:
        try:
            status = dict(self._runner.status())
            if status.get("available") is not True:
                return dict(available=False, reason=status.get("reason") or "TRUSTED_LOCAL_RUNNER_UNAVAILABLE",
                            backend_id=status.get("backend_id"))
            return dict(available=True, reason=None, backend_id=status.get("backend_id"))
        except Exception:
            return dict(available=False, reason="TRUSTED_LOCAL_RUNNER_UNAVAILABLE", backend_id=None)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latest = next(reversed(self._jobs.values()), None) if self._jobs else None
            return dict(schema="robot-scope.raw-global-observations.v1", provider=self.provider_status(),
                        generation=self._generation, closed=self._closed,
                        active=self._public(self._jobs[self._active]) if self._active else None,
                        latest=self._public(latest) if latest else None, **_FLAGS)

    @staticmethod
    def _public(job: dict[str, Any]) -> dict[str, Any]:
        public = copy.deepcopy({key: value for key, value in job.items() if not key.startswith("_")})
        received = ((public.get("captured_context") or {}).get("scan") or {}).get("received_monotonic_s")
        public["capture_age_s"] = (max(0., time.monotonic() - received)
            if type(received) in (int, float) and math.isfinite(received) else None)
        public["capture_age_basis"] = "OBSERVER_HOST_RECEIPT_MONOTONIC_ONLY"
        return public

    def _get(self, job_id: str) -> dict[str, Any]:
        if job_id not in self._jobs:
            raise GlobalObservationNotFound("raw global observation job was not found")
        return self._jobs[job_id]

    def job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return self._public(self._get(job_id))

    def start(self, request_id: str, map_id: str, map_revision: str) -> dict[str, Any]:
        if (not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", request_id)
                or not isinstance(map_id, str) or not re.fullmatch(r"[a-f0-9]{24}", map_id)
                or not isinstance(map_revision, str) or not re.fullmatch(r"[a-f0-9]{64}", map_revision)):
            raise GlobalObservationValidationError("invalid raw global observation request")
        with self._lock:
            previous = self._requests.get(request_id)
            if previous:
                job = self._jobs[previous]
                if (job["map_id"], job["map_revision"]) != (map_id, map_revision):
                    raise GlobalObservationConflict("request_id was already used for different input")
                return self._public(job)
            if self._closed:
                raise GlobalObservationUnavailable("raw global observation owner is closed")
            if self._active:
                raise GlobalObservationBusy("a raw global observation worker is still active")
            if not self.provider_status()["available"]:
                raise GlobalObservationUnavailable("TRUSTED_LOCAL_RUNNER_UNAVAILABLE")
            if self._agent.raw_pointcloud_context_snapshot().get("pipeline_stage") not in {"raw", "converted"}:
                raise GlobalObservationUnavailable("RAW_OR_CONVERTED_POINTCLOUD_SOURCE_REQUIRED")
            try:
                metadata = self._catalog.metadata(map_id)
            except SavedMapError as exc:
                raise GlobalObservationConflict("saved map changed or unavailable") from exc
            if (metadata.get("revision") != map_revision or metadata.get("kind") != "pointcloud3d"
                    or metadata.get("format") != "pcd-binary"):
                raise GlobalObservationConflict("raw global reference requires one unchanged binary PCD")
            self._generation += 1
            job_id, started = secrets.token_hex(12), time.monotonic()
            job = dict(schema="robot-scope.raw-global-observation-job.v1", job_id=job_id,
                       request_id=request_id, generation=self._generation, map_id=map_id,
                       map_revision=map_revision, state="capturing", reason=None,
                       captured_context=None, observed_completion_context=None,
                       created_monotonic_s=started, completed_monotonic_s=None,
                       deadline_monotonic_s=started + self._capture_timeout_s + self._timeout_s,
                       worker_active=True, cancellation_requested=False, result=None, **_FLAGS)
            event = threading.Event()
            self._jobs[job_id], self._requests[request_id], self._events[job_id] = job, job_id, event
            self._active = job_id
            worker = threading.Thread(target=self._prepare, args=(job_id, event),
                                      name=f"raw-global-capture-{self._generation}", daemon=True)
            self._threads[job_id] = worker
            try:
                worker.start()
            except RuntimeError as exc:
                job.update(state="failed", reason="WORKER_START_FAILED", worker_active=False,
                           completed_monotonic_s=time.monotonic())
                self._active = None
                self._threads.pop(job_id, None)
                self._events.pop(job_id, None)
                raise GlobalObservationUnavailable("raw global worker could not start") from exc
            return self._public(job)

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._get(job_id)
            if job["state"] in _TERMINAL:
                return self._public(job)
            self._generation += 1
            self._events[job_id].set()
            job.update(state="cancelled", reason="CANCELLED", cancellation_requested=True,
                       completed_monotonic_s=time.monotonic(), result=None)
            capture_id, manager_id = job.get("_capture_id"), job.get("_manager_id")
        if manager_id:
            self._manager.cancel(manager_id)
        else:
            # Covers admission/context-check and the interval before the
            # supervisor has recorded the manager ID. The ticket also retains
            # this cancellation event, so admission starting later cannot run.
            self._manager.invalidate("CANCELLED_DURING_CAPTURE_OR_ADMISSION")
        if capture_id:
            self._agent.cancel_raw_pointcloud_capture(capture_id)
        return self.job(job_id)

    def _current_context(self, captured: dict[str, Any]) -> dict[str, Any]:
        metadata = self._catalog.metadata(captured["map_id"])
        live = self._agent.raw_pointcloud_context_snapshot()
        observation = live.get("observation") or {}
        received = observation.get("received_monotonic_s")
        age = time.monotonic() - received if type(received) in (int, float) else math.inf
        if (live.get("topic") != captured["scan"]["source_topic"]
                or live.get("pipeline_stage") != captured["source_pipeline_stage"]
                or not math.isfinite(age) or not 0 <= age <= 1.):
            raise GlobalObservationUnavailable("raw source context changed or receipt is unavailable")
        return dict(map_id=captured["map_id"], map_revision=metadata.get("revision"),
                    map_frame=captured["map_frame"], source_frame=live.get("frame_id"),
                    observer_id=observation.get("observer_id"), observer_epoch=observation.get("publisher_epoch"),
                    source_stamp_ns=observation.get("source_stamp_ns"),
                    receipt_age_s=age, receipt_clock="OBSERVER_HOST_MONOTONIC",
                    source_clock_verified=False)

    def _run_ticket(self, payload: dict[str, Any], *, cancel_event: threading.Event) -> dict[str, Any]:
        with self._lock:
            buffers = self._tickets.pop(payload["input_ticket"])
        scan_bytes, map_bytes, context, capture_cancel = buffers
        if capture_cancel.is_set():
            cancel_event.set()
            raise GlobalObservationUnavailable("capture was cancelled before runner admission")
        return self._runner.run_arrays(scan_bytes=scan_bytes, map_bytes=map_bytes,
                                       context=context, cancel_event=cancel_event)

    def _prepare(self, job_id: str, cancel: threading.Event) -> None:
        capture_id = manager_id = ticket = None
        try:
            with self._lock:
                job = self._jobs[job_id]
                map_id, revision = job["map_id"], job["map_revision"]
            if cancel.is_set():
                return
            capture = self._agent.request_raw_pointcloud_capture(timeout_s=self._capture_timeout_s,
                                                                 max_points=self._max_points,
                                                                 max_bytes=self._max_bytes)
            capture_id = capture["capture_id"]
            with self._lock:
                job["_capture_id"] = capture_id
            reference = self._catalog.raw_global_reference(map_id, revision, max_points=self._max_points,
                                                            max_bytes=self._max_bytes)
            while not cancel.is_set():
                capture = self._agent.raw_pointcloud_capture_snapshot(capture_id)
                if capture and capture["state"] == "ready":
                    break
                if not capture or capture["state"] in {"failed", "cancelled", "stale", "timed_out", "consumed"}:
                    reason = (capture or {}).get("reason") or "CAPTURE_UNAVAILABLE"
                    state = (capture or {}).get("state")
                    with self._lock:
                        if not cancel.is_set():
                            job.update(state=state if state in _TERMINAL else "failed", reason=reason,
                                       completed_monotonic_s=time.monotonic())
                    return
                cancel.wait(.025)
            if cancel.is_set():
                return
            capture = self._agent.take_raw_pointcloud_capture(capture_id)
            scan_bytes, map_bytes = capture.pop("xyz_bytes"), reference.pop("xyz_bytes")
            observation = capture.get("observation") or {}
            scan = _lossless_json(dict(capture, sha256=capture["xyz_sha256"],
                                      point_count=capture["captured_points"], shape=[capture["captured_points"], 3],
                                      dtype="<f8", source_topic=capture["topic"]))
            source_stage = capture.get("pipeline_stage")
            if source_stage not in {"raw", "converted"}:
                raise GlobalObservationUnavailable("received source pipeline stage is unsupported")
            context = dict(map_id=map_id, map_revision=revision, map_frame=reference["frame_id"],
                           source_frame=capture["source_frame"], observer_id=observation.get("observer_id"),
                           observer_epoch=observation.get("publisher_epoch"),
                           source_stamp_ns=capture["source_stamp_ns"], scan=scan, map=reference,
                           source_pipeline_stage=source_stage, upstream_processing_verified=False,
                           full_original_scope="RECEIVED_POINTCLOUD2_XYZ_ONLY",
                           original_raw_sensor_archive=False,
                           source_stamp_basis="RECEIVED_POINTCLOUD2_HEADER_UNVERIFIED",
                           source_clock="UNVERIFIED", source_clock_verified=False,
                           deskew_verified=False, deskew_applied_by_this_validation=False,
                           map_axes_verified=False, body_extrinsic_verified=False)
            ticket = secrets.token_hex(16)
            canonical = json.dumps(context, sort_keys=True, separators=(",", ":"), allow_nan=False)
            with self._lock:
                if cancel.is_set():
                    return
                self._tickets[ticket] = scan_bytes, map_bytes, context, cancel
                job["captured_context"] = copy.deepcopy(context)
            started = self._manager.start(job_id, context, dict(input_ticket=ticket,
                scan_sha256=scan["sha256"], map_array_sha256=reference["sha256"],
                input_context_sha256=hashlib.sha256(canonical.encode()).hexdigest()))
            manager_id = started["job_id"]
            with self._lock:
                job["_manager_id"] = manager_id
                if not cancel.is_set():
                    job.update(state="running", deadline_monotonic_s=started["deadline_monotonic_s"])
            if cancel.is_set():
                self._manager.cancel(manager_id)
            while not self._manager.wait(manager_id, .1):
                current = self._manager.job(manager_id)
                if current["state"] in _TERMINAL:
                    self._apply_manager(job_id, current, cancel)
            self._apply_manager(job_id, self._manager.job(manager_id), cancel)
        except GlobalObservationConflict:
            self._fail(job_id, "stale", "CONTEXT_CHANGED", cancel)
        except SavedMapError:
            self._fail(job_id, "stale", "MAP_CHANGED_OR_UNAVAILABLE", cancel)
        except Exception:
            self._fail(job_id, "failed", "CAPTURE_OR_RUNNER_UNAVAILABLE", cancel)
        finally:
            if capture_id:
                try:
                    self._agent.cancel_raw_pointcloud_capture(capture_id)
                except Exception:
                    pass
            with self._lock:
                if ticket:
                    self._tickets.pop(ticket, None)
                self._jobs[job_id]["worker_active"] = False
                self._threads.pop(job_id, None)
                self._events.pop(job_id, None)
                if self._active == job_id:
                    self._active = None
                while len(self._jobs) > self._max_jobs:
                    oldest = next(iter(self._jobs))
                    previous = self._jobs.pop(oldest)
                    self._requests.pop(previous["request_id"], None)

    def _fail(self, job_id: str, state: str, reason: str, cancel: threading.Event) -> None:
        with self._lock:
            if not cancel.is_set():
                self._jobs[job_id].update(state=state, reason=reason,
                    completed_monotonic_s=time.monotonic(), result=None)

    def _apply_manager(self, job_id: str, managed: dict[str, Any], cancel: threading.Event) -> None:
        with self._lock:
            if cancel.is_set():
                return
            job = self._jobs[job_id]
            for key in ("state", "reason", "completed_monotonic_s", "cancellation_requested",
                        "observed_completion_context", "result"):
                job[key] = copy.deepcopy(managed[key])
            if job["result"]:
                job["result"].update(job_id=job_id, generation=job["generation"])

    def close(self) -> bool:
        with self._lock:
            self._closed = True
            active = self._active
        if active:
            self.cancel(active)
        settled = self._manager.close()
        with self._lock:
            worker = self._threads.get(active or "")
        if worker:
            worker.join(timeout=1.)
        return settled and (worker is None or not worker.is_alive())


def configure_global_observation(runtime: Any) -> None:
    from ..relocalization.external_global_observation import ExternalGlobalObservationRunner

    runtime.global_observation = GlobalObservationCoordinator(
        runtime.saved_maps, runtime.require_agent(), ExternalGlobalObservationRunner.from_environment())


async def close_global_observation(runtime: Any, logger: Any) -> None:
    import asyncio

    if runtime.global_observation is None:
        return
    try:
        settled = await asyncio.to_thread(runtime.global_observation.close)
        if not settled:
            logger.error("raw global observation cleanup did not settle within its bounded wait")
    except Exception:
        logger.exception("raw global observation shutdown failed")
