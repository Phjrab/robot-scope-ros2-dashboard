"""Private, immutable PCD copy registry, independent of Maps and robot runtime.

Only a trusted resolver supplies filesystem paths. Requests describe regions,
never point arrays, preview assets or paths. A complete hidden staging directory
is renamed into the registry under a process-shared lock as the commit point.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any, Callable
import uuid

from .geometry import PcdEditError, validate_regions
from .pcd import filter_pcd

REQUEST_SCHEMA = "robot-scope.pcd-edit-request.v1"
MANIFEST_SCHEMA = "robot-scope.pcd-edited-map.v1"
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_HISTORY = 1000
DEFAULT_MAX_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_POINTS = 20_000_000
_ID = re.compile(r"[0-9a-f]{24}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_SOURCE_KEYS = {"map_id", "revision", "sha256", "frame_id", "units", "asset_role"}


class PcdEditConflict(PcdEditError):
    """A pinned source changed or an immutable output already exists."""


@dataclass(frozen=True)
class SourceAsset:
    """Server-only full original reference; never deserialize this from HTTP."""

    map_id: str
    revision: str
    path: Path
    frame_id: str
    units: str = "m"
    asset_role: str = "full_source"
    origin: dict[str, Any] | None = None
    edit_history: tuple[dict[str, Any], ...] = ()


def _canonical(value: Any) -> bytes:
    try:
        data = json.dumps(value, ensure_ascii=False, allow_nan=False,
                          sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise PcdEditError("edit document must be finite JSON") from exc
    if len(data) > MAX_DOCUMENT_BYTES:
        raise PcdEditError("edit document exceeds the 2 MiB limit")
    return data


def _keys(value: Any, keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise PcdEditError(f"{label} has invalid fields")


def _text(value: Any, label: str, limit: int = 128) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise PcdEditError(f"{label} is invalid")
    return value


def _hex(value: Any, pattern: re.Pattern, label: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise PcdEditError(f"{label} is invalid")
    return value


def _source(value: Any) -> dict[str, Any]:
    _keys(value, _SOURCE_KEYS, "full source")
    _hex(value["map_id"], _ID, "source map ID")
    _hex(value["revision"], _HASH, "source revision")
    _hex(value["sha256"], _HASH, "source SHA-256")
    _text(value["frame_id"], "source frame")
    if value["units"] != "m" or value["asset_role"] != "full_source":
        raise PcdEditError("editing requires a full original PCD in metres")
    return copy.deepcopy(value)


def _annotation(value: Any) -> dict[str, Any]:
    _keys(value, {"schema", "schema_version", "version_id", "source",
                  "runtime_installed", "regions"}, "annotation")
    if (value["schema"] != "robot-dashboard.map-editor3d"
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or value["runtime_installed"] is not False):
        raise PcdEditError("unsupported annotation version or runtime installation")
    _text(value["version_id"], "annotation version ID", 128)
    _keys(value["source"], {"map_id", "revision", "frame_id"}, "annotation source")
    _hex(value["source"]["map_id"], _ID, "annotation map ID")
    _hex(value["source"]["revision"], _HASH, "annotation revision")
    _text(value["source"]["frame_id"], "annotation frame")
    return {**copy.deepcopy(value), "regions": validate_regions(value["regions"])}


def validate_request(value: Any) -> dict[str, Any]:
    """Strict wire contract; point buffers, paths and preview hints are rejected."""
    _canonical(value)
    _keys(value, {"schema", "name", "purpose", "source", "annotation"}, "edit request")
    if value["schema"] != REQUEST_SCHEMA:
        raise PcdEditError("unsupported PCD edit request schema")
    if not isinstance(value["name"], str) or not _NAME.fullmatch(value["name"]):
        raise PcdEditError("name requires 1-64 ASCII letters, numbers, underscores or hyphens")
    if value["purpose"] not in ("visibility", "localization"):
        raise PcdEditError("copy purpose must be visibility or localization")
    source = _source(value["source"])
    annotation = _annotation(value["annotation"])
    if annotation["source"] != {key: source[key] for key in ("map_id", "revision", "frame_id")}:
        raise PcdEditConflict("annotation does not identify this full original")
    return {**copy.deepcopy(value), "source": source, "annotation": annotation}


def _safe_path(path: Path) -> Path:
    path = Path(path).absolute()
    for component in (path, *path.parents):
        if component.is_symlink():
            raise PcdEditError("symlinks are not allowed for PCD editing assets")
    return path


def _open_regular(path: Path, limit: int):
    path = _safe_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        current = os.fstat(fd)
        if not stat.S_ISREG(current.st_mode) or not 0 < current.st_size <= limit:
            raise PcdEditError("PCD editing asset is not a bounded regular file")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def _signature(current: os.stat_result) -> tuple[int, ...]:
    return (current.st_dev, current.st_ino, current.st_size,
            current.st_mtime_ns, current.st_ctime_ns)


def _digest(path: Path, limit: int = DEFAULT_MAX_BYTES, *,
            expected_signature: tuple[int, ...] | None = None) -> str:
    digest = hashlib.sha256()
    with _open_regular(path, limit) as stream:
        before = _signature(os.fstat(stream.fileno()))
        if expected_signature is not None and before != expected_signature:
            raise PcdEditConflict("source file identity changed before registration")
        total = 0
        while block := stream.read(1024 * 1024):
            total += len(block)
            if total > limit:
                raise PcdEditError("PCD editing asset exceeds the byte limit")
            digest.update(block)
        if before != _signature(os.fstat(stream.fileno())):
            raise PcdEditConflict("source changed during reading")
    return digest.hexdigest()


def _revision(metadata: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical({key: value for key, value in metadata.items()
                                      if key != "revision"})).hexdigest()


def _validate_manifest(value: Any) -> dict[str, Any]:
    _keys(value, {"schema", "id", "name", "kind", "format", "file_name", "manageable",
                  "revision", "frame_id", "units", "sha256", "point_count", "source",
                  "origin", "edit_history", "created_at", "runtime_installed", "asset_role"},
          "PCD manifest")
    _hex(value["id"], _ID, "map ID")
    _hex(value["sha256"], _HASH, "output SHA-256")
    _hex(value["revision"], _HASH, "map revision")
    if (value["schema"] != MANIFEST_SCHEMA or value["kind"] != "pointcloud3d"
            or value["format"] != "pcd-binary" or value["file_name"] != "map.pcd"
            or value["manageable"] is not False or value["runtime_installed"] is not False
            or value["asset_role"] != "full_source" or value["units"] != "m"):
        raise PcdEditError("unsupported immutable PCD manifest")
    if not isinstance(value["name"], str) or not _NAME.fullmatch(value["name"]):
        raise PcdEditError("manifest name is invalid")
    _text(value["frame_id"], "manifest frame")
    _text(value["created_at"], "manifest creation time")
    if type(value["point_count"]) is not int or value["point_count"] <= 0:
        raise PcdEditError("manifest point count is invalid")
    source, origin = _source(value["source"]), _source(value["origin"])
    if any(source[key] != value[key] or origin[key] != value[key]
           for key in ("frame_id", "units")):
        raise PcdEditError("manifest coordinate system is inconsistent")
    history = value["edit_history"]
    if not isinstance(history, list) or not 1 <= len(history) <= MAX_HISTORY:
        raise PcdEditError("manifest edit history is invalid")
    for entry in history:
        _keys(entry, {"purpose", "annotation", "applied_at", "source_sha256", "input_points",
                      "output_points", "removed_points", "nonfinite_points_preserved"}, "edit history")
        if entry["purpose"] not in ("visibility", "localization"):
            raise PcdEditError("manifest edit purpose is invalid")
        _annotation(entry["annotation"])
        _text(entry["applied_at"], "edit time")
        _hex(entry["source_sha256"], _HASH, "history source hash")
        for key in ("input_points", "output_points", "removed_points", "nonfinite_points_preserved"):
            if type(entry[key]) is not int or entry[key] < 0:
                raise PcdEditError("history point counts are invalid")
        if (entry["input_points"] != entry["output_points"] + entry["removed_points"]
                or entry["nonfinite_points_preserved"] > entry["output_points"]):
            raise PcdEditError("history point counts are inconsistent")
    first = history[0]
    if (first["source_sha256"] != origin["sha256"]
            or first["annotation"]["source"] != {
                key: origin[key] for key in ("map_id", "revision", "frame_id")}):
        raise PcdEditError("history does not match the original root source")
    for previous, following in zip(history, history[1:]):
        if previous["output_points"] != following["input_points"]:
            raise PcdEditError("history point counts do not connect across revisions")
    last = history[-1]
    if (last["output_points"] != value["point_count"] or last["source_sha256"] != source["sha256"]
            or last["annotation"]["source"] != {key: source[key] for key in ("map_id", "revision", "frame_id")}):
        raise PcdEditError("history does not match the manifest source")
    if value["revision"] != _revision(value):
        raise PcdEditError("manifest revision does not match its content")
    return copy.deepcopy(value)


@contextmanager
def _registry_lock(root: Path, mode: int, *, create: bool = False):
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    if create:
        flags |= os.O_CREAT
    fd = os.open(root / ".store.lock", flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise PcdEditError("registry lock must be a regular file")
        with os.fdopen(fd, "r+b", closefd=False) as lock:
            fcntl.flock(lock.fileno(), mode)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _read_manifest(directory: Path, verify_pcd: bool) -> dict[str, Any]:
    directory = _safe_path(directory)
    with _open_regular(directory / "manifest.json", MAX_DOCUMENT_BYTES) as stream:
        try:
            value = json.loads(stream.read(MAX_DOCUMENT_BYTES + 1))
        except (ValueError, UnicodeError) as exc:
            raise PcdEditError("invalid PCD manifest JSON") from exc
    metadata = _validate_manifest(value)
    if directory.name != metadata["id"]:
        raise PcdEditError("manifest directory does not match map ID")
    if verify_pcd and _digest(directory / "map.pcd") != metadata["sha256"]:
        raise PcdEditError("registered PCD hash differs from its manifest")
    return metadata


def read_manifest(directory: Path, *, verify_pcd: bool = True) -> dict[str, Any]:
    """Read a committed copy under the registry read lock; expose no paths."""
    directory = _safe_path(directory)
    with _registry_lock(directory.parent, fcntl.LOCK_SH):
        return _read_manifest(directory, verify_pcd)


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class PcdEditStore:
    """Atomic on-disk registration for newly derived PCDs only.

    The directory is private service-owned storage. Local processes writing to
    it must use this store's lock. Publication never updates a selected map.
    """

    def __init__(self, root: Path, source_resolver: Callable[[str], SourceAsset], *,
                 max_bytes: int = DEFAULT_MAX_BYTES, max_points: int = DEFAULT_MAX_POINTS,
                 chunk_points: int = 65536):
        self.root = _safe_path(root)
        if self.root.exists() and not self.root.is_dir():
            raise PcdEditError("PCD edit root must be a directory")
        self.source_resolver = source_resolver
        if any(type(value) is not int or value <= 0 for value in (max_bytes, max_points, chunk_points)):
            raise PcdEditError("PCD edit resource limits must be positive integers")
        if max_bytes > DEFAULT_MAX_BYTES:
            raise PcdEditError("PCD edit byte limit cannot exceed 256 MiB")
        self.max_bytes, self.max_points, self.chunk_points = max_bytes, max_points, chunk_points

    def _resolve(self, map_id: str) -> SourceAsset:
        _hex(map_id, _ID, "source map ID")
        asset = self.source_resolver(map_id)
        if not isinstance(asset, SourceAsset) or asset.map_id != map_id:
            raise PcdEditError("resolver did not return the requested full source")
        _source({"map_id": asset.map_id, "revision": asset.revision, "sha256": "0" * 64,
                 "frame_id": asset.frame_id, "units": asset.units, "asset_role": asset.asset_role})
        return asset

    def descriptor(self, map_id: str) -> dict[str, Any]:
        asset = self._resolve(map_id)
        result = {"map_id": asset.map_id, "revision": asset.revision,
                  "sha256": _digest(asset.path, self.max_bytes), "frame_id": asset.frame_id,
                  "units": asset.units, "asset_role": asset.asset_role}
        if self._resolve(map_id) != asset:
            raise PcdEditConflict("source identity changed; load it again")
        return result

    def get(self, map_id: str) -> dict[str, Any]:
        _hex(map_id, _ID, "map ID")
        _safe_path(self.root)
        if not self.root.exists():
            raise FileNotFoundError("PCD edit registry does not exist")
        if not self.root.is_dir():
            raise PcdEditError("PCD edit root must be a directory")
        return read_manifest(self.root / map_id)

    def list(self) -> list[dict[str, Any]]:
        _safe_path(self.root)
        if not self.root.exists():
            return []
        if not self.root.is_dir():
            raise PcdEditError("PCD edit root must be a directory")
        registered = []
        for directory in sorted(self.root.iterdir()):
            if _ID.fullmatch(directory.name):
                try:
                    registered.append(read_manifest(directory))
                except (OSError, PcdEditError):
                    continue
        return registered

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = validate_request(payload)
        requested = request["source"]
        asset = self._resolve(requested["map_id"])
        for key in ("map_id", "revision", "frame_id", "units", "asset_role"):
            if getattr(asset, key) != requested[key]:
                raise PcdEditConflict("source identity changed; load it again")
        if len(asset.edit_history) >= MAX_HISTORY:
            raise PcdEditError("edit history limit reached")
        # A read-only descriptor or an invalid/stale request must not create a
        # registry. The first valid save initializes its private output root.
        if not self.root.exists() and _digest(asset.path, self.max_bytes) != requested["sha256"]:
            raise PcdEditConflict("source revision or hash changed; load it again")
        _safe_path(self.root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        _safe_path(self.root)
        if not self.root.is_dir():
            raise PcdEditError("PCD edit root must be a directory")
        with _registry_lock(self.root, fcntl.LOCK_EX, create=True):
            pass
        stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=self.root))
        published: Path | None = None
        try:
            snapshot = stage / ".source.pcd"
            digest = hashlib.sha256()
            with _open_regular(asset.path, self.max_bytes) as source, snapshot.open("xb") as target:
                before = _signature(os.fstat(source.fileno()))
                total = 0
                while block := source.read(1024 * 1024):
                    total += len(block)
                    if total > self.max_bytes:
                        raise PcdEditError("source exceeds the byte limit")
                    digest.update(block)
                    target.write(block)
                if before != _signature(os.fstat(source.fileno())):
                    raise PcdEditConflict("source changed while taking a snapshot")
            if digest.hexdigest() != requested["sha256"] or self._resolve(asset.map_id) != asset:
                raise PcdEditConflict("source revision or hash changed; load it again")
            result = filter_pcd(snapshot, stage / "map.pcd", request["annotation"]["regions"],
                                request["purpose"], max_bytes=self.max_bytes,
                                max_points=self.max_points, chunk_points=self.chunk_points)
            if result["source_sha256"] != requested["sha256"]:
                raise PcdEditConflict("snapshot hash does not match the requested source")
            snapshot.unlink()
            created = datetime.now(timezone.utc).isoformat()
            entry = {"purpose": request["purpose"], "annotation": request["annotation"],
                     "applied_at": created, "source_sha256": requested["sha256"],
                     "input_points": result["source_points"], "output_points": result["output_points"],
                     "removed_points": result["removed_points"],
                     "nonfinite_points_preserved": result["nonfinite_points_preserved"]}
            metadata = {"schema": MANIFEST_SCHEMA, "id": uuid.uuid4().hex[:24],
                        "name": request["name"], "kind": "pointcloud3d", "format": "pcd-binary",
                        "file_name": "map.pcd", "manageable": False, "frame_id": asset.frame_id,
                        "units": asset.units, "sha256": result["output_sha256"],
                        "point_count": result["output_points"], "source": requested,
                        "origin": copy.deepcopy(asset.origin or requested),
                        "edit_history": [*copy.deepcopy(asset.edit_history), entry],
                        "created_at": created, "runtime_installed": False, "asset_role": "full_source"}
            ancestor_ids = {requested["map_id"], metadata["origin"]["map_id"]}
            ancestor_ids.update(item["annotation"]["source"]["map_id"]
                                for item in metadata["edit_history"])
            if metadata["id"] in ancestor_ids:
                raise PcdEditConflict("output map ID collides with its source history")
            metadata["revision"] = _revision(metadata)
            _validate_manifest(metadata)
            with (stage / "manifest.json").open("xb") as manifest:
                manifest.write(_canonical(metadata))
                manifest.flush()
                os.fsync(manifest.fileno())
            with (stage / "map.pcd").open("rb") as pcd:
                os.fsync(pcd.fileno())
            _sync_directory(stage)
            # Resolver may read a parent from this registry. Call it before the
            # write lock so its read lock cannot deadlock against this writer.
            if self._resolve(asset.map_id) != asset:
                raise PcdEditConflict("source changed before registration; load it again")
            with _registry_lock(self.root, fcntl.LOCK_EX):
                if _digest(asset.path, self.max_bytes, expected_signature=before) != requested["sha256"]:
                    raise PcdEditConflict("source changed before registration; load it again")
                destination = self.root / metadata["id"]
                if os.path.lexists(destination):
                    raise PcdEditConflict("output map ID already exists")
                os.rename(stage, destination)
                published = destination
                try:
                    _sync_directory(self.root)
                except BaseException:
                    # Readers use the shared registry lock and cannot observe
                    # a registration that fails its final durability check.
                    shutil.rmtree(destination)
                    published = None
                    raise
            return copy.deepcopy(metadata)
        except BaseException:
            if published is not None:
                shutil.rmtree(published)
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)
