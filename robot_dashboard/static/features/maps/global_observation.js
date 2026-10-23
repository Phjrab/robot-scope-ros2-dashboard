import { GlobalObservationController } from './global_observation_contract.js';

export function globalObservationSummary(record) {
  const value = record?.result?.observation;
  if (!value) return '';
  const selected = Number.isInteger(value.selected_candidate) ? `원본 선택 후보 ${value.selected_candidate}` : '원본 선택 후보 없음';
  const gates = Array.isArray(value.rejection_reasons) ? value.rejection_reasons.join(', ') : '미제공';
  return `${value.status || '상태 미제공'} · ${selected} · 거부 사유 ${gates || '없음'} · T_map_sensor는 캡처 시점 센서의 과거 가설입니다. 현재 pose·본체 pose·추적으로 적용하지 않습니다.`;
}

export function globalResidualText(observation) {
  if (!Array.isArray(observation?.residual_comparisons)) return '원본 5cm / 잠정 10cm 잔차 비교 미제공';
  return observation.residual_comparisons.map(item => {
    const e = item.evaluation;
    if (!e || e.policy?.unit !== 'm' || e.original_policy?.max_rmse_m !== .05
        || e.policy?.max_rmse_m !== .10 || e.overall_candidate_acceptance_evaluated !== false
        || e.overall_candidate_accepted !== null) return `후보 ${item.candidate_index}: 잔차 비교 미검증`;
    return `후보 ${item.candidate_index}: RMSE ${Number.isFinite(e.rmse_m) ? e.rmse_m.toFixed(5) : '—'} m · 원본 5cm ${e.original_residual_passed ? '통과' : '미통과'} · 잠정 10cm ${e.residual_passed ? '통과' : '미통과'}`;
  }).join(' | ') + ' · 저장 잔차만 비교하며 원본 선택·다른 gate·실제 정확도 판정을 바꾸지 않습니다.';
}

