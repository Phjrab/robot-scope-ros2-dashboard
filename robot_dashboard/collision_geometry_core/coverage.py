"""Bounded motion-volume coverage, not absence-of-detections clearance.

Currently only explicitly generated closed synthetic scenes can qualify. Real
ray/voxel coverage integration remains MOTION_COVERAGE_NOT_QUALIFIED. A caller
cannot relabel replay evidence SYNTHETIC to pass; evidence kinds must match.
"""

import math
import numpy as np

from .geometry import vector


def qualifies(evidence, state, *, volume_min, volume_max, horizon_s):
    if not isinstance(evidence, dict):
        return False
    try:
        return bool(
            state["evidence_kind"] == evidence["evidence_kind"] == "SYNTHETIC"
            and evidence["kind"] == "GENERATED_CLOSED_SCENE_VOLUME"
            and evidence["complete_for_motion"] is True
            and evidence["source_refs"]
            and all(
                evidence[k] == state[k]
                for k in ("source_epoch", "clock_domain", "frame_key", "map_binding")
            )
            and math.isfinite(evidence["horizon_s"])
            and evidence["horizon_s"] >= horizon_s
            and int(evidence["valid_from_ns"]) <= int(state["stamp_ns"])
            and int(evidence["valid_until_ns"])
            >= int(state["stamp_ns"]) + math.ceil(horizon_s * 1e9)
            and np.all(vector(evidence["volume_min"]) <= volume_min)
            and np.all(vector(evidence["volume_max"]) >= volume_max)
        )
    except (KeyError, ValueError, TypeError, OverflowError):
        return False
