"""Private local visual audit. Labels never enter production detector/association.

Evaluate frozen detector outputs against target rectangles, and classify manual
crops as a separately reported oracle diagnostic. No retraining or threshold fit.
All images/overlays stay in the caller's new private output directory.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path

import cv2
import numpy as np

from experiments.competition_vm.traffic_signals.core import classify_roi
from experiments.competition_vm.traffic_signals.detector import Detection, iou
from .config import TrafficConfig, sha256_file
from .model import OwnerModel
from .replay import write_json


def audit_case(label, bgr, detections):
    box = label["roi_xyxy_native"]
    matches = sorted(((iou(d.bbox, box), d) for d in detections), key=lambda x: x[0], reverse=True) if box else []
    matched = bool(matches and matches[0][0] >= .2)
    # Localization-conditioned color is not a production binding or stable state.
    color = classify_roi(bgr, matches[0][1].bbox) if matched else None
    oracle = classify_roi(bgr, box) if box else None
    emitter = label.get("emitter_roi_native")
    emitter_metrics = None
    if emitter:
        x1, y1, x2, y2 = emitter
        pixels = bgr[y1:y2, x1:x2]
        hsv = cv2.cvtColor(pixels, cv2.COLOR_BGR2HSV)
        emitter_metrics = {"red_channel_ge_250_fraction": float(np.mean(pixels[:, :, 2] >= 250)),
                           "saturation_below_55_fraction": float(np.mean(hsv[:, :, 1] < 55)),
                           "white_all_channels_ge_250_fraction": float(np.mean(np.all(pixels >= 250, axis=2)))}
    def clean(c):
        return None if c is None else {k: v for k, v in c.items() if k != "mask"}
    predicted = color["raw_state"] if color else "UNKNOWN"
    # NO_LIGHT is an image-level negative: a false GREEN anywhere counts even
    # though there is deliberately no target rectangle to match.
    negative_states = []
    if label["label"] == "NO_LIGHT":
        negative_states = [classify_roi(bgr, d.bbox)["raw_state"] for d in detections]
        predicted = next((state for state in ("GREEN", "RED", "AMBIGUOUS") if state in negative_states), "UNKNOWN")
    return {"id": label["id"], "sha256": label["sha256"], "label": label["label"], "split": label["split"],
            "candidate_count": len(detections), "target_matched": matched,
            "negative_image_candidate_states": negative_states,
            "max_target_iou": matches[0][0] if matches else None,
            "localized_raw_prediction": predicted, "stable_prediction": "NOT_EVALUATED_UNVERIFIED_BINDING",
            "rejection": ("NO_CANDIDATE" if not detections else "TARGET_NOT_MATCHED" if not matched else
                          "COLOR_REJECTED" if predicted not in ("RED", "GREEN") else None),
            "matched_crop_color": clean(color), "manual_crop_oracle": clean(oracle),
            "emitter_metrics": emitter_metrics}


def metrics(records):
    readable = [r for r in records if r["label"] in ("RED", "GREEN")]
    green = [r for r in records if r["label"] == "GREEN"]
    negatives = [r for r in records if r["label"] in ("RED", "OTHER_LIGHT", "NO_LIGHT")]
    return {"target_cases": len(records), "unique_images": len({r["sha256"] for r in records}),
            "labels": dict(Counter(r["label"] for r in records)),
            "localized_raw_predictions": dict(Counter(r["localized_raw_prediction"] for r in records)),
            "readable_unknown": {"count": sum(r["localized_raw_prediction"] == "UNKNOWN" for r in readable), "denominator": len(readable)},
            "false_green": {"count": sum(r["localized_raw_prediction"] == "GREEN" for r in negatives), "denominator": len(negatives)},
            "valid_green_rejected": {"count": sum(r["localized_raw_prediction"] != "GREEN" for r in green), "denominator": len(green)},
            "rejections": dict(Counter(r["rejection"] for r in records if r["rejection"])),
            "unreadable_excluded_from_correctness_denominators": True,
            "production_stable_metrics": "NOT_EVALUATED_BINDING_UNVERIFIED"}


def overlay(bgr, detections, expected=None, manual=None):
    image = bgr.copy()
    for d in detections:
        cv2.rectangle(image, (int(d.bbox[0]), int(d.bbox[1])), (int(d.bbox[2]), int(d.bbox[3])), (255, 255, 0), 2)
    for box, color in ((expected, (0, 255, 255)), (manual, (255, 0, 255))):
        if box:
            cv2.rectangle(image, tuple(box[:2]), tuple(box[2:]), color, 2)
    return image


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("input-root", "labels", "config", "model", "output"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--acknowledge-trusted-pickle", action="store_true")
    args = p.parse_args(argv)
    root, output = Path(args.input_root).resolve(strict=True), Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    cfg = TrafficConfig.read(args.config)
    detector = OwnerModel(args.model, cfg, acknowledge_trusted_pickle=args.acknowledge_trusted_pickle)
    labels = json.loads(Path(args.labels).read_text())["records"]
    records, tiles, cache = [], [], {}
    for label in labels:
        path = (root / label["image"]).resolve(strict=True)
        if root not in path.parents or sha256_file(path) != label["sha256"]:
            raise ValueError("LABEL_INPUT_CHECKSUM_OR_PATH_INVALID")
        key = label["sha256"]
        if key not in cache:
            bgr = cv2.imread(str(path))
            if bgr is None:
                raise ValueError("LABEL_IMAGE_DECODE_FAILED")
            ds = detector.infer(bgr)
            # Use exactly the production floor/ceil native-coordinate rounding.
            ds = [Detection((math.floor(d.bbox[0]), math.floor(d.bbox[1]), math.ceil(d.bbox[2]), math.ceil(d.bbox[3])),
                            d.confidence, d.class_id, d.track_id) for d in ds if d.confidence >= cfg.document["min_confidence"]]
            cache[key] = bgr, ds
        bgr, ds = cache[key]
        result = audit_case(label, bgr, ds)
        records.append(result)
        expected = cfg.document["association"]["expected_roi_native"] if label["source"] == "go2_front" and label["split"] == "diagnostic_v3" else None
        marked = overlay(bgr, ds, expected, label["roi_xyxy_native"])
        cv2.imwrite(str(output / (label["id"] + "-overlay.jpg")), marked)
        tile = np.full((350, 640, 3), 235, np.uint8)
        tile[35:305, :480] = cv2.resize(marked, (480, 270))
        box = label["roi_xyxy_native"]
        if box:
            x1, y1, x2, y2 = box
            crop = bgr[y1:y2, x1:x2]
            cv2.imwrite(str(output / (label["id"] + "-native.png")), crop)
            scale = min(150/crop.shape[1], 260/crop.shape[0])
            enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
            tile[35:35+enlarged.shape[0], 485:485+enlarged.shape[1]] = enlarged
        text = f'{label["id"]}: GT={label["label"]} raw={result["localized_raw_prediction"]}'
        cv2.putText(tile, text, (5, 22), cv2.FONT_HERSHEY_SIMPLEX, .48, (0, 0, 0), 1)
        cv2.putText(tile, 'cyan: detector  yellow: expected  magenta: labeled target', (5, 327), cv2.FONT_HERSHEY_SIMPLEX, .43, (0, 0, 0), 1)
        tiles.append(tile)
    for start in range(0, len(tiles), 8):
        page = tiles[start:start+8]
        while len(page) % 2:
            page.append(np.full_like(tiles[0], 235))
        cv2.imwrite(str(output / f'contact-{start//8+1}.jpg'), np.vstack([np.hstack(page[i:i+2]) for i in range(0, len(page), 2)]))
    write_json(output / 'evaluation.json', {"metrics": metrics(records),
               "by_split": {s: metrics([r for r in records if r["split"] == s]) for s in sorted({r["split"] for r in records})},
               "records": records, "config_sha256": cfg.sha256, "model_sha256": detector.sha256,
               "labels_sha256": sha256_file(Path(args.labels)), "ground_truth_used_only_for_scoring_and_oracle": True})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
