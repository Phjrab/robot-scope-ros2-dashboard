"""Bounded execution of an explicitly configured, pinned offline SE3 backend.

The HTTP client cannot choose a path, interpreter, module, command or deadline.
No backend is installed or enabled automatically. Results remain historical
sensor observations; this module neither publishes ROS nor changes live gates.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import threading
import time
from typing import Any

import numpy as np

from .residual_policy import PROVISIONAL_RESIDUAL_POLICY, evaluate_residual

MAX_RESULT_BYTES = 65_536
MAX_ARRAY_BYTES = 32 * 1024 * 1024
MAX_LOG_BYTES = 65_536
BACKEND_ID = "pinned-open3d-unrestricted-se3-v031"
_WORKER = Path(__file__).with_name("global_observation_worker.py")


class ExternalGlobalObservationError(RuntimeError):
    pass


def _strict_json(raw: bytes) -> Any:
    def invalid(value: str) -> None:
        raise ValueError("nonfinite JSON: " + value)
    return json.loads(raw, parse_constant=invalid)


class ExternalGlobalObservationRunner:
    def __init__(self, python: str | None = None, source_root: str | None = None,
                 pin_file: str | None = None, *, timeout_s: float = 120.) -> None:
        if isinstance(timeout_s, bool) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 120:
            raise ValueError("deadline must be positive and at most 120 seconds")
        self.python = python
        self.source_root = source_root
        self.pin_file = pin_file
        self.timeout_s = timeout_s

    @classmethod
    def from_environment(cls) -> ExternalGlobalObservationRunner:
        return cls(os.environ.get("ROBOT_SCOPE_GLOBAL_OBSERVATION_PYTHON"),
                   os.environ.get("ROBOT_SCOPE_GLOBAL_OBSERVATION_SOURCE"),
                   os.environ.get("ROBOT_SCOPE_GLOBAL_OBSERVATION_PIN"))

    def _configuration(self) -> tuple[Path, Path, dict[str, Any], str]:
        if not all((self.python, self.source_root, self.pin_file)):
            raise ExternalGlobalObservationError("GLOBAL_BACKEND_NOT_CONFIGURED")
        python, root, pin_path = (Path(v) for v in (self.python, self.source_root, self.pin_file))
        if not (python.is_absolute() and python.is_file() and os.access(python, os.X_OK)):
            raise ExternalGlobalObservationError("GLOBAL_PYTHON_UNAVAILABLE")
        if not (root.is_absolute() and root.resolve() == root and root.is_dir()
                and pin_path.is_absolute() and pin_path.resolve() == pin_path and pin_path.is_file()
                and pin_path.stat().st_size <= 131_072):
            raise ExternalGlobalObservationError("GLOBAL_SOURCE_PIN_UNAVAILABLE")
        raw = pin_path.read_bytes()
        pin = _strict_json(raw)
        if not isinstance(pin, dict) or pin.get("schema") != "robot-scope.global-source-pin.v1":
            raise ExternalGlobalObservationError("GLOBAL_SOURCE_PIN_INVALID")
        files = pin.get("files")
        package = root / "auto_localization"
        if package.is_symlink() or not package.is_dir() or not isinstance(files, dict) or not files:
            raise ExternalGlobalObservationError("GLOBAL_SOURCE_PIN_INVALID")
        actual = {str(p.relative_to(root)) for p in package.rglob("*.py")}
        if actual != set(files) or "auto_localization/isolated.py" not in files:
            raise ExternalGlobalObservationError("GLOBAL_SOURCE_COVERAGE_MISMATCH")
        for name, expected in files.items():
            path = root / name
            if (path.resolve() != path or not path.is_file() or not isinstance(expected, str)
                    or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
                raise ExternalGlobalObservationError("GLOBAL_SOURCE_HASH_MISMATCH")
        return python, root, pin, hashlib.sha256(raw).hexdigest()

    def status(self) -> dict[str, Any]:
        try:
            _, _, _, pin_sha = self._configuration()
            return {"available": True, "reason": None, "backend_id": BACKEND_ID,
                    "source_pin_sha256": pin_sha, "deadline_s": self.timeout_s,
                    "dependency_runtime_probe_performed": False}
        except (OSError, ValueError, TypeError, ExternalGlobalObservationError) as exc:
            reason = str(exc) if isinstance(exc, ExternalGlobalObservationError) else "GLOBAL_SOURCE_PIN_INVALID"
            return {"available": False, "reason": reason, "backend_id": BACKEND_ID}

    @staticmethod
    def _array(data: bytes, metadata: dict[str, Any]) -> None:
        if (not isinstance(data, bytes) or not 0 < len(data) <= MAX_ARRAY_BYTES or len(data) % 24
                or metadata.get("encoding") != "float64_le_xyz"
                or type(metadata.get("point_count")) is not int
                or metadata["point_count"] != len(data) // 24
                or metadata.get("sha256") != hashlib.sha256(data).hexdigest()):
            raise ExternalGlobalObservationError("GLOBAL_ARRAY_CONTRACT_MISMATCH")
        if not np.isfinite(np.frombuffer(data, dtype="<f8")).all():
            raise ExternalGlobalObservationError("GLOBAL_NONFINITE_INPUT_UNSUPPORTED_NO_ROWS_REMOVED")

    def run_arrays(self, *, scan_bytes: bytes, map_bytes: bytes, context: dict[str, Any],
                   cancel_event: threading.Event) -> dict[str, Any]:
        started = time.monotonic()
        deadline = started + self.timeout_s

        def check() -> None:
            if cancel_event.is_set():
                raise ExternalGlobalObservationError("GLOBAL_CANCELLED")
            if time.monotonic() >= deadline:
                raise ExternalGlobalObservationError("GLOBAL_DEADLINE_EXCEEDED")

        check()
        python, source, pin, pin_sha = self._configuration()
        for name in ("map_id", "map_revision", "map_frame", "source_frame", "observer_id", "observer_epoch", "source_stamp_ns"):
            if not isinstance(context.get(name), str) or not context[name]:
                raise ExternalGlobalObservationError("GLOBAL_CONTEXT_INVALID")
        if not context["source_stamp_ns"].isdecimal() or int(context["source_stamp_ns"]) <= 0:
            raise ExternalGlobalObservationError("GLOBAL_SOURCE_STAMP_INVALID")
        self._array(scan_bytes, context["scan"])
        self._array(map_bytes, context["map"])
        # Copy strict JSON before crossing the process boundary; no mutable alias.
        context = _strict_json(json.dumps(context, allow_nan=False).encode())
        with tempfile.TemporaryDirectory(prefix="robot-scope-global-") as name:
            folder = Path(name)
            folder.chmod(0o700)
            for filename, data in (("scan.f64", scan_bytes), ("map.f64", map_bytes)):
                path = folder / filename
                path.write_bytes(data)
                path.chmod(0o600)
            envelope = {"context": context, "source_root": str(source), "source_pin": pin,
                        "remaining_s": max(0., deadline - time.monotonic())}
            (folder / "input.json").write_text(json.dumps(envelope, allow_nan=False))
            check()
            environment = {k: v for k, v in os.environ.items()
                           if not k.startswith(("PYTHON", "LD_", "DYLD_"))}
            environment.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
            process = subprocess.Popen([str(python), "-I", str(_WORKER), str(folder)],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       env=environment, start_new_session=True)
            output_bytes = 0
            try:
                with selectors.DefaultSelector() as selector:
                    for stream in (process.stdout, process.stderr):
                        os.set_blocking(stream.fileno(), False)
                        selector.register(stream, selectors.EVENT_READ)
                    while process.poll() is None or selector.get_map():
                        check()
                        for key, _ in selector.select(min(.05, max(0., deadline - time.monotonic()))):
                            chunk = os.read(key.fd, 8192)
                            if not chunk:
                                selector.unregister(key.fileobj)
                            output_bytes += len(chunk)
                            if output_bytes > MAX_LOG_BYTES:
                                raise ExternalGlobalObservationError("GLOBAL_WORKER_LOG_LIMIT")
                        result_path = folder / "result.json"
                        if result_path.exists() and (result_path.is_symlink() or result_path.stat().st_size > MAX_RESULT_BYTES):
                            raise ExternalGlobalObservationError("GLOBAL_RESULT_LIMIT")
                check()
                if process.returncode != 0:
                    raise ExternalGlobalObservationError("GLOBAL_WORKER_FAILED_EXIT_" + str(process.returncode))
                result_path = folder / "result.json"
                if not result_path.is_file() or result_path.is_symlink() or not 0 < result_path.stat().st_size <= MAX_RESULT_BYTES:
                    raise ExternalGlobalObservationError("GLOBAL_RESULT_MISSING_OR_OVERSIZED")
                result = _strict_json(result_path.read_bytes())
                self._validate_result(result, context)
                check()
            finally:
                # Reap descendants too: the trusted backend may spawn a native worker.
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
                process.wait(timeout=.2)
                for stream in (process.stdout, process.stderr):
                    stream.close()
            check()
        # This sidecar never reselects; the pinned backend owns its own
        # selection policy, ranking, ambiguity and non-residual gates.
        # The fixed policy is identical for every candidate. Retain its entire
        # metadata once so a diagnostics-heavy valid backend result can still
        # fit the unchanged 64 KiB result limit after the comparison is added.
        comparison_policy = evaluate_residual(0., policy=PROVISIONAL_RESIDUAL_POLICY).as_dict()
        for field in ("rmse_m", "residual_passed", "original_residual_passed"):
            comparison_policy.pop(field)
        comparison_policy["schema"] = "robot-scope.residual-comparison-policy.v1"
        comparison_policy["candidate_index_basis"] = "CANDIDATE_ARRAY_INDEX"
        comparison_policy["comparison_fields"] = ["residual_passed", "original_residual_passed"]
        comparisons = []
        for candidate in result["candidates"]:
            try:
                value = evaluate_residual(candidate.get("rmse_m"), policy=PROVISIONAL_RESIDUAL_POLICY)
                comparison = [value.residual_passed, value.original_residual_passed]
            except ValueError:
                comparison = {"reason": "INVALID_STORED_RMSE"}
            comparisons.append(comparison)
        result.update(residual_comparisons=comparisons,
                      residual_comparison_policy=comparison_policy,
                      residual_comparison_scope="STORED_RMSE_ONLY_NO_GLOBAL_RESELECTION",
                      execution={"elapsed_s": time.monotonic() - started, "source_pin_sha256": pin_sha,
                                 "backend_id": BACKEND_ID, "deadline_s": self.timeout_s,
                                 "worker_reaped": True, "worker_log_bytes": output_bytes})
        if len(json.dumps(result, allow_nan=False, separators=(",", ":")).encode()) > MAX_RESULT_BYTES:
            raise ExternalGlobalObservationError("GLOBAL_ENVELOPED_RESULT_LIMIT_NO_TRUNCATION")
        check()
        return result

    @staticmethod
    def _validate_result(value: Any, context: dict[str, Any]) -> None:
        if (not isinstance(value, dict) or value.get("status") != "OBSERVATION_ONLY_UNVERIFIED"
                or value.get("map_frame") != context["map_frame"]
                or value.get("scan_frame") != context["source_frame"]
                or value.get("frame_id") != context["source_frame"]
                or value.get("source_stamp_ns") != context["source_stamp_ns"]
                or value.get("session_id") != context["observer_epoch"]
                or value.get("map_id") != "sha256:" + context["map"]["sha256"]
                or value.get("input_points") != context["scan"]["point_count"]
                or value.get("reference_points") != context["map"]["point_count"]
                or not isinstance(value.get("candidates"), list)):
            raise ExternalGlobalObservationError("GLOBAL_RESULT_IDENTITY_MISMATCH")
        selected = value.get("selected_candidate")
        if selected is not None and (type(selected) is not int or not 0 <= selected < len(value["candidates"])):
            raise ExternalGlobalObservationError("GLOBAL_SELECTED_CANDIDATE_INVALID")
        for candidate in value["candidates"]:
            if not isinstance(candidate, dict) or not isinstance(candidate.get("gate_reasons"), list):
                raise ExternalGlobalObservationError("GLOBAL_CANDIDATE_INVALID")
            matrix = candidate.get("map_from_scan")
            if matrix is not None:
                a = np.asarray(matrix, dtype=float)
                if (a.shape != (4, 4) or not np.isfinite(a).all() or not np.allclose(a[3], [0, 0, 0, 1], atol=1e-8)
                        or not np.allclose(a[:3, :3].T @ a[:3, :3], np.eye(3), atol=1e-6)
                        or not math.isclose(float(np.linalg.det(a[:3, :3])), 1., abs_tol=1e-6)):
                    raise ExternalGlobalObservationError("GLOBAL_CANDIDATE_TRANSFORM_INVALID")
        if selected is not None and (value["candidates"][selected]["gate_reasons"]
                                     or value["candidates"][selected].get("map_from_scan") is None):
            raise ExternalGlobalObservationError("GLOBAL_SELECTED_CANDIDATE_REJECTED")
