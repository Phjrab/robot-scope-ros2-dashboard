"""Fail-closed lifecycle control for the dedicated Go2 control bridge.

The manager intentionally owns one immutable systemd unit and two immutable
mutation commands.  Browser input can select only ``start`` or ``stop``; it
can never supply a unit name, argv item, shell fragment, environment value or
privilege option.  The HTTP layer is responsible for same-origin enforcement.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence


SERVICE_NAME = "robot-scope-control-bridge.service"
SUDO_PATH = "/usr/bin/sudo"
SYSTEMCTL_PATH = "/usr/bin/systemctl"
SSH_PATH = "/usr/bin/ssh"
LIFECYCLE_TRANSPORT_ENV = "ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_TRANSPORT"
REMOTE_USER_ENV = "ROBOT_SCOPE_CONTROL_BRIDGE_REMOTE_USER"
SSH_IDENTITY_ENV = "ROBOT_SCOPE_CONTROL_BRIDGE_SSH_IDENTITY"
SSH_KNOWN_HOSTS_ENV = "ROBOT_SCOPE_CONTROL_BRIDGE_SSH_KNOWN_HOSTS"
MUTATION_COMMANDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "start": (
            SUDO_PATH,
            "-n",
            SYSTEMCTL_PATH,
            "--no-block",
            "start",
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
STATUS_COMMAND = (
    SYSTEMCTL_PATH,
    "show",
    "--property=ActiveState",
    "--property=SubState",
    "--property=InvocationID",
    "--property=LoadState",
    "--property=UnitFileState",
    SERVICE_NAME,
)
ACTIVE_OPERATION_STATES = frozenset({"scheduled", "dispatching", "waiting"})
_TRANSITIONING_SYSTEMD_STATES = frozenset(
    {"activating", "deactivating", "reloading", "refreshing"}
)
_SYSTEMD_VALUE = re.compile(r"^[A-Za-z0-9_.:@-]{0,128}$")
_INVOCATION_ID = re.compile(r"^[0-9a-fA-F]{32}$")
_SSH_USER = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


class ControlBridgeLifecycleError(RuntimeError):
    """Base class for expected control-bridge lifecycle failures."""


class ControlBridgeLifecycleUnavailable(ControlBridgeLifecycleError):
    """Raised when the fixed lifecycle facility cannot be used safely."""


class ControlBridgeLifecycleConfirmationRequired(ControlBridgeLifecycleError):
    """Raised unless the operator explicitly confirms the mutation."""


class ControlBridgeLifecycleBusy(ControlBridgeLifecycleError):
    """Raised while a start or stop transition is already in progress."""


class ControlBridgeLifecycleBlocked(ControlBridgeLifecycleError):
    """Raised when the requested transition fails its safety preflight."""

    def __init__(self, action: str, blockers: Sequence[str]) -> None:
        self.action = str(action)
        self.blockers = tuple(dict.fromkeys(str(item) for item in blockers if item))
        super().__init__(f"control bridge {self.action} is blocked")


CommandRunner = Callable[
    [tuple[str, ...], float], subprocess.CompletedProcess[str]
]
PreflightProvider = Callable[[], Mapping[str, Sequence[str]]]
BridgeStatusProvider = Callable[[], bool | None]
ExecutableProbe = Callable[[str], bool]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enabled(value: object) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _default_executable_probe(path: str) -> bool:
    candidate = Path(path)
    return candidate.is_file() and os.access(candidate, os.X_OK)


def _fixed_environment() -> dict[str, str]:
    return {
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
    }


def _default_mutation_runner(
    command: tuple[str, ...],
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    """Run one trusted mutation without a shell, prompt or inherited hooks."""

    return subprocess.run(
        command,
        shell=False,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=timeout_seconds,
        env=_fixed_environment(),
    )


def _default_status_runner(
    command: tuple[str, ...],
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    """Read only the fixed public systemd fields for the fixed unit."""

    return subprocess.run(
        command,
        shell=False,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=timeout_seconds,
        env=_fixed_environment(),
    )


class FixedSshControlBridgeRunner:
    """Run the fixed lifecycle vocabulary through one restricted SSH key."""

    def __init__(
        self,
        *,
        host: str,
        user: str,
        identity_file: str,
        known_hosts_file: str,
    ) -> None:
        from .control_datagram import private_control_host

        # Reuse the datagram address validator without permitting a second,
        # independently configurable lifecycle target.
        validated_host = private_control_host(
            host,
            field="remote control bridge host",
        )
        if not _SSH_USER.fullmatch(user):
            raise ValueError("remote control bridge user is invalid")
        identity = Path(identity_file)
        known_hosts = Path(known_hosts_file)
        if not identity.is_absolute() or identity == Path("/"):
            raise ValueError("control bridge SSH identity must be an absolute file")
        if not known_hosts.is_absolute() or known_hosts == Path("/"):
            raise ValueError("control bridge known-hosts path must be absolute")
        self.host = validated_host
        self.user = user
        self.identity_file = identity
        self.known_hosts_file = known_hosts

    @property
    def available(self) -> bool:
        if not _default_executable_probe(SSH_PATH):
            return False
        try:
            identity_stat = self.identity_file.lstat()
            known_hosts_stat = self.known_hosts_file.lstat()
        except OSError:
            return False
        return bool(
            stat.S_ISREG(identity_stat.st_mode)
            and stat.S_IMODE(identity_stat.st_mode) & 0o077 == 0
            and identity_stat.st_uid == os.geteuid()
            and identity_stat.st_nlink == 1
            and os.access(self.identity_file, os.R_OK)
            and stat.S_ISREG(known_hosts_stat.st_mode)
            and os.access(self.known_hosts_file, os.R_OK)
        )

    def executable_probe(self, _path: str) -> bool:
        return self.available

    def _command(self, action: str) -> tuple[str, ...]:
        if action not in {"status", "start", "stop"}:
            raise ValueError("remote control bridge action is not allowlisted")
        return (
            SSH_PATH,
            "-F",
            "/dev/null",
            "-i",
            str(self.identity_file),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self.known_hosts_file}",
            "-o",
            "ConnectTimeout=2",
            "--",
            f"{self.user}@{self.host}",
            action,
        )

    @staticmethod
    def _action_for_command(command: tuple[str, ...]) -> str:
        if command == STATUS_COMMAND:
            return "status"
        for action, expected in MUTATION_COMMANDS.items():
            if command == expected:
                return action
        raise ValueError("control bridge lifecycle command is not allowlisted")

    def run_mutation(
        self, command: tuple[str, ...], timeout_seconds: float
    ) -> subprocess.CompletedProcess[str]:
        action = self._action_for_command(command)
        if action not in {"start", "stop"}:
            raise ValueError("status cannot be dispatched as a mutation")
        return subprocess.run(
            self._command(action),
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout_seconds,
            env=_fixed_environment(),
        )

    def run_status(
        self, command: tuple[str, ...], timeout_seconds: float
    ) -> subprocess.CompletedProcess[str]:
        if self._action_for_command(command) != "status":
            raise ValueError("mutation cannot be dispatched as a status read")
        return subprocess.run(
            self._command("status"),
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout_seconds,
            env=_fixed_environment(),
        )


def _safe_systemd_value(value: object, *, fallback: str) -> str:
    rendered = str(value or "").strip()
    if not rendered or not _SYSTEMD_VALUE.fullmatch(rendered):
        return fallback
    return rendered


def parse_systemd_show(output: object) -> dict[str, Any]:
    """Parse the fixed ``systemctl show`` output into a bounded public view."""

    values: dict[str, str] = {}
    if isinstance(output, str):
        for line in output.splitlines()[:16]:
            key, separator, value = line.partition("=")
            if separator and key in {
                "ActiveState",
                "SubState",
                "InvocationID",
                "LoadState",
                "UnitFileState",
            }:
                values[key] = value
    active_state = _safe_systemd_value(values.get("ActiveState"), fallback="unknown")
    sub_state = _safe_systemd_value(values.get("SubState"), fallback="unknown")
    load_state = _safe_systemd_value(values.get("LoadState"), fallback="unknown")
    unit_file_state = _safe_systemd_value(
        values.get("UnitFileState"), fallback="unknown"
    )
    invocation = str(values.get("InvocationID") or "").strip()
    if not _INVOCATION_ID.fullmatch(invocation):
        invocation = ""
    available = bool(
        active_state != "unknown"
        and sub_state != "unknown"
        and load_state == "loaded"
        and unit_file_state != "unknown"
    )
    return {
        "available": available,
        "active_state": active_state,
        "sub_state": sub_state,
        "load_state": load_state,
        "unit_file_state": unit_file_state,
        "invocation_id": invocation.lower(),
        "running": active_state == "active",
        "transitioning": active_state in _TRANSITIONING_SYSTEMD_STATES,
    }


def collect_control_bridge_lifecycle_blockers(
    *,
    control: Mapping[str, Any] | None,
    navigation_runtime: Mapping[str, Any] | None,
    navigation_jobs: Mapping[str, Any] | None,
    mapping_jobs: Mapping[str, Any] | None,
    mapping_task_active: bool,
    dataset_capture_active: bool | None,
    dashboard_service_lifecycle_busy: bool | None,
) -> dict[str, list[str]]:
    """Build action-specific blockers from subsystem public snapshots.

    Robot reachability and bridge freshness deliberately are not stop blockers:
    stopping the local bridge is a cleanup action and must remain possible when
    the robot or DDS transport is offline.  Active motion ownership is always a
    blocker; the operator must disarm/cancel/stop it first and there is no force
    option.
    """

    shared: list[str] = []
    start_only: list[str] = []

    if control is None:
        shared.append("control_status_unavailable")
        start_only.extend(("control_not_configured", "control_target_incompatible"))
    else:
        enabled = control.get("enabled") is True
        transport_configured = control.get(
            "transport_configured", control.get("configured")
        ) is True
        if not enabled or not transport_configured:
            start_only.append("control_not_configured")
        restart_required = bool(
            control.get("control_restart_required", False)
            or control.get("restart_required", False)
        )
        if (
            control.get("target_supported") is not True
            or control.get("target_matches_startup") is not True
            or restart_required
        ):
            start_only.append("control_target_incompatible")

        lease = control.get("lease") if isinstance(control.get("lease"), dict) else {}
        if lease.get("active"):
            source = str(lease.get("input_source") or lease.get("source") or "")
            if source == "navigation":
                shared.append("navigation_active")
            elif source in {"keyboard", "gamepad"}:
                shared.append("manual_control_active")
            else:
                shared.append("control_lease_active")
        action_guard = (
            control.get("action_guard")
            if isinstance(control.get("action_guard"), dict)
            else {}
        )
        if action_guard.get("active"):
            shared.append("robot_action_active")

    if navigation_runtime is None:
        shared.append("navigation_status_unavailable")
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
            shared.append("navigation_active")

    if navigation_jobs is None:
        shared.append("navigation_status_unavailable")
    else:
        pipeline = (
            navigation_jobs.get("pipeline")
            if isinstance(navigation_jobs.get("pipeline"), dict)
            else {}
        )
        if pipeline.get("state") in {"starting", "running", "stopping"}:
            shared.append("navigation_active")

    # Mapping and dataset capture do not consume the signed Go2 motion lease or
    # the dedicated bridge process.  Their snapshots are intentionally
    # inspected by the application preflight but do not block this independent
    # lifecycle.  This preserves simultaneous mapping/capture while driving.
    _ = mapping_jobs, mapping_task_active, dataset_capture_active

    if dashboard_service_lifecycle_busy is None:
        shared.append("dashboard_service_lifecycle_status_unavailable")
    elif dashboard_service_lifecycle_busy:
        shared.append("dashboard_service_lifecycle_active")

    shared = list(dict.fromkeys(shared))
    return {
        "start": list(dict.fromkeys([*start_only, *shared])),
        "stop": list(shared),
    }


class ControlBridgeLifecycleManager:
    """Serialize and observe start/stop transitions for the fixed bridge unit."""

    def __init__(
        self,
        *,
        enabled: bool,
        preflight_provider: PreflightProvider | None = None,
        bridge_status_provider: BridgeStatusProvider | None = None,
        mutation_runner: CommandRunner | None = None,
        status_runner: CommandRunner | None = None,
        executable_probe: ExecutableProbe | None = None,
        command_timeout_seconds: float = 3.0,
        status_timeout_seconds: float = 1.0,
        transition_timeout_seconds: float = 10.0,
        poll_interval_seconds: float = 0.1,
    ) -> None:
        if not 0.5 <= float(command_timeout_seconds) <= 10.0:
            raise ValueError("command timeout must be between 0.5 and 10 seconds")
        if not 0.1 <= float(status_timeout_seconds) <= 5.0:
            raise ValueError("status timeout must be between 0.1 and 5 seconds")
        if not 0.5 <= float(transition_timeout_seconds) <= 30.0:
            raise ValueError("transition timeout must be between 0.5 and 30 seconds")
        if not 0.01 <= float(poll_interval_seconds) <= 1.0:
            raise ValueError("poll interval must be between 0.01 and 1 second")

        self._enabled = bool(enabled)
        self._preflight_provider = preflight_provider or (
            lambda: {"start": (), "stop": ()}
        )
        self._bridge_status_provider = bridge_status_provider or (lambda: False)
        self._mutation_runner = mutation_runner or _default_mutation_runner
        self._status_runner = status_runner or _default_status_runner
        probe = executable_probe or _default_executable_probe
        self._mutation_runner_available = bool(
            probe(SUDO_PATH) and probe(SYSTEMCTL_PATH)
        )
        self._status_runner_available = bool(probe(SYSTEMCTL_PATH))
        self._command_timeout_seconds = float(command_timeout_seconds)
        self._status_timeout_seconds = float(status_timeout_seconds)
        self._transition_timeout_seconds = float(transition_timeout_seconds)
        self._poll_interval_seconds = float(poll_interval_seconds)
        self._instance_id = uuid.uuid4().hex
        self._privilege = "unchecked" if self._enabled else "disabled"
        self._operation: dict[str, Any] | None = None
        self._closed = False
        self._lock = threading.RLock()
        self._schedule_lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._cancel = threading.Event()

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        preflight_provider: PreflightProvider | None = None,
        bridge_status_provider: BridgeStatusProvider | None = None,
    ) -> "ControlBridgeLifecycleManager":
        values = os.environ if environ is None else environ
        enabled = _enabled(
            values.get("ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_ENABLED")
        )
        lifecycle_transport = str(
            values.get(LIFECYCLE_TRANSPORT_ENV, "local")
        ).strip().casefold() or "local"
        if lifecycle_transport == "local":
            return cls(
                enabled=enabled,
                preflight_provider=preflight_provider,
                bridge_status_provider=bridge_status_provider,
            )
        if lifecycle_transport != "ssh":
            return cls(
                enabled=enabled,
                preflight_provider=preflight_provider,
                bridge_status_provider=bridge_status_provider,
                executable_probe=lambda _path: False,
            )
        try:
            from .control_datagram import (
                CONTROL_TRANSPORT_UDP,
                ControlDatagramConfig,
                control_transport_mode,
            )

            if control_transport_mode(values) != CONTROL_TRANSPORT_UDP:
                raise ValueError("remote lifecycle requires udp control transport")
            datagram_config = ControlDatagramConfig.from_environment(values)
            runner = FixedSshControlBridgeRunner(
                host=datagram_config.peer_host,
                user=str(values.get(REMOTE_USER_ENV, "")),
                identity_file=str(values.get(SSH_IDENTITY_ENV, "")),
                known_hosts_file=str(values.get(SSH_KNOWN_HOSTS_ENV, "")),
            )
        except (OSError, ValueError):
            return cls(
                enabled=enabled,
                preflight_provider=preflight_provider,
                bridge_status_provider=bridge_status_provider,
                executable_probe=lambda _path: False,
            )
        return cls(
            enabled=enabled,
            preflight_provider=preflight_provider,
            bridge_status_provider=bridge_status_provider,
            mutation_runner=runner.run_mutation,
            status_runner=runner.run_status,
            executable_probe=runner.executable_probe,
        )

    @property
    def configured(self) -> bool:
        return bool(
            self._enabled
            and self._mutation_runner_available
            and self._status_runner_available
        )

    def _preflight(self) -> dict[str, list[str]]:
        try:
            raw = self._preflight_provider()
            if not isinstance(raw, Mapping):
                raise TypeError("preflight provider returned a non-mapping")
            result: dict[str, list[str]] = {}
            for action in ("start", "stop"):
                values = raw.get(action, ())
                if isinstance(values, (str, bytes)):
                    raise TypeError("preflight provider returned a scalar")
                result[action] = list(
                    dict.fromkeys(str(item) for item in values if str(item))
                )[:24]
            return result
        except Exception:
            return {
                "start": ["lifecycle_preflight_unavailable"],
                "stop": ["lifecycle_preflight_unavailable"],
            }

    @staticmethod
    def _unknown_systemd() -> dict[str, Any]:
        return {
            "available": False,
            "active_state": "unknown",
            "sub_state": "unknown",
            "load_state": "unknown",
            "unit_file_state": "unknown",
            "invocation_id": "",
            "running": False,
            "transitioning": False,
        }

    def _read_systemd(self) -> dict[str, Any]:
        if not self._status_runner_available:
            return self._unknown_systemd()
        try:
            with self._status_lock:
                result = self._status_runner(
                    STATUS_COMMAND,
                    self._status_timeout_seconds,
                )
        except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
            return self._unknown_systemd()
        except Exception:
            return self._unknown_systemd()
        if int(getattr(result, "returncode", 1)) != 0:
            return self._unknown_systemd()
        return parse_systemd_show(getattr(result, "stdout", ""))

    def _bridge_status_fresh(self) -> bool | None:
        """Return whether authenticated bridge status is still being observed."""

        try:
            value = self._bridge_status_provider()
        except Exception:
            return None
        return value if isinstance(value, bool) else None

    def snapshot(self) -> dict[str, Any]:
        systemd = self._read_systemd()
        blockers = self._preflight()
        with self._lock:
            operation = dict(self._operation) if self._operation is not None else None
            busy = bool(operation and operation.get("state") in ACTIVE_OPERATION_STATES)
            configured = self.configured and not self._closed
            start_state_ready = bool(
                systemd["available"]
                and systemd["active_state"] in {"inactive", "failed"}
            )
            stop_state_ready = bool(
                systemd["available"]
                and systemd["active_state"] not in {"inactive", "failed"}
            )
            return {
                "service": SERVICE_NAME,
                "instance_id": self._instance_id,
                "enabled": self._enabled,
                "configured": configured,
                "systemd": systemd,
                "blockers": blockers,
                "can_start": bool(
                    configured and not busy and start_state_ready and not blockers["start"]
                ),
                "can_stop": bool(
                    configured and not busy and stop_state_ready and not blockers["stop"]
                ),
                "operation": operation,
                "privilege": {
                    "runner_available": self._mutation_runner_available,
                    "last_result": self._privilege,
                },
            }

    def is_busy(self) -> bool:
        with self._lock:
            return bool(
                self._operation
                and self._operation.get("state") in ACTIVE_OPERATION_STATES
            )

    def schedule_start(self, *, confirmed: bool) -> dict[str, Any]:
        return self._schedule("start", confirmed=confirmed)

    def schedule_stop(self, *, confirmed: bool) -> dict[str, Any]:
        return self._schedule("stop", confirmed=confirmed)

    def _schedule(self, action: str, *, confirmed: bool) -> dict[str, Any]:
        if action not in MUTATION_COMMANDS:
            raise ControlBridgeLifecycleUnavailable(
                "control bridge service action is not allowlisted"
            )
        if confirmed is not True:
            raise ControlBridgeLifecycleConfirmationRequired(
                "confirmed=true is required for control bridge service operations"
            )

        # Serialize the check/reservation sequence without holding the state
        # lock across subsystem callbacks or systemctl.  Snapshot takes those
        # external locks before the state lock, so this ordering avoids a
        # status-lock/state-lock inversion while keeping concurrent mutations
        # single-flight.
        with self._schedule_lock:
            with self._lock:
                if self._closed or not self._enabled:
                    raise ControlBridgeLifecycleUnavailable(
                        "control bridge service lifecycle is not configured"
                    )
                if not self._mutation_runner_available:
                    raise ControlBridgeLifecycleUnavailable(
                        "control bridge service runner is unavailable"
                    )
                if (
                    self._operation
                    and self._operation.get("state") in ACTIVE_OPERATION_STATES
                ):
                    raise ControlBridgeLifecycleBusy(
                        "another control bridge service operation is already active"
                    )
            blockers = self._preflight()[action]
            if blockers:
                raise ControlBridgeLifecycleBlocked(action, blockers)
            systemd = self._read_systemd()
            if not systemd["available"]:
                raise ControlBridgeLifecycleUnavailable(
                    "control bridge systemd status is unavailable"
                )
            if action == "start" and systemd["active_state"] not in {
                "inactive",
                "failed",
            }:
                raise ControlBridgeLifecycleBlocked(
                    action, ["control_bridge_service_already_active"]
                )

            with self._lock:
                if self._closed:
                    raise ControlBridgeLifecycleUnavailable(
                        "control bridge service lifecycle is not configured"
                    )
                if (
                    self._operation
                    and self._operation.get("state") in ACTIVE_OPERATION_STATES
                ):
                    raise ControlBridgeLifecycleBusy(
                        "another control bridge service operation is already active"
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
                    args=(operation_id, action, systemd),
                    name=f"control-bridge-lifecycle-{action}",
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
                self._operation["exit_status"] = max(
                    -255, min(int(exit_status), 255)
                )

    @staticmethod
    def _desired_state(action: str, systemd: Mapping[str, Any]) -> bool:
        active_state = str(systemd.get("active_state", "unknown"))
        if action == "start":
            return active_state == "active"
        return active_state in {"inactive", "failed"}

    def _dispatch(
        self,
        operation_id: str,
        action: str,
        initial_systemd: Mapping[str, Any],
    ) -> None:
        if self._cancel.is_set():
            self._update_operation(
                operation_id, state="cancelled", error="application_shutdown"
            )
            return

        blockers = self._preflight()[action]
        if blockers:
            self._update_operation(
                operation_id, state="blocked", error="preflight_blocked"
            )
            return

        current = self._read_systemd()
        if not current["available"]:
            self._update_operation(
                operation_id, state="failed", error="systemd_status_unavailable"
            )
            return
        if self._desired_state(action, current) and (
            action == "start" or self._bridge_status_fresh() is False
        ):
            self._update_operation(operation_id, state="succeeded")
            return

        # Shutdown can begin while the worker is inside the bounded preflight
        # or systemd status probe above.  Recheck at the final dispatch boundary
        # so closing the dashboard never launches a newly queued bridge command.
        if self._cancel.is_set():
            self._update_operation(
                operation_id,
                state="cancelled",
                error="application_shutdown",
            )
            return

        self._update_operation(operation_id, state="dispatching")
        if self._cancel.is_set():
            self._update_operation(
                operation_id,
                state="cancelled",
                error="application_shutdown",
            )
            return
        try:
            result = self._mutation_runner(
                MUTATION_COMMANDS[action],
                self._command_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            with self._lock:
                self._privilege = "unknown"
            self._update_operation(
                operation_id, state="failed", error="dispatch_timeout"
            )
            return
        except (OSError, subprocess.SubprocessError):
            with self._lock:
                self._privilege = "unavailable"
            self._update_operation(
                operation_id, state="failed", error="dispatch_unavailable"
            )
            return
        except Exception:
            with self._lock:
                self._privilege = "unknown"
            self._update_operation(
                operation_id, state="failed", error="dispatch_failed"
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
        self._update_operation(operation_id, state="waiting")

        deadline = time.monotonic() + self._transition_timeout_seconds
        last = dict(initial_systemd)
        while time.monotonic() < deadline:
            if self._cancel.wait(self._poll_interval_seconds):
                self._update_operation(
                    operation_id,
                    state="cancelled",
                    error="application_shutdown",
                )
                return
            last = self._read_systemd()
            desired = self._desired_state(action, last)
            bridge_stale = action == "start" or self._bridge_status_fresh() is False
            if desired and bridge_stale:
                self._update_operation(operation_id, state="succeeded")
                return

        if not last.get("available"):
            error = "systemd_status_timeout"
        elif action == "stop" and self._bridge_status_fresh() is not False:
            error = "bridge_status_timeout"
        else:
            error = "service_transition_timeout"
        self._update_operation(operation_id, state="failed", error=error)

    def close(self) -> None:
        """Cancel pending observation; never issue a mutation during shutdown."""

        with self._lock:
            self._closed = True
            self._cancel.set()


__all__ = [
    "MUTATION_COMMANDS",
    "FixedSshControlBridgeRunner",
    "LIFECYCLE_TRANSPORT_ENV",
    "REMOTE_USER_ENV",
    "SERVICE_NAME",
    "SSH_IDENTITY_ENV",
    "SSH_KNOWN_HOSTS_ENV",
    "SSH_PATH",
    "STATUS_COMMAND",
    "ControlBridgeLifecycleBlocked",
    "ControlBridgeLifecycleBusy",
    "ControlBridgeLifecycleConfirmationRequired",
    "ControlBridgeLifecycleError",
    "ControlBridgeLifecycleManager",
    "ControlBridgeLifecycleUnavailable",
    "collect_control_bridge_lifecycle_blockers",
    "parse_systemd_show",
]
