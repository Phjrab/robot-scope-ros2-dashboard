"""Explicit current-owner profile, retaining the older pinned CorePorts unchanged.

C1 4e1dd519 owns clock normalization; D3 356d0a03 owns swept-volume coverage.
No automatic schema fallback. C3's supported legacy profile is opt-in and bounded.
"""
from copy import deepcopy
from dataclasses import asdict, replace

from .binding import browser_safe, decimal
from .ports import CorePorts, ingest_scene


class CanonicalCorePorts(CorePorts):
    @classmethod
    def from_installed(cls, geometry, **kwargs):
        from robot_dashboard import obstacle_fusion_core, collision_geometry_core, expansion_contracts
        from robot_dashboard.expansion_contracts import time_binding
        from robot_dashboard.collision_geometry_core import contracts
        from robot_dashboard.obstacle_fusion_core.consumer_port import compact_frame
        result = cls(obstacle_fusion_core, collision_geometry_core, expansion_contracts, geometry, **kwargs)
        result.time_binding, result.d3_contracts, result.compact_frame = time_binding, contracts, compact_frame
        return result

    def perceive(self, packet, meta, rays):
        result = super().perceive(packet, meta, rays)
        # A partial component list cannot qualify complete collision coverage.
        if result["obstacle_frame"]["dropped_counts"].get("object_budget", 0):
            raise ValueError("GEOMETRY_INCOMPLETE_OBJECT_BUDGET")
        result["obstacle_frame"] = self.time_binding.upgrade_observation(result["obstacle_frame"])
        self.contracts.ObstacleFrame.from_dict(result["obstacle_frame"])
        return result

    def assess(self, state, frame, motion, *, now_stamp_ns, clock_domain, complete, coverage_evidence=None):
        # Never replace a missing volume certificate with the old magic label.
        return self.d3.assess(self.geometry, state, frame, motion,
            now_stamp_ns=now_stamp_ns, now_clock_domain=clock_domain,
            uncertainty_in_extent=True, coverage=deepcopy(coverage_evidence) if complete else None)

    def canonical_assessment(self, assessment, *, context, mapping, motion, timing):
        if (assessment.get("schema_version") != "0.2"
                or assessment.get("producer") != "d3.collision_geometry_core"):
            raise ValueError("CURRENT_D3_PROFILE_REQUIRED")
        if (assessment["robot_geometry_hash"] != context.robot_geometry_hash
                or assessment["path_ref"] != motion["ref"]):
            raise ValueError("D3_GEOMETRY_OR_MOTION_MISMATCH")
        mapping.check(context, assessment["clock_domain"])
        original = assessment["freshness"].get("source_validity_interval", {})
        if original:
            if set(original) != {"clock_domain", "from_ns", "until_ns"}:
                raise ValueError("UNSUPPORTED_D3_VALIDITY")
            mapping.check(context, original["clock_domain"])
            # C4 checks calibration lifetime/clock epoch; C1 performs conversion.
            mapping.host(decimal(original["from_ns"]))
            mapping.host(decimal(original["until_ns"]))
        binding = self.time_binding.ClockBinding(mapping.source_domain, mapping.source_epoch,
            mapping.host_clock_id, mapping.offset_ns, mapping.uncertainty_ns, mapping.evidence_id)
        result = self.d3_contracts.canonical_assessment(assessment,
            normalize=self.time_binding.normalize_collision_assessment, clock_binding=binding)
        result["freshness"]["c4_binding"] = asdict(context)
        result["freshness"]["protection_mode"] = "ADVISORY_ONLY"
        result["freshness"]["c4"] = dict(
            source_profile="d3-356d0a036eb62d546e159e12a0691d7f5ea278f6/0.2",
            clock_epoch=mapping.clock_epoch, mapping_window_ns=[str(mapping.source_start_ns),str(mapping.source_end_ns)],
            original_validity_interval=deepcopy(original),
            timing={k: str(v) if k.endswith("_ns") else v for k, v in timing.items()},
            product_enforcement_connected=False,
        )
        # Full original references are now supported by actual C1; do not narrow.
        return self.contracts.CollisionAssessment.from_dict(result).to_dict()

    def scene_obstacle(self, frame):
        """Use D2's actual provenance-only compactor, retaining every object."""
        result = self.compact_frame(frame, canonical=self.contracts.canonical)
        return self.contracts.ObstacleFrame.from_dict(result).to_dict()

    def ingest_scene(self, service, result, *, legacy_profile=False):
        """Explicit version choice before delivering to the actual C1 service."""
        if service.schema_version != ('0.1' if legacy_profile else '0.2'):
            raise ValueError('EXPLICIT_C1_SERVICE_PROFILE_REQUIRED')
        if result.obstacle_frame is None or result.assessment is None:
            raise ValueError('NO_VALIDATED_SCENE_SAMPLE')
        obstacle = self.scene_obstacle(result.obstacle_frame)
        assessment = result.assessment
        if legacy_profile:
            obstacle = legacy_observation(obstacle, validate=self.contracts.ObstacleFrame.from_dict)
            assessment = legacy_observation(assessment, validate=self.contracts.CollisionAssessment.from_dict)
        return ingest_scene(service, replace(result, obstacle_frame=obstacle, assessment=assessment))


def legacy_observation(payload, *, validate):
    """Explicit C1-supported 0.1 wire projection for the pinned C3 consumer.

    It is NOT an automatic fallback for unknown clocks/versions. No renamed
    validity aliases, receipt reset, reference removal, or unsafe Number values.
    """
    if payload.get("schema_version") != "0.2":
        raise ValueError("CANONICAL_V02_INPUT_REQUIRED")
    validate(payload)

    def convert(value):
        if isinstance(value, list):
            return [convert(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {k: convert(v) for k, v in value.items()}
        for key in ("received_monotonic_ns", "received_ns", "start_monotonic_ns", "end_monotonic_ns"):
            if key in result and result[key] is not None:
                value = result[key]
                if isinstance(value, str):
                    result[key] = decimal(value)
        if result.get("schema_version") == "0.2" and "received_monotonic_ns" in result:
            result["schema_version"] = "0.1"
        return result

    out = browser_safe(convert(deepcopy(payload)))
    return validate(out).to_dict()
