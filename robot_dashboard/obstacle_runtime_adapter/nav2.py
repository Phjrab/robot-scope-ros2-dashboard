"""Transport/profile ports for Humble Nav2 1.1.20; no costmap or planner math."""
from copy import deepcopy
from dataclasses import dataclass
import math
import struct

from .isolation import review_topic
from .messages import Sample, finite, MAX_POINTS


@dataclass(frozen=True)
class Observation:
    sample: Sample
    topic: str
    marking: bool
    clearing: bool


def observation(sample, *, topic, source_kind, now_ns, receipt_clock_id, stale_ns=500_000_000):
    review_topic(topic)
    identity = sample.identity
    if (identity.receipt_clock_id != receipt_clock_id
            or not 0 <= now_ns - identity.received_ns <= stale_ns):
        raise ValueError("STALE_OR_UNMAPPED_OBSERVATION")
    if sample.kind != "PointCloud2" or source_kind not in {"lidar", "depth", "geometry"}:
        raise ValueError("RAW_GEOMETRY_REQUIRED")
    # Header frame must be the acquisition sensor frame for native clearing.
    # A fused geometry cloud has no single ray origin and is marking-only.
    clearing = (source_kind == "lidar" and sample.origin_m == (0., 0., 0.)
                and identity.frame_id == "review_lidar")
    return Observation(sample, topic, True, clearing)


def geometry_cloud(points, identity):
    """D2 supplies ALL observed geometry points, not a centroid or class filter.

    This encoder does no fusion, self filtering, localization exclusion or
    free-space generation. D2's bbox-only output cannot create clearing rays.
    """
    if len(points) > MAX_POINTS:
        raise ValueError("GEOMETRY_LIMIT")
    xyz = tuple(finite(p) for p in points)
    if any(len(p) != 3 for p in xyz):
        raise ValueError("XYZ_REQUIRED")
    data = b"".join(struct.pack("<fff", *p) for p in xyz)
    return Sample(identity, "PointCloud2", {"xyz_m": xyz, "raw_data": data,
        "fields": [{"name": n, "offset": i*4, "datatype": 7, "count": 1} for i, n in enumerate("xyz")],
        "width": len(xyz), "height": 1, "point_step": 12, "row_step": len(data),
        "is_bigendian": False}, diagnostics=("MARKING_ONLY_NO_FREE_RAYS",))


def ros_pointcloud(observation, *, pointcloud_type, field_type):
    """Inject generated sensor_msgs classes; preserve stamp, frame, raw layout."""
    sample = observation.sample
    msg = pointcloud_type()
    stamp = int(sample.identity.stamp_ns)
    msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(stamp, 1_000_000_000)
    msg.header.frame_id = sample.identity.frame_id
    for name in ("width", "height", "point_step", "row_step", "is_bigendian"):
        setattr(msg, name, sample.payload[name])
    msg.fields = []
    for f in sample.payload["fields"]:
        field = field_type()
        for name, value in f.items():
            setattr(field, name, value)
        msg.fields.append(field)
    msg.data = sample.payload["raw_data"]
    msg.is_dense = False
    return msg


