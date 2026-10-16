import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

// Isolated browser fixture: no robot, broker, camera or ROS process is used.
async function fixture(page, { engine = null, empty = false } = {}) {
  const backend = await installDashboardBackend(page);
  const mutations = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/v1/slam/**', route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() !== 'GET') mutations.push(path);
    const packages = empty ? [] : [{ id: `np_${'a'.repeat(32)}`, name: 'Stereo office · UI fixture',
      engine_id: 'visual_stereo', native_artifacts: [{ path: 'data.mdb' }],
      revision: 'b'.repeat(64), map_frame: 'map', preview_consistency: 'approximate',
      data_provenance: 'SYNTHETIC_FIXTURE' }];
    const value = path.endsWith('/engines') ? { engines: [
      { engine_id: 'lidar_fastlio', available_now: true, tasks: ['mapping'] },
      { engine_id: 'visual_stereo', available_now: true, tasks: ['mapping'] },
    ] } : path.endsWith('/session') ? { active_session: engine ? {
      session_id: 'fixture', generation: 1, engine_id: engine, state: 'MAPPING', task: 'mapping', map_epoch: 'fixture',
    } : null } : path.endsWith('/packages') ? { packages }
      : path.endsWith('/preview') ? { global_map: { points: [[0, 0, 0], [1, 1, 0]],
        coordinate_frame: 'map', provenance: 'SYNTHETIC_FIXTURE', coverage: 'subset' } } : {};
    return route.fulfill({ json: value });
  });
  return { mutations, errors, backend };
}

for (const theme of ['dark', 'light']) {
  for (const width of [390, 768, 1440]) {
    test(`mapping menus and map library remain usable at ${width}px in ${theme}`, async ({ page }) => {
      const { mutations, errors, backend } = await fixture(page);
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/#mapping');
      if (theme === 'light') await page.locator('#themeToggle').click();
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await expect(page.locator('#slamConsole')).toHaveAttribute('data-presentation', 'workspace');
      await expect(page.locator('#slamSessionState')).toHaveText('IDLE');
      await expect(page.locator('#mappingStartButton')).toBeVisible();
      await expect(page.locator('#slamStart')).toBeHidden();
      await page.locator('#slamEngine').selectOption('visual_stereo');
      await expect(page.locator('#mappingStartButton')).toBeHidden();
      await expect(page.locator('.mapping-panel')).toBeHidden();
      await expect(page.locator('#slamCameraCanvas')).toBeVisible();
      await expect(page.locator('#slamGlobalCanvas')).toBeVisible();
      await expect(page.locator('#slamCameraPose')).toBeVisible();
      await expect(page.locator('#slamAvailability p')).toHaveCount(6);
      await expect(page.locator('#slamStart')).toBeDisabled();
      await expect(page.locator('#slamStop')).toBeDisabled();
      await expect(page.locator('#slamCreate2d')).toBeHidden();
      expect((await page.locator('#slamEngine').boundingBox()).height).toBeLessThan(56);
      const noOverflow = async () => expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
      await noOverflow();
      if (process.env.SLAM_PRESENTATION_CAPTURE) {
        await page.screenshot({ path: `${process.env.SLAM_PRESENTATION_CAPTURE}/mapping-${theme}-${width}.png`, fullPage: true });
      }
      await page.locator('#slamEngine').selectOption('lidar_fastlio');
      await expect(page.locator('.mapping-panel')).toBeVisible();
      await expect(page.locator('.slam-views')).toBeHidden();

      await page.getByRole('link', { name: '저장 지도 · 지도 탐색·편집', exact: true }).click();
      await page.locator('#slamPackageFilter').selectOption('vslam');
      expect((await page.locator('#slamPackageFilter').boundingBox()).height).toBeLessThan(56);
      await expect(page.locator('.saved-layout')).toBeHidden();
      await expect(page.locator('#slamArchiveEmpty')).toBeVisible();
      await page.locator('#slamPackageRows button').click();
      await expect(page.locator('#slamArchiveEmpty')).toBeHidden();
      await expect(page.locator('#slamPackageCanvas')).toBeVisible();
      await expect(page.locator('#slamPackageDetail')).toContainText('SYNTHETIC_FIXTURE');
      await expect(page.locator('#slamPackageExport')).toBeVisible();
      await noOverflow();
      if (process.env.SLAM_PRESENTATION_CAPTURE) {
        await page.screenshot({ path: `${process.env.SLAM_PRESENTATION_CAPTURE}/maps-${theme}-${width}.png`, fullPage: true });
      }
      await page.locator('#slamPackageFilter').selectOption('lidar');
      await expect(page.locator('.slam-archive-layout')).toBeHidden();
      await expect(page.locator('.saved-layout')).toBeVisible();
      await page.locator('#slamPackageFilter').selectOption('vslam');
      await expect(page.locator('#slamPackageRows button')).toHaveAttribute('aria-pressed', 'true');
      await expect(page.locator('#slamPackageCanvas')).toBeVisible();
      expect(mutations).toEqual([]);
      expect(backend.state.requests.filter(request => /control\/(arm|acquire|command|stop)|navigation\/(start|goal)|mapping\/(start|save)/.test(request.path))).toEqual([]);
      expect(errors).toEqual([]);
    });
  }
}

for (const engine of ['visual_stereo', 'lidar_fastlio']) {
  test(`active ${engine} session keeps its stop control visible on reconnect`, async ({ page }) => {
    const { mutations } = await fixture(page, { engine });
    await page.goto('/#mapping');
    await expect(page.locator('#slamSessionState')).toHaveText('MAPPING');
    await expect(page.locator('#slamEngine')).toBeDisabled();
    await expect(page.locator('#slamStart')).toBeDisabled();
    await expect(page.locator('#slamStop')).toBeVisible();
    await expect(page.locator('#slamStop')).toBeEnabled();
    if (engine === 'visual_stereo') {
      await expect(page.locator('.mapping-panel')).toBeHidden();
      await expect(page.locator('#slamCameraCanvas')).toBeVisible();
    }
    expect(mutations).toEqual([]);
  });
}

test('empty VSLAM library shows an explanation and import without losing LiDAR tools', async ({ page }) => {
  await fixture(page, { empty: true });
  await page.goto('/#maps');
  await page.locator('#slamPackageFilter').selectOption('vslam');
  await expect(page.locator('.slam-list-empty')).toBeVisible();
  await expect(page.locator('#slamPackageImport')).toBeVisible();
  await expect(page.locator('#slamArchiveEmpty')).toBeVisible();
  await page.locator('#slamPackageFilter').selectOption('lidar');
  await expect(page.locator('.saved-tools-grid')).toBeVisible();
});
