import assert from 'node:assert/strict';
import test from 'node:test';

import { createEditor } from '../robot_dashboard/static/features/map_editor3d/core.js';
import { buildFullSourceEditRequest, FULL_SOURCE_EDIT_SCHEMA, saveFullSourceCopy } from '../robot_dashboard/static/features/map_editor3d/full_source.js';

const fullSource = () => ({ map_id: '1'.repeat(24), revision: '2'.repeat(64), sha256: '3'.repeat(64), frame_id: 'camera_init', units: 'm', asset_role: 'full_source' });
const region = (kind = 'visibility') => ({ kind, selection: 'outside', polygon: [[0, 0], [2, 0], [2, 2], [0, 2]], z_min: -1, z_max: 2 });
function fixture() {
  const source = fullSource();
  const editor = createEditor({ ...source, points: [0.25, 0.25, 0, 17, 17, 0] });
  editor.addRegion(region());
  editor.addRegion(region('localization'));
  editor.addRegion(region('keepout'));
  return { source, editor, input: { name: 'edited_copy', purpose: 'visibility', source, annotation: editor.exportVersion() } };
}
const clone = (value) => JSON.parse(JSON.stringify(value));

test('reuses annotation geometry but sends only source identity, never sampled preview points', () => {
  const { source, editor, input } = fixture();
  const original = editor.original;
  const annotation = input.annotation;
  const request = buildFullSourceEditRequest(input);
  assert.deepEqual(Object.keys(request).sort(), ['schema', 'name', 'purpose', 'source', 'annotation'].sort());
  assert.equal(request.schema, FULL_SOURCE_EDIT_SCHEMA);
  assert.deepEqual(request.source, source);
  assert.deepEqual(request.annotation, annotation);
  assert.equal(request.annotation.runtime_installed, false);
  assert.equal(request.source.asset_role, 'full_source');
  assert.ok(!JSON.stringify(request).includes('points'));
  assert.deepEqual(editor.original, original);
  assert.notStrictEqual(request.source, input.source);
  assert.notStrictEqual(request.annotation.regions, annotation.regions);
  input.source.sha256 = '4'.repeat(64);
  assert.equal(request.source.sha256, '3'.repeat(64));
  assert.ok(Object.isFrozen(request.annotation.regions[0].polygon[0]));
});

test('the localization purpose uses the same annotation and preserves all separate kinds', () => {
  const { input } = fixture();
  const request = buildFullSourceEditRequest({ ...input, purpose: 'localization', name: 'fresh_copy' });
  assert.equal(request.purpose, 'localization');
  assert.equal(request.name, 'fresh_copy');
  assert.deepEqual(request.annotation.regions.map((r) => r.kind), ['visibility', 'localization', 'keepout']);
  assert.equal(request.annotation.regions[0].selection, 'outside');
});

test('rejects malformed descriptors and any sampled source role', () => {
  const invalid = [
    null, [], {},
    { map_id: '../private/path' }, { map_id: '1'.repeat(23) }, { map_id: 'A'.repeat(24) },
    { revision: 1 }, { revision: 'rev-1' }, { revision: '2'.repeat(63) },
    { sha256: '3'.repeat(63) }, { sha256: 'G'.repeat(64) },
    { frame_id: '' }, { frame_id: ' ' }, { frame_id: 'map\nsecret' }, { frame_id: 'x'.repeat(129) },
    { units: 'cm' }, { asset_role: 'sampled_preview' }, { asset_role: 'full_source', points: [1, 2, 3] },
    { preview_count: 2 }, { source_points: 20 },
  ];
  for (const fields of invalid) {
    const { input } = fixture();
    input.source = fields && !Array.isArray(fields) && Object.keys(fields).length ? { ...input.source, ...fields } : fields;
    assert.throws(() => buildFullSourceEditRequest(input), TypeError);
  }
});

test('rejects stale annotation identity even if the old sampled cloud still exists', () => {
  for (const [key, value] of [['map_id', '4'.repeat(24)], ['revision', '4'.repeat(64)], ['frame_id', 'other_map']]) {
    const { input } = fixture();
    input.source = { ...input.source, [key]: value };
    assert.throws(() => buildFullSourceEditRequest(input), /does not match.*reload/);
  }
});

