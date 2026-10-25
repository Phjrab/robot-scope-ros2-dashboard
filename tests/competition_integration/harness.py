"""Real D0/C4 pipeline, C2 state/ports, service ledger and MissionCoordinator.

Only RGB detector, clocks, map/navigation/planner/actuator boundaries are fake.
These tests are software evidence and never claim sensor/physical qualification.
"""
import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from competition_traffic import optional_deps  # noqa: F401
from competition_traffic.helpers import config, frame, lamp, Detector
from competition_native.helpers import Rig, POSE, ALL_CAPS
from competition_native.test_coordinator import Navigation, SavedMaps
from robot_dashboard.application.mission_coordinator import MissionCoordinator, MissionConflict
from robot_dashboard.competition_traffic.pipeline import TrafficPipeline
from robot_dashboard.competition_traffic.worker import TrafficWorker
from robot_dashboard.mission_routes.service import MissionRoutes
from robot_dashboard.mission_routes.competition_native.contracts import Activation, TimingPolicy
from robot_dashboard.mission_routes.competition_native.coordinator import LegBinding
from robot_dashboard.mission_routes.competition_native.authority import Command
from robot_dashboard.mission_routes.competition_native.observations import Extras


class SoftwareHarness:
    source_clock = "fixture"
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.lock = asyncio.Lock()
        self.nav = Navigation(self.lock)
        self.coordinator = MissionCoordinator(self.nav, SavedMaps(), self.root/'missions',
            coordination_lock=self.lock, poll_interval_s=.05, cancel_timeout_s=.1)
        self.service = MissionRoutes(self.root/'plans', SavedMaps(), None, self.coordinator,
                                     SimpleNamespace(snapshot=lambda: {}), None)
        # Explicit isolated planner boundary; no native availability is asserted.
        self.preflights = []
        async def preflight(mission):
            self.preflights.append(mission['current_index'])
        self.coordinator._dispatch_preflight = preflight
        self.visits = ('1'*32, '2'*32)
        result = await self.coordinator.create(label='Synthetic native traffic',
            map_id='a'*24, map_revision='b'*64, annotation_revision='c'*64,
            context_revision='d'*64, waypoints=[{'visit_id': v, 'label': 'Leg',
                'mission_local_pose': POSE} for v in self.visits])
        self.rig = Rig()
        self.clock = self.rig.clock
        scope = replace(self.rig.scope, mission_run_id=result['mission']['id'])
        action = self.rig.adapter.action.model_dump()
        action.update(signal_id='signal_01', crossing_id='crossing_01', timeout_seconds=300.)
        bindings = dict(self.rig.bindings)
        bindings['signal'] = replace(bindings['signal'], producer_id='camera-1', source_clock=self.source_clock)
        self.cfg = config()
        self.worker = TrafficWorker(TrafficPipeline(self.cfg, Detector(), clock=self.clock), clock=self.clock)
        self.worker.start()
        self.session = await self.service.create_software_native_session(scope=scope, action=action,
            legs={(scope.step_id, leg): LegBinding(v, tuple(POSE.values()))
                  for leg, v in zip(('approach', 'exit'), self.visits)},
            policy=TimingPolicy(.25, .25, .25, .25), bindings=bindings,
            activation=Activation(True, True, 'isolated-test-ports', 'synthetic-only', ALL_CAPS),
            clock=self.clock, traffic_config_hash=self.cfg.sha256, worker=self.worker)
        if self.source_clock != 'fixture':
            from robot_dashboard.mission_routes.competition_native.fragments import SignalBinding
            self.session.ingress.signal_binding = SignalBinding('camera-1', 'epoch-1', self.source_clock,
                self.cfg.sha256, self.cfg.document['association']['binding_id'],
                self.cfg.document['model']['sha256'], 'signal_01', 'crossing_01',
                self.session.adapter.receiver_clock_id)
        self.rig.adapter = self.session.adapter
        self.number = 0
        self.command_seq = 0
        await self.session.start('native-start-00000001', approach_pose=POSE)

    async def asyncTearDown(self):
        self.nav.cancel_ack = True
        await self.service.close()
        await self.coordinator.close()
        self.temp.cleanup()

    async def tick(self, *, color='GREEN', advance=.1, source_advance_ns=None, **fields):
        self.clock.now = round(self.clock.now + advance, 6)
        self.number += 1
        rgb = lamp((0, 230, 0) if color == 'GREEN' else (0, 0, 230) if color == 'RED' else (0, 0, 0))
        f = frame(self.number, image=rgb, received_s=self.clock.now,
                  source_stamp_ns=str(round(self.clock.now*1e9)), source_clock=self.source_clock)
        self.worker.offer(f)
        await self.worker.queue.join()
        packet = self.rig.packet(**fields)
        observed = self.session.port.goal_observation(self.session.adapter.scope)
        packet = replace(packet, evidence={**packet.evidence, **observed})
        if source_advance_ns is not None:
            stamps = dict(packet.components)
            for name in ('feet', 'motion'):
                previous = self.session.adapter.normalizer.received[name].stamp
                stamps[name] = replace(stamps[name], source_stamp_ns=str(int(previous.source_stamp_ns) + source_advance_ns))
            packet = replace(packet, components=stamps)
        self.last_packet = packet
        self.last_sample = self.worker.latest
        return await self.session.observe(f'native-event-{self.number:08}', packet, sample=self.last_sample)

    def command(self):
        self.command_seq += 1
        return self.session.command(Command(self.session.adapter.scope, self.command_seq,
                                            self.clock.now, (.2, 0., 0.)))

    async def terminal(self, *, canceled=False):
        if canceled:
            await self.tick()  # two feet INSIDE requests actual coordinator pause/cancel
            self.assertEqual(self.session.adapter.state.phase, 'WAIT_CANCEL')
            self.assertEqual(self.nav.goal['state'], 'canceled')
        else:
            self.nav.goal['state'] = 'succeeded'
            for _ in range(30):
                if self.coordinator.snapshot(self.session.adapter.scope.mission_run_id)['mission']['phase'] == 'native_barrier':
                    break
                await asyncio.sleep(.01)
        await self.tick()
        self.assertEqual(self.session.adapter.state.phase, 'HOLD_ACK')
        await self.tick()
        self.assertEqual(self.session.adapter.state.phase, 'HOLD_SIGNAL')

    async def exit_ready(self, *, canceled=False):
        await self.terminal(canceled=canceled)
        for _ in range(23):
            await self.tick()
            if self.session.adapter.state.phase == 'EXIT_PENDING':
                break
        self.assertEqual(self.session.adapter.state.phase, 'EXIT_PENDING')
        self.assertEqual(len(self.nav.sent), 2)
        self.assertEqual(self.preflights, [0, 1])

    def assertEqual(self, actual, expected):
        assert actual == expected, (actual, expected)
