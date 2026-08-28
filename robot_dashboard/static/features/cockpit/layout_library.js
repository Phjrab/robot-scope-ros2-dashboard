import { COCKPIT_LAYOUT_MAX_BYTES, COCKPIT_LAYOUT_NAME_MAX } from './layout_schema.js';

function make(documentValue, name, className = '', text = '') {
  const value = documentValue.createElement(name);
  if (className) value.className = className;
  value.textContent = text;
  return value;
}

function actionButton(documentValue, label, action) {
  const value = make(documentValue, 'button', '', label);
  value.type = 'button';
  value.dataset.layoutLibraryAction = action;
  return value;
}

export function createLayoutLibrary(options = {}) {
  const root = options.root;
  const documentValue = options.document || globalThis.document;
  const store = options.store;
  if (!root || !documentValue || !store) throw new TypeError('LayoutLibrary requires root, document, and store.');
  root.replaceChildren();
  root.className = 'cockpit-layout-library';

  const toggle = actionButton(documentValue, 'LAYOUTS', 'toggle');
  toggle.className = 'cockpit-layout-library-toggle';
  toggle.setAttribute('aria-expanded', 'false');
  const body = make(documentValue, 'div', 'cockpit-layout-library-body');
  body.hidden = true;
  const heading = make(documentValue, 'strong', '', 'WORKSPACE PRESETS');
  const profile = make(documentValue, 'small', 'cockpit-layout-profile', 'PROFILE · WAITING');
  const name = make(documentValue, 'input');
  name.type = 'text';
  name.maxLength = COCKPIT_LAYOUT_NAME_MAX;
  name.placeholder = 'preset name';
  name.setAttribute('aria-label', '새 Cockpit preset 이름');
  const saveAs = actionButton(documentValue, 'SAVE AS', 'save-as');
  const createRow = make(documentValue, 'div', 'cockpit-layout-library-row');
  createRow.append(name, saveAs);

  const select = make(documentValue, 'select');
  select.setAttribute('aria-label', 'Cockpit preset 목록');
  select.dataset.cockpitPresetList = '';
  const presetActions = make(documentValue, 'div', 'cockpit-layout-library-actions');
  const buttons = new Map();
  for (const [label, action] of [['LOAD', 'load'], ['OVERWRITE', 'overwrite'], ['DEFAULT', 'default'], ['DELETE', 'delete'], ['EXPORT', 'export']]) {
    const value = actionButton(documentValue, label, action);
    buttons.set(action, value);
    presetActions.append(value);
  }

  const reset = actionButton(documentValue, 'RESET PROFILE LAYOUTS', 'reset');
  buttons.set('reset', reset);
  const importLabel = make(documentValue, 'label', 'cockpit-layout-import-file', 'IMPORT JSON FILE');
  const importFile = make(documentValue, 'input');
  importFile.type = 'file';
  importFile.accept = '.json,application/json';
  importLabel.append(importFile);
  const importText = make(documentValue, 'textarea');
  importText.maxLength = COCKPIT_LAYOUT_MAX_BYTES;
  importText.placeholder = 'JSON을 붙여넣고 PREVIEW를 누르세요.';
  importText.setAttribute('aria-label', 'Cockpit layout import JSON');
  const preview = actionButton(documentValue, 'PREVIEW IMPORT', 'preview');
  const applyImport = actionButton(documentValue, 'APPLY IMPORT', 'apply-import');
  buttons.set('preview', preview);
  buttons.set('apply-import', applyImport);
  const importActions = make(documentValue, 'div', 'cockpit-layout-library-actions');
  importActions.append(preview, applyImport);
  const status = make(documentValue, 'small', 'cockpit-layout-library-status', '저장된 preset이 없습니다.');
  status.setAttribute('role', 'status');
  body.append(heading, profile, createRow, select, presetActions, reset, importLabel, importText, importActions, status);
  root.append(toggle, body);

  let layoutEditable = false;
  let pendingImport = null;

  function selectedName() { return select.value || ''; }

  function setStatus(message, error = false) {
    status.textContent = message;
    status.dataset.error = String(error);
  }

  function refresh(preferred = selectedName()) {
    const snapshot = store.snapshot();
    profile.textContent = `PROFILE · ${snapshot.profileId || 'WAITING'}`;
    select.replaceChildren();
    for (const preset of snapshot.presets) {
      const option = make(documentValue, 'option');
      option.value = preset.name;
      option.textContent = `${preset.name}${snapshot.defaultPreset === preset.name ? ' · DEFAULT' : ''} · ${preset.panelCount} PANELS`;
      select.append(option);
    }
    select.value = snapshot.presets.some((preset) => preset.name === preferred) ? preferred : snapshot.defaultPreset || snapshot.presets[0]?.name || '';
    syncDisabled();
    if (snapshot.corrupted) setStatus('손상된 저장소를 무시하고 기본 배치로 복구했습니다.', true);
    else if (!snapshot.storageAvailable) setStatus('브라우저 layout 저장소를 사용할 수 없습니다. 기본 배치로 동작합니다.', true);
  }

  function syncDisabled() {
    const hasPreset = Boolean(selectedName());
    saveAs.disabled = !layoutEditable;
    select.disabled = !hasPreset;
    for (const action of ['load', 'overwrite', 'default', 'delete']) buttons.get(action).disabled = !layoutEditable || !hasPreset;
    buttons.get('export').disabled = !hasPreset;
    reset.disabled = !layoutEditable;
    preview.disabled = !layoutEditable || !importText.value.trim();
    applyImport.disabled = !layoutEditable || !pendingImport;
    importFile.disabled = !layoutEditable;
    importText.disabled = !layoutEditable;
  }

  function run(callback) {
    try { callback(); } catch (error) { setStatus(error?.message || 'Layout 작업을 완료하지 못했습니다.', true); }
  }

  function setExpanded(expanded) { body.hidden = !expanded; toggle.setAttribute('aria-expanded', String(expanded)); }
  toggle.addEventListener('click', () => setExpanded(body.hidden));
  select.addEventListener('change', syncDisabled);
  name.addEventListener('input', syncDisabled);
  importText.addEventListener('input', () => { pendingImport = null; syncDisabled(); });
  importFile.addEventListener('change', () => run(() => {
    const file = importFile.files?.[0];
    if (!file || file.size > COCKPIT_LAYOUT_MAX_BYTES) throw new RangeError('Layout JSON file is too large.');
    const reader = new FileReader();
    reader.addEventListener('load', () => { importText.value = String(reader.result || ''); pendingImport = null; syncDisabled(); });
    reader.addEventListener('error', () => setStatus('Layout JSON file을 읽지 못했습니다.', true));
    reader.readAsText(file);
  }));
  saveAs.addEventListener('click', () => run(() => {
    const document = options.captureLayout(name.value);
    store.save(document);
    name.value = '';
    refresh(document.name);
    setStatus(`${document.name} preset을 저장했습니다.`);
  }));
  buttons.get('overwrite').addEventListener('click', () => run(() => {
    const document = options.captureLayout(selectedName());
    store.save(document);
    refresh(document.name);
    setStatus(`${document.name} preset을 현재 배치로 갱신했습니다.`);
  }));
  buttons.get('load').addEventListener('click', () => run(() => {
    const document = store.get(selectedName());
    if (!document || options.applyLayout(document) === false) throw new Error('Preset을 적용하지 못했습니다.');
    setStatus(`${document.name} preset을 적용했습니다.`);
  }));
  buttons.get('default').addEventListener('click', () => run(() => {
    store.setDefault(selectedName());
    refresh(selectedName());
    setStatus(`${selectedName()} preset을 기본 배치로 지정했습니다.`);
  }));
  buttons.get('delete').addEventListener('click', () => run(() => {
    const removed = selectedName();
    store.remove(removed);
    refresh();
    setStatus(`${removed} preset을 삭제했습니다.`);
  }));
  reset.addEventListener('click', () => run(() => {
    store.reset();
    options.resetLayout();
    pendingImport = null;
    importText.value = '';
    refresh();
    setStatus('현재 profile의 저장 배치와 panel 배치를 초기화했습니다.');
  }));
  buttons.get('export').addEventListener('click', () => run(() => {
    const presetName = selectedName();
    const blob = new Blob([store.exportJson(presetName)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = make(documentValue, 'a');
    anchor.href = url;
    anchor.download = `${presetName.replace(/[^a-zA-Z0-9_-]+/g, '-') || 'cockpit-layout'}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus(`${presetName} preset JSON을 내보냈습니다.`);
  }));
  preview.addEventListener('click', () => run(() => {
    pendingImport = store.previewImport(importText.value);
    setStatus(`PREVIEW · ${pendingImport.name} · ${pendingImport.panels.length} PANELS · 아직 적용되지 않음`);
    syncDisabled();
  }));
  applyImport.addEventListener('click', () => run(() => {
    if (!pendingImport) throw new Error('먼저 import preview를 확인하세요.');
    store.save(pendingImport);
    if (options.applyLayout(pendingImport) === false) throw new Error('Import layout을 적용하지 못했습니다.');
    const applied = pendingImport.name;
    pendingImport = null;
    importText.value = '';
    refresh(applied);
    setStatus(`${applied} import를 저장하고 적용했습니다.`);
  }));

  function setLayoutEditable(next) { layoutEditable = Boolean(next); syncDisabled(); }
  function setProfile() { pendingImport = null; importText.value = ''; refresh(); }
  function destroy() { root.replaceChildren(); }

  refresh();
  return Object.freeze({ setLayoutEditable, setProfile, setExpanded, refresh, destroy, diagnostics: () => Object.freeze({ expanded: !body.hidden, layoutEditable, pendingImport: pendingImport?.name || null, ...store.snapshot() }) });
}
