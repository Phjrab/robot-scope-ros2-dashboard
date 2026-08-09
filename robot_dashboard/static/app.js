const $ = (selector) => document.querySelector(selector);

const ui = {
  connectionChip: $('#connectionChip'),
  connectionLabel: $('#connectionLabel'),
  robotType: $('#robotType'),
  robotTypeNote: $('#robotTypeNote'),
  discoverRobotsButton: $('#discoverRobotsButton'),
  robotDiscoveryStatus: $('#robotDiscoveryStatus'),
  robotDiscoveryResults: $('#robotDiscoveryResults'),
  selectedRobotModel: $('#selectedRobotModel'),
  selectedRobotUrdf: $('#selectedRobotUrdf'),
  robotIp: $('#robotIp'),
  connectButton: $('#connectButton'),
  agentHost: $('#agentHost'),
  rosRuntime: $('#rosRuntime'),
  rosDomain: $('#rosDomain'),
  topicCount: $('#topicCount'),
  profileLabel: $('#profileLabel'),
  pageTitle: $('#pageTitle'),
  pageDescription: $('#pageDescription'),
  linkMetric: $('#linkMetric'),
  linkSub: $('#linkSub'),
  cameraMetric: $('#cameraMetric'),
  cameraSub: $('#cameraSub'),
  lidarMetric: $('#lidarMetric'),
  lidarSub: $('#lidarSub'),
  batteryMetric: $('#batteryMetric'),
  batterySub: $('#batterySub'),
  cameraSource: $('#cameraSource'),
  cloudSource: $('#cloudSource'),
  odomSource: $('#odomSource'),
  mapSource: $('#mapSource'),
  cameraCanvas: $('#cameraCanvas'),
  cameraEmpty: $('#cameraEmpty'),
  cameraEmptyText: $('#cameraEmptyText'),
  cameraState: $('#cameraState'),
  cameraTopicLabel: $('#cameraTopicLabel'),
  cameraCodecLabel: $('#cameraCodecLabel'),
  cameraMediaStatus: $('#cameraMediaStatus'),
  cameraMediaHelp: $('#cameraMediaHelp'),
  cameraRecordDuration: $('#cameraRecordDuration'),
  cameraCaptureFormat: $('#cameraCaptureFormat'),
  cameraCaptureButton: $('#cameraCaptureButton'),
  cameraRecordButton: $('#cameraRecordButton'),
  cameraStopRecordButton: $('#cameraStopRecordButton'),
  sceneCanvas: $('#sceneCanvas'),
  mapCanvas: $('#mapCanvas'),
  mapGridOverlay: $('#mapGridOverlay'),
  sceneControls: $('#sceneControls'),
  sceneResetButton: $('#sceneResetButton'),
  sceneTopButton: $('#sceneTopButton'),
  sceneFrontButton: $('#sceneFrontButton'),
  sceneFollowButton: $('#sceneFollowButton'),
  mapViewMode: $('#mapViewMode'),
  livePointBudget: $('#livePointBudget'),
  livePointCustomWrap: $('#livePointCustomWrap'),
  livePointCustom: $('#livePointCustom'),
  livePointApply: $('#livePointApply'),
  mapOverlayToggle: $('#mapOverlayToggle'),
  mappingState: $('#mappingState'),
  liveModelState: $('#liveModelState'),
  mapFrame: $('#mapFrame'),
  mapPoints: $('#mapPoints'),
  savedSceneCanvas: $('#savedSceneCanvas'),
  savedMapCanvas: $('#savedMapCanvas'),
  savedMapGridOverlay: $('#savedMapGridOverlay'),
  savedSceneControls: $('#savedSceneControls'),
  savedSceneResetButton: $('#savedSceneResetButton'),
  savedSceneTopButton: $('#savedSceneTopButton'),
  savedSceneFrontButton: $('#savedSceneFrontButton'),
  savedMapViewMode: $('#savedMapViewMode'),
  savedPointBudget: $('#savedPointBudget'),
  savedPointCustomWrap: $('#savedPointCustomWrap'),
  savedPointCustom: $('#savedPointCustom'),
  savedPointApply: $('#savedPointApply'),
  savedMapOverlayToggle: $('#savedMapOverlayToggle'),
  savedMappingState: $('#savedMappingState'),
  savedModelState: $('#savedModelState'),
  savedMapFrame: $('#savedMapFrame'),
  savedMapPoints: $('#savedMapPoints'),
  savedMapCount: $('#savedMapCount'),
  savedMapList: $('#savedMapList'),
  savedMapTitle: $('#savedMapTitle'),
  savedMapSource: $('#savedMapSource'),
  savedMapDetailFrame: $('#savedMapDetailFrame'),
  savedMapDetailPoints: $('#savedMapDetailPoints'),
  savedMapBounds: $('#savedMapBounds'),
  savedMapNameInput: $('#savedMapNameInput'),
  savedMapRenameButton: $('#savedMapRenameButton'),
  savedMapDeleteButton: $('#savedMapDeleteButton'),
  savedMapManageNote: $('#savedMapManageNote'),
  liveCloudTopic: $('#liveCloudTopic'),
  liveCloudStatus: $('#liveCloudStatus'),
  liveOdomTopic: $('#liveOdomTopic'),
  liveOdomStatus: $('#liveOdomStatus'),
  liveMapTopic: $('#liveMapTopic'),
  liveMapStatus: $('#liveMapStatus'),
  mappingControlState: $('#mappingControlState'),
  mappingSessionName: $('#mappingSessionName'),
  mappingCreate2d: $('#mappingCreate2d'),
  mappingStartButton: $('#mappingStartButton'),
  mappingSaveButton: $('#mappingSaveButton'),
  mappingStopButton: $('#mappingStopButton'),
  mappingPipelineLabel: $('#mappingPipelineLabel'),
  mappingDataLabel: $('#mappingDataLabel'),
  mappingSaveLabel: $('#mappingSaveLabel'),
  mappingOperationMessage: $('#mappingOperationMessage'),
  mappingLog: $('#mappingLog'),
  sensorGrid: $('#sensorGrid'),
  sensorCount: $('#sensorCount'),
  odomTopic: $('#odomTopic'),
  posX: $('#posX'), posY: $('#posY'), posZ: $('#posZ'), speed: $('#speed'),
  topicsBody: $('#topicsBody'),
  topicSearch: $('#topicSearch'),
  categoryFilter: $('#categoryFilter'),
  lastUpdated: $('#lastUpdated'),
  toast: $('#toast'),
};

const controlUi = {
  profileNotice: $('#controlProfileNotice'),
  profileNoticeText: $('#controlProfileNoticeText'),
  availability: $('#controlAvailability'),
  availabilityNote: $('#controlAvailabilityNote'),
  leaseState: $('#controlLeaseState'),
  leaseNote: $('#controlLeaseNote'),
  bridgeState: $('#controlBridgeState'),
  bridgeNote: $('#controlBridgeNote'),
  estopStatusCard: $('#estopStatusCard'),
  estopState: $('#controlEstopState'),
  estopNote: $('#controlEstopNote'),
  statePill: $('#controlStatePill'),
  inputSource: $('#controlInputSource'),
  gamepadWrap: $('#gamepadDeviceWrap'),
  gamepad: $('#gamepadDevice'),
  pin: $('#controlPin'),
  deviceIndicator: $('#controlDeviceIndicator'),
  deviceStatus: $('#controlDeviceStatus'),
  arm: $('#controlArmButton'),
  disarm: $('#controlDisarmButton'),
  speed: $('#controlSpeedScale'),
  speedOutput: $('#controlSpeedOutput'),
  keyboardGuide: $('#keyboardControlGuide'),
  gamepadGuide: $('#gamepadControlGuide'),
  touchController: $('#touchController'),
  commandX: $('#controlCommandX'),
  commandY: $('#controlCommandY'),
  commandZ: $('#controlCommandZ'),
  commandXBar: $('#controlCommandXBar'),
  commandYBar: $('#controlCommandYBar'),
  commandZBar: $('#controlCommandZBar'),
  deadmanState: $('#controlDeadmanState'),
  deadmanMonitor: $('.deadman-monitor'),
  commandSource: $('#controlCommandSource'),
  estop: $('#softwareEstopButton'),
  clearPin: $('#estopClearPin'),
  clearConfirm: $('#estopClearConfirm'),
  clear: $('#estopClearButton'),
  actions: $('#controlActions'),
};

let latestState = null;
let latestTopics = [];
let sourceFingerprint = '';
let cameraSocket = null;
let jointSocket = null;
let poseSocket = null;
let cameraMeta = null;
let cameraStatusMeta = null;
let videoDecoder = null;
let cameraHasKey = false;
let cameraFrames = 0;
let cameraFrameWindow = [];
let cameraLastFrameAt = 0;
let cameraActiveSourceKey = '';
let cameraRecording = null;
let cameraImageDecodeQueue = null;
let cloudSeq = -1;
let pointcloudRequestInFlight = false;
let pointcloudRequestGeneration = 0;
let mapSeq = -1;
let toastTimer = null;
let currentPose = null;
let targetPose = null;
let poseLive = false;
let lastPoseAt = 0;
let lastMotionFrameAt = 0;
let poseImuAnchor = null;
let lastPoseSignature = '';
let poseTrail = [];
let lastCloudSnapshot = null;
let liveCloudAccumulator = null;
let livePointLimit = 10000;
let savedPointLimit = null;
let livePointBudgetBusy = false;
let savedPointBudgetBusy = false;
let savedMapMutationBusy = false;
let offlineCloudSnapshot = null;
let lastMapSnapshot = null;
let savedOccupancySnapshot = null;
let savedMapCatalog = [];
let selectedSavedMapId = '';
let selectedSavedMapMeta = null;
const savedMapDataCache = new Map();
const savedMapLoadPromises = new Map();
let activePage = 'overview';
let activeMapView = null;
let mapViewPreference = 'cloud';
let savedMapViewPreference = 'cloud';
let mapOverlayVisible = true;
let savedMapOverlayVisible = true;
let sceneCloudDataKey = '';
let sceneCloudSourceKey = '';
let savedSceneCloudDataKey = '';
let savedSceneCloudSourceKey = '';
let liveSceneHadCloud = false;
let robotModelsReady = false;
let robotModelsFailed = false;
let robotModelLoadGeneration = 0;
let robotTypes = [];
let selectedRobotType = 'go2';
let selectedRobotCandidate = null;
let robotDiscoveryBusy = false;
let robotTypeDirty = false;
let robotIpDirty = false;
let robotDiscoveryGeneration = 0;
let robotDiscoveryController = null;
let robotConnectionBusy = false;
let robotRuntimeDataCompatible = true;
let jointLive = false;
let lastJointAt = 0;
let latestBodyRpy = null;
let targetJointPositions = null;
let renderedJointPositions = null;
let mappingControlSnapshot = null;
let mappingLogCursor = 0;
let mappingLogLines = [];
let handledMappingOperation = '';
const controlInput = window.RobotControlInput;
const CONTROL_SOCKET_MAX_BUFFER_BYTES = 4096;
let controlSnapshot = null;
let controlLeaseId = '';
let controlLeaseSource = '';
let controlSocket = null;
let controlSocketBound = false;
const intentionallyClosedControlSockets = new WeakSet();
let controlSequence = 0;
let lastControlHeartbeatAt = 0;
let controlDisarmBusy = false;
let controlEmergencyBusy = false;
let controlArmBusy = false;
let controlArmGeneration = 0;
let controlActionBusy = false;
let controlActionAckTimer = null;
let pendingControlActionId = '';
let controlSpeedInitialized = false;
let controlHadDeadman = false;
let controlLastCommand = null;
let selectedGamepadIndex = '';
let gamepadEstopPressed = false;
let actionConfirmation = null;
const controlPressedKeys = new Set();
const controlPointerDirections = new Map();
const controlDeadmanPointers = new Set();

const scene3d = window.RobotScene3D && ui.sceneCanvas
  ? new window.RobotScene3D(ui.sceneCanvas, {
      maxPoints: 10000,
      maxCloudRadius: 150,
      pointSize: 0.05,
      autoFitOnFirstCloud: true,
    })
  : null;

if (scene3d) {
  scene3d.bindControls({
    reset: ui.sceneResetButton,
    top: ui.sceneTopButton,
    front: ui.sceneFrontButton,
    follow: ui.sceneFollowButton,
  });
  scene3d.setStatus({ online: false, lidarOnline: false, snapshot: false, message: '실시간 LiDAR 신호를 기다리고 있습니다' });
}

const savedScene3d = window.RobotScene3D && ui.savedSceneCanvas
  ? new window.RobotScene3D(ui.savedSceneCanvas, {
      maxPoints: null,
      maxCloudRadius: 1000000,
      pointSize: 0.05,
      autoFitOnFirstCloud: true,
    })
  : null;

if (savedScene3d) {
  savedScene3d.bindControls({
    reset: ui.savedSceneResetButton,
    top: ui.savedSceneTopButton,
    front: ui.savedSceneFrontButton,
  });
  savedScene3d.setStatus({ online: null, lidarOnline: null, snapshot: true, message: '저장 지도를 불러오는 중입니다' });
}

function activeRobotProfile() {
  const profiles = robotTypes.length ? robotTypes : (window.RobotProfiles?.normalizeTypes?.([]) || []);
  return profiles.find((profile) => profile.id === selectedRobotType) || profiles[0] || null;
}

function modelBadgeLabel(profile = activeRobotProfile()) {
  return String(profile?.model?.label || profile?.label || 'ROBOT MODEL').trim().toUpperCase();
}

function modelFidelityNote(profile = activeRobotProfile()) {
  const fidelity = String(profile?.model?.fidelity || '').toLowerCase();
  if (fidelity.includes('generic') || fidelity.includes('approx')) return '범용 URDF 근사 모델 · 제조사 공식 모델 아님';
  if (fidelity.includes('official')) return '공식 URDF 기반 모델';
  return fidelity ? fidelity.replace(/[-_]/g, ' ') : 'URDF 기반 3D 모델';
}

function updateControlProfileUx(profile = activeRobotProfile()) {
  const go2 = profile?.id === 'go2';
  if (controlUi.profileNotice) controlUi.profileNotice.hidden = go2;
  if (controlUi.profileNoticeText && !go2) {
    controlUi.profileNoticeText.textContent = `${profile?.label || '이 로봇'}은 현재 상태 확인·센서·3D 모델만 지원하며, 주행과 모션 명령은 Go2에서만 사용할 수 있습니다.`;
  }
  renderControlStatus();
}

function updateLiveModelBadge() {
  const label = modelBadgeLabel();
  ui.liveModelState.classList.toggle('ready', robotModelsReady);
  ui.liveModelState.classList.toggle('fallback', robotModelsFailed);
  if (!robotRuntimeDataCompatible) ui.liveModelState.textContent = `${label} · RESTART REQUIRED`;
  else if (robotModelsFailed) ui.liveModelState.textContent = `${label} · FALLBACK`;
  else if (!robotModelsReady) ui.liveModelState.textContent = `${label} · LOADING`;
  else if (jointLive) ui.liveModelState.textContent = `${label} · JOINTS LIVE`;
  else ui.liveModelState.textContent = `${label} · READY`;
}

async function applyRobotModel(profile = activeRobotProfile()) {
  if (!profile) return;
  const generation = ++robotModelLoadGeneration;
  const assetUrl = String(profile.model?.asset_url || '').trim();
  const renderers = [scene3d, savedScene3d].filter(Boolean);
  robotModelsReady = false;
  robotModelsFailed = false;
  renderers.forEach((renderer, index) => {
    renderer._robotModelLabel = profile.label;
    renderer._robotModelType = profile.id;
    renderer.resetRobotJointPositions?.();
    renderer.configureOfficialRobot?.({
      enabled: Boolean(assetUrl),
      assetUrl,
      poseOrigin: index === 0 ? 'base' : 'ground',
      adaptiveScale: index !== 0,
      scale: 1,
    });
  });
  if (ui.selectedRobotModel) ui.selectedRobotModel.textContent = `${profile.model?.label || profile.label} · ${modelFidelityNote(profile)}`;
  if (ui.selectedRobotUrdf) {
    const urdfUrl = String(profile.model?.urdf_url || '').trim();
    ui.selectedRobotUrdf.hidden = !urdfUrl;
    if (urdfUrl) ui.selectedRobotUrdf.href = urdfUrl;
    else ui.selectedRobotUrdf.removeAttribute('href');
  }
  ui.savedModelState.textContent = `${modelBadgeLabel(profile)} · LOADING`;
  ui.savedModelState.classList.remove('ready', 'fallback');
  updateLiveModelBadge();
  try {
    if (!assetUrl || renderers.length !== 2 || renderers.some((renderer) => typeof renderer.loadOfficialRobotModel !== 'function')) {
      throw new Error('robot model renderer or asset is unavailable');
    }
    await Promise.all(renderers.map((renderer) => renderer.loadOfficialRobotModel(assetUrl)));
    if (generation !== robotModelLoadGeneration) return;
    robotModelsReady = true;
    ui.savedModelState.textContent = modelBadgeLabel(profile);
    ui.savedModelState.classList.add('ready');
    updateLiveModelBadge();
  } catch (error) {
    if (generation !== robotModelLoadGeneration) return;
    console.warn(`${profile.label} model fallback:`, error);
    robotModelsFailed = true;
    ui.savedModelState.textContent = `${modelBadgeLabel(profile)} · FALLBACK`;
    ui.savedModelState.classList.add('fallback');
    updateLiveModelBadge();
  }
}

function renderRobotTypeOptions() {
  const fragment = document.createDocumentFragment();
  robotTypes.forEach((profile) => {
    const option = document.createElement('option');
    option.value = profile.id;
    option.textContent = profile.label;
    fragment.appendChild(option);
  });
  ui.robotType.replaceChildren(fragment);
  if (robotTypes.some((profile) => profile.id === selectedRobotType)) ui.robotType.value = selectedRobotType;
}

function clearRobotDiscovery(message = '네트워크 검색을 시작하면 연결 후보가 여기에 표시됩니다.') {
  selectedRobotCandidate = null;
  const empty = document.createElement('div');
  empty.className = 'robot-discovery-empty';
  empty.textContent = message;
  ui.robotDiscoveryResults.replaceChildren(empty);
}

function setDiscoveryStatus(message, error = false) {
  ui.robotDiscoveryStatus.textContent = message;
  ui.robotDiscoveryStatus.classList.toggle('error', error);
}

function cancelRobotDiscovery() {
  robotDiscoveryGeneration += 1;
  robotDiscoveryController?.abort();
  robotDiscoveryController = null;
  robotDiscoveryBusy = false;
  ui.discoverRobotsButton.disabled = false;
  ui.discoverRobotsButton.textContent = '네트워크 검색';
}

function selectRobotCandidate(candidate) {
  selectedRobotCandidate = candidate;
  robotIpDirty = true;
  ui.robotIp.value = candidate.ip;
  ui.robotDiscoveryResults.querySelectorAll('.robot-candidate').forEach((button) => {
    const selected = button.dataset.robotIp === candidate.ip;
    button.classList.toggle('is-selected', selected);
    button.setAttribute('aria-pressed', selected ? 'true' : 'false');
  });
}

function renderRobotCandidates(candidates) {
  if (!candidates.length) {
    clearRobotDiscovery('선택한 유형의 로봇을 찾지 못했습니다. 연결과 전원을 확인하거나 IP를 직접 입력하세요.');
    return;
  }
  const fragment = document.createDocumentFragment();
  candidates.forEach((candidate) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'robot-candidate';
    button.dataset.robotIp = candidate.ip;
    button.setAttribute('aria-pressed', 'false');
    const identity = document.createElement('span');
    const ip = document.createElement('strong');
    ip.textContent = candidate.ip;
    const host = document.createElement('small');
    const details = [candidate.hostname, candidate.interface, candidate.reason].filter(Boolean);
    host.textContent = details.join(' · ');
    identity.append(ip, host);
    const metric = document.createElement('em');
    const confidenceLabel = candidate.confidence == null
      ? '유형 미확인'
      : candidate.confidence >= 0.8
        ? '유형 일치'
        : candidate.confidence >= 0.4
          ? '네트워크 후보'
          : '미확인 호스트';
    const latencyLabel = candidate.latency_ms == null ? '응답 확인' : `${candidate.latency_ms.toFixed(1)} ms`;
    metric.textContent = `${confidenceLabel} · ${latencyLabel}`;
    button.title = details.join(' · ');
    button.append(identity, metric);
    button.addEventListener('click', () => selectRobotCandidate(candidate));
    fragment.appendChild(button);
  });
  ui.robotDiscoveryResults.replaceChildren(fragment);
}

