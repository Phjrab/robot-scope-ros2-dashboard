"""Separate decoded originals, exact native crops and VM diagnostic masks."""
from __future__ import annotations

import hashlib
from pathlib import Path

import cv2

from .config import sha256_file


def detection_overlay(bgr, observation):
    """All boxes are free observations, never mission signal identities."""
    image = bgr.copy()
    for candidate in observation.context.get("free_observations", []):
        x1, y1, x2, y2 = candidate["bbox_xyxy_native"]
        color = {"GREEN": (0, 220, 0), "RED": (0, 0, 255)}.get(candidate["raw_state"], (255, 255, 0))
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        cv2.putText(image, "raw " + candidate["raw_state"], (max(0, x1), max(36, y1-4)),
                    cv2.FONT_HERSHEY_SIMPLEX, .45, color, 1)
    stage = observation.context.get("observation_stage", "detection-only")
    cv2.putText(image, "Boxes: detection-only | signal stage: " + stage, (4, 18),
                cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1)
    return image


def save_images(root, frame, observation):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    entries = {}
    if frame.bgr is None or observation.signal["native_image_size"] is None:
        return entries
    index = f"{frame.sequence:08d}"
    candidates = {"decoded_original_bgr": (f"{index}-original.png", frame.bgr)}
    candidates["detection_only_overlay"] = (f"{index}-detections.png", detection_overlay(frame.bgr, observation))
    roi = observation.signal["roi_xyxy_native"]
    if roi is not None:
        x1, y1, x2, y2 = roi
        h, w = frame.bgr.shape[:2]
        crop = frame.bgr[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if crop.size:
            candidates["native_roi_crop"] = (f"{index}-roi.png", crop)
    if observation.mask is not None:
        candidates["processed_color_mask"] = (f"{index}-mask.png", observation.mask)
    for kind, (name, pixels) in candidates.items():
        path = root / name
        if path.exists():
            raise ValueError("ARTIFACT_EXISTS")
        if not cv2.imwrite(str(path), pixels):
            raise OSError("ARTIFACT_WRITE_FAILED")
        handle = hashlib.sha256((frame.image_handle + kind).encode()).hexdigest()
        entries[kind] = {"image_handle": handle, "relative_path": "frames/" + name,
                         "sha256": sha256_file(path), "size_bytes": path.stat().st_size,
                         "encoding": "PNG/BGR decoded by OpenCV"}
        if kind == "decoded_original_bgr":
            observation.signal["native_image"] = handle
        elif kind == "processed_color_mask":
            observation.signal["processed_image"] = handle
    return entries
