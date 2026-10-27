import { initializeMapSeed } from './map_seed.js';
import { matrixPose, multiply } from '../experiments/recorded_report.js';
import { LiveMapObservation, rpyMatrix } from './live_observation_contract.js';
import { ObservedJoints, GO2_JOINT_NAMES } from './observed_joints.js';
import { initializeObservationSession } from './observation_session.js';
import { ANCHOR_FIELDS, initializeAnchorPresets, validAnchorPose } from './anchor_presets.js';
import { initializeAnchorProposal, anchorSourceContract, sameAnchorSource } from './anchor_proposal.js';

export function observationAvailabilityText(state) {
  if (state.status === 'AGENT_CONNECTION_LOST') return '대시보드 연결이 끊겨 현재 LiDAR·pose 수신 상태를 확인할 수 없습니다. 연결 복구 후 새 입력을 확인하세요.';
  if (state.status === 'ROBOT_TELEMETRY_UNAVAILABLE') return '서버가 로봇 관측 불가 상태를 보고했습니다. 로봇 연결과 센서 수신 상태를 확인하세요.';
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

export function observationRegistrationText(registration) {
  if (!registration) return '';
  const m = registration.metrics, e = registration.residual_evaluation;
  const rmse = typeof m?.rmse_m === 'number' && Number.isFinite(m.rmse_m) ? `${m.rmse_m.toFixed(5)} m` : '미제공';
  const overlap = typeof m?.overlap_ratio === 'number' && Number.isFinite(m.overlap_ratio) ? `${(m.overlap_ratio * 100).toFixed(0)}%` : '미제공';
  const residual = registration.provisional === true
    ? `잠정 10cm 잔차 ${e ? (e.residual_passed ? '통과' : '미통과') : '미평가'} · 원본 5cm 잔차 ${e ? (e.original_residual_passed ? '통과' : '미통과') : '미평가'}`
    : `원본 5cm 잔차 ${m?.rmse_m == null ? '미평가' : m.rmse_m <= .05 ? '통과' : '미통과'}`;
  const original = registration.original_assessment;
  const runtime = Number.isFinite(registration.total_runtime_ms) ? ` · 처리 ${registration.total_runtime_ms.toFixed(1)} ms` : '';
  return `RMSE ${rmse} · overlap ${overlap} · ${residual}${original ? ` · 원본 판정 ${original.status} (${original.reason})` : ''}${runtime} · 정합 잔차≠실제 위치오차 · 본체/추적 미검증`;
}

export function initializeLiveMapObservation({ scene, getContext, demandChanged }) {
  const host = document.querySelector('.saved-map-panel');
  const layout = host?.closest('.saved-layout');
  if (!host || !layout || !scene) return null;
  const style = document.createElement('link'); style.rel = 'stylesheet'; style.href = '/static/features/maps/live_observation.css'; document.head.append(style);
  const panel = document.createElement('section'); panel.className = 'panel saved-live-observation'; panel.id = 'savedLiveObservation';
  panel.innerHTML = `<div class="saved-live-heading"><strong>저장 지도 · 실험 관측</strong><label class="saved-live-toggle"><input id="savedLiveEnabled" type="checkbox"> 현재 점군·pose 읽기</label></div>
    <div class="saved-live-overview">
      <div class="saved-live-status"><strong id="savedLiveState" role="status">OFF</strong><span class="saved-live-qualification">미검증 추정 · 운영 위치 적용 없음</span></div>
      <p>자동 추정 또는 저장된 초기값을 확인한 뒤 기준점 연결·지도 정합을 진행하세요.</p>
      <span id="savedLiveMetrics"></span>
      <span id="savedLiveHeight"></span>
      <p id="savedLiveAvailability" hidden></p>
      <p id="savedLiveProvenanceNote" hidden>로컬 subscription과 ROS graph만 확인합니다. 메시지별 publisher·센서 외부변환·본체 자세는 검증되지 않습니다. 모드를 바꾸면 새 확인과 기준점 연결이 필요합니다.</p>
    </div>
    <div class="saved-live-actions saved-live-result-actions"><button id="savedLiveCenter" type="button">후보 중심</button><button id="savedLiveExport" type="button">관측 JSON</button></div>
    <details class="saved-live-details" id="savedLiveAnchorDetails">
      <summary><span>기준점 설정</span><small>지도 위치·방향</small></summary>
      <div class="saved-live-details-body">
        <p>지도 초기 위치는 확인·수정할 수 있는 근사값입니다. 본체 교정·시계·scan deskew는 미검증입니다.</p>
        <details id="savedLiveCoordinates"><summary>고급 좌표 수정</summary><div class="saved-live-anchor">${['x','y','z','roll','pitch','yaw'].map(k => `<label>${k.toUpperCase()} (${['x','y','z'].includes(k) ? 'm' : '°'})<input id="savedLive_${k}" type="number" step="0.01" value="0" aria-label="지도 후보 ${k}"></label>`).join('')}</div></details>
        <label><input id="savedLiveConfirm" type="checkbox"> 정지 상태에서 입력한 위치·방향을 근사 기준점으로 사용합니다. 원점 0은 자동으로 검증되지 않습니다.</label>
        <div class="saved-live-actions"><button id="savedLiveAnchor" type="button">현재 pose를 기준점에 연결</button><button id="savedLiveClear" type="button">기준점 해제</button></div>
      </div>
    </details>
    <details class="saved-live-details" id="savedLiveAdvancedDetails">
      <summary><span>고급 관측 옵션</span><small>정합·연속 관측·출처 허용</small></summary>
      <div class="saved-live-details-body saved-live-options">
        <label><input id="savedLiveRegistration" type="checkbox"><span>지도 정합 반복 계산<small>scan-to-map · 최대 1 Hz · 운영 적용 없음</small></span></label>
        <label><input id="savedLiveContinuous" type="checkbox"><span>근사 연속 관측<small>정합 실패 시 odometry 유지 · 같은 세션의 새 입력이 모두 수신되면 근사 연결 재개</small></span></label>
        <label><input id="savedLiveRobotModel" type="checkbox" checked><span>Go2 URDF 관절 모델<small>IMU 원점과 몸체 원점이 같다고 가정한 근사 표시 · 실제 관절 입력 사용</small></span></label>
        <label><input id="savedLiveSourceUnverified" type="checkbox"><span>출처 미검증 관측 후보 허용<small>로컬 subscription·ROS graph 기준 · 주행 적용 없음</small></span></label>
      </div>
    </details>
    <details class="saved-live-details" id="savedLiveJointsDetails">
      <summary><span>관절·몸체 높이</span><small id="savedLiveJointsState">관절 수신 대기</small></summary>
      <div class="saved-live-details-body">
        <p>공식 Go2 URDF의 링크·관절 구조입니다. IMU↔본체 보정과 관절·pose 시계 동기화는 미검증입니다. Z는 지면 높이가 아니며 ΔZ는 기준점 연결 이후 odometry의 상대 높이입니다.</p>
        <div class="saved-live-joint-table"><table><thead><tr><th>다리</th><th>Hip (°)</th><th>Thigh (°)</th><th>Calf (°)</th></tr></thead><tbody>${['FR','FL','RR','RL'].map((leg, i) => `<tr><th>${['앞 오른쪽','앞 왼쪽','뒤 오른쪽','뒤 왼쪽'][i]}</th>${['hip','thigh','calf'].map(j => `<td id="savedLiveJoint_${leg}_${j}_joint">—</td>`).join('')}</tr>`).join('')}</tbody></table></div>
      </div>
    </details>
    <details class="saved-live-details" id="savedLiveSourceDetails">
      <summary><span>지도·수신 상세</span><small>원본 출처·시각·frame</small></summary>
      <div class="saved-live-details-body"><small id="savedLiveMap"></small><small id="savedLiveSource"></small></div>
    </details>`;
  // Keep the shared LiDAR/VSLAM preview and inspector row at its fixed size.
  layout.after(panel);
  const el = id => panel.querySelector(`#savedLive${id}`), model = new LiveMapObservation();
  const joints = new ObservedJoints();
  let geometryKey = '', inFlight = false, nextRequest = -Infinity, error = '', wasVisible = false, dynamicCleared = false, requestController = null, disposed = false, suspended = false;
  let presetReference = null, presetMapKey = '', proposalFence = null, seedFeature = null;
  const proposalInputs = () => ({ cloud: model.cloud?.value, pose: model.pose?.value, mode: model.provenanceMode });
  const anchorMapKey = () => JSON.stringify([model.map?.id, model.map?.revision, model.map?.frame]);
  const currentReference = () => model.pose
    ? (model.pose.value.topic === '/Odometry' && model.pose.value.frame_id === 'camera_init' && model.pose.value.child_frame_id === 'body' ? 'FASTLIO_IMU' : 'UNVERIFIED_BODY')
    : presetReference || 'FASTLIO_IMU';
  const readAnchorPose = () => Object.fromEntries(ANCHOR_FIELDS.map(k => [k,
    el(`_${k}`).value.trim() === '' ? NaN : Number(el(`_${k}`).value)]));
  const clearProposalInputs = () => {
    proposalFence = null; presetReference = null; presetMapKey = '';
    el('Confirm').checked = false;
  };
  const fillAnchorPose = (pose, reference) => {
      if (!validAnchorPose(pose)) throw new Error('초기 위치·방향 값을 확인해 주세요.');
      if (model.pose && reference !== currentReference()) throw new Error('프리셋의 IMU/본체 기준이 현재 pose와 다릅니다.');
      proposalFence = null;
      presetReference = reference; presetMapKey = anchorMapKey();
      for (const k of ANCHOR_FIELDS) el(`_${k}`).value = String(Number(pose[k].toFixed(6)));
      el('Confirm').checked = false;
      proposal.invalidateDraft();
      seedFeature?.edit(pose, reference==='FASTLIO_IMU'?'preserved_prior':'approximate');
      error = ''; render();
  };
  const presets = initializeAnchorPresets({
    host: el('AnchorDetails').querySelector('.saved-live-details-body'), getState: () => model.snapshot(),
    getReference: () => presetReference || currentReference(), readPose: readAnchorPose, fillPose: fillAnchorPose,
  });
  const proposal = initializeAnchorProposal({
    host: el('AnchorDetails').querySelector('.saved-live-details-body'), getState: () => model.snapshot(), getInputs: proposalInputs,
    available: () => !disposed && !suspended && model.enabled && getContext().visible,
    onStart: () => {
      el('Confirm').checked = false; render();
    },
    fillPose: (pose, fence) => { fillAnchorPose(pose, 'FASTLIO_IMU'); proposalFence = fence; },
  });
  seedFeature = initializeMapSeed({host:panel.querySelector('.saved-live-overview'),scene,
    getState:()=>model.snapshot(),getInputs:proposalInputs,readPose:readAnchorPose,
    writePose:pose=>{for(const k of ANCHOR_FIELDS) el(`_${k}`).value=Number.isFinite(pose[k])?String(Number(pose[k].toFixed(6))):'';},
    edited:()=>{proposalFence=null;el('Confirm').checked=false;proposal.invalidateDraft();},
    apply:value=>{
      model.ready();
      if(BigInt(model.pose.value.observation.source_stamp_ns)<BigInt(value.capture_stamp_ns)) throw new Error('새 pose 수신을 기다려 주세요.');
      model.setAnchor(matrixPose(multiply(value.T_map_odom,model.pose.matrix)),true);
      requestController?.abort();error='';render();
    },
  });
  const resetSession = reason => {
    model.resetInputs(reason); model.registrationEnabled = false; el('Confirm').checked = false; el('Registration').checked = false;
    requestController?.abort(); error = ''; clearDynamic(true); render();
  };
  const session = initializeObservationSession({ panel, getContext,
    onStart: () => { model.enable(true); el('Enabled').checked = true; resetSession('OBSERVATION_STARTING'); demandChanged(); },
    onSessionChange: () => { model.enable(true); el('Enabled').checked = true; resetSession('OBSERVATION_SESSION_CHANGED'); demandChanged(); },
    onStop: () => resetSession('OBSERVATION_STOPPED') });
  const wanted = () => model.enabled && !suspended && getContext().visible && !layout.hidden;
  function clearDynamic(force = false) {
    scene.setStatus({ online: null, lidarOnline: null, snapshot: true, message: model.snapshot().status });
    if (dynamicCleared && !force) return;
    scene.setPointCloudOverlay(null); scene.setRobotPose(null); scene.setRobotVisible(false); scene.setTrail([]); scene.setTrailVisible(false); geometryKey = '';
    scene.setSensorObservationOverlay?.(null);
    scene.setObservedRobotModel?.(null);
    dynamicCleared = true;
  }
  function render(baseChanged = false) {
    if (disposed) return false;
    const context = getContext();
    context.visible = context.visible && !layout.hidden;
    panel.hidden = !context.visible;
    model.setMap(context.meta, context.cloud);
    if (proposalFence && !sameAnchorSource(proposalFence, anchorSourceContract(proposalInputs()))) {
      clearProposalInputs();
    }
    if (presetReference && presetMapKey !== anchorMapKey()) {
      presetReference = null; presetMapKey = '';
      for (const k of ANCHOR_FIELDS) el(`_${k}`).value = '';
      el('Confirm').checked = false;
    }
    presets.render();
    proposal.render();
    seedFeature?.render(context.visible && !suspended);
    if (!context.visible && wasVisible && model.enabled) model.invalidate('VIEW_SUSPENDED');
    wasVisible = context.visible;
    const state = model.snapshot();
    const jointState = model.enabled && !suspended ? joints.snapshot() : null;
    el('JointsState').textContent = jointState ? `12관절 수신 · ${Math.round(jointState.age_ms)} ms · 시계 동기화 미검증` : '관절 수신 대기 / STALE';
    for (const name of GO2_JOINT_NAMES) el(`Joint_${name}`).textContent = jointState ? (jointState.positions[name] * 180 / Math.PI).toFixed(1) : '—';
    el('Height').textContent = state.pose_reference === 'FASTLIO_IMU' && state.pose
      ? `IMU 지도 Z ${state.pose.z.toFixed(3)} m · 기준점 이후 odometry ΔZ ${state.relative_height_m >= 0 ? '+' : ''}${state.relative_height_m.toFixed(3)} m · 본체 원점 근사`
      : '';
    el('State').textContent = suspended ? 'SENSOR_TRACKING_ACTIVE · 기존 실험 관측 일시 중지' : error || state.status;
    el('State').dataset.status = error ? 'ERROR' : state.status;
    el('Map').textContent = state.map ? `고정 지도 ${state.map.name || state.map.id} · ${state.map.id} · ${state.map.point_count ?? '—'}점 · 저장 ${state.map.saved_at || '미상'} · revision ${state.map.revision}` : '';
    el('Anchor').disabled = !state.canAnchor || !el('Confirm').checked;
    el('Center').disabled = !state.pose; el('Export').disabled = !model.samples.length;
    el('Registration').disabled = !state.anchor;
    el('ProvenanceNote').hidden = state.provenance_mode !== 'subscription_observation';
    const availability = observationAvailabilityText(state);
    el('Availability').textContent = availability; el('Availability').hidden = !availability;
    const r = state.registration;
    el('Metrics').textContent = state.pose
      ? `X ${state.pose.x.toFixed(3)} · Y ${state.pose.y.toFixed(3)} · Z ${state.pose.z.toFixed(3)} m | R ${(state.pose.roll*180/Math.PI).toFixed(1)}° · P ${(state.pose.pitch*180/Math.PI).toFixed(1)}° · Y ${(state.pose.yaw*180/Math.PI).toFixed(1)}° | ${state.pair_method === 'REGISTERED_FRAME_INDEPENDENT_CURRENT_POSE' ? '독립 수신' : '수신 pair'} Δ ${(state.receipt_pair_delta_s*1000).toFixed(0)} ms${r?.metrics ? ` | ${observationRegistrationText(r)}` : r?.reason ? ` | 지도 정합 ${r.reason}` : ''}` : (state.status === 'SOURCE_IDENTITY_UNAVAILABLE' ? '지도 정합: UNAVAILABLE · NOT_RUN · 지도 기준 pose·잔차 없음' : r ? `${r.reason}${r.metrics ? ` | ${observationRegistrationText(r)}` : ''} · 이전 후보는 현재 결과로 표시하지 않습니다.` : '유효한 현재 입력과 근사 기준점이 필요합니다.');
    el('Source').textContent = observationTelemetryText(state.telemetry) + (state.pose
      ? ` | 추적 ${state.pose_reference} (${state.tracked_frame}) · ${state.pose_topic} [${state.odometry_frame}] → ${state.map.frame} · ${state.pair_method} · pose ${state.source_stamp_ns} ns` : '');
    if (!model.enabled || suspended) { if (suspended) clearDynamic(); return false; }
    if (!context.visible || !state.pose || !state.points) { clearDynamic(baseChanged); return true; }
    dynamicCleared = false;
    scene.configureOfficialRobot({ poseOrigin: 'base', adaptiveScale: false, scale: 1 });
    if (baseChanged || geometryKey !== state.geometryKey) {
      if (!scene.setPointCloudOverlay({ points: state.points, frame_id: state.map.frame, color: '#ffb566' })) {
        model.invalidate('OVERLAY_RENDER_REJECTED'); clearDynamic(); return true;
      }
      geometryKey = state.geometryKey;
    }
    scene.options.robotPoseLabel = r?.provisional === true
      ? `GO2 ESTIMATE · PROVISIONAL · ${state.provenance_mode === 'subscription_observation' ? 'SOURCE / BODY UNVERIFIED' : 'BODY UNVERIFIED'}`
      : state.provenance_mode === 'subscription_observation' ? 'GO2 ESTIMATE · SOURCE UNVERIFIED' : 'GO2 ESTIMATE · UNVERIFIED';
    if (state.pose_reference === 'FASTLIO_IMU') {
      scene.setRobotVisible(false); scene.setRobotPose(null); scene.setTrailVisible(false);
      scene.setSensorObservationOverlay({ frameId: state.map.frame, T_map_sensor: rpyMatrix(state.pose),
        trail: state.trail.slice(-40).map(rpyMatrix), referenceLabel: 'FAST-LIO IMU · BODY UNVERIFIED' });
      scene.setObservedRobotModel?.(el('RobotModel').checked && context.robotVisible && jointState ? {
        reference: 'FASTLIO_IMU', body_extrinsic_verified: false, pose: state.pose, joints: jointState.positions,
        expires_at: Math.min(jointState.expires_at, performance.now() + 1000 - Math.max(state.pose_age_ms, state.cloud_age_ms)),
      } : null);
    } else {
      scene.setObservedRobotModel?.(null);
      scene.setSensorObservationOverlay?.(null);
      scene.setRobotVisible(context.robotVisible); scene.setRobotPose(state.pose);
      scene.setTrail(state.trail); scene.setTrailVisible(true);
    }
    scene.setStatus({ online: true, snapshot: false, message: state.status });
    return true;
  }
  async function estimate() {
    if (!wanted() || !model.registrationEnabled || !model.anchor || inFlight || performance.now() < nextRequest) return;
    let body;
    try { body = model.alignmentRequest(); } catch (_) { return; }
    const generation = model.generation;
    inFlight = true;
    const requestedAt = performance.now();
    let retryAfterMs = 1000;
    const controller = new AbortController(); requestController = controller;
    const timeout = setTimeout(() => controller.abort(), 2000);
    try {
      const response = await fetch('/api/v1/observations/map-alignment', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: controller.signal });
      const result = await response.json();
      const retry = response.headers.get('X-Observation-Retry-After-Ms');
      if (retry !== null && /^\d{1,4}$/.test(retry) && Number(retry) <= 1000) retryAfterMs = Number(retry);
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : `HTTP ${response.status}`);
      model.applyAlignment(result, generation, requestedAt);
    } catch (e) { model.alignmentFailed(e.message, generation); }
    finally {
      // Start the server-supplied cooldown at receipt, not at browser send time.
      // Missing headers/network failure use a conservative one-second delay.
      nextRequest = performance.now() + retryAfterMs;
      clearTimeout(timeout); requestController = null; inFlight = false; render();
    }
  }
  el('Enabled').addEventListener('change', () => {
    model.enable(el('Enabled').checked); model.registrationEnabled = false; el('Registration').checked = false;
    error = ''; clearDynamic(); demandChanged(); render();
  });
  el('Confirm').addEventListener('change', () => render());
  el('RobotModel').addEventListener('change', () => render());
  el('Continuous').addEventListener('change', () => {
    model.setContinuousEstimate(el('Continuous').checked, { resumeSameSession: true }); el('Confirm').checked = false;
    requestController?.abort(); error = ''; clearDynamic(); render();
  });
  el('SourceUnverified').addEventListener('change', () => {
    model.setProvenanceMode(el('SourceUnverified').checked ? 'subscription_observation' : 'native_publisher');
    el('Confirm').checked = false; el('Registration').checked = false; requestController?.abort();
    error = ''; clearDynamic(); render();
  });
  for (const k of ['x','y','z','roll','pitch','yaw']) el(`_${k}`).addEventListener('input', () => { proposalFence=null; proposal.invalidateDraft(); seedFeature?.edit(readAnchorPose()); el('Confirm').checked = false; render(); });
  el('Anchor').addEventListener('click', () => {
    try {
      if (presetReference && presetReference !== currentReference()) throw new Error('프리셋의 IMU/본체 기준이 현재 pose와 다릅니다.');
      const pose = Object.fromEntries(['x','y','z','roll','pitch','yaw'].map(k => [k, (el(`_${k}`).value.trim() === '' ? NaN : Number(el(`_${k}`).value)) * (['x','y','z'].includes(k) ? 1 : Math.PI/180)]));
      model.setAnchor(pose, el('Confirm').checked); error = '';
    } catch (e) { error = e.message; }
    render();
  });
  el('Clear').addEventListener('click', () => { proposalFence = null; presetReference = null; presetMapKey = ''; model.invalidate('CLEARED'); error = ''; render(); });
  el('Registration').addEventListener('change', () => {
    model.registrationEnabled = el('Registration').checked; model.registration = null; model.generation++;
    model.geometryCache = null; render(); void estimate();
  });
  el('Center').addEventListener('click', () => model.snapshot().pose_reference === 'FASTLIO_IMU'
    ? scene.centerOnSensorObservation() : scene.centerOnPose());
  el('Export').addEventListener('click', () => {
    const jointState = joints.snapshot();
    const record = { ...model.exportRecord(), articulated_model: {
      enabled: el('RobotModel').checked, source: 'UNITREE_GO2_URDF_DERIVED', origin_assumption: 'URDF_BASE_EQUALS_FASTLIO_IMU',
      body_extrinsic_verified: false, joint_pose_clock_sync_verified: false, joints: jointState,
      relative_odometry_height_m: model.snapshot().relative_height_m ?? null,
    } };
    const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = 'robot-scope-map-observation.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  const timer = setInterval(() => { if (model.enabled) { render(); void estimate(); } }, 100);
  const visibility = new MutationObserver(() => { render(); demandChanged(); });
  visibility.observe(layout, { attributes: true, attributeFilter: ['hidden'] });
  return { wanted, render, suspend: value => {
    const next = Boolean(value); if (next === suspended) return;
    suspended = next; model.resetInputs(next ? 'SENSOR_TRACKING_ACTIVE' : 'SENSOR_TRACKING_ENDED');
    requestController?.abort(); if (next) clearDynamic(true);
    demandChanged(); render();
  }, ingestPose: value => { if (!suspended) model.ingestPose(value); }, ingestCloud: value => { if (!suspended) model.ingestCloud(value); },
    ingestJoints: value => joints.ingest(value),
    reset: reason => {
      joints.clear();
      // Clear the proposal fence before resetting inputs, so the next render
      // preserves the reset cause instead of mistaking missing inputs for a new source.
      if (proposalFence) clearProposalInputs();
      seedFeature?.invalidateSource(); model.resetInputs(reason); clearDynamic(true);
    }, destroy: () => { disposed = true; seedFeature?.destroy(); proposal.destroy(); presets.destroy(); session.destroy(); visibility.disconnect(); model.enable(false); requestController?.abort(); clearInterval(timer); clearDynamic(); panel.remove(); style.remove(); } };
}
