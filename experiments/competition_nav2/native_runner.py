"""Native ROS adapter for the planar plant. Import only inside network-none Humble.

No replacement planner/controller is implemented here. Nav2 supplies every raw
navigation command. Explicit fault probes are labeled, never counted as native.
"""

import json
import hashlib
import math
from pathlib import Path
import resource
import sys
import time
import xml.etree.ElementTree as ET

from configure import NODES, PLUGINS
from footprint_coverage import COVERAGE_VARIANTS, OMNI_VARIANTS, coverage
from core import Boundary, Command, LIMITS, propagate, swept_poses
from fixtures import make_world, digest
from preflight import require_isolated
from humble_executor import metadata_executor_type
from observations import grid_payload
from omni import OmniBoundary, OmniCommand, propagate_omni, swept_omni


def publisher_owners_match(observed, owner, endpoint_count=1):
    """Humble TimedBehavior allocates one publisher per loaded behavior plugin."""
    return sorted(observed) == [owner] * endpoint_count


def goal_uuid_to_json(uuid):
    values = [int(value) for value in uuid]
    if len(values) != 16 or any(not 0 <= value <= 255 for value in values):
        raise ValueError("action UUID must contain 16 bytes")
    return values


def plugin_library_names(share, plugin):
    """Use installed plugin exports; package and shared-library names can differ."""
    names = set()
    for xml in Path(share).rglob("*.xml"):
        root = ET.parse(xml).getroot()
        for library in root.iter("library"):
            if any(
                plugin in (cls.get("type"), cls.get("name"))
                for cls in library.iter("class")
            ):
                base = Path(library.attrib["path"]).name
                names.add(
                    (base if base.startswith("lib") else "lib" + base)
                    + (".so" if ".so" not in base else "")
                )
    if not names:
        raise RuntimeError("installed plugin library export missing: " + plugin)
    return names


