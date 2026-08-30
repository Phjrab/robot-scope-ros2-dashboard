import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

import { createLatestCameraFrameQueue, projectCameraObservability } from '../robot_dashboard/static/features/sensors/camera_observability.js';

const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
const stylesSource = readFileSync(new URL('../robot_dashboard/static/styles.css', import.meta.url), 'utf8');
const observabilitySource = readFileSync(new URL('../robot_dashboard/static/features/sensors/camera_observability.js', import.meta.url), 'utf8');

function extractedFunction(startMarker, endMarker, exportName) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start + startMarker.length);
  assert.ok(start >= 0 && end > start, `${exportName} source must exist`);
  const sandbox = {};
  runInNewContext(`${appSource.slice(start, end)}\nthis.result = ${exportName};`, sandbox);
  return sandbox.result;
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

const flushTasks = () => new Promise((resolve) => setImmediate(resolve));

test('camera panel exposes capture format, record, stop and duration controls', () => {
  for (const id of [
    'cameraCaptureFormat',
    'cameraCaptureButton',
    'cameraRecordButton',
    'cameraStopRecordButton',
    'cameraRecordDuration',
    'cameraMediaStatus',
  ]) {
    assert.match(indexSource, new RegExp(`id="${id}"`));
  }
  assert.match(indexSource, /option value="image\/png"/);
  assert.match(indexSource, /option value="image\/jpeg"/);
  assert.match(stylesSource, /\.camera-panel\.is-recording/);
});

