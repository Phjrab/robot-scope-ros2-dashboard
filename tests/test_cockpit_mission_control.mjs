import assert from 'node:assert/strict';
import test from 'node:test';
import { MISSION_PRESETS, missionPresetDocument } from '../robot_dashboard/static/features/cockpit/mission_presets.js';
import { PLACEHOLDER_DESCRIPTORS } from '../robot_dashboard/static/features/cockpit/panel_registry.js';
import { projectMissionInspector } from '../robot_dashboard/static/features/cockpit/mission_inspector.js';
import { missionPageFromHash, filterSavedMapEntries, frameProvenance } from '../robot_dashboard/static/features/cockpit/mission_shell.js';
import { projectCockpitPointcloud } from '../robot_dashboard/static/features/cockpit/workspace.js';
import { projectCameraPanelState } from '../robot_dashboard/static/features/cockpit/panels/camera_panel.js';

const registry = { list: () => PLACEHOLDER_DESCRIPTORS, get: (type) => PLACEHOLDER_DESCRIPTORS.find((entry) => entry.panelType === type) };
test('Mission presets are bounded unique existing panels and only UI preferences', () => {
  for (const preset of MISSION_PRESETS) {
    const layout = missionPresetDocument(preset.id, 'go2', registry, { width: 1000 });
    assert.equal(layout.schema_version, 1);
    assert.equal(new Set(layout.panels.map((panel) => panel.id)).size, layout.panels.length);
    assert.deepEqual(Object.keys(layout).sort(), ['name', 'panels', 'profile_id', 'scene', 'schema_version']);
    for (const panel of layout.panels) { assert.ok(panel.x + panel.width <= 1); assert.ok(panel.y + panel.height <= 1); }
  }
  assert.throws(() => missionPresetDocument('arm', 'go2', registry), /Unknown/);
});
test('narrow builtin layouts compact panels without control state or active camera demand', () => {
  assert.ok(missionPresetDocument('capture', 'go2', registry, { width: 390 }).panels.every((panel) => panel.mode === 'compact'));
});
test('default, corrupt and retired routes enter observation while active routes remain', () => {
  const mode = { dedicated: false, pageFromHash: () => 'maps' };
  assert.equal(missionPageFromHash(mode, ''), 'cockpit');
  assert.equal(missionPageFromHash(mode, '#untrusted'), 'cockpit');
  assert.equal(missionPageFromHash(mode, '#maps'), 'maps');
  for (const route of ['#controls', '#experiments', '#/controls']) assert.equal(missionPageFromHash(mode, route), 'cockpit');
  assert.equal(missionPageFromHash({ dedicated: true, pageFromHash: () => 'cockpit' }, '#controls'), 'cockpit');
});
test('inspector separates stale, missing readiness and absent measurements', () => {
  const empty = projectMissionInspector({}, 2000);
  assert.equal(empty.robot, 'NOT_CONNECTED'); assert.equal(empty.samples, '—'); assert.equal(empty.readiness, 'NOT_CONNECTED');
  const state = { health: { robot_online: true, agent_ready: true } };
  const ready = projectMissionInspector({ state, stateUpdatedAt: 1000, navigation: { navigation: { readiness: { tf: true, odometry: false } } } }, 2000);
  assert.equal(ready.robot, 'CONNECTED'); assert.equal(ready.readiness, 'WAIT · odometry');
  assert.equal(projectMissionInspector({ state, stateUpdatedAt: 1000 }, 5000).robot, 'STALE');
});
test('synthetic pointcloud and camera never project LIVE and stale remains stale', () => {
  const cloud = { points: [0, 0, 0], data_provenance: 'SYNTHETIC_FIXTURE' };
  assert.equal(projectCockpitPointcloud({ cloud, ready: true, lastFrameAt: 1000, now: 1500 }).freshness, 'FIXTURE');
  assert.equal(projectCockpitPointcloud({ cloud, ready: true, lastFrameAt: 1000, now: 9000 }).freshness, 'STALE');
  const source = { connection: 'live', metadata: { data_provenance: 'SYNTHETIC_FIXTURE' } };
  assert.equal(projectCameraPanelState(source, 1000, 1500).state, 'FIXTURE');
  assert.equal(projectCameraPanelState(source, 1000, 9000).state, 'STALE');
  assert.equal(frameProvenance({ data_provenance: 'REPLAY' }), 'REPLAY');
  assert.equal(projectCockpitPointcloud({ cloud: { ...cloud, data_provenance: 'REPLAY' }, ready: true, lastFrameAt: 1000, now: 1500 }).freshness, 'REPLAY');
  assert.equal(projectCameraPanelState({ ...source, metadata: { data_provenance: 'REPLAY' } }, 1000, 1500).state, 'REPLAY');
  assert.equal(projectMissionInspector({ state: { health: { robot_online: true, agent_ready: true } }, stateUpdatedAt: 1000, cameras: { sources: [{ id: 'go2_front', ageMs: 500, connection: 'live', metadata: { data_provenance: 'REPLAY' } }] } }, 1500).camera, 'REPLAY');
  assert.equal(frameProvenance({}), 'LIVE');
});
test('saved-map search preserves records and selection identity and handles long unsafe strings literally', () => {
  const maps = [{ id: 'one', name: 'Room <script>', frame_id: 'map' }, { id: 'two', name: '다른 지도', file_name: 'floor.yaml' }];
  assert.deepEqual(filterSavedMapEntries(maps, '  SCRIPT '), [maps[0]]);
  assert.deepEqual(filterSavedMapEntries(maps, 'floor'), [maps[1]]);
  assert.equal(filterSavedMapEntries(maps, ''), maps);
  assert.deepEqual(filterSavedMapEntries(maps, 'not found'), []);
});
