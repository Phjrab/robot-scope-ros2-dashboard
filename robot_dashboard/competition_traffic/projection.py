"""Partial, validated signal fields for C2; never fabricate full Evidence."""
from __future__ import annotations

import copy

from .config import finite


def signal_fragment(observation, *, now_s, received_s):
    """Receiver supplies local arrival time; foreign host clocks are not inputs.

    C2 must validate the source identity, epoch, sequence and mission binding and
    join independent navigation/foot/stop evidence. This result cannot itself be
    submitted as competition-evidence.v0.1 (required mission fields are absent).
    Offline fixture records are rejected from this production projection.
    """
    c = observation.context
    if c["source_clock"] == "fixture":
        raise ValueError("OFFLINE_REPLAY_NOT_ROBOT_EVIDENCE")
    if (not c["association_verified"] or not c["clock_verified"] or c["source_age_s"] is None
            or not finite(now_s, 0, 1e16) or not finite(received_s, 0, 1e16)
            or now_s < received_s or now_s - received_s > .25
            or c["source_age_s"] + now_s - received_s > .25):
        raise ValueError("SIGNAL_EVIDENCE_EXPIRED")
    result = copy.deepcopy(observation.signal)
    if result["quality_flags"]:
        result["stable_state"] = "UNKNOWN"
    return result
