// A selected global hypothesis fills an editable prior, never a live anchor.
import { GlobalObservationController } from './global_observation_contract.js';
import { validAnchorPose } from './anchor_presets.js';

export function anchorSourceContract({ cloud, pose, mode }) {
  if (cloud?.topic !== '/cloud_registered' || cloud.pipeline_stage !== 'registered' || cloud.frame_id !== 'camera_init'
      || pose?.topic !== '/Odometry' || pose.frame_id !== 'camera_init' || pose.child_frame_id !== 'body') return null;
  const co = cloud.observation, po = pose.observation;
  if (!co?.observer_id || co.observer_id !== po?.observer_id || !co.publisher_epoch || !po.publisher_epoch) return null;
  const subscription = o => [o.subscription_evidence?.session_id, o.subscription_evidence?.graph?.fingerprint];
  return { observer_id: co.observer_id, cloud_epoch: co.publisher_epoch, pose_epoch: po.publisher_epoch,
    provenance_mode: mode, cloud_subscription: mode === 'subscription_observation' ? subscription(co) : null,
    pose_subscription: mode === 'subscription_observation' ? subscription(po) : null };
}
export function sameAnchorSource(a, b) {
  return Boolean(a && b && ['observer_id','cloud_epoch','pose_epoch','provenance_mode','cloud_subscription','pose_subscription']
    .every(k => JSON.stringify(a[k]) === JSON.stringify(b[k])));
}
export function validateAnchorProposal(value, jobId, map, inputs) {
  const stamp = s => typeof s === 'string' && /^[1-9][0-9]{0,19}$/.test(s);
  return value?.schema === 'robot-scope.anchor-proposal.v1' && value.job_id === jobId
    && map && ['id','revision','frame'].every(k => value.map?.[k] === map[k])
    && value.pose_reference === 'FASTLIO_IMU' && value.units === 'metres_degrees' && validAnchorPose(value.pose)
    && value.approximate_only === true && value.requires_reanchor === true && value.operational_application === 'NOT_RUN'
    && value.absolute_accuracy_m === null && value.body_extrinsic_verified === false
    && typeof value.ambiguity_unresolved === 'boolean' && Number.isFinite(value.rmse_m) && value.rmse_m >= 0
    && Number.isFinite(value.overlap) && value.overlap >= .6 && value.overlap <= 1
    && Number.isFinite(value.pose_age_s) && value.pose_age_s >= 0 && value.pose_age_s <= 1
    && stamp(value.capture_stamp_ns) && stamp(value.proposal_stamp_ns)
    && BigInt(value.proposal_stamp_ns) >= BigInt(value.capture_stamp_ns)
    && sameAnchorSource(value.source_contract, anchorSourceContract(inputs));
}

