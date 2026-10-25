"""One optional RGB support heuristic, not proof of emission or crossing identity.

Use the unchanged color core's ORIGINAL chromatic mask. No CLAHE pixels,
frame IDs, target coordinates, learned weights or negative-location lists.
"""
from dataclasses import asdict, dataclass

import cv2
import numpy as np


PROFILE_NAME = "enclosed-chroma-v1"


@dataclass(frozen=True)
class EmitterProfile:
    name: str = PROFILE_NAME
    min_crop_side: int = 12
    frame_edge_margin: int = 1
    component_margin: int = 2
    min_component_pixels: int = 12
    max_components: int = 32
    max_area_fraction: float = .25
    max_width_fraction: float = .65
    max_height_fraction: float = .55
    center_x_min: float = .20
    center_x_max: float = .80
    min_component_median_value: float = 160.
    min_value_contrast: float = 60.
    enclosure_value_drop: float = 40.
    min_dark_enclosure_fraction: float = .65
    ring_radius_fraction: float = .15
    min_ring_radius: int = 2


PROFILE = EmitterProfile()


def profile_settings(name):
    if name != PROFILE_NAME:
        raise ValueError("EMITTER_PROFILE_UNKNOWN")
    return asdict(PROFILE)


def validate_emitter(bgr, bbox, color, *, encoding="bgr8"):
    """Return supported color or UNKNOWN; never alter the raw diagnostic color.

    Intensity means HSV V, not calibrated luminance/radiance. A bright printed
    or reflected object can satisfy these priors: supported != verified front.
    """
    result = {"profile": PROFILE_NAME, "raw_state": color.get("raw_state", "UNKNOWN"),
              "validated_state": "UNKNOWN", "supported": False, "reasons": [],
              "components": [], "crossing_identity_verified": False,
              "physical_emission_proven": False, "color_reconstruction_claimed": False}

    def reject(reason):
        result["reasons"] = [reason]
        return result

    p = PROFILE
    if (encoding != "bgr8" or not isinstance(bgr, np.ndarray) or bgr.dtype != np.uint8
            or bgr.ndim != 3 or bgr.shape[2] != 3):
        return reject("ENCODING_MISMATCH")
    if len(bbox) != 4 or any(type(x) is not int for x in bbox):
        return reject("NATIVE_INTEGER_BOX_REQUIRED")
    x1, y1, x2, y2 = bbox
    h, w = bgr.shape[:2]
    if (x1 <= p.frame_edge_margin or y1 <= p.frame_edge_margin
            or x2 >= w-p.frame_edge_margin or y2 >= h-p.frame_edge_margin):
        return reject("FRAME_EDGE_OR_TRUNCATED")
    cw, ch = x2-x1, y2-y1
    if min(cw, ch) < p.min_crop_side:
        return reject("INSUFFICIENT_CONTEXT_SIZE")
    if color.get("quality_flags") or color.get("raw_state") not in ("RED", "GREEN"):
        return reject("RAW_COLOR_UNRESOLVED")
    mask = color.get("mask")
    if not isinstance(mask, np.ndarray) or mask.shape != (ch, cw, 3) or mask.dtype != np.uint8:
        return reject("ORIGINAL_CHROMA_MASK_REQUIRED")
    channel = 1 if color["raw_state"] == "GREEN" else 2
    count, labels, stats, centers = cv2.connectedComponentsWithStats((mask[:, :, channel] == 255).astype(np.uint8), 8)
    ids = [n for n in range(1, count) if stats[n, cv2.CC_STAT_AREA] >= p.min_component_pixels]
    if not ids or len(ids) > p.max_components:
        return reject("COMPONENT_COUNT_UNSUPPORTED")
    value = cv2.cvtColor(bgr[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)[:, :, 2]
    for n in ids:
        x, y, width, height, area = map(int, stats[n])
        component = labels == n
        radius = max(p.min_ring_radius, round(p.ring_radius_fraction * max(width, height)))
        ring = cv2.dilate(component.astype(np.uint8), np.ones((2*radius+1, 2*radius+1), np.uint8)).astype(bool) & ~component
        median = float(np.median(value[component]))
        ring_median = float(np.median(value[ring])) if ring.any() else median
        contrast = median-ring_median
        dark_fraction = float(np.mean(value[ring] <= median-p.enclosure_value_drop)) if ring.any() else 0.
        reasons = []
        if min(x, y, cw-x-width, ch-y-height) < p.component_margin:
            reasons.append("COMPONENT_TOUCHES_CROP_EDGE")
        if (area/(cw*ch) > p.max_area_fraction or width/cw > p.max_width_fraction
                or height/ch > p.max_height_fraction
                or not p.center_x_min <= centers[n][0]/cw <= p.center_x_max):
            reasons.append("COMPONENT_GEOMETRY_UNSUPPORTED")
        if median < p.min_component_median_value:
            reasons.append("COMPONENT_NOT_BRIGHT")
        if contrast < p.min_value_contrast or dark_fraction < p.min_dark_enclosure_fraction:
            reasons.append("DARK_ENCLOSURE_UNSUPPORTED")
        result["components"].append({"bbox_xyxy_native": [x1+x, y1+y, x1+x+width, y1+y+height],
                                     "pixels": area, "median_value": median, "ring_median_value": ring_median,
                                     "value_contrast": contrast, "dark_enclosure_fraction": dark_fraction,
                                     "supported": not reasons, "reasons": reasons})
    result["supported"] = any(c["supported"] for c in result["components"])
    if result["supported"]:
        result["validated_state"] = color["raw_state"]
    else:
        result["reasons"] = sorted({reason for c in result["components"] for reason in c["reasons"]})
    return result
