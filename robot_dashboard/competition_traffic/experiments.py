"""Small frozen-weight search comparison on existing exploratory labels."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import time

import cv2

from experiments.competition_vm.traffic_signals.detector import Detection, iou
from .config import TrafficConfig, sha256_file
from .diagnose import audit_case, metrics, overlay
from .lamp import lamp_diagnostic
from .model import OwnerModel
from .emitter import PROFILE_NAME, validate_emitter
from experiments.competition_vm.traffic_signals.core import classify_roi
from .replay import write_json, dependencies


def compare(root, labels, config, model_path, output, *, acknowledge_trusted_pickle=False,
            include_confidence_ablation=False, emitter_profile=None):
    # Fixed before viewing candidate results. Labels score outputs, never crops.
    variants = [(name, .25) for name in ("full640", "full960", "full1280", "upper-overlap640")]
    if include_confidence_ablation:
        variants.extend((name, .10) for name in ("full640", "upper-overlap640"))
    if emitter_profile is not None:
        if include_confidence_ablation:
            raise ValueError("EMITTER_AUDIT_USES_ONE_FROZEN_SEARCH_PROFILE")
        variants = [("upper-overlap640", .25)]
    images = {}
    for row in labels:
        path = (root / row["image"]).resolve(strict=True)
        if root not in path.parents or sha256_file(path) != row["sha256"]:
            raise ValueError("LABEL_INPUT_CHECKSUM_OR_PATH_INVALID")
        if row["sha256"] not in images:
            images[row["sha256"]] = cv2.imread(str(path))
            if images[row["sha256"]] is None:
                raise ValueError("IMAGE_DECODE_FAILED")
    results = []
    for profile, confidence in variants:
        name = f"{profile}-conf{confidence:.2f}"
        document = json.loads(json.dumps(config.document))
        document["min_confidence"] = confidence
        cfg = TrafficConfig.parse(document)
        started = time.monotonic()
        detector = OwnerModel(model_path, cfg, acknowledge_trusted_pickle=acknowledge_trusted_pickle,
                              inference_profile=profile, emitter_profile=emitter_profile)
        setup_wall = time.monotonic()-started
        detections, diagnostics, latencies = {}, {}, []
        emitter_by_image, emitter_times = {}, []
        private = output / name
        private.mkdir()
        for digest, bgr in images.items():
            start = time.monotonic()
            ds = detector.infer(bgr)
            ds = [Detection((math.floor(d.bbox[0]), math.floor(d.bbox[1]), math.ceil(d.bbox[2]), math.ceil(d.bbox[3])),
                            d.confidence, d.class_id, d.track_id) for d in ds if d.confidence >= confidence]
            latencies.append(time.monotonic()-start)
            detections[digest] = ds
            diagnostics[digest] = dict(detector.last_diagnostics)
            if emitter_profile is not None:
                # Before/after on exactly the same detector boxes, no new search.
                colors = [classify_roi(bgr, d.bbox) for d in ds]
                began = time.monotonic()
                emitter_by_image[digest] = [validate_emitter(bgr, d.bbox, c) for d, c in zip(ds, colors)]
                emitter_times.append(time.monotonic()-began)
        records = []
        for row in labels:
            bgr, ds = images[row["sha256"]], detections[row["sha256"]]
            record = audit_case(row, bgr, ds)
            # Diagnostics on a matched detector box, always distinct from oracle.
            if emitter_profile is None and record["target_matched"] and record["localized_raw_prediction"] in ("UNKNOWN", "AMBIGUOUS"):
                chosen = max(ds, key=lambda d: iou(d.bbox, row["roi_xyxy_native"]))
                record["detector_lamp_diagnostic"] = lamp_diagnostic(bgr, chosen.bbox)
            record["native_candidates"] = [{"bbox": list(d.bbox), "confidence": d.confidence} for d in ds]
            if emitter_profile is not None:
                checks = emitter_by_image[row["sha256"]]
                after = "UNKNOWN"
                if record["target_matched"]:
                    index = max(range(len(ds)), key=lambda n: iou(ds[n].bbox, row["roi_xyxy_native"]))
                    record["emitter_validation"] = checks[index]
                    after = checks[index]["validated_state"]
                if row["label"] == "NO_LIGHT":
                    states = [c["validated_state"] for c in checks]
                    after = next((s for s in ("GREEN", "RED", "AMBIGUOUS") if s in states), "UNKNOWN")
                record["after_emitter_prediction"] = after
            records.append(record)
            cv2.imwrite(str(private / f'{row["id"]}.jpg'), overlay(bgr, ds, manual=row["roi_xyxy_native"]))
        by_class = {}
        for label in ("GREEN", "RED", "UNREADABLE", "OTHER_LIGHT", "NO_LIGHT"):
            rs = [r for r in records if r["label"] == label]
            by_class[label] = {"targets": len(rs), "matched_targets": sum(r["target_matched"] for r in rs),
                               "raw_states": dict(Counter(r["localized_raw_prediction"] for r in rs))}
        ordered = sorted(latencies)
        result = {"candidate": name, "exploratory_previously_viewed_data": True,
                  "confidence_ablation": confidence != .25, "inference_settings": detector.inference_settings,
                  "inference_settings_sha256": detector.inference_settings_sha256, "config_sha256": cfg.sha256,
                  "setup_wall_s": setup_wall, "latency_s": {"count": len(ordered), "mean": sum(ordered)/len(ordered),
                      "p95": ordered[min(len(ordered)-1, math.ceil(.95*len(ordered))-1)],
                      "max": max(ordered), "first_inference": latencies[0], "includes_cold_first_frame": True},
                  "metrics": metrics(records), "by_label": by_class,
                  "mission_other_crossing_selection": "NOT_EVALUATED_NO_VERIFIED_BINDING",
                  "records": records, "per_image_diagnostics": diagnostics}
        if emitter_profile is not None:
            result["after_emitter_by_label"] = {label: dict(Counter(r["after_emitter_prediction"] for r in records if r["label"] == label)) for label in by_class}
            result["emitter_validation_wall_s_by_image"] = emitter_times
        results.append(result)
        print(name, json.dumps(by_class), flush=True)
        write_json(output / "comparison.json", {"model_sha256": detector.sha256, "dependencies": dependencies(),
                   "ground_truth_used_as_inference_input": False, "independent_test": False,
                   "results": results, "stable_real_green": "INPUT_REQUIRED_CONTINUOUS_SEQUENCE_AND_BINDING"})
    return results


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("input-root", "labels", "config", "model", "output"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--acknowledge-trusted-pickle", action="store_true")
    p.add_argument("--include-confidence-ablation", action="store_true")
    p.add_argument("--emitter-profile", choices=(PROFILE_NAME,))
    args = p.parse_args(argv)
    root, output = Path(args.input_root).resolve(strict=True), Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    compare(root, json.loads(Path(args.labels).read_text())["records"], TrafficConfig.read(args.config),
            args.model, output, acknowledge_trusted_pickle=args.acknowledge_trusted_pickle,
            include_confidence_ablation=args.include_confidence_ablation, emitter_profile=args.emitter_profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
