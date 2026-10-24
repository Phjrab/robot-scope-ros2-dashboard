"""Opt-in software integration using the existing durable service and coordinator.

No production registration, ROS subscription, camera opening or actuator output.
A future live binding must qualify the final consumer; this session rejects live
activation rather than making synthetic port injection a motion capability.
"""
from __future__ import annotations

import copy
import asyncio
from dataclasses import asdict, replace
import secrets

from .adapter import NativeActionAdapter
from .authority import CommandBoundary
from .contracts import ConstraintAck, ConstraintRequest
from .coordinator import CoordinatorNavigationPort
from .ingress import CompetitionIngress
from .state import TERMINAL


class SessionGate:
    """One software command consumer; old generations/late ACKs cannot reopen it."""
    def __init__(self, scope, clock):
        self.boundary = CommandBoundary(scope)
        self.clock = clock
        self.closed = False
        self.requests = {}

    async def apply(self, request):
        if self.closed:
            return None
        if request.scope != self.boundary.scope:
            old = self.boundary.scope
            if (replace(request.scope, goal_id=old.goal_id, goal_generation=old.goal_generation) != old
                    or request.scope.goal_generation != old.goal_generation + 1
                    or request.mode != 'HOLD'):
                self.retire()
                return None
            self.boundary.retire()
            self.boundary = CommandBoundary(request.scope)
            self.requests.clear()
        if len(self.requests) >= 128 and request.request_id not in self.requests:
            self.retire()
            return None
        if self.boundary.apply_constraint('mission', request, self.clock()):
            self.requests[request.request_id] = request
            return self.ack(request)
        self.retire()
        return None

    def ack(self, request):
        if (not self.closed and not self.boundary.retired
                and self.requests.get(request.request_id) == request
                and self.boundary.scope == request.scope
                and self.boundary.owner_sequences.get('mission') == request.sequence):
            return ConstraintAck(request.scope, request.request_id, request.mode, True)
        return None

    def retire(self):
        self.closed = True
        self.boundary.retire()


