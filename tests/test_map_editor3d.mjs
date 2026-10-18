import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createEditor, EDITOR_LIMITS, pointInRegion, validateRegion, VERSION_SCHEMA, VERSION_SCHEMA_VERSION,
} from '../robot_dashboard/static/features/map_editor3d/core.js';

const CLOUD = [0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 0.5, 0.5, -1];
const source = (overrides = {}) => ({ map_id: 'saved-warehouse', revision: 'rev-17', frame_id: 'map', points: CLOUD.slice(), ...overrides });
const region = (kind = 'visibility', overrides = {}) => ({ kind, polygon: [[0, 0], [1, 0], [1, 1], [0, 1]], z_min: 0, z_max: 1, ...overrides });
const asJson = (value) => JSON.stringify(value);
const mutableVersion = (editor) => JSON.parse(asJson(editor.exportVersion()));

test('source and every returned coordinate buffer are defensively copied', () => {
  const input = source();
  const editor = createEditor(input);
  input.points[0] = 500;
  input.map_id = 'other';
  input.revision = 'other';
  const original = editor.original;
  original[0] = 600;
  const firstPreview = editor.preview();
  firstPreview.points[0] = 700;
  assert.deepEqual(editor.original, CLOUD);
  assert.deepEqual(editor.preview().points, CLOUD);
  assert.equal(editor.exportVersion().source.map_id, 'saved-warehouse');
  assert.equal(editor.exportVersion().source.revision, 'rev-17');
  assert.notStrictEqual(editor.original, editor.original);
  assert.notStrictEqual(editor.preview().points, editor.preview().points);
});

test('visibility is preview-only while localization and keepout have separate union counts', () => {
  const editor = createEditor(source());
  editor.addRegion(region('localization'));
  editor.addRegion(region('keepout'));
  assert.deepEqual(editor.preview().points, CLOUD);
  assert.deepEqual(editor.preview().counts, { total: 5, visible: 5, hidden: 0, visibility: 0, localization: 2, keepout: 2 });
  editor.addRegion(region());
  editor.addRegion(region());
  editor.addRegion(region('localization'));
  assert.deepEqual(editor.preview().points, CLOUD.slice(6));
  assert.deepEqual(editor.preview().counts, { total: 5, visible: 3, hidden: 2, visibility: 2, localization: 2, keepout: 2 });
  assert.deepEqual(editor.original, CLOUD);
  assert.equal(editor.exportVersion().runtime_installed, false);
});

test('overlapping region counts count a point once per kind, including hidden points', () => {
  const editor = createEditor(source());
  editor.addRegion(region());
  editor.addRegion(region('visibility', { polygon: [[1, 1], [3, 1], [3, 3], [1, 3]], z_max: 3 }));
  editor.addRegion(region('keepout', { polygon: [[1, 1], [3, 1], [3, 3], [1, 3]], z_max: 3 }));
  assert.deepEqual(editor.preview().counts, { total: 5, visible: 1, hidden: 4, visibility: 4, localization: 0, keepout: 3 });
  assert.deepEqual(editor.preview().points, [0.5, 0.5, -1]);
});

test('edits, reset, undo and redo preserve immutable snapshots and source', () => {
  const editor = createEditor(source());
  const input = region();
  assert.equal(editor.undo(), false);
  assert.equal(editor.redo(), false);
  assert.equal(editor.reset(), false);
  assert.equal(editor.addRegion(input), true);
  input.polygon[0][0] = 900;
  const first = editor.regions;
  assert.deepEqual(first[0].polygon[0], [0, 0]);
  assert.ok(Object.isFrozen(first));
  assert.ok(Object.isFrozen(first[0]));
  assert.ok(Object.isFrozen(first[0].polygon));
  assert.ok(Object.isFrozen(first[0].polygon[0]));
  assert.throws(() => { first[0].polygon[0][0] = 900; }, TypeError);
  editor.addRegion(region('keepout'));
  assert.equal(first.length, 1);
  assert.equal(editor.canUndo, true);
  assert.equal(editor.canRedo, false);
  assert.equal(editor.undo(), true);
  assert.strictEqual(editor.regions, first);
  assert.equal(editor.canRedo, true);
  assert.equal(editor.redo(), true);
  assert.equal(editor.regions.length, 2);
  assert.equal(editor.reset(), true);
  assert.equal(editor.regions.length, 0);
  assert.deepEqual(editor.preview().points, CLOUD);
  assert.equal(editor.undo(), true);
  assert.equal(editor.regions.length, 2);
  assert.deepEqual(editor.original, CLOUD);
});

