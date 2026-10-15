"""Bounded Humble ComputePathToPose adapter. Never submits a motion goal."""
from __future__ import annotations

import asyncio
import hashlib
import math
import os
from pathlib import Path
import threading
import time
import uuid

from ..application.mission_coordinator import MissionConflict, MissionUnavailable
from .models import Pose, digest


_ROS_ENVIRONMENT_KEYS = (
    "ROS_DOMAIN_ID", "ROS_LOCALHOST_ONLY", "RMW_IMPLEMENTATION", "ROS_DISTRO",
    "ROS_AUTOMATIC_DISCOVERY_RANGE", "ROS_STATIC_PEERS", "ROS_SECURITY_ENABLE",
    "ROS_SECURITY_ENCLAVE_OVERRIDE", "ROS_SECURITY_KEYSTORE", "ROS_SECURITY_STRATEGY",
    "ROS_DISCOVERY_SERVER", "ROS_SUPER_CLIENT", "RMW_FASTRTPS_USE_QOS_FROM_XML", "CYCLONEDDS_URI",
    "FASTRTPS_DEFAULT_PROFILES_FILE", "FASTDDS_DEFAULT_PROFILES_FILE",
)


def _environment_snapshot():
    values = {key: os.environ.get(key) for key in _ROS_ENVIRONMENT_KEYS}
    profiles = {}
    for key in ("CYCLONEDDS_URI", "FASTRTPS_DEFAULT_PROFILES_FILE", "FASTDDS_DEFAULT_PROFILES_FILE"):
        value = values[key]
        if not value:
            continue
        if key == "CYCLONEDDS_URI" and value.lstrip().startswith("<"):
            profiles[key] = hashlib.sha256(value.encode()).hexdigest()
            continue
        try:
            path = Path(value.removeprefix("file://"))
            with path.open("rb") as source:
                body = source.read(1024 * 1024 + 1)
            profiles[key] = hashlib.sha256(body).hexdigest() if len(body) <= 1024 * 1024 else "unavailable"
        except (OSError, ValueError):
            profiles[key] = "unavailable"
    return {"values": values, "profile_digests": profiles}


