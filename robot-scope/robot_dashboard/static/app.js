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
  mapViewMode: $('#mapViewMode'),
  mapOverlayToggle: $('#mapOverlayToggle'),
  mappingState: $('#mappingState'),
  mapFrame: $('#mapFrame'),
  mapPoints: $('#mapPoints'),
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
let cameraMeta = null;
let videoDecoder = null;
let cameraHasKey = false;
let cameraFrames = 0;
let cameraFrameWindow = [];
let cloudSeq = -1;
let mapSeq = -1;
let toastTimer = null;
let currentPose = null;
let poseTrail = [];
let lastCloudSnapshot = null;
let offlineCloudSnapshot = null;
let lastMapSnapshot = null;
let activeMapView = null;
let mapViewPreference = 'cloud';
let mapOverlayVisible = true;
let sceneCloudDataKey = '';
let sceneCloudSourceKey = '';

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
  });
  scene3d.setStatus({ online: false, lidarOnline: false, message: '저장된 3D 지도를 불러오는 중입니다' });
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
  return Boolean(latestState?.health?.robot_online) &&
    (cloudState === 'ok' || mappingState === 'mapping' || mappingState === 'cloud_only');
}

function activeSceneCloud(candidate = lastCloudSnapshot) {
  if (candidate?.points?.length && isLiveCloudReady()) return candidate;
  return offlineCloudSnapshot?.points?.length ? offlineCloudSnapshot : candidate;
}

function cloudPointCount(cloud) {
  return Number(cloud?.sent_points || (cloud?.points?.length ? Math.floor(cloud.points.length / 3) : 0));
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
  if (desiredMapView() === 'occupancy') {
    const gridTopic = latestTopics.find((topic) => topic.name === gridSource);
    ui.lidarMetric.textContent = gridTopic?.state === 'ok' && gridTopic?.hz == null ? 'STATIC' : formatHz(gridTopic?.hz);
    ui.lidarSub.textContent = `${hesaiOnline ? 'XT16 ONLINE · ' : ''}${gridSource || 'No 2D map topic'}`;
    ui.mapFrame.textContent = `FRAME ${grid.frame_id || '—'}`;
    ui.mapPoints.textContent = grid.width && grid.height ? `${grid.width}×${grid.height} CELLS` : '0 CELLS';
    setStatePill(ui.mappingState, gridTopic?.state || 'waiting', gridTopic?.state === 'ok' ? '2D MAP READY' : (gridTopic?.state || 'WAITING').toUpperCase());
  } else {
    const cloudMetric = mapping.cloud || {};
    const sceneCloud = activeSceneCloud();
    const saved = Boolean(sceneCloud?.offline_snapshot);
    if (saved) {
      const demo = Boolean(sceneCloud.demo_snapshot);
      ui.lidarMetric.textContent = `${cloudPointCount(sceneCloud).toLocaleString()} pts`;
      ui.lidarSub.textContent = `${demo ? 'DEMO' : 'SAVED'} SNAPSHOT · ${sceneCloud.topic || '/saved/Laser_map'}`;
      ui.mapFrame.textContent = `FRAME ${sceneCloud.frame_id || '—'}`;
      ui.mapPoints.textContent = `${cloudPointCount(sceneCloud).toLocaleString()} POINTS · ${demo ? 'DEMO' : 'SAVED'}`;
      setStatePill(ui.mappingState, 'saved', demo ? 'DEMO 3D MAP' : 'SAVED 3D MAP');
    } else {
      ui.lidarMetric.textContent = formatHz(cloudMetric.hz);
      ui.lidarSub.textContent = `${hesaiOnline ? 'XT16 ONLINE · ' : ''}${cloudSource || 'No cloud topic'}`;
      ui.mapFrame.textContent = `FRAME ${cloud.frame_id || sceneCloud?.frame_id || '—'}`;
      ui.mapPoints.textContent = `${Number(cloud.sent_points || cloudPointCount(sceneCloud)).toLocaleString()} POINTS`;
      const mappingLabels = { mapping: 'MAPPING', cloud_only: 'CLOUD LIVE', waiting: 'WAITING', stale: 'STALE' };
      setStatePill(ui.mappingState, mapping.state || 'waiting', mappingLabels[mapping.state] || 'WAITING');
    }
  }
  ui.lidarSub.title = ui.lidarSub.textContent;

  const battery = (state.sensors || []).find((sensor) => sensor.values?.battery_soc != null || sensor.category === 'battery');
  const soc = battery?.values?.battery_soc ?? (battery?.values?.percentage != null ? battery.values.percentage * 100 : null);
  ui.batteryMetric.textContent = soc == null ? '—' : `${Math.round(soc)}%`;
  ui.batterySub.textContent = battery ? `${safeNumber(battery.values.power_v ?? battery.values.voltage, 1)} V · ${formatHz(battery.hz)}` : '데이터 대기 중';

  updateSensors(state.sensors || []);
  updateOdometry(state.sensors || [], odomSource);
  ui.lastUpdated.textContent = `Last update ${new Date().toLocaleTimeString('ko-KR', { hour12: false })}`;
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
  const odom = sensors.find((sensor) => sensor.topic === source) || sensors.find((sensor) => sensor.category === 'odometry');
  ui.odomTopic.textContent = source || odom?.topic || 'NO SOURCE';
  if (latestState?.health?.robot_online === false) {
    ui.posX.textContent = ui.posY.textContent = ui.posZ.textContent = ui.speed.textContent = '—';
    currentPose = null;
    poseTrail = [];
    return;
  }
  const position = odom?.values?.position || {};
  const velocity = odom?.values?.linear_velocity || {};
  ui.posX.textContent = safeNumber(position.x);
  ui.posY.textContent = safeNumber(position.y);
  ui.posZ.textContent = safeNumber(position.z);
  const speed = Math.hypot(Number(velocity.x || 0), Number(velocity.y || 0), Number(velocity.z || 0));
  ui.speed.textContent = odom ? safeNumber(speed) : '—';
  updateMapPose(position, odom?.values?.orientation, odom?.values?.frame_id);
}

