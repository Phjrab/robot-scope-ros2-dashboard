"""Explicitly driven single-step adapter. No startup hook, monitor or publisher."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
import math
import secrets
import time

from ..models import CompetitionAction, Pose
from .contracts import ActionEvent, Activation, ConstraintAck, ConstraintRequest, ExitAuthorization, GoalReceipt, Scope
from .observations import Normalizer, ObservationRejected
from .state import ActionState, TERMINAL, decide


class NativeActionAdapter:
    def __init__(self, *, action, scope: Scope, navigation, constraints, policy, bindings,
                 activation=Activation(), posture=None, terrain=None, clock=time.monotonic,
                 event_binding=None, receiver_clock_id=None):
        self.action = CompetitionAction.model_validate(action)
        if self.action.step_id != scope.step_id:
            raise ValueError("ACTION_STEP_MISMATCH")
        self.scope, self.navigation, self.constraints = scope, navigation, constraints
        self.posture, self.terrain = posture, terrain
        self.activation, self.policy, self.clock = activation, policy, clock
        self.bindings = dict(bindings)
        self.receiver_session_id = secrets.token_hex(16)
        self.receiver_clock_id = receiver_clock_id or self.receiver_session_id
        self.event_binding = event_binding
        self._event_sequence = -1
        self._events = {}
        self._exit_previous_scope = None
        self._goal_request_id = None
        self._goal_requested_s = None
        self._goal_ack_s = None
        self._constraint_ack_s = None
        self._constraint_requested_s = None
        self._cancel_request_id = None
        self._cancel_requested_s = None
        self.normalizer = None
        self.state = ActionState()
        self._lock = asyncio.Lock()
        self._requests = {}
        self._effects = set()
        self._constraint = None
        self._constraint_ack = None
        self._goal = None
        self._cancelled_generations = set()
        self._last_now = None
        self._stop_requested = False
        self._constraint_sequence = 0
        self._constraint_error = False
        self._cancel_errors = set()

    def snapshot(self):
        # Read-only: no owner creation, clock sampling, port calls, or imports.
        return {"state": dict(vars(self.state)), "scope": dict(vars(self.scope)),
                "capabilities": self.activation.report(self.action),
                "actual_goal_id": self._goal.actual_goal_id if self._goal else None,
                "receiver_session_id": self.receiver_session_id,
                "receiver_clock_id": self.receiver_clock_id,
                "pending": {"goal_request_id": self._goal_request_id,
                            "goal_requested_s": self._goal_requested_s, "goal_ack_s": self._goal_ack_s,
                            "cancel_request_id": self._cancel_request_id,
                            "cancel_requested_s": self._cancel_requested_s,
                            "constraint_requested_s": self._constraint_requested_s,
                            "constraint_ack_s": self._constraint_ack_s,
                            "constraint": asdict(self._constraint) if self._constraint else None}}

    def _now(self):
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError("INVALID_RECEIVER_CLOCK")
        if self._last_now is not None and now < self._last_now:
            raise ValueError("RECEIVER_CLOCK_ROLLBACK")
        self._last_now = now
        return now

    def _cleanup_time(self):
        # Clock failure must not prevent HOLD/cancel. This timestamp can never
        # authorize RELEASE: the active operation fails and retires the action.
        try:
            return self._now()
        except ValueError:
            return self._last_now if self._last_now is not None else 0.0

    def _request(self, request_id, operation):
        if not isinstance(request_id, str) or not 16 <= len(request_id) <= 64:
            raise ValueError("INVALID_REQUEST_ID")
        if request_id in self._requests:
            if self._requests[request_id] != operation:
                raise ValueError("REQUEST_ID_REUSED_WITH_DIFFERENT_PAYLOAD")
            return False
        if len(self._requests) >= 128:
            raise ValueError("REQUEST_LEDGER_FULL_NEW_ACTION_REQUIRED")
        self._requests[request_id] = operation
        return True

    async def start(self, request_id, *, approach_pose):
        pose = Pose.model_validate(approach_pose).model_dump()
        async with self._lock:
            operation = ("start", tuple(pose.items()))
            if not self._request(request_id, operation):
                return self.snapshot()
            if self.state.phase != "NEW":
                raise ValueError("ACTION_ALREADY_STARTED_OR_RETIRED")
            if not self.activation.report(self.action)["enabled"]:
                raise ValueError("NATIVE_BINDING_OR_CAPABILITY_UNCONNECTED")
            self.policy.validate()
            if self.action.type == "TRAFFIC_STOP_AND_GO" and self.action.exit_pose is None:
                raise ValueError("EXIT_POSE_REQUIRED")
            if self.action.type == "PARK_SIT_HOLD" and self.posture is None:
                raise ValueError("POSTURE_PORT_UNCONNECTED")
            if self.action.type == "TRAVERSE_TERRAIN" and self.terrain is None:
                raise ValueError("TERRAIN_PORT_UNCONNECTED")
            self.normalizer = Normalizer(self.scope, self.policy, self.bindings,
                                         synthetic=self.activation.synthetic, receiver_session_id=self.receiver_session_id, receiver_clock_id=self.receiver_clock_id)
            self.state = ActionState(phase="APPROACH", reason="APPROACH_DISPATCH",
                                     started_s=self._now())
            try:
                await self._dispatch("approach", pose)
            except BaseException:
                await self._fail("GOAL_SUBMISSION_UNCERTAIN")
                raise
            return self.snapshot()

    async def _dispatch(self, leg, pose):
        # Dispatch intent is consumed before awaiting: ambiguous sends never retry.
        key = (self.scope.goal_generation, "dispatch", leg)
        if key in self._effects:
            return
        self._effects.add(key)
        self._goal_request_id = secrets.token_hex(16)
        self._goal_requested_s = self._now()
        self._goal_ack_s = None
        receipt = await self.navigation.dispatch(self.scope, leg=leg, pose=pose,
                                                  request_id=self._goal_request_id)
        if (not isinstance(receipt, GoalReceipt) or receipt.scope != self.scope
                or receipt.accepted is not True or not receipt.actual_goal_id):
            raise ValueError("GOAL_RECEIPT_SCOPE_MISMATCH")
        self._goal = receipt
        if receipt.acknowledged is True:
            self._goal_ack_s = self._now()
        if self._stop_requested:
            raise ValueError("STOP_REQUESTED_DURING_DISPATCH")

    async def _constrain(self, mode, reason):
        if self._constraint and self._constraint.scope == self.scope and self._constraint.mode == mode:
            if self._constraint_error:
                raise ValueError("CONSTRAINT_OUTCOME_UNCONFIRMED")
            return
        self._constraint_sequence += 1
        request = ConstraintRequest(self.scope, secrets.token_hex(16), mode, reason,
                                    self.policy.command_ttl_s, self._constraint_sequence)
        self._constraint, self._constraint_ack = request, None
        self._constraint_ack_s = None
        self._constraint_requested_s = self._cleanup_time() if mode == "HOLD" else self._now()
        self._constraint_error = False
        try:
            ack = await self.constraints.apply(request)
        except BaseException:
            if self._constraint is request:
                self._constraint_error = True
            raise
        if self._constraint is not request:
            raise ValueError("CONSTRAINT_SUPERSEDED_BY_STOP")
        self._constraint_ack = ack
        if self._valid_ack():
            self._constraint_ack_s = self._cleanup_time() if mode == "HOLD" else self._now()
        if mode == "RELEASE" and ack is not None and not self._valid_ack():
            raise ValueError("RELEASE_ACK_MISMATCH")

    def _valid_ack(self):
        return (self._constraint is not None and isinstance(self._constraint_ack, ConstraintAck)
                and self._constraint_ack.matches(self._constraint))

    async def _cancel(self):
        if self.scope.goal_generation in self._cancel_errors:
            raise ValueError("CANCEL_OUTCOME_UNCONFIRMED")
        if self.scope.goal_generation in self._cancelled_generations:
            return
        self._cancelled_generations.add(self.scope.goal_generation)
        # Port retains exact actual goal ownership, including uncertain dispatch.
        self._cancel_request_id = secrets.token_hex(16)
        self._cancel_requested_s = self._cleanup_time()
        ports = [self.navigation]
        if (self.scope.goal_generation, "TERRAIN") in self._effects:
            ports.append(self.terrain)
        if any((self.scope.goal_generation, kind) in self._effects for kind in ("SIT", "STAND")):
            ports.append(self.posture)
        failures = []
        for port in ports:
            try:
                await port.cancel(self.scope, request_id=self._cancel_request_id)
            except BaseException as exc:
                failures.append(exc)
        if failures:
            self._cancel_errors.add(self.scope.goal_generation)
            raise ValueError("EXECUTOR_CANCEL_UNCONFIRMED") from failures[0]

    async def _fail(self, reason, *, interrupted=False):
        self.state = replace(self.state, phase="INTERRUPTED" if interrupted else "FAILED",
                             reason=reason, dwell_start=None, last_valid_s=None, departed=False)
        if self.normalizer is not None:
            self.normalizer.invalidate()
        errors = []
        for operation in (lambda: self._constrain("HOLD", reason), self._cancel):
            try:
                await operation()
            except BaseException as exc:
                errors.append(type(exc).__name__)
        if not self._valid_ack() or self._constraint.mode != "HOLD":
            errors.append("HOLD_ACK_UNCONFIRMED")
        if errors:
            self.state = replace(self.state, reason=reason + ":CLEANUP_UNCONFIRMED:" + ",".join(errors))

    async def observe(self, packet=None):
        async with self._lock:
            if self.state.phase == "NEW" or self.normalizer is None:
                return self.snapshot()
            if self.state.phase in TERMINAL:
                return self.snapshot()
            try:
                now = self._now()
                if self._constraint is not None:
                    polled_ack = self.constraints.ack(self._constraint)
                    if polled_ack is not None:
                        self._constraint_ack = polled_ack
                        if self._valid_ack() and self._constraint_ack_s is None:
                            self._constraint_ack_s = now
                if self.state.phase == "EXIT_PREPARE":
                    if self._valid_ack():
                        await self._finish_exit()
                    elif now - self._constraint_requested_s > self.policy.command_ttl_s:
                        await self._fail("EXIT_HOLD_ACK_TIMEOUT")
                    return self.snapshot()
                frame = (self.normalizer.receive(packet, now) if packet is not None
                         else self.normalizer.current(now))
                decision = decide(self.state, self.action, frame, now=now,
                                  hold_ack=self._valid_ack() and self._constraint.mode == "HOLD",
                                  synthetic=self.activation.synthetic, hold_ack_s=self._constraint_ack_s,
                                  exit_ack_s=self._goal_ack_s,
                                  release_ack_s=(self._constraint_ack_s if self._valid_ack()
                                                 and self._constraint.mode == "RELEASE" else None))
                self.state = decision.state
                for effect in decision.effects:
                    await self._effect(effect)
            except ObservationRejected as exc:
                # Invalid packets never count toward dwell. If still holding,
                # another valid observation may restart dwell; moving fails closed.
                if self.state.phase in {"HOLD_ACK", "HOLD_SIGNAL", "PARK_HOLD"}:
                    self.state = replace(self.state, reason=str(exc), dwell_start=None, last_valid_s=None)
                    await self._constrain("HOLD", "INVALID_OBSERVATION")
                else:
                    await self._fail(str(exc))
            except BaseException:
                await self._fail("PORT_OR_CLOCK_FAILURE")
                raise
            return self.snapshot()

    async def _effect(self, effect):
        if self._stop_requested and effect not in {"HOLD", "CANCEL"}:
            raise ValueError("STOP_REQUESTED")
        if effect == "HOLD":
            await self._constrain("HOLD", self.state.reason)
        elif effect == "CANCEL":
            await self._cancel()
        elif effect in {"RELEASE", "RELEASE_TRACKING"}:
            if effect == "RELEASE_TRACKING" and self._constraint is None:
                return  # Approach must not be blocked by traffic HOLD.
            # Refresh age after awaited IO, immediately before a release.
            frame = self.normalizer.current(self._now())
            if frame is None or not frame.fresh("safety", "navigation", "pose", "path"):
                raise ValueError("RELEASE_INPUT_EXPIRED")
            if effect == "RELEASE" and not frame.fresh("signal"):
                raise ValueError("RELEASE_SIGNAL_EXPIRED")
            await self._constrain("RELEASE", self.state.reason)
        elif effect == "EXIT":
            self._exit_previous_scope = self.scope
            self.scope = replace(self.scope, goal_id=secrets.token_hex(16),
                                 goal_generation=self.scope.goal_generation + 1)
            self.normalizer.change_scope(self.scope)
            self._goal = None
            # Hold the NEW generation before dispatch; release on new-generation
            # observations on a later tick. Old GREEN/goal/commands cannot carry over.
            await self._constrain("HOLD", "EXIT_GENERATION_BARRIER")
            self.state = replace(self.state, phase="EXIT_PREPARE", reason="EXIT_HOLD_ACK_REQUIRED")
            if self._valid_ack():
                await self._finish_exit()
        elif effect in {"SIT", "STAND", "TERRAIN"}:
            key = (self.scope.goal_generation, effect)
            if key in self._effects:
                return
            self._effects.add(key)
            if effect == "TERRAIN":
                await self.terrain.begin(self.scope, segment=self.action.terrain_segment,
                                         profile=self.action.gait_profile, request_id=secrets.token_hex(16))
            else:
                await self.posture.request(self.scope, posture=effect, request_id=secrets.token_hex(16))

    async def _finish_exit(self):
        prepare = getattr(self.navigation, "prepare_exit", None)
        if prepare is not None:
            prepare(ExitAuthorization(self._exit_previous_scope, self.scope,
                                      self._constraint, self._constraint_ack))
        await self._dispatch("exit", self.action.exit_pose.model_dump())
        self.state = replace(self.state, phase="EXIT_PENDING", reason="EXIT_GOAL_DISPATCHED")

    async def tick(self):
        """Call from the existing owner loop; no new receipt or sequence."""
        return await self.observe()

    async def event_ack(self, event: ActionEvent):
        """Correlated ACK ingress. A duplicate is inert, never renewed freshness."""
        async with self._lock:
            if self.state.phase in TERMINAL or self.state.phase == "NEW":
                return {"accepted": False, "reason": "ACTION_INACTIVE", "snapshot": self.snapshot()}
            if (isinstance(event, ActionEvent) and type(event.sequence) is int
                    and event == self._events.get(event.sequence)):
                return {"accepted": False, "reason": "DUPLICATE_ACK", "snapshot": self.snapshot()}
            try:
                now = self._now()
                binding = self.event_binding
                if not isinstance(event, ActionEvent) or binding is None:
                    raise ValueError("EVENT_BINDING_REQUIRED")
                expected_goal = self._goal.actual_goal_id if self._goal else ""
                if (event.scope != self.scope or event.actual_goal_id != expected_goal
                        or event.producer_id != binding.producer_id or event.epoch != binding.epoch
                        or event.receiver_session_id != self.receiver_session_id
                        or event.receiver_clock_id != self.receiver_clock_id):
                    raise ValueError("EVENT_OWNER_EPOCH_OR_GENERATION_MISMATCH")
                if len(self._events) >= 128:
                    raise ValueError("EVENT_LEDGER_FULL_NEW_ACTION_REQUIRED")
                if (type(event.sequence) is not int or event.sequence <= self._event_sequence
                        or type(event.cancel_ack) is not bool
                        or any(type(v) not in (int, float) or not math.isfinite(v)
                               for v in (event.first_received_s, event.source_age_s))
                        or event.source_age_s < 0
                        or not 0 <= now - event.first_received_s <= self.policy.command_ttl_s
                        or not 0 <= event.source_age_s + now - event.first_received_s <= self.policy.command_ttl_s):
                    raise ValueError("EVENT_REPEATED_OR_EXPIRED")
                supported = event.first_received_s - event.source_age_s
                if event.kind == "APPROACH_TERMINAL":
                    if self.state.phase not in {"APPROACH", "WAIT_CANCEL"}:
                        raise ValueError("APPROACH_EVENT_PHASE_MISMATCH")
                    cancel = event.status == "CANCELED"
                    expected_id = self._cancel_request_id if cancel else self._goal_request_id
                    requested = self._cancel_requested_s if cancel else self._goal_requested_s
                    if (event.status not in {"SUCCEEDED", "CANCELED", "FAILED"}
                            or expected_id is None or event.request_id != expected_id
                            or requested is None or supported <= requested):
                        raise ValueError("APPROACH_REQUEST_ACK_MISMATCH")
                    if cancel and not event.cancel_ack:
                        self._event_sequence = event.sequence
                        self._events[event.sequence] = event
                        return {"accepted": False, "reason": "CANCEL_ACK_PENDING", "snapshot": self.snapshot()}
                    if event.status == "FAILED":
                        await self._fail("NAVIGATION_PROGRESS_FAILED")
                    elif self.action.type in {"TRAFFIC_STOP_AND_GO", "PARK_SIT_HOLD"}:
                        self.state = replace(self.state, phase="HOLD_ACK", reason="APPROACH_TERMINAL_EVENT")
                        await self._constrain("HOLD", self.state.reason)
                    else:
                        raise ValueError("TERMINAL_EVENT_REQUIRES_TRAFFIC_OR_PARK_ACTION")
                elif event.kind == "EXIT_ACK":
                    if (self.state.phase not in {"EXIT_PENDING", "DEPARTING"}
                            or event.request_id != self._goal_request_id or event.status != "ACTIVE"
                            or supported <= self._goal_requested_s):
                        raise ValueError("EXIT_REQUEST_ACK_MISMATCH")
                    if self._goal_ack_s is None:
                        self._goal_ack_s = event.first_received_s
                elif event.kind in {"HOLD_ACK", "RELEASE_ACK"}:
                    mode = event.kind.removesuffix("_ACK")
                    request = self._constraint
                    if (request is None or request.mode != mode or event.request_id != request.request_id
                            or event.status != "ACKNOWLEDGED" or supported <= self._constraint_requested_s):
                        raise ValueError("CONSTRAINT_REQUEST_ACK_MISMATCH")
                    self._constraint_ack = ConstraintAck(self.scope, event.request_id, mode, True)
                    if self._constraint_ack_s is None:
                        self._constraint_ack_s = event.first_received_s
                else:
                    raise ValueError("UNSUPPORTED_ACTION_EVENT")
                self._event_sequence = event.sequence
                self._events[event.sequence] = event
                return {"accepted": True, "reason": "ACK_ACCEPTED", "snapshot": self.snapshot()}
            except (ValueError, TypeError, AttributeError) as exc:
                await self._fail("ACK_REJECTED:" + str(exc))
                return {"accepted": False, "reason": str(exc), "snapshot": self.snapshot()}
            except BaseException:
                await self._fail("ACK_PORT_FAILURE")
                raise

    async def close(self, request_id):
        """Explicit shutdown; pending/uncertain cleanup cannot auto-resume."""
        return await self.stop(request_id, restart=True)

    async def stop(self, request_id, *, restart=False):
        # Fence intent immediately, before waiting behind an in-flight dispatch.
        # ConstraintPort must reject out-of-order request.sequence atomically.
        if not self._request(request_id, ("stop", restart)):
            return self.snapshot()
        self._stop_requested = True
        if self.state.phase != "NEW":
            try:
                await self._constrain("HOLD", "STOP_REQUESTED")
            except BaseException:
                pass  # _fail reports unconfirmed HOLD and still attempts cancel.
        async with self._lock:
            if self.state.phase == "NEW":
                self.state = replace(self.state, phase="INTERRUPTED", reason="RETIRED_BEFORE_START")
            else:
                await self._fail("SERVER_RESTART" if restart else "CANCELED", interrupted=True)
            return self.snapshot()

    async def reconnect(self, request_id):
        # No GREEN/dwell/goal/constraint restore. Require fresh run identity and
        # producer epochs in a new adapter; request histories are never resumed.
        return await self.stop(request_id, restart=True)

    async def prepare_movement(self, request_id):
        async with self._lock:
            if not self._request(request_id, ("stand",)):
                return self.snapshot()
            if self.action.type != "PARK_SIT_HOLD" or self.state.phase != "SUCCEEDED":
                raise ValueError("COMPLETED_PARK_REQUIRED")
            self.state = replace(self.state, phase="RISE_WAIT", started_s=self._now(),
                                 dwell_start=None, last_valid_s=None)
            try:
                await self._effect("STAND")
            except BaseException:
                await self._fail("POSTURE_REQUEST_UNCERTAIN")
                raise
            return self.snapshot()
