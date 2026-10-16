"""Opt-in, local Isaac ROS 3.2 stereo SLAM runtime.

Importing this module never imports ROS or starts a process.  The administrator
must supply observed contracts and a recently checked isolated domain.  Camera
handoff/locking belongs to the application owner which calls this adapter.
"""

from __future__ import annotations

import base64
from collections import deque
import copy
import datetime as dt
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import runpy
import shutil
import signal
import stat
import struct
import subprocess
import threading
import time
from typing import Any, Callable
import xml.etree.ElementTree as ET
import zlib

from .slam_features import FeatureStream, FeatureValidationError, StreamContext
from .slam_managed_scope import (DomainReservation, ManagedScopeError, load_managed_scope,
                                 validate_reservation_proof)
from .slam_native_diagnostics import (NativeLogDiagnostics, digest, opaque_native_identity,
                                      persist_attempt)


MAP_FRAME = "vslam_lab_map"
SLAM_ROOT = "/vslam_lab/visual_slam"
CORRECTED_POSE_TOPIC = SLAM_ROOT + "/vis/slam_odometry"
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_MAP_POINTS = 32768
MAX_OBSERVATIONS = 2048
MAX_PATH_POSES = 1024
STEREO_HISTORY_SIZE = 16
MAX_IMAGE_HISTORY_BYTES = 16 * 1024 * 1024
EXPECTED_PARAMETERS = {
    "enable_imu_fusion": False,
    "enable_localization_n_mapping": True,
    "enable_slam_visualization": True,
    "enable_landmarks_view": True,
    "enable_observations_view": True,
    "publish_map_to_odom_tf": False,
    "publish_odom_to_base_tf": False,
    "use_sim_time": False,
}


class IsaacRuntimeError(RuntimeError):
    """One bounded runtime operation failed; no operational pose is applied."""


def _stamp(message: Any) -> int:
    stamp = message.header.stamp
    seconds, nanoseconds = int(stamp.sec), int(stamp.nanosec)
    if seconds < 0 or not 0 <= nanoseconds < 1_000_000_000:
        raise IsaacRuntimeError("SLAM source stamp is invalid")
    return seconds * 1_000_000_000 + nanoseconds


def _pose(value: Any) -> dict[str, Any]:
    pose = value.pose.pose if hasattr(value.pose, "pose") else value.pose
    numbers = [float(getattr(pose.position, key)) for key in ("x", "y", "z")]
    quaternion = [float(getattr(pose.orientation, key)) for key in ("x", "y", "z", "w")]
    if not all(math.isfinite(item) for item in numbers + quaternion):
        raise IsaacRuntimeError("SLAM pose contains nonfinite coordinates")
    if abs(sum(item * item for item in quaternion) - 1.0) > 0.02:
        raise IsaacRuntimeError("SLAM pose quaternion is invalid")
    return {"position": numbers, "quaternion_xyzw": quaternion,
            "frame_id": str(value.header.frame_id), "stamp_ns": _stamp(value)}


def compose_optical_pose(pose: dict[str, Any], transform: Any) -> tuple[list[float], list[float]]:
    """Compose observed map_T_base with TF's base_T_rectified_optical."""
    q = pose["quaternion_xyzw"]
    t = transform.transform.translation
    r = transform.transform.rotation
    b = [float(r.x), float(r.y), float(r.z), float(r.w)]
    offset = [float(t.x), float(t.y), float(t.z)]
    if not all(math.isfinite(value) for value in b + offset) or abs(sum(value * value for value in b) - 1) > 0.02:
        raise IsaacRuntimeError("observed camera optical transform is invalid")
    def multiply(a, c):
        x, y, z, w = a
        u, v, s, n = c
        return [w*u+x*n+y*s-z*v, w*v-x*s+y*n+z*u,
                w*s+x*v-y*u+z*n, w*n-x*u-y*v-z*s]
    rotated = multiply(multiply(q, offset + [0.0]), [-q[0], -q[1], -q[2], q[3]])
    return [pose["position"][i] + rotated[i] for i in range(3)], multiply(q, b)


def decode_cloud(message: Any, limit: int) -> list[list[float]]:
    """Read bounded real XYZ fields with ROS row padding and endianness."""
    width, height, point_step, row_step = (
        int(message.width), int(message.height), int(message.point_step), int(message.row_step)
    )
    if width < 0 or height < 0 or width * height > limit:
        raise IsaacRuntimeError("Isaac visualization cloud exceeds its source limit")
    if not 12 <= point_step <= 256 or row_step < width * point_step:
        raise IsaacRuntimeError("Isaac visualization cloud layout is invalid")
    data = bytes(message.data)
    if len(data) != height * row_step or len(data) > limit * 256:
        raise IsaacRuntimeError("Isaac visualization cloud byte count is invalid")
    fields = {str(field.name): field for field in message.fields}
    offsets = []
    for key in ("x", "y", "z"):
        field = fields.get(key)
        if field is None or int(field.datatype) != 7 or int(field.count) != 1:
            raise IsaacRuntimeError("Isaac visualization requires FLOAT32 XYZ fields")
        offset = int(field.offset)
        if offset < 0 or offset + 4 > point_step:
            raise IsaacRuntimeError("Isaac visualization field offset is invalid")
        offsets.append(offset)
    prefix = ">" if message.is_bigendian else "<"
    result = []
    for row in range(height):
        for col in range(width):
            index = row * row_step + col * point_step
            xyz = [struct.unpack_from(prefix + "f", data, index + offset)[0] for offset in offsets]
            if all(math.isfinite(value) for value in xyz):
                result.append(xyz)
    return result


def _private_json(path: Path) -> dict[str, Any]:
    if not path.is_absolute() or path.is_symlink():
        raise IsaacRuntimeError("runtime configuration must be an absolute regular file")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 256 * 1024:
        raise IsaacRuntimeError("runtime configuration file is invalid")
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise IsaacRuntimeError("runtime configuration must be private and owned by this user")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise IsaacRuntimeError("runtime configuration must be an object")
    return value


def encode_png(image: dict[str, Any]) -> bytes:
    """Lossless standard-library fallback for actual bounded stereo pixels."""
    channels = {"mono8": 1, "rgb8": 3}.get(image["encoding"])
    if channels is None:
        raise IsaacRuntimeError("stereo preview encoding is unsupported")
    width, height, step = image["width"], image["height"], image["step"]
    count = width * channels
    if step < count or len(image["data"]) != step * height:
        raise IsaacRuntimeError("stereo preview row layout is invalid")
    scanlines = b"".join(b"\0" + image["data"][row*step:row*step+count] for row in range(height))
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name+data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0 if channels == 1 else 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(scanlines, 1)) + chunk(b"IEND", b""))


