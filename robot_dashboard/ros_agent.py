"""ROS 2 runtime used by the Robot Scope web agent."""

from __future__ import annotations

import copy
import ipaddress
import json
import math
import os
import platform
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rosidl_runtime_py.utilities import get_message
from std_msgs.msg import String

from .camera_decoder import H264JpegDecoder
from .capabilities import capabilities_for_robot_type
from .control import (
    ControlDisabled,
    LeaseBusy,
)
from .discovery import (
    infer_robot_type,
    is_local_robot_ipv4,
    normalize_hostname,
    robot_type_definition,
)
from .go2_multicast_camera import Go2MulticastCamera
from .remote_mjpeg_camera import REALSENSE_RELAY_HOST, RemoteMjpegCamera
from .public_diagnostics import public_diagnostic
from .ros.cameras import CAMERA_SOURCE_IDS, CameraHub, public_camera_status
from .ros.control_transport import (
    CONTROL_COMMAND_TOPIC,
    CONTROL_STATUS_TOPIC,
    ControlTransport,
)
from .ros.graph import RosGraphMonitor
from .ros.navigation_gateway import (
    NAVIGATION_ACTION,
    NAVIGATION_CLEAR_SERVICES,
    NAVIGATION_CMD_VEL_TOPIC,
    NAVIGATION_CONTROLLER_ODOM_TOPIC,
    NAVIGATION_FAST_LIO_ODOM_TOPIC,
    NAVIGATION_INITIAL_POSE_TOPIC,
    NAVIGATION_LOCALIZATION_POSE_TOPIC,
    NAVIGATION_ODOM_STAMP_MAX_AGE_S,
    NAVIGATION_ODOM_STAMP_MAX_FUTURE_S,
    NAVIGATION_RUNTIME_HEALTH_TOPIC,
    NavigationRosGateway,
    public_navigation_reason as _public_navigation_reason,
)
from .ros.pointcloud import PointCloudHub
from .ros.runtime import RosRuntime
from .ros.sources import (
    SOURCE_CATEGORIES,
    SOURCE_SELECTION_STATE_MAX_BYTES,
    SourceRegistry,
    pointcloud_source_metadata,
)
from .ros.telemetry import RateMeter, TelemetryHub
from .runtime_status import ros_transport_status
from .serializers import (
    classify_type,
    is_observable_type,
)


CAMERA_TYPES = {
    "sensor_msgs/msg/Image",
    "sensor_msgs/msg/CompressedImage",
    "unitree_go/msg/Go2FrontVideoData",
}

# Kept as explicit module exports while RosAgent remains the migration facade
# for fixed control/navigation/source contracts.  The component modules own
# implementation; callers and existing integrations may still import these
# stable constants from this compatibility surface.
__all__ = [
    "CAMERA_SOURCE_IDS",
    "CONTROL_COMMAND_TOPIC",
    "CONTROL_STATUS_TOPIC",
    "NAVIGATION_ACTION",
    "NAVIGATION_CLEAR_SERVICES",
    "NAVIGATION_CMD_VEL_TOPIC",
    "NAVIGATION_CONTROLLER_ODOM_TOPIC",
    "NAVIGATION_FAST_LIO_ODOM_TOPIC",
    "NAVIGATION_INITIAL_POSE_TOPIC",
    "NAVIGATION_LOCALIZATION_POSE_TOPIC",
    "NAVIGATION_ODOM_STAMP_MAX_AGE_S",
    "NAVIGATION_ODOM_STAMP_MAX_FUTURE_S",
    "NAVIGATION_RUNTIME_HEALTH_TOPIC",
    "SOURCE_SELECTION_STATE_MAX_BYTES",
    "_public_navigation_reason",
    "RosAgent",
]


