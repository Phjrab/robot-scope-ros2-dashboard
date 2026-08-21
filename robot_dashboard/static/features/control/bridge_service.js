import { api } from '../../core/api.js';
import { $, setStatePill } from '../../core/dom.js';

const controlUi = {
  bridgeServiceState: $('#controlBridgeServiceState'), bridgeServiceName: $('#controlBridgeServiceName'),
  bridgeServiceActive: $('#controlBridgeServiceActive'), bridgeServiceSub: $('#controlBridgeServiceSub'),
  bridgeServiceOperation: $('#controlBridgeServiceOperation'), bridgeServiceConfirm: $('#controlBridgeServiceConfirm'),
  bridgeServiceStart: $('#controlBridgeServiceStart'), bridgeServiceStop: $('#controlBridgeServiceStop'),
  bridgeServiceMessage: $('#controlBridgeServiceMessage'),
};
let controlBridgeServiceSnapshot = null;
let controlBridgeServiceBusy = false;
let controlBridgeServiceRequestGeneration = 0;
let controlBridgeServiceMutationGeneration = 0;
let controlBridgeServiceExpected = null;
let initialized = false;
let showToast = () => {};
let getActivePage = () => '';
let refreshControl = () => {};
let refreshNavigationState = () => {};

const CONTROL_BRIDGE_SERVICE_ACTIVE_STATES = new Set(['scheduled', 'dispatching', 'waiting']);
const CONTROL_BRIDGE_SERVICE_FAILED_STATES = new Set(['failed', 'blocked', 'cancelled']);
const CONTROL_BRIDGE_SERVICE_TRANSITION_TIMEOUT_MS = 45_000;
const CONTROL_BRIDGE_SERVICE_BLOCKER_LABELS = {
  control_status_unavailable: '제어 상태 확인 불가',
  manual_control_active: '수동 제어 ARM 활성',
  control_lease_active: '로봇 제어 lease 활성',
  robot_action_active: 'Go2 모션 실행 중',
  control_not_configured: 'Go2 제어 전송 설정 미완료',
  control_target_incompatible: '현재 로봇 대상과 시작 설정 불일치',
  navigation_status_unavailable: 'Nav2 상태 확인 불가',
  navigation_active: 'Nav2 자율주행 활성',
  mapping_status_unavailable: '매핑 상태 확인 불가',
  mapping_pipeline_active: 'LiDAR 매핑 파이프라인 활성',
  mapping_operation_active: '지도 저장·변환 작업 중',
  service_status_unavailable: 'systemd 상태 확인 불가',
  dashboard_service_lifecycle_status_unavailable: '대시보드 서비스 전환 상태 확인 불가',
  dashboard_service_lifecycle_active: '대시보드 서비스 재시작·중지 진행 중',
  control_bridge_service_already_active: '제어 브리지 서비스가 이미 실행 중',
  lifecycle_preflight_unavailable: '서버 사전 점검 실패',
};
const CONTROL_BRIDGE_SERVICE_ERROR_LABELS = {
  preflight_blocked: '안전 사전점검에서 차단됨',
  systemd_status_unavailable: 'systemd 상태 확인 불가',
  dispatch_timeout: 'systemctl 요청 시간 초과',
  dispatch_unavailable: 'systemctl 실행 불가',
  dispatch_failed: 'systemctl 실행 실패',
  dispatch_rejected: 'sudo 권한 또는 systemctl 요청 거부',
  systemd_status_timeout: 'systemd 상태 확인 시간 초과',
  service_transition_timeout: 'systemd 상태 전환 시간 초과',
  bridge_status_timeout: '인증된 브리지 종료 상태 확인 시간 초과',
  application_shutdown: '대시보드 종료로 요청 취소',
};

function controlBridgeServiceOperationActive(snapshot = controlBridgeServiceSnapshot) {
  return CONTROL_BRIDGE_SERVICE_ACTIVE_STATES.has(String(snapshot?.operation?.state || ''));
}

