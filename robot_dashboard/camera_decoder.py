"""Bounded H.264 to JPEG bridge using the Jetson GStreamer runtime."""

from __future__ import annotations

import queue
import shutil
import subprocess
import threading
from typing import Callable, Optional


class H264JpegDecoder:
    """Decode a continuous Annex-B H.264 stream without blocking ROS callbacks."""

    def __init__(self, on_jpeg: Callable[[bytes], None]) -> None:
        self.on_jpeg = on_jpeg
        self._queue: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=96)
        self._process: Optional[subprocess.Popen] = None
        self._writer: Optional[threading.Thread] = None
        self._reader: Optional[threading.Thread] = None
        self._stderr: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stopping = False
        self.last_error = ""
        self.decoded_frames = 0
        self.dropped_chunks = 0

    @property
    def available(self) -> bool:
        return shutil.which("gst-launch-1.0") is not None

    def start(self) -> bool:
        with self._lock:
            if self._process and self._process.poll() is None:
                return True
            if not self.available or self._stopping:
                return False
            command = [
                "gst-launch-1.0", "-q",
                "fdsrc", "fd=0",
                "!", "h264parse", "disable-passthrough=true",
                "!", "avdec_h264", "output-corrupt=false",
                "!", "videoconvert",
                "!", "videoscale", "method=0",
                "!", "videorate", "drop-only=true",
                "!", "video/x-raw,format=I420,width=640,height=360,framerate=12/1",
                "!", "jpegenc", "quality=72",
                "!", "fdsink", "fd=1", "sync=false",
            ]
            try:
                self._process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )
            except OSError as exc:
                self.last_error = str(exc)
                self._process = None
                return False
            self._writer = threading.Thread(target=self._write_loop, name="camera-h264-writer", daemon=True)
            self._reader = threading.Thread(target=self._read_loop, name="camera-jpeg-reader", daemon=True)
            self._stderr = threading.Thread(target=self._stderr_loop, name="camera-gst-stderr", daemon=True)
            self._writer.start()
            self._reader.start()
            self._stderr.start()
            return True

    def feed(self, payload: bytes) -> bool:
        if not payload or not self.start():
            return False
        try:
            self._queue.put_nowait(payload)
            return True
        except queue.Full:
            self.dropped_chunks += 1
            return False

    def _write_loop(self) -> None:
        process = self._process
        if not process or not process.stdin:
            return
        while not self._stopping and process.poll() is None:
            try:
                payload = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if payload is None:
                break
            try:
                process.stdin.write(payload)
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self.last_error = str(exc)
                break

    def _read_loop(self) -> None:
        process = self._process
        if not process or not process.stdout:
            return
        buffer = bytearray()
        while not self._stopping and process.poll() is None:
            try:
                chunk = process.stdout.read(65536)
            except OSError as exc:
                self.last_error = str(exc)
                break
            if not chunk:
                break
            buffer.extend(chunk)
            while True:
                start = buffer.find(b"\xff\xd8")
                if start < 0:
                    if len(buffer) > 8 * 1024 * 1024:
                        buffer.clear()
                    break
                end = buffer.find(b"\xff\xd9", start + 2)
                if end < 0:
                    if start:
                        del buffer[:start]
                    break
                jpeg = bytes(buffer[start : end + 2])
                del buffer[: end + 2]
                self.decoded_frames += 1
                self.on_jpeg(jpeg)

    def _stderr_loop(self) -> None:
        process = self._process
        if not process or not process.stderr:
            return
        while not self._stopping and process.poll() is None:
            line = process.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                self.last_error = text[-400:]

    def stop(self) -> None:
        self._stopping = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        process = self._process
        if process:
            try:
                if process.stdin:
                    process.stdin.close()
            except OSError:
                pass
            try:
                process.terminate()
                process.wait(timeout=1.5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass

