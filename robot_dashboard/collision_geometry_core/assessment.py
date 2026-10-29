"""Pure collision assessment, not a safety controller or C1 wire validator."""

import math

import numpy as np

from .geometry import Primitive, clearance, plane_clearance, rigid, vector


META = (
    "frame_key",
    "stamp_ns",
    "clock_domain",
    "host_clock_id",
    "received_monotonic_ns",
    "map_binding",
    "source_epoch",
    "sequence",
    "evidence_kind",
)


def obstacle_primitives(frame, *, uncertainty_in_extent):
    """D2 bridge: caller declares pinned extent uncertainty convention explicitly.

    D2 c0d266e inflates extent by 2*sigma already. Never add that sigma twice.
    Sparse observations are occupied bounds, NOT observed-free coverage.
    """
    from scipy.spatial.transform import Rotation

    out = []
    for obj in frame["obstacles"]:
        if obj["state"] == "REJECTED":
            raise ValueError("rejected obstacle cannot prove free")
        g = obj["geometry"]
        dims = vector(g["extent"])
        uncertainty = obj.get("uncertainty")
        if uncertainty is None:
            raise ValueError("unknown obstacle uncertainty")
        bound = float(uncertainty["bound_m"])
        if not math.isfinite(bound) or bound < 0:
            raise ValueError("invalid obstacle uncertainty")
        if not uncertainty_in_extent:
            dims = dims + 2 * bound
        q = vector(g["orientation_xyzw"], 4)
        if abs(np.linalg.norm(q) - 1) > 1e-8:
            raise ValueError("unit xyzw quaternion required")
        t = np.eye(4)
        t[:3, :3] = Rotation.from_quat(q).as_matrix()
        t[:3, 3] = vector(g["center"])
        out.append(Primitive(obj["track_id"], "box", t, tuple(dims)))
    return out


def sweep_samples(path, radius, *, resolution=0.005, max_samples=4096):
    """Linear translation + shortest SO3 arc, <= resolution point travel/step.

    Joints are held at current values. No gait forecast is invented. The return
    bound can be subtracted from sampled clearance for conservative continuous
    clearance for this interpolation ONLY. Paths with full turns need waypoints.
    """
    from scipy.spatial.transform import Rotation, Slerp

    if not 0 < resolution <= 0.05 or not math.isfinite(radius) or radius < 0:
        raise ValueError("invalid sweep budget")
    if not path or len(path) > 128:
        raise ValueError("bounded nonempty path required")
    poses = [rigid(p["pose"]) for p in path]
    times = [float(p["time_s"]) for p in path]
    if times[0] != 0 or not all(math.isfinite(t) for t in times):
        raise ValueError("path starts at zero finite time")
    samples = [(times[0], poses[0])]
    bound = 0.0
    for i in range(len(path) - 1):
        if times[i + 1] <= times[i]:
            raise ValueError("strictly increasing path time required")
        rotations = Rotation.from_matrix(
            np.stack([poses[i][:3, :3], poses[i + 1][:3, :3]])
        )
        angle = float((rotations[0].inv() * rotations[1]).magnitude())
        travel = np.linalg.norm(poses[i + 1][:3, 3] - poses[i][:3, 3]) + radius * angle
        n = max(1, math.ceil(travel / resolution))
        if len(samples) + n > max_samples:
            raise ValueError("sweep sample budget exceeded")
        bound = max(bound, float(travel / n))
        slerp = Slerp([0, 1], rotations)
        for k in range(1, n + 1):
            u = k / n
            t = np.eye(4)
            t[:3, :3] = slerp(u).as_matrix()
            t[:3, 3] = (1 - u) * poses[i][:3, 3] + u * poses[i + 1][:3, 3]
            samples.append((times[i] + u * (times[i + 1] - times[i]), t))
    return samples, bound


