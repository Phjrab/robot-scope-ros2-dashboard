"""Bounded Humble ComputePathToPose adapter. Never submits a motion goal."""
from __future__ import annotations

import asyncio
import math
import threading
import time

from ..application.mission_coordinator import MissionConflict, MissionUnavailable
from .models import Pose


class NativePlanner:
    # Fixed server-side Humble contract; HTTP cannot choose topics/plugins.
    action_name = "/compute_path_to_pose"
    planner_id = "GridBased"
    evidence_type = "native_planner"

    def __init__(self, *, enabled=False, timeout_s=5.0):
        self.enabled = enabled
        self.timeout_s = min(10.0, max(0.2, timeout_s))
        self._lock = threading.Lock()

    async def plan(self, start, goal):
        if not self.enabled:
            raise MissionUnavailable("NATIVE_PLANNER_RESOURCE_WINDOW_REQUIRED")
        cancelled = threading.Event()
        worker = asyncio.create_task(asyncio.to_thread(self._compute, start, goal, cancelled))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancelled.set()
            # The bounded worker owns its ROS context and cancels only its own
            # accepted preview request before releasing the concurrency slot.
            try:
                await asyncio.shield(worker)
            except Exception:
                pass
            raise

    def _compute(self, start, goal, cancelled=None):
        if not self._lock.acquire(blocking=False):
            raise MissionConflict("PLANNER_BUSY")
        context = node = client = handle = None
        try:
            try:
                import rclpy
                from rclpy.action import ActionClient
                from rclpy.context import Context
                from nav2_msgs.action import ComputePathToPose
                from geometry_msgs.msg import PoseStamped
            except ImportError as exc:
                raise MissionUnavailable("HUMBLE_PLANNER_DEPENDENCIES_UNAVAILABLE") from exc
            context = Context()
            rclpy.init(args=[], context=context)
            node = rclpy.create_node("robot_scope_mission_preview", context=context, enable_rosout=False)
            client = ActionClient(node, ComputePathToPose, self.action_name)
            deadline = time.monotonic() + self.timeout_s

            def wait(future):
                while not future.done():
                    if cancelled is not None and cancelled.is_set():
                        raise MissionUnavailable("PLANNER_REQUEST_CANCELLED")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise MissionUnavailable("PLANNER_TIMEOUT")
                    rclpy.spin_until_future_complete(node, future, timeout_sec=min(remaining, 0.1))
                return future.result()

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
            request = ComputePathToPose.Goal()
            request.start, request.goal = stamped(start), stamped(goal)
            request.use_start = True
            request.planner_id = self.planner_id
            accepted_future = client.send_goal_async(request)
            # Even if deadline expires before acceptance, drain acceptance briefly
            # so only this preview goal can be cancelled; never cancel all goals.
            try:
                handle = wait(accepted_future)
            except MissionUnavailable:
                rclpy.spin_until_future_complete(node, accepted_future, timeout_sec=1.0)
                if accepted_future.done():
                    handle = accepted_future.result()
                raise
            if handle is None or not handle.accepted:
                raise MissionConflict("PLANNER_REQUEST_REJECTED")
            result = wait(handle.get_result_async())
            if result.status != 4:
                raise MissionConflict("PLANNER_DID_NOT_SUCCEED")
            path = result.result.path
            if path.header.frame_id != "map" or not 1 <= len(path.poses) <= 4096:
                raise MissionConflict("PLANNER_PATH_FRAME_OR_SIZE_INVALID")
            points = []
            for entry in path.poses:
                if entry.header.frame_id not in {"", "map"}:
                    raise MissionConflict("PLANNER_PATH_FRAME_INVALID")
                q = entry.pose.orientation
                values = (q.x, q.y, q.z, q.w)
                if not all(math.isfinite(v) for v in values) or abs(sum(v*v for v in values) - 1.0) > 0.01:
                    raise MissionConflict("PLANNER_ORIENTATION_INVALID")
                yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
                points.append(Pose(x=float(entry.pose.position.x), y=float(entry.pose.position.y), yaw=yaw).model_dump())
            return {"poses": points, "frame": "map", "actual_nav2_run": True, "evidence_type": self.evidence_type, "planner_id": self.planner_id}
        finally:
            # Cleanup failures must never strand the adapter's concurrency slot
            # or destroy another request's node/context.
            try:
                if handle is not None and handle.accepted and node is not None:
                    try:
                        future = handle.cancel_goal_async()
                        rclpy.spin_until_future_complete(node, future, timeout_sec=0.5)
                    except Exception:
                        pass
            finally:
                try:
                    if client is not None:
                        client.destroy()
                finally:
                    try:
                        if node is not None:
                            node.destroy_node()
                    finally:
                        try:
                            if context is not None and context.ok():
                                context.shutdown()
                        finally:
                            self._lock.release()
