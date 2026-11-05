#!/usr/bin/env python3
"""A3 real Humble/Nav2 replay with synthetic sensors and simulated actuator."""
from __future__ import annotations

import argparse
import json
import math
import platform
import shlex
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

SHA = "4cebeed8f309a1f5e69ade96f21a4f29d2ba93f4"
ROOM = (0.0, 0.0, 11.0, 9.0)
START = (2.0, 3.0, 0.25)
ODOM_START = (7.0, -3.0, 0.80)
RADIUS = 0.22
RAW = "/robot_scope/nav/cmd_vel_raw"
HEALTH = "/robot_scope/nav/runtime_health"
CONTROLLER_ODOM = "/utlidar/robot_odom"
RECOVERY = "/robot_scope/nav/recovery_cmd_vel_blocked"
MODE = "manual_seeded_2d"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def compose(a, b):
    c, s = math.cos(a[2]), math.sin(a[2])
    return (a[0] + c * b[0] - s * b[1], a[1] + s * b[0] + c * b[1], angle(a[2] + b[2]))


def inverse(pose):
    x, y, yaw = pose
    c, s = math.cos(yaw), math.sin(yaw)
    return (-c * x - s * y, s * x - c * y, -yaw)


def error(a, b):
    return math.dist(a[:2], b[:2]), abs(angle(a[2] - b[2]))


def yaw(quaternion):
    return math.atan2(2 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
                      1 - 2 * (quaternion.y ** 2 + quaternion.z ** 2))


def stamp_ns(stamp):
    return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)


def pose_from_transform(transform):
    return (transform.translation.x, transform.translation.y, yaw(transform.rotation))


def contact_clearance(pose, obstacle):
    x, y, _ = pose
    room_distance = min(x - ROOM[0], ROOM[2] - x, y - ROOM[1], ROOM[3] - y)
    if obstacle:
        left, bottom, right, top = obstacle
        dx = max(left - x, 0.0, x - right)
        dy = max(bottom - y, 0.0, y - top)
        distance = math.hypot(dx, dy)
        if dx == dy == 0.0:
            distance = -min(x - left, right - x, y - bottom, top - y)
        room_distance = min(room_distance, distance)
    return room_distance - RADIUS


def make_map(path):
    path.mkdir()
    resolution = 0.05
    width, height = round(ROOM[2] / resolution), round(ROOM[3] / resolution)
    pixels = bytes(0 if min(u, v, width - u - 1, height - v - 1) < 2 else 254
                   for v in range(height) for u in range(width))
    (path / "room.pgm").write_bytes(f"P5\n{width} {height}\n255\n".encode() + pixels)
    (path / "room.yaml").write_text(
        "image: room.pgm\nresolution: 0.05\norigin: [0.0, 0.0, 0.0]\n"
        "negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\nmode: trinary\n"
    )


def native_launcher(repo, output):
    """Run the exact product process-launch tail without accessing host/hardware setup."""
    source = (repo / "scripts/run_go2_navigation_humble.sh").read_text()
    begin = 'PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"'
    require(source.count(begin) == 1, "production launcher boundary changed")
    tail = source[source.index(begin):]
    require(tail.count('if [[ "$MAPPING_PROFILE" == "go2-xt16-wireless" ]]; then') == 1,
            "production wireless transport boundary changed")
    wrapper = output / "launch_native.sh"
    wrapper.write_text(
        "#!/bin/bash\nset -eo pipefail\n"
        '[[ "$#" == 6 && "$1" == --map-yaml && "$3" == --params-file && '
        '"$5" == --mode && "$6" == manual_seeded_2d ]]\n'
        f"PROJECT_DIR={shlex.quote(str(repo))}\n"
        f"EVIDENCE_DIR={shlex.quote(str(output))}\n"
        'MAP_YAML="$2"\nPARAMS_FILE="$4"\nRUNTIME_MODE=(--mode "$6")\n'
        "MAPPING_PROFILE=go2-onboard\n"
        'cd "$PROJECT_DIR"\n'
        'JOB_NAME="$(basename -- "$(dirname -- "$PARAMS_FILE")")"\n'
        'exec > >(tee "$EVIDENCE_DIR/nav2-$JOB_NAME.log") 2>&1\n'
        + tail
    )
    wrapper.chmod(0o700)
    return wrapper