function controlBridgeServiceBlockerText(blockers) {
  return (Array.isArray(blockers) ? blockers : [])
    .map((value) => CONTROL_BRIDGE_SERVICE_BLOCKER_LABELS[value] || String(value).replaceAll('_', ' '))
    .join(' · ');
}

function controlBridgeServiceOperationErrorText(value) {
  const key = String(value || 'unknown');
  return CONTROL_BRIDGE_SERVICE_ERROR_LABELS[key] || key.replaceAll('_', ' ');
}

function controlBridgeServiceErrorText(error) {
  if (error?.status === 403) return '같은 대시보드에서 보낸 요청인지 확인하세요.';
  if (error?.status === 409) return '활성 작업 또는 다른 전환 요청 때문에 차단되었습니다. 상태를 다시 확인하세요.';
  if (error?.status === 422) return '안전 확인 값이 올바르지 않습니다.';
  if (error?.status === 503) return '제어 브리지 관리 기능, systemd 상태 또는 sudo 권한이 준비되지 않았습니다.';
  return `제어 브리지 서비스 요청 실패: ${error?.message || '연결 오류'}`;
}

function controlBridgeServiceDesiredState(snapshot, action) {
  const systemd = snapshot?.systemd || {};
  if (!systemd.available || systemd.transitioning) return false;
  if (action === 'start') return systemd.running === true;
  return action === 'stop'
    && systemd.running === false
    && ['inactive', 'failed'].includes(String(systemd.active_state || '').toLowerCase());
}

function controlBridgeServiceTransitionOutcome(expected, snapshot) {
  if (!expected || !snapshot || !expected.operationId) return { state: 'pending' };
  const operation = snapshot.operation;
  if (!operation || operation.id !== expected.operationId) return { state: 'pending' };
  const operationState = String(operation.state || '');
  if (CONTROL_BRIDGE_SERVICE_FAILED_STATES.has(operationState)) {
    return { state: 'failed', error: operation.error || operationState };
  }
  if (operationState === 'succeeded' && controlBridgeServiceDesiredState(snapshot, expected.action)) {
    return { state: 'complete' };
  }
  return { state: 'pending' };
}

function bindExpectedControlBridgeServiceOperation(snapshot) {
  const expected = controlBridgeServiceExpected;
  const operation = snapshot?.operation;
  if (!expected || expected.operationId || !operation?.id || operation.action !== expected.action) return;
  if (operation.id === expected.baselineOperationId) return;
  const requestedAt = Date.parse(operation.requested_at || '');
  if (!Number.isFinite(requestedAt) || requestedAt < expected.startedAt - 2_000) return;
  expected.operationId = String(operation.id);
}

function completeExpectedControlBridgeServiceTransition(snapshot) {
  bindExpectedControlBridgeServiceOperation(snapshot);
  const expected = controlBridgeServiceExpected;
  const outcome = controlBridgeServiceTransitionOutcome(expected, snapshot);
  if (outcome.state === 'complete') {
    const action = expected.action;
    controlBridgeServiceExpected = null;
    showToast(action === 'start' ? '제어 브리지 서비스가 실행 중입니다.' : '제어 브리지 서비스가 중지되었습니다.');
    void refreshControl();
    void refreshNavigationState();
  } else if (outcome.state === 'failed') {
    controlBridgeServiceExpected = null;
    showToast(`제어 브리지 ${expected.action === 'start' ? '시작' : '중지'} 실패: ${controlBridgeServiceOperationErrorText(outcome.error)}`, true);
  }
}

