"""Three narrow adapters. Internal archive manifest, NOT a C1 canonical DTO."""

import copy
from decimal import Decimal
import hashlib
import json
import math
import re

from .io import read_json, read_jsonl
from ..goal_precision import pose_error

SCHEMA = "robot-scope.run-review.v1"
MANIFEST = "robot-scope.run-review-manifest.v1"
KINDS = (
    "dispatch",
    "accepted",
    "rejected",
    "initialization",
    "path_update",
    "obstacle_appeared",
    "stale",
    "reconnect",
    "recovery",
    "cancel",
    "result",
    "command_zero",
    "bridge_ack",
    "measured_stop",
    "contact",
    "map_change",
    "pose",
    "scene",
    "input_gap",
    "unclassified",
)
META_KEYS = (
    "code_sha",
    "parameters_revision",
    "parameters_digest",
    "map_id",
    "map_revision",
    "goal_id",
    "data_kind",
    "source_id",
)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def pose(value):
    if not isinstance(value, dict) or not all(
        finite(value.get(k)) for k in ("x", "y", "yaw")
    ):
        return None
    return {
        k: value[k] for k in ("x", "y", "z", "yaw") if k in value and finite(value[k])
    }


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def timestamp(
    value=None, *, domain=None, epoch=None, sequence=None, basis="UNOBSERVED"
):
    return dict(
        value=value,
        clock_domain=domain,
        source_epoch=epoch,
        sequence=sequence,
        basis=basis,
    )


def seconds(value):
    # Only replay scheduling. The original float remains in timestamp/source data.
    return (
        int(Decimal(str(value)) * 1_000_000_000)
        if finite(value) and value >= 0
        else None
    )


def sample_summary(sample, goal):
    if not sample or not pose(sample.get("pose")):
        return None
    p = pose(sample["pose"])
    return dict(
        pose=p,
        stamp_ns=sample.get("stamp_ns"),
        frame_id=sample.get("frame_id"),
        received_ros_ns=sample.get("received_ros_ns"),
        received_monotonic_s=sample.get("received_monotonic_s"),
        offset_from_result_receipt_s=sample.get("offset_from_result_receipt_s"),
        source_age_at_receive_s=sample.get("source_age_at_receive_s"),
        error=pose_error(p, goal) if goal else None,
    )


class Builder:
    def __init__(self, manifest):
        self.meta = {k: manifest.get(k) for k in META_KEYS}
        self.events, self.frames, self.precision = [], [], {}
        self.last_clock = None
        self.last_ns = None
        self.anchor_ns = self.anchor_play = 0
        self.play_ns = 0
        self.gaps = []
        self.missing_time = 0
        self.delay_samples = []
        self.retained_bytes = 0
        self.discontinuities = 0

    def event(self, kind, time, payload=None, ns=None, clock=None):
        if len(self.events) >= 20000:
            raise ValueError("EVENT_LIMIT")
        if ns is not None and clock:
            if (
                clock == self.last_clock
                and self.last_ns is not None
                and ns >= self.last_ns
            ):
                delta = ns - self.last_ns
                if delta > 86_400_000_000_000:
                    raise ValueError("REPLAY_DURATION_LIMIT")
                self.play_ns = max(self.play_ns, self.anchor_play + ns - self.anchor_ns)
                if delta > 2_000_000_000:
                    self.gaps.append(
                        dict(
                            after_event=len(self.events) - 1,
                            seconds=delta / 1e9,
                            meaning="OBSERVATION_INTERVAL_NOT_SENSOR_LOSS",
                        )
                    )
            else:
                if self.events:
                    self.discontinuities += 1
                    self.play_ns += 1_000_000
                self.anchor_ns, self.anchor_play = ns, self.play_ns
            self.last_clock, self.last_ns = clock, ns
        elif self.events:
            self.play_ns += 1_000_000  # record order, not a measured interval
        if ns is None:
            self.missing_time += 1
        if self.events:
            self.play_ns = max(self.play_ns, int(self.events[-1]["replay_ns"]) + 1)
        item = dict(
            index=len(self.events),
            kind=kind if kind in KINDS else "unclassified",
            replay_ns=str(self.play_ns),
            time=time,
            payload=payload or {},
        )
        self.retain(item)
        self.events.append(item)
        return item

    def retain(self, value):
        self.retained_bytes += len(json.dumps(value, separators=(",", ":")).encode())
        if self.retained_bytes > 32 * 1024 * 1024:
            raise ValueError("REVIEW_MEMORY_BUDGET")

    def frame(self, value):
        self.retain(value)
        self.frames.append(value)

    def finish(self):
        counts = {k: sum(e["kind"] == k for e in self.events) for k in KINDS}
        return dict(
            schema=SCHEMA,
            mode="REPLAY",
            provenance=self.meta,
            events=self.events,
            frames=self.frames,
            precision=self.precision,
            observations={k: n if n else "UNOBSERVED" for k, n in counts.items()},
            quality=dict(
                input_gaps=self.gaps,
                events_without_independent_time=self.missing_time,
                receive_age_s=dict(
                    samples=len(self.delay_samples),
                    minimum=min(self.delay_samples, default=None),
                    maximum=max(self.delay_samples, default=None),
                ),
                cross_host_latency="UNOBSERVED",
                clock_discontinuities=self.discontinuities,
                replay_timing="SOURCE_DELTAS_WITH_RECORD_ORDER_FALLBACK",
            ),
            input_digest=digest(self.events),
        )


