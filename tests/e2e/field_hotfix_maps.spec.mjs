import { test, expect } from '@playwright/test';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, delimiter } from 'node:path';
import { installDashboardBackend } from './dashboard_backend.mjs';
const exec = promisify(execFile);
test.setTimeout(60_000);

test('saved grid identity, palette, late selection, display ROI and yaw-aware real crop', async ({ page }, testInfo) => {
  const root = await mkdtemp(join(tmpdir(), 'a0-map-browser-'));
  try {
    const call = async (...args) => {
      const { stdout } = await exec(process.env.PCD_EDIT_TEST_PYTHON || 'python3',
        ['tests/e2e/field_hotfix_map_fixture.py', root, ...args],
        { env: { ...process.env, PYTHONPATH: [resolve('.'), resolve('tests')].join(delimiter) } });
      return JSON.parse(stdout);
    };
    let catalog = await call('init');
    const arena = catalog.maps.find(map => map.name === 'arena');
    const other = catalog.maps.find(map => map.name === 'other');
    const cloud = catalog.maps.find(map => map.name === 'hall');
    const projection = catalog.maps.find(map => map.name === 'projection');
    const original = await readFile(join(root, 'arena.pgm'));
    const originalPcd = await readFile(join(root, 'hall.pcd'));
    const backend = await installDashboardBackend(page);
    const errors = [], mutations = [];
    page.on('pageerror', error => errors.push(error.message));
    let held = null, crops = [];
    backend.on('/api/v1/saved-maps', ({ json }) => json(catalog));
    async function register(map) {
      const data = await call('data', map.id);
      backend.on('/api/v1/saved-maps/' + map.id + '/data', async ({ json }) => {
        if (held && map.id === other.id) await held;
        return json(data);
      });
      const family = await call('family', map.id);
      backend.on('/api/v1/saved-maps/' + map.id + '/family', ({ json }) => json(family));
      backend.on('/api/v1/saved-maps/' + map.id + '/cropped-copy', async ({ json, body }) => {
        mutations.push(body);
        const result = await call('crop', map.id, JSON.stringify(body));
        crops.push(result.map); catalog = await call('list');
        await register(result.map);
        return json(result, 201);
      });
    }
    for (const map of catalog.maps) await register(map);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto('/#maps');
    const select = id => page.locator('[data-saved-map-id="' + id + '"]').click();
    await select(cloud.id);
    await expect(page.locator('#savedMapPoints')).toContainText('POINTS');
    await select(projection.id);
    await expect(page.locator('#savedOccupancyDetails')).toContainText('원본 PCD ' + cloud.id);
    await expect(page.locator('#savedOccupancyDetails')).toContainText('최소 1점');
    await select(arena.id);
    await expect(page.locator('#savedOccupancyDetails')).toContainText(arena.id);
    await expect(page.locator('#savedMapPoints')).toHaveText('12×8 CELLS');
    await expect(page.locator('#savedOccupancyDetails')).toContainText('origin [1, 2, 1.5707963267948966]');
    await expect(page.locator('#savedOccupancyDetails')).toContainText('UNKNOWN 33.3%');
    await expect(page.locator('#savedOccupancyLegend')).toBeVisible();

    // Compare actual canvas pixels in both themes and at a narrow viewport.
    async function palette() {
      return page.locator('#savedMapCanvas').evaluate(canvas => {
        const colors = new Set(), pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
        for (let i = 0; i < pixels.length; i += 4) colors.add(Array.from(pixels.slice(i, i + 3)).join(','));
        return [...colors];
      });
    }
    for (const [theme, width] of [['dark', 1440], ['light', 1440], ['dark', 390], ['light', 390]]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(theme => { document.documentElement.dataset.theme = theme; window.dispatchEvent(new Event('resize')); }, theme);
      expect(await palette()).toEqual(expect.arrayContaining(['20,25,28', '125,136,148', '245,248,250']));
      await page.locator('.saved-map-panel').screenshot({ path: testInfo.outputPath('grid-' + theme + '-' + width + '.png') });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    let release;
    held = new Promise(resolve => { release = resolve; });
    await select(other.id);
    await expect(page.locator('#savedMapPoints')).toHaveText('LOADING');
    await expect(page.locator('#savedOccupancyDetails')).not.toContainText(arena.id);
    const alpha = await page.locator('#savedMapCanvas').evaluate(canvas => canvas.getContext('2d').getImageData(canvas.width / 2, canvas.height / 2, 1, 1).data[3]);
    expect(alpha).toBe(0);
    await select(arena.id);
    release(); held = null;
    await expect(page.locator('#savedMapPoints')).toHaveText('12×8 CELLS');
    await expect(page.locator('#savedOccupancyDetails')).toContainText(arena.id);
    await page.locator('#mapCropSelect').click();
    const box = await page.locator('#mapCropCanvas').boundingBox();
    await page.mouse.move(box.x + box.width * .35, box.y + box.height * .35);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * .65, box.y + box.height * .65);
    await page.mouse.up();
    await expect(page.locator('#mapCropView')).toBeEnabled();
    await page.locator('#mapCropView').click();
    await expect(page.locator('#mapCropView')).toHaveText('전체 지도 보기');
    expect(mutations).toEqual([]);
    await page.locator('#mapCropName').fill('arena_copy');
    page.once('dialog', dialog => dialog.accept());
    await page.locator('#mapCropSave').click();
    await expect.poll(() => crops.length).toBe(1);
    await expect(page.locator('#savedOccupancyDetails')).toContainText(crops[0].id);
    const crop = mutations[0].crop, grid = await call('data', crops[0].id);
    expect(grid.resolution).toBe(.5);
    expect(grid.origin[0]).toBeCloseTo(1 - crop.min_y * .5);
    expect(grid.origin[1]).toBeCloseTo(2 + crop.min_x * .5);
    expect(grid.origin[2]).toBeCloseTo(Math.PI / 2);
    expect(await readFile(join(root, 'arena.pgm'))).toEqual(original);
    expect(await readFile(join(root, 'hall.pcd'))).toEqual(originalPcd);
    await page.reload();
    await select(crops[0].id);
    await expect(page.locator('#savedMapPoints')).toHaveText(grid.width + '×' + grid.height + ' CELLS');
    expect(errors).toEqual([]);
    expect(backend.state.requests.filter(entry => /navigation|control|mapping/.test(entry.path))).toEqual([]);
  } finally { await rm(root, { recursive: true, force: true }); }
});
