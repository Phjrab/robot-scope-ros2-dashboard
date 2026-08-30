function element(documentValue, name, className = '', text = '') {
  const value = documentValue.createElement(name);
  if (className) value.className = className;
  value.textContent = text;
  return value;
}

function metric(documentValue, label, field) {
  const item = element(documentValue, 'div', 'cockpit-safety-metric');
  const name = element(documentValue, 'span', '', label);
  const value = element(documentValue, 'strong', '', 'UNKNOWN');
  value.dataset.safetyField = field;
  item.append(name, value);
  return { item, value };
}

export function createSafetyHudView(options = {}) {
  const documentValue = options.document || globalThis.document;
  const root = options.root;
  if (!documentValue || !root) throw new TypeError('SafetyHudView requires document and root.');
  root.replaceChildren();
  root.className = 'cockpit-safety-hud';
  root.setAttribute('aria-label', 'Cockpit 고정 Safety HUD');

  const header = element(documentValue, 'div', 'cockpit-safety-header');
  const identity = element(documentValue, 'div', 'cockpit-safety-identity');
  identity.append(element(documentValue, 'span', '', 'FIXED SAFETY HUD'), element(documentValue, 'strong', '', 'CONTROL AUTHORITY'));
  const mode = element(documentValue, 'strong', 'cockpit-layout-mode', 'OPERATE');
  mode.dataset.safetyField = 'layout-mode';
  const edit = element(documentValue, 'button', '', 'EDIT LAYOUT');
  edit.type = 'button';
  edit.dataset.cockpitLayoutAction = 'edit';
  const apply = element(documentValue, 'button', '', 'APPLY / EXIT');
  apply.type = 'button';
  apply.dataset.cockpitLayoutAction = 'apply';
  const modeActions = element(documentValue, 'div', 'cockpit-layout-mode-actions');
  modeActions.append(mode, edit, apply);
  header.append(identity, modeActions);

  const metrics = element(documentValue, 'div', 'cockpit-safety-metrics');
  const fields = new Map();
  for (const [label, field] of [
    ['CONTROL SOURCE', 'control-source'], ['ARM', 'armed'], ['DEADMAN', 'deadman'],
    ['SOFTWARE STOP', 'software-stop'], ['CONTROL BRIDGE', 'control-bridge'], ['CONTROL LEASE', 'lease'], ['GO2 LINK', 'go2-link'],
    ['OPERATION MODE', 'operation-mode'], ['COMPETITION LOCK', 'competition-lock'], ['PERCEPTION AUTHORITY', 'perception-authority'], ['DATASET', 'dataset'],
    ['LOWSTATE', 'lowstate'], ['BATTERY', 'battery'], ['VX', 'vx'], ['VY', 'vy'],
    ['WZ', 'wz'], ['SPEED SCALE', 'speed-scale'],
  ]) {
    const entry = metric(documentValue, label, field);
    metrics.append(entry.item);
    fields.set(field, entry.value);
  }

  const stop = element(documentValue, 'button', 'cockpit-fixed-stop');
  stop.type = 'button';
  stop.dataset.cockpitSoftwareStop = '';
  stop.append(element(documentValue, 'strong', '', 'DASHBOARD SOFTWARE STOP'), element(documentValue, 'small', '', '물리 E-STOP 아님'));
  const physicalReminder = element(documentValue, 'p', 'cockpit-physical-stop-reminder', 'PHYSICAL STOP 위치와 접근 가능 상태를 현장에서 확인하세요 · Competition Lock / Dashboard STOP은 물리 E-STOP이 아닙니다.');
  root.append(header, metrics, physicalReminder, stop);

  edit.addEventListener('click', () => options.onRequestEdit?.());
  apply.addEventListener('click', () => options.onApply?.());
  stop.addEventListener('click', () => options.onStop?.());

  function render(projected, layoutState) {
    root.dataset.tone = projected.tone;
    root.dataset.layoutMode = layoutState.mode;
    for (const [field, value] of fields) value.textContent = projected[field];
    mode.textContent = layoutState.mode === 'layout-edit' ? 'LAYOUT EDIT' : 'OPERATE';
    mode.dataset.armed = String(layoutState.armed);
    edit.disabled = layoutState.armed || layoutState.mode === 'layout-edit';
    apply.disabled = layoutState.mode !== 'layout-edit';
    edit.setAttribute('aria-pressed', String(layoutState.mode === 'layout-edit'));
    stop.setAttribute('aria-label', '대시보드 SOFTWARE STOP 실행 · 물리 E-stop 아님');
  }

  function destroy() {
    root.replaceChildren();
  }

  return Object.freeze({ render, destroy });
}