def run(repo, output, requested_sha, report):
    require(requested_sha == SHA, "runner requires the exact requested A3 SHA")
    # Container package sets can omit git. In that case verify immutable input
    # on the host before mounting and pass the verified SHA explicitly.
    if shutil.which("git") and (repo / ".git").exists():
        actual = subprocess.check_output(
            ["git", "-c", f"safe.directory={repo}", "-C", str(repo), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        require(actual == SHA, f"source HEAD is {actual}, expected {SHA}")
        report["sha_verified_in_container"] = actual
    sys.path.insert(0, str(repo / "experiments/competition_nav2"))
    sys.path.insert(0, str(repo))
    from preflight import require_isolated

    report["isolation"] = require_isolated()

    import numpy as np
    import rclpy
    from action_msgs.msg import GoalStatus, GoalStatusArray
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import OccupancyGrid, Odometry, Path as NavPath
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
    from rclpy.time import Time
    from sensor_msgs.msg import LaserScan, PointCloud2, PointField
    from std_msgs.msg import String
    from tf2_ros import Buffer, TransformListener, TransformException

    from robot_dashboard.control import ControlManager, ControlError
    from robot_dashboard.navigation_jobs import (
        MAP_YAML_TOKEN, PARAMS_FILE_TOKEN, NavigationCommandSpec, NavigationJobManager,
    )
    from robot_dashboard.ros.navigation_gateway import NavigationRosGateway
    from robot_dashboard.saved_maps import SavedMapCatalog

    readonly = json.loads((repo / "config/go2-onboard.json").read_text())
    control_profile = {key: readonly[key] for key in ("control", "navigation_health")}
    trace_file = (output / "trace.jsonl").open("w", buffering=1)
    trace_lock = threading.Lock()
    t0 = time.monotonic()

    def trace(event, **fields):
        with trace_lock:
            trace_file.write(json.dumps({"t_s": time.monotonic() - t0,
                                         "event": event, **fields}, allow_nan=False) + "\n")

    class ControlPort:
        """Physical output boundary only. Gate, lease and watchdog are product code."""
        def __init__(self):
            self.manager = ControlManager(control_profile, environ={"ROBOT_SCOPE_CONTROL_ENABLED": "1"})
            self.operation_lock = threading.RLock()
            self.velocity = (0.0, 0.0, 0.0)
            self.last_drive_at = 0.0
            self.stop_count = 0
            self.last_stop_reason = None
            self.nonzero_count = 0
            self.watchdog_count = 0

        def ensure_target(self):
            return None

        def go2_target(self):
            return True

        def flush_outputs(self):
            self.publish_outputs(self.manager.drain_outputs())

        def publish_outputs(self, outputs):
            for item in outputs:
                kind = item["type"]
                require(kind in ("stop", "drive"), f"unexpected non-motion envelope {kind}")
                if kind == "stop":
                    self.stop_count += 1
                    self.last_stop_reason = item.get("reason")
                    self.velocity = (0.0, 0.0, 0.0)
                else:
                    self.last_drive_at = time.monotonic()
                    self.velocity = tuple(item["velocity"][k] for k in ("vx", "vy", "wz"))
                    self.nonzero_count += int(any(abs(v) > 1e-5 for v in self.velocity))
                trace("actuator", kind=kind, velocity=self.velocity, reason=item.get("reason"))

        def applied(self, now):
            # The production signed bridge independently limits command age.
            # This is an isolated actuator, with no robot socket or DDS topic.
            if any(self.velocity) and now - self.last_drive_at > 0.2:
                self.watchdog_count += 1
                self.velocity = (0.0, 0.0, 0.0)
                trace("synthetic_actuator_watchdog")
            return self.velocity

    port = ControlPort()
    rclpy.init(args=[])

    class Plant(Node):
        def __init__(self):
            super().__init__("robot_scope_agent")
            self.pose_lock = threading.RLock()
            self.pose = START
            self.odom_from_map = compose(ODOM_START, inverse(START))
            self.odom_enabled = True
            self.last_tick = time.monotonic()
            self.last_moved = self.last_tick
            self.velocity = (0.0, 0.0, 0.0)
            self.distance = 0.0
            self.obstacle = None
            self.obstacle_min_clearance = float("inf")
            self.contact_count = 0
            self.raw_count = self.raw_nonzero = 0
            self.raw_last_nonzero = 0.0
            self.raw_last_zero = 0.0
            self.raw_last = (0.0, 0.0, 0.0)
            self.recovery_count = 0
            self.statuses = {}
            self.costmaps = {}
            self.latest_path = None
            self.health = {}
            self.latest_scan = None
            self.last_map_tf_ns = 0
            self.last_scan_sent = 0.0
            self.graph_names = {}
            self.cloud_angle = np.linspace(-math.pi, math.pi, 720, endpoint=False)
            self.cloud_pub = self.create_publisher(PointCloud2, "/velodyne_points", 10)
            self.odom_pub = self.create_publisher(Odometry, "/Odometry", 10)
            self.controller_pub = self.create_publisher(Odometry, CONTROLLER_ODOM, 10)
            latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                                 durability=DurabilityPolicy.TRANSIENT_LOCAL)
            self.create_subscription(String, HEALTH, self.on_health, latched)
            self.create_subscription(Twist, RAW, self.on_raw, 10)
            self.create_subscription(Twist, RECOVERY, self.on_recovery, 10)
            self.create_subscription(LaserScan, "/scan", self.on_scan,
                                     QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
            self.create_subscription(GoalStatusArray, "/navigate_to_pose/_action/status",
                                     self.on_status, latched)
            self.create_subscription(NavPath, "/plan", self.on_path, 10)
            for key in ("global", "local"):
                self.create_subscription(OccupancyGrid, f"/{key}_costmap/costmap",
                                         lambda msg, key=key: self.on_costmap(key, msg), latched)
            self.tf = Buffer()
            self.listener = TransformListener(self.tf, self, spin_thread=False)
            self.gateway = NavigationRosGateway(
                port, node_getter=lambda: self, tick=lambda *_: None,
                graph_getter=lambda: {
                    topic: {"publishers": self.count_publishers(topic)}
                    for topic in ("/map", "/plan", "/tf", "/tf_static")
                },
                profile=control_profile, navigation_profile="go2-onboard",
            )
            self.gateway.setup(self)
            self.create_timer(0.04, self.tick)

        def on_raw(self, message):
            values = (message.linear.x, message.linear.y, message.angular.z)
            now = time.monotonic()
            self.raw_count += 1
            self.raw_last = values
            if any(abs(v) > 1e-5 for v in values):
                self.raw_nonzero += 1
                self.raw_last_nonzero = now
            else:
                self.raw_last_zero = now
            trace("native_cmd_vel", velocity=values)

        def on_recovery(self, message):
            if abs(message.linear.x) + abs(message.linear.y) + abs(message.angular.z) > 1e-5:
                self.recovery_count += 1
                trace("native_recovery_output_blocked")

        def on_health(self, message):
            self.health = json.loads(message.data)
            manual = self.health.get("manual_seed") or {}
            trace("runtime_health", odom_fresh=self.health.get("odom_fresh"),
                  cloud_fresh=self.health.get("cloud_fresh"), ready=self.health.get("ready"),
                  manual_seed=manual, map_tf_age_s=self.health.get("map_tf_age_s"))

        def on_scan(self, message):
            self.latest_scan = message

        def on_status(self, message):
            for status in message.status_list:
                identifier = bytes(status.goal_info.goal_id.uuid).hex()
                value = int(status.status)
                if self.statuses.get(identifier) != value:
                    trace("native_action_status", uuid=identifier, status=value)
                self.statuses[identifier] = value

        def on_path(self, message):
            self.latest_path = (
                time.monotonic(),
                [(pose.pose.position.x, pose.pose.position.y) for pose in message.poses],
            )

        def on_costmap(self, key, message):
            self.costmaps[key] = (time.monotonic(), message)

        def tick(self):
            now = time.monotonic()
            # Same ordering as RosAgent._control_tick, with synthetic
            # bridge/lowstate readiness and no hardware transport.
            with port.operation_lock:
                port.manager.set_readiness(bridge_ready=True, lowstate_ready=True)
                reason = self.gateway.reconcile_control_locked(now) or self.gateway.keepalive_locked(now)
                if reason:
                    trace("control_revoked", reason=reason)
                    self.gateway.deactivate(reason)
                port.publish_outputs(port.manager.tick())
                reason = self.gateway.reconcile_control_locked(now)
                if reason:
                    trace("control_revoked", reason=reason)
                    self.gateway.deactivate(reason)
                velocity = port.applied(now)
            with self.pose_lock:
                dt = min(0.12, now - self.last_tick)
                self.last_tick = now
                before = self.pose
                self.velocity = velocity
                delta = (velocity[0] * dt, velocity[1] * dt, velocity[2] * dt)
                self.pose = compose(before, delta)
                if any(abs(v) > 1e-5 for v in velocity):
                    self.last_moved = now
                    self.distance += math.dist(before[:2], self.pose[:2])
                clearance = contact_clearance(self.pose, self.obstacle)
                if self.obstacle:
                    self.obstacle_min_clearance = min(self.obstacle_min_clearance, clearance)
                if clearance < 0.0:
                    self.contact_count += 1
                odom = compose(self.odom_from_map, self.pose)
                stamp = self.get_clock().now().to_msg()
                if self.odom_enabled:
                    self.odom_pub.publish(self.odom_msg(stamp, odom, "camera_init", "body"))
                self.controller_pub.publish(self.odom_msg(stamp, odom, "odom", "base_link"))
                if now - self.last_scan_sent >= 0.079:
                    self.cloud_pub.publish(self.cloud_msg(stamp))
                    self.last_scan_sent = now
                trace("plant", map_pose=self.pose, odom_pose=odom, velocity=velocity,
                      distance_m=self.distance, clearance_m=clearance,
                      odom_enabled=self.odom_enabled)

        def odom_msg(self, stamp, pose, parent, child):
            message = Odometry()
            message.header.frame_id = parent
            message.header.stamp = stamp
            message.child_frame_id = child
            message.pose.pose.position.x, message.pose.pose.position.y = pose[:2]
            message.pose.pose.orientation.z = math.sin(pose[2] / 2)
            message.pose.pose.orientation.w = math.cos(pose[2] / 2)
            (message.twist.twist.linear.x, message.twist.twist.linear.y,
             message.twist.twist.angular.z) = self.velocity
            return message

        def cloud_msg(self, stamp):
            # Match the runtime's production static lidar offset.  The real
            # runtime, not this sensor, transforms and publishes the LaserScan.
            x, y, a = compose(self.pose, (0.25, 0.0, math.pi / 2))
            theta = self.cloud_angle + a
            dx, dy = np.cos(theta), np.sin(theta)
            distance = np.full_like(dx, np.inf)
            boundaries = [(ROOM[0], ROOM[1], ROOM[2], ROOM[3])]
            if self.obstacle:
                boundaries.append(self.obstacle)
            with np.errstate(divide="ignore", invalid="ignore"):
                for left, bottom, right, top in boundaries:
                    for edge in (left, right):
                        length = (edge - x) / dx
                        transverse = y + length * dy
                        valid = (length > 0) & (transverse >= bottom) & (transverse <= top)
                        distance = np.minimum(distance, np.where(valid, length, np.inf))
                    for edge in (bottom, top):
                        length = (edge - y) / dy
                        transverse = x + length * dx
                        valid = (length > 0) & (transverse >= left) & (transverse <= right)
                        distance = np.minimum(distance, np.where(valid, length, np.inf))
            valid = (distance >= 0.05) & (distance <= 9.9)
            d, bearing = distance[valid], self.cloud_angle[valid]
            xyz = np.column_stack((d * np.cos(bearing), d * np.sin(bearing), np.zeros(d.size))).astype("<f4")
            message = PointCloud2()
            message.header.stamp = stamp
            message.header.frame_id = "hesai_lidar"
            message.height = 1
            message.width = len(xyz)
            message.fields = [PointField(name=k, offset=i * 4, datatype=PointField.FLOAT32, count=1)
                              for i, k in enumerate("xyz")]
            message.point_step = 12
            message.row_step = message.width * message.point_step
            message.is_bigendian = False
            message.is_dense = True
            message.data = xyz.tobytes()
            return message

    plant = Plant()
    gateway = plant.gateway
    executor = SingleThreadedExecutor()
    executor.add_node(plant)
    spin_errors = []

    def spin():
        try:
            executor.spin()
        except BaseException:
            spin_errors.append(traceback.format_exc())

    thread = threading.Thread(target=spin, daemon=True)
    thread.start()
    input_path = output / "input_map"
    make_map(input_path)
    catalog = SavedMapCatalog([input_path], managed_roots=[input_path])
    map_row = catalog.list_snapshot()["maps"][0]
    map_identity = {"map_id": map_row["id"], "map_revision": map_row["revision"]}
    wrapper = native_launcher(repo, output)
    manager = NavigationJobManager(
        project_dir=repo,
        runtime_dir=output / "runtime",
        base_parameters_file=repo / "config/nav2_params_go2_humble.yaml",
        start_command=NavigationCommandSpec((str(wrapper), "--map-yaml", MAP_YAML_TOKEN,
                                             "--params-file", PARAMS_FILE_TOKEN), cwd=repo),
        map_snapshotter=catalog.snapshot_navigation_map, navigation_profile="go2-onboard",
    )

    def wait(description, predicate, timeout, *, check_process=True):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if spin_errors:
                raise RuntimeError(spin_errors[0])
            if check_process and manager.snapshot()["pipeline"]["state"] == "failed":
                raise RuntimeError(f"Nav2 process stopped: {manager.snapshot()['pipeline']}")
            value = predicate()
            if value:
                return value
            time.sleep(0.04)
        raise TimeoutError(f"{description}; health={plant.health.get('manual_seed')}, "
                           f"goal={gateway.state.get('goal')}, actual_pose={plant.pose}")

    def snapshot_goal():
        with gateway.lock:
            return dict(gateway.state["goal"])

    def manual():
        return plant.health.get("manual_seed") or {}

    def tf_lookup(target, source):
        try:
            return plant.tf.lookup_transform(target, source, Time())
        except TransformException:
            return None

    def tf_stamp(target, source):
        message = tf_lookup(target, source)
        return stamp_ns(message.header.stamp) if message else 0

    def zero_for(seconds):
        return (time.monotonic() - plant.last_moved >= seconds
                and not any(abs(v) > 1e-5 for v in plant.velocity))

    def verify_graph():
        nodes = sorted(f"{ns.rstrip('/')}/{name}" for name, ns in plant.get_node_names_and_namespaces())
        names = {
            topic: sorted({item.node_name for item in plant.get_publishers_info_by_topic(topic)})
            for topic in ("/tf", "/tf_static", RAW, "/scan", "/Odometry", CONTROLLER_ODOM)
        }
        require(not any("amcl" in n or "relocal" in n for n in nodes), f"unexpected localization node: {nodes}")
        require(all(n in nodes for n in ["/map_server", "/planner_server", "/controller_server",
                                        "/behavior_server", "/bt_navigator", "/lifecycle_manager_navigation",
                                        "/robot_scope_navigation_runtime"]), f"native nodes missing: {nodes}")
        require(names[RAW] == ["controller_server"], f"wrong command owner: {names[RAW]}")
        require(names["/tf"] == names["/tf_static"] == ["robot_scope_navigation_runtime"],
                f"wrong TF owners: {names}")
        return {"nodes": nodes, "publisher_owners": names}

    def start_job():
        wait("previous ROS graph cleanup", lambda: plant.count_publishers(HEALTH) == 0
             and plant.count_publishers("/tf") == 0 and plant.count_publishers(RAW) == 0,
             25, check_process=False)
        wait("simulated bridge and lowstate heartbeat",
             lambda: port.manager.snapshot()["ready"], 5, check_process=False)
        gateway.manual_start_preflight()
        ready_after = time.monotonic()
        report["isolation"]["native_launch_attempted"] = True
        start = manager.start(**map_identity,
                              parameters_revision=manager.snapshot()["parameters_revision"], mode=MODE)
        job_id = start["pipeline"]["job_id"]
        path = manager.runtime_dir / "jobs" / job_id
        preserve = output / ("job_" + job_id)
        preserve.mkdir()
        for filename in ("manual-navigation.json", "nav2_params.yaml", "map.yaml", "map.pgm"):
            shutil.copyfile(path / filename, preserve / filename)
        require(not (path / "operational-3d.json").exists(), "manual job unexpectedly has 3D bundle")
        job = {"id": job_id, "ready_after": ready_after,
               "parameters": start["parameter_evidence"]["generated_job_yaml"]}
        report.setdefault("jobs", []).append(job)
        wait("manual runtime with fresh synthetic inputs",
             lambda: (manual().get("job_id") == job_id and manual().get("inputs_ready")
                      and manual().get("state") == "waiting_initial_pose"
                      and manual().get("stopped_seconds", 0) >= 2.05
                      and gateway.prelocalization_snapshot(
                          **map_identity, mode=MODE, job_id=job_id,
                          ready_after=ready_after)["ready"]), 35)
        status = gateway.activate(**map_identity, map_name="A3 synthetic room",
                                  mode=MODE, job_id=job_id, ready_after=ready_after)
        require(not status["safety"]["can_send_goal"], "goal opened before explicit seed")
        return job_id

    def seed(job, pose):
        native_generation_before = manual()["seed_generation"]
        odom = compose(plant.odom_from_map, plant.pose)
        source = manual()
        status = gateway.set_initial_pose(
            **map_identity, x=pose[0], y=pose[1], yaw=pose[2], job_id=job,
            seed_generation=source["seed_generation"], source_epoch=source["source_epoch"],
        )
        receipt = status["manual_seed"]["receipt"]
        require(receipt["accepted"] and receipt["seed_generation"] > native_generation_before,
                f"native seed receipt missing: {receipt}")
        wait("independent tf2 map/base and valid action gate",
             lambda: tf_stamp("map", "base_link") >= int(receipt["odometry_stamp_ns"])
             and gateway.runtime_snapshot()["safety"]["can_send_goal"], 40)
        observed = pose_from_transform(tf_lookup("map", "base_link").transform)
        odom_tf = pose_from_transform(tf_lookup("odom", "base_link").transform)
        map_odom_tf = pose_from_transform(tf_lookup("map", "odom").transform)
        expected_map_odom = compose(pose, inverse(odom))
        require(max(error(odom_tf, odom)) < 0.02, f"odom differs: {odom_tf} vs {odom}")
        require(max(error(observed, pose)) < 0.02, f"seed map pose differs: {observed} vs {pose}")
        require(max(error(map_odom_tf, expected_map_odom)) < 0.02, "unexpected map-to-odom transform")
        return {
            "job_id": job, "fixture_odom_pose": odom, "seed_map_pose": pose,
            "tf_map_base": observed, "tf_odom_base": odom_tf, "tf_map_odom": map_odom_tf,
            "runtime_receipt": receipt,
            "runtime_tf_readback_stamp_ns": status["manual_seed"]["tf_readback_stamp_ns"],
            "independent_tf2_stamp_ns": tf_stamp("map", "base_link"),
        }

    def send(target):
        validated = manager.validate_active_pose(**map_identity, x=target[0], y=target[1], yaw=target[2])
        status = gateway.send_goal(**map_identity, **validated, seed_generation=manual()["seed_generation"])
        goal_id = status["goal"]["goal_id"]

        def live_handle():
            with gateway.lock:
                handle = gateway._navigation_goal_handle
                state = gateway.state["goal"]["state"]
                return bytes(handle.goal_id.uuid).hex() if state == "active" and handle else None

        identifier = wait("Nav2 goal accepted and active", live_handle, 12)
        return goal_id, identifier

    def successful_goal(target):
        before, initial_commands = plant.pose, plant.raw_nonzero
        goal_id, identifier = send(target)
        state = wait("native successful goal result",
                     lambda: (value if (value := snapshot_goal())["state"] in
                              ("succeeded", "failed", "canceled") else None), 65)
        require(state["state"] == "succeeded", f"unexpected Nav2 action result: {state}")
        wait("native action status succeeded", lambda: plant.statuses.get(identifier) == GoalStatus.STATUS_SUCCEEDED, 6)
        wait("native goal leaves actuator stopped", lambda: zero_for(.4), 4)
        measured = plant.pose
        distance, heading_error = error(measured, target)
        limits = manager.parameters_snapshot()["values"]
        require(distance <= limits["xy_goal_tolerance"] + 0.025
                and heading_error <= limits["yaw_goal_tolerance"] + 0.04, "independent pose misses goal tolerance")
        require(math.dist(measured[:2], before[:2]) >= .5 and plant.raw_nonzero > initial_commands,
                "simulated actuator did not integrate native movement")
        require(plant.contact_count == 0, "simulated obstacle contact")
        return {"target": target, "ground_truth": measured, "xy_error_m": distance,
                "yaw_error_rad": heading_error, "native_action_uuid": identifier,
                "native_action_status": plant.statuses[identifier], "gateway_goal_id": goal_id,
                "native_nonzero_commands": plant.raw_nonzero - initial_commands}

    def cancel_case():
        before = plant.pose
        target = (min(before[0] + 3.0, 9.0), before[1], before[2])
        goal_id, identifier = send(target)
        wait("moving prior to explicit cancel", lambda: math.dist(plant.pose[:2], before[:2]) >= .24, 18)
        at_cancel = plant.pose
        stop_count = port.stop_count
        gateway.cancel_goal(goal_id=goal_id)
        wait("native action canceled", lambda: plant.statuses.get(identifier) == GoalStatus.STATUS_CANCELED, 12)
        wait("gateway reports canceled", lambda: snapshot_goal()["state"] == "canceled", 5)
        wait("actuator stopped after cancel", lambda: zero_for(.5), 5)
        after = plant.pose
        require(port.stop_count > stop_count and math.dist(at_cancel[:2], after[:2]) < .18,
                "cancel did not stop simulated actuator in bound")
        return {"target": target, "cancel_pose": at_cancel, "stopped_pose": after,
                "stop_displacement_m": math.dist(at_cancel[:2], after[:2]),
                "native_action_uuid": identifier, "native_action_status": plant.statuses[identifier]}

    def occupancy_at(frame, point):
        packet = plant.costmaps.get(frame)
        if not packet:
            return None
        when, msg = packet
        q = msg.info.origin.orientation
        p = msg.info.origin.position
        rel = compose(inverse((p.x, p.y, yaw(q))), (point[0], point[1], 0.0))
        r = msg.info.resolution
        data = []
        for yy in range(-1, 2):
            for xx in range(-1, 2):
                u, v = math.floor(rel[0] / r) + xx, math.floor(rel[1] / r) + yy
                if 0 <= u < msg.info.width and 0 <= v < msg.info.height:
                    data.append(int(msg.data[v * msg.info.width + u]))
        return (when, max(data)) if data else None

    def obstacle_case():
        before = plant.pose
        obstacle = (before[0] + 1.25, before[1] - 0.55,
                    before[0] + 1.55, before[1] + 0.55)
        target = (before[0] + 3.15, before[1], 0.0)
        probes = [(obstacle[0] + 0.02, before[1] + v) for v in (-.4, -.2, 0.0, .2, .4)]

        def global_probe():
            values = [occupancy_at("global", p) for p in probes]
            return max((v for v in values if v), key=lambda v: v[1], default=None)

        clear = wait("unoccupied global costmap at obstacle position",
                     lambda: (data if (data := global_probe()) and data[1] <= 20 else None), 10)
        raw_before, stopped_before = plant.raw_nonzero, port.watchdog_count
        with plant.pose_lock:
            plant.obstacle = obstacle
            plant.obstacle_min_clearance = float("inf")
        introduced_at = time.monotonic()
        try:
            marked = wait("native /scan obstacle marked by Nav2 global costmap",
                          lambda: (data if (data := global_probe()) and data[0] > introduced_at
                                   and data[1] >= 99 else None), 14)
            goal_id, identifier = send(target)
            state = wait("Nav2 avoided obstacle or commanded a sustained stop",
                         lambda: (value if (value := snapshot_goal())["state"] in ("succeeded", "failed")
                                  else {"state": "controller_stop"} if (
                                      plant.raw_nonzero > raw_before
                                      and math.dist(plant.pose[:2], before[:2]) >= .15
                                      and zero_for(1.75)
                                      and time.monotonic() - plant.raw_last_nonzero >= 1.7
                                      and plant.raw_last_zero > plant.raw_last_nonzero
                                  ) else None), 65)
            clearance = plant.obstacle_min_clearance
            require(clearance > 0 and plant.contact_count == 0, f"obstacle contact: {clearance:.3f}m")
            require(plant.raw_nonzero > raw_before and port.watchdog_count == stopped_before,
                    "result not attributable to native controller motion")
            if state["state"] == "succeeded":
                require(error(plant.pose, target)[0] <= .375, "native avoidance ended outside goal tolerance")
                outcome = "AVOIDED"
            else:
                require(math.dist(plant.pose[:2], before[:2]) >= .15, "no approach before controller stop")
                wait("stationary actuator after obstacle response", lambda: zero_for(1.0), 5)
                require(plant.raw_last_zero > plant.raw_last_nonzero, "no native zero command after approach")
                outcome = "SAFE_STOP"
            native_status = plant.statuses.get(identifier)
            terminal_pose = plant.pose
            if snapshot_goal()["state"] in ("pending", "active", "canceling"):
                gateway.cancel_goal(goal_id=goal_id)
                wait("cancel after obstacle case", lambda: snapshot_goal()["state"] == "canceled", 12)
            return {"result": outcome, "obstacle_rectangle": obstacle, "goal": target,
                    "costmap_value_before": clear[1], "costmap_value_after": marked[1],
                    "costmap_mark_latency_s": marked[0] - introduced_at,
                    "terminal_pose": terminal_pose, "native_action_uuid": identifier,
                    "native_action_status_before_cleanup": native_status,
                    "minimum_footprint_clearance_m": clearance, "contacts": plant.contact_count,
                    "native_nonzero_commands": plant.raw_nonzero - raw_before,
                    "recovery_nonzero_messages_ignored": plant.recovery_count}
        finally:
            with plant.pose_lock:
                plant.obstacle = None

    def outage_case():
        before = plant.pose
        # Move toward room center after avoidance, with no contact geometries.
        target = (2.0 if before[0] > 5.0 else 8.0, min(max(before[1], 2.5), 6.5), 0.0)
        # Real costmap clear request after removing the synthetic obstacle.
        gateway.clear_costmaps(scope="both")
        wait("clear-costmap service finished",
             lambda: (gateway.state.get("clear_costmaps") or {}).get("state") not in
                     (None, "idle", "pending", "clearing", "running"), 10)
        require(gateway.state["clear_costmaps"]["state"] == "succeeded", "costmap clear failed")
        old_generation = manual()["seed_generation"]
        _, identifier = send(target)
        wait("moving when FAST-LIO odometry is interrupted",
             lambda: math.dist(plant.pose[:2], before[:2]) >= .22, 22)
        cut_pose, cut_time = plant.pose, time.monotonic()
        old_stop_count = port.stop_count
        plant.odom_enabled = False
        try:
            invalidated = wait("runtime invalidates anchor on odometry gap",
                               lambda: (value if (value := manual()).get("state") == "reseed_required"
                                        and value["seed_generation"] > old_generation else None), 5)
            wait("gateway closes lease and stops actuator",
                 lambda: not gateway.state["active"] and port.stop_count > old_stop_count and zero_for(.3), 5)
            stopped, verified_stop_time = plant.pose, time.monotonic()
            require(math.dist(stopped[:2], cut_pose[:2]) < .25, "actuator did not stop within outage bound")
            wait("Nav2 cancels exact interrupted goal",
                 lambda: plant.statuses.get(identifier) == GoalStatus.STATUS_CANCELED, 8)
            withheld_ns = tf_stamp("map", "odom")
            require(withheld_ns, "expected earlier map-to-odom sample in tf2")
        finally:
            plant.odom_enabled = True
        wait("odometry recovered without reviving manual alignment",
             lambda: manual().get("state") == "reseed_required" and manual().get("inputs_ready"), 12)
        time.sleep(.6)
        require(tf_stamp("map", "odom") == withheld_ns, "old map-to-odom TF resumed")
        require(not gateway.runtime_snapshot()["safety"]["can_send_goal"], "goal reopened after recovery")
        try:
            gateway.send_goal(**map_identity, x=target[0], y=target[1], yaw=target[2], seed_generation=old_generation)
        except ControlError as exc:
            stale_goal_rejection = type(exc).__name__
        else:
            raise AssertionError("old seed dispatched a goal after odometry recovery")
        return {"goal": target, "cut_pose": cut_pose, "stopped_pose": stopped,
                "stop_displacement_m": math.dist(stopped[:2], cut_pose[:2]),
                "runtime_invalidation": invalidated, "gateway_stop_reason": gateway.state["deactivation_reason"],
                "native_action_uuid": identifier, "native_action_status": plant.statuses[identifier],
                "elapsed_until_verified_stop_s": verified_stop_time - cut_time,
                "old_tf_stamp_unchanged_ns": withheld_ns, "stale_goal_rejection": stale_goal_rejection}

    def record(name, operation, *, cleanup=False):
        trace("case_start", name=name)
        try:
            result = operation()
        except Exception:
            result = {"status": "FAIL", "error": traceback.format_exc()}
            print(f"FAIL {name}\n{result['error']}", flush=True)
            if cleanup:
                try:
                    goal = snapshot_goal()
                    if goal["state"] in ("pending", "active", "canceling"):
                        gateway.cancel_goal(goal_id=goal["goal_id"])
                        wait("case failure cleanup", lambda: snapshot_goal()["state"] == "canceled", 8)
                except Exception:
                    result["cleanup_error"] = traceback.format_exc()
        else:
            result = {"status": "PASS", **result}
            print(f"PASS {name} {json.dumps(result, allow_nan=False)}", flush=True)
        report.setdefault("cases", {})[name] = result
        trace("case_end", name=name, status=result["status"])
        (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        return result

    def restart_and_reseed():
        manager.stop()
        with plant.pose_lock:
            current = plant.pose
            reset_odom = (4.7, 5.2, -0.45)
            plant.odom_from_map = compose(reset_odom, inverse(current))
        new_job = start_job()
        initial = seed(new_job, current)
        x = current[0] - 1.1 if current[0] > 4.0 else current[0] + 1.1
        target = (x, current[1], math.pi if x < current[0] else 0.0)
        movement = successful_goal(target)
        return {"operator_prepared_new_job": True, "explicit_new_seed": initial,
                "new_native_goal": movement}

    try:
        # All representatively independent scenarios are attempted. A seed
        # or readiness failure is a blocked dependent case, not a pass.
        first_job = start_job()
        record("nonzero_odom_seed", lambda: seed(first_job, START))
        record("native_graph", verify_graph)
        record("native_goal", lambda: successful_goal((3.6, 3.0, 0.0)), cleanup=True)
        record("native_cancel", cancel_case, cleanup=True)
        record("native_obstacle", obstacle_case, cleanup=True)
        outage = record("odom_outage", outage_case, cleanup=True)
        if outage["status"] != "PASS" and gateway.state.get("active"):
            gateway.deactivate("navigation_stop")
        record("explicit_reseed", restart_and_reseed, cleanup=True)
        report["contact_count"] = plant.contact_count
        report["recovery_output_messages_ignored"] = plant.recovery_count
        report["synthetic_actuator_watchdog_count"] = port.watchdog_count
        report["pass"] = all(case["status"] == "PASS" for case in report["cases"].values())
    finally:
        try:
            gateway.deactivate("navigation_stop")
            manager.stop()
            report["manager_final_state"] = manager.snapshot()["pipeline"]
            report["manager_logs"] = manager.snapshot()["logs"]
        finally:
            executor.shutdown(timeout_sec=3)
            thread.join(timeout=3)
            plant.destroy_node()
            rclpy.shutdown()
            trace_file.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha", default=SHA)
    options = parser.parse_args()
    output = options.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    require(not (output / "report.json").exists(), "output directory must be fresh")
    report = {
        "sha": options.sha,
        "backend": "native_humble_nav2_and_product_runtime_with_synthetic_plant",
        "platform": platform.platform(),
        "cases": {},
        "synthetic": ["lidar geometry", "relative and controller odometry", "bridge/lowstate readiness",
                      "actuator dynamics"],
        "not_exercised": ["physical robot", "signed hardware bridge", "hardware launcher preflight",
                          "FAST-LIO estimator", "dashboard HTTP/browser"],
    }
    try:
        run(options.repo.resolve(), output, options.sha, report)
    except BaseException:
        report["pass"] = False
        report["fatal"] = traceback.format_exc()
        print(report["fatal"], file=sys.stderr, flush=True)
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