test('rejects unknown fields and point payloads at every accepted object level', () => {
  const mutators = [
    (v) => { v.points = [1, 2, 3]; },
    (v) => { v.annotation.points = [1, 2, 3]; },
    (v) => { v.annotation.source.points = [1, 2, 3]; },
    (v) => { v.annotation.regions[0].points = [1, 2, 3]; },
    (v) => { v.source.preview = { points: [1, 2, 3] }; },
    (v) => { v.annotation.toJSON = () => ({}); },
    (v) => { v.annotation.regions.points = [1, 2, 3]; },
    (v) => { v.annotation.regions[0].polygon.points = [1, 2, 3]; },
    (v) => { v.annotation.regions[0].polygon[0].points = [1, 2, 3]; },
    (v) => { v.source[Symbol('points')] = [1, 2, 3]; },
    (v) => { Object.defineProperty(v.source, 'points', { value: [1, 2, 3] }); },
    (v) => { Object.defineProperty(v.source, 'sha256', { get: () => '3'.repeat(64) }); },
  ];
  for (const mutate of mutators) {
    const input = clone(fixture().input);
    mutate(input);
    assert.throws(() => buildFullSourceEditRequest(input), TypeError);
  }
});

test('rejects runtime installs, unsupported versions and malformed regions', () => {
  const mutators = [
    (v) => { v.annotation.runtime_installed = true; },
    (v) => { v.annotation.schema = 'robot-dashboard.edited-cloud-copy'; },
    (v) => { v.annotation.schema_version = 2; },
    (v) => { v.annotation.version_id = ''; },
    (v) => { v.annotation.version_id = 'x'.repeat(129); },
    (v) => { v.annotation.regions = Array(101).fill(region()); },
    (v) => { v.annotation.regions[0].polygon = [[0, 0], [1, 1], [0, 1], [1, 0]]; },
    (v) => { v.annotation.regions[0].z_min = Infinity; },
    (v) => { v.annotation.regions[0].selection = 'all'; },
    (v) => { v.purpose = 'keepout'; },
    (v) => { v.name = ' '; },
    (v) => { v.name = 'x'.repeat(65); },
    (v) => { v.name = 'name with spaces'; },
    (v) => { v.name = 'line\nbreak'; },
  ];
  for (const mutate of mutators) {
    const input = clone(fixture().input);
    mutate(input);
    assert.throws(() => buildFullSourceEditRequest(input), TypeError);
  }
});

test('POSTs one bounded annotation request and returns the new catalogue map only', async () => {
  const { editor, input } = fixture();
  const before = editor.exportVersion();
  const calls = [];
  const result = { map: { id: '4'.repeat(24), revision: '5'.repeat(64), runtime_installed: false } };
  const saved = await saveFullSourceCopy({ ...input, fetchImpl: async (...args) => {
    calls.push(args);
    return { ok: true, json: async () => result };
  } });
  assert.strictEqual(saved, result);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], `/api/v1/saved-maps/${input.source.map_id}/pcd-edited-copy`);
  const options = calls[0][1];
  assert.equal(options.method, 'POST');
  assert.deepEqual(options.headers, { 'Content-Type': 'application/json' });
  assert.deepEqual(JSON.parse(options.body), buildFullSourceEditRequest(input));
  assert.deepEqual(editor.original, [0.25, 0.25, 0, 17, 17, 0]);
  assert.deepEqual(editor.exportVersion().source, before.source);
  assert.equal(editor.exportVersion().runtime_installed, false);
  assert.equal(editor.canUndo, true);
});

test('invalid save inputs are rejected before fetch, including an accidental editedCopy payload', async () => {
  let calls = 0;
  const { input, editor } = fixture();
  const fetchImpl = async () => { calls += 1; };
  await assert.rejects(saveFullSourceCopy({ ...input, ...editor.editedCopy(), fetchImpl }), TypeError);
  await assert.rejects(saveFullSourceCopy({ ...input, fetchImpl, annotation: { ...input.annotation, runtime_installed: true } }), TypeError);
  assert.equal(calls, 0);
});

test('failed POSTs produce clean messages without leaking server or network details', async () => {
  const { input } = fixture();
  await assert.rejects(saveFullSourceCopy({ ...input, fetchImpl: async () => { throw new Error('token=secret /private/sensor.pcd'); } }),
    (e) => /Check the connection/.test(e.message) && !/secret|private/.test(e.message));
  for (const status of [400, 403, 404, 422, 500]) {
    await assert.rejects(saveFullSourceCopy({ ...input, fetchImpl: async () => ({ ok: false, status, json: () => { throw new Error('must not read error body'); } }) }),
      new RegExp(`HTTP ${status}`));
  }
  await assert.rejects(saveFullSourceCopy({ ...input, fetchImpl: async () => ({ ok: false, status: 409 }) }), /Reload its descriptor and preview/);
  await assert.rejects(saveFullSourceCopy({ ...input, fetchImpl: async () => ({ ok: true, json: async () => { throw new Error('secret'); } }) }),
    /Refresh the catalogue before retrying/);
});
