"""Advisory ownership copies; never run owners' status or lifecycle methods.

This intentionally reads the fixed in-process composition's private fields.
An unsupported owner shape or contended lock is unknown, never idle. It does
not replace admission, physical checks, the broker ledger, or OS ownership.
"""
from __future__ import annotations

import asyncio
import _thread as thread_native
from contextlib import contextmanager
import math
import os
import threading
import time
from typing import Any, Callable


SCHEMA = "robot-scope.ownership-readback.v1"
_LOCK_TYPES = (type(threading.Lock()), type(threading.RLock()))


@contextmanager
def _locked(lock: Any):
    # Never wait behind native work, and never invoke a manager callback.
    if type(lock) not in _LOCK_TYPES:
        raise TypeError("unsupported owner lock")
    if not lock.acquire(blocking=False):
        raise RuntimeError("owner lock busy")
    try:
        yield
    finally:
        lock.release()


def _copy(value: Any, depth: int = 0) -> Any:
    """Copy only bounded builtin JSON values; never invoke copy/reduce hooks."""
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is str and len(value) <= 4096:
        return value
    if depth < 8 and type(value) is dict and len(value) <= 64:
        if any(type(key) is not str for key in value):
            raise TypeError("unsupported owner key")
        return {key: _copy(item, depth + 1) for key, item in value.items()}
    if depth < 8 and type(value) is list and len(value) <= 128:
        return [_copy(item, depth + 1) for item in value]
    raise TypeError("unsupported owner value")


def _bools(*values: Any) -> None:
    if any(type(value) is not bool for value in values):
        raise TypeError("ownership boolean unavailable")