function renderControlBridgeService() {
  if (!controlUi.bridgeServiceState) return;
  const snapshot = controlBridgeServiceSnapshot;
  const expected = controlBridgeServiceExpected;
  const systemd = snapshot?.systemd || {};
  const operation = snapshot?.operation || null;
  const operationState = String(operation?.state || 'idle');
  const operationAction = String(operation?.action || '');
  const activeState = String(systemd.active_state || (systemd.running ? 'active' : 'unknown'));
  const subState = String(systemd.sub_state || 'unknown');
  const loadState = String(systemd.load_state || 'unknown');
  const startBlockers = Array.isArray(snapshot?.blockers?.start) ? snapshot.blockers.start : [];
  const stopBlockers = Array.isArray(snapshot?.blockers?.stop) ? snapshot.blockers.stop : [];
  const relevantBlockers = systemd.running ? stopBlockers : startBlockers;
  const transitionAction = expected?.action || (controlBridgeServiceOperationActive(snapshot) ? operationAction : '');

  controlUi.bridgeServiceName.textContent = snapshot?.service || 'robot-scope-control-bridge.service';
  controlUi.bridgeServiceActive.textContent = activeState.toUpperCase();
  controlUi.bridgeServiceSub.textContent = `${subState.toUpperCase()} · ${loadState.toUpperCase()}`;
  controlUi.bridgeServiceOperation.textContent = operationAction
    ? `${operationAction.toUpperCase()} · ${operationState.toUpperCase()}`
    : 'IDLE';

  let state = 'waiting';
  let label = 'CHECKING';
  let message = '제어 브리지 서비스 상태를 확인하고 있습니다.';
  let messageClass = '';
  if (expected) {
    label = expected.action === 'start' ? 'STARTING' : 'STOPPING';
    message = expected.action === 'start'
      ? 'systemd에 시작을 요청했습니다. 실제 명령 연결은 위 BRIDGE 상태에서 별도로 확인하세요.'
      : 'systemd에 중지를 요청했습니다. 서비스 정지 상태를 확인하고 있습니다.';
  } else if (!snapshot) {
    state = 'error';
    label = 'UNAVAILABLE';
    message = '제어 브리지 서비스 상태를 불러오지 못했습니다.';
    messageClass = 'error';
  } else if (!snapshot.enabled) {
    label = 'DISABLED';
    message = 'Jetson 환경 설정에서 제어 브리지 관리 기능을 활성화해야 합니다.';
  } else if (!snapshot.privilege?.runner_available) {
    state = 'error';
    label = 'RUNNER MISSING';
    message = 'sudo 또는 systemctl 실행 환경을 확인할 수 없습니다.';
    messageClass = 'error';
  } else if (!snapshot.configured) {
    state = 'error';
    label = 'NOT CONFIGURED';
    message = '고정 서비스 관리 설정을 확인하세요.';
    messageClass = 'error';
  } else if (!systemd.available) {
    state = 'error';
    label = 'STATUS ERROR';
    message = `systemd 상태를 신뢰할 수 없습니다. load=${String(systemd.load_state || 'unknown')} · unit=${String(systemd.unit_file_state || 'unknown')}`;
    messageClass = 'error';
  } else if (controlBridgeServiceOperationActive(snapshot) || systemd.transitioning) {
    label = transitionAction === 'stop' ? 'STOPPING' : 'STARTING';
    message = 'systemd 상태 전환 중입니다. 완료될 때까지 버튼이 잠깁니다.';
  } else if (CONTROL_BRIDGE_SERVICE_FAILED_STATES.has(operationState)) {
    state = 'error';
    label = operationState.toUpperCase();
    if (operationState === 'blocked' && relevantBlockers.length) {
      message = `요청 차단: ${controlBridgeServiceBlockerText(relevantBlockers)}`;
    } else {
      message = `최근 ${operationAction || 'service'} 요청 실패: ${controlBridgeServiceOperationErrorText(operation?.error || operationState)}`;
    }
    messageClass = 'error';
  } else if (systemd.running) {
    state = 'ok';
    label = 'RUNNING';
    message = stopBlockers.length
      ? `서비스 실행 중 · 중지 차단: ${controlBridgeServiceBlockerText(stopBlockers)}`
      : '서비스 실행 중입니다. 실제 명령 연결은 위 BRIDGE 상태에서 별도로 확인하세요.';
    messageClass = stopBlockers.length ? '' : 'ok';
  } else if (activeState.toLowerCase() === 'inactive') {
    label = 'STOPPED';
    message = startBlockers.length
      ? `시작 차단: ${controlBridgeServiceBlockerText(startBlockers)}`
      : '서비스가 중지되어 있습니다. 안전 확인 후 대시보드에서 시작할 수 있습니다.';
  } else {
    state = activeState.toLowerCase() === 'failed' ? 'error' : 'waiting';
    label = activeState.toUpperCase();
    message = relevantBlockers.length
      ? `현재 작업 차단: ${controlBridgeServiceBlockerText(relevantBlockers)}`
      : `systemd 상태: ${activeState}/${subState}`;
    messageClass = state === 'error' ? 'error' : '';
  }

  setStatePill(controlUi.bridgeServiceState, state, label);
  controlUi.bridgeServiceMessage.textContent = message;
  controlUi.bridgeServiceMessage.className = `control-bridge-service-message${messageClass ? ` ${messageClass}` : ''}`;
  const locallyConfirmed = Boolean(controlUi.bridgeServiceConfirm.checked);
  const locked = controlBridgeServiceBusy
    || Boolean(expected)
    || controlBridgeServiceOperationActive(snapshot)
    || Boolean(systemd.transitioning);
  controlUi.bridgeServiceConfirm.disabled = locked
    || !snapshot?.enabled
    || !snapshot?.configured
    || !systemd.available
    || (!snapshot?.can_start && !snapshot?.can_stop);
  controlUi.bridgeServiceStart.disabled = locked || !snapshot?.can_start || !locallyConfirmed;
  controlUi.bridgeServiceStop.disabled = locked || !snapshot?.can_stop || !locallyConfirmed;
  controlUi.bridgeServiceStart.textContent = transitionAction === 'start' ? 'STARTING…' : 'START BRIDGE';
  controlUi.bridgeServiceStop.textContent = transitionAction === 'stop' ? 'STOPPING…' : 'STOP BRIDGE';
  controlUi.bridgeServiceState.setAttribute('aria-busy', locked ? 'true' : 'false');
}

