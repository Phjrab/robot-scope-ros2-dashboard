import assert from 'node:assert/strict';
import test from 'node:test';

import { migrateLayoutDocument } from '../robot_dashboard/static/features/cockpit/layout_migrations.js';
import {
  COCKPIT_LAYOUT_MAX_BYTES,
  COCKPIT_LAYOUT_MAX_PRESETS,
  createLayoutDocument,
  layoutPanelsToPixels,
  parseLayoutDocument,
} from '../robot_dashboard/static/features/cockpit/layout_schema.js';
import { createLayoutStore } from '../robot_dashboard/static/features/cockpit/layout_store.js';

const TYPES = ['camera.go2-front', 'placeholder.map'];
const IDS = { 'camera.go2-front': 'camera-go2-front', 'placeholder.map': 'placeholder-map' };
const VIEWPORT = { width: 1000, height: 700, padding: 12, reservedBottom: 78 };

function scene() {
  return { view: 'robot-follow', follow_robot: true, point_size: 2, range_m: 30 };
}

function document(name = 'competition-drive', profileId = 'go2') {
  return {
    schema_version: 1,
    name,
    profile_id: profileId,
    scene: scene(),
    panels: [{
      id: 'camera-go2-front', panel_type: 'camera.go2-front', mode: 'floating', dock: null,
      x: 0.1, y: 0.08, width: 0.3, height: 0.28, pinned: true, locked: false,
      restore_geometry: null,
    }],
  };
}

function storageHarness(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    values,
    storage: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, String(value)),
      removeItem: (key) => values.delete(key),
    },
  };
}

test('layout schema accepts only bounded registered fields and rejects unsafe or oversized JSON', () => {
  const parsed = parseLayoutDocument(document(), { profileId: 'go2', allowedPanelTypes: TYPES });
  assert.equal(parsed.panels[0].panel_type, 'camera.go2-front');
  assert.throws(() => parseLayoutDocument({ ...document(), lease_token: 'secret' }, { profileId: 'go2', allowedPanelTypes: TYPES }), /unknown field/);
  assert.throws(() => parseLayoutDocument({ ...document(), profile_id: 'turtlebot' }, { profileId: 'go2', allowedPanelTypes: TYPES }), /profile/);
  assert.throws(() => parseLayoutDocument({ ...document(), panels: [{ ...document().panels[0], panel_type: 'camera.unregistered' }] }, { profileId: 'go2', allowedPanelTypes: TYPES }), /not registered/);
  assert.throws(() => parseLayoutDocument({ ...document(), panels: [{ ...document().panels[0], id: 'placeholder-map' }] }, { profileId: 'go2', allowedPanelTypes: TYPES, panelIdsByType: IDS }), /does not match/);
  assert.throws(() => parseLayoutDocument({ ...document(), panels: [document().panels[0], document().panels[0]] }, { profileId: 'go2', allowedPanelTypes: TYPES }), /duplicate/);
  assert.throws(() => parseLayoutDocument(`${JSON.stringify(document()).slice(0, -1)},"padding":"${'x'.repeat(COCKPIT_LAYOUT_MAX_BYTES)}"}`, { profileId: 'go2', allowedPanelTypes: TYPES }), /too large/);
});

test('normalized geometry round trip preserves floating and focus restore geometry across viewport sizes', () => {
  const source = [{
    id: 'camera-go2-front', panelType: 'camera.go2-front', mode: 'focus', dock: null,
    x: 12, y: 12, width: 976, height: 598, zIndex: 1, pinned: true, locked: false, visible: true,
    restoreGeometry: { mode: 'floating', dock: null, x: 200, y: 100, width: 360, height: 240 },
  }];
  const saved = createLayoutDocument({ name: 'focus-safe', profileId: 'go2', scene: scene(), panels: source, viewport: VIEWPORT, allowedPanelTypes: TYPES });
  assert.equal(saved.panels[0].mode, 'focus');
  assert.ok(saved.panels[0].restore_geometry);
  const restored = layoutPanelsToPixels(saved, { ...VIEWPORT, width: 520, height: 430 });
  assert.equal(restored[0].mode, 'focus');
  assert.ok(restored[0].restoreGeometry.x >= 12);
  assert.ok(restored[0].restoreGeometry.x + restored[0].restoreGeometry.width <= 508);
});