def main(directory):
    isolation = require_isolated()  # before rclpy.init, no host ROS graph access
    import rclpy
    from rclpy.action import ActionClient
    from rclpy.clock import Clock, ClockType
    from rclpy.node import Node
    from rclpy.executors import SingleThreadedExecutor, await_or_execute
    from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
    from ament_index_python.packages import get_package_share_directory
    from action_msgs.msg import GoalStatusArray
    from geometry_msgs.msg import TransformStamped, Twist, PointStamped
    from lifecycle_msgs.srv import GetState
    from nav2_msgs.action import ComputePathToPose, NavigateToPose, Spin
    from nav2_msgs.srv import ManageLifecycleNodes
    from nav_msgs.msg import Odometry, OccupancyGrid, Path as NativePath
    from rcl_interfaces.srv import GetParameters
    from rosgraph_msgs.msg import Clock as ClockMessage
    from sensor_msgs.msg import LaserScan
    from tf2_msgs.msg import TFMessage
    import yaml

    directory = Path(directory)
    fixture = json.loads((directory / "fixture.json").read_text())
    run = json.loads((directory / "run.json").read_text())
    expected = yaml.safe_load((directory / "params.yaml").read_text())
    omni = run["variant"] in OMNI_VARIANTS
    zero_command = (0.0, 0.0, 0.0) if omni else (0.0, 0.0)
    command_type = OmniCommand if omni else Command

    class Plant(Node):
        def __init__(self):
            super().__init__("bench_plant", namespace="c3_nav2")
            self.world = make_world(fixture)
            if hasattr(self.world, "start_sensor"):
                self.world.start_sensor()
            gate_type = OmniBoundary if omni else Boundary
            self.boundary = gate_type(fixture.get("sensor_ttl_s", LIMITS["sensor_ttl"]))
            self.pose = tuple(fixture["start"])
            self.sim_t = 0.0
            self.goal_start = None
            self.global_map_observed = False
            self.last_tick = time.monotonic()
            self.next_scan = 0.0
            self.pending_scans = []
            self.sequence = 0
            self.previous_output = zero_command
            self.raw_count = {"controller_server": 0, "behavior_server": 0}
            self.active_actions = {"controller_server": False, "behavior_server": False}
            self.command_owner = None
            self.recovery_nonzero = 0
            self.delayed_probe = None
            self.trace = (directory / "trace.jsonl").open("w")
            self.raw = (directory / "raw_commands.jsonl").open("w")
            self.scans = (directory / "scans.jsonl").open("w")
            self.observations = (directory / "observations.jsonl").open("w")
            self.appeared = set()
            self.action_events = []
            self.deadline_miss = 0
            self.periods = []
            self.collision_count = 0
            self.boundary_count = 0
            self.path_length = 0.0
            self.min_clearance = math.inf
            self.zero_since = time.monotonic()
            self.hold_nonzero = 0
            self.graph_checked = False
            self.graph_snapshots = []
            self.start_cpu = time.process_time()
            self.start_wall = time.monotonic()
            self.clock_pub = self.create_publisher(ClockMessage, "/clock", 10)
            self.tf_pub = self.create_publisher(TFMessage, "tf", 10)
            static_qos = QoSProfile(
                depth=1,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
                reliability=ReliabilityPolicy.RELIABLE,
            )
            self.static_pub = self.create_publisher(TFMessage, "tf_static", static_qos)
            self.odom_pub = self.create_publisher(Odometry, "odom", 10)
            self.scan_pub = self.create_publisher(LaserScan, "scan", 10)
            self.final_pub = self.create_publisher(Twist, "sim_actuator_cmd", 10)
            self.subscriptions_raw = []
            self.subscriptions_observed = [
                self.create_subscription(
                    OccupancyGrid,
                    "global_costmap/costmap",
                    self.observe_costmap,
                    static_qos,
                ),
                self.create_subscription(NativePath, "plan", self.observe_path, 10),
            ]
            if fixture.get("world_kind") == "d0_shared":
                # Read-only native diagnostics: no replacement path or command.
                self.subscriptions_observed += [
                    self.create_subscription(
                        OccupancyGrid,
                        "local_costmap/costmap",
                        lambda msg: self.observe_costmap(msg, "local_costmap"),
                        static_qos,
                    ),
                    self.create_subscription(
                        NativePath,
                        "lookahead_collision_arc",
                        lambda msg: self.observe_path(msg, "rpp_collision_arc"),
                        10,
                    ),
                    self.create_subscription(
                        PointStamped,
                        "lookahead_point",
                        lambda msg: self.observe(
                            "rpp_carrot",
                            msg,
                            point=[msg.point.x, msg.point.y],
                            receipt_pose=list(self.pose),
                        ),
                        10,
                    ),
                ]

            if run["variant"] in COVERAGE_VARIANTS:
                self.tf_observer = self.create_subscription(
                    TFMessage, "/tf", self.observe_tf, 100
                )

            def bind_callback(owner):
                def callback(msg, info):
                    self.receive_command(msg, info, owner)

                return callback

            for owner in self.raw_count:
                sub = self.create_subscription(
                    Twist, "raw/" + owner, bind_callback(owner), 1
                )
                sub.c3_with_metadata = True
                self.subscriptions_raw.append(sub)

            def bind_status(owner):
                def callback(msg):
                    self.active_actions[owner] = any(
                        s.status in (1, 2, 3) for s in msg.status_list
                    )

                return callback

            for owner, action in [
                ("controller_server", "follow_path"),
                ("behavior_server", "spin"),
            ]:
                self.subscriptions_raw.append(
                    self.create_subscription(
                        GoalStatusArray,
                        action + "/_action/status",
                        bind_status(owner),
                        static_qos,
                    )
                )
            self.timer = self.create_timer(
                0.05, self.tick, clock=Clock(clock_type=ClockType.STEADY_TIME)
            )

        def stamp(self, seconds):
            from builtin_interfaces.msg import Time

            return Time(sec=int(seconds), nanosec=int((seconds - int(seconds)) * 1e9))

        def observe_tf(self, msg):
            for transform in msg.transforms:
                if transform.child_frame_id in ("odom", "base_link"):
                    t, q = transform.transform.translation, transform.transform.rotation
                    self.observe(
                        "tf",
                        transform,
                        child_frame=transform.child_frame_id,
                        translation=[t.x, t.y, t.z],
                        quaternion=[q.x, q.y, q.z, q.w],
                    )

        def observe(self, kind, msg, **data):
            source = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
            self.observations.write(
                json.dumps(
                    dict(
                        kind=kind,
                        sim_t=self.sim_t,
                        receipt_monotonic=time.monotonic(),
                        source_sim_s=source,
                        source_elapsed_s=source - self.goal_start
                        if self.goal_start is not None
                        else -1.0,
                        frame=msg.header.frame_id,
                        **data,
                    )
                )
                + "\n"
            )

        def observe_costmap(self, msg, kind="costmap"):
            if kind == "costmap":
                self.global_map_observed = True
            self.observe(
                kind,
                msg,
                width=msg.info.width,
                height=msg.info.height,
                resolution=msg.info.resolution,
                origin=[msg.info.origin.position.x, msg.info.origin.position.y],
                data_zlib_base64=grid_payload(msg.data),
            )

        def observe_path(self, msg, kind="path"):
            self.observe(
                kind,
                msg,
                points=[[p.pose.position.x, p.pose.position.y] for p in msg.poses],
                z=[p.pose.position.z for p in msg.poses],
                quaternions=[
                    [
                        p.pose.orientation.x,
                        p.pose.orientation.y,
                        p.pose.orientation.z,
                        p.pose.orientation.w,
                    ]
                    for p in msg.poses
                ],
                # RPP arc default orientation does not encode projected heading.
                receipt_pose=list(self.pose),
            )

        def receive_command(self, msg, info, owner):
            now, wall_ns = time.monotonic(), time.time_ns()
            stamp = int(info["source_timestamp"])
            age = (wall_ns - stamp) / 1e9 if stamp > 0 else math.inf
            self.sequence += 1
            self.raw_count[owner] += 1
            nonzero = any(
                abs(x) > 1e-9
                for x in (
                    msg.linear.x,
                    msg.linear.y,
                    msg.linear.z,
                    msg.angular.x,
                    msg.angular.y,
                    msg.angular.z,
                )
            )
            if owner == "behavior_server" and nonzero:
                self.recovery_nonzero += 1
            if any(
                abs(x) > 1e-9
                for x in (
                    (0.0 if omni else msg.linear.y),
                    msg.linear.z,
                    msg.angular.x,
                    msg.angular.y,
                )
            ):
                self.boundary.stop("UNSUPPORTED_TWIST_AXIS")
            # DDS source timestamp uses the same host realtime clock in this container.
            # Reject unavailable, future, or delayed source stamps instead of re-stamping.
            accepted = False
            owners = [name for name, active in self.active_actions.items() if active]
            if not self.boundary.hold and len(owners) > 1:
                self.boundary.stop("SIM_COMMAND_OWNER_CONFLICT")
            if (
                owners == [owner]
                and self.command_owner != owner
                and not self.boundary.hold
            ):
                self.command_owner = owner
                self.boundary.epoch += 1
                self.boundary.command = None
                self.boundary.output = zero_command
                self.boundary.release_at = now
            if not 0 <= age <= LIMITS["command_ttl"]:
                self.boundary.stop("DDS_SOURCE_AGE_INVALID")
            elif owners == [owner]:
                accepted = self.boundary.accept(
                    command_type(
                        self.sequence,
                        self.boundary.epoch,
                        now - age,
                        now,
                        msg.linear.x,
                        msg.angular.z,
                        **({"vy": msg.linear.y} if omni else {}),
                    ),
                    now,
                )
            self.raw.write(
                json.dumps(
                    dict(
                        sim_t=self.sim_t,
                        receipt_monotonic=now,
                        source_timestamp_ns=stamp,
                        dds_received_timestamp_ns=int(info["received_timestamp"]),
                        source_age_s=age if math.isfinite(age) else None,
                        owner=owner,
                        v=msg.linear.x,
                        w=msg.angular.z,
                        **({"vy": msg.linear.y} if omni else {}),
                        accepted=accepted,
                        epoch=self.boundary.epoch,
                        fault=self.boundary.fault,
                        held=self.boundary.hold,
                        active_action_owners=owners,
                        origin="native_nav2",
                    ),
                    allow_nan=False,
                )
                + "\n"
            )

        def tick(self):
            now = time.monotonic()
            gap = now - self.last_tick
            self.last_tick = now
            self.periods.append(gap)
            self.deadline_miss += int(gap > 0.075)
            if self.goal_start is not None and gap > 0.3:
                self.boundary.stop("PLANT_WATCHDOG")
            dt = 0.05
            before = self.pose
            scene_time = (
                0.0 if self.goal_start is None else self.sim_t - self.goal_start
            )
            # Integrate actual previous simulated actuator command, never desired/raw input.
            applied = self.previous_output
            v, w = applied[0], applied[-1]
            vy = applied[1] if omni else 0.0
            samples = (
                swept_omni(before, v, vy, w, dt, self.world.radius)
                if omni
                else swept_poses(before, v, w, dt, radius=self.world.radius)
            )
            if any(self.world.collision(p, scene_time) for p in samples):
                self.collision_count += 1
                self.boundary.stop("FOOTPRINT_CONTACT")
            if any(self.world.boundary_violation(p) for p in samples):
                self.boundary_count += 1
            self.pose = (
                propagate_omni(before, v, vy, w, dt)
                if omni
                else propagate(before, v, w, dt)
            )
            self.path_length += math.dist(before[:2], self.pose[:2])
            self.min_clearance = min(
                self.min_clearance,
                *(self.world.clearance(p, scene_time) for p in samples),
            )
            self.sim_t += dt
            elapsed = 0.0 if self.goal_start is None else self.sim_t - self.goal_start
            for index, obstacle in enumerate(fixture["obstacles"]):
                if elapsed >= obstacle["appears_s"] and index not in self.appeared:
                    self.appeared.add(index)
                    self.observations.write(
                        json.dumps(
                            dict(
                                kind="appearance",
                                obstacle=index,
                                sim_t=self.sim_t,
                                elapsed_s=elapsed,
                            )
                        )
                        + "\n"
                    )
            clock = ClockMessage()
            clock.clock = self.stamp(self.sim_t)
            self.clock_pub.publish(clock)
            identity = TransformStamped()
            identity.header.stamp = clock.clock
            identity.header.frame_id, identity.child_frame_id = "map", "odom"
            identity.transform.rotation.w = 1.0
            self.static_pub.publish(TFMessage(transforms=[identity]))
            if fixture.get("sensor_frame"):
                sensor_tf = TransformStamped()
                sensor_tf.header.stamp = clock.clock
                sensor_tf.header.frame_id, sensor_tf.child_frame_id = (
                    "base_link",
                    fixture["sensor_frame"],
                )
                sensor_tf.transform.rotation.w = 1.0
                self.static_pub.publish(TFMessage(transforms=[identity, sensor_tf]))
            transform = TransformStamped()
            transform.header.stamp = clock.clock
            transform.header.frame_id, transform.child_frame_id = "odom", "base_link"
            transform.transform.translation.x, transform.transform.translation.y = (
                self.pose[:2]
            )
            transform.transform.rotation.z = math.sin(self.pose[2] / 2)
            transform.transform.rotation.w = math.cos(self.pose[2] / 2)
            self.tf_pub.publish(TFMessage(transforms=[transform]))
            odom = Odometry()
            odom.header = transform.header
            odom.child_frame_id = "base_link"
            odom.pose.pose.position.x, odom.pose.pose.position.y = self.pose[:2]
            odom.pose.pose.orientation = transform.transform.rotation
            odom.twist.twist.linear.x, odom.twist.twist.angular.z = v, w
            odom.twist.twist.linear.y = vy
            self.odom_pub.publish(odom)
            if (
                self.sim_t + (1e-9 if fixture.get("d0_bundle") else 0.0)
                >= self.next_scan
            ):
                self.next_scan = self.sim_t + fixture["sensor_period_s"]
                if self.goal_start is None or elapsed < fixture.get(
                    "sensor_dropout_s", math.inf
                ):
                    msg = LaserScan()
                    msg.header.frame_id, msg.header.stamp = (
                        fixture.get("sensor_frame", "base_link"),
                        clock.clock,
                    )
                    msg.angle_min = -math.pi
                    msg.angle_increment = 2 * math.pi / fixture["scan_beams"]
                    msg.angle_max = math.pi - msg.angle_increment
                    msg.range_min, msg.range_max = 0.02, 8.0
                    msg.scan_time = fixture["sensor_period_s"]
                    msg.ranges = self.world.scan(self.pose, elapsed)
                    self.pending_scans.append(
                        (
                            now + fixture["sensor_delay_s"],
                            now,
                            msg,
                            list(self.pose),
                            elapsed,
                            getattr(self.world, "last_observation", None),
                        )
                    )
            if fixture.get("d0_bundle"):
                now = (
                    time.monotonic()
                )  # Include synchronous sensor computation in source/receipt age.
            while self.pending_scans and self.pending_scans[0][0] <= now:
                (
                    _,
                    source_mono,
                    scan,
                    source_pose,
                    source_elapsed,
                    sensor_observation,
                ) = self.pending_scans.pop(0)
                self.scan_pub.publish(scan)
                self.boundary.sensor(now, now - source_mono)
                self.scans.write(
                    json.dumps(
                        dict(
                            sim_t=self.sim_t,
                            source_sim_s=scan.header.stamp.sec
                            + scan.header.stamp.nanosec / 1e9,
                            receipt_monotonic=now,
                            source_age_s=now - source_mono,
                            min_range_m=min(scan.ranges),
                            source_pose=source_pose,
                            source_elapsed_s=source_elapsed,
                            ranges=list(scan.ranges),
                            sensor_observation=sensor_observation,
                        )
                    )
                    + "\n"
                )
            window = fixture.get("hold_window_s", [])
            held = self.goal_start is None or bool(
                window and window[0] <= elapsed < window[1]
            )
            self.boundary.set_hold(held, now)
            if (
                fixture.get("delayed_command_at_s", math.inf) <= elapsed
                and self.delayed_probe is None
            ):
                # Separate fault injection, never counted among native controller commands.
                accepted = self.boundary.accept(
                    command_type(
                        self.sequence + 1,
                        self.boundary.epoch - 1,
                        now - 1.0,
                        now,
                        0.18,
                        0.1,
                    ),
                    now,
                )
                self.delayed_probe = dict(
                    origin="synthetic_fault_probe",
                    accepted=accepted,
                    elapsed_s=elapsed,
                    old_epoch=self.boundary.epoch - 1,
                )
            output = self.boundary.step(now, dt)
            self.previous_output = output
            twist = Twist()
            twist.linear.x, twist.angular.z = output[0], output[-1]
            twist.linear.y = output[1] if omni else 0.0
            self.final_pub.publish(twist)
            zero = output == zero_command
            self.hold_nonzero += int(held and not zero)
            if not zero:
                self.zero_since = now
            self.trace.write(
                json.dumps(
                    dict(
                        sim_t=self.sim_t,
                        elapsed_s=elapsed,
                        pose=list(self.pose),
                        applied_previous=list(applied),
                        actuator=list(output),
                        held=held,
                        reason=self.boundary.reason,
                        raw_sequence=self.sequence,
                        epoch=self.boundary.epoch,
                        monotonic=now,
                        command_source_age_s=(
                            now - self.boundary.command.sent
                            if self.boundary.command
                            else None
                        ),
                        command_receipt_age_s=(
                            now - self.boundary.command.received
                            if self.boundary.command
                            else None
                        ),
                        sensor_source_age_s=(
                            now
                            - self.boundary.scan_received
                            + self.boundary.scan_source
                            if self.boundary.scan_received is not None
                            else None
                        ),
                        sensor_receipt_age_s=(
                            now - self.boundary.scan_received
                            if self.boundary.scan_received is not None
                            else None
                        ),
                        published_ros=dict(
                            clock_s=self.sim_t,
                            tf_stamp_s=self.sim_t,
                            odom_stamp_s=self.sim_t,
                            tf_frames=["map", "odom", "base_link"],
                        ),
                        action_owners=dict(self.active_actions),
                        wall_gap_s=gap,
                        collision_count=self.collision_count,
                        boundary_count=self.boundary_count,
                    ),
                    allow_nan=False,
                )
                + "\n"
            )

        def wait(self, future, timeout=10.0):
            deadline = time.monotonic() + timeout
            while rclpy.ok() and not future.done() and time.monotonic() < deadline:
                rclpy.spin_once(self, executor=executor, timeout_sec=0.02)
            if not future.done():
                raise TimeoutError("ROS response deadline exceeded")
            result = future.result()
            if result is None:
                raise RuntimeError("empty ROS response")
            return result

        def service(self, kind, name, request, timeout=15.0):
            client = self.create_client(kind, name)
            deadline = time.monotonic() + timeout
            while not client.wait_for_service(timeout_sec=0.05):
                rclpy.spin_once(self, executor=executor, timeout_sec=0.02)
                if time.monotonic() >= deadline:
                    raise TimeoutError(name)
            response = self.wait(client.call_async(request), timeout)
            self.destroy_client(client)
            return response

        def audit_graph(self, require_owners=True):
            names = [
                ns.rstrip("/") + "/" + name
                for name, ns in self.get_node_names_and_namespaces()
            ]
            foreign = [name for name in names if not name.startswith("/c3_nav2/")]
            if foreign:
                raise RuntimeError("unexpected ROS nodes: " + str(foreign))
            topics = dict(self.get_topic_names_and_types())
            outside = [
                t
                for t in topics
                if not t.startswith("/c3_nav2/")
                and t not in ("/clock", "/parameter_events", "/rosout")
            ]
            if outside:
                raise RuntimeError("unexpected ROS topics: " + str(outside))
            ownership = {}
            expected_owners = {
                "/clock": "bench_plant",
                "/c3_nav2/tf": "bench_plant",
                "/c3_nav2/tf_static": "bench_plant",
                "/c3_nav2/odom": "bench_plant",
                "/c3_nav2/scan": "bench_plant",
                "/c3_nav2/sim_actuator_cmd": "bench_plant",
                "/c3_nav2/raw/controller_server": "controller_server",
                "/c3_nav2/raw/behavior_server": "behavior_server",
                "/c3_nav2/plan": "planner_server",
                "/c3_nav2/global_costmap/costmap": "global_costmap/global_costmap",
            }
            if fixture.get("world_kind") == "d0_shared":
                expected_owners.update(
                    {
                        "/c3_nav2/local_costmap/costmap": "local_costmap/local_costmap",
                    }
                )
                if run["controller"] == "rpp":
                    expected_owners.update(
                        {
                            "/c3_nav2/lookahead_point": "controller_server",
                            "/c3_nav2/lookahead_collision_arc": "controller_server",
                        }
                    )
            for topic, owner in expected_owners.items():
                pubs = self.get_publishers_info_by_topic(topic)
                ownership[topic] = [
                    p.node_namespace.rstrip("/") + "/" + p.node_name for p in pubs
                ]
                count = (
                    len(
                        expected["behavior_server"]["ros__parameters"][
                            "behavior_plugins"
                        ]
                    )
                    if owner == "behavior_server"
                    else 1
                )
                if require_owners and not publisher_owners_match(
                    ownership[topic], "/c3_nav2/" + owner, count
                ):
                    raise RuntimeError(
                        "publisher ownership conflict or absence: "
                        + topic
                        + " "
                        + str(ownership[topic])
                    )
            snapshot = dict(
                nodes=names,
                topics=topics,
                publishers=ownership,
                sim_t=self.sim_t,
                owners_required=require_owners,
            )
            self.graph_snapshots.append(snapshot)
            return snapshot

    rclpy.init(
        args=[
            "--ros-args",
            "-r",
            "/tf:=/c3_nav2/tf",
            "-r",
            "/tf_static:=/c3_nav2/tf_static",
        ]
    )
    executor = metadata_executor_type(SingleThreadedExecutor, await_or_execute)()
    node = Plant()
    report = dict(
        schema="competition-nav2-result.v1",
        backend="nav2_native_sim",
        status="FAIL",
        scenario=fixture["scenario"],
        controller=run["controller"],
        variant=run["variant"],
        repeat=run["repeat"],
        seed=fixture["seed"],
        fixture_sha256=fixture["fixture_sha256"],
        config_sha256=digest(expected),
        isolation=isolation,
        pose_source="SIM_GT",
        physical_robot_qualification="NOT_RUN",
        full_course="NOT_RUN",
        limitations=[],
        lifecycle={},
        parameters={},
        loaded_libraries=[],
        package_versions={},
        action={},
        planner_only=run.get("planner_only", False),
    )
    goal_handle = None
    try:
        # Pre-start graph inspection: nodes may exist, but no native controller is active.
        wait_end = time.monotonic() + 20.0
        while time.monotonic() < wait_end:
            rclpy.spin_once(node, executor=executor, timeout_sec=0.05)
            current = {
                name
                for name, ns in node.get_node_names_and_namespaces()
                if ns == "/c3_nav2"
            }
            if set(NODES + ["lifecycle_manager_navigation"]).issubset(current):
                break
        else:
            raise TimeoutError("native nodes did not appear")
        node.audit_graph(require_owners=False)
        request = ManageLifecycleNodes.Request()
        request.command = ManageLifecycleNodes.Request.STARTUP
        if not node.service(
            ManageLifecycleNodes,
            "lifecycle_manager_navigation/manage_nodes",
            request,
            30.0,
        ).success:
            raise RuntimeError("native lifecycle STARTUP failed")
        for name in NODES:
            state = node.service(
                GetState, name + "/get_state", GetState.Request()
            ).current_state
            report["lifecycle"][name] = dict(id=state.id, label=state.label)
            if state.id != 3:
                raise RuntimeError(name + " not active")
        node.audit_graph()

        # Read back all explicitly set controller parameters, not just the plugin string.
        def flatten(mapping, prefix=""):
            result = {}
            for key, val in mapping.items():
                path = prefix + key
                if isinstance(val, dict):
                    result.update(flatten(val, path + "."))
                else:
                    result[path] = val
            return result

        flat = flatten(expected["controller_server"]["ros__parameters"])
        request = GetParameters.Request()
        request.names = list(flat)
        values = node.service(
            GetParameters, "controller_server/get_parameters", request
        ).values
        fields = {
            1: "bool_value",
            2: "integer_value",
            3: "double_value",
            4: "string_value",
            5: "byte_array_value",
            6: "bool_array_value",
            7: "integer_array_value",
            8: "double_array_value",
            9: "string_array_value",
        }
        for name, value in zip(request.names, values):
            actual = (
                getattr(value, fields[value.type]) if value.type in fields else None
            )
            if value.type >= 5:
                actual = list(actual)
            report["parameters"][name] = actual
            if actual != flat[name]:
                raise RuntimeError("parameter mismatch: " + name)
        flat_planner = flatten(expected["planner_server"]["ros__parameters"])
        request.names = list(flat_planner)
        values = node.service(
            GetParameters, "planner_server/get_parameters", request
        ).values
        report["planner_parameters"] = {}
        if omni:
            report.update(
                schema="competition-nav2-result.omni-v1",
                motion_model="Omni",
                command_axes=["linear.x", "linear.y", "angular.z"],
                motion_contract="repro/omni-checked-overlay-contract.json"
                if run["variant"] == "omni_checked_overlay"
                else "repro/omni-coverage-contract.json"
                if run["variant"] == "omni_coverage"
                else "repro/omni-contract.json",
                motion_primitive_sha256=hashlib.sha256(
                    Path(flat_planner["GridBased.lattice_filepath"]).read_bytes()
                ).hexdigest(),
            )
        if fixture.get("world_kind") == "d0_shared":
            report["narrow_diagnostics_schema"] = "c3-native-narrow-observations.v1"
        for name, value in zip(request.names, values):
            actual = (
                getattr(value, fields[value.type]) if value.type in fields else None
            )
            if value.type >= 5:
                actual = list(actual)
            report["planner_parameters"][name] = actual
            if actual != flat_planner[name]:
                raise RuntimeError("planner parameter mismatch: " + name)
        report["costmap_parameters"] = {}
        shared_keys = [
            "footprint",
            "footprint_padding",
            "resolution",
            "track_unknown_space",
            "inflation_layer.inflation_radius",
            "inflation_layer.cost_scaling_factor",
            "obstacle_layer.scan.topic",
            "obstacle_layer.scan.expected_update_rate",
        ]
        coverage_defaults = {}
        if run["variant"] in COVERAGE_VARIANTS:
            coverage_defaults = {
                "inflation_layer.enabled": True,
                "inflation_layer.inflate_unknown": False,
                "inflation_layer.inflate_around_unknown": False,
            }
            shared_keys += ["plugins", "inflation_layer.plugin", *coverage_defaults]
            report["coverage"] = coverage(
                fixture["effective_footprint"], fixture["resolution_m"]
            )
            request.names = ["FollowPath.CostCritic.inflation_layer_name"]
            selector = node.service(
                GetParameters, "controller_server/get_parameters", request
            ).values[0]
            if selector.type != 4:
                raise RuntimeError("critic inflation selector is not a declared string")
            actual = selector.string_value
            report["critic_inflation_layer_name"] = actual
            if actual != "":
                raise RuntimeError("unexpected critic inflation layer selector")
        for costmap in ("global_costmap", "local_costmap"):
            flat_costmap = flatten(expected[costmap][costmap]["ros__parameters"])
            request = GetParameters.Request()
            request.names = shared_keys
            values = node.service(
                GetParameters, f"{costmap}/{costmap}/get_parameters", request
            ).values
            applied = {}
            for key, value in zip(shared_keys, values):
                actual = (
                    getattr(value, fields[value.type]) if value.type in fields else None
                )
                if value.type >= 5:
                    actual = list(actual)
                applied[key] = actual
                if actual != flat_costmap.get(key, coverage_defaults.get(key)):
                    raise RuntimeError(
                        "costmap parameter mismatch: " + costmap + "." + key
                    )
            report["costmap_parameters"][costmap] = applied
        if run["variant"] in COVERAGE_VARIANTS:
            share = Path(get_package_share_directory("nav2_costmap_2d"))
            report["inflation_package_version"] = (
                ET.parse(share / "package.xml").getroot().findtext("version")
            )
            names = plugin_library_names(share, "nav2_costmap_2d::InflationLayer")
            report["inflation_library_sha256"] = {}
            for proc in Path("/proc").glob("[0-9]*"):
                try:
                    command = (
                        (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode()
                    )
                    if not any(
                        command.startswith("/opt/ros/humble/lib/" + part)
                        for part in (
                            "nav2_controller/controller_server ",
                            "nav2_planner/planner_server ",
                        )
                    ):
                        continue
                    paths = {
                        line.split()[-1]
                        for line in (proc / "maps").read_text().splitlines()
                        if Path(line.split()[-1]).name in names
                    }
                    report["inflation_library_sha256"][
                        "controller" if "/controller_server " in command else "planner"
                    ] = {
                        p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                        for p in paths
                    }
                except (OSError, UnicodeError):
                    continue
            if set(report["inflation_library_sha256"]) != {
                "controller",
                "planner",
            } or not all(report["inflation_library_sha256"].values()):
                raise RuntimeError(
                    "inflation library not loaded in both native processes"
                )
        package = (
            "nav2_mppi_controller"
            if run["controller"] == "mppi"
            else "nav2_regulated_pure_pursuit_controller"
        )
        for name in [
            "nav2_controller",
            "nav2_planner",
            "nav2_bt_navigator",
            "rclpy",
            package,
        ]:
            share = Path(get_package_share_directory(name))
            report["package_versions"][name] = (
                ET.parse(share / "package.xml").getroot().findtext("version")
            )
        library_names = plugin_library_names(
            get_package_share_directory(package), PLUGINS[run["controller"]]
        )
        report["plugin_export_library_names"] = sorted(library_names)
        for proc in Path("/proc").glob("[0-9]*"):
            try:
                command = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode()
                if (
                    "/nav2_controller/controller_server" in command
                    and command.startswith("/opt/ros/humble/")
                ):
                    maps = (proc / "maps").read_text()
                    report["loaded_libraries"] += sorted(
                        {
                            line.split()[-1]
                            for line in maps.splitlines()
                            if "/opt/ros/humble/" in line
                            and Path(line.split()[-1]).name in library_names
                        }
                    )
                    report["controller_process"] = dict(
                        pid=int(proc.name), command=command
                    )
            except (OSError, UnicodeError):
                continue
        if not report["loaded_libraries"]:
            raise RuntimeError(
                "no native controller shared library found in process maps"
            )
        report["loaded_library_sha256"] = {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in report["loaded_libraries"]
        }
        planner_plugin = flat_planner["GridBased.plugin"]
        planner_package = planner_plugin.split("/")[0].split("::")[0]
        planner_share = Path(get_package_share_directory(planner_package))
        report["package_versions"][planner_package] = (
            ET.parse(planner_share / "package.xml").getroot().findtext("version")
        )
        planner_libraries = plugin_library_names(planner_share, planner_plugin)
        report["planner_plugin_export_library_names"] = sorted(planner_libraries)
        report["planner_loaded_library_sha256"] = {}
        for proc in Path("/proc").glob("[0-9]*"):
            try:
                command = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode()
                if command.startswith(
                    "/opt/ros/humble/lib/nav2_planner/planner_server "
                ):
                    report["planner_process"] = dict(
                        pid=int(proc.name), command=command
                    )
                    paths = {
                        line.split()[-1]
                        for line in (proc / "maps").read_text().splitlines()
                        if "/opt/ros/humble/" in line
                        and Path(line.split()[-1]).name in planner_libraries
                    }
                    report["planner_loaded_library_sha256"].update(
                        {
                            p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                            for p in paths
                        }
                    )
            except (OSError, UnicodeError):
                continue
        if not report["planner_loaded_library_sha256"]:
            raise RuntimeError("no native planner shared library found in process maps")
        if run["variant"] == "omni_checked_overlay":
            report["overlay_loaded_library_sha256"] = {}
            for proc in Path("/proc").glob("[0-9]*"):
                try:
                    for line in (proc / "maps").read_text().splitlines():
                        lib = line.split()[-1]
                        if lib.startswith("/opt/c3-overlay/") and lib.endswith(".so"):
                            report["overlay_loaded_library_sha256"][lib] = (
                                hashlib.sha256(Path(lib).read_bytes()).hexdigest()
                            )
                except (OSError, UnicodeError):
                    continue
            required = {"libnav2_smac_planner_lattice.so", "libmppi_critics.so"}
            if not required.issubset(
                {Path(p).name for p in report["overlay_loaded_library_sha256"]}
            ):
                raise RuntimeError("required overlay libraries not actually loaded")
        if run.get("planner_only"):
            # Same sensor, costmaps and original goal; the actuator stays held because
            # goal_start is never set. No NavigateToPose/FollowPath action is submitted.
            action = ActionClient(node, ComputePathToPose, "compute_path_to_pose")
            wait_map = time.monotonic() + 3.0
            while not node.global_map_observed and time.monotonic() < wait_map:
                rclpy.spin_once(node, executor=executor, timeout_sec=0.02)
            if not node.global_map_observed:
                raise TimeoutError("planner-only lacks prior received global map")
            if not action.wait_for_server(timeout_sec=10.0):
                raise TimeoutError("ComputePathToPose action server absent")
            request = ComputePathToPose.Goal()
            request.goal.header.frame_id = "map"
            request.goal.header.stamp = node.stamp(node.sim_t)
            request.goal.pose.position.x, request.goal.pose.position.y = fixture[
                "goal"
            ][:2]
            request.goal.pose.orientation.z = math.sin(fixture["goal"][2] / 2)
            request.goal.pose.orientation.w = math.cos(fixture["goal"][2] / 2)
            request.planner_id = "GridBased"
            request.use_start = False
            goal_handle = node.wait(action.send_goal_async(request))
            report["action"] = dict(
                type="ComputePathToPose",
                accepted=goal_handle.accepted,
                goal_uuid=goal_uuid_to_json(goal_handle.goal_id.uuid),
            )
            if not goal_handle.accepted:
                raise RuntimeError("planner-only goal rejected")
            result = node.wait(goal_handle.get_result_async(), 15.0)
            report["action"]["status"] = result.status
            report["planner_action_path_points"] = len(result.result.path.poses)
            report["planner_action_time_s"] = (
                result.result.planning_time.sec
                + result.result.planning_time.nanosec / 1e9
            )
            settle = time.monotonic() + 2.1
            while time.monotonic() < settle:
                rclpy.spin_once(node, executor=executor, timeout_sec=0.02)
            report.update(status="NATIVE_RECORDED", outcome="SAFE_WAIT")
            return 0  # finally still records trace/zero/cleanup; validator gates path validity.
        action = ActionClient(node, NavigateToPose, "navigate_to_pose")
        if not action.wait_for_server(timeout_sec=10.0):
            raise TimeoutError("NavigateToPose action server absent")
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = node.stamp(node.sim_t)
        goal.pose.pose.position.x, goal.pose.pose.position.y = fixture["goal"][:2]
        goal.pose.pose.orientation.z = math.sin(fixture["goal"][2] / 2)
        goal.pose.pose.orientation.w = math.cos(fixture["goal"][2] / 2)
        goal.behavior_tree = str(Path(__file__).parent / "config/replan.xml")
        goal_handle = node.wait(action.send_goal_async(goal))
        report["action"]["accepted"] = goal_handle.accepted
        report["action"]["goal_uuid"] = goal_uuid_to_json(goal_handle.goal_id.uuid)
        if not goal_handle.accepted:
            raise RuntimeError("native goal rejected")
        node.goal_start = node.sim_t
        result_future = goal_handle.get_result_async()
        deadline = time.monotonic() + fixture["timeout_s"] * 2 + 15.0
        audit_at, recovery = time.monotonic(), None
        while (
            time.monotonic() < deadline
            and node.sim_t - node.goal_start < fixture["timeout_s"]
        ):
            rclpy.spin_once(node, executor=executor, timeout_sec=0.02)
            elapsed = node.sim_t - node.goal_start
            if time.monotonic() >= audit_at:
                node.audit_graph()
                audit_at = time.monotonic() + 1.0
            if (
                fixture.get("recovery_probe_s", math.inf) <= elapsed
                and recovery is None
            ):
                # Invoke the REAL behavior server while the final boundary is held.
                client = ActionClient(node, Spin, "spin")
                if not client.wait_for_server(timeout_sec=2.0):
                    raise TimeoutError("native Spin recovery action absent")
                request = Spin.Goal()
                request.target_yaw = 0.4
                request.time_allowance.sec = 3
                recovery = node.wait(client.send_goal_async(request))
                node.action_events.append(
                    dict(type="native_spin_during_hold", accepted=recovery.accepted)
                )
            if result_future.done() and (
                not fixture.get("recovery_probe_s") or elapsed >= 6.0
            ):
                break
            if node.boundary.fault:
                break
        if not result_future.done():
            cancel = node.wait(goal_handle.cancel_goal_async())
            report["action"]["cancel_ack_count"] = len(cancel.goals_canceling)
        # Always collect actual terminal action status, including abort/cancel.
        result = node.wait(result_future, 10.0)
        report["action"]["status"] = result.status
        if result.status != 4 or node.boundary.fault == "SENSOR_STALE":
            # Observe the terminal native stop plus TTL and two seconds of zero.
            # Do not inject HOLD or fabricate zero to make a SAFE_WAIT outcome.
            settle = time.monotonic() + 2.6
            while time.monotonic() < settle:
                rclpy.spin_once(node, executor=executor, timeout_sec=0.02)
        if node.boundary.fault == "SENSOR_STALE":
            report["dropout_recovery"] = dict(
                fault_latched=node.boundary.fault,
                final_output=list(node.previous_output),
                auto_resume=False,
                restart_requirement="Terminate this run; create a fresh isolated run, acquire fresh scans, activate servers, accept a new goal and release epoch. HOLD/RELEASE alone cannot clear a latched fault.",
            )
        if recovery is not None:
            rr = node.wait(recovery.get_result_async(), 8.0)
            node.action_events[-1]["result_status"] = rr.status
        distance = math.dist(node.pose[:2], fixture["goal"][:2])
        yaw_error = abs(
            (node.pose[2] - fixture["goal"][2] + math.pi) % (2 * math.pi) - math.pi
        )
        if result.status == 4 and distance <= 0.12 and yaw_error <= 0.2:
            report["outcome"] = "GOAL_REACHED"
        elif time.monotonic() - node.zero_since >= 2.0 and node.collision_count == 0:
            report["outcome"] = "SAFE_WAIT"
        else:
            report["outcome"] = "FAILED"
        report["status"] = "NATIVE_RECORDED"
        report["goal_distance_m"], report["goal_yaw_error_rad"] = distance, yaw_error
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
        node.boundary.stop("RUN_FAILED")
        if goal_handle is not None and goal_handle.accepted:
            try:
                node.wait(goal_handle.cancel_goal_async(), 3.0)
            except Exception as cancel_exc:
                report["cancel_error"] = str(cancel_exc)
    finally:
        terminal_fault = node.boundary.fault
        node.boundary.stop("RUN_FINISHED")
        # Observe final exact-zero actuator commands for a bounded shutdown interval.
        until = time.monotonic() + 0.5
        try:
            while rclpy.ok() and time.monotonic() < until:
                rclpy.spin_once(node, executor=executor, timeout_sec=0.02)
        except Exception as exc:
            report["shutdown_error"] = type(exc).__name__ + ": " + str(exc)
            report["status"] = "FAIL"
            node.final_pub.publish(Twist())
        report.update(
            metrics=dict(
                footprint_collision_count=node.collision_count,
                boundary_violation_count=node.boundary_count,
                min_conservative_clearance_m=node.min_clearance,
                path_length_m=node.path_length,
                sim_time_s=node.sim_t,
                wall_time_s=time.monotonic() - node.start_wall,
                plant_deadline_misses=node.deadline_miss,
                plant_max_wall_gap_s=max(node.periods, default=0.0),
                runner_cpu_s=time.process_time() - node.start_cpu,
                runner_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                hold_nonzero_count=node.hold_nonzero,
            ),
            raw_command_counts=node.raw_count,
            recovery_nonzero_count=node.recovery_nonzero,
            delayed_command_probe=node.delayed_probe,
            action_events=node.action_events,
            graph_snapshots=node.graph_snapshots,
            terminal_fault=terminal_fault,
            observation_schema="c3-native-observations.v1",
        )
        for file in (node.trace, node.raw, node.scans, node.observations):
            file.close()
        raw = [
            json.loads(line)
            for line in (directory / "raw_commands.jsonl").read_text().splitlines()
        ]
        report["raw_command_timing"] = {}
        for owner in node.raw_count:
            timestamps = [r["receipt_monotonic"] for r in raw if r["owner"] == owner]
            gaps = [b - a for a, b in zip(timestamps, timestamps[1:])]
            report["raw_command_timing"][owner] = dict(
                samples=len(timestamps),
                nominal_period_s=0.05,
                max_gap_s=max(gaps, default=None),
                gaps_over_75ms=sum(gap > 0.075 for gap in gaps),
                note="Observed receipt gaps include HOLD/recovery/action transitions; not isolated controller compute latency.",
            )
        (directory / "result.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n"
        )
        if hasattr(node.world, "close"):
            node.world.close()
        node.destroy_node()
        executor.shutdown()
        rclpy.shutdown()
    return 0 if report["status"] == "NATIVE_RECORDED" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
