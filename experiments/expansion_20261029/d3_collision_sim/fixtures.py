"""Deterministic synthetic inputs. Ground truth is never a detector/planner input."""

import copy
import math

import numpy as np

from robot_dashboard.collision_geometry_core import RobotGeometry, transform


def metadata(stamp=1_000_000_000):
    return dict(
        schema_version="0.1",
        producer="d3.fixture",
        sequence=1,
        source_epoch="synthetic-1",
        frame_key=dict(source_epoch="synthetic-1", frame_id="odom"),
        stamp_ns=str(stamp),
        clock_domain="fixture-clock",
        host_clock_id="fixture-host",
        received_monotonic_ns=stamp,
        evidence_kind="SYNTHETIC",
        map_binding=dict(map_id="a" * 24, revision="b" * 64, generation=0),
    )


def model(gait_margin=0.0):
    # Historical standing envelope retained, not reduced to get a success.
    return RobotGeometry(
        '<robot name="synthetic"><link name="base"><collision>'
        '<geometry><box size="0.716 0.324 0.35"/></geometry>'
        "</collision></link></robot>",
        provenance="SYNTHETIC_standing_envelope_not_measured_gait",
        gait_margin=gait_margin,
    )


def state():
    return dict(
        metadata(),
        pose=transform((0, 0, 0.3)).tolist(),
        joints={},
        joint_stamp_ns="1000000000",
        calibration_known=True,
        pose_uncertainty_m=0.01,
        joint_uncertainty_m=0.0,
    )


def obstacle(center=(1.0, 0, 0.3), extent=(0.26, 0.26, 0.6), track="cone-1"):
    return dict(
        track_id=track,
        geometry=dict(
            center=list(center),
            extent=list(extent),
            orientation_xyzw=[0.0, 0.0, 0.0, 1.0],
        ),
        uncertainty=dict(bound_m=0.0),
        state="OBSERVED",
        novelty="NEW_TO_REFERENCE",
        provenance={"kind": "SYNTHETIC"},
        sensor_support=["LIDAR"],
    )


def frame(objects=()):
    return dict(
        metadata(),
        obstacles=copy.deepcopy(list(objects)),
        health={},
        dropped_counts={},
        input_sources=[],
        calibration_id="synthetic",
        observation_only=True,
        published_to_nav2=False,
        costmap_ingestion_observed=False,
        controller_consumption_observed=False,
    )


def scenarios():
    """Native requirements manifest; NONE is a native execution result."""
    return [
        dict(
            name=name,
            evidence_kind="SYNTHETIC",
            native_status="NOT_RUN",
            required_evidence=[
                "raw_observation",
                "costmap_ingestion",
                "plan_change",
                "controller_command",
                "command_driven_plant",
                "independent_contact",
            ],
            events=events,
        )
        for name, events in (
            ("empty_lane", []),
            (
                "one_cone_feasible",
                [{"time_s": 0, "action": "add", "center": [2, 0.4, 0.3]}],
            ),
            (
                "cone_added_during_motion",
                [{"time_s": 2, "action": "add", "center": [2, 0, 0.3]}],
            ),
            (
                "cone_move_remove",
                [
                    {"time_s": 0, "action": "add"},
                    {"time_s": 2, "action": "move"},
                    {"time_s": 4, "action": "remove"},
                ],
            ),
            ("fully_blocked", [{"time_s": 0, "action": "wall_across_lane"}]),
            (
                "input_interruption",
                [{"time_s": 2, "action": "stop_sensor_publication"}],
            ),
        )
    ]


def sensor_points(truth, *, seed=17, rays=180, fov=math.pi, maximum=5.0, noise=0.002):
    """2D range rays against truth cylinders; nearest return occludes farther one.

    Produces raw XYZ samples only, no truth IDs or bounds. Deliberately sparse;
    a missing ray is not a free-space declaration. Oracle retained separately.
    """
    rng = np.random.default_rng(seed)
    points = []
    for angle in np.linspace(-fov / 2, fov / 2, rays):
        direction = np.array([math.cos(angle), math.sin(angle)])
        best = maximum
        for x, y, radius in truth:
            center = np.array([x, y])
            dot = float(center @ direction)
            disc = dot * dot - float(center @ center) + radius * radius
            if disc >= 0:
                distance = dot - math.sqrt(disc)
                if 0 < distance < best:
                    best = distance
        if best < maximum:
            p = direction * (best + rng.normal(0, noise))
            for z in (0.12, 0.16, 0.20, 0.24):
                points.append([float(p[0]), float(p[1]), z])
    return np.asarray(points, dtype=float).reshape((-1, 3))


def oracle_circle_box(center, radius, pose_xy_yaw, half=(0.358, 0.162)):
    """Independent closed-form 2D scene oracle; no production collision calls."""
    x, y, yaw = pose_xy_yaw
    dx, dy = center[0] - x, center[1] - y
    u = abs(math.cos(yaw) * dx + math.sin(yaw) * dy) - half[0]
    v = abs(-math.sin(yaw) * dx + math.cos(yaw) * dy) - half[1]
    return math.hypot(max(u, 0), max(v, 0)) + min(max(u, v), 0) - radius


def coverage_evidence(s=None, horizon_s=5.0):
    s = state() if s is None else s
    return dict(
        kind="GENERATED_CLOSED_SCENE_VOLUME",
        complete_for_motion=True,
        evidence_kind="SYNTHETIC",
        source_refs=[{"generator": "d3.fixtures.closed_scene.v1"}],
        **{
            k: copy.deepcopy(s[k])
            for k in ("source_epoch", "clock_domain", "frame_key", "map_binding")
        },
        horizon_s=horizon_s,
        volume_min=[-10, -10, -10],
        volume_max=[10, 10, 10],
        valid_from_ns=s["stamp_ns"],
        valid_until_ns=str(int(s["stamp_ns"]) + int(horizon_s * 1e9)),
    )
