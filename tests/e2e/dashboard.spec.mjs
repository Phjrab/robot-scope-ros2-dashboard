import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

async function openDashboard(page, backendOptions = {}, hash = 'overview') {
  const backend = await installDashboardBackend(page, backendOptions);
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto(`/#${hash}`);
  await expect(page.locator('#pageTitle')).not.toHaveText('');
  return backend;
}

async function enterLayoutEdit(page) {
  await page.locator('[data-cockpit-layout-action="edit"]').click();
  await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-layout-mode', 'layout-edit');
}

async function pressSyntheticGamepadButton(page, index, holdMs = 90) {
  await page.evaluate((button) => window.__syntheticGamepad.setButton(button, true), index);
  await page.waitForTimeout(holdMs);
  await page.evaluate((button) => window.__syntheticGamepad.setButton(button, false), index);
  await page.waitForTimeout(70);
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

test('Sensors camera observability shows Wi-Fi, source, transport, decode and clock domain', async ({ page }) => {
  await openDashboard(page, {}, 'sensors');
  await page.locator('#cameraPrimarySource').selectOption('realsense_color');
  await expect(page.locator('#cameraWifiStatus')).toHaveText('LIVE');
  await expect(page.locator('#cameraWifiDetail')).toContainText('-54 dBm');
  await expect(page.locator('#cameraSourceHealthStatus')).toHaveText('LIVE');
  await expect(page.locator('#cameraSourceHealthDetail')).toContainText('640×480');
  await expect(page.locator('#cameraTransportHealthStatus')).toHaveText('LIVE');
  await expect(page.locator('#cameraTransportHealthDetail')).toContainText('4.125 Mbps');
  await expect(page.locator('#cameraDecodeHealthStatus')).toHaveText('LIVE');
  await expect(page.locator('#cameraDecodeHealthDetail')).toContainText('OK ');
  await expect(page.locator('#cameraLatencyDomain')).toContainText('UNVERIFIED_CLOCK_DOMAIN');
});

test('Cockpit enter, leave, resize, and 20 reentries keep one scene and one PointCloud owner', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'cockpit');
  await expect(page.locator('#cockpitWorkspace')).toBeVisible();
  await expect(page.locator('#cockpitSceneCanvas')).toBeVisible();
  await expect(page.locator('#cockpitPointcloudStatus')).toHaveText('WAITING');
  await expect.poll(() => backend.state.wsConnections.pointcloud).toBe(1);

  await page.setViewportSize({ width: 1180, height: 760 });
  const canvasSize = await page.locator('#cockpitSceneCanvas').evaluate((canvas) => ({
    clientWidth: canvas.clientWidth,
    clientHeight: canvas.clientHeight,
    width: canvas.width,
    height: canvas.height,
  }));
  expect(canvasSize.clientWidth).toBeGreaterThan(0);
  expect(canvasSize.clientHeight).toBeGreaterThan(0);
  expect(canvasSize.width).toBeGreaterThan(0);
  expect(canvasSize.height).toBeGreaterThan(0);

  for (let index = 0; index < 20; index += 1) {
    await page.locator('[data-nav="overview"]').click();
    await expect(page.locator('#cockpitWorkspace')).toBeHidden();
    await page.locator('[data-nav="cockpit"]').click();
    await expect(page.locator('#cockpitWorkspace')).toBeVisible();
  }

  const cockpit = await page.evaluate(() => window.RobotScopeCockpit.snapshot());
  expect(cockpit.workspace.active).toBe(true);
  expect(cockpit.workspace.scene.rendererCount).toBe(1);
  expect(cockpit.workspace.scene.peakRenderers).toBe(1);
  expect(cockpit.workspace.scene.starts - cockpit.workspace.scene.stops).toBe(1);
  expect(cockpit.pointcloud.activeConsumers).toEqual(['cockpit']);
  expect(cockpit.pointcloud.connected).toBe(true);
  await expect.poll(() => backend.state.wsConnections.pointcloud).toBe(21);
  await expect.poll(() => backend.state.wsCloses.pointcloud).toBeGreaterThanOrEqual(20);
});

test('Cockpit point quality switches LOW, MEDIUM, HIGH and exposes adaptive scene controls', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'cockpit');
  await expect(page.locator('#cockpitPointQuality')).toHaveValue('low');
  await page.locator('#cockpitPointQuality').selectOption('medium');
  await expect.poll(() => backend.mutations('/api/v1/pointcloud/settings').at(-1)?.body?.max_points).toBe(30_000);
  await page.locator('#cockpitPointQuality').selectOption('high');
  await expect.poll(() => backend.mutations('/api/v1/pointcloud/settings').at(-1)?.body?.max_points).toBe(60_000);
  await expect.poll(async () => (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.scene.quality.mode).toBe('high');
  await expect(page.locator('#cockpitPointMetrics')).toContainText('HIGH · 60K');

  await page.locator('#cockpitPointAdaptive').click();
  await expect(page.locator('#cockpitPointAdaptive')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#cockpitHeightColor').click();
  await expect(page.locator('#cockpitHeightColor')).toHaveAttribute('aria-pressed', 'false');
  await page.locator('#cockpitNearField').click();
  await expect(page.locator('#cockpitNearField')).toHaveAttribute('aria-pressed', 'false');
});

