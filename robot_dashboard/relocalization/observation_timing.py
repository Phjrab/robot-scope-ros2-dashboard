"""Bounded request-local timings; never contain clouds, poses or device IDs."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import time


_CURRENT: ContextVar["ObservationTiming | None"] = ContextVar("observation_timing", default=None)


class ObservationTiming:
    def __init__(self) -> None:
        self.started = time.monotonic()
        self.stages: dict[str, dict[str, float | int]] = {}
        self.values: dict[str, float | int | bool] = {}
        self.failed_stage: str | None = None

    @contextmanager
    def bind(self):
        token = _CURRENT.set(self)
        try:
            yield self
        finally:
            _CURRENT.reset(token)

    def summary(self) -> dict:
        return {"schema": "robot-scope.observation-timing.v1",
                "dispatch_to_response_ms": (time.monotonic() - self.started) * 1000,
                "failed_stage": self.failed_stage, "stages": self.stages, "values": self.values}


@contextmanager
def measure(name: str):
    trace = _CURRENT.get()
    if trace is None:
        yield
        return
    # Names are internal constants; guard storage even if a future caller errs.
    if name not in trace.stages and len(trace.stages) >= 32:
        yield
        return
    row = trace.stages.setdefault(name, {"wall_ms": 0.0, "thread_cpu_ms": 0.0, "calls": 0})
    started, cpu = time.monotonic(), time.thread_time()
    try:
        yield
    except BaseException:
        if trace.failed_stage is None:
            trace.failed_stage = name
        raise
    finally:
        row["wall_ms"] += (time.monotonic() - started) * 1000
        row["thread_cpu_ms"] += (time.thread_time() - cpu) * 1000
        row["calls"] += 1


def note(name: str, value: float | int | bool) -> None:
    trace = _CURRENT.get()
    if trace is not None and (name in trace.values or len(trace.values) < 16):
        trace.values[name] = value


@contextmanager
def measured_lock(lock, name: str):
    with measure(name + "_wait"):
        lock.acquire()
    try:
        with measure(name + "_hold"):
            yield
    finally:
        lock.release()
