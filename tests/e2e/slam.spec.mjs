import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

const PACKAGE_ID = 'np_' + 'a'.repeat(32);
const REVISION = 'b'.repeat(64);
const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRz8AAAAASUVORK5CYII=';
const nativePackage = () => ({ id: PACKAGE_ID, package_id: PACKAGE_ID,
  name: 'SYNTHETIC_FIXTURE <img onerror=alert(1)>', engine_id: 'visual_stereo', map_kind: 'vslam_native',
  revision: REVISION, native_content_revision: 'c'.repeat(64), preview_revision: 'd'.repeat(64),
  preview_consistency: 'approximate', map_frame: 'map', calibration_hash: 'e'.repeat(64),
  native_artifacts: [{ path: 'data.mdb', size_bytes: 28, sha256: 'f'.repeat(64) }],
  save_completion: { status: 'completed' }, validation: { native_load: 'unknown', localization_success: 'unknown' },
  compatibility: { status: 'blocked' }, data_provenance: 'SYNTHETIC_FIXTURE' });

function fixtureFrame(session, sequence = '1') {
  return { schema_version: 1, ...session, sequence, frame_id: 'map', clock_domain: 'ros',
    source_timestamp_ns: '9007199254740993001', stream_connected: true,
    heartbeat_receive_age_seconds: 0.05, tracking_state: 'MAPPING',
    image: { png_base64: PNG, stamp_ns: '9007199254740993001', width: 1, height: 1,
      frame_id: 'left_optical', camera_id: 'left', rectified: true },
    overlay: { overlay_kind: 'current_observations_reprojected', reason: null, points: [[0, 0]], displayed_count: 1,
      receive_age_seconds: 0.05, provenance: 'SYNTHETIC_FIXTURE',
      image: { source_timestamp_ns: '9007199254740993001', width: 1, height: 1, frame_id: 'left_optical', camera_id: 'left', calibration_revision: 'fixture-cal' } },
    camera_view: { available: true, session_id: session.session_id, generation: session.generation,
      engine_id: session.engine_id, map_epoch: session.map_epoch, coordinate_frame: 'map', camera_frame_id: 'left_optical',
      position: [1, 0, 0], quaternion_xyzw: [0, 0, 0, 1], intrinsics: [1, 1, 0.5, 0.5], width: 1, height: 1,
      source_timestamp_ns: '9007199254740993001', image_source_timestamp_ns: '9007199254740993001',
      pose_source_timestamp_ns: '9007199254740993001', calibration_source_timestamp_ns: '9007199254740993001',
      calibration_revision: 'fixture-cal', projection_convention: 'rectified_optical_x_right_y_down_z_forward',
      provenance: 'SYNTHETIC_FIXTURE_timestamped_slam_map_rectified_optical_pose' },
    global_map: { spatial_scope: 'global_map', coverage: 'subset', points: [[-100, 0, 0], [100, 0, 0], [0, 1, 1]],
      displayed_count: 3, exported_count: 3, engine_total_count: null, backend_limit: 32768, decimation: false,
      coordinate_frame: 'map', map_epoch: session.map_epoch, snapshot_id: '1', engine_revision: null,
      source_timestamp_ns: '9007199254740993001', provenance: 'SYNTHETIC_FIXTURE' },
    current_observations: { available: true, points: [[0, 0, 1]], coordinate_frame: 'map', map_epoch: session.map_epoch },
    trajectory: { points: [[0, 0, 0], [1, 0, 0]], trajectory_kind: 'slam', coordinate_frame: 'map', map_epoch: session.map_epoch },
    camera_pose: { position: [1, 0, 0], quaternion_xyzw: [0, 0, 0, 1], frame_id: 'map', stamp_ns: '9007199254740993001' },
    readiness: { ready: true, tracking_state: 'TRACKING', pose_reference: 'camera_link',
      operational_pose_approved: false, pose_source: '/fixture/corrected_pose',
      freshness: { image: true, pose: true, tracking: true } } };
}

