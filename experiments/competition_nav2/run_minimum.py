"""Execute eight native cases sequentially in one immutable image; never fake results."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SCENARIOS = ("empty", "diagnostic_single_obstacle", "fully_blocked", "sensor_stale")


def execute(lock, output):
    output.mkdir(parents=True, exist_ok=True)
    summary = dict(
        schema="c3-native-minimum.v1",
        planned=8,
        attempted=0,
        native_recorded=0,
        cases=[],
        status="RUNNING",
    )
    order = [("rpp", "empty")] + [
        (c, s) for c in ("rpp", "mppi") for s in SCENARIOS if (c, s) != ("rpp", "empty")
    ]
    for controller, scenario in order:
        case_dir = output / (controller + "-" + scenario)
        process = subprocess.run(
            [
                sys.executable,
                str(ROOT / "container/manage.py"),
                "run",
                "--lock",
                str(lock),
                "--controller",
                controller,
                "--scenario",
                scenario,
                "--variant",
                "baseline",
                "--seed",
                "20261024",
                "--repeat",
                "0",
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
        expected = "GOAL_REACHED" if scenario in SCENARIOS[:2] else "SAFE_WAIT"
        row = dict(
            controller=controller,
            scenario=scenario,
            returncode=process.returncode,
            status=result.get("status", "NO_RESULT"),
            outcome=result.get("outcome"),
            expected=expected,
            validation=validation,
            error=result.get("error"),
            terminal_fault=result.get("terminal_fault"),
            action=result.get("action"),
            metrics=result.get("metrics"),
            fixture_sha256=result.get("fixture_sha256"),
            config_sha256=result.get("config_sha256"),
            source_sha=environment.get("source_sha"),
            image_id=environment.get("image_id"),
        )
        row["expectation_met"] = (
            validation.get("status") == "PASS" and row["outcome"] == expected
        )
        summary["cases"].append(row)
        summary["attempted"] += 1
        summary["native_recorded"] += int(row["status"] == "NATIVE_RECORDED")
        (output / "minimum-summary.json").write_text(
            json.dumps(summary, indent=2) + "\n"
        )
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
            summary["status"] = "BLOCKED_AT_EMPTY_BASELINE"
            break
    else:
        summary["status"] = (
            "PASS"
            if all(r["expectation_met"] for r in summary["cases"])
            else "COMPLETED_WITH_FAILURES"
        )
    (output / "minimum-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(execute(args.lock, args.output))
