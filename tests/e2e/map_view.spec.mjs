import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

// Synthetic display-only geometry: dense room + two remote points. No sensor,
// broker, robot API mutation or private captured map is involved.
const POINTS = Array.from({ length: 400 }, (_, index) => [index % 20 / 10 - 1, Math.floor(index / 20) / 10 - 1, index % 5 / 10]);
POINTS.push([-100, 0, 0], [100, 0, 0]);
const SESSION = { session_id: 'map-view-fixture', generation: 1, map_epoch: 'map-view-epoch',
  engine_id: 'visual_stereo', state: 'MAPPING', task: 'mapping' };
const STAMP = '9007199254740993001';
const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRz8AAAAASUVORK5CYII=';

function frame(sequence, { empty = false, pose = true } = {}) {
  return { schema_version: 1, ...SESSION, sequence: String(sequence), frame_id: 'map', clock_domain: 'ros',
    source_timestamp_ns: STAMP, stream_connected: true, heartbeat_receive_age_seconds: 0.05, tracking_state: 'MAPPING',
    image: { png_base64: PNG, stamp_ns: STAMP, width: 1, height: 1, frame_id: 'left_optical', camera_id: 'left', rectified: true },
    overlay: { overlay_kind: 'current_observations_reprojected', reason: null, points: [], displayed_count: 0,
      receive_age_seconds: 0.05, provenance: 'SYNTHETIC_FIXTURE',
      image: { source_timestamp_ns: STAMP, width: 1, height: 1, frame_id: 'left_optical', camera_id: 'left', calibration_revision: 'fixture-cal' } },
    camera_view: { available: pose, session_id: SESSION.session_id, generation: SESSION.generation,
      engine_id: SESSION.engine_id, map_epoch: SESSION.map_epoch, coordinate_frame: 'map', camera_frame_id: 'left_optical',
      position: [1, 0.5, 0.4], quaternion_xyzw: [0, 0, 0, 1], intrinsics: [1, 1, 0.5, 0.5], width: 1, height: 1,
      source_timestamp_ns: STAMP, image_source_timestamp_ns: STAMP, pose_source_timestamp_ns: STAMP,
      calibration_source_timestamp_ns: STAMP, calibration_revision: 'fixture-cal',
      projection_convention: 'rectified_optical_x_right_y_down_z_forward',
      provenance: 'SYNTHETIC_FIXTURE_timestamped_slam_map_rectified_optical_pose' },
    global_map: { spatial_scope: 'global_map', coverage: 'subset', points: empty ? [] : POINTS,
      displayed_count: empty ? 0 : POINTS.length, exported_count: empty ? 0 : POINTS.length, engine_total_count: null,
      backend_limit: 32768, decimation: false, coordinate_frame: 'map', map_epoch: SESSION.map_epoch,
      snapshot_id: String(sequence), source_timestamp_ns: STAMP, provenance: 'SYNTHETIC_FIXTURE' },
    trajectory: { points: [], trajectory_kind: 'slam', coordinate_frame: 'map', map_epoch: SESSION.map_epoch },
    camera_pose: pose ? { position: [1, 0.5, 0.4], quaternion_xyzw: [0, 0, 0, 1], frame_id: 'map', stamp_ns: STAMP } : null,
    readiness: { ready: true, tracking_state: 'TRACKING', pose_reference: 'camera_link',
      operational_pose_approved: false, pose_source: '/fixture/corrected_pose', freshness: { image: true, pose, tracking: true } } };
}

