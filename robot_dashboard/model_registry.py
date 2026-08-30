"""Fail-closed model package, target-engine, activation and rollback registry."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
import stat
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping

import yaml


REGISTRY_SCHEMA = "robot-scope.model-registry/v1"
OUTPUT_SCHEMA = "robot-scope.perception-result/v1"
ENGINE_SCHEMA = "robot-scope.engine-validation/v1"
MODEL_TASKS = frozenset({"lane", "object", "depth_summary"})
MODEL_STATES = frozenset({"staged", "validated", "active", "previous", "rejected"})
PACKAGE_FILES = frozenset(
    {"model.onnx", "labels.yaml", "metadata.json", "evaluation.json", "sha256.txt"}
)
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SESSION_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z_[0-9a-f]{32}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_ONNX_BYTES = 500 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
MAX_ENGINE_BYTES = 1024 * 1024 * 1024
MAX_BUILD_LOG_BYTES = 256 * 1024
METADATA_KEYS = frozenset(
    {
        "model_id",
        "task",
        "source_dataset_sessions",
        "training_code_commit",
        "class_names",
        "input_shape",
        "preprocessing",
        "output_schema_version",
        "opset",
        "validation_metrics",
        "created_at",
        "onnx_sha256",
        "supported_target",
    }
)
TARGET_KEYS = frozenset(
    {"platform", "jetpack_version", "tensorrt_version", "gpu_identity"}
)
ENGINE_KEYS = frozenset(
    {
        "schema_version",
        "model_id",
        "package_sha256",
        "engine_sha256",
        "jetpack_version",
        "tensorrt_version",
        "gpu_identity",
        "build_log_sha256",
        "created_at",
        "shadow_smoke_passed",
        "resource_check_passed",
    }
)
REGISTRY_RECORD_KEYS = frozenset(
    {
        "model_id",
        "task",
        "state",
        "package_sha256",
        "onnx_sha256",
        "created_at",
        "source_dataset_sessions",
        "supported_target",
        "engine",
        "reason",
    }
)
ENGINE_PUBLIC_KEYS = frozenset(
    {
        "sha256",
        "bytes",
        "build_log_sha256",
        "build_log_bytes",
        "jetpack_version",
        "tensorrt_version",
        "gpu_identity",
        "validated_at",
        "shadow_smoke_passed",
        "resource_check_passed",
    }
)
SECRET_PATTERN = re.compile(
    r"(?i)(password|secret|token|api[_-]?key|private[_-]?key)\s*[:=]\s*\S+"
)


class ModelRegistryError(RuntimeError):
    """Base error for model lifecycle operations."""


class ModelRegistryValidationError(ModelRegistryError):
    pass


class ModelRegistryConflict(ModelRegistryError):
    pass


class ModelRegistryNotFound(ModelRegistryError):
    pass


class ModelRegistryUnavailable(ModelRegistryError):
    pass


def _utc(value: object) -> str:
    if not isinstance(value, str) or len(value) > 64 or not value.endswith("Z"):
        raise ModelRegistryValidationError("timestamp is invalid")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ModelRegistryValidationError("timestamp is invalid") from exc
    return value


def _bounded_text(value: object, label: str, maximum: int = 128) -> str:
    if not isinstance(value, str):
        raise ModelRegistryValidationError(f"{label} is invalid")
    clean = " ".join(value.split())
    if not clean or len(clean) > maximum or any(ord(character) < 32 for character in clean):
        raise ModelRegistryValidationError(f"{label} is invalid")
    return clean


def _hash_file(path: Path, maximum: int) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise ModelRegistryValidationError("model artifact is not a regular file")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > maximum:
        raise ModelRegistryValidationError("model artifact size is invalid")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest(), info.st_size


def _write_new(path: Path, source: Any, maximum: int) -> tuple[str, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    digest = hashlib.sha256()
    written = 0
    try:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > maximum:
                raise ModelRegistryValidationError("model package entry exceeds its size limit")
            view = memoryview(chunk)
            while view:
                count = os.write(descriptor, view)
                if count <= 0:
                    raise OSError("short model artifact write")
                view = view[count:]
            digest.update(chunk)
        if written <= 0:
            raise ModelRegistryValidationError("model package entry is empty")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return digest.hexdigest(), written


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            break
        except OSError as exc:
            raise ModelRegistryValidationError("cannot inspect model registry root") from exc
        if stat.S_ISLNK(info.st_mode):
            raise ModelRegistryValidationError("model registry root cannot contain symlinks")


class ModelRegistry:
    """Own immutable packages and one atomic active/previous manifest."""

    def __init__(self, root: Path) -> None:
        requested = Path(root).expanduser()
        if not requested.is_absolute():
            raise ModelRegistryValidationError("model registry root must be absolute")
        _reject_symlink_components(requested)
        requested.mkdir(parents=True, exist_ok=True, mode=0o700)
        _reject_symlink_components(requested)
        if requested.is_symlink() or not requested.is_dir() or requested.resolve() == Path("/"):
            raise ModelRegistryValidationError("model registry root is invalid")
        self.root = requested.resolve(strict=True)
        self.root.chmod(0o700)
        self.packages = self.root / "packages"
        self.engines = self.root / "engines"
        for directory in (self.packages, self.engines):
            directory.mkdir(mode=0o700, exist_ok=True)
            if directory.is_symlink() or not directory.is_dir():
                raise ModelRegistryValidationError("model registry directory is invalid")
            directory.chmod(0o700)
        self.registry_path = self.root / "registry.json"
        self._lock = threading.RLock()
        if self.registry_path.exists():
            self._state = self._read_registry()
        else:
            self._state = {
                "schema_version": REGISTRY_SCHEMA,
                "models": {},
                "active": {},
                "previous": {},
            }
            self._atomic_registry(self._state)

    def _read_registry(self) -> Dict[str, Any]:
        if self.registry_path.is_symlink() or not self.registry_path.is_file():
            raise ModelRegistryUnavailable("model registry is unavailable")
        info = self.registry_path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > MAX_METADATA_BYTES:
            raise ModelRegistryUnavailable("model registry is unavailable")
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelRegistryUnavailable("model registry is unavailable") from exc
        if (
            not isinstance(payload, dict)
            or frozenset(payload) != frozenset({"schema_version", "models", "active", "previous"})
            or payload.get("schema_version") != REGISTRY_SCHEMA
            or not isinstance(payload.get("models"), dict)
            or not isinstance(payload.get("active"), dict)
            or not isinstance(payload.get("previous"), dict)
        ):
            raise ModelRegistryUnavailable("model registry is unavailable")
        models = payload["models"]
        active = payload["active"]
        previous = payload["previous"]
        try:
            if len(models) > 256 or set(active) - MODEL_TASKS or set(previous) - MODEL_TASKS:
                raise ValueError
            for model_id, record in models.items():
                if (
                    not isinstance(model_id, str)
                    or not MODEL_ID_RE.fullmatch(model_id)
                    or not isinstance(record, dict)
                    or frozenset(record) != REGISTRY_RECORD_KEYS
                    or record.get("model_id") != model_id
                    or record.get("task") not in MODEL_TASKS
                    or record.get("state") not in MODEL_STATES
                    or not HASH_RE.fullmatch(str(record.get("package_sha256", "")))
                    or not HASH_RE.fullmatch(str(record.get("onnx_sha256", "")))
                    or not isinstance(record.get("source_dataset_sessions"), list)
                    or not 1 <= len(record["source_dataset_sessions"]) <= 256
                    or any(
                        not isinstance(session_id, str)
                        or not SESSION_ID_RE.fullmatch(session_id)
                        for session_id in record["source_dataset_sessions"]
                    )
                    or not isinstance(record.get("reason"), str)
                    or len(record["reason"]) > 160
                    or any(ord(character) < 32 for character in record["reason"])
                ):
                    raise ValueError
                _utc(record.get("created_at"))
                target = record.get("supported_target")
                if (
                    not isinstance(target, dict)
                    or frozenset(target) != TARGET_KEYS
                    or target.get("platform") != "go2-internal-jetson"
                ):
                    raise ValueError
                for key in TARGET_KEYS:
                    _bounded_text(target.get(key), f"supported target {key}")
                engine = record.get("engine")
                if engine is not None:
                    if (
                        not isinstance(engine, dict)
                        or frozenset(engine) != ENGINE_PUBLIC_KEYS
                        or not HASH_RE.fullmatch(str(engine.get("sha256", "")))
                        or not HASH_RE.fullmatch(str(engine.get("build_log_sha256", "")))
                        or isinstance(engine.get("bytes"), bool)
                        or not isinstance(engine.get("bytes"), int)
                        or not 0 < engine["bytes"] <= MAX_ENGINE_BYTES
                        or isinstance(engine.get("build_log_bytes"), bool)
                        or not isinstance(engine.get("build_log_bytes"), int)
                        or not 0 < engine["build_log_bytes"] <= MAX_BUILD_LOG_BYTES
                        or engine.get("shadow_smoke_passed") is not True
                        or engine.get("resource_check_passed") is not True
                        or engine.get("jetpack_version") != target["jetpack_version"]
                        or engine.get("tensorrt_version") != target["tensorrt_version"]
                        or engine.get("gpu_identity") != target["gpu_identity"]
                    ):
                        raise ValueError
                    _utc(engine.get("validated_at"))
                if record["state"] in {"validated", "active", "previous"} and engine is None:
                    raise ValueError
            for task in MODEL_TASKS:
                active_id = active.get(task)
                previous_id = previous.get(task)
                if active_id is not None and (
                    active_id not in models
                    or models[active_id]["task"] != task
                    or models[active_id]["state"] != "active"
                ):
                    raise ValueError
                if previous_id is not None and (
                    previous_id not in models
                    or models[previous_id]["task"] != task
                    or models[previous_id]["state"] != "previous"
                    or previous_id == active_id
                ):
                    raise ValueError
            for model_id, record in models.items():
                if record["state"] == "active" and active.get(record["task"]) != model_id:
                    raise ValueError
                if record["state"] == "previous" and previous.get(record["task"]) != model_id:
                    raise ValueError
        except (KeyError, TypeError, ValueError, ModelRegistryValidationError) as exc:
            raise ModelRegistryUnavailable("model registry is unavailable") from exc
        return payload

    def _atomic_registry(self, payload: Mapping[str, Any]) -> None:
        encoded = json.dumps(
            payload,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) > MAX_METADATA_BYTES:
            raise ModelRegistryUnavailable("model registry metadata exceeds its limit")
        temporary = self.root / f".registry.json.tmp-{uuid.uuid4().hex}"
        try:
            with temporary.open("xb") as handle:
                os.chmod(handle.fileno(), 0o600)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.registry_path)
            descriptor = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _validate_preprocessing(value: object) -> Dict[str, Any]:
        if not isinstance(value, dict) or not 1 <= len(value) <= 16:
            raise ModelRegistryValidationError("preprocessing contract is invalid")
        encoded = json.dumps(value, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 16 * 1024:
            raise ModelRegistryValidationError("preprocessing contract is invalid")
        for key in value:
            if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", key):
                raise ModelRegistryValidationError("preprocessing contract is invalid")
        return json.loads(encoded)

    @staticmethod
    def _validate_metrics(value: object) -> Dict[str, float]:
        if not isinstance(value, dict) or len(value) > 32:
            raise ModelRegistryValidationError("validation metrics are invalid")
        result = {}
        for key, raw in value.items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,31}", key):
                raise ModelRegistryValidationError("validation metrics are invalid")
            if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
                raise ModelRegistryValidationError("validation metrics are invalid")
            result[key] = float(raw)
        return result

    @classmethod
    def _validate_metadata(cls, raw: object, onnx_sha: str) -> Dict[str, Any]:
        if not isinstance(raw, dict) or frozenset(raw) != METADATA_KEYS:
            raise ModelRegistryValidationError("model metadata schema is invalid")
        model_id = raw.get("model_id")
        if not isinstance(model_id, str) or not MODEL_ID_RE.fullmatch(model_id):
            raise ModelRegistryValidationError("model id is invalid")
        task = raw.get("task")
        if task not in MODEL_TASKS:
            raise ModelRegistryValidationError("model task is not supported")
        sessions = raw.get("source_dataset_sessions")
        if (
            not isinstance(sessions, list)
            or not 1 <= len(sessions) <= 256
            or any(not isinstance(item, str) or not SESSION_ID_RE.fullmatch(item) for item in sessions)
            or len(set(sessions)) != len(sessions)
        ):
            raise ModelRegistryValidationError("source dataset sessions are invalid")
        commit = raw.get("training_code_commit")
        if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
            raise ModelRegistryValidationError("training code commit is invalid")
        classes = raw.get("class_names")
        if (
            not isinstance(classes, list)
            or len(classes) > 256
            or any(
                not isinstance(item, str)
                or not item
                or len(item) > 64
                or any(ord(character) < 32 for character in item)
                for item in classes
            )
            or len(set(classes)) != len(classes)
            or (task == "object" and not classes)
            or (task != "object" and classes)
        ):
            raise ModelRegistryValidationError("model class names are invalid")
        shape = raw.get("input_shape")
        if (
            not isinstance(shape, list)
            or len(shape) != 4
            or any(isinstance(item, bool) or not isinstance(item, int) for item in shape)
            or shape[0:2] != [1, 3]
            or not 240 <= shape[2] <= 2160
            or not 320 <= shape[3] <= 3840
        ):
            raise ModelRegistryValidationError("model input shape is invalid")
        if raw.get("output_schema_version") != OUTPUT_SCHEMA:
            raise ModelRegistryValidationError("model output schema is unknown")
        opset = raw.get("opset")
        if isinstance(opset, bool) or not isinstance(opset, int) or not 9 <= opset <= 21:
            raise ModelRegistryValidationError("model opset is invalid")
        declared_hash = raw.get("onnx_sha256")
        if declared_hash != onnx_sha or not isinstance(declared_hash, str):
            raise ModelRegistryValidationError("ONNX hash does not match metadata")
        target = raw.get("supported_target")
        if not isinstance(target, dict) or frozenset(target) != TARGET_KEYS:
            raise ModelRegistryValidationError("supported target is invalid")
        target_clean = {
            key: _bounded_text(target[key], f"supported target {key}")
            for key in TARGET_KEYS
        }
        if target_clean["platform"] != "go2-internal-jetson":
            raise ModelRegistryValidationError("supported target is invalid")
        return {
            **raw,
            "source_dataset_sessions": list(sessions),
            "class_names": list(classes),
            "input_shape": list(shape),
            "preprocessing": cls._validate_preprocessing(raw.get("preprocessing")),
            "validation_metrics": cls._validate_metrics(raw.get("validation_metrics")),
            "created_at": _utc(raw.get("created_at")),
            "supported_target": target_clean,
        }

    @staticmethod
    def _package_digest(directory: Path) -> str:
        digest = hashlib.sha256()
        for name in sorted(PACKAGE_FILES):
            path = directory / name
            file_hash, size = _hash_file(
                path,
                MAX_ONNX_BYTES if name == "model.onnx" else MAX_METADATA_BYTES,
            )
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(size).encode("ascii"))
            digest.update(b"\0")
            digest.update(file_hash.encode("ascii"))
            digest.update(b"\n")
        return digest.hexdigest()

    def stage_archive(self, archive_path: Path) -> Dict[str, Any]:
        archive_path = Path(archive_path)
        _hash_file(archive_path, MAX_PACKAGE_BYTES)
        temporary = self.packages / f".stage-{uuid.uuid4().hex}"
        temporary.mkdir(mode=0o700)
        try:
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    entries = archive.infolist()
                    if (
                        len(entries) != len(PACKAGE_FILES)
                        or {entry.filename for entry in entries} != PACKAGE_FILES
                        or any(entry.is_dir() or entry.flag_bits & 0x1 for entry in entries)
                        or sum(entry.file_size for entry in entries) > MAX_PACKAGE_BYTES
                    ):
                        raise ModelRegistryValidationError("model package archive layout is invalid")
                    hashes = {}
                    for entry in entries:
                        maximum = (
                            MAX_ONNX_BYTES if entry.filename == "model.onnx" else MAX_METADATA_BYTES
                        )
                        if entry.file_size <= 0 or entry.file_size > maximum:
                            raise ModelRegistryValidationError("model package entry size is invalid")
                        with archive.open(entry) as source:
                            hashes[entry.filename], written = _write_new(
                                temporary / entry.filename,
                                source,
                                maximum,
                            )
                        if written != entry.file_size:
                            raise ModelRegistryValidationError("model package entry size changed")
            except (zipfile.BadZipFile, OSError) as exc:
                raise ModelRegistryValidationError("model package archive is invalid") from exc
            try:
                metadata_raw = json.loads((temporary / "metadata.json").read_text(encoding="utf-8"))
                evaluation = json.loads((temporary / "evaluation.json").read_text(encoding="utf-8"))
                labels = yaml.safe_load((temporary / "labels.yaml").read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
                raise ModelRegistryValidationError("model package metadata is invalid") from exc
            metadata = self._validate_metadata(metadata_raw, hashes["model.onnx"])
            if not isinstance(evaluation, dict) or not evaluation:
                raise ModelRegistryValidationError("model evaluation is invalid")
            try:
                evaluation_encoded = json.dumps(
                    evaluation,
                    allow_nan=False,
                    separators=(",", ":"),
                )
            except (TypeError, ValueError) as exc:
                raise ModelRegistryValidationError("model evaluation is invalid") from exc
            if len(evaluation_encoded.encode("utf-8")) > MAX_METADATA_BYTES:
                raise ModelRegistryValidationError("model evaluation is invalid")
            if labels != metadata["class_names"]:
                raise ModelRegistryValidationError("labels do not match model metadata")
            checksum_text = (temporary / "sha256.txt").read_text(encoding="ascii").strip()
            if checksum_text != f"{hashes['model.onnx']}  model.onnx":
                raise ModelRegistryValidationError("model checksum file is invalid")
            package_sha = self._package_digest(temporary)
            model_id = metadata["model_id"]
            final = self.packages / f"{model_id}-{package_sha[:16]}"
            with self._lock:
                existing = self._state["models"].get(model_id)
                if existing and existing.get("package_sha256") != package_sha:
                    raise ModelRegistryConflict("model id already refers to another package")
                if existing:
                    return copy.deepcopy(existing)
                if not final.exists():
                    os.rename(temporary, final)
                    descriptor = os.open(self.packages, os.O_RDONLY)
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                elif final.is_symlink() or not final.is_dir():
                    raise ModelRegistryUnavailable("model package registry is invalid")
                elif self._package_digest(final) != package_sha:
                    raise ModelRegistryUnavailable("existing model package content is invalid")
                record = {
                    "model_id": model_id,
                    "task": metadata["task"],
                    "state": "staged",
                    "package_sha256": package_sha,
                    "onnx_sha256": hashes["model.onnx"],
                    "created_at": metadata["created_at"],
                    "source_dataset_sessions": metadata["source_dataset_sessions"],
                    "supported_target": metadata["supported_target"],
                    "engine": None,
                    "reason": "",
                }
                next_state = copy.deepcopy(self._state)
                next_state["models"][model_id] = record
                self._atomic_registry(next_state)
                self._state = next_state
                return copy.deepcopy(record)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)

    def validate_engine(
        self,
        model_id: str,
        engine_path: Path,
        engine_metadata_path: Path,
        build_log_path: Path,
    ) -> Dict[str, Any]:
        if not isinstance(model_id, str) or not MODEL_ID_RE.fullmatch(model_id):
            raise ModelRegistryNotFound("model was not found")
        with self._lock:
            record = copy.deepcopy(self._state["models"].get(model_id))
        if not record:
            raise ModelRegistryNotFound("model was not found")
        if record.get("state") not in {"staged", "rejected"}:
            raise ModelRegistryConflict("model engine validation is not available in this state")
        engine_sha, engine_bytes = _hash_file(Path(engine_path), MAX_ENGINE_BYTES)
        log_sha, log_bytes = _hash_file(Path(build_log_path), MAX_BUILD_LOG_BYTES)
        _hash_file(Path(engine_metadata_path), MAX_METADATA_BYTES)
        try:
            log_text = Path(build_log_path).read_text(encoding="utf-8")
            engine_metadata = json.loads(Path(engine_metadata_path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelRegistryValidationError("engine validation evidence is invalid") from exc
        if SECRET_PATTERN.search(log_text) or any(
            character not in "\n\r\t" and ord(character) < 32 for character in log_text
        ):
            raise ModelRegistryValidationError("engine build log is not safely redacted")
        if not isinstance(engine_metadata, dict) or frozenset(engine_metadata) != ENGINE_KEYS:
            raise ModelRegistryValidationError("engine validation evidence is invalid")
        target = record["supported_target"]
        if (
            engine_metadata.get("schema_version") != ENGINE_SCHEMA
            or engine_metadata.get("model_id") != model_id
            or engine_metadata.get("package_sha256") != record["package_sha256"]
            or engine_metadata.get("engine_sha256") != engine_sha
            or engine_metadata.get("build_log_sha256") != log_sha
            or engine_metadata.get("jetpack_version") != target["jetpack_version"]
            or engine_metadata.get("tensorrt_version") != target["tensorrt_version"]
            or engine_metadata.get("gpu_identity") != target["gpu_identity"]
            or engine_metadata.get("shadow_smoke_passed") is not True
            or engine_metadata.get("resource_check_passed") is not True
        ):
            self.reject(model_id, "target engine validation failed")
            raise ModelRegistryValidationError("engine does not match the validated target")
        _utc(engine_metadata.get("created_at"))
        destination = self.engines / model_id
        destination.mkdir(mode=0o700, exist_ok=True)
        if destination.is_symlink() or not destination.is_dir():
            raise ModelRegistryUnavailable("engine registry directory is invalid")
        temporary = destination / f".engine-{uuid.uuid4().hex}"
        temporary.mkdir(mode=0o700)
        try:
            shutil.copyfile(engine_path, temporary / "engine.plan", follow_symlinks=False)
            shutil.copyfile(build_log_path, temporary / "build.log", follow_symlinks=False)
            copied_engine_sha, copied_engine_bytes = _hash_file(
                temporary / "engine.plan",
                MAX_ENGINE_BYTES,
            )
            copied_log_sha, copied_log_bytes = _hash_file(
                temporary / "build.log",
                MAX_BUILD_LOG_BYTES,
            )
            if (
                copied_engine_sha != engine_sha
                or copied_engine_bytes != engine_bytes
                or copied_log_sha != log_sha
                or copied_log_bytes != log_bytes
            ):
                raise ModelRegistryValidationError("engine validation artifacts changed during copy")
            (temporary / "engine-validation.json").write_text(
                json.dumps(engine_metadata, allow_nan=False, separators=(",", ":"), sort_keys=True),
                encoding="utf-8",
            )
            for artifact in temporary.iterdir():
                artifact.chmod(0o600)
                descriptor = os.open(artifact, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            descriptor = os.open(temporary, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            final = destination / engine_sha
            if final.exists():
                try:
                    if final.is_symlink() or not final.is_dir():
                        raise ModelRegistryUnavailable(
                            "existing engine validation content is invalid"
                        )
                    entries = {
                        artifact.name: artifact
                        for artifact in final.iterdir()
                    }
                    if (
                        set(entries) != {
                            "engine.plan",
                            "build.log",
                            "engine-validation.json",
                        }
                        or any(
                            artifact.is_symlink() or not artifact.is_file()
                            for artifact in entries.values()
                        )
                    ):
                        raise ModelRegistryUnavailable(
                            "existing engine validation content is invalid"
                        )
                    existing_engine_sha, existing_engine_bytes = _hash_file(
                        entries["engine.plan"],
                        MAX_ENGINE_BYTES,
                    )
                    existing_log_sha, existing_log_bytes = _hash_file(
                        entries["build.log"],
                        MAX_BUILD_LOG_BYTES,
                    )
                    _hash_file(entries["engine-validation.json"], MAX_METADATA_BYTES)
                    existing_metadata = json.loads(
                        entries["engine-validation.json"].read_text(encoding="utf-8")
                    )
                    if (
                        existing_engine_sha != engine_sha
                        or existing_engine_bytes != engine_bytes
                        or existing_log_sha != log_sha
                        or existing_log_bytes != log_bytes
                        or existing_metadata != engine_metadata
                    ):
                        raise ModelRegistryUnavailable(
                            "existing engine validation content is invalid"
                        )
                except (
                    OSError,
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                    ModelRegistryValidationError,
                ) as exc:
                    raise ModelRegistryUnavailable(
                        "existing engine validation content is invalid"
                    ) from exc
                shutil.rmtree(temporary)
            else:
                os.rename(temporary, final)
                descriptor = os.open(destination, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            engine_public = {
                "sha256": engine_sha,
                "bytes": engine_bytes,
                "build_log_sha256": log_sha,
                "build_log_bytes": log_bytes,
                "jetpack_version": target["jetpack_version"],
                "tensorrt_version": target["tensorrt_version"],
                "gpu_identity": target["gpu_identity"],
                "validated_at": engine_metadata["created_at"],
                "shadow_smoke_passed": True,
                "resource_check_passed": True,
            }
            with self._lock:
                next_state = copy.deepcopy(self._state)
                next_record = next_state["models"][model_id]
                next_record["state"] = "validated"
                next_record["engine"] = engine_public
                next_record["reason"] = ""
                self._atomic_registry(next_state)
                self._state = next_state
                return copy.deepcopy(next_record)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)

    def reject(self, model_id: str, reason: str) -> Dict[str, Any]:
        reason = _bounded_text(reason, "rejection reason", 160)
        with self._lock:
            if model_id not in self._state["models"]:
                raise ModelRegistryNotFound("model was not found")
            next_state = copy.deepcopy(self._state)
            record = next_state["models"][model_id]
            if record.get("state") in {"active", "previous"}:
                raise ModelRegistryConflict(
                    "an active or rollback-candidate model cannot be rejected"
                )
            record["state"] = "rejected"
            record["reason"] = reason
            self._atomic_registry(next_state)
            self._state = next_state
            return copy.deepcopy(record)

    def activate(self, model_id: str, confirmation: str) -> Dict[str, Any]:
        if confirmation != model_id:
            raise ModelRegistryConflict("model activation requires exact operator confirmation")
        with self._lock:
            record = self._state["models"].get(model_id)
            if not record:
                raise ModelRegistryNotFound("model was not found")
            if record.get("state") != "validated" or not isinstance(record.get("engine"), dict):
                raise ModelRegistryConflict("only a target-validated model can be activated")
            package_path = self.packages / f"{model_id}-{record['package_sha256'][:16]}"
            if self._package_digest(package_path) != record["package_sha256"]:
                raise ModelRegistryValidationError("validated model package hash changed")
            engine_path = self.engines / model_id / record["engine"]["sha256"] / "engine.plan"
            engine_sha, _ = _hash_file(engine_path, MAX_ENGINE_BYTES)
            if engine_sha != record["engine"]["sha256"]:
                raise ModelRegistryValidationError("validated engine hash changed")
            task = record["task"]
            current = self._state["active"].get(task)
            next_state = copy.deepcopy(self._state)
            old_previous = next_state["previous"].pop(task, None)
            if old_previous and old_previous != current:
                old_previous_record = next_state["models"].get(old_previous)
                if (
                    old_previous_record is None
                    or old_previous_record.get("state") != "previous"
                ):
                    raise ModelRegistryUnavailable(
                        "model rollback state is inconsistent"
                    )
                old_previous_record["state"] = "validated"
            if current and current in next_state["models"]:
                next_state["models"][current]["state"] = "previous"
                next_state["previous"][task] = current
            next_state["models"][model_id]["state"] = "active"
            next_state["active"][task] = model_id
            self._atomic_registry(next_state)
            self._state = next_state
            return self.active_snapshot()

    def rollback(self, task: str, confirmation: str) -> Dict[str, Any]:
        if task not in MODEL_TASKS:
            raise ModelRegistryValidationError("model task is not supported")
        with self._lock:
            current = self._state["active"].get(task)
            previous = self._state["previous"].get(task)
            if not current or confirmation != current:
                raise ModelRegistryConflict("rollback requires the exact active model confirmation")
            if not previous or previous not in self._state["models"]:
                raise ModelRegistryConflict("no previous model is available")
            previous_record = self._state["models"][previous]
            if (
                previous_record.get("state") != "previous"
                or not isinstance(previous_record.get("engine"), dict)
            ):
                raise ModelRegistryConflict("previous model validation is unavailable")
            package_path = self.packages / (
                f"{previous}-{previous_record['package_sha256'][:16]}"
            )
            if self._package_digest(package_path) != previous_record["package_sha256"]:
                raise ModelRegistryValidationError("previous model package hash changed")
            engine_path = self.engines / previous / previous_record["engine"]["sha256"] / "engine.plan"
            engine_sha, _ = _hash_file(engine_path, MAX_ENGINE_BYTES)
            if engine_sha != previous_record["engine"]["sha256"]:
                raise ModelRegistryValidationError("previous engine hash changed")
            next_state = copy.deepcopy(self._state)
            next_state["models"][current]["state"] = "previous"
            next_state["models"][previous]["state"] = "active"
            next_state["active"][task] = previous
            next_state["previous"][task] = current
            self._atomic_registry(next_state)
            self._state = next_state
            return self.active_snapshot()

    def list_models(self) -> Dict[str, Any]:
        with self._lock:
            models = [copy.deepcopy(self._state["models"][key]) for key in sorted(self._state["models"])]
            return {
                "schema_version": REGISTRY_SCHEMA,
                "models": models,
                "active": copy.deepcopy(self._state["active"]),
                "previous": copy.deepcopy(self._state["previous"]),
                "activation_surface": "LOCAL_OPERATOR_ONLY",
            }

    def active_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            active = {}
            for task, model_id in self._state["active"].items():
                record = self._state["models"].get(model_id)
                if record and record.get("state") == "active":
                    active[task] = {
                        "model_id": model_id,
                        "package_sha256": record["package_sha256"],
                        "engine_sha256": record["engine"]["sha256"],
                    }
            return {
                "schema_version": REGISTRY_SCHEMA,
                "active": active,
                "previous": copy.deepcopy(self._state["previous"]),
                "activation_surface": "LOCAL_OPERATOR_ONLY",
            }
