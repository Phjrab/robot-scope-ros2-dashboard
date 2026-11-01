"""Explicit C1 clock normalization and legacy C4 consumer projection.

C1 owns validation/clock binding; inject the exact pinned implementations. This
module owns neither a competing schema nor a clock estimator nor a ROS port.
"""

from copy import deepcopy
import json


def canonical_assessment(assessment, *, normalize, clock_binding):
    """Use C1's v0.2 boundary without granting a new receipt time or TTL."""
    source = deepcopy(assessment)
    source["schema_version"] = "0.1"
    source["received_monotonic_ns"] = int(source["received_monotonic_ns"])
    source["validity_interval"] = source["freshness"].get(
        "source_validity_interval", {}
    )
    return normalize(source, binding=clock_binding)


def c4_constraint(
    assessment,
    *,
    validate_canonical,
    consume,
    binding,
    command_sequence,
    enforcement_mode,
):
    """Canonical validation -> explicit legacy C4 projection -> actual consumer.

    ADVISORY_ONLY is an upfront configuration, not a downgrade on any exception.
    ACTIVE fails closed: UNKNOWN is passed unmodified and C4 latches HOLD.
    """
    if enforcement_mode not in ("ACTIVE", "ADVISORY_ONLY"):
        raise ValueError("explicit enforcement mode required")
    validate_canonical(assessment)
    if enforcement_mode == "ADVISORY_ONLY":
        return None  # no command authority; NOT an enabled protective layer
    interval = assessment["validity_interval"]
    expected_frame = json.dumps(
        assessment["frame_key"], sort_keys=True, separators=(",", ":")
    )
    if (
        assessment["source_epoch"] != binding.source_epoch
        or assessment["host_clock_id"] != binding.clock_id
        or binding.frame_key != expected_frame
        or interval.get("host_clock_id") != binding.clock_id
        or assessment["map_binding"]["generation"] != binding.generation
        or assessment["path_ref"] != {"command_sequence": command_sequence}
    ):
        raise ValueError("CANONICAL_COMMAND_CONTEXT_MISMATCH")
    projected = deepcopy(assessment)
    projected["freshness"]["c4_binding"] = deepcopy(binding.__dict__)
    projected["validity_interval"] = dict(
        clock_id=interval["host_clock_id"],
        valid_from_ns=int(interval["start_monotonic_ns"]),
        valid_until_ns=int(interval["end_monotonic_ns"]),
    )
    # C4's old injected-validator API cannot consume canonical keys directly.
    # Verify canonical original with real C1 AND byte-exact projection here.
    expected = deepcopy(projected)

    def validate_projection(value):
        validate_canonical(assessment)
        if value != expected:
            raise ValueError("LEGACY_C4_PROJECTION_CHANGED")

    return consume(
        projected,
        validate_assessment=validate_projection,
        binding=binding,
        command_sequence=command_sequence,
    )