def goal_evidence(root, manifest):
    b = Builder(manifest)
    requested = None
    last_context = None
    previous_plan = previous_stale = None
    for row in read_jsonl(root, manifest["file"]):
        if row.get("schema") != "robot-scope.goal-evidence-log.v1" or not isinstance(
            row.get("evidence"), dict
        ):
            raise ValueError("GOAL_EVIDENCE_SCHEMA")
        e = row["evidence"]
        if e.get("goal_id") != manifest["goal_id"]:
            continue
        context = e.get("context")
        if context:
            current_context = (context.get("map_id"), context.get("map_revision"))
            if last_context is not None and current_context != last_context:
                b.event(
                    "map_change",
                    timestamp(),
                    dict(map_id=current_context[0], map_revision=current_context[1]),
                )
            last_context = current_context
            for target, source in [
                ("map_id", "map_id"),
                ("map_revision", "map_revision"),
                ("parameters_revision", "parameters_revision"),
            ]:
                if context.get(source):
                    if b.meta[target] and b.meta[target] != context[source]:
                        # Actual per-record identity remains visible; comparison must see variation.
                        b.meta[target] = None
                    else:
                        b.meta[target] = context[source]
        observed_parameters = e.get("effective_at_result") or (context or {}).get(
            "effective_at_dispatch"
        )
        if observed_parameters and any(
            observed_parameters.get(k) for k in ("controller", "planner")
        ):
            b.meta["parameters_digest"] = digest(
                {k: observed_parameters.get(k) for k in ("controller", "planner")}
            )
        if e.get("requested"):
            requested = pose(e["requested"].get("pose"))
        current = e.get("current")
        if current and finite(current.get("source_age_at_receive_s")):
            b.delay_samples.append(current["source_age_at_receive_s"])
        kind = {
            "sample": "pose",
            "zero_issued": "command_zero",
            "first_measured_stop": "measured_stop",
        }.get(row["event"], row["event"])
        source, field = None, None
        if kind == "dispatch":
            source, field = e.get("transmitted"), "stamp_ns"
        elif kind == "result":
            source, field = e.get("result"), "received_ros_ns"
        elif kind == "command_zero":
            source, field = e.get("zero_command_issued"), "issued_ros_ns"
        elif kind == "measured_stop":
            source, field = e.get("after_stop"), "stamp_ns"
        elif kind == "pose":
            source, field = current, "stamp_ns"
        raw_time = source.get(field) if source else None
        t = timestamp(
            raw_time,
            domain=manifest.get("clock_domain"),
            epoch=manifest.get("source_epoch"),
            basis="RESULT_RECEIPT_NOT_SUCCESS"
            if kind == "result"
            else field or "EVENT_TIME_UNOBSERVED",
        )
        ns = int(raw_time) if raw_time is not None else None
        payload = dict(
            goal_id=e["goal_id"],
            requested=requested,
            current=sample_summary(current, requested),
            map_id=context.get("map_id")
            if context
            else (last_context or (None, None))[0],
            map_revision=context.get("map_revision")
            if context
            else (last_context or (None, None))[1],
            source_epoch=current.get("source_generation") if current else None,
            sequence=None,
            original_event=row["event"],
        )
        if kind == "result":
            payload["state"] = (e.get("result") or {}).get("state")
        if raw_time is None:
            payload["associated_sample_stamp_ns"] = (
                current.get("stamp_ns") if current else None
            )
        b.event(
            kind,
            t,
            payload,
            ns,
            (t["clock_domain"], t["source_epoch"])
            if all((t["clock_domain"], t["source_epoch"]))
            else None,
        )
        # Preserve updates to metrology made after the terminal result.
        for key in (
            "result",
            "near_result",
            "after_stop",
            "zero_command_issued",
            "motion_vs_correction",
        ):
            if e.get(key) is not None:
                b.precision[key] = copy.deepcopy(e[key])
        b.precision["requested"] = requested
        plan = e.get("plan_endpoint")
        if plan and plan.get("stamp_ns") != previous_plan:
            previous_plan = plan.get("stamp_ns")
            b.event(
                "path_update",
                timestamp(
                    previous_plan,
                    domain=t["clock_domain"],
                    epoch=t["source_epoch"],
                    basis="ENDPOINT_ONLY_NO_PATH_GEOMETRY",
                ),
                dict(endpoint=sample_summary(plan, requested)),
            )
        stale = e.get("unavailable_reason") or (
            "POSE_STALE" if current and current.get("fresh") is False else None
        )
        if stale and not previous_stale:
            b.event("stale", timestamp(), dict(reason=stale))
        if previous_stale and current and current.get("fresh") is True and not stale:
            b.event(
                "reconnect", timestamp(), dict(basis="FRESH_SAMPLE_AFTER_GAP_NOT_LIVE")
            )
        previous_stale = stale
    if not b.events:
        raise ValueError("GOAL_INPUT_REQUIRED")
    raw = b.precision
    b.precision = dict(
        requested=requested,
        result=raw.get("result"),
        near_result=sample_summary(raw.get("near_result"), requested),
        after_stop=sample_summary(raw.get("after_stop"), requested),
        zero_command_issued=raw.get("zero_command_issued"),
        bridge_ack="UNOBSERVED",
        contact="UNOBSERVED",
        motion_vs_correction=None,
    )
    a, z = raw.get("near_result"), raw.get("after_stop")
    # Never compute a new unpaired decomposition. Reuse the producer's exact pair only.
    if (
        a
        and z
        and a.get("source_generation") == z.get("source_generation")
        and all(
            s.get("stamp_ns") == s.get("odom_body", {}).get("stamp_ns")
            and s.get("map_odom_transform")
            for s in (a, z)
        )
        and (raw.get("motion_vs_correction") or {}).get("pairing")
        == "EXACT_SOURCE_STAMP_FULL_SE3"
    ):
        b.precision["motion_vs_correction"] = raw["motion_vs_correction"]
    return b.finish()


