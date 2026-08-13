"""ROS 2 runtime used by the Robot Scope web agent."""

from __future__ import annotations

import base64
import copy
import ipaddress
import json
import math
import os
import platform
import re
import secrets
import socket
import stat
import subprocess
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rosidl_runtime_py.utilities import get_message
from std_msgs.msg import String

from .camera_decoder import H264JpegDecoder
from .control import (
    CommandValidationError,
    ControlClosed,
    ControlDisabled,
    ControlError,
    ControlManager,
    ControlNotReady,
    EmergencyStopLatched,
    LeaseBusy,
    LeaseInvalid,
)
from .control_protocol import (
    ControlProtocolError,
    decode_signed,
    encode_signed,
    shared_key,
)
from .discovery import (
    infer_robot_type,
    is_local_robot_ipv4,
    normalize_hostname,
    robot_type_definition,
)
from .go2_multicast_camera import Go2MulticastCamera
from .pointcloud import extract_xyz, reject_spatial_outliers
from .remote_mjpeg_camera import RemoteMjpegCamera
from .runtime_status import ros_transport_status
from .serializers import (
    classify_type,
    extract_odometry_pose,
    extract_go2_imu_rpy,
    extract_go2_joint_positions,
    go2_joint_state_payload,
    is_observable_type,
    odometry_pose_payload,
    summarize_message,
)


CAMERA_TYPES = {
    "sensor_msgs/msg/Image",
    "sensor_msgs/msg/CompressedImage",
    "unitree_go/msg/Go2FrontVideoData",
}

# Source identity is deliberately derived from a small, fixed topic allowlist.
# ROS graph names are untrusted display metadata; a similar-looking vendor or
# user topic must never be presented as a known physical LiDAR.
HESAI_XT16_POINTCLOUD_STAGES = {
    "/lidar_points": "raw",
    "/velodyne_points": "converted",
    "/cloud_registered": "registered",
    "/Laser_map": "map",
}
GO2_UTLIDAR_POINTCLOUD_STAGES = {
    "/utlidar/cloud": "raw",
    "/utlidar/cloud_deskewed": "deskewed",
    "/utlidar/cloud_base": "base_frame",
    "/utlidar/grid_map": "local_map",
    "/utlidar/height_map": "height_map",
    "/utlidar/range_map": "range_map",
    "/utlidar/voxel_map": "voxel_map",
}
GO2_USLAM_POINTCLOUD_STAGES = {
    "/uslam/cloud_map": "map",
}
POINTCLOUD_STAGE_LABELS = {
    "raw": "Raw points",
    "converted": "Converted points",
    "deskewed": "Deskewed points",
    "base_frame": "Base-frame points",
    "registered": "Registered cloud",
    "local_map": "Local map",
    "height_map": "Height map",
    "range_map": "Range map",
    "voxel_map": "Voxel map",
    "map": "SLAM map",
    "unknown": "PointCloud",
}

SOURCE_CATEGORIES = ("camera", "pointcloud", "odometry", "occupancy_grid")
SOURCE_SELECTION_STATE_VERSION = 1
SOURCE_SELECTION_STATE_MAX_BYTES = 16 * 1024
CAMERA_SOURCE_IDS = ("go2_front", "realsense_color")
MAX_ACTIVE_CAMERA_SOURCES = 2
MAX_CAMERA_VIEWERS = 8
MAX_CAMERA_VIEWERS_PER_SOURCE = 4


def pointcloud_source_metadata(topic: str) -> Dict[str, str]:
    """Return allowlisted LiDAR identity and processing-stage metadata."""

    normalized = str(topic or "")
    if normalized in HESAI_XT16_POINTCLOUD_STAGES:
        sensor_id = "hesai_xt16"
        sensor_label = "Hesai XT16"
        stage = HESAI_XT16_POINTCLOUD_STAGES[normalized]
    elif normalized in GO2_UTLIDAR_POINTCLOUD_STAGES:
        sensor_id = "go2_builtin_lidar"
        sensor_label = "Go2 Built-in LiDAR"
        stage = GO2_UTLIDAR_POINTCLOUD_STAGES[normalized]
    elif normalized in GO2_USLAM_POINTCLOUD_STAGES:
        sensor_id = "go2_builtin_lidar"
        sensor_label = "Go2 Built-in LiDAR"
        stage = GO2_USLAM_POINTCLOUD_STAGES[normalized]
    else:
        sensor_id = "generic_pointcloud"
        sensor_label = "Generic PointCloud"
        stage = "unknown"
    stage_label = POINTCLOUD_STAGE_LABELS[stage]
    return {
        "sensor_id": sensor_id,
        "sensor_label": sensor_label,
        "pipeline_stage": stage,
        "pipeline_stage_label": stage_label,
        "display_label": f"{sensor_label} · {stage_label} · {normalized}",
    }

CONTROL_COMMAND_TOPIC = "/robot_scope/control/command"
CONTROL_STATUS_TOPIC = "/robot_scope/control/status"
# Nav2 is remapped to this private ingress.  A random/global /cmd_vel publisher
# can therefore never acquire the autonomous gate accidentally.
NAVIGATION_CMD_VEL_TOPIC = "/robot_scope/nav/cmd_vel_raw"
NAVIGATION_INITIAL_POSE_TOPIC = "/initialpose"
NAVIGATION_LOCALIZATION_POSE_TOPIC = "/amcl_pose"
NAVIGATION_RUNTIME_HEALTH_TOPIC = "/robot_scope/nav/runtime_health"
NAVIGATION_FAST_LIO_ODOM_TOPIC = "/Odometry"
# PDF 11 deliberately uses the Go2's continuously available onboard odometry
# for controller velocity feedback.  FAST-LIO odometry remains a separate,
# fixed localization input to the trusted runtime sidecar.
NAVIGATION_CONTROLLER_ODOM_TOPIC = "/utlidar/robot_odom"
NAVIGATION_ACTION = "/navigate_to_pose"
# Controller feedback and FAST-LIO run on the same real-time ROS clock as the
# dashboard (use_sim_time is fixed false).  Permit moderate network/clock jitter
# without accepting zero, replayed or substantially future-dated odometry.
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


def _public_navigation_reason(reason: object) -> str:
    """Return one bounded internal reason without credentials/control bytes."""

    value = _NAVIGATION_REASON_CONTROL_RE.sub(" ", str(reason or ""))
    value = _NAVIGATION_REASON_WHITESPACE_RE.sub(" ", value).strip()
    value = _NAVIGATION_REASON_SECRET_RE.sub(
        lambda match: f"{match.group(1)}=[redacted]",
        value,
    )
    return (value or "navigation stopped")[:160]


class RateMeter:
    def __init__(self, maxlen: int = 180) -> None:
        self.times: deque[float] = deque(maxlen=maxlen)
        self.samples = 0

    def tick(self, now: float) -> None:
        self.times.append(now)
        self.samples += 1

    def hz(self) -> Optional[float]:
        if len(self.times) < 2:
            return None
        elapsed = self.times[-1] - self.times[0]
        if elapsed <= 0:
            return None
        return round((len(self.times) - 1) / elapsed, 2)

    def jitter_ms(self) -> Optional[float]:
        if len(self.times) < 4:
            return None
        intervals = np.diff(np.asarray(self.times, dtype=np.float64))
        return round(float(np.std(intervals) * 1000.0), 2)

    @property
    def last(self) -> Optional[float]:
        return self.times[-1] if self.times else None


