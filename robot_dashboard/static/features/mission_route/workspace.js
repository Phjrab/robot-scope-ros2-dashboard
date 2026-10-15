import { createDraftStore, newVisit, resolvedTarget, headingToNext, worldToGrid, gridToWorld, requestId } from './state.js';
import { createPlanClient } from './client.js';
import { familyPins } from '../route_planner/spatial_editor.js';

const NS = 'http://www.w3.org/2000/svg';
export function createMissionWorkspace({ host, client: missionClient, navigationAdapter, document: doc = globalThis.document, planClient = createPlanClient() }) {
  const make = (tag, text = '') => { const n = doc.createElement(tag); n.textContent = text; return n; };
  const svg = (tag, attrs = {}) => { const n = doc.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v)); return n; };
  const root = make('section'); root.className = 'mr-workspace'; root.setAttribute('aria-label', '경로·미션 지도 작업');
  if (!doc.querySelector('link[data-mission-route-style]')) { const style = make('link'); style.rel = 'stylesheet'; style.href = new URL('./workspace.css', import.meta.url).href; style.dataset.missionRouteStyle = 'true'; doc.head.append(style); }
  const storageKey = 'robot-scope:mission-route-draft:v1';
  const state = createDraftStore((snapshot) => {
    try {
      if (snapshot.draft) globalThis.sessionStorage?.setItem(storageKey, JSON.stringify({ schema: 1, draft: snapshot.draft, saved: snapshot.saved, selected: snapshot.selected, dirty: snapshot.dirty }));
      else globalThis.sessionStorage?.removeItem(storageKey);
    } catch { /* Storage may be disabled; in-memory edits remain available. */ }
  });
  let restored = false;
  try { const raw = globalThis.sessionStorage?.getItem(storageKey); const value = raw && JSON.parse(raw); restored = value?.schema === 1 && state.restore(value); } catch { /* Invalid tab-local data is never executed. */ }
  let map = null, annotations = null, background = '', view = [0, 0, 640, 400], context = null, currentRun = null, release = null, destroyed = false, active = false, busy = false, mode = 'edit', gesture = null, hypothetical = null, selectedDrawer = 'visits';
  let pendingActions = 0;
  let epoch = 0, observing = false, lastObservation = 0, uncertainAction = null, reportGeneration = null;
  let staleReasons = [], geometryCurrent = false;
  let editorMap = null, runMission = null, navigationRelease = null, sourceRoute = null, sourceRouteKey = '', connectionStale = true, lastReceived = null;
  let comparison = null, lastReport = null;
  const invalidInputs = new Map();
  const header = make('header'), left = make('aside'), main = make('main'), right = make('aside'), footer = make('footer'); right.className = 'mr-inspector';
  const identity = make('div'), modeActions = make('div'), definitionActions = make('div');
  identity.className = 'mr-identity'; modeActions.className = 'mr-mode-actions'; definitionActions.className = 'mr-definition-actions';
  modeActions.setAttribute('role', 'group'); modeActions.setAttribute('aria-label', '미션 작업 모드');
  header.append(identity, modeActions, definitionActions);
  const name = make('input'); name.value = state.snapshot().draft?.label || '새 미션'; name.maxLength = 64; name.setAttribute('aria-label', '미션 이름');
  const mapLabel = make('span', 'navigation 지도 · 운영 위치 미확인');
  const definitionMode = make('span', 'FLEXIBLE · STOP/TASK 순서 방문');
  const status = make('div', '저장·검사·compile은 이동 명령을 보내지 않습니다.'); status.className = 'mr-status'; status.setAttribute('role', 'status');
  const connectionStatus = make('p', '서버 상태 확인 중'); connectionStatus.dataset.connectionStatus = 'pending';
  const takeoverStatus = make('p', '수동 전환 · IDLE · 자동 ARM 없음'); takeoverStatus.dataset.takeoverStatus = 'IDLE';
  const button = (parent, label, action, interrupt = false) => { const n = make('button', label); n.type = 'button'; n.addEventListener('click', () => run(action, interrupt)); parent.append(n); return n; };
  const select = (parent, label) => { const wrapper = make('label', label); const n = make('select'); n.setAttribute('aria-label', label); wrapper.append(n); parent.append(wrapper); return n; };
  const option = (value, label) => { const n = make('option', label); n.value = value; return n; };
  const mapSelect = select(identity, '지도'); const routeSelect = select(left, 'E1 저장 경로'); const planSelect = select(left, '저장 미션');
  const nameLabel = make('label', '미션 이름'); nameLabel.append(name); identity.prepend(nameLabel);
  const contextSummary = make('div'); contextSummary.className = 'mr-context'; contextSummary.append(mapLabel, definitionMode); header.append(contextSummary);
  for (const [value, label] of [['edit', '편집'], ['inspect', '검사'], ['execute', '실행']]) button(modeActions, label, async () => { await changeMode(value); status.textContent = `${label} 모드 · 방문 변경은 편집 모드에서만 적용됩니다.`; });
  const drawers = make('div'); drawers.className = 'mr-compact-tabs';
  for (const [value, label] of [['visits', '방문 목록'], ['inspector', '방문 설정']]) button(drawers, label, () => { selectedDrawer = value; updateDrawers(); });
  root.append(header, drawers, left, main, right, footer); host.append(root);
  const toolbar = make('div'); toolbar.className = 'mr-toolbar'; const tool = select(toolbar, '지도 도구'); tool.append(option('select', '선택'), option('add', '방문 추가'), option('move', '방문 이동'), option('pan', '지도 이동'), option('start', '가상 시작점 · 미리보기 전용'));
  button(toolbar, '되돌리기', () => { requireEditing(); invalidInputs.clear(); state.undo(); name.value = state.snapshot().draft?.label || '새 미션'; renderDraft(); }); button(toolbar, '전체 보기', () => { if (map) { view = [0, 0, map.width, map.height]; draw(); } });
  button(toolbar, '운영 위치에서 미리보기', () => { hypothetical = null; state.invalidate(); draw(); status.textContent = '다음 미리보기는 현재 운영 위치를 사용합니다. 실제 위치 설정 명령은 보내지 않습니다.'; });
  const canvas = svg('svg', { role: 'img', tabindex: 0, 'aria-label': '미션 지도 편집 · 목표 전송 없음 · 선택 방문 방향키 이동', viewBox: view.join(' ') });
  const legend = make('p', '┄ 작성 방문 연결선 · 파랑   ··· E1 원본 선호 geometry · 회색   ━ Nav2 미리보기 · 초록   ━ 출발 직전 계획 · 보라(Nav2 재계획 가능)   ·━· 관측 궤적 · 주황   방문 상태: 현재 ◎ / 완료 ✓ / 건너뜀 × / 예정 ○'); legend.className = 'mr-legend';
  const routeNotice = make('p'), segmentDetails = make('p', '작성선/원본 E1 선을 클릭하면 구간 상세를 확인할 수 있습니다.'); segmentDetails.dataset.segmentDetails = 'true';
  main.append(toolbar, canvas, legend, routeNotice, segmentDetails, make('p', 'FLEXIBLE: 지정한 STOP/TASK 순서로 방문합니다. 구간 안에서는 재계획할 수 있습니다. 제한 영역 표시는 실제 costmap 적용 증거와 별도입니다.'));
  const list = make('ol'); left.append(list); const annotationSelect = select(left, '지도 주석 방문');
  function addAnnotation(p) { const v = newVisit(p.pose || p, p.name || '주석 방문'); v.target = 'annotation_ref'; v.annotation_id = p.id; v.pose = null; state.add(v); }
  const editButtons = [];
  editButtons.push(button(left, '주석을 방문으로 추가', () => { requireEditing(); if (staleReasons.length) throw new Error('현재 지도 버전에 초안을 먼저 연결하세요.'); const p = annotations?.points?.find((p) => p.id === annotationSelect.value); if (!p) return; addAnnotation(p); renderDraft(); }));
  for (const [label, action] of [['위로', () => state.move(-1)], ['아래로', () => state.move(1)], ['복제', () => state.duplicate()], ['삭제', () => state.remove()]]) editButtons.push(button(left, label, () => { requireEditing(); action(); renderDraft(); }));
  const historyRow = make('div'), validationRow = make('div'), runActions = make('div');
  historyRow.className = 'mr-history'; validationRow.className = 'mr-validation-actions'; runActions.className = 'mr-run-actions';
  validationRow.setAttribute('role', 'group'); validationRow.setAttribute('aria-label', '미션 검사와 실행 준비');
  runActions.setAttribute('role', 'group'); runActions.setAttribute('aria-label', '선택 실행 제어');
  footer.append(historyRow, validationRow, runActions);
  const checkOutput = make('div'); const runSummary = make('pre', '선택된 실행 없음'); const history = select(historyRow, '실행 이력');
  const compareSelect = select(historyRow, '비교 실행 이력'), comparisonSummary = make('pre', '비교 실행 없음'); comparisonSummary.dataset.comparisonSummary = 'true'; historyRow.append(comparisonSummary);
  compareSelect.addEventListener('change', () => run(async () => { comparison = compareSelect.value ? await planClient.run(compareSelect.value) : null; updateComparison(); draw(); }));
  const checkButtons = [];
  function requireEditing() { if (mode !== 'edit') throw new Error('방문 변경은 편집 모드에서 가능합니다.'); }
  function assertInputs() { const invalid = [...right.querySelectorAll('input[type=number]')].find((node) => !node.disabled && !node.validity.valid); if (invalid || invalidInputs.size) { invalid?.reportValidity(); throw new Error('숫자 입력의 빈 값 또는 허용 범위를 확인하세요. 기존 값은 변경하지 않았습니다.'); } }
  async function savedEntry() { assertInputs(); const s = state.snapshot(); if (!s.saved?.id || s.dirty) throw new Error('변경 내용을 먼저 저장하세요.'); if (staleReasons.length) throw new Error(staleReasons.join(' · ')); return s.saved; }
  checkButtons.push(button(validationRow, '작성 검사', async () => { const entry = await savedEntry(); const generation = state.snapshot().generation; const result = await planClient.validate(entry); if (!destroyed && generation === state.snapshot().generation) showReport(result); }));
  checkButtons.push(button(validationRow, 'Nav2 계획 미리보기', async () => { const e = await savedEntry(); const generation = state.snapshot().generation; const result = await planClient.preview(e, hypothetical); if (destroyed || !state.applyPreview(result, generation)) return; showReport(result); draw(); }));
  checkButtons.push(button(validationRow, 'FLEXIBLE compile', async () => { const entry = await savedEntry(); const generation = state.snapshot().generation; const result = await planClient.compile(entry); if (destroyed || generation !== state.snapshot().generation) return; showReport(result.validation); status.textContent = '실행 초안 생성됨 · 방문·작업 순서 보존 · 이동 명령 없음'; }));
  const createRunButton = button(validationRow, '새 실행 만들기', async () => { const result = await planClient.createRun(await savedEntry()); if (destroyed) return; currentRun = result.run; missionClient.select(result.mission.id); updateRun(result.mission); await missionClient.refresh(); await refreshHistory(); });
  const actionButtons = {};
  for (const [action, label] of [['start', '실행 시작'], ['pause', '일시정지'], ['resume', '재개 / 현재 확인 승인'], ['retry', '현재 방문 재시도'], ['skip', '방문 건너뛰기'], ['abort', '실행 취소']]) actionButtons[action] = button(runActions, label, async () => {
    if (!currentRun) throw new Error('실행을 먼저 선택하세요.');
    if (['start', 'skip', 'abort'].includes(action) && globalThis.confirm?.(`${label} · ${currentRun.definition.label}`) !== true) return;
    const mission = missionClient.snapshot().missions?.find((m) => m.id === currentRun.id);
    if (uncertainAction && ['start', 'resume', 'retry', 'skip'].includes(action)) throw new Error('이전 요청 결과를 실행 상태 다시 확인으로 먼저 확인하세요.');
    const key = requestId();
    try { const result = await planClient.action(currentRun.id, action, mission?.confirmation_token, key); if (destroyed) return; currentRun = result.run; updateRun(result.mission); draw(); if (result.audit_warning) { status.textContent = result.audit_warning; uncertainAction = { runId: currentRun.id, action, key }; } }
    catch (error) {
      if (!error.status || error.status >= 500 || error.message.includes('REQUEST_OUTCOME_UNCERTAIN')) uncertainAction = { runId: currentRun.id, action, key };
      error.message += `\n요청 ${key}는 자동 재전송하지 않습니다.${uncertainAction ? ' 실행 상태 다시 확인 후 현재 방문·로그를 확인하세요.' : ''}`;
      await missionClient.refresh(); throw error;
    }
    await missionClient.refresh();
  }, ['pause', 'abort'].includes(action));
  button(runActions, '수동 전환 요청', async () => { updateTakeover(await navigationAdapter.requestTakeover()); }, true);
  button(runActions, '실행 상태 다시 확인', async () => { const identifier = uncertainAction?.runId || currentRun?.id; if (!identifier) throw new Error('실행을 먼저 선택하세요.'); const result = await planClient.run(identifier); if (destroyed) return; currentRun = result.run; missionClient.select(identifier); history.value = identifier; uncertainAction = null; updateRun(result.mission); draw(); status.textContent = '서버 실행 상태를 다시 읽었습니다. 현재 방문과 로그를 확인하세요. 이전 요청을 재전송하지 않았습니다.'; });
  button(historyRow, '실행 이력 내보내기', async () => { if (!currentRun) throw new Error('실행을 먼저 선택하세요.'); const result = await planClient.exportRun(currentRun.id); if (destroyed) return; const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })); const link = make('a'); link.href = url; link.download = `mission-run-${currentRun.id}.json`; root.append(link); link.click(); link.remove(); URL.revokeObjectURL(url); status.textContent = '읽기 전용 실행 이력을 내려받았습니다. 실행 가능한 정의가 아닙니다.'; });
  const stop = make('a', '공통 STOP으로 이동'); stop.href = '#settings'; runActions.append(stop); footer.append(connectionStatus, takeoverStatus, runSummary, checkOutput, status);
  button(definitionActions, '목록 새로고침', refreshLists);
  button(definitionActions, '지도 불러오기 / 새 미션', async () => { if (!discard()) return; const generation = state.snapshot().generation; await loadMap(mapSelect.value); preservePendingEdits(generation); const f = familyPins(map, map._family); state.fresh({ label: '새 미션', map_family: f, annotation_revision: annotations.annotation_revision, mode: 'FLEXIBLE', visits: [], route_ref: null }); name.value = '새 미션'; mode = 'edit'; editorMap = null; hypothetical = null; currentRun = null; runMission = null; renderDraft(); });
  button(left, '미션 불러오기', async () => { if (!discard()) return; const e = entries.find((e) => e.id === planSelect.value); if (!e) return; const generation = state.snapshot().generation; await loadMap(e.definition.map_family.occupancy_map_id); preservePendingEdits(generation); state.load(e); name.value = e.definition.label; mode = 'edit'; editorMap = null; hypothetical = null; renderDraft(); });
  button(left, 'E1 → 미션 초안', async () => { if (!discard()) return; const generation = state.snapshot().generation; const result = await planClient.routeDraft(routeSelect.value); await loadMap(result.draft.map_family.occupancy_map_id); preservePendingEdits(generation); state.fresh(result.draft); name.value = result.draft.label; mode = 'edit'; editorMap = null; hypothetical = null; renderDraft(); if (!staleReasons.length) status.textContent = result.notice; });
  for (const [copy, label] of [[false, '미션 저장'], [true, '새 미션으로 복사']]) button(definitionActions, label, async () => {
    assertInputs();
    const s = state.snapshot(); if (!s.draft) throw new Error('먼저 지도를 불러오세요.');
    if (staleReasons.length) throw new Error('지도 버전이 달라 먼저 현재 지도 버전에 초안을 연결하세요.');
    const result = await planClient.save(s.draft, s.saved, copy); if (destroyed) return;
    const unchanged = state.acceptSave(result.plan, s.generation);
    if (unchanged) renderDraft(); else { draw(); updateButtons(); }
    await refreshPlans(); status.textContent = unchanged ? '저장됨 · 실행 중인 정의는 해당 실행에 고정됩니다.' : '요청한 버전은 저장했습니다. 저장 중 입력한 변경은 편집 초안에 보존되어 추가 저장이 필요합니다.';
  });
  button(definitionActions, '저장 미션 삭제', async () => { const entry = await savedEntry(); if (globalThis.confirm?.(`저장 미션 ${entry.definition.label}을 삭제할까요? 실행 이력은 보존됩니다.`) !== true) return; const generation = state.snapshot().generation; await planClient.remove(entry); if (destroyed) return; if (state.snapshot().generation === generation) { state.clear(); name.value = '새 미션'; renderDraft(); } else { const draft = state.snapshot().draft; state.fresh(draft); } await refreshPlans(); status.textContent = '저장 미션을 삭제했습니다. 기존 실행 이력은 보존됩니다.'; });
  button(definitionActions, '현재 지도 버전에 초안 연결', async () => {
    const s = state.snapshot(); if (!s.draft || !map) throw new Error('먼저 지도와 미션을 불러오세요.');
    if (globalThis.confirm?.('현재 지도·주석 버전으로 새 초안을 만들까요? 기존 좌표를 직접 검토해야 하며 원본 경로 연결은 해제됩니다.') !== true) return;
    await loadMap(s.draft.map_family.occupancy_map_id);
    preservePendingEdits(s.generation);
    const missing = s.draft.visits.some((v) => v.target === 'annotation_ref' && !annotations.points.some((p) => p.id === v.annotation_id));
    if (missing) throw new Error('현재 지도에 없는 참조 주석이 있습니다. 원본 지도·주석을 복구하거나 해당 방문을 지도 좌표 방문으로 다시 작성하세요.');
    invalidInputs.clear(); state.fresh({ ...s.draft, map_family: familyPins(map, map._family), annotation_revision: annotations.annotation_revision, route_ref: null }); mode = 'edit'; editorMap = null; hypothetical = null; renderDraft(); status.textContent = '현재 지도 버전의 새 초안입니다. 모든 방문 위치·방향을 검토한 뒤 저장·검사하세요.';
  });
  name.addEventListener('input', () => { state.edit((d) => { d.label = name.value; }); draw(); updateButtons(); });
  history.addEventListener('change', () => run(async () => { const result = await planClient.run(history.value); if (destroyed) return; currentRun = result.run; missionClient.select(currentRun.id); updateRun(result.mission); await changeMode('execute'); }));
  let entries = [], runEntries = [];
  const mapSnapshot = () => ({ map, annotations, background, view: [...view] });
  function restoreMap(value) { ({ map, annotations, background } = value); view = [...value.view]; annotationSelect.replaceChildren(...(annotations?.points || []).filter((p) => ['HOME', 'POI', 'DOCK', 'INSPECTION_POINT'].includes(p.type)).map((p) => option(p.id, `${p.type} · ${p.name}`))); }
  async function changeMode(value) {
    if (value === 'execute' && currentRun) {
      const previous = mapSnapshot(), previousMode = mode;
      if (mode !== 'execute' && state.snapshot().draft) editorMap = previous;
      try { await loadMap(currentRun.definition.map_family.occupancy_map_id); } catch (error) { restoreMap(previous); mode = previousMode; throw error; }
      mode = value;
    } else {
      if (mode === 'execute' && editorMap) { restoreMap(editorMap); editorMap = null; }
      mode = value;
    }
    root.dataset.mode = mode; renderDraft(); updateComparison();
    if (mode === 'execute' && currentRun && (currentRun.definition.map_family.occupancy_revision !== map?.revision || currentRun.definition.annotation_revision !== annotations?.annotation_revision)) status.textContent = '이력 지도/주석 버전이 현재 저장본과 달라 해당 방문·계획을 겹쳐 표시할 수 없습니다. 편집 초안은 보존했습니다.';
  }
  function updateTakeover(snapshot) { const t = snapshot?.takeover; if (!t) return; takeoverStatus.dataset.takeoverStatus = t.state; takeoverStatus.textContent = `수동 전환 · ${t.state} · ${t.error || (t.readyToArm ? '정리 확인됨 · ARM은 별도 요청 필요' : t.state === 'IDLE' ? '요청 대기' : 'goal·미션·권한 정리 상태 확인 중')} · 자동 ARM 없음`; }
  function markConnection(stale, reason = '') { connectionStale = stale; if (!stale) lastReceived = new Date().toISOString(); connectionStatus.dataset.connectionStatus = stale ? 'stale' : 'connected'; connectionStatus.textContent = `${stale ? '연결 끊김 / 상태 오래됨' : '서버 연결됨'} · 마지막 수신 ${lastReceived || '없음'}${reason ? ` · ${reason}` : ''}`; if (stale) { context = { ...context, operational_pose: null, blocking_reasons: ['SERVER_STATE_UNAVAILABLE'] }; state.invalidate(); draw(); } }
  function updateComparison() {
    if (!comparison) { comparisonSummary.textContent = '비교 실행 없음'; return; }
    const describe = (r, m) => `${r.definition.label} · ${r.id}\n정의 ${r.definition_revision || '미확인'}\n시작 ${r.started_at || '없음'} / 종료 ${r.completed_at || '없음'}\n결과 ${m?.outcome || m?.state || r.outcome || '미확인'}\n${(m?.waypoints || r.visit_results || []).map((v, i) => `${i + 1}. ${v.label} · ${v.status} · 시도 ${v.attempts ?? 0}`).join('\n')}`;
    const sameMap = currentRun && currentRun.definition.map_family.occupancy_map_id === comparison.run.definition.map_family.occupancy_map_id && currentRun.definition.map_family.occupancy_revision === comparison.run.definition.map_family.occupancy_revision;
    comparisonSummary.textContent = `선택 실행\n${currentRun ? describe(currentRun, runMission) : '없음'}\n\n비교 실행\n${describe(comparison.run, comparison.mission)}\n${sameMap ? '같은 지도 · 비교 관측 궤적은 자홍색 긴 점선' : 'MAP_MISMATCH · 서로 다른 지도의 궤적을 겹치지 않습니다.'}\n관측 표본·epoch 기준이며 위치 오차 통계를 제공하지 않습니다.`;
  }
  async function refreshSourceRoute() {
    const definition = mode === 'execute' ? currentRun?.definition : state.snapshot().draft, ref = definition?.route_ref;
    const key = ref ? `${ref.route_id}:${ref.revision}:${JSON.stringify(definition.map_family)}` : '';
    if (key === sourceRouteKey) return; sourceRouteKey = key; sourceRoute = null; routeNotice.textContent = ref ? 'E1 원본 geometry 읽는 중' : '';
    if (!ref) return;
    try { const result = await planClient.route(ref.route_id); if (destroyed || sourceRouteKey !== key) return; const route = result.route;
      if (route.revision !== ref.revision || Object.keys(definition.map_family).some((k) => route.map_family?.[k] !== definition.map_family[k]) || !Array.isArray(route.poses) || route.poses.length > 4096 || !route.poses.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y))) throw new Error('E1 원본 경로 revision이 다르거나 geometry가 유효하지 않습니다.');
      sourceRoute = route; routeNotice.textContent = `E1 원본 선호 geometry · ${route.poses.length}점 · 정확한 선 추종 보장 없음`; draw();
    } catch (error) { if (sourceRouteKey === key && !destroyed) routeNotice.textContent = `E1 geometry 표시 불가 · ${error.message}`; }
  }
  function discard() { const accepted = !(state.snapshot().dirty || invalidInputs.size) || globalThis.confirm?.('저장하지 않은 편집 내용을 버리고 불러올까요?') === true; if (accepted) invalidInputs.clear(); return accepted; }
  function preservePendingEdits(generation) { if (state.snapshot().generation !== generation) { renderDraft(); throw new Error('불러오는 동안 입력하거나 운영 컨텍스트가 변경되어 기존 초안을 보존했습니다. 다시 불러오세요.'); } }
  async function run(action, interrupt = false) { if (busy && !interrupt || destroyed || !active) return; pendingActions++; busy = true; updateButtons(); try { await action(); } catch (error) { if (!destroyed) status.textContent = error.message; } finally { pendingActions--; busy = pendingActions > 0; updateButtons(); } }
  async function refreshPlans() { const result = await planClient.list(); if (destroyed) return; entries = result.definitions; context = result.context; const prev = planSelect.value; planSelect.replaceChildren(...entries.map((e) => option(e.id, e.definition.label))); if (entries.some((e) => e.id === prev)) planSelect.value = prev; mapLabel.textContent = `navigation 지도 ${context.navigation_map?.id || '없음'} · 운영 ${context.pose_source?.source || '미확인'} · ${context.pose_source?.readiness || '미준비'}`; updateButtons(); }
  async function refreshHistory() { const result = await planClient.runs(); if (destroyed) return; runEntries = result.runs; const options = () => runEntries.map((r) => option(r.run.id, `${r.run.definition.label} · ${r.mission.state} · ${r.run.id.slice(0, 8)}`)); history.replaceChildren(option('', '실행 선택'), ...options()); compareSelect.replaceChildren(option('', '비교 안 함'), ...options()); if (comparison) compareSelect.value = comparison.run.id; const selected = runEntries.find((r) => r.run.id === (currentRun?.id || missionClient.snapshot().selectedMissionId)); if (selected) { currentRun = selected.run; history.value = currentRun.id; updateRun(selected.mission); draw(); } }
  async function refreshLists() { const [maps, routes] = await Promise.all([planClient.maps(), planClient.routes()]); if (destroyed) return; const previous = mapSelect.value; mapSelect.replaceChildren(...(maps.maps || []).filter((m) => m.kind === 'occupancy2d').map((m) => option(m.id, m.name))); if ([...mapSelect.options].some((o) => o.value === previous)) mapSelect.value = previous; routeSelect.replaceChildren(...(routes.routes || []).map((r) => option(r.route_id, r.label))); await refreshPlans(); await refreshHistory(); }
  async function loadMap(identifier) {
    if (!/^[0-9a-f]{24}$/.test(identifier || '')) throw new Error('저장 지도를 선택하세요.');
    const requestEpoch = epoch;
    const result = await planClient.map(identifier); if (destroyed || !active || requestEpoch !== epoch) throw new Error('화면이 변경되어 지도 응답을 적용하지 않았습니다. 다시 불러오세요.');
    const data = result.data;
    if (data.kind !== 'occupancy2d' || data.frame_id !== 'map' || data.map_id !== identifier || !Array.isArray(data.origin) || data.origin.length !== 3 || !data.origin.every(Number.isFinite) || !Number.isInteger(data.width) || !Number.isInteger(data.height) || data.width < 1 || data.height < 1 || data.width * data.height > 16000000 || !Number.isFinite(data.resolution) || !(data.resolution > 0)) throw new Error('navigation occupancy 지도가 필요합니다.');
    if (result.annotations.map_id !== data.map_id || result.annotations.map_revision !== data.revision || !Array.isArray(result.annotations.points)) throw new Error('지도·주석 revision이 다릅니다.');
    const bytes = atob(data.data_b64); if (bytes.length !== data.width * data.height) throw new Error('지도 셀 수가 다릅니다.');
    const imageCanvas = doc.createElement('canvas'); imageCanvas.width = data.width; imageCanvas.height = data.height;
    const ctx = imageCanvas.getContext('2d'), pixels = ctx.createImageData(data.width, data.height);
    for (let y = 0; y < data.height; y++) for (let x = 0; x < data.width; x++) { const cell = bytes.charCodeAt(y * data.width + x), value = cell === 255 ? 110 : cell === 0 ? 240 : 25; pixels.data.set([value, value, value, 255], ((data.height - y - 1) * data.width + x) * 4); }
    ctx.putImageData(pixels, 0, 0); background = imageCanvas.toDataURL(); map = { ...data, _family: result.family }; annotations = result.annotations; view = [0, 0, map.width, map.height];
    annotationSelect.replaceChildren(...annotations.points.filter((p) => ['HOME', 'POI', 'DOCK', 'INSPECTION_POINT'].includes(p.type)).map((p) => option(p.id, `${p.type} · ${p.name}`)));
  }
  function target(visit) { return resolvedTarget(visit, annotations); }
  function comparePins() {
    const d = state.snapshot().draft; staleReasons = []; geometryCurrent = false;
    if (mode === 'execute') return;
    if (!d || !map) return;
    geometryCurrent = d.map_family.occupancy_map_id === map.map_id && d.map_family.occupancy_revision === map.revision;
    if (!geometryCurrent) staleReasons.push('STALE_MAP_REVISION: 저장된 방문 좌표를 최신 지도 위에 표시하지 않습니다.');
    try { const pins = familyPins(map, map._family); if (Object.keys(pins).some((k) => pins[k] !== d.map_family[k])) staleReasons.push('STALE_MAP_FAMILY: 지도 연결 버전이 다릅니다.'); } catch (error) { staleReasons.push(error.message); }
    if (d.annotation_revision !== annotations.annotation_revision) staleReasons.push('STALE_ANNOTATION_REVISION: 참조 주석 위치·방향을 다시 확인해야 합니다.');
    if (staleReasons.length) { state.invalidate(); status.textContent = staleReasons.join('\n'); }
  }
  function renderDraft() {
    comparePins();
    const s = state.snapshot(); list.replaceChildren();
    for (const key of invalidInputs.keys()) if (!s.draft?.visits.some((v) => key.startsWith(`${v.visit_id}:`))) invalidInputs.delete(key);
    for (const [i, visit] of (s.draft?.visits || []).entries()) { const row = make('li'), b = make('button', visitSummary(visit, i)); b.type = 'button'; b.dataset.visitLabel = visit.visit_id; b.setAttribute('aria-current', String(visit.visit_id === s.selected)); b.addEventListener('click', () => { state.select(visit.visit_id); renderDraft(); }); row.append(b); list.append(row); }
    right.replaceChildren(); const visit = s.draft?.visits.find((v) => v.visit_id === s.selected);
    if (visit) {
      right.append(make('strong', '선택 방문 상세'));
      function input(label, type, value, change, disabled = false) {
        const wrapper = make('label', label), node = make('input'), key = `${visit.visit_id}:${label}`; node.type = type; node.setAttribute('aria-label', label);
        if (type === 'checkbox') node.checked = value; else node.value = invalidInputs.has(key) ? invalidInputs.get(key) : String(value);
        if (type === 'number') { node.required = true; node.step = 'any'; }
        node.disabled = disabled || mode !== 'edit'; wrapper.append(node); right.append(wrapper);
        node.addEventListener('input', () => {
          if (type === 'number' && (!node.value.trim() || !node.validity.valid || !Number.isFinite(node.valueAsNumber))) { invalidInputs.set(key, node.value); node.setAttribute('aria-invalid', 'true'); state.invalidate(); draw(); updateButtons(); return; }
          invalidInputs.delete(key); node.removeAttribute('aria-invalid'); change(type === 'checkbox' ? node.checked : type === 'number' ? node.valueAsNumber : node.value); draw(); updateButtons();
        }); return node;
      }
      input('방문 이름', 'text', visit.label, (v) => state.update({ label: v })).maxLength = 64;
      const kind = select(right, '방문 종류'); kind.append(...[['STOP', '정지 방문'], ['TASK', '작업 방문'], ['PASS_THROUGH', '무정차 경유 · 미지원']].map(([v, l]) => option(v, l))); kind.value = visit.kind; kind.disabled = mode !== 'edit'; kind.addEventListener('change', () => { state.update({ kind: kind.value }); draw(); updateButtons(); });
      if (visit.target === 'annotation_ref') {
        const reference = select(right, '참조 지도 주석'); reference.append(...(annotations?.points || []).filter((p) => ['HOME', 'POI', 'DOCK', 'INSPECTION_POINT'].includes(p.type)).map((p) => option(p.id, `${p.type} · ${p.name}`))); reference.value = visit.annotation_id; reference.disabled = mode !== 'edit';
        reference.addEventListener('change', () => { state.update({ annotation_id: reference.value, heading_yaw: null }); renderDraft(); });
        input('주석 방향 대신 방문별 방향 사용', 'checkbox', visit.heading_yaw != null, (value) => { state.update({ heading_yaw: value ? target(visit)?.yaw || 0 : null }); renderDraft(); });
      }
      const p = target(visit);
      function setHeading(yaw) { if (visit.target === 'annotation_ref') state.update({ heading_yaw: yaw }); else state.update({ pose: { ...state.snapshot().draft.visits.find((v) => v.visit_id === visit.visit_id).pose, yaw } }); }
      if (p) {
        for (const axis of ['x', 'y']) { const coordinate = input(`${axis}(m)`, 'number', p[axis], (v) => state.update({ pose: { ...state.snapshot().draft.visits.find((v) => v.visit_id === visit.visit_id).pose, [axis]: v } }), visit.target !== 'mission_local_pose' || staleReasons.length > 0); coordinate.min = '-10000'; coordinate.max = '10000'; }
        const heading = input('방향(°)', 'number', p.yaw * 180 / Math.PI, (v) => setHeading(v * Math.PI / 180), visit.target === 'annotation_ref' && visit.heading_yaw == null || staleReasons.length > 0); heading.min = '-180'; heading.max = '180';
        const nextHeading = headingToNext(s.draft.visits, s.selected, annotations);
        const nextButton = button(right, '다음 구간 방향으로 설정', () => { setHeading(nextHeading); renderDraft(); }); nextButton.disabled = nextHeading == null || mode !== 'edit' || staleReasons.length > 0;
      }
      const hold = input('도착 후 대기(초)', 'number', visit.hold_seconds ?? 0, (v) => state.update({ hold_seconds: v })); hold.min = '0'; hold.max = '300';
      input('출발 전 운영자 확인', 'checkbox', visit.requires_operator_confirmation, (v) => state.update({ requires_operator_confirmation: v })); input('도착 후 운영자 확인', 'checkbox', visit.after_arrival_confirmation, (v) => state.update({ after_arrival_confirmation: v }));
      const action = select(right, '추가 작업'); action.append(...[['none', '추가 작업 없음'], ['photo', '사진 · 공급자 미지원'], ['sit_then_rise', '앉기/일어서기 · 미지원'], ['dock', '도킹 · 미지원']].map(([v, l]) => option(v, l))); action.value = visit.action || 'none'; action.disabled = mode !== 'edit'; action.addEventListener('change', () => { state.update({ action: action.value }); draw(); updateButtons(); });
      input('속도 · DEFAULT(기존 제한)', 'text', visit.speed || 'DEFAULT', () => {}, true); input('도착 판정 · NAV2_DEFAULT', 'text', visit.arrival_tolerance == null ? 'Nav2 성공 · 물리 정지 별도' : `${visit.arrival_tolerance}m · 실행 미지원`, () => {}, true);
    } else right.append(make('p', '지도 도구에서 방문 추가를 선택하거나 주석을 추가하세요.'));
    updateDrawers(); draw(); updateButtons(); refreshSourceRoute();
  }
  function updateDrawers() { left.dataset.drawerHidden = String(selectedDrawer !== 'visits'); right.dataset.drawerHidden = String(selectedDrawer !== 'inspector'); }
  function updateButtons() {
    root.dataset.busy = String(busy);
    const s = state.snapshot(); for (const b of [...checkButtons, createRunButton]) b.disabled = busy || s.dirty || !s.saved?.id || staleReasons.length > 0 || invalidInputs.size > 0;
    name.disabled = mode !== 'edit'; for (const b of editButtons) b.disabled = busy || mode !== 'edit' || !s.draft;
    const m = missionClient.snapshot().missions?.find((m) => m.id === currentRun?.id);
    for (const [a, b] of Object.entries(actionButtons)) { const allowed = { start: ['ready'], pause: ['running', 'starting'], resume: ['paused'], retry: ['failed'], skip: ['running', 'paused', 'failed'], abort: ['running', 'paused', 'starting', 'pausing', 'canceling', 'retrying', 'skipping'] }[a]; b.disabled = busy && !['pause', 'abort'].includes(a) || !m || !allowed.includes(m.state) || Boolean(uncertainAction && ['start', 'resume', 'retry', 'skip'].includes(a)); b.title = b.disabled ? '선택한 실행의 현재 상태 또는 실행 준비 조건을 확인하세요.' : ''; }
    if (['aborted', 'interrupted'].includes(m?.outcome) || m?.phase === 'interrupted') { actionButtons.retry.disabled = true; actionButtons.skip.disabled = true; }
    if (connectionStale) for (const action of ['start', 'resume', 'retry', 'skip']) { actionButtons[action].disabled = true; actionButtons[action].title = '서버 상태를 다시 확인해야 합니다.'; }
    if (context?.blocking_reasons?.length) for (const action of ['start', 'resume', 'retry', 'skip']) { const reasons = context.blocking_reasons.filter((reason) => !(action === 'skip' && m?.ownership_active && reason === 'GOAL_ADMISSION_UNAVAILABLE')); if (reasons.length) { actionButtons[action].disabled = true; actionButtons[action].title = reasons.join(', '); } }
  }
  function showReport(report) {
    lastReport = report;
    reportGeneration = state.snapshot().generation;
    checkOutput.replaceChildren(make('p', `${report.status} · ${report.scope} · actual_nav2_run=${report.actual_nav2_run === true}`));
    if (report.start_source) checkOutput.append(make('p', `시작점 ${report.start_source} · 위치 snapshot ${report.snapshot_seq ?? '미확인'}`));
    for (const reason of [...(report.blocking_reasons || []), ...(report.execution_readiness?.blocking_reasons || [])]) checkOutput.append(make('p', reason));
    const violationRows = (values, prefix) => {
      for (const violation of values || []) {
        const label = `${prefix} ${violation.segment ?? violation.index ?? ''} · ${violation.violation_code || violation.kind} · ${violation.severity || ''}`;
        const control = button(checkOutput, label, () => { if (map && Number.isFinite(violation.x) && Number.isFinite(violation.y)) { const p = worldToGrid(map, violation); view = [p.x - view[2]/4, p.y - view[3]/4, view[2]/2, view[3]/2]; draw(); } });
        control.title = `revision ${violation.affected_revision || '해당 검사 버전'} · ${violation.remedy || ''}`;
        if (violation.remedy) checkOutput.append(make('p', violation.remedy));
      }
    };
    violationRows(report.violations || report.validation?.violations, '문제 구간');
    const connectors = report.validation?.connector_validation;
    if (connectors?.violations?.length) { checkOutput.append(make('p', '작성 연결선 경고 · 실제 Nav2 계획과 별도입니다.')); violationRows(connectors.violations, '작성 연결선'); }
    if (report.length_m != null) checkOutput.append(make('p', `${report.actual_nav2_run ? '실제 Nav2 계획' : '합성 검사 결과'} 길이 ${report.length_m.toFixed(2)}m · ETA 미제공`));
    for (const [zone, support] of Object.entries(report.zone_support || {})) checkOutput.append(make('p', `${zone} · 작성 ${support.authoring || '미지원'} · 계획 ${support.planning || '미지원'} · 실행 ${support.runtime || '미지원'}`));
    status.textContent = report.notice || '검사 결과는 해당 revision 기준이며 실행 허가와 별도입니다.';
  }
  function updateRun(mission) {
    if (!mission) return; if (mission.id === currentRun?.id) runMission = mission;
    const current = mission.waypoints[mission.current_index], next = mission.waypoints[mission.current_index + 1];
    runSummary.textContent = `${mission.label} · ${mission.state} / ${mission.phase || ''}\n현재 ${current?.label || '없음'} · 다음 ${next?.label || '없음'}\n방문 ${Math.min(mission.current_index + 1, mission.waypoints.length)} · 완료 ${mission.completed_count}/${mission.waypoints.length} · 대기 잔여 ${mission.hold_remaining ?? 0}s\n${mission.pause_reason || mission.error || mission.outcome || ''}\n취소 응답·goal terminal·물리 정지는 별도입니다. 물리 정지: 관측 안 됨\n실행 계획: ${currentRun?.preview?.actual_nav2_run ? '출발 직전 계획 · Nav2 재계획 가능' : '수신 안 됨'} · ${currentRun?.preview?.observed_at || '시각 미확인'}\n현재 Nav2 runtime 경로: ${currentRun?.live_plan?.reason || '출처·시각 증거 없음'}\n${(mission.logs || []).slice(-8).map((e) => `${e.seq} ${e.event}`).join('\n')}`;
    updateComparison(); updateButtons();
  }
  function inspectSegment(points, event, label) {
    const pixel = location(event); if (!pixel || points.length < 2) return; const world = gridToWorld(map, pixel.x, pixel.y); let best = null;
    for (let index = 0; index < points.length - 1; index++) { const a = points[index], b = points[index + 1], dx = b.x - a.x, dy = b.y - a.y, length2 = dx*dx + dy*dy, t = length2 ? Math.max(0, Math.min(1, ((world.x-a.x)*dx + (world.y-a.y)*dy)/length2)) : 0; const distance = Math.hypot(world.x-a.x-t*dx, world.y-a.y-t*dy); if (!best || distance < best.distance) best = { index, distance, length: Math.sqrt(length2), a, b }; }
    const violations = [...(lastReport?.violations || lastReport?.validation?.violations || []), ...(lastReport?.validation?.connector_validation?.violations || [])].filter((v) => (v.segment ?? v.index) === best.index);
    segmentDetails.textContent = `${label} 구간 ${best.index + 1} · ${best.length.toFixed(2)}m · (${best.a.x.toFixed(2)}, ${best.a.y.toFixed(2)}) → (${best.b.x.toFixed(2)}, ${best.b.y.toFixed(2)})\n작성 guidance이며 실제 계획·추종 보장이 아닙니다. 관련 검사: ${violations.map((v) => v.violation_code || v.kind).join(', ') || '해당 검사 결과 없음'}`;
  }
  function visitSummary(visit, index) { return `${index + 1}. ${visit.label} · ${visit.kind}${visit.hold_seconds ? ` · 대기 ${visit.hold_seconds}s` : ''}${visit.after_arrival_confirmation ? ' · 도착 확인' : ''}`; }
  function draw() {
    const latest = state.snapshot();
    if (reportGeneration != null && reportGeneration !== latest.generation) { checkOutput.replaceChildren(make('p', '이전 검사 결과는 편집 또는 운영 컨텍스트 변경으로 만료됐습니다. 다시 검사하세요.')); reportGeneration = null; lastReport = null; }
    definitionMode.textContent = latest.draft && latest.draft.mode !== 'FLEXIBLE' ? `${latest.draft.mode} · 작성 전용 / 실행 미지원` : 'FLEXIBLE · STOP/TASK 순서 방문';
    canvas.replaceChildren(); canvas.setAttribute('viewBox', view.join(' ')); canvas.dataset.mapId = map?.map_id || ''; if (!map) return;
    canvas.append(svg('image', { href: background, width: map.width, height: map.height })); const scale = Math.max(view[2], view[3]) / 500;
    const line = (points, attrs) => { if (!points?.length) return; const shape = svg('polyline', { points: points.map((p) => { const g = worldToGrid(map, p); return `${g.x},${g.y}`; }).join(' '), fill: 'none', 'stroke-width': 2 * scale, ...attrs }); if (['authored_connectors', 'authored_e1_geometry'].includes(attrs['data-evidence'])) shape.addEventListener('pointerdown', (event) => { if (tool.value !== 'add' && tool.value !== 'move') { inspectSegment(points, event, attrs['data-evidence'] === 'authored_e1_geometry' ? 'E1 원본 geometry' : '작성 방문 연결선'); event.stopPropagation(); } }); canvas.append(shape); };
    for (const polygon of annotations?.polygons || []) { const points = (polygon.vertices || []).map((p) => { const g = worldToGrid(map, p); return `${g.x},${g.y}`; }).join(' '); canvas.append(svg('polygon', { points, fill: '#ed5965', 'fill-opacity': '.22', stroke: '#ed5965', 'stroke-width': scale })); }
    const s = state.snapshot();
    for (const b of list.querySelectorAll('[data-visit-label]')) { const i = (s.draft?.visits || []).findIndex((v) => v.visit_id === b.dataset.visitLabel); if (i >= 0) { b.textContent = visitSummary(s.draft.visits[i], i); b.setAttribute('aria-current', String(b.dataset.visitLabel === s.selected)); } }
    const sameMap = currentRun?.definition.map_family.occupancy_map_id === map.map_id && currentRun?.definition.map_family.occupancy_revision === map.revision;
    const visits = mode === 'execute' ? (sameMap && currentRun.definition.annotation_revision === annotations.annotation_revision ? currentRun.definition.visits : []) : (geometryCurrent && !staleReasons.length ? s.draft?.visits || [] : []);
    if (sourceRoute?.map_family.occupancy_map_id === map.map_id && sourceRoute.map_family.occupancy_revision === map.revision) line(sourceRoute.poses, { stroke: '#777', 'stroke-dasharray': `${2*scale} ${3*scale}`, 'stroke-width': 4*scale, 'data-evidence': 'authored_e1_geometry' });
    for (const p of annotations?.points || []) { if (!['HOME', 'POI', 'DOCK', 'INSPECTION_POINT'].includes(p.type)) continue; const g = worldToGrid(map, p.pose || p); const marker = svg('circle', { cx: g.x, cy: g.y, r: 4*scale, fill: '#7c5cc4', 'data-annotation': p.id }); const title = svg('title'); title.textContent = `${p.type} · ${p.name} · 현재 지도 주석`; marker.append(title); canvas.append(marker); }
    line(visits.map(target).filter(Boolean), { stroke: '#127ed1', 'stroke-dasharray': `${6*scale} ${4*scale}`, 'data-evidence': 'authored_connectors' });
    if (mode !== 'execute' && s.preview?.actual_nav2_run && !staleReasons.length) for (const leg of s.preview.legs || []) line(leg.poses, { stroke: '#13994c', 'data-evidence': 'native_preview' });
    if (mode === 'execute' && sameMap && currentRun.preview?.actual_nav2_run) for (const leg of currentRun.preview.legs || []) line(leg.poses, { stroke: '#9147bb', 'data-evidence': 'dispatch_preflight' });
    if (sameMap) { let trajectoryEpoch = null, points = []; const attrs = { stroke: '#ed9328', 'stroke-dasharray': `${9*scale} ${3*scale} ${2*scale} ${3*scale}`, 'data-evidence': 'observed_trajectory' }; for (const p of currentRun.trajectory || []) { if (p.epoch !== trajectoryEpoch) { line(points, attrs); points = []; trajectoryEpoch = p.epoch; } points.push(p); } line(points, attrs); }
    if (sameMap && comparison?.run.definition.map_family.occupancy_map_id === map.map_id && comparison.run.definition.map_family.occupancy_revision === map.revision) { let lastEpoch = null, points = []; const attrs = { stroke: '#b735a5', 'stroke-dasharray': `${14*scale} ${7*scale}`, 'data-evidence': 'comparison_trajectory' }; for (const p of comparison.run.trajectory || []) { if (p.epoch !== lastEpoch) { line(points, attrs); points = []; lastEpoch = p.epoch; } points.push(p); } line(points, attrs); }
    visits.forEach((visit, index) => {
      const p = target(visit); if (!p) return; const g = worldToGrid(map, p), result = mode === 'execute' ? runMission?.waypoints.find((v) => v.visit_id === visit.visit_id) || runMission?.waypoints[index] : null;
      const progress = mode !== 'execute' ? 'draft' : result?.status === 'completed' ? 'completed' : result?.status === 'skipped' ? 'skipped' : index === runMission?.current_index ? 'current' : 'pending';
      const symbols = { completed: '✓', skipped: '×', current: '◎', pending: '○', draft: '' }, colors = { completed: '#249a55', skipped: '#777', current: '#e66b18', pending: '#127ed1', draft: visit.visit_id === s.selected ? '#e66b18' : '#127ed1' };
      const marker = svg('circle', { cx: g.x, cy: g.y, r: (progress === 'current' ? 8 : 6)*scale, fill: colors[progress], 'data-visit': visit.visit_id, 'data-visit-status': progress }); const title = svg('title'); title.textContent = `${visit.label} · ${progress} · ${result?.status || '작성'}`; marker.append(title); canvas.append(marker);
      const label = svg('text', { x: g.x+9*scale, y: g.y, 'font-size': 13*scale, fill: '#111', 'pointer-events': 'none' }); label.textContent = `${index+1}${symbols[progress]}`; canvas.append(label); const yaw = p.yaw - map.origin[2]; canvas.append(svg('line', { x1: g.x, y1: g.y, x2: g.x+15*scale*Math.cos(yaw), y2: g.y-15*scale*Math.sin(yaw), stroke: '#8b3fac', 'stroke-width': 3*scale, 'pointer-events': 'none' }));
    });
    if (hypothetical && mode !== 'execute') { const g = worldToGrid(map, hypothetical); canvas.append(svg('circle', { cx: g.x, cy: g.y, r: 8*scale, stroke: '#d142a6', fill: 'none', 'stroke-width': 2*scale })); }
    if (!connectionStale && context?.navigation_map?.id === map.map_id && context?.navigation_map?.revision === map.revision && context?.operational_pose) { const g = worldToGrid(map, context.operational_pose); const marker = svg('circle', { cx: g.x, cy: g.y, r: 7*scale, stroke: '#111', fill: '#fff', 'stroke-width': 2*scale, 'data-evidence': 'operational_pose' }); const title = svg('title'); title.textContent = `운영 위치 · ${context.pose_source?.source || '미확인'} · snapshot ${context.snapshot_seq ?? '미확인'}`; marker.append(title); canvas.append(marker); }
  }
  function location(event) { const matrix = canvas.getScreenCTM(); if (!matrix) return null; const point = canvas.createSVGPoint(); point.x = event.clientX; point.y = event.clientY; return point.matrixTransform(matrix.inverse()); }
  canvas.addEventListener('pointerdown', (event) => {
    if (!map || busy || event.button !== 0 || !active) return;
    const p = location(event); if (!p) return;
    const visitId = event.target.getAttribute('data-visit');
    if (visitId && state.snapshot().draft?.visits.some((v) => v.visit_id === visitId)) state.select(visitId);
    const selectedTool = mode === 'edit' ? tool.value : 'select';
    if (selectedTool !== 'pan' && (p.x < 0 || p.y < 0 || p.x >= map.width || p.y >= map.height)) return;
    if (['add', 'move', 'start'].includes(selectedTool) && staleReasons.length) { status.textContent = '현재 지도 버전에 초안을 먼저 연결하세요.'; return; }
    gesture = { id: event.pointerId, tool: selectedTool, start: p, view: [...view], visitId }; canvas.setPointerCapture(event.pointerId); if (selectedTool === 'move' && visitId) state.beginEdit();
    const world = gridToWorld(map, p.x, p.y);
    try {
      if (selectedTool === 'add') { const annotation = annotations.points.find((v) => v.id === event.target.getAttribute('data-annotation')); if (annotation) addAnnotation(annotation); else state.add(newVisit(world)); }
      if (selectedTool === 'start') { hypothetical = { ...world, yaw: 0 }; state.invalidate(); }
      renderDraft();
    } catch (error) { gesture = null; status.textContent = error.message; }
  });
  canvas.addEventListener('pointermove', (event) => { if (!gesture || event.pointerId !== gesture.id || !active || busy) return; const p = location(event); if (!p) return; if (gesture.tool === 'pan') { view[0] += gesture.start.x-p.x; view[1] += gesture.start.y-p.y; draw(); } if (mode === 'edit' && gesture.tool === 'move' && gesture.visitId && p.x >= 0 && p.y >= 0 && p.x < map.width && p.y < map.height) { const v = state.snapshot().draft.visits.find((v) => v.visit_id === gesture.visitId); if (v?.target === 'mission_local_pose') { state.update({ pose: { ...v.pose, ...gridToWorld(map, p.x, p.y) } }); draw(); } } });
  const end = (event) => { if (gesture?.tool === 'move') { state.endEdit(event.type === 'pointercancel'); renderDraft(); } gesture = null; }; canvas.addEventListener('pointerup', end); canvas.addEventListener('pointercancel', end);
  canvas.addEventListener('wheel', (event) => { if (!map || gesture) return; event.preventDefault(); const p = location(event); if (!p) return; const factor = event.deltaY > 0 ? 1.15 : 1/1.15, next = view[2]*factor; if (next < map.width/50 || next > map.width*3) return; view = [p.x+(view[0]-p.x)*factor, p.y+(view[1]-p.y)*factor, next, view[3]*factor]; draw(); }, { passive: false });
  canvas.addEventListener('keydown', (event) => {
    if (!map || busy || !active || mode !== 'edit' || staleReasons.length || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
    const s = state.snapshot(), visit = s.draft?.visits.find((v) => v.visit_id === s.selected); if (visit?.target !== 'mission_local_pose') return;
    event.preventDefault(); const step = event.shiftKey ? 0.5 : 0.05;
    state.update({ pose: { ...visit.pose, x: visit.pose.x + (event.key === 'ArrowRight' ? step : event.key === 'ArrowLeft' ? -step : 0), y: visit.pose.y + (event.key === 'ArrowUp' ? step : event.key === 'ArrowDown' ? -step : 0) } }); renderDraft();
  });
  // Reuse the existing mission client's subscription clock; no second poll timer.
  async function observeRun() {
    if (!active || destroyed || observing || Date.now() - lastObservation < 1000) return;
    observing = true; lastObservation = Date.now(); const requestEpoch = epoch, runId = currentRun?.id;
    try {
      const [latest, definitions] = await Promise.all([runId ? planClient.run(runId) : Promise.resolve(null), planClient.list()]);
      if (!active || destroyed || requestEpoch !== epoch) return;
      const nextContext = definitions.context;
      if (context?.navigation_context_revision && context.navigation_context_revision !== nextContext?.navigation_context_revision) state.invalidate();
      context = nextContext;
      markConnection(missionClient.snapshot().available === false, missionClient.snapshot().available === false ? '미션 상태 조회 실패' : '');
      mapLabel.textContent = `navigation 지도 ${context?.navigation_map?.id || '없음'} · 운영 ${context?.pose_source?.source || '미확인'} · ${context?.pose_source?.readiness || '미준비'}`;
      if (latest && currentRun?.id === runId) { currentRun = latest.run; updateRun(latest.mission); }
      draw();
      updateButtons();
    } catch (error) { if (active && requestEpoch === epoch && !destroyed) { markConnection(true, error.message); updateButtons(); } }
    finally { observing = false; }
  }
  renderDraft();
  return {
    activate() {
      if (active || destroyed) return; active = true; epoch++; lastObservation = 0;
      release = missionClient.subscribe((snapshot) => { if (!active) return; if (snapshot.available === false) markConnection(true, snapshot.error || '미션 상태 조회 실패'); if (!currentRun && snapshot.selected) updateRun(snapshot.selected); else updateRun(snapshot.missions?.find((m) => m.id === currentRun?.id)); observeRun(); });
      navigationRelease = navigationAdapter.subscribe?.(updateTakeover) || null;
      run(async () => { await refreshLists(); if (restored && state.snapshot().draft && !map) { await loadMap(state.snapshot().draft.map_family.occupancy_map_id); restored = false; renderDraft(); if (!staleReasons.length) status.textContent = '이 탭의 편집 초안을 복구했습니다. 실행은 자동 시작하지 않습니다.'; } });
    },
    deactivate() { active = false; epoch++; state.endEdit(true); gesture = null; release?.(); release = null; navigationRelease?.(); navigationRelease = null; connectionStale = true; state.invalidate(); },
    destroy() { this.deactivate(); destroyed = true; root.remove(); },
  };
}
