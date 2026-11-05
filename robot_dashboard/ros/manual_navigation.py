"""Private ROS contract for the job-bound manual odometry anchor."""
from __future__ import annotations

import json
import re
from pathlib import Path

MODE = "manual_seeded_2d"
OPERATIONAL_MODE = "operational_3d"
SEED_TOPIC = "/robot_scope/nav/manual_seed"
SEED_PUBLISHER_NAME = "robot_scope_agent"
POSE_SOURCE = "manual_seeded_odometry"
STOP_SECONDS = 2.0
CONTROL_FENCE_S = 1.5
LINEAR_STOP_MPS = 0.03
ANGULAR_STOP_RPS = 0.05
BINDING_KEYS = ("mode", "job_id", "map_id", "map_revision")


def binding(value):
    if not isinstance(value, dict) or value.get("mode") != MODE:
        return None
    job_id, map_id, revision = (value.get(key) for key in BINDING_KEYS[1:])
    if (not isinstance(job_id, str) or re.fullmatch("[a-f0-9]{32}", job_id) is None
            or not isinstance(map_id, str) or not map_id.strip() or len(map_id) > 256
            or not isinstance(revision, str) or re.fullmatch("[a-f0-9]{64}", revision) is None):
        return None
    return {key: value[key] for key in BINDING_KEYS}


def load_manual_binding(params_file):
    path = Path(params_file).parent / "manual-navigation.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("MANUAL_NAVIGATION_JOB_SNAPSHOT_REQUIRED")
    data = json.loads(path.read_text(encoding="utf-8"))
    validated = binding(data)
    if validated is None or set(data) != set(BINDING_KEYS) or validated["job_id"] != path.parent.name:
        raise ValueError("MANUAL_NAVIGATION_JOB_SNAPSHOT_INVALID")
    if any((path.parent / name).exists() or (path.parent / name).is_symlink()
           for name in ("operational-3d.json", "localization-reference.pcd")):
        raise ValueError("MANUAL_NAVIGATION_JOB_CONTAINS_3D_REFERENCE")
    return validated


def publisher_endpoint(node, topic, *, expected_name=None):
    """Return a single discovered endpoint's real graph GID, if available."""
    try:
        infos = node.get_publishers_info_by_topic(topic)
        if len(infos) != 1:
            return None
        endpoint = infos[0]
        if expected_name is not None and (endpoint.node_name, endpoint.node_namespace) != (expected_name, "/"):
            return None
        gid = bytes(endpoint.endpoint_gid)
        if len(gid) in (16, 24) and any(gid):
            return gid
    except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError):
        pass
    return None


def stamp_ns(stamp):
    if (type(stamp.sec) is not int or stamp.sec < 0 or type(stamp.nanosec) is not int
            or not 0 <= stamp.nanosec < 1_000_000_000):
        return 0
    return stamp.sec * 1_000_000_000 + stamp.nanosec


def stamp_string(value):
    return isinstance(value, str) and re.fullmatch("[1-9][0-9]{0,18}", value) is not None


def generation(value):
    return type(value) is int and 0 < value <= 2**53 - 1


def context(health):
    source = health.get("manual_seed") or {}
    return (binding(source), health.get("runtime_instance_generation"), source.get("source_epoch"))


