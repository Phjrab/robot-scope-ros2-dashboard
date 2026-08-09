const $ = (selector) => document.querySelector(selector);

const ui = {
  connectionChip: $('#connectionChip'),
  connectionLabel: $('#connectionLabel'),
  robotIp: $('#robotIp'),
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

let latestState = null;
let latestTopics = [];
let sourceFingerprint = '';
let cameraSocket = null;
let jointSocket = null;
let poseSocket = null;
let cameraMeta = null;
let videoDecoder = null;
let cameraHasKey = false;
let cameraFrames = 0;
let cameraFrameWindow = [];
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
let officialModelsReady = false;
let officialModelsFailed = false;
let jointLive = false;
let lastJointAt = 0;
let latestBodyRpy = null;
let targetJointPositions = null;
let renderedJointPositions = null;
let mappingControlSnapshot = null;
let mappingLogCursor = 0;
let mappingLogLines = [];
let handledMappingOperation = '';

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

async function prepareOfficialRobotModels() {
  const renderers = [scene3d, savedScene3d].filter((scene) => typeof scene?.loadOfficialRobotModel === 'function');
  try {
    if (renderers.length !== 2) throw new Error('official model renderer unavailable');
    await Promise.all(renderers.map((scene) => scene.loadOfficialRobotModel()));
    scene3d.configureOfficialRobot?.({ poseOrigin: 'base', adaptiveScale: false, scale: 1 });
    officialModelsReady = true;
    ui.savedModelState.textContent = 'OFFICIAL GO2 URDF';
    ui.savedModelState.classList.add('ready');
    updateLiveModelBadge();
  } catch (error) {
    console.warn('Official Go2 model fallback:', error);
    officialModelsFailed = true;
    [ui.liveModelState, ui.savedModelState].forEach((element) => {
      element.textContent = 'GO2 FALLBACK MODEL';
      element.classList.add('fallback');
    });
  }
}

function updateLiveModelBadge() {
  if (officialModelsFailed) return;
  ui.liveModelState.classList.toggle('ready', officialModelsReady);
  if (!officialModelsReady) {
    ui.liveModelState.textContent = 'GO2 MODEL · LOADING';
  } else if (jointLive) {
    ui.liveModelState.textContent = 'OFFICIAL GO2 · JOINTS LIVE';
  } else {
    ui.liveModelState.textContent = 'OFFICIAL GO2 · JOINTS WAITING';
  }
}

const PAGE_META = {
  overview: ['Overview', '로봇과 ROS 2 시스템의 전체 상태를 빠르게 확인합니다.'],
  mapping: ['Live LiDAR Mapping', '실시간 점군, 로봇 자세와 매핑 파이프라인을 확인합니다.'],
  maps: ['Saved Maps', '이미 매핑된 3D PCD와 2D 점유 지도를 센서 없이 탐색합니다.'],
  sensors: ['Sensors & Camera', '카메라 스트림과 로봇 센서 값을 기능별로 확인합니다.'],
  topics: ['ROS Graph', '발견된 ROS 2 토픽, 타입, 수신률과 지연을 조회합니다.'],
  settings: ['Settings', '로봇 연결 대상과 자동 탐색된 ROS 2 데이터 소스를 선택합니다.'],
};

function pageFromHash() {
  const route = location.hash.replace(/^#\/?/, '').trim();
  return Object.hasOwn(PAGE_META, route) ? route : 'overview';
}

function activatePage(page, updateHash = false) {
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
  ui.connectionChip.className = `connection-chip ${ready && online ? 'ok' : ready ? 'waiting' : 'error'}`;
  ui.connectionLabel.textContent = ready && online ? '로봇 연결됨' : ready ? '에이전트 연결됨' : '에이전트 오류';
  ui.agentHost.textContent = health.hostname || '—';
  ui.rosRuntime.textContent = `${health.ros_distro || '—'} · ${health.rmw || 'default'}`;
  ui.rosDomain.textContent = health.ros_domain_id ?? '0';
  ui.topicCount.textContent = health.topic_count ?? '—';
  ui.profileLabel.textContent = (health.profile || 'GENERIC ROS 2').toUpperCase();
  if (document.activeElement !== ui.robotIp && health.robot_ip) ui.robotIp.value = health.robot_ip;
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

  const cameraTopic = latestTopics.find((topic) => topic.name === cameraSource);
  ui.cameraMetric.textContent = formatHz(cameraTopic?.hz);
  ui.cameraSub.textContent = cameraSource || 'No camera topic';
  ui.cameraTopicLabel.textContent = cameraSource || 'NO SOURCE';
  ui.cameraCodecLabel.textContent = camera.format && camera.format !== 'none' ? `${camera.format.toUpperCase()} ${camera.width || ''}×${camera.height || ''}` : '—';
  setStatePill(ui.cameraState, cameraTopic?.state || 'waiting', cameraTopic?.state === 'ok' ? 'LIVE' : (cameraTopic?.state || 'WAITING').toUpperCase());

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
  const sorted = [...sensors].sort((a, b) => priority.indexOf(a.category) - priority.indexOf(b.category)).slice(0, 6);
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
    if (renderedJointPositions) scene3d?.setRobotJointPositions?.(renderedJointPositions);
    scene3d?.setRobotPose(poseLive ? currentPose : null);
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
    scene3d.setRobotVisible(mapOverlayVisible);
    scene3d.setStatus({ online: Boolean(latestState?.health?.robot_online), lidarOnline: false, snapshot: false, message: '실시간 LiDAR 신호를 기다리고 있습니다' });
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
  scene3d.setRobotPose(poseLive ? currentPose : null);
  scene3d.setTrail(poseTrail);
  scene3d.setRobotVisible(mapOverlayVisible);
  scene3d.setTrailVisible(mapOverlayVisible);
  scene3d.setStatus({
    online: poseLive || jointLive || Boolean(latestState?.health?.robot_online),
    lidarOnline: isLiveCloudReady(),
    snapshot: false,
    message: '실시간 LiDAR 포인트클라우드',
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
  const canvas = ui.cameraCanvas;
  if (canvas.width !== frame.displayWidth || canvas.height !== frame.displayHeight) {
    canvas.width = frame.displayWidth;
    canvas.height = frame.displayHeight;
  }
  canvas.getContext('2d').drawImage(frame, 0, 0);
  frame.close();
  cameraFrames += 1;
  cameraFrameWindow.push(performance.now());
  while (cameraFrameWindow.length && performance.now() - cameraFrameWindow[0] > 1000) cameraFrameWindow.shift();
  ui.cameraEmpty.style.display = 'none';
}

async function renderImageBlob(data, format) {
  const bitmap = await createImageBitmap(new Blob([data], { type: format === 'png' ? 'image/png' : 'image/jpeg' }));
  const canvas = ui.cameraCanvas;
  canvas.width = bitmap.width; canvas.height = bitmap.height;
  canvas.getContext('2d').drawImage(bitmap, 0, 0);
  bitmap.close();
  ui.cameraEmpty.style.display = 'none';
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
  ui.cameraEmpty.style.display = 'none';
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
  cameraSocket.onmessage = async (event) => {
    if (typeof event.data === 'string') {
      cameraMeta = JSON.parse(event.data);
      return;
    }
    if (!cameraMeta) return;
    try {
      if (cameraMeta.format === 'h264') {
        if (!videoDecoder || videoDecoder.state === 'closed') if (!resetDecoder()) return;
        if (cameraMeta.key) cameraHasKey = true;
        if (!cameraHasKey) return;
        const chunk = new EncodedVideoChunk({
          type: cameraMeta.key ? 'key' : 'delta',
          timestamp: Number(cameraMeta.seq) * 33333,
          data: new Uint8Array(event.data),
        });
        if (videoDecoder.decodeQueueSize < 4) videoDecoder.decode(chunk);
      } else if (cameraMeta.format === 'jpeg' || cameraMeta.format === 'png') {
        await renderImageBlob(event.data, cameraMeta.format);
      } else if (cameraMeta.format === 'raw') {
        renderRawImage(event.data, cameraMeta);
      }
    } catch (error) {
      console.warn('camera render:', error);
      if (cameraMeta.format === 'h264') resetDecoder();
    }
  };
  cameraSocket.onclose = () => setTimeout(connectCamera, 1800);
  cameraSocket.onerror = () => cameraSocket.close();
}

async function setRobotIp() {
  try {
    await api('/api/v1/robot', { method: 'POST', body: JSON.stringify({ ip: ui.robotIp.value.trim() }) });
    showToast('로봇 연결 대상을 변경했습니다.');
    await refreshState();
  } catch (error) { showToast(`IP 변경 실패: ${error.message}`, true); }
}

function startClock() {
  const tick = () => { $('#clock').textContent = new Date().toLocaleTimeString('ko-KR', { hour12: false }); };
  tick(); setInterval(tick, 1000);
}

$('#connectButton').addEventListener('click', setRobotIp);
ui.robotIp.addEventListener('keydown', (event) => { if (event.key === 'Enter') setRobotIp(); });
$('#refreshButton').addEventListener('click', async () => { await Promise.all([refreshState(), refreshTopics(), refreshSources(), refreshMappingControl()]); showToast('대시보드를 갱신했습니다.'); });
ui.mappingStartButton.addEventListener('click', startMappingSession);
ui.mappingSaveButton.addEventListener('click', saveMappingSession);
ui.mappingStopButton.addEventListener('click', stopMappingSession);
ui.cameraSource.addEventListener('change', () => selectSource('camera', ui.cameraSource.value));
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
window.addEventListener('hashchange', () => activatePage(pageFromHash()));
window.addEventListener('resize', () => {
  if (activePage === 'mapping') redrawActiveMap();
  if (activePage === 'maps') redrawSavedMap();
});

startClock();
activatePage(pageFromHash(), true);
ui.mappingSessionName.value = generatedMapName();
prepareOfficialRobotModels();
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