function updateMapPose(position, orientation, frameId) {
  const x = Number(position?.x);
  const y = Number(position?.y);
  const z = Number(position?.z);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return;
  const yaw = quaternionYaw(orientation);
  const nextPose = { x, y, z: Number.isFinite(z) ? z : 0, yaw, frameId: frameId || '' };
  const previous = poseTrail[poseTrail.length - 1];
  const distance = previous ? Math.hypot(nextPose.x - previous.x, nextPose.y - previous.y) : Infinity;
  const turn = previous ? Math.abs(angleDelta(nextPose.yaw, previous.yaw)) : Infinity;
  if (!previous || distance > 0.025 || turn > 0.035) {
    poseTrail.push(nextPose);
    poseTrail = poseTrail.slice(-36);
  }
  currentPose = nextPose;
  redrawActiveMap();
}

function quaternionYaw(quaternion) {
  const x = Number(quaternion?.x) || 0;
  const y = Number(quaternion?.y) || 0;
  const z = Number(quaternion?.z) || 0;
  const w = Number(quaternion?.w);
  const normalizedW = Number.isFinite(w) ? w : 1;
  return Math.atan2(2 * (normalizedW * z + x * y), 1 - 2 * (y * y + z * z));
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
    redrawActiveMap();
  } catch (error) {
    ui.connectionChip.className = 'connection-chip error';
    ui.connectionLabel.textContent = '에이전트 연결 끊김';
    if (scene3d) scene3d.setStatus({ online: false, lidarOnline: false, message: '에이전트 연결이 끊겼습니다' });
  }
}