async function discoverRobots() {
  const generation = ++robotDiscoveryGeneration;
  robotDiscoveryController?.abort();
  const controller = new AbortController();
  robotDiscoveryController = controller;
  robotDiscoveryBusy = true;
  selectedRobotCandidate = null;
  ui.discoverRobotsButton.disabled = true;
  ui.discoverRobotsButton.textContent = '검색 중…';
  setDiscoveryStatus('검색 중');
  clearRobotDiscovery('Jetson에 연결된 네트워크 인터페이스를 검색하고 있습니다…');
  try {
    const payload = await api('/api/v1/robots/discover', {
      method: 'POST',
      signal: controller.signal,
      body: JSON.stringify({ robot_type: selectedRobotType }),
    });
    if (generation !== robotDiscoveryGeneration) return;
    const candidates = window.RobotProfiles.normalizeDiscovery(payload);
    renderRobotCandidates(candidates);
    setDiscoveryStatus(candidates.length ? `${candidates.length}개 발견` : '후보 없음');
  } catch (error) {
    if (generation !== robotDiscoveryGeneration) return;
    if (error.name === 'AbortError') return;
    clearRobotDiscovery('자동 검색에 실패했습니다. IP를 직접 입력해 연결할 수 있습니다.');
    setDiscoveryStatus(`검색 실패 · ${error.message}`, true);
  } finally {
    if (generation === robotDiscoveryGeneration) {
      robotDiscoveryBusy = false;
      robotDiscoveryController = null;
      ui.discoverRobotsButton.disabled = false;
      ui.discoverRobotsButton.textContent = '다시 검색';
    }
  }
}

function activateRobotType(typeId, { discover = false, dirty = false } = {}) {
  const profile = robotTypes.find((candidate) => candidate.id === typeId) || robotTypes[0];
  if (!profile) return;
  const typeChanged = selectedRobotType !== profile.id;
  if (typeChanged) {
    cancelRobotDiscovery();
    robotRuntimeDataCompatible = false;
    resetLiveRobotSessionView();
  }
  selectedRobotType = profile.id;
  robotTypeDirty = dirty;
  markJointsStale(true);
  ui.robotType.value = profile.id;
  ui.robotTypeNote.textContent = `${profile.description || `${profile.label} 네트워크 설정을 사용합니다.`} · ${modelFidelityNote(profile)}`;
  clearRobotDiscovery();
  setDiscoveryStatus('검색 대기');
  applyRobotModel(profile);
  updateControlProfileUx(profile);
  if (discover) discoverRobots();
}

async function initializeRobotProfiles() {
  const profiles = window.RobotProfiles;
  if (!profiles) {
    showToast('로봇 유형 모듈을 불러오지 못했습니다.', true);
    return;
  }
  let payload = null;
  try {
    payload = await api('/api/v1/robots/types');
  } catch (error) {
    console.warn('Robot type catalog fallback:', error);
  }
  robotTypes = profiles.normalizeTypes(payload);
  selectedRobotType = profiles.robotTypeId(payload?.selected_type) || selectedRobotType;
  if (!robotTypes.some((profile) => profile.id === selectedRobotType)) selectedRobotType = robotTypes[0]?.id || 'go2';
  renderRobotTypeOptions();
  activateRobotType(selectedRobotType);
}

const PAGE_META = {
  overview: ['Overview', '로봇과 ROS 2 시스템의 전체 상태를 빠르게 확인합니다.'],
  mapping: ['Live LiDAR Mapping', '실시간 점군, 로봇 자세와 매핑 파이프라인을 확인합니다.'],
  maps: ['Saved Maps', '이미 매핑된 3D PCD와 2D 점유 지도를 센서 없이 탐색합니다.'],
  sensors: ['Sensors & Camera', '카메라 스트림과 로봇 센서 값을 기능별로 확인합니다.'],
  topics: ['ROS Graph', '발견된 ROS 2 토픽, 타입, 수신률과 지연을 조회합니다.'],
  controls: ['Robot Controls', 'PIN으로 제어 권한을 얻은 뒤 키보드·게임패드 주행과 허용된 Go2 동작을 실행합니다.'],
  settings: ['Settings', '로봇 유형을 고르고 네트워크에서 연결 대상을 찾은 뒤 ROS 2 데이터 소스를 선택합니다.'],
};