class IsaacStereoAdapter:
    """Synchronous adapter used by the SLAM application coordinator.

    The local process uses the preserved installed ROS environment.  This class
    never installs packages, launches Docker, changes systemd, or publishes TF.
    """

    engine_id = "visual_stereo"

    def __init__(self, project_dir: Path, runtime_root: Path, *, enabled: bool = False,
                 config_path: Path | None = None,
                 confirmation_clock: Callable[[], float] = time.monotonic,
                 confirmation_wait: Callable[[float], None] = time.sleep) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.runtime_root = Path(runtime_root).resolve()
        self.enabled = enabled
        self.config_path = config_path
        self._lock = threading.RLock()
        self._job: dict[str, Any] | None = None
        self._last_compatibility: dict[str, Any] = {}
        self._confirmation_clock = confirmation_clock
        self._confirmation_wait = confirmation_wait
        self._camera_coordinator: Any = None

    def bind_camera_coordinator(self, camera: Any) -> None:
        """Bind the broker's actual reservation owner without opening a device."""
        with self._lock:
            if self._job is not None:
                raise ManagedScopeError("session", "reservation_owner_change")
            self._camera_coordinator = camera

    @classmethod
    def from_environment(cls, project_dir: Path, runtime_root: Path) -> Any:
        socket_path = os.environ.get("ROBOT_SCOPE_SLAM_BROKER_SOCKET")
        if socket_path:
            from .slam_broker import BrokerIsaacAdapter

            return BrokerIsaacAdapter(Path(socket_path))
        value = os.environ.get("ROBOT_SCOPE_SLAM_RUNTIME_CONFIG", "")
        return cls(project_dir, runtime_root,
                   enabled=os.environ.get("ROBOT_SCOPE_SLAM_ENABLE") == "1",
                   config_path=Path(value) if value else None)

    def capability(self) -> dict[str, Any]:
        installed = all(importlib.util.find_spec(name) is not None for name in
                        ("rclpy", "launch", "launch_ros", "sensor_msgs", "tf2_ros",
                         "ament_index_python", "isaac_ros_visual_slam_interfaces"))
        reason = ""
        if not self.enabled:
            reason = "administrator has not enabled the preserved Isaac runtime"
        elif self.config_path is None:
            reason = "observed runtime configuration is missing"
        elif not installed or shutil.which("ros2") is None:
            reason = "Isaac ROS environment is unavailable in this dashboard process"
        elif (os.environ.get("ROS_LOCALHOST_ONLY") != "1"
                or os.environ.get("RMW_IMPLEMENTATION") != "rmw_fastrtps_cpp"
                or any(os.environ.get(key) for key in ("CYCLONEDDS_URI", "FASTDDS_DEFAULT_PROFILES_FILE", "FASTRTPS_DEFAULT_PROFILES_FILE"))):
            reason = "dashboard observer requires an isolated localhost FastDDS process environment"
        return {"engine_id": self.engine_id, "available_now": not reason,
                "supported_in_source": True, "installed": installed,
                "software_verified": False, "hardware_verified": False,
                "blocked_reason": "ENGINE_UNAVAILABLE" if reason else None,
                "blocked_detail": reason, "tasks": ["tracking", "mapping"],
                "map_frame": MAP_FRAME, "pose_reference": "camera_link",
                "installed_contract_verified": False,
                "source_limits": {"observations": MAX_OBSERVATIONS,
                                  "map_landmarks": MAX_MAP_POINTS, "trajectory": MAX_PATH_POSES},
                "compatibility": self.compatibility()}

    def _configuration(self, task: str = "mapping") -> dict[str, Any]:
        capability = self.capability()
        if not capability["available_now"]:
            raise IsaacRuntimeError(capability["blocked_detail"])
        assert self.config_path is not None
        config = _private_json(self.config_path)
        domain = config.get("domain_id")
        if type(domain) is not int or not 1 <= domain <= 232 or domain == config.get("operational_domain_id", 0):
            raise IsaacRuntimeError("SLAM requires a distinct administrator-checked ROS domain")
        managed_path = config.get("managed_scope")
        if managed_path is not None:
            if not isinstance(managed_path, str):
                raise ManagedScopeError("session", "managed_scope_invalid")
            config["_managed_scope"] = load_managed_scope(Path(managed_path), domain_id=domain,
                operational_domain_id=config.get("operational_domain_id", 0))
        else:
            try:
                checked = dt.datetime.fromisoformat(str(config["domain_checked_at_utc"]).replace("Z", "+00:00"))
                age = (dt.datetime.now(dt.timezone.utc) - checked).total_seconds()
            except (KeyError, ValueError, TypeError) as exc:
                raise IsaacRuntimeError("isolated domain observation is missing") from exc
            if config.get("domain_available") is not True or not -5 <= age <= 300:
                raise IsaacRuntimeError("isolated domain must be checked within five minutes")
        contract_module = runpy.run_path(str(self.project_dir / "experiments/isaac_vslam/config/launch_contract.py"))
        for name in ("input_contract", "camera_contract"):
            if not isinstance(config.get(name), str):
                raise IsaacRuntimeError("observed input and camera contract paths are required")
        inputs = _private_json(Path(config["input_contract"]))
        camera = _private_json(Path(config["camera_contract"]))
        if inputs.get("source", {}).get("kind") != "live":
            raise IsaacRuntimeError("managed stereo runtime accepts live observed input only")
        if inputs.get("rectified_images") is not True:
            raise IsaacRuntimeError("managed stereo overlay requires observed rectified input")
        contract_module["validate_input"](inputs, "slam_vo" if task == "mapping" else "vo", False)
        contract_module["validate_camera_profile" if managed_path is not None else "validate_camera"](
            camera, config.get("stereo_profile", ""))
        config["input"] = inputs
        for key, document in (("input", inputs), ("camera", camera)):
            encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
            config[key + "_content"] = encoded
            config[key + "_hash"] = hashlib.sha256(encoded).hexdigest()
        return config

    def preflight(self, task: str) -> None:
        if task not in {"mapping", "tracking"}:
            raise IsaacRuntimeError("Isaac stereo task is unsupported")
        self._configuration(task)
        with self._lock:
            if self._job is not None:
                raise IsaacRuntimeError("an owned Isaac stereo session already exists")

    @staticmethod
    def _identity(session: dict[str, Any]) -> tuple[str, int]:
        identifier, generation = session.get("session_id"), session.get("generation")
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier):
            raise IsaacRuntimeError("SLAM session identity is invalid")
        if type(generation) is not int or generation < 1:
            raise IsaacRuntimeError("SLAM session generation is invalid")
        return identifier, generation

    def _owned(self, session: dict[str, Any]) -> dict[str, Any]:
        identity = self._identity(session)
        with self._lock:
            if self._job is None or self._job["identity"] != identity:
                raise IsaacRuntimeError("SLAM session ownership changed")
            return self._job

    def start(self, session: dict[str, Any], cancel: threading.Event) -> dict[str, Any]:
        identity = self._identity(session)
        self.preflight(str(session.get("task", "mapping")))
        config = self._configuration(str(session.get("task", "mapping")))
        run_dir = self.runtime_root / (identity[0] + "-" + str(identity[1]))
        run_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        # Launch the exact validated contract snapshots, preserving originals.
        for key in ("input", "camera"):
            path = run_dir / (key + "_contract.json")
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(config[key + "_content"])
            config[key + "_contract"] = str(path)
        job: dict[str, Any] = {"identity": identity, "session": dict(session), "config": config,
                               "run_dir": run_dir, "process": None, "context": None,
                               "node": None, "executor": None, "thread": None,
                               "lock": threading.RLock(), "frames": {}, "errors": [],
                               "effective_parameters": {}, "stopping": False,
                               "native_log_diagnostics": NativeLogDiagnostics()}
        job["effective_mode"] = "slam_vo" if session.get("task", "mapping") == "mapping" else "vo"
        job["expected_parameters"] = dict(EXPECTED_PARAMETERS,
            enable_localization_n_mapping=job["effective_mode"] == "slam_vo")
        context = StreamContext(identity[0], identity[1], str(session.get("map_epoch", identity[0])), "ros")
        job["feature_context"] = context
        job["features"] = FeatureStream(context, engine_id=self.engine_id, map_frame=MAP_FRAME,
                                         camera_id="left", max_observations=MAX_OBSERVATIONS,
                                         max_global_points=MAX_MAP_POINTS)
        job["calibration_revision"] = config["input_hash"]
        with self._lock:
            if self._job is not None:
                raise IsaacRuntimeError("an owned Isaac stereo session already exists")
            self._job = job
        try:
            scope = config.get("_managed_scope")
            camera_proof = None
            if scope is not None:
                if self._camera_coordinator is None:
                    raise ManagedScopeError("camera", "managed_reservation_missing")
                camera_proof = self._camera_coordinator.reservation_proof(session)
                if (camera_proof["scope_id"] != scope["scope_id"]
                        or camera_proof["scope_sha256"] != scope["scope_sha256"]):
                    raise ManagedScopeError("camera", "managed_scope_changed")
                job["domain_reservation"] = DomainReservation(scope)
                job["domain_reservation"].acquire()
            self._attach_ros(job)
            environment = dict(os.environ)
            for key in ("CYCLONEDDS_URI", "FASTDDS_DEFAULT_PROFILES_FILE", "FASTRTPS_DEFAULT_PROFILES_FILE"):
                environment.pop(key, None)
            environment.update(ROS_DOMAIN_ID=str(config["domain_id"]), ROS_LOCALHOST_ONLY="1",
                               RMW_IMPLEMENTATION="rmw_fastrtps_cpp",
                               VSLAM_LAB_OPERATIONAL_DOMAIN_ID=str(config.get("operational_domain_id", 0)))
            command = [str(shutil.which("ros2")), "launch", str(self.project_dir / "scripts/slam/managed.launch.py"),
                       "input_contract:=" + str(config["input_contract"]),
                       "camera_contract:=" + str(config["camera_contract"]),
                       "stereo_profile:=" + str(config["stereo_profile"]), "run_dir:=" + str(run_dir),
                       "mode:=" + job["effective_mode"]]
            if scope is not None:
                proof = dict(camera_proof, schema_version=1, evidence_kind="live_managed_reservation",
                    session_id=identity[0], generation=identity[1], domain_id=scope["domain_id"],
                    domain_lock=job["domain_reservation"].evidence())
                validate_reservation_proof(proof, scope)
                proof_path = run_dir / "reservation_proof.json"
                descriptor = os.open(proof_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as output:
                    json.dump(proof, output, allow_nan=False, sort_keys=True)
                command.extend(["managed_scope:=" + str(config["managed_scope"]),
                                "reservation_proof:=" + str(proof_path)])
            log_file = (run_dir / "runtime.log").open("xb")
            job["log_file"] = log_file
            job["process"] = subprocess.Popen(command, cwd=self.project_dir, env=environment,
                                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                               start_new_session=True)
            job["log_thread"] = threading.Thread(target=self._read_log, args=(job,),
                name="robot-scope-slam-log", daemon=True)
            job["log_thread"].start()
            deadline = time.monotonic() + 45.0
            while time.monotonic() < deadline:
                if cancel.is_set():
                    raise IsaacRuntimeError("SLAM startup canceled")
                if job["process"].poll() is not None:
                    raise IsaacRuntimeError("owned Isaac launch exited during startup")
                if not job["effective_parameters"]:
                    self._read_parameters(job, timeout=0.25)
                current = self.status(session)
                if current["ready"]:
                    return {"effective_mode": job["effective_mode"], "readiness": current, "ready": True,
                            "effective_parameters": dict(job["effective_parameters"]),
                            "installed_contract_verified": True}
                cancel.wait(0.05)
            raise IsaacRuntimeError("Isaac stereo startup timed out before verified tracking")
        except BaseException:
            self.stop(session)
            raise

    @staticmethod
    def _read_log(job: dict[str, Any]) -> None:
        stream = job["process"].stdout
        total = 0
        try:
            while True:
                # read1 observes available native messages without waiting to
                # fill 4096 bytes. The retained raw log remains capped at1MiB.
                chunk = stream.read1(4096)
                if not chunk:
                    return
                job["native_log_diagnostics"].feed(chunk)
                retained = chunk[:max(0, 1024 * 1024 - total)]
                if retained:
                    job["log_file"].write(retained)
                    job["log_file"].flush()
                    total += len(retained)
                if len(retained) != len(chunk):
                    job["log_truncated"] = True
        finally:
            stream.close()

    def _attach_ros(self, job: dict[str, Any]) -> None:
        import rclpy
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.node import Node
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import CameraInfo, Image, PointCloud2
        from nav_msgs.msg import Odometry, Path as RosPath
        from isaac_ros_visual_slam_interfaces.msg import VisualSlamStatus
        from tf2_ros import Buffer, TransformListener
        from ament_index_python.packages import get_package_share_directory

        context = Context()
        package_xml = Path(get_package_share_directory("isaac_ros_visual_slam")) / "package.xml"
        job["engine_version"] = ET.parse(package_xml).getroot().findtext("version") or "unknown"
        self._last_compatibility = self._compatibility(job)
        rclpy.init(context=context, domain_id=job["config"]["domain_id"])
        job["context"] = context
        node = Node("robot_scope_slam_observer", namespace="/vslam_lab", context=context,
                    cli_args=["--ros-args", "-r", "/tf:=/vslam_lab/tf", "-r", "/tf_static:=/vslam_lab/tf_static"])
        job["node"] = node
        executor = SingleThreadedExecutor(context=context)
        job["executor"] = executor
        executor.add_node(node)
        job["tf_buffer"] = Buffer(node=node)
        job["tf_listener"] = TransformListener(job["tf_buffer"], node, spin_thread=False)
        inputs = job["config"]["input"]
        topics = [(Image, inputs["left"]["image_topic"], "image"),
                  (Image, inputs["right"]["image_topic"], "right_image"),
                  (CameraInfo, inputs["left"]["camera_info_topic"], "camera_info"),
                  (CameraInfo, inputs["right"]["camera_info_topic"], "right_camera_info"),
                  (PointCloud2, SLAM_ROOT + "/vis/observations_cloud", "observations"),
                  (PointCloud2, SLAM_ROOT + "/vis/landmarks_cloud", "landmarks"),
                  (Odometry, CORRECTED_POSE_TOPIC, "pose"),
                  (RosPath, SLAM_ROOT + "/tracking/slam_path", "path"),
                  (VisualSlamStatus, SLAM_ROOT + "/status", "tracking")]
        job["topics"] = {key: topic for _, topic, key in topics}
        job["subscriptions"] = [node.create_subscription(kind, topic,
            lambda message, key=key: self._receive(job, key, message), qos_profile_sensor_data)
            for kind, topic, key in topics]
        thread = threading.Thread(target=executor.spin, name="robot-scope-slam-observer", daemon=True)
        job["thread"] = thread
        thread.start()
        # Observe the isolated graph before this owner starts any child.  The
        # Legacy attestations and fixed managed policy are never a graph probe.
        # Managed starts already hold their exact domain reservation here.
        time.sleep(0.25)
        foreign = [(name, namespace) for name, namespace in node.get_node_names_and_namespaces()
                   if name not in {"robot_scope_slam_observer", "transform_listener_impl"}]
        if foreign:
            raise ManagedScopeError("ros_domain", "foreign_participant")

    def _receive(self, job: dict[str, Any], key: str, message: Any) -> None:
        try:
            with job["lock"]:
                if job.get("localizing", False):
                    return
            if job.get("node") is not None and job["node"].count_publishers(job["topics"][key]) != 1:
                raise IsaacRuntimeError("SLAM source publisher is not unique")
            if key in {"image", "right_image"}:
                if len(message.data) > MAX_IMAGE_BYTES or not 1 <= int(message.width) <= 1920 or not 1 <= int(message.height) <= 1080:
                    raise IsaacRuntimeError("SLAM input image exceeds the fixed runtime bound")
                expected = job["config"]["input"].get("left" if key == "image" else "right", {})
                if (expected.get("encoding") is not None and str(message.encoding) != expected["encoding"]
                        or str(message.header.frame_id) != expected.get("image_frame", str(message.header.frame_id))):
                    raise IsaacRuntimeError("SLAM input image does not match the observed camera contract")
                channels = {"mono8": 1, "rgb8": 3}.get(str(message.encoding))
                if (channels is None or int(message.step) < int(message.width)*channels
                        or len(message.data) != int(message.step)*int(message.height)):
                    raise IsaacRuntimeError("SLAM input image row layout is invalid")
                value = {"width": int(message.width), "height": int(message.height),
                         "encoding": str(message.encoding), "step": int(message.step),
                         "data": bytes(message.data), "stamp_ns": _stamp(message),
                         "frame_id": str(message.header.frame_id)}
            elif key in {"camera_info", "right_camera_info"}:
                expected = job["config"]["input"].get("left" if key == "camera_info" else "right", {})
                if str(message.header.frame_id) != expected.get("camera_info_frame", str(message.header.frame_id)):
                    raise IsaacRuntimeError("SLAM CameraInfo frame does not match the observed contract")
                value = {"width": int(message.width), "height": int(message.height),
                         "k": list(message.k), "p": list(message.p), "r": list(message.r),
                         "d": list(message.d), "distortion_model": str(message.distortion_model),
                         "frame_id": str(message.header.frame_id), "stamp_ns": _stamp(message)}
            elif key in {"observations", "landmarks"}:
                if str(message.header.frame_id) != MAP_FRAME:
                    raise IsaacRuntimeError("Isaac visualization cloud is outside the isolated map frame")
                value = {"xyz": decode_cloud(message, MAX_OBSERVATIONS if key == "observations" else MAX_MAP_POINTS),
                         "stamp_ns": _stamp(message), "frame_id": MAP_FRAME,
                         "source_limit": MAX_OBSERVATIONS if key == "observations" else MAX_MAP_POINTS,
                         "source_limited": True}
            elif key == "pose":
                value = _pose(message)
                if value["frame_id"] != MAP_FRAME or str(message.child_frame_id) != job["config"]["input"]["base_frame"]:
                    raise IsaacRuntimeError("corrected SLAM pose has the wrong map frame")
                value["source_topic"] = CORRECTED_POSE_TOPIC
                value["child_frame_id"] = str(message.child_frame_id)
                value["pose_reference"] = str(message.child_frame_id)
            elif key == "path":
                if str(message.header.frame_id) != MAP_FRAME or len(message.poses) > MAX_PATH_POSES:
                    raise IsaacRuntimeError("SLAM path frame or bounded source count is invalid")
                value = {"poses": [_pose(pose) for pose in message.poses],
                         "frame_id": MAP_FRAME, "stamp_ns": _stamp(message), "source_limited": True,
                         "source_limit": MAX_PATH_POSES}
            else:
                value = {"state": {0: "UNKNOWN", 1: "TRACKING", 2: "LOST"}.get(int(message.vo_state), "UNKNOWN"),
                         "stamp_ns": _stamp(message),
                         "received_monotonic": time.monotonic()}
            value["received_monotonic"] = time.monotonic()
            with job["lock"]:
                # Native localization changes map coordinates. Volatile DDS
                # callbacks queued before its completion must not be relabeled
                # with the new map epoch. Live host_ros input and the verified
                # observer system clock share this exact timestamp domain.
                if job.get("localizing", False):
                    return
                if value["stamp_ns"] <= job.get("source_stamp_floor_ns", -1):
                    raise IsaacRuntimeError("SLAM source predates native localization epoch")
                previous = job["frames"].get(key)
                if previous is not None and "stamp_ns" in value and value["stamp_ns"] <= previous["stamp_ns"]:
                    raise IsaacRuntimeError("SLAM source stamp did not advance")
                job["frames"][key] = value
                if key == "image":
                    # Actual immutable left pixels, separate from stereo pair
                    # readiness metadata. Never restamp delayed native output.
                    history = job.setdefault("image_history", deque())
                    history.append(value)
                    while (len(history) > STEREO_HISTORY_SIZE
                           or sum(len(item["data"]) for item in history) > MAX_IMAGE_HISTORY_BYTES):
                        history.popleft()
                        job["image_history_evictions"] = job.get("image_history_evictions", 0) + 1
                if key in {"image", "right_image"}:
                    # Callback order is not a stereo synchronizer. Retain only
                    # bounded metadata, not another history of image payloads,
                    # so a newer unmatched callback cannot hide a real pair.
                    history = job.setdefault("stereo_history", {})
                    history.setdefault(key, deque(maxlen=STEREO_HISTORY_SIZE)).append({
                        field: value[field] for field in
                        ("stamp_ns", "received_monotonic", "width", "height", "frame_id")})
                self._record_features(job, key, message, value)
        except (AttributeError, TypeError, ValueError, IsaacRuntimeError, FeatureValidationError) as exc:
            with job["lock"]:
                job["errors"] = (job["errors"] + [str(exc)[:160]])[-8:]

    def _record_features(self, job: dict[str, Any], key: str, message: Any, value: dict[str, Any]) -> None:
        stream, context = job["features"], job["feature_context"]
        shared = {"context": context, "camera_id": "left", "calibration_revision": job["calibration_revision"]}
        if key == "image":
            stream.record_image(**shared, stamp_ns=value["stamp_ns"], width=value["width"],
                                height=value["height"], frame_id=value["frame_id"],
                                received_at=value["received_monotonic"])
        elif key == "camera_info":
            roi = message.roi
            stream.record_camera_info(**shared, stamp_ns=value["stamp_ns"], width=value["width"],
                height=value["height"], frame_id=value["frame_id"], p=value["p"],
                roi=(int(roi.x_offset), int(roi.y_offset), int(roi.width), int(roi.height)),
                binning_x=int(message.binning_x), binning_y=int(message.binning_y))
        elif key == "observations":
            stream.update_observations(message, **shared, source_id=SLAM_ROOT + "/vis/observations_cloud",
                provenance="isaac_ros_3_2_LL_OBSERVATIONS_xyz_reprojection")
        elif key == "landmarks":
            stream.replace_global(message, context=context, source_id=SLAM_ROOT + "/vis/landmarks_cloud",
                provenance="isaac_ros_3_2_LL_MAP_visualization", coverage="unknown", backend_limit=MAX_MAP_POINTS)
        elif key == "pose":
            from rclpy.time import Time

            inputs = job["config"]["input"]
            optical = inputs["left"]["image_frame"]
            base = inputs["base_frame"]
            try:
                # Query the verified camera chain at the source stamp. Never
                # substitute latest dynamic TF or assume a body extrinsic.
                transform = job["tf_buffer"].lookup_transform(base, optical, Time(nanoseconds=value["stamp_ns"]))
                position, quaternion = compose_optical_pose(value, transform)
                stream.record_pose(context=context, stamp_ns=value["stamp_ns"], frame_id=MAP_FRAME,
                    camera_frame_id=optical, position=position, quaternion_xyzw=quaternion)
            except Exception as exc:
                job["errors"] = (job["errors"] + ["observed optical transform unavailable: " + type(exc).__name__])[-8:]
        elif key == "path":
            stream.replace_trajectory([pose["position"] for pose in value["poses"]], context=context,
                stamp_ns=value["stamp_ns"], source_id=SLAM_ROOT + "/tracking/slam_path",
                provenance="isaac_ros_3_2_corrected_slam_path", frame_id=MAP_FRAME,
                trajectory_kind="slam" if job.get("effective_mode", "slam_vo") == "slam_vo" else "vo")
        elif key == "tracking":
            stream.heartbeat(context=context, tracking_state=value["state"])

    @staticmethod
    def _call(job: dict[str, Any], kind: Any, service: str, request: Any, timeout: float) -> Any:
        client = job["node"].create_client(kind, service)
        try:
            if not client.wait_for_service(timeout_sec=min(timeout, 1.0)):
                raise IsaacRuntimeError("required Isaac service is unavailable")
            future = client.call_async(request)
            deadline = time.monotonic() + timeout
            while not future.done() and time.monotonic() < deadline and not job["stopping"]:
                time.sleep(0.01)
            if not future.done():
                future.cancel()
                raise IsaacRuntimeError("Isaac service operation timed out")
            result = future.result()
            if result is None:
                raise IsaacRuntimeError("Isaac service returned no result")
            return result
        finally:
            job["node"].destroy_client(client)

    def _read_parameters(self, job: dict[str, Any], timeout: float) -> None:
        from rcl_interfaces.srv import GetParameters

        request = GetParameters.Request()
        expected = job.get("expected_parameters", EXPECTED_PARAMETERS)
        request.names = list(expected)
        try:
            result = self._call(job, GetParameters, "/vslam_lab/visual_slam_node/get_parameters", request, timeout)
        except IsaacRuntimeError:
            return
        if len(result.values) != len(request.names):
            raise IsaacRuntimeError("Isaac effective parameter readback is incomplete")
        effective = {}
        for name, value in zip(request.names, result.values):
            if int(value.type) != 1 or bool(value.bool_value) is not expected[name]:
                raise IsaacRuntimeError("Isaac effective parameter mismatch: " + name)
            effective[name] = bool(value.bool_value)
        job["effective_parameters"] = effective

    @staticmethod
    def _stereo_pair(job: dict[str, Any], now: float) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Select actual received input within the existing 5 ms/1 s bounds."""
        history, frames = job.get("stereo_history", {}), job["frames"]
        samples = {key: [value for value in history.get(key, [frames.get(key, {})])
                         if "stamp_ns" in value and now-value["received_monotonic"] <= 1.0]
                   for key in ("image", "right_image")}
        pairs = [(left, right) for left in samples["image"] for right in samples["right_image"]
                 if abs(left["stamp_ns"]-right["stamp_ns"]) <= 5_000_000
                 and all(left.get(key) == right.get(key) for key in ("width", "height"))]
        return max(pairs, key=lambda pair: (min(value["stamp_ns"] for value in pair),
                   -abs(pair[0]["stamp_ns"]-pair[1]["stamp_ns"]))) if pairs else None

    def status(self, session: dict[str, Any]) -> dict[str, Any]:
        job = self._owned(session)
        now = time.monotonic()
        with job["lock"]:
            frames = job["frames"]
            fresh = {key: key in frames and now - frames[key]["received_monotonic"] <= 1.0
                     for key in ("image", "right_image", "pose", "tracking")}
            tracking = frames.get("tracking", {}).get("state", "UNKNOWN")
            ready = all(fresh.values()) and tracking == "TRACKING" and bool(job["effective_parameters"])
            pair = self._stereo_pair(job, now)
            stereo = {"matched": pair is not None, "source_tolerance_ns": "5000000"}
            cached = job.get("stereo_history", {})
            stereo["histories"] = {}
            for side in ("image", "right_image"):
                entries = list(cached.get(side, [frames[side]] if side in frames else []))
                stamps = [item["stamp_ns"] for item in entries]
                stereo["histories"][side] = {
                    "retained_count": len(entries), "capacity": STEREO_HISTORY_SIZE,
                    "fresh_count": sum(now-item["received_monotonic"] <= 1.0 for item in entries),
                    "min_stamp_ns": str(min(stamps)) if stamps else None,
                    "max_stamp_ns": str(max(stamps)) if stamps else None,
                }
            if pair is not None:
                left, right = pair
                stereo.update(left_timestamp_ns=str(left["stamp_ns"]),
                              right_timestamp_ns=str(right["stamp_ns"]),
                              skew_ns=str(abs(left["stamp_ns"]-right["stamp_ns"])),
                              receive_age_s=max(now-value["received_monotonic"] for value in pair))
            if job.get("node") is not None:
                required = ("image", "right_image", "camera_info", "right_camera_info", "pose", "tracking")
                unique = all(job["node"].count_publishers(job["topics"][key]) == 1 for key in required)
                ready = ready and unique
                left, right = pair if pair is not None else ({}, {})
                info, right_info = frames.get("camera_info", {}), frames.get("right_camera_info", {})
                aligned = (pair is not None
                           and all(info.get(key) == left.get(key) == right.get(key) == right_info.get(key)
                                   for key in ("width", "height"))
                           and all(key in frames and now-frames[key]["received_monotonic"] <= 1.0
                                   for key in ("camera_info", "right_camera_info")))
                projection = right_info.get("p", [])
                baseline = job["config"]["input"]["baseline_m"]
                if len(projection) != 12 or not projection[0] or not math.isfinite(projection[3]):
                    aligned = False
                else:
                    aligned = aligned and abs(abs(projection[3] / projection[0]) - baseline) <= 0.0001
                ready = ready and aligned
            process = job["process"]
            alive = process is not None and process.poll() is None
            return {"ready": ready and alive and not job.get("stopping", False) and not job.get("localizing", False), "alive": alive,
                    "stopping": bool(job.get("stopping", False)),
                    "localizing": bool(job.get("localizing", False)),
                    "tracking_state": tracking, "freshness": fresh,
                    "stereo_pair": stereo,
                    "effective_parameters": dict(job["effective_parameters"]),
                    "installed_contract_verified": bool(job["effective_parameters"]),
                    "pose_source": CORRECTED_POSE_TOPIC,
                    "pose_reference": job["config"]["input"]["base_frame"],
                    "operational_pose_approved": False, "errors": list(job["errors"])}

    def frame(self, session: dict[str, Any]) -> dict[str, Any]:
        job = self._owned(session)
        with job["lock"]:
            frames = copy.deepcopy(job["frames"])
            now = time.monotonic()
            history = {str(image["stamp_ns"]): image for image in job.get("image_history", ())
                       if now-image["received_monotonic"] <= 1.0}
            result = job["features"].frame(now_monotonic=now, image_timestamps_ns=list(history))
            retained = job.get("image_history", ())
            diagnostics = result.get("alignment_diagnostics")
            # FeatureStream may omit optional diagnostics to preserve geometry
            # within its wire budget. Do not recreate them or suppress media.
            if isinstance(diagnostics, dict):
                diagnostics["pixel_cache"] = {
                    "retained_count": len(retained), "fresh_count": len(history),
                    "capacity": STEREO_HISTORY_SIZE, "byte_limit": MAX_IMAGE_HISTORY_BYTES,
                    "retained_bytes": sum(len(item["data"]) for item in retained),
                    "evicted_count": job.get("image_history_evictions", 0),
                    "min_stamp_ns": str(min(item["stamp_ns"] for item in retained)) if retained else None,
                    "max_stamp_ns": str(max(item["stamp_ns"] for item in retained)) if retained else None,
                }
            selection = result.get("image_selection", {})
            if selection.get("kind") == "newest_fresh_completed_quartet":
                frames["image"] = copy.deepcopy(history[selection["selected_timestamp_ns"]])
        result.update({"session_id": session["session_id"], "generation": session["generation"],
                       "map_epoch": session.get("map_epoch"), "engine_id": self.engine_id,
                       "installed_contract_verified": bool(job["effective_parameters"]),
                       "pose_origin_topic": CORRECTED_POSE_TOPIC})
        image = frames.get("image")
        if image:
            image.update(camera_id="left", rectified=job["config"]["input"].get("rectified_images") is True)
            try:
                from PIL import Image

                encoding = image["encoding"]
                mode = {"mono8": "L", "rgb8": "RGB"}.get(encoding)
                if mode is None:
                    raise ValueError("unsupported stereo image encoding")
                decoded = Image.frombytes(mode, (image["width"], image["height"]), image["data"],
                                          "raw", mode, image["step"])
                output = io.BytesIO()
                decoded.save(output, format="JPEG", quality=80)
                image["jpeg_base64"] = base64.b64encode(output.getvalue()).decode("ascii")
            except (ImportError, ValueError, OSError):
                try:
                    image["png_base64"] = base64.b64encode(encode_png(image)).decode("ascii")
                except IsaacRuntimeError:
                    image["preview_unavailable_reason"] = "matching stereo input preview encoder unavailable"
            image.pop("data", None)
            image["stamp_ns"] = str(image["stamp_ns"])
        result["image"] = image
        result["camera_pose"] = frames.get("pose")
        if result["camera_pose"]:
            result["camera_pose"]["stamp_ns"] = str(result["camera_pose"]["stamp_ns"])
        result["readiness"] = self.status(session)
        return result

    def save(self, session: dict[str, Any], native_path: Path) -> dict[str, Any]:
        from isaac_ros_visual_slam_interfaces.srv import FilePath

        job = self._owned(session)
        if job.get("effective_mode", "slam_vo") != "slam_vo":
            raise IsaacRuntimeError("native save is unavailable in tracking-only mode")
        if not self.status(session)["ready"]:
            raise IsaacRuntimeError("verified stereo tracking is required before saving")
        path = Path(native_path)
        if not path.is_absolute() or path.is_symlink() or not path.is_dir() or any(path.iterdir()):
            raise IsaacRuntimeError("native save requires an empty validated staging directory")
        request = FilePath.Request()
        request.file_path = str(path)
        response = self._call(job, FilePath, SLAM_ROOT + "/save_map", request, 25.0)
        data = path / "data.mdb"
        if not response.success or data.is_symlink() or not data.is_file() or data.stat().st_size < 1:
            raise IsaacRuntimeError("official Isaac save did not produce a nonempty native data.mdb")
        return {"official_save_completed": True, "required_native_files": ["data.mdb"],
                "native_format": "isaac-cuvslam-lmdb", "installed_contract_verified": True,
                "metadata": {**self._compatibility(job),
                             "capture_time": dt.datetime.now(dt.timezone.utc).isoformat()},
                "data_provenance": "live_real"}

    def _compatibility(self, job: dict[str, Any]) -> dict[str, Any]:
        config = job["config"]
        return {"engine_id": self.engine_id, "engine_version": job.get("engine_version", "unknown"),
                "native_format_version": "isaac-cuvslam-3.2-lmdb", "map_frame": MAP_FRAME,
                "units": "m", "axes": "ros",
                "calibration_hash": config["input_hash"], "sensor_config_hash": config["camera_hash"]}

    def compatibility(self) -> dict[str, Any]:
        with self._lock:
            job = self._job
            retained = dict(self._last_compatibility)
        if job is not None and job.get("engine_version"):
            return self._compatibility(job)
        if retained:
            return retained
        if not self.enabled or self.config_path is None:
            return {}
        # Static compatibility must not acquire a camera, initialize CUDA/ROS,
        # or require a fresh resource window. Runtime launch still revalidates
        # the complete observed contracts and ownership separately.
        try:
            from ament_index_python.packages import get_package_share_directory

            config = _private_json(self.config_path)
            for name in ("input", "camera"):
                document = _private_json(Path(config[name + "_contract"]))
                config[name + "_hash"] = hashlib.sha256(json.dumps(document, sort_keys=True,
                    separators=(",", ":")).encode("utf-8")).hexdigest()
            package_xml = Path(get_package_share_directory("isaac_ros_visual_slam")) / "package.xml"
            version = ET.parse(package_xml).getroot().findtext("version")
            return self._compatibility({"config": config, "engine_version": version}) if version else {}
        except (ImportError, OSError, ValueError, LookupError, ET.ParseError, IsaacRuntimeError):
            return {}

    def localize(self, session: dict[str, Any], native_path: Path, hint: dict[str, Any]) -> dict[str, Any]:
        from isaac_ros_visual_slam_interfaces.srv import LocalizeInMap

        job = self._owned(session)
        path = Path(native_path)
        if not path.is_absolute() or path.is_symlink() or (path / "data.mdb").is_symlink() or not (path / "data.mdb").is_file():
            raise IsaacRuntimeError("native localization directory is invalid")
        position = hint.get("position")
        orientation = hint.get("quaternion_xyzw")
        if (hint.get("operator_verified") is not True or hint.get("frame_id") != MAP_FRAME or not isinstance(position, (list, tuple))
                or len(position) != 3 or not isinstance(orientation, (list, tuple)) or len(orientation) != 4):
            raise IsaacRuntimeError("explicit isolated map_T_camera pose hint is required")
        values = list(position) + list(orientation)
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in values) or abs(sum(value * value for value in orientation) - 1) > 0.02:
            raise IsaacRuntimeError("localization pose hint is invalid")
        request = LocalizeInMap.Request()
        request.map_folder_path = str(path)
        for key, value in zip(("x", "y", "z"), position):
            setattr(request.pose_hint.position, key, float(value))
        for key, value in zip(("x", "y", "z", "w"), orientation):
            setattr(request.pose_hint.orientation, key, float(value))
        native_identity = opaque_native_identity(path / "data.mdb")
        with job["lock"]:
            if job.get("localizing", False):
                raise IsaacRuntimeError("native localization is already in progress")
            job["localizing"] = True
            job["session"] = dict(session)
            job["feature_context"] = StreamContext(session["session_id"], session["generation"], session["map_epoch"], "ros")
            job["features"].reset(job["feature_context"])
            job["frames"].clear()
            job.pop("stereo_history", None)
            job.pop("image_history", None)
            job.pop("image_history_evictions", None)
            attempt = job["native_localization_attempt"] = job.get("native_localization_attempt", 0) + 1
            log_diagnostics = job.setdefault("native_log_diagnostics", NativeLogDiagnostics())
            log_sequence = log_diagnostics.sequence
            try:
                dispatch_fence = job["node"].get_clock().now().nanoseconds
                if type(dispatch_fence) is not int or dispatch_fence < 0:
                    dispatch_fence = None
            except (AttributeError, KeyError, TypeError, ValueError):
                dispatch_fence = None
        reference = job["config"]["input"].get("base_frame")
        if not isinstance(reference, str) or re.fullmatch(r"[A-Za-z][A-Za-z0-9_/]{0,127}", reference) is None:
            reference = None
        normalized_hint = {"frame_id": MAP_FRAME, "pose_reference": reference,
            "operator_verified": True, "position": [float(value) for value in position],
            "quaternion_xyzw": [float(value) for value in orientation]}
        trace = {"schema_version": 1, "attempt_sequence": attempt,
            "context_digest": digest({key: session.get(key) for key in ("session_id", "generation", "map_epoch")}),
            "hint": normalized_hint, "native_artifact": native_identity,
            "dispatch_source_fence_ns": str(dispatch_fence) if dispatch_fence is not None else None,
            "service": SLAM_ROOT + "/localize_in_map", "response_received": False,
            "official_success": None, "native_sdk_status": None,
            "operational_pose_approved": False}
        trace["request_digest"] = digest(trace)
        trace["private_request_recorded"] = persist_attempt(job.get("run_dir"), attempt, "request", trace)
        completed = False
        response = None
        service_reason = "SERVICE_CALL_INCOMPLETE"
        started = time.monotonic()
        try:
            response = self._call(job, LocalizeInMap, SLAM_ROOT + "/localize_in_map", request, 25.0)
            completed = True
            service_reason = "RESPONSE_RECEIVED"
        except Exception as exc:
            service_reason = {"Isaac service operation timed out": "SERVICE_TIMEOUT",
                "required Isaac service is unavailable": "SERVICE_UNAVAILABLE",
                "Isaac service returned no result": "SERVICE_NO_RESULT"}.get(str(exc), "SERVICE_CALL_ERROR")
            raise
        finally:
            elapsed = max(0.0, time.monotonic() - started)
            fence = None
            clock_error = None
            with job["lock"]:
                job["features"].reset(job["feature_context"])
                job["frames"].clear()
                job.pop("image_history", None)
                job.pop("image_history_evictions", None)
                # A failed/timeout request may still have changed the native
                # estimator. Require new source-time output in either outcome.
                try:
                    fence = job["node"].get_clock().now().nanoseconds
                    if type(fence) is not int or fence < 0:
                        raise ValueError("invalid observer clock")
                except (AttributeError, KeyError, TypeError, ValueError) as exc:
                    clock_error = exc
                if fence is not None and clock_error is None:
                    job["source_stamp_floor_ns"] = max(fence, job.get("source_stamp_floor_ns", -1))
                # Canceling a service future cannot cancel server-side work.
                # On timeout/error the coordinator must stop this owned job;
                # keep its visualization quarantined until cleanup completes.
                job["localizing"] = not completed or clock_error is not None
                context_matches = job["feature_context"] == StreamContext(session["session_id"],
                    session["generation"], session["map_epoch"], "ros")
            trace.update(response_received=completed, official_success=bool(response.success) if completed else None,
                service_outcome=service_reason, service_elapsed_seconds=elapsed, context_matches=context_matches,
                completion_source_fence_ns=str(fence) if clock_error is None else None,
                native_log=log_diagnostics.window(log_sequence, dispatch_fence, fence if clock_error is None else None))
            if not completed or clock_error is not None:
                persist_attempt(job.get("run_dir"), attempt, "result", trace)
                with job["lock"]:
                    job["native_localization_diagnostics"] = copy.deepcopy(trace)
            if clock_error is not None:
                raise IsaacRuntimeError("native localization source clock fence is unavailable") from clock_error
        official = bool(response.success)
        reason = self._confirm_localization(job, session, job["source_stamp_floor_ns"]) if official else "OFFICIAL_LOCALIZATION_FAILED"
        confirmed = official and reason is None
        trace.update(fresh_pose_tracking_confirmed=confirmed, confirmation_reason=reason)
        persist_attempt(job.get("run_dir"), attempt, "result", trace)
        with job["lock"]:
            job["native_localization_diagnostics"] = copy.deepcopy(trace)
        return {"success": confirmed, "localize_success": confirmed, "reason": reason,
                "official_localization_completed": official,
                "fresh_pose_tracking_confirmed": confirmed, "confirmation_reason": reason,
                "native_load": "verified" if response.success else "unknown",
                "operational_pose_approved": False, "pose_reference": "camera_link",
                "native_localization_diagnostics": trace}

    def _confirm_localization(self, job: dict[str, Any], session: dict[str, Any], fence: int) -> str | None:
        """Require new corrected output after the official service completed.

        Service success proves native localization completed. It does not prove
        the observer has received a usable pose in that map epoch. This bounded
        confirmation shares no operational pose publisher or initial-pose path.
        """
        expected = StreamContext(session["session_id"], session["generation"], session["map_epoch"], "ros")
        deadline = self._confirmation_clock() + 5.0
        while self._confirmation_clock() < deadline:
            with self._lock:
                if self._job is not job:
                    return "LOCALIZATION_OWNERSHIP_CHANGED"
            with job["lock"]:
                if job["feature_context"] != expected or job["source_stamp_floor_ns"] != fence:
                    return "LOCALIZATION_CONTEXT_CHANGED"
                if job.get("stopping") or job.get("localizing"):
                    return "LOCALIZATION_OBSERVER_UNAVAILABLE"
                pose, tracking = job["frames"].get("pose", {}), job["frames"].get("tracking", {})
                post_fence = (pose.get("stamp_ns", -1) > fence and tracking.get("stamp_ns", -1) > fence
                    and pose.get("frame_id") == MAP_FRAME and pose.get("source_topic") == CORRECTED_POSE_TOPIC
                    and tracking.get("state") == "TRACKING")
                if post_fence and self.status(session)["ready"]:
                    return None
            remaining = deadline - self._confirmation_clock()
            if remaining > 0:
                self._confirmation_wait(min(0.05, remaining))
        return "FRESH_CORRECTED_POSE_TRACKING_UNAVAILABLE"

    def stop(self, session: dict[str, Any]) -> None:
        with self._lock:
            if self._job is None:
                return
        job = self._owned(session)
        job["stopping"] = True
        process = job.get("process")
        if process is not None:
            for signum, timeout in ((signal.SIGINT, 5), (signal.SIGTERM, 3), (signal.SIGKILL, 2)):
                try:
                    os.killpg(process.pid, signum)
                    deadline = time.monotonic() + timeout
                    while time.monotonic() < deadline:
                        process.poll()
                        os.killpg(process.pid, 0)
                        time.sleep(0.05)
                except ProcessLookupError:
                    break
            process.wait(timeout=2)
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                pass
            else:
                raise IsaacRuntimeError("owned Isaac child group cleanup is not confirmed")
        executor = job.get("executor")
        if executor is not None:
            executor.shutdown(timeout_sec=2)
        thread = job.get("thread")
        if thread is not None:
            thread.join(timeout=2)
            if thread.is_alive():
                raise IsaacRuntimeError("owned Isaac observer cleanup is not confirmed")
        log_thread = job.get("log_thread")
        if log_thread is not None:
            log_thread.join(timeout=2)
            if log_thread.is_alive():
                raise IsaacRuntimeError("owned Isaac log reader cleanup is not confirmed")
        if job.get("node") is not None:
            job["node"].destroy_node()
        context = job.get("context")
        if context is not None and context.ok():
            context.shutdown()
        if job.get("log_file") is not None:
            job["log_file"].close()
        if job.get("domain_reservation") is not None:
            job["domain_reservation"].release()
        with self._lock:
            if self._job is job:
                self._job = None
