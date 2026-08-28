const NAVIGATION_KEYS = Object.freeze(['ArrowDown', 'ArrowRight', 'ArrowUp', 'ArrowLeft', 'Home', 'End']);

export function nextLauncherIndex(current, key, count) {
  if (!count) return -1;
  if (key === 'Home') return 0;
  if (key === 'End') return count - 1;
  if (key === 'ArrowDown' || key === 'ArrowRight') return (current + 1 + count) % count;
  if (key === 'ArrowUp' || key === 'ArrowLeft') return (current - 1 + count) % count;
  return current;
}

function button(documentValue, label, action) {
  const element = documentValue.createElement('button');
  element.type = 'button';
  element.textContent = label;
  if (action) element.dataset.layoutAction = action;
  return element;
}

export function createSensorLauncher(options = {}) {
  const root = options.root;
  const registry = options.registry;
  const documentValue = options.document || globalThis.document;
  if (!root || !registry || !documentValue) throw new TypeError('SensorLauncher requires root, registry, and document.');
  root.replaceChildren();

  const toggle = button(documentValue, 'SENSORS', '');
  toggle.className = 'cockpit-launcher-toggle';
  toggle.setAttribute('aria-expanded', 'true');
  toggle.setAttribute('aria-controls', 'cockpitLauncherBody');
  const body = documentValue.createElement('div');
  body.id = 'cockpitLauncherBody';
  body.className = 'cockpit-launcher-body';
  const heading = documentValue.createElement('strong');
  heading.textContent = 'SENSOR LAUNCHER';
  const list = documentValue.createElement('div');
  list.className = 'cockpit-launcher-list';
  list.setAttribute('role', 'toolbar');
  list.setAttribute('aria-label', 'Sensor panel 선택');
  const panelButtons = [];
  const panelEntries = [];
  let visibleTypes = new Set();
  let activePanelId = '';
  let layoutEditable = false;
  let sourceMap = new Map();

  for (const descriptor of registry.list()) {
    const item = button(documentValue, '', '');
    item.className = 'cockpit-launcher-item';
    item.dataset.panelType = descriptor.panelType;
    item.setAttribute('aria-label', `${descriptor.label} panel 열기 또는 앞으로 가져오기`);
    item.setAttribute('aria-pressed', 'false');
    const icon = documentValue.createElement('span');
    icon.className = 'cockpit-launcher-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = descriptor.icon;
    const identity = documentValue.createElement('span');
    const label = documentValue.createElement('b');
    label.textContent = descriptor.label;
    const size = documentValue.createElement('small');
    size.textContent = `${descriptor.defaultGeometry.width}×${descriptor.defaultGeometry.height} · MIN ${descriptor.bounds.minWidth}×${descriptor.bounds.minHeight}`;
    const availability = documentValue.createElement('small');
    availability.className = 'cockpit-launcher-availability';
    availability.textContent = descriptor.sourceId ? 'CATALOG WAITING' : 'AVAILABLE';
    identity.append(label, size, availability);
    item.append(icon, identity);
    item.addEventListener('click', () => options.onOpen?.(descriptor.panelType));
    list.append(item);
    panelButtons.push(item);
    panelEntries.push({ item, descriptor, availability });
  }

  const layouts = documentValue.createElement('div');
  layouts.className = 'cockpit-layout-controls';
  layouts.setAttribute('aria-label', 'Panel workspace 정렬');
  const layoutActions = [
    ['L', 'dock-left', '선택 panel 왼쪽 Dock'],
    ['R', 'dock-right', '선택 panel 오른쪽 Dock'],
    ['T', 'dock-top', '선택 panel 위 Dock'],
    ['B', 'dock-bottom', '선택 panel 아래 Dock'],
    ['FREE', 'undock', '선택 panel Dock 해제'],
    ['50:50', 'split', 'Panel 두 개 50 대 50 배치'],
    ['2×2', 'tile', 'Panel 2 곱하기 2 배치'],
    ['CASCADE', 'cascade', 'Panel cascade 배치'],
    ['RECOVER', 'recover', '모든 panel 화면 안으로 복구'],
  ];
  const activeActions = new Set(['dock-left', 'dock-right', 'dock-top', 'dock-bottom', 'undock']);
  const layoutButtons = [];
  for (const [label, action, ariaLabel] of layoutActions) {
    const item = button(documentValue, label, action);
    item.setAttribute('aria-label', ariaLabel);
    item.addEventListener('click', () => options.onLayoutAction?.(action));
    layouts.append(item);
    layoutButtons.push(item);
  }
  const gridLabel = documentValue.createElement('label');
  gridLabel.textContent = 'GRID';
  const grid = documentValue.createElement('select');
  grid.setAttribute('aria-label', 'Panel grid snap 크기');
  for (const value of [8, 16, 24, 32]) {
    const option = documentValue.createElement('option');
    option.value = String(value);
    option.textContent = `${value}px`;
    option.selected = value === 16;
    grid.append(option);
  }
  grid.addEventListener('change', () => options.onSnapOptions?.({ gridSize: Number(grid.value) }));
  gridLabel.append(grid);
  layouts.append(gridLabel);
  body.append(heading, list, layouts);
  root.append(toggle, body);

  function setExpanded(expanded) {
    body.hidden = !expanded;
    toggle.setAttribute('aria-expanded', String(expanded));
  }
  toggle.addEventListener('click', () => setExpanded(toggle.getAttribute('aria-expanded') !== 'true'));
  toggle.addEventListener('keydown', (event) => {
    if (event.key !== 'ArrowDown') return;
    event.preventDefault();
    setExpanded(true);
    panelButtons.find((item) => !item.disabled)?.focus();
  });
  list.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      setExpanded(false);
      toggle.focus();
      return;
    }
    if (!NAVIGATION_KEYS.includes(event.key)) return;
    const focusable = panelButtons.filter((item) => !item.disabled);
    const current = focusable.indexOf(documentValue.activeElement);
    if (current < 0) return;
    event.preventDefault();
    focusable[nextLauncherIndex(current, event.key, focusable.length)]?.focus();
  });

  function syncAvailability() {
    for (const { item, descriptor, availability } of panelEntries) {
      const source = descriptor.sourceId ? sourceMap.get(descriptor.sourceId) : null;
      const sourceAvailable = !descriptor.sourceId || Boolean(source?.available);
      const visible = visibleTypes.has(descriptor.panelType);
      item.disabled = !sourceAvailable || (!layoutEditable && !visible);
      item.dataset.availability = sourceAvailable ? 'available' : source ? 'unavailable' : 'waiting';
      availability.textContent = !sourceAvailable ? (source ? 'UNAVAILABLE' : 'CATALOG WAITING')
        : layoutEditable ? 'AVAILABLE' : visible ? 'ACTIVE · OPERATE' : 'LAYOUT LOCKED';
      item.setAttribute('aria-label', `${descriptor.label} ${sourceAvailable ? visible ? 'panel 앞으로 가져오기' : layoutEditable ? 'panel 열기' : 'Layout Edit에서 열기' : '사용 불가'}`);
    }
    for (const item of layoutButtons) item.disabled = !layoutEditable || (activeActions.has(item.dataset.layoutAction) && !activePanelId);
    grid.disabled = !layoutEditable;
  }

  function update(states = [], nextActivePanelId = '') {
    visibleTypes = new Set(states.filter((state) => state.visible).map((state) => state.panelType));
    activePanelId = nextActivePanelId;
    for (const item of panelButtons) {
      const visible = visibleTypes.has(item.dataset.panelType);
      item.classList.toggle('is-active', visible);
      item.setAttribute('aria-pressed', String(visible));
    }
    syncAvailability();
  }

  function updateAvailability(sources = []) {
    sourceMap = new Map(sources.map((source) => [source.id, source]));
    syncAvailability();
  }

  function setLayoutEditable(nextEditable) {
    layoutEditable = Boolean(nextEditable);
    syncAvailability();
  }

  function destroy() {
    root.replaceChildren();
  }

  update();
  return Object.freeze({ update, updateAvailability, setLayoutEditable, setExpanded, destroy, diagnostics: () => Object.freeze({ expanded: !body.hidden, panelCount: panelButtons.length, layoutEditable }) });
}
