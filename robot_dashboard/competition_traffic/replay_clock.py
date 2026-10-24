"""Separate recorded timeline semantics from paced local CPU workload timing."""
from dataclasses import replace
import time


class ReplayClock:
    def __init__(self, mode, *, clock=time.monotonic, sleep=time.sleep):
        if mode not in ("source-timeline", "wall-clock"):
            raise ValueError("REPLAY_CLOCK_MODE_INVALID")
        self.mode, self.clock, self.sleep = mode, clock, sleep
        self.anchor = self.first_source = self.previous_source = None

    def arrive(self, frame):
        source_time = frame.received_s
        if self.previous_source is not None and source_time <= self.previous_source:
            raise ValueError("REPLAY_TIMELINE_NOT_INCREASING")
        self.previous_source = source_time
        if self.mode == "source-timeline":
            return frame, source_time
        if self.anchor is None:
            self.anchor, self.first_source = self.clock(), source_time
        scheduled = self.anchor + source_time - self.first_source
        # A virtual receiver receives at the recorded cadence even if processing
        # is behind. Queue delay stays visible; never reset receipt to dequeue.
        while True:
            remaining = scheduled - self.clock()
            if remaining <= 0:
                break
            self.sleep(min(.25, remaining))
        return replace(frame, received_s=scheduled), self.clock()
