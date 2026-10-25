"""Execute eight native cases sequentially in one immutable image; never fake results."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SCENARIOS = ("empty", "diagnostic_single_obstacle", "fully_blocked", "sensor_stale")


def execute(
    lock,
    output,
    order=None,
    summary_name="minimum-summary.json",
    fixtures=None,
    variant="baseline",
    expected_outcomes=None,
):
    extension = order is not None
    if order is None:
        order = [("rpp", "empty", 0)] + [
            (c, s, 0)
            for c in ("rpp", "mppi")
            for s in SCENARIOS
            if (c, s) != ("rpp", "empty")
        ]
    output.mkdir(parents=True, exist_ok=True)
    summary = dict(
        schema="c3-native-extension.v1" if extension else "c3-native-minimum.v1",
        planned=len(order),
        attempted=0,
        native_recorded=0,
        cases=[],
        status="RUNNING",
    )
    for controller, scenario, repeat in order:
        case_dir = output / (
            controller + "-" + scenario + (f"-{repeat}" if extension else "")
        )
        process = subprocess.run(
            [
                sys.executable,
                str(ROOT / "container/manage.py"),
                "run",
                "--lock",
                str(lock),
                "--controller",
                controller,
                *(
                    ["--fixture", str(fixtures[scenario])]
                    if fixtures and scenario in fixtures
                    else ["--scenario", scenario]
                ),
                "--variant",
                variant,
                "--seed",
                "20261024",
                "--repeat",
                str(repeat),
                "--output",
                str(case_dir),
            ],
            check=False,
        )

        def read(name):
            path = case_dir / "run" / name
            return json.loads(path.read_text()) if path.exists() else {}

        result, validation, environment = [
            read(n) for n in ("result.json", "validation.json", "environment.json")
        ]
        expected = (
            "SAFE_WAIT"
            if scenario
            in ("fully_blocked", "sensor_stale", "d0_blocked", "d0_sensor_dropout")
            else "GOAL_REACHED"
        )
        expected = (expected_outcomes or {}).get(scenario, expected)
        row = dict(
            controller=controller,
            variant=variant,
            scenario=scenario,
            repeat=repeat,
            returncode=process.returncode,
            status=result.get("status", "NO_RESULT"),
            outcome=result.get("outcome"),
            expected=expected,
            validation=validation,
            error=result.get("error"),
            terminal_fault=result.get("terminal_fault"),
            action=result.get("action"),
            metrics=result.get("metrics"),
            goal_distance_m=result.get("goal_distance_m"),
            goal_yaw_error_rad=result.get("goal_yaw_error_rad"),
            package_versions=result.get("package_versions"),
            loaded_library_sha256=result.get("loaded_library_sha256"),
            raw_command_counts=result.get("raw_command_counts"),
            map_sha256=read("fixture.json").get("map_sha256"),
            d0_scene_sha256=read("fixture.json").get("d0_scene_sha256"),
            d0_source_commit=read("fixture.json").get("d0_source_commit"),
            fixture_sha256=result.get("fixture_sha256"),
            config_sha256=result.get("config_sha256"),
            source_sha=environment.get("source_sha"),
            image_id=environment.get("image_id"),
        )
        row["expectation_met"] = (
            process.returncode == 0
            and row["status"] == "NATIVE_RECORDED"
            and validation.get("status") == "PASS"
            and row["outcome"] == expected
        )
        summary["cases"].append(row)
        summary["attempted"] += 1
        summary["native_recorded"] += int(row["status"] == "NATIVE_RECORDED")
        (output / summary_name).write_text(json.dumps(summary, indent=2) + "\n")
        print(
            json.dumps(
                {
                    k: row[k]
                    for k in (
                        "controller",
                        "scenario",
                        "status",
                        "outcome",
                        "expectation_met",
                    )
                }
            ),
            flush=True,
        )
        # Do not fan out an environment/TF/clock/activation failure in the first baseline.
        if len(summary["cases"]) == 1 and not row["expectation_met"]:
            summary["status"] = (
                "STOPPED_AT_FEASIBLE1"
                if scenario == "d0_feasible1"
                else "BLOCKED_AT_RPP_BASELINE"
                if extension
                else "BLOCKED_AT_EMPTY_BASELINE"
            )
            break
    else:
        summary["status"] = (
            "PASS"
            if all(r["expectation_met"] for r in summary["cases"])
            else "COMPLETED_WITH_FAILURES"
        )
    if extension and all(s == "diagnostic_single_obstacle" for _, s, _ in order[:3]):
        repeats = summary["cases"][:3]
        summary["repeatability"] = dict(
            status="PASS"
            if len(repeats) == 3
            and all(r["expectation_met"] for r in repeats)
            and all(
                len({r[k] for r in repeats}) == 1
                for k in ("source_sha", "image_id", "fixture_sha256", "config_sha256")
            )
            else "FAIL",
            fields=["source_sha", "image_id", "fixture_sha256", "config_sha256"],
        )
        if summary["repeatability"]["status"] != "PASS":
            summary["status"] = "COMPLETED_WITH_FAILURES"
    (output / summary_name).write_text(json.dumps(summary, indent=2) + "\n")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(execute(args.lock, args.output))
