"""Normalized raw PointCloud2 -> explicit calibrated local-frame packet.

TF is an injected stamped transform; this module never looks up or publishes TF.
Keep the original Sample separately for the existing review-only ROS raw route.
"""
from copy import deepcopy
import hashlib
import numpy as np
from robot_dashboard.relocalization.experimental_se3 import validate_transform
from .composition import InputFramePacket


def packet_from_pointcloud(sample, *, context, clock_epoch, transform, calibration_id,
                           max_range_m, fov_rad):
    identity = sample.identity
    if sample.kind != "PointCloud2" or sample.origin_m != (0., 0., 0.):
        raise ValueError("RAW_SENSOR_CLOUD_AND_ORIGIN_REQUIRED")
    if (identity.source_epoch != context.source_epoch or identity.tf_epoch != context.tf_epoch
            or identity.binding != (context.map_id, context.map_revision, context.tf_epoch, context.map_generation)
            or identity.receipt_clock_id != context.host_clock_id or clock_epoch != context.clock_epoch):
        raise ValueError("RAW_CLOUD_CONTEXT_MISMATCH")
    if (transform.get("verified") is not True or transform.get("source_frame") != identity.frame_id
            or transform.get("target_frame") != context.frame_id or transform.get("stamp_ns") != identity.stamp_ns
            or transform.get("source_epoch") != identity.source_epoch or transform.get("tf_epoch") != identity.tf_epoch
            or transform.get("clock_domain") != identity.clock_domain):
        raise ValueError("STAMPED_CALIBRATED_TRANSFORM_REQUIRED")
    matrix = validate_transform(transform["matrix"])
    points = np.asarray(sample.payload["xyz_m"], dtype=float).reshape(-1, 3)
    local = points @ matrix[:3, :3].T + matrix[:3, 3]
    meta = dict(source_epoch=identity.source_epoch, sequence=identity.sequence, stamp_ns=identity.stamp_ns,
        clock_domain=identity.clock_domain, frame_key=dict(source_epoch=identity.source_epoch, frame_id=context.frame_id),
        map_binding=context.map_binding, host_clock_id=identity.receipt_clock_id, received_monotonic_ns=identity.received_ns,
        evidence_kind=identity.evidence_kind, calibration_id=calibration_id, field_layout=deepcopy(sample.payload["fields"]))
    source = dict(meta=deepcopy(meta), tf_epoch=identity.tf_epoch, sensor_frame=identity.frame_id,
        origin_m=matrix[:3, 3].tolist(), max_range_m=max_range_m, fov_rad=fov_rad,
        valid_measurement=bool(len(points)), calibration_id=calibration_id,
        raw_reference=hashlib.sha256(sample.payload["raw_data"]).hexdigest(),
        transform=deepcopy(transform), invalid_points=sample.payload["invalid_points"], free_rays=[])
    # A return cloud is marking data here. No clearing proof is synthesized.
    return InputFramePacket(meta, context.key, clock_epoch, identity.tf_epoch, local, dict(lidar=source))