test('Cockpit map panel shows revision-pinned localization and toggles the bounded 3D overlay', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'cockpit');
  await enterLayoutEdit(page);
  await page.locator('.cockpit-launcher-item[data-panel-type="placeholder.map"]').click();
  const panel = page.locator('[data-panel-id="placeholder-map"]');
  backend.state.navigation = {
    ...backend.state.navigation,
    pipeline: { state: 'running', job_id: 'f'.repeat(32), error: '' },
    map: { id: backend.mapId, revision: backend.mapRevision },
    localization: { state: 'localized', pose: { x: 0.5, y: 0.5, yaw: 0.2, frame_id: 'map' } },
    localization_health: { state: 'READY', reason_code: 'HEALTHY', metrics: { odometry_age_s: 0.05, tf_age_s: 0.08 } },
    readiness: { ...backend.state.navigation.readiness, map: true, odometry: true, tf: true, localization: true },
    path: [{ x: 0.25, y: 0.25 }, { x: 0.5, y: 0.5 }],
    goal: { state: 'active', goal_id: '1'.repeat(32), pose: { x: 0.75, y: 0.75, yaw: 0 }, message: '' },
  };
  await page.locator('#refreshButton').click();
  await expect(panel.locator('.cockpit-map-panel')).toBeVisible();
  await expect(panel.locator('.cockpit-map-header strong')).toHaveText('LIVE');
  await expect(panel.locator('.cockpit-map-header span')).toContainText('e2e_static_map');
  await expect(panel.locator('.cockpit-map-header span')).toContainText(backend.mapId.slice(0, 8));
  await expect(panel.locator('.cockpit-map-metrics')).toContainText('LOCALIZED / READY');

  await panel.locator('[data-panel-action="focus"]').click();
  await expect(panel).toHaveAttribute('data-mode', 'focus');
  await expect(page.locator('#cockpitSafetyHud')).toBeVisible();
  await expect(page.locator('#cockpitMapOverlay')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#cockpitMapOverlay').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#cockpitMapOverlay')).toHaveAttribute('aria-pressed', 'false');
  await expect.poll(async () => (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.scene.mapOverlay.enabled).toBe(false);

  backend.state.navigation = { ...backend.state.navigation, map: { id: backend.mapId, revision: 'd'.repeat(64) } };
  await expect(panel.locator('.cockpit-map-header strong')).toHaveText('CONFLICT', { timeout: 3_000 });
  await expect(panel.locator('.cockpit-map-warning')).toContainText('REVISION CONFLICT');
  const cockpit = await page.evaluate(() => window.RobotScopeCockpit.snapshot());
  expect(cockpit.workspace.scene.mapOverlay.pathPoints).toBe(0);
  expect(cockpit.workspace.scene.mapOverlay.markerCount).toBe(0);
  expect(backend.mutations('/api/v1/navigation/start')).toHaveLength(0);
  expect(backend.mutations('/api/v1/navigation/goal')).toHaveLength(0);
});

test('Cockpit manual to Nav2 to explicit takeover stays mutually exclusive and never auto-arms', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'cockpit');
  await enterLayoutEdit(page);
  await page.locator('.cockpit-launcher-item[data-panel-type="navigation.main"]').click();
  const panel = page.locator('[data-panel-id="navigation-main"]');
  await expect(panel.locator('.cockpit-navigation-panel')).toBeVisible();
  backend.state.control.lease = { active: true, bound: true, source: 'keyboard' };
  await page.locator('#refreshButton').click();
  await expect(panel.locator('[data-navigation-action="start"]')).toBeDisabled();
  await expect(panel.locator('.cockpit-navigation-metrics')).toContainText('LEASE ACTIVE · BLOCKED');

  backend.state.control.lease = { active: false, bound: false, source: null };
  await page.locator('#refreshButton').click();
  await expect(panel.locator('[data-navigation-action="start"]')).toBeEnabled();
  await panel.locator('[data-navigation-action="start"]').click();
  await expect.poll(() => backend.mutations('/api/v1/navigation/start').length).toBe(1);
  await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-layout-mode', 'operate');
  await expect(panel.locator('[data-navigation-action="takeover"]')).toBeEnabled();

  await panel.locator('[data-navigation-action="takeover"]').click();
  await expect.poll(() => backend.mutations('/api/v1/navigation/cancel').length).toBe(1);
  await expect.poll(() => backend.mutations('/api/v1/navigation/stop').length).toBe(1);
  await expect(panel.locator('.cockpit-navigation-takeover strong')).toHaveText('TAKEOVER READY_TO_ARM');
  await expect(panel.locator('.cockpit-navigation-takeover small')).toContainText('별도로 ARM하세요');
  expect(backend.mutations('/api/v1/control/arm')).toHaveLength(0);
});

test('Cockpit runs a server-owned two-waypoint mission and restores it after reload', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'cockpit');
  backend.state.annotations.points.push({ id: backend.secondAnnotationId, type: 'INSPECTION_POINT', name: 'E2E Inspect', pose: { x: 0.75, y: 0.5, yaw: 0 } });
  await enterLayoutEdit(page);
  await page.locator('.cockpit-launcher-item[data-panel-type="navigation.main"]').click();
  await page.locator('.cockpit-launcher-item[data-panel-type="mission.main"]').click();
  const navigationPanel = page.locator('[data-panel-id="navigation-main"]');
  const missionPanel = page.locator('[data-panel-id="mission-main"]');
  await expect(missionPanel.locator('.cockpit-mission-panel')).toBeVisible();
  await page.locator('.cockpit-launcher-item[data-panel-type="navigation.main"]').click();
  await navigationPanel.locator('[data-navigation-action="start"]').click();
  await expect.poll(() => backend.mutations('/api/v1/navigation/start').length).toBe(1);
  backend.state.navigation.goal = { state: 'idle', goal_id: null };
  backend.state.navigation.safety.can_send_goal = true;

  await expect(missionPanel.locator('[data-mission-draft-id]')).toHaveCount(2);
  await missionPanel.locator('[data-mission-draft-id]').nth(0).click();
  await missionPanel.locator('[data-mission-draft-id]').nth(1).click();
  await missionPanel.locator('[aria-label="Mission label"]').fill('E2E competition route');
  await missionPanel.locator('[data-mission-action="create"]').click();
  await expect.poll(() => backend.mutations('/api/v1/missions').length).toBe(1);
  await expect(missionPanel.locator('.cockpit-mission-header strong')).toHaveText('MISSION READY');
  await missionPanel.locator('[data-mission-action="start"]').click();
  await expect.poll(() => backend.mutations(`/api/v1/missions/${'9'.repeat(32)}/start`).length).toBe(1);
  await expect(missionPanel.locator('.cockpit-mission-header strong')).toHaveText('MISSION RUNNING');
  expect(backend.state.control.lease.source).toBe('navigation');
  expect(backend.mutations('/api/v1/control/arm')).toHaveLength(0);

  backend.completeMissionWaypoint();
  await expect(missionPanel.locator('.cockpit-mission-route')).toContainText('2. E2E Inspect · RUNNING');
  backend.completeMissionWaypoint();
  await expect(missionPanel.locator('.cockpit-mission-header strong')).toHaveText('MISSION COMPLETED');
  await navigationPanel.locator('[data-navigation-action="stop"]').click();
  await expect.poll(() => backend.mutations('/api/v1/navigation/stop').length).toBe(1);

  await page.reload();
  await enterLayoutEdit(page);
  await page.locator('.cockpit-launcher-item[data-panel-type="mission.main"]').click();
  const restored = page.locator('[data-panel-id="mission-main"]');
  await expect(restored.locator('.cockpit-mission-header strong')).toHaveText('MISSION COMPLETED');
  await expect(restored.locator('.cockpit-mission-route')).toContainText('E2E Home · COMPLETED');
  await expect(restored.locator('.cockpit-mission-route')).toContainText('E2E Inspect · COMPLETED');
});

