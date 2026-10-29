"""One two-field comparison candidate and bounded parameter-layer evidence."""

from __future__ import annotations

PRECISION_PATCH = {"xy_goal_tolerance": 0.10, "yaw_goal_tolerance": 0.10}
CONTROLLER_FIELDS = (
    "controller_frequency",
    "controller_plugins",
    "goal_checker_plugins",
    "progress_checker_plugin",
    "odom_topic",
    "goal_checker.plugin",
    "goal_checker.xy_goal_tolerance",
    "goal_checker.yaw_goal_tolerance",
    "goal_checker.stateful",
    "FollowPath.plugin",
    "FollowPath.primary_controller",
    "FollowPath.rotate_to_goal_heading",
    "FollowPath.closed_loop",
    "FollowPath.desired_linear_vel",
    "FollowPath.rotate_to_heading_angular_vel",
    "FollowPath.max_angular_accel",
    "FollowPath.use_rotate_to_heading",
    "FollowPath.lookahead_dist",
    "FollowPath.min_lookahead_dist",
    "FollowPath.lookahead_time",
    "FollowPath.regulated_linear_scaling_min_speed",
    "FollowPath.approach_velocity_scaling_dist",
    "FollowPath.min_approach_linear_velocity",
    "progress_checker.required_movement_radius",
    "progress_checker.movement_time_allowance",
)
PLANNER_FIELDS = (
    "planner_plugins",
    "GridBased.plugin",
    "GridBased.tolerance",
    "GridBased.use_astar",
    "GridBased.allow_unknown",
    "GridBased.use_final_approach_orientation",
)


def precision_preset(values, revision):
    return {
        "id": "go2-precision-10cm",
        "label": "Go2 정밀 도착 · 10cm / 5.7°",
        "description": "미검증 비교 후보 · 현재 저장값에서 XY/yaw 허용오차만 0.10으로 변경. 나머지 설정 유지.",
        "baseline_revision": revision,
        "values": {**values, **PRECISION_PATCH},
    }


def generated_readback(document):
    result = {}
    for node, fields in [
        ("controller_server", CONTROLLER_FIELDS),
        ("planner_server", PLANNER_FIELDS),
    ]:
        parameters = document.get(node, {}).get("ros__parameters", {})
        out = {}
        for key in fields:
            value = parameters
            for part in key.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            out[key] = value
        result["/" + node] = out
    return result
