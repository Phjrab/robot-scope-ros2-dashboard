import { api } from '../../core/api.js';
import { $, setStatePill } from '../../core/dom.js';

const ui = {
  serviceLifecycleState: $('#serviceLifecycleState'), serviceLifecycleName: $('#serviceLifecycleName'),
  serviceLifecycleInstance: $('#serviceLifecycleInstance'), serviceLifecyclePrivilege: $('#serviceLifecyclePrivilege'),
  serviceLifecycleOperation: $('#serviceLifecycleOperation'), serviceLifecycleConfirm: $('#serviceLifecycleConfirm'),
  serviceRestartButton: $('#serviceRestartButton'), serviceStopButton: $('#serviceStopButton'),
  serviceLifecycleMessage: $('#serviceLifecycleMessage'),
};
let serviceLifecycleSnapshot = null;
let serviceLifecycleBusy = false;
let serviceLifecycleRequestGeneration = 0;
let serviceLifecycleExpected = null;
let initialized = false;
let showToast = () => {};
let getActivePage = () => '';

const SERVICE_LIFECYCLE_ACTIVE_STATES = new Set(['scheduled', 'dispatching', 'queued']);
const SERVICE_LIFECYCLE_BLOCKER_LABELS = {
  control_status_unavailable: '제어 상태 확인 불가',
  manual_control_active: '수동 제어 ARM 활성',
  control_lease_active: '로봇 제어 lease 활성',
  robot_action_active: 'Go2 모션 실행 중',
  navigation_status_unavailable: 'Nav2 상태 확인 불가',
  navigation_active: 'Nav2 자율주행 활성',
  mapping_status_unavailable: '매핑 상태 확인 불가',
  mapping_pipeline_active: 'LiDAR 매핑 파이프라인 활성',
  mapping_operation_active: '지도 저장·변환 작업 중',
  dataset_capture_active: '서버 데이터셋 수집 중',
  dataset_capture_state_unknown: '데이터셋 수집 상태 확인 불가',
  lifecycle_preflight_unavailable: '서버 사전 점검 실패',
};

function serviceLifecycleOperationActive(snapshot = serviceLifecycleSnapshot) {
  return SERVICE_LIFECYCLE_ACTIVE_STATES.has(String(snapshot?.operation?.state || ''));
}

function serviceLifecycleBlockerText(blockers) {
  return (Array.isArray(blockers) ? blockers : [])
    .map((value) => SERVICE_LIFECYCLE_BLOCKER_LABELS[value] || String(value).replaceAll('_', ' '))
    .join(' · ');
}

function serviceLifecycleErrorText(error) {
  if (error?.status === 403) return '요청 출처를 확인하세요.';
  if (error?.status === 409) return '활성 작업이 있어 요청이 차단되었습니다. 상태를 새로 확인하세요.';
  if (error?.status === 503) return '서버 관리 기능 또는 sudo 권한이 준비되지 않았습니다.';
  if (error?.status === 422) return '확인 값이 올바르지 않습니다.';
  return `서버 관리 요청 실패: ${error?.message || '연결 오류'}`;
}

