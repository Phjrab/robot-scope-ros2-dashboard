"""Fail-closed, allowlisted lifecycle control for the dashboard service.

Only the two immutable ``systemctl`` argv entries below can be dispatched.
Same-origin enforcement belongs to the HTTP layer; this manager owns explicit
confirmation, bounded asynchronous execution, idle preflight rechecks and
public status that never exposes command lines.
"""

from __future__ import annotations

import os
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence


SERVICE_NAME = "robot-scope.service"
SUDO_PATH = "/usr/bin/sudo"
SYSTEMCTL_PATH = "/usr/bin/systemctl"
ACTIVE_STATES = frozenset({"scheduled", "dispatching", "queued"})
COMMANDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "restart": (
            SUDO_PATH,
            "-n",
            SYSTEMCTL_PATH,
            "--no-block",
            "restart",
            SERVICE_NAME,
        ),
        "stop": (
            SUDO_PATH,
            "-n",
            SYSTEMCTL_PATH,
            "--no-block",
            "stop",
            SERVICE_NAME,
        ),
    }
)


class ServiceLifecycleError(RuntimeError):
    """Base class for expected service lifecycle failures."""


class ServiceLifecycleUnavailable(ServiceLifecycleError):
    """Raised when lifecycle control has not been safely configured."""


class ServiceLifecycleConfirmationRequired(ServiceLifecycleError):
    """Raised when the request lacks an explicit confirmation."""


class ServiceLifecycleBusy(ServiceLifecycleError):
    """Raised while another lifecycle operation is still active."""


class ServiceLifecycleBlocked(ServiceLifecycleError):
    """Raised when robot, navigation or mapping activity is in progress."""

    def __init__(self, blockers: Sequence[str]) -> None:
        self.blockers = tuple(dict.fromkeys(str(item) for item in blockers if item))
        super().__init__("service lifecycle is blocked by active robot work")


CommandRunner = Callable[
    [tuple[str, ...], float], subprocess.CompletedProcess[str]
]
BlockerProvider = Callable[[], Sequence[str]]
ExecutableProbe = Callable[[str], bool]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enabled(value: object) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _default_executable_probe(path: str) -> bool:
    candidate = Path(path)
    return candidate.is_file() and os.access(candidate, os.X_OK)


