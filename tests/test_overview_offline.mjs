import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';
import { controlBridgeConnectionState, renderHeaderConnections } from '../robot_dashboard/static/features/control/session_contract.js';

const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');

const overviewFields = [
  'linkMetric',
  'linkSub',
  'cameraMetric',
  'cameraSub',
  'lidarMetric',
  'lidarSub',
  'batteryMetric',
  'batterySub',
];

function functionSource(name) {
  const marker = `function ${name}(`;
  const markerStart = appSource.indexOf(marker);
  assert.ok(markerStart >= 0, `${name} must exist`);
  const start = appSource.slice(Math.max(0, markerStart - 6), markerStart) === 'async '
    ? markerStart - 6
    : markerStart;
  const parametersStart = appSource.indexOf('(', markerStart);
  let parametersDepth = 0;
  let parametersEnd = -1;
  let parameterQuote = '';
  let parameterEscaped = false;
  for (let index = parametersStart; index < appSource.length; index += 1) {
    const character = appSource[index];
    if (parameterQuote) {
      if (parameterEscaped) parameterEscaped = false;
      else if (character === '\\') parameterEscaped = true;
      else if (character === parameterQuote) parameterQuote = '';
      continue;
    }
    if (character === "'" || character === '"' || character === '`') {
      parameterQuote = character;
      continue;
    }
    if (character === '(') parametersDepth += 1;
    if (character === ')' && --parametersDepth === 0) {
      parametersEnd = index;
      break;
    }
  }
  const bodyStart = appSource.indexOf('{', parametersEnd);
  assert.ok(bodyStart > start, `${name} must have a body`);
  let depth = 0;
  let quote = '';
  let escaped = false;
  let lineComment = false;
  let blockComment = false;
  for (let index = bodyStart; index < appSource.length; index += 1) {
    const character = appSource[index];
    const next = appSource[index + 1];
    if (lineComment) {
      if (character === '\n') lineComment = false;
      continue;
    }
    if (blockComment) {
      if (character === '*' && next === '/') {
        blockComment = false;
        index += 1;
      }
      continue;
    }
    if (quote) {
      if (escaped) escaped = false;
      else if (character === '\\') escaped = true;
      else if (character === quote) quote = '';
      continue;
    }
    if (character === '/' && next === '/') {
      lineComment = true;
      index += 1;
      continue;
    }
    if (character === '/' && next === '*') {
      blockComment = true;
      index += 1;
      continue;
    }
    if (character === "'" || character === '"' || character === '`') {
      quote = character;
      continue;
    }
    if (character === '{') depth += 1;
    if (character === '}') {
      depth -= 1;
      if (depth === 0) return appSource.slice(start, index + 1);
    }
  }
  assert.fail(`${name} body must be balanced`);
}

function loadFunctions(names, globals = {}) {
  const sandbox = { ...globals };
  const exports = names.map((name) => `this.${name} = ${name};`).join('\n');
  runInNewContext(`${names.map(functionSource).join('\n')}\n${exports}`, sandbox);
  return sandbox;
}

function node(initial = '') {
  return {
    textContent: initial,
    title: '',
    className: '',
    dataset: {},
    style: {},
    classList: {
      add() {},
      remove() {},
      toggle() {},
      contains() { return false; },
    },
  };
}

function uiFixture() {
  const entries = overviewFields.map((id) => [id, node(`stale:${id}`)]);
  return new Proxy(Object.fromEntries(entries), {
    get(target, property) {
      if (!(property in target)) target[property] = node();
      return target[property];
    },
  });
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((onResolve, onReject) => {
    resolve = onResolve;
    reject = onReject;
  });
  return { promise, resolve, reject };
}

