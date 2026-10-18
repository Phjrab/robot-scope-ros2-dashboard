import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

// Isolated browser fixture: no robot, broker, camera or ROS process is used.
async function fixture(page, { engine = null, empty = false, packageCount = 1 } = {}) {
  const backend = await installDashboardBackend(page);
  const mutations = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/v1/slam/**', route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() !== 'GET') mutations.push(path);
    const packages = empty ? [] : Array.from({ length: packageCount }, (_, index) => ({ id: `np_${index.toString(16).padStart(32, 'a')}`, name: `Stereo office ${index + 1} · UI fixture`,
      engine_id: 'visual_stereo', native_artifacts: [{ path: 'data.mdb' }],
      revision: 'b'.repeat(64), map_frame: 'map', preview_consistency: 'approximate',
      data_provenance: 'SYNTHETIC_FIXTURE' }));
    const value = path.endsWith('/engines') ? { engines: [
      { engine_id: 'lidar_fastlio', available_now: true, tasks: ['mapping'] },
      { engine_id: 'visual_stereo', available_now: true, tasks: ['mapping'] },
    ] } : path.endsWith('/session') ? { generation: engine ? 1 : 0, active_session: engine ? {
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
      await expect(page.locator('#slamPackageFilter')).toHaveValue('lidar');
      await expect(page.locator('#slamPackageFilter option[value="all"]')).toHaveCount(0);
      const geometry = async (preview, inspector, stage) => page.locator('#slamPackageLibrary').evaluate((root, selectors) => {
        const rect = selector => root.querySelector(selector).getBoundingClientRect();
        const base = root.getBoundingClientRect();
        const [preview, inspector, stage] = selectors.map(rect);
        return { top: stage.top - base.top, height: stage.height, previewHeight: preview.height,
          previewBottom: preview.bottom - base.top, inspectorHeight: inspector.height,
          inspectorBottom: inspector.bottom - base.top, layoutBottom: root.querySelector('.saved-layout:not([hidden]), .slam-archive-layout:not([hidden])').getBoundingClientRect().bottom - base.top };
      }, [preview, inspector, stage]);
      const lidar = await geometry('.saved-map-panel', '.saved-library-panel', '.saved-map-stage');
      if (process.env.SLAM_PRESENTATION_CAPTURE) {
        await page.screenshot({ path: `${process.env.SLAM_PRESENTATION_CAPTURE}/maps-lidar-${theme}-${width}.png`, fullPage: true });
      }
      await page.locator('#slamPackageFilter').selectOption('vslam');
      expect((await page.locator('#slamPackageFilter').boundingBox()).height).toBeLessThan(56);
      await expect(page.locator('.saved-layout')).toBeHidden();
      await expect(page.locator('#slamArchiveEmpty')).toBeVisible();
      await page.locator('#slamPackageRows button').click();
      await expect(page.locator('#slamArchiveEmpty')).toBeHidden();
      await expect(page.locator('#slamPackageCanvas')).toBeVisible();
      const native = await geometry('.slam-archive-preview', '.slam-archive-sidebar', '#slamPackageCanvas');
      for (const key of ['top', 'height', 'previewHeight', 'inspectorHeight', 'layoutBottom']) {
        expect(Math.abs(native[key] - lidar[key]), key).toBeLessThan(1);
      }
      if (width > 1100) {
        expect(Math.abs(lidar.previewBottom - lidar.inspectorBottom)).toBeLessThan(1);
        expect(Math.abs(native.previewBottom - native.inspectorBottom)).toBeLessThan(1);
        expect(Math.abs(lidar.layoutBottom - lidar.previewBottom)).toBeLessThan(1);
      }
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

test('long archives scroll inside equal inspectors and keep management reachable', async ({ page }) => {
  const { backend, mutations, errors } = await fixture(page, { packageCount: 18 });
  backend.on('/api/v1/saved-maps', ({ json }) => json({ maps: Array.from({ length: 18 }, (_, index) => ({
    id: index.toString(16).padStart(24, '0'), name: `LiDAR office ${index + 1}`, revision: 'a'.repeat(64),
    kind: 'occupancy2d', format: 'map-server-pgm', file_name: `office-${index}.yaml`,
    frame_id: 'map', size_bytes: 4096, manageable: true, width: 4, height: 4,
  })) }));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/#maps');
  await expect(page.locator('#savedMapList [data-saved-map-id]')).toHaveCount(18);
  const assertBounded = async (previewSelector, inspectorSelector, listSelector) => {
    const size = await page.locator(inspectorSelector).evaluate((inspector, selectors) => {
      const preview = document.querySelector(selectors[0]).getBoundingClientRect();
      const list = document.querySelector(selectors[1]);
      return { bottom: inspector.getBoundingClientRect().bottom - preview.bottom,
        height: inspector.clientHeight, scrollHeight: inspector.scrollHeight,
        listHeight: list.clientHeight, listScrollHeight: list.scrollHeight };
    }, [previewSelector, listSelector]);
    expect(Math.abs(size.bottom)).toBeLessThan(1);
    expect(size.scrollHeight).toBeGreaterThan(size.height);
    expect(size.listScrollHeight).toBeGreaterThan(size.listHeight);
  };
  await assertBounded('.saved-map-panel', '.saved-library-panel', '#savedMapList');
  await page.locator('.saved-map-detail summary').click();
  await page.locator('#savedMapDeleteButton').scrollIntoViewIfNeeded();
  await expect(page.locator('#savedMapDeleteButton')).toBeInViewport();
  await assertBounded('.saved-map-panel', '.saved-library-panel', '#savedMapList');
  await page.locator('#slamPackageFilter').selectOption('vslam');
  await page.locator('#slamPackageRows button').last().click();
  await assertBounded('.slam-archive-preview', '.slam-archive-sidebar', '#slamPackageRows');
  await page.locator('#slamPackageExport').scrollIntoViewIfNeeded();
  await expect(page.locator('#slamPackageExport')).toBeInViewport();
  await page.locator('#slamArchiveReuse summary').click();
  await page.locator('#slamPackageLocalize').scrollIntoViewIfNeeded();
  await expect(page.locator('#slamPackageLocalize')).toBeInViewport();
  await expect(page.locator('#slamPackageLocalize')).toBeDisabled();
  await assertBounded('.slam-archive-preview', '.slam-archive-sidebar', '#slamPackageRows');
  expect(mutations).toEqual([]);
  expect(backend.state.requests).toEqual([]);
  expect(errors).toEqual([]);
});
