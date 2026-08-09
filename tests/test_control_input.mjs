import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';

const require = createRequire(import.meta.url);
const input = require('../robot_dashboard/static/control_input.js');
const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');

function loadBackpressureDecision() {
  const match = appSource.match(/function controlBackpressureDecision\([\s\S]+?\n\}/);
  assert.ok(match, 'controlBackpressureDecision must exist');
  const context = {
    CONTROL_SOCKET_MAX_BUFFER_BYTES: 4096,
    CONTROL_SOCKET_BACKPRESSURE_GRACE_MS: 100,
    Number,
  };
  vm.runInNewContext(`${match[0]}; this.decision = controlBackpressureDecision;`, context);
  return context.decision;
}

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

test('Shift-only is a held zero-axis deadman, not a drive frame', () => {
  const shiftOnly = input.keyboardCommand(keys('ShiftLeft'));
  assert.deepEqual(shiftOnly, {
    source: 'keyboard', deadman: true, linear_x: 0, linear_y: 0, angular_z: 0,
  });
  assert.equal(input.controlFrameIntent(shiftOnly), 'idle');
  assert.equal(input.controlFrameIntent(shiftOnly, { heartbeatDue: true }), 'heartbeat');
  assert.equal(input.controlFrameIntent(shiftOnly, { motionActive: true }), 'stop');
  const moving = input.keyboardCommand(keys('ShiftLeft', 'KeyW'));
  assert.equal(input.controlFrameIntent(moving), 'drive');
  assert.equal(input.controlFrameIntent(moving, { heartbeatDue: true }), 'heartbeat');
  assert.equal(input.controlFrameIntent(shiftOnly, { motionActive: true, heartbeatDue: true }), 'stop');
});

test('only releasing the final Shift ends the keyboard deadman hold', () => {
  assert.equal(input.deadmanReleaseEndsHold(keys('ShiftLeft'), 'KeyW'), false);
  assert.equal(input.deadmanReleaseEndsHold(keys('ShiftRight'), 'ShiftLeft'), false);
  assert.equal(input.deadmanReleaseEndsHold(keys(), 'ShiftLeft'), true);
  assert.equal(input.deadmanReleaseEndsHold(keys(), 'KeyW'), false);
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
  assert.match(appSource, /CONTROL_SOCKET_BACKPRESSURE_GRACE_MS = 100/);
  assert.match(appSource, /controlBackpressureDecision\(queuedBytes, controlBackpressureSince, Date\.now\(\)\)/);
  assert.match(appSource, /if \(payload\.type === 'bound'\) \{\s*controlSocketBound = true/);
  assert.match(appSource, /if \(controlSocketBound && controlSocket\?\.readyState === WebSocket\.OPEN\)/);
});

test('small WebSocket backpressure skips frames briefly, then fails closed', () => {
  const decision = loadBackpressureDecision();
  assert.deepEqual({ ...decision(0, 900, 1000) }, { action: 'send', sinceMs: null });
  assert.deepEqual({ ...decision(16, null, 1000) }, { action: 'skip', sinceMs: 1000 });
  assert.deepEqual({ ...decision(16, 1000, 1099) }, { action: 'skip', sinceMs: 1000 });
  assert.deepEqual({ ...decision(16, 1000, 1100) }, { action: 'disarm', sinceMs: 1000 });
  assert.deepEqual({ ...decision(4097, null, 1000) }, { action: 'disarm', sinceMs: null });
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

test('control arming and software-stop clearing are explicit PIN-free button flows', () => {
  assert.doesNotMatch(indexSource, /controlPin|estopClearPin|제어 PIN|해제 PIN/);
  assert.doesNotMatch(appSource, /controlUi\.(?:pin|clearPin)/);
  assert.match(appSource, /body: JSON\.stringify\(\{ input_source: source \}\)/);
  assert.match(appSource, /body: JSON\.stringify\(\{ confirmed: true \}\)/);
});

test('an inactive control poll started before ARM cannot revoke the new lease', () => {
  const start = appSource.indexOf('async function refreshControlSnapshot()');
  const end = appSource.indexOf('\nfunction selectedControlGamepad()', start);
  assert.ok(start >= 0 && end > start, 'refreshControlSnapshot must exist');
  const refresh = appSource.slice(start, end);
  assert.match(refresh, /const armGenerationAtRequest = controlArmGeneration/);
  assert.match(refresh, /const leaseAtRequest = controlLeaseId/);
  assert.match(refresh, /armGenerationAtRequest !== controlArmGeneration \|\| leaseAtRequest !== controlLeaseId/);
  assert.ok(
    refresh.indexOf('armGenerationAtRequest !== controlArmGeneration') < refresh.indexOf('applyControlSnapshot(snapshot)'),
    'stale polls must be rejected before their snapshot is applied',
  );
});

test('late messages from an old control socket cannot touch a replacement lease', () => {
  const start = appSource.indexOf('socket.onmessage = (event) => {');
  const end = appSource.indexOf('\n  socket.onerror =', start);
  assert.ok(start >= 0 && end > start, 'control socket message handler must exist');
  const handler = appSource.slice(start, end);
  const guard = 'if (controlSocket !== socket || controlLeaseId !== leaseAtConnect) return;';
  assert.match(handler, /controlSocket !== socket \|\| controlLeaseId !== leaseAtConnect/);
  assert.ok(handler.indexOf(guard) < handler.indexOf('JSON.parse(event.data)'), 'session guard must run before payload handling');
  assert.ok(handler.indexOf(guard) < handler.indexOf("payload.type === 'error'"), 'old errors must be ignored');
  assert.ok(handler.indexOf(guard) < handler.indexOf("payload.type === 'bound'"), 'old bound frames must be ignored');
});

test('keyboard repeats are idempotent and direction keyup stops without disarming', () => {
  const downStart = appSource.indexOf('function handleControlKeyDown(event)');
  const upStart = appSource.indexOf('function handleControlKeyUp(event)');
  const upEnd = appSource.indexOf('\nfunction releaseControlPointer(event)', upStart);
  const downHandler = appSource.slice(downStart, upStart);
  const upHandler = appSource.slice(upStart, upEnd);
  assert.match(downHandler, /event\.repeat && controlPressedKeys\.has\(event\.code\)/);
  assert.match(upHandler, /deadmanReleaseEndsHold\(controlPressedKeys, event\.code\)/);
  assert.match(upHandler, /keyboard_deadman_released/);
  assert.match(upHandler, /else \{[\s\S]{0,180}controlTick\(\)/);
  assert.doesNotMatch(upHandler, /keyboard_key_released/);
  assert.match(indexSource, /방향키를 놓으면 정지하고 ARM은 유지됩니다/);
});

test('screen direction release also stops without releasing a held deadman', () => {
  const start = appSource.indexOf('function releaseControlPointer(event)');
  const end = appSource.indexOf('\nfunction bindControlPointerButtons()', start);
  const handler = appSource.slice(start, end);
  assert.match(handler, /wasDeadman && controlDeadmanPointers\.size === 0 && !keyboardDeadman/);
  assert.match(handler, /pointer_deadman_released/);
  assert.match(handler, /else \{\s*controlTick\(\)/);
  assert.doesNotMatch(handler, /pointer_direction_released/);
});

test('ARM clears button focus while window blur remains fail-safe', () => {
  assert.match(appSource, /controlUi\.arm\.blur\(\)/);
  assert.match(appSource, /window\.addEventListener\('blur',[\s\S]{0,180}failSafeDisarm\('window_blurred'\)/);
});
