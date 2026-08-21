"""Fixed ROS navigation gateway and autonomous motion safety gate."""

from __future__ import annotations

import copy
import json
import math
import re
import secrets
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional, Protocol

from ..control import (
    CommandValidationError,
    ControlDisabled,
    ControlError,
    ControlNotReady,
    EmergencyStopLatched,
    LeaseBusy,
)


# Nav2 is remapped to this private ingress. A random/global /cmd_vel publisher
# can therefore never acquire the autonomous gate accidentally.
NAVIGATION_CMD_VEL_TOPIC = "/robot_scope/nav/cmd_vel_raw"
NAVIGATION_INITIAL_POSE_TOPIC = "/initialpose"
NAVIGATION_LOCALIZATION_POSE_TOPIC = "/amcl_pose"
NAVIGATION_RUNTIME_HEALTH_TOPIC = "/robot_scope/nav/runtime_health"
NAVIGATION_FAST_LIO_ODOM_TOPIC = "/Odometry"
# The Go2's continuously available onboard odometry provides controller
# velocity feedback. FAST-LIO remains the fixed localization input.
NAVIGATION_CONTROLLER_ODOM_TOPIC = "/utlidar/robot_odom"
NAVIGATION_ACTION = "/navigate_to_pose"
NAVIGATION_ODOM_STAMP_MAX_AGE_S = 1.5
NAVIGATION_ODOM_STAMP_MAX_FUTURE_S = 0.5
NAVIGATION_CLEAR_SERVICES = (
    "/global_costmap/clear_entirely_global_costmap",
    "/local_costmap/clear_entirely_local_costmap",
)

_NAVIGATION_REASON_SECRET_RE = re.compile(
    r"(?i)\b([A-Za-z0-9_]*(?:password|passwd|secret|token|api[_-]?key|"
    r"private[_-]?key|credential|authorization|bridge[_-]?key)[A-Za-z0-9_]*)"
    r"\b\s*(?:[:=]|\s)\s*(?:\"[^\"]*\"|'[^']*'|\S+)"
)
_NAVIGATION_REASON_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_NAVIGATION_REASON_WHITESPACE_RE = re.compile(r"\s+")


def public_navigation_reason(reason: object) -> str:
    """Return one bounded internal reason without credentials/control bytes."""

    value = _NAVIGATION_REASON_CONTROL_RE.sub(" ", str(reason or ""))
    value = _NAVIGATION_REASON_WHITESPACE_RE.sub(" ", value).strip()
    value = _NAVIGATION_REASON_SECRET_RE.sub(
        lambda match: f"{match.group(1)}=[redacted]",
        value,
    )
    return (value or "navigation stopped")[:160]


class NavigationControlPort(Protocol):
    """Narrow control-plane surface required by autonomous navigation."""

    manager: Any
    operation_lock: threading.RLock

    def flush_outputs(self) -> None: ...

    def publish_outputs(self, outputs: list[Dict[str, Any]]) -> None: ...

    def ensure_target(self) -> None: ...

    def go2_target(self) -> bool: ...


