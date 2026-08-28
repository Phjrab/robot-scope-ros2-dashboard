import assert from 'node:assert/strict';
import test from 'node:test';

import { createMissionClient } from '../robot_dashboard/static/features/cockpit/mission_client.js';

const ID = 'a'.repeat(32);

function mission(state = 'ready') {
  return { id: ID, label: 'Route', state, map_id: 'b'.repeat(24), map_revision: 'c'.repeat(64), annotation_revision: 'd'.repeat(64), current_index: 0, completed_count: 0, remaining_count: 1, elapsed_seconds: 0, ownership_active: state === 'running', waypoints: [{ annotation_id: 'e'.repeat(24), label: 'Home', status: state === 'running' ? 'running' : 'pending', hold_seconds: 0, requires_operator_confirmation: false, attempts: state === 'running' ? 1 : 0 }], logs: [] };
}

test('mission client restores server state, bounds projections, and releases polling demand', async () => {
  let interval; let cleared = 0; const calls = [];
  const client = createMissionClient({
    api: async (path) => { calls.push(path); return { available: true, active_mission_id: null, missions: [mission()] }; },
    setInterval(callback) { interval = callback; return 7; }, clearInterval() { cleared += 1; },
  });
  const states = []; const release = client.subscribe((state) => states.push(state));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(client.snapshot().selected.id, ID);
  assert.equal(client.snapshot().selected.waypoints.length, 1);
  assert.equal(calls[0], '/api/v1/missions');
  assert.equal(typeof interval, 'function');
  release();
  assert.equal(cleared, 1);
  assert.equal(client.diagnostics().subscribers, 0);
  client.destroy();
});

test('duplicate mission mutations serialize and never submit two starts', async () => {
  let resolveStart; let starts = 0; let serverMission = mission();
  const client = createMissionClient({ api: async (path) => {
    if (path === '/api/v1/missions') return { available: true, active_mission_id: serverMission.state === 'running' ? ID : null, missions: [serverMission] };
    starts += 1; await new Promise((resolve) => { resolveStart = resolve; }); serverMission = mission('running'); return { mission: serverMission };
  }, setInterval() { return 0; }, clearInterval() {} });
  const release = client.subscribe(() => {}); await new Promise((resolve) => setTimeout(resolve, 0));
  const first = client.start(ID); const duplicate = client.start(ID);
  assert.equal(await duplicate, null);
  resolveStart(); await first;
  assert.equal(starts, 1);
  assert.equal(client.snapshot().active.id, ID);
  release(); client.destroy();
});

test('destroy fences a late mission response', async () => {
  let resolveRequest;
  const client = createMissionClient({ api: () => new Promise((resolve) => { resolveRequest = resolve; }), setInterval() { return 0; }, clearInterval() {} });
  client.subscribe(() => {}); client.destroy(); resolveRequest({ available: true, missions: [mission()], active_mission_id: null });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(client.snapshot().selected, null);
  assert.equal(client.diagnostics().destroyed, true);
});