test('a new successful edit discards redo but invalid edits leave history untouched', () => {
  const editor = createEditor(source());
  editor.addRegion(region());
  editor.addRegion(region('keepout'));
  editor.undo();
  const before = editor.regions;
  assert.throws(() => editor.addRegion(region('nav2')));
  assert.strictEqual(editor.regions, before);
  assert.equal(editor.canRedo, true);
  editor.addRegion(region('localization'));
  assert.equal(editor.canRedo, false);
  assert.equal(editor.redo(), false);
  assert.deepEqual(editor.regions.map((value) => value.kind), ['visibility', 'localization']);
});

test('history keeps at most 100 undo steps and permits all retained redo steps', () => {
  const editor = createEditor(source());
  for (let i = 0; i < EDITOR_LIMITS.history + 11; i += 1) {
    if (editor.regions.length) editor.reset();
    else editor.addRegion(region());
  }
  let undos = 0;
  while (editor.undo()) undos += 1;
  assert.equal(undos, EDITOR_LIMITS.history);
  let redos = 0;
  while (editor.redo()) redos += 1;
  assert.equal(redos, EDITOR_LIMITS.history);
  assert.equal(editor.regions.length, 1);
});

test('polygon and Z boundaries are inclusive; concave regions support either winding', () => {
  const square = region();
  for (const point of [[0, 0, 0], [1, 1, 1], [0, 0.5, 0.5], [0.5, 0.5, 0]]) assert.equal(pointInRegion(point, square), true);
  for (const point of [[-0.1, 0.5, 0], [0.5, 1.1, 0], [0.5, 0.5, -0.01], [0.5, 0.5, 1.01]]) assert.equal(pointInRegion(point, square), false);
  const concave = region('visibility', { polygon: [[0, 0], [3, 0], [3, 1], [1, 1], [1, 3], [0, 3]] });
  for (const polygon of [concave.polygon, concave.polygon.slice().reverse()]) {
    assert.equal(pointInRegion([0.5, 2, 0], { ...concave, polygon }), true);
    assert.equal(pointInRegion([2, 0.5, 1], { ...concave, polygon }), true);
    assert.equal(pointInRegion([2, 2, 0], { ...concave, polygon }), false);
    assert.equal(pointInRegion([1, 2, 0], { ...concave, polygon }), true);
  }
  assert.equal(pointInRegion([0.5, 0.5, 0], region('keepout', { z_min: 0, z_max: 0 })), true);
});

test('geometry normalization handles large and tiny finite coordinates', () => {
  for (const scale of [1e-200, 1e200, 1e308]) {
    const polygon = [[-scale, -scale], [scale, -scale], [scale, scale], [-scale, scale]];
    const validated = validateRegion(region('visibility', { polygon }));
    assert.equal(pointInRegion([0, 0, 0], validated), true);
    assert.equal(pointInRegion([scale, scale, 1], validated), true);
  }
});

test('invalid, crossing, touching, duplicate, overlapping and degenerate polygons are rejected', () => {
  const polygons = [
    [], [[0, 0], [1, 1]],
    [[0, 0], [1, 1], [2, 2]],
    [[0, 0], [1, 0], [1, 0], [0, 1]],
    [[0, 0], [1, 0], [1, 1], [0, 0]],
    [[0, 0], [3, 3], [0, 3], [2, 0]],
    [[0, 0], [2, 0], [2, 2], [1, 0], [0, 2]],
    [[0, 0], [2, 0], [1, 0], [1, 2], [0, 2]],
    [[0, 0], [1, NaN], [0, 1]],
    [[0, 0], [Infinity, 1], [0, 1]],
    [[0, 0], ['1', 1], [0, 1]],
    [[0, 0], [1, 1, 1], [0, 1]],
    [[0, 0], null, [0, 1]],
  ];
  for (const polygon of polygons) assert.throws(() => validateRegion(region('visibility', { polygon })), TypeError);
  const withCollinearVertex = region('visibility', { polygon: [[0, 0], [0.5, 0], [1, 0], [1, 1], [0, 1]] });
  assert.equal(pointInRegion([0.5, 0.5, 0], withCollinearVertex), true);
});

