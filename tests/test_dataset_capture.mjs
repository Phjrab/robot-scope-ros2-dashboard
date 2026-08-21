import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const serviceLifecycleSource = readFileSync(new URL('../robot_dashboard/static/features/settings/service_lifecycle.js', import.meta.url), 'utf8');
const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
const stylesSource = readFileSync(new URL('../robot_dashboard/static/styles.css', import.meta.url), 'utf8');

function datasetHooks() {
  const start = appSource.indexOf('const DATASET_CAPTURE_ACTIVE_STATES');
  const end = appSource.indexOf('function controlReady(', start);
  assert.ok(start >= 0 && end > start, 'dataset frontend implementation must exist');
  const sandbox = { window: {}, console };
  runInNewContext(`${appSource.slice(start, end)}\nthis.hooks = window.RobotScopeDatasetCapture;`, sandbox);
  return sandbox.hooks;
}

test('Sensors exposes a server-side dataset capture panel and compact global status', () => {
  for (const id of [
    'datasetGlobalStatus',
    'datasetCaptureState',
    'datasetSourcePicker',
    'datasetCaptureHz',
    'datasetSessionLabel',
    'datasetCaptureStart',
    'datasetCaptureStop',
    'datasetCaptureElapsed',
    'datasetCaptureSaved',
    'datasetCaptureDropped',
    'datasetCaptureBytes',
    'datasetCaptureFree',
    'datasetCaptureQuota',
    'datasetCaptureReserve',
    'datasetCapturePath',
    'datasetOpenFolder',
    'datasetPageNewest',
    'datasetPageNewer',
    'datasetPageOlder',
    'datasetPageStatus',
  ]) {
    assert.match(indexSource, new RegExp(`id="${id}"`));
  }
  assert.match(indexSource, /value="go2_front"/);
  assert.match(indexSource, /value="realsense_color"/);
  assert.match(indexSource, /value="both"/);
  assert.match(indexSource, /id="datasetCaptureHz"[^>]+min="0\.2"[^>]+max="5"/);
  assert.match(indexSource, /브라우저를 닫거나 Controls 화면으로 이동해도 저장은 계속됩니다/);
  assert.match(indexSource, /이미지별 분류 라벨·주석 기능을 제공하지 않습니다/);
  assert.match(stylesSource, /\.dataset-capture-panel, \.dataset-library-panel\s*\{\s*grid-column:1\/-1/);
});

test('dataset capture uses only the fixed same-origin API contract', () => {
  assert.match(appSource, /api\('\/api\/v1\/datasets\/capture'\)/);
  assert.match(appSource, /api\('\/api\/v1\/datasets\/capture\/start',\s*\{[\s\S]*?method: 'POST',[\s\S]*?body: JSON\.stringify\(body\)/);
  assert.match(appSource, /const body = \{\s*sources: selectedDatasetSourceControl\(\),\s*capture_hz: captureHz,\s*label: ui\.datasetSessionLabel\.value\.trim\(\)/);
  assert.match(appSource, /api\('\/api\/v1\/datasets\/capture\/stop',\s*\{[\s\S]*?body: JSON\.stringify\(\{ session_id: sessionId \}\)/);
  assert.match(appSource, /api\('\/api\/v1\/datasets'\)/);
  assert.doesNotMatch(appSource, /dataset[^\n]{0,80}(?:file:\/\/|xdg-open|open\s+-a)/i);
});

test('capture response normalization accepts fixed source counts and storage fields', () => {
  const hooks = datasetHooks();
  const normalized = hooks.normalizeCapture({
    available: true,
    state: 'capturing',
    session_id: 'session_123',
    sources: ['go2_front', 'realsense_color'],
    capture_hz: 2,
    label: 'corridor',
    elapsed_s: 12.5,
    saved: { go2_front: 9, realsense_color: 9 },
    drop_counts: { queue_full: 2, stale: 1 },
    bytes_written: 4096,
    free_bytes: 8192,
    session_quota_bytes: 20 * 1024 * 1024 * 1024,
    minimum_free_bytes: 5 * 1024 * 1024 * 1024,
    output_path: '/srv/robot-scope/datasets/session_123',
  });
  assert.equal(normalized.active, true);
  assert.deepEqual(Array.from(normalized.sources), ['go2_front', 'realsense_color']);
  assert.equal(normalized.saved, 18);
  assert.equal(normalized.dropped, 3);
  assert.equal(normalized.bytes, 4096);
  assert.equal(normalized.freeBytes, 8192);
  assert.equal(normalized.sessionQuotaBytes, 20 * 1024 * 1024 * 1024);
  assert.equal(normalized.minimumFreeBytes, 5 * 1024 * 1024 * 1024);
  assert.equal(normalized.path, '/srv/robot-scope/datasets/session_123');
  assert.equal(hooks.normalizeCapture({ free_bytes: 0 }).freeBytes, 0);
  assert.equal(hooks.normalizeCapture({}).freeBytes, null);
  assert.equal(hooks.formatBytes(1024 * 1024), '1.00 MiB');
});

test('saved dataset browser uses opaque IDs and the fixed image endpoint', () => {
  const hooks = datasetHooks();
  const catalog = hooks.normalizeCatalog({ sessions: [{
    session_id: 'abc_123',
    label: 'run 1',
    source: 'both',
    sample_count: 4,
  }] });
  assert.equal(catalog.length, 1);
  assert.equal(catalog[0].id, 'abc_123');
  assert.deepEqual(Array.from(catalog[0].sources), ['go2_front', 'realsense_color']);
  assert.equal(
    hooks.imageUrl('abc/123', 7, 'go2_front'),
    '/api/v1/datasets/abc%2F123/samples/7/go2_front.jpg',
  );
  assert.equal(hooks.detailUrl('abc/123'), '/api/v1/datasets/abc%2F123?limit=24');
  assert.equal(
    hooks.detailUrl('abc/123', 101),
    '/api/v1/datasets/abc%2F123?before=101&limit=24',
  );
  const detail = hooks.normalizeDetail({
    session_id: 'abc_123',
    sample_count: 100,
    samples: Array.from({ length: 24 }, (_, offset) => ({
      sample_index: 77 + offset,
      sources: ['go2_front'],
    })),
    page: {
      limit: 24,
      before: 101,
      oldest_index: 77,
      newest_index: 100,
      next_before: 77,
      has_older: true,
    },
  });
  assert.equal(detail.samples.length, 24);
  assert.deepEqual({ ...detail.page }, {
    limit: 24,
    before: 101,
    oldestIndex: 77,
    newestIndex: 100,
    nextBefore: 77,
    hasOlder: true,
  });
  assert.match(indexSource, /id="datasetSessionList"/);
  assert.match(indexSource, /id="datasetSampleGallery"/);
  assert.match(appSource, /loading="lazy" decoding="async"/);
  assert.match(appSource, /target="_blank" rel="noopener noreferrer"/);
});

test('dataset status and folder polls discard stale overlapping responses', () => {
  assert.match(appSource, /const generation = \+\+datasetCapturePollGeneration/);
  assert.match(appSource, /generation !== datasetCapturePollGeneration/);
  assert.match(appSource, /const generation = \+\+datasetSessionsPollGeneration/);
  assert.match(appSource, /generation !== datasetSessionsPollGeneration/);
  assert.match(appSource, /const generation = \+\+datasetDetailPollGeneration/);
  assert.match(appSource, /generation !== datasetDetailPollGeneration \|\| sessionId !== selectedDatasetSessionId/);
  assert.match(appSource, /const newestPageChanged = selectedDatasetPageBefore == null && sampleCountChanged/);
  assert.match(appSource, /selectionChanged \|\| !selectedDatasetDetail \|\| forceDetail \|\| newestPageChanged/);
  assert.match(appSource, /if \(selectedDatasetGalleryKey === key\) return false/);
  assert.doesNotMatch(appSource, /selectionChanged \|\| activePage === 'sensors'/);
});

test('failed but still-active capture remains stoppable for recovery', () => {
  const hooks = datasetHooks();
  assert.equal(hooks.canStop({ sessionId: 'session_123', state: 'failed', active: true }), true);
  assert.equal(hooks.canStop({ sessionId: 'session_123', state: 'failed', active: false }), false);
  assert.equal(hooks.canStop({ sessionId: 'session_123', state: 'capturing', active: false }), true);
});

test('dataset pages expose bounded newest, newer and older navigation', () => {
  assert.match(indexSource, /id="datasetPageNewest"[^>]*>NEWEST</);
  assert.match(indexSource, /id="datasetPageNewer"[^>]*>NEWER</);
  assert.match(indexSource, /id="datasetPageOlder"[^>]*>OLDER</);
  assert.match(indexSource, /최대 24개 샘플/);
  assert.match(appSource, /navigateDatasetPage\('newest'\)/);
  assert.match(appSource, /navigateDatasetPage\('newer'\)/);
  assert.match(appSource, /navigateDatasetPage\('older'\)/);
  assert.match(stylesSource, /\.dataset-gallery-pagination\s*\{/);
});

test('Safari page lifecycle never stops a server dataset session', () => {
  const visibilityStart = appSource.indexOf("document.addEventListener('visibilitychange'");
  const pageHideStart = appSource.indexOf("window.addEventListener('pagehide'", visibilityStart);
  const unloadStart = appSource.indexOf("window.addEventListener('beforeunload'", pageHideStart);
  assert.ok(visibilityStart >= 0 && pageHideStart > visibilityStart && unloadStart > pageHideStart);
  const lifecycle = appSource.slice(visibilityStart, unloadStart);
  assert.match(lifecycle, /refreshDatasetCapture\(\)/);
  assert.doesNotMatch(lifecycle, /stopDatasetCapture\(/);
  assert.doesNotMatch(lifecycle, /sendBeacon/);
  assert.match(appSource, /setInterval\(refreshDatasetCapture, 1500\)/);
});

test('active or unknown server capture is named in service lifecycle blockers', () => {
  assert.match(serviceLifecycleSource, /dataset_capture_active:\s*'서버 데이터셋 수집 중'/);
  assert.match(serviceLifecycleSource, /dataset_capture_state_unknown:\s*'데이터셋 수집 상태 확인 불가'/);
});

test('dataset capture and gallery collapse safely on narrow screens', () => {
  assert.match(stylesSource, /@media \(max-width: 800px\)[\s\S]*?\.dataset-capture-layout, \.dataset-library-layout\s*\{\s*grid-template-columns:1fr/);
  assert.match(stylesSource, /@media \(max-width: 520px\)[\s\S]*?\.dataset-source-picker, \.dataset-capture-summary\s*\{\s*grid-template-columns:1fr/);
  assert.match(stylesSource, /\.dataset-sample-card img\s*\{[\s\S]*?object-fit:contain/);
});
