(function controlInputModule(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.RobotControlInput = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function buildControlInput() {
  'use strict';

  const MOVEMENT_CODES = Object.freeze(['KeyW', 'KeyS', 'KeyA', 'KeyD', 'KeyQ', 'KeyE']);
  const DEADMAN_CODES = Object.freeze(['ShiftLeft', 'ShiftRight']);

  function finiteNumber(value, fallback = 0) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function clamp(value, minimum = -1, maximum = 1) {
    const low = Math.min(finiteNumber(minimum), finiteNumber(maximum));
    const high = Math.max(finiteNumber(minimum), finiteNumber(maximum));
    return Math.min(high, Math.max(low, finiteNumber(value)));
  }

  function applyDeadzone(value, deadzone = 0.12) {
    const axis = clamp(value);
    const threshold = clamp(Math.abs(deadzone), 0, 0.95);
    if (Math.abs(axis) <= threshold) return 0;
    return Math.sign(axis) * ((Math.abs(axis) - threshold) / (1 - threshold));
  }

  function codePressed(keys, code) {
    if (!keys) return false;
    if (typeof keys.has === 'function') return keys.has(code);
    return Boolean(keys[code]);
  }

  function zeroCommand(source = 'keyboard') {
    return { source, deadman: false, linear_x: 0, linear_y: 0, angular_z: 0 };
  }

  function keyboardCommand(keys) {
    const deadman = DEADMAN_CODES.some((code) => codePressed(keys, code));
    if (!deadman) return zeroCommand('keyboard');
    return {
      source: 'keyboard',
      deadman: true,
      linear_x: (codePressed(keys, 'KeyW') ? 1 : 0) - (codePressed(keys, 'KeyS') ? 1 : 0),
      linear_y: (codePressed(keys, 'KeyA') ? 1 : 0) - (codePressed(keys, 'KeyD') ? 1 : 0),
      angular_z: (codePressed(keys, 'KeyQ') ? 1 : 0) - (codePressed(keys, 'KeyE') ? 1 : 0),
    };
  }

  function pointerCommand(directions, deadman) {
    if (!deadman) return zeroCommand('keyboard');
    const active = directions instanceof Set ? directions : new Set(directions || []);
    return {
      source: 'keyboard',
      deadman: true,
      linear_x: (active.has('forward') ? 1 : 0) - (active.has('backward') ? 1 : 0),
      linear_y: (active.has('left') ? 1 : 0) - (active.has('right') ? 1 : 0),
      angular_z: (active.has('turn-left') ? 1 : 0) - (active.has('turn-right') ? 1 : 0),
    };
  }

  function gamepadButtonPressed(gamepad, index) {
    const button = gamepad?.buttons?.[index];
    return Boolean(typeof button === 'number' ? button > 0.5 : button?.pressed || Number(button?.value) > 0.5);
  }

  function gamepadCommand(gamepad, deadzone = 0.12) {
    if (!gamepad || gamepad.mapping !== 'standard' || !gamepadButtonPressed(gamepad, 4)) return zeroCommand('gamepad');
    const axes = gamepad.axes || [];
    return {
      source: 'gamepad',
      deadman: true,
      linear_x: applyDeadzone(-finiteNumber(axes[1]), deadzone),
      linear_y: applyDeadzone(-finiteNumber(axes[0]), deadzone),
      angular_z: applyDeadzone(-finiteNumber(axes[2]), deadzone),
    };
  }

  function scaleCommand(command, limits = {}, speedScale = 1) {
    const source = command?.source === 'gamepad' ? 'gamepad' : 'keyboard';
    if (!command?.deadman) return zeroCommand(source);
    const scale = clamp(speedScale, 0, 1);
    return {
      source,
      deadman: true,
      linear_x: clamp(command.linear_x) * Math.max(0, finiteNumber(limits.max_linear_x)) * scale,
      linear_y: clamp(command.linear_y) * Math.max(0, finiteNumber(limits.max_linear_y)) * scale,
      angular_z: clamp(command.angular_z) * Math.max(0, finiteNumber(limits.max_angular_z)) * scale,
    };
  }

  function isMovementCode(code) {
    return MOVEMENT_CODES.includes(code);
  }

  function isDeadmanCode(code) {
    return DEADMAN_CODES.includes(code);
  }

  function isControlCode(code) {
    return isMovementCode(code) || isDeadmanCode(code);
  }

  return Object.freeze({
    MOVEMENT_CODES,
    DEADMAN_CODES,
    clamp,
    applyDeadzone,
    zeroCommand,
    keyboardCommand,
    pointerCommand,
    gamepadButtonPressed,
    gamepadCommand,
    scaleCommand,
    isMovementCode,
    isDeadmanCode,
    isControlCode,
  });
}));
