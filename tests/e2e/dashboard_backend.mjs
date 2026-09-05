import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const navigationContract = require('../../robot_dashboard/static/navigation.js');
const MAP_ID = '0123456789abcdef01234567';
const MAP_REVISION = 'a'.repeat(64);
const PARAMETER_REVISION = 'b'.repeat(64);
const ANNOTATION_REVISION = 'c'.repeat(64);
const ANNOTATION_ID = 'd'.repeat(24);
const SECOND_ANNOTATION_ID = 'e'.repeat(24);
const MISSION_ID = '9'.repeat(32);
const ROUTE_ORDER_ID = '6'.repeat(32);
const ROUTE_ORDER_REVISION = '7'.repeat(64);
const ROUTE_GRAPH_REVISION = '8'.repeat(64);

function routePlan(id, profile, distance, eta, risk) {
  const routeId = id.repeat(32);
  return {
    id: routeId, revision: id.repeat(64), profile, profiles: [profile], operation_mode: 'AUTO_NAV2',
    map_id: MAP_ID, map_revision: MAP_REVISION, annotation_revision: ANNOTATION_REVISION,
    graph_revision: ROUTE_GRAPH_REVISION, start_node_id: 'START_NODE', executable: true, reason: '',
    stops: [
      { index: 0, node_id: 'HANSOT_DOCK', annotation_id: '1'.repeat(24), role: 'RESTAURANT_DOCK', venue_id: 'HANSOT', label: '한솟도시락' },
      { index: 1, node_id: 'EDIYA_DOCK', annotation_id: '2'.repeat(24), role: 'RESTAURANT_DOCK', venue_id: 'EDIYA', label: '이디야커피' },
      { index: 2, node_id: 'COEX_DOCK', annotation_id: '3'.repeat(24), role: 'DESTINATION_DOCK', venue_id: 'COEX', label: '코엑스' },
    ],
    node_ids: ['START_NODE', 'HANSOT_DOCK', 'EDIYA_DOCK', 'COEX_DOCK'],
    segments: [
      { index: 0, edge_id: 'START_HANSOT', from_node_id: 'START_NODE', to_node_id: 'HANSOT_DOCK', type: 'NORMAL_WALKWAY', label: 'Start → Hansot', distance_m: distance / 3, travel_time_s: 10, expected_wait_s: 0, risk: risk / 3, requirements: [], allow_replan: true, polyline: [{ x: 0, y: 0 }, { x: 1, y: 0 }] },
      { index: 1, edge_id: 'HANSOT_EDIYA', from_node_id: 'HANSOT_DOCK', to_node_id: 'EDIYA_DOCK', type: 'CROSSWALK', label: 'Hansot → Ediya', distance_m: distance / 3, travel_time_s: 12, expected_wait_s: 5, risk: risk / 3, requirements: [{ id: 'TRAFFIC_GREEN', state: 'READY' }], allow_replan: true, polyline: [{ x: 1, y: 0 }, { x: 2, y: 0 }] },
      { index: 2, edge_id: 'EDIYA_COEX', from_node_id: 'EDIYA_DOCK', to_node_id: 'COEX_DOCK', type: 'DOCKING_APPROACH', label: 'Ediya → COEX', distance_m: distance / 3, travel_time_s: 13, expected_wait_s: 0, risk: risk / 3, requirements: [{ id: 'ARUCO_DOCKING', state: 'READY' }], allow_replan: true, polyline: [{ x: 2, y: 0 }, { x: 3, y: 0 }] },
    ],
    metrics: { distance_m: distance, travel_time_s: 35, food_wait_s: 60, signal_wait_s: 5, risk_score: risk, eta_s: eta, crosswalk_count: 1, underpass_count: 0, turn_count: 0, special_behavior_count: 2 },
  };
}

function baseRoutePlanner() {
  return {
    available: true, state: 'DRAFT', error: null, selected_route_id: null,
    order: null,
    graph: {
      graph_revision: ROUTE_GRAPH_REVISION, map_id: MAP_ID, map_revision: MAP_REVISION,
      annotation_revision: ANNOTATION_REVISION,
      nodes: [
        { id: 'START_NODE', role: 'START', label: 'E2E Start' },
        { id: 'HANSOT_DOCK', role: 'RESTAURANT_DOCK', venue_id: 'HANSOT', label: '한솟도시락' },
        { id: 'EDIYA_DOCK', role: 'RESTAURANT_DOCK', venue_id: 'EDIYA', label: '이디야커피' },
        { id: 'COEX_DOCK', role: 'DESTINATION_DOCK', venue_id: 'COEX', label: '코엑스' },
      ],
      edges: [],
    },
    recommendations: [],
    guidance: { active: false, completed_pickups: [], dropoff_complete: false, current_segment_index: 0 },
    perception: { fresh: true, state: 'FRESH', age_s: 0.1 },
    rehearsal: { enabled: false, active: false, mode: 'DISABLED', scenarios: [], side_effect_count: 0 },
    motion_authority: false,
  };
}

const rehearsalSideEffects = () => ({ control_acquire: 0, arm: 0, deadman: 0, velocity: 0, navigation_activate: 0, navigation_goal: 0, mission_create: 0, mission_start: 0, sport: 0, service_restart: 0 });

function readyRehearsal() {
  return {
    enabled: true, active: false, mode: 'READY', side_effect_count: 0,
    scenarios: [
      { scenario_id: 'traffic-red-to-green', description: 'RED to stable GREEN', event_count: 2, duration_ms: 100 },
      { scenario_id: 'person-occupied', description: 'Person occupied crosswalk', event_count: 1, duration_ms: 100 },
      { scenario_id: 'aruco-docking-ready', description: 'ArUco docking ready', event_count: 1, duration_ms: 100 },
    ],
  };
}

