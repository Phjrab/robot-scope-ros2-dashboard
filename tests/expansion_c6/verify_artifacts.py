"""Explicit local artifact verification. Outputs private bundles and allowlisted summaries."""

import argparse
import hashlib
from pathlib import Path

from robot_dashboard.run_review.dependencies import c1_validator
from robot_dashboard.run_review.io import read_json, read_jsonl, write_new
from robot_dashboard.run_review.review import MANIFEST, load_run
from robot_dashboard.run_review.summary import compare, markdown, summary


def verify(args):
    args.output.mkdir(mode=0o700)
    public_dir = args.output / "public"
    public_dir.mkdir(mode=0o700)
    receipts = []
    validate = c1_validator(args.deps)
    if args.goal_root:
        source = args.goal_root / "events.jsonl"
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        # Bounded iterator validates the input before selecting goal IDs.
        originals = {}
        for row in read_jsonl(args.goal_root, "events.jsonl"):
            e = row["evidence"]
            if e.get("near_result") and e.get("after_stop"):
                originals[e["goal_id"]] = e
        runs = []
        for index, (goal, e) in enumerate(originals.items()):
            m = dict(
                schema=MANIFEST,
                format="goal-evidence-v1",
                file="events.jsonl",
                goal_id=goal,
                code_sha=args.goal_code_sha,
                data_kind="REAL",
                source_id="LOCAL_GOAL_EVIDENCE",
                clock_domain="recorded-service-ros",
                source_epoch=e["context"]["job_id"],
            )
            run = load_run(args.goal_root, m)
            for key in ("near_result", "after_stop"):
                assert run["precision"][key]["stamp_ns"] == e[key]["stamp_ns"]
                assert run["precision"][key]["pose"] == e[key]["pose"]
            assert run["precision"]["requested"] == e["requested"]["pose"]
            write_new(args.output / f"goal-{index}.private.json", run)
            public = summary(run)
            write_new(public_dir / f"goal-{index}.json", public)
            write_new(public_dir / f"goal-{index}.md", markdown(public))
            runs.append(run)
            receipts.append(
                dict(
                    kind="REAL",
                    original_pose_goal_time="EXACT_MATCH",
                    result=public["result_state"],
                    events=len(run["events"]),
                )
            )
        assert before == hashlib.sha256(source.read_bytes()).hexdigest()
        if len(runs) == 2:
            write_new(public_dir / "field-comparison.json", compare(*runs))
        receipts.append(dict(original_sha256=before, original_unchanged=True))
    if args.native_root:
        for path in sorted(args.native_root.glob("*.manifest.json")):
            m = read_json(args.native_root, path.name)
            run = load_run(args.native_root, m, validator=validate)
            name = path.name.split(".")[0]
            write_new(args.output / (name + ".private.json"), run)
            receipts.append(
                dict(
                    kind="RECORDED_NATIVE_SIM",
                    case=name,
                    events=len(run["events"]),
                    frames=len(run["frames"]),
                    result=run["precision"]["result"]["state"],
                    local_native_execution="NOT_RUN",
                )
            )
    write_new(
        public_dir / "artifact-verification.json",
        dict(receipts=receipts, robot_control_mutations=0),
    )
    print(
        "Artifact verification complete; public/ contains only allowlisted summaries."
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--deps", type=Path, required=True)
    p.add_argument("--goal-root", type=Path)
    p.add_argument("--goal-code-sha")
    p.add_argument("--native-root", type=Path)
    p.add_argument("--output", type=Path, required=True)
    verify(p.parse_args())
