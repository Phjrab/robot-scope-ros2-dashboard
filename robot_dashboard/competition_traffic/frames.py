"""Frame transfer boundary. No camera acquisition, subscription or network client."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Protocol

import cv2
import numpy as np

from .config import finite, identity


@dataclass(frozen=True)
class Frame:
    bgr: object
    source_id: str
    producer_epoch: str
    sequence: int
    source_stamp_ns: str
    source_clock: str
    source_age_s: float | None
    received_s: float
    clock_verified: bool
    provenance: str
    image_handle: str
    binding_id: str
    exposure_settling: bool = False
    exposure_metadata: dict = field(default_factory=dict)
    original_metadata: dict = field(default_factory=dict)
    identity_verified: bool = False

    def validate(self):
        if not all(identity(v) for v in (
            self.source_id, self.producer_epoch, self.image_handle, self.binding_id
        )):
            raise ValueError("FRAME_ID_INVALID")
        if type(self.sequence) is not int or not 0 <= self.sequence < 2**63:
            raise ValueError("FRAME_SEQUENCE_INVALID")
        if not isinstance(self.source_stamp_ns, str) or not re.fullmatch(r"[0-9]{1,24}", self.source_stamp_ns):
            raise ValueError("SOURCE_STAMP_INVALID")
        if self.source_clock not in ("fixture", "synchronized_ros", "synchronized_utc"):
            raise ValueError("SOURCE_CLOCK_UNSUPPORTED")
        if any(type(v) is not bool for v in (self.clock_verified, self.identity_verified, self.exposure_settling)):
            raise ValueError("FRAME_BOOLEAN_INVALID")
        if not finite(self.received_s, 0, 1e16):
            raise ValueError("RECEIPT_TIME_INVALID")
        if self.source_age_s is not None and not finite(self.source_age_s, 0, 3600):
            raise ValueError("SOURCE_AGE_INVALID")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("PROVENANCE_REQUIRED")
        if (not isinstance(self.exposure_metadata, dict) or len(self.exposure_metadata) > 16
                or any(not isinstance(k, str) or not finite(v, -1e16, 1e16)
                       for k, v in self.exposure_metadata.items())):
            raise ValueError("EXPOSURE_METADATA_INVALID")


class FrameSink(Protocol):
    def process(self, frame: Frame, *, now_s: float):
        """Called by the existing owner with a receiver-local monotonic reading."""


def decode_jpeg(payload: bytes):
    if not isinstance(payload, bytes) or not 0 < len(payload) <= 4 * 1024 * 1024:
        return None
    return cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)


def from_owner_jpeg(payload: bytes, *, source_id, producer_epoch, sequence,
                    source_stamp_ns, source_clock, source_age_s, received_s,
                    clock_verified, provenance, binding_id, identity_verified=False, exposure_settling=False):
    """Accept bytes already acquired by the camera owner; never open a device.

    Do not use another host's `updated` monotonic as received_s. The owner must
    supply its actual source epoch/sequence, not a polling counter.
    """
    handle = hashlib.sha256(payload).hexdigest()
    return Frame(decode_jpeg(payload), source_id, producer_epoch, sequence,
                 source_stamp_ns, source_clock, source_age_s, received_s,
                 clock_verified, provenance, handle, binding_id, identity_verified=identity_verified,
                 exposure_settling=exposure_settling)