async function fixture(page) {
  await installDashboardBackend(page);
  const sockets = new Set();
  const mutations = [];
  let sequence = 0;
  await page.route('**/api/v1/slam/**', route => {
    const request = route.request();
    if (request.method() !== 'GET') mutations.push(request.url());
    const path = new URL(request.url()).pathname;
    const json = path.endsWith('/session') ? { active_session: SESSION, generation: 1 }
      : path.endsWith('/engines') ? { engines: [{ engine_id: 'visual_stereo', available_now: true, tasks: ['mapping'] }] }
        : path.endsWith('/packages') ? { packages: [] } : {};
    return route.fulfill({ json });
  });
  await page.routeWebSocket('**/api/v1/ws/slam*', ws => {
    sockets.add(ws);
    ws.onClose(() => sockets.delete(ws));
  });
  const send = options => { for (const ws of sockets) ws.send(JSON.stringify(frame(++sequence, options))); };
  await page.goto('/#mapping');
  await expect(page.locator('#slamSessionState')).toHaveText('MAPPING');
  await expect.poll(() => sockets.size).toBe(1);
  // Observe the real scene through its public view method; do not change data.
  await page.evaluate(() => {
    const original = window.RobotScene3D.prototype.fitToPointCloud;
    window.RobotScene3D.prototype.fitToPointCloud = function (...args) {
      if (this.canvas.id === 'slamGlobalCanvas') window.mapViewScene = this;
      return original.apply(this, args);
    };
  });
  return { send, mutations };
}

test('map full FIT, main-area FIT and pose center only change the displayed view', async ({ page }) => {
  if (process.env.MAP_VIEW_CAPTURE) await page.setViewportSize({ width: 1440, height: 1600 });
  const { send, mutations } = await fixture(page);
  await expect(page.locator('#slamFit')).toBeDisabled();
  await expect(page.locator('#slamFitMain')).toBeDisabled();
  await expect(page.locator('#slamCenterPose')).toBeDisabled();
  send();
  await expect(page.locator('#slamFitMain')).toBeEnabled();
  await page.locator('#slamFit').click();
  const original = await page.evaluate(() => ({ points: Array.from(window.mapViewScene.cloud.points),
    bounds: window.mapViewScene.cloud.bounds, distance: window.mapViewScene.camera.distance }));
  if (process.env.MAP_VIEW_CAPTURE) await page.locator('.slam-views').screenshot({ path: `${process.env.MAP_VIEW_CAPTURE}/map-full-fit.png` });
  await page.locator('#slamFitMain').click();
  const mainDistance = await page.evaluate(() => window.mapViewScene.camera.distance);
  expect(mainDistance).toBeLessThan(original.distance / 20);
  await expect(page.locator('#slamFitMain')).toHaveAttribute('title', /2.*98/);
  if (process.env.MAP_VIEW_CAPTURE) await page.locator('.slam-views').screenshot({ path: `${process.env.MAP_VIEW_CAPTURE}/map-main-fit.png` });
  send();
  await expect(page.locator('#slamCenterPose')).toBeEnabled();
  await page.locator('#slamCenterPose').click();
  const after = await page.evaluate(() => ({ points: Array.from(window.mapViewScene.cloud.points),
    bounds: window.mapViewScene.cloud.bounds, camera: window.mapViewScene.camera }));
  expect(after.camera.target).toEqual([1, 0.5, 0.4]);
  expect(after.camera.distance).toBe(mainDistance);
  expect(after.points).toEqual(original.points);
  expect(after.bounds).toEqual(original.bounds);
  await page.locator('#slamFit').click();
  expect(await page.evaluate(() => window.mapViewScene.camera.distance)).toBe(original.distance);
  expect(mutations).toEqual([]);
});

test('map view actions disable on absent data and pose; stale snapshots keep only FIT', async ({ page }) => {
  const { send, mutations } = await fixture(page);
  send();
  await expect(page.locator('#slamCenterPose')).toBeEnabled();
  await expect(page.locator('#slamFitMain')).toBeEnabled();
  await expect(page.locator('#slamCenterPose')).toBeDisabled({ timeout: 5000 });
  await expect(page.locator('#slamFit')).toBeEnabled();
  await expect(page.locator('#slamFitMain')).toBeEnabled();
  send({ empty: true, pose: false });
  await expect(page.locator('#slamFit')).toBeDisabled();
  await expect(page.locator('#slamFitMain')).toBeDisabled();
  await expect(page.locator('#slamCenterPose')).toBeDisabled();
  expect(mutations).toEqual([]);
});
