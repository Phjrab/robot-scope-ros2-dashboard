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

from .runtime import NativeRuntime, RuntimeConfig, RuntimePorts
from .contracts import EventBinding, GoalReceipt, Scope
from ..models import digest
from ...application.mission_coordinator import MissionConflict
from collections import OrderedDict
from .authority import CommandBoundary
from .contracts import ConstraintAck, ConstraintRequest
from .coordinator import CoordinatorNavigationPort
from .ingress import CompetitionIngress
from .state import TERMINAL


class SessionGate:
    """One software command consumer; old generations/late ACKs cannot reopen it."""
    def __init__(self, scope, clock, service):
        self.boundary = CommandBoundary(scope)
        self.clock, self.service = clock, service
        self.closed = False
        self.requests = {}

    async def apply(self, request):
        async def install():
            ack = await self._install(request)
            return {'ack': asdict(ack) if ack else None}
        result = await self.service._transaction(request.request_id,
            {'constraint': asdict(request)}, install, safety=request.mode == 'HOLD')
        # A persisted receipt never installs or reopens a retired gate.
        return self.ack(request) if result['ack'] else None

    async def _install(self, request):
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


class DurableNavigation:
    """Journal each effect before the existing coordinator/port can submit it."""
    def __init__(self, service, port):
        self.service, self.port = service, port

    def __getattr__(self, name):
        return getattr(self.port, name)

    async def dispatch(self, scope, *, leg, pose, request_id):
        async def send():
            receipt = await self.port.dispatch(scope, leg=leg, pose=pose, request_id=request_id)
            return asdict(receipt)
        result = await self.service._transaction(request_id,
            {'goal': asdict(scope), 'leg': leg, 'pose': pose}, send)
        return GoalReceipt(Scope(**result['scope']), result['actual_goal_id'],
                           result['accepted'], result['acknowledged'])

    async def cancel(self, scope, *, request_id):
        async def cancel():
            await self.port.cancel(scope, request_id=request_id)
            return {'canceled': True}
        await self.service._transaction(request_id, {'cancel': asdict(scope)}, cancel, safety=True)


class SoftwareNativeSession:
    @classmethod
    async def create(cls, service, *, scope, action, legs, policy, bindings,
                     activation, clock, traffic_config_hash, worker=None, signal_binding=None):
        if not activation.synthetic or not activation.enabled:
            raise ValueError('EXPLICIT_SOFTWARE_TEST_ACTIVATION_REQUIRED')
        self = cls()
        self.service, self.clock, self.worker = service, clock, worker
        self.token = object()
        self.gate = SessionGate(scope, clock, service)
        self.port = CoordinatorNavigationPort(service.coordinator, service.coordinator._navigation,
            mission_id=scope.mission_run_id, admission=service._admission, legs=legs,
            native_owner=self.token)
        self.runtime = NativeRuntime(RuntimeConfig(action, scope, policy, bindings,
            EventBinding('software-coordinator', 'session-' + secrets.token_hex(8)),
            'same-host-' + secrets.token_hex(8), activation),
            RuntimePorts(DurableNavigation(service, self.port), self.gate), clock=clock)
        self.adapter = self.runtime.adapter
        self.ingress = CompetitionIngress(self.adapter, traffic_config_hash=traffic_config_hash, signal_binding=signal_binding)
        self.closed = False
        self._finished = False
        self._operation_lock = asyncio.Lock()
        self.latest = None
        self.observation_requests = OrderedDict()
        self.observation_count = 0
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
        return not self.closed and self.runtime.continuation_proven(
            completed=completed, starting=starting)

    async def start(self, request_id, *, approach_pose):
        async def operation():
            async with self._operation_lock:
                if self.closed:
                    raise ValueError('SESSION_RETIRED')
                return await self.runtime.start(request_id, approach_pose=approach_pose)
        return await self.service._transaction(request_id,
            {'native': self.adapter.scope.mission_run_id, 'start': approach_pose}, operation)

    async def observe(self, request_id, packet=None, *, sample=None):
        # Freeze bounded ingress before any await. Telemetry never enters the request ledger.
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
        fingerprint = digest(payload)
        async def apply_event():
            if self.closed:
                raise ValueError('SESSION_RETIRED')
            self.latest = packet if packet is not None else self.latest
            self.observation_count += 1
            result = await self.runtime.receive(packet) if packet is not None else await self.runtime.tick()
            if self.adapter.state.phase == 'SUCCEEDED' and not self._finished:
                await self.service.coordinator.finish_native(self.adapter.scope.mission_run_id,
                    admission=self.service._admission, token=self.token,
                    actual_goal_id=self.runtime.snapshot()['actual_goal_id'])
                self._finished = True
            if self.adapter.state.phase in TERMINAL:
                self.gate.retire()
            elif (self.adapter.state.phase == 'APPROACH' and result['pending']['constraint'] is None
                  and self.adapter.state.reason == 'NAVIGATION_ACTIVE'
                  and not self.gate.requests):
                await self.gate.apply(ConstraintRequest(self.adapter.scope,
                    'tracking-' + self.adapter.scope.mission_run_id, 'RELEASE', 'TRACKING', sequence=0))
            return result
        async def operation():
            nonlocal packet
            async with self._operation_lock:
                prior = self.observation_requests.get(request_id)
                if prior is not None and prior != fingerprint:
                    raise MissionConflict('REQUEST_ID_PAYLOAD_CONFLICT')
                # Only the last 64 transport IDs are cached. C2's bounded per-component
                # epoch/sequence high-water rejects older replay after cache eviction.
                self.observation_requests[request_id] = fingerprint
                self.observation_requests.move_to_end(request_id)
                if len(self.observation_requests) > 64:
                    self.observation_requests.popitem(last=False)
                if packet is not None and packet == self.latest:
                    packet = None  # exact duplicate is a health tick, no new receipt
                return await apply_event()
        try:
            return await operation()
        except BaseException:
            # Ledger/input/IO uncertainty can never leave the software consumer open.
            self.gate.retire()
            raise

    def command(self, command):
        context = self.runtime.command_context()
        try:
            observed = self.port.goal_observation(context.scope)
            mission = self.service.coordinator.snapshot(context.scope.mission_run_id)['mission']
            owned = (not self.closed and observed['goal_state'] == 'ACTIVE' and mission['state'] == 'running'
                     and mission['ownership_active']
                     and context.scope.mission_run_id not in self.service.coordinator._stop_requests)
        except ValueError:
            owned = False
            self.gate.retire()
        return self.gate.boundary.evaluate(command, now=self.clock(),
            estop=context.estop, collision=context.collision,
            inputs_fresh=context.inputs_fresh and owned, goal_scope=context.scope if owned else None,
            goal_receipt_s=context.goal_receipt_s)

    async def stop(self, request_id, *, restart=False):
        self.closed = True
        self.gate.retire()  # Immediate, even while durable IO/dispatch is awaiting.
        self.service.coordinator.fence_native_stop(self.adapter.scope.mission_run_id, token=self.token)
        async def operation():
            try:
                return await self.runtime.cleanup(request_id) if restart else await self.runtime.stop(request_id)
            finally:
                if self.worker is not None:
                    await self.worker.close()
        return await self.service._transaction(request_id,
            {'native': self.adapter.scope.mission_run_id, 'stop': True, 'restart': restart},
            operation, safety=True)

    async def close(self):
        return await self.stop(secrets.token_hex(16), restart=True)
