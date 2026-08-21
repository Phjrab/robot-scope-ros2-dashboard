"""Single-thread ROS runtime ownership without domain policy."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable


class RosRuntime:
    """Own the ROS thread, executor handles, readiness, and shared state lock."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.node: Any = None
        self.executor: Any = None
        self.started_at = time.monotonic()
        self.ready = False
        self.last_error = ""

    def start(self, target: Callable[[], None]) -> bool:
        if self.thread and self.thread.is_alive():
            return False
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=target,
            name="robot-scope-ros",
            daemon=True,
        )
        self.thread.start()
        return True

    def request_stop(self) -> None:
        self.stop_event.set()

    def shutdown_executor(self, timeout_s: float = 2.0) -> None:
        executor = self.executor
        if executor is None:
            return
        try:
            executor.shutdown(timeout_sec=timeout_s)
        except Exception:
            pass

    def join(self, timeout_s: float = 4.0) -> None:
        thread = self.thread
        if thread is not None:
            thread.join(timeout=timeout_s)
