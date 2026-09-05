import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { createRoutePlannerClient, projectRehearsal, projectState } from '../robot_dashboard/static/features/cockpit/route_planner_client.js';
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

function rehearsalPayload() {
  return {
    enabled: true, active: true, mode: 'REHEARSAL', banner: 'REHEARSAL — VIRTUAL DATA — ROBOT WILL NOT MOVE', virtual_data_only: true,
    scenarios: [{ scenario_id: 'traffic-red-to-green', description: 'Traffic transition', event_count: 4, duration_ms: 100 }],
    scenario: { scenario_id: 'traffic-red-to-green', description: 'Traffic transition' },
    playback: { state: 'PAUSED', speed: 2, position_ms: 50, duration_ms: 100, event_index: 2, event_count: 4 },
    events: Array.from({ length: 300 }, (_, index) => ({ index, at_ms: index, kind: index === 2 ? 'PERCEPTION' : 'POSE', status: index < 2 ? 'APPLIED' : 'PENDING' })),
    expected_actual: { match: false, expected: { stale_or_invalid: 'FRESH' }, actual: { stale_or_invalid: 'STALE' } },
    virtual_robot: { label: 'VIRTUAL ROBOT', source: 'VIRTUAL_ROUTE_REPLAY', frame_id: 'map', x: 0.5, y: 2, yaw: 0, segment_index: 0, segment_progress: 0.5, off_route: true, update_rate_hz: 10 },
    overlay: { current_segment_index: 0, current_segment_progress: 0.5, completed_segment_indices: [], actual_nav2_path_status: 'UNAVAILABLE_IN_REHEARSAL' },
    advisory_behavior: { behavior: 'NORMAL_GUIDANCE', state: 'HOLD', advisory: 'REPLAN_RECOMMENDED', reason_codes: ['ROUTE_DEVIATION'] },
    advisory_transitions: [{ position_ms: 50, behavior: 'NORMAL_GUIDANCE', state: 'HOLD', advisory: 'REPLAN_RECOMMENDED' }],
    delivery: { state: 'EN_ROUTE_PICKUP', advisory: 'PROCEED_RECOMMENDED', cargo_count: 2, cargo_capacity: 5, next_venue_id: 'EDIYA', destination_id: 'COEX', destination_state: 'PENDING', items: [{ sequence: 1, venue_id: 'HANSOT', menu_id: 'CHICKEN_MAYO', quantity: 2, estimated_ready_s: 40, arrival_estimate_s: 10, wait_estimate_s: 30, pickup_state: 'CONFIRMED' }] },
    explainability: { template: 'DETERMINISTIC_METRICS_V1', reason: 'BALANCED: ETA 35.0s, distance 2.0m, risk 1.0.', score_breakdown: { travel_time_s: 10, food_wait_s: 20, signal_wait_s: 5, distance_m: 2, risk_score: 1, crosswalk_count: 1, underpass_count: 0, turn_count: 0, special_behavior_count: 1 }, alternatives: [] },
    mission_dry_run: { eligibility: true, rejection_reason: null, waypoint_count: 3, resolved_annotation_ids: ['1'.repeat(24)], mission_created: false, mission_started: false, navigation_goal_submitted: false },
    restrictions: { control_api_enabled: false, navigation_start_enabled: false, navigation_goal_enabled: false, mission_create_enabled: false, mission_start_enabled: false, real_service_state_included: false },
    side_effect_count: 0, side_effect_counters: { control_acquire: 0, arm: 0, deadman: 0, velocity: 0, navigation_activate: 0, navigation_goal: 0, mission_create: 0, mission_start: 0, sport: 0, service_restart: 0 }, report_available: true,
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

test('Rehearsal projection bounds timeline and keeps virtual pose separate from an unavailable Nav2 path', () => {
  const value = payload(); value.rehearsal = rehearsalPayload();
  const state = projectState(value);
  assert.equal(state.rehearsal.events.length, 256);
  assert.equal(state.rehearsal.virtualRobot.label, 'VIRTUAL ROBOT');
  assert.equal(state.rehearsal.virtualRobot.offRoute, true);
  assert.equal(state.rehearsal.overlay.actualNav2PathStatus, 'UNAVAILABLE_IN_REHEARSAL');
  assert.equal(state.overlay.actualNav2Path.length, 0);
  assert.ok(state.overlay.currentSegment.length > 1 && state.overlay.currentSegment.length < 128);
  assert.equal(state.overlay.virtualRobot.source, 'VIRTUAL_ROUTE_REPLAY');
  assert.equal(state.overlay.advisoryState.advisory, 'REPLAN_RECOMMENDED');
});

test('Rehearsal projection exposes deterministic explainability, cargo, and pure mission dry-run', () => {
  const rehearsal = projectRehearsal(rehearsalPayload());
  assert.equal(rehearsal.explainability.template, 'DETERMINISTIC_METRICS_V1');
  assert.equal(rehearsal.explainability.scoreBreakdown.signal_wait_s, 5);
  assert.equal(rehearsal.delivery.cargoCount, 2);
  assert.equal(rehearsal.delivery.items[0].waitEstimateS, 30);
  assert.equal(rehearsal.missionDryRun.eligibility, true);
  assert.equal(rehearsal.missionDryRun.missionCreated, false);
  assert.equal(rehearsal.sideEffectCount, 0);
  assert.ok(Object.values(rehearsal.sideEffectCounters).every((value) => value === 0));
});

test('Rehearsal client uses only dedicated mock and dry-run endpoints', async () => {
  const calls = [];
  const value = payload(); value.rehearsal = rehearsalPayload();
  const client = createRoutePlannerClient({ api: async (path, options = {}) => { calls.push([path, options]); return value; } });
  const selected = projectState(value).selectedRoute;
  await client.beginRehearsal(selected, 'traffic-red-to-green');
  await client.controlRehearsal('STEP');
  await client.controlRehearsal('SCRUB', { position_ms: 50 });
  await client.controlRehearsal('OFF_ROUTE', { enabled: true });
  await client.controlRehearsal('CONFIRM_PICKUP', { venue_id: 'HANSOT' });
  await client.missionDryRun(selected);
  await client.rehearsalReport();
  const paths = calls.map(([path]) => path).join('\n');
  assert.match(paths, /\/rehearsal\/start/);
  assert.match(paths, /\/rehearsal\/control/);
  assert.match(paths, /\/mission-dry-run/);
  assert.match(paths, /\/rehearsal\/report/);
  assert.doesNotMatch(paths, /\/export-mission|\/missions\/[^/]+\/(create|start)|\/navigation\/(start|goal)|\/api\/v1\/control|lease|arm|deadman|cmd_vel|sport/i);
  client.destroy();
});

test('Rehearsal panel is server-flag hidden and visibly labels every virtual-only boundary', () => {
  const panel = readFileSync(new URL('../robot_dashboard/static/features/cockpit/panels/route_planner_panel.js', import.meta.url), 'utf8');
  assert.match(panel, /rehearsalSection\.hidden = !value\.enabled/);
  assert.match(panel, /REHEARSAL — VIRTUAL DATA — ROBOT WILL NOT MOVE/);
  assert.match(panel, /VIRTUAL ROBOT/);
  assert.match(panel, /UNAVAILABLE/);
  assert.match(panel, /MISSION DRY-RUN/);
  assert.doesNotMatch(panel, /new\s+(WebSocket|RobotScene3D)/);
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