test('Cockpit mission pause, failure retry, and skips remain explicit and fail closed', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'cockpit');
  backend.state.annotations.points.push({ id: backend.secondAnnotationId, type: 'INSPECTION_POINT', name: 'E2E Inspect', pose: { x: 0.75, y: 0.5, yaw: 0 } });
  await enterLayoutEdit(page);
  await page.locator('.cockpit-launcher-item[data-panel-type="navigation.main"]').click();
  await page.locator('.cockpit-launcher-item[data-panel-type="mission.main"]').click();
  const navigationPanel = page.locator('[data-panel-id="navigation-main"]');
  const missionPanel = page.locator('[data-panel-id="mission-main"]');
  await page.locator('.cockpit-launcher-item[data-panel-type="navigation.main"]').click();
  await navigationPanel.locator('[data-navigation-action="start"]').click();
  await expect.poll(() => backend.mutations('/api/v1/navigation/start').length).toBe(1);
  await page.locator('.cockpit-launcher-item[data-panel-type="mission.main"]').click();
  await page.locator('#cockpitSensorLauncher .cockpit-launcher-toggle').click();
  backend.state.navigation.goal = { state: 'idle', goal_id: null };
  backend.state.navigation.safety.can_send_goal = true;

  await missionPanel.locator('[data-mission-draft-id]').nth(0).click();
  await missionPanel.locator('[data-mission-draft-id]').nth(1).click();
  await missionPanel.locator('[aria-label="Mission label"]').fill('CWP-12 recovery route');
  await missionPanel.locator('[data-mission-action="create"]').click();
  await missionPanel.locator('[data-mission-action="start"]').click();
  const missionId = '9'.repeat(32);
  await expect(missionPanel.locator('.cockpit-mission-header strong')).toHaveText('MISSION RUNNING');

  await missionPanel.locator('[data-mission-action="pause"]').click();
  await expect.poll(() => backend.mutations(`/api/v1/missions/${missionId}/pause`).length).toBe(1);
  await expect(missionPanel.locator('.cockpit-mission-header strong')).toHaveText('MISSION PAUSED');
  expect(backend.state.navigation.goal.state).toBe('canceled');
  await missionPanel.locator('[data-mission-action="resume"]').click();
  await expect(missionPanel.locator('.cockpit-mission-header strong')).toHaveText('MISSION RUNNING');

  const mission = backend.state.missions[0];
  mission.state = 'failed'; mission.outcome = 'waypoint_failed'; mission.error = 'navigation_goal_failed';
  mission.ownership_active = false; mission.waypoints[mission.current_index].status = 'failed';
  backend.state.activeMissionId = null;
  backend.state.navigation.goal = { state: 'failed', goal_id: null };
  await expect(missionPanel.locator('.cockpit-mission-header strong')).toHaveText('MISSION FAILED');
  await expect(missionPanel.locator('[data-mission-action="retry"]')).toBeEnabled();
  expect(backend.mutations(`/api/v1/missions/${missionId}/retry`)).toHaveLength(0);

  await missionPanel.locator('[data-mission-action="retry"]').click();
  await expect.poll(() => backend.mutations(`/api/v1/missions/${missionId}/retry`).length).toBe(1);
  await expect(missionPanel.locator('.cockpit-mission-header strong')).toHaveText('MISSION RUNNING');
  await missionPanel.locator('[data-mission-action="skip"]').click();
  await expect(missionPanel.locator('.cockpit-mission-route')).toContainText('E2E Home · SKIPPED');
  await expect(missionPanel.locator('.cockpit-mission-route')).toContainText('E2E Inspect · RUNNING');
  await missionPanel.locator('[data-mission-action="skip"]').click();
  await expect(missionPanel.locator('.cockpit-mission-header strong')).toHaveText('MISSION COMPLETED');
  expect(backend.mutations(`/api/v1/missions/${missionId}/skip`)).toHaveLength(2);
  expect(backend.mutations('/api/v1/control/arm')).toHaveLength(0);
});