def review_profile(base, *, envelope_radius_m, safety_padding_m):
    """Separate opt-in test copy. One inflation pass, independent mark sources.

    Radius must come from D3's conservative projected padded envelope. No
    polygon/full-body planning claim is made. Root product config stays intact.
    """
    radius, padding = finite((envelope_radius_m, safety_padding_m))
    if radius <= 0 or padding < 0:
        raise ValueError("EXPLICIT_D3_ENVELOPE_REQUIRED")
    result = deepcopy(base)
    for name, frame in (("global_costmap", "map"), ("local_costmap", "odom")):
        p = result[name][name]["ros__parameters"]
        if p["obstacle_layer"]["plugin"] != "nav2_costmap_2d::ObstacleLayer":
            raise ValueError("UNREVIEWED_PLUGIN")
        if p.get("footprint", "[]") not in ("", "[]"):
            raise ValueError("CIRCLE_BASELINE_REQUIRED")
        p.update(global_frame=frame, robot_base_frame="base_link", footprint="[]",
            robot_radius=max(radius, float(p["robot_radius"])),
            footprint_padding=max(padding, float(p.get("footprint_padding", 0.))),
            always_send_full_costmap=True, track_unknown_space=True,
            rolling_window=True, width=12, height=12,
            plugins=["obstacle_layer", "inflation_layer"])
        source = {"data_type": "PointCloud2", "marking": True,
            "clearing": False, "observation_persistence": 0., "expected_update_rate": .5,
            "min_obstacle_height": -.5, "max_obstacle_height": 2.,
            "obstacle_max_range": 8., "raytrace_max_range": 10., "inf_is_valid": False}
        p["obstacle_layer"] = {"plugin": "nav2_costmap_2d::ObstacleLayer", "enabled": True,
            "footprint_clearing_enabled": False, "combination_method": 1,
            "observation_sources": "lidar depth geometry",
            "lidar": dict(source, topic="/review/lidar_points", clearing=True, sensor_frame="review_lidar"),
            "depth": dict(source, topic="/review/depth_points", sensor_frame="review_depth"),
            "geometry": dict(source, topic="/review/geometry_marking")}
        p["inflation_layer"]["inflation_radius"] = max(
            p["inflation_layer"]["inflation_radius"], p["robot_radius"]+p["footprint_padding"]+p["resolution"])
    result["planner_server"]["ros__parameters"]["GridBased"].update(tolerance=0., allow_unknown=False)
    return result


def launch_parameters(base, *, envelope_radius_m, safety_padding_m):
    from .isolation import NAMESPACE
    profile = review_profile(base, envelope_radius_m=envelope_radius_m, safety_padding_m=safety_padding_m)
    result = {k: profile[k] for k in ("planner_server", "global_costmap", "local_costmap")}
    validate_launch_parameters(result)
    return {NAMESPACE: result}


def validate_launch_parameters(parameters):
    """Constrain the opt-in launch to two costmaps, one planner, review inputs."""
    if set(parameters) != {"planner_server", "global_costmap", "local_costmap"}:
        raise ValueError("REVIEW_NODES_ONLY")
    planner = parameters["planner_server"]["ros__parameters"]
    if (planner.get("planner_plugins") != ["GridBased"]
            or planner["GridBased"].get("plugin") != "nav2_navfn_planner/NavfnPlanner"
            or planner["GridBased"].get("allow_unknown") is not False):
        raise ValueError("REVIEW_PLANNER_REQUIRED")
    for name, frame in (("global_costmap", "map"), ("local_costmap", "odom")):
        p = parameters[name][name]["ros__parameters"]
        if (p["plugins"] != ["obstacle_layer", "inflation_layer"] or p["global_frame"] != frame
                or p["robot_base_frame"] != "base_link" or p.get("footprint", "[]") != "[]"
                or not math.isfinite(p["robot_radius"]) or p["robot_radius"] < .22
                or p["inflation_layer"]["plugin"] != "nav2_costmap_2d::InflationLayer"):
            raise ValueError("REVIEW_COSTMAP_REQUIRED")
        layer = p["obstacle_layer"]
        if (layer["plugin"] != "nav2_costmap_2d::ObstacleLayer"
                or layer["observation_sources"] != "lidar depth geometry"
                or layer.get("footprint_clearing_enabled") is not False):
            raise ValueError("REVIEW_OBSERVATIONS_REQUIRED")
        for source, topic in (("lidar", "/review/lidar_points"), ("depth", "/review/depth_points"), ("geometry", "/review/geometry_marking")):
            s = layer[source]
            if (s["topic"] != topic or s["data_type"] != "PointCloud2" or s["marking"] is not True
                    or s["clearing"] is not (source == "lidar")):
                raise ValueError("PER_SENSOR_MARK_CLEAR_REQUIRED")
    # Reject injected robot remaps, external map topics, ROS endpoint params.
    def scan(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"odom_topic", "map_topic", "cmd_vel_topic", "filters", "remappings"}:
                    raise ValueError("PRODUCT_ENDPOINT_FORBIDDEN")
                scan(child)
        elif isinstance(value, list):
            for child in value:
                scan(child)
        elif isinstance(value, str) and value.startswith(("http:", "https:", "dds:", "rtsp:", "/dev/")):
            raise ValueError("REAL_ENDPOINT_FORBIDDEN")
    scan(parameters)
