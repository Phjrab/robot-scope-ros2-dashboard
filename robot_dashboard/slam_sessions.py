"""Additive SLAM session ownership, independent of operational pose authority."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import math
import re
import threading
import time
from typing import Any, Callable
import uuid

from .slam_camera import CameraBusy, CameraOwnerCoordinator
from .slam_packages import MapPackageStore


class SlamError(RuntimeError):
    def __init__(self, code: str, status: int = 409) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


class FastLioAdapter:
    """Delegate to the existing manager; never create a second sensor owner."""
    def __init__(self, mapping: Any, *, input_ready: Callable[[], bool]) -> None:
        self.mapping = mapping
        self.input_ready = input_ready
        self._job: str | None = None

    def capability(self) -> dict[str, Any]:
        return {"supported_in_source": True, "installed": self.mapping is not None,
                "available_now": self.mapping is not None, "software_verified": True,
                "hardware_verified": False, "blocked_reason": None,
                "tasks": ["mapping"], "effective_modes": {"mapping": "fastlio"}}

    def preflight(self, task: str) -> None:
        if task != "mapping":
            raise SlamError("MODE_UNSUPPORTED", 422)
        snap = self.mapping.snapshot()
        if snap.get("pipeline", {}).get("state") in {"starting", "running", "stopping"}:
            raise SlamError("RESOURCE_CONFLICT")

    def start(self, session: dict[str, Any], cancel: threading.Event) -> dict[str, Any]:
        if cancel.is_set():
            raise SlamError("START_CANCELLED")
        snap = self.mapping.start_mapping()
        self._job = snap.get("pipeline", {}).get("job_id")
        if not self._job:
            raise SlamError("ENGINE_START_FAILED", 503)
        return {"effective_mode": "fastlio", "ready": self.input_ready()}

    def stop(self, session: dict[str, Any]) -> None:
        if self._job:
            stopped, snap = self.mapping.stop_mapping_if_job_id(self._job)
            if not stopped and snap.get("pipeline", {}).get("state") not in {"idle", "stopped", "failed"}:
                raise SlamError("RESOURCE_OWNER_MISMATCH")
            self._job = None

    def status(self, session: dict[str, Any]) -> dict[str, Any]:
        snap = self.mapping.snapshot()
        return {"ready": self.input_ready(), "alive": snap.get("pipeline", {}).get("state") == "running"}

    def save_legacy(self, name: str, create_2d: bool) -> dict[str, Any]:
        # Coordinator owns the existing asynchronous save and existing catalog.
        raise SlamError("LEGACY_SAVE_REQUIRES_COORDINATOR")

    def frame(self, session: dict[str, Any]) -> dict[str, Any]:
        return {"session_id": session["session_id"], "generation": session["generation"],
                "engine_id": "lidar_fastlio", "map_epoch": session["map_epoch"], "reason": "USE_EXISTING_LIDAR_STREAM"}


class SlamSessionManager:
    def __init__(self, adapters: dict[str, Any], packages: MapPackageStore, *,
                 coordination_lock: asyncio.Lock,
                 blockers: Callable[[], list[str]],
                 navigation_context: Callable[[], dict[str, Any]],
                 camera: CameraOwnerCoordinator | None = None,
                 legacy_save: Callable[..., Any] | None = None) -> None:
        self.adapters = adapters
        self.packages = packages
        self.coordination_lock = coordination_lock
        self._blockers = blockers
        self._navigation_context = navigation_context
        self.camera = camera
        self._legacy_save = legacy_save
        self._session: dict[str, Any] | None = None
        self._generation = 0
        self._operation: asyncio.Task[Any] | None = None
        self._cancel = threading.Event()
        self._camera_owned = False
        self._camera_acquisition_pending = False
        self._runtime_start_attempted = False
        self._scratch: Any = None
        self._jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._requests: OrderedDict[str, tuple[str, dict[str, Any]]] = OrderedDict()

    def engines(self) -> dict[str, Any]:
        values = []
        for engine_id, adapter in self.adapters.items():
            try:
                capability = adapter.capability()
            except Exception:
                capability = {"supported_in_source": True, "installed": None, "available_now": False,
                              "software_verified": False, "hardware_verified": False,
                              "blocked_reason": "ENGINE_UNAVAILABLE", "tasks": []}
            values.append({**capability, "engine_id": engine_id})
        values.append({"engine_id": "visual_inertial", "supported_in_source": True,
                       "installed": None, "available_now": False, "software_verified": False,
                       "hardware_verified": False, "blocked_reason": "IMU_NOT_QUALIFIED", "tasks": []})
        return {"engines": values}

    def blocks_context_change(self) -> bool:
        return bool((self._session and self._session["state"] != "IDLE") or
                    (self._operation and not self._operation.done()))

    def active_engine(self) -> str | None:
        return self._session["engine_id"] if self._session and self._session["state"] != "IDLE" else None

    def require_context_idle(self) -> None:
        if self.blocks_context_change():
            raise SlamError("SLAM_SESSION_ACTIVE")

    def owns_current_operation(self) -> bool:
        try:
            return asyncio.current_task() is self._operation
        except RuntimeError:
            return False

    def navigation_context(self) -> dict[str, Any]:
        return deepcopy(self._navigation_context())

    def snapshot(self) -> dict[str, Any]:
        owned = self._session
        session = deepcopy(owned)
        fence = (session.get("state"), session.get("map_epoch")) if session else None
        if session and session["state"] in {"WAITING_INPUT", "TRACKING", "MAPPING", "LOST"}:
            try:
                health = self.adapters[session["engine_id"]].status(session)
                if health.get("alive") is False:
                    session.update(state="ERROR", reason="CHILD_EXITED", cleanup_required=True)
                elif health.get("tracking_state") == "LOST":
                    session.update(state="LOST", reason="TRACKING_LOST")
                elif health.get("ready") is True:
                    session.update(state="MAPPING" if session["task"] == "mapping" else "TRACKING", reason=None)
                else:
                    session.update(state="WAITING_INPUT", reason="STALE_SOURCE")
            except Exception:
                session.update(state="ERROR", reason="ENGINE_STATUS_UNAVAILABLE", cleanup_required=True)
        # Read-side probes run in worker threads. Never let a delayed result
        # mutate lifecycle ownership or overwrite a stop/save/new generation.
        if self._session is not owned or (owned and (owned.get("state"), owned.get("map_epoch")) != fence):
            session = deepcopy(self._session)
        return {"active_session": session, "generation": self._generation,
                "operational_pose_source": self.navigation_context().get("operational_pose"),
                "camera": self.camera.snapshot() if self.camera else None,
                "jobs": deepcopy(list(self._jobs.values())[-10:])}

    def _check_blockers(self) -> None:
        try:
            reasons = self._blockers()
        except Exception as exc:
            raise SlamError("RESOURCE_STATE_UNAVAILABLE", 503) from exc
        if reasons:
            raise SlamError("RESOURCE_CONFLICT")

    def _duplicate(self, request_id: str, value: Any) -> dict[str, Any] | None:
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}", request_id):
            raise SlamError("INVALID_REQUEST_ID", 422)
        try:
            fingerprint = hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()
        except (TypeError, ValueError) as exc:
            raise SlamError("INVALID_REQUEST_VALUE", 422) from exc
        old = self._requests.get(request_id)
        if old:
            if old[0] != fingerprint:
                raise SlamError("REQUEST_ID_CONFLICT")
            return deepcopy(old[1])
        return None

    def _remember(self, request_id: str, value: Any, result: dict[str, Any]) -> dict[str, Any]:
        fingerprint = hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()
        self._requests[request_id] = (fingerprint, deepcopy(result))
        while len(self._requests) > 256:
            self._requests.popitem(last=False)
        return result

    def _match(self, session_id: str, generation: int) -> dict[str, Any]:
        if not self._session or self._session["session_id"] != session_id or self._session["generation"] != generation:
            raise SlamError("SESSION_GENERATION_CONFLICT")
        return self._session

    async def start(self, *, engine_id: str, task: str, request_id: str,
                    operator_confirmed: bool = False) -> dict[str, Any]:
        value = ["start", engine_id, task, operator_confirmed]
        async with self.coordination_lock:
            duplicate = self._duplicate(request_id, value)
            if duplicate is not None:
                return duplicate
            self.require_context_idle()
            self._check_blockers()
            if operator_confirmed is not True:
                raise SlamError("OPERATOR_CONFIRMATION_REQUIRED", 422)
            if engine_id not in self.adapters:
                raise SlamError("ENGINE_UNAVAILABLE", 503)
            adapter = self.adapters[engine_id]
            if task not in {"tracking", "mapping"}:
                raise SlamError("MODE_UNSUPPORTED", 422)
            cap = await asyncio.to_thread(adapter.capability)
            if not cap.get("available_now"):
                raise SlamError(cap.get("blocked_reason") or "ENGINE_UNAVAILABLE", 503)
            if task not in cap.get("tasks", []):
                raise SlamError("MODE_UNSUPPORTED", 422)
            self._generation += 1
            self._cancel = threading.Event()
            self._runtime_start_attempted = False
            session = {"session_id": uuid.uuid4().hex, "generation": self._generation,
                       "map_epoch": uuid.uuid4().hex, "engine_id": engine_id, "task": task,
                       "effective_mode": None, "state": "PREFLIGHT", "reason": None,
                       "unsaved": task == "mapping", "created_at_epoch": time.time(),
                       "operational_pose_applied": False, "evidence_type": "unverified_session"}
            self._session = session
            self._operation = asyncio.create_task(self._start(session, adapter, self._cancel))
            return self._remember(request_id, value, {"session_id": session["session_id"], "generation": session["generation"]})

    async def _start(self, session: dict[str, Any], adapter: Any, cancel: threading.Event) -> None:
        runtime_start_attempted = False
        try:
            await asyncio.to_thread(adapter.preflight, session["task"])
            if cancel.is_set():
                raise SlamError("START_CANCELLED")
            if session["engine_id"] == "visual_stereo":
                if self.camera is None:
                    raise SlamError("CAMERA_HANDOFF_REQUIRED")
                # An RPC may reserve the device and then lose its response.
                # Retain uncertainty until exact-owner reconciliation succeeds.
                self._camera_acquisition_pending = True
                await asyncio.to_thread(self.camera.acquire, deepcopy(session))
                self._camera_owned = True
                self._camera_acquisition_pending = False
            session["state"] = "STARTING"
            runtime_start_attempted = True
            self._runtime_start_attempted = True
            result = await asyncio.to_thread(adapter.start, deepcopy(session), cancel)
            if cancel.is_set():
                raise SlamError("START_CANCELLED")
            session["effective_mode"] = result.get("effective_mode")
            session["effective_parameters"] = result.get("effective_parameters")
            session["state"] = ("MAPPING" if session["task"] == "mapping" else "TRACKING") if result.get("ready") else "WAITING_INPUT"
        except Exception as exc:
            session.update(state="ERROR", reason=_reason(exc), cleanup_required=True)
            try:
                if runtime_start_attempted:
                    await asyncio.to_thread(adapter.stop, deepcopy(session))
                await self._release_camera(session)
                session.update(state="IDLE", cleanup_required=False)
            except Exception:
                session.update(state="ERROR", reason="CLEANUP_REQUIRED", cleanup_required=True)

    async def _release_camera(self, session: dict[str, Any]) -> None:
        if (self._camera_owned or self._camera_acquisition_pending) and self.camera:
            release = self.camera.release
            if self._camera_acquisition_pending:
                release = getattr(self.camera, "release_if_owned", release)
            await asyncio.to_thread(release, deepcopy(session))
            self._camera_owned = False
            self._camera_acquisition_pending = False

    async def stop(self, session_id: str, *, generation: int, request_id: str,
                   discard_unsaved: bool = False) -> dict[str, Any]:
        value = ["stop", session_id, generation, discard_unsaved]
        async with self.coordination_lock:
            duplicate = self._duplicate(request_id, value)
            if duplicate is not None:
                return duplicate
            session = self._match(session_id, generation)
            # Cleanup remains possible while a foreign operation is blocked.
            if session["state"] == "IDLE":
                return self._remember(request_id, value, self.snapshot())
            if session["state"] in {"SAVING", "LOCALIZING", "STOPPING"}:
                raise SlamError("OPERATION_IN_PROGRESS")
            if session.get("unsaved") and session["state"] not in {"PREFLIGHT", "STARTING", "ERROR"} and not discard_unsaved:
                raise SlamError("UNSAVED_MAP_CONFIRMATION_REQUIRED")
            self._cancel.set()
            previous = self._operation
            session["state"] = "STOPPING"
            self._operation = asyncio.create_task(self._stop(session, previous))
            return self._remember(request_id, value, {"session_id": session_id, "generation": generation, "state": "STOPPING"})

    async def _stop(self, session: dict[str, Any], previous: asyncio.Task[Any] | None) -> None:
        try:
            if previous and not previous.done():
                await asyncio.shield(previous)
            session["state"] = "STOPPING"
            if self._runtime_start_attempted:
                await asyncio.to_thread(self.adapters[session["engine_id"]].stop, deepcopy(session))
            if self._scratch:
                self.packages.release_scratch(self._scratch.scratch_id)
                self._scratch = None
            await self._release_camera(session)
            session.update(state="IDLE", cleanup_required=False, unsaved=False)
        except Exception:
            session.update(state="ERROR", reason="CLEANUP_REQUIRED", cleanup_required=True)

    async def save(self, session_id: str, *, generation: int, request_id: str,
                   name: str, create_2d: bool = False) -> dict[str, Any]:
        value = ["save", session_id, generation, name, create_2d]
        async with self.coordination_lock:
            duplicate = self._duplicate(request_id, value)
            if duplicate is not None:
                return duplicate
            session = self._match(session_id, generation)
            self._check_blockers()
            health = (await asyncio.to_thread(self.snapshot))["active_session"]
            if session["task"] != "mapping" or not health or health["state"] != "MAPPING":
                raise SlamError("MAPPING_NOT_READY")
            if not isinstance(name, str) or not name.strip() or len(name) > 64 or any(ord(c) < 32 for c in name):
                raise SlamError("INVALID_MAP_NAME", 422)
            job = {"job_id": uuid.uuid4().hex, "state": "SAVING", "package_id": None,
                   "session_id": session_id, "generation": generation, "reason": None}
            self._jobs[job["job_id"]] = job
            while len(self._jobs) > 64:
                self._jobs.popitem(last=False)
            session["state"] = "SAVING"
            self._operation = asyncio.create_task(self._save(session, job, name, create_2d))
            return self._remember(request_id, value, deepcopy(job))

    async def _save(self, session: dict[str, Any], job: dict[str, Any], name: str, create_2d: bool) -> None:
        staging = None
        resume = True
        try:
            adapter = self.adapters[session["engine_id"]]
            if session["engine_id"] == "lidar_fastlio":
                if self._legacy_save is None:
                    raise SlamError("ENGINE_UNAVAILABLE", 503)
                result = await self._legacy_save(name, create_2d=create_2d)
                job.update(state="LEGACY_SAVING", legacy_operation=result)
                # Existing coordinator retains its own save job and publication fence.
                task = getattr(getattr(self._legacy_save, "__self__", None), "task", None)
                if task:
                    await asyncio.shield(task)
                operation = adapter.mapping.snapshot().get("operation", {})
                if operation.get("state") != "succeeded":
                    raise SlamError("NATIVE_SAVE_FAILED", 503)
                job.update(state="SUCCEEDED", legacy_operation=operation)
            else:
                staging = self.packages.create_staging()
                saved = await asyncio.to_thread(adapter.save, deepcopy(session), staging.native_path)
                preview = await asyncio.to_thread(adapter.frame, deepcopy(session))
                # Camera pixels are volatile; packages retain feature/trajectory preview only.
                preview = {k: v for k, v in preview.items() if k not in {"image", "image_jpeg_base64"}}
                metadata = {**saved.get("metadata", {}), "name": name,
                            "engine_id": session["engine_id"], "source_session_id": session["session_id"],
                            "data_provenance": saved.get("data_provenance", "unknown"),
                            "preview_consistency": "approximate"}
                package = await asyncio.to_thread(self.packages.publish_staging, staging.token,
                    metadata=metadata, official_save_completed=saved.get("official_save_completed") is True,
                    required_native_files=saved.get("required_native_files", []), preview=preview)
                job.update(state="SUCCEEDED", package_id=package["package_id"], package=package)
            session["last_saved_job_id"] = job["job_id"]
            # Mapping keeps changing after a save; stopping still confirms discard.
            session["unsaved"] = True
        except Exception as exc:
            job.update(state="FAILED", reason=_reason(exc))
            if session["engine_id"] == "visual_stereo":
                resume = False
                # A service timeout does not cancel a native writer. Settle the
                # exact owned runtime before deleting any private save staging.
                try:
                    await asyncio.to_thread(self.adapters[session["engine_id"]].stop, deepcopy(session))
                    if self._scratch:
                        self.packages.release_scratch(self._scratch.scratch_id)
                        self._scratch = None
                    await self._release_camera(session)
                    if staging:
                        self.packages.discard_staging(staging.token)
                    session.update(state="IDLE", reason=job["reason"], cleanup_required=False)
                except Exception:
                    session.update(state="ERROR", reason="CLEANUP_REQUIRED", cleanup_required=True)
        finally:
            if resume:
                session["state"] = "MAPPING"

    async def localize(self, session_id: str, *, generation: int, request_id: str,
                       package_id: str, revision: str, hint: dict[str, Any],
                       discard_unsaved: bool = False) -> dict[str, Any]:
        value = ["localize", session_id, generation, package_id, revision, hint, discard_unsaved]
        async with self.coordination_lock:
            duplicate = self._duplicate(request_id, value)
            if duplicate is not None:
                return duplicate
            session = self._match(session_id, generation)
            self._check_blockers()
            health = (await asyncio.to_thread(self.snapshot))["active_session"]
            if session["engine_id"] != "visual_stereo" or not health or health["state"] not in {"MAPPING", "TRACKING"}:
                raise SlamError("MODE_UNSUPPORTED")
            if session["task"] != "mapping":
                raise SlamError("LOCALIZATION_REQUIRES_SLAM_MODE")
            if session.get("unsaved") and discard_unsaved is not True:
                raise SlamError("UNSAVED_MAP_CONFIRMATION_REQUIRED")
            _validate_hint(hint)
            package = self.packages.get_package(package_id)
            if hint["frame_id"] != package.get("map_frame"):
                raise SlamError("POSE_HINT_FRAME_MISMATCH", 422)
            if self._scratch:
                raise SlamError("MAP_ALREADY_LOADED")
            adapter = self.adapters[session["engine_id"]]
            runtime = (await asyncio.to_thread(adapter.capability)).get("compatibility", {})
            self._scratch = await asyncio.to_thread(self.packages.prepare_load, package_id,
                expected_revision=revision, runtime=runtime)
            session["map_epoch"] = uuid.uuid4().hex
            session["state"] = "LOCALIZING"
            self._operation = asyncio.create_task(self._localize(session, adapter, hint))
            return self._remember(request_id, value, {"state": "LOCALIZING", "native_load": "PENDING", "localize_success": False})

    async def _localize(self, session: dict[str, Any], adapter: Any, hint: dict[str, Any]) -> None:
        try:
            result = await asyncio.to_thread(adapter.localize, deepcopy(session), self._scratch.native_path, hint)
            result["retry_requires_new_session"] = result.get("localize_success") is not True
            session["localization_result"] = result
            session["state"] = "MAPPING"
            session["reason"] = None if result.get("localize_success") is True else "LOCALIZATION_FAILED"
        except Exception as exc:
            session.update(reason=_reason(exc), localization_result={"localize_success": False,
                "reason": _reason(exc), "retry_requires_new_session": True})
            try:
                await asyncio.to_thread(adapter.stop, deepcopy(session))
                if self._scratch:
                    self.packages.release_scratch(self._scratch.scratch_id)
                    self._scratch = None
                await self._release_camera(session)
                session.update(state="IDLE", cleanup_required=False)
            except Exception:
                session.update(state="ERROR", reason="CLEANUP_REQUIRED", cleanup_required=True)

    def frame(self) -> dict[str, Any]:
        session = self.snapshot()["active_session"]
        if not session or session["state"] in {"IDLE", "PREFLIGHT", "STARTING", "STOPPING", "ERROR", "LOCALIZING"}:
            return {"schema_version": 1, "session_id": None, "generation": self._generation, "reason": "NO_ACTIVE_STREAM"}
        frame = self.adapters[session["engine_id"]].frame(deepcopy(session))
        current = self._session
        if not current or current["state"] in {"IDLE", "PREFLIGHT", "STARTING", "STOPPING", "ERROR", "LOCALIZING"}:
            raise SlamError("STALE_GENERATION")
        if any(current[key] != session[key] for key in ("session_id", "generation", "map_epoch")):
            raise SlamError("STALE_GENERATION")
        if frame.get("session_id") != session["session_id"] or frame.get("generation") != session["generation"] or frame.get("map_epoch") != session["map_epoch"]:
            raise SlamError("STALE_GENERATION")
        return frame

    def job(self, job_id: str) -> dict[str, Any]:
        if job_id not in self._jobs:
            raise SlamError("JOB_NOT_FOUND", 404)
        return deepcopy(self._jobs[job_id])

    async def mutate_package(self, operation: str, package_id: str | None = None, **values: Any) -> Any:
        async with self.coordination_lock:
            self.require_context_idle()
            self._check_blockers()
            if operation not in {"rename_package", "copy_package", "delete_package", "import_package"}:
                raise SlamError("OPERATION_UNSUPPORTED", 422)
            method = getattr(self.packages, operation)
            return await asyncio.to_thread(method, **({"package_id": package_id, **values} if package_id else values))

    async def close(self) -> None:
        session = self._session
        if session and session["state"] != "IDLE":
            if session["state"] in {"SAVING", "LOCALIZING"} and self._operation:
                await asyncio.shield(self._operation)
            self._cancel.set()
            await self._stop(session, self._operation)


def _reason(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{1,80}", code):
        return code
    if isinstance(exc, CameraBusy):
        return str(exc) if re.fullmatch(r"[A-Z_]{1,80}", str(exc)) else "CAMERA_BUSY"
    return "ENGINE_OPERATION_FAILED"


def _validate_hint(hint: dict[str, Any]) -> None:
    if not isinstance(hint, dict) or set(hint) != {"frame_id", "position", "quaternion_xyzw", "operator_verified"} or hint.get("operator_verified") is not True:
        raise SlamError("POSE_HINT_REQUIRED", 422)
    if not isinstance(hint["frame_id"], str) or not 1 <= len(hint["frame_id"]) <= 128:
        raise SlamError("INVALID_POSE_HINT", 422)
    for key, size in (("position", 3), ("quaternion_xyzw", 4)):
        vals = hint.get(key)
        if not isinstance(vals, list) or len(vals) != size or any(type(v) not in {int, float} or not math.isfinite(v) for v in vals):
            raise SlamError("INVALID_POSE_HINT", 422)
    if abs(sum(v*v for v in hint["quaternion_xyzw"]) - 1) > 1e-3:
        raise SlamError("INVALID_POSE_HINT", 422)


def project_navigation_context(runtime: Any) -> dict[str, Any]:
    """Read actual Nav authority only. Missing evidence remains unknown."""
    navigation = runtime.navigation
    agent = runtime.agent
    view = navigation.view() if navigation else {}
    raw = agent.navigation_runtime_snapshot() if agent else {}
    navmap = view.get("map") or {}
    health = raw.get("runtime_health") or {}
    bindings = view.get("bindings") or {}
    runtime_bindings = raw.get("bindings") or {}
    context = {
        "schema_version": 1,
        "navigation_map": {"id": navmap.get("id"), "revision": navmap.get("revision"), "frame": navmap.get("frame_id") or navmap.get("frame")},
        "operational_pose": {"source": runtime_bindings.get("localization_pose"),
                             "odometry_source": bindings.get("localization_odometry"),
                             "frame": navmap.get("frame_id") or navmap.get("frame"),
                             "generation": health.get("runtime_instance_generation") or health.get("process_generation"),
                             "readiness": view.get("readiness", {}),
                             "state": (view.get("localization") or {}).get("state", "unknown")},
        "alignment": {"verified": False, "transform": None, "reason": "NO_VERIFIED_VSLAM_NAV_ALIGNMENT"},
    }
    context["context_revision"] = hashlib.sha256(json.dumps(context, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return context
