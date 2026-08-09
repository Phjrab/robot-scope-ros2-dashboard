import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
const stylesSource = readFileSync(new URL('../robot_dashboard/static/styles.css', import.meta.url), 'utf8');

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
    'function createLatestCameraFrameQueue(',
    'cameraFrameIsFresh',
  );
  assert.equal(isFresh(1_000, { state: 'ok', age_s: 0.2 }, 3_999), true);
  assert.equal(isFresh(1_000, { state: 'ok', age_s: 0.2 }, 4_001), false);
  assert.equal(isFresh(1_000, { state: 'stale', age_s: 0.2 }, 2_000), false);
  assert.equal(isFresh(1_000, { state: 'ok', age_s: 3.1 }, 2_000), false);
  assert.equal(isFresh(1_000, {}, 2_000), true);
  assert.match(appSource, /setInterval\(syncCameraFrameFreshness, 500\)/);
  assert.match(appSource, /영상 신호가 3초 이상 멈춰 녹화를 종료하고 저장했습니다/);
  assert.match(appSource, /const wasFresh = cameraFrameAvailable\(\)/);
  assert.match(appSource, /if \(!cameraRecording && !wasFresh\)/);
});

test('JPEG queue is single-flight, latest-only and never renders an older pending frame', async () => {
  const createQueue = extractedFunction(
    'function createLatestCameraFrameQueue(',
    'function getCameraImageDecodeQueue()',
    'createLatestCameraFrameQueue',
  );
  const waits = new Map([['a', deferred()], ['b', deferred()], ['c', deferred()]]);
  const decoded = [];
  const rendered = [];
  const closed = [];
  const queue = createQueue({
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
  assert.deepEqual({ ...queue.snapshot() }, { generation: 0, active: true, pending: 1 });
  waits.get('a').resolve({ id: 'bitmap-a' });
  await flushTasks();
  assert.deepEqual(decoded, ['a', 'c']);
  assert.deepEqual(rendered, ['a:bitmap-a']);
  assert.deepEqual(closed, ['bitmap-a']);
  waits.get('c').resolve({ id: 'bitmap-c' });
  await flushTasks();
  assert.deepEqual(rendered, ['a:bitmap-a', 'c:bitmap-c']);
  assert.deepEqual(closed, ['bitmap-a', 'bitmap-c']);
  assert.deepEqual({ ...queue.snapshot() }, { generation: 0, active: false, pending: 0 });
});

test('source generation reset closes an old decoded bitmap without rendering it', async () => {
  const createQueue = extractedFunction(
    'function createLatestCameraFrameQueue(',
    'function getCameraImageDecodeQueue()',
    'createLatestCameraFrameQueue',
  );
  const waits = new Map([['old', deferred()], ['new', deferred()]]);
  const decoded = [];
  const rendered = [];
  const closed = [];
  const queue = createQueue({
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
  assert.deepEqual({ ...queue.snapshot() }, { generation: 1, active: false, pending: 0 });
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
