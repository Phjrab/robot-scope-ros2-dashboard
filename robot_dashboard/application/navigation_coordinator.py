"""Application-level navigation transaction and interlock coordination.

The coordinator owns the asynchronous Nav2 startup transaction, its
thread-safe ownership record, and cross-subsystem cleanup.  Fixed ROS
endpoints remain in :mod:`robot_dashboard.ros.navigation_gateway`, process
ownership remains in :mod:`robot_dashboard.navigation_jobs`, and mapping/map
filesystem safety remains behind the injected coordinators and catalog.
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from ..mapping_jobs import MappingJobError
from ..navigation_jobs import (
    NavigationBusy,
    NavigationConflict,
    NavigationJobError,
    NavigationPoseError,
    NavigationUnavailable,
)
from ..public_diagnostics import public_diagnostic


LOGGER = logging.getLogger(__name__)
NAVIGATION_START_READY_TIMEOUT_S = 8.0
NAVIGATION_START_READY_POLL_S = 0.05
NAVIGATION_LOCALIZATION_READY_TIMEOUT_S = 75.0
JOB_ID_RE = re.compile(r"[0-9a-f]{32}")

START_PHASES = frozenset(
    {
        "starting_localization",
        "waiting_localization",
        "starting_navigation",
        "warming_navigation",
        "activating",
        "active",
        "stopping",
        "failed",
        "idle",
    }
)
MANUAL_CONTROL_BLOCKING_PHASES = frozenset(
    {
        "starting_localization",
        "waiting_localization",
        "starting_navigation",
        "warming_navigation",
        "activating",
        "stopping",
    }
)
LOCALIZATION_SESSION_STATES = frozenset(
    {
        "idle",
        "starting",
        "waiting_initial_pose",
        "localizing",
        "localized",
        "stopping",
        "failed",
    }
)


def _public_navigation_diagnostic(value: object) -> str | None:
    """Return one bounded navigation diagnostic for the browser contract."""

    clean = public_diagnostic(value)
    return clean[:160] if clean else None


def navigation_start_state() -> dict[str, Any]:
    """Create one independent fenced navigation-start ownership record."""

    return {
        "seq": 0,
        "token": None,
        "phase": "idle",
        "pending": False,
        "cancel_requested": False,
        "mapping_job_id": None,
        "mapping_owned": False,
        "navigation_job_id": None,
        "terminal_cleanup": False,
        "error": None,
    }


def localization_session_state() -> dict[str, Any]:
    """Create one explicit lease-free localization session record."""

    return {
        "seq": 0,
        "token": None,
        "active": False,
        "mode": "localization_only",
        "state": "idle",
        "map_id": None,
        "map_revision": None,
        "parameters_revision": None,
        "initial_pose_count": 0,
        "initial_pose": None,
        "goal_allowed": False,
        "motion_allowed": False,
        "error": None,
    }


class NavigationAgentPort(Protocol):
    """Narrow application-facing port implemented by the RosAgent facade."""

    def control_snapshot(self) -> dict[str, Any]: ...

    def navigation_runtime_snapshot(self) -> dict[str, Any]: ...

    def navigation_prelocalization_snapshot(
        self,
        *,
        ready_after: float,
    ) -> dict[str, Any]: ...

    def navigation_start_preflight(self) -> None: ...

    def navigation_localization_only_preflight(self) -> dict[str, Any]: ...

    def navigation_set_localization_failure_callback(
        self,
        callback: Callable[[str], None] | None,
    ) -> None: ...

    def navigation_activate(
        self,
        *,
        map_id: str,
        map_revision: str,
        map_name: str,
        ready_after: float,
    ) -> dict[str, Any]: ...

    def navigation_deactivate(self, *, reason: str) -> dict[str, Any]: ...

    def navigation_activate_localization_only(
        self,
        *,
        map_id: str,
        map_revision: str,
        map_name: str,
        ready_after: float,
    ) -> dict[str, Any]: ...

    def navigation_deactivate_localization_only(
        self,
        *,
        reason: str,
    ) -> dict[str, Any]: ...

    def navigation_set_initial_pose(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: float,
        y: float,
        yaw: float,
    ) -> dict[str, Any]: ...

    def navigation_set_localization_only_initial_pose(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: float,
        y: float,
        yaw: float,
    ) -> dict[str, Any]: ...

    def navigation_send_goal(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: float,
        y: float,
        yaw: float,
    ) -> dict[str, Any]: ...

    def navigation_cancel_goal(self, *, goal_id: str) -> dict[str, Any]: ...

    def navigation_clear_costmaps(self, *, scope: str) -> dict[str, Any]: ...


class NavigationJobsPort(Protocol):
    """Bounded Nav2 process, parameter, log, and pose-validation port."""

    on_terminal: Callable[[str, str], None] | None

    def snapshot(self) -> dict[str, Any]: ...

    def progress_snapshot(
        self,
        *,
        after: int = 0,
        limit: int = 80,
    ) -> dict[str, Any]: ...

    def parameters_snapshot(self) -> dict[str, Any]: ...

    def update_parameters(
        self,
        base_revision: str,
        patch: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def start(
        self,
        *,
        map_id: str,
        map_revision: str,
        parameters_revision: str,
    ) -> dict[str, Any]: ...

    def stop(self) -> dict[str, Any]: ...

    def validate_active_pose(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: object,
        y: object,
        yaw: object,
    ) -> dict[str, float]: ...

    def close(self) -> None: ...


class MappingCoordinatorPort(Protocol):
    """Shared localization and mapping-operation interlock port."""

    def activity(self) -> tuple[bool, list[str]]: ...

    def pipeline_state(self) -> str: ...

    def snapshot(self, *, since_log_seq: int = 0) -> dict[str, Any]: ...

    def start_mapping(self) -> dict[str, Any]: ...

    def stop_mapping_if_job_id(
        self,
        job_id: str,
    ) -> tuple[bool, dict[str, Any]]: ...


class SavedMapsPort(Protocol):
    """Opaque saved-map lookup port; raw paths never enter this component."""

    def resolve_navigation_map(self, map_id: str, revision: str) -> Any: ...

    def resolve_annotation_goal(
        self,
        map_id: str,
        map_revision: str,
        annotation_revision: str,
        annotation_id: str,
    ) -> Any: ...


class NavigationCoordinator:
    """Own the complete one-click localization/Nav2 application transaction.

    ``coordination_lock`` must be the same exact asyncio lock used by mapping,
    manual-control arming, dataset capture, and lifecycle operations.
    ``require_lifecycle_idle`` is intentionally omitted from cleanup methods so
    stop/cancel remain available while a lifecycle transition is pending.
    """

    def __init__(
        self,
        agent: NavigationAgentPort,
        navigation_jobs: NavigationJobsPort,
        mapping: MappingCoordinatorPort,
        saved_maps: SavedMapsPort,
        *,
        coordination_lock: asyncio.Lock,
        require_lifecycle_idle: Callable[[], None],
        ready_timeout_s: float = NAVIGATION_START_READY_TIMEOUT_S,
        localization_timeout_s: float = NAVIGATION_LOCALIZATION_READY_TIMEOUT_S,
        poll_interval_s: float = NAVIGATION_START_READY_POLL_S,
        logger: logging.Logger | None = None,
    ) -> None:
        if not callable(require_lifecycle_idle):
            raise TypeError("require_lifecycle_idle must be callable")
        if ready_timeout_s <= 0.0 or localization_timeout_s <= 0.0:
            raise ValueError("navigation readiness timeouts must be positive")
        if poll_interval_s <= 0.0:
            raise ValueError("navigation readiness poll interval must be positive")
        self._agent = agent
        self._jobs = navigation_jobs
        self._mapping = mapping
        self._saved_maps = saved_maps
        self._coordination_lock = coordination_lock
        self._require_lifecycle_idle = require_lifecycle_idle
        self._ready_timeout_s = float(ready_timeout_s)
        self._localization_timeout_s = float(localization_timeout_s)
        self._poll_interval_s = float(poll_interval_s)
        self._logger = logger or LOGGER
        self._state_lock = threading.RLock()
        self._start = navigation_start_state()
        self._start_task: asyncio.Task[None] | None = None
        self._localization_session = localization_session_state()

        previous_terminal = getattr(navigation_jobs, "on_terminal", None)
        if previous_terminal is not None and previous_terminal != self.handle_terminal:
            raise ValueError("navigation terminal callback already has another owner")
        navigation_jobs.on_terminal = self.handle_terminal
        localization_failure_setter = getattr(
            agent,
            "navigation_set_localization_failure_callback",
            None,
        )
        if callable(localization_failure_setter):
            localization_failure_setter(self.handle_localization_failure)

    @property
    def coordination_lock(self) -> asyncio.Lock:
        """Expose the exact shared lock for integration identity tests."""

        return self._coordination_lock

    @property
    def start_task(self) -> asyncio.Task[None] | None:
        """Return the single coordinator-owned background START task."""

        return self._start_task

    @property
    def state_lock(self) -> threading.RLock:
        """Expose the terminal-thread-compatible lock for identity tests."""

        return self._state_lock

    @property
    def jobs(self) -> NavigationJobsPort:
        """Return the one bounded navigation process manager."""

        return self._jobs

    def start_state(self) -> dict[str, Any]:
        """Return the bounded public START projection without its secret token."""

        state = self.internal_start_state()
        state.pop("token", None)
        return state

    def internal_start_state(self) -> dict[str, Any]:
        """Copy the fenced ownership record for application interlocks."""

        with self._state_lock:
            return dict(self._start)

    def localization_session(self) -> dict[str, Any]:
        """Return the bounded public lease-free localization state."""

        with self._state_lock:
            result = dict(self._localization_session)
        result.pop("token", None)
        return result

    def internal_localization_session(self) -> dict[str, Any]:
        with self._state_lock:
            return dict(self._localization_session)

    def _update_localization_session(
        self,
        token: str,
        state: str,
        **updates: Any,
    ) -> bool:
        if state not in LOCALIZATION_SESSION_STATES:
            raise ValueError("invalid localization-only state")
        with self._state_lock:
            if self._localization_session.get("token") != token:
                return False
            self._localization_session.update(
                seq=int(self._localization_session.get("seq", 0) or 0) + 1,
                state=state,
                **updates,
            )
            return True

    def _begin_localization_session(
        self,
        *,
        map_id: str,
        map_revision: str,
        parameters_revision: str,
    ) -> str:
        token = self.begin_start()
        with self._state_lock:
            self._localization_session = {
                "seq": int(self._localization_session.get("seq", 0) or 0) + 1,
                "token": token,
                "active": True,
                "mode": "localization_only",
                "state": "starting",
                "map_id": map_id,
                "map_revision": map_revision,
                "parameters_revision": parameters_revision,
                "initial_pose_count": 0,
                "initial_pose": None,
                "goal_allowed": False,
                "motion_allowed": False,
                "error": None,
            }
        return token

    def _finish_localization_session(
        self,
        token: str | None,
        *,
        state: str,
        error: str | None = None,
        clear: bool = False,
    ) -> None:
        if state not in LOCALIZATION_SESSION_STATES:
            raise ValueError("invalid localization-only state")
        with self._state_lock:
            current_token = self._localization_session.get("token")
            if token is not None and current_token != token:
                return
            previous_seq = int(self._localization_session.get("seq", 0) or 0)
            if clear:
                previous = dict(self._localization_session)
                self._localization_session = localization_session_state()
                self._localization_session.update(
                    seq=previous_seq + 1,
                    state=state,
                    initial_pose_count=int(
                        previous.get("initial_pose_count", 0) or 0
                    ),
                    initial_pose=previous.get("initial_pose"),
                    error=_public_navigation_diagnostic(error) if error else None,
                )
                return
            self._localization_session.update(
                seq=previous_seq + 1,
                active=state not in {"idle", "failed"},
                state=state,
                error=_public_navigation_diagnostic(error) if error else None,
            )

    def begin_start(self) -> str:
        """Reserve the one permitted localization/Nav2 startup transaction."""

        with self._state_lock:
            if (
                self._start.get("token") is not None
                or self._start.get("pending")
                or self._start.get("phase") in {"active", "stopping"}
                or self._start.get("mapping_owned")
                or self._localization_session.get("active")
            ):
                raise NavigationBusy("navigation is already active or starting")
            token = secrets.token_hex(16)
            self._start.update(
                seq=int(self._start.get("seq", 0) or 0) + 1,
                token=token,
                phase="starting_localization",
                pending=True,
                cancel_requested=False,
                mapping_job_id=None,
                mapping_owned=False,
                navigation_job_id=None,
                terminal_cleanup=False,
                error=None,
            )
            return token

    def update_start(
        self,
        token: str,
        phase: str,
        *,
        mapping_job_id: str | None = None,
        mapping_owned: bool | None = None,
        navigation_job_id: str | None = None,
        error: str | None = None,
    ) -> bool:
        """Publish one token-fenced phase and validate every ownership ID."""

        if phase not in START_PHASES:
            raise ValueError("invalid navigation startup phase")
        with self._state_lock:
            if self._start.get("token") != token:
                return False
            updates: dict[str, Any] = {
                "seq": int(self._start.get("seq", 0) or 0) + 1,
                "phase": phase,
            }
            if mapping_job_id is not None:
                if not isinstance(mapping_job_id, str) or JOB_ID_RE.fullmatch(
                    mapping_job_id
                ) is None:
                    raise ValueError("invalid localization dependency job_id")
                updates["mapping_job_id"] = mapping_job_id
            if mapping_owned is not None:
                updates["mapping_owned"] = bool(mapping_owned)
            if navigation_job_id is not None:
                if not isinstance(navigation_job_id, str) or JOB_ID_RE.fullmatch(
                    navigation_job_id
                ) is None:
                    raise ValueError("invalid navigation job_id")
                updates["navigation_job_id"] = navigation_job_id
            if error is not None:
                updates["error"] = (
                    _public_navigation_diagnostic(error)
                    or "navigation startup failed"
                )
            self._start.update(updates)
            return True

    def start_cancelled(self, token: str) -> bool:
        with self._state_lock:
            return bool(
                self._start.get("token") != token
                or self._start.get("cancel_requested")
            )

    def request_start_cancel(self) -> str | None:
        """Fence every future startup phase before process cleanup begins."""

        with self._state_lock:
            token = self._start.get("token")
            if not isinstance(token, str):
                return None
            self._start.update(
                seq=int(self._start.get("seq", 0) or 0) + 1,
                phase="stopping",
                cancel_requested=True,
            )
            return token

    def request_terminal_cancel(
        self,
        job_id: str,
    ) -> tuple[str, dict[str, Any]] | None:
        """Fence only the startup that owns one unexpectedly exiting Nav job."""

        if not isinstance(job_id, str) or JOB_ID_RE.fullmatch(job_id) is None:
            return None
        with self._state_lock:
            token = self._start.get("token")
            if (
                not isinstance(token, str)
                or self._start.get("navigation_job_id") != job_id
            ):
                return None
            ownership = dict(self._start)
            self._start.update(
                seq=int(self._start.get("seq", 0) or 0) + 1,
                phase="stopping",
                cancel_requested=True,
                terminal_cleanup=True,
            )
            return token, ownership

    def commit_start(self, token: str) -> bool:
        """Commit only if STOP has not fenced the background transaction."""

        with self._state_lock:
            if (
                self._start.get("token") != token
                or self._start.get("cancel_requested")
            ):
                return False
            self._start.update(
                seq=int(self._start.get("seq", 0) or 0) + 1,
                phase="active",
                pending=False,
                error=None,
            )
            return True

    def finish_start_failure(
        self,
        token: str,
        error: str,
        *,
        cleanup_complete: bool,
        terminal_cleanup_owner: bool = False,
    ) -> None:
        """Retain exact cleanup ownership whenever rollback is incomplete."""

        clean = (
            _public_navigation_diagnostic(error)
            or "navigation startup failed"
        )
        with self._state_lock:
            if self._start.get("token") != token:
                return
            if self._start.get("terminal_cleanup") and not terminal_cleanup_owner:
                return
            self._start.update(
                seq=int(self._start.get("seq", 0) or 0) + 1,
                phase="failed",
                pending=False,
                error=clean,
                terminal_cleanup=False,
            )
            if cleanup_complete:
                self._start.update(
                    token=None,
                    cancel_requested=False,
                    mapping_job_id=None,
                    mapping_owned=False,
                    navigation_job_id=None,
                )

    def reset_start(self, token: str | None) -> None:
        """Clear one settled owner without touching a newer/terminal owner."""

        with self._state_lock:
            if token is not None and self._start.get("token") != token:
                return
            if self._start.get("terminal_cleanup"):
                return
            self._start.update(
                seq=int(self._start.get("seq", 0) or 0) + 1,
                token=None,
                phase="idle",
                pending=False,
                cancel_requested=False,
                mapping_job_id=None,
                mapping_owned=False,
                navigation_job_id=None,
                terminal_cleanup=False,
                error=None,
            )

    def manual_control_blocked(self) -> bool:
        """Report startup phases that must fence a new manual motion lease."""

        startup = self.internal_start_state()
        localization = self.internal_localization_session()
        return bool(
            startup.get("pending")
            or startup.get("phase") in MANUAL_CONTROL_BLOCKING_PHASES
            or localization.get("active")
        )

    def is_active(self) -> bool:
        """Return the complete cleanup union, failing closed on unreadable state."""

        startup = self.internal_start_state()
        localization = self.internal_localization_session()
        startup_active = bool(
            startup.get("pending")
            or startup.get("mapping_owned")
            or startup.get("phase") in {"active", "stopping"}
            or localization.get("active")
        )
        try:
            manager = self._jobs.snapshot()
            pipeline = (
                manager.get("pipeline")
                if isinstance(manager.get("pipeline"), Mapping)
                else {}
            )
            manager_active = bool(
                pipeline.get("state") in {"starting", "running", "stopping"}
                or pipeline.get("job_id")
            )
        except Exception:
            return True
        try:
            runtime = self._agent.navigation_runtime_snapshot()
            goal = (
                runtime.get("goal")
                if isinstance(runtime.get("goal"), Mapping)
                else {}
            )
            control = self._agent.control_snapshot()
            lease = (
                control.get("lease")
                if isinstance(control.get("lease"), Mapping)
                else {}
            )
            runtime_active = bool(
                runtime.get("active")
                or runtime.get("cleanup_required")
                or runtime.get("map")
                or goal.get("state") in {"pending", "active", "canceling"}
                or (
                    lease.get("active")
                    and lease.get("input_source") == "navigation"
                )
            )
            return manager_active or runtime_active or startup_active
        except Exception:
            return True

    def require_runtime_capability(self, capability: str) -> None:
        runtime = self._agent.navigation_runtime_snapshot()
        safety = (
            runtime.get("safety")
            if isinstance(runtime.get("safety"), Mapping)
            else {}
        )
        if safety.get(capability) is not True:
            raise NavigationUnavailable(
                f"navigation runtime safety gate {capability} is not ready"
            )

    def progress_snapshot(self, *, after: int = 0, limit: int = 80) -> dict[str, Any]:
        return self._jobs.progress_snapshot(after=after, limit=limit)

    def parameters_snapshot(self) -> dict[str, Any]:
        return self._jobs.parameters_snapshot()

    async def update_parameters(
        self,
        base_revision: str,
        values: Mapping[str, Any],
    ) -> dict[str, Any]:
        async with self._coordination_lock:
            return await asyncio.to_thread(
                self._jobs.update_parameters,
                base_revision,
                values,
            )

    async def start(
        self,
        *,
        map_id: str,
        map_revision: str,
        parameters_revision: str,
    ) -> dict[str, Any]:
        """Validate and schedule the one-click startup without blocking HTTP."""

        manager = self._jobs
        async with self._coordination_lock:
            self._require_lifecycle_idle()
            mapping_busy, _ = self._mapping.activity()
            if mapping_busy:
                raise NavigationBusy(
                    "a mapping save, conversion, or pipeline transition is active"
                )
            preflight = await asyncio.to_thread(manager.snapshot)
            pipeline_state = str(
                (preflight.get("pipeline") or {}).get("state", "failed")
            )
            if pipeline_state in {"starting", "running", "stopping"}:
                raise NavigationBusy("navigation is already active")
            if not preflight.get("available"):
                raise NavigationUnavailable("navigation prerequisites are unavailable")
            if parameters_revision != preflight.get("parameters_revision"):
                raise NavigationConflict(
                    "navigation parameters changed; reload before starting"
                )
            source = await asyncio.to_thread(
                self._saved_maps.resolve_navigation_map,
                map_id,
                map_revision,
            )

            # Reject every control gate before a cold mapping launch can have
            # any process side effect.
            await asyncio.to_thread(self._agent.navigation_start_preflight)

            mapping_snapshot = await asyncio.to_thread(self._mapping.snapshot)
            mapping_pipeline = (
                mapping_snapshot.get("pipeline")
                if isinstance(mapping_snapshot.get("pipeline"), Mapping)
                else {}
            )
            shared_pipeline_state = str(mapping_pipeline.get("state", "failed"))
            if shared_pipeline_state == "stopped":
                shared_pipeline_state = "idle"
            if shared_pipeline_state not in {"idle", "failed", "running"}:
                raise NavigationBusy("localization pipeline is changing state")
            existing_mapping_job_id = mapping_pipeline.get("job_id")
            if shared_pipeline_state == "running" and (
                not isinstance(existing_mapping_job_id, str)
                or JOB_ID_RE.fullmatch(existing_mapping_job_id) is None
            ):
                raise NavigationUnavailable(
                    "localization pipeline ownership is unavailable"
                )

            token = self.begin_start()
            if shared_pipeline_state == "running":
                self.update_start(
                    token,
                    "waiting_localization",
                    mapping_job_id=existing_mapping_job_id,
                    mapping_owned=False,
                )
            coroutine = self._run_start_operation(
                token,
                manager,
                map_id=str(source.map_id),
                map_revision=str(source.revision),
                map_name=str(source.name),
                parameters_revision=parameters_revision,
                start_localization=shared_pipeline_state in {"idle", "failed"},
                previous_mapping_job_id=(
                    existing_mapping_job_id
                    if isinstance(existing_mapping_job_id, str)
                    else None
                ),
            )
            try:
                self._start_task = asyncio.create_task(
                    coroutine,
                    name="navigation-start-operation",
                )
            except Exception:
                coroutine.close()
                self.reset_start(token)
                raise
        return {
            "accepted": True,
            "pending": True,
            "navigation": await asyncio.to_thread(self.view),
        }

    async def start_localization_only(
        self,
        *,
        map_id: str,
        map_revision: str,
        parameters_revision: str,
    ) -> dict[str, Any]:
        """Start exact-map Nav2 localization without acquiring motion authority."""

        manager = self._jobs
        async with self._coordination_lock:
            self._require_lifecycle_idle()
            mapping_busy, _ = self._mapping.activity()
            if mapping_busy:
                raise NavigationBusy(
                    "a mapping save, conversion, or pipeline transition is active"
                )
            preflight = await asyncio.to_thread(manager.snapshot)
            pipeline_state = str(
                (preflight.get("pipeline") or {}).get("state", "failed")
            )
            if pipeline_state in {"starting", "running", "stopping"}:
                raise NavigationBusy("navigation is already active")
            if not preflight.get("available"):
                raise NavigationUnavailable("navigation prerequisites are unavailable")
            if parameters_revision != preflight.get("parameters_revision"):
                raise NavigationConflict(
                    "navigation parameters changed; reload before starting"
                )
            source = await asyncio.to_thread(
                self._saved_maps.resolve_navigation_map,
                map_id,
                map_revision,
            )
            await asyncio.to_thread(
                self._agent.navigation_localization_only_preflight
            )

            mapping_snapshot = await asyncio.to_thread(self._mapping.snapshot)
            mapping_pipeline = (
                mapping_snapshot.get("pipeline")
                if isinstance(mapping_snapshot.get("pipeline"), Mapping)
                else {}
            )
            shared_pipeline_state = str(mapping_pipeline.get("state", "failed"))
            if shared_pipeline_state == "stopped":
                shared_pipeline_state = "idle"
            if shared_pipeline_state not in {"idle", "failed", "running"}:
                raise NavigationBusy("localization pipeline is changing state")
            existing_mapping_job_id = mapping_pipeline.get("job_id")
            if shared_pipeline_state == "running" and (
                not isinstance(existing_mapping_job_id, str)
                or JOB_ID_RE.fullmatch(existing_mapping_job_id) is None
            ):
                raise NavigationUnavailable(
                    "localization pipeline ownership is unavailable"
                )

            token = self._begin_localization_session(
                map_id=str(source.map_id),
                map_revision=str(source.revision),
                parameters_revision=parameters_revision,
            )
            if shared_pipeline_state == "running":
                self.update_start(
                    token,
                    "waiting_localization",
                    mapping_job_id=existing_mapping_job_id,
                    mapping_owned=False,
                )
            coroutine = self._run_localization_only_start_operation(
                token,
                manager,
                map_id=str(source.map_id),
                map_revision=str(source.revision),
                map_name=str(source.name),
                parameters_revision=parameters_revision,
                start_localization=shared_pipeline_state in {"idle", "failed"},
                previous_mapping_job_id=(
                    existing_mapping_job_id
                    if isinstance(existing_mapping_job_id, str)
                    else None
                ),
            )
            try:
                self._start_task = asyncio.create_task(
                    coroutine,
                    name="localization-only-start-operation",
                )
            except Exception:
                coroutine.close()
                self.reset_start(token)
                self._finish_localization_session(
                    token,
                    state="failed",
                    error="localization-only startup could not be scheduled",
                    clear=True,
                )
                raise
        return {
            "accepted": True,
            "pending": True,
            "navigation": await asyncio.to_thread(self.view),
        }

    async def stop(self) -> dict[str, Any]:
        """Fence, settle, and clean every START side effect before returning."""

        async with self._coordination_lock:
            if self.internal_localization_session().get("active"):
                raise NavigationConflict(
                    "use localization stop for the localization-only session"
                )
            token = self.request_start_cancel()
            task = self._start_task
            if task is not None and not task.done():
                task.cancel()
            request_cancelled = False
            if task is not None and not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    if not task.done():
                        request_cancelled = True
                        try:
                            await asyncio.shield(task)
                        except asyncio.CancelledError:
                            pass
                except Exception:
                    self._logger.exception(
                        "navigation background stop settlement failed"
                    )

            cleanup_task = asyncio.create_task(
                self._perform_stop_cleanup(token),
                name="navigation-stop-cleanup",
            )
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError:
                request_cancelled = True
                try:
                    await asyncio.shield(cleanup_task)
                except NavigationJobError:
                    raise
            if request_cancelled:
                raise asyncio.CancelledError
        return {"navigation": await asyncio.to_thread(self.view)}

    async def stop_localization_only(self) -> dict[str, Any]:
        """Reverse-clean the lease-free session without issuing a robot stop."""

        async with self._coordination_lock:
            session = self.internal_localization_session()
            token = session.get("token")
            if not session.get("active") and not isinstance(token, str):
                return {"navigation": await asyncio.to_thread(self.view)}
            if isinstance(token, str):
                self._update_localization_session(token, "stopping")
            self.request_start_cancel()
            task = self._start_task
            if task is not None and not task.done():
                task.cancel()
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    pass
                except Exception:
                    self._logger.exception(
                        "localization-only startup settlement failed"
                    )
            await self._perform_localization_only_cleanup(
                token if isinstance(token, str) else None,
                reason="localization_stop",
            )
        return {"navigation": await asyncio.to_thread(self.view)}

    async def set_localization_only_initial_pose(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: object,
        y: object,
        yaw: object,
        confirmed: bool,
    ) -> dict[str, Any]:
        """Validate and publish the session's sole operator-confirmed pose."""

        if confirmed is not True:
            raise NavigationPoseError(
                "confirmed=true is required before publishing the initial pose"
            )
        async with self._coordination_lock:
            self._require_lifecycle_idle()
            session = self.internal_localization_session()
            token = session.get("token")
            if not session.get("active") or not isinstance(token, str):
                raise NavigationBusy("localization-only session is not active")
            if session.get("state") != "waiting_initial_pose":
                raise NavigationConflict(
                    "localization-only session is not waiting for an initial pose"
                )
            if int(session.get("initial_pose_count", 0) or 0) != 0:
                raise NavigationConflict(
                    "localization-only initial pose has already been published"
                )
            if (
                map_id != session.get("map_id")
                or map_revision != session.get("map_revision")
            ):
                raise NavigationConflict(
                    "localization request does not match the pinned map"
                )
            if self._mapping.pipeline_state() != "running":
                raise NavigationBusy(
                    "shared Hesai + FAST-LIO localization pipeline is not running"
                )
            pose = await asyncio.to_thread(
                self._jobs.validate_active_pose,
                map_id=map_id,
                map_revision=map_revision,
                x=x,
                y=y,
                yaw=yaw,
            )
            runtime = await asyncio.to_thread(
                self._agent.navigation_set_localization_only_initial_pose,
                map_id=map_id,
                map_revision=map_revision,
                **pose,
            )
            runtime_session = (
                runtime.get("localization_session")
                if isinstance(runtime.get("localization_session"), Mapping)
                else {}
            )
            if int(runtime_session.get("initial_pose_count", 0) or 0) != 1:
                raise NavigationUnavailable(
                    "localization runtime did not confirm exactly one initial pose"
                )
            self._update_localization_session(
                token,
                "localizing",
                initial_pose_count=1,
                initial_pose=dict(pose),
            )
        return {
            "accepted": True,
            "navigation": await asyncio.to_thread(self.view),
        }

    async def set_initial_pose(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: object,
        y: object,
        yaw: object,
    ) -> dict[str, Any]:
        if self.internal_localization_session().get("active"):
            raise NavigationConflict(
                "use the localization-only initial-pose endpoint for this session"
            )
        async with self._coordination_lock:
            self._require_lifecycle_idle()
            mapping_busy, _ = self._mapping.activity()
            if mapping_busy:
                raise NavigationBusy("mapping is active")
            if self._mapping.pipeline_state() != "running":
                raise NavigationBusy(
                    "shared Hesai + FAST-LIO localization pipeline is not running"
                )
            await asyncio.to_thread(
                self.require_runtime_capability,
                "can_set_initial_pose",
            )
            pose = await asyncio.to_thread(
                self._jobs.validate_active_pose,
                map_id=map_id,
                map_revision=map_revision,
                x=x,
                y=y,
                yaw=yaw,
            )
            await asyncio.to_thread(
                self._agent.navigation_set_initial_pose,
                map_id=map_id,
                map_revision=map_revision,
                **pose,
            )
        return {
            "accepted": True,
            "navigation": await asyncio.to_thread(self.view),
        }

    async def send_goal(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: object,
        y: object,
        yaw: object,
        confirmed: bool,
    ) -> dict[str, Any]:
        if self.internal_localization_session().get("active"):
            raise NavigationConflict(
                "navigation goal is unavailable during localization-only session"
            )
        if confirmed is not True:
            raise NavigationPoseError(
                "confirmed=true is required before sending a navigation goal"
            )
        async with self._coordination_lock:
            await self._send_goal_locked(
                map_id=map_id,
                map_revision=map_revision,
                x=x,
                y=y,
                yaw=yaw,
            )
        return {
            "accepted": True,
            "navigation": await asyncio.to_thread(self.view),
        }

    async def send_annotation_goal(
        self,
        *,
        map_id: str,
        map_revision: str,
        annotation_revision: str,
        annotation_id: str,
        confirmed: bool,
    ) -> dict[str, Any]:
        """Resolve a revision-pinned point then use the normal goal safety path."""

        if self.internal_localization_session().get("active"):
            raise NavigationConflict(
                "navigation goal is unavailable during localization-only session"
            )
        if confirmed is not True:
            raise NavigationPoseError(
                "confirmed=true is required before sending a navigation goal"
            )
        async with self._coordination_lock:
            annotation = await asyncio.to_thread(
                self._saved_maps.resolve_annotation_goal,
                map_id,
                map_revision,
                annotation_revision,
                annotation_id,
            )
            await self._send_goal_locked(
                map_id=map_id,
                map_revision=map_revision,
                x=annotation.x,
                y=annotation.y,
                yaw=annotation.yaw,
            )
        return {
            "accepted": True,
            "annotation": {
                "id": annotation.annotation_id,
                "type": annotation.annotation_type,
                "name": annotation.name,
            },
            "navigation": await asyncio.to_thread(self.view),
        }

    async def _send_goal_locked(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: object,
        y: object,
        yaw: object,
    ) -> None:
        self._require_lifecycle_idle()
        mapping_busy, _ = self._mapping.activity()
        if mapping_busy:
            raise NavigationBusy("mapping is active")
        if self._mapping.pipeline_state() != "running":
            raise NavigationBusy(
                "shared Hesai + FAST-LIO localization pipeline is not running"
            )
        await asyncio.to_thread(
            self.require_runtime_capability,
            "can_send_goal",
        )
        pose = await asyncio.to_thread(
            self._jobs.validate_active_pose,
            map_id=map_id,
            map_revision=map_revision,
            x=x,
            y=y,
            yaw=yaw,
        )
        await asyncio.to_thread(
            self._agent.navigation_send_goal,
            map_id=map_id,
            map_revision=map_revision,
            **pose,
        )

    async def cancel_goal(self, *, goal_id: str) -> dict[str, Any]:
        await asyncio.to_thread(
            self._agent.navigation_cancel_goal,
            goal_id=goal_id,
        )
        return {"navigation": await asyncio.to_thread(self.view)}

    async def clear_costmaps(self, *, scope: str) -> dict[str, Any]:
        await asyncio.to_thread(
            self._agent.navigation_clear_costmaps,
            scope=scope,
        )
        return {"navigation": await asyncio.to_thread(self.view)}

    async def wait_prelocalization_ready(
        self,
        manager: NavigationJobsPort,
        *,
        ready_after: float,
    ) -> None:
        """Wait boundedly for fresh Nav-runtime cloud/odom projections."""

        deadline = time.monotonic() + self._ready_timeout_s
        reason = "navigation runtime inputs did not become ready"
        while time.monotonic() < deadline:
            pipeline = await asyncio.to_thread(manager.snapshot)
            pipeline_state = str(
                (pipeline.get("pipeline") or {}).get("state", "failed")
            )
            if pipeline_state != "running":
                raise NavigationUnavailable(
                    "navigation pipeline stopped while runtime inputs were warming up"
                )
            readiness = await asyncio.to_thread(
                self._agent.navigation_prelocalization_snapshot,
                ready_after=ready_after,
            )
            if readiness.get("ready") is True:
                return
            reason = str(readiness.get("reason") or reason)[:160]
            await asyncio.sleep(self._poll_interval_s)
        raise NavigationUnavailable(f"navigation startup timed out: {reason}")

    async def start_localization_dependency(
        self,
        token: str,
        *,
        previous_job_id: str | None,
    ) -> str:
        """Start mapping and claim its exact job even when this task is cancelled."""

        start_task = asyncio.create_task(
            asyncio.to_thread(self._mapping.start_mapping),
            name="navigation-localization-start",
        )
        snapshot: dict[str, Any] | None = None
        try:
            snapshot = await asyncio.shield(start_task)
        except asyncio.CancelledError:
            try:
                snapshot = await asyncio.shield(start_task)
            except Exception:
                snapshot = await asyncio.to_thread(self._mapping.snapshot)
            if snapshot is not None:
                pipeline = (
                    snapshot.get("pipeline")
                    if isinstance(snapshot.get("pipeline"), Mapping)
                    else {}
                )
                job_id = pipeline.get("job_id")
                if (
                    isinstance(job_id, str)
                    and JOB_ID_RE.fullmatch(job_id)
                    and job_id != previous_job_id
                ):
                    self.update_start(
                        token,
                        "stopping",
                        mapping_job_id=job_id,
                        mapping_owned=True,
                    )
            raise
        except Exception:
            snapshot = await asyncio.to_thread(self._mapping.snapshot)
            pipeline = (
                snapshot.get("pipeline")
                if isinstance(snapshot.get("pipeline"), Mapping)
                else {}
            )
            job_id = pipeline.get("job_id")
            if (
                isinstance(job_id, str)
                and JOB_ID_RE.fullmatch(job_id)
                and job_id != previous_job_id
            ):
                self.update_start(
                    token,
                    "failed",
                    mapping_job_id=job_id,
                    mapping_owned=True,
                )
            raise

        pipeline = (
            snapshot.get("pipeline")
            if isinstance(snapshot.get("pipeline"), Mapping)
            else {}
        )
        job_id = pipeline.get("job_id")
        if not isinstance(job_id, str) or JOB_ID_RE.fullmatch(job_id) is None:
            raise NavigationUnavailable(
                "localization pipeline did not publish an ownership token"
            )
        if job_id == previous_job_id:
            raise NavigationUnavailable(
                "localization pipeline reused a stale ownership token"
            )
        if not self.update_start(
            token,
            "waiting_localization",
            mapping_job_id=job_id,
            mapping_owned=True,
        ):
            raise NavigationConflict("navigation startup ownership expired")
        return job_id

    async def wait_localization_dependency(self, token: str) -> None:
        """Wait boundedly for the exact reserved FAST-LIO job to run."""

        deadline = time.monotonic() + self._localization_timeout_s
        while time.monotonic() < deadline:
            if self.start_cancelled(token):
                raise NavigationConflict("navigation startup was stopped")
            ownership = self.internal_start_state()
            expected_job_id = ownership.get("mapping_job_id")
            snapshot = await asyncio.to_thread(self._mapping.snapshot)
            pipeline = (
                snapshot.get("pipeline")
                if isinstance(snapshot.get("pipeline"), Mapping)
                else {}
            )
            state = str(pipeline.get("state", "failed"))
            if pipeline.get("job_id") != expected_job_id:
                raise NavigationUnavailable(
                    "localization pipeline ownership changed during startup"
                )
            if state == "running":
                return
            if state not in {"starting", "stopping"}:
                reason = " ".join(str(pipeline.get("error") or state).split())[:120]
                raise NavigationUnavailable(
                    f"localization pipeline failed: {reason}"
                )
            if state == "stopping":
                raise NavigationConflict(
                    "localization pipeline was stopped during navigation startup"
                )
            await asyncio.sleep(self._poll_interval_s)
        raise NavigationUnavailable("localization pipeline readiness timed out")

    def cleanup_localization_dependency_sync(self, token: str) -> bool:
        """Compare-and-stop only the exact Nav-owned localization job."""

        ownership = self.internal_start_state()
        if ownership.get("token") != token or not ownership.get("mapping_owned"):
            return True
        job_id = ownership.get("mapping_job_id")
        if not isinstance(job_id, str):
            return False
        try:
            _, snapshot = self._mapping.stop_mapping_if_job_id(job_id)
        except MappingJobError:
            self._logger.exception("navigation-owned localization cleanup failed")
            return False
        pipeline = (
            snapshot.get("pipeline")
            if isinstance(snapshot.get("pipeline"), Mapping)
            else {}
        )
        return bool(
            pipeline.get("job_id") != job_id
            or pipeline.get("state") not in {"starting", "running", "stopping"}
        )

    async def cleanup_localization_dependency(self, token: str) -> bool:
        return await asyncio.to_thread(
            self.cleanup_localization_dependency_sync,
            token,
        )

    async def rollback_transaction(
        self,
        token: str,
        manager: NavigationJobsPort,
        reason: str,
    ) -> bool:
        """Disarm Nav before exact mapping compare-and-stop cleanup."""

        await self.rollback_start(manager, reason)
        return await self.cleanup_localization_dependency(token)

    async def _perform_stop_cleanup(self, token: str | None) -> None:
        try:
            await asyncio.to_thread(
                self._agent.navigation_deactivate,
                reason="navigation_stop",
            )
        except Exception:
            self._logger.exception("navigation stop could not reach the ROS agent")
        manager_error: NavigationJobError | None = None
        try:
            await asyncio.to_thread(self._jobs.stop)
        except NavigationJobError as exc:
            manager_error = exc
        cleanup_complete = True
        if token is not None:
            cleanup_complete = await self.cleanup_localization_dependency(token)
        if cleanup_complete:
            if token is not None:
                self.reset_start(token)
        elif token is not None:
            self.finish_start_failure(
                token,
                "navigation stopped but localization cleanup must be retried",
                cleanup_complete=False,
            )
        if manager_error is not None:
            raise manager_error

    async def _perform_localization_only_cleanup(
        self,
        token: str | None,
        *,
        reason: str,
    ) -> None:
        """Stop only localization-owned processes and never emit motion output."""

        try:
            await asyncio.to_thread(
                self._agent.navigation_deactivate_localization_only,
                reason=reason,
            )
        except Exception:
            self._logger.exception(
                "localization-only stop could not reach the ROS agent"
            )
        manager_error: NavigationJobError | None = None
        try:
            await asyncio.to_thread(self._jobs.stop)
        except NavigationJobError as exc:
            manager_error = exc
        cleanup_complete = True
        if token is not None:
            cleanup_complete = await self.cleanup_localization_dependency(token)
        if cleanup_complete:
            if token is not None:
                self.reset_start(token)
            self._finish_localization_session(
                token,
                state="idle",
                clear=True,
            )
        else:
            self._finish_localization_session(
                token,
                state="failed",
                error="localization cleanup must be retried",
            )
        if manager_error is not None:
            raise manager_error

    async def rollback_start(
        self,
        manager: NavigationJobsPort,
        reason: str,
    ) -> None:
        """Best-effort both sides of a partially completed Nav start."""

        try:
            await asyncio.to_thread(self._agent.navigation_deactivate, reason=reason)
        except Exception:
            self._logger.exception("navigation activation rollback failed")
        try:
            await asyncio.to_thread(manager.stop)
        except Exception:
            self._logger.exception("navigation process rollback failed")

    async def rollback_localization_only(
        self,
        token: str,
        manager: NavigationJobsPort,
        reason: str,
    ) -> bool:
        try:
            await asyncio.to_thread(
                self._agent.navigation_deactivate_localization_only,
                reason=reason,
            )
        except Exception:
            self._logger.exception("localization-only activation rollback failed")
        try:
            await asyncio.to_thread(manager.stop)
        except Exception:
            self._logger.exception("localization-only process rollback failed")
        return await self.cleanup_localization_dependency(token)

    async def run_manager_start(
        self,
        manager: NavigationJobsPort,
        *,
        map_id: str,
        map_revision: str,
        parameters_revision: str,
    ) -> None:
        """Settle an uncancellable manager thread before any rollback."""

        start_task = asyncio.create_task(
            asyncio.to_thread(
                manager.start,
                map_id=map_id,
                map_revision=map_revision,
                parameters_revision=parameters_revision,
            ),
            name="navigation-manager-start",
        )
        try:
            await asyncio.shield(start_task)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(start_task)
            except Exception:
                pass
            await asyncio.shield(
                self.rollback_start(manager, "navigation_start_cancelled")
            )
            raise
        except Exception:
            await self.rollback_start(manager, "navigation_start_failed")
            raise

    async def run_localization_only_manager_start(
        self,
        manager: NavigationJobsPort,
        *,
        map_id: str,
        map_revision: str,
        parameters_revision: str,
    ) -> None:
        """Settle the uncancellable manager start; outer owner performs cleanup."""

        start_task = asyncio.create_task(
            asyncio.to_thread(
                manager.start,
                map_id=map_id,
                map_revision=map_revision,
                parameters_revision=parameters_revision,
            ),
            name="localization-only-manager-start",
        )
        try:
            await asyncio.shield(start_task)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(start_task)
            except Exception:
                pass
            raise

    async def run_activation(
        self,
        manager: NavigationJobsPort,
        *,
        map_id: str,
        map_revision: str,
        map_name: str,
        ready_after: float,
    ) -> dict[str, Any]:
        """Settle activation and public projection before any rollback."""

        activation_task = asyncio.create_task(
            asyncio.to_thread(
                self._agent.navigation_activate,
                map_id=map_id,
                map_revision=map_revision,
                map_name=map_name,
                ready_after=ready_after,
            ),
            name="navigation-runtime-activate",
        )
        try:
            await asyncio.shield(activation_task)
            return await asyncio.to_thread(self.view)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(activation_task)
            except Exception:
                pass
            await asyncio.shield(
                self.rollback_start(manager, "navigation_start_cancelled")
            )
            raise
        except Exception:
            await self.rollback_start(manager, "navigation_start_failed")
            raise

    async def run_localization_only_activation(
        self,
        manager: NavigationJobsPort,
        *,
        map_id: str,
        map_revision: str,
        map_name: str,
        ready_after: float,
    ) -> dict[str, Any]:
        activation_task = asyncio.create_task(
            asyncio.to_thread(
                self._agent.navigation_activate_localization_only,
                map_id=map_id,
                map_revision=map_revision,
                map_name=map_name,
                ready_after=ready_after,
            ),
            name="localization-only-runtime-activate",
        )
        try:
            await asyncio.shield(activation_task)
            return await asyncio.to_thread(self.view)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(activation_task)
            except Exception:
                pass
            raise

    async def _run_start_operation(
        self,
        token: str,
        manager: NavigationJobsPort,
        *,
        map_id: str,
        map_revision: str,
        map_name: str,
        parameters_revision: str,
        start_localization: bool,
        previous_mapping_job_id: str | None,
    ) -> None:
        """Complete one background START outside the shared API mutex."""

        try:
            if start_localization:
                await self.start_localization_dependency(
                    token,
                    previous_job_id=previous_mapping_job_id,
                )
            if self.start_cancelled(token):
                raise NavigationConflict("navigation startup was stopped")
            self.update_start(token, "waiting_localization")
            await self.wait_localization_dependency(token)

            if self.start_cancelled(token):
                raise NavigationConflict("navigation startup was stopped")
            self.update_start(token, "starting_navigation")
            start_fence = time.monotonic()
            await self.run_manager_start(
                manager,
                map_id=map_id,
                map_revision=map_revision,
                parameters_revision=parameters_revision,
            )

            started = await asyncio.to_thread(manager.snapshot)
            started_pipeline = (
                started.get("pipeline")
                if isinstance(started.get("pipeline"), Mapping)
                else {}
            )
            navigation_job_id = started_pipeline.get("job_id")
            if (
                str(started_pipeline.get("state", "failed")) != "running"
                or not isinstance(navigation_job_id, str)
                or JOB_ID_RE.fullmatch(navigation_job_id) is None
            ):
                raise NavigationUnavailable(
                    "navigation pipeline did not publish an ownership token"
                )
            if not self.update_start(
                token,
                "warming_navigation",
                navigation_job_id=navigation_job_id,
            ):
                raise NavigationConflict("navigation startup ownership expired")

            if self.start_cancelled(token):
                raise NavigationConflict("navigation startup was stopped")
            await self.wait_prelocalization_ready(
                manager,
                ready_after=start_fence,
            )
            await self.wait_localization_dependency(token)
            latest = await asyncio.to_thread(manager.snapshot)
            if str((latest.get("pipeline") or {}).get("state", "failed")) != "running":
                raise NavigationUnavailable(
                    "navigation pipeline stopped before motion could be armed"
                )
            await asyncio.to_thread(self._agent.navigation_start_preflight)
            if self.start_cancelled(token):
                raise NavigationConflict("navigation startup was stopped")
            self.update_start(token, "activating")
            await self.run_activation(
                manager,
                map_id=map_id,
                map_revision=map_revision,
                map_name=map_name,
                ready_after=start_fence,
            )
            if not self.commit_start(token):
                raise NavigationConflict("navigation startup was stopped")
        except asyncio.CancelledError:
            cleanup_complete = await asyncio.shield(
                self.rollback_transaction(
                    token,
                    manager,
                    "navigation_start_cancelled",
                )
            )
            self.finish_start_failure(
                token,
                "navigation startup was stopped",
                cleanup_complete=cleanup_complete,
            )
        except Exception as exc:
            cleanup_complete = await self.rollback_transaction(
                token,
                manager,
                "navigation_start_failed",
            )
            message = (
                _public_navigation_diagnostic(exc)
                or "navigation startup failed"
            )
            self.finish_start_failure(
                token,
                message,
                cleanup_complete=cleanup_complete,
            )
            self._logger.warning("navigation background startup failed: %s", message)
        finally:
            if self._start_task is asyncio.current_task():
                self._start_task = None

    async def _run_localization_only_start_operation(
        self,
        token: str,
        manager: NavigationJobsPort,
        *,
        map_id: str,
        map_revision: str,
        map_name: str,
        parameters_revision: str,
        start_localization: bool,
        previous_mapping_job_id: str | None,
    ) -> None:
        """Start no-command Nav2 and bind a distinct lease-free session."""

        try:
            if start_localization:
                await self.start_localization_dependency(
                    token,
                    previous_job_id=previous_mapping_job_id,
                )
            if self.start_cancelled(token):
                raise NavigationConflict("localization-only startup was stopped")
            self.update_start(token, "waiting_localization")
            self._update_localization_session(token, "starting")
            await self.wait_localization_dependency(token)

            if self.start_cancelled(token):
                raise NavigationConflict("localization-only startup was stopped")
            self.update_start(token, "starting_navigation")
            start_fence = time.monotonic()
            await self.run_localization_only_manager_start(
                manager,
                map_id=map_id,
                map_revision=map_revision,
                parameters_revision=parameters_revision,
            )
            started = await asyncio.to_thread(manager.snapshot)
            started_pipeline = (
                started.get("pipeline")
                if isinstance(started.get("pipeline"), Mapping)
                else {}
            )
            navigation_job_id = started_pipeline.get("job_id")
            if (
                str(started_pipeline.get("state", "failed")) != "running"
                or not isinstance(navigation_job_id, str)
                or JOB_ID_RE.fullmatch(navigation_job_id) is None
            ):
                raise NavigationUnavailable(
                    "localization-only pipeline did not publish an ownership token"
                )
            if not self.update_start(
                token,
                "warming_navigation",
                navigation_job_id=navigation_job_id,
            ):
                raise NavigationConflict("localization-only ownership expired")
            await self.wait_prelocalization_ready(
                manager,
                ready_after=start_fence,
            )
            await self.wait_localization_dependency(token)
            latest = await asyncio.to_thread(manager.snapshot)
            if str((latest.get("pipeline") or {}).get("state", "failed")) != "running":
                raise NavigationUnavailable(
                    "localization-only pipeline stopped before activation"
                )
            await asyncio.to_thread(
                self._agent.navigation_localization_only_preflight
            )
            if self.start_cancelled(token):
                raise NavigationConflict("localization-only startup was stopped")
            self.update_start(token, "activating")
            await self.run_localization_only_activation(
                manager,
                map_id=map_id,
                map_revision=map_revision,
                map_name=map_name,
                ready_after=start_fence,
            )
            if not self.commit_start(token):
                raise NavigationConflict("localization-only startup was stopped")
            if not self._update_localization_session(
                token,
                "waiting_initial_pose",
            ):
                raise NavigationConflict("localization-only ownership expired")
        except asyncio.CancelledError:
            cleanup_complete = await asyncio.shield(
                self.rollback_localization_only(
                    token,
                    manager,
                    "localization_start_cancelled",
                )
            )
            self.finish_start_failure(
                token,
                "localization-only startup was stopped",
                cleanup_complete=cleanup_complete,
            )
            self._finish_localization_session(
                token,
                state="failed",
                error="localization-only startup was stopped",
                clear=cleanup_complete,
            )
        except Exception as exc:
            cleanup_complete = await self.rollback_localization_only(
                token,
                manager,
                "localization_start_failed",
            )
            message = _public_navigation_diagnostic(exc) or "localization-only startup failed"
            self.finish_start_failure(
                token,
                message,
                cleanup_complete=cleanup_complete,
            )
            self._finish_localization_session(
                token,
                state="failed",
                error=message,
                clear=cleanup_complete,
            )
            self._logger.warning(
                "localization-only background startup failed: %s",
                message,
            )
        finally:
            if self._start_task is asyncio.current_task():
                self._start_task = None

    def handle_terminal(self, reason: str, job_id: str) -> None:
        """Synchronously close motion before one unexpected process teardown."""

        fenced = self.request_terminal_cancel(job_id)
        if fenced is None:
            return
        token, _ownership = fenced
        localization_only = self.internal_localization_session()
        try:
            if localization_only.get("token") == token:
                self._agent.navigation_deactivate_localization_only(reason=reason)
            else:
                self._agent.navigation_deactivate(reason=reason)
        except Exception:
            # A lost robot transport must never skip exact mapping cleanup.
            self._logger.exception("navigation terminal deactivation failed")
        cleanup_complete = self.cleanup_localization_dependency_sync(token)
        self.finish_start_failure(
            token,
            reason,
            cleanup_complete=cleanup_complete,
            terminal_cleanup_owner=True,
        )
        if localization_only.get("token") == token:
            self._finish_localization_session(
                token,
                state="failed",
                error=reason,
                clear=cleanup_complete,
            )

    def handle_localization_failure(self, reason: str) -> None:
        """Synchronously reverse-clean a failed lease-free runtime session."""

        localization = self.internal_localization_session()
        token = localization.get("token")
        if not localization.get("active") or not isinstance(token, str):
            return
        self.request_start_cancel()
        manager_clean = True
        try:
            self._jobs.stop()
        except Exception:
            manager_clean = False
            self._logger.exception("localization-only failure process cleanup failed")
        cleanup_complete = (
            self.cleanup_localization_dependency_sync(token) and manager_clean
        )
        self.finish_start_failure(
            token,
            reason,
            cleanup_complete=cleanup_complete,
        )
        self._finish_localization_session(
            token,
            state="failed",
            error=reason,
            clear=cleanup_complete,
        )

    async def settle_startup(self) -> None:
        """Fence and settle the coordinator-owned START worker, if any.

        Application shutdown calls this before lifecycle observers are closed.
        Calling it again is harmless: a completed task is never cancelled or
        awaited twice, while a still-running task is always fenced first.
        """

        task = self._start_task
        if task is None or task.done():
            return
        self.request_start_cancel()
        task.cancel()
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            pass
        except Exception:
            self._logger.exception("navigation startup shutdown settlement failed")

    async def close(self) -> None:
        """Settle START, close Nav motion/processes, then exact mapping ownership."""

        await self.settle_startup()
        startup = self.internal_start_state()
        token = startup.get("token")
        localization = self.internal_localization_session()
        try:
            if localization.get("active"):
                await asyncio.to_thread(
                    self._agent.navigation_deactivate_localization_only,
                    reason="server_shutdown",
                )
            else:
                await asyncio.to_thread(
                    self._agent.navigation_deactivate,
                    reason="server_shutdown",
                )
        except Exception:
            self._logger.exception("navigation shutdown stop failed")
        await asyncio.to_thread(self._jobs.close)
        if isinstance(token, str):
            cleanup_complete = await self.cleanup_localization_dependency(token)
            if cleanup_complete:
                self.reset_start(token)
                if localization.get("token") == token:
                    self._finish_localization_session(
                        token,
                        state="idle",
                        clear=True,
                    )

    def view(self) -> dict[str, Any]:
        """Merge process ownership and ROS readiness into the stable UI contract."""

        manager = self._jobs.snapshot()
        try:
            runtime = self._agent.navigation_runtime_snapshot()
        except Exception:
            self._logger.exception("navigation runtime snapshot failed")
            runtime = {}

        startup = self.start_state()
        localization_session = self.localization_session()
        runtime_localization_session = (
            runtime.get("localization_session")
            if isinstance(runtime.get("localization_session"), Mapping)
            else {}
        )
        if localization_session.get("active") and runtime_localization_session.get(
            "active"
        ):
            if (
                runtime_localization_session.get("map_id")
                == localization_session.get("map_id")
                and runtime_localization_session.get("map_revision")
                == localization_session.get("map_revision")
            ):
                runtime_state = str(runtime_localization_session.get("state", ""))
                if runtime_state in LOCALIZATION_SESSION_STATES:
                    localization_session["state"] = runtime_state
                localization_session["initial_pose_count"] = int(
                    runtime_localization_session.get("initial_pose_count", 0) or 0
                )
                localization_session["initial_pose"] = (
                    runtime_localization_session.get("initial_pose")
                    if isinstance(
                        runtime_localization_session.get("initial_pose"), Mapping
                    )
                    else localization_session.get("initial_pose")
                )
                for key in (
                    "raw_command_count",
                    "zero_command_count",
                    "nonzero_command_count",
                ):
                    localization_session[key] = int(
                        runtime_localization_session.get(key, 0) or 0
                    )
        startup_phase = str(startup.get("phase", "idle"))
        startup_pending = bool(startup.get("pending", False))
        manager_pipeline = (
            manager.get("pipeline")
            if isinstance(manager.get("pipeline"), Mapping)
            else {}
        )
        pipeline_state = str(manager_pipeline.get("state", "failed"))
        if pipeline_state not in {"idle", "starting", "running", "stopping", "failed"}:
            pipeline_state = "failed"
        if startup_pending and pipeline_state in {"idle", "failed"}:
            pipeline_state = "starting"
        elif startup_phase == "failed" and pipeline_state == "idle":
            pipeline_state = "failed"
        pipeline = {
            "state": pipeline_state,
            "job_id": manager_pipeline.get("job_id"),
            "error": _public_navigation_diagnostic(
                manager_pipeline.get("error") or startup.get("error")
            ),
            "started_at": manager_pipeline.get("started_at"),
        }

        runtime_readiness = (
            runtime.get("readiness")
            if isinstance(runtime.get("readiness"), Mapping)
            else {}
        )
        readiness = {
            key: bool(runtime_readiness.get(key, False))
            for key in (
                "map_server",
                "localization",
                "planner",
                "controller",
                "behavior",
                "cmd_bridge",
                "map",
                "scan",
                "odometry",
                "tf",
                "action_server",
            )
        }
        for key in (
            "cmd_vel_publishers",
            "scan_publishers",
            "odometry_publishers",
            "controller_odometry_publishers",
            "runtime_health_publishers",
            "localization_publishers",
        ):
            value = runtime_readiness.get(key)
            readiness[key] = value if type(value) is int else 0
        manager_available = bool(manager.get("available", False))
        runtime_available = bool(runtime.get("available", False))
        available = manager_available and runtime_available
        robot_online = bool(runtime.get("robot_online", False))
        mapping_busy, mapping_blockers = self._mapping.activity()
        shared_mapping_state = self._mapping.pipeline_state()
        if (
            startup_pending
            and startup.get("mapping_job_id")
            and startup.get("mapping_job_id")
            == (self._mapping.snapshot().get("pipeline") or {}).get("job_id")
        ):
            mapping_blockers = [
                blocker
                for blocker in mapping_blockers
                if blocker != "mapping_transition"
            ]
            mapping_busy = bool(mapping_blockers)

        runtime_safety = (
            runtime.get("safety")
            if isinstance(runtime.get("safety"), Mapping)
            else {}
        )
        blockers = [
            str(item)
            for item in runtime_safety.get("blockers", [])
            if isinstance(item, str) and item
        ]
        blockers.extend(mapping_blockers)
        if not manager_available or not runtime_available:
            blockers.append("navigation_unavailable")
        if not robot_online:
            blockers.append("robot_offline")
        if pipeline_state in {"starting", "stopping"}:
            blockers.append("navigation_transition")
        if pipeline_state == "running" and shared_mapping_state != "running":
            blockers.append("localization_pipeline_not_running")
        blockers = list(dict.fromkeys(blockers))

        manager_map = (
            manager.get("map") if isinstance(manager.get("map"), Mapping) else None
        )
        localization = (
            runtime.get("localization")
            if isinstance(runtime.get("localization"), Mapping)
            else {}
        )
        localization_state = str(localization.get("state", "uninitialized"))
        if localization_state not in {
            "uninitialized",
            "localizing",
            "localized",
            "lost",
        }:
            localization_state = "lost"
        localization_view = {
            "state": localization_state,
            "pose": (
                localization.get("pose")
                if isinstance(localization.get("pose"), Mapping)
                else None
            ),
        }
        goal = (
            runtime.get("goal")
            if isinstance(runtime.get("goal"), Mapping)
            else {}
        )
        goal_state = str(goal.get("state", "idle"))
        if goal_state not in {
            "idle",
            "pending",
            "active",
            "canceling",
            "succeeded",
            "failed",
            "canceled",
        }:
            goal_state = "failed"
        first_nonready_health = (
            dict(goal.get("first_nonready_health"))
            if isinstance(goal.get("first_nonready_health"), Mapping)
            else None
        )
        goal_view = {
            "state": goal_state,
            "goal_id": goal.get("goal_id"),
            "pose": goal.get("pose") if isinstance(goal.get("pose"), Mapping) else None,
            "distance_remaining": goal.get("distance_remaining"),
            "initial_distance": goal.get("initial_distance"),
            "navigation_time": goal.get("navigation_time"),
            "recoveries": int(goal.get("recoveries", 0) or 0),
            "error": _public_navigation_diagnostic(goal.get("error")),
            "first_nonready_health": first_nonready_health,
        }
        running = pipeline_state == "running" and manager_map is not None
        runtime_goal_active = goal_state in {"pending", "active", "canceling"}
        manager_cleanup_required = bool(
            pipeline_state in {"starting", "running", "stopping"}
            or manager_pipeline.get("job_id")
        )
        runtime_cleanup_required = bool(
            runtime.get("active")
            or runtime.get("cleanup_required")
            or runtime.get("map")
            or runtime_goal_active
            or runtime.get("navigation_lease_active")
            or runtime_localization_session.get("active")
        )
        runtime_bindings = (
            runtime.get("bindings")
            if isinstance(runtime.get("bindings"), Mapping)
            else {}
        )
        controller_odometry_topic = str(
            runtime_bindings.get("controller_odometry")
            or manager.get("controller_odometry_topic")
            or "/utlidar/robot_odom"
        )
        navigation_profile = str(
            runtime_bindings.get("navigation_profile")
            or manager.get("navigation_profile")
            or "go2-xt16-wired"
        )
        startup_cleanup_required = bool(
            startup_pending
            or startup.get("mapping_owned")
            or startup_phase in {"active", "stopping"}
        )
        safety = {
            "can_start": bool(
                available
                and robot_online
                and not mapping_busy
                and not startup_cleanup_required
                and pipeline_state in {"idle", "failed"}
                and runtime_safety.get("can_start", False)
            ),
            "can_set_initial_pose": bool(
                running
                and shared_mapping_state == "running"
                and runtime_safety.get("can_set_initial_pose", False)
            ),
            "can_send_goal": bool(
                running
                and not localization_session.get("active")
                and shared_mapping_state == "running"
                and runtime_safety.get("can_send_goal", False)
            ),
            "can_start_localization_only": bool(
                available
                and not mapping_busy
                and not startup_cleanup_required
                and pipeline_state in {"idle", "failed"}
                and runtime_safety.get("can_start_localization_only", False)
            ),
            "can_set_localization_only_initial_pose": bool(
                running
                and localization_session.get("active")
                and localization_session.get("state") == "waiting_initial_pose"
                and shared_mapping_state == "running"
                and runtime_safety.get(
                    "can_set_localization_only_initial_pose",
                    False,
                )
            ),
            "can_stop": bool(
                manager_cleanup_required
                or runtime_cleanup_required
                or startup_cleanup_required
            ),
            "blockers": blockers,
        }
        result: dict[str, Any] = {
            "seq": max(
                int(manager.get("seq", 0) or 0),
                int(runtime.get("seq", 0) or 0),
                int(startup.get("seq", 0) or 0),
            ),
            "available": available,
            "robot_online": robot_online,
            "pipeline": pipeline,
            "readiness": readiness,
            "map": manager_map,
            "localization": localization_view,
            "session_mode": (
                "localization_only"
                if localization_session.get("active")
                else "navigation"
                if runtime.get("active")
                else "idle"
            ),
            "localization_session": localization_session,
            "goal": goal_view,
            "safety": safety,
            "command_topic": str(
                manager.get("command_topic", "/robot_scope/nav/cmd_vel_raw")
            ),
            "bindings": {
                "navigation_profile": navigation_profile,
                "scan": "/scan",
                "odometry": controller_odometry_topic,
                "localization_odometry": "/Odometry",
                "controller_odometry": controller_odometry_topic,
                "command": "/robot_scope/nav/cmd_vel_raw",
            },
            "localization_pipeline": {
                "state": shared_mapping_state,
                "shared": True,
                "phase": startup_phase,
                "pending": startup_pending,
                "owned_by_navigation": bool(startup.get("mapping_owned", False)),
                "job_id": startup.get("mapping_job_id"),
                "error": _public_navigation_diagnostic(startup.get("error")),
            },
        }
        controller_source = runtime.get("controller_source")
        if isinstance(controller_source, Mapping):
            result["controller_source"] = dict(controller_source)
        health = runtime.get("localization_health")
        if isinstance(health, Mapping):
            result["localization_health"] = dict(health)
        calibration = runtime.get("calibration_assistant")
        if isinstance(calibration, Mapping):
            result["calibration_assistant"] = dict(calibration)
        deactivation_reason = runtime.get("deactivation_reason")
        if isinstance(deactivation_reason, str) and deactivation_reason:
            public_reason = _public_navigation_diagnostic(deactivation_reason)
            if public_reason:
                result["deactivation_reason"] = public_reason
        path = runtime.get("path")
        if isinstance(path, list):
            result["path"] = path
        return result


__all__ = [
    "LOCALIZATION_SESSION_STATES",
    "MANUAL_CONTROL_BLOCKING_PHASES",
    "NAVIGATION_LOCALIZATION_READY_TIMEOUT_S",
    "NAVIGATION_START_READY_POLL_S",
    "NAVIGATION_START_READY_TIMEOUT_S",
    "NavigationCoordinator",
    "localization_session_state",
    "navigation_start_state",
]
