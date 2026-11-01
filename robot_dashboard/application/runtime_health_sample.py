"""Locally timed navigation health read, never constructed from an HTTP body."""
from __future__ import annotations

import copy
import math
import time

_TOKEN = object()


class RuntimeHealthSample:
    __slots__ = ('__value', '__sampled_at')

    def __init__(self, value, sampled_at, token):
        if token is not _TOKEN:
            raise TypeError('use capture_runtime_health')
        self.__value = copy.deepcopy(value)
        self.__sampled_at = sampled_at

    @property
    def sampled_at(self):
        return self.__sampled_at

    def snapshot(self):
        return copy.deepcopy(self.__value)

    def age_s(self):
        age = self.__value.get('age_s') if isinstance(self.__value, dict) else None
        elapsed = time.monotonic() - self.__sampled_at
        if (type(age) not in (int, float) or not math.isfinite(age) or age < 0
                or not math.isfinite(elapsed) or elapsed < 0):
            return None
        # Gateway rounds its age to milliseconds; preserve a conservative margin.
        return age + elapsed + .001


def capture_runtime_health(agent):
    sampled_at = time.monotonic()
    value = agent._navigation_runtime_health_snapshot(sampled_at) if agent else {}
    return RuntimeHealthSample(value, sampled_at, _TOKEN)