class RosAgent:
    """ROS observability agent with an isolated, signed control transport."""

    MIN_CLOUD_POINTS = PointCloudHub.MIN_CLOUD_POINTS
    MAX_CUSTOM_CLOUD_POINTS = PointCloudHub.MAX_CUSTOM_CLOUD_POINTS

    def __init__(
        self,
        robot_ip: str = "",
        profile_path: Optional[str] = None,
        cloud_max_points: Optional[int] = 18000,
        source_selection_path: Optional[str] = None,
    ) -> None:
        self.robot_ip = self._valid_ip(robot_ip)
        normalized_cloud_max_points = self._normalize_cloud_max_points(cloud_max_points)
        self.profile = self._load_profile(profile_path)
        self._startup_profile_name = str(self.profile.get("name", "Generic ROS 2"))
        self._robot_type = infer_robot_type(self.profile)
        # These values describe the immutable ROS/DDS control transport that
        # was constructed at process startup.  Runtime UI selection only
        # changes observation/display metadata; it never retargets the bridge.
        self._startup_robot_type = self._robot_type
        self._startup_robot_ip = self.robot_ip
        self._robot_target_connected = bool(self.robot_ip)
        self._target_restart_required = False
        self._robot_hostname = ""
        self._robot_model = (
            robot_type_definition(self._robot_type)["model"] if self._robot_type else None
        )
        cloud_radius_limit = max(
            5.0,
            min(float(self.profile.get("cloud_radius_limit_m", 500.0)), 10_000.0),
        )
        cloud_frame_interval_s = max(
            0.10,
            min(float(self.profile.get("pointcloud_frame_interval_s", 0.18)), 1.0),
        )

        self._ros_runtime = RosRuntime()
        self._lock = self._ros_runtime.lock
        self._graph_monitor = RosGraphMonitor(self._lock)
        joint_stale_after = max(
            0.2,
            min(float(self.profile.get("joint_state_stale_after_s", 1.0)), 10.0),
        )
        pose_stale_after = max(
            0.25,
            min(float(self.profile.get("odometry_stale_after_s", 1.5)), 10.0),
        )
        pose_position_limit = max(
            1.0,
            min(float(self.profile.get("pose_position_limit_m", 10_000.0)), 1_000_000.0),
        )
        self._telemetry_hub = TelemetryHub(
            self._lock,
            joint_stale_after_s=joint_stale_after,
            pose_stale_after_s=pose_stale_after,
            pose_position_limit_m=pose_position_limit,
        )
        self._source_registry = SourceRegistry(self.profile, source_selection_path)
        self._pointcloud_hub = PointCloudHub(
            self._lock,
            max_points=normalized_cloud_max_points,
            radius_limit_m=cloud_radius_limit,
            frame_interval_s=cloud_frame_interval_s,
        )
        self._camera_hub = CameraHub(
            self._lock,
            tick=self._tick,
            selected_ros_topic=lambda: self._sources.get("camera", ""),
        )
        self._camera_decoder = H264JpegDecoder(self._camera_hub.decoded_callback)
        direct_camera_profile = self.profile.get("direct_camera", {})
        if not isinstance(direct_camera_profile, dict):
            direct_camera_profile = {}
        configured_interface = str(direct_camera_profile.get("interface", "")).strip()
        runtime_interface = (
            os.environ.get("ROBOT_SCOPE_CAMERA_INTERFACE", "").strip()
            or os.environ.get("ROBOT_SCOPE_DDS_INTERFACE", "").strip()
            or configured_interface
        )
        allowed_interfaces_value = direct_camera_profile.get("allowed_interfaces", [])
        allowed_interfaces = (
            [str(value) for value in allowed_interfaces_value]
            if isinstance(allowed_interfaces_value, list)
            else []
        )
        # The profile protects the camera transport from HTTP-selected network
        # devices. A host installer may use a different predictable NIC name
        # than the reference ``eno1``. Treat the trusted server environment as
        # an additional exact allowlist entry only when camera and Go2 DDS use
        # the same interface; arbitrary runtime source selection remains
        # impossible.
        configured_go2_interface = os.environ.get(
            "ROBOT_SCOPE_GO2_INTERFACE", ""
        ).strip()
        if runtime_interface and runtime_interface == configured_go2_interface:
            allowed_interfaces.append(runtime_interface)
        self._direct_camera = Go2MulticastCamera(
            self._camera_hub.direct_callback,
            enabled=(
                self._startup_robot_type == "go2"
                and bool(direct_camera_profile.get("enabled", False))
            ),
            interface=runtime_interface,
            allowed_interfaces=allowed_interfaces,
            width=direct_camera_profile.get("width", 1280),
            height=direct_camera_profile.get("height", 720),
            fps_limit=direct_camera_profile.get("fps_limit", 15),
            jpeg_quality=direct_camera_profile.get("jpeg_quality", 80),
            stale_after_s=direct_camera_profile.get("stale_after_s", 3.0),
            startup_frame_timeout_s=direct_camera_profile.get(
                "startup_frame_timeout_s", 8.0
            ),
            frame_timeout_s=direct_camera_profile.get("frame_timeout_s"),
            restart_initial_s=direct_camera_profile.get("restart_initial_s", 0.5),
            restart_max_s=direct_camera_profile.get("restart_max_s", 8.0),
        )
        remote_cameras_profile = self.profile.get("remote_cameras", {})
        if not isinstance(remote_cameras_profile, dict):
            remote_cameras_profile = {}
        realsense_profile = remote_cameras_profile.get("realsense_color", {})
        if not isinstance(realsense_profile, dict):
            realsense_profile = {}
        allowed_urls_value = realsense_profile.get("allowed_urls", [])
        allowed_urls = (
            [str(value) for value in allowed_urls_value]
            if isinstance(allowed_urls_value, list)
            else []
        )
        runtime_realsense_host = os.environ.get(
            "ROBOT_SCOPE_REALSENSE_RELAY_HOST", ""
        ).strip()
        realsense_host = runtime_realsense_host or REALSENSE_RELAY_HOST
        realsense_url = str(realsense_profile.get("url", ""))
        if runtime_realsense_host:
            # The host-only override keeps scheme, port and path fixed while
            # allowing the relay management link to move from wired to Wi-Fi.
            # RemoteMjpegCamera validates the address before opening a socket.
            realsense_url = f"http://{runtime_realsense_host}:8090/stream"
            allowed_urls = [realsense_url]
        self._remote_camera = RemoteMjpegCamera(
            self._camera_hub.remote_callback,
            enabled=(
                self._startup_robot_type == "go2"
                and bool(realsense_profile.get("enabled", False))
            ),
            url=realsense_url,
            allowed_urls=allowed_urls,
            relay_host=realsense_host,
            source_id="realsense_color",
            source_label=str(
                realsense_profile.get("label", "RealSense color camera")
            ),
            stale_after_s=realsense_profile.get("stale_after_s", 3.0),
            request_timeout_s=realsense_profile.get("request_timeout_s", 6.0),
            restart_initial_s=realsense_profile.get("restart_initial_s", 0.5),
            restart_max_s=realsense_profile.get("restart_max_s", 8.0),
        )
        self._camera_hub.attach(
            self._direct_camera,
            self._remote_camera,
            self._camera_decoder,
        )
        self._control_transport = ControlTransport(
            self.profile,
            ensure_target=self._ensure_go2_control_target,
            go2_target=self._go2_control_target,
        )
        self._navigation_gateway = NavigationRosGateway(
            self._control_transport,
            node_getter=lambda: self._node,
            tick=self._tick,
            graph_getter=lambda: self._graph,
            profile=self.profile,
        )
        self._network_cache: Tuple[float, bool, Optional[float]] = (0.0, False, None)

    # Compatibility properties keep the migration facade stable while the
    # focused components own all control/navigation-plane mutable state.
    @property
    def _stop_event(self) -> threading.Event:
        return self._ros_runtime.stop_event

    @property
    def _thread(self) -> Optional[threading.Thread]:
        return self._ros_runtime.thread

    @_thread.setter
    def _thread(self, value: Optional[threading.Thread]) -> None:
        self._ros_runtime.thread = value

    @property
    def _node(self) -> Optional[Node]:
        return self._ros_runtime.node

    @_node.setter
    def _node(self, value: Optional[Node]) -> None:
        self._ros_runtime.node = value

    @property
    def _executor(self) -> Optional[MultiThreadedExecutor]:
        return self._ros_runtime.executor

    @_executor.setter
    def _executor(self, value: Optional[MultiThreadedExecutor]) -> None:
        self._ros_runtime.executor = value

    @property
    def _started_at(self) -> float:
        return self._ros_runtime.started_at

    @property
    def _ready(self) -> bool:
        return self._ros_runtime.ready

    @_ready.setter
    def _ready(self, value: bool) -> None:
        self._ros_runtime.ready = bool(value)

    @property
    def _last_error(self) -> str:
        return self._ros_runtime.last_error

    @_last_error.setter
    def _last_error(self, value: str) -> None:
        self._ros_runtime.last_error = str(value)

    # Phase 5 compatibility properties forward legacy private probes to the
    # single control/navigation component owners. They never duplicate motion
    # state, keys, leases, freshness receipts, or ROS handles.
    @property
    def _control_manager(self) -> Any:
        return self._control_transport.manager

    @_control_manager.setter
    def _control_manager(self, value: Any) -> None:
        self._control_transport.manager = value

    @property
    def _control_operation_lock(self) -> threading.RLock:
        return self._control_transport.operation_lock

    @property
    def _control_transport_lock(self) -> threading.RLock:
        return self._control_transport.transport_lock

    @property
    def _control_bridge_key(self) -> Optional[bytes]:
        return self._control_transport.bridge_key

    @_control_bridge_key.setter
    def _control_bridge_key(self, value: Optional[bytes]) -> None:
        self._control_transport.bridge_key = value

    @property
    def _control_bridge_epoch(self) -> str:
        return self._control_transport.bridge_epoch

    @_control_bridge_epoch.setter
    def _control_bridge_epoch(self, value: str) -> None:
        self._control_transport.bridge_epoch = str(value)

    @property
    def _control_bridge_seq(self) -> int:
        return self._control_transport.bridge_seq

    @_control_bridge_seq.setter
    def _control_bridge_seq(self, value: int) -> None:
        self._control_transport.bridge_seq = int(value)

    @property
    def _control_source_id(self) -> str:
        return self._control_transport.source_id

    @property
    def _control_status_timeout_s(self) -> float:
        return self._control_transport.status_timeout_s

    @property
    def _control_lowstate_timeout_s(self) -> float:
        return self._control_transport.lowstate_timeout_s

    @property
    def _control_expected_bare_sport_publishers(self) -> int:
        return self._control_transport.expected_bare_sport_publishers

    @property
    def _control_callback_group(self) -> Any:
        return self._control_transport.callback_group

    @_control_callback_group.setter
    def _control_callback_group(self, value: Any) -> None:
        self._control_transport.callback_group = value

    @property
    def _control_command_publisher(self) -> Any:
        return self._control_transport.command_publisher

    @_control_command_publisher.setter
    def _control_command_publisher(self, value: Any) -> None:
        self._control_transport.command_publisher = value

    @property
    def _control_status_subscription(self) -> Any:
        return self._control_transport.status_subscription

    @_control_status_subscription.setter
    def _control_status_subscription(self, value: Any) -> None:
        self._control_transport.status_subscription = value

    @property
    def _control_timer(self) -> Any:
        return self._control_transport.timer

    @_control_timer.setter
    def _control_timer(self, value: Any) -> None:
        self._control_transport.timer = value

    @property
    def _control_status_received(self) -> float:
        return self._control_transport.status_received

    @_control_status_received.setter
    def _control_status_received(self, value: float) -> None:
        self._control_transport.status_received = float(value)

    @property
    def _control_status(self) -> Dict[str, Any]:
        return self._control_transport.status

    @_control_status.setter
    def _control_status(self, value: Dict[str, Any]) -> None:
        self._control_transport.status = value

    @property
    def _control_shutdown(self) -> bool:
        return self._control_transport.shutdown_started

    @_control_shutdown.setter
    def _control_shutdown(self, value: bool) -> None:
        self._control_transport.shutdown_started = bool(value)

    @property
    def _navigation_lock(self) -> threading.RLock:
        return self._navigation_gateway._navigation_lock

    @property
    def _navigation(self) -> Dict[str, Any]:
        return self._navigation_gateway._navigation

    @_navigation.setter
    def _navigation(self, value: Dict[str, Any]) -> None:
        self._navigation_gateway._navigation = value

    @property
    def _navigation_callback_group(self) -> Any:
        return self._navigation_gateway._navigation_callback_group

    @_navigation_callback_group.setter
    def _navigation_callback_group(self, value: Any) -> None:
        self._navigation_gateway._navigation_callback_group = value

    @property
    def _navigation_cmd_subscription(self) -> Any:
        return self._navigation_gateway._navigation_cmd_subscription

    @_navigation_cmd_subscription.setter
    def _navigation_cmd_subscription(self, value: Any) -> None:
        self._navigation_gateway._navigation_cmd_subscription = value

    @property
    def _navigation_health_subscriptions(self) -> Dict[str, Any]:
        return self._navigation_gateway._navigation_health_subscriptions

    @_navigation_health_subscriptions.setter
    def _navigation_health_subscriptions(self, value: Dict[str, Any]) -> None:
        self._navigation_gateway._navigation_health_subscriptions = value

    @property
    def _navigation_initial_pose_publisher(self) -> Any:
        return self._navigation_gateway._navigation_initial_pose_publisher

    @_navigation_initial_pose_publisher.setter
    def _navigation_initial_pose_publisher(self, value: Any) -> None:
        self._navigation_gateway._navigation_initial_pose_publisher = value

    @property
    def _navigation_pose_type(self) -> Any:
        return self._navigation_gateway._navigation_pose_type

    @_navigation_pose_type.setter
    def _navigation_pose_type(self, value: Any) -> None:
        self._navigation_gateway._navigation_pose_type = value

    @property
    def _navigation_action_type(self) -> Any:
        return self._navigation_gateway._navigation_action_type

    @_navigation_action_type.setter
    def _navigation_action_type(self, value: Any) -> None:
        self._navigation_gateway._navigation_action_type = value

    @property
    def _navigation_action_client(self) -> Any:
        return self._navigation_gateway._navigation_action_client

    @_navigation_action_client.setter
    def _navigation_action_client(self, value: Any) -> None:
        self._navigation_gateway._navigation_action_client = value

    @property
    def _navigation_clear_service_type(self) -> Any:
        return self._navigation_gateway._navigation_clear_service_type

    @_navigation_clear_service_type.setter
    def _navigation_clear_service_type(self, value: Any) -> None:
        self._navigation_gateway._navigation_clear_service_type = value

    @property
    def _navigation_clear_clients(self) -> Dict[str, Any]:
        return self._navigation_gateway._navigation_clear_clients

    @_navigation_clear_clients.setter
    def _navigation_clear_clients(self, value: Dict[str, Any]) -> None:
        self._navigation_gateway._navigation_clear_clients = value

    @property
    def _navigation_runtime_health_received(self) -> float:
        return self._navigation_gateway._navigation_runtime_health_received

    @_navigation_runtime_health_received.setter
    def _navigation_runtime_health_received(self, value: float) -> None:
        self._navigation_gateway._navigation_runtime_health_received = float(value)

    @property
    def _navigation_runtime_health(self) -> Dict[str, Any]:
        return self._navigation_gateway._navigation_runtime_health

    @_navigation_runtime_health.setter
    def _navigation_runtime_health(self, value: Dict[str, Any]) -> None:
        self._navigation_gateway._navigation_runtime_health = value

    @property
    def _navigation_odom_stamp_ns(self) -> Dict[str, int]:
        return self._navigation_gateway._navigation_odom_stamp_ns

    @_navigation_odom_stamp_ns.setter
    def _navigation_odom_stamp_ns(self, value: Dict[str, int]) -> None:
        self._navigation_gateway._navigation_odom_stamp_ns = value

    @property
    def _navigation_validated_receipts(self) -> Dict[str, float]:
        return self._navigation_gateway._navigation_validated_receipts

    @_navigation_validated_receipts.setter
    def _navigation_validated_receipts(self, value: Dict[str, float]) -> None:
        self._navigation_gateway._navigation_validated_receipts = value

    @property
    def _navigation_token(self) -> str:
        return self._navigation_gateway._navigation_token

    @_navigation_token.setter
    def _navigation_token(self, value: str) -> None:
        self._navigation_gateway._navigation_token = str(value)

    @property
    def _navigation_binding(self) -> str:
        return self._navigation_gateway._navigation_binding

    @_navigation_binding.setter
    def _navigation_binding(self, value: str) -> None:
        self._navigation_gateway._navigation_binding = str(value)

    @property
    def _navigation_goal_generation(self) -> int:
        return self._navigation_gateway._navigation_goal_generation

    @_navigation_goal_generation.setter
    def _navigation_goal_generation(self, value: int) -> None:
        self._navigation_gateway._navigation_goal_generation = int(value)

    @property
    def _navigation_goal_handle(self) -> Any:
        return self._navigation_gateway._navigation_goal_handle

    @_navigation_goal_handle.setter
    def _navigation_goal_handle(self, value: Any) -> None:
        self._navigation_gateway._navigation_goal_handle = value

    @property
    def _graph(self) -> Dict[str, Dict[str, Any]]:
        return self._graph_monitor.graph

    @_graph.setter
    def _graph(self, value: Dict[str, Dict[str, Any]]) -> None:
        self._graph_monitor.graph = value

    @property
    def _metrics(self) -> Dict[str, RateMeter]:
        return self._graph_monitor.metrics

    @_metrics.setter
    def _metrics(self, value: Dict[str, RateMeter]) -> None:
        self._graph_monitor.metrics = value

    @property
    def _subscriptions(self) -> Dict[str, Any]:
        return self._graph_monitor.subscriptions

    @property
    def _special_subscription_topics(self) -> Dict[str, str]:
        return self._graph_monitor.special_subscription_topics

    @property
    def _summaries(self) -> Dict[str, Dict[str, Any]]:
        return self._telemetry_hub.summaries

    @property
    def _summary_updated(self) -> Dict[str, float]:
        return self._telemetry_hub.summary_updated

    @property
    def _joints(self) -> Dict[str, Any]:
        return self._telemetry_hub.joints

    @_joints.setter
    def _joints(self, value: Dict[str, Any]) -> None:
        self._telemetry_hub.joints = value

    @property
    def _pose(self) -> Dict[str, Any]:
        return self._telemetry_hub.pose

    @_pose.setter
    def _pose(self, value: Dict[str, Any]) -> None:
        self._telemetry_hub.pose = value

    @property
    def _map(self) -> Dict[str, Any]:
        return self._telemetry_hub.map

    @_map.setter
    def _map(self, value: Dict[str, Any]) -> None:
        self._telemetry_hub.map = value

    @property
    def _joint_last_processed(self) -> float:
        return self._telemetry_hub.joint_last_processed

    @_joint_last_processed.setter
    def _joint_last_processed(self, value: float) -> None:
        self._telemetry_hub.joint_last_processed = value

    @property
    def _joint_stale_after(self) -> float:
        return self._telemetry_hub.joint_stale_after_s

    @property
    def _pose_stale_after(self) -> float:
        return self._telemetry_hub.pose_stale_after_s

    @property
    def _pose_position_limit(self) -> float:
        return self._telemetry_hub.pose_position_limit_m

    @property
    def _sources(self) -> Dict[str, str]:
        return self._source_registry.sources

    @_sources.setter
    def _sources(self, value: Dict[str, str]) -> None:
        self._source_registry.sources = value

    @property
    def _requested_sources(self) -> Dict[str, str]:
        return self._source_registry.requested_sources

    @_requested_sources.setter
    def _requested_sources(self, value: Dict[str, str]) -> None:
        self._source_registry.requested_sources = value

    @property
    def _source_selection_path(self) -> Optional[Path]:
        return self._source_registry.state_path

    @property
    def _source_selection_policies(self) -> Dict[str, Dict[str, Any]]:
        return self._source_registry.policies

    @property
    def _source_selection_overrides(self) -> Dict[str, Dict[str, str]]:
        return self._source_registry.overrides

    @_source_selection_overrides.setter
    def _source_selection_overrides(self, value: Dict[str, Dict[str, str]]) -> None:
        self._source_registry.overrides = value

    @property
    def _source_pins(self) -> set[str]:
        return self._source_registry.pins

    @_source_pins.setter
    def _source_pins(self, value: set[str]) -> None:
        self._source_registry.pins = value

    @property
    def _source_selection_origins(self) -> Dict[str, str]:
        return self._source_registry.origins

    @_source_selection_origins.setter
    def _source_selection_origins(self, value: Dict[str, str]) -> None:
        self._source_registry.origins = value

    @property
    def cloud_max_points(self) -> Optional[int]:
        return self._pointcloud_hub.max_points

    @cloud_max_points.setter
    def cloud_max_points(self, value: Optional[int]) -> None:
        self._pointcloud_hub.max_points = value

    @property
    def cloud_radius_limit(self) -> float:
        return self._pointcloud_hub.radius_limit_m

    @property
    def _cloud_frame_interval_s(self) -> float:
        return self._pointcloud_hub.base_frame_interval_s

    @property
    def _cloud(self) -> Dict[str, Any]:
        return self._pointcloud_hub.cloud

    @_cloud.setter
    def _cloud(self, value: Dict[str, Any]) -> None:
        self._pointcloud_hub.cloud = value

    @property
    def _cloud_stream_id(self) -> str:
        return self._pointcloud_hub.stream_id

    @property
    def _last_cloud_processed(self) -> float:
        return self._pointcloud_hub.last_processed

    @_last_cloud_processed.setter
    def _last_cloud_processed(self, value: float) -> None:
        self._pointcloud_hub.last_processed = value

    @property
    def _camera(self) -> Dict[str, Any]:
        return self._camera_hub.camera

    @_camera.setter
    def _camera(self, value: Dict[str, Any]) -> None:
        self._camera_hub.camera = value

    @property
    def _remote_camera_frame(self) -> Dict[str, Any]:
        return self._camera_hub.remote_frame

    @_remote_camera_frame.setter
    def _remote_camera_frame(self, value: Dict[str, Any]) -> None:
        self._camera_hub.remote_frame = value

    @property
    def _camera_stream_ids(self) -> Dict[str, str]:
        return self._camera_hub.stream_ids

    @property
    def _camera_demand_lock(self) -> threading.RLock:
        return self._camera_hub.demand_lock

    @property
    def _camera_accepting_demand(self) -> bool:
        return self._camera_hub.accepting_demand

    @_camera_accepting_demand.setter
    def _camera_accepting_demand(self, value: bool) -> None:
        self._camera_hub.accepting_demand = bool(value)

    @property
    def _camera_consumers(self) -> int:
        return self._camera_hub.consumers

    @property
    def _camera_demand_tokens(self) -> Dict[str, set[str]]:
        return self._camera_hub.demand_tokens

    @property
    def _camera_token_sources(self) -> Dict[str, str]:
        return self._camera_hub.token_sources

    @staticmethod
    def _bounded_control_timeout(
        value: object,
        *,
        default: float,
        low: float,
        high: float,
    ) -> float:
        return ControlTransport.bounded_timeout(
            value,
            default=default,
            low=low,
            high=high,
        )

    @staticmethod
    def _valid_ip(value: str) -> str:
        if not value:
            return ""
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            return ""

    @classmethod
    def _normalize_cloud_max_points(cls, value: Optional[int]) -> Optional[int]:
        return PointCloudHub.normalize_limit(value)

    def cloud_point_settings(self) -> Dict[str, Any]:
        return self._pointcloud_hub.settings()

    def _pointcloud_frame_interval(self, point_limit: Optional[int]) -> float:
        """Target at most ~4 MB/s of packed XYZ data per browser client."""

        return self._pointcloud_hub.frame_interval(point_limit)

    def set_cloud_max_points(self, value: Optional[int]) -> Dict[str, Any]:
        return self._pointcloud_hub.set_limit(
            value,
            self._sources.get("pointcloud", ""),
        )

    @staticmethod
    def _load_profile(path: Optional[str]) -> Dict[str, Any]:
        if not path:
            return {}
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _normalize_source_selection_path(value: Optional[str]) -> Optional[Path]:
        return SourceRegistry.normalize_state_path(value)

    @staticmethod
    def _valid_source_name(value: object) -> bool:
        return SourceRegistry.valid_source_name(value)

    def _source_profile_scope(self) -> Dict[str, str]:
        return self._source_registry.profile_scope()

    def _source_policies_from_profile(self) -> Dict[str, Dict[str, Any]]:
        return self._source_registry.policies_from_profile()

    def _validate_source_state_file(self, path: Path) -> os.stat_result:
        return SourceRegistry.validate_state_file(path)

    def _load_source_selection_overrides(self) -> Dict[str, Dict[str, str]]:
        return self._source_registry.load_overrides()

    def _apply_startup_source_selection(self) -> None:
        self._source_registry.apply_startup_selection()

    def _write_source_selection_overrides(
        self,
        overrides: Dict[str, Dict[str, str]],
    ) -> None:
        self._source_registry.write_overrides(overrides)

    def start(self) -> None:
        with self._camera_demand_lock:
            self._camera_accepting_demand = True
        self._ros_runtime.start(self._run)

    @staticmethod
    def _valid_camera_source_id(source_id: object) -> bool:
        return CameraHub.valid_source_id(source_id)

    def camera_stream_open(self, source_id: str = "go2_front") -> Dict[str, Any]:
        """Acquire one opaque, exactly-once demand token for a fixed source."""
        return self._camera_hub.stream_open(source_id)

    def camera_stream_close(
        self,
        source_id: str = "go2_front",
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Release a demand token once; duplicate/foreign closes are no-ops."""
        return self._camera_hub.stream_close(source_id, token)

    def _clear_camera_frame(self, source_id: str = "go2_front") -> None:
        """Drop only the selected source's frame between viewer sessions."""
        self._camera_hub.clear_frame(source_id)

    def stop(self) -> None:
        # Publish the manager's final signed stop while the ROS node and
        # executor are still alive.  The standalone bridge has its own watchdog
        # as a second line of defence if transport is already unavailable.
        self.navigation_deactivate("agent_stop")
        self.shutdown_control()
        self._ros_runtime.request_stop()
        self._camera_hub.shutdown()
        self._ros_runtime.shutdown_executor()
        self._ros_runtime.join()

    def _run(self) -> None:
        try:
            rclpy.init(args=None)
            node = Node("robot_scope_agent")
            executor = MultiThreadedExecutor(num_threads=4)
            executor.add_node(node)
            self._node = node
            self._executor = executor
            self._setup_control_transport(node)
            self._setup_navigation_transport(node)
            node.create_timer(2.0, self._refresh_graph)
            self._refresh_graph()
            with self._lock:
                self._ready = True
            while rclpy.ok() and not self._stop_event.is_set():
                executor.spin_once(timeout_sec=0.2)
        except Exception as exc:
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"
        finally:
            self.navigation_deactivate("ros_runtime_exit")
            self.shutdown_control()
            with self._lock:
                self._ready = False
            if self._node:
                try:
                    self._node.destroy_node()
                except Exception:
                    pass
            if rclpy.ok():
                try:
                    rclpy.shutdown()
                except Exception:
                    pass

    def _setup_control_transport(self, node: Node) -> None:
        self._control_transport.setup(node, self._control_tick)

    def _setup_navigation_transport(self, node: Node) -> None:
        self._navigation_gateway.setup(node)

    @staticmethod
    def _navigation_pose_values(
        x: object,
        y: object,
        yaw: object,
    ) -> tuple[float, float, float]:
        return NavigationRosGateway.pose_values(x, y, yaw)

    @staticmethod
    def _duration_seconds(value: Any) -> Optional[float]:
        return NavigationRosGateway._duration_seconds(value)

    def _new_stamped_pose(self, x: float, y: float, yaw: float) -> Any:
        return self._navigation_gateway._new_stamped_pose(x, y, yaw)

    def _navigation_transport_configured_locked(self) -> bool:
        return self._navigation_gateway._navigation_transport_configured_locked()

    def navigation_activate(
        self,
        *,
        map_id: str,
        map_revision: str,
        map_name: str = "",
        ready_after: float = 0.0,
    ) -> Dict[str, Any]:
        return self._navigation_gateway.activate(
            map_id=map_id,
            map_revision=map_revision,
            map_name=map_name,
            ready_after=ready_after,
        )

    def navigation_start_preflight(self) -> Dict[str, Any]:
        return self._navigation_gateway.start_preflight()

    def navigation_prelocalization_snapshot(
        self,
        *,
        ready_after: float = 0.0,
    ) -> Dict[str, Any]:
        return self._navigation_gateway.prelocalization_snapshot(
            ready_after=ready_after
        )

    def _navigation_cancel_handle(self, handle: Any) -> None:
        NavigationRosGateway._navigation_cancel_handle(handle)

    def navigation_deactivate(
        self,
        reason: str = "navigation_stop",
    ) -> Dict[str, Any]:
        return self._navigation_gateway.deactivate(reason)

    def _navigation_health_callback(self, topic: str, message: Any) -> None:
        self._navigation_gateway._navigation_health_callback(topic, message)

    def _navigation_validate_odom_stamp(self, topic: str, message: Any) -> int:
        return self._navigation_gateway._navigation_validate_odom_stamp(
            topic,
            message,
        )

    def _navigation_commit_odom_stamp(
        self,
        topic: str,
        stamp_ns: int,
    ) -> bool:
        return self._navigation_gateway._navigation_commit_odom_stamp(
            topic,
            stamp_ns,
        )

    def _navigation_runtime_health_callback(self, message: String) -> None:
        self._navigation_gateway._navigation_runtime_health_callback(message)

    def _navigation_localization_callback(self, message: Any) -> None:
        self._navigation_gateway._navigation_localization_callback(message)

    def _navigation_next_sequence_locked(self) -> int:
        return self._navigation_gateway._navigation_next_sequence_locked()

    def _navigation_runtime_health_snapshot(self, now: float) -> Dict[str, Any]:
        return self._navigation_gateway._navigation_runtime_health_snapshot(now)

    def _navigation_validated_recency(
        self,
        topic: str,
        now: float,
        maximum_age: float,
    ) -> tuple[bool, Optional[float]]:
        return self._navigation_gateway._navigation_validated_recency(
            topic,
            now,
            maximum_age,
        )

    def _navigation_source_count(self, topic: str) -> int:
        return self._navigation_gateway._navigation_source_count(topic)

    def _navigation_sensor_interlock_reason(
        self,
        now: float,
        *,
        require_localized: bool,
    ) -> Optional[str]:
        return self._navigation_gateway._navigation_sensor_interlock_reason(
            now,
            require_localized=require_localized,
        )

    def _navigation_prelocalization_reason(
        self,
        now: float,
        *,
        ready_after: float = 0.0,
    ) -> Optional[str]:
        return self._navigation_gateway._navigation_prelocalization_reason(
            now,
            ready_after=ready_after,
        )

    def _navigation_issue_stop(self, reason: str) -> None:
        self._navigation_gateway._navigation_issue_stop(reason)

    def _navigation_keepalive_locked(self, now: float) -> Optional[str]:
        return self._navigation_gateway.keepalive_locked(now)

    def _navigation_reconcile_control_locked(self, now: float) -> Optional[str]:
        return self._navigation_gateway.reconcile_control_locked(now)

    def _navigation_submit_velocity(self, vx: float, vy: float, wz: float) -> None:
        self._navigation_gateway.submit_velocity(vx, vy, wz)

    def _navigation_cmd_vel_callback(self, message: Any) -> None:
        self._navigation_gateway._navigation_cmd_vel_callback(message)

    def _navigation_require_pinned_map_locked(
        self,
        map_id: str,
        map_revision: str,
    ) -> None:
        self._navigation_gateway._navigation_require_pinned_map_locked(
            map_id,
            map_revision,
        )

    def navigation_set_initial_pose(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: object,
        y: object,
        yaw: object,
    ) -> Dict[str, Any]:
        return self._navigation_gateway.set_initial_pose(
            map_id=map_id,
            map_revision=map_revision,
            x=x,
            y=y,
            yaw=yaw,
        )

    def _navigation_feedback_callback(
        self,
        generation: int,
        goal_id: str,
        message: Any,
    ) -> None:
        self._navigation_gateway._navigation_feedback_callback(
            generation,
            goal_id,
            message,
        )

    def _navigation_goal_response_callback(
        self,
        generation: int,
        goal_id: str,
        future: Any,
    ) -> None:
        self._navigation_gateway._navigation_goal_response_callback(
            generation,
            goal_id,
            future,
        )

    def _navigation_result_callback(
        self,
        generation: int,
        goal_id: str,
        future: Any,
    ) -> None:
        self._navigation_gateway._navigation_result_callback(
            generation,
            goal_id,
            future,
        )

    def navigation_send_goal(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: object,
        y: object,
        yaw: object,
    ) -> Dict[str, Any]:
        return self._navigation_gateway.send_goal(
            map_id=map_id,
            map_revision=map_revision,
            x=x,
            y=y,
            yaw=yaw,
        )

    def navigation_cancel_goal(self, *, goal_id: str) -> Dict[str, Any]:
        return self._navigation_gateway.cancel_goal(goal_id=goal_id)

    def navigation_clear_costmaps(
        self,
        *,
        scope: str = "both",
    ) -> Dict[str, Any]:
        return self._navigation_gateway.clear_costmaps(scope=scope)

    def navigation_runtime_snapshot(self) -> Dict[str, Any]:
        return self._navigation_gateway.runtime_snapshot()

    @staticmethod
    def _control_status_readiness(
        payload: Dict[str, Any],
        *,
        lowstate_timeout_s: float,
        expected_bare_sport_publishers: int = 0,
    ) -> Tuple[bool, bool, str]:
        return ControlTransport.status_readiness(
            payload,
            lowstate_timeout_s=lowstate_timeout_s,
            expected_bare_sport_publishers=expected_bare_sport_publishers,
        )

    def _control_status_callback(self, message: String) -> None:
        self._control_transport.status_callback(message)

    def _set_control_readiness(
        self,
        *,
        bridge_ready: bool,
        lowstate_ready: bool,
    ) -> None:
        self._control_transport.set_readiness(
            bridge_ready=bridge_ready,
            lowstate_ready=lowstate_ready,
        )

    def _set_control_unready(self, message: str) -> None:
        self._control_transport.set_unready(message)

    def _control_tick(self) -> None:
        with self._control_operation_lock:
            now = time.monotonic()
            # Preserve the safety-critical ordering: fail closed before any
            # manager output can drain, publish, then recheck the autonomous
            # lease and validated sensor gate once more.
            navigation_failure = self._navigation_reconcile_control_locked(now)
            if navigation_failure:
                self.navigation_deactivate(navigation_failure)
            else:
                navigation_failure = self._navigation_keepalive_locked(now)
                if navigation_failure:
                    self.navigation_deactivate(navigation_failure)
            self._control_transport.update_staleness_locked(now)
            outputs = self._control_transport.manager_tick_locked()
            self._publish_control_outputs(outputs)
            navigation_failure = self._navigation_reconcile_control_locked(now)
            if navigation_failure:
                self.navigation_deactivate(navigation_failure)

    @staticmethod
    def _control_bridge_envelope(
        output: Dict[str, Any],
        *,
        source_id: str,
        sequence: int,
        bridge_epoch: str,
    ) -> Dict[str, Any]:
        return ControlTransport.bridge_envelope(
            output,
            source_id=source_id,
            sequence=sequence,
            bridge_epoch=bridge_epoch,
        )

    def _publish_control_outputs(
        self,
        outputs: List[Dict[str, Any]],
        *,
        allow_shutdown: bool = False,
    ) -> None:
        self._control_transport.publish_outputs(
            outputs,
            allow_shutdown=allow_shutdown,
        )

    def _flush_control_outputs(self) -> None:
        self._control_transport.flush_outputs()

    def _target_matches_startup(self) -> bool:
        with self._lock:
            return (
                self._robot_target_connected
                and self._robot_type == self._startup_robot_type
                and self.robot_ip == self._startup_robot_ip
            )

    def _go2_control_target(self) -> bool:
        with self._lock:
            return (
                self._startup_robot_type == "go2"
                and bool(self._startup_robot_ip)
                and self._robot_target_connected
                and self._robot_type == "go2"
                and self.robot_ip == self._startup_robot_ip
                and not self._target_restart_required
            )

    def _control_target_reason(self) -> str:
        with self._lock:
            if not self._robot_target_connected:
                return "robot_target_disconnected"
            if self._target_restart_required:
                return "runtime_target_changed_restart_required"
            if self._startup_robot_type != "go2":
                return "startup_profile_not_go2"
            if not self._startup_robot_ip:
                return "startup_go2_ip_not_configured"
            if self._robot_type != "go2":
                return "selected_type_not_go2"
            if self.robot_ip != self._startup_robot_ip:
                return "selected_ip_not_startup_control_target"
            return "startup_go2_target_match"

    def _ensure_go2_control_target(self) -> None:
        if not self._go2_control_target():
            raise ControlDisabled(
                "selected target is not bound to the startup Go2 DDS control transport; "
                "restart the dashboard with the intended Go2 profile and IP"
            )

    def control_snapshot(self) -> Dict[str, Any]:
        with self._control_operation_lock:
            snapshot = self._control_transport.raw_snapshot()
            bridge = snapshot.pop("bridge")
            transport_configured = bool(snapshot.pop("transport_configured"))
            target_supported = self._go2_control_target()
            target_matches_startup = self._target_matches_startup()
            with self._lock:
                restart_required = self._target_restart_required
            target_reason = self._control_target_reason()
        if not target_supported:
            snapshot.update(
                {
                    "enabled": False,
                    "configured": False,
                    "ready": False,
                    "actions": [],
                }
            )
            bridge.update(
                {
                    "ready": False,
                    "available": False,
                    "message": (
                        "런타임 로봇 선택은 DDS 제어 대상을 변경하지 않습니다. "
                        "선택한 Go2 프로필과 IP로 대시보드를 재시작해야 합니다."
                        if restart_required or not target_matches_startup
                        else "Go2 시작 프로필이 아니므로 Go2 제어 브리지가 차단됩니다."
                    ),
                }
            )
        snapshot["target_supported"] = target_supported
        snapshot["target_matches_startup"] = target_matches_startup
        snapshot["restart_required"] = restart_required
        snapshot["control_restart_required"] = restart_required
        snapshot["control_target_reason"] = target_reason
        snapshot["bridge"] = bridge
        snapshot["transport_configured"] = transport_configured
        snapshot["available"] = bool(snapshot.get("ready"))
        snapshot["state"] = (
            "closed"
            if snapshot.get("closed")
            else "ready"
            if snapshot.get("ready")
            else "unavailable"
        )
        snapshot["estop_latched"] = bool(snapshot.get("estop", {}).get("latched"))
        with self._navigation_lock:
            snapshot["navigation_active"] = bool(self._navigation.get("active"))
            snapshot["navigation_state"] = str(self._navigation.get("state", "inactive"))
        limits = snapshot.setdefault("limits", {})
        limits.update(
            {
                "max_linear_x": limits.get("vx_mps", 0.0),
                "max_linear_y": limits.get("vy_mps", 0.0),
                "max_angular_z": limits.get("wz_rps", 0.0),
                "default_speed_scale": self._bounded_control_timeout(
                    self.profile.get("control", {}).get("default_speed_scale")
                    if isinstance(self.profile.get("control"), dict)
                    else None,
                    default=0.35,
                    low=0.10,
                    high=1.0,
                ),
            }
        )
        return snapshot

    def control_acquire(self, input_source: str) -> Dict[str, Any]:
        with self._control_operation_lock:
            try:
                self._ensure_go2_control_target()
                with self._navigation_lock:
                    if self._navigation.get("active"):
                        raise LeaseBusy(
                            "stop autonomous navigation before arming manual control"
                        )
                return self._control_manager.acquire_lease(input_source)
            finally:
                self._flush_control_outputs()

    def control_bind(self, token: str, binding: str) -> Dict[str, Any]:
        with self._control_operation_lock:
            try:
                self._ensure_go2_control_target()
                return self._control_manager.bind_lease(token, binding)
            finally:
                self._flush_control_outputs()

    def control_heartbeat(self, token: str, binding: str, seq: int) -> Dict[str, Any]:
        with self._control_operation_lock:
            try:
                self._ensure_go2_control_target()
                return self._control_manager.heartbeat(token, binding, seq)
            finally:
                self._flush_control_outputs()

    def control_drive(
        self,
        token: str,
        binding: str,
        seq: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        with self._control_operation_lock:
            try:
                self._ensure_go2_control_target()
                return self._control_manager.submit_drive(token, binding, seq, **kwargs)
            finally:
                # Deadman/timeout paths publish StopMove before success or an
                # error returns; a live drive stays coalesced for the ROS timer.
                self._flush_control_outputs()

    def control_action(
        self,
        token: str,
        binding: str,
        seq: int,
        action: str | int,
        *,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        with self._control_operation_lock:
            try:
                self._ensure_go2_control_target()
                return self._control_manager.request_action(
                    token,
                    binding,
                    seq,
                    action,
                    confirm=confirm,
                )
            finally:
                self._flush_control_outputs()

    def control_release(
        self,
        token: str,
        binding: Optional[str] = None,
    ) -> Dict[str, Any]:
        # ``None`` intentionally asks ControlManager to authenticate only the
        # unguessable token.  This permits safe disarm if a client disconnects
        # between HTTP acquire and WebSocket binding; release never enables
        # motion and always emits a stop.
        with self._control_operation_lock:
            try:
                return self._control_manager.release_lease(token, binding)
            finally:
                self._flush_control_outputs()

    def control_estop(self, reason: str = "operator_estop") -> Dict[str, Any]:
        with self._control_operation_lock:
            try:
                return self._control_manager.emergency_stop(reason)
            finally:
                self._flush_control_outputs()

    def control_clear_estop(self, *, confirm: bool = False) -> Dict[str, Any]:
        with self._control_operation_lock:
            try:
                self._ensure_go2_control_target()
                return self._control_manager.clear_emergency_stop(confirm=confirm)
            finally:
                self._flush_control_outputs()

    def shutdown_control(self) -> None:
        self._control_transport.shutdown()

    def _refresh_graph(self) -> None:
        node = self._node
        if not node:
            return
        try:
            discovered = self._graph_monitor.discover(node)
            with self._lock:
                self._graph = discovered
                self._pick_default_sources_locked()
            self._sync_special_subscriptions()
            self._sync_joint_subscription()
            self._sync_observable_subscriptions()
        except Exception as exc:
            with self._lock:
                self._last_error = f"graph refresh: {exc}"

    def _pick_default_sources_locked(self) -> None:
        preferences = self.profile.get("preferred_topics", {}) if self.profile else {}
        disabled = set(self.profile.get("disabled_sources", [])) if self.profile else set()
        for category in self._sources:
            requested = self._requested_sources.get(category, "")
            previous = self._sources.get(category, "")
            # A fail-closed pin describes operator intent, not current graph
            # availability.  Keep the exact topic selected while its driver or
            # mapping pipeline restarts so another physical LiDAR cannot become
            # active silently.
            if category in self._source_pins and requested:
                chosen = requested
            elif category in disabled and not requested:
                chosen = ""
            else:
                candidates = [
                    name
                    for name, item in self._graph.items()
                    if item.get("category") == category and item.get("publishers", 0) > 0
                ]
                ordered = list(preferences.get(category, []))
                # Categories without a fail-closed profile retain their legacy
                # temporary-failover behavior.  Automatic choices are never
                # copied into the manual request.
                chosen = requested if requested in candidates else ""
                if not chosen:
                    chosen = next((name for name in ordered if name in candidates), "")
                if not chosen and previous in candidates:
                    chosen = previous
                if not chosen and candidates:
                    chosen = sorted(candidates)[0]
            self._sources[category] = chosen
            if chosen != previous:
                if category == "odometry":
                    self._reset_pose_locked(chosen)
                elif category == "pointcloud":
                    self._reset_cloud_locked(chosen)

    def _reset_pose_locked(self, topic: str) -> None:
        self._telemetry_hub.reset_pose(
            topic,
            str(self._graph.get(topic, {}).get("type", "")),
        )

    def _reset_cloud_locked(self, topic: str) -> None:
        self._pointcloud_hub.reset(topic)

    def _sync_special_subscriptions(self) -> None:
        for category in ("camera", "pointcloud", "occupancy_grid"):
            with self._lock:
                wanted = self._sources.get(category, "")
                current = self._special_subscription_topics.get(category, "")
            if wanted == current:
                continue
            if current:
                self._destroy_subscription(f"special:{category}")
                with self._lock:
                    self._special_subscription_topics[category] = ""
            if wanted:
                callback = {
                    "camera": self._camera_callback,
                    "pointcloud": self._pointcloud_callback,
                    "occupancy_grid": self._map_callback,
                }[category]
                if self._create_subscription(f"special:{category}", wanted, callback):
                    with self._lock:
                        self._special_subscription_topics[category] = wanted

    def _preferred_joint_source_locked(self) -> str:
        """Select one real joint source, preferring named JointState data."""

        now = time.monotonic()

        def has_recent_samples(topic: str) -> bool:
            meter = self._metrics.get(topic)
            return bool(
                meter
                and meter.last is not None
                and 0.0 <= now - meter.last <= 3.0
            )

        candidates = [
            (topic, descriptor.get("type", ""))
            for topic, descriptor in self._graph.items()
            if (
                (
                    descriptor.get("type") == "sensor_msgs/msg/JointState"
                    and descriptor.get("publishers", 0) > 0
                )
                or (
                    str(descriptor.get("type", "")).casefold().endswith("/lowstate")
                    and (
                        descriptor.get("publishers", 0) > 0
                        or has_recent_samples(topic)
                    )
                )
            )
        ]
        if not candidates:
            return ""

        def priority(item: Tuple[str, str]) -> Tuple[int, int, str]:
            topic, type_name = item
            is_joint_state = type_name == "sensor_msgs/msg/JointState"
            exact_name = topic in {"/joint_states", "/lowstate"}
            return (0 if is_joint_state else 1, 0 if exact_name else 1, topic)

        return min(candidates, key=priority)[0]

    def _sync_joint_subscription(self) -> None:
        """Maintain one lightweight subscription for Go2 model articulation."""

        with self._lock:
            wanted = self._preferred_joint_source_locked()
            current = self._special_subscription_topics.get("joints", "")
        if wanted == current:
            return
        if current:
            self._destroy_subscription("special:joints")
            with self._lock:
                self._special_subscription_topics["joints"] = ""
        with self._lock:
            self._joints = {
                "seq": self._joints["seq"],
                "topic": wanted,
                "type": self._graph.get(wanted, {}).get("type", ""),
                "position_rad": None,
                "imu_rpy_rad": None,
                "source_order": "",
                "stamp_ns": 0,
                "updated": 0.0,
            }
        if not wanted:
            return
        # Avoid deserializing a high-rate LowState twice if it was also allowed
        # by the generic observed-topic policy.  The dedicated callback stores
        # the same compact summary at 5 Hz in addition to joint positions.
        self._destroy_subscription(f"observe:{wanted}")
        if self._create_subscription("special:joints", wanted, self._joint_callback):
            with self._lock:
                self._special_subscription_topics["joints"] = wanted

    def _sync_observable_subscriptions(self) -> None:
        with self._lock:
            items = list(self._graph.items())
            selected_odometry = self._sources.get("odometry", "")
            selected_joints = self._special_subscription_topics.get("joints", "")
        configured = self.profile.get("observed_topics") if self.profile else None
        observed_topics = set(configured) if isinstance(configured, list) else None
        for topic, descriptor in items:
            type_name = descriptor.get("type", "")
            category = descriptor.get("category", "")
            if not is_observable_type(type_name):
                continue
            if category in {"camera", "pointcloud", "occupancy_grid"}:
                continue
            if topic == selected_joints:
                continue
            # High-rate robot graphs often expose duplicated aliases (for
            # example /lowstate and /lf/lowstate).  A profile allowlist avoids
            # blindly deserializing every compatible topic while the selected
            # odometry source always remains observable for map pose display.
            if observed_topics is not None and topic not in observed_topics and topic != selected_odometry:
                continue
            key = f"observe:{topic}"
            if key not in self._subscriptions:
                self._create_subscription(key, topic, self._summary_callback)

    def _qos_for(self, topic: str, type_name: str) -> QoSProfile:
        durability = DurabilityPolicy.VOLATILE
        reliability = ReliabilityPolicy.BEST_EFFORT
        node = self._node
        if node:
            try:
                offers = node.get_publishers_info_by_topic(topic)
                if offers and all(info.qos_profile.durability == DurabilityPolicy.TRANSIENT_LOCAL for info in offers):
                    durability = DurabilityPolicy.TRANSIENT_LOCAL
                if offers and all(info.qos_profile.reliability == ReliabilityPolicy.RELIABLE for info in offers):
                    reliability = ReliabilityPolicy.RELIABLE
            except Exception:
                pass
        # Keep point clouds publisher-compatible.  FAST-LIO's large /Laser_map
        # is RELIABLE, while many raw LiDAR drivers offer BEST_EFFORT; the
        # publisher inspection above selects the matching policy for either.
        if type_name in CAMERA_TYPES or classify_type(type_name) in {"imu", "robot_state", "lidar"}:
            durability = DurabilityPolicy.VOLATILE
            reliability = ReliabilityPolicy.BEST_EFFORT
        return QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=reliability,
            durability=durability,
        )

    def _create_subscription(self, key: str, topic: str, callback: Any) -> bool:
        node = self._node
        with self._lock:
            descriptor = self._graph.get(topic, {})
            type_name = descriptor.get("type", "")
        if not node or not type_name:
            return False
        try:
            message_type = get_message(type_name)

            def wrapped(message: Any, topic_name: str = topic, ros_type: str = type_name) -> None:
                callback(topic_name, ros_type, message)

            subscription = node.create_subscription(
                message_type,
                topic,
                wrapped,
                self._qos_for(topic, type_name),
            )
            with self._lock:
                self._subscriptions[key] = subscription
                self._metrics.setdefault(topic, RateMeter())
            return True
        except Exception as exc:
            with self._lock:
                self._last_error = f"subscribe {topic}: {exc}"
            return False

    def _destroy_subscription(self, key: str) -> None:
        node = self._node
        with self._lock:
            subscription = self._subscriptions.pop(key, None)
        if node and subscription:
            try:
                node.destroy_subscription(subscription)
            except Exception:
                pass

    def _tick(self, topic: str, now: float) -> None:
        self._graph_monitor.tick(topic, now)

    def _summary_callback(self, topic: str, type_name: str, message: Any) -> None:
        now = time.monotonic()
        self._tick(topic, now)
        if type_name == "nav_msgs/msg/Odometry":
            self._update_pose(topic, type_name, message, now)
        self._store_summary(topic, type_name, message, now)

    def _update_pose(self, topic: str, type_name: str, message: Any, now: float) -> None:
        self._telemetry_hub.update_pose(
            topic,
            type_name,
            message,
            now,
            selected_topic=lambda: self._sources.get("odometry", ""),
            stamp_ns=self._stamp_ns,
        )

    def _store_summary(self, topic: str, type_name: str, message: Any, now: float) -> None:
        try:
            self._telemetry_hub.store_summary(topic, type_name, message, now)
        except Exception as exc:
            with self._lock:
                self._last_error = f"summarize {topic}: {exc}"

    def _joint_callback(self, topic: str, type_name: str, message: Any) -> None:
        """Extract only the twelve Go2 positions needed by the web model."""

        now = time.monotonic()
        with self._lock:
            if topic != self._special_subscription_topics.get("joints", ""):
                return
        self._tick(topic, now)
        self._store_summary(topic, type_name, message, now)
        self._telemetry_hub.update_joints(
            topic,
            type_name,
            message,
            now,
            selected_topic=lambda: self._special_subscription_topics.get("joints", ""),
            stamp_ns=self._stamp_ns,
        )

    def _camera_callback(self, topic: str, type_name: str, message: Any) -> None:
        self._camera_hub.ros_callback(topic, type_name, message)

    def _decoded_camera_callback(self, jpeg: bytes) -> None:
        self._camera_hub.decoded_callback(jpeg)

    def _direct_camera_callback(self, jpeg: bytes) -> None:
        """Store one JPEG decoded from the Go2's non-ROS RTP multicast."""
        self._camera_hub.direct_callback(jpeg)

    def _remote_camera_callback(self, jpeg: bytes) -> None:
        """Store a RealSense JPEG independently from the Go2 front stream."""
        self._camera_hub.remote_callback(jpeg)

    @staticmethod
    def _first_start_code(payload: bytes) -> int:
        return CameraHub.first_start_code(payload)

    @staticmethod
    def _nal_units(payload: bytes) -> List[Tuple[int, int, int]]:
        return CameraHub.nal_units(payload)

    def _prepare_h264(self, payload: bytes) -> Tuple[bytes, bool]:
        return self._camera_hub.prepare_h264(payload)

    def _pointcloud_callback(self, topic: str, type_name: str, message: Any) -> None:
        now = time.monotonic()
        with self._lock:
            if topic != self._sources.get("pointcloud", ""):
                return
        self._tick(topic, now)
        try:
            self._pointcloud_hub.process(
                topic,
                message,
                now,
                selected_topic=lambda: self._sources.get("pointcloud", ""),
                stamp_ns=self._stamp_ns,
                robot_pose_in_frame=self._robot_pose_in_cloud_frame,
            )
        except Exception as exc:
            with self._lock:
                self._last_error = f"pointcloud {topic}: {exc}"

    def _map_callback(self, topic: str, type_name: str, message: Any) -> None:
        now = time.monotonic()
        self._tick(topic, now)
        try:
            self._telemetry_hub.update_map(
                topic,
                message,
                now,
                stamp_ns=self._stamp_ns,
            )
        except Exception as exc:
            with self._lock:
                self._last_error = f"map {topic}: {exc}"

    def set_sources(self, values: Dict[str, str]) -> Dict[str, Any]:
        with self._lock:
            self._source_registry.apply_selection(
                values,
                self._graph,
                direct_camera_configured=self._direct_camera.configured,
                direct_camera_uri=self._direct_camera.source_uri,
            )
            self._pick_default_sources_locked()
        return self.sources_snapshot()

    def _robot_pose_in_cloud_frame(self, frame_id: str) -> Optional[Dict[str, Any]]:
        configured = self.profile.get("robot_pose_in_cloud_frames", {}) if self.profile else {}
        value = configured.get(frame_id) if isinstance(configured, dict) else None
        if not isinstance(value, dict):
            return None
        try:
            position = [float(item) for item in value.get("position", [])]
            rpy = [float(item) for item in value.get("rpy", [])]
        except (TypeError, ValueError):
            return None
        if len(position) != 3 or len(rpy) != 3 or not all(
            math.isfinite(item) for item in position + rpy
        ):
            return None
        return {
            "x": position[0],
            "y": position[1],
            "z": position[2],
            "roll": rpy[0],
            "pitch": rpy[1],
            "yaw": rpy[2],
            "frame_id": frame_id,
            "source": "configured_sensor_extrinsic",
        }

    @staticmethod
    def _stamp_ns(message: Any) -> int:
        stamp = getattr(getattr(message, "header", None), "stamp", None)
        return int(getattr(stamp, "sec", 0)) * 1_000_000_000 + int(getattr(stamp, "nanosec", 0))

    def _stop_for_target_change_locked(self) -> None:
        """Revoke any Go2 lease before an IP or robot type can change."""
        self._control_transport.stop_for_target_change()

    def robot_target_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            selected_capabilities = capabilities_for_robot_type(self._robot_type)
            runtime_capabilities = capabilities_for_robot_type(self._startup_robot_type)
            target_matches_startup = (
                self._robot_target_connected
                and self._robot_type == self._startup_robot_type
                and self.robot_ip == self._startup_robot_ip
            )
            return {
                "connected": self._robot_target_connected,
                "ip": self.robot_ip,
                "hostname": self._robot_hostname,
                "robot_type": self._robot_type,
                "profile": {
                    "id": self._robot_type,
                    "label": (
                        robot_type_definition(self._robot_type)["label"]
                        if self._robot_type
                        else self._startup_profile_name
                    ),
                    "startup_label": self._startup_profile_name,
                    "capabilities": selected_capabilities,
                },
                "runtime_capabilities": runtime_capabilities,
                "model": copy.deepcopy(self._robot_model),
                "target_matches_startup": target_matches_startup,
                "restart_required": self._target_restart_required,
                "control_restart_required": self._target_restart_required,
                "control_target_reason": self._control_target_reason(),
                "control_target_supported": (
                    self._startup_robot_type == "go2"
                    and bool(self._startup_robot_ip)
                    and self._robot_target_connected
                    and target_matches_startup
                    and not self._target_restart_required
                ),
            }

    def set_robot_target(
        self,
        value: str,
        robot_type: str,
        hostname: str | None = None,
    ) -> Dict[str, Any]:
        """Select a discovered local robot/controller and its display model.

        A runtime type switch deliberately does not hot-swap the startup ROS
        profile or control implementation.  Observation can keep running, while
        Go2 control is gated independently below and is always revoked before a
        target/type change becomes visible.
        """

        valid = self._valid_ip(value)
        if not valid or not is_local_robot_ipv4(valid):
            raise ValueError("로봇 대상은 로컬 RFC1918 또는 link-local IPv4 주소여야 합니다.")
        definition = robot_type_definition(robot_type)
        normalized_hostname = normalize_hostname(hostname)
        with self._control_operation_lock:
            with self._lock:
                changed = (
                    not self._robot_target_connected
                    or valid != self.robot_ip
                    or definition["id"] != self._robot_type
                )
                # Generic/TurtleBot profiles have no Go2 motion
                # transport. Their target selection is observation/display
                # metadata and can change live. Any transition touching Go2,
                # or any change from a Go2 startup, remains fail-closed.
                go2_involved = (
                    self._startup_robot_type == "go2"
                    or self._robot_type == "go2"
                    or definition["id"] == "go2"
                )
            if changed and go2_involved:
                self._stop_for_target_change_locked()
            with self._lock:
                if changed:
                    self._target_restart_required = (
                        True
                        if self._startup_robot_type == "go2"
                        else definition["id"] == "go2"
                    )
                self.robot_ip = valid
                self._robot_target_connected = True
                self._robot_type = definition["id"]
                self._robot_hostname = normalized_hostname
                self._robot_model = copy.deepcopy(definition["model"])
                self._network_cache = (0.0, False, None)
            # Snapshot while the operation lock still owns this mutation, so
            # concurrent direct API clients cannot make this request report a
            # later request's target.
            snapshot = self.robot_target_snapshot()
            snapshot["changed"] = changed
        return snapshot

    def disconnect_robot_target(self) -> Dict[str, Any]:
        """Clear the selected display/control target without touching the NIC.

        The ROS/DDS participant is fixed at process startup, so this operation
        revokes Go2 motion and marks all target-specific UI data disconnected;
        it does not reconfigure interfaces, stop system services or power off a
        device. Reconnecting a Go2 target remains fail-closed until restart.
        """

        with self._control_operation_lock:
            with self._lock:
                changed = self._robot_target_connected or bool(self.robot_ip)
                go2_involved = (
                    self._startup_robot_type == "go2" or self._robot_type == "go2"
                )
            if changed and go2_involved:
                self._stop_for_target_change_locked()
            with self._lock:
                self.robot_ip = ""
                self._robot_hostname = ""
                self._robot_target_connected = False
                if changed and go2_involved:
                    self._target_restart_required = True
                self._network_cache = (0.0, False, None)
            snapshot = self.robot_target_snapshot()
            snapshot["changed"] = changed
        return snapshot

    def set_robot_ip(self, value: str) -> str:
        """Legacy IP-only setter; still revokes motion when the target changes."""

        valid = self._valid_ip(value)
        if not valid:
            raise ValueError("유효한 IPv4 또는 IPv6 주소가 아닙니다.")
        with self._control_operation_lock:
            with self._lock:
                changed = valid != self.robot_ip
                go2_involved = (
                    self._startup_robot_type == "go2" or self._robot_type == "go2"
                )
            if changed and go2_involved:
                self._stop_for_target_change_locked()
            with self._lock:
                if changed:
                    self._target_restart_required = go2_involved
                self.robot_ip = valid
                self._robot_target_connected = True
                self._network_cache = (0.0, False, None)
        return valid

    def _network_status(self) -> Tuple[bool, Optional[float]]:
        now = time.monotonic()
        with self._lock:
            cached_at, online, latency = self._network_cache
            target_ip = self.robot_ip
            target_connected = self._robot_target_connected
        if now - cached_at < 3.0:
            return online, latency
        if not target_connected or not target_ip:
            return False, None
        started = time.monotonic()
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "1", target_ip],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
            )
            online = result.returncode == 0
            latency = round((time.monotonic() - started) * 1000.0, 1) if online else None
        except (OSError, subprocess.TimeoutExpired):
            online, latency = False, None
        with self._lock:
            # A concurrent target selection must not let an old ping poison the
            # new target's three-second health cache.
            if self.robot_ip != target_ip:
                return False, None
            self._network_cache = (now, online, latency)
        return online, latency

    def health_snapshot(self) -> Dict[str, Any]:
        online, latency = self._network_status()
        ros_transport = ros_transport_status(
            require_go2_interface=self._startup_robot_type == "go2"
        )
        direct_camera = public_camera_status(self._direct_camera.status())
        with self._lock:
            selected_capabilities = capabilities_for_robot_type(self._robot_type)
            runtime_capabilities = capabilities_for_robot_type(self._startup_robot_type)
            runtime_profile = (
                robot_type_definition(self._robot_type) if self._robot_type else None
            )
            target_matches_startup = (
                self._robot_target_connected
                and self._robot_type == self._startup_robot_type
                and self.robot_ip == self._startup_robot_ip
            )
            return {
                "agent_ready": self._ready,
                "agent_version": "0.1.0",
                "hostname": socket.gethostname(),
                "platform": platform.machine(),
                "ros_distro": os.environ.get("ROS_DISTRO", "unknown"),
                "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", "0"),
                "rmw": os.environ.get("RMW_IMPLEMENTATION", "default"),
                "ros_transport": ros_transport,
                "ros_interface_ready": ros_transport["interface_ready"],
                "ros_offline_viewer": ros_transport["offline_viewer"],
                "robot_ip": self.robot_ip,
                "robot_target_connected": self._robot_target_connected,
                "robot_hostname": self._robot_hostname,
                "robot_type": self._robot_type,
                "robot_model": copy.deepcopy(self._robot_model),
                "target_matches_startup": target_matches_startup,
                "restart_required": self._target_restart_required,
                "control_restart_required": self._target_restart_required,
                "control_target_reason": self._control_target_reason(),
                "control_target_supported": (
                    self._startup_robot_type == "go2"
                    and bool(self._startup_robot_ip)
                    and self._robot_target_connected
                    and target_matches_startup
                    and not self._target_restart_required
                ),
                "robot_online": online,
                "robot_latency_ms": latency,
                "uptime_s": round(time.monotonic() - self._started_at, 1),
                "topic_count": len(self._graph),
                "last_error": public_diagnostic(self._last_error),
                "direct_camera": direct_camera,
                # `profile` always names the actually running ROS profile.
                # Runtime selection is display/observation metadata only.
                "profile": self._startup_profile_name,
                "runtime_profile": {
                    "id": self._startup_robot_type,
                    "label": self._startup_profile_name,
                    "capabilities": runtime_capabilities,
                },
                "selected_profile": {
                    "id": self._robot_type,
                    "label": runtime_profile["label"] if runtime_profile else "Unselected",
                    "capabilities": selected_capabilities,
                },
            }

    def _pointcloud_source_descriptor_locked(
        self,
        topic: str,
        item: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Describe one PointCloud source without trusting its ROS topic name."""

        identity = pointcloud_source_metadata(topic)
        publishers = max(0, int(item.get("publishers", 0) or 0))
        metric = self._metric_snapshot(topic, "pointcloud")
        sample_state = str(metric.get("state", "waiting"))
        samples = max(0, int(metric.get("samples", 0) or 0))
        available = publishers > 0
        if not available:
            # Retained metrics may be stale after a publisher disappears.  The
            # selected source is intentionally waiting for that exact publisher,
            # rather than reporting a stale frame as an alternate live source.
            sample_state = "waiting"
        live = available and samples > 0 and sample_state == "ok"
        policy = self._source_selection_policies.get("pointcloud", {})
        pinned = bool(
            "pointcloud" in self._source_pins
            and self._requested_sources.get("pointcloud") == topic
            and self._sources.get("pointcloud") == topic
        )
        return {
            # Keep the original option contract for older dashboard clients.
            "topic": topic,
            "type": str(item.get("type", "")),
            **identity,
            "publishers": publishers,
            "samples": samples,
            "hz": metric.get("hz"),
            "jitter_ms": metric.get("jitter_ms"),
            "age_s": metric.get("age_s"),
            "available": available,
            "live": live,
            "state": sample_state,
            "sample_state": sample_state,
            "pinned": pinned,
            "selection_origin": (
                self._source_selection_origins.get("pointcloud", "auto")
                if pinned
                else ""
            ),
            "configured": topic in policy.get("allowed_offline", ()),
        }

    def sources_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            options: Dict[str, List[Dict[str, Any]]] = {key: [] for key in self._sources}
            for name, item in self._graph.items():
                category = item.get("category")
                if category in options and item.get("publishers", 0) > 0:
                    if category == "pointcloud":
                        option = self._pointcloud_source_descriptor_locked(name, item)
                    else:
                        option = {"topic": name, "type": item.get("type", "")}
                    options[category].append(option)
            pinned_pointcloud = self._requested_sources.get("pointcloud", "")
            if (
                "pointcloud" in self._source_pins
                and pinned_pointcloud
                and self._sources.get("pointcloud") == pinned_pointcloud
                and not any(
                    item["topic"] == pinned_pointcloud
                    for item in options["pointcloud"]
                )
            ):
                pinned_item = self._graph.get(
                    pinned_pointcloud,
                    {
                        "type": "sensor_msgs/msg/PointCloud2",
                        "category": "pointcloud",
                        "publishers": 0,
                    },
                )
                options["pointcloud"].append(
                    self._pointcloud_source_descriptor_locked(
                        pinned_pointcloud,
                        pinned_item,
                    )
                )
            for values in options.values():
                values.sort(key=lambda item: item["topic"])
            selected = dict(self._sources)
            selected_pointcloud = selected.get("pointcloud", "")
            selected_pointcloud_item = self._graph.get(selected_pointcloud, {})
            if (
                selected_pointcloud
                and not selected_pointcloud_item
                and "pointcloud" in self._source_pins
            ):
                selected_pointcloud_item = {
                    "type": "sensor_msgs/msg/PointCloud2",
                    "category": "pointcloud",
                    "publishers": 0,
                }
            selected_pointcloud_descriptor = (
                self._pointcloud_source_descriptor_locked(
                    selected_pointcloud,
                    selected_pointcloud_item,
                )
                if selected_pointcloud
                else None
            )
            locked: Dict[str, bool] = {}
            direct_camera = self._direct_camera.status()
            if direct_camera.get("enabled") and direct_camera.get("configured"):
                uri = str(direct_camera.get("uri", self._direct_camera.source_uri))
                options["camera"] = [
                    {
                        "topic": uri,
                        "type": "video/H264 (direct RTP multicast)",
                    }
                ]
                selected["camera"] = uri
                locked["camera"] = True
            selection: Dict[str, Dict[str, Any]] = {}
            for category in SOURCE_CATEGORIES:
                policy = self._source_selection_policies.get(category, {})
                pinned = bool(
                    category in self._source_pins
                    and self._requested_sources.get(category)
                    and self._sources.get(category)
                    == self._requested_sources.get(category)
                )
                selection[category] = {
                    "mode": "pinned" if pinned else "auto",
                    "requested": self._requested_sources.get(category, ""),
                    "origin": self._source_selection_origins.get(category, "auto"),
                    "persistent": bool(policy.get("persistent", False)),
                    "fail_closed": bool(policy.get("fail_closed", False)),
                }
            return {
                "selected": selected,
                "selected_descriptors": {
                    "pointcloud": selected_pointcloud_descriptor,
                },
                "options": options,
                "locked": locked,
                "selection": selection,
            }

    def _metric_snapshot(self, topic: str, category: str) -> Dict[str, Any]:
        return self._graph_monitor.metric_snapshot(topic, category)

    def topics_snapshot(self) -> List[Dict[str, Any]]:
        topics = self._graph_monitor.topics_snapshot(set(self._sources.values()))
        for item in topics:
            if item.get("category") == "pointcloud":
                item.update(pointcloud_source_metadata(str(item.get("name", ""))))
        return topics

    def _joint_snapshot_locked(self, now: float) -> Dict[str, Any]:
        return self._telemetry_hub.joint_snapshot_locked(now)

    def joint_snapshot(self) -> Dict[str, Any]:
        """Return the small joint-only snapshot for a high-rate API/WS route."""

        with self._lock:
            return self._joint_snapshot_locked(time.monotonic())

    def _pose_snapshot_locked(self, now: float) -> Dict[str, Any]:
        return self._telemetry_hub.pose_snapshot_locked(now)

    def pose_snapshot(self) -> Dict[str, Any]:
        """Return the selected world pose without the large state payload."""

        with self._lock:
            return self._pose_snapshot_locked(time.monotonic())

    def _camera_snapshot_locked(self) -> Dict[str, Any]:
        return self._camera_hub.camera_snapshot_locked()

    def _remote_camera_snapshot_locked(self) -> Dict[str, Any]:
        return self._camera_hub.remote_snapshot_locked()

    def cameras_snapshot(self) -> Dict[str, Any]:
        """Return the fixed camera catalog without exposing demand tokens."""
        return self._camera_hub.catalog_snapshot()

    def state_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            sensors = []
            for topic, summary in self._summaries.items():
                item = dict(summary)
                item.update(self._metric_snapshot(topic, summary.get("category", "")))
                sensors.append(item)
            sources = dict(self._sources)
            camera_meta = {
                key: value for key, value in self._camera_snapshot_locked().items() if key != "data"
            }
            if camera_meta.get("source") == "go2_multicast":
                # State consumers can treat the direct feed like a selected
                # source without adding a non-ROS URI to /api/v1/sources, whose
                # POST validation remains strictly tied to the ROS graph.
                sources["camera"] = str(camera_meta.get("topic", ""))
            cloud_meta = {
                key: value
                for key, value in self._cloud.items()
                if key not in {"points", "points_bytes"}
            }
            cloud_topic = str(cloud_meta.get("topic") or sources.get("pointcloud", ""))
            if cloud_topic:
                cloud_meta.update(pointcloud_source_metadata(cloud_topic))
            map_meta = {key: value for key, value in self._map.items() if key != "data_b64"}
            robot_joints = self._joint_snapshot_locked(time.monotonic())
            robot_pose = self._pose_snapshot_locked(time.monotonic())

            mapping_topic = sources.get("pointcloud", "")
            mapping_metric = self._metric_snapshot(mapping_topic, "pointcloud") if mapping_topic else {"state": "waiting"}
            odom_topic = sources.get("odometry", "")
            odom_metric = self._metric_snapshot(odom_topic, "odometry") if odom_topic else {"state": "waiting"}
            if mapping_metric.get("state") == "ok" and odom_metric.get("state") == "ok":
                mapping_state = "mapping"
            elif mapping_metric.get("state") == "ok":
                mapping_state = "cloud_only"
            elif mapping_metric.get("state") == "stale":
                mapping_state = "stale"
            else:
                mapping_state = "waiting"

            return {
                "health": self.health_snapshot(),
                "sources": sources,
                "sensors": sorted(sensors, key=lambda item: item["topic"]),
                "camera": camera_meta,
                "cloud": cloud_meta,
                "map": map_meta,
                "robot_joints": robot_joints,
                "robot_pose": robot_pose,
                "mapping": {
                    "state": mapping_state,
                    "cloud": mapping_metric,
                    "odometry": odom_metric,
                },
            }

    def camera_snapshot(self, source_id: str = "go2_front") -> Dict[str, Any]:
        with self._lock:
            if source_id == "go2_front":
                return self._camera_snapshot_locked()
            if source_id == "realsense_color":
                return self._remote_camera_snapshot_locked()
            raise ValueError("camera source is not allowlisted")

    def camera_snapshots(self, source_ids: Tuple[str, ...]) -> Dict[str, Dict[str, Any]]:
        """Snapshot one or both fixed cameras under the same frame lock.

        Dataset capture uses this method so a two-camera sample observes one
        coherent point in the dashboard process.  The camera hardware is not
        trigger-synchronised; callers must still enforce an explicit timestamp
        skew bound before committing a pair.
        """

        return self._camera_hub.snapshots(source_ids)

    def pointcloud_snapshot(self) -> Dict[str, Any]:
        snapshot = self._pointcloud_hub.json_snapshot()
        topic = str(snapshot.get("topic", ""))
        if topic:
            snapshot.update(pointcloud_source_metadata(topic))
        return snapshot

    def pointcloud_binary_snapshot(self) -> Dict[str, Any]:
        """Return immutable packed points plus small JSON-safe metadata."""
        snapshot = self._pointcloud_hub.binary_snapshot()
        topic = str(snapshot.get("topic", ""))
        if topic:
            snapshot.update(pointcloud_source_metadata(topic))
        return snapshot

    def map_snapshot(self) -> Dict[str, Any]:
        return self._telemetry_hub.map_snapshot()