function pageFromHash() {
  const route = location.hash.replace(/^#\/?/, '').trim();
  return Object.hasOwn(PAGE_META, route) ? route : 'overview';
}

function activatePage(page, updateHash = false) {
  const previousPage = activePage;
  activePage = Object.hasOwn(PAGE_META, page) ? page : 'overview';
  document.querySelectorAll('[data-page]').forEach((element) => {
    const active = element.dataset.page === activePage;
    element.hidden = !active;
    element.classList.toggle('is-active', active);
  });
  document.querySelectorAll('[data-nav]').forEach((element) => {
    const active = element.dataset.nav === activePage;
    element.classList.toggle('is-active', active);
    if (active) element.setAttribute('aria-current', 'page'); else element.removeAttribute('aria-current');
  });
  const [title, description] = PAGE_META[activePage];
  ui.pageTitle.textContent = title;
  ui.pageDescription.textContent = description;
  if (updateHash && location.hash !== `#${activePage}`) history.replaceState(null, '', `#${activePage}`);
  if (previousPage === 'controls' && activePage !== 'controls') leaveControlPage('controls_page_left');
  if (activePage === 'controls' && previousPage !== 'controls') enterControlPage();
  if (previousPage === 'sensors' && activePage !== 'sensors' && cameraRecording) {
    stopCameraRecording(cameraRecordingCleanupPolicy('sensors_page_left'));
  }
  requestAnimationFrame(() => {
    if (activePage === 'mapping') {
      scene3d?.resize();
      redrawActiveMap();
    } else if (activePage === 'maps') {
      savedScene3d?.resize();
      redrawSavedMap();
    }
  });
}

function showToast(message, error = false) {
  ui.toast.textContent = message;
  ui.toast.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { ui.toast.className = 'toast'; }, 2800);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    cache: 'no-store',
  });
  if (!response.ok) {
    let detail = `${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return response.json();
}

async function latestApi(path, seq) {
  const response = await fetch(`${path}?since=${encodeURIComponent(seq)}`, { cache: 'no-store' });
  if (response.status === 204) return null;
  if (!response.ok) throw new Error(String(response.status));
  return response.json();
}

function setStatePill(element, state, label) {
  element.className = `panel-state ${state === 'ok' || state === 'mapping' || state === 'cloud_only' || state === 'grid_live' || state === 'saved' ? 'ok' : state === 'stale' || state === 'error' ? 'error' : 'waiting'}`;
  element.innerHTML = `<span></span>${label || state.toUpperCase()}`;
}

function formatHz(value) {
  return value == null ? '—' : `${Number(value).toFixed(value >= 10 ? 1 : 2)} Hz`;
}

function safeNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : '—';
}

function updateHealth(health) {
  const ready = Boolean(health.agent_ready);
  const online = Boolean(health.robot_online);
  const rosTransport = health.ros_transport || {};
  const rosInterfaceReady = rosTransport.interface_ready ?? health.ros_interface_ready;
  const offlineViewer = Boolean(rosTransport.offline_viewer ?? health.ros_offline_viewer);
  ui.connectionChip.className = `connection-chip ${ready && rosInterfaceReady === true && online ? 'ok' : ready ? 'waiting' : 'error'}`;
  ui.connectionLabel.textContent = !ready
    ? '에이전트 오류'
    : offlineViewer || rosInterfaceReady === false
      ? 'ROS/DDS 오프라인 뷰어'
      : rosInterfaceReady === true
        ? 'ROS/DDS 인터페이스 준비'
        : 'ROS 에이전트 연결됨';
  ui.agentHost.textContent = health.hostname || '—';
  const rosInterface = rosTransport.interface ? ` · ${rosTransport.interface}` : '';
  ui.rosRuntime.textContent = `${health.ros_distro || '—'} · ${health.rmw || 'default'}${rosInterface}`;
  ui.rosDomain.textContent = health.ros_domain_id ?? '0';
  ui.topicCount.textContent = health.topic_count ?? '—';
  ui.profileLabel.textContent = (health.profile || 'GENERIC ROS 2').toUpperCase();
  const healthRobotType = window.RobotProfiles?.robotTypeId?.(health.robot_type || health.profile_id);
  const runtimeCompatible = !robotTypeDirty
    && !Boolean(health.restart_required || health.control_restart_required)
    && (!healthRobotType || healthRobotType === selectedRobotType);
  if (robotRuntimeDataCompatible && !runtimeCompatible) resetLiveRobotSessionView();
  robotRuntimeDataCompatible = runtimeCompatible;
  updateLiveModelBadge();
  if (!robotTypeDirty && healthRobotType && healthRobotType !== selectedRobotType && robotTypes.some((profile) => profile.id === healthRobotType)) {
    activateRobotType(healthRobotType);
  }
  if (!robotIpDirty && document.activeElement !== ui.robotIp && health.robot_ip) ui.robotIp.value = health.robot_ip;
  ui.linkMetric.textContent = online ? (health.robot_latency_ms != null ? `${health.robot_latency_ms} ms` : 'ONLINE') : 'OFFLINE';
  ui.linkSub.textContent = health.robot_ip || 'IP not configured';
  if (health.last_error) console.warn('Robot Scope:', health.last_error);
}

function isLiveCloudReady() {
  const cloudState = latestState?.mapping?.cloud?.state;
  const mappingState = latestState?.mapping?.state;
  return cloudState === 'ok' || mappingState === 'mapping' || mappingState === 'cloud_only';
}

function liveSceneCloud(candidate = lastCloudSnapshot) {
  return candidate?.points?.length && isLiveCloudReady() ? candidate : null;
}

function savedSceneCloud() {
  return offlineCloudSnapshot?.points?.length ? offlineCloudSnapshot : null;
}

function cloudPointCount(cloud) {
  return Number(cloud?.sent_points || (cloud?.points?.length ? Math.floor(cloud.points.length / 3) : 0));
}

function cloudPointSummary(cloud) {
  const shown = cloudPointCount(cloud);
  const source = Math.max(shown, Number(cloud?.source_points || shown));
  return shown < source
    ? `${shown.toLocaleString()} / ${source.toLocaleString()}`
    : shown.toLocaleString();
}

function normalizePointLimit(value) {
  if (value == null || value === 'all') return null;
  const number = Math.floor(Number(value));
  if (!Number.isFinite(number) || number < 1000 || number > 1000000) {
    throw new Error('포인트 수는 1,000~1,000,000 사이여야 합니다.');
  }
  return number;
}

function pointBudgetCacheKey(mapId, limit = savedPointLimit, kind = 'pointcloud3d') {
  if (kind === 'occupancy2d') return `${mapId}:grid`;
  return `${mapId}:${limit == null ? 'all' : limit}`;
}

function savedPointDataUrl(meta) {
  const base = meta.data_url || `/api/v1/saved-maps/${encodeURIComponent(meta.id)}/data`;
  const separator = base.includes('?') ? '&' : '?';
  return `${base}${separator}max_points=${savedPointLimit == null ? 'all' : encodeURIComponent(savedPointLimit)}`;
}

function storedPointLimit(key) {
  try {
    const value = localStorage.getItem(key);
    if (value == null) return undefined;
    return normalizePointLimit(value);
  } catch (_) {
    return undefined;
  }
}

function rememberPointLimit(key, value) {
  try { localStorage.setItem(key, value == null ? 'all' : String(value)); } catch (_) {}
}

function syncPointBudgetControl(select, wrapper, input, value) {
  const option = value == null ? 'all' : String(value);
  const known = Array.from(select.options).some((item) => item.value === option);
  select.value = known ? option : 'custom';
  wrapper.classList.toggle('is-hidden', select.value !== 'custom');
  if (value != null) input.value = String(value);
}

function updateSavedPointBudgetAvailability() {
  const disabled = savedPointBudgetBusy || selectedSavedMapMeta?.kind !== 'pointcloud3d';
  ui.savedPointBudget.disabled = disabled;
  ui.savedPointCustom.disabled = disabled;
  ui.savedPointApply.disabled = disabled;
  ui.savedPointCustomWrap.classList.toggle(
    'is-hidden',
    disabled || ui.savedPointBudget.value !== 'custom',
  );
}

async function applyLivePointLimit(value, notify = true) {
  if (livePointBudgetBusy) return;
  let limit;
  try {
    limit = normalizePointLimit(value);
  } catch (error) {
    syncPointBudgetControl(ui.livePointBudget, ui.livePointCustomWrap, ui.livePointCustom, livePointLimit);
    if (notify) showToast(`포인트 설정 실패: ${error.message}`, true);
    return;
  }
  livePointBudgetBusy = true;
  ui.livePointBudget.disabled = ui.livePointCustom.disabled = ui.livePointApply.disabled = true;
  try {
    const settings = await api('/api/v1/pointcloud/settings', {
      method: 'POST',
      body: JSON.stringify({ max_points: limit }),
    });
    livePointLimit = settings.all_points ? null : Number(settings.max_points);
    rememberPointLimit('robotScope.livePointLimit', livePointLimit);
    syncPointBudgetControl(ui.livePointBudget, ui.livePointCustomWrap, ui.livePointCustom, livePointLimit);
    scene3d?.setPointLimit?.(livePointLimit);
    resetLiveCloudAccumulator();
    lastCloudSnapshot = null;
    pointcloudRequestGeneration += 1;
    cloudSeq = -1;
    sceneCloudDataKey = '';
    sceneCloudSourceKey = '';
    await refreshPointcloud();
    if (notify) showToast(livePointLimit == null ? '실시간 점군을 ALL SESSION으로 표시합니다.' : `실시간 점군 표시량을 ${livePointLimit.toLocaleString()}점으로 설정했습니다.`);
  } catch (error) {
    syncPointBudgetControl(ui.livePointBudget, ui.livePointCustomWrap, ui.livePointCustom, livePointLimit);
    if (notify) showToast(`포인트 설정 실패: ${error.message}`, true);
  } finally {
    livePointBudgetBusy = false;
    ui.livePointBudget.disabled = ui.livePointCustom.disabled = ui.livePointApply.disabled = false;
  }
}

async function applySavedPointLimit(value, notify = true) {
  if (savedPointBudgetBusy) return;
  let limit;
  try {
    limit = normalizePointLimit(value);
  } catch (error) {
    syncPointBudgetControl(ui.savedPointBudget, ui.savedPointCustomWrap, ui.savedPointCustom, savedPointLimit);
    if (notify) showToast(`포인트 설정 실패: ${error.message}`, true);
    return;
  }
  const previousLimit = savedPointLimit;
  savedPointBudgetBusy = true;
  ui.savedPointBudget.disabled = ui.savedPointCustom.disabled = ui.savedPointApply.disabled = true;
  try {
    savedPointLimit = limit;
    syncPointBudgetControl(ui.savedPointBudget, ui.savedPointCustomWrap, ui.savedPointCustom, savedPointLimit);
    savedScene3d?.setPointLimit?.(savedPointLimit);
    savedSceneCloudDataKey = '';
    savedSceneCloudSourceKey = '';
    if (selectedSavedMapMeta?.kind === 'pointcloud3d' && selectedSavedMapId !== '__fallback_cloud') {
      clearSavedMapCache(selectedSavedMapId);
      offlineCloudSnapshot = null;
      const loaded = await selectSavedMap(selectedSavedMapId, false, true);
      if (!loaded) throw new Error('선택한 포인트 수로 지도를 불러오지 못했습니다.');
    } else {
      redrawSavedMap();
    }
    rememberPointLimit('robotScope.savedPointLimit', savedPointLimit);
    if (notify) showToast(savedPointLimit == null ? '저장 지도의 모든 포인트를 표시합니다.' : `저장 지도 표시량을 ${savedPointLimit.toLocaleString()}점으로 설정했습니다.`);
  } catch (error) {
    savedPointLimit = previousLimit;
    savedScene3d?.setPointLimit?.(savedPointLimit);
    syncPointBudgetControl(ui.savedPointBudget, ui.savedPointCustomWrap, ui.savedPointCustom, savedPointLimit);
    if (selectedSavedMapMeta?.kind === 'pointcloud3d' && selectedSavedMapId !== '__fallback_cloud') {
      await selectSavedMap(selectedSavedMapId, false);
    }
    if (notify) showToast(`포인트 설정 실패: ${error.message}`, true);
  } finally {
    savedPointBudgetBusy = false;
    updateSavedPointBudgetAvailability();
  }
}

async function initializePointBudgets() {
  const savedStored = storedPointLimit('robotScope.savedPointLimit');
  savedPointLimit = savedStored === undefined ? null : savedStored;
  syncPointBudgetControl(ui.savedPointBudget, ui.savedPointCustomWrap, ui.savedPointCustom, savedPointLimit);
  savedScene3d?.setPointLimit?.(savedPointLimit);
  try {
    const settings = await api('/api/v1/pointcloud/settings');
    const stored = storedPointLimit('robotScope.livePointLimit');
    if (stored !== undefined && stored !== settings.max_points) {
      await applyLivePointLimit(stored, false);
      return;
    }
    livePointLimit = settings.all_points ? null : Number(settings.max_points);
  } catch (_) {}
  syncPointBudgetControl(ui.livePointBudget, ui.livePointCustomWrap, ui.livePointCustom, livePointLimit);
  scene3d?.setPointLimit?.(livePointLimit);
}

function resetLiveCloudAccumulator() {
  liveCloudAccumulator = null;
}

function resetLiveRobotSessionView() {
  resetLiveCloudAccumulator();
  lastCloudSnapshot = null;
  pointcloudRequestGeneration += 1;
  cloudSeq = -1;
  poseTrail = [];
  sceneCloudDataKey = '';
  sceneCloudSourceKey = '';
  liveSceneHadCloud = false;
  clearLivePose();
  scene3d?.clearPointCloud();
  scene3d?.clearTrail();
  scene3d?.setRobotPose(null);
}

function accumulateRegisteredCloud(cloud) {
  if (cloud?.topic !== '/cloud_registered' || !cloud?.points?.length) {
    resetLiveCloudAccumulator();
    return cloud;
  }
  const key = `${cloud.topic}:${cloud.frame_id || ''}`;
  if (liveCloudAccumulator?.key === key && liveCloudAccumulator.lastSeq === cloud.seq) {
    return liveCloudAccumulator.payload;
  }
  let accumulator = liveCloudAccumulator?.key === key ? liveCloudAccumulator : null;
  const incoming = cloud.points;
  const required = (accumulator?.length || 0) + incoming.length;
  if (!accumulator) {
    const initial = Math.max(required, Math.min((livePointLimit || Math.floor(required / 3)) * 3, 262144));
    accumulator = {
      key,
      buffer: new Float32Array(Math.max(initial, 3)),
      length: 0,
      totalObservedPoints: 0,
      bounds: null,
    };
  } else if (required > accumulator.buffer.length) {
    let capacity = Math.max(accumulator.buffer.length, 3);
    while (capacity < required) capacity *= 2;
    const grown = new Float32Array(capacity);
    grown.set(accumulator.buffer.subarray(0, accumulator.length));
    accumulator.buffer = grown;
  }
  accumulator.buffer.set(incoming, accumulator.length);
  accumulator.length += incoming.length;
  accumulator.totalObservedPoints += Number(cloud.source_points ?? cloudPointCount(cloud));

  let available = Math.floor(accumulator.length / 3);
  if (livePointLimit != null && available > livePointLimit) {
    const sampled = new Float32Array(livePointLimit * 3);
    const stride = available / livePointLimit;
    for (let index = 0; index < livePointLimit; index += 1) {
      const source = Math.min(available - 1, Math.floor(index * stride)) * 3;
      sampled[index * 3] = accumulator.buffer[source];
      sampled[index * 3 + 1] = accumulator.buffer[source + 1];
      sampled[index * 3 + 2] = accumulator.buffer[source + 2];
    }
    accumulator.buffer = sampled;
    accumulator.length = sampled.length;
    available = livePointLimit;
  }
  const points = accumulator.buffer.subarray(0, accumulator.length);
  const oldBounds = accumulator.bounds;
  const bounds = oldBounds?.min && cloud.bounds?.min ? {
    min: oldBounds.min.map((value, index) => Math.min(Number(value), Number(cloud.bounds.min[index]))),
    max: oldBounds.max.map((value, index) => Math.max(Number(value), Number(cloud.bounds.max[index]))),
  } : cloud.bounds;
  accumulator.bounds = bounds;
  const payload = {
    ...cloud,
    points,
    bounds,
    sent_points: available,
    source_points: Math.max(available, accumulator.totalObservedPoints),
    frame_source_points: Number(cloud.source_points || cloudPointCount(cloud)),
    accumulated_registered_scans: true,
  };
  accumulator.lastSeq = cloud.seq;
  accumulator.payload = payload;
  liveCloudAccumulator = accumulator;
  return payload;
}

function buildDemoPointcloud() {
  const points = [];
  const add = (x, y, z) => points.push(Number(x.toFixed(3)), Number(y.toFixed(3)), Number(z.toFixed(3)));
  for (let x = -6; x <= 6; x += .28) {
    for (let y = -4; y <= 4; y += .28) {
      if ((Math.round((x + y) * 100) % 5) === 0) add(x, y, 0);
    }
  }
  for (let z = 0; z <= 2.5; z += .16) {
    for (let x = -6; x <= 6; x += .22) {
      add(x, -4, z);
      if (x < -1.2 || x > 1.2 || z > 2.1) add(x, 4, z);
    }
    for (let y = -4; y <= 4; y += .22) {
      add(-6, y, z);
      add(6, y, z);
    }
  }
  for (let angle = 0; angle < Math.PI * 2; angle += .08) {
    for (let z = 0; z <= 1.1; z += .12) add(2.2 + Math.cos(angle) * .7, -.8 + Math.sin(angle) * .7, z);
  }
  return {
    seq: 'demo-1', topic: '/demo/pointcloud', frame_id: 'map', units: 'm',
    source_points: Math.floor(points.length / 3), sent_points: Math.floor(points.length / 3),
    bounds: { min: [-6, -4, 0], max: [6, 4, 2.5] },
    offline_snapshot: true, demo_snapshot: true, points,
  };
}

function updateOverview(state) {
  updateHealth(state.health);
  applyJointSnapshot(state.robot_joints);
  const camera = state.camera || {};
  const cloud = state.cloud || {};
  const grid = state.map || {};
  const mapping = state.mapping || {};
  const cameraSource = state.sources?.camera || '';
  const cloudSource = state.sources?.pointcloud || '';
  const odomSource = state.sources?.odometry || '';
  const gridSource = state.sources?.occupancy_grid || '';

  const directCamera = camera.direct_camera || {};
  const cameraTopicName = camera.topic || cameraSource;
  const cameraTopic = latestTopics.find((topic) => topic.name === cameraTopicName);
  const cameraSourceKey = cameraTopicName || camera.source || directCamera.uri || '';
  if (cameraSourceKey) noteCameraSource(cameraSourceKey);
  // /api/v1/state is also the liveness clock for the direct Go2 multicast
  // camera.  Merge it into the latest WS frame metadata so a frozen canvas
  // becomes stale even when no more WebSocket messages arrive.
  cameraStatusMeta = { ...camera };
  const cameraLabel = camera.source_label || camera.topic || cameraSource || 'NO SOURCE';
  const cameraTransport = camera.transport || directCamera.transport || '';
  const cameraInterface = camera.interface || directCamera.interface || '';
  const cameraFps = camera.fps ?? directCamera.fps ?? cameraTopic?.hz;
  const cameraAge = camera.age_s ?? directCamera.age_s ?? cameraTopic?.age_s;
  const reportedCameraState = camera.state || directCamera.state || cameraTopic?.state || 'waiting';
  const reportedCameraLive = camera.live ?? directCamera.live ?? (reportedCameraState === 'ok');
  const cameraLive = Boolean(reportedCameraLive) && (cameraAge == null || Number(cameraAge) <= 3);
  ui.cameraMetric.textContent = formatHz(cameraFps);
  ui.cameraSub.textContent = [cameraLabel, cameraTransport, cameraInterface].filter(Boolean).join(' · ') || 'No camera source';
  ui.cameraSub.title = ui.cameraSub.textContent;
  ui.cameraTopicLabel.textContent = cameraLabel;
  ui.cameraTopicLabel.title = camera.topic || cameraSource || cameraLabel;
  const cameraWidth = camera.width || directCamera.width || '';
  const cameraHeight = camera.height || directCamera.height || '';
  const cameraFormat = camera.format && camera.format !== 'none' ? camera.format.toUpperCase() : '';
  const cameraDimensions = cameraWidth && cameraHeight ? `${cameraWidth}×${cameraHeight}` : '';
  ui.cameraCodecLabel.textContent = [cameraFormat, cameraDimensions, cameraTransport].filter(Boolean).join(' · ') || '—';
  setStatePill(ui.cameraState, cameraLive ? 'ok' : reportedCameraState, cameraLive ? 'LIVE' : String(reportedCameraState).toUpperCase());
  syncCameraFrameFreshness();

  const hesaiTopic = latestTopics.find((topic) => topic.name === '/lidar_points');
  const hesaiOnline = Number(hesaiTopic?.publishers || 0) > 0;
  const cloudMetric = mapping.cloud || {};
  const liveCloud = liveSceneCloud();
  const cloudTopic = latestTopics.find((topic) => topic.name === cloudSource);
  const odomTopic = latestTopics.find((topic) => topic.name === odomSource);
  const gridTopic = latestTopics.find((topic) => topic.name === gridSource);
  const cloudFrame = cloud.frame_id || liveCloud?.frame_id || '';
  const poseFrame = state.robot_pose?.frame_id || '';
  const frameMismatch = Boolean(cloudFrame && poseFrame && cloudFrame !== poseFrame);

  ui.lidarMetric.textContent = liveCloud ? formatHz(cloudMetric.hz ?? cloudTopic?.hz) : 'OFFLINE';
  ui.lidarSub.textContent = `${hesaiOnline ? 'XT16 ONLINE · ' : ''}${cloudSource || 'No live cloud topic'}`;
  ui.liveCloudTopic.textContent = cloudSource || 'NO SOURCE';
  ui.liveCloudStatus.textContent = liveCloud ? `live · ${formatHz(cloudMetric.hz ?? cloudTopic?.hz)} · ${cloudFrame || 'no frame'}` : (cloudTopic?.state || 'waiting');
  ui.liveOdomTopic.textContent = odomSource || 'NO SOURCE';
  ui.liveOdomStatus.textContent = odomTopic?.state === 'ok' ? `live · ${formatHz(odomTopic.hz)}` : (odomTopic?.state || 'waiting');
  ui.liveMapTopic.textContent = gridSource || 'NO SOURCE';
  ui.liveMapStatus.textContent = gridTopic?.state === 'ok' ? (gridTopic.hz == null ? 'static ready' : `live · ${formatHz(gridTopic.hz)}`) : (gridTopic?.state || 'waiting');

  if (desiredMapView() === 'occupancy') {
    ui.mapFrame.textContent = `FRAME ${grid.frame_id || '—'}`;
    ui.mapPoints.textContent = grid.width && grid.height ? `${grid.width}×${grid.height} CELLS` : '0 CELLS';
    setStatePill(ui.mappingState, gridTopic?.state || 'waiting', gridTopic?.state === 'ok' && state.health?.robot_online ? 'LIVE 2D MAP' : 'LIVE DATA WAITING');
  } else {
    ui.mapFrame.textContent = `FRAME ${cloud.frame_id || liveCloud?.frame_id || '—'}`;
    const displayPoints = liveCloud?.accumulated_registered_scans ? cloudPointCount(liveCloud) : Number(cloud.sent_points || cloudPointCount(liveCloud));
    const pointLabel = liveCloud ? cloudPointSummary(liveCloud) : displayPoints.toLocaleString();
    ui.mapPoints.textContent = `${pointLabel} POINTS${liveCloud?.accumulated_registered_scans ? ' · ACCUMULATED' : ''}`;
    const mappingLabels = { mapping: 'WORLD FRAME · LIVE', cloud_only: 'CLOUD LIVE', waiting: 'LIVE DATA WAITING', stale: 'LIVE DATA STALE' };
    const label = frameMismatch ? 'SENSOR FRAME · EXTRINSIC' : (mappingLabels[mapping.state] || 'CLOUD LIVE');
    setStatePill(ui.mappingState, liveCloud ? (frameMismatch ? 'waiting' : (mapping.state || 'cloud_only')) : 'waiting', liveCloud ? label : 'LIVE DATA WAITING');
  }
  ui.lidarSub.title = ui.lidarSub.textContent;

  const battery = (state.sensors || []).find((sensor) => sensor.values?.battery_soc != null || sensor.category === 'battery');
  const soc = battery?.values?.battery_soc ?? (battery?.values?.percentage != null ? battery.values.percentage * 100 : null);
  ui.batteryMetric.textContent = soc == null ? '—' : `${Math.round(soc)}%`;
  ui.batterySub.textContent = battery ? `${safeNumber(battery.values.power_v ?? battery.values.voltage, 1)} V · ${formatHz(battery.hz)}` : '데이터 대기 중';

  updateSensors(state.sensors || []);
  updateOdometry(state.sensors || [], odomSource);
  updateSavedMapOverview();
  ui.lastUpdated.textContent = `Last update ${new Date().toLocaleTimeString('ko-KR', { hour12: false })}`;
}

function formatBounds(bounds) {
  if (!bounds?.min || !bounds?.max) return '—';
  const span = bounds.min.map((value, index) => Math.abs(Number(bounds.max[index]) - Number(value)));
  return span.every(Number.isFinite) ? `${span.map((value) => value.toFixed(1)).join(' × ')} m` : '—';
}

function updateSavedMapOverview() {
  const cloud = savedSceneCloud();
  const entries = savedMapCatalog.length ? savedMapCatalog : (cloud ? [{
    id: '__fallback_cloud', name: cloud.demo_snapshot ? 'Public demo cloud' : 'Saved point cloud',
    kind: 'pointcloud3d', file_name: cloud.topic || '/saved/map', point_count: cloudPointCount(cloud),
    frame_id: cloud.frame_id || 'map', bounds: cloud.bounds,
  }] : []);
  if (!selectedSavedMapMeta && entries.length) {
    selectedSavedMapMeta = entries[0];
    selectedSavedMapId = entries[0].id;
  }
  ui.savedMapCount.textContent = `${entries.length} map${entries.length === 1 ? '' : 's'}`;
  ui.savedMapList.innerHTML = entries.length ? entries.map((entry) => {
    const grid = entry.kind === 'occupancy2d';
    const count = grid ? `${entry.width || '—'}×${entry.height || '—'}` : `${Number(entry.point_count || 0).toLocaleString()} pts`;
    return `<button class="saved-map-item${selectedSavedMapId === entry.id ? ' is-active' : ''}" type="button" data-saved-map-id="${escapeHtml(entry.id)}"><i>${grid ? '▦' : '◌'}</i><span><strong>${escapeHtml(entry.name || 'Saved map')}</strong><small>${escapeHtml(entry.file_name || (grid ? '2D occupancy' : '3D point cloud'))}</small></span><b>${escapeHtml(count)}</b></button>`;
  }).join('') : '<div class="sensor-placeholder">저장 지도가 없습니다.</div>';

  const showingGrid = selectedSavedMapMeta?.kind === 'occupancy2d';
  const selected = showingGrid ? savedOccupancySnapshot : cloud;
  if (showingGrid && selected) {
    ui.savedMapTitle.textContent = selectedSavedMapMeta?.name || selected.name || 'Saved 2D map';
    ui.savedMapSource.textContent = selectedSavedMapMeta?.file_name || selected.topic || '/saved/map';
    ui.savedMapDetailFrame.textContent = selected.frame_id || '—';
    ui.savedMapDetailPoints.textContent = `${selected.width}×${selected.height} cells`;
    ui.savedMapBounds.textContent = `${safeNumber(selected.width * selected.resolution, 1)} × ${safeNumber(selected.height * selected.resolution, 1)} m`;
    ui.savedMapFrame.textContent = `FRAME ${selected.frame_id || '—'}`;
    ui.savedMapPoints.textContent = `${selected.width}×${selected.height} CELLS`;
    setStatePill(ui.savedMappingState, 'saved', 'SAVED 2D MAP');
  } else if (!showingGrid && selected) {
    const demo = Boolean(selected.demo_snapshot);
    ui.savedMapTitle.textContent = selectedSavedMapMeta?.name || (demo ? 'Public demo cloud' : selected.name || 'Saved point cloud');
    ui.savedMapSource.textContent = selectedSavedMapMeta?.file_name || selected.topic || '/saved/map';
    ui.savedMapDetailFrame.textContent = selected.frame_id || '—';
    ui.savedMapDetailPoints.textContent = `${cloudPointSummary(selected)} points`;
    ui.savedMapBounds.textContent = formatBounds(selected.bounds);
    ui.savedMapFrame.textContent = `FRAME ${selected.frame_id || '—'}`;
    ui.savedMapPoints.textContent = `${cloudPointSummary(selected)} POINTS · ${demo ? 'DEMO' : 'SAVED'}`;
    setStatePill(ui.savedMappingState, 'saved', demo ? 'DEMO 3D MAP' : 'SAVED 3D MAP');
  } else {
    ui.savedMapTitle.textContent = selectedSavedMapMeta?.name || '—';
    ui.savedMapSource.textContent = selectedSavedMapMeta?.file_name || '—';
    ui.savedMapDetailFrame.textContent = selectedSavedMapMeta?.frame_id || '—';
    ui.savedMapDetailPoints.textContent = showingGrid ? '2D map loading…' : '3D map loading…';
    ui.savedMapBounds.textContent = '—';
    setStatePill(ui.savedMappingState, entries.length ? 'waiting' : 'waiting', entries.length ? 'LOADING MAP' : 'NO SAVED MAP');
  }
  updateSavedPointBudgetAvailability();
  updateSavedMapManagement();
}

function updateSavedMapManagement() {
  const manageable = Boolean(selectedSavedMapMeta?.manageable && selectedSavedMapId !== '__fallback_cloud');
  const enabled = manageable && !savedMapMutationBusy;
  if (document.activeElement !== ui.savedMapNameInput) {
    ui.savedMapNameInput.value = selectedSavedMapMeta?.name || '';
  }
  ui.savedMapNameInput.disabled = !enabled;
  ui.savedMapRenameButton.disabled = !enabled;
  ui.savedMapDeleteButton.disabled = !enabled;
  ui.savedMapList.setAttribute('aria-busy', savedMapMutationBusy ? 'true' : 'false');
  ui.savedMapList.querySelectorAll('button').forEach((button) => {
    button.disabled = savedMapMutationBusy;
  });
  if (!selectedSavedMapMeta) ui.savedMapManageNote.textContent = '관리할 지도를 선택하세요.';
  else if (!manageable) ui.savedMapManageNote.textContent = '번들 데모 또는 읽기 전용 지도는 변경할 수 없습니다.';
  else if (selectedSavedMapMeta.kind === 'occupancy2d') ui.savedMapManageNote.textContent = '이름 변경·삭제 시 YAML과 연결된 PGM을 함께 처리합니다.';
  else ui.savedMapManageNote.textContent = '선택한 저장 지도 파일의 이름을 변경하거나 삭제합니다.';
}

function compactValue(value) {
  if (value == null) return '—';
  if (Array.isArray(value)) {
    const shown = value.slice(0, 4).map((item) => typeof item === 'number' ? Number(item).toFixed(2) : String(item));
    return `[${shown.join(', ')}${value.length > 4 ? '…' : ''}]`;
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value).slice(0, 3).map(([key, item]) => `${key}:${typeof item === 'number' ? Number(item).toFixed(2) : item}`);
    return entries.join(' ');
  }
  if (typeof value === 'number') return Number(value).toFixed(Math.abs(value) >= 100 ? 0 : 2);
  return String(value);
}

function updateSensors(sensors) {
  const priority = ['robot_state', 'imu', 'lidar', 'battery', 'gnss', 'range', 'environment'];
  const rank = (sensor) => {
    const index = priority.indexOf(sensor.category);
    return index < 0 ? priority.length : index;
  };
  const sorted = [...sensors].sort((a, b) => rank(a) - rank(b) || String(a.topic).localeCompare(String(b.topic)));
  ui.sensorCount.textContent = `${sensors.length} streams`;
  if (!sorted.length) {
    ui.sensorGrid.innerHTML = '<div class="sensor-placeholder">센서 데이터를 기다리고 있습니다.</div>';
    return;
  }
  ui.sensorGrid.innerHTML = sorted.map((sensor) => {
    const values = Object.entries(sensor.values || {})
      .filter(([key]) => !key.startsWith('motor_'))
      .slice(0, 5)
      .map(([key, value]) => `<div class="sensor-value"><span>${escapeHtml(key.replaceAll('_', ' '))}</span><b>${escapeHtml(compactValue(value))}</b></div>`)
      .join('');
    return `<article class="sensor-card"><div class="sensor-card-head"><strong title="${escapeHtml(sensor.topic)}">${escapeHtml(sensor.topic)}</strong><span>${formatHz(sensor.hz)}</span></div><div class="sensor-values">${values || '<div class="sensor-value"><span>state</span><b>receiving</b></div>'}</div></article>`;
  }).join('');
}

function updateOdometry(sensors, source) {
  const snapshot = latestState?.robot_pose;
  const odom = sensors.find((sensor) => sensor.topic === source) || sensors.find((sensor) => sensor.category === 'odometry');
  ui.odomTopic.textContent = snapshot?.topic || source || odom?.topic || 'NO SOURCE';
  if (snapshot) {
    applyPoseSnapshot(snapshot);
    return;
  }
  updateMapPose(
    odom?.values?.position,
    odom?.values?.orientation,
    odom?.values?.frame_id,
    odom?.values?.linear_velocity,
    odom?.topic || source || '',
  );
}

function applyPoseSnapshot(snapshot) {
  ui.odomTopic.textContent = snapshot?.topic || latestState?.sources?.odometry || 'NO SOURCE';
  if (!robotRuntimeDataCompatible) {
    clearLivePose();
    return;
  }
  const signature = `${snapshot?.topic || ''}:${snapshot?.seq || 0}:${snapshot?.state || 'waiting'}`;
  if (signature === lastPoseSignature) return;
  lastPoseSignature = signature;
  if (snapshot?.state !== 'ok') {
    clearLivePose();
    return;
  }
  updateMapPose(
    snapshot.position,
    snapshot.orientation,
    snapshot.frame_id,
    snapshot.linear_velocity,
    snapshot.topic,
  );
}

function updateMapPose(position, orientation, frameId, velocity = null, topic = '') {
  const x = Number(position?.x);
  const y = Number(position?.y);
  const z = Number(position?.z);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return;
  const rpy = quaternionRpy(orientation);
  const nextPose = {
    x,
    y,
    z: Number.isFinite(z) ? z : 0,
    roll: rpy[0],
    pitch: rpy[1],
    yaw: rpy[2],
    frameId: frameId || '',
    topic,
  };
  const previous = poseTrail[poseTrail.length - 1];
  const distance = previous ? Math.hypot(nextPose.x - previous.x, nextPose.y - previous.y) : Infinity;
  const turn = previous ? Math.abs(angleDelta(nextPose.yaw, previous.yaw)) : Infinity;
  if (!previous || distance > 0.025 || turn > 0.035) {
    poseTrail.push(nextPose);
    poseTrail = poseTrail.slice(-120);
  }
  if (!targetPose || targetPose.frameId !== nextPose.frameId || Math.hypot(targetPose.x - x, targetPose.y - y) > 5) {
    currentPose = { ...nextPose };
  }
  targetPose = nextPose;
  poseLive = true;
  lastPoseAt = Date.now();
  poseImuAnchor = Array.isArray(latestBodyRpy)
    ? { imuYaw: latestBodyRpy[2], odomYaw: nextPose.yaw }
    : null;
  const speed = Math.hypot(Number(velocity?.x || 0), Number(velocity?.y || 0), Number(velocity?.z || 0));
  ui.posX.textContent = safeNumber(x);
  ui.posY.textContent = safeNumber(y);
  ui.posZ.textContent = safeNumber(nextPose.z);
  ui.speed.textContent = safeNumber(speed);
}

function quaternionYaw(quaternion) {
  const x = Number(quaternion?.x) || 0;
  const y = Number(quaternion?.y) || 0;
  const z = Number(quaternion?.z) || 0;
  const w = Number(quaternion?.w);
  const normalizedW = Number.isFinite(w) ? w : 1;
  return Math.atan2(2 * (normalizedW * z + x * y), 1 - 2 * (y * y + z * z));
}

function quaternionRpy(quaternion) {
  const x = Number(quaternion?.x) || 0;
  const y = Number(quaternion?.y) || 0;
  const z = Number(quaternion?.z) || 0;
  const w = Number.isFinite(Number(quaternion?.w)) ? Number(quaternion.w) : 1;
  const roll = Math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y));
  const sinPitch = Math.max(-1, Math.min(1, 2 * (w * y - z * x)));
  return [roll, Math.asin(sinPitch), quaternionYaw({ x, y, z, w })];
}

function clearLivePose() {
  poseLive = false;
  targetPose = null;
  currentPose = null;
  poseImuAnchor = null;
  ui.posX.textContent = ui.posY.textContent = ui.posZ.textContent = ui.speed.textContent = '—';
  if (activePage === 'mapping') scene3d?.setRobotPose(null);
}

function animateRobot(timestamp) {
  requestAnimationFrame(animateRobot);
  if (!lastMotionFrameAt) lastMotionFrameAt = timestamp;
  const elapsed = Math.min(Math.max((timestamp - lastMotionFrameAt) / 1000, 0), 0.2);
  if (elapsed < 1 / 30) return;
  lastMotionFrameAt = timestamp;

  if (targetJointPositions) {
    if (!renderedJointPositions || renderedJointPositions.length !== targetJointPositions.length) {
      renderedJointPositions = targetJointPositions.slice();
    } else {
      const alpha = 1 - Math.exp(-elapsed / 0.055);
      renderedJointPositions = renderedJointPositions.map((value, index) =>
        value + (targetJointPositions[index] - value) * alpha);
    }
  }

  if (targetPose) {
    if (!currentPose || currentPose.frameId !== targetPose.frameId) {
      currentPose = { ...targetPose };
    } else {
      const alpha = 1 - Math.exp(-elapsed / 0.09);
      currentPose = {
        ...targetPose,
        x: currentPose.x + (targetPose.x - currentPose.x) * alpha,
        y: currentPose.y + (targetPose.y - currentPose.y) * alpha,
        z: currentPose.z + (targetPose.z - currentPose.z) * alpha,
        roll: currentPose.roll + angleDelta(targetPose.roll, currentPose.roll) * alpha,
        pitch: currentPose.pitch + angleDelta(targetPose.pitch, currentPose.pitch) * alpha,
        yaw: currentPose.yaw + angleDelta(targetPose.yaw, currentPose.yaw) * alpha,
      };
    }
  }

  if (activePage === 'mapping' && desiredMapView() === 'cloud') {
    if (robotRuntimeDataCompatible && renderedJointPositions) scene3d?.setRobotJointPositions?.(renderedJointPositions);
    scene3d?.setRobotPose(robotRuntimeDataCompatible && poseLive ? currentPose : null);
  }
}

function angleDelta(a, b) {
  return Math.atan2(Math.sin(a - b), Math.cos(a - b));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));
}

function renderTopics() {
  const query = ui.topicSearch.value.trim().toLowerCase();
  const category = ui.categoryFilter.value;
  const rows = latestTopics.filter((topic) => {
    const matchesText = !query || `${topic.name} ${topic.type}`.toLowerCase().includes(query);
    return matchesText && (!category || topic.category === category);
  });
  if (!rows.length) {
    ui.topicsBody.innerHTML = '<tr><td colspan="6" class="table-empty">조건에 맞는 토픽이 없습니다.</td></tr>';
    return;
  }
  ui.topicsBody.innerHTML = rows.map((topic) => `
    <tr>
      <td><span class="state-pill ${topic.state}">${topic.state}</span></td>
      <td class="topic-name">${topic.selected ? '◆ ' : ''}${escapeHtml(topic.name)}</td>
      <td class="topic-type">${escapeHtml(topic.type || topic.types?.join(', ') || 'type conflict')}</td>
      <td><span class="category-tag">${escapeHtml(topic.category)}</span></td>
      <td>${topic.hz == null ? '—' : topic.hz.toFixed(2)}</td>
      <td>${topic.age_s == null ? '—' : `${topic.age_s.toFixed(2)}s`}</td>
    </tr>`).join('');
}

function fillSourceSelect(select, options, selected, emptyLabel) {
  const html = [`<option value="">${emptyLabel}</option>`]
    .concat((options || []).map((item) => `<option value="${escapeHtml(item.topic)}">${escapeHtml(item.topic)}</option>`))
    .join('');
  select.innerHTML = html;
  select.value = selected || '';
}

async function refreshSources() {
  try {
    const payload = await api('/api/v1/sources');
    const fingerprint = JSON.stringify(payload);
    if (fingerprint === sourceFingerprint) return;
    sourceFingerprint = fingerprint;
    fillSourceSelect(ui.cameraSource, payload.options.camera, payload.selected.camera, '카메라 없음');
    ui.cameraSource.disabled = Boolean(payload.locked?.camera);
    ui.cameraSource.title = payload.locked?.camera
      ? 'Go2 직접 멀티캐스트 카메라는 실행 프로필에서 고정됩니다.'
      : '';
    fillSourceSelect(ui.cloudSource, payload.options.pointcloud, payload.selected.pointcloud, 'PointCloud 없음');
    fillSourceSelect(ui.odomSource, payload.options.odometry, payload.selected.odometry, 'Odometry 없음');
    fillSourceSelect(ui.mapSource, payload.options.occupancy_grid, payload.selected.occupancy_grid, '2D 맵 없음');
  } catch (error) { console.warn(error); }
}

async function selectSource(kind, value) {
  try {
    await api('/api/v1/sources', { method: 'POST', body: JSON.stringify({ [kind]: value }) });
    showToast(`${kind} 소스를 변경했습니다.`);
    sourceFingerprint = '';
  } catch (error) { showToast(`소스 변경 실패: ${error.message}`, true); }
}

async function refreshState() {
  try {
    latestState = await api('/api/v1/state');
    updateOverview(latestState);
    if (activePage === 'mapping') redrawActiveMap();
    if (activePage === 'maps') redrawSavedMap();
  } catch (error) {
    ui.connectionChip.className = 'connection-chip error';
    ui.connectionLabel.textContent = '에이전트 연결 끊김';
    if (scene3d) scene3d.setStatus({ online: false, lidarOnline: false, message: '에이전트 연결이 끊겼습니다' });
  }
}

function generatedMapName() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, '0');
  return `map_${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
}

function hasFreshLaserMap() {
  const topic = latestTopics.find((item) => item.name === '/Laser_map');
  if (topic?.state === 'ok') return true;
  // The live renderer deliberately subscribes to the much smaller
  // /cloud_registered stream.  /Laser_map is therefore not metered by the
  // dashboard, even though FAST-LIO is publishing it.  A live registered scan,
  // matching FAST-LIO odometry, and a Laser_map publisher together are a safe
  // readiness signal; the saver still waits for and validates an actual map.
  return Number(topic?.publishers || 0) > 0 &&
    latestState?.sources?.pointcloud === '/cloud_registered' &&
    latestState?.sources?.odometry === '/Odometry' &&
    latestState?.mapping?.cloud?.state === 'ok' &&
    latestState?.mapping?.odometry?.state === 'ok';
}

function mappingPipelineActive() {
  return ['starting', 'running', 'stopping'].includes(mappingControlSnapshot?.pipeline?.state);
}

function renderMappingControl() {
  if (!mappingControlSnapshot) return;
  const pipeline = mappingControlSnapshot.pipeline || {};
  const operation = mappingControlSnapshot.operation || {};
  const laserMapReady = hasFreshLaserMap();
  const lidarLive = latestState?.mapping?.cloud?.state === 'ok';
  const pipelineActive = mappingPipelineActive();
  const saving = operation.state === 'saving';
  const external = laserMapReady && !pipelineActive;

  ui.mappingPipelineLabel.textContent = external ? 'EXTERNAL · LIVE' : String(pipeline.state || 'idle').toUpperCase();
  ui.mappingDataLabel.textContent = laserMapReady ? 'LASER_MAP READY' : lidarLive ? 'LIDAR LIVE · MAP WAITING' : 'WAITING';
  ui.mappingSaveLabel.textContent = operation.state === 'succeeded'
    ? (operation.files || []).join(' · ')
    : operation.state === 'failed' ? 'FAILED' : operation.map_name || '—';

  if (saving) {
    setStatePill(ui.mappingControlState, 'waiting', 'SAVING');
    ui.mappingOperationMessage.textContent = `${operation.map_name || 'map'} 저장 및 검증을 진행하고 있습니다.`;
  } else if (pipeline.state === 'failed' && !external) {
    setStatePill(ui.mappingControlState, 'error', 'START FAILED');
    ui.mappingOperationMessage.textContent = pipeline.error || '매핑 파이프라인이 종료되었습니다. 로그를 확인하세요.';
  } else if (operation.state === 'failed') {
    setStatePill(ui.mappingControlState, 'error', 'SAVE FAILED');
    ui.mappingOperationMessage.textContent = operation.error || '지도 저장 또는 검증에 실패했습니다.';
  } else if (laserMapReady) {
    setStatePill(ui.mappingControlState, 'ok', external ? 'EXTERNAL MAPPING' : 'MAPPING READY');
    ui.mappingOperationMessage.textContent = external
      ? '터미널에서 시작된 매핑을 감지했습니다. 현재 맵 저장은 가능하며 중지는 시작한 터미널에서 해야 합니다.'
      : '누적 /Laser_map이 정상입니다. 지금 3D PCD와 선택한 2D 지도를 저장할 수 있습니다.';
  } else if (pipelineActive) {
    setStatePill(ui.mappingControlState, 'waiting', 'DATA WAITING');
    ui.mappingOperationMessage.textContent = '프로세스는 시작됐지만 /Laser_map 데이터가 아직 없습니다. 케이블과 XT16 입력을 확인하세요.';
  } else if (operation.state === 'succeeded') {
    setStatePill(ui.mappingControlState, 'ok', 'SAVED');
    ui.mappingOperationMessage.textContent = `${operation.map_name} 저장과 결과 검증이 완료되었습니다.`;
  } else {
    setStatePill(ui.mappingControlState, 'waiting', 'IDLE');
    ui.mappingOperationMessage.textContent = '로봇과 XT16 연결 후 새 매핑을 시작할 수 있습니다.';
  }

  ui.mappingStartButton.textContent = external ? '외부 세션 동작 중' : pipelineActive ? '새 세션 재시작' : '새 맵 시작';
  ui.mappingStartButton.disabled = saving || external || pipeline.state === 'stopping';
  ui.mappingSaveButton.disabled = saving || !laserMapReady;
  ui.mappingStopButton.disabled = saving || !pipelineActive || pipeline.state === 'stopping';
  ui.mappingSessionName.disabled = saving;
  ui.mappingCreate2d.disabled = saving;

  ui.mappingLog.textContent = mappingLogLines.length
    ? mappingLogLines.join('\n')
    : '[Robot Scope] mapping console ready';
  ui.mappingLog.scrollTop = ui.mappingLog.scrollHeight;

  if (operation.job_id && ['succeeded', 'failed'].includes(operation.state)) {
    const key = `${operation.job_id}:${operation.state}`;
    if (handledMappingOperation !== key) {
      handledMappingOperation = key;
      if (operation.state === 'succeeded') {
        showToast(`${operation.map_name} 지도를 저장했습니다.`);
        ui.mappingSessionName.value = generatedMapName();
        savedMapDataCache.clear();
        refreshSavedMaps();
      } else {
        showToast(`지도 저장 실패: ${operation.error || '로그를 확인하세요.'}`, true);
      }
    }
  }
}

async function refreshMappingControl() {
  try {
    const payload = await api(`/api/v1/mapping/control?since_log_seq=${mappingLogCursor}`);
    if (payload.logs_truncated) mappingLogLines = [];
    for (const entry of payload.logs || []) {
      const time = entry.at ? new Date(entry.at).toLocaleTimeString('ko-KR', { hour12: false }) : '--:--:--';
      mappingLogLines.push(`[${time}] ${String(entry.message || '')}`);
    }
    mappingLogLines = mappingLogLines.slice(-80);
    mappingLogCursor = Number(payload.log_cursor || mappingLogCursor);
    mappingControlSnapshot = payload;
    renderMappingControl();
  } catch (error) {
    ui.mappingStartButton.disabled = ui.mappingSaveButton.disabled = ui.mappingStopButton.disabled = true;
    setStatePill(ui.mappingControlState, 'error', 'UNAVAILABLE');
    ui.mappingOperationMessage.textContent = `매핑 제어를 사용할 수 없습니다: ${error.message}`;
  }
}

async function startMappingSession() {
  const active = mappingPipelineActive();
  const warning = active
    ? '저장하지 않은 현재 누적 지도를 지우고 새 FAST-LIO 세션을 시작할까요?'
    : '새 맵 시작은 기존 Hesai·FAST-LIO 프로세스를 정리하고 누적 지도를 처음부터 만듭니다. 계속할까요?';
  if (!window.confirm(warning)) return;
  ui.mappingStartButton.disabled = true;
  try {
    if (active) await api('/api/v1/mapping/stop', { method: 'POST', body: '{}' });
    await api('/api/v1/mapping/start', { method: 'POST', body: '{}' });
    resetLiveCloudAccumulator();
    lastCloudSnapshot = null;
    cloudSeq = -1;
    poseTrail = [];
    sceneCloudDataKey = '';
    sceneCloudSourceKey = '';
    scene3d?.clearTrail();
    showToast(active ? '새 매핑 세션을 시작했습니다.' : 'Hesai + FAST-LIO 시작을 요청했습니다.');
  } catch (error) {
    showToast(`매핑 시작 실패: ${error.message}`, true);
  } finally {
    await refreshMappingControl();
  }
}

async function saveMappingSession() {
  const name = ui.mappingSessionName.value.trim() || generatedMapName();
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(name)) {
    showToast('지도 이름은 영문, 숫자, 밑줄, 하이픈만 사용할 수 있습니다.', true);
    return;
  }
  ui.mappingSessionName.value = name;
  ui.mappingSaveButton.disabled = true;
  try {
    await api('/api/v1/mapping/save', {
      method: 'POST',
      body: JSON.stringify({ name, create_2d: ui.mappingCreate2d.checked }),
    });
    showToast('지도 캡처와 저장을 시작했습니다.');
  } catch (error) {
    showToast(`지도 저장 시작 실패: ${error.message}`, true);
  } finally {
    setTimeout(refreshMappingControl, 120);
  }
}