def _default_command_runner(
    command: tuple[str, ...],
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    """Run one trusted argv without a shell, prompt or inherited user hooks."""

    return subprocess.run(
        command,
        shell=False,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=timeout_seconds,
        env={
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
        },
    )


def collect_service_lifecycle_blockers(
    *,
    control: Mapping[str, Any] | None,
    navigation_runtime: Mapping[str, Any] | None,
    navigation_jobs: Mapping[str, Any] | None,
    mapping_jobs: Mapping[str, Any] | None,
    mapping_task_active: bool,
) -> list[str]:
    """Normalize public subsystem snapshots into stable fail-closed blockers."""

    blockers: list[str] = []
    if control is None:
        blockers.append("control_status_unavailable")
    else:
        lease = control.get("lease") if isinstance(control.get("lease"), dict) else {}
        if lease.get("active"):
            source = str(lease.get("input_source") or "")
            if source == "navigation":
                blockers.append("navigation_active")
            elif source in {"keyboard", "gamepad"}:
                blockers.append("manual_control_active")
            else:
                blockers.append("control_lease_active")
        action_guard = (
            control.get("action_guard")
            if isinstance(control.get("action_guard"), dict)
            else {}
        )
        if action_guard.get("active"):
            blockers.append("robot_action_active")
        # A latched software stop has already revoked every lease and motion
        # command. Restart never restores a lease, so the latch is a safe
        # service-transition state rather than active robot work.

    if navigation_runtime is None:
        blockers.append("navigation_status_unavailable")
    else:
        goal = (
            navigation_runtime.get("goal")
            if isinstance(navigation_runtime.get("goal"), dict)
            else {}
        )
        if navigation_runtime.get("active") or goal.get("state") in {
            "pending",
            "active",
            "canceling",
        }:
            blockers.append("navigation_active")

    if navigation_jobs is None:
        blockers.append("navigation_status_unavailable")
    else:
        pipeline = (
            navigation_jobs.get("pipeline")
            if isinstance(navigation_jobs.get("pipeline"), dict)
            else {}
        )
        if pipeline.get("state") in {"starting", "running", "stopping"}:
            blockers.append("navigation_active")

    if mapping_jobs is None:
        blockers.append("mapping_status_unavailable")
    else:
        pipeline = (
            mapping_jobs.get("pipeline")
            if isinstance(mapping_jobs.get("pipeline"), dict)
            else {}
        )
        operation = (
            mapping_jobs.get("operation")
            if isinstance(mapping_jobs.get("operation"), dict)
            else {}
        )
        if pipeline.get("state") in {"starting", "running", "stopping"}:
            blockers.append("mapping_pipeline_active")
        if operation.get("state") in {"saving", "stopping"}:
            blockers.append("mapping_operation_active")

    if mapping_task_active:
        blockers.append("mapping_operation_active")
    return list(dict.fromkeys(blockers))


class ServiceLifecycleManager:
    """Serialize fixed service restart/stop jobs with a delayed dispatch."""

    def __init__(
        self,
        *,
        enabled: bool,
        blocker_provider: BlockerProvider | None = None,
        command_runner: CommandRunner | None = None,
        executable_probe: ExecutableProbe | None = None,
        dispatch_delay_seconds: float = 0.75,
        command_timeout_seconds: float = 3.0,
        transition_timeout_seconds: float = 10.0,
    ) -> None:
        if not 0.25 <= float(dispatch_delay_seconds) <= 5.0:
            raise ValueError("dispatch delay must be between 0.25 and 5 seconds")
        if not 0.5 <= float(command_timeout_seconds) <= 10.0:
            raise ValueError("command timeout must be between 0.5 and 10 seconds")
        if not 0.5 <= float(transition_timeout_seconds) <= 30.0:
            raise ValueError("transition timeout must be between 0.5 and 30 seconds")

        self._enabled = bool(enabled)
        self._blocker_provider = blocker_provider or (lambda: ())
        self._command_runner = command_runner or _default_command_runner
        probe = executable_probe or _default_executable_probe
        self._runner_available = bool(probe(SUDO_PATH) and probe(SYSTEMCTL_PATH))
        self._dispatch_delay_seconds = float(dispatch_delay_seconds)
        self._command_timeout_seconds = float(command_timeout_seconds)
        self._transition_timeout_seconds = float(transition_timeout_seconds)
        self._instance_id = uuid.uuid4().hex
        self._privilege = "unchecked" if self._enabled else "disabled"
        self._operation: dict[str, Any] | None = None
        self._closed = False
        self._lock = threading.RLock()
        self._cancel = threading.Event()

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        blocker_provider: BlockerProvider | None = None,
    ) -> "ServiceLifecycleManager":
        values = os.environ if environ is None else environ
        return cls(
            enabled=_enabled(values.get("ROBOT_SCOPE_SERVICE_LIFECYCLE_ENABLED")),
            blocker_provider=blocker_provider,
        )

    @property
    def configured(self) -> bool:
        """Retain the public API field while confirmation replaces credentials."""

        return True

    def _blockers(self) -> list[str]:
        try:
            values = self._blocker_provider()
            if isinstance(values, (str, bytes)):
                raise TypeError("blocker provider returned a scalar")
            blockers = [str(item) for item in values if str(item)]
        except Exception:
            blockers = ["lifecycle_preflight_unavailable"]
        return list(dict.fromkeys(blockers))[:16]

    def snapshot(self) -> dict[str, Any]:
        blockers = self._blockers()
        with self._lock:
            operation = dict(self._operation) if self._operation is not None else None
            busy = bool(operation and operation.get("state") in ACTIVE_STATES)
            base_ready = bool(
                self._enabled
                and self.configured
                and self._runner_available
                and not self._closed
                and not busy
                and not blockers
            )
            return {
                "service": SERVICE_NAME,
                "instance_id": self._instance_id,
                "enabled": self._enabled,
                "configured": self.configured,
                "privilege": {
                    "runner_available": self._runner_available,
                    "last_result": self._privilege,
                },
                "blockers": blockers,
                "can_restart": base_ready,
                "can_stop": base_ready,
                "operation": operation,
            }

    def is_busy(self) -> bool:
        with self._lock:
            return bool(
                self._operation
                and self._operation.get("state") in ACTIVE_STATES
            )

    def schedule_restart(self, *, confirmed: bool) -> dict[str, Any]:
        return self._schedule("restart", confirmed=confirmed)

    def schedule_stop(self, *, confirmed: bool) -> dict[str, Any]:
        return self._schedule("stop", confirmed=confirmed)

    def _schedule(self, action: str, *, confirmed: bool) -> dict[str, Any]:
        if action not in COMMANDS:
            raise ServiceLifecycleUnavailable("service action is not allowlisted")
        if confirmed is not True:
            raise ServiceLifecycleConfirmationRequired(
                "confirmed=true is required for service lifecycle operations"
            )
        blockers = self._blockers()
        if blockers:
            raise ServiceLifecycleBlocked(blockers)

        with self._lock:
            if self._closed or not self._enabled:
                raise ServiceLifecycleUnavailable(
                    "service lifecycle control is not configured"
                )
            if not self._runner_available:
                raise ServiceLifecycleUnavailable(
                    "service lifecycle runner is unavailable"
                )
            if self._operation and self._operation.get("state") in ACTIVE_STATES:
                raise ServiceLifecycleBusy(
                    "another service lifecycle operation is already active"
                )
            operation_id = uuid.uuid4().hex
            self._operation = {
                "id": operation_id,
                "action": action,
                "state": "scheduled",
                "requested_at": _utc_now(),
                "updated_at": _utc_now(),
                "error": None,
            }
            worker = threading.Thread(
                target=self._dispatch,
                args=(operation_id, action),
                name=f"service-lifecycle-{action}",
                daemon=True,
            )
            worker.start()
            return self.snapshot()

    def _update_operation(
        self,
        operation_id: str,
        *,
        state: str,
        error: str | None = None,
        exit_status: int | None = None,
    ) -> None:
        with self._lock:
            if not self._operation or self._operation.get("id") != operation_id:
                return
            self._operation["state"] = state
            self._operation["updated_at"] = _utc_now()
            self._operation["error"] = error
            if exit_status is not None:
                self._operation["exit_status"] = max(-255, min(int(exit_status), 255))

    def _dispatch(self, operation_id: str, action: str) -> None:
        if self._cancel.wait(self._dispatch_delay_seconds):
            self._update_operation(
                operation_id,
                state="cancelled",
                error="application_shutdown",
            )
            return

        blockers = self._blockers()
        if blockers:
            self._update_operation(
                operation_id,
                state="blocked",
                error="active_robot_work",
            )
            return

        self._update_operation(operation_id, state="dispatching")
        try:
            result = self._command_runner(
                COMMANDS[action],
                self._command_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            with self._lock:
                self._privilege = "unknown"
            self._update_operation(
                operation_id,
                state="failed",
                error="dispatch_timeout",
            )
            return
        except (OSError, subprocess.SubprocessError):
            with self._lock:
                self._privilege = "unavailable"
            self._update_operation(
                operation_id,
                state="failed",
                error="dispatch_unavailable",
            )
            return
        except Exception:
            with self._lock:
                self._privilege = "unknown"
            self._update_operation(
                operation_id,
                state="failed",
                error="dispatch_failed",
            )
            return

        returncode = int(getattr(result, "returncode", 1))
        if returncode != 0:
            with self._lock:
                self._privilege = "rejected"
            self._update_operation(
                operation_id,
                state="failed",
                error="dispatch_rejected",
                exit_status=returncode,
            )
            return

        with self._lock:
            self._privilege = "verified"
        self._update_operation(operation_id, state="queued")
        # A successful --no-block call should make this process receive the
        # systemd stop signal. If it remains alive, release the wedged state
        # after a fixed interval so an administrator can inspect and retry.
        if not self._cancel.wait(self._transition_timeout_seconds):
            with self._lock:
                if (
                    self._operation
                    and self._operation.get("id") == operation_id
                    and self._operation.get("state") == "queued"
                ):
                    self._privilege = "unknown"
                    self._operation["state"] = "failed"
                    self._operation["updated_at"] = _utc_now()
                    self._operation["error"] = "service_transition_not_observed"

    def close(self) -> None:
        """Cancel only a not-yet-dispatched job during application shutdown."""

        with self._lock:
            self._closed = True
            self._cancel.set()


__all__ = [
    "COMMANDS",
    "SERVICE_NAME",
    "collect_service_lifecycle_blockers",
    "ServiceLifecycleBlocked",
    "ServiceLifecycleBusy",
    "ServiceLifecycleConfirmationRequired",
    "ServiceLifecycleError",
    "ServiceLifecycleManager",
    "ServiceLifecycleUnavailable",
]
