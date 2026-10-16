"""Private, revision-pinned native SLAM bundles, independent of ROS imports.

Paths returned by staging/load methods are installation-side capabilities. HTTP
requests must use opaque IDs; none of the management methods accepts a path.
Native files are never edited in place, including during saved-map localization.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import shutil
import stat
import struct
import tempfile
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Mapping

from .slam_preview_export import MAX_EXPORT_BYTES, PreviewExportError, preview_export_files


SCHEMA = "robot-scope.native-slam-package/v1"
ID_RE = re.compile(r"^np_[0-9a-f]{32}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
CHUNK_BYTES = 1024 * 1024


class MapPackageError(ValueError):
    """Expected, path-free failure suitable for an API error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class NativeSaveStaging:
    token: str
    native_path: Path


@dataclass(frozen=True)
class NativeLoadScratch:
    scratch_id: str
    native_path: Path
    package_id: str
    revision: str
    reference_token: str


def _fail(code: str, message: str) -> None:
    raise MapPackageError(code, message)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False,
                          sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        _fail("INVALID_METADATA", "Metadata must contain finite JSON values.")


def _parse_json(raw: bytes) -> Any:
    try:
        return json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        _fail("INVALID_PACKAGE", "Package JSON is invalid.")


def _relative(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        _fail("UNSAFE_ARCHIVE", "Artifact name is invalid.")
    # Backslashes and drive prefixes are rejected on every host, including POSIX.
    if "\\" in value or ":" in value or "\x00" in value or value.startswith("/"):
        _fail("UNSAFE_ARCHIVE", "Artifact name is unsafe.")
    parts = value.split("/")
    if any(part in {"", ".", ".."} or len(part) > 255 or
           any(ord(char) < 32 for char in part) for part in parts):
        _fail("UNSAFE_ARCHIVE", "Artifact name is unsafe.")
    if str(PurePosixPath(value)) != value:
        _fail("UNSAFE_ARCHIVE", "Artifact name is unsafe.")
    return value


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        _fail("UNSAFE_ROOT", "Package root must be a real private directory.")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        _fail("UNSAFE_ROOT", "Package root must be private to its owner.")
    return path.resolve(strict=True)


def _write_private(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _path_safe(method):
    """Never expose an installation's private filesystem through an API error."""
    @wraps(method)
    def call(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except OSError:
            _fail("PACKAGE_IO_ERROR", "Native package storage operation could not be completed.")
    return call


def _bounded_zip_directory(raw: bytes, max_entries: int) -> None:
    """Bound the central directory before ZipFile eagerly creates ZipInfo objects.

    The EOCD count alone is insufficient: an author can lie about it while
    supplying millions of minimum-sized central records. Native archives do not
    need self-extracting prefixes, multi-volume containers, or ZIP64 entry counts.
    ZIP64 individual file fields remain accepted by ZipFile after this check.
    """
    end = raw.rfind(b"PK\x05\x06", max(0, len(raw) - 65557))
    if end < 0 or end + 22 > len(raw):
        _fail("INVALID_PACKAGE", "Import archive has no valid directory.")
    _, disk, directory_disk, disk_entries, declared_entries, size, offset, comment = struct.unpack_from(
        "<4s4H2LH", raw, end)
    if disk or directory_disk or disk_entries != declared_entries or end + 22 + comment != len(raw):
        _fail("UNSAFE_ARCHIVE", "Multi-volume or ambiguous ZIP directories are unsupported.")
    if declared_entries > max_entries or declared_entries == 0xFFFF:
        _fail("PACKAGE_LIMIT", "Import archive contains too many files.")
    if offset + size != end:
        _fail("UNSAFE_ARCHIVE", "ZIP directory offsets are unsupported.")
    cursor, count = offset, 0
    while cursor < end:
        if cursor + 46 > end or raw[cursor:cursor + 4] != b"PK\x01\x02":
            _fail("INVALID_PACKAGE", "Import archive directory is invalid.")
        name_size, extra_size, comment_size = struct.unpack_from("<3H", raw, cursor + 28)
        cursor += 46 + name_size + extra_size + comment_size
        count += 1
        if count > max_entries:
            _fail("PACKAGE_LIMIT", "Import archive contains too many files.")
    if cursor != end or count != declared_entries:
        _fail("INVALID_PACKAGE", "Import archive directory count is inconsistent.")


def _safe_zip_extra(extra: bytes) -> None:
    cursor = 0
    while cursor < len(extra):
        if cursor + 4 > len(extra):
            _fail("UNSAFE_ARCHIVE", "Archive extra field is invalid.")
        field, size = struct.unpack_from("<HH", extra, cursor)
        cursor += 4 + size
        # PKWARE Unix and ASi Unix can encode hard/symbolic links outside the
        # ordinary file-mode field. Never interpret or preserve these records.
        if cursor > len(extra) or field in {0x000D, 0x756E}:
            _fail("UNSAFE_ARCHIVE", "Archive contains unsupported link metadata.")


class MapPackageStore:
    """Atomic native bundle catalog with explicit runtime compatibility gates.

    An engine must finish its official save and relinquish its writer before
    ``publish_staging``. The store additionally checks stable file signatures
    across a quiet interval and across hashing/copying; this is not a substitute
    for the engine's completion acknowledgement.
    """

    def __init__(self, root: Path, *, max_native_bytes: int = 2 * 1024**3,
                 max_files: int = 4096, max_archive_bytes: int = 512 * 1024**2,
                 max_preview_bytes: int = 16 * 1024**2,
                 max_manifest_bytes: int = 2 * 1024**2,
                 max_compression_ratio: float = 200.0,
                 quiescence_seconds: float = 0.05):
        for limit in (max_native_bytes, max_files, max_archive_bytes,
                      max_preview_bytes, max_manifest_bytes):
            if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
                raise ValueError("Package limits must be positive integers")
        if (not math.isfinite(quiescence_seconds) or quiescence_seconds <= 0 or
                not math.isfinite(max_compression_ratio) or max_compression_ratio <= 0):
            raise ValueError("Package timing and compression limits must be positive")
        self.root = _private_dir(Path(root))
        self._packages = _private_dir(self.root / "packages")
        self._staging_root = _private_dir(self.root / "staging")
        self._scratch_root = _private_dir(self.root / "scratch")
        self.max_native_bytes = max_native_bytes
        self.max_files = max_files
        self.max_archive_bytes = max_archive_bytes
        self.max_preview_bytes = max_preview_bytes
        self.max_manifest_bytes = max_manifest_bytes
        self.max_compression_ratio = max_compression_ratio
        self.quiescence_seconds = quiescence_seconds
        self._lock = threading.RLock()
        self._staging: dict[str, NativeSaveStaging] = {}
        self._references: dict[str, tuple[str, str]] = {}
        self._scratch: dict[str, NativeLoadScratch] = {}

    @_path_safe
    def create_staging(self) -> NativeSaveStaging:
        with self._lock:
            token = uuid.uuid4().hex
            # pathlib applies mode only to the leaf when parents=True. Create
            # and validate the opaque token directory before its native child.
            workspace = _private_dir(self._staging_root / token)
            native = _private_dir(workspace / "native")
            staging = NativeSaveStaging(token, native)
            self._staging[token] = staging
            return staging

    @_path_safe
    def discard_staging(self, token: str) -> None:
        """Only after the adapter has stopped the writer; no engine is stopped here."""
        with self._lock:
            staging = self._staging.pop(token, None)
            if staging is None:
                _fail("STAGING_NOT_FOUND", "Native save staging is unavailable.")
            shutil.rmtree(staging.native_path.parent)

    def _scan(self, native: Path) -> dict[str, tuple[int, int, int, int]]:
        if native.is_symlink() or not native.is_dir():
            _fail("INVALID_PACKAGE", "Native artifact directory is unavailable.")
        files: dict[str, tuple[int, int, int, int]] = {}
        total = 0
        entries = 0
        for directory, dirs, names in os.walk(native, followlinks=False):
            for name in dirs + names:
                path = Path(directory) / name
                relative = _relative(path.relative_to(native).as_posix())
                info = path.lstat()
                entries += 1
                if entries > self.max_files * 2:
                    _fail("PACKAGE_LIMIT", "Native package contains too many entries.")
                if stat.S_ISLNK(info.st_mode) or not (
                        stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    _fail("UNSAFE_ARTIFACT", "Native package contains a link or special file.")
                if stat.S_ISREG(info.st_mode):
                    if info.st_nlink != 1:
                        _fail("UNSAFE_ARTIFACT", "Native package contains linked artifacts.")
                    total += info.st_size
                    if len(files) >= self.max_files or total > self.max_native_bytes:
                        _fail("PACKAGE_LIMIT", "Native package exceeds configured limits.")
                    files[relative] = (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if not files:
            _fail("NATIVE_FILES_MISSING", "Native save produced no files.")
        return files

    def _copy_native(self, source: Path, target: Path,
                     signatures: Mapping[str, tuple[int, int, int, int]]) -> list[dict]:
        artifacts = []
        for name, signature in sorted(signatures.items()):
            destination = target / name
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(source / name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as reader:
                info = os.fstat(reader.fileno())
                if (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != signature:
                    _fail("NATIVE_WRITE_ACTIVE", "Native artifacts changed during publication.")
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    _fail("UNSAFE_ARTIFACT", "Native artifact is not an independent regular file.")
                digest = hashlib.sha256()
                count = 0
                output = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(output, "wb") as writer:
                    while True:
                        chunk = reader.read(CHUNK_BYTES)
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > signature[1]:
                            _fail("NATIVE_WRITE_ACTIVE", "Native artifacts changed during publication.")
                        digest.update(chunk)
                        writer.write(chunk)
                    writer.flush()
                    os.fsync(writer.fileno())
                after = os.fstat(reader.fileno())
                if (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != signature:
                    _fail("NATIVE_WRITE_ACTIVE", "Native artifacts changed during publication.")
                if count != signature[1]:
                    _fail("NATIVE_WRITE_ACTIVE", "Native artifact size changed during publication.")
            artifacts.append({"path": name, "size_bytes": count, "sha256": digest.hexdigest()})
        return artifacts

    def _metadata(self, metadata: Mapping[str, Any]) -> dict:
        if not isinstance(metadata, Mapping):
            _fail("INVALID_METADATA", "Package metadata must be an object.")
        name = metadata.get("name", "Untitled native map")
        if (not isinstance(name, str) or not name.strip() or len(name) > 120 or
                any(ord(char) < 32 for char in name)):
            _fail("INVALID_NAME", "Map display name is invalid.")
        result: dict[str, Any] = {"name": name.strip(), "map_kind": "vslam_native"}
        for field in ("engine_id", "engine_version", "native_format_version",
                      "source_session_id", "map_frame", "calibration_hash",
                      "sensor_config_hash", "site_id", "capture_time", "native_snapshot_id"):
            value = metadata.get(field)
            if value is not None and (not isinstance(value, str) or not value or len(value) > 256 or
                                      any(ord(char) < 32 for char in value)):
                _fail("INVALID_METADATA", "Package metadata field is invalid.")
            result[field] = value
        if not result["engine_id"]:
            _fail("INVALID_METADATA", "A native package requires an engine ID.")
        result["units"] = metadata.get("units", "unknown")
        result["axes"] = metadata.get("axes", "unknown")
        if (not isinstance(result["units"], str) or not isinstance(result["axes"], str) or
                result["units"] not in {"m", "unknown"} or result["axes"] not in {"ros", "unknown"}):
            _fail("INVALID_METADATA", "Map coordinate convention is invalid.")
        # Runtime/load validation is deliberately never accepted from callers or an archive.
        result["validation"] = {"native_load": "unknown", "localization_attempt": "unknown",
                                "localization_success": "unknown"}
        result["data_provenance"] = metadata.get("data_provenance", "unknown")
        if not isinstance(result["data_provenance"], (str, dict)):
            _fail("INVALID_METADATA", "Data provenance must be a string or object.")
        if len(_json_bytes(result)) > 16384:
            _fail("INVALID_METADATA", "Package metadata is too large.")
        return result

    @_path_safe
    def publish_staging(self, token: str, *, metadata: Mapping[str, Any],
                        official_save_completed: bool,
                        required_native_files: tuple[str, ...] | list[str],
                        preview: Any = None,
                        preview_consistency: str = "approximate") -> dict:
        """Publish only an acknowledged official save, atomically and without hardlinks.

        Failed publication leaves staging available for adapter diagnosis/cleanup.
        A preview may be exact only with matching engine snapshot IDs supplied in
        both metadata.native_snapshot_id and preview.native_snapshot_id.
        """
        with self._lock:
            if official_save_completed is not True:
                _fail("SAVE_INCOMPLETE", "Official native save has not completed.")
            staging = self._staging.get(token)
            if staging is None:
                _fail("STAGING_NOT_FOUND", "Native save staging is unavailable.")
            normalized = self._metadata(metadata)
            if not isinstance(required_native_files, (tuple, list)) or not required_native_files:
                _fail("NATIVE_FILES_MISSING", "The adapter must declare required native files.")
            required = {_relative(name) for name in required_native_files}
            before = self._scan(staging.native_path)
            if not required.issubset(before) or any(before[name][1] <= 0 for name in required):
                _fail("NATIVE_FILES_MISSING", "Required native save artifacts are missing or empty.")
            time.sleep(self.quiescence_seconds)
            if before != self._scan(staging.native_path):
                _fail("NATIVE_WRITE_ACTIVE", "Native save artifacts are still changing.")
            return self._publish(staging, normalized, before, preview,
                                 preview_consistency, "official_save_acknowledged")

    def _publish(self, staging: NativeSaveStaging, metadata: dict,
                 signatures: dict, preview: Any, consistency: str, completion: str,
                 *, derived_from: dict | None = None) -> dict:
        if consistency not in {"approximate", "exact", "unavailable"}:
            _fail("INVALID_METADATA", "Preview consistency is invalid.")
        if preview is None:
            consistency = "unavailable"
        elif consistency == "exact" and not (
                isinstance(preview, dict) and metadata.get("native_snapshot_id") and
                preview.get("native_snapshot_id") == metadata["native_snapshot_id"]):
            _fail("SNAPSHOT_MISMATCH", "Exact preview requires the same native snapshot ID.")
        preview_bytes = _json_bytes(preview) if preview is not None else None
        if preview_bytes is not None and len(preview_bytes) > self.max_preview_bytes:
            _fail("PACKAGE_LIMIT", "Native map preview is too large.")
        package_id = "np_" + uuid.uuid4().hex
        building = _private_dir(self._staging_root / ("publish_" + uuid.uuid4().hex))
        try:
            native = _private_dir(building / "native")
            artifacts = self._copy_native(staging.native_path, native, signatures)
            if signatures != self._scan(staging.native_path):
                _fail("NATIVE_WRITE_ACTIVE", "Native save artifacts changed during publication.")
            manifest = {"metadata_schema": SCHEMA, "package_id": package_id,
                        **metadata, "created_at": _now(), "metadata_generation": 1,
                        "native_artifacts": artifacts,
                        "native_content_revision": hashlib.sha256(_json_bytes(artifacts)).hexdigest(),
                        "preview_revision": (hashlib.sha256(preview_bytes).hexdigest()
                                             if preview_bytes is not None else None),
                        "preview_consistency": consistency,
                        "preview_capture_time": (preview.get("capture_time")
                                                 if isinstance(preview, dict) else None),
                        "save_completion": {"status": "completed", "evidence": completion,
                                            "verified_at": _now()},
                        "derived_from": derived_from}
            manifest["revision"] = self._revision(manifest)
            manifest_bytes = _json_bytes(manifest)
            if len(manifest_bytes) > self.max_manifest_bytes:
                _fail("PACKAGE_LIMIT", "Native package manifest is too large.")
            if preview_bytes is not None:
                _private_dir(building / "preview")
                _write_private(building / "preview" / "snapshot.json", preview_bytes)
            _write_private(building / "manifest.json", manifest_bytes)
            # Rename is on the same filesystem. Catalog readers never see partial packages.
            os.replace(building, self._packages / package_id)
        finally:
            if building.exists():
                shutil.rmtree(building)
        self._staging.pop(staging.token, None)
        result = self._public(manifest)
        try:
            shutil.rmtree(staging.native_path.parent)
            result["staging_cleanup"] = "complete"
        except OSError:
            # The immutable package is already committed. Do not report a failed
            # save (and encourage a duplicate retry) for a cleanup-only failure.
            result["staging_cleanup"] = "pending"
        return result

    @staticmethod
    def _revision(manifest: dict) -> str:
        return hashlib.sha256(_json_bytes({key: value for key, value in manifest.items()
                                          if key != "revision"})).hexdigest()

    def _path(self, package_id: str) -> Path:
        if not isinstance(package_id, str) or not ID_RE.fullmatch(package_id):
            _fail("PACKAGE_NOT_FOUND", "Native map package was not found.")
        path = self._packages / package_id
        if path.is_symlink() or not path.is_dir():
            _fail("PACKAGE_NOT_FOUND", "Native map package was not found.")
        return path

    def _read_regular(self, path: Path, limit: int) -> bytes:
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
                    _fail("INVALID_PACKAGE", "Package artifact is invalid or exceeds limits.")
                raw = handle.read(limit + 1)
                if len(raw) > limit:
                    _fail("PACKAGE_LIMIT", "Package artifact exceeds configured limits.")
                return raw
        except OSError:
            _fail("INVALID_PACKAGE", "Package artifact is unavailable.")

    def _manifest(self, package_id: str) -> dict:
        manifest = _parse_json(self._read_regular(self._path(package_id) / "manifest.json",
                                                  self.max_manifest_bytes))
        if (not isinstance(manifest, dict) or manifest.get("metadata_schema") != SCHEMA or
                manifest.get("package_id") != package_id or
                manifest.get("revision") != self._revision(manifest)):
            _fail("INVALID_PACKAGE", "Native package manifest failed validation.")
        self._validate_import_manifest(manifest)
        return manifest

    def _public(self, manifest: dict) -> dict:
        # All paths in the manifest are relative native artifact names.
        result = _parse_json(_json_bytes(manifest))
        result.update({"id": manifest["package_id"], "kind": "vslam_native",
                       "format": "native-slam-package", "manageable": True,
                       "size_bytes": sum(item["size_bytes"] for item in manifest["native_artifacts"]),
                       "navigation_eligible": False,
                       "navigation_reason": "VALIDATED_NAVIGATION_ALIGNMENT_REQUIRED",
                       "compatibility": {"status": "blocked", "code": "MAP_INCOMPATIBLE",
                                         "reason": "Runtime compatibility has not been checked."}})
        return result

    @_path_safe
    def list_packages(self) -> list[dict]:
        with self._lock:
            packages = []
            for path in sorted(self._packages.iterdir()):
                if ID_RE.fullmatch(path.name) and path.is_dir() and not path.is_symlink():
                    try:
                        packages.append(self._public(self._manifest(path.name)))
                    except MapPackageError:
                        # Invalid/corrupt entries are never represented as valid maps.
                        continue
            return packages

    @_path_safe
    def get_package(self, package_id: str) -> dict:
        with self._lock:
            return self._public(self._manifest(package_id))

    @_path_safe
    def get_preview(self, package_id: str, *, expected_revision: str | None = None) -> Any:
        with self._lock:
            manifest = self._manifest(package_id)
            if expected_revision is not None:
                self._expected(manifest, expected_revision)
            if manifest["preview_revision"] is None:
                _fail("PREVIEW_UNAVAILABLE", "Native map preview is unavailable.")
            raw = self._read_regular(self._path(package_id) / "preview" / "snapshot.json",
                                     self.max_preview_bytes)
            if hashlib.sha256(raw).hexdigest() != manifest["preview_revision"]:
                _fail("INVALID_PACKAGE", "Native map preview failed integrity validation.")
            return _parse_json(raw)

    @staticmethod
    def _expected(manifest: dict, revision: str) -> None:
        if not isinstance(revision, str) or revision != manifest["revision"]:
            _fail("REVISION_CONFLICT", "Native map package revision changed.")

    def _not_referenced(self, package_id: str) -> None:
        if any(item[0] == package_id for item in self._references.values()):
            _fail("PACKAGE_IN_USE", "Native map package is referenced by an active operation.")

    @_path_safe
    def acquire_reference(self, package_id: str, *, expected_revision: str,
                          purpose: str = "active_session") -> str:
        """Use for active sessions, saves, localizations, and linked navigation maps."""
        with self._lock:
            self._expected(self._manifest(package_id), expected_revision)
            token = uuid.uuid4().hex
            self._references[token] = (package_id, purpose)
            return token

    def release_reference(self, reference_token: str) -> None:
        with self._lock:
            self._references.pop(reference_token, None)

    @_path_safe
    def rename_package(self, package_id: str, *, name: str, expected_revision: str) -> dict:
        with self._lock:
            manifest = self._manifest(package_id)
            self._expected(manifest, expected_revision)
            self._not_referenced(package_id)
            normalized = self._metadata({**manifest, "name": name})
            manifest["name"] = normalized["name"]
            manifest["metadata_generation"] += 1
            manifest["revision"] = self._revision(manifest)
            path = self._path(package_id)
            temporary = path / ("manifest_" + uuid.uuid4().hex + ".tmp")
            try:
                _write_private(temporary, _json_bytes(manifest))
                os.replace(temporary, path / "manifest.json")
            finally:
                temporary.unlink(missing_ok=True)
            return self._public(manifest)

    def _verify_native(self, package_id: str, manifest: dict) -> dict:
        native = self._path(package_id) / "native"
        signatures = self._scan(native)
        expected = {item["path"]: item for item in manifest["native_artifacts"]}
        if set(signatures) != set(expected):
            _fail("INVALID_PACKAGE", "Native artifacts differ from the package manifest.")
        for name, signature in signatures.items():
            item = expected[name]
            if signature[1] != item["size_bytes"]:
                _fail("INVALID_PACKAGE", "Native artifact size failed validation.")
            descriptor = os.open(native / name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as handle:
                digest = hashlib.sha256()
                for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
                    digest.update(chunk)
                if digest.hexdigest() != item["sha256"]:
                    _fail("INVALID_PACKAGE", "Native artifact hash failed validation.")
        if self._scan(native) != signatures:
            _fail("INVALID_PACKAGE", "Native artifacts changed during verification.")
        return signatures

    @_path_safe
    def copy_package(self, package_id: str, *, expected_revision: str,
                     name: str | None = None) -> dict:
        with self._lock:
            manifest = self._manifest(package_id)
            self._expected(manifest, expected_revision)
            signatures = self._verify_native(package_id, manifest)
            staging = self.create_staging()
            try:
                self._copy_native(self._path(package_id) / "native", staging.native_path, signatures)
                metadata = self._metadata({**manifest, "name": name or manifest["name"]})
                preview = self.get_preview(package_id) if manifest["preview_revision"] else None
                return self._publish(staging, metadata, self._scan(staging.native_path), preview,
                                     manifest["preview_consistency"], "verified_package_copy",
                                     derived_from={"package_id": package_id,
                                                   "revision": manifest["revision"]})
            finally:
                if staging.token in self._staging:
                    self.discard_staging(staging.token)

    @_path_safe
    def delete_package(self, package_id: str, *, expected_revision: str) -> dict:
        with self._lock:
            manifest = self._manifest(package_id)
            self._expected(manifest, expected_revision)
            self._not_referenced(package_id)
            # Remove catalog identity first; a cleanup error never leaves a partial live map.
            tombstone = self._staging_root / ("delete_" + uuid.uuid4().hex)
            os.replace(self._path(package_id), tombstone)
            try:
                shutil.rmtree(tombstone)
            except OSError:
                return {"id": package_id, "deleted": True, "cleanup": "pending"}
            return {"id": package_id, "deleted": True, "cleanup": "complete"}

    @_path_safe
    def compatibility(self, package_id: str, *, runtime: Mapping[str, Any]) -> dict:
        with self._lock:
            manifest = self._manifest(package_id)
            if not isinstance(runtime, Mapping):
                _fail("MAP_INCOMPATIBLE", "Installed runtime compatibility is unknown.")
            fields = ("engine_id", "engine_version", "native_format_version",
                      "calibration_hash", "sensor_config_hash")
            reasons = []
            for field in fields:
                recorded, installed = manifest.get(field), runtime.get(field)
                unknown = {"unknown", "unavailable", "unverified", "unsupported", "none"}
                if (not isinstance(recorded, str) or not isinstance(installed, str) or
                        not recorded or not installed or recorded.lower() in unknown or
                        installed.lower() in unknown or
                        (field.endswith("_hash") and (not HASH_RE.fullmatch(recorded) or
                                                      not HASH_RE.fullmatch(installed)))):
                    reasons.append(field + "_unknown")
                elif recorded != installed:
                    reasons.append(field + "_mismatch")
            return {"status": "blocked" if reasons else "compatible",
                    "code": "MAP_INCOMPATIBLE" if reasons else None,
                    "reasons": reasons, "native_load_validated": False,
                    "localization_validated": False}

    @_path_safe
    def prepare_load(self, package_id: str, *, expected_revision: str,
                     runtime: Mapping[str, Any]) -> NativeLoadScratch:
        """Compatibility-gated scratch native copy; never supplies an initial pose."""
        with self._lock:
            manifest = self._manifest(package_id)
            self._expected(manifest, expected_revision)
            if self.compatibility(package_id, runtime=runtime)["status"] != "compatible":
                _fail("MAP_INCOMPATIBLE", "Native map is incompatible or compatibility is unknown.")
            signatures = self._verify_native(package_id, manifest)
            scratch_id = uuid.uuid4().hex
            workspace = _private_dir(self._scratch_root / scratch_id)
            native = _private_dir(workspace / "native")
            reference = self.acquire_reference(package_id, expected_revision=expected_revision,
                                               purpose="localize_saved")
            try:
                self._copy_native(self._path(package_id) / "native", native, signatures)
            except BaseException:
                self.release_reference(reference)
                shutil.rmtree(native.parent)
                raise
            scratch = NativeLoadScratch(scratch_id, native, package_id, expected_revision, reference)
            self._scratch[scratch_id] = scratch
            return scratch

    @_path_safe
    def release_scratch(self, scratch_id: str) -> None:
        """Call only after the adapter has finished using its scratch writer."""
        with self._lock:
            scratch = self._scratch.pop(scratch_id, None)
            if scratch is None:
                _fail("SCRATCH_NOT_FOUND", "Native map scratch is unavailable.")
            shutil.rmtree(scratch.native_path.parent)
            self.release_reference(scratch.reference_token)

    @_path_safe
    def export_package(self, package_id: str, *, expected_revision: str) -> tuple[BinaryIO, dict]:
        """Private spooled archive; caller closes the returned binary handle."""
        with self._lock:
            manifest = self._manifest(package_id)
            self._expected(manifest, expected_revision)
            signatures = self._verify_native(package_id, manifest)
            if sum(item[1] for item in signatures.values()) > self.max_archive_bytes:
                _fail("PACKAGE_LIMIT", "Export archive exceeds configured limits.")
            output = tempfile.TemporaryFile(mode="w+b", dir=self._staging_root)
            try:
                os.fchmod(output.fileno(), 0o600)
                with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
                    def add(name: str, payload: bytes) -> None:
                        info = zipfile.ZipInfo(name)
                        info.create_system = 3
                        info.external_attr = (stat.S_IFREG | 0o600) << 16
                        archive.writestr(info, payload)
                    add("manifest.json", _json_bytes(manifest))
                    for name in sorted(signatures):
                        info = zipfile.ZipInfo("native/" + name)
                        info.create_system = 3
                        info.external_attr = (stat.S_IFREG | 0o600) << 16
                        with archive.open(info, "w", force_zip64=True) as writer:
                            with (self._path(package_id) / "native" / name).open("rb") as reader:
                                shutil.copyfileobj(reader, writer, CHUNK_BYTES)
                    if manifest["preview_revision"]:
                        add("preview/snapshot.json", _json_bytes(self.get_preview(package_id)))
                if self._scan(self._path(package_id) / "native") != signatures:
                    _fail("INVALID_PACKAGE", "Native map changed during export.")
                size = output.tell()
                if size > self.max_archive_bytes:
                    _fail("PACKAGE_LIMIT", "Export archive exceeds configured limits.")
                output.seek(0)
                return output, {"id": package_id, "revision": manifest["revision"],
                                "filename": "robot-scope-native-" + package_id + ".zip",
                                "bytes": size}
            except BaseException:
                output.close()
                raise

    @_path_safe
    def export_preview(self, package_id: str, *, expected_revision: str) -> tuple[BinaryIO, dict]:
        """Derived XYZ/CSV/provenance from one hash-verified saved preview only."""
        with self._lock:
            manifest = self._manifest(package_id)
            self._expected(manifest, expected_revision)
            preview = self.get_preview(package_id, expected_revision=expected_revision)
            try:
                files = preview_export_files(manifest, preview, max_bytes=self.max_archive_bytes)
            except PreviewExportError as exc:
                _fail(str(exc), "Saved preview cannot be exported under the declared bounds.")
            output = tempfile.TemporaryFile(mode="w+b", dir=self._staging_root)
            try:
                os.fchmod(output.fileno(), 0o600)
                with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
                    for name, payload in files.items():
                        info = zipfile.ZipInfo(name)
                        info.create_system = 3
                        info.external_attr = (stat.S_IFREG | 0o600) << 16
                        archive.writestr(info, payload)
                size = output.tell()
                if size > min(self.max_archive_bytes, MAX_EXPORT_BYTES):
                    _fail("PACKAGE_LIMIT", "Preview export exceeds configured limits.")
                output.seek(0)
                return output, {"id": package_id, "revision": manifest["revision"],
                                "filename": package_id + "-preview.zip", "bytes": size}
            except BaseException:
                output.close()
                raise

    @_path_safe
    def import_package(self, source: bytes | BinaryIO, *, name: str | None = None) -> dict:
        """Validate a bounded ZIP in isolation; importing never starts a runtime."""
        with self._lock:
            if isinstance(source, bytes):
                raw = source
            elif hasattr(source, "read"):
                raw = source.read(self.max_archive_bytes + 1)
            else:
                _fail("INVALID_PACKAGE", "Import requires archive bytes or a binary stream.")
            if not isinstance(raw, bytes) or len(raw) > self.max_archive_bytes:
                _fail("PACKAGE_LIMIT", "Import archive exceeds configured limits.")
            _bounded_zip_directory(raw, self.max_files + 2)
            staging = self.create_staging()
            try:
                try:
                    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                        infos = archive.infolist()
                        if len(infos) > self.max_files + 2:
                            _fail("PACKAGE_LIMIT", "Import archive contains too many files.")
                        names = set()
                        total = 0
                        for info in infos:
                            relative = _relative(info.filename)
                            _safe_zip_extra(info.extra)
                            kind = stat.S_IFMT(info.external_attr >> 16)
                            if (info.is_dir() or kind not in {0, stat.S_IFREG} or
                                    relative in names or info.flag_bits & 1 or
                                    info.filename != info.orig_filename):
                                _fail("UNSAFE_ARCHIVE", "Archive has linked, special, duplicate or encrypted entries.")
                            # Restrict decoder memory/CPU behavior to formats we
                            # export and ordinary bounded DEFLATE uploads.
                            if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                                _fail("UNSAFE_ARCHIVE", "Archive compression method is unsupported.")
                            names.add(relative)
                            if relative not in {"manifest.json", "preview/snapshot.json"} and not relative.startswith("native/"):
                                _fail("UNSAFE_ARCHIVE", "Archive has an unsupported artifact.")
                            limit = (self.max_manifest_bytes if relative == "manifest.json" else
                                     self.max_preview_bytes if relative == "preview/snapshot.json" else
                                     self.max_native_bytes)
                            total += info.file_size
                            if (info.file_size > limit or total > self.max_native_bytes + self.max_preview_bytes + self.max_manifest_bytes or
                                    info.file_size / max(1, info.compress_size) > self.max_compression_ratio):
                                _fail("PACKAGE_LIMIT", "Archive exceeds expansion limits.")
                        if "manifest.json" not in names:
                            _fail("INVALID_PACKAGE", "Import has no package manifest.")
                        manifest = _parse_json(archive.read("manifest.json"))
                        self._validate_import_manifest(manifest)
                        expected = {"native/" + item["path"] for item in manifest["native_artifacts"]}
                        if manifest["preview_revision"] is not None:
                            expected.add("preview/snapshot.json")
                        if names != expected | {"manifest.json"}:
                            _fail("INVALID_PACKAGE", "Import artifacts do not match the manifest.")
                        metadata = self._metadata({**manifest, "name": name or manifest["name"]})
                        for item in manifest["native_artifacts"]:
                            path = staging.native_path / item["path"]
                            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                            digest = hashlib.sha256()
                            count = 0
                            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                            with os.fdopen(descriptor, "wb") as writer, archive.open("native/" + item["path"]) as reader:
                                while True:
                                    chunk = reader.read(CHUNK_BYTES)
                                    if not chunk:
                                        break
                                    count += len(chunk)
                                    if count > item["size_bytes"] or count > self.max_native_bytes:
                                        _fail("PACKAGE_LIMIT", "Import artifact exceeds declared size.")
                                    digest.update(chunk)
                                    writer.write(chunk)
                            if count != item["size_bytes"] or digest.hexdigest() != item["sha256"]:
                                _fail("INVALID_PACKAGE", "Import native artifact failed integrity validation.")
                        preview = None
                        if manifest["preview_revision"]:
                            preview_raw = archive.read("preview/snapshot.json")
                            if hashlib.sha256(preview_raw).hexdigest() != manifest["preview_revision"]:
                                _fail("INVALID_PACKAGE", "Import preview failed integrity validation.")
                            preview = _parse_json(preview_raw)
                        return self._publish(staging, metadata, self._scan(staging.native_path), preview,
                                             manifest["preview_consistency"], "imported_manifest_integrity_only",
                                             derived_from={"package_id": manifest["package_id"],
                                                           "revision": manifest["revision"]})
                except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, EOFError):
                    _fail("INVALID_PACKAGE", "Import archive is invalid or unsupported.")
            finally:
                if staging.token in self._staging:
                    self.discard_staging(staging.token)

    def _validate_import_manifest(self, manifest: Any) -> None:
        if (not isinstance(manifest, dict) or manifest.get("metadata_schema") != SCHEMA or
                not isinstance(manifest.get("package_id"), str) or
                not ID_RE.fullmatch(manifest["package_id"]) or
                manifest.get("revision") != self._revision(manifest) or
                not isinstance(manifest.get("save_completion"), dict) or
                manifest["save_completion"].get("status") != "completed"):
            _fail("INVALID_PACKAGE", "Import package manifest failed validation.")
        required_keys = {"name", "engine_id", "created_at", "metadata_generation",
                         "preview_revision", "preview_consistency", "native_content_revision"}
        if (not required_keys.issubset(manifest) or
                isinstance(manifest.get("metadata_generation"), bool) or
                not isinstance(manifest.get("metadata_generation"), int) or
                manifest["metadata_generation"] <= 0 or
                not isinstance(manifest.get("created_at"), str)):
            _fail("INVALID_PACKAGE", "Import package metadata is incomplete.")
        # Archive hashes detect corruption, not authenticity. Validate metadata
        # even when an untrusted author has recomputed every declared hash.
        self._metadata(manifest)
        artifacts = manifest.get("native_artifacts")
        if not isinstance(artifacts, list) or not artifacts or len(artifacts) > self.max_files:
            _fail("INVALID_PACKAGE", "Import native artifact manifest is invalid.")
        names = set()
        total = 0
        for item in artifacts:
            if not isinstance(item, dict) or set(item) != {"path", "size_bytes", "sha256"}:
                _fail("INVALID_PACKAGE", "Import native artifact entry is invalid.")
            relative = _relative(item["path"])
            size = item["size_bytes"]
            if (relative in names or isinstance(size, bool) or not isinstance(size, int) or size < 0 or
                    not isinstance(item["sha256"], str) or not HASH_RE.fullmatch(item["sha256"])):
                _fail("INVALID_PACKAGE", "Import native artifact entry is invalid.")
            names.add(relative)
            total += size
            if total > self.max_native_bytes:
                _fail("PACKAGE_LIMIT", "Import native artifacts exceed configured limits.")
        if hashlib.sha256(_json_bytes(artifacts)).hexdigest() != manifest.get("native_content_revision"):
            _fail("INVALID_PACKAGE", "Import native content revision failed validation.")
        preview_revision = manifest.get("preview_revision")
        if preview_revision is not None and (not isinstance(preview_revision, str) or
                                              not HASH_RE.fullmatch(preview_revision)):
            _fail("INVALID_PACKAGE", "Import preview revision is invalid.")
        if manifest.get("preview_consistency") not in {"exact", "approximate", "unavailable"}:
            _fail("INVALID_PACKAGE", "Import preview consistency is invalid.")