async function stopMappingSession() {
  if (hasFreshLaserMap() && !window.confirm('저장하지 않은 누적 지도는 사라집니다. 매핑을 중지할까요?')) return;
  ui.mappingStopButton.disabled = true;
  try {
    await api('/api/v1/mapping/stop', { method: 'POST', body: '{}' });
    showToast('대시보드가 시작한 매핑 프로세스를 중지했습니다.');
  } catch (error) {
    showToast(`매핑 중지 실패: ${error.message}`, true);
  } finally {
    await refreshMappingControl();
  }
}

async function refreshTopics() {
  try {
    latestTopics = (await api('/api/v1/topics')).topics || [];
    renderTopics();
    if (latestState) updateOverview(latestState);
    renderMappingControl();
  } catch (error) { console.warn(error); }
}

function resizeCanvas(canvas) {
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
  const height = Math.max(1, Math.round(canvas.clientHeight * ratio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  return { width, height, ratio };
}

async function refreshPointcloud() {
  if (pointcloudRequestInFlight) return;
  pointcloudRequestInFlight = true;
  const generation = pointcloudRequestGeneration;
  try {
    const cloud = await latestApi('/api/v1/pointcloud', cloudSeq);
    if (generation !== pointcloudRequestGeneration) return;
    if (!cloud?.seq || !cloud.points?.length) {
      if (activePage === 'mapping' && desiredMapView() === 'cloud') drawPointcloud(lastCloudSnapshot);
      return;
    }
    if (Number(cloud.seq) <= Number(cloudSeq)) return;
    cloudSeq = cloud.seq;
    lastCloudSnapshot = accumulateRegisteredCloud(cloud);
    if (activePage === 'mapping' && desiredMapView() === 'cloud') drawPointcloud(lastCloudSnapshot);
  } catch (_) {
    if (activePage === 'mapping' && desiredMapView() === 'cloud') drawPointcloud(null);
  } finally {
    pointcloudRequestInFlight = false;
  }
}

async function loadOfflinePointcloud() {
  try {
    const response = await fetch('/static/data/go2_saved_map.json', { cache: 'force-cache' });
    if (!response.ok) throw new Error(String(response.status));
    const cloud = await response.json();
    if (!cloud?.points?.length) throw new Error('empty snapshot');
    offlineCloudSnapshot = { ...cloud, offline_snapshot: true };
    updateSavedMapOverview();
    if (activePage === 'maps') redrawSavedMap();
    if (latestState) updateOverview(latestState);
  } catch (error) {
    console.info('offline 3D map unavailable; using generated demo cloud:', error);
    offlineCloudSnapshot = buildDemoPointcloud();
    updateSavedMapOverview();
    if (activePage === 'maps') redrawSavedMap();
    if (latestState) updateOverview(latestState);
  }
}

async function refreshSavedMaps() {
  try {
    const payload = await api('/api/v1/saved-maps');
    const maps = Array.isArray(payload.maps) ? payload.maps : [];
    savedMapCatalog = maps;
    const preserved = maps.find((entry) => entry.id === selectedSavedMapId);
    const keepFallback = selectedSavedMapId === '__fallback_cloud' && offlineCloudSnapshot &&
      !maps.some((entry) => entry.kind === 'pointcloud3d');
    const next = keepFallback ? null : (preserved || maps[0] || null);
    if (preserved) selectedSavedMapMeta = preserved;
    if (next && (next.id !== selectedSavedMapId || !savedMapDataCache.has(pointBudgetCacheKey(next.id, savedPointLimit, next.kind)))) {
      await selectSavedMap(next.id, false);
      return;
    }
    if (!next) {
      selectedSavedMapId = offlineCloudSnapshot ? '__fallback_cloud' : '';
      selectedSavedMapMeta = offlineCloudSnapshot ? {
        id: '__fallback_cloud', name: offlineCloudSnapshot.demo_snapshot ? 'Public demo cloud' : 'Saved point cloud',
        kind: 'pointcloud3d', file_name: offlineCloudSnapshot.topic || '/saved/map', frame_id: offlineCloudSnapshot.frame_id,
      } : null;
      savedMapViewPreference = 'cloud';
    }
    updateSavedMapOverview();
    if (activePage === 'maps') redrawSavedMap();
  } catch (error) {
    console.info('saved map catalog unavailable; using bundled fallback:', error);
    updateSavedMapOverview();
  }
}

async function selectSavedMap(mapId, notify = true, rethrow = false) {
  if (mapId === '__fallback_cloud') {
    selectedSavedMapId = mapId;
    selectedSavedMapMeta = savedMapCatalog.find((entry) => entry.id === mapId) || {
      id: mapId, name: offlineCloudSnapshot?.demo_snapshot ? 'Public demo cloud' : 'Saved point cloud',
      kind: 'pointcloud3d', file_name: offlineCloudSnapshot?.topic || '/saved/map', frame_id: offlineCloudSnapshot?.frame_id,
    };
    savedMapViewPreference = 'cloud';
    ui.savedMapViewMode.value = 'cloud';
    updateSavedMapOverview();
    if (activePage === 'maps') redrawSavedMap();
    return true;
  }
  const meta = savedMapCatalog.find((entry) => entry.id === mapId);
  if (!meta) return;
  selectedSavedMapId = meta.id;
  selectedSavedMapMeta = meta;
  savedMapViewPreference = meta.kind === 'occupancy2d' ? 'occupancy' : 'cloud';
  ui.savedMapViewMode.value = savedMapViewPreference;
  if (meta.kind === 'occupancy2d') savedOccupancySnapshot = null;
  else offlineCloudSnapshot = null;
  updateSavedMapOverview();
  try {
    const cacheKey = pointBudgetCacheKey(meta.id, savedPointLimit, meta.kind);
    let payload = savedMapDataCache.get(cacheKey);
    if (!payload) {
      let pending = savedMapLoadPromises.get(cacheKey);
      if (!pending) {
        pending = api(meta.kind === 'pointcloud3d' ? savedPointDataUrl(meta) : (meta.data_url || `/api/v1/saved-maps/${encodeURIComponent(meta.id)}/data`));
        savedMapLoadPromises.set(cacheKey, pending);
      }
      try {
        payload = await pending;
      } finally {
        if (savedMapLoadPromises.get(cacheKey) === pending) savedMapLoadPromises.delete(cacheKey);
      }
      savedMapDataCache.set(cacheKey, payload);
      while (savedMapDataCache.size > 2) {
        savedMapDataCache.delete(savedMapDataCache.keys().next().value);
      }
    }
    if (selectedSavedMapId !== meta.id) return;
    if (meta.kind === 'occupancy2d') savedOccupancySnapshot = payload;
    else offlineCloudSnapshot = { ...payload, offline_snapshot: true };
    updateSavedMapOverview();
    if (activePage === 'maps') redrawSavedMap();
    if (notify) showToast(`${meta.name || '저장 지도'}를 불러왔습니다.`);
    return true;
  } catch (error) {
    setStatePill(ui.savedMappingState, 'error', 'LOAD FAILED');
    if (notify) showToast(`저장 지도 로드 실패: ${error.message}`, true);
    if (rethrow) throw error;
    return false;
  }
}

function clearSavedMapCache(mapId) {
  for (const key of savedMapDataCache.keys()) {
    if (key.startsWith(`${mapId}:`)) savedMapDataCache.delete(key);
  }
  for (const key of savedMapLoadPromises.keys()) {
    if (key.startsWith(`${mapId}:`)) savedMapLoadPromises.delete(key);
  }
}

async function renameSelectedSavedMap() {
  if (savedMapMutationBusy || !selectedSavedMapMeta?.manageable) return;
  const name = ui.savedMapNameInput.value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(name)) {
    showToast('지도 이름은 영문·숫자로 시작하고 영문·숫자·_·-만 사용할 수 있습니다.', true);
    return;
  }
  if (name === selectedSavedMapMeta.name) {
    showToast('현재 이름과 같습니다.');
    return;
  }
  const previousId = selectedSavedMapId;
  savedMapMutationBusy = true;
  updateSavedMapManagement();
  try {
    const result = await api(`/api/v1/saved-maps/${encodeURIComponent(previousId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    });
    clearSavedMapCache(previousId);
    selectedSavedMapId = result.map.id;
    selectedSavedMapMeta = result.map;
    if (result.map.kind === 'pointcloud3d') offlineCloudSnapshot = null;
    else savedOccupancySnapshot = null;
    await refreshSavedMaps();
    showToast(`${result.map.name}으로 이름을 변경했습니다.`);
  } catch (error) {
    showToast(`이름 변경 실패: ${error.message}`, true);
  } finally {
    savedMapMutationBusy = false;
    updateSavedMapManagement();
  }
}

async function deleteSelectedSavedMap() {
  if (savedMapMutationBusy || !selectedSavedMapMeta?.manageable) return;
  const selected = selectedSavedMapMeta;
  const paired = selected.kind === 'occupancy2d' ? ' (YAML과 PGM 모두)' : '';
  if (!window.confirm(`${selected.name}${paired}을 삭제할까요? 이 작업은 되돌릴 수 없습니다.`)) return;
  const previousId = selectedSavedMapId;
  savedMapMutationBusy = true;
  updateSavedMapManagement();
  try {
    await api(`/api/v1/saved-maps/${encodeURIComponent(previousId)}`, { method: 'DELETE' });
    clearSavedMapCache(previousId);
    if (selected.kind === 'pointcloud3d') offlineCloudSnapshot = null;
    else savedOccupancySnapshot = null;
    selectedSavedMapId = '';
    selectedSavedMapMeta = null;
    await refreshSavedMaps();
    showToast(`${selected.name} 지도를 삭제했습니다.`);
  } catch (error) {
    showToast(`지도 삭제 실패: ${error.message}`, true);
  } finally {
    savedMapMutationBusy = false;
    updateSavedMapManagement();
  }
}

function setMapLayerVisibility(mode) {
  const cloudMode = mode !== 'occupancy';
  ui.sceneCanvas?.classList.toggle('is-hidden', !cloudMode);
  ui.mapCanvas?.classList.toggle('is-hidden', cloudMode);
  ui.mapGridOverlay?.classList.toggle('is-hidden', cloudMode);
  ui.sceneControls?.classList.toggle('is-hidden', !cloudMode);
  if (cloudMode) scene3d?.resize();
}

function setSavedMapLayerVisibility(mode) {
  const cloudMode = mode !== 'occupancy';
  ui.savedSceneCanvas?.classList.toggle('is-hidden', !cloudMode);
  ui.savedMapCanvas?.classList.toggle('is-hidden', cloudMode);
  ui.savedMapGridOverlay?.classList.toggle('is-hidden', cloudMode);
  ui.savedSceneControls?.classList.toggle('is-hidden', !cloudMode);
  if (cloudMode) savedScene3d?.resize();
}

function drawPointcloud(cloud) {
  const selectedCloud = liveSceneCloud(cloud);
  setMapLayerVisibility('cloud');
  activeMapView = 'cloud';
  if (!scene3d) return;
  if (!selectedCloud?.points?.length) {
    if (liveSceneHadCloud) {
      scene3d.clearPointCloud();
      sceneCloudDataKey = '';
      sceneCloudSourceKey = '';
      liveSceneHadCloud = false;
    }
    scene3d.setRobotPose(null);
    scene3d.setTrail([]);
    scene3d.setRobotVisible(mapOverlayVisible && robotRuntimeDataCompatible);
    scene3d.setStatus({
      online: Boolean(latestState?.health?.robot_online),
      lidarOnline: false,
      snapshot: false,
      message: robotRuntimeDataCompatible
        ? '실시간 LiDAR 신호를 기다리고 있습니다'
        : 'ROS 재시작 전 로봇 오버레이 숨김',
    });
    return;
  }

  const sourceKey = `live:${selectedCloud.topic || selectedCloud.frame_id || 'cloud'}`;
  const dataKey = `${sourceKey}:${selectedCloud.seq ?? selectedCloud.stamp_ns ?? cloudPointCount(selectedCloud)}`;
  if (dataKey !== sceneCloudDataKey) {
    scene3d.setPointCloud(selectedCloud, { fit: sourceKey !== sceneCloudSourceKey });
    sceneCloudDataKey = dataKey;
    sceneCloudSourceKey = sourceKey;
  }
  liveSceneHadCloud = true;
  scene3d.setRobotPose(robotRuntimeDataCompatible && poseLive ? currentPose : null);
  scene3d.setTrail(robotRuntimeDataCompatible ? poseTrail : []);
  scene3d.setRobotVisible(mapOverlayVisible && robotRuntimeDataCompatible);
  scene3d.setTrailVisible(mapOverlayVisible && robotRuntimeDataCompatible);
  scene3d.setStatus({
    online: poseLive || jointLive || Boolean(latestState?.health?.robot_online),
    lidarOnline: isLiveCloudReady(),
    snapshot: false,
    message: robotRuntimeDataCompatible
      ? '실시간 LiDAR 포인트클라우드'
      : 'ROS 재시작 전 기존 데이터 · 로봇 오버레이 숨김',
  });
}

function drawSavedPointcloud() {
  const selectedCloud = savedSceneCloud();
  setSavedMapLayerVisibility('cloud');
  if (!savedScene3d) return;
  if (!selectedCloud?.points?.length) {
    savedScene3d.clearPointCloud();
    savedScene3d.setRobotPose(null);
    savedScene3d.setStatus({ online: null, lidarOnline: null, snapshot: true, message: '저장된 3D 지도가 없습니다' });
    return;
  }
  const sourceKey = `saved:${selectedSavedMapId || selectedCloud.map_id || 'fallback'}:${selectedCloud.topic || selectedCloud.frame_id || 'cloud'}`;
  const dataKey = `${sourceKey}:${selectedCloud.seq ?? cloudPointCount(selectedCloud)}`;
  if (dataKey !== savedSceneCloudDataKey) {
    savedScene3d.setPointCloud(selectedCloud, { fit: sourceKey !== savedSceneCloudSourceKey });
    savedSceneCloudDataKey = dataKey;
    savedSceneCloudSourceKey = sourceKey;
  }
  savedScene3d.setRobotPose(null);
  savedScene3d.setTrail([]);
  savedScene3d.setRobotVisible(savedMapOverlayVisible);
  savedScene3d.setTrailVisible(false);
  savedScene3d.setStatus({ online: null, lidarOnline: null, snapshot: true, message: selectedCloud.demo_snapshot ? '공개용 데모 지도' : '저장된 LiDAR 지도' });
}

async function refreshMap() {
  try {
    const map = await latestApi('/api/v1/map', mapSeq);
    if (!map?.seq || !map.data_b64) return;
    mapSeq = map.seq;
    lastMapSnapshot = map;
    if (activePage === 'mapping' && desiredMapView() === 'occupancy') drawOccupancyMap(map, false);
  } catch (_) {}
}

function drawOccupancyMap(map, saved = false) {
  if (saved) setSavedMapLayerVisibility('occupancy'); else setMapLayerVisibility('occupancy');
  const canvas = saved ? ui.savedMapCanvas : ui.mapCanvas;
  const { width, height, ratio } = resizeCanvas(canvas);
  const source = document.createElement('canvas');
  source.width = map.width; source.height = map.height;
  const sourceContext = source.getContext('2d');
  const image = sourceContext.createImageData(map.width, map.height);
  const binary = atob(map.data_b64);
  for (let y = 0; y < map.height; y++) {
    for (let x = 0; x < map.width; x++) {
      const inputIndex = y * map.width + x;
      const outputIndex = ((map.height - 1 - y) * map.width + x) * 4;
      const raw = binary.charCodeAt(inputIndex);
      const value = raw > 127 ? -1 : raw;
      const shade = value < 0 ? 35 : value >= 65 ? 7 : 205;
      image.data[outputIndex] = shade * .55;
      image.data[outputIndex + 1] = shade;
      image.data[outputIndex + 2] = shade * .82;
      image.data[outputIndex + 3] = 255;
    }
  }
  sourceContext.putImageData(image, 0, 0);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#06100e'; ctx.fillRect(0, 0, width, height);
  const scale = Math.min(width / map.width, height / map.height) * .94;
  const drawWidth = map.width * scale, drawHeight = map.height * scale;
  const left = (width - drawWidth) / 2;
  const top = (height - drawHeight) / 2;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(source, left, top, drawWidth, drawHeight);
  if (saved) savedOccupancySnapshot = map;
  else {
    lastMapSnapshot = map;
    activeMapView = 'occupancy';
  }
  const origin = Array.isArray(map.origin) ? map.origin : [0, 0, 0];
  const originX = Number(origin[0]) || 0;
  const originY = Number(origin[1]) || 0;
  const originYaw = Number(origin[2]) || 0;
  const resolution = Math.max(Number(map.resolution) || 0, 0.0001);
  const cos = Math.cos(originYaw);
  const sin = Math.sin(originYaw);
  const projectWorld = (pose) => {
    const dx = pose.x - originX;
    const dy = pose.y - originY;
    const localX = cos * dx + sin * dy;
    const localY = -sin * dx + cos * dy;
    return {
      x: left + (localX / resolution) * scale,
      y: top + drawHeight - (localY / resolution) * scale,
      heading: -(pose.yaw - originYaw),
      inside: localX >= 0 && localX <= map.width * resolution && localY >= 0 && localY <= map.height * resolution,
    };
  };
  if (!saved) drawMapOverlay(ctx, { width, height, ratio, projectWorld, fallbackScale: scale / resolution, mode: 'GRID', frameId: map.frame_id || '' });
}

function redrawActiveMap() {
  const desired = desiredMapView();
  setMapLayerVisibility(desired);
  if (desired === 'occupancy' && lastMapSnapshot) drawOccupancyMap(lastMapSnapshot, false);
  else if (desired === 'cloud') drawPointcloud(lastCloudSnapshot);
}

function redrawSavedMap() {
  setSavedMapLayerVisibility(savedMapViewPreference);
  if (savedMapViewPreference === 'occupancy') {
    if (savedOccupancySnapshot) drawOccupancyMap(savedOccupancySnapshot, true);
    else setStatePill(ui.savedMappingState, 'waiting', 'LOADING 2D MAP');
  } else {
    drawSavedPointcloud();
  }
  updateSavedMapOverview();
}

function desiredMapView() {
  const liveGridReady = Boolean(latestState?.health?.robot_online && latestState?.sources?.occupancy_grid && lastMapSnapshot);
  if (mapViewPreference === 'occupancy') {
    return liveGridReady ? 'occupancy' : 'cloud';
  }
  if (mapViewPreference === 'cloud') return 'cloud';
  return liveGridReady ? 'occupancy' : 'cloud';
}

function chooseMapView(mode) {
  mapViewPreference = mode;
  ui.mapViewMode.value = mode;
  redrawActiveMap();
  if (latestState) updateOverview(latestState);
}

function chooseSavedMapView(mode) {
  const kind = mode === 'occupancy' ? 'occupancy2d' : 'pointcloud3d';
  const candidate = savedMapCatalog.find((entry) => entry.kind === kind);
  if (candidate) {
    selectSavedMap(candidate.id);
    return;
  }
  if (mode === 'cloud' && offlineCloudSnapshot) {
    selectSavedMap('__fallback_cloud');
    return;
  }
  savedMapViewPreference = mode === 'occupancy' && savedOccupancySnapshot ? 'occupancy' : 'cloud';
  ui.savedMapViewMode.value = savedMapViewPreference;
  redrawSavedMap();
}

function drawMapOverlay(ctx, viewport) {
  if (!mapOverlayVisible || !currentPose) return;
  const framesMatch = !viewport.frameId || !currentPose.frameId || viewport.frameId === currentPose.frameId;
  const poseProjection = viewport.projectWorld(currentPose);
  const anchor = framesMatch && poseProjection.inside
    ? poseProjection
    : {
        x: viewport.width / 2,
        y: viewport.height / 2,
        heading: poseProjection.heading,
        inside: false,
        frameMismatch: !framesMatch,
      };
  const fallbackProject = (pose) => ({
    x: anchor.x + (pose.x - currentPose.x) * viewport.fallbackScale,
    y: anchor.y - (pose.y - currentPose.y) * viewport.fallbackScale,
  });
  const projectedTrail = poseTrail.map((pose) => {
    const projected = viewport.projectWorld(pose);
    return framesMatch && projected.inside && poseProjection.inside ? projected : fallbackProject(pose);
  }).filter((point) => point.x > -20 && point.x < viewport.width + 20 && point.y > -20 && point.y < viewport.height + 20);
  const unit = viewport.ratio;

  ctx.save();
  ctx.lineCap = 'round';
  if (projectedTrail.length > 1) {
    ctx.beginPath();
    projectedTrail.forEach((point, index) => index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y));
    ctx.strokeStyle = 'rgba(162, 139, 255, .76)';
    ctx.lineWidth = 1.5 * unit;
    ctx.setLineDash([4 * unit, 5 * unit]);
    ctx.stroke();
    ctx.setLineDash([]);
    projectedTrail.forEach((point, index) => {
      const alpha = .18 + (.52 * (index + 1) / projectedTrail.length);
      ctx.fillStyle = `rgba(162, 139, 255, ${alpha})`;
      ctx.beginPath();
      ctx.arc(point.x, point.y, 1.8 * unit, 0, Math.PI * 2);
      ctx.fill();
    });
  }
  drawQuadruped(ctx, anchor.x, anchor.y, anchor.heading, unit);
  drawPoseLabel(ctx, anchor, viewport, unit);
  ctx.restore();
}

function drawQuadruped(ctx, x, y, heading, unit) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(heading);
  ctx.shadowColor = 'rgba(125, 240, 182, .76)';
  ctx.shadowBlur = 13 * unit;
  ctx.strokeStyle = '#c9ffe6';
  ctx.fillStyle = 'rgba(31, 102, 78, .94)';
  ctx.lineWidth = 1.35 * unit;
  const legLength = 12 * unit;
  const legOffsets = [[5, 8], [5, -8], [-7, 8], [-7, -8]];
  ctx.beginPath();
  legOffsets.forEach(([legX, legY]) => {
    ctx.moveTo(legX * unit, legY * unit);
    ctx.lineTo((legX + (legX > 0 ? 4 : -3)) * unit, (legY + (legY > 0 ? 1 : -1)) * unit);
  });
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(13 * unit, 0);
  ctx.lineTo(5 * unit, 7 * unit);
  ctx.lineTo(-10 * unit, 6 * unit);
  ctx.lineTo(-13 * unit, 0);
  ctx.lineTo(-10 * unit, -6 * unit);
  ctx.lineTo(5 * unit, -7 * unit);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = '#ecfff5';
  ctx.beginPath();
  ctx.moveTo(17 * unit, 0);
  ctx.lineTo(8 * unit, -3 * unit);
  ctx.lineTo(8 * unit, 3 * unit);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function drawPoseLabel(ctx, anchor, viewport, unit) {
  const xText = `X ${currentPose.x.toFixed(2)} m`;
  const yText = `Y ${currentPose.y.toFixed(2)} m`;
  const yawDegrees = ((currentPose.yaw * 180 / Math.PI) + 360) % 360;
  const headingText = `${viewport.mode} · ${yawDegrees.toFixed(0)}°`;
  const fontSize = 9 * unit;
  ctx.font = `600 ${fontSize}px ui-monospace, SFMono-Regular, Menlo, monospace`;
  const labelWidth = Math.max(ctx.measureText(xText).width, ctx.measureText(yText).width, ctx.measureText(headingText).width) + 14 * unit;
  const labelHeight = 39 * unit;
  const labelX = Math.min(viewport.width - labelWidth - 8 * unit, Math.max(8 * unit, anchor.x + 18 * unit));
  const labelY = Math.max(8 * unit, anchor.y - labelHeight - 10 * unit);
  ctx.fillStyle = 'rgba(5, 16, 13, .86)';
  ctx.strokeStyle = 'rgba(125, 240, 182, .38)';
  ctx.lineWidth = unit;
  ctx.beginPath();
  ctx.roundRect(labelX, labelY, labelWidth, labelHeight, 5 * unit);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = '#d9fff0';
  ctx.fillText(xText, labelX + 7 * unit, labelY + 12 * unit);
  ctx.fillText(yText, labelX + 7 * unit, labelY + 23 * unit);
  ctx.fillStyle = '#8fa9a1';
  ctx.font = `500 ${7 * unit}px ui-monospace, SFMono-Regular, Menlo, monospace`;
  ctx.fillText(headingText, labelX + 7 * unit, labelY + 33 * unit);
  if (!anchor.inside) {
    ctx.fillStyle = 'rgba(255, 198, 109, .9)';
    ctx.font = `600 ${7 * unit}px ui-monospace, SFMono-Regular, Menlo, monospace`;
    ctx.fillText(anchor.frameMismatch ? 'FRAME RELATIVE' : 'RELATIVE VIEW', labelX + labelWidth - 72 * unit, labelY + 33 * unit);
  }
}

const CAMERA_FRAME_FRESH_MS = 3000;
const CAMERA_RECORD_MAX_MS = 10 * 60 * 1000;
const CAMERA_RECORD_MAX_BYTES = 256 * 1024 * 1024;

function cameraFrameIsFresh(lastFrameAt, metadata = {}, now = Date.now(), maxAgeMs = CAMERA_FRAME_FRESH_MS) {
  const localAgeMs = Number(now) - Number(lastFrameAt || 0);
  if (!lastFrameAt || !Number.isFinite(localAgeMs) || localAgeMs < 0 || localAgeMs > maxAgeMs) return false;
  const state = String(metadata?.state || '').toLowerCase();
  if (state && state !== 'ok' && state !== 'live') return false;
  const reportedAge = Number(metadata?.age_s);
  if (metadata?.age_s != null && (!Number.isFinite(reportedAge) || reportedAge * 1000 > maxAgeMs)) return false;
  return true;
}

function createLatestCameraFrameQueue({ decode, render, close, onError = () => {} }) {
  let generation = 0;
  let active = false;
  let pending = null;

  async function drain(initialFrame) {
    let frame = initialFrame;
    while (frame) {
      let decoded = null;
      try {
        decoded = await decode(frame);
        if (frame.generation === generation) render(decoded, frame);
      } catch (error) {
        if (frame.generation === generation) onError(error, frame);
      } finally {
        if (decoded) close(decoded, frame);
      }
      frame = pending;
      pending = null;
    }
    active = false;
  }

  return Object.freeze({
    enqueue(frame) {
      const tagged = { ...frame, generation };
      if (active) {
        // Keep only the newest undecoded frame. ArrayBuffer payloads require no
        // explicit close and are released when this reference is replaced.
        pending = tagged;
      } else {
        active = true;
        void drain(tagged);
      }
      return generation;
    },
    reset() {
      generation += 1;
      pending = null;
      return generation;
    },
    snapshot() {
      return { generation, active, pending: pending ? 1 : 0 };
    },
  });
}

function getCameraImageDecodeQueue() {
  if (cameraImageDecodeQueue) return cameraImageDecodeQueue;
  cameraImageDecodeQueue = createLatestCameraFrameQueue({
    decode: (frame) => createImageBitmap(new Blob(
      [frame.data],
      { type: frame.format === 'png' ? 'image/png' : 'image/jpeg' },
    )),
    render: (bitmap, frame) => renderCameraSourceFrame(
      bitmap,
      bitmap.width,
      bitmap.height,
      frame.sourceKey,
    ),
    close: (bitmap) => bitmap.close(),
    onError: (error) => console.warn('camera image decode:', error),
  });
  return cameraImageDecodeQueue;
}

function resetCameraImageDecodeQueue() {
  cameraImageDecodeQueue?.reset();
}

function enqueueCameraImageFrame(data, metadata) {
  getCameraImageDecodeQueue().enqueue({
    data,
    format: metadata.format,
    seq: metadata.seq,
    sourceKey: metadata.topic || metadata.source || metadata.stream_url || metadata.transport || cameraActiveSourceKey,
  });
}

function cameraFrameAvailable(now = Date.now()) {
  return Boolean(
    ui.cameraCanvas.width > 1
    && ui.cameraCanvas.height > 1
    && cameraFrameIsFresh(cameraLastFrameAt, cameraStatusMeta || cameraMeta, now),
  );
}

function cameraRecordingSupported() {
  return typeof ui.cameraCanvas?.captureStream === 'function' && typeof window.MediaRecorder === 'function';
}

function setCameraMediaMessage(status, help, error = false) {
  ui.cameraMediaStatus.textContent = status;
  ui.cameraMediaStatus.dataset.state = error ? 'error' : 'ok';
  if (help) ui.cameraMediaHelp.textContent = help;
}

function syncCameraMediaControls() {
  const hasFrame = cameraFrameAvailable();
  const recording = Boolean(cameraRecording);
  const stopping = Boolean(cameraRecording?.stopping);
  const supported = cameraRecordingSupported();
  ui.cameraCaptureButton.disabled = !hasFrame;
  ui.cameraCaptureFormat.disabled = !hasFrame || recording;
  ui.cameraRecordButton.disabled = !hasFrame || recording || !supported;
  ui.cameraStopRecordButton.disabled = !recording || stopping;
  ui.cameraCanvas.closest('.camera-panel')?.classList.toggle('is-recording', recording && !stopping);
}

function syncCameraFrameFreshness(now = Date.now()) {
  const fresh = cameraFrameAvailable(now);
  syncCameraMediaControls();
  if (fresh || !cameraLastFrameAt) return fresh;
  const reportedState = String(cameraStatusMeta?.state || cameraMeta?.state || 'stale').toUpperCase();
  const message = `마지막 영상 프레임이 ${Math.max(0, (now - cameraLastFrameAt) / 1000).toFixed(1)}초 전입니다. 새 프레임을 기다리고 있습니다.`;
  if (cameraRecording) {
    if (!cameraRecording.stopping) {
      stopCameraRecording({ discard: false, reason: '영상 신호가 3초 이상 멈춰 녹화를 종료하고 저장했습니다.' });
    }
  } else {
    setCameraMediaMessage(`FRAME ${reportedState === 'OK' ? 'STALE' : reportedState}`, message, true);
  }
  return false;
}

function markCameraFrameRendered(sourceKey = '') {
  const wasFresh = cameraFrameAvailable();
  if (sourceKey) cameraActiveSourceKey = sourceKey;
  cameraLastFrameAt = Date.now();
  cameraFrames += 1;
  cameraFrameWindow.push(performance.now());
  while (cameraFrameWindow.length && performance.now() - cameraFrameWindow[0] > 1000) cameraFrameWindow.shift();
  ui.cameraEmpty.style.display = 'none';
  if (!cameraRecording && !wasFresh) {
    const recorderNote = cameraRecordingSupported()
      ? '현재 표시 프레임을 캡처하거나 브라우저에서 녹화할 수 있습니다.'
      : '화면 캡처 가능 · 이 브라우저는 영상 녹화를 지원하지 않습니다.';
    setCameraMediaMessage('FRAME READY', recorderNote);
  }
  syncCameraMediaControls();
}

// Every camera transport ends here.  A direct Flask/MJPEG adapter can pass its
// HTMLImageElement to this function and gets the same capture/record behavior
// as the existing ROS/WebSocket H.264, JPEG, PNG and raw-image paths.
function renderCameraSourceFrame(source, requestedWidth = 0, requestedHeight = 0, sourceKey = '') {
  const width = Number(requestedWidth || source?.displayWidth || source?.videoWidth || source?.naturalWidth || source?.width || 0);
  const height = Number(requestedHeight || source?.displayHeight || source?.videoHeight || source?.naturalHeight || source?.height || 0);
  if (!source || !Number.isFinite(width) || !Number.isFinite(height) || width < 2 || height < 2) {
    throw new Error('카메라 프레임 크기가 비어 있습니다.');
  }
  const canvas = ui.cameraCanvas;
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  canvas.getContext('2d').drawImage(source, 0, 0, width, height);
  markCameraFrameRendered(sourceKey || cameraMeta?.topic || cameraActiveSourceKey);
}

function cameraTimestamp() {
  const value = new Date();
  const parts = [
    value.getFullYear(),
    String(value.getMonth() + 1).padStart(2, '0'),
    String(value.getDate()).padStart(2, '0'),
    '_',
    String(value.getHours()).padStart(2, '0'),
    String(value.getMinutes()).padStart(2, '0'),
    String(value.getSeconds()).padStart(2, '0'),
  ];
  return parts.join('');
}

function cameraDownloadName(kind, extension, sourceOverride = '') {
  const source = String(sourceOverride || cameraMeta?.topic || cameraActiveSourceKey || 'camera')
    .split('/').filter(Boolean).pop()?.replace(/[^a-z0-9_-]+/gi, '_') || 'camera';
  return `${source}_${kind}_${cameraTimestamp()}.${extension}`;
}

function downloadCameraBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1200);
}

async function captureCameraFrame() {
  if (!cameraFrameAvailable()) {
    const message = '캡처할 카메라 프레임이 없습니다. 영상이 표시된 뒤 다시 시도하세요.';
    setCameraMediaMessage('NO FRAME', message, true);
    showToast(message, true);
    return;
  }
  const mimeType = ui.cameraCaptureFormat.value === 'image/jpeg' ? 'image/jpeg' : 'image/png';
  const extension = mimeType === 'image/jpeg' ? 'jpg' : 'png';
  try {
    const blob = await new Promise((resolve, reject) => {
      ui.cameraCanvas.toBlob(
        (result) => result ? resolve(result) : reject(new Error('브라우저가 이미지 파일을 만들지 못했습니다.')),
        mimeType,
        mimeType === 'image/jpeg' ? 0.92 : undefined,
      );
    });
    const filename = cameraDownloadName('capture', extension);
    downloadCameraBlob(blob, filename);
    setCameraMediaMessage('CAPTURE SAVED', `${filename} 다운로드를 시작했습니다.`);
    showToast(`카메라 화면을 ${extension.toUpperCase()}로 저장했습니다.`);
  } catch (error) {
    const message = `화면 캡처 실패: ${error.message}`;
    setCameraMediaMessage('CAPTURE FAILED', message, true);
    showToast(message, true);
  }
}

function chooseCameraRecordingMimeType() {
  const candidates = [
    'video/webm;codecs=vp9',
    'video/webm;codecs=vp8',
    'video/webm',
    'video/mp4;codecs=avc1.42E01E',
    'video/mp4',
  ];
  if (typeof window.MediaRecorder?.isTypeSupported !== 'function') return '';
  return candidates.find((mimeType) => window.MediaRecorder.isTypeSupported(mimeType)) || '';
}

function updateCameraRecordingDuration(session = cameraRecording) {
  if (!session || session.finalized) return;
  const elapsedMs = Math.max(0, performance.now() - session.startedAt);
  const seconds = Math.floor(elapsedMs / 1000);
  const minutes = Math.floor(seconds / 60);
  ui.cameraRecordDuration.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  ui.cameraRecordDuration.dateTime = `PT${seconds}S`;
  if (elapsedMs >= CAMERA_RECORD_MAX_MS && !session.stopping) {
    stopCameraRecording({ discard: false, reason: '최대 녹화 시간 10분에 도달하여 자동 저장했습니다.' });
  }
}

function finalizeCameraRecording(session) {
  if (!session || session.finalized) return;
  session.finalized = true;
  clearInterval(session.timer);
  session.stream.getTracks().forEach((track) => track.stop());
  if (cameraRecording === session) cameraRecording = null;
  syncCameraMediaControls();

  if (session.discard) {
    const message = session.reason || '녹화를 중단하고 임시 데이터를 정리했습니다.';
    setCameraMediaMessage(session.failed ? 'RECORDING FAILED' : 'RECORDING STOPPED', message, session.failed);
    if (session.failed && !session.silent) showToast(message, true);
    return;
  }
  const mimeType = session.recorder.mimeType || session.mimeType || 'video/webm';
  const blob = new Blob(session.chunks, { type: mimeType });
  if (!blob.size) {
    const message = '녹화된 프레임이 없어 파일을 만들지 못했습니다.';
    setCameraMediaMessage('EMPTY RECORDING', message, true);
    showToast(message, true);
    return;
  }
  const extension = mimeType.includes('mp4') ? 'mp4' : 'webm';
  const filename = cameraDownloadName('recording', extension, session.sourceKey);
  downloadCameraBlob(blob, filename);
  setCameraMediaMessage('RECORDING SAVED', session.reason || `${filename} 다운로드를 시작했습니다.`);
  showToast(session.reason || `카메라 녹화를 ${extension.toUpperCase()}로 저장했습니다.`);
}

function startCameraRecording() {
  if (cameraRecording) return;
  if (!cameraFrameAvailable()) {
    const message = '녹화할 카메라 프레임이 없습니다. 영상이 표시된 뒤 다시 시도하세요.';
    setCameraMediaMessage('NO FRAME', message, true);
    showToast(message, true);
    return;
  }
  if (!cameraRecordingSupported()) {
    const message = '이 브라우저는 canvas.captureStream 또는 MediaRecorder를 지원하지 않습니다.';
    setCameraMediaMessage('RECORDING UNSUPPORTED', message, true);
    showToast(message, true);
    return;
  }

  let stream = null;
  try {
    stream = ui.cameraCanvas.captureStream(30);
    if (!stream.getVideoTracks().length) throw new Error('캔버스 비디오 트랙을 만들지 못했습니다.');
    const mimeType = chooseCameraRecordingMimeType();
    let recorder;
    try {
      recorder = mimeType
        ? new window.MediaRecorder(stream, { mimeType, videoBitsPerSecond: 4_000_000 })
        : new window.MediaRecorder(stream);
    } catch (_) {
      recorder = new window.MediaRecorder(stream);
    }
    const session = {
      recorder,
      stream,
      mimeType,
      chunks: [],
      bytes: 0,
      startedAt: performance.now(),
      sourceKey: cameraActiveSourceKey,
      timer: null,
      stopping: false,
      discard: false,
      reason: '',
      failed: false,
      silent: false,
      finalized: false,
    };
    recorder.addEventListener('dataavailable', (event) => {
      if (session.discard || !event.data?.size) return;
      session.chunks.push(event.data);
      session.bytes += event.data.size;
      if (session.bytes >= CAMERA_RECORD_MAX_BYTES && !session.stopping) {
        stopCameraRecording({ discard: false, reason: '녹화 데이터가 256 MiB 제한에 도달하여 자동 저장했습니다.' });
      }
    });
    recorder.addEventListener('error', (event) => {
      if (session.stopping) return;
      session.discard = true;
      session.failed = true;
      session.reason = `브라우저 녹화 오류: ${event.error?.message || '알 수 없는 오류'}`;
      if (recorder.state !== 'inactive') recorder.stop(); else finalizeCameraRecording(session);
    });
    recorder.addEventListener('stop', () => finalizeCameraRecording(session), { once: true });
    cameraRecording = session;
    recorder.start(1000);
    session.timer = setInterval(() => updateCameraRecordingDuration(session), 250);
    updateCameraRecordingDuration(session);
    setCameraMediaMessage('RECORDING', '표시 중인 캔버스를 녹화합니다 · 최대 10분 또는 256 MiB');
    syncCameraMediaControls();
  } catch (error) {
    stream?.getTracks().forEach((track) => track.stop());
    cameraRecording = null;
    const message = `녹화 시작 실패: ${error.message}`;
    setCameraMediaMessage('RECORDING FAILED', message, true);
    syncCameraMediaControls();
    showToast(message, true);
  }
}

function cameraRecordingCleanupPolicy(trigger) {
  if (trigger === 'page_hidden') {
    return { discard: true, reason: '페이지를 벗어나 녹화를 중단하고 임시 데이터를 정리했습니다.', silent: true };
  }
  if (trigger === 'sensors_page_left') {
    return { discard: false, reason: 'Sensors 화면을 벗어나 녹화를 종료하고 저장했습니다.', silent: false };
  }
  return { discard: false, reason: '페이지가 숨겨져 녹화를 종료하고 저장했습니다.', silent: false };
}

function stopCameraRecording({ discard = false, reason = '', silent = false } = {}) {
  const session = cameraRecording;
  if (!session || session.stopping || session.finalized) return false;
  session.stopping = true;
  session.discard = discard;
  session.reason = reason;
  session.silent = silent;
  if (discard) {
    session.chunks.length = 0;
    session.bytes = 0;
  }
  clearInterval(session.timer);
  setCameraMediaMessage('FINALIZING', discard ? '녹화 데이터를 정리하고 있습니다.' : '녹화 파일을 마무리하고 있습니다.');
  syncCameraMediaControls();
  try {
    if (!discard && session.recorder.state === 'recording') session.recorder.requestData();
    if (session.recorder.state !== 'inactive') session.recorder.stop();
    else finalizeCameraRecording(session);
    if (discard) session.stream.getTracks().forEach((track) => track.stop());
  } catch (error) {
    session.discard = true;
    session.failed = true;
    session.reason = `녹화 종료 실패: ${error.message}`;
    finalizeCameraRecording(session);
  }
  return true;
}

function discardCameraRecordingForPageHide() {
  const session = cameraRecording;
  if (!session) return false;
  const policy = cameraRecordingCleanupPolicy('page_hidden');
  if (!session.stopping) return stopCameraRecording(policy);
  // visibilitychange may have started an asynchronous save immediately before
  // pagehide. A download cannot be trusted once the document is unloading, so
  // convert that in-flight finalization to a discard and release tracks now.
  session.discard = true;
  session.reason = policy.reason;
  session.silent = true;
  session.chunks.length = 0;
  session.bytes = 0;
  session.stream.getTracks().forEach((track) => track.stop());
  return true;
}

function resetCameraRenderedFrame(nextSourceKey = '', { discardRecording = false, reason = '' } = {}) {
  if (cameraRecording) {
    stopCameraRecording({
      discard: discardRecording,
      reason: reason || (discardRecording ? '페이지를 벗어나 녹화를 중단했습니다.' : '카메라 소스 변경으로 녹화를 종료하고 저장했습니다.'),
      silent: discardRecording,
    });
  }
  resetCameraImageDecodeQueue();
  if (videoDecoder && videoDecoder.state !== 'closed') {
    try { videoDecoder.close(); } catch (_) {}
  }
  videoDecoder = null;
  cameraHasKey = false;
  cameraMeta = null;
  cameraStatusMeta = null;
  cameraLastFrameAt = 0;
  cameraFrames = 0;
  cameraFrameWindow = [];
  cameraActiveSourceKey = nextSourceKey;
  ui.cameraCanvas.width = 1;
  ui.cameraCanvas.height = 1;
  ui.cameraEmpty.style.display = '';
  ui.cameraEmptyText.textContent = reason || '새 카메라 영상 신호를 기다리고 있습니다.';
  ui.cameraRecordDuration.textContent = '00:00';
  ui.cameraRecordDuration.dateTime = 'PT0S';
  if (!cameraRecording) setCameraMediaMessage('FRAME WAITING', '영상이 표시되면 캡처와 녹화를 사용할 수 있습니다.');
  syncCameraMediaControls();
}

function noteCameraSource(sourceKey) {
  const nextSourceKey = String(sourceKey || '').trim();
  if (!nextSourceKey) return;
  if (cameraActiveSourceKey && cameraActiveSourceKey !== nextSourceKey) {
    resetCameraRenderedFrame(nextSourceKey, { reason: '카메라 소스가 변경되어 새 프레임을 기다리고 있습니다.' });
  } else {
    cameraActiveSourceKey = nextSourceKey;
  }
}

function initializeCameraMediaControls() {
  syncCameraMediaControls();
  if (!cameraRecordingSupported()) {
    ui.cameraMediaHelp.textContent = '화면 캡처 가능 · 녹화는 canvas.captureStream 및 MediaRecorder 지원 브라우저가 필요합니다.';
  }
}

window.RobotScopeCameraFrame = Object.freeze({
  beginSource: noteCameraSource,
  draw: renderCameraSourceFrame,
  markRendered: markCameraFrameRendered,
});

function resetDecoder() {
  if (videoDecoder && videoDecoder.state !== 'closed') {
    try { videoDecoder.close(); } catch (_) {}
  }
  cameraHasKey = false;
  if (!('VideoDecoder' in window)) {
    ui.cameraEmptyText.textContent = '이 브라우저는 H.264 WebCodecs를 지원하지 않습니다.';
    return false;
  }
  videoDecoder = new VideoDecoder({
    output: renderVideoFrame,
    error: (error) => {
      console.warn('H264 decoder:', error);
      cameraHasKey = false;
    },
  });
  videoDecoder.configure({ codec: cameraMeta?.encoding || 'avc1.42E01E', optimizeForLatency: true });
  return true;
}

function renderVideoFrame(frame) {
  try {
    renderCameraSourceFrame(frame, frame.displayWidth, frame.displayHeight);
  } finally {
    frame.close();
  }
}

function renderImageBlob(data, metadata) {
  enqueueCameraImageFrame(data, metadata);
}

function renderRawImage(data, metadata) {
  const { width, height, encoding, step } = metadata;
  if (!width || !height || !['rgb8', 'bgr8', 'rgba8', 'bgra8', 'mono8'].includes(encoding)) return;
  const source = new Uint8Array(data);
  const canvas = ui.cameraCanvas;
  canvas.width = width; canvas.height = height;
  const ctx = canvas.getContext('2d');
  const image = ctx.createImageData(width, height);
  const channels = encoding === 'mono8' ? 1 : encoding.includes('rgba') ? 4 : 3;
  const rowStep = step || width * channels;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const src = y * rowStep + x * channels;
      const dst = (y * width + x) * 4;
      if (channels === 1) image.data[dst] = image.data[dst + 1] = image.data[dst + 2] = source[src];
      else {
        const bgr = encoding.startsWith('bgr');
        image.data[dst] = source[src + (bgr ? 2 : 0)];
        image.data[dst + 1] = source[src + 1];
        image.data[dst + 2] = source[src + (bgr ? 0 : 2)];
      }
      image.data[dst + 3] = 255;
    }
  }
  ctx.putImageData(image, 0, 0);
  markCameraFrameRendered(cameraMeta?.topic || cameraActiveSourceKey);
}

function markJointsStale(force = false) {
  if (!force && Date.now() - lastJointAt <= 1200) return;
  if (jointLive) scene3d?.resetRobotJointPositions?.();
  jointLive = false;
  latestBodyRpy = null;
  targetJointPositions = null;
  renderedJointPositions = null;
  poseImuAnchor = null;
  updateLiveModelBadge();
}

function applyJointSnapshot(snapshot) {
  if (!robotRuntimeDataCompatible || selectedRobotType !== 'go2') {
    if (jointLive || targetJointPositions || renderedJointPositions) markJointsStale(true);
    return;
  }
  const positions = snapshot?.position_rad;
  const validPositions = snapshot?.state === 'ok' && Array.isArray(positions) && positions.length === 12 && positions.every(Number.isFinite);
  if (!validPositions) {
    if (snapshot?.state === 'stale') markJointsStale(true);
    return;
  }
  lastJointAt = Date.now();
  jointLive = true;
  targetJointPositions = positions.slice();
  if (!renderedJointPositions) renderedJointPositions = positions.slice();
  const rpy = snapshot?.imu_rpy_rad;
  if (Array.isArray(rpy) && rpy.length === 3 && rpy.every(Number.isFinite)) {
    latestBodyRpy = rpy.slice(0, 3);
    // FAST-LIO starts camera_init yaw at zero and does not consume Unitree's
    // absolute IMU quaternion.  Only use the high-rate IMU yaw *delta* from
    // the latest Odometry anchor; the mapped roll/pitch/yaw basis remains the
    // full FAST-LIO quaternion.
    if (targetPose && poseImuAnchor) {
      targetPose = {
        ...targetPose,
        yaw: poseImuAnchor.odomYaw + angleDelta(rpy[2], poseImuAnchor.imuYaw),
      };
    }
  }
  updateLiveModelBadge();
}

function connectJoints() {
  if (jointSocket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(jointSocket.readyState)) return;
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  jointSocket = new WebSocket(`${scheme}//${location.host}/api/v1/ws/joints`);
  jointSocket.onmessage = (event) => {
    try { applyJointSnapshot(JSON.parse(event.data)); }
    catch (error) { console.warn('joint stream:', error); }
  };
  jointSocket.onclose = () => setTimeout(connectJoints, 1400);
  jointSocket.onerror = () => jointSocket.close();
}

function connectPose() {
  if (poseSocket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(poseSocket.readyState)) return;
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  poseSocket = new WebSocket(`${scheme}//${location.host}/api/v1/ws/pose`);
  poseSocket.onmessage = (event) => {
    try { applyPoseSnapshot(JSON.parse(event.data)); }
    catch (error) { console.warn('pose stream:', error); }
  };
  poseSocket.onclose = () => setTimeout(connectPose, 1200);
  poseSocket.onerror = () => poseSocket.close();
}

function connectCamera() {
  if (cameraSocket) cameraSocket.close();
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  cameraSocket = new WebSocket(`${scheme}//${location.host}/api/v1/ws/camera`);
  cameraSocket.binaryType = 'arraybuffer';
  cameraSocket.onmessage = (event) => {
    if (typeof event.data === 'string') {
      const metadata = JSON.parse(event.data);
      noteCameraSource(metadata.topic || metadata.source || metadata.stream_url || metadata.transport);
      cameraMeta = metadata;
      return;
    }
    if (!cameraMeta) return;
    const metadata = { ...cameraMeta };
    try {
      if (metadata.format === 'h264') {
        if (!videoDecoder || videoDecoder.state === 'closed') if (!resetDecoder()) return;
        if (metadata.key) cameraHasKey = true;
        if (!cameraHasKey) return;
        const chunk = new EncodedVideoChunk({
          type: metadata.key ? 'key' : 'delta',
          timestamp: Number(metadata.seq) * 33333,
          data: new Uint8Array(event.data),
        });
        if (videoDecoder.decodeQueueSize < 4) videoDecoder.decode(chunk);
      } else if (metadata.format === 'jpeg' || metadata.format === 'png') {
        renderImageBlob(event.data, metadata);
      } else if (metadata.format === 'raw') {
        renderRawImage(event.data, metadata);
      }
    } catch (error) {
      console.warn('camera render:', error);
      if (metadata.format === 'h264') resetDecoder();
    }
  };
  cameraSocket.onclose = () => setTimeout(connectCamera, 1800);
  cameraSocket.onerror = () => cameraSocket.close();
}

function controlReady(snapshot = controlSnapshot) {
  if (selectedRobotType !== 'go2') return false;
  const available = snapshot?.available ?? snapshot?.ready;
  return Boolean(snapshot?.enabled && snapshot?.configured && available);
}

function controlEstopLatched(snapshot = controlSnapshot) {
  return Boolean(snapshot?.estop_latched ?? snapshot?.estop?.latched);
}

function controlLimits() {
  const limits = controlSnapshot?.limits || {};
  return {
    max_linear_x: Math.max(0, Number(limits.max_linear_x ?? limits.vx_mps) || 0),
    max_linear_y: Math.max(0, Number(limits.max_linear_y ?? limits.vy_mps) || 0),
    max_angular_z: Math.max(0, Number(limits.max_angular_z ?? limits.wz_rps) || 0),
  };
}

function extractControlSnapshot(payload) {
  if (!payload || typeof payload !== 'object') return null;
  if (payload.control && typeof payload.control === 'object') return payload.control;
  if (Object.hasOwn(payload, 'enabled') && Object.hasOwn(payload, 'lease')) return payload;
  if (payload.snapshot && typeof payload.snapshot === 'object') return extractControlSnapshot(payload.snapshot);
  return null;
}

function actionList(snapshot = controlSnapshot) {
  const actions = snapshot?.actions;
  if (Array.isArray(actions)) return actions;
  if (actions && typeof actions === 'object') {
    return Object.entries(actions).map(([id, metadata]) => ({ id, ...(metadata || {}) }));
  }
  return [];
}

function normalizedBridgeState() {
  const bridge = controlSnapshot?.bridge || {};
  const state = String(bridge.state || (bridge.connected ? 'connected' : bridge.available ? 'ready' : 'waiting'));
  const ready = Boolean(bridge.connected || bridge.available || ['ready', 'connected', 'online', 'ok'].includes(state.toLowerCase()));
  return { bridge, state, ready };
}

function syncEstopClearButton() {
  controlUi.clear.disabled = selectedRobotType !== 'go2' || controlEmergencyBusy || !controlEstopLatched() || !controlUi.clearConfirm.checked || !controlUi.clearPin.value.trim();
}

function renderControlStatus() {
  const snapshot = controlSnapshot || {};
  const go2Profile = selectedRobotType === 'go2';
  const ready = controlReady(snapshot);
  const estopLatched = controlEstopLatched(snapshot);
  const serverLease = snapshot.lease || {};
  const locallyArmed = Boolean(controlLeaseId);
  const { bridge, state: bridgeState, ready: bridgeReady } = normalizedBridgeState();
  const availabilityCard = controlUi.availability.closest('.control-status-card');
  const leaseCard = controlUi.leaseState.closest('.control-status-card');
  const bridgeCard = controlUi.bridgeState.closest('.control-status-card');

  availabilityCard.classList.toggle('is-ok', ready);
  availabilityCard.classList.toggle('is-error', !go2Profile || snapshot.enabled === false || snapshot.configured === false);
  controlUi.availability.textContent = !go2Profile ? 'GO2 ONLY' : ready ? 'AVAILABLE' : snapshot.enabled === false ? 'DISABLED' : snapshot.configured === false ? 'NOT CONFIGURED' : 'UNAVAILABLE';
  controlUi.availabilityNote.textContent = !go2Profile ? `${activeRobotProfile()?.label || '선택 로봇'} 제어는 아직 지원하지 않음` : snapshot.state || (ready ? '제어 서버 준비 완료' : '서버 설정 또는 로봇 연결 확인');

  leaseCard.classList.toggle('is-ok', locallyArmed && serverLease.active !== false);
  leaseCard.classList.toggle('is-error', Boolean(serverLease.active && !locallyArmed));
  controlUi.leaseState.textContent = locallyArmed ? (serverLease.bound ? 'BOUND' : 'ARMED') : serverLease.active ? 'IN USE' : 'DISARMED';
  controlUi.leaseNote.textContent = locallyArmed ? `${controlLeaseSource.toUpperCase()} · 이 브라우저` : serverLease.active ? `${String(serverLease.source || serverLease.input_source || 'other').toUpperCase()} 제어 중` : '명령 권한 없음';

  bridgeCard.classList.toggle('is-ok', go2Profile && bridgeReady);
  bridgeCard.classList.toggle('is-error', ['error', 'offline', 'failed'].includes(bridgeState.toLowerCase()));
  controlUi.bridgeState.textContent = bridgeState.toUpperCase();
  controlUi.bridgeNote.textContent = !go2Profile ? 'Go2 유형 선택 시에만 사용' : bridge.message || bridge.detail || (bridgeReady ? 'Go2 명령 브리지 준비' : 'Go2 연결 대기');

  controlUi.estopStatusCard.classList.toggle('is-latched', estopLatched);
  controlUi.estopState.textContent = estopLatched ? 'LATCHED' : 'CLEAR';
  controlUi.estopNote.textContent = estopLatched ? 'PIN 확인 전까지 ARM 불가' : '대시보드 정지 해제 상태';

  if (estopLatched) setStatePill(controlUi.statePill, 'error', 'SOFTWARE STOP');
  else if (locallyArmed) setStatePill(controlUi.statePill, 'ok', serverLease.bound ? 'ARMED · BOUND' : 'ARMED · BINDING');
  else setStatePill(controlUi.statePill, ready ? 'waiting' : 'error', ready ? 'DISARMED' : 'UNAVAILABLE');

  controlUi.arm.disabled = controlArmBusy || controlDisarmBusy || locallyArmed || !ready || estopLatched;
  controlUi.disarm.disabled = controlDisarmBusy || !locallyArmed;
  controlUi.inputSource.setAttribute('aria-disabled', locallyArmed ? 'true' : 'false');
  controlUi.estop.disabled = controlEmergencyBusy || !go2Profile;
  syncEstopClearButton();
  renderControlInputMode();
  renderControlActions();
}

function renderControlInputMode() {
  const source = controlUi.inputSource.value;
  const gamepadMode = source === 'gamepad';
  const locallyArmed = Boolean(controlLeaseId);
  controlUi.gamepadWrap.classList.toggle('is-hidden', !gamepadMode);
  controlUi.keyboardGuide.classList.toggle('is-hidden', gamepadMode);
  controlUi.gamepadGuide.classList.toggle('is-hidden', !gamepadMode);
  controlUi.touchController.classList.toggle('is-hidden', gamepadMode);
  controlUi.touchController.querySelectorAll('button').forEach((button) => { button.disabled = !locallyArmed || gamepadMode; });

  if (gamepadMode) {
    const pad = selectedControlGamepad();
    controlUi.deviceIndicator.className = `device-indicator ${pad ? 'is-ok' : 'is-error'}`;
    controlUi.deviceStatus.textContent = pad ? `${pad.id} 연결됨` : '선택한 게임패드 연결 끊김';
  } else {
    controlUi.deviceIndicator.className = 'device-indicator is-ok';
    controlUi.deviceStatus.textContent = locallyArmed ? '키보드·화면 버튼 제어 활성' : '키보드 입력 준비';
  }
}

function actionNeedsConfirmation(action) {
  return Boolean(action.requires_confirmation ?? action.confirmation_required ?? action.dangerous ?? true);
}

function renderControlActions() {
  const focusedAction = document.activeElement?.dataset?.controlAction || '';
  const actions = actionList();
  if (!actions.length) {
    controlUi.actions.innerHTML = '<div class="control-action-empty">서버에서 허용한 모션이 없습니다.</div>';
    return;
  }
  const armed = Boolean(controlLeaseId) && !controlEstopLatched() && !controlHadDeadman && !controlActionBusy;
  const now = Date.now();
  if (actionConfirmation && actionConfirmation.expires <= now) actionConfirmation = null;
  controlUi.actions.innerHTML = actions.map((action) => {
    const id = String(action.action_id ?? (typeof action.id === 'string' ? action.id : action.name ?? action.id ?? ''));
    const confirming = actionConfirmation?.id === id && actionConfirmation.expires > now;
    const enabled = armed && action.enabled !== false && action.available !== false;
    const needsConfirmation = actionNeedsConfirmation(action);
    const buttonLabel = confirming ? '다시 눌러 실행 확인' : action.button_label || action.buttonLabel || '실행';
    return `<article class="control-action-card">
      <span>${escapeHtml(action.category || action.group || action.type || 'GO2 ACTION')}</span>
      <strong>${escapeHtml(action.label || action.name || id)}</strong>
      <small>${escapeHtml(action.description || action.note || '서버 허용 목록에 등록된 Go2 동작입니다.')}</small>
      <button type="button" data-control-action="${escapeHtml(id)}" data-confirm="${needsConfirmation ? 'true' : 'false'}" class="${confirming ? 'is-confirming' : ''}" ${enabled ? '' : 'disabled'}>${escapeHtml(buttonLabel)}</button>
    </article>`;
  }).join('');
  if (focusedAction) {
    requestAnimationFrame(() => {
      Array.from(controlUi.actions.querySelectorAll('[data-control-action]'))
        .find((button) => button.dataset.controlAction === focusedAction)?.focus({ preventScroll: true });
    });
  }
}

function commandNumber(value) {
  const number = Number(value) || 0;
  return `${number >= 0 ? '+' : ''}${number.toFixed(3)}`;
}

function renderControlCommand(command = controlLastCommand || controlSnapshot?.command || controlInput?.zeroCommand(controlUi.inputSource.value)) {
  if (!command) return;
  const limits = controlLimits();
  const x = Number(command.linear_x) || 0;
  const y = Number(command.linear_y) || 0;
  const z = Number(command.angular_z) || 0;
  controlUi.commandX.textContent = commandNumber(x);
  controlUi.commandY.textContent = commandNumber(y);
  controlUi.commandZ.textContent = commandNumber(z);
  controlUi.commandXBar.style.width = `${Math.min(100, Math.abs(x) / (limits.max_linear_x || 1) * 100)}%`;
  controlUi.commandYBar.style.width = `${Math.min(100, Math.abs(y) / (limits.max_linear_y || 1) * 100)}%`;
  controlUi.commandZBar.style.width = `${Math.min(100, Math.abs(z) / (limits.max_angular_z || 1) * 100)}%`;
  controlUi.deadmanState.textContent = command.deadman ? 'HELD' : 'RELEASED';
  controlUi.deadmanMonitor.classList.toggle('is-active', Boolean(command.deadman));
  controlUi.commandSource.textContent = command.deadman ? `${String(command.source || controlLeaseSource || 'input').toUpperCase()} · LIVE` : 'ZERO COMMAND';
}

function applyControlSnapshot(snapshot) {
  if (!snapshot) return;
  controlSnapshot = snapshot;
  if (!controlSpeedInitialized) {
    const percent = controlInput.clamp(Number(snapshot.limits?.default_speed_scale) || 0.3, 0.1, 1) * 100;
    controlUi.speed.value = String(Math.round(percent / 5) * 5);
    controlSpeedInitialized = true;
  }
  controlUi.speedOutput.textContent = `${controlUi.speed.value}%`;
  renderControlStatus();
  if (!controlLeaseId) renderControlCommand(snapshot.command);
}

async function refreshControlSnapshot() {
  if (activePage !== 'controls') return;
  try {
    const snapshot = extractControlSnapshot(await api('/api/v1/control'));
    applyControlSnapshot(snapshot);
    if (controlLeaseId && snapshot?.lease?.active === false && !controlDisarmBusy) {
      await failSafeDisarm('lease_expired', { notify: true });
    }
  } catch (error) {
    controlUi.availability.textContent = 'API ERROR';
    controlUi.availabilityNote.textContent = error.message;
    controlUi.availability.closest('.control-status-card').classList.add('is-error');
  }
}

function selectedControlGamepad() {
  if (!navigator.getGamepads || selectedGamepadIndex === '') return null;
  return Array.from(navigator.getGamepads()).find((pad) => pad?.mapping === 'standard' && String(pad.index) === String(selectedGamepadIndex)) || null;
}

function refreshControlGamepads() {
  if (!navigator.getGamepads) return;
  const detectedPads = Array.from(navigator.getGamepads()).filter(Boolean);
  const pads = detectedPads.filter((pad) => pad.mapping === 'standard');
  const previous = selectedGamepadIndex || controlUi.gamepad.value;
  controlUi.gamepad.innerHTML = pads.length
    ? pads.map((pad) => `<option value="${pad.index}">${escapeHtml(pad.id || `Gamepad ${pad.index + 1}`)}</option>`).join('')
    : `<option value="">${detectedPads.length ? '표준 매핑 장치 없음' : '연결된 장치 없음'}</option>`;
  const stillPresent = pads.some((pad) => String(pad.index) === String(previous));
  const selectedDisconnected = previous !== '' && !stillPresent;
  selectedGamepadIndex = stillPresent ? String(previous) : pads.length ? String(pads[0].index) : '';
  controlUi.gamepad.value = selectedGamepadIndex;
  renderControlInputMode();
  if (controlLeaseId && controlLeaseSource === 'gamepad' && (selectedDisconnected || !selectedControlGamepad())) {
    failSafeDisarm('gamepad_disconnected', { notify: true });
  }
}

function controlSocketSend(message, socket = controlSocket) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return false;
  const queuedBytes = Number(socket.bufferedAmount);
  if (!Number.isFinite(queuedBytes) || queuedBytes !== 0 || queuedBytes > CONTROL_SOCKET_MAX_BUFFER_BYTES) {
    if (!controlDisarmBusy) failSafeDisarm('websocket_backpressure', { notify: true });
    return false;
  }
  try { socket.send(JSON.stringify(message)); return true; }
  catch (_) {
    if (!controlDisarmBusy) failSafeDisarm('websocket_send_failed', { notify: true });
    return false;
  }
}

function clearPendingControlAction(render = true) {
  if (controlActionAckTimer) clearTimeout(controlActionAckTimer);
  controlActionAckTimer = null;
  controlActionBusy = false;
  pendingControlActionId = '';
  actionConfirmation = null;
  if (render) renderControlActions();
}

function zeroTwistMessage(leaseId = controlLeaseId, source = controlLeaseSource || controlUi.inputSource.value) {
  return {
    type: 'twist', lease_id: leaseId, seq: ++controlSequence, source,
    deadman: false, linear_x: 0, linear_y: 0, angular_z: 0,
    speed_scale: Number(controlUi.speed.value) / 100, client_time_ms: Date.now(),
  };
}

function sendImmediateZero(leaseId = controlLeaseId, source = controlLeaseSource) {
  if (!leaseId) return;
  controlSocketSend(zeroTwistMessage(leaseId, source));
  controlLastCommand = controlInput.zeroCommand(source || 'keyboard');
  renderControlCommand(controlLastCommand);
}

function closeControlSocket(reason = 'client_close') {
  const socket = controlSocket;
  controlSocket = null;
  controlSocketBound = false;
  clearPendingControlAction(false);
  if (!socket) return;
  intentionallyClosedControlSockets.add(socket);
  try { socket.close(1000, reason.slice(0, 90)); } catch (_) {}
}

function connectControlSocket() {
  if (activePage !== 'controls' || !controlLeaseId) return;
  if (controlSocket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(controlSocket.readyState)) return;
  const leaseAtConnect = controlLeaseId;
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(`${scheme}//${location.host}/api/v1/ws/control`);
  controlSocket = socket;
  controlSocketBound = false;
  socket.onopen = () => {
    if (activePage !== 'controls' || controlLeaseId !== leaseAtConnect) {
      intentionallyClosedControlSockets.add(socket);
      socket.close(1000, 'inactive_control_page');
      return;
    }
    controlSocketSend({ type: 'bind', lease_id: leaseAtConnect, client_time_ms: Date.now() }, socket);
    lastControlHeartbeatAt = Date.now();
  };
  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === 'error') {
        clearPendingControlAction();
        showToast(`제어 스트림 오류: ${payload.detail || payload.message || 'unknown'}`, true);
        failSafeDisarm('websocket_server_error');
        return;
      }
      if (payload.type === 'bound') {
        controlSocketBound = true;
        applyControlSnapshot(extractControlSnapshot(payload));
        return;
      }
      if (payload.type === 'action_accepted') {
        const acceptedAction = pendingControlActionId || payload.action_id || payload.action || 'Go2';
        const acceptedSnapshot = extractControlSnapshot(payload);
        controlLeaseId = '';
        controlLeaseSource = '';
        clearPendingControlAction(false);
        resetControlInputs();
        // Do not send zero/release after an accepted one-shot action: either
        // frame could cancel it. Closing the socket intentionally makes the
        // next browser command require a completely new ARM.
        closeControlSocket('action_accepted');
        if (acceptedSnapshot) {
          controlSnapshot = {
            ...acceptedSnapshot,
            lease: { ...(acceptedSnapshot.lease || {}), active: false, bound: false, source: null },
          };
        }
        renderControlStatus();
        showToast(`${acceptedAction} 대시보드 명령 접수 · 브리지 수신/실행 완료 신호가 아닙니다. 안전 대기 종료 후 다시 ARM하세요.`);
        setTimeout(() => refreshControlSnapshot(), 400);
        return;
      }
      applyControlSnapshot(extractControlSnapshot(payload));
    } catch (error) { console.warn('control stream:', error); }
  };
  socket.onerror = () => { try { socket.close(); } catch (_) {} };
  socket.onclose = () => {
    if (controlSocket === socket) {
      controlSocket = null;
      controlSocketBound = false;
    }
    if (intentionallyClosedControlSockets.has(socket)) return;
    // A lost command stream is a terminal lease event: do not auto re-arm.
    if (controlLeaseId === leaseAtConnect) failSafeDisarm('websocket_closed', { notify: true });
  };
}