async function refreshControlBridgeService(force = false) {
  if (!force && !['controls', 'navigation'].includes(getActivePage()) && !controlBridgeServiceExpected) return;
  const generation = ++controlBridgeServiceRequestGeneration;
  try {
    const snapshot = await api('/api/v1/control/bridge-service');
    if (generation !== controlBridgeServiceRequestGeneration) return;
    controlBridgeServiceSnapshot = snapshot;
    completeExpectedControlBridgeServiceTransition(snapshot);
    if (controlBridgeServiceExpected
      && Date.now() - controlBridgeServiceExpected.startedAt > CONTROL_BRIDGE_SERVICE_TRANSITION_TIMEOUT_MS) {
      controlBridgeServiceExpected = null;
      showToast('제어 브리지 전환을 45초 안에 확인하지 못했습니다.', true);
    }
  } catch (error) {
    if (generation !== controlBridgeServiceRequestGeneration) return;
    if (controlBridgeServiceExpected) {
      const elapsed = Date.now() - controlBridgeServiceExpected.startedAt;
      if (elapsed > CONTROL_BRIDGE_SERVICE_TRANSITION_TIMEOUT_MS) {
        controlBridgeServiceExpected = null;
        showToast('제어 브리지 전환을 45초 안에 확인하지 못했습니다.', true);
      }
    } else {
      controlBridgeServiceSnapshot = null;
      if (force) showToast(controlBridgeServiceErrorText(error), true);
    }
  }
  renderControlBridgeService();
}

