// Catalog operations deliberately never call parameter APPLY or pipeline APIs.
export function initializeNavigationPresetFeature({ catalog, ui, canSave, getDraft, renderOptions, sync, showToast }) {
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
  return { refresh, save };
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
      return Object.freeze({ id: entry.id, label: `사용자 · ${entry.label}`, description: '팀 공용 사용자 프리셋', values: Object.freeze({ ...validate(entry.values) }) });
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
