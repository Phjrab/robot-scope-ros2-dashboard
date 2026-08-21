"""Bounded server-side camera dataset capture.

The browser is deliberately not part of the persistence path.  This manager
holds normal camera demand tokens, samples immutable JPEG snapshots, and
publishes complete samples with same-filesystem atomic renames.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import logging
import os
import queue
import re
import shutil
import stat
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple


LOGGER = logging.getLogger(__name__)

CAMERA_SOURCE_IDS = ("go2_front", "realsense_color")
ACTIVE_STATES = {"starting", "capturing", "stopping", "finalizing"}
SESSION_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z_[0-9a-f]{32}$")
SAMPLE_DIR_RE = re.compile(r"^[0-9]{8}$")
TEMP_SAMPLE_DIR_RE = re.compile(r"^\.tmp-[0-9a-f]{32}$")
MAX_JPEG_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_SESSIONS = 2_000
DEFAULT_SAMPLES_PER_PAGE = 24
MAX_SAMPLES_PER_DETAIL = 48


class DatasetCaptureError(RuntimeError):
    """Base error for the fixed dataset capture surface."""


class DatasetCaptureBusy(DatasetCaptureError):
    pass


class DatasetCaptureNotFound(DatasetCaptureError):
    pass


class DatasetCaptureUnavailable(DatasetCaptureError):
    pass


class DatasetCaptureValidationError(DatasetCaptureError):
    pass


class DatasetCaptureConflict(DatasetCaptureError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if result == result and abs(result) != float("inf") else default
    except (TypeError, ValueError, OverflowError):
        return default


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _reject_symlink_components(path: Path) -> None:
    """Reject an existing symlink anywhere in an absolute configured path."""

    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            # Descendants cannot exist until this missing parent is created.
            break
        except OSError as exc:
            raise DatasetCaptureValidationError(
                f"cannot inspect dataset output path: {exc}"
            ) from exc
        if stat.S_ISLNK(info.st_mode):
            raise DatasetCaptureValidationError(
                "dataset output path cannot contain symlinks"
            )


class DatasetCaptureManager:
    """Own one bounded dataset session at a time."""

    def __init__(
        self,
        output_dir: Path,
        *,
        camera_open: Callable[[str], Dict[str, Any]],
        camera_close: Callable[[str, str], Dict[str, Any]],
        camera_snapshots: Callable[[Tuple[str, ...]], Dict[str, Dict[str, Any]]],
        metadata_snapshot: Optional[Callable[[], Dict[str, Any]]] = None,
        queue_size: int = 8,
        startup_timeout_s: float = 10.0,
        stale_after_s: float = 2.0,
        pair_skew_us: int = 250_000,
        session_quota_bytes: int = 20 * 1024 * 1024 * 1024,
        minimum_free_bytes: int = 5 * 1024 * 1024 * 1024,
    ) -> None:
        requested = Path(output_dir).expanduser()
        if not requested.is_absolute():
            raise DatasetCaptureValidationError(
                "dataset output directory must be an absolute non-root path"
            )
        try:
            normalized = requested.resolve(strict=False)
        except OSError as exc:
            raise DatasetCaptureValidationError(
                f"cannot normalize dataset output directory: {exc}"
            ) from exc
        if normalized == Path("/"):
            raise DatasetCaptureValidationError(
                "dataset output directory must be an absolute non-root path"
            )
        _reject_symlink_components(requested)
        requested.mkdir(parents=True, exist_ok=True, mode=0o700)
        _reject_symlink_components(requested)
        if not requested.is_dir():
            raise DatasetCaptureValidationError("dataset output directory must be a real directory")
        self.root = requested.resolve(strict=True)
        if self.root == Path("/"):
            raise DatasetCaptureValidationError(
                "dataset output directory must be an absolute non-root path"
            )
        try:
            self.root.chmod(0o700)
        except OSError as exc:
            raise DatasetCaptureUnavailable(f"cannot secure dataset output directory: {exc}") from exc
        self.sessions_dir = self.root / "sessions"
        self.sessions_dir.mkdir(mode=0o700, exist_ok=True)
        if self.sessions_dir.is_symlink() or not self.sessions_dir.is_dir():
            raise DatasetCaptureValidationError("dataset sessions directory must be real")
        self.sessions_dir.chmod(0o700)

        if queue_size < 1 or queue_size > 32:
            raise DatasetCaptureValidationError("dataset writer queue size is invalid")
        if startup_timeout_s <= 0 or stale_after_s <= 0 or pair_skew_us <= 0:
            raise DatasetCaptureValidationError("dataset timing limits are invalid")
        if session_quota_bytes < MAX_MANIFEST_BYTES or minimum_free_bytes < 0:
            raise DatasetCaptureValidationError("dataset storage limits are invalid")

        self._camera_open = camera_open
        self._camera_close = camera_close
        self._camera_snapshots = camera_snapshots
        self._metadata_snapshot = metadata_snapshot
        self._queue_size = queue_size
        self._startup_timeout_s = startup_timeout_s
        self._stale_after_s = stale_after_s
        self._pair_skew_us = pair_skew_us
        self._session_quota_bytes = session_quota_bytes
        self._minimum_free_bytes = minimum_free_bytes

        self._lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._state = "idle"
        self._session_id = ""
        self._session_dir: Optional[Path] = None
        self._sources: Tuple[str, ...] = ()
        self._capture_hz = 0.0
        self._label = ""
        self._started_at = ""
        self._completed_at = ""
        self._started_monotonic = 0.0
        self._terminal_elapsed_s = 0.0
        self._saved = 0
        self._dropped: Dict[str, int] = {}
        self._bytes_written = 0
        self._last_error = ""
        self._message = "ready"
        self._tokens: Dict[str, str] = {}
        self._last_frame_keys: Dict[str, Tuple[str, int]] = {}
        self._stop_event = threading.Event()
        self._writer_done_event = threading.Event()
        self._sample_queue: queue.Queue[Optional[Dict[str, Any]]] = queue.Queue(maxsize=queue_size)
        self._sampler_thread: Optional[threading.Thread] = None
        self._writer_thread: Optional[threading.Thread] = None
        self._recover_interrupted_sessions()

    @staticmethod
    def _validate_sources(sources: Tuple[str, ...]) -> Tuple[str, ...]:
        if (
            not isinstance(sources, tuple)
            or not sources
            or len(sources) > len(CAMERA_SOURCE_IDS)
            or len(set(sources)) != len(sources)
            or any(source not in CAMERA_SOURCE_IDS for source in sources)
        ):
            raise DatasetCaptureValidationError("camera sources are not allowlisted")
        return tuple(source for source in CAMERA_SOURCE_IDS if source in sources)

    @staticmethod
    def _validate_label(label: str) -> str:
        if not isinstance(label, str):
            raise DatasetCaptureValidationError("dataset label must be text")
        clean = label.strip()
        if len(clean) > 64 or any(ord(character) < 32 for character in clean):
            raise DatasetCaptureValidationError("dataset label is invalid")
        return clean

    @staticmethod
    def _validate_session_id(session_id: str) -> str:
        if not isinstance(session_id, str) or not SESSION_ID_RE.fullmatch(session_id):
            raise DatasetCaptureNotFound("dataset session was not found")
        return session_id

    def _session_path(self, session_id: str) -> Path:
        session_id = self._validate_session_id(session_id)
        candidate = self.sessions_dir / session_id
        if candidate.is_symlink() or not candidate.is_dir():
            raise DatasetCaptureNotFound("dataset session was not found")
        resolved = candidate.resolve(strict=True)
        if resolved.parent != self.sessions_dir.resolve(strict=True):
            raise DatasetCaptureNotFound("dataset session was not found")
        return resolved

    def _free_bytes(self) -> int:
        try:
            return int(shutil.disk_usage(self.root).free)
        except OSError:
            return 0

    def _snapshot_locked(self) -> Dict[str, Any]:
        workers_alive = self._workers_alive_locked()
        elapsed = self._terminal_elapsed_s
        if self._started_monotonic and (self._state in ACTIVE_STATES or workers_alive):
            elapsed = max(0.0, time.monotonic() - self._started_monotonic)
        dropped_total = sum(self._dropped.values())
        return {
            "available": True,
            "state": self._state,
            "active": self._state in ACTIVE_STATES or workers_alive,
            "session_id": self._session_id,
            "sources": list(self._sources),
            "capture_hz": self._capture_hz,
            "label": self._label,
            "started_at": self._started_at,
            "completed_at": self._completed_at,
            "elapsed_s": round(elapsed, 3),
            "saved": self._saved,
            "saved_samples": self._saved,
            "sample_count": self._saved,
            "dropped": dropped_total,
            "dropped_samples": dropped_total,
            "drop_counts": dict(self._dropped),
            "bytes_written": self._bytes_written,
            "free_bytes": self._free_bytes(),
            "session_quota_bytes": self._session_quota_bytes,
            "minimum_free_bytes": self._minimum_free_bytes,
            "output_path": str(self._session_dir or self.root),
            "message": self._message,
            "last_error": self._last_error,
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def _workers_alive_locked(self) -> bool:
        return any(
            worker is not None and worker.is_alive()
            for worker in (self._sampler_thread, self._writer_thread)
        )

    def is_active(self) -> bool:
        with self._lock:
            return self._state in ACTIVE_STATES or self._workers_alive_locked()

    def _drop(self, reason: str, amount: int = 1) -> None:
        with self._lock:
            self._dropped[reason] = self._dropped.get(reason, 0) + max(1, amount)

    def _manifest_locked(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "session_id": self._session_id,
            "label": self._label,
            "state": self._state,
            "sources": list(self._sources),
            "capture_hz": self._capture_hz,
            "started_at": self._started_at,
            "completed_at": self._completed_at,
            "elapsed_s": round(self._terminal_elapsed_s, 3),
            "sample_count": self._saved,
            "drop_counts": dict(self._dropped),
            "dropped": sum(self._dropped.values()),
            "bytes_written": self._bytes_written,
            "output_path": str(self._session_dir or self.root),
            "last_error": self._last_error,
            "message": self._message,
            "pairing": {
                "hardware_synchronised": False,
                "maximum_host_timestamp_skew_us": self._pair_skew_us,
            },
            "annotations_present": False,
        }

    @staticmethod
    def _write_new_file(path: Path, data: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            view = memoryview(data)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short dataset write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @classmethod
    def _atomic_json(cls, path: Path, payload: Dict[str, Any]) -> None:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) > MAX_MANIFEST_BYTES:
            raise DatasetCaptureError("dataset metadata exceeds its size limit")
        temporary = path.parent / f".{path.name}.tmp-{uuid.uuid4().hex}"
        try:
            cls._write_new_file(temporary, encoded)
            os.replace(temporary, path)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _write_manifest(self) -> None:
        with self._lock:
            session_dir = self._session_dir
            payload = self._manifest_locked()
        if session_dir is not None:
            self._atomic_json(session_dir / "manifest.json", payload)

    def _release_tokens(self) -> None:
        with self._lock:
            tokens = dict(self._tokens)
            self._tokens.clear()
        for source_id, token in tokens.items():
            try:
                self._camera_close(source_id, token)
            except Exception:
                # Token release is idempotent.  Continue releasing the other
                # source even when one adapter is already shutting down.
                pass

    def start(
        self,
        sources: Tuple[str, ...],
        capture_hz: float = 1.0,
        label: str = "",
    ) -> Dict[str, Any]:
        with self._lifecycle_lock:
            return self._start(sources, capture_hz, label)

    def _start(
        self,
        sources: Tuple[str, ...],
        capture_hz: float,
        label: str,
    ) -> Dict[str, Any]:
        sources = self._validate_sources(sources)
        label = self._validate_label(label)
        if isinstance(capture_hz, bool):
            raise DatasetCaptureValidationError("capture rate is invalid")
        capture_hz = _safe_float(capture_hz, -1.0)
        if capture_hz < 0.2 or capture_hz > 5.0:
            raise DatasetCaptureValidationError("capture rate must be between 0.2 and 5 Hz")

        with self._lock:
            if self._state in ACTIVE_STATES or self._workers_alive_locked():
                raise DatasetCaptureBusy("a dataset capture session is already active")
            if self._free_bytes() - MAX_MANIFEST_BYTES < self._minimum_free_bytes:
                raise DatasetCaptureUnavailable("dataset storage free-space reserve is not available")
            self._state = "starting"
            self._session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex
            self._sources = sources
            self._capture_hz = capture_hz
            self._label = label
            self._started_at = _utc_now()
            self._completed_at = ""
            self._started_monotonic = time.monotonic()
            self._terminal_elapsed_s = 0.0
            self._saved = 0
            self._dropped = {}
            self._bytes_written = 0
            self._last_error = ""
            self._message = "waiting for fresh camera frames"
            self._tokens = {}
            self._last_frame_keys = {}
            self._stop_event = threading.Event()
            self._writer_done_event = threading.Event()
            self._sample_queue = queue.Queue(maxsize=self._queue_size)
            session_dir = self.sessions_dir / self._session_id
            try:
                session_dir.mkdir(mode=0o700)
                (session_dir / "samples").mkdir(mode=0o700)
                self._session_dir = session_dir.resolve(strict=True)
                _fsync_directory(session_dir)
                _fsync_directory(self.sessions_dir)
            except OSError as exc:
                LOGGER.exception("dataset session directory creation failed")
                self._state = "failed"
                self._completed_at = _utc_now()
                self._terminal_elapsed_s = max(
                    0.0, time.monotonic() - self._started_monotonic
                )
                self._last_error = "dataset session storage is unavailable"
                self._message = "cannot create dataset session directory"
                raise DatasetCaptureUnavailable(self._last_error) from exc

        opened: Dict[str, str] = {}
        writer_started = False
        try:
            for source_id in sources:
                response = self._camera_open(source_id)
                if not bool(response.get("accepted", False)) or not response.get("token"):
                    raise DatasetCaptureUnavailable(
                        str(response.get("reason", "camera source is unavailable"))
                    )
                opened[source_id] = str(response["token"])
            with self._lock:
                self._tokens = dict(opened)
            baseline = self._camera_snapshots(sources)
            for source_id in sources:
                snapshot = baseline.get(source_id, {})
                stream_id = str(snapshot.get("stream_id", ""))
                seq = _safe_int(snapshot.get("seq"))
                if stream_id and seq > 0:
                    self._last_frame_keys[source_id] = (stream_id, seq)
            self._write_manifest()
            self._writer_thread = threading.Thread(
                target=self._writer_loop,
                name="robot-scope-dataset-writer",
                daemon=True,
            )
            self._sampler_thread = threading.Thread(
                target=self._sampler_loop,
                name="robot-scope-dataset-sampler",
                daemon=True,
            )
            self._writer_thread.start()
            writer_started = True
            try:
                self._sampler_thread.start()
            except Exception:
                self._stop_event.set()
                self._sample_queue.put_nowait(None)
                if self._writer_thread.ident is not None:
                    self._writer_thread.join(timeout=2.0)
                raise
            return self.snapshot()
        except Exception as exc:
            if not isinstance(exc, DatasetCaptureError):
                LOGGER.exception("dataset capture startup failed")
            if not writer_started:
                for source_id, token in opened.items():
                    try:
                        self._camera_close(source_id, token)
                    except Exception:
                        pass
            with self._lock:
                # Once the writer starts it exclusively owns token release.
                # A bounded join above may time out while it is still
                # finalising, so clearing here would make the later release a
                # no-op and leak the camera demand token permanently.
                if not writer_started:
                    self._tokens.clear()
                self._state = "failed"
                self._last_error = (
                    str(exc)
                    if isinstance(exc, DatasetCaptureError)
                    else "dataset capture could not be started"
                )
                self._message = "dataset capture did not start"
                self._completed_at = _utc_now()
                self._terminal_elapsed_s = max(
                    0.0, time.monotonic() - self._started_monotonic
                )
            try:
                self._write_manifest()
            except Exception:
                pass
            if isinstance(exc, DatasetCaptureError):
                raise
            raise DatasetCaptureUnavailable(self._last_error) from exc

    def _validated_bundle(self) -> Optional[Dict[str, Any]]:
        try:
            snapshots = self._camera_snapshots(self._sources)
        except Exception:
            self._drop("snapshot_error")
            return None
        frames: Dict[str, Dict[str, Any]] = {}
        stamps: list[int] = []
        keys: Dict[str, Tuple[str, int]] = {}
        now_utc = _utc_now()
        for source_id in self._sources:
            snapshot = snapshots.get(source_id)
            if not isinstance(snapshot, dict):
                self._drop("source_missing")
                return None
            data = snapshot.get("data")
            if not isinstance(data, bytes) or not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
                self._drop("invalid_jpeg")
                return None
            if len(data) < 4 or len(data) > MAX_JPEG_BYTES:
                self._drop("invalid_jpeg_size")
                return None
            state = str(snapshot.get("state", "waiting"))
            age_s = _safe_float(snapshot.get("age_s"), self._stale_after_s + 1.0)
            if state != "ok" or age_s < 0 or age_s > self._stale_after_s:
                self._drop("stale_frame")
                return None
            seq = _safe_int(snapshot.get("seq"))
            stream_id = str(snapshot.get("stream_id", ""))
            stamp_us = _safe_int(snapshot.get("stamp_us"))
            if seq <= 0 or not stream_id or stamp_us <= 0:
                self._drop("invalid_frame_metadata")
                return None
            key = (stream_id, seq)
            if self._last_frame_keys.get(source_id) == key:
                self._drop("duplicate_frame")
                return None
            keys[source_id] = key
            stamps.append(stamp_us)
            frames[source_id] = {
                "data": data,
                "metadata": {
                    "source_id": source_id,
                    "seq": seq,
                    "stream_id": stream_id,
                    "stamp_us": stamp_us,
                    "age_s": age_s,
                    "topic": str(snapshot.get("topic", ""))[:512],
                    "transport": str(snapshot.get("transport", ""))[:64],
                    "width": max(0, _safe_int(snapshot.get("width"))),
                    "height": max(0, _safe_int(snapshot.get("height"))),
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                },
            }
        skew_us = max(stamps) - min(stamps) if len(stamps) > 1 else 0
        if skew_us > self._pair_skew_us:
            self._drop("pair_skew")
            return None
        self._last_frame_keys.update(keys)
        metadata: Dict[str, Any] = {}
        if self._metadata_snapshot is not None:
            try:
                candidate = self._metadata_snapshot()
                if isinstance(candidate, dict):
                    # A bounded JSON round trip removes custom mapping objects
                    # and ensures metadata cannot break the writer later.
                    encoded = json.dumps(candidate, allow_nan=False, separators=(",", ":"))
                    if len(encoded.encode("utf-8")) <= 64 * 1024:
                        metadata = json.loads(encoded)
            except Exception:
                metadata = {}
        return {
            "captured_at": now_utc,
            "requested_monotonic_ns": time.monotonic_ns(),
            "pair_skew_us": skew_us,
            "frames": frames,
            "robot_pose": metadata,
        }

    def _sampler_loop(self) -> None:
        period = 1.0 / self._capture_hz
        next_due = time.monotonic()
        startup_deadline = next_due + self._startup_timeout_s
        try:
            while not self._stop_event.is_set():
                now = time.monotonic()
                if now < next_due:
                    self._stop_event.wait(min(next_due - now, 0.2))
                    continue
                bundle = self._validated_bundle()
                if bundle is not None:
                    try:
                        self._sample_queue.put_nowait(bundle)
                    except queue.Full:
                        self._drop("writer_queue_full")
                elif time.monotonic() >= startup_deadline:
                    with self._lock:
                        if self._state == "starting":
                            self._state = "failed"
                            self._last_error = "no fresh camera frame arrived before startup timeout"
                            self._message = "dataset capture failed"
                    self._stop_event.set()
                    break
                next_due += period
                lag = time.monotonic() - next_due
                if lag >= period:
                    skipped = max(1, int(lag / period))
                    self._drop("sampler_late", skipped)
                    next_due = time.monotonic() + period
        finally:
            # The writer drains every accepted bundle before finalising.
            while not self._writer_done_event.is_set():
                try:
                    self._sample_queue.put(None, timeout=0.2)
                    break
                except queue.Full:
                    continue

    def _commit_bundle(self, bundle: Dict[str, Any]) -> None:
        with self._lock:
            session_dir = self._session_dir
            next_index = self._saved + 1
            current_bytes = self._bytes_written
        if session_dir is None:
            raise DatasetCaptureError("dataset session directory is unavailable")
        source_metadata = {
            source_id: frame["metadata"]
            for source_id, frame in bundle["frames"].items()
        }
        metadata = {
            "schema_version": 1,
            "session_id": self._session_id,
            "sample_index": next_index,
            "captured_at": bundle["captured_at"],
            "requested_monotonic_ns": bundle["requested_monotonic_ns"],
            "sources": source_metadata,
            "pair_skew_us": bundle["pair_skew_us"],
            "hardware_synchronised": False,
            "annotations_present": False,
            "robot_pose": bundle["robot_pose"],
        }
        metadata_bytes = json.dumps(
            metadata,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(metadata_bytes) > MAX_MANIFEST_BYTES:
            raise DatasetCaptureUnavailable("dataset sample metadata exceeds its size limit")
        proposed_bytes = len(metadata_bytes) + sum(
            len(frame["data"]) for frame in bundle["frames"].values()
        )
        # Reserve the full bounded manifest allowance.  The manifest is
        # atomically replaced over the lifetime of the session, so this keeps
        # the complete session directory below its hard quota even as status
        # and counters grow during finalisation.
        bounded_proposed_bytes = proposed_bytes + MAX_MANIFEST_BYTES
        if current_bytes + bounded_proposed_bytes > self._session_quota_bytes:
            raise DatasetCaptureUnavailable("dataset session quota was reached")
        if self._free_bytes() - bounded_proposed_bytes < self._minimum_free_bytes:
            raise DatasetCaptureUnavailable("dataset storage free-space reserve was reached")

        samples_dir = session_dir / "samples"
        final_dir = samples_dir / f"{next_index:08d}"
        temporary = samples_dir / f".tmp-{uuid.uuid4().hex}"
        temporary.mkdir(mode=0o700)
        written_bytes = 0
        try:
            for source_id, frame in bundle["frames"].items():
                data = frame["data"]
                self._write_new_file(temporary / f"{source_id}.jpg", data)
                written_bytes += len(data)
            self._write_new_file(temporary / "metadata.json", metadata_bytes)
            written_bytes += len(metadata_bytes)
            directory_fd = os.open(temporary, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            os.rename(temporary, final_dir)
            _fsync_directory(samples_dir)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)

        with self._lock:
            self._saved = next_index
            self._bytes_written += written_bytes
            if self._state == "starting":
                self._state = "capturing"
                self._message = "server dataset capture is active"
        self._write_manifest()

    def _writer_loop(self) -> None:
        terminal_error = ""
        try:
            while True:
                bundle = self._sample_queue.get()
                try:
                    if bundle is None:
                        break
                    self._commit_bundle(bundle)
                except Exception as exc:
                    if isinstance(exc, DatasetCaptureError):
                        terminal_error = str(exc)
                    else:
                        LOGGER.exception("dataset sample commit failed")
                        terminal_error = "dataset sample could not be written"
                    self._stop_event.set()
                    break
                finally:
                    self._sample_queue.task_done()
        finally:
            with self._lock:
                if terminal_error:
                    self._state = "failed"
                    self._last_error = terminal_error
                    self._message = "dataset capture failed"
                elif self._state not in {"failed"}:
                    self._state = "finalizing"
                    self._message = "finalizing dataset manifest"
            self._release_tokens()
            with self._lock:
                if self._state == "finalizing":
                    self._state = "completed"
                    self._message = "dataset session completed"
                self._completed_at = _utc_now()
                self._terminal_elapsed_s = max(
                    0.0, time.monotonic() - self._started_monotonic
                )
            try:
                self._write_manifest()
            except Exception:
                LOGGER.exception("dataset manifest finalization failed")
                with self._lock:
                    self._state = "failed"
                    self._last_error = "dataset manifest could not be finalized"
                    self._message = "dataset finalization failed"
            finally:
                self._writer_done_event.set()

    def stop(self, session_id: str, timeout_s: float = 8.0) -> Dict[str, Any]:
        with self._lifecycle_lock:
            return self._stop(session_id, timeout_s)

    def _stop(self, session_id: str, timeout_s: float) -> Dict[str, Any]:
        session_id = self._validate_session_id(session_id)
        with self._lock:
            if not self._session_id or session_id != self._session_id:
                raise DatasetCaptureConflict("dataset session id does not match the active session")
            workers_alive = self._workers_alive_locked()
            if self._state not in ACTIVE_STATES and not workers_alive:
                return self._snapshot_locked()
            if self._state in ACTIVE_STATES and self._state not in {"stopping", "finalizing"}:
                self._state = "stopping"
                self._message = "stopping dataset capture"
            self._stop_event.set()
            sampler = self._sampler_thread
            writer = self._writer_thread
        deadline = time.monotonic() + max(0.1, timeout_s)
        if (
            sampler is not None
            and sampler is not threading.current_thread()
            and sampler.ident is not None
        ):
            sampler.join(max(0.0, deadline - time.monotonic()))
        if (
            writer is not None
            and writer is not threading.current_thread()
            and writer.ident is not None
        ):
            writer.join(max(0.0, deadline - time.monotonic()))
        with self._lock:
            if self._state in ACTIVE_STATES and time.monotonic() >= deadline:
                self._last_error = "dataset capture is still finalizing"
                self._message = "dataset capture stop timed out; do not restart the service"
            return self._snapshot_locked()

    def close(self) -> None:
        with self._lifecycle_lock:
            with self._lock:
                session_id = self._session_id
                active = self._state in ACTIVE_STATES or self._workers_alive_locked()
            if active and session_id:
                self._stop(session_id, timeout_s=10.0)
            self._release_tokens()

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        if path.is_symlink() or not path.is_file():
            raise DatasetCaptureNotFound("dataset metadata was not found")
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > MAX_MANIFEST_BYTES:
            raise DatasetCaptureNotFound("dataset metadata was not found")
        with path.open("rb") as handle:
            payload = json.loads(handle.read(MAX_MANIFEST_BYTES + 1).decode("utf-8"))
        if not isinstance(payload, dict):
            raise DatasetCaptureNotFound("dataset metadata is invalid")
        return payload

    def _recover_interrupted_sessions(self) -> None:
        for candidate in self.sessions_dir.iterdir():
            if candidate.is_symlink() or not candidate.is_dir() or not SESSION_ID_RE.fullmatch(candidate.name):
                continue
            manifest_path = candidate / "manifest.json"
            try:
                manifest = self._read_json(manifest_path)
            except (DatasetCaptureError, OSError, ValueError, json.JSONDecodeError):
                continue
            samples_dir = candidate / "samples"
            if samples_dir.is_symlink() or not samples_dir.is_dir():
                continue
            if str(manifest.get("state", "")) in ACTIVE_STATES:
                # A single writer publishes one sample then atomically updates
                # the manifest before taking the next queue item.  Therefore a
                # crash can leave at most one committed directory ahead of the
                # durable count.  Probe only that exact path instead of sorting
                # an arbitrarily large training session during application
                # startup.
                committed_count = min(
                    99_999_999,
                    max(0, _safe_int(manifest.get("sample_count"))),
                )
                committed_bytes = max(0, _safe_int(manifest.get("bytes_written")))
                next_index = committed_count + 1
                if next_index <= 99_999_999:
                    extra = samples_dir / f"{next_index:08d}"
                    if (
                        not extra.is_symlink()
                        and extra.is_dir()
                        and SAMPLE_DIR_RE.fullmatch(extra.name)
                    ):
                        try:
                            metadata = self._read_json(extra / "metadata.json")
                            raw_sources = metadata.get("sources", {})
                            source_ids = [
                                source_id
                                for source_id in CAMERA_SOURCE_IDS
                                if isinstance(raw_sources, dict)
                                and source_id in raw_sources
                            ]
                            if (
                                metadata.get("session_id") != candidate.name
                                or _safe_int(metadata.get("sample_index")) != next_index
                                or not source_ids
                            ):
                                raise DatasetCaptureNotFound("dataset sample is incomplete")
                            artifacts = [extra / "metadata.json"] + [
                                extra / f"{source_id}.jpg" for source_id in source_ids
                            ]
                            extra_bytes = 0
                            for artifact in artifacts:
                                if artifact.is_symlink() or not artifact.is_file():
                                    raise DatasetCaptureNotFound("dataset sample is incomplete")
                                info = artifact.stat()
                                if not stat.S_ISREG(info.st_mode):
                                    raise DatasetCaptureNotFound("dataset sample is incomplete")
                                extra_bytes += info.st_size
                            manifest["sample_count"] = next_index
                            manifest["bytes_written"] = committed_bytes + extra_bytes
                        except (DatasetCaptureError, OSError, ValueError, json.JSONDecodeError):
                            pass
                manifest["state"] = "interrupted"
                manifest["completed_at"] = _utc_now()
                manifest["last_error"] = "dashboard stopped before dataset finalization"
                manifest["message"] = "recovered interrupted dataset session"
                try:
                    self._atomic_json(manifest_path, manifest)
                except (DatasetCaptureError, OSError):
                    continue
            # Temp sample names are random and not addressable by an index.
            # Scanning a completed 20 GiB session on every dashboard startup
            # would make boot time proportional to the dataset size.  Only an
            # interrupted active session can require crash-temp cleanup, and
            # its queue bound means at most a small number can exist.
            if str(manifest.get("state", "")) == "interrupted":
                removed = 0
                inspected = 0
                with os.scandir(samples_dir) as entries:
                    for entry in entries:
                        inspected += 1
                        if inspected > self._queue_size + 32 or removed >= self._queue_size + 2:
                            break
                        if (
                            TEMP_SAMPLE_DIR_RE.fullmatch(entry.name)
                            and not entry.is_symlink()
                            and entry.is_dir(follow_symlinks=False)
                        ):
                            shutil.rmtree(samples_dir / entry.name, ignore_errors=True)
                            removed += 1

    @staticmethod
    def _session_summary(manifest: Dict[str, Any]) -> Dict[str, Any]:
        raw_session_id = manifest.get("session_id", "")
        session_id = raw_session_id if isinstance(raw_session_id, str) else ""
        raw_label = manifest.get("label", "")
        label = raw_label[:64] if isinstance(raw_label, str) else ""
        raw_state = manifest.get("state", "unknown")
        allowed_states = ACTIVE_STATES | {"idle", "completed", "failed", "interrupted"}
        state = raw_state if isinstance(raw_state, str) and raw_state in allowed_states else "unknown"
        raw_sources = manifest.get("sources", [])
        sources = []
        if isinstance(raw_sources, list):
            # Managed manifests contain at most two values.  Bound imported or
            # corrupted input so a 1 MiB JSON file cannot inflate an API
            # response with hundreds of thousands of repeated source IDs.
            for source in raw_sources[:8]:
                if source in CAMERA_SOURCE_IDS and source not in sources:
                    sources.append(source)
        output_path = manifest.get("output_path", "")
        started_at = manifest.get("started_at", "")
        completed_at = manifest.get("completed_at", "")
        capture_hz = min(5.0, max(0.0, _safe_float(manifest.get("capture_hz"))))
        sample_count = min(99_999_999, max(0, _safe_int(manifest.get("sample_count"))))
        bytes_written = min((1 << 63) - 1, max(0, _safe_int(manifest.get("bytes_written"))))
        return {
            "id": session_id,
            "session_id": session_id,
            "label": label or session_id,
            "state": state,
            "sources": sources,
            "capture_hz": capture_hz,
            "sample_count": sample_count,
            "bytes": bytes_written,
            "bytes_written": bytes_written,
            "output_path": output_path[:4096] if isinstance(output_path, str) else "",
            "started_at": started_at[:64] if isinstance(started_at, str) else "",
            "completed_at": completed_at[:64] if isinstance(completed_at, str) else "",
        }

    def list_sessions(self) -> Dict[str, Any]:
        sessions = []
        candidates = heapq.nlargest(
            MAX_SESSIONS,
            self.sessions_dir.iterdir(),
            key=lambda path: path.name,
        )
        for candidate in candidates:
            if candidate.is_symlink() or not candidate.is_dir() or not SESSION_ID_RE.fullmatch(candidate.name):
                continue
            try:
                manifest = self._read_json(candidate / "manifest.json")
            except (DatasetCaptureError, OSError, ValueError, json.JSONDecodeError):
                continue
            if manifest.get("session_id") != candidate.name:
                continue
            sessions.append(self._session_summary(manifest))
        return {"sessions": sessions, "output_path": str(self.root)}

    def session_detail(
        self,
        session_id: str,
        before: Optional[int] = None,
        limit: int = DEFAULT_SAMPLES_PER_PAGE,
    ) -> Dict[str, Any]:
        if isinstance(before, bool) or (
            before is not None and (not isinstance(before, int) or before < 1 or before > 100_000_000)
        ):
            raise DatasetCaptureValidationError("dataset page cursor is invalid")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > MAX_SAMPLES_PER_DETAIL:
            raise DatasetCaptureValidationError("dataset page limit is invalid")
        session_dir = self._session_path(session_id)
        manifest = self._read_json(session_dir / "manifest.json")
        if manifest.get("session_id") != session_id:
            raise DatasetCaptureNotFound("dataset session was not found")
        samples = []
        samples_dir = session_dir / "samples"
        if samples_dir.is_symlink() or not samples_dir.is_dir():
            raise DatasetCaptureNotFound("dataset samples were not found")
        sample_count = min(99_999_999, max(0, _safe_int(manifest.get("sample_count"))))
        last_index = sample_count if before is None else min(sample_count, before - 1)
        first_index = max(1, last_index - limit + 1)
        for sample_index in range(first_index, last_index + 1):
            candidate = samples_dir / f"{sample_index:08d}"
            if candidate.is_symlink() or not candidate.is_dir() or not SAMPLE_DIR_RE.fullmatch(candidate.name):
                continue
            try:
                metadata = self._read_json(candidate / "metadata.json")
            except (DatasetCaptureError, OSError, ValueError, json.JSONDecodeError):
                continue
            source_ids = [
                source_id
                for source_id in CAMERA_SOURCE_IDS
                if (candidate / f"{source_id}.jpg").is_file()
                and not (candidate / f"{source_id}.jpg").is_symlink()
            ]
            if not source_ids:
                continue
            samples.append(
                {
                    "index": int(candidate.name),
                    "sample_index": int(candidate.name),
                    "sources": source_ids,
                    "captured_at": (
                        metadata.get("captured_at", "")[:64]
                        if isinstance(metadata.get("captured_at"), str)
                        else ""
                    ),
                    "pair_skew_us": min(
                        self._pair_skew_us,
                        max(0, _safe_int(metadata.get("pair_skew_us"))),
                    ),
                }
            )
        detail = self._session_summary(manifest)
        detail["samples"] = samples
        oldest_index = samples[0]["index"] if samples else 0
        newest_index = samples[-1]["index"] if samples else 0
        detail["page"] = {
            "limit": limit,
            "before": before,
            "oldest_index": oldest_index,
            "newest_index": newest_index,
            "next_before": first_index if first_index > 1 else None,
            "has_older": first_index > 1,
            "has_newer": before is not None and last_index < sample_count,
        }
        return detail

    def read_image(self, session_id: str, sample_index: int, source_id: str) -> bytes:
        session_dir = self._session_path(session_id)
        if source_id not in CAMERA_SOURCE_IDS:
            raise DatasetCaptureNotFound("dataset image was not found")
        if isinstance(sample_index, bool) or sample_index < 1 or sample_index > 99_999_999:
            raise DatasetCaptureNotFound("dataset image was not found")
        samples_dir = session_dir / "samples"
        sample_dir = samples_dir / f"{sample_index:08d}"
        if sample_dir.is_symlink() or not sample_dir.is_dir():
            raise DatasetCaptureNotFound("dataset image was not found")
        try:
            if sample_dir.resolve(strict=True).parent != samples_dir.resolve(strict=True):
                raise DatasetCaptureNotFound("dataset image was not found")
        except OSError as exc:
            raise DatasetCaptureNotFound("dataset image was not found") from exc
        path = sample_dir / f"{source_id}.jpg"
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise DatasetCaptureNotFound("dataset image was not found") from exc
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size < 4 or info.st_size > MAX_JPEG_BYTES:
                raise DatasetCaptureNotFound("dataset image was not found")
            data = b""
            while len(data) < info.st_size:
                chunk = os.read(descriptor, min(256 * 1024, info.st_size - len(data)))
                if not chunk:
                    break
                data += chunk
        finally:
            os.close(descriptor)
        if len(data) != info.st_size or not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
            raise DatasetCaptureNotFound("dataset image was not found")
        return data