function activeRehearsal(scenarioId) {
  const behavior = scenarioId === 'person-occupied'
    ? { behavior: 'CROSSWALK', state: 'WAIT_PERSON', advisory: 'WAIT', reason_codes: ['PERSON_OCCUPIED'] }
    : scenarioId === 'aruco-docking-ready'
      ? { behavior: 'DOCKING', state: 'READY', advisory: 'DOCKING_READY', reason_codes: [] }
      : { behavior: 'CROSSWALK', state: 'WAIT_SIGNAL', advisory: 'WAIT', reason_codes: ['TRAFFIC_RED'] };
  return {
    ...readyRehearsal(), active: true, mode: 'REHEARSAL', banner: 'REHEARSAL — VIRTUAL DATA — ROBOT WILL NOT MOVE', virtual_data_only: true,
    scenario: { scenario_id: scenarioId, description: scenarioId },
    playback: { state: 'PAUSED', speed: 1, position_ms: 0, duration_ms: 100, event_index: 0, event_count: 2 },
    events: [{ index: 0, at_ms: 0, kind: 'PERCEPTION', status: 'PENDING' }, { index: 1, at_ms: 100, kind: 'POSE', status: 'PENDING' }],
    expected_actual: { match: false, expected: {}, actual: {} },
    virtual_robot: { label: 'VIRTUAL ROBOT', source: 'VIRTUAL_ROUTE_REPLAY', frame_id: 'map', x: 0, y: 0, yaw: 0, segment_index: 0, segment_progress: 0, off_route: false, update_rate_hz: 10 },
    overlay: { current_segment_index: 0, current_segment_progress: 0, completed_segment_indices: [], actual_nav2_path_status: 'UNAVAILABLE_IN_REHEARSAL' },
    advisory_behavior: behavior, advisory_transitions: [],
    delivery: {
      state: 'EN_ROUTE_PICKUP', advisory: 'PROCEED_RECOMMENDED', cargo_count: 0, cargo_capacity: 5, next_venue_id: 'HANSOT', destination_id: 'COEX', destination_state: 'PENDING',
      items: [
        { sequence: 1, venue_id: 'HANSOT', menu_id: 'CHICKEN_MAYO', quantity: 2, estimated_ready_s: 40, arrival_estimate_s: 10, wait_estimate_s: 30, pickup_state: 'PENDING' },
        { sequence: 2, venue_id: 'EDIYA', menu_id: 'AMERICANO', quantity: 1, estimated_ready_s: 60, arrival_estimate_s: 20, wait_estimate_s: 40, pickup_state: 'PENDING' },
      ],
    },
    explainability: { template: 'DETERMINISTIC_METRICS_V1', reason: 'BALANCED: ETA 100.0s, distance 30.0m, risk 3.0.', score_breakdown: { travel_time_s: 35, food_wait_s: 60, signal_wait_s: 5, distance_m: 30, risk_score: 3, crosswalk_count: 1, underpass_count: 0, turn_count: 0, special_behavior_count: 2 }, alternatives: [] },
    mission_dry_run: { eligibility: true, rejection_reason: null, waypoint_count: 3, resolved_annotation_ids: ['1'.repeat(24), '2'.repeat(24), '3'.repeat(24)], mission_created: false, mission_started: false, navigation_goal_submitted: false },
    restrictions: { control_api_enabled: false, navigation_start_enabled: false, navigation_goal_enabled: false, mission_create_enabled: false, mission_start_enabled: false, real_service_state_included: false },
    side_effect_count: 0, side_effect_counters: rehearsalSideEffects(), report_available: true,
  };
}

const tunedNavigationValues = { ...navigationContract.TUNED_VALUES };

function baseControl() {
  return {
    enabled: true, configured: true, available: true, state: 'ready',
    bridge: { state: 'ready', connected: true, available: true, authenticated: true, status_age_s: 0.1 },
    lease: { active: false, bound: false, source: null },
    estop_latched: false,
    limits: { max_linear_x: 0.5, max_linear_y: 0.3, max_angular_z: 1, default_speed_scale: 0.3 },
    actions: [], command: { linear_x: 0, linear_y: 0, angular_z: 0, deadman: false },
  };
}

function baseNavigation() {
  return {
    available: true, robot_online: true,
    pipeline: { state: 'idle', job_id: null, error: '' },
    localization_pipeline: { state: 'idle', phase: 'idle', pending: false, owned_by_navigation: false, job_id: null, error: '' },
    map: null,
    localization: { state: 'uninitialized', pose: null },
    goal: { state: 'idle', goal_id: null, message: '' },
    readiness: { map_server: false, planner: false, controller: false, behavior: false, cmd_bridge: true, map: false, scan: false, odometry: false, tf: false, localization: false },
    runtime_health: { localized: false },
    safety: { can_start: true, can_stop: false, can_set_initial_pose: false, can_send_goal: false, blockers: [] },
    bindings: { scan: '/scan', odometry: '/utlidar/robot_odom' },
  };
}

function baseMapping() {
  return {
    pipeline: { state: 'idle', job_id: null, error: '' },
    preview: { state: 'running' },
    operation: { state: 'idle', kind: '', job_id: null, error: '', files: [] },
    logs: [], log_cursor: 0, logs_truncated: false,
  };
}

function baseDataset() {
  return {
    available: true, state: 'idle', active: false, session_id: '', sources: [],
    capture_hz: 0, elapsed_s: 0, saved: 0, dropped: 0, bytes_written: 0,
    free_bytes: 12 * 1024 ** 3, session_quota_bytes: 20 * 1024 ** 3,
    minimum_free_bytes: 5 * 1024 ** 3, output_path: '/srv/robot-scope/datasets', last_error: '',
  };
}

function json(route, value, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
}