def _fields(value: dict[str, Any], *keys: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise TypeError("owner record unavailable")
    return {key: _copy(value[key]) for key in keys if key in value}


def _task(task: Any) -> bool:
    if task is None:
        return False
    if type(task) not in (asyncio.Future, asyncio.Task):
        raise TypeError("unsupported task")
    return not task.done()


def _thread(thread: Any) -> bool:
    if thread is None:
        return False
    if type(thread) is not threading.Thread:
        raise TypeError("unsupported thread")
    # Thread.is_alive() on CPython 3.10 may finalize an ended thread's
    # _is_stopped/_tstate_lock bookkeeping. Read the pinned stdlib primitives
    # instead; never join, acquire its lifetime lock, or call _stop().
    values = thread.__dict__
    if values.get("_initialized") is not True:
        raise TypeError("uninitialized thread")
    started = values["_started"]
    if type(started) is not threading.Event or type(started._flag) is not bool:
        raise TypeError("unsupported thread startup event")
    if not started._flag:
        return False
    if "_handle" in values:
        # CPython 3.13: is_done is the exact C handle's read-only query, also
        # used by that stdlib's is_alive. It does not join/finalize the Thread.
        handle = values["_handle"]
        if type(handle) is not getattr(thread_native, "_ThreadHandle", None):
            raise TypeError("unsupported native thread handle")
        return not handle.is_done()
    stopped = values["_is_stopped"]
    if type(stopped) is not bool:
        raise TypeError("unsupported legacy thread state")
    if stopped:
        return False
    lifetime_lock = values["_tstate_lock"]
    if type(lifetime_lock) is not type(threading.Lock()):
        raise TypeError("unsupported legacy thread lifetime lock")
    return lifetime_lock.locked()


def _threads(threads: dict[str, Any]) -> bool:
    if type(threads) is not dict:
        raise TypeError("unsupported thread owners")
    return any(_thread(thread) for thread in threads.values())


def _mapping(owner: Any) -> dict[str, Any]:
    manager = owner._manager
    with _locked(manager._lock):
        pipeline = _fields(manager._pipeline, "state", "job_id")
        operation = _fields(manager._operation, "state", "kind")
        preview = _fields(manager._preview, "state")
        retained_process = (manager._pipeline_process is not None
                            or manager._save_process is not None
                            or manager._pipeline_pgid is not None
                            or manager._save_pgid is not None)
    task_active = _task(owner._task)
    recovery_monitor = _task(owner._preview_recovery_task)
    recovery_active = _task(owner._preview_recovery_inflight)
    busy = (pipeline["state"] not in {"idle", "stopped", "failed"}
            or operation["state"] not in {"idle", "succeeded", "failed"}
            or retained_process or task_active or recovery_active)
    return dict(busy=busy, pipeline=pipeline, operation=operation,
                preview=preview, retained_process=retained_process,
                task_active=task_active, preview_recovery_active=recovery_active,
                preview_recovery_monitor_active=recovery_monitor,
                preview_restart_impact=preview["state"] in {"starting", "running", "stopping"})


def _navigation(owner: Any) -> dict[str, Any]:
    with _locked(owner._state_lock):
        startup = _fields(owner._start, "pending", "mapping_owned", "phase", "terminal_cleanup")
        startup.update(token_retained=owner._start["token"] is not None,
                       mapping_job_retained=owner._start["mapping_job_id"] is not None,
                       navigation_job_retained=owner._start["navigation_job_id"] is not None)
        localization = _fields(owner._localization_session, "active", "state", "map_id", "map_revision")
        localization["token_retained"] = owner._localization_session["token"] is not None
        task_active = _task(owner._start_task)
    jobs = owner._jobs
    with _locked(jobs._lock):
        pipeline = _fields(jobs._pipeline, "state", "job_id")
        retained_process = (jobs._process is not None or jobs._pgid is not None
                            or jobs._map_snapshot is not None)
    gateway = owner._agent._navigation_gateway
    with _locked(gateway._navigation_lock):
        runtime = _fields(gateway._navigation, "active", "cleanup_required", "map")
        goal = _fields(gateway._navigation["goal"], "state", "goal_id")
        runtime_localization = _fields(gateway._localization_only, "active", "state")
        runtime.update(token_retained=bool(gateway._navigation_token),
                       goal_handle_retained=gateway._navigation_goal_handle is not None)
    _bools(startup["pending"], startup["mapping_owned"], localization["active"],
           runtime["active"], runtime_localization["active"], startup["terminal_cleanup"])
    busy = (startup["pending"] or startup["mapping_owned"] or startup["token_retained"]
            or startup["mapping_job_retained"] or startup["navigation_job_retained"]
            or startup["terminal_cleanup"]
            or startup["phase"] in {"active", "stopping"}
            or localization["active"] or localization["token_retained"] or task_active or retained_process
            or pipeline["state"] not in {"idle", "stopped", "failed"}
            or runtime["active"] or runtime.get("cleanup_required", False)
            or runtime["token_retained"] or runtime["goal_handle_retained"]
            or bool(runtime.get("map")) or runtime_localization["active"]
            or goal["state"] in {"pending", "active", "canceling"})
    return dict(busy=bool(busy), startup=startup, localization=localization,
                pipeline=pipeline, retained_process=retained_process,
                task_active=task_active, runtime=runtime, goal=goal,
                runtime_localization=runtime_localization)


def _slam(owner: Any) -> dict[str, Any]:
    # Called synchronously on the ASGI loop under the shared coordination lock.
    # Unlike snapshot(), this never probes an adapter or navigation context.
    session = (_fields(owner._session, "session_id", "generation", "engine_id", "task",
                       "state", "unsaved", "cleanup_required")
               if owner._session is not None else None)
    active = _task(owner._operation)
    if session is not None:
        _bools(session["unsaved"])
        if session["state"] == "IDLE":
            _bools(session["cleanup_required"])
    camera = owner.camera
    _bools(owner._camera_owned, owner._camera_acquisition_pending, owner._runtime_start_attempted)
    if camera is None:
        camera_state = dict(configured=False, reserved=False, reservation_unknown=False)
    else:
        reserved = camera._owner is not None
        if hasattr(camera, "_reservation_unknown"):
            _bools(camera._reservation_unknown)
            camera_state = dict(configured=True, reserved=reserved,
                                reservation_unknown=camera._reservation_unknown)
        else:
            camera_state = dict(configured=True, reserved=reserved,
                                reservation_unknown=False, lock_handle_retained=camera._fd is not None)
    busy = (bool(session and (session["state"] != "IDLE"
                              or session.get("unsaved") or session.get("cleanup_required")))
            or active or owner._camera_owned or owner._camera_acquisition_pending
            or owner._scratch is not None
            or camera_state["reserved"] or camera_state["reservation_unknown"]
            or camera_state.get("lock_handle_retained", False))
    return dict(busy=bool(busy), session=session, generation=owner._generation,
                operation_active=active, camera=camera_state,
                camera_owned=owner._camera_owned,
                camera_acquisition_pending=owner._camera_acquisition_pending,
                runtime_start_attempted=owner._runtime_start_attempted,
                scratch_retained=owner._scratch is not None,
                external_broker_readback_required=camera is not None)


def _control(agent: Any) -> dict[str, Any]:
    transport = agent._control_transport
    manager = transport.manager
    with _locked(transport.operation_lock), _locked(manager._lock):
        # An expired but retained lease still blocks. Do not expire it or drain
        # queued outputs to make this observation look idle.
        lease = (_fields(manager._lease, "input_source", "heartbeat_at")
                 if manager._lease is not None else None)
        drive_retained = manager._drive is not None
        pending_outputs, pending_actions = len(manager._outputs), len(manager._actions)
        motion_active = manager._motion_active
        guard_until = manager._action_guard_until
        if type(guard_until) not in (int, float) or not math.isfinite(guard_until):
            raise TypeError("guard deadline unavailable")
        _bools(motion_active, manager._estop_latched)
        guard_active = guard_until > time.monotonic()
        busy = (lease is not None or drive_retained or pending_outputs > 0
                or pending_actions > 0 or motion_active or guard_active)
        return dict(busy=bool(busy), lease_retained=lease is not None, lease=lease,
                    drive_retained=drive_retained, pending_outputs=pending_outputs,
                    pending_actions=pending_actions, motion_active=motion_active,
                    action_guard_active=guard_active, estop_latched=manager._estop_latched,
                    timer_expiry_applied=False, output_flush_applied=False)


def _dataset(owner: Any) -> dict[str, Any]:
    with _locked(owner._lock):
        _bools(owner._export_active)
        workers = _thread(owner._sampler_thread) or _thread(owner._writer_thread)
        return dict(busy=owner._state not in {"idle", "completed", "failed"}
                    or workers or owner._export_active,
                    state=owner._state, session_id=owner._session_id,
                    workers_alive=workers, export_active=owner._export_active)


def _raw_capture(agent: Any) -> dict[str, Any]:
    latch = agent._pointcloud_hub._raw_capture
    with _locked(latch._lock):
        record = (_fields(latch._record, "capture_id", "generation", "state", "capture_active")
                  if latch._record is not None else None)
        in_flight = latch._in_flight is not None
        return dict(busy=in_flight or bool(record and record["state"] in {"awaiting", "capturing", "ready"}),
                    record=record, in_flight=in_flight, generation=latch._generation)


def _mission(owner: Any) -> dict[str, Any]:
    task_active = _task(owner._task)
    return dict(busy=owner._active_id is not None or task_active
                or owner._operation_lock.locked() or bool(owner._storage_error),
                active_mission_id=owner._active_id, generation=owner._generation,
                task_active=task_active, operation_locked=owner._operation_lock.locked(),
                storage_unavailable=bool(owner._storage_error))


def _mission_routes(owner: Any) -> dict[str, Any]:
    planner = owner.planner
    with _locked(planner._admission_lock):
        foreground = bool(planner._foreground_workers)
    quarantined = planner._quarantine is not None
    _bools(owner._preview_active)
    return dict(busy=owner._preview_active or foreground or quarantined or owner._lock.locked(),
                generation=owner._generation, preview_active=owner._preview_active,
                foreground_busy=foreground, cleanup_quarantined=quarantined,
                transaction_locked=owner._lock.locked())


def _native_jobs(owner: Any, *, coordinator: bool = False) -> dict[str, Any]:
    with _locked(owner._lock):
        active_id = owner._active if coordinator else owner._active_job_id
        active = owner._jobs.get(active_id) if active_id is not None else None
        job = _fields(active, "job_id", "state", "worker_active", "cancellation_requested") if active else None
        worker_alive = _threads(owner._threads)
        generation = owner._generation
    result = dict(busy=active_id is not None or worker_alive, active=job,
                  active_id=active_id, generation=generation, workers_alive=worker_alive)
    if coordinator:
        managed = _native_jobs(owner._manager)
        result.update(busy=result["busy"] or managed["busy"], managed=managed)
    return result


def _sensor(owner: Any) -> dict[str, Any]:
    with _locked(owner._lock):
        worker = _thread(owner._thread)
        retained = owner._process is not None
        capture_retained = owner._capture_id is not None
        if owner._cancel is not None and type(owner._cancel) is not threading.Event:
            raise TypeError("unsupported cancellation owner")
        if owner._cleanup_complete is not None:
            _bools(owner._cleanup_complete)
        if owner._cancel is not None:
            _bools(owner._cancel._flag)
        return dict(busy=owner._state not in {"WAITING_GLOBAL", "STALE", "LOST", "STOPPED", "ERROR"}
                    or worker or retained or capture_retained or owner._cleanup_complete is False,
                    state=owner._state, generation=owner._generation,
                    worker_active=worker, process_retained=retained,
                    cleanup_complete=owner._cleanup_complete,
                    capture_retained=capture_retained,
                    execution_policy=_copy(owner._execution_policy),
                    resource_admission=_copy(owner._resource_admission),
                    cancel_requested=owner._cancel._flag if owner._cancel is not None else False,
                    source_age_revalidated=False)


def _lifecycle(owner: Any) -> dict[str, Any]:
    operations = {}
    busy = False
    for name, manager in (("dashboard", owner._service_lifecycle),
                          ("bridge", owner._control_bridge_lifecycle)):
        if manager is None:
            raise RuntimeError("lifecycle manager unavailable")
        with _locked(manager._lock):
            operation = (_fields(manager._operation, "id", "action", "state")
                         if manager._operation else None)
        operations[name] = operation
        busy = busy or bool(operation and operation["state"] in
                            {"scheduled", "dispatching", "queued", "waiting"})
    return dict(busy=busy, operations=operations,
                bridge_automatic_start_enabled=owner._control_bridge_autostart)


def _route_planner(owner: Any) -> dict[str, Any]:
    locked = owner._lock.locked()
    guidance_active = owner._state["guidance"]["active"]
    _bools(guidance_active)
    return dict(busy=locked or guidance_active or bool(owner._storage_error),
                operation_locked=locked, guidance_active=guidance_active,
                state=owner._state["state"], storage_unavailable=bool(owner._storage_error))


def ownership_readback(runtime: Any) -> dict[str, Any]:
    """Copy local constraints without publishing, expiry, probing, or cleanup.

    The caller must hold pipeline_coordination_lock on the ASGI event loop.
    Component thread locks protect each copy, not a globally atomic instant.
    """
    started = time.monotonic()
    components: dict[str, Any] = {}

    def sample(name: str, owner: Any, reader: Callable[[Any], dict[str, Any]], *, optional: bool = False):
        if owner is None:
            components[name] = dict(status="absent" if optional else "unknown", busy=None if not optional else False)
            return
        try:
            value = reader(owner)
            if type(value["busy"]) is not bool:
                raise TypeError("invalid ownership observation")
            components[name] = dict(status="observed", **value)
        except Exception:
            # Do not expose exceptions, paths, lease tokens or application hooks.
            components[name] = dict(status="unknown", busy=None)

    sample("mapping", runtime.mapping, _mapping)
    sample("navigation", runtime.navigation, _navigation)
    sample("slam", runtime.slam, _slam)
    sample("control", runtime.agent, _control)
    sample("raw_capture", runtime.agent, _raw_capture)
    sample("dataset", runtime.dataset_capture, _dataset)
    sample("mission", runtime.mission, _mission)
    sample("mission_routes", runtime.mission_routes, _mission_routes)
    sample("route_planner", runtime.route_planner, _route_planner)
    sample("lifecycle", runtime.lifecycle, _lifecycle)
    sample("global_observation", runtime.global_observation,
           lambda owner: _native_jobs(owner, coordinator=True), optional=True)
    sample("relocalization", runtime.relocalization, _native_jobs, optional=True)
    sample("sensor_tracking", runtime.sensor_tracking, _sensor, optional=True)
    def observation_session(owner):
        with _locked(owner._lock):
            stale = owner.enabled and time.monotonic() - owner._updated_at > 6
            return dict(busy=bool(owner._status["busy"] or owner._pending or stale),
                        state="UNKNOWN" if stale else owner._status["state"], session_id=owner._status.get("session_id"),
                        operation=owner._pending)
    sample("fastlio_observation", runtime.fastlio_observation, observation_session, optional=True)
    if runtime.observation_aligner is None:
        components["legacy_alignment"] = dict(status="absent", busy=False)
    else:
        # Do not acquire the single-flight lock: locked() is its ownership.
        try:
            components["legacy_alignment"] = dict(status="observed", busy=runtime.observation_aligner.lock.locked())
        except Exception:
            components["legacy_alignment"] = dict(status="unknown", busy=None)
    unknown = [key for key, value in components.items() if value["status"] == "unknown"]
    busy = [key for key, value in components.items() if value["busy"] is True]
    return dict(schema=SCHEMA, process_id=os.getpid(), sampled_monotonic_s=started,
                completed_monotonic_s=time.monotonic(), components=components,
                busy_components=busy, unknown_components=unknown,
                sampled_constraints_clear=not unknown and not busy,
                globally_atomic=False, restart_authorized=False,
                physical_state_verified=False, external_broker_and_os_ownership_required=True)