test('Cockpit panels drag, resize, focus, lock, close, and recover without orbiting the scene', async ({ page }) => {
  await openDashboard(page, {}, 'cockpit');
  await enterLayoutEdit(page);
  for (const type of ['camera.go2-front', 'placeholder.map', 'placeholder.controller']) {
    await page.locator(`.cockpit-launcher-item[data-panel-type="${type}"]`).click();
  }
  const panels = page.locator('.cockpit-floating-panel:not([hidden])');
  await expect(panels).toHaveCount(3);
  const telemetry = page.locator('[data-panel-id="camera-go2-front"]');
  const spatial = page.locator('[data-panel-id="placeholder-map"]');
  const mission = page.locator('[data-panel-id="placeholder-controller"]');

  const beforeDrag = await page.evaluate(() => window.RobotScopeCockpit.snapshot());
  const telemetryBefore = beforeDrag.workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  const titlebar = telemetry.locator('.cockpit-panel-titlebar');
  const titleBox = await titlebar.boundingBox();
  await page.mouse.move(titleBox.x + 25, titleBox.y + 25);
  await page.mouse.down();
  await page.mouse.move(titleBox.x + 125, titleBox.y + 85, { steps: 4 });
  await page.mouse.up();
  const afterDrag = await page.evaluate(() => window.RobotScopeCockpit.snapshot());
  const telemetryAfter = afterDrag.workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  expect(telemetryAfter.x).toBeGreaterThan(telemetryBefore.x);
  expect(telemetryAfter.y).toBeGreaterThan(telemetryBefore.y);
  expect(afterDrag.workspace.scene.camera).toEqual(beforeDrag.workspace.scene.camera);
  expect(telemetryAfter.zIndex).toBe(Math.max(...afterDrag.workspace.panels.panels.filter((panel) => panel.visible).map((panel) => panel.zIndex)));

  const spatialBefore = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'placeholder-map');
  const resizeHandle = spatial.locator('[data-panel-resize="se"]');
  const resizeBox = await resizeHandle.boundingBox();
  await page.mouse.move(resizeBox.x + resizeBox.width / 2, resizeBox.y + resizeBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(resizeBox.x + 90, resizeBox.y + 70, { steps: 3 });
  await page.mouse.up();
  const spatialAfter = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'placeholder-map');
  expect(spatialAfter.width).toBeGreaterThan(spatialBefore.width);
  expect(spatialAfter.height).toBeGreaterThan(spatialBefore.height);

  await spatial.locator('[data-panel-action="pin"]').click();
  await expect(spatial.locator('[data-panel-action="pin"]')).toHaveAttribute('aria-pressed', 'true');
  await spatial.locator('[data-panel-action="lock"]').click();
  const lockedBefore = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'placeholder-map');
  const lockedTitleBox = await spatial.locator('.cockpit-panel-titlebar').boundingBox();
  await page.mouse.move(lockedTitleBox.x + 20, lockedTitleBox.y + 20);
  await page.mouse.down();
  await page.mouse.move(lockedTitleBox.x + 120, lockedTitleBox.y + 80);
  await page.mouse.up();
  const lockedAfter = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'placeholder-map');
  expect({ x: lockedAfter.x, y: lockedAfter.y }).toEqual({ x: lockedBefore.x, y: lockedBefore.y });

  const missionBeforeCompact = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'placeholder-controller');
  await mission.locator('[data-panel-action="compact"]').click();
  await expect(mission).toHaveAttribute('data-mode', 'compact');
  await mission.locator('[data-panel-action="compact"]').click();
  const missionBeforeFocus = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'placeholder-controller');
  expect({ x: missionBeforeFocus.x, y: missionBeforeFocus.y, width: missionBeforeFocus.width, height: missionBeforeFocus.height }).toEqual({
    x: missionBeforeCompact.x, y: missionBeforeCompact.y, width: missionBeforeCompact.width, height: missionBeforeCompact.height,
  });
  await mission.locator('[data-panel-action="focus"]').click();
  await expect(mission).toHaveAttribute('data-mode', 'focus');
  await mission.locator('[data-panel-action="focus"]').click();
  const missionRestored = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'placeholder-controller');
  expect({ x: missionRestored.x, y: missionRestored.y, width: missionRestored.width, height: missionRestored.height }).toEqual({
    x: missionBeforeFocus.x, y: missionBeforeFocus.y, width: missionBeforeFocus.width, height: missionBeforeFocus.height,
  });

  await page.locator('.cockpit-launcher-item[data-panel-type="camera.go2-front"]').click();
  await telemetry.locator('[data-panel-action="close"]').click();
  await expect(panels).toHaveCount(2);
  await page.locator('.cockpit-launcher-item[data-panel-type="camera.go2-front"]').click();
  await expect(panels).toHaveCount(3);

  await page.setViewportSize({ width: 720, height: 640 });
  await expect.poll(() => page.evaluate(() => {
    const layer = document.querySelector('#cockpitPanelLayer');
    return window.RobotScopeCockpit.snapshot().workspace.panels.panels.filter((panel) => panel.visible).every((panel) =>
      panel.x >= 12 && panel.y >= 12 && panel.x + panel.width <= layer.clientWidth - 12 && panel.y + panel.height <= layer.clientHeight - 90);
  })).toBe(true);
  const recovered = await page.evaluate(() => ({
    width: document.querySelector('#cockpitPanelLayer').clientWidth,
    height: document.querySelector('#cockpitPanelLayer').clientHeight,
    panels: window.RobotScopeCockpit.snapshot().workspace.panels.panels.filter((panel) => panel.visible),
  }));
  for (const panel of recovered.panels) {
    expect(panel.x).toBeGreaterThanOrEqual(12);
    expect(panel.y).toBeGreaterThanOrEqual(12);
    expect(panel.x + panel.width).toBeLessThanOrEqual(recovered.width - 12);
    expect(panel.y + panel.height).toBeLessThanOrEqual(recovered.height - 90);
    expect(panel.zIndex).toBeLessThan(25);
  }
});

