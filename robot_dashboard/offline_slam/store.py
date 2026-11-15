"""Isolated, single-flight subprocess jobs and immutable map packages."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid
import zipfile

from .core import MAX_BYTES, digest, encoded, preview, validate_session

ID = re.compile(r"^[a-f0-9]{32}$")


def read_json(path, limit=MAX_BYTES):
    if path.is_symlink() or path.stat().st_size > limit:
        raise ValueError("UNSAFE_OR_OVERSIZE_FILE")
    return json.loads(path.read_bytes())


def write_new(path, data):
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._file_lock = (self.root / ".owner.lock").open("a+b")
        self._file_lock.write(b"0")
        self._file_lock.flush()
        self._file_lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._file_lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._file_lock.close()
            raise ValueError("OFFLINE_STORE_ALREADY_OPEN") from exc
        self.lock = threading.RLock()
        self.process = None
        self.active = None
        self.started = 0
        # One application process owns this store; unfinished jobs never auto-resume.
        for path in self.root.glob("*/job.json"):
            if path.parent.is_symlink():
                continue
            job = read_json(path)
            if job.get("state") == "RUNNING":
                job["state"] = "INTERRUPTED"
                self._replace(path, job)

    @staticmethod
    def _replace(path, data):
        temp = path.with_suffix(".tmp")
        temp.write_bytes(encoded(data))
        os.replace(temp, path)

    def directory(self, identifier):
        if not ID.fullmatch(identifier):
            raise ValueError("INVALID_ID")
        path = self.root / identifier
        if path.is_symlink() or not path.is_dir():
            raise ValueError("SESSION_NOT_FOUND")
        return path

    @staticmethod
    def work_directory(path, job):
        run_id = job.get("run_id")
        if not isinstance(run_id, str) or not ID.fullmatch(run_id):
            raise ValueError("RUN_ID_REQUIRED")
        work = path / run_id
        if work.is_symlink() or not work.is_dir():
            raise ValueError("RUN_NOT_FOUND")
        return work

    def import_session(self, raw):
        if len(raw) > MAX_BYTES:
            raise ValueError("SESSION_TOO_LARGE")
        data = validate_session(json.loads(raw))
        identifier = uuid.uuid4().hex
        with self.lock:
            if len(list(self.root.iterdir())) >= 100:
                raise ValueError("SESSION_STORAGE_LIMIT")
            path = self.root / identifier
            path.mkdir()
            write_new(path / "session.json", encoded(data))
            self._replace(
                path / "job.json",
                dict(
                    state="IMPORTED",
                    source_revision=digest(data),
                    keyframes=len(data["keyframes"]),
                    provenance=data["provenance"],
                ),
            )
        return self.status(identifier)

    def _poll(self):
        if self.process is None:
            return
        code = self.process.poll()
        timeout = time.monotonic() - self.started > 600
        if code is None and not timeout:
            return
        if code is None:
            self.process.terminate()
            try:
                self.process.wait(3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        path = self.directory(self.active)
        job = read_json(path / "job.json")
        work = self.work_directory(path, job)
        state = "FAILED"
        if timeout:
            state = "TIMED_OUT"
        elif code == 0 and (work / "result.json").exists():
            result = read_json(work / "result.json")
            state = result["state"]
        job["state"] = state
        self._replace(path / "job.json", job)
        self.process, self.active = None, None

    def status(self, identifier):
        with self.lock:
            self._poll()
            path = self.directory(identifier)
            job = read_json(path / "job.json")
            job.update(id=identifier)
            work = self.work_directory(path, job) if job.get("run_id") else path
            if (work / "settings.json").exists():
                job["settings"] = read_json(work / "settings.json")
            if (
                job["state"] in {"SUCCEEDED", "NO_LOOP", "FAILED"}
                and (work / "result.json").exists()
            ):
                result = read_json(work / "result.json")
                job.update(
                    {
                        k: result[k]
                        for k in ("metrics", "revision", "candidates", "error")
                        if k in result
                    }
                )
            if (path / "map-package.zip").exists():
                job["saved"] = True
            return job

    def list_sessions(self):
        with self.lock:
            return [
                self.status(p.name)
                for p in sorted(self.root.iterdir())
                if ID.fullmatch(p.name)
                and not p.is_symlink()
                and (p / "job.json").exists()
            ]

    def tick(self):
        with self.lock:
            self._poll()

    def start(self, identifier, settings, expected_revision):
        settings.validate()
        with self.lock:
            self._poll()
            if self.process:
                raise ValueError("WORKER_BUSY")
            path = self.directory(identifier)
            data = read_json(path / "session.json")
            if digest(data) != expected_revision:
                raise ValueError("SOURCE_REVISION_CONFLICT")
            if (path / "map-package.zip").exists():
                raise ValueError("SAVED_RESULT_IMMUTABLE_IMPORT_SESSION_AGAIN")
            from dataclasses import asdict

            if len(list(path.glob("*/settings.json"))) >= 5:
                raise ValueError("RUN_LIMIT_IMPORT_SESSION_AGAIN")
            run_id = uuid.uuid4().hex
            work = path / run_id
            work.mkdir()
            write_new(work / "session.json", encoded(data))
            self._replace(work / "settings.json", asdict(settings))
            env = dict(
                os.environ,
                OPENBLAS_NUM_THREADS="1",
                OMP_NUM_THREADS="1",
                MKL_NUM_THREADS="1",
            )
            project_root = Path(__file__).resolve().parents[2]
            env["PYTHONPATH"] = (
                str(project_root) + os.pathsep + env.get("PYTHONPATH", "")
            )
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "robot_dashboard.offline_slam.worker",
                    str(work),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                cwd=project_root,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.active, self.started = identifier, time.monotonic()
            self._replace(
                path / "job.json",
                dict(
                    state="RUNNING",
                    run_id=run_id,
                    source_revision=expected_revision,
                    keyframes=len(data["keyframes"]),
                    provenance=data["provenance"],
                ),
            )
            return self.status(identifier)

    def cancel(self, identifier):
        with self.lock:
            self.directory(identifier)
            self._poll()
            if self.active == identifier and self.process:
                self.process.terminate()
                try:
                    self.process.wait(3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                self.process, self.active = None, None
                path = self.directory(identifier) / "job.json"
                job = read_json(path)
                job["state"] = "CANCELLED"
                self._replace(path, job)
            return self.status(identifier)

    def comparison(self, identifier):
        with self.lock:
            job = self.status(identifier)
            path = self.directory(identifier)
            if job["state"] == "SUCCEEDED":
                return read_json(self.work_directory(path, job) / "preview.json")
            return preview(read_json(path / "session.json"))

    def save(self, identifier, revision):
        with self.lock:
            job = self.status(identifier)
            if job["state"] != "SUCCEEDED" or job.get("revision") != revision:
                raise ValueError("RESULT_REVISION_CONFLICT")
            path = self.directory(identifier)
            work = self.work_directory(path, job)
            archive = path / "map-package.zip"
            if not archive.exists():
                names = (
                    "session.json",
                    "result.json",
                    "optimized.pcd",
                    "map.pgm",
                    "map.yaml",
                )
                hashes = {
                    name: hashlib.sha256((work / name).read_bytes()).hexdigest()
                    for name in names
                }
                manifest = dict(
                    schema="robot-scope.offline-map/v1",
                    revision=revision,
                    source_revision=job["source_revision"],
                    provenance=job["provenance"],
                    files=hashes,
                    operational_application="NOT_APPLIED",
                    navigation_validated=False,
                    occupancy="Single-level candidate; height is measured in the anchored parent frame",
                )
                temp = path / "package.tmp"
                with zipfile.ZipFile(
                    temp, "w", compression=zipfile.ZIP_DEFLATED
                ) as out:
                    for name in names:
                        out.write(work / name, name)
                    out.writestr("manifest.json", encoded(manifest))
                os.replace(temp, archive)
            return dict(
                id=identifier,
                revision=revision,
                saved=True,
                operational_application="NOT_APPLIED",
            )

    def export(self, identifier, revision):
        with self.lock:
            job = self.status(identifier)
            if job.get("revision") != revision or not job.get("saved"):
                raise ValueError("SAVED_REVISION_REQUIRED")
            return self.directory(identifier) / "map-package.zip"

    def close(self):
        with self.lock:
            if self.active:
                self.cancel(self.active)
            self._file_lock.close()
