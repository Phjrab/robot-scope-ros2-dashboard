import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../robot_dashboard/static/features/slam/dashboard.js', import.meta.url), 'utf8');
const { boundedPoints, overlayMatchesImage, frameIsCurrent, describeCoverage, cameraFrustumGeometry,
  describeLocalization, frameAvailability, describeCameraPose, errorText, SLAM_STREAM_PATH,
  sameSessionContext, saveJobIsCurrent, SLAM_REQUEST_TIMEOUT_MS } = await import(
  'data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

const session = { session_id: 'session-a', generation: 4, map_epoch: 'epoch-a', engine_id: 'visual_stereo' };
const frame = { ...session, sequence: '1', tracking_state: 'MAPPING', stream_connected: true,
  image: { jpeg_base64: 'AA==', stamp_ns: '9007199254740993001', frame_id: 'left_optical', width: 640, height: 480, camera_id: 'left', rectified: true },
  overlay: { overlay_kind: 'current_observations_reprojected', reason: null, points: [[10, 20]],
    image: { source_timestamp_ns: '9007199254740993001', frame_id: 'left_optical', width: 640, height: 480, camera_id: 'left' } } };

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