function overviewHarness() {
  const ui = uiFixture();
  const resetCalls = [];
  const sandbox = loadFunctions(
    ['overviewTelemetryLive', 'overviewUnavailableReason', 'renderOverviewUnavailable', 'updateOverview'],
    {
      ui,
      cameraStatusMeta: { state: 'ok', fps: 99 },
      overviewTelemetryAvailability: null,
      cameraCatalog: [],
      latestTopics: [],
      latestState: null,
      activePage: 'overview',
      offlineCloudSnapshot: { id: 'saved-cloud' },
      selectedSavedMapId: 'saved-map-1',
      selectedSavedMapMeta: { id: 'saved-map-1' },
      cameraRecording: { id: 'recording-1' },
      updateHealth(health) {
        ui.linkMetric.textContent = health.robot_online
          ? (health.robot_latency_ms == null ? 'ONLINE' : `${health.robot_latency_ms} ms`)
          : 'OFFLINE';
        ui.linkSub.textContent = health.robot_ip || 'IP not configured';
      },
      applyJointSnapshot() {},
      resetLiveRobotSessionView() { resetCalls.push('reset-live'); },
      noteCameraSource() {},
      formatHz(value) {
        return value == null ? '—' : `${Number(value).toFixed(Number(value) >= 10 ? 1 : 2)} Hz`;
      },
      safeNumber(value, digits = 2) {
        const numberValue = Number(value);
        return Number.isFinite(numberValue) ? numberValue.toFixed(digits) : '—';
      },
      primaryCameraSlot() { throw new Error('offline state must not read a stale camera catalog'); },
      cameraSourceForId() { return {}; },
      cameraSlotMetadata() { return { fps: 99, transport: 'cached' }; },
      renderCameraSlotIdentity() {},
      syncCameraFrameFreshness() {},
      liveSceneCloud() { return { points: [0, 0, 0], frame_id: 'map' }; },
      desiredMapView() { return 'cloud'; },
      cloudPointCount() { return 1; },
      cloudPointSummary() { return '1'; },
      setStatePill() {},
      renderLidarSourceIdentity() {
        ui.lidarSub.textContent = 'XT16 · REGISTERED CLOUD · /cloud_registered';
      },
      updateSensors() {},
      updateOdometry() {},
      updateSavedMapOverview() {},
      syncPointcloudTransport() {},
      liveMap2d: { snapshot: () => ({ cellCount: 0 }) },
      Date,
      Number,
      Boolean,
      String,
      Math,
      console,
    },
  );
  sandbox.resetCalls = resetCalls;
  return sandbox;
}

function statePayload({ online = true, battery = undefined, cameraFps = 30, lidarHz = 10 } = {}) {
  return {
    health: {
      agent_ready: true,
      robot_target_connected: true,
      robot_online: online,
      robot_ip: '192.0.2.10',
      robot_latency_ms: 7,
    },
    camera: {
      state: 'ok',
      live: true,
      age_s: 0.1,
      fps: cameraFps,
      source_label: 'Go2 front',
      topic: '/camera/front',
    },
    cloud: { frame_id: 'map', sent_points: 1 },
    map: {},
    mapping: { state: 'cloud_only', cloud: { hz: lidarHz } },
    robot_pose: { frame_id: 'map' },
    sources: {
      camera: '/camera/front',
      pointcloud: '/cloud_registered',
      odometry: '/Odometry',
      occupancy_grid: '',
    },
    sensors: battery === undefined ? [] : [battery],
  };
}

function battery({ state = 'ok', age = 0.2, soc = 64 } = {}) {
  const result = {
    category: 'battery',
    state,
    hz: 1,
    values: { battery_soc: soc, power_v: 28.4 },
  };
  if (age !== 'missing') result.age_s = age;
  return result;
}

