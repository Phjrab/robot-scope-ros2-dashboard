import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const moduleSource = readFileSync(
  new URL('../robot_dashboard/static/map_annotations.js', import.meta.url),
  'utf8',
);
const indexSource = readFileSync(
  new URL('../robot_dashboard/static/index.html', import.meta.url),
  'utf8',
);
const appSource = readFileSync(
  new URL('../robot_dashboard/static/app.js', import.meta.url),
  'utf8',
);
const stylesSource = readFileSync(
  new URL('../robot_dashboard/static/styles.css', import.meta.url),
  'utf8',
);

function moduleHarness() {
  const sandbox = { Object, Number, String, TypeError };
  sandbox.window = sandbox;
  vm.runInNewContext(moduleSource, sandbox);
  return sandbox.RobotMapAnnotations;
}

function payload(overrides = {}) {
  return {
    schema_version: 1,
    map_id: 'a'.repeat(24),
    map_revision: 'b'.repeat(64),
    annotation_revision: 'c'.repeat(64),
    revision: 'c'.repeat(64),
    exists: true,
    points: [{
      id: 'd'.repeat(24),
      type: 'HOME',
      name: 'Home 1',
      pose: { x: 1, y: 2, yaw: 0.5 },
    }],
    polygons: [{
      id: 'e'.repeat(24),
      type: 'WAIT_ZONE',
      name: 'Wait Zone',
      vertices: [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 0, y: 1 }],
    }],
    ...overrides,
  };
}

test('annotation projection accepts only the fixed schema, pins and type sets', () => {
  const annotations = moduleHarness();
  const normalized = annotations.normalizeDocument(
    payload(),
    'a'.repeat(24),
    'b'.repeat(64),
  );
  assert.deepEqual([...annotations.POINT_TYPES], ['POI', 'HOME', 'DOCK', 'INSPECTION_POINT']);
  assert.deepEqual([...annotations.POLYGON_TYPES], ['KEEP_OUT', 'SLOW_ZONE', 'WAIT_ZONE']);
  assert.equal(normalized.points[0].type, 'HOME');
  assert.equal(normalized.polygons[0].vertices.length, 3);
  assert.throws(
    () => annotations.normalizeDocument(payload({ map_revision: 'f'.repeat(64) }), 'a'.repeat(24), 'b'.repeat(64)),
    /map revision changed/,
  );
  assert.throws(
    () => annotations.normalizeDocument(payload({ points: [{ ...payload().points[0], type: 'SHELL' }] }), 'a'.repeat(24), 'b'.repeat(64)),
    /point type/,
  );
});

test('editable drafts cannot mutate a server snapshot and request keeps both CAS pins', () => {
  const annotations = moduleHarness();
  const normalized = annotations.normalizeDocument(payload(), 'a'.repeat(24), 'b'.repeat(64));
  const draft = annotations.editableCopy(normalized);
  draft.points[0].pose.x = 9;
  draft.polygons[0].vertices[0].x = 8;
  assert.equal(normalized.points[0].pose.x, 1);
  assert.equal(normalized.polygons[0].vertices[0].x, 0);
  const body = annotations.requestBody(normalized, draft);
  assert.equal(body.map_revision, 'b'.repeat(64));
  assert.equal(body.base_annotation_revision, 'c'.repeat(64));
  assert.equal(body.points[0].pose.x, 9);
  assert.equal(body.polygons[0].vertices[0].x, 8);
  assert.deepEqual(Object.keys(body).sort(), [
    'base_annotation_revision', 'map_revision', 'points', 'polygons',
  ]);
});

test('names and geometry are bounded before a mutation is sent', () => {
  const annotations = moduleHarness();
  assert.equal(annotations.normalizeName('  출입구 1  '), '출입구 1');
  assert.throws(() => annotations.normalizeName('../secret'), /invalid/);
  assert.throws(() => annotations.normalizeName('emoji 🚗'), /invalid/);
  const normalized = annotations.normalizeDocument(payload(), 'a'.repeat(24), 'b'.repeat(64));
  const draft = annotations.editableCopy(normalized);
  draft.polygons[0].vertices = draft.polygons[0].vertices.slice(0, 2);
  assert.throws(() => annotations.requestBody(normalized, draft), /vertex count/);
});

test('Navigation UI exposes bounded annotation editing and revision-pinned goal APIs', () => {
  assert.match(indexSource, /\/static\/map_annotations\.js/);
  for (const id of [
    'mapAnnotationState', 'mapAnnotationType', 'mapAnnotationName',
    'mapAnnotationDraw', 'mapAnnotationFinish', 'mapAnnotationCancel',
    'mapAnnotationList', 'mapAnnotationDiscard', 'mapAnnotationSave',
  ]) assert.match(indexSource, new RegExp(`id="${id}"`));
  assert.match(indexSource, /costmap을 자동 변경하지 않습니다/);
  assert.match(stylesSource, /\.map-annotation-panel/);
  assert.ok(moduleSource.includes('/api/v1/saved-maps/${encodeURIComponent(meta.id)}/annotations'));
  assert.ok(moduleSource.includes('/api/v1/navigation/goal/annotation'));
  assert.match(moduleSource, /base_annotation_revision/);
  assert.match(moduleSource, /confirmed: true/);
  assert.match(appSource, /mapAnnotationEngine\?\.createFeature/);
});

test('annotation editor is fail-closed during Nav2 and reuses the normal goal gate', () => {
  const editingStart = moduleSource.indexOf('function editingAllowed(');
  const editingEnd = moduleSource.indexOf('\n    function goalAllowed(', editingStart);
  const editing = moduleSource.slice(editingStart, editingEnd);
  assert.match(editing, /!state\.pipelineActive/);
  assert.match(editing, /!state\.operationBusy/);
  assert.match(editing, /!busy/);

  const goalStart = moduleSource.indexOf('function goalAllowed(');
  const goalEnd = moduleSource.indexOf('\n    function render(', goalStart);
  const goal = moduleSource.slice(goalStart, goalEnd);
  assert.match(goal, /!dirty/);
  assert.match(goal, /context\(\)\.goalAllowed/);
  assert.match(appSource, /goalAllowed: navigationPoseToolAllowed\('goal'\)/);
  assert.match(appSource, /pipelineActive: navigationEngine\?\.pipelineActive\(navigationSnapshot\)/);
});
