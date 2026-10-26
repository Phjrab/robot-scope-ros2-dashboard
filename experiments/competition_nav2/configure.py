"""Generate candidates from fixed repository Humble configuration; no deployment."""

import argparse
import copy
import json
from pathlib import Path
import yaml

from core import FOOTPRINT, LIMITS
from footprint_coverage import OMNI_VARIANTS, coverage
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


def candidate(controller, variant="baseline", fixture=None):
    if variant not in ("baseline", "tuned", "se2_rpp", *OMNI_VARIANTS):
        raise ValueError("unknown candidate revision: " + variant)
    if variant == "se2_rpp" and (
        controller != "rpp" or not fixture or fixture.get("world_kind") != "d0_shared"
    ):
        raise ValueError("se2_rpp is an isolated D0/RPP candidate only")
    if variant in OMNI_VARIANTS and (
        controller != "mppi" or not fixture or fixture.get("world_kind") != "d0_shared"
    ):
        raise ValueError("omni_lattice is an isolated D0/MPPI candidate only")
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
        if variant in OMNI_VARIANTS:
            # Total linear speed <= hypot(.16, .08) < the existing .18 m/s bound.
            follow.update(
                motion_model="Omni",
                vx_max=0.16,
                vy_max=0.08,
                vx_std=0.08,
                vy_std=0.06,
                wz_std=0.1,
                PathAlignCritic=dict(
                    use_path_orientations=True, offset_from_furthest=5
                ),
            )
            # Humble 1.1.20 has no PathAngleCritic.mode. Its heading-to-point
            # preference would turn toward a lateral segment; align native SE2 yaw.
            follow["critics"].remove("PathAngleCritic")
            follow["critics"].append("PathAlignCritic")
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
    if fixture and fixture.get("world_kind") == "d0_shared":
        for name in ("global_costmap", "local_costmap"):
            cm = cfg[name][name]["ros__parameters"]
            cm["footprint"] = json.dumps(fixture["effective_footprint"])
            cm["resolution"] = fixture["resolution_m"]
            cm["obstacle_layer"]["scan"]["expected_update_rate"] = fixture[
                "sensor_ttl_s"
            ]
    if variant == "se2_rpp":
        # Humble 1.1.20 exports this slash-form plugin name. Preserve the RPP,
        # footprint, padding, costmaps, sensor, bounds, goal and recovery settings.
        cfg["planner_server"]["ros__parameters"]["GridBased"] = dict(
            plugin="nav2_smac_planner/SmacPlannerHybrid",
            tolerance=0.0,
            allow_unknown=False,
            downsample_costmap=False,
            angle_quantization_bins=72,
            motion_model_for_search="DUBIN",
            minimum_turning_radius=0.8,
            smooth_path=False,
            max_iterations=500000,
            max_on_approach_iterations=1000,
            max_planning_time=1.0,
            lookup_table_size=5.0,
            analytic_expansion_max_length=3.2,
            cache_obstacle_heuristic=False,
        )
    if variant in OMNI_VARIANTS:
        cfg["planner_server"]["ros__parameters"]["GridBased"] = dict(
            plugin="nav2_smac_planner/SmacPlannerLattice",
            tolerance=0.0,
            allow_unknown=False,
            smooth_path=False,
            lattice_filepath=str(ROOT / "config/omni-2cm-primitives.json"),
            max_iterations=500000,
            max_on_approach_iterations=1000,
            max_planning_time=1.0,
            lookup_table_size=5.0,
            analytic_expansion_max_length=3.2,
            cache_obstacle_heuristic=False,
            allow_reverse_expansion=False,
        )
    if variant == "omni_coverage":
        radius = coverage(fixture["effective_footprint"], fixture["resolution_m"])[
            "inflation_radius_m"
        ]
        for name in ("global_costmap", "local_costmap"):
            cfg[name][name]["ros__parameters"]["inflation_layer"][
                "inflation_radius"
            ] = radius
    return cfg


def validate_config(cfg, controller, footprint=FOOTPRINT):
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
        if json.loads(cm["footprint"]) != [list(p) for p in footprint]:
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