class RosAgent:
    """ROS observability agent with an isolated, signed control transport."""

    MIN_CLOUD_POINTS = 1_000
    MAX_CUSTOM_CLOUD_POINTS = 1_000_000

    def __init__(
        self,
        robot_ip: str = "",
        profile_path: Optional[str] = None,
        cloud_max_points: Optional[int] = 18000,
        source_selection_path: Optional[str] = None,
    ) -> None:
        self.robot_ip = self._valid_ip(robot_ip)
        self.cloud_max_points = self._normalize_cloud_max_points(cloud_max_points)
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
        self.cloud_radius_limit = max(
            5.0,
            min(float(self.profile.get("cloud_radius_limit_m", 500.0)), 10_000.0),
        )
        self._cloud_frame_interval_s = max(
            0.10,
            min(float(self.profile.get("pointcloud_frame_interval_s", 0.18)), 1.0),
        )

        # Browser input is validated and statefully gated by the pure-Python
        # manager.  This process only transports its already-bounded outputs to
        # the separately watchdog-protected Go2 bridge.
        self._control_manager = ControlManager(self.profile)
        control_profile = self.profile.get("control", {})
        if not isinstance(control_profile, dict):
            control_profile = {}
        self._control_status_timeout_s = self._bounded_control_timeout(
            control_profile.get("bridge_status_timeout_s"),
            default=0.75,
            low=0.25,
            high=5.0,
        )
        self._control_lowstate_timeout_s = self._bounded_control_timeout(
            control_profile.get("telemetry_timeout_s"),
            default=0.50,
            low=0.20,
            high=2.0,
        )
        expected_bare_sport_publishers = control_profile.get(
            "expected_bare_sport_publishers", 0
        )
        if (
            isinstance(expected_bare_sport_publishers, bool)
            or not isinstance(expected_bare_sport_publishers, int)
            or not 0 <= expected_bare_sport_publishers <= 64
        ):
            raise ValueError(
                "control.expected_bare_sport_publishers must be an integer "
                "from 0 to 64"
            )
        self._control_expected_bare_sport_publishers = (
            expected_bare_sport_publishers
        )
        try:
            self._control_bridge_key: Optional[bytes] = shared_key(
                os.environ.get("ROBOT_SCOPE_CONTROL_BRIDGE_KEY", "")
            )
            bridge_key_error = ""
        except ControlProtocolError as exc:
            self._control_bridge_key = None
            bridge_key_error = str(exc)
        self._control_source_id = (
            f"robot-scope-agent-{os.getpid()}-{secrets.token_hex(8)}"
        )
        self._control_bridge_seq = -1
        self._control_bridge_epoch = ""

        self._lock = threading.RLock()
        # Serializes every control state mutation with output publication.  A
        # terminal stop/release that has returned can therefore never be
        # followed by a drive output drained by an earlier timer tick.
        self._control_operation_lock = threading.RLock()
        self._control_transport_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._node: Optional[Node] = None
        self._executor: Optional[MultiThreadedExecutor] = None
        self._control_callback_group: Optional[MutuallyExclusiveCallbackGroup] = None
        self._control_command_publisher: Any = None
        self._control_status_subscription: Any = None
        self._control_timer: Any = None
        self._control_status_received = 0.0
        self._control_status: Dict[str, Any] = {
            "state": "not_configured" if bridge_key_error else "waiting",
            "ready": False,
            "connected": False,
            "available": False,
            "message": bridge_key_error or "signed Go2 bridge status waiting",
        }
        self._control_shutdown = False

        # Nav2 never publishes Unitree requests directly.  While a navigation
        # session is active it owns an internal ControlManager lease and feeds
        # bounded /cmd_vel samples through the exact same signed watchdog
        # transport used by keyboard/gamepad control.
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
        # Motion-gating freshness is based only on each trusted callback's
        # fully validated samples.  Keep these receipts separate from the
        # generic topic metrics used by the observability UI: discovery or
        # another consumer calling ``_tick`` must never open the motion gate.
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
        self._started_at = time.monotonic()
        self._ready = False
        self._last_error = ""

        self._graph: Dict[str, Dict[str, Any]] = {}
        self._metrics: Dict[str, RateMeter] = {}
        self._summaries: Dict[str, Dict[str, Any]] = {}
        self._summary_updated: Dict[str, float] = {}
        self._subscriptions: Dict[str, Any] = {}
        self._special_subscription_topics: Dict[str, str] = {}

        self._joint_stale_after = max(
            0.2,
            min(float(self.profile.get("joint_state_stale_after_s", 1.0)), 10.0),
        )
        self._joint_last_processed = 0.0
        self._joints: Dict[str, Any] = {
            "seq": 0,
            "topic": "",
            "type": "",
            "position_rad": None,
            "imu_rpy_rad": None,
            "source_order": "",
            "stamp_ns": 0,
            "updated": 0.0,
        }

        self._pose_stale_after = max(
            0.25,
            min(float(self.profile.get("odometry_stale_after_s", 1.5)), 10.0),
        )
        self._pose_position_limit = max(
            1.0,
            min(float(self.profile.get("pose_position_limit_m", 10_000.0)), 1_000_000.0),
        )
        self._pose: Dict[str, Any] = {
            "seq": 0,
            "topic": "",
            "type": "",
            "pose": None,
            "stamp_ns": 0,
            "updated": 0.0,
        }

        self._sources: Dict[str, str] = {
            "camera": "",
            "pointcloud": "",
            "odometry": "",
            "occupancy_grid": "",
        }
        self._requested_sources: Dict[str, str] = dict(self._sources)
        self._source_selection_path = self._normalize_source_selection_path(
            source_selection_path
        )
        self._source_selection_policies = self._source_policies_from_profile()
        self._source_selection_overrides = self._load_source_selection_overrides()
        self._source_pins: set[str] = set()
        self._source_selection_origins: Dict[str, str] = {
            category: "auto" for category in SOURCE_CATEGORIES
        }
        self._apply_startup_source_selection()

        self._camera: Dict[str, Any] = {
            "seq": 0,
            "format": "none",
            "data": b"",
            "stamp_us": 0,
            "key": False,
            "width": 0,
            "height": 0,
            "encoding": "",
            "source": "none",
            "transport": "",
            "state": "waiting",
            "fps": None,
            "age_s": None,
        }
        self._camera_stream_ids: Dict[str, str] = {
            source_id: secrets.token_urlsafe(12) for source_id in CAMERA_SOURCE_IDS
        }
        self._remote_camera_frame: Dict[str, Any] = {
            "seq": 0,
            "format": "none",
            "data": b"",
            "stamp_us": 0,
            "key": False,
            "width": 0,
            "height": 0,
            "encoding": "",
            "source": "remote_mjpeg",
            "source_id": "realsense_color",
            "source_label": "RealSense color camera",
            "transport": "http_mjpeg",
            "state": "waiting",
            "fps": None,
            "age_s": None,
            "updated": 0.0,
        }
        self._h264_sps = b""
        self._h264_pps = b""
        self._h264_pending_stamp = 0
        self._h264_pending = bytearray()
        self._camera_decoder = H264JpegDecoder(self._decoded_camera_callback)
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
            self._direct_camera_callback,
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
        self._remote_camera = RemoteMjpegCamera(
            self._remote_camera_callback,
            enabled=(
                self._startup_robot_type == "go2"
                and bool(realsense_profile.get("enabled", False))
            ),
            url=str(realsense_profile.get("url", "")),
            allowed_urls=allowed_urls,
            source_id="realsense_color",
            source_label=str(
                realsense_profile.get("label", "RealSense color camera")
            ),
            stale_after_s=realsense_profile.get("stale_after_s", 3.0),
            request_timeout_s=realsense_profile.get("request_timeout_s", 6.0),
            restart_initial_s=realsense_profile.get("restart_initial_s", 0.5),
            restart_max_s=realsense_profile.get("restart_max_s", 8.0),
        )
        # The direct Go2 H.264 receiver is comparatively expensive (software
        # decode + JPEG relay).  Keep it stopped unless at least one camera
        # WebSocket is actively viewing it.  The separate lock makes the
        # first-open/last-close transition atomic across concurrent clients.
        self._camera_demand_lock = threading.RLock()
        self._camera_consumers = 0
        self._camera_accepting_demand = False
        self._camera_demand_tokens: Dict[str, set[str]] = {
            source_id: set() for source_id in CAMERA_SOURCE_IDS
        }
        self._camera_token_sources: Dict[str, str] = {}

        self._cloud: Dict[str, Any] = {
            "seq": 0,
            "points_bytes": b"",
            "source_points": 0,
            "frame_id": "",
            "bounds": None,
            "updated": 0.0,
        }
        # Browser clients use this non-secret epoch to distinguish a dashboard
        # restart from an out-of-order frame.  ROS sequence counters restart at
        # zero with the process; without an epoch a long-lived tab could reject
        # every frame from the new process indefinitely.
        self._cloud_stream_id = secrets.token_urlsafe(12)
        self._last_cloud_processed = 0.0

        self._map: Dict[str, Any] = {
            "seq": 0,
            "width": 0,
            "height": 0,
            "resolution": 0.0,
            "origin": [0.0, 0.0, 0.0],
            "frame_id": "",
            "data_b64": "",
            "updated": 0.0,
        }
        self._network_cache: Tuple[float, bool, Optional[float]] = (0.0, False, None)

    @staticmethod
    def _bounded_control_timeout(
        value: object,
        *,
        default: float,
        low: float,
        high: float,
    ) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(parsed):
            return default
        return max(low, min(parsed, high))

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
        if value is None:
            return None
        limit = int(value)
        if limit < cls.MIN_CLOUD_POINTS or limit > cls.MAX_CUSTOM_CLOUD_POINTS:
            raise ValueError(
                f"max_points must be between {cls.MIN_CLOUD_POINTS} and "
                f"{cls.MAX_CUSTOM_CLOUD_POINTS}, or null for all points"
            )
        return limit

    def cloud_point_settings(self) -> Dict[str, Any]:
        with self._lock:
            limit = self.cloud_max_points
            source_points = int(self._cloud.get("source_points", 0))
            sent_points = int(self._cloud.get("sent_points", 0))
        return {
            "max_points": limit,
            "all_points": limit is None,
            "min_points": self.MIN_CLOUD_POINTS,
            "max_custom_points": self.MAX_CUSTOM_CLOUD_POINTS,
            "source_points": source_points,
            "sent_points": sent_points,
            "frame_interval_s": self._pointcloud_frame_interval(limit),
            "transport": "binary_websocket",
        }

    def _pointcloud_frame_interval(self, point_limit: Optional[int]) -> float:
        """Target at most ~4 MB/s of packed XYZ data per browser client."""

        effective_points = self.MAX_CUSTOM_CLOUD_POINTS if point_limit is None else point_limit
        byte_budget_interval = (effective_points * 12) / 4_000_000.0
        return min(3.0, max(self._cloud_frame_interval_s, byte_budget_interval))

    def set_cloud_max_points(self, value: Optional[int]) -> Dict[str, Any]:
        limit = self._normalize_cloud_max_points(value)
        with self._lock:
            if limit != self.cloud_max_points:
                self.cloud_max_points = limit
                self._reset_cloud_locked(self._sources.get("pointcloud", ""))
            else:
                self._last_cloud_processed = 0.0
        return self.cloud_point_settings()

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
        if value is None or not str(value).strip():
            return None
        path = Path(str(value)).expanduser()
        return path if path.is_absolute() else Path.cwd() / path

    @staticmethod
    def _valid_source_name(value: object) -> bool:
        if not isinstance(value, str) or not 1 <= len(value) <= 255:
            return False
        if not value.startswith("/") or value.endswith("/") or "//" in value:
            return False
        return all(character.isalnum() or character in "_~/" for character in value)

    def _source_profile_scope(self) -> Dict[str, str]:
        return {
            "robot_type": str(self.profile.get("robot_type", "")),
            "name": str(self.profile.get("name", "Generic ROS 2")),
        }

    def _source_policies_from_profile(self) -> Dict[str, Dict[str, Any]]:
        raw = self.profile.get("source_selection", {}) if self.profile else {}
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ValueError("source_selection profile setting must be an object")
        unknown = set(raw) - set(SOURCE_CATEGORIES)
        if unknown:
            raise ValueError(
                f"unknown source_selection categories: {', '.join(sorted(unknown))}"
            )
        policies: Dict[str, Dict[str, Any]] = {}
        for category, value in raw.items():
            if not isinstance(value, dict):
                raise ValueError(f"source_selection.{category} must be an object")
            persistent = value.get("persistent", False)
            fail_closed = value.get("fail_closed", False)
            if not isinstance(persistent, bool) or not isinstance(fail_closed, bool):
                raise ValueError(
                    f"source_selection.{category} flags must be booleans"
                )
            allowed = value.get("allowed_offline", [])
            if not isinstance(allowed, list) or any(
                not self._valid_source_name(topic) for topic in allowed
            ):
                raise ValueError(
                    f"source_selection.{category}.allowed_offline must contain ROS topics"
                )
            if len(set(allowed)) != len(allowed):
                raise ValueError(
                    f"source_selection.{category}.allowed_offline contains duplicates"
                )
            default = value.get("default", "")
            if default and not self._valid_source_name(default):
                raise ValueError(
                    f"source_selection.{category}.default must be a ROS topic"
                )
            if default and default not in allowed:
                raise ValueError(
                    f"source_selection.{category}.default must be allowed offline"
                )
            if default and not fail_closed:
                raise ValueError(
                    f"source_selection.{category}.default requires fail_closed"
                )
            policies[category] = {
                "persistent": persistent,
                "fail_closed": fail_closed,
                "allowed_offline": frozenset(allowed),
                "default": default,
            }
        return policies

    def _validate_source_state_file(self, path: Path) -> os.stat_result:
        try:
            result = path.lstat()
        except FileNotFoundError:
            raise
        if stat.S_ISLNK(result.st_mode) or not stat.S_ISREG(result.st_mode):
            raise ValueError("source selection state must be a regular file")
        if result.st_uid != os.geteuid():
            raise ValueError("source selection state must be owned by the service user")
        if stat.S_IMODE(result.st_mode) != 0o600:
            raise ValueError("source selection state permissions must be 0600")
        if result.st_size > SOURCE_SELECTION_STATE_MAX_BYTES:
            raise ValueError("source selection state exceeds the size limit")
        return result

    def _load_source_selection_overrides(self) -> Dict[str, Dict[str, str]]:
        path = self._source_selection_path
        if path is None:
            return {}
        try:
            expected = self._validate_source_state_file(path)
        except FileNotFoundError:
            return {}
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise ValueError(f"cannot open source selection state: {exc}") from exc
        try:
            actual = os.fstat(descriptor)
            if (
                not stat.S_ISREG(actual.st_mode)
                or actual.st_dev != expected.st_dev
                or actual.st_ino != expected.st_ino
            ):
                raise ValueError("source selection state changed while opening")
            payload = os.read(descriptor, SOURCE_SELECTION_STATE_MAX_BYTES + 1)
        finally:
            os.close(descriptor)
        if len(payload) > SOURCE_SELECTION_STATE_MAX_BYTES:
            raise ValueError("source selection state exceeds the size limit")
        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("source selection state is not valid JSON") from exc
        if not isinstance(document, dict):
            raise ValueError("source selection state must be an object")
        if document.get("version") != SOURCE_SELECTION_STATE_VERSION:
            raise ValueError("unsupported source selection state version")
        if document.get("profile") != self._source_profile_scope():
            return {}
        selections = document.get("selections", {})
        if not isinstance(selections, dict):
            raise ValueError("source selection state selections must be an object")
        overrides: Dict[str, Dict[str, str]] = {}
        for category, entry in selections.items():
            policy = self._source_selection_policies.get(category)
            if not policy or not policy["persistent"]:
                continue
            if not isinstance(entry, dict):
                raise ValueError(f"persisted {category} selection must be an object")
            mode = entry.get("mode")
            topic = entry.get("topic")
            if mode != "pinned" or not self._valid_source_name(topic):
                raise ValueError(f"persisted {category} selection is invalid")
            if topic not in policy["allowed_offline"]:
                raise ValueError(
                    f"persisted {category} selection is not allowed by this profile"
                )
            overrides[category] = {"mode": "pinned", "topic": str(topic)}
        return overrides

    def _apply_startup_source_selection(self) -> None:
        for category, policy in self._source_selection_policies.items():
            override = self._source_selection_overrides.get(category)
            if override:
                topic = override["topic"]
                self._requested_sources[category] = topic
                self._sources[category] = topic
                if policy["fail_closed"]:
                    self._source_pins.add(category)
                self._source_selection_origins[category] = "persisted"
                continue
            default = str(policy.get("default", ""))
            if default:
                self._requested_sources[category] = default
                self._sources[category] = default
                self._source_pins.add(category)
                self._source_selection_origins[category] = "profile_default"

    def _write_source_selection_overrides(
        self,
        overrides: Dict[str, Dict[str, str]],
    ) -> None:
        path = self._source_selection_path
        if path is None:
            return
        document = {
            "version": SOURCE_SELECTION_STATE_VERSION,
            "profile": self._source_profile_scope(),
            "selections": overrides,
        }
        payload = (
            json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        if len(payload) > SOURCE_SELECTION_STATE_MAX_BYTES:
            raise ValueError("source selection state exceeds the size limit")
        parent = path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent_stat = parent.lstat()
        if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
            raise ValueError("source selection state directory must be a real directory")
        try:
            self._validate_source_state_file(path)
        except FileNotFoundError:
            pass
        descriptor = -1
        temporary = ""
        try:
            descriptor, temporary = tempfile.mkstemp(
                prefix=f".{path.name}.",
                dir=parent,
            )
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = ""
            os.chmod(path, 0o600, follow_symlinks=False)
            directory_flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                directory_flags |= os.O_DIRECTORY
            directory_fd = os.open(parent, directory_flags)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise ValueError(f"cannot persist source selection: {exc}") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        with self._camera_demand_lock:
            self._camera_accepting_demand = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="robot-scope-ros", daemon=True)
        self._thread.start()

    @staticmethod
    def _valid_camera_source_id(source_id: object) -> bool:
        return isinstance(source_id, str) and source_id in CAMERA_SOURCE_IDS

    def camera_stream_open(self, source_id: str = "go2_front") -> Dict[str, Any]:
        """Acquire one opaque, exactly-once demand token for a fixed source."""

        if not self._valid_camera_source_id(source_id):
            return {
                "accepted": False,
                "reason": "camera_source_not_found",
                "consumers": self._camera_consumers,
            }
        with self._camera_demand_lock:
            if not self._camera_accepting_demand:
                return {
                    "accepted": False,
                    "reason": "camera_relay_shutting_down",
                    "consumers": self._camera_consumers,
                }
            if len(self._camera_token_sources) >= MAX_CAMERA_VIEWERS:
                return {
                    "accepted": False,
                    "reason": "camera_viewer_limit_reached",
                    "consumers": self._camera_consumers,
                }
            if len(self._camera_demand_tokens[source_id]) >= MAX_CAMERA_VIEWERS_PER_SOURCE:
                return {
                    "accepted": False,
                    "reason": "camera_source_viewer_limit_reached",
                    "consumers": self._camera_consumers,
                }
            active_sources = sum(
                1 for source_tokens in self._camera_demand_tokens.values() if source_tokens
            )
            if (
                not self._camera_demand_tokens[source_id]
                and active_sources >= MAX_ACTIVE_CAMERA_SOURCES
            ):
                return {
                    "accepted": False,
                    "reason": "active_camera_source_limit_reached",
                    "consumers": self._camera_consumers,
                }
            status = (
                self._direct_camera.status()
                if source_id == "go2_front"
                else self._remote_camera.status()
            )
            # ``go2_front`` also names the original ROS camera stream when a
            # profile has no direct multicast receiver.  Keep the legacy
            # source-less WebSocket usable for generic ROS profiles.
            if source_id != "go2_front" and not bool(status.get("configured", False)):
                return {
                    "accepted": False,
                    "reason": "camera_source_unavailable",
                    "consumers": self._camera_consumers,
                }
            token = secrets.token_urlsafe(24)
            tokens = self._camera_demand_tokens[source_id]
            first_for_source = not tokens
            tokens.add(token)
            self._camera_token_sources[token] = source_id
            self._camera_consumers = len(self._camera_token_sources)
            if first_for_source:
                self._clear_camera_frame(source_id)
                receiver = (
                    self._direct_camera
                    if source_id == "go2_front"
                    else self._remote_camera
                )
                try:
                    started = (
                        receiver.start()
                        if source_id != "go2_front" or self._direct_camera.configured
                        else True
                    )
                except Exception:
                    tokens.remove(token)
                    self._camera_token_sources.pop(token, None)
                    self._camera_consumers = len(self._camera_token_sources)
                    raise
                if not started:
                    tokens.remove(token)
                    self._camera_token_sources.pop(token, None)
                    self._camera_consumers = len(self._camera_token_sources)
                    return {
                        "accepted": False,
                        "reason": "camera_source_unavailable",
                        "consumers": self._camera_consumers,
                    }
            return {
                "accepted": True,
                "source_id": source_id,
                "token": token,
                "consumers": self._camera_consumers,
                "source_viewers": len(tokens),
            }

    def camera_stream_close(
        self,
        source_id: str = "go2_front",
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Release a demand token once; duplicate/foreign closes are no-ops."""

        if not self._valid_camera_source_id(source_id):
            return {"released": False, "consumers": self._camera_consumers}
        with self._camera_demand_lock:
            tokens = self._camera_demand_tokens[source_id]
            release_token = token
            if (
                not release_token
                or self._camera_token_sources.get(release_token) != source_id
                or release_token not in tokens
            ):
                return {
                    "released": False,
                    "consumers": len(self._camera_token_sources),
                    "source_viewers": len(tokens),
                }
            tokens.remove(release_token)
            self._camera_token_sources.pop(release_token, None)
            self._camera_consumers = len(self._camera_token_sources)
            if not tokens:
                receiver = (
                    self._direct_camera
                    if source_id == "go2_front"
                    else self._remote_camera
                )
                receiver.stop()
                self._clear_camera_frame(source_id)
            return {
                "released": True,
                "consumers": self._camera_consumers,
                "source_viewers": len(tokens),
            }

    def _clear_camera_frame(self, source_id: str = "go2_front") -> None:
        """Drop only the selected source's frame between viewer sessions."""

        with self._lock:
            target = (
                self._camera
                if source_id == "go2_front"
                else self._remote_camera_frame
            )
            cleared = {
                "seq": int(target.get("seq", 0)) + 1,
                "format": "none",
                "data": b"",
                "stamp_us": 0,
                "key": False,
                "width": 0,
                "height": 0,
                "encoding": "",
                "source": "go2_multicast" if source_id == "go2_front" else "remote_mjpeg",
                "source_id": source_id,
                "source_label": (
                    "Go2 front camera"
                    if source_id == "go2_front"
                    else "RealSense color camera"
                ),
                "transport": (
                    "udp_multicast_rtp_h264"
                    if source_id == "go2_front"
                    else "http_mjpeg"
                ),
                "state": "waiting",
                "fps": None,
                "age_s": None,
                "updated": 0.0,
            }
            if source_id == "go2_front":
                self._camera = cleared
            else:
                self._remote_camera_frame = cleared

    def stop(self) -> None:
        # Publish the manager's final signed stop while the ROS node and
        # executor are still alive.  The standalone bridge has its own watchdog
        # as a second line of defence if transport is already unavailable.
        self.navigation_deactivate("agent_stop")
        self.shutdown_control()
        self._stop_event.set()
        with self._camera_demand_lock:
            self._camera_accepting_demand = False
            self._camera_consumers = 0
            self._camera_token_sources.clear()
            for tokens in self._camera_demand_tokens.values():
                tokens.clear()
            self._direct_camera.stop()
            self._remote_camera.stop()
        self._camera_decoder.stop()
        executor = self._executor
        if executor:
            try:
                executor.shutdown(timeout_sec=2.0)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=4.0)

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
        """Create the signed dashboard-to-watchdog transport in one group."""

        try:
            callback_group = MutuallyExclusiveCallbackGroup()
            reliable = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            publisher = node.create_publisher(
                String,
                CONTROL_COMMAND_TOPIC,
                reliable,
                callback_group=callback_group,
            )
            subscription = node.create_subscription(
                String,
                CONTROL_STATUS_TOPIC,
                self._control_status_callback,
                reliable,
                callback_group=callback_group,
            )
            timer = node.create_timer(
                0.05,
                self._control_tick,
                callback_group=callback_group,
            )
            with self._control_transport_lock:
                self._control_callback_group = callback_group
                self._control_command_publisher = publisher
                self._control_status_subscription = subscription
                self._control_timer = timer
        except Exception as exc:
            self._set_control_unready(f"control ROS transport unavailable: {exc}")

    def _setup_navigation_transport(self, node: Node) -> None:
        """Create fixed Nav2 ingress/action/service endpoints.

        Message types are resolved only after the ROS environment has been
        sourced.  A missing Nav2 installation leaves observation available but
        autonomous driving unavailable; it never weakens manual control.
        """

        try:
            from rclpy.action import ActionClient
            from rosidl_runtime_py.utilities import get_action, get_service

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
                self._navigation["error"] = f"Nav2 ROS transport unavailable: {exc}"[:240]
                self._navigation["seq"] += 1

    @staticmethod
    def _navigation_pose_values(x: object, y: object, yaw: object) -> tuple[float, float, float]:
        values: list[float] = []
        for label, value in (("x", x), ("y", y), ("yaw", yaw)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise CommandValidationError(f"navigation pose {label} must be numeric")
            number = float(value)
            if not math.isfinite(number):
                raise CommandValidationError(f"navigation pose {label} must be finite")
            values.append(number)
        if abs(values[0]) > 10_000.0 or abs(values[1]) > 10_000.0:
            raise CommandValidationError("navigation pose is outside the supported map bounds")
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
        node = self._node
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

    def navigation_activate(
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
        if len(revision) != 64 or any(char not in "0123456789abcdef" for char in revision):
            raise CommandValidationError("navigation map revision is invalid")
        if (
            isinstance(ready_after, bool)
            or not isinstance(ready_after, (int, float))
            or not math.isfinite(float(ready_after))
            or float(ready_after) < 0.0
        ):
            raise CommandValidationError("navigation readiness fence is invalid")
        with self._control_operation_lock:
            self.navigation_start_preflight()
            interlock = self._navigation_prelocalization_reason(
                time.monotonic(),
                ready_after=float(ready_after),
            )
            if interlock:
                # This check occurs immediately before acquisition.  The Nav2
                # process may run while sensors warm up, but it cannot reserve
                # or retain the robot's motion lease during that interval.
                raise ControlNotReady(interlock)
            acquired = self._control_manager.acquire_navigation_lease()
            token = str(acquired["token"])
            binding = f"robot-scope-navigation-{secrets.token_urlsafe(18)}"
            try:
                self._control_manager.bind_lease(token, binding)
            except Exception:
                try:
                    self._control_manager.release_lease(token)
                except ControlError:
                    pass
                self._flush_control_outputs()
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
                        "localization": {"state": "uninitialized", "pose": None},
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
            self._flush_control_outputs()
        return self.navigation_runtime_snapshot()

    def navigation_start_preflight(self) -> Dict[str, Any]:
        """Check whether navigation could reserve motion without doing so."""

        with self._control_operation_lock:
            self._ensure_go2_control_target()
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
                    raise LeaseBusy("another navigation session already owns the robot")
            control = self._control_manager.snapshot()
            if not control.get("configured") or control.get("closed"):
                raise ControlDisabled("robot control is not configured")
            estop = control.get("estop") if isinstance(control.get("estop"), dict) else {}
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
            lease = control.get("lease") if isinstance(control.get("lease"), dict) else {}
            if lease.get("active"):
                raise LeaseBusy("another controller already owns the robot")
            return {"ready": True}

    def navigation_prelocalization_snapshot(
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
            "reason": None if reason is None else _public_navigation_reason(reason),
        }

    def _navigation_cancel_handle(self, handle: Any) -> None:
        if handle is None:
            return
        try:
            handle.cancel_goal_async()
        except Exception:
            pass

    def navigation_deactivate(
        self,
        reason: str = "navigation_stop",
    ) -> Dict[str, Any]:
        """Close the Nav2 velocity gate and issue signed StopMove first."""

        public_reason = _public_navigation_reason(reason)
        normal_stop = reason in {"navigation_stop", "operator_stop"}
        with self._control_operation_lock:
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
                        "localization": {"state": "uninitialized", "pose": None},
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
                    self._control_manager.release_lease(token, binding or None)
                    stop_published = True
                except (ControlError, ValueError):
                    pass
            if was_active and not stop_published:
                self._publish_control_outputs(
                    [
                        {
                            "type": "stop",
                            "reason": public_reason,
                            "velocity": {"vx": 0.0, "vy": 0.0, "wz": 0.0},
                            "created_at": time.monotonic(),
                        }
                    ]
                )
            self._flush_control_outputs()
            # Stop crosses the signed transport before asynchronous Nav2
            # cancellation can wait on a failed action server.
            self._navigation_cancel_handle(handle)
        return self.navigation_runtime_snapshot()

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
                    parent = str(getattr(message.header, "frame_id", "")).lstrip("/")
                    child = str(getattr(message, "child_frame_id", "")).lstrip("/")
                    if parent != "camera_init" or child != "body":
                        raise ValueError("unexpected FAST-LIO odometry frames")
                if not self._navigation_commit_odom_stamp(
                    topic,
                    stamp_ns,
                ):
                    # The first controller sample, and the first sample after
                    # an inactive robot-clock reset, establish only a new
                    # baseline.  A later strict advance is required before the
                    # stream can become fresh.
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
                self.navigation_deactivate(f"invalid {topic} sample: {exc}")
            return
        self._tick(topic, observed_at)

    def _navigation_validate_odom_stamp(self, topic: str, message: Any) -> int:
        """Validate timestamp shape and clock bounds without mutating state.

        FAST-LIO is stamped from the dashboard host clock, so it must also be
        close to that clock.  Unitree's controller odometry advances on the
        robot clock and may carry a stable offset from the host after either
        machine synchronizes time.  That stream is observed through a
        best-effort KEEP_LAST(1) reader; strict stamp progression plus the
        separate monotonic receipt-age watchdog proves liveness without
        treating the robot clock as the host clock.
        """

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
            node = self._node
            if node is None:
                raise ValueError("ROS clock is unavailable")
            now_ns = node.get_clock().now().nanoseconds
            if isinstance(now_ns, bool) or not isinstance(now_ns, int) or now_ns <= 0:
                raise ValueError("ROS clock is invalid")
            age_ns = now_ns - stamp_ns
            if age_ns > int(NAVIGATION_ODOM_STAMP_MAX_AGE_S * 1_000_000_000):
                raise ValueError("odometry timestamp is stale")
            if age_ns < -int(NAVIGATION_ODOM_STAMP_MAX_FUTURE_S * 1_000_000_000):
                raise ValueError("odometry timestamp is in the future")

        return stamp_ns

    def _navigation_commit_odom_stamp(
        self,
        topic: str,
        stamp_ns: int,
    ) -> bool:
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
                        # A stopped Unitree can reboot or reset its device
                        # clock.  Re-prime while motion is disarmed, but do not
                        # call this sample fresh; the next sample must advance.
                        self._navigation_odom_stamp_ns[topic] = stamp_ns
                        return False
                raise ValueError("odometry timestamp did not increase")

            self._navigation_odom_stamp_ns[topic] = stamp_ns
            return True

    def _navigation_runtime_health_callback(self, message: String) -> None:
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
                    raise ValueError(f"health publisher count for {topic} is invalid")
                sanitized_counts[topic] = count
            if payload.get("ready") and any(
                count != 1 for count in sanitized_counts.values()
            ):
                raise ValueError("ready health has non-unique sensor sources")
            input_points = int(payload.get("input_points", 0))
            accepted_points = int(payload.get("accepted_points", 0))
            if input_points < 0 or accepted_points < 0 or accepted_points > input_points:
                raise ValueError("health point counts are invalid")
            node = self._node
            publishers = (
                node.count_publishers(NAVIGATION_RUNTIME_HEALTH_TOPIC)
                if node
                else 0
            )
            if publishers != 1:
                raise ValueError(
                    f"expected one navigation runtime health publisher, found {publishers}"
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
        node = self._node
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
            self.navigation_deactivate(
                f"expected one localization pose publisher, found {publishers}"
            )
            return
        try:
            pose = message.pose.pose
            x = float(pose.position.x)
            y = float(pose.position.y)
            orientation = pose.orientation
            yaw = math.atan2(
                2.0 * (orientation.w * orientation.z + orientation.x * orientation.y),
                1.0 - 2.0 * (orientation.y * orientation.y + orientation.z * orientation.z),
            )
            x, y, yaw = self._navigation_pose_values(x, y, yaw)
        except (AttributeError, TypeError, ValueError, CommandValidationError) as exc:
            with self._navigation_lock:
                self._navigation_validated_receipts[
                    NAVIGATION_LOCALIZATION_POSE_TOPIC
                ] = 0.0
                active = bool(self._navigation.get("active"))
            if active:
                self.navigation_deactivate(f"invalid localization pose: {exc}")
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
        node = self._node
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
            # cmd_vel can remain silent while a controller is stopped; its
            # publisher uniqueness is the safety property, not sample rate.
            if topic in self._navigation_validated_receipts:
                recent, _ = self._navigation_validated_recency(
                    topic,
                    now,
                    maximum_age,
                )
            else:
                # cmd_vel can legitimately remain silent while stopped; its
                # unique publisher is the complete gate for this topic.
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

        with self._control_operation_lock:
            with self._navigation_lock:
                token = self._navigation_token
                binding = self._navigation_binding
                sequence = (
                    self._navigation_next_sequence_locked()
                    if token and binding
                    else -1
                )
                self._navigation["last_cmd_at"] = 0.0
                self._navigation["last_cmd"] = {"vx": 0.0, "vy": 0.0, "wz": 0.0}
                self._navigation["seq"] += 1
            submitted = False
            if token and binding:
                try:
                    self._control_manager.submit_drive(
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
                self._publish_control_outputs(
                    [
                        {
                            "type": "stop",
                            "reason": str(reason)[:160] or "navigation stop",
                            "velocity": {"vx": 0.0, "vy": 0.0, "wz": 0.0},
                            "created_at": time.monotonic(),
                        }
                    ]
                )
            self._flush_control_outputs()

    def _navigation_keepalive_locked(self, now: float) -> Optional[str]:
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
            self._control_manager.heartbeat(token, binding, sequence)
        except ControlError as exc:
            return f"navigation heartbeat failed: {exc}"
        with self._navigation_lock:
            if token == self._navigation_token:
                self._navigation_last_heartbeat = now
        return None

    def _navigation_reconcile_control_locked(self, now: float) -> Optional[str]:
        with self._navigation_lock:
            if not self._navigation.get("active"):
                return None
            goal_state = str((self._navigation.get("goal") or {}).get("state", "idle"))
        snapshot = self._control_manager.snapshot()
        lease = snapshot.get("lease", {})
        if not lease.get("active") or lease.get("input_source") != "navigation":
            return "navigation control lease was lost"
        # The internal lease remains motion-capable even before a goal is
        # active.  Keep its minimum cloud/odom/scan gate live throughout the
        # whole session, and strengthen it with localization/controller inputs
        # while a goal could command motion.
        return self._navigation_sensor_interlock_reason(
            now,
            require_localized=goal_state in {"pending", "active", "canceling"},
        )

    def _navigation_submit_velocity(self, vx: float, vy: float, wz: float) -> None:
        with self._control_operation_lock:
            with self._navigation_lock:
                if not self._navigation.get("active"):
                    return
                goal_state = str((self._navigation.get("goal") or {}).get("state", "idle"))
                token = self._navigation_token
                binding = self._navigation_binding
            snapshot = self._control_manager.snapshot()
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
            # A controller command may arrive while the action request is still
            # pending.  Never allow non-zero motion until the server explicitly
            # accepts the exact goal and all trusted sensor gates are fresh.
            if goal_state != "active":
                self._navigation_issue_stop("navigation goal is not active")
                return
            interlock = self._navigation_sensor_interlock_reason(
                time.monotonic(),
                require_localized=True,
            )
            if interlock:
                self.navigation_deactivate(interlock)
                return
            try:
                with self._navigation_lock:
                    sequence = self._navigation_next_sequence_locked()
                self._control_manager.submit_drive(
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
                self._flush_control_outputs()
            except ControlError as exc:
                self.navigation_deactivate(f"navigation command rejected: {exc}")

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
            self.navigation_deactivate("invalid Nav2 velocity")
            return
        node = self._node
        try:
            publishers = node.count_publishers(NAVIGATION_CMD_VEL_TOPIC) if node else 0
        except Exception:
            publishers = 0
        if publishers != 1:
            self.navigation_deactivate(
                f"expected one Nav2 velocity publisher, found {publishers}"
            )
            return
        self._navigation_submit_velocity(*values)

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
            or str(map_revision).lower() != str(active_map.get("revision", "")).lower()
        ):
            raise CommandValidationError("navigation map revision does not match the active session")

    def navigation_set_initial_pose(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: object,
        y: object,
        yaw: object,
    ) -> Dict[str, Any]:
        x_value, y_value, yaw_value = self._navigation_pose_values(x, y, yaw)
        with self._control_operation_lock:
            interlock = self._navigation_sensor_interlock_reason(
                time.monotonic(),
                require_localized=False,
            )
            if interlock:
                raise ControlDisabled(interlock)
            with self._navigation_lock:
                self._navigation_require_pinned_map_locked(map_id, map_revision)
                goal_state = str((self._navigation.get("goal") or {}).get("state", "idle"))
                if goal_state in {"pending", "active", "canceling"}:
                    raise LeaseBusy("cancel the active goal before resetting localization")
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
        return self.navigation_runtime_snapshot()

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
                distance = float(getattr(feedback, "distance_remaining", float("nan")))
                goal["distance_remaining"] = round(max(0.0, distance), 3) if math.isfinite(distance) else None
            except (TypeError, ValueError):
                goal["distance_remaining"] = None
            goal["navigation_time"] = self._duration_seconds(
                getattr(feedback, "navigation_time", None)
            )
            try:
                goal["recoveries"] = max(0, int(getattr(feedback, "number_of_recoveries", 0)))
            except (TypeError, ValueError):
                goal["recoveries"] = 0
            # Feedback can be scheduled before the goal-response callback.
            # Keep the non-zero gate closed until an accepted handle for this
            # exact generation has been stored.
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
            if not stale and handle is not None and bool(getattr(handle, "accepted", False)):
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
                    g, i, completed
                )
            )
        except Exception as exc:
            with self._navigation_lock:
                goal = dict(self._navigation.get("goal") or {})
                if generation == self._navigation_goal_generation and goal.get("goal_id") == goal_id:
                    goal["state"] = "failed"
                    goal["error"] = f"NavigateToPose result unavailable: {exc}"[:200]
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
        state = {4: "succeeded", 5: "canceled", 6: "failed"}.get(status, "failed")
        with self._navigation_lock:
            goal = dict(self._navigation.get("goal") or {})
            if generation != self._navigation_goal_generation or goal.get("goal_id") != goal_id:
                return
            goal["state"] = state
            goal["error"] = error if error else ("navigation aborted" if status == 6 else None)
            self._navigation["goal"] = goal
            self._navigation_goal_handle = None
            self._navigation_cancel_requested = False
            self._navigation["seq"] += 1
        # Close the non-zero command gate immediately at every terminal state.
        self._navigation_issue_stop(f"navigation goal {state}")

    def navigation_send_goal(
        self,
        *,
        map_id: str,
        map_revision: str,
        x: object,
        y: object,
        yaw: object,
    ) -> Dict[str, Any]:
        x_value, y_value, yaw_value = self._navigation_pose_values(x, y, yaw)
        with self._control_operation_lock:
            interlock = self._navigation_sensor_interlock_reason(
                time.monotonic(),
                require_localized=True,
            )
            if interlock:
                raise ControlDisabled(interlock)
            with self._navigation_lock:
                self._navigation_require_pinned_map_locked(map_id, map_revision)
                if (self._navigation.get("localization") or {}).get("state") != "localized":
                    raise ControlDisabled("a fresh localized pose is required before sending a goal")
                current = self._navigation.get("goal") or {}
                if current.get("state") in {"pending", "active", "canceling"}:
                    raise LeaseBusy("another navigation goal is active")
                client = self._navigation_action_client
                if client is None or not client.server_is_ready():
                    raise ControlDisabled("NavigateToPose action server is unavailable")
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
                    feedback_callback=lambda feedback, g=generation, i=goal_id: self._navigation_feedback_callback(
                        g, i, feedback
                    ),
                )
                future.add_done_callback(
                    lambda completed, g=generation, i=goal_id: self._navigation_goal_response_callback(
                        g, i, completed
                    )
                )
            except Exception as exc:
                with self._navigation_lock:
                    goal = dict(self._navigation.get("goal") or {})
                    if goal.get("goal_id") == goal_id:
                        goal["state"] = "failed"
                        goal["error"] = f"NavigateToPose request failed: {exc}"[:200]
                        self._navigation["goal"] = goal
                        self._navigation["seq"] += 1
                self._navigation_issue_stop("NavigateToPose request failed")
                raise ControlDisabled("NavigateToPose request could not be sent") from exc
        return self.navigation_runtime_snapshot()

    def navigation_cancel_goal(self, *, goal_id: str) -> Dict[str, Any]:
        identifier = str(goal_id).strip()
        with self._control_operation_lock:
            with self._navigation_lock:
                goal = dict(self._navigation.get("goal") or {})
                if not identifier or identifier != goal.get("goal_id"):
                    raise CommandValidationError("goal id does not match the active navigation goal")
                if goal.get("state") not in {"pending", "active", "canceling"}:
                    return self.navigation_runtime_snapshot()
                goal["state"] = "canceling"
                self._navigation["goal"] = goal
                self._navigation_cancel_requested = True
                handle = self._navigation_goal_handle
                token = self._navigation_token
                binding = self._navigation_binding
                sequence = self._navigation_next_sequence_locked() if token and binding else -1
                self._navigation["seq"] += 1
            # Stop first; cancellation acknowledgment can be delayed or lost.
            if token and binding:
                try:
                    self._control_manager.submit_drive(
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
            self._flush_control_outputs()
            self._navigation_cancel_handle(handle)
        return self.navigation_runtime_snapshot()

    def navigation_clear_costmaps(self, *, scope: str = "both") -> Dict[str, Any]:
        normalized = str(scope).strip().lower()
        if normalized not in {"both", "global", "local"}:
            raise CommandValidationError("costmap scope must be both, global, or local")
        with self._navigation_lock:
            if not self._navigation.get("active"):
                raise ControlDisabled("navigation is not active")
            goal_state = str((self._navigation.get("goal") or {}).get("state", "idle"))
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
            clients = [(service, self._navigation_clear_clients.get(service)) for service in services]
            if any(client is None or not client.service_is_ready() for _, client in clients):
                raise ControlDisabled("requested costmap service is unavailable")
            self._navigation["clear_costmaps"] = {"state": "running", "error": None}
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
            future.add_done_callback(lambda done, name=service: completed(name, done))
        return self.navigation_runtime_snapshot()

    def navigation_runtime_snapshot(self) -> Dict[str, Any]:
        now = time.monotonic()
        with self._control_operation_lock:
            control = self._control_manager.snapshot()
            with self._navigation_lock:
                snapshot = copy.deepcopy(self._navigation)
                configured = self._navigation_transport_configured_locked()
                action_client = self._navigation_action_client
                clear_clients = dict(self._navigation_clear_clients)
        runtime_health = self._navigation_runtime_health_snapshot(now)
        node = self._node
        try:
            cmd_publishers = node.count_publishers(NAVIGATION_CMD_VEL_TOPIC) if node else 0
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
                topic_publishers[topic] = node.count_publishers(topic) if node else 0
            except Exception:
                topic_publishers[topic] = 0
        try:
            action_ready = bool(action_client and action_client.server_is_ready())
        except Exception:
            action_ready = False
        clear_ready = {}
        for service in NAVIGATION_CLEAR_SERVICES:
            try:
                clear_ready[service] = bool(
                    clear_clients.get(service) and clear_clients[service].service_is_ready()
                )
            except Exception:
                clear_ready[service] = False

        scan_fresh, raw_scan_age = self._navigation_validated_recency(
            "/scan", now, 1.0
        )
        fast_odom_fresh, raw_fast_odom_age = self._navigation_validated_recency(
            NAVIGATION_FAST_LIO_ODOM_TOPIC, now, 1.0
        )
        controller_odom_fresh, raw_controller_odom_age = self._navigation_validated_recency(
            NAVIGATION_CONTROLLER_ODOM_TOPIC, now, 1.0
        )
        localization_fresh, raw_localization_age = self._navigation_validated_recency(
            NAVIGATION_LOCALIZATION_POSE_TOPIC, now, 1.5
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
        target_supported = self._go2_control_target()
        manual_active = bool(
            lease.get("active") and lease.get("input_source") in {"keyboard", "gamepad"}
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
        localization_state = str((snapshot.get("localization") or {}).get("state", "uninitialized"))
        can_start = configured and target_supported and bridge_ready and not manual_active and not active
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
        snapshot.update(
            {
                "available": bool(configured and target_supported),
                "robot_online": bridge_ready,
                "command_topic": NAVIGATION_CMD_VEL_TOPIC,
                "readiness": {
                    "transport": configured,
                    "map_server": bool(self._graph.get("/map", {}).get("publishers", 0)),
                    "localization": localization_ready,
                    "planner": bool(self._graph.get("/plan", {}).get("publishers", 0)),
                    "controller": cmd_publishers == 1,
                    "behavior": action_ready,
                    "cmd_bridge": bridge_ready,
                    "map": bool(self._graph.get("/map", {}).get("publishers", 0)),
                    "scan": scan_ready,
                    "odometry": fast_odom_ready and controller_odom_ready,
                    "localization_odometry": fast_odom_ready,
                    "controller_odometry": controller_odom_ready,
                    "runtime_health": runtime_ready,
                    "tf": bool(self._graph.get("/tf", {}).get("publishers", 0)),
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
            None if last_cmd_at <= 0.0 else round(max(0.0, now - last_cmd_at), 3)
        )
        return snapshot

    @staticmethod
    def _control_status_readiness(
        payload: Dict[str, Any],
        *,
        lowstate_timeout_s: float,
        expected_bare_sport_publishers: int = 0,
    ) -> Tuple[bool, bool, str]:
        """Validate the bridge health fields after signature verification."""

        if payload.get("type") != "bridge_status":
            raise ControlProtocolError("unexpected bridge status type")
        reported_ready = payload.get("ready")
        if not isinstance(reported_ready, bool):
            raise ControlProtocolError("bridge ready flag is invalid")
        subscribers = payload.get("sport_subscribers")
        if isinstance(subscribers, bool) or not isinstance(subscribers, int):
            raise ControlProtocolError("bridge subscriber count is invalid")
        sport_publishers = payload.get("sport_publishers")
        if (
            isinstance(sport_publishers, bool)
            or not isinstance(sport_publishers, int)
            or sport_publishers < 0
            or sport_publishers > 128
        ):
            raise ControlProtocolError("sport request publisher count is invalid")
        publisher_fields = {
            "own_sport_publishers": 16,
            "foreign_named_sport_publishers": 16,
            "bare_unitree_sport_publishers": 64,
            "expected_bare_sport_publishers": 64,
        }
        publisher_counts: Dict[str, int] = {}
        for field, upper_bound in publisher_fields.items():
            value = payload.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
                or value > upper_bound
            ):
                raise ControlProtocolError(f"{field} is invalid")
            publisher_counts[field] = value
        if publisher_counts["expected_bare_sport_publishers"] != int(
            expected_bare_sport_publishers
        ):
            raise ControlProtocolError(
                "bridge bare sport publisher expectation does not match profile"
            )
        if sport_publishers != (
            publisher_counts["own_sport_publishers"]
            + publisher_counts["foreign_named_sport_publishers"]
            + publisher_counts["bare_unitree_sport_publishers"]
        ):
            raise ControlProtocolError("sport request publisher counts are inconsistent")
        publishers = payload.get("lowstate_publishers")
        if isinstance(publishers, bool) or not isinstance(publishers, int):
            raise ControlProtocolError("LowState publisher count is invalid")
        bridge_epoch = payload.get("bridge_epoch")
        if not isinstance(bridge_epoch, str) or not 16 <= len(bridge_epoch) <= 128:
            raise ControlProtocolError("bridge epoch is invalid")
        lowstate_age_ms = payload.get("lowstate_age_ms")
        if (
            isinstance(lowstate_age_ms, bool)
            or not isinstance(lowstate_age_ms, (int, float))
            or not math.isfinite(float(lowstate_age_ms))
            or float(lowstate_age_ms) < 0.0
        ):
            lowstate_ready = False
        else:
            lowstate_ready = (
                float(lowstate_age_ms) <= float(lowstate_timeout_s) * 1_000.0
            )
        # ``ready`` is calculated by the watchdog from both telemetry freshness
        # and the presence of a Unitree sport-request subscriber.  Recheck the
        # subscriber field instead of trusting a truthy status value alone.
        bridge_ready = (
            reported_ready
            and subscribers == 1
            and publisher_counts["own_sport_publishers"] == 1
            and publisher_counts["foreign_named_sport_publishers"] == 0
            and publisher_counts["bare_unitree_sport_publishers"]
            == expected_bare_sport_publishers
            and publishers == 1
        )
        return bridge_ready, lowstate_ready, bridge_epoch

    def _control_status_callback(self, message: String) -> None:
        key = self._control_bridge_key
        if key is None:
            self._set_control_unready("signed bridge key is not configured")
            return
        try:
            payload = decode_signed(
                message.data,
                key,
                max_age_s=max(1.0, self._control_status_timeout_s * 2.0),
            )
            bridge_ready, lowstate_ready, bridge_epoch = self._control_status_readiness(
                payload,
                lowstate_timeout_s=self._control_lowstate_timeout_s,
                expected_bare_sport_publishers=(
                    self._control_expected_bare_sport_publishers
                ),
            )
        except (ControlProtocolError, TypeError, ValueError) as exc:
            self._set_control_unready(f"rejected bridge status: {exc}")
            return

        now = time.monotonic()
        available = bridge_ready and lowstate_ready
        status = dict(payload)
        status.update(
            {
                "authenticated": True,
                "connected": available,
                "available": available,
                "message": (
                    "signed Go2 bridge ready"
                    if available
                    else str(payload.get("last_error") or "Go2 bridge is not ready")
                ),
            }
        )
        with self._control_operation_lock:
            with self._control_transport_lock:
                previous_epoch = self._control_bridge_epoch
                self._control_bridge_epoch = bridge_epoch
                self._control_status_received = now
                self._control_status = status
            if previous_epoch and previous_epoch != bridge_epoch:
                # A restarted bridge rejects the old epoch.  Revoke any active
                # browser lease and publish a new-epoch StopMove before readying.
                self._set_control_readiness(
                    bridge_ready=False,
                    lowstate_ready=False,
                )
            self._set_control_readiness(
                bridge_ready=bridge_ready,
                lowstate_ready=lowstate_ready,
            )

    def _set_control_readiness(
        self,
        *,
        bridge_ready: bool,
        lowstate_ready: bool,
    ) -> None:
        with self._control_operation_lock:
            try:
                self._control_manager.set_readiness(
                    bridge_ready=bridge_ready,
                    lowstate_ready=lowstate_ready,
                )
            except ControlClosed:
                return
            self._flush_control_outputs()

    def _set_control_unready(self, message: str) -> None:
        with self._control_operation_lock:
            with self._control_transport_lock:
                self._control_status_received = 0.0
                self._control_status = {
                    "state": "error",
                    "ready": False,
                    "connected": False,
                    "available": False,
                    "authenticated": False,
                    "message": str(message)[:240],
                }
            self._set_control_readiness(bridge_ready=False, lowstate_ready=False)

    def _control_tick(self) -> None:
        with self._control_operation_lock:
            now = time.monotonic()
            # Reconcile the autonomous sensor/lease gate before draining any
            # queued drive.  A stale scan/odom/localization sample can therefore
            # only produce a signed StopMove, never one final non-zero command.
            navigation_failure = self._navigation_reconcile_control_locked(now)
            if navigation_failure:
                self.navigation_deactivate(navigation_failure)
            else:
                navigation_failure = self._navigation_keepalive_locked(now)
                if navigation_failure:
                    self.navigation_deactivate(navigation_failure)
            with self._control_transport_lock:
                status_received = self._control_status_received
                stale = (
                    status_received <= 0.0
                    or now - status_received > self._control_status_timeout_s
                )
                if stale and status_received > 0.0:
                    self._control_status = {
                        **self._control_status,
                        "state": "stale",
                        "ready": False,
                        "connected": False,
                        "available": False,
                        "message": "signed Go2 bridge status is stale",
                    }
                    self._control_status_received = 0.0
            if stale:
                self._set_control_readiness(bridge_ready=False, lowstate_ready=False)
            try:
                outputs = self._control_manager.tick()
            except ControlClosed:
                return
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
        """Translate a manager output into the watchdog's narrow contract."""

        kind = output.get("type")
        envelope: Dict[str, Any] = {
            "type": kind,
            "source_id": source_id,
            "seq": sequence,
            "bridge_epoch": bridge_epoch,
        }
        if kind == "drive":
            velocity = output.get("velocity")
            if not isinstance(velocity, dict):
                raise ValueError("drive output has no velocity")
            values = {
                "linear_x": velocity.get("vx"),
                "linear_y": velocity.get("vy"),
                "angular_z": velocity.get("wz"),
            }
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in values.values()
            ):
                raise ValueError("drive output velocity is invalid")
            envelope.update(
                {
                    "deadman": True,
                    **{name: float(value) for name, value in values.items()},
                }
            )
            return envelope
        if kind == "stop":
            envelope["reason"] = str(output.get("reason", "dashboard stop"))[:160]
            return envelope
        if kind == "action":
            action_name = output.get("action")
            if not isinstance(action_name, str) or not action_name:
                raise ValueError("action output has no action name")
            # The standalone bridge deliberately accepts the allowlisted action
            # name, not the numeric API ID supplied by the browser manager.
            envelope["action_id"] = action_name
            return envelope
        raise ValueError("unknown control manager output")

    def _publish_control_outputs(
        self,
        outputs: List[Dict[str, Any]],
        *,
        allow_shutdown: bool = False,
    ) -> None:
        if not outputs:
            return
        with self._control_transport_lock:
            # A timer may have obtained drive outputs immediately before another
            # thread closes the manager.  Once shutdown starts, only the final
            # stop drained by ``shutdown_control`` may cross the transport.
            if self._control_shutdown and not allow_shutdown:
                return
            publisher = self._control_command_publisher
            key = self._control_bridge_key
            bridge_epoch = self._control_bridge_epoch
            if publisher is None or key is None or not bridge_epoch:
                return
            try:
                for output in outputs:
                    self._control_bridge_seq += 1
                    envelope = self._control_bridge_envelope(
                        output,
                        source_id=self._control_source_id,
                        sequence=self._control_bridge_seq,
                        bridge_epoch=bridge_epoch,
                    )
                    message = String()
                    message.data = encode_signed(envelope, key)
                    publisher.publish(message)
            except (ControlProtocolError, TypeError, ValueError) as exc:
                self._control_status = {
                    "state": "error",
                    "ready": False,
                    "connected": False,
                    "available": False,
                    "message": f"control command publish rejected: {exc}",
                }
                try:
                    self._control_manager.set_readiness(
                        bridge_ready=False,
                        lowstate_ready=False,
                    )
                except ControlClosed:
                    pass
            except Exception as exc:
                self._control_status = {
                    "state": "error",
                    "ready": False,
                    "connected": False,
                    "available": False,
                    "message": f"control command transport failed: {exc}",
                }
                try:
                    self._control_manager.set_readiness(
                        bridge_ready=False,
                        lowstate_ready=False,
                    )
                except ControlClosed:
                    pass

    def _flush_control_outputs(self) -> None:
        with self._control_operation_lock:
            self._publish_control_outputs(self._control_manager.drain_outputs())

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
            snapshot = self._control_manager.snapshot()
            self._flush_control_outputs()
            snapshot = self._control_manager.snapshot()
            target_supported = self._go2_control_target()
            target_matches_startup = self._target_matches_startup()
            with self._lock:
                restart_required = self._target_restart_required
            target_reason = self._control_target_reason()
            with self._control_transport_lock:
                bridge = dict(self._control_status)
                received = self._control_status_received
                transport_configured = bool(
                    self._control_bridge_key is not None
                    and self._control_command_publisher is not None
                    and self._control_status_subscription is not None
                    and self._control_timer is not None
                )
        bridge["status_age_s"] = (
            None if received <= 0.0 else round(max(0.0, time.monotonic() - received), 3)
        )
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
        with self._control_operation_lock:
            with self._control_transport_lock:
                if self._control_shutdown:
                    return
                self._control_shutdown = True
                self._control_manager.close()
                # RLock permits the shared publisher path to allocate the final,
                # independent bridge sequence while shutdown owns the transport.
                outputs = self._control_manager.drain_outputs()
                self._publish_control_outputs(outputs, allow_shutdown=True)

    def _refresh_graph(self) -> None:
        node = self._node
        if not node:
            return
        try:
            discovered: Dict[str, Dict[str, Any]] = {}
            for topic, types in node.get_topic_names_and_types():
                if topic.startswith("/_"):
                    continue
                type_name = types[0] if len(types) == 1 else ""
                discovered[topic] = {
                    "name": topic,
                    "types": list(types),
                    "type": type_name,
                    "category": classify_type(type_name) if type_name else "conflict",
                    "publishers": node.count_publishers(topic),
                    "subscribers": node.count_subscribers(topic),
                    "supported": bool(type_name and (is_observable_type(type_name) or classify_type(type_name) in {"camera", "pointcloud", "occupancy_grid", "path"})),
                }
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
        self._pose = {
            "seq": int(self._pose.get("seq", 0)) + 1,
            "topic": topic,
            "type": str(self._graph.get(topic, {}).get("type", "")),
            "pose": None,
            "stamp_ns": 0,
            "updated": 0.0,
        }

    def _reset_cloud_locked(self, topic: str) -> None:
        self._cloud = {
            "seq": int(self._cloud.get("seq", 0)) + 1,
            "points_bytes": b"",
            "sent_points": 0,
            "source_points": 0,
            "frame_id": "",
            "stamp_ns": 0,
            "units": "m",
            "bounds": None,
            "topic": topic,
            "robot_pose_in_frame": None,
            "updated": 0.0,
        }
        self._last_cloud_processed = 0.0

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
        with self._lock:
            self._metrics.setdefault(topic, RateMeter()).tick(now)

    def _summary_callback(self, topic: str, type_name: str, message: Any) -> None:
        now = time.monotonic()
        self._tick(topic, now)
        if type_name == "nav_msgs/msg/Odometry":
            self._update_pose(topic, type_name, message, now)
        self._store_summary(topic, type_name, message, now)

    def _update_pose(self, topic: str, type_name: str, message: Any, now: float) -> None:
        with self._lock:
            if topic != self._sources.get("odometry", ""):
                return
        pose = extract_odometry_pose(
            message,
            type_name,
            position_limit_m=self._pose_position_limit,
        )
        if pose is None:
            return
        with self._lock:
            if topic != self._sources.get("odometry", ""):
                return
            self._pose = {
                "seq": int(self._pose.get("seq", 0)) + 1,
                "topic": topic,
                "type": type_name,
                "pose": pose,
                "stamp_ns": self._stamp_ns(message),
                "updated": now,
            }

    def _store_summary(self, topic: str, type_name: str, message: Any, now: float) -> None:
        with self._lock:
            last = self._summary_updated.get(topic, 0.0)
        if now - last < 0.2:
            return
        try:
            summary = summarize_message(message, type_name)
            with self._lock:
                self._summaries[topic] = {
                    "topic": topic,
                    "type": type_name,
                    "category": classify_type(type_name),
                    "values": summary,
                }
                self._summary_updated[topic] = now
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
        # LowState is commonly 500 Hz.  A 50 Hz model stream is smooth while
        # avoiding needless repeated list construction and lock contention.
        if now - self._joint_last_processed < 0.02:
            return
        self._joint_last_processed = now
        positions = extract_go2_joint_positions(message, type_name)
        if positions is None:
            return
        imu_rpy = extract_go2_imu_rpy(message, type_name)
        source_order = "named_joint_state" if type_name == "sensor_msgs/msg/JointState" else "unitree_lowstate"
        with self._lock:
            if topic != self._special_subscription_topics.get("joints", ""):
                return
            self._joints = {
                "seq": self._joints["seq"] + 1,
                "topic": topic,
                "type": type_name,
                "position_rad": positions,
                "imu_rpy_rad": imu_rpy,
                "source_order": source_order,
                "stamp_ns": self._stamp_ns(message),
                "updated": now,
            }

    def _camera_callback(self, topic: str, type_name: str, message: Any) -> None:
        now = time.monotonic()
        self._tick(topic, now)
        if self._direct_camera.configured:
            # The Go2 profile deliberately uses the factory multicast feed as
            # its sole camera transport.  A manually selected legacy ROS topic
            # remains measurable in the graph but cannot race and overwrite the
            # direct JPEG stream.
            return
        camera: Dict[str, Any]
        if type_name.endswith("/Go2FrontVideoData"):
            payload = bytes(getattr(message, "video720p", b""))
            stamp = int(getattr(message, "time_frame", 0))
            start = self._first_start_code(payload)
            if 0 < start <= 16:
                payload = payload[start:]
            if not payload:
                return
            if self._h264_pending_stamp == 0:
                self._h264_pending_stamp = stamp
                self._h264_pending.extend(payload)
                return
            if stamp == self._h264_pending_stamp:
                self._h264_pending.extend(payload)
                if len(self._h264_pending) > 16 * 1024 * 1024:
                    self._h264_pending.clear()
                    self._h264_pending_stamp = 0
                return
            completed_stamp = self._h264_pending_stamp
            completed = bytes(self._h264_pending)
            self._h264_pending.clear()
            self._h264_pending.extend(payload)
            self._h264_pending_stamp = stamp
            payload, key = self._prepare_h264(completed)
            if self._camera_decoder.feed(payload):
                return
            camera = {
                "format": "h264",
                "data": payload,
                "stamp_us": completed_stamp or int(time.time() * 1_000_000),
                "key": key,
                "width": 1280,
                "height": 720,
                "encoding": "avc1.42E01E",
                "source": "ros_topic",
                "transport": "ros2",
                "state": "ok",
            }
        elif type_name == "sensor_msgs/msg/CompressedImage":
            fmt = str(getattr(message, "format", "jpeg")).lower()
            camera = {
                "format": "jpeg" if "jpeg" in fmt or "jpg" in fmt else "png",
                "data": bytes(getattr(message, "data", b"")),
                "stamp_us": int(time.time() * 1_000_000),
                "key": True,
                "width": 0,
                "height": 0,
                "encoding": fmt,
                "source": "ros_topic",
                "transport": "ros2",
                "state": "ok",
            }
        else:
            camera = {
                "format": "raw",
                "data": bytes(getattr(message, "data", b"")),
                "stamp_us": int(time.time() * 1_000_000),
                "key": True,
                "width": int(getattr(message, "width", 0)),
                "height": int(getattr(message, "height", 0)),
                "step": int(getattr(message, "step", 0)),
                "encoding": str(getattr(message, "encoding", "")),
                "source": "ros_topic",
                "transport": "ros2",
                "state": "ok",
            }
        if not camera["data"]:
            return
        with self._lock:
            camera["seq"] = self._camera["seq"] + 1
            camera["topic"] = topic
            camera["updated"] = now
            self._camera = camera

    def _decoded_camera_callback(self, jpeg: bytes) -> None:
        if self._direct_camera.configured:
            return
        now = time.monotonic()
        with self._lock:
            self._camera = {
                "format": "jpeg",
                "data": jpeg,
                "stamp_us": int(time.time() * 1_000_000),
                "key": True,
                "width": 640,
                "height": 360,
                "encoding": "jpeg",
                "seq": self._camera["seq"] + 1,
                "topic": self._sources.get("camera", "/frontvideostream"),
                "updated": now,
                "decoder": "gstreamer",
                "source": "ros_topic",
                "transport": "ros2",
                "state": "ok",
            }

    def _direct_camera_callback(self, jpeg: bytes) -> None:
        """Store one JPEG decoded from the Go2's non-ROS RTP multicast."""

        now = time.monotonic()
        status = self._direct_camera.status()
        with self._lock:
            self._camera = {
                "format": "jpeg",
                "data": jpeg,
                "stamp_us": int(time.time() * 1_000_000),
                "key": True,
                "width": int(status.get("width", 1280)),
                "height": int(status.get("height", 720)),
                "encoding": "jpeg",
                "seq": int(self._camera.get("seq", 0)) + 1,
                "topic": str(status.get("uri", "go2-camera://230.1.1.1:1720")),
                "source": "go2_multicast",
                "source_id": "go2_front",
                "source_label": str(status.get("source_label", "Go2 front camera")),
                "transport": str(status.get("transport", "udp_multicast_rtp_h264")),
                "interface": str(status.get("interface", "")),
                "fps": status.get("fps"),
                "age_s": status.get("age_s"),
                "state": "ok",
                "updated": now,
                "decoder": "gstreamer",
            }

    def _remote_camera_callback(self, jpeg: bytes) -> None:
        """Store a RealSense JPEG independently from the Go2 front stream."""

        now = time.monotonic()
        status = self._remote_camera.status()
        with self._lock:
            self._remote_camera_frame = {
                "format": "jpeg",
                "data": jpeg,
                "stamp_us": int(time.time() * 1_000_000),
                "key": True,
                "width": 0,
                "height": 0,
                "encoding": "jpeg",
                "seq": int(self._remote_camera_frame.get("seq", 0)) + 1,
                "topic": str(status.get("uri", "")),
                "source": "remote_mjpeg",
                "source_id": "realsense_color",
                "source_label": str(
                    status.get("source_label", "RealSense color camera")
                ),
                "transport": "http_mjpeg",
                "fps": status.get("fps"),
                "age_s": status.get("age_s"),
                "state": "ok",
                "updated": now,
                "decoder": "upstream_jpeg",
            }

    @staticmethod
    def _first_start_code(payload: bytes) -> int:
        indexes = [index for index in (payload.find(b"\x00\x00\x00\x01"), payload.find(b"\x00\x00\x01")) if index >= 0]
        return min(indexes) if indexes else -1

    @staticmethod
    def _nal_units(payload: bytes) -> List[Tuple[int, int, int]]:
        starts: List[Tuple[int, int]] = []
        index = 0
        while index < len(payload) - 3:
            if payload[index : index + 4] == b"\x00\x00\x00\x01":
                starts.append((index, 4))
                index += 4
            elif payload[index : index + 3] == b"\x00\x00\x01":
                starts.append((index, 3))
                index += 3
            else:
                index += 1
        units: List[Tuple[int, int, int]] = []
        for pos, (start, prefix) in enumerate(starts):
            end = starts[pos + 1][0] if pos + 1 < len(starts) else len(payload)
            header = start + prefix
            if header < end:
                units.append((payload[header] & 0x1F, start, end))
        return units

    def _prepare_h264(self, payload: bytes) -> Tuple[bytes, bool]:
        units = self._nal_units(payload)
        if units:
            payload = payload[units[0][1] :]
            units = self._nal_units(payload)
        present = {unit_type for unit_type, _, _ in units}
        for unit_type, start, end in units:
            if unit_type == 7:
                self._h264_sps = payload[start:end]
            elif unit_type == 8:
                self._h264_pps = payload[start:end]
        key = 5 in present
        if key:
            prefix = b""
            if 7 not in present:
                prefix += self._h264_sps
            if 8 not in present:
                prefix += self._h264_pps
            payload = prefix + payload
        return payload, key

    def _pointcloud_callback(self, topic: str, type_name: str, message: Any) -> None:
        now = time.monotonic()
        with self._lock:
            if topic != self._sources.get("pointcloud", ""):
                return
            point_limit = self.cloud_max_points
            frame_interval = self._pointcloud_frame_interval(point_limit)
        self._tick(topic, now)
        if now - self._last_cloud_processed < frame_interval:
            return
        self._last_cloud_processed = now
        try:
            # "ALL SESSION" is a browser-side reservoir.  A single ROS frame
            # remains capped at one million samples so one malformed or very
            # large /Laser_map message cannot create an unbounded WS payload.
            extraction_limit = self.MAX_CUSTOM_CLOUD_POINTS if point_limit is None else point_limit
            array, source_points = extract_xyz(message, extraction_limit)
            array = reject_spatial_outliers(array, self.cloud_radius_limit)
            if not len(array):
                return
            mins = [float(value) for value in np.min(array, axis=0)]
            maxs = [float(value) for value in np.max(array, axis=0)]
            packed_points = np.ascontiguousarray(array, dtype="<f4").reshape(-1).tobytes()
            with self._lock:
                if topic != self._sources.get("pointcloud", ""):
                    return
                self._cloud = {
                    "seq": self._cloud["seq"] + 1,
                    "points_bytes": packed_points,
                    "sent_points": int(array.shape[0]),
                    "source_points": source_points,
                    "frame_id": str(getattr(getattr(message, "header", None), "frame_id", "")),
                    "stamp_ns": self._stamp_ns(message),
                    "units": "m",
                    "bounds": {"min": mins, "max": maxs},
                    "topic": topic,
                    "robot_pose_in_frame": self._robot_pose_in_cloud_frame(
                        str(getattr(getattr(message, "header", None), "frame_id", ""))
                    ),
                    "updated": now,
                }
        except Exception as exc:
            with self._lock:
                self._last_error = f"pointcloud {topic}: {exc}"

    def _map_callback(self, topic: str, type_name: str, message: Any) -> None:
        now = time.monotonic()
        self._tick(topic, now)
        try:
            info = message.info
            width = int(info.width)
            height = int(info.height)
            cells = width * height
            if width <= 0 or height <= 0 or cells > 16_000_000 or len(message.data) != cells:
                raise ValueError(f"invalid OccupancyGrid dimensions/data: {width}x{height}, {len(message.data)} cells")
            origin = info.origin.position
            orientation = info.origin.orientation
            yaw = math.atan2(
                2.0 * (orientation.w * orientation.z + orientation.x * orientation.y),
                1.0 - 2.0 * (orientation.y * orientation.y + orientation.z * orientation.z),
            )
            raw = bytes((int(value) & 0xFF for value in message.data))
            with self._lock:
                self._map = {
                    "seq": self._map["seq"] + 1,
                    "width": width,
                    "height": height,
                    "resolution": float(info.resolution),
                    "origin": [float(origin.x), float(origin.y), float(yaw)],
                    "origin_pose": {
                        "position": {"x": float(origin.x), "y": float(origin.y), "z": float(origin.z)},
                        "orientation": {
                            "x": float(orientation.x), "y": float(orientation.y),
                            "z": float(orientation.z), "w": float(orientation.w),
                        },
                        "yaw": float(yaw),
                    },
                    "frame_id": str(message.header.frame_id),
                    "stamp_ns": self._stamp_ns(message),
                    "data_b64": base64.b64encode(raw).decode("ascii"),
                    "data_encoding": "int8-base64",
                    "cell_order": "row-major; cell(0,0) at origin",
                    "topic": topic,
                    "updated": now,
                }
        except Exception as exc:
            with self._lock:
                self._last_error = f"map {topic}: {exc}"

    def set_sources(self, values: Dict[str, str]) -> Dict[str, Any]:
        with self._lock:
            requested = dict(self._requested_sources)
            origins = dict(self._source_selection_origins)
            pins = set(self._source_pins)
            overrides = copy.deepcopy(self._source_selection_overrides)
            for category in self._requested_sources:
                candidate = values.get(category)
                if candidate is None:
                    continue
                if category == "camera" and self._direct_camera.configured:
                    if candidate == self._direct_camera.source_uri:
                        continue
                    raise ValueError(
                        "Go2 direct camera is active; ROS camera selection is locked"
                    )
                policy = self._source_selection_policies.get(category)
                item = self._graph.get(candidate) if candidate else None
                allowed_offline = bool(
                    candidate
                    and policy
                    and candidate in policy["allowed_offline"]
                )
                if candidate and item is None and not allowed_offline:
                    raise ValueError(f"unknown ROS topic: {candidate}")
                if candidate and item is not None and item.get("category") != category:
                    raise ValueError(f"{candidate} is not a {category} topic")
                if (
                    candidate
                    and policy
                    and policy["persistent"]
                    and policy["fail_closed"]
                    and candidate not in policy["allowed_offline"]
                ):
                    raise ValueError(
                        f"{candidate} is not allowed for persistent {category} selection"
                    )

                if not policy:
                    requested[category] = candidate
                    origins[category] = "user" if candidate else "auto"
                    pins.discard(category)
                    continue

                if candidate:
                    requested[category] = candidate
                    origins[category] = "user"
                    if policy["fail_closed"]:
                        pins.add(category)
                    else:
                        pins.discard(category)
                    if policy["persistent"]:
                        overrides[category] = {
                            "mode": "pinned",
                            "topic": candidate,
                        }
                else:
                    # Empty means "remove my override".  A configured default
                    # is then restored; it is deliberately not an AUTO escape
                    # hatch from a profile's fail-closed sensor policy.
                    overrides.pop(category, None)
                    default = str(policy.get("default", ""))
                    requested[category] = default
                    origins[category] = "profile_default" if default else "auto"
                    if default and policy["fail_closed"]:
                        pins.add(category)
                    else:
                        pins.discard(category)

            if overrides != self._source_selection_overrides:
                self._write_source_selection_overrides(overrides)
            self._source_selection_overrides = overrides
            self._requested_sources = requested
            self._source_selection_origins = origins
            self._source_pins = pins
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

        try:
            self._control_manager.emergency_stop("robot_target_changed")
        except ControlClosed:
            pass
        self._flush_control_outputs()

    def robot_target_snapshot(self) -> Dict[str, Any]:
        with self._lock:
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
                },
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
                # Generic/TurtleBot/SO-101 profiles have no Go2 motion
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
        direct_camera = self._direct_camera.status()
        with self._lock:
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
                "last_error": self._last_error,
                "direct_camera": direct_camera,
                # `profile` always names the actually running ROS profile.
                # Runtime selection is display/observation metadata only.
                "profile": self._startup_profile_name,
                "runtime_profile": {
                    "id": self._startup_robot_type,
                    "label": self._startup_profile_name,
                },
                "selected_profile": {
                    "id": self._robot_type,
                    "label": runtime_profile["label"] if runtime_profile else "Unselected",
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
        now = time.monotonic()
        meter = self._metrics.get(topic)
        hz = meter.hz() if meter else None
        age = round(now - meter.last, 3) if meter and meter.last is not None else None
        # Some robot DDS bridges deliver otherwise high-rate topics in short bursts.
        # Keep the UI from reporting a false disconnect between those bursts.
        threshold = 3.0 if category in {"imu", "robot_state", "odometry"} else 5.0
        if not meter or meter.last is None:
            state = "waiting"
        elif category == "occupancy_grid":
            # Static map servers commonly publish once with TRANSIENT_LOCAL
            # durability.  An old sample is still the current valid map.
            state = "ok"
        elif age is not None and age > threshold:
            state = "stale"
        else:
            state = "ok"
        return {
            "hz": hz,
            "jitter_ms": meter.jitter_ms() if meter else None,
            "age_s": age,
            "samples": meter.samples if meter else 0,
            "state": state,
        }

    def topics_snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            result: List[Dict[str, Any]] = []
            selected = set(self._sources.values())
            for topic, item in self._graph.items():
                row = dict(item)
                row.update(self._metric_snapshot(topic, item.get("category", "")))
                row["selected"] = topic in selected
                result.append(row)
            return sorted(result, key=lambda row: (row["category"], row["name"]))

    def _joint_snapshot_locked(self, now: float) -> Dict[str, Any]:
        joint_data = dict(self._joints)
        return go2_joint_state_payload(
            topic=str(joint_data.get("topic", "")),
            type_name=str(joint_data.get("type", "")),
            positions=joint_data.get("position_rad"),
            updated_at=float(joint_data.get("updated", 0.0)),
            now=now,
            stale_after_s=self._joint_stale_after,
            seq=int(joint_data.get("seq", 0)),
            stamp_ns=int(joint_data.get("stamp_ns", 0)),
            source_order=str(joint_data.get("source_order", "")),
            imu_rpy_rad=joint_data.get("imu_rpy_rad"),
        )

    def joint_snapshot(self) -> Dict[str, Any]:
        """Return the small joint-only snapshot for a high-rate API/WS route."""

        with self._lock:
            return self._joint_snapshot_locked(time.monotonic())

    def _pose_snapshot_locked(self, now: float) -> Dict[str, Any]:
        pose_data = dict(self._pose)
        return odometry_pose_payload(
            topic=str(pose_data.get("topic", "")),
            type_name=str(pose_data.get("type", "")),
            pose=pose_data.get("pose"),
            updated_at=float(pose_data.get("updated", 0.0)),
            now=now,
            stale_after_s=self._pose_stale_after,
            seq=int(pose_data.get("seq", 0)),
            stamp_ns=int(pose_data.get("stamp_ns", 0)),
        )

    def pose_snapshot(self) -> Dict[str, Any]:
        """Return the selected world pose without the large state payload."""

        with self._lock:
            return self._pose_snapshot_locked(time.monotonic())

    def _camera_snapshot_locked(self) -> Dict[str, Any]:
        snapshot = dict(self._camera)
        snapshot["stream_id"] = self._camera_stream_ids["go2_front"]
        snapshot["source_id"] = "go2_front"
        direct_status = self._direct_camera.status()
        snapshot["direct_camera"] = direct_status
        direct_active = bool(
            direct_status.get("enabled") and direct_status.get("configured")
        )
        if direct_active:
            snapshot.update(
                {
                    "topic": direct_status.get("uri", "go2-camera://230.1.1.1:1720"),
                    "source": direct_status.get("source", "go2_multicast"),
                    "source_label": direct_status.get("source_label", "Go2 front camera"),
                    "transport": direct_status.get("transport", "udp_multicast_rtp_h264"),
                    "interface": direct_status.get("interface", ""),
                    "state": direct_status.get("state", "waiting"),
                    "fps": direct_status.get("fps"),
                    "age_s": direct_status.get("age_s"),
                }
            )
        else:
            updated = float(snapshot.get("updated", 0.0) or 0.0)
            snapshot["age_s"] = (
                round(max(0.0, time.monotonic() - updated), 3) if updated else None
            )
            if snapshot.get("state") == "ok" and (
                snapshot["age_s"] is None or snapshot["age_s"] > 2.0
            ):
                snapshot["state"] = "stale"
        return snapshot

    def _remote_camera_snapshot_locked(self) -> Dict[str, Any]:
        snapshot = dict(self._remote_camera_frame)
        status = self._remote_camera.status()
        snapshot.update(
            {
                "stream_id": self._camera_stream_ids["realsense_color"],
                "source_id": "realsense_color",
                "topic": status.get("uri", ""),
                "source": status.get("source", "remote_mjpeg"),
                "source_label": status.get(
                    "source_label", "RealSense color camera"
                ),
                "transport": status.get("transport", "http_mjpeg"),
                "state": status.get("state", "waiting"),
                "fps": status.get("fps"),
                "age_s": status.get("age_s"),
            }
        )
        return snapshot

    def cameras_snapshot(self) -> Dict[str, Any]:
        """Return the fixed camera catalog without exposing demand tokens."""

        with self._camera_demand_lock:
            viewers = {
                source_id: len(tokens)
                for source_id, tokens in self._camera_demand_tokens.items()
            }
            total_viewers = len(self._camera_token_sources)
        direct_status = self._direct_camera.status()
        remote_status = self._remote_camera.status()
        entries = []
        for source_id, label, status in (
            ("go2_front", "Go2 front camera", direct_status),
            ("realsense_color", "RealSense color camera", remote_status),
        ):
            entry = {
                "id": source_id,
                "source_id": source_id,
                "label": str(status.get("source_label", label)),
                "enabled": bool(status.get("enabled", False)),
                "configured": bool(status.get("configured", False)),
                "available": bool(status.get("available", False)),
                "state": str(status.get("state", "disabled")),
                "live": bool(status.get("live", False)),
                "format": "jpeg",
                "encoding": "jpeg",
                "transport": str(status.get("transport", "")),
                "topic": str(status.get("uri", "")),
                "uri": str(status.get("uri", "")),
                "width": int(status.get("width", 0) or 0),
                "height": int(status.get("height", 0) or 0),
                "stream_id": self._camera_stream_ids[source_id],
                "viewers": viewers[source_id],
                "max_viewers": MAX_CAMERA_VIEWERS_PER_SOURCE,
                "fps": status.get("fps"),
                "age_s": status.get("age_s"),
                "last_error": str(status.get("last_error", "")),
            }
            entries.append(entry)
        return {
            "sources": entries,
            "max_active": MAX_ACTIVE_CAMERA_SOURCES,
            "max_viewers": MAX_CAMERA_VIEWERS,
            "active_sources": sum(1 for value in viewers.values() if value),
            "viewers": total_viewers,
        }

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

        if (
            not isinstance(source_ids, tuple)
            or not source_ids
            or len(source_ids) > len(CAMERA_SOURCE_IDS)
            or len(set(source_ids)) != len(source_ids)
            or any(not self._valid_camera_source_id(source_id) for source_id in source_ids)
        ):
            raise ValueError("camera sources are not allowlisted")
        with self._lock:
            return {
                source_id: (
                    self._camera_snapshot_locked()
                    if source_id == "go2_front"
                    else self._remote_camera_snapshot_locked()
                )
                for source_id in source_ids
            }

    def pointcloud_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            snapshot = {
                key: value for key, value in self._cloud.items() if key != "points_bytes"
            }
            point_bytes = self._cloud.get("points_bytes", b"")
            snapshot["stream_id"] = self._cloud_stream_id
        snapshot["points"] = np.frombuffer(point_bytes, dtype="<f4").tolist()
        return snapshot

    def pointcloud_binary_snapshot(self) -> Dict[str, Any]:
        """Return immutable packed points plus small JSON-safe metadata."""

        with self._lock:
            snapshot = dict(self._cloud)
            snapshot["stream_id"] = self._cloud_stream_id
            return snapshot

    def map_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._map)
