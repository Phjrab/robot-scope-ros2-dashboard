const TAKEOVER_STATES = Object.freeze(['IDLE', 'CANCELING', 'STOPPING', 'VERIFYING', 'READY_TO_ARM', 'FAILED']);

function navigationActive(snapshot) {
  const pipeline = String(snapshot?.pipeline?.state || '').toLowerCase();
  const goal = String(snapshot?.goal?.state || '').toLowerCase();
  return ['starting', 'running', 'stopping'].includes(pipeline) || ['pending', 'active', 'canceling'].includes(goal);
}

function goalActive(snapshot) {
  return ['pending', 'active', 'canceling'].includes(String(snapshot?.goal?.state || '').toLowerCase());
}

function navigationLeaseReleased(control) {
  return control && control.lease?.active === false;
}

function zeroManualCommand(command) {
  return command?.deadman !== true && ['linear_x', 'linear_y', 'angular_z'].every((key) => {
    const value = Number(command?.[key] || 0);
    return Number.isFinite(value) && Math.abs(value) <= 0.001;
  });
}

export function createCockpitNavigationAdapter(options = {}) {
  const getInput = options.getSnapshot || (() => ({}));
  const actions = options.actions || {};
  const now = options.now || Date.now;
  const setIntervalValue = options.setInterval || globalThis.setInterval?.bind(globalThis);
  const clearIntervalValue = options.clearInterval || globalThis.clearInterval?.bind(globalThis);
  const timeoutMs = Math.max(1_000, Math.min(30_000, Number(options.takeoverTimeoutMs) || 15_000));
  const subscribers = new Set();
  let destroyed = false;
  let actionGeneration = 0;
  let takeoverGeneration = 0;
  let takeoverState = 'IDLE';
  let takeoverError = '';
  let takeoverStartedAt = 0;
  let actionBusy = false;
  let timer = 0;
  let state = null;

  function input() {
    const value = getInput();
    return value && typeof value === 'object' ? value : {};
  }

  function project() {
    const current = input();
    const navigation = current.navigation || {};
    const control = current.control || null;
    const manualActive = Boolean(String(current.localLeaseId || '').trim()) || current.navigationEngine?.manualControlActive?.(control, current.localLeaseId) === true;
    const navActive = navigationActive(navigation);
    const mapExact = Boolean(current.mapMeta?.id && current.map?.id === current.mapMeta.id && current.map?.revision === current.mapMeta.revision);
    const parametersReady = Boolean(String(current.parameters?.revision || ''));
    const controller = current.controller || {};
    const canStart = current.navigationAvailable === true && navigation.available === true && navigation.robot_online === true &&
      navigation.safety?.can_start === true && !navActive && !manualActive && zeroManualCommand(current.command || control?.command) && mapExact && parametersReady;
    const takeoverReady = takeoverState === 'READY_TO_ARM' && !navActive && navigationLeaseReleased(control);
    return Object.freeze({
      navigation, control, mapMeta: current.mapMeta || null, map: current.map || null,
      mapCells: current.mapCells || null,
      maps: Object.freeze((Array.isArray(current.maps) ? current.maps : []).slice(0, 64)), parameters: current.parameters || null,
      annotations: current.annotations || null, logs: current.logs || null, controller,
      navigationAvailable: current.navigationAvailable === true, operationBusy: Boolean(current.operationBusy || actionBusy),
      manualActive, commandZero: zeroManualCommand(current.command || control?.command), navigationActive: navActive,
      canStart, canStop: navigation.safety?.can_stop === true || navActive, canCancel: goalActive(navigation),
      canClear: String(navigation.pipeline?.state || '').toLowerCase() === 'running',
      takeover: Object.freeze({ state: takeoverState, error: takeoverError, readyToArm: takeoverReady, generation: takeoverGeneration,
        bridgeReady: control?.bridge?.available === true || control?.bridge?.ready === true,
        controllerFresh: controller.connected === true && controller.inputFreshness === 'FRESH' }),
    });
  }

  function publish() {
    state = project();
    for (const subscriber of subscribers) subscriber(state);
    return state;
  }

  function setTakeover(next, error = '') {
    takeoverState = TAKEOVER_STATES.includes(next) ? next : 'FAILED';
    takeoverError = String(error || '').slice(0, 180);
    publish();
  }

  async function invoke(name, ...args) {
    if (destroyed || actionBusy || typeof actions[name] !== 'function') return null;
    const generation = ++actionGeneration;
    actionBusy = true; publish();
    try {
      const result = await actions[name](...args);
      return generation === actionGeneration && !destroyed ? result : null;
    } finally {
      if (generation === actionGeneration && !destroyed) { actionBusy = false; publish(); }
    }
  }

  function reconcileTakeover() {
    if (takeoverState !== 'VERIFYING') return publish();
    const current = input();
    if (!navigationActive(current.navigation) && navigationLeaseReleased(current.control)) {
      setTakeover('READY_TO_ARM');
    } else if (now() - takeoverStartedAt >= timeoutMs) {
      setTakeover('FAILED', 'Navigation stop 또는 lease 해제를 확인하지 못했습니다. cleanup을 다시 시도하세요.');
    } else publish();
    return state;
  }

  async function requestTakeover() {
    if (destroyed || ['CANCELING', 'STOPPING', 'VERIFYING'].includes(takeoverState)) return state;
    const generation = ++takeoverGeneration;
    takeoverStartedAt = now();
    let cleanupWarning = '';
    setTakeover('CANCELING');
    try {
      if (goalActive(input().navigation)) {
        const cancelled = await actions.cancel?.();
        if (generation !== takeoverGeneration || destroyed) return state;
        if (!cancelled) cleanupWarning = 'Goal cancel 확인 실패; stop cleanup을 계속합니다.';
      }
      setTakeover('STOPPING', cleanupWarning);
      if (navigationActive(input().navigation)) {
        const stopped = await actions.stop?.();
        if (generation !== takeoverGeneration || destroyed) return state;
        if (!stopped) cleanupWarning = `${cleanupWarning} Navigation stop 응답을 확인하지 못했습니다.`.trim();
      }
      setTakeover('VERIFYING', cleanupWarning);
      reconcileTakeover();
    } catch (error) {
      if (generation === takeoverGeneration && !destroyed) setTakeover('FAILED', `Cleanup 실패: ${String(error?.message || error).slice(0, 140)}`);
    }
    return state;
  }

  function subscribe(callback) {
    if (typeof callback !== 'function') throw new TypeError('Navigation subscriber callback is required.');
    subscribers.add(callback); callback(state || publish());
    return () => subscribers.delete(callback);
  }

  timer = setIntervalValue?.(reconcileTakeover, 250) || 0;
  publish();
  return Object.freeze({
    subscribe, snapshot: () => state, refresh: publish, requestTakeover, retryTakeover: requestTakeover,
    start: () => invoke('start'), stop: () => invoke('stop'), cancel: () => invoke('cancel'), clear: () => invoke('clear'),
    selectMap: (id) => invoke('selectMap', id), submitPose: (mode, pose) => invoke('pose', mode, pose),
    submitAnnotationGoal: (id) => invoke('annotationGoal', id),
    diagnostics: () => Object.freeze({ destroyed, subscribers: subscribers.size, actionGeneration, takeoverGeneration, takeoverState, actionBusy }),
    destroy() { destroyed = true; actionGeneration += 1; subscribers.clear(); if (timer) clearIntervalValue?.(timer); timer = 0; },
  });
}
