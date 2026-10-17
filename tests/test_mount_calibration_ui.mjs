import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../robot_dashboard/static/features/settings/mount_calibration.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
const app = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const css = readFileSync(new URL('../robot_dashboard/static/features/settings/mount_calibration.css', import.meta.url), 'utf8');
const prefix = 'mount-calibration-';
const assertions = ['stationary-check', 'wall-check', 'pitch-check'];
const flush = () => new Promise((resolve) => setImmediate(resolve));
const deferred = () => { let resolve; const promise = new Promise((r) => { resolve = r; }); return { promise, resolve }; };

class Element {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.listeners = new Map(); this.attributes = {};
    this.hidden = false; this.disabled = false; this.checked = false; this.value = ''; this.files = [];
    this.className = ''; this._text = ''; this.parentElement = null;
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  append(...nodes) {
    for (const node of nodes) {
      if (node.tagName === 'fragment') this.append(...node.children);
      else { node.parentElement = this; this.children.push(node); }
    }
  }
  replaceChildren(...nodes) { this.children = []; this._text = ''; this.append(...nodes); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name]; }
  addEventListener(type, fn) { if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(fn); }
  removeEventListener(type, fn) { this.listeners.get(type)?.delete(fn); }
  dispatch(type, init = {}) {
    const event = { target: this, currentTarget: this, preventDefault() {}, ...init };
    const results = [...(this.listeners.get(type) || [])].map((fn) => fn(event));
    // Browser dispatch clears currentTarget before an async file read completes.
    event.currentTarget = null;
    return Promise.all(results);
  }
  click() { return this.disabled ? Promise.resolve() : this.dispatch('click'); }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter((child) => child !== this); }
  getBoundingClientRect() { return { left: 0, top: 0, width: this.width, height: this.height }; }
  getContext() {
    return { createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }),
      putImageData() {}, drawImage() {}, beginPath() {}, arc() {}, fill() {}, stroke() {},
      fillRect() {}, fillText() {}, measureText: (text) => ({ width: text.length * 6 }) };
  }
}

function descendants(element, predicate) {
  return element.children.flatMap((child) => [...(predicate(child) ? [child] : []), ...descendants(child, predicate)]);
}
function byClass(element, name) { return descendants(element, (child) => child.className.split(' ').includes(name)); }
function sample(id = 'capture-a', { synthetic = false, points } = {}) {
  return {
    id, width: 40, height: 30, intrinsics: { fx: 36, fy: 36, cx: 20, cy: 15, model: 'pinhole' },
    depth_m: Array(1200).fill(2.2),
    points: points || [{ u: 4, v: 4 }, { u: 20, v: 4 }, { u: 35, v: 4 }, { u: 4, v: 25 }, { u: 20, v: 25 }, { u: 35, v: 25 }],
    metadata: { synthetic, rectified: true, serial: synthetic ? 'SYNTHETIC' : 'test-device', frame_id: 'camera_depth_optical_frame',
      profile_id: '40x30', depth_semantics: 'optical_z', source_timestamp: 10, clock_domain: 'test' },
  };
}
function analysis(input, override = {}) {
  return { reference_id: input.reference_id, synthetic: input.samples.every((s) => s.metadata.synthetic),
    pitch_only_consistent: true, status: 'RELATIVE_ONLY', body_extrinsic_validated: false,
    samples: input.samples.map((s, index) => ({ id: s.id, relative_pitch_deg: index === 0 ? 0 : 10,
      plane_rmse_m: .0002, inlier_points: s.points.length, valid_points: s.points.length, inlier_ratio: 1,
      normal_camera: [0, 0, -1], warnings: [], validated_points: s.points.map((point) => ({ ...point, valid: true, inlier: true })) })), ...override };
}
function harness(handler) {
  const elements = new Map();
  for (const match of html.matchAll(/id="(mount-calibration-[^"]+)"/g)) elements.set(match[1], new Element());
  const el = (id) => elements.get(prefix + id);
  for (const id of ['depth-min', 'depth-max']) el(id).parentElement = new Element();
  const allocations = { canvas: 0 };
  const document = { getElementById: (id) => elements.get(id), body: new Element('body'),
    createDocumentFragment: () => new Element('fragment'),
    createElement: (tag) => { if (tag === 'canvas') allocations.canvas += 1; return new Element(tag); } };
  const calls = [], downloads = [];
  const api = async (path, options = {}) => {
    const call = { path, options }; calls.push(call);
    if (handler) { const value = handler(call); if (value !== undefined) return value; }
    if (path.endsWith('/status')) return { live_capture_available: false };
    const input = JSON.parse(options.body);
    return path.endsWith('/export') ? { input, analysis: analysis(input) } : analysis(input);
  };
  const context = { AbortController, Blob, document, api, setTimeout: (fn) => { fn(); return 0; },
    URL: { createObjectURL: (blob) => { downloads.push(blob); return 'blob:unit'; }, revokeObjectURL() {} } };
  vm.runInNewContext(source.replace(/^import[^\n]+\n/, '').replace('export function initializeMountCalibrationFeature', 'function initializeMountCalibrationFeature') + '\nthis.initialize = initializeMountCalibrationFeature;', context);
  const feature = context.initialize({ document, api });
  const importFiles = (values) => {
    el('file-input').files = values.map((value, index) => value.text ? value : ({ name: `capture-${index}.json`, size: 100, text: async () => JSON.stringify(value) }));
    return el('file-input').dispatch('change');
  };
  const confirm = async () => { for (const id of assertions) { el(id).checked = true; await el(id).dispatch('change'); } };
  return { el, feature, calls, downloads, allocations, context, document, api, importFiles, confirm };
}

