import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

import { createCockpitNavigationAdapter } from '../robot_dashboard/static/features/cockpit/navigation_adapter.js';
import { createNavigationPanel } from '../robot_dashboard/static/features/cockpit/panels/navigation_panel.js';

const require = createRequire(import.meta.url);
const navigationEngine = require('../robot_dashboard/static/navigation.js');
const MAP_ID = 'a'.repeat(24); const REVISION = 'b'.repeat(64);

function input() {
  return {
    navigationEngine, navigationAvailable: true, operationBusy: false,
    navigation: { available: true, robot_online: true, pipeline: { state: 'idle' }, goal: { state: 'idle' }, safety: { can_start: true, can_stop: false } },
    control: { lease: { active: false, source: null }, command: { deadman: false, linear_x: 0, linear_y: 0, angular_z: 0 }, bridge: { available: true } },
    command: { deadman: false, linear_x: 0, linear_y: 0, angular_z: 0 }, localLeaseId: '',
    mapMeta: { id: MAP_ID, revision: REVISION }, map: { id: MAP_ID, revision: REVISION }, parameters: { revision: 'c'.repeat(64) },
    controller: { connected: true, inputFreshness: 'FRESH' },
  };
}

function harness(state, actions = {}, options = {}) {
  let interval;
  const adapter = createCockpitNavigationAdapter({
    getSnapshot: () => state, actions, now: options.now || (() => 0),
    takeoverTimeoutMs: 1000, setInterval: (callback) => { interval = callback; return 1; }, clearInterval() {},
  });
  return { adapter, tick: () => interval?.() };
}

test('manual lease, held deadman, and non-zero command independently block Nav start', () => {
  const state = input(); const { adapter } = harness(state);
  assert.equal(adapter.snapshot().canStart, true);
  state.control = { ...state.control, lease: { active: true, source: 'keyboard' } }; adapter.refresh();
  assert.equal(adapter.snapshot().canStart, false);
  state.control = { ...state.control, lease: { active: false, source: null } }; state.command = { deadman: true, linear_x: 0, linear_y: 0, angular_z: 0 }; adapter.refresh();
  assert.equal(adapter.snapshot().canStart, false);
  state.command = { deadman: false, linear_x: 0.1, linear_y: 0, angular_z: 0 }; adapter.refresh();
  assert.equal(adapter.snapshot().canStart, false);
  adapter.destroy();
});

test('takeover cancels, stops, verifies lease release, and never invokes ARM', async () => {
  const state = input(); state.navigation.pipeline.state = 'running'; state.navigation.goal = { state: 'active', goal_id: 'd'.repeat(32) }; state.navigation.safety.can_stop = true;
  state.control.lease = { active: true, source: 'navigation' };
  const calls = [];
  const { adapter } = harness(state, {
    async cancel() { calls.push('cancel'); state.navigation.goal = { state: 'cancelled' }; return { navigation: state.navigation }; },
    async stop() { calls.push('stop'); state.navigation.pipeline.state = 'idle'; state.control.lease = { active: false, source: null }; return { navigation: state.navigation }; },
  });
  await adapter.requestTakeover();
  assert.deepEqual(calls, ['cancel', 'stop']);
  assert.equal(adapter.snapshot().takeover.state, 'READY_TO_ARM');
  assert.equal(adapter.snapshot().takeover.readyToArm, true);
  assert.equal(Object.hasOwn(adapter, 'arm'), false);
  adapter.destroy();
});

test('panel close releases only its subscription while takeover cleanup continues', async () => {
  const state = input(); state.navigation.pipeline.state = 'running'; state.navigation.safety.can_stop = true; state.control.lease = { active: true, source: 'navigation' };
  let finishStop; const stopped = new Promise((resolve) => { finishStop = resolve; });
  const { adapter } = harness(state, { async stop() { await stopped; state.navigation.pipeline.state = 'idle'; state.control.lease.active = false; return {}; } });
  let destroyed = 0;
  const panel = createNavigationPanel({ adapter, viewFactory: () => ({ render() {}, clear() {}, destroy() { destroyed += 1; } }) });
  panel.mount({}); panel.activate();
  const operation = adapter.requestTakeover();
  panel.destroy();
  assert.equal(adapter.diagnostics().subscribers, 0);
  finishStop(); await operation;
  assert.equal(adapter.snapshot().takeover.state, 'READY_TO_ARM');
  assert.equal(destroyed, 1); adapter.destroy();
});

test('failed cleanup times out fail-closed and explicit retry can complete it', async () => {
  const state = input(); state.navigation.pipeline.state = 'running'; state.navigation.safety.can_stop = true; state.control.lease = { active: true, source: 'navigation' };
  let clock = 0; let attempts = 0;
  const { adapter, tick } = harness(state, { async stop() { attempts += 1; if (attempts === 1) return null; state.navigation.pipeline.state = 'idle'; state.control.lease.active = false; return {}; } }, { now: () => clock });
  await adapter.requestTakeover();
  clock = 1001; tick();
  assert.equal(adapter.snapshot().takeover.state, 'FAILED');
  assert.equal(adapter.snapshot().takeover.readyToArm, false);
  await adapter.retryTakeover();
  assert.equal(attempts, 2);
  assert.equal(adapter.snapshot().takeover.state, 'READY_TO_ARM');
  adapter.destroy();
});

test('late action response after owner destruction is ignored', async () => {
  const state = input(); let resolveStart;
  const pending = new Promise((resolve) => { resolveStart = resolve; });
  const { adapter } = harness(state, { start: () => pending });
  const result = adapter.start(); adapter.destroy(); resolveStart({ stale: true });
  assert.equal(await result, null);
  assert.equal(adapter.diagnostics().destroyed, true);
});