async function requestControlBridgeService(action) {
  if (controlBridgeServiceBusy || controlBridgeServiceExpected || !['start', 'stop'].includes(action)) return;
  if (controlBridgeServiceSnapshot?.[`can_${action}`] !== true) {
    showToast(`제어 브리지 ${action === 'start' ? '시작' : '중지'}가 현재 허용되지 않습니다.`, true);
    void refreshControlBridgeService(true);
    return;
  }
  if (!controlUi.bridgeServiceConfirm.checked) {
    showToast('제어 브리지 안전 확인 체크가 필요합니다.', true);
    return;
  }
  const warning = action === 'start'
    ? '고정된 제어 브리지 서비스를 시작합니다. 실제 로봇 제어 전 BRIDGE READY를 확인하고 별도로 ARM해야 합니다. 시작할까요?'
    : '제어 브리지 서비스를 중지하면 수동 제어와 Navigation 명령 경로가 끊깁니다. 중지할까요?';
  if (!window.confirm(warning)) return;

  controlBridgeServiceBusy = true;
  controlBridgeServiceRequestGeneration += 1;
  const mutationGeneration = ++controlBridgeServiceMutationGeneration;
  controlBridgeServiceExpected = {
    action,
    operationId: '',
    baselineOperationId: String(controlBridgeServiceSnapshot?.operation?.id || ''),
    invocationId: String(controlBridgeServiceSnapshot?.systemd?.invocation_id || ''),
    startedAt: Date.now(),
  };
  controlUi.bridgeServiceConfirm.checked = false;
  renderControlBridgeService();
  try {
    const snapshot = await api(`/api/v1/control/bridge-service/${action}`, {
      method: 'POST',
      body: JSON.stringify({ confirmed: true }),
    });
    if (mutationGeneration !== controlBridgeServiceMutationGeneration || controlBridgeServiceExpected?.action !== action) return;
    controlBridgeServiceSnapshot = snapshot;
    if (snapshot?.operation?.action === action) {
      controlBridgeServiceExpected.operationId = String(snapshot.operation.id || '');
    }
    showToast(`제어 브리지 ${action === 'start' ? '시작' : '중지'} 요청을 접수했습니다.`);
    completeExpectedControlBridgeServiceTransition(snapshot);
  } catch (error) {
    if (mutationGeneration !== controlBridgeServiceMutationGeneration) return;
    if (error?.status) controlBridgeServiceExpected = null;
    showToast(
      error?.status
        ? controlBridgeServiceErrorText(error)
        : '요청 결과를 확인할 수 없습니다. 제어 브리지 상태를 다시 확인합니다.',
      true,
    );
  } finally {
    if (mutationGeneration === controlBridgeServiceMutationGeneration) {
      controlBridgeServiceBusy = false;
      renderControlBridgeService();
      void refreshControlBridgeService(true);
    }
  }
}

export function initializeControlBridgeServiceFeature(options = {}) {
  if (initialized) return feature;
  initialized = true;
  showToast = options.showToast || showToast;
  getActivePage = options.getActivePage || getActivePage;
  refreshControl = options.refreshControl || refreshControl;
  refreshNavigationState = options.refreshNavigation || refreshNavigationState;
  controlUi.bridgeServiceConfirm?.addEventListener('change', renderControlBridgeService);
  controlUi.bridgeServiceStart?.addEventListener('click', () => requestControlBridgeService('start'));
  controlUi.bridgeServiceStop?.addEventListener('click', () => requestControlBridgeService('stop'));
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && (['controls', 'navigation'].includes(getActivePage()) || controlBridgeServiceExpected)) {
      controlBridgeServiceRequestGeneration += 1;
      void refreshControlBridgeService(true);
    }
  });
  window.addEventListener('pagehide', () => { controlBridgeServiceRequestGeneration += 1; });
  window.addEventListener('pageshow', () => {
    controlBridgeServiceRequestGeneration += 1;
    if (['controls', 'navigation'].includes(getActivePage()) || controlBridgeServiceExpected) void refreshControlBridgeService(true);
  });
  setInterval(refreshControlBridgeService, 1000);
  renderControlBridgeService();
  return feature;
}

const feature = Object.freeze({
  refresh: refreshControlBridgeService, render: renderControlBridgeService, request: requestControlBridgeService,
  invalidate: () => { controlBridgeServiceRequestGeneration += 1; },
  hasExpectedTransition: () => Boolean(controlBridgeServiceExpected),
});
