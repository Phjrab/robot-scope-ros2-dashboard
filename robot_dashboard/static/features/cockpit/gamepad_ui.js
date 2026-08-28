export const GAMEPAD_UI_BUTTONS = Object.freeze({
  compact: 2,
  focus: 3,
  launcher: 8,
  menu: 9,
  previousPanel: 14,
  nextPanel: 15,
});

const UI_ACTIONS = Object.freeze(Object.entries(GAMEPAD_UI_BUTTONS)
  .map(([action, button]) => Object.freeze({ action, button })));

function finite(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function clamp(value, minimum = -1, maximum = 1) {
  return Math.min(maximum, Math.max(minimum, finite(value)));
}

function pressed(gamepad, index) {
  const button = gamepad?.buttons?.[index];
  return Boolean(typeof button === 'number' ? button > 0.5 : button?.pressed || finite(button?.value) > 0.5);
}

function inputSignature(gamepad) {
  const axes = Array.from(gamepad?.axes || [], (value) => clamp(value).toFixed(2));
  const buttons = Array.from(gamepad?.buttons || [], (button) => {
    const value = typeof button === 'number' ? button : button?.value;
    return clamp(value, 0, 1).toFixed(2);
  });
  return `${axes.join(',')}|${buttons.join(',')}`;
}

export function safeGamepadId(value) {
  const cleaned = String(value || '')
    .replace(/\([^)]*(?:vendor|product|[0-9a-f]{4})[^)]*\)/gi, ' ')
    .replace(/[^\p{L}\p{N} ._+\-]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return (cleaned || 'STANDARD GAMEPAD').slice(0, 64);
}

function sampleAxes(gamepad) {
  return Object.freeze({
    leftX: clamp(gamepad?.axes?.[0]),
    leftY: clamp(gamepad?.axes?.[1]),
    rightX: clamp(gamepad?.axes?.[2]),
  });
}

export function createGamepadUiMapper(options = {}) {
  const now = options.now || Date.now;
  let identity = '';
  let connected = false;
  let priorButtons = new Set();
  let priorSignature = '';
  let lastInputAt = 0;
  let priorDeadman = false;

  function reset() {
    identity = '';
    connected = false;
    priorButtons = new Set();
    priorSignature = '';
    lastInputAt = 0;
    priorDeadman = false;
  }

  function sample(gamepad, context = {}) {
    const sampledAt = finite(context.now, now());
    const valid = Boolean(gamepad && gamepad.connected !== false && gamepad.mapping === 'standard');
    if (!valid) {
      const disconnected = connected;
      reset();
      return Object.freeze({ connected: false, disconnected, sampledAt, safeId: 'NO GAMEPAD', lastInputAt: 0,
        deadman: false, deadmanReleased: false, axes: sampleAxes(null), vibration: false, actions: Object.freeze([]) });
    }

    const nextIdentity = `${finite(gamepad.index, -1)}:${safeGamepadId(gamepad.id)}`;
    const currentButtons = new Set(UI_ACTIONS.filter(({ button }) => pressed(gamepad, button)).map(({ button }) => button));
    const signature = inputSignature(gamepad);
    const newConnection = !connected || identity !== nextIdentity;
    const deadman = pressed(gamepad, 4);
    const deadmanReleased = !newConnection && priorDeadman && !deadman;
    if (newConnection || signature !== priorSignature) lastInputAt = sampledAt;
    const actions = !newConnection && context.enabled !== false && !context.blocked
      ? UI_ACTIONS.filter(({ button }) => currentButtons.has(button) && !priorButtons.has(button)).map(({ action }) => action)
      : [];
    identity = nextIdentity;
    connected = true;
    priorButtons = currentButtons;
    priorSignature = signature;
    priorDeadman = deadman;
    return Object.freeze({
      connected: true,
      disconnected: false,
      sampledAt,
      safeId: safeGamepadId(gamepad.id),
      lastInputAt,
      deadman,
      deadmanReleased,
      axes: sampleAxes(gamepad),
      vibration: Boolean(gamepad.vibrationActuator),
      actions: Object.freeze(actions),
    });
  }

  return Object.freeze({ sample, reset });
}

export function projectControllerStatus(sample = {}, context = {}) {
  const now = finite(context.now, Date.now());
  const connected = Boolean(sample.connected);
  const inputAgeMs = connected && sample.lastInputAt ? Math.max(0, now - sample.lastInputAt) : null;
  const frameAt = finite(context.lastControlFrameAt);
  const speedMinimum = clamp(context.speedScaleRange?.[0] ?? 0, 0, 1);
  const speedMaximum = clamp(context.speedScaleRange?.[1] ?? 1, speedMinimum, 1);
  return Object.freeze({
    connected,
    safeId: connected ? safeGamepadId(sample.safeId) : 'NO GAMEPAD',
    inputAgeMs,
    inputFreshness: !connected ? 'DISCONNECTED' : inputAgeMs <= 1000 ? 'FRESH' : inputAgeMs <= 5000 ? 'IDLE' : 'STALE',
    deadman: connected && Boolean(sample.deadman),
    axes: connected ? sample.axes : sampleAxes(null),
    speedScale: clamp(context.speedScale, speedMinimum, speedMaximum),
    leaseSource: String(context.leaseSource || '').toLowerCase() === 'gamepad' ? 'GAMEPAD'
      : String(context.leaseSource || '').toLowerCase() === 'keyboard' ? 'KEYBOARD' : 'NONE',
    lastFrameAgeMs: frameAt ? Math.max(0, now - frameAt) : null,
    vibration: connected && Boolean(sample.vibration),
  });
}

export function dispatchGamepadUiAction(action, sample, handlers = {}) {
  if (!UI_ACTIONS.some((entry) => entry.action === action)) return false;
  if (['focus', 'compact'].includes(action) && !sample?.deadman && handlers.hasSelection?.()) handlers.ensureZero?.();
  handlers[action]?.();
  return true;
}

export function createControllerStateStore() {
  let state = projectControllerStatus();
  const listeners = new Set();
  return Object.freeze({
    snapshot: () => state,
    update(next) {
      state = Object.freeze({ ...next, axes: Object.freeze({ ...(next?.axes || {}) }) });
      for (const listener of listeners) listener(state);
      return state;
    },
    subscribe(listener) {
      if (typeof listener !== 'function') throw new TypeError('Controller state listener must be a function.');
      listeners.add(listener);
      listener(state);
      return () => listeners.delete(listener);
    },
  });
}