class NavigationRosGateway:
    """Own fixed Nav2 ROS endpoints, state, and autonomous safety gates."""

    def __init__(
        self,
        control_port: NavigationControlPort,
        *,
        node_getter: Callable[[], Any],
        tick: Callable[[str, float], None],
        graph_getter: Callable[[], Mapping[str, Mapping[str, Any]]],
    ) -> None:
        self._control_port = control_port
        self._node_getter = node_getter
        self._tick = tick
        self._graph_getter = graph_getter

        self._navigation_lock = threading.RLock()
        self._navigation_callback_group: Any = None
        self._navigation_cmd_subscription: Any = None
        self._navigation_health_subscriptions: Dict[str, Any] = {}
        self._navigation_initial_pose_publisher: Any = None
        self._navigation_pose_type: Any = None
        self._navigation_action_type: Any = None
        self._navigation_action_client: Any = None
        self._navigation_clear_service_type: Any = None
        self._navigation_clear_clients: Dict[str, Any] = {}
        self._navigation_runtime_health_received = 0.0
        self._navigation_runtime_health: Dict[str, Any] = {
            "ready": False,
            "cloud_fresh": False,
            "odom_fresh": False,
            "localized": False,
            "error": "navigation runtime health waiting",
        }
        self._navigation_odom_stamp_ns: Dict[str, int] = {
            NAVIGATION_FAST_LIO_ODOM_TOPIC: 0,
            NAVIGATION_CONTROLLER_ODOM_TOPIC: 0,
        }
        # These receipts are written only after fixed callback validation. UI
        # graph metrics must never be able to open a motion gate.
        self._navigation_validated_receipts: Dict[str, float] = {
            "/scan": 0.0,
            NAVIGATION_FAST_LIO_ODOM_TOPIC: 0.0,
            NAVIGATION_CONTROLLER_ODOM_TOPIC: 0.0,
            NAVIGATION_LOCALIZATION_POSE_TOPIC: 0.0,
        }
        self._navigation_token = ""
        self._navigation_binding = ""
        self._navigation_sequence = -1
        self._navigation_last_heartbeat = 0.0
        self._navigation_goal_handle: Any = None
        self._navigation_goal_generation = 0
        self._navigation_cancel_requested = False
        self._navigation_clear_generation = 0
        self._navigation_last_clear = 0.0
        self._navigation: Dict[str, Any] = {
            "seq": 0,
            "active": False,
            "state": "inactive",
            "error": None,
            "deactivation_reason": None,
            "map": None,
            "localization": {
                "state": "uninitialized",
                "pose": None,
            },
            "goal": {
                "state": "idle",
                "goal_id": None,
                "pose": None,
                "distance_remaining": None,
                "navigation_time": None,
                "recoveries": 0,
                "error": None,
            },
            "last_cmd_at": 0.0,
            "last_cmd": {"vx": 0.0, "vy": 0.0, "wz": 0.0},
            "clear_costmaps": {"state": "idle", "error": None},
        }

    @property
    def lock(self) -> threading.RLock:
        return self._navigation_lock

    @property
    def state(self) -> Dict[str, Any]:
        return self._navigation

    @property
    def validated_receipts(self) -> Dict[str, float]:
        return self._navigation_validated_receipts

    def setup(self, node: Any) -> None:
        """Create fixed Nav2 ingress/action/service endpoints.

        Message types remain lazy so a missing Nav2 installation disables only
        autonomous driving and does not weaken observation or manual control.
        """

        try:
            from rclpy.action import ActionClient
            from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
            from rclpy.qos import (
                DurabilityPolicy,
                HistoryPolicy,
                QoSProfile,
                ReliabilityPolicy,
            )
            from rosidl_runtime_py.utilities import get_action, get_message, get_service
            from std_msgs.msg import String

            callback_group = MutuallyExclusiveCallbackGroup()
            reliable = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            twist_type = get_message("geometry_msgs/msg/Twist")
            pose_type = get_message("geometry_msgs/msg/PoseWithCovarianceStamped")
            scan_type = get_message("sensor_msgs/msg/LaserScan")
            odometry_type = get_message("nav_msgs/msg/Odometry")
            action_type = get_action("nav2_msgs/action/NavigateToPose")
            clear_type = get_service("nav2_msgs/srv/ClearEntireCostmap")
            command_subscription = node.create_subscription(
                twist_type,
                NAVIGATION_CMD_VEL_TOPIC,
                self._navigation_cmd_vel_callback,
                reliable,
                callback_group=callback_group,
            )
            health_subscriptions = {
                "/scan": node.create_subscription(
                    scan_type,
                    "/scan",
                    lambda message: self._navigation_health_callback("/scan", message),
                    QoSProfile(
                        history=HistoryPolicy.KEEP_LAST,
                        depth=1,
                        reliability=ReliabilityPolicy.BEST_EFFORT,
                        durability=DurabilityPolicy.VOLATILE,
                    ),
                    callback_group=callback_group,
                ),
                NAVIGATION_FAST_LIO_ODOM_TOPIC: node.create_subscription(
                    odometry_type,
                    NAVIGATION_FAST_LIO_ODOM_TOPIC,
                    lambda message: self._navigation_health_callback(
                        NAVIGATION_FAST_LIO_ODOM_TOPIC, message
                    ),
                    QoSProfile(
                        history=HistoryPolicy.KEEP_LAST,
                        depth=1,
                        reliability=ReliabilityPolicy.BEST_EFFORT,
                        durability=DurabilityPolicy.VOLATILE,
                    ),
                    callback_group=callback_group,
                ),
                NAVIGATION_CONTROLLER_ODOM_TOPIC: node.create_subscription(
                    odometry_type,
                    NAVIGATION_CONTROLLER_ODOM_TOPIC,
                    lambda message: self._navigation_health_callback(
                        NAVIGATION_CONTROLLER_ODOM_TOPIC, message
                    ),
                    QoSProfile(
                        history=HistoryPolicy.KEEP_LAST,
                        depth=1,
                        reliability=ReliabilityPolicy.BEST_EFFORT,
                        durability=DurabilityPolicy.VOLATILE,
                    ),
                    callback_group=callback_group,
                ),
                NAVIGATION_LOCALIZATION_POSE_TOPIC: node.create_subscription(
                    pose_type,
                    NAVIGATION_LOCALIZATION_POSE_TOPIC,
                    self._navigation_localization_callback,
                    reliable,
                    callback_group=callback_group,
                ),
                NAVIGATION_RUNTIME_HEALTH_TOPIC: node.create_subscription(
                    String,
                    NAVIGATION_RUNTIME_HEALTH_TOPIC,
                    self._navigation_runtime_health_callback,
                    QoSProfile(
                        history=HistoryPolicy.KEEP_LAST,
                        depth=1,
                        reliability=ReliabilityPolicy.RELIABLE,
                        durability=DurabilityPolicy.TRANSIENT_LOCAL,
                    ),
                    callback_group=callback_group,
                ),
            }
            pose_publisher = node.create_publisher(
                pose_type,
                NAVIGATION_INITIAL_POSE_TOPIC,
                reliable,
                callback_group=callback_group,
            )
            action_client = ActionClient(
                node,
                action_type,
                NAVIGATION_ACTION,
                callback_group=callback_group,
            )
            clear_clients = {
                service: node.create_client(
                    clear_type,
                    service,
                    callback_group=callback_group,
                )
                for service in NAVIGATION_CLEAR_SERVICES
            }
            with self._navigation_lock:
                self._navigation_callback_group = callback_group
                self._navigation_cmd_subscription = command_subscription
                self._navigation_health_subscriptions = health_subscriptions
                self._navigation_initial_pose_publisher = pose_publisher
                self._navigation_pose_type = pose_type
                self._navigation_action_type = action_type
                self._navigation_action_client = action_client
                self._navigation_clear_service_type = clear_type
                self._navigation_clear_clients = clear_clients
                self._navigation["error"] = None
                self._navigation["seq"] += 1
        except Exception as exc:
            with self._navigation_lock:
                self._navigation["state"] = "unavailable"
                self._navigation["error"] = (
                    f"Nav2 ROS transport unavailable: {exc}"[:240]
                )
                self._navigation["seq"] += 1

    @staticmethod
    def pose_values(
        x: object,
        y: object,
        yaw: object,
    ) -> tuple[float, float, float]:
        values: list[float] = []
        for label, value in (("x", x), ("y", y), ("yaw", yaw)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise CommandValidationError(
                    f"navigation pose {label} must be numeric"
                )
            number = float(value)
            if not math.isfinite(number):
                raise CommandValidationError(
                    f"navigation pose {label} must be finite"
                )
            values.append(number)
        if abs(values[0]) > 10_000.0 or abs(values[1]) > 10_000.0:
            raise CommandValidationError(
                "navigation pose is outside the supported map bounds"
            )
        values[2] = math.atan2(math.sin(values[2]), math.cos(values[2]))
        return values[0], values[1], values[2]

    @staticmethod
    def _duration_seconds(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            seconds = int(getattr(value, "sec", 0))
            nanoseconds = int(getattr(value, "nanosec", 0))
            result = seconds + nanoseconds / 1_000_000_000.0
            return round(max(0.0, result), 3)
        except (TypeError, ValueError, OverflowError):
            return None

    def _new_stamped_pose(self, x: float, y: float, yaw: float) -> Any:
        pose_type = self._navigation_pose_type
        node = self._node_getter()
        if pose_type is None or node is None:
            raise ControlDisabled("Nav2 pose transport is unavailable")
        message = pose_type()
        message.header.frame_id = "map"
        message.header.stamp = node.get_clock().now().to_msg()
        message.pose.pose.position.x = x
        message.pose.pose.position.y = y
        message.pose.pose.position.z = 0.0
        message.pose.pose.orientation.x = 0.0
        message.pose.pose.orientation.y = 0.0
        message.pose.pose.orientation.z = math.sin(yaw * 0.5)
        message.pose.pose.orientation.w = math.cos(yaw * 0.5)
        return message

    def _navigation_transport_configured_locked(self) -> bool:
        return bool(
            self._navigation_cmd_subscription is not None
            and len(self._navigation_health_subscriptions) == 5
            and self._navigation_initial_pose_publisher is not None
            and self._navigation_pose_type is not None
            and self._navigation_action_type is not None
            and self._navigation_action_client is not None
            and self._navigation_clear_service_type is not None
            and len(self._navigation_clear_clients) == len(NAVIGATION_CLEAR_SERVICES)
        )

    def activate(
        self,
        *,
        map_id: str,
        map_revision: str,
        map_name: str = "",
        ready_after: float = 0.0,
    ) -> Dict[str, Any]:
        """Arm a pinned map only after its runtime inputs are currently ready."""

        identifier = str(map_id).strip()
        revision = str(map_revision).strip().lower()
        if not identifier or len(identifier) > 256:
            raise CommandValidationError("navigation map id is invalid")
        if len(revision) != 64 or any(
            char not in "0123456789abcdef" for char in revision
        ):
            raise CommandValidationError("navigation map revision is invalid")
        if (
            isinstance(ready_after, bool)
            or not isinstance(ready_after, (int, float))
            or not math.isfinite(float(ready_after))
            or float(ready_after) < 0.0
        ):
            raise CommandValidationError("navigation readiness fence is invalid")
        with self._control_port.operation_lock:
            self.start_preflight()
            interlock = self._navigation_prelocalization_reason(
                time.monotonic(),
                ready_after=float(ready_after),
            )
            if interlock:
                raise ControlNotReady(interlock)
            acquired = self._control_port.manager.acquire_navigation_lease()
            token = str(acquired["token"])
            binding = f"robot-scope-navigation-{secrets.token_urlsafe(18)}"
            try:
                self._control_port.manager.bind_lease(token, binding)
            except Exception:
                try:
                    self._control_port.manager.release_lease(token)
                except ControlError:
                    pass
                self._control_port.flush_outputs()
                raise
            now = time.monotonic()
            with self._navigation_lock:
                self._navigation_token = token
                self._navigation_binding = binding
                self._navigation_sequence = -1
                self._navigation_last_heartbeat = now
                self._navigation_goal_generation += 1
                self._navigation_goal_handle = None
                self._navigation_cancel_requested = False
                self._navigation_last_clear = 0.0
                self._navigation.update(
                    {
                        "seq": int(self._navigation.get("seq", 0)) + 1,
                        "active": True,
                        "state": "armed",
                        "error": None,
                        "deactivation_reason": None,
                        "map": {
                            "id": identifier,
                            "revision": revision,
                            "name": str(map_name)[:128],
                            "frame_id": "map",
                        },
                        "localization": {
                            "state": "uninitialized",
                            "pose": None,
                        },
                        "goal": {
                            "state": "idle",
                            "goal_id": None,
                            "pose": None,
                            "distance_remaining": None,
                            "navigation_time": None,
                            "recoveries": 0,
                            "error": None,
                        },
                        "last_cmd_at": 0.0,
                        "last_cmd": {"vx": 0.0, "vy": 0.0, "wz": 0.0},
                        "clear_costmaps": {"state": "idle", "error": None},
                    }
                )
            self._control_port.flush_outputs()
        return self.runtime_snapshot()

    def start_preflight(self) -> Dict[str, Any]:
        """Check whether navigation could reserve motion without doing so."""

        with self._control_port.operation_lock:
            self._control_port.ensure_target()
            with self._navigation_lock:
                if not self._navigation_transport_configured_locked():
                    raise ControlDisabled("Nav2 ROS transport is unavailable")
                goal_state = str(
                    (self._navigation.get("goal") or {}).get("state", "idle")
                )
                if (
                    self._navigation.get("active")
                    or self._navigation_token
                    or self._navigation_binding
                    or goal_state in {"pending", "active", "canceling"}
                ):
                    raise LeaseBusy(
                        "another navigation session already owns the robot"
                    )
            control = self._control_port.manager.snapshot()
            if not control.get("configured") or control.get("closed"):
                raise ControlDisabled("robot control is not configured")
            estop = (
                control.get("estop")
                if isinstance(control.get("estop"), dict)
                else {}
            )
            if estop.get("latched"):
                raise EmergencyStopLatched("dashboard software stop is latched")
            action_guard = (
                control.get("action_guard")
                if isinstance(control.get("action_guard"), dict)
                else {}
            )
            if action_guard.get("active"):
                raise ControlNotReady("robot action safety window is active")
            if not control.get("ready"):
                raise ControlNotReady("bridge and lowstate must both be fresh")
            lease = (
                control.get("lease")
                if isinstance(control.get("lease"), dict)
                else {}
            )
            if lease.get("active"):
                raise LeaseBusy("another controller already owns the robot")
            return {"ready": True}

    def prelocalization_snapshot(
        self,
        *,
        ready_after: float = 0.0,
    ) -> Dict[str, Any]:
        """Observe the fixed runtime's fresh cloud/odom gate without arming."""

        if (
            isinstance(ready_after, bool)
            or not isinstance(ready_after, (int, float))
            or not math.isfinite(float(ready_after))
            or float(ready_after) < 0.0
        ):
            raise CommandValidationError("navigation readiness fence is invalid")
        reason = self._navigation_prelocalization_reason(
            time.monotonic(),
            ready_after=float(ready_after),
        )
        return {
            "ready": reason is None,
            "reason": None if reason is None else public_navigation_reason(reason),
        }

    @staticmethod
    def _navigation_cancel_handle(handle: Any) -> None:
        if handle is None:
            return
        try:
            handle.cancel_goal_async()
        except Exception:
            pass

    def deactivate(self, reason: str = "navigation_stop") -> Dict[str, Any]:
        """Close the Nav2 velocity gate and issue signed StopMove first."""

        public_reason = public_navigation_reason(reason)
        normal_stop = reason in {"navigation_stop", "operator_stop"}
        with self._control_port.operation_lock:
            with self._navigation_lock:
                token = self._navigation_token
                binding = self._navigation_binding
                handle = self._navigation_goal_handle
                was_active = bool(self._navigation.get("active"))
                self._navigation_token = ""
                self._navigation_binding = ""
                self._navigation_goal_handle = None
                self._navigation_cancel_requested = False
                self._navigation_goal_generation += 1
                self._navigation_clear_generation += 1
                self._navigation.update(
                    {
                        "seq": int(self._navigation.get("seq", 0)) + 1,
                        "active": False,
                        "state": "inactive" if normal_stop else "stopped",
                        "error": None if normal_stop else public_reason,
                        "deactivation_reason": public_reason,
                        "map": None,
                        "localization": {
                            "state": "uninitialized",
                            "pose": None,
                        },
                        "last_cmd_at": 0.0,
                        "last_cmd": {"vx": 0.0, "vy": 0.0, "wz": 0.0},
                    }
                )
                goal = dict(self._navigation.get("goal") or {})
                if goal.get("state") in {"pending", "active", "canceling"}:
                    goal["state"] = "canceled"
                    goal["error"] = public_reason
                    self._navigation["goal"] = goal
            stop_published = False
            if token:
                try:
                    self._control_port.manager.release_lease(token, binding or None)
                    stop_published = True
                except (ControlError, ValueError):
                    pass
            if was_active and not stop_published:
                self._control_port.publish_outputs(
                    [
                        {
                            "type": "stop",
                            "reason": public_reason,
                            "velocity": {"vx": 0.0, "vy": 0.0, "wz": 0.0},
                            "created_at": time.monotonic(),
                        }
                    ]
                )
            self._control_port.flush_outputs()
            # Stop crosses the signed transport before asynchronous Nav2
            # cancellation can wait on a failed action server.
            self._navigation_cancel_handle(handle)
        return self.runtime_snapshot()

    def _navigation_health_callback(self, topic: str, message: Any) -> None:
        """Count only structurally valid samples as fresh navigation input."""

        observed_at = time.monotonic()
        try:
            if topic == "/scan":
                frame_id = str(getattr(message.header, "frame_id", "")).lstrip("/")
                if frame_id != "hesai_lidar":
                    raise ValueError("unexpected scan frame")
                ranges = getattr(message, "ranges", None)
                if ranges is None or len(ranges) < 8:
                    raise ValueError("scan contains too few ranges")
            elif topic in {
                NAVIGATION_FAST_LIO_ODOM_TOPIC,
                NAVIGATION_CONTROLLER_ODOM_TOPIC,
            }:
                stamp_ns = self._navigation_validate_odom_stamp(topic, message)
                pose = message.pose.pose
                twist = message.twist.twist
                values = (
                    pose.position.x,
                    pose.position.y,
                    pose.position.z,
                    pose.orientation.x,
                    pose.orientation.y,
                    pose.orientation.z,
                    pose.orientation.w,
                    twist.linear.x,
                    twist.linear.y,
                    twist.angular.z,
                )
                if not all(math.isfinite(float(value)) for value in values):
                    raise ValueError("odometry contains non-finite values")
                if (
                    abs(float(pose.position.x)) > 10_000.0
                    or abs(float(pose.position.y)) > 10_000.0
                    or abs(float(pose.position.z)) > 100.0
                ):
                    raise ValueError("odometry pose is outside supported bounds")
                quaternion_norm = math.sqrt(
                    float(pose.orientation.x) ** 2
                    + float(pose.orientation.y) ** 2
                    + float(pose.orientation.z) ** 2
                    + float(pose.orientation.w) ** 2
                )
                if quaternion_norm < 0.5 or quaternion_norm > 1.5:
                    raise ValueError("odometry quaternion norm is invalid")
                if (
                    abs(float(twist.linear.x)) > 5.0
                    or abs(float(twist.linear.y)) > 5.0
                    or abs(float(twist.angular.z)) > 10.0
                ):
                    raise ValueError("odometry twist is physically implausible")
                if topic == NAVIGATION_FAST_LIO_ODOM_TOPIC:
                    parent = str(getattr(message.header, "frame_id", "")).lstrip(
                        "/"
                    )
                    child = str(getattr(message, "child_frame_id", "")).lstrip(
                        "/"
                    )
                    if parent != "camera_init" or child != "body":
                        raise ValueError("unexpected FAST-LIO odometry frames")
                if not self._navigation_commit_odom_stamp(topic, stamp_ns):
                    # The first controller sample, and the first sample after
                    # an inactive robot-clock reset, establish only a baseline.
                    return
            with self._navigation_lock:
                if topic in self._navigation_validated_receipts:
                    self._navigation_validated_receipts[topic] = observed_at
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            with self._navigation_lock:
                if topic in self._navigation_validated_receipts:
                    self._navigation_validated_receipts[topic] = 0.0
                active = bool(self._navigation.get("active"))
            if active:
                self.deactivate(f"invalid {topic} sample: {exc}")
            return
        self._tick(topic, observed_at)

    def _navigation_validate_odom_stamp(self, topic: str, message: Any) -> int:
        """Validate timestamp shape and clock bounds without mutating state."""

        if topic not in {
            NAVIGATION_FAST_LIO_ODOM_TOPIC,
            NAVIGATION_CONTROLLER_ODOM_TOPIC,
        }:
            raise ValueError("unexpected odometry topic")
        stamp = message.header.stamp
        seconds = stamp.sec
        nanoseconds = stamp.nanosec
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, int)
            or isinstance(nanoseconds, bool)
            or not isinstance(nanoseconds, int)
            or seconds < 0
            or nanoseconds < 0
            or nanoseconds >= 1_000_000_000
        ):
            raise ValueError("odometry timestamp is malformed")
        stamp_ns = seconds * 1_000_000_000 + nanoseconds
        if stamp_ns <= 0:
            raise ValueError("odometry timestamp is zero")

        if topic == NAVIGATION_FAST_LIO_ODOM_TOPIC:
            node = self._node_getter()
            if node is None:
                raise ValueError("ROS clock is unavailable")
            now_ns = node.get_clock().now().nanoseconds
            if (
                isinstance(now_ns, bool)
                or not isinstance(now_ns, int)
                or now_ns <= 0
            ):
                raise ValueError("ROS clock is invalid")
            age_ns = now_ns - stamp_ns
            if age_ns > int(
                NAVIGATION_ODOM_STAMP_MAX_AGE_S * 1_000_000_000
            ):
                raise ValueError("odometry timestamp is stale")
            if age_ns < -int(
                NAVIGATION_ODOM_STAMP_MAX_FUTURE_S * 1_000_000_000
            ):
                raise ValueError("odometry timestamp is in the future")

        return stamp_ns

    def _navigation_commit_odom_stamp(self, topic: str, stamp_ns: int) -> bool:
        """Commit a fully validated stamp and return whether it proves liveness."""

        with self._navigation_lock:
            previous_ns = int(self._navigation_odom_stamp_ns.get(topic, 0) or 0)
            if not previous_ns:
                self._navigation_odom_stamp_ns[topic] = stamp_ns
                if topic == NAVIGATION_CONTROLLER_ODOM_TOPIC:
                    self._navigation_validated_receipts[topic] = 0.0
                    return False
                return True

            if stamp_ns <= previous_ns:
                if topic == NAVIGATION_CONTROLLER_ODOM_TOPIC:
                    self._navigation_validated_receipts[topic] = 0.0
                    active = bool(self._navigation.get("active"))
                    if not active and stamp_ns < previous_ns:
                        # A stopped robot may reboot/reset its clock. Re-prime
                        # while disarmed, but require the next strict advance.
                        self._navigation_odom_stamp_ns[topic] = stamp_ns
                        return False
                raise ValueError("odometry timestamp did not increase")

            self._navigation_odom_stamp_ns[topic] = stamp_ns
            return True

    def _navigation_runtime_health_callback(self, message: Any) -> None:
        now = time.monotonic()
        try:
            payload = json.loads(message.data)
            if not isinstance(payload, dict):
                raise ValueError("health payload must be an object")
            if payload.get("schema") != "robot-scope.navigation-runtime-health.v1":
                raise ValueError("health schema is invalid")
            for key in ("ready", "cloud_fresh", "odom_fresh", "localized"):
                if not isinstance(payload.get(key), bool):
                    raise ValueError(f"health {key} flag is invalid")
            if payload.get("cloud_topic") != "/velodyne_points":
                raise ValueError("health cloud topic is invalid")
            if payload.get("scan_topic") != "/scan":
                raise ValueError("health scan topic is invalid")
            if payload.get("odometry_topic") != "/Odometry":
                raise ValueError("health odometry topic is invalid")
            if payload.get("cloud_frame") != "hesai_lidar":
                raise ValueError("health cloud frame is invalid")
            counts = payload.get("publisher_counts")
            if not isinstance(counts, dict):
                raise ValueError("health publisher counts are invalid")
            sanitized_counts: Dict[str, int] = {}
            for topic in ("/velodyne_points", NAVIGATION_FAST_LIO_ODOM_TOPIC):
                count = counts.get(topic)
                if (
                    isinstance(count, bool)
                    or not isinstance(count, int)
                    or count < 0
                    or count > 16
                ):
                    raise ValueError(
                        f"health publisher count for {topic} is invalid"
                    )
                sanitized_counts[topic] = count
            if payload.get("ready") and any(
                count != 1 for count in sanitized_counts.values()
            ):
                raise ValueError("ready health has non-unique sensor sources")
            input_points = int(payload.get("input_points", 0))
            accepted_points = int(payload.get("accepted_points", 0))
            if (
                input_points < 0
                or accepted_points < 0
                or accepted_points > input_points
            ):
                raise ValueError("health point counts are invalid")
            node = self._node_getter()
            publishers = (
                node.count_publishers(NAVIGATION_RUNTIME_HEALTH_TOPIC)
                if node
                else 0
            )
            if publishers != 1:
                raise ValueError(
                    "expected one navigation runtime health publisher, "
                    f"found {publishers}"
                )
        except (AttributeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            with self._navigation_lock:
                self._navigation_runtime_health_received = 0.0
                self._navigation_runtime_health = {
                    "ready": False,
                    "cloud_fresh": False,
                    "odom_fresh": False,
                    "localized": False,
                    "error": f"rejected navigation runtime health: {exc}"[:240],
                }
            return
        sanitized = {
            "ready": payload["ready"],
            "cloud_fresh": payload["cloud_fresh"],
            "odom_fresh": payload["odom_fresh"],
            "localized": payload["localized"],
            "publisher_counts": sanitized_counts,
            "cloud_error": str(payload.get("cloud_error", ""))[:160],
            "odom_error": str(payload.get("odom_error", ""))[:160],
            "input_points": input_points,
            "accepted_points": accepted_points,
            "error": None,
        }
        with self._navigation_lock:
            self._navigation_runtime_health_received = now
            self._navigation_runtime_health = sanitized

    def _navigation_localization_callback(self, message: Any) -> None:
        now = time.monotonic()
        node = self._node_getter()
        try:
            publishers = (
                node.count_publishers(NAVIGATION_LOCALIZATION_POSE_TOPIC)
                if node
                else 0
            )
        except Exception:
            publishers = 0
        if publishers != 1:
            with self._navigation_lock:
                self._navigation_validated_receipts[
                    NAVIGATION_LOCALIZATION_POSE_TOPIC
                ] = 0.0
            self.deactivate(
                f"expected one localization pose publisher, found {publishers}"
            )
            return
        try:
            pose = message.pose.pose
            x = float(pose.position.x)
            y = float(pose.position.y)
            orientation = pose.orientation
            yaw = math.atan2(
                2.0
                * (
                    orientation.w * orientation.z
                    + orientation.x * orientation.y
                ),
                1.0
                - 2.0
                * (
                    orientation.y * orientation.y
                    + orientation.z * orientation.z
                ),
            )
            x, y, yaw = self.pose_values(x, y, yaw)
        except (AttributeError, TypeError, ValueError, CommandValidationError) as exc:
            with self._navigation_lock:
                self._navigation_validated_receipts[
                    NAVIGATION_LOCALIZATION_POSE_TOPIC
                ] = 0.0
                active = bool(self._navigation.get("active"))
            if active:
                self.deactivate(f"invalid localization pose: {exc}")
            return
        self._tick(NAVIGATION_LOCALIZATION_POSE_TOPIC, now)
        with self._navigation_lock:
            self._navigation_validated_receipts[
                NAVIGATION_LOCALIZATION_POSE_TOPIC
            ] = now
            if not self._navigation.get("active"):
                return
            self._navigation["localization"] = {
                "state": "localized",
                "pose": {"x": x, "y": y, "yaw": yaw},
            }
            self._navigation["seq"] += 1

    def _navigation_next_sequence_locked(self) -> int:
        self._navigation_sequence += 1
        return self._navigation_sequence

    def _navigation_runtime_health_snapshot(self, now: float) -> Dict[str, Any]:
        with self._navigation_lock:
            health = copy.deepcopy(self._navigation_runtime_health)
            received = self._navigation_runtime_health_received
        age = None if received <= 0.0 else max(0.0, now - received)
        health["age_s"] = None if age is None else round(age, 3)
        health["fresh"] = bool(age is not None and age <= 0.75)
        return health

    def _navigation_validated_recency(
        self,
        topic: str,
        now: float,
        maximum_age: float,
    ) -> tuple[bool, Optional[float]]:
        """Read only a safety-owned receipt populated by its fixed callback."""

        with self._navigation_lock:
            received = float(self._navigation_validated_receipts.get(topic, 0.0))
        age = None if received <= 0.0 else max(0.0, now - received)
        return bool(age is not None and age <= maximum_age), age

    def _navigation_source_count(self, topic: str) -> int:
        node = self._node_getter()
        try:
            return int(node.count_publishers(topic)) if node else 0
        except Exception:
            return 0

    def _navigation_sensor_interlock_reason(
        self,
        now: float,
        *,
        require_localized: bool,
    ) -> Optional[str]:
        """Return a fail-closed reason for the trusted navigation inputs."""

        health = self._navigation_runtime_health_snapshot(now)
        if not health.get("fresh"):
            return "navigation runtime health is stale"
        if not health.get("cloud_fresh") or not health.get("odom_fresh"):
            return "navigation localization inputs are stale"
        if require_localized and (
            not health.get("ready") or not health.get("localized")
        ):
            return "navigation localization is not ready"

        required_topics = {
            "/scan": 0.75,
            NAVIGATION_FAST_LIO_ODOM_TOPIC: 0.75,
            NAVIGATION_CONTROLLER_ODOM_TOPIC: 0.75,
        }
        if require_localized:
            required_topics.update(
                {
                    NAVIGATION_LOCALIZATION_POSE_TOPIC: 1.0,
                    NAVIGATION_CMD_VEL_TOPIC: 0.25,
                }
            )
        for topic, maximum_age in required_topics.items():
            if self._navigation_source_count(topic) != 1:
                return f"expected one publisher for {topic}"
            # cmd_vel may be silent while stopped; uniqueness is its liveness
            # property. Other topics require a validated callback receipt.
            if topic in self._navigation_validated_receipts:
                recent, _ = self._navigation_validated_recency(
                    topic,
                    now,
                    maximum_age,
                )
            else:
                recent = topic == NAVIGATION_CMD_VEL_TOPIC
            if not recent:
                return f"navigation input {topic} is stale"
        return None

    def _navigation_prelocalization_reason(
        self,
        now: float,
        *,
        ready_after: float = 0.0,
    ) -> Optional[str]:
        """Require health emitted by this startup and currently fresh inputs."""

        with self._navigation_lock:
            health_received = self._navigation_runtime_health_received
            controller_odom_received = self._navigation_validated_receipts[
                NAVIGATION_CONTROLLER_ODOM_TOPIC
            ]
        if ready_after > 0.0 and health_received < ready_after:
            return "navigation runtime health has not started for this session"
        if ready_after > 0.0 and controller_odom_received < ready_after:
            return "controller odometry has not advanced for this session"
        return self._navigation_sensor_interlock_reason(
            now,
            require_localized=False,
        )

    def _navigation_issue_stop(self, reason: str) -> None:
        """Send a signed zero/StopMove independent of the current goal state."""

        with self._control_port.operation_lock:
            with self._navigation_lock:
                token = self._navigation_token
                binding = self._navigation_binding
                sequence = (
                    self._navigation_next_sequence_locked()
                    if token and binding
                    else -1
                )
                self._navigation["last_cmd_at"] = 0.0
                self._navigation["last_cmd"] = {
                    "vx": 0.0,
                    "vy": 0.0,
                    "wz": 0.0,
                }
                self._navigation["seq"] += 1
            submitted = False
            if token and binding:
                try:
                    self._control_port.manager.submit_drive(
                        token,
                        binding,
                        sequence,
                        vx=0.0,
                        vy=0.0,
                        wz=0.0,
                        speed_scale=1.0,
                        deadman=False,
                        client_age_s=0.0,
                    )
                    submitted = True
                except ControlError:
                    pass
            if not submitted:
                self._control_port.publish_outputs(
                    [
                        {
                            "type": "stop",
                            "reason": str(reason)[:160] or "navigation stop",
                            "velocity": {"vx": 0.0, "vy": 0.0, "wz": 0.0},
                            "created_at": time.monotonic(),
                        }
                    ]
                )
            self._control_port.flush_outputs()

    def keepalive_locked(self, now: float) -> Optional[str]:
        """Refresh the internal autonomous lease or return a failure reason."""

        with self._navigation_lock:
            if not self._navigation.get("active"):
                return None
            token = self._navigation_token
            binding = self._navigation_binding
            if not token or not binding:
                return "navigation_lease_missing"
            if now - self._navigation_last_heartbeat < 0.50:
                return None
            sequence = self._navigation_next_sequence_locked()
        try:
            self._control_port.manager.heartbeat(token, binding, sequence)
        except ControlError as exc:
            return f"navigation heartbeat failed: {exc}"
        with self._navigation_lock:
            if token == self._navigation_token:
                self._navigation_last_heartbeat = now
        return None

    def reconcile_control_locked(self, now: float) -> Optional[str]:
        """Recheck autonomous lease and input gates around every control tick."""

        with self._navigation_lock:
            if not self._navigation.get("active"):
                return None
            goal_state = str(
                (self._navigation.get("goal") or {}).get("state", "idle")
            )
        snapshot = self._control_port.manager.snapshot()
        lease = snapshot.get("lease", {})
        if not lease.get("active") or lease.get("input_source") != "navigation":
            return "navigation control lease was lost"
        return self._navigation_sensor_interlock_reason(
            now,
            require_localized=goal_state in {"pending", "active", "canceling"},
        )

    def submit_velocity(self, vx: float, vy: float, wz: float) -> None:
        with self._control_port.operation_lock:
            with self._navigation_lock:
                if not self._navigation.get("active"):
                    return
                goal_state = str(
                    (self._navigation.get("goal") or {}).get("state", "idle")
                )
                token = self._navigation_token
                binding = self._navigation_binding
            snapshot = self._control_port.manager.snapshot()
            limits = snapshot.get("limits", {})
            vx_limit = max(0.01, float(limits.get("vx_mps", 0.30)))
            vy_limit = max(0.01, float(limits.get("vy_mps", 0.20)))
            wz_limit = max(0.05, float(limits.get("wz_rps", 0.50)))
            bounded = {
                "vx": max(-vx_limit, min(vx_limit, float(vx))),
                "vy": max(-vy_limit, min(vy_limit, float(vy))),
                "wz": max(-wz_limit, min(wz_limit, float(wz))),
            }
            deadman = any(abs(value) > 1e-4 for value in bounded.values())
            if not deadman:
                self._navigation_issue_stop("Nav2 requested zero velocity")
                return
            # A controller sample can race goal acceptance. Non-zero motion
            # remains closed until the exact goal generation is active.
            if goal_state != "active":
                self._navigation_issue_stop("navigation goal is not active")
                return
            interlock = self._navigation_sensor_interlock_reason(
                time.monotonic(),
                require_localized=True,
            )
            if interlock:
                self.deactivate(interlock)
                return
            try:
                with self._navigation_lock:
                    sequence = self._navigation_next_sequence_locked()
                self._control_port.manager.submit_drive(
                    token,
                    binding,
                    sequence,
                    vx=bounded["vx"] / vx_limit,
                    vy=bounded["vy"] / vy_limit,
                    wz=bounded["wz"] / wz_limit,
                    speed_scale=1.0,
                    deadman=deadman,
                    client_age_s=0.0,
                )
                now = time.monotonic()
                with self._navigation_lock:
                    if token == self._navigation_token:
                        self._navigation["last_cmd_at"] = now
                        self._navigation["last_cmd"] = bounded
                        self._navigation["seq"] += 1
                self._control_port.flush_outputs()
            except ControlError as exc:
                self.deactivate(f"navigation command rejected: {exc}")

    def _navigation_cmd_vel_callback(self, message: Any) -> None:
        try:
            values = (
                float(message.linear.x),
                float(message.linear.y),
                float(message.angular.z),
            )
            if not all(math.isfinite(value) for value in values):
                raise ValueError("non-finite Nav2 velocity")
        except (AttributeError, TypeError, ValueError):
            self.deactivate("invalid Nav2 velocity")
            return
        node = self._node_getter()
        try:
            publishers = (
                node.count_publishers(NAVIGATION_CMD_VEL_TOPIC) if node else 0
            )
        except Exception:
            publishers = 0
        if publishers != 1:
            self.deactivate(
                f"expected one Nav2 velocity publisher, found {publishers}"
            )
            return
        self.submit_velocity(*values)

    def _navigation_require_pinned_map_locked(
        self,
        map_id: str,
        map_revision: str,
    ) -> None:
        if not self._navigation.get("active"):
            raise ControlDisabled("navigation is not active")
        active_map = self._navigation.get("map") or {}
        if (
            str(map_id) != str(active_map.get("id", ""))
            or str(map_revision).lower()
            != str(active_map.get("revision", "")).lower()
        ):
            raise CommandValidationError(
                "navigation map revision does not match the active session"
            )

    def set_initial_pose(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: object,
        y: object,
        yaw: object,
    ) -> Dict[str, Any]:
        x_value, y_value, yaw_value = self.pose_values(x, y, yaw)
        with self._control_port.operation_lock:
            interlock = self._navigation_sensor_interlock_reason(
                time.monotonic(),
                require_localized=False,
            )
            if interlock:
                raise ControlDisabled(interlock)
            with self._navigation_lock:
                self._navigation_require_pinned_map_locked(map_id, map_revision)
                goal_state = str(
                    (self._navigation.get("goal") or {}).get("state", "idle")
                )
                if goal_state in {"pending", "active", "canceling"}:
                    raise LeaseBusy(
                        "cancel the active goal before resetting localization"
                    )
                publisher = self._navigation_initial_pose_publisher
            if publisher is None:
                raise ControlDisabled("initial-pose publisher is unavailable")
            message = self._new_stamped_pose(x_value, y_value, yaw_value)
            message.pose.covariance = [0.0] * 36
            message.pose.covariance[0] = 0.25
            message.pose.covariance[7] = 0.25
            message.pose.covariance[35] = 0.06853891945200942
            publisher.publish(message)
            with self._navigation_lock:
                self._navigation["localization"] = {
                    "state": "localizing",
                    "pose": {"x": x_value, "y": y_value, "yaw": yaw_value},
                }
                self._navigation["seq"] += 1
        return self.runtime_snapshot()

    def _navigation_feedback_callback(
        self,
        generation: int,
        goal_id: str,
        message: Any,
    ) -> None:
        feedback = getattr(message, "feedback", None)
        with self._navigation_lock:
            goal = dict(self._navigation.get("goal") or {})
            if (
                generation != self._navigation_goal_generation
                or goal.get("goal_id") != goal_id
                or goal.get("state") not in {"pending", "active"}
            ):
                return
            try:
                distance = float(
                    getattr(feedback, "distance_remaining", float("nan"))
                )
                goal["distance_remaining"] = (
                    round(max(0.0, distance), 3)
                    if math.isfinite(distance)
                    else None
                )
            except (TypeError, ValueError):
                goal["distance_remaining"] = None
            goal["navigation_time"] = self._duration_seconds(
                getattr(feedback, "navigation_time", None)
            )
            try:
                goal["recoveries"] = max(
                    0,
                    int(getattr(feedback, "number_of_recoveries", 0)),
                )
            except (TypeError, ValueError):
                goal["recoveries"] = 0
            # Feedback can be scheduled before the goal-response callback.
            if self._navigation_goal_handle is not None:
                goal["state"] = "active"
            self._navigation["goal"] = goal
            self._navigation["seq"] += 1

    def _navigation_goal_response_callback(
        self,
        generation: int,
        goal_id: str,
        future: Any,
    ) -> None:
        try:
            handle = future.result()
        except Exception as exc:
            handle = None
            error = f"NavigateToPose request failed: {exc}"[:200]
        else:
            error = "NavigateToPose goal was rejected"
        with self._navigation_lock:
            goal = dict(self._navigation.get("goal") or {})
            stale = (
                generation != self._navigation_goal_generation
                or goal.get("goal_id") != goal_id
            )
            cancel_requested = self._navigation_cancel_requested
            if (
                not stale
                and handle is not None
                and bool(getattr(handle, "accepted", False))
            ):
                self._navigation_goal_handle = handle
                goal["state"] = "canceling" if cancel_requested else "active"
                self._navigation["goal"] = goal
                self._navigation["seq"] += 1
            elif not stale:
                goal["state"] = "failed"
                goal["error"] = error
                self._navigation["goal"] = goal
                self._navigation["seq"] += 1
        if stale:
            self._navigation_cancel_handle(handle)
            return
        if handle is None or not bool(getattr(handle, "accepted", False)):
            self._navigation_issue_stop(error)
            return
        if cancel_requested:
            self._navigation_cancel_handle(handle)
        try:
            result_future = handle.get_result_async()
            result_future.add_done_callback(
                lambda completed, g=generation, i=goal_id: self._navigation_result_callback(
                    g,
                    i,
                    completed,
                )
            )
        except Exception as exc:
            with self._navigation_lock:
                goal = dict(self._navigation.get("goal") or {})
                if (
                    generation == self._navigation_goal_generation
                    and goal.get("goal_id") == goal_id
                ):
                    goal["state"] = "failed"
                    goal["error"] = (
                        f"NavigateToPose result unavailable: {exc}"[:200]
                    )
                    self._navigation["goal"] = goal
                    self._navigation["seq"] += 1
            self._navigation_issue_stop("NavigateToPose result unavailable")

    def _navigation_result_callback(
        self,
        generation: int,
        goal_id: str,
        future: Any,
    ) -> None:
        try:
            wrapped = future.result()
            status = int(getattr(wrapped, "status", 0))
            error = None
        except Exception as exc:
            status = 0
            error = f"NavigateToPose result failed: {exc}"[:200]
        state = {4: "succeeded", 5: "canceled", 6: "failed"}.get(
            status,
            "failed",
        )
        with self._navigation_lock:
            goal = dict(self._navigation.get("goal") or {})
            if (
                generation != self._navigation_goal_generation
                or goal.get("goal_id") != goal_id
            ):
                return
            goal["state"] = state
            goal["error"] = (
                error if error else ("navigation aborted" if status == 6 else None)
            )
            self._navigation["goal"] = goal
            self._navigation_goal_handle = None
            self._navigation_cancel_requested = False
            self._navigation["seq"] += 1
        self._navigation_issue_stop(f"navigation goal {state}")

    def send_goal(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: object,
        y: object,
        yaw: object,
    ) -> Dict[str, Any]:
        x_value, y_value, yaw_value = self.pose_values(x, y, yaw)
        with self._control_port.operation_lock:
            interlock = self._navigation_sensor_interlock_reason(
                time.monotonic(),
                require_localized=True,
            )
            if interlock:
                raise ControlDisabled(interlock)
            with self._navigation_lock:
                self._navigation_require_pinned_map_locked(map_id, map_revision)
                if (
                    self._navigation.get("localization") or {}
                ).get("state") != "localized":
                    raise ControlDisabled(
                        "a fresh localized pose is required before sending a goal"
                    )
                current = self._navigation.get("goal") or {}
                if current.get("state") in {"pending", "active", "canceling"}:
                    raise LeaseBusy("another navigation goal is active")
                client = self._navigation_action_client
                if client is None or not client.server_is_ready():
                    raise ControlDisabled(
                        "NavigateToPose action server is unavailable"
                    )
                goal_id = secrets.token_hex(16)
                self._navigation_goal_generation += 1
                generation = self._navigation_goal_generation
                self._navigation_cancel_requested = False
                self._navigation_goal_handle = None
                self._navigation["goal"] = {
                    "state": "pending",
                    "goal_id": goal_id,
                    "pose": {"x": x_value, "y": y_value, "yaw": yaw_value},
                    "distance_remaining": None,
                    "navigation_time": None,
                    "recoveries": 0,
                    "error": None,
                }
                self._navigation["seq"] += 1
                action_type = self._navigation_action_type
            stamped = self._new_stamped_pose(x_value, y_value, yaw_value)
            goal_message = action_type.Goal()
            goal_message.pose.header = stamped.header
            goal_message.pose.pose = stamped.pose.pose
            try:
                future = client.send_goal_async(
                    goal_message,
                    feedback_callback=(
                        lambda feedback, g=generation, i=goal_id: (
                            self._navigation_feedback_callback(g, i, feedback)
                        )
                    ),
                )
                future.add_done_callback(
                    lambda completed, g=generation, i=goal_id: (
                        self._navigation_goal_response_callback(g, i, completed)
                    )
                )
            except Exception as exc:
                with self._navigation_lock:
                    goal = dict(self._navigation.get("goal") or {})
                    if goal.get("goal_id") == goal_id:
                        goal["state"] = "failed"
                        goal["error"] = (
                            f"NavigateToPose request failed: {exc}"[:200]
                        )
                        self._navigation["goal"] = goal
                        self._navigation["seq"] += 1
                self._navigation_issue_stop("NavigateToPose request failed")
                raise ControlDisabled(
                    "NavigateToPose request could not be sent"
                ) from exc
        return self.runtime_snapshot()

    def cancel_goal(self, *, goal_id: str) -> Dict[str, Any]:
        identifier = str(goal_id).strip()
        with self._control_port.operation_lock:
            with self._navigation_lock:
                goal = dict(self._navigation.get("goal") or {})
                if not identifier or identifier != goal.get("goal_id"):
                    raise CommandValidationError(
                        "goal id does not match the active navigation goal"
                    )
                if goal.get("state") not in {"pending", "active", "canceling"}:
                    return self.runtime_snapshot()
                goal["state"] = "canceling"
                self._navigation["goal"] = goal
                self._navigation_cancel_requested = True
                handle = self._navigation_goal_handle
                token = self._navigation_token
                binding = self._navigation_binding
                sequence = (
                    self._navigation_next_sequence_locked()
                    if token and binding
                    else -1
                )
                self._navigation["seq"] += 1
            # Stop first; cancellation acknowledgment can be delayed or lost.
            if token and binding:
                try:
                    self._control_port.manager.submit_drive(
                        token,
                        binding,
                        sequence,
                        vx=0.0,
                        vy=0.0,
                        wz=0.0,
                        speed_scale=1.0,
                        deadman=False,
                        client_age_s=0.0,
                    )
                except ControlError:
                    pass
            self._control_port.flush_outputs()
            self._navigation_cancel_handle(handle)
        return self.runtime_snapshot()

    def clear_costmaps(self, *, scope: str = "both") -> Dict[str, Any]:
        normalized = str(scope).strip().lower()
        if normalized not in {"both", "global", "local"}:
            raise CommandValidationError(
                "costmap scope must be both, global, or local"
            )
        with self._navigation_lock:
            if not self._navigation.get("active"):
                raise ControlDisabled("navigation is not active")
            goal_state = str(
                (self._navigation.get("goal") or {}).get("state", "idle")
            )
            if goal_state in {"pending", "active", "canceling"}:
                raise LeaseBusy("stop the active goal before clearing costmaps")
            now = time.monotonic()
            if now - self._navigation_last_clear < 2.0:
                raise LeaseBusy("wait before clearing costmaps again")
            services = [
                service
                for service in NAVIGATION_CLEAR_SERVICES
                if normalized == "both"
                or (normalized == "global" and "global_costmap" in service)
                or (normalized == "local" and "local_costmap" in service)
            ]
            clients = [
                (service, self._navigation_clear_clients.get(service))
                for service in services
            ]
            if any(
                client is None or not client.service_is_ready()
                for _, client in clients
            ):
                raise ControlDisabled("requested costmap service is unavailable")
            self._navigation["clear_costmaps"] = {
                "state": "running",
                "error": None,
            }
            self._navigation["seq"] += 1
            self._navigation_last_clear = now
            self._navigation_clear_generation += 1
            generation = self._navigation_clear_generation
            service_type = self._navigation_clear_service_type
        pending = {service for service, _ in clients}
        errors: list[str] = []

        def completed(service: str, future: Any) -> None:
            try:
                future.result()
            except Exception as exc:
                errors.append(f"{service}: {exc}"[:180])
            pending.discard(service)
            if pending:
                return
            with self._navigation_lock:
                if generation != self._navigation_clear_generation:
                    return
                self._navigation["clear_costmaps"] = {
                    "state": "failed" if errors else "succeeded",
                    "error": "; ".join(errors)[:240] if errors else None,
                }
                self._navigation["seq"] += 1

        for service, client in clients:
            future = client.call_async(service_type.Request())
            future.add_done_callback(
                lambda done, name=service: completed(name, done)
            )
        return self.runtime_snapshot()

    def runtime_snapshot(self) -> Dict[str, Any]:
        now = time.monotonic()
        with self._control_port.operation_lock:
            control = self._control_port.manager.snapshot()
            with self._navigation_lock:
                snapshot = copy.deepcopy(self._navigation)
                configured = self._navigation_transport_configured_locked()
                action_client = self._navigation_action_client
                clear_clients = dict(self._navigation_clear_clients)
        runtime_health = self._navigation_runtime_health_snapshot(now)
        node = self._node_getter()
        try:
            cmd_publishers = (
                node.count_publishers(NAVIGATION_CMD_VEL_TOPIC) if node else 0
            )
        except Exception:
            cmd_publishers = 0
        topic_publishers: Dict[str, int] = {}
        for topic in (
            "/scan",
            NAVIGATION_FAST_LIO_ODOM_TOPIC,
            NAVIGATION_CONTROLLER_ODOM_TOPIC,
            NAVIGATION_LOCALIZATION_POSE_TOPIC,
            NAVIGATION_RUNTIME_HEALTH_TOPIC,
        ):
            try:
                topic_publishers[topic] = (
                    node.count_publishers(topic) if node else 0
                )
            except Exception:
                topic_publishers[topic] = 0
        try:
            action_ready = bool(
                action_client and action_client.server_is_ready()
            )
        except Exception:
            action_ready = False
        clear_ready: Dict[str, bool] = {}
        for service in NAVIGATION_CLEAR_SERVICES:
            try:
                clear_ready[service] = bool(
                    clear_clients.get(service)
                    and clear_clients[service].service_is_ready()
                )
            except Exception:
                clear_ready[service] = False

        scan_fresh, raw_scan_age = self._navigation_validated_recency(
            "/scan",
            now,
            1.0,
        )
        fast_odom_fresh, raw_fast_odom_age = self._navigation_validated_recency(
            NAVIGATION_FAST_LIO_ODOM_TOPIC,
            now,
            1.0,
        )
        (
            controller_odom_fresh,
            raw_controller_odom_age,
        ) = self._navigation_validated_recency(
            NAVIGATION_CONTROLLER_ODOM_TOPIC,
            now,
            1.0,
        )
        (
            localization_fresh,
            raw_localization_age,
        ) = self._navigation_validated_recency(
            NAVIGATION_LOCALIZATION_POSE_TOPIC,
            now,
            1.5,
        )
        scan_age = None if raw_scan_age is None else round(raw_scan_age, 3)
        fast_odom_age = (
            None if raw_fast_odom_age is None else round(raw_fast_odom_age, 3)
        )
        controller_odom_age = (
            None
            if raw_controller_odom_age is None
            else round(raw_controller_odom_age, 3)
        )
        localization_age = (
            None
            if raw_localization_age is None
            else round(raw_localization_age, 3)
        )
        lease = control.get("lease", {})
        navigation_lease_active = bool(
            lease.get("active") and lease.get("input_source") == "navigation"
        )
        bridge_ready = bool(control.get("ready"))
        target_supported = self._control_port.go2_target()
        manual_active = bool(
            lease.get("active")
            and lease.get("input_source") in {"keyboard", "gamepad"}
        )
        active = bool(snapshot.get("active"))
        blockers: list[str] = []
        if not configured:
            blockers.append("navigation_transport_unavailable")
        if not target_supported:
            blockers.append("control_target_mismatch")
        if not bridge_ready:
            blockers.append("bridge_or_lowstate_unavailable")
        if manual_active:
            blockers.append("manual_control_active")
        if active and cmd_publishers != 1:
            blockers.append("cmd_vel_publisher_count")
        localization_state = str(
            (snapshot.get("localization") or {}).get("state", "uninitialized")
        )
        can_start = (
            configured
            and target_supported
            and bridge_ready
            and not manual_active
            and not active
        )
        scan_ready = scan_fresh and topic_publishers["/scan"] == 1
        fast_odom_ready = (
            fast_odom_fresh
            and topic_publishers[NAVIGATION_FAST_LIO_ODOM_TOPIC] == 1
        )
        controller_odom_ready = (
            controller_odom_fresh
            and topic_publishers[NAVIGATION_CONTROLLER_ODOM_TOPIC] == 1
        )
        localization_ready = (
            localization_fresh
            and topic_publishers[NAVIGATION_LOCALIZATION_POSE_TOPIC] == 1
        )
        runtime_prelocalization_ready = bool(
            runtime_health.get("fresh")
            and runtime_health.get("cloud_fresh")
            and runtime_health.get("odom_fresh")
            and topic_publishers[NAVIGATION_RUNTIME_HEALTH_TOPIC] == 1
        )
        runtime_ready = bool(
            runtime_prelocalization_ready
            and runtime_health.get("ready")
            and runtime_health.get("localized")
        )
        can_set_initial_pose = bool(
            active
            and scan_ready
            and fast_odom_ready
            and runtime_prelocalization_ready
        )
        can_send_goal = bool(
            active
            and action_ready
            and cmd_publishers == 1
            and scan_ready
            and fast_odom_ready
            and controller_odom_ready
            and localization_ready
            and runtime_ready
            and localization_state == "localized"
            and (snapshot.get("goal") or {}).get("state")
            not in {"pending", "active", "canceling"}
        )
        goal_state = str((snapshot.get("goal") or {}).get("state", "idle"))
        runtime_state = str(snapshot.get("state", "inactive"))
        cleanup_required = bool(
            active
            or navigation_lease_active
            or goal_state in {"pending", "active", "canceling"}
            or runtime_state in {"arming", "armed", "stopping"}
        )
        graph = self._graph_getter()
        snapshot.update(
            {
                "available": bool(configured and target_supported),
                "robot_online": bridge_ready,
                "command_topic": NAVIGATION_CMD_VEL_TOPIC,
                "readiness": {
                    "transport": configured,
                    "map_server": bool(
                        graph.get("/map", {}).get("publishers", 0)
                    ),
                    "localization": localization_ready,
                    "planner": bool(
                        graph.get("/plan", {}).get("publishers", 0)
                    ),
                    "controller": cmd_publishers == 1,
                    "behavior": action_ready,
                    "cmd_bridge": bridge_ready,
                    "map": bool(graph.get("/map", {}).get("publishers", 0)),
                    "scan": scan_ready,
                    "odometry": fast_odom_ready and controller_odom_ready,
                    "localization_odometry": fast_odom_ready,
                    "controller_odometry": controller_odom_ready,
                    "runtime_health": runtime_ready,
                    "tf": bool(graph.get("/tf", {}).get("publishers", 0)),
                    "action_server": action_ready,
                    "costmap_services": clear_ready,
                    "cmd_vel_publishers": cmd_publishers,
                    "scan_publishers": topic_publishers["/scan"],
                    "odometry_publishers": topic_publishers[
                        NAVIGATION_FAST_LIO_ODOM_TOPIC
                    ],
                    "controller_odometry_publishers": topic_publishers[
                        NAVIGATION_CONTROLLER_ODOM_TOPIC
                    ],
                    "runtime_health_publishers": topic_publishers[
                        NAVIGATION_RUNTIME_HEALTH_TOPIC
                    ],
                    "localization_publishers": topic_publishers[
                        NAVIGATION_LOCALIZATION_POSE_TOPIC
                    ],
                    "scan_age_s": scan_age,
                    "odometry_age_s": fast_odom_age,
                    "controller_odometry_age_s": controller_odom_age,
                    "localization_age_s": localization_age,
                    "runtime_health_age_s": runtime_health.get("age_s"),
                },
                "safety": {
                    "can_start": can_start,
                    "can_set_initial_pose": can_set_initial_pose,
                    "can_send_goal": can_send_goal,
                    "blockers": blockers,
                },
                "manual_control_active": manual_active,
                "navigation_lease_active": navigation_lease_active,
                "cleanup_required": cleanup_required,
                "runtime_health": runtime_health,
                "bindings": {
                    "pointcloud": "/velodyne_points",
                    "scan": "/scan",
                    "localization_odometry": NAVIGATION_FAST_LIO_ODOM_TOPIC,
                    "controller_odometry": NAVIGATION_CONTROLLER_ODOM_TOPIC,
                    "localization_pose": NAVIGATION_LOCALIZATION_POSE_TOPIC,
                    "command": NAVIGATION_CMD_VEL_TOPIC,
                },
            }
        )
        last_cmd_at = float(snapshot.pop("last_cmd_at", 0.0) or 0.0)
        snapshot["command_age_s"] = (
            None
            if last_cmd_at <= 0.0
            else round(max(0.0, now - last_cmd_at), 3)
        )
        return snapshot
