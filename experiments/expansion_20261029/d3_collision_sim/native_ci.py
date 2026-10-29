"""D3-only hosted-CI driver reusing the existing native Nav2 executor unchanged
except namespace/domain in an ephemeral source export. No local daemon setup.
No planner substitute, controller parameter tuning, secret, or physical device.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

REPO = Path(__file__).resolve().parents[3]
BASELINE = "experiments/competition_nav2"


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def stage(destination):
    destination.mkdir(parents=True, exist_ok=False)
    archive = destination.parent / "d3-source.tar"
    with archive.open("wb") as out:
        subprocess.run(["git", "archive", "HEAD"], cwd=REPO, stdout=out, check=True)
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                raise ValueError("unsafe source archive")
        source.extractall(destination)
    archive.unlink()
    # Read-only git identity access used by the existing run driver. Never write
    # the original index/tree through this marker; stage is not a development clone.
    (destination / ".git").write_text("gitdir: " + str(REPO / ".git") + "\n")
    changes = []
    for p in (destination / BASELINE).rglob("*"):
        if not p.is_file() or (
            p.suffix not in (".py", ".yaml") and p.name != "Dockerfile"
        ):
            continue
        original = p.read_bytes()
        adapted = original.replace(b"c3_nav2", b"robot_scope_review_x").replace(
            b"ROS_DOMAIN_ID=193", b"ROS_DOMAIN_ID=194"
        )
        if p.name == "configure.py":
            # Preserve the production-prefix ban. Normalize ONLY this exact
            # approved review namespace for that textual validation check.
            adapted = adapted.replace(
                b"text = json.dumps(cfg)",
                b'text = json.dumps(cfg).replace("/robot_scope_review_x/", "/c3_nav2/")',
            )
        if p.name == "preflight.py":
            adapted = adapted.replace(b'!= "193"', b'!= "194"')
        if adapted != original:
            p.write_bytes(adapted)
            changes.append(
                dict(
                    path=str(p.relative_to(destination)),
                    original_sha256=hashlib.sha256(original).hexdigest(),
                    adapted_sha256=hashlib.sha256(adapted).hexdigest(),
                )
            )
    write(
        destination.parent / "namespace-adaptation.json",
        dict(
            changes=changes,
            policy="namespace/domain literals and exact review-prefix validation normalization ONLY; no controller, limits, geometry or outcomes changed",
        ),
    )
    return destination / BASELINE


def run_case(native, lock, output, scenario):
    target = output / scenario
    p = subprocess.run(
        [
            sys.executable,
            str(native / "container/manage.py"),
            "run",
            "--lock",
            str(lock),
            "--controller",
            "rpp",
            "--variant",
            "baseline",
            "--scenario",
            scenario,
            "--seed",
            "20261024",
            "--output",
            str(target),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(p.stdout, flush=True)
    (target / "driver-output.txt").write_text(p.stdout)

    def read(name):
        path = target / "run" / name
        return json.loads(path.read_text()) if path.exists() else {}

    result, validation = read("result.json"), read("validation.json")
    expected = (
        "SAFE_WAIT" if scenario in ("fully_blocked", "sensor_stale") else "GOAL_REACHED"
    )
    row = dict(
        scenario=scenario,
        process_exit=p.returncode,
        expected=expected,
        execution="NATIVE_NAV2_SIM"
        if result.get("status") == "NATIVE_RECORDED"
        else "NATIVE_ATTEMPT_FAILED",
        status="PASS"
        if p.returncode == 0
        and result.get("status") == "NATIVE_RECORDED"
        and validation.get("status") == "PASS"
        and result.get("outcome") == expected
        else "FAIL",
        driver_error=p.stdout[-3000:] if p.returncode else None,
        result=result,
        validation=validation,
    )
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--stage-only", action="store_true")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    native = stage(args.output / "source")
    if args.stage_only:
        return 0
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
    ):
        raise RuntimeError("explicit GitHub-hosted temporary runner required")
    summary = dict(
        source_sha=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        native_source_base="47ae383fff5bfa12c20d523d2851a952dbb60f4b",
        namespace="/robot_scope_review_x",
        domain=194,
        controller="STOCK_NAVFN_RPP_NO_HEADING_PATCH",
        additional_3d_constraint_mode="ADVISORY_ONLY",
        native_nav2_collision_detection="ACTIVE_EXISTING_RPP",
        status="NOT_RUN",
        cases=[],
        first_blocker=None,
    )
    summary_path = args.output / "summary.json"
    write(summary_path, summary)
    lock = args.output / "image-lock.json"
    try:
        # Resolve a new immutable image once; record all actual packages. This
        # does not pretend an old full apt snapshot is still available.
        subprocess.run(
            [
                sys.executable,
                str(native / "container/manage.py"),
                "build",
                "--lock",
                str(lock),
            ],
            check=True,
        )
        image = json.loads(lock.read_text())
        packages = dict(line.split("\t") for line in image["packages_tsv"].splitlines())
        selected = {
            k: v
            for k, v in packages.items()
            if k.startswith("ros-humble-nav2-") or k == "ros-humble-navigation2"
        }
        if not selected or any(not v.startswith("1.1.20-") for v in selected.values()):
            raise RuntimeError(
                "Humble/Nav2 1.1.20 package lock mismatch: " + str(selected)
            )
        summary["image_id"] = image["image_id"]
        summary["base_digest"] = image["base_digest"]
        summary["nav2_packages"] = selected
        summary["status"] = "RUNNING"
        write(summary_path, summary)
        for scenario in ("empty", "diagnostic_single_obstacle", "fully_blocked"):
            row = run_case(native, lock, args.output, scenario)
            summary["cases"].append(row)
            write(summary_path, summary)
            if row["status"] != "PASS":
                summary["first_blocker"] = dict(
                    scenario=scenario,
                    error=row["result"].get("error") or row.get("driver_error"),
                    terminal_fault=row["result"].get("terminal_fault"),
                    outcome=row["result"].get("outcome"),
                    action=row["result"].get("action"),
                )
                summary["status"] = "FAIL"
                break
        else:
            # Short fixed extension ONLY after all three minimum cases pass.
            for scenario in ("diagnostic_appearing_obstacle", "sensor_stale"):
                row = run_case(native, lock, args.output, scenario)
                summary["cases"].append(row)
                write(summary_path, summary)
                if row["status"] != "PASS":
                    summary["first_blocker"] = dict(
                        scenario=scenario,
                        error=row["result"].get("error") or row.get("driver_error"),
                        terminal_fault=row["result"].get("terminal_fault"),
                        outcome=row["result"].get("outcome"),
                    )
                    summary["status"] = "FAIL"
                    break
            else:
                summary["status"] = "PASS"
    except Exception as exc:
        summary["first_blocker"] = dict(error=type(exc).__name__ + ": " + str(exc))
        summary["status"] = "FAIL" if summary["status"] == "RUNNING" else "NOT_RUN"
    finally:
        write(summary_path, summary)
        print(
            "D3_NATIVE_EVIDENCE="
            + json.dumps(
                {
                    **{k: v for k, v in summary.items() if k != "cases"},
                    "cases": [
                        {
                            **{
                                k: r[k]
                                for k in ("scenario", "status", "execution", "expected")
                            },
                            "result": {
                                k: r["result"].get(k)
                                for k in (
                                    "status",
                                    "outcome",
                                    "error",
                                    "terminal_fault",
                                    "action",
                                    "metrics",
                                    "package_versions",
                                    "loaded_library_sha256",
                                    "raw_command_counts",
                                    "goal_distance_m",
                                    "goal_yaw_error_rad",
                                    "fixture_sha256",
                                    "config_sha256",
                                )
                            },
                            "validation": r["validation"],
                        }
                        for r in summary["cases"]
                    ],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        print(
            json.dumps(
                dict(
                    status=summary["status"],
                    first_blocker=summary["first_blocker"],
                    cases=[
                        {k: r[k] for k in ("scenario", "status", "execution")}
                        for r in summary["cases"]
                    ],
                )
            ),
            flush=True,
        )
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
