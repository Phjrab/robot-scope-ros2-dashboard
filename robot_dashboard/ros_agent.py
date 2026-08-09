"""ROS 2 runtime used by the Robot Scope web agent."""

from __future__ import annotations

import base64
import copy
import ipaddress
import json
import math
import os
import platform
import secrets
import socket
import subprocess
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
from .control import ControlClosed, ControlDisabled, ControlManager
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

CONTROL_COMMAND_TOPIC = "/robot_scope/control/command"
CONTROL_STATUS_TOPIC = "/robot_scope/control/status"


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
        self._target_restart_required = False
        self._robot_hostname = ""
        self._robot_model = (
            robot_type_definition(self._robot_type)["model"] if self._robot_type else None
        )
        self.cloud_radius_limit = max(
            5.0,
            min(float(self.profile.get("cloud_radius_limit_m", 500.0)), 10_000.0),
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

        self._cloud: Dict[str, Any] = {
            "seq": 0,
            "points": [],
            "source_points": 0,
            "frame_id": "",
            "bounds": None,
            "updated": 0.0,
        }
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
        }

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

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._direct_camera.start()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="robot-scope-ros", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        # Publish the manager's final signed stop while the ROS node and
        # executor are still alive.  The standalone bridge has its own watchdog
        # as a second line of defence if transport is already unavailable.
        self.shutdown_control()
        self._stop_event.set()
        self._direct_camera.stop()
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
            executor = MultiThreadedExecutor(num_threads=3)
            executor.add_node(node)
            self._node = node
            self._executor = executor
            self._setup_control_transport(node)
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

    @staticmethod
    def _control_status_readiness(
        payload: Dict[str, Any],
        *,
        lowstate_timeout_s: float,
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
        bridge_ready = reported_ready and subscribers == 1 and publishers == 1
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
                self._robot_type == self._startup_robot_type
                and self.robot_ip == self._startup_robot_ip
            )

    def _go2_control_target(self) -> bool:
        with self._lock:
            return (
                self._startup_robot_type == "go2"
                and bool(self._startup_robot_ip)
                and self._robot_type == "go2"
                and self.robot_ip == self._startup_robot_ip
                and not self._target_restart_required
            )

    def _control_target_reason(self) -> str:
        with self._lock:
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

    def control_acquire(self, pin: str, input_source: str) -> Dict[str, Any]:
        with self._control_operation_lock:
            try:
                self._ensure_go2_control_target()
                return self._control_manager.acquire_lease(pin, input_source)
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

    def control_clear_estop(
        self,
        pin: str,
        *,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        with self._control_operation_lock:
            try:
                self._ensure_go2_control_target()
                return self._control_manager.clear_emergency_stop(pin, confirm=confirm)
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
            if category in disabled and not requested:
                chosen = ""
            else:
                candidates = [
                    name
                    for name, item in self._graph.items()
                    if item.get("category") == category and item.get("publishers", 0) > 0
                ]
                ordered = list(preferences.get(category, []))
                # A user choice is sticky while it is live.  If its publisher
                # disappears we temporarily fail over, then restore it when it
                # returns.  Automatic choices are never copied into the manual
                # override, so a newly available world-frame mapping topic can
                # supersede a raw LiDAR topic on the next graph refresh.
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
            "points": [],
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
                "source_label": str(status.get("source_label", "Go2 front camera")),
                "transport": str(status.get("transport", "udp_multicast_rtp_h264")),
                "interface": str(status.get("interface", "")),
                "fps": status.get("fps"),
                "age_s": status.get("age_s"),
                "state": "ok",
                "updated": now,
                "decoder": "gstreamer",
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
        self._tick(topic, now)
        if now - self._last_cloud_processed < 0.35:
            return
        self._last_cloud_processed = now
        try:
            array, source_points = extract_xyz(message, point_limit)
            array = reject_spatial_outliers(array, self.cloud_radius_limit)
            if not len(array):
                return
            mins = [float(value) for value in np.min(array, axis=0)]
            maxs = [float(value) for value in np.max(array, axis=0)]
            with self._lock:
                if topic != self._sources.get("pointcloud", ""):
                    return
                self._cloud = {
                    "seq": self._cloud["seq"] + 1,
                    "points": array.reshape(-1).tolist(),
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

    def set_sources(self, values: Dict[str, str]) -> Dict[str, str]:
        with self._lock:
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
                if candidate and candidate not in self._graph:
                    raise ValueError(f"unknown ROS topic: {candidate}")
                if candidate and self._graph[candidate].get("category") != category:
                    raise ValueError(f"{candidate} is not a {category} topic")
                previous = self._sources.get(category, "")
                self._requested_sources[category] = candidate
                self._sources[category] = candidate
                if candidate != previous:
                    if category == "odometry":
                        self._reset_pose_locked(candidate)
                    elif category == "pointcloud":
                        self._reset_cloud_locked(candidate)
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
                self._robot_type == self._startup_robot_type
                and self.robot_ip == self._startup_robot_ip
            )
            return {
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
                changed = valid != self.robot_ip or definition["id"] != self._robot_type
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
                self._network_cache = (0.0, False, None)
        return valid

    def _network_status(self) -> Tuple[bool, Optional[float]]:
        now = time.monotonic()
        with self._lock:
            cached_at, online, latency = self._network_cache
            target_ip = self.robot_ip
        if now - cached_at < 3.0:
            return online, latency
        if not target_ip:
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
                self._robot_type == self._startup_robot_type
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

    def sources_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            options: Dict[str, List[Dict[str, str]]] = {key: [] for key in self._sources}
            for name, item in self._graph.items():
                category = item.get("category")
                if category in options and item.get("publishers", 0) > 0:
                    options[category].append({"topic": name, "type": item.get("type", "")})
            for values in options.values():
                values.sort(key=lambda item: item["topic"])
            selected = dict(self._sources)
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
            return {
                "selected": selected,
                "options": options,
                "locked": locked,
                "direct_camera": direct_camera,
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
        return snapshot

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
            cloud_meta = {key: value for key, value in self._cloud.items() if key != "points"}
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

    def camera_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self._camera_snapshot_locked()

    def pointcloud_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._cloud)

    def map_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._map)
