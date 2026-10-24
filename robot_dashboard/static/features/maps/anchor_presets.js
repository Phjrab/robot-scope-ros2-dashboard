// Presets fill editable map coordinates only; they never create a live anchor.
export const ANCHOR_FIELDS = ['x', 'y', 'z', 'roll', 'pitch', 'yaw'];
export function validAnchorPose(pose) {
  return pose && typeof pose === 'object' && !Array.isArray(pose)
    && Object.keys(pose).length === 6 && ANCHOR_FIELDS.every(k => typeof pose[k] === 'number'
      && Number.isFinite(pose[k]) && Math.abs(pose[k]) <= (['x', 'y', 'z'].includes(k) ? 1000 : 360));
}
export function compatibleAnchorPreset(entry, map) {
  const v = entry?.values;
  return /^user-[a-f0-9]{32}$/.test(entry?.id || '') && typeof entry.label === 'string'
    && entry.label.length > 0 && entry.label.length <= 64 && map
    && v?.map_id === map.id && v.map_revision === map.revision && v.map_frame === map.frame
    && ['FASTLIO_IMU', 'UNVERIFIED_BODY'].includes(v.pose_reference)
    && v.units === 'metres_degrees' && typeof v.saved_at === 'string' && Number.isFinite(Date.parse(v.saved_at))
    && validAnchorPose(v.pose);
}

