import { SensorTrackingController } from './sensor_tracking_contract.js';
import { validatedAmbiguityMetadata } from './global_observation_contract.js';

const activeStates = new Set(['INITIALIZING', 'ACQUIRING_FRESH_SCAN', 'SENSOR_CANDIDATE', 'LOST', 'STALE']);

export function sensorSceneReserved(snapshot, pending, writing) {
  return snapshot.active || snapshot.previewSuppressed || snapshot.stopRequested || Boolean(pending) || writing;
}

export function sensorTrackingStateText(snapshot) {
  const ambiguous = snapshot.global?.ambiguity_override_applied === true
    || validatedAmbiguityMetadata(snapshot.value?.ambiguity_override);
  const warning = ambiguous ? '모호한 미검증 추정 · ' : '';
  if (snapshot.error) return `${warning}센서 연속 관측 확인 실패 · ${snapshot.error} · 센서 마커 숨김`;
  if (snapshot.stopRequested) return `${warning}센서 연속 관측 중지 확인 중 · 센서 마커 숨김`;
  const value = snapshot.value;
  if (!value) return snapshot.global ? `${warning}전역 과거 후보 준비됨 · 센서 연속 관측은 시작 전` : '선택된 전역 후보 대기';
  const names = {
    WAITING_GLOBAL: '전역 후보 대기', INITIALIZING: '센서 관측 초기화 중',
    ACQUIRING_FRESH_SCAN: '새 점군 확인 중', SENSOR_CANDIDATE: '센서 위치·방향 잠정 후보',
    LOST: '센서 위치 상실 · 재탐색 대기', STALE: '센서 자료 오래됨 · 위치 숨김', STOPPED: '센서 연속 관측 중지',
  };
  return `${warning}${names[value.state] || value.state} · ${value.reason || '사유 없음'} · GO2 본체 자세/운영 추적 미검증`;
}

export function sensorTrackingDetailText(snapshot) {
  const value = snapshot.value, source = value?.source, pose = value?.sensor_pose;
  const ambiguous = snapshot.global?.ambiguity_override_applied === true
    || validatedAmbiguityMetadata(value?.ambiguity_override);
  if (!value) return `${ambiguous ? '전역 후보는 모호한 미검증 추정입니다. ' : ''}T_map_sensor는 센서 좌표의 관측입니다. 본체 좌표·실제 위치 정확도·운영 TF를 검증하지 않습니다.`;
  const time = source?.source_stamp_ns || pose?.source_stamp_ns || '미제공';
  const age = Number.isFinite(source?.age_s) ? `${source.age_s.toFixed(3)} s` : '미제공';
  const rmse = Number.isFinite(pose?.rmse_m) ? `${pose.rmse_m.toFixed(5)} m` : '미제공';
  const overlap = Number.isFinite(pose?.overlap) ? `${(pose.overlap * 100).toFixed(1)}%` : '미제공';
  return `지도 ${value.map?.map_id || '미제공'} @ ${value.map?.map_revision || '미제공'} [${value.map?.frame_id || '미제공'}]`
    + ` · 센서 ${source?.topic || '미제공'} [${source?.frame_id || '미제공'}]`
    + ` · 원본 스캔 시각 ${time} ns (원본 clock 미검증)`
    + ` · 호스트 수신 age ${age} · observer epoch ${source?.observer_epoch || '미제공'}`
    + ` · RMSE ${rmse} · overlap ${overlap} · 5cm/10cm는 비교값, 선택 문턱 해제`
    + ` · 시간 연속 관측 ${value.temporal_consistency_confirmed ? '확인' : '미확인'}`
    + (ambiguous ? ` · 모호한 미검증 추정 (${value.ambiguity_source || 'GLOBAL'} 근거) · 대안·gate는 원본 기록 보존` : '')
    + ` · 본체 외부변환 미검증`;
}