async function install(page, { available = true, state = null } = {}) {
  await installDashboardBackend(page);
  const shared = state || { session: null, packages: [nativePackage()], mutations: [], sockets: new Set(), socketPaths: [], sequence: 0 };
  shared.jobs ||= [];
  shared.saveRequests ||= new Map();
  shared.nativeSaves ||= 0;
  const send = () => {
    if (!shared.session || shared.session.state === 'IDLE') return;
    for (const ws of shared.sockets) {
      const frame = fixtureFrame(shared.session, String(++shared.sequence));
      ws.send(JSON.stringify(shared.frameTransform ? shared.frameTransform(frame) : frame));
    }
  };
  await page.routeWebSocket('**/api/v1/ws/slam', (ws) => {
    expect(new URL(ws.url()).pathname).toBe('/api/v1/ws/slam');
    shared.socketPaths.push(new URL(ws.url()).pathname);
    shared.sockets.add(ws);
    ws.onClose(() => shared.sockets.delete(ws));
    send();
  });
  await page.route('**/api/v1/slam/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.slice('/api/v1/slam'.length);
    const method = request.method();
    const body = request.postDataJSON?.bind(request);
    const reply = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    if (method !== 'GET') shared.mutations.push({ path, method, body: path.endsWith('/import') ? 'raw ZIP' : body() });
    if (path === '/engines') return reply({ engines: [
      { engine_id: 'lidar_fastlio', available_now: true, installed: true, tasks: ['mapping'], hardware_verified: false },
      { engine_id: 'visual_stereo', available_now: available, installed: available, tasks: ['mapping'],
        blocked_reason: available ? null : 'CAMERA_HANDOFF_REQUIRED', software_verified: true, hardware_verified: false },
      { engine_id: 'visual_inertial', available_now: false, tasks: [], blocked_reason: 'IMU_NOT_QUALIFIED' },
    ] });
    if (path === '/session') {
      const value = { active_session: shared.session, generation: shared.session?.generation || 0,
        jobs: shared.jobs, operational_pose_source: { source: '/Odometry', generation: 7 } };
      if (shared.holdNextSessionResponse) {
        shared.holdNextSessionResponse = false;
        shared.releaseSessionResponse = () => reply(value);
        return;
      }
      return reply(value);
    }
    if (path === '/sessions' && method === 'POST') {
      if (shared.startConflict) return reply({ detail: { code: 'RESOURCE_CONFLICT', resources: shared.startConflict } }, 409);
      if (shared.session && shared.session.state !== 'IDLE') return reply({ detail: 'SLAM_SESSION_ACTIVE' }, 409);
      shared.session = { session_id: 'fixture-session', generation: 1, map_epoch: 'fixture-epoch',
        engine_id: body().engine_id, task: body().task, effective_mode: 'isaac_slam', state: 'MAPPING', unsaved: true };
      setTimeout(send, 100);
      return reply({ session_id: shared.session.session_id, generation: 1 });
    }
    if (path.endsWith('/save')) {
      if (shared.saveError) return reply({ detail: shared.saveError }, 409);
      const requestBody = body();
      let job = shared.saveRequests.get(requestBody.request_id);
      if (!job) {
        shared.nativeSaves += 1;
        job = { job_id: `fixture-job-${shared.nativeSaves}`, state: 'SAVING', package_id: null,
          session_id: shared.session.session_id, generation: shared.session.generation };
        shared.saveRequests.set(requestBody.request_id, structuredClone(job));
        shared.jobs.push(job);
        shared.session.state = 'SAVING';
        // The snapshot is immutable while mapping may collect an unsaved tail.
        shared.session.unsaved = true;
      }
      if (shared.holdSaveResponse) { shared.releaseSaveResponse = () => reply(job); return; }
      if (shared.hangSaveResponse) return;
      if (shared.loseSaveResponses > 0) { shared.loseSaveResponses -= 1; return route.abort('failed'); }
      return reply(job);
    }
    if (path.endsWith('/stop')) {
      if (shared.session.state === 'SAVING') return reply({ detail: 'SAVE_IN_PROGRESS' }, 409);
      if (shared.session.unsaved && body().discard_unsaved !== true) return reply({ detail: 'UNSAVED_MAP' }, 409);
      shared.session.state = 'IDLE'; return reply({ active_session: shared.session });
    }
    if (path.startsWith('/jobs/')) {
      const job = shared.jobs.find((value) => value.job_id === path.slice('/jobs/'.length));
      if (!job) return reply({ detail: 'JOB_NOT_FOUND' }, 404);
      if (shared.holdJobResponse) { shared.releaseJobResponse = () => reply({ ...job, state: 'SUCCEEDED', package_id: PACKAGE_ID }); return; }
      if (shared.session.session_id === job.session_id && shared.session.generation === job.generation) {
        shared.session.state = 'MAPPING'; shared.session.unsaved = true;
      }
      Object.assign(job, shared.failSave ? { state: 'FAILED', reason: 'NATIVE_SAVE_FAILED' } : { state: 'SUCCEEDED', package_id: PACKAGE_ID });
      return reply(job);
    }
    if (path === '/packages') return reply({ packages: shared.packages });
    if (path.endsWith('/preview')) return reply(fixtureFrame({ session_id: 'saved', generation: 1, engine_id: 'visual_stereo', map_epoch: 'saved-epoch' }));
    if (path.endsWith('/rename')) return reply({ detail: 'REVISION_CONFLICT' }, 409);
    if (path.endsWith('/import')) return reply({ detail: 'UNSAFE_ARCHIVE' }, 422);
    if (path.endsWith('/localize')) {
      if (shared.session.unsaved && body().discard_unsaved !== true) return reply({ detail: 'UNSAVED_MAP_CONFIRMATION_REQUIRED' }, 409);
      shared.session.state = 'LOCALIZING';
      setTimeout(() => {
        shared.session.state = 'MAPPING';
        // Readiness may clear session.reason; the durable result must still
        // show official completion without claiming confirmed localization.
        shared.session.reason = null;
        shared.session.localization_result = { official_localization_completed: true, native_load: 'verified',
          localize_success: false, fresh_pose_tracking_confirmed: false,
          reason: 'POST_LOCALIZATION_POSE_TIMEOUT', confirmation_reason: 'POST_LOCALIZATION_POSE_TIMEOUT',
          retry_requires_new_session: true };
      }, 100);
      return reply({ state: 'LOCALIZING', native_load: 'PENDING', localize_success: false });
    }
    return reply({ detail: 'UNSUPPORTED_FIXTURE' }, 404);
  });
  return { shared, send };
}

