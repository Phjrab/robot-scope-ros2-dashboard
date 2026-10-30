"""Synthetic input/evidence contract for the C4-owned ROS-to-Runtime bridge.

No ROS import, worker, perception, controller or publication implementation.
PointCloud2 bytes are fixture measurements, not fused boxes or free-space claims.
"""

import math
import struct

CASES = (
    "empty_path_preserved", "obstacle_appears", "obstacle_removed_with_rays",
    "input_stale", "map_revision_source_epoch", "old_frame_rejected",
)
STAGES = (
    "ros_received", "identity_verified", "worker_completed", "d2_completed",
    "d3_completed", "observation_published", "costmap_observed", "plan_observed",
    "actuator_result",
)


def measurement(sequence=1, *, epoch="sensor-1", revision="r1", generation=0,
                stamp_ns=1_000_000_000, received_ns=2**53 + 12345,
                obstacle=False):
    """Bounded planar ray fixture; all endpoints are actual synthetic returns.

    Empty means no interior obstacle, not an empty point list: room-wall returns
    retain ray origin and measured range. Not a D3 complete-volume certificate.
    """
    points, rays = [], []
    for index in range(33):
        angle = -.8 + index * .05
        distance = 2.0 if obstacle and abs(angle) <= .1 else 5.0
        end = (distance * math.cos(angle), distance * math.sin(angle), .15)
        points.append(end)
        rays.append({"origin": [0., 0., 0.], "endpoint": list(end),
                     "measurement_valid": True, "beam": index})
    identity = dict(source_id="d3-review-lidar", source_epoch=epoch,
        sequence=sequence, stamp_ns=str(stamp_ns), clock_domain="review-sim",
        frame_id="review_lidar", received_ns=received_ns,
        receipt_clock_id="review-host-monotonic", tf_epoch="review-tf-1",
        map_id="d3-review-map", revision=revision, map_generation=generation,
        evidence_kind="SYNTHETIC", producer="d3.input-fixture")
    raw_reference = f"fixture:{epoch}:{sequence}:{stamp_ns}"
    for ray in rays:
        ray["raw_reference"] = raw_reference
    sec, nanosec = divmod(stamp_ns, 1_000_000_000)
    message = dict(header=dict(stamp=dict(sec=sec, nanosec=nanosec), frame_id="review_lidar"),
        height=1, width=len(points), point_step=12, row_step=len(points)*12,
        fields=[dict(name=n, offset=i*4, datatype=7, count=1) for i,n in enumerate("xyz")],
        is_bigendian=False, is_dense=True,
        data=b"".join(struct.pack("<fff", *point) for point in points))
    return dict(identity=identity, message=message, raw_reference=raw_reference,
                rays=rays, coverage=None, protection_mode="ADVISORY_ONLY")


def latency_ns(first, second):
    """Compare only explicitly same clock AND epoch. JSON times stay strings."""
    if (not first.get("clock_id") or not first.get("epoch")
            or (first["clock_id"], first["epoch"]) != (second.get("clock_id"), second.get("epoch"))):
        return None
    a, b = int(first["stamp_ns"]), int(second["stamp_ns"])
    if b < a:
        return None
    return str(b-a)


def audit_case(case, evidence):
    """Missing real native observations remain NOT_RUN, never mock success.

    This validates an evidence envelope, not Nav2 physics. The existing native
    independent contact/boundary validator remains mandatory and unchanged.
    """
    if case not in CASES:
        raise ValueError("UNKNOWN_CASE")
    if evidence.get("execution") != "NATIVE_NAV2_SIM":
        return {"status": "NOT_RUN", "reason": "REAL_NATIVE_EXECUTION_REQUIRED"}
    required = STAGES if case not in ("input_stale", "old_frame_rejected") else (
        "ros_received", "identity_verified", "rejection_or_stale", "actuator_result")
    missing = [s for s in required if not evidence.get(s)]
    if missing:
        return {"status": "FAIL", "reason": "MISSING_STAGE", "missing": missing}
    if evidence.get("independent_validation") != "PASS":
        return {"status": "FAIL", "reason": "INDEPENDENT_VALIDATION_REQUIRED"}
    if evidence.get("contact_count") != 0 or evidence.get("boundary_count") != 0:
        return {"status": "FAIL", "reason": "CONTACT_OR_BOUNDARY"}
    if case == "obstacle_removed_with_rays" and not (
        evidence.get("raw_ray_reference") and evidence.get("cleared_cell_indices")
        and evidence.get("marking_cell_indices") and evidence.get("ray_cell_intersections")
    ):
        return {"status": "FAIL", "reason": "CLEARING_RAY_AND_CELL_PROOF_REQUIRED"}
    return {"status": "PASS", "claim": "EVIDENCE_ENVELOPE_ONLY"}
