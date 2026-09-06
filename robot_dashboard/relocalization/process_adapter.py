"""Single-job, path-confined process adapter for offline registration."""

from __future__ import annotations

import json
import os
import resource
import signal
import stat
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterable

from .models import (
    MAX_ERROR_BYTES,
    MAX_INPUT_BYTES,
    MAX_OUTPUT_BYTES,
    RegistrationContractError,
    RegistrationRequest,
    RegistrationResultSet,
)


MAX_REFERENCE_BYTES = 256 * 1024 * 1024
MAX_QUERY_BYTES = 64 * 1024 * 1024
MAX_PCD_HEADER_BYTES = 64 * 1024


class RegistrationBusy(RuntimeError):
    """Another offline registration owns the one process slot."""


class RegistrationProcessError(RuntimeError):
    """The bounded child failed or timed out."""


class OfflineRegistrationProcess:
    def __init__(self, executable: Path, allowed_roots: Iterable[Path]) -> None:
        self._executable = self._validate_executable(executable)
        roots = tuple(Path(root).resolve(strict=True) for root in allowed_roots)
        if not roots:
            raise RegistrationContractError("at least one allowed root is required")
        self._roots = roots
        self._lock = threading.Lock()

    def run(self, payload: Any) -> dict[str, Any]:
        try:
            encoded = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
        except (TypeError, ValueError) as exc:
            raise RegistrationContractError("registration request is not JSON-safe") from exc
        if len(encoded) > MAX_INPUT_BYTES:
            raise RegistrationContractError("registration request is oversized")
        request = RegistrationRequest.parse(payload)
        reference = self._validate_pcd(
            Path(request.reference_pcd), MAX_REFERENCE_BYTES, request.max_reference_points
        )
        query = self._validate_pcd(
            Path(request.query_pcd), MAX_QUERY_BYTES, request.max_query_points
        )
        if not self._lock.acquire(blocking=False):
            raise RegistrationBusy("offline registration is already active")
        try:
            return self._run_locked(request, reference, query)
        finally:
            self._lock.release()

    def _run_locked(
        self, request: RegistrationRequest, reference: Path, query: Path
    ) -> dict[str, Any]:
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            process = subprocess.Popen(
                request.argv(str(self._executable), str(reference), str(query)),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                close_fds=True,
                shell=False,
                preexec_fn=_child_limits,
            )
            try:
                process.wait(timeout=request.timeout_ms / 1000.0)
            except subprocess.TimeoutExpired as exc:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2.0)
                raise RegistrationProcessError("offline registration timed out") from exc
            stdout_file.seek(0, os.SEEK_END)
            stdout_size = stdout_file.tell()
            stderr_file.seek(0, os.SEEK_END)
            stderr_size = stderr_file.tell()
            if stdout_size > MAX_OUTPUT_BYTES or stderr_size > MAX_ERROR_BYTES:
                raise RegistrationProcessError("offline registration output exceeded its bound")
            stdout_file.seek(0)
            stderr_file.seek(0)
            raw_output = stdout_file.read(MAX_OUTPUT_BYTES + 1)
            error = stderr_file.read(MAX_ERROR_BYTES).decode("utf-8", "replace")
            if process.returncode != 0:
                detail = error.strip()[:512] or "offline registration failed"
                raise RegistrationProcessError(detail)
            try:
                decoded = json.loads(raw_output)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RegistrationProcessError("offline registration returned invalid JSON") from exc
            return RegistrationResultSet.parse(decoded).payload

    def _validate_pcd(self, path: Path, maximum_bytes: int, maximum_points: int) -> Path:
        if not path.is_absolute() or path.is_symlink():
            raise RegistrationContractError("PCD path must be an absolute regular file")
        resolved = path.resolve(strict=True)
        if not any(resolved.is_relative_to(root) for root in self._roots):
            raise RegistrationContractError("PCD path is outside the allowed staging roots")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(resolved, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0 or metadata.st_size > maximum_bytes:
                raise RegistrationContractError("PCD file size or type is invalid")
            header = os.read(descriptor, min(metadata.st_size, MAX_PCD_HEADER_BYTES + 1))
        finally:
            os.close(descriptor)
        marker = header.find(b"DATA binary\n")
        if marker < 0 or marker > MAX_PCD_HEADER_BYTES:
            raise RegistrationContractError("PCD must use bounded binary encoding")
        text = header[: marker + len(b"DATA binary\n")].decode("ascii", "strict")
        values = _pcd_header(text)
        if values["FIELDS"][:3] != ["x", "y", "z"]:
            raise RegistrationContractError("PCD must begin with x/y/z fields")
        field_count = len(values["FIELDS"])
        if (
            len(values["SIZE"]) != field_count
            or len(values["TYPE"]) != field_count
            or len(values["COUNT"]) != field_count
            or any(value != "1" for value in values["COUNT"])
        ):
            raise RegistrationContractError("PCD field layout is invalid")
        if values["SIZE"][:3] != ["4", "4", "4"] or values["TYPE"][:3] != ["F", "F", "F"]:
            raise RegistrationContractError("PCD XYZ fields must be float32")
        points = int(values["POINTS"][0])
        if points <= 0 or points > maximum_points:
            raise RegistrationContractError("PCD point count is outside the request limit")
        return resolved

    @staticmethod
    def _validate_executable(path: Path) -> Path:
        if not path.is_absolute() or path.is_symlink():
            raise RegistrationContractError("registration executable must be absolute")
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
        if not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
            raise RegistrationContractError("registration executable is not executable")
        return resolved


def _pcd_header(text: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if not parts:
            continue
        if parts[0] in values:
            raise RegistrationContractError("PCD header contains duplicate fields")
        values[parts[0]] = parts[1:]
    required = {"FIELDS", "SIZE", "TYPE", "COUNT", "WIDTH", "HEIGHT", "POINTS", "DATA"}
    if not required.issubset(values) or values["DATA"] != ["binary"]:
        raise RegistrationContractError("PCD header is incomplete")
    try:
        if int(values["WIDTH"][0]) * int(values["HEIGHT"][0]) != int(values["POINTS"][0]):
            raise RegistrationContractError("PCD dimensions do not match POINTS")
    except (ValueError, IndexError) as exc:
        raise RegistrationContractError("PCD dimensions are invalid") from exc
    return values


def _child_limits() -> None:
    os.setsid()
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT_BYTES, MAX_OUTPUT_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