async function open(page, hash = 'mapping') {
  await page.goto(`/#${hash}`);
  // Idempotent when index.html already includes the integration script.
  await page.addScriptTag({ type: 'module', url: '/static/features/slam/dashboard.js' });
  await expect(page.locator('#slamConsole')).toHaveCount(1);
  if (hash === 'mapping') await expect(page.locator('#slamSessionState')).toHaveText('IDLE');
}

async function startStereo(page) {
  await page.locator('#slamEngine').selectOption('visual_stereo');
  await page.locator('#slamOperatorConfirmed').check();
  await page.locator('#slamStart').click();
  await expect(page.locator('#slamSessionState')).toHaveText('MAPPING');
}

test('SLAM unavailable camera reason stays visible and loading never starts an engine', async ({ page }) => {
  const fixture = await install(page, { available: false });
  await open(page);
  await expect(page.locator('#slamEngine')).toHaveValue('lidar_fastlio');
  await expect(page.locator('#slamEngine option[value=visual_stereo]')).toHaveJSProperty('disabled', true);
  await expect(page.locator('#slamEngine option[value=visual_stereo]')).toContainText('CAMERA_HANDOFF_REQUIRED');
  await expect(page.locator('#slamEngine option[value=visual_inertial]')).toContainText('IMU_NOT_QUALIFIED');
  await expect(page.locator('#mappingStartButton')).toBeVisible();
  await expect.poll(() => fixture.shared.socketPaths.length).toBeGreaterThan(0);
  expect([...new Set(fixture.shared.socketPaths)]).toEqual(['/api/v1/ws/slam']);
  await expect(page.locator('#cockpitSafetyHud')).toBeAttached();
  await page.reload();
  await page.addScriptTag({ type: 'module', url: '/static/features/slam/dashboard.js' });
  await expect(page.locator('#slamConsole')).toHaveCount(1);
  expect(fixture.shared.mutations).toEqual([]);
});

test('SLAM real action path renders bounded observation/global stream and requires explicit stop choice', async ({ page }) => {
  const fixture = await install(page);
  await open(page);
  await startStereo(page);
  fixture.send();
  await expect(page.locator('#slamImageStatus')).toContainText('current_observations_reprojected');
  await expect(page.locator('#slamCameraCanvas')).toHaveJSProperty('width', 1);
  await expect(page.locator('#slamMapCoverage')).toContainText('coverage subset');
  await expect(page.locator('#slamMapCoverage')).toContainText('engine total unknown');
  await expect(page.locator('#slamProvenance')).toContainText('SYNTHETIC_FIXTURE');
  await expect(page.locator('#slamSourceIdentity')).toContainText('/Odometry');
  await expect(page.locator('#slamGlobalCanvas')).toHaveAttribute('data-camera-view', 'visible');
  await expect(page.locator('#slamCameraViewStatus')).toContainText('표시선 1m');
  await page.locator('#slamCameraView').uncheck();
  await expect(page.locator('#slamGlobalCanvas')).toHaveAttribute('data-camera-view', 'hidden');
  await page.locator('#slamCameraView').check();
  await expect(page.locator('#slamGlobalCanvas')).toHaveAttribute('data-camera-view', 'visible');
  await page.locator('#slamObservationPoints').check();
  await page.locator('#slamFollow').check();
  await page.locator('#slamFit').click();
  await page.locator('#slamStop').click();
  await expect(page.locator('#slamStopDialog')).toBeVisible();
  await page.locator('#slamStopCancel').click();
  expect(fixture.shared.mutations.filter((value) => value.path.endsWith('/stop'))).toHaveLength(0);
  await page.locator('#slamMapName').fill('synthetic-room');
  await page.locator('#slamStop').click();
  await expect(page.locator('#slamStopDialog')).toContainText('snapshot 이후');
  await page.locator('#slamSaveThenStop').click();
  await expect(page.locator('#slamSessionState')).toHaveText('IDLE');
  const actions = fixture.shared.mutations.map((value) => value.path);
  expect(actions).toEqual(['/sessions', '/sessions/fixture-session/save', '/sessions/fixture-session/stop']);
  expect(fixture.shared.mutations.at(-1).body.discard_unsaved).toBe(true);
});

