import assert from 'node:assert/strict';
import test from 'node:test';
import { createRoutePlannerClient, projectState } from '../robot_dashboard/static/features/cockpit/route_planner_client.js';
import { schematicPoint } from '../robot_dashboard/static/features/route_planner/competition_map_view.js';

function payload() { return { available: true, schematic: { available: true, context: 'DEMO', map_kind: 'SCHEMATIC_MANUAL', state: 'READY', revision: 3, distance_m: null, eta_s: null, recommendations: [], guidance: { current_segment_index: 0, progress_revision: 0 } } }; }
test('schematic preserves unknown units and never produces a ROS map overlay', () => {
  const s = projectState(payload());
  assert.equal(s.schematic.distance_m, null); assert.equal(s.schematic.eta_s, null);
  assert.equal(s.graph, null); assert.equal(s.selectedRoute, null); assert.equal(s.overlay, null);
});
test('schematic client reuses one polling loop and only display command surface', async () => {
  const calls = []; const timers = new Set();
  const c = createRoutePlannerClient({ api: async (path, opts) => { calls.push([path, opts]); return payload(); }, setInterval: (fn) => { timers.add(fn); return fn; }, clearInterval: (fn) => timers.delete(fn) });
  const a = c.subscribe(() => {}); const b = c.subscribe(() => {}); await c.refresh();
  assert.equal(timers.size, 1);
  await c.createOrder({ label: 'test', orders: [] }); await c.calculate({ operation_mode: 'AUTO_NAV2' });
  const r = { id: 'schematic-test', revision: 'r' };
  await c.select(r); await c.startGuidance(r); await c.stopGuidance();
  await c.preview(r); await c.exportMission(r); await c.missionDryRun(r); await c.beginRehearsal(r, 'test');
  assert.ok(calls.every(([path]) => ['/api/v1/route-planner', '/api/v1/route-planner/schematic'].includes(path)));
  assert.doesNotMatch(JSON.stringify(calls), /AUTO_NAV2|cmd_vel|\/control|\/missions|\/navigation/);
  a(); assert.equal(timers.size, 1); b(); assert.equal(timers.size, 0); c.destroy();
});
test('disconnected schematic keeps reference data but disables live claims', async () => {
  let fail = false;
  const c = createRoutePlannerClient({ api: async () => { if (fail) throw new Error('offline'); return payload(); } });
  await c.refresh(); fail = true; await c.refresh();
  assert.equal(c.snapshot().schematic.context, 'DEMO'); assert.equal(c.snapshot().schematic.available, false); assert.match(c.snapshot().error, /offline/); c.destroy();
});
test('schematic clicks use inverse SVG screen matrix, not CSS pixel calibration', () => {
  const svg = { getScreenCTM: () => ({ inverse: () => ({ scale: .5 }) }), createSVGPoint: () => ({ matrixTransform(m) { return { x: this.x*m.scale, y: this.y*m.scale }; } }) };
  assert.deepEqual(schematicPoint(svg, 400, 200), { x: 200, y: 100 });
  assert.equal(schematicPoint({ ...svg, getScreenCTM: () => null }, 0, 0), null);
});

test('manual records support LAN HTTP without crypto.randomUUID', async () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  Object.defineProperty(globalThis, 'crypto', { configurable: true, value: { getRandomValues: (bytes) => bytes.fill(37) } });
  const writes = [];
  const value = payload();
  value.schematic.recommendations = [{ id: 'schematic-route', revision: 'revision' }];
  value.schematic.selected_route_id = 'schematic-route';
  const client = createRoutePlannerClient({ api: async (path, options) => { if (options) writes.push(JSON.parse(options.body)); return value; } });
  try {
    await client.refresh();
    await client.schematicEvent('STEP');
    assert.equal(writes.length, 1);
    assert.match(writes[0].data.event_id, /^[0-9a-f]{32}$/);
    assert.equal(writes[0].data.route_id, 'schematic-route');
  } finally {
    client.destroy();
    Object.defineProperty(globalThis, 'crypto', descriptor);
  }
});