function resetControlInputs() {
  controlPressedKeys.clear();
  controlPointerDirections.clear();
  controlDeadmanPointers.clear();
  controlHadDeadman = false;
  document.querySelectorAll('.keyboard-guide kbd.is-pressed, .touch-dpad button.is-pressed').forEach((element) => element.classList.remove('is-pressed'));
  controlLastCommand = controlInput.zeroCommand(controlLeaseSource || controlUi.inputSource.value);
  renderControlCommand(controlLastCommand);
}

async function failSafeDisarm(reason, { notify = false } = {}) {
  if (controlDisarmBusy) return;
  const leaseId = controlLeaseId;
  const source = controlLeaseSource;
  if (!leaseId) {
    closeControlSocket(reason);
    resetControlInputs();
    renderControlStatus();
    return;
  }
  controlDisarmBusy = true;
  sendImmediateZero(leaseId, source);
  controlSocketSend({ type: 'release', lease_id: leaseId, reason, client_time_ms: Date.now() });
  controlLeaseId = '';
  controlLeaseSource = '';
  closeControlSocket(reason);
  resetControlInputs();
  renderControlStatus();
  try {
    await api('/api/v1/control/disarm', { method: 'POST', keepalive: true, body: JSON.stringify({ lease_id: leaseId }) });
    if (notify) showToast('안전 해제: 제로 명령 후 제어 권한을 반납했습니다.');
  } catch (error) {
    if (notify) showToast(`제어 해제 확인 실패: ${error.message}`, true);
  } finally {
    controlDisarmBusy = false;
    if (activePage === 'controls') await refreshControlSnapshot();
  }
}

