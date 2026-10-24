"""Generate candidates from fixed repository Humble configuration; no deployment."""

import argparse
import copy
import json
from pathlib import Path
import yaml

from core import FOOTPRINT, LIMITS
from fixtures import ROOT, REPO, digest

PLUGINS = {
    "rpp": "nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController",
    "mppi": "nav2_mppi_controller::MPPIController",
}
NODES = [
    "map_server",
    "controller_server",
    "planner_server",
    "behavior_server",
    "bt_navigator",
]
NAMESPACE = "c3_nav2"


def candidate(controller, variant="baseline"):
    cfg = yaml.safe_load(
        (
            REPO
            / "experiments/competition_vm/avoidance/config/rpp_polygon_vm_candidate.yaml"
        ).read_text()
    )
    cp = cfg["controller_server"]["ros__parameters"]
    cp.update(
        controller_frequency=20.0, odom_topic="odom", min_y_velocity_threshold=0.001
    )
    cp["goal_checker"].update(xy_goal_tolerance=0.12, yaw_goal_tolerance=0.2)
    cp["progress_checker"].update(
        required_movement_radius=0.1, movement_time_allowance=10.0
    )
    if controller == "rpp":
        follow = dict(
            plugin=PLUGINS[controller],
            desired_linear_vel=LIMITS["v"],
            lookahead_dist=0.4,
            use_velocity_scaled_lookahead_dist=False,
            use_collision_detection=True,
            max_allowed_time_to_collision_up_to_carrot=1.0,
            allow_reversing=False,
            use_rotate_to_heading=True,
            rotate_to_heading_angular_vel=LIMITS["w"],
            max_angular_accel=LIMITS["alpha"],
            min_approach_linear_velocity=0.03,
            regulated_linear_scaling_min_speed=0.05,
            transform_tolerance=0.2,
        )
        if variant == "tuned":
            follow["lookahead_dist"] = 0.25
    elif controller == "mppi":
        follow = dict(
            plugin=PLUGINS[controller],
            motion_model="DiffDrive",
            model_dt=0.05,
            time_steps=56,
            batch_size=1000,
            iteration_count=1,
            vx_max=LIMITS["v"],
            vx_min=0.0,
            vy_max=0.0,
            wz_max=LIMITS["w"],
            vx_std=0.1,
            vy_std=0.0,
            wz_std=0.2,
            temperature=0.3,
            gamma=0.015,
            regenerate_noises=False,
            critics=[
                "ConstraintCritic",
                "CostCritic",
                "GoalCritic",
                "GoalAngleCritic",
                "PathFollowCritic",
                "PathAngleCritic",
                "PreferForwardCritic",
            ],
            CostCritic=dict(
                enabled=True, consider_footprint=True, collision_cost=1000000.0
            ),
        )
        if variant == "tuned":
            follow.update(time_steps=40, batch_size=1500)
    else:
        raise ValueError(controller)
    cp["FollowPath"] = follow
    cfg["bt_navigator"]["ros__parameters"]["odom_topic"] = "odom"
    bp = cfg["behavior_server"]["ros__parameters"]
    bp.update(
        behavior_plugins=["spin", "wait"],
        cycle_frequency=20.0,
        global_frame="odom",
        max_rotational_vel=LIMITS["w"],
        min_rotational_vel=0.1,
        rotational_acc_lim=LIMITS["alpha"],
        costmap_topic="local_costmap/costmap_raw",
        footprint_topic="local_costmap/published_footprint",
    )
    bp.pop("backup", None)
    bp.pop("local_frame", None)  # Humble BehaviorServer has only global_frame.
    for name in ("global_costmap", "local_costmap"):
        cm = cfg[name][name]["ros__parameters"]
        cm.update(
            footprint=json.dumps(FOOTPRINT),
            footprint_padding=0.0,
            resolution=0.04,
            track_unknown_space=True,
            plugins=["static_layer", "obstacle_layer", "inflation_layer"],
        )
        cm.pop("robot_radius", None)
        cm["static_layer"] = dict(
            plugin="nav2_costmap_2d::StaticLayer",
            map_subscribe_transient_local=True,
            map_topic="/c3_nav2/map",
        )
        cm["obstacle_layer"]["scan"].update(
            topic="/c3_nav2/scan",
            expected_update_rate=0.3,
            inf_is_valid=False,
            obstacle_max_range=7.9,
            raytrace_max_range=8.0,
        )
    cfg["lifecycle_manager_navigation"]["ros__parameters"].update(
        autostart=False, node_names=NODES
    )
    return cfg


def validate_config(cfg, controller):
    errors = []
    cp = cfg["controller_server"]["ros__parameters"]
    follow = cp["FollowPath"]
    if follow["plugin"] != PLUGINS[controller]:
        errors.append("controller plugin mismatch")
    if (
        controller == "mppi"
        and abs(1 / cp["controller_frequency"] - follow["model_dt"]) > 1e-9
    ):
        errors.append("Humble MPPI model_dt must equal controller period")
    for name in ("global_costmap", "local_costmap"):
        cm = cfg[name][name]["ros__parameters"]
        if json.loads(cm["footprint"]) != [list(p) for p in FOOTPRINT]:
            errors.append("footprint mismatch")
        if not cm["track_unknown_space"] or "static_layer" not in cm["plugins"]:
            errors.append("unknown/static policy violated")
    text = json.dumps(cfg)
    for forbidden in ("/utlidar", "/robot_scope", "/cmd_vel", "ax_max", "az_max"):
        if forbidden in text:
            errors.append("unsupported or production parameter: " + forbidden)
    if cfg["lifecycle_manager_navigation"]["ros__parameters"]["autostart"]:
        errors.append("automatic lifecycle activation forbidden")
    return errors


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=ROOT / "config")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for controller in PLUGINS:
        baseline = candidate(controller)
        for variant in ("baseline", "tuned"):
            cfg = candidate(controller, variant)
            assert not validate_config(cfg, controller)
            name = f"{controller}_{variant}"
            (args.output / f"{name}.yaml").write_text(
                yaml.safe_dump(cfg, sort_keys=False)
            )
            current = cfg["controller_server"]["ros__parameters"]["FollowPath"]
            base = baseline["controller_server"]["ros__parameters"]["FollowPath"]
            manifest[name] = dict(
                config_sha256=digest(cfg),
                tuning_delta={
                    k: {"from": base.get(k), "to": v}
                    for k, v in current.items()
                    if base.get(k) != v
                },
            )
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    # Fairness: all non-controller parameters and final boundary limits are shared.
    a, b = [copy.deepcopy(candidate(c)) for c in PLUGINS]
    for cfg in (a, b):
        cfg["controller_server"]["ros__parameters"].pop("FollowPath")
    assert a == b


if __name__ == "__main__":
    main()
