import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { initializeMapEditor3D, savedCloudEditorSource } from '../robot_dashboard/static/features/map_editor3d/workspace.js';

// Small deterministic DOM fixture. These are controller tests, not visual/browser
// assertions; tests/e2e/map_editor3d.spec.mjs covers the real browser separately.
class Element {
  constructor(tag, doc) { this.tagName = tag; this.ownerDocument = doc; this.children = []; this.attrs = {}; this.listeners = {}; this.dataset = {}; this.value = ''; this.hidden = false; this.disabled = false; this.checked = false; this.text = ''; }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return this.text + this.children.map((child) => child.textContent).join(''); }
  setAttribute(key, value) { this.attrs[key] = String(value); if (key === 'value') this.value = String(value); }
  append(...children) { for (const child of children) { child.parent = this; this.children.push(child); if (this.tagName === 'select' && this.children.length === 1) this.value = child.value; } }
  before(child) { child.parent = this.parent; this.parent.children.splice(this.parent.children.indexOf(this), 0, child); }
  after(child) { child.parent = this.parent; this.parent.children.splice(this.parent.children.indexOf(this) + 1, 0, child); }
  replaceChildren(...children) { this.children = []; this.text = ''; this.append(...children); }
  querySelector(selector) { for (const child of this.children) { if ((selector[0] === '#' && child.attrs.id === selector.slice(1)) || child.tagName === selector) return child; const found = child.querySelector(selector); if (found) return found; } return null; }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  async emit(type, event = {}) { for (const handler of this.listeners[type] || []) await handler({ preventDefault() {}, ...event }); }
  click() { if (!this.disabled) return this.emit('click'); }
  getBoundingClientRect() { return { left: 0, top: 0, width: 1100, height: 540 }; }
  getContext() { return this.context ||= { fills: [], fillRect(...args) { this.fills.push(args); }, rect() {}, fillText() {}, beginPath() {}, lineTo() {}, moveTo() {}, closePath() {}, setLineDash() {}, stroke() {}, fill() {} }; }
}

const fixtureSource = () => ({ kind: 'pointcloud3d', map_id: '3'.repeat(24), revision: 'b'.repeat(64), frame_id: 'map', points: [-5, -5, 0, 0, 0, 0, 5, 5, 0] });

function mount(t, initialSource = fixtureSource()) {
  const document = { createElement(tag) { return new Element(tag, document); } };
  const panel = document.createElement('article');
  for (const [tag, id] of [['h2', 'heading'], ['div', 'mapEditorState'], ['div', 'mapEditor2D']]) { const element = document.createElement(tag); element.setAttribute('id', id); panel.append(element); }
  const listeners = {}, downloads = []; let source = initialSource, redraws = 0, confirmValue = true, confirms = 0, writes = 0;
  for (const [name, value] of Object.entries({ addEventListener: (name, handler) => { listeners[name] = handler; }, confirm: () => { confirms += 1; return confirmValue; }, fetch: () => { writes += 1; throw new Error('No network activity is permitted by this controller'); } })) {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, { value, configurable: true, writable: true });
    t.after(() => descriptor ? Object.defineProperty(globalThis, name, descriptor) : delete globalThis[name]);
  }
  t.mock.method(URL, 'createObjectURL', (blob) => { downloads.push(blob); return 'blob:map-editor-test'; });
  t.mock.method(URL, 'revokeObjectURL', () => {});
  const controller = initializeMapEditor3D({ panel, getSource: () => source, is2DDirty: () => true, redraw2D: () => { redraws += 1; } });
  const $ = (id) => panel.querySelector(`#${id}`);
  return { $, panel, controller, downloads, listeners, get redraws() { return redraws; }, get writes() { return writes; }, get confirms() { return confirms; }, setSource(value) { source = value; }, setConfirm(value) { confirmValue = value; } };
}

async function polygon(fixture, points = [[500, 320], [600, 320], [600, 220], [500, 220]]) {
  for (const [clientX, clientY] of points) await fixture.$('map3Canvas').emit('click', { clientX, clientY });
}