def command_prediction(root_pose, command):
    """Constant body twist hypothesis, not a controller/plant or braking model."""
    from .geometry import transform

    root = rigid(root_pose)
    v, w, horizon = (
        float(command[k]) for k in ("linear_x_mps", "angular_z_radps", "horizon_s")
    )
    if (
        not all(math.isfinite(x) for x in (v, w, horizon))
        or not 0 < horizon <= 5
        or abs(v) > 5
        or abs(w) > 5
    ):
        raise ValueError("bounded finite command hypothesis required")
    # Short arc waypoints avoid shortest-arc aliasing for rotations > pi.
    count = max(1, math.ceil(abs(w) * horizon / 0.25), math.ceil(horizon / 0.1))
    result = []
    for i in range(count + 1):
        t = horizon * i / count
        angle = w * t
        x = v * t if abs(w) < 1e-10 else v * math.sin(angle) / w
        y = 0.0 if abs(w) < 1e-10 else v * (1 - math.cos(angle)) / w
        result.append({"time_s": t, "pose": root @ transform((x, y, 0), (0, 0, angle))})
    return result


def _reference(message):
    ref = {k: message.get(k) for k in META}
    if ref.get("received_monotonic_ns") is not None:
        ref["received_monotonic_ns"] = str(ref["received_monotonic_ns"])
    return ref