test('strict region validation rejects unknown kinds, fields and invalid heights', () => {
  for (const value of [null, [], {}, region('delete'), region('visibility', { z_min: -Infinity }), region('visibility', { z_max: NaN }), region('visibility', { z_min: '0' }), region('visibility', { z_min: 2 }), { ...region(), runtime_installed: true }]) {
    assert.throws(() => validateRegion(value), TypeError);
  }
  for (const point of [[0, 0], [0, 0, NaN], ['0', 0, 0], null]) assert.throws(() => pointInRegion(point, region()), TypeError);
});

test('point and identity validation rejects malformed sources without numeric coercion', () => {
  for (const points of [null, {}, [1, 2], [0, 0, NaN], [0, Infinity, 0], [0, '1', 0], new DataView(new ArrayBuffer(12)), new BigInt64Array([0n, 0n, 0n])]) {
    assert.throws(() => createEditor(source({ points })), TypeError);
  }
  for (const overrides of [{ map_id: '' }, { map_id: ' ' }, { frame_id: null }, { frame_id: '' }, { revision: '' }, { revision: -1 }, { revision: 1.5 }, { revision: Infinity }, { revision: false }]) {
    assert.throws(() => createEditor(source(overrides)), TypeError);
  }
  assert.throws(() => createEditor(null), TypeError);
  assert.deepEqual(createEditor(source({ points: new Float32Array(CLOUD) })).original, CLOUD);
  assert.equal(createEditor(source({ revision: 0 })).exportVersion().source.revision, 0);
  assert.deepEqual(createEditor(source({ points: [] })).preview().counts, { total: 0, visible: 0, hidden: 0, visibility: 0, localization: 0, keepout: 0 });
});

test('point, polygon and region limits apply at their inclusive boundaries', () => {
  const maxPoints = new Float32Array(EDITOR_LIMITS.points * 3);
  const editor = createEditor(source({ points: maxPoints }));
  assert.equal(editor.original.length, EDITOR_LIMITS.points * 3);
  assert.throws(() => createEditor(source({ points: new Float32Array(EDITOR_LIMITS.points * 3 + 3) })), /at most/);
  const polygon = Array.from({ length: EDITOR_LIMITS.vertices }, (_, i) => [Math.cos(i * 2 * Math.PI / EDITOR_LIMITS.vertices), Math.sin(i * 2 * Math.PI / EDITOR_LIMITS.vertices)]);
  assert.equal(validateRegion(region('visibility', { polygon })).polygon.length, EDITOR_LIMITS.vertices);
  assert.throws(() => validateRegion(region('visibility', { polygon: [...polygon, [0, 0]] })), /vertices/);
  const bounded = createEditor(source());
  for (let i = 0; i < EDITOR_LIMITS.regions; i += 1) bounded.addRegion(region());
  assert.equal(bounded.regions.length, EDITOR_LIMITS.regions);
  assert.throws(() => bounded.addRegion(region()), /100 regions/);
});

