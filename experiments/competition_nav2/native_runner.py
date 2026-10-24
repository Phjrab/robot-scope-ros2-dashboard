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
from core import Boundary, Command, LIMITS, propagate, swept_poses
from fixtures import World, digest
from preflight import require_isolated


def plugin_library_names(share, plugin):
    """Use installed plugin exports; package and shared-library names can differ."""
    names = set()
    for xml in Path(share).rglob("*.xml"):
        root = ET.parse(xml).getroot()
        for library in root.iter("library"):
            if any(cls.get("type") == plugin for cls in library.iter("class")):
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
    from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
    from ament_index_python.packages import get_package_share_directory
    from action_msgs.msg import GoalStatusArray
    from geometry_msgs.msg import TransformStamped, Twist
    from lifecycle_msgs.srv import GetState
    from nav2_msgs.action import NavigateToPose, Spin
    from nav2_msgs.srv import ManageLifecycleNodes
    from nav_msgs.msg import Odometry
    from rcl_interfaces.srv import GetParameters
    from rosgraph_msgs.msg import Clock as ClockMessage
    from sensor_msgs.msg import LaserScan
    from tf2_msgs.msg import TFMessage
    import yaml

    directory = Path(directory)
    fixture = json.loads((directory / "fixture.json").read_text())
    run = json.loads((directory / "run.json").read_text())
    expected = yaml.safe_load((directory / "params.yaml").read_text())

    class Plant(Node):
        def __init__(self):
            super().__init__("bench_plant", namespace="c3_nav2")
            self.world = World(fixture)
            self.boundary = Boundary()
            self.pose = tuple(fixture["start"])
            self.sim_t = 0.0
            self.goal_start = None
            self.last_tick = time.monotonic()
            self.next_scan = 0.0
            self.pending_scans = []
            self.sequence = 0
            self.previous_output = (0.0, 0.0)
            self.raw_count = {"controller_server": 0, "behavior_server": 0}
            self.active_actions = {"controller_server": False, "behavior_server": False}
            self.command_owner = None
            self.recovery_nonzero = 0
            self.delayed_probe = None
            self.trace = (directory / "trace.jsonl").open("w")
            self.raw = (directory / "raw_commands.jsonl").open("w")
            self.scans = (directory / "scans.jsonl").open("w")
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

            def bind_callback(owner):
                def callback(msg, info):
                    self.receive_command(msg, info, owner)

                return callback

            for owner in self.raw_count:
                self.subscriptions_raw.append(
                    self.create_subscription(
                        Twist, "raw/" + owner, bind_callback(owner), 1
                    )
                )

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

        def receive_command(self, msg, info, owner):
            now, wall_ns = time.monotonic(), time.time_ns()
            stamp = int(info.source_timestamp)
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
                for x in (msg.linear.y, msg.linear.z, msg.angular.x, msg.angular.y)
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
                self.boundary.output = (0.0, 0.0)
                self.boundary.release_at = now
            if not 0 <= age <= LIMITS["command_ttl"]:
                self.boundary.stop("DDS_SOURCE_AGE_INVALID")
            elif owners == [owner]:
                accepted = self.boundary.accept(
                    Command(
                        self.sequence,
                        self.boundary.epoch,
                        now - age,
                        now,
                        msg.linear.x,
                        msg.angular.z,
                    ),
                    now,
                )
            self.raw.write(
                json.dumps(
                    dict(
                        sim_t=self.sim_t,
                        receipt_monotonic=now,
                        source_timestamp_ns=stamp,
                        source_age_s=age if math.isfinite(age) else None,
                        owner=owner,
                        v=msg.linear.x,
                        w=msg.angular.z,
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
            v, w = self.previous_output
            samples = swept_poses(before, v, w, dt)
            if any(self.world.collision(p, scene_time) for p in samples):
                self.collision_count += 1
                self.boundary.stop("FOOTPRINT_CONTACT")
            if any(self.world.boundary_violation(p) for p in samples):
                self.boundary_count += 1
            self.pose = propagate(before, v, w, dt)
            self.path_length += math.dist(before[:2], self.pose[:2])
            self.min_clearance = min(
                self.min_clearance,
                *(self.world.clearance(p, scene_time) for p in samples),
            )
            self.sim_t += dt
            elapsed = 0.0 if self.goal_start is None else self.sim_t - self.goal_start
            clock = ClockMessage()
            clock.clock = self.stamp(self.sim_t)
            self.clock_pub.publish(clock)
            identity = TransformStamped()
            identity.header.stamp = clock.clock
            identity.header.frame_id, identity.child_frame_id = "map", "odom"
            identity.transform.rotation.w = 1.0
            self.static_pub.publish(TFMessage(transforms=[identity]))
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
            self.odom_pub.publish(odom)
            if self.sim_t >= self.next_scan:
                self.next_scan = self.sim_t + fixture["sensor_period_s"]
                if self.goal_start is None or elapsed < fixture.get(
                    "sensor_dropout_s", math.inf
                ):
                    msg = LaserScan()
                    msg.header.frame_id, msg.header.stamp = "base_link", clock.clock
                    msg.angle_min = -math.pi
                    msg.angle_increment = 2 * math.pi / fixture["scan_beams"]
                    msg.angle_max = math.pi - msg.angle_increment
                    msg.range_min, msg.range_max = 0.02, 8.0
                    msg.scan_time = fixture["sensor_period_s"]
                    msg.ranges = self.world.scan(self.pose, elapsed)
                    self.pending_scans.append(
                        (now + fixture["sensor_delay_s"], now, msg)
                    )
            while self.pending_scans and self.pending_scans[0][0] <= now:
                _, source_mono, scan = self.pending_scans.pop(0)
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
                    Command(
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
            twist.linear.x, twist.angular.z = output
            self.final_pub.publish(twist)
            zero = output == (0.0, 0.0)
            self.hold_nonzero += int(held and not zero)
            if not zero:
                self.zero_since = now
            self.trace.write(
                json.dumps(
                    dict(
                        sim_t=self.sim_t,
                        elapsed_s=elapsed,
                        pose=list(self.pose),
                        applied_previous=[v, w],
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
                rclpy.spin_once(self, timeout_sec=0.02)
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
                rclpy.spin_once(self, timeout_sec=0.02)
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
            }
            for topic, owner in expected_owners.items():
                pubs = self.get_publishers_info_by_topic(topic)
                ownership[topic] = [
                    p.node_namespace.rstrip("/") + "/" + p.node_name for p in pubs
                ]
                if require_owners and ownership[topic] != ["/c3_nav2/" + owner]:
                    raise RuntimeError(
                        "publisher ownership conflict or absence: "
                        + topic
                        + " "
                        + str(ownership[topic])
                    )
            snapshot = dict(
                nodes=names, topics=topics, publishers=ownership, sim_t=self.sim_t
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
    )
    goal_handle = None
    try:
        # Pre-start graph inspection: nodes may exist, but no native controller is active.
        wait_end = time.monotonic() + 20.0
        while time.monotonic() < wait_end:
            rclpy.spin_once(node, timeout_sec=0.05)
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
                applied[key] = actual
                if actual != flat_costmap[key]:
                    raise RuntimeError(
                        "costmap parameter mismatch: " + costmap + "." + key
                    )
            report["costmap_parameters"][costmap] = applied
        package = (
            "nav2_mppi_controller"
            if run["controller"] == "mppi"
            else "nav2_regulated_pure_pursuit_controller"
        )
        for name in ["nav2_controller", "nav2_planner", "nav2_bt_navigator", package]:
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
        report["action"]["goal_uuid"] = list(goal_handle.goal_id.uuid)
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
            rclpy.spin_once(node, timeout_sec=0.02)
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
                rclpy.spin_once(node, timeout_sec=0.02)
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
        while rclpy.ok() and time.monotonic() < until:
            rclpy.spin_once(node, timeout_sec=0.02)
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
        )
        for file in (node.trace, node.raw, node.scans):
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
        node.destroy_node()
        rclpy.shutdown()
    return 0 if report["status"] == "NATIVE_RECORDED" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
