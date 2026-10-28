"""One-shot OPERATOR_TEST permission; never writes perception observations."""
from __future__ import annotations

import math


class OperatorTestGate:
    def __init__(self, health, clock):
        self.health, self.clock = health, clock
        self.binding = self._binding(self._proof())
        self.arrived_at = None
        self.stop_generation = 0
        self.releases = {}
        self.pending = None
        self.last_event = None
        self.invalidated = False

    @staticmethod
    def _binding(proof):
        return tuple(proof[k] for k in ('runtime_instance_generation', 'bundle_generation', 'localization_generation'))

    def _proof(self):
        health = self.health()
        proof = dict(health.get('operational_3d') or {})
        if (health.get('fresh') is not True or health.get('ready') is not True
                or proof.get('source') != 'STORED_PCD_FASTLIO' or proof.get('ready') is not True):
            raise ValueError('LIVE_3D_LOCALIZATION_REQUIRED')
        proof['runtime_instance_generation'] = health.get('runtime_instance_generation')
        if not proof['runtime_instance_generation']:
            raise ValueError('RUNTIME_GENERATION_REQUIRED')
        for key in ('linear_speed_mps', 'angular_speed_rps', 'stopped_seconds'):
            value = proof.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('MEASURED_STOP_EVIDENCE_REQUIRED')
        return proof

    def require_source(self):
        if self.invalidated:
            raise ValueError('OPERATOR_TEST_SOURCE_REAUTHORIZATION_REQUIRED')
        try:
            proof = self._proof()
            if self._binding(proof) != self.binding:
                raise ValueError('OPERATOR_TEST_SOURCE_GENERATION_CHANGED')
        except (ValueError, KeyError):
            self.invalidated = True
            self.pending = None
            raise
        return proof

    def arrived(self):
        self.stop_generation += 1
        self.arrived_at = self.clock()
        self.pending = None

    def stopped(self):
        proof = self.require_source()
        return bool(self.arrived_at is not None and self.clock() - self.arrived_at >= 2.
                    and proof['stopped_seconds'] >= 2.
                    and proof['linear_speed_mps'] <= .03 and proof['angular_speed_rps'] <= .05)

    def release(self, *, request_id, run_id, step_id, token):
        if not self.stopped():
            raise ValueError('MEASURED_STOP_DWELL_REQUIRED')
        now = self.clock()
        self.pending = {'source': 'OPERATOR_TEST', 'kind': 'GREEN_RELEASE_REQUEST',
            'completion_profile': 'NAV_STOP_POINT_TEST', 'request_id': request_id,
            'run_id': run_id, 'step_id': step_id, 'stop_id': step_id,
            'stop_generation': self.stop_generation, 'confirmation_token': token,
            'map_bundle_generation': self.binding[1], 'localization_generation': self.binding[2],
            'server_issued_at_monotonic': now, 'expires_at_monotonic': now + 2.,
            'departure': 'NOT_DISPATCHED'}
        self.last_event = self.pending.copy()
        self.releases[request_id] = self.last_event
        return self.last_event

    def require_dispatch(self, index):
        self.require_source()
        if index == 0:
            return
        if (self.pending is None or self.clock() > self.pending['expires_at_monotonic']
                or not self.stopped()):
            raise ValueError('CURRENT_OPERATOR_TEST_RELEASE_REQUIRED')

    def dispatched(self):
        if self.pending is not None:
            self.last_event['departure'] = 'GOAL_DISPATCHED'
        self.pending = None
        self.arrived_at = None

    def snapshot(self):
        try:
            ready = self.stopped()
            reason = '' if ready else 'WAITING_MEASURED_STOP_DWELL'
        except ValueError as exc:
            ready, reason = False, str(exc)
        return {'source': 'OPERATOR_TEST', 'completion_profile': 'NAV_STOP_POINT_TEST',
                'stop_generation': self.stop_generation, 'ready': ready, 'reason': reason,
                'last_event': self.last_event}