test('exports are distinct deeply frozen annotation-only versions', () => {
  const editor = createEditor(source());
  editor.addRegion(region('localization'));
  const exported = editor.exportVersion();
  assert.equal(exported.schema, VERSION_SCHEMA);
  assert.equal(exported.schema_version, VERSION_SCHEMA_VERSION);
  assert.equal(exported.runtime_installed, false);
  assert.notEqual(editor.exportVersion().version_id, exported.version_id);
  assert.deepEqual(exported.source, { map_id: 'saved-warehouse', revision: 'rev-17', frame_id: 'map' });
  assert.deepEqual(Object.keys(exported).sort(), ['schema', 'schema_version', 'version_id', 'source', 'runtime_installed', 'regions'].sort());
  assert.ok(Object.isFrozen(exported));
  assert.ok(Object.isFrozen(exported.source));
  assert.ok(Object.isFrozen(exported.regions));
  assert.throws(() => { exported.runtime_installed = true; }, TypeError);
  assert.throws(() => { exported.source.revision = 'bad'; }, TypeError);
  assert.equal(asJson(exported).includes('points'), false);
  editor.reset();
  assert.equal(exported.regions.length, 1);
});

test('version round trips are atomic, source-bound, undoable, and keep proposals separate', () => {
  const first = createEditor(source());
  first.addRegion(region());
  first.addRegion(region('localization'));
  first.addRegion(region('keepout'));
  const second = createEditor(source());
  assert.equal(second.importVersion(asJson(first.exportVersion())), true);
  assert.deepEqual(second.preview(), first.preview());
  assert.deepEqual(second.regions, first.regions);
  assert.equal(second.importVersion(asJson(first.exportVersion())), false, 'identical import is a no-op');
  assert.equal(second.undo(), true);
  assert.equal(second.regions.length, 0);
  assert.equal(second.redo(), true);
  assert.deepEqual(second.original, CLOUD);
});

test('imports reject mismatched identity, frame and revision without changing edits or redo', () => {
  const editor = createEditor(source());
  editor.addRegion(region());
  editor.addRegion(region('keepout'));
  editor.undo();
  for (const [key, value] of [['map_id', 'different'], ['frame_id', 'odom'], ['revision', 'rev-18']]) {
    const imported = mutableVersion(editor);
    imported.source[key] = value;
    assert.throws(() => editor.importVersion(asJson(imported)), /does not match/);
    assert.equal(editor.regions.length, 1);
    assert.equal(editor.canRedo, true);
  }
  const numeric = createEditor(source({ revision: 1 }));
  const imported = mutableVersion(numeric);
  imported.source.revision = '1';
  assert.throws(() => numeric.importVersion(asJson(imported)), /revision does not match/);
});

test('imports reject oversized input, unknown fields, raw points and runtime installation claims', () => {
  const editor = createEditor(source());
  editor.addRegion(region());
  const mutations = [
    (v) => { v.schema = 'unknown'; },
    (v) => { v.schema_version = 2; },
    (v) => { v.version_id = ''; },
    (v) => { v.runtime_installed = true; },
    (v) => { v.runtime_installed = 'false'; },
    (v) => { v.points = CLOUD; },
    (v) => { v.source.points = CLOUD; },
    (v) => { v.regions = {}; },
    (v) => { v.regions = Array.from({ length: EDITOR_LIMITS.regions + 1 }, () => region()); },
    (v) => { v.regions.push(region('nav2')); },
    (v) => { v.regions.push(region('keepout', { polygon: [[0, 0], [1, 1], [0, 1], [1, 0]] })); },
    (v) => { delete v.source.frame_id; },
  ];
  for (const mutate of mutations) {
    const imported = mutableVersion(editor);
    mutate(imported);
    const before = editor.regions;
    assert.throws(() => editor.importVersion(asJson(imported)), TypeError);
    assert.strictEqual(editor.regions, before);
  }
  for (const input of [null, {}, 'null', '[]', '{', '{}']) assert.throws(() => editor.importVersion(input), TypeError);
  assert.throws(() => editor.importVersion(' '.repeat(EDITOR_LIMITS.importBytes + 1)), /2 MiB/);
  assert.throws(() => editor.importVersion('💥'.repeat(600_000)), /2 MiB/, 'limit measures UTF-8 bytes, not code units');
  assert.equal(editor.regions.length, 1);
});