def c1_scene(root, manifest, validator=None):
    b = Builder(manifest)
    prior = None
    retired = {}
    seen_contexts = set()
    previous_context = None
    for row in read_jsonl(root, manifest["file"]):
        if row.get("schema") != "robot-scope.c1-scene-record.v1":
            raise ValueError("C1_ARCHIVE_ENVELOPE_REQUIRED")
        wire, context, t = row["packet"], row["context"], row["recorded_at"]
        if wire.get("schema_version") not in ("0.1", "0.2"):
            raise ValueError("C1_VERSION_REQUIRED")
        if validator is None:
            raise ValueError("PINNED_C1_VALIDATOR_REQUIRED")
        validator(wire)
        if (
            not isinstance(t.get("stamp_ns"), str)
            or not t["stamp_ns"].isdigit()
            or not t.get("clock_domain")
            or not t.get("source_epoch")
        ):
            raise ValueError("ARCHIVE_TIME_REQUIRED")
        binding = wire["map_binding"]
        if (
            any(
                context.get(k) != binding[k]
                for k in ("map_id", "revision", "generation")
            )
            or context.get("stream_epoch") != wire["stream_epoch"]
        ):
            raise ValueError("C1_CONTEXT_MISMATCH")
        context_key = (
            binding["map_id"],
            binding["revision"],
            binding["generation"],
            wire["stream_epoch"],
        )
        if context_key != previous_context:
            if context_key in seen_contexts:
                raise ValueError("C1_RETIRED_CONTEXT_REAPPEARED")
            seen_contexts.add(context_key)
            retired.clear()
        elif prior and wire["sequence"] < prior["sequence"]:
            raise ValueError("C1_SEQUENCE_ROLLBACK")
        for slot, source in wire.get("sources", {}).items():
            if not isinstance(source, dict) or not isinstance(
                source.get("sequence"), int
            ):
                continue
            key = (slot, source.get("source_epoch"))
            if source.get("status") in ("expired", "unavailable"):
                retired[key] = max(retired.get(key, -1), source["sequence"])
            elif source.get("status") == "ready" and source["sequence"] <= retired.get(
                key, -1
            ):
                raise ValueError("C1_RETIRED_SOURCE_REAPPEARED")
        previous_context = context_key
        tm = timestamp(
            t["stamp_ns"],
            domain=t["clock_domain"],
            epoch=t["source_epoch"],
            sequence=wire["sequence"],
            basis="ARCHIVE_RECEIPT",
        )
        frame = dict(packet=wire, context=context, recorded_at=t)
        item = b.event(
            "scene", tm, {}, int(t["stamp_ns"]), (t["clock_domain"], t["source_epoch"])
        )
        frame["replay_ns"] = item["replay_ns"]
        frame["event_index"] = item["index"]
        b.frame(frame)
        if prior:
            if binding != prior["map_binding"]:
                b.event("map_change", tm, binding)
            if wire["stream_epoch"] != prior["stream_epoch"]:
                b.event("reconnect", tm, dict(basis="RECORDED_STREAM_EPOCH_CHANGE"))
        for slot, event in [
            ("global_path", "path_update"),
            ("obstacle_frame", "obstacle_appeared"),
        ]:
            value = wire.get(slot)
            if (
                value
                and (not prior or value != prior.get(slot))
                and (slot != "obstacle_frame" or value.get("obstacles"))
            ):
                b.event(
                    event,
                    tm,
                    dict(
                        source_stamp_ns=value["stamp_ns"],
                        source_epoch=value["source_epoch"],
                        sequence=value["sequence"],
                    ),
                )
        if any(
            v.get("status") == "expired"
            for v in wire.get("sources", {}).values()
            if isinstance(v, dict)
        ):
            b.event("stale", tm, dict(basis="RECORDED_C1_EXPIRED"))
        prior = wire
    if not b.frames:
        raise ValueError("SCENE_INPUT_REQUIRED")
    return b.finish()