test('Cockpit Sensor Launcher is keyboard accessible and snap, dock, tile, and cascade stay bounded', async ({ page }) => {
  await openDashboard(page, {}, 'cockpit');
  await enterLayoutEdit(page);
  const toggle = page.locator('.cockpit-launcher-toggle');
  const body = page.locator('#cockpitLauncherBody');
  const cameraButton = page.locator('.cockpit-launcher-item[data-panel-type="camera.go2-front"]');
  const realsenseButton = page.locator('.cockpit-launcher-item[data-panel-type="camera.realsense-color"]');
  const mapButton = page.locator('.cockpit-launcher-item[data-panel-type="placeholder.map"]');
  const controllerButton = page.locator('.cockpit-launcher-item[data-panel-type="placeholder.controller"]');
  await expect(page.locator('.cockpit-launcher-item')).toHaveCount(6);
  await expect(cameraButton).toContainText('360×240 · MIN 280×170');

  await toggle.click();
  await expect(body).toBeHidden();
  await toggle.focus();
  await page.keyboard.press('ArrowDown');
  await expect(body).toBeVisible();
  await expect(cameraButton).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('[data-panel-id="camera-go2-front"]')).toHaveCount(1);
  await expect(cameraButton).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Enter');
  await expect(page.locator('[data-panel-id="camera-go2-front"]')).toHaveCount(1);
  await page.keyboard.press('ArrowDown');
  await expect(realsenseButton).toBeFocused();
  await page.keyboard.press('Enter');
  await page.keyboard.press('ArrowDown');
  await expect(mapButton).toBeFocused();
  await page.keyboard.press('Enter');
  await page.keyboard.press('End');
  await expect(controllerButton).toBeFocused();
  await page.keyboard.press('Enter');
  await page.keyboard.press('Escape');
  await expect(body).toBeHidden();
  await expect(toggle).toBeFocused();
  await toggle.press('ArrowDown');

  await cameraButton.click();
  const camera = page.locator('[data-panel-id="camera-go2-front"]');
  const floatingBeforeDock = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  await page.locator('[data-layout-action="dock-left"]').click();
  let cameraState = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  expect(cameraState.dock).toBe('left');
  expect(cameraState.x).toBe(12);
  await page.locator('[data-layout-action="undock"]').click();
  cameraState = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  expect({ x: cameraState.x, y: cameraState.y, width: cameraState.width, height: cameraState.height }).toEqual({
    x: floatingBeforeDock.x, y: floatingBeforeDock.y, width: floatingBeforeDock.width, height: floatingBeforeDock.height,
  });

  const titleBox = await camera.locator('.cockpit-panel-titlebar').boundingBox();
  await page.mouse.move(titleBox.x + 24, titleBox.y + 24);
  await page.mouse.down();
  await page.mouse.move(37, titleBox.y + 24, { steps: 3 });
  await expect(page.locator('#cockpitSnapPreview')).toBeVisible();
  await page.mouse.up();
  cameraState = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  expect(cameraState.x).toBe(12);

  const snappedTitleBox = await camera.locator('.cockpit-panel-titlebar').boundingBox();
  await page.keyboard.down('Alt');
  await page.mouse.move(snappedTitleBox.x + 24, snappedTitleBox.y + 24);
  await page.mouse.down();
  await page.mouse.move(snappedTitleBox.x + 31, snappedTitleBox.y + 24);
  await page.mouse.up();
  await page.keyboard.up('Alt');
  cameraState = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  expect(cameraState.x).toBe(19);

  await page.locator('.cockpit-layout-controls select').selectOption('24');
  expect((await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.snapOptions.gridSize).toBe(24);
  for (const action of ['split', 'tile', 'cascade', 'recover']) {
    await page.locator(`[data-layout-action="${action}"]`).click();
    const snapshot = await page.evaluate(() => ({
      width: document.querySelector('#cockpitPanelLayer').clientWidth,
      height: document.querySelector('#cockpitPanelLayer').clientHeight,
      panels: window.RobotScopeCockpit.snapshot().workspace.panels.panels.filter((panel) => panel.visible),
    }));
    for (const panel of snapshot.panels) {
      expect(panel.x).toBeGreaterThanOrEqual(12);
      expect(panel.y).toBeGreaterThanOrEqual(12);
      expect(panel.x + panel.width).toBeLessThanOrEqual(snapshot.width - 12);
      expect(panel.y + panel.height).toBeLessThanOrEqual(snapshot.height - 90);
    }
  }
});

test('Cockpit camera panels share catalog-owned streams through dual open, focus swap, resize, compact, stale, and close', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'cockpit');
  await enterLayoutEdit(page);
  const go2Button = page.locator('.cockpit-launcher-item[data-panel-type="camera.go2-front"]');
  const realsenseButton = page.locator('.cockpit-launcher-item[data-panel-type="camera.realsense-color"]');
  await expect(go2Button).toBeEnabled();
  await expect(realsenseButton).toBeEnabled();
  await go2Button.click();
  await realsenseButton.click();

  const go2 = page.locator('[data-panel-id="camera-go2-front"]');
  const realsense = page.locator('[data-panel-id="camera-realsense-color"]');
  await expect(go2.locator('.cockpit-camera-state')).toHaveText('LIVE');
  await expect(realsense.locator('.cockpit-camera-state')).toHaveText('LIVE');
  await expect(realsense.locator('.cockpit-camera-metrics')).toContainText('ROBOT WI-FI');
  await expect(realsense.locator('.cockpit-camera-metrics')).toContainText('LIVE · RSSI -54 dBm');
  await expect(realsense.locator('.cockpit-camera-metrics')).toContainText('4.125 Mbps · 14.8 FPS');
  await expect(realsense.locator('.cockpit-camera-metrics')).toContainText('UNVERIFIED_CLOCK_DOMAIN');
  await expect.poll(() => backend.state.cameraConnectionsBySource.go2_front).toBe(1);
  await expect.poll(() => backend.state.cameraConnectionsBySource.realsense_color).toBe(1);
  await go2Button.click();
  await expect.poll(() => backend.state.cameraConnectionsBySource.go2_front).toBe(1);

  await go2.locator('[data-panel-action="focus"]').click();
  await expect(go2).toHaveAttribute('data-mode', 'focus');
  await go2.locator('[data-panel-action="focus"]').click();
  await realsenseButton.click();
  await realsense.locator('[data-panel-action="focus"]').click();
  await expect(realsense).toHaveAttribute('data-mode', 'focus');
  await expect(go2.locator('.cockpit-camera-state')).toHaveText('LIVE');
  await realsense.locator('[data-panel-action="focus"]').click();

  const resize = go2.locator('[data-panel-resize="se"]');
  const resizeBox = await resize.boundingBox();
  await page.mouse.move(resizeBox.x + resizeBox.width / 2, resizeBox.y + resizeBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(resizeBox.x + 55, resizeBox.y + 35, { steps: 3 });
  await page.mouse.up();
  await expect.poll(() => backend.state.cameraConnectionsBySource.go2_front).toBe(1);

  await go2.locator('[data-panel-action="compact"]').click();
  await expect(go2).toHaveAttribute('data-mode', 'compact');
  await expect.poll(() => backend.state.cameraClosesBySource.go2_front).toBe(1);
  await expect(realsense.locator('.cockpit-camera-state')).toHaveText('LIVE');
  expect(backend.state.cameraClosesBySource.realsense_color).toBe(0);
  await go2.locator('[data-panel-action="compact"]').click();
  await expect(go2.locator('.cockpit-camera-state')).toHaveText('LIVE');
  await expect.poll(() => backend.state.cameraConnectionsBySource.go2_front).toBe(2);

  backend.state.cameraStreaming.realsense_color = false;
  await expect(realsense.locator('.cockpit-camera-state')).toHaveText('STALE', { timeout: 5_000 });
  await expect(realsense.locator('.cockpit-camera-overlay')).toContainText('STALE');
  await expect(realsense.locator('canvas:not(.cockpit-perception-overlay)')).toHaveJSProperty('width', 1);
  await expect(go2.locator('.cockpit-camera-state')).toHaveText('LIVE');

  await realsense.locator('[data-panel-action="close"]').click();
  await expect(realsense).toHaveCount(0);
  await expect.poll(() => backend.state.cameraClosesBySource.realsense_color).toBe(1);
  const demands = await page.evaluate(() => window.RobotScopeCameraStreams.snapshot().demand.sources.map((source) => ({ id: source.id, viewers: source.viewerCount })));
  expect(demands).toEqual([{ id: 'go2_front', viewers: 1 }, { id: 'realsense_color', viewers: 0 }]);
  await expect(go2.locator('.cockpit-camera-state')).toHaveText('LIVE');
});

