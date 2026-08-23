import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

async function openDashboard(page, backendOptions = {}, hash = 'overview') {
  const backend = await installDashboardBackend(page, backendOptions);
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto(`/#${hash}`);
  await expect(page.locator('#pageTitle')).not.toHaveText('');
  return backend;
}

test('offline viewer keeps saved maps available while live telemetry fails closed', async ({ page }) => {
  await openDashboard(page, { online: false }, 'overview');
  await expect(page.locator('#connectionLabel')).toContainText('연결 끊김');
  await expect(page.locator('#batteryMetric')).toHaveText('OFFLINE');
  await page.locator('[data-nav="maps"]').click();
  await expect(page.locator('#savedMapCount')).toHaveText('1 map');
  await page.locator('.saved-map-item').first().click();
  await expect(page.locator('#savedMapTitle')).toContainText('e2e_static_map');
});

test('camera and pointcloud reconnect, then release transports on page switch', async ({ page }) => {
  const backend = await openDashboard(page, { closeFirstSockets: ['camera', 'pointcloud'] }, 'sensors');
  await expect.poll(() => backend.state.wsConnections.camera).toBeGreaterThanOrEqual(2);
  await page.locator('[data-nav="overview"]').click();
  await expect.poll(() => backend.state.wsCloses.camera).toBeGreaterThanOrEqual(1);

  backend.state.wsConnections.pointcloud = 0;
  backend.state.wsCloses.pointcloud = 0;
  await page.locator('[data-nav="mapping"]').click();
  await expect.poll(() => backend.state.wsConnections.pointcloud).toBeGreaterThanOrEqual(2);
  await expect(page.locator('#mappingSaveButton')).toBeDisabled();
  await page.locator('[data-nav="overview"]').click();
  await expect.poll(() => backend.state.wsCloses.pointcloud).toBeGreaterThanOrEqual(1);
});

test('mapping start, save and stop preserve one mutation per operator action', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'mapping');
  await expect(page.locator('#mappingStartButton')).toBeEnabled();
  await page.locator('#mappingStartButton').click();
  await expect.poll(() => backend.mutations('/api/v1/mapping/start').length).toBe(1);
  await expect(page.locator('#mappingPipelineLabel')).toContainText('RUNNING');

  await page.waitForTimeout(3_600);
  await expect(page.locator('#mappingSaveButton')).toBeEnabled();
  await page.locator('#mappingSaveButton').click();
  await expect.poll(() => backend.mutations('/api/v1/mapping/save').length).toBe(1);
  backend.state.mapping.operation = { state: 'idle', kind: '', job_id: null, error: '', files: [] };
  await expect(page.locator('#mappingStopButton')).toBeEnabled();
  await page.locator('#mappingStopButton').click();
  await expect.poll(() => backend.mutations('/api/v1/mapping/stop').length).toBe(1);
});

test('navigation starts with pinned revisions, exposes active progress, and cancels once', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'navigation');
  await expect(page.locator('#navigationStartButton')).toBeEnabled();
  await page.locator('#navigationStartButton').click();
  await expect.poll(() => backend.mutations('/api/v1/navigation/start').length).toBe(1);
  const startBody = backend.mutations('/api/v1/navigation/start')[0].body;
  expect(startBody).toEqual({
    map_id: backend.mapId,
    map_revision: backend.mapRevision,
    parameters_revision: backend.parameterRevision,
  });
  await expect(page.locator('#navigationPipelineState')).toContainText('RUNNING');
  await expect(page.locator('#navigationCancelGoal')).toBeEnabled();
  await page.locator('#navigationCancelGoal').dblclick();
  await expect.poll(() => backend.mutations('/api/v1/navigation/cancel').length).toBe(1);
});

