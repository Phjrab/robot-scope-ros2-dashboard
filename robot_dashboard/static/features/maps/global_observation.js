import { GlobalObservationController } from './global_observation_contract.js';

export function globalObservationSummary(record) {
  const value = record?.result?.observation;
  if (!value) return '';
  const selection = value.selection_policy;
  const provisional = selection?.schema === 'robot-scope.global-provisional-selection.v1'
    && selection.adapter === 'dashboard-v031-residual-gate-v1'
    && selection.scope === 'PROVISIONAL_OBSERVATION_ONLY'
    && selection.scoring === 'UNCHANGED_ORIGINAL_REFERENCE_POPULATION'
    && selection.original_max_rmse_m === .05 && selection.provisional_max_rmse_m === .10
    && selection.original_selection_replayed === false;
  const label = selection == null ? '원본 선택 후보' : provisional ? '잠정 10cm 선택 후보' : '선택 정책 미검증';
  const selected = label === '선택 정책 미검증' ? label
    : Number.isInteger(value.selected_candidate) ? `${label} ${value.selected_candidate}` : `${label} 없음`;
  const gateReasons = Array.isArray(value.gate_reasons) ? value.gate_reasons : value.rejection_reasons;
  const gates = Array.isArray(gateReasons) ? gateReasons.join(', ') : '미제공';
  const captured = record.captured_context, reference = captured?.map, provenance = reference?.reference_provenance;
  const editedReference = provenance?.asset_role === 'EDITED_FULL_SOURCE'
    && provenance.scoring_population === 'THIS_EDITED_MAP_COMPLETE_XYZ'
    && provenance.parent_score_comparable === false
    && reference.map_id === captured.map_id && reference.map_revision === captured.map_revision
    && reference.frame_id === captured.map_frame
    && provenance.direct_parent && (provenance.direct_parent.map_id !== captured.map_id
      || provenance.direct_parent.revision !== captured.map_revision);
  const comparisonNote = editedReference
    ? ' · 선택한 편집 지도의 전체 XYZ로 채점했습니다. 부모 원본 지도와 RMSE를 직접 비교할 수 없으며, 낮은 잔차가 원본 대비 정확도 개선을 뜻하지 않습니다.' : '';
  return `${value.status || '상태 미제공'} · ${selected} · 거부 사유 ${gates || '없음'} · T_map_sensor는 캡처 시점 센서의 과거 가설입니다. 현재 pose·본체 pose·추적으로 적용하지 않습니다.${comparisonNote}`;
}

export function globalResidualText(observation) {
  if (!Array.isArray(observation?.residual_comparisons)) return '원본 5cm / 잠정 10cm 잔차 비교 미제공';
  const policy = observation.residual_comparison_policy;
  const compact = policy?.schema === 'robot-scope.residual-comparison-policy.v1'
    && policy.candidate_index_basis === 'CANDIDATE_ARRAY_INDEX'
    && Array.isArray(policy.comparison_fields) && policy.comparison_fields.length === 2
    && policy.comparison_fields[0] === 'residual_passed'
    && policy.comparison_fields[1] === 'original_residual_passed'
    && policy.policy?.unit === 'm' && policy.policy?.max_rmse_m === .10
    && policy.original_policy?.max_rmse_m === .05
    && policy.overall_candidate_acceptance_evaluated === false
    && policy.overall_candidate_accepted === null
    && Array.isArray(observation.candidates)
    && observation.residual_comparisons.length === observation.candidates.length;
  if (policy != null && !compact) return '원본 5cm / 잠정 10cm 잔차 비교 미검증';
  const parts = observation.residual_comparisons.map((item, index) => {
    const candidateIndex = compact ? index : item?.candidate_index;
    const rmse = compact ? observation.candidates[index]?.rmse_m : item?.evaluation?.rmse_m;
    const original = compact && Array.isArray(item) ? item[1] : item?.evaluation?.original_residual_passed;
    const provisional = compact && Array.isArray(item) ? item[0] : item?.evaluation?.residual_passed;
    const legacy = !compact && item?.evaluation?.policy?.unit === 'm'
      && item?.evaluation?.original_policy?.max_rmse_m === .05
      && item?.evaluation?.policy?.max_rmse_m === .10
      && item?.evaluation?.overall_candidate_acceptance_evaluated === false
      && item?.evaluation?.overall_candidate_accepted === null;
    if ((compact && (!Array.isArray(item) || item.length !== 2)) || (!compact && !legacy))
      return `후보 ${candidateIndex}: 잔차 비교 미검증`;
    if (!Number.isInteger(candidateIndex) || !Number.isFinite(rmse) || rmse < 0
        || typeof original !== 'boolean' || typeof provisional !== 'boolean'
        || original !== (rmse <= .05) || provisional !== (rmse <= .10))
      return `후보 ${candidateIndex}: 잔차 비교 미검증`;
    return `후보 ${candidateIndex}: RMSE ${rmse.toFixed(5)} m · 원본 5cm ${original ? '통과' : '미통과'} · 잠정 10cm ${provisional ? '통과' : '미통과'}`;
  });
  return parts.join(' | ') + ' · 이 잔차 비교 표시는 후보 선택·다른 gate·실제 정확도 판정을 바꾸지 않습니다.';
}

