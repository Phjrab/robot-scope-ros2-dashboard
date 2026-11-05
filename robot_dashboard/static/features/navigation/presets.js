// Only the explicit combined action invokes the existing parameter apply handler.
export function initializeNavigationPresetFeature({ catalog, ui, canSave, getDraft, renderOptions, sync, showToast, apply, diff }) {
  let loaded = null;
  let editBaseline = null;
  const update = document.getElementById('navigationPresetUpdate');
  const combined = document.getElementById('navigationPresetApply');
  const difference = document.getElementById('navigationPresetDifference');
  const selected = () => catalog.presets.find(entry => entry.id === ui.navigationPreset.value);

  function remember(entry, values = entry?.values) {
    loaded = entry;
    editBaseline = values && { ...values };
  }
  function hasEditedDraft() {
    if (!editBaseline || !getDraft()) return false;
    try { return Object.keys(diff(editBaseline, getDraft())).length > 0; }
    catch { return true; }
  }
  function allowReplace() {
    return !hasEditedDraft() || window.confirm('저장하지 않은 편집 값을 버리고 다시 불러올까요?');
  }
  function controls({ preset, ready, invalid, pipelineActive, parameterBusy, currentDirty }) {
    const user = selected();
    const matches = user && /^[0-9a-f]{32}$/.test(user.revision) && loaded?.id === user.id && Boolean(loaded.revision);
    const changed = ready && !invalid && preset ? Object.keys(diff(preset.values, getDraft())) : [];
    difference.textContent = !ready || !preset ? '—' : invalid ? '프리셋 비교 대기' :
      '선택 프리셋과 다른 값 ' + changed.length + '개' + (changed.length ? ' · ' + changed.join(', ') : '');
    update.disabled = catalog.busy || parameterBusy || !matches || invalid || !ready || !changed.length;
    combined.disabled = catalog.busy || parameterBusy || !matches || invalid || !ready || pipelineActive || !(changed.length || currentDirty);
    if (user && !matches) difference.textContent += ' · LOAD로 편집 대상을 확인하세요.';
    if (matches && loaded.revision !== user.revision) {
      const fields = Object.entries(diff(loaded.values, user.values)).map(([key, value]) => key + '=' + value);
      difference.textContent += ' · 서버 변경 ' + fields.join(', ') + ' · 저장 시 덮어쓰기 확인';
    }
  }

  async function saveSelected(andApply) {
    const target = selected();
    if ((andApply ? combined : update).disabled || !target || !canSave()) return;
    if (loaded.revision !== target.revision &&
        !window.confirm('다른 사용자의 최신 값을 현재 편집 값으로 덮어쓸까요? 비교 항목을 확인하세요.')) return;
    try {
      const saved = await catalog.update(target, getDraft());
      if (!saved) return;
      remember(saved);
      const savedMessage = saved.label + ' · 프리셋 저장 완료';
      ui.navigationPresetMessage.textContent = savedMessage;
      if (andApply) ui.navigationPresetMessage.textContent = savedMessage + ' / ' + await apply();
    } catch (error) {
      ui.navigationPresetMessage.textContent = error.message + ' · 편집 값은 유지됩니다. 목록을 새로고침해 비교하세요.';
    }
    sync();
  }
  async function refresh() {
    try {
      if (await catalog.refresh()) {
        renderOptions();
        ui.navigationPresetMessage.textContent = '팀 공용 프리셋 목록을 불러왔습니다. 저장은 현재 Nav2 설정을 바꾸지 않습니다.';
      }
    } catch (error) {
      ui.navigationPresetMessage.textContent = `프리셋 목록 확인 실패: ${error.message}`;
    }
    sync();
  }
  async function save() {
    if (!canSave()) return;
    try {
      const id = await catalog.save(ui.navigationPresetName.value, getDraft());
      if (!id) return;
      renderOptions(id);
      remember(selected());
      ui.navigationPresetName.value = '';
      ui.navigationPresetMessage.textContent = '팀 공용 프리셋을 저장했습니다. 현재 Nav2에는 적용하지 않았습니다.';
      showToast('프리셋 저장 완료 · 실제 적용은 LOAD 후 Nav2 정지 상태에서 APPLY');
    } catch (error) {
      ui.navigationPresetMessage.textContent = `프리셋 저장 실패: ${error.message}`;
    }
    sync();
  }
  ui.navigationPresetSave.addEventListener('click', save);
  ui.navigationPresetRefresh.addEventListener('click', refresh);
  ui.navigationPresetName.addEventListener('input', sync);
  update.addEventListener('click', () => saveSelected(false));
  combined.addEventListener('click', () => saveSelected(true));
  ui.navigationPreset.addEventListener('change', sync);
  return { refresh, save, remember, controls, allowReplace, hasEditedDraft };
}