async function importJson(fixture, text, size = Buffer.byteLength(text)) {
  fixture.$('map3Import').files = [{ size, text: async () => text }];
  await fixture.$('map3Import').emit('change');
}

test('3D workspace is mutually exclusive in the existing panel and preserves each mode draft', async (t) => {
  const f = mount(t);
  assert.equal(f.controller.mode, '2d'); assert.equal(f.$('mapEditor2D').hidden, false); assert.equal(f.$('mapEditor3D').hidden, true);
  f.$('mapEditor2D').draftSentinel = 'unsaved 2D cells';
  f.controller.setMode('3d'); await f.$('map3Load').click(); await polygon(f); await f.$('map3Add').click();
  assert.equal(f.$('map3Regions').children.length, 1);
  assert.equal(f.$('mapEditor2D').hidden, true); assert.equal(f.$('mapEditorState').hidden, true);
  assert.equal(f.$('mapEditor3D').hidden, false);
  f.controller.setMode('2d'); assert.equal(f.redraws, 1); assert.equal(f.$('mapEditor2D').draftSentinel, 'unsaved 2D cells');
  f.controller.setMode('3d'); assert.equal(f.$('map3Regions').children.length, 1);
  assert.match(f.$('map3Status').textContent, /초안/); assert.throws(() => f.controller.setMode('both'), /Unknown/);
  assert.equal(f.$('mapEditor3D').parent, f.$('mapEditor2D').parent);
});

test('3D polygon selection, keyboard cancellation, undo, redo, and reset are reversible', async (t) => {
  const f = mount(t); f.controller.setMode('3d'); await f.$('map3Load').click();
  await polygon(f, [[500, 320], [600, 320], [600, 220]]);
  assert.equal(f.$('map3Add').disabled, false);
  await f.$('map3Canvas').emit('keydown', { key: 'Backspace' }); assert.equal(f.$('map3Add').disabled, true);
  await f.$('map3Canvas').emit('keydown', { key: 'Escape' }); assert.match(f.$('map3Stats').textContent, /선택 0 vertices/);
  await polygon(f); await f.$('map3Add').click(); assert.match(f.$('map3Stats').textContent, /숨김 1/);
  await f.$('map3Undo').click(); assert.equal(f.$('map3Regions').children.length, 0); assert.equal(f.$('map3Redo').disabled, false);
  await f.$('map3Redo').click(); assert.equal(f.$('map3Regions').children.length, 1);
  f.setConfirm(false); await f.$('map3Reset').click(); assert.equal(f.$('map3Regions').children.length, 1);
  f.setConfirm(true); await f.$('map3Reset').click(); assert.equal(f.$('map3Regions').children.length, 0);
  await f.$('map3Undo').click(); assert.equal(f.$('map3Regions').children.length, 1);
  let prevented = false; f.listeners.beforeunload({ preventDefault() { prevented = true; } }); assert.equal(prevented, true);
});

test('3D workspace rejects blank, nonfinite, inverted heights and self-intersection without changing draft', async (t) => {
  const f = mount(t); f.controller.setMode('3d'); await f.$('map3Load').click(); await polygon(f);
  for (const [min, max] of [['', '1'], ['NaN', '1'], ['Infinity', '1'], ['2', '1']]) {
    f.$('map3ZMin').value = min; f.$('map3ZMax').value = max; await f.$('map3Add').click();
    assert.equal(f.$('map3Status').dataset.error, 'true'); assert.equal(f.$('map3Regions').children.length, 0); assert.match(f.$('map3Stats').textContent, /선택 4 vertices/);
  }
  f.$('map3ZMin').value = '-1'; f.$('map3ZMax').value = '1'; await f.$('map3Cancel').click();
  await polygon(f, [[500, 320], [600, 220], [600, 320], [500, 220]]); await f.$('map3Add').click();
  assert.match(f.$('map3Status').textContent, /self-intersect/); assert.equal(f.$('map3Regions').children.length, 0);
});

