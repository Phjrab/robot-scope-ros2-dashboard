import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  createGamepadUiMapper,
  dispatchGamepadUiAction,
  projectControllerStatus,
  safeGamepadId,
} from '../robot_dashboard/static/features/cockpit/gamepad_ui.js';

function gamepad({ pressed = [], axes = [0, 0, 0], connected = true } = {}) {
  const buttons = Array.from({ length: 16 }, (_, index) => ({ pressed: pressed.includes(index), value: pressed.includes(index) ? 1 : 0 }));
  return { id: 'Synthetic Xbox (Vendor: 045e Product: 02fd)', index: 0, connected, mapping: 'standard', axes, buttons, vibrationActuator: {} };
}

test('standard Xbox UI buttons are rising-edge triggered and repeats are idempotent', () => {
  let now = 1000;
  const mapper = createGamepadUiMapper({ now: () => now });
  assert.deepEqual(mapper.sample(gamepad()).actions, []);
  now += 50;
  assert.deepEqual(mapper.sample(gamepad({ pressed: [15] })).actions, ['nextPanel']);
  now += 50;
  assert.deepEqual(mapper.sample(gamepad({ pressed: [15] })).actions, [], 'held D-pad must not repeat');
  mapper.sample(gamepad());
  assert.deepEqual(mapper.sample(gamepad({ pressed: [15] })).actions, ['nextPanel']);

  mapper.sample(gamepad());
  assert.deepEqual(mapper.sample(gamepad({ pressed: [2] }), { blocked: true }).actions, []);
  assert.deepEqual(mapper.sample(gamepad({ pressed: [2] }), { blocked: false }).actions, [], 'unblocking a held button must not synthesize an edge');
});

test('UI mapping is separate from drive axes, LB deadman, and B software-stop input', () => {
  const mapper = createGamepadUiMapper({ now: () => 1000 });
  const pad = gamepad({ pressed: [1, 4], axes: [-0.7, 0.4, 0.9] });
  const before = structuredClone(pad);
  const sample = mapper.sample(pad);
  assert.deepEqual(pad, before, 'UI sampling must not mutate the control input object');
  assert.equal(sample.deadman, true);
  assert.deepEqual(sample.axes, { leftX: -0.7, leftY: 0.4, rightX: 0.9 });
  assert.deepEqual(sample.actions, [], 'LB and B remain outside the Cockpit UI shortcut map');
});

test('disconnect clears mapper history and reconnect cannot replay held buttons', () => {
  let now = 1000;
  const mapper = createGamepadUiMapper({ now: () => now });
  mapper.sample(gamepad());
  mapper.sample(gamepad({ pressed: [3] }));
  now += 50;
  const disconnected = mapper.sample(null);
  assert.equal(disconnected.connected, false);
  assert.equal(disconnected.disconnected, true);
  assert.equal(disconnected.deadman, false);
  now += 50;
  assert.deepEqual(mapper.sample(gamepad({ pressed: [3] })).actions, [], 'held Y on reconnect must not focus a panel');
});

test('released-deadman focus and compact dispatch zero before the UI mutation', () => {
  const events = [];
  const handlers = {
    hasSelection: () => true,
    ensureZero: () => events.push('zero'),
    focus: () => events.push('focus'),
    compact: () => events.push('compact'),
  };
  dispatchGamepadUiAction('focus', { deadman: false }, handlers);
  dispatchGamepadUiAction('compact', { deadman: false }, handlers);
  assert.deepEqual(events, ['zero', 'focus', 'zero', 'compact']);
  events.length = 0;
  dispatchGamepadUiAction('focus', { deadman: true }, handlers);
  assert.deepEqual(events, ['focus']);
});

test('releasing LB while a focused UI session is active emits an immediate zero boundary', () => {
  const mapper = createGamepadUiMapper({ now: () => 1000 });
  mapper.sample(gamepad());
  const focused = mapper.sample(gamepad({ pressed: [3, 4] }));
  assert.deepEqual(focused.actions, ['focus']);
  assert.equal(focused.deadmanReleased, false);
  const released = mapper.sample(gamepad({ pressed: [3] }));
  assert.equal(released.deadman, false);
  assert.equal(released.deadmanReleased, true);
  assert.deepEqual(released.actions, []);
});

test('Controller projection is bounded, read-only, and excludes sensitive integration state', () => {
  assert.equal(safeGamepadId('Xbox Wireless Controller (Vendor: 045e Product: 02fd)'), 'Xbox Wireless Controller');
  const projected = projectControllerStatus({
    connected: true,
    safeId: 'Xbox Wireless Controller (Vendor: 045e Product: 02fd)',
    lastInputAt: 900,
    deadman: true,
    axes: { leftX: -1, leftY: 0.25, rightX: 1 },
    vibration: true,
  }, { now: 1000, speedScale: 4, speedScaleRange: [0.2, 0.6], leaseSource: 'gamepad', lastControlFrameAt: 950, leaseId: 'must-not-project' });
  assert.deepEqual(projected, {
    connected: true,
    safeId: 'Xbox Wireless Controller',
    inputAgeMs: 100,
    inputFreshness: 'FRESH',
    deadman: true,
    axes: { leftX: -1, leftY: 0.25, rightX: 1 },
    speedScale: 0.6,
    leaseSource: 'GAMEPAD',
    lastFrameAgeMs: 50,
    vibration: true,
  });
  assert.doesNotMatch(JSON.stringify(projected), /lease_id|leaseId|token|045e|02fd/i);
});

test('Cockpit UI adapter invokes the existing fail-safe without extending the control protocol', () => {
  const app = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
  const workspace = readFileSync(new URL('../robot_dashboard/static/features/cockpit/workspace.js', import.meta.url), 'utf8');
  const mapper = readFileSync(new URL('../robot_dashboard/static/features/cockpit/gamepad_ui.js', import.meta.url), 'utf8');
  assert.match(app, /onGamepadUiZeroIntent: \(\) => failSafeDisarm\('cockpit_gamepad_ui_zero'\)/);
  assert.match(app, /onGamepadDisconnect:[\s\S]{0,180}failSafeDisarm\('gamepad_disconnected'/);
  assert.match(workspace, /dispatchGamepadUiAction\(action, sample/);
  assert.match(workspace, /sample\.deadmanReleased[\s\S]{0,80}onGamepadUiZeroIntent/);
  assert.doesNotMatch(mapper, /WebSocket|lease_id|\/api\/v1|RobotControlInput|triggerEmergencyStop/);
});
