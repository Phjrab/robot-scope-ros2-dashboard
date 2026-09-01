"""Safe process manager for dashboard-controlled mapping and map saves.

The HTTP layer is intentionally not part of this module.  Callers select a
logical action (start mapping, stop mapping, or save one of the configured map
kinds); request data is never interpreted as a command line.  Every executable
and argument template is supplied by trusted application configuration and all
processes are launched with ``shell=False`` in their own process group.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterable, Iterator, Mapping, Optional, Sequence

from .public_diagnostics import public_diagnostic


MAP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
KIND_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
SUFFIX_RE = re.compile(r"^\.[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
OUTPUT_PREFIX_TOKEN = "{output_prefix}"
WIRED_MAPPING_PROFILE = "go2-xt16-wired"
WIRELESS_MAPPING_PROFILE = "go2-xt16-wireless"
COMPETITION_DIRECT_MAPPING_PROFILE = "competition-pdf-direct"
WIRELESS_MAPPING_EXIT_REASONS = MappingProxyType(
    {
        61: "WIRELESS XT16 RELAY OFFLINE",
        62: "XT16 PACKETS STALE",
        63: "HESAI DRIVER WAITING",
        64: "WIRELESS IMU UNAUTHENTICATED",
        65: "IMU STALE",
        66: "CLOCK NOT SYNCHRONIZED",
        67: "CLOUD BRIDGE STALE",
        68: "FAST-LIO NOT READY",
        69: "WIRELESS MAPPING PREFLIGHT BLOCKED",
    }
)


class MappingJobError(RuntimeError):
    """Base class for an expected mapping-control failure."""


class JobBusyError(MappingJobError):
    """Raised when a conflicting mapping operation is already active."""


class InvalidMapName(MappingJobError):
    """Raised when a requested map name is not a safe portable filename."""


class PipelineNotRunning(MappingJobError):
    """Raised when a save requires a manager-owned mapping pipeline."""


class SaveResultError(MappingJobError):
    """Raised when a save command did not produce valid expected artifacts."""


@dataclass(frozen=True)
class CommandSpec:
    """A trusted, immutable argv allowlist entry.

    ``argv[0]`` must be an absolute executable.  No interpolation is supported
    for pipeline commands.
    """

    argv: tuple[str, ...]
    cwd: Optional[Path] = None
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        _validate_argv(self.argv, allow_output_prefix=False)
        if self.timeout_seconds <= 0 or self.timeout_seconds > 900:
            raise ValueError("command timeout must be between 0 and 900 seconds")


@dataclass(frozen=True)
class SaveCommandSpec:
    """A trusted map-save argv template and its required output artifacts.

    An argv entry may contain ``{output_prefix}``; it is replaced with a path in
    a private staging directory.  ``expected_suffixes`` are fixed extensions
    appended to that prefix, for example ``('.yaml', '.pgm')``.
    """

    argv: tuple[str, ...]
    expected_suffixes: tuple[str, ...]
    cwd: Optional[Path] = None
    timeout_seconds: float = 45.0
    min_result_bytes: int = 4
    max_result_bytes: int = 512 * 1024 * 1024

    def __post_init__(self) -> None:
        _validate_argv(self.argv, allow_output_prefix=True)
        if not any(OUTPUT_PREFIX_TOKEN in value for value in self.argv):
            raise ValueError("save command must use {output_prefix}")
        if not self.expected_suffixes:
            raise ValueError("save command must declare expected output suffixes")
        if len(set(self.expected_suffixes)) != len(self.expected_suffixes):
            raise ValueError("save command output suffixes must be unique")
        for suffix in self.expected_suffixes:
            if not isinstance(suffix, str) or not SUFFIX_RE.fullmatch(suffix):
                raise ValueError(f"unsafe save output suffix: {suffix!r}")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 900:
            raise ValueError("save timeout must be between 0 and 900 seconds")
        if self.min_result_bytes < 1 or self.min_result_bytes > 1024 * 1024:
            raise ValueError("min_result_bytes is outside the supported range")
        if (
            self.max_result_bytes < self.min_result_bytes
            or self.max_result_bytes > 2 * 1024**3
        ):
            raise ValueError("max_result_bytes is outside the supported range")


def _validate_argv(argv: Sequence[str], *, allow_output_prefix: bool) -> None:
    if not isinstance(argv, tuple) or not argv:
        raise ValueError("command argv must be a non-empty tuple")
    executable = argv[0]
    if not isinstance(executable, str) or not Path(executable).is_absolute():
        raise ValueError("command executable must be an absolute path")
    for value in argv:
        if not isinstance(value, str) or not value or "\x00" in value:
            raise ValueError("command arguments must be non-empty strings without NUL")
        remainder = value.replace(OUTPUT_PREFIX_TOKEN, "") if allow_output_prefix else value
        if "{" in remainder or "}" in remainder:
            raise ValueError("command contains an unsupported interpolation token")
        if not allow_output_prefix and OUTPUT_PREFIX_TOKEN in value:
            raise ValueError("pipeline command cannot contain output interpolation")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


class MappingJobManager:
    """Manage one sensor preview, mapping pipeline and bounded save at a time.

    The optional preview process owns only the Hesai driver and fixed XT16
    conversion bridge.  It remains active while FAST-LIO mapping starts and
    stops, so live point clouds do not depend on a mapping session.  Public
    methods are thread-safe.
    """

    def __init__(
        self,
        *,
        project_dir: Path,
        output_dir: Path,
        start_command: CommandSpec,
        preview_command: Optional[CommandSpec] = None,
        save_commands: Mapping[str, SaveCommandSpec],
        log_capacity: int = 300,
        stop_grace_seconds: float = 4.0,
        require_pipeline_for_save: bool = True,
        failure_exit_reasons: Mapping[int, str] | None = None,
        readiness_runtime_marker: str | None = None,
    ) -> None:
        self.project_dir = project_dir.expanduser().resolve(strict=True)
        if not self.project_dir.is_dir():
            raise ValueError("project_dir must be a directory")
        self.output_dir = output_dir.expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if not self.output_dir.is_dir() or self.output_dir.is_symlink():
            raise ValueError("output_dir must be a real directory")

        self.start_command = self._prepare_command(start_command)
        self.preview_command = (
            self._prepare_command(preview_command)
            if preview_command is not None
            else None
        )
        prepared_saves: dict[str, SaveCommandSpec] = {}
        for kind, spec in save_commands.items():
            if not isinstance(kind, str) or not KIND_RE.fullmatch(kind):
                raise ValueError(f"unsafe map kind: {kind!r}")
            prepared_saves[kind] = self._prepare_save_command(spec)
        self.save_commands = MappingProxyType(prepared_saves)

        if log_capacity < 10 or log_capacity > 5_000:
            raise ValueError("log_capacity must be between 10 and 5000")
        if stop_grace_seconds <= 0 or stop_grace_seconds > 30:
            raise ValueError("stop_grace_seconds must be between 0 and 30 seconds")

        self.stop_grace_seconds = float(stop_grace_seconds)
        self.require_pipeline_for_save = bool(require_pipeline_for_save)
        self.failure_exit_reasons = MappingProxyType(
            {
                int(code): public_diagnostic(reason)
                for code, reason in (failure_exit_reasons or {}).items()
                if 1 <= int(code) <= 255 and public_diagnostic(reason)
            }
        )
        if readiness_runtime_marker is not None and readiness_runtime_marker != (
            "[Robot Scope] wireless XT16 mapping readiness verified"
        ):
            raise ValueError("unsupported mapping readiness marker")
        self.readiness_runtime_marker = readiness_runtime_marker
        self._lock = threading.RLock()
        self._logs: deque[dict[str, Any]] = deque(maxlen=int(log_capacity))
        self._seq = 0
        self._pipeline_process: Optional[subprocess.Popen[str]] = None
        self._pipeline_pgid: Optional[int] = None
        self._pipeline_token = ""
        self._stop_requested = False
        self._closing = False
        self._preview_process: Optional[subprocess.Popen[str]] = None
        self._preview_pgid: Optional[int] = None
        self._preview_token = ""
        self._preview_stop_requested = False
        self._save_active = False
        self._save_process: Optional[subprocess.Popen[str]] = None
        self._save_pgid: Optional[int] = None
        self._local_operation_token: Optional[str] = None
        self._local_operation_started = False
        self._pipeline: dict[str, Any] = {
            "state": "idle",
            "job_id": None,
            "pid": None,
            "started_at": None,
            "stopped_at": None,
            "exit_code": None,
            "error": None,
        }
        self._preview: dict[str, Any] = {
            "state": "idle" if self.preview_command is not None else "disabled",
            "job_id": None,
            "pid": None,
            "started_at": None,
            "stopped_at": None,
            "exit_code": None,
            "error": None,
        }
        self._operation: dict[str, Any] = {
            "state": "idle",
            "job_id": None,
            "kind": None,
            "map_name": None,
            "started_at": None,
            "finished_at": None,
            "exit_code": None,
            "files": [],
            "details": {},
            "error": None,
        }

    @classmethod
    def for_robot_scope(
        cls,
        *,
        project_dir: Path,
        output_dir: Path,
        save_commands: Mapping[str, SaveCommandSpec],
        enable_preview: bool = False,
        mapping_profile: str = WIRED_MAPPING_PROFILE,
        **kwargs: Any,
    ) -> "MappingJobManager":
        """Build a manager using the repository's allowlisted Humble launcher."""

        project = project_dir.expanduser().resolve(strict=True)
        if mapping_profile == WIRED_MAPPING_PROFILE:
            launcher = project / "scripts" / "start_hesai_mapping_humble.sh"
            preview_launcher = project / "scripts" / "start_xt16_preview_humble.sh"
            failure_exit_reasons: Mapping[int, str] = {}
            readiness_runtime_marker = None
        elif mapping_profile == COMPETITION_DIRECT_MAPPING_PROFILE:
            launcher = (
                project
                / "scripts"
                / "start_competition_pdf_direct_mapping_humble.sh"
            )
            preview_launcher = (
                project
                / "scripts"
                / "start_competition_pdf_direct_preview_humble.sh"
            )
            failure_exit_reasons = {}
            readiness_runtime_marker = None
        elif mapping_profile == WIRELESS_MAPPING_PROFILE:
            launcher = project / "scripts" / "start_wireless_mapping_humble.sh"
            preview_launcher = None
            enable_preview = False
            failure_exit_reasons = WIRELESS_MAPPING_EXIT_REASONS
            readiness_runtime_marker = (
                "[Robot Scope] wireless XT16 mapping readiness verified"
            )
        else:
            raise ValueError("unsupported mapping profile")
        return cls(
            project_dir=project,
            output_dir=output_dir,
            start_command=CommandSpec((str(launcher),), cwd=project, timeout_seconds=30),
            preview_command=(
                CommandSpec((str(preview_launcher),), cwd=project, timeout_seconds=30)
                if enable_preview and preview_launcher is not None
                else None
            ),
            save_commands=save_commands,
            failure_exit_reasons=failure_exit_reasons,
            readiness_runtime_marker=readiness_runtime_marker,
            **kwargs,
        )

    @property
    def allowed_save_kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self.save_commands))

    def _prepare_command(self, spec: CommandSpec) -> CommandSpec:
        executable = self._resolve_executable(spec.argv[0])
        cwd = self._resolve_cwd(spec.cwd)
        return CommandSpec(
            (str(executable), *spec.argv[1:]),
            cwd=cwd,
            timeout_seconds=spec.timeout_seconds,
        )

    def _prepare_save_command(self, spec: SaveCommandSpec) -> SaveCommandSpec:
        executable = self._resolve_executable(spec.argv[0])
        cwd = self._resolve_cwd(spec.cwd)
        return SaveCommandSpec(
            (str(executable), *spec.argv[1:]),
            spec.expected_suffixes,
            cwd=cwd,
            timeout_seconds=spec.timeout_seconds,
            min_result_bytes=spec.min_result_bytes,
            max_result_bytes=spec.max_result_bytes,
        )

    @staticmethod
    def _resolve_executable(value: str) -> Path:
        try:
            executable = Path(value).expanduser().resolve(strict=True)
        except OSError as exc:
            raise ValueError(f"allowlisted executable does not exist: {value}") from exc
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError(f"allowlisted executable is not executable: {value}")
        return executable

    def _resolve_cwd(self, value: Optional[Path]) -> Path:
        cwd = (value or self.project_dir).expanduser().resolve(strict=True)
        if not cwd.is_dir():
            raise ValueError("command cwd must be a directory")
        return cwd

    def snapshot(self, *, since_log_seq: int = 0) -> dict[str, Any]:
        """Return JSON-safe state and ring-buffered logs after ``since_log_seq``."""

        with self._lock:
            requested = max(0, int(since_log_seq))
            logs = [dict(item) for item in self._logs if item["seq"] > requested]
            oldest = self._logs[0]["seq"] if self._logs else self._seq + 1
            return {
                "preview": dict(self._preview),
                "pipeline": dict(self._pipeline),
                "operation": {
                    **self._operation,
                    "files": list(self._operation["files"]),
                    "details": dict(self._operation.get("details", {})),
                },
                "allowed_save_kinds": list(self.allowed_save_kinds),
                "logs": logs,
                "log_cursor": self._seq,
                "logs_truncated": bool(requested and requested < oldest - 1),
            }

    def start_preview(self) -> dict[str, Any]:
        """Start the fixed Hesai + XT16 conversion preview process group."""

        command = self.preview_command
        if command is None:
            return self.snapshot()
        with self._lock:
            if self._closing:
                raise MappingJobError("mapping manager is shutting down")
            if self._preview["state"] in {"starting", "running", "stopping"}:
                return self.snapshot()
            token = uuid.uuid4().hex
            self._preview_token = token
            self._preview_stop_requested = False
            self._preview = {
                "state": "starting",
                "job_id": token,
                "pid": None,
                "started_at": _utc_now(),
                "stopped_at": None,
                "exit_code": None,
                "error": None,
            }
            self._append_log_locked(
                "preview",
                "starting persistent Hesai + XT16 point-cloud preview",
            )

        try:
            process = self._spawn(command.argv, command.cwd)
        except OSError as exc:
            with self._lock:
                self._preview.update(
                    state="failed",
                    stopped_at=_utc_now(),
                    error=f"preview could not be started: {exc.strerror or type(exc).__name__}",
                )
                self._append_log_locked("preview", self._preview["error"])
            raise MappingJobError("XT16 preview could not be started") from exc

        pgid = process.pid
        with self._lock:
            if self._closing:
                self._preview_stop_requested = True
            self._preview_process = process
            self._preview_pgid = pgid
            self._preview.update(state="running", pid=process.pid)
            self._append_log_locked(
                "preview",
                "XT16 preview supervisor started",
            )

        self._start_reader(process, "preview")
        threading.Thread(
            target=self._monitor_preview,
            args=(token, process, pgid),
            name="robot-scope-preview-monitor",
            daemon=True,
        ).start()
        if self._closing:
            self.stop_preview()
        return self.snapshot()

    def stop_preview(self) -> dict[str, Any]:
        """Stop only the manager-owned sensor-preview process group."""

        with self._lock:
            if self._pipeline["state"] in {"starting", "running", "stopping"}:
                raise JobBusyError("mapping must stop before the XT16 preview can stop")
            if self._preview["state"] not in {"starting", "running", "stopping"}:
                return self.snapshot()
            process = self._preview_process
            pgid = self._preview_pgid
            self._preview_stop_requested = True
            self._preview["state"] = "stopping"
            self._append_log_locked("preview", "stopping XT16 preview process group")

        if pgid is not None:
            self._terminate_group(process, pgid)

        exit_code = process.poll() if process is not None else None
        with self._lock:
            self._preview.update(
                state="stopped",
                stopped_at=_utc_now(),
                exit_code=exit_code,
                error=None,
            )
            self._preview_process = None
            self._preview_pgid = None
            self._append_log_locked("preview", "XT16 preview stopped")
        return self.snapshot()

    def start_mapping(self) -> dict[str, Any]:
        """Start the allowlisted mapping pipeline in a new process group."""

        with self._lock:
            if self._closing:
                raise MappingJobError("mapping manager is shutting down")
            if self._save_active:
                raise JobBusyError("a map save is in progress")
            if self._pipeline["state"] in {"starting", "running", "stopping"}:
                raise JobBusyError("mapping pipeline is already active")

        # The mapping launcher now owns only FAST-LIO.  Ensure its fixed raw
        # and converted point-cloud producers exist before readiness probing.
        self.start_preview()

        with self._lock:
            if self._closing:
                raise MappingJobError("mapping manager is shutting down")
            if self._save_active:
                raise JobBusyError("a map save is in progress")
            if self._pipeline["state"] in {"starting", "running", "stopping"}:
                raise JobBusyError("mapping pipeline is already active")
            token = uuid.uuid4().hex
            self._pipeline_token = token
            self._stop_requested = False
            self._pipeline = {
                "state": "starting",
                "job_id": token,
                "pid": None,
                "started_at": _utc_now(),
                "stopped_at": None,
                "exit_code": None,
                "error": None,
            }
            self._append_log_locked("pipeline", "starting allowlisted Hesai + FAST-LIO pipeline")

        try:
            process = self._spawn(self.start_command.argv, self.start_command.cwd)
        except OSError as exc:
            with self._lock:
                self._pipeline.update(
                    state="failed",
                    stopped_at=_utc_now(),
                    error=f"pipeline could not be started: {exc.strerror or type(exc).__name__}",
                )
                self._append_log_locked("pipeline", self._pipeline["error"])
            raise MappingJobError("mapping pipeline could not be started") from exc

        # start_new_session=True makes the child's PID the process-group ID.
        # Deriving it locally also handles a launcher that exits immediately.
        pgid = process.pid
        with self._lock:
            self._pipeline_process = process
            self._pipeline_pgid = pgid
            self._pipeline.update(pid=process.pid)
            self._append_log_locked(
                "pipeline",
                "pipeline readiness launcher started",
            )

        self._start_reader(process, "pipeline")
        threading.Thread(
            target=self._monitor_pipeline,
            args=(token, process, pgid),
            name="robot-scope-mapping-monitor",
            daemon=True,
        ).start()
        return self.snapshot()

    def stop_mapping(self) -> dict[str, Any]:
        """Gracefully stop the complete manager-owned mapping process group."""

        _, snapshot = self._stop_mapping(expected_job_id=None)
        return snapshot

    def stop_mapping_if_job_id(self, job_id: str) -> tuple[bool, dict[str, Any]]:
        """Stop only the exact still-active mapping job named by ``job_id``.

        Navigation uses this compare-and-stop operation for a localization
        pipeline that it started itself.  Checking the token and publishing
        ``stopping`` happen under the manager lock, so a stale navigation
        cleanup can never stop a replacement or operator-started pipeline.
        """

        if not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise MappingJobError("mapping cleanup job_id is invalid")
        return self._stop_mapping(expected_job_id=job_id)

    def _stop_mapping(
        self,
        *,
        expected_job_id: Optional[str],
    ) -> tuple[bool, dict[str, Any]]:
        """Implement unconditional and token-fenced mapping cleanup."""

        with self._lock:
            if (
                expected_job_id is not None
                and self._pipeline.get("job_id") != expected_job_id
            ):
                return False, self.snapshot()
            if self._save_active:
                raise JobBusyError("map save must finish before mapping can stop")
            if self._pipeline["state"] not in {"starting", "running", "stopping"}:
                return False, self.snapshot()
            token = self._pipeline_token
            process = self._pipeline_process
            pgid = self._pipeline_pgid
            self._stop_requested = True
            self._pipeline["state"] = "stopping"
            self._append_log_locked("pipeline", "stopping mapping process group")

        if pgid is not None:
            self._terminate_group(process, pgid)

        exit_code = process.poll() if process is not None else None
        with self._lock:
            # No public start can replace a ``stopping`` job, but retain a
            # second token fence so future manager changes cannot let stale
            # cleanup publish terminal state for another process group.
            if self._pipeline_token != token:
                return False, self.snapshot()
            self._pipeline.update(
                state="stopped",
                stopped_at=_utc_now(),
                exit_code=exit_code,
                error=None,
            )
            self._pipeline_process = None
            self._pipeline_pgid = None
            self._append_log_locked("pipeline", "mapping pipeline stopped")
        return True, self.snapshot()

    def save_map(self, name: str, kind: str) -> dict[str, Any]:
        """Run one allowlisted save recipe and publish only verified artifacts."""

        safe_name = self.validate_map_name(name)
        spec = self.save_commands.get(kind) if isinstance(kind, str) else None
        if spec is None:
            raise MappingJobError(f"map kind is not allowlisted: {kind}")

        with self._lock:
            if self._closing:
                raise MappingJobError("mapping manager is shutting down")
            if self._save_active:
                raise JobBusyError("another map save is already in progress")
            if self._pipeline["state"] == "stopping":
                raise JobBusyError("mapping pipeline is stopping")
            if self.require_pipeline_for_save and self._pipeline["state"] != "running":
                raise PipelineNotRunning("mapping pipeline must be running before saving")
            self._ensure_targets_available(safe_name, spec.expected_suffixes)
            token = uuid.uuid4().hex
            self._save_active = True
            self._operation = {
                "state": "saving",
                "job_id": token,
                "kind": kind,
                "map_name": safe_name,
                "started_at": _utc_now(),
                "finished_at": None,
                "exit_code": None,
                "files": [],
                "details": {},
                "error": None,
            }
            self._append_log_locked("save", f"saving {kind} map as {safe_name}")

        jobs_dir = self.output_dir / ".robot_scope_jobs"
        staging_dir = jobs_dir / token
        prefix = staging_dir / safe_name
        argv = tuple(value.replace(OUTPUT_PREFIX_TOKEN, str(prefix)) for value in spec.argv)
        process: Optional[subprocess.Popen[str]] = None
        pgid: Optional[int] = None
        try:
            with self._lock:
                if self._closing:
                    raise SaveResultError("map save cancelled during shutdown")
            jobs_dir.mkdir(mode=0o700, exist_ok=True)
            if jobs_dir.is_symlink() or jobs_dir.resolve(strict=True).parent != self.output_dir:
                raise SaveResultError("map staging directory is unsafe")
            staging_dir.mkdir(mode=0o700, exist_ok=False)
            process = self._spawn(argv, spec.cwd)
            pgid = process.pid
            with self._lock:
                self._save_process = process
                self._save_pgid = pgid
            reader = self._start_reader(process, "save")
            try:
                exit_code = process.wait(timeout=spec.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                self._terminate_group(process, pgid)
                raise SaveResultError("map save timed out") from exc
            reader.join(timeout=1.0)
            if exit_code != 0:
                raise SaveResultError(f"map save command exited with status {exit_code}")
            if self._group_alive(pgid):
                self._terminate_group(process, pgid)
                raise SaveResultError("map save command left child processes running")

            sources = self._validate_outputs(prefix, spec)
            published = self._publish_outputs(safe_name, spec.expected_suffixes, sources)
            with self._lock:
                self._operation.update(
                    state="succeeded",
                    finished_at=_utc_now(),
                    exit_code=exit_code,
                    files=[path.name for path in published],
                    details={},
                    error=None,
                )
                self._append_log_locked(
                    "save",
                    f"saved {', '.join(path.name for path in published)}",
                )
            return self.snapshot()
        except (OSError, SaveResultError) as exc:
            if pgid is not None and self._group_alive(pgid):
                self._terminate_group(process, pgid)
            message = str(exc) if isinstance(exc, SaveResultError) else "map save process failed"
            with self._lock:
                self._operation.update(
                    state="failed",
                    finished_at=_utc_now(),
                    exit_code=process.poll() if process is not None else None,
                    files=[],
                    details={},
                    error=message,
                )
                self._append_log_locked("save", message)
            if isinstance(exc, SaveResultError):
                raise
            raise MappingJobError(message) from exc
        finally:
            with self._lock:
                self._save_active = False
                self._save_process = None
                self._save_pgid = None
            shutil.rmtree(staging_dir, ignore_errors=True)
            try:
                jobs_dir.rmdir()
            except OSError:
                pass

    def run_local_operation(
        self,
        kind: str,
        map_name: str,
        worker: Callable[[], Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Reserve and run one bounded shell-free operation synchronously."""

        reservation = self.reserve_local_operation(kind, map_name)
        job_id = str(reservation["operation"]["job_id"])
        return self.run_reserved_local_operation(job_id, worker)

    def reserve_local_operation(self, kind: str, map_name: str) -> dict[str, Any]:
        """Atomically reserve the shared job lease before an HTTP 202 response.

        The returned snapshot already contains the stable job ID.  A caller
        must pass that exact ID to :meth:`run_reserved_local_operation`; wrong,
        concurrent, or replayed IDs cannot execute or mutate the reservation.
        """

        safe_name = self.validate_map_name(map_name)
        if not isinstance(kind, str) or not KIND_RE.fullmatch(kind):
            raise MappingJobError("local map operation kind is invalid")

        with self._lock:
            if self._closing:
                raise MappingJobError("mapping manager is shutting down")
            if self._save_active:
                raise JobBusyError("another map operation is already in progress")
            if self._pipeline["state"] == "stopping":
                raise JobBusyError("mapping pipeline is stopping")
            token = uuid.uuid4().hex
            self._save_active = True
            self._local_operation_token = token
            self._local_operation_started = False
            self._operation = {
                "state": "saving",
                "job_id": token,
                "kind": kind,
                "map_name": safe_name,
                "started_at": _utc_now(),
                "finished_at": None,
                "exit_code": None,
                "files": [],
                "details": {},
                "error": None,
            }
            self._append_log_locked("save", f"running {kind} as {safe_name}")
            return self.snapshot()

    def run_reserved_local_operation(
        self,
        job_id: str,
        worker: Callable[[], Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Execute the callable belonging to one exact local reservation.

        The callable owns its filesystem transaction.  Only JSON-safe details
        and portable output filenames are copied into the public operation
        snapshot; paths and caller-supplied commands are never accepted.
        """

        with self._lock:
            if (
                not isinstance(job_id, str)
                or not re.fullmatch(r"[0-9a-f]{32}", job_id)
                or self._local_operation_token != job_id
                or not self._save_active
                or self._operation.get("job_id") != job_id
                or self._operation.get("state") != "saving"
            ):
                raise MappingJobError("local map operation reservation is invalid or expired")
            if self._local_operation_started:
                raise JobBusyError("local map operation is already running")
            self._local_operation_started = True

        try:
            if not callable(worker):
                raise MappingJobError("local map operation worker is invalid")
            result = worker()
            if not isinstance(result, Mapping):
                raise SaveResultError("local map operation returned an invalid result")
            raw_files = result.get("files", [])
            raw_details = result.get("details", {})
            if not isinstance(raw_files, (list, tuple)) or not all(
                isinstance(value, str)
                and value
                and len(value) <= 128
                and not value.startswith(".")
                and Path(value).name == value
                for value in raw_files
            ):
                raise SaveResultError("local map operation returned unsafe filenames")
            if not isinstance(raw_details, Mapping):
                raise SaveResultError("local map operation returned invalid details")
            try:
                serialized = json.dumps(
                    dict(raw_details),
                    allow_nan=False,
                    separators=(",", ":"),
                )
            except (TypeError, ValueError) as exc:
                raise SaveResultError("local map operation details are not JSON-safe") from exc
            if len(serialized.encode("utf-8")) > 64 * 1024:
                raise SaveResultError("local map operation details exceed the configured limit")
            details = json.loads(serialized)
            files = list(raw_files)
            with self._lock:
                self._operation.update(
                    state="succeeded",
                    finished_at=_utc_now(),
                    exit_code=0,
                    files=files,
                    details=details,
                    error=None,
                )
                self._append_log_locked("save", f"created {', '.join(files)}")
            return self.snapshot()
        except Exception as exc:
            message = public_diagnostic(exc) or "local map operation failed"
            with self._lock:
                self._operation.update(
                    state="failed",
                    finished_at=_utc_now(),
                    exit_code=None,
                    files=[],
                    details={},
                    error=message,
                )
                self._append_log_locked("save", message)
            raise
        finally:
            with self._lock:
                if self._local_operation_token == job_id:
                    self._save_active = False
                    self._local_operation_token = None
                    self._local_operation_started = False

    def fail_reserved_local_operation(self, job_id: str, message: str) -> dict[str, Any]:
        """Fail and release a reservation whose worker could not be scheduled."""

        clean = public_diagnostic(message) or "local map operation could not be scheduled"
        with self._lock:
            if (
                self._local_operation_token != job_id
                or not self._save_active
                or self._local_operation_started
                or self._operation.get("job_id") != job_id
                or self._operation.get("state") != "saving"
            ):
                raise MappingJobError("local map operation reservation is invalid or expired")
            self._operation.update(
                state="failed",
                finished_at=_utc_now(),
                exit_code=None,
                files=[],
                details={},
                error=clean,
            )
            self._append_log_locked("save", clean)
            self._save_active = False
            self._local_operation_token = None
            self._local_operation_started = False
            return self.snapshot()

    def local_operation_cancelled(self, job_id: str) -> bool:
        """Return true when a reserved worker must not publish new artifacts."""

        with self._lock:
            return self._local_operation_cancelled_locked(job_id)

    @contextmanager
    def local_publication_guard(self, job_id: str) -> Iterator[bool]:
        """Serialize final artifact publication against manager shutdown."""

        with self._lock:
            yield not self._local_operation_cancelled_locked(job_id)

    def _local_operation_cancelled_locked(self, job_id: str) -> bool:
        return bool(
            self._closing
            or self._local_operation_token != job_id
            or not self._save_active
            or not self._local_operation_started
            or self._operation.get("job_id") != job_id
            or self._operation.get("state") != "saving"
        )

    @staticmethod
    def validate_map_name(name: str) -> str:
        if not isinstance(name, str) or not MAP_NAME_RE.fullmatch(name):
            raise InvalidMapName(
                "map name must be 1-64 ASCII letters, numbers, underscores or hyphens"
            )
        return name

    def close(self) -> None:
        """Best-effort lifecycle cleanup for an application shutdown hook."""

        with self._lock:
            self._closing = True
            if self._local_operation_token and not self._local_operation_started:
                self._operation.update(
                    state="failed",
                    finished_at=_utc_now(),
                    exit_code=None,
                    files=[],
                    details={},
                    error="local map operation cancelled during shutdown",
                )
                self._append_log_locked("save", self._operation["error"])
                self._save_active = False
                self._local_operation_token = None
        deadline = time.monotonic() + self.stop_grace_seconds * 2 + 1.0
        while time.monotonic() < deadline:
            with self._lock:
                save_active = self._save_active
                save_process = self._save_process
                save_pgid = self._save_pgid
            if not save_active:
                break
            if save_pgid is not None:
                self._terminate_group(save_process, save_pgid)
            time.sleep(0.02)
        try:
            self.stop_mapping()
        except JobBusyError:
            # A concurrent save thread owns final state publication; its process
            # group has already been stopped above.  Application shutdown must
            # remain best effort and must not leak the mapping pipeline.
            with self._lock:
                process = self._pipeline_process
                pgid = self._pipeline_pgid
            if pgid is not None:
                self._terminate_group(process, pgid)
        try:
            self.stop_preview()
        except JobBusyError:
            # A concurrent pipeline monitor can take a short interval to
            # publish its terminal state.  The complete process groups are
            # still explicitly drained during application shutdown.
            with self._lock:
                preview_process = self._preview_process
                preview_pgid = self._preview_pgid
            if preview_pgid is not None:
                self._terminate_group(preview_process, preview_pgid)

    @staticmethod
    def _spawn(argv: Sequence[str], cwd: Optional[Path]) -> subprocess.Popen[str]:
        return subprocess.Popen(
            list(argv),
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,
            start_new_session=True,
            close_fds=True,
        )

    def _start_reader(self, process: subprocess.Popen[str], source: str) -> threading.Thread:
        def read_output() -> None:
            if process.stdout is None:
                return
            try:
                for line in process.stdout:
                    self._append_log(source, line)
            finally:
                process.stdout.close()

        thread = threading.Thread(
            target=read_output,
            name=f"robot-scope-{source}-log",
            daemon=True,
        )
        thread.start()
        return thread

    def _monitor_pipeline(
        self,
        token: str,
        process: subprocess.Popen[str],
        pgid: int,
    ) -> None:
        exit_code = process.wait()

        with self._lock:
            if token != self._pipeline_token or self._pipeline["state"] == "stopped":
                return
            if self._stop_requested or self._pipeline["state"] == "stopping":
                return

        if exit_code != 0:
            # A failed launcher may have spawned children before a readiness
            # gate rejected the pipeline.  Stop the complete manager-owned
            # process group before publishing the terminal failed state.
            if self._group_alive(pgid):
                self._terminate_group(process, pgid)
            with self._lock:
                if token != self._pipeline_token or self._pipeline["state"] == "stopped":
                    return
                if self._stop_requested or self._pipeline["state"] == "stopping":
                    return
                self._pipeline_process = None
                self._pipeline_pgid = None
                self._pipeline.update(
                    state="failed",
                    stopped_at=_utc_now(),
                    exit_code=exit_code,
                    error=self.failure_exit_reasons.get(
                        exit_code,
                        f"mapping readiness launcher exited with status {exit_code}",
                    ),
                )
                self._append_log_locked("pipeline", self._pipeline["error"])
            return

        if not self._group_alive(pgid):
            with self._lock:
                if token != self._pipeline_token or self._pipeline["state"] == "stopped":
                    return
                if self._stop_requested or self._pipeline["state"] == "stopping":
                    return
                self._pipeline_process = None
                self._pipeline_pgid = None
                self._pipeline.update(
                    state="failed",
                    stopped_at=_utc_now(),
                    exit_code=exit_code,
                    error="mapping readiness passed but no pipeline processes survived",
                )
                self._append_log_locked("pipeline", self._pipeline["error"])
            return

        with self._lock:
            if token != self._pipeline_token or self._pipeline["state"] == "stopped":
                return
            if self._stop_requested or self._pipeline["state"] == "stopping":
                return
            self._pipeline.update(state="running", exit_code=None, error=None)
            self._append_log_locked("pipeline", "mapping pipeline readiness verified")

        while self._group_alive(pgid):
            with self._lock:
                if token != self._pipeline_token or self._pipeline["state"] == "stopped":
                    return
            time.sleep(0.1)

        with self._lock:
            if token != self._pipeline_token or self._pipeline["state"] == "stopped":
                return
            stopped = self._stop_requested
            self._pipeline_process = None
            self._pipeline_pgid = None
            self._pipeline.update(
                state="stopped" if stopped else "failed",
                stopped_at=_utc_now(),
                exit_code=exit_code,
                error=None if stopped else "mapping pipeline exited unexpectedly",
            )
            self._append_log_locked(
                "pipeline",
                "mapping pipeline stopped" if stopped else "mapping pipeline exited unexpectedly",
            )

    def _monitor_preview(
        self,
        token: str,
        process: subprocess.Popen[str],
        pgid: int,
    ) -> None:
        exit_code = process.wait()
        if self._group_alive(pgid):
            self._terminate_group(process, pgid)

        with self._lock:
            if token != self._preview_token or self._preview["state"] == "stopped":
                return
            if self._preview_stop_requested or self._preview["state"] == "stopping":
                return
            self._preview_process = None
            self._preview_pgid = None
            self._preview.update(
                state="failed",
                stopped_at=_utc_now(),
                exit_code=exit_code,
                error=f"XT16 preview exited unexpectedly with status {exit_code}",
            )
            self._append_log_locked("preview", self._preview["error"])
            pipeline_pgid = (
                self._pipeline_pgid
                if self._pipeline["state"] in {"starting", "running"}
                else None
            )
            pipeline_process = self._pipeline_process

        # FAST-LIO must not keep presenting a running mapping session after
        # both of its fixed point-cloud producers disappear.
        if pipeline_pgid is not None:
            self._terminate_group(pipeline_process, pipeline_pgid)

    def _append_log(self, source: str, message: str) -> None:
        runtime_ready = bool(
            source == "pipeline"
            and self.readiness_runtime_marker is not None
            and str(message).strip() == self.readiness_runtime_marker
        )
        clean = public_diagnostic(message, runtime=True)
        if not clean:
            return
        with self._lock:
            self._append_log_locked(source, clean)
            if runtime_ready and self._pipeline["state"] == "starting":
                self._pipeline.update(state="running", exit_code=None, error=None)
                self._append_log_locked(
                    "pipeline",
                    "mapping pipeline readiness verified",
                )

    def _append_log_locked(self, source: str, message: str) -> None:
        clean = "".join(char for char in str(message).strip() if char == "\t" or ord(char) >= 32)
        if not clean:
            return
        self._seq += 1
        self._logs.append(
            {
                "seq": self._seq,
                "at": _utc_now(),
                "source": source,
                "message": clean[:1_000],
            }
        )

    def _ensure_targets_available(self, name: str, suffixes: Iterable[str]) -> None:
        for suffix in suffixes:
            target = (self.output_dir / f"{name}{suffix}").resolve()
            if not _inside(self.output_dir, target):
                raise SaveResultError("map output escaped the configured directory")
            if target.exists() or target.is_symlink():
                raise SaveResultError(f"map already exists: {target.name}")

    def _validate_outputs(self, prefix: Path, spec: SaveCommandSpec) -> list[Path]:
        results: list[Path] = []
        staging_root = prefix.parent.resolve(strict=True)
        for suffix in spec.expected_suffixes:
            candidate = prefix.with_name(prefix.name + suffix)
            if candidate.is_symlink():
                raise SaveResultError(f"save result cannot be a symlink: {candidate.name}")
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise SaveResultError(f"save result is missing: {candidate.name}") from exc
            if not _inside(staging_root, resolved) or not resolved.is_file():
                raise SaveResultError(f"save result is not a regular staged file: {candidate.name}")
            if resolved.stat().st_size < spec.min_result_bytes:
                raise SaveResultError(f"save result is empty: {candidate.name}")
            if resolved.stat().st_size > spec.max_result_bytes:
                raise SaveResultError(f"save result exceeds the configured limit: {candidate.name}")
            self._validate_file_format(resolved, prefix.name, spec.expected_suffixes)
            results.append(resolved)
        return results

    @staticmethod
    def _validate_file_format(path: Path, prefix_name: str, suffixes: Sequence[str]) -> None:
        suffix = path.suffix.lower()
        if suffix == ".pcd":
            with path.open("rb") as stream:
                raw_header = stream.read(16_384)
            header = raw_header.split(b"DATA", 1)[0].decode("ascii", "replace")
            fields = next(
                (line for line in header.splitlines() if line.upper().startswith("FIELDS ")),
                "",
            )
            points = next(
                (line for line in header.splitlines() if line.upper().startswith("POINTS ")),
                "",
            )
            if not {"x", "y", "z"}.issubset(set(fields.lower().split()[1:])):
                raise SaveResultError("PCD result is missing x/y/z fields")
            try:
                point_count = int(points.split()[1])
            except (IndexError, ValueError) as exc:
                raise SaveResultError("PCD result has an invalid point count") from exc
            if point_count < 1 or b"DATA " not in raw_header.upper():
                raise SaveResultError("PCD result has no point data")
        elif suffix in {".yaml", ".yml"}:
            with path.open("r", encoding="utf-8") as stream:
                text = stream.read(65_536)
            image_line = next(
                (line for line in text.splitlines() if line.strip().lower().startswith("image:")),
                "",
            )
            image = image_line.split(":", 1)[1].strip().strip("'\"") if image_line else ""
            expected_images = {
                f"{prefix_name}{value}"
                for value in suffixes
                if value in {".pgm", ".png"}
            }
            if (
                not image
                or Path(image).name != image
                or (expected_images and image not in expected_images)
            ):
                raise SaveResultError("map YAML does not reference its expected local image")
        elif suffix == ".pgm":
            with path.open("rb") as stream:
                magic = stream.read(2)
            if magic not in {b"P2", b"P5"}:
                raise SaveResultError("occupancy image is not a PGM file")
        elif suffix == ".json":
            try:
                with path.open("r", encoding="utf-8") as stream:
                    payload = json.load(stream)
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise SaveResultError("saved map JSON is invalid") from exc
            points = payload.get("points") if isinstance(payload, dict) else None
            if not isinstance(points, list) or len(points) < 3 or len(points) % 3:
                raise SaveResultError("saved map JSON has no points array")

    def _publish_outputs(
        self,
        name: str,
        suffixes: Sequence[str],
        sources: Sequence[Path],
    ) -> list[Path]:
        self._ensure_targets_available(name, suffixes)
        targets = [self.output_dir / f"{name}{suffix}" for suffix in suffixes]
        published: list[Path] = []
        try:
            for source, target in zip(sources, targets):
                os.link(source, target, follow_symlinks=False)
                published.append(target)
        except OSError as exc:
            for target in published:
                try:
                    target.unlink()
                except OSError:
                    pass
            raise SaveResultError("verified map files could not be published") from exc
        for source in sources:
            source.unlink()
        return published

    def _terminate_group(
        self,
        process: Optional[subprocess.Popen[str]],
        pgid: int,
    ) -> None:
        grace = self.stop_grace_seconds
        for sig, wait_seconds in (
            (signal.SIGINT, grace),
            (signal.SIGTERM, grace / 2),
            (signal.SIGKILL, grace / 4),
        ):
            if not self._group_alive(pgid):
                break
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                break
            deadline = time.monotonic() + max(0.05, wait_seconds)
            while time.monotonic() < deadline:
                if not self._group_alive(pgid):
                    break
                if process is not None:
                    process.poll()
                time.sleep(0.05)
        if process is not None:
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass

    @staticmethod
    def _group_alive(pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
