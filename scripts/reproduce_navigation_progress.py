#!/usr/bin/env python3
"""Robot-free startup-distance diagnostic; exit 1 means the defect reproduced.

Uses the production gateway/health classifier with existing synthetic control
ports. Rounded field distances and synthetic times are NOT a ROS bag replay,
native Nav2 verification, or evidence of physical motion/stopping.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from test_ros_navigation_gateway import NavigationRosGatewayTests as Fixture, gateway  # noqa: E402


def feedback(nav, distance, when, generation=None, goal_id=None):
    message = SimpleNamespace(feedback=SimpleNamespace(
        distance_remaining=distance, navigation_time=None, number_of_recoveries=0))
    with patch("robot_dashboard.ros.navigation_gateway.time.monotonic", return_value=when):
        nav._navigation_feedback_callback(
            nav._navigation_goal_generation if generation is None else generation,
            nav._navigation["goal"]["goal_id"] if goal_id is None else goal_id, message)


def snapshot(nav, when):
    goal = nav._navigation["goal"]
    health = Fixture._goal_health(nav, now=when)
    initial, remaining = goal["initial_distance"], goal["distance_remaining"]
    return {
        "initial_distance_m": initial, "remaining_distance_m": remaining,
        "display_fraction_formula": max(0, min(1, 1 - remaining / initial))
        if initial and remaining is not None else None,
        "progress_rate_mps": nav._navigation_goal_progress["progress_rate_mps"],
        "baseline_state": nav._navigation_goal_progress["baseline_state"],
        "health": health["state"], "reason": health["reason_code"],
    }


def sequence(distances, times):
    nav = gateway()
    Fixture._prepare_active_goal(nav)
    for distance, when in zip(distances, times):
        feedback(nav, distance, when)
    return nav, snapshot(nav, 103.1)


def new_goal(nav, when):
    # Use real send_goal/reset logic; only ROS transport and sensor admission
    # are synthetic. This deliberately cannot establish field readiness.
    nav._navigation["map"] = {"id": "map", "revision": "a" * 64}
    nav._navigation_action_type = SimpleNamespace(
        Goal=lambda: SimpleNamespace(pose=SimpleNamespace(header=None, pose=None)))
    nav._navigation_action_client = SimpleNamespace(
        server_is_ready=lambda: True,
        send_goal_async=lambda *args, **kwargs: SimpleNamespace(add_done_callback=lambda callback: None))
    nav._new_stamped_pose = lambda *args: SimpleNamespace(
        header=SimpleNamespace(), pose=SimpleNamespace(pose=SimpleNamespace()))
    with patch.object(nav, "_navigation_sensor_interlock_reason", return_value=None), patch(
        "robot_dashboard.ros.navigation_gateway.time.monotonic", return_value=when
    ):
        nav.send_goal(map_id="map", map_revision="a" * 64, x=.801, y=0, yaw=0)
        handle = SimpleNamespace(accepted=True, goal_id=SimpleNamespace(uuid=[0] * 16),
            get_result_async=lambda: SimpleNamespace(add_done_callback=lambda callback: None))
        nav._navigation_goal_response_callback(nav._navigation_goal_generation,
            nav._navigation["goal"]["goal_id"], SimpleNamespace(result=lambda: handle))


def main():
    approach = [.838, .681, .581, .531, .515, .490]
    times = [100.1, 100.6, 101.1, 101.6, 102.1, 103.0]
    cases = {}
    poisoned, cases["small_positive_then_approach"] = sequence([.0416856, *approach], [100.0, *times])
    _, cases["normal_approach"] = sequence(approach, times)
    for name, values in {
        "stationary": [.838] * 7,
        "zero_only": [0.0] * 7,
        "bounded_noise": [.838 + (.002 if i % 2 else -.002) for i in range(7)],
        "reverse": [.838 + .02 * i for i in range(7)],
    }.items():
        _, cases[name] = sequence(values, [100.0, *times])

    old_generation = poisoned._navigation_goal_generation
    old_goal = poisoned._navigation["goal"]["goal_id"]
    with patch("robot_dashboard.ros.navigation_gateway.time.monotonic", return_value=104.0):
        poisoned.cancel_goal(goal_id=old_goal)
    before = dict(poisoned._navigation_goal_progress)
    feedback(poisoned, .001, 104.1)
    cases["cancel_ignores_feedback"] = before == poisoned._navigation_goal_progress
    poisoned._navigation_result_callback(old_generation, old_goal,
        SimpleNamespace(result=lambda: SimpleNamespace(status=5)))
    new_goal(poisoned, 105.0)
    cases["new_goal_resets_baseline"] = poisoned._navigation["goal"]["initial_distance"] is None
    before = dict(poisoned._navigation_goal_progress)
    feedback(poisoned, .001, 105.01, old_generation, old_goal)
    cases["old_callback_ignored_after_new_goal"] = before == poisoned._navigation_goal_progress
    feedback(poisoned, .838, 105.1)
    feedback(poisoned, .681, 105.6)
    cases["new_goal_normal_feedback"] = snapshot(poisoned, 105.6)

    restarted = gateway()
    Fixture._prepare_active_goal(restarted, started_at=110.0)
    restarted._navigation["goal"]["state"] = "idle"
    new_goal(restarted, 110.0)
    cases["restart_resets_baseline"] = restarted._navigation["goal"]["initial_distance"] is None
    feedback(restarted, .0416856, 110.0)
    for distance, when in zip(approach, times):
        feedback(restarted, distance, when + 10)
    cases["restart_small_positive_then_approach"] = snapshot(restarted, 113.1)

    controls_ok = (cases["normal_approach"]["health"] == "READY"
        and all(cases[key]["health"] == "DEGRADED" for key in ["stationary", "zero_only", "bounded_noise", "reverse"])
        and all(cases[key] for key in ["cancel_ignores_feedback", "new_goal_resets_baseline",
            "old_callback_ignored_after_new_goal", "restart_resets_baseline"])
        and cases["new_goal_normal_feedback"]["health"] == "READY")
    reproduced = all(cases[key]["display_fraction_formula"] == 0
        and cases[key]["health"] == "DEGRADED"
        for key in ["small_positive_then_approach", "restart_small_positive_then_approach"])
    paths = ["robot_dashboard/ros/navigation_gateway.py", "robot_dashboard/localization_health.py",
             "robot_dashboard/static/app.js", "tests/test_ros_navigation_gateway.py"]
    print(json.dumps({
        "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths},
        "environment": {"python": sys.version.split()[0], "profile": poisoned._navigation_profile},
        "evidence": "production callbacks and classifier; synthetic transport/times; display formula only",
        "controls_ok": controls_ok,
        "result": "REPRODUCED" if reproduced else "NOT_REPRODUCED", "cases": cases,
    }, ensure_ascii=False, indent=2))
    return 2 if not controls_ok else 1 if reproduced else 0


if __name__ == "__main__":
    raise SystemExit(main())