test('outside masks select outside XY only within the inclusive Z slab', () => {
  const outside = region('visibility', { selection: 'outside' });
  assert.equal(pointInRegion([2, 2, 0], outside), true);
  assert.equal(pointInRegion([2, 2, 1], outside), true);
  assert.equal(pointInRegion([0.5, 0.5, 0.5], outside), false);
  assert.equal(pointInRegion([0, 0.5, 0], outside), false, 'polygon edges remain inside');
  assert.equal(pointInRegion([2, 2, -1], outside), false, 'below the slab is not selected');
  assert.equal(pointInRegion([2, 2, 2], outside), false, 'above the slab is not selected');
  const points = [0.5, 0.5, 0, 2, 2, 0, 2, 2, 1, 2, 2, -1, 2, 2, 2];
  const editor = createEditor(source({ points }));
  editor.addRegion(outside);
  assert.deepEqual(editor.preview().points, [0.5, 0.5, 0, 2, 2, -1, 2, 2, 2]);
  assert.equal(editor.preview().counts.visibility, 2);
  assert.deepEqual(editor.original, points);
});

test('selection defaults to inside and is explicit in validated and exported annotations', () => {
  assert.equal(validateRegion(region()).selection, 'inside');
  for (const selection of ['other', null, 0, undefined]) {
    assert.throws(() => validateRegion(region('visibility', { selection })), /selection/);
  }
  const first = createEditor(source());
  first.addRegion(region());
  first.addRegion(region('localization', { selection: 'outside' }));
  assert.deepEqual(first.exportVersion().regions.map((value) => value.selection), ['inside', 'outside']);
  const second = createEditor(source());
  second.importVersion(asJson(first.exportVersion()));
  assert.deepEqual(second.regions, first.regions);
  assert.deepEqual(second.preview(), first.preview());
});

test('edited cloud copies exclude only their own purpose and never apply keepout proposals', () => {
  const editor = createEditor(source());
  editor.addRegion(region('visibility'));
  editor.addRegion(region('localization', { polygon: [[1, 1], [3, 1], [3, 3], [1, 3]], z_min: 2, z_max: 3 }));
  editor.addRegion(region('keepout', { z_min: -1, z_max: -1 }));
  const visibilityResult = editor.editedCopy();
  const visibilityCopy = visibilityResult.points;
  const localizationResult = editor.editedCopy('localization');
  const localizationCopy = localizationResult.points;
  assert.equal(visibilityResult.purpose, 'visibility');
  assert.equal(visibilityResult.removed_count, 2);
  assert.equal(localizationResult.purpose, 'localization');
  assert.equal(localizationResult.removed_count, 2);
  assert.deepEqual(visibilityCopy, [2, 2, 2, 3, 3, 3, 0.5, 0.5, -1]);
  assert.deepEqual(localizationCopy, [0, 0, 0, 1, 1, 1, 0.5, 0.5, -1]);
  assert.deepEqual(editor.preview().points, visibilityCopy);
  assert.notStrictEqual(editor.editedCopy().points, visibilityCopy);
  assert.notStrictEqual(editor.editedCopy('localization').points, localizationCopy);
  visibilityCopy[0] = 900;
  localizationCopy[0] = 800;
  assert.deepEqual(editor.original, CLOUD);
  assert.equal(editor.editedCopy().points[0], 2);
  assert.equal(editor.editedCopy('localization').points[0], 0);
  assert.throws(() => editor.editedCopy('keepout'), /purpose/);
  assert.throws(() => editor.editedCopy('all'), /purpose/);
  assert.equal(editor.exportVersion().runtime_installed, false);
});

test('outside localization copy preserves visibility preview and points beyond its Z limits', () => {
  const editor = createEditor(source());
  editor.addRegion(region('localization', { selection: 'outside', z_min: 0, z_max: 2 }));
  assert.deepEqual(editor.editedCopy('localization'), { points: [0, 0, 0, 1, 1, 1, 3, 3, 3, 0.5, 0.5, -1], purpose: 'localization', removed_count: 1 });
  assert.deepEqual(editor.editedCopy('visibility'), { points: CLOUD, purpose: 'visibility', removed_count: 0 });
  assert.deepEqual(editor.preview().points, CLOUD);
  assert.equal(editor.preview().counts.localization, 1);
  assert.deepEqual(editor.original, CLOUD);
});
