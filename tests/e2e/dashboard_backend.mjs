import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const navigationContract = require('../../robot_dashboard/static/navigation.js');
const MAP_ID = '0123456789abcdef01234567';
const MAP_REVISION = 'a'.repeat(64);
const PARAMETER_REVISION = 'b'.repeat(64);
const ANNOTATION_REVISION = 'c'.repeat(64);
const ANNOTATION_ID = 'd'.repeat(24);

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
  const state = {
    online: options.online !== false,
    pointMax: 10_000,
    mapping: baseMapping(), navigation: baseNavigation(), control: baseControl(), dataset: baseDataset(),
    mapRevision: MAP_REVISION, serviceBlocked: Boolean(options.serviceBlocked),
    annotations: {
      schema_version: 1, map_id: MAP_ID, map_revision: MAP_REVISION,
      annotation_revision: ANNOTATION_REVISION, revision: ANNOTATION_REVISION, exists: true,
      points: [{ id: ANNOTATION_ID, type: 'HOME', name: 'E2E Home', pose: { x: 0.5, y: 0.5, yaw: 0 } }],
      polygons: [],
    },
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
    on(path, handler) { handlers.set(path, handler); },
    mutations(path) { return state.requests.filter((entry) => entry.path === path); },
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
        socket.send(JSON.stringify({
          source_id: cameraSourceId, topic: cameraSourceId === 'go2_front' ? '/camera/image' : '/camera/color/image_raw',
          format: 'raw', encoding: 'rgb8', width: 4, height: 3, step: 12, fps: 15, transport: 'fake', state: 'ok', seq,
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
        { source_id: 'realsense_color', id: 'realsense_color', label: 'REALSENSE COLOR', configured: true, available: true, enabled: true, live: true, state: 'ok', age_s: 0.1, fps: 15, width: 4, height: 3, topic: '/camera/color/image_raw', transport: 'fake' },
      ],
    });
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
    if (path === '/api/v1/datasets') return json(route, { sessions: state.dataset.session_id ? [{ session_id: state.dataset.session_id, label: state.dataset.label || 'session_e2e', state: state.dataset.state, sources: state.dataset.sources, sample_count: state.dataset.saved, bytes_written: state.dataset.bytes_written, output_path: state.dataset.output_path }] : [] });
    if (path.startsWith('/api/v1/datasets/')) return json(route, { session_id: 'session_e2e', label: 'session_e2e', state: state.dataset.state, sources: state.dataset.sources, sample_count: 0, bytes_written: 0, output_path: state.dataset.output_path, samples: [], page: { limit: 24, before: null, oldest_index: null, newest_index: null, next_before: null, has_older: false } });
    return json(route, { detail: `unhandled fake endpoint ${method} ${path}` }, 404);
  });

  return backend;
}
