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
from test_goal_precision import message as pose_message  # noqa: E402


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


def sequence(distances, times, *, snapshot_at=103.1):
    nav = gateway()
    Fixture._prepare_active_goal(nav)
    for distance, when in zip(distances, times):
        feedback(nav, distance, when)
    return nav, snapshot(nav, snapshot_at)


def new_goal(nav, when):
    # Use real send_goal/reset logic; only ROS transport and sensor admission
    # are synthetic. This deliberately cannot establish field readiness.
    nav._navigation["map"] = {"id": "map", "revision": "a" * 64}
    nav._navigation_action_type = SimpleNamespace(
        Goal=lambda: SimpleNamespace(pose=SimpleNamespace(header=None, pose=None)))
    nav._navigation_action_client = SimpleNamespace(
        server_is_ready=lambda: True,
        send_goal_async=lambda *args, **kwargs: SimpleNamespace(add_done_callback=lambda callback: None))
    nav._new_stamped_pose = lambda *args: pose_message(when, x=.801)
    with patch.object(nav, "_navigation_sensor_interlock_reason", return_value=None), patch(
        "robot_dashboard.ros.navigation_gateway.time.monotonic", return_value=when
    ), patch.object(nav, "_goal_precision_clock", return_value=round(when * 1e9)):
        nav.send_goal(map_id="map", map_revision="a" * 64, x=.801, y=0, yaw=0)
        handle = SimpleNamespace(accepted=True, goal_id=SimpleNamespace(uuid=[0] * 16),
            get_result_async=lambda: SimpleNamespace(add_done_callback=lambda callback: None))
        nav._navigation_goal_response_callback(nav._navigation_goal_generation,
            nav._navigation["goal"]["goal_id"], SimpleNamespace(result=lambda: handle))


def matching_plan_sequence(distances, times):
    """Even a fresh matching endpoint is only an observation, not consumption."""
    nav = gateway()
    Fixture._prepare_active_goal(nav)
    nav._navigation["goal"]["state"] = "idle"
    new_goal(nav, 99.9)
    endpoint = pose_message(100.0, x=.801)
    plan = SimpleNamespace(header=endpoint.header, poses=[endpoint])
    with patch("robot_dashboard.ros.navigation_gateway.time.monotonic", return_value=100.0), patch.object(
        nav, "_goal_precision_clock", return_value=100_000_000_000
    ):
        nav._goal_precision_plan_callback(plan)
    for distance, when in zip(distances, times):
        feedback(nav, distance, when)
    result = snapshot(nav, 103.1)
    observed = nav._goal_precision.plan or {}
    result["plan_association"] = observed.get("association")
    result["plan_endpoint_error_m"] = (observed.get("request_error") or {}).get("xy_m")
    result["feedback_plan_binding"] = "UNAVAILABLE"
    return result


def diagnostic_verdict(cases, controls_ok):
    """A partial reproduction must not become exit 0; broken controls are unknown."""
    names = ["small_positive_then_approach", "restart_small_positive_then_approach",
             "accepted_goal_with_matching_plan"]
    reproduced = [name for name in names if cases[name]["display_fraction_formula"] == 0
                  and cases[name]["health"] == "DEGRADED"
                  and cases[name]["reason"] == "GOAL_PROGRESS_TOO_LOW"]
    if not controls_ok:
        return "INCONCLUSIVE", 2, reproduced
    if reproduced:
        return ("REPRODUCED" if len(reproduced) == len(names) else "PARTIALLY_REPRODUCED"), 1, reproduced
    return "NOT_REPRODUCED", 0, reproduced


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
        "large_oscillation": [.838 + (.060 if i % 2 else 0) for i in range(7)],
    }.items():
        _, cases[name] = sequence(values, [100.0, *times])
    _, cases["legitimate_small_goal"] = sequence(
        [.0416856, .030, .015, .008], [100.0, 100.2, 100.4, 100.6], snapshot_at=100.7)
    cases["accepted_goal_with_matching_plan"] = matching_plan_sequence(
        [.0416856, *approach], [100.0, *times])

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
        and all(cases[key]["health"] == "DEGRADED" for key in ["stationary", "zero_only", "bounded_noise", "reverse", "large_oscillation"])
        and all(cases[key] for key in ["cancel_ignores_feedback", "new_goal_resets_baseline",
            "old_callback_ignored_after_new_goal", "restart_resets_baseline"])
        and cases["new_goal_normal_feedback"]["health"] == "READY"
        and cases["legitimate_small_goal"]["health"] == "READY"
        and cases["legitimate_small_goal"]["initial_distance_m"] == .042
        and cases["accepted_goal_with_matching_plan"]["plan_association"] == "OBSERVED_DURING_GOAL_NO_ACTION_UUID"
        and cases["accepted_goal_with_matching_plan"]["plan_endpoint_error_m"] == 0)
    verdict, exit_code, reproduced = diagnostic_verdict(cases, controls_ok)
    paths = ["robot_dashboard/ros/navigation_gateway.py", "robot_dashboard/localization_health.py",
             "robot_dashboard/static/app.js", "tests/test_ros_navigation_gateway.py",
             "robot_dashboard/goal_precision.py", "scripts/reproduce_navigation_progress.py",
             "tests/test_goal_precision.py"]
    print(json.dumps({
        "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths},
        "environment": {"python": sys.version.split()[0], "profile": poisoned._navigation_profile},
        "evidence": "production callbacks and classifier; synthetic transport/times; display formula only",
        "controls_ok": controls_ok,
        "result": verdict, "reproduced_cases": reproduced, "cases": cases,
    }, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
