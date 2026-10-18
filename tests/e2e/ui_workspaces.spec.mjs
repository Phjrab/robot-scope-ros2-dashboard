import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

async function fixture(page) {
  const backend = await installDashboardBackend(page);
  const packages = [{ id: `np_${'a'.repeat(32)}`, name: 'UI fixture native map', engine_id: 'visual_stereo', native_artifacts: [] }];
  await page.route('**/api/v1/slam/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== 'GET') throw new Error(`Unexpected SLAM mutation: ${path}`);
    const value = path.endsWith('/engines') ? { engines: [
      { engine_id: 'lidar_fastlio', available_now: true, tasks: ['mapping'] },
      { engine_id: 'visual_stereo', available_now: true, tasks: ['mapping'] },
    ] } : path.endsWith('/session') ? { active_session: null }
      : path.endsWith('/packages') ? { packages }
        : path.endsWith('/preview') ? { global_map: { points: [], coverage: 'unknown', provenance: 'SYNTHETIC_FIXTURE' } } : {};
    return route.fulfill({ json: value });
  });
  await page.route('**/api/v1/routes', route => route.fulfill({ json: { routes: [] } }));
  await page.route('**/api/v1/mission-plans', route => route.fulfill({ json: { definitions: [], context: {} } }));
  await page.route('**/api/v1/mission-runs', route => route.fulfill({ json: { runs: [] } }));
  return backend;
}

for (const width of [390, 768, 1024, 1440]) {
  test(`mapping, saved maps, cameras and missions preserve usable layout at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    const backend = await fixture(page);
    const noOverflow = async () => expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    await page.goto('/#mapping');
    await expect(page.locator('#slamSessionState')).toHaveText('IDLE');
    await expect(page.locator('.slam-views')).toBeHidden();
    const layout = await page.locator('[data-page="mapping"]').evaluate(page => {
      const box = selector => page.querySelector(selector).getBoundingClientRect().toJSON();
      return { width: page.getBoundingClientRect().width, console: box('#slamConsole'), map: box('.mapping-panel'), controls: box('.mapping-control-panel') };
    });
    expect(layout.console.width).toBeGreaterThan(layout.width * .98);
    expect(layout.map.top).toBeGreaterThanOrEqual(layout.console.bottom);
    if (width > 1100) {
      expect(layout.map.width).toBeGreaterThan(layout.width * .6);
      expect(Math.abs(layout.map.top - layout.controls.top)).toBeLessThan(1);
    }
    await page.locator('#slamEngine').selectOption('visual_stereo');
    await expect(page.locator('.slam-views')).toBeVisible();
    await page.locator('#slamEngine').selectOption('lidar_fastlio');
    await noOverflow();

    await page.goto('/#maps');
    await expect(page.locator('#slamPackageRows button')).toHaveCount(1);
    await expect(page.locator('#slamNativeDetail')).toBeHidden();
    await page.locator('#slamPackageFilter').selectOption('vslam');
    await page.locator('#slamPackageRows button').click();
    await expect(page.locator('#slamNativeDetail')).toBeVisible();
    await expect(page.locator('#slamPackageRows button')).toHaveAttribute('aria-pressed', 'true');
    await page.locator('#slamPackageFilter').selectOption('vslam');
    await expect(page.locator('[data-page="maps"] .saved-layout')).toBeHidden();
    await expect(page.locator('.saved-tools-grid')).toBeHidden();
    await expect(page.locator('.map-crop-panel')).toBeHidden();
    await page.locator('#slamPackageFilter').selectOption('lidar');
    await expect(page.locator('#slamNativeDetail')).toBeHidden();
    await expect(page.locator('[data-page="maps"] .saved-layout')).toBeVisible();
    await expect(page.locator('.saved-tools-grid')).toBeVisible();
    await noOverflow();

    await page.goto('/#sensors');
    await expect(page.locator('#cameraDualMode')).toBeEnabled();
    await page.locator('#cameraDualMode').click();
    await expect(page.locator('#cameraSecondarySlot')).toBeVisible();
    const camera = await page.locator('.sensor-page-grid').evaluate(grid => {
      const rect = selector => grid.querySelector(selector).getBoundingClientRect();
      const camera = rect('.camera-panel'), capture = rect('.dataset-capture-panel');
      return { overlap: Math.min(camera.right,capture.right)-Math.max(camera.left,capture.left)>1 && Math.min(camera.bottom,capture.bottom)-Math.max(camera.top,capture.top)>1,
        clipped: [...grid.querySelectorAll('.dataset-source-picker label span')].some(node => node.scrollWidth > node.clientWidth + 1),
        stageWidths: [...grid.querySelectorAll('.camera-stage')].map(node => node.getBoundingClientRect().width) };
    });
    expect(camera.overlap).toBe(false); expect(camera.clipped).toBe(false);
    expect(camera.stageWidths.every(value => value >= 280)).toBe(true);
    await noOverflow();

    await page.goto('/#missions');
    const workspace = page.locator('.mr-workspace');
    await expect(workspace.getByRole('group', { name: '미션 작업 모드' })).toBeVisible();
    await expect(workspace.getByRole('group', { name: '미션 검사와 실행 준비' })).toBeVisible();
    const mission = await workspace.evaluate(root => ({
      footerPosition: getComputedStyle(root.querySelector('footer')).position,
      nameWidth: root.querySelector('[aria-label="미션 이름"]').getBoundingClientRect().width,
      mapWidth: root.querySelector('[aria-label="지도"]').getBoundingClientRect().width,
    }));
    expect(mission.footerPosition).toBe('static');
    expect(mission.nameWidth).toBeGreaterThan(200); expect(mission.mapWidth).toBeGreaterThan(200);
    await noOverflow();
    await workspace.getByRole('link', { name: '공통 STOP으로 이동' }).click();
    await expect(page.locator('[data-cockpit-software-stop]')).toBeVisible();
    expect(errors).toEqual([]);
    expect(backend.state.requests.filter(request => /control\/(arm|acquire|command|stop)|navigation\/(start|goal)|mapping\/(start|save)|missions/.test(request.path))).toEqual([]);
  });
}
