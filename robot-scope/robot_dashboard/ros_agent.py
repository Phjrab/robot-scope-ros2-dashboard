"""ROS 2 runtime used by the Robot Scope web agent."""

from __future__ import annotations

import base64
import ipaddress
import json
import math
import os
import platform
import socket
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rosidl_runtime_py.utilities import get_message

from .camera_decoder import H264JpegDecoder
from .pointcloud import extract_xyz, reject_spatial_outliers
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
    """A single-process, read-only bridge between ROS 2 and the web API."""

    def __init__(
        self,
        robot_ip: str = "",
        profile_path: Optional[str] = None,
        cloud_max_points: int = 18000,
    ) -> None:
        self.robot_ip = self._valid_ip(robot_ip)
        self.cloud_max_points = max(1000, min(int(cloud_max_points), 50000))
        self.profile = self._load_profile(profile_path)
        self.cloud_radius_limit = max(
            5.0,
            min(float(self.profile.get("cloud_radius_limit_m", 500.0)), 10_000.0),
        )

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._node: Optional[Node] = None
        self._executor: Optional[MultiThreadedExecutor] = None
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
        }
        self._h264_sps = b""
        self._h264_pps = b""
        self._h264_pending_stamp = 0
        self._h264_pending = bytearray()
        self._camera_decoder = H264JpegDecoder(self._decoded_camera_callback)

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
    def _valid_ip(value: str) -> str:
        if not value:
            return ""
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            return ""

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
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="robot-scope-ros", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
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
            executor = MultiThreadedExecutor(num_threads=2)
            executor.add_node(node)
            self._node = node
            self._executor = executor
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

        candidates = [
            (topic, descriptor.get("type", ""))
            for topic, descriptor in self._graph.items()
            if descriptor.get("publishers", 0) > 0
            and (
                descriptor.get("type") == "sensor_msgs/msg/JointState"
                or str(descriptor.get("type", "")).casefold().endswith("/lowstate")
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
            }
        if not camera["data"]:
            return
        with self._lock:
            camera["seq"] = self._camera["seq"] + 1
            camera["topic"] = topic
            camera["updated"] = now
            self._camera = camera

    def _decoded_camera_callback(self, jpeg: bytes) -> None:
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
        self._tick(topic, now)
        if now - self._last_cloud_processed < 0.35:
            return
        self._last_cloud_processed = now
        try:
            array, source_points = extract_xyz(message, self.cloud_max_points)
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

    def set_robot_ip(self, value: str) -> str:
        valid = self._valid_ip(value)
        if not valid:
            raise ValueError("유효한 IPv4 또는 IPv6 주소가 아닙니다.")
        self.robot_ip = valid
        self._network_cache = (0.0, False, None)
        return valid

    def _network_status(self) -> Tuple[bool, Optional[float]]:
        cached_at, online, latency = self._network_cache
        now = time.monotonic()
        if now - cached_at < 3.0:
            return online, latency
        if not self.robot_ip:
            return False, None
        started = time.monotonic()
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "1", self.robot_ip],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
            )
            online = result.returncode == 0
            latency = round((time.monotonic() - started) * 1000.0, 1) if online else None
        except (OSError, subprocess.TimeoutExpired):
            online, latency = False, None
        self._network_cache = (now, online, latency)
        return online, latency

    def health_snapshot(self) -> Dict[str, Any]:
        online, latency = self._network_status()
        with self._lock:
            return {
                "agent_ready": self._ready,
                "agent_version": "0.1.0",
                "hostname": socket.gethostname(),
                "platform": platform.machine(),
                "ros_distro": os.environ.get("ROS_DISTRO", "unknown"),
                "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", "0"),
                "rmw": os.environ.get("RMW_IMPLEMENTATION", "default"),
                "robot_ip": self.robot_ip,
                "robot_online": online,
                "robot_latency_ms": latency,
                "uptime_s": round(time.monotonic() - self._started_at, 1),
                "topic_count": len(self._graph),
                "last_error": self._last_error,
                "profile": self.profile.get("name", "Generic ROS 2"),
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
            return {"selected": dict(self._sources), "options": options}

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

    def state_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            sensors = []
            for topic, summary in self._summaries.items():
                item = dict(summary)
                item.update(self._metric_snapshot(topic, summary.get("category", "")))
                sensors.append(item)
            sources = dict(self._sources)
            camera_meta = {key: value for key, value in self._camera.items() if key != "data"}
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
            return dict(self._camera)

    def pointcloud_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._cloud)

    def map_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._map)
