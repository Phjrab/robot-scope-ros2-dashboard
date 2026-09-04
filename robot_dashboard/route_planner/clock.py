"""Clock ports used by deterministic Route Planner replay tests."""

from __future__ import annotations

from dataclasses import dataclass

from .perception import MAX_UINT64


class VirtualClockError(ValueError):
    """Raised when a virtual time operation would violate uint64 monotonicity."""


@dataclass
class VirtualMonotonicClock:
    """A deterministic, non-decreasing nanosecond clock with no wall-clock access."""

    _value_ns: int = 0

    def __post_init__(self) -> None:
        self.set_ns(self._value_ns)

    def now_ns(self) -> int:
        return self._value_ns

    def advance_ms(self, milliseconds: int) -> int:
        if (
            isinstance(milliseconds, bool)
            or not isinstance(milliseconds, int)
            or milliseconds < 0
        ):
            raise VirtualClockError("clock advance must be a non-negative integer")
        increment = milliseconds * 1_000_000
        if increment > MAX_UINT64 - self._value_ns:
            raise VirtualClockError("clock advance would overflow uint64")
        self._value_ns += increment
        return self._value_ns

    def set_ns(self, value_ns: int) -> int:
        """Set virtual time for tests; moving backwards is forbidden."""

        if (
            isinstance(value_ns, bool)
            or not isinstance(value_ns, int)
            or not 0 <= value_ns <= MAX_UINT64
        ):
            raise VirtualClockError("clock value must be a uint64-compatible integer")
        if value_ns < self._value_ns:
            raise VirtualClockError("clock cannot move backwards")
        self._value_ns = value_ns
        return self._value_ns


__all__ = ["VirtualClockError", "VirtualMonotonicClock"]
