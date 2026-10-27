"""Offline A/B/C comparison on identical native boxes; no upstream ROS imports.

Only the explicitly acknowledged, hash-pinned color module is executed. It stays
outside this repository. Output contains private paths/observations: keep local.
Labels are scoring inputs only, never inference crops or association bindings.
"""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
import math
from pathlib import Path
import time

import cv2

from experiments.competition_vm.traffic_signals.detector import iou
from .config import TrafficConfig, finite, sha256_file
from .consensus import POLICY
from .frames import Frame
from .model import OwnerModel
from .pipeline import TrafficPipeline

UPSTREAM_COLOR_SHA256 = "9331a55201ef69a45a3ed208d34b157cdbc563be26f26a06c3f5b8bd296a2c10"


def load_comparator(path, *, acknowledge_source=False):
    if not acknowledge_source:
        raise ValueError("UPSTREAM_SOURCE_ACK_REQUIRED")
    path = Path(path).resolve(strict=True)
    if sha256_file(path) != UPSTREAM_COLOR_SHA256:
        raise ValueError("UPSTREAM_COLOR_CHECKSUM_MISMATCH")
    spec = importlib.util.spec_from_file_location("c4_private_color_comparison", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TrafficLightColorDetector()


def compare_color(comparator, image, box):
    """Guard geometry before upstream cvtColor; do not repair its color logic."""
    h, w = image.shape[:2]
    if (len(box) != 4 or not all(finite(x, 0, max(w, h)) for x in box)
            or not 0 <= box[0] < box[2] <= w or not 0 <= box[1] < box[3] <= h
            or int(box[0]) >= int(box[2]) or int(box[1]) >= int(box[3])):
        return {"state": "UNKNOWN", "reason": "INVALID_NATIVE_CROP"}
    start = time.perf_counter()
    try:
        result = {}
        for key, method in (("rgb", comparator.detect_color),
                            ("hsv", comparator.detect_color_by_hue),
                            ("combined", comparator.detect_color_combined)):
            called = time.perf_counter()
            state, score = method(image, box)
            result[key] = {"state": state, "uncalibrated_score": float(score),
                           "wall_s": time.perf_counter()-called}
        return {**result, "state": result["combined"]["state"],
                "diagnostic_total_wall_s": time.perf_counter()-start, "score_is_probability": False}
    except Exception as exc:
        return {"state": "UNKNOWN", "reason": "UPSTREAM_COLOR_EXCEPTION",
                "exception_type": type(exc).__name__, "wall_s": time.perf_counter()-start}


def score_target(label, records):
    roi = label["roi_xyxy_native"]
    ranked = sorted(((iou(r["bbox_xyxy_native"], roi), r) for r in records),
                    key=lambda p: p[0], reverse=True) if roi else []
    matched = bool(ranked and ranked[0][0] >= .2)
    candidates = records if label["label"] == "NO_LIGHT" else [ranked[0][1]] if matched else []
    def choose(field):
        states = [r[field] for r in candidates]
        return next((s for s in ("GREEN", "RED", "AMBIGUOUS") if s in states), "UNKNOWN")
    return {"id": label["id"], "sha256": label["sha256"], "label": label["label"],
            "target_matched": matched, "max_iou": ranked[0][0] if ranked else None,
            "predictions": {key: choose(field) for key, field in
                            (("A_model", "model_state"), ("B_c4", "c4_raw_state"),
                             ("C_upstream", "upstream_state"), ("candidate", "raw_state"))}}


def summarize(records):
    result = {}
    for key in ("A_model", "B_c4", "C_upstream", "candidate"):
        by_label = {}
        for label in sorted({r["label"] for r in records}):
            rows = [r for r in records if r["label"] == label]
            by_label[label] = {"n": len(rows), "matched": sum(r["target_matched"] for r in rows),
                               "states": dict(Counter(r["predictions"][key] for r in rows))}
        result[key] = by_label
    return result


def latency(values):
    if not values:
        return {"n": 0, "status": "NOT_RUN"}
    values = sorted(values)
    return {"n": len(values), "mean_s": sum(values)/len(values),
            "p95_s": values[math.ceil(.95*len(values))-1], "max_s": values[-1]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("input-root", "labels", "config", "model", "upstream-color", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--acknowledge-trusted-pickle", action="store_true")
    parser.add_argument("--acknowledge-upstream-source", action="store_true")
    args = parser.parse_args(argv)
    cfg = TrafficConfig.read(args.config)
    if cfg.document.get("color_policy") != POLICY:
        raise ValueError("EXPLICIT_TEAMMATE_POLICY_REQUIRED")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    comparator = load_comparator(args.upstream_color, acknowledge_source=args.acknowledge_upstream_source)
    start = time.perf_counter()
    detector = OwnerModel(args.model, cfg, acknowledge_trusted_pickle=args.acknowledge_trusted_pickle)
    setup = time.perf_counter()-start
    pipeline = TrafficPipeline(cfg, detector, observation_mode="detection-only", measure_wall_latency=True)
    root = Path(args.input_root).resolve(strict=True)
    labels = json.loads(Path(args.labels).read_text())["records"]
    cache, scored, missing, durations = {}, [], [], []
    for label in labels:
        path = (root / label["image"]).resolve()
        if root not in path.parents:
            raise ValueError("LABEL_PATH_OUTSIDE_ROOT")
        if not path.is_file():
            missing.append({"id": label["id"], "image": label["image"]})
            continue
        if sha256_file(path) != label["sha256"]:
            raise ValueError("LABEL_INPUT_CHECKSUM_MISMATCH")
        key = label["sha256"]
        if key not in cache:
            image = cv2.imread(str(path))
            if image is None:
                raise ValueError("LABEL_IMAGE_DECODE_FAILED")
            # Static images have no verified source clock; each is a new epoch.
            now = time.monotonic()
            frame = Frame(image, "offline-static", f"static-{len(cache)}", 0, "0", "fixture",
                          None, now, False, "STATIC_RGB_DIAGNOSTIC_NOT_TEMPORAL", key,
                          cfg.document["association"]["binding_id"],
                          original_metadata={"input_sha256": key, "image": label["image"]})
            observation = pipeline.process(frame, now_s=now)
            durations.append(observation.context["pipeline_wall_s"])
            for record in observation.context["free_observations"]:
                record["upstream_comparison"] = compare_color(comparator, image, record["bbox_xyxy_native"])
                record["upstream_state"] = record["upstream_comparison"]["state"]
            cache[key] = observation.json_record()
        scored.append(score_target(label, cache[key]["context"]["free_observations"]))
    status = ("STATIC_RGB_PARTIAL" if missing else "STATIC_RGB_TESTED") if scored else "STATIC_RGB_NOT_RUN_INPUT_MISSING"
    result = {"status": status,
              "model_sha256": detector.sha256, "names": detector.names,
              "config_sha256": cfg.sha256, "inference_settings_sha256": detector.inference_settings_sha256,
              "inference_settings": detector.inference_settings, "upstream_color_sha256": UPSTREAM_COLOR_SHA256,
              "labels_sha256": sha256_file(Path(args.labels)), "model_setup_s": setup,
              "unique_images": len(cache), "target_cases": len(scored), "missing": missing,
              "pipeline_latency": latency(durations), "first_pipeline_s": durations[0] if durations else None,
              "comparison": summarize(scored), "records": scored,
              "scope": "Previously inspected diagnostic set; not independent accuracy or temporal/Jetson evidence",
              "departure_authorized": False}
    (output / "comparison.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    (output / "observations.jsonl").write_text("".join(json.dumps(v, allow_nan=False)+"\n" for v in cache.values()))
    print(json.dumps({k: result[k] for k in ("status", "unique_images", "target_cases", "pipeline_latency")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
