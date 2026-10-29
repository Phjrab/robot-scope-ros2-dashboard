"""Factories for exact published owner APIs; no local collision/fusion algorithm."""
from copy import deepcopy
from dataclasses import asdict

from .binding import D3_PROFILE, browser_safe


class CorePorts:
    def __init__(self, d2, d3, contracts, geometry, *, limits=None):
        self.d2, self.d3, self.contracts, self.geometry = d2, d3, contracts, geometry
        self.limits = limits or d2.Limits()
        self.reset()

    @classmethod
    def from_installed(cls, geometry, **kwargs):
        # These imports resolve only after the host explicitly supplies dependencies.
        from robot_dashboard import obstacle_fusion_core, collision_geometry_core, expansion_contracts
        return cls(obstacle_fusion_core, collision_geometry_core, expansion_contracts, geometry, **kwargs)

    def reset(self):
        self.tracker = self.d2.Tracker(self.limits)

    def perceive(self, packet, meta, rays):
        lidar = self.d2.process_lidar(packet.lidar_points, meta, ground=packet.ground,
            self_boxes=packet.self_boxes, reference=packet.reference, limits=self.limits)
        depth_diagnostics = []
        if packet.depth is not None:
            # RGBD cannot suppress valid LiDAR when camera metadata/depth is invalid.
            try:
                depth = self.d2.lift_detections(packet.detections, packet.depth, meta,
                    calibration=packet.calibration, model_manifest=packet.model_manifest, limits=self.limits)
                lidar = self.d2.associate(lidar, depth, limits=self.limits)
                depth_diagnostics = depth.get("image_only", [])
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                depth_diagnostics = [{"reason": "RGBD_REJECTED", "detail": str(exc)}]
        result = self.tracker.step(lidar, clearing_rays=rays)
        result["obstacle_frame"]["health"]["c4_rgbd_diagnostics"] = depth_diagnostics
        self.contracts.ObstacleFrame.from_dict(result["obstacle_frame"])
        return result

    def assess(self, state, frame, motion, *, now_stamp_ns, clock_domain, complete):
        return self.d3.assess(self.geometry, state, frame, motion,
            now_stamp_ns=now_stamp_ns, now_clock_domain=clock_domain,
            uncertainty_in_extent=True, coverage="COMPLETE_SYNTHETIC" if complete else "SPARSE")

    def canonical_assessment(self, assessment, *, context, mapping, motion, timing):
        result = deepcopy(assessment)
        if result["schema_version"] != "0.1" or result["producer"] != "d3.collision_geometry_core":
            raise ValueError("UNSUPPORTED_D3_ASSESSMENT")
        if result["robot_geometry_hash"] != context.robot_geometry_hash or result["path_ref"] != motion["ref"]:
            raise ValueError("D3_GEOMETRY_OR_MOTION_MISMATCH")
        original = deepcopy(result["validity_interval"])
        # Invalid D3 inputs may have no validity at all. Preserve UNKNOWN, no TTL.
        result["validity_interval"] = mapping.interval(original, profile=D3_PROFILE, context=context) if original else {}
        reference = deepcopy(result["obstacle_frame_ref"])
        result["obstacle_frame_ref"] = {k: reference[k] for k in ("source_epoch", "sequence")}
        mapping_evidence = asdict(mapping)
        for name in ("source_start_ns", "source_end_ns", "offset_ns"):
            mapping_evidence[name] = str(mapping_evidence[name])
        result["freshness"]["c4"] = dict(
            source_profile=D3_PROFILE, original_validity_interval=original,
            original_obstacle_frame_ref=reference, clock_mapping=mapping_evidence,
            timing=deepcopy(timing), browser_integer_policy="REJECT_UNSAFE_C1_V01_INTEGER",
        )
        # Authority is supplied by this trusted runtime, never fabricated by D3.
        result["freshness"]["c4_binding"] = asdict(context)
        return browser_safe(self.contracts.CollisionAssessment.from_dict(result).to_dict())


def ingest_scene(service, result):
    """Actual C1 service; false/rejection is surfaced, never reported as delivery."""
    if result.obstacle_frame is None or result.assessment is None:
        raise ValueError("NO_VALIDATED_SCENE_SAMPLE")
    browser_safe(result.obstacle_frame)
    browser_safe(result.assessment)
    if not service.ingest("obstacle_frame", result.obstacle_frame):
        raise ValueError("C1_OBSTACLE_REJECTED")
    if not service.ingest("collision_assessment", result.assessment):
        raise ValueError("C1_ASSESSMENT_REJECTED")
    return service.snapshot()
