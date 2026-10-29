"""Bounded read-only goal metrology. Never supplies a motion/arrival permission.

Action results have no success timestamp. We retain the nearest *received*
localization sample, including its source time offset, rather than invent one.
Only exact-stamp map/body + odom/body pairs can separate correction and motion.
"""

from __future__ import annotations

from collections import deque
import copy
import math

import numpy as np

from .relocalization.experimental_se3 import (
    from_translation_quaternion,
    inverse,
    rotation_error_rad,
)

SCHEMA = "robot-scope.goal-precision.v1"
MAX_AGE_S = 0.5
PRECISION_LIMITS = {"xy_m": 0.10, "yaw_rad": 0.10}


def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def pose_error(pose, goal):
    return {
        "xy_m": math.hypot(pose["x"] - goal["x"], pose["y"] - goal["y"]),
        "yaw_rad": wrap(pose["yaw"] - goal["yaw"]),
    }


def read_pose(message, expected_frame, now_ns, received):
    """Validate actual ROS source clock/frame. Do not retimestamp old samples."""
    if message.header.frame_id != expected_frame:
        raise ValueError("FRAME_MISMATCH")
    stamp = message.header.stamp
    if (
        type(stamp.sec) is not int
        or type(stamp.nanosec) is not int
        or not 0 <= stamp.nanosec < 10**9
    ):
        raise ValueError("INVALID_STAMP")
    ns = stamp.sec * 10**9 + stamp.nanosec
    age = (now_ns - ns) / 1e9
    if ns <= 0 or now_ns <= 0 or not 0 <= age <= MAX_AGE_S:
        raise ValueError("STALE_OR_FUTURE_POSE")
    pose = message.pose.pose if hasattr(message.pose, "pose") else message.pose
    p, q = pose.position, pose.orientation
    xyz, quat = (
        [float(p.x), float(p.y), float(p.z)],
        [float(q.x), float(q.y), float(q.z), float(q.w)],
    )
    if not all(math.isfinite(v) for v in xyz + quat) or max(map(abs, xyz)) > 10000:
        raise ValueError("INVALID_POSE")
    norm = float(np.linalg.norm(quat))
    if abs(norm - 1) > 0.01:
        raise ValueError("INVALID_QUATERNION")
    matrix = from_translation_quaternion(xyz, np.array(quat) / norm)
    return {
        "stamp_ns": str(ns),
        "received_ros_ns": str(now_ns),
        "received_monotonic_s": received,
        "source_age_at_receive_s": age,
        "frame_id": expected_frame,
        "body_frame_id": "base_link",
        "pose": {
            "x": xyz[0],
            "y": xyz[1],
            "z": xyz[2],
            "yaw": math.atan2(matrix[1, 0], matrix[0, 0]),
        },
        "transform": matrix.tolist(),
    }


def parameter_observation(readback):
    """Retain live values as observed; missing values are never inferred defaults."""
    parameters = readback.get("parameters", {})
    controller = parameters.get("/controller_server", {})
    return {
        "status": readback.get("status", "unavailable"),
        "age_s": readback.get("age_s"),
        "sequence": readback.get("sequence"),
        "controller": copy.deepcopy(controller),
        "planner": copy.deepcopy(parameters.get("/planner_server", {})),
        "lifecycle": copy.deepcopy(readback.get("lifecycle", {})),
    }