test('corrupted storage falls back without throwing or leaking layouts across profiles', () => {
  const key = 'robot-scope.cockpit.layouts.v1.go2';
  const harness = storageHarness({ [key]: '{broken' });
  const errors = [];
  const store = createLayoutStore({ storage: harness.storage, allowedPanelTypes: TYPES, onError: (error) => errors.push(error) });
  const go2 = store.setProfile('go2');
  assert.equal(go2.corrupted, true);
  assert.deepEqual(go2.presets, []);
  assert.equal(errors.length, 1);
  store.save(parseLayoutDocument(document(), { profileId: 'go2', allowedPanelTypes: TYPES }));
  store.setProfile('turtlebot');
  assert.deepEqual(store.snapshot().presets, []);
  store.save(parseLayoutDocument(document('tb-layout', 'turtlebot'), { profileId: 'turtlebot', allowedPanelTypes: TYPES }));
  store.setProfile('go2');
  assert.deepEqual(store.snapshot().presets.map((preset) => preset.name), ['competition-drive']);
});

test('schema migration is explicit and unsupported versions fail closed', () => {
  const legacy = document();
  delete legacy.profile_id;
  legacy.schema_version = 0;
  legacy.profile = 'go2';
  const migrated = migrateLayoutDocument(legacy);
  assert.equal(migrated.schema_version, 1);
  assert.equal(migrated.profile_id, 'go2');
  assert.throws(() => migrateLayoutDocument({ ...document(), schema_version: 99 }), /Unsupported/);
});

test('import preview is atomic and preset name and count remain bounded', () => {
  const harness = storageHarness();
  const store = createLayoutStore({ storage: harness.storage, allowedPanelTypes: TYPES });
  store.setProfile('go2');
  store.save(parseLayoutDocument(document('before'), { profileId: 'go2', allowedPanelTypes: TYPES }));
  const before = store.snapshot();
  assert.throws(() => store.previewImport('{bad'), /invalid/);
  assert.deepEqual(store.snapshot(), before);
  const preview = store.previewImport(JSON.stringify(document('imported')));
  assert.equal(preview.name, 'imported');
  assert.deepEqual(store.snapshot(), before, 'successful preview must not write storage');
  store.save(preview);
  assert.equal(store.getDefault().name, 'before');
  for (let index = 2; index < COCKPIT_LAYOUT_MAX_PRESETS; index += 1) store.save(parseLayoutDocument(document(`preset-${index}`), { profileId: 'go2', allowedPanelTypes: TYPES }));
  assert.equal(store.snapshot().presets.length, COCKPIT_LAYOUT_MAX_PRESETS);
  assert.throws(() => store.save(parseLayoutDocument(document('one-too-many'), { profileId: 'go2', allowedPanelTypes: TYPES })), /limit/);
  assert.throws(() => parseLayoutDocument(document('x'.repeat(49)), { profileId: 'go2', allowedPanelTypes: TYPES }), /name/);
});

test('default, delete, export, and reset update only the active profile catalog', () => {
  const harness = storageHarness();
  const store = createLayoutStore({ storage: harness.storage, allowedPanelTypes: TYPES });
  store.setProfile('go2');
  store.save(parseLayoutDocument(document('alpha'), { profileId: 'go2', allowedPanelTypes: TYPES }));
  store.save(parseLayoutDocument(document('bravo'), { profileId: 'go2', allowedPanelTypes: TYPES }));
  store.setDefault('bravo');
  assert.equal(store.getDefault().name, 'bravo');
  assert.equal(JSON.parse(store.exportJson('bravo')).name, 'bravo');
  store.remove('bravo');
  assert.equal(store.snapshot().defaultPreset, 'alpha');
  store.reset();
  assert.deepEqual(store.snapshot().presets, []);
  assert.equal(harness.values.has('robot-scope.cockpit.layouts.v1.go2'), false);
});

test('a storage write failure does not publish an in-memory preset that cannot survive reload', () => {
  const store = createLayoutStore({
    storage: { getItem: () => null, setItem: () => { throw new Error('quota blocked'); }, removeItem() {} },
    allowedPanelTypes: TYPES,
  });
  store.setProfile('go2');
  const parsed = parseLayoutDocument(document('not-saved'), { profileId: 'go2', allowedPanelTypes: TYPES });
  assert.throws(() => store.save(parsed), /quota blocked/);
  assert.deepEqual(store.snapshot().presets, []);
});
