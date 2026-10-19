"""ROS-free ownership of cancellable raw global observation jobs.

Every successful result describes its immutable captured input and remains
historical only. This owner never promotes a result to a current pose, performs
odometry propagation, imports a registration backend, or publishes to ROS.
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
from collections.abc import Mapping
from typing import Any, Callable, Protocol


class GlobalObservationRunner(Protocol):
    def __call__(self, payload: dict[str, Any], *, cancel_event: threading.Event) -> Mapping[str, Any]: ...


class ContextSnapshotProvider(Protocol):
    def __call__(self, captured_context: dict[str, Any]) -> Mapping[str, Any]: ...


class GlobalObservationError(RuntimeError):
    pass


class GlobalObservationBusy(GlobalObservationError):
    pass


class GlobalObservationConflict(GlobalObservationError):
    pass


class GlobalObservationNotFound(GlobalObservationError):
    pass


class GlobalObservationUnavailable(GlobalObservationError):
    pass


class GlobalObservationValidationError(GlobalObservationError, ValueError):
    pass


_FENCES = ("map_id", "map_revision", "map_frame", "source_frame", "observer_id", "observer_epoch")
_TERMINAL = frozenset({"succeeded", "cancelled", "failed", "stale", "timed_out"})
_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SOURCE_STAMP = re.compile(r"[1-9][0-9]{0,19}\Z")


def _json_object(value: Any, *, maximum_bytes: int) -> tuple[str, dict[str, Any]]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise GlobalObservationValidationError("an object with string keys is required")
    try:
        def check(item: Any) -> None:
            if isinstance(item, dict):
                if any(not isinstance(key, str) for key in item):
                    raise ValueError("nested object keys must be strings")
                for nested in item.values():
                    check(nested)
            elif isinstance(item, list):
                for nested in item:
                    check(nested)
            elif item is not None and type(item) not in (str, bool, int, float):
                raise ValueError("only JSON-native input values are supported")
        plain = dict(value)
        check(plain)
        encoded = json.dumps(plain, sort_keys=True, separators=(",", ":"), allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise GlobalObservationValidationError("job input or output must be strict JSON") from exc
    if len(encoded.encode("utf-8")) > maximum_bytes:
        raise GlobalObservationValidationError("job input or output exceeds its byte limit")
    return encoded, decoded


def _context(value: Any) -> tuple[str, dict[str, Any]]:
    encoded, normalized = _json_object(value, maximum_bytes=16_384)
    if any(not isinstance(normalized.get(key), str) or not normalized[key].strip()
           or len(normalized[key]) > 240 for key in _FENCES):
        raise GlobalObservationValidationError("explicit map, frame and observer fences are required")
    if not isinstance(normalized.get("source_stamp_ns"), str) or not _SOURCE_STAMP.fullmatch(normalized["source_stamp_ns"]):
        raise GlobalObservationValidationError("source_stamp_ns must be an exact positive decimal string")
    return encoded, normalized


def _context_changed(captured: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    # Normal new scans may advance during global search. They do not make an
    # old capture current, and they do not invalidate its historical evidence.
    return (any(captured[key] != current[key] for key in _FENCES)
            or int(current["source_stamp_ns"]) < int(captured["source_stamp_ns"]))


class GlobalObservationJobManager:
    """Own one actual runner until it has returned, including after cancellation.

    A duplicate request ID with the same canonical context/payload returns the
    retained job; reusing that ID for different input is a conflict. A different
    request while a runner still owns the slot is busy. Idempotency lasts for the
    bounded retained history (32 jobs by default), not across process restarts.

    Cancellation/deadline invalidate publication immediately. They cannot stop
    arbitrary Python code: the injected production runner must kill/reap its
    subprocess when cancel_event is set. Until it returns the slot stays busy.
    close() returns whether that cleanup settled within its bounded wait.
    """

    def __init__(self, runner: GlobalObservationRunner, context_provider: ContextSnapshotProvider, *,
                 timeout_s: float = 120., close_timeout_s: float = 1., max_jobs: int = 32,
                 max_payload_bytes: int = 16 * 1024 * 1024, max_result_bytes: int = 65_536,
                 now: Callable[[], float] = time.monotonic) -> None:
        if (not callable(runner) or not callable(context_provider)
                or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 300
                or type(close_timeout_s) not in (int, float) or not math.isfinite(close_timeout_s) or not 0 <= close_timeout_s <= 5
                or type(max_jobs) is not int or not 1 <= max_jobs <= 256
                or type(max_payload_bytes) is not int or max_payload_bytes < 1
                or type(max_result_bytes) is not int or max_result_bytes < 1):
            raise GlobalObservationValidationError("invalid job owner configuration")
        self._runner, self._context_provider, self._now = runner, context_provider, now
        self._timeout_s, self._close_timeout_s = float(timeout_s), float(close_timeout_s)
        self._max_jobs, self._max_payload_bytes, self._max_result_bytes = max_jobs, max_payload_bytes, max_result_bytes
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._request_ids: dict[str, str] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._events: dict[str, threading.Event] = {}
        self._settled: dict[str, threading.Event] = {}
        self._timers: dict[str, threading.Timer] = {}
        self._active_job_id: str | None = None
        self._generation = 0
        self._closed = False

    def start(self, request_id: str, context: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
            raise GlobalObservationValidationError("request_id is invalid")
        context_json, captured = _context(context)
        payload_json, _ = _json_object(payload, maximum_bytes=self._max_payload_bytes)
        signature = hashlib.sha256((context_json + "\n" + payload_json).encode()).hexdigest()
        with self._lock:
            duplicate = self._admit(request_id, signature)
            if duplicate is not None:
                return duplicate
            admission_generation = self._generation
        # The provider is deliberately outside the owner lock. It may acquire a
        # catalogue/telemetry lock; cancellation must remain responsive.
        try:
            _, current = _context(self._context_provider(copy.deepcopy(captured)))
        except Exception as exc:
            raise GlobalObservationUnavailable("capture context snapshot is unavailable") from exc
        if _context_changed(captured, current):
            raise GlobalObservationConflict("capture context changed before job admission")
        with self._lock:
            duplicate = self._admit(request_id, signature)
            if duplicate is not None:
                return duplicate
            if self._generation != admission_generation:
                raise GlobalObservationConflict("observation generation changed during job admission")
            self._generation += 1
            generation, job_id, started = self._generation, secrets.token_hex(12), self._now()
            job = {"schema": "robot-scope.raw-global-observation-job.v1", "job_id": job_id,
                   "request_id": request_id, "generation": generation, "state": "running", "reason": None,
                   "captured_context": captured, "observed_completion_context": None,
                   "created_monotonic_s": started, "completed_monotonic_s": None,
                   "deadline_monotonic_s": started + self._timeout_s, "worker_active": True,
                   "cancellation_requested": False, "historical_only": True,
                   "current_result": None, "body_pose": None, "tracking_verified": False,
                   "body_pose_verified": False, "body_extrinsic_verified": False,
                   "operational_application": "NOT_RUN", "absolute_accuracy_m": None,
                   "result": None, "_signature": signature}
            self._jobs[job_id], self._request_ids[request_id] = job, job_id
            self._active_job_id = job_id
            cancel, settled = threading.Event(), threading.Event()
            self._events[job_id], self._settled[job_id] = cancel, settled
            worker = threading.Thread(target=self._run, args=(job_id, generation, payload_json, cancel),
                                      name=f"raw-global-observation-{generation}", daemon=True)
            timer = threading.Timer(self._timeout_s, self._expire, args=(job_id, generation))
            timer.daemon = True
            self._threads[job_id], self._timers[job_id] = worker, timer
            try:
                worker.start()
                timer.start()
            except RuntimeError:
                cancel.set()
                self._terminal(job, "failed", "WORKER_START_FAILED")
                if not worker.is_alive():
                    self._release(job_id)
                raise GlobalObservationUnavailable("job worker could not start")
            return self._public(job)

    def _admit(self, request_id: str, signature: str) -> dict[str, Any] | None:
        if self._closed:
            raise GlobalObservationUnavailable("job owner is closed")
        previous = self._request_ids.get(request_id)
        if previous is not None:
            job = self._jobs[previous]
            if job["_signature"] != signature:
                raise GlobalObservationConflict("request_id was already used for different input")
            return self._public(job)
        if self._active_job_id is not None:
            raise GlobalObservationBusy("a raw global observation worker is still active")
        return None

    def job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return self._public(self._get(job_id))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active = self._jobs.get(self._active_job_id or "")
            latest = next(reversed(self._jobs.values()), None) if self._jobs else None
            return {"schema": "robot-scope.raw-global-observations.v1", "generation": self._generation,
                    "closed": self._closed, "active": self._public(active) if active else None,
                    "latest": self._public(latest) if latest else None, "current_result": None,
                    "historical_only": True, "body_pose": None, "tracking_verified": False,
                    "body_pose_verified": False, "body_extrinsic_verified": False,
                    "operational_application": "NOT_RUN", "absolute_accuracy_m": None}

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._get(job_id)
            if job["state"] not in _TERMINAL:
                self._generation += 1
                self._events[job_id].set()
                job["cancellation_requested"] = True
                self._terminal(job, "cancelled", "CANCELLED")
            return self._public(job)

    def invalidate(self, reason: str = "CONTEXT_CHANGED") -> None:
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 240:
            raise GlobalObservationValidationError("invalidation reason is invalid")
        with self._lock:
            self._generation += 1
            job = self._jobs.get(self._active_job_id or "")
            if job is not None and job["state"] not in _TERMINAL:
                self._events[job["job_id"]].set()
                job["cancellation_requested"] = True
                self._terminal(job, "stale", reason)

    def wait(self, job_id: str, timeout_s: float = 1.) -> bool:
        """Bounded settlement wait for callers/tests; never called by HTTP polling."""
        if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 <= timeout_s <= 5:
            raise GlobalObservationValidationError("settlement wait must be between 0 and 5 seconds")
        with self._lock:
            self._get(job_id)
            settled = self._settled[job_id]
        return settled.wait(timeout_s)

    def close(self) -> bool:
        with self._lock:
            self._closed = True
            self._generation += 1
            job = self._jobs.get(self._active_job_id or "")
            if job is not None:
                self._events[job["job_id"]].set()
                job["cancellation_requested"] = True
                if job["state"] not in _TERMINAL:
                    self._terminal(job, "cancelled", "OWNER_CLOSED")
            for timer in self._timers.values():
                timer.cancel()
            settled = self._settled.get(self._active_job_id or "")
        return settled is None or settled.wait(self._close_timeout_s)

    def _get(self, job_id: str) -> dict[str, Any]:
        if not isinstance(job_id, str) or job_id not in self._jobs:
            raise GlobalObservationNotFound("raw global observation job was not found")
        return self._jobs[job_id]

    @staticmethod
    def _public(job: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy({key: value for key, value in job.items() if not key.startswith("_")})

    def _publishable(self, job: dict[str, Any], generation: int, cancel: threading.Event) -> bool:
        return (not self._closed and self._active_job_id == job["job_id"]
                and job["generation"] == generation == self._generation
                and job["state"] == "running" and not cancel.is_set())

    def _terminal(self, job: dict[str, Any], state: str, reason: str | None) -> None:
        job.update(state=state, reason=reason, completed_monotonic_s=self._now(), result=None)

    def _expire(self, job_id: str, generation: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            cancel = self._events.get(job_id)
            if job is not None and cancel is not None and self._publishable(job, generation, cancel):
                cancel.set()
                job["cancellation_requested"] = True
                self._terminal(job, "timed_out", "DEADLINE_EXCEEDED")

    def _run(self, job_id: str, generation: int, payload_json: str, cancel: threading.Event) -> None:
        try:
            with self._lock:
                job = self._jobs[job_id]
                if not self._publishable(job, generation, cancel):
                    return
                captured = copy.deepcopy(job["captured_context"])
            raw = self._runner(json.loads(payload_json), cancel_event=cancel)
            with self._lock:
                if not self._publishable(job, generation, cancel):
                    return
            _, current = _context(self._context_provider(copy.deepcopy(captured)))
            _, observation = _json_object(raw, maximum_bytes=self._max_result_bytes)
            with self._lock:
                if not self._publishable(job, generation, cancel):
                    return
                if self._now() >= job["deadline_monotonic_s"]:
                    cancel.set()
                    job["cancellation_requested"] = True
                    self._terminal(job, "timed_out", "DEADLINE_EXCEEDED")
                elif _context_changed(captured, current):
                    self._terminal(job, "stale", "CONTEXT_CHANGED")
                else:
                    completed = self._now()
                    job.update(state="succeeded", reason=None, completed_monotonic_s=completed,
                               observed_completion_context=current,
                               result={"schema": "robot-scope.raw-global-observation-result.v1",
                                       "job_id": job_id, "generation": generation,
                                       "captured_context": captured, "observation": observation,
                                       "completed_monotonic_s": completed, "historical_only": True,
                                       "current_result": None, "body_pose": None, "tracking_verified": False,
                                       "body_pose_verified": False, "body_extrinsic_verified": False,
                                       "operational_application": "NOT_RUN", "absolute_accuracy_m": None})
        except TimeoutError:
            with self._lock:
                job = self._jobs[job_id]
                if self._publishable(job, generation, cancel):
                    cancel.set()
                    job["cancellation_requested"] = True
                    self._terminal(job, "timed_out", "DEADLINE_EXCEEDED")
        except Exception:
            with self._lock:
                job = self._jobs[job_id]
                if self._publishable(job, generation, cancel):
                    self._terminal(job, "failed", "RUNNER_OR_CONTEXT_FAILED")
        finally:
            with self._lock:
                self._release(job_id)

    def _release(self, job_id: str) -> None:
        timer = self._timers.pop(job_id, None)
        if timer is not None:
            timer.cancel()
        self._jobs[job_id]["worker_active"] = False
        self._events.pop(job_id, None)
        self._threads.pop(job_id, None)
        if self._active_job_id == job_id:
            self._active_job_id = None
        self._settled[job_id].set()
        while len(self._jobs) > self._max_jobs:
            oldest = next(iter(self._jobs))
            if oldest == self._active_job_id:
                break
            previous = self._jobs.pop(oldest)
            self._request_ids.pop(previous["request_id"], None)
            self._settled.pop(oldest, None)