test('3D preview only hides visibility points and local file export/import never writes to network', async (t) => {
  const f = mount(t); f.controller.setMode('3d'); await f.$('map3Load').click();
  for (const kind of ['visibility', 'localization', 'keepout']) { f.$('map3Kind').value = kind; await polygon(f); await f.$('map3Add').click(); }
  assert.match(f.$('map3Stats').textContent, /숨김 1 \/ 위치추정 제외 1 \/ 진입금지 1/);
  const canvas = f.$('map3Canvas'), before = canvas.getContext().fills.length;
  f.$('map3Preview').checked = true; await f.$('map3Preview').emit('change');
  // One background plus two visible points, plus twelve region-vertex markers.
  assert.equal(canvas.getContext().fills.length - before, 15);
  await f.$('map3Export').click(); assert.equal(f.downloads.length, 1);
  const version = JSON.parse(await f.downloads[0].text());
  assert.equal(version.runtime_installed, false); assert.equal(version.regions.length, 3); assert.equal(version.source.frame_id, 'map');
  assert.equal(Object.hasOwn(version, 'points'), false); assert.doesNotMatch(f.$('map3Status').textContent, /초안/);
  await f.$('map3Reset').click(); assert.equal(f.$('map3Regions').children.length, 0);
  await importJson(f, JSON.stringify(version)); assert.equal(f.$('map3Regions').children.length, 3);
  assert.equal(f.writes, 0);
});

test('3D bad imports, source replacement cancellation, and oversized files preserve the loaded draft', async (t) => {
  const f = mount(t); f.controller.setMode('3d'); await f.$('map3Load').click(); await polygon(f); await f.$('map3Add').click(); await f.$('map3Export').click();
  const original = JSON.parse(await f.downloads[0].text());
  const badVersions = [
    '{',
    JSON.stringify({ ...original, schema_version: 999 }),
    JSON.stringify({ ...original, source: { ...original.source, revision: 'different' } }),
    JSON.stringify({ ...original, runtime_installed: true }),
    JSON.stringify({ ...original, unexpected: 'field' }),
  ];
  for (const value of badVersions) { await importJson(f, value); assert.equal(f.$('map3Status').dataset.error, 'true'); assert.equal(f.$('map3Regions').children.length, 1); }
  await importJson(f, JSON.stringify(original), 2 * 1024 * 1024 + 1); assert.match(f.$('map3Status').textContent, /2 MB/);
  await polygon(f); f.setConfirm(false); f.setSource({ ...fixtureSource(), map_id: 'other-map' }); await f.$('map3Load').click();
  assert.match(f.$('map3Stats').textContent, new RegExp(fixtureSource().map_id)); assert.equal(f.$('map3Regions').children.length, 1);
  assert.equal(f.writes, 0);
});

test('3D controls fail closed without a point cloud or source identity', async (t) => {
  const f = mount(t, null); f.controller.setMode('3d'); await f.$('map3Load').click();
  assert.equal(f.$('map3Add').disabled, true); assert.equal(f.$('map3Export').disabled, true); assert.equal(f.$('map3Import').disabled, true);
  assert.equal(f.$('map3Status').dataset.error, 'true');
  f.setSource({ ...fixtureSource(), frame_id: '' }); await f.$('map3Load').click(); assert.equal(f.$('map3Export').disabled, true);
});