class SoftwareNativeSession:
    @classmethod
    async def create(cls, service, *, scope, action, legs, policy, bindings,
                     activation, clock, traffic_config_hash, worker=None):
        if not activation.synthetic or not activation.enabled:
            raise ValueError('EXPLICIT_SOFTWARE_TEST_ACTIVATION_REQUIRED')
        self = cls()
        self.service, self.clock, self.worker = service, clock, worker
        self.token = object()
        self.gate = SessionGate(scope, clock)
        self.port = CoordinatorNavigationPort(service.coordinator, service.coordinator._navigation,
            mission_id=scope.mission_run_id, admission=service._admission, legs=legs,
            native_owner=self.token)
        self.adapter = NativeActionAdapter(scope=scope, action=action, navigation=self.port,
            constraints=self.gate, policy=policy, bindings=bindings, activation=activation, clock=clock)
        self.ingress = CompetitionIngress(self.adapter, traffic_config_hash=traffic_config_hash)
        self.closed = False
        self._operation_lock = asyncio.Lock()
        self.proof = None
        if self.adapter.action.type != 'TRAFFIC_STOP_AND_GO':
            raise ValueError('SOFTWARE_INTEGRATION_SUPPORTS_TRAFFIC_ONLY')
        if not activation.report(self.adapter.action)['enabled']:
            raise ValueError('COMPLETE_SOFTWARE_PORT_CONTRACT_REQUIRED')
        mission = service.coordinator.snapshot(scope.mission_run_id)['mission']
        if len(mission['waypoints']) != 2 or any(
                tuple(point['mission_local_pose'][key] for key in ('x', 'y', 'yaw')) !=
                legs[(scope.step_id, leg)].pose
                for point, leg in zip(mission['waypoints'], ('approach', 'exit'))):
            raise ValueError('COMPILED_LEG_BINDING_MISMATCH')
        await service.coordinator.bind_native_owner(scope.mission_run_id,
            admission=service._admission, token=self.token,
            visits=[legs[(scope.step_id, name)].visit_id for name in ('approach', 'exit')],
            guard=self._continuation_proven)
        return self

    def _continuation_proven(self, *, completed=False, starting=False):
        a = self.adapter
        if starting:
            return not self.closed and not a._stop_requested and a.state.phase == 'APPROACH'
        if completed:
            frame = a.normalizer.current(self.clock()) if a.normalizer else None
            return (not self.closed and not a._stop_requested and a.state.phase == 'SUCCEEDED'
                    and a.state.departed and frame is not None
                    and frame.fresh('navigation', 'safety') and a._valid_ack()
                    and a._constraint.mode == 'HOLD'
                    and frame.evidence.goal_state == 'SUCCEEDED'
                    and not frame.extras.estop and not frame.extras.collision)
        if (self.closed or a._stop_requested or a.state.phase != 'EXIT_PENDING'
                or not a._valid_ack() or a._constraint.mode != 'HOLD'
                or self.proof is None):
            return False
        frame = replace(self.proof, now=self.clock())
        return (frame.fresh('safety', 'feet', 'motion', 'signal', 'pose', 'path')
                and not frame.extras.estop and not frame.extras.collision
                and a.scope.goal_generation == frame.evidence.goal_generation + 1)

    async def start(self, request_id, *, approach_pose):
        async def operation():
            async with self._operation_lock:
                if self.closed:
                    raise ValueError('SESSION_RETIRED')
                return await self.adapter.start(request_id, approach_pose=approach_pose)
        return await self.service._transaction(request_id,
            {'native': self.adapter.scope.mission_run_id, 'start': approach_pose}, operation)

    async def observe(self, request_id, packet=None, *, sample=None):
        # Freeze ingress before any await; durable CAS describes these exact inputs.
        packet = copy.deepcopy(packet)
        try:
            if sample is not None:
                if packet is None:
                    raise ValueError('INDEPENDENT_COMPONENT_EVIDENCE_REQUIRED')
                packet = self.ingress.join(packet, sample, now=self.clock())
        except BaseException:
            self.gate.retire()
            raise
        payload = {'native': self.adapter.scope.mission_run_id,
                   'event': asdict(packet) if packet is not None else None}
        async def apply_event():
            if self.closed:
                raise ValueError('SESSION_RETIRED')
            # C2 changes generation before EXIT dispatch. Preserve the previous
            # validated source-supported frame for the atomic owner guard.
            if packet is not None:
                normalizer = self.adapter.normalizer
                if normalizer is not None:
                    # Preview on a copy: the real adapter remains the sole receiver
                    # and state transition owner; this does not refresh receipts.
                    preview = copy.deepcopy(normalizer)
                    self.proof = preview.receive(packet, self.clock())
            else:
                self.proof = self.adapter.normalizer.current(self.clock()) if self.adapter.normalizer else None
            result = await self.adapter.observe(packet)
            if self.adapter.state.phase == 'SUCCEEDED':
                await self.service.coordinator.finish_native(self.adapter.scope.mission_run_id,
                    admission=self.service._admission, token=self.token,
                    actual_goal_id=self.adapter._goal.actual_goal_id)
            if self.adapter.state.phase in TERMINAL:
                self.gate.retire()
            elif (self.adapter.state.phase == 'APPROACH' and self.adapter._constraint is None
                  and self.adapter.state.reason == 'NAVIGATION_ACTIVE'):
                await self.gate.apply(ConstraintRequest(self.adapter.scope, 'approach-tracking',
                                                       'RELEASE', 'TRACKING', sequence=0))
            return result
        async def operation():
            async with self._operation_lock:
                return await apply_event()
        try:
            return await self.service._transaction(request_id, payload, operation)
        except BaseException:
            # Ledger/input/IO uncertainty can never leave the software consumer open.
            self.gate.retire()
            raise

    def command(self, command):
        a = self.adapter
        try:
            frame = a.normalizer.current(self.clock()) if a.normalizer else None
            observed = self.port.goal_observation(a.scope)
            mission = self.service.coordinator.snapshot(a.scope.mission_run_id)['mission']
            owned = (observed['goal_state'] == 'ACTIVE' and mission['state'] == 'running'
                     and mission['ownership_active']
                     and a.scope.mission_run_id not in self.service.coordinator._stop_requests)
        except ValueError:
            frame, owned = None, False
            self.gate.retire()
        fresh = frame is not None and frame.fresh('safety', 'navigation', 'pose', 'path')
        if fresh:
            fresh = (frame.evidence.pose is not None and frame.evidence.path_clear
                     and frame.evidence.obstacle_state in {'FOLLOWING', 'GOAL_REACHED'})
        if fresh and a.state.phase in {'EXIT_PENDING', 'DEPARTING'} and not a.state.departed:
            fresh = (frame.fresh('signal', 'motion') and frame.evidence.raw_state == 'GREEN'
                     and frame.evidence.stable_state == 'GREEN' and not frame.evidence.quality_flags)
        goal_receipt = frame.components['navigation'].receipt_s if fresh else None
        return self.gate.boundary.evaluate(command, now=self.clock(),
            estop=bool(frame and frame.extras.estop), collision=bool(frame and frame.extras.collision),
            inputs_fresh=fresh and owned, goal_scope=a.scope if owned else None,
            goal_receipt_s=goal_receipt)

    async def stop(self, request_id, *, restart=False):
        self.closed = True
        self.gate.retire()  # Immediate, even while durable IO/dispatch is awaiting.
        self.service.coordinator.fence_native_stop(self.adapter.scope.mission_run_id, token=self.token)
        async def operation():
            try:
                return await self.adapter.stop(request_id, restart=restart)
            finally:
                if self.worker is not None:
                    await self.worker.close()
        return await self.service._transaction(request_id,
            {'native': self.adapter.scope.mission_run_id, 'stop': True, 'restart': restart},
            operation, safety=True)

    async def close(self):
        return await self.stop(secrets.token_hex(16), restart=True)