test('SLAM camera frustum rejects changed calibration and stale optical pose while retaining global map', async ({ page }) => {
  const fixture = await install(page);
  await open(page); await startStereo(page); fixture.send();
  await expect(page.locator('#slamGlobalCanvas')).toHaveAttribute('data-camera-view', 'visible');
  const invalid = fixtureFrame(fixture.shared.session, String(++fixture.shared.sequence));
  invalid.camera_view.calibration_revision = 'old-calibration';
  for (const socket of fixture.shared.sockets) socket.send(JSON.stringify(invalid));
  await expect(page.locator('#slamGlobalCanvas')).toHaveAttribute('data-camera-view', 'unavailable');
  await expect(page.locator('#slamFollow')).toBeDisabled();
  await expect(page.locator('#slamMapCoverage')).toContainText('global_map');
  fixture.send();
  await expect(page.locator('#slamGlobalCanvas')).toHaveAttribute('data-camera-view', 'visible');
  await expect(page.locator('#slamGlobalCanvas')).toHaveAttribute('data-camera-view', 'unavailable', { timeout: 4000 });
  await expect(page.locator('#slamCameraViewStatus')).toContainText('STALE_SOURCE');
  await expect(page.locator('#slamMapCoverage')).toContainText('coverage subset');
});

test('SLAM fresh image and camera 6DoF remain visible without overlay, global map or trajectory', async ({ page }) => {
  const fixture = await install(page);
  fixture.shared.frameTransform = (frame) => ({ ...frame, stream_connected: false,
    readiness: { ...frame.readiness, ready: false },
    overlay: { overlay_kind: 'unavailable', reason: 'OBSERVATIONS_UNAVAILABLE' },
    camera_view: { available: false, reason: 'CAMERA_ALIGNMENT_UNAVAILABLE' },
    global_map: null, trajectory: null });
  await open(page); await startStereo(page); fixture.send();

  await expect(page.locator('#slamCameraCanvas')).toBeVisible();
  await expect(page.locator('#slamCameraCanvas')).toHaveJSProperty('width', 1);
  for (const channel of ['image', 'pose', 'tracking']) {
    await expect(page.locator(`#slamAvailability-${channel}`)).toHaveAttribute('data-availability', 'available');
  }
  for (const channel of ['overlay', 'global_map', 'trajectory']) {
    await expect(page.locator(`#slamAvailability-${channel}`)).toHaveAttribute('data-availability', 'unavailable');
  }
  await expect(page.locator('#slamImageStatus')).toContainText('입력 이미지 available');
  await expect(page.locator('#slamCameraPose')).toContainText('1.000 / 0.000 / 0.000');
  await expect(page.locator('#slamCameraPose')).toContainText('카메라 6DoF');
  await expect(page.locator('#slamCameraPose')).toContainText('Go2 body pose 미검증');
  await expect(page.locator('#slamCameraPose')).toContainText('camera→Go2 extrinsic 필요');
  await expect(page.locator('#slamCameraPose')).toContainText('주행 승인 안 됨');
  await expect(page.locator('#slamCameraPose')).not.toContainText('PASS');
});

test('SLAM stale image and pose do not hide subset global map or trajectory snapshots', async ({ page }) => {
  const fixture = await install(page);
  fixture.shared.frameTransform = (frame) => ({ ...frame, tracking_state: 'LOST',
    readiness: { ...frame.readiness, ready: false, tracking_state: 'LOST',
      freshness: { image: false, pose: false, tracking: false } },
    overlay: { ...frame.overlay, overlay_kind: 'unavailable', reason: 'LOST' } });
  await open(page); await startStereo(page); fixture.send();

  for (const channel of ['image', 'pose', 'tracking', 'overlay']) {
    await expect(page.locator(`#slamAvailability-${channel}`)).toHaveAttribute('data-availability', 'unavailable');
  }
  for (const channel of ['global_map', 'trajectory']) {
    await expect(page.locator(`#slamAvailability-${channel}`)).toHaveAttribute('data-availability', 'available');
  }
  await expect(page.locator('#slamGlobalCanvas')).toBeVisible();
  await expect(page.locator('#slamMapCoverage')).toContainText('coverage subset');
  await expect(page.locator('#slamMapCoverage')).toContainText('engine total unknown');
  await expect(page.locator('#slamImageStatus')).toContainText('IMAGE_STALE');
  await expect(page.locator('#slamCameraPose')).toContainText('POSE_STALE');
  await expect(page.locator('#slamCameraPose')).not.toContainText('1.000 / 0.000 / 0.000');
});

