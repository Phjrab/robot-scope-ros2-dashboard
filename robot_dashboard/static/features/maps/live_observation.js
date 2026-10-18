import { LiveMapObservation } from './live_observation_contract.js';

export function observationAvailabilityText(state) {
  if (state.status !== 'SOURCE_IDENTITY_UNAVAILABLE') return '';
  if (state.provenance_mode === 'subscription_observation') return '출처 미검증 관측 후보에 필요한 subscription·ROS graph 증거가 없거나 오래되었습니다. 최신 수신과 단일 publisher graph 정보가 필요합니다.';
  const missingPublisher = Object.values(state.telemetry || {}).some(value => value && !value.publisher_gid_present);
  return missingPublisher
    ? '이 ROS runtime에서 메시지별 publisher 정보가 제공되지 않습니다. 원본 점군·native odometry 관측은 가능하지만 출처 연속성을 확인할 수 없어 기본 저장 지도 정합 계산은 사용할 수 없습니다. 별도 허용과 최신 subscription·ROS graph 증거가 있으면 출처 미검증 관측 후보만 계산할 수 있습니다.'
    : '원본 관측의 출처 연속성을 확인할 수 없어 저장 지도 정합 계산은 사용할 수 없습니다. publisher 유일성·시각·출처 정보를 확인해야 합니다.';
}

export function observationTelemetryText(telemetry = {}) {
  const describe = (kind, label) => {
    const value = telemetry[kind];
    if (!value) return `${label}: 현재 수신 요약 없음`;
    const freshness = value.freshness === 'RECEIVED' ? '원본 수신' : value.freshness === 'STALE' ? '마지막 수신 · STALE'
      : value.freshness === 'INVALIDATED' ? '무효화된 수신' : '수신 대기';
    const frame = `${value.frame_id || 'frame 없음'}${kind === 'pose' ? ` → ${value.child_frame_id || 'child 없음'}` : ''}`;
    const identity = (!value.publisher_gid_present ? '메시지별 publisher 정보 없음' : `identity ${value.identity_status}`)
      + (value.subscription_session_id ? ` · subscription ${value.subscription_session_id} · graph ${value.graph_state || 'unavailable'} (${value.graph_endpoint_count ?? '—'} endpoint)` : '');
    return `${label}: ${freshness} · ${value.topic || 'topic 없음'} [${frame}] · seq ${value.seq ?? '—'}${kind === 'cloud' ? ` · ${value.point_count}점` : ''} · source ${value.source_stamp_ns || '—'} ns · 수신 age ${Math.round(value.age_ms)} ms · ${identity}`;
  };
  return `${describe('cloud', '점군')} | ${describe('pose', 'native odometry')} · 원본 frame의 관측이며 저장 지도 위치·검증된 본체 자세가 아닙니다. 센서→화면 전체 지연은 미측정입니다.`;
}

