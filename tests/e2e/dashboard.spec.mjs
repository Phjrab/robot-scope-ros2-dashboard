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

test('Cockpit panels drag, resize, focus, lock, close, and recover without orbiting the scene', async ({ page }) => {
  await openDashboard(page, {}, 'cockpit');
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
  const toggle = page.locator('.cockpit-launcher-toggle');
  const body = page.locator('#cockpitLauncherBody');
  const cameraButton = page.locator('.cockpit-launcher-item[data-panel-type="camera.go2-front"]');
  const realsenseButton = page.locator('.cockpit-launcher-item[data-panel-type="camera.realsense-color"]');
  const mapButton = page.locator('.cockpit-launcher-item[data-panel-type="placeholder.map"]');
  const controllerButton = page.locator('.cockpit-launcher-item[data-panel-type="placeholder.controller"]');
  await expect(page.locator('.cockpit-launcher-item')).toHaveCount(4);
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
  await expect(realsense.locator('canvas')).toHaveJSProperty('width', 1);
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
  await expect(page.locator('.cockpit-launcher-item[data-panel-type="camera.go2-front"]')).toBeEnabled();
  const unavailable = page.locator('.cockpit-launcher-item[data-panel-type="camera.realsense-color"]');
  await expect(unavailable).toBeDisabled();
  await expect(unavailable).toContainText('UNAVAILABLE');
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
