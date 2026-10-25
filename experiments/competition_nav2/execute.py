"""Run one native case, collect provenance, terminate child group, validate evidence."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import yaml

from configure import candidate, validate_config
from fixtures import (
    ROOT,
    World,
    cases,
    diagnostic_cases,
    extension_cases,
    digest,
    reference_feasibility,
)
from preflight import require_isolated
from validate import validate_directory, sha


_SEEN_PROCESSES = set()


def process_snapshot(groups):
    all_rows = []
    for p in Path("/proc").glob("[0-9]*"):
        try:
            stat = (p / "stat").read_text().rsplit(")", 1)[1].split()
            all_rows.append(
                dict(
                    pid=int(p.name),
                    ppid=int(stat[1]),
                    group=int(stat[2]),
                    state=stat[0],
                    start_ticks=int(stat[19]),
                    cpu_ticks=int(stat[11]) + int(stat[12]),
                    rss_pages=int(stat[21]),
                )
            )
        except (OSError, ValueError, IndexError):
            continue
    selected = {
        r["pid"]
        for r in all_rows
        if r["group"] in groups or (r["pid"], r["start_ticks"]) in _SEEN_PROCESSES
    }
    while True:
        extended = selected | {r["pid"] for r in all_rows if r["ppid"] in selected}
        if extended == selected:
            break
        selected = extended
    rows = [r for r in all_rows if r["pid"] in selected]
    _SEEN_PROCESSES.update((r["pid"], r["start_ticks"]) for r in rows)
    return rows


def execute(args):
    isolation = require_isolated()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    fixture = next(
        f
        for f in cases(args.seed)
        + diagnostic_cases(args.seed)
        + extension_cases(args.seed)
        if f["scenario"] == args.scenario
    )
    if fixture.get("reference_waypoints"):
        feasibility = reference_feasibility(fixture)
        (out / "reference_feasibility.json").write_text(
            json.dumps(feasibility, indent=2) + "\n"
        )
        assert feasibility["status"] == "PASS"
    world = World(fixture)
    fixture["map_sha256"] = world.write_map(out)
    fixture["fixture_sha256"] = digest(fixture)
    (out / "fixture.json").write_text(json.dumps(fixture, indent=2) + "\n")
    cfg = candidate(args.controller, args.variant)
    assert not validate_config(cfg, args.controller)
    cfg["map_server"]["ros__parameters"]["yaml_filename"] = str(out / "map.yaml")
    cfg["bt_navigator"]["ros__parameters"]["default_nav_to_pose_bt_xml"] = str(
        ROOT / "config/replan.xml"
    )
    # Humble activates BOTH navigators and loads both default trees, even when
    # this runner only sends NavigateToPose. Its shipped through-poses tree uses
    # Backup, which is intentionally absent from this forward-only experiment.
    cfg["bt_navigator"]["ros__parameters"]["default_nav_through_poses_bt_xml"] = str(
        ROOT / "config/replan_through_poses.xml"
    )
    (out / "params.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    (out / "run.json").write_text(
        json.dumps(
            dict(
                controller=args.controller,
                variant=args.variant,
                repeat=args.repeat,
                seed=args.seed,
            ),
            indent=2,
        )
        + "\n"
    )
    packages = subprocess.run(
        ["dpkg-query", "-W", "-f=${Package}\t${Version}\n"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    environment = dict(
        isolation=isolation,
        installed_packages=packages,
        package_lock_sha256=hashlib.sha256(packages.encode()).hexdigest(),
        image_id=os.environ.get("C3_IMAGE_ID"),
        source_sha=os.environ.get("C3_SOURCE_SHA"),
        python=sys.version,
        cmd=[
            "ros2",
            "launch",
            str(ROOT / "launch/native.launch.py"),
            "run_dir:=" + str(out),
        ],
        mppi_optimizer_seed="not exposed by verified Humble source; stochastic repeats, not bitwise reproducible",
        fixture_seed=args.seed,
        repeat=args.repeat,
    )
    (out / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    processes, groups = [], []
    graceful = True
    native = (out / "native.log").open("w")
    runner = (out / "runner.log").open("w")
    resources = (out / "resources.jsonl").open("w")
    failure = None
    try:
        nav = subprocess.Popen(
            environment["cmd"],
            stdout=native,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        processes.append(nav)
        groups.append(nav.pid)
        plant = subprocess.Popen(
            [sys.executable, str(ROOT / "native_runner.py"), str(out)],
            stdout=runner,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        processes.append(plant)
        groups.append(plant.pid)
        deadline = time.monotonic() + fixture["timeout_s"] * 2 + 120.0
        while (
            plant.poll() is None and nav.poll() is None and time.monotonic() < deadline
        ):
            resources.write(
                json.dumps(
                    dict(
                        monotonic=time.monotonic(),
                        processes=process_snapshot(groups),
                        clock_ticks_per_s=os.sysconf("SC_CLK_TCK"),
                        page_bytes=os.sysconf("SC_PAGE_SIZE"),
                    )
                )
                + "\n"
            )
            resources.flush()
            time.sleep(0.25)
        if plant.poll() is None:
            raise RuntimeError("native child exited or overall deadline expired")
    except Exception as exc:
        failure = type(exc).__name__ + ": " + str(exc)
    finally:
        # ros2 launch forwards SIGINT to its own children. Signalling both the
        # launcher group and every descendant caused duplicate interrupts in CI.
        for process in reversed(processes):
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            for p in processes:
                p.poll()
            remaining = [r for r in process_snapshot(groups) if r["state"] != "Z"]
            if not remaining:
                break
            time.sleep(0.1)
        else:
            graceful = False
            for group in groups:
                try:
                    os.killpg(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for child in process_snapshot(groups):
                try:
                    os.kill(child["pid"], signal.SIGKILL)
                except ProcessLookupError:
                    pass
        for p in processes:
            p.wait(timeout=5.0)
        remaining = [r for r in process_snapshot(groups) if r["state"] != "Z"]
        (out / "cleanup.json").write_text(
            json.dumps(
                dict(
                    graceful=graceful,
                    remaining_processes=remaining,
                    return_codes=[p.returncode for p in processes],
                ),
                indent=2,
            )
            + "\n"
        )
        native.close()
        runner.close()
        resources.close()
    result_file = out / "result.json"
    if not result_file.exists():
        result_file.write_text(
            json.dumps(
                dict(
                    backend="nav2_native_sim",
                    status="FAIL",
                    error="runner produced no result; see runner.log",
                )
            )
            + "\n"
        )
    result = json.loads(result_file.read_text())
    if failure:
        result.update(status="FAIL", error=failure)
    names = [
        "native.log",
        "raw_commands.jsonl",
        "trace.jsonl",
        "scans.jsonl",
        "observations.jsonl",
        "fixture.json",
        "params.yaml",
        "environment.json",
        "cleanup.json",
        "resources.jsonl",
    ]
    result["artifact_hashes"] = {
        name: sha(out / name) for name in names if (out / name).exists()
    }
    result_file.write_text(json.dumps(result, indent=2) + "\n")
    validation = validate_directory(out)
    (out / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    print(json.dumps(validation, indent=2))
    return 0 if validation["status"] == "PASS" else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--controller", choices=["rpp", "mppi"], required=True)
    p.add_argument("--variant", choices=["baseline", "tuned"], default="baseline")
    p.add_argument(
        "--scenario",
        choices=[
            f["scenario"] for f in cases() + diagnostic_cases() + extension_cases()
        ],
        required=True,
    )
    p.add_argument("--seed", type=int, default=20261024)
    p.add_argument("--repeat", type=int, default=0)
    p.add_argument("--output", type=Path, required=True)
    raise SystemExit(execute(p.parse_args()))
