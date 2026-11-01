"""D2-owned numerical shim for C4's actual Sample -> frame injection boundary.

No acquisition, ROS serialization, worker, service or shared validator here.
C1's canonical/ObstacleFrame implementations must be injected by the host.
"""

from copy import deepcopy
import time
import numpy as np
from .core import Limits, Tracker, process_lidar


def compact_frame(frame, *, canonical, max_bytes=16 * 1024, reserve_bytes=2048):
    """Deduplicate provenance only. Never drop objects, extents, or timestamps.

    Source references address frame.input_sources, retaining old occluded source
    receipts and distinct sensor origins. Over budget rejects the whole delivery;
    full geometry remains with the caller for collision use, not hidden UI loss.
    """
    out = deepcopy(frame)
    sources = []

    def source_ref(value):
        for i, source in enumerate(sources):
            if value == source:
                return i
        if len(sources) >= 16:
            raise ValueError("PROVENANCE_SOURCE_BUDGET")
        sources.append(deepcopy(value))
        return len(sources) - 1

    for source in out["input_sources"]:
        source_ref(source)

    def visit(value):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == "source" and isinstance(item, dict) and "stamp_ns" in item:
                    result["source_ref"] = source_ref(item)
                else:
                    result[key] = visit(item)
            return result
        if isinstance(value, list):
            return [visit(item) for item in value]
        return value

    for obstacle in out["obstacles"]:
        obstacle["provenance"] = visit(obstacle["provenance"])
    out["input_sources"] = sources
    out["health"]["provenance_encoding"] = "input_sources_index_v1"
    # Injected C1 encoder enforces its own JSON rules; this is a transport budget,
    # not a competing schema validator. Reserve covers C4 wrapper diagnostics.
    encoded = canonical(out)
    if not 0 <= reserve_bytes < max_bytes or len(encoded) + reserve_bytes > max_bytes:
        raise ValueError(
            f"FRAME_BUDGET_EXCEEDED:{len(encoded)}+{reserve_bytes}>{max_bytes}"
        )
    return out


class C4CorePort:
    """Injected C4 RuntimeAdapter.d2, precise process(sample) shim.

    Supports C4 PointCloud2 Sample only. Other kinds need an explicitly paired
    capture-time calibrated RGB-D call to lift_detections, never process(packet).
    One instance is bound to one sensor source. Sensor-frame geometry is retained
    unchanged; local/map transform must be explicit upstream, never latest TF.
    """

    def __init__(
        self,
        *,
        canonical,
        validate_frame,
        limits=Limits(),
        geometry_context=None,
        clock_ns=time.monotonic_ns,
        processing_clock_id="d2-process-monotonic",
    ):
        self.canonical = canonical
        self.validate_frame = validate_frame
        self.limits = limits
        self.geometry_context = geometry_context or (lambda sample: {})
        self.clock_ns = clock_ns
        self.processing_clock_id = processing_clock_id
        self.tracker = Tracker(limits)
        self.source_id = None
        self.last_result = None

    def process(self, sample):
        if sample.kind != "PointCloud2":
            raise ValueError("PAIRED_RGBD_INPUT_REQUIRED")
        identity = sample.identity
        if self.source_id not in (None, identity.source_id):
            raise ValueError("ONE_SENSOR_SOURCE_PER_PORT")
        self.source_id = identity.source_id
        payload = sample.payload
        metadata = payload.get("metadata", {})
        meta = identity.packet()
        meta.update(
            host_clock_id=identity.receipt_clock_id,
            received_monotonic_ns=identity.received_ns,
            sensor_origin_m=deepcopy(sample.origin_m),
            field_layout=deepcopy(payload["fields"]),
            calibration_id=metadata.get("calibration_id"),
        )
        context = self.geometry_context(sample)
        points = np.asarray(payload["xyz_m"], dtype=float).reshape(-1, 3)
        observation = process_lidar(
            points,
            meta,
            limits=self.limits,
            ground=context.get("ground"),
            self_boxes=context.get("self_boxes", ()),
            reference=context.get("reference"),
        )
        observation["dropped_counts"]["transport_invalid"] = payload.get(
            "invalid_points", 0
        )
        self.last_result = self.tracker.step(observation)
        frame = self.last_result["obstacle_frame"]
        frame["health"]["postprocess"] = {
            "completed_monotonic_ns": self.clock_ns(),
            "host_clock_id": self.processing_clock_id,
            "renews_observation": False,
        }
        if observation["dropped_counts"]["object_budget"]:
            raise ValueError("GEOMETRY_INCOMPLETE_OBJECT_BUDGET")
        out = compact_frame(frame, canonical=self.canonical)
        self.validate_frame(out)
        return out