test('Overview declares one fail-closed reset for all eight KPI fields', () => {
  for (const id of overviewFields) assert.match(indexSource, new RegExp(`id="${id}"`));
  const resetSource = functionSource('renderOverviewUnavailable');
  for (const id of overviewFields) {
    assert.match(resetSource, new RegExp(`ui\\.${id}\\.textContent\\s*=`), `${id} must be reset centrally`);
  }
  assert.match(resetSource, /cameraStatusMeta\s*=\s*null/);
  assert.match(resetSource, /resetLiveRobotSessionView\(\)/);
  assert.doesNotMatch(resetSource, /disconnectCamera|disconnectCameraSlot|stopCameraRecording|cameraRecording\s*=/);
  assert.doesNotMatch(resetSource, /offlineCloudSnapshot\s*=|selectedSavedMap(?:Id|Meta)\s*=|clearSavedMap|savedMapCatalog\s*=/);
  const liveResetSource = functionSource('resetLiveRobotSessionView');
  assert.doesNotMatch(liveResetSource, /disconnectCamera|cameraSocket|stopCameraRecording|cameraRecording\s*=/);
  assert.doesNotMatch(liveResetSource, /offlineCloudSnapshot\s*=|selectedSavedMap(?:Id|Meta)\s*=|clearSavedMap|savedMapCatalog\s*=/);
});

test('live telemetry gate fails closed for agent, target and robot state including legacy targets', () => {
  const { overviewTelemetryLive } = loadFunctions(['overviewTelemetryLive'], { Boolean });
  const healthy = { agent_ready: true, robot_target_connected: true, robot_online: true, robot_ip: '192.0.2.1' };
  assert.equal(overviewTelemetryLive(healthy), true);
  assert.equal(overviewTelemetryLive({ ...healthy, agent_ready: false }), false);
  assert.equal(overviewTelemetryLive({ ...healthy, robot_target_connected: false }), false);
  assert.equal(overviewTelemetryLive({ ...healthy, robot_online: false }), false);
  assert.equal(overviewTelemetryLive({ agent_ready: true, robot_online: true, robot_ip: '192.0.2.1' }), true);
  assert.equal(overviewTelemetryLive({ agent_ready: true, robot_online: true }), false);
  assert.equal(overviewTelemetryLive({ ...healthy, robot_target_connected: false, robot_ip: '192.0.2.1' }), false);
});

test('header separates direct ROS observability from authenticated remote control Bridge', () => {
  for (const id of ['connectionChip', 'connectionLabel', 'controlConnectionChip', 'controlConnectionLabel']) {
    assert.match(indexSource, new RegExp(`id="${id}"`));
  }
  assert.deepEqual(
    { ...controlBridgeConnectionState({
      configured: true,
      target_supported: true,
      readiness: { bridge_fresh: true },
      bridge: { authenticated: true, connected: true, state: 'ready' },
    }) },
    { tone: 'ok', label: '원격 제어 Bridge 연결' },
  );
  assert.deepEqual(
    { ...controlBridgeConnectionState({
      configured: true,
      target_supported: true,
      readiness: { bridge_fresh: false },
      bridge: { authenticated: true, connected: false, state: 'stale' },
    }) },
    { tone: 'error', label: '원격 제어 Bridge 오프라인' },
  );
  const headerUi = uiFixture();
  renderHeaderConnections(
    headerUi,
    {
      agent_ready: true,
      robot_target_connected: true,
      robot_online: false,
      ros_transport: { interface_ready: false, offline_viewer: true },
    },
    {
      configured: true,
      target_supported: true,
      readiness: { bridge_fresh: true },
      bridge: { authenticated: true, connected: true, state: 'ready' },
    },
  );
  assert.equal(headerUi.connectionLabel.textContent, '직접 ROS 오프라인');
  assert.equal(headerUi.controlConnectionLabel.textContent, '원격 제어 Bridge 연결');
  assert.match(headerUi.connectionChip.className, /waiting/);
  assert.match(headerUi.controlConnectionChip.className, /ok/);
  assert.match(indexSource, /대시보드 호스트에서 로봇 ROS\/DDS를 직접 관측하는 상태/);
  assert.match(functionSource('refreshControlSnapshot'), /\['overview', 'controls', 'navigation', 'cockpit'\]/);
});

