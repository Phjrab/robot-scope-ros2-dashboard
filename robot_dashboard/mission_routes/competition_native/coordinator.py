"""Calls the real base-revision MissionCoordinator API; never sends raw goals.

C1 must provide a compiled visit mapping and its existing managed admission.
No owner is constructed here. No run creation, monitor, direct cmd_vel, recovery,
operator skip, or production registration is performed by this boundary.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .contracts import ContinuationRequest, ExitAuthorization, GoalReceipt


@dataclass(frozen=True)
class LegBinding:
    visit_id: str
    pose: tuple[float, float, float]


class CoordinatorNavigationPort:
    def __init__(self, coordinator, navigation, *, mission_id, admission, legs,
                 canceled_approach_continuation=None, successful_approach_continuation=None,
                 native_owner=None):
        if coordinator._coordination_lock is not navigation.coordination_lock:
            raise ValueError("EXACT_SHARED_COORDINATION_LOCK_REQUIRED")
        if admission is None or admission is not coordinator._managed_admission:
            raise ValueError("EXISTING_MANAGED_ADMISSION_REQUIRED")
        if not coordinator.snapshot(mission_id)["mission"].get("context_revision"):
            raise ValueError("PINNED_CONTEXT_REQUIRED")
        self.coordinator, self.navigation = coordinator, navigation
        self.mission_id, self.admission, self.legs = mission_id, admission, dict(legs)
        self.canceled_approach_continuation = canceled_approach_continuation
        self.successful_approach_continuation = successful_approach_continuation
        self.native_owner = native_owner
        self._exit_authorization = None
        self._cancel_receipts = {}
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
                owner_args = {"native_owner": self.native_owner} if self.native_owner is not None else {}
                response = await self.coordinator.start(self.mission_id, admission=self.admission, **owner_args)
            elif leg == "exit" and mission["state"] == "paused":
                response = await self._continue(mission, scope, binding, request_id)
            else:
                raise ValueError("COORDINATOR_CONTINUATION_HOOK_REQUIRED")
            current = response["mission"]
            waypoint = current.get("current_waypoint") or {}
            actual_id = waypoint.get("goal_id")
            nav_goal = self.navigation.view().get("goal", {})
            if (not current["ownership_active"] or waypoint.get("visit_id") != binding.visit_id
                    or not isinstance(actual_id, str) or nav_goal.get("goal_id") != actual_id
                    or nav_goal.get("state") not in {"pending", "active"}):
                raise ValueError("COORDINATOR_GOAL_OWNERSHIP_UNCERTAIN")
            receipt = GoalReceipt(scope, actual_id, acknowledged=nav_goal.get("state") == "active")
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
                owner_args = {"native_owner": self.native_owner} if self.native_owner is not None else {}
                await self.coordinator.pause(self.mission_id, **owner_args)
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
            if receipt and terminal.get("state") == "canceled":
                self._cancel_receipts[scope.goal_generation] = request_id

    def prepare_exit(self, authorization: ExitAuthorization):
        """Pure binding of the NEW generation's acknowledged HOLD, no dispatch."""
        if (not isinstance(authorization, ExitAuthorization)
                or authorization.previous_scope != self._last_scope
                or authorization.next_scope != authorization.hold_request.scope
                or authorization.hold_request.mode != "HOLD"
                or not authorization.hold_ack.matches(authorization.hold_request)):
            raise ValueError("EXIT_HOLD_AUTHORIZATION_MISMATCH")
        old, new = authorization.previous_scope, authorization.next_scope
        if (new.goal_generation != old.goal_generation + 1 or new.goal_id == old.goal_id
                or any(getattr(old, key) != getattr(new, key)
                       for key in ("owner_id", "mission_run_id", "step_id", "config_hash"))):
            raise ValueError("EXIT_SCOPE_NOT_SUCCESSOR")
        self._exit_authorization = authorization

    async def _continue(self, mission, scope, binding, request_id):
        if self.native_owner is not None:
            return await self._continue_owned(mission, scope, binding)
        # NEVER turn the ordinary operator after-arrival confirmation into a
        # native barrier. C1 owns a distinct native_action_barrier in the owner.
        if mission["phase"] != "native_action_barrier":
            raise ValueError("NATIVE_BARRIER_REQUIRED:COORDINATOR_CONTINUATION_HOOK_REQUIRED")
        authorization = self._exit_authorization
        previous = self._last_scope
        receipt = self._owned.get(previous.goal_generation) if previous else None
        barrier = mission.get("native_barrier") or {}
        goal = self.navigation.view().get("goal", {})
        status = {"succeeded": "SUCCEEDED", "canceled": "CANCELED"}.get(goal.get("state"))
        index = mission["current_index"] + 1
        if (authorization is None or authorization.next_scope != scope or receipt is None
                or not mission["ownership_active"] or mission["id"] != self.mission_id
                or goal.get("goal_id") != receipt.actual_goal_id
                or barrier.get("scope") != vars(previous)
                or barrier.get("actual_goal_id") != receipt.actual_goal_id
                or status is None or barrier.get("terminal_status") != status
                or not isinstance(barrier.get("token"), str) or not barrier["token"]
                or index >= len(mission["waypoints"])
                or mission["waypoints"][index]["visit_id"] != binding.visit_id):
            raise ValueError("NATIVE_BARRIER_OWNERSHIP_MISMATCH")
        cancel_id = self._cancel_receipts.get(previous.goal_generation) if status == "CANCELED" else None
        callback = (self.canceled_approach_continuation if status == "CANCELED"
                    else self.successful_approach_continuation)
        if callback is None or (status == "CANCELED" and cancel_id is None):
            raise ValueError("COORDINATOR_CONTINUATION_HOOK_REQUIRED")
        request = ContinuationRequest(authorization, receipt.actual_goal_id, binding.visit_id,
                                      status, barrier["token"], cancel_id, request_id)
        # Callback atomically revalidates this snapshot under coordinator's own
        # operation lock. This port does not acquire it or call skip/resume.
        return await callback(request=request, admission=self.admission)

    async def _continue_owned(self, mission, scope, binding):
        """C1 r2's existing token/guard/operation-lock API; no UI resume path."""
        previous = self._last_scope
        receipt = self._owned.get(previous.goal_generation) if previous else None
        authorization = self._exit_authorization
        goal = self.navigation.view().get("goal", {})
        if (receipt is None or authorization is None or authorization.next_scope != scope
                or authorization.previous_scope != previous
                or not mission["ownership_active"] or mission["id"] != self.mission_id
                or mission["current_index"] != 0 or len(mission["waypoints"]) != 2
                or mission["waypoints"][1]["visit_id"] != binding.visit_id
                or goal.get("goal_id") != receipt.actual_goal_id
                or goal.get("state") not in {"succeeded", "canceled"}
                or (goal.get("state") == "succeeded" and mission["phase"] not in {"native_barrier", "native_action_barrier"})
                or (goal.get("state") == "canceled"
                    and previous.goal_generation not in self._cancel_receipts)):
            raise ValueError("NATIVE_OWNER_CONTINUATION_MISMATCH")
        return await self.coordinator.continue_native(
            self.mission_id, admission=self.admission, token=self.native_owner,
            previous_visit=self.legs[(previous.step_id, "approach")].visit_id,
            next_visit_id=binding.visit_id, actual_goal_id=receipt.actual_goal_id)

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
