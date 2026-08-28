function make(documentValue, name, className = '', text = '') {
  const element = documentValue.createElement(name);
  if (className) element.className = className;
  element.textContent = text;
  return element;
}

function ageLabel(value) {
  if (value == null) return 'NONE';
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

function axisLabel(value) {
  const number = Number(value) || 0;
  return `${number >= 0 ? '+' : ''}${number.toFixed(2)}`;
}

export function createControllerPanel(options = {}) {
  const documentValue = options.document || globalThis.document;
  const stateStore = options.controllerState;
  if (!documentValue || !stateStore) throw new TypeError('ControllerPanel requires document and controller state.');
  let host = null;
  let release = null;
  let active = false;
  let destroyed = false;
  const values = new Map();

  function metric(grid, label, key) {
    const item = make(documentValue, 'div', 'cockpit-controller-metric');
    item.dataset.controllerMetric = key;
    const caption = make(documentValue, 'span', '', label);
    const value = make(documentValue, 'strong', '', '—');
    item.append(caption, value);
    grid.append(item);
    values.set(key, value);
  }

  function render(state) {
    if (!host) return;
    host.dataset.controllerConnected = String(state.connected);
    values.get('device').textContent = state.safeId;
    values.get('connection').textContent = state.connected ? 'CONNECTED' : 'DISCONNECTED';
    values.get('freshness').textContent = `${state.inputFreshness} · ${ageLabel(state.inputAgeMs)}`;
    values.get('deadman').textContent = state.deadman ? 'LB HELD' : 'RELEASED';
    values.get('axes').textContent = `LX ${axisLabel(state.axes.leftX)} · LY ${axisLabel(state.axes.leftY)} · RX ${axisLabel(state.axes.rightX)}`;
    values.get('speed').textContent = `${Math.round(state.speedScale * 100)}% · SERVER CLAMPED`;
    values.get('lease').textContent = state.leaseSource;
    values.get('frame').textContent = ageLabel(state.lastFrameAgeMs);
    values.get('vibration').textContent = state.vibration ? 'SUPPORTED · READ ONLY' : 'UNAVAILABLE';
  }

  function mount(nextHost) {
    if (destroyed || host) return;
    host = nextHost;
    const wrapper = make(documentValue, 'div', 'cockpit-controller-panel');
    const status = make(documentValue, 'div', 'cockpit-controller-status');
    status.append(make(documentValue, 'span', '', 'STANDARD GAMEPAD'), make(documentValue, 'strong', '', 'READ-ONLY INPUT MONITOR'));
    const grid = make(documentValue, 'div', 'cockpit-controller-grid');
    for (const [label, key] of [['DEVICE', 'device'], ['LINK', 'connection'], ['INPUT', 'freshness'], ['DEADMAN', 'deadman'],
      ['NORMALIZED AXES', 'axes'], ['SPEED SCALE', 'speed'], ['LEASE SOURCE', 'lease'], ['LAST CONTROL FRAME', 'frame'], ['VIBRATION', 'vibration']]) metric(grid, label, key);
    const bindings = make(documentValue, 'small', 'cockpit-controller-bindings', 'D-PAD ◀▶ PANEL · Y FOCUS · X COMPACT · VIEW SENSORS · MENU COCKPIT · LB DEADMAN UNCHANGED');
    wrapper.append(status, grid, bindings);
    host.append(wrapper);
    render(stateStore.snapshot());
  }

  function activate() {
    if (destroyed || active || !host) return;
    active = true;
    host.dataset.contentLifecycle = 'active';
    release = stateStore.subscribe(render);
  }

  function deactivate() {
    if (!active) return;
    active = false;
    release?.();
    release = null;
    if (host) host.dataset.contentLifecycle = 'inactive';
  }

  function destroy() {
    if (destroyed) return;
    deactivate();
    destroyed = true;
    host?.replaceChildren();
    host = null;
  }

  return Object.freeze({ mount, activate, deactivate, destroy, diagnostics: () => Object.freeze({ active, destroyed, mounted: Boolean(host) }) });
}
