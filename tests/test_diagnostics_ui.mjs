import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { downloadApi, operatorRequestHeaders } from '../robot_dashboard/static/core/api.js';
import { createDiagnosticsExportFeature } from '../robot_dashboard/static/features/settings/diagnostics.js';

const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../robot_dashboard/static/core/api.js', import.meta.url), 'utf8');
const featureSource = readFileSync(new URL('../robot_dashboard/static/features/settings/diagnostics.js', import.meta.url), 'utf8');
const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
const stylesSource = readFileSync(new URL('../robot_dashboard/static/styles.css', import.meta.url), 'utf8');

function button() {
  const target = new EventTarget();
  target.disabled = false;
  target.click = () => target.dispatchEvent(new Event('click'));
  return target;
}

test('operator request headers identify only a browser session and monotonic request sequence', () => {
  const first = operatorRequestHeaders();
  const second = operatorRequestHeaders({
    Accept: 'application/zip',
    'X-Robot-Scope-Browser-Session': 'caller_must_not_override',
    'X-Robot-Scope-Request-Sequence': '9000',
  });
  assert.match(first['X-Robot-Scope-Browser-Session'], /^[A-Za-z0-9_-]{8,64}$/);
  assert.equal(first['X-Robot-Scope-Browser-Session'], second['X-Robot-Scope-Browser-Session']);
  assert.equal(Number(second['X-Robot-Scope-Request-Sequence']), Number(first['X-Robot-Scope-Request-Sequence']) + 1);
  assert.notEqual(second['X-Robot-Scope-Browser-Session'], 'caller_must_not_override');
  assert.equal(second.Accept, 'application/zip');
  assert.doesNotMatch(JSON.stringify(second), /credential|authorization|user[_-]?id/i);
});

test('download helper requires a bounded ZIP and a fixed filename', async () => {
  const originalFetch = globalThis.fetch;
  let received = null;
  globalThis.fetch = async (path, options) => {
    received = { path, options };
    return new Response(new Blob(['PK-safe'], { type: 'application/zip' }), {
      status: 200,
      headers: {
        'Content-Type': 'application/zip',
        'Content-Disposition': 'attachment; filename="robot-scope-diagnostics-20260823T054500Z.zip"',
      },
    });
  };
  try {
    const bundle = await downloadApi('/api/v1/system/diagnostics/export', { method: 'POST' });
    assert.equal(bundle.filename, 'robot-scope-diagnostics-20260823T054500Z.zip');
    assert.equal(received.path, '/api/v1/system/diagnostics/export');
    assert.equal(received.options.method, 'POST');
    assert.match(received.options.headers['X-Robot-Scope-Browser-Session'], /^[A-Za-z0-9_-]{8,64}$/);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.match(apiSource, /DIAGNOSTICS_MAX_DOWNLOAD_BYTES = 2 \* 1024 \* 1024/);
});

test('Settings export prevents duplicate requests and releases browser resources', async () => {
  const originalDocument = globalThis.document;
  const originalWindow = globalThis.window;
  const originalUrl = globalThis.URL;
  const created = [];
  const revoked = [];
  let clicked = 0;
  let resolveRequest;
  let requestCount = 0;
  const request = () => {
    requestCount += 1;
    return new Promise((resolve) => { resolveRequest = resolve; });
  };
  const ui = { button: button(), state: { textContent: '', className: '' }, message: { textContent: '' } };
  globalThis.document = {
    body: { append: (node) => created.push(node) },
    createElement: () => ({
      href: '', download: '', rel: '', hidden: false,
      click: () => { clicked += 1; }, remove: () => {},
    }),
  };
  globalThis.window = { setTimeout: (callback) => { callback(); return 1; } };
  globalThis.URL = {
    createObjectURL: () => 'blob:diagnostics',
    revokeObjectURL: (value) => revoked.push(value),
  };
  try {
    const feature = createDiagnosticsExportFeature({ ui, downloadApi: request, showToast: () => {} }).start();
    const first = feature.exportBundle();
    const duplicate = await feature.exportBundle();
    assert.equal(duplicate, null);
    assert.equal(requestCount, 1);
    assert.equal(feature.snapshot().busy, true);
    resolveRequest({ blob: new Blob(['zip']), filename: 'robot-scope-diagnostics-20260823T054500Z.zip' });
    assert.equal(await first, 'robot-scope-diagnostics-20260823T054500Z.zip');
    assert.equal(clicked, 1);
    assert.equal(created[0].download, 'robot-scope-diagnostics-20260823T054500Z.zip');
    assert.deepEqual(revoked, ['blob:diagnostics']);
    feature.destroy();
    assert.deepEqual(feature.snapshot(), { busy: false, destroyed: true, started: false });
    ui.button.click();
    assert.equal(requestCount, 1);
  } finally {
    globalThis.document = originalDocument;
    globalThis.window = originalWindow;
    globalThis.URL = originalUrl;
  }
});

test('diagnostics UI is an explicit read-only Settings surface', () => {
  for (const id of ['diagnosticsExportState', 'diagnosticsExportMessage', 'diagnosticsExportButton']) {
    assert.match(indexSource, new RegExp(`id="${id}"`));
  }
  assert.match(indexSource, /제어·매핑·Nav2·데이터셋 작업을 중지하지 않으며/);
  assert.match(featureSource, /'\/api\/v1\/system\/diagnostics\/export'/);
  assert.match(featureSource, /method: 'POST'/);
  assert.match(featureSource, /new AbortController\(\)/);
  assert.match(featureSource, /listeners\?\.abort\(\)/);
  assert.match(featureSource, /URL\.revokeObjectURL/);
  assert.match(appSource, /createDiagnosticsExportFeature\(\{ showToast \}\)\.start\(\)/);
  assert.match(stylesSource, /\.diagnostics-export-panel \{ grid-column:1\/-1; \}/);
  assert.doesNotMatch(featureSource, /control|navigation\/start|mapping\/start|service\/stop/);
});