test('Cockpit disables camera launchers that are absent from the active catalog profile', async ({ page }) => {
  await openDashboard(page, {
    cameraSources: [{ source_id: 'go2_front', id: 'go2_front', label: 'GO2 FRONT', available: true, state: 'ok', transport: 'fake' }],
  }, 'cockpit');
  await enterLayoutEdit(page);
  await expect(page.locator('.cockpit-launcher-item[data-panel-type="camera.go2-front"]')).toBeEnabled();
  const unavailable = page.locator('.cockpit-launcher-item[data-panel-type="camera.realsense-color"]');
  await expect(unavailable).toBeDisabled();
  await expect(unavailable).toContainText('UNAVAILABLE');
});

test('Cockpit starts in Operate, gates layout mutations, and keeps HUD and software STOP above focus panels', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'cockpit');
  const workspace = page.locator('#cockpitWorkspace');
  const hud = page.locator('#cockpitSafetyHud');
  const go2Button = page.locator('.cockpit-launcher-item[data-panel-type="camera.go2-front"]');
  await expect(workspace).toHaveAttribute('data-layout-mode', 'operate');
  await expect(go2Button).toBeDisabled();
  await expect(hud.locator('[data-safety-field="control-source"]')).toHaveText('NONE');
  await expect(hud.locator('[data-safety-field="go2-link"]')).toHaveText('LIVE');
  await expect(hud.locator('[data-safety-field="lowstate"]')).toHaveText('50 ms');
  await expect(hud.locator('[data-safety-field="battery"]')).toHaveText('83%');

  await enterLayoutEdit(page);
  await expect(go2Button).toBeEnabled();
  await go2Button.click();
  const camera = page.locator('[data-panel-id="camera-go2-front"]');
  await expect(camera.locator('.cockpit-camera-state')).toHaveText('LIVE');
  await page.locator('[data-cockpit-layout-action="apply"]').click();
  await expect(workspace).toHaveAttribute('data-layout-mode', 'operate');
  await expect(camera.locator('[data-panel-action="close"]')).toBeDisabled();
  await expect(camera.locator('[data-panel-action="focus"]')).toBeEnabled();

  const before = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  const title = await camera.locator('.cockpit-panel-titlebar').boundingBox();
  await page.mouse.move(title.x + 20, title.y + 20);
  await page.mouse.down();
  await page.mouse.move(title.x + 120, title.y + 80);
  await page.mouse.up();
  const after = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  expect({ x: after.x, y: after.y, width: after.width, height: after.height }).toEqual({ x: before.x, y: before.y, width: before.width, height: before.height });

  await camera.locator('[data-panel-action="focus"]').click();
  await expect(camera).toHaveAttribute('data-mode', 'focus');
  const layering = await page.evaluate(() => {
    const hudElement = document.querySelector('#cockpitSafetyHud');
    const stop = document.querySelector('[data-cockpit-software-stop]');
    const box = stop.getBoundingClientRect();
    return {
      hudZ: Number(getComputedStyle(hudElement).zIndex),
      panelZ: Number(getComputedStyle(document.querySelector('#cockpitPanelLayer')).zIndex),
      hit: document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2)?.closest?.('[data-cockpit-software-stop]') === stop,
    };
  });
  expect(layering.hudZ).toBeGreaterThan(layering.panelZ);
  expect(layering.hit).toBe(true);
  const stop = page.locator('[data-cockpit-software-stop]');
  await expect(stop).toContainText('물리 E-STOP 아님');
  await stop.click();
  await expect.poll(() => backend.mutations('/api/v1/control/stop').length).toBe(1);
  await expect(hud.locator('[data-safety-field="software-stop"]')).toHaveText('LATCHED');
});

test('active manual lease auto-locks Layout Edit and cancels an in-flight pointer operation', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'cockpit');
  await enterLayoutEdit(page);
  const button = page.locator('.cockpit-launcher-item[data-panel-type="camera.go2-front"]');
  await button.click();
  const camera = page.locator('[data-panel-id="camera-go2-front"]');
  const title = await camera.locator('.cockpit-panel-titlebar').boundingBox();
  await page.mouse.move(title.x + 20, title.y + 20);
  await page.mouse.down();
  await page.mouse.move(title.x + 75, title.y + 45);
  backend.state.control.lease = { active: true, bound: true, source: 'keyboard' };

  await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-layout-mode', 'operate');
  await expect(page.locator('[data-safety-field="armed"]')).toHaveText('ARMED');
  await expect(page.locator('[data-cockpit-layout-action="edit"]')).toBeDisabled();
  await expect.poll(() => page.evaluate(() => window.RobotScopeCockpit.snapshot().workspace.panels.interaction)).toBe(null);
  await page.mouse.up();
  const locked = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');

  const lockedTitle = await camera.locator('.cockpit-panel-titlebar').boundingBox();
  await page.mouse.move(lockedTitle.x + 20, lockedTitle.y + 20);
  await page.mouse.down();
  await page.mouse.move(lockedTitle.x + 110, lockedTitle.y + 70);
  await page.mouse.up();
  const unchanged = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  expect({ x: unchanged.x, y: unchanged.y }).toEqual({ x: locked.x, y: locked.y });
  await camera.locator('[data-panel-action="focus"]').click();
  await expect(camera).toHaveAttribute('data-mode', 'focus');
  await expect(button).toBeEnabled();

  backend.state.control.lease = { active: false, bound: false, source: null };
  await expect(page.locator('[data-safety-field="armed"]')).toHaveText('DISARMED');
  await expect(page.locator('[data-cockpit-layout-action="edit"]')).toBeEnabled();
});

