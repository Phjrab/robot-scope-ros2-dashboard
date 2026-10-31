/** Presentation only. Runtime admission remains authoritative for every command. */
export const PREPARATION_STEPS = [
  ['지도 선택·연결 확인', '3D·2D 지도 ID/revision, 변환 계보와 좌표 관계를 서버에서 확인'],
  ['센서·교정·초기값 준비', '검증된 센서·본체 교정과 명시한 초기 높이·기울기 준비'],
  ['Nav2 시작·노드와 TF 확인', '실행 source, 현재 점군·자세, Nav2 노드와 TF 입력 확인'],
  ['INITIAL POSE 지정·전송', '지도에서 지정한 현재 위치·방향의 실제 런타임 접수 확인'],
  ['현재 LiDAR와 저장 지도 정합', '명시적으로 정합을 시작하고 실제 보정 갱신·품질 확인'],
  ['추정 위치·주행 준비 확인', '신선한 추정 위치, TF 반영과 기존 주행 안전 조건 충족'],
  ['목표 전송·경로 진행', '사용자가 별도로 목표를 전송하고 실제 Nav2 종료 확인'],
];

const REASONS = {
  WAITING_EXPLICIT_INITIAL_POSE: ['초기 위치·방향 미지정', '실제 정지 상태에서 INITIAL POSE를 지정·전송하세요.'],
  WAITING_EXPLICIT_MAP_MATCH: ['정합 시작 입력 필요', '초기 위치 접수 후 ⑤ 정합 시작을 누르세요.'],
  WAITING_EXPLICIT_MATCH: ['정합 시작 입력 필요', '초기 위치 접수 후 ⑤ 정합 시작을 누르세요.'],
  WAITING_EXACT_STAMP_PAIR: ['동일 시각 점군·자세 입력 부족', '센서 입력·시각과 TF 상태를 확인한 뒤 해당 단계에서 다시 확인하세요.'],
  INITIAL_REFINEMENT_LOW_OVERLAP: ['지도와 겹치는 관측 부족', '실제 위치·방향과 현재 관측 가능한 구조를 확인하세요.'],
  INITIAL_REFINEMENT_REQUIRES_STOP: ['실제 정지·대기 미충족', '로봇을 정지하고 관측된 정지 시간이 충족된 뒤 다시 확인하세요.'],
  INITIAL_REFINEMENT_OUT_OF_BOUNDS: ['초기값 주변 정합 범위 초과', '현재 위치·방향을 다시 지정하세요.'],
  CORRECTION_JUMP_RESEED_REQUIRED: ['지도 보정 불연속', '안전하게 정지한 뒤 초기 위치를 다시 지정하세요.'],
  MAP_CORRECTION_STALE: ['지도 보정 결과 오래됨', '현재 점군·자세와 지도 정합의 갱신 상태를 확인하세요.'],
  INSUFFICIENT_STRUCTURE: ['관측 가능한 구조 부족', '서로 다른 방향의 안정적인 구조가 관측되는지 확인하세요.'],
  HIGH_RESIDUAL: ['현재 정합 품질 기준 미달', '현재 잔차·겹침·구조 검사 결과를 확인하세요.'],
};
const finite = value => typeof value === 'number' && Number.isFinite(value);
const pin = map => map && `${map.map_id || map.id}:${map.revision}`;
const issue = (code, current, required, remedy, step) => ({ code, current, required, remedy, step });
const samePin = (a, b) => Boolean(a && b && pin(a) === pin(b));

export function operationalPoseContextMatches(observation, source, map) {
  return Boolean(observation && source && map && samePin({ map_id: observation.map_id, revision: observation.map_revision }, map)
    && observation.bundle_generation === source.bundle_generation && source.bundle_generation
    && observation.localization_generation === source.localization_generation && Number.isInteger(source.localization_generation)
    && observation.runtime_instance_generation === source.runtime_instance_generation && source.runtime_instance_generation
    && observation.localization_map_id === source.localization_map_id && source.localization_map_id
    && observation.localization_map_revision === source.localization_map_revision && source.localization_map_revision
    && ['x', 'y', 'z', 'roll', 'pitch', 'yaw'].every(key => finite(observation.pose?.[key])));
}