function invalidatePendingArm() {
  controlArmGeneration += 1;
  controlArmBusy = false;
}

async function armControl() {
  if (controlLeaseId || controlDisarmBusy || controlArmBusy) return;
  const source = controlUi.inputSource.value;
  const pin = controlUi.pin.value.trim();
  if (!pin) { showToast('제어 PIN을 입력하세요.', true); controlUi.pin.focus(); return; }
  if (source === 'gamepad' && !selectedControlGamepad()) { showToast('연결된 게임패드를 선택하세요.', true); return; }
  const armGeneration = ++controlArmGeneration;
  controlArmBusy = true;
  renderControlStatus();
  try {
    const response = await api('/api/v1/control/arm', {
      method: 'POST', body: JSON.stringify({ pin, input_source: source }),
    });
    if (!response.lease_id) throw new Error('서버가 lease_id를 반환하지 않았습니다.');
    if (armGeneration !== controlArmGeneration || activePage !== 'controls') {
      try {
        await api('/api/v1/control/disarm', {
          method: 'POST', keepalive: true, body: JSON.stringify({ lease_id: String(response.lease_id) }),
        });
      } catch (_) {}
      return;
    }
    controlLeaseId = String(response.lease_id);
    controlLeaseSource = source;
    controlSequence = -1;
    controlUi.pin.value = '';
    resetControlInputs();
    applyControlSnapshot(extractControlSnapshot(response));
    connectControlSocket();
    renderControlStatus();
    showToast(`${source === 'gamepad' ? '게임패드' : '키보드'} 제어를 ARM했습니다. 데드맨을 계속 누르세요.`);
  } catch (error) {
    if (armGeneration === controlArmGeneration) showToast(`ARM 실패: ${error.message}`, true);
  } finally {
    if (armGeneration === controlArmGeneration) controlArmBusy = false;
    renderControlStatus();
  }
}