def d3_native(root, manifest, validator=None):
    """Existing result/trace/observations, never launch a simulator or extract archives."""
    b = Builder(manifest)
    if manifest["data_kind"] != "SIMULATION":
        raise ValueError("NATIVE_IS_SIMULATION")
    result = read_json(root, manifest["result_file"], limit=4 * 1024 * 1024)
    if (
        result.get("schema") != "competition-nav2-result.v1"
        or result.get("observation_schema") != "c3-native-observations.v1"
        or result.get("status") != "NATIVE_RECORDED"
    ):
        raise ValueError("NATIVE_SCHEMA_REQUIRED")
    b.meta["parameters_digest"] = (
        digest(result["parameters"]) if result.get("parameters") else None
    )
    goal = pose(manifest.get("goal"))
    records = []
    for row in read_jsonl(root, manifest["trace_file"]):
        if (
            not finite(row.get("sim_t"))
            or not isinstance(row.get("pose"), list)
            or len(row["pose"]) != 3
            or not all(finite(v) for v in row["pose"])
        ):
            raise ValueError("NATIVE_TRACE_SCHEMA")
        records.append(("pose", row["sim_t"], row))
    for row in read_jsonl(root, manifest["observations_file"]):
        if not finite(row.get("sim_t")) or row.get("kind") not in (
            "path",
            "costmap",
            "scan",
            "odom",
            "action",
            "feedback",
            "appearance",
        ):
            raise ValueError("NATIVE_OBSERVATION_SCHEMA")
        records.append(
            (
                "path_update"
                if row["kind"] == "path"
                else "obstacle_appeared"
                if row["kind"] == "appearance"
                else "scene",
                row["sim_t"],
                row,
            )
        )
        if len(records) > 20000:
            raise ValueError("NATIVE_RECORD_LIMIT")
    records.sort(key=lambda r: r[1])
    projection = NativeProjection(manifest, validator) if validator else None
    for kind, sim_time, record in records:
        item = b.event(
            kind,
            timestamp(
                sim_time,
                domain=manifest.get("clock_domain"),
                epoch=manifest.get("source_epoch"),
                basis="RECORDED_FLOAT_SECONDS",
            ),
            dict(original=record),
            seconds(sim_time),
            (manifest.get("clock_domain"), manifest.get("source_epoch")),
        )
        if projection and kind in ("pose", "path_update"):
            frame = projection.frame(kind, record)
            if frame:
                frame.update(replay_ns=item["replay_ns"], event_index=item["index"])
                b.frame(frame)
    state = {4: "succeeded", 5: "canceled", 6: "failed"}.get(
        result.get("action", {}).get("status"), "unobserved"
    )
    b.event(
        "result", timestamp(), dict(state=state, timing="RESULT_TIMESTAMP_UNOBSERVED")
    )
    for event in result.get("action_events", []):
        b.event(
            "recovery"
            if event.get("type") == "native_spin_during_hold"
            else "unclassified",
            timestamp(),
            dict(original=event),
        )
    if result.get("terminal_fault") == "SENSOR_STALE":
        b.event("stale", timestamp(), dict(basis="NATIVE_TERMINAL_FAULT"))
    b.precision = dict(
        requested=goal,
        result=dict(state=state, timing="RESULT_TIMESTAMP_UNOBSERVED"),
        near_result=None,
        after_stop=None,
        native_report_final=dict(
            xy_m=result.get("goal_distance_m"),
            abs_yaw_rad=result.get("goal_yaw_error_rad"),
        ),
        bridge_ack="UNOBSERVED",
        measured_stop="UNOBSERVED",
        simulated_contact_count=result.get("metrics", {}).get(
            "footprint_collision_count"
        ),
        motion_vs_correction=None,
    )
    return b.finish()