def sanitize_status(raw):
    pins = binding(raw)
    if pins is None:
        return None
    state = raw.get("state")
    if state not in {"waiting_initial_pose", "checking_tf", "ready_manual", "reseed_required"}:
        return None
    if (not generation(raw.get("source_epoch")) or type(raw.get("seed_generation")) is not int
            or not 0 <= raw["seed_generation"] <= 2**53 - 1
            or type(raw.get("inputs_ready")) is not bool or type(raw.get("tf_readback")) is not bool):
        return None
    result = {
        **pins, "state": state, "pose_source": POSE_SOURCE, "source_epoch": raw["source_epoch"],
        "seed_generation": raw["seed_generation"], "inputs_ready": raw["inputs_ready"],
        "tf_readback": raw["tf_readback"], "reason": _reason(raw.get("reason")),
        "tf_readback_stamp_ns": raw.get("tf_readback_stamp_ns")
        if stamp_string(raw.get("tf_readback_stamp_ns")) else None,
    }
    for key in ("stopped_seconds", "seed_age_s", "odometry_distance_m"):
        value = raw.get(key)
        if type(value) not in (int, float) or not 0 <= value <= 1e9:
            result[key] = None
        else:
            result[key] = value
    receipt = raw.get("receipt")
    result["receipt"] = None
    if (isinstance(receipt, dict) and stamp_string(receipt.get("stamp_ns"))
            and type(receipt.get("accepted")) is bool and generation(receipt.get("source_epoch"))
            and type(receipt.get("seed_generation")) is int
            and 0 <= receipt["seed_generation"] <= 2**53 - 1):
        result["receipt"] = {
            "stamp_ns": receipt["stamp_ns"], "accepted": receipt["accepted"],
            "reason": _reason(receipt.get("reason")), "source_epoch": receipt["source_epoch"],
            "seed_generation": receipt["seed_generation"],
            "odometry_stamp_ns": receipt.get("odometry_stamp_ns")
            if stamp_string(receipt.get("odometry_stamp_ns")) else None,
            "accepted_ros_ns": receipt.get("accepted_ros_ns")
            if stamp_string(receipt.get("accepted_ros_ns")) else None,
        }
    return result


def _reason(value):
    if isinstance(value, str) and re.fullmatch("[A-Z0-9_]{1,80}", value):
        return value
    return "MANUAL_RUNTIME_STATUS_UNKNOWN"


class StopObservation:
    """Two seconds of advancing measured samples with no stale gap."""

    def __init__(self, timeout):
        self.timeout = timeout
        self.clear()

    def clear(self):
        self.at = None
        self.stamp = 0
        self.stopped_at = None
        self.stopped_stamp = 0

    def observe(self, stamp, now, linear, angular):
        if stamp <= self.stamp or stamp <= 0:
            self.clear()
            return False
        if (not self.fresh(now) or stamp - self.stamp > self.timeout * 1e9
                or linear > LINEAR_STOP_MPS or angular > ANGULAR_STOP_RPS):
            self.stopped_at = None
        elif self.stopped_at is None:
            self.stopped_at = now
            self.stopped_stamp = stamp
        self.at, self.stamp = now, stamp
        return True

    def fresh(self, now):
        return self.at is not None and 0 <= now - self.at <= self.timeout

    def stopped_seconds(self, now):
        if not self.fresh(now) or self.stopped_at is None:
            return 0.0
        return max(0.0, min(self.at - self.stopped_at, (self.stamp - self.stopped_stamp) * 1e-9))


