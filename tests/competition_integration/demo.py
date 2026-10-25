"""Dedicated localhost fixture only. Simulation facts never claim robot evidence."""
import asyncio
import secrets
from dataclasses import asdict

from competition_integration.harness import SoftwareHarness
from robot_dashboard.mission_routes.competition_native.observations import Extras
from robot_dashboard.mission_routes.competition_native.state import TERMINAL


class SignalDemo:
    def __init__(self):
        self.harness = None
        self.task = None
        self.scenario = None
        self.trace = []
        self.planning = False
        self.release_plan = asyncio.Event()
        self.requests = {}
        self.lock = asyncio.Lock()
        self.error = None

    async def start(self, scenario, request_id):
        async with self.lock:
            if request_id in self.requests:
                if self.requests[request_id] != scenario:
                    raise ValueError('REQUEST_ID_PAYLOAD_CONFLICT')
                return self.snapshot()
            if scenario not in {'normal', 'red', 'unknown', 'delayed_plan'}:
                raise ValueError('UNKNOWN_SCENARIO')
            if len(self.requests) >= 32:
                raise ValueError('FIXTURE_HISTORY_FULL_RESTART_SERVER')
            if self.harness and self.harness.session.adapter.state.phase not in TERMINAL:
                raise ValueError('EXISTING_OFFLINE_RUN_ACTIVE')
            if self.harness:
                await self.harness.asyncTearDown()
            harness = SoftwareHarness()
            harness.source_clock = "synchronized_ros"  # verified virtual clock; still SYNTHETIC
            await harness.asyncSetUp()
            # A concurrent read must never see a partially initialized session.
            self.harness = harness
            self.scenario, self.trace, self.error = scenario, [], None
            self.requests[request_id] = scenario
            self.release_plan = asyncio.Event()
            async def preflight(mission):
                self.harness.preflights.append(mission['current_index'])
                if scenario == 'delayed_plan' and mission['current_index'] == 1:
                    self.planning = True
                    await self.release_plan.wait()
                    self.planning = False
            self.harness.coordinator._dispatch_preflight = preflight
            self.task = asyncio.create_task(self._drive())
            return self.snapshot()

    async def _drive(self):
        h = self.harness
        try:
            while h.session.adapter.state.phase not in TERMINAL and not h.session.closed:
                phase = h.session.adapter.state.phase
                fields = {}
                # The simulated navigation port completes approach; motion/feet
                # are supplied independently from image signal and constraint ACK.
                if phase == 'APPROACH' and h.clock.now >= .4:
                    h.nav.goal['state'] = 'succeeded'
                    await asyncio.sleep(.06)  # existing coordinator monitor consumes terminal
                if phase in {'EXIT_PENDING', 'DEPARTING'} and h.session.adapter._constraint.mode == 'RELEASE':
                    fields = {'body_motion_status': 'MOVING', 'extras': Extras(departure_observed=True)}
                if h.session.adapter.state.departed:
                    h.nav.goal['state'] = 'succeeded'
                color = {'red': 'RED', 'unknown': 'UNKNOWN'}.get(self.scenario, 'GREEN')
                await h.tick(color=color, front_left_status='OUTSIDE' if phase == 'APPROACH' else 'INSIDE',
                             front_right_status='OUTSIDE' if phase == 'APPROACH' else 'INSIDE', **fields)
                current = h.session.adapter.state.phase
                if not self.trace or self.trace[-1]['phase'] != current:
                    self.trace.append({'phase': current, 'time_s': h.clock.now,
                                       'goal_count': len(h.nav.sent), 'departed': h.session.adapter.state.departed})
                await asyncio.sleep(.1)
        except Exception as exc:
            if not h.session.closed:
                self.error = str(exc)
                await h.session.stop('demo-failure-' + secrets.token_hex(8))

    async def stop(self):
        if self.harness:
            # STOP must fence synchronously before the delayed planner is released.
            pending = asyncio.create_task(self.harness.session.stop('demo-stop-' + secrets.token_hex(8)))
            await asyncio.sleep(0)
            self.release_plan.set()
            await pending
            if self.task:
                await self.task
        return self.snapshot()

    def snapshot(self):
        result = {'mode': 'OFFLINE_SYNTHETIC', 'source': 'generated RGB + simulated independent sensors',
                  'actual_nav2_run': False, 'physical_motion': False, 'scenario': self.scenario,
                  'planning_delayed': self.planning, 'trace': self.trace, 'error': self.error}
        if not self.harness:
            return {**result, 'phase': 'NOT_STARTED', 'run_id': None, 'goal_count': 0}
        h, a = self.harness, self.harness.session.adapter
        frame = a.normalizer.current(h.clock()) if a.normalizer else None
        return {**result, 'phase': a.state.phase, 'reason': a.state.reason,
                'run_id': a.scope.mission_run_id, 'goal_count': len(h.nav.sent),
                'last_observation_s': h.clock.now if h.session.latest else None,
                'observation': frame.evidence.model_dump() if frame else None,
                'departed': a.state.departed, 'dwell_elapsed_s': max(0., (a.state.last_valid_s or 0.) - (a.state.dwell_start or 0.)),
                'request_count': len(h.service.data['requests']),
                'constraint': asdict(a._constraint) if a._constraint else None}

    async def close(self):
        await self.stop()
        if self.harness:
            await self.harness.asyncTearDown()
