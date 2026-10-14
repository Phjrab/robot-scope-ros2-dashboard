#!/usr/bin/env python3
"""Analyze collect.py JSONL without ROS. Never infer ground truth or clock alignment."""
import argparse
from bisect import bisect_left
from collections import defaultdict
import json
import math
from pathlib import Path


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def distribution(values):
    values = sorted(float(x) for x in values if finite_number(x))
    def percentile(p):
        at = (len(values) - 1) * p
        lo = int(at)
        hi = min(lo + 1, len(values) - 1)
        return values[lo] + (values[hi] - values[lo]) * (at - lo)
    return {"samples": len(values), "mean": sum(values) / len(values) if values else None,
            "p50": percentile(.5) if values else None,
            "p95": percentile(.95) if values else None,
            "max": max(values) if values else None}


def intervals(values):
    return [b - a for a, b in zip(values, values[1:])]


def timing(values, gap_ms):
    differences = intervals(values)
    positive = [v / 1e6 for v in differences if v > 0]
    duration = (values[-1] - values[0]) / 1e9 if len(values) > 1 else 0
    valid_order = all(d > 0 for d in differences)
    return {"samples": len(values), "interval_ms": distribution(positive),
            "fps_over_observed_span": (len(values) - 1) / duration if duration > 0 and valid_order else None,
            "duplicate_timestamps": sum(d == 0 for d in differences),
            "out_of_order": sum(d < 0 for d in differences),
            "gaps_above_threshold": sum(d > gap_ms * 1e6 for d in differences),
            "gap_threshold_ms": gap_ms}


def normalized_quaternion(q):
    if not isinstance(q, list) or len(q) != 4 or not all(finite_number(v) for v in q):
        return None
    norm = math.hypot(*q)
    return [v / norm for v in q] if norm > 1e-12 else None


def pose_metrics(events):
    good = []
    for event in events:
        pose = event.get("pose", {})
        p = pose.get("position")
        q = normalized_quaternion(pose.get("quaternion_xyzw"))
        if isinstance(p, list) and len(p) == 3 and all(finite_number(v) for v in p) and q:
            good.append((event, p, q))
    frames = sorted({(e.get("frame_id", ""), e.get("child_frame_id", "")) for e, _, _ in good})
    if not good:
        return {"state": "NOT_OBSERVED", "samples": 0}
    if len(frames) != 1:
        return {"state": "N/A", "reason": "pose frames changed; no transforms inferred", "samples": len(good), "frames": frames}
    origin, q0 = good[0][1:]
    translations = [math.dist(p, origin) for _, p, _ in good]
    angles = [math.degrees(2 * math.acos(min(1., abs(sum(a * b for a, b in zip(q, q0)))))) for _, _, q in good]
    path_length = sum(math.dist(a[1], b[1]) for a, b in zip(good, good[1:]))
    return {"state": "OBSERVED", "samples": len(good), "frames": frames,
            "translation_from_first_m": distribution(translations),
            "rotation_from_first_deg": distribution(angles),
            "endpoint_displacement_m": translations[-1], "estimated_path_length_m": path_length,
            "interpretation": "Pose change only. Stationarity/motion must be independently declared; no accuracy, return error, ATE or RPE without a reference."}


def status_metrics(events, end_ns):
    mapped = [e for e in events if e.get("tracking_state") in ("TRACKING", "LOST", "STOPPED")]
    if not mapped:
        return {"state": "NOT_OBSERVED" if not events else "UNMAPPED", "samples": len(events),
                "reason": "No explicit status mapping available"}
    lost_transitions = 0
    recoveries = []
    lost_since = None
    previous = None
    stopped_samples = 0
    for event in mapped:
        state, stamp = event["tracking_state"], event["receipt_monotonic_ns"]
        if state == "LOST" and previous != "LOST":
            lost_transitions += 1
            if lost_since is None:
                lost_since = stamp
        elif state == "TRACKING" and lost_since is not None:
            recoveries.append((stamp - lost_since) / 1e9)
            lost_since = None
        elif state == "STOPPED":
            stopped_samples += 1
            # STOPPED is not recovery. Preserve an open lost interval until TRACKING.
        previous = state
    return {"state": "OBSERVED", "samples": len(events), "mapped_samples": len(mapped),
            "unknown_samples": sum(e.get("tracking_state") == "UNKNOWN" for e in events),
            "lost_entries": lost_transitions,
            "initial_state_lost": mapped[0]["tracking_state"] == "LOST",
            "recovery_seconds": distribution(recoveries),
            "unrecovered_loss_seconds_at_end": (end_ns - lost_since) / 1e9 if lost_since is not None else None,
            "explicit_stopped_samples": stopped_samples, "last_state": mapped[-1]["tracking_state"]}