function currentRawControlCommand() {
  if (controlLeaseSource === 'gamepad') return controlInput.gamepadCommand(selectedControlGamepad());
  const keyboard = controlInput.keyboardCommand(controlPressedKeys);
  const pointer = controlInput.pointerCommand(
    new Set(controlPointerDirections.values()),
    controlDeadmanPointers.size > 0 || keyboard.deadman,
  );
  if (keyboard.deadman && pointer.deadman) {
    return {
      source: 'keyboard', deadman: true,
      linear_x: controlInput.clamp(keyboard.linear_x + pointer.linear_x),
      linear_y: controlInput.clamp(keyboard.linear_y + pointer.linear_y),
      angular_z: controlInput.clamp(keyboard.angular_z + pointer.angular_z),
    };
  }
  return keyboard.deadman ? keyboard : pointer;
}

function controlTick() {
  if (activePage !== 'controls') return;
  const estopPad = controlUi.inputSource.value === 'gamepad' ? selectedControlGamepad() : null;
  const estopPressed = Boolean(estopPad && controlInput.gamepadButtonPressed(estopPad, 1));
  if (estopPressed && !gamepadEstopPressed) {
    gamepadEstopPressed = true;
    triggerEmergencyStop('gamepad_b');
    return;
  }
  gamepadEstopPressed = estopPressed;
  if (!controlLeaseId || controlActionBusy) return;
  if (controlLeaseSource === 'gamepad') {
    const pad = selectedControlGamepad();
    if (!pad) { failSafeDisarm('gamepad_disconnected', { notify: true }); return; }
  }
  const raw = currentRawControlCommand();
  if (controlHadDeadman && !raw.deadman) {
    failSafeDisarm('deadman_released', { notify: true });
    return;
  }
  if (raw.deadman && !controlHadDeadman) {
    controlHadDeadman = true;
    renderControlActions();
  }
  const speedScale = Number(controlUi.speed.value) / 100;
  const scaled = controlInput.scaleCommand(raw, controlLimits(), speedScale);
  controlLastCommand = scaled;
  renderControlCommand(scaled);
  if (controlSocketBound && controlSocket?.readyState === WebSocket.OPEN) {
    if (Date.now() - lastControlHeartbeatAt >= 1000) {
      const heartbeatSent = controlSocketSend({
        type: 'heartbeat', lease_id: controlLeaseId, seq: ++controlSequence,
        client_time_ms: Date.now(),
      });
      if (heartbeatSent) lastControlHeartbeatAt = Date.now();
      return;
    }
    if (!raw.deadman && !controlHadDeadman) return;
    controlSocketSend({
      type: 'twist', lease_id: controlLeaseId, seq: ++controlSequence,
      source: controlLeaseSource, deadman: raw.deadman,
      linear_x: raw.linear_x, linear_y: raw.linear_y, angular_z: raw.angular_z,
      speed_scale: speedScale, client_time_ms: Date.now(),
    });
  }
}