test('offline cached payload cannot revive camera, lidar, battery or link KPIs', () => {
  const harness = overviewHarness();
  harness.cameraCatalog = [{ id: 'cached-camera', fps: 99, state: 'ok' }];
  harness.updateOverview(statePayload({
    online: false,
    cameraFps: 99,
    lidarHz: 20,
    battery: battery({ soc: 88 }),
  }));

  for (const id of overviewFields) {
    assert.doesNotMatch(harness.ui[id].textContent, /99(?:\.0)? Hz|20(?:\.0)? Hz|88%|192\.0\.2\.10|XT16/);
    assert.notEqual(harness.ui[id].textContent, `stale:${id}`);
  }
  assert.equal(harness.cameraStatusMeta, null);
  assert.deepEqual(harness.offlineCloudSnapshot, { id: 'saved-cloud' });
  assert.equal(harness.selectedSavedMapId, 'saved-map-1');
  assert.deepEqual(harness.selectedSavedMapMeta, { id: 'saved-map-1' });
  assert.deepEqual(harness.cameraRecording, { id: 'recording-1' });
});

test('battery KPI requires ok state and rejects a non-finite reported age', () => {
  const cases = [
    battery({ state: 'stale', age: 0.1 }),
    battery({ state: 'ok', age: Number.POSITIVE_INFINITY }),
  ];
  for (const sensor of cases) {
    const harness = overviewHarness();
    harness.updateOverview(statePayload({ battery: sensor }));
    assert.equal(harness.ui.batteryMetric.textContent, '—');
    assert.doesNotMatch(harness.ui.batterySub.textContent, /28\.4 V|64%/);
  }

  const harness = overviewHarness();
  harness.updateOverview(statePayload({ battery: battery({ state: 'ok', age: 0.2, soc: 64 }) }));
  assert.equal(harness.ui.batteryMetric.textContent, '64%');
  assert.match(harness.ui.batterySub.textContent, /28\.4 V/);

  const legacyHarness = overviewHarness();
  legacyHarness.updateOverview(statePayload({ battery: battery({ state: 'ok', age: 'missing', soc: 63 }) }));
  assert.equal(legacyHarness.ui.batteryMetric.textContent, '63%');
});

test('camera catalog requires current live metadata and never reuses slot fps', () => {
  const harness = overviewHarness();
  harness.primaryCameraSlot = () => ({ statusMeta: null, meta: { state: 'ok', live: true, fps: 99 } });
  harness.cameraSourceForId = () => ({ id: 'go2_front', label: 'Go2 front', state: 'stale', live: false, age_s: 4, fps: 99 });
  harness.renderCameraSlotIdentity = () => {};
  harness.cameraCatalog = [{ id: 'go2_front' }];
  harness.cameraPrimarySourceId = 'go2_front';
  harness.updateOverview(statePayload({ online: true, cameraFps: 99 }));
  assert.equal(harness.ui.cameraMetric.textContent, 'OFFLINE');

  harness.cameraSourceForId = () => ({ id: 'go2_front', label: 'Go2 front', live: true, age_s: 0.1, fps: 25 });
  harness.updateOverview(statePayload({ online: true, cameraFps: 99 }));
  assert.equal(harness.ui.cameraMetric.textContent, '25.0 Hz');
});

test('an online payload restores fresh KPIs after an offline reset without touching saved maps or recording', () => {
  const harness = overviewHarness();
  harness.updateOverview(statePayload({ online: false, battery: battery({ soc: 88 }) }));
  harness.cameraCatalog = [];
  harness.updateOverview(statePayload({ online: true, cameraFps: 24, lidarHz: 12, battery: battery({ soc: 61 }) }));

  assert.equal(harness.ui.linkMetric.textContent, '7 ms');
  assert.equal(harness.ui.cameraMetric.textContent, '24.0 Hz');
  assert.equal(harness.ui.lidarMetric.textContent, '12.0 Hz');
  assert.equal(harness.ui.batteryMetric.textContent, '61%');
  assert.deepEqual(harness.offlineCloudSnapshot, { id: 'saved-cloud' });
  assert.equal(harness.selectedSavedMapId, 'saved-map-1');
  assert.deepEqual(harness.cameraRecording, { id: 'recording-1' });
});