async function refreshTopics() {
  try {
    latestTopics = (await api('/api/v1/topics')).topics || [];
    renderTopics();
    if (latestState) updateOverview(latestState);
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
  try {
    const cloud = await latestApi('/api/v1/pointcloud', cloudSeq);
    if (!cloud?.seq || !cloud.points?.length) {
      if (desiredMapView() === 'cloud' && offlineCloudSnapshot) drawPointcloud(offlineCloudSnapshot);
      return;
    }
    cloudSeq = cloud.seq;
    lastCloudSnapshot = cloud;
    if (desiredMapView() === 'cloud') drawPointcloud(cloud);
  } catch (_) {
    if (desiredMapView() === 'cloud' && offlineCloudSnapshot) drawPointcloud(offlineCloudSnapshot);
  }
}

async function loadOfflinePointcloud() {
  try {
    const response = await fetch('/static/data/go2_saved_map.json', { cache: 'force-cache' });
    if (!response.ok) throw new Error(String(response.status));
    const cloud = await response.json();
    if (!cloud?.points?.length) throw new Error('empty snapshot');
    offlineCloudSnapshot = { ...cloud, offline_snapshot: true };
    if (desiredMapView() === 'cloud') drawPointcloud(offlineCloudSnapshot);
    if (latestState) updateOverview(latestState);
  } catch (error) {
    console.info('offline 3D map unavailable; using generated demo cloud:', error);
    offlineCloudSnapshot = buildDemoPointcloud();
    if (desiredMapView() === 'cloud') drawPointcloud(offlineCloudSnapshot);
    if (latestState) updateOverview(latestState);
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

function drawPointcloud(cloud) {
  const selectedCloud = activeSceneCloud(cloud);
  setMapLayerVisibility('cloud');
  activeMapView = 'cloud';
  if (!scene3d || !selectedCloud?.points?.length) return;

  const saved = Boolean(selectedCloud.offline_snapshot);
  const sourceKey = `${saved ? 'saved' : 'live'}:${selectedCloud.topic || selectedCloud.frame_id || 'cloud'}`;
  const dataKey = `${sourceKey}:${selectedCloud.seq ?? selectedCloud.stamp_ns ?? cloudPointCount(selectedCloud)}`;
  if (dataKey !== sceneCloudDataKey) {
    scene3d.setPointCloud(selectedCloud, { fit: sourceKey !== sceneCloudSourceKey });
    sceneCloudDataKey = dataKey;
    sceneCloudSourceKey = sourceKey;
  }
  scene3d.setRobotPose(saved || !latestState?.health?.robot_online ? null : currentPose);
  scene3d.setTrail(poseTrail);
  scene3d.setRobotVisible(mapOverlayVisible);
  scene3d.setTrailVisible(mapOverlayVisible);
  scene3d.setStatus({
    online: Boolean(latestState?.health?.robot_online),
    lidarOnline: !saved && isLiveCloudReady(),
    snapshot: saved,
    message: saved ? '저장된 LiDAR 지도를 표시하고 있습니다' : '실시간 LiDAR 포인트클라우드',
  });
}

async function refreshMap() {
  try {
    const map = await latestApi('/api/v1/map', mapSeq);
    if (!map?.seq || !map.data_b64) return;
    mapSeq = map.seq;
    lastMapSnapshot = map;
    if (desiredMapView() === 'occupancy') drawOccupancyMap(map);
  } catch (_) {}
}

function drawOccupancyMap(map) {
  setMapLayerVisibility('occupancy');
  const canvas = ui.mapCanvas;
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
  lastMapSnapshot = map;
  activeMapView = 'occupancy';
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
  drawMapOverlay(ctx, { width, height, ratio, projectWorld, fallbackScale: scale / resolution, mode: 'GRID', frameId: map.frame_id || '' });
}

function redrawActiveMap() {
  const desired = desiredMapView();
  setMapLayerVisibility(desired);
  if (desired === 'occupancy' && lastMapSnapshot) drawOccupancyMap(lastMapSnapshot);
  else if (desired === 'cloud') drawPointcloud(activeSceneCloud());
}

function desiredMapView() {
  if (mapViewPreference === 'occupancy') {
    return latestState?.sources?.occupancy_grid ? 'occupancy' : 'cloud';
  }
  if (mapViewPreference === 'cloud') return 'cloud';
  return latestState?.sources?.occupancy_grid && lastMapSnapshot ? 'occupancy' : 'cloud';
}

function chooseMapView(mode) {
  mapViewPreference = mode;
  ui.mapViewMode.value = mode;
  redrawActiveMap();
  if (latestState) updateOverview(latestState);
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
$('#refreshButton').addEventListener('click', async () => { await Promise.all([refreshState(), refreshTopics(), refreshSources()]); showToast('대시보드를 갱신했습니다.'); });
ui.cameraSource.addEventListener('change', () => selectSource('camera', ui.cameraSource.value));
ui.cloudSource.addEventListener('change', () => {
  if (ui.cloudSource.value) chooseMapView('cloud');
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
ui.mapOverlayToggle.addEventListener('change', () => {
  mapOverlayVisible = ui.mapOverlayToggle.checked;
  redrawActiveMap();
});
ui.topicSearch.addEventListener('input', renderTopics);
ui.categoryFilter.addEventListener('change', renderTopics);
window.addEventListener('resize', () => { cloudSeq = -1; mapSeq = -1; redrawActiveMap(); });

startClock();
connectCamera();
loadOfflinePointcloud();
refreshState();
refreshTopics();
refreshSources();
refreshPointcloud();
refreshMap();
setInterval(refreshState, 1000);
setInterval(refreshPointcloud, 1000);
setInterval(refreshMap, 2000);
setInterval(refreshTopics, 3500);
setInterval(refreshSources, 5000);