function renderServiceLifecycle() {
  if (!ui.serviceLifecycleState) return;
  const snapshot = serviceLifecycleSnapshot;
  const expected = serviceLifecycleExpected;
  const operation = snapshot?.operation || null;
  const operationState = String(operation?.state || 'idle');
  const operationAction = String(operation?.action || '');
  const blockers = Array.isArray(snapshot?.blockers) ? snapshot.blockers : [];
  const expectedLabel = expected?.action === 'stop' ? 'STOPPING' : 'RESTARTING';

  ui.serviceLifecycleName.textContent = snapshot?.service || 'robot-scope.service';
  ui.serviceLifecycleInstance.textContent = snapshot?.instance_id
    ? String(snapshot.instance_id).slice(0, 12)
    : '—';
  ui.serviceLifecyclePrivilege.textContent = String(snapshot?.privilege?.last_result || 'unknown').toUpperCase();
  ui.serviceLifecycleOperation.textContent = operationAction
    ? `${operationAction.toUpperCase()} · ${operationState.toUpperCase()}`
    : 'IDLE';

  let state = 'waiting';
  let label = 'CHECKING';
  let message = '서버 관리 상태를 확인하고 있습니다.';
  let messageClass = '';
  if (expected) {
    label = expectedLabel;
    message = expected.action === 'stop'
      ? '대시보드 중지를 요청했습니다. 연결 종료는 정상 동작입니다.'
      : '대시보드가 재시작되는 동안 연결이 잠시 끊길 수 있습니다.';
  } else if (!snapshot) {
    state = 'error';
    label = 'UNAVAILABLE';
    message = '서버 관리 상태를 불러오지 못했습니다.';
    messageClass = 'error';
  } else if (operationState === 'failed' || operationState === 'blocked' || operationState === 'cancelled') {
    state = 'error';
    label = operationState.toUpperCase();
    message = `최근 ${operationAction || 'service'} 요청 실패: ${operation?.error || operationState}`;
    messageClass = 'error';
  } else if (!snapshot.enabled) {
    label = 'DISABLED';
    message = '관리 기능은 기본 비활성입니다. Jetson 환경 파일에서 명시적으로 활성화해야 합니다.';
  } else if (!snapshot.privilege?.runner_available) {
    state = 'error';
    label = 'RUNNER MISSING';
    message = 'sudo 또는 systemctl 실행 파일을 확인할 수 없습니다.';
    messageClass = 'error';
  } else if (serviceLifecycleOperationActive(snapshot)) {
    label = operationAction === 'stop' ? 'STOPPING' : 'RESTARTING';
    message = '요청을 systemd에 전달하고 있습니다. 반복해서 누르지 마세요.';
  } else if (blockers.length) {
    label = 'BLOCKED';
    message = `먼저 정지해야 할 작업: ${serviceLifecycleBlockerText(blockers)}`;
  } else if (snapshot.can_restart && snapshot.can_stop) {
    state = 'ok';
    label = 'READY';
    message = '안전 확인 체크 후 대시보드 서비스만 재시작하거나 중지할 수 있습니다.';
    messageClass = 'ok';
  }
  setStatePill(ui.serviceLifecycleState, state, label);
  ui.serviceLifecycleMessage.textContent = message;
  ui.serviceLifecycleMessage.className = `service-lifecycle-message${messageClass ? ` ${messageClass}` : ''}`;

  const locallyConfirmed = Boolean(ui.serviceLifecycleConfirm.checked);
  const locked = serviceLifecycleBusy || Boolean(expected) || serviceLifecycleOperationActive(snapshot);
  ui.serviceLifecycleConfirm.disabled = locked || !snapshot?.enabled || !snapshot?.configured;
  ui.serviceRestartButton.disabled = locked || !snapshot?.can_restart || !locallyConfirmed;
  ui.serviceStopButton.disabled = locked || !snapshot?.can_stop || !locallyConfirmed;
}

function serviceLifecycleTransitionOutcome(expected, snapshot) {
  if (!expected || !snapshot) return { state: 'pending' };
  const instanceChanged = Boolean(
    expected.instanceId
    && snapshot.instance_id
    && snapshot.instance_id !== expected.instanceId
  );
  if (instanceChanged) return { state: 'complete' };
  const operation = snapshot.operation;
  const sameOperation = Boolean(expected.operationId && operation?.id === expected.operationId);
  if (sameOperation && ['failed', 'blocked', 'cancelled'].includes(String(operation?.state || ''))) {
    return { state: 'failed', error: operation?.error || operation?.state };
  }
  return { state: 'pending' };
}

function completeExpectedServiceTransition(snapshot) {
  const expected = serviceLifecycleExpected;
  const outcome = serviceLifecycleTransitionOutcome(expected, snapshot);
  if (outcome.state === 'complete') {
    const action = expected.action;
    serviceLifecycleExpected = null;
    showToast(action === 'restart' ? '대시보드가 새 인스턴스로 재시작되었습니다.' : '대시보드 서비스가 다시 시작되었습니다.');
  } else if (outcome.state === 'failed') {
    serviceLifecycleExpected = null;
    showToast(`서버 요청 실패: ${outcome.error}`, true);
  }
}