class GoalPrecision:
    def __init__(self):
        self.context = {}
        self.reset()

    def reset(self):
        self.goal_id = None
        self.goal = None
        self.result = None
        self.near_result = None
        self.after_stop = None
        self.latest = None
        self.invalid_reason = "NO_POSE"
        self.samples = deque(maxlen=64)
        self.odometry = deque(maxlen=64)
        self.still_since = None
        self.still_stamp = None
        self.stop_window = None
        self.plan = None
        self.wire_goal = None
        self.zero = None
        self.live_parameters = None
        self.source_generation = None
        self.last_log = -math.inf
        self.logged_samples = 0
        self.logged_stop = False
        self.action_uuid = None
        self.source_changed = False

    def start(self, goal_id, goal, context):
        self.reset()
        self.goal_id, self.goal = goal_id, dict(goal)
        self.context = copy.deepcopy(context)

    def sent(self, message, now_ns, now):
        try:
            self.wire_goal = read_pose(message, "map", now_ns, now)
            self.wire_goal["request_error"] = pose_error(
                self.wire_goal["pose"], self.goal
            )
        except (ValueError, TypeError, AttributeError):
            self.wire_goal = {"reason": "TRANSMITTED_POSE_UNAVAILABLE"}

    def accepted(self, handle):
        raw = getattr(getattr(handle, "goal_id", None), "uuid", None)
        if raw is not None and len(raw) == 16:
            self.action_uuid = bytes(raw).hex()

    def issued_zero(self, now_ns, now):
        if self.result and self.zero is None:
            self.zero = {
                "issued_ros_ns": str(now_ns),
                "issued_monotonic_s": now,
                "bridge_ack": "UNOBSERVED",
            }

    def observe_odom(self, message, now_ns, now):
        if not self.goal_id:
            return
        try:
            if message.child_frame_id != "base_link":
                raise ValueError("BODY_FRAME_MISMATCH")
            sample = read_pose(message, "odom", now_ns, now)
            if self.odometry:
                previous = self.odometry[-1]
                dt = (int(sample["stamp_ns"]) - int(previous["stamp_ns"])) / 1e9
                receipt_gap = now - previous["received_monotonic_s"]
                if dt <= 0:
                    return
                a, b = np.array(previous["transform"]), np.array(sample["transform"])
                speed = float(np.linalg.norm(b[:3, 3] - a[:3, 3])) / dt
                angular = rotation_error_rad(a, b) / dt
                sample.update(linear_speed_mps=speed, angular_speed_rps=angular)
                if (
                    dt <= MAX_AGE_S
                    and 0 <= receipt_gap <= MAX_AGE_S
                    and speed <= 0.03
                    and angular <= 0.05
                ):
                    if self.still_since is None:
                        self.still_since, self.still_stamp = (
                            now,
                            int(sample["stamp_ns"]),
                        )
                else:
                    self.still_since = self.still_stamp = self.stop_window = None
            self.odometry.append(sample)
            self._pair()
        except (ValueError, TypeError, AttributeError, OverflowError):
            self.still_since = self.still_stamp = self.stop_window = None

    def observe_map(self, message, now_ns, now, generation):
        if not self.goal_id:
            return
        try:
            sample = read_pose(message, "map", now_ns, now)
            if generation != self.source_generation:
                if self.source_generation is not None:
                    self.source_changed = True
                self.samples.clear()
                self.odometry.clear()
                self.still_since = self.still_stamp = self.stop_window = None
                self.source_generation = generation
            if self.samples and int(sample["stamp_ns"]) <= int(
                self.samples[-1]["stamp_ns"]
            ):
                return
            sample["source_generation"] = generation
            sample["error"] = pose_error(sample["pose"], self.goal)
            self.samples.append(sample)
            self.latest, self.invalid_reason = sample, None
            self._pair()
        except (ValueError, TypeError, AttributeError, OverflowError) as exc:
            self.invalid_reason = (
                str(exc) if isinstance(exc, ValueError) else "INVALID_POSE"
            )

    def _pair(self):
        if not self.latest:
            return
        sample = self.latest
        odom = next(
            (o for o in reversed(self.odometry) if o["stamp_ns"] == sample["stamp_ns"]),
            None,
        )
        if odom:
            sample["odom_body"] = copy.deepcopy(odom)
            sample["map_odom_transform"] = (
                np.array(sample["transform"]) @ inverse(np.array(odom["transform"]))
            ).tolist()
        if self.result:
            # Wait at most 0.5s for the nearest before/after-result sample.
            if (
                not self.source_changed
                and abs(
                    sample["received_monotonic_s"] - self.result["received_monotonic_s"]
                )
                <= MAX_AGE_S
                and abs(int(sample["stamp_ns"]) - int(self.result["received_ros_ns"]))
                <= MAX_AGE_S * 1e9
            ):
                delta = abs(
                    int(sample["stamp_ns"]) - int(self.result["received_ros_ns"])
                )
                if self.near_result is None or delta <= abs(
                    int(self.near_result["stamp_ns"])
                    - int(self.result["received_ros_ns"])
                ):
                    self.near_result = copy.deepcopy(sample)
                    self.near_result["offset_from_result_receipt_s"] = (
                        int(sample["stamp_ns"]) - int(self.result["received_ros_ns"])
                    ) / 1e9
            self._observe_stop(sample, odom)

    def finish(self, state, now_ns, now, readback):
        if self.result is not None:
            return
        self.result = {
            "state": state,
            "nav2_success_stamp_ns": None,
            "received_ros_ns": str(now_ns),
            "received_monotonic_s": now,
            "timing": "RESULT_RECEIPT_NOT_NAV2_SUCCESS_TIME",
        }
        self.live_parameters = parameter_observation(readback)
        self.stop_window = None
        if self.latest and self.invalid_reason is None:
            age = (
                self.latest["source_age_at_receive_s"]
                + now
                - self.latest["received_monotonic_s"]
            )
            if 0 <= age <= MAX_AGE_S:
                self.near_result = copy.deepcopy(self.latest)
                self.near_result["offset_from_result_receipt_s"] = (
                    int(self.latest["stamp_ns"]) - now_ns
                ) / 1e9

    def _observe_stop(self, sample, odom):
        # Require new exact-stamp body observations *after* result receipt.
        if (
            self.source_changed
            or not odom
            or self.still_since is None
            or int(sample["stamp_ns"]) < int(self.result["received_ros_ns"])
        ):
            self.stop_window = None
            return
        now = sample["received_monotonic_s"]
        elapsed = min(
            now - max(self.still_since, self.result["received_monotonic_s"]),
            (
                int(sample["stamp_ns"])
                - max(self.still_stamp, int(self.result["received_ros_ns"]))
            )
            / 1e9,
        )
        if elapsed < 2:
            return
        if self.after_stop is None:
            self.after_stop = copy.deepcopy(sample)
            self.after_stop["confirmed_monotonic_s"] = now
        previous = self.stop_window
        if previous is None or previous["last_stamp_ns"] != sample["stamp_ns"]:
            self.stop_window = {
                "observed_stopped_seconds": elapsed,
                "samples": 1
                if previous is None
                else min(100000, previous["samples"] + 1),
                "last_stamp_ns": sample["stamp_ns"],
                "first_observed_monotonic_s": now
                if previous is None
                else previous["first_observed_monotonic_s"],
                "max_xy_error_m": max(
                    sample["error"]["xy_m"],
                    previous["max_xy_error_m"] if previous else 0,
                ),
                "max_abs_yaw_error_rad": max(
                    abs(sample["error"]["yaw_rad"]),
                    previous["max_abs_yaw_error_rad"] if previous else 0,
                ),
            }

    def observe_plan(self, message, now_ns, now):
        if (
            not self.goal_id
            or self.result
            or not self.wire_goal
            or "stamp_ns" not in self.wire_goal
        ):
            return
        try:
            if message.header.frame_id != "map" or not 0 < len(message.poses) <= 20000:
                raise ValueError("INVALID_PLAN")
            # Path carries no action UUID: temporal association is explicitly unverified.
            last = message.poses[-1]
            sample = read_pose(last, "map", now_ns, now)
            if int(sample["stamp_ns"]) < int(self.wire_goal["stamp_ns"]):
                return
            sample["request_error"] = pose_error(sample["pose"], self.goal)
            sample["association"] = "OBSERVED_DURING_GOAL_NO_ACTION_UUID"
            self.plan = sample
        except (ValueError, TypeError, AttributeError, OverflowError):
            self.plan = {"reason": "PLAN_ENDPOINT_UNAVAILABLE"}

    def snapshot(self, now):
        if not self.goal_id:
            return None
        current = copy.deepcopy(self.latest)
        age = (
            None
            if current is None
            else current["source_age_at_receive_s"]
            + now
            - current["received_monotonic_s"]
        )
        fresh = (
            self.invalid_reason is None and age is not None and 0 <= age <= MAX_AGE_S
        )
        if current:
            current.update(age_s=age, fresh=fresh)
        stopped = bool(
            fresh
            and self.stop_window
            and self.odometry
            and 0 <= now - self.odometry[-1]["received_monotonic_s"] <= MAX_AGE_S
            and self.still_since is not None
        )
        error = current["error"] if fresh else None
        precise = (
            None
            if not stopped or error is None
            else bool(
                self.result
                and self.result["state"] == "succeeded"
                and error["xy_m"] <= 0.10
                and abs(error["yaw_rad"]) <= 0.10
            )
        )
        change = None
        a, b = self.near_result, self.after_stop
        if (
            a
            and b
            and a.get("source_generation") == b.get("source_generation")
            and all("map_odom_transform" in s for s in (a, b))
        ):
            oa, ob = (
                np.array(a["odom_body"]["transform"]),
                np.array(b["odom_body"]["transform"]),
            )
            ca, cb = (
                np.array(a["map_odom_transform"]),
                np.array(b["map_odom_transform"]),
            )
            change = {
                "pairing": "EXACT_SOURCE_STAMP_FULL_SE3",
                "body_odom_translation_m": float(np.linalg.norm(ob[:3, 3] - oa[:3, 3])),
                "body_odom_rotation_rad": rotation_error_rad(oa, ob),
                "map_odom_translation_m": float(np.linalg.norm(cb[:3, 3] - ca[:3, 3])),
                "map_odom_rotation_rad": rotation_error_rad(ca, cb),
            }
        return copy.deepcopy(
            {
                "schema": SCHEMA,
                "goal_id": self.goal_id,
                "action_uuid": self.action_uuid,
                "context": self.context,
                "requested": {
                    "frame_id": "map",
                    "body_frame_id": "base_link",
                    "pose": self.goal,
                },
                "transmitted": self.wire_goal,
                "plan_endpoint": self.plan,
                "current": current,
                "unavailable_reason": self.invalid_reason
                if self.invalid_reason
                else None
                if fresh
                else "POSE_STALE",
                "result": self.result,
                "near_result": self.near_result,
                "after_stop": self.after_stop,
                "stop": {
                    "confirmed_now": stopped,
                    "basis": "MEASURED_ODOM_BODY_MOTION_2S",
                    "window": self.stop_window,
                },
                "precision": {"limits": PRECISION_LIMITS, "satisfied_now": precise},
                "motion_vs_correction": change,
                "zero_command_issued": self.zero,
                "effective_at_result": self.live_parameters,
                "source_changed_after_dispatch": self.source_changed,
                "trace_limit_reached": self.logged_samples >= 600,
            }
        )