test('an active map revision conflict blocks navigation pose and goal controls', async ({ page }) => {
  const backend = await installDashboardBackend(page);
  backend.state.navigation = {
    ...backend.state.navigation,
    pipeline: { state: 'running', job_id: 'f'.repeat(32), error: '' },
    map: { id: backend.mapId, revision: '9'.repeat(64) },
    localization: { state: 'localized', pose: { x: 0, y: 0, yaw: 0 } },
    goal: { state: 'idle', goal_id: null },
    safety: { can_start: false, can_stop: true, can_set_initial_pose: true, can_send_goal: true, blockers: [] },
  };
  await page.goto('/#navigation');
  await expect(page.locator('#navigationSafetyTitle')).toHaveText('ACTIVE MAP REVISION MISMATCH');
  await expect(page.locator('#navigationInitialPoseTool')).toBeDisabled();
  await expect(page.locator('#navigationGoalPoseTool')).toBeDisabled();
});

test('dataset start/finalize is lifecycle-owned and duplicate clicks do not duplicate mutations', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'sensors');
  await expect(page.locator('#datasetCaptureStart')).toBeEnabled();
  await page.locator('#datasetCaptureStart').dblclick();
  await expect.poll(() => backend.mutations('/api/v1/datasets/capture/start').length).toBe(1);
  await expect(page.locator('#datasetCaptureState')).toContainText('CAPTURING');
  await expect(page.locator('#datasetCaptureStop')).toBeEnabled();
  await page.locator('#datasetCaptureStop').dblclick();
  await expect.poll(() => backend.mutations('/api/v1/datasets/capture/stop').length).toBe(1);
  await expect(page.locator('#datasetCaptureState')).toContainText('COMPLETE');

  expect(await page.evaluate(() => window.RobotScopeDatasetCapture.snapshot().lifecycle.active)).toBe(true);
  await page.locator('[data-nav="overview"]').click();
  await expect.poll(() => page.evaluate(() => window.RobotScopeDatasetCapture.snapshot().lifecycle.active)).toBe(false);
  const destroyed = await page.evaluate(() => {
    window.RobotScopeDatasetCapture.destroy();
    return window.RobotScopeDatasetCapture.snapshot();
  });
  expect(destroyed.lifecycle).toEqual({ started: true, active: false, destroyed: true });
  expect(destroyed.sessions).toEqual([]);
  expect(destroyed.selectedSessionId).toBe('');
  await page.locator('[data-nav="sensors"]').click();
  await page.locator('#datasetCaptureStart').click();
  await page.waitForTimeout(100);
  expect(backend.mutations('/api/v1/datasets/capture/start')).toHaveLength(1);
});

test('software E-stop remains latched until explicit local confirmation clears it', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'controls');
  await page.locator('#softwareEstopButton').click();
  await expect.poll(() => backend.mutations('/api/v1/control/stop').length).toBe(1);
  await expect(page.locator('#estopClearButton')).toBeDisabled();
  await page.locator('#estopClearConfirm').check();
  await expect(page.locator('#estopClearButton')).toBeEnabled();
  await page.locator('#estopClearButton').dblclick();
  await expect.poll(() => backend.mutations('/api/v1/control/estop/clear').length).toBe(1);
  expect(backend.mutations('/api/v1/control/estop/clear')[0].body).toEqual({ confirmed: true });
});

test('service lifecycle blockers remain server-authoritative in the browser', async ({ page }) => {
  const backend = await openDashboard(page, { serviceBlocked: true }, 'settings');
  await expect(page.locator('#serviceLifecycleConfirm')).toBeDisabled();
  await expect(page.locator('#serviceRestartButton')).toBeDisabled();
  await expect(page.locator('#serviceStopButton')).toBeDisabled();
  await expect(page.locator('#serviceLifecycleMessage')).toContainText('매핑');
  expect(backend.mutations('/api/v1/system/service/restart')).toHaveLength(0);
});

test('cross-origin browser WebSocket handshakes are rejected before acceptance', async ({ page, request }) => {
  await page.goto('http://127.0.0.1:4174/');
  const outcome = await page.evaluate(() => new Promise((resolve) => {
    const socket = new WebSocket('ws://127.0.0.1:4173/api/v1/ws/pose');
    socket.onopen = () => resolve('opened');
    socket.onerror = () => resolve('rejected');
    setTimeout(() => resolve('timeout'), 2_000);
  }));
  expect(outcome).toBe('rejected');
  const response = await request.get('http://127.0.0.1:4174/ws-rejections');
  expect((await response.json()).rejected).toBeGreaterThanOrEqual(1);
});
