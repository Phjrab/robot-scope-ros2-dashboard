#!/usr/bin/env python3
"""Finite, headless ROS 2 collection for the isolated VSLAM lab domain.

Only subscribes. No robot commands, bag recording, device access or parameters changed.
Run inside the pinned ROS container; analyze.py remains usable without ROS.
"""
import argparse
import datetime
import json
import math
import os
from pathlib import Path
import signal
import time


STATUS_SOURCE = "NVIDIA-ISAAC-ROS/isaac_ros_visual_slam@e31f4cc1d41a329a01946e5fe63669f8b15da677:isaac_ros_visual_slam_interfaces/msg/VisualSlamStatus.msg"
STATUS_MAP = {0: "UNKNOWN", 1: "TRACKING", 2: "LOST"}
STATUS_TIMINGS = ("node_callback_execution_time", "track_execution_time",
                  "track_execution_time_mean", "track_execution_time_max")


def status_schema_matches(fields):
    expected = {"header", "vo_state", *STATUS_TIMINGS}
    return (set(fields) == expected and fields["vo_state"] == "uint8" and
            fields["header"] in ("std_msgs/Header", "std_msgs/msg/Header") and
            all(fields[name] in ("double", "float64") for name in STATUS_TIMINGS))


def finite_json(value):
    """Keep sensor invalid values explicit without emitting nonstandard NaN/Infinity JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): finite_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_json(v) for v in value]
    return value


def vector(message):
    return [message.x, message.y, message.z]


def sample_fields(stream, message):
    result = {}
    if hasattr(message, "header"):
        stamp = message.header.stamp
        result.update(stamp_ns=stamp.sec * 1_000_000_000 + stamp.nanosec, frame_id=message.header.frame_id)
    if stream in ("left", "right"):
        result.update(width=message.width, height=message.height, encoding=message.encoding,
                      is_bigendian=message.is_bigendian, step=message.step)
    elif stream.endswith("_info"):
        result.update(width=message.width, height=message.height,
                      distortion_model=message.distortion_model,
                      d=list(message.d), k=list(message.k), r=list(message.r), p=list(message.p),
                      binning_x=message.binning_x, binning_y=message.binning_y,
                      roi={key: getattr(message.roi, key) for key in
                           ("x_offset", "y_offset", "height", "width", "do_rectify")})
    elif stream == "imu":
        result.update(angular_velocity_rad_s=vector(message.angular_velocity),
                      linear_acceleration_m_s2=vector(message.linear_acceleration),
                      angular_velocity_covariance=list(message.angular_velocity_covariance),
                      linear_acceleration_covariance=list(message.linear_acceleration_covariance))
    elif stream == "odom":
        pose = message.pose.pose if hasattr(message.pose, "pose") else message.pose
        q = pose.orientation
        result["pose"] = {"position": vector(pose.position), "quaternion_xyzw": [q.x, q.y, q.z, q.w]}
        if hasattr(message, "child_frame_id"):
            result["child_frame_id"] = message.child_frame_id
    elif stream == "slam_path":
        result["path_poses"] = len(message.poses)
        if message.poses:
            latest = message.poses[-1]
            q = latest.pose.orientation
            result["pose"] = {"position": vector(latest.pose.position), "quaternion_xyzw": [q.x, q.y, q.z, q.w]}
            result["stamp_ns"] = latest.header.stamp.sec * 1_000_000_000 + latest.header.stamp.nanosec
            result["frame_id"] = latest.header.frame_id or message.header.frame_id
    elif stream == "status":
        fields = dict(message.get_fields_and_field_types())
        result["status_fields"] = fields
        result["status_schema_matches_release32"] = status_schema_matches(fields)
        if result["status_schema_matches_release32"]:
            result["vo_state"] = int(message.vo_state)
            result["tracking_state"] = STATUS_MAP.get(message.vo_state, "UNMAPPED")
            result["algorithm_timing_seconds"] = {name: getattr(message, name) for name in STATUS_TIMINGS}
        else:
            result["tracking_state"] = "UNMAPPED"
    elif stream == "static_tf":
        result["transforms"] = [
            {"parent": transform.header.frame_id, "child": transform.child_frame_id,
             "stamp_ns": transform.header.stamp.sec * 1_000_000_000 + transform.header.stamp.nanosec,
             "translation_m": vector(transform.transform.translation),
             "quaternion_xyzw": [transform.transform.rotation.x, transform.transform.rotation.y,
                                  transform.transform.rotation.z, transform.transform.rotation.w]}
            for transform in message.transforms]
    return finite_json(result)


def read_resources():
    """Read local /proc and thermal sysfs; no device control and no privilege escalation."""
    values = {}
    try:
        fields = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            fields[key] = float(value.strip().split()[0]) * 1024
        values["ram_used_bytes"] = fields["MemTotal"] - fields["MemAvailable"]
        values["ram_available_bytes"] = fields["MemAvailable"]
        values["swap_used_bytes"] = fields["SwapTotal"] - fields["SwapFree"]
    except (OSError, KeyError, ValueError):
        pass
    try:
        values["load_average_1m"] = os.getloadavg()[0]
    except OSError:
        pass
    for path in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        try:
            name = (path / "type").read_text().strip()
            values[f"temperature_c/{path.name}/{name}"] = float((path / "temp").read_text().strip()) / 1000
        except (OSError, ValueError):
            pass
    return values


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--domain", type=int, required=True)
    parser.add_argument("--duration", type=float, required=True, help="Wall monotonic seconds, including warmup; 1..3600")
    parser.add_argument("--max-events", type=int, default=250000)
    parser.add_argument("--evidence-type", choices=("official_bag", "live_input", "live_stationary", "live_supervised_motion", "recorded_sensor_bag", "synthetic"), required=True)
    parser.add_argument("--use-sim-time", action="store_true")
    parser.add_argument("--clock-contract-evidence", default="", help="Only provide after verifying header/receipt use the same ROS clock")
    parser.add_argument("--left", default="/vslam_lab/camera/infra1/image_rect_raw")
    parser.add_argument("--right", default="/vslam_lab/camera/infra2/image_rect_raw")
    parser.add_argument("--left-info", default="/vslam_lab/camera/infra1/camera_info")
    parser.add_argument("--right-info", default="/vslam_lab/camera/infra2/camera_info")
    parser.add_argument("--imu", default="", help="Empty omits IMU (VO); set verified D435i IMU topic for VIO")
    parser.add_argument("--odom", default="/vslam_lab/visual_slam/tracking/odometry")
    parser.add_argument("--slam-path", default="", help="Optional release-3.2 nav_msgs/Path topic; collects latest path pose only")
    parser.add_argument("--status", default="/vslam_lab/visual_slam/status")
    parser.add_argument("--static-tf", default="/vslam_lab/tf_static")
    args = parser.parse_args(argv)
    if not math.isfinite(args.duration) or not 1 <= args.duration <= 3600:
        parser.error("--duration must be finite and 1..3600")
    if not 1 <= args.max_events <= 2_000_000:
        parser.error("--max-events must be 1..2000000")
    if not 1 <= args.domain <= 232:
        parser.error("--domain must be an independently verified unused value in 1..232")
    if os.environ.get("ROS_DOMAIN_ID") != str(args.domain):
        parser.error("ROS_DOMAIN_ID must already equal --domain in this process environment")
    if os.environ.get("ROS_LOCALHOST_ONLY") != "1":
        parser.error("ROS_LOCALHOST_ONLY=1 is required for this local-only collector")
    return args


def main():
    args = parse_args()
    import rclpy
    from rclpy.parameter import Parameter
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
    from rosidl_runtime_py.utilities import get_message

    rclpy.init(args=[])
    node = rclpy.create_node("metrics_collector", namespace="/vslam_lab",
                            parameter_overrides=[Parameter("use_sim_time", value=args.use_sim_time)])
    definitions = {
        "left": (args.left, "sensor_msgs/msg/Image"), "right": (args.right, "sensor_msgs/msg/Image"),
        "left_info": (args.left_info, "sensor_msgs/msg/CameraInfo"),
        "right_info": (args.right_info, "sensor_msgs/msg/CameraInfo"),
        "imu": (args.imu, "sensor_msgs/msg/Imu"), "odom": (args.odom, "nav_msgs/msg/Odometry"),
        "slam_path": (args.slam_path, "nav_msgs/msg/Path"),
        "status": (args.status, "isaac_ros_visual_slam_interfaces/msg/VisualSlamStatus"),
        "static_tf": (args.static_tf, "tf2_msgs/msg/TFMessage")}
    definitions = {k: v for k, v in definitions.items() if v[0]}
    stop = {"reason": None, "samples": 0}
    def on_signal(signum, frame):
        stop["reason"] = signal.Signals(signum).name
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, on_signal)
    # Exclusive create preserves previous run evidence and fails early on accidental reuse.
    with args.output.open("x", encoding="utf-8", buffering=1) as output:
        def write(event):
            output.write(json.dumps(finite_json(event), allow_nan=False, separators=(",", ":")) + "\n")
        start_ns = time.monotonic_ns()
        write({"event": "run_start", "schema_version": 1, "run_id": args.run_id,
               "utc_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "receipt_monotonic_ns": start_ns,
               "evidence_type": args.evidence_type,
               "ros_domain_id": os.environ["ROS_DOMAIN_ID"], "ros_localhost_only": os.environ["ROS_LOCALHOST_ONLY"],
               "rmw_implementation": os.environ.get("RMW_IMPLEMENTATION", "DEFAULT"),
               "use_sim_time": node.get_parameter("use_sim_time").value,
               "duration_seconds": args.duration, "max_events": args.max_events,
               "streams": {k: {"topic": v[0], "type": v[1]} for k, v in definitions.items()},
               "clock_contract": {"header_and_receipt_same_ros_clock": bool(args.clock_contract_evidence),
                                  "evidence": args.clock_contract_evidence, "mode": "simulation" if args.use_sim_time else "live"},
               "status_schema_source": STATUS_SOURCE, "status_mapping": STATUS_MAP,
               "resource_scope": "container-visible host memory/load/thermal; no GPU or per-process CPU claimed"})
        try:
            subscriptions = []
            for stream, (topic, type_name) in definitions.items():
                def callback(message, stream=stream):
                    receipt = time.monotonic_ns()
                    ros_ns = node.get_clock().now().nanoseconds
                    write({"event": "sample", "stream": stream, "receipt_monotonic_ns": receipt,
                           "receipt_ros_ns": ros_ns, **sample_fields(stream, message)})
                    stop["samples"] += 1
                    if stop["samples"] >= args.max_events:
                        stop["reason"] = "max_events"
                qos = QoSProfile(depth=50, reliability=ReliabilityPolicy.BEST_EFFORT)
                if stream == "static_tf":
                    qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
                subscriptions.append(node.create_subscription(get_message(type_name), topic, callback, qos))
            next_resource = start_ns
            while not stop["reason"] and rclpy.ok():
                now_ns = time.monotonic_ns()
                if now_ns - start_ns >= args.duration * 1e9:
                    stop["reason"] = "duration_complete"
                    break
                if now_ns >= next_resource:
                    write({"event": "resource", "receipt_monotonic_ns": now_ns, "values": read_resources()})
                    next_resource = now_ns + 1_000_000_000
                rclpy.spin_once(node, timeout_sec=.1)
        except Exception as exc:
            stop["reason"] = "collector_error"
            write({"event": "collector_error", "receipt_monotonic_ns": time.monotonic_ns(),
                   "error_type": type(exc).__name__, "message": str(exc)})
            raise
        finally:
            write({"event": "run_end", "receipt_monotonic_ns": time.monotonic_ns(),
                   "reason": stop["reason"] or "ros_context_ended", "samples_written": stop["samples"]})
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()


if __name__ == "__main__":
    main()
