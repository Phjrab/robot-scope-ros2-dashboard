"""Partial signal fields plus availability; never manufacture mission Evidence."""
from __future__ import annotations

import copy

from .config import finite


def signal_fragment(observation, *, now_s, received_s=None):
    """Use the first local receipt recorded by the pipeline, never a poll time.

    The legacy received_s argument may only confirm that same first receipt.
    Cross-process delivery needs a trusted age transfer in C1/C2; these local
    monotonic values cannot be subtracted on another host.
    """
    c = observation.context
    if c["source_clock"] == "fixture":
        raise ValueError("OFFLINE_REPLAY_NOT_ROBOT_EVIDENCE")
    first = c["first_received_s"]
    age = c["source_age_at_first_receipt_s"]
    if received_s is not None and (not finite(received_s, 0, 1e16) or received_s != first):
        raise ValueError("FIRST_RECEIPT_MISMATCH")
    if (not c["association_verified"] or not c["clock_verified"] or not c["identity_verified"]
            or age is None or not finite(now_s, 0, 1e16) or now_s < c["processed_s"]
            or not 0 <= now_s - first <= .25 or age + now_s - first > .25):
        raise ValueError("SIGNAL_EVIDENCE_EXPIRED")
    result = copy.deepcopy(observation.signal)
    if result["quality_flags"]:
        result["stable_state"] = "UNKNOWN"
    return result


def signal_status(pipeline, *, now_s):
    """Read-only availability. Repeated reads do not mint identity or refresh TTL."""
    obs = pipeline.latest
    status = {"fragment": None, "reasons": [],
              "last_valid_observation_s": pipeline.last_valid_observation_s,
              "identity": None, "first_received_s": None}
    if obs is None:
        status["reasons"] = ["NO_OBSERVATION"]
        return status
    c = obs.context
    status["identity"] = {k: c[k] for k in ("source_id", "producer_epoch", "sequence", "source_stamp_ns", "binding_id")}
    status["first_received_s"] = c["first_received_s"]
    try:
        fragment = signal_fragment(obs, now_s=now_s)
    except ValueError as exc:
        status["reasons"] = [str(exc)]
    else:
        status["reasons"] = list(fragment["quality_flags"])
        if not status["reasons"]:
            status["fragment"] = fragment
    return status