test('native Settings integration is scoped and never embeds the standalone prototype', () => {
  const start = html.indexOf('data-page="settings"');
  const feature = html.indexOf('id="mount-calibration-panel"');
  assert.ok(feature > start && feature < html.indexOf('data-page="resources"', start));
  assert.match(app, /import \{ initializeMountCalibrationFeature \} from '\.\/features\/settings\/mount_calibration\.js'/);
  assert.match(app, /initializeMountCalibrationFeature\(\)/);
  assert.match(html, /카메라 장착 각도 보정/);
  assert.match(html, /mount-calibration-file-input[^>]+multiple/);
  assert.doesNotMatch(html.slice(feature, html.indexOf('control-bridge-service-panel', feature)), /<iframe|Mount Lab|workspace-footer|disabled-action/);
  assert.match(css, /\.settings-grid > \.mount-calibration \{ grid-column: 1 \/ -1/);
  assert.match(css, /var\(--font-ui\)/);
  assert.doesNotMatch(css, /:root|@import|font-family:\s*(?:Inter|Pretendard)/);
  const ids = [...html.matchAll(/id="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(ids.length, new Set(ids).size, 'dashboard IDs remain unique');
});

test('initialization is idempotent, empty and read-only without fixture allocation', async () => {
  const h = harness(); await flush();
  assert.equal(h.feature.snapshot().sampleCount, 0);
  assert.equal(h.allocations.canvas, 0);
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].path, '/api/v1/settings/mount-calibration/status');
  assert.equal(h.calls[0].options.method, undefined);
  assert.equal(h.el('estimate-button').disabled, true);
  assert.equal(h.el('export-button').disabled, true);
  assert.equal(h.el('depth-empty').hidden, false);
  for (const id of assertions) assert.equal(h.el(id).checked, false);
  assert.equal(h.context.initialize({ document: h.document, api: h.api }), h.feature);
  assert.equal(h.el('demo-button').listeners.get('click').size, 1);
});

test('demo is explicit, synthetic, unchecked, and estimate sends only the shared settings contract', async () => {
  const h = harness();
  await h.el('demo-button').click();
  assert.equal(h.feature.snapshot().sampleCount, 3);
  assert.equal(h.allocations.canvas, 1, 'only the selected capture heatmap is built');
  assert.equal(h.calls.length, 1, 'demo does not request analysis');
  for (const id of assertions) assert.equal(h.el(id).checked, false);
  await h.confirm(); await h.el('estimate-button').click();
  const last = h.calls.at(-1);
  assert.equal(last.path, '/api/v1/settings/mount-calibration/estimate');
  assert.equal(last.options.method, 'POST');
  assert.ok(last.options.signal instanceof AbortSignal);
  const input = JSON.parse(last.options.body);
  assert.deepEqual(input.samples.map((s) => s.metadata.fixture_pitch_deg), [0, 10, -8]);
  assert.ok(input.samples.every((s) => s.metadata.synthetic));
  assert.equal(h.el('results-content').hidden, false);
  assert.equal(h.el('results-body').children.length, 3);
  assert.match(h.el('results-summary').textContent, /합성 데모 분석/);
});

test('multi-file import is atomic and survives dispatch currentTarget lifetime', async () => {
  const h = harness();
  await h.importFiles([sample('a'), sample('b')]);
  assert.equal(h.feature.snapshot().sampleCount, 2);
  assert.equal(h.feature.snapshot().referenceId, 'a');
  assert.match(h.el('notice').textContent, /파일 2개에서 촬영 2개/);
  await h.confirm();
  assert.equal(h.el('estimate-button').disabled, false);
  await h.importFiles([sample('new'), { invalid: true }]);
  assert.equal(h.feature.snapshot().sampleCount, 2);
  assert.equal(h.feature.snapshot().referenceId, 'a', 'failed import leaves previous captures intact');
  assert.match(h.el('notice').textContent, /가져오기 실패/);
});

test('imports accept an exported input, clear all assertions and never trust exported analysis', async () => {
  const h = harness(); await h.importFiles([sample('a'), sample('b')]); await h.confirm(); await h.el('estimate-button').click();
  await h.importFiles([{ input: { samples: [sample('c'), sample('d')], reference_id: 'd' }, analysis: { status: 'FAKE_VALIDATED' } }]);
  assert.equal(h.feature.snapshot().referenceId, 'd');
  assert.equal(h.feature.snapshot().hasResult, false);
  assert.equal(h.el('export-button').disabled, true);
  for (const id of assertions) assert.equal(h.el(id).checked, false);
});

test('imports reject duplicate IDs, mixed provenance, too many captures and total oversize', async () => {
  const h = harness();
  for (const files of [
    [sample('a'), sample('a')],
    [sample('a'), sample('b', { synthetic: true })],
    [{ samples: Array.from({ length: 13 }, (_, i) => sample(String(i))) }],
    [{ size: 31 * 1024 * 1024, text: async () => { throw Error('must not read oversize data'); } }],
  ]) {
    await h.importFiles(files);
    assert.equal(h.feature.snapshot().sampleCount, 0);
    assert.match(h.el('notice').textContent, /가져오기 실패/);
  }
});

test('at least six valid, non-collinear and spread points are required on every capture', async () => {
  const h = harness();
  for (const points of [sample().points.slice(0, 5), Array.from({ length: 6 }, (_, u) => ({ u: u * 5, v: 10 }))]) {
    await h.importFiles([sample('a'), sample('b', { points })]); await h.confirm();
    assert.equal(h.el('estimate-button').disabled, true);
  }
  const narrow = sample('b', { points: [{ u: 1, v: 1 }, { u: 2, v: 1 }, { u: 3, v: 1 }, { u: 1, v: 2 }, { u: 2, v: 2 }, { u: 3, v: 2 }] });
  narrow.width = 200; narrow.height = 200; narrow.depth_m = Array(40000).fill(2.2);
  await h.importFiles([sample('a'), narrow]); await h.confirm();
  assert.equal(h.el('estimate-button').disabled, true, 'tightly clustered points fail spread gate');
  const invalidDepth = sample('b'); invalidDepth.depth_m[4 * 40 + 4] = null;
  await h.importFiles([sample('a'), invalidDepth]); await h.confirm();
  assert.equal(h.el('estimate-button').disabled, true);
});

test('viewing a capture preserves results; a reference, point, or assertion change invalidates', async () => {
  const h = harness(); await h.importFiles([sample('a'), sample('b')]); await h.confirm(); await h.el('estimate-button').click();
  await byClass(h.el('sample-list'), 'sample-select')[1].click();
  assert.equal(h.feature.snapshot().selectedId, 'b'); assert.equal(h.feature.snapshot().hasResult, true);
  assert.equal(h.el('schematic-angle').textContent, '+10.00°');
  const radios = descendants(h.el('sample-list'), (e) => e.type === 'radio');
  await radios[1].dispatch('change');
  assert.equal(h.feature.snapshot().referenceId, 'b'); assert.equal(h.feature.snapshot().hasResult, false);
  await h.el('estimate-button').click();
  h.el('point-u').value = '10'; h.el('point-v').value = '12'; await h.el('point-form').dispatch('submit');
  assert.equal(h.feature.snapshot().hasResult, false);
  await h.el('estimate-button').click();
  h.el('pitch-check').checked = false; await h.el('pitch-check').dispatch('change');
  assert.equal(h.feature.snapshot().hasResult, false); assert.equal(h.el('estimate-button').disabled, true);
});

test('a point change aborts in-flight estimates and late responses cannot restore stale results', async () => {
  const gate = deferred(); const h = harness(({ path }) => path.endsWith('/estimate') ? gate.promise : undefined);
  await h.importFiles([sample('a'), sample('b')]); await h.confirm();
  const pending = h.el('estimate-button').click();
  const call = h.calls.at(-1); const input = JSON.parse(call.options.body);
  assert.equal(h.feature.snapshot().busy, true);
  await h.el('undo-button').click();
  assert.equal(call.options.signal.aborted, true);
  gate.resolve(analysis(input)); await pending;
  assert.equal(h.feature.snapshot().hasResult, false); assert.equal(h.el('results-content').hidden, true);
  assert.equal(h.el('export-button').disabled, true);
});

test('new imports or demo choices supersede older file reads', async () => {
  const gate = deferred(); const h = harness();
  const pending = h.importFiles([{ size: 100, text: () => gate.promise }]);
  await h.importFiles([sample('new-a'), sample('new-b')]);
  gate.resolve(JSON.stringify({ samples: [sample('old-a'), sample('old-b')] })); await pending;
  assert.equal(h.feature.snapshot().referenceId, 'new-a');
  const gate2 = deferred(); const pending2 = h.importFiles([{ size: 100, text: () => gate2.promise }]);
  await h.el('demo-button').click(); gate2.resolve(JSON.stringify(sample('late'))); await pending2;
  assert.equal(h.feature.snapshot().sampleCount, 3); assert.match(h.feature.snapshot().referenceId, /데모/);
});

test('nullable angles and quality warnings are preserved without displaying a false zero', async () => {
  const h = harness(({ path, options }) => {
    if (!path.endsWith('/estimate')) return;
    const result = analysis(JSON.parse(options.body)); result.pitch_only_consistent = false;
    result.samples[1].relative_pitch_deg = null; result.samples[1].warnings = ['quality_warning'];
    return result;
  });
  await h.importFiles([sample('a'), sample('b')]); await h.confirm(); await h.el('estimate-button').click();
  assert.match(h.el('results-body').children[1].textContent, /추정 보류/);
  assert.match(h.el('result-warnings').textContent, /quality_warning/);
  await byClass(h.el('sample-list'), 'sample-select')[1].click();
  assert.equal(h.el('schematic-angle').textContent, '보류');
});

test('export recomputes current raw input and downloads a relative-only analysis', async () => {
  const h = harness(); await h.importFiles([sample('a'), sample('b')]); await h.confirm(); await h.el('estimate-button').click();
  await h.el('export-button').click();
  assert.equal(h.calls.at(-1).path, '/api/v1/settings/mount-calibration/export');
  assert.equal(h.downloads.length, 1);
  const result = JSON.parse(await h.downloads[0].text());
  assert.equal(result.input.samples[0].depth_m.length, 1200);
  assert.equal(result.input.samples[0].points.length, 6);
  assert.equal(result.analysis.body_extrinsic_validated, false);
  assert.equal(h.el('export-button').disabled, false);
});

test('destroy removes static handlers, aborts status/analysis and invalidates asynchronous imports', async () => {
  const status = deferred(), imported = deferred();
  const h = harness(({ path }) => path.endsWith('/status') ? status.promise : undefined);
  const pending = h.importFiles([{ size: 100, text: () => imported.promise }]);
  h.feature.destroy();
  assert.equal(h.calls[0].options.signal.aborted, true);
  imported.resolve(JSON.stringify(sample())); status.resolve({ live_capture_available: false }); await pending; await flush();
  assert.equal(h.feature.snapshot().sampleCount, 0);
  assert.equal(h.feature.snapshot().destroyed, true);
  assert.equal(h.el('demo-button').listeners.get('click').size, 0);
  const restarted = h.context.initialize({ document: h.document, api: h.api });
  assert.notEqual(restarted, h.feature);
  assert.equal(h.el('demo-button').listeners.get('click').size, 1);
});