export function initializeSensorTrackingObservation({ scene, getContext, getGlobalRecord, onExclusive = () => {} }) {
  const layout = document.querySelector('.saved-layout');
  if (!layout || !scene) return null;
  const style = document.createElement('link'); style.rel = 'stylesheet'; style.href = '/static/features/maps/sensor_tracking.css'; document.head.append(style);
  const panel = document.createElement('section'); panel.id = 'savedSensorTracking'; panel.className = 'panel saved-sensor-tracking';
  panel.innerHTML = `<strong>저장 3D 지도 · 센서 연속 관측</strong>
    <p>전역 탐색이 선택한 과거 센서 후보에서 새 점군으로 이어지는 관측입니다. 센서 마커와 방향축·짧은 궤적만 표시하며 GO2 본체 위치로 해석하지 않습니다.</p>
    <div class="saved-sensor-actions"><button id="savedSensorStart" type="button" disabled>선택된 전역 후보로 센서 관측 시작</button><button id="savedSensorStop" type="button" disabled>센서 관측 중지</button></div>
    <strong id="savedSensorState" role="status">전역 후보 대기</strong><p id="savedSensorDetail"></p>
    <details id="savedSensorAlternatives" hidden><summary>마지막 지역 정합 원본 기록 (과거 진단 · 대안·점수·gate)</summary><pre id="savedSensorAlternativesRecord"></pre></details>
    <small>원본 점군 잔차와 시간적 연속성은 실제 위치 정확도·본체 자세·자율주행 가능성을 뜻하지 않습니다. 운영 TF·제어 입력에 적용하지 않습니다.</small>`;
  (document.querySelector('#savedGlobalObservation') || layout).after(panel);
  const el = name => panel.querySelector(`#savedSensor${name}`);
  let disposed = false, exclusive = false, overlayKey = '', visible = false;
  const model = new SensorTrackingController({ changed: () => queueMicrotask(render) });
  function render() {
    if (disposed) return false;
    const context = getContext();
    visible = Boolean(context.visible && !layout.hidden);
    model.setMap(context.meta, context.cloud);
    model.setGlobalRecord(getGlobalRecord());
    if ((model.startedJobId || model.pending) && !model.global) model.invalidate('GLOBAL_SELECTION_CHANGED');
    const snapshot = model.snapshot(), value = snapshot.value;
    const active = sensorSceneReserved(snapshot, model.pending, model.writing);
    if (active !== exclusive) { exclusive = active; onExclusive(active); }
    if (active) scene.setRobotVisible(false);
    panel.hidden = !visible;
    el('Start').disabled = !snapshot.canStart && !snapshot.canRetry;
    el('Start').textContent = snapshot.canRetry ? '같은 요청 재확인' : '선택된 전역 후보로 센서 관측 시작';
    el('Stop').disabled = !snapshot.canStop;
    el('State').textContent = sensorTrackingStateText(snapshot);
    el('State').dataset.state = snapshot.error ? 'ERROR' : snapshot.state;
    el('Detail').textContent = sensorTrackingDetailText(snapshot);
    el('Alternatives').hidden = !value?.last_alignment;
    el('AlternativesRecord').textContent = value?.last_alignment ? JSON.stringify(value.last_alignment, null, 2) : '';
    const candidate = !snapshot.error && context.cloud?.points?.length && value?.state === 'SENSOR_CANDIDATE'
      && value.temporal_consistency_confirmed === true && value.map?.frame_id === snapshot.map?.map_frame;
    const ambiguous = candidate && validatedAmbiguityMetadata(value.ambiguity_override);
    const nextKey = candidate ? JSON.stringify([value.generation, value.source?.observer_id,
      value.source?.observer_epoch, value.sensor_pose, value.trail, ambiguous]) : '';
    if (nextKey !== overlayKey) {
      overlayKey = nextKey;
      scene.setSensorObservationOverlay(candidate ? {
        frameId: value.map.frame_id, T_map_sensor: value.sensor_pose.T_map_sensor,
        trail: value.trail.map(item => item.T_map_sensor), ambiguous,
      } : null);
    }
    if (active) scene.setStatus({ online: null, lidarOnline: null, snapshot: true,
      message: snapshot.error || value?.state || 'SENSOR_TRACKING_REQUEST_PENDING' });
    return active;
  }
  el('Start').addEventListener('click', () => { render(); void model.start(); });
  el('Stop').addEventListener('click', () => { void model.stop(); });
  const timer = setInterval(() => { render(); if (visible || model.snapshot().active || model.pending) void model.poll(); }, 750);
  const mutation = new MutationObserver(render); mutation.observe(layout, { attributes: true, attributeFilter: ['hidden'] });
  render(); if (visible) void model.poll();
  return { render, snapshot: () => model.snapshot(), reset: reason => {
    model.invalidate(reason); overlayKey = ''; scene.setSensorObservationOverlay(null); render();
  }, destroy: () => {
    disposed = true; model.destroy(); clearInterval(timer); mutation.disconnect();
    scene.setSensorObservationOverlay(null); if (exclusive) onExclusive(false);
    panel.remove(); style.remove();
  } };
}
