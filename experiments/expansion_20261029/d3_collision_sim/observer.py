"""Fixture-only final command gate; no ROS publishing, controller or plant.

A predictive stop stays latched while observation continues for a bounded
remaining window. Actual geometry contact, cancel and infrastructure failure
are distinct terminal outcomes. Never restart goals or release the stop here.
"""

import math


class Observer:
    def __init__(self, deadline_s, continuation_s=1.0):
        if not all(math.isfinite(x) and x > 0 for x in (deadline_s, continuation_s)):
            raise ValueError("finite positive observer bounds required")
        self.deadline = deadline_s
        self.continuation = continuation_s
        self.stop_at = None
        self.last_time = -1.0
        self.terminal = None

    def step(
        self,
        time_s,
        command,
        assessment,
        *,
        oracle_contact=False,
        cancel=False,
        infrastructure_error=False,
    ):
        if not math.isfinite(time_s) or time_s < 0 or time_s < self.last_time:
            raise ValueError("monotonic fixture time required")
        if len(command) != 2 or not all(math.isfinite(x) for x in command):
            raise ValueError("finite two-axis fixture command required")
        self.last_time = time_s
        if self.terminal:
            return {
                "command": (0.0, 0.0),
                "terminal": self.terminal,
                "observing": False,
            }
        if infrastructure_error:
            self.terminal = "INFRASTRUCTURE_FAILURE"
        elif cancel:
            self.terminal = "CANCELED"
        elif oracle_contact:
            self.terminal = "ACTUAL_SIM_GEOMETRY_CONTACT"
        if assessment["severity"] != "CLEAR" and self.stop_at is None:
            self.stop_at = time_s
        until = (
            min(self.deadline, self.stop_at + self.continuation)
            if self.stop_at is not None
            else self.deadline
        )
        if time_s >= until and not self.terminal:
            self.terminal = (
                "PREDICTIVE_STOP_OBSERVED"
                if self.stop_at is not None
                else "OBSERVATION_DEADLINE"
            )
        stop = self.stop_at is not None or self.terminal is not None
        return {
            "command": (0.0, 0.0) if stop else tuple(command),
            "terminal": self.terminal,
            "observing": self.terminal is None,
        }