export function preparationModel({ state, navigation = {}, draft3d, draft2d, error = '', available = true }) {
  navigation ||= {};
  const selected = state?.selected;
  const source = navigation.operational_localization;
  const enabled = Boolean(draft3d || selected || source || navigation.operational_expected);
  const active = ['starting', 'running', 'stopping'].includes(navigation.pipeline?.state);
  const running = navigation.pipeline?.state === 'running';
  const geometry = selected?.seed_geometry;
  const pairChecks = Array.isArray(state?.pair?.checks) ? state.pair.checks : [];
  const geometryCodes = new Set(['INITIAL_HEIGHT_TILT_REQUIRED', 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED']);
  const geometryBlocked = pairChecks.some(check => geometryCodes.has(check.code));
  const legacySeed = selected && selected.workflow !== 'staged_navigation_pair' && Array.isArray(selected.seed_T_map_imu);
  const geometryReady = Boolean(!geometryBlocked && (legacySeed || geometry && ['z', 'roll', 'pitch'].every(key => finite(geometry[key]))));
  const matched = state?.pair?.valid !== false && samePin(selected?.localization_3d, draft3d) && samePin(selected?.navigation_2d, draft2d);
  const applied = Boolean(running && source?.bundle_generation === selected?.generation
    && samePin(navigation.map, selected?.navigation_2d)
    && source?.localization_map_id === selected?.localization_3d?.map_id
    && source?.localization_map_revision === selected?.localization_3d?.revision);
  const marker = operationalPoseContextMatches(source?.accepted_initial_pose, source, navigation.map)
    && source.accepted_initial_pose.accepted === true ? source.accepted_initial_pose : null;
  const estimate = operationalPoseContextMatches(source?.estimated_pose, source, navigation.map) ? source.estimated_pose : null;
  const tracking = Boolean(matched && applied && source.fresh === true && source.ready === true && estimate && estimate.stale !== true);
  const nodesReady = applied && source?.fresh === true && (navigation.safety?.can_set_initial_pose === true || Boolean(marker));
  const goalReady = tracking && navigation.safety?.can_send_goal === true;
  const goalContext = navigation.goal?.precision_evidence?.context;
  const currentGoal = navigation.pipeline?.job_id && navigation.goal?.goal_id
    && navigation.goal.precision_evidence?.goal_id === navigation.goal.goal_id
    && goalContext?.job_id === navigation.pipeline.job_id
    && goalContext?.map_id === navigation.map?.id && goalContext?.map_revision === navigation.map?.revision ? navigation.goal : null;
  const matchWaiting = ['WAITING_EXPLICIT_MAP_MATCH', 'WAITING_EXPLICIT_MATCH'].includes(source?.state);
  const issues = [];
  for (const check of pairChecks) issues.push(issue(check.code || 'PAIR_CHECK_FAILED', check.current || '서버 검사 미충족', check.required || '서버 검증 통과', check.remedy || '해당 단계를 다시 확인하세요.', geometryCodes.has(check.code) ? 2 : state.pair.restart_from_step || 1));
  if (!draft3d) issues.push(issue('MAP_3D_REQUIRED', '3D 지도 미선택', '위치추정용 저장 3D 지도', '3D 위치추정 지도에서 지도를 선택하세요.', 1));
  if (!draft2d) issues.push(issue('MAP_2D_REQUIRED', '2D 지도 미선택', '경로 계산용 2D 지도', '2D 경로 계산 지도를 선택하세요.', 1));
  if (draft3d && draft2d && !matched) issues.push(issue('PAIR_NOT_APPLIED', '선택한 지도 조합이 서버 준비 구성과 다름', '정확한 ID·revision과 검증된 변환 계보', '① 지도 연결 확인·적용을 누르세요. 실행 중이면 먼저 STOP하세요.', 1));
  if (selected && !geometryReady && !geometryBlocked) issues.push(issue('INITIAL_GEOMETRY_REQUIRED', '초기 높이·기울기 미확인', '지도 좌표의 본체 높이(m)·roll/pitch(rad)', '②에서 확인한 값을 직접 입력하고 초기 높이·기울기 저장을 누르세요.', 2));
  if (selected && selected.calibration?.verified !== true) issues.push(issue('CALIBRATION_REQUIRED', '검증된 교정 정보 없음', '본체·센서·TF와 지도 연결의 서버 검증', '교정·좌표 관계의 서버 검사 결과를 확인하세요.', 2));
  if (running && !applied) issues.push(issue('RUNTIME_SOURCE_MISMATCH', '실행 source 또는 지도·실행 세대 불일치', '선택한 구성과 동일한 실제 source', 'STOP 후 ①에서 지도 구성을 다시 확인하세요.', 3));
  if (applied && !nodesReady) {
    if (source.fresh !== true) issues.push(issue('RUNTIME_STATUS_STALE', '실행 상태 수신 오래됨', '신선한 센서·노드 검사 결과', '입력과 런타임 연결을 확인하고 ③부터 다시 확인하세요.', 3));
    for (const [key, label] of [['scan', '현재 /scan'], ['odometry', 'FAST-LIO 자세'], ['map_server', '지도 서버'], ['planner', '경로 계획 노드'], ['controller', '주행 제어 노드'], ['tf', 'TF']]) {
      if (navigation.readiness?.[key] !== true) issues.push(issue(`NOT_READY_${key.toUpperCase()}`, `${label} 준비 미확인`, `${label}의 실제 입력·노드 준비`, '③의 상세 지표와 주행 로그에서 입력·노드 상태를 확인한 뒤 다시 확인하세요.', 3));
    }
  }
  if (nodesReady && !marker) issues.push(issue('INITIAL_POSE_REQUIRED', '이번 실행의 초기 위치 접수 없음', '현재 지도·실행에 접수된 사용자 위치·방향', '④ INITIAL POSE로 지도에서 현재 위치·방향을 지정하고 SEND POSE를 누르세요.', 4));
  if (marker && !tracking) {
    const [reason, remedy] = REASONS[source.state] || [`정합 확인 필요: ${source.state || '입력 없음'}`, '⑤의 현재 잔차·겹침·입력·정지 상태와 주행 로그를 확인하세요.'];
    issues.push(issue(source.state || 'MATCH_REQUIRED', reason, '품질 검사에 통과한 신선한 저장 지도 보정', remedy, 5));
  }
  if (tracking && !goalReady) issues.push(issue('GOAL_CONDITIONS_REQUIRED', (navigation.safety?.blockers || []).join(' · ') || '목표 전송 조건 미충족', '기존 source·TF·정지·대기·제어 조건', '아래 안전 상태와 정지·대기 증거를 확인하세요. 조건이 회복되면 ⑥부터 다시 확인합니다.', 6));
  if (!available) issues.unshift(issue('STATUS_UNAVAILABLE', '현재 준비 상태 수신 실패', '신선한 서버 상태', '연결을 확인하고 현재 단계 다시 확인을 누르세요.', 1));
  if (error) issues.unshift(issue('REQUEST_REJECTED', error, '서버 검증 통과', '표시된 항목을 해결한 뒤 해당 버튼으로 다시 확인하세요.', 1));
  const statuses = ['미시작', '미시작', '미시작', '미시작', '미시작', '미시작', '미시작'];
  statuses[0] = matched ? '완료' : error || state?.pair?.valid === false ? '오류' : '사용자 입력 필요';
  if (matched) statuses[1] = geometryReady && selected.calibration?.verified === true ? '완료' : '사용자 입력 필요';
  if (statuses[1] === '완료') statuses[2] = nodesReady ? '완료' : navigation.pipeline?.state === 'failed' ? '오류' : active ? '확인 중' : '사용자 입력 필요';
  if (nodesReady) statuses[3] = marker ? '완료' : '사용자 입력 필요';
  if (marker) statuses[4] = tracking ? '완료' : matchWaiting ? '사용자 입력 필요' : /WAITING|CONFIRMING/.test(source?.state || '') ? '확인 중' : '오류';
  if (tracking) statuses[5] = goalReady ? '완료' : '사용자 입력 필요';
  if (goalReady || currentGoal) statuses[6] = currentGoal?.state === 'succeeded' ? '완료' : ['failed', 'rejected'].includes(currentGoal?.state) ? '오류' : ['pending', 'active', 'canceling'].includes(currentGoal?.state) ? '확인 중' : '사용자 입력 필요';
  const checks = [
    matched ? '서버가 준비한 지도 조합과 선택 ID·revision 일치' : '지도 선택 후 명시적 연결 검증 필요',
    geometry ? `명시된 본체 높이 ${geometry.z} m · roll ${geometry.roll} · pitch ${geometry.pitch} rad` : legacySeed ? '기존 명시적 3D 초기값과 교정 구성 사용' : '높이·기울기 값이 없으면 자동으로 0을 사용하지 않습니다.',
    nodesReady ? '이번 실행의 Nav2 초기 위치 접수 조건 확인' : 'Nav2 시작 후 실제 센서·노드·TF 상태를 확인합니다.',
    marker ? '실제 런타임 접수 확인 · 초기 위치 점 보존' : '사용자 초기 위치는 아직 확인되지 않았습니다.',
    source ? `보정 ${source.correction_sequence ?? '—'}회 · 상태 ${source.state || '—'} · 나이 ${finite(source.correction_age_s) ? source.correction_age_s.toFixed(2) + ' s' : '미확인'}` : '현재 저장 지도 정합 결과 없음',
    estimate ? `${tracking ? '실제 정합 추정 위치 수신' : '마지막 추정 위치 · 현재 추적 미확인'} · z ${estimate.pose.z.toFixed(3)} m · roll ${estimate.pose.roll.toFixed(3)} / pitch ${estimate.pose.pitch.toFixed(3)} rad · 목표 전송은 별도 작업` : '지도상 로봇 위치 미확인',
    currentGoal ? `이번 실행의 Nav2 목표 상태: ${currentGoal.state}` : '이번 실행의 목표 전송 없음. 목표를 전송하면 실제 이동이 시작될 수 있습니다.',
  ];
  return { enabled, active, matched, applied, geometryReady, marker, estimate, tracking, matchWaiting, issues,
    canStart: !enabled || Boolean(available && matched && geometryReady && selected.calibration?.verified === true && state?.pair?.can_start !== false),
    canMatch: Boolean(available && matched && geometryReady && nodesReady && marker && matchWaiting && source.fresh === true),
    steps: PREPARATION_STEPS.map(([title, condition], index) => ({ number: index + 1, title, condition, status: statuses[index], result: checks[index],
      issues: issues.filter(item => item.step === index + 1), next: statuses[index] === '완료' })),
  };
}

export function initializeNavigationPreparation({ host, map3dSelect, map2dSelect, api, context, onChange, actions }) {
  let state = null, busy = false, available = true, error = '', fetchError = '', checkedAt = 0, refreshing = false, draftTouched = false, actionStep = null;
  let lastContext = '', invalidated = '', selected3d = '', draft3dRevision = '', geometryGeneration = '';
  const node = (tag, text, className) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; };
  host.innerHTML = `<div class="panel-header compact"><div><div class="eyebrow">STORED MAP NAVIGATION</div><h2>단계별 주행 준비</h2></div><button type="button" data-prep="refresh">현재 단계 다시 확인</button></div>
    <p data-prep="current"></p><p data-prep="selected"></p><p data-prep="applied"></p><p data-prep="invalidation" role="status"></p>
    <div class="navigation-preparation-actions"><button type="button" data-prep="pair">① 지도 연결 확인·적용</button><button type="button" data-prep="clear">기존 2D 모드로 복구</button></div>
    <details class="navigation-seed-geometry"><summary>② 초기 높이·기울기 입력</summary><p>현재 로봇 본체 원점(base_link)의 지도 좌표 높이(m), roll·pitch(rad)를 확인해 입력하세요. 바닥 높이와 본체 원점의 높이는 다릅니다. 값이 없으면 이 단계에서 표시하며, 임의의 0이나 이전 실행값을 사용하지 않습니다. 센서의 현재 입력은 Nav2 시작 후 ③에서 확인합니다.</p>
    <div><label>높이 z (m)<input data-geometry="z" type="number" step="0.001" placeholder="미지정"></label><label>roll (rad)<input data-geometry="roll" type="number" step="0.001" placeholder="미지정"></label><label>pitch (rad)<input data-geometry="pitch" type="number" step="0.001" placeholder="미지정"></label><button type="button" data-prep="geometry">초기 높이·기울기 저장</button></div><p data-prep="geometry-source"></p></details>
    <ol class="navigation-preparation-steps" data-prep="steps"></ol>
    <section class="navigation-preparation-issues" aria-label="준비 상태·해결할 항목"><h3>준비 상태·해결할 항목</h3><div data-prep="issues" role="status"></div></section>
    <details><summary>기술 상세 · 현재 검사 수치와 실행 정보</summary><pre data-prep="details"></pre></details>`;
  const el = name => host.querySelector(`[data-prep="${name}"]`);
  const selectors = node('div', undefined, 'navigation-preparation-map-selectors');
  for (const select of [map3dSelect, map2dSelect]) {
    const label = select.closest('label');
    if (label) selectors.append(label);
  }
  host.insertBefore(selectors, el('current'));
  function current() {
    const ctx = context();
    const maps = ctx.maps || [];
    const draft3d = maps.find(map => map.id === map3dSelect.value && map.kind === 'pointcloud3d');
    return { ...ctx, navigation: ctx.navigation || {}, draft3d, draft2d: ctx.map, model: preparationModel({ state, navigation: ctx.navigation, draft3d, draft2d: ctx.map, error: error || fetchError, available }) };
  }
  function syncOptions() {
    const maps = (context().maps || []).filter(map => map.kind === 'pointcloud3d' && map.revision);
    const desired = map3dSelect.value || (!draftTouched ? state?.selected?.localization_3d?.map_id : '') || '';
    const signature = maps.map(map => `${map.id}:${map.revision}:${map.name}`).join('|');
    if (map3dSelect.dataset.catalog === signature) return;
    map3dSelect.dataset.catalog = signature;
    map3dSelect.replaceChildren(node('option', '3D 위치추정 지도 선택'));
    map3dSelect.firstChild.value = '';
    maps.forEach(map => { const option = node('option', `${map.name} · ${map.revision.slice(0, 8)}`); option.value = map.id; map3dSelect.append(option); });
    if (maps.some(map => map.id === desired)) map3dSelect.value = desired;
    else if (desired) { invalidated = '지도 ID 또는 revision이 변경됐습니다. ①에서 지도를 다시 선택·확인하세요. 기존 목표 주석은 해당 지도에 그대로 보존됩니다.'; draftTouched = true; }
  }
  function render() {
    syncOptions();
    const { navigation = {}, map, model, draft3d, busy: navigationBusy } = current();
    const source = navigation.operational_localization;
    const identity = source ? `${navigation.pipeline?.job_id}:${source.bundle_generation}:${source.localization_generation}:${source.runtime_instance_generation}` : '';
    if (lastContext && identity && lastContext !== identity) invalidated = '실행 또는 위치추정 세대가 변경됐습니다. ③~⑥의 현재 증거를 다시 확인하세요. 지도 구성이 같으면 ①~②는 유지됩니다.';
    if (identity) lastContext = identity;
    const selected = state?.selected;
    if (geometryGeneration !== (selected?.generation || '')) {
      geometryGeneration = selected?.generation || '';
      host.querySelectorAll('[data-geometry]').forEach(input => { input.value = ''; });
    }
    const mapName = pinValue => (context().maps || []).find(entry => samePin(entry, pinValue))?.name || pinValue?.map_id || '없음';
    const nextStep = busy && actionStep ? model.steps[actionStep - 1] : model.steps.find(step => step.status !== '완료') || model.steps[6];
    el('current').textContent = model.enabled || busy ? `현재 단계: ${nextStep.number}. ${nextStep.title} · ${busy ? '확인 중' : nextStep.status}` : '현재 모드: 기존 2D · 저장 지도 위치추정은 3D 지도 선택 후 준비';
    el('selected').textContent = `화면 선택: 3D ${draft3d?.name || '미선택'} / 2D ${map?.name || '미선택'} · 서버 준비 구성: ${selected ? `${mapName(selected.localization_3d)} / ${mapName(selected.navigation_2d)}` : '기존 2D 모드'}`;
    el('applied').textContent = source ? `실제 실행: ${source.source || 'source 미확인'} · 3D ${mapName({ map_id: source.localization_map_id, revision: source.localization_map_revision })} / 2D ${mapName(navigation.map)} · ${model.applied ? '준비 구성과 일치' : '구성 일치 미확인'} · ${model.tracking ? '추적 중' : '지도상 현재 위치 미확인'}` : '실제 실행: 저장 3D 지도 위치추정 미적용';
    el('invalidation').textContent = invalidated;
    map3dSelect.disabled = busy || navigationBusy || model.active;
    el('pair').disabled = busy || navigationBusy || model.active || !draft3d || !map;
    el('clear').disabled = busy || navigationBusy || model.active || !selected;
    el('geometry').disabled = busy || navigationBusy || model.active || !selected;
    host.querySelectorAll('[data-geometry]').forEach(input => { input.disabled = busy || navigationBusy || model.active || !selected; });
    const geometry = selected?.seed_geometry;
    el('geometry-source').textContent = geometry ? `출처: ${geometry.source || '사용자 명시 입력'} · 확인 시각: ${finite(geometry.confirmed_at) ? new Date(geometry.confirmed_at * 1000).toLocaleString() : '서버 확인 정보 참고'} · 현재 구성에만 적용` : '이번 구성에 확인된 높이·기울기 없음';
    el('steps').replaceChildren(...model.steps.map(step => {
      const item = node('li'); item.dataset.state = step.status;
      item.append(node('strong', `${step.number}. ${step.title}`), node('span', step.status, 'preparation-state'), node('p', `완료 조건: ${step.condition}`), node('p', `검사 결과: ${step.result}`));
      const missing = step.issues.map(value => value.current).join(' · ');
      if (missing) item.append(node('p', `부족/실패: ${missing}`, 'preparation-missing'));
      item.append(node('small', step.next ? '다음 단계 확인 가능' : step.number > 1 && model.steps[step.number - 2].status !== '완료' ? `${step.number - 1}단계 확인 후 진행` : '조건을 해결한 뒤 이 단계에서 다시 확인'));
      const action = { 3: ['Nav2 시작', actions.start, !model.canStart || model.active], 4: ['INITIAL POSE 지정', actions.initial, navigation.safety?.can_set_initial_pose !== true], 5: ['정합 시작', match, !model.canMatch], 7: ['GOAL POSE 지정', actions.goal, navigation.safety?.can_send_goal !== true || !model.tracking] }[step.number];
      if (action) { const button = node('button', action[0]); button.type = 'button'; button.disabled = busy || navigationBusy || action[2]; button.onclick = action[1]; item.append(button); }
      return item;
    }));
    el('issues').replaceChildren(...(model.issues.length ? model.issues.map(value => { const item = node('p'); item.append(node('strong', `${value.step}단계 · ${value.current}`), document.createElement('br'), node('span', `필요: ${value.required} → 해결: ${value.remedy}`)); return item; }) : [node('p', model.enabled ? '현재 확인된 필수 항목 충족. 다음 단계 버튼으로 진행하세요.' : '3D 지도를 선택하면 단계별 저장 지도 위치추정 준비가 시작됩니다. 기존 2D 모드의 상태는 아래에서 확인하세요.')]));
    el('details').textContent = JSON.stringify({ selected: selected ? { generation: selected.generation, localization_3d: selected.localization_3d, navigation_2d: selected.navigation_2d, seed_geometry: geometry } : null, pair: state?.pair, runtime: source, readiness: navigation.readiness, metrics: navigation.localization_health?.metrics, errors: model.issues.map(value => value.code) }, null, 2);
    return model;
  }
  async function refresh(force = false) {
    if (refreshing || busy || (!force && Date.now() - checkedAt < 2500)) return;
    refreshing = true;
    try { state = await api('/api/v1/navigation/operational-3d', { signal: AbortSignal.timeout(10000) }); available = true; fetchError = ''; if (!draftTouched && !map3dSelect.value && state.selected?.localization_3d?.map_id) map3dSelect.value = state.selected.localization_3d.map_id; }
    catch (failure) { available = false; fetchError = `상태 확인 실패: ${failure.message}`; }
    finally { checkedAt = Date.now(); refreshing = false; render(); onChange(); }
  }
  async function run(path, body, method = 'POST') {
    if (busy) return;
    busy = true; error = ''; actionStep = path.endsWith('/seed-geometry') ? 2 : path.endsWith('/match') ? 5 : 1; render(); onChange();
    try { state = await api(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(15000) }); available = true; invalidated = ''; }
    catch (failure) { error = failure.message; }
    finally { busy = false; actionStep = null; checkedAt = 0; await refresh(true); render(); onChange(); }
  }
  async function match() {
    const { model, navigation } = current();
    if (!model.canMatch) return;
    const source = navigation.operational_localization;
    await run('/api/v1/navigation/operational-3d/match', { map_id: navigation.map.id, map_revision: navigation.map.revision,
      bundle_generation: source.bundle_generation, localization_generation: source.localization_generation,
      initial_pose_stamp_ns: source.accepted_initial_pose.stamp_ns });
  }
  map3dSelect.addEventListener('change', () => { draftTouched = true; selected3d = map3dSelect.value; draft3dRevision = current().draft3d?.revision || ''; error = ''; render(); onChange(); });
  map2dSelect.addEventListener('change', () => { draftTouched = true; error = ''; });
  el('pair').onclick = () => { const { draft3d, map } = current(); if (!draft3d || !map) return; void run('/api/v1/navigation/operational-3d/pair', { map_id: draft3d.id, map_revision: draft3d.revision, navigation_map_id: map.id, navigation_map_revision: map.revision }); };
  el('clear').onclick = async () => { await run('/api/v1/navigation/operational-3d', undefined, 'DELETE'); if (!state?.selected) { map3dSelect.value = ''; draftTouched = true; render(); onChange(); } };
  el('geometry').onclick = () => {
    const values = Object.fromEntries([...host.querySelectorAll('[data-geometry]')].map(input => [input.dataset.geometry, input.value.trim() === '' ? null : Number(input.value)]));
    if (!['z', 'roll', 'pitch'].every(key => finite(values[key]))) { error = '높이·roll·pitch를 모두 명시적으로 입력하세요. 빈 값은 0으로 처리하지 않습니다.'; render(); return; }
    void run('/api/v1/navigation/operational-3d/seed-geometry', { generation: state?.selected?.generation, ...values });
  };
  el('refresh').onclick = () => { error = ''; void refresh(true); void actions.refresh(); };
  return { render() { const result = render(); const next = current().draft3d; if (selected3d && next?.id === selected3d && draft3dRevision && next.revision !== draft3dRevision) invalidated = '3D 지도 revision이 변경됐습니다. ①부터 다시 확인하세요.'; return result; }, refresh,
    canStart: () => current().model.canStart, permitsGoal: () => !current().model.enabled || current().model.tracking,
    state: () => state };
}
