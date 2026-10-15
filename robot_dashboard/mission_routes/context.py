"""Read-only projection of the existing operational navigation owner."""
from __future__ import annotations

import math

from .models import Pose, digest


class NavigationContext:
    def __init__(self, navigation, *, slam=None, policy_provider=None, runtime_provider=None):
        self.navigation, self.slam = navigation, slam
        self.policy_provider = policy_provider or (lambda: {})
        self.runtime_provider = runtime_provider or (lambda: {})

    def snapshot(self):
        nav = self.navigation.view()
        nav_map = nav.get("map") or {}
        localization = nav.get("localization") or {}
        pipeline = nav.get("pipeline") or {}
        shared = nav.get("localization_pipeline") or {}
        bindings = nav.get("bindings") or {}
        policy = self.policy_provider()
        # Job identities remain useful pins, but a runtime can restart inside
        # the same jobs. Pin its operational process generation independently.
        generation = [pipeline.get("job_id"), shared.get("job_id")]
        semantic = {"map": {k: nav_map.get(k) for k in ("id", "revision")}, "generation": generation, "bindings": bindings, "policy": policy}
        ms = self.slam.navigation_context() if self.slam is not None else None
        if ms is not None:
            semantic["multi_slam"] = {"navigation_map": ms.get("navigation_map"), "alignment": ms.get("alignment"), "source": (ms.get("operational_pose") or {}).get("source"), "generation": (ms.get("operational_pose") or {}).get("generation")}
        raw = self.runtime_provider()
        source = (ms.get("operational_pose") or {}).get("source") if ms else (raw.get("bindings") or {}).get("localization_pose", bindings.get("localization_pose"))
        source_generation = (ms.get("operational_pose") or {}).get("generation") if ms is not None else (raw.get("runtime_health") or {}).get("process_generation")
        known_generation = (
            isinstance(source_generation, int) and not isinstance(source_generation, bool) and source_generation > 0
            or ms is not None and isinstance(source_generation, str) and bool(source_generation.strip()) and len(source_generation) <= 128
        )
        if not known_generation:
            source_generation = None
        semantic["operational_generation"] = source_generation
        pose = None
        if pipeline.get("state") == "running" and localization.get("state") == "localized" and (nav.get("readiness") or {}).get("localization") is True:
            try:
                pose = Pose.model_validate(localization.get("pose")).model_dump()
            except (ValueError, TypeError):
                pass
        reasons = []
        if not nav_map.get("id") or not nav_map.get("revision"):
            reasons.append("NAVIGATION_MAP_REQUIRED")
        if pipeline.get("state") != "running" or pose is None:
            reasons.append("FRESH_OPERATIONAL_POSE_REQUIRED")
        if (nav.get("safety") or {}).get("can_send_goal") is not True:
            reasons.append("GOAL_ADMISSION_UNAVAILABLE")
        if not source:
            reasons.append("OPERATIONAL_POSE_SOURCE_UNAVAILABLE")
        radius = policy.get("robot_radius_m")
        if not isinstance(radius, (int, float)) or isinstance(radius, bool) or not math.isfinite(radius) or radius <= 0:
            reasons.append("EFFECTIVE_FOOTPRINT_UNAVAILABLE")
        if not any(generation) or not known_generation:
            reasons.append("SOURCE_GENERATION_UNAVAILABLE")
        if self.slam is not None and self.slam.blocks_context_change():
            reasons.append("SLAM_CONTEXT_BUSY")
        if policy.get("runtime_policy_enforced") is not True:
            reasons.append("RUNTIME_POLICY_NOT_ENFORCED")
        if not policy.get("planner_config_digest") or not policy.get("footprint_revision"):
            reasons.append("EFFECTIVE_PLANNER_CONFIG_UNAVAILABLE")
        semantic["operational_source"] = source
        return {
            "navigation_map": semantic["map"], "frame": "map", "units": "m",
            "pose_source": {"source": source, "odometry_source": (ms.get("operational_pose") or {}).get("odometry_source") if ms else bindings.get("localization_odometry"), "generation": source_generation, "job_generation": generation, "readiness": localization.get("state")},
            "navigation_context_revision": digest(semantic), "snapshot_seq": nav.get("seq"),
            "operational_pose": pose, "blocking_reasons": reasons,
            "planner_config_digest": policy.get("planner_config_digest"),
            "footprint_revision": policy.get("footprint_revision"),
            "robot_radius_m": policy.get("robot_radius_m"),
            "runtime_policy_enforced": policy.get("runtime_policy_enforced") is True,
            "capabilities": {"arrival": ["NAV2_DEFAULT"], "speed": ["DEFAULT"], "visits": ["STOP", "TASK"], "actions": ["hold", "before_departure_confirmation", "after_arrival_confirmation"], "motion_constraints": ["FLEXIBLE"]},
        }
