import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../robot_dashboard/static/features/slam/dashboard.js', import.meta.url), 'utf8');
const { boundedPoints, overlayMatchesImage, frameIsCurrent, describeCoverage, cameraFrustumGeometry,
  describeLocalization, SLAM_STREAM_PATH } = await import(
  'data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

const session = { session_id: 'session-a', generation: 4, map_epoch: 'epoch-a', engine_id: 'visual_stereo' };
const frame = { ...session, sequence: '1', tracking_state: 'MAPPING', stream_connected: true,
  image: { jpeg_base64: 'AA==', stamp_ns: '9007199254740993001', frame_id: 'left_optical', width: 640, height: 480, camera_id: 'left', rectified: true },
  overlay: { overlay_kind: 'current_observations_reprojected', reason: null, points: [[10, 20]],
    image: { source_timestamp_ns: '9007199254740993001', frame_id: 'left_optical', width: 640, height: 480, camera_id: 'left' } } };

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