def assess(
    robot_geometry,
    stamped_robot_state,
    obstacles,
    path_or_command=None,
    *,
    now_stamp_ns,
    now_clock_domain,
    padding=0.03,
    max_age_s=0.25,
    uncertainty_in_extent=True,
    coverage="SPARSE",
    support_surfaces=(),
    resolution=0.005,
):
    """Return C1 v0.2-shaped numeric result; host interval requires C1 binding. Numeric validity is fail-closed.

    State: metadata + pose (4x4), joints dict, joint_stamp_ns,
    calibration_known bool, pose_uncertainty_m, joint_uncertainty_m.
    Path: {ref: dict, poses: [{time_s, pose}]}; this is NOT a controller.
    Coverage must be an explicit bounded generated-scene certificate; a label is insufficient.
    """
    state = stamped_robot_state
    out = {k: state.get(k) for k in META}
    out.update(
        schema_version="0.2",
        producer="d3.collision_geometry_core",
        robot_pose_ref=_reference(state),
        joint_state_ref={"stamp_ns": state.get("joint_stamp_ns")},
        robot_geometry_hash=robot_geometry.geometry_hash,
        obstacle_frame_ref=_reference(obstacles),
        path_ref=path_or_command.get("ref") if path_or_command else None,
        padded_envelope=None,
        unpadded_envelope=None,
        min_clearance=None,
        predicted_overlap=None,
        modeled_ttc=None,
        freshness={},
        validity_interval={},
        reason="UNKNOWN",
        severity="UNKNOWN",
        recommendation="HOLD_FOR_VALID_INPUT",
    )
    out["received_monotonic_ns"] = str(out["received_monotonic_ns"])
    issues = []
    try:
        if (
            state["evidence_kind"] not in ("SYNTHETIC", "REPLAY")
            or obstacles["evidence_kind"] != state["evidence_kind"]
        ):
            raise ValueError("offline evidence only; mixed evidence forbidden")
        for k in ("frame_key", "map_binding", "source_epoch", "clock_domain"):
            if state[k] != obstacles[k]:
                issues.append("MISMATCH_" + k)
        if now_clock_domain != state["clock_domain"] or now_clock_domain in (
            "UNKNOWN",
            "unknown",
            "",
        ):
            issues.append("CLOCK_MAPPING_UNKNOWN")
        if not state.get("calibration_known"):
            issues.append("CALIBRATION_UNKNOWN")
        ages = [
            (int(now_stamp_ns) - int(x)) / 1e9
            for x in (
                state["stamp_ns"],
                state.get("joint_stamp_ns"),
                obstacles["stamp_ns"],
            )
        ]
        out["freshness"] = dict(
            zip(("pose_age_s", "joint_age_s", "obstacle_age_s"), ages)
        )
        if (
            not math.isfinite(max_age_s)
            or max_age_s <= 0
            or any(a < 0 or a > max_age_s for a in ages)
        ):
            issues.append("STALE_OR_FUTURE_INPUT")
        if abs(int(state["stamp_ns"]) - int(obstacles["stamp_ns"])) / 1e9 > 0.05:
            issues.append("UNCOMPENSATED_TIME_SKEW")
        if abs(int(state["stamp_ns"]) - int(state["joint_stamp_ns"])) / 1e9 > 0.05:
            issues.append("UNCOMPENSATED_JOINT_TIME_SKEW")
        if any(o["state"] != "OBSERVED" for o in obstacles["obstacles"]):
            issues.append("OBSTACLE_NOT_FRESHLY_OBSERVED")
        margins = [
            float(padding),
            float(state["pose_uncertainty_m"]),
            float(state["joint_uncertainty_m"]),
        ]
        if any(not math.isfinite(x) or x < 0 for x in margins):
            raise ValueError("known nonnegative uncertainty/padding required")
        if issues:
            out["freshness"]["issues"] = issues
            return out
        primitives = robot_geometry.fk(state["pose"], state["joints"])
        if not primitives:
            raise ValueError("empty robot geometry")
        root = rigid(state["pose"])
        radius = max(
            np.linalg.norm(p.pose[:3, 3] - root[:3, 3]) + p.radius for p in primitives
        )
        path = (
            (
                command_prediction(root, path_or_command["command"])
                if "command" in path_or_command
                else path_or_command["poses"]
            )
            if path_or_command
            else [{"time_s": 0.0, "pose": root}]
        )
        if not path:
            raise ValueError("nonempty path required")
        if not np.allclose(rigid(path[0]["pose"]), root, rtol=0, atol=1e-8):
            raise ValueError("path start differs from stamped root pose")
        samples, bound = sweep_samples(path, float(radius), resolution=resolution)
        command_arc_bound = 0.0
        if path_or_command and "command" in path_or_command:
            c = path_or_command["command"]
            v, w = abs(float(c["linear_x_mps"])), abs(float(c["angular_z_radps"]))
            dt = float(c["horizon_s"]) / (len(path) - 1)
            command_arc_bound = v * w * dt * dt / 8
            bound += command_arc_bound
        obs = obstacle_primitives(
            obstacles, uncertainty_in_extent=uncertainty_in_extent
        )
        if (
            len(obs) > 512
            or len(samples) * len(primitives) * max(1, len(obs)) > 1_000_000
        ):
            raise ValueError("pair evaluation budget exceeded")
        for surface in support_surfaces:
            lo, hi = vector(surface["patch_min"]), vector(surface["patch_max"])
            tolerances = [
                float(surface["penetration_tolerance_m"]),
                float(surface["contact_tolerance_m"]),
            ]
            if np.any(lo > hi) or any(
                not math.isfinite(t) or not 0 <= t <= 0.01 for t in tolerances
            ):
                raise ValueError("bounded support patch/tolerances required (max 1 cm)")
        if (
            not math.isfinite(robot_geometry.gait_margin)
            or robot_geometry.gait_margin < 0
        ):
            raise ValueError("invalid gait margin")
        margin = sum(margins) + robot_geometry.gait_margin
        minimum = math.inf
        first = None
        current = math.inf
        supports = []
        volume_min, volume_max = np.full(3, math.inf), np.full(3, -math.inf)
        for time_s, pose in samples:
            for p in robot_geometry.fk(pose, state["joints"]):
                extent = p.radius + margin + bound
                volume_min = np.minimum(volume_min, p.pose[:3, 3] - extent)
                volume_max = np.maximum(volume_max, p.pose[:3, 3] + extent)
                distances = [clearance(p, o) for o in obs]
                for surface in support_surfaces:
                    d = plane_clearance(p, surface["normal"], surface["offset"])
                    # Explicit finite patch and named support link association.
                    center = p.pose[:3, 3]
                    lo, hi = vector(surface["patch_min"]), vector(surface["patch_max"])
                    eligible = (
                        p.support_eligible
                        and p.name in surface["allowed_feet"]
                        and np.all(center - p.radius >= lo)
                        and np.all(center + p.radius <= hi)
                        and -surface["penetration_tolerance_m"]
                        <= d
                        <= surface["contact_tolerance_m"]
                    )
                    if eligible:
                        supports.append((p.name, surface["id"]))
                    else:
                        distances.append(d)
                distance = min(distances, default=math.inf)
                minimum = min(minimum, distance)
                if time_s == 0:
                    current = min(current, distance)
                if first is None and distance - margin - bound <= 0:
                    first = time_s
        raw = minimum if math.isfinite(minimum) else None
        padded = None if raw is None else raw - margin
        out["unpadded_envelope"] = dict(
            min_clearance=raw,
            overlap=raw is not None and raw <= 0,
            distance_kind="conservative_signed_lower_bound_m",
            geometry_source_hash=robot_geometry.source_hash,
            provenance=robot_geometry.provenance,
        )
        out["padded_envelope"] = dict(
            min_clearance=padded,
            overlap=padded is not None and padded <= 0,
            padding_m=padding,
            pose_uncertainty_m=margins[1],
            joint_uncertainty_m=margins[2],
            gait_margin_m=robot_geometry.gait_margin,
            future_joints="HELD_CURRENT_NOT_GAIT_PREDICTION",
            future_obstacles="HELD_CURRENT_NOT_MOTION_PREDICTION",
            sweep_displacement_bound_m=bound,
            command_arc_approximation_bound_m=command_arc_bound,
            samples=len(samples),
            continuous_clearance_lower_bound=None if padded is None else padded - bound,
            support_pairs=[list(x) for x in sorted(set(supports))],
            unmodeled=list(robot_geometry.unmodeled),
            mesh_backend="NOT_RUN",
        )
        out["min_clearance"] = padded
        out["predicted_overlap"] = first is not None
        out["modeled_ttc"] = (
            first  # first conservative sampled risk, NOT exact physical contact time
        )
        out["freshness"]["source_validity_interval"] = {
            "clock_domain": now_clock_domain,
            "from_ns": str(
                max(
                    int(state["stamp_ns"]),
                    int(state["joint_stamp_ns"]),
                    int(obstacles["stamp_ns"]),
                )
            ),
            "until_ns": str(
                min(
                    int(state["stamp_ns"]),
                    int(state["joint_stamp_ns"]),
                    int(obstacles["stamp_ns"]),
                )
                + int(max_age_s * 1e9)
            ),
        }
        from .coverage import qualifies

        qualified = qualifies(
            coverage,
            state,
            volume_min=volume_min,
            volume_max=volume_max,
            horizon_s=float(path[-1]["time_s"]),
        )
        out["freshness"]["coverage"] = dict(
            complete_for_motion=qualified,
            horizon_s=float(path[-1]["time_s"]),
            swept_volume_min=volume_min.tolist(),
            swept_volume_max=volume_max.tolist(),
            evidence=coverage if isinstance(coverage, dict) else None,
            status="QUALIFIED_SYNTHETIC"
            if qualified
            else "MOTION_COVERAGE_NOT_QUALIFIED",
        )
        if current <= 0:
            out.update(
                reason="MODEL_OVERLAP",
                severity="STOP_REQUIRED",
                recommendation="SIMULATED_COMMAND_STOP_CONTACT_UNCONFIRMED",
            )
        elif first is not None:
            out.update(
                reason="PREDICTED_COLLISION",
                severity="STOP_REQUIRED",
                recommendation="SIMULATED_COMMAND_STOP_CONTACT_UNCONFIRMED",
            )
        elif not qualified:
            out["freshness"]["issues"] = ["MOTION_COVERAGE_NOT_QUALIFIED"]
        elif robot_geometry.unmodeled:
            out.update(
                reason="UNKNOWN",
                severity="CAUTION",
                recommendation="QUALIFY_UNMODELED_GEOMETRY",
            )
        else:
            out.update(
                reason="CLEAR",
                severity="CLEAR",
                recommendation="MODEL_ONLY_NOT_SAFETY_CERTIFIED",
            )
        return out
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
        out["freshness"]["issues"] = ["INVALID_INPUT: " + str(exc)]
        return out