export function createNavigationPresetCatalog({ api, validate, onChange = () => {} }) {
  let presets = [];
  let busy = false;
  function normalize(payload) {
    if (!Array.isArray(payload?.presets) || payload.presets.length > 64) throw new Error('프리셋 목록 형식이 올바르지 않습니다.');
    const ids = new Set();
    return payload.presets.map((entry) => {
      if (!/^user-[0-9a-f]{32}$/.test(entry?.id) || typeof entry.label !== 'string' || !entry.label.trim() || [...entry.label].length > 64 || ids.has(entry.id)) throw new Error('프리셋 형식이 올바르지 않습니다.');
      ids.add(entry.id);
      return Object.freeze({ id: entry.id, revision: entry.revision, label: `사용자 · ${entry.label}`, description: '팀 공용 사용자 프리셋', values: Object.freeze({ ...validate(entry.values) }) });
    });
  }
  async function run(operation) {
    if (busy) return null;
    busy = true;
    onChange();
    try { return await operation(); }
    finally { busy = false; onChange(); }
  }
  return {
    get busy() { return busy; },
    get presets() { return [...presets]; },
    refresh() {
      return run(async () => {
        presets = normalize(await api('/api/v1/navigation/presets'));
        return true;
      });
    },
    update(target, draft) {
      return run(async () => {
        if (!target || !presets.includes(target) || !/^[0-9a-f]{32}$/.test(target.revision)) {
          throw new Error('사용자 프리셋을 다시 불러오세요.');
        }
        const values = { ...validate(draft) };
        const path = '/api/v1/navigation/presets';
        const payload = await api(path + '/' + encodeURIComponent(target.id), {
          method: 'PATCH', body: JSON.stringify({ base_revision: target.revision, values }),
        });
        const committed = payload?.preset;
        if (committed?.id !== target.id || !/^[0-9a-f]{32}$/.test(committed.revision)) {
          throw new Error('저장 응답 확인 실패');
        }
        let next;
        try { next = normalize(await api(path)); }
        catch { throw new Error('서버 저장 응답 수신 / 저장값 재조회 실패 / 현재 적용 생략'); }
        const saved = next.find(entry => entry.id === target.id);
        if (saved?.revision !== committed.revision || Object.keys(values).some(key => saved.values[key] !== values[key])) {
          throw new Error('재조회한 값이 저장 응답과 다릅니다. 현재 적용 생략');
        }
        presets = next;
        return saved;
      });
    },
    save(name, draft) {
      return run(async () => {
        name = String(name).normalize('NFC').trim();
        if (!name || [...name].length > 64 || /\p{C}/u.test(name)) throw new Error('프리셋 이름은 제어 문자 없이 1~64자로 입력해 주세요.');
        const values = { ...validate(draft) };
        const payload = await api('/api/v1/navigation/presets', { method: 'POST', body: JSON.stringify({ name, values }) });
        const next = normalize(payload);
        if (!next.some((entry) => entry.id === payload.preset?.id)) throw new Error('저장 응답을 확인할 수 없습니다. 목록을 새로고침해 주세요.');
        presets = next;
        return payload.preset.id;
      });
    },
  };
}