test('integration keeps the 2D engine intact and gates rendering of both map editor modes', () => {
  const index = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
  const app = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
  const css = readFileSync(new URL('../robot_dashboard/static/features/map_editor3d/editor.css', import.meta.url), 'utf8');
  const workspace = readFileSync(new URL('../robot_dashboard/static/features/map_editor3d/workspace.js', import.meta.url), 'utf8');
  assert.match(index, /id="mapEditor2D"/); assert.match(index, /features\/map_editor3d\/editor\.css/);
  assert.match(app, /initializeMapEditor3D\(/);
  assert.match(app, /getSource: \(\) => savedCloudEditorSource\(selectedSavedMapMeta, offlineCloudSnapshot\)/); assert.match(app, /is2DDirty:.*mapEditorHasChanges/);
  for (const id of ['mapEditor2D', 'mapEditor3D']) assert.ok(css.includes(`#${id}[hidden]`));
  assert.doesNotMatch(workspace, /fetch\(|\/api\/|WebSocket|sendBeacon/);
});

test('outside-course selection exports separate filtered copies and marks uncertain source completeness', async (t) => {
  const f = mount(t, { ...fixtureSource(), source_points: 3 }); f.controller.setMode('3d'); await f.$('map3Load').click();
  f.$('map3Selection').value = 'outside'; await polygon(f); await f.$('map3Add').click();
  assert.match(f.$('map3Stats').textContent, /숨김 2/); assert.notEqual(f.$('map3Status').dataset.error, 'true');
  await f.$('map3CopyExport').click();
  assert.notEqual(f.$('map3Status').dataset.error, 'true');
  const display = JSON.parse(await f.downloads[0].text());
  assert.equal(display.schema, 'robot-dashboard.edited-cloud-copy'); assert.equal(display.preview_only, false); assert.equal(display.runtime_installed, false);
  assert.equal(display.source_scope, 'complete-normalized-snapshot'); assert.equal(display.purpose, 'visibility');
  assert.equal(display.loaded_points, 3); assert.equal(display.output_points, 1); assert.deepEqual(display.points, [0, 0, 0]);
  assert.equal(display.regions[0].selection, 'outside'); assert.equal(display.units, 'm');
  f.$('map3Kind').value = 'localization'; f.$('map3Selection').value = 'inside'; await polygon(f); await f.$('map3Add').click();
  f.$('map3CopyPurpose').value = 'localization'; await f.$('map3CopyExport').click();
  const localization = JSON.parse(await f.downloads[1].text());
  assert.equal(localization.purpose, 'localization'); assert.equal(localization.output_points, 2); assert.deepEqual(localization.points, [-5, -5, 0, 5, 5, 0]);
  assert.notEqual(display.version_id, localization.version_id);
  f.setSource({ ...fixtureSource(), source_points: 99 }); await f.$('map3Load').click(); await f.$('map3CopyExport').click();
  const sample = JSON.parse(await f.downloads[2].text());
  assert.equal(sample.preview_only, true); assert.equal(sample.source_scope, 'sampled-or-unverified-preview'); assert.equal(sample.source_points, 99);
  assert.match(f.$('map3Status').textContent, /PREVIEW ONLY/); assert.equal(f.writes, 0);
});

test('file imports cannot replace a draft edited during the asynchronous file read', async (t) => {
  const f = mount(t); f.controller.setMode('3d'); await f.$('map3Load').click(); await polygon(f); await f.$('map3Add').click(); await f.$('map3Export').click();
  const exported = await f.downloads[0].text(); let release;
  f.$('map3Import').files = [{ size: exported.length, text: () => new Promise((resolve) => { release = resolve; }) }];
  const reading = f.$('map3Import').emit('change');
  await polygon(f, [[500, 320]]); release(exported); await reading;
  assert.equal(f.$('map3Status').dataset.error, 'true'); assert.match(f.$('map3Stats').textContent, /선택 1 vertices/); assert.equal(f.$('map3Regions').children.length, 1);
  await f.$('map3CopyExport').click(); assert.equal(f.downloads.length, 1); assert.equal(f.$('map3Status').dataset.error, 'true');
});

test('dashboard source adapter refuses stale clouds and propagates original coordinates and completeness', () => {
  const getSource = savedCloudEditorSource;
  const meta = { id: 'selected-map', kind: 'pointcloud3d', revision: 'revision-1' };
  const snapshot = { map_id: 'selected-map', revision: 'revision-1', frame_id: 'odom', source_points: 7, points: [11, 12, 13] };
  const source = getSource(meta, snapshot);
  assert.deepEqual(source, { kind: 'pointcloud3d', map_id: meta.id, revision: snapshot.revision, frame_id: 'odom', source_points: 7, points: snapshot.points });
  assert.equal(source.points, snapshot.points);
  assert.equal(getSource(meta, { ...snapshot, map_id: 'other-map' }), null);
  assert.equal(getSource(meta, { ...snapshot, revision: 'revision-2' }), null);
  assert.equal(getSource(meta, { ...snapshot, points: [] }), null);
  assert.equal(getSource({ ...meta, kind: 'occupancy2d' }, snapshot), null);
  assert.equal(getSource(null, snapshot), null); assert.equal(getSource(meta, null), null);
});