test('Safety HUD clears stale cached values and preserves STOP and control source on a narrow viewport', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'cockpit');
  const hud = page.locator('#cockpitSafetyHud');
  await expect(hud.locator('[data-safety-field="go2-link"]')).toHaveText('LIVE');
  await expect(hud.locator('[data-safety-field="software-stop"]')).toHaveText('CLEAR');
  backend.on('/api/v1/control', ({ json }) => json({ detail: 'control unavailable' }, 503));
  backend.state.online = false;
  await expect(hud.locator('[data-safety-field="go2-link"]')).toHaveText('STALE');
  await expect(hud.locator('[data-safety-field="software-stop"]')).toHaveText('UNKNOWN');
  await expect(hud.locator('[data-safety-field="armed"]')).toHaveText('UNKNOWN');
  await expect(hud.locator('[data-safety-field="battery"]')).toHaveText('WAITING');

  await page.setViewportSize({ width: 520, height: 720 });
  await expect(hud).toBeVisible();
  await expect(hud.locator('[data-safety-field="control-source"]')).toBeVisible();
  await expect(page.locator('[data-cockpit-software-stop]')).toBeVisible();
  const bounds = await page.locator('[data-cockpit-software-stop]').boundingBox();
  expect(bounds.x).toBeGreaterThanOrEqual(0);
  expect(bounds.y).toBeGreaterThanOrEqual(0);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(520);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(720);
});

test('Cockpit preset saves normalized geometry, restores after reload, and imports only after preview apply', async ({ page }) => {
  await openDashboard(page, {}, 'cockpit');
  await expect(page.locator('.cockpit-layout-profile')).toHaveText('PROFILE · go2');
  await enterLayoutEdit(page);
  await page.locator('.cockpit-launcher-item[data-panel-type="camera.go2-front"]').click();
  const camera = page.locator('[data-panel-id="camera-go2-front"]');
  const title = await camera.locator('.cockpit-panel-titlebar').boundingBox();
  await page.mouse.move(title.x + 25, title.y + 25);
  await page.mouse.down();
  await page.mouse.move(title.x + 170, title.y + 105, { steps: 4 });
  await page.mouse.up();

  await page.locator('[data-layout-library-action="toggle"]').click();
  await page.locator('.cockpit-layout-library input[aria-label="새 Cockpit preset 이름"]').fill('competition-drive');
  await page.locator('[data-layout-library-action="save-as"]').click();
  await expect(page.locator('[data-cockpit-preset-list]')).toContainText('competition-drive · DEFAULT');
  const saved = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem('robot-scope.cockpit.layouts.v1.go2')));
  expect(stored.presets[0].panels[0].x).toBeGreaterThanOrEqual(0);
  expect(stored.presets[0].panels[0].x).toBeLessThanOrEqual(1);
  expect(stored.presets[0].panels[0].width).toBeLessThanOrEqual(1);

  await page.reload();
  await expect(page.locator('#cockpitWorkspace')).toBeVisible();
  await expect(page.locator('.cockpit-layout-profile')).toHaveText('PROFILE · go2');
  await expect(camera).toBeVisible();
  const restored = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  expect(Math.abs(restored.x - saved.x)).toBeLessThan(2);
  expect(Math.abs(restored.y - saved.y)).toBeLessThan(2);

  await enterLayoutEdit(page);
  const restoredTitle = await camera.locator('.cockpit-panel-titlebar').boundingBox();
  await page.mouse.move(restoredTitle.x + 25, restoredTitle.y + 25);
  await page.mouse.down();
  await page.mouse.move(restoredTitle.x - 80, restoredTitle.y - 40, { steps: 3 });
  await page.mouse.up();
  const changed = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  expect({ x: changed.x, y: changed.y }).not.toEqual({ x: restored.x, y: restored.y });

  await page.locator('[data-layout-library-action="toggle"]').click();
  await page.locator('[aria-label="Cockpit layout import JSON"]').fill('{bad');
  await page.locator('[data-layout-library-action="preview"]').click();
  await expect(page.locator('.cockpit-layout-library-status')).toHaveAttribute('data-error', 'true');
  const afterInvalid = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  expect({ x: afterInvalid.x, y: afterInvalid.y }).toEqual({ x: changed.x, y: changed.y });

  await page.locator('[aria-label="Cockpit layout import JSON"]').fill(JSON.stringify(stored.presets[0]));
  await page.locator('[data-layout-library-action="preview"]').click();
  await expect(page.locator('.cockpit-layout-library-status')).toContainText('아직 적용되지 않음');
  const afterPreview = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  expect({ x: afterPreview.x, y: afterPreview.y }).toEqual({ x: changed.x, y: changed.y });
  await page.locator('[data-layout-library-action="apply-import"]').click();
  const imported = (await page.evaluate(() => window.RobotScopeCockpit.snapshot())).workspace.panels.panels.find((panel) => panel.id === 'camera-go2-front');
  expect(Math.abs(imported.x - restored.x)).toBeLessThan(2);
  expect(Math.abs(imported.y - restored.y)).toBeLessThan(2);

  await page.setViewportSize({ width: 620, height: 700 });
  const bounds = await camera.locator('.cockpit-panel-titlebar').boundingBox();
  expect(bounds.x).toBeGreaterThanOrEqual(0);
  expect(bounds.y).toBeGreaterThanOrEqual(0);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(620);
});

