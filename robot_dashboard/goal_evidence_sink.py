"""Bounded private metrology writer; no filesystem work in control callbacks."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import stat
import threading


class GoalEvidenceSink:
    MAX_RECORD_BYTES = 256 * 1024
    MAX_FILE_BYTES = 8 * 1024 * 1024
    BACKUPS = 3

    def __init__(self, directory: Path):
        self._directory = directory
        self._queue = queue.Queue(maxsize=64)
        self._closing = threading.Event()
        self._written = self._dropped = self._errors = 0
        self._thread = threading.Thread(target=self._run, name='goal-evidence-writer', daemon=True)
        self._thread.start()

    def submit(self, event, evidence):
        """Evidence is an already detached, bounded GoalPrecision snapshot."""
        if self._closing.is_set():
            self._dropped += 1
            return False
        try:
            self._queue.put_nowait({'schema': 'robot-scope.goal-evidence-log.v1',
                                   'event': event, 'evidence': evidence})
            return True
        except queue.Full:
            self._dropped += 1
            return False

    def snapshot(self):
        return {'configured': True, 'written': self._written, 'dropped': self._dropped,
                'errors': self._errors, 'pending': self._queue.qsize(),
                'writer_alive': self._thread.is_alive()}

    def close(self, timeout=0.5):
        # Called only after control/ROS shutdown. Disk failure cannot delay STOP.
        self._closing.set()
        self._thread.join(timeout)

    def _write(self, payload):
        directory = self._directory
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError('private evidence directory is not owned')
        directory.chmod(0o700)
        path = directory / 'events.jsonl'
        if path.is_symlink():
            raise ValueError('evidence symlink rejected')
        if path.exists() and path.stat().st_size + len(payload) > self.MAX_FILE_BYTES:
            for index in range(self.BACKUPS, 0, -1):
                source = directory / ('events.jsonl' if index == 1 else f'events.jsonl.{index - 1}')
                if source.exists():
                    source.replace(directory / f'events.jsonl.{index}')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                raise ValueError('evidence file is not private regular file')
            os.fchmod(fd, 0o600)
            remaining = memoryview(payload)
            while remaining:
                count = os.write(fd, remaining)
                if count <= 0:
                    raise OSError('evidence write incomplete')
                remaining = remaining[count:]
        finally:
            os.close(fd)

    def _run(self):
        while not self._closing.is_set() or not self._queue.empty():
            try:
                record = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                payload = (json.dumps(record, allow_nan=False, separators=(',', ':')) + '\n').encode()
                if len(payload) > self.MAX_RECORD_BYTES:
                    self._dropped += 1
                else:
                    self._write(payload)
                    self._written += 1
            except Exception:
                self._errors += 1
            finally:
                self._queue.task_done()