test('SLAM resource conflict exposes concrete resources for request and asynchronous startup failure', async ({ page }) => {
  const fixture = await install(page);
  fixture.shared.startConflict = [
    { resource: 'lidar', reason: 'existing_lidar_pipeline_active' },
    { resource: 'camera', reason: 'camera_owner_active' },
  ];
  await open(page);
  await page.locator('#slamEngine').selectOption('visual_stereo');
  await page.locator('#slamOperatorConfirmed').check();
  await page.locator('#slamStart').click();
  await expect(page.locator('#slamMessage')).toContainText('RESOURCE_CONFLICT');
  await expect(page.locator('#slamMessage')).toContainText('LiDAR (existing_lidar_pipeline_active)');
  await expect(page.locator('#slamMessage')).toContainText('카메라 (camera_owner_active)');

  fixture.shared.startConflict = null;
  await page.locator('#slamStart').click();
  await expect(page.locator('#slamSessionState')).toHaveText('MAPPING');
  fixture.shared.session.state = 'ERROR';
  fixture.shared.session.reason = 'RESOURCE_CONFLICT';
  fixture.shared.session.resource_conflicts = [{ resource: 'ros_domain', reason: 'domain_owner_active' }];
  await expect(page.locator('#slamMessage')).toContainText('ROS domain (domain_owner_active)');
  // Failed owned cleanup changes the primary reason, but must preserve the
  // original resource diagnostics alongside that more urgent cleanup state.
  fixture.shared.session.reason = 'CLEANUP_REQUIRED';
  fixture.shared.session.cleanup_required = true;
  await expect(page.locator('#slamMessage')).toContainText('CLEANUP_REQUIRED');
  await expect(page.locator('#slamMessage')).toContainText('ROS domain (domain_owner_active)');
});

test('SLAM save-then-stop never discards or stops after a failed native save', async ({ page }) => {
  const fixture = await install(page);
  fixture.shared.failSave = true;
  await open(page); await startStereo(page);
  await page.locator('#slamMapName').fill('failed-save-fixture');
  await page.locator('#slamStop').click();
  await page.locator('#slamSaveThenStop').click();
  await expect(page.locator('#slamMessage')).toContainText('NATIVE_SAVE_FAILED');
  expect(fixture.shared.mutations.filter((value) => value.path.endsWith('/stop'))).toHaveLength(0);
  expect(fixture.shared.session.unsaved).toBe(true);
  expect(fixture.shared.session.state).toBe('MAPPING');
});

test('SLAM direct native Save posts the selected name and exposes pending and completion', async ({ page }) => {
  const fixture = await install(page);
  await open(page); await startStereo(page);
  fixture.shared.holdSaveResponse = true;
  await page.locator('#slamMapName').fill('direct-save-fixture');
  await page.locator('#slamSave').click();
  await expect.poll(() => Boolean(fixture.shared.releaseSaveResponse)).toBe(true);
  await expect(page.locator('#slamConsole')).toHaveAttribute('aria-busy', 'true');
  await expect(page.locator('#slamMessage')).toContainText('native 저장 요청 중');
  for (const id of ['slamSave', 'slamRefresh', 'slamMapName']) await expect(page.locator(`#${id}`)).toBeDisabled();
  const request = fixture.shared.mutations.find((value) => value.path.endsWith('/save'));
  expect(request).toMatchObject({ method: 'POST', path: '/sessions/fixture-session/save',
    body: { generation: 1, name: 'direct-save-fixture', create_2d: false } });
  expect(request.body.request_id).toMatch(/^[A-Za-z0-9_-]{8,96}$/);
  await fixture.shared.releaseSaveResponse();
  await expect(page.locator('#slamMessage')).toContainText('SUCCEEDED');
  await expect(page.locator('#slamConsole')).toHaveAttribute('aria-busy', 'false');
  expect(fixture.shared.nativeSaves).toBe(1);
  expect(fixture.shared.mutations.filter((value) => value.path.endsWith('/stop'))).toHaveLength(0);
});