class ManualSeed:
    """Runtime-local receipt and evidence lifetime independent of a map matcher."""

    def __init__(self, pins, odom_timeout):
        self.pins = pins
        self.odom_stop = StopObservation(odom_timeout)
        self.controller_stop = StopObservation(0.75)
        self.source_epoch = 1
        self.seed_generation = 0
        self.source_signature = None
        self.receipt = None
        self.last_request_ns = 0
        self.seeded_at = None
        self.control_seen_at = None
        self.distance_m = 0.0
        self.last_map_tf_stamp = 0
        self.tf_expected_stamp = 0
        self.tf_readback = False
        self.state = "waiting_initial_pose"
        self.reason = "WAITING_EXPLICIT_INITIAL_POSE"

    def invalidate(self, reason):
        if self.seeded_at is not None:
            self.seed_generation += 1
            self.state = "reseed_required"
        self.seeded_at = None
        self.control_seen_at = None
        self.tf_expected_stamp = 0
        self.tf_readback = False
        self.reason = reason if self.state == "reseed_required" else "WAITING_EXPLICIT_INITIAL_POSE"

    def observe_sources(self, signature):
        """Revoke the previous epoch even when uniqueness returns afterward."""
        if signature != self.source_signature:
            self.source_signature = signature
            self.source_epoch += 1
            self.odom_stop.clear()
            self.controller_stop.clear()
            self.invalidate("MANUAL_SOURCE_CHANGED")
            return True
        return False

    def request_stamp(self, payload, instance, now_ns):
        if (binding(payload) != self.pins or payload.get("runtime_instance_generation") != instance
                or type(payload.get("source_epoch")) is not int
                or payload["source_epoch"] != self.source_epoch
                or not stamp_string(payload.get("stamp_ns"))):
            return None
        stamp = int(payload["stamp_ns"])
        if stamp <= self.last_request_ns or not 0 <= now_ns - stamp <= 500_000_000:
            return None
        self.last_request_ns = stamp
        return stamp

    def acknowledge(self, stamp, reason, *, now=None, odom_stamp=0, accepted_ros_ns=0):
        accepted = now is not None
        if accepted:
            self.seed_generation += 1
            self.seeded_at = now
            self.control_seen_at = now
            self.distance_m = 0.0
            self.tf_expected_stamp = 0
            self.tf_readback = False
            self.state = "checking_tf"
        self.reason = reason
        self.receipt = {
            "stamp_ns": str(stamp), "accepted": accepted, "reason": reason,
            "source_epoch": self.source_epoch, "seed_generation": self.seed_generation,
            "odometry_stamp_ns": str(odom_stamp) if odom_stamp else None,
            "accepted_ros_ns": str(accepted_ros_ns) if accepted_ros_ns else None,
        }

    def keepalive(self, generation, now):
        if self.seeded_at is not None and type(generation) is int and generation == self.seed_generation:
            if self.control_fresh(now):
                self.control_seen_at = now
            else:
                self.invalidate("MANUAL_CONTROL_FENCE_STALE")

    def control_fresh(self, now):
        return self.control_seen_at is not None and 0 <= now - self.control_seen_at <= CONTROL_FENCE_S

    def note_map_tf_publication(self, source_stamp):
        # A reseed can use the latest already-broadcast odometry sample.
        # Wait for a strictly newer TF stamp so a cached old anchor cannot
        # satisfy readback or share a timestamp with a conflicting value.
        if source_stamp <= self.last_map_tf_stamp:
            return False
        self.last_map_tf_stamp = source_stamp
        if self.state == "checking_tf" and not self.tf_expected_stamp:
            self.tf_expected_stamp = source_stamp
        return True

    def observe_tf(self, message):
        if self.state != "checking_tf" or not self.tf_expected_stamp:
            return
        edges = {
            (transform.header.frame_id, transform.child_frame_id)
            for transform in message.transforms
            if stamp_ns(transform.header.stamp) == self.tf_expected_stamp
        }
        if {("map", "odom"), ("odom", "base_link")} <= edges:
            self.tf_readback = True
            self.state = "ready_manual"
            self.reason = "MANUAL_ANCHOR_READ_BACK"

    def stopped_seconds(self, now):
        return min(self.odom_stop.stopped_seconds(now), self.controller_stop.stopped_seconds(now))

    def snapshot(self, now, inputs_ready, input_reason):
        return {
            **self.pins, "pose_source": POSE_SOURCE, "state": self.state,
            "source_epoch": self.source_epoch, "seed_generation": self.seed_generation,
            "inputs_ready": inputs_ready, "reason": self.reason if inputs_ready else input_reason,
            "tf_readback": self.tf_readback, "receipt": self.receipt,
            "tf_readback_stamp_ns": str(self.tf_expected_stamp) if self.tf_readback else None,
            "stopped_seconds": self.stopped_seconds(now),
            "seed_age_s": round(now - self.seeded_at, 3) if self.seeded_at is not None else None,
            "odometry_distance_m": round(self.distance_m, 3) if self.seeded_at is not None else None,
        }
