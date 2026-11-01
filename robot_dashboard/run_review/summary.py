"""Allowlisted public projection: no raw context, arbitrary strings, paths or assets."""

import hashlib
import json
import re

from .review import META_KEYS, finite, pose


def identifier(value):
    # Human free text/hostnames/paths never cross the public boundary. Hash opaque IDs.
    if value is None:
        return None
    if isinstance(value, str) and re.fullmatch("[a-f0-9]{24,64}", value):
        return value
    return "sha256:" + hashlib.sha256(str(value).encode()).hexdigest()


def error(value):
    return {
        k: v
        for k, v in (value or {}).items()
        if k in ("xy_m", "yaw_rad", "abs_yaw_rad") and finite(v)
    } or None


def sample(value):
    if not value:
        return None
    return dict(
        pose=pose(value.get("pose")),
        stamp_ns=value.get("stamp_ns"),
        received_ros_ns=value.get("received_ros_ns"),
        error=error(value.get("error")),
    )


def summary(run):
    p = run["precision"]
    meta = run["provenance"]
    result = p.get("result") or {}
    state = (
        result.get("state")
        if result.get("state")
        in ("succeeded", "canceled", "failed", "rejected", "unobserved")
        else "unobserved"
    )
    public = dict(
        schema="robot-scope.run-review-summary.v1",
        mode="REPLAY",
        provenance={
            k: (meta[k] if k == "data_kind" else identifier(meta[k])) for k in META_KEYS
        },
        input_digest=run["input_digest"],
        requested=pose(p.get("requested")),
        result_state=state,
        result_received_ros_ns=result.get("received_ros_ns"),
        result_timing="RESULT_RECEIPT_NOT_SUCCESS"
        if result.get("received_ros_ns")
        else "UNOBSERVED",
        near_result=sample(p.get("near_result")),
        after_stop=sample(p.get("after_stop")),
        native_report_final=error(p.get("native_report_final")),
        motion_vs_correction={
            k: v
            for k, v in (p.get("motion_vs_correction") or {}).items()
            if k
            in (
                "body_odom_translation_m",
                "body_odom_rotation_rad",
                "map_odom_translation_m",
                "map_odom_rotation_rad",
            )
            and finite(v)
        }
        or None,
        translation_semantics="3D_TRANSLATION_NORM_NOT_XY",
        observations=run["observations"],
        quality=dict(
            events_without_independent_time=run["quality"][
                "events_without_independent_time"
            ],
            observation_gap_count=len(run["quality"]["input_gaps"]),
            cross_host_latency="UNOBSERVED",
        ),
        events=[
            dict(
                index=e["index"],
                kind=e["kind"],
                replay_ns=e["replay_ns"],
                original_time=e["time"]["value"],
                clock_domain=identifier(e["time"]["clock_domain"]),
                source_epoch=identifier(e["time"]["source_epoch"]),
                sequence=e["time"]["sequence"],
            )
            for e in run["events"][:80]
        ],
        event_table_truncated=len(run["events"]) > 80,
    )
    return public


def compare(a, b):
    sa, sb = summary(a), summary(b)
    differences = []
    for key in META_KEYS:
        x, y = a["provenance"][key], b["provenance"][key]
        if x != y or x is None or y is None:
            differences.append(
                dict(
                    field=key,
                    left=sa["provenance"][key],
                    right=sb["provenance"][key],
                    reason="DIFFERENT" if x != y else "UNOBSERVED",
                )
            )
    if sa["requested"] != sb["requested"] or sa["requested"] is None:
        differences.append(
            dict(
                field="goal_pose",
                left=sa["requested"],
                right=sb["requested"],
                reason="DIFFERENT_OR_UNOBSERVED",
            )
        )
    return dict(
        schema="robot-scope.run-review-comparison.v1",
        classification="REFERENCE_COMPARISON_NOT_SAME_CONDITION_AB"
        if differences
        else "RECORDED_METADATA_MATCH_NOT_CAUSAL_PROOF",
        differences=differences,
        left=sa,
        right=sb,
        algorithm_improvement_rate=None,
    )


def markdown(value):
    if value.get("schema") == "robot-scope.run-review-comparison.v1":
        return (
            "# REPLAY comparison\n\n"
            + value["classification"]
            + "\n\n```json\n"
            + json.dumps(value, ensure_ascii=False, indent=2)
            + "\n```\n"
        )
    lines = [
        "# REPLAY run review",
        "",
        "Read-only archived evidence. Missing events are UNOBSERVED.",
        "",
        "Result: " + value["result_state"],
        "Timing: " + value["result_timing"],
        "",
        "```json",
        json.dumps(
            {k: v for k, v in value.items() if k != "events"},
            ensure_ascii=False,
            indent=2,
        ),
        "```",
        "",
        "| # | Event | Replay ns | Original time |",
        "|---:|---|---:|---|",
    ]
    for e in value["events"]:
        lines.append(
            f"| {e['index']} | {e['kind']} | {e['replay_ns']} | {e['original_time']} |"
        )
    return "\n".join(lines) + "\n"
