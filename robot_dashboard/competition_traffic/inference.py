"""Fixed, label-independent search profiles and native-coordinate fusion."""
from __future__ import annotations

import hashlib
import json
from experiments.competition_vm.traffic_signals.detector import iou

PROFILES = {
    "full640": {"imgsz": 640, "search": "full"},
    "full960": {"imgsz": 960, "search": "full"},
    "full1280": {"imgsz": 1280, "search": "full"},
    "upper-overlap640": {"imgsz": 640, "search": "full_plus_upper_overlap"},
}


def settings(name, *, confidence_floor, model_sha256, emitter_profile=None):
    if name not in PROFILES:
        raise ValueError("INFERENCE_PROFILE_UNKNOWN")
    result = {"version": "c4-search.v1", "profile": name, **PROFILES[name],
              "confidence_floor": confidence_floor, "model_sha256": model_sha256,
              "device": "cpu", "rect": True, "prediction_nms_iou": .7, "max_det": 300,
              "native_fusion_iou": .5, "internal_edge_margin_px": 1,
              "upper_tiles_normalized_xyxy": [[0, 0, .5, .6], [.25, 0, .75, .6], [.5, 0, 1, .6]]}
    if emitter_profile is not None:
        from .emitter import profile_settings
        result["emitter_validation"] = profile_settings(emitter_profile)
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return result, hashlib.sha256(canonical.encode()).hexdigest()


def regions(size, profile):
    w, h = size
    boxes = [(0, 0, w, h)]
    if profile["search"] == "full_plus_upper_overlap":
        boxes.extend((round(a*w), round(b*h), round(c*w), round(d*h))
                     for a, b, c, d in profile["upper_tiles_normalized_xyxy"])
    return boxes


def interior_edge(box, region, native_size, margin=1):
    x1, y1, x2, y2 = region
    w, h = native_size
    a, b, c, d = box
    return ((x1 > 0 and a <= margin) or (y1 > 0 and b <= margin)
            or (x2 < w and c >= x2-x1-margin) or (y2 < h and d >= y2-y1-margin))


def native_nms(detections, threshold=.5):
    # Geometry/confidence only; never prefer a color or a ground-truth target.
    result = []
    for detection in sorted(detections, key=lambda d: (-d.confidence, d.bbox)):
        if all(detection.class_id != old.class_id or iou(detection.bbox, old.bbox) <= threshold for old in result):
            result.append(detection)
    return result
