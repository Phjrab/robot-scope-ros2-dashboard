"""Small explicit owner-loop API. Construction never calls ports or schedules work."""
from dataclasses import dataclass, replace
from typing import Mapping

from .adapter import NativeActionAdapter
from .contracts import Activation, EventBinding, Scope, TimingPolicy
from .observations import ClockBinding


@dataclass(frozen=True)
class RuntimeConfig:
    action: Mapping
    scope: Scope
    policy: TimingPolicy
    observation_bindings: Mapping[str, ClockBinding]
    event_binding: EventBinding
    receiver_clock_id: str
    activation: Activation = Activation()


@dataclass(frozen=True)
class RuntimePorts:
    navigation: object
    constraints: object
    posture: object = None
    terrain: object = None


class NativeRuntime:
    """No second FSM; delegates to the existing single-action adapter.

    C1 owns serialization, durable request ledger, authentication and loop cadence.
    Offline calls never require physical capability qualification. Live start is
    unavailable here until C1 supplies/reviews a real final-consumer integration.
    """
    def __init__(self, config: RuntimeConfig, ports: RuntimePorts, *, clock):
        if not isinstance(config.receiver_clock_id, str) or not config.receiver_clock_id:
            raise ValueError("RECEIVER_CLOCK_ID_REQUIRED")
        if not isinstance(config.event_binding, EventBinding):
            raise ValueError("EVENT_BINDING_REQUIRED")
        config.policy.validate()
        if config.policy.receiver_ttl_s > .25 or config.policy.source_max_age_s > .25:
            raise ValueError("RUNTIME_OBSERVATION_TTL_EXCEEDS_BOUND")
        self.config = config
        self.adapter = NativeActionAdapter(action=dict(config.action), scope=config.scope,
            policy=config.policy, bindings=dict(config.observation_bindings),
            activation=config.activation, navigation=ports.navigation, constraints=ports.constraints,
            posture=ports.posture, terrain=ports.terrain, clock=clock,
            event_binding=config.event_binding, receiver_clock_id=config.receiver_clock_id)

    @property
    def scope(self):
        return self.adapter.scope

    def continuation_proven(self, *, starting=False, completed=False):
        return self.adapter.continuation_proven(starting=starting, completed=completed)

    def require_dispatch_authorized(self, *, starting=False):
        """C1 calls at the END of existing awaited preflight, under its lock."""
        if not self.continuation_proven(starting=starting):
            raise ValueError("NATIVE_DISPATCH_NOT_PROVEN")

    def command_context(self):
        return self.adapter.command_context()

    def snapshot(self):
        return {**self.adapter.snapshot(), "live_ready": False,
                "execution_mode": "OFFLINE_CONTRACT" if self.config.activation.synthetic else "UNCONNECTED"}

    async def start(self, request_id: str, *, approach_pose: dict):
        if not self.config.activation.synthetic:
            raise ValueError("LIVE_FINAL_CONSUMER_BINDING_UNCONNECTED")
        await self.adapter.start(request_id, approach_pose=approach_pose)
        return self.snapshot()

    async def receive(self, packet):
        await self.adapter.observe(packet)
        return self.snapshot()

    async def event_ack(self, event):
        result = await self.adapter.event_ack(event)
        return {**result, "snapshot": self.snapshot()}

    async def tick(self):
        await self.adapter.tick()
        return self.snapshot()

    async def stop(self, request_id: str):
        await self.adapter.stop(request_id)
        return self.snapshot()

    async def cleanup(self, request_id: str):
        await self.adapter.close(request_id)
        return self.snapshot()

    async def prepare_movement(self, request_id: str):
        await self.adapter.prepare_movement(request_id)
        return self.snapshot()


def configure_action(config: RuntimeConfig, ports: RuntimePorts, *, clock) -> NativeRuntime:
    return NativeRuntime(config, ports, clock=clock)


def offline_config(config: RuntimeConfig) -> RuntimeConfig:
    """Explicit test-only execution label; never upgrades a real capability."""
    return replace(config, activation=replace(config.activation, synthetic=True))