export function initializeGlobalMapObservation({ getContext }) {
  const layout = document.querySelector('.saved-layout');
  if (!layout) return null;
  const style = document.createElement('link'); style.rel = 'stylesheet'; style.href = '/static/features/maps/global_observation.css'; document.head.append(style);
  const panel = document.createElement('section'); panel.id = 'savedGlobalObservation'; panel.className = 'panel saved-global-observation';
  panel.innerHTML = `<strong>저장 3D 지도 · 비동기 전역 관측</strong>
    <p>수신 PointCloud2의 XYZ 전체 한 장으로 초기 위치 가설을 찾습니다. 변환 전 센서 원본 archive는 아니며, upstream 처리도 미검증입니다. 완료돼도 과거 관측으로만 보존합니다.</p>
    <p id="savedGlobalProvider" role="status">실행 환경 확인 중</p>
    <div class="saved-global-actions"><button id="savedGlobalStart" type="button" disabled>수신 점군 전역 관측 시작</button><button id="savedGlobalRetry" type="button" hidden>같은 요청 재확인</button><button id="savedGlobalCancel" type="button" disabled>관측 취소</button><button id="savedGlobalExport" type="button" disabled>과거 관측 JSON</button></div>
    <strong id="savedGlobalState" role="status">IDLE · HISTORICAL_ONLY</strong><p id="savedGlobalCapture"></p>
    <p id="savedGlobalSummary"></p><p id="savedGlobalResidual"></p>
    <details id="savedGlobalDetails" hidden><summary>원본 후보·gate·잔차·변환 전체 기록</summary><pre id="savedGlobalRecord"></pre></details>
    <small>운영 적용 없음 · 본체 변환/추적/정밀 정확도 미검증. 이 패널은 카메라·주행·TF를 시작하지 않습니다.</small>`;
  (document.querySelector('#savedLiveObservation') || layout).after(panel);
  const el = name => panel.querySelector(`#savedGlobal${name}`);
  let disposed = false, visible = false;
  const model = new GlobalObservationController({ changed: render });
  function render() {
    if (disposed) return;
    const state = model.snapshot(), job = state.job;
    panel.hidden = !visible;
    el('Provider').textContent = state.provider?.available
      ? `고정 소스 설정 확인 · ${state.provider.backend_id || 'backend 미제공'} · 실행 의존성은 작업 시작 시 검사합니다.`
      : `실행 불가 · ${state.provider?.reason || '상태 확인 필요'} · 실행 환경이 확인되기 전 시작할 수 없습니다.`;
    el('Start').disabled = !state.canStart; el('Retry').hidden = !state.canRetry;
    el('Cancel').disabled = !state.canCancel; el('Export').disabled = !state.record;
    el('State').textContent = `${state.error || (state.busy && !job ? '작업 확인 중' : job?.state?.toUpperCase() || 'IDLE')} · HISTORICAL_ONLY${job?.worker_active ? ' · worker 정리 전' : ''}`;
    const context = job?.captured_context;
    const age = job?.capture_age_s ?? context?.capture_age_s;
    el('Capture').textContent = context
      ? `지도 ${context.map_id} @ ${context.map_revision} [${context.map_frame}] · source ${context.source_stamp_ns} ns [${context.source_frame}] · stage ${context.source_pipeline_stage || '미제공'} · clock ${context.source_clock || context.source_clock_domain || '확인되지 않음'} · 관측 호스트 수신 이후 age ${typeof age === 'number' && Number.isFinite(age) ? `${age.toFixed(3)} s` : '미제공'} (원본 시계 신선도 아님) · epoch ${context.observer_epoch}`
      : state.map ? `선택 지도 ${state.map.map_id} @ ${state.map.map_revision} [${state.map.map_frame}] · 원본 캡처 대기` : '3D 저장 지도를 선택하세요.';
    el('Summary').textContent = globalObservationSummary(state.record);
    el('Residual').textContent = state.record ? globalResidualText(state.record.result.observation) : '';
    el('Details').hidden = !state.record;
    el('Record').textContent = state.record ? JSON.stringify(state.record, null, 2) : '';
  }
  function sync() {
    const context = getContext(); visible = context.visible && !layout.hidden;
    model.setMap(context.meta, context.cloud); render();
  }
  el('Start').addEventListener('click', () => { sync(); void model.start(); });
  el('Retry').addEventListener('click', () => { sync(); void model.start(); });
  el('Cancel').addEventListener('click', () => { void model.cancel(); });
  el('Export').addEventListener('click', () => {
    const record = model.snapshot().record; if (!record) return;
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
