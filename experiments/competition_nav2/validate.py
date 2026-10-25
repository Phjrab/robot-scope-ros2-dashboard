"""Fail-closed evidence validation. Offline checks can never yield NATIVE PASS."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import yaml

from configure import NODES, PLUGINS
from core import LIMITS, propagate, swept_poses
from fixtures import World, digest


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_record(record):
    errors = []
    if record.get("backend") != "nav2_native_sim":
        return ["backend is not nav2_native_sim"]
    if record.get("status") != "NATIVE_RECORDED":
        errors.append("native run not recorded successfully")
    if record.get("isolation", {}).get("errors") != []:
        errors.append("isolation proof absent or failed")
    if record.get("isolation", {}).get("network_interfaces") != ["lo"]:
        errors.append("network is not loopback-only")
    if any(record.get("lifecycle", {}).get(n, {}).get("id") != 3 for n in NODES):
        errors.append("native lifecycle active proof incomplete")
    if record.get("parameters", {}).get("FollowPath.plugin") != PLUGINS.get(
        record.get("controller"), "INVALID"
    ):
        errors.append("controller plugin readback mismatch")
    if not record.get("loaded_libraries") or not record.get("package_versions"):
        errors.append("native binary/version provenance missing")
    action = record.get("action", {})
    if (
        not action.get("accepted")
        or action.get("status") not in (4, 5, 6)
        or len(action.get("goal_uuid", [])) != 16
    ):
        errors.append("actual action terminal result missing")
    metrics = record.get("metrics", {})
    for field in (
        "footprint_collision_count",
        "boundary_violation_count",
        "hold_nonzero_count",
    ):
        if metrics.get(field) != 0:
            errors.append(field + " is nonzero or missing")
    for field in (
        "path_length_m",
        "wall_time_s",
        "sim_time_s",
        "min_conservative_clearance_m",
    ):
        value = metrics.get(field)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            errors.append("invalid metric: " + field)
    if record.get("outcome") == "GOAL_REACHED":
        if action.get("status") != 4 or record.get("goal_distance_m", math.inf) > 0.12:
            errors.append("goal claim contradicts actual result/pose")
        if record.get("raw_command_counts", {}).get("controller_server", 0) < 1:
            errors.append("no actual native controller output")
    elif record.get("outcome") != "SAFE_WAIT":
        errors.append("failed or missing scenario outcome")
    if (
        record.get("scenario") == "hold_release_delayed"
        and (record.get("delayed_command_probe") or {}).get("accepted") is not False
    ):
        errors.append("delayed nonzero rejection not demonstrated")
    if (
        record.get("scenario") == "signal_hold_recovery"
        and record.get("recovery_nonzero_count", 0) < 1
    ):
        errors.append("native recovery output while held was not exercised")
    if (
        record.get("scenario") == "sensor_stale"
        and record.get("terminal_fault") != "SENSOR_STALE"
    ):
        errors.append("stale response not exercised")
    if not record.get("graph_snapshots"):
        errors.append("ROS graph ownership evidence missing")
    return errors


def validate_directory(directory):
    directory = Path(directory)
    record = json.loads((directory / "result.json").read_text())
    errors = validate_record(record)
    required = [
        "native.log",
        "raw_commands.jsonl",
        "trace.jsonl",
        "scans.jsonl",
        "fixture.json",
        "params.yaml",
        "environment.json",
        "cleanup.json",
        "resources.jsonl",
    ]
    hashes = record.get("artifact_hashes", {})
    for name in required:
        file = directory / name
        if not file.is_file() or hashes.get(name) != sha(file):
            errors.append("missing or changed evidence: " + name)
    if (directory / "environment.json").exists():
        environment = json.loads((directory / "environment.json").read_text())
        if not re.fullmatch(r"[0-9a-f]{40}", environment.get("source_sha") or ""):
            errors.append("actual source commit missing")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", environment.get("image_id") or ""):
            errors.append("actual image ID missing")
    if (directory / "params.yaml").exists():
        config = yaml.safe_load((directory / "params.yaml").read_text())
        if digest(config) != record.get("config_sha256"):
            errors.append("config hash mismatch")
        for name in ("global_costmap", "local_costmap"):
            applied = record.get("costmap_parameters", {}).get(name, {})
            requested = config[name][name]["ros__parameters"]
            for key in (
                "footprint",
                "footprint_padding",
                "resolution",
                "track_unknown_space",
                "inflation_layer.inflation_radius",
                "inflation_layer.cost_scaling_factor",
                "obstacle_layer.scan.topic",
                "obstacle_layer.scan.expected_update_rate",
            ):
                expected = requested
                for part in key.split("."):
                    expected = expected[part]
                if applied.get(key) != expected:
                    errors.append(
                        "costmap readback missing/mismatched: " + name + "." + key
                    )
    log = (
        (directory / "native.log").read_text(errors="replace")
        if (directory / "native.log").is_file()
        else ""
    )
    if PLUGINS.get(record.get("controller"), "INVALID") not in log:
        errors.append("native plugin creation log missing")
    trace = (
        [
            json.loads(line)
            for line in (directory / "trace.jsonl").read_text().splitlines()
        ]
        if (directory / "trace.jsonl").exists()
        else []
    )
    if not trace:
        errors.append("empty actuator trace")
    else:
        for row in trace:
            v, w = row["actuator"]
            if (
                not all(math.isfinite(n) for n in (v, w))
                or not -1e-9 <= v <= LIMITS["v"] + 1e-9
                or abs(w) > LIMITS["w"] + 1e-9
            ):
                errors.append("actuator limit/nonfinite violation")
                break
            if (row["held"] or row["reason"] != "RELEASE") and (v != 0.0 or w != 0.0):
                errors.append("nonzero actuator under hold/fault/TTL")
                break
            if v != 0.0 or w != 0.0:
                for key, limit in (
                    ("command_source_age_s", LIMITS["command_ttl"]),
                    ("command_receipt_age_s", LIMITS["command_ttl"]),
                    ("sensor_source_age_s", LIMITS["sensor_ttl"]),
                    ("sensor_receipt_age_s", LIMITS["sensor_ttl"]),
                ):
                    age = row.get(key)
                    if age is None or not 0 <= age <= limit:
                        errors.append("nonzero output without fresh evidence: " + key)
            if row.get("published_ros", {}).get("clock_s") != row["sim_t"]:
                errors.append("clock publication evidence missing/mismatched")
                break
        if trace[-1]["actuator"] != [0.0, 0.0]:
            errors.append("shutdown actuator is not zero")
        if (directory / "fixture.json").exists():
            fixture = json.loads((directory / "fixture.json").read_text())
            claimed = fixture.pop("fixture_sha256", None)
            if digest(fixture) != claimed or claimed != record.get("fixture_sha256"):
                errors.append("fixture hash mismatch")
            world = World(fixture)
            previous_pose = fixture["start"]
            previous_t = 0.0
            previous_actuator = [0.0, 0.0]
            for row in trace:
                dt = row["sim_t"] - previous_t
                if (
                    not 0 < dt <= 0.100001
                    or row["applied_previous"] != previous_actuator
                ):
                    errors.append("trace time/actuator continuity failure")
                    break
                v, w = row["applied_previous"]
                predicted = propagate(previous_pose, v, w, dt)
                if any(abs(a - b) > 1e-6 for a, b in zip(predicted, row["pose"])):
                    errors.append("pose not explained by actual actuator commands")
                    break
                samples = swept_poses(previous_pose, v, w, dt)
                if any(
                    world.collision(p, max(0.0, row["elapsed_s"] - dt)) for p in samples
                ):
                    errors.append("independent interpolated footprint collision")
                    break
                if row["actuator"] != [0.0, 0.0] and row["reason"] == "RELEASE":
                    if (
                        abs(row["actuator"][0] - previous_actuator[0])
                        > LIMITS["a"] * dt + 1e-6
                        or abs(row["actuator"][1] - previous_actuator[1])
                        > LIMITS["alpha"] * dt + 1e-6
                    ):
                        errors.append("normal-command acceleration limit exceeded")
                        break
                previous_pose, previous_t, previous_actuator = (
                    row["pose"],
                    row["sim_t"],
                    row["actuator"],
                )
        if record.get("outcome") == "SAFE_WAIT":
            last = trace[-1]["sim_t"]
            tail = [r for r in trace if r["sim_t"] >= last - 2.0]
            if (
                not tail
                or tail[-1]["sim_t"] - tail[0]["sim_t"] < 1.9
                or any(r["actuator"] != [0.0, 0.0] for r in tail)
            ):
                errors.append("safe wait lacks two-second zero-command evidence")
        if record.get("scenario") == "sensor_stale":
            stale = [r for r in trace if r["reason"] == "SENSOR_STALE"]
            if not stale or not any(
                r["actuator"][0] > 0 for r in trace if r["sim_t"] < stale[0]["sim_t"]
            ):
                errors.append("dropout was not exercised during forward progress")
            recovery = record.get("dropout_recovery", {})
            if recovery.get("fault_latched") != "SENSOR_STALE" or recovery.get(
                "final_output"
            ) != [0.0, 0.0]:
                errors.append("dropout latched zero evidence missing")
    if (directory / "cleanup.json").exists():
        cleanup = json.loads((directory / "cleanup.json").read_text())
        if (
            cleanup.get("remaining_processes") != []
            or cleanup.get("graceful") is not True
        ):
            errors.append("child process cleanup incomplete/non-graceful")
    return dict(
        status="PASS" if not errors else "FAIL",
        backend="nav2_native_sim",
        errors=errors,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("directory", type=Path)
    args = p.parse_args()
    result = validate_directory(args.directory)
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result["errors"]))