async function triggerEmergencyStop(reason = 'dashboard_button') {
  if (controlEmergencyBusy) return;
  invalidatePendingArm();
  controlEmergencyBusy = true;
  const leaseId = controlLeaseId;
  const source = controlLeaseSource;
  sendImmediateZero(leaseId, source);
  if (leaseId) controlSocketSend({ type: 'release', lease_id: leaseId, reason: 'software_estop', client_time_ms: Date.now() });
  controlLeaseId = '';
  controlLeaseSource = '';
  closeControlSocket('software_estop');
  resetControlInputs();
  renderControlStatus();
  try {
    await api('/api/v1/control/stop', { method: 'POST', body: JSON.stringify({ reason }) });
    if (leaseId) {
      try { await api('/api/v1/control/disarm', { method: 'POST', body: JSON.stringify({ lease_id: leaseId }) }); } catch (_) {}
    }
    showToast('대시보드 SOFTWARE STOP 명령을 전송했습니다. 물리 E-stop은 아닙니다.', true);
  } catch (error) {
    showToast(`대시보드 정지 전송 실패: ${error.message}`, true);
  } finally {
    controlEmergencyBusy = false;
    if (activePage === 'controls') await refreshControlSnapshot();
  }
}

async function clearEmergencyStop() {
  const pin = controlUi.clearPin.value.trim();
  if (!pin || !controlUi.clearConfirm.checked) return;
  controlEmergencyBusy = true;
  syncEstopClearButton();
  try {
    const response = await api('/api/v1/control/estop/clear', {
      method: 'POST', body: JSON.stringify({ pin, confirmed: true }),
    });
    controlUi.clearPin.value = '';
    controlUi.clearConfirm.checked = false;
    applyControlSnapshot(extractControlSnapshot(response));
    showToast('대시보드 SOFTWARE STOP 래치를 해제했습니다. 제어하려면 다시 ARM하세요.');
  } catch (error) {
    showToast(`대시보드 정지 해제 실패: ${error.message}`, true);
  } finally {
    controlEmergencyBusy = false;
    syncEstopClearButton();
    if (activePage === 'controls') await refreshControlSnapshot();
  }
}

function invokeControlAction(id, confirmed) {
  if (!controlLeaseId) { showToast('먼저 제어를 ARM하세요.', true); return; }
  if (controlActionBusy) return;
  if (controlHadDeadman) {
    showToast('주행에 사용한 ARM은 안전 해제 후, 모션 실행용으로 다시 ARM하세요.', true);
    return;
  }
  if (!controlSocketBound || !controlSocket || controlSocket.readyState !== WebSocket.OPEN) {
    showToast('제어 소켓 바인딩이 완료되지 않아 동작을 실행할 수 없습니다.', true);
    failSafeDisarm('action_socket_unavailable');
    return;
  }
  controlActionBusy = true;
  pendingControlActionId = id;
  actionConfirmation = null;
  renderControlActions();
  const sent = controlSocketSend({
    type: 'action', lease_id: controlLeaseId, seq: ++controlSequence,
    action_id: id, confirmed: Boolean(confirmed), client_time_ms: Date.now(),
  });
  if (!sent) {
    clearPendingControlAction();
    failSafeDisarm('action_send_failed', { notify: true });
    return;
  }
  controlActionAckTimer = setTimeout(() => {
    clearPendingControlAction();
    failSafeDisarm('action_ack_timeout', { notify: true });
  }, 1200);
}

function handleControlActionClick(event) {
  const button = event.target.closest('[data-control-action]');
  if (!button || button.disabled) return;
  const id = button.dataset.controlAction;
  if (button.dataset.confirm === 'true') {
    const now = Date.now();
    if (actionConfirmation?.id !== id || actionConfirmation.expires <= now) {
      actionConfirmation = { id, expires: now + 3500 };
      renderControlActions();
      setTimeout(() => {
        if (actionConfirmation?.id === id && actionConfirmation.expires <= Date.now()) {
          actionConfirmation = null;
          renderControlActions();
        }
      }, 3600);
      return;
    }
  }
  invokeControlAction(id, button.dataset.confirm === 'true');
}

function isFormControlTarget(target) {
  return Boolean(target?.closest?.('input, select, textarea, button, [contenteditable="true"]'));
}

function updateKeyboardGuide() {
  const keyMap = { KeyQ: 0, KeyW: 1, KeyE: 2, KeyA: 3, KeyS: 4, KeyD: 5 };
  const keys = Array.from(controlUi.keyboardGuide.querySelectorAll('.key-row kbd'));
  Object.entries(keyMap).forEach(([code, index]) => keys[index]?.classList.toggle('is-pressed', controlPressedKeys.has(code)));
  controlUi.keyboardGuide.querySelector('.shift-key kbd')?.classList.toggle('is-pressed', controlPressedKeys.has('ShiftLeft') || controlPressedKeys.has('ShiftRight'));
}

function handleControlKeyDown(event) {
  if (activePage !== 'controls' || controlLeaseSource !== 'keyboard' || !controlLeaseId || isFormControlTarget(event.target) || !controlInput.isControlCode(event.code)) return;
  event.preventDefault();
  controlPressedKeys.add(event.code);
  updateKeyboardGuide();
}

function handleControlKeyUp(event) {
  if (!controlInput.isControlCode(event.code) || !controlPressedKeys.has(event.code)) return;
  controlPressedKeys.delete(event.code);
  updateKeyboardGuide();
  if (controlLeaseId && controlLeaseSource === 'keyboard') {
    failSafeDisarm('keyboard_key_released', { notify: true });
  }
}

function releaseControlPointer(event) {
  const button = event.currentTarget;
  const wasDirection = controlPointerDirections.delete(event.pointerId);
  const wasDeadman = controlDeadmanPointers.delete(event.pointerId);
  button.classList.remove('is-pressed');
  if ((wasDirection || wasDeadman) && controlLeaseId) {
    failSafeDisarm(wasDeadman ? 'pointer_deadman_released' : 'pointer_direction_released', { notify: true });
  }
}

function bindControlPointerButtons() {
  controlUi.touchController.querySelectorAll('[data-control-direction], [data-control-deadman]').forEach((button) => {
    button.addEventListener('pointerdown', (event) => {
      if (!controlLeaseId || controlLeaseSource !== 'keyboard') return;
      event.preventDefault();
      try { button.setPointerCapture(event.pointerId); } catch (_) {}
      if (button.dataset.controlDirection) controlPointerDirections.set(event.pointerId, button.dataset.controlDirection);
      else controlDeadmanPointers.add(event.pointerId);
      button.classList.add('is-pressed');
    });
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach((name) => button.addEventListener(name, releaseControlPointer));
  });
}

function enterControlPage() {
  refreshControlGamepads();
  refreshControlSnapshot();
  if (controlLeaseId) connectControlSocket();
}

function leaveControlPage(reason = 'controls_page_left') {
  invalidatePendingArm();
  if (controlLeaseId) failSafeDisarm(reason);
  else closeControlSocket(reason);
  resetControlInputs();
}

async function setRobotIp() {
  if (robotConnectionBusy) return;
  robotConnectionBusy = true;
  ui.connectButton.disabled = true;
  ui.connectButton.textContent = '확인 중…';
  try {
    const ip = ui.robotIp.value.trim();
    const candidate = selectedRobotCandidate?.ip === ip ? selectedRobotCandidate : null;
    const payload = window.RobotProfiles.connectionPayload(activeRobotProfile(), candidate, ip);
    const response = await api('/api/v1/robot', { method: 'POST', body: JSON.stringify(payload) });
    if (response.robot?.changed) resetLiveRobotSessionView();
    robotRuntimeDataCompatible = !Boolean(response.robot?.restart_required)
      && (!response.robot_type || response.robot_type === selectedRobotType);
    robotTypeDirty = false;
    robotIpDirty = false;
    if (response.robot_type && response.robot_type !== selectedRobotType) activateRobotType(response.robot_type);
    const restartNote = response.robot?.restart_required
      ? ' DDS 재연결을 위해 해당 프로필로 대시보드를 다시 시작해야 하며, 그 전에는 Go2 제어가 차단됩니다.'
      : ' ROS 연결 설정은 별도로 확인하세요.';
    showToast(`${activeRobotProfile()?.label || '로봇'} 표시·확인 대상을 변경했습니다.${restartNote}`);
    await refreshState();
  } catch (error) {
    showToast(`IP 변경 실패: ${error.message}`, true);
  } finally {
    robotConnectionBusy = false;
    ui.connectButton.disabled = false;
    ui.connectButton.textContent = '연결';
  }
}

function startClock() {
  const tick = () => { $('#clock').textContent = new Date().toLocaleTimeString('ko-KR', { hour12: false }); };
  tick(); setInterval(tick, 1000);
}

$('#connectButton').addEventListener('click', setRobotIp);
ui.robotType.addEventListener('change', () => activateRobotType(ui.robotType.value, { discover: true, dirty: true }));
ui.discoverRobotsButton.addEventListener('click', discoverRobots);
ui.robotIp.addEventListener('input', () => {
  robotIpDirty = true;
  if (selectedRobotCandidate?.ip === ui.robotIp.value.trim()) return;
  selectedRobotCandidate = null;
  ui.robotDiscoveryResults.querySelectorAll('.robot-candidate').forEach((button) => {
    button.classList.remove('is-selected');
    button.setAttribute('aria-pressed', 'false');
  });
});
ui.robotIp.addEventListener('keydown', (event) => { if (event.key === 'Enter') setRobotIp(); });
$('#refreshButton').addEventListener('click', async () => { await Promise.all([refreshState(), refreshTopics(), refreshSources(), refreshMappingControl(), refreshControlSnapshot()]); showToast('대시보드를 갱신했습니다.'); });
ui.mappingStartButton.addEventListener('click', startMappingSession);
ui.mappingSaveButton.addEventListener('click', saveMappingSession);
ui.mappingStopButton.addEventListener('click', stopMappingSession);
ui.cameraSource.addEventListener('change', () => {
  resetCameraRenderedFrame(ui.cameraSource.value, { reason: '카메라 소스를 변경하여 새 프레임을 기다리고 있습니다.' });
  selectSource('camera', ui.cameraSource.value);
});
ui.cloudSource.addEventListener('change', () => {
  if (ui.cloudSource.value) chooseMapView('cloud');
  resetLiveCloudAccumulator();
  lastCloudSnapshot = null;
  pointcloudRequestGeneration += 1;
  cloudSeq = -1;
  selectSource('pointcloud', ui.cloudSource.value);
});
ui.odomSource.addEventListener('change', () => selectSource('odometry', ui.odomSource.value));
ui.mapSource.addEventListener('change', () => {
  if (ui.mapSource.value) chooseMapView('occupancy');
  mapSeq = -1;
  selectSource('occupancy_grid', ui.mapSource.value);
});
ui.mapViewMode.addEventListener('change', () => chooseMapView(ui.mapViewMode.value));
ui.livePointBudget.addEventListener('change', async () => {
  const value = ui.livePointBudget.value;
  ui.livePointCustomWrap.classList.toggle('is-hidden', value !== 'custom');
  if (value === 'custom') {
    ui.livePointCustom.focus();
    return;
  }
  if (value === 'all' && !window.confirm('ALL SESSION은 브라우저 세션 동안 수신한 모든 점을 누적하므로 메모리와 렌더링 부하가 커질 수 있습니다. 계속할까요?')) {
    syncPointBudgetControl(ui.livePointBudget, ui.livePointCustomWrap, ui.livePointCustom, livePointLimit);
    return;
  }
  await applyLivePointLimit(value);
});
ui.livePointApply.addEventListener('click', () => applyLivePointLimit(ui.livePointCustom.value));
ui.livePointCustom.addEventListener('keydown', (event) => { if (event.key === 'Enter') applyLivePointLimit(ui.livePointCustom.value); });
ui.mapOverlayToggle.addEventListener('change', () => {
  mapOverlayVisible = ui.mapOverlayToggle.checked;
  redrawActiveMap();
});
ui.savedMapViewMode.addEventListener('change', () => chooseSavedMapView(ui.savedMapViewMode.value));
ui.savedPointBudget.addEventListener('change', async () => {
  const value = ui.savedPointBudget.value;
  ui.savedPointCustomWrap.classList.toggle('is-hidden', value !== 'custom');
  if (value === 'custom') {
    ui.savedPointCustom.focus();
    return;
  }
  await applySavedPointLimit(value);
});
ui.savedPointApply.addEventListener('click', () => applySavedPointLimit(ui.savedPointCustom.value));
ui.savedPointCustom.addEventListener('keydown', (event) => { if (event.key === 'Enter') applySavedPointLimit(ui.savedPointCustom.value); });
ui.savedMapOverlayToggle.addEventListener('change', () => {
  savedMapOverlayVisible = ui.savedMapOverlayToggle.checked;
  redrawSavedMap();
});
ui.savedMapList.addEventListener('click', (event) => {
  if (savedMapMutationBusy) return;
  const button = event.target.closest('[data-saved-map-id]');
  if (button) selectSavedMap(button.dataset.savedMapId);
});
ui.savedMapRenameButton.addEventListener('click', renameSelectedSavedMap);
ui.savedMapDeleteButton.addEventListener('click', deleteSelectedSavedMap);
ui.savedMapNameInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') renameSelectedSavedMap(); });
ui.topicSearch.addEventListener('input', renderTopics);
ui.categoryFilter.addEventListener('change', renderTopics);
ui.cameraCaptureButton.addEventListener('click', captureCameraFrame);
ui.cameraRecordButton.addEventListener('click', startCameraRecording);
ui.cameraStopRecordButton.addEventListener('click', () => stopCameraRecording());
controlUi.arm.addEventListener('click', armControl);
controlUi.disarm.addEventListener('click', () => failSafeDisarm('manual_disarm', { notify: true }));
controlUi.pin.addEventListener('keydown', (event) => { if (event.key === 'Enter') armControl(); });
controlUi.inputSource.addEventListener('change', () => {
  invalidatePendingArm();
  if (controlLeaseId) failSafeDisarm('input_source_changed', { notify: true });
  resetControlInputs();
  renderControlInputMode();
});
controlUi.gamepad.addEventListener('change', () => {
  invalidatePendingArm();
  if (controlLeaseId) failSafeDisarm('gamepad_selection_changed', { notify: true });
  selectedGamepadIndex = controlUi.gamepad.value;
  resetControlInputs();
  renderControlInputMode();
});
controlUi.speed.addEventListener('input', () => {
  controlUi.speedOutput.textContent = `${controlUi.speed.value}%`;
});
controlUi.estop.addEventListener('click', () => triggerEmergencyStop('dashboard_button'));
controlUi.clearPin.addEventListener('input', syncEstopClearButton);
controlUi.clearConfirm.addEventListener('change', syncEstopClearButton);
controlUi.clear.addEventListener('click', clearEmergencyStop);
controlUi.actions.addEventListener('click', handleControlActionClick);
document.addEventListener('keydown', handleControlKeyDown);
document.addEventListener('keyup', handleControlKeyUp);
window.addEventListener('gamepadconnected', refreshControlGamepads);
window.addEventListener('gamepaddisconnected', refreshControlGamepads);
window.addEventListener('blur', () => {
  if (controlArmBusy) invalidatePendingArm();
  if (controlLeaseId) failSafeDisarm('window_blurred');
});
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) return;
  if (controlArmBusy) invalidatePendingArm();
  if (controlLeaseId) failSafeDisarm('document_hidden');
  if (cameraRecording) stopCameraRecording(cameraRecordingCleanupPolicy('visibility_hidden'));
});
window.addEventListener('pagehide', () => {
  if (controlArmBusy) invalidatePendingArm();
  if (controlLeaseId) failSafeDisarm('page_hidden');
  discardCameraRecordingForPageHide();
});
window.addEventListener('hashchange', () => activatePage(pageFromHash()));
window.addEventListener('resize', () => {
  if (activePage === 'mapping') redrawActiveMap();
  if (activePage === 'maps') redrawSavedMap();
});

startClock();
initializeCameraMediaControls();
bindControlPointerButtons();
refreshControlGamepads();
renderControlStatus();
renderControlCommand();
activatePage(pageFromHash(), true);
ui.mappingSessionName.value = generatedMapName();
initializeRobotProfiles();
connectCamera();
connectJoints();
connectPose();
requestAnimationFrame(animateRobot);
const pointBudgetReady = initializePointBudgets();
pointBudgetReady.then(() => loadOfflinePointcloud().then(refreshSavedMaps));
refreshState();
refreshTopics();
refreshSources();
pointBudgetReady.then(refreshPointcloud);
refreshMap();
refreshMappingControl();
setInterval(refreshState, 1000);
setInterval(refreshPointcloud, 400);
setInterval(refreshMap, 2000);
setInterval(refreshTopics, 3500);
setInterval(refreshSources, 5000);
setInterval(refreshSavedMaps, 15000);
setInterval(refreshMappingControl, 1000);
setInterval(markJointsStale, 250);
setInterval(syncCameraFrameFreshness, 500);
setInterval(controlTick, 50);
setInterval(refreshControlSnapshot, 1000);
setInterval(refreshControlGamepads, 1000);