test('screenshots export the currently rendered canvas with an empty-frame guard', () => {
  const start = appSource.indexOf('async function captureCameraFrame()');
  const end = appSource.indexOf('function chooseCameraRecordingMimeType()', start);
  assert.ok(start >= 0 && end > start, 'captureCameraFrame implementation must exist');
  const implementation = appSource.slice(start, end);
  assert.match(implementation, /if \(!cameraFrameAvailable\(\)\)/);
  assert.match(implementation, /ui\.cameraCanvas\.toBlob\(/);
  assert.match(implementation, /image\/jpeg/);
  assert.match(implementation, /image\/png/);
  assert.match(implementation, /downloadCameraBlob\(blob, filename\)/);
});

test('recording uses canvas captureStream and MediaRecorder with a real stop path', () => {
  assert.match(appSource, /ui\.cameraCanvas\.captureStream\(30\)/);
  assert.match(appSource, /new window\.MediaRecorder\(stream/);
  assert.match(appSource, /recorder\.start\(1000\)/);
  assert.match(appSource, /cameraStopRecordButton\.addEventListener\('click',[^\n]+stopCameraRecording/);
  assert.match(appSource, /new Blob\(session\.chunks, \{ type: mimeType \}\)/);
  assert.match(appSource, /if \(!blob\.size\)/);
  assert.match(appSource, /session\.stream\.getTracks\(\)\.forEach\(\(track\) => track\.stop\(\)\)/);
  assert.match(appSource, /CAMERA_RECORD_MAX_MS = 10 \* 60 \* 1000/);
  assert.match(appSource, /CAMERA_RECORD_MAX_BYTES = 256 \* 1024 \* 1024/);
});

test('all current and future camera transports converge on one canvas frame contract', () => {
  assert.match(appSource, /function renderCameraSourceFrame\(source,/);
  assert.match(appSource, /renderCameraSourceFrame\(frame, frame\.displayWidth, frame\.displayHeight\)/);
  assert.match(appSource, /enqueueCameraImageFrame\(data, metadata\)/);
  assert.match(appSource, /markCameraFrameRendered\(sourceKey \|\| cameraMeta\?\.topic \|\| cameraActiveSourceKey\)/);
  assert.match(appSource, /window\.RobotScopeCameraFrame = Object\.freeze\(\{/);
});

test('recording cleanup policy saves on visibility and route changes but discards on unload', () => {
  const cleanupPolicy = extractedFunction(
    'function cameraRecordingCleanupPolicy(trigger)',
    'function stopCameraRecording(',
    'cameraRecordingCleanupPolicy',
  );
  assert.equal(cleanupPolicy('visibility_hidden').discard, false);
  assert.equal(cleanupPolicy('sensors_page_left').discard, false);
  assert.equal(cleanupPolicy('page_hidden').discard, true);
  assert.match(appSource, /cameraSource\.addEventListener\('change',[\s\S]{0,180}resetCameraRenderedFrame/);
  assert.match(appSource, /visibilitychange[\s\S]{0,300}cameraRecordingCleanupPolicy\('visibility_hidden'\)/);
  assert.match(appSource, /pagehide[\s\S]{0,260}discardCameraRecordingForPageHide\(\)/);
  assert.match(appSource, /previousPage === 'sensors'[\s\S]{0,180}cameraRecordingCleanupPolicy\('sensors_page_left'\)/);
  assert.match(appSource, /noteCameraSource\(metadata\.topic \|\| metadata\.source/);
});

test('camera freshness rejects frozen frames and stale backend metadata', () => {
  const isFresh = extractedFunction(
    'const CAMERA_FRAME_FRESH_MS = 3000;',
    'function getCameraImageDecodeQueue()',
    'cameraFrameIsFresh',
  );
  assert.equal(isFresh(1_000, { state: 'ok', age_s: 0.2 }, 3_999), true);
  assert.equal(isFresh(1_000, { state: 'ok', age_s: 0.2 }, 4_001), false);
  assert.equal(isFresh(1_000, { state: 'stale', age_s: 0.2 }, 2_000), false);
  assert.equal(isFresh(1_000, { state: 'ok', age_s: 3.1 }, 2_000), false);
  assert.equal(isFresh(1_000, {}, 2_000), true);
  assert.match(appSource, /setInterval\(syncCameraFrameFreshness, 500\)/);
  assert.match(appSource, /slot\.lastFrameAt \? 'stale'/);
  assert.match(appSource, /영상 신호가 3초 이상 멈춰 녹화를 종료하고 저장했습니다/);
  assert.match(appSource, /const wasFresh = cameraFrameAvailable\(\)/);
  assert.match(appSource, /if \(!cameraRecording && !wasFresh\)/);
});

test('JPEG queue is single-flight, latest-only and never renders an older pending frame', async () => {
  const waits = new Map([['a', deferred()], ['b', deferred()], ['c', deferred()]]);
  const decoded = [];
  const rendered = [];
  const closed = [];
  const queue = createLatestCameraFrameQueue({
    decode: (frame) => {
      decoded.push(frame.id);
      return waits.get(frame.id).promise;
    },
    render: (bitmap, frame) => rendered.push(`${frame.id}:${bitmap.id}`),
    close: (bitmap) => closed.push(bitmap.id),
  });

  queue.enqueue({ id: 'a', sourceKey: 'source-a' });
  queue.enqueue({ id: 'b', sourceKey: 'source-a' });
  queue.enqueue({ id: 'c', sourceKey: 'source-a' });
  assert.deepEqual({ ...queue.snapshot() }, {
    generation: 0,
    active: true,
    pending: 1,
    queueDepth: 2,
    decodedFrames: 0,
    decodeFailures: 0,
    supersededFrames: 1,
  });
  waits.get('a').resolve({ id: 'bitmap-a' });
  await flushTasks();
  assert.deepEqual(decoded, ['a', 'c']);
  assert.deepEqual(rendered, ['a:bitmap-a']);
  assert.deepEqual(closed, ['bitmap-a']);
  waits.get('c').resolve({ id: 'bitmap-c' });
  await flushTasks();
  assert.deepEqual(rendered, ['a:bitmap-a', 'c:bitmap-c']);
  assert.deepEqual(closed, ['bitmap-a', 'bitmap-c']);
  assert.deepEqual({ ...queue.snapshot() }, {
    generation: 0,
    active: false,
    pending: 0,
    queueDepth: 0,
    decodedFrames: 2,
    decodeFailures: 0,
    supersededFrames: 1,
  });
});

test('source generation reset closes an old decoded bitmap without rendering it', async () => {
  const waits = new Map([['old', deferred()], ['new', deferred()]]);
  const decoded = [];
  const rendered = [];
  const closed = [];
  const queue = createLatestCameraFrameQueue({
    decode: (frame) => {
      decoded.push(frame.id);
      return waits.get(frame.id).promise;
    },
    render: (_bitmap, frame) => rendered.push(frame.id),
    close: (bitmap) => closed.push(bitmap.id),
  });

  queue.enqueue({ id: 'old', sourceKey: 'source-a' });
  assert.equal(queue.reset(), 1);
  queue.enqueue({ id: 'new', sourceKey: 'source-b' });
  waits.get('old').resolve({ id: 'bitmap-old' });
  await flushTasks();
  assert.deepEqual(decoded, ['old', 'new']);
  assert.deepEqual(rendered, []);
  assert.deepEqual(closed, ['bitmap-old']);
  waits.get('new').resolve({ id: 'bitmap-new' });
  await flushTasks();
  assert.deepEqual(rendered, ['new']);
  assert.deepEqual(closed, ['bitmap-old', 'bitmap-new']);
  assert.deepEqual({ ...queue.snapshot() }, {
    generation: 1,
    active: false,
    pending: 0,
    queueDepth: 0,
    decodedFrames: 2,
    decodeFailures: 0,
    supersededFrames: 0,
  });
});

test('camera decode diagnostics count bounded failures without blocking later frames', async () => {
  const rendered = [];
  const queue = createLatestCameraFrameQueue({
    decode: async (frame) => {
      if (frame.id === 'bad') throw new Error('malformed JPEG');
      return { id: frame.id };
    },
    render: (_bitmap, frame) => rendered.push(frame.id),
    close: () => {},
  });
  queue.enqueue({ id: 'bad' });
  await flushTasks();
  queue.enqueue({ id: 'good' });
  await flushTasks();
  assert.deepEqual(rendered, ['good']);
  assert.equal(queue.snapshot().decodedFrames, 1);
  assert.equal(queue.snapshot().decodeFailures, 1);
  assert.ok(queue.snapshot().queueDepth <= 2);
});

test('camera page supports single and dual layouts with persistent primary controls', () => {
  for (const id of [
    'cameraSingleMode',
    'cameraDualMode',
    'cameraPrimarySource',
    'cameraViewGrid',
    'cameraPrimarySlot',
    'cameraSecondarySlot',
    'cameraSecondaryCanvas',
    'cameraCapacity',
  ]) {
    assert.match(indexSource, new RegExp(`id="${id}"`));
  }
  assert.match(indexSource, /data-camera-slot="primary"/);
  assert.match(indexSource, /data-camera-slot="secondary"/);
  assert.match(indexSource, /캡처·녹화는 PRIMARY 화면만 사용/);
  assert.match(stylesSource, /\.camera-view-grid\[data-view-mode="dual"\]\s*\{\s*grid-template-columns:repeat\(2/);
  assert.match(stylesSource, /\.sensor-page-grid \.camera-panel\.is-dual-view\s*\{\s*grid-column:1\/-1/);
  assert.match(stylesSource, /\.camera-view-toolbar\s*\{[^}]*grid-template-columns:minmax\(130px,max-content\) minmax\(190px,1fr\)/);
  assert.match(stylesSource, /\.camera-view-toggle\s*\{[^}]*min-width:130px/);
  assert.match(stylesSource, /\.camera-view-capacity\s*\{[^}]*grid-column:1\/-1/);
  assert.match(appSource, /classList\.toggle\('is-dual-view', cameraViewMode === 'dual'\)/);
  assert.match(appSource, /\$\{connectedSources\} CONNECTED · \$\{requestedSources\} REQUESTED/);
  assert.match(stylesSource, /@media \(max-width: 800px\)[\s\S]*?\.camera-view-grid\[data-view-mode="dual"\]\s*\{\s*grid-template-columns:1fr/);
});

test('both slots keep source identity, topic, transport, state and fps visible', () => {
  for (const prefix of ['cameraPrimary', 'cameraSecondary']) {
    for (const suffix of ['Label', 'SourceId', 'State', 'Fps', 'Topic', 'Transport']) {
      assert.match(indexSource, new RegExp(`id="${prefix}${suffix}"`));
    }
  }
  assert.match(appSource, /slot\.sourceIdLabel\.textContent = slot\.sourceId \|\| 'NO SOURCE'/);
  assert.match(appSource, /slot\.state\.textContent = state\.toUpperCase\(\)/);
  assert.match(appSource, /slot\.fps\.textContent = formatCameraFps/);
  assert.match(appSource, /slot\.topic\.textContent = `TOPIC \$\{topic\}`/);
  assert.match(appSource, /slot\.transport\.textContent = `TRANSPORT \$\{transport\}`/);
});

test('Sensors camera panel exposes bounded link observability and clock-domain warning', () => {
  for (const id of [
    'cameraWifiStatus',
    'cameraWifiDetail',
    'cameraSourceHealthStatus',
    'cameraSourceHealthDetail',
    'cameraTransportHealthStatus',
    'cameraTransportHealthDetail',
    'cameraDecodeHealthStatus',
    'cameraDecodeHealthDetail',
    'cameraLatencyDomain',
  ]) {
    assert.match(indexSource, new RegExp(`id="${id}"`));
  }
  assert.match(indexSource, /UNVERIFIED_CLOCK_DOMAIN/);
  assert.match(stylesSource, /\.camera-link-observability/);
  assert.match(observabilitySource, /function cameraObservabilityState\(/);
  assert.match(observabilitySource, /receive_bitrate_mbps/);
  assert.match(observabilitySource, /supersededFrames/);
  assert.match(observabilitySource, /clock: 'UNVERIFIED_CLOCK_DOMAIN'/);
});

test('camera observability rejects malformed and non-finite metrics without widening clock state', () => {
  const projected = projectCameraObservability({
    metadata: {
      receive_bitrate_mbps: Number.POSITIVE_INFINITY,
      receive_fps: 9999,
      cross_host_latency_state: 'forged-clock-domain',
      relay_health: {
        state: 'unexpected',
        fps: Number.NaN,
        profile: { width: 99999, height: -1 },
        wifi: { state: 'unexpected', rssi_dbm: null, link_mbps: Number.POSITIVE_INFINITY },
      },
    },
    queue: { decodedFrames: Number.POSITIVE_INFINITY, decodeFailures: -1, supersededFrames: 'bad', queueDepth: 99 },
    reconnects: Number.POSITIVE_INFINITY,
  });
  assert.equal(projected.wifi.state, 'UNVERIFIED');
  assert.equal(projected.source.state, 'UNVERIFIED');
  assert.equal(projected.transport.detail, '— Mbps · — FPS · R0');
  assert.equal(projected.decode.detail, 'OK 0 · FAIL 0 · DROP 0 · Q2');
  assert.equal(projected.clock, 'UNVERIFIED_CLOCK_DOMAIN');
});

test('camera catalog normalizes source_id aliases and clamps active streams to two', () => {
  const normalize = extractedFunction(
    'function normalizeCameraCatalog(payload)',
    'function cameraSourceForId(',
    'normalizeCameraCatalog',
  );
  const result = normalize({
    max_active: 8,
    sources: [
      { source_id: 'go2_front', label: 'Go2 front', stream_id: 'multicast/front', live: true, fps: '29.5' },
      { id: 'realsense_color', label: 'RealSense', transport: 'ros2', state: 'stale', available: true },
      { id: 'go2_front', label: 'duplicate' },
    ],
  });
  assert.equal(result.maxActive, 2);
  assert.equal(result.sources.length, 2);
  assert.equal(result.sources[0].id, 'go2_front');
  assert.equal(result.sources[0].source_id, 'go2_front');
  assert.equal(result.sources[0].topic, 'multicast/front');
  assert.equal(result.sources[0].fps, 29.5);
  assert.equal(result.sources[1].id, 'realsense_color');
});

test('each active slot has its own socket generation, reconnect timer and latest-frame queue', () => {
  assert.match(appSource, /function createCameraSlotRuntime\(role, elements\)[\s\S]*?socketGeneration: 0,[\s\S]*?reconnectTimer: 0,[\s\S]*?imageDecodeQueue: null/);
  assert.match(appSource, /const generation = \+\+slot\.socketGeneration/);
  assert.match(appSource, /generation !== slot\.socketGeneration/);
  assert.match(appSource, /slot\.reconnectTimer = setTimeout/);
  assert.match(appSource, /getCameraSlotImageDecodeQueue\(slot\)\.enqueue/);
  assert.match(appSource, /for \(const slot of Object\.values\(getCameraSlots\(\)\)\)/);
});

test('camera websocket identifies each requested source and reconnects only wanted slots', () => {
  assert.match(appSource, /\/api\/v1\/ws\/camera\?source_id=\$\{encodeURIComponent\(sourceId\)\}/);
  assert.match(appSource, /sourceId !== slot\.sourceId/);
  assert.match(appSource, /slot\.role === 'secondary' && cameraViewMode !== 'dual'/);
  assert.match(appSource, /cameraSlotTransportWanted\(slot\)/);
});

test('Safari JPEG fallback decodes an Image and always revokes its object URL', () => {
  const start = appSource.indexOf('async function decodeCameraImageFrame(frame)');
  const end = appSource.indexOf('function getCameraSlotImageDecodeQueue(', start);
  assert.ok(start >= 0 && end > start);
  const implementation = appSource.slice(start, end);
  assert.match(implementation, /typeof window\.createImageBitmap === 'function'/);
  assert.match(implementation, /const image = new window\.Image\(\)/);
  assert.match(implementation, /await image\.decode\(\)/);
  assert.match(implementation, /URL\.revokeObjectURL\(objectUrl\)/);
});

test('camera preferences and browser diagnostics are exposed without mutable sockets', () => {
  assert.match(appSource, /CAMERA_PREFERENCE_KEY = 'robot-scope\.camera-view\.v1'/);
  assert.match(appSource, /primarySourceId: cameraPrimarySourceId/);
  assert.match(appSource, /window\.RobotScopeCameraStreams = Object\.freeze\(\{/);
  assert.match(appSource, /socketGeneration: slot\.socketGeneration/);
  assert.match(appSource, /queue: slot\.imageDecodeQueue\?\.snapshot\(\) \|\| null/);
  assert.doesNotMatch(appSource, /RobotScopeCameraStreams[\s\S]{0,900}socket:\s*slot\.socket/);
});

test('camera catalog ignores stale overlapping poll responses', () => {
  assert.match(appSource, /let cameraCatalogRequestGeneration = 0/);
  assert.match(appSource, /const generation = \+\+cameraCatalogRequestGeneration/);
  assert.match(appSource, /if \(generation !== cameraCatalogRequestGeneration\) return null/);
});

test('overview uses direct camera state, label, transport, interface and fps metadata', () => {
  const start = appSource.indexOf('function updateOverview(state)');
  const end = appSource.indexOf('function updateSensors(', start);
  assert.ok(start >= 0 && end > start);
  const implementation = appSource.slice(start, end);
  assert.match(implementation, /camera\.source_label/);
  assert.match(implementation, /camera\.fps \?\? directCamera\.fps/);
  assert.match(implementation, /camera\.age_s \?\? directCamera\.age_s/);
  assert.match(implementation, /camera\.state \|\| directCamera\.state/);
  assert.match(implementation, /camera\.live \?\? directCamera\.live/);
  assert.match(implementation, /camera\.transport \|\| directCamera\.transport/);
  assert.match(implementation, /camera\.interface \|\| directCamera\.interface/);
  assert.match(implementation, /cameraStatusMeta = \{ \.\.\.camera \}/);
  assert.match(implementation, /if \(!cameraCatalog\.length\) cameraStatusMeta = \{ \.\.\.camera \}/);
  assert.match(implementation, /cameraStatusMeta = \{ \.\.\.selectedMetadata \}/);
  assert.match(implementation, /renderCameraSlotIdentity\(primarySlot\)/);
});

test('direct Go2 camera is shown as a locked non-ROS source in Settings', () => {
  const start = appSource.indexOf('async function refreshSources()');
  const end = appSource.indexOf('async function selectSource(', start);
  assert.ok(start >= 0 && end > start, 'refreshSources implementation must exist');
  const implementation = appSource.slice(start, end);
  assert.match(implementation, /payload\.locked\?\.camera/);
  assert.match(implementation, /ui\.cameraSource\.disabled/);
  assert.match(implementation, /직접 멀티캐스트 카메라/);
});