test('lidar source identity cannot repopulate its subtitle while telemetry is unavailable', () => {
  const ui = uiFixture();
  const sandbox = loadFunctions(
    ['overviewTelemetryLive', 'overviewUnavailableReason', 'renderLidarSourceIdentity'],
    {
      ui,
      overviewTelemetryAvailability: null,
      latestState: { health: { agent_ready: true, robot_target_connected: true, robot_online: false } },
      selectedPointcloudTopic() { throw new Error('offline lidar rendering must return before resolving cached sources'); },
      pointcloudSourceCatalog: new Map(),
      latestTopics: [],
      LidarSourceIdentity: {},
      lidarSourceFreshness() { return 'LIVE'; },
      lidarSourcePinInfo() { return {}; },
      renderLidarSourceReadout() {},
      Object,
      Boolean,
    },
  );
  sandbox.renderLidarSourceIdentity();
  assert.doesNotMatch(ui.lidarSub.textContent, /XT16|REGISTERED|\/cloud_registered/);
  assert.notEqual(ui.lidarSub.textContent, 'stale:lidarSub');

  sandbox.latestState = null;
  sandbox.overviewTelemetryAvailability = false;
  ui.lidarSub.textContent = 'cached XT16 · /cloud_registered';
  sandbox.renderLidarSourceIdentity();
  assert.doesNotMatch(ui.lidarSub.textContent, /XT16|\/cloud_registered/);
});

test('state polling has a generation fence and ignores an older response', async () => {
  const first = deferred();
  const second = deferred();
  const requests = [first, second];
  const rendered = [];
  const ui = uiFixture();
  const sandbox = loadFunctions(['refreshState'], {
    stateRequestGeneration: 0,
    api() { return requests.shift().promise; },
    latestState: null,
    updateOverview(value) { rendered.push(value.id); },
    activePage: 'overview',
    redrawActiveMap() {},
    redrawSavedMap() {},
    renderOverviewUnavailable() {},
    renderLidarSourceIdentity() {},
    ui,
    scene3d: null,
  });

  const older = sandbox.refreshState();
  const newer = sandbox.refreshState();
  second.resolve({ id: 'newer' });
  await newer;
  first.resolve({ id: 'older' });
  await older;
  assert.deepEqual(rendered, ['newer']);
  assert.equal(sandbox.latestState.id, 'newer');
});

test('state request failure resets Overview and connect/disconnect invalidate older requests', async () => {
  const reasons = [];
  const ui = uiFixture();
  const sandbox = loadFunctions(['invalidateStateRequests', 'refreshState'], {
    stateRequestGeneration: 4,
    api: async () => { throw new Error('offline'); },
    latestState: { id: 'cached-online', health: { agent_ready: true, robot_target_connected: true, robot_online: true } },
    updateOverview() { assert.fail('failed state request must not render cached telemetry'); },
    activePage: 'overview',
    redrawActiveMap() {},
    redrawSavedMap() {},
    renderOverviewUnavailable(reason) { reasons.push(reason); },
    renderLidarSourceIdentity() {},
    ui,
    scene3d: { setStatus() {} },
  });
  sandbox.invalidateStateRequests();
  assert.equal(sandbox.stateRequestGeneration, 5);
  await sandbox.refreshState();
  assert.equal(reasons.length, 1);

  for (const name of ['setRobotIp', 'disconnectRobotTarget']) {
    assert.match(functionSource(name), /invalidateStateRequests\(\)/, `${name} must fence requests explicitly`);
  }
});