export function initializeAnchorProposal({ host, getState, getInputs, available, onStart, fillPose }) {
  const panel = document.createElement('div'); panel.className = 'saved-anchor-proposal';
  panel.innerHTML = `<strong>초기 위치 자동 추정</strong>
    <small>관측기를 시작하고 입력 준비 후 사용하세요. 계산 중에는 정지하고, 제안값을 확인·수정한 뒤 기준점에 연결하세요.</small>
    <div class="saved-live-actions"><button id="savedAnchorEstimateStart" type="button">초기 위치 자동 추정</button>
    <button id="savedAnchorEstimateRetry" type="button" hidden>같은 요청 재확인</button>
    <button id="savedAnchorEstimateCancel" type="button" disabled>추정 취소</button>
    <button id="savedAnchorEstimateApply" type="button" disabled>제안값으로 채우기</button></div>
    <small id="savedAnchorEstimateStatus" role="status"></small>`;
  host.prepend(panel);
  const el = name => panel.querySelector('#savedAnchorEstimate' + name);
  let contextKey = '', sourceKey = '', wasAvailable = false, busy = false, disposed = false, token = 0, message = '';
  const controller = new GlobalObservationController({ inputKind: 'fastlio_imu',
    getProvenanceMode: () => getInputs().mode, changed: draw });
  function draw() {
    if (disposed) return;
    const state = controller.snapshot(), ready = available() && getState().canAnchor === true;
    el('Start').disabled = busy || !ready || !anchorSourceContract(getInputs()) || !state.canStart;
    el('Retry').hidden = !state.canRetry; el('Retry').disabled = busy || !ready;
    el('Cancel').disabled = !state.canCancel;
    el('Apply').disabled = busy || !ready || !state.record || state.record.worker_active;
    const status = {capturing:'입력 확보 중',running:'지도 전체에서 초기 위치 계산 중',succeeded:state.record
      ? '계산 완료 · 제안값으로 채우기를 누르세요' : '이전 추정은 현재 입력에 사용할 수 없습니다. 다시 추정하세요.',
      failed:'추정 실패',stale:'입력·지도 변경으로 무효',timed_out:'계산 제한 시간 초과',cancelled:'취소됨'}[state.job?.state];
    el('Status').textContent = message || state.error || (status ? `${status}${state.job.reason ? ' · '+state.job.reason : ''}`
      : !ready ? '관측 입력 준비와 출처 허용 설정을 먼저 확인하세요.'
      : state.foreignBusy ? '다른 전역 관측이 실행 중입니다.' : state.provider?.available ? '초기 좌표를 직접 입력하지 않고 찾을 수 있습니다.' : '전역 탐색 환경 확인 중 / 사용 불가');
  }
  async function start() {
    if (!available() || !getState().canAnchor || busy) return;
    token++; message = ''; onStart(); await controller.start(); draw();
  }
  el('Start').addEventListener('click', () => { void start(); });
  el('Retry').addEventListener('click', () => { void start(); });
  el('Cancel').addEventListener('click', () => { token++; message = ''; void controller.cancel(); });
  el('Apply').addEventListener('click', async () => {
    const jobId = controller.snapshot().record?.job_id;
    if (!jobId || busy || !available() || !getState().canAnchor) return;
    const revision = ++token, map = { ...getState().map };
    busy = true; message = ''; draw();
    try {
      const response = await fetch(`/api/v1/observations/global-jobs/${jobId}/anchor-proposal`, {cache:'no-store',signal:AbortSignal.timeout(8000)});
      const value = await response.json();
      if (disposed || revision !== token) return;
      if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : `HTTP ${response.status}`);
      if (!validateAnchorProposal(value, jobId, map, getInputs()) || !getState().canAnchor) throw new Error('지도·입력 세대가 달라졌습니다. 다시 추정해 주세요.');
      fillPose(value.pose, value.source_contract);
      message = `${value.ambiguity_unresolved ? '모호한 후보 · 다른 위치일 수 있습니다. ' : ''}IMU 초기값을 채웠습니다. RMSE ${value.rmse_m.toFixed(3)}m · 겹침 ${(value.overlap*100).toFixed(0)}% · 실제 정확도 미검증. 위치 확인 후 기준점 연결·지도 정합을 진행하세요.`;
    } catch (error) { if (revision === token) message = `제안값 사용 불가 · ${error.message}`; }
    finally { busy = false; draw(); }
  });
  function render() {
    if (disposed) return;
    const map = getState().map, key = JSON.stringify(map && [map.id,map.revision,map.frame]);
    const source = JSON.stringify(anchorSourceContract(getInputs()));
    if (key !== contextKey) {
      contextKey = key; token++; message = '';
      controller.setMap(map && {...map,kind:'pointcloud3d',frame_id:map.frame}, null);
    }
    const active = available();
    if (source !== sourceKey || active !== wasAvailable) {
      const hadSource = sourceKey && sourceKey !== 'null'; sourceKey = source;
      wasAvailable = active;
      if (hadSource || controller.snapshot().busy) { token++; message = ''; controller.invalidate('SOURCE_CHANGED'); }
    }
    draw();
  }
  const timer = setInterval(() => { if (available() || controller.snapshot().busy) void controller.poll(); }, 1000);
  return { render, destroy() { disposed = true; token++; clearInterval(timer); controller.destroy(); panel.remove(); } };
}
