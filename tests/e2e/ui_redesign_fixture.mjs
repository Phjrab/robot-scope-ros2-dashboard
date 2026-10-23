import { installDashboardBackend } from './dashboard_backend.mjs';

export function syntheticCloudFrame(seq) {
  const points = [];
  for (let x = -5; x <= 5; x += 0.25) for (let y = -4; y <= 4; y += 0.25) {
    points.push(x, y, 0);
    if (Math.abs(x) > 4.8 || Math.abs(y) > 3.8) for (let z = 0.25; z <= 2; z += 0.25) points.push(x, y, z);
  }
  const metadata = Buffer.from(JSON.stringify({ seq, stream_id: 'synthetic-mission-control-v1',
    encoding: 'float32le', point_count: points.length / 3, source_points: points.length / 3,
    frame_id: 'camera_init', topic: '/cloud_registered', age_s: 0, data_provenance: 'SYNTHETIC_FIXTURE' }));
  const offset = (16 + metadata.length + 3) & ~3;
  const frame = Buffer.alloc(offset + points.length * 4);
  frame.write('RSPC'); frame.writeUInt8(1, 4); frame.writeUInt16LE(metadata.length, 6);
  frame.writeUInt32LE(points.length / 3, 8); frame.writeUInt32LE(points.length * 4, 12);
  metadata.copy(frame, 16);
  points.forEach((value, index) => frame.writeFloatLE(value, offset + index * 4));
  return frame;
}

export async function installMissionFixture(page, options = {}) {
  const unexpected = [];
  const consoleErrors = [];
  const pageErrors = [];
  const httpErrors = [];
  page.on('response', (response) => { if (response.status() >= 400) httpErrors.push({ url: new URL(response.url()).pathname, status: response.status() }); });
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('pageerror', (error) => pageErrors.push(error.message));
  await page.route('**/*', (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== '127.0.0.1') { unexpected.push(url.origin); return route.abort('blockedbyclient'); }
    return route.fallback();
  });
  await page.routeWebSocket('**/*', (socket) => {
    unexpected.push(new URL(socket.url()).origin); socket.close();
  });
  let backend;
  backend = await installDashboardBackend(page, { ...options, syntheticFixture: true,
    pointcloudFrame: (seq) => backend?.state.online && backend.state.uiCloudStreaming !== false ? syntheticCloudFrame(seq) : null });
  backend.state.uiCloudStreaming = true;
  // Current pages also read SLAM catalogue and offline calibration status.
  // Keep these explicit and read-only so captures show the UI, not fake 404s.
  const readOnly = {
    '/api/v1/slam/engines': { engines: [
      { engine_id: 'lidar_fastlio', available_now: false, tasks: ['mapping'], blocked_reason: 'SYNTHETIC_NO_HARDWARE' },
      { engine_id: 'visual_stereo', available_now: false, tasks: ['mapping'], blocked_reason: 'SYNTHETIC_NO_HARDWARE' },
    ] },
    '/api/v1/slam/session': { active_session: null, generation: 0, jobs: [] },
    '/api/v1/slam/packages': { packages: [] },
    '/api/v1/slam/depth/samples': { samples: [] },
    '/api/v1/settings/mount-calibration/status': {
      status: 'ok', schema_version: '1.0.0', mode: 'offline', input_source: 'imported_depth_json',
      input_sources: ['imported_depth_json', 'saved_depth_samples'],
      saved_samples_endpoint: '/api/v1/slam/depth/samples', saved_sample_access: 'read_only',
      live_capture_available: false, hardware_access: false, persistence: false,
      body_extrinsic_validated: false, absolute_pitch_validated: false,
      max_request_bytes: 64 * 1024 * 1024, provenance: 'SYNTHETIC_BROWSER_FIXTURE',
    },
  };
  for (const [path, value] of Object.entries(readOnly)) backend.on(path, ({ method, json }) => {
    if (method !== 'GET') throw new Error(`Unexpected fixture mutation: ${method} ${path}`);
    return json(value);
  });
  const width = 72; const height = 64;
  const cells = Buffer.alloc(width * height);
  for (let y = 0; y < height; y += 1) for (let x = 0; x < width; x += 1) {
    cells[y * width + x] = x < 3 || y < 3 || x > width - 4 || y > height - 4 ? 255
      : x === 4 || y === 4 || x === width - 5 || y === height - 5 || (x > 20 && x < 24 && y > 10 && y < 40)
        || (x > 45 && x < 60 && y > 40 && y < 44) ? 100 : 0;
  }
  const map = { id: backend.mapId, revision: backend.mapRevision, name: 'synthetic_static_lab', kind: 'occupancy2d',
    format: 'map-server-pgm', file_name: 'synthetic_static_lab.yaml', frame_id: 'map', width, height,
    resolution: .1, origin: [-3.6, -3.2, 0], size_bytes: cells.length, manageable: true, editable: true,
    data_url: `/api/v1/saved-maps/${backend.mapId}/data` };
  backend.on('/api/v1/saved-maps', ({ json }) => json({ total_size_bytes: cells.length, maps: [map] }));
  backend.on(map.data_url, ({ json }) => json({ ...map, data_b64: cells.toString('base64') }));
  return { backend, unexpected, consoleErrors, pageErrors, httpErrors, map };
}