export async function installDashboardBackend(page, options = {}) {
  const routePlanner = baseRoutePlanner();
  if (options.routePlannerRehearsal === true) routePlanner.rehearsal = readyRehearsal();
  const state = {
    online: options.online !== false,
    pointMax: 10_000,
    mapping: baseMapping(), navigation: baseNavigation(), control: baseControl(), dataset: baseDataset(),
    routePlanner,
    competition: {
      schema_version: 'robot-scope.competition-state/v1', operation_mode: 'MANUAL',
      requested_mode: 'MANUAL', locked: false, revision: 1,
      motion_authority: 'NONE', perception_mode: 'SHADOW',
    },
    perceptionOnline: true,
    mapRevision: MAP_REVISION, serviceBlocked: Boolean(options.serviceBlocked),
    annotations: {
      schema_version: 1, map_id: MAP_ID, map_revision: MAP_REVISION,
      annotation_revision: ANNOTATION_REVISION, revision: ANNOTATION_REVISION, exists: true,
      points: [
        { id: ANNOTATION_ID, type: 'HOME', name: 'E2E Home', pose: { x: 0.5, y: 0.5, yaw: 0 } },
        ...(options.includeSecondAnnotation
          ? [{ id: SECOND_ANNOTATION_ID, type: 'INSPECTION_POINT', name: 'E2E Inspect', pose: { x: 0.75, y: 0.5, yaw: 0 } }]
          : []),
      ],
      polygons: [],
    },
    missions: [], activeMissionId: null,
    requests: [], wsConnections: { camera: 0, pointcloud: 0, joints: 0, pose: 0, control: 0 },
    wsCloses: { camera: 0, pointcloud: 0 },
    cameraConnectionsBySource: { go2_front: 0, realsense_color: 0 },
    cameraClosesBySource: { go2_front: 0, realsense_color: 0 },
    cameraStreaming: { go2_front: true, realsense_color: true },
  };
  const handlers = new Map();

  const backend = {
    state,
    mapId: MAP_ID,
    mapRevision: MAP_REVISION,
    parameterRevision: PARAMETER_REVISION,
    annotationRevision: ANNOTATION_REVISION,
    annotationId: ANNOTATION_ID,
    secondAnnotationId: SECOND_ANNOTATION_ID,
    on(path, handler) { handlers.set(path, handler); },
    mutations(path) { return state.requests.filter((entry) => entry.path === path); },
    completeMissionWaypoint() {
      const mission = state.missions.find((item) => item.id === state.activeMissionId); if (!mission) return;
      mission.waypoints[mission.current_index].status = 'completed'; mission.completed_count += 1; mission.current_index += 1;
      mission.logs.push({ seq: mission.logs.length + 1, timestamp: '2026-08-28T00:00:00.000Z', event: 'waypoint_completed', waypoint_index: mission.current_index - 1 });
      if (mission.current_index >= mission.waypoints.length) { mission.state = 'completed'; mission.outcome = 'completed'; mission.ownership_active = false; mission.remaining_count = 0; state.activeMissionId = null; state.navigation.goal = { state: 'succeeded', goal_id: null }; }
      else { mission.remaining_count -= 1; mission.current_waypoint = mission.waypoints[mission.current_index]; mission.waypoints[mission.current_index].status = 'running'; state.navigation.goal = { state: 'active', goal_id: String(mission.current_index + 3).repeat(32).slice(0, 32) }; }
    },
  };

  await page.routeWebSocket('**/api/v1/ws/**', async (socket) => {
    const socketUrl = new URL(socket.url());
    const path = socketUrl.pathname;
    const kind = path.endsWith('/camera') ? 'camera'
      : path.endsWith('/pointcloud') ? 'pointcloud'
        : path.endsWith('/joints') ? 'joints'
          : path.endsWith('/pose') ? 'pose' : 'control';
    state.wsConnections[kind] += 1;
    const cameraSourceId = kind === 'camera' ? String(socketUrl.searchParams.get('source_id') || '') : '';
    if (cameraSourceId) state.cameraConnectionsBySource[cameraSourceId] = (state.cameraConnectionsBySource[cameraSourceId] || 0) + 1;
    let cameraTimer = null;
    socket.onClose(() => {
      if (kind === 'camera' || kind === 'pointcloud') state.wsCloses[kind] += 1;
      if (cameraSourceId) state.cameraClosesBySource[cameraSourceId] = (state.cameraClosesBySource[cameraSourceId] || 0) + 1;
      if (cameraTimer) clearInterval(cameraTimer);
    });
    const closeFirstSockets = Array.isArray(options.closeFirstSockets) ? options.closeFirstSockets : [];
    if ((options.closeFirstSocket === kind || closeFirstSockets.includes(kind)) && state.wsConnections[kind] === 1) {
      setTimeout(() => socket.close({ code: 1012, reason: 'fake reconnect' }), 30);
    } else if (cameraSourceId) {
      let seq = 0;
      const sendFrame = () => {
        if (state.cameraStreaming[cameraSourceId] === false) return;
        seq += 1;
        const observability = cameraSourceId === 'realsense_color' ? {
          receive_fps: 14.8,
          receive_bitrate_mbps: 4.125,
          restart_count: 1,
          status_class: 'LIVE',
          cross_host_latency_state: 'UNVERIFIED_CLOCK_DOMAIN',
          relay_health: {
            state: 'streaming', fps: 15, last_frame_age_s: 0.12,
            payload_bitrate_mbps: 3.9,
            profile: { width: 640, height: 480, fps: 15, jpeg_quality: 72 },
            wifi: { state: 'LIVE', interface: 'wlan0', rssi_dbm: -54, link_mbps: 433.3 },
          },
        } : {};
        socket.send(JSON.stringify({
          source_id: cameraSourceId, topic: cameraSourceId === 'go2_front' ? '/camera/image' : '/camera/color/image_raw',
          format: 'raw', encoding: 'rgb8', width: 4, height: 3, step: 12, fps: 15, transport: 'fake', state: 'ok', seq,
          ...observability,
        }));
        socket.send(Buffer.from([
          240, 40, 40, 40, 240, 40, 40, 40, 240, 220, 220, 40,
          40, 220, 220, 220, 40, 220, 180, 180, 180, 90, 150, 220,
          220, 90, 150, 150, 220, 90, 90, 150, 220, 240, 240, 240,
        ]));
      };
      sendFrame();
      cameraTimer = setInterval(sendFrame, 120);
    }
  });

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    let body = null;
    try { body = request.postDataJSON(); } catch (_) {}
    if (method !== 'GET') state.requests.push({ path, method, body });
    const custom = handlers.get(path);
    if (custom) return custom({ route, request, url, path, method, body, state, json: (value, status) => json(route, value, status) });

    if (path === '/api/v1/robots/types') return json(route, {
      selected_type: 'go2',
      types: [{
        id: 'go2', label: 'Unitree Go2', description: 'E2E fake robot',
        capabilities: { observability: true, camera: true, mapping: true, manual_control: true, navigation: true },
        model: { kind: 'robot-model-lite', asset_url: '/static/assets/go2/go2-official-lite.json', urdf_url: '', label: 'Go2', fidelity: 'official-derived' },
      }],
    });
    if (path === '/api/v1/state') {
      if (!state.online) return json(route, { detail: 'offline' }, 503);
      return json(route, {
        health: { agent_ready: true, robot_target_connected: true, robot_online: true, robot_ip: '192.168.123.161', ros_interface_ready: true },
        robot: { type: 'go2' },
        sources: { pointcloud: '/cloud_registered', odometry: '/Odometry', occupancy_grid: '/map', camera: '/camera/image' },
        mapping: { state: 'mapping', cloud: { state: 'ok', hz: 8, frame_id: 'camera_init' }, odometry: { state: 'ok', hz: 50 }, map: {} },
        camera: { state: 'ok', live: true, age_s: 0.1, fps: 15, topic: '/camera/image' },
        sensors: [
          { category: 'robot_state', state: 'ok', age_s: 0.05, hz: 50, topic: '/lowstate', values: {} },
          { category: 'battery', state: 'ok', age_s: 0.1, hz: 10, topic: '/lowstate', values: { battery_soc: 83, power_v: 28.4 } },
        ],
      });
    }
    if (path === '/api/v1/topics') return json(route, { topics: [
      { name: '/Laser_map', type: 'sensor_msgs/msg/PointCloud2', category: 'pointcloud', state: state.mapping.pipeline.state === 'running' ? 'ok' : 'waiting', publishers: state.mapping.pipeline.state === 'running' ? 1 : 0, hz: state.mapping.pipeline.state === 'running' ? 1 : null, age_s: state.mapping.pipeline.state === 'running' ? 0.1 : null },
      { name: '/cloud_registered', type: 'sensor_msgs/msg/PointCloud2', category: 'pointcloud', state: 'ok', publishers: 1, hz: 8, age_s: 0.1 },
      { name: '/Odometry', type: 'nav_msgs/msg/Odometry', category: 'odometry', state: 'ok', publishers: 1, hz: 50, age_s: 0.1 },
    ] });
    if (path === '/api/v1/sources') return json(route, {
      selected: { camera: '/camera/image', pointcloud: '/cloud_registered', odometry: '/Odometry', occupancy_grid: '/map' },
      selected_descriptors: { pointcloud: { id: '/cloud_registered', topic: '/cloud_registered', sensor_id: 'xt16', pipeline_stage: 'registered' } },
      selection: { pointcloud: { pinned: true } }, locked: { camera: false },
      options: { camera: ['/camera/image'], pointcloud: ['/cloud_registered'], odometry: ['/Odometry'], occupancy_grid: ['/map'] },
      metadata: { pointcloud: [{ id: '/cloud_registered', topic: '/cloud_registered', sensor_id: 'xt16', pipeline_stage: 'registered' }] },
    });
    if (path === '/api/v1/cameras') return json(route, {
      max_active: 2,
      sources: options.cameraSources || [
        { source_id: 'go2_front', id: 'go2_front', label: 'GO2 FRONT', configured: true, available: true, enabled: true, live: true, state: 'ok', age_s: 0.1, fps: 15, width: 4, height: 3, topic: '/camera/image', transport: 'fake' },
        {
          source_id: 'realsense_color', id: 'realsense_color', label: 'REALSENSE COLOR',
          configured: true, available: true, enabled: true, live: true, state: 'ok',
          age_s: 0.1, fps: 15, width: 4, height: 3,
          topic: '/camera/color/image_raw', transport: 'fake', receive_fps: 14.8,
          receive_bitrate_mbps: 4.125, restart_count: 1, status_class: 'LIVE',
          cross_host_latency_state: 'UNVERIFIED_CLOCK_DOMAIN',
          relay_health: {
            state: 'streaming', fps: 15, last_frame_age_s: 0.12,
            payload_bitrate_mbps: 3.9,
            profile: { width: 640, height: 480, fps: 15, jpeg_quality: 72 },
            wifi: { state: 'LIVE', interface: 'wlan0', rssi_dbm: -54, link_mbps: 433.3 },
          },
        },
      ],
    });
    if (path === '/api/v1/competition') return json(route, state.competition);
    if (path === '/api/v1/competition/lock') {
      state.competition = { ...state.competition, locked: true, revision: state.competition.revision + 1 };
      return json(route, state.competition);
    }
    if (path === '/api/v1/competition/unlock') {
      if (body?.stationary_confirmed !== true || state.control.lease.active || state.dataset.active || state.activeMissionId) {
        return json(route, { detail: 'competition unlock blockers are active' }, 409);
      }
      state.competition = { ...state.competition, locked: false, revision: state.competition.revision + 1 };
      return json(route, state.competition);
    }
    if (path === '/api/v1/competition/mode') {
      if (state.competition.locked || !['MANUAL', 'SHADOW'].includes(body?.mode)) return json(route, { detail: 'mode is blocked' }, 409);
      state.competition = { ...state.competition, requested_mode: body.mode, operation_mode: body.mode, revision: state.competition.revision + 1 };
      return json(route, state.competition);
    }
    if (path === '/api/v1/route-planner' && method === 'GET') return json(route, state.routePlanner);
    if (path === '/api/v1/route-planner/rehearsal/scenarios' && method === 'GET') return json(route, readyRehearsal());
    if (path === '/api/v1/route-planner/orders' && method === 'POST') {
      state.routePlanner.order = {
        ...body, id: ROUTE_ORDER_ID, revision: ROUTE_ORDER_REVISION,
        total_quantity: body.lines.reduce((sum, line) => sum + line.quantity, 0),
        restaurant_count: new Set(body.lines.map((line) => line.restaurant_id)).size,
        difficulty: 'LOW',
        lines: body.lines.map((line, index) => ({ ...line, ready_at_s: body.lines.slice(0, index + 1).reduce((sum, item) => sum + item.quantity * 20, 0) })),
      };
      state.routePlanner.state = 'ORDER_READY';
      return json(route, { order: state.routePlanner.order, route_planner: state.routePlanner }, 201);
    }
    const routeOrderUpdate = path.match(/^\/api\/v1\/route-planner\/orders\/([0-9a-f]{32})$/);
    if (routeOrderUpdate && method === 'PATCH') {
      state.routePlanner.order = { ...state.routePlanner.order, ...body, id: routeOrderUpdate[1], revision: ROUTE_ORDER_REVISION };
      delete state.routePlanner.order.base_revision;
      return json(route, { order: state.routePlanner.order, route_planner: state.routePlanner });
    }
    if (path === '/api/v1/route-planner/recommendations' && method === 'POST') {
      state.routePlanner.recommendations = [
        routePlan('1', 'BALANCED', 30, 100, 3),
        routePlan('2', 'FASTEST', 28, 94, 5),
        routePlan('3', 'SAFEST', 34, 108, 1),
      ];
      state.routePlanner.selected_route_id = null;
      state.routePlanner.state = 'RECOMMENDATIONS_READY';
      return json(route, { recommendations: state.routePlanner.recommendations, route_planner: state.routePlanner });
    }
    const routeSelect = path.match(/^\/api\/v1\/route-planner\/recommendations\/([0-9a-f]{32})\/select$/);
    if (routeSelect && method === 'POST') {
      state.routePlanner.selected_route_id = routeSelect[1]; state.routePlanner.state = 'ROUTE_SELECTED';
      return json(route, { selected_route: state.routePlanner.recommendations.find((item) => item.id === routeSelect[1]), route_planner: state.routePlanner });
    }
    if (path === '/api/v1/route-planner/guidance/start' && method === 'POST') {
      state.routePlanner.guidance = {
        active: true, paused: false, instruction_type: 'CONTINUE_STRAIGHT', instruction: '직진',
        current_segment_index: 0, remaining_distance_m: 29, eta_remaining_s: 96,
        cross_track_error_m: 0.04, requirements: { TRAFFIC_GREEN: 'READY' },
        completed_pickups: [], dropoff_complete: false,
      };
      state.routePlanner.state = 'GUIDANCE_ACTIVE';
      return json(route, { guidance: state.routePlanner.guidance, route_planner: state.routePlanner });
    }
    if (path === '/api/v1/route-planner/guidance/stop' && method === 'POST') {
      state.routePlanner.guidance.active = false; state.routePlanner.state = 'ROUTE_SELECTED';
      return json(route, { guidance: state.routePlanner.guidance, route_planner: state.routePlanner });
    }
    if (path === '/api/v1/route-planner/guidance/pickup' && method === 'POST') {
      if (!state.routePlanner.guidance.completed_pickups.includes(body.venue_id)) state.routePlanner.guidance.completed_pickups.push(body.venue_id);
      return json(route, { guidance: state.routePlanner.guidance, route_planner: state.routePlanner });
    }
    if (path === '/api/v1/route-planner/guidance/dropoff' && method === 'POST') {
      state.routePlanner.guidance.dropoff_complete = true;
      return json(route, { guidance: state.routePlanner.guidance, route_planner: state.routePlanner });
    }
    const routePreview = path.match(/^\/api\/v1\/route-planner\/routes\/([0-9a-f]{32})\/preview$/);
    if (routePreview && method === 'POST') return json(route, { route_id: routePreview[1], live_nav2_preview: { status: 'BLOCKED', reason: 'SAFE_PLAN_ONLY_NAV2_INTERFACE_NOT_AVAILABLE' }, goal_submitted: false });
    if (path === '/api/v1/route-planner/rehearsal/start' && method === 'POST') {
      state.routePlanner.rehearsal = activeRehearsal(body.scenario_id);
      return json(route, { rehearsal: state.routePlanner.rehearsal });
    }
    if (path === '/api/v1/route-planner/rehearsal/control' && method === 'POST') {
      const rehearsal = state.routePlanner.rehearsal;
      if (body.action === 'EXIT') state.routePlanner.rehearsal = readyRehearsal();
      else if (body.action === 'RESET') state.routePlanner.rehearsal = activeRehearsal(rehearsal.scenario.scenario_id);
      else if (body.action === 'STEP') {
        rehearsal.playback.event_index = Math.min(rehearsal.playback.event_count, rehearsal.playback.event_index + 1);
        rehearsal.playback.position_ms = rehearsal.playback.event_index ? 100 : 0;
        rehearsal.events[0].status = 'APPLIED';
        if (rehearsal.scenario.scenario_id === 'traffic-red-to-green') rehearsal.advisory_behavior = { behavior: 'CROSSWALK', state: 'READY', advisory: 'PROCEED_RECOMMENDED', reason_codes: [] };
      } else if (body.action === 'PLAY' || body.action === 'PAUSE') rehearsal.playback.state = body.action === 'PLAY' ? 'PLAYING' : 'PAUSED';
      else if (body.action === 'SET_SPEED') rehearsal.playback.speed = body.speed;
      else if (body.action === 'SCRUB') { rehearsal.playback.position_ms = body.position_ms; rehearsal.playback.event_index = body.position_ms > 0 ? 1 : 0; }
      else if (body.action === 'OFF_ROUTE') { rehearsal.virtual_robot.off_route = body.enabled; rehearsal.advisory_behavior = body.enabled ? { behavior: 'NORMAL_GUIDANCE', state: 'HOLD', advisory: 'REPLAN_RECOMMENDED', reason_codes: ['ROUTE_DEVIATION'] } : rehearsal.advisory_behavior; }
      else if (body.action === 'CONFIRM_PICKUP') {
        const item = rehearsal.delivery.items.find((entry) => entry.venue_id === body.venue_id);
        if (item && item.pickup_state !== 'CONFIRMED') { item.pickup_state = 'CONFIRMED'; rehearsal.delivery.cargo_count += item.quantity; }
        rehearsal.delivery.next_venue_id = rehearsal.delivery.items.find((entry) => entry.pickup_state !== 'CONFIRMED')?.venue_id || null;
        rehearsal.delivery.state = rehearsal.delivery.next_venue_id ? 'EN_ROUTE_PICKUP' : 'EN_ROUTE_DESTINATION';
      } else if (body.action === 'CONFIRM_DROPOFF') {
        rehearsal.delivery.cargo_count = 0; rehearsal.delivery.destination_state = 'COMPLETE'; rehearsal.delivery.state = 'ORDER_COMPLETE';
      }
      return json(route, { rehearsal: state.routePlanner.rehearsal });
    }
    if (path === '/api/v1/route-planner/rehearsal/report' && method === 'GET') return json(route, { json: { kind: 'ROUTE_PLANNER_REHEARSAL_REPORT', side_effect_count: 0, side_effect_counters: rehearsalSideEffects() }, markdown: '# Route Planner Rehearsal Report\n\n- Side effects: 0\n- ROBOT WILL NOT MOVE' });
    const routeDryRun = path.match(/^\/api\/v1\/route-planner\/routes\/([0-9a-f]{32})\/mission-dry-run$/);
    if (routeDryRun && method === 'POST') return json(route, { kind: 'MISSION_DRAFT_DRY_RUN', route_id: routeDryRun[1], eligibility: true, rejection_reason: null, waypoint_count: 3, mission_created: false, mission_started: false, navigation_goal_submitted: false, side_effect_count: 0, side_effect_counters: rehearsalSideEffects() });
    const routeExport = path.match(/^\/api\/v1\/route-planner\/routes\/([0-9a-f]{32})\/export-mission$/);
    if (routeExport && method === 'POST') {
      state.routePlanner.state = 'MISSION_EXPORTED';
      return json(route, { mission: { id: '5'.repeat(32), state: 'ready' }, created: true, mission_started: false, navigation_goal_submitted: false }, 201);
    }
    if (path === '/api/v1/models/active') return json(route, {
      active: {
        lane: { model_id: 'lane-v2', package_sha256: 'a'.repeat(64), engine_sha256: 'b'.repeat(64) },
        object: { model_id: 'yolo-v3', package_sha256: 'c'.repeat(64), engine_sha256: 'd'.repeat(64) },
      },
      previous: { lane: 'lane-v1', object: 'yolo-v2' }, activation_surface: 'LOCAL_OPERATOR_ONLY',
    });
    if (path === '/api/v1/perception/latest') {
      if (!state.perceptionOnline) return json(route, { detail: 'perception offline' }, 503);
      return json(route, { mode: 'SHADOW', transport_state: 'LIVE', results: [
        { task: 'lane', result_status: 'LIVE', model_id: 'lane-v2', model_sha256: 'a'.repeat(64), sequence: 12, source_sequence: 1202, source_epoch: 81, input_age_s: 0.2, last_receive_age: 0.1, inference_fps: 12, inference_p95_ms: 9, confidence: 0.91, clock_domain_verified: false },
        { task: 'object', result_status: 'LIVE', model_id: 'yolo-v3', model_sha256: 'c'.repeat(64), sequence: 13, source_sequence: 1203, source_epoch: 81, input_age_s: 0.2, last_receive_age: 0.1, inference_fps: 10, inference_p95_ms: 18, confidence: 0.84, clock_domain_verified: false },
        { task: 'depth_summary', result_status: 'LIVE', model_id: 'depth-v1', model_sha256: 'e'.repeat(64), sequence: 14, source_sequence: 1204, source_epoch: 81, input_age_s: 0.2, last_receive_age: 0.1, inference_fps: 8, inference_p95_ms: 22, confidence: 0.75, clock_domain_verified: false },
      ] });
    }
    if (path === '/api/v1/pointcloud/settings') {
      if (method === 'POST' && Number.isInteger(body?.max_points)) state.pointMax = body.max_points;
      return json(route, { max_points: state.pointMax, all_points: false, min_points: 1_000, max_custom_points: 1_000_000 });
    }
    if (path === '/api/v1/pointcloud.bin' || path === '/api/v1/pointcloud' || path === '/api/v1/map') return route.fulfill({ status: 204, body: '' });
    if (path === '/api/v1/saved-maps') return json(route, { maps: [{
      id: MAP_ID, revision: state.mapRevision, name: 'e2e_static_map', kind: 'occupancy2d',
      format: 'map-server-pgm', file_name: 'e2e_static_map.yaml', frame_id: 'map',
      width: 4, height: 4, resolution: 0.25, origin: [0, 0, 0], manageable: true, editable: true,
      data_url: `/api/v1/saved-maps/${MAP_ID}/data`,
      annotations_url: `/api/v1/saved-maps/${MAP_ID}/annotations`,
    }] });
    if (path === `/api/v1/saved-maps/${MAP_ID}/data`) return json(route, {
      id: MAP_ID, revision: state.mapRevision, name: 'e2e_static_map', frame_id: 'map',
      width: 4, height: 4, resolution: 0.25, origin: [0, 0, 0], data_b64: 'AAAAAAAAAAAAAAAAAAAAAA==',
    });
    if (path === `/api/v1/saved-maps/${MAP_ID}/annotations`) {
      if (method === 'PATCH') {
        state.annotations = {
          schema_version: 1,
          map_id: MAP_ID,
          map_revision: state.mapRevision,
          annotation_revision: 'e'.repeat(64),
          revision: 'e'.repeat(64),
          exists: true,
          points: (body?.points || []).map((point, index) => ({ ...point, id: point.id || String(index + 1).padStart(24, '0') })),
          polygons: (body?.polygons || []).map((polygon, index) => ({ ...polygon, id: polygon.id || String(index + 65).padStart(24, '0') })),
        };
      }
      return json(route, state.annotations);
    }
    if (path === '/api/v1/mapping/control') return json(route, state.mapping);
    if (path === '/api/v1/mapping/start') {
      state.mapping = { ...baseMapping(), pipeline: { state: 'running', job_id: 'c'.repeat(32), error: '' } };
      return json(route, state.mapping, 202);
    }
    if (path === '/api/v1/mapping/save') {
      state.mapping.operation = { state: 'saving', kind: body?.create_2d ? 'pointcloud3d_2d' : 'pointcloud3d', job_id: 'd'.repeat(32), map_name: body?.name || 'map', error: '', files: [] };
      return json(route, { accepted: true, map_name: body?.name, kind: state.mapping.operation.kind }, 202);
    }
    if (path === '/api/v1/mapping/stop') {
      state.mapping = baseMapping();
      return json(route, state.mapping);
    }
    if (path === '/api/v1/navigation/parameters') return json(route, {
      revision: PARAMETER_REVISION, active_preset: 'e2e', values: tunedNavigationValues,
      presets: [{ id: 'e2e', label: 'E2E', description: 'fake', values: tunedNavigationValues }], requires_restart: true,
    });
    if (path === '/api/v1/navigation/logs') return json(route, { stream_id: 'e'.repeat(32), job: null, entries: [], cursor: 0, latest_cursor: 0, truncated: false, has_more: false, limits: { max_entries: 100, max_message_chars: 320 } });
    if (path === '/api/v1/missions' && method === 'GET') return json(route, { available: true, active_mission_id: state.activeMissionId, missions: state.missions, limits: { max_missions: 32, max_waypoints: 32, max_log_entries: 200 } });
    if (path === '/api/v1/missions' && method === 'POST') {
      const mission = { id: MISSION_ID, label: body?.label || 'Route', state: 'ready', outcome: null, error: null, map_id: body?.map_id, map_revision: body?.map_revision, annotation_revision: body?.annotation_revision, current_index: 0, completed_count: 0, remaining_count: body?.waypoints?.length || 0, elapsed_seconds: 0, hold_remaining: 0, ownership_active: false, waypoints: (body?.waypoints || []).map((item) => ({ ...item, status: 'pending', goal_id: null, attempts: 0 })), logs: [{ seq: 1, timestamp: '2026-08-28T00:00:00.000Z', event: 'mission_created', waypoint_index: null }] };
      state.missions = [mission]; return json(route, { mission }, 201);
    }
    const missionAction = path.match(/^\/api\/v1\/missions\/([0-9a-f]{32})\/(start|pause|resume|skip|retry|abort)$/);
    if (missionAction) {
      const mission = state.missions.find((item) => item.id === missionAction[1]); const action = missionAction[2];
      if (!mission) return json(route, { detail: 'mission was not found' }, 404);
      if (action === 'start' || action === 'resume' || action === 'retry') { mission.state = 'running'; mission.outcome = null; mission.error = null; mission.ownership_active = true; state.activeMissionId = mission.id; const waypoint = mission.waypoints[mission.current_index]; waypoint.status = 'running'; waypoint.attempts += 1; waypoint.goal_id = '7'.repeat(32); state.navigation.goal = { state: 'active', goal_id: waypoint.goal_id }; }
      if (action === 'pause') { mission.state = 'paused'; mission.ownership_active = true; state.navigation.goal = { state: 'canceled', goal_id: null }; }
      if (action === 'skip') {
        mission.waypoints[mission.current_index].status = 'skipped';
        mission.current_index += 1;
        mission.remaining_count = Math.max(0, mission.remaining_count - 1);
        if (mission.current_index >= mission.waypoints.length) {
          mission.state = 'completed'; mission.ownership_active = false; state.activeMissionId = null;
        } else {
          const waypoint = mission.waypoints[mission.current_index];
          waypoint.status = 'running'; waypoint.attempts += 1; waypoint.goal_id = '8'.repeat(32);
          state.navigation.goal = { state: 'active', goal_id: waypoint.goal_id };
        }
      }
      if (action === 'abort') { mission.state = 'failed'; mission.outcome = 'aborted'; mission.ownership_active = false; state.activeMissionId = null; state.navigation.goal = { state: 'canceled', goal_id: null }; }
      mission.logs.push({ seq: mission.logs.length + 1, timestamp: '2026-08-28T00:00:00.000Z', event: `mission_${action}`, waypoint_index: mission.current_index });
      return json(route, { mission }, action === 'start' ? 202 : 200);
    }
    const missionDetail = path.match(/^\/api\/v1\/missions\/([0-9a-f]{32})$/);
    if (missionDetail) { const mission = state.missions.find((item) => item.id === missionDetail[1]); return mission ? json(route, { available: true, mission }) : json(route, { detail: 'mission was not found' }, 404); }
    if (path === '/api/v1/navigation') return json(route, state.navigation);
    if (path === '/api/v1/navigation/start') {
      state.control.lease = { active: true, bound: true, source: 'navigation' };
      state.navigation = {
        ...baseNavigation(), pipeline: { state: 'running', job_id: 'f'.repeat(32), error: '' },
        localization_pipeline: { state: 'running', phase: 'running', pending: false, owned_by_navigation: true, job_id: 'c'.repeat(32), error: '' },
        map: { id: MAP_ID, revision: state.mapRevision }, localization: { state: 'localized', pose: { x: 0.5, y: 0.5, yaw: 0 } },
        goal: { state: 'active', goal_id: '1'.repeat(32), distance_remaining: 1, initial_distance: 2, message: '' },
        readiness: { map_server: true, planner: true, controller: true, behavior: true, cmd_bridge: true, map: true, scan: true, odometry: true, tf: true, localization: true },
        runtime_health: { localized: true },
        safety: { can_start: false, can_stop: true, can_set_initial_pose: true, can_send_goal: false, blockers: [] },
        bindings: { scan: '/scan', odometry: '/utlidar/robot_odom' },
      };
      return json(route, state.navigation, 202);
    }
    if (path === '/api/v1/navigation/cancel') {
      state.navigation.goal = { state: 'cancelled', goal_id: null, message: 'cancelled' };
      return json(route, state.navigation);
    }
    if (path === '/api/v1/navigation/goal/annotation') {
      state.navigation.goal = {
        state: 'active', goal_id: '2'.repeat(32), message: 'annotation goal',
        pose: { x: 0.5, y: 0.5, yaw: 0 },
      };
      return json(route, {
        accepted: true,
        annotation: { id: body?.annotation_id, type: 'HOME', name: 'E2E Home' },
        navigation: state.navigation,
      });
    }
    if (path === '/api/v1/navigation/stop') {
      state.navigation = baseNavigation();
      state.control.lease = { active: false, bound: false, source: null };
      return json(route, state.navigation);
    }
    if (path === '/api/v1/control') return json(route, state.control);
    if (path === '/api/v1/control/stop') {
      state.control.estop_latched = true;
      return json(route, state.control);
    }
    if (path === '/api/v1/control/estop/clear') {
      state.control.estop_latched = false;
      return json(route, state.control);
    }
    if (path === '/api/v1/control/bridge-service') return json(route, {
      service: 'robot-scope-control-bridge.service', enabled: true, configured: true,
      systemd: { available: true, active_state: 'active', sub_state: 'running', load_state: 'loaded', unit_file_state: 'disabled', running: true, transitioning: false },
      blockers: { start: ['control_bridge_service_already_active'], stop: [] }, can_start: false, can_stop: true,
      operation: null, privilege: { runner_available: true, last_result: '' },
    });
    if (path === '/api/v1/system/service') {
      const blockers = state.serviceBlocked ? ['mapping_pipeline_active'] : [];
      return json(route, {
        service: 'robot-scope.service', instance_id: 'instance-e2e', enabled: true,
        systemd: { available: true, active_state: 'active', sub_state: 'running' }, privilege: { runner_available: true },
        blockers, can_restart: blockers.length === 0, can_stop: blockers.length === 0, operation: null,
      });
    }
    if (path === '/api/v1/system/diagnostics/export') return route.fulfill({
      status: 200,
      contentType: 'application/zip',
      headers: { 'Content-Disposition': 'attachment; filename="robot-scope-diagnostics-20260823T054500Z.zip"' },
      body: Buffer.from('PK\u0003\u0004e2e-diagnostics'),
    });
    if (path === '/api/v1/datasets/capture') return json(route, state.dataset);
    if (path === '/api/v1/datasets/capture/start') {
      state.dataset = { ...baseDataset(), state: 'capturing', active: true, session_id: 'session_e2e', sources: body?.sources === 'both' ? ['go2_front', 'realsense_color'] : [body?.sources || 'go2_front'], capture_hz: body?.capture_hz || 1, label: body?.label || '', output_path: '/srv/robot-scope/datasets/session_e2e' };
      return json(route, state.dataset, 202);
    }
    if (path === '/api/v1/datasets/capture/stop') {
      state.dataset = { ...state.dataset, state: 'complete', active: false };
      return json(route, state.dataset);
    }
    if (path === '/api/v1/models') return json(route, {
      schema_version: 'robot-scope.model-registry/v1', activation_surface: 'LOCAL_OPERATOR_ONLY',
      active: { object: 'object-e2e-v2' }, previous: { object: 'object-e2e-v1' },
      models: [
        { model_id: 'object-e2e-v2', task: 'object', state: 'active', package_sha256: 'a'.repeat(64), engine: { sha256: 'b'.repeat(64) }, reason: '' },
        { model_id: 'object-e2e-v1', task: 'object', state: 'previous', package_sha256: 'c'.repeat(64), engine: { sha256: 'd'.repeat(64) }, reason: '' },
      ],
    });
    if (path === '/api/v1/datasets') return json(route, { sessions: state.dataset.session_id ? [{ session_id: state.dataset.session_id, label: state.dataset.label || 'session_e2e', state: state.dataset.state, sources: state.dataset.sources, sample_count: state.dataset.saved, bytes_written: state.dataset.bytes_written, output_path: state.dataset.output_path }] : [] });
    if (path === '/api/v1/datasets/session_e2e/export') return json(route, {
      schema_version: 'robot-scope.dataset-export-artifact/v1', export_id: '1'.repeat(32),
      session_id: 'session_e2e', filename: 'robot-scope-dataset-session_e2e.zip',
      bytes: 1024, file_count: 2, sha256: 'e'.repeat(64), finalized: true,
    }, 201);
    if (path === `/api/v1/datasets/exports/${'1'.repeat(32)}`) return route.fulfill({
      status: 200, contentType: 'application/zip',
      headers: { 'Content-Disposition': 'attachment; filename="robot-scope-dataset-session_e2e.zip"' },
      body: Buffer.from('PK\u0003\u0004e2e-dataset'),
    });
    if (path.startsWith('/api/v1/datasets/')) return json(route, { session_id: 'session_e2e', label: 'session_e2e', state: state.dataset.state, sources: state.dataset.sources, sample_count: 0, bytes_written: 0, output_path: state.dataset.output_path, samples: [], page: { limit: 24, before: null, oldest_index: null, newest_index: null, next_before: null, has_older: false } });
    return json(route, { detail: `unhandled fake endpoint ${method} ${path}` }, 404);
  });

  return backend;
}
