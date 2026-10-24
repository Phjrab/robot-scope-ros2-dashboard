"""Bounded transfer from an existing camera owner; no acquisition or inference on ingress."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time


@dataclass(frozen=True)
class SignalSample:
    frame: object
    observation: object
    processed_s: float


class TrafficWorker:
    """One executing frame plus one latest pending frame. Explicit start/close only.

    The owner transfers a Frame with its original source/receipt metadata and must
    not mutate the image afterward. A dropped sequence makes C4 reset stability.
    Optional detector libraries stay outside dashboard startup imports.
    """
    def __init__(self, pipeline, *, clock=time.monotonic):
        self.pipeline, self.clock = pipeline, clock
        self.queue = asyncio.Queue(maxsize=1)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='traffic-frame')
        self.task = None
        self.latest = None
        self.error = None
        self.closed = False
        self.dropped = 0

    def start(self):
        if self.closed or self.task is not None:
            raise ValueError('WORKER_ALREADY_STARTED_OR_CLOSED')
        self.task = asyncio.create_task(self._run())

    def offer(self, frame):
        """Call on the owner event loop (or via call_soon_threadsafe). Never awaits."""
        if self.closed or self.task is None:
            return False
        if self.queue.full():
            self.queue.get_nowait()
            self.queue.task_done()
            self.dropped += 1
        self.queue.put_nowait(frame)
        return True

    async def _run(self):
        loop = asyncio.get_running_loop()
        while True:
            frame = await self.queue.get()
            try:
                observation = await loop.run_in_executor(self.executor,
                    lambda: self.pipeline.process(frame, now_s=self.clock()))
                if not self.closed:
                    self.latest = SignalSample(frame, observation, self.clock())
                    self.error = None
            except Exception as exc:
                self.latest = None
                self.error = type(exc).__name__
            finally:
                self.queue.task_done()

    async def close(self):
        self.closed = True
        self.latest = None
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        # Running inference cannot be forcibly interrupted. It has no callback
        # into the mission or command gate; late results are discarded.
        self.executor.shutdown(wait=False, cancel_futures=True)
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
