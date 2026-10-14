import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

for (const width of [390, 768, 1440, 1920]) {
  test(`menu disappears and dual cameras stay outside dataset at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await installDashboardBackend(page);
    await page.goto('/#sensors');
    await expect(page.locator('#cameraDualMode')).toBeEnabled();
    await page.locator('#cameraDualMode').click();
    await expect(page.locator('#cameraViewGrid')).toHaveAttribute('data-view-mode', 'dual');
    const overlap = () => page.evaluate(() => {
      const camera = document.querySelector('.sensor-page-grid .camera-panel').getBoundingClientRect();
      const dataset = document.querySelector('.dataset-capture-panel').getBoundingClientRect();
      return Math.min(camera.right, dataset.right) - Math.max(camera.left, dataset.left) > 1
        && Math.min(camera.bottom, dataset.bottom) - Math.max(camera.top, dataset.top) > 1;
    });
    expect(await overlap()).toBe(false);
    await page.locator('#navigationToggle').click();
    await expect(page.locator('.sidebar')).toBeHidden();
    await expect(page.locator('#navigationToggle')).toHaveAccessibleName('메뉴 펼치기');
    expect(await overlap()).toBe(false);
    await page.locator('#navigationToggle').click();
    await expect(page.locator('.sidebar')).toBeVisible();
    await expect(page.locator('#navigationToggle')).toHaveAccessibleName('메뉴 접기');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    if (width === 1440) await page.screenshot({ path: test.info().outputPath('dual-camera.png'), fullPage: true });
  });
}

test('resource monitor is a native route, shares both palettes and pauses outside its page', async ({ page, context }) => {
  const backend = await installDashboardBackend(page);
  let seq = 0;
  backend.on('/api/v1/system/resources', ({ json }) => json({
    schema: 'robot-scope.resources.v1', seq: ++seq, timestamp_ms: Date.now(), sample_interval_s: 1,
    host: { model: 'Jetson fixture', hostname: 'fixture' },
    cpu: { percent: 25, cores: [] }, gpu: { percent: 15 }, memory: { percent: 40 }, sensors: {},
  }));
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/#overview');
  const initialPages = context.pages().length;
  await page.locator('[data-nav="resources"]').first().click();
  await expect(page).toHaveURL(/#resources$/);
  await expect(page.locator('.sidebar')).toBeVisible();
  await expect(page.locator('#resourceMonitor #hostModel')).toHaveText('Jetson fixture');
  expect(context.pages().length).toBe(initialPages);
  expect(await page.locator('iframe').count()).toBe(0);
  for (const theme of ['light', 'dark']) {
    await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
    const colors = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement);
      const monitor = getComputedStyle(document.querySelector('#resourceMonitor'));
      const panel = getComputedStyle(document.querySelector('#resourceMonitor .metric-card'));
      const probe = document.createElement('span'); document.body.append(probe);
      probe.style.color = root.getPropertyValue('--bg'); const bg = getComputedStyle(probe).color;
      probe.style.color = root.getPropertyValue('--panel'); const card = getComputedStyle(probe).color;
      probe.remove(); return { bg, card, monitor: monitor.backgroundColor, panel: panel.backgroundColor };
    });
    expect(colors.monitor).toBe(colors.bg); expect(colors.panel).toBe(colors.card);
  }
  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
  }
  await page.locator('#resourceMonitor #experimentNote').fill('keep local note');
  await page.locator('[data-nav="navigation"]').click();
  await expect(page.locator('#resourceMonitor')).toBeHidden();
  await page.waitForTimeout(150); const stopped = seq;
  await page.waitForTimeout(1300); expect(seq).toBe(stopped);
  await page.locator('[data-nav="resources"]').first().click();
  await expect(page.locator('#resourceMonitor #connectionState')).toHaveAttribute('data-state', 'live');
  await expect(page.locator('#resourceMonitor #experimentNote')).toHaveValue('keep local note');
  await page.screenshot({ path: test.info().outputPath('resources.png'), fullPage: true });
  expect(errors).toEqual([]);
  expect(backend.mutations('/api/v1/control/arm')).toHaveLength(0);
  expect(backend.mutations('/api/v1/navigation/start')).toHaveLength(0);
});

test('overview reports fresh ROS LiDAR without opening binary pointcloud transport', async ({ page }) => {
  const backend = await installDashboardBackend(page);
  let fresh = true;
  backend.on('/api/v1/state', ({ json }) => json({
    health: { agent_ready: true, robot_target_connected: true, robot_online: true, robot_ip: '192.0.2.10' },
    sources: { pointcloud: '/velodyne_points' },
    cloud: { topic: '/velodyne_points', sent_points: 16000, frame_id: 'hesai_lidar' },
    mapping: { state: fresh ? 'cloud_only' : 'stale', cloud: { state: fresh ? 'ok' : 'stale', age_s: fresh ? 0.1 : 9, hz: 10 } },
  }));
  await page.goto('/#overview');
  await expect(page.locator('#lidarMetric')).toHaveText('10.0 Hz');
  expect(backend.state.wsConnections.pointcloud).toBe(0);
  fresh = false;
  await expect(page.locator('#lidarMetric')).toHaveText('OFFLINE', { timeout: 8000 });
  fresh = true;
  await expect(page.locator('#lidarMetric')).toHaveText('10.0 Hz', { timeout: 8000 });
});
