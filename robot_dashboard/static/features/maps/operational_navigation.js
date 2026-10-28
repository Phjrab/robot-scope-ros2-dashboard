/** Explicit stored-map source selection. All movement uses existing Nav2 UI. */
export function initializeOperationalNavigation({ host, getSeed }) {
  const panel = document.createElement('details');
  panel.innerHTML = `<summary>3D 위치추정을 주행에 사용</summary>
    <p>정합한 3D 사본과 연결할 기존 2D 주행 지도를 선택하세요. 주행 시작 뒤 현재 정지 위치를 확인하면 저장 지도 보정이 시작됩니다.</p>
    <label>연결할 2D 주행 지도 <select aria-label="3D 위치추정에 연결할 2D 지도"></select></label>
    <div class="saved-live-actions"><button type="button" data-op="refresh">지도·상태 새로고침</button><button type="button" data-op="select">이 3D 지도로 위치추정 준비</button><button type="button" data-op="confirm">현재 정지 위치 확인 · 정합 시작</button><button type="button" data-op="clear">기존 2D 위치 모드 선택</button></div>
    <p role="status"></p>`;
  host.append(panel);
  const select = panel.querySelector('select'), note = panel.querySelector('[role=status]');
  const button = key => panel.querySelector(`[data-op=${key}]`);
  let state = null, maps = [], disposed = false, busy = false;
  async function api(path, method = 'GET', body) {
    const response = await fetch(path, { method, cache: 'no-store', headers: { 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(15000) });
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : `요청 실패 (${response.status})`);
    return value;
  }
  function draw() {
    const seed = getSeed();
    button('select').disabled = busy || !seed || !select.value;
    button('confirm').disabled = busy || !state?.initial_pose_confirmation;
    button('clear').disabled = busy || !state?.selected;
  }
  async function refresh() {
    const [next, catalog] = await Promise.all([api('/api/v1/navigation/operational-3d'), api('/api/v1/saved-maps')]);
    if (disposed) return;
    state = next; maps = (catalog.maps || []).filter(map => map.kind === 'occupancy2d' && map.manageable);
    const previous = select.value;
    select.replaceChildren(...maps.map(map => { const option = document.createElement('option'); option.value = map.id; option.textContent = `${map.name} · ${map.revision.slice(0, 8)}`; return option; }));
    if (maps.some(map => map.id === previous)) select.value = previous;
    if (!previous && state.selected) select.value = state.selected.navigation_2d.map_id;
    const runtime = state.runtime;
    note.textContent = runtime ? `${state.runtime_fresh ? '' : '연결 오래됨 · '}${runtime.state} · 지도 보정 ${runtime.correction_sequence}회 · ${runtime.reference_sha256.slice(0, 12)}`
      : state.selected ? '지도 묶음 선택됨 · 기존 주행 시작 후 정지 위치를 확인하세요.'
        : state.calibration_available ? '3D 지도를 정합한 뒤 기존 2D 지도와 묶어 선택하세요.' : '장비 연결 후 기존 TF·본체 장착·지도 정렬 확인이 필요합니다.';
    draw();
  }
  panel.addEventListener('toggle', () => { if (panel.open) void run(refresh); });
  async function run(action) {
    if (busy || disposed) return;
    busy = true; draw();
    try { await action(); } catch (error) { if (!disposed) note.textContent = error.message; }
    finally { busy = false; if (!disposed) draw(); }
  }
  button('refresh').onclick = () => void run(refresh);
  button('select').onclick = () => void run(async () => {
    const seed = getSeed(), nav = maps.find(map => map.id === select.value);
    if (!seed || !nav) throw new Error('현재 지도 정합과 2D 지도 선택이 필요합니다.');
    state = await api('/api/v1/navigation/operational-3d', 'POST', {
      map_id: seed.map.id, map_revision: seed.map.revision, navigation_map_id: nav.id,
      navigation_map_revision: nav.revision, seed_pose: seed.pose,
      ...(seed.course ? { course_region: seed.course } : {}),
    });
    await refresh();
  });
  button('confirm').onclick = () => void run(async () => {
    if (!state?.initial_pose_confirmation) return;
    await api('/api/v1/navigation/initial-pose', 'POST', state.initial_pose_confirmation);
    note.textContent = '정지 위치 확인 요청됨 · 실제 지도 보정 갱신을 새로고침으로 확인하세요.';
  });
  button('clear').onclick = () => void run(async () => { state = await api('/api/v1/navigation/operational-3d', 'DELETE'); await refresh(); });
  draw();
  return { render: draw, destroy() { disposed = true; panel.remove(); } };
}