class NativePlanner:
    # Fixed server-side Humble contract; HTTP cannot choose topics/plugins.
    action_name = "/compute_path_to_pose"
    planner_id = "GridBased"
    server_node = ("planner_server", "/")
    evidence_type = "native_planner"
    # A late acceptance/cancel is owned for a finite grace period. Unresolved
    # ownership then remains quarantined, never reported as successful cleanup.
    cleanup_timeout_s = 1.0
    quarantine_cleanup_timeout_s = 5.0

    def __init__(self, *, enabled=False, timeout_s=5.0):
        self.enabled = enabled
        self.timeout_s = min(10.0, max(0.2, timeout_s))
        self._lock = threading.Lock()
        self._admission_lock = threading.Lock()
        self._foreground_workers = set()
        self._environment = _environment_snapshot()
        self._server_identity = None
        self._quarantine = None

    def diagnostics(self):
        state = self._quarantine
        with self._admission_lock:
            foreground_busy = bool(self._foreground_workers)
        return {"enabled": self.enabled, "cleanup": "quarantined" if state else "idle",
                "foreground_busy": foreground_busy,
                "blocking_reason": state["reason"] if state else None,
                "goal_id": state["goal_id"] if state else None}

    async def plan(self, start, goal):
        if not self.enabled:
            raise MissionUnavailable("NATIVE_PLANNER_RESOURCE_WINDOW_REQUIRED")
        cancelled = threading.Event()
        admission = object()
        with self._admission_lock:
            self._foreground_workers.add(admission)
        try:
            worker = asyncio.create_task(asyncio.to_thread(self._compute_owned, start, goal, cancelled, admission))
        except BaseException:
            with self._admission_lock:
                self._foreground_workers.discard(admission)
            raise
        # Repeated HTTP cancellation can stop the await below. The worker still
        # owns cleanup; consume its eventual exception without orphan warnings.
        worker.add_done_callback(lambda task: None if task.cancelled() else task.exception())
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancelled.set()
            # The bounded worker owns its ROS context and cancels only its own
            # accepted preview request before releasing the concurrency slot.
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    # More than one disconnect/shutdown cancellation must not
                    # release the service reservation while its worker owns ROS.
                    cancelled.set()
                except Exception:
                    break
            raise

    def _compute_owned(self, start, goal, cancelled, admission):
        try:
            return self._compute(start, goal, cancelled)
        finally:
            # The native thread, rather than its asyncio wrapper, ends this
            # admission. Cancelling a Future never proves thread completion.
            with self._admission_lock:
                self._foreground_workers.discard(admission)

    def _compute(self, start, goal, cancelled=None):
        if not self._lock.acquire(blocking=False):
            raise MissionConflict("PLANNER_CLEANUP_PENDING" if self._quarantine else "PLANNER_BUSY")
        context = node = client = handle = executor = None
        accepted_future = result_future = None
        transferred = False
        goal_id = uuid.uuid4()
        try:
            self._check_environment()
            try:
                import rclpy
                from rclpy.action import ActionClient
                from rclpy.action.graph import get_action_server_names_and_types_by_node
                from rclpy.context import Context
                from rclpy.executors import SingleThreadedExecutor
                from rclpy.utilities import get_rmw_implementation_identifier
                from nav2_msgs.action import ComputePathToPose
                from geometry_msgs.msg import PoseStamped
                from unique_identifier_msgs.msg import UUID
            except ImportError as exc:
                raise MissionUnavailable("HUMBLE_PLANNER_DEPENDENCIES_UNAVAILABLE") from exc
            try:
                domain_id = int(self._environment["values"]["ROS_DOMAIN_ID"] or "0")
            except ValueError as exc:
                raise MissionUnavailable("PLANNER_ROS_DOMAIN_INVALID") from exc
            context = Context()
            rclpy.init(args=[], context=context, domain_id=domain_id)
            if context.get_domain_id() != domain_id:
                raise MissionUnavailable("PLANNER_ROS_DOMAIN_MISMATCH")
            executor = SingleThreadedExecutor(context=context)
            node = rclpy.create_node("robot_scope_mission_preview_" + goal_id.hex[:12], namespace="/",
                                     context=context, enable_rosout=False, use_global_arguments=False)
            client = ActionClient(node, ComputePathToPose, self.action_name)
            deadline = time.monotonic() + self.timeout_s

            rmw = get_rmw_implementation_identifier()
            configured_rmw = self._environment["values"]["RMW_IMPLEMENTATION"]
            if configured_rmw and configured_rmw != rmw:
                raise MissionUnavailable("PLANNER_RMW_MISMATCH")
            ros_environment = {"environment_digest": digest(self._environment), "rmw": rmw,
                               "domain_id": context.get_domain_id(),
                               "localhost_only": self._environment["values"]["ROS_LOCALHOST_ONLY"] or "0",
                               "profile_digests": self._environment["profile_digests"]}

            def wait(future):
                check_deadline()
                while not future.done():
                    remaining = check_deadline()
                    rclpy.spin_until_future_complete(node, future, executor=executor, timeout_sec=min(remaining, 0.1))
                check_deadline()
                return future.result()

            def check_deadline():
                if cancelled is not None and cancelled.is_set():
                    raise MissionUnavailable("PLANNER_REQUEST_CANCELLED")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MissionUnavailable("PLANNER_TIMEOUT")
                return remaining

            def stamped(value):
                pose = Pose.model_validate(value)
                result = PoseStamped()
                result.header.frame_id = "map"
                result.header.stamp = node.get_clock().now().to_msg()
                result.pose.position.x, result.pose.position.y = float(pose.x), float(pose.y)
                result.pose.orientation.z = math.sin(pose.yaw / 2)
                result.pose.orientation.w = math.cos(pose.yaw / 2)
                return result

            if not client.wait_for_server(timeout_sec=min(1.0, self.timeout_s)):
                raise MissionUnavailable("PLANNER_SERVER_UNAVAILABLE")
            check_deadline()
            identity = self._identity(node, get_action_server_names_and_types_by_node)
            if self._server_identity is not None and identity != self._server_identity:
                raise MissionConflict("PLANNER_SERVER_IDENTITY_CHANGED")
            self._server_identity = identity
            request = ComputePathToPose.Goal()
            request.start, request.goal = stamped(start), stamped(goal)
            request.use_start = True
            request.planner_id = self.planner_id
            check_deadline()
            self._check_environment()
            accepted_future = client.send_goal_async(request, goal_uuid=UUID(uuid=list(goal_id.bytes)))
            handle = wait(accepted_future)
            if handle is None or not handle.accepted:
                raise MissionConflict("PLANNER_REQUEST_REJECTED")
            self._check_handle(handle, goal_id)
            result_future = handle.get_result_async()
            result = wait(result_future)
            if result.status != 4:
                raise MissionConflict("PLANNER_DID_NOT_SUCCEED")
            self._check_environment()
            if self._identity(node, get_action_server_names_and_types_by_node) != identity:
                raise MissionConflict("PLANNER_SERVER_IDENTITY_CHANGED")
            path = result.result.path
            if path.header.frame_id != "map" or not 1 <= len(path.poses) <= 4096:
                raise MissionConflict("PLANNER_PATH_FRAME_OR_SIZE_INVALID")
            points = []
            original = []
            for entry in path.poses:
                if entry.header.frame_id not in {"", "map"}:
                    raise MissionConflict("PLANNER_PATH_FRAME_INVALID")
                q = entry.pose.orientation
                position = entry.pose.position
                if not all(math.isfinite(v) for v in (position.x, position.y, position.z)):
                    raise MissionConflict("PLANNER_POSITION_INVALID")
                values = (q.x, q.y, q.z, q.w)
                if not all(math.isfinite(v) for v in values) or abs(sum(v*v for v in values) - 1.0) > 0.01:
                    raise MissionConflict("PLANNER_ORIENTATION_INVALID")
                yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
                points.append(Pose(x=float(entry.pose.position.x), y=float(entry.pose.position.y), yaw=yaw).model_dump())
                original.append({"header": self._header(entry.header),
                                 "position": {key: float(getattr(position, key)) for key in ("x", "y", "z")},
                                 "orientation": {key: float(getattr(q, key)) for key in ("x", "y", "z", "w")}})
            check_deadline()
            return {"poses": points, "frame": "map", "actual_nav2_run": True,
                    "evidence_type": self.evidence_type, "planner_id": self.planner_id,
                    "goal_id": goal_id.hex, "action_name": self.action_name,
                    "action_server": identity, "ros_environment": ros_environment,
                    "request": {"use_start": True, "start": Pose.model_validate(start).model_dump(),
                                "goal": Pose.model_validate(goal).model_dump(), "header": self._header(request.start.header)},
                    "native_path": {"header": self._header(path.header), "poses": original}}
        finally:
            if accepted_future is not None:
                state = {"goal_id": goal_id.hex, "reason": "PLANNER_CLEANUP_PENDING", "context": context,
                         "node": node, "client": client, "executor": executor, "accepted": accepted_future, "handle": handle,
                         "result": result_future, "cancel": None}
                if not self._finish_owned(rclpy, state, self.cleanup_timeout_s):
                    self._quarantine = state
                    # Transfer, never destroy the context under an unresolved
                    # acceptance. At most one finite cleanup thread can exist.
                    transferred = True
                    try:
                        threading.Thread(target=self._reap_owned, args=(rclpy, state), daemon=True,
                                         name="mission-preview-cleanup-" + goal_id.hex[:8]).start()
                    except RuntimeError:
                        state["reason"] = "PLANNER_CLEANUP_UNCERTAIN"
            if not transferred:
                self._dispose(context, node, client, executor)

    def _check_environment(self):
        if "unavailable" in self._environment["profile_digests"].values():
            raise MissionUnavailable("PLANNER_ROS_PROFILE_UNAVAILABLE")
        if _environment_snapshot() != self._environment:
            raise MissionConflict("PLANNER_ROS_ENVIRONMENT_CHANGED")

    def _identity(self, node, action_servers):
        try:
            return self._inspect_identity(node, action_servers)
        except MissionConflict:
            raise
        except Exception as exc:
            # Nodes may disappear during graph inspection. Never fall through
            # to an unqualified server or expose native exception/path strings.
            raise MissionUnavailable("PLANNER_GRAPH_PROVENANCE_UNAVAILABLE") from exc

    def _inspect_identity(self, node, action_servers):
        owners = []
        for name, namespace in node.get_node_names_and_namespaces():
            for action, types in action_servers(node, name, namespace):
                if action == self.action_name:
                    if types != ["nav2_msgs/action/ComputePathToPose"]:
                        raise MissionConflict("PLANNER_ACTION_TYPE_INVALID")
                    owners.append((name, namespace))
        if owners != [self.server_node]:
            raise MissionConflict("PLANNER_ACTION_OWNER_NOT_UNIQUE")
        publishers = node.get_publishers_info_by_topic(self.action_name + "/_action/status")
        if len(publishers) != 1:
            raise MissionConflict("PLANNER_STATUS_OWNER_NOT_UNIQUE")
        publisher = publishers[0]
        if (publisher.node_name, publisher.node_namespace) != self.server_node or publisher.topic_type != "action_msgs/msg/GoalStatusArray":
            raise MissionConflict("PLANNER_STATUS_OWNER_MISMATCH")
        gid = bytes(publisher.endpoint_gid)
        if len(gid) != 24 or not any(gid):
            raise MissionConflict("PLANNER_SERVER_GID_UNAVAILABLE")
        return {"node_name": self.server_node[0], "node_namespace": self.server_node[1], "status_gid": gid.hex()}

    @staticmethod
    def _header(header):
        stamp = header.stamp
        return {"frame_id": header.frame_id, "stamp": {"sec": stamp.sec, "nanosec": stamp.nanosec}}

    @staticmethod
    def _check_handle(handle, goal_id):
        if bytes(handle.goal_id.uuid) != goal_id.bytes:
            raise MissionConflict("PLANNER_GOAL_IDENTITY_MISMATCH")

    def _finish_owned(self, rclpy, state, timeout_s):
        deadline = time.monotonic() + timeout_s
        try:
            while True:
                accepted = state["accepted"]
                if not accepted.done():
                    future = accepted
                else:
                    handle = state["handle"] = accepted.result()
                    if handle is None or not handle.accepted:
                        return True
                    self._check_handle(handle, uuid.UUID(hex=state["goal_id"]))
                    if state["result"] is None:
                        state["result"] = handle.get_result_async()
                    if state["result"].done():
                        return state["result"].result().status in (4, 5, 6)
                    if state["cancel"] is None:
                        state["cancel"] = handle.cancel_goal_async()
                    # Cancellation acknowledgement alone is not terminal proof.
                    future = state["result"]
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                rclpy.spin_until_future_complete(state["node"], future, executor=state["executor"], timeout_sec=min(.1, remaining))
        except Exception:
            state["reason"] = "PLANNER_CLEANUP_UNCERTAIN"
            return False

    def _reap_owned(self, rclpy, state):
        if self._finish_owned(rclpy, state, self.quarantine_cleanup_timeout_s):
            self._dispose(state["context"], state["node"], state["client"], state["executor"])
            self._quarantine = None
        else:
            state["reason"] = "PLANNER_CLEANUP_UNCERTAIN"
            # Retain exact ownership/resources and deny admission. A current
            # operator must reconcile this request before a resource restart.

    def _dispose(self, context, node, client, executor):
        try:
            if client is not None:
                client.destroy()
        finally:
            try:
                if node is not None:
                    node.destroy_node()
            finally:
                try:
                    if executor is not None:
                        executor.shutdown(timeout_sec=.1)
                finally:
                    try:
                        if context is not None and context.ok():
                            context.shutdown()
                    finally:
                        self._lock.release()