export function initializeGlobalMapObservation({ getContext, canChangeHistory = () => true }) {
  const layout = document.querySelector('.saved-layout');
  if (!layout) return null;
  const style = document.createElement('link'); style.rel = 'stylesheet'; style.href = '/static/features/maps/global_observation.css'; document.head.append(style);
  const panel = document.createElement('section'); panel.id = 'savedGlobalObservation'; panel.className = 'panel saved-global-observation';
  panel.innerHTML = `<strong>저장 3D 지도 · 비동기 전역 관측</strong>
    <p>수신 PointCloud2의 XYZ 전체 한 장으로 초기 위치 가설을 찾습니다. 변환 전 센서 원본 archive는 아니며, upstream 처리도 미검증입니다. 완료돼도 과거 관측으로만 보존합니다.</p>
    <p id="savedGlobalProvider" role="status">실행 환경 확인 중</p>
    <div class="saved-global-actions"><button id="savedGlobalStart" type="button" disabled>수신 점군 전역 관측 시작</button><button id="savedGlobalRetry" type="button" hidden>같은 요청 재확인</button><button id="savedGlobalCancel" type="button" disabled>관측 취소</button><button id="savedGlobalExport" type="button" disabled>과거 관측 JSON</button></div>
    <div class="saved-global-actions">
      <label for="savedGlobalHistory">저장된 과거 결과 <select id="savedGlobalHistory" aria-describedby="savedGlobalHistoryHelp" disabled><option value="">조회 가능한 결과 없음</option></select></label>
      <button id="savedGlobalHistoryRefresh" type="button" disabled>과거 결과 목록 새로고침</button>
      <label for="savedGlobalHistoryId">이전 작업 ID (선택) <input id="savedGlobalHistoryId" type="text" pattern="[a-f0-9]{24}" maxlength="24" autocomplete="off" spellcheck="false" aria-describedby="savedGlobalHistoryHelp" placeholder="24자리 작업 ID" disabled></label>
      <button id="savedGlobalHistoryOpen" type="button" disabled>선택한 과거 결과 열기</button>
    </div>
    <p id="savedGlobalHistoryHelp">목록은 현재 서버의 최근 결과와 이 화면에서 연 결과입니다. 다른 보존 결과는 작업 ID로 조회할 수 있으며 서버 재시작 후 보존은 보장되지 않습니다. 명시적으로 연 결과만 표시하며 새 관측·추적을 시작하지 않습니다.</p>
    <p id="savedGlobalHistoryStatus" role="status"></p>
    <strong id="savedGlobalState" role="status">IDLE · HISTORICAL_ONLY</strong><p id="savedGlobalCapture"></p>
    <p id="savedGlobalSummary"></p><p id="savedGlobalResidual"></p>
    <details id="savedGlobalDetails" hidden><summary>원본 후보·gate·잔차·변환 전체 기록</summary><pre id="savedGlobalRecord"></pre></details>
    <small>운영 적용 없음 · 본체 변환/추적/정밀 정확도 미검증. 이 패널은 카메라·주행·TF를 시작하지 않습니다.</small>`;
  (document.querySelector('#savedLiveObservation') || layout).after(panel);
  const el = name => panel.querySelector(`#savedGlobal${name}`);
  let disposed = false, visible = false, historyMapKey = '', historyFingerprint = '';
  const historicalIdPattern = /^[a-f0-9]{24}$/;
  const model = new GlobalObservationController({ changed: render, canChangeHistory });
  function selectedHistoricalId() {
    return el('HistoryId').value.trim() || el('History').value;
  }
  function renderHistory(state) {
    const mapKey = JSON.stringify(state.map);
    if (historyMapKey !== mapKey) {
      historyMapKey = mapKey; historyFingerprint = '';
      el('HistoryId').value = ''; el('History').value = '';
    }
    const history = Array.isArray(state.history) ? state.history : [];
    // Polling may update age each second. Rebuild only changed identities/states
    // so a user's explicit choice and keyboard interaction remain intact.
    const fingerprint = JSON.stringify(history.map(job => [job.job_id, job.state, job.captured_context?.source_stamp_ns]));
    if (historyFingerprint !== fingerprint) {
      const selected = el('History').value;
      const options = history.map(job => {
        const option = document.createElement('option'); option.value = job.job_id;
        option.textContent = `${job.job_id} · ${job.state.toUpperCase()} · source ${job.captured_context?.source_stamp_ns || '미제공'} ns`;
        return option;
      });
      if (!options.length) {
        const option = document.createElement('option'); option.value = ''; option.textContent = '조회 가능한 결과 없음'; options.push(option);
      }
      el('History').replaceChildren(...options);
      const preferred = [selected, state.historicalSelection].find(id => id && history.some(job => job.job_id === id));
      el('History').value = preferred || history[0]?.job_id || '';
      historyFingerprint = fingerprint;
    }
    const available = state.canOpenHistorical === true && !state.historyBusy;
    el('History').disabled = !available || !history.length;
    el('HistoryId').disabled = !available;
    el('HistoryRefresh').disabled = !available;
    el('HistoryOpen').disabled = !available || !historicalIdPattern.test(selectedHistoricalId());
    el('HistoryStatus').textContent = state.historyLocked ? '센서 관측이 현재 후보를 사용 중이거나 정리 중입니다. 과거 결과 전환은 관측 종료 확인 후 가능합니다.'
      : state.historyBusy ? '과거 결과 조회 중 · HISTORICAL_ONLY'
      : state.historicalSelection ? `명시적으로 연 과거 작업 ${state.historicalSelection} · HISTORICAL_ONLY${state.historicalCurrentGeneration === false ? ' · 현재 서버 세대와 다름 · 추적 연결 없음' : state.historicalTrackingEligible ? '' : ' · 표시 전용 · 추적 연결 없음'} · 현재 위치로 채택하지 않습니다.`
      : '과거 결과는 선택한 뒤 열어야 표시됩니다. · HISTORICAL_ONLY';
  }
  function render() {
    if (disposed) return;
    const state = model.snapshot(), job = state.displayJob ?? state.job, record = state.displayRecord ?? state.record;
    panel.hidden = !visible;
    renderHistory(state);
    el('Provider').textContent = state.provider?.available
      ? `고정 소스 설정 확인 · ${state.provider.backend_id || 'backend 미제공'} · 실행 의존성은 작업 시작 시 검사합니다.`
      : `실행 불가 · ${state.provider?.reason || '상태 확인 필요'} · 실행 환경이 확인되기 전 시작할 수 없습니다.`;
    el('Start').disabled = !state.canStart; el('Retry').hidden = !state.canRetry;
    el('Cancel').disabled = !state.canCancel; el('Export').disabled = !record;
    el('State').textContent = `${state.error || (state.busy && !job ? '작업 확인 중' : job?.state?.toUpperCase() || 'IDLE')} · HISTORICAL_ONLY${job?.worker_active ? ' · worker 정리 전' : ''}${job?.reason ? ` · ${job.reason}` : ''}`;
    const context = job?.captured_context;
    const age = job?.capture_age_s ?? context?.capture_age_s;
    const ageLabel = state.historicalSelection === job?.job_id ? '조회 당시 호스트 수신 이후 age' : '관측 호스트 수신 이후 age';
    el('Capture').textContent = context
      ? `지도 ${context.map_id} @ ${context.map_revision} [${context.map_frame}] · source ${context.source_stamp_ns} ns [${context.source_frame}] · stage ${context.source_pipeline_stage || '미제공'} · clock ${context.source_clock || context.source_clock_domain || '확인되지 않음'} · ${ageLabel} ${typeof age === 'number' && Number.isFinite(age) ? `${age.toFixed(3)} s` : '미제공'} (원본 시계 신선도 아님) · epoch ${context.observer_epoch}`
      : state.map ? `선택 지도 ${state.map.map_id} @ ${state.map.map_revision} [${state.map.map_frame}] · 원본 캡처 대기` : '3D 저장 지도를 선택하세요.';
    el('Summary').textContent = globalObservationSummary(record);
    el('Residual').textContent = record ? globalResidualText(record.result.observation) : '';
    el('Details').hidden = !record;
    el('Record').textContent = record ? JSON.stringify(record, null, 2) : '';
  }
  function sync() {
    const context = getContext(); visible = context.visible && !layout.hidden;
    model.setMap(context.meta, context.cloud); render();
  }
  el('Start').addEventListener('click', () => { sync(); void model.start(); });
  el('Retry').addEventListener('click', () => { sync(); void model.start(); });
  el('Cancel').addEventListener('click', () => { void model.cancel(); });
  el('History').addEventListener('change', () => { el('HistoryId').value = ''; model.clearHistoricalSelection(); render(); });
  el('HistoryId').addEventListener('input', () => { model.clearHistoricalSelection(); render(); });
  el('HistoryRefresh').addEventListener('click', () => { sync(); void model.poll(); });
  el('HistoryOpen').addEventListener('click', () => {
    sync();
    const id = selectedHistoricalId();
    if (historicalIdPattern.test(id)) void model.openHistorical(id);
  });
  el('Export').addEventListener('click', () => {
    const state = model.snapshot(), record = state.displayRecord ?? state.record; if (!record) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `robot-scope-historical-global-${record.job_id}.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  const timer = setInterval(() => { sync(); if (visible || model.snapshot().busy || model.pending) void model.poll(); }, 1000);
  const mutation = new MutationObserver(sync); mutation.observe(layout, { attributes: true, attributeFilter: ['hidden'] });
  sync(); if (visible) void model.poll();
  return { render: sync, ingestCloud: cloud => model.ingestCloud(cloud), reset: reason => { model.invalidate(reason); model.source = null; },
    destroy: () => { disposed = true; model.destroy(); clearInterval(timer); mutation.disconnect(); panel.remove(); style.remove(); } };
}