export function initializeAnchorPresets({ host, getState, getReference, readPose, fillPose }) {
  const panel = document.createElement('div'); panel.className = 'saved-anchor-presets';
  panel.innerHTML = `<div class="saved-anchor-preset-row">
    <label for="savedAnchorPreset">저장된 초기값<select id="savedAnchorPreset"><option value="">저장된 초기값 없음</option></select></label>
    <button id="savedAnchorPresetLoad" type="button">초기값 불러오기</button>
    <button id="savedAnchorPresetRefresh" type="button">목록 새로고침</button></div>
    <div class="saved-anchor-preset-row"><label for="savedAnchorPresetName">프리셋 이름<input id="savedAnchorPresetName" maxlength="64" placeholder="예: 출입구 · 서 있는 자세" autocomplete="off"></label>
    <button id="savedAnchorPresetSave" type="button">입력값 저장</button>
    <button id="savedAnchorPresetCurrent" type="button">현재 보정 위치로 채우기</button></div>
    <small>서버에 지도별로 저장됩니다. 불러온 값은 근사 초기값이며 위치·방향 확인 후 새 pose에 연결하세요.</small>
    <small id="savedAnchorPresetReference"></small><small id="savedAnchorPresetStatus" role="status"></small>`;
  host.prepend(panel);
  const el = suffix => panel.querySelector('#savedAnchorPreset' + suffix);
  let map = null, key = '', entries = [], pending = false, controller = null, token = 0, disposed = false;
  const mapKey = m => m ? JSON.stringify([m.id, m.revision, m.frame]) : '';
  const message = text => { el('Status').textContent = text; };
  function controls() {
    const state = getState();
    el('').disabled = pending || !entries.length;
    el('Load').disabled = pending || !entries.some(item => item.id === el('').value);
    el('Refresh').disabled = pending || !map;
    el('Save').disabled = pending || !map;
    el('Current').disabled = pending || !state.pose || !state.anchor?.accepted_registration;
    el('Reference').textContent = `저장 좌표 기준: ${getReference() === 'FASTLIO_IMU' ? 'FAST-LIO IMU' : '본체 기준 미검증'} · 위치 m / 각도 °`;
  }
  function options(selected = el('').value) {
    el('').replaceChildren();
    if (!entries.length) { const option = document.createElement('option'); option.value = ''; option.textContent = '저장된 초기값 없음'; el('').append(option); }
    for (const item of entries) {
      const option = document.createElement('option'); option.value = item.id;
      option.textContent = item.label; el('').append(option);
    }
    if (entries.some(item => item.id === selected)) el('').value = selected;
    controls();
  }
  async function request(method) {
    if (!map || pending) return;
    const target = { ...map }, targetKey = key, revision = ++token;
    let body;
    if (method === 'POST') {
      const pose = readPose(), name = el('Name').value.trim();
      if (!validAnchorPose(pose) || !name || name.length > 64) { message('이름과 위치·방향 6개 값을 확인해 주세요.'); return; }
      body = { name, map_revision: target.revision, map_frame: target.frame, pose_reference: getReference(), pose };
    }
    controller = new AbortController(); const activeController = controller;
    const timeout = setTimeout(() => activeController.abort(), 8000);
    pending = true; controls();
    try {
      const response = await fetch(`/api/v1/observations/anchor-presets/${target.id}`, {
        method, cache: 'no-store', signal: activeController.signal,
        ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}),
      });
      const result = await response.json();
      if (disposed || token !== revision || key !== targetKey) return;
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : `HTTP ${response.status}`);
      if (result.approximate_only !== true || result.requires_reanchor !== true) throw new Error('프리셋 응답을 확인할 수 없습니다.');
      if (method === 'POST') {
        if (!compatibleAnchorPreset(result.preset, target)) throw new Error('저장 결과의 지도·좌표 기준이 다릅니다.');
        entries = [...entries.filter(item => item.id !== result.preset.id), result.preset]; options(result.preset.id);
        message(`“${result.preset.label}” 저장 완료 · ${new Date(result.preset.values.saved_at).toLocaleString()} (서버 저장 시각)`);
      } else {
        if (result.map?.map_id !== target.id || result.map.map_revision !== target.revision || result.map.map_frame !== target.frame
            || !Array.isArray(result.presets) || result.presets.length > 64
            || !result.presets.every(item => compatibleAnchorPreset(item, target))) throw new Error('현재 지도와 호환되는 초기값 목록이 아닙니다.');
        entries = result.presets; options();
        message(result.incompatible_count ? '지도 버전이 다른 초기값은 목록에서 제외했습니다.' : `불러올 수 있는 초기값 ${entries.length}개`);
      }
    } catch (error) {
      if (!disposed && token === revision && key === targetKey) message(method === 'POST'
        ? `저장 확인 실패: ${error.message} · 자동 재시도하지 않습니다. 목록을 확인해 주세요.` : `목록 확인 실패: ${error.message}`);
    } finally {
      clearTimeout(timeout);
      if (token === revision) { pending = false; controller = null; controls(); }
    }
  }
  el('').addEventListener('change', controls);
  el('Refresh').addEventListener('click', () => { void request('GET'); });
  el('Save').addEventListener('click', () => { void request('POST'); });
  el('Load').addEventListener('click', () => {
    const entry = entries.find(item => item.id === el('').value);
    if (!compatibleAnchorPreset(entry, getState().map)) { message('현재 지도와 호환되는 초기값을 선택해 주세요.'); return; }
    try {
      fillPose(entry.values.pose, entry.values.pose_reference); el('Name').value = entry.label;
      message(`“${entry.label}” 입력값을 불러왔습니다. 현재 위치·방향을 확인하고 기준점을 연결해 주세요.`);
    } catch (error) { message(error.message); }
  });
  el('Current').addEventListener('click', () => {
    const state = getState();
    if (!state.pose || !state.anchor?.accepted_registration) { message('신선한 지도 보정 위치를 먼저 확인해 주세요.'); return; }
    const pose = Object.fromEntries(ANCHOR_FIELDS.map(k => [k, state.pose[k] * (['x', 'y', 'z'].includes(k) ? 1 : 180 / Math.PI)]));
    try { fillPose(pose, state.pose_reference); message('현재 보정 위치로 채웠습니다. 수정·저장하거나 확인 후 다시 연결할 수 있습니다.'); }
    catch (error) { message(error.message); }
  });
  return {
    render() {
      const next = getState().map, nextKey = mapKey(next);
      if (nextKey !== key) {
        token++; controller?.abort(); controller = null; pending = false; key = nextKey; map = next; entries = [];
        el('Name').value = ''; message(''); options(); if (map) void request('GET');
      }
      controls();
    },
    destroy() { disposed = true; token++; controller?.abort(); panel.remove(); },
  };
}