def stereo_metrics(left, right, tolerance_ms):
    """Nearest one-to-one timestamp pairing; skip reused matches and reject distant pairs."""
    a = sorted(e["stamp_ns"] for e in left if finite_number(e.get("stamp_ns")))
    b = sorted(e["stamp_ns"] for e in right if finite_number(e.get("stamp_ns")))
    used = set()
    differences = []
    for stamp in a:
        j = bisect_left(b, stamp)
        candidates = [k for k in (j - 1, j) if 0 <= k < len(b) and k not in used]
        if not candidates:
            continue
        k = min(candidates, key=lambda k: abs(b[k] - stamp))
        if abs(b[k] - stamp) <= tolerance_ms * 1e6:
            used.add(k)
            differences.append((stamp - b[k]) / 1e6)
    return {"method": "nearest one-to-one header timestamps; no clock-offset correction",
            "tolerance_ms": tolerance_ms, "matched_pairs": len(differences),
            "unmatched_left": len(a) - len(differences), "unmatched_right": len(b) - len(differences),
            "left_minus_right_ms": distribution(differences),
            "absolute_difference_ms": distribution([abs(v) for v in differences])}


def analyze(records, warmup_seconds=10., gap_ms=100., stereo_tolerance_ms=15., expected_stereo_hz=30.):
    starts = [r for r in records if r.get("event") == "run_start"]
    if len(starts) != 1:
        raise ValueError("Exactly one run_start is required")
    start = starts[0]
    start_ns = start["receipt_monotonic_ns"]
    ends = [r for r in records if r.get("event") == "run_end"]
    if len(ends) > 1:
        raise ValueError("Multiple run_end records")
    end_ns = ends[0]["receipt_monotonic_ns"] if ends else max(r.get("receipt_monotonic_ns", start_ns) for r in records)
    if not finite_number(start_ns) or not finite_number(end_ns) or end_ns < start_ns:
        raise ValueError("Invalid monotonic collection interval")
    if not all(finite_number(v) for v in (warmup_seconds, gap_ms, stereo_tolerance_ms, expected_stereo_hz)):
        raise ValueError("Timing options must be finite")
    if min(warmup_seconds, gap_ms, stereo_tolerance_ms) < 0 or expected_stereo_hz <= 0:
        raise ValueError("Timing options must be nonnegative and expected stereo Hz positive")
    measure_ns = start_ns + int(warmup_seconds * 1e9)
    selected = [r for r in records if r.get("event") == "sample" and
                finite_number(r.get("receipt_monotonic_ns")) and measure_ns <= r["receipt_monotonic_ns"] <= end_ns]
    groups = defaultdict(list)
    for name in start.get("streams", {}):
        groups[name] = []
    for event in selected:
        groups[event["stream"]].append(event)
    contract = start.get("clock_contract", {})
    age_allowed = contract.get("header_and_receipt_same_ros_clock") is True and bool(contract.get("evidence"))
    streams = {}
    for name, events in sorted(groups.items()):
        receipts = [e["receipt_monotonic_ns"] for e in events]
        stamps = [e["stamp_ns"] for e in events if finite_number(e.get("stamp_ns"))]
        ros_receipts = [e["receipt_ros_ns"] for e in events if finite_number(e.get("receipt_ros_ns"))]
        ages = [(e["receipt_ros_ns"] - e["stamp_ns"]) / 1e6 for e in events
                if finite_number(e.get("stamp_ns")) and finite_number(e.get("receipt_ros_ns"))]
        age_reason = None
        if not age_allowed:
            age_reason = "Header/receipt ROS clock relationship is not verified"
        elif not ages:
            age_reason = "No paired header and receipt ROS timestamps"
        elif any(d < 0 for d in intervals(stamps)) or any(d < 0 for d in intervals(ros_receipts)):
            age_reason = "Backward timestamp jump; clock continuity not established"
        elif any(v < 0 for v in ages):
            age_reason = "Negative age; clock contract contradicted"
        elif len(ros_receipts) > 1 and max(ros_receipts) == min(ros_receipts):
            age_reason = "ROS clock did not advance"
        elif contract.get("mode") == "live" and len(ros_receipts) == len(receipts) and any(
                abs(ros_delta - mono_delta) > 1e9 for ros_delta, mono_delta in zip(intervals(ros_receipts), intervals(receipts))):
            age_reason = "Live ROS clock advanced differently from monotonic by over 1s; possible clock jump"
        last_age = (end_ns - receipts[-1]) / 1e9 if receipts else None
        streams[name] = {"state": "NOT_OBSERVED" if not events else
                         ("NO_RECENT_INPUT" if last_age > gap_ms / 1000 else "OBSERVED"),
                         "samples": len(events), "receipt_monotonic": timing(receipts, gap_ms),
                         "header_stamp": timing(stamps, gap_ms),
                         "seconds_since_last_sample_at_end": last_age,
                         "seconds_to_first_sample_in_window": (receipts[0] - measure_ns) / 1e9 if receipts else None,
                         "frames": sorted({e.get("frame_id", "") for e in events}),
                         "data_age_ms": {"state": "N/A", "reason": age_reason} if age_reason else
                         {"state": "MEASURED", "distribution": distribution(ages),
                          "meaning": "Header-to-subscriber ROS-clock age, not algorithm compute time"}}
        if any("pose" in e for e in events):
            streams[name]["pose"] = pose_metrics(events)
        if name in ("left", "right"):
            periods = [d / 1e6 for d in intervals(stamps) if d > 0]
            streams[name]["absolute_period_deviation_ms"] = distribution([abs(p - 1000 / expected_stereo_hz) for p in periods])
            streams[name]["expected_hz"] = expected_stereo_hz
        if name == "status" or any("tracking_state" in e for e in events):
            streams[name]["tracking"] = status_metrics(events, end_ns)
    resources = defaultdict(list)
    for event in records:
        if event.get("event") == "resource" and measure_ns <= event["receipt_monotonic_ns"] <= end_ns:
            for name, value in event.get("values", {}).items():
                if finite_number(value):
                    resources[name].append(value)
    algorithm_timings = defaultdict(list)
    for event in groups.get("status", []):
        for name, value in event.get("algorithm_timing_seconds", {}).items():
            if finite_number(value) and value >= 0:
                algorithm_timings[name + "_ms"].append(value * 1000)
    result = {"schema_version": 1, "run_id": start.get("run_id"),
              "evidence_type": start.get("evidence_type", "NOT_DECLARED"),
              "collector": {"state": "ENDED" if ends else "INCOMPLETE", "end_reason": ends[0].get("reason") if ends else None},
              "measurement": {"warmup_seconds": warmup_seconds,
                              "start_monotonic_ns": measure_ns, "end_monotonic_ns": end_ns,
                              "duration_seconds": max(0., (end_ns - measure_ns) / 1e9),
                              "state": "OBSERVED" if end_ns > measure_ns else "NO_MEASUREMENT_WINDOW"},
              "streams": streams, "clock_contract": contract,
              "stereo": stereo_metrics(groups.get("left", []), groups.get("right", []), stereo_tolerance_ms),
              "resources": {name: distribution(values) for name, values in sorted(resources.items())},
              "sensor_requirements_reference": {"release": "3.2", "minimum_image_hz": 30,
                                                "image_period_jitter_ms": 2, "stereo_offset_ms": .1,
                                                "note": "Sensor requirements differ from sync_matching_threshold_ms and image_jitter_threshold_ms warning parameters; no automatic pass assigned"},
              "accuracy": {"state": "N/A", "reason": "No measured reference trajectory supplied; no ATE/RPE or motion accuracy computed"},
              "algorithm_processing_time_ms": {"state": "MEASURED", "fields": {k: distribution(v) for k, v in algorithm_timings.items()},
                                               "source": start.get("status_schema_source"),
                                               "meaning": "Published release-3.2 status durations; callback covers input processing through output publication, track covers cuVSLAM pose tracking. Rolling mean/max fields are not independent per-frame timings."} if algorithm_timings else
                                              {"state": "N/A", "reason": "No verified status timing samples received; receipt age is not processing time"},
              "notes": ["No received samples does not prove tracking loss or a stopped estimator.",
                        "NO_RECENT_INPUT describes subscriber silence, not its cause.",
                        "Statistics do not assign INSTALL_PASS, LIVE_INPUT_PASS, VO_PASS or VIO_PASS."]}
    return result


def read_jsonl(path):
    records = []
    with Path(path).open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON"))))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid JSONL at line {lineno}: {exc}") from exc
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=10.)
    parser.add_argument("--gap-ms", type=float, default=100.)
    parser.add_argument("--stereo-tolerance-ms", type=float, default=15.)
    parser.add_argument("--expected-stereo-hz", type=float, default=30.)
    args = parser.parse_args()
    result = analyze(read_jsonl(args.input), args.warmup_seconds, args.gap_ms, args.stereo_tolerance_ms, args.expected_stereo_hz)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print(f"Wrote {args.output}; {result['measurement']['duration_seconds']:.3f} measured seconds")


if __name__ == "__main__":
    main()