test('Xbox Cockpit shortcuts select panels edge-wise and disconnect fails closed', async ({ page }) => {
  await page.addInitScript(() => {
    const state = { connected: true, timestamp: 1 };
    const buttons = Array.from({ length: 16 }, () => ({ pressed: false, value: 0 }));
    const pad = {
      id: 'Synthetic Xbox (Vendor: 045e Product: 02fd)', index: 0, connected: true,
      mapping: 'standard', axes: [0, 0, 0, 0], buttons, vibrationActuator: {},
      get timestamp() { return state.timestamp; },
    };
    Object.defineProperty(navigator, 'getGamepads', { configurable: true, value: () => state.connected ? [pad] : [] });
    window.__syntheticGamepad = {
      setButton(index, pressed) { buttons[index] = { pressed, value: pressed ? 1 : 0 }; state.timestamp += 1; },
      disconnect() { state.connected = false; pad.connected = false; state.timestamp += 1; },
    };
  });
  const backend = await openDashboard(page, {}, 'cockpit');
  await enterLayoutEdit(page);
  await page.locator('.cockpit-launcher-item[data-panel-type="placeholder.map"]').click();
  await page.locator('.cockpit-launcher-item[data-panel-type="placeholder.controller"]').click();
  await page.locator('[data-cockpit-layout-action="apply"]').click();
  const map = page.locator('[data-panel-id="placeholder-map"]');
  const controller = page.locator('[data-panel-id="placeholder-controller"]');
  await expect(controller.locator('[data-controller-metric="device"] strong')).toHaveText('Synthetic Xbox');

  await page.evaluate(() => window.__syntheticGamepad.setButton(15, true));
  await expect(map).toHaveClass(/is-gamepad-selected/);
  await page.waitForTimeout(180);
  await expect(map).toHaveClass(/is-gamepad-selected/);
  await page.evaluate(() => window.__syntheticGamepad.setButton(15, false));
  await page.waitForTimeout(70);
  await pressSyntheticGamepadButton(page, 15);
  await expect(controller).toHaveClass(/is-gamepad-selected/);

  await page.evaluate(() => window.__syntheticGamepad.setButton(3, true));
  await expect(controller).toHaveAttribute('data-mode', 'focus');
  await page.waitForTimeout(180);
  await expect(controller).toHaveAttribute('data-mode', 'focus', { timeout: 500 });
  await page.evaluate(() => window.__syntheticGamepad.setButton(3, false));
  await page.waitForTimeout(70);
  await pressSyntheticGamepadButton(page, 3);
  await expect(controller).toHaveAttribute('data-mode', 'floating');
  await pressSyntheticGamepadButton(page, 2);
  await expect(controller).toHaveAttribute('data-mode', 'compact');
  await pressSyntheticGamepadButton(page, 2);
  await expect(controller).toHaveAttribute('data-mode', 'floating');

  await pressSyntheticGamepadButton(page, 8);
  await expect(page.locator('#cockpitLauncherBody')).toBeHidden();
  await pressSyntheticGamepadButton(page, 9);
  await expect(page.locator('.cockpit-layout-library-body')).toBeVisible();

  await page.evaluate(() => window.__syntheticGamepad.disconnect());
  await expect(controller).not.toHaveClass(/is-gamepad-selected/);
  await expect(controller.locator('[data-controller-metric="connection"] strong')).toHaveText('DISCONNECTED');
  expect(backend.mutations('/api/v1/control/arm')).toHaveLength(0);
  expect(backend.mutations('/api/v1/control/stop')).toHaveLength(0);
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

test('map annotations use exact revisions and point goals reuse the Nav safety gate', async ({ page }) => {
  const backend = await installDashboardBackend(page);
  backend.state.navigation = {
    ...backend.state.navigation,
    pipeline: { state: 'running', job_id: 'f'.repeat(32), error: '' },
    localization_pipeline: { state: 'running', phase: 'running', pending: false, owned_by_navigation: false, job_id: 'c'.repeat(32), error: '' },
    map: { id: backend.mapId, revision: backend.mapRevision },
    localization: { state: 'localized', pose: { x: 0.5, y: 0.5, yaw: 0 } },
    goal: { state: 'idle', goal_id: null, message: '' },
    readiness: { map_server: true, planner: true, controller: true, behavior: true, cmd_bridge: true, map: true, scan: true, odometry: true, tf: true, localization: true },
    runtime_health: { localized: true },
    safety: { can_start: false, can_stop: true, can_set_initial_pose: true, can_send_goal: true, blockers: [] },
  };
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto('/#navigation');
  await expect(page.locator('.map-annotation-item')).toHaveCount(1);
  await expect(page.locator('.map-annotation-item')).toContainText('E2E Home');
  await page.locator('.map-annotation-item button[data-action="goal"]').click();
  await expect.poll(() => backend.mutations('/api/v1/navigation/goal/annotation').length).toBe(1);
  expect(backend.mutations('/api/v1/navigation/goal/annotation')[0].body).toEqual({
    map_id: backend.mapId,
    map_revision: backend.mapRevision,
    annotation_revision: backend.annotationRevision,
    annotation_id: backend.annotationId,
    confirmed: true,
  });
});

test('annotation edits are disabled during Nav2 and publish a full CAS document while idle', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'navigation');
  await expect(page.locator('.map-annotation-item')).toHaveCount(1);
  await page.locator('.map-annotation-item button[data-action="remove"]').click();
  await expect(page.locator('#mapAnnotationSave')).toBeEnabled();
  await page.locator('#mapAnnotationSave').click();
  await expect.poll(() => backend.mutations(`/api/v1/saved-maps/${backend.mapId}/annotations`).length).toBe(1);
  const body = backend.mutations(`/api/v1/saved-maps/${backend.mapId}/annotations`)[0].body;
  expect(body).toEqual({
    map_revision: backend.mapRevision,
    base_annotation_revision: backend.annotationRevision,
    points: [],
    polygons: [],
  });
  await page.locator('#navigationStartButton').click();
  await expect(page.locator('#mapAnnotationDraw')).toBeDisabled();
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

test('Settings exports one bounded diagnostics download without robot-work confirmation', async ({ page }) => {
  const backend = await openDashboard(page, {}, 'settings');
  await expect(page.locator('#diagnosticsExportButton')).toBeEnabled();
  const download = page.waitForEvent('download');
  await page.locator('#diagnosticsExportButton').dblclick();
  const artifact = await download;
  expect(artifact.suggestedFilename()).toBe('robot-scope-diagnostics-20260823T054500Z.zip');
  await expect.poll(() => backend.mutations('/api/v1/system/diagnostics/export').length).toBe(1);
  await expect(page.locator('#diagnosticsExportButton')).toBeEnabled();
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