class NativeProjection:
    """Existing C1 producer creates display-only archived slices of provided pose/path.

    C1 has no native recording DTO. This is C6's explicit profile; float seconds
    are rounded solely for display envelopes. Original float records are retained.
    Missing joints, obstacle boxes, costmap geometry and contact are never invented.
    """

    def __init__(self, manifest, validator):
        from robot_dashboard.expansion_services.scene import SceneSnapshotService

        self.m, self.validator = manifest, validator
        self.now = 0
        self.binding = dict(
            map_id=manifest["map_id"], revision=manifest["map_revision"], generation=0
        )
        self.service = SceneSnapshotService(
            self.binding,
            schema_version="0.2",
            host_clock_id="native-archive-host",
            stream_epoch="native-archive-stream",
            clock=lambda: self.now,
        )
        self.seq = 0

    def frame(self, kind, record):
        receipt = (
            record.get("monotonic")
            if kind == "pose"
            else record.get("receipt_monotonic")
        )
        if seconds(receipt) is None:
            return None
        self.now = seconds(receipt)
        self.seq += 1
        if kind == "pose":
            x, y, yaw = record["pose"]
            data = dict(
                position_m=[x, y, 0],
                rpy_rad=[0, 0, yaw],
                provenance={"pose_source": "SIM_GT_2D_GROUND_PLANE"},
            )
            source = record["sim_t"]
            slot = "robot_pose"
        else:
            data = dict(
                points_m=record["points"],
                dimensions=2,
                representation="2D_GROUND_PLANE",
                plane_z_m=0,
                generation=str(self.seq),
            )
            source = record["source_sim_s"]
            slot = "global_path"
        observation = dict(
            schema_version="0.2",
            evidence_kind="REPLAY",
            producer="c6.d3-archive-projection",
            sequence=self.seq,
            source_epoch=self.m["source_epoch"],
            frame_key=dict(source_epoch=self.m["source_epoch"], frame_id="map"),
            stamp_ns=str(seconds(source)),
            clock_domain=self.m["clock_domain"],
            host_clock_id="native-archive-host",
            received_monotonic_ns=str(self.now),
            map_binding=self.binding,
            data=data,
            health=dict(
                state="RECORDED_NATIVE_SIM",
                precision="FLOAT_SECONDS_ROUNDED_FOR_DISPLAY",
                original_source_seconds=source,
                original_receipt_seconds=receipt,
            ),
        )
        if not self.service.ingest(slot, observation):
            raise ValueError("NATIVE_DISPLAY_REJECTED")
        wire = self.service.snapshot()
        self.validator(wire)
        return dict(
            packet=wire,
            context=dict(
                **self.binding,
                frame_id="map",
                source_epoch=self.m["source_epoch"],
                stream_epoch="native-archive-stream",
                clock_domain=self.m["clock_domain"],
                calibration_id="UNAVAILABLE",
                units="m",
            ),
            recorded_at=dict(
                stamp_ns=str(self.now),
                clock_domain="native-archive-host",
                source_epoch=self.m["source_epoch"],
            ),
        )


def load_run(root, manifest, *, validator=None):
    if manifest.get("schema") != MANIFEST or manifest.get("data_kind") not in (
        "REAL",
        "SYNTHETIC",
        "SIMULATION",
        "UNKNOWN",
    ):
        raise ValueError("MANIFEST_SCHEMA_OR_KIND")
    sha = manifest.get("code_sha")
    if sha is not None and not re.fullmatch("[a-f0-9]{40}", sha):
        raise ValueError("CODE_SHA_INVALID")
    fmt = manifest.get("format")
    if fmt == "goal-evidence-v1":
        return goal_evidence(root, manifest)
    if fmt == "c1-scene-v1":
        return c1_scene(root, manifest, validator)
    if fmt == "d3-native-v1":
        return d3_native(root, manifest, validator)
    raise ValueError("UNSUPPORTED_FORMAT")