test('SLAM direct native Save exposes missing names and admission failures without retrying rejected writes', async ({ page }) => {
  const fixture = await install(page);
  await open(page); await startStereo(page);
  await page.locator('#slamSave').click();
  await expect(page.locator('#slamMessage')).toContainText('저장 지도 이름을 입력하세요.');
  expect(fixture.shared.mutations.filter((value) => value.path.endsWith('/save'))).toHaveLength(0);
  fixture.shared.saveError = 'RESOURCE_CONFLICT';
  await page.locator('#slamMapName').fill('rejected-fixture');
  await page.locator('#slamSave').click();
  await expect(page.locator('#slamMessage')).toContainText('RESOURCE_CONFLICT');
  await expect(page.locator('#slamSave')).toBeEnabled();
  expect(fixture.shared.mutations.filter((value) => value.path.endsWith('/save'))).toHaveLength(1);
  expect(fixture.shared.nativeSaves).toBe(0);
});

test('SLAM background session polling leaves direct Save available and cannot replace the newer response', async ({ page }) => {
  const fixture = await install(page);
  await open(page); await startStereo(page);
  fixture.shared.holdNextSessionResponse = true;
  await expect.poll(() => Boolean(fixture.shared.releaseSessionResponse)).toBe(true);
  await expect(page.locator('#slamSave')).toBeEnabled();
  await page.locator('#slamMapName').fill('poll-overlap-fixture');
  await page.locator('#slamSave').click();
  await expect.poll(() => fixture.shared.nativeSaves).toBe(1);
  await fixture.shared.releaseSessionResponse();
  await expect(page.locator('#slamMessage')).toContainText('SUCCEEDED');
  expect(fixture.shared.mutations.filter((value) => value.path.endsWith('/save'))).toHaveLength(1);
});

test('SLAM lost Save acknowledgement recovers the exact idempotent request instead of adopting catalogue jobs', async ({ page }) => {
  const fixture = await install(page);
  await open(page); await startStereo(page);
  fixture.shared.jobs.push({ job_id: 'old-same-session-job', session_id: 'fixture-session', generation: 1,
    state: 'SUCCEEDED', package_id: 'old-package' }, { job_id: 'foreign-job', session_id: 'foreign-session', generation: 2,
    state: 'SUCCEEDED', package_id: 'foreign-package' });
  fixture.shared.loseSaveResponses = 1;
  await page.locator('#slamMapName').fill('response-lost-fixture');
  await page.locator('#slamSave').click();
  await expect(page.locator('#slamMessage')).toContainText('SUCCEEDED');
  await expect(page.locator('#slamMessage')).toContainText(PACKAGE_ID);
  const requests = fixture.shared.mutations.filter((value) => value.path.endsWith('/save'));
  expect(requests).toHaveLength(2);
  expect(requests[1].body).toEqual(requests[0].body);
  expect(fixture.shared.nativeSaves).toBe(1);
  await expect(page.locator('#slamMessage')).not.toContainText('old-package');
  await expect(page.locator('#slamMessage')).not.toContainText('foreign-package');
});

test('SLAM timed out Save remains explicit and result confirmation reuses its original request', async ({ page }) => {
  const fixture = await install(page);
  await open(page); await startStereo(page);
  await page.clock.install();
  fixture.shared.hangSaveResponse = true;
  await page.locator('#slamMapName').fill('timeout-fixture');
  await page.locator('#slamSave').click();
  await expect.poll(() => fixture.shared.mutations.filter((value) => value.path.endsWith('/save')).length).toBe(1);
  await page.clock.fastForward(15_001);
  await expect.poll(() => fixture.shared.mutations.filter((value) => value.path.endsWith('/save')).length).toBe(2);
  await page.clock.fastForward(15_001);
  await expect(page.locator('#slamMessage')).toContainText('SAVE_RESPONSE_UNCONFIRMED');
  await expect(page.locator('#slamConsole')).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('#slamSave')).toHaveText('저장 요청 결과 확인');
  await expect(page.locator('#slamSave')).toBeEnabled();
  await expect(page.locator('#slamStop')).toBeDisabled();
  await expect(page.locator('#slamMapName')).toBeDisabled();
  fixture.shared.hangSaveResponse = false;
  await page.locator('#slamSave').click();
  await page.clock.fastForward(1501);
  await expect(page.locator('#slamMessage')).toContainText('SUCCEEDED');
  const requests = fixture.shared.mutations.filter((value) => value.path.endsWith('/save'));
  expect(requests).toHaveLength(3);
  expect(requests.map((value) => value.body)).toEqual(Array(3).fill(requests[0].body));
  expect(fixture.shared.nativeSaves).toBe(1);
});

