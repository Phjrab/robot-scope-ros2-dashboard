import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

import { COCKPIT_MAP_LIMITS, createCockpitMapStore } from '../robot_dashboard/static/features/cockpit/map_state.js';
import { createMapPanel, createOccupancyRasterCache } from '../robot_dashboard/static/features/cockpit/panels/map_panel.js';

const require = createRequire(import.meta.url);
const navigationEngine = require('../robot_dashboard/static/navigation.js');
const MAP_ID = '0123456789abcdef01234567';
const REVISION = 'a'.repeat(64);
const HOME_ID = 'b'.repeat(24);
const POI_ID = 'c'.repeat(24);
const mapMeta = Object.freeze({ id: MAP_ID, revision: REVISION, name: 'Lab map' });
const map = Object.freeze({ id: MAP_ID, revision: REVISION, frame_id: 'map', width: 4, height: 4, resolution: 0.25, origin: [1, 2, Math.PI / 2], data_b64: 'AAAAAAAAAAAAAAAAAAAAAA==' });
const annotations = Object.freeze({
  map_id: MAP_ID, map_revision: REVISION,
  points: [
    { id: HOME_ID, type: 'HOME', name: 'Home', pose: { x: 1.25, y: 2.25, yaw: 0 } },
    { id: POI_ID, type: 'POI', name: 'Inspect', pose: { x: 1.5, y: 2.5, yaw: 1 } },
  ],
});

function navigation(overrides = {}) {
  return {
    map: { id: MAP_ID, revision: REVISION },
    pipeline: { state: 'running' },
    localization: { state: 'localized', pose: { x: 1.25, y: 2.25, yaw: 0.2, frame_id: 'map' } },
    localization_health: { state: 'READY', reason_code: 'HEALTHY', metrics: { odometry_age_s: 0.05, tf_age_s: 0.08 } },
    readiness: { odometry: true, tf: true },
    path: [{ x: 1.25, y: 2.25 }, { x: 1.5, y: 2.5 }],
    goal: { state: 'active', pose: { x: 1.5, y: 2.5, yaw: 1 } },
    ...overrides,
  };
}

const input = (nav = navigation()) => ({ mapMeta, map, annotations, navigation: nav, robotRadius: 0.24 });

test('map state pins map, navigation and annotations to one exact revision', () => {
  const store = createCockpitMapStore();
  const state = store.update(input());
  assert.equal(state.status, 'LIVE');
  assert.equal(state.map.id, MAP_ID);
  assert.equal(state.map.revision, REVISION);
  assert.equal(state.localization.fresh, true);
  assert.equal(state.overlay.revision, REVISION);
  assert.deepEqual(state.overlay.markers.map((marker) => marker.type), ['HOME']);
  store.selectAnnotation(POI_ID);
  assert.deepEqual(store.snapshot().overlay.markers.map((marker) => marker.type), ['HOME', 'POI']);
});

test('revision conflict fails closed without mixing pose, path or overlay', () => {
  const state = createCockpitMapStore().update(input(navigation({ map: { id: MAP_ID, revision: 'd'.repeat(64) } })));
  assert.equal(state.status, 'CONFLICT');
  assert.equal(state.conflictReason, 'NAVIGATION_MAP_REVISION_MISMATCH');
  assert.equal(state.localization.pose, null);
  assert.equal(state.path.length, 0);
  assert.equal(state.overlay, null);
});

test('stale localization keeps an explicit last-known pose but removes normal pose and overlay trail', () => {
  const store = createCockpitMapStore();
  store.update(input());
  const stale = store.update(input(navigation({ localization_health: { state: 'STALE', reason_code: 'ODOMETRY_STALE', metrics: { odometry_age_s: 4, tf_age_s: 0.1 } } })));
  assert.equal(stale.status, 'STALE');
  assert.equal(stale.localization.pose, null);
  assert.ok(stale.localization.lastPose);
  assert.equal(stale.localization.fresh, false);
  assert.equal(stale.overlay.trail.length, 0);
});

test('pose trail and supplied navigation path stay bounded', () => {
  const store = createCockpitMapStore({ maxTrail: 3, maxPath: 4 });
  for (let index = 0; index < 8; index += 1) {
    store.update(input(navigation({
      localization: { state: 'localized', pose: { x: 1 + index * 0.1, y: 2, yaw: 0, frame_id: 'map' } },
      path: Array.from({ length: 20 }, (_, point) => ({ x: point, y: 0 })),
    })));
  }
  assert.equal(store.snapshot().trail.length, 3);
  assert.equal(store.snapshot().path.length, 4);
  assert.ok(COCKPIT_MAP_LIMITS.trail >= store.snapshot().trail.length);
});

test('map panel subscribes only while active and releases on compact or close lifecycle', () => {
  let subscriptions = 0; let releases = 0; let renders = 0; let clears = 0; let destroys = 0;
  const mapState = {
    selectAnnotation() {},
    subscribe(callback) { subscriptions += 1; callback({}); return () => { releases += 1; }; },
  };
  const panel = createMapPanel({ mapState, viewFactory: () => ({ render() { renders += 1; }, clear() { clears += 1; }, destroy() { destroys += 1; } }) });
  panel.mount({}); panel.activate(); panel.activate();
  assert.deepEqual({ subscriptions, renders }, { subscriptions: 1, renders: 1 });
  panel.deactivate(); panel.deactivate();
  assert.deepEqual({ releases, clears }, { releases: 1, clears: 1 });
  panel.activate(); panel.destroy(); panel.destroy();
  assert.deepEqual({ subscriptions, releases, destroys }, { subscriptions: 2, releases: 2, destroys: 1 });
});

test('occupancy raster decodes once per pinned revision, not once per resize', () => {
  let imageWrites = 0;
  const context = { createImageData: (width, height) => ({ data: new Uint8ClampedArray(width * height * 4) }), putImageData() { imageWrites += 1; } };
  const cache = createOccupancyRasterCache({ document: { createElement: () => ({ getContext: () => context }) }, decodeBase64: () => String.fromCharCode(...Array(16).fill(0)) });
  assert.strictEqual(cache.get({ ...map, dataB64: map.data_b64 }, navigationEngine), cache.get({ ...map, dataB64: map.data_b64 }, navigationEngine));
  assert.equal(cache.diagnostics().decodes, 1);
  assert.equal(imageWrites, 1);
  cache.get({ ...map, revision: 'e'.repeat(64), dataB64: map.data_b64 }, navigationEngine);
  assert.equal(cache.diagnostics().decodes, 2);
});

test('map pose projection reuses the navigation transform including rotated origin and canvas Y inversion', () => {
  const layout = navigationEngine.mapLayout(map, 400, 300, 0);
  const point = navigationEngine.worldToCanvas(layout, { x: 1, y: 2.25, yaw: 0 });
  assert.equal(point.inside, true);
  assert.ok(Number.isFinite(point.x) && Number.isFinite(point.y) && Number.isFinite(point.heading));
  assert.ok(Math.abs(point.heading - Math.PI / 2) < 1e-9);
});
