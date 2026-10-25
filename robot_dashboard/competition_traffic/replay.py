"""Offline CLI: no camera, network endpoint, model download or robot startup."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time

from .config import TrafficConfig, sha256_file


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def dependencies():
    result = {"python": platform.python_version()}
    for name in ("numpy", "opencv-python", "ultralytics", "torch"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    try:
        import cv2
        result["cv2_runtime"] = cv2.__version__
    except ImportError:
        result["cv2_runtime"] = None
    return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, help="Existing local image, directory, Robot Scope dataset or video")
    p.add_argument("--output", required=True, help="New directory; never overwrite an earlier run")
    p.add_argument("--model", help="Explicit owner-supplied local PT/ONNX; never downloaded")
    p.add_argument("--config", help="Explicit model/class-map/association JSON")
    p.add_argument("--fps", type=float, help="Required virtual replay rate; not a sensor clock")
    p.add_argument("--clock-mode", choices=("source-timeline", "wall-clock"), default="source-timeline")
    p.add_argument("--max-frames", type=int, default=10000)
    p.add_argument("--dry-run", action="store_true", help="Hash and decode inputs without loading a model")
    p.add_argument("--acknowledge-trusted-pickle", action="store_true")
    return p


def run(args, output):
    from .replay_input import inspect_inputs, iter_frames
    from .replay_clock import ReplayClock

    items = inspect_inputs(args.input, max_frames=args.max_frames)
    manifest = {"schema_version": "traffic-replay-manifest.v0.1", "input_files": [x.manifest() for x in items],
                "model": None, "config": None, "dependencies": dependencies(),
                "clock_mode": args.clock_mode,
                "clock": "offline fixture only; recorded captured_at is NOT a verified sensor clock",
                "sampling": "all supplied frames in order; fps only fills missing replay_time_s",
                "labels_used_as_detector_input": False, "command": [sys.executable, "-m", __package__ + ".replay", *sys.argv[1:]]}
    missing = []
    config = TrafficConfig.read(args.config) if args.config else None
    if config is None:
        missing.append("CLASS_MAP_AND_SIGNAL_BINDING_CONFIG")
    else:
        manifest["config"] = {"path": str(Path(args.config).resolve()), "sha256": sha256_file(Path(args.config)),
                              "canonical_sha256": config.sha256}
    if args.model:
        model_path = Path(args.model).resolve(strict=True)
        if not model_path.is_file() or model_path.suffix.lower() not in (".pt", ".onnx"):
            raise ValueError("LOCAL_MODEL_FILE_REQUIRED")
        digest = sha256_file(model_path)
        manifest["model"] = {"path": str(model_path), "sha256": digest, "size_bytes": model_path.stat().st_size,
                             "provenance": config.document["model"]["provenance"] if config else None}
        if config and digest != config.document["model"]["sha256"]:
            raise ValueError("MODEL_CHECKSUM_MISMATCH")
    else:
        missing.append("OWNER_TRAFFIC_MODEL")
    write_json(output / "manifest.json", manifest)
    summary = {"status": "INPUT_REQUIRED" if missing else "PASS", "missing_inputs": missing,
               "real_model_inference": "NOT_RUN", "real_rgb_decode": "NOT_RUN",
               "real_rgb_detection_replay": "NOT_RUN", "robot_observation": "NOT_RUN",
               "traffic_accuracy": None, "exposure_problem_resolved": False,
               "input_files": len(items), "frames": 0, "decode_errors": 0,
               "quality_flags": {}, "stable_states": {}, "complete_mission_evidence": False}
    write_json(output / "summary.json", summary)
    if args.fps is None:
        raise ValueError("EXPLICIT_REPLAY_FPS_REQUIRED")
    detector = None
    if not args.dry_run:
        if missing:
            return 2
        from .model import OwnerModel
        detector = OwnerModel(args.model, config, acknowledge_trusted_pickle=args.acknowledge_trusted_pickle)
        manifest["loaded_model_class_names"] = detector.names
        write_json(output / "manifest.json", manifest)
    from .artifacts import save_images
    from .pipeline import TrafficPipeline
    timeline = ReplayClock(args.clock_mode)
    pipeline = TrafficPipeline(config, detector, measure_wall_latency=args.clock_mode == "wall-clock") if config else None
    counts, states, terminal, passes = Counter(), Counter(), Counter(), Counter()
    latencies = []
    binding = config.document["association"]["binding_id"] if config else "unbound-inspection"
    start = time.monotonic()
    with (output / "observations.jsonl").open("x", encoding="utf-8") as stream:
        for f in iter_frames(items, fps=args.fps, binding_id=binding, max_frames=args.max_frames):
            source_time = f.received_s
            f, now = timeline.arrive(f)
            summary["frames"] += 1
            if f.bgr is None:
                summary["decode_errors"] += 1
            if args.dry_run:
                record = {"sequence": f.sequence, "image_handle": f.image_handle,
                          "decode_ok": f.bgr is not None,
                          "native_image_size": [f.bgr.shape[1], f.bgr.shape[0]] if f.bgr is not None else None,
                          "original_metadata": f.original_metadata, "inference": "NOT_RUN"}
            else:
                began = time.monotonic()
                obs = pipeline.process(f, now_s=now)
                elapsed = time.monotonic() - began
                latencies.append(elapsed)
                d = obs.context["diagnostics"]
                d["replay_timing"] = {"mode": args.clock_mode, "recorded_offset_s": source_time,
                                      "pipeline_wall_s": elapsed, "analysis_sequence": f.sequence,
                                      "historical_clock_verified": False}
                terminal.update([d["terminal_rejection"] or "ACCEPTED"])
                passes.update({"decoded": int(f.bgr is not None),
                               "candidate_present": int(bool(obs.context["detection_candidates"])),
                               "roi_selected": int(d["crop_selected"]),
                               "readable_raw_color": int(obs.signal["raw_state"] in ("RED", "GREEN")),
                               "binding_verified": int(d["crop_selected"] and obs.context["association_verified"]),
                               "stable_color": int(obs.signal["stable_state"] in ("RED", "GREEN"))})
                assets = save_images(output / "frames", f, obs)
                counts.update(obs.signal["quality_flags"])
                states.update([obs.signal["stable_state"]])
                record = {**obs.json_record(), "images": assets}
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    summary.update(quality_flags=dict(counts), stable_states=dict(states), wall_seconds=time.monotonic() - start,
                   real_rgb_decode="PASS" if summary["frames"] and not summary["decode_errors"] else "FAILED")
    summary.update(clock_mode=args.clock_mode, funnel_pass_counts=dict(passes),
                   terminal_rejections=dict(terminal), historical_clock_verified=False,
                   online_readiness="NOT_VERIFIED_LOCAL_FIXTURE_WORKLOAD_ONLY")
    if latencies:
        ordered = sorted(latencies)
        summary["pipeline_wall_latency_s"] = {"min": min(ordered), "max": max(ordered),
                                               "mean": sum(ordered) / len(ordered),
                                               "p95": ordered[min(len(ordered)-1, int(.95 * len(ordered)))]}
    if not args.dry_run:
        summary["real_model_inference"] = "FAILED" if counts["MODEL_EXCEPTION"] else "RUN"
        summary["real_rgb_detection_replay"] = "RUN"
    errors = (summary["decode_errors"] or counts["MODEL_EXCEPTION"] or counts["DETECTION_INVALID"]
              or counts["COLOR_ANALYSIS_EXCEPTION"])
    code = 4 if errors else (2 if missing else 0)
    summary["status"] = "FAILED" if errors else ("INPUT_REQUIRED" if missing else "PASS")
    write_json(output / "summary.json", summary)
    return code


def main(argv=None):
    args = parser().parse_args(argv)
    output = Path(args.output).resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError:
        print("OUTPUT_MUST_BE_NEW_DIRECTORY", file=sys.stderr)
        return 3
    try:
        code = run(args, output)
    except (OSError, ValueError, TypeError, ImportError, RuntimeError) as exc:
        code = 3
        summary_path = output / "summary.json"
        summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
        summary.update(status="FAILED", completed=False)
        write_json(summary_path, summary)
        write_json(output / "failure.json", {"status": "FAILED", "error_type": type(exc).__name__,
                                           "reason": str(exc)[:300], "real_model_inference": "NOT_CONFIRMED"})
    print(json.dumps({"exit_code": code, "output": str(output)}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