test('SLAM late Save acknowledgement cannot stop a replacement generation', async ({ page }) => {
  const fixture = await install(page);
  await open(page); await startStereo(page);
  fixture.shared.holdSaveResponse = true;
  await page.locator('#slamMapName').fill('old-generation-fixture');
  await page.locator('#slamStop').click();
  await page.locator('#slamSaveThenStop').click();
  await expect.poll(() => Boolean(fixture.shared.releaseSaveResponse)).toBe(true);
  fixture.shared.session = { ...fixture.shared.session, generation: 2, map_epoch: 'new-epoch', state: 'MAPPING' };
  await expect(page.locator('#slamSourceIdentity')).toContainText('generation 7');
  await expect(page.locator('#slamMessage')).toContainText('세션이 변경');
  await fixture.shared.releaseSaveResponse();
  await expect(page.locator('#slamConsole')).toHaveAttribute('aria-busy', 'false');
  expect(fixture.shared.mutations.filter((value) => value.path.endsWith('/stop'))).toHaveLength(0);
  expect(fixture.shared.nativeSaves).toBe(1);
  await expect(page.locator('#slamMessage')).not.toContainText('SUCCEEDED');
  expect(fixture.shared.session.generation).toBe(2);
});

test('SLAM late job completion cannot overwrite another session after an independent refresh', async ({ page }) => {
  const fixture = await install(page);
  await open(page); await startStereo(page);
  fixture.shared.holdJobResponse = true;
  await page.locator('#slamMapName').fill('old-job-fixture');
  await page.locator('#slamSave').click();
  await expect.poll(() => Boolean(fixture.shared.releaseJobResponse)).toBe(true);
  fixture.shared.session = { ...fixture.shared.session, session_id: 'replacement-session', generation: 2,
    map_epoch: 'replacement-epoch', state: 'MAPPING' };
  await page.locator('#slamRefresh').click();
  await expect(page.locator('#slamMessage')).toContainText('replacement-session');
  await fixture.shared.releaseJobResponse();
  await expect(page.locator('#slamMessage')).toContainText('replacement-session');
  await expect(page.locator('#slamMessage')).not.toContainText('SUCCEEDED');
  expect(fixture.shared.mutations.filter((value) => value.path.endsWith('/stop'))).toHaveLength(0);
});

test('SLAM native preview remains renderer only; revisions and archive errors surface safely', async ({ page }) => {
  const fixture = await install(page);
  await open(page, 'maps');
  await expect(page.locator('#slamPackageRows button')).toHaveCount(1);
  await page.locator('#slamPackageFilter').selectOption('vslam');
  await page.locator('#slamPackageRows button').click();
  await expect(page.locator('#slamPackageDetail')).toContainText('SYNTHETIC_FIXTURE');
  await expect(page.locator('#slamPackageDetail')).toContainText('approximate');
  await expect(page.locator('#slamPackageExport')).toHaveAttribute('href', `/api/v1/slam/packages/${PACKAGE_ID}/export?expected_revision=${REVISION}`);
  await expect(page.locator('#slamPackagePreviewExport')).toHaveAttribute('href', `/api/v1/slam/packages/${PACKAGE_ID}/preview-export?expected_revision=${REVISION}`);
  await expect(page.locator('#slamPackagePreviewExport')).toHaveAttribute('download', `preview-${PACKAGE_ID}.zip`);
  await expect(page.locator('.slam-archive-support')).toContainText('전체 관측 경로를 보장하지 않습니다.');
  await expect(page.locator('#slamPackageLibrary img')).toHaveCount(0);
  await page.locator('#slamPackageFilter').selectOption('vslam');
  await expect(page.locator('[data-page=maps] .saved-layout')).toBeHidden();
  await page.locator('#slamPackageFilter').selectOption('lidar');
  await expect(page.locator('#slamNativeDetail')).toBeHidden();
  await page.locator('#slamPackageFilter').selectOption('vslam');
  expect(fixture.shared.mutations).toEqual([]);
  await page.locator('#slamPackageName').fill('renamed');
  await page.locator('#slamPackageRename').click();
  await expect(page.locator('#slamPackageStatus')).toContainText('REVISION_CONFLICT');
  expect(fixture.shared.mutations.at(-1).body.expected_revision).toBe(REVISION);
  await page.locator('#slamPackageImport').setInputFiles({ name: 'unsafe.zip', mimeType: 'application/zip', buffer: Buffer.from('not a zip') });
  await expect(page.locator('#slamPackageStatus')).toContainText('UNSAFE_ARCHIVE');
  expect(fixture.shared.mutations.some((value) => value.path === '/sessions')).toBe(false);
});

