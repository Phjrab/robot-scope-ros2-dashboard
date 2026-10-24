"""Calls the real base-revision MissionCoordinator API; never sends raw goals.

C1 must provide a compiled visit mapping and its existing managed admission.
No owner is constructed here. No run creation, monitor, direct cmd_vel, recovery,
operator skip, or production registration is performed by this boundary.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .contracts import GoalReceipt


@dataclass(frozen=True)
class LegBinding:
    visit_id: str
    pose: tuple[float, float, float]


class CoordinatorNavigationPort:
    def __init__(self, coordinator, navigation, *, mission_id, admission, legs,
                 canceled_approach_continuation=None, native_owner=None):
        if coordinator._coordination_lock is not navigation.coordination_lock:
            raise ValueError("EXACT_SHARED_COORDINATION_LOCK_REQUIRED")
        if admission is None or admission is not coordinator._managed_admission:
            raise ValueError("EXISTING_MANAGED_ADMISSION_REQUIRED")
        if not coordinator.snapshot(mission_id)["mission"].get("context_revision"):
            raise ValueError("PINNED_CONTEXT_REQUIRED")
        self.coordinator, self.navigation = coordinator, navigation
        self.mission_id, self.admission, self.legs = mission_id, admission, dict(legs)
        self.canceled_approach_continuation = canceled_approach_continuation
        self.native_owner = native_owner
        self._lock = asyncio.Lock()
        self._requests, self._owned = {}, {}
        self._last_scope = None

    def _mission(self):
        return self.coordinator.snapshot(self.mission_id)["mission"]

    async def dispatch(self, scope, *, leg, pose, request_id):
        async with self._lock:
            payload = ("dispatch", scope, leg, tuple(pose.items()))
            if request_id in self._requests:
                old, response = self._requests[request_id]
                if old != payload:
                    raise ValueError("REQUEST_PAYLOAD_MISMATCH")
                if response is None:
                    raise ValueError("GOAL_SUBMISSION_UNCERTAIN")
                return response
            if len(self._requests) >= 128:
                raise ValueError("REQUEST_LEDGER_FULL")
            binding = self.legs[(scope.step_id, leg)]
            if tuple(pose[k] for k in ("x", "y", "yaw")) != binding.pose:
                raise ValueError("COMPILED_POSE_MISMATCH")
            if scope.mission_run_id != self.mission_id:
                raise ValueError("MISSION_OWNER_MISMATCH")
            if self._last_scope and scope.goal_generation <= self._last_scope.goal_generation:
                raise ValueError("GOAL_GENERATION_REUSED")
            self._requests[request_id] = (payload, None)
            mission = self._mission()
            waypoint = mission.get("current_waypoint") or {}
            if mission["state"] == "ready":
                if waypoint.get("visit_id") != binding.visit_id:
                    raise ValueError("VISIT_OWNER_MISMATCH")
                # start -> _claim takes the shared admission lock; send_goal also
                # takes it. Do not wrap this call in the same non-reentrant lock.
                response = await self.coordinator.start(self.mission_id, admission=self.admission,
                                                        native_owner=self.native_owner)
            elif self.native_owner is not None and leg == "exit" and self._last_scope is not None:
                previous = self.legs[(scope.step_id, "approach")]
                receipt = self._owned[self._last_scope.goal_generation]
                response = await self.coordinator.continue_native(self.mission_id,
                    admission=self.admission, token=self.native_owner,
                    previous_visit=previous.visit_id, next_visit_id=binding.visit_id,
                    actual_goal_id=receipt.actual_goal_id)
            elif mission["state"] == "paused" and mission["phase"] == "after_arrival_confirmation":
                next_index = mission["current_index"] + 1
                if (next_index >= len(mission["waypoints"])
                        or mission["waypoints"][next_index]["visit_id"] != binding.visit_id):
                    raise ValueError("NEXT_VISIT_OWNER_MISMATCH")
                # Internal server continuation, with exact token. No remote skip.
                response = await self.coordinator.resume(self.mission_id,
                    confirmation_token=mission["confirmation_token"], admission=self.admission)
            elif (mission["state"] == "paused" and leg == "exit"
                  and self.canceled_approach_continuation is not None):
                # Absent in base coordinator. C1 owns this explicit atomic hook;
                # fake-port completion does not pretend this API already exists.
                response = await self.canceled_approach_continuation(
                    mission_id=self.mission_id, previous_scope=self._last_scope,
                    next_visit_id=binding.visit_id, admission=self.admission)
            else:
                raise ValueError("COORDINATOR_CONTINUATION_HOOK_REQUIRED")
            current = response["mission"]
            waypoint = current.get("current_waypoint") or {}
            actual_id = waypoint.get("goal_id")
            nav_goal = self.navigation.view().get("goal", {})
            if (not current["ownership_active"] or waypoint.get("visit_id") != binding.visit_id
                    or not isinstance(actual_id, str) or nav_goal.get("goal_id") != actual_id
                    or nav_goal.get("state") not in {"pending", "active", "canceling"}):
                raise ValueError("COORDINATOR_GOAL_OWNERSHIP_UNCERTAIN")
            receipt = GoalReceipt(scope, actual_id)
            self._owned[scope.goal_generation] = receipt
            self._last_scope = scope
            self._requests[request_id] = (payload, receipt)
            return receipt

    async def cancel(self, scope, *, request_id):
        async with self._lock:
            payload = ("cancel", scope)
            if request_id in self._requests:
                if self._requests[request_id][0] != payload:
                    raise ValueError("REQUEST_PAYLOAD_MISMATCH")
                if self._requests[request_id][1] is None:
                    raise ValueError("CANCEL_ACK_UNCONFIRMED")
                return
            if scope.mission_run_id != self.mission_id:
                raise ValueError("MISSION_OWNER_MISMATCH")
            if self._last_scope is not None and scope != self._last_scope:
                raise ValueError("LATE_CANCEL_GENERATION")
            self._requests[request_id] = (payload, None)
            mission = self._mission()
            receipt = self._owned.get(scope.goal_generation)
            nav_goal = self.navigation.view().get("goal", {})
            if receipt and nav_goal.get("goal_id") != receipt.actual_goal_id:
                raise ValueError("FOREIGN_GOAL_NOT_CANCELED")
            if mission["state"] in {"starting", "running"}:
                await self.coordinator.pause(self.mission_id)
            elif mission["state"] in {"pausing", "canceling"}:
                raise ValueError("CANCEL_ACK_PENDING")
            elif mission["state"] not in {"paused", "completed", "failed"}:
                raise ValueError("NO_ACTIVE_OWNED_GOAL")
            # pause() waits for exact goal terminal ACK and retains admission.
            # Read goal state separately; a method return is not physical STOP.
            terminal = self.navigation.view().get("goal", {})
            if receipt and (terminal.get("goal_id") != receipt.actual_goal_id
                            or terminal.get("state") not in {"succeeded", "canceled"}):
                raise ValueError("EXACT_CANCEL_TERMINAL_ACK_REQUIRED")

            self._requests[request_id] = (payload, True)

    def goal_observation(self, scope):
        """Translate exact Nav2 ID to v0.1 logical ID only after ownership check.

        Nav coordinator allows 16..128 token characters; Evidence requires hex32.
        Never truncate/hash a foreign ID into a matching observation.
        """
        receipt = self._owned.get(scope.goal_generation)
        if receipt is None or receipt.scope != scope:
            raise ValueError("UNKNOWN_GOAL_GENERATION")
        goal = self.navigation.view().get("goal", {})
        if goal.get("goal_id") != receipt.actual_goal_id:
            raise ValueError("GOAL_OWNERSHIP_CHANGED")
        states = {"pending": "ACTIVE", "active": "ACTIVE", "canceling": "ACTIVE",
                  "succeeded": "SUCCEEDED", "canceled": "CANCELED", "failed": "FAILED"}
        if goal.get("state") not in states:
            raise ValueError("UNKNOWN_NAVIGATION_STATE")
        return {"goal_id": scope.goal_id, "goal_generation": scope.goal_generation,
                "goal_state": states[goal["state"]], "cancel_ack": goal["state"] == "canceled"}
