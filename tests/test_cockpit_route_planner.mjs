import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { createRoutePlannerClient, projectState } from '../robot_dashboard/static/features/cockpit/route_planner_client.js';
import { createCockpitSceneHost } from '../robot_dashboard/static/features/cockpit/scene_host.js';

const route = (id, profile, points = 3) => ({
  id: id.repeat(32), revision: id.repeat(64), profile, profiles: [profile], operation_mode: 'AUTO_NAV2',
  map_id: 'a'.repeat(24), map_revision: 'b'.repeat(64), annotation_revision: 'c'.repeat(64), graph_revision: 'd'.repeat(64),
  start_node_id: 'START_NODE', executable: false, reason: 'SPECIAL_EDGE_NOT_READY',
  stops: [{ index: 0, node_id: 'HANSOT_DOCK', annotation_id: '1'.repeat(24), role: 'RESTAURANT_DOCK', venue_id: 'HANSOT', label: '한솥' }],
  segments: [{ index: 0, edge_id: 'EDGE_ONE', from_node_id: 'START_NODE', to_node_id: 'HANSOT_DOCK', type: 'CROSSWALK', label: 'Start → Hansot', distance_m: 2, travel_time_s: 10, expected_wait_s: 5, risk: 1,
    requirements: [{ id: 'TRAFFIC_GREEN', state: 'UNKNOWN' }], polyline: Array.from({ length: points }, (_, index) => ({ x: index / 10, y: 0, z: 0.035 })) }],
  metrics: { distance_m: 2, travel_time_s: 10, food_wait_s: 20, signal_wait_s: 5, risk_score: 1, eta_s: 35, crosswalk_count: 1, underpass_count: 0, turn_count: 0, special_behavior_count: 1 },
});

function payload() {
  const balanced = route('1', 'BALANCED', 5000);
  const fastest = route('2', 'FASTEST', 5000);
  const safest = route('3', 'SAFEST', 5000);
  return {
    available: true, state: 'GUIDANCE_ACTIVE', selected_route_id: balanced.id,
    order: { id: 'f'.repeat(32), revision: 'e'.repeat(64), label: '예선 주문', destination_id: 'COEX', total_quantity: 3, restaurant_count: 2, difficulty: 'LOW', locked: true,
      lines: [{ sequence: 1, restaurant_id: 'HANSOT', menu_id: 'CHICKEN_MAYO', quantity: 2, ready_at_s: 40 }, { sequence: 2, restaurant_id: 'EDIYA', menu_id: 'AMERICANO', quantity: 1, ready_at_s: 60 }] },
    graph: { graph_revision: 'd'.repeat(64), map_id: 'a'.repeat(24), map_revision: 'b'.repeat(64), annotation_revision: 'c'.repeat(64), nodes: [], edges: [] },
    recommendations: [balanced, fastest, safest],
    guidance: { active: true, instruction_type: 'WAIT_TRAFFIC_GREEN', instruction: '신호 대기', current_segment_index: 0, remaining_distance_m: 1.2, eta_remaining_s: 12, cross_track_error_m: 0.04, requirements: { TRAFFIC_GREEN: 'UNKNOWN' }, completed_pickups: [], dropoff_complete: false },
    perception: { fresh: false, state: 'UNKNOWN', age_s: 2 },
  };
}

test('Route Planner projection is bounded, revision-pinned, and shares one selected route', () => {
  const state = projectState(payload());
  assert.equal(state.state, 'GUIDANCE_ACTIVE');
  assert.equal(state.order.difficulty, 'LOW');
  assert.equal(state.recommendations.length, 3);
  assert.equal(state.selectedRoute.profile, 'BALANCED');
  assert.equal(state.overlay.selectedRoute.length, 128, 'each segment is bounded before the overlay budget');
  assert.equal(state.overlay.alternatives.length, 2);
  assert.equal(state.guidance.instruction_type, 'WAIT_TRAFFIC_GREEN');
});

test('Route Planner client has one polling owner and emits no mission start, goal, lease, or control request', async () => {
  const calls = [];
  const timers = new Map(); let timerId = 0;
  const api = async (path, options = {}) => { calls.push([path, options]); return payload(); };
  const client = createRoutePlannerClient({ api, setInterval(callback) { timers.set(++timerId, callback); return timerId; }, clearInterval(id) { timers.delete(id); } });
  const first = client.subscribe(() => {});
  const second = client.subscribe(() => {});
  await Promise.resolve(); await Promise.resolve();
  assert.equal(timers.size, 1);
  const selected = projectState(payload()).selectedRoute;
  await client.startGuidance(selected);
  await client.markPickup('HANSOT');
  await client.markDropoff('COEX');
  await client.preview(selected);
  await client.exportMission(selected);
  const paths = calls.map(([path]) => path).join('\n');
  assert.doesNotMatch(paths, /\/missions\/[^/]+\/start|\/navigation\/goal|\/control|lease|arm|deadman|cmd_vel|sport/i);
  assert.match(paths, /\/guidance\/start/);
  assert.match(paths, /\/guidance\/pickup/);
  assert.match(paths, /\/guidance\/dropoff/);
  assert.match(paths, /\/export-mission/);
  first(); assert.equal(timers.size, 1); second(); assert.equal(timers.size, 0);
  client.destroy();
});

test('Route overlay reuses the active Cockpit renderer and never creates a second renderer', () => {
  const instances = [];
  class Renderer {
    constructor() { this.overlays = []; instances.push(this); }
    bindControls() {} setStatus() {} clearPointCloud() {} setRobotPose() {} setTrail() {} resetRobotJointPositions() {} configureOfficialRobot() {} resize() {} destroy() {}
    setSpatialOverlay(value) { this.overlays.push(value); }
    clearSpatialOverlay() { this.overlays.push(null); }
  }
  const host = createCockpitSceneHost({ canvas: {}, Renderer });
  host.setMapState({ map: { id: 'a'.repeat(24), revision: 'b'.repeat(64) }, markers: [{ id: '1'.repeat(24), pose: { x: 1, y: 0 }, type: 'DOCK', name: '한솥' }], overlay: { mapId: 'a'.repeat(24), revision: 'b'.repeat(64), frameId: 'map', path: [], trail: [], markers: [] } });
  host.activate(); host.setRouteState(projectState(payload()));
  assert.equal(instances.length, 1);
  assert.equal(host.diagnostics().rendererCount, 1);
  assert.equal(host.diagnostics().routeOverlay.alternativeCount, 2);
  assert.equal(instances[0].overlays.at(-1).routeStops.length, 1);
  host.destroy();
});

test('Route Planner source never owns control or a second renderer', () => {
  const client = readFileSync(new URL('../robot_dashboard/static/features/cockpit/route_planner_client.js', import.meta.url), 'utf8');
  const panel = readFileSync(new URL('../robot_dashboard/static/features/cockpit/panels/route_planner_panel.js', import.meta.url), 'utf8');
  assert.doesNotMatch(client + panel, /new\s+(WebSocket|RobotScene3D)|\/api\/v1\/control|\/cmd_vel|\/api\/sport\/request/);
  assert.doesNotMatch(client + panel, /\/api\/v1\/missions\/[^`'"$]+\/start/);
});
