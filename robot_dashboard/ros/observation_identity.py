"""Read-only observation epochs; publisher identity never qualifies a map origin."""

from __future__ import annotations

import secrets
from typing import Any


OBSERVER_ID = secrets.token_hex(16)


def wrap_observation_callback(callback: Any, topic: str, type_name: str, is_current: Any) -> Any:
    """rclpy detects MessageInfo from exactly two required positional arguments."""
    def wrapped(message: Any, message_info: Any) -> None:
        if is_current():
            callback(topic, type_name, message, message_info=message_info)
    return wrapped


class ObservationIdentity:
    """Fence display anchors on source replacement, backwards time, or a gap.

    An RMW GID identifies a publisher lifetime, not a verified native map session.
    Missing MessageInfo is explicitly unavailable, including on older runtimes.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.epoch = secrets.token_hex(16)
        self.key: tuple[str, ...] | None = None
        self.stamp = 0
        self.received = 0.0
        self.progress_received = 0.0

    def observe(
        self, *, topic: str, frame: str, child: str = "", stamp_ns: int,
        received: float, message_info: Any = None, publisher_count: int | None = None,
    ) -> dict[str, Any]:
        try:
            raw_gid = bytes(message_info.publisher_gid)
            gid = raw_gid.hex() if len(raw_gid) in {16, 24} and any(raw_gid) else None
        except (AttributeError, TypeError, ValueError):
            gid = None
        valid = gid is not None and publisher_count == 1 and stamp_ns > 0
        key = (topic, frame, child, gid or "", str(publisher_count))
        reason = None
        if self.key != key or stamp_ns != self.stamp:
            self.progress_received = received
        elif received - self.progress_received > 1.0:
            valid = False
            reason = "SOURCE_STAMP_STALLED"
        if self.key is not None:
            if key != self.key:
                reason = "SOURCE_CHANGED"
            elif stamp_ns < self.stamp:
                reason = "SOURCE_TIME_REVERSED"
            elif received - self.received > 1.0:
                reason = "RECEIPT_GAP"
            if reason:
                self.epoch = secrets.token_hex(16)
        self.key, self.stamp, self.received = key, stamp_ns, received
        return {
            "observer_id": OBSERVER_ID,
            "publisher_epoch": self.epoch,
            "publisher_gid": gid,
            "publisher_count": publisher_count,
            "identity_status": "OBSERVED_PUBLISHER" if valid else "UNAVAILABLE",
            "identity_basis": "RMW_MESSAGE_INFO",
            "native_session_id": None,
            "source_stamp_ns": str(stamp_ns),
            "source_clock": "ROS_HEADER_UNVERIFIED",
            "received_monotonic_s": received,
            "receipt_clock": "OBSERVER_HOST_MONOTONIC",
            "reset_reason": reason,
            "origin_verified": False,
        }
