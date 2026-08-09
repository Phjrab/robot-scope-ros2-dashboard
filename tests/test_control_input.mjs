import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const input = require('../robot_dashboard/static/control_input.js');
const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');

function keys(...codes) {
  return new Set(codes);
}

function gamepad({ axes = [0, 0, 0], lb = false } = {}) {
  const buttons = Array.from({ length: 5 }, () => ({ pressed: false, value: 0 }));
  buttons[4] = { pressed: lb, value: lb ? 1 : 0 };
  return { axes, buttons, mapping: 'standard' };
}

test('keyboard maps W/S, A/D and Q/E to ROS twist axes', () => {
  assert.deepEqual(input.keyboardCommand(keys('ShiftLeft', 'KeyW', 'KeyA', 'KeyQ')), {
    source: 'keyboard', deadman: true, linear_x: 1, linear_y: 1, angular_z: 1,
  });
  assert.deepEqual(input.keyboardCommand(keys('ShiftRight', 'KeyS', 'KeyD', 'KeyE')), {
    source: 'keyboard', deadman: true, linear_x: -1, linear_y: -1, angular_z: -1,
  });
});

test('opposite keyboard and pointer directions cancel', () => {
  assert.deepEqual(input.keyboardCommand(keys('ShiftLeft', 'KeyW', 'KeyS', 'KeyA', 'KeyD', 'KeyQ', 'KeyE')), {
    source: 'keyboard', deadman: true, linear_x: 0, linear_y: 0, angular_z: 0,
  });
  assert.deepEqual(input.pointerCommand(['forward', 'backward', 'turn-left', 'turn-right'], true), {
    source: 'keyboard', deadman: true, linear_x: 0, linear_y: 0, angular_z: 0,
  });
});

test('deadzone removes drift and rescales usable gamepad travel', () => {
  assert.equal(input.applyDeadzone(0.1, 0.12), 0);
  assert.equal(input.applyDeadzone(-0.12, 0.12), 0);
  assert.equal(input.applyDeadzone(1, 0.12), 1);
  assert.equal(input.applyDeadzone(-1, 0.12), -1);
  assert.ok(Math.abs(input.applyDeadzone(0.56, 0.12) - 0.5) < 1e-12);
});

test('gamepad uses left stick translation, right X yaw and LB deadman', () => {
  assert.deepEqual(input.gamepadCommand(gamepad({ axes: [-1, -1, 1], lb: true })), {
    source: 'gamepad', deadman: true, linear_x: 1, linear_y: 1, angular_z: -1,
  });
  assert.deepEqual(input.gamepadCommand(gamepad({ axes: [-1, -1, 1], lb: false })), input.zeroCommand('gamepad'));
  assert.deepEqual(
    input.gamepadCommand({ ...gamepad({ axes: [-1, -1, 1], lb: true }), mapping: '' }),
    input.zeroCommand('gamepad'),
  );
});

test('commands clamp before applying server limits and speed scale', () => {
  const scaled = input.scaleCommand(
    { source: 'keyboard', deadman: true, linear_x: 2, linear_y: -2, angular_z: 0.5 },
    { max_linear_x: 1.2, max_linear_y: 0.6, max_angular_z: 2 },
    1.5,
  );
  assert.deepEqual(scaled, {
    source: 'keyboard', deadman: true, linear_x: 1.2, linear_y: -0.6, angular_z: 1,
  });
});

test('all input paths zero motion when deadman is released', () => {
  assert.deepEqual(input.keyboardCommand(keys('KeyW')), input.zeroCommand('keyboard'));
  assert.deepEqual(input.pointerCommand(['forward'], false), input.zeroCommand('keyboard'));
  assert.deepEqual(
    input.scaleCommand({ source: 'gamepad', deadman: false, linear_x: 1 }, { max_linear_x: 10 }, 1),
    input.zeroCommand('gamepad'),
  );
});

test('browser control frames carry fresh client timestamps and reject queued writes', () => {
  assert.match(appSource, /type: 'bind',[^\n]+client_time_ms: Date\.now\(\)/);
  assert.match(appSource, /type: 'twist',[\s\S]{0,260}client_time_ms: Date\.now\(\)/);
  assert.match(appSource, /type: 'heartbeat',[\s\S]{0,180}client_time_ms: Date\.now\(\)/);
  assert.match(appSource, /type: 'action',[\s\S]{0,220}client_time_ms: Date\.now\(\)/);
  assert.match(appSource, /type: 'release',[^\n]+client_time_ms: Date\.now\(\)/);
  assert.match(appSource, /bufferedAmount/);
  assert.match(appSource, /queuedBytes !== 0/);
  assert.match(appSource, /if \(payload\.type === 'bound'\) \{\s*controlSocketBound = true/);
  assert.match(appSource, /if \(controlSocketBound && controlSocket\?\.readyState === WebSocket\.OPEN\)/);
});

test('accepted one-shot action discards the local lease without zero or release', () => {
  const start = appSource.indexOf("if (payload.type === 'action_accepted')");
  const end = appSource.indexOf('applyControlSnapshot(extractControlSnapshot(payload));', start);
  assert.ok(start >= 0 && end > start, 'action_accepted handler must exist');
  const handler = appSource.slice(start, end);
  assert.match(handler, /controlLeaseId = ''/);
  assert.match(handler, /controlLeaseSource = ''/);
  assert.match(handler, /closeControlSocket\('action_accepted'\)/);
  assert.doesNotMatch(handler, /sendImmediateZero|type: 'release'/);
  assert.doesNotMatch(handler, /300/);
});

test('dashboard stop copy does not present software control as a physical E-stop', () => {
  assert.match(indexSource, /DASHBOARD SOFTWARE STOP/);
  assert.match(indexSource, /물리 E-stop 아님/);
  assert.match(indexSource, /물리 비상정지 장치를 대신하지 않습니다/);
  assert.doesNotMatch(indexSource, /SOFTWARE E-STOP|Emergency stop|E-STOP CLEAR/);
});
