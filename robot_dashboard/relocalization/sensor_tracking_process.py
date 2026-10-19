"""Bounded persistent process for historical seeded LiDAR-to-map observations.

This layer carries full float64 XYZ populations to the reviewed v0.3.1 source.
It does not validate source clocks, robot extrinsics, body pose or tracking.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import selectors
import signal
import socket
import struct
import subprocess
import tempfile
import threading
import time
from typing import Any, cast

import numpy as np

from .external_global_observation import (
    ExternalGlobalObservationError, ExternalGlobalObservationRunner, MAX_RESULT_BYTES,
    _strict_json,
)
from .residual_policy import PROVISIONAL_RESIDUAL_POLICY, evaluate_residual
from .v031_observation_compat import SELECTION_POLICY, supports_pin


START_DEADLINE_S = 30.0
# Existing local observation_alignment compute deadline is 0.6 s. Do not widen.
ALIGN_DEADLINE_S = 0.6
_WORKER = Path(__file__).with_name("sensor_tracking_worker.py")


class SensorTrackingError(RuntimeError):
    pass


def _context_value(context: dict[str, Any], name: str) -> str:
    value = context.get(name)
    if not isinstance(value, str) or not value:
        raise SensorTrackingError("SENSOR_CONTEXT_INVALID")
    return value


def _cancelled(cancel_event: threading.Event | None) -> bool:
    return cancel_event is not None and cancel_event.is_set()


def _rigid_seed(value: Any) -> list[list[float]]:
    try:
        matrix = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise SensorTrackingError("SENSOR_SEED_INVALID") from exc
    if (matrix.shape != (4, 4) or not np.isfinite(matrix).all()
            or not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-8)
            or not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-6)
            or not math.isclose(float(np.linalg.det(matrix[:3, :3])), 1., abs_tol=1e-6)):
        raise SensorTrackingError("SENSOR_SEED_NOT_RIGID")
    return cast(list[list[float]], matrix.tolist())


def _private_file(folder: Path, name: str, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(folder / name, flags, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(data)


def _stop_group(process: subprocess.Popen[bytes] | None) -> bool:
    if process is None:
        return True
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=.2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=.2)
    except subprocess.TimeoutExpired:
        return False
    return process.poll() is not None


class SensorTrackingProcess:
    """One map and one observer stream per process; close after loss or change.

    `start` may spend up to 30 s loading Open3D and the map once. Each `align`
    call has a 0.6 s end-to-end cap. A timeout/cancel kills the entire owned
    process group, so no late result can be accepted on a later scan.
    """

    def __init__(self, external_runner: ExternalGlobalObservationRunner):
        if not isinstance(external_runner, ExternalGlobalObservationRunner):
            raise TypeError("an existing external observation runner is required")
        self._runner = external_runner
        self._call_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._channel: socket.socket | None = None
        self._folder: tempfile.TemporaryDirectory[str] | None = None
        self._pending_folders: list[tempfile.TemporaryDirectory[str]] = []
        self._closed = False
        self._started = False
        self._map_context: dict[str, Any] | None = None
        self._pin_sha: str | None = None
        self._stream: tuple[str, str] | None = None
        self._last_stamp = 0
        self._sequence = 0

    def _check(self, deadline: float, cancel_event: threading.Event | None) -> None:
        if _cancelled(cancel_event):
            raise SensorTrackingError("SENSOR_CANCELLED")
        with self._state_lock:
            if self._closed:
                raise SensorTrackingError("SENSOR_PROCESS_CLOSED")
            process = self._process
        if time.monotonic() >= deadline:
            raise SensorTrackingError("SENSOR_DEADLINE_EXCEEDED")
        if process is not None and process.poll() is not None:
            raise SensorTrackingError("SENSOR_WORKER_EXITED")

    def _exchange(self, request: dict[str, Any], deadline: float,
                  cancel_event: threading.Event | None) -> dict[str, Any]:
        with self._state_lock:
            channel = self._channel
        if channel is None:
            raise SensorTrackingError("SENSOR_WORKER_UNAVAILABLE")
        encoded = json.dumps(request, allow_nan=False, separators=(",", ":")).encode()
        if not 0 < len(encoded) <= MAX_RESULT_BYTES:
            raise SensorTrackingError("SENSOR_COMMAND_LIMIT")
        outgoing = memoryview(struct.pack("!I", len(encoded)) + encoded)
        received = bytearray()
        needed = 4
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(channel, selectors.EVENT_READ | selectors.EVENT_WRITE)
                while outgoing or len(received) < needed:
                    self._check(deadline, cancel_event)
                    timeout = min(.01, max(0., deadline - time.monotonic()))
                    for _, event in selector.select(timeout):
                        if event & selectors.EVENT_WRITE and outgoing:
                            sent = os.write(channel.fileno(), outgoing)
                            outgoing = outgoing[sent:]
                            if not outgoing:
                                selector.modify(channel, selectors.EVENT_READ)
                        if event & selectors.EVENT_READ and len(received) < needed:
                            chunk = os.read(channel.fileno(), needed - len(received))
                            if not chunk:
                                raise SensorTrackingError("SENSOR_WORKER_CLOSED_CHANNEL")
                            received.extend(chunk)
                            if needed == 4 and len(received) == 4:
                                size = struct.unpack("!I", received)[0]
                                if not 0 < size <= MAX_RESULT_BYTES:
                                    raise SensorTrackingError("SENSOR_RESULT_LIMIT_NO_TRUNCATION")
                                needed = 4 + size
                self._check(deadline, cancel_event)
        except (OSError, ValueError) as exc:
            raise SensorTrackingError("SENSOR_WORKER_CHANNEL_FAILED") from exc
        value = _strict_json(bytes(received[4:]))
        if not isinstance(value, dict):
            raise SensorTrackingError("SENSOR_RESULT_INVALID")
        if value.get("error"):
            reason = str(value["error"])
            kind = value.get("error_type")
            if kind in {"ValueError", "RuntimeError", "TypeError", "KeyError"}:
                reason += ":" + kind
            raise SensorTrackingError(reason)
        return cast(dict[str, Any], value)

    def _drain_folders(self) -> None:
        with self._state_lock:
            folders, self._pending_folders = self._pending_folders, []
        for folder in folders:
            folder.cleanup()

    def start(self, map_bytes: bytes, context: dict[str, Any],
              cancel_event: threading.Event | None) -> None:
        deadline = time.monotonic() + START_DEADLINE_S
        if not self._call_lock.acquire(blocking=False):
            raise SensorTrackingError("SENSOR_PROCESS_BUSY")
        try:
            with self._state_lock:
                if self._closed or self._started or self._process is not None:
                    raise SensorTrackingError("SENSOR_PROCESS_ALREADY_USED")
            self._check(deadline, cancel_event)
            python, source, pin, pin_sha = self._runner._configuration()
            if not supports_pin(pin["files"]):
                raise SensorTrackingError("SENSOR_REVIEWED_SOURCE_REQUIRED")
            if not isinstance(context, dict) or not isinstance(context.get("map"), dict):
                raise SensorTrackingError("SENSOR_CONTEXT_INVALID")
            map_context: dict[str, Any] = {key: _context_value(context, key) for key in
                                           ("map_id", "map_revision", "map_frame", "source_frame")}
            if map_context["map_frame"] == map_context["source_frame"]:
                raise SensorTrackingError("SENSOR_FRAMES_NOT_DISTINCT")
            self._runner._array(map_bytes, context["map"])
            map_context["map"] = {key: context["map"][key] for key in
                                  ("encoding", "point_count", "sha256")}
            folder = tempfile.TemporaryDirectory(prefix="robot-scope-sensor-track-")
            with self._state_lock:
                if self._closed:
                    folder.cleanup()
                    raise SensorTrackingError("SENSOR_PROCESS_CLOSED")
                self._folder = folder
            work = Path(folder.name)
            work.chmod(0o700)
            _private_file(work, "map.f64", map_bytes)
            configuration = {"context": map_context, "source_root": str(source),
                             "pin": pin, "pin_sha256": pin_sha,
                             "allow_ambiguous": self._runner.allow_ambiguous}
            _private_file(work, "config.json", json.dumps(configuration, allow_nan=False).encode())
            parent, child = socket.socketpair()
            try:
                parent.setblocking(False)
                environment = {key: value for key, value in os.environ.items()
                               if not key.startswith(("PYTHON", "LD_", "DYLD_"))}
                environment.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
                process = subprocess.Popen(
                    [str(python), "-I", str(_WORKER), str(work), str(child.fileno())],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    cwd=work, env=environment, pass_fds=(child.fileno(),),
                    close_fds=True, start_new_session=True,
                )
            except BaseException:
                parent.close()
                raise
            finally:
                child.close()
            with self._state_lock:
                if self._closed:
                    _stop_group(process)
                    parent.close()
                    raise SensorTrackingError("SENSOR_PROCESS_CLOSED")
                self._process, self._channel = process, parent
            ready = self._receive_ready(deadline, cancel_event)
            _, _, _, final_pin_sha = self._runner._configuration()
            if (ready.get("ready") is not True or ready.get("source_pin_sha256") != pin_sha
                    or final_pin_sha != pin_sha or ready.get("map_sha256") != map_context["map"]["sha256"]
                    or ready.get("reference_points") != map_context["map"]["point_count"]):
                raise SensorTrackingError("SENSOR_START_IDENTITY_MISMATCH")
            with self._state_lock:
                self._check_started_unlocked(map_context, pin_sha)
        except BaseException:
            self.close()
            raise
        finally:
            self._call_lock.release()
            self._drain_folders()

    def _check_started_unlocked(self, context: dict[str, Any], pin_sha: str) -> None:
        if self._closed:
            raise SensorTrackingError("SENSOR_PROCESS_CLOSED")
        self._map_context, self._pin_sha, self._started = context, pin_sha, True

    def _receive_ready(self, deadline: float,
                       cancel_event: threading.Event | None) -> dict[str, Any]:
        # The child writes one framed ready message before it accepts commands.
        return self._read_ready(deadline, cancel_event)

    def _read_ready(self, deadline: float,
                    cancel_event: threading.Event | None) -> dict[str, Any]:
        with self._state_lock:
            channel = self._channel
        if channel is None:
            raise SensorTrackingError("SENSOR_WORKER_UNAVAILABLE")
        received = bytearray()
        needed = 4
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(channel, selectors.EVENT_READ)
                while len(received) < needed:
                    self._check(deadline, cancel_event)
                    for _, _ in selector.select(min(.01, max(0., deadline - time.monotonic()))):
                        chunk = os.read(channel.fileno(), needed - len(received))
                        if not chunk:
                            raise SensorTrackingError("SENSOR_WORKER_CLOSED_CHANNEL")
                        received.extend(chunk)
                        if needed == 4 and len(received) == 4:
                            size = struct.unpack("!I", received)[0]
                            if not 0 < size <= MAX_RESULT_BYTES:
                                raise SensorTrackingError("SENSOR_RESULT_LIMIT_NO_TRUNCATION")
                            needed = 4 + size
                self._check(deadline, cancel_event)
        except (OSError, ValueError) as exc:
            raise SensorTrackingError("SENSOR_WORKER_CHANNEL_FAILED") from exc
        value = _strict_json(bytes(received[4:]))
        if not isinstance(value, dict) or value.get("error"):
            raise SensorTrackingError("SENSOR_WORKER_START_FAILED")
        return cast(dict[str, Any], value)

    def align(self, scan_bytes: bytes, context: dict[str, Any], seed_matrix: Any,
              cancel_event: threading.Event | None) -> dict[str, Any]:
        deadline = time.monotonic() + ALIGN_DEADLINE_S
        if not self._call_lock.acquire(blocking=False):
            raise SensorTrackingError("SENSOR_PROCESS_BUSY")
        try:
            self._check(deadline, cancel_event)
            with self._state_lock:
                stored = self._map_context
                pin_sha = self._pin_sha
                folder = self._folder
                sequence = self._sequence + 1
                stream = self._stream
                last_stamp = self._last_stamp
            if not self._started or stored is None or folder is None or pin_sha is None:
                raise SensorTrackingError("SENSOR_PROCESS_NOT_STARTED")
            if not isinstance(context, dict) or not isinstance(context.get("scan"), dict):
                raise SensorTrackingError("SENSOR_CONTEXT_INVALID")
            for field in ("map_id", "map_revision", "map_frame", "source_frame"):
                if context.get(field) != stored[field]:
                    raise SensorTrackingError("SENSOR_MAP_OR_FRAME_CHANGED")
            if context.get("map") != stored["map"]:
                raise SensorTrackingError("SENSOR_MAP_CHANGED")
            identity = (_context_value(context, "observer_id"),
                        _context_value(context, "observer_epoch"))
            if stream is not None and identity != stream:
                raise SensorTrackingError("SENSOR_SOURCE_EPOCH_CHANGED")
            stamp_text = _context_value(context, "source_stamp_ns")
            if not stamp_text.isdecimal() or int(stamp_text) <= last_stamp:
                raise SensorTrackingError("SENSOR_SOURCE_STAMP_NOT_ADVANCING")
            self._runner._array(scan_bytes, context["scan"])
            scan_metadata = {key: context["scan"][key] for key in
                             ("encoding", "point_count", "sha256")}
            seed = _rigid_seed(seed_matrix)
            _, _, _, current_pin_sha = self._runner._configuration()
            if current_pin_sha != pin_sha:
                raise SensorTrackingError("SENSOR_SOURCE_PIN_CHANGED")
            work = Path(folder.name)
            scan_path = work / f"scan-{sequence:08d}.f64"
            _private_file(work, scan_path.name, scan_bytes)
            payload_context = {**stored, "scan": scan_metadata,
                               "observer_id": identity[0], "observer_epoch": identity[1],
                               "source_stamp_ns": stamp_text}
            reply = self._exchange({"operation": "align", "sequence": sequence,
                                    "context": payload_context, "seed_matrix": seed},
                                   deadline, cancel_event)
            # The child has completed this request; retain only the fixed map.
            # Any failure before this point closes and removes the whole folder.
            scan_path.unlink()
            if reply.get("sequence") != sequence or not isinstance(reply.get("result"), dict):
                raise SensorTrackingError("SENSOR_REPLY_SEQUENCE_MISMATCH")
            result = reply["result"]
            ExternalGlobalObservationRunner._validate_result(
                result, payload_context, allow_ambiguous=self._runner.allow_ambiguous)
            if (result.get("selection_policy") != SELECTION_POLICY
                    or result.get("source_pin_sha256") != pin_sha
                    or result.get("observer_id") != identity[0]
                    or result.get("map_revision") != stored["map_revision"]
                    or result.get("tracking_verified") is not False
                    or result.get("body_pose") is not None
                    or result.get("current_pose") is not None):
                raise SensorTrackingError("SENSOR_RESULT_POLICY_OR_IDENTITY_MISMATCH")
            # Comparison only. It neither selects nor rejects a local branch.
            comparison_policy = evaluate_residual(0., policy=PROVISIONAL_RESIDUAL_POLICY).as_dict()  # type: ignore[arg-type]
            for field in ("rmse_m", "residual_passed", "original_residual_passed"):
                comparison_policy.pop(field)
            comparison_policy.update(schema="robot-scope.residual-comparison-policy.v1",
                                     candidate_index_basis="CANDIDATE_ARRAY_INDEX",
                                     comparison_fields=["residual_passed", "original_residual_passed"])
            comparisons: list[Any] = []
            for candidate in result["candidates"]:
                try:
                    value = evaluate_residual(candidate.get("rmse_m"),
                                              policy=PROVISIONAL_RESIDUAL_POLICY)
                    comparisons.append([value.residual_passed, value.original_residual_passed])
                except ValueError:
                    comparisons.append({"reason": "INVALID_STORED_RMSE"})
            result.update(residual_comparisons=comparisons,
                          residual_comparison_policy=comparison_policy,
                          residual_comparison_scope="STORED_RMSE_ONLY_NO_LOCAL_RESELECTION")
            if len(json.dumps(result, allow_nan=False, separators=(",", ":")).encode()) > MAX_RESULT_BYTES:
                raise SensorTrackingError("SENSOR_ENVELOPED_RESULT_LIMIT_NO_TRUNCATION")
            self._check(deadline, cancel_event)
            with self._state_lock:
                if self._closed:
                    raise SensorTrackingError("SENSOR_PROCESS_CLOSED")
                self._stream, self._last_stamp, self._sequence = identity, int(stamp_text), sequence
            return cast(dict[str, Any], result)
        except (ExternalGlobalObservationError, ValueError, TypeError, KeyError) as exc:
            self.close()
            raise SensorTrackingError("SENSOR_INPUT_OR_RESULT_INVALID") from exc
        except BaseException:
            self.close()
            raise
        finally:
            self._call_lock.release()
            self._drain_folders()

    def close(self) -> bool:
        with self._state_lock:
            self._closed = True
            process, channel, folder = self._process, self._channel, self._folder
            self._process = self._channel = self._folder = None
            self._started = False
            if folder is not None:
                self._pending_folders.append(folder)
        if channel is not None:
            channel.close()
        reaped = _stop_group(process)
        if not self._call_lock.locked():
            self._drain_folders()
        return reaped
