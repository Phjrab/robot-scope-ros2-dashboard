import test from 'node:test';
import assert from 'node:assert/strict';
import { gridToWorld, worldToGrid, familyPins, pathPoses } from '../robot_dashboard/static/features/route_planner/spatial_editor.js';
import { createRoutePlannerClient } from '../robot_dashboard/static/features/cockpit/route_planner_client.js';

test('editor maps image-down coordinates into translated rotated ROS map coordinates', () => {
  const map = { width: 200, height: 100, resolution: 0.05, origin: [2, -3, Math.PI / 2] };
  const p = gridToWorld(map, 20, 60);
  assert.ok(Math.abs(p.x) < 1e-10); assert.ok(Math.abs(p.y + 2) < 1e-10);
  const restored = worldToGrid(map, p);
  assert.ok(Math.abs(restored.x - 20) < 1e-10); assert.ok(Math.abs(restored.y - 60) < 1e-10);
});

test('map lineage must uniquely match exact occupancy revision', () => {
  const map = { map_id: 'a'.repeat(24), revision: 'b'.repeat(64) };
  const f = { family_id: 'c'.repeat(24), family_revision: 'd'.repeat(64), source: { pcd_map_id: 'e'.repeat(24), pcd_revision: 'f'.repeat(64) }, occupancy: { map_id: map.map_id, map_revision: map.revision } };
  const document = { map_id: map.map_id, map_revision: map.revision, families: [f] };
  assert.equal(familyPins(map, document).pcd_map_id, f.source.pcd_map_id);
  assert.throws(() => familyPins(map, { ...document, families: [] }));
  assert.throws(() => familyPins(map, { ...document, families: [f, f] }));
  assert.throws(() => familyPins({ ...map, revision: '0'.repeat(64) }, document));
});

test('path headings follow segment direction and preserve chosen final heading and pose metadata', () => {
  const poses = pathPoses([{ x: 1, y: 2, hold_seconds: 4 }, { x: 1, y: 3 }], -90);
  assert.equal(poses[0].yaw, Math.PI / 2); assert.equal(poses[1].yaw, -Math.PI / 2);
  assert.equal(poses[0].hold_seconds, 4);
  assert.throws(() => pathPoses([], 0));
  assert.throws(() => pathPoses([{ x: NaN, y: 0 }], 0));
  assert.throws(() => pathPoses([{ x: 0, y: 0 }], 181));
});

test('spatial authoring uses revision CAS and never invokes execution endpoints', async () => {
  const calls = [];
  const client = createRoutePlannerClient({ api: async (path, options) => { calls.push({ path, options }); return { available: true, state: 'EMPTY' }; } });
  await client.refresh();
  const previous = { route_id: 'a'.repeat(24), revision: 'b'.repeat(64) };
  await client.saveSpatialRoute({ label: 'test' }, previous);
  assert.equal(calls.at(-1).options.method, 'PATCH');
  assert.equal(JSON.parse(calls.at(-1).options.body).base_revision, previous.revision);
  assert.ok(calls.every((call) => !/missions|navigation|control/.test(call.path)));
  client.destroy();
});

test('schematic context cannot write an actual-map spatial route', async () => {
  const calls = [];
  const client = createRoutePlannerClient({ api: async (path) => { calls.push(path); return { schematic: { map_kind: 'SCHEMATIC_MANUAL', context: 'SCHEMATIC_MANUAL', state: 'EMPTY' } }; } });
  await client.refresh();
  await assert.rejects(client.saveSpatialRoute({ label: 'not a ROS map' }));
  assert.equal(calls.length, 1); client.destroy();
});