export function initializeLiveMapObservation({ scene, getContext, demandChanged }) {
  const host = document.querySelector('.saved-map-panel');
  const layout = host?.closest('.saved-layout');
  if (!host || !layout || !scene) return null;
  const style = document.createElement('link'); style.rel = 'stylesheet'; style.href = '/static/features/maps/live_observation.css'; document.head.append(style);
  const panel = document.createElement('section'); panel.className = 'panel saved-live-observation'; panel.id = 'savedLiveObservation';
  panel.innerHTML = `<div class="saved-live-heading"><strong>저장 3D 지도 · 실험 관측</strong><label><input id="savedLiveEnabled" type="checkbox"> 현재 점군·pose 읽기</label></div>
    <p>지도 기준 초기 위치는 사용자 추정값입니다. 본체 교정·시계·scan deskew는 미검증이며 운영 위치로 적용하지 않습니다.</p>
    <label><input id="savedLiveSourceUnverified" type="checkbox"> 출처 미검증 관측 후보 허용 (주행 적용 없음)</label>
    <p id="savedLiveProvenanceNote" hidden>로컬 subscription과 ROS graph만 확인합니다. 메시지별 publisher·센서 외부변환·본체 자세는 검증되지 않습니다. 모드를 바꾸면 새 확인과 기준점 연결이 필요합니다.</p>
    <div class="saved-live-anchor">${['x','y','z','roll','pitch','yaw'].map(k => `<label>${k.toUpperCase()} (${['x','y','z'].includes(k) ? 'm' : '°'})<input id="savedLive_${k}" type="number" step="0.01" value="0" aria-label="지도 후보 ${k}"></label>`).join('')}</div>
    <label><input id="savedLiveConfirm" type="checkbox"> 정지 상태에서 입력한 지도 위치·방향을 근사 기준점으로 사용합니다. 원점 0은 자동으로 검증되지 않습니다.</label>
    <div class="saved-live-actions"><button id="savedLiveAnchor" type="button">현재 pose를 후보 기준점에 연결</button><button id="savedLiveClear" type="button">기준점 해제</button><button id="savedLiveCenter" type="button">후보 중심</button><button id="savedLiveExport" type="button">관측 JSON</button></div>
    <label><input id="savedLiveRegistration" type="checkbox"> 저장 지도에 scan-to-map 반복 계산 (최대 1 Hz · 운영 적용 없음)</label>
    <strong id="savedLiveState" role="status">OFF</strong><p id="savedLiveAvailability" hidden></p><span id="savedLiveMetrics"></span><small id="savedLiveSource"></small>`;
  // Keep the shared LiDAR/VSLAM preview and inspector row at its fixed size.
  layout.after(panel);
  const el = id => panel.querySelector(`#savedLive${id}`), model = new LiveMapObservation();
  let geometryKey = '', inFlight = false, lastRequest = -Infinity, error = '', wasVisible = false, dynamicCleared = false, requestController = null, disposed = false;
  const wanted = () => model.enabled && getContext().visible && !layout.hidden;
  function clearDynamic(force = false) {
    scene.setStatus({ online: null, lidarOnline: null, snapshot: true, message: model.snapshot().status });
    if (dynamicCleared && !force) return;
    scene.setPointCloudOverlay(null); scene.setRobotPose(null); scene.setRobotVisible(false); scene.setTrail([]); scene.setTrailVisible(false); geometryKey = '';
    dynamicCleared = true;
  }
  function render(baseChanged = false) {
    if (disposed) return false;
    const context = getContext();
    context.visible = context.visible && !layout.hidden;
    panel.hidden = !context.visible;
    model.setMap(context.meta, context.cloud);
    if (!context.visible && wasVisible && model.enabled) model.invalidate('VIEW_SUSPENDED');
    wasVisible = context.visible;
    const state = model.snapshot();
    el('State').textContent = error || state.status;
    el('State').dataset.status = error ? 'ERROR' : state.status;
    el('Anchor').disabled = !state.canAnchor || !el('Confirm').checked;
    el('Center').disabled = !state.pose; el('Export').disabled = !model.samples.length;
    el('Registration').disabled = !state.anchor;
    el('ProvenanceNote').hidden = state.provenance_mode !== 'subscription_observation';
    const availability = observationAvailabilityText(state);
    el('Availability').textContent = availability; el('Availability').hidden = !availability;
    const r = state.registration;
    el('Metrics').textContent = state.pose
      ? `X ${state.pose.x.toFixed(3)} · Y ${state.pose.y.toFixed(3)} · Z ${state.pose.z.toFixed(3)} m | R ${(state.pose.roll*180/Math.PI).toFixed(1)}° · P ${(state.pose.pitch*180/Math.PI).toFixed(1)}° · Y ${(state.pose.yaw*180/Math.PI).toFixed(1)}° | 수신 pair Δ ${(state.receipt_pair_delta_s*1000).toFixed(0)} ms${r?.metrics ? ` | RMSE ${r.metrics.rmse_m?.toFixed(3) ?? '—'} m · overlap ${(r.metrics.overlap_ratio*100).toFixed(0)}%` : ''}` : (state.status === 'SOURCE_IDENTITY_UNAVAILABLE' ? '지도 정합: UNAVAILABLE · NOT_RUN · 지도 기준 pose·잔차 없음' : r ? `${r.reason} · 이전 후보는 현재 결과로 표시하지 않습니다.` : '유효한 현재 입력과 근사 기준점이 필요합니다.');
    el('Source').textContent = observationTelemetryText(state.telemetry);
    if (!model.enabled) return false;
    if (!context.visible || !state.pose || !state.points) { clearDynamic(baseChanged); return true; }
    dynamicCleared = false;
    scene.configureOfficialRobot({ poseOrigin: 'base', adaptiveScale: false, scale: 1 });
    if (baseChanged || geometryKey !== state.geometryKey) {
      if (!scene.setPointCloudOverlay({ points: state.points, frame_id: state.map.frame, color: '#ffb566' })) {
        model.invalidate('OVERLAY_RENDER_REJECTED'); clearDynamic(); return true;
      }
      geometryKey = state.geometryKey;
    }
    scene.options.robotPoseLabel = state.provenance_mode === 'subscription_observation' ? 'GO2 ESTIMATE · SOURCE UNVERIFIED' : 'GO2 ESTIMATE · UNVERIFIED';
    scene.setRobotVisible(context.robotVisible); scene.setRobotPose(state.pose);
    scene.setTrail(state.trail); scene.setTrailVisible(true);
    scene.setStatus({ online: true, snapshot: false, message: state.status });
    return true;
  }
  async function estimate() {
    if (!wanted() || !model.registrationEnabled || !model.anchor || inFlight || performance.now()-lastRequest < 1000) return;
    let body;
    try { body = model.alignmentRequest(); } catch (_) { return; }
    const generation = model.generation;
    inFlight = true; lastRequest = performance.now();
    const requestedAt = lastRequest;
    const controller = new AbortController(); requestController = controller;
    const timeout = setTimeout(() => controller.abort(), 2000);
    try {
      const response = await fetch('/api/v1/observations/map-alignment', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: controller.signal });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : `HTTP ${response.status}`);
      model.applyAlignment(result, generation, requestedAt);
    } catch (e) { model.alignmentFailed(e.message, generation); }
    finally { clearTimeout(timeout); requestController = null; inFlight = false; render(); }
  }
  el('Enabled').addEventListener('change', () => {
    model.enable(el('Enabled').checked); model.registrationEnabled = false; el('Registration').checked = false;
    error = ''; clearDynamic(); demandChanged(); render();
  });
  el('Confirm').addEventListener('change', () => render());
  el('SourceUnverified').addEventListener('change', () => {
    model.setProvenanceMode(el('SourceUnverified').checked ? 'subscription_observation' : 'native_publisher');
    el('Confirm').checked = false; el('Registration').checked = false; requestController?.abort();
    error = ''; clearDynamic(); render();
  });
  for (const k of ['x','y','z','roll','pitch','yaw']) el(`_${k}`).addEventListener('input', () => { model.invalidate('ANCHOR_INPUT_CHANGED'); el('Confirm').checked = false; render(); });
  el('Anchor').addEventListener('click', () => {
    try {
      const pose = Object.fromEntries(['x','y','z','roll','pitch','yaw'].map(k => [k, (el(`_${k}`).value.trim() === '' ? NaN : Number(el(`_${k}`).value)) * (['x','y','z'].includes(k) ? 1 : Math.PI/180)]));
      model.setAnchor(pose, el('Confirm').checked); error = '';
    } catch (e) { error = e.message; }
    render();
  });
  el('Clear').addEventListener('click', () => { model.invalidate('CLEARED'); error = ''; render(); });
  el('Registration').addEventListener('change', () => {
    model.registrationEnabled = el('Registration').checked; model.registration = null; model.generation++;
    model.geometryCache = null; render(); void estimate();
  });
  el('Center').addEventListener('click', () => scene.centerOnPose());
  el('Export').addEventListener('click', () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(model.exportRecord(), null, 2)], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = 'robot-scope-map-observation.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  const timer = setInterval(() => { if (model.enabled) { render(); void estimate(); } }, 100);
  const visibility = new MutationObserver(() => { render(); demandChanged(); });
  visibility.observe(layout, { attributes: true, attributeFilter: ['hidden'] });
  return { wanted, render, ingestPose: value => model.ingestPose(value), ingestCloud: value => model.ingestCloud(value),
    reset: reason => { model.resetInputs(reason); clearDynamic(true); }, destroy: () => { disposed = true; visibility.disconnect(); model.enable(false); requestController?.abort(); clearInterval(timer); clearDynamic(); panel.remove(); style.remove(); } };
}