test('SLAM localization needs an operator verified frame/pose and never invents an identity hint', async ({ page }) => {
  const fixture = await install(page);
  await open(page); await startStereo(page);
  await page.evaluate(() => { location.hash = 'maps'; });
  await expect(page.locator('#slamPackageRows button')).toHaveCount(1);
  await page.locator('#slamPackageFilter').selectOption('vslam');
  await page.locator('#slamPackageRows button').click();
  await page.locator('#slamArchiveReuse summary').click();
  await expect(page.locator('#slamHintPosition')).toHaveValue('');
  await expect(page.locator('#slamHintQuaternion')).toHaveValue('');
  await expect(page.locator('#slamPackageLocalize')).toBeDisabled();
  await page.locator('#slamHintVerified').check();
  await expect(page.locator('#slamPackageLocalize')).toBeDisabled();
  await expect(page.locator('#slamReplaceUnsaved')).not.toBeChecked();
  expect(fixture.shared.mutations.filter((value) => value.path.endsWith('/localize'))).toHaveLength(0);
  await page.locator('#slamReplaceUnsaved').check();
  await page.locator('#slamPackageLocalize').click();
  await expect(page.locator('#slamPackageStatus')).toContainText('INVALID_POSE_HINT');
  expect(fixture.shared.mutations.filter((value) => value.path.endsWith('/localize'))).toHaveLength(0);
  await page.locator('#slamHintFrame').fill('map');
  await page.locator('#slamHintPosition').fill('1, 2, 0.3');
  await page.locator('#slamHintQuaternion').fill('0, 0, 0, 1');
  await page.locator('#slamReplaceUnsaved').uncheck();
  await expect(page.locator('#slamPackageLocalize')).toBeDisabled();
  await page.locator('#slamReplaceUnsaved').check();
  await page.locator('#slamPackageLocalize').click();
  await expect.poll(() => fixture.shared.mutations.filter((value) => value.path.endsWith('/localize')).length).toBe(1);
  expect(fixture.shared.mutations.at(-1).body).toMatchObject({
    generation: 1, package_id: PACKAGE_ID, revision: REVISION, discard_unsaved: true,
    hint: { frame_id: 'map', position: [1, 2, 0.3], quaternion_xyzw: [0, 0, 0, 1], operator_verified: true },
  });
  await expect(page.locator('#slamReplaceUnsaved')).not.toBeChecked();
  await expect(page.locator('#slamPackageLocalizationStatus')).toContainText('공식 localization 서비스 완료: true');
  await expect(page.locator('#slamPackageLocalizationStatus')).toContainText('native load: verified');
  await expect(page.locator('#slamPackageLocalizationStatus')).toContainText('localize_success: false');
  await expect(page.locator('#slamPackageLocalizationStatus')).toContainText('새 corrected pose / TRACKING 확인: false');
  await expect(page.locator('#slamPackageLocalizationStatus')).toContainText('POST_LOCALIZATION_POSE_TIMEOUT');
  await expect(page.locator('#slamPackageLocalizationStatus')).toContainText('현재 세션을 중지하고 새 세션');
  await page.locator('#slamHintVerified').check();
  await page.locator('#slamReplaceUnsaved').check();
  await expect(page.locator('#slamPackageLocalize')).toBeDisabled();
  await page.evaluate(() => { location.hash = 'mapping'; });
  await expect(page.locator('#slamLocalizationStatus')).toContainText('POST_LOCALIZATION_POSE_TIMEOUT');
});

test('SLAM two tabs and reconnect do not duplicate start or retain inactive visualization sockets', async ({ page, context }) => {
  const fixture = await install(page);
  await open(page); await startStereo(page);
  const second = await context.newPage();
  await install(second, { state: fixture.shared });
  await second.goto('/#mapping');
  await second.addScriptTag({ type: 'module', url: '/static/features/slam/dashboard.js' });
  await expect(second.locator('#slamSessionState')).toHaveText('MAPPING');
  await expect(second.locator('#slamStart')).toBeDisabled();
  await second.reload();
  await second.addScriptTag({ type: 'module', url: '/static/features/slam/dashboard.js' });
  await expect(second.locator('#slamSessionState')).toHaveText('MAPPING');
  const sockets = [...fixture.shared.sockets];
  for (const socket of sockets) socket.close();
  await expect.poll(() => fixture.shared.sockets.size).toBeGreaterThan(0);
  expect(fixture.shared.mutations.filter((value) => value.path === '/sessions')).toHaveLength(1);
  await second.evaluate(() => { location.hash = 'maps'; });
  await expect(second.locator('#slamPackageLibrary')).toBeVisible();
  await expect.poll(() => fixture.shared.sockets.size).toBeLessThanOrEqual(1);
  await second.close();
});
