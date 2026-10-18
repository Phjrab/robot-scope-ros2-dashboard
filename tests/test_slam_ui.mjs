import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../robot_dashboard/static/features/slam/dashboard.js', import.meta.url), 'utf8');
const { boundedPoints, overlayMatchesImage, frameIsCurrent, describeCoverage, cameraFrustumGeometry,
  describeLocalization, frameAvailability, describeCameraPose, errorText, SLAM_STREAM_PATH,
  sameSessionContext, saveJobIsCurrent, SLAM_REQUEST_TIMEOUT_MS, geometryFrameHydrator,
  latestFrameRenderer, latestImageDecoder, sameImageSource, samePointGeometry,
  reconcileStopProgress, describeStopProgress, sessionReadbackIsCurrent, sessionSnapshotIsValid } = await import(
  'data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

const session = { session_id: 'session-a', generation: 4, map_epoch: 'epoch-a', engine_id: 'visual_stereo' };
const frame = { ...session, sequence: '1', tracking_state: 'MAPPING', stream_connected: true,
  image: { jpeg_base64: 'AA==', stamp_ns: '9007199254740993001', frame_id: 'left_optical', width: 640, height: 480, camera_id: 'left', rectified: true },
  overlay: { overlay_kind: 'current_observations_reprojected', reason: null, points: [[10, 20]],
    image: { source_timestamp_ns: '9007199254740993001', frame_id: 'left_optical', width: 640, height: 480, camera_id: 'left' } } };

const geometryFrame = () => ({ ...structuredClone(frame), frame_id: 'map',
  global_map: { coordinate_frame: 'map', map_epoch: session.map_epoch, points: [[1, 2, 3]] },
  trajectory: { coordinate_frame: 'map', map_epoch: session.map_epoch, points: [[0, 0, 0]] },
  geometry_updates: { version: 1, layers: { global_map: { kind: 'full', token: '1' }, trajectory: { kind: 'full', token: '2' } } } });

test('geometry references preserve exact complete layer and fresh independent channels', () => {
  const cache = geometryFrameHydrator(), full = geometryFrame();
  const first = cache.hydrate(full);
  const reference = { ...full, global_map: null, trajectory: null, camera_pose: { position: [4, 5, 6] },
    geometry_updates: { version: 1, layers: { global_map: { kind: 'reference', token: '1' }, trajectory: { kind: 'reference', token: '2' } } } };
  const next = cache.hydrate(reference);
  assert.equal(next.global_map, first.global_map);
  assert.equal(next.trajectory, first.trajectory);
  assert.equal(next.image, reference.image);
  assert.equal(next.camera_pose, reference.camera_pose);
  assert.equal(reference.global_map, null);
  const corrected = geometryFrame();
  corrected.global_map.points[0][0] = 42;
  corrected.geometry_updates.layers.global_map.token = '3';
  assert.equal(cache.hydrate(corrected).global_map.points[0][0], 42);
});

test('missing or invalid geometry references clear only that layer and never cross contexts', () => {
  for (const change of [{ session_id: 'other' }, { generation: 5 }, { engine_id: 'other' },
    { map_epoch: 'other' }, { frame_id: 'other' }, {}]) {
    const cache = geometryFrameHydrator(), full = geometryFrame();
    cache.hydrate(full);
    const ref = { ...full, ...change, global_map: null, trajectory: null,
      geometry_updates: { version: 1, layers: { global_map: { kind: 'reference', token: change.session_id ? '1' : '999' } } } };
    const result = cache.hydrate(ref);
    assert.equal(result.global_map, null); assert.equal(result.trajectory, null);
    assert.equal(result.image, full.image); assert.equal(result.overlay, full.overlay);
  }
  for (const clear of ['explicit', 'legacy', 'absent', 'badversion', 'invalidpoints']) {
    const cache = geometryFrameHydrator(), full = geometryFrame();
    cache.hydrate(full);
    if (clear === 'explicit') cache.clear();
    if (clear === 'legacy') cache.hydrate({ ...full, geometry_updates: undefined });
    if (clear === 'absent') cache.hydrate({ ...full, global_map: null, geometry_updates: { version: 1, layers: {} } });
    if (clear === 'badversion') cache.hydrate({ ...full, geometry_updates: { version: 2, layers: full.geometry_updates.layers } });
    if (clear === 'invalidpoints') cache.hydrate({ ...full, global_map: { ...full.global_map, points: [[NaN, 0, 0]] } });
    assert.equal(cache.hydrate({ ...full, global_map: null,
      geometry_updates: { version: 1, layers: { global_map: { kind: 'reference', token: '1' } } } }).global_map, null);
  }
});

test('latest-frame renderer bounds backlog and cancels pending renders', () => {
  const callbacks = new Map(), painted = []; let id = 0;
  const renderer = latestFrameRenderer((fn) => { callbacks.set(++id, fn); return id; },
    (key) => callbacks.delete(key), (value) => painted.push(value));
  for (let i = 0; i < 100; i++) renderer.submit({ sequence: i });
  assert.equal(callbacks.size, 1);
  const flush = () => { const [key, fn] = callbacks.entries().next().value; callbacks.delete(key); fn(); };
  flush(); assert.deepEqual(painted, [{ sequence: 99 }]);
  renderer.submit({ sequence: 100 }); renderer.clear();
  assert.equal(callbacks.size, 0); assert.equal(painted.length, 1);
  renderer.submit({ sequence: 101 }); flush(); assert.equal(painted.at(-1).sequence, 101);
});

test('one decoder skips intermediate images, keeps matched overlays and reuses identical pixels', () => {
  const images = [], painted = [], failures = [];
  const decoder = latestImageDecoder(() => { const image = { naturalWidth: 640, naturalHeight: 480 }; images.push(image); return image; },
    () => true, (image, value) => painted.push({ image, value }), (error) => failures.push(error));
  const a = structuredClone(frame), b = structuredClone(frame), c = structuredClone(frame);
  b.image.stamp_ns = '2'; c.image.stamp_ns = '3';
  decoder.submit(a); decoder.submit(b); decoder.submit(c);
  assert.equal(images.length, 1); images[0].onload();
  assert.equal(painted[0].value, a); assert.equal(images.length, 2);
  images[1].onload(); assert.equal(painted[1].value, c);
  const newOverlay = { ...c, overlay: { ...c.overlay, points: [[5, 6]] } };
  decoder.submit(newOverlay);
  assert.equal(images.length, 2); assert.equal(painted.at(-1).value, newOverlay);
  assert.equal(sameImageSource(a, b), false);
  assert.equal(sameImageSource(c, { ...c, map_epoch: 'other' }), false);
  assert.deepEqual(failures, []);
});

test('decoder clear, expired contexts, dimensions and errors cannot paint stale pixels', () => {
  const images = [], painted = [], failures = []; let current = true;
  const decoder = latestImageDecoder(() => { const image = { naturalWidth: 640, naturalHeight: 480 }; images.push(image); return image; },
    () => current, (_, value) => painted.push(value), (error) => failures.push(error));
  decoder.submit(frame); const oldLoad = images[0].onload; decoder.clear(); oldLoad();
  assert.equal(painted.length, 0); assert.equal(images[0].src, '');
  decoder.submit(frame); current = false; images[1].onload(); assert.equal(painted.length, 0);
  decoder.clear(); current = true; decoder.submit(frame); images[2].naturalWidth = 2; images[2].onload();
  assert.deepEqual(failures, ['IMAGE_DIMENSION_MISMATCH']);
  decoder.submit(frame); images[3].onerror();
  assert.deepEqual(failures, ['IMAGE_DIMENSION_MISMATCH', 'IMAGE_DECODE_UNAVAILABLE']);
});

test('point equality detects coordinate corrections even when array counts match', () => {
  assert.equal(samePointGeometry([[1, 2, 3]], [[1, 2, 3]]), true);
  assert.equal(samePointGeometry([[1, 2, 3]], [[1, 2, 4]]), false);
  assert.equal(samePointGeometry([[1, 2, 3]], []), false);
});

test('save results require the originating session, generation, engine and map epoch', () => {
  const job = { job_id: 'save-a', session_id: session.session_id, generation: session.generation };
  assert.equal(SLAM_REQUEST_TIMEOUT_MS, 15_000);
  assert.equal(saveJobIsCurrent(job, session, { ...session }), true);
  for (const change of [{ session_id: 'session-b' }, { generation: 5 }, { map_epoch: 'epoch-b' }, { engine_id: 'lidar_fastlio' }]) {
    assert.equal(sameSessionContext(session, { ...session, ...change }), false);
    assert.equal(saveJobIsCurrent(job, session, { ...session, ...change }), false);
  }
  for (const change of [{ job_id: null }, { session_id: 'session-b' }, { generation: 5 }, { generation: undefined }]) {
    assert.equal(saveJobIsCurrent({ ...job, ...change }, session, session), false);
  }
  assert.equal(sameSessionContext({ session_id: 'x' }, { session_id: 'x' }), false);
  assert.equal(saveJobIsCurrent(job, null, session), false);
});

test('SLAM websocket uses the registered backend route rather than an unregistered short path', () => {
  const router = readFileSync(new URL('../robot_dashboard/api/routers/slam.py', import.meta.url), 'utf8');
  const registered = /@router\.websocket\("([^\"]+)"\)/.exec(router)?.[1];
  assert.equal(SLAM_STREAM_PATH, '/api/v1/ws/slam');
  assert.equal(SLAM_STREAM_PATH, registered);
});

test('localization displays service/native completion separately from fresh-pose success and retry condition', () => {
  const failure = describeLocalization({ official_localization_completed: true, native_load: 'verified',
    localize_success: false, fresh_pose_tracking_confirmed: false,
    confirmation_reason: 'POST_LOCALIZATION_POSE_TIMEOUT', retry_requires_new_session: true }, { state: 'MAPPING', reason: null });
  assert.match(failure, /공식 localization 서비스 완료: true/);
  assert.match(failure, /native load: verified/);
  assert.match(failure, /localize_success: false/);
  assert.match(failure, /새 corrected pose \/ TRACKING 확인: false/);
  assert.match(failure, /POST_LOCALIZATION_POSE_TIMEOUT/);
  assert.match(failure, /현재 세션을 중지하고 새 세션/);
  const verified = describeLocalization({ official_localization_completed: true, native_load: 'verified',
    localize_success: true, fresh_pose_tracking_confirmed: true });
  assert.match(verified, /localize_success: true/);
  assert.match(verified, /새 corrected pose \/ TRACKING 확인: true/);
  const pending = describeLocalization({ state: 'LOCALIZING', native_load: 'PENDING', localize_success: false });
  assert.match(pending, /localize_success: pending/);
  assert.match(pending, /공식 localization 서비스 완료: unknown/);
  assert.match(describeLocalization(null), /실행 기록 없음/);
});

test('camera overlay requires exact nanosecond image identity without Number conversion', () => {
  assert.equal(overlayMatchesImage(frame), true);
  assert.equal(overlayMatchesImage({ ...frame, image: { ...frame.image, stamp_ns: '9007199254740993002' } }), false);
  assert.equal(overlayMatchesImage({ ...frame, image: { ...frame.image, stamp_ns: 9007199254740993001 } }), false);
  for (const change of [{ frame_id: 'rgb' }, { camera_id: 'right' }, { width: 1280 }, { rectified: false }]) {
    assert.equal(overlayMatchesImage({ ...frame, image: { ...frame.image, ...change } }), false);
  }
  assert.equal(overlayMatchesImage({ ...frame, image: { ...frame.image, jpeg_base64: undefined, png_base64: 'AA==' } }), true);
});

test('zero current observations are valid while stale, lost and unavailable overlay are hidden', () => {
  assert.equal(overlayMatchesImage({ ...frame, overlay: { ...frame.overlay, points: [] } }), true);
  for (const state of ['LOST', 'STOPPED', 'WAITING_INPUT']) assert.equal(overlayMatchesImage({ ...frame, tracking_state: state }), false);
  assert.equal(overlayMatchesImage({ ...frame, stream_connected: false }), false);
  assert.equal(overlayMatchesImage({ ...frame, overlay: { ...frame.overlay, reason: 'STALE_SOURCE' } }), false);
  assert.equal(overlayMatchesImage({ ...frame, overlay: { ...frame.overlay, overlay_kind: 'unavailable' } }), false);
});

test('image caption names the unavailable overlay separately from the available input image', () => {
  const assignment = source.split('\n').find((line) => line.includes('imageStatus.textContent = `입력 이미지 available'));
  assert.ok(assignment);
  const imageStatus = { textContent: '' };
  runInNewContext(assignment, { imageStatus, canOverlay: false,
    overlay: { overlay_kind: 'unavailable', reason: 'NO_VALID_TIME_ALIGNMENT' } });
  assert.match(imageStatus.textContent, /^입력 이미지 available · 오버레이 unavailable · NO_VALID_TIME_ALIGNMENT/);
});

test('session, generation, engine, epoch and exact increasing sequence fence stream frames', () => {
  assert.equal(frameIsCurrent(frame, session), true);
  for (const change of [{ session_id: 'old' }, { generation: 3 }, { engine_id: 'lidar_fastlio' }, { map_epoch: 'old' }]) {
    assert.equal(frameIsCurrent({ ...frame, ...change }, session), false);
  }
  assert.equal(frameIsCurrent(frame, session, frame), false);
  assert.equal(frameIsCurrent({ ...frame, sequence: '9007199254740993002' }, session, { ...frame, sequence: '9007199254740993001' }), true);
  assert.equal(frameIsCurrent({ ...frame, sequence: 'bad' }, session, frame), false);
  assert.equal(frameIsCurrent(frame, null), false);
});

test('bounded renderer input rejects malformed dimensions/nonfinite/oversized frames', () => {
  assert.deepEqual(boundedPoints([[1, 2, 3], [0, 0, 0], [1, 2], [1, 2, Infinity], ['1', 2, 3]]), [[1, 2, 3], [0, 0, 0]]);
  assert.deepEqual(boundedPoints([[1, 2], [3, 4]], 4096, 2), [[1, 2], [3, 4]]);
  assert.deepEqual(boundedPoints([[1, 2, 3], [4, 5, 6]], 1), []);
  assert.deepEqual(boundedPoints(null), []);
});

test('global extent and source completeness labels do not invent engine totals', () => {
  const label = describeCoverage({ spatial_scope: 'global_map', coverage: 'subset', displayed_count: 60,
    exported_count: 100, engine_total_count: null, backend_limit: 32768, decimation: true, coordinate_frame: 'map' });
  assert.match(label, /global_map/);
  assert.match(label, /coverage subset/);
  assert.match(label, /표시 60/);
  assert.match(label, /export 100/);
  assert.match(label, /engine total unknown/);
  assert.match(label, /backend cap 32768/);
  assert.match(label, /engine revision unknown/);
});

function liveCameraFrame() {
  return { ...frame, frame_id: 'map', camera_pose: { position: [1, 2, 3], quaternion_xyzw: [0, 0, 0, 1],
    frame_id: 'map', stamp_ns: '9007199254740993001' },
    readiness: { ready: false, tracking_state: 'TRACKING', pose_reference: 'camera_link', operational_pose_approved: false,
      freshness: { image: true, pose: true, tracking: true } },
    overlay: { overlay_kind: 'unavailable', reason: 'OBSERVATIONS_UNAVAILABLE' } };
}

test('fresh camera image, camera 6DoF and tracking survive absent overlay, map and trajectory', () => {
  const current = liveCameraFrame();
  const channels = frameAvailability(current);
  assert.equal(channels.image.available, true);
  assert.equal(channels.pose.available, true);
  assert.equal(channels.tracking.available, true);
  assert.equal(channels.overlay.available, false);
  assert.equal(channels.global_map.available, false);
  assert.equal(channels.trajectory.available, false);
  // Feature-stream heartbeat and aggregate readiness are not image/pose gates.
  assert.equal(frameAvailability({ ...current, stream_connected: false }).image.available, true);
  assert.equal(frameAvailability({ ...current, stream_connected: false }).pose.available, true);
  const label = describeCameraPose(current);
  assert.match(label, /카메라 6DoF/);
  assert.match(label, /camera_link/);
  assert.match(label, /1\.000 \/ 2\.000 \/ 3\.000/);
  assert.match(label, /9007199254740993001/);
  assert.match(label, /Go2 body pose 미검증/);
  assert.match(label, /camera→Go2 extrinsic 필요/);
  assert.match(label, /주행 승인 안 됨/);
  assert.doesNotMatch(label, /PASS/);
});

test('each live output obeys its own freshness while subset snapshots remain independently available', () => {
  const current = liveCameraFrame();
  const layers = { ...current,
    global_map: { coordinate_frame: 'map', map_epoch: session.map_epoch, coverage: 'subset', points: [[1, 2, 3]] },
    trajectory: { coordinate_frame: 'map', map_epoch: session.map_epoch, trajectory_kind: 'slam', points: [[0, 0, 0]] } };
  for (const coverage of ['subset', 'unknown']) {
    assert.equal(frameAvailability({ ...layers, global_map: { ...layers.global_map, coverage } }).global_map.available, true);
  }
  const missingMap = frameAvailability({ ...layers, global_map: null });
  assert.equal(missingMap.global_map.available, false);
  assert.equal(missingMap.trajectory.available, true);
  const invalidMap = frameAvailability({ ...layers, global_map: { ...layers.global_map, map_epoch: 'old' } });
  assert.equal(invalidMap.global_map.available, false);
  assert.equal(invalidMap.global_map.reason, 'GLOBAL_MAP_CONTEXT_OR_POINTS_INVALID');
  assert.equal(invalidMap.trajectory.available, true);
  const stale = frameAvailability(layers, false);
  for (const key of ['image', 'pose', 'tracking', 'overlay']) assert.equal(stale[key].available, false, key);
  assert.equal(stale.global_map.available, true);
  assert.equal(stale.trajectory.available, true);
  const imageStale = frameAvailability({ ...layers, readiness: { ...layers.readiness,
    freshness: { image: false, pose: true, tracking: false } } });
  assert.equal(imageStale.image.available, false);
  assert.equal(imageStale.pose.available, true);
  assert.equal(imageStale.tracking.available, false);
  assert.equal(frameAvailability({ ...layers, camera_pose: null }).image.available, true);
});

test('camera pose display rejects malformed or wrong-frame pose without hiding valid image', () => {
  const current = liveCameraFrame();
  for (const change of [{ position: [NaN, 0, 0] }, { quaternion_xyzw: [0, 0, 0, 0] },
    { frame_id: 'body' }, { stamp_ns: 9007199254740993001 }]) {
    const invalid = { ...current, camera_pose: { ...current.camera_pose, ...change } };
    assert.equal(frameAvailability(invalid).pose.available, false);
    assert.equal(frameAvailability(invalid).image.available, true);
    assert.match(describeCameraPose(invalid), /pose unavailable/);
  }
});

test('resource conflict names concrete bounded resources and uses an unknown fallback', () => {
  const label = errorText({ detail: { code: 'RESOURCE_CONFLICT', resources: [
    { resource: 'lidar', reason: 'existing_lidar_pipeline_active' },
    { resource: 'camera', reason: 'camera_owner_active' },
    { resource: '__proto__', reason: '<private>' },
  ] } }, 'fallback');
  assert.match(label, /RESOURCE_CONFLICT/);
  assert.match(label, /LiDAR \(existing_lidar_pipeline_active\)/);
  assert.match(label, /카메라 \(camera_owner_active\)/);
  assert.match(label, /알 수 없는 자원/);
  assert.doesNotMatch(label, /<private>|__proto__/);
  const cleanup = errorText({ detail: { code: 'CLEANUP_REQUIRED', resources: [
    { resource: 'ros_domain', reason: 'foreign_participant' },
  ] } }, 'fallback');
  assert.equal(cleanup, 'CLEANUP_REQUIRED · ROS domain (foreign_participant)');
  assert.ok(errorText({ detail: { code: 'RESOURCE_CONFLICT', resources: Array(1000).fill({
    resource: 'camera', reason: 'x'.repeat(10000) }) } }, '').length < 300);
  assert.equal(errorText({ detail: { code: 'CAMERA_BUSY' } }, 'fallback'), 'CAMERA_BUSY');
});

function opticalFrame() {
  const stamp = '9007199254740993001';
  return { ...frame, camera_pose: { position: [99, 99, 99] },
    overlay: { ...frame.overlay, image: { ...frame.overlay.image, calibration_revision: 'calibration-7' } },
    camera_view: { available: true, ...session, coordinate_frame: 'map',
      camera_frame_id: 'left_optical', projection_convention: 'rectified_optical_x_right_y_down_z_forward',
      position: [10, 20, 30], quaternion_xyzw: [0, 0, 0, 1], intrinsics: [320, 240, 320, 240],
      width: 640, height: 480, calibration_revision: 'calibration-7', source_timestamp_ns: stamp,
      image_source_timestamp_ns: stamp, pose_source_timestamp_ns: stamp, calibration_source_timestamp_ns: stamp },
    frame_id: 'map' };
}

test('camera frustum comes from calibrated optical pose and bounded visual ray length', () => {
  const current = opticalFrame();
  const geometry = cameraFrustumGeometry(current.camera_view, current);
  assert.deepEqual(geometry.position, [10, 20, 30]);
  assert.deepEqual(geometry.corners, [[9, 19, 31], [11, 19, 31], [11, 21, 31], [9, 21, 31]]);
  assert.equal(geometry.ray_length_m, 1);
  const rotated = cameraFrustumGeometry({ ...current.camera_view,
    quaternion_xyzw: [0, 0, Math.SQRT1_2, Math.SQRT1_2] }, current);
  assert.ok(Math.abs(rotated.corners[0][0] - 11) < 1e-9);
  assert.ok(Math.abs(rotated.corners[0][1] - 19) < 1e-9);
  assert.equal(cameraFrustumGeometry(current.camera_view, current, Infinity), null);
  const noObservations = { ...current, overlay: { ...current.overlay, overlay_kind: 'unavailable', reason: 'OBSERVATIONS_UNAVAILABLE' } };
  assert.ok(cameraFrustumGeometry(noObservations.camera_view, noObservations));
  const unrelatedMap = { ...current, global_map: { coordinate_frame: 'wrong' } };
  assert.ok(cameraFrustumGeometry(unrelatedMap.camera_view, unrelatedMap));
});

test('camera frustum rejects unverified, stale, old-context and mismatched source calibration', () => {
  const current = opticalFrame();
  for (const change of [
    { available: false }, { coordinate_frame: 'odom' }, { camera_frame_id: 'body' }, { map_epoch: 'old' },
    { session_id: 'old' }, { generation: 3 }, { engine_id: 'lidar_fastlio' }, { calibration_revision: 'wrong' },
    { projection_convention: 'body' }, { intrinsics: [0, 240, 320, 240] }, { quaternion_xyzw: [0, 0, 0, 0] },
    { position: [NaN, 0, 0] }, { width: 1280 }, { image_source_timestamp_ns: '9007199254740993002' },
    { pose_source_timestamp_ns: '9007199254761993001' }, { pose_source_timestamp_ns: 1 },
  ]) assert.equal(cameraFrustumGeometry({ ...current.camera_view, ...change }, current), null, JSON.stringify(change));
  assert.equal(cameraFrustumGeometry(current.camera_view, { ...current, tracking_state: 'LOST' }), null);
  assert.equal(cameraFrustumGeometry(current.camera_view, { ...current, stream_connected: false }), null);
});

test('renderer camera hook draws only bounded same-frame geometry; opt-in map trail keeps existing pose fences', () => {
  const sceneSource = readFileSync(new URL('../robot_dashboard/static/scene3d.js', import.meta.url), 'utf8');
  const calls = { lines: 0, markers: 0 };
  const context = { setTransform() {}, clearRect() {}, save() {}, restore() {}, setLineDash() {}, beginPath() {},
    moveTo() {}, lineTo() { calls.lines += 1; }, stroke() {}, arc() { calls.markers += 1; }, fill() {}, fillText() {} };
  const canvas = { width: 640, height: 360, clientWidth: 640, clientHeight: 360, style: {},
    getContext: () => context, getBoundingClientRect: () => ({ width: 640, height: 360 }),
    hasAttribute: () => true, setAttribute() {}, addEventListener() {}, removeEventListener() {} };
  const sandbox = { Float32Array, Math, Number, Object, devicePixelRatio: 1, requestAnimationFrame: () => 1,
    cancelAnimationFrame() {}, addEventListener() {}, removeEventListener() {} };
  sandbox.globalThis = sandbox; sandbox.window = sandbox;
  runInNewContext(sceneSource, sandbox);
  const scene = new sandbox.RobotScene3D(canvas, { storage: null, worldFrameTrail: true });
  scene.render = () => {};
  scene.cloud.frameId = 'map';
  const current = opticalFrame();
  const geometry = cameraFrustumGeometry(current.camera_view, current);
  assert.equal(scene.setCameraFrustum(geometry), true);
  scene._project = ([x, y, z]) => ({ x, y, depth: z });
  assert.equal(scene._drawCameraFrustum(), 8);
  assert.equal(calls.markers, 1);
  scene.cloud.frameId = 'odom'; assert.equal(scene._drawCameraFrustum(), 0);
  assert.equal(scene.setCameraFrustum({ ...geometry, corners: [...geometry.corners, [1, 2, 3]] }), false);
  assert.equal(scene.setCameraFrustum(null), false);
  scene.cloud.frameId = 'map';
  scene.setTrail([{ x: 0, y: 0, z: 0, frameId: 'map' }, { x: 1, y: 0, z: 0, frameId: 'map' }]);
  assert.equal(scene._displayTrail().length, 2);
  scene.options.worldFrameTrail = false;
  assert.equal(scene._displayTrail().length, 0);
  scene.destroy();
});

function stopActionFixture({ post, readback } = {}) {
  const start = source.indexOf('  async function stopSession(');
  const end = source.indexOf('\n  function ', start + 3);
  const state = { session: { ...session, state: 'MAPPING' }, refreshSerial: 0 };
  const writes = [];
  const sandbox = { state, requestId: () => 'stop-request-a', win: {},
    sameSessionContext, SLAM_REQUEST_TIMEOUT_MS,
    currentSession: () => state.session,
    requireSession(expected) {
      if (!sameSessionContext(expected, state.session)) throw Object.assign(new Error('SLAM_SESSION_CHANGED'), { staleAction: true });
    },
    updateButtons() {}, renderSessionStatus() {},
    message: { textContent: '' }, sessionMessage: () => '',
    api: async (path, options) => { writes.push({ path, options });
      return post ? post(state) : { session_id: session.session_id, generation: session.generation, state: 'STOPPING' }; },
    refresh: async () => readback ? readback(state) : undefined };
  const action = runInNewContext(`(${source.slice(start, end).trim()})`, sandbox);
  return { state, writes, action };
}

// This failed with SLAM_REQUEST_TIMEOUT before the fix: the actual production
// action used to discard the POST acknowledgement and throw the GET failure.
test('accepted Stop survives immediate status timeout without reporting mapping or retrying', async () => {
  const fixture = stopActionFixture({ readback: async () => { throw new Error('SLAM_REQUEST_TIMEOUT'); } });
  await fixture.action(true);
  const { state, writes } = fixture;
  assert.equal(state.stopRequest.phase, 'accepted');
  assert.equal(state.stopRequest.readbackError, 'SLAM_REQUEST_TIMEOUT');
  const display = describeStopProgress(state.stopRequest, state.session);
  assert.equal(display.status, 'STOP_ACCEPTED');
  assert.match(display.message, /중지 요청 수락/);
  assert.match(display.message, /완료는 아직 미확인/);
  assert.match(display.message, /상태 조회 실패/);
  await fixture.action(true);
  assert.equal(writes.length, 1);
});

test('Stop readback distinguishes cleaning, confirmed IDLE and actual cleanup failure', () => {
  const accepted = { session, phase: 'accepted', readbackError: 'SLAM_REQUEST_TIMEOUT' };
  const stopping = reconcileStopProgress(accepted, { ...session, state: 'STOPPING' });
  assert.equal(stopping.phase, 'stopping'); assert.equal(stopping.readbackError, null);
  assert.match(describeStopProgress(stopping, session).message, /서버 정리 중/);
  const failure = reconcileStopProgress(stopping, { ...session, state: 'ERROR', cleanup_required: true, reason: 'CLEANUP_REQUIRED' });
  assert.equal(failure.phase, 'cleanup_failed');
  assert.match(describeStopProgress(failure, session).message, /서버 정리 실패.*자원 해제 미확인/);
  const idle = reconcileStopProgress(stopping, { ...session, state: 'IDLE', cleanup_required: false });
  assert.equal(idle.phase, 'idle');
  assert.equal(describeStopProgress(idle, session).status, 'IDLE');
  assert.match(describeStopProgress(idle, session).message, /서버 IDLE 확인/);
  const contradictory = reconcileStopProgress(stopping, { ...session, state: 'IDLE', cleanup_required: true });
  assert.equal(contradictory.phase, 'cleanup_failed');
});

test('cleanup retry follows server STOPPING and IDLE while historical failure reason remains', () => {
  const failedSession = { ...session, state: 'ERROR', cleanup_required: true, reason: 'CLEANUP_REQUIRED' };
  const retry = { session: failedSession, phase: 'accepted' };
  const stopping = reconcileStopProgress(retry, { ...failedSession, state: 'STOPPING' });
  assert.equal(stopping.phase, 'stopping');
  assert.equal(describeStopProgress(stopping, failedSession).status, 'STOPPING');
  const finished = reconcileStopProgress(stopping, { ...failedSession, state: 'IDLE', cleanup_required: false });
  assert.equal(finished.phase, 'idle');
  assert.equal(describeStopProgress(finished, failedSession).status, 'IDLE');
  assert.doesNotMatch(describeStopProgress(finished, failedSession).message, /실패/);
});

test('incomplete or invalid session snapshots cannot be interpreted as confirmed IDLE', () => {
  const valid = { generation: 4, active_session: { ...session, state: 'MAPPING' } };
  assert.equal(sessionSnapshotIsValid(valid), true);
  assert.equal(sessionSnapshotIsValid({ generation: 0, active_session: null }), true);
  for (const value of [null, {}, { generation: 4 }, { active_session: null }, { generation: -1, active_session: null },
    { ...valid, active_session: { ...valid.active_session, state: 'INVENTED' } },
    { ...valid, active_session: { ...valid.active_session, map_epoch: null } },
    { ...valid, active_session: { ...valid.active_session, cleanup_required: 'false' } }]) {
    assert.equal(sessionSnapshotIsValid(value), false);
    assert.equal(sessionReadbackIsCurrent(value, session, 4), false);
  }
});

test('Stop receipts never migrate to another session, epoch or generation', () => {
  const request = { session, phase: 'accepted' };
  for (const change of [{ session_id: 'other' }, { generation: 5 }, { map_epoch: 'new' }, { engine_id: 'other' }]) {
    assert.equal(reconcileStopProgress(request, { ...session, ...change, state: 'IDLE' }), null);
    assert.equal(describeStopProgress(request, { ...session, ...change }), null);
  }
  assert.equal(reconcileStopProgress(request, null), null);
});

test('session reads reject older generations and cannot revive an already IDLE generation', () => {
  const idle = { ...session, state: 'IDLE' };
  assert.equal(sessionReadbackIsCurrent({ generation: 3, active_session: { ...session, generation: 3 } }, idle, 4), false);
  assert.equal(sessionReadbackIsCurrent({ generation: 4, active_session: { ...session, generation: 3 } }, idle, 4), false);
  assert.equal(sessionReadbackIsCurrent({ generation: 4, active_session: { ...session, state: 'MAPPING' } }, idle, 4), false);
  assert.equal(sessionReadbackIsCurrent({ generation: 4, active_session: idle }, idle, 4), true);
  assert.equal(sessionReadbackIsCurrent({ generation: 5, active_session: { ...session, generation: 5, state: 'MAPPING' } }, idle, 4), true);
});

test('unknown Stop response stays unconfirmed and does not automatically repeat writes', async () => {
  for (const post of [async () => { throw Object.assign(new Error('SLAM_REQUEST_TIMEOUT'), { transportUncertain: true }); },
    async () => ({ session_id: 'wrong-session', generation: 4, state: 'STOPPING' }), async () => null]) {
    const fixture = stopActionFixture({ post });
    await fixture.action(true); await fixture.action(true);
    assert.equal(fixture.state.stopRequest.phase, 'unconfirmed');
    assert.equal(describeStopProgress(fixture.state.stopRequest, fixture.state.session).status, 'STOP_UNCONFIRMED');
    assert.equal(fixture.writes.length, 1);
  }
});

test('late Stop acknowledgement cannot demote confirmed cleanup or overwrite a replacement', async () => {
  let resolve;
  const fixture = stopActionFixture({ post: () => new Promise((done) => { resolve = done; }) });
  const pending = fixture.action(true);
  fixture.state.session = { ...session, state: 'IDLE' };
  fixture.state.stopRequest = reconcileStopProgress(fixture.state.stopRequest, fixture.state.session);
  resolve({ session_id: session.session_id, generation: session.generation, state: 'STOPPING' });
  await pending;
  assert.equal(fixture.state.stopRequest.phase, 'idle');
  const other = stopActionFixture({ post: () => new Promise((done) => { resolve = done; }) });
  const obsolete = other.action(true);
  other.state.session = { ...session, generation: 5, state: 'MAPPING' };
  other.state.stopRequest = null;
  resolve({ session_id: session.session_id, generation: session.generation, state: 'STOPPING' });
  await assert.rejects(obsolete, { message: 'SLAM_SESSION_CHANGED', staleAction: true });
  assert.equal(other.state.stopRequest, null); assert.equal(other.state.session.generation, 5);
});

test('explicit Stop rejection releases only its own pending request for operator correction', async () => {
  const fixture = stopActionFixture({ post: async () => { throw new Error('UNSAVED_MAP_CONFIRMATION_REQUIRED'); } });
  await assert.rejects(fixture.action(false), /UNSAVED_MAP_CONFIRMATION_REQUIRED/);
  assert.equal(fixture.state.stopRequest, null); assert.equal(fixture.writes.length, 1);
});

test('older failed session GET cannot overwrite a newer readback or stop acknowledgement', async () => {
  const start = source.indexOf('  async function refresh()');
  const end = source.indexOf('\n  function updateLocalizationStatus(', start);
  let reject;
  const state = { activePage: 'mapping', refreshSerial: 0, session, stopRequest: { session, phase: 'idle' } };
  const message = { textContent: '서버 IDLE 확인' };
  const refresh = runInNewContext(`(${source.slice(start, end).trim()})`, {
    state, message, ACTIVE_PAGES: new Set(['mapping']), doc: { hidden: false }, sameSessionContext,
    api: () => new Promise((_, fail) => { reject = fail; }),
  });
  const pending = refresh(); state.refreshSerial += 1;
  reject(new Error('SLAM_REQUEST_TIMEOUT')); await pending;
  assert.equal(state.stopRequest.readbackError, undefined);
  assert.equal(message.textContent, '서버 IDLE 확인');
});
