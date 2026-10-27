"""Opt-in observation consensus for the teammate's three-class detector.

Model color remains diagnostic evidence. It cannot fill missing chroma, turn a
conflicting RED into GREEN, or establish a mission/crossing identity.
"""
from __future__ import annotations

from experiments.competition_vm.traffic_signals.core import ColorProfile

POLICY = "teammate-color-consensus-v1"
SIGNAL_CLASSES = {"0": "traffic_light_green", "1": "traffic_light_red"}
MODEL_CLASSES = {**SIGNAL_CLASSES, "2": "crosswalk"}
COLORS = {"traffic_light_green": "GREEN", "traffic_light_red": "RED"}


def policy_settings(name):
    if name != POLICY:
        raise ValueError("COLOR_POLICY_UNKNOWN")
    return {"name": POLICY, "model_classes": dict(MODEL_CLASSES),
            "signal_classes": dict(SIGNAL_CLASSES),
            "color_profile_sha256": ColorProfile().sha256,
            "agreement_required": True, "conflict_state": "AMBIGUOUS",
            "missing_color_state": "UNKNOWN"}


def combine(color, class_name):
    """Return a copy; preserve the original C4 result and its quality evidence."""
    model_state = COLORS.get(class_name)
    c4_state = color["raw_state"]
    reasons = []
    state = c4_state
    if model_state is None:
        state = "UNKNOWN"
        reasons.append("MODEL_COLOR_UNAVAILABLE")
    elif color["quality_flags"]:
        state = "UNKNOWN"
        reasons.append("COLOR_QUALITY_REJECTED")
    elif c4_state in ("RED", "GREEN"):
        if model_state != c4_state:
            state = "AMBIGUOUS"
            reasons.append("MODEL_COLOR_CONFLICT")
    elif c4_state == "AMBIGUOUS":
        reasons.append("COLOR_AMBIGUOUS")
    else:
        state = "UNKNOWN"
        reasons.append("COLOR_EVIDENCE_MISSING")
    diagnostic = {"policy": POLICY, "model_state": model_state,
                  "c4_raw_state": c4_state, "final_state": state,
                  "reasons": reasons}
    result = {**color, "raw_state": state,
              "quality_flags": list(dict.fromkeys(color["quality_flags"] + reasons)),
              "score": color.get("score", 0.) if state in ("RED", "GREEN") else 0.}
    return result, diagnostic
