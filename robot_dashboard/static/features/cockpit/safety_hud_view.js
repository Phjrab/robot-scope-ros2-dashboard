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

export function safetyStatusLabel(projected) {
  if (projected['software-stop'] === 'LATCHED') return '소프트웨어 정지 유지';
  if (projected.armed.includes('UNKNOWN')) return projected.armed.includes('LOCKED') ? '제어 잠김 · 상태 확인 필요' : '제어 상태 확인 필요';
  if (projected['control-source'] === 'NAVIGATION' && projected.armed === 'ARMED') return '수동 제어 · 주행 파이프라인 동시 활성';
  if (projected.tone === 'danger' && ['WAITING', 'STALE', 'UNKNOWN'].includes(projected.lowstate)
    && (projected.armed === 'ARMED' || projected['control-source'] === 'NAVIGATION')) return '로봇 상태 수신 확인 필요';
  if (projected['control-source'] === 'NAVIGATION') return '주행 파이프라인 실행 중';
  if (projected.armed === 'ARMED') return '수동 제어 활성';
  return projected['control-bridge'] === 'READY' ? '제어 해제 · 연결 준비됨' : '제어 해제 · 연결 확인 필요';
}

export function createSafetyHudView(options = {}) {
  const documentValue = options.document || globalThis.document;
  const root = options.root;
  if (!documentValue || !root) throw new TypeError('SafetyHudView requires document and root.');
  root.replaceChildren();
  root.className = 'cockpit-safety-hud';
  root.setAttribute('aria-label', '제어 상태와 소프트웨어 정지');
  let expanded = false;

  const header = element(documentValue, 'div', 'cockpit-safety-header');
  const identity = element(documentValue, 'div', 'cockpit-safety-identity');
  const status = element(documentValue, 'strong', '', '제어 상태 확인 필요');
  identity.append(status);
  const mode = element(documentValue, 'strong', 'cockpit-layout-mode', '관측 중');
  mode.dataset.safetyField = 'layout-mode';
  const edit = element(documentValue, 'button', '', '배치 편집');
  edit.type = 'button';
  edit.dataset.cockpitLayoutAction = 'edit';
  const apply = element(documentValue, 'button', '', '저장·닫기');
  apply.type = 'button';
  apply.dataset.cockpitLayoutAction = 'apply';
  const modeActions = element(documentValue, 'div', 'cockpit-layout-mode-actions');
  modeActions.append(mode, edit, apply);
  const saveStatus = element(documentValue, 'span', 'cockpit-layout-save-status', '');
  saveStatus.setAttribute('role', 'status');
  modeActions.append(saveStatus);
  const summary = element(documentValue, 'span', 'cockpit-safety-summary', 'ARM UNKNOWN · DEADMAN UNKNOWN · BRIDGE UNKNOWN · LEASE UNKNOWN');
  const toggle = element(documentValue, 'button', 'cockpit-safety-toggle', '상세 펼치기');
  toggle.type = 'button';
  toggle.setAttribute('aria-expanded', 'false');
  toggle.setAttribute('aria-controls', 'cockpitSafetyDetails');
  header.append(identity, summary, toggle);
  const layoutRoot = documentValue.querySelector?.('#cockpitLayoutModeActions');
  (layoutRoot || header).append(modeActions);

  const metrics = element(documentValue, 'div', 'cockpit-safety-metrics');
  metrics.id = 'cockpitSafetyDetails';
  metrics.hidden = true;
  const fields = new Map();
  for (const [label, field] of [
    ['제어 주체', 'control-source'], ['제어 권한 · ARM', 'armed'], ['데드맨', 'deadman'],
    ['소프트웨어 정지', 'software-stop'], ['제어 연결', 'control-bridge'], ['제어 점유', 'lease'], ['로봇 연결', 'go2-link'],
    ['운영 모드', 'operation-mode'], ['대회 잠금', 'competition-lock'], ['인식 권한', 'perception-authority'], ['데이터 수집', 'dataset'],
    ['로봇 상태 · LowState', 'lowstate'], ['배터리', 'battery'], ['전후 속도 · VX', 'vx'], ['좌우 속도 · VY', 'vy'],
    ['회전 속도 · WZ', 'wz'], ['속도 배율', 'speed-scale'],
  ]) {
    const entry = metric(documentValue, label, field);
    metrics.append(entry.item);
    fields.set(field, entry.value);
  }

  const stop = element(documentValue, 'button', 'cockpit-fixed-stop');
  stop.type = 'button';
  stop.dataset.cockpitSoftwareStop = '';
  stop.append(element(documentValue, 'strong', '', 'STOP · 소프트웨어 정지'), element(documentValue, 'small', '', '물리 E-STOP 아님'));
  const physicalReminder = element(documentValue, 'p', 'cockpit-physical-stop-reminder', '물리 비상정지의 위치와 접근 가능 상태를 현장에서 확인하세요. 대시보드 STOP은 물리 비상정지가 아닙니다.');
  physicalReminder.hidden = true;
  const stopFeedback = element(documentValue, 'output', 'software-stop-feedback', '서버 STOP 요청 결과 · 아직 요청하지 않음');
  stopFeedback.id = 'softwareStopFeedback';
  stopFeedback.setAttribute('role', 'status');
  root.append(header, metrics, physicalReminder, stop, stopFeedback);

  edit.addEventListener('click', () => options.onRequestEdit?.());
  apply.addEventListener('click', () => options.onApply?.());
  stop.addEventListener('click', () => options.onStop?.());
  toggle.addEventListener('click', () => setExpanded(!expanded));

  function setExpanded(value) {
    expanded = Boolean(value);
    root.dataset.expanded = String(expanded);
    metrics.hidden = !expanded;
    physicalReminder.hidden = !expanded;
    toggle.textContent = expanded ? '상세 접기' : '상세 펼치기';
    toggle.setAttribute('aria-expanded', String(expanded));
  }

  function render(projected, layoutState) {
    root.dataset.tone = projected.tone;
    root.dataset.layoutMode = layoutState.mode;
    modeActions.dataset.layoutMode = layoutState.mode;
    for (const [field, value] of fields) {
      value.textContent = projected[field];
      value.dataset.state = String(projected[field]).toLowerCase();
    }
    status.textContent = safetyStatusLabel(projected);
    status.dataset.state = projected.armed.toLowerCase();
    summary.textContent = `ARM ${projected.armed} · DEADMAN ${projected.deadman} · BRIDGE ${projected['control-bridge']} · LEASE ${projected.lease}`;
    mode.textContent = layoutState.mode === 'layout-edit' ? '배치 편집 중' : layoutState.armed ? '배치 잠김' : '관측 중';
    mode.dataset.armed = String(layoutState.armed);
    edit.disabled = layoutState.armed || layoutState.mode === 'layout-edit';
    apply.disabled = layoutState.mode !== 'layout-edit';
    edit.setAttribute('aria-pressed', String(layoutState.mode === 'layout-edit'));
    stop.setAttribute('aria-label', '대시보드 SOFTWARE STOP 실행 · 물리 E-stop 아님');
  }

  function destroy() {
    if (layoutRoot) layoutRoot.replaceChildren();
    root.replaceChildren();
  }

  setExpanded(false);
  return Object.freeze({ render, setExpanded, setLayoutSaveStatus: (text) => { saveStatus.textContent = text; }, snapshot: () => Object.freeze({ expanded }), destroy });
}
