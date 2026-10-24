from dataclasses import replace

from robot_dashboard.mission_routes.competition_contract import REQUIREMENTS
from robot_dashboard.mission_routes.competition_native import Activation, NativeActionAdapter, Scope, TimingPolicy
from robot_dashboard.mission_routes.competition_native.contracts import ConstraintAck, GoalReceipt
from robot_dashboard.mission_routes.competition_native.observations import ClockBinding, ComponentStamp, Extras, FIELDS, Packet

POSE = {"x": 1.0, "y": 2.0, "yaw": 0.0}
ALL_CAPS = frozenset(x for requirements in REQUIREMENTS.values() for x in requirements)


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class Ports:
    def __init__(self):
        self.calls = []
        self.drop_ack = False
        self.wrong_ack = False
        self.fail_goal = False
        self.fail_hold = False
        self.fail_cancel = False
        self.requests = {}

    async def dispatch(self, scope, *, leg, pose, request_id):
        self.calls.append(("goal", leg, scope.goal_generation))
        if self.fail_goal:
            raise RuntimeError("uncertain dispatch")
        return GoalReceipt(scope, "actual-navigation-goal-" + str(scope.goal_generation))

    async def cancel(self, scope, *, request_id):
        self.calls.append(("cancel", scope.goal_generation))
        if self.fail_cancel:
            raise RuntimeError("cancel uncertain")

    async def apply(self, request):
        self.calls.append((request.mode, request.scope.goal_generation))
        self.requests[request.request_id] = request
        if request.mode == "HOLD" and self.fail_hold:
            raise RuntimeError("hold uncertain")
        return self.ack(request)

    def ack(self, request):
        if self.drop_ack:
            return None
        scope = replace(request.scope, goal_generation=999) if self.wrong_ack else request.scope
        return ConstraintAck(scope, request.request_id, request.mode, True)

    async def request(self, scope, *, posture, request_id):
        self.calls.append((posture, scope.goal_generation))

    async def begin(self, scope, *, segment, profile, request_id):
        self.calls.append(("terrain", scope.goal_generation))


class Rig:
    def __init__(self, kind="TRAFFIC_STOP_AND_GO", *, activation=None, policy=None):
        self.clock, self.ports, self.seq = Clock(), Ports(), 0
        self.scope = Scope("native-test", "a" * 32, "b" * 32, "c" * 64, "d" * 32, 1)
        self.bindings = {name: ClockBinding("test-source", "epoch-1", "fixture", True)
                         for name in (*FIELDS, "envelope")}
        action = {"step_id": self.scope.step_id, "type": kind, "zone_id": "zone-1",
                  "signal_id": "signal-1", "crossing_id": "crossing-1",
                  "avoidance_profile": "profile-1", "terrain_segment": "terrain-1",
                  "gait_profile": "gait-1", "exit_pose": POSE, "timeout_seconds": 20.0}
        self.adapter = NativeActionAdapter(action=action, scope=self.scope,
            navigation=self.ports, constraints=self.ports, posture=self.ports, terrain=self.ports,
            policy=policy or TimingPolicy.synthetic(), bindings=self.bindings,
            activation=activation or Activation(True, True, "fake-ports", "synthetic-test", ALL_CAPS),
            clock=self.clock)

    async def start(self):
        return await self.adapter.start("start-request-0001", approach_pose=POSE)

    def packet(self, *, extras=None, **values):
        self.seq += 1
        scope = self.adapter.scope
        data = dict(schema_version="competition-evidence.v0.1", **vars(scope),
                    producer_id="test-source", producer_epoch="epoch-1", sequence=self.seq,
                    source_clock="fixture", source_stamp_ns=str(self.seq), source_age_s=0.0,
                    evidence_type="fixture", goal_state="ACTIVE", cancel_ack=False,
                    hold_ack=True, pose=POSE, path_clear=True,
                    signal_id="signal-1", crossing_id="crossing-1", zone_id="zone-1",
                    raw_state="GREEN", stable_state="GREEN", front_left_status="INSIDE",
                    front_right_status="INSIDE", feet_evidence_kind="SIM_GT",
                    body_motion_status="STOPPED")
        data.update(values)
        stamps = {name: ComponentStamp(scope, "test-source", "epoch-1", self.seq,
                                       str(self.seq), 0.0, "fixture") for name in FIELDS}
        return Packet(data, stamps, extras or Extras(), self.adapter.receiver_session_id)

    async def tick(self, time, **values):
        self.clock.now = time
        await self.adapter.observe(self.packet(**values))
        return self.adapter.state

    async def hold(self):
        await self.start()
        await self.tick(0.0, goal_state="SUCCEEDED")
        await self.tick(0.01, goal_state="SUCCEEDED")

    async def dwell(self, *, start=0.02, duration=2.0, **values):
        steps = int(duration / 0.25)
        for i in range(steps + 1):
            await self.tick(round(start + i * 0.25, 6), goal_state="SUCCEEDED", **values)
        return self.adapter.state
