"""Compare native evidence only, preserving failures and incomplete matched pairs."""

import argparse
import json
from pathlib import Path
import statistics

from validate import validate_directory


def compare(root):
    rows, groups = [], {}
    for path in sorted(root.rglob("result.json")):
        record = json.loads(path.read_text())
        if record.get("backend") != "nav2_native_sim":
            continue
        try:
            validation = validate_directory(path.parent)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            validation = dict(status="FAIL", errors=["malformed evidence: " + str(exc)])
        row = dict(
            path=str(path.relative_to(root)),
            controller=record.get("controller"),
            variant=record.get("variant"),
            scenario=record.get("scenario"),
            repeat=record.get("repeat"),
            validation=validation,
            outcome=record.get("outcome"),
            metrics=record.get("metrics", {}),
            fixture_sha256=record.get("fixture_sha256"),
        )
        rows.append(row)
        groups.setdefault((row["variant"], row["scenario"], row["repeat"]), []).append(
            row
        )
    unmatched = [
        list(key)
        for key, values in groups.items()
        if len(values) != 2
        or {v["controller"] for v in values} != {"rpp", "mppi"}
        or len({v["fixture_sha256"] for v in values}) != 1
    ]
    aggregates = []
    for controller in ("rpp", "mppi"):
        for variant in ("baseline", "tuned"):
            selected = [
                r
                for r in rows
                if r["controller"] == controller and r["variant"] == variant
            ]
            valid = [r for r in selected if r["validation"]["status"] == "PASS"]
            reached = [r for r in valid if r["outcome"] == "GOAL_REACHED"]
            aggregates.append(
                dict(
                    controller=controller,
                    variant=variant,
                    runs=len(selected),
                    valid_native_runs=len(valid),
                    goal_reached=len(reached),
                    safe_wait=sum(r["outcome"] == "SAFE_WAIT" for r in valid),
                    failures=len(selected) - len(valid),
                    median_path_length_m=statistics.median(
                        r["metrics"]["path_length_m"] for r in reached
                    )
                    if reached
                    else None,
                    median_wall_time_s=statistics.median(
                        r["metrics"]["wall_time_s"] for r in reached
                    )
                    if reached
                    else None,
                )
            )
    return dict(
        backend="nav2_native_sim",
        status="NOT_RUN" if not rows else "RECORDED",
        rows=rows,
        unmatched_or_unfair_pairs=unmatched,
        aggregates=aggregates,
        recommendation="NO_RECOMMENDATION until complete matched repeats, zero collisions/boundary/hold violations, stale-stop and recovery hold checks pass. Rank safety first, then goal success, then measured completion/deadline/resource metrics. Host timings are not Jetson predictions.",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.write_text(json.dumps(compare(args.root), indent=2) + "\n")