async function refreshServiceLifecycle(force = false) {
  if (!force && getActivePage() !== 'settings' && !serviceLifecycleExpected) return;
  const generation = ++serviceLifecycleRequestGeneration;
  try {
    const snapshot = await api('/api/v1/system/service');
    if (generation !== serviceLifecycleRequestGeneration) return;
    serviceLifecycleSnapshot = snapshot;
    completeExpectedServiceTransition(snapshot);
  } catch (error) {
    if (generation !== serviceLifecycleRequestGeneration) return;
    serviceLifecycleSnapshot = null;
    if (serviceLifecycleExpected) {
      const elapsed = Date.now() - serviceLifecycleExpected.startedAt;
      if (elapsed > 90_000) {
        serviceLifecycleExpected = null;
        showToast('서비스 전환을 90초 안에 확인하지 못했습니다.', true);
      }
    } else if (force) {
      showToast(serviceLifecycleErrorText(error), true);
    }
  }
  renderServiceLifecycle();
}

async function requestServiceLifecycle(action) {
  if (serviceLifecycleBusy || serviceLifecycleExpected || !['restart', 'stop'].includes(action)) return;
  if (!ui.serviceLifecycleConfirm.checked) {
    showToast('연결 중단 확인 체크가 필요합니다.', true);
    return;
  }
  const warning = action === 'stop'
    ? '대시보드 서비스를 중지하면 SSH 또는 systemd로 다시 시작할 때까지 접속할 수 없습니다. 정말 중지할까요?'
    : '대시보드 연결이 잠시 끊기며 진행 중이던 화면 상태는 초기화됩니다. 지금 재시작할까요?';
  if (!window.confirm(warning)) return;

  serviceLifecycleBusy = true;
  serviceLifecycleRequestGeneration += 1;
  serviceLifecycleExpected = {
    action,
    instanceId: serviceLifecycleSnapshot?.instance_id || '',
    operationId: '',
    startedAt: Date.now(),
  };
  ui.serviceLifecycleConfirm.checked = false;
  renderServiceLifecycle();
  try {
    const snapshot = await api(`/api/v1/system/service/${action}`, {
      method: 'POST',
      body: JSON.stringify({ confirmed: true }),
    });
    serviceLifecycleSnapshot = snapshot;
    if (serviceLifecycleExpected?.action === action) {
      serviceLifecycleExpected.operationId = String(snapshot?.operation?.id || '');
    }
    showToast(action === 'stop' ? '대시보드 중지 요청을 접수했습니다.' : '대시보드 재시작 요청을 접수했습니다.');
  } catch (error) {
    if (error?.status) serviceLifecycleExpected = null;
    showToast(error?.status ? serviceLifecycleErrorText(error) : '요청 결과를 확인할 수 없습니다. 서비스 상태를 다시 확인합니다.', true);
  } finally {
    serviceLifecycleBusy = false;
    renderServiceLifecycle();
  }
}

export function initializeServiceLifecycleFeature(options = {}) {
  if (initialized) return feature;
  initialized = true;
  showToast = options.showToast || showToast;
  getActivePage = options.getActivePage || getActivePage;
  ui.serviceLifecycleConfirm?.addEventListener('change', renderServiceLifecycle);
  ui.serviceRestartButton?.addEventListener('click', () => requestServiceLifecycle('restart'));
  ui.serviceStopButton?.addEventListener('click', () => requestServiceLifecycle('stop'));
  setInterval(refreshServiceLifecycle, 5000);
  renderServiceLifecycle();
  return feature;
}

const feature = Object.freeze({
  refresh: refreshServiceLifecycle, render: renderServiceLifecycle, request: requestServiceLifecycle,
  hasExpectedTransition: () => Boolean(serviceLifecycleExpected),
});
